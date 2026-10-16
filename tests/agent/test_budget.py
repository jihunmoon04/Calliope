"""AG-D §3.5 and §11 test 2, AG4-D §3 and §5 (budget): searches metered at the engine port across
restarts, uncached analyses from any tool, the rolling window and its retry time, per-call and
per-window limits, nodes per tree, and an analysis the meter cut short is not cached."""

from __future__ import annotations

import pytest
from agent_helpers import G1, GAME, Starts, session
from synthetic import IDENTITY

from calliope.agent import BudgetError, Limits, Meter, MeteredPort, SearchBudgetExhausted
from calliope.agent.budget import Budget, Window
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

    meter, stub = Meter(Window(2, 900, lambda: 0.0)), Stub()
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
    s.ply(G1, 3)
    assert len(starts.started) == 2  # the slot restarted the engine
    first, second = starts.started
    calls = len(first.calls) + len(second.calls)
    assert s.budget.meter.used == calls and len(first.calls) == 3  # the failed call included
    assert isinstance(s.slot.port, MeteredPort) and s.slot.port.meter is s.budget.meter


def test_a_store_hit_is_free(tmp_path) -> None:
    s = session(tmp_path)
    s.open_game(pgn=GAME)
    s.explore(G1, {"ply": 4, "at": "after"}, [], search=True)
    used = s.budget.meter.used
    again = s.explore(G1, {"ply": 4, "at": "after"}, [], search=True)
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
        s.ply(G1, 3)
    assert len(starts.started) == 1  # no restart for a budget refusal
    assert s.budget.meter.refused == 1
    assert not s._cached(s.game(G1).parsed, 3)  # nothing in the ply cache


def test_uncached_analyses_from_every_tool_count(tmp_path) -> None:
    s = session(tmp_path, Limits(max_uncached_plies=3))
    s.open_game(pgn=GAME, plies="1")
    s.ply(G1, 2)
    s.judge_move(G1, {"ply": 3, "at": "before"}, "Nc3")
    assert s.budget.uncached.used == 3
    with pytest.raises(BudgetError, match="uncached"):
        s.ply(G1, 3)
    s.ply(G1, 1)  # cached: free
    with pytest.raises(BudgetError, match="uncached"):  # a new FEN is no way around it
        s.open_game(fen="8/P6k/8/8/8/8/8/K7 w - - 0 1", moves=["a8=Q"], plies="1")


def test_open_game_counts_the_uncached_plies_of_its_range_first(tmp_path) -> None:
    s = session(tmp_path, Limits(max_uncached_plies=2))
    with pytest.raises(BudgetError, match="3 uncached"):
        s.open_game(pgn=GAME, plies="1-3")
    assert s.budget.uncached.used == 0 and s.budget.meter.used == 0


def test_searches_and_nodes_are_refused_when_used(tmp_path) -> None:
    s = session(tmp_path, Limits(max_searches=1))
    s.open_game(pgn=GAME)
    s.explore(G1, {"ply": 2, "at": "after"}, [], search=True)
    with pytest.raises(BudgetError, match="a search"):
        s.explore(G1, {"ply": 3, "at": "after"}, [], search=True)
    with pytest.raises(BudgetError, match="an analysis"):
        s.ply(G1, 1)
    small = session(tmp_path / "n", Limits(max_nodes_per_tree=4))
    small.open_game(pgn=GAME)
    answer = small.facts(G1, {"ply": 3, "at": "after"})  # the root and three plies
    with pytest.raises(BudgetError, match="new nodes"):
        small.facts(G1, {"ply": 4, "at": "after"})
    assert answer["budget_left"]["nodes"] == 0


# -- the rolling window (AG4-D §3.2) -------------------------------------------------------------


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_charges_leave_the_window_after_its_seconds() -> None:
    clock = Clock()
    window = Window(2, 900, clock)
    window.charge()
    clock.now += 100
    window.charge()
    assert window.left == 0 and window.retry_after(1) == 800
    clock.now += 799.5
    assert window.left == 0 and window.retry_after(1) == 1  # ceil of half a second
    clock.now += 0.5  # the first charge is 900 seconds old
    assert window.left == 1 and window.retry_after(1) == 0
    clock.now += 100
    assert window.left == 2 and window.used == 0


def test_retry_after_waits_for_the_need_th_oldest_charge() -> None:
    """Review C3: needing 3 of a limit of 4 with 1 left, the 2nd-oldest charge must expire."""

    clock = Clock()
    window = Window(4, 900, clock)
    for step in (0, 10, 20):
        clock.now = 1000.0 + step
        window.charge()
    clock.now = 1030.0
    assert window.left == 1
    assert window.retry_after(1) == 0
    assert window.retry_after(2) == 1000 + 900 - 1030  # the oldest
    assert window.retry_after(3) == 1010 + 900 - 1030  # the second oldest
    assert window.retry_after(4) == 1020 + 900 - 1030
    assert window.retry_after(5) is None  # more than the limit itself


def test_a_refusal_names_what_is_left_and_when_room_comes_back() -> None:
    clock = Clock()
    budget = Budget(Limits(max_uncached_plies=2, window_seconds=60), clock)
    budget.admit_analysis(1)
    clock.now += 15
    budget.admit_analysis(1)
    with pytest.raises(BudgetError, match="retry_after_seconds: 45") as error:
        budget.admit_analysis(1)
    assert error.value.retry_after_seconds == 45 and "'uncached_plies': 0" in str(error.value)
    with pytest.raises(BudgetError, match="more than the limit") as error:
        budget.admit_analyses([1, 2, 3])
    assert error.value.retry_after_seconds is None
    clock.now += 45
    budget.admit_analysis(1)  # the first charge left the window
    assert budget.left() == {"uncached_plies": 0, "searches": 40, "window_seconds": 60}


def test_per_call_and_per_window_limits_hold_independently() -> None:
    clock = Clock()
    per_call = Budget(Limits(max_uncached_plies=10, max_uncached_plies_per_call=2), clock)
    with pytest.raises(BudgetError, match="in one call: at most 2"):
        per_call.admit_analyses([1, 2, 3])
    per_call.admit_analyses([1, 2])
    per_window = Budget(Limits(max_uncached_plies=2, max_uncached_plies_per_call=10), clock)
    per_window.admit_analysis(1)
    with pytest.raises(BudgetError, match="2 uncached analyses") as error:
        per_window.admit_analyses([1, 2])
    assert error.value.retry_after_seconds == 900


def test_admission_refuses_an_analysis_whose_search_bound_the_window_cannot_hold() -> None:
    clock = Clock()
    budget = Budget(Limits(max_searches=12), clock)
    for _ in range(3):
        budget.meter.take()
        clock.now += 1
    with pytest.raises(BudgetError, match="up to 10 searches") as error:
        budget.admit_analysis(5)  # 9 left, the bound is 10: one charge must expire
    assert error.value.retry_after_seconds == 900 - 3 and budget.uncached.used == 0
    budget.admit_analysis(1)  # ply 1's bound is 8


def test_the_meter_refuses_when_the_window_is_used_and_takes_again_once_it_moves() -> None:
    clock = Clock()
    meter = Meter(Window(1, 900, clock))
    meter.take()
    with pytest.raises(SearchBudgetExhausted, match="retry_after_seconds: 900"):
        meter.take()
    clock.now += 900
    meter.take()
    assert meter.total == 2 and meter.refused == 1


def test_a_session_window_refills_with_its_clock(tmp_path) -> None:
    clock = Clock()
    s = session(tmp_path, Limits(max_uncached_plies=1, window_seconds=600), clock=clock)
    s.open_game(pgn=GAME, plies="1")
    with pytest.raises(BudgetError, match="retry_after_seconds: 600"):
        s.ply(G1, 2)
    clock.now += 600
    assert s.ply(G1, 2)["budget_left"]["uncached_plies"] == 0


# -- limit values (AG4-D AM1) ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [{"window_seconds": 0}, {"window_seconds": -1}, {"window_seconds": float("inf")},
     {"window_seconds": float("nan")}, {"window_seconds": True}, {"window_seconds": 10**400},
     {"max_searches": -1}, {"max_uncached_plies": 1.5},
     {"max_store_results": 0}, {"max_open_games": 0}, {"max_nodes_per_tree": 0},
     {"max_nodes_total": 0}, {"max_handles": 0}, {"max_analyses": 0},
     {"max_uncached_plies_per_call": True}],
)  # fmt: skip
def test_a_limit_out_of_range_is_refused(bad) -> None:
    with pytest.raises(ValueError, match=next(iter(bad))):
        Limits(**bad)


def test_a_budget_amount_may_be_zero() -> None:
    limits = Limits(max_uncached_plies=0, max_searches=0, max_uncached_plies_per_call=0,
                    window_seconds=0.5)  # fmt: skip
    assert Budget(limits).left()["searches"] == 0


def test_the_server_refuses_a_limit_out_of_range(capsys) -> None:
    from tools.mcp.__main__ import main

    with pytest.raises(SystemExit) as exit_:
        main(["--max-store-results", "0"])
    assert exit_.value.code == 2 and "max_store_results is an integer of at least 1" in (
        capsys.readouterr().err)  # fmt: skip
