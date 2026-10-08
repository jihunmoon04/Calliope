"""The common connector of fact families (design F0 §5)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol

import chess

from calliope.facts.identity import IdentityStep
from calliope.facts.keys import PositionKey
from calliope.facts.tree import Scope
from calliope.facts.values import FactClass


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
    """Read-only inputs of one family computation. Families never mutate `board`."""

    board: chess.Board
    records: Mapping[str, Any]  # records of the families listed in `requires`, same target
    history: HistoryWindow | None = None  # NODE scope
    parent_board: chess.Board | None = None  # EDGE scope: position before the move
    move: chess.Move | None = None  # EDGE scope
    identity: IdentityStep | None = None  # EDGE scope


class FactFamily(Protocol):
    name: ClassVar[str]
    version: ClassVar[str]
    scope: ClassVar[Scope]
    fact_class: ClassVar[FactClass]
    requires: ClassVar[tuple[str, ...]]

    def compute(self, ctx: FamilyContext) -> Any: ...
