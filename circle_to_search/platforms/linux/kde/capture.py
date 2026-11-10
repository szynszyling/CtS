"""Capture through Spectacle, which already has KDE's Wayland permissions."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage

from ...base import Capture


def capture_desktop(workspace: QRectF, current_screen: QRectF) -> Capture:
    binary = shutil.which("spectacle")
    if not binary:
        raise RuntimeError("Install KDE Spectacle to capture your desktop.")
    try:
        help_result = subprocess.run(
            [binary, "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        )
        scaled = "--scaled" in help_result.stdout
        # Older Spectacle versions have incompatible mixed-DPI workspace layouts.
        # Capturing only the pointer's screen avoids guessing their pixel geometry.
        geometry = workspace if scaled else current_screen
        mode = ["--fullscreen", "--scaled"] if scaled else ["--current"]
        with tempfile.TemporaryDirectory(prefix="circle-to-search-") as directory:
            output = Path(directory) / "desktop.png"
            result = subprocess.run(
                [
                    binary,
                    "--new-instance",
                    "--background",
                    "--nonotify",
                    *mode,
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
                timeout=25,
            )
            image = QImage(str(output))
            if result.returncode or image.isNull():
                detail = result.stderr.strip()[-800:]
                raise RuntimeError("Spectacle could not capture the screen. " + detail)
            # PNG metadata may contain a DPR. All our mappings use raw pixel sizes.
            image.setDevicePixelRatio(1)
        return Capture(image, QRectF(geometry))
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "Screen capture timed out. Check that Spectacle works in your Plasma session."
        ) from exc
