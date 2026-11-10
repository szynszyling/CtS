import unittest

from PySide6.QtCore import QPointF, QRect, QRectF, QSize

from circle_to_search.geometry import pixel_bounds, selection_bounds


class GeometryTests(unittest.TestCase):
    def test_circle_uses_every_point_not_just_start_and_end(self):
        points = [
            QPointF(50, 20),
            QPointF(80, 50),
            QPointF(50, 80),
            QPointF(20, 50),
            QPointF(50, 20),
        ]
        self.assertEqual(selection_bounds(points, QRectF(0, 0, 100, 100)), QRectF(20, 20, 60, 60))

    def test_box_drag_works_in_reverse(self):
        points = [QPointF(80, 90), QPointF(5, 5), QPointF(20, 30)]
        self.assertEqual(
            selection_bounds(points, QRectF(0, 0, 100, 100), box=True), QRectF(20, 30, 60, 60)
        )

    def test_selection_clamped_at_monitor_edge(self):
        points = [QPointF(-20, -30), QPointF(150, 130)]
        self.assertEqual(selection_bounds(points, QRectF(0, 0, 100, 100)), QRectF(0, 0, 100, 100))

    def test_fractional_dpi_rounds_outward(self):
        self.assertEqual(
            pixel_bounds(QRectF(1, 1, 2, 2), QRectF(0, 0, 100, 100), QSize(125, 125)),
            QRect(1, 1, 3, 3),
        )

    def test_negative_monitor_origin(self):
        self.assertEqual(
            pixel_bounds(
                QRectF(-1920, 0, 1920, 1080), QRectF(-1920, 0, 3840, 1080), QSize(7680, 2160)
            ),
            QRect(0, 0, 3840, 2160),
        )

    def test_second_monitor_offset(self):
        self.assertEqual(
            pixel_bounds(QRectF(0, 0, 1920, 1080), QRectF(-1920, 0, 3840, 1080), QSize(3840, 1080)),
            QRect(1920, 0, 1920, 1080),
        )

    def test_outside_or_empty_selection_cannot_become_full_image(self):
        for rect in [QRectF(), QRectF(101, 101, 10, 10)]:
            self.assertTrue(pixel_bounds(rect, QRectF(0, 0, 100, 100), QSize(100, 100)).isEmpty())

    def test_no_points(self):
        self.assertTrue(selection_bounds([], QRectF(0, 0, 100, 100)).isEmpty())
