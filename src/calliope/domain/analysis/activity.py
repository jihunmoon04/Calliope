"""Versioned geometric activity observations, not mobility scores or explanation claims.

Geometry comes from P4 attacks and the P4 piece map. Legal-action fields describe only the
side to move; the opponent's fields are None because it is not on move.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from calliope.domain.analysis.positional import (
    POSITIONAL_DEFINITION_VERSION,
    LineAnalysis,
    PositionAnalysis,
    TransitionAnalysis,
)
from calliope.domain.chess import (
    ChessMove,
    Color,
    LegalCapture,
    PieceRef,
    PieceType,
    PositionFacts,
    square_index,
)
from calliope.errors import IncompatiblePositionObservationError

ACTIVITY_DEFINITION_VERSION = "activity_v1"

Direction = tuple[int, int]

_BISHOP_DIRECTIONS: tuple[Direction, ...] = ((-1, -1), (-1, 1), (1, -1), (1, 1))
_ROOK_DIRECTIONS: tuple[Direction, ...] = ((-1, 0), (0, -1), (0, 1), (1, 0))
SLIDER_DIRECTIONS: dict[PieceType, tuple[Direction, ...]] = {
    PieceType.BISHOP: _BISHOP_DIRECTIONS,
    PieceType.ROOK: _ROOK_DIRECTIONS,
    PieceType.QUEEN: tuple(sorted(_BISHOP_DIRECTIONS + _ROOK_DIRECTIONS)),
}
SQUARES: tuple[str, ...] = tuple(f"{f}{r}" for r in "12345678" for f in "abcdefgh")


def _fail(message: str) -> IncompatiblePositionObservationError:
    return IncompatiblePositionObservationError(message)


_UCI = re.compile(r"[a-h][1-8][a-h][1-8][qrbn]?")


def _require_square(square: object, what: str) -> None:
    try:
        square_index(square)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise _fail(f"{what} contains an invalid square: {square!r}") from None


def uci_structure_error(source: PieceRef, uci: object) -> str | None:
    """Structural UCI check for a move by ``source``; not a legality check.

    Requires lowercase standard UCI from the piece's square to a different valid square,
    and a promotion suffix exactly when a pawn reaches its last rank.
    """
    if not isinstance(uci, str) or not _UCI.fullmatch(uci):
        return f"move {uci!r} is not canonical standard UCI"
    if uci[:2] != source.square:
        return f"move {uci!r} does not start from {source.square}"
    if uci[2:4] == uci[:2]:
        return f"move {uci!r} does not change square"
    last_rank = "8" if source.color is Color.WHITE else "1"
    promotes = source.piece_type is PieceType.PAWN and uci[3] == last_rank
    if promotes != (len(uci) == 5):
        return f"move {uci!r} has an inconsistent promotion suffix"
    return None


def _canonical_squares(squares: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(squares, key=square_index))


def _require_canonical_squares(squares: tuple[str, ...], what: str) -> None:
    for square in squares:
        _require_square(square, what)
    if squares != _canonical_squares(set(squares)):
        raise _fail(f"{what} must be unique squares in board order")


def _require_canonical_pieces(pieces: tuple[PieceRef, ...], what: str) -> None:
    if pieces != tuple(sorted(set(pieces), key=lambda p: square_index(p.square))) or len(
        {p.square for p in pieces}
    ) != len(pieces):
        raise _fail(f"{what} must be unique pieces in board order")


def _require_canonical_captures(captures: tuple[LegalCapture, ...], what: str) -> None:
    ucis = [c.move.uci for c in captures]
    if ucis != sorted(set(ucis)):
        raise _fail(f"{what} must have unique UCIs in sorted order")


def ray_path(square: str, direction: Direction) -> tuple[str, ...]:
    """Every square after ``square`` in ``direction`` up to the board edge, near to far."""
    df, dr = direction
    file, rank = ord(square[0]) - ord("a") + df, int(square[1]) - 1 + dr
    path = []
    while 0 <= file < 8 and 0 <= rank < 8:
        path.append(f"{chr(ord('a') + file)}{rank + 1}")
        file, rank = file + df, rank + dr
    return tuple(path)


class AttackTargetKind(StrEnum):
    EMPTY = "empty"
    FRIENDLY = "friendly"
    ENEMY = "enemy"


@dataclass(frozen=True, slots=True)
class SliderRay:
    """Complete geometric ray of one slider; squares beyond the first blocker are not attacks.

    An edge-empty ray has ``squares == ()``; an unblocked ray has squares but no occupants.
    """

    source: PieceRef
    direction: Direction
    squares: tuple[str, ...]
    occupants: tuple[PieceRef, ...]

    def __post_init__(self) -> None:
        directions = SLIDER_DIRECTIONS.get(self.source.piece_type)
        if directions is None:
            raise _fail("only bishops, rooks and queens have slider rays")
        if self.direction not in directions:
            raise _fail("ray direction is not applicable to the source piece type")
        if self.squares != ray_path(self.source.square, self.direction):
            raise _fail("ray squares must run from the next square to the board edge")
        if len(set(self.occupants)) != len(self.occupants):
            raise _fail("ray occupants must be unique")
        positions = [
            self.squares.index(p.square) if p.square in self.squares else -1 for p in self.occupants
        ]
        if -1 in positions or positions != sorted(set(positions)):
            raise _fail("ray occupants must lie on the ray in near-to-far order")

    @property
    def first_blocker(self) -> PieceRef | None:
        return self.occupants[0] if self.occupants else None

    @property
    def visible_squares(self) -> tuple[str, ...]:
        """Squares through and including the first blocker (of either color), or to the edge."""
        if not self.occupants:
            return self.squares
        return self.squares[: self.squares.index(self.occupants[0].square) + 1]

    @property
    def edge_empty(self) -> bool:
        return not self.squares

    @property
    def unblocked(self) -> bool:
        return bool(self.squares) and not self.occupants


@dataclass(frozen=True, slots=True)
class AbsolutePin:
    """Rule-level absolute pin copied from the tactical observation."""

    pinner: PieceRef
    pinned: PieceRef
    king: PieceRef

    def __post_init__(self) -> None:
        if self.king.piece_type is not PieceType.KING:
            raise _fail("absolute pin must be against a king")
        if self.pinned.color is not self.king.color or self.pinned.piece_type is PieceType.KING:
            raise _fail("pinned piece must be a non-king of the king's color")
        if self.pinner.color is self.king.color or self.pinner.piece_type not in SLIDER_DIRECTIONS:
            raise _fail("pinner must be an opposing slider")


@dataclass(frozen=True, slots=True)
class SquareAccess:
    """Geometric attackers of one square and current-side legal captures landing on it.

    A geometric attacker need not be able to capture. Captures belong only to the side to
    move; their absence says nothing about the opponent, which is not on move.
    """

    square: str
    occupant: PieceRef | None
    white_attackers: tuple[PieceRef, ...]
    black_attackers: tuple[PieceRef, ...]
    current_legal_captures: tuple[LegalCapture, ...]

    def __post_init__(self) -> None:
        _require_square(self.square, "square access")
        if self.occupant is not None and self.occupant.square != self.square:
            raise _fail("square occupant stands on a different square")
        for color, attackers in (
            (Color.WHITE, self.white_attackers),
            (Color.BLACK, self.black_attackers),
        ):
            _require_canonical_pieces(attackers, "square attackers")
            if any(a.color is not color or a.square == self.square for a in attackers):
                raise _fail("square attacker has the wrong color or stands on the square")
        _require_canonical_captures(self.current_legal_captures, "square captures")
        if any(c.landing_square != self.square for c in self.current_legal_captures):
            raise _fail("square capture lands on a different square")

    @property
    def white_attacker_count(self) -> int:
        return len(self.white_attackers)

    @property
    def black_attacker_count(self) -> int:
        return len(self.black_attackers)


@dataclass(frozen=True, slots=True)
class PieceActivity:
    """Geometric attack footprint plus current-side legal actions (None when not on move).

    Legal destinations are not a subset of the footprint: pawn advances and castling lie
    outside it, and a friendly occupied attacked square is never a legal destination.
    """

    piece: PieceRef
    footprint: tuple[str, ...]
    empty_attacks: tuple[str, ...]
    friendly_attacks: tuple[str, ...]
    enemy_attacks: tuple[str, ...]
    legal_moves_now: tuple[ChessMove, ...] | None
    legal_captures_now: tuple[LegalCapture, ...] | None

    def __post_init__(self) -> None:
        parts = (self.empty_attacks, self.friendly_attacks, self.enemy_attacks)
        for squares in (self.footprint, *parts):
            _require_canonical_squares(squares, "attack footprint")
        if self.piece.square in self.footprint:
            raise _fail("a piece does not attack its own square")
        if sum(map(len, parts)) != len(self.footprint) or set().union(*parts) != set(
            self.footprint
        ):
            raise _fail("footprint partitions must be disjoint and cover the footprint")
        if (self.legal_moves_now is None) != (self.legal_captures_now is None):
            raise _fail("legal moves and captures are observed together or not at all")
        if self.legal_moves_now is None or self.legal_captures_now is None:
            return
        ucis = [m.uci for m in self.legal_moves_now]
        for uci in ucis:
            error = uci_structure_error(self.piece, uci)
            if error is not None:
                raise _fail(error)
        if ucis != sorted(set(ucis)):
            raise _fail("legal moves must have unique UCIs in sorted order")
        _require_canonical_captures(self.legal_captures_now, "piece captures")
        if any(c.capturer != self.piece or c.move.uci not in ucis for c in self.legal_captures_now):
            raise _fail("piece captures must be legal moves made by this piece")

    @property
    def geometric_attack_count(self) -> int:
        return len(self.footprint)

    @property
    def legal_destinations_now(self) -> tuple[str, ...] | None:
        """Unique UCI targets; four promotion choices share one destination."""
        if self.legal_moves_now is None:
            return None
        return _canonical_squares({m.uci[2:4] for m in self.legal_moves_now})

    @property
    def legal_move_count_now(self) -> int | None:
        return None if self.legal_moves_now is None else len(self.legal_moves_now)

    @property
    def legal_capture_count_now(self) -> int | None:
        return None if self.legal_captures_now is None else len(self.legal_captures_now)


def _source_piece_map(facts: PositionFacts) -> dict[str, PieceRef]:
    pieces = {s.piece.square: s.piece for s in facts.pieces}
    if len(pieces) != len(facts.pieces):
        raise _fail("facts contain duplicate piece squares")
    return pieces


def _source_footprints(
    facts: PositionFacts, pieces: dict[str, PieceRef]
) -> dict[PieceRef, tuple[str, ...]]:
    if len(set(facts.attacks)) != len(facts.attacks):
        raise _fail("facts contain duplicate attack relations")
    targets: dict[PieceRef, set[str]] = {p: set() for p in pieces.values()}
    for relation in facts.attacks:
        if pieces.get(relation.attacker.square) != relation.attacker:
            raise _fail("attack relation references a piece outside the observed position")
        targets[relation.attacker].add(relation.target_square)
    footprints = {p: _canonical_squares(t) for p, t in targets.items()}
    if any(footprints[s.piece] != _canonical_squares(s.attacks) for s in facts.pieces):
        raise _fail("piece-state attacks disagree with attack relations")
    return footprints


def _target_kind(piece: PieceRef, occupant: PieceRef | None) -> AttackTargetKind:
    if occupant is None:
        return AttackTargetKind.EMPTY
    return AttackTargetKind.FRIENDLY if occupant.color is piece.color else AttackTargetKind.ENEMY


def project_square_access(facts: PositionFacts) -> tuple[SquareAccess, ...]:
    """All 64 square records projected from P4 attacks and legal captures."""
    pieces = _source_piece_map(facts)
    footprints = _source_footprints(facts, pieces)
    attackers: dict[str, list[PieceRef]] = {s: [] for s in SQUARES}
    for piece in sorted(footprints, key=lambda p: square_index(p.square)):
        for target in footprints[piece]:
            attackers[target].append(piece)
    captures: dict[str, list[LegalCapture]] = {s: [] for s in SQUARES}
    for capture in sorted(facts.legal_captures, key=lambda c: c.move.uci):
        _require_square(capture.landing_square, "legal capture landing")
        captures[capture.landing_square].append(capture)
    return tuple(
        SquareAccess(
            square=square,
            occupant=pieces.get(square),
            white_attackers=tuple(a for a in attackers[square] if a.color is Color.WHITE),
            black_attackers=tuple(a for a in attackers[square] if a.color is Color.BLACK),
            current_legal_captures=tuple(captures[square]),
        )
        for square in SQUARES
    )


def project_piece_geometry(
    facts: PositionFacts,
) -> tuple[tuple[PieceRef, tuple[str, ...], tuple[tuple[str, ...], ...]], ...]:
    """Per piece: footprint and its (empty, friendly, enemy) partitions, in board order."""
    pieces = _source_piece_map(facts)
    footprints = _source_footprints(facts, pieces)
    result = []
    for piece in sorted(footprints, key=lambda p: square_index(p.square)):
        footprint = footprints[piece]
        kinds = {t: _target_kind(piece, pieces.get(t)) for t in footprint}
        parts = tuple(tuple(t for t in footprint if kinds[t] is k) for k in AttackTargetKind)
        result.append((piece, footprint, parts))
    return tuple(result)


def project_slider_rays(facts: PositionFacts) -> tuple[SliderRay, ...]:
    """Every applicable ray of every slider, checked against its P4 attack footprint."""
    pieces = _source_piece_map(facts)
    footprints = _source_footprints(facts, pieces)
    rays = []
    for piece in sorted(footprints, key=lambda p: square_index(p.square)):
        directions = SLIDER_DIRECTIONS.get(piece.piece_type)
        if directions is None:
            continue
        own = []
        for direction in directions:
            path = ray_path(piece.square, direction)
            own.append(
                SliderRay(piece, direction, path, tuple(pieces[s] for s in path if s in pieces))
            )
        visible = {s for ray in own for s in ray.visible_squares}
        if _canonical_squares(visible) != footprints[piece]:
            raise _fail("slider ray visibility disagrees with the P4 attack footprint")
        rays.extend(own)
    return tuple(rays)


def _direction_towards(source: str, target: str) -> Direction:
    df = ord(target[0]) - ord(source[0])
    dr = int(target[1]) - int(source[1])
    return ((df > 0) - (df < 0), (dr > 0) - (dr < 0))


@dataclass(frozen=True, slots=True)
class ActivityFacts:
    """activity_v1 observations of one position, validated against their P4 anchor."""

    source_facts: PositionFacts
    position_id: str
    side_to_move: Color
    squares: tuple[SquareAccess, ...]
    pieces: tuple[PieceActivity, ...]
    rays: tuple[SliderRay, ...]
    absolute_pins: tuple[AbsolutePin, ...]
    definition_version: str = ACTIVITY_DEFINITION_VERSION

    def __post_init__(self) -> None:
        if self.definition_version != ACTIVITY_DEFINITION_VERSION:
            raise _fail("unsupported activity definition version")
        if self.position_id != self.source_facts.position_id:
            raise _fail("activity facts belong to a different position")
        if self.squares != project_square_access(self.source_facts):
            raise _fail("square access disagrees with the source facts")
        geometry = project_piece_geometry(self.source_facts)
        if len(self.pieces) != len(geometry):
            raise _fail("activity must contain every observed piece exactly once")
        captures_by_piece: dict[PieceRef, list[LegalCapture]] = {}
        for capture in sorted(self.source_facts.legal_captures, key=lambda c: c.move.uci):
            captures_by_piece.setdefault(capture.capturer, []).append(capture)
        for activity, (piece, footprint, parts) in zip(self.pieces, geometry, strict=True):
            if (activity.piece, activity.footprint) != (piece, footprint) or (
                activity.empty_attacks,
                activity.friendly_attacks,
                activity.enemy_attacks,
            ) != parts:
                raise _fail("piece activity disagrees with the source facts")
            if (activity.legal_moves_now is None) is (piece.color is self.side_to_move):
                raise _fail("only side-to-move pieces carry legal-action observations")
            if activity.legal_captures_now is not None and activity.legal_captures_now != tuple(
                captures_by_piece.get(piece, ())
            ):
                raise _fail("piece captures disagree with the source legal captures")
        if self.rays != project_slider_rays(self.source_facts):
            raise _fail("slider rays disagree with the source facts")
        pinned = [p.pinned for p in self.absolute_pins]
        _require_canonical_pieces(tuple(pinned), "absolutely pinned pieces")
        live = {s.piece for s in self.source_facts.pieces}
        rays = {(r.source, r.direction): r for r in self.rays}
        for pin in self.absolute_pins:
            if not {pin.pinner, pin.pinned, pin.king} <= live:
                raise _fail("absolute pin references a piece outside the observed position")
            ray = rays.get((pin.pinner, _direction_towards(pin.pinner.square, pin.king.square)))
            if ray is None or ray.occupants[:2] != (pin.pinned, pin.king):
                raise _fail("absolute pin disagrees with the pinner's ray occupants")


@dataclass(frozen=True, slots=True)
class ActivityPositionAnalysis:
    structural: PositionAnalysis
    activity: ActivityFacts

    def __post_init__(self) -> None:
        position = self.structural.position
        if not (
            position.position_id
            == self.structural.facts.position_id
            == self.structural.features.position_id
            == self.activity.position_id
        ):
            raise _fail("activity and structural analysis belong to different positions")
        if self.structural.features.definition_version != POSITIONAL_DEFINITION_VERSION:
            raise _fail("unsupported positional definition version")
        if self.activity.source_facts != self.structural.facts:
            raise _fail("activity is anchored to different facts than the structural frame")
        if self.activity.side_to_move is not position.side_to_move:
            raise _fail("activity side to move disagrees with the position")


@dataclass(frozen=True, slots=True)
class TargetOccupancyChange:
    """A target square stayed in the footprint but its occupancy class changed."""

    square: str
    before: AttackTargetKind
    after: AttackTargetKind

    def __post_init__(self) -> None:
        _require_square(self.square, "occupancy change")
        if self.before is self.after:
            raise _fail("occupancy change must change the occupancy class")


@dataclass(frozen=True, slots=True)
class AttackFootprintChange:
    """One physical piece's footprint across a move; None covers capture.

    Target-square changes are geometry, not improvement; counts may stay equal.
    """

    before: PieceRef
    after: PieceRef | None
    added_targets: tuple[str, ...]
    removed_targets: tuple[str, ...]
    occupancy_changes: tuple[TargetOccupancyChange, ...]

    def __post_init__(self) -> None:
        _require_canonical_squares(self.added_targets, "added targets")
        _require_canonical_squares(self.removed_targets, "removed targets")


@dataclass(frozen=True, slots=True)
class RayChange:
    """One physical slider's ray in one direction; None covers capture or promotion.

    ``blockers_changed`` compares physical identities through P5 correspondence, so a
    relocated blocker is not reported as a different piece. A change is not a line claim.
    """

    direction: Direction
    before: SliderRay | None
    after: SliderRay | None
    added_visible: tuple[str, ...]
    removed_visible: tuple[str, ...]
    blockers_changed: bool

    def __post_init__(self) -> None:
        _require_canonical_squares(self.added_visible, "added visible squares")
        _require_canonical_squares(self.removed_visible, "removed visible squares")


@dataclass(frozen=True, slots=True)
class ActivityTransitionAnalysis:
    structural: TransitionAnalysis
    before_activity: ActivityPositionAnalysis
    after_activity: ActivityPositionAnalysis
    attack_footprint_changes: tuple[AttackFootprintChange, ...]
    ray_changes: tuple[RayChange, ...]

    def __post_init__(self) -> None:
        if (
            self.before_activity.structural != self.structural.before
            or self.after_activity.structural != self.structural.after
        ):
            raise _fail("activity frames do not bind the structural transition")


@dataclass(frozen=True, slots=True)
class ActivityLineAnalysis:
    """Activity at every structural frame and for every structural step of a supplied line."""

    structural: LineAnalysis
    activity_frames: tuple[ActivityPositionAnalysis, ...]
    activity_transitions: tuple[ActivityTransitionAnalysis, ...]

    def __post_init__(self) -> None:
        frames = (self.structural.initial, *(t.after for t in self.structural.transitions))
        if len(self.activity_frames) != len(frames) or any(
            a.structural != f for a, f in zip(self.activity_frames, frames, strict=False)
        ):
            raise _fail("activity frames do not match the structural line frames")
        if self.structural.final != frames[-1]:
            raise _fail("structural line final frame is inconsistent")
        if len(self.activity_transitions) != len(self.structural.transitions) or any(
            step.structural != t
            or step.before_activity != self.activity_frames[i]
            or step.after_activity != self.activity_frames[i + 1]
            for i, (step, t) in enumerate(
                zip(self.activity_transitions, self.structural.transitions, strict=False)
            )
        ):
            raise _fail("activity steps do not match the structural line transitions")
