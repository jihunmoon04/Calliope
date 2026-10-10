"""`planned_search_bound` and `TreeView.request` (reasoning R0-D §6.5, §18.2)."""

from __future__ import annotations

import time

import pytest
from synthetic import IDENTITY, engine, synthetic

from calliope.facts import (
    NONE,
    PLAYED,
    EngineProfile,
    EnsureRequest,
    ExpansionSpec,
    ExtendRequest,
    FactEngine,
    InputLine,
    InvalidRequestError,
    OpenRequest,
    RootSpec,
    SessionBudget,
    analysis,
    planned_search_bound,
    storage,
)
from calliope.facts.search import ScriptedEngine

PROFILE = EngineProfile()
PROBE = ExpansionSpec(True, True, False)


def _bound_and_actual(fact_engine, tree, request) -> tuple[int, int]:
    view = tree.view()
    bound = planned_search_bound(view, request)
    rev = fact_engine.extend(tree, request)
    after = tree.view(rev)
    actual = sum(1 for node in after.nodes() for b in after.searches(node.node_id) if b.rev == rev)
    return bound, actual


UNBOUNDED = SessionBudget()


def _session(port=None, budget=UNBOUNDED):
    fact_engine = FactEngine(engine=port or engine(pv_plies=4))
    tree = fact_engine.open(OpenRequest(engine=PROFILE, root_expansion=NONE, budget=budget))
    return fact_engine, tree


def test_a_played_extension_is_bounded() -> None:
    fact_engine, tree = _session()
    line = InputLine("g", ("e4", "e5", "Nf3"))
    bound, actual = _bound_and_actual(fact_engine, tree, ExtendRequest((line,), PLAYED))
    assert actual > 0 and bound >= actual


def test_analysis_lines_with_and_without_comparison() -> None:
    fact_engine, tree = _session()
    fact_engine.extend(tree, ExtendRequest((InputLine("g", ("e4", "e5")),), PLAYED))
    view = tree.view()
    pv_node = next(n.node_id for n in view.nodes() if not view.has_input_role(n.node_id))
    legal = view.fact("status", pv_node).legal_moves[0].uci
    quiet = ExtendRequest((InputLine("q", (legal,), start=pv_node),), analysis("r"), NONE)
    assert _bound_and_actual(fact_engine, tree, quiet) == (0, 0)
    p = view.input_line("g").nodes[1]
    probe = ExtendRequest((InputLine("p", ("h7h6", "h2h3"), start=p),), analysis("r"), PROBE)
    bound, actual = _bound_and_actual(fact_engine, tree, probe)
    assert actual > 0 and bound >= actual


def test_a_skipped_comparison_retried_through_an_analysis_line_is_counted() -> None:
    slow = {"on": True}
    answer = synthetic(4)

    def delayed(request):
        if slow["on"]:
            time.sleep(0.02)
        return answer(request)

    port = ScriptedEngine(IDENTITY, delayed)
    fact_engine, tree = _session(port, SessionBudget(deadline_per_request_ms=5))
    fact_engine.extend(tree, ExtendRequest((InputLine("g", ("g4",)),), PLAYED))
    root = tree.view().root
    assert any(kind == "comparison" for _, kind, _ in tree.view().manifest()[-1].skipped)
    slow["on"] = False
    quiet = ExtendRequest((InputLine("q", ("e4",), start=root),), analysis("r"), NONE)
    bound, actual = _bound_and_actual(fact_engine, tree, quiet)
    assert actual == 1 and bound >= 1  # the retried policy comparison at the root


def test_a_stale_view_and_an_engine_less_session() -> None:
    fact_engine, tree = _session()
    stale = tree.view()
    fact_engine.extend(tree, ExtendRequest((InputLine("g", ("e4",)),), PLAYED))
    request = ExtendRequest((InputLine("h", ("d4",)),), PLAYED)
    with pytest.raises(InvalidRequestError):
        planned_search_bound(stale, request)
    plain = FactEngine()
    tree = plain.open(OpenRequest())
    assert planned_search_bound(tree.view(), request) == 0


def test_tree_view_request_is_the_normalized_log_and_survives_load() -> None:
    fact_engine, tree = _session()
    fact_engine.extend(tree, ExtendRequest((InputLine("g", ("e4", "e5")),), PLAYED))
    view = tree.view()
    engine_only = sorted(n.node_id for n in view.nodes() if not view.has_input_role(n.node_id))
    nodes = engine_only[:2]
    assert fact_engine.ensure(tree, EnsureRequest((nodes[1], nodes[0]), ("pieces",))) == 3
    view = tree.view()
    opening, extend, ensure = (view.request(rev) for rev in (1, 2, 3))
    assert isinstance(opening, OpenRequest) and opening.root == RootSpec(
        fen=opening.root.fen, moves=()
    )
    assert extend.lines[0].moves == ("e2e4", "e7e5")  # SAN in, canonical UCI logged
    assert ensure.nodes == tuple(nodes)  # sorted
    with pytest.raises(KeyError):
        view.request(4)
    with pytest.raises(KeyError):
        tree.view(1).request(2)
    loaded = FactEngine(engine=engine(pv_plies=4)).load(storage.save(tree))
    assert [loaded.view().request(r) for r in (1, 2, 3)] == [opening, extend, ensure]
