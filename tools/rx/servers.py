"""AF-D §6 (R1; review N1 of rev. 2): the worktree an earlier tool version's server runs from.

LT §16: the v7 worktree, checked out from WSL with LF line endings, hashed its reasoning data files
(curves, phrasebooks) into another `build_id` than the base's, and three `A@v7` runs stopped before
the model. `server-worktree` makes the worktree with the checkout's own `core.autocrlf` and checks,
byte for byte, every reasoning data file that is the same in git at both commits — the files whose
bytes would differ only by a checkout's line endings. An existing worktree is checked, never
replaced.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .run import REPO, SERVER_ROOTS, server_root

DATA_ROOT = Path("src") / "calliope" / "reasoning"  # the build hashes its curves and phrasebooks


def _git(*args: str, cwd: Path = REPO) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          check=True).stdout.strip()  # fmt: skip


def data_files(root: Path) -> list[Path]:
    """The reasoning build's data files under a checkout: every file under `DATA_ROOT` that is
    not Python."""

    base = root / DATA_ROOT
    return sorted(p.relative_to(root) for p in base.rglob("*")
                  if p.is_file() and p.suffix not in (".py", ".pyc"))  # fmt: skip


def _blob(rev: str, path: Path, cwd: Path = REPO) -> str | None:
    try:
        return _git("rev-parse", f"{rev}:{path.as_posix()}", cwd=cwd)
    except subprocess.CalledProcessError:
        return None


def check(root: Path, repo: Path = REPO) -> list[str]:
    """What makes a server worktree unlike the checkout the base was built from: each data file
    the same in git at the worktree's commit and the checkout's, whose bytes differ (a line-ending
    difference). An empty list passes."""

    if not root.is_dir():
        return [f"no worktree at {root}"]
    rev = _git("rev-parse", "HEAD", cwd=root)
    head = _git("rev-parse", "HEAD", cwd=repo)
    out = []
    for path in data_files(root):
        theirs = repo / path
        if not theirs.is_file() or _blob(rev, path, repo) != _blob(head, path, repo):
            continue  # not the same file in git: its bytes may differ for another reason
        if (root / path).read_bytes() != theirs.read_bytes():
            out.append(f"{path.as_posix()}: the bytes differ from the checkout's (line endings?)")
    return out


def make(tools: str, repo: Path = REPO) -> dict:
    """The variant's worktree: made from its tag with the checkout's `core.autocrlf`, or the
    existing one; then checked."""

    root = server_root(tools)
    if root is None:
        raise ValueError(f"tools {tools!r} runs from this repository, not a worktree")
    made = False
    if not root.exists():
        try:
            autocrlf = _git("config", "--get", "core.autocrlf", cwd=repo)
        except subprocess.CalledProcessError:
            # TB-D B6: WSL's git does not see the Windows checkout's setting; the checkout's own
            # files say which line endings it has
            crlf = b"\r\n" in (repo / "pyproject.toml").read_bytes()
            autocrlf = "true" if crlf else "false"
        root.parent.mkdir(parents=True, exist_ok=True)
        _git("-c", f"core.autocrlf={autocrlf}", "worktree", "add", "--detach", str(root),
             SERVER_ROOTS[tools], cwd=repo)  # fmt: skip
        made = True
    problems = check(root, repo)
    return {"tools": tools, "root": str(root), "made": made,
            "commit": _git("rev-parse", "HEAD", cwd=root), "problems": problems}  # fmt: skip
