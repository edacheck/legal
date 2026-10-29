"""Integration regressions for version changes and failed PDF conversion."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from common import ROOT, digest


class BuildChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "public"
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns(
            "_build", ".git", ".tools", "__pycache__"))
        self.output = self.root / "_build" / "site"
        self.config = json.loads((self.root / "edition.json").read_text(encoding="utf-8"))
        self.run_build()

    def command(self, arguments, success=True):
        result = subprocess.run([sys.executable, "-B", *arguments], cwd=self.root,
                                capture_output=True, text=True, check=False)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def run_build(self):
        self.command(["build.py"])

    def configure(self, **changes):
        self.config.update(changes)
        (self.root / "edition.json").write_text(json.dumps(self.config), encoding="utf-8")

    def snapshot(self, output=None):
        directory = self.output if output is None else output
        return {str(path.relative_to(directory)): digest(path.read_bytes())
                for path in directory.rglob("*") if path.is_file()}

    def test_version_change_preserves_old_archive_and_replaces_current(self):
        old_version = self.config["version"]
        old = self.snapshot(self.output / "versions" / old_version)
        self.configure(version="2026-10-29-draft.2")
        self.run_build()
        self.command(["verify.py"])
        self.assertEqual(len(list(self.output.glob("*/*.pdf"))), 3)
        self.assertEqual(len(list(self.output.rglob("*.pdf"))), 9)
        self.assertEqual(old, self.snapshot(self.output / "versions" / old_version))
        links = json.loads((self.output / "registration-links.json").read_text())
        for name in ("AGREEMENT", "POLICY"):
            self.assertIn("/versions/2026-10-29-draft.2/",
                          links[f"EDACHECK_REGISTRATION_{name}_URL"])
        self.assertFalse(list(self.output.glob(f"*/*-{old_version}.pdf")))

    def test_converter_failure_preserves_complete_current_output(self):
        before = self.snapshot()
        pointer = self.output.readlink()
        self.configure(version="2026-10-29-draft.2")
        for failure_at in (1, 2):
            with self.subTest(failure_at=failure_at):
                script = (
                    "import build, render; original=render.execute; calls=0\n"
                    "def fail(arguments, content=None):\n"
                    " global calls\n"
                    " if '--pdf-engine=typst' in arguments:\n"
                    "  calls += 1\n"
                    f"  if calls == {failure_at}: raise ValueError('injected PDF failure')\n"
                    " return original(arguments, content)\n"
                    "render.execute=fail\nbuild.build()\n"
                )
                result = self.command(["-c", script], success=False)
                self.assertIn("injected PDF failure", result.stderr)
                self.assertEqual(before, self.snapshot())
                self.assertEqual(pointer, self.output.readlink())

    def test_approved_snapshot_is_reused_and_cannot_be_rewritten(self):
        self.configure(version="2026-10-29.1", status="approved", effective_date="2026-11-01")
        self.run_build()
        archived = self.output / "versions" / self.config["version"]
        before = self.snapshot(archived)
        self.run_build()
        self.assertEqual(before, self.snapshot(archived))
        source = self.root / "documents" / "terms.md"
        source.write_text(source.read_text(encoding="utf-8") + "\nДополнение.\n", encoding="utf-8")
        result = self.command(["build.py"], success=False)
        self.assertIn("Approved edition is immutable", result.stderr)
        self.assertEqual(before, self.snapshot(archived))

    def test_verification_failure_does_not_activate_new_edition(self):
        before = self.snapshot()
        pointer = self.output.readlink()
        self.configure(version="2026-10-29-draft.2")
        script = (
            "import build\n"
            "def reject(*arguments, **keywords):\n"
            " raise ValueError('injected verification failure')\n"
            "build.verify_site=reject\nbuild.build()\n"
        )
        result = self.command(["-c", script], success=False)
        self.assertIn("injected verification failure", result.stderr)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(pointer, self.output.readlink())

    def test_clean_runner_preserves_archives_from_previous_site(self):
        previous = Path(self.temporary.name) / "previous-site"
        shutil.copytree(self.output, previous)
        old_version = self.config["version"]
        old = self.snapshot(previous / "versions" / old_version)
        self.output.unlink()
        self.configure(version="2026-10-29-draft.2")
        self.command(["build.py", "--previous-site", str(previous)])
        self.command(["verify.py"])
        self.assertEqual(old, self.snapshot(self.output / "versions" / old_version))


if __name__ == "__main__":
    unittest.main()
