"""Check native motion, Wayland roles and KWin effect eligibility offline."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def child():
    from PySide6.QtCore import QRectF, Qt, QTimer
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication

    from circle_to_search.appearance import prepare_qt
    from circle_to_search.ocr import Document, Glyph
    from circle_to_search.ui import SelectionOverlay

    prepare_qt()
    app = QApplication([])
    app.setApplicationName("circle-to-search-motion-check")
    screen = app.primaryScreen()
    image = QImage(screen.size(), QImage.Format.Format_RGB32)
    image.fill(Qt.white)
    rect = QRectF(200, 200, 150, 24)
    overlay = SelectionOverlay(
        image,
        screen,
        document=Document([Glyph("Motion", rect, "line", "word")]),
        start_ocr=False,
        auto_search=False,
    )
    overlay.dismissed.connect(app.quit)
    overlay.show_overlay()
    geometry = overlay.geometry()
    canvas = set()
    selections = set()
    sheet_frames = set()
    failures = []

    def sample():
        if overlay.geometry() != geometry:
            failures.append("The full-screen surface moved or resized")
        canvas.add(round(overlay.overlay_progress, 3))
        if overlay.selection:
            selections.add(round(overlay.selection_progress, 3))
        if overlay.sheet.isVisible():
            sheet_frames.add((overlay.sheet.y(), overlay.sheet.height()))

    timer = QTimer()
    timer.timeout.connect(sample)
    timer.start(10)

    def select():
        overlay.finish_gesture([rect.center()], False)
        overlay.sheet.ensure_browser()
        overlay.sheet.browser.setHtml(
            '<body style="background:white">Offline browser rendering</body>'
        )

    QTimer.singleShot(250, select)
    QTimer.singleShot(900, overlay.sheet.toggle)
    QTimer.singleShot(1300, overlay.sheet.toggle)
    QTimer.singleShot(1700, overlay.clear_selection)
    QTimer.singleShot(2100, overlay.dismiss)
    QTimer.singleShot(6000, app.quit)
    app.exec()
    if len(canvas) < 5 or len(selections) < 3 or len(sheet_frames) < 10:
        failures.append("A transition snapped instead of producing intermediate frames")
    if overlay.isVisible() or not overlay.closing:
        failures.append("Dismissal did not finish")
    print(
        "Motion frames:",
        len(canvas),
        "overlay,",
        len(selections),
        "selection,",
        len(sheet_frames),
        "sheet",
        flush=True,
    )
    if failures:
        print(failures, file=sys.stderr)
    return bool(failures)


def main():
    if "--child" in sys.argv:
        return child()
    log = Path("/tmp/circle-to-search-motion-wayland.log")
    descriptor = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    environment = os.environ.copy()
    environment["WAYLAND_DEBUG"] = "client"
    with os.fdopen(descriptor, "w") as stream:
        result = subprocess.run(
            [sys.executable, __file__, "--child"],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=stream,
            text=True,
            timeout=15,
        )
    print(result.stdout, end="")
    if result.returncode:
        print("Native motion check failed; details:", log, file=sys.stderr)
        return 1
    trace = log.read_text()
    if not re.search(r'get_layer_surface\([^\n]*"utility"', trace):
        raise RuntimeError("No utility layer surface was mapped in the Wayland protocol")
    if "get_toplevel(" in trace:
        raise RuntimeError("The overlay or its browser created an ordinary application window")
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtQml import QJSEngine

    _app = QCoreApplication([])
    window = {
        "windowClass": "circle-to-search circle-to-search",
        "hasDecoration": False,
        "popupWindow": False,
        "managed": True,
        "visible": True,
        "normalWindow": False,
        "dialog": False,
        "utility": True,
    }
    for effect, name in [
        ("scale", "ScaleEffect.isScaleWindow"),
        ("fade", "FadeEffect.isFadeWindow"),
        ("fadingpopups", "isPopupWindow"),
    ]:
        source = Path("/usr/share/kwin/effects", effect, "contents/code/main.js").read_text()
        if effect == "fadingpopups":
            source = source.split("var fadingPopupsEffect")[0]
        else:
            source = source.rsplit(
                "new " + ("ScaleEffect" if effect == "scale" else "FadeEffect"), 1
            )[0]
        engine = QJSEngine()
        globals = "var effect={isGrabbed:()=>false};var Effect={WindowAddedGrabRole:1,WindowClosedGrabRole:2};\n"
        value = engine.evaluate(globals + source + "\n" + name + "(" + json.dumps(window) + ")")
        if value.isError() or not value.isBool() or value.toBool():
            raise RuntimeError(
                "KWin " + effect + " would still animate the overlay: " + value.toString()
            )
    print(
        "Verified utility layer protocol, no application-window role, and exclusion from installed KWin Scale/Fade/Popup effects."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
