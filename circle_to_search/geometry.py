"""Selection coordinates are logical; screenshot coordinates are physical pixels."""

import math

from PySide6.QtCore import QPointF, QRect, QRectF, QSize


def selection_bounds(points: list[QPointF], viewport: QRectF, box: bool = False) -> QRectF:
    if not points:
        return QRectF()
    if box:
        bounds = QRectF(points[0], points[-1]).normalized()
    else:
        xs, ys = [p.x() for p in points], [p.y() for p in points]
        bounds = QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    # QRectF.intersected() discards the location of a zero-height highlight
    # stroke. Keep its endpoints so a horizontal line can still select text.
    left, top = max(bounds.left(), viewport.left()), max(bounds.top(), viewport.top())
    right, bottom = min(bounds.right(), viewport.right()), min(bounds.bottom(), viewport.bottom())
    return (
        QRectF(left, top, right - left, bottom - top)
        if right >= left and bottom >= top
        else QRectF()
    )


def pixel_bounds(selection: QRectF, viewport: QRectF, image_size: QSize) -> QRect:
    """Round outward, retaining edge pixels and clamping to the actual image."""
    if viewport.isEmpty() or selection.isEmpty():
        return QRect()
    selection = selection.intersected(viewport)
    if selection.isEmpty():
        return QRect()
    sx, sy = image_size.width() / viewport.width(), image_size.height() / viewport.height()
    left = math.floor((selection.left() - viewport.left()) * sx)
    top = math.floor((selection.top() - viewport.top()) * sy)
    right = math.ceil((selection.right() - viewport.left()) * sx)
    bottom = math.ceil((selection.bottom() - viewport.top()) * sy)
    return QRect(left, top, right - left, bottom - top).intersected(
        QRect(0, 0, image_size.width(), image_size.height())
    )
