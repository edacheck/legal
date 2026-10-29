"""Copy reviewed GitHub branches and immutable tags to the GitLab backup."""

import subprocess

BACKUP = "ssh://git@gitlab.edacheck.ru:2222/foodapp/legal.git"


def git(*arguments):
    result = subprocess.run(["git", *arguments], text=True, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr)
    return result.stdout.strip()


def backup():
    if git("remote", "get-url", "gitlab-backup") != BACKUP:
        raise ValueError("Unexpected GitLab backup remote")
    git("fetch", "origin", "--tags")
    references = []
    for branch in ("dev", "main"):
        commit = git("rev-parse", f"refs/remotes/origin/{branch}")
        references.append(f"{commit}:refs/heads/{branch}")
    for tag in git("tag", "--list").splitlines():
        references.append(f"refs/tags/{tag}:refs/tags/{tag}")
    print(git("push", "--atomic", "--push-option=ci.skip", "gitlab-backup", *references))
    print("GitLab backup synchronized; no force-push, pruning, Pages or services")


if __name__ == "__main__":
    backup()
