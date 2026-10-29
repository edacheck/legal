#!/usr/bin/env python3
"""Generate a reviewed public registration handoff outside Pages assets."""

import argparse
import base64
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common import OUTPUT, digest, document, edition, registration_links
from verify import verify_release

EDITION_FIELDS = {"version", "date", "status", "effective_date", "domain", "documents", "tools"}
LINK_FIELDS = {
    "EDACHECK_REGISTRATION_AGREEMENT_URL", "EDACHECK_REGISTRATION_POLICY_URL",
    "EDACHECK_REGISTRATION_DOCUMENT_VERSION", "EDACHECK_REGISTRATION_POLICY_VERSION",
}
ASSET_FIELDS = {"index.html", "style.css", "CNAME", ".nojekyll", "registration-links.json"}
PROFILE_FIELDS = {"schema_version", "document_id", "action_id"}
RECORD_FIELDS = {
    "url", "source_sha256", "document_sha256", "ast_sha256", "html", "html_sha256",
    "pdf", "pdf_sha256",
}
MANIFEST_FIELDS = {"edition", "tools", "documents", "assets", "inputs"}
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9-]*", re.ASCII)


def reject_duplicates(pairs):
    value = {}
    for name, item in pairs:
        if name in value:
            raise ValueError(f"Duplicate JSON field: {name}")
        value[name] = item
    return value


def read_json(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Required regular file is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)


def exact_fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"Unknown or missing {label} fields")


def encoded_document(config, slug, record):
    if (ROOT / "documents" / f"{slug}.md").is_symlink():
        raise ValueError(f"Document source must not be a symlink: {slug}")
    content = document(config, slug).encode("utf-8")
    if digest(content) != record["document_sha256"]:
        raise ValueError(f"Document digest mismatch: {slug}")
    encoded = base64.b64encode(content).decode("ascii")
    if base64.b64decode(encoded, validate=True) != content:
        raise ValueError(f"Non-canonical Base64 encoding: {slug}")
    return encoded


def handoff():
    config = edition()
    exact_fields(config, EDITION_FIELDS, "edition")
    exact_fields(config["tools"], {"pandoc", "typst"}, "edition tool")
    if config["status"] != "approved":
        raise ValueError("Only an approved edition can be handed off")
    profile = read_json(ROOT / "release-profile.json")
    exact_fields(profile, PROFILE_FIELDS, "profile")
    if profile["schema_version"] != 1:
        raise ValueError("Unsupported handoff schema version")
    for name in ("document_id", "action_id"):
        value = profile[name]
        if not isinstance(value, str) or IDENTIFIER.fullmatch(value) is None:
            raise ValueError(f"Unsafe ASCII {name}")
    if profile["document_id"] != "terms" or profile["action_id"] != "accept-terms":
        raise ValueError("Technical profile identifiers do not match the approved contract")

    release = OUTPUT / "versions" / config["version"]
    if release.is_symlink() or not release.is_dir():
        raise ValueError("Versioned release must be a regular directory")
    manifest_path = release / "manifest.json"
    links_path = release / "registration-links.json"
    manifest = read_json(manifest_path)
    links = read_json(links_path)
    exact_fields(manifest, MANIFEST_FIELDS, "manifest")
    exact_fields(manifest["edition"], EDITION_FIELDS, "manifest edition")
    exact_fields(manifest["tools"], set(config["tools"]), "manifest tool")
    exact_fields(manifest["documents"], set(config["documents"]), "manifest document")
    exact_fields(manifest["assets"], ASSET_FIELDS, "manifest asset")
    exact_fields(manifest["inputs"], {"style.css", "pdf.typ"}, "manifest input")
    exact_fields(links, LINK_FIELDS, "registration link")
    for slug, record in manifest["documents"].items():
        exact_fields(record, RECORD_FIELDS, f"{slug} document record")
    verify_release(release, config, check_sources=True)
    if links != registration_links(config):
        raise ValueError("Registration links do not match the approved edition")

    terms = manifest["documents"]["terms"]
    privacy = manifest["documents"]["privacy"]
    return {
        "schema_version": 1,
        "document_id": profile["document_id"],
        "action_id": profile["action_id"],
        "document_version": config["version"],
        "policy_version": config["version"],
        "terms": {"text_base64": encoded_document(config, "terms", terms),
                  "sha256": terms["document_sha256"], "url": terms["url"]},
        "privacy": {"text_base64": encoded_document(config, "privacy", privacy),
                    "sha256": privacy["document_sha256"], "url": privacy["url"]},
    }


def write_output(path, value):
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise ValueError("Handoff output must be a regular file")
    repository = ROOT.resolve()
    target = path.resolve()
    if target == repository or repository in target.parents:
        raise ValueError("Handoff must not be written inside the repository")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".release-handoff.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        write_output(arguments.output, handoff())
        print(f"Generated public release handoff: {arguments.output}")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"Handoff failed: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
