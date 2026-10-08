"""Test-only auditor (design F0 §9.4): recompute every F1 fact naively and compare.

It never runs on the runtime path. Oracles are python-chess queries on a board that carries the
full move stack (so python-chess's own repetition logic sees the whole history), plus an
independent piece-identity tracker written differently from `calliope.facts.identity`.
"""

from __future__ import annotations

import chess

from calliope.facts import FactTree, NodeId, TerminalKind
from calliope.facts.families import Capture, Promotion, RookTransfer
from calliope.facts.values import AtLeast, HistoryUnknown


class NaiveIdentity:
    """square -> id, advanced from python-chess move metadata only."""

    def __init__(self, board: chess.Board) -> None:
        self.ids = {
            chess.square_name(
                sq
            ): f"{'w' if p.color else 'b'}.{p.symbol().upper()}.{chess.square_name(sq)}"
            for sq, p in board.piece_map().items()
        }

    def push(self, board: chess.Board, move: chess.Move) -> str | None:
        frm, to = chess.square_name(move.from_square), chess.square_name(move.to_square)
        captured = None
        if board.is_en_passant(move):
            victim = chess.square_name(
                chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
            )
            captured = self.ids.pop(victim)
        elif to in self.ids:
            captured = self.ids.pop(to)
        if board.is_castling(move):
            rank = chess.square_rank(move.from_square)
            kingside = chess.square_file(move.to_square) == 6
            rook_from = chess.square_name(chess.square(7 if kingside else 0, rank))
            rook_to = chess.square_name(chess.square(5 if kingside else 3, rank))
            self.ids[rook_to] = self.ids.pop(rook_from)
        self.ids[to] = self.ids.pop(frm)
        return captured


def tri_consistent(ours: object, truth: bool) -> bool:
    """A tri-state answer is sound if it equals the truth or admits not knowing it."""

    return isinstance(ours, HistoryUnknown) or ours is truth


def audit_line(
    tree: FactTree, nodes: tuple[NodeId, ...], oracle: chess.Board, *, complete: bool
) -> int:
    """Audit every node of a committed line. `oracle` is the full-stack board at `nodes[0]`.

    With `complete`, the oracle's stack covers the whole history, so draw facts must be exact;
    otherwise they must only be sound (true/false never contradicted by the full history).
    Returns the number of audited nodes.
    """

    view = tree.view()
    tracker = NaiveIdentity(oracle) if view.node(nodes[0]).parent is None else None
    board = oracle.copy()
    for index, node_id in enumerate(nodes):
        node = view.node(node_id)
        if index:
            move = chess.Move.from_uci(node.incoming_move)
            facts = view.fact("move", node_id)
            assert facts.uci == move.uci() and facts.san == board.san(move)
            assert facts.gives_check == board.gives_check(move)
            captures = [e for e in facts.events if isinstance(e, Capture)]
            assert bool(captures) == board.is_capture(move)
            assert any(isinstance(e, Promotion) for e in facts.events) == (
                move.promotion is not None
            )
            assert any(isinstance(e, RookTransfer) for e in facts.events) == board.is_castling(move)
            if captures and move.promotion is not None:
                assert isinstance(facts.events[0], Capture) and isinstance(
                    facts.events[1], Promotion
                )
            if tracker is not None:
                captured = tracker.push(board, move)
                assert (captures[0].piece.value if captures else None) == captured
            board.push(move)
        _audit_node(view, node_id, board, complete=complete)
        if tracker is not None:
            assert {sq: pid.value for sq, pid in node.pieces} == tracker.ids
        _audit_pieces_match_board(node, board)
    return len(nodes)


def _audit_pieces_match_board(node, board: chess.Board) -> None:
    on_board = {chess.square_name(sq): p for sq, p in board.piece_map().items()}
    assert set(on_board) == {sq for sq, _ in node.pieces}
    for square, pid in node.pieces:
        color, letter, _root = pid.value.split(".")
        piece = on_board[square]
        assert (color == "w") == piece.color
        assert letter == piece.symbol().upper() or (
            letter == "P" and piece.piece_type != chess.KING
        )


def _audit_node(view, node_id: NodeId, board: chess.Board, *, complete: bool) -> None:
    node = view.node(node_id)
    assert node.fen == board.fen(en_passant="legal")
    assert node.side_to_move.value == ("white" if board.turn else "black")
    status = view.fact("status", node_id)
    legal = sorted(board.legal_moves, key=lambda m: m.uci())
    assert [m.uci for m in status.legal_moves] == [m.uci() for m in legal]
    assert [m.san for m in status.legal_moves] == [board.san(m) for m in legal]
    assert status.in_check == board.is_check()
    assert status.checkmate == board.is_checkmate()
    assert status.stalemate == board.is_stalemate()
    assert status.insufficient_material == board.is_insufficient_material()
    assert [c.uci for c in status.legal_captures] == [m.uci() for m in legal if board.is_capture(m)]
    mates = []
    for m in legal:
        board.push(m)
        if board.is_checkmate():
            mates.append(m.uci())
        board.pop()
    assert list(status.mating_moves) == mates

    material = view.fact("material", node_id)
    points = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
    for color, counts in ((chess.WHITE, material.white), (chess.BLACK, material.black)):
        pieces = [p for p in board.piece_map().values() if p.color == color]
        for kind, field in (
            (chess.PAWN, "pawns"),
            (chess.KNIGHT, "knights"),
            (chess.BISHOP, "bishops"),
            (chess.ROOK, "rooks"),
            (chess.QUEEN, "queens"),
        ):
            assert getattr(counts, field) == sum(p.piece_type == kind for p in pieces)
        light = [
            sq
            for sq, p in board.piece_map().items()
            if p.color == color
            and p.piece_type == chess.BISHOP
            and (chess.square_file(sq) + chess.square_rank(sq)) % 2
        ]
        assert counts.light_square_bishops == len(light)
    assert material.points.value == tuple(
        sum(points.get(p.piece_type, 0) for p in board.piece_map().values() if p.color == color)
        for color in (chess.WHITE, chess.BLACK)
    )

    draw = view.fact("draw", node_id)
    truth = max(k for k in range(1, 12) if board.is_repetition(k))
    if complete:
        assert node.history_complete
        assert draw.occurrences == truth
        assert draw.threefold_reached is board.is_repetition(3)
        assert draw.fivefold_reached is board.is_fivefold_repetition()
        claim = board.can_claim_threefold_repetition()
        assert claim == (draw.threefold_reached or draw.threefold_claimable_by_move is True)
        assert draw.threefold_claimable_by_move is not True or claim
    else:
        occurrences = draw.occurrences
        seen = occurrences.n if isinstance(occurrences, AtLeast) else occurrences
        assert seen <= truth and (isinstance(occurrences, AtLeast) or seen == truth)
        assert tri_consistent(draw.threefold_reached, board.is_repetition(3))
        assert tri_consistent(draw.fivefold_reached, board.is_fivefold_repetition())
    assert draw.fifty_move_reached == (board.halfmove_clock >= 100)
    assert draw.seventy_five_move_reached == (
        board.halfmove_clock >= 150 and not board.is_checkmate()
    )

    kind = node.terminal.kind
    if board.is_checkmate():
        assert kind is TerminalKind.CHECKMATE
    elif board.is_stalemate():
        assert kind is TerminalKind.STALEMATE
    elif (
        board.is_insufficient_material()
        or board.is_seventyfive_moves()
        or board.is_fivefold_repetition()
    ):
        assert kind in (TerminalKind.AUTOMATIC_DRAW, TerminalKind.UNPROVEN)
        if complete:
            assert kind is TerminalKind.AUTOMATIC_DRAW
    else:
        assert kind in (TerminalKind.NONE, TerminalKind.UNPROVEN)
        if complete:
            assert kind is TerminalKind.NONE
