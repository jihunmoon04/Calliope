"""Detect tactical pattern candidates from exact facts, board delta and rule observations.

Pure deterministic policy.  Every candidate is DETECTED: nothing here verifies a tactic,
assigns a cause, or evaluates a position.
"""

from __future__ import annotations

from dataclasses import dataclass

from calliope.application.ports.tactics import TacticalObservation
from calliope.domain.analysis import (
    BoardDelta,
    CheckChangeKind,
    TacticalCandidate,
    TacticalCandidateKind,
    TacticalCandidateStatus,
    TacticalDetection,
)
from calliope.domain.chess import (
    ChessMove,
    PieceRef,
    PieceState,
    PieceType,
    PositionFacts,
    square_index,
)
from calliope.errors import IncompatibleTacticalContextError

_KIND = TacticalCandidateKind
_DETECTED = TacticalCandidateStatus.DETECTED


def _fail(message: str) -> IncompatibleTacticalContextError:
    return IncompatibleTacticalContextError(message)


def _pieces(pieces: set[PieceRef] | list[PieceRef] | tuple[PieceRef, ...]) -> tuple[PieceRef, ...]:
    return tuple(sorted(set(pieces), key=lambda p: square_index(p.square)))


def _candidate(
    kind: TacticalCandidateKind,
    *,
    actors=(),
    targets=(),
    related=(),
    responses: tuple[ChessMove, ...] = (),
) -> TacticalCandidate:
    return TacticalCandidate(
        kind=kind,
        status=_DETECTED,
        actors=_pieces(actors),
        targets=_pieces(targets),
        related=_pieces(related),
        responses=tuple(sorted(responses, key=lambda m: m.uci)),
    )


def _sort_key(c: TacticalCandidate):
    def squares(pieces: tuple[PieceRef, ...]) -> tuple[int, ...]:
        return tuple(square_index(p.square) for p in pieces)

    return (
        c.kind.value,
        squares(c.actors),
        squares(c.targets),
        squares(c.related),
        tuple(m.uci for m in c.responses),
    )


@dataclass(slots=True)
class TacticalDetector:
    def detect(
        self,
        *,
        before: PositionFacts,
        after: PositionFacts,
        delta: BoardDelta,
        before_rules: TacticalObservation,
        after_rules: TacticalObservation,
    ) -> TacticalDetection:
        self._validate(before, after, delta, before_rules, after_rules)

        after_by_square = {s.piece.square: s for s in after.pieces}
        candidates: set[TacticalCandidate] = set()

        candidates.update(self._checks(after, delta, after_rules))
        candidates.update(self._hanging(after))
        attack_candidates = self._attacks(after_by_square, delta)
        candidates.update(attack_candidates)
        candidates.update(self._pins(before_rules, after_rules, delta))
        candidates.update(self._removals(after_by_square, delta))
        candidates.update(self._forced(after, after_rules))

        return TacticalDetection(
            before_position_id=delta.before_position_id,
            after_position_id=delta.after_position_id,
            move=delta.move,
            mover=delta.mover,
            candidates=tuple(sorted(candidates, key=_sort_key)),
        )

    # ---- context ---------------------------------------------------------------------

    @staticmethod
    def _validate(
        before: PositionFacts,
        after: PositionFacts,
        delta: BoardDelta,
        before_rules: TacticalObservation,
        after_rules: TacticalObservation,
    ) -> None:
        if not (before.position_id == delta.before_position_id == before_rules.position_id):
            raise _fail("before position ids are not aligned")
        if not (after.position_id == delta.after_position_id == after_rules.position_id):
            raise _fail("after position ids are not aligned")
        if before_rules.side_to_move is not delta.mover:
            raise _fail("before observation side to move differs from the mover")
        if after_rules.side_to_move is not delta.mover.opposite:
            raise _fail("after observation side to move differs from the opponent")

        in_check_no_moves = after.side_to_move_in_check and not after_rules.legal_moves
        if after.side_to_move_checkmated != in_check_no_moves:
            raise _fail("after checkmate state disagrees with check state and legal moves")

        for rules, facts in ((before_rules, before), (after_rules, after)):
            present = {s.piece for s in facts.pieces}
            for pin in rules.absolute_pins:
                if not {pin.pinner, pin.pinned, pin.king} <= present:
                    raise _fail("pin references a piece that is not in the position")
                if (
                    pin.pinner.color is pin.pinned.color
                    or pin.pinned.color is not pin.king.color
                    or pin.king.piece_type is not PieceType.KING
                ):
                    raise _fail("pin piece colors are inconsistent")

    # ---- check / checkmate -------------------------------------------------------------

    @staticmethod
    def _checks(
        after: PositionFacts, delta: BoardDelta, after_rules: TacticalObservation
    ) -> list[TacticalCandidate]:
        created = any(
            c.kind is CheckChangeKind.CREATED and c.checked_color is delta.mover.opposite
            for c in delta.check_changes
        )
        if created != after.side_to_move_in_check:
            raise _fail("delta check change disagrees with after facts")
        if not created:
            return []
        king = next(
            (
                s
                for s in after.pieces
                if s.piece.piece_type is PieceType.KING and s.piece.color is delta.mover.opposite
            ),
            None,
        )
        if king is None:
            raise _fail("checked king not found")
        checkers = [a for a in king.attacked_by if a.color is delta.mover]
        if not checkers:
            raise _fail("check created but no checking piece found")
        kind = _KIND.CHECKMATE if after.side_to_move_checkmated else _KIND.CHECK
        return [_candidate(kind, actors=checkers, targets=(king.piece,))]

    # ---- hanging -----------------------------------------------------------------------

    @staticmethod
    def _hanging(after: PositionFacts) -> list[TacticalCandidate]:
        result = []
        for state in after.pieces:
            if not state.hanging_now or state.piece.piece_type is PieceType.KING:
                continue
            capturers = [c.capturer for c in after.legal_captures if c.captured == state.piece]
            if not capturers:
                raise _fail("hanging piece has no legal capturer")
            result.append(_candidate(_KIND.HANGING_PIECE, actors=capturers, targets=(state.piece,)))
        return result

    # ---- attacks -----------------------------------------------------------------------

    @staticmethod
    def _attacks(
        after_by_square: dict[str, PieceState], delta: BoardDelta
    ) -> list[TacticalCandidate]:
        def enemy_at(attacker: PieceRef, square: str) -> PieceRef | None:
            state = after_by_square.get(square)
            if state is None or state.piece.color is attacker.color:
                return None
            return state.piece

        result: list[TacticalCandidate] = []
        new_pairs = [(c.attacker, enemy_at(c.attacker, c.target_square)) for c in delta.new_attacks]
        new_pairs = [(a, t) for a, t in new_pairs if t is not None]

        for attacker, target in new_pairs:
            if target.piece_type is not PieceType.KING:
                result.append(
                    _candidate(_KIND.DIRECT_ATTACK, actors=(attacker,), targets=(target,))
                )

        # forks: all enemy pieces attacked by one piece, at least one relation newly created
        new_relations = {(a, t) for a, t in new_pairs}
        attacked_after: dict[PieceRef, set[PieceRef]] = {}
        for state in after_by_square.values():
            for target_square in state.attacks:
                target = enemy_at(state.piece, target_square)
                if target is not None:
                    attacked_after.setdefault(state.piece, set()).add(target)
        fork_actors = set()
        for actor, targets in attacked_after.items():
            if len(targets) >= 2 and any((actor, t) in new_relations for t in targets):
                fork_actors.add(actor)
                result.append(_candidate(_KIND.FORK, actors=(actor,), targets=targets))

        # double attack: distinct non-fork actors with new relations onto distinct targets
        for color in {a.color for a, _ in new_pairs}:
            relations = [(a, t) for a, t in new_pairs if a.color is color and a not in fork_actors]
            actors = {a for a, _ in relations}
            targets = {t for _, t in relations}
            if len(actors) >= 2 and len(targets) >= 2:
                result.append(_candidate(_KIND.DOUBLE_ATTACK, actors=actors, targets=targets))
        return result

    # ---- absolute pins -----------------------------------------------------------------

    @staticmethod
    def _pins(
        before_rules: TacticalObservation,
        after_rules: TacticalObservation,
        delta: BoardDelta,
    ) -> list[TacticalCandidate]:
        to_before = {c.after: c.before for c in delta.piece_correspondence}
        existing = {(p.pinner, p.pinned, p.king) for p in before_rules.absolute_pins}
        result = []
        for pin in after_rules.absolute_pins:
            try:
                key = (to_before[pin.pinner], to_before[pin.pinned], to_before[pin.king])
            except KeyError:
                raise _fail(
                    "after pin references a piece without a before correspondence"
                ) from None
            if key in existing:
                continue
            result.append(
                _candidate(
                    _KIND.ABSOLUTE_PIN,
                    actors=(pin.pinner,),
                    targets=(pin.pinned,),
                    related=(pin.king,),
                )
            )
        return result

    # ---- removal of defender -------------------------------------------------------------

    @staticmethod
    def _removals(
        after_by_square: dict[str, PieceState], delta: BoardDelta
    ) -> list[TacticalCandidate]:
        capture = delta.capture
        if capture is None:
            return []
        to_after = {c.before: c.after for c in delta.piece_correspondence}
        result = []
        for removed in delta.removed_defenses:
            if removed.defender != capture.captured:
                continue
            survivor = to_after.get(removed.defended)
            if survivor is None:
                continue
            state = after_by_square.get(survivor.square)
            if state is None or state.piece != survivor:
                raise _fail("surviving defended piece missing from after facts")
            if not state.attacked_by:
                continue
            result.append(
                _candidate(
                    _KIND.REMOVAL_OF_DEFENDER,
                    actors=(capture.capturer_after,),
                    targets=(survivor,),
                    related=(capture.captured,),
                )
            )
        return result

    # ---- forced response ---------------------------------------------------------------

    @staticmethod
    def _forced(after: PositionFacts, after_rules: TacticalObservation) -> list[TacticalCandidate]:
        if after.side_to_move_checkmated or len(after_rules.legal_moves) != 1:
            return []
        return [_candidate(_KIND.FORCED_RESPONSE, responses=after_rules.legal_moves)]
