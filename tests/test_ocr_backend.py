import json
import ssl
import urllib.error
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QRectF,Qt
from PySide6.QtGui import QImage

from circle_to_search.ocr import recognize_document
from circle_to_search.ocr_backend import OcrConfig,configure_ocr,current_config,recognize_remote,server_request


class Reply:
    def __init__(self,payload):self.data=json.dumps(payload).encode()
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def read(self,limit):return self.data[:limit]


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.previous=current_config()
        self.image=QImage(120,80,QImage.Format_RGB32);self.image.fill(Qt.white)
        self.config=OcrConfig('server','http://127.0.0.1:8766','secret',3)
        self.payload={'service':'circle-to-search-ocr','api_version':1,'width':120,'height':80,'glyphs':[
            {'text':'か','bbox':[10,20,15,24],'line':'0','word':'0:0','confidence':98},
            {'text':'語','bbox':[25,20,15,24],'line':'0','word':'0:0','confidence':97}]}

    def tearDown(self):configure_ocr(self.previous)

    @patch('circle_to_search.ocr_backend.urllib.request.build_opener')
    def test_remote_character_geometry_and_image_protocol(self,opener):
        opener.return_value.open.return_value=Reply(self.payload)
        document=recognize_remote(self.image,'jpn+eng',False,'interactive',self.config)
        self.assertEqual(document.text(),'か語')
        self.assertEqual(document.glyphs[1].rect,QRectF(25,20,15,24))
        request=opener.return_value.open.call_args.args[0]
        self.assertEqual(request.get_header('Authorization'),'Bearer secret')
        self.assertEqual(request.get_header('Content-type'),'image/png')
        self.assertTrue(request.data.startswith(b'\x89PNG'))
        self.assertIn('priority=interactive',request.full_url)

    @patch('circle_to_search.ocr_backend.server_request')
    def test_invalid_dimensions_nan_and_phrase_geometry_are_rejected(self,request):
        request.return_value=dict(self.payload,width=240)
        with self.assertRaisesRegex(RuntimeError,'dimensions'):
            recognize_remote(self.image,'jpn',False,'background',self.config)
        for bbox in ([float('nan'),20,15,24],[10,20,-15,24],[200,20,15,24]):
            request.return_value=dict(self.payload,glyphs=[dict(self.payload['glyphs'][0],bbox=bbox)])
            with self.assertRaisesRegex(RuntimeError,'character box'):
                recognize_remote(self.image,'jpn',False,'background',self.config)

    def test_fallback_requires_an_explicit_choice(self):
        configure_ocr(self.config)
        with patch('circle_to_search.ocr_backend.recognize_remote',side_effect=RuntimeError('offline')),patch('circle_to_search.ocr.recognize_tesseract') as local:
            with self.assertRaisesRegex(RuntimeError,'offline'):recognize_document(self.image)
            local.assert_not_called()
            configure_ocr(OcrConfig('server',self.config.server_url,'',3,True))
            recognize_document(self.image)
            local.assert_called_once()

    def test_gpu_mode_preserves_the_explicit_fallback_choice(self):
        configure_ocr(OcrConfig('gpu',fallback=True))
        with patch('circle_to_search.managed_ocr.ensure_local',return_value=self.config),patch('circle_to_search.ocr_backend.recognize_remote',side_effect=RuntimeError('offline')),patch('circle_to_search.ocr.recognize_tesseract') as local:
            recognize_document(self.image)
            local.assert_called_once()

    def test_preferences_persist_with_private_file_permissions(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'ocr.json'
            self.config.save(path)
            with patch.dict('os.environ',{},clear=True):self.assertEqual(OcrConfig.load(path),self.config)
            self.assertEqual(path.stat().st_mode&0o777,0o600)

    def test_server_url_rejects_credentials_and_unsafe_schemes(self):
        for url in ('file:///tmp/image','http://user:password@host','https://server/?token=secret','https://server/#fragment','http://server:invalid'):
            with self.assertRaises(ValueError):OcrConfig('server',url).validated()

    @patch('circle_to_search.ocr_backend.urllib.request.build_opener')
    def test_invalid_https_certificates_are_reported_without_disabling_validation(self,opener):
        opener.return_value.open.side_effect=urllib.error.URLError(ssl.SSLCertVerificationError(1,'hostname mismatch'))
        with self.assertRaisesRegex(RuntimeError,'HTTPS certificate'):
            server_request(OcrConfig('server','https://cts.test','secret'),'/v1/health')
        self.assertEqual(opener.return_value.open.call_count,1)

    @patch('circle_to_search.ocr_backend.urllib.request.build_opener')
    def test_invalid_api_response_is_reported(self,opener):
        opener.return_value.open.return_value=Reply({'api_version':2})
        with self.assertRaisesRegex(RuntimeError,'API version'):server_request(self.config,'/v1/health')


if __name__=='__main__':unittest.main()
