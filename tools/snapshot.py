"""Require a complete public snapshot and reject stale-main deployments."""

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.github_api import get_json
from tools.site_ci import extract_snapshot


def current_main():
    repository = os.environ["GITHUB_REPOSITORY"]
    current = get_json(f"repos/{repository}/git/ref/heads/main")
    if current["object"]["sha"] != os.environ["GITHUB_SHA"]:
        raise ValueError("Stale workflow: main has advanced; deployment is forbidden")


def files(directory):
    return {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob("*") if path.is_file()}


def run(arguments):
    subprocess.run(arguments, check=True)


def ensure_snapshot(archive):
    current_main()
    repository = os.environ["GITHUB_REPOSITORY"]
    commit = os.environ["GITHUB_SHA"]
    tag = f"site-{commit}"
    endpoint = f"repos/{repository}/releases/tags/{tag}"
    release = get_json(endpoint, missing_ok=True)
    if release is None:
        run(["gh", "release", "create", tag, str(archive), "--repo", repository,
             "--target", commit, "--prerelease", "--title", f"Pages snapshot {commit}",
             "--notes", "Immutable public HTML/PDF snapshot for Pages history and recovery."])
        release = get_json(endpoint)
    if release["draft"]:
        raise ValueError("Incomplete draft snapshot; deployment is blocked")
    assets = [asset for asset in release["assets"] if asset["name"] == "site.tar.gz"]
    if len(assets) != 1 or assets[0]["state"] != "uploaded":
        raise ValueError("Missing or incomplete snapshot asset; deployment is blocked")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        run(["gh", "release", "download", tag, "--repo", repository,
             "--pattern", "site.tar.gz", "--dir", str(root)])
        expected = root / "expected"
        stored = root / "stored"
        extract_snapshot(archive, expected)
        extract_snapshot(root / "site.tar.gz", stored)
        if not files(expected) or files(expected) != files(stored):
            raise ValueError("Published snapshot differs from verified artifact")
    print(f"Verified complete public snapshot: {tag}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("current", "archive"))
    parser.add_argument("--archive", type=Path, default=Path("snapshot/site.tar.gz"))
    arguments = parser.parse_args()
    try:
        current_main() if arguments.command == "current" else ensure_snapshot(arguments.archive)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f"Deployment guard failed: {error}", file=sys.stderr)
        sys.exit(1)
