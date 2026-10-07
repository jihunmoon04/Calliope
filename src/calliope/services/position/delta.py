"""Compute the exact board change caused by one legal move.

Pure policy over PositionFacts: moves are interpreted from UCI and the facts, never from a
rules library.  Every before/after piece must be accounted for or the analysis fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass

from calliope.application.ports.chess import ChessRulesPort
from calliope.domain.analysis import (
    AttackChange,
    BoardDelta,
    CaptureDelta,
    CheckChange,
    CheckChangeKind,
    DefenseChange,
    MaterialChange,
    PieceCorrespondence,
    PieceTransition,
    PieceTransitionKind,
    RelationChangeKind,
)
from calliope.domain.chess import (
    ChessMove,
    Color,
    PieceRef,
    PieceType,
    PositionFacts,
    PositionSnapshot,
    square_index,
)
from calliope.errors import IncompatibleBoardDeltaError
from calliope.services.position.facts import PositionFactExtractor

_PROMOTIONS = {
    "q": PieceType.QUEEN,
    "r": PieceType.ROOK,
    "b": PieceType.BISHOP,
    "n": PieceType.KNIGHT,
}
# king uci -> (rook from, rook to)
_CASTLING = {
    "e1g1": ("h1", "f1"),
    "e1c1": ("a1", "d1"),
    "e8g8": ("h8", "f8"),
    "e8c8": ("a8", "d8"),
}
_MATERIAL_TYPES = (
    PieceType.PAWN,
    PieceType.KNIGHT,
    PieceType.BISHOP,
    PieceType.ROOK,
    PieceType.QUEEN,
)
_COUNT_FIELD = {
    PieceType.PAWN: "pawns",
    PieceType.KNIGHT: "knights",
    PieceType.BISHOP: "bishops",
    PieceType.ROOK: "rooks",
    PieceType.QUEEN: "queens",
}


def _fail(message: str) -> IncompatibleBoardDeltaError:
    return IncompatibleBoardDeltaError(message)


def _sq(piece: PieceRef) -> int:
    return square_index(piece.square)


@dataclass(slots=True)
class BoardDeltaAnalyzer:
    chess: ChessRulesPort
    facts: PositionFactExtractor

    def analyze(self, before: PositionSnapshot, move: ChessMove) -> BoardDelta:
        before_facts = self.facts.extract(before)
        after = self.chess.apply_move(before, move)
        after_facts = self.facts.extract(after)

        mover = before.side_to_move
        if after.side_to_move is not mover.opposite:
            raise _fail("after position must have the opponent to move")
        if before_facts.position_id != before.position_id:
            raise _fail("before facts are bound to a different position")
        if after_facts.position_id != after.position_id:
            raise _fail("after facts are bound to a different position")

        before_map = {s.piece.square: s.piece for s in before_facts.pieces}
        after_map = {s.piece.square: s.piece for s in after_facts.pieces}
        if len(before_map) != len(before_facts.pieces) or len(after_map) != len(after_facts.pieces):
            raise _fail("duplicate piece on a square")

        from_sq, to_sq, promotion = _parse_uci(move.uci)

        transitions: list[PieceTransition] = []
        pairs: list[PieceCorrespondence] = []
        explained_before: set[str] = set()
        explained_after: set[str] = set()

        def link(kind: PieceTransitionKind | None, b: PieceRef, a: PieceRef) -> None:
            if b.square in explained_before:
                raise _fail(f"before piece on {b.square} explained twice")
            if a.square in explained_after:
                raise _fail(f"after piece on {a.square} explained twice")
            explained_before.add(b.square)
            explained_after.add(a.square)
            pairs.append(PieceCorrespondence(b, a))
            if kind is not None:
                transitions.append(PieceTransition(kind, b, a))

        # primary moved piece
        moved_before = before_map.get(from_sq)
        moved_after = after_map.get(to_sq)
        if moved_before is None or moved_after is None:
            raise _fail("moved piece missing before or after the move")
        if moved_before.color is not mover or moved_after.color is not mover:
            raise _fail("moved piece does not belong to the mover")
        if promotion is not None:
            if moved_before.piece_type is not PieceType.PAWN:
                raise _fail("promotion by a non-pawn")
            if moved_after.piece_type is not promotion:
                raise _fail("promoted piece type does not match the move")
            link(PieceTransitionKind.PROMOTION, moved_before, moved_after)
        else:
            if moved_after.piece_type is not moved_before.piece_type:
                raise _fail("moved piece changed type without promotion")
            link(PieceTransitionKind.MOVE, moved_before, moved_after)

        # capture
        matches = [c for c in before_facts.legal_captures if c.move.uci == move.uci]
        if len(matches) > 1:
            raise _fail("multiple legal captures match the played move")
        capture: CaptureDelta | None = None
        if matches:
            c = matches[0]
            if c.capturer != moved_before:
                raise _fail("capturer does not match the moved piece")
            if before_map.get(c.captured_square) != c.captured:
                raise _fail("captured piece is not on its captured square")
            explained_before.add(c.captured_square)
            capture = CaptureDelta(
                capturer_before=c.capturer,
                capturer_after=moved_after,
                captured=c.captured,
                captured_square=c.captured_square,
                landing_square=c.landing_square,
                is_en_passant=c.is_en_passant,
            )

        # castling rook
        if moved_before.piece_type is PieceType.KING and move.uci in _CASTLING:
            rook_from, rook_to = _CASTLING[move.uci]
            rook_before = before_map.get(rook_from)
            rook_after = after_map.get(rook_to)
            if (
                rook_before is None
                or rook_after is None
                or rook_before.piece_type is not PieceType.ROOK
                or rook_after.piece_type is not PieceType.ROOK
                or rook_before.color is not mover
                or rook_after.color is not mover
            ):
                raise _fail("castling rook is missing or inconsistent")
            link(PieceTransitionKind.CASTLING_ROOK, rook_before, rook_after)

        # stationary pieces
        for square, piece in before_map.items():
            if square in explained_before:
                continue
            if after_map.get(square) != piece:
                raise _fail(f"piece on {square} disappeared or changed unexplained")
            link(None, piece, piece)

        if set(after_map) != explained_after:
            extra = sorted(set(after_map) - explained_after)
            raise _fail(f"unexplained piece(s) appeared on {extra}")

        pairs.sort(key=lambda p: _sq(p.before))
        transitions.sort(key=lambda t: _sq(t.before))

        to_before = {p.after: p.before for p in pairs}

        new_attacks, removed_attacks = _attack_changes(before_facts, after_facts, to_before)
        new_defenses, removed_defenses = _defense_changes(before_facts, after_facts, to_before)

        return BoardDelta(
            before_position_id=before.position_id,
            after_position_id=after.position_id,
            move=move,
            mover=mover,
            piece_correspondence=tuple(pairs),
            transitions=tuple(transitions),
            capture=capture,
            material_changes=_material_changes(before_facts, after_facts),
            new_attacks=new_attacks,
            removed_attacks=removed_attacks,
            new_defenses=new_defenses,
            removed_defenses=removed_defenses,
            check_changes=_check_changes(before_facts, after_facts, mover),
        )


def _parse_uci(uci: str) -> tuple[str, str, PieceType | None]:
    if len(uci) not in (4, 5):
        raise _fail(f"unsupported UCI move: {uci!r}")
    from_sq, to_sq, suffix = uci[:2], uci[2:4], uci[4:]
    try:
        square_index(from_sq)
        square_index(to_sq)
    except ValueError:
        raise _fail(f"unsupported UCI move: {uci!r}") from None
    if not suffix:
        return from_sq, to_sq, None
    if suffix not in _PROMOTIONS:
        raise _fail(f"unsupported promotion piece in {uci!r}")
    return from_sq, to_sq, _PROMOTIONS[suffix]


def _material_changes(before: PositionFacts, after: PositionFacts) -> tuple[MaterialChange, ...]:
    changes = []
    for color in (Color.WHITE, Color.BLACK):
        b = getattr(before.material, color.value)
        a = getattr(after.material, color.value)
        for piece_type in _MATERIAL_TYPES:
            name = _COUNT_FIELD[piece_type]
            delta = getattr(a, name) - getattr(b, name)
            if delta:
                changes.append(MaterialChange(color, piece_type, delta))
    return tuple(changes)


def _attack_changes(
    before: PositionFacts,
    after: PositionFacts,
    to_before: dict[PieceRef, PieceRef],
) -> tuple[tuple[AttackChange, ...], tuple[AttackChange, ...]]:
    # logical key: (identity of attacker as its before-piece, target square)
    before_rel = {(r.attacker, r.target_square): r for r in before.attacks}
    after_rel = {(to_before[r.attacker], r.target_square): r for r in after.attacks}

    added = [
        AttackChange(RelationChangeKind.ADDED, r.attacker, r.target_square)
        for key, r in after_rel.items()
        if key not in before_rel
    ]
    removed = [
        AttackChange(RelationChangeKind.REMOVED, r.attacker, r.target_square)
        for key, r in before_rel.items()
        if key not in after_rel
    ]
    added.sort(key=lambda c: (_sq(c.attacker), square_index(c.target_square)))
    removed.sort(key=lambda c: (_sq(c.attacker), square_index(c.target_square)))
    return tuple(added), tuple(removed)


def _defense_changes(
    before: PositionFacts,
    after: PositionFacts,
    to_before: dict[PieceRef, PieceRef],
) -> tuple[tuple[DefenseChange, ...], tuple[DefenseChange, ...]]:
    before_rel = {(d, s.piece): (d, s.piece) for s in before.pieces for d in s.defended_by}
    after_rel = {
        (to_before[d], to_before[s.piece]): (d, s.piece)
        for s in after.pieces
        for d in s.defended_by
    }

    added = [
        DefenseChange(RelationChangeKind.ADDED, d, p)
        for key, (d, p) in after_rel.items()
        if key not in before_rel
    ]
    removed = [
        DefenseChange(RelationChangeKind.REMOVED, d, p)
        for key, (d, p) in before_rel.items()
        if key not in after_rel
    ]
    added.sort(key=lambda c: (_sq(c.defender), _sq(c.defended)))
    removed.sort(key=lambda c: (_sq(c.defender), _sq(c.defended)))
    return tuple(added), tuple(removed)


def _check_changes(
    before: PositionFacts, after: PositionFacts, mover: Color
) -> tuple[CheckChange, ...]:
    changes = []
    # before facts describe the mover; after facts describe the opponent
    if before.side_to_move_in_check:
        changes.append(CheckChange(CheckChangeKind.REMOVED, mover))
    if after.side_to_move_in_check:
        changes.append(CheckChange(CheckChangeKind.CREATED, mover.opposite))
    changes.sort(key=lambda c: (c.checked_color is Color.BLACK, c.kind.value))
    return tuple(changes)
