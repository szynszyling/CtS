import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from circle_to_search.ocr_backend import OcrConfig
from circle_to_search.platforms.linux import ocr as managed_ocr


class ManagedBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.previous = (managed_ocr._CONNECTION, managed_ocr._GPU_NAME)
        self.languages = ("eng", "jpn")
        self.language_patch = patch.object(
            managed_ocr, "selected_models", return_value=self.languages
        )
        self.language_patch.start()
        managed_ocr._CONNECTION = None
        managed_ocr._GPU_NAME = None

    def tearDown(self):
        self.language_patch.stop()
        managed_ocr._CONNECTION, managed_ocr._GPU_NAME = self.previous
        self.temp.cleanup()

    def test_existing_managed_gpu_is_reused_without_building(self):
        (self.root / "ocr-server.env").write_text(
            "CTS_OCR_SERVER_TOKEN=secret\nCTS_OCR_PORT=8766\n"
        )
        with (
            patch.object(managed_ocr, "settings_path", return_value=self.root / "ocr.json"),
            patch.object(
                managed_ocr,
                "command",
                return_value=SimpleNamespace(
                    returncode=0,
                    stdout=managed_ocr.image_for_languages(self.languages) + " true",
                ),
            ),
            patch.object(managed_ocr, "wait_ready", return_value={"accelerated": True}),
            patch.object(managed_ocr, "build_image") as build,
        ):
            connection = managed_ocr.ensure_local(OcrConfig("gpu", local_gpu_name="AMD"))
        self.assertEqual(connection.backend, "server")
        self.assertEqual(connection.token, "secret")
        self.assertEqual(connection.server_url, "http://127.0.0.1:8766")
        build.assert_not_called()

    def test_an_unrelated_container_is_never_replaced(self):
        with (
            patch.object(managed_ocr, "settings_path", return_value=self.root / "ocr.json"),
            patch.object(
                managed_ocr,
                "command",
                return_value=SimpleNamespace(returncode=0, stdout="another-project:latest true"),
            ) as command,
        ):
            with self.assertRaisesRegex(RuntimeError, "another application"):
                managed_ocr.ensure_local(OcrConfig("gpu"), setup=True, replace_existing=True)
        self.assertEqual(command.call_count, 1)

    def test_build_context_excludes_env_and_unrelated_files(self):
        source = self.root / "server"
        source.mkdir()
        for name in (
            "Dockerfile",
            "pyproject.toml",
            "requirements.lock",
            "README.md",
            "LICENSE",
            "THIRD_PARTY.md",
            "build_models.py",
        ):
            (source / name).write_text("source")
        (source / "licenses").mkdir()
        (source / "licenses/Apache-2.0.txt").write_text("model license")
        (source / "licenses/.env").write_text("unrelated private settings")
        (source / ".env").write_text("private token")
        for directory in ("cts_ocr_server", "tests"):
            (source / directory).mkdir()
            (source / directory / "example.py").write_text("pass")
            (source / directory / "unrelated.png").write_bytes(b"private image")
        observed = []

        def inspect(command, **kwargs):
            context = Path(command[-1])
            observed.extend(
                path.relative_to(context).as_posix()
                for path in context.rglob("*")
                if path.is_file()
            )

        with (
            patch.object(managed_ocr, "deployment_directory", return_value=source),
            patch.object(managed_ocr, "command", side_effect=inspect),
        ):
            managed_ocr.build_image()
        self.assertIn("server/cts_ocr_server/example.py", observed)
        self.assertIn("server/LICENSE", observed)
        self.assertIn("server/licenses/Apache-2.0.txt", observed)
        self.assertIn("server/build_models.py", observed)
        self.assertFalse(any(name.endswith((".env", ".png", ".traineddata")) for name in observed))

    def test_language_selection_changes_the_local_image(self):
        self.assertNotEqual(
            managed_ocr.image_for_languages(("eng", "pol")),
            managed_ocr.image_for_languages(("eng", "ukr")),
        )
        self.assertEqual(
            managed_ocr.image_for_languages(("eng", "pol")),
            managed_ocr.image_for_languages(("pol", "eng")),
        )

    def test_failed_model_switch_restores_the_previous_container_and_token(self):
        token = self.root / "ocr-server.env"
        token.write_text("CTS_OCR_SERVER_TOKEN=old-token\nCTS_OCR_PORT=8766\n")

        def docker(arguments, **kwargs):
            output = ""
            if arguments[1:3] == ["container", "inspect"]:
                output = "circle-to-search-ocr:0.13.0 true"
            elif arguments[-1] == "--list-devices":
                output = "0 AMD test GPU"
            return SimpleNamespace(returncode=0, stdout=output)

        with (
            patch.object(managed_ocr, "settings_path", return_value=self.root / "ocr.json"),
            patch.object(managed_ocr, "command", side_effect=docker) as command,
            patch.object(managed_ocr, "wait_ready", side_effect=RuntimeError("startup failed")),
            patch.object(managed_ocr.Path, "glob") as nodes,
        ):
            nodes.return_value = [SimpleNamespace(stat=lambda: SimpleNamespace(st_gid=123))]
            with self.assertRaisesRegex(RuntimeError, "startup failed"):
                managed_ocr.ensure_local(OcrConfig("gpu"), setup=True)
        commands = [call.args[0] for call in command.call_args_list]
        backup = next(args[-1] for args in commands if args[1:3] == ["rename", managed_ocr.NAME])
        self.assertIn(["docker", "rename", backup, managed_ocr.NAME], commands)
        self.assertIn(["docker", "start", managed_ocr.NAME], commands)
        self.assertIn("CTS_OCR_SERVER_TOKEN=old-token", token.read_text())

    def test_local_modes_do_not_require_a_valid_unused_remote_address(self):
        self.assertEqual(OcrConfig("gpu", server_url="unfinished").validated().backend, "gpu")
        with self.assertRaises(ValueError):
            OcrConfig("server", server_url="unfinished").validated()


if __name__ == "__main__":
    unittest.main()
