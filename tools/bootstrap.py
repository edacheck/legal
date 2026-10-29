"""Install hash-pinned Linux build binaries into this checkout only."""

import hashlib
import io
import os
import platform
import subprocess
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = {
    "actionlint": (
        "https://github.com/rhysd/actionlint/releases/download/v1.7.7/actionlint_1.7.7_linux_amd64.tar.gz",
        "023070a287cd8cccd71515fedc843f1985bf96c436b7effaecce67290e7e0757",
        "actionlint",
    ),
    "pandoc": (
        "https://github.com/jgm/pandoc/releases/download/3.6.4/pandoc-3.6.4-linux-amd64.tar.gz",
        "5def6e1ff535e397becce292ee97767a947306150b9fb1488003b67ac3417c5e",
        "pandoc-3.6.4/bin/pandoc",
    ),
    "typst": (
        "https://github.com/typst/typst/releases/download/v0.15.1/typst-x86_64-unknown-linux-musl.tar.xz",
        "a6d077d0a95eed5a2eba715b2dae06be954f624ccbf85758a03f389ded33118c",
        "typst-x86_64-unknown-linux-musl/typst",
    ),
}


def bootstrap():
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("Bootstrap requires Linux x86_64; native tools may be used on other hosts")
    destination = ROOT / ".tools" / "bin"
    destination.mkdir(parents=True, exist_ok=True)
    for name, (url, expected, member_name) in TOOLS.items():
        request = urllib.request.Request(url, headers={"User-Agent": "edacheck-legal-build"})
        with urllib.request.urlopen(request, timeout=120) as response:
            content = response.read(100 * 1024 * 1024)
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"Release archive checksum mismatch: {name}")
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as archive:
            member = archive.getmember(member_name)
            if not member.isfile():
                raise ValueError(f"Expected regular binary: {name}")
            with archive.extractfile(member) as stream:
                binary = stream.read()
        temporary = destination / f".{name}.partial"
        temporary.write_bytes(binary)
        temporary.chmod(0o755)
        os.replace(temporary, destination / name)
        subprocess.run([str(destination / name), "--version"], check=True)
    print(f"Pinned tools ready: {destination}")


if __name__ == "__main__":
    bootstrap()
