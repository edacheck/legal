"""Validate complete current and historical editions before activation."""

import argparse
import json
import sys
import unicodedata

from common import (OUTPUT, ROOT, digest, document, edition, execute,
                    registration_links, validate_edition, version_url)
from html_checks import Page, links
from render import ASSETS, inputs


def normalize(content):
    return "".join(unicodedata.normalize("NFKC", content).split())


def sources():
    config = edition()
    for slug in config["documents"]:
        document(config, slug)
    for path in ROOT.rglob("*"):
        if any(part in {"_build", ".tools", ".git", "__pycache__"} for part in path.parts):
            continue
        if path.is_file() and (path.suffix in {".py", ".md", ".css", ".typ", ".json", ".yml"}
                               or path.name == "Makefile"):
            if len(path.read_text(encoding="utf-8").splitlines()) >= 150:
                raise ValueError(f"Source exceeds line budget: {path.name}")
    return config


def verify_release(output, config=None, check_sources=False):
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    actual_config = validate_edition(manifest["edition"])
    if config is not None and actual_config != config:
        raise ValueError("Stale manifest edition")
    config = actual_config
    if set(manifest["documents"]) != set(config["documents"]) or set(manifest["assets"]) != ASSETS:
        raise ValueError("Unexpected public manifest entries")
    expected = {"manifest.json", *ASSETS}
    for name, expected_hash in manifest["assets"].items():
        if digest((output / name).read_bytes()) != expected_hash:
            raise ValueError(f"Asset hash mismatch: {name}")
    if json.loads((output / "registration-links.json").read_text()) != registration_links(config):
        raise ValueError("Registration links do not match edition")
    if check_sources and manifest["inputs"] != inputs():
        raise ValueError("Stale edition templates")
    for slug, record in manifest["documents"].items():
        if record["url"] != version_url(config, slug):
            raise ValueError("Document URL is not edition-bound")
        paths = {"html": f"{slug}/index.html", "pdf": f"{slug}/{slug}-{config['version']}.pdf"}
        for kind, relative in paths.items():
            if record[kind] != relative:
                raise ValueError("Unexpected document path")
            expected.add(relative)
            if digest((output / relative).read_bytes()) != record[f"{kind}_sha256"]:
                raise ValueError(f"Artifact hash mismatch: {slug}/{kind}")
        if check_sources:
            source = (ROOT / "documents" / f"{slug}.md").read_bytes()
            if digest(source) != record["source_sha256"]:
                raise ValueError(f"Stale source: {slug}")
            if digest(document(config, slug).encode("utf-8")) != record["document_sha256"]:
                raise ValueError(f"Stale assembled document: {slug}")
        parsed = Page()
        parsed.feed((output / record["html"]).read_text(encoding="utf-8"))
        extracted = execute(["pdftotext", "-layout", "-enc", "UTF-8", "-nopgbrk",
                             str(output / record["pdf"]), "-"]).decode("utf-8")
        visible = "".join(parsed.article)
        if not visible.strip() or normalize(visible) != normalize(extracted):
            raise ValueError(f"Actual HTML/PDF text mismatch: {slug}")
    actual = set()
    for path in output.rglob("*"):
        relative = path.relative_to(output)
        if path.is_symlink():
            raise ValueError("Symlinks are not public artifacts")
        if relative.parts[0] == "versions":
            continue
        if path.is_file():
            actual.add(str(relative))
            if path.suffix == ".html":
                parsed = Page()
                parsed.feed(path.read_text(encoding="utf-8"))
                links(path, parsed, output)
    if actual != expected:
        raise ValueError(f"Unexpected or missing public files: {actual ^ expected}")
    return manifest


def verify_site(output, config=None, check_sources=False):
    manifest = verify_release(output, config, check_sources)
    releases = output / "versions"
    current = manifest["edition"]["version"]
    if not (releases / current).is_dir():
        raise ValueError("Missing versioned current edition")
    for release in releases.iterdir():
        if not release.is_dir() or release.is_symlink():
            raise ValueError("Unexpected release entry")
        archived = verify_release(release)
        if archived["edition"]["version"] != release.name:
            raise ValueError("Release directory and edition version differ")
        if (release / "versions").exists():
            raise ValueError("Nested release archives are not allowed")
        if release.name == current and archived != manifest:
            raise ValueError("Current and versioned manifests differ")
    print(f"PASS {current}: complete current/versioned HTML/PDF, links and public allowlist")


def verify():
    verify_site(OUTPUT, sources(), check_sources=True)


if __name__ == "__main__":
    arguments = argparse.ArgumentParser()
    arguments.add_argument("--sources", action="store_true")
    options = arguments.parse_args()
    try:
        if options.sources:
            sources()
            print("PASS edition, source titles, placeholders and file line budget")
        else:
            verify()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Verification failed: {error}", file=sys.stderr)
        sys.exit(1)
