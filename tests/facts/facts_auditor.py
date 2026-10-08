"""Test-only auditor (design F0 §9.4): recompute every F1 fact naively and compare.

It never runs on the runtime path and shares no code with `calliope.facts` beyond reading its
records. Two python-chess boards travel with every audited node:

* `full` — the true game from a clock-0 start, carrying the whole move stack: ground truth;
* `known` — the root's start FEN plus the moves the engine was given: what can be proven.

Where the engine says `history_complete`, history-dependent facts must equal the truth exactly;
elsewhere they must be sound (a `true`/`false` is never contradicted by the truth). Piece
identity is checked against an independently written tracker.
"""

from __future__ import annotations

from dataclasses import dataclass

import chess

from calliope.facts import FactTree, NodeId, TerminalKind
from calliope.facts.families import Capture, CastlingSide, Promotion, RookTransfer
from calliope.facts.values import AtLeast, HistoryUnknown

TYPE = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}
POINTS = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


class NaiveIdentity:
    """square -> id, advanced from python-chess move metadata only."""

    def __init__(self, ids: dict[str, str]) -> None:
        self.ids = dict(ids)

    @classmethod
    def at_root(cls, board: chess.Board) -> NaiveIdentity:
        return cls(
            {
                chess.square_name(
                    sq
                ): f"{'w' if p.color else 'b'}.{p.symbol().upper()}.{chess.square_name(sq)}"
                for sq, p in board.piece_map().items()
            }
        )

    def push(self, board: chess.Board, move: chess.Move) -> str | None:
        frm, to = chess.square_name(move.from_square), chess.square_name(move.to_square)
        captured = None
        if board.is_en_passant(move):
            victim = chess.square(
                chess.square_file(move.to_square), chess.square_rank(move.from_square)
            )
            captured = self.ids.pop(chess.square_name(victim))
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


@dataclass
class Cursor:
    """The auditor's state at the first node of a line."""

    full: chess.Board
    known: chess.Board
    tracker: NaiveIdentity
    ended_known: bool  # proven from known history: the game ended at an earlier position
    ended_full: bool  # truth: the game ended at an earlier position


def ended_before(board: chess.Board, start_clock_over_150: bool) -> bool:
    """Replay `board`'s stack once: did any position before the current one end the game?"""

    replay = board.root()
    ended = start_clock_over_150
    for move in board.move_stack:
        ended = ended or replay.is_game_over(claim_draw=False)
        replay.push(move)
    return ended


def root_cursor(full: chess.Board, known: chess.Board) -> Cursor:
    return Cursor(
        full=full.copy(),
        known=known.copy(),
        tracker=NaiveIdentity.at_root(full),
        ended_known=ended_before(known, known.root().halfmove_clock > 150),
        ended_full=ended_before(full, False),
    )


def tri_sound(ours: object, truth: bool) -> bool:
    return isinstance(ours, HistoryUnknown) or ours is truth


def advance(cursor: Cursor, moves: list[chess.Move]) -> Cursor:
    """The cursor after `moves` (used to start a branch from a node of an audited line)."""

    full, known = cursor.full.copy(), cursor.known.copy()
    tracker = NaiveIdentity(cursor.tracker.ids)
    ended_known, ended_full = cursor.ended_known, cursor.ended_full
    for move in moves:
        ended_known = ended_known or known.is_game_over(claim_draw=False)
        ended_full = ended_full or full.is_game_over(claim_draw=False)
        tracker.push(full, move)
        full.push(move)
        known.push(move)
    return Cursor(full, known, tracker, ended_known, ended_full)


def audit_line(tree: FactTree, nodes: tuple[NodeId, ...], cursor: Cursor) -> int:
    """Audit the nodes of a committed line from `cursor` (the state at `nodes[0]`)."""

    view = tree.view()
    full, known = cursor.full.copy(), cursor.known.copy()
    tracker = NaiveIdentity(cursor.tracker.ids)
    ended_known, ended_full = cursor.ended_known, cursor.ended_full
    for index, node_id in enumerate(nodes):
        node = view.node(node_id)
        if index:
            move = chess.Move.from_uci(node.incoming_move)
            _audit_move(view.fact("move", node_id), full, move, tracker)
            ended_known = ended_known or known.is_game_over(claim_draw=False)
            ended_full = ended_full or full.is_game_over(claim_draw=False)
            full.push(move)
            known.push(move)
        assert node.after_terminal is ended_known
        assert not node.after_terminal or ended_full
        assert {sq: pid.value for sq, pid in node.pieces} == tracker.ids
        _audit_node(view, node, full, known)
    return len(nodes)


def _audit_move(facts, board: chess.Board, move: chess.Move, tracker: NaiveIdentity) -> None:
    piece = board.piece_at(move.from_square)
    assert facts.uci == move.uci() and facts.san == board.san(move)
    assert facts.mover.value == ("white" if board.turn else "black")
    assert facts.piece.value == tracker.ids[chess.square_name(move.from_square)]
    assert facts.piece_type.value == TYPE[piece.piece_type]
    assert (facts.from_square, facts.to_square) == (
        chess.square_name(move.from_square),
        chess.square_name(move.to_square),
    )
    assert facts.gives_check == board.gives_check(move)
    after = board.copy(stack=False)
    after.push(move)
    assert facts.gives_mate == after.is_checkmate()
    expected_side = None
    if board.is_kingside_castling(move):
        expected_side = CastlingSide.KINGSIDE
    elif board.is_queenside_castling(move):
        expected_side = CastlingSide.QUEENSIDE
    assert facts.castling is expected_side

    expected: list[object] = []
    ep = board.is_en_passant(move)
    mover = facts.piece.value
    captured = tracker.push(board, move)
    if captured is not None:
        rank = chess.square_rank(move.from_square if ep else move.to_square)
        victim_sq = chess.square(chess.square_file(move.to_square), rank)
        victim = board.piece_at(victim_sq)
        expected.append(
            ("capture", captured, TYPE[victim.piece_type], chess.square_name(victim_sq), ep)
        )
    if move.promotion is not None:
        expected.append(("promotion", mover, TYPE[move.promotion]))
    if expected_side is not None:
        file = 5 if expected_side is CastlingSide.KINGSIDE else 3
        rook_to = chess.square(file, chess.square_rank(move.from_square))
        expected.append(("rook", tracker.ids[chess.square_name(rook_to)]))
    actual: list[object] = []
    for event in facts.events:
        if isinstance(event, Capture):
            actual.append(
                (
                    "capture",
                    event.piece.value,
                    event.piece_type.value,
                    event.square,
                    event.en_passant,
                )
            )
        elif isinstance(event, Promotion):
            actual.append(("promotion", event.piece.value, event.to.value))
        else:
            assert isinstance(event, RookTransfer)
            actual.append(("rook", event.piece.value))
    assert actual == expected


def _audit_node(view, node, full: chess.Board, known: chess.Board) -> None:
    assert node.fen == full.fen(en_passant="legal")
    assert node.side_to_move.value == ("white" if full.turn else "black")
    assert node.known_plies == len(known.move_stack)
    assert node.history_complete == (len(known.move_stack) >= full.halfmove_clock)
    _audit_status(view.fact("status", node.node_id), full)
    _audit_material(view.fact("material", node.node_id), full)
    _audit_draw(view.fact("draw", node.node_id), full, known, exact=node.history_complete)
    _audit_terminal(node, full, known)


def _audit_status(status, board: chess.Board) -> None:
    legal = sorted(board.legal_moves, key=lambda m: m.uci())
    assert [m.uci for m in status.legal_moves] == [m.uci() for m in legal]
    assert [m.san for m in status.legal_moves] == [board.san(m) for m in legal]
    assert status.legal_move_count == len(legal)
    assert status.in_check == board.is_check()
    assert list(status.checkers) == [chess.square_name(sq) for sq in sorted(board.checkers())]
    assert status.checkmate == board.is_checkmate()
    assert status.stalemate == board.is_stalemate()
    assert status.insufficient_material == board.is_insufficient_material()
    assert list(status.checking_moves) == [m.uci() for m in legal if board.gives_check(m)]
    assert list(status.promotions) == [m.uci() for m in legal if m.promotion]
    mates = []
    for move in legal:
        board.push(move)
        if board.is_checkmate():
            mates.append(move.uci())
        board.pop()
    assert list(status.mating_moves) == mates
    expected = []
    for move in legal:
        if not board.is_capture(move):
            continue
        ep = board.is_en_passant(move)
        rank = chess.square_rank(move.from_square if ep else move.to_square)
        victim = chess.square(chess.square_file(move.to_square), rank)
        expected.append(
            (
                move.uci(),
                chess.square_name(move.from_square),
                TYPE[board.piece_type_at(move.from_square)],
                chess.square_name(victim),
                TYPE[board.piece_type_at(victim)],
                chess.square_name(move.to_square),
                ep,
                None if move.promotion is None else TYPE[move.promotion],
            )
        )
    actual = [
        (
            c.uci,
            c.capturer_square,
            c.capturer_type.value,
            c.victim_square,
            c.victim_type.value,
            c.landing_square,
            c.en_passant,
            None if c.promotion is None else c.promotion.value,
        )
        for c in status.legal_captures
    ]
    assert actual == expected


def _audit_material(material, board: chess.Board) -> None:
    pieces = board.piece_map()
    for color, counts in ((chess.WHITE, material.white), (chess.BLACK, material.black)):
        own = [(sq, p) for sq, p in pieces.items() if p.color == color]
        for kind, field in (
            (chess.PAWN, "pawns"),
            (chess.KNIGHT, "knights"),
            (chess.BISHOP, "bishops"),
            (chess.ROOK, "rooks"),
            (chess.QUEEN, "queens"),
        ):
            assert getattr(counts, field) == sum(p.piece_type == kind for _, p in own)
        bishops = [sq for sq, p in own if p.piece_type == chess.BISHOP]
        light = sum((chess.square_file(sq) + chess.square_rank(sq)) % 2 == 1 for sq in bishops)
        assert (counts.light_square_bishops, counts.dark_square_bishops) == (
            light,
            len(bishops) - light,
        )
    assert material.points.value == tuple(
        sum(POINTS.get(p.piece_type, 0) for p in pieces.values() if p.color == color)
        for color in (chess.WHITE, chess.BLACK)
    )


def _claimable_truth(board: chess.Board) -> bool:
    for move in list(board.legal_moves):
        board.push(move)
        reached = board.is_repetition(3)
        board.pop()
        if reached:
            return True
    return False


def _audit_draw(draw, full: chess.Board, known: chess.Board, *, exact: bool) -> None:
    truth = max(k for k in range(1, 12) if full.is_repetition(k))
    proven = max(k for k in range(1, 12) if known.is_repetition(k))
    claimable = _claimable_truth(full)
    if exact:
        assert draw.occurrences == truth
        assert draw.threefold_reached is full.is_repetition(3)
        assert draw.fivefold_reached is full.is_fivefold_repetition()
        assert draw.threefold_claimable_by_move is claimable
    else:
        assert draw.occurrences == AtLeast(proven) and proven <= truth
        assert tri_sound(draw.threefold_reached, full.is_repetition(3))
        assert tri_sound(draw.fivefold_reached, full.is_fivefold_repetition())
        assert tri_sound(draw.threefold_claimable_by_move, claimable)
        # what the known stack proves must be reported as proven
        assert draw.threefold_reached is True or not known.is_repetition(3)
        assert draw.fivefold_reached is True or not known.is_fivefold_repetition()
        assert draw.threefold_claimable_by_move is True or not _claimable_truth(known)
    assert draw.halfmove_clock == full.halfmove_clock
    assert draw.fullmove_number == full.fullmove_number
    assert draw.fifty_move_reached == (full.halfmove_clock >= 100)
    # python-chess requires a legal move for the 75-move rule; the design (§6.9) only excludes
    # checkmate, so the two differ exactly at a stalemate with clock >= 150.
    assert draw.seventy_five_move_reached == (
        full.is_seventyfive_moves() or (full.halfmove_clock >= 150 and full.is_stalemate())
    )


def _audit_terminal(node, full: chess.Board, known: chess.Board) -> None:
    kind, rule = node.terminal.kind, node.terminal.rule
    if full.is_checkmate():
        assert kind is TerminalKind.CHECKMATE
        return
    if full.is_stalemate():
        assert kind is TerminalKind.STALEMATE
        return
    proven = (
        known.is_insufficient_material()
        or known.halfmove_clock >= 150
        or known.is_fivefold_repetition()
    )
    truth = (
        full.is_insufficient_material()
        or full.is_seventyfive_moves()
        or full.is_fivefold_repetition()
    )
    if proven:
        assert kind is TerminalKind.AUTOMATIC_DRAW and rule is not None
    else:
        assert kind is not TerminalKind.AUTOMATIC_DRAW, "automatic draw reported without proof"
    if node.history_complete:
        assert (kind is TerminalKind.AUTOMATIC_DRAW) == truth
        assert kind is not TerminalKind.UNPROVEN
    if kind is TerminalKind.NONE:
        assert not truth
