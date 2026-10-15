"""AG-D §9 and §11 test 8: two processes on one data directory — one sound cache pair for a ply
both analyse, a reader that waits for a whole pair, and a start-up cleanup that spares another
running process's temporary files."""

from __future__ import annotations

import multiprocessing
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

from helpers import UNRATED, slot

from calliope.server import PlyCache, analyse_game, parse_game
from calliope.server import cache as cache_module
from calliope.server.files import remove_temporaries

FORK = multiprocessing.get_context("fork")


def _analyse(root: str, marks: str, barrier, delay: float) -> None:
    """A process analysing ply 1; it marks every write and holds the lock for `delay`."""

    original = cache_module.PlyCache._put

    def put(self, *args, **kwargs):
        Path(marks, f"wrote-{os.getpid()}").touch()
        time.sleep(delay)
        return original(self, *args, **kwargs)

    cache_module.PlyCache._put = put
    engine_slot, _ = slot()
    barrier.wait()
    analyse_game(engine_slot, parse_game(UNRATED), range(1, 2), PlyCache(Path(root)))


def test_two_processes_analysing_one_ply_leave_one_sound_pair(tmp_path) -> None:
    root, marks = tmp_path / "plies", tmp_path / "marks"
    marks.mkdir()
    barrier = FORK.Barrier(2)
    workers = [FORK.Process(target=_analyse, args=(str(root), str(marks), barrier, 0.5))
               for _ in range(2)]  # fmt: skip
    for w in workers:
        w.start()
    for w in workers:
        w.join(60)
    assert [w.exitcode for w in workers] == [0, 0]
    assert len(list(marks.iterdir())) == 1  # the second found the first's pair under the lock
    files = sorted(p.suffix for p in root.rglob("*") if p.is_file())
    assert files == [".graph", ".lock", ".tree"]  # no temporaries left
    engine_slot, _ = slot()
    _, progress = _get(engine_slot, root)
    assert progress[0].cached


def _get(engine_slot, root: Path):
    progress = []
    document = analyse_game(engine_slot, parse_game(UNRATED), range(1, 2), PlyCache(root),
                            on_ply=progress.append)  # fmt: skip
    return document, progress


def _write_slowly(root: str) -> None:
    """A writer that pauses between the tree and the graph, holding the exclusive lock."""

    original = cache_module.atomic_write

    def slow(path, data):
        original(path, data)
        if path.suffix == ".tree":
            time.sleep(1.0)

    cache_module.atomic_write = slow
    engine_slot, _ = slot()
    analyse_game(engine_slot, parse_game(UNRATED), range(1, 2), PlyCache(Path(root)))


def test_a_reader_never_sees_half_a_pair(tmp_path) -> None:
    root = tmp_path / "plies"
    writer = FORK.Process(target=_write_slowly, args=(str(root),))
    writer.start()
    deadline = time.monotonic() + 60
    while not list(root.rglob("*.tree")) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert list(root.rglob("*.tree")), "the writer wrote no tree"
    assert not list(root.rglob("*.graph"))  # half a pair on disk now
    engine_slot, _ = slot()
    _, progress = _get(engine_slot, root)  # waits on the shared lock for the whole pair
    writer.join(60)
    assert writer.exitcode == 0 and progress[0].cached


def test_the_cleanup_spares_a_running_processs_temporaries(tmp_path) -> None:
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    live = tmp_path / f"job.json.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    gone = tmp_path / f"job.json.{dead.pid}.{secrets.token_hex(8)}.tmp"
    old = tmp_path / "result.json.tmp"
    for path in (live, gone, old):
        path.write_bytes(b"{partial")
    assert remove_temporaries(tmp_path) == 2
    assert live.exists() and not gone.exists() and not old.exists()
