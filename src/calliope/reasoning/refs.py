"""The common currency of the reasoning blocks: subjects, operands and evidence (R0-D §4).

Every stage names chess objects and evidence with these types. They hold ids and indices only;
text with chess meaning (SAN, piece names) is produced by the renderer from fact records.
"""

from __future__ import annotations

from dataclasses import dataclass

from calliope.facts import EngineLineId, LineId, NodeId, PieceId, PositionKey

ClaimId = str  # = HypothesisId, a sha256 hex digest (R0-D §8.3)


@dataclass(frozen=True, slots=True)
class MoveSubject:
    """The move from `parent` to `child`."""

    parent: NodeId
    child: NodeId


@dataclass(frozen=True, slots=True)
class PieceRef:
    """A physical piece at a node (A0 §4)."""

    piece: PieceId
    node: NodeId
    square: str


@dataclass(frozen=True, slots=True)
class SquareRef:
    square: str


@dataclass(frozen=True, slots=True)
class MoveRef:
    """The move into `node`: an attached edge of the tree."""

    node: NodeId


@dataclass(frozen=True, slots=True)
class SearchMoveRef:
    """Ply `ply` (from 1) of the PV of line `rank` of a search, attached or not (review 4)."""

    search_id: str
    rank: int
    ply: int


@dataclass(frozen=True, slots=True)
class MaterialAmount:
    points: int
    policy: str = "points_v1"


@dataclass(frozen=True, slots=True)
class LineSegment:
    """Role indices `first … last` (inclusive) of an input or engine line."""

    line: LineId | EngineLineId
    first: int
    last: int


@dataclass(frozen=True, slots=True)
class FactRef:
    """A value inside a fact record: `path` walks field names and tuple indices."""

    family: str
    target: PositionKey | NodeId
    rev: int
    path: tuple[str | int, ...] = ()


@dataclass(frozen=True, slots=True)
class SearchRef:
    """A search, or one of its lines (`rank`)."""

    search_id: str
    rank: int | None = None


@dataclass(frozen=True, slots=True)
class ScopeRef:
    """The scope of a claim, used as qualification."""

    claim: ClaimId


LineRef = LineSegment
Evidence = FactRef | SearchRef | LineSegment
