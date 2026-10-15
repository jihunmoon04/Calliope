"""Atomic files (AS-D §5.1, re-review B2): a reader never sees a partial file under its name.

Two processes may share the data directory (AG-D §9): every temporary file has a name of its own,
`<name>.<pid>.<token>.tmp`, and the start-up cleanup removes only the temporaries of processes
that are no longer running (and old-style `<name>.tmp` files, which name no process).
"""

from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

TMP = ".tmp"
_OWNED = re.compile(r"\.(\d+)\.[0-9a-f]{16}\.tmp$")


def temporary_name(path: Path) -> Path:
    """`<name>.<pid>.<token>.tmp` beside `path`: unique to this process and this write."""

    return path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(8)}{TMP}")


def atomic_write(path: Path, data: bytes) -> None:
    """Write a temporary file of its own in the same directory, flush and `fsync` it, then rename
    it over `path`."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = temporary_name(path)
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def running(pid: int) -> bool:
    """Is a process with this id running? (`PermissionError`: it is, as another user's; a
    reused id counts as running, AG-D §9.)"""

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def remove_temporaries(root: Path) -> int:
    """Remove left-over `*.tmp` files under `root` (start-up); returns how many. A temporary of a
    running process is another writer's file in flight and stays (AG-D §9)."""

    count = 0
    for tmp in root.rglob(f"*{TMP}"):
        if not tmp.is_file():
            continue
        owner = _OWNED.search(tmp.name)
        pid = int(owner[1]) if owner is not None else None
        if pid is not None and pid != os.getpid() and running(pid):  # our own: left by a former
            continue  # process under our id, nothing of ours is in flight at start-up
        tmp.unlink(missing_ok=True)
        count += 1
    return count


def read_or_none(path: Path) -> bytes | None:
    """The file's bytes, or None when it is missing or unreadable."""

    try:
        return path.read_bytes()
    except OSError:
        return None
