"""Resolve a circle, scribble, highlight stroke or tap against local OCR boxes."""

from dataclasses import dataclass, field
from statistics import median

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainterPath, QPainterPathStroker

from .geometry import selection_bounds
from .ocr import Document


@dataclass
class Selection:
    kind: str
    bounds: QRectF
    indices: list[int] = field(default_factory=list)
    text: str = ""


def stroke_length(points):
    return sum(
        ((b.x() - a.x()) ** 2 + (b.y() - a.y()) ** 2) ** 0.5 for a, b in zip(points, points[1:])
    )


def is_loop(points, bounds):
    if len(points) < 5 or min(bounds.width(), bounds.height()) < 16:
        return False
    gap = ((points[-1].x() - points[0].x()) ** 2 + (points[-1].y() - points[0].y()) ** 2) ** 0.5
    area = (
        abs(sum(a.x() * b.y() - b.x() * a.y() for a, b in zip(points, points[1:] + points[:1]))) / 2
    )
    return (
        gap < max(bounds.width(), bounds.height()) * 0.45
        and area > bounds.width() * bounds.height() * 0.3
    )


def text_selection(document, indices):
    indices = document.expand_words(indices)
    lines = {}
    for index in indices:
        lines.setdefault(document.glyphs[index].line, []).append(index)
    indices = [
        i
        for line, selected in lines.items()
        for i in range(min(selected), max(selected) + 1)
        if document.glyphs[i].line == line
    ]
    indices.sort()
    return Selection("text", document.bounds(indices), indices, document.text(indices))


def resolve_gesture(
    points: list[QPointF], viewport: QRectF, document: Document, box=False
) -> Selection | None:
    if not points:
        return None
    bounds = selection_bounds(points, viewport, box)
    if stroke_length(points) < 9 and not box:
        point = points[-1]
        candidates = [
            (i, g)
            for i, g in enumerate(document.glyphs)
            if g.rect.adjusted(-5, -5, 5, 5).contains(point)
        ]
        if candidates:
            index, _ = min(
                candidates, key=lambda pair: (pair[1].rect.center() - point).manhattanLength()
            )
            return text_selection(document, [index])
        # An object tap starts a movable crop. Lens performs object recognition.
        return Selection(
            "image", QRectF(point.x() - 100, point.y() - 100, 200, 200).intersected(viewport)
        )
    if box:
        return Selection("image", bounds) if min(bounds.width(), bounds.height()) >= 8 else None
    path = QPainterPath(points[0])
    for point in points[1:]:
        path.lineTo(point)
    loop = is_loop(points, bounds)
    if loop:
        path.closeSubpath()
        hits = [i for i, g in enumerate(document.glyphs) if path.contains(g.rect.center())]
    else:
        stroker = QPainterPathStroker()
        stroker.setWidth(8)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        stroke = stroker.createStroke(path)
        hits = []
        for i, glyph in enumerate(document.glyphs):
            # Include underlines and strokes just above the glyph baseline.
            rect = glyph.rect
            if bounds.width() >= bounds.height() * 2:
                inset = min(3, rect.width() * 0.2)
                padding = min(10, rect.height() * 0.4)
                hit_rect = rect.adjusted(inset, -padding, -inset, padding)
            elif bounds.height() >= bounds.width() * 2:
                inset = min(3, rect.height() * 0.2)
                padding = min(10, rect.width() * 0.4)
                hit_rect = rect.adjusted(-padding, inset, padding, -inset)
            else:
                hit_rect = rect.adjusted(2, 2, -2, -2)
            if stroke.intersects(hit_rect):
                hits.append(i)
    if hits:
        # An underline can fall within the padded hit boxes of two adjacent
        # rows. A nearly straight stroke belongs to the nearest reading line,
        # while a taller scribble must remain able to select multiple lines.
        heights = [document.glyphs[i].rect.height() for i in hits]
        widths = [document.glyphs[i].rect.width() for i in hits]
        horizontal = (
            bounds.width() >= bounds.height() * 2 and bounds.height() <= median(heights) * 0.6
        )
        vertical = bounds.height() >= bounds.width() * 2 and bounds.width() <= median(widths) * 0.6
        if not loop and (horizontal or vertical):
            lines = {}
            for i in hits:
                lines.setdefault(document.glyphs[i].line, []).append(i)
            if len(lines) > 1:

                def distance(indices):
                    if horizontal:
                        return median(
                            abs(
                                bounds.center().y()
                                - (
                                    document.glyphs[i].rect.bottom()
                                    - document.glyphs[i].rect.height() * 0.25
                                )
                            )
                            for i in indices
                        )
                    return median(
                        abs(bounds.center().x() - document.glyphs[i].rect.center().x())
                        for i in indices
                    )

                hits = min(lines.values(), key=distance)
        coverage = sum(
            document.glyphs[i].rect.width() * document.glyphs[i].rect.height() for i in hits
        )
        coverage /= max(1, bounds.width() * bounds.height())
        heights = [document.glyphs[i].rect.height() for i in hits]
        widths = [document.glyphs[i].rect.width() for i in hits]
        narrow = bounds.height() < median(heights) * 2.4 or bounds.width() < median(widths) * 2.4
        if coverage >= 0.14 or (not loop and narrow):
            return text_selection(document, hits)
    # A perfectly straight line is valid. Give an unrecognized line a padded
    # crop so OCR can retry the full glyphs instead of uploading a 0px strip.
    if bounds.width() < 8 or bounds.height() < 8:
        bounds = bounds.adjusted(-12, -16, 12, 16).intersected(viewport)
    return Selection("image", bounds) if not bounds.isEmpty() else None
