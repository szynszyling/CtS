import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from circle_to_search.platforms.linux.kde import installer as install


@unittest.skipUnless(sys.platform.startswith("linux"), "KDE installer requires Linux")
class InstallTests(unittest.TestCase):
    @patch("circle_to_search.platforms.linux.kde.installer.register_shortcut")
    def test_staged_launcher_runs_from_path_with_spaces_without_desktop_mutation(self, register):
        with tempfile.TemporaryDirectory(prefix="cts stage ") as directory:
            target = Path(directory) / "share/circle-to-search"
            old_package = target / "circle_to_search"
            (old_package / "icons").mkdir(parents=True)
            (old_package / "desktop.py").write_text("obsolete = True\n")
            (old_package / "icons/google.svg").write_text("<svg/>")
            profile = target / "QtWebEngine"
            profile.mkdir()
            (profile / "user-data").write_text("keep this browser session")
            (target / "server").mkdir()
            (target / "server/.env").write_text("private user settings")
            with contextlib.redirect_stdout(io.StringIO()):
                launcher = install.install(Path(directory))
            result = subprocess.run(
                [str(launcher), "--help"], cwd="/tmp", capture_output=True, text=True, timeout=10
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Circle, highlight", result.stdout)
            backend = Path(directory) / "share/circle-to-search/server"
            self.assertTrue((backend / "Dockerfile").is_file())
            self.assertEqual(
                (target / "LICENSE").read_text(), (install.SOURCE / "LICENSE").read_text()
            )
            self.assertTrue((target / "THIRD_PARTY.md").is_file())
            self.assertTrue((backend / "LICENSE").is_file())
            self.assertTrue((backend / "licenses/Apache-2.0.txt").is_file())
            self.assertTrue((backend / "cts_ocr_server/models.json").is_file())
            self.assertEqual((backend / ".env").read_text(), "private user settings")
            self.assertFalse((old_package / "desktop.py").exists())
            self.assertFalse((old_package / "icons/google.svg").exists())
            self.assertEqual((profile / "user-data").read_text(), "keep this browser session")
            desktop = Path(directory) / "share/applications" / install.DESKTOP_ID
            self.assertIn(f'Exec="{launcher}"', desktop.read_text())
            if shutil.which("desktop-file-validate"):
                result = subprocess.run(
                    ["desktop-file-validate", str(desktop)], capture_output=True, text=True
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        register.assert_not_called()
