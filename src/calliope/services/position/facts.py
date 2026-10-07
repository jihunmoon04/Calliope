"""Derive PositionFacts from an exact PositionObservation.

Pure policy: no board access and no evaluation.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from calliope.application.ports.position import PositionObservationPort
from calliope.domain.chess import (
    Color,
    LegalCapture,
    MaterialCount,
    MaterialState,
    PieceRef,
    PieceState,
    PieceType,
    PositionFacts,
    PositionSnapshot,
    square_index,
)
from calliope.errors import IncompatiblePositionObservationError


def _by_square(piece: PieceRef) -> int:
    return square_index(piece.square)


@dataclass(slots=True)
class PositionFactExtractor:
    observations: PositionObservationPort

    def extract(self, position: PositionSnapshot) -> PositionFacts:
        observation = self.observations.observe_position(position)
        if observation.position_id != position.position_id:
            raise IncompatiblePositionObservationError(
                "observation position_id does not match the requested position"
            )

        pieces = tuple(sorted(observation.pieces, key=_by_square))
        attacks = tuple(
            sorted(
                observation.attacks,
                key=lambda a: (square_index(a.attacker.square), square_index(a.target_square)),
            )
        )
        captures = tuple(sorted(observation.legal_captures, key=lambda c: c.move.uci))

        attacks_from: dict[str, list[str]] = defaultdict(list)
        attackers_of: dict[str, list[PieceRef]] = defaultdict(list)
        for relation in attacks:
            attacks_from[relation.attacker.square].append(relation.target_square)
            attackers_of[relation.target_square].append(relation.attacker)

        captures_of: dict[PieceRef, list[LegalCapture]] = defaultdict(list)
        for capture in captures:
            captures_of[capture.captured].append(capture)

        states = tuple(
            self._piece_state(piece, attacks_from, attackers_of, captures_of)
            for piece in pieces
        )
        return PositionFacts(
            position_id=position.position_id,
            pieces=states,
            material=self._material(pieces),
            attacks=attacks,
            legal_captures=captures,
            side_to_move_in_check=observation.side_to_move_in_check,
            side_to_move_checkmated=observation.side_to_move_checkmated,
        )

    @staticmethod
    def _piece_state(
        piece: PieceRef,
        attacks_from: dict[str, list[str]],
        attackers_of: dict[str, list[PieceRef]],
        captures_of: dict[PieceRef, list[LegalCapture]],
    ) -> PieceState:
        attackers = attackers_of.get(piece.square, [])
        attacked_by = tuple(a for a in attackers if a.color is not piece.color)
        defended_by = tuple(a for a in attackers if a.color is piece.color and a != piece)
        captures = captures_of.get(piece, [])
        hanging = (
            piece.piece_type is not PieceType.KING
            and bool(captures)
            and all(not c.is_en_passant for c in captures)
            and not defended_by
        )
        return PieceState(
            piece=piece,
            attacks=tuple(attacks_from.get(piece.square, [])),
            attacked_by=attacked_by,
            defended_by=defended_by,
            legally_capturable_now=bool(captures),
            hanging_now=hanging,
        )

    @staticmethod
    def _material(pieces: tuple[PieceRef, ...]) -> MaterialState:
        def count(color: Color) -> MaterialCount:
            def n(kind: PieceType) -> int:
                return sum(1 for p in pieces if p.color is color and p.piece_type is kind)

            return MaterialCount(
                pawns=n(PieceType.PAWN),
                knights=n(PieceType.KNIGHT),
                bishops=n(PieceType.BISHOP),
                rooks=n(PieceType.ROOK),
                queens=n(PieceType.QUEEN),
            )

        return MaterialState(white=count(Color.WHITE), black=count(Color.BLACK))
