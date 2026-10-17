"""CC-D §6 for the ply cache: writing without the replay (C1), `checked` (C5), reusing loaded pairs
(C2) within their bounds, one generation of a pair under the key's lock, and kept pairs shared,
never copied."""

from __future__ import annotations

import threading
from dataclasses import replace

import pytest
from helpers import UNRATED, slot

from calliope.facts import EngineProfile, FactEngine
from calliope.reasoning import Reasoner, build_digest
from calliope.reasoning.storage import save
from calliope.server import (
    PlyCache,
    StoreFailed,
    analyse_game,
    analyse_ply,
    normalized_ply,
    parse_game,
)
from calliope.server import cache as cache_module

PROFILE = EngineProfile()


def _ply(tmp_path, ply: int = 1, **options):
    """A cache, the key, request and build of `ply`, and a fresh analysis of it."""

    parsed, the_slot = parse_game(UNRATED), slot()[0]
    port = the_slot.port
    build = Reasoner(FactEngine(engine=port)).build()
    expected = normalized_ply(parsed, ply, PROFILE)
    key = PlyCache.key(expected, build_digest(build), port.identity, PROFILE)
    fingerprint = list(port.identity.fingerprint())
    analysis, rendered = analyse_ply(the_slot, parsed, ply, PROFILE, fingerprint)
    return PlyCache(tmp_path, **options), key, expected, build, analysis, rendered


class Loads:
    """Counts `load` in the cache module."""

    def __init__(self, monkeypatch) -> None:
        self.calls = 0
        real = cache_module.load

        def counted(*args, **kwargs):
            self.calls += 1
            return real(*args, **kwargs)

        monkeypatch.setattr(cache_module, "load", counted)


# -- C1, C5: writing --------------------------------------------------------------------------------


def test_a_write_returns_the_pipelines_analysis_as_written(tmp_path, monkeypatch) -> None:
    cache, key, expected, build, analysis, rendered = _ply(tmp_path)
    loads = Loads(monkeypatch)
    stored = cache.put(key, analysis, rendered, expected, build)
    assert stored.analysis is analysis and stored.rendered is rendered
    assert stored.checked == "written" and loads.calls == 0
    tree_path, graph_path = cache.paths(key)
    assert (tree_path.read_bytes(), graph_path.read_bytes()) == save(analysis, rendered)
    assert cache.counts == {"written": 1, "replayed": 0, "reused": 0}


def test_with_verify_writes_the_written_bytes_are_replayed(tmp_path, monkeypatch) -> None:
    cache, key, expected, build, analysis, rendered = _ply(tmp_path, verify_writes=True)
    loads = Loads(monkeypatch)
    stored = cache.put(key, analysis, rendered, expected, build)
    assert stored.checked == "replayed" and loads.calls == 1
    assert stored.analysis is not analysis
    assert save(stored.analysis, stored.rendered) == save(analysis, rendered)


@pytest.mark.parametrize("fault", ["read back", "request", "build"])
def test_a_failed_check_removes_both_files(tmp_path, monkeypatch, fault) -> None:
    cache, key, expected, build, analysis, rendered = _ply(tmp_path)
    if fault == "read back":
        real = cache_module.atomic_write
        monkeypatch.setattr(
            cache_module, "atomic_write", lambda path, data: real(path, data + b"x")
        )
    if fault == "request":
        expected = normalized_ply(parse_game(UNRATED), 2, PROFILE)
    if fault == "build":
        build = replace(build, templates=())
    with pytest.raises(StoreFailed):
        cache.put(key, analysis, rendered, expected, build)
    assert not any(p.exists() for p in cache.paths(key))
    assert cache.kept()["pairs"] == 0


@pytest.mark.parametrize("failing", [1, 2])
def test_a_write_failing_part_way_leaves_no_pair_and_no_temporary(
    tmp_path, monkeypatch, failing
) -> None:
    """Review F1: the tree's or the graph's write fails (`fsync`, as on a full disk): `StoreFailed`,
    neither file left — not a new tree beside an old graph — and no temporary file."""

    from calliope.server import files

    cache, key, expected, build, analysis, rendered = _ply(tmp_path)
    tree_path, graph_path = cache.paths(key)
    tree_path.parent.mkdir(parents=True)
    tree_path.write_bytes(b"{old")  # an earlier, unsound pair: a miss, so the put writes
    graph_path.write_bytes(b"{old")
    calls, fsync = [], files.os.fsync

    def full_disk(fd):
        calls.append(fd)
        if len(calls) == failing:
            raise OSError(28, "No space left on device")
        return fsync(fd)

    monkeypatch.setattr(files.os, "fsync", full_disk)
    with pytest.raises(StoreFailed, match="OSError"):
        cache.put(key, analysis, rendered, expected, build)
    left = sorted(p.name for p in tree_path.parent.iterdir())
    assert left == [f"{key}.lock"]  # no tree, no graph, no temporary
    assert cache.kept()["pairs"] == 0


def test_a_failed_write_fails_the_job(tmp_path, monkeypatch) -> None:
    from calliope.server import JobFailed, files

    monkeypatch.setattr(files.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError(28, "full")))
    with pytest.raises(JobFailed, match="ply 1 failed its check: OSError"):
        analyse_game(slot()[0], parse_game(UNRATED), range(1, 2), PlyCache(tmp_path))


# -- C2: reusing loaded pairs -----------------------------------------------------------------------


def test_a_second_read_reuses_the_pair_without_a_replay(tmp_path, monkeypatch) -> None:
    writer, key, expected, build, analysis, rendered = _ply(tmp_path)
    writer.put(key, analysis, rendered, expected, build)
    loads = Loads(monkeypatch)
    assert writer.get(key, expected, build).analysis is analysis  # the written pair, kept
    reader = PlyCache(tmp_path)  # another process: replays once, then reuses
    first = reader.get(key, expected, build)
    second = reader.get(key, expected, build)
    assert first.checked == "replayed" and second is first and loads.calls == 1
    assert reader.counts == {"written": 0, "replayed": 1, "reused": 1}


def test_changed_removed_or_foreign_files_never_reuse_a_pair(tmp_path, monkeypatch) -> None:
    cache, key, expected, build, analysis, rendered = _ply(tmp_path)
    cache.put(key, analysis, rendered, expected, build)
    loads = Loads(monkeypatch)
    # the kept pair is not served for another build or request: the bytes are loaded and refused
    assert cache.get(key, expected, replace(build, templates=())) is None
    assert cache.get(key, normalized_ply(parse_game(UNRATED), 2, PROFILE), build) is None
    assert loads.calls == 2
    _, graph_path = cache.paths(key)
    graph_path.write_bytes(graph_path.read_bytes() + b" ")  # one byte more: other digests
    found = cache.get(key, expected, build)
    assert loads.calls == 3 and (found is None or found.analysis is not analysis)
    graph_path.unlink()
    assert cache.get(key, expected, build) is None and loads.calls == 3  # a miss before the LRU


def test_the_kept_pairs_hold_both_bounds(tmp_path, monkeypatch) -> None:
    parsed, the_slot = parse_game(UNRATED), slot()[0]
    analyse_game(the_slot, parsed, range(1, 5), PlyCache(tmp_path))
    port = the_slot.port
    build = Reasoner(FactEngine(engine=port)).build()
    keys = []
    for ply in range(1, 5):
        expected = normalized_ply(parsed, ply, PROFILE)
        keys.append((PlyCache.key(expected, build_digest(build), port.identity, PROFILE), expected))
    by_count = PlyCache(tmp_path, max_loaded=2)
    for key, expected in keys:
        by_count.get(key, expected, build)
    assert by_count.kept()["pairs"] == 2
    loads = Loads(monkeypatch)
    by_count.get(*keys[0], build)  # evicted as the least recently used: replayed again
    by_count.get(*keys[3], build)  # the most recent: still kept
    assert loads.calls == 1
    sizes = [sum(p.stat().st_size for p in by_count.paths(k)) for k, _ in keys]
    room = max(sizes) * cache_module.BYTES_PER_FILE_BYTE * 2
    by_memory = PlyCache(tmp_path, max_loaded_mb=1)
    by_memory.max_loaded_bytes = room  # room for two of the largest pair's estimate
    for key, expected in keys:
        by_memory.get(key, expected, build)
    assert 1 <= by_memory.kept()["pairs"] < 4 and by_memory.kept()["estimated_bytes"] <= room
    for none in (PlyCache(tmp_path, max_loaded=0), PlyCache(tmp_path, max_loaded_mb=0)):
        none.get(*keys[0], build)
        assert none.kept() == {"pairs": 0, "estimated_bytes": 0}
    with pytest.raises(ValueError, match="at least 0"):
        PlyCache(tmp_path, max_loaded=-1)


def test_two_threads_never_get_a_pair_of_other_bytes(tmp_path) -> None:
    writer, key, expected, build, analysis, rendered = _ply(tmp_path)
    writer.put(key, analysis, rendered, expected, build)
    reader, got = PlyCache(tmp_path), []
    threads = [threading.Thread(target=lambda: got.append(reader.get(key, expected, build)))
               for _ in range(4)]  # fmt: skip
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(got) == 4 and {g.bundle for g in got} == {writer.get(key, expected, build).bundle}


# -- one generation of a pair (CC-D §3.1) -----------------------------------------------------------


def test_a_reader_waits_for_a_writer_and_never_mixes_two_writes(tmp_path) -> None:
    """Review F2: the reader is shown blocked while the writer holds the lock between its tree and
    its graph, and done only after the writer lets go; what it then reads is one whole pair."""

    cache, key, expected, build, analysis, rendered = _ply(tmp_path)
    cache.put(key, analysis, rendered, expected, build)
    *_, analysis2, rendered2 = _ply(tmp_path / "other", ply=2)
    other_tree, other_graph = save(analysis2, rendered2)
    tree_path, graph_path = cache.paths(key)
    reader = PlyCache(tmp_path)
    held, release, found = threading.Event(), threading.Event(), []
    read_started, read_done = threading.Event(), threading.Event()

    def writer():  # another writer of the key: a tree of a new generation, then its graph
        with cache.lock(key, exclusive=True):
            tree_path.write_bytes(other_tree)
            held.set()
            release.wait(5)
            graph_path.write_bytes(other_graph)

    def read():
        read_started.set()  # the reader is about to ask for the key's shared lock (review N2)
        found.append(reader.get(key, expected, build))
        read_done.set()

    writing = threading.Thread(target=writer)
    writing.start()
    assert held.wait(5)  # the writer holds the lock with half a pair written
    reading = threading.Thread(target=read)
    reading.start()
    assert read_started.wait(5)
    assert not read_done.wait(0.3)  # blocked on the shared lock while the writer holds it
    release.set()
    writing.join(5)
    reading.join(5)
    assert read_done.is_set() and found == [None]  # the whole new pair is ply 2's: a miss


def test_files_replaced_outside_the_lock_go_through_load(tmp_path, monkeypatch) -> None:
    cache, key, expected, build, analysis, rendered = _ply(tmp_path)
    cache.put(key, analysis, rendered, expected, build)
    *_, analysis2, rendered2 = _ply(tmp_path / "other", ply=2)
    tree_path, graph_path = cache.paths(key)
    other_tree, other_graph = save(analysis2, rendered2)
    tree_path.write_bytes(other_tree)  # a tree of another write, with the old graph
    loads = Loads(monkeypatch)
    assert cache.get(key, expected, build) is None and loads.calls == 1  # mixed: not reused
    graph_path.write_bytes(other_graph)  # now a whole pair of ply 2
    assert cache.get(key, expected, build) is None and loads.calls == 2  # loads, wrong request
