"""AG-D §3.5 and §11 test 2: the budget — searches metered at the engine port across restarts,
uncached analyses from any tool, nodes, and an analysis the meter cut short is not cached."""

from __future__ import annotations

import pytest
from agent_helpers import GAME, Starts, session
from synthetic import IDENTITY

from calliope.agent import BudgetError, Limits, Meter, MeteredPort, SearchBudgetExhausted
from calliope.facts import EngineError


def test_the_meter_charges_before_the_engine_and_never_refunds() -> None:
    class Stub:
        identity = IDENTITY
        calls = 0

        def search(self, request):
            self.calls += 1
            if self.calls == 1:
                raise EngineError("engine process exited")
            return "raw"

    meter, stub = Meter(2), Stub()
    port = MeteredPort(stub, meter)
    assert port.identity == IDENTITY
    with pytest.raises(EngineError):
        port.search("request")
    assert meter.used == 1  # a failed search stays charged
    assert port.search("request") == "raw" and meter.used == 2
    with pytest.raises(SearchBudgetExhausted):
        port.search("request")
    assert stub.calls == 2 and meter.refused == 1 and meter.left == 0  # the engine was not asked


def test_a_failure_restart_and_retry_charge_both_attempts_to_one_meter(tmp_path) -> None:
    """Review R3: 3 searches before an engine failure and the retry's searches are all counted."""

    starts = Starts(fail_on={3})
    s = session(tmp_path, start=starts)
    s.open_game(pgn=GAME)
    s.ply("g1", 3)
    assert len(starts.started) == 2  # the slot restarted the engine
    first, second = starts.started
    calls = len(first.calls) + len(second.calls)
    assert s.budget.meter.used == calls and len(first.calls) == 3  # the failed call included
    assert isinstance(s.slot.port, MeteredPort) and s.slot.port.meter is s.budget.meter


def test_a_store_hit_is_free(tmp_path) -> None:
    s = session(tmp_path)
    s.open_game(pgn=GAME)
    s.explore("g1", {"ply": 4, "at": "after"}, [], search=True)
    used = s.budget.meter.used
    again = s.explore("g1", {"ply": 4, "at": "after"}, [], search=True)
    assert s.budget.meter.used == used and again["search"]["lines"]


def test_an_exhausted_meter_stops_the_analysis_without_a_restart_and_caches_nothing(
    tmp_path,
) -> None:
    starts = Starts(fail_on=set())
    s = session(tmp_path, start=starts)
    s.open_game(pgn=GAME)
    admit = s.budget.admit_analysis

    def admit_then_shrink(target: int) -> None:  # admitted, then one search left
        admit(target)
        s.budget.meter.limit = s.budget.meter.used + 1

    s.budget.admit_analysis = admit_then_shrink
    with pytest.raises(BudgetError, match="cut short"):
        s.ply("g1", 3)
    assert len(starts.started) == 1  # no restart for a budget refusal
    assert s.budget.meter.refused == 1
    assert not s._cached(s.game("g1").parsed, 3)  # nothing in the ply cache


def test_uncached_analyses_from_every_tool_count(tmp_path) -> None:
    s = session(tmp_path, Limits(max_uncached_plies=3))
    s.open_game(pgn=GAME, plies="1")
    s.ply("g1", 2)
    s.judge_move("g1", {"ply": 3, "at": "before"}, "Nc3")
    assert s.budget.uncached == 3
    with pytest.raises(BudgetError, match="uncached"):
        s.ply("g1", 3)
    s.ply("g1", 1)  # cached: free
    with pytest.raises(BudgetError, match="uncached"):  # a new FEN is no way around it
        s.open_game(fen="8/P6k/8/8/8/8/8/K7 w - - 0 1", moves=["a8=Q"], plies="1")


def test_open_game_counts_the_uncached_plies_of_its_range_first(tmp_path) -> None:
    s = session(tmp_path, Limits(max_uncached_plies=2))
    with pytest.raises(BudgetError, match="3 uncached"):
        s.open_game(pgn=GAME, plies="1-3")
    assert s.budget.uncached == 0 and s.budget.meter.used == 0


def test_searches_and_nodes_are_refused_when_used(tmp_path) -> None:
    s = session(tmp_path, Limits(max_searches=1))
    s.open_game(pgn=GAME)
    s.explore("g1", {"ply": 2, "at": "after"}, [], search=True)
    with pytest.raises(BudgetError, match="a search"):
        s.explore("g1", {"ply": 3, "at": "after"}, [], search=True)
    with pytest.raises(BudgetError, match="an analysis"):
        s.ply("g1", 1)
    small = session(tmp_path / "n", Limits(max_nodes=4))
    small.open_game(pgn=GAME)
    small.facts("g1", {"ply": 3, "at": "after"})  # the root and three plies
    with pytest.raises(BudgetError, match="new nodes"):
        small.facts("g1", {"ply": 4, "at": "after"})
    assert small.budget.left()["nodes"] == 0
