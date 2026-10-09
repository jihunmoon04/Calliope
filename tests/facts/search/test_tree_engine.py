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
    root_fen = chess.Board("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1").fen()
    assert {c.input.fen for c in port.calls} == {root_fen}  # the mated node is never searched


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
    view, nodes = _extend(fact_engine, tree, "h2h3")
    assert view.basis(tree.root) == NotComputed("DEADLINE")
    assert _kinds(view, nodes[1]) == [SearchKind.SURVEY]  # surveys still run past the deadline


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
    assert warm.view().runtimes() and all(r.reused is not None for r in warm.view().runtimes())
    results = []
    shared = EngineResultStore()  # cold: the threads really share the port and the store

    def cold_build():
        fact_engine = FactEngine(engine=port, store=shared)
        tree = fact_engine.open(OpenRequest(engine=PROFILE))
        for i, moves in enumerate(lines):
            fact_engine.extend(tree, ExtendRequest((InputLine(f"l{i}", moves),), PLAYED))
        results.append(_records(tree))

    threads = [threading.Thread(target=cold_build) for _ in range(3)]
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


# -- review F4b-C1/C3 regressions ---------------------------------------------------------------


def _scripted(pvs: dict[str, tuple[str, ...]]):
    """Answers a one-rank search at the listed FENs with the given PV."""

    from calliope.facts.search import Bound, RawLine, RawSearch, StoppedBy
    from calliope.facts.search.inputs import window_end

    def answer(request):
        board = window_end(request.input)
        pv = pvs.get(board.fen()) or (min(m.uci() for m in board.legal_moves),)
        line = RawLine(1, 12, 14, ("cp", 0), Bound.EXACT, (0, 1000, 0), 1, 0, pv)
        return RawSearch((line,), StoppedBy.DEPTH, 1)

    return ScriptedEngine(IDENTITY, answer)


def test_engine_lines_end_at_checkmate_and_stalemate() -> None:
    mate = "6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1"
    stale = "7k/8/6Q1/8/8/8/8/K7 w - - 0 1"
    for fen, pv, end in (
        (mate, ("a1a8",), LineEnd.CHECKMATE),
        (stale, ("g6f7",), LineEnd.STALEMATE),
    ):
        fact_engine = FactEngine(engine=_scripted({chess.Board(fen).fen(): pv}))
        tree = fact_engine.open(
            OpenRequest(root=RootSpec(fen=fen), engine=EngineProfile(multipv=1))
        )
        view = tree.view()
        (line,) = [ln for ln in view.lines() if isinstance(ln.line_id, EngineLineId)]
        assert line.end is end and line.unattached_plies == 0
        audit_engine_tree(tree)


def test_an_already_bound_analysis_search_is_not_attached_later() -> None:
    fact_engine, tree, _port = _open()
    probe = ExpansionSpec(True, True, False)
    view, _ = _extend(fact_engine, tree, "h2h3", label="p1", role=analysis("b"), expansion=probe)
    lines = len(view.lines())
    bindings = len(view.searches(tree.root))
    view, _ = _extend(fact_engine, tree, "h2h3", label="p2", role=analysis("b"), expansion=FULL)
    assert len(view.searches(tree.root)) == bindings
    new_engine_lines = [
        ln
        for ln in view.lines()
        if isinstance(ln.line_id, EngineLineId)
        and ln.rev == tree.rev
        and ln.line_id.anchor == tree.root
    ]
    assert new_engine_lines == []
    assert view.manifest()[-1].searches_reused == ()
    assert len(view.lines()) >= lines


def test_comparison_not_requested_is_in_the_manifest() -> None:
    no_compare = ExpansionSpec(True, False, True)
    fact_engine, tree, _port = _open(
        defaults=Defaults(played=no_compare), root_expansion=no_compare
    )
    view, _ = _extend(fact_engine, tree, "h2h3")
    assert view.manifest()[-1].skipped == ((tree.root, "comparison", "COMPARISON_NOT_REQUESTED"),)


def test_a_skipped_comparison_is_retried_when_the_node_is_in_a_request() -> None:
    store = EngineResultStore()
    port = engine()
    fact_engine = FactEngine(engine=port, store=store)
    tree = fact_engine.open(OpenRequest(engine=PROFILE, budget=Budget(max_searches=2)))
    _extend(fact_engine, tree, "h2h3")
    assert tree.view().basis(tree.root) == NotComputed("BUDGET")
    helper = fact_engine.open(OpenRequest(engine=PROFILE))  # fills the store with the comparison
    _extend(fact_engine, helper, "h2h3")
    calls = len(port.calls)
    view, _ = _extend(fact_engine, tree, "a2a3", label="x", role=EXPLORED, expansion=NONE)
    basis = view.basis(tree.root)
    assert isinstance(basis, str) and view.search(basis).kind is SearchKind.COMPARISON
    assert len(port.calls) == calls  # a store hit: free under the budget
    audit_engine_tree(tree)


def test_transpositions_share_one_search_and_get_two_lines() -> None:
    fact_engine, tree, port = _open()
    _extend(fact_engine, tree, "e4", "e5", "Nf3", "Nc6", "d4", label="a")
    calls = len(port.calls)
    view, nodes = _extend(
        fact_engine, tree, "Nf3", "Nc6", "e4", "e5", "d4", label="b", role=EXPLORED
    )
    a_end = view.input_line("a").nodes[-1]
    b_end = nodes[-1]
    assert a_end != b_end
    (sa,), (sb,) = view.searches(a_end), view.searches(b_end)
    assert sa.search_id == sb.search_id
    anchors = {
        ln.line_id.anchor
        for ln in view.lines()
        if isinstance(ln.line_id, EngineLineId) and ln.line_id.search_id == sa.search_id
    }
    assert anchors == {a_end, b_end}
    end_input = view.search(sa.search_id).input
    assert sum(c.input == end_input for c in port.calls) == 1  # asked once, for both nodes
    assert len(port.calls) > calls
    audit_engine_tree(tree)


def test_transposed_request_nodes_share_one_irregular_search() -> None:
    board = chess.Board()
    for move in ("e4", "e5", "Nf3", "Nc6", "d4"):
        board.push_san(move)
    board.fullmove_number = 1  # the engine input's fullmove number (F4-D §4)
    fact_engine, tree, port = _open(engine(irregular=frozenset({board.fen()})))
    fact_engine.extend(
        tree,
        ExtendRequest(
            (
                InputLine("a", ("e4", "e5", "Nf3", "Nc6", "d4")),
                InputLine("b", ("Nf3", "Nc6", "e4", "e5", "d4")),
            ),
            EXPLORED,
        ),
    )
    view = tree.view()
    ends = [view.input_line(label, RoleKind.EXPLORED).nodes[-1] for label in ("a", "b")]
    (sa,), (sb,) = (view.searches(n) for n in ends)
    assert sa.search_id == sb.search_id and not view.search(sa.search_id).regular
    end_input = view.search(sa.search_id).input
    surveys = [c for c in port.calls if c.input == end_input and c.root_moves is None]
    assert len(surveys) == 1  # one engine question, one (irregular) answer for both nodes


def test_no_comparison_after_an_irregular_survey_but_one_after_a_regular_one() -> None:
    after_h3 = chess.Board("rnbqkbnr/pppppppp/8/8/8/7P/PPPPPPP1/RNBQKBNR b KQkq - 0 1").fen()
    for irregular, expected in (
        (frozenset({after_h3}), [SearchKind.SURVEY]),
        (frozenset(), [SearchKind.SURVEY, SearchKind.COMPARISON]),
    ):
        fact_engine, tree, _port = _open(engine(irregular=irregular))
        view, nodes = _extend(fact_engine, tree, "h2h3", "h7h6")  # h7h6 is outside the survey
        assert _kinds(view, nodes[1]) == expected


def test_attachment_order_decides_budget_cuts() -> None:
    _fact_engine, tree, _port = _open(budget=Budget(max_nodes=7))
    view = tree.view()
    survey = view.searches(tree.root)[0].search_id
    by_rank = {
        ln.line_id.rank: ln
        for ln in view.lines()
        if isinstance(ln.line_id, EngineLineId) and ln.line_id.search_id == survey
    }
    assert by_rank[1].end is LineEnd.PV_END and len(by_rank[1].nodes) == 5
    assert by_rank[2].end is LineEnd.BUDGET_LIMIT and len(by_rank[2].nodes) == 3
    assert all(
        by_rank[r].end is LineEnd.BUDGET_LIMIT and len(by_rank[r].nodes) == 1 for r in (3, 4, 5)
    )


def test_budget_limit_only_when_a_new_node_is_needed() -> None:
    fact_engine, tree, _port = _open(budget=Budget(max_nodes=21))
    view = tree.view()
    assert len(view.nodes()) == 21  # every root line attached
    first = view.lines()[0].nodes[1]
    move = view.node(first).incoming_move
    view, nodes = _extend(fact_engine, tree, move)
    survey = view.searches(nodes[1])[0].search_id
    line = view.line(EngineLineId(nodes[1], survey, 1))
    assert line.end is LineEnd.BUDGET_LIMIT and len(line.nodes) == 4 and line.unattached_plies == 1


def test_analysis_search_skipped_for_budget() -> None:
    fact_engine, tree, _port = _open(budget=Budget(max_searches=2))
    view, _ = _extend(fact_engine, tree, "h2h3", label="p", role=analysis("b"), expansion=FULL)
    assert (tree.root, "analysis", "BUDGET") in view.manifest()[-1].skipped


def test_precheck_counts_role_gain() -> None:
    fact_engine, tree, _port = _open(budget=Budget(max_searches=1))
    view = tree.view()
    move = view.node(view.lines()[0].nodes[1]).incoming_move  # an engine-only node
    with pytest.raises(BudgetExceededError):
        _extend(fact_engine, tree, move)


def test_irregular_comparison_is_basis_row_seven() -> None:
    plain = synthetic()

    def answer(request):
        raw = plain(request)
        if request.root_moves is None:
            return raw
        from calliope.facts.search import StoppedBy

        return type(raw)(raw.lines, StoppedBy.TIME, raw.elapsed_ms)

    fact_engine, tree, _port = _open(ScriptedEngine(IDENTITY, answer))
    view, _ = _extend(fact_engine, tree, "h2h3")
    assert SearchKind.COMPARISON in _kinds(view, tree.root)
    assert view.basis(tree.root) == NotComputed("IRREGULAR_SEARCH")
    audit_engine_tree(tree)


def test_repeated_requests_bind_and_attach_nothing_new() -> None:
    fact_engine, tree, port = _open()
    view, _ = _extend(fact_engine, tree, "e4", "e5")
    before = (len(port.calls), sum(len(view.searches(n.node_id)) for n in view.nodes()))
    engine_lines = sum(isinstance(ln.line_id, EngineLineId) for ln in view.lines())
    view, _ = _extend(fact_engine, tree, "e4", "e5", label="again")
    after = (len(port.calls), sum(len(view.searches(n.node_id)) for n in view.nodes()))
    assert after == before
    assert sum(isinstance(ln.line_id, EngineLineId) for ln in view.lines()) == engine_lines
