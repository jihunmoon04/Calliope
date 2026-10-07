"""Compose base-position piece identity through verified board deltas.

P8 compares alternative branches by physical piece identity anchored to the common base
position. This helper is deterministic and engine-independent: it only consumes P4 facts and
P5 BoardDelta correspondences.
"""

from __future__ import annotations

from dataclasses import dataclass

from calliope.domain.analysis import BasePieceRef, BoardDelta, PieceTransitionKind
from calliope.domain.chess import PieceRef, PieceType, PositionFacts, square_index
from calliope.errors import IncompatibleBadMoveContextError


def _fail(message: str) -> IncompatibleBadMoveContextError:
    return IncompatibleBadMoveContextError(message)


def _base_key(base: BasePieceRef) -> tuple[int, str, str]:
    return (square_index(base.base_square), base.color.value, base.piece_type.value)


@dataclass(frozen=True, slots=True)
class BasePieceIdentityMap:
    """Map base-position pieces to their current branch piece, or to capture."""

    base_position_id: str
    position_id: str
    _entries: tuple[tuple[BasePieceRef, PieceRef | None], ...]

    def __post_init__(self) -> None:
        if not self.base_position_id or not self.position_id:
            raise _fail("identity-map position ids must not be empty")

        bases = tuple(base for base, _ in self._entries)
        if len(bases) != len(set(bases)):
            raise _fail("identity map contains duplicate base pieces")
        if len({base.base_square for base in bases}) != len(bases):
            raise _fail("identity map contains two base pieces on one base square")

        live = tuple(piece for _, piece in self._entries if piece is not None)
        if len(live) != len(set(live)):
            raise _fail("multiple base pieces map to the same current piece")
        if len({piece.square for piece in live}) != len(live):
            raise _fail("multiple base pieces occupy the same current square")

        for base, piece in self._entries:
            if piece is None:
                continue
            if piece.color is not base.color:
                raise _fail("current piece color differs from its base identity")
            if piece.piece_type is not base.piece_type and (
                base.piece_type is not PieceType.PAWN
                or piece.piece_type in (PieceType.PAWN, PieceType.KING)
            ):
                raise _fail("current piece type is incompatible with its base identity")

        if list(bases) != sorted(bases, key=_base_key):
            raise _fail("identity map entries are not in canonical base-square order")

    @classmethod
    def from_facts(cls, facts: PositionFacts) -> BasePieceIdentityMap:
        pieces = tuple(state.piece for state in facts.pieces)
        if len({piece.square for piece in pieces}) != len(pieces):
            raise _fail("base facts contain duplicate piece squares")
        if len(set(pieces)) != len(pieces):
            raise _fail("base facts contain duplicate pieces")

        entries = tuple(
            sorted(
                (
                    (BasePieceRef(piece.color, piece.piece_type, piece.square), piece)
                    for piece in pieces
                ),
                key=lambda item: _base_key(item[0]),
            )
        )
        return cls(
            base_position_id=facts.position_id,
            position_id=facts.position_id,
            _entries=entries,
        )

    @property
    def base_pieces(self) -> tuple[BasePieceRef, ...]:
        return tuple(base for base, _ in self._entries)

    @property
    def live_pieces(self) -> tuple[PieceRef, ...]:
        return tuple(piece for _, piece in self._entries if piece is not None)

    def current_piece(self, base: BasePieceRef) -> PieceRef | None:
        for candidate, piece in self._entries:
            if candidate == base:
                return piece
        raise _fail("base piece does not belong to this identity map")

    def base_ref_for(self, piece: PieceRef) -> BasePieceRef:
        matches = [base for base, current in self._entries if current == piece]
        if len(matches) != 1:
            raise _fail("current piece does not map uniquely to a base piece")
        return matches[0]

    def advance(self, delta: BoardDelta) -> BasePieceIdentityMap:
        """Apply one exact P5 delta and return the identity map for its after-position."""

        if delta.before_position_id != self.position_id:
            raise _fail("board delta does not continue from the current identity position")
        if not delta.after_position_id:
            raise _fail("board delta after_position_id must not be empty")

        current_by_base = dict(self._entries)
        live_to_base = {piece: base for base, piece in self._entries if piece is not None}
        if len(live_to_base) != len(self.live_pieces):
            raise _fail("multiple base pieces map to the same current piece")

        pairs = delta.piece_correspondence
        before_pieces = tuple(pair.before for pair in pairs)
        after_pieces = tuple(pair.after for pair in pairs)
        if len(set(before_pieces)) != len(before_pieces):
            raise _fail("board delta has duplicate before-piece correspondences")
        if len(set(after_pieces)) != len(after_pieces):
            raise _fail("board delta has duplicate after-piece correspondences")

        expected_before = set(live_to_base)
        accounted_before = set(before_pieces)

        captured = delta.capture.captured if delta.capture is not None else None
        if captured is not None:
            if delta.capture is None:
                raise AssertionError("unreachable")
            if delta.capture.capturer_before.color is delta.capture.captured.color:
                raise _fail("capture cannot remove a piece of the capturer's color")
            if delta.capture.captured_square != delta.capture.captured.square:
                raise _fail("capture captured_square disagrees with the captured piece")
            if delta.capture.capturer_after.square != delta.capture.landing_square:
                raise _fail("capture landing square disagrees with the surviving capturer")
            off_landing = delta.capture.captured_square != delta.capture.landing_square
            if off_landing is not delta.capture.is_en_passant:
                raise _fail("only en passant captures away from the landing square")
            if delta.capture.is_en_passant and not (
                delta.capture.capturer_before.piece_type is PieceType.PAWN
                and captured.piece_type is PieceType.PAWN
            ):
                raise _fail("en passant capture must be pawn takes pawn")
            if captured not in expected_before:
                raise _fail("captured piece is not live in the current identity map")
            if captured in accounted_before:
                raise _fail("captured piece also appears as a surviving correspondence")
            accounted_before.add(captured)

            capture_pairs = [
                pair
                for pair in pairs
                if pair.before == delta.capture.capturer_before
                and pair.after == delta.capture.capturer_after
            ]
            if len(capture_pairs) != 1:
                raise _fail("capture does not bind its capturer through piece correspondence")

        if accounted_before != expected_before:
            missing = expected_before - accounted_before
            extra = accounted_before - expected_before
            if missing:
                raise _fail("board delta leaves a live base piece unexplained")
            if extra:
                raise _fail("board delta references a piece outside the current identity map")

        transitions = {(t.before, t.after): t.kind for t in delta.transitions}
        if len(transitions) != len(delta.transitions):
            raise _fail("board delta has duplicate piece transitions")
        pair_keys = {(pair.before, pair.after) for pair in pairs}
        for transition in delta.transitions:
            if (transition.before, transition.after) not in pair_keys:
                raise _fail("piece transition has no matching correspondence")
            if transition.before.color is not transition.after.color:
                raise _fail("piece transition changes piece color")
            if transition.kind is PieceTransitionKind.PROMOTION:
                if (
                    transition.before.piece_type is not PieceType.PAWN
                    or transition.after.piece_type in (PieceType.PAWN, PieceType.KING)
                ):
                    raise _fail("invalid promotion transition")
            elif transition.before.piece_type is not transition.after.piece_type:
                raise _fail("non-promotion transition changes piece type")

        next_by_base = dict(current_by_base)
        for pair in pairs:
            base = live_to_base.get(pair.before)
            if base is None:
                raise _fail("piece correspondence starts from an unknown current piece")
            if pair.after.color is not pair.before.color:
                raise _fail("piece correspondence changes piece color")

            if pair.after.piece_type is not pair.before.piece_type:
                kind = transitions.get((pair.before, pair.after))
                if (
                    kind is not PieceTransitionKind.PROMOTION
                    or pair.before.piece_type is not PieceType.PAWN
                ):
                    raise _fail("piece type changes without a promotion transition")

            next_by_base[base] = pair.after

        if captured is not None:
            next_by_base[live_to_base[captured]] = None

        next_live = [piece for piece in next_by_base.values() if piece is not None]
        if len(next_live) != len(set(next_live)):
            raise _fail("multiple base pieces map to the same after-position piece")

        entries = tuple((base, next_by_base[base]) for base in sorted(next_by_base, key=_base_key))
        return BasePieceIdentityMap(
            base_position_id=self.base_position_id,
            position_id=delta.after_position_id,
            _entries=entries,
        )

    def advance_all(self, deltas: tuple[BoardDelta, ...]) -> BasePieceIdentityMap:
        """Compose identity through every P5 delta in one replayed branch."""

        current = self
        for delta in deltas:
            current = current.advance(delta)
        return current
