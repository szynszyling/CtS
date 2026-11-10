import unittest
from unittest.mock import patch

from tools.publish_ocr_image import main, require_visibility


class PublishTests(unittest.TestCase):
    def test_private_package_is_rejected_before_a_public_release(self):
        with (
            patch.dict(
                "os.environ",
                {
                    "GHCR_TOKEN": "test-token",
                    "GITHUB_REPOSITORY": "owner/CtS",
                    "GITHUB_SHA": "a" * 40,
                    "GITHUB_ACTOR": "owner",
                },
            ),
            patch("tools.publish_ocr_image.package_info", return_value={"visibility": "private"}),
            patch("tools.publish_ocr_image.subprocess.run") as docker,
        ):
            with self.assertRaisesRegex(RuntimeError, "Expected a public"):
                main(["--image", "ghcr.io/owner/cts-ocr", "--version", "1.2.3"])
            docker.assert_not_called()

    def test_package_must_belong_to_the_expected_repository(self):
        with self.assertRaisesRegex(RuntimeError, "another repository"):
            require_visibility(
                {"visibility": "public", "repository": {"full_name": "owner/other"}},
                "owner/CtS",
                "public",
            )
        require_visibility(
            {"visibility": "public", "repository": {"full_name": "owner/cts"}},
            "owner/CtS",
            "public",
        )

    def test_public_release_cannot_create_an_unverified_private_package(self):
        with self.assertRaisesRegex(RuntimeError, "public package must exist"):
            require_visibility(None, "owner/CtS", "public")
        require_visibility(None, "owner/CtS", "private")

    def test_public_release_pushes_the_tested_image_and_pulls_the_version_back(self):
        with (
            patch.dict(
                "os.environ",
                {
                    "GHCR_TOKEN": "test-token",
                    "GITHUB_REPOSITORY": "owner/CtS",
                    "GITHUB_SHA": "a" * 40,
                    "GITHUB_ACTOR": "owner",
                },
            ),
            patch("tools.publish_ocr_image.package_info", return_value={"visibility": "public"}),
            patch("tools.publish_ocr_image.subprocess.run") as docker,
        ):
            self.assertEqual(main(["--image", "ghcr.io/owner/cts-ocr", "--version", "1.2.3"]), 0)
        pushes = [
            call.args[0][-1]
            for call in docker.call_args_list
            if call.args[0][:2] == ["docker", "push"]
        ]
        self.assertEqual(
            pushes,
            [
                "ghcr.io/owner/cts-ocr:1.2.3",
                "ghcr.io/owner/cts-ocr:sha-" + "a" * 40,
                "ghcr.io/owner/cts-ocr:latest",
            ],
        )
        self.assertIn(
            ["docker", "pull", "ghcr.io/owner/cts-ocr:1.2.3"],
            [call.args[0] for call in docker.call_args_list],
        )

    def test_failed_version_push_does_not_update_latest_and_logs_out(self):
        import subprocess

        calls = []

        def run(arguments, **kwargs):
            calls.append(arguments)
            if arguments[:2] == ["docker", "push"]:
                raise subprocess.CalledProcessError(1, arguments)

        with (
            patch.dict(
                "os.environ",
                {
                    "GHCR_TOKEN": "test-token",
                    "GITHUB_REPOSITORY": "owner/CtS",
                    "GITHUB_SHA": "a" * 40,
                    "GITHUB_ACTOR": "owner",
                },
            ),
            patch("tools.publish_ocr_image.package_info", return_value=None),
            patch("tools.publish_ocr_image.subprocess.run", side_effect=run),
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                main(
                    [
                        "--image",
                        "ghcr.io/owner/cts-ocr",
                        "--version",
                        "1.2.3",
                        "--visibility",
                        "private",
                    ]
                )
        self.assertEqual(
            [args[-1] for args in calls if args[:2] == ["docker", "push"]],
            ["ghcr.io/owner/cts-ocr:1.2.3"],
        )
        self.assertEqual(calls[-1], ["docker", "logout", "ghcr.io"])


if __name__ == "__main__":
    unittest.main()
