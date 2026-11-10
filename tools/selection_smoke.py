"""Measure actual first-selection latency on a synthetic desktop, offline."""

import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint,QThreadPool,QTimer,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from circle_to_search.appearance import prepare_qt
from circle_to_search.ui import SelectionOverlay
from tools.ocr_benchmark import desktop


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--japanese',action='store_true',help='Measure a small Japanese underline selection')
    parser.add_argument('--gpu',action='store_true',help='Use CtS’s managed local GPU backend')
    args=parser.parse_args()
    if args.gpu:
        from circle_to_search.ocr_backend import OcrConfig,configure_ocr
        config=OcrConfig.load()
        from dataclasses import replace
        configure_ocr(replace(config,backend='gpu'))
    prepare_qt()
    app=QApplication([])
    app.setApplicationName('circle-to-search-selection-check')
    screen=app.primaryScreen()
    print('Platform:',app.platformName(),'screen:',screen.size(),flush=True)
    image=desktop(screen.size())
    overlay=SelectionOverlay(image,screen,auto_search=False)
    overlay.show_overlay()
    started=time.perf_counter()
    clicked=[None]
    selected=[False]
    full_done=[False]
    failures=[]
    original_ready=overlay.recognition_ready
    def full_ready(document,generation):
        full_done[0]=True
        original_ready(document,generation)
        print(f'Full-screen OCR ready: {(time.perf_counter()-started)*1000:.0f} ms',flush=True)
        from circle_to_search.gestures import resolve_gesture
        from PySide6.QtCore import QPointF,QRectF
        points=[QPointF(64,110),QPointF(98,110)] if args.japanese else [QPointF(70,74)]
        full_selection=resolve_gesture(points,QRectF(overlay.rect()),overlay.full_document)
        print('Full-screen selection:',repr(full_selection.text),flush=True)
        if selected[0]:app.quit()
    overlay.recognition_ready=full_ready
    def accepted(*_):
        selected[0]=True
        elapsed=(time.perf_counter()-clicked[0])*1000
        print(f'Selection ready: {elapsed:.0f} ms after release; text={overlay.selection.text!r}; full scan pending={overlay.ocr_pending}',flush=True)
        if overlay.selection.text!=('東京で' if args.japanese else 'Circle'):failures.append('The priority scan did not select the expected text')
        if full_done[0]:app.quit()
    overlay.selected.connect(accepted)
    def click():
        clicked[0]=time.perf_counter()
        if args.japanese:
            QTest.mousePress(overlay,Qt.MouseButton.LeftButton,pos=QPoint(64,110))
            QTest.mouseMove(overlay,QPoint(98,110))
            QTest.mouseRelease(overlay,Qt.MouseButton.LeftButton,pos=QPoint(98,110))
        else:
            QTest.mouseClick(overlay,Qt.MouseButton.LeftButton,pos=QPoint(70,74))
    QTimer.singleShot(100,click)
    QTimer.singleShot(15000,app.quit)
    overlay.cancelled.connect(app.quit)
    app.exec()
    QThreadPool.globalInstance().waitForDone()
    if failures or not selected[0]:
        print(failures or ['Selection did not complete'],file=sys.stderr)
        return 1
    print('Native selection and background OCR passed using the local GPU service; synthetic images only.' if args.gpu else 'Native priority selection and background OCR passed; no capture or network requests.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
