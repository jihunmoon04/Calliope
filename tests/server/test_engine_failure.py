"""Engine failures (AS-D §5.2, review B3; test 7)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from helpers import UNRATED, Failing, other_identity
from synthetic import engine

from calliope.facts import BudgetExceededError, EngineError, EngineOutputError
from calliope.reasoning import AnalysisFailed, Reasoner, RequestOutcome, Round
from calliope.server import EngineSlot, JobFailed, PlyCache, analyse_game, parse_game, pipeline
from calliope.server.pipeline import is_engine_failure, refused_by_engine_failure


def _slot(*ports):
    """A slot that hands out `ports` in turn, then fresh synthetic engines."""

    queue, started = list(ports), []

    def start():
        started.append(queue.pop(0) if queue else engine())
        return started[-1]

    return EngineSlot(start), started


def test_round_zero_failure_restarts_the_engine_and_the_ply_succeeds(tmp_path) -> None:
    """`AnalysisFailed` caused by an `EngineError`: one restart, then the ply is analysed."""

    the_slot, started = _slot(Failing({1}))
    document = analyse_game(the_slot, parse_game(UNRATED), range(1, 3), PlyCache(tmp_path))
    assert len(started) == 2 and [p["ply"] for p in document["plies"]] == [1, 2]


def test_two_round_zero_failures_fail_the_job_and_the_next_job_runs(tmp_path) -> None:
    the_slot, started = _slot(Failing({1}), Failing({1}))
    with pytest.raises(JobFailed, match="the engine failed twice"):
        analyse_game(the_slot, parse_game(UNRATED), range(1, 2), PlyCache(tmp_path))
    assert not [p for p in tmp_path.rglob("*") if p.is_file()]  # nothing cached
    the_slot.restart()  # the next job starts with a fresh engine
    document = analyse_game(the_slot, parse_game(UNRATED), range(1, 2), PlyCache(tmp_path))
    assert len(started) == 3 and document["plies"][0]["ply"] == 1


def test_a_later_round_engine_refusal_discards_the_analysis(tmp_path, monkeypatch) -> None:
    """`REFUSED(EngineError)` in a later round: the analysis is not kept, the engine restarts
    and the ply is analysed again. The synthetic engine's later rounds reuse round 0's
    searches, so the refusal is injected into the first analysis's rounds."""

    calls = []

    class Injecting(Reasoner):
        def analyse(self, request):
            analysis = super().analyse(request)
            calls.append(request.target)
            if len(calls) == 1:
                refused = Round(
                    1, analysis.rev, (), (RequestOutcome(None, "REFUSED(EngineError)"),)
                )
                return replace(analysis, rounds=(refused,))
            return analysis

    monkeypatch.setattr(pipeline, "Reasoner", Injecting)
    the_slot, started = _slot()
    document = analyse_game(the_slot, parse_game(UNRATED), range(1, 2), PlyCache(tmp_path))
    assert calls == [1, 1] and len(started) == 2
    assert all(
        o.outcome != "REFUSED(EngineError)" for r in document_rounds(tmp_path) for o in r.requests
    )
    assert document["plies"][0]["bundle"]["stored"]


def document_rounds(tmp_path):
    from calliope.facts import FactEngine
    from calliope.reasoning.storage import load

    graph = next(tmp_path.rglob("*.graph"))
    tree = graph.with_suffix(".tree")
    analysis, _ = load(FactEngine(), tree.read_bytes(), graph.read_bytes())
    return analysis.rounds


def test_what_is_and_is_not_an_engine_failure() -> None:
    """Not retried: refusals about the answer, the identity or the budget (AS-D §5.2)."""

    assert is_engine_failure(EngineError("engine process exited"))
    assert not is_engine_failure(EngineOutputError("an illegal PV"))
    assert not is_engine_failure(BudgetExceededError("budget"))
    assert not is_engine_failure(None)

    def with_outcome(outcome):
        return replace(_ANALYSIS[0], rounds=(Round(1, 1, (), (RequestOutcome(None, outcome),)),))

    assert refused_by_engine_failure(with_outcome("REFUSED(EngineError)"))
    assert not refused_by_engine_failure(with_outcome("REFUSED(EngineOutputError)"))
    assert not refused_by_engine_failure(with_outcome("REFUSED(BudgetExceededError)"))


_ANALYSIS: list = []


@pytest.fixture(autouse=True)
def _one_analysis():
    if not _ANALYSIS:
        from calliope.facts import EngineProfile, FactEngine
        from calliope.server import ply_request

        parsed = parse_game(UNRATED)
        _ANALYSIS.append(
            Reasoner(FactEngine(engine=engine())).analyse(ply_request(parsed, 1, EngineProfile()))
        )


def test_another_cause_fails_the_job_at_once(tmp_path, monkeypatch) -> None:
    calls = []

    class Refusing(Reasoner):
        def analyse(self, request):
            calls.append(request.target)
            raise AnalysisFailed("round 0 failed: budget", BudgetExceededError("budget"))

    monkeypatch.setattr(pipeline, "Reasoner", Refusing)
    the_slot, started = _slot()
    with pytest.raises(JobFailed, match="budget"):
        analyse_game(the_slot, parse_game(UNRATED), range(1, 2), PlyCache(tmp_path))
    assert calls == [1] and len(started) == 1  # no retry, no restart


def test_a_restarted_engine_with_another_identity_fails_the_job(tmp_path) -> None:
    the_slot, _ = _slot(Failing({1}), Failing(set(), identity=other_identity()))
    with pytest.raises(JobFailed, match="not the one this job was posted for"):
        analyse_game(the_slot, parse_game(UNRATED), range(1, 2), PlyCache(tmp_path))
