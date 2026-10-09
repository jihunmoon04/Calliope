"""Test-only auditor of engine facts in a tree (F4-D §9.2.7). It recomputes, independently:

- every bound search's `EngineInput` from a full python-chess replay of the node's history;
- every PV's legality and every attached engine line node by node, with its end status;
- every node's basis from the recorded searches, by the F4-D §7.3 table;
- that every child score comes from its parent's basis search (no cross-search value).
"""

from __future__ import annotations

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


def audit_engine_tree(tree) -> None:
    view = tree.view()
    for node in view.nodes():
        bindings = view.searches(node.node_id)
        if bindings:
            board = _history(tree, view, node.node_id)
            assert not node.terminal.ends_game and not node.after_terminal
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
                assert score.search_id == view.basis(node.parent)
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
    if not view.effective_expansion(node.node_id, policy=True).comparison:
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
