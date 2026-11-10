"""Inspect AI Mode once using synthetic input and the app's Google session."""

import json
import tempfile
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QSettings,QTimer,Qt,QUrl
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEngineScript

from circle_to_search.appearance import prepare_qt,ThemeManager
from circle_to_search.ocr import Document
from circle_to_search.search import search_tab_url
from circle_to_search.ui import SelectionOverlay


def main():
    prepare_qt()
    app=QApplication([]);app.setApplicationName('circle-to-search')
    temporary=tempfile.TemporaryDirectory(prefix='cts-ai-theme-')
    appearance=ThemeManager(app,mode='dark' if '--dark' in sys.argv else 'light',settings=QSettings(str(Path(temporary.name)/'appearance.ini'),QSettings.IniFormat))
    screen=app.primaryScreen()
    image=QImage(screen.size(),QImage.Format.Format_RGB32);image.fill(Qt.GlobalColor.white)
    overlay=SelectionOverlay(image,screen,document=Document([]),start_ocr=False,auto_search=False)
    overlay.show_overlay();overlay.cancelled.connect(app.quit)
    sheet=overlay.sheet;sheet.bar.query.setText('What is KDE Konsole?')
    sheet.ensure_browser()
    script=QWebEngineScript();script.setInjectionPoint(QWebEngineScript.DocumentCreation)
    script.setWorldId(QWebEngineScript.MainWorld)
    script.setSourceCode("window.__ctsErrors=[];addEventListener('error',e=>__ctsErrors.push(e.message));addEventListener('unhandledrejection',e=>__ctsErrors.push(String(e.reason)));")
    sheet.browser.page().scripts().insert(script)
    output=Path('/tmp/cts-ai-check');output.mkdir(exist_ok=True)
    failures=[]
    def inspect():
        def report(raw):
            print('AI page:',raw,flush=True)
            data=json.loads(raw)
            if data.get('dark')!=appearance.theme.dark:failures.append('AI Mode did not use the selected theme')
            if len(data.get('text',''))<200 or 'terminal' not in data.get('text','').lower():
                failures.append('AI Mode did not expose its answer')
            sheet.browser.page().toHtml(lambda html:(output/'page.html').write_text(html))
            sheet.grab().save(str(output/'page.png'))
            def compared(data):
                print('Header-style comparison:',data,flush=True)
                sheet.grab().save(str(output/'without-cleanup.png'))
                QTimer.singleShot(100,app.quit)
            sheet.browser.page().runJavaScript("""JSON.stringify((()=>{
                const before=document.body.innerText;
                for(const s of document.querySelectorAll('style'))if(s.id==='cts-search-chrome')s.disabled=true;
                return{before:before.slice(0,1600),after:document.body.innerText.slice(0,3000)};
            })())""",compared)
        sheet.browser.page().runJavaScript("""JSON.stringify({background:getComputedStyle(document.body).backgroundColor,dark:matchMedia('(prefers-color-scheme:dark)').matches,url:location.pathname,lang:document.documentElement.lang,text:document.body.innerText.slice(0,3000),errors:window.__ctsErrors,
            main:[...document.querySelectorAll('#main,#rcnt,[role="main"]')].map(e=>({id:e.id,role:e.getAttribute('role'),height:e.getBoundingClientRect().height,text:e.innerText.slice(0,1000)}))})""",report)
    sheet.browser.page().loadingChanged.connect(lambda info:print('HTTP:',info.errorCode(),info.errorString(),flush=True) if info.errorCode() else None)
    sheet.loading('Checking AI Mode…')
    sheet.load_url(search_tab_url('','ai','What is KDE Konsole?'))
    QTimer.singleShot(20000,inspect)
    QTimer.singleShot(25000,app.quit)
    app.exec()
    for path in output.iterdir():path.chmod(0o600)
    if failures:raise RuntimeError('; '.join(failures))
    print('AI Mode answer is visible inside the existing results sheet.')


if __name__=='__main__':main()
