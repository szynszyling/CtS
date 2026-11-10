from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from circle_to_search import managed_ocr
from circle_to_search.ocr_backend import OcrConfig


class ManagedBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.previous=(managed_ocr._CONNECTION,managed_ocr._GPU_NAME)
        managed_ocr._CONNECTION=None;managed_ocr._GPU_NAME=None

    def tearDown(self):
        managed_ocr._CONNECTION,managed_ocr._GPU_NAME=self.previous
        self.temp.cleanup()

    def test_existing_managed_gpu_is_reused_without_building(self):
        (self.root/'ocr-server.env').write_text('CTS_OCR_SERVER_TOKEN=secret\nCTS_OCR_PORT=8766\n')
        with patch.object(managed_ocr,'settings_path',return_value=self.root/'ocr.json'),patch.object(managed_ocr,'command',return_value=SimpleNamespace(returncode=0,stdout=managed_ocr.IMAGE+' true')),patch.object(managed_ocr,'wait_ready',return_value={'accelerated':True}),patch.object(managed_ocr,'build_image') as build:
            connection=managed_ocr.ensure_local(OcrConfig('gpu',local_gpu_name='AMD'))
        self.assertEqual(connection.backend,'server')
        self.assertEqual(connection.token,'secret')
        self.assertEqual(connection.server_url,'http://127.0.0.1:8766')
        build.assert_not_called()

    def test_an_unrelated_container_is_never_replaced(self):
        with patch.object(managed_ocr,'settings_path',return_value=self.root/'ocr.json'),patch.object(managed_ocr,'command',return_value=SimpleNamespace(returncode=0,stdout='another-project:latest true')) as command:
            with self.assertRaisesRegex(RuntimeError,'another application'):
                managed_ocr.ensure_local(OcrConfig('gpu'),setup=True,replace_existing=True)
        self.assertEqual(command.call_count,1)

    def test_build_context_excludes_env_and_unrelated_files(self):
        source=self.root/'server';source.mkdir()
        for name in ('Dockerfile','pyproject.toml','requirements.lock','README.md','THIRD_PARTY.md'):(source/name).write_text('source')
        (source/'.env').write_text('private token')
        for directory in ('cts_ocr_server','tests'):
            (source/directory).mkdir()
            (source/directory/'example.py').write_text('pass')
            (source/directory/'unrelated.png').write_bytes(b'private image')
        observed=[]
        def inspect(command,**kwargs):
            context=Path(command[-1])
            observed.extend(str(path.relative_to(context)) for path in context.rglob('*') if path.is_file())
        with patch.object(managed_ocr,'deployment_directory',return_value=source),patch.object(managed_ocr,'command',side_effect=inspect):
            managed_ocr.build_image()
        self.assertIn('server/cts_ocr_server/example.py',observed)
        self.assertFalse(any('.env' in name or '.png' in name for name in observed))

    def test_local_modes_do_not_require_a_valid_unused_remote_address(self):
        self.assertEqual(OcrConfig('gpu',server_url='unfinished').validated().backend,'gpu')
        with self.assertRaises(ValueError):OcrConfig('server',server_url='unfinished').validated()


if __name__=='__main__':unittest.main()
