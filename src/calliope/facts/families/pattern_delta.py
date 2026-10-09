"""`pattern_delta` (EDGE, DEFINED, `pattern_delta_v1`): pattern changes across a move (F3-D §4).

Participants are mapped to `PieceId` through each end's piece map. Only these id projections are
compared: a participant's type, `order` or pinned flag changing under the same ids is not a
change here. `DEFENCE_ENDED_UNDER_ATTACK` is a filtered view of `delta.piece_defences.ended`
with a reason taken from the edge's identity step.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from calliope.facts.families.base import FamilyContext
from calliope.facts.families.delta import DeltaFacts, SetChange
from calliope.facts.families.patterns import LinePattern, PatternsFacts
from calliope.facts.families.pieces import PiecesFacts
from calliope.facts.identity import IdentityStep, PieceMap
from calliope.facts.keys import PieceId, PieceType
from calliope.facts.tree import Scope
from calliope.facts.values import CAPTURED, Absent, FactClass


class DefenceEndReason(StrEnum):
    DEFENDER_CAPTURED = "defender_captured"
    DEFENDER_MOVED = "defender_moved"  # the mover or the castling rook
    DEFENDED_MOVED = "defended_moved"  # the mover or the castling rook
    LINE_BLOCKED = "line_blocked"  # neither moved: a slider's line was blocked


@dataclass(frozen=True, slots=True, order=True)
class LineTriple:
    slider: PieceId
    front: PieceId  # the blocker of a discovery line
    back: PieceId


@dataclass(frozen=True, slots=True)
class TargetSetChange:
    """An actor's (or defender's) id set: `()` means the pattern does not hold."""

    piece: PieceId
    before: tuple[PieceId, ...]
    after: tuple[PieceId, ...] | Absent


@dataclass(frozen=True, slots=True)
class BackRankIds:
    blockers: tuple[PieceId, ...]  # sorted by id
    covered: tuple[str, ...]  # board order


@dataclass(frozen=True, slots=True)
class BackRankChange:
    king: PieceId
    before: BackRankIds | None
    after: BackRankIds | None


@dataclass(frozen=True, slots=True)
class DefenceEnded:
    defender: PieceId
    defended: PieceId
    reason: DefenceEndReason


@dataclass(frozen=True, slots=True)
class PatternDeltaFacts:
    multi_target_attacks: tuple[TargetSetChange, ...]  # by piece id
    relative_pins: SetChange[LineTriple]
    skewers: SetChange[LineTriple]
    discovery_lines: SetChange[LineTriple]
    sole_defenders: tuple[TargetSetChange, ...]  # by piece id
    back_ranks: tuple[BackRankChange, ...]  # by king id
    defences_ended_under_attack: tuple[DefenceEnded, ...]  # by (defender, defended)


class PatternDeltaFamily:
    name: ClassVar[str] = "pattern_delta"
    version: ClassVar[str] = "pattern_delta_v1"
    scope: ClassVar[Scope] = Scope.EDGE
    fact_class: ClassVar[FactClass] = FactClass.DEFINED
    requires: ClassVar[tuple[str, ...]] = ("patterns", "pieces", "delta")
    # record types of this family, for the closed type registry (F5-D §2)
    record_types: ClassVar[tuple[type, ...]] = (
        PatternDeltaFacts,
        LineTriple,
        TargetSetChange,
        BackRankIds,
        BackRankChange,
        DefenceEnded,
        DefenceEndReason,
        SetChange,
    )

    def compute(self, ctx: FamilyContext) -> PatternDeltaFacts:
        parent_map, child_map = ctx.pieces_maps
        (step,) = ctx.identity_steps
        before = _Ids(ctx.parent_records["patterns"], ctx.parent_records["pieces"], parent_map)
        after = _Ids(ctx.records["patterns"], ctx.records["pieces"], child_map)
        return PatternDeltaFacts(
            multi_target_attacks=_set_changes(
                before.multi_target_attacks, after.multi_target_attacks, after.alive
            ),
            relative_pins=_change(before.relative_pins, after.relative_pins),
            skewers=_change(before.skewers, after.skewers),
            discovery_lines=_change(before.discovery_lines, after.discovery_lines),
            sole_defenders=_set_changes(before.sole_defenders, after.sole_defenders, after.alive),
            back_ranks=tuple(
                BackRankChange(king, before.back_ranks.get(king), after.back_ranks.get(king))
                for king in sorted(before.kings)
                if before.back_ranks.get(king) != after.back_ranks.get(king)
            ),
            defences_ended_under_attack=_defences_ended(
                ctx.records["delta"], ctx.records["pieces"], child_map, step
            ),
        )


class _Ids:
    """One end's patterns as `PieceId` projections."""

    def __init__(self, patterns: PatternsFacts, pieces: PiecesFacts, piece_map: PieceMap) -> None:
        ids = dict(piece_map)
        self.alive = frozenset(ids.values())
        self.kings = frozenset(
            ids[p.square] for p in pieces.pieces if p.piece_type is PieceType.KING
        )
        self.multi_target_attacks = {
            ids[m.actor.square]: _sorted(ids[t.piece.square] for t in m.targets)
            for m in patterns.multi_target_attacks
        }
        self.sole_defenders = {
            ids[s.defender.square]: _sorted(ids[d.square] for d in s.defended)
            for s in patterns.sole_defenders
        }

        def triples(items: tuple[LinePattern, ...]) -> frozenset[LineTriple]:
            return frozenset(
                LineTriple(ids[p.slider.square], ids[p.front.square], ids[p.back.square])
                for p in items
            )

        self.relative_pins = triples(patterns.relative_pins)
        self.skewers = triples(patterns.skewers)
        self.discovery_lines = triples(patterns.discovery_lines)
        self.back_ranks = {
            ids[b.king.square]: BackRankIds(_sorted(ids[r.square] for r in b.blockers), b.covered)
            for b in patterns.back_ranks
        }


def _sorted(items: Iterable[PieceId]) -> tuple[PieceId, ...]:
    return tuple(sorted(items))


def _change(before: frozenset[LineTriple], after: frozenset[LineTriple]) -> SetChange[LineTriple]:
    return SetChange(began=tuple(sorted(after - before)), ended=tuple(sorted(before - after)))


def _set_changes(
    before: Mapping[PieceId, tuple[PieceId, ...]],
    after: Mapping[PieceId, tuple[PieceId, ...]],
    alive: frozenset[PieceId],
) -> tuple[TargetSetChange, ...]:
    out: list[TargetSetChange] = []
    for piece in sorted(before.keys() | after.keys()):
        old = before.get(piece, ())
        new: tuple[PieceId, ...] | Absent = after.get(piece, ()) if piece in alive else CAPTURED
        if new != old:
            out.append(TargetSetChange(piece, old, new))
    return tuple(out)


def _defences_ended(
    delta: DeltaFacts, pieces: PiecesFacts, child_map: PieceMap, step: IdentityStep
) -> tuple[DefenceEnded, ...]:
    squares = {pid: square for square, pid in child_map}
    moved = {step.mover} | ({step.rook[0]} if step.rook is not None else set())
    out: list[DefenceEnded] = []
    for pair in delta.piece_defences.ended:  # sorted by (defender, defended)
        defender, defended = pair.source, pair.target
        square = squares.get(defended)
        if square is None:
            continue  # the defended piece was captured: its relations end in `delta`
        facts = pieces.at(square)
        assert facts is not None
        if facts.piece_type is PieceType.KING or facts.attacker_count == 0:
            continue
        out.append(DefenceEnded(defender, defended, _reason(defender, defended, step, moved)))
    return tuple(out)


def _reason(
    defender: PieceId, defended: PieceId, step: IdentityStep, moved: set[PieceId]
) -> DefenceEndReason:
    if defender == step.captured:
        return DefenceEndReason.DEFENDER_CAPTURED
    if defender in moved:
        return DefenceEndReason.DEFENDER_MOVED
    if defended in moved:
        return DefenceEndReason.DEFENDED_MOVED
    return DefenceEndReason.LINE_BLOCKED
