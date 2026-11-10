"""Exercise OCR settings through the real Wayland overlay and pointer routing.

Uses synthetic content/local HTML only. Settings writes are intercepted.
"""

import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint,QSettings,QTimer,Qt
from PySide6.QtGui import QColor,QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QMenu

from circle_to_search.appearance import prepare_qt,ThemeManager
from circle_to_search.ocr import Document
from circle_to_search.ocr_backend import OcrConfig,configure_ocr,current_config
from circle_to_search.ui import SelectionOverlay


def main():
    temporary=tempfile.TemporaryDirectory(prefix='cts-settings-check-')
    os.environ['XDG_DATA_HOME']=temporary.name+'/data'
    os.environ['XDG_CACHE_HOME']=temporary.name+'/cache'
    prepare_qt()
    app=QApplication([])
    app.setApplicationName('circle-to-search-settings-check')
    ThemeManager(app,mode='dark',settings=QSettings(temporary.name+'/appearance.ini',QSettings.IniFormat),watch=False)
    configure_ocr(OcrConfig())
    screen=app.primaryScreen()
    image=QImage(screen.size(),QImage.Format_RGB32);image.fill(QColor('#334455'))
    overlay=SelectionOverlay(image,screen,document=Document([]),start_ocr=False,auto_search=False)
    overlay.show_overlay()
    overlay.dismissed.connect(app.quit)
    failures=[];changed=[];cancelled=[];completed=[False]
    overlay.ocrSettingsChanged.connect(lambda:changed.append(True))
    overlay.cancelled.connect(lambda:cancelled.append(True))
    window=overlay.windowHandle()
    sheet=overlay.sheet
    sheet.expanded=True;sheet.sheet_height=overlay.height()-84
    sheet.loading();sheet.ensure_browser()
    sheet.browser.setHtml('<body style="background:#22242a"><div style="position:fixed;inset:0;background:#24a35a">Accelerated browser behind settings</div></body>')

    def check(function):
        def run():
            try:function()
            except Exception as error:
                failures.append(str(error))
                modal=app.activeModalWidget()
                if modal:modal.reject()
                overlay.hide()
                app.exit(1)
        return run

    def click(control):
        point=control.mapTo(overlay,control.rect().center())
        QTest.mouseClick(window,Qt.LeftButton,pos=point)

    def open_menu():
        click(overlay.more_button)
        QTimer.singleShot(100,check(choose_settings))

    def choose_settings():
        menu=app.activePopupWidget()
        assert isinstance(menu,QMenu),'The three-dot menu did not open'
        action=next(a for a in menu.actions() if a.text()=='Text recognition…')
        QTest.mouseClick(menu.windowHandle(),Qt.LeftButton,pos=menu.actionGeometry(action).center())
        QTimer.singleShot(150,check(ready))

    def ready():
        panel=overlay.ocr_settings_panel
        assert panel is not None and panel.isVisible(),'The settings panel is not visible'
        dialog=panel.dialog
        assert not dialog.isWindow() and dialog.window() is overlay,'Settings became a separate desktop window'
        assert app.activeModalWidget() is None,'A hidden modal window grabbed application input'
        assert overlay.isEnabled(),'The overlay was disabled by settings'
        assert overlay.size()==screen.size(),'Settings resized the fullscreen overlay'
        # The panel stays above an actually accelerated browser, including
        # subsequent sheet presentations while it is open.
        sheet.show_sheet(False)
        point=dialog.mapTo(overlay,QPoint(12,10))
        widget=overlay.childAt(point)
        assert widget is not None and panel.isAncestorOf(widget),'The results browser covers settings'
        QTest.mouseClick(window,Qt.LeftButton,pos=QPoint(80,320))
        assert overlay.selection is None,'Settings passed a click through to the selection canvas'
        click(dialog.backend)
        QTimer.singleShot(100,check(change_backend))

    def change_backend():
        popup=app.activePopupWidget()
        assert popup is not None,'The backend selector did not open'
        QTest.keyClick(popup.windowHandle(),Qt.Key_Home)
        QTest.keyClick(popup.windowHandle(),Qt.Key_Down)
        QTest.keyClick(popup.windowHandle(),Qt.Key_Return)
        QTimer.singleShot(100,check(edit_url))

    def edit_url():
        dialog=overlay.ocr_settings_panel.dialog
        assert dialog.backend.currentData()=='server','The backend selector did not accept keyboard input'
        assert dialog.url.isEnabled(),'The server URL field stayed disabled'
        click(dialog.url)
        QTest.keyClick(window,Qt.Key_A,Qt.ControlModifier)
        QTest.keyClick(window,Qt.Key_X)
        assert dialog.url.text()=='x','Native keyboard input did not reach the settings field'
        overlay.grab().save('/tmp/cts-ocr-settings-native.png')
        QTest.keyClick(window,Qt.Key_Escape)
        QTimer.singleShot(100,check(cancelled_settings))

    def cancelled_settings():
        assert overlay.ocr_settings_panel is None,'Escape did not dismiss settings'
        assert not cancelled,'Escape closed CtS instead of just settings'
        assert not changed,'Cancelling changed the OCR backend'
        assert current_config().backend=='local','Cancelling persisted the edited backend'
        overlay.edit_ocr_settings()
        QTimer.singleShot(100,check(save_settings))

    def save_settings():
        dialog=overlay.ocr_settings_panel.dialog
        dialog.backend.setCurrentIndex(dialog.backend.findData('server'))
        dialog.url.setText('http://test-server:8766')
        click(dialog.buttons.button(QDialogButtonBox.Save))
        QTimer.singleShot(100,check(saved_settings))

    def saved_settings():
        assert overlay.ocr_settings_panel is None,'Save did not dismiss settings'
        assert changed==[True] and current_config().backend=='server','Saving did not notify CtS of the backend change'
        assert app.activeModalWidget() is None and overlay.isEnabled(),'Settings left input blocked'
        QTest.mouseClick(window,Qt.LeftButton,pos=QPoint(80,320))
        assert overlay.selection is not None,'The desktop canvas remained blocked after settings closed'
        completed[0]=True
        overlay.dismiss()

    QTimer.singleShot(650,check(open_menu))
    def timed_out():
        failures.append('The native settings check timed out')
        overlay.hide()
        app.exit(1)
    QTimer.singleShot(12000,timed_out)
    with patch.object(OcrConfig,'save'):
        app.exec()
    overlay.hide()
    temporary.cleanup()
    if failures or not completed[0]:
        print(failures or ['The native settings check did not complete'],file=sys.stderr)
        return 1
    print('Native menu, embedded settings over WebEngine, selector/text input, Escape, Save and restored input passed. No screen capture, network requests or settings writes.')
    return 0


if __name__=='__main__':raise SystemExit(main())
