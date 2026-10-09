"""`pawns` (POSITION, DEFINED, `pawns_v1`): pawn structure (F2-D §5).

Forward and behind are relative to the pawn's colour (White forward = rank + 1). File distance is
|file − file′|. A promoted pawn is no longer a pawn and leaves every pawn fact.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

import chess

from calliope.facts.families.base import FamilyContext
from calliope.facts.families.geometry import bits, squares
from calliope.facts.keys import Color
from calliope.facts.tree import Scope
from calliope.facts.values import FactClass


class FileState(StrEnum):
    OPEN = "open"  # no pawns
    SEMI_OPEN_WHITE = "semi_open_white"  # no white pawn, at least one black pawn
    SEMI_OPEN_BLACK = "semi_open_black"  # no black pawn, at least one white pawn
    CLOSED = "closed"  # pawns of both colours


@dataclass(frozen=True, slots=True)
class PawnFacts:
    square: str
    color: Color
    isolated: bool
    doubled: bool
    passed: bool
    own_pawn_ahead: bool
    backward: bool
    supporters: tuple[str, ...]  # friendly pawns on an adjacent file, one rank behind
    phalanx: tuple[str, ...]  # friendly pawns on an adjacent file, same rank


@dataclass(frozen=True, slots=True)
class PawnChain:
    color: Color
    squares: tuple[str, ...]
    bases: tuple[str, ...]  # members without a supporter
    heads: tuple[str, ...]  # members supporting no member


@dataclass(frozen=True, slots=True)
class FileFacts:
    file: str
    white_pawns: int
    black_pawns: int
    state: FileState


@dataclass(frozen=True, slots=True)
class ByColor[T]:
    white: T
    black: T

    def of(self, color: Color) -> T:
        return self.white if color is Color.WHITE else self.black


@dataclass(frozen=True, slots=True)
class PawnsFacts:
    pawns: tuple[PawnFacts, ...]  # by square
    chains: tuple[PawnChain, ...]  # by first member square
    islands: ByColor[tuple[tuple[str, ...], ...]]  # runs of adjacent files holding own pawns
    files: tuple[FileFacts, ...]  # a … h
    outside_enemy_pawn_cones: ByColor[tuple[str, ...]]  # per colour: squares in no enemy span

    def at(self, square: str) -> PawnFacts | None:
        return next((p for p in self.pawns if p.square == square), None)


class PawnsFamily:
    name: ClassVar[str] = "pawns"
    version: ClassVar[str] = "pawns_v1"
    scope: ClassVar[Scope] = Scope.POSITION
    fact_class: ClassVar[FactClass] = FactClass.DEFINED
    requires: ClassVar[tuple[str, ...]] = ()
    # record types of this family, for the closed type registry (F5-D §2)
    record_types: ClassVar[tuple[type, ...]] = (
        PawnsFacts,
        PawnFacts,
        PawnChain,
        FileFacts,
        FileState,
        ByColor,
    )

    def compute(self, ctx: FamilyContext) -> PawnsFacts:
        board = ctx.board
        pawns: list[PawnFacts] = []
        support: dict[int, tuple[int, ...]] = {}
        for square in bits(board.pawns):
            color = board.color_at(square)
            assert color is not None
            facts, supporters = _pawn(board, square, color)
            pawns.append(facts)
            support[square] = supporters
        return PawnsFacts(
            pawns=tuple(pawns),
            chains=_chains(board, support),
            islands=ByColor(_islands(board, chess.WHITE), _islands(board, chess.BLACK)),
            files=tuple(_file(board, file) for file in range(8)),
            outside_enemy_pawn_cones=ByColor(
                _outside_cones(board, chess.WHITE), _outside_cones(board, chess.BLACK)
            ),
        )


def _ranks(ranks) -> int:
    mask = 0
    for rank in ranks:
        mask |= chess.BB_RANKS[rank]
    return mask


# AHEAD[color][rank]: every square on a rank strictly ahead of `rank` for `color`.
AHEAD = (
    tuple(_ranks(range(rank)) for rank in range(8)),  # chess.BLACK
    tuple(_ranks(range(rank + 1, 8)) for rank in range(8)),  # chess.WHITE
)
ADJACENT_FILES = tuple(
    (chess.BB_FILES[f - 1] if f > 0 else 0) | (chess.BB_FILES[f + 1] if f < 7 else 0)
    for f in range(8)
)


def _pawn(board: chess.Board, square: int, color: chess.Color) -> tuple[PawnFacts, tuple[int, ...]]:
    own = board.pawns & board.occupied_co[color]
    enemy = board.pawns & board.occupied_co[not color]
    file, rank = chess.square_file(square), chess.square_rank(square)
    forward = 1 if color == chess.WHITE else -1
    ahead = AHEAD[color][rank]
    adjacent = ADJACENT_FILES[file]
    same_file = chess.BB_FILES[file]
    isolated = not own & adjacent
    behind_rank = rank - forward
    supporters = own & adjacent & chess.BB_RANKS[behind_rank] if 0 <= behind_rank < 8 else 0
    phalanx = own & adjacent & chess.BB_RANKS[rank]
    stop_rank = rank + forward
    stop_attacked = 0 <= stop_rank < 8 and bool(
        chess.BB_PAWN_ATTACKS[color][chess.square(file, stop_rank)] & enemy
    )
    backward = (
        not isolated
        and not own & adjacent & ~ahead  # none on the same rank or behind
        and stop_attacked
    )
    facts = PawnFacts(
        square=chess.SQUARE_NAMES[square],
        color=Color.of(color),
        isolated=isolated,
        doubled=chess.popcount(own & same_file) >= 2,
        passed=not enemy & (same_file | adjacent) & ahead,
        own_pawn_ahead=bool(own & same_file & ahead),
        backward=backward,
        supporters=squares(supporters),
        phalanx=squares(phalanx),
    )
    return facts, tuple(bits(supporters))


def _chains(board: chess.Board, support: dict[int, tuple[int, ...]]) -> tuple[PawnChain, ...]:
    """Connected components (≥ 2 pawns) of the supporter graph."""

    neighbours: dict[int, set[int]] = {sq: set() for sq in support}
    for supported, supporters in support.items():
        for supporter in supporters:
            neighbours[supported].add(supporter)
            neighbours[supporter].add(supported)
    supporting = {s for supporters in support.values() for s in supporters}
    seen: set[int] = set()
    chains: list[PawnChain] = []
    for start in sorted(support):
        if start in seen or not neighbours[start]:
            continue
        component: set[int] = set()
        frontier = [start]
        while frontier:
            square = frontier.pop()
            if square in component:
                continue
            component.add(square)
            frontier.extend(neighbours[square] - component)
        seen |= component
        members = sorted(component)
        color = board.color_at(start)
        assert color is not None
        chains.append(
            PawnChain(
                color=Color.of(color),
                squares=_names(members),
                bases=_names(sq for sq in members if not support[sq]),
                heads=_names(sq for sq in members if sq not in supporting),
            )
        )
    return tuple(chains)


def _islands(board: chess.Board, color: chess.Color) -> tuple[tuple[str, ...], ...]:
    own = board.pawns & board.occupied_co[color]
    files = [bool(own & chess.BB_FILES[f]) for f in range(8)]
    islands: list[tuple[str, ...]] = []
    run: list[str] = []
    for f, present in enumerate(files):
        if present:
            run.append(chess.FILE_NAMES[f])
        elif run:
            islands.append(tuple(run))
            run = []
    if run:
        islands.append(tuple(run))
    return tuple(islands)


def _file(board: chess.Board, file: int) -> FileFacts:
    mask = board.pawns & chess.BB_FILES[file]
    white = chess.popcount(mask & board.occupied_co[chess.WHITE])
    black = chess.popcount(mask & board.occupied_co[chess.BLACK])
    if not white and not black:
        state = FileState.OPEN
    elif not white:
        state = FileState.SEMI_OPEN_WHITE
    elif not black:
        state = FileState.SEMI_OPEN_BLACK
    else:
        state = FileState.CLOSED
    return FileFacts(chess.FILE_NAMES[file], white, black, state)


def _outside_cones(board: chess.Board, color: chess.Color) -> tuple[str, ...]:
    """Squares in no current enemy pawn's span (adjacent files, every rank strictly ahead)."""

    enemy_color = not color
    covered = 0
    for square in bits(board.pawns & board.occupied_co[enemy_color]):
        covered |= ADJACENT_FILES[square & 7] & AHEAD[enemy_color][square >> 3]
    return squares(chess.BB_ALL & ~covered)


def _names(members: Iterable[int]) -> tuple[str, ...]:
    return tuple(chess.SQUARE_NAMES[sq] for sq in members)
