"""Structural extension of P4/P5; no engine calls and no value judgements."""

from __future__ import annotations

from dataclasses import dataclass

from calliope.application.ports.chess import ChessRulesPort
from calliope.domain.analysis.positional import (
    FileStructure,
    FileStructureChange,
    PawnStructure,
    PawnStructureChange,
    PositionalFeatures,
    PositionAnalysis,
    TransitionAnalysis,
)
from calliope.domain.chess import ChessMove, Color, PieceType, PositionFacts, PositionSnapshot
from calliope.errors import IncompatibleBoardDeltaError, IncompatiblePositionObservationError
from calliope.services.position.delta import BoardDeltaAnalyzer
from calliope.services.position.facts import PositionFactExtractor


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
