import shutil
import subprocess
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

from circle_to_search.gestures import resolve_gesture
from circle_to_search.ocr import (
    MODEL_DIR,
    Document,
    Glyph,
    HocrParser,
    gesture_region,
    recognize_document,
)

APP = QApplication.instance() or QApplication([])


def japanese_image(text="日本語の文字を選択します", size=18, dark=False):
    image = QImage(900, 130, QImage.Format.Format_RGB32)
    image.fill(QColor("#202124") if dark else Qt.GlobalColor.white)
    p = QPainter(image)
    f = QFont("Noto Sans CJK JP")
    f.setPixelSize(size)
    p.setFont(f)
    p.setPen(Qt.GlobalColor.white if dark else Qt.GlobalColor.black)
    p.drawText(20, 65, text)
    p.end()
    return image


class DocumentTests(unittest.TestCase):
    @patch("circle_to_search.ocr.shutil.which", return_value=None)
    def test_missing_tesseract_is_reported(self, _):
        with self.assertRaisesRegex(RuntimeError, "Install Tesseract"):
            recognize_document(japanese_image())

    @patch("circle_to_search.ocr.MODEL_DIR")
    @patch("circle_to_search.ocr.subprocess.run")
    def test_missing_japanese_data_never_silently_falls_back_to_english(self, run, directory):
        directory.__truediv__.return_value.exists.return_value = False
        run.return_value = subprocess.CompletedProcess(
            [], 0, "List of available languages (1):\neng\n", ""
        )
        with self.assertRaisesRegex(RuntimeError, "jpn"):
            recognize_document(japanese_image())

    @patch(
        "circle_to_search.ocr.subprocess.run",
        side_effect=subprocess.TimeoutExpired("tesseract", 35),
    )
    def test_ocr_timeout_has_a_recovery_message(self, _):
        with self.assertRaisesRegex(RuntimeError, "smaller selection"):
            recognize_document(japanese_image())

    def test_hocr_character_coordinates_account_for_upscaling(self):
        parser = HocrParser(2, 2)
        parser.feed(
            "<span class='ocr_line' id='l'><span class='ocrx_word' id='w'><span class='ocrx_cinfo' title='x_bboxes 20 40 40 70; x_conf 98'>語</span></span></span>"
        )
        self.assertEqual(parser.glyphs[0].text, "語")
        self.assertEqual(parser.glyphs[0].rect, QRectF(10, 20, 10, 15))

    def test_japanese_is_not_split_with_spaces(self):
        doc = Document(
            [
                Glyph(c, QRectF(i * 20, 10, 18, 20), "line", str(i))
                for i, c in enumerate("日本語かなカナ")
            ]
        )
        self.assertEqual(doc.text(), "日本語かなカナ")
        self.assertEqual(doc.text([1, 2]), "本語")

    def test_latin_words_keep_spaces(self):
        doc = Document(
            [Glyph("Hello", QRectF(), "line", "1"), Glyph("world", QRectF(), "line", "2")]
        )
        self.assertEqual(doc.text(), "Hello world")

    def test_lines_keep_reading_order(self):
        doc = Document([Glyph("日本語", QRectF(), "1", "1"), Glyph("次の行", QRectF(), "2", "2")])
        self.assertEqual(doc.text(), "日本語\n次の行")

    def test_region_keeps_text_above_an_underline_and_context_at_the_screen_edge(self):
        rect = gesture_region([QPointF(4, 70), QPointF(100, 70)], QRectF(0, 0, 1920, 1080))
        self.assertTrue(rect.contains(QRectF(4, 45, 100, 20)))
        self.assertEqual(rect.left(), 0)
        self.assertLess(rect.width() * rect.height(), 1920 * 1080 / 10)

    def test_vertical_region_keeps_context_along_the_column(self):
        rect = gesture_region([QPointF(100, 100)], QRectF(0, 0, 1920, 1080), vertical=True)
        self.assertTrue(rect.contains(QPointF(100, 240)))
        self.assertTrue(rect.contains(QPointF(75, 100)))


@unittest.skipUnless(
    shutil.which("tesseract") and (MODEL_DIR / "jpn.traineddata").exists(),
    "Fetch Japanese OCR models first",
)
class JapaneseRecognitionTests(unittest.TestCase):
    def test_priority_region_preserves_small_kana_and_kanji(self):
        from circle_to_search.geometry import pixel_bounds

        text = "ひらがなとカタカナと漢字"
        image = japanese_image(text, 14, True)
        region = gesture_region([QPointF(30, 66), QPointF(180, 66)], QRectF(image.rect()))
        crop = image.copy(pixel_bounds(region, QRectF(image.rect()), image.size()))
        self.assertEqual(recognize_document(crop).text(), text)

    def test_kana_and_kanji_are_read_at_small_desktop_sizes(self):
        for size in (12, 18, 24):
            with self.subTest(size=size):
                text = "東京で日本語を勉強しています"
                self.assertEqual(recognize_document(japanese_image(text, size)).text(), text)

    def test_hiragana_katakana_and_kanji_on_dark_background(self):
        text = "ひらがなとカタカナと漢字"
        self.assertEqual(recognize_document(japanese_image(text, 14, True)).text(), text)

    def test_line_selects_exact_japanese_characters(self):
        image = japanese_image()
        doc = recognize_document(image)
        start, end = doc.glyphs[0].rect.center(), doc.glyphs[2].rect.center()
        selection = resolve_gesture([start, end], QRectF(image.rect()), doc)
        self.assertEqual(selection.kind, "text")
        self.assertEqual(selection.text, "日本語")

    def test_tap_selects_one_kanji(self):
        image = japanese_image()
        doc = recognize_document(image)
        point = doc.glyphs[2].rect.center()
        selection = resolve_gesture([point, point], QRectF(image.rect()), doc)
        self.assertEqual(selection.text, "語")

    def test_underline_selects_kana_without_needing_a_loop(self):
        image = japanese_image("ひらがなとカタカナ")
        doc = recognize_document(image)
        first, last = doc.glyphs[0].rect, doc.glyphs[3].rect
        y = max(g.rect.bottom() for g in doc.glyphs[:4]) + 3
        selection = resolve_gesture(
            [QPointF(first.center().x(), y), QPointF(last.center().x(), y)],
            QRectF(image.rect()),
            doc,
        )
        self.assertEqual(selection.kind, "text")
        self.assertEqual(selection.text, "ひらがな")

    def test_vertical_japanese_has_real_character_boxes(self):
        image = QImage(150, 300, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        p = QPainter(image)
        font = QFont("Noto Sans CJK JP")
        font.setPixelSize(28)
        p.setFont(font)
        p.setPen(Qt.GlobalColor.black)
        text = "日本語の文章"
        for i, c in enumerate(text):
            p.drawText(70, 50 + i * 36, c)
        p.end()
        doc = recognize_document(image, vertical=True)
        self.assertEqual(doc.text(), text)
        self.assertTrue(all(not g.rect.isEmpty() for g in doc.glyphs))
        self.assertGreater(doc.glyphs[-1].rect.top(), doc.glyphs[0].rect.bottom())
        selection = resolve_gesture(
            [doc.glyphs[0].rect.center(), doc.glyphs[2].rect.center()], QRectF(image.rect()), doc
        )
        self.assertEqual(selection.text, "日本語")
