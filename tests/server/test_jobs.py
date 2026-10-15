"""Jobs (AS-D §5; tests 4–6, 6a, 7a)."""

from __future__ import annotations

import json
import os
import threading

import pytest
from helpers import RATED, UNRATED, other_identity, slot

from calliope.server import JobFailed, PlyCache, analyse_game, parse_game
from calliope.server import files as files_module
from calliope.server import jobs as jobs_module
from calliope.server.files import atomic_write
from calliope.server.jobs import DAMAGED, ENVIRONMENT_CHANGED, Jobs, QueueFull, job_id

DOC = {"schema": "calliope_result_v1"}


def stub(slot, parsed, plies, cache, *, profile, engine, on_ply):
    """The per-ply analysis replaced (AS-D §10.5): reports every ply, the even ones cached."""

    from calliope.server import PlyProgress

    for ply in plies:
        on_ply(PlyProgress(ply, parsed.sans[ply - 1], ply % 2 == 0, 0.5))
    return DOC


def failing(slot, parsed, plies, cache, **kwargs):
    raise JobFailed("ply 1: refused")


def accept(data, parsed, plies, env) -> bool:
    """The result check for the stub's minimal document (`result_matches` is tested below)."""

    try:
        return json.loads(data) == DOC
    except ValueError:
        return False


def jobs(tmp_path, analyse=stub, **kwargs) -> Jobs:
    the_slot = kwargs.pop("the_slot", None) or slot()[0]
    kwargs.setdefault("check", accept)
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

    def observing(slot, parsed, plies, cache, *, profile, engine, on_ply):
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
    changed = Jobs(tmp_path, the_slot, analyse=stub, check=accept)
    changed.recover()
    status = changed.status(job["id"])
    assert status["state"] == "failed" and status["error"] == ENVIRONMENT_CHANGED
    assert changed.queue == []
    again, _ = changed.submit(UNRATED, None)  # a new id under the new environment
    assert again["id"] != job["id"] and changed.queue == [again["id"]]
    assert json.loads((tmp_path / "games" / job["id"] / "error.json").read_bytes())["message"] == (
        ENVIRONMENT_CHANGED
    )


def test_6_another_build_is_never_resumed(tmp_path, monkeypatch) -> None:
    table = jobs(tmp_path)
    job, _ = table.submit(UNRATED, None)
    monkeypatch.setattr(jobs_module, "build_of", lambda port: "0" * 64)  # the code changed
    changed = jobs(tmp_path)
    assert changed.status(job["id"])["error"] == ENVIRONMENT_CHANGED and changed.queue == []


def test_6_a_job_file_edited_to_another_environment_is_damaged(tmp_path) -> None:
    """AS1 review B2: the stored environment no longer hashes to the directory's name."""

    table = jobs(tmp_path)
    job, _ = table.submit(UNRATED, None)
    path = tmp_path / "games" / job["id"] / "job.json"
    record = json.loads(path.read_bytes())
    record["environment"]["build"] = "0" * 64
    path.write_text(json.dumps(record))
    assert jobs(tmp_path).status(job["id"])["error"] == DAMAGED


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


@pytest.mark.parametrize("edit", ["another game", "another range"])
def test_b2_a_job_file_with_another_game_is_damaged(tmp_path, edit) -> None:
    """AS1 review B2: valid JSON and types, but not the job its directory names."""

    table = jobs(tmp_path)
    job, _ = table.submit(UNRATED, None)
    path = tmp_path / "games" / job["id"] / "job.json"
    record = json.loads(path.read_bytes())
    if edit == "another game":
        record["pgn"] = RATED
    else:
        record["plies"] = "1-3"
    path.write_text(json.dumps(record))
    restarted = jobs(tmp_path)
    status = restarted.status(job["id"])
    assert status["state"] == "failed" and status["error"] == DAMAGED and restarted.queue == []


def _done_job(tmp_path, pgn=UNRATED, plies="1-2"):
    table = Jobs(tmp_path, slot()[0])  # the real pipeline over the synthetic engine
    table.recover()
    job, _ = table.submit(pgn, plies)
    table.run_next()
    assert table.status(job["id"])["state"] == "done"
    return job["id"], tmp_path / "games" / job["id"] / "result.json"


def test_b3_a_sound_result_is_done_after_a_restart(tmp_path) -> None:
    jid, _ = _done_job(tmp_path)
    restarted = Jobs(tmp_path, slot()[0])
    restarted.recover()
    assert restarted.status(jid)["state"] == "done" and restarted.result(jid) is not None


@pytest.mark.parametrize(
    "tamper",
    [
        "empty object", "schema", "build", "engine", "another game", "plies", "not stored",
        "no text", "no segments", "no claims", "no evaluation", "bad digest", "grade type",
    ],
)  # fmt: skip
def test_b3_a_result_that_is_not_this_jobs_is_not_done(tmp_path, tamper) -> None:
    """AS1 review B3 and re-review B3: valid JSON is not enough, nor the right identifiers; a
    document that breaks the shipped schema or is another job's is not done. The job is resumed
    and nothing is served."""

    jid, path = _done_job(tmp_path)
    doc = json.loads(path.read_bytes())
    if tamper == "empty object":
        doc = {}
    elif tamper == "schema":
        doc["schema"] = "calliope_result_v2"
    elif tamper == "build":
        doc["provenance"]["build_digest"] = "0" * 64
    elif tamper == "engine":
        doc["provenance"]["engine"]["binary_sha256"] = "0" * 64
    elif tamper == "another game":
        _, other = _done_job(tmp_path / "other", pgn=RATED)
        doc = json.loads(other.read_bytes())
    elif tamper == "plies":
        doc["plies"] = doc["plies"][:1]
    elif tamper == "not stored":
        doc["plies"][0]["bundle"]["stored"] = False
    elif tamper == "bad digest":  # AS1 re-review B3: the schema's structure, not only identity
        doc["plies"][0]["bundle"]["graph"] = "zz"
    elif tamper == "grade type":
        doc["plies"][0]["grade"] = 3
    else:
        del doc["plies"][0][tamper.removeprefix("no ")]
    path.write_text(json.dumps(doc))
    restarted = Jobs(tmp_path, slot()[0])
    restarted.recover()
    assert restarted.status(jid)["state"] == "queued" and restarted.result(jid) is None
    restarted.run_next()  # analysed again (from the cache) and the result replaced
    assert restarted.status(jid)["state"] == "done"
    assert json.loads(path.read_bytes())["schema"] == "calliope_result_v1"


def _ports(*ports, then=None):
    """A slot handing out `ports` in turn, then `then()` (default: the synthetic engine)."""

    from synthetic import engine

    from calliope.server import EngineSlot

    queue, started = list(ports), []

    def start():
        started.append(queue.pop(0) if queue else (then or engine)())
        return started[-1]

    return EngineSlot(start), started


def test_b1_a_job_never_runs_on_an_engine_it_was_not_posted_for(tmp_path) -> None:
    """AS1 review B1: J1's restart brings engine B; J2 (posted for A) fails, never runs on B;
    the server's environment follows B, so posting J2's game again runs it under B."""

    from helpers import Failing

    the_slot, _ = _ports(Failing({1}), then=lambda: Failing(set(), identity=other_identity()))
    table = Jobs(tmp_path, the_slot)
    table.recover()
    j1, _ = table.submit(UNRATED, "1-2")
    j2, _ = table.submit(RATED, "1-2")
    table.run_next()
    assert table.status(j1["id"])["state"] == "failed"
    table.run_next()
    status = table.status(j2["id"])
    assert status["state"] == "failed" and status["error"] == ENVIRONMENT_CHANGED
    assert not (tmp_path / "games" / j2["id"] / "result.json").exists()
    again, _ = table.submit(RATED, "1-2")
    assert again["id"] != j2["id"]
    table.run_next()
    assert table.status(again["id"])["state"] == "done"
    document = json.loads(table.result(again["id"]))
    assert document["provenance"]["engine"]["binary_sha256"] == "6" * 64


def test_b1_an_engine_that_failed_twice_is_not_reused(tmp_path) -> None:
    from helpers import Failing

    dead = Failing({1, 2, 3, 4, 5, 6, 7, 8})
    the_slot, started = _ports(Failing({1}), dead)
    table = Jobs(tmp_path, the_slot)
    table.recover()
    j1, _ = table.submit(UNRATED, "1-2")
    j2, _ = table.submit(RATED, "1-2")
    table.run_next()
    assert "failed twice" in table.status(j1["id"])["error"]
    table.run_next()
    assert table.status(j2["id"])["state"] == "done"
    assert started[-1] is not dead and len(started) == 3  # a fresh engine for J2


def test_detail_is_part_of_the_job_and_gives_each_ply_its_analysis(tmp_path) -> None:
    """DF-D §4.3: `detail` asks for `analysis`; it names another job, and survives a restart."""

    table = Jobs(tmp_path, slot()[0])  # the real pipeline over the synthetic engine
    table.recover()
    plain, _ = table.submit(UNRATED, "1-2")
    full, _ = table.submit(UNRATED, "1-2", True)
    parsed = parse_game(UNRATED)
    assert plain["id"] == job_id(parsed, range(1, 3), table.environment)  # unchanged without it
    assert full["id"] == job_id(parsed, range(1, 3), table.environment, True) != plain["id"]
    table.run_next()
    table.run_next()
    documents = {jid: json.loads(table.result(jid)) for jid in (plain["id"], full["id"])}
    assert all("analysis" not in p for p in documents[plain["id"]]["plies"])
    assert all("analysis" in p for p in documents[full["id"]]["plies"])
    restarted = Jobs(tmp_path, slot()[0])
    restarted.recover()
    assert restarted.status(full["id"])["state"] == "done"


def test_b2_a_detail_job_does_not_accept_a_result_without_analysis(tmp_path) -> None:
    """DF1 review B2: a plain result in a detail job's folder is not that job's result."""

    plain_id, plain_result = _done_job(tmp_path)  # a finished job without detail
    table = Jobs(tmp_path, slot()[0])
    table.recover()
    full, _ = table.submit(UNRATED, "1-2", True)
    folder = tmp_path / "games" / full["id"]
    (folder / "result.json").write_bytes(plain_result.read_bytes())
    restarted = Jobs(tmp_path, slot()[0])
    restarted.recover()
    assert restarted.status(full["id"])["state"] == "queued"  # resumed, not done
    assert restarted.status(plain_id)["state"] == "done"  # the plain job keeps its result
    restarted.run_next()
    document = json.loads(restarted.result(full["id"]))
    assert all("analysis" in p for p in document["plies"])


def test_b3_a_damaged_detail_job_posted_again_runs_with_detail(tmp_path) -> None:
    """DF1 review B3: job.json loses `detail` → DAMAGED at restart → posted again with detail
    → the job runs with it and its result carries `analysis`."""

    table = Jobs(tmp_path, slot()[0])
    table.recover()
    full, _ = table.submit(UNRATED, "1-2", True)
    path = tmp_path / "games" / full["id"] / "job.json"
    record = json.loads(path.read_bytes())
    record.pop("detail")  # the file now names the job without detail: its id does not match
    path.write_text(json.dumps(record))
    restarted = Jobs(tmp_path, slot()[0])
    restarted.recover()
    assert restarted.status(full["id"])["state"] == "failed"
    status, _ = restarted.submit(UNRATED, "1-2", True)
    assert status["id"] == full["id"] and restarted.jobs[full["id"]].detail is True
    restarted.run_next()
    assert restarted.status(full["id"])["state"] == "done"
    document = json.loads(restarted.result(full["id"]))
    assert all("analysis" in p for p in document["plies"])
    assert json.loads(path.read_bytes())["detail"] is True
