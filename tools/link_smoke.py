"""Click a local result and verify system handoff plus CtS dismissal."""

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QObject,QPoint,QTimer,Qt,QUrl,Slot
from PySide6.QtGui import QDesktopServices,QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor

from circle_to_search.appearance import prepare_qt
from circle_to_search.app import Controller
from circle_to_search.ocr import Document
from circle_to_search.ui import SelectionOverlay


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=['normal','newtab','app'],default='normal')
    parser.add_argument('--real-opener',action='store_true',help='Actually open example.org with the system default handler')
    args=parser.parse_args()
    prepare_qt()
    app=QApplication([]);app.setApplicationName('circle-to-search-link-check')
    screen=app.primaryScreen()
    image=QImage(screen.size(),QImage.Format.Format_RGB32);image.fill(Qt.white)
    overlay=SelectionOverlay(image,screen,document=Document([]),start_ocr=False,auto_search=False)
    controller=Controller(app,None);controller.overlays=[overlay]
    overlay.externalRequested.connect(controller.open_external)
    overlay.cancelled.connect(controller.quit)
    overlay.show_overlay()
    requests=[];attempts=[];failures=[];clicked=[False];completed=[False]
    class Recorder(QObject):
        @Slot(QUrl)
        def record(self,url):requests.append(url.toString())
    recorder=Recorder()
    if not args.real_opener:
        for scheme in ['https','ctstest']:QDesktopServices.setUrlHandler(scheme,recorder,'record')
    target='ctstest://example/result' if args.case=='app' else 'https://example.org/'
    sheet=overlay.sheet;sheet.bar.query.setText('Link test');sheet.loading();sheet.ensure_browser()
    class Offline(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self,info):
            if info.requestUrl().scheme() in ('http','https'):info.block(True)
    offline=Offline(sheet.browser)
    sheet.browser.profile.setUrlRequestInterceptor(offline)
    def click():
        if clicked[0]:return
        def located(raw):
            if clicked[0]:return
            if not raw:
                failures.append('The local result link did not render');app.quit();return
            position=json.loads(raw)
            clicked[0]=True
            point=sheet.browser.mapTo(overlay,QPoint(round(position['x']),round(position['y'])))
            QTest.mouseClick(overlay.windowHandle(),Qt.LeftButton,pos=point)
        sheet.browser.page().runJavaScript("""(()=>{const e=document.getElementById('result');if(!e)return null;const r=e.getBoundingClientRect();return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2})})()""",located)
    def loaded(ok):
        if ok:QTimer.singleShot(250,click)
    sheet.browser.loadFinished.connect(loaded)
    target_attribute='target="_blank"' if args.case=='newtab' else ''
    sheet.browser.setHtml(f'<body style="margin:24px;background:white"><a id="result" {target_attribute} href="{target}">Open result</a></body>',QUrl('https://www.google.com/search?hl=en'))
    def closing():
        completed[0]=controller.closing and not overlay.isVisible()
    app.aboutToQuit.connect(closing)
    QTimer.singleShot(8000,app.quit)
    original=QDesktopServices.openUrl
    def opened(url):
        attempts.append(url.toString())
        if args.real_opener:requests.append(url.toString())
        return original(url)
    with patch('circle_to_search.app.QDesktopServices.openUrl',side_effect=opened):app.exec()
    if not args.real_opener:
        for scheme in ['https','ctstest']:QDesktopServices.unsetUrlHandler(scheme)
    if requests!=[target] or attempts!=[target] or not completed[0]:failures.append(f'Expected one handoff and a dismissed overlay; attempts={attempts}, requests={requests}, dismissed={completed[0]}')
    if failures:
        print(failures,file=sys.stderr)
        return 1
    print(f'{args.case} link: system opener called once; CtS completed dismissal.'+(' Real default handler requested.' if args.real_opener else ' Desktop handler intercepted; no network requests.'))
    return 0


if __name__=='__main__':raise SystemExit(main())
