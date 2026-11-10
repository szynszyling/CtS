import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, QRectF, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QCursor, QDesktopServices, QIcon, QImage
from PySide6.QtWidgets import QApplication, QMessageBox

from .geometry import pixel_bounds
from .ocr import default_languages, find_tesseract
from .platforms import get_backend
from .platforms.base import Capture, UnsupportedPlatform
from .results import close_browser_profile
from .ui import SelectionOverlay
from .workers import Task


class Controller(QObject):
    finished = Signal()

    def __init__(self, app, args, *, quit_on_close=True):
        super().__init__()
        self.app, self.args = app, args
        self.desktop = get_backend()
        self.overlays = []
        self.closing = False
        self.pending_dismissals = set()
        self.quit_on_close = quit_on_close

    def start(self):
        if self.closing:
            return
        screens = self.app.screens()
        if not screens:
            self.error("No desktop screen is available.")
            return
        self.current = self.app.screenAt(QCursor.pos()) or self.app.primaryScreen()
        workspace = QRectF()
        for screen in screens:
            workspace = workspace.united(QRectF(screen.geometry()))
        if self.args.image:
            image = QImage(str(self.args.image))
            if image.isNull():
                self.error("Could not read the image: " + str(self.args.image))
            else:
                image.setDevicePixelRatio(1)
                self.captured(Capture(image, QRectF(self.current.geometry())))
            return
        self.task = Task(self.desktop.capture_desktop, workspace, QRectF(self.current.geometry()))
        self.task.signals.done.connect(self.captured)
        self.task.signals.failed.connect(self.error)
        QThreadPool.globalInstance().start(self.task)

    def captured(self, capture):
        if self.closing:
            return
        for screen in self.app.screens():
            screen_rect = screen.geometry()
            geometry = QRectF(screen_rect)
            if capture.screen_images:
                image = capture.screen_images.get((screen_rect.x(), screen_rect.y()))
                if image is None:
                    continue
            else:
                if not capture.geometry.contains(geometry):
                    continue
                source = pixel_bounds(geometry, capture.geometry, capture.image.size())
                image = capture.image.copy(source)
            overlay = SelectionOverlay(
                image,
                screen,
                self.args.mode,
                language=self.args.ocr_language,
                auto_search=self.args.auto_search,
                external=self.args.external,
            )
            overlay.vertical = self.args.vertical
            overlay.selected.connect(self.selected)
            overlay.cancelled.connect(self.quit)
            overlay.externalRequested.connect(self.open_external)
            overlay.ocrSettingsChanged.connect(self.update_ocr)
            self.overlays.append(overlay)
        if not self.overlays:
            self.error("The display layout changed while capturing. Please try again.")
            return
        self.show_overlays()

    def show_overlays(self):
        active = self.overlays[0]
        for overlay in self.overlays:
            overlay.clear_selection()
            overlay.show_overlay()
            overlay.update()
            if overlay.screen() == self.current:
                active = overlay
        active.raise_()
        active.activateWindow()

    def update_ocr(self):
        for overlay in self.overlays:
            overlay.clear_selection()
            overlay.hint.setText("Circle, highlight, scribble or tap to search")
            overlay.hint.adjustSize()
            overlay.start_recognition()

    def selected(self, image, geometry):
        active = self.sender()
        for overlay in self.overlays:
            if overlay is not active:
                overlay.clear_selection()

    def error(self, message):
        if self.closing:
            return
        if sys.stderr is not None:
            print("Circle to Search: " + message, file=sys.stderr)
        QMessageBox.critical(None, "Circle to Search", message)
        self.quit()

    def quit(self, *_):
        if self.closing:
            return
        self.closing = True
        self.pending_dismissals = {overlay for overlay in self.overlays if overlay.isVisible()}
        if not self.pending_dismissals:
            self.finish()
            return
        for overlay in list(self.pending_dismissals):
            overlay.dismissed.connect(lambda overlay=overlay: self.overlay_dismissed(overlay))
            overlay.dismiss()

    def open_external(self, url):
        if self.closing:
            return
        # Dispatch while the click's Wayland activation context is still
        # valid; the exit transition keeps the event loop alive for Qt's
        # asynchronous activation-token request before the overlay disappears.
        if QDesktopServices.openUrl(QUrl(url)):
            self.quit()
        else:
            for overlay in self.overlays:
                if overlay.isVisible():
                    overlay.sheet.error(
                        "Your system could not open this link. Check the default application for this URL."
                    )

    def overlay_dismissed(self, overlay):
        self.pending_dismissals.discard(overlay)
        if not self.pending_dismissals:
            self.finish()

    def finish(self):
        if self.quit_on_close:
            self.app.quit()
        self.finished.emit()


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="circle-to-search",
        description="Circle, highlight, scribble or tap anything on your desktop.",
    )
    parser.add_argument("--mode", choices=("circle", "box"), default="circle")
    parser.add_argument(
        "--ocr-language",
        default=os.environ.get("CTS_OCR_LANGUAGE", default_languages()),
        help="Tesseract languages (default: Japanese and English with bundled models)",
    )
    parser.add_argument("--vertical", action="store_true", help="Recognize vertical Japanese text")
    parser.add_argument(
        "--no-auto-search",
        action="store_false",
        dest="auto_search",
        help="Select and copy locally; search only when you press Enter",
    )
    parser.add_argument(
        "--external",
        action="store_true",
        help="Open results in your browser instead of the overlay",
    )
    parser.add_argument(
        "--image", type=Path, help="Select within a local image instead of capturing the desktop"
    )
    parser.add_argument(
        "--theme",
        choices=("auto", "light", "dark"),
        help="Appearance override (default: saved preference or system theme)",
    )
    parser.add_argument(
        "--ocr-backend",
        choices=("local", "gpu", "server"),
        help="Local Tesseract, local GPU, or your self-hosted OCR server",
    )
    parser.add_argument("--ocr-server", help="OCR server base URL (or CTS_OCR_SERVER)")
    parser.add_argument(
        "--ocr-token-file", type=Path, help="Read the server bearer token from a file"
    )
    parser.add_argument(
        "--resident", action="store_true", help="Windows tray launcher and global shortcut"
    )
    parser.add_argument(
        "--background",
        action="store_true",
        help="Start the Windows tray without opening a selection",
    )
    parser.add_argument("--hotkey", help="Windows global shortcut (default: Meta+Shift+G)")
    args = parser.parse_args(argv)
    if (args.resident or args.background or args.hotkey) and sys.platform != "win32":
        parser.error("Tray and global-hotkey options are supported on Windows only.")
    if args.background:
        args.resident = True
    try:
        desktop = get_backend()
    except UnsupportedPlatform as error:
        parser.error(str(error))
    from .ocr_backend import OcrConfig, configure_ocr, settings_path

    try:
        ocr_config = OcrConfig.load()
        if (
            sys.platform == "win32"
            and not args.ocr_backend
            and not settings_path().exists()
            and "CTS_OCR_BACKEND" not in os.environ
            and not find_tesseract()
        ):
            from .platforms.windows.ocr import available

            if available():
                ocr_config = replace(ocr_config, backend="gpu")
        if args.ocr_backend:
            ocr_config = replace(ocr_config, backend=args.ocr_backend)
        if args.ocr_server:
            ocr_config = replace(ocr_config, server_url=args.ocr_server)
        if args.ocr_token_file:
            ocr_config = replace(ocr_config, token=args.ocr_token_file.read_text().strip())
        configure_ocr(ocr_config)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    from .appearance import ThemeManager, prepare_qt

    prepare_qt()
    app = QApplication([sys.argv[0]])
    app.setApplicationName("circle-to-search")
    app.setApplicationDisplayName("Circle to Search")
    app.setDesktopFileName("io.github.circle_to_search")
    app.setWindowIcon(QIcon.fromTheme("circle-to-search", QIcon.fromTheme("edit-find")))
    if app.windowIcon().isNull():
        app.setWindowIcon(QIcon(str(Path(__file__).with_name("icons") / "app.svg")))
    app.setQuitOnLastWindowClosed(False)
    ThemeManager(app, mode=args.theme)
    lock = QLockFile(str(desktop.instance_lock_path()))
    if not lock.tryLock(0):
        if sys.platform == "win32":
            if args.background:
                return 0
            from .platforms.windows.resident import activate_existing

            if activate_existing():
                return 0
        print("Circle to Search is already open.", file=sys.stderr)
        return 1
    if args.resident:
        from .platforms.windows.resident import Resident

        controller = Resident(app, args)
        if not args.background:
            QTimer.singleShot(0, controller.activate)
    else:
        controller = Controller(app, args)
        QTimer.singleShot(0, controller.start)
    code = app.exec()
    # Workers only handle cropped image data after capture. Wait before destroying
    # Qt signal objects, even when the user closes during OCR or an upload.
    QThreadPool.globalInstance().waitForDone()
    close_browser_profile(app)
    lock.unlock()
    return code
