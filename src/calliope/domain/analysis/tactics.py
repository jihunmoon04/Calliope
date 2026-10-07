"""Tactical pattern candidates.

A candidate records that observed facts match a pattern.  It is not a verified tactic, not a
cause of any evaluation change, and not an explanation claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from calliope.domain.chess import ChessMove, Color, PieceRef, PieceType


class TacticalCandidateKind(StrEnum):
    CHECK = "check"
    CHECKMATE = "checkmate"

    HANGING_PIECE = "hanging_piece"

    DIRECT_ATTACK = "direct_attack"
    FORK = "fork"
    DOUBLE_ATTACK = "double_attack"

    ABSOLUTE_PIN = "absolute_pin"
    REMOVAL_OF_DEFENDER = "removal_of_defender"

    FORCED_RESPONSE = "forced_response"


class TacticalCandidateStatus(StrEnum):
    DETECTED = "detected"
    VERIFIED = "verified"
    REFUTED = "refuted"


def _is_king(piece: PieceRef) -> bool:
    return piece.piece_type is PieceType.KING


@dataclass(frozen=True, slots=True)
class TacticalCandidate:
    kind: TacticalCandidateKind
    status: TacticalCandidateStatus

    actors: tuple[PieceRef, ...] = ()
    targets: tuple[PieceRef, ...] = ()
    related: tuple[PieceRef, ...] = ()
    responses: tuple[ChessMove, ...] = ()

    def __post_init__(self) -> None:
        kind = TacticalCandidateKind
        k = self.kind
        problem: str | None = None
        if k in (kind.CHECK, kind.CHECKMATE):
            if not self.actors or len(self.targets) != 1 or not _is_king(self.targets[0]):
                problem = "needs actors and exactly one king target"
            elif self.responses:
                problem = "must not carry responses"
        elif k is kind.HANGING_PIECE:
            if not self.actors or len(self.targets) != 1 or _is_king(self.targets[0]):
                problem = "needs actors and exactly one non-king target"
        elif k is kind.DIRECT_ATTACK:
            if (
                len(self.actors) != 1
                or len(self.targets) != 1
                or _is_king(self.targets[0])
                or self.targets[0].color is self.actors[0].color
            ):
                problem = "needs one actor and one enemy non-king target"
        elif k is kind.FORK:
            if len(self.actors) != 1 or len(self.targets) < 2:
                problem = "needs one actor and two or more targets"
        elif k is kind.DOUBLE_ATTACK:
            if len(self.actors) < 2 or len(self.targets) < 2:
                problem = "needs two or more actors and targets"
        elif k is kind.ABSOLUTE_PIN:
            if (
                len(self.actors) != 1
                or len(self.targets) != 1
                or len(self.related) != 1
                or not _is_king(self.related[0])
            ):
                problem = "needs one pinner, one pinned piece and one king"
        elif k is kind.REMOVAL_OF_DEFENDER:
            if not self.actors or len(self.targets) != 1 or len(self.related) != 1:
                problem = "needs actors, one target and one captured defender"
        elif k is kind.FORCED_RESPONSE and len(self.responses) != 1:
            problem = "needs exactly one response"
        if problem is not None:
            raise ValueError(f"{k.value} candidate {problem}")


@dataclass(frozen=True, slots=True)
class TacticalDetection:
    before_position_id: str
    after_position_id: str
    move: ChessMove
    mover: Color
    candidates: tuple[TacticalCandidate, ...]
