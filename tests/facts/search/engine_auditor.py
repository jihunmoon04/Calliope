"""Test-only auditor of engine facts in a tree (F4-D §9.2.7). It recomputes, independently:

- every bound search's `EngineInput` from a full python-chess replay of the node's history;
- every PV's legality and every attached engine line node by node, with its end status;
- every node's basis from the recorded searches, by the F4-D §7.3 table;
- that every child score comes from its parent's basis search (no cross-search value).
"""

from __future__ import annotations

import itertools

import chess

from calliope.facts.keys import NodeId
from calliope.facts.request import RoleKind
from calliope.facts.search.records import SearchKind
from calliope.facts.tree import EngineLineId, LineEnd, SearchScore
from calliope.facts.values import NotApplicable, NotComputed


def _history(tree, view, node_id) -> chess.Board:
    session = tree._session
    board = session.start_board.copy()
    for uci in session.pre_root_moves:
        board.push_uci(uci)
    for n in view.path(node_id)[1:]:
        board.push_uci(view.node(n).incoming_move)
    return board


def _expected_input(board: chess.Board) -> tuple[str, tuple[str, ...]]:
    w = min(board.halfmove_clock, len(board.move_stack))
    start = board.copy()
    moves = []
    for _ in range(w):
        moves.append(start.pop().uci())
    fields = start.fen(en_passant="legal").split()
    fields[5] = "1"
    return " ".join(fields), tuple(reversed(moves))


INPUT = (RoleKind.ROOT, RoleKind.PLAYED, RoleKind.EXPLORED, RoleKind.ANALYSIS)


def _flags(view, node_id, *, policy: bool) -> tuple[bool, bool, bool]:
    """(survey, comparison, attach_lines) recomputed from the role entries (F4-D §6.2)."""

    survey = comparison = attach = False
    for role in view.roles(node_id):
        if role.kind not in INPUT or role.expansion is None:
            continue
        if policy and role.kind is RoleKind.ANALYSIS:
            continue
        survey |= role.expansion.survey
        attach |= role.expansion.attach_lines
        if role.kind is not RoleKind.ANALYSIS:
            comparison |= role.expansion.comparison
    return survey, comparison, attach


def audit_engine_tree(tree) -> None:
    view = tree.view()
    with tree._publish_lock:
        stored_basis = {n: list(entries) for n, entries in tree._store.basis.items()}
    for entries in stored_basis.values():
        values = [e.value for e in entries]
        assert all(a != b for a, b in itertools.pairwise(values))  # only on change
        assert all(
            not isinstance(v, NotApplicable) and v != NotComputed("PARENT_NOT_SEARCHED")
            for v in values
        )  # rows 1–2 are derived, never written
    for node in view.nodes():
        bindings = view.searches(node.node_id)
        if bindings:
            assert any(r.kind in INPUT for r in view.roles(node.node_id))  # input-role nodes only
            board = _history(tree, view, node.node_id)
            assert not node.terminal.ends_game and not node.after_terminal
            if _flags(view, node.node_id, policy=False)[2]:
                for binding in bindings:
                    if binding.kind is SearchKind.ANALYSIS:
                        continue
                    ranks = [
                        ln.line_id.rank
                        for ln in view.lines()
                        if isinstance(ln.line_id, EngineLineId)
                        and ln.line_id.anchor == node.node_id
                        and ln.line_id.search_id == binding.search_id
                    ]
                    expected = [ln.rank for ln in view.search(binding.search_id).lines]
                    assert ranks == expected  # attached exactly once, every rank
            for binding in bindings:
                search = view.search(binding.search_id)
                assert (search.input.fen, search.input.moves) == _expected_input(board)
                for line in search.lines:
                    walker = board.copy(stack=False)
                    for uci in line.pv:
                        move = chess.Move.from_uci(uci)
                        assert move in walker.legal_moves
                        walker.push(move)
        _audit_basis(view, node)
        if node.parent is not None:
            score = view.child_score(node.node_id)
            if isinstance(score, SearchScore):
                basis = view.search(view.basis(node.parent))
                line = next(ln for ln in basis.lines if ln.move == node.incoming_move)
                assert (score.search_id, score.rank, score.score, score.bound) == (
                    basis.search_id,
                    line.rank,
                    line.score,
                    line.bound,
                )  # every value from the one basis search
    for line in view.lines():
        if isinstance(line.line_id, EngineLineId):
            _audit_line(tree, view, line)


def _audit_line(tree, view, line) -> None:
    anchor, search_id, rank = line.line_id.anchor, line.line_id.search_id, line.line_id.rank
    search = view.search(search_id)
    pv = next(ln.pv for ln in search.lines if ln.rank == rank)
    assert line.nodes[0] == anchor
    board = _history(tree, view, anchor)
    current = anchor
    for index, node_id in enumerate(line.nodes[1:], start=1):
        assert node_id == NodeId.child(current, pv[index - 1])
        board.push_uci(pv[index - 1])
        assert view.node(node_id).fen == board.fen(en_passant="legal")
        for on_edge in (True, False):
            assert any(
                r.kind is RoleKind.ENGINE
                and (r.anchor, r.search_id, r.rank, r.index) == (anchor, search_id, rank, index)
                for r in view.roles(node_id, on_edge=on_edge)
            )
        current = node_id
    attached = len(line.nodes) - 1
    assert line.unattached_plies == len(pv) - attached
    last = view.node(line.nodes[-1])
    if attached and last.terminal.ends_game:
        assert line.end in (LineEnd.CHECKMATE, LineEnd.STALEMATE, LineEnd.DRAW_RULE)
    elif attached == len(pv):
        assert line.end is LineEnd.PV_END
    else:
        assert line.end is LineEnd.BUDGET_LIMIT


def _audit_basis(view, node) -> None:
    basis = view.basis(node.node_id)
    if node.terminal.ends_game or node.after_terminal:
        assert isinstance(basis, NotApplicable)
        return
    surveys = [b for b in view.searches(node.node_id) if b.kind is SearchKind.SURVEY]
    if not surveys:
        assert basis == NotComputed("PARENT_NOT_SEARCHED")
        return
    survey = view.search(surveys[0].search_id)
    if not survey.regular:
        assert basis == NotComputed("IRREGULAR_SEARCH")
        return
    wanted = {ln.move for ln in survey.lines}
    for child in view.children(node.node_id):
        edge_roles = view.roles(child, on_edge=True)
        if any(r.kind in (RoleKind.PLAYED, RoleKind.EXPLORED) for r in edge_roles):
            wanted.add(view.node(child).incoming_move)
    if len(wanted) == len(survey.lines):
        assert basis == survey.search_id
        return
    if not _flags(view, node.node_id, policy=True)[1]:
        assert basis == NotComputed("COMPARISON_NOT_REQUESTED")
        return
    comparisons = [
        view.search(b.search_id)
        for b in view.searches(node.node_id)
        if b.kind is SearchKind.COMPARISON
    ]
    covering = [c for c in comparisons if set(c.root_moves) >= wanted]
    if covering:
        last = covering[-1]
        assert basis == (last.search_id if last.regular else NotComputed("IRREGULAR_SEARCH"))
    else:
        assert basis in (NotComputed("BUDGET"), NotComputed("DEADLINE"))
