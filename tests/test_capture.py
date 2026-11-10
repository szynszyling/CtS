import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage

from circle_to_search.capture import capture_desktop


class CaptureTests(unittest.TestCase):
    def run_capture(self, scaled):
        calls = []
        paths = []

        def run(command, **kwargs):
            calls.append(command)
            if "--help" in command:
                return subprocess.CompletedProcess(command, 0, "--scaled" if scaled else "", "")
            output = Path(command[command.index("--output") + 1])
            paths.append(output)
            image = QImage(100, 100, QImage.Format.Format_RGB32)
            image.fill(0)
            image.save(str(output))
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch("circle_to_search.capture.shutil.which", return_value="/usr/bin/spectacle"), patch("circle_to_search.capture.subprocess.run", side_effect=run):
            capture = capture_desktop(QRectF(-100, 0, 200, 100), QRectF(0, 0, 100, 100))
        self.assertFalse(paths[0].exists(), "Full desktop capture must be removed before preview")
        self.assertFalse(capture.image.isNull(), "Image must survive deletion of its PNG")
        return capture, calls[-1]

    def test_current_spectacle_captures_scaled_workspace(self):
        capture, command = self.run_capture(True)
        self.assertEqual(capture.geometry, QRectF(-100, 0, 200, 100))
        self.assertIn("--scaled", command)
        self.assertIn("--nonotify", command)

    def test_older_spectacle_uses_pointer_monitor(self):
        capture, command = self.run_capture(False)
        self.assertEqual(capture.geometry, QRectF(0, 0, 100, 100))
        self.assertIn("--current", command)
        self.assertNotIn("--scaled", command)

    @patch("circle_to_search.capture.shutil.which", return_value=None)
    def test_missing_spectacle(self, _):
        with self.assertRaisesRegex(RuntimeError, "Install KDE Spectacle"):
            capture_desktop(QRectF(), QRectF())

    @patch("circle_to_search.capture.shutil.which", return_value="spectacle")
    @patch("circle_to_search.capture.subprocess.run", side_effect=subprocess.TimeoutExpired("spectacle", 25))
    def test_capture_timeout(self, *_):
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            capture_desktop(QRectF(), QRectF())
