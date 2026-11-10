"""Exercise real browser/native themes and live Plasma changes, entirely offline."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PySide6.QtCore import QPoint, QRect, QSettings, QTimer, QUrl
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from circle_to_search.appearance import ThemeManager, prepare_qt
from circle_to_search.ocr import Document
from circle_to_search.platforms.linux.kde.theme import PlasmaThemeSource
from circle_to_search.ui import SelectionOverlay


def main():
    prepare_qt()
    app = QApplication([])
    app.setApplicationName("circle-to-search-theme-check")
    temporary = tempfile.TemporaryDirectory(prefix="cts-theme-")
    root = Path(temporary.name)
    kde = root / "kdeglobals"
    kde.write_text("[Colors:Window]\nBackgroundNormal=#202124\n")
    manager = ThemeManager(
        app,
        mode="light",
        settings=QSettings(str(root / "appearance.ini"), QSettings.IniFormat),
        source=PlasmaThemeSource(kde),
    )
    image = QImage(app.primaryScreen().size(), QImage.Format_RGB32)
    image.fill(QColor("#254c34"))
    overlay = SelectionOverlay(
        image, app.primaryScreen(), document=Document([]), start_ocr=False, auto_search=False
    )
    overlay.cancelled.connect(app.quit)
    overlay.show_overlay()
    sheet = overlay.sheet
    sheet.loading()
    sheet.bar.query.setText("Offline theme fixture")
    sheet.ensure_browser()
    browser = sheet.browser
    failures = []
    stage = [0]
    stages = (
        "light",
        "dark",
        "light",
        "auto-dark",
        "auto-light",
        "manual-dark",
        "manual-ignores-plasma",
        "auto-resumes",
    )
    frames = [0]
    sample_frames = [False]
    output = Path("/tmp/circle-to-search-previews")
    output.mkdir(exist_ok=True)

    def fail(message):
        failures.append(message)
        print(message, file=sys.stderr, flush=True)
        app.quit()

    def close_color(actual, expected):
        expected = QColor(expected)
        return (
            max(
                abs(actual.red() - expected.red()),
                abs(actual.green() - expected.green()),
                abs(actual.blue() - expected.blue()),
            )
            <= 3
        )

    def sample():
        if not sample_frames[0]:
            return
        frames[0] += 1
        pixel = sheet.content.grab(QRect(0, 0, 8, 8)).toImage().pixelColor(3, 3)
        if not close_color(pixel, manager.theme.background):
            fail(
                "Wrong-theme frame at "
                + stages[stage[0]]
                + ": "
                + pixel.name()
                + " expected "
                + manager.theme.background
            )

    timer = QTimer()
    timer.timeout.connect(sample)
    timer.start(20)

    def inspect():
        def checked(raw):
            if failures:
                return
            metrics = json.loads(raw)
            expected = manager.theme
            if (
                metrics["dark"] != expected.dark
                or metrics["background"] != QColor(expected.background).name()
            ):
                fail("Browser theme did not follow native controls: " + str(metrics))
                return
            if sheet.content.currentWidget() != browser:
                fail("Loading cover did not reveal the correctly themed browser")
                return
            # The source image must retain its red pixels in either theme.
            picture = metrics["image"]
            sample = browser.grab().toImage().pixelColor(round(picture["x"]), round(picture["y"]))
            if not close_color(sample, "#ea4335"):
                fail("The page image was recolored: " + sample.name())
                return
            popup = overlay.text_actions
            popup.show_at(sheet.pos() + QPoint(100, 150), animate=False)
            app.processEvents()
            if not close_color(popup.grab().toImage().pixelColor(9, 21), expected.background):
                fail("Selection popup background is transparent or has the wrong theme")
                return
            divider = popup.divider.grab().toImage().pixelColor(0, 10)
            if not close_color(divider, expected.border):
                fail("Selection popup divider has the wrong theme: " + divider.name())
                return
            if not close_color(sheet.bar.grab().toImage().pixelColor(75, 10), expected.surface):
                fail("Search field did not adopt the selected theme")
                return
            print(
                stages[stage[0]],
                "passed; web background:",
                metrics["background"],
                "Plasma mode:",
                manager.mode,
                flush=True,
            )
            overlay.grab().save(str(output / ("theme-" + stages[stage[0]] + ".png")))
            if stage[0] == len(stages) - 1:
                app.quit()
                return
            stage[0] += 1
            next_stage = stages[stage[0]]
            if next_stage in ("dark", "light"):
                manager.set_mode(next_stage)
            elif next_stage == "auto-dark":
                manager.set_mode("auto")
            elif next_stage == "auto-light":
                replacement = root / "replacement"
                replacement.write_text("[Colors:Window]\nBackgroundNormal=255,255,255\n")
                replacement.replace(kde)
            elif next_stage == "manual-dark":
                manager.set_mode("dark")
            elif next_stage == "manual-ignores-plasma":
                kde.write_text("[Colors:Window]\nBackgroundNormal=#303134\n")
                # A second change to light checks explicit override survives it.
                QTimer.singleShot(
                    180, lambda: kde.write_text("[Colors:Window]\nBackgroundNormal=250,250,250\n")
                )
            elif next_stage == "auto-resumes":
                manager.set_mode("auto")
            QTimer.singleShot(650, inspect)

        browser.page().runJavaScript(
            r"""JSON.stringify({dark:matchMedia('(prefers-color-scheme:dark)').matches,
            image:(()=>{const r=document.querySelector('img').getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})(),
            background:'#'+getComputedStyle(document.body).backgroundColor.match(/\d+/g).slice(0,3).map(n=>Number(n).toString(16).padStart(2,'0')).join('')})""",
            checked,
        )

    def loaded(ok):
        if not ok:
            fail("Offline fixture failed to load")
            return
        sample_frames[0] = True
        QTimer.singleShot(450, inspect)

    browser.loadFinished.connect(loaded)
    browser.setHtml(
        """<!doctype html><style>
        :root{color-scheme:light dark}body{margin:0;background:#ffffff;color:#202124}
        @media(prefers-color-scheme:dark){body{background:#22242a;color:#e8eaed}}
        main{padding:24px} img{width:80px;height:80px}
        </style><main><h2>Offline Google-style theme check</h2><p>Native controls and browser use the same theme.</p>
        <img src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='80'%3E%3Crect width='80' height='80' fill='%23ea4335'/%3E%3C/svg%3E"></main>""",
        QUrl("about:blank"),
    )
    QTimer.singleShot(12000, lambda: fail("Theme check timed out"))
    app.exec()
    overlay.hide()
    manager.watcher.blockSignals(True)
    temporary.cleanup()
    if failures or stage[0] != len(stages) - 1:
        return 1
    print(
        "Native/browser light, dark, live automatic switching and opaque popup passed;",
        frames[0],
        "frames checked.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
