import contextlib
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import install


class InstallTests(unittest.TestCase):
    @patch("install.register_shortcut")
    def test_staged_launcher_runs_from_path_with_spaces_without_desktop_mutation(self, register):
        with tempfile.TemporaryDirectory(prefix="cts stage ") as directory:
            with contextlib.redirect_stdout(io.StringIO()):
                launcher = install.install(Path(directory))
            result = subprocess.run([str(launcher), "--help"], cwd="/tmp", capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Circle, highlight", result.stdout)
            backend = Path(directory) / "share/circle-to-search/server"
            self.assertTrue((backend / "Dockerfile").is_file())
            self.assertTrue((backend / "cts_ocr_server/models.json").is_file())
            self.assertFalse((backend / ".env").exists())
            desktop = Path(directory) / "share/applications" / install.DESKTOP_ID
            self.assertIn(f'Exec="{launcher}"', desktop.read_text())
            if shutil.which("desktop-file-validate"):
                result = subprocess.run(["desktop-file-validate", str(desktop)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        register.assert_not_called()
