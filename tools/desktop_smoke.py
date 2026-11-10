"""Exercise native capture, selection, reselect and Escape; never upload data."""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint, QThreadPool, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from circle_to_search.app import Controller
from circle_to_search.appearance import prepare_qt


def main():
    prepare_qt()
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    controller = Controller(app, argparse.Namespace(image=None, mode="circle", ocr_language="jpn+eng",
                                                  auto_search=False, external=False, vertical=False))
    failure = []
    stage = ["capture"]
    deadline = time.monotonic() + 40

    def fail(message):
        failure.append(message)
        app.quit()

    # Avoid modal dialogs if native capture itself fails during the smoke check.
    controller.error = fail

    def advance():
        try:
            if time.monotonic() > deadline:
                fail("Timed out during " + stage[0])
                return
            if stage[0] == "capture" and controller.overlays:
                overlay = next(o for o in controller.overlays if o.screen() == controller.current)
                assert overlay.isVisible()
                if app.platformName()=="wayland":
                    assert overlay.layer_surface is not None,"Wayland overlay role was not configured"
                geometry = overlay.screen().geometry()
                assert overlay.size() == geometry.size(), (overlay.size(), geometry.size())
                x, y = overlay.width() // 2, overlay.height() // 2
                stage[0] = "preview"
                QTest.mousePress(overlay, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, QPoint(x - 50, y - 50))
                QTest.mouseMove(overlay, QPoint(x + 50, y + 50))
                QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, QPoint(x + 50, y + 50))
            elif stage[0] == "preview":
                overlay = next(o for o in controller.overlays if o.screen() == controller.current)
                assert overlay.selection is not None
                assert overlay.sheet.isVisible()
                assert overlay.isVisible()
                assert not overlay.crop().isNull()
                print("Native capture and selection:", controller.current.name(), "crop", overlay.crop().size())
                overlay.sheet.toggle()
                assert overlay.sheet.expanded
                overlay.sheet.cleared.emit()
                assert overlay.selection is None
                stage[0] = "cancel"
            elif stage[0] == "cancel":
                overlay = next(o for o in controller.overlays if o.screen() == controller.current)
                assert overlay.isVisible()
                stage[0] = "done"
                QTest.keyClick(overlay, Qt.Key.Key_Escape)
        except Exception as exc:
            fail(repr(exc))

    timer = QTimer()
    timer.timeout.connect(advance)
    timer.start(100)
    QTimer.singleShot(0, controller.start)
    app.exec()
    QThreadPool.globalInstance().waitForDone()
    if failure or stage[0] != "done":
        print("Desktop smoke check failed:", failure or stage[0], file=sys.stderr)
        return 1
    print("Native Wayland capture, inline sheet, expansion, reselection, and Escape passed. No image was uploaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
