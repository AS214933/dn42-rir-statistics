from __future__ import annotations

import subprocess
from pathlib import Path


DEFAULT_REMOTE = "https://git.origami.pub/Bingxin/dn42-registry.git"
DEFAULT_BRANCH = "master"


def sync_registry(remote: str, branch: str, cache_dir: Path) -> Path:
    cache_dir = cache_dir.resolve()
    if not (cache_dir / ".git").is_dir():
        cache_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                branch,
                remote,
                str(cache_dir),
            ],
            check=True,
        )
        return cache_dir

    subprocess.run(
        ["git", "-C", str(cache_dir), "fetch", "--depth", "1", "origin", branch],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(cache_dir), "checkout", "-q", branch],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(cache_dir), "reset", "--hard", f"origin/{branch}"],
        check=True,
    )
    return cache_dir
