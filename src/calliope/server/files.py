"""Atomic files (AS-D §5.1, re-review B2): a reader never sees a partial file under its name.

Two processes may share the data directory (AG-D §9): every temporary file has a name of its own,
`<name>.<pid>.<token>.tmp`, and the start-up cleanup removes only the temporaries of processes
that are no longer running (and old-style `<name>.tmp` files, which name no process).
"""

from __future__ import annotations

import os
import re
import secrets
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _ERROR_ACCESS_DENIED = 5
    _STILL_ACTIVE = 259
    _ERROR_SHARING_VIOLATION = 32

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.OpenProcess.argtypes = [
        ctypes.wintypes.DWORD,
        ctypes.wintypes.BOOL,
        ctypes.wintypes.DWORD,
    ]
    _kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE
    _kernel32.GetExitCodeProcess.argtypes = [
        ctypes.wintypes.HANDLE,
        ctypes.POINTER(ctypes.wintypes.DWORD),
    ]
    _kernel32.GetExitCodeProcess.restype = ctypes.wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
    _kernel32.CloseHandle.restype = ctypes.wintypes.BOOL

TMP = ".tmp"
_OWNED = re.compile(r"\.(\d+)\.[0-9a-f]{16}\.tmp$")


def long_path(path: Path) -> Path:
    """Return a Win32 extended-length path so nested hashes never hit MAX_PATH."""

    if sys.platform != "win32":
        return path
    resolved = os.path.abspath(os.fspath(path))
    if not resolved.startswith("\\\\?\\"):
        if resolved.startswith("\\\\"):
            return Path("\\\\?\\UNC\\" + resolved[2:])
        return Path("\\\\?\\" + resolved)
    return path


def temporary_name(path: Path) -> Path:
    """`<name>.<pid>.<token>.tmp` beside `path`: unique to this process and this write."""

    return path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(8)}{TMP}")


def _replace_file(tmp: Path, path: Path) -> None:
    if sys.platform != "win32":
        os.replace(tmp, path)
        return
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError as err:
            if getattr(err, "winerror", None) != _ERROR_SHARING_VIOLATION or attempt == 4:
                raise
            time.sleep(0.01 * (attempt + 1))


def atomic_write(path: Path, data: bytes) -> None:
    """Write a temporary file of its own in the same directory, flush and `fsync` it, then rename
    it over `path`. A failure removes the temporary file and leaves `path` as it was."""

    target = long_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = long_path(temporary_name(path))
    try:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_file(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def running(pid: int) -> bool:
    """Is a process with this id running? (`PermissionError`: it is, as another user's; a
    reused id counts as running, AG-D §9.)"""

    if pid <= 0:
        return False
    if sys.platform == "win32":
        handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ctypes.get_last_error() == _ERROR_ACCESS_DENIED
        try:
            code = ctypes.wintypes.DWORD()
            ok = _kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok and code.value == _STILL_ACTIVE)
        finally:
            _kernel32.CloseHandle(handle)
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
    for tmp in long_path(root).rglob(f"*{TMP}"):
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
        return long_path(path).read_bytes()
    except OSError:
        return None
