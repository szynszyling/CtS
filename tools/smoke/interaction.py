"""Exercise real pointer routing while moving and loading the native UI."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from circle_to_search.appearance import prepare_qt
from circle_to_search.ocr import Document
from circle_to_search.ui import SelectionOverlay


def main():
    prepare_qt()
    app = QApplication([])
    app.setApplicationName("circle-to-search-interaction-check")
    screen = app.primaryScreen()
    image = QImage(screen.size(), QImage.Format.Format_RGB32)
    image.fill(Qt.white)
    overlay = SelectionOverlay(
        image, screen, document=Document([]), start_ocr=False, auto_search=False
    )
    overlay.dismissed.connect(app.quit)
    overlay.show_overlay()
    window = overlay.windowHandle()
    failures = []
    completed = [False]

    def check(function):
        def run():
            try:
                function()
            except Exception as error:
                failures.append(str(error))
                app.quit()

        return run

    def click(point):
        QTest.mouseClick(window, Qt.LeftButton, pos=point)

    def drag(control, dx, dy=0):
        start = control.mapTo(overlay, control.rect().center())
        end = start + QPoint(dx, dy)
        QTest.mousePress(window, Qt.LeftButton, pos=start)
        QTest.mouseMove(window, end)
        QTest.mouseRelease(window, Qt.LeftButton, pos=end)

    def opening():
        bar = overlay.bar
        left = bar.x()
        top = bar.y()
        drag(bar.logo, -300, -120)
        assert bar.x() == max(24, left - 300), "The floating bar did not follow the pointer"
        assert bar.y() == max(84, top - 120), "The floating bar did not move vertically"
        assert overlay.selection is None, "Dragging the bar selected the desktop"
        overlay.sheet.loading()
        click(overlay.sheet.target_geometry().center())
        assert overlay.selection is None, "An opening results sheet allowed a desktop selection"
        QTimer.singleShot(300, check(loading))

    def loading():
        sheet = overlay.sheet
        click(sheet.message_page.mapTo(overlay, sheet.message_page.rect().center()))
        assert overlay.selection is None, "The loading cover passed a click to the desktop"
        before = sheet.geometry()
        drag(sheet.bar.logo, -200, -80)
        assert sheet.x() == max(16, before.x() - 200), (
            "The results sheet did not move with its search bar"
        )
        assert sheet.height() == before.height() + 80, (
            "Diagonal search-bar dragging did not expand results"
        )
        before = sheet.geometry()
        start = sheet.handle.mapTo(overlay, sheet.handle.rect().center())
        QTest.mousePress(window, Qt.LeftButton, pos=start)
        QTest.mouseMove(window, start + QPoint(90, 0))
        QTest.mouseMove(window, start + QPoint(90, -60))
        QTest.mouseRelease(window, Qt.LeftButton, pos=start + QPoint(90, -60))
        assert sheet.x() == before.x() + 90 and sheet.height() == before.height() + 60, (
            "The handle locked its drag direction"
        )
        assert overlay.selection is None, "Dragging results selected the desktop"
        sheet.ensure_browser()
        sheet.browser.setHtml('<body style="background:white">Local results fixture</body>')
        QTimer.singleShot(300, check(dismissing))

    def dismissing():
        sheet = overlay.sheet
        point = sheet.geometry().topLeft() + QPoint(35, 170)
        sheet.stop(animate=True)
        click(point)
        assert overlay.selection is None, "The disappearing sheet passed a click to the desktop"
        QTimer.singleShot(250, check(uncovered))

    def uncovered():
        assert not overlay.sheet.isVisible(), "The results sheet did not finish dismissing"
        click(QPoint(100, 300))
        assert overlay.selection is not None, "Uncovered desktop content was not selectable"
        completed[0] = True
        overlay.dismiss()

    QTimer.singleShot(300, check(opening))
    QTimer.singleShot(8000, app.quit)
    app.exec()
    if failures or not completed[0]:
        print(failures or ["The interaction check did not complete"], file=sys.stderr)
        return 1
    print(
        "Native free bar movement, simultaneous sheet movement/resizing, direction changes, and pointer blocking passed. No capture or network requests."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
