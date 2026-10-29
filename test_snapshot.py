"""Deployment regressions for incomplete releases and stale workflow retries."""

import io
import os
import shutil
import tarfile
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from tools import github_api, snapshot


def archive(path, content):
    with tarfile.open(path, "w:gz") as output:
        member = tarfile.TarInfo("index.html")
        member.size = len(content)
        output.addfile(member, io.BytesIO(content))


class DeploymentChecks(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {
            "GITHUB_REPOSITORY": "edacheck/legal", "GITHUB_SHA": "a" * 40,
            "GH_TOKEN": "test-token",
        })
        environment.start()
        self.addCleanup(environment.stop)

    def test_failed_deploy_retry_cannot_replace_newer_main(self):
        with patch.object(snapshot, "get_json", return_value={"object": {"sha": "b" * 40}}):
            with self.assertRaisesRegex(ValueError, "Stale workflow"):
                snapshot.current_main()

    def test_existing_draft_is_not_a_successful_snapshot(self):
        with patch.object(snapshot, "current_main"), \
                patch.object(snapshot, "get_json", return_value={"draft": True}), \
                patch.object(snapshot, "run") as runner:
            with self.assertRaisesRegex(ValueError, "Incomplete draft"):
                snapshot.ensure_snapshot(Path("site.tar.gz"))
        runner.assert_not_called()

    def test_published_release_without_asset_blocks_deploy(self):
        with patch.object(snapshot, "current_main"), \
                patch.object(snapshot, "get_json", return_value={"draft": False, "assets": []}), \
                patch.object(snapshot, "run") as runner:
            with self.assertRaisesRegex(ValueError, "Missing or incomplete"):
                snapshot.ensure_snapshot(Path("site.tar.gz"))
        runner.assert_not_called()

    def test_published_asset_must_match_verified_file_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = root / "verified.tar.gz"
            stored = root / "stored.tar.gz"
            archive(expected, b"verified")
            for content in (b"verified", b"different"):
                with self.subTest(content=content):
                    archive(stored, content)

                    def download(arguments):
                        self.assertEqual(arguments[:3], ["gh", "release", "download"])
                        destination = Path(arguments[arguments.index("--dir") + 1])
                        shutil.copyfile(stored, destination / "site.tar.gz")

                    release = {"draft": False, "assets": [{"name": "site.tar.gz", "state": "uploaded"}]}
                    with patch.object(snapshot, "current_main"), \
                            patch.object(snapshot, "get_json", return_value=release), \
                            patch.object(snapshot, "run", side_effect=download):
                        if content == b"verified":
                            snapshot.ensure_snapshot(expected)
                        else:
                            with self.assertRaisesRegex(ValueError, "differs from verified"):
                                snapshot.ensure_snapshot(expected)

    def test_only_explicit_404_means_missing_release(self):
        for status in (404, 403, 500):
            with self.subTest(status=status), patch.object(
                github_api.urllib.request, "urlopen",
                side_effect=urllib.error.HTTPError("https://api.github.com/test", status, "failure", {}, None),
            ):
                if status == 404:
                    self.assertIsNone(github_api.get_json("test", missing_ok=True))
                else:
                    with self.assertRaisesRegex(ValueError, f"HTTP {status}"):
                        github_api.get_json("test", missing_ok=True)


if __name__ == "__main__":
    unittest.main()
