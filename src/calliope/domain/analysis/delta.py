"""Objective before/after board changes caused by one move.

Only exact board-state differences: no tactical meaning, no evaluation. Legal-capture and
hanging status are side-to-move dependent and are deliberately not diffed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from calliope.domain.chess import ChessMove, Color, PieceRef, PieceType


@dataclass(frozen=True, slots=True)
class PieceCorrespondence:
    """``before`` and ``after`` are the same physical piece."""

    before: PieceRef
    after: PieceRef


class PieceTransitionKind(StrEnum):
    MOVE = "move"
    PROMOTION = "promotion"
    CASTLING_ROOK = "castling_rook"


@dataclass(frozen=True, slots=True)
class PieceTransition:
    kind: PieceTransitionKind
    before: PieceRef
    after: PieceRef


@dataclass(frozen=True, slots=True)
class CaptureDelta:
    capturer_before: PieceRef
    capturer_after: PieceRef
    captured: PieceRef
    captured_square: str
    landing_square: str
    is_en_passant: bool


@dataclass(frozen=True, slots=True)
class MaterialChange:
    """Change in the count of one piece type; no values are assigned."""

    color: Color
    piece_type: PieceType
    count_delta: int


class RelationChangeKind(StrEnum):
    ADDED = "added"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class AttackChange:
    """ADDED uses after-position pieces; REMOVED uses before-position pieces."""

    kind: RelationChangeKind
    attacker: PieceRef
    target_square: str


@dataclass(frozen=True, slots=True)
class DefenseChange:
    """ADDED uses after-position pieces; REMOVED uses before-position pieces."""

    kind: RelationChangeKind
    defender: PieceRef
    defended: PieceRef


class CheckChangeKind(StrEnum):
    CREATED = "created"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class CheckChange:
    kind: CheckChangeKind
    checked_color: Color


@dataclass(frozen=True, slots=True)
class BoardDelta:
    before_position_id: str
    after_position_id: str

    move: ChessMove
    mover: Color

    piece_correspondence: tuple[PieceCorrespondence, ...]
    transitions: tuple[PieceTransition, ...]

    capture: CaptureDelta | None

    material_changes: tuple[MaterialChange, ...]

    new_attacks: tuple[AttackChange, ...]
    removed_attacks: tuple[AttackChange, ...]

    new_defenses: tuple[DefenseChange, ...]
    removed_defenses: tuple[DefenseChange, ...]

    check_changes: tuple[CheckChange, ...]
