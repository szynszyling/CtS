"""Check the selection popup over an accelerated browser using local HTML."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from circle_to_search.appearance import prepare_qt
from circle_to_search.ocr import Document, Glyph
from circle_to_search.ui import SelectionOverlay


def main():
    prepare_qt()
    app = QApplication([])
    app.setApplicationName("circle-to-search-popup-check")
    screen = app.primaryScreen()
    image = QImage(screen.size(), QImage.Format.Format_RGB32)
    image.fill(QColor("#202124"))
    rect = QRectF(screen.size().width() / 2 - 100, screen.size().height() - 150, 200, 24)
    overlay = SelectionOverlay(
        image,
        screen,
        document=Document([Glyph("Selection", rect, "line", "word")]),
        start_ocr=False,
        auto_search=False,
    )
    overlay.show_overlay()
    overlay.cancelled.connect(app.quit)
    failures = []
    finished = [False]
    entrance = set()
    exit_frames = set()
    positions = set()

    def sample():
        popup = overlay.text_actions
        if hasattr(popup, "_fade"):
            frames = entrance if popup.visible_goal else exit_frames
            frames.add(round(popup._fade.effect.opacity(), 3))
            if popup.visible_goal:
                positions.add(popup.y())

    timer = QTimer()
    timer.timeout.connect(sample)
    timer.start(10)

    def warm():
        overlay.sheet.loading()
        overlay.sheet.ensure_browser()
        overlay.sheet.browser.setHtml(
            '<body style="margin:0;background:#ccffcc">Local browser background</body>'
        )

    def select():
        overlay.finish_gesture([rect.center()], False)
        overlay.sheet.browser.setHtml(
            '<body style="margin:0;background:#ccffcc"><h2>Local browser background</h2></body>'
        )

    def inspect():
        popup = overlay.text_actions
        point = popup.pos() + QPoint(8, popup.height() // 2)
        capture = overlay.grab().toImage()
        pixel = capture.pixelColor(
            round(point.x() * capture.devicePixelRatio()),
            round(point.y() * capture.devicePixelRatio()),
        )
        effect = popup.graphicsEffect()
        print(
            "Popup background:",
            pixel.name(),
            "opacity:",
            effect.opacity() if effect else "painted directly",
            flush=True,
        )
        if min(pixel.red(), pixel.green(), pixel.blue()) < 245:
            failures.append("The popup background is not opaque white over the browser")
        divider = popup.divider.mapTo(overlay, popup.divider.rect().center())
        line = capture.pixelColor(
            round(divider.x() * capture.devicePixelRatio()),
            round(divider.y() * capture.devicePixelRatio()),
        )
        if (
            min(line.red(), line.green(), line.blue()) >= 245
            or max(line.red(), line.green(), line.blue())
            - min(line.red(), line.green(), line.blue())
            > 12
        ):
            failures.append("The thin divider is not visible between Copy and Translate")
        print(
            "Divider:",
            line.name(),
            "entrance frames:",
            len(entrance),
            "slide positions:",
            len(positions),
            flush=True,
        )
        clicks = []
        popup.copyRequested.disconnect(overlay.copy_text)
        popup.translateRequested.disconnect(overlay.translate)
        popup.copyRequested.connect(lambda: clicks.append("copy"))
        popup.translateRequested.connect(lambda: clicks.append("translate"))
        for button in [popup.copy_button, popup.translate_button]:
            QTest.mouseClick(
                overlay.windowHandle(),
                Qt.LeftButton,
                pos=button.mapTo(overlay, button.rect().center()),
            )
        if clicks != ["copy", "translate"]:
            failures.append("The popup buttons did not receive clicks above the browser")
        path = Path("/tmp/circle-to-search-popup.png")
        capture.save(str(path))
        path.chmod(0o600)
        overlay.clear_selection()
        QTimer.singleShot(220, hidden)

    def hidden():
        if overlay.text_actions.isVisible():
            failures.append("The popup did not finish dismissing")
        if len(entrance) < 3 or len(exit_frames) < 3 or len(positions) < 3:
            failures.append("The popup transition did not animate smoothly")
        finished[0] = True
        app.quit()

    QTimer.singleShot(100, warm)
    QTimer.singleShot(500, select)
    QTimer.singleShot(850, overlay.sheet.toggle)
    QTimer.singleShot(1200, overlay.sheet.toggle)
    QTimer.singleShot(1700, inspect)
    QTimer.singleShot(6000, app.quit)
    app.exec()
    if failures or not finished[0]:
        print(failures or ["Popup check did not complete"], file=sys.stderr)
        return 1
    print(
        "Opaque popup, divider, native button input, sheet stacking and entrance/exit motion passed; no capture or network requests."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
