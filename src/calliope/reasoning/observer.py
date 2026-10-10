"""The observer: the move judgement `quality_v1` and observations (R0-D §7, R2-D §2).

Pure: a function of a pinned `TreeView`. Every number of a judgement comes from one search, the
parent's basis S (R0-D D3); nothing here compares scores of two searches.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from calliope.facts import (
    Color,
    Cp,
    EngineLineFact,
    EngineLineId,
    Mate,
    NodeId,
    NotComputed,
    TreeView,
    Wdl,
)
from calliope.reasoning.refs import Evidence, LineSegment, MoveSubject, SearchRef

QUALITY_POLICY = "quality_v1"
OBSERVATIONS_VERSION = "obs_v1"

# quality_v1 bands, lower bounds inclusive, in 1/2000 expected points (R0-D §7.2 step 6.4)
BANDS = ((40, "EXCELLENT"), (100, "GOOD"), (200, "INACCURACY"), (400, "MISTAKE"))


class Grade(StrEnum):
    BEST = "best"
    EXCELLENT = "excellent"
    GOOD = "good"
    INACCURACY = "inaccuracy"
    MISTAKE = "mistake"
    BLUNDER = "blunder"

    @property
    def rank(self) -> int:
        return _GRADE_ORDER.index(self)

    def at_least(self, other: Grade) -> bool:
        """`self ≥ other`: `self` is `other` or worse (R0-D §7.1)."""

        return self.rank >= other.rank


_GRADE_ORDER = tuple(Grade)


class JudgementStatus(StrEnum):
    DECIDED = "decided"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class LineScore:
    """One line of S, with its expected points from the mover's view, in 1/2000."""

    rank: int
    move: str
    score: Cp | Mate
    wdl: Wdl
    expected: int


@dataclass(frozen=True, slots=True)
class Judgement:
    subject: MoveSubject
    status: JudgementStatus
    reason: str | None
    search: SearchRef | None  # S, pinned at V_0 (R0-D R0-I1)
    played: LineScore | None
    best: LineScore | None
    alternatives: tuple[LineScore, ...]  # every line of S, by rank
    loss: int | None  # 1/2000 expected points
    grade: Grade | None
    policy: str = QUALITY_POLICY


@dataclass(frozen=True, slots=True)
class JudgementRef:
    subject: MoveSubject


@dataclass(frozen=True, slots=True)
class MissingLine:
    """A standard line that is not attached at P."""

    search_id: str
    rank: int
    reason: str


@dataclass(frozen=True, slots=True)
class Observation:
    kind: str
    version: str
    subject: MoveSubject
    round: int
    operands: tuple
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True, slots=True)
class ObservationRef:
    kind: str
    version: str
    subject: MoveSubject
    round: int
    index: int  # within (round, kind), canonical order


def expected(wdl: Wdl, mover: Color) -> int:
    """Expected points of the mover in 1/2000: `2·win + draw`, WDL in permille (R0-D §7.2.4)."""

    win = wdl.white_win if mover is Color.WHITE else wdl.black_win
    return 2 * win + wdl.draw


def _mate_distance_grade(d: int) -> Grade:
    """legacy `_slower_grade`, for a mate `d` moves slower (or `d` moves sooner mated)."""

    if d <= 0:
        return Grade.EXCELLENT
    if d == 1:
        return Grade.GOOD
    if d <= 3:
        return Grade.INACCURACY
    return Grade.MISTAKE


def grade(played: LineScore, best: LineScore, mover: Color) -> tuple[int, Grade]:
    """`quality_v1`: the loss of `played` against rank 1 and its grade (R0-D §7.2 steps 5–6)."""

    loss = max(0, best.expected - played.expected)
    if played.rank == 1:
        return loss, Grade.BEST
    p, b = played.score, best.score
    if isinstance(p, Mate) and isinstance(b, Mate):
        if p.winner is mover and b.winner is mover:
            return loss, _mate_distance_grade(p.moves - b.moves)
        if p.winner is not mover and b.winner is not mover:
            return loss, _mate_distance_grade(b.moves - p.moves)
    for bound, name in BANDS:
        if loss < bound:
            return loss, Grade[name]
    return loss, Grade.BLUNDER


def judge(view: TreeView, subject: MoveSubject) -> Judgement:
    """The judgement of `subject` on `view` (R0-D §7.2)."""

    parent = view.node(subject.parent)
    child = view.node(subject.child)
    mover = parent.side_to_move
    basis = view.basis(subject.parent)
    if not isinstance(basis, str):
        reason = basis.reason if isinstance(basis, NotComputed) else "NOT_APPLICABLE"
        return _inconclusive(subject, reason, None)
    search = view.search(basis)
    ref = SearchRef(search.search_id)
    if any(not isinstance(line.wdl, Wdl) for line in search.lines):
        return _inconclusive(subject, "WDL_UNAVAILABLE", ref)
    scores = tuple(_line_score(line, mover) for line in sorted(search.lines, key=_rank))
    played = next((s for s in scores if s.move == child.incoming_move), None)
    if played is None:
        return _inconclusive(subject, "NOT_IN_BASIS", ref)
    best = scores[0]
    loss, result = grade(played, best, mover)
    return Judgement(
        subject, JudgementStatus.DECIDED, None, ref, played, best, scores, loss, result
    )


def _rank(line: EngineLineFact) -> int:
    return line.rank


def _line_score(line: EngineLineFact, mover: Color) -> LineScore:
    assert isinstance(line.wdl, Wdl)
    return LineScore(line.rank, line.move, line.score, line.wdl, expected(line.wdl, mover))


def _inconclusive(subject: MoveSubject, reason: str, search: SearchRef | None) -> Judgement:
    return Judgement(
        subject, JudgementStatus.INCONCLUSIVE, reason, search, None, None, (), None, None
    )


def standard_line_ids(judgement: Judgement) -> tuple[EngineLineId, EngineLineId] | None:
    """`(Lp, L1)` of a decided judgement: lines of S anchored at P (R0-D §7.3)."""

    if judgement.status is not JudgementStatus.DECIDED:
        return None
    assert judgement.search is not None and judgement.played is not None
    anchor = judgement.subject.parent
    search_id = judgement.search.search_id
    return (
        EngineLineId(anchor, search_id, judgement.played.rank),
        EngineLineId(anchor, search_id, 1),
    )


def standard_lines(view: TreeView, judgement: Judgement, round_: int = 0) -> Observation | None:
    """The observation `standard_lines` (R2-D §2): `Lp` and `L1` as attached line segments."""

    ids = standard_line_ids(judgement)
    if ids is None:
        return None
    operands: list[LineSegment | MissingLine] = []
    evidence: list[Evidence] = []
    for line_id in ids:
        evidence.append(SearchRef(line_id.search_id, line_id.rank))
        try:
            record = view.line(line_id)
        except KeyError:
            operands.append(MissingLine(line_id.search_id, line_id.rank, "NOT_ATTACHED"))
            continue
        segment = LineSegment(line_id, 0, len(record.nodes) - 1)
        operands.append(segment)
        evidence.append(segment)
    return Observation(
        "standard_lines",
        OBSERVATIONS_VERSION,
        judgement.subject,
        round_,
        tuple(operands),
        tuple(evidence),
    )


def line_nodes(view: TreeView, judgement: Judgement, plies: int) -> tuple[NodeId, ...]:
    """The engine-line nodes of `Lp` and `L1` within `plies` (the round-0 `ensure`, R0-D §6.1)."""

    ids = standard_line_ids(judgement)
    if ids is None:
        return ()
    nodes: list[NodeId] = []
    for line_id in ids:
        try:
            record = view.line(line_id)
        except KeyError:
            continue
        nodes.extend(record.nodes[1 : plies + 1])
    return tuple(dict.fromkeys(nodes))
