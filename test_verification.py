"""Exercise rejection of mismatched text and accidental private publication."""

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import verify
from common import OUTPUT, digest


class ArtifactChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name) / "site"
        shutil.copytree(OUTPUT, self.output)

    def check_failure(self, message):
        with patch.object(verify, "OUTPUT", self.output):
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, message):
                    verify.verify()

    def test_detects_text_mismatch_even_after_updated_hash(self):
        path = self.output / "privacy" / "index.html"
        content = path.read_text(encoding="utf-8")
        content = content.replace("Оператор - Общество", "Оператор - Другое общество", 1)
        path.write_text(content, encoding="utf-8")
        manifest_path = self.output / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["documents"]["privacy"]["html_sha256"] = digest(path.read_bytes())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.check_failure("Actual HTML/PDF text mismatch: privacy")

    def test_rejects_private_file_in_public_output(self):
        (self.output / "internal-notes.md").write_text("private", encoding="utf-8")
        self.check_failure("Unexpected or missing public files")

    def test_manifest_cannot_allow_private_file(self):
        path = self.output / "internal-notes.md"
        path.write_text("private", encoding="utf-8")
        manifest_path = self.output / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["assets"][path.name] = digest(path.read_bytes())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.check_failure("Unexpected public manifest entries")

    def test_detects_missing_pdf(self):
        manifest = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        (self.output / manifest["documents"]["terms"]["pdf"]).write_bytes(b"not a PDF")
        self.check_failure("Artifact hash mismatch: terms/pdf")


if __name__ == "__main__":
    unittest.main()
