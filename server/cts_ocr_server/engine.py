"""PP-OCRv5 on ncnn's Vulkan backend, with CTC-aligned character boxes.

Detection/preprocessing follows Tencent's BSD-3-Clause ppocrv5 example;
see THIRD_PARTY.md. Character geometry is mapped back through the actual
recognizer crop, rather than assigning equal widths to a returned string.
"""

import hashlib
import json
import math
from pathlib import Path
import re
import urllib.request


def fetch_models(directory):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    manifest=json.loads(Path(__file__).with_name('models.json').read_text())
    for name,entry in manifest.items():
        target=directory/name
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest()==entry['sha256']:
            continue
        request=urllib.request.Request(entry['url'],headers={'User-Agent':'CircleToSearch-OCR/0.12'})
        with urllib.request.urlopen(request,timeout=60) as response:
            data=response.read(128*1024*1024)
        if hashlib.sha256(data).hexdigest()!=entry['sha256']:
            raise RuntimeError('Model checksum failed: '+name)
        temporary=target.with_suffix(target.suffix+'.tmp')
        temporary.write_bytes(data)
        temporary.replace(target)
    return directory


def dictionary(path):
    # This upstream header consists of UTF-8 C string literals, one per entry.
    content=Path(path).read_text(encoding='utf-8')
    return [json.loads(value) for value in re.findall(r'^\s*("(?:[^"\\]|\\.)*")\s*,?\s*$',content,re.MULTILINE)]


def ctc_runs(probabilities):
    """Collapse repeated CTC steps while retaining each character's span."""
    import numpy as np
    indices=np.argmax(probabilities,axis=1)
    result=[]
    previous=0
    for step,token in enumerate(indices):
        token=int(token)
        confidence=float(probabilities[step,token])
        if token and token==previous:
            result[-1][2]=step+1
            result[-1][3]=max(result[-1][3],confidence)
        elif token:
            result.append([token,step,step+1,confidence])
        previous=token
    return result


def compatible_parameters(text):
    """Use ncnn's current linear layer after global pooling.

    These pinned 2025 exports use 1x1 Convolution on 1-D pooled tensors.
    ncnn 2026 explicitly deprecates that path and prescribes InnerProduct;
    its parameter/weight layout is identical under this remapping. Keeping
    the source assets intact preserves their upstream checksums.
    """
    flat=set();output=[]
    for line in text.splitlines():
        parts=line.split()
        if len(parts)<4 or not parts[2].isdigit() or not parts[3].isdigit():
            output.append(line);continue
        bottom_count,top_count=map(int,parts[2:4])
        bottoms=parts[4:4+bottom_count]
        tops=parts[4+bottom_count:4+bottom_count+top_count]
        attributes=dict(value.split('=',1) for value in parts[4+bottom_count+top_count:] if '=' in value)
        pooled=parts[0]=='Pooling' and attributes.get('4')=='1'
        inherited=bool(bottoms) and all(value in flat for value in bottoms)
        if parts[0]=='Convolution' and inherited and all(attributes.get(key,default)==default for key,default in
                (('1','1'),('11','1'),('2','1'),('12','1'),('3','1'),('13','1'),('4','0'),('14','0'))):
            mapped={'0':attributes['0'],'1':attributes.get('5','0'),'2':attributes['6']}
            for key in ('8','9','-23310'):
                if key in attributes:mapped[key]=attributes[key]
            parts[0]='InnerProduct'
            line=' '.join(parts[:4+bottom_count+top_count]+[key+'='+value for key,value in mapped.items()])
        if pooled or (inherited and parts[0] in ('InnerProduct','Split','ReLU','HardSigmoid','HardSwish','Sigmoid','BinaryOp','UnaryOp')):
            flat.update(tops)
        output.append(line)
    return '\n'.join(output)+'\n'


def order_quad(points):
    import numpy as np
    center=points.mean(axis=0)
    angles=np.arctan2(points[:,1]-center[1],points[:,0]-center[0])
    points=points[np.argsort(angles)]
    return np.roll(points,-int(np.argmin(points.sum(axis=1))),axis=0).astype(np.float32)


class NcnnEngine:
    def __init__(self,model_dir,device='vulkan',gpu_index=0):
        import ncnn
        self.ncnn=ncnn
        self.device=device
        self.gpu_index=gpu_index
        if device not in ('vulkan','cpu'):
            raise ValueError('Device must be vulkan or cpu.')
        if device=='vulkan':
            count=ncnn.get_gpu_count()
            if not 0<=gpu_index<count:
                raise RuntimeError(f'Vulkan GPU {gpu_index} is unavailable ({count} devices found).')
            info=ncnn.get_gpu_info(gpu_index)
            self.device_name=info.device_name()
            if info.type()==4 or any(word in self.device_name.lower() for word in ('llvmpipe','lavapipe','swiftshader','software')):
                raise RuntimeError('A software Vulkan renderer cannot be used as GPU acceleration.')
        else:
            self.device_name='CPU (explicit development mode)'
        model_dir=fetch_models(model_dir)
        self.characters=['']+dictionary(model_dir/'ppocrv5_dict.h')+[' ']
        self.detector=self.load_net(model_dir,'det')
        self.recognizer=self.load_net(model_dir,'rec')

    def load_net(self,directory,task):
        net=self.ncnn.Net()
        net.opt.num_threads=4
        net.opt.use_vulkan_compute=self.device=='vulkan'
        if self.device=='vulkan':
            net.set_vulkan_device(self.gpu_index)
        prefix=directory/('PP_OCRv5_mobile_'+task+'.ncnn')
        parameters=compatible_parameters(Path(str(prefix)+'.param').read_text())
        if net.load_param_mem(parameters) or net.load_model(str(prefix)+'.bin'):
            raise RuntimeError('Could not load the '+task+' model.')
        if self.device=='vulkan' and (not net.opt.use_vulkan_compute or net.vulkan_device() is None):
            raise RuntimeError('ncnn did not activate Vulkan; refusing a silent CPU fallback.')
        return net

    def infer(self,net,pixels,mean,norm):
        import numpy as np
        data=np.ascontiguousarray(pixels.transpose(2,0,1),dtype=np.float32)
        mat=self.ncnn.Mat(data).clone()
        mat.substract_mean_normalize(mean,norm)
        with net.create_extractor() as extractor:
            if extractor.input('in0',mat):
                raise RuntimeError('The OCR input tensor was rejected.')
            code,output=extractor.extract('out0')
            if code:
                raise RuntimeError('The OCR GPU inference failed.')
            return np.array(output,copy=True)

    def detect(self,image):
        import cv2
        import numpy as np
        import pyclipper
        height,width=image.shape[:2]
        scale=min(2.,1600/max(height,width))
        w,h=max(1,round(width*scale)),max(1,round(height*scale))
        resized=cv2.resize(image,(w,h),interpolation=cv2.INTER_LINEAR)
        xpad=(-w)%32;ypad=(-h)%32
        padded=cv2.copyMakeBorder(resized,ypad//2,ypad-ypad//2,xpad//2,xpad-xpad//2,cv2.BORDER_CONSTANT,value=(114,114,114))
        probability=self.infer(self.detector,padded,[.485*255,.456*255,.406*255],[1/(.229*255),1/(.224*255),1/(.225*255)]).squeeze()
        if probability.ndim!=2:
            raise RuntimeError('Unexpected detector output shape.')
        mask=(probability>.3).astype(np.uint8)*255
        contours,_=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        result=[]
        for contour in contours[:1000]:
            if len(contour)<3:continue
            x,y,cw,ch=cv2.boundingRect(contour)
            area_mask=np.zeros((ch,cw),dtype=np.uint8)
            cv2.fillPoly(area_mask,[contour-np.array([x,y])],1)
            score=cv2.mean(probability[y:y+ch,x:x+cw],mask=area_mask)[0]
            if score<.5:continue
            rect=cv2.minAreaRect(contour)
            if min(rect[1])<3:continue
            box=cv2.boxPoints(rect)
            perimeter=cv2.arcLength(box,True)
            if perimeter<=0:continue
            offset=pyclipper.PyclipperOffset()
            offset.AddPath(box.tolist(),pyclipper.JT_ROUND,pyclipper.ET_CLOSEDPOLYGON)
            expanded=offset.Execute(cv2.contourArea(box)*1.6/perimeter)
            if len(expanded)!=1:continue
            box=cv2.boxPoints(cv2.minAreaRect(np.asarray(expanded[0],dtype=np.float32)))
            box[:,0]=(box[:,0]-xpad//2)/(w/width)
            box[:,1]=(box[:,1]-ypad//2)/(h/height)
            box[:,0]=np.clip(box[:,0],0,width)
            box[:,1]=np.clip(box[:,1],0,height)
            result.append(order_quad(box))
        return result

    def recognize_line(self,image,quad,line_id):
        import cv2
        import numpy as np
        width=max(np.linalg.norm(quad[1]-quad[0]),np.linalg.norm(quad[2]-quad[3]))
        height=max(np.linalg.norm(quad[3]-quad[0]),np.linalg.norm(quad[2]-quad[1]))
        if min(width,height)<1:return []
        if height>width*1.5:
            quad=np.roll(quad,-1,axis=0)
            width,height=height,width
        crop_width=max(8,min(4096,math.ceil(48*width/height)))
        target=np.array([[0,0],[crop_width,0],[crop_width,48],[0,48]],np.float32)
        transform=cv2.getPerspectiveTransform(quad,target)
        inverse=cv2.getPerspectiveTransform(target,quad)
        crop=cv2.warpPerspective(image,transform,(crop_width,48),borderMode=cv2.BORDER_REPLICATE)
        probabilities=self.infer(self.recognizer,crop,[127.5]*3,[1/127.5]*3).squeeze()
        if probabilities.ndim!=2 or probabilities.shape[1]!=len(self.characters):
            raise RuntimeError(f'Recognizer/dictionary mismatch: {probabilities.shape}, {len(self.characters)} characters.')
        runs=ctc_runs(probabilities)
        if not runs or sum(run[3] for run in runs)/len(runs)<.5:return []
        steps=probabilities.shape[0]
        glyphs=[];word=0
        for i,(token,start,end,score) in enumerate(runs):
            text=self.characters[token]
            if text.isspace():word+=1;continue
            # Boundaries follow the model's CTC centers, including variable-width
            # Latin letters and Japanese kana; no phrase-level box is fabricated.
            center=(start+end)/2
            previous=(runs[i-1][1]+runs[i-1][2])/2 if i else max(0,center-(end-start)*2)
            following=(runs[i+1][1]+runs[i+1][2])/2 if i+1<len(runs) else min(steps,center+(end-start)*2)
            left=max(0,(previous+center)/2)*crop_width/steps
            right=min(steps,(center+following)/2)*crop_width/steps
            points=np.array([[[left,0],[right,0],[right,48],[left,48]]],np.float32)
            points=cv2.perspectiveTransform(points,inverse)[0]
            lo=points.min(axis=0);hi=points.max(axis=0)
            glyphs.append({'text':text,'bbox':[float(lo[0]),float(lo[1]),float(hi[0]-lo[0]),float(hi[1]-lo[1])],
                           'line':str(line_id),'word':f'{line_id}:{word}','confidence':max(0,min(100,score*100))})
        return glyphs

    def recognize(self,image,vertical=False,on_yield=None):
        import cv2
        import numpy as np
        pixels=cv2.cvtColor(np.asarray(image.convert('RGB')),cv2.COLOR_RGB2BGR)
        if on_yield:on_yield()
        quads=self.detect(pixels)
        quads.sort(key=(lambda q:(-float(q[:,0].mean()),float(q[:,1].min()))) if vertical else
                   (lambda q:(round(float(q[:,1].min())/12),float(q[:,0].min()))))
        glyphs=[]
        for index,quad in enumerate(quads):
            if on_yield:on_yield()
            glyphs.extend(self.recognize_line(pixels,quad,index))
        return glyphs
