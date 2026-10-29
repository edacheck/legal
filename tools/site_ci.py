"""Preserve Pages history using immutable, public per-commit release snapshots."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common import OUTPUT, edition
from verify import verify_site
from tools.github_api import get_json


def extract_snapshot(archive_path, destination):
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) > 4096 or sum(member.size for member in members) > 256 * 1024 * 1024:
            raise ValueError("Snapshot exceeds archive limits")
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not (member.isdir() or member.isfile()):
                raise ValueError("Unsafe snapshot archive member")
        archive.extractall(destination, members=members, filter="data")


def github(arguments):
    result = subprocess.run(["gh", *arguments], capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError(f"GitHub snapshot operation failed: {result.stderr}")
    return result.stdout


def select_snapshot(repository, commit):
    current = f"site-{commit}"
    release = get_json(f"repos/{repository}/releases/tags/{current}", missing_ok=True)
    if release is not None:
        if release["draft"]:
            raise ValueError("Incomplete snapshot draft for this commit")
        return current
    page = 1
    while True:
        releases = get_json(f"repos/{repository}/releases?per_page=100&page={page}")
        if not releases:
            return None
        for release in releases:
            if not release["draft"] and re.fullmatch(r"site-[0-9a-f]{40}", release["tag_name"]):
                return release["tag_name"]
        page += 1


def restore():
    root = ROOT / "_build"
    root.mkdir(exist_ok=True)
    previous = root / "previous-site"
    if previous.exists():
        raise ValueError("History directory already exists; use a clean checkout")
    repository = os.environ["GITHUB_REPOSITORY"]
    commit = os.environ["GITHUB_SHA"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Expected full GitHub commit SHA")
    current = f"site-{commit}"
    selected = select_snapshot(repository, commit)
    previous.mkdir()
    if selected is not None:
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            github(["release", "download", selected, "--repo", repository,
                    "--pattern", "site.tar.gz", "--dir", temporary])
            extract_snapshot(Path(temporary) / "site.tar.gz", previous)
        verify_site(previous)
    (root / "history.json").write_text(json.dumps({"tag": selected, "reuse": selected == current}))
    print(f"Previous Pages snapshot: {selected or 'first deployment'}")


def package():
    root = ROOT / "_build"
    history = json.loads((root / "history.json").read_text())
    previous = root / "previous-site"
    if history["reuse"]:
        verify_site(previous, edition(), check_sources=True)
        source = previous
    else:
        subprocess.run([sys.executable, "build.py", "--previous-site", str(previous)],
                       cwd=ROOT, check=True)
        source = OUTPUT
    destination = root / "publish"
    if destination.exists():
        raise ValueError("Publish directory already exists; use a clean checkout")
    shutil.copytree(source, destination)
    verify_site(destination, edition(), check_sources=True)
    with tarfile.open(root / "site.tar.gz", "w:gz") as archive:
        for path in sorted(destination.rglob("*")):
            if path.is_file():
                archive.add(path, arcname=str(path.relative_to(destination)), recursive=False)
    print(f"Verified public Pages artifact: {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("restore", "package"))
    arguments = parser.parse_args()
    try:
        {"restore": restore, "package": package}[arguments.command]()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f"Pages preparation failed: {error}", file=sys.stderr)
        sys.exit(1)
