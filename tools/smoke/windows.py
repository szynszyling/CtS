"""Exercise native capture, OCR, WebEngine and dismissal with synthetic pixels."""

import argparse
import ctypes
import sys
import tempfile
import time
from pathlib import Path
from statistics import median
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PySide6.QtCore import QObject, QPoint, QRectF, QSettings, Qt, QThreadPool, QUrl, Slot
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontDatabase, QImage, QPainter, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from circle_to_search.app import Controller
from circle_to_search.appearance import ThemeManager, prepare_qt
from circle_to_search.ocr import recognize_document
from circle_to_search.ocr_backend import OcrConfig, configure_ocr
from circle_to_search.platforms.base import Capture
from circle_to_search.platforms.windows.capture import capture_desktop, monitor_rectangles
from circle_to_search.platforms.windows.resident import NativeHotkey
from circle_to_search.platforms.windows.surface import WindowsSurface
from tools.fetch_test_font import FONT

JAPANESE = "日本語の文章"


def wait_until(predicate, label, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        QTest.qWait(50)
    raise RuntimeError("Timed out waiting for " + label)


def synthetic_image(width, height):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#f4f6f8"))
    painter = QPainter(image)
    font = QFont("Noto Sans CJK JP")
    font.setPixelSize(34)
    painter.setFont(font)
    painter.drawText(120, 180, "Circle these words")
    painter.drawText(120, 250, JAPANESE)
    painter.end()
    return image


class BrowserHandoff(QObject):
    def __init__(self):
        super().__init__()
        self.urls = []

    @Slot(QUrl)
    def receive(self, url):
        self.urls.append(url.toString())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gpu", help="Also verify the selected native Vulkan GPU (for example AMD)"
    )
    parser.add_argument("--fixture", type=Path, help="Write a synthetic image for manual UI checks")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Run this test on an interactive Windows desktop.")
    prepare_qt()
    app = QApplication([])
    app.setApplicationName("circle-to-search-windows-smoke")
    app.setQuitOnLastWindowClosed(False)
    if QFontDatabase.addApplicationFont(str(FONT)) < 0:
        parser.error("Run python tools/fetch_test_font.py first.")
    screen = app.primaryScreen()
    origin = screen.geometry().x(), screen.geometry().y()
    monitors = {rectangle[:2]: rectangle[2:] for rectangle in monitor_rectangles().values()}
    width, height = monitors[origin]
    image = synthetic_image(width, height)
    if args.fixture:
        if not image.save(str(args.fixture)):
            raise RuntimeError("Could not save the synthetic fixture.")
        return 0
    with tempfile.TemporaryDirectory(prefix="cts-windows-smoke-") as directory:
        theme = ThemeManager(
            app,
            mode="light",
            settings=QSettings(str(Path(directory) / "theme.ini"), QSettings.IniFormat),
        )
        fixture = QLabel()
        fixture.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        fixture.setScreen(screen)
        fixture.setGeometry(screen.geometry())
        fixture.setPixmap(QPixmap.fromImage(image))
        fixture.setScaledContents(True)
        surface = WindowsSurface(fixture)
        fixture.show()
        wait_until(lambda: fixture.windowHandle().isExposed(), "test window to become visible")
        QTest.qWait(300)
        frame = capture_desktop(QRectF(screen.geometry()), QRectF(screen.geometry())).screen_images[
            origin
        ]
        assert frame.size() == image.size(), (frame.size(), image.size())
        assert frame.pixelColor(50, 50) == image.pixelColor(50, 50), (
            "Capture did not match the test window"
        )
        print(
            f"Native capture: {screen.name()}, {width} × {height}, scale {screen.devicePixelRatio()}",
            flush=True,
        )
        fixture.hide()
        if args.gpu:
            configure_ocr(OcrConfig("gpu", local_gpu_name=args.gpu))
            result = recognize_document(frame.copy(80, 120, 700, 165), priority="interactive")
            assert "Circle these words" in result.text(), repr(result.text())
            assert JAPANESE in result.text(), repr(result.text())
            print("Native Vulkan worker recognized English and Japanese.", flush=True)
        configure_ocr(OcrConfig())
        controller = Controller(
            app,
            SimpleNamespace(
                mode="circle",
                vertical=False,
                ocr_language="jpn+eng",
                external=False,
                auto_search=False,
            ),
            quit_on_close=False,
        )
        controller.current = screen
        controller.captured(Capture(QImage(), QRectF(screen.geometry()), {origin: frame}))
        overlay = controller.overlays[0]
        wait_until(lambda: not overlay.ocr_pending, "local recognition")
        assert overlay.geometry() == screen.geometry(), (overlay.geometry(), screen.geometry())
        text = overlay.document.text()
        assert JAPANESE in text, repr(text)
        indices = [i for i, glyph in enumerate(overlay.document.glyphs) if glyph.text in JAPANESE]
        glyphs = [overlay.document.glyphs[index] for index in indices]
        baseline = round(median(glyph.rect.bottom() for glyph in glyphs) + 2)
        left = QPoint(round(glyphs[0].rect.center().x()), baseline)
        right = QPoint(round(glyphs[-1].rect.center().x()), baseline)
        QTest.mousePress(overlay, Qt.LeftButton, pos=left)
        for glyph in glyphs:
            QTest.mouseMove(overlay, QPoint(round(glyph.rect.center().x()), baseline))
        QTest.mouseRelease(overlay, Qt.LeftButton, pos=right)
        wait_until(lambda: overlay.selection is not None, "Japanese underline selection")
        assert overlay.selection.text == JAPANESE, repr(overlay.selection.text)
        assert overlay.text_actions.isVisible()
        print("Full-screen overlay and real Japanese underline selection passed.", flush=True)

        pressed = []
        hotkey = NativeHotkey(app, lambda: pressed.append(True))
        try:
            hotkey.set_sequence("Meta+Shift+G")
            thread = ctypes.windll.kernel32.GetCurrentThreadId()
            assert ctypes.windll.user32.PostThreadMessageW(thread, 0x0312, hotkey.identifier, 0)
            wait_until(lambda: pressed, "registered hotkey message")
        finally:
            hotkey.close()
        print("Windows global shortcut registration and dispatch passed.", flush=True)

        sheet = overlay.sheet
        sheet.ensure_browser()
        sheet.show_sheet(False)
        browser = sheet.browser
        loaded = []
        browser.loadFinished.connect(loaded.append)
        browser.setHtml(
            '<h1>Offline result</h1><a href="https://example.invalid/cts-fixture">Open result</a>'
        )
        wait_until(lambda: loaded, "embedded browser to render")
        assert loaded[-1]
        for mode in ("dark", "light"):
            theme.set_mode(mode)
            dark = []
            QTest.qWait(300)
            browser.page().runJavaScript(
                "matchMedia('(prefers-color-scheme: dark)').matches", dark.append
            )
            wait_until(lambda: dark, "WebEngine color scheme")
            assert dark[-1] == (mode == "dark"), (mode, dark)
        handoff = BrowserHandoff()
        QDesktopServices.setUrlHandler("https", handoff, "receive")
        try:
            browser.page().runJavaScript("document.querySelector('a').click()")
            wait_until(
                lambda: handoff.urls and not overlay.isVisible(), "external link and dismissal"
            )
            assert handoff.urls == ["https://example.invalid/cts-fixture"]
        finally:
            QDesktopServices.unsetUrlHandler("https")
        print("Embedded WebEngine, both themes and default-browser handoff passed.", flush=True)
        QThreadPool.globalInstance().waitForDone()
        fixture.close()
        overlay.close()
        del surface
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
