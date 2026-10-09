"""The common connector of fact families (design F0 §5)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, ClassVar, Protocol

import chess

from calliope.facts.identity import IdentityStep, PieceMap
from calliope.facts.keys import PositionKey
from calliope.facts.tree import Scope
from calliope.facts.values import FactClass

_EMPTY: Mapping[str, Any] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class HistoryWindow:
    """Known positions that can repeat the node: the last `min(halfmove_clock, known_plies)` plies.

    `keys` is newest first (distance 1, 2, …). `unknown_plies` is how many plies of the
    repetition window lie before the known history (0 when history is complete, §2.2).
    """

    keys: tuple[PositionKey, ...]
    unknown_plies: int

    @property
    def complete(self) -> bool:
        return self.unknown_plies == 0


@dataclass(frozen=True, slots=True)
class FamilyContext:
    """Read-only inputs of one family computation. Families never mutate `board`.

    A family receives exactly the records it lists in `requires`, resolved by scope (F2-D §9):
    POSITION and NODE families on their own target; an EDGE family on the child (`records`, which
    also holds required records of this edge) and on the parent (`parent_records`); a SPAN family
    on the node (`records`) and on the grandparent (`grandparent_records`).

    A POSITION family's `board` is rebuilt from its `PositionKey` (clocks 0, no move stack), so
    its record cannot depend on anything that differs between transpositions (F2-D §1.5).
    """

    board: chess.Board
    records: Mapping[str, Any]  # records of the families listed in `requires`, this target
    history: HistoryWindow | None = None  # NODE scope
    parent_board: chess.Board | None = None  # EDGE scope: position before the move
    move: chess.Move | None = None  # EDGE scope
    identity: IdentityStep | None = None  # EDGE scope: the identity step of this edge
    parent_records: Mapping[str, Any] = _EMPTY  # EDGE scope
    grandparent_records: Mapping[str, Any] = _EMPTY  # SPAN scope
    # EDGE: (parent, child); SPAN: (grandparent, parent, node)
    pieces_maps: tuple[PieceMap, ...] = ()
    # EDGE: (this edge,); SPAN: (grandparent -> parent, parent -> node)
    identity_steps: tuple[IdentityStep, ...] = ()


class FactFamily(Protocol):
    name: ClassVar[str]
    version: ClassVar[str]
    scope: ClassVar[Scope]
    fact_class: ClassVar[FactClass]
    requires: ClassVar[tuple[str, ...]]

    def compute(self, ctx: FamilyContext) -> Any: ...
