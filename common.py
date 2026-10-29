"""Shared edition validation and offline document conversion."""

import hashlib
import json
import re
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "_build" / "site"


def digest(content):
    return hashlib.sha256(content).hexdigest()


def execute(arguments, content=None):
    result = subprocess.run(arguments, input=content, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(f"{arguments[0]} failed: {result.stderr.decode('utf-8')}")
    return result.stdout


def edition():
    config = json.loads((ROOT / "edition.json").read_text(encoding="utf-8"))
    validate_edition(config)
    actual = {path.stem for path in (ROOT / "documents").glob("*.md")}
    if actual != set(config["documents"]):
        raise ValueError("Unlisted or missing Markdown documents")
    return config


def validate_edition(config):
    if config["status"] not in {"draft", "approved"}:
        raise ValueError("Unknown edition status")
    date.fromisoformat(config["date"])
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", config["version"]):
        raise ValueError("Unsafe edition version")
    if config["domain"] != "legal.edacheck.ru":
        raise ValueError("Review links and domain before changing publication host")
    if set(config["documents"]) != {"privacy", "terms", "deletion"}:
        raise ValueError("Unexpected public document set")
    if config["status"] == "approved":
        date.fromisoformat(config["effective_date"])
    elif config["effective_date"] is not None:
        raise ValueError("A draft must not have an effective date")
    return config


def tools(config):
    versions = {}
    for name, expected in config["tools"].items():
        first = execute([name, "--version"]).decode("utf-8").splitlines()[0]
        if first.split()[1] != expected:
            raise ValueError(f"Expected {name} {expected}, found {first}")
        versions[name] = first
    execute(["pdftotext", "-v"])
    return versions


def document(config, slug):
    source = (ROOT / "documents" / f"{slug}.md").read_text(encoding="utf-8")
    expected = f"# {config['documents'][slug]}\n"
    if not source.startswith(expected):
        raise ValueError(f"Unexpected title: {slug}")
    if re.search(r"\[(?:ДОМЕН|EMAIL|НАЗВАНИЕ|ПЕРЕЧЕНЬ|СТРАНА)", source):
        raise ValueError(f"Unfilled placeholder: {slug}")
    if config["status"] == "draft":
        status = "Проект для согласования. Не вступил в силу."
    else:
        status = f"Вступает в силу: {config['effective_date']}."
    notice = f"> {status} Версия: {config['version']}. Дата редакции: {config['date']}."
    content = source.replace(expected, expected + f"\n{notice}\n", 1)
    for target in config["documents"]:
        current = f"https://{config['domain']}/{target}/"
        content = content.replace(f"]({current})", f"]({version_url(config, target)})")
    return content


def version_url(config, slug):
    return f"https://{config['domain']}/versions/{config['version']}/{slug}/"


def registration_links(config):
    return {
        "EDACHECK_REGISTRATION_AGREEMENT_URL": version_url(config, "terms"),
        "EDACHECK_REGISTRATION_POLICY_URL": version_url(config, "privacy"),
        "EDACHECK_REGISTRATION_DOCUMENT_VERSION": config["version"],
        "EDACHECK_REGISTRATION_POLICY_VERSION": config["version"],
    }
