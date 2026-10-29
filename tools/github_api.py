"""Read GitHub JSON; only an explicit 404 may mean an absent resource."""

import json
import os
import urllib.error
import urllib.request


def get_json(path, missing_ok=False):
    request = urllib.request.Request("https://api.github.com/" + path, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + os.environ["GH_TOKEN"],
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "edacheck-legal-ci",
    })
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read(4 * 1024 * 1024))
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        if status == 404 and missing_ok:
            return None
        raise ValueError(f"GitHub API failed with HTTP {status}") from None
