"""Structural extension of P4/P5; no engine calls and no value judgements."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from calliope.application.ports.chess import ChessRulesPort
from calliope.domain.analysis import (
    BoardDelta,
    MaterialChange,
    PieceTransition,
    PieceTransitionKind,
)
from calliope.domain.analysis.positional import (
    FileStructure,
    FileStructureChange,
    PawnStructure,
    PawnStructureChange,
    PositionalFeatures,
    PositionAnalysis,
    TransitionAnalysis,
)
from calliope.domain.chess import (
    ChessMove,
    Color,
    PieceType,
    PositionFacts,
    PositionSnapshot,
    square_index,
)
from calliope.errors import (
    IncompatibleBadMoveContextError,
    IncompatibleBoardDeltaError,
    IncompatiblePositionObservationError,
)
from calliope.services.explanation.piece_identity import BasePieceIdentityMap
from calliope.services.position.delta import BoardDeltaAnalyzer
from calliope.services.position.facts import PositionFactExtractor


def _material_delta(before: PositionFacts, after: PositionFacts) -> tuple[MaterialChange, ...]:
    """Independent count reconciliation against pieces, including promotions."""
    b = Counter((s.piece.color, s.piece.piece_type) for s in before.pieces)
    a = Counter((s.piece.color, s.piece.piece_type) for s in after.pieces)
    return tuple(
        MaterialChange(color, kind, a[color, kind] - b[color, kind])
        for color in (Color.WHITE, Color.BLACK)
        for kind in (
            PieceType.PAWN,
            PieceType.KNIGHT,
            PieceType.BISHOP,
            PieceType.ROOK,
            PieceType.QUEEN,
        )
        if a[color, kind] != b[color, kind]
    )


def _reconcile_delta(before: PositionFacts, after: PositionFacts, delta: BoardDelta) -> None:
    # P5 is the producer, but standalone transition analysis must also reject a
    # same-id delta that disagrees with its independently observed board states.
    try:
        identity = BasePieceIdentityMap.from_facts(before).advance(delta)
    except IncompatibleBadMoveContextError as exc:
        raise IncompatibleBoardDeltaError(str(exc)) from exc
    if set(identity.live_pieces) != {s.piece for s in after.pieces}:
        raise IncompatibleBoardDeltaError("delta pieces do not reconcile with after facts")
    if delta.material_changes != _material_delta(before, after):
        raise IncompatibleBoardDeltaError("delta material changes disagree with piece counts")
    _check_move_correspondence(before, after, delta)


def _check_move_correspondence(
    before: PositionFacts, after: PositionFacts, delta: BoardDelta
) -> None:
    """Check supplied P5 identities against an already validated standard-chess move.

    This does not produce a second delta or discover legality. Only the mover and,
    during castling, its rook may change squares; all other surviving pieces stay put.
    """
    before_pieces = {s.piece.square: s.piece for s in before.pieces}
    after_pieces = {s.piece.square: s.piece for s in after.pieces}
    uci = delta.move.uci
    source, target = uci[:2], uci[2:4]
    mover_before = before_pieces.get(source)
    mover_after = after_pieces.get(target)
    if mover_before is None or mover_after is None:
        raise IncompatibleBoardDeltaError("move endpoints have no corresponding pieces")
    moved = {mover_before: mover_after}
    expected = [
        PieceTransition(
            PieceTransitionKind.PROMOTION if len(uci) == 5 else PieceTransitionKind.MOVE,
            mover_before,
            mover_after,
        )
    ]
    castling_rooks = {
        "e1g1": ("h1", "f1"),
        "e1c1": ("a1", "d1"),
        "e8g8": ("h8", "f8"),
        "e8c8": ("a8", "d8"),
    }
    if mover_before.piece_type is PieceType.KING and uci in castling_rooks:
        rook_source, rook_target = castling_rooks[uci]
        rook_before = before_pieces.get(rook_source)
        rook_after = after_pieces.get(rook_target)
        if (
            rook_before is None
            or rook_after is None
            or rook_before.piece_type is not PieceType.ROOK
            or rook_after.piece_type is not PieceType.ROOK
            or rook_before.color is not mover_before.color
            or rook_after.color is not mover_before.color
        ):
            raise IncompatibleBoardDeltaError("castling rook endpoints are inconsistent")
        moved[rook_before] = rook_after
        expected.append(PieceTransition(PieceTransitionKind.CASTLING_ROOK, rook_before, rook_after))
    for pair in delta.piece_correspondence:
        if pair.after != moved.get(pair.before, pair.before):
            raise IncompatibleBoardDeltaError("piece correspondence disagrees with the played move")
    expected.sort(key=lambda t: square_index(t.before.square))
    if delta.transitions != tuple(expected):
        raise IncompatibleBoardDeltaError("piece transitions disagree with the played move")


def extract_positional_features(facts: PositionFacts) -> PositionalFeatures:
    """Definitions depend only on P4 pieces and geometric pawn support.

    Isolated: no friendly pawn anywhere on either adjacent file.
    Doubled: at least two friendly pawns on this file (each is marked).
    Passed: no enemy pawn ahead on this or adjacent files; says nothing about safety.
    Support: friendly pawn geometrically attacks this pawn, even when pinned.
    """
    pawns = tuple(s for s in facts.pieces if s.piece.piece_type is PieceType.PAWN)
    squares = [s.piece.square for s in facts.pieces]
    if len(squares) != len(set(squares)):
        raise IncompatiblePositionObservationError("facts contain duplicate piece squares")
    features = []
    for state in pawns:
        pawn = state.piece
        file = ord(pawn.square[0]) - ord("a")
        rank = int(pawn.square[1])
        friendly = tuple(s.piece for s in pawns if s.piece.color is pawn.color)
        enemy = tuple(s.piece for s in pawns if s.piece.color is not pawn.color)
        direction = 1 if pawn.color is Color.WHITE else -1
        features.append(
            PawnStructure(
                pawn=pawn,
                isolated=not any(abs(ord(p.square[0]) - ord("a") - file) == 1 for p in friendly),
                doubled=sum(p.square[0] == pawn.square[0] for p in friendly) >= 2,
                passed=not any(
                    abs(ord(p.square[0]) - ord("a") - file) <= 1
                    and (int(p.square[1]) - rank) * direction > 0
                    for p in enemy
                ),
                pawn_supporters=tuple(
                    p
                    for p in friendly
                    if abs(ord(p.square[0]) - ord("a") - file) == 1
                    and rank - int(p.square[1]) == direction
                ),
            )
        )
    return PositionalFeatures(
        position_id=facts.position_id,
        pawns=tuple(features),
        files=tuple(
            FileStructure(
                file=file,
                white_pawns=sum(
                    s.piece.square[0] == file and s.piece.color is Color.WHITE for s in pawns
                ),
                black_pawns=sum(
                    s.piece.square[0] == file and s.piece.color is Color.BLACK for s in pawns
                ),
            )
            for file in "abcdefgh"
        ),
    )


@dataclass(slots=True)
class PositionAnalyzer:
    facts: PositionFactExtractor

    def analyze(self, position: PositionSnapshot) -> PositionAnalysis:
        facts = self.facts.extract(position)
        if facts.position_id != position.position_id:
            raise IncompatiblePositionObservationError("facts belong to a different position")
        return PositionAnalysis(position, facts, extract_positional_features(facts))


@dataclass(slots=True)
class TransitionAnalyzer:
    chess: ChessRulesPort
    positions: PositionAnalyzer
    deltas: BoardDeltaAnalyzer

    def analyze(self, before: PositionSnapshot, move: ChessMove) -> TransitionAnalysis:
        # Normalize once before P5, including whitespace and equivalent castling notation.
        canonical_move = self.chess.legal_move_from_uci(before, move.uci)
        after = self.chess.apply_move(before, canonical_move)
        before_analysis = self.positions.analyze(before)
        after_analysis = self.positions.analyze(after)
        delta = self.deltas.analyze(before, canonical_move)
        if (delta.before_position_id, delta.after_position_id) != (
            before.position_id,
            after.position_id,
        ) or delta.move.uci != canonical_move.uci:
            raise IncompatibleBoardDeltaError("delta does not match the analyzed transition")
        if delta.mover is not before.side_to_move:
            raise IncompatibleBoardDeltaError("delta mover does not match the source position")
        _reconcile_delta(before_analysis.facts, after_analysis.facts, delta)

        after_pawns = {p.pawn: p for p in after_analysis.features.pawns}
        correspondence = {p.before: p.after for p in delta.piece_correspondence}
        inverse = {p.after: p.before for p in delta.piece_correspondence}
        pawn_changes = []
        for pawn in before_analysis.features.pawns:
            successor = correspondence.get(pawn.pawn)
            new = after_pawns.get(successor)
            # Normalize supporter identities into the before-position for comparison.
            same_support = new is not None and set(pawn.pawn_supporters) == {
                inverse[p] for p in new.pawn_supporters
            }
            if (
                new is None
                or (pawn.isolated, pawn.doubled, pawn.passed)
                != (new.isolated, new.doubled, new.passed)
                or not same_support
            ):
                pawn_changes.append(PawnStructureChange(pawn, new))
        file_changes = tuple(
            FileStructureChange(b, a)
            for b, a in zip(
                before_analysis.features.files, after_analysis.features.files, strict=True
            )
            if b != a
        )
        return TransitionAnalysis(
            before_analysis, after_analysis, delta, tuple(pawn_changes), file_changes
        )
