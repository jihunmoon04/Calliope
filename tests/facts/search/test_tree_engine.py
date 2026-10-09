"""F4-D §9.2: engine work in the tree, with the synthetic engine."""

import threading

import chess
import pytest
from engine_auditor import audit_engine_tree
from synthetic import IDENTITY, engine, synthetic

from calliope.facts import (
    EXPLORED,
    PLAYED,
    ExtendRequest,
    FactEngine,
    InputLine,
    OpenRequest,
    RootSpec,
    analysis,
)
from calliope.facts.errors import (
    BudgetExceededError,
    CrossSearchError,
    EngineError,
    InvalidRequestError,
)
from calliope.facts.request import FULL, NONE, Defaults, EnsureRequest, ExpansionSpec, RoleKind
from calliope.facts.request import SessionBudget as Budget
from calliope.facts.search import EngineProfile, EngineResultStore, ScriptedEngine, SearchKind
from calliope.facts.search.profile import EngineIdentity
from calliope.facts.tree import NOT_IN_BASIS, EngineLineId, LineEnd, order
from calliope.facts.values import NotApplicable, NotComputed

PROFILE = EngineProfile()
SURVEY_ONLY = ExpansionSpec(True, False, False)


def _open(port=None, fen=None, **kwargs):
    port = port or engine()
    fact_engine = FactEngine(engine=port, store=kwargs.pop("store", None))
    tree = fact_engine.open(OpenRequest(root=RootSpec(fen=fen), engine=PROFILE, **kwargs))
    return fact_engine, tree, port


def _extend(fact_engine, tree, *moves, label="g", role=PLAYED, start=None, expansion=None):
    fact_engine.extend(
        tree, ExtendRequest((InputLine(label, moves, start=start),), role, expansion)
    )
    view = tree.view()
    kind = role.kind
    return view, view.input_line(label, kind, by=role.by or "").nodes


def _kinds(view, node):
    return [b.kind for b in view.searches(node)]


# -- the root, expansions, planned work ------------------------------------------------------


def test_root_is_surveyed_at_open_under_its_role() -> None:
    _engine, tree, port = _open()
    view = tree.view()
    (root_role,) = view.roles(tree.root)
    assert root_role.kind is RoleKind.ROOT and root_role.expansion == FULL
    assert _kinds(view, tree.root) == [SearchKind.SURVEY] and len(port.calls) == 1
    assert isinstance(view.basis(tree.root), str)
    assert len([ln for ln in view.lines() if isinstance(ln.line_id, EngineLineId)]) == 5
    audit_engine_tree(tree)
    _engine, tree, port = _open(root_expansion=NONE)
    assert port.calls == [] and tree.view().searches(tree.root) == ()


def test_no_engine_session_has_no_root_role_and_no_calls() -> None:
    port = engine()
    fact_engine = FactEngine(engine=port)
    tree = fact_engine.open(OpenRequest())
    fact_engine.extend(tree, ExtendRequest((InputLine("g", ("e4",)),), PLAYED))
    assert all(r.kind is not RoleKind.ROOT for r in tree.view().roles(tree.root))
    assert all(r.expansion is None for r in tree.view().roles(tree.root))
    assert port.calls == []


def test_invalid_expansions_and_missing_analysis_expansion_are_refused() -> None:
    with pytest.raises(InvalidRequestError):
        ExpansionSpec(False, True, False)
    with pytest.raises(InvalidRequestError):
        ExpansionSpec(False, False, True)
    fact_engine, tree, _port = _open()
    with pytest.raises(InvalidRequestError, match="ANALYSIS"):
        fact_engine.extend(tree, ExtendRequest((InputLine("a", ("e4",)),), analysis("x")))


def test_surveys_run_in_line_order_and_only_at_request_nodes() -> None:
    fact_engine, tree, port = _open()
    _view, nodes = _extend(fact_engine, tree, "e4", "e5", "Nf3")
    surveyed = [c.input for c in port.calls if c.root_moves is None]
    assert len(surveyed) == 4  # root at open + 3 line nodes, in order
    before = len(port.calls)
    _extend(fact_engine, tree, "d4", label="other", role=EXPLORED)
    new = port.calls[before:]
    assert len(new) == 2  # the d4 node's survey, and the root's re-comparison
    view = tree.view()
    assert all(view.searches(n) for n in nodes)


def test_effective_expansion_union_example() -> None:
    # N surveyed under FULL; an EXPLORED request with NONE starts at N and adds a child outside
    # the survey: N's effective (policy) expansion still has `comparison`, so N is compared.
    fact_engine, tree, _port = _open()
    view, _nodes = _extend(fact_engine, tree, "h2h3", label="x", role=EXPLORED, expansion=NONE)
    assert SearchKind.COMPARISON in _kinds(view, tree.root)
    assert view.searches(view.input_line("x", RoleKind.EXPLORED).nodes[1]) == ()


def test_analysis_comparison_never_changes_a_played_basis() -> None:
    defaults = Defaults(played=ExpansionSpec(True, False, True))
    fact_engine, tree, _port = _open(
        defaults=defaults, root_expansion=ExpansionSpec(True, False, True)
    )
    view, _ = _extend(fact_engine, tree, "h2h3")
    assert view.basis(tree.root) == NotComputed("COMPARISON_NOT_REQUESTED")
    view, _ = _extend(
        fact_engine, tree, "h2h4", label="probe", role=analysis("block"), expansion=FULL
    )
    assert view.basis(tree.root) == NotComputed("COMPARISON_NOT_REQUESTED")
    assert SearchKind.COMPARISON not in _kinds(view, tree.root)
    assert SearchKind.ANALYSIS in _kinds(view, tree.root)


def test_comparison_trigger_set_and_recomparison() -> None:
    fact_engine, tree, port = _open()
    view, _nodes = _extend(fact_engine, tree, "a2a3")  # inside the survey: no comparison
    assert _kinds(view, tree.root) == [SearchKind.SURVEY]
    assert view.basis(tree.root) == view.searches(tree.root)[0].search_id
    view, _ = _extend(fact_engine, tree, "h2h3", label="x", role=EXPLORED)
    first = view.search(view.searches(tree.root)[-1].search_id)
    assert first.kind is SearchKind.COMPARISON and "h2h3" in first.root_moves
    view, _ = _extend(fact_engine, tree, "g2g3", label="y", role=EXPLORED)
    second = view.search(view.basis(tree.root))
    assert set(second.root_moves) == set(first.root_moves) | {"g2g3"}
    calls = len(port.calls)
    _extend(fact_engine, tree, "g2g3", label="y2", role=EXPLORED)  # nothing new
    assert len(port.calls) == calls


def test_analysis_children_never_enter_the_comparison_set_and_analysis_searches() -> None:
    fact_engine, tree, _port = _open()
    view, nodes = _extend(
        fact_engine, tree, "h2h3", "h7h6", label="p", role=analysis("b"), expansion=FULL
    )
    assert SearchKind.COMPARISON not in _kinds(view, tree.root)
    assert _kinds(view, tree.root) == [SearchKind.SURVEY, SearchKind.ANALYSIS]
    assert SearchKind.ANALYSIS in _kinds(view, nodes[1])
    assert SearchKind.ANALYSIS not in _kinds(view, nodes[2])  # the end node: no child move
    assert view.child_score(nodes[1]) is NOT_IN_BASIS  # the basis is the survey
    analysis_search = view.search(view.searches(tree.root)[-1].search_id)
    anchored = [
        ln.line_id.search_id
        for ln in view.lines()
        if isinstance(ln.line_id, EngineLineId) and ln.line_id.anchor == tree.root
    ]
    assert analysis_search.search_id in anchored  # attached by its own request (FULL)


def test_attachment_after_an_expansion_upgrade() -> None:
    fact_engine, tree, _port = _open(root_expansion=SURVEY_ONLY)
    view = tree.view()
    assert not any(isinstance(ln.line_id, EngineLineId) for ln in view.lines())
    view, _ = _extend(fact_engine, tree, "a2a3")
    root_lines = [
        ln
        for ln in view.lines()
        if isinstance(ln.line_id, EngineLineId) and ln.line_id.anchor == tree.root
    ]
    assert len(root_lines) == 5  # the open-time survey attached once PLAYED gave attach_lines
    count = len(view.lines())
    _extend(fact_engine, tree, "a2a3", label="again")
    assert len(tree.view().lines()) == count + 1  # only the new input line; nothing re-attached


def test_basis_rows_and_scores() -> None:
    after_h3 = "rnbqkbnr/pppppppp/8/8/8/7P/PPPPPPP1/RNBQKBNR b KQkq - 0 1"
    fact_engine, tree, _port = _open(engine(irregular=frozenset({chess.Board(after_h3).fen()})))
    view, nodes = _extend(fact_engine, tree, "h2h3", "a7a6")
    assert view.basis(nodes[1]) == NotComputed("IRREGULAR_SEARCH")
    assert _kinds(view, nodes[1]) == [SearchKind.SURVEY]  # no comparison after an irregular survey
    assert view.manifest()[-1].load_dependent
    engine_only = next(n.node_id for n in view.nodes() if not view.has_input_role(n.node_id))
    assert view.basis(engine_only) == NotComputed("PARENT_NOT_SEARCHED")
    score = view.child_score(nodes[1])
    assert score.search_id == view.basis(tree.root)
    assert view.child_score(nodes[2]) == NotComputed("IRREGULAR_SEARCH")
    deeper = view.child_score(view.children(nodes[2])[0])
    assert deeper.search_id == view.basis(nodes[2]) != score.search_id
    with pytest.raises(CrossSearchError):
        order(score, deeper)
    sibling = view.child_score(view.children(tree.root)[0])
    assert order(score, sibling) in (-1, 0, 1)
    audit_engine_tree(tree)


def test_terminal_nodes_are_not_applicable_and_never_searched() -> None:
    fact_engine, tree, port = _open(fen="6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1")
    view, nodes = _extend(fact_engine, tree, "a1a8")
    assert view.node(nodes[1]).terminal.ends_game
    assert view.basis(nodes[1]) == NotApplicable("terminal or after a terminal node")
    assert view.searches(nodes[1]) == ()
    calls = len(port.calls)
    board = chess.Board(view.node(nodes[1]).fen)
    assert board.is_checkmate()  # no move can follow: nothing to search beyond it
    assert len(port.calls) == calls


# -- engine lines --------------------------------------------------------------------------------


def test_engine_lines_roles_shared_edges_and_transpositions() -> None:
    fact_engine, tree, _port = _open(engine(pv_plies=3))
    view, nodes = _extend(fact_engine, tree, "a2a3", "a7a5")
    survey = view.searches(tree.root)[0].search_id
    roles = view.roles(nodes[1], on_edge=True)
    kinds = {r.kind for r in roles}
    assert kinds == {RoleKind.PLAYED, RoleKind.ENGINE}  # the played move is the PV's first move
    engine_role = next(r for r in roles if r.kind is RoleKind.ENGINE and r.search_id == survey)
    assert (engine_role.anchor, engine_role.rank, engine_role.index) == (tree.root, 1, 1)
    audit_engine_tree(tree)


def test_attachment_stops_at_terminal_nodes_and_counts_unattached_plies() -> None:
    _fact_engine, tree, _port = _open(fen="4k3/8/8/8/8/8/8/3qK3 w - - 0 1")
    view = tree.view()
    line = view.line(EngineLineId(tree.root, view.searches(tree.root)[0].search_id, 1))
    assert line.end is LineEnd.DRAW_RULE and line.unattached_plies == 3
    assert view.node(line.nodes[-1]).terminal.ends_game


def test_budget_limit_on_nodes_cuts_lines() -> None:
    _fact_engine, tree, _port = _open(budget=Budget(max_nodes=7))
    view = tree.view()
    ends = {ln.end for ln in view.lines() if isinstance(ln.line_id, EngineLineId)}
    assert LineEnd.BUDGET_LIMIT in ends and len(view.nodes()) == 7


# -- tiers and role gain ---------------------------------------------------------------------------


def test_tier_and_role_gain() -> None:
    fact_engine, tree, port = _open()
    view = tree.view()
    pv_node = next(n.node_id for n in view.nodes() if not view.has_input_role(n.node_id))
    assert view.fact("pieces", pv_node) == NotComputed("tier")
    assert not isinstance(view.fact("material", pv_node), NotComputed)
    move = view.node(pv_node).incoming_move
    calls = len(port.calls)
    view, nodes = _extend(fact_engine, tree, move)
    assert nodes[1] == pv_node and not isinstance(view.fact("pieces", pv_node), NotComputed)
    assert SearchKind.SURVEY in _kinds(view, pv_node) and len(port.calls) > calls
    # a line starting at an engine-only node
    deeper = next(
        n.node_id for n in view.nodes() if not view.has_input_role(n.node_id) and n.ply == 2
    )
    child = chess.Board(view.node(deeper).fen)
    reply = max(m.uci() for m in child.legal_moves)
    view, nodes = _extend(fact_engine, tree, reply, label="s", role=EXPLORED, start=deeper)
    assert not isinstance(view.fact("pieces", deeper), NotComputed)
    assert view.searches(deeper)
    fact_engine.ensure(tree, EnsureRequest((pv_node,), ("pieces",)))


# -- budget, deadline, failures --------------------------------------------------------------------


def test_survey_precheck_refuses_and_commits_nothing() -> None:
    fact_engine, tree, port = _open(budget=Budget(max_searches=2))
    rev = tree.rev
    with pytest.raises(BudgetExceededError):
        _extend(fact_engine, tree, "e4", "e5")
    assert tree.rev == rev and len(port.calls) == 1


def test_comparisons_skipped_for_budget_and_retried() -> None:
    fact_engine, tree, _port = _open(budget=Budget(max_searches=2))
    view, _ = _extend(fact_engine, tree, "h2h3")  # survey uses the last call
    assert view.basis(tree.root) == NotComputed("BUDGET")
    assert view.manifest()[-1].skipped == ((tree.root, "comparison", "BUDGET"),)


def test_deadline_skips_comparisons_and_lines() -> None:
    fact_engine, tree, _port = _open(budget=Budget(deadline_per_request_ms=0))
    view = tree.view()
    assert view.manifest()[0].load_dependent
    assert {ln.end for ln in view.lines() if isinstance(ln.line_id, EngineLineId)} == {
        LineEnd.BUDGET_LIMIT
    }
    view, _ = _extend(fact_engine, tree, "h2h3")
    assert view.basis(tree.root) == NotComputed("DEADLINE")


def test_engine_failure_commits_nothing() -> None:
    def answer(request):
        if " b " in request.input.fen:
            raise EngineError("engine died")
        return synthetic()(request)

    fact_engine, tree, _port = _open(ScriptedEngine(IDENTITY, answer))
    rev, nodes = tree.rev, len(tree.view().nodes())
    with pytest.raises(EngineError):
        _extend(fact_engine, tree, "e4")
    assert tree.rev == rev and len(tree.view().nodes()) == nodes


# -- session binding and sharing --------------------------------------------------------------------


def test_session_is_bound_to_its_engine() -> None:
    _fact_engine, tree, _port = _open()
    with pytest.raises(InvalidRequestError, match="port"):
        FactEngine().extend(tree, ExtendRequest((InputLine("g", ("e4",)),), PLAYED))
    other = ScriptedEngine(
        EngineIdentity("Stockfish 19", "x", "9" * 64, IDENTITY.options), synthetic()
    )
    with pytest.raises(InvalidRequestError, match="port"):
        FactEngine(engine=other).extend(tree, ExtendRequest((InputLine("g", ("e4",)),), PLAYED))
    with pytest.raises(InvalidRequestError, match="engine port"):
        FactEngine().open(OpenRequest(engine=PROFILE))


def _records(tree):
    view = tree.view()
    return (
        sorted((str(n.node_id), n.fen) for n in view.nodes()),
        sorted(str(ln.line_id) + str(ln.nodes) + ln.end.value for ln in view.lines()),
        sorted(
            (str(n.node_id), b.search_id) for n in view.nodes() for b in view.searches(n.node_id)
        ),
        sorted((str(n.node_id), str(view.basis(n.node_id))) for n in view.nodes()),
    )


def test_cold_and_warm_store_give_equal_trees_and_threads_share_safely() -> None:
    store = EngineResultStore()
    port = engine()
    lines = (("e4", "e5", "Nf3", "Nc6"), ("d4", "d5", "c4"))

    def build():
        fact_engine = FactEngine(engine=port, store=store)
        tree = fact_engine.open(OpenRequest(engine=PROFILE))
        for i, moves in enumerate(lines):
            fact_engine.extend(tree, ExtendRequest((InputLine(f"l{i}", moves),), PLAYED))
        return tree

    cold = build()
    calls = len(port.calls)
    warm = build()
    assert len(port.calls) == calls  # every search from the store
    assert _records(cold) == _records(warm)
    assert any(r.reused is not None for r in warm.view().runtimes())
    results = []
    threads = [threading.Thread(target=lambda: results.append(_records(build()))) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert all(r == _records(cold) for r in results)
    audit_engine_tree(cold)


def test_manifest_records_engine_work() -> None:
    fact_engine, tree, _port = _open()
    view, _ = _extend(fact_engine, tree, "h2h3")
    open_delta, extend_delta = view.manifest()
    assert dict(open_delta.engine).keys() == {"profile", "identity", "pinned_options"}
    assert dict(extend_delta.searches_run) == {"comparison": 1, "survey": 1}
    assert dict(extend_delta.engine_lines) == {"pv_end": 11}
    assert not extend_delta.load_dependent


def test_ensure_never_calls_the_engine() -> None:
    fact_engine, tree, port = _open()
    calls = len(port.calls)
    nodes = tuple(n.node_id for n in tree.view().nodes())
    fact_engine.ensure(tree, EnsureRequest(nodes, ("pieces", "patterns")))
    assert len(port.calls) == calls


def test_after_terminal_nodes_are_never_searched() -> None:
    fact_engine, tree, port = _open(fen="4k3/8/8/8/8/8/8/3qK3 w - - 0 1")
    view, nodes = _extend(fact_engine, tree, "e1d1", "e8e7", "d1d2")
    assert view.node(nodes[1]).terminal.ends_game
    assert all(view.node(n).after_terminal for n in nodes[2:])
    assert all(view.searches(n) == () for n in nodes[1:])
    assert all(isinstance(view.basis(n), NotApplicable) for n in nodes[1:])
    assert len(port.calls) == 1  # the root only
