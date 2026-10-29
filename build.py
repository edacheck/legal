"""Stage and verify the entire website before switching the local output."""

import argparse
import fcntl
import json
import shutil
import sys
import tempfile
from pathlib import Path

from common import OUTPUT, digest, document, edition, tools
from publish import activate
from render import inputs, render
from verify import verify_release, verify_site


def reusable(previous, config):
    manifest = json.loads((previous / "manifest.json").read_text(encoding="utf-8"))
    if manifest["edition"]["status"] != "approved":
        return False
    matching = manifest["edition"] == config and manifest["inputs"] == inputs()
    for slug, record in manifest["documents"].items():
        matching = matching and record["document_sha256"] == digest(
            document(config, slug).encode("utf-8"))
    if not matching:
        raise ValueError("Approved edition is immutable; choose a new version")
    return True


def stage(config, versions, output, previous):
    releases = previous / "versions"
    known = []
    if releases.exists():
        for release in sorted(releases.iterdir()):
            if release.is_symlink() or not release.is_dir():
                raise ValueError(f"Unexpected release entry: {release.name}")
            manifest = verify_release(release)
            if release.name != manifest["edition"]["version"]:
                raise ValueError("Release directory and edition version differ")
            known.append(release)
    current = releases / config["version"]
    if current in known and reusable(current, config):
        shutil.copytree(current, output)
    else:
        render(config, versions, output)
    verify_release(output, config, check_sources=True)
    archive = output / "versions"
    archive.mkdir()
    for release in known:
        if release.name != config["version"]:
            shutil.copytree(release, archive / release.name)
    shutil.copytree(output, archive / config["version"], ignore=shutil.ignore_patterns("versions"))
    verify_site(output, config, check_sources=True)


def build(previous=None):
    config = edition()
    versions = tools(config)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with (OUTPUT.parent / "build.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with tempfile.TemporaryDirectory(prefix="staging-", dir=OUTPUT.parent) as temporary:
            staged = Path(temporary) / "site"
            stage(config, versions, staged, previous if previous is not None else OUTPUT)
            activate(staged, OUTPUT)
    print(f"Built and verified {len(config['documents'])} HTML/PDF pairs: {OUTPUT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous-site", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.previous_site is not None and not arguments.previous_site.is_dir():
            raise ValueError("Previous website directory does not exist")
        build(arguments.previous_site)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        sys.exit(1)
