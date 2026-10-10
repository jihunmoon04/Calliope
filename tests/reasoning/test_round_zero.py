"""Round 0 of the controller and the input contract (reasoning R0-D §5, §6.1, §18.4)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from scripted import scripted
from synthetic import engine

from calliope.facts import (
    FULL,
    NONE,
    EngineLineId,
    EngineProfile,
    EnsureRequest,
    ExtendRequest,
    FactEngine,
    IllegalMoveError,
    LineEnd,
    NotComputed,
    OpenRequest,
    PiecesFacts,
    RootSpec,
    material_flow,
)
from calliope.facts.search import EngineResultStore
from calliope.reasoning import (
    AnalysisRequest,
    Controller,
    InvalidAnalysisRequest,
    JudgementStatus,
    LineSegment,
    MoveSubject,
    ReasoningBudget,
)

PROFILE = EngineProfile()
GAME = ("e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5")


DEFAULT_BUDGET = ReasoningBudget()


def _run(target: int, *, port=None, budget=DEFAULT_BUDGET, moves=GAME, store=None):
    fact_engine = FactEngine(engine=port or engine(pv_plies=6), store=store)
    request = AnalysisRequest(RootSpec(), moves, target, PROFILE, budget)
    return Controller(fact_engine).round_zero(request), fact_engine


@pytest.mark.parametrize(
    ("target", "kinds"),
    [
        (1, ["OpenRequest", "ExtendRequest", "EnsureRequest"]),
        (2, ["OpenRequest", "ExtendRequest", "EnsureRequest"]),
        (5, ["OpenRequest", "ExtendRequest", "ExtendRequest", "EnsureRequest"]),
    ],
)
def test_round_zero_requests(target: int, kinds: list[str]) -> None:
    result, _ = _run(target)
    view = result.tree.view(result.rev)
    requests = [view.request(rev) for rev in range(1, result.rev + 1)]
    assert [type(r).__name__ for r in requests] == kinds
    opening = requests[0]
    assert isinstance(opening, OpenRequest)
    assert opening.root_expansion == NONE  # R0-D §6.1 as amended by R1
    assert opening.budget.max_nodes == target + 1 + ReasoningBudget().max_tree_nodes
    assert opening.budget.deadline_per_request_ms == ReasoningBudget().deadline_ms
    extends = [r for r in requests if isinstance(r, ExtendRequest)]
    assert [e.expansion for e in extends] == ([NONE, FULL] if target > 2 else [FULL])
    assert isinstance(requests[-1], EnsureRequest)


def test_g_p_c_are_searched_and_judged() -> None:
    result, _ = _run(5)
    view = result.tree.view(result.rev)
    g, p = result.previous.parent, result.subject.parent
    for node in (g, p, result.subject.child):
        assert any(b.kind.value == "survey" for b in view.searches(node))
    assert result.previous == MoveSubject(g, p)
    assert [j.subject for j in result.judgements] == [result.subject, result.previous]
    assert all(j.status is JudgementStatus.DECIDED for j in result.judgements)


def test_standard_lines_and_the_round_zero_ensure() -> None:
    budget = replace(ReasoningBudget(), pv_plies=2)
    result, _ = _run(5, budget=budget)
    view = result.tree.view(result.rev)
    (observation,) = result.observations
    assert observation.kind == "standard_lines" and observation.round == 0
    lp, l1 = observation.operands
    judgement = result.judgements[0]
    assert lp == LineSegment(
        EngineLineId(result.subject.parent, judgement.search.search_id, judgement.played.rank),
        0,
        len(view.line(lp.line).nodes) - 1,
    )
    assert l1.line.rank == 1
    nodes = view.line(l1.line).nodes
    assert isinstance(view.fact("pieces", nodes[2]), PiecesFacts)  # within pv_plies
    beyond = view.fact("pieces", nodes[3])
    assert isinstance(beyond, PiecesFacts) or beyond == NotComputed("tier")
    flow = material_flow(view, nodes)  # tier records suffice on engine-only nodes
    assert flow.points_before is not None and len(flow.plies) == len(nodes) - 1


def test_san_input_is_normalized_and_moves_after_the_target_are_dropped() -> None:
    result, _ = _run(3)
    assert result.request.moves == ("e2e4", "e7e5", "g1f3")
    assert result.request.root == RootSpec(fen=result.request.root.fen, moves=())


def test_refusals_before_any_engine_work() -> None:
    port = engine()
    controller = Controller(FactEngine(engine=port))
    bad = [
        AnalysisRequest(RootSpec(), GAME, 0, PROFILE),
        AnalysisRequest(RootSpec(), GAME, 7, PROFILE),
        AnalysisRequest(RootSpec(), GAME, 1, PROFILE, language="xx"),
        AnalysisRequest(RootSpec(), GAME, 1, PROFILE, replace(ReasoningBudget(), pv_plies=0)),
    ]
    for request in bad:
        with pytest.raises(InvalidAnalysisRequest):
            controller.round_zero(request)
    assert port.calls == []


def test_an_illegal_move_is_an_invalid_request() -> None:
    with pytest.raises(InvalidAnalysisRequest) as raised:
        _run(2, moves=("e4", "e4"))
    assert isinstance(raised.value.cause, IllegalMoveError)


def test_a_small_tree_bound_cuts_engine_lines_deterministically() -> None:
    budget = replace(ReasoningBudget(), max_tree_nodes=3)
    result, _ = _run(1, budget=budget)
    view = result.tree.view(result.rev)
    ends = {line.end for line in view.lines() if isinstance(line.line_id, EngineLineId)}
    assert LineEnd.BUDGET_LIMIT in ends
    assert result.reproducible  # a node bound is deterministic, unlike a deadline
    again, _ = _run(1, budget=budget)
    assert again.tree.view(again.rev).digest() == view.digest()


def test_determinism_and_cold_versus_warm_store() -> None:
    store = EngineResultStore()
    cold, _ = _run(5, store=store)
    warm, _ = _run(5, store=store)
    fresh, _ = _run(5)
    digests = {r.tree.view(r.rev).digest() for r in (cold, warm, fresh)}
    assert len(digests) == 1
    assert cold.judgements == warm.judgements == fresh.judgements
    assert cold.observations == warm.observations == fresh.observations


def test_a_deadline_cut_marks_the_result_not_reproducible() -> None:
    delay = {"seconds": 0.01}
    budget = replace(ReasoningBudget(), deadline_ms=1)
    result, _ = _run(1, port=scripted({}, delay=delay), budget=budget)
    assert not result.reproducible
