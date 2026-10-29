"""Activate verified local generations; preserve the previous complete result."""

import os
import tempfile
from pathlib import Path


def activate(staged, output):
    generations = output.parent / "generations"
    generations.mkdir(exist_ok=True)
    generation = Path(tempfile.mkdtemp(prefix="edition-", dir=generations))
    destination = generation / "site"
    staged.replace(destination)
    pointer = output.parent / f".{generation.name}"
    legacy = None
    try:
        pointer.symlink_to(destination.relative_to(output.parent), target_is_directory=True)
        if output.exists() and not output.is_symlink():
            legacy = generation / "previous-site"
            output.replace(legacy)
        try:
            os.replace(pointer, output)
        except OSError:
            if legacy is not None:
                legacy.replace(output)
            raise
    finally:
        if pointer.is_symlink():
            pointer.unlink()
