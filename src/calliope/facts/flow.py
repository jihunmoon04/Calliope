"""Material along a path of the tree: a read helper over `material` and `move` records.

Design: `docs/design/reasoning-r0-design.md` §6.5 (amends A0 §8). It stores nothing and changes no
digest; it reads only records every node carries (the tier of engine-only nodes included).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise

from calliope.facts.errors import InvalidRequestError
from calliope.facts.families.material import MaterialFacts
from calliope.facts.families.move import Capture, MoveFacts, Promotion
from calliope.facts.keys import Color, NodeId
from calliope.facts.tree import TerminalKind, TreeView
from calliope.facts.values import NotComputed


class UnstableReason(StrEnum):
    DRAWN_END = "drawn_end"  # the path ends in stalemate or an automatic draw
    CAPTURE_AT_END = "capture_at_end"  # the last ply captures
    TOO_SHORT = "too_short"  # fewer than 2 plies after the last material change


@dataclass(frozen=True, slots=True)
class Stable:
    """The material of the path's end is settled (legacy P8 §12.0)."""


@dataclass(frozen=True, slots=True)
class Unstable:
    reason: UnstableReason


STABLE = Stable()


@dataclass(frozen=True, slots=True)
class PlyMaterial:
    """One ply of a path: a capture and a promotion of one move stay together (R2-D C8)."""

    index: int  # 1-based ply of the path
    mover: Color
    capture: Capture | None
    promotion: Promotion | None
    points: tuple[int, int]  # (white, black) under points_v1, after this ply


@dataclass(frozen=True, slots=True)
class MaterialFlow:
    path: tuple[NodeId, ...]
    points_before: tuple[int, int] | None
    points_after: tuple[int, int] | None
    plies: tuple[PlyMaterial, ...]
    last_change: int | None  # ply index of the last capture or promotion
    stable: Stable | Unstable | NotComputed

    def balance(self, color: Color, ply: int) -> int:
        """`color`'s points minus the opponent's after `ply`, relative to the path's start.

        Ply 0 is the start (balance 0). A capture of the opponent's queen raises the capturer's
        balance by 9 although its own points do not change (R0-D §6.5).
        """

        if self.points_before is None:
            raise ValueError("the flow has no material records")
        if ply == 0:
            return 0
        after = self.plies[ply - 1].points
        return _signed(after, color) - _signed(self.points_before, color)


def _signed(points: tuple[int, int], color: Color) -> int:
    white, black = points
    return white - black if color is Color.WHITE else black - white


def material_flow(view: TreeView, path: tuple[NodeId, ...]) -> MaterialFlow:
    """Material along `path`, a parent-to-child chain of nodes visible in `view`."""

    path = tuple(path)
    if not path:
        raise InvalidRequestError("a material path needs at least one node")
    for parent, child in pairwise(path):
        if not view.has_node(child) or view.node(child).parent != parent:
            raise InvalidRequestError(f"{child} is not a child of {parent} at rev {view.rev}")
    if not view.has_node(path[0]):
        raise InvalidRequestError(f"no node {path[0]} at rev {view.rev}")

    start = view.fact("material", path[0])
    if not isinstance(start, MaterialFacts):
        return _missing(path, start)
    before = start.points.value
    plies: list[PlyMaterial] = []
    last_change: int | None = None
    for index, child in enumerate(path[1:], start=1):
        move = view.fact("move", child)
        material = view.fact("material", child)
        if not isinstance(move, MoveFacts):
            return _missing(path, move)
        if not isinstance(material, MaterialFacts):
            return _missing(path, material)
        capture = next((e for e in move.events if isinstance(e, Capture)), None)
        promotion = next((e for e in move.events if isinstance(e, Promotion)), None)
        if capture is not None or promotion is not None:
            last_change = index
        plies.append(PlyMaterial(index, move.mover, capture, promotion, material.points.value))

    end = view.node(path[-1]).terminal
    settled = len(plies) - last_change >= 2 if last_change is not None else len(plies) >= 2
    if end.kind in (TerminalKind.STALEMATE, TerminalKind.AUTOMATIC_DRAW):
        stable: Stable | Unstable = Unstable(UnstableReason.DRAWN_END)
    elif end.kind is TerminalKind.CHECKMATE or settled:
        stable = STABLE
    elif plies and plies[-1].capture is not None:
        stable = Unstable(UnstableReason.CAPTURE_AT_END)
    else:
        stable = Unstable(UnstableReason.TOO_SHORT)
    after = plies[-1].points if plies else before
    return MaterialFlow(path, before, after, tuple(plies), last_change, stable)


def _missing(path: tuple[NodeId, ...], value: object) -> MaterialFlow:
    reason = value.reason if isinstance(value, NotComputed) else "record not applicable"
    return MaterialFlow(path, None, None, (), None, NotComputed(reason))
