import tempfile
import unittest
from pathlib import Path

from tools.clean import clean


class CleanupTests(unittest.TestCase):
    def test_cleanup_removes_generated_files_and_preserves_models_and_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated = root / "build/lib/obsolete.py"
            generated.parent.mkdir(parents=True)
            generated.write_text("stale build")
            nested_cache = root / "server/build/__pycache__"
            nested_cache.mkdir(parents=True)
            (nested_cache / "old.pyc").write_bytes(b"stale backend build")
            cache = root / "circle_to_search/__pycache__"
            cache.mkdir(parents=True)
            (cache / "obsolete.pyc").write_bytes(b"cache")
            model = root / "circle_to_search/tessdata/eng.traineddata"
            model.parent.mkdir()
            model.write_bytes(b"downloaded model")
            config = root / "server/.env"
            config.parent.mkdir(exist_ok=True)
            config.write_text("private settings")
            protected = root / "tools/.venv/__pycache__"
            protected.mkdir(parents=True)
            (protected / "keep.pyc").write_bytes(b"environment cache")
            self.assertIn(root / "build", clean(root, dry_run=True))
            self.assertTrue(generated.exists())
            clean(root)
            self.assertFalse(generated.exists())
            self.assertFalse(cache.exists())
            self.assertFalse((root / "server/build").exists())
            self.assertEqual(model.read_bytes(), b"downloaded model")
            self.assertEqual(config.read_text(), "private settings")
            self.assertTrue(protected.exists())

    def test_cleanup_unlinks_a_generated_directory_symlink_without_following_it(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            preserved = Path(outside) / "user-file"
            preserved.write_text("keep")
            (root / "build").symlink_to(outside, target_is_directory=True)
            clean(root)
            self.assertFalse((root / "build").exists())
            self.assertEqual(preserved.read_text(), "keep")
