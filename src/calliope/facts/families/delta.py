"""`delta` (EDGE, `delta_v1`): what the move changed in side-independent geometry (F2-D §7.1).

Relations are keyed by `PieceId` through each end's piece map, so a moved piece is the same
piece. Only changes are recorded. A captured piece ends every relation it took part in and its
flags end with `Absent(CAPTURED)`; a promoted pawn's pawn flags end with `Absent(PROMOTED)` and
its piece flags continue under the same id. Side-dependent facts are in `same_side_delta`.

Components carry their own class: relations from `pieces` and `lines` are RULE; those from
`pawns` and `king` are DEFINED (`COMPONENT_CLASS`).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

import chess

from calliope.facts.families.base import FamilyContext
from calliope.facts.families.king import KingFacts
from calliope.facts.families.lines import LinesFacts
from calliope.facts.families.pawns import ByColor, FileFacts, PawnsFacts
from calliope.facts.families.pieces import PiecesFacts
from calliope.facts.identity import PieceMap
from calliope.facts.keys import Color, PieceId
from calliope.facts.tree import Scope
from calliope.facts.values import CAPTURED, PROMOTED, Absent, FactClass


@dataclass(frozen=True, slots=True, order=True)
class PiecePair:
    """A directed relation between two pieces: attacker → victim, defender → defended, …"""

    source: PieceId
    target: PieceId


@dataclass(frozen=True, slots=True)
class SquareControl:
    piece: PieceId
    square: str


@dataclass(frozen=True, slots=True, order=True)
class PinRelation:
    pinner: PieceId
    pinned: PieceId
    king: PieceId


@dataclass(frozen=True, slots=True, order=True)
class XRayRelation:
    slider: PieceId
    first: PieceId
    second: PieceId


@dataclass(frozen=True, slots=True, order=True)
class BatteryRelation:
    pieces: tuple[PieceId, PieceId]  # unordered pair, stored sorted


@dataclass(frozen=True, slots=True)
class ZoneAttack:
    king: PieceId
    square: str
    attacker: PieceId


@dataclass(frozen=True, slots=True)
class SetChange[T]:
    began: tuple[T, ...]
    ended: tuple[T, ...]


@dataclass(frozen=True, slots=True)
class PieceFlags:
    attacked_without_defender: bool
    attackers_exceed_defenders: bool


@dataclass(frozen=True, slots=True)
class PawnFlags:
    isolated: bool
    doubled: bool
    passed: bool
    own_pawn_ahead: bool
    backward: bool


@dataclass(frozen=True, slots=True)
class FlagChange[T]:
    piece: PieceId
    before: T
    after: T | Absent


@dataclass(frozen=True, slots=True)
class FileChange:
    file: str
    before: FileFacts
    after: FileFacts


@dataclass(frozen=True, slots=True)
class IslandChange:
    color: Color
    before: tuple[tuple[str, ...], ...]
    after: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class DeltaFacts:
    square_control: SetChange[SquareControl]
    piece_attacks: SetChange[PiecePair]  # attacker → victim
    piece_defences: SetChange[PiecePair]  # defender → defended
    piece_flags: tuple[FlagChange[PieceFlags], ...]
    pins: SetChange[PinRelation]
    xrays: SetChange[XRayRelation]
    batteries: SetChange[BatteryRelation]
    pawn_flags: tuple[FlagChange[PawnFlags], ...]
    pawn_supports: SetChange[PiecePair]  # supporter → supported
    files: tuple[FileChange, ...]
    islands: tuple[IslandChange, ...]
    zone_attacks: SetChange[ZoneAttack]
    shield: SetChange[PiecePair]  # king → shield pawn


COMPONENT_CLASS: Mapping[str, FactClass] = {
    "square_control": FactClass.RULE,
    "piece_attacks": FactClass.RULE,
    "piece_defences": FactClass.RULE,
    "piece_flags": FactClass.RULE,
    "pins": FactClass.RULE,
    "xrays": FactClass.RULE,
    "batteries": FactClass.RULE,
    "pawn_flags": FactClass.DEFINED,
    "pawn_supports": FactClass.DEFINED,
    "files": FactClass.DEFINED,
    "islands": FactClass.DEFINED,
    "zone_attacks": FactClass.DEFINED,
    "shield": FactClass.DEFINED,
}


Raw = tuple[Any, ...]  # a relation as plain values: piece ids as strings, squares as indexes


@dataclass(frozen=True, slots=True)
class Relations:
    """One node's side-independent relation sets, as raw tuples keyed by piece-id strings.

    Raw tuples sort in canonical order and hash fast; `MAKERS` turns one into its record type.
    It is also the test hook for "delta applied to the parent's sets gives the child's" (§10.2).
    """

    square_control: frozenset[Raw]  # (piece, square index)
    piece_attacks: frozenset[Raw]  # (attacker, victim)
    piece_defences: frozenset[Raw]  # (defender, defended)
    piece_flags: Mapping[str, PieceFlags]
    pins: frozenset[Raw]  # (pinner, pinned, king)
    xrays: frozenset[Raw]  # (slider, first, second)
    batteries: frozenset[Raw]  # (lower id, higher id)
    pawn_flags: Mapping[str, PawnFlags]
    pawn_supports: frozenset[Raw]  # (supporter, supported)
    files: tuple[FileFacts, ...]
    islands: ByColor[tuple[tuple[str, ...], ...]]
    zone_attacks: frozenset[Raw]  # (king, square index, attacker)
    shield: frozenset[Raw]  # (king, pawn)


def _pair(raw: Raw) -> PiecePair:
    return PiecePair(PieceId(raw[0]), PieceId(raw[1]))


MAKERS: Mapping[str, Callable[[Raw], Any]] = {
    "square_control": lambda r: SquareControl(PieceId(r[0]), chess.SQUARE_NAMES[r[1]]),
    "piece_attacks": _pair,
    "piece_defences": _pair,
    "pins": lambda r: PinRelation(PieceId(r[0]), PieceId(r[1]), PieceId(r[2])),
    "xrays": lambda r: XRayRelation(PieceId(r[0]), PieceId(r[1]), PieceId(r[2])),
    "batteries": lambda r: BatteryRelation((PieceId(r[0]), PieceId(r[1]))),
    "pawn_supports": _pair,
    "zone_attacks": lambda r: ZoneAttack(PieceId(r[0]), chess.SQUARE_NAMES[r[1]], PieceId(r[2])),
    "shield": _pair,
}
SET_COMPONENTS = tuple(MAKERS)


class DeltaFamily:
    name: ClassVar[str] = "delta"
    version: ClassVar[str] = "delta_v1"
    scope: ClassVar[Scope] = Scope.EDGE
    fact_class: ClassVar[FactClass] = FactClass.DEFINED  # mixed; see COMPONENT_CLASS
    requires: ClassVar[tuple[str, ...]] = ("pieces", "lines", "pawns", "king")
    component_classes: ClassVar[Mapping[str, FactClass]] = COMPONENT_CLASS  # F2-N2
    # record types of this family, for the closed type registry (F5-D §2)
    record_types: ClassVar[tuple[type, ...]] = (
        DeltaFacts,
        SetChange,
        FlagChange,
        PiecePair,
        SquareControl,
        PinRelation,
        XRayRelation,
        BatteryRelation,
        ZoneAttack,
        PieceFlags,
        PawnFlags,
        FileChange,
        IslandChange,
    )

    def compute(self, ctx: FamilyContext) -> DeltaFacts:
        parent_map, child_map = ctx.pieces_maps
        before = relations_of(ctx.parent_records, parent_map)
        after = relations_of(ctx.records, child_map)
        changes = {
            name: _change(getattr(before, name), getattr(after, name), MAKERS[name])
            for name in SET_COMPONENTS
        }
        return DeltaFacts(
            piece_flags=_flags(before.piece_flags, after.piece_flags, lambda _pid: CAPTURED),
            pawn_flags=_flags(
                before.pawn_flags,
                after.pawn_flags,
                lambda pid: PROMOTED if pid in after.piece_flags else CAPTURED,
            ),
            files=tuple(
                FileChange(b.file, b, a)
                for b, a in zip(before.files, after.files, strict=True)
                if b != a
            ),
            islands=tuple(
                IslandChange(color, before.islands.of(color), after.islands.of(color))
                for color in Color
                if before.islands.of(color) != after.islands.of(color)
            ),
            **changes,
        )


def relations_of(records: Mapping[str, Any], piece_map: PieceMap) -> Relations:
    """One node's relation sets from its POSITION records and its piece map."""

    ids = {square: pid.value for square, pid in piece_map}
    index = _SQUARE_INDEX
    pieces: PiecesFacts = records["pieces"]
    lines: LinesFacts = records["lines"]
    pawns: PawnsFacts = records["pawns"]
    kings: ByColor[KingFacts] = records["king"]
    king_ids = {color: ids[kings.of(color).square] for color in Color}
    control: set[Raw] = set()
    attacks: set[Raw] = set()
    defences: set[Raw] = set()
    flags: dict[str, PieceFlags] = {}
    pins: set[Raw] = set()
    for piece in pieces.pieces:
        pid = ids[piece.square]
        footprint = piece.attacks
        for part in (footprint.empty, footprint.friendly, footprint.enemy):
            control.update((pid, index[sq]) for sq in part)
        attacks.update((ids[a.square], pid) for a in piece.attackers)
        defences.update((ids[d.square], pid) for d in piece.defenders)
        flags[pid] = PieceFlags(piece.attacked_without_defender, piece.attackers_exceed_defenders)
        if piece.absolutely_pinned is not None:
            pins.add((ids[piece.absolutely_pinned.pinner], pid, king_ids[piece.color]))
    xrays = {
        (ids[ray.source], ids[ray.xray.first.square], ids[ray.xray.second.square])
        for ray in lines.rays
        if ray.xray is not None
    }
    batteries = {tuple(sorted((ids[b.pieces[0]], ids[b.pieces[1]]))) for b in lines.batteries}
    pawn_flags = {
        ids[p.square]: PawnFlags(p.isolated, p.doubled, p.passed, p.own_pawn_ahead, p.backward)
        for p in pawns.pawns
    }
    supports = {(ids[supporter], ids[p.square]) for p in pawns.pawns for supporter in p.supporters}
    zone: set[Raw] = set()
    shield: set[Raw] = set()
    for color in Color:
        king = kings.of(color)
        kid = king_ids[color]
        zone.update((kid, index[z.square], ids[a.square]) for z in king.zone for a in z.attackers)
        shield.update((kid, ids[sq]) for sq in king.shield)
    return Relations(
        square_control=frozenset(control),
        piece_attacks=frozenset(attacks),
        piece_defences=frozenset(defences),
        piece_flags=flags,
        pins=frozenset(pins),
        xrays=frozenset(xrays),
        batteries=frozenset(batteries),
        pawn_flags=pawn_flags,
        pawn_supports=frozenset(supports),
        files=pawns.files,
        islands=pawns.islands,
        zone_attacks=frozenset(zone),
        shield=frozenset(shield),
    )


_SQUARE_INDEX = {name: i for i, name in enumerate(chess.SQUARE_NAMES)}


def _change(before: frozenset[Raw], after: frozenset[Raw], make: Callable[[Raw], Any]) -> SetChange:
    return SetChange(
        began=tuple(make(r) for r in sorted(after - before)),
        ended=tuple(make(r) for r in sorted(before - after)),
    )


def _flags[T](
    before: Mapping[str, T],
    after: Mapping[str, T],
    gone: Callable[[str], Absent],
) -> tuple[FlagChange[T], ...]:
    out: list[FlagChange[T]] = []
    for pid in sorted(before):
        now: T | Absent = after[pid] if pid in after else gone(pid)
        if now != before[pid]:
            out.append(FlagChange(PieceId(pid), before[pid], now))
    return tuple(out)
