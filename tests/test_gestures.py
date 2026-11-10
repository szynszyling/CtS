import math
import unittest

from PySide6.QtCore import QPointF, QRectF

from circle_to_search.gestures import resolve_gesture
from circle_to_search.ocr import Document, Glyph


class GestureTests(unittest.TestCase):
    def setUp(self):
        self.doc=Document([Glyph(c,QRectF(100+i*20,100,18,24),"line",str(i)) for i,c in enumerate("日本語かな")])
        self.viewport=QRectF(0,0,800,600)

    def test_reverse_horizontal_highlight(self):
        selection=resolve_gesture([QPointF(150,112),QPointF(108,112)],self.viewport,self.doc)
        self.assertEqual(selection.text,"日本語")

    def test_scribbling_across_characters_selects_text(self):
        points=[QPointF(102,115),QPointF(118,100),QPointF(128,124),QPointF(143,100),QPointF(155,115)]
        self.assertEqual(resolve_gesture(points,self.viewport,self.doc).text,"日本語")

    def test_circle_around_text_selects_text(self):
        points=[QPointF(129+39*math.cos(i*math.tau/32),112+20*math.sin(i*math.tau/32)) for i in range(33)]
        self.assertEqual(resolve_gesture(points,self.viewport,self.doc).text,"日本語")

    def test_circle_around_large_image_does_not_select_tiny_caption(self):
        points=[QPointF(220+190*math.cos(i*math.tau/32),220+190*math.sin(i*math.tau/32)) for i in range(33)]
        self.assertEqual(resolve_gesture(points,self.viewport,self.doc).kind,"image")

    def test_forced_box_keeps_image_search_even_over_text(self):
        selection=resolve_gesture([QPointF(98,98),QPointF(160,126)],self.viewport,self.doc,box=True)
        self.assertEqual(selection.kind,"image")

    def test_missing_text_does_not_discard_straight_line(self):
        selection=resolve_gesture([QPointF(100,100),QPointF(200,100)],self.viewport,Document([]))
        self.assertGreater(selection.bounds.height(),20)

    def test_tap_at_monitor_edge_does_not_capture_outside_screen(self):
        selection=resolve_gesture([QPointF(2,2)],self.viewport,Document([]))
        self.assertEqual(selection.bounds.topLeft(),QPointF(0,0))

    def test_cjk_can_be_selected_independently_within_one_ocr_word(self):
        self.doc=Document([Glyph(g.text,g.rect,g.line,"same-word") for g in self.doc.glyphs])
        selection=resolve_gesture([QPointF(129,112),QPointF(150,112)],self.viewport,self.doc)
        self.assertEqual(selection.text,"本語")

    def test_underline_does_not_pick_up_the_next_close_row(self):
        doc=Document([Glyph(c,QRectF(60+i*14,y,13,13),line,str(i))
                      for line,y,text in [('a',93,'東京で'),('b',118,'ひらが')]
                      for i,c in enumerate(text)])
        selection=resolve_gesture([QPointF(64,110),QPointF(98,110)],self.viewport,doc)
        self.assertEqual(selection.text,'東京で')

    def test_scribble_can_still_select_two_close_rows(self):
        doc=Document([Glyph(c,QRectF(60+i*14,y,13,13),line,str(i))
                      for line,y,text in [('a',93,'東京で'),('b',118,'ひらが')]
                      for i,c in enumerate(text)])
        points=[QPointF(64,100),QPointF(98,100),QPointF(64,125),QPointF(98,125)]
        self.assertEqual(resolve_gesture(points,self.viewport,doc).text,'東京で\nひらが')
