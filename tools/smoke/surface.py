"""Check real WebEngine rendering without any remote search requests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PySide6.QtCore import QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from shiboken6 import getCppPointer, isValid

from circle_to_search.appearance import prepare_qt
from circle_to_search.ocr import Document, Glyph
from circle_to_search.ui import SelectionOverlay


def main():
    prepare_qt()
    app = QApplication([])
    app.setApplicationName("circle-to-search-surface-check")
    screen = app.primaryScreen()
    image = QImage(screen.size(), QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    rect = QRectF(200, 200, 180, 24)
    overlay = SelectionOverlay(
        image,
        screen,
        document=Document([Glyph("Surface test", rect, "line", "word")]),
        start_ocr=False,
        auto_search=False,
    )
    overlay.cancelled.connect(app.quit)
    failures = []
    observed = set()
    completed = [0]
    navigating = [False]
    overlay.show_overlay()

    def observe():
        size = (overlay.width(), overlay.height())
        if size not in observed:
            observed.add(size)
            handle = overlay.windowHandle()
            print(
                "Surface geometry:",
                size,
                "window:",
                getCppPointer(handle)[0],
                "surface:",
                handle.surfaceType(),
                "layer valid:",
                isValid(overlay.layer_surface),
                flush=True,
            )
            if isValid(overlay.layer_surface):
                print(
                    "Layer exclusion:", overlay.layer_surface.property("exclusionZone"), flush=True
                )
        if overlay.size() != screen.geometry().size() and not failures:
            failures.append("Overlay changed size while initializing the browser")
        sheet = overlay.sheet
        if sheet.isVisible():
            pixel = sheet.content.grab(QRect(0, 0, 6, 6)).toImage().pixelColor(3, 3)
            if min(pixel.red(), pixel.green(), pixel.blue()) < 200 and not failures:
                failures.append("A dark browser frame was exposed during loading")
        if navigating[0] and sheet.content.currentWidget() is sheet.browser:
            navigating[0] = False
            completed[0] += 1
            if completed[0] == 3:
                QTimer.singleShot(50, load_ai_fixture)
            elif completed[0] == 4:

                def check_theme(dark):
                    if dark is not False:
                        failures.append("The browser still advertises the desktop's dark theme")
                    app.quit()

                sheet.browser.page().runJavaScript(
                    "matchMedia('(prefers-color-scheme:dark)').matches", check_theme
                )
            else:
                QTimer.singleShot(50, load_page)

    timer = QTimer()
    timer.timeout.connect(observe)
    timer.start(10)

    def select():
        overlay.finish_gesture([rect.center()], False)
        load_page()

    def load_page():
        navigating[0] = True
        overlay.sheet.ensure_browser()
        overlay.sheet.browser.setHtml("""<html><body style='background:#202124'>
            <h1>Offline surface test</h1>
            <script>setTimeout(()=>document.body.style.background='white',350)</script>
            </body></html>""")

    def load_ai_fixture():
        from PySide6.QtCore import QUrl

        navigating[0] = True
        overlay.sheet.browser.setHtml(
            """<body style="background:white"><header>Duplicate search header</header>
            <div id="main"><div id="cnt"><div id="top_nav">Duplicate navigation</div>
            <div role="main" id="ai-answer">AI Mode answer remains visible</div>
            <div id="rcnt"><div id="search"></div></div></div></div></body>""",
            QUrl("https://www.google.com/search?udm=50&hl=en"),
        )

        def check_content(ok):
            if overlay.sheet.browser.url().query().find("udm=50") < 0:
                return

            def checked(visible):
                if visible is not True:
                    failures.append("AI Mode answer was hidden by Search header cleanup")

            overlay.sheet.browser.page().runJavaScript(
                "document.getElementById('ai-answer').getBoundingClientRect().height>0 && getComputedStyle(document.querySelector('header')).display==='none'",
                checked,
            )

        overlay.sheet.browser.loadFinished.connect(check_content)

    QTimer.singleShot(100, select)
    QTimer.singleShot(10000, app.quit)
    app.exec()
    if failures:
        print(failures[0], file=sys.stderr)
        return 1
    if completed[0] != 4:
        print("Not all browser transitions completed", file=sys.stderr)
        return 1
    print(
        "Fullscreen geometry, light preference, white loading frames and visible AI Mode content passed; no remote requests."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
