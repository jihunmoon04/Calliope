"""Requests to the fact engine (design F0 §2). Engine-related fields arrive with packet F4."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from calliope.facts.keys import NodeId


class RoleKind(StrEnum):
    """Why a node or edge is in the tree. Order is the canonical role order (§3.5)."""

    PLAYED = "played"
    EXPLORED = "explored"
    ANALYSIS = "analysis"
    ENGINE = "engine"


INPUT_ROLE_KINDS = (RoleKind.PLAYED, RoleKind.EXPLORED, RoleKind.ANALYSIS)


@dataclass(frozen=True, slots=True)
class LineRole:
    """The input role of an `extend` request: `PLAYED`, `EXPLORED` or `ANALYSIS(by)`."""

    kind: RoleKind
    by: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in INPUT_ROLE_KINDS:
            raise ValueError(f"{self.kind} is not an input role")
        if (self.kind is RoleKind.ANALYSIS) != bool(self.by):
            raise ValueError("ANALYSIS needs `by`; PLAYED and EXPLORED take none")


PLAYED = LineRole(RoleKind.PLAYED)
EXPLORED = LineRole(RoleKind.EXPLORED)


def analysis(by: str) -> LineRole:
    return LineRole(RoleKind.ANALYSIS, by)


@dataclass(frozen=True, slots=True)
class RootSpec:
    """`fen=None` means the standard start position. `moves` are replayed before the root."""

    fen: str | None = None
    moves: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class InputLine:
    """Moves (UCI or SAN) played from `start` (default: the root node)."""

    label: str
    moves: tuple[str, ...]
    start: NodeId | None = None


@dataclass(frozen=True, slots=True)
class SessionBudget:
    """Cumulative over the session (§2.4). `None` means unlimited."""

    max_nodes: int | None = None


@dataclass(frozen=True, slots=True)
class OpenRequest:
    root: RootSpec = RootSpec()
    # The eager set (F2-D §9): None means every registered family. `status`, `draw` and `move`
    # are always added, and the set is closed under `requires`.
    families: tuple[str, ...] | None = None
    budget: SessionBudget = SessionBudget()


@dataclass(frozen=True, slots=True)
class ExtendRequest:
    lines: tuple[InputLine, ...]
    role: LineRole


@dataclass(frozen=True, slots=True)
class EnsureRequest:
    """Compute the missing records of `families` (and their dependencies) on `nodes` (F2-D §9)."""

    nodes: tuple[NodeId, ...]
    families: tuple[str, ...]
