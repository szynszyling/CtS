import subprocess
import sys
import unittest

from circle_to_search.platforms import get_backend
from circle_to_search.platforms.base import UnsupportedPlatform


class PlatformTests(unittest.TestCase):
    def test_linux_selects_the_kde_implementation(self):
        backend = get_backend("linux")
        self.assertEqual(backend.name, "KDE Plasma")
        self.assertEqual(backend.theme_source().label, "Plasma")

    def test_unimplemented_ports_fail_clearly_without_linux_imports(self):
        for name in ("win32", "darwin"):
            with (
                self.subTest(platform=name),
                self.assertRaisesRegex(UnsupportedPlatform, "not available"),
            ):
                get_backend(name)
        code = """
import sys
from circle_to_search.platforms import get_backend
try:
    get_backend('win32')
except RuntimeError:
    pass
else:
    raise AssertionError('An unimplemented port was selected')
assert not any(name.startswith('circle_to_search.platforms.linux') for name in sys.modules)
"""
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=10
        )
        self.assertEqual(result.returncode, 0, result.stderr)
