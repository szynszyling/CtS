"""Compare Google's public search route with the rejected side-panel route."""

import json
import os
import sys
import argparse
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QCoreApplication,QTimer,Qt,QUrl
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from circle_to_search.ocr import Document
from circle_to_search.ui import SelectionOverlay


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fresh-profile',action='store_true',help='Compare with an unmodified, temporary Qt browser profile')
    parser.add_argument('--app-preferences',action='store_true',help='Include the app\'s English/light and side-panel parameters')
    parser.add_argument('--plain',action='store_true',help='Use only the public query and language parameters')
    parser.add_argument('--light',action='store_true',help='Use public search with only the language and color-scheme hints')
    parser.add_argument('--preferences',action='store_true',help='Inspect Google\'s normal appearance settings instead of searching')
    parser.add_argument('--offline-layout',action='store_true',help='Inspect saved HTML with all network requests blocked')
    args=parser.parse_args()
    if args.offline_layout:
        from circle_to_search.appearance import prepare_qt
        prepare_qt()
    else:
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app=QApplication([])
    app.setApplicationName("circle-to-search")
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    screen=app.primaryScreen()
    image=QImage(screen.size(),QImage.Format.Format_RGB32);image.fill(Qt.GlobalColor.white)
    parent=SelectionOverlay(image,screen,document=Document([]),start_ocr=False,auto_search=False)
    parent.cancelled.connect(app.quit)
    parent.show_overlay()
    sheet=parent.sheet
    sheet.loading("Checking the public search route…")
    sheet.ensure_browser()
    browser=sheet.browser
    if args.fresh_profile:
        from PySide6.QtWebEngineCore import QWebEnginePage,QWebEngineProfile
        profile=QWebEngineProfile(browser)
        page=QWebEnginePage(profile,browser)
        profile.setParent(page)
        browser.setPage(page)
        print('Fresh Qt profile; default user agent:',profile.httpUserAgent(),flush=True)
        browser.cookie_ready=True
    browser.loadFinished.disconnect(sheet.loaded)
    statuses=[]
    browser.page().loadingChanged.connect(lambda info:statuses.append(info.errorCode()))
    def loaded(ok):
        if args.offline_layout:
            from circle_to_search.web_scripts import SEARCH_CHROME
            def inspect():
                browser.page().runJavaScript("""JSON.stringify(['main','cnt','top_nav','hdtb','appbar','rcnt','center_col','search','rso'].map(id=>{
                    const e=document.getElementById(id);if(!e)return{id};const s=getComputedStyle(e),r=e.getBoundingClientRect();
                    return{id,top:r.top,height:r.height,margin:s.margin,padding:s.padding,position:s.position,display:s.display,
                    children:[...e.children].slice(0,8).map(c=>({id:c.id,cls:c.className,top:c.getBoundingClientRect().top,height:c.getBoundingClientRect().height}))};
                }))""",lambda data:(print(data,flush=True),app.quit()))
            browser.page().runJavaScript(SEARCH_CHROME,lambda _:QTimer.singleShot(150,inspect))
            return
        def saved(html):
            output=Path('/tmp/cts-preferences.html' if args.preferences else '/tmp/cts-public-search.html')
            output.write_text(html);output.chmod(0o600)
            browser.page().runJavaScript("JSON.stringify({background:document.body?getComputedStyle(document.body).backgroundColor:'none',lang:document.documentElement.lang,darkMedia:matchMedia('(prefers-color-scheme:dark)').matches})",lambda data:(print('Public page:',ok,'HTTP status:',statuses,'appearance:',data,flush=True),app.quit()))
        browser.page().toHtml(saved)
    browser.loadFinished.connect(lambda ok:QTimer.singleShot(400,lambda:loaded(ok)))
    url="https://www.google.com/search?q=translate&hl=en" if args.fresh_profile or args.plain or args.light else "https://www.google.com/search?q=translate&hl=en&gl=us&lr=lang_en&cs=0"
    if args.light:
        url+='&cs=0'
    if args.app_preferences:
        from circle_to_search.search import english_light_url
        url=english_light_url(url)
    if args.preferences:
        url='https://www.google.com/preferences?hl=en#appearance'
    if args.offline_layout:
        import re
        from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor
        class Offline(QWebEngineUrlRequestInterceptor):
            def interceptRequest(self,info):
                if info.requestUrl().scheme() in ('http','https'):info.block(True)
        interceptor=Offline(browser)
        browser.profile.setUrlRequestInterceptor(interceptor)
        html=re.sub(r'<script\b[^>]*>.*?</script>','',Path('/tmp/cts-public-search.html').read_text(),flags=re.S|re.I)
        browser.setHtml(html,QUrl('https://www.google.com/search?hl=en'))
    else:
        browser.load(QUrl(url))
    QTimer.singleShot(20000,app.quit)
    app.exec()


if __name__=="__main__":
    main()
