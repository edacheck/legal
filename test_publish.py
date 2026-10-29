"""Verify activation failures preserve both legacy and generation outputs."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from publish import activate

ORIGINAL_REPLACE = os.replace


def reject_pointer(source, destination):
    if Path(source).is_symlink():
        raise OSError("activation failed")
    return ORIGINAL_REPLACE(source, destination)


class ActivationChecks(unittest.TestCase):
    def test_failure_rolls_back_legacy_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "site"
            output.mkdir()
            (output / "old.txt").write_text("previous", encoding="utf-8")
            staged = root / "staged"
            staged.mkdir()
            (staged / "new.txt").write_text("new", encoding="utf-8")
            with patch("publish.os.replace", side_effect=reject_pointer):
                with self.assertRaisesRegex(OSError, "activation failed"):
                    activate(staged, output)
            self.assertFalse(output.is_symlink())
            self.assertEqual((output / "old.txt").read_text(), "previous")
            self.assertFalse((output / "new.txt").exists())

    def test_generation_switch_failure_preserves_previous_pointer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "site"
            original = root / "first"
            original.mkdir()
            (original / "old.txt").write_text("previous", encoding="utf-8")
            activate(original, output)
            pointer = output.readlink()
            staged = root / "second"
            staged.mkdir()
            with patch("publish.os.replace", side_effect=reject_pointer):
                with self.assertRaisesRegex(OSError, "activation failed"):
                    activate(staged, output)
            self.assertEqual(output.readlink(), pointer)
            self.assertEqual((output / "old.txt").read_text(), "previous")


if __name__ == "__main__":
    unittest.main()
