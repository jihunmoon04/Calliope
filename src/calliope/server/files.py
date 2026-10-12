"""Atomic files (AS-D §5.1, re-review B2): a reader never sees a partial file under its name."""

from __future__ import annotations

import os
from pathlib import Path

TMP = ".tmp"


def atomic_write(path: Path, data: bytes) -> None:
    """Write `<name>.tmp` in the same directory, flush and `fsync` it, then rename it over `path`."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + TMP)
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def remove_temporaries(root: Path) -> int:
    """Remove left-over `*.tmp` files under `root` (start-up); returns how many."""

    count = 0
    for tmp in root.rglob(f"*{TMP}"):
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
            count += 1
    return count


def read_or_none(path: Path) -> bytes | None:
    """The file's bytes, or None when it is missing or unreadable."""

    try:
        return path.read_bytes()
    except OSError:
        return None
