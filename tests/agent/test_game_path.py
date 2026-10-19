"""AG6-D §13 for packet AG6b through the session: `analyze_game` and its meters and locks,
`game_overview` and its moments, `show_game`'s board at any stage and within its bound, `next`
on the game path, and the job budget."""

from __future__ import annotations

import os
import threading
import time

import pytest
from agent_helpers import G1, GAME, session
from synthetic import engine

from calliope.agent import AgentError, Limits
from calliope.agent import session as session_module
from calliope.agent.jobs import WAIT_LIMIT
from calliope.agent.session import MOMENTS, _moments, _next_job


class Slow:
    """The synthetic engine, each search taking `seconds`."""

    def __init__(self, seconds: float = 0.05) -> None:
        self.inner = engine()
        self.seconds = seconds

    @property
    def identity(self):
        return self.inner.identity

    def search(self, request):
        time.sleep(self.seconds)
        return self.inner.search(request)

    def close(self) -> None:
        self.inner.close()


@pytest.fixture
def s(tmp_path):
    s = session(tmp_path)
    s.open_game(pgn=GAME)
    yield s
    s.close()


# -- analyze_game, meters (§4.4) ---------------------------------------------------------------------


def test_a_game_is_analysed_by_one_job_charged_to_its_own_meter(s) -> None:
    answer = s.analyze_game(G1, wait_seconds=60)
    job = answer["job"]
    assert job["state"] == "done" and (job["done"], job["total"]) == (10, 10)
    assert answer["next"] == _next_job(job) and "game_overview" in answer["next"]
    assert s.budget.meter.used == 0 and s.budget.uncached.used == 0  # AG4-D's: untouched
    meter = s.jobs.jobs[s.game(G1).key].slot.meter
    assert meter.total > 0
    taken = meter.total
    s.ply(G1, 3)  # a cached ply: no meter moves
    s.judge_move(G1, {"ply": 3, "at": "before"}, "Nc3")  # a tool's analysis: AG4-D's meter
    assert s.budget.meter.used > 0 and meter.total == taken
    s.engine_slot.restart()  # a restart keeps both meters apart
    s.judge_move(G1, {"ply": 3, "at": "before"}, "Qh5")
    assert meter.total == taken and s.slot.port.meter is s.budget.meter


def test_the_same_game_again_finds_its_plies_in_the_cache(tmp_path) -> None:
    first = session(tmp_path)
    try:
        first.open_game(pgn=GAME)
        first.analyze_game(G1, wait_seconds=60)
    finally:
        first.close()
    second = session(tmp_path)  # a restarted process forgets its jobs, not the cache
    try:
        second.open_game(pgn=GAME)
        job = second.analyze_game(G1, wait_seconds=60)["job"]
        assert job["state"] == "done" and job["cached"] == 10 and job["analysed"] == 0
    finally:
        second.close()


def test_the_job_budget_holds(tmp_path) -> None:
    s = session(tmp_path, Limits(max_job_plies=5, max_job_plies_per_window=3))
    try:
        s.open_game(pgn=GAME)
        with pytest.raises(AgentError, match="at most 5 plies, not 10"):
            s.analyze_game(G1)
        job = s.analyze_game(G1, plies="1-5", wait_seconds=2)["job"]
        assert job["state"] == "waiting" and job["done"] == 3  # the hourly limit: it waits
        assert "resume_after_seconds" in job
        s.analyze_game(G1, plies="1-5", cancel=True)
        assert s.jobs.wait(s.game(G1).key, 5).state == "cancelled"
    finally:
        s.close()


@pytest.mark.parametrize(
    ("job", "says"),
    [
        (None, "analyze_game으로 분석을 시작"),
        ({"state": "queued"}, f"wait_seconds={WAIT_LIMIT}"),
        ({"state": "running"}, f"wait_seconds={WAIT_LIMIT}"),
        ({"state": "waiting", "resume_after_seconds": 120}, f"wait_seconds={WAIT_LIMIT}"),
        ({"state": "waiting", "resume_after_seconds": 1200}, "game_overview를 보고"),
        ({"state": "done"}, "game_overview로"),
        ({"state": "failed"}, "다시 부르면 이어서"),
        ({"state": "cancelled"}, "다시 부르면 이어서"),
    ],
)
def test_next_after_analyze_game(job, says) -> None:
    """AG6-D §7's rows, re-review B8: a long budget wait sends to the overview, not to a loop."""

    text = _next_job(job)
    assert says in text
    if job and job.get("resume_after_seconds", 0) > WAIT_LIMIT:
        assert "analyze_game을 다시 부르지 마세요" in text


# -- locks (§4.3) ---------------------------------------------------------------------------------


def test_tools_answer_while_a_job_runs_and_no_ply_is_analysed_twice(tmp_path) -> None:
    s = session(tmp_path, start=lambda: Slow(0.05))
    try:
        s.open_game(pgn=GAME, plies="1")  # ply 1 cached before the job
        key = s.game(G1).key
        s.analyze_start(G1)
        started = time.monotonic()
        s.ply(G1, 1)  # cached: no engine lock is taken
        assert time.monotonic() - started < 1.0
        answer = s.judge_move(G1, {"ply": 5, "at": "before"}, "Nc3")  # waits for one analysis
        assert answer["move"] == "3.Nc3"
        s.ply(G1, 6)  # the job's ply asked by a tool: analysed once, by whichever comes first
        s.jobs.wait(key, 60)
        assert s.jobs.snapshot(key)["state"] == "done"
        assert s.cache.counts["written"] == 10 + 1  # ten plies and the judged move, once each
    finally:
        s.close()


def test_the_engine_lock_serves_in_turn() -> None:
    from calliope.agent.budget import EngineLock

    lock, order, held = EngineLock(), [], threading.Event()

    def holder():
        with lock:
            held.set()
            time.sleep(0.2)
            order.append("holder")

    def caller(name, delay):
        time.sleep(delay)
        with lock:
            order.append(name)

    threads = [threading.Thread(target=holder)]
    threads += [threading.Thread(target=caller, args=(f"c{k}", 0.02 * (k + 1))) for k in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert held.is_set() and order == ["holder", "c0", "c1", "c2"]
    with lock, lock:  # re-entrant for its holder
        assert lock.waiting() == 0


# -- game_overview (§3.3) -------------------------------------------------------------------------


def _summary(ply, grade="good", label=None, loss=0, white=1000):
    return {"ply": ply, "san": "e4", "move": f"{ply}.e4", "grade": grade, "label": label,
            "score": "+0.10", "best_move": "e4", "loss": loss, "white_expected": white,
            "bundle": ["t", "g"]}  # fmt: skip


def test_the_moments_follow_their_rules(monkeypatch) -> None:
    monkeypatch.setattr(session_module, "MOMENTS", 8)  # AG6-D's cap: the rules under a cap
    summaries = {p: _summary(p) for p in range(1, 31)}
    summaries[3] = _summary(3, "blunder", loss=900)
    summaries[5] = _summary(5, "mistake", loss=300)
    summaries[7] = _summary(7, "best", "brilliant")
    summaries[9] = _summary(9, "inaccuracy", "miss", loss=180)
    summaries[11] = _summary(11, "best", "great")
    summaries[13] = _summary(13, "mistake", loss=300)  # ties 5 on loss: the earlier ply first
    summaries[15] = _summary(15, "inaccuracy", loss=160)
    summaries[16] = _summary(16, "good", white=600)  # 15 → 16 crosses 1000 by 400: a turning point
    summaries[20] = _summary(20, "blunder", loss=700)
    summaries[22] = _summary(22, "best", "brilliant")
    moments = _moments(summaries)
    assert [m["ply"] for m in moments] == [3, 5, 7, 9, 11, 13, 20, 22]  # 8, in ply order
    by = {m["ply"]: m["reasons"] for m in moments}
    assert (
        by[3] == ["blunder", "loss"]
        and by[9] == ["miss", "inaccuracy"]
        and by[20] == ["blunder", "loss"]
    )
    assert 16 not in by  # a turning point (priority 7) ranked below the eight
    assert [m["ply"] for m in _moments({p: summaries[p] for p in (15, 16)})] == [15, 16]
    assert _moments({p: summaries[p] for p in (15, 16)})[1]["reasons"] == ["turning_point"]


def test_the_overview_of_an_analysed_game(s) -> None:
    s.analyze_game(G1, wait_seconds=60)
    key = s.game(G1).key
    files = s.cache.file_digests(s._key(s.game(G1).parsed, 4)[0])  # kept of the files there (B2)
    s.jobs.keep_summary(key, 4, _summary(4, "blunder", loss=800)
                        | {"san": "Nf6", "move": "2...Nf6", "bundle": list(files)})  # fmt: skip
    overview = s.game_overview(G1)
    assert overview["plies"] == 10 and overview["analysed"] == 10 and "ranges" not in overview
    assert [line["ply"] for line in overview["lines"]] == list(range(1, 11))
    assert overview["lines"][3]["grade_ko"] == "블런더"
    assert [m["ply"] for m in overview["moments"]] == [4]
    assert overview["warnings"] and overview["warnings"][0].startswith(
        "graded with the default curve"
    )
    assert "ply 4" in overview["next"]
    d = s.ply(G1, 4)
    assert "submit_commentary(items)" in d["next"]  # every moment read (§7)


LONG = " ".join(["Nf3 Nf6 Ng1 Ng8"] * 113)  # 452 plies of knights, for the ranges only


def test_a_long_game_is_read_in_ranges_with_the_whole_games_moments(tmp_path, monkeypatch) -> None:
    s = session(tmp_path)
    try:
        game = s.open_game(fen=None, moves=LONG.split())["game"]
        blunder = _summary(437, "blunder", loss=900)  # one ply analysed, without analysing it
        monkeypatch.setattr(s, "_summary", lambda g, ply: blunder if ply == 437 else None)
        first = s.game_overview(game)
        last = s.game_overview(game, "401-452")
        assert first["ranges"] == ["1–200", "201–400", "401–452"]
        assert [line["ply"] for line in first["lines"]] == list(range(1, 201))
        assert [line["ply"] for line in last["lines"]] == list(range(401, 453))
        assert first["moments"] == last["moments"] and first["moments"][0]["ply"] == 437
        assert first["lines"][0]["analysed"] is False
        with pytest.raises(AgentError, match="200수까지"):
            s.game_overview(game, "1-201")
    finally:
        s.close()


def test_a_game_over_600_plies_is_refused_on_the_game_path(tmp_path) -> None:
    s = session(tmp_path)
    try:
        game = s.open_game(moves=" ".join(["Nf3 Nf6 Ng1 Ng8"] * 151).split())["game"]
        for call in (lambda: s.analyze_game(game), lambda: s.game_overview(game),
                     lambda: s.show_game(game)):  # fmt: skip
            with pytest.raises(AgentError, match="at most 600 plies, not 604"):
                call()
    finally:
        s.close()


# -- show_game at any stage and within its bound (§6) ------------------------------------------------


def test_the_board_follows_a_job(tmp_path) -> None:
    s = session(tmp_path, start=lambda: Slow(0.05))
    try:
        s.open_game(pgn=GAME)
        s.analyze_start(G1)
        view, text = s.show_game(G1)
        assert view["job"] is not None and view["job"]["state"] in ("queued", "running")
        assert "pending" in {e["state"] for e in view["plies"]}
        assert "분석 작업:" in text
        s.jobs.wait(s.game(G1).key, 60)
        view, _ = s.show_game(G1)
        assert {e["state"] for e in view["plies"]} == {"analysed"} and view["job"][
            "state"
        ] == "done"
    finally:
        s.close()


def _commented(s, plies) -> None:
    for ply in plies:
        d = s.ply(G1, ply)
        s.submit_commentary(G1, agent={"name": "t"}, ply=ply,
                            propositions=[{"id": "p1", "kind": "judgement", "judgement": d["judgement"]}],
                            sentences=[{"text": f"{d['move']}로 이어졌다.", "class": "sourced",
                                        "cites": ["p1"]}])  # fmt: skip


def test_what_does_not_fit_the_board_is_left_out_whole_and_named(s, monkeypatch) -> None:
    s.analyze_game(G1, wait_seconds=60)
    _commented(s, (2, 4, 6, 8))
    s.moments[s.game(G1).key] = [2, 4]  # the overview's moments keep their commentary longest
    full, _ = s.show_game(G1)
    size = len(session_module._compact(full["result"]).encode())
    monkeypatch.setattr(session_module, "VIEW_LIMIT", size + 64 * 1024 - 1)  # one byte short
    view, text = s.show_game(G1)
    assert view["omitted"]["commentary"] == [8] and view["omitted"]["records"] == []
    assert next(e for e in view["plies"] if e["ply"] == 8)["omitted"] == "commentary"
    assert "크기 때문에 판에 담지 못한 해설: 수 8" in text
    monkeypatch.setattr(session_module, "VIEW_LIMIT", 64 * 1024 + 1)  # room for the moves only
    view, _ = s.show_game(G1)
    assert view["omitted"]["commentary"] == [2, 4, 6, 8]  # moments last
    assert view["omitted"]["records"] == list(range(1, 11)) and view["result"] is None
    monkeypatch.setattr(session_module, "RECORD_LIMIT", 100)  # every record over its own bound
    view, _ = s.show_game(G1)
    assert view["omitted"]["records"] == list(range(1, 11)) and view["result"] is None


def test_the_board_holds_its_bound_with_200_of_the_largest_commentaries(s, monkeypatch) -> None:
    """AG6-D §6.2's worst case: 200 plies, each commentary just under 64 KiB; small records first,
    then records too large to fit together."""

    sizes = {"record": 1024}
    commentary = {"sentences": ["c" * (64 * 1024 - 64)]}

    def game_result(headed, run, chosen):
        return {"plies": [{"ply": i.ply, "record": "r" * sizes["record"]} for i in chosen]}

    def with_commentary(document, stored, played):
        return {"plies": [dict(p, ai_commentary=commentary) for p in document["plies"]]}

    monkeypatch.setattr(session_module, "game_result", game_result)
    monkeypatch.setattr(session_module, "with_commentary", with_commentary)
    loaded = {p: type("Loaded", (), {"ply": p})() for p in range(1, 201)}
    s.moments[s.game(G1).key] = [5, 150]
    budget = session_module.VIEW_LIMIT - 64 * 1024

    def view():
        omitted = {"records": [], "commentary": []}
        started = time.monotonic()
        result = s._view_result(s.game(G1), None, loaded, omitted)
        assert time.monotonic() - started < 10  # a build per run of drops, not one per ply
        return result, omitted, len(session_module._compact(result).encode())

    result, omitted, size = view()
    kept = [p["ply"] for p in result["plies"] if "ai_commentary" in p]
    assert size <= budget and omitted["records"] == [] and len(result["plies"]) == 200
    assert 5 in kept and 150 in kept and 1 < len(kept) < 12  # the moments' commentary last to go
    assert sorted(kept + omitted["commentary"]) == list(range(1, 201))
    sizes["record"] = 20 * 1024  # 200 such records alone are over the bound
    result, omitted, size = view()
    count = len(result["plies"])
    assert size <= budget and size + 20 * 1024 > budget  # as many records as fit
    assert omitted["commentary"] == list(range(1, 201))  # all commentary before any record
    assert omitted["records"] == list(range(count + 1, 201))  # records from the end


# -- review B1–B4 ------------------------------------------------------------------------------------


class Recorded(Slow):
    """`Slow`, recording into `log` when each search starts and ends and when it is closed."""

    def __init__(self, seconds: float, log: list) -> None:
        super().__init__(seconds)
        self.log = log

    def search(self, request):
        self.log.append(("start", time.monotonic()))
        try:
            return super().search(request)
        finally:
            self.log.append(("end", time.monotonic()))

    def close(self) -> None:
        self.log.append(("close", time.monotonic()))
        super().close()


def _closing_mid_ply(tmp_path):
    log: list = []
    s = session(tmp_path, start=lambda: Recorded(2.0, log))
    s.open_game(pgn=GAME, plies="1")
    before = len(log)
    s.analyze_start(G1)
    deadline = time.monotonic() + 30
    while not any(e == "start" for e, _ in log[before:]) and time.monotonic() < deadline:
        time.sleep(0.05)  # the job's analysis of ply 2 has begun
    time.sleep(0.5)
    return s, log


def test_the_engine_closes_only_after_the_worker_ends(tmp_path) -> None:
    """Review B1: the ply under way when the session closes takes longer than five seconds."""

    s, log = _closing_mid_ply(tmp_path)
    started = time.monotonic()
    s.close()
    assert time.monotonic() - started > 5  # the old 5 s join would have closed the engine early
    events = [e for e, _ in log]
    assert events[-1] == "close" and events.count("start") == events.count("end")
    assert not s.jobs._thread.is_alive()
    assert s.jobs.snapshot(s.game(G1).key)["state"] == "cancelled"


def test_a_worker_that_does_not_end_keeps_the_engine(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(session_module, "STOP_SECONDS", 0.2)
    s, log = _closing_mid_ply(tmp_path)
    s.close()
    assert "close" not in [e for e, _ in log] and s.jobs._thread.is_alive()
    s.jobs._thread.join(60)  # the ply ends, then the worker; nothing used a closed engine
    assert [e for e, _ in log].count("start") == [e for e, _ in log].count("end")


class Gated(Slow):
    """`Slow`, whose searches block while `gate` is clear."""

    def __init__(self) -> None:
        super().__init__(0)
        self.gate = threading.Event()
        self.gate.set()
        self.inside = threading.Event()

    def search(self, request):
        self.inside.set()
        assert self.gate.wait(60)
        return super().search(request)


def test_a_cached_ply_never_waits_for_an_analysis(tmp_path) -> None:
    """Review B3: the job holds the engine lock inside a search; cached reads do not wait for it."""

    port = Gated()
    s = session(tmp_path, start=lambda: port)
    try:
        s.open_game(pgn=GAME, plies="1-2")  # plies 1 and 2 cached
        port.gate.clear()
        port.inside.clear()
        s.analyze_start(G1)  # plies 1 and 2 are hits; ply 3 blocks inside a search
        assert port.inside.wait(30) and s.engine_lock._owner is not None
        read = []

        def reads() -> None:
            read.append(s.ply(G1, 1)["ply"])
            read.append(s.ply(G1, 2, view="full")["ply"])
            read.append(s.show_game(G1, "1-2")[0]["schema"])
            read.append(s.game_overview(G1)["analysed"])

        reader = threading.Thread(target=reads)
        reader.start()
        reader.join(30)
        blocked = reader.is_alive()
        port.gate.set()
        reader.join(30)
        assert not blocked and read == [1, 2, "calliope_view_v1", 2]
    finally:
        port.gate.set()
        s.close()


def test_the_overview_and_the_board_agree_when_files_are_gone(s) -> None:
    """Review B2: a ply whose files were removed after a job is not analysed in either."""

    s.analyze_game(G1, wait_seconds=60)
    for path in s.cache.paths(s._key(s.game(G1).parsed, 3)[0]):
        path.unlink()
    overview = s.game_overview(G1)
    assert overview["analysed"] == 9 and overview["lines"][2]["analysed"] is False
    view, _ = s.show_game(G1)
    assert view["plies"][2]["state"] == "none"
    assert 3 not in [p["ply"] for p in view["result"]["plies"]]


def test_a_job_budget_of_none_fails_the_job(tmp_path) -> None:
    """Review B4 through the session: the job fails at once and says why."""

    s = session(tmp_path, Limits(max_job_plies_per_window=0))
    try:
        s.open_game(pgn=GAME)
        started = time.monotonic()
        answer = s.analyze_game(G1, wait_seconds=10)
        assert time.monotonic() - started < 5
        assert answer["job"]["state"] == "failed"
        assert "max_job_plies_per_window is 0" in answer["job"]["error"]
    finally:
        s.close()


def test_a_corrupt_pair_on_disk_is_not_a_way_around_the_job_budget(tmp_path) -> None:
    """Re-review B5: both files of ply 1 exist but do not load; with no job budget nothing is
    analysed and the job fails."""

    s = session(tmp_path, Limits(max_job_plies_per_window=0))
    try:
        s.open_game(pgn=GAME, plies="1")
        key = s._key(s.game(G1).parsed, 1)[0]
        for path in s.cache.paths(key):
            path.write_bytes(b"not a bundle")
        assert s._job_cached(s.jobs.start(s.game(G1).key, G1, s.game(G1).parsed, range(1, 2)), 1)
        answer = s.analyze_game(G1, plies="1", wait_seconds=10)
        job = s.jobs.jobs[s.game(G1).key]
        assert answer["job"]["state"] == "failed" and job.slot.meter.total == 0
        assert "max_job_plies_per_window is 0" in answer["job"]["error"]
    finally:
        s.close()


def test_a_corrupt_pair_outside_the_asked_range_is_not_shown_analysed(s, monkeypatch) -> None:
    """Review B8: the board's states for the whole game agree with the overview, ply 8 corrupt
    while the board shows plies 1–4."""

    monkeypatch.setattr(session_module, "SHOW_LIMIT", 4)
    s.analyze_game(G1, wait_seconds=60)
    tree, graph = s.cache.paths(s._key(s.game(G1).parsed, 8)[0])
    before = s.cache.file_digests(s._key(s.game(G1).parsed, 8)[0])
    tree.write_bytes(b"not a tree")
    graph.write_bytes(b"not a graph")
    assert s.cache.file_digests(s._key(s.game(G1).parsed, 8)[0]) != before
    view, _ = s.show_game(G1, "1-4")
    overview = s.game_overview(G1)
    states = {e["ply"]: e["state"] for e in view["plies"]}
    lines = {line["ply"]: line.get("analysed", True) for line in overview["lines"]}
    assert states[8] == "none" and lines[8] is False
    assert all((states[p] == "analysed") == lines[p] for p in range(1, 11))
    assert [p["ply"] for p in view["result"]["plies"]] == [1, 2, 3, 4]


def test_a_pair_changed_in_place_with_its_stat_restored_is_not_analysed(s) -> None:
    """Review B9: the same inode, size and mtime, other bytes: the content decides."""

    s.analyze_game(G1, wait_seconds=60)
    key = s._key(s.game(G1).parsed, 3)[0]
    assert s.game_overview(G1)["analysed"] == 10  # every summary kept and checked once
    for path in s.cache.paths(key):
        before = path.stat()
        data = bytearray(path.read_bytes())
        data[len(data) // 2] ^= 0xFF  # one byte, the same length
        with open(path, "r+b") as handle:  # in place: the same inode
            handle.write(data)
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        after = path.stat()
        assert (after.st_ino, after.st_size, after.st_mtime_ns) == (
            before.st_ino, before.st_size, before.st_mtime_ns)  # fmt: skip
    overview = s.game_overview(G1)
    view, _ = s.show_game(G1)
    assert overview["analysed"] == 9 and overview["lines"][2].get("analysed") is False
    assert view["plies"][2]["state"] == "none"


# -- LM-D §2: inaccuracies as moments, up to 16 ----------------------------------------------------


def test_an_inaccuracy_is_a_moment_ranked_after_the_key_ones() -> None:
    summaries = {p: _summary(p, white=1000 if p < 9 else 600) for p in range(1, 41)}
    summaries[4] = _summary(4, "inaccuracy", loss=90)
    summaries[6] = _summary(6, "mistake", loss=300)  # 8 → 9 crosses 1000 by 400: a turning point
    moments = {m["ply"]: m["reasons"] for m in _moments(summaries)}
    assert moments == {4: ["inaccuracy"], 6: ["mistake", "loss"], 9: ["turning_point"]}
    inaccuracies = {p: _summary(p, "inaccuracy", loss=60 + p, white=600) for p in range(11, 31)}
    keys = {3: _summary(3, "blunder", loss=900), 5: _summary(5, "best", "great", white=1000)}
    ranked = _moments({**summaries, **inaccuracies, **keys})
    assert len(ranked) == MOMENTS == 16  # the key moments, then the inaccuracies by loss
    plies = [m["ply"] for m in ranked]
    assert {3, 5, 6, 9} <= set(plies)  # the key moments are never pushed out by inaccuracies
    kept = [p for p in plies if p in inaccuracies or p == 4]
    dropped = [p for p in (4, *inaccuracies) if p not in plies]
    assert min(inaccuracies[p]["loss"] if p != 4 else 90 for p in kept) >= max(
        inaccuracies[p]["loss"] if p != 4 else 90 for p in dropped
    )  # the larger losses kept
    assert plies == sorted(plies)  # in ply order
