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
    SquareRef,
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
    MATE_OVER_SCORES = "mate_over_scores"  # MS-D §3: open keeping lines compared by their scores


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


@dataclass(frozen=True, slots=True)
class PieceOfferFinding:
    """`piece_offer_v1` (LV-D §5–§6): the offered piece and how the move offered it."""

    piece: PieceRef  # at C
    offer: int  # points_v1: exposure at C minus what the move captured
    created: bool | None  # the exposure grew with the move; None when P is in check (unknown)
    capture: bool  # the move captures
    taken_by: MoveRef  # the opponent's least valuable capture of the piece (the move into X)
    best_keeping: SearchRef | None  # the best line of S that offers nothing (LV-D §5 step 4)
    best_keeping_expected: int | None  # its expected points, 1/2000


@dataclass(frozen=True, slots=True)
class CaptureHoldsFinding:
    """`capture_holds_v1`: the mover's best reply after the capture, and its expected points."""

    reply: SearchRef
    expected: int  # 1/2000, from the mover's view


@dataclass(frozen=True, slots=True)
class RescueFinding:
    """`rescue_v1`: the moved piece was en prise at P and is not at C."""

    piece: PieceRef  # at C
    exposure_before: int  # points_v1, hypothetical at P


@dataclass(frozen=True, slots=True)
class MissedGainFinding:
    """`missed_gain_v1` (MV-D §4): rank 1 of S and the played move's loss, both read from S."""

    best: SearchMoveRef  # S, rank 1, ply 1: a reported move, attached or not
    loss: int  # 1/2000 expected points, under the request's grading


class DrawKind(StrEnum):
    """How a checking draw is proved (EV-D §2.1): by rule (fifth, third occurrence) or by score."""

    FIVEFOLD = "fivefold"
    THREEFOLD = "threefold"
    REPEATED = "repeated"
    SCORED = "scored"


@dataclass(frozen=True, slots=True)
class ChecksDrawFinding:
    """`checks_draw_v1`, `checks_draw_missed_v1` (EV-D §2.1): a run of checks ending the window."""

    checker: Color
    kind: DrawKind
    line: LineSegment  # `N_{q-1} … N_k`: it shows the edges into `N_q … N_k`
    checks: int
    repeat_at: MoveRef | None  # the edge into the first fifth / third occurrence or repetition


class ReplyKind(StrEnum):
    """What the best move does about the opponent's reply (EV-D §3.3)."""

    RESCUES = "rescues"
    DEFENDS = "defends"
    COVERS = "covers"


@dataclass(frozen=True, slots=True)
class ReplyFinding:
    """`best_stops_reply_v1` (EV-D §3.4). `board` is the node `square` is shown on (B1); `counter`
    the node `B1 + r` that `answer` (canonical UCI) is played from."""

    kind: ReplyKind
    best: SearchMoveRef
    reply: MoveRef
    piece: PieceRef
    square: SquareRef | None
    board: NodeId | None
    counter: NodeId | None
    answer: str | None
    lost: int | None  # COVERS: `ex(C, s).gain`
    played_gain: int | None  # DEFENDS: `g(R)`
    best_gain: int | None  # DEFENDS: `g(C)`


@dataclass(frozen=True, slots=True)
class ConcessionFinding:
    """`concession_v1` (EF-D §3.4): the loser's own move after the reply exposed `piece`, and the
    move did not force it. The origin is one ply (`origin_first == origin_last`) or the range the
    undecided nodes leave open; `nodes` are `N_{origin_first}` and, when different,
    `N_{origin_last}` (`N_{q−1}` for an empty run)."""

    piece: PieceRef
    origin_first: int  # o⁺
    origin_last: int  # o⁻
    nodes: tuple[NodeId, ...]


class CheckAnswerKind(StrEnum):
    """How the move answers a check (EF-D §5)."""

    BLOCK = "block"
    CAPTURE = "capture"
    KING = "king"


@dataclass(frozen=True, slots=True)
class CheckAnswerFinding:
    """`check_answer_v1` (EF-D §5)."""

    kind: CheckAnswerKind
    checkers: tuple[PieceRef, ...]
    legal_moves: int


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
    PieceOfferFinding,
    CaptureHoldsFinding,
    RescueFinding,
    MissedGainFinding,
    DrawKind,
    ChecksDrawFinding,
    ReplyKind,
    ReplyFinding,
    ConcessionFinding,
    CheckAnswerKind,
    CheckAnswerFinding,
)

__all__ = [k.__name__ for k in KINDS] + ["KINDS"]
