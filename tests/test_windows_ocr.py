import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from circle_to_search.ocr_backend import OcrConfig
from circle_to_search.platforms.windows import ocr


@unittest.skipUnless(sys.platform == "win32", "Windows native worker")
class WindowsOcrTests(unittest.TestCase):
    def test_language_change_prepares_a_new_worker_and_failed_download_keeps_the_old_one(self):
        connection = OcrConfig("server")
        process = Mock()
        process.poll.return_value = None
        with (
            patch.object(ocr, "_PROCESS", process),
            patch.object(ocr, "_CONNECTION", connection),
            patch.object(ocr, "_GPU", "AMD"),
            patch.object(ocr, "_LANGUAGES", ("eng",)),
            patch.object(ocr, "available", return_value=True),
            patch.object(ocr, "prepare_model_selection") as prepare,
            patch.object(ocr, "stop_worker") as stop,
            patch.object(ocr, "start_worker", return_value=(connection, {})) as start,
        ):
            config = OcrConfig("gpu", local_gpu_name="AMD")
            self.assertEqual(ocr.ensure_local(config, ("eng",)), connection)
            prepare.assert_not_called()
            prepare.side_effect = OSError("offline")
            with self.assertRaisesRegex(RuntimeError, "selected GPU models"):
                ocr.ensure_local(config, ("pol",))
            stop.assert_not_called()
            prepare.side_effect = None
            prepare.return_value = Path("selected-models")
            ocr.ensure_local(config, ("pol",))
            stop.assert_called_once()
            self.assertEqual(start.call_args.args[-1], ("pol",))

    def test_cached_bundle_must_match_selected_languages_and_file_hashes(self):
        from cts_ocr_server.bundle import ready_bundle

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            model = directory / "latin.ncnn.bin"
            model.write_bytes(b"verified model")
            manifest = {
                "profile": "local",
                "languages": ["pol"],
                "files": {model.name: hashlib.sha256(model.read_bytes()).hexdigest()},
            }
            (directory / "bundle.json").write_text(json.dumps(manifest))
            self.assertTrue(ready_bundle(directory, ("pol",)))
            self.assertFalse(ready_bundle(directory, ("rus",)))
            model.write_bytes(b"incomplete download")
            self.assertFalse(ready_bundle(directory, ("pol",)))
