"""The played positions surveyed ahead of a game's analysis (PF-D §4.2, D4)."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest
from helpers import RATED, UNRATED, Failing, other_identity, slot
from synthetic import IDENTITY, engine, synthetic

from calliope.facts import EngineProfile, EngineResultStore, FactEngine, PositionRecords
from calliope.facts.search import ScriptedEngine
from calliope.server import EngineSlot, JobFailed, PlyCache, Prefetch, analyse_game, parse_game
from calliope.server.jobs import Jobs
from tools.explain_game.__main__ import explain_game

PROFILE = EngineProfile()


def _ahead(port=None) -> tuple[EngineSlot, list]:
    return slot(port)


def _game(parsed, plies, cache, *, prefetch=None, the_slot=None, store=None):
    the_slot = the_slot if the_slot is not None else slot()[0]
    store = store if store is not None else EngineResultStore()
    document = analyse_game(the_slot, parsed, plies, cache, store=store,
                            memo=PositionRecords(10_000), prefetch=prefetch)  # fmt: skip
    return document, store


def _answers(document):
    return [p | {"bundle": p["bundle"] | {"tree": None}} for p in document["plies"]]


def _digests(root: Path):
    return {p.stem: json.loads(p.read_bytes())["digests"] for p in root.rglob("*.tree")}


def test_the_prefetch_changes_no_answer_and_no_search_is_asked_twice(tmp_path) -> None:
    parsed = parse_game(RATED)
    plies = range(1, len(parsed.sans) + 1)
    plain, _ = _game(parsed, plies, PlyCache(tmp_path / "plain"))
    main_slot, main_started = slot()
    ahead_slot, ahead_started = _ahead()
    prefetch = Prefetch(ahead_slot)
    ahead, store = _game(parsed, plies, PlyCache(tmp_path / "ahead"), prefetch=prefetch,
                         the_slot=main_slot)  # fmt: skip
    assert _answers(ahead) == _answers(plain)
    assert _digests(tmp_path / "ahead") == _digests(tmp_path / "plain")
    asked = [repr(c) for c in main_started[0].calls + ahead_started[0].calls]
    assert len(asked) == len(set(asked)) == len(store)
    assert prefetch.counts["ran"] > 0
    assert prefetch.windows == list(plies)
    assert not store._reserved  # every reservation released


def test_the_surveys_ahead_are_round_zeros(tmp_path) -> None:
    """The keys asked ahead are the ones the analysis asks: none is wasted on a full run."""

    parsed = parse_game(UNRATED)
    plies = range(1, len(parsed.sans) + 1)
    main_slot, _ = slot()
    ahead_slot, ahead_started = _ahead()
    _game(parsed, plies, PlyCache(tmp_path / "a"), prefetch=Prefetch(ahead_slot),
          the_slot=main_slot)  # fmt: skip
    plain_slot, plain_started = slot()
    _game(parsed, plies, PlyCache(tmp_path / "b"), the_slot=plain_slot)
    every = {repr(c) for c in plain_started[0].calls}
    assert {repr(c) for c in ahead_started[0].calls} <= every


def test_a_partly_cached_game_asks_nothing_ahead_for_its_cached_plies(tmp_path) -> None:
    parsed = parse_game(UNRATED)
    cache = PlyCache(tmp_path)
    _game(parsed, range(1, 5), cache)
    prefetch = Prefetch(_ahead()[0])
    _game(parsed, range(1, 11), PlyCache(tmp_path), prefetch=prefetch)
    assert prefetch.windows == list(range(5, 11))


def test_one_uncached_ply_starts_no_prefetch(tmp_path) -> None:
    ahead_slot, started = _ahead()
    _game(parse_game(UNRATED), range(3, 4), PlyCache(tmp_path), prefetch=Prefetch(ahead_slot))
    assert started == []


class _Gate:
    """A run whose analysis never reaches a ply: the windows asked are the lookahead's."""

    def __init__(self) -> None:
        self.ahead_slot, self.started = _ahead()
        self.prefetch = Prefetch(self.ahead_slot)
        self.store = EngineResultStore()
        self.parsed = parse_game(UNRATED)

    def start(self, plies):
        facts = FactEngine(engine=engine(), store=self.store)
        return self.prefetch.start(facts, self.parsed, plies, PROFILE)


def _settle(prefetch, count: int, asked: int) -> None:
    """Until `count` windows have begun and `asked` surveys have ended (review N6)."""

    deadline = time.monotonic() + 10
    while (len(prefetch.windows) < count or sum(prefetch.counts.values()) < asked) and (
        time.monotonic() < deadline
    ):
        time.sleep(0.005)
    time.sleep(0.05)  # nothing more may start: the gate is closed


def test_the_prefetch_stays_three_listed_plies_ahead() -> None:
    gate = _Gate()
    run = gate.start([2, 4, 6, 8, 10])
    _settle(gate.prefetch, 3, 7)  # positions 0–6
    assert gate.prefetch.windows == [2, 4, 6]  # nothing reached yet: the first three
    run.reach(3)  # the analysis is past u1 = 2
    _settle(gate.prefetch, 4, 9)
    assert gate.prefetch.windows == [2, 4, 6, 8]
    run.reach(9)
    _settle(gate.prefetch, 5, 11)
    run.stop()
    assert gate.prefetch.windows == [2, 4, 6, 8, 10] and not run.thread.is_alive()
    # windows apart (k = u-2 … u): three positions each, none asked twice
    assert sum(gate.prefetch.counts.values()) == len({k for u in (2, 4, 6, 8, 10)
                                                      for k in range(u - 2, u + 1)})  # fmt: skip


def test_stop_ends_a_run_waiting_at_the_gate_and_releases_everything() -> None:
    gate = _Gate()
    run = gate.start([2, 4, 6, 8, 10])
    _settle(gate.prefetch, 3, 7)
    run.stop()
    assert not run.thread.is_alive() and not gate.store._reserved
    assert gate.prefetch.windows == [2, 4, 6]


class _Slow(ScriptedEngine):
    def __init__(self) -> None:
        super().__init__(IDENTITY, synthetic())
        self.closed = False

    def search(self, request):
        time.sleep(0.05)
        return super().search(request)

    def close(self) -> None:
        self.closed = True


def test_a_failing_analysis_stops_the_prefetch_without_closing_its_engine_mid_search(
    tmp_path,
) -> None:
    port = _Slow()
    prefetch = Prefetch(EngineSlot(lambda: port))
    store = EngineResultStore()
    with pytest.raises(JobFailed):
        _game(parse_game(UNRATED), range(1, 11), PlyCache(tmp_path), prefetch=prefetch,
              the_slot=EngineSlot(lambda: Failing(set(range(1, 10_000)))),
              store=store)  # fmt: skip
    assert not port.closed and not store._reserved  # every reservation released (§6)
    assert not any(t.name == "calliope-prefetch" for t in threading.enumerate())


@pytest.mark.parametrize("bad", ["failing", "other identity"])
def test_a_prefetch_failure_closes_its_engine_and_the_analysis_goes_on(
    tmp_path, bad, caplog
) -> None:
    parsed = parse_game(UNRATED)
    plies = range(1, 9)
    plain, _ = _game(parsed, plies, PlyCache(tmp_path / "plain"))
    if bad == "failing":
        port = Failing({2})
    else:
        port = ScriptedEngine(other_identity(), synthetic())
    closed = []
    port.close = lambda: closed.append(True)
    ahead_slot = EngineSlot(lambda: port)
    prefetch = Prefetch(ahead_slot)
    document, _ = _game(parsed, plies, PlyCache(tmp_path / "bad"), prefetch=prefetch)
    assert _answers(document) == _answers(plain)
    assert closed == [True] and ahead_slot.current is None  # started again by the next job
    assert "prefetch stopped" in caplog.text


def test_explain_game_surveys_ahead_only_with_a_second_engine() -> None:
    main = engine()
    plain_records, plain = explain_game(main, UNRATED, plies="1-6", digests=True)
    ahead_slot, started = _ahead()
    records, document = explain_game(engine(), UNRATED, plies="1-6", digests=True,
                                     prefetch=Prefetch(ahead_slot))  # fmt: skip
    assert [r["text"] for r in records] == [r["text"] for r in plain_records]
    assert started and started[0].calls
    assert [p["bundle"]["graph"] for p in document["plies"]] == [
        p["bundle"]["graph"] for p in plain["plies"]
    ]


def test_jobs_pass_the_prefetch_and_report_whether_the_worker_ended(tmp_path) -> None:
    given = []

    def observing(slot, parsed, plies, cache, *, prefetch, **kwargs):
        given.append(prefetch)
        return {"schema": "calliope_result_v1"}

    ahead_slot = _ahead()[0]
    table = Jobs(tmp_path, slot()[0], analyse=observing, check=lambda *a: True,
                 ahead_slot=ahead_slot)  # fmt: skip
    table.recover()
    table.submit(RATED, None)
    table.run_next()
    assert given == [table.prefetch] and table.prefetch.ahead is ahead_slot
    assert Jobs(tmp_path / "off", slot()[0]).prefetch is None
    assert table.stop(timeout=1) is True  # no worker thread
    table.start()
    assert table.stop(timeout=5) is True


def test_a_replaced_engine_identity_is_refused_by_the_survey(tmp_path) -> None:
    other = ScriptedEngine(replace(IDENTITY, binary_sha256="7" * 64), synthetic())
    facts = FactEngine(engine=engine())
    from calliope.facts import InvalidRequestError, RootSpec

    with pytest.raises(InvalidRequestError):
        facts.prefetch_survey(RootSpec(), PROFILE, other)


def test_another_exception_ends_the_prefetch_logged_and_keeps_its_engine(
    tmp_path, monkeypatch, caplog
) -> None:
    """§4.2: any exception ends the run and is logged; only engine and identity failures close
    the engine."""

    def broken(self, root, profile, port):
        raise RuntimeError("a bug")

    monkeypatch.setattr(FactEngine, "prefetch_survey", broken)
    parsed = parse_game(UNRATED)
    plain, _ = _game(parsed, range(1, 7), PlyCache(tmp_path / "plain"))
    ahead_slot, started = _ahead()
    prefetch = Prefetch(ahead_slot)
    document, _ = _game(parsed, range(1, 7), PlyCache(tmp_path / "x"), prefetch=prefetch)
    assert _answers(document) == _answers(plain)
    assert "prefetch stopped: a bug" in caplog.text and ahead_slot.current is started[0]


def test_a_run_that_outlives_its_stop_keeps_the_prefetch_off(monkeypatch, caplog) -> None:
    """Review N1: a port without a bound; the job goes on, and no second thread uses the
    engine while the first lives."""

    from calliope.server import pipeline

    monkeypatch.setattr(pipeline, "search_bound_s", lambda profile: -0.9)  # join 0.1 s
    gate = _Gate()
    release = threading.Event()

    def blocked(self, root, profile, port):
        release.wait(30)
        from calliope.facts import PrefetchOutcome

        return PrefetchOutcome.RAN

    monkeypatch.setattr(FactEngine, "prefetch_survey", blocked)
    run = gate.start([2, 4])
    run.stop()
    assert run.thread.is_alive() and "outlived its bound" in caplog.text
    assert gate.start([2, 4]) is None  # off while it lives
    release.set()
    run.thread.join(10)
    again = gate.start([2, 4])
    assert again is not None
    again.stop()
    again.thread.join(10)


def test_shutdown_never_closes_an_engine_still_searching(monkeypatch) -> None:
    """Review N9: a stuck run keeps its engine at shutdown."""

    from calliope.server import pipeline

    monkeypatch.setattr(pipeline, "search_bound_s", lambda profile: -0.9)
    gate = _Gate()
    release = threading.Event()
    monkeypatch.setattr(FactEngine, "prefetch_survey",
                        lambda self, root, profile, port: release.wait(30))  # fmt: skip
    run = gate.start([2, 4])
    run.stop()
    closed = []
    gate.ahead_slot.close = lambda: closed.append(True)
    assert gate.prefetch.close() is False and closed == []
    release.set()
    run.thread.join(10)
    assert gate.prefetch.close() is True and closed == [True]


def test_jobs_stop_reports_a_worker_still_running_and_serve_keeps_its_engines(tmp_path) -> None:
    from tools.serve.__main__ import close_engines

    entered, release = threading.Event(), threading.Event()

    def stuck(slot, parsed, plies, cache, **kwargs):
        entered.set()
        release.wait(30)
        return {"schema": "calliope_result_v1"}

    closed: list[str] = []
    main_slot, ahead_slot = slot()[0], _ahead()[0]
    main_slot.close = lambda: closed.append("main")
    ahead_slot.close = lambda: closed.append("ahead")
    table = Jobs(tmp_path, main_slot, analyse=stuck, check=lambda *a: True, ahead_slot=ahead_slot)
    table.recover()
    table.start()
    table.submit(RATED, None)
    assert entered.wait(10)
    assert close_engines(table, main_slot, timeout=0.1) is False and closed == []
    release.set()
    assert close_engines(table, main_slot, timeout=10) is True
    assert closed == ["ahead", "main"]  # the engine ahead first (§4.2)
