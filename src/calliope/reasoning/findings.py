"""Typed findings of catalogue v1 (R2-D §1.7, E2) and the `line_material` operand.

Frozen records in the reasoning type registry. No chess strings: moves are `MoveRef` /
`SearchMoveRef`, pieces `PieceRef`; the renderer produces text from fact records.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from calliope.facts import Color, LineEnd, NodeId, PieceType
from calliope.reasoning.refs import (
    LineSegment,
    MaterialAmount,
    MoveRef,
    PieceRef,
    SearchMoveRef,
    SearchRef,
)


class OutcomeKind(StrEnum):
    MATE = "mate"
    STABLE = "stable"
    DRAWN = "drawn"
    OPEN = "open"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class Outcome:
    """`outcome(L)` of R2-D §1.3; `delta` is the mover's balance from P for `STABLE`."""

    kind: OutcomeKind
    winner: Color | None = None
    moves: int | None = None
    delta: int | None = None
    plies: int = 0
    line_end: LineEnd | None = None
    reason: str | None = None  # for MISSING: LINE_TOO_SHORT or NOT_COMPUTED(...)


@dataclass(frozen=True, slots=True)
class DecisiveEvent:
    """R2-D §1.5: the ply where the balance reaches its final level; `node` is `N_ply`."""

    ply: int
    node: NodeId
    victim: PieceRef | None
    capturer: PieceRef | None
    promotion: PieceType | None


@dataclass(frozen=True, slots=True)
class LineMaterial:
    """One line of S in the `line_material` observation (R2-D §2)."""

    window: LineSegment  # plies 0 … k of the line (R2-D §1.3)
    outcome: Outcome
    changes: tuple[int, ...]  # plies with a capture or a promotion
    event: DecisiveEvent | None
    veto: tuple[int, ...] | None  # the balances from B, `bB_0 … bB_k`; None when B = P


@dataclass(frozen=True, slots=True)
class MaterialFinding:
    amount: MaterialAmount
    event: DecisiveEvent
    played: Outcome
    best: Outcome


@dataclass(frozen=True, slots=True)
class MateFinding:
    moves: int
    mating_move: MoveRef | SearchMoveRef | None


@dataclass(frozen=True, slots=True)
class ComparisonFinding:
    best_move: SearchMoveRef
    best: Outcome
    played: Outcome


@dataclass(frozen=True, slots=True)
class MechanismFinding:
    kind: str  # fork | pin | skewer | discovery
    node: NodeId
    move: MoveRef
    actor: PieceRef
    targets: tuple[PieceRef, ...]
    walked_into: bool


@dataclass(frozen=True, slots=True)
class DefenceFinding:
    defender: PieceRef
    defended: PieceRef
    reason: str  # DefenceEndReason value


class HangingKind(StrEnum):
    MOVED_INTO_ATTACK = "moved_into_attack"
    LINE_OPENED = "line_opened"
    LEFT = "left"


@dataclass(frozen=True, slots=True)
class HangingFinding:
    kind: HangingKind
    piece: PieceRef
    attackers: tuple[PieceRef, ...]


@dataclass(frozen=True, slots=True)
class ForcingFinding:
    check: bool
    replies: int


@dataclass(frozen=True, slots=True)
class AlternativeFinding:
    line: SearchRef
    loss: int  # 1/2000 expected points


class Fate(StrEnum):
    """The fate of a given-up piece on an alternative (R2-D §3.11)."""

    PRESERVED = "preserved"
    TRADED = "traded"
    GIVEN_UP = "given_up"
    UNDECIDED = "undecided"


@dataclass(frozen=True, slots=True)
class OfferFinding:
    amount: MaterialAmount
    event: DecisiveEvent
    keeping: tuple[tuple[SearchRef, Fate], ...]


class CompensationKind(StrEnum):
    MATE = "mate"
    MATERIAL_RETURN = "material_return"
    ENGINE = "engine"


@dataclass(frozen=True, slots=True)
class CompensationFinding:
    kind: CompensationKind
    expected: int  # E(Lp), 1/2000


class PreventsKind(StrEnum):
    MATE = "mate"
    MATERIAL = "material"
    MIXED = "mixed"


@dataclass(frozen=True, slots=True)
class PreventsFinding:
    kind: PreventsKind
    alternatives: int
    smallest_loss: int | None


KINDS = (
    OutcomeKind,
    Outcome,
    DecisiveEvent,
    LineMaterial,
    MaterialFinding,
    MateFinding,
    ComparisonFinding,
    MechanismFinding,
    DefenceFinding,
    HangingKind,
    HangingFinding,
    ForcingFinding,
    AlternativeFinding,
    Fate,
    OfferFinding,
    CompensationKind,
    CompensationFinding,
    PreventsKind,
    PreventsFinding,
)

__all__ = [k.__name__ for k in KINDS] + ["KINDS"]
