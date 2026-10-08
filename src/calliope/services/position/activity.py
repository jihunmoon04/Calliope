"""activity_v1 on top of the positional foundation; no engine calls and no value judgements.

The tactical observation port is the sole legal-move producer. Its moves are structurally
validated and bound to P4 captures; this is not a second legality generator.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from calliope.application.ports.tactics import TacticalObservation, TacticalObservationPort
from calliope.domain.analysis.activity import (
    AbsolutePin,
    ActivityFacts,
    ActivityLineAnalysis,
    ActivityPositionAnalysis,
    ActivityTransitionAnalysis,
    AttackFootprintChange,
    AttackTargetKind,
    PieceActivity,
    RayChange,
    SliderRay,
    TargetOccupancyChange,
    project_piece_geometry,
    project_slider_rays,
    project_square_access,
    uci_structure_error,
)
from calliope.domain.analysis.positional import (
    POSITIONAL_DEFINITION_VERSION,
    PositionAnalysis,
    TransitionAnalysis,
)
from calliope.domain.chess import (
    ChessMove,
    LegalCapture,
    PieceRef,
    PieceType,
    PositionSnapshot,
    square_index,
)
from calliope.errors import (
    IncompatibleBoardDeltaError,
    IncompatiblePositionObservationError,
    IncompatibleTacticalContextError,
)
from calliope.services.position.line import LineAnalyzer
from calliope.services.position.positional import PositionAnalyzer, TransitionAnalyzer


def _ordered(squares: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(squares, key=square_index))


def _tactical(message: str) -> IncompatibleTacticalContextError:
    return IncompatibleTacticalContextError(message)


def _validate_structural(structural: PositionAnalysis) -> dict[str, PieceRef]:
    """Step 1 (and step 5 attack references, via the domain projections)."""
    position, facts, features = structural.position, structural.facts, structural.features
    if not position.position_id == facts.position_id == features.position_id:
        raise IncompatiblePositionObservationError("structural frame ids disagree")
    if features.definition_version != POSITIONAL_DEFINITION_VERSION:
        raise IncompatiblePositionObservationError("unsupported positional definition version")
    pieces = {s.piece.square: s.piece for s in facts.pieces}
    if len(pieces) != len(facts.pieces):
        raise IncompatiblePositionObservationError("facts contain duplicate piece squares")
    if len(set(facts.attacks)) != len(facts.attacks):
        raise IncompatiblePositionObservationError("facts contain duplicate attack relations")
    return pieces


def _validate_moves(
    position: PositionSnapshot, pieces: dict[str, PieceRef], moves: tuple[ChessMove, ...]
) -> None:
    """Step 3: structural UCI checks only; SAN is ignored for identity."""
    ucis = [m.uci for m in moves]
    if ucis != sorted(set(ucis)):
        raise _tactical("legal moves must have unique UCIs in sorted order")
    for uci in ucis:
        source = pieces.get(uci[:2]) if isinstance(uci, str) else None
        if source is None or source.color is not position.side_to_move:
            raise _tactical(f"legal move {uci!r} does not start from a mover-owned piece")
        error = uci_structure_error(source, uci)
        if error is not None:
            raise _tactical(f"legal {error}")


def _validate_captures(
    pieces: dict[str, PieceRef],
    moves: tuple[ChessMove, ...],
    captures: tuple[LegalCapture, ...],
) -> None:
    """Step 4: bind P4 captures and tactical legal moves by UCI in both directions."""
    by_uci = {c.move.uci: c for c in captures}
    if len(by_uci) != len(captures):
        raise _tactical("P4 legal captures contain duplicate UCIs")
    legal = {m.uci for m in moves}
    if not set(by_uci) <= legal:
        raise _tactical("a P4 legal capture is absent from the tactical legal moves")
    for uci in sorted(legal):
        source, target = pieces[uci[:2]], uci[2:4]
        occupant = pieces.get(target)
        is_capture = (occupant is not None and occupant.color is not source.color) or (
            source.piece_type is PieceType.PAWN and occupant is None and uci[0] != uci[2]
        )
        if is_capture and uci not in by_uci:
            raise _tactical(f"legal capture {uci!r} is absent from the P4 legal captures")
    for uci, capture in by_uci.items():
        source, landing = pieces[uci[:2]], uci[2:4]
        occupant = pieces.get(landing)
        if capture.capturer != source or capture.landing_square != landing:
            raise _tactical(f"capture {uci!r} does not bind its capturer and landing square")
        if occupant is None:
            victim = pieces.get(landing[0] + uci[1])
            if not capture.is_en_passant or source.piece_type is not PieceType.PAWN:
                raise _tactical(f"capture {uci!r} onto an empty square must be en passant")
            if victim is None or victim.piece_type is not PieceType.PAWN:
                raise _tactical(f"en passant {uci!r} has no pawn victim beside its source")
        else:
            victim = occupant
            if capture.is_en_passant:
                raise _tactical(f"capture {uci!r} onto an occupied square is not en passant")
        if (
            capture.captured != victim
            or victim.color is source.color
            or victim.piece_type is PieceType.KING
        ):
            raise _tactical(f"capture {uci!r} does not bind its actual victim")


def _validate_tactics(
    structural: PositionAnalysis,
    pieces: dict[str, PieceRef],
    observation: TacticalObservation,
) -> tuple[AbsolutePin, ...]:
    position = structural.position
    if observation.position_id != position.position_id:
        raise _tactical("tactical observation belongs to a different position")
    if observation.side_to_move is not position.side_to_move:
        raise _tactical("tactical side to move disagrees with the position")
    _validate_moves(position, pieces, observation.legal_moves)
    _validate_captures(pieces, observation.legal_moves, structural.facts.legal_captures)
    live = set(pieces.values())
    pins = []
    for pin in observation.absolute_pins:
        if not {pin.pinner, pin.pinned, pin.king} <= live:
            raise _tactical("absolute pin references a piece outside the observed position")
        try:
            pins.append(AbsolutePin(pin.pinner, pin.pinned, pin.king))
        except IncompatiblePositionObservationError as exc:
            raise _tactical(str(exc)) from exc
    pins.sort(key=lambda p: square_index(p.pinned.square))
    return tuple(pins)


@dataclass(slots=True)
class ActivityAnalyzer:
    positions: PositionAnalyzer
    tactics: TacticalObservationPort

    def analyze(self, position: PositionSnapshot) -> ActivityPositionAnalysis:
        return self._from_position_analysis(self.positions.analyze(position))

    def _from_position_analysis(self, structural: PositionAnalysis) -> ActivityPositionAnalysis:
        """Consume an exact structural frame from replay; validation is never skipped."""
        pieces = _validate_structural(structural)
        observation = self.tactics.observe_tactics(structural.position)
        pins = _validate_tactics(structural, pieces, observation)
        facts = structural.facts
        side = structural.position.side_to_move
        moves_by_source: dict[str, list[ChessMove]] = {}
        for move in observation.legal_moves:
            moves_by_source.setdefault(move.uci[:2], []).append(move)
        captures_by_piece: dict[PieceRef, list[LegalCapture]] = {}
        for capture in facts.legal_captures:
            captures_by_piece.setdefault(capture.capturer, []).append(capture)
        activities = []
        for piece, footprint, (empty, friendly, enemy) in project_piece_geometry(facts):
            on_move = piece.color is side
            activities.append(
                PieceActivity(
                    piece=piece,
                    footprint=footprint,
                    empty_attacks=empty,
                    friendly_attacks=friendly,
                    enemy_attacks=enemy,
                    legal_moves_now=tuple(moves_by_source.get(piece.square, ()))
                    if on_move
                    else None,
                    legal_captures_now=tuple(
                        sorted(captures_by_piece.get(piece, ()), key=lambda c: c.move.uci)
                    )
                    if on_move
                    else None,
                )
            )
        activity = ActivityFacts(
            source_facts=facts,
            position_id=facts.position_id,
            side_to_move=side,
            squares=project_square_access(facts),
            pieces=tuple(activities),
            rays=project_slider_rays(facts),
            absolute_pins=pins,
        )
        return ActivityPositionAnalysis(structural, activity)


def _footprint_change(
    before: PieceActivity, after: PieceActivity | None
) -> AttackFootprintChange | None:
    def kinds(activity: PieceActivity) -> dict[str, AttackTargetKind]:
        return {
            **dict.fromkeys(activity.empty_attacks, AttackTargetKind.EMPTY),
            **dict.fromkeys(activity.friendly_attacks, AttackTargetKind.FRIENDLY),
            **dict.fromkeys(activity.enemy_attacks, AttackTargetKind.ENEMY),
        }

    old = kinds(before)
    new = kinds(after) if after is not None else {}
    added = _ordered(new.keys() - old.keys())
    removed = _ordered(old.keys() - new.keys())
    occupancy = tuple(
        TargetOccupancyChange(s, old[s], new[s])
        for s in _ordered(old.keys() & new.keys())
        if old[s] is not new[s]
    )
    if after is not None and not (added or removed or occupancy):
        return None
    return AttackFootprintChange(
        before.piece, None if after is None else after.piece, added, removed, occupancy
    )


def _ray_change(
    direction: tuple[int, int],
    before: SliderRay | None,
    after: SliderRay | None,
    correspondence: dict[PieceRef, PieceRef],
) -> RayChange | None:
    old = set(before.visible_squares) if before is not None else set()
    new = set(after.visible_squares) if after is not None else set()
    mapped = tuple(correspondence.get(p) for p in before.occupants) if before else None
    blockers_changed = before is None or after is None or mapped != after.occupants
    if before is not None and after is not None and old == new and not blockers_changed:
        return None
    return RayChange(
        direction, before, after, _ordered(new - old), _ordered(old - new), blockers_changed
    )


def _activity_diff(
    structural: TransitionAnalysis,
    before: ActivityPositionAnalysis,
    after: ActivityPositionAnalysis,
) -> ActivityTransitionAnalysis:
    """Compare geometry through the already validated P5 physical-piece correspondence."""
    delta = structural.board_delta
    correspondence = {p.before: p.after for p in delta.piece_correspondence}
    after_pieces = {a.piece: a for a in after.activity.pieces}
    if set(correspondence.values()) != set(after_pieces):
        raise IncompatibleBoardDeltaError("correspondence does not cover the after activity")
    before_rays: dict[PieceRef, dict[tuple[int, int], SliderRay]] = {}
    after_rays: dict[PieceRef, dict[tuple[int, int], SliderRay]] = {}
    for ray in before.activity.rays:
        before_rays.setdefault(ray.source, {})[ray.direction] = ray
    for ray in after.activity.rays:
        after_rays.setdefault(ray.source, {})[ray.direction] = ray

    footprint_changes = []
    ray_changes = []
    for activity in before.activity.pieces:
        successor = correspondence.get(activity.piece)
        change = _footprint_change(activity, after_pieces.get(successor) if successor else None)
        if change is not None:
            footprint_changes.append(change)
        old = before_rays.get(activity.piece, {})
        new = after_rays.get(successor, {}) if successor is not None else {}
        for direction in sorted(old.keys() | new.keys()):
            ray = _ray_change(direction, old.get(direction), new.get(direction), correspondence)
            if ray is not None:
                ray_changes.append(ray)
    return ActivityTransitionAnalysis(
        structural, before, after, tuple(footprint_changes), tuple(ray_changes)
    )


@dataclass(slots=True)
class ActivityTransitionAnalyzer:
    transitions: TransitionAnalyzer
    activity: ActivityAnalyzer

    def analyze(self, before: PositionSnapshot, move: ChessMove) -> ActivityTransitionAnalysis:
        # The corrected structural boundary (including F1) runs before any activity observation.
        structural = self.transitions.analyze(before, move)
        return _activity_diff(
            structural,
            self.activity._from_position_analysis(structural.before),
            self.activity._from_position_analysis(structural.after),
        )


@dataclass(slots=True)
class ActivityLineAnalyzer:
    lines: LineAnalyzer
    activity: ActivityAnalyzer

    def analyze(
        self,
        initial: PositionSnapshot,
        moves: tuple[ChessMove, ...],
        *,
        max_plies: int = 64,
    ) -> ActivityLineAnalysis:
        # LineAnalyzer applies the budget before any observation; there is no second replay.
        structural = self.lines.analyze(initial, moves, max_plies=max_plies)
        frames = tuple(
            self.activity._from_position_analysis(frame)
            for frame in (structural.initial, *(t.after for t in structural.transitions))
        )
        steps = tuple(
            _activity_diff(transition, frames[i], frames[i + 1])
            for i, transition in enumerate(structural.transitions)
        )
        return ActivityLineAnalysis(structural, frames, steps)
