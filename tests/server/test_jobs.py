"""Jobs (AS-D §5; tests 4–6, 6a, 7a)."""

from __future__ import annotations

import json
import os
import threading

import pytest
from helpers import RATED, UNRATED, other_identity, slot

from calliope.server import JobFailed, PlyCache, analyse_game, parse_game
from calliope.server import files as files_module
from calliope.server.files import atomic_write
from calliope.server.jobs import DAMAGED, ENVIRONMENT_CHANGED, Jobs, QueueFull, job_id

DOC = {"schema": "calliope_result_v1"}


def stub(slot, parsed, plies, cache, *, profile, identity, on_ply):
    """The per-ply analysis replaced (AS-D §10.5): reports every ply, the even ones cached."""

    from calliope.server import PlyProgress

    for ply in plies:
        on_ply(PlyProgress(ply, parsed.sans[ply - 1], ply % 2 == 0, 0.5))
    return DOC


def failing(slot, parsed, plies, cache, **kwargs):
    raise JobFailed("ply 1: refused")


def jobs(tmp_path, analyse=stub, **kwargs) -> Jobs:
    the_slot = kwargs.pop("the_slot", None) or slot()[0]
    table = Jobs(tmp_path, the_slot, analyse=analyse, **kwargs)
    table.recover()
    return table


def test_4_the_same_game_is_one_job_and_other_headers_another(tmp_path) -> None:
    table = jobs(tmp_path)
    first, done = table.submit(RATED, None)
    again, _ = table.submit(RATED + "\n", None)
    assert first["id"] == again["id"] and not done and table.queue == [first["id"]]
    other, _ = table.submit(RATED.replace("Alice", "Carol"), None)
    assert other["id"] != first["id"] and len(table.queue) == 2
    ranged, _ = table.submit(RATED, "1-4")
    assert ranged["id"] not in (first["id"], other["id"])


def test_5_states_progress_and_a_failed_job_posted_again(tmp_path) -> None:
    table = jobs(tmp_path)
    a, _ = table.submit(RATED, None)
    b, _ = table.submit(UNRATED, "1-4")
    assert (a["state"], a["queue_position"], table.status(b["id"])["queue_position"]) == (
        "queued",
        1,
        2,
    )
    assert a["game"] == {"white": "Alice", "black": "Bob", "result": "*",
                         "site": "https://www.chess.com/game/live/1"}  # fmt: skip
    assert table.result(a["id"]) is None
    table.run_next()
    done = table.status(a["id"])
    assert done["state"] == "done" and done["plies"] == {
        "first": 1, "last": 10, "total": 10, "done": 10, "cached": 5,
    }  # fmt: skip
    assert json.loads(table.result(a["id"])) == DOC
    assert table.submit(RATED, None)[1] is True  # done: answered at once
    assert table.status(b["id"])["queue_position"] == 1
    table.analyse = failing
    table.run_next()
    failed = table.status(b["id"])
    assert failed["state"] == "failed" and failed["error"] == "ply 1: refused"
    assert (tmp_path / "games" / b["id"] / "error.json").exists()
    table.analyse = stub
    status, _ = table.submit(UNRATED, "1-4")  # posted again: queued again
    assert (
        status["state"] == "queued" and not (tmp_path / "games" / b["id"] / "error.json").exists()
    )
    table.run_next()
    assert table.status(b["id"])["state"] == "done"
    assert {s["id"] for s in table.summaries()} == {a["id"], b["id"]}  # newest first


def test_5_running_progress_reports_the_current_move_and_an_estimate(tmp_path) -> None:
    seen = []

    def observing(slot, parsed, plies, cache, *, profile, identity, on_ply):
        from calliope.server import PlyProgress

        on_ply(PlyProgress(1, parsed.sans[0], False, 2.0))
        seen.append(table.status(job["id"]))
        return DOC

    table = jobs(tmp_path, analyse=observing)
    job, _ = table.submit(UNRATED, None)
    table.run_next()
    running = seen[0]
    assert running["state"] == "running" and running["current"] == {"ply": 2, "san": "d5"}
    assert running["eta_seconds"] == 18 and running["plies"]["done"] == 1


def test_6_restart_resumes_and_cached_plies_are_not_analysed_again(tmp_path) -> None:
    table = Jobs(tmp_path, slot()[0])
    table.recover()
    analyse_game(slot()[0], parse_game(UNRATED), range(1, 5), PlyCache(tmp_path / "plies"))
    job, _ = table.submit(UNRATED, "1-8")
    resumed = Jobs(tmp_path, slot()[0])  # a new process on the same data directory
    resumed.recover()
    assert resumed.queue == [job["id"]] and resumed.status(job["id"])["state"] == "queued"
    resumed.run_next()
    status = resumed.status(job["id"])
    assert status["state"] == "done" and status["plies"]["cached"] == 4


def test_6_another_environment_is_never_resumed(tmp_path) -> None:
    """Review B4: the job's id names its environment; a changed engine fails it."""

    table = jobs(tmp_path)
    job, _ = table.submit(UNRATED, None)
    the_slot, _ = slot(port=_engine_with(other_identity()))
    changed = Jobs(tmp_path, the_slot, analyse=stub)
    changed.recover()
    status = changed.status(job["id"])
    assert status["state"] == "failed" and status["error"] == ENVIRONMENT_CHANGED
    assert changed.queue == []
    again, _ = changed.submit(UNRATED, None)  # a new id under the new environment
    assert again["id"] != job["id"] and changed.queue == [again["id"]]
    assert json.loads((tmp_path / "games" / job["id"] / "error.json").read_bytes())["message"] == (
        ENVIRONMENT_CHANGED
    )


def test_6_another_build_is_never_resumed(tmp_path) -> None:
    table = jobs(tmp_path)
    job, _ = table.submit(UNRATED, None)
    path = tmp_path / "games" / job["id"] / "job.json"
    record = json.loads(path.read_bytes())
    record["environment"]["build"] = "0" * 64
    path.write_text(json.dumps(record))
    changed = jobs(tmp_path)
    assert changed.status(job["id"])["error"] == ENVIRONMENT_CHANGED and changed.queue == []


def _engine_with(identity):
    from synthetic import synthetic

    from calliope.facts.search import ScriptedEngine

    return ScriptedEngine(identity, synthetic())


@pytest.mark.parametrize("damage", ["truncated", "not json", "no pgn", "wrong type"])
def test_6a_a_damaged_job_file_is_isolated(tmp_path, damage) -> None:
    """Re-review B2: the server starts, the damaged job fails, the sound one resumes."""

    table = jobs(tmp_path)
    sound, _ = table.submit(UNRATED, None)
    bad, _ = table.submit(RATED, None)
    path = tmp_path / "games" / bad["id"] / "job.json"
    raw = path.read_bytes()
    record = json.loads(raw)
    if damage == "truncated":
        path.write_bytes(raw[: len(raw) // 2])
    elif damage == "not json":
        path.write_bytes(b"\x00\x01")
    elif damage == "no pgn":
        del record["pgn"]
        path.write_text(json.dumps(record))
    else:
        record["pgn"] = 7
        path.write_text(json.dumps(record))
    (tmp_path / "games" / sound["id"] / "job.json.tmp").write_bytes(b'{"pgn": ')
    restarted = jobs(tmp_path)
    assert restarted.queue == [sound["id"]]
    status = restarted.status(bad["id"])
    assert status["state"] == "failed" and status["error"] == DAMAGED
    assert not (tmp_path / "games" / sound["id"] / "job.json.tmp").exists()
    assert (tmp_path / "games" / bad["id"] / "error.json").exists()
    again, _ = restarted.submit(RATED, None)  # posting it again repairs it
    assert again["state"] == "queued" and json.loads(path.read_bytes())["pgn"] == RATED


def test_6a_damaged_result_and_error_files(tmp_path) -> None:
    table = jobs(tmp_path)
    job, _ = table.submit(UNRATED, None)
    folder = tmp_path / "games" / job["id"]
    (folder / "result.json").write_bytes(b"{trunc")
    assert jobs(tmp_path).status(job["id"])["state"] == "queued"  # not JSON: absent, resumed
    (folder / "result.json").unlink()
    (folder / "error.json").write_bytes(b"[")
    status = jobs(tmp_path).status(job["id"])
    assert status["state"] == "failed" and status["error"] == DAMAGED


def test_6a_an_interrupted_write_keeps_the_previous_file(tmp_path, monkeypatch) -> None:
    path = tmp_path / "job.json"
    atomic_write(path, b'{"v": 1}')

    def interrupted(src, dst):
        raise OSError("killed before the rename")

    monkeypatch.setattr(files_module.os, "replace", interrupted)
    with pytest.raises(OSError):
        atomic_write(path, b'{"v": 2}')
    monkeypatch.setattr(files_module.os, "replace", os.replace)
    assert path.read_bytes() == b'{"v": 1}' and (tmp_path / "job.json.tmp").exists()


def test_7a_concurrent_posts_make_one_job_and_respect_the_queue_limit(tmp_path) -> None:
    table = jobs(tmp_path)
    barrier = threading.Barrier(8)
    ids, errors = [], []

    def post(pgn):
        barrier.wait()
        try:
            ids.append(table.submit(pgn, None)[0]["id"])
        except QueueFull as error:
            errors.append(error)

    threads = [threading.Thread(target=post, args=(UNRATED,)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(ids)) == 1 and table.queue == ids[:1] and not errors

    table = jobs(tmp_path / "limit")
    barrier = threading.Barrier(25)
    ids, errors = [], []
    games = [UNRATED.replace("1. e4", f'[White "player {i}"]\n\n1. e4') for i in range(25)]
    threads = [threading.Thread(target=post, args=(g,)) for g in games]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(table.queue) == 20 and len(ids) == 20 and len(errors) == 5


def test_the_job_id_is_the_documented_digest(tmp_path) -> None:
    table = jobs(tmp_path)
    parsed = parse_game(UNRATED)
    status, _ = table.submit(UNRATED, "2-5")
    assert status["id"] == job_id(parsed, range(2, 6), table.environment)
    assert (tmp_path.stat().st_mode & 0o777) == 0o700


def test_the_worker_thread_runs_the_queue(tmp_path) -> None:
    from calliope.server.jobs import wait_until

    table = jobs(tmp_path)
    table.start()
    try:
        job, _ = table.submit(UNRATED, None)
        assert wait_until(lambda: table.status(job["id"])["state"] == "done", 10)
    finally:
        table.stop(timeout=5)
