"""Render a synthetic selection and result panel without touching the desktop."""

import math
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPointF, QRectF, Qt, QThreadPool
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication

from circle_to_search.ocr import recognize_document
from circle_to_search.ui import SelectionOverlay


def sample_image(width=1440, height=900):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#202937"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#f4efe5"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(90, 110, width - 180, height - 210), 16, 16)
    painter.setPen(QColor("#536056"))
    painter.setFont(QFont("DejaVu Sans", 11))
    painter.drawText(140, 165, "FIELDNOTES    /    A LITTLE CLOSER TO NATURE")
    painter.setFont(QFont("DejaVu Sans", 32, QFont.Weight.Bold))
    painter.drawText(155, 270, "Room to grow.")
    painter.setFont(QFont("DejaVu Sans", 15))
    painter.drawText(155, 325, "Small discoveries for everyday spaces.")
    painter.drawText(155, 385, "MONSTERA DELICIOSA")
    painter.setFont(QFont("DejaVu Sans", 12))
    painter.drawText(155, 420, "A familiar leaf. An unfamiliar name?")
    painter.setFont(QFont("Noto Sans CJK JP", 16))
    painter.drawText(155, 480, "ひらがな・カタカナ・漢字を選択")
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#dfd5c4"))
    painter.drawRoundedRect(QRectF(810, 240, 400, 420), 25, 25)
    painter.setPen(QColor("#417054"))
    painter.setBrush(QColor("#417054"))
    painter.drawRoundedRect(QRectF(1004, 405, 10, 150), 4, 4)
    for angle in [-50, 10, 75]:
        painter.save()
        painter.translate(1010, 440)
        painter.rotate(angle)
        path = QPainterPath(QPointF(0, 0))
        path.cubicTo(-110, -10, -145, -145, -25, -155)
        path.cubicTo(80, -160, 85, -55, 0, 0)
        painter.drawPath(path)
        painter.restore()
    painter.setBrush(QColor("#ba7a59"))
    painter.setPen(Qt.PenStyle.NoPen)
    pot = QPainterPath(QPointF(955, 535))
    pot.lineTo(1065, 535)
    pot.lineTo(1047, 620)
    pot.lineTo(973, 620)
    pot.closeSubpath()
    painter.drawPath(pot)
    painter.end()
    return image


def main():
    app = QApplication([])
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/circle-to-search-previews")
    output.mkdir(parents=True, exist_ok=True)
    image = sample_image()
    image.save(str(output / "sample.png"))
    document = recognize_document(image)
    overlay = SelectionOverlay(
        image, app.primaryScreen(), document=document, start_ocr=False, auto_search=False
    )
    overlay.resize(1440, 900)
    overlay.show()
    app.processEvents()
    overlay.created_at -= 2
    overlay.grab().save(str(output / "initial.png"))
    overlay.points = [
        QPointF(1010 + 220 * math.cos(i * math.tau / 96), 440 + 240 * math.sin(i * math.tau / 96))
        for i in range(97)
    ]
    overlay.grab().save(str(output / "gesture.png"))
    overlay.finish_gesture(overlay.points, False)
    app.processEvents()
    overlay.sheet.animation.stop()
    overlay.sheet.show_sheet(False)
    overlay.grab().save(str(output / "image.png"))
    overlay.clear_selection()
    # OCR coordinates are already in this fixture's logical pixel space.
    japanese = [g for g in document.glyphs if any("\u3040" <= c <= "\u9fff" for c in g.text)]
    japanese = [g for g in japanese if g.rect.top() > 440]
    if japanese:
        start, end = japanese[0].rect.center(), japanese[-1].rect.center()
        overlay.finish_gesture([start, end], False)
        app.processEvents()
        overlay.sheet.animation.stop()
        overlay.sheet.show_sheet(False)
        overlay.grab().save(str(output / "japanese.png"))
    QThreadPool.globalInstance().waitForDone()
    print(output)


if __name__ == "__main__":
    main()
