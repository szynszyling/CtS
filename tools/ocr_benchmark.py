"""Time local OCR on a synthetic desktop; no capture or network requests."""

import argparse
import os
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QRect,Qt
from PySide6.QtGui import QColor,QFont,QImage,QPainter
from PySide6.QtWidgets import QApplication

from circle_to_search.ocr import recognize_document


def desktop(size=None):
    image=QImage(size.width() if size else 1920,size.height() if size else 1080,QImage.Format.Format_RGB32)
    image.fill(QColor('#202124'))
    painter=QPainter(image)
    font=QFont('Noto Sans CJK JP');font.setPixelSize(14)
    painter.setFont(font);painter.setPen(Qt.GlobalColor.white)
    lines=['Circle these words to search the desktop.',
           '東京で日本語を勉強しています',
           'ひらがなとカタカナと漢字',
           'Select text, translate a phrase, or search an image.']
    for x in range(60,image.width(),620):
        for row in range(max(1,(image.height()-100)//25)):
            painter.drawText(x,80+row*25,lines[row%len(lines)])
    painter.end()
    return image


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--threads',choices=['default','1'],default='default')
    parser.add_argument('--case',choices=['full','region','both'],default='both')
    parser.add_argument('--runs',type=int,default=2)
    args=parser.parse_args()
    if args.threads=='1':os.environ['OMP_THREAD_LIMIT']='1'
    os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
    app=QApplication([])
    image=desktop()
    cases={'full':image,'region':image.copy(QRect(40,275,580,90))}
    for name,sample in cases.items():
        if args.case not in ('both',name):continue
        samples=[]
        for run in range(args.runs):
            start=time.perf_counter()
            document=recognize_document(sample)
            samples.append(time.perf_counter()-start)
            print(f'{name} threads={args.threads} run={run+1}: {samples[-1]*1000:.0f} ms, {len(document.glyphs)} glyphs',flush=True)
        print(f'{name} median: {statistics.median(samples)*1000:.0f} ms',flush=True)


if __name__=='__main__':
    main()
