import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from circle_to_search.ocr_backend import OcrConfig, configure_ocr, current_config
from circle_to_search.ocr_settings import OcrSettingsDialog

APP = QApplication.instance() or QApplication([])


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.previous = current_config()
        configure_ocr(OcrConfig())
        self.dialog = OcrSettingsDialog()
        self.dialog.show()
        APP.processEvents()

    def tearDown(self):
        self.dialog.reject()
        self.dialog.deleteLater()
        APP.processEvents()
        configure_ocr(self.previous)

    def choose(self, mode):
        self.dialog.backend.setCurrentIndex(self.dialog.backend.findData(mode))
        APP.processEvents()

    def test_server_choice_saves_the_remote_connection(self):
        self.choose("server")
        self.dialog.url.setText("http://my-server:8766")
        self.dialog.token.setText("remote-token")
        with patch.object(OcrConfig, "save") as save:
            self.dialog.save_settings()
        save.assert_called_once()
        self.assertEqual(current_config().backend, "server")
        self.assertEqual(current_config().server_url, "http://my-server:8766")

    def test_local_gpu_is_saved_only_after_its_backend_is_ready(self):
        self.choose("gpu")
        self.dialog.gpu.setText("AMD")
        with (
            patch("circle_to_search.ocr_settings.QThreadPool") as pool,
            patch.object(OcrConfig, "save") as save,
        ):
            self.dialog.save_settings()
            save.assert_not_called()
            task = pool.globalInstance.return_value.start.call_args.args[0]
            task.signals.done.emit({"accelerated": True, "device": "AMD test GPU"})
            APP.processEvents()
            save.assert_called_once()
        self.assertEqual(current_config().backend, "gpu")
        self.assertEqual(current_config().local_gpu_name, "AMD")

    def test_cancelling_setup_does_not_change_the_selected_backend(self):
        self.choose("gpu")
        with (
            patch("circle_to_search.ocr_settings.QThreadPool") as pool,
            patch.object(OcrConfig, "save") as save,
        ):
            self.dialog.save_settings()
            task = pool.globalInstance.return_value.start.call_args.args[0]
            self.dialog.reject()
            task.signals.done.emit({"accelerated": True, "device": "AMD test GPU"})
            APP.processEvents()
            save.assert_not_called()
        self.assertEqual(current_config().backend, "local")


if __name__ == "__main__":
    unittest.main()
