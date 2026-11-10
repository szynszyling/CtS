import math
import unittest
from urllib.parse import parse_qs,urlsplit
from unittest.mock import patch

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QThreadPool,QUrl,Signal
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from circle_to_search.ocr import Document, Glyph
from circle_to_search.ui import SelectionOverlay

APP = QApplication.instance() or QApplication([])


class FakeBrowser(QWidget):
    loadFinished = Signal(bool)
    loadingChanged = Signal(object)
    externalRequested=Signal(QUrl)

    def load(self, url):
        self.url = url
        self.loadFinished.emit(True)

    def stop(self):
        pass

    def page(self):
        return self

    def upload_image(self,png,query=""):
        self.uploaded_png=png
        self.uploaded_query=query


class DelayedBrowser(FakeBrowser):
    loadStarted=Signal()

    def __init__(self,parent):
        super().__init__(parent)
        self.probes=[]

    def load(self,url):
        self.url=url
        self.loadStarted.emit()

    def runJavaScript(self,script,callback):
        self.probes.append(callback)


def english_document():
    glyphs = []
    x = 200
    for word_id, word in enumerate(["Circle", "these", "words"]):
        for c in word:
            glyphs.append(Glyph(c, QRectF(x, 200, 12, 24), "line", str(word_id)))
            x += 13
        x += 12
    return Document(glyphs)


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.image = QImage(800, 600, QImage.Format.Format_RGB32)
        self.image.fill(QColor("#ff0000"))
        painter = QPainter(self.image)
        painter.fillRect(200, 200, 100, 100, QColor("#00ff00"))
        painter.end()
        self.overlay = SelectionOverlay(self.image, APP.primaryScreen(), document=Document([]), start_ocr=False,
                                        auto_search=False, browser_factory=FakeBrowser)
        self.overlay.resize(800, 600)
        self.overlay.show()
        APP.processEvents()
        self.selections = []
        self.overlay.selected.connect(lambda crop, rect: self.selections.append((crop, rect)))

    def tearDown(self):
        APP.processEvents()
        QThreadPool.globalInstance().waitForDone()
        APP.processEvents()
        self.overlay.hide()
        self.overlay.deleteLater()
        APP.processEvents()

    def test_ocr_settings_are_clickable_children_of_the_overlay(self):
        cancelled=[]
        self.overlay.cancelled.connect(lambda:cancelled.append(True))
        self.overlay.edit_ocr_settings()
        APP.processEvents()
        panel=self.overlay.ocr_settings_panel
        dialog=panel.dialog
        self.assertFalse(dialog.isWindow())
        self.assertIs(dialog.window(),self.overlay)
        self.assertIsNone(APP.activeModalWidget())
        self.assertTrue(self.overlay.isEnabled())
        self.assertFalse(self.overlay.search_shortcut.isEnabled())
        dialog.backend.setCurrentIndex(dialog.backend.findData('server'))
        self.assertTrue(dialog.url.isEnabled())
        QTest.mouseClick(self.overlay,Qt.LeftButton,pos=QPoint(80,350))
        self.assertIsNone(self.overlay.selection)
        self.overlay.back()
        APP.processEvents()
        self.assertIsNone(self.overlay.ocr_settings_panel)
        self.assertEqual(cancelled,[])
        self.assertTrue(self.overlay.search_shortcut.isEnabled())
        QTest.mouseClick(self.overlay,Qt.LeftButton,pos=QPoint(80,350))
        self.assertIsNotNone(self.overlay.selection)

    def test_saving_embedded_ocr_settings_emits_the_backend_change(self):
        from circle_to_search.ocr_backend import OcrConfig,configure_ocr,current_config
        previous=current_config()
        changed=[]
        self.overlay.ocrSettingsChanged.connect(lambda:changed.append(True))
        self.overlay.edit_ocr_settings()
        APP.processEvents()
        dialog=self.overlay.ocr_settings_panel.dialog
        dialog.backend.setCurrentIndex(dialog.backend.findData('server'))
        dialog.url.setText('http://test-server:8766')
        try:
            with patch.object(OcrConfig,'save'):dialog.save_settings()
            APP.processEvents()
            self.assertIsNone(self.overlay.ocr_settings_panel)
            self.assertEqual(changed,[True])
            self.assertIsNone(APP.activeModalWidget())
        finally:configure_ocr(previous)

    def drag(self, start, end, shift=False):
        mods = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
        QTest.mousePress(self.overlay, Qt.MouseButton.LeftButton, mods, QPoint(*start))
        QTest.mouseMove(self.overlay, QPoint(*end))
        QTest.mouseRelease(self.overlay, Qt.MouseButton.LeftButton, mods, QPoint(*end))

    def drag_control(self,control,dx,dy=0):
        point=control.rect().center()
        destination=control.mapToGlobal(point)+QPoint(dx,dy)
        QTest.mousePress(control,Qt.LeftButton,pos=point)
        QTest.mouseMove(control,control.mapFromGlobal(destination))
        QTest.mouseRelease(control,Qt.LeftButton,pos=control.mapFromGlobal(destination))

    def test_theme_change_preserves_verification_and_does_not_reload_hidden_results(self):
        from circle_to_search.appearance import DARK,LIGHT
        sheet=self.overlay.sheet
        sheet.load_url('https://www.google.com/search?q=test')
        QTest.qWait(260)
        sheet.browser.apply_theme=lambda theme:None
        sheet.browser.reloads=0
        def reload():sheet.browser.reloads+=1
        sheet.browser.reload=reload
        sheet.browser.url=lambda:QUrl('https://www.google.com/search?q=test')
        sheet.show_http_status(429)
        sheet.cover_theme_change(DARK)
        sheet.apply_theme(DARK)
        self.assertIs(sheet.content.currentWidget(),sheet.browser)
        self.assertTrue(sheet.verification.isVisible())
        self.assertEqual(sheet.browser.reloads,0)
        sheet.verification.hide()
        sheet.hide()
        sheet.cover_theme_change(LIGHT)
        sheet.apply_theme(LIGHT)
        self.assertEqual(sheet.browser.reloads,0)

    def test_theme_change_during_navigation_reloads_after_the_old_request_finishes(self):
        from circle_to_search.appearance import DARK
        sheet=self.overlay.sheet
        sheet.browser_factory=DelayedBrowser
        sheet.load_url('https://www.google.com/search?q=test')
        sheet.browser.url=lambda:QUrl('https://www.google.com/search?q=test')
        reloads=[]
        sheet.browser.reload=lambda:reloads.append(True)
        sheet.cover_theme_change(DARK)
        sheet.apply_theme(DARK)
        self.assertTrue(sheet.theme_reload_pending)
        self.assertEqual(reloads,[])
        sheet.loaded(True)
        self.assertEqual(reloads,[True])
        self.assertFalse(sheet.theme_reload_pending)

    def test_floating_search_bar_can_move_without_selecting_the_desktop(self):
        self.overlay.resize(1600,900)
        APP.processEvents()
        bar=self.overlay.bar
        previous=bar.geometry()
        self.drag_control(bar.logo,-300,-100)
        self.assertEqual(bar.x(),previous.x()-300)
        self.assertEqual(bar.y(),previous.y()-100)
        self.assertIsNone(self.overlay.selection)
        self.overlay.resizeEvent(None)
        self.assertEqual(bar.x(),previous.x()-300)
        self.assertEqual(bar.y(),previous.y()-100)
        # A formerly covered point becomes selectable immediately.
        point=QPoint(previous.right()-4,previous.center().y())
        self.assertFalse(bar.geometry().contains(point))
        QTest.mouseClick(self.overlay,Qt.LeftButton,pos=point)
        self.assertIsNotNone(self.overlay.selection)

    def test_dragging_the_results_search_bar_moves_the_whole_sheet_and_keeps_its_position(self):
        self.overlay.resize(1600,900)
        sheet=self.overlay.sheet
        sheet.load_url('https://www.google.com/search?q=first')
        QTest.qWait(260)
        previous=sheet.geometry()
        self.drag_control(sheet.bar.logo,-250)
        self.assertEqual(sheet.x(),previous.x()-250)
        self.assertEqual(sheet.y(),previous.y())
        self.assertIsNone(self.overlay.selection)
        sheet.load_url('https://www.google.com/search?q=second')
        sheet.toggle()
        QTest.qWait(260)
        self.assertEqual(sheet.x(),previous.x()-250)

    def test_results_handle_supports_straight_sideways_motion_and_vertical_resizing(self):
        self.overlay.resize(1600,900)
        sheet=self.overlay.sheet
        sheet.loading()
        QTest.qWait(260)
        height=sheet.height()
        left=sheet.x()
        self.drag_control(sheet.handle,120)
        self.assertEqual(sheet.x(),left+120)
        self.assertEqual(sheet.height(),height)
        self.drag_control(sheet.handle,0,-70)
        self.assertEqual(sheet.x(),left+120)
        self.assertEqual(sheet.height(),height+70)

    def test_results_handle_can_move_and_expand_in_one_diagonal_drag(self):
        self.overlay.resize(1600,900)
        sheet=self.overlay.sheet
        sheet.loading()
        QTest.qWait(260)
        before=sheet.geometry()
        self.drag_control(sheet.handle,120,-70)
        self.assertEqual(sheet.x(),before.x()+120)
        self.assertEqual(sheet.height(),before.height()+70)
        self.assertEqual(sheet.geometry().bottom(),before.bottom())

    def test_results_handle_can_change_direction_without_releasing(self):
        self.overlay.resize(1600,900)
        sheet=self.overlay.sheet
        sheet.loading()
        QTest.qWait(260)
        before=sheet.geometry()
        handle=sheet.handle
        point=handle.rect().center()
        origin=handle.mapToGlobal(point)
        QTest.mousePress(handle,Qt.LeftButton,pos=point)
        QTest.mouseMove(handle,handle.mapFromGlobal(origin+QPoint(80,0)))
        QTest.mouseMove(handle,handle.mapFromGlobal(origin+QPoint(80,-60)))
        QTest.mouseRelease(handle,Qt.LeftButton,pos=handle.mapFromGlobal(origin+QPoint(80,-60)))
        self.assertEqual(sheet.x(),before.x()+80)
        self.assertEqual(sheet.height(),before.height()+60)

    def test_results_logo_can_move_and_shrink_together(self):
        self.overlay.resize(1600,900)
        sheet=self.overlay.sheet
        sheet.loading()
        QTest.qWait(260)
        before=sheet.geometry()
        self.drag_control(sheet.bar.logo,-100,45)
        self.assertEqual(sheet.x(),before.x()-100)
        self.assertEqual(sheet.height(),before.height()-45)
        self.assertIsNone(self.overlay.selection)

    def test_search_bar_drag_stays_on_screen(self):
        self.drag_control(self.overlay.bar.logo,-2000,-2000)
        self.assertEqual(self.overlay.bar.x(),24)
        self.assertEqual(self.overlay.bar.y(),84)
        self.drag_control(self.overlay.bar.logo,4000,4000)
        self.assertEqual(self.overlay.bar.geometry().right(),self.overlay.width()-25)
        self.assertEqual(self.overlay.bar.geometry().bottom(),self.overlay.height()-25)

    def test_query_text_selection_does_not_drag_the_results_sheet(self):
        sheet=self.overlay.sheet
        sheet.load_url('https://www.google.com/search?q=test')
        QTest.qWait(260)
        sheet.bar.query.setText('select these words')
        position=sheet.pos()
        QTest.mousePress(sheet.bar.query,Qt.LeftButton,pos=QPoint(3,15))
        QTest.mouseMove(sheet.bar.query,QPoint(65,15))
        QTest.mouseRelease(sheet.bar.query,Qt.LeftButton,pos=QPoint(65,15))
        self.assertTrue(sheet.bar.query.selectedText())
        self.assertEqual(sheet.pos(),position)
        self.assertIsNone(self.overlay.selection)

    def test_loading_page_mouse_events_never_reach_desktop_selection(self):
        sheet=self.overlay.sheet
        sheet.loading()
        QTest.qWait(260)
        control=sheet.message_page
        point=control.rect().center()
        QTest.mousePress(control,Qt.LeftButton,pos=point)
        QTest.mouseMove(control,point+QPoint(30,0))
        QTest.mouseRelease(control,Qt.LeftButton,pos=point+QPoint(30,0))
        self.assertIsNone(self.overlay.selection)
        self.assertFalse(self.overlay.dragging)
        self.assertTrue(sheet.isVisible())

    def test_opening_sheet_blocks_selection_in_its_destination_before_the_first_frame(self):
        sheet=self.overlay.sheet
        sheet.loading()
        point=sheet.target_geometry().center()
        generation=self.overlay.generation
        QTest.mouseClick(self.overlay,Qt.LeftButton,pos=point)
        self.assertEqual(self.overlay.generation,generation)
        self.assertIsNone(self.overlay.selection)
        self.assertFalse(self.overlay.dragging)

    def test_visible_dismissing_sheet_keeps_blocking_selection_until_hidden(self):
        sheet=self.overlay.sheet
        sheet.loading()
        QTest.qWait(260)
        point=sheet.geometry().topLeft()+QPoint(35,140)
        sheet.stop(animate=True)
        QTest.mouseClick(self.overlay,Qt.LeftButton,pos=point)
        self.assertIsNone(self.overlay.selection)
        QTest.qWait(220)
        QTest.mouseClick(self.overlay,Qt.LeftButton,pos=point)
        self.assertIsNotNone(self.overlay.selection)

    def test_box_crop_contains_only_selected_pixels_and_stays_on_screen(self):
        self.drag((200, 200), (300, 300), shift=True)
        self.assertEqual(len(self.selections), 1)
        crop, _ = self.selections[0]
        self.assertEqual((crop.width(), crop.height()), (100, 100))
        self.assertEqual(crop.pixelColor(0, 0), QColor("#00ff00"))
        self.assertEqual(crop.pixelColor(99, 99), QColor("#00ff00"))
        self.assertTrue(self.overlay.isVisible())
        self.assertTrue(self.overlay.sheet.isVisible())

    def test_circle_gesture_keeps_bounding_crop(self):
        QTest.mousePress(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(300, 250))
        for i in range(1, 33):
            angle = i * math.tau / 32
            QTest.mouseMove(self.overlay, QPoint(round(250 + 50 * math.cos(angle)), round(250 + 50 * math.sin(angle))))
        QTest.mouseRelease(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(300, 250))
        crop, _ = self.selections[0]
        self.assertEqual((crop.width(), crop.height()), (100, 100))

    def test_perfectly_horizontal_line_selects_text(self):
        self.overlay.document = english_document()
        self.drag((205, 211), (355, 211))
        self.assertEqual(self.overlay.selection.kind, "text")
        self.assertEqual(self.overlay.selection.text, "Circle these")
        self.assertTrue(self.overlay.text_actions.isVisible())

    def test_tap_selects_word(self):
        self.overlay.document = english_document()
        QTest.mouseClick(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(220, 211))
        self.assertEqual(self.overlay.selection.text, "Circle")

    def test_tap_on_image_creates_movable_crop(self):
        QTest.mouseClick(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(400, 200))
        self.assertEqual(self.overlay.selection.kind, "image")
        self.assertEqual(self.overlay.selection.bounds, QRectF(300, 100, 200, 200))

    @patch("circle_to_search.ui.SelectionOverlay.run_task")
    def test_full_scan_can_finish_before_the_priority_region(self,run_task):
        self.overlay.ocr_pending = True
        self.drag((205, 211), (355, 211))
        self.assertIsNone(self.overlay.selection)
        self.assertIsNotNone(self.overlay.pending_gesture)
        self.overlay.recognition_ready(english_document(), self.overlay.ocr_generation)
        self.assertEqual(self.overlay.selection.text, "Circle these")

    @patch("circle_to_search.ui.SelectionOverlay.run_task")
    def test_priority_region_selects_without_waiting_for_full_scan(self,run_task):
        self.overlay.ocr_pending=True
        self.drag((205,211),(355,211))
        function,args,ready,failed=run_task.call_args.args
        crop=args[0]
        self.assertLess(crop.width()*crop.height(),self.image.width()*self.image.height()/3)
        # The cropped OCR coordinates must be translated back to the desktop.
        origin=QPointF(45,147)
        region=Document([Glyph(g.text,g.rect.translated(-origin),g.line,g.word) for g in english_document().glyphs])
        ready(region)
        self.assertEqual(self.overlay.selection.text,"Circle these")
        self.assertTrue(self.overlay.ocr_pending)
        self.assertEqual(self.overlay.selection.bounds,english_document().bounds(range(11)))

    @patch("circle_to_search.ui.SelectionOverlay.run_task")
    def test_late_region_cannot_restore_a_cleared_selection(self,run_task):
        self.overlay.ocr_pending=True
        self.drag((205,211),(355,211))
        ready=run_task.call_args.args[2]
        self.overlay.clear_selection()
        ready(english_document())
        self.assertIsNone(self.overlay.selection)

    @patch("circle_to_search.ui.SelectionOverlay.run_task")
    def test_background_result_preserves_regional_selection_and_extends_handles(self,run_task):
        self.overlay.ocr_pending=True
        self.drag((205,211),(355,211))
        ready=run_task.call_args.args[2]
        origin=QPointF(45,147)
        partial=Document([Glyph(g.text,g.rect.translated(-origin),g.line,g.word) for g in english_document().glyphs[:11]])
        ready(partial)
        self.overlay.recognition_ready(english_document(),self.overlay.ocr_generation)
        self.assertEqual(self.overlay.selection.text,"Circle these")
        self.assertEqual(len(self.overlay.document.glyphs),16)
        self.assertFalse(self.overlay.document_is_regional)
        end=self.overlay.text_handle_positions()[1].toPoint()
        self.drag((end.x(),end.y()),(440,211))
        self.assertEqual(self.overlay.selection.text,"Circle these words")

    @patch("circle_to_search.ui.SelectionOverlay.run_task")
    def test_background_failure_cannot_erase_a_successful_regional_selection(self,run_task):
        self.overlay.ocr_pending=True
        self.drag((205,211),(355,211))
        ready=run_task.call_args.args[2]
        origin=QPointF(45,147)
        ready(Document([Glyph(g.text,g.rect.translated(-origin),g.line,g.word) for g in english_document().glyphs]))
        self.overlay.recognition_failed("Full scan timed out",self.overlay.ocr_generation)
        self.assertEqual(self.overlay.selection.text,"Circle these")
        self.assertEqual(self.overlay.document.text(),"Circle these words")

    @patch("circle_to_search.ui.SelectionOverlay.run_task")
    def test_late_region_cannot_replace_a_full_scan_selection(self,run_task):
        self.overlay.ocr_pending=True
        self.drag((205,211),(355,211))
        ready=run_task.call_args.args[2]
        self.overlay.recognition_ready(english_document(),self.overlay.ocr_generation)
        ready(Document([]))
        self.assertEqual(self.overlay.selection.text,"Circle these")

    @patch("circle_to_search.ui.SelectionOverlay.run_task")
    def test_empty_region_waits_for_full_recognition_before_choosing_image_search(self,run_task):
        self.overlay.ocr_pending=True
        self.drag((205,211),(355,211))
        ready=run_task.call_args.args[2]
        ready(Document([]))
        self.assertIsNone(self.overlay.selection)
        self.overlay.recognition_ready(english_document(),self.overlay.ocr_generation)
        self.assertEqual(self.overlay.selection.text,"Circle these")

    @patch("circle_to_search.ui.SelectionOverlay.run_task")
    def test_regional_coordinates_keep_fractional_display_scaling(self,run_task):
        self.overlay.image=self.image.scaled(1000,750)
        self.overlay.ocr_pending=True
        self.drag((205,211),(355,211))
        ready=run_task.call_args.args[2]
        # The outward-rounded crop starts at physical pixel (56,183).
        regional=Document([Glyph(g.text,QRectF(g.rect.x()*1.25-56,g.rect.y()*1.25-183,
                                              g.rect.width()*1.25,g.rect.height()*1.25),g.line,g.word)
                           for g in english_document().glyphs])
        ready(regional)
        self.assertEqual(self.overlay.selection.text,"Circle these")
        self.assertAlmostEqual(self.overlay.selection.bounds.left(),200)
        self.assertAlmostEqual(self.overlay.selection.bounds.top(),200)

    @patch("circle_to_search.ui.SelectionOverlay.run_task")
    def test_new_gesture_can_retry_region_after_background_timeout(self,run_task):
        self.overlay.recognition_enabled=True
        self.overlay.ocr_pending=False
        self.overlay.full_document=None
        self.drag((205,211),(355,211))
        self.assertEqual(run_task.call_count,1)
        self.assertIsNotNone(self.overlay.pending_gesture)

    def test_copy_selected_text(self):
        self.overlay.document = english_document()
        self.drag((205, 211), (355, 211))
        self.overlay.copy_text()
        self.assertEqual(APP.clipboard().text(), "Circle these")

    def test_text_popup_stays_opaque_above_results_and_after_expansion(self):
        self.overlay.document=Document([Glyph('Selection',QRectF(300,560,160,20),'line','word')])
        self.overlay.auto_search=True
        self.overlay.finish_gesture([QPointF(380,570)],False)
        self.overlay.sheet.browser.setStyleSheet('background:#ccffcc;')
        QTest.qWait(240)
        popup=self.overlay.text_actions
        def background():
            sample=popup.pos()+QPoint(8,popup.height()//2)
            return self.overlay.grab().toImage().pixelColor(sample)
        self.assertEqual(background(),QColor('white'))
        self.overlay.sheet.toggle()
        QTest.qWait(260)
        self.assertEqual(background(),QColor('white'))

    def test_popup_position_updates_do_not_restart_its_entrance_animation(self):
        self.overlay.document=english_document()
        self.drag((205,211),(355,211))
        popup=self.overlay.text_actions
        QTest.qWait(50)
        elapsed=popup._fade.animation.currentTime()
        self.overlay.position_text_actions()
        self.assertGreaterEqual(popup._fade.animation.currentTime(),elapsed)
        self.overlay.clear_selection()
        QTest.qWait(180)
        self.assertFalse(popup.isVisible())

    def test_popup_buttons_copy_and_translate_the_selected_text(self):
        self.overlay.document=english_document()
        self.drag((205,211),(355,211))
        self.overlay.text_actions.copy_button.click()
        self.assertEqual(APP.clipboard().text(),'Circle these')
        self.overlay.text_actions.translate_button.click()
        url=self.overlay.sheet.browser.url
        self.assertEqual(url.host(),'translate.google.com')
        self.assertEqual(parse_qs(urlsplit(url.toString()).query)['text'],['Circle these'])

    def test_text_handle_extends_selection(self):
        self.overlay.document = english_document()
        self.drag((205, 211), (265, 211))
        self.assertEqual(self.overlay.selection.text, "Circle")
        end = self.overlay.text_handle_positions()[1].toPoint()
        self.drag((end.x(), end.y()), (440, 211))
        self.assertEqual(self.overlay.selection.text, "Circle these words")

    def test_image_corner_resize_does_not_move_original_origin(self):
        self.drag((200, 200), (300, 300), shift=True)
        self.drag((300, 300), (350, 330))
        self.assertEqual(self.overlay.selection.bounds, QRectF(200, 200, 150, 130))

    def test_image_move_clamps_to_screen(self):
        self.drag((200, 200), (300, 300), shift=True)
        self.drag((250, 250), (900, 700))
        self.assertEqual(self.overlay.selection.bounds, QRectF(700, 500, 100, 100))

    def test_escape_clears_results_then_closes(self):
        cancelled = []
        self.overlay.cancelled.connect(lambda: cancelled.append(True))
        self.drag((200, 200), (300, 300), shift=True)
        QTest.keyClick(self.overlay, Qt.Key.Key_Escape)
        self.assertIsNone(self.overlay.selection)
        self.assertTrue(self.overlay.sheet.dismissing)
        self.assertEqual(cancelled, [])
        QTest.keyClick(self.overlay, Qt.Key.Key_Escape)
        self.assertEqual(cancelled, [True])
        QTest.qWait(220)
        self.assertFalse(self.overlay.sheet.isVisible())

    def test_right_click_closes(self):
        cancelled = []
        self.overlay.cancelled.connect(lambda: cancelled.append(True))
        QTest.mouseClick(self.overlay, Qt.MouseButton.RightButton, pos=QPoint(300, 250))
        self.assertEqual(cancelled, [True])

    @patch("circle_to_search.ui.upload_to_lens")
    def test_auto_text_search_uses_inline_results_without_image_upload(self, upload):
        self.overlay.auto_search = True
        self.overlay.document = english_document()
        self.drag((205, 211), (355, 211))
        browser = self.overlay.sheet.browser
        self.assertEqual(browser.url.host(), "www.google.com")
        self.assertIn("Circle+these", browser.url.toString())
        upload.assert_not_called()

    def test_manual_mode_selects_without_opening_web_content(self):
        self.overlay.document = english_document()
        self.drag((205, 211), (355, 211))
        self.assertIsNone(self.overlay.sheet.browser)
        self.assertEqual(self.overlay.sheet.current_url, "")

    def test_auto_image_search_sends_only_the_crop(self):
        self.overlay.auto_search=True
        self.drag((200,200),(300,300),shift=True)
        image=QImage.fromData(self.overlay.sheet.browser.uploaded_png)
        self.assertEqual((image.width(),image.height()),(100,100))
        self.assertEqual(image.pixelColor(50,50),QColor("#00ff00"))

    @patch("circle_to_search.ui.SelectionOverlay.run_task")
    def test_clearing_selection_ignores_an_old_upload_response(self, run_task):
        self.overlay.auto_search=True
        self.overlay.external=True
        self.drag((200,200),(300,300),shift=True)
        callback=run_task.call_args.args[2]
        self.overlay.clear_selection()
        callback("https://www.google.com/search?udm=26")
        QTest.qWait(220)
        self.assertFalse(self.overlay.sheet.isVisible())
        self.assertIsNone(self.overlay.sheet.browser)

    def test_empty_query_keeps_search_bar_visible(self):
        self.overlay.submit("")
        self.assertTrue(self.overlay.bar.isVisible())

    def test_new_search_cannot_open_previous_results_url(self):
        self.overlay.sheet.load_url("https://www.google.com/search?q=old")
        self.overlay.sheet.loading("Searching for something new…")
        self.assertEqual(self.overlay.sheet.current_url,"")
        self.assertFalse(self.overlay.sheet.external.isEnabled())

    def test_google_verification_response_stays_visible_and_interactive(self):
        from types import SimpleNamespace
        self.overlay.sheet.load_url("https://www.google.com/search?q=test")
        browser=self.overlay.sheet.browser
        browser.loadFinished.emit(False)
        self.overlay.sheet.loading_info(SimpleNamespace(errorCode=lambda:429))
        APP.processEvents()
        self.assertIs(self.overlay.sheet.content.currentWidget(),browser)
        self.assertTrue(self.overlay.sheet.verification.isVisible())
        self.assertTrue(self.overlay.sheet.isVisible())

    def test_successful_http_response_does_not_show_verification_prompt(self):
        from types import SimpleNamespace
        self.overlay.sheet.load_url("https://www.google.com/search?q=test")
        self.overlay.sheet.loading_info(SimpleNamespace(errorCode=lambda:200))
        self.assertFalse(self.overlay.sheet.verification.isVisible())

    def test_access_denied_is_not_presented_as_a_captcha(self):
        from types import SimpleNamespace
        sheet=self.overlay.sheet
        sheet.load_url("https://www.google.com/search?q=test")
        sheet.browser.loadFinished.emit(False)
        sheet.loading_info(SimpleNamespace(errorCode=lambda:403))
        APP.processEvents()
        self.assertIs(sheet.content.currentWidget(),sheet.message_page)
        self.assertIn("HTTP 403",sheet.message.text())
        self.assertFalse(sheet.verification.isVisible())
        self.assertTrue(sheet.fallback.isVisible())

    def test_loading_cover_waits_for_the_light_page(self):
        sheet=self.overlay.sheet
        sheet.browser_factory=DelayedBrowser
        sheet.loading()
        sheet.load_url("https://www.google.com/search?q=test")
        browser=sheet.browser
        browser.loadFinished.emit(True)
        self.assertIs(sheet.content.currentWidget(),sheet.message_page)
        browser.probes.pop()(False)
        QTest.qWait(70)
        self.assertIs(sheet.content.currentWidget(),sheet.message_page)
        browser.probes.pop()(True)
        QTest.qWait(70)
        self.assertIs(sheet.content.currentWidget(),browser)

    def test_new_tab_stays_covered_despite_an_old_page_ready_callback(self):
        sheet=self.overlay.sheet
        sheet.browser_factory=DelayedBrowser
        sheet.loading()
        sheet.load_url("https://www.google.com/search?q=test")
        browser=sheet.browser
        browser.loadFinished.emit(True)
        browser.probes.pop()(True)
        browser.loadStarted.emit()
        QTest.qWait(70)
        self.assertIs(sheet.content.currentWidget(),sheet.message_page)

    def test_results_expand_and_collapse(self):
        self.drag((200, 200), (300, 300), shift=True)
        height = self.overlay.sheet.target_geometry().height()
        self.overlay.sheet.toggle()
        QTest.qWait(260)
        self.assertGreater(self.overlay.sheet.height(), height)
        self.overlay.sheet.toggle()
        QTest.qWait(260)
        self.assertEqual(self.overlay.sheet.height(), height)

    def test_repeated_loading_does_not_snap_an_opening_sheet_to_its_destination(self):
        sheet=self.overlay.sheet
        sheet.loading()
        QTest.qWait(50)
        before=sheet.geometry()
        sheet.load_url('https://www.google.com/search?q=test')
        self.assertNotEqual(sheet.geometry(),sheet.target_geometry())
        self.assertEqual(sheet.geometry(),before)
        QTest.qWait(240)
        self.assertEqual(sheet.geometry(),sheet.target_geometry())

    def test_overlay_dismisses_in_place_and_emits_completion_once(self):
        completed=[]
        self.overlay.dismissed.connect(lambda:completed.append(True))
        bounds=self.overlay.geometry()
        self.overlay.dismiss()
        self.overlay.dismiss()
        QTest.qWait(80)
        self.assertEqual(self.overlay.geometry(),bounds)
        self.assertGreater(self.overlay.overlay_progress,0)
        self.assertLess(self.overlay.overlay_progress,1)
        QTest.qWait(160)
        self.assertFalse(self.overlay.isVisible())
        self.assertEqual(completed,[True])

    def test_a_new_search_can_interrupt_sheet_dismissal(self):
        sheet=self.overlay.sheet
        sheet.loading()
        QTest.qWait(260)
        sheet.stop(animate=True)
        QTest.qWait(60)
        sheet.loading()
        QTest.qWait(260)
        self.assertFalse(sheet.dismissing)
        self.assertTrue(sheet.isVisible())
        self.assertEqual(sheet.geometry(),sheet.target_geometry())

    def test_controller_waits_for_all_overlays_to_finish_closing(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from circle_to_search.app import Controller
        other=SelectionOverlay(self.image,APP.primaryScreen(),document=Document([]),start_ocr=False,
                               auto_search=False,browser_factory=FakeBrowser)
        other.show()
        quit_app=Mock()
        controller=Controller(SimpleNamespace(quit=quit_app),None)
        controller.overlays=[self.overlay,other]
        try:
            controller.quit()
            controller.quit()
            other.reveal.setDuration(300)
            QTest.qWait(230)
            quit_app.assert_not_called()
            QTest.qWait(130)
            quit_app.assert_called_once()
            self.assertFalse(other.isVisible())
        finally:
            other.hide()
            other.deleteLater()

    @patch('circle_to_search.app.QDesktopServices.openUrl',return_value=True)
    def test_result_link_opens_with_the_system_handler_and_closes_cts_once(self,opener):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from circle_to_search.app import Controller
        quit_app=Mock()
        controller=Controller(SimpleNamespace(quit=quit_app),None)
        controller.overlays=[self.overlay]
        self.overlay.externalRequested.connect(controller.open_external)
        self.overlay.sheet.load_url('https://www.google.com/search?q=test')
        target=QUrl('https://example.org/article')
        self.overlay.sheet.browser.externalRequested.emit(target)
        self.overlay.sheet.browser.externalRequested.emit(target)
        opener.assert_called_once_with(target)
        self.assertTrue(controller.closing)
        QTest.qWait(230)
        self.assertFalse(self.overlay.isVisible())
        quit_app.assert_called_once()

    @patch('circle_to_search.app.QDesktopServices.openUrl',return_value=True)
    def test_open_in_browser_button_uses_the_same_close_and_open_path(self,opener):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from circle_to_search.app import Controller
        controller=Controller(SimpleNamespace(quit=Mock()),None)
        controller.overlays=[self.overlay]
        self.overlay.externalRequested.connect(controller.open_external)
        self.overlay.sheet.load_url('https://www.google.com/search?q=test&gsc=2')
        self.overlay.sheet.open_external()
        self.assertEqual(opener.call_count,1)
        url=opener.call_args.args[0]
        self.assertNotIn('gsc=',url.toString())
        self.assertIn('q=test',url.toString())
        QTest.qWait(230)
        self.assertFalse(self.overlay.isVisible())

    @patch('circle_to_search.app.QDesktopServices.openUrl',return_value=False)
    def test_failed_system_opener_keeps_results_available(self,opener):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from circle_to_search.app import Controller
        quit_app=Mock()
        controller=Controller(SimpleNamespace(quit=quit_app),None)
        controller.overlays=[self.overlay]
        self.overlay.sheet.load_url('https://www.google.com/search?q=test')
        controller.open_external(QUrl('https://example.org/article'))
        self.assertFalse(controller.closing)
        self.assertTrue(self.overlay.isVisible())
        self.assertIn('default application',self.overlay.sheet.message.text())
        quit_app.assert_not_called()

    def test_active_tab_indicator_moves_smoothly_to_the_new_tab(self):
        sheet=self.overlay.sheet
        sheet.load_url('https://www.google.com/search?q=test')
        QTest.qWait(250)
        tabs=sheet.tabs
        start=tabs.indicator.x()
        tabs.set_active('videos')
        QTest.qWait(70)
        self.assertGreater(tabs.indicator.x(),start)
        self.assertLess(tabs.indicator.x(),tabs.buttons['videos'].x())
        QTest.qWait(150)
        self.assertEqual(tabs.indicator.x(),tabs.buttons['videos'].x())

    def test_same_navigation_tabs_stay_visible_for_all_images_and_videos(self):
        sheet=self.overlay.sheet
        labels=["AI Mode","All","Images","Videos","Shopping","News","Forums"]
        for suffix,active in [("","all"),("&tbm=isch","images"),("&tbm=vid","videos")]:
            sheet.load_url("https://www.google.com/search?q=example"+suffix)
            self.assertEqual([b.text() for b in sheet.tabs.buttons.values()],labels)
            self.assertTrue(all(b.isVisible() for b in sheet.tabs.buttons.values()))
            self.assertTrue(sheet.tabs.buttons[active].isChecked())

    def test_native_tab_click_changes_view_without_replacing_query(self):
        sheet=self.overlay.sheet
        sheet.load_url("https://www.google.com/search?q=docs%2FREFERENCE.md")
        sheet.tabs.buttons["videos"].click()
        self.assertEqual(parse_qs(urlsplit(sheet.browser.url.toString()).query)["q"],["docs/REFERENCE.md"])
        self.assertIn("udm=7",sheet.browser.url.toString())
        self.assertTrue(sheet.tabs.buttons["videos"].isChecked())
        self.assertTrue(sheet.tabs.buttons["ai"].isVisible())

    def test_native_tools_filter_keeps_search_view(self):
        sheet=self.overlay.sheet
        sheet.load_url("https://www.google.com/search?q=example&udm=7")
        sheet.filter_time("w")
        self.assertIn("udm=7",sheet.browser.url.toString())
        self.assertIn("tbs=qdr",sheet.browser.url.toString())

    def test_search_navigation_is_not_added_to_google_translate(self):
        sheet=self.overlay.sheet
        sheet.load_url("https://translate.google.com/?sl=auto&tl=en&hl=en&text=hello")
        self.assertFalse(sheet.tabs.isVisible())
