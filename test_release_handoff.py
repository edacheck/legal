"""Regression checks for the approved public registration handoff."""

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from common import OUTPUT, digest, document, edition
from tools import release_handoff


class ReleaseHandoffChecks(unittest.TestCase):
    def snapshot(self):
        return {str(path.relative_to(OUTPUT)): digest(path.read_bytes())
                for path in OUTPUT.rglob("*") if path.is_file()}

    def test_exact_bytes_digests_versions_urls_and_snapshot(self):
        before = self.snapshot()
        value = release_handoff.handoff()
        config = edition()
        expected = {
            "terms": "d497e3e8e841292619994d9f74c8a6ddc8b8e33dbe094fbf151cc1311b367a85",
            "privacy": "3710d069b361ea96666dcf401b13f61b5688defc90ea80f322ab5c94de0c45de",
        }
        self.assertEqual(value["schema_version"], 1)
        self.assertEqual(value["document_id"], "terms")
        self.assertEqual(value["action_id"], "accept-terms")
        self.assertEqual(value["document_version"], config["version"])
        self.assertEqual(value["policy_version"], config["version"])
        for slug in ("terms", "privacy"):
            content = document(config, slug).encode("utf-8")
            self.assertEqual(base64.b64decode(value[slug]["text_base64"], validate=True), content)
            self.assertEqual(value[slug]["sha256"], expected[slug])
            self.assertEqual(digest(content), expected[slug])
            self.assertEqual(value[slug]["url"],
                             f"https://legal.edacheck.ru/versions/{config['version']}/{slug}/")
        self.assertEqual(self.snapshot(), before)

    def test_writes_deterministic_json_outside_pages(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "handoff.json"
            value = release_handoff.handoff()
            release_handoff.write_output(output, value)
            self.assertEqual(json.loads(output.read_text(encoding="ascii")), value)
            with self.assertRaisesRegex(ValueError, "inside the repository"):
                release_handoff.write_output(OUTPUT / "handoff.json", value)
            with self.assertRaisesRegex(ValueError, "inside the repository"):
                release_handoff.write_output(Path(__file__).parent / "edition.json", value)

    def test_rejects_unknown_fields_drafts_mismatches_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "release-profile.json"
            profile.write_text(json.dumps({"schema_version": 1, "document_id": "terms",
                                           "action_id": "accept-terms", "unknown": True}))
            with patch.object(release_handoff, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "profile fields"):
                    release_handoff.handoff()
            profile.unlink()
            profile.symlink_to(Path(__file__).parent / "release-profile.json")
            with patch.object(release_handoff, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "regular file"):
                    release_handoff.handoff()
        config = edition()
        with patch.object(release_handoff, "edition", return_value={**config, "status": "draft"}):
            with self.assertRaisesRegex(ValueError, "approved edition"):
                release_handoff.handoff()
        with patch.object(release_handoff, "edition", return_value={**config, "extra": True}):
            with self.assertRaisesRegex(ValueError, "edition fields"):
                release_handoff.handoff()

    def test_rejects_non_ascii_control_ids_and_manifest_mismatch(self):
        for identifier in ("t\u0435rms", "terms\n"):
            with self.subTest(identifier=identifier), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "release-profile.json").write_text(json.dumps({
                    "schema_version": 1, "document_id": identifier,
                    "action_id": "accept-terms"}))
                with patch.object(release_handoff, "ROOT", root):
                    with self.assertRaisesRegex(ValueError, "Unsafe ASCII"):
                        release_handoff.handoff()
        manifest = json.loads((OUTPUT / "versions/2026-10-28.1/manifest.json").read_text())
        manifest["documents"]["terms"]["document_sha256"] = "0" * 64
        with patch.object(release_handoff, "read_json", side_effect=[
                json.loads((Path(__file__).parent / "release-profile.json").read_text()), manifest,
                json.loads((OUTPUT / "versions/2026-10-28.1/registration-links.json").read_text())]):
            with self.assertRaises(ValueError):
                release_handoff.handoff()


if __name__ == "__main__":
    unittest.main()
