import unittest
from unittest.mock import patch

from tools.publish_ocr_image import main,require_private


class PublishTests(unittest.TestCase):
    def test_public_package_is_rejected_before_any_docker_operation(self):
        with patch.dict('os.environ',{'GHCR_TOKEN':'test-token','GITHUB_REPOSITORY':'owner/CtS',
                                    'GITHUB_SHA':'a'*40,'GITHUB_ACTOR':'owner'}),\
             patch('tools.publish_ocr_image.package_info',return_value={'visibility':'public'}),\
             patch('tools.publish_ocr_image.subprocess.run') as docker:
            with self.assertRaisesRegex(RuntimeError,'non-private'):
                main(['--image','ghcr.io/owner/cts-ocr','--version','1.2.3'])
            docker.assert_not_called()

    def test_private_package_must_belong_to_the_expected_repository(self):
        with self.assertRaisesRegex(RuntimeError,'another repository'):
            require_private({'visibility':'private','repository':{'full_name':'owner/other'}},'owner/CtS')
        require_private({'visibility':'private','repository':{'full_name':'owner/cts'}},'owner/CtS')

    def test_failed_version_push_does_not_update_latest_and_logs_out(self):
        import subprocess
        calls=[]
        def run(arguments,**kwargs):
            calls.append(arguments)
            if arguments[:2]==['docker','push']:raise subprocess.CalledProcessError(1,arguments)
        with patch.dict('os.environ',{'GHCR_TOKEN':'test-token','GITHUB_REPOSITORY':'owner/CtS',
                                    'GITHUB_SHA':'a'*40,'GITHUB_ACTOR':'owner'}),\
             patch('tools.publish_ocr_image.package_info',return_value=None),\
             patch('tools.publish_ocr_image.subprocess.run',side_effect=run):
            with self.assertRaises(subprocess.CalledProcessError):
                main(['--image','ghcr.io/owner/cts-ocr','--version','1.2.3'])
        self.assertEqual([args[-1] for args in calls if args[:2]==['docker','push']],['ghcr.io/owner/cts-ocr:1.2.3'])
        self.assertEqual(calls[-1],['docker','logout','ghcr.io'])


if __name__=='__main__':unittest.main()
