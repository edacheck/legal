"""Verify snapshot extraction boundaries and release history selection."""

import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import site_ci
from tools import backup


class SnapshotChecks(unittest.TestCase):
    def test_rejects_escaping_paths_and_symlinks(self):
        for name, kind in (("../private.txt", tarfile.REGTYPE),
                           ("/private.txt", tarfile.REGTYPE),
                           ("link", tarfile.SYMTYPE)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                path = root / "site.tar.gz"
                with tarfile.open(path, "w:gz") as archive:
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    member.linkname = "../private.txt" if kind == tarfile.SYMTYPE else ""
                    archive.addfile(member)
                with self.assertRaisesRegex(ValueError, "Unsafe snapshot"):
                    site_ci.extract_snapshot(path, root / "result")
                self.assertFalse((root / "private.txt").exists())

    def test_valid_snapshot_extracts_only_relative_regular_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "site.tar.gz"
            with tarfile.open(path, "w:gz") as archive:
                member = tarfile.TarInfo("versions/test/index.html")
                member.size = 4
                archive.addfile(member, io.BytesIO(b"page"))
            site_ci.extract_snapshot(path, root / "result")
            self.assertEqual((root / "result/versions/test/index.html").read_bytes(), b"page")

    def test_first_deployment_does_not_ignore_github_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(site_ci, "ROOT", root), patch.dict(os.environ, {
                "GITHUB_REPOSITORY": "edacheck/legal", "GITHUB_SHA": "a" * 40,
            }), patch.object(site_ci, "get_json", side_effect=ValueError("API unavailable")):
                with self.assertRaisesRegex(ValueError, "API unavailable"):
                    site_ci.restore()
                self.assertFalse((root / "_build/previous-site").exists())

    def test_initial_empty_history_is_recorded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(site_ci, "ROOT", root), patch.dict(os.environ, {
                "GITHUB_REPOSITORY": "edacheck/legal", "GITHUB_SHA": "a" * 40,
            }), patch.object(site_ci, "get_json", side_effect=[None, []]):
                site_ci.restore()
            self.assertEqual(json.loads((root / "_build/history.json").read_text()),
                             {"tag": None, "reuse": False})

    def test_backup_pushes_reviewed_refs_without_force_or_ci(self):
        with patch.object(backup, "git", side_effect=[
            backup.BACKUP, "", "a" * 40, "b" * 40, "site-test", "",
        ]) as runner:
            backup.backup()
        self.assertEqual(runner.call_args.args, (
            "push", "--atomic", "--push-option=ci.skip", "gitlab-backup",
            "a" * 40 + ":refs/heads/dev", "b" * 40 + ":refs/heads/main",
            "refs/tags/site-test:refs/tags/site-test",
        ))

    def test_backup_refuses_unexpected_remote(self):
        with patch.object(backup, "git", return_value="ssh://other.invalid/repo") as runner:
            with self.assertRaisesRegex(ValueError, "Unexpected GitLab backup"):
                backup.backup()
        self.assertEqual(runner.call_count, 1)

    def test_history_search_continues_after_first_page(self):
        unrelated = [{"draft": False, "tag_name": f"other-{index}"} for index in range(100)]
        expected = "site-" + "b" * 40
        with patch.object(site_ci, "get_json", side_effect=[
            None, unrelated, [{"draft": False, "tag_name": expected}],
        ]) as reader:
            self.assertEqual(site_ci.select_snapshot("edacheck/legal", "a" * 40), expected)
        self.assertTrue(reader.call_args.args[0].endswith("page=2"))

    def test_current_draft_snapshot_blocks_publication(self):
        with patch.object(site_ci, "get_json", return_value={"draft": True}):
            with self.assertRaisesRegex(ValueError, "Incomplete snapshot draft"):
                site_ci.select_snapshot("edacheck/legal", "a" * 40)


if __name__ == "__main__":
    unittest.main()
