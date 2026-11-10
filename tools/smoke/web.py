"""Verify embedded text/Lens results using synthetic input in a live session."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PySide6.QtCore import QRect, QRectF, QSettings, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from circle_to_search.appearance import ThemeManager, prepare_qt
from circle_to_search.geometry import pixel_bounds
from circle_to_search.ocr import Document, Glyph, encode_png
from circle_to_search.platforms import get_backend
from circle_to_search.search import normalize_search_url, translation_url
from circle_to_search.ui import SelectionOverlay


def main():
    prepare_qt()
    app = QApplication([])
    app.setApplicationName("circle-to-search")
    temporary = tempfile.TemporaryDirectory(prefix="cts-web-theme-")
    mode = "dark" if "--dark" in sys.argv else "auto" if "--auto" in sys.argv else "light"
    appearance = ThemeManager(
        app,
        mode=mode,
        settings=QSettings(str(Path(temporary.name) / "appearance.ini"), QSettings.IniFormat),
    )
    print("Web check theme:", appearance.theme.name, "mode:", appearance.mode, flush=True)
    screen = app.primaryScreen()
    workspace = QRectF()
    for item in app.screens():
        workspace = workspace.united(QRectF(item.geometry()))
    capture = get_backend().capture_desktop(workspace, QRectF(screen.geometry()))
    image = capture.image.copy(
        pixel_bounds(QRectF(screen.geometry()), capture.geometry, capture.image.size())
    )
    text_rect = QRectF(screen.geometry().width() / 2 - 120, 180, 240, 28)
    document = Document([Glyph("日本語 meaning", text_rect, "test-line", "test-word")])
    parent = SelectionOverlay(image, screen, document=document, start_ocr=False, auto_search=True)
    parent.cancelled.connect(app.quit)
    parent.bar.hide()
    parent.hint.hide()
    sheet = parent.sheet
    sheet.bar.set_selection(text="日本語 meaning")
    parent.show_overlay()
    failures = []
    observed_sizes = set()
    geometry_timer = QTimer()

    def observe_geometry():
        size = (parent.width(), parent.height())
        if size not in observed_sizes:
            print("Overlay geometry:", size, "screen:", screen.geometry().size(), flush=True)
            observed_sizes.add(size)
        if parent.size() != screen.geometry().size():
            fail("The overlay stopped covering the full screen")
        if sheet.isVisible() and not sheet.verification.isVisible():
            pixel = sheet.content.grab(QRect(0, 0, 6, 6)).toImage().pixelColor(3, 3)
            if (
                max(pixel.red(), pixel.green(), pixel.blue()) > 180
                if appearance.theme.dark
                else min(pixel.red(), pixel.green(), pixel.blue()) < 190
            ):
                fail("An opposite-theme browser frame was visible during a search/tab transition")

    geometry_timer.timeout.connect(observe_geometry)
    geometry_timer.start(20)
    translate_only = "--translate-only" in sys.argv
    text_only = "--text-only" in sys.argv
    lens_only = "--lens-only" in sys.argv
    stage = ["translate" if translate_only else "lens" if lens_only else "text"]
    lens_checks = [0]
    theme_cycled = [False]
    output = Path("/tmp/circle-to-search-previews")
    output.mkdir(exist_ok=True)

    def fail(message):
        failures.append(message)
        print(message, file=sys.stderr, flush=True)
        app.quit()

    def inspect_page(ok):
        if not ok:

            def check_failure():
                if sheet.last_error_code == 403:
                    fail(
                        "Google denied the request (HTTP 403); there is no verification to complete"
                    )
                elif sheet.last_error_code >= 400:
                    print(
                        "Google requires verification; the page will stay open for you to complete it.",
                        flush=True,
                    )
                    timeout.stop()
                else:
                    fail("Google results failed to load")

            QTimer.singleShot(0, check_failure)
            return
        url = sheet.browser.url()
        if QUrl(normalize_search_url(url.toString())) != url:
            return  # the native sheet is reloading with the requested preferences
        if url.host().endswith("google.com") and (
            url.path().startswith("/sorry") or url.host().startswith("consent.")
        ):
            print("Google verification is open; complete it in the window to continue.", flush=True)
            timeout.stop()
            return
        translating = stage[0] == "translate" and url.host() == "translate.google.com"
        if not translating and (url.host() != "www.google.com" or url.path() != "/search"):
            fail("Google returned " + url.host() + url.path() + " instead of search results")
            return

        def inspect_text(text):
            if stage[0] == "done":
                return
            if len(text) < 100:
                fail("Google result page was unexpectedly empty")
                return
            print("Embedded", stage[0], "results loaded;", len(text), "text characters", flush=True)
            if stage[0] != "translate" and not all(
                control.isVisible() for control in sheet.tabs.buttons.values()
            ):
                fail("A native search tab disappeared in the current view")
                return
            snapshot = sheet.grab()
            snapshot.save(str(output / ("live-" + stage[0] + "-results.png")))
            snapshot.save(
                str(output / ("live-" + stage[0] + "-" + appearance.theme.name + "-results.png"))
            )
            if text_only:
                stage[0] = "done"
                QTimer.singleShot(250, app.quit)
                return
            if stage[0] in ("text", "images"):
                tab = {"text": "images", "images": "videos"}[stage[0]]
                stage[0] = {"text": "images", "images": "videos"}[stage[0]]
                sheet.tabs.buttons[tab].click()
            elif stage[0] == "videos":
                stage[0] = "lens"
                image = QImage("/tmp/cts-references/lens-eiffel.jpg")
                if image.isNull():
                    fail("Download the public Eiffel Tower fixture before the browser check")
                    return
                sheet.bar.set_selection(image)
                sheet.search_image(encode_png(image))
            elif stage[0] == "lens":

                def validate(metrics):
                    if isinstance(metrics, str):
                        metrics = json.loads(metrics) if metrics else {}
                    print("Lens content check:", metrics, flush=True)
                    if metrics.get("images", 0) < 3 or "eiffel" not in text.lower():
                        lens_checks[0] += 1
                        if lens_checks[0] < 8:
                            QTimer.singleShot(
                                2000, lambda: sheet.browser.page().toPlainText(inspect_text)
                            )
                            return
                        sheet.browser.page().toHtml(
                            lambda html: (output / "lens-debug.html").write_text(html)
                        )
                        fail(
                            "Lens page loaded but did not return visual matches for the landmark test photo"
                        )
                        return
                    if metrics.get("lang", "").split("-")[0] != "en" or not metrics.get(
                        "themeMatches"
                    ):
                        fail("Google did not apply the requested English/selected appearance")
                        return
                    stage[0] = "translate"
                    sheet.load_url(translation_url("こんにちは"))

                sheet.browser.page().runJavaScript(
                    """JSON.stringify({lang:document.documentElement.lang,themeMatches:matchMedia('(prefers-color-scheme:dark)').matches===THEME_DARK,background:document.body?getComputedStyle(document.body).backgroundColor:'pending',images:[...document.images].filter(i=>i.naturalWidth>=80 && i.naturalHeight>=60).length})""".replace(
                        "THEME_DARK", "true" if appearance.theme.dark else "false"
                    ),
                    validate,
                )
            elif stage[0] == "translate":
                if "--cycle-theme" in sys.argv and not theme_cycled[0]:
                    theme_cycled[0] = True
                    appearance.set_mode("light" if appearance.theme.dark else "dark")
                    return
                if sheet.tabs.isVisible():
                    fail("Search tabs should not be added to the Translate interface")
                    return
                stage[0] = "done"
                QTimer.singleShot(250, app.quit)

        def inspect_chrome(raw):
            if sheet.content.currentWidget() != sheet.browser:
                QTimer.singleShot(
                    300, lambda: sheet.browser.page().runJavaScript(chrome_script, inspect_chrome)
                )
                return
            metrics = json.loads(raw) if isinstance(raw, str) and raw else {}
            print(
                stage[0],
                "appearance:",
                metrics.get("background"),
                "dark preference:",
                metrics.get("darkMedia"),
                flush=True,
            )
            if (
                metrics.get("darkMedia") != appearance.theme.dark
                or metrics.get("bodyDark") != appearance.theme.dark
            ):
                fail("Browser preference or page appearance disagrees with native theme")
                return
            if len(metrics.get("legacyTabs", [])) >= 3:
                fail("Google's variable navigation is still visible: " + str(metrics["legacyTabs"]))
                return
            if metrics.get("duplicateTools", 0):
                fail("Google's duplicate Tools control is still visible")
                return
            if stage[0] == "translate":
                print("Translate header check:", metrics, flush=True)
                if metrics.get("backgroundHex") != appearance.theme.background:
                    fail(
                        "Translate's background does not match the surrounding sheet: "
                        + str(metrics.get("backgroundHex"))
                    )
                    return
                if (
                    appearance.theme.dark
                    and metrics.get("headerBackgroundHex") != appearance.theme.background
                ):
                    fail(
                        "Translate's header does not match the surrounding sheet: "
                        + str(metrics.get("headerBackgroundHex"))
                    )
                    return
                if (
                    appearance.theme.dark
                    and metrics.get("containerSurface") != appearance.theme.surface
                ):
                    fail("Translate's panel color does not match the app's surface palette")
                    return
                if metrics.get("accountControls", 0) or not metrics.get("textInputs", 0):
                    fail("Translate account controls are visible or translation inputs were hidden")
                    return
            sheet.browser.page().toPlainText(inspect_text)

        chrome_script = r"""JSON.stringify((()=>{
            const visible=e=>{const r=e.getBoundingClientRect();return r.width>0 && r.height>0 && getComputedStyle(e).visibility!=='hidden'};
            const labels=new Set(['ai mode','all','images','videos','shopping','news','forums']);
            const legacyTabs=[...new Set([...document.querySelectorAll('a[href]')].filter(visible).filter(e=>e.getBoundingClientRect().top+scrollY<200).map(e=>e.textContent.trim().toLowerCase()).filter(n=>labels.has(n)))];
            const controls=[...document.querySelectorAll('[aria-label="Google apps"],a[href*="accounts.google.com/ServiceLogin"],a[href*="accounts.google.com/v3/signin"]')].filter(visible);
            const textInputs=[...document.querySelectorAll('textarea,[role="textbox"]')].filter(visible).length;
            const duplicateTools=[...document.querySelectorAll('#hdtb-tls')].filter(visible).length;
            const body=getComputedStyle(document.body);
            const backgroundHex='#'+body.backgroundColor.match(/[\d.]+/g).slice(0,3).map(n=>Number(n).toString(16).padStart(2,'0')).join('');
            const containerSurface=body.getPropertyValue('--gm3-sys-color-surface-container').trim();
            const header=document.querySelector('#gb,header,[role="banner"]');
            const headerChannels=header && getComputedStyle(header).backgroundColor.match(/[\d.]+/g);
            const headerBackgroundHex=headerChannels && '#'+headerChannels.slice(0,3).map(n=>Number(n).toString(16).padStart(2,'0')).join('');
            return {headerBackgroundHex,backgroundHex,containerSurface,legacyTabs,accountControls:controls.length,textInputs,duplicateTools,background:getComputedStyle(document.body).backgroundColor,darkMedia:matchMedia('(prefers-color-scheme:dark)').matches,bodyDark:(getComputedStyle(document.body).backgroundColor.match(/[\d.]+/g)||[]).slice(0,3).reduce((sum,n)=>sum+Number(n),0)<384};
        })())"""
        QTimer.singleShot(
            1500, lambda: sheet.browser.page().runJavaScript(chrome_script, inspect_chrome)
        )

    if translate_only:
        sheet.expanded = True
        sheet.sheet_height = parent.height() - 84
        sheet.loading("Translating…")
        sheet.load_url(translation_url("こんにちは"))
    elif lens_only:
        image = QImage("/tmp/cts-references/lens-eiffel.jpg")
        if image.isNull():
            print(
                "Download the public Eiffel Tower fixture before the browser check", file=sys.stderr
            )
            return 1
        sheet.bar.set_selection(image)
        sheet.search_image(encode_png(image))
    else:
        parent.finish_gesture([text_rect.center()], False)
    sheet.browser.loadFinished.connect(inspect_page)

    def loading_info(info):
        if info.errorCode() >= 400 or info.errorCode() < 0:
            print(
                "Embedded browser load detail:",
                info.errorCode(),
                info.errorString(),
                info.url().host(),
                info.url().path(),
                info.errorDomain(),
                flush=True,
            )

    sheet.browser.page().loadingChanged.connect(loading_info)
    sheet.browser.page().navigationRequested.connect(
        lambda req: print(
            "Navigation:", req.url().host(), req.url().path(), req.isMainFrame(), flush=True
        )
    )
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(lambda: fail("Timed out loading embedded results"))
    timeout.start(45000)
    app.exec()
    QThreadPool.globalInstance().waitForDone()
    if failures or stage[0] != "done":
        return 1
    print(
        "Embedded Translate controls passed."
        if translate_only
        else "Embedded text search and consistent navigation passed."
        if text_only
        else "Embedded Lens upload and Translate controls passed."
        if lens_only
        else "Embedded text search, consistent tabs, browser-session Lens upload and Translate controls passed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
