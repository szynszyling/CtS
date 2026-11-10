import io
from pathlib import Path
import threading
import unittest
from unittest.mock import patch,Mock

from fastapi.testclient import TestClient
from PIL import Image
import numpy as np

from cts_ocr_server.engine import ctc_runs,compatible_parameters,NcnnEngine,validate_probabilities
from cts_ocr_server.service import create_app,InferenceWorker


class FakeEngine:
    device='vulkan';device_name='test GPU';gpu_index=1
    precision='fp32';self_test_passed=True
    detector_scale=2.
    def recognize(self,image,vertical=False,on_yield=None):
        return [{'text':'語','bbox':[2,3,10,12],'line':'0','word':'0','confidence':99}]


def png():
    buffer=io.BytesIO();Image.new('RGB',(64,48),'white').save(buffer,format='PNG');return buffer.getvalue()


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(create_app(FakeEngine(),'test-secret'))
        self.client.__enter__()
        self.headers={'Authorization':'Bearer test-secret','Content-Type':'image/png'}

    def tearDown(self):self.client.__exit__(None,None,None)

    def test_authentication_and_real_image_dimensions(self):
        self.assertEqual(self.client.get('/v1/health').status_code,401)
        health=self.client.get('/v1/health',headers=self.headers).json()
        self.assertEqual(health['device'],'test GPU')
        self.assertEqual(health['precision'],'fp32')
        self.assertTrue(health['self_test_passed'])
        self.assertEqual(health['detector_scale'],2.)
        result=self.client.post('/v1/ocr?priority=interactive',headers=self.headers,content=png())
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual((result.json()['width'],result.json()['height']),(64,48))
        self.assertEqual(result.json()['glyphs'][0]['text'],'語')

    def test_invalid_format_language_and_payload_are_rejected(self):
        self.assertEqual(self.client.post('/v1/ocr',headers={'Authorization':'Bearer test-secret'},content=png()).status_code,415)
        self.assertEqual(self.client.post('/v1/ocr?language=pol',headers=self.headers,content=png()).status_code,422)
        self.assertEqual(self.client.post('/v1/ocr',headers=self.headers,content=b'not PNG').status_code,400)
        with patch('cts_ocr_server.service.MAX_BYTES',10):
            self.assertEqual(self.client.post('/v1/ocr',headers=self.headers,content=png()).status_code,413)
        with patch('cts_ocr_server.service.MAX_PIXELS',100):
            self.assertEqual(self.client.post('/v1/ocr',headers=self.headers,content=png()).status_code,413)

    def test_inference_failures_do_not_return_tracebacks(self):
        with self.assertLogs('cts_ocr_server.service',level='ERROR'),patch.object(FakeEngine,'recognize',side_effect=RuntimeError('private-server-path')):
            response=self.client.post('/v1/ocr',headers=self.headers,content=png())
        self.assertEqual(response.status_code,500)
        self.assertNotIn('private-server-path',response.text)


class QueueTests(unittest.TestCase):
    def test_interactive_work_runs_before_queued_background_work(self):
        started=threading.Event();release=threading.Event();order=[]
        class Engine(FakeEngine):
            def recognize(self,image,vertical=False,on_yield=None):
                if not order:started.set();release.wait(3)
                order.append(image.width)
                return []
        worker=InferenceWorker(Engine())
        try:
            first=worker.submit(Image.new('RGB',(1,1)),False,False)
            self.assertTrue(started.wait(2))
            background=worker.submit(Image.new('RGB',(2,1)),False,False)
            interactive=worker.submit(Image.new('RGB',(3,1)),False,True)
            release.set()
            for future in (first,background,interactive):future.result(timeout=3)
            self.assertEqual(order,[1,3,2])
        finally:release.set();worker.close()

    def test_gesture_interrupts_an_in_progress_background_scan(self):
        started=threading.Event();release=threading.Event();order=[]
        class Engine(FakeEngine):
            def recognize(self,image,vertical=False,on_yield=None):
                if image.width==1:
                    order.append('background-start')
                    started.set();release.wait(3)
                    on_yield()
                    order.append('background-end')
                else:order.append('gesture')
                return []
        worker=InferenceWorker(Engine())
        try:
            background=worker.submit(Image.new('RGB',(1,1)),False,False)
            self.assertTrue(started.wait(2))
            gesture=worker.submit(Image.new('RGB',(3,1)),False,True)
            release.set()
            background.result(timeout=3);gesture.result(timeout=3)
            self.assertEqual(order,['background-start','gesture','background-end'])
        finally:release.set();worker.close()


class GeometryTests(unittest.TestCase):
    def test_detector_scale_rejects_invalid_values_before_loading_models(self):
        for scale in (0,.9,2.1,float('nan'),float('inf')):
            with self.subTest(scale=scale),self.assertRaisesRegex(ValueError,'Detector scale'):
                NcnnEngine('/unused',detector_scale=scale)

    def test_corrupt_probabilities_never_decode_into_confident_letters(self):
        for value in (np.nan,np.inf,-np.inf,-.5,1.5):
            with self.subTest(value=value),self.assertRaises(RuntimeError):
                ctc_runs(np.array([[.1,value,.9],[.2,value,.8]]))
        for probabilities in (np.array([]),np.empty((0,3)),np.zeros((2,3)),np.full((2,3),.5)):
            with self.subTest(shape=probabilities.shape),self.assertRaises(RuntimeError):
                ctc_runs(probabilities)
        with self.assertRaises(RuntimeError):validate_probabilities(np.array([[np.nan]]))

    def test_full_precision_is_selected_before_loading_models(self):
        engine=NcnnEngine.__new__(NcnnEngine)
        engine.device='vulkan';engine.gpu_index=0;engine.ncnn=Mock()
        net=engine.ncnn.Net.return_value
        def check_precision(*args):
            for flag in ('use_fp16_packed','use_fp16_storage','use_fp16_arithmetic',
                         'use_bf16_storage','use_int8_storage','use_int8_arithmetic'):
                self.assertIs(getattr(net.opt,flag),False)
            self.assertTrue(net.opt.use_vulkan_compute)
            return 0
        net.load_param_mem.side_effect=check_precision
        net.load_model.return_value=0
        with patch('pathlib.Path.read_text',return_value='7767517\n0 0\n'):
            engine.load_net(Path('/unused'),'rec')

    def test_self_test_rejects_broken_recognition_and_blocks_readiness(self):
        engine=NcnnEngine.__new__(NcnnEngine)
        engine.recognize=Mock(return_value=[{'text':'Y'}])
        with self.assertRaisesRegex(RuntimeError,'self-test expected'):engine.self_test()
        self.assertFalse(engine.self_test_passed)
        with self.assertRaisesRegex(RuntimeError,'self-test'):create_app(engine)

    def test_self_test_checks_different_text_and_a_blank_image(self):
        engine=NcnnEngine.__new__(NcnnEngine)
        correct=[[{'text':text}] for text in ('Circle these words','Hello World 123')]
        engine.recognize=Mock(side_effect=correct+[[]])
        engine.self_test()
        self.assertTrue(engine.self_test_passed)
        engine.recognize=Mock(side_effect=correct+[[{'text':'Y'}]])
        with self.assertRaisesRegex(RuntimeError,'blank'):engine.self_test()
        self.assertFalse(engine.self_test_passed)

    def test_ctc_keeps_repeated_letters_separated_by_a_blank(self):
        probabilities=np.array([[.1,.9,0],[.2,.8,0],[1,0,0],[.1,.9,0],[.1,0,.9]])
        runs=ctc_runs(probabilities)
        self.assertEqual([run[:3] for run in runs],[[1,0,2],[1,3,4],[2,4,5]])

    def test_linear_conversion_is_limited_to_pooled_vectors(self):
        params='7767517\n4 4\nConvolution regular 1 1 in0 a 0=8 1=1 5=1 6=64\nPooling pool 1 1 a b 0=1 4=1\nConvolution linear 1 1 b c 0=4 1=1 5=1 6=32 9=1\nConvolution linear2 1 1 c out0 0=8 1=1 5=1 6=32\n'
        result=compatible_parameters(params)
        self.assertIn('Convolution regular',result)
        self.assertIn('InnerProduct linear 1 1 b c 0=4 1=1 2=32 9=1',result)
        self.assertIn('InnerProduct linear2',result)

    def test_vulkan_mode_rejects_unavailable_and_software_devices(self):
        with patch('ncnn.get_gpu_count',return_value=0):
            with self.assertRaisesRegex(RuntimeError,'unavailable'):NcnnEngine('/tmp/unused')
        with patch('ncnn.get_gpu_count',return_value=1),patch('ncnn.get_gpu_info') as info:
            info.return_value.device_name.return_value='lavapipe'
            with self.assertRaisesRegex(RuntimeError,'software'):NcnnEngine('/tmp/unused')


if __name__=='__main__':unittest.main()
