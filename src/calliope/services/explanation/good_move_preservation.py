"""P9 ONLY_MOVE_CANDIDATE preservation rules over verified Batch-A replay evidence.

Pure policy: no engine access and no rules-library access.  The question is which concrete
failure the representative alternatives suffer that the played move avoids; the answer never
claims literal uniqueness.  Only Batch-A lines are read: an externally attached Batch B is
ignored.  P7 scores are inspected for mate only; material comes from exact I4 evidence.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from calliope.domain.analysis import (
    AlternativeScope,
    BasePieceRef,
    BoardDelta,
    GoodMoveBenefitKind,
    GoodMoveBenefitResult,
    GoodMoveBenefitStatus,
    GoodMoveExplanationResult,
    GoodMoveExplanationStatus,
    GoodMoveMode,
    MateEvidenceLevel,
    PieceTransitionKind,
    RepresentativeAlternative,
    TacticalCandidate,
    TacticalCandidateKind,
)
from calliope.domain.chess import Color, PieceType
from calliope.errors import IncompatibleGoodMoveContextError
from calliope.services.explanation.good_move_benefits import (
    base_key,
    base_ref,
    establishes_mate,
    replay_mates_for,
)

if TYPE_CHECKING:
    from calliope.services.explanation.good_move import (
        GoodMoveAlternativeLineEvidence,
        GoodMoveLineEvidence,
        GoodMovePreparedContext,
        GoodMoveReplayContext,
        GoodMoveReplayedLineContext,
    )

_K = GoodMoveBenefitKind
_S = GoodMoveBenefitStatus
_TK = TacticalCandidateKind
_KIND_ORDER = {kind: index for index, kind in enumerate(GoodMoveBenefitKind)}


def _fail(message: str) -> IncompatibleGoodMoveContextError:
    return IncompatibleGoodMoveContextError(message)


def _unique[T](values: Iterable[T]) -> tuple[T, ...]:
    found: list[T] = []
    for value in values:
        if value not in found:
            found.append(value)
    return tuple(found)


def require_only_move(prepared: GoodMovePreparedContext) -> None:
    if prepared.mode is not GoodMoveMode.ONLY_MOVE_CANDIDATE:
        raise _fail("preservation rules require ONLY_MOVE_CANDIDATE mode")


def _mover_king(replay: GoodMoveReplayContext) -> BasePieceRef:
    deterministic = replay.counterfactual.deterministic
    mover = deterministic.prepared.base.side_to_move
    kings = [
        base
        for base in deterministic.root_identity.base_pieces
        if base.color is mover and base.piece_type is PieceType.KING
    ]
    if len(kings) != 1:
        raise _fail("mover king does not resolve uniquely in the base identity")
    return kings[0]


def _exact_immediate(line: GoodMoveReplayedLineContext, opponent: Color) -> bool:
    """The opponent's immediate reply to the alternative (ply 2) is exact checkmate."""

    return len(line.plies) == 2 and replay_mates_for(line, opponent)


def _deficit(evidence: GoodMoveLineEvidence) -> int | None:
    """Stable mover deficit D = max(0, -delta); None while the line is incomplete."""

    material = evidence.material
    if material.stable_at_ply is None:
        return None
    return max(0, -material.material_delta)


def _negative_events(
    line: GoodMoveReplayedLineContext, mover: Color
) -> tuple[tuple[BoardDelta, BasePieceRef], ...]:
    """Exact events lowering the mover's material: own pieces captured, opponent promotions."""

    events = []
    for step in line.plies:
        capture = step.delta.capture
        if capture is not None and capture.captured.color is mover:
            events.append((step.delta, base_ref(step.before_identity, capture.captured)))
        for transition in step.delta.transitions:
            if (
                transition.kind is PieceTransitionKind.PROMOTION
                and transition.after.color is mover.opposite
            ):
                events.append((step.delta, base_ref(step.before_identity, transition.before)))
    return tuple(events)


class _Rules:
    def __init__(self, replay: GoodMoveReplayContext) -> None:
        self.replay = replay
        self.prepared = replay.counterfactual.deterministic.prepared
        self.mover = self.prepared.base.side_to_move
        self.alternatives: tuple[GoodMoveAlternativeLineEvidence, ...] = replay.alternatives
        # Batch A only, in representative rank order; Batch B is never preservation evidence.
        self.probes = (
            replay.played.line.probe_result,
            *(a.evidence.line.probe_result for a in self.alternatives),
        )

    def benefit(
        self,
        kind: GoodMoveBenefitKind,
        status: GoodMoveBenefitStatus,
        subject: tuple[BasePieceRef, ...],
        failed: tuple[RepresentativeAlternative, ...],
        equivalent: bool | None,
        **evidence: object,
    ) -> GoodMoveBenefitResult:
        return GoodMoveBenefitResult(
            kind=kind,
            status=status,
            mode=GoodMoveMode.ONLY_MOVE_CANDIDATE,
            subject=subject,
            base_position_id=self.prepared.base.position_id,
            played_move=self.prepared.played_move,
            alternatives=self.prepared.alternatives,
            failed_alternatives=failed,
            probe_results=self.probes,
            equivalent_alternative_benefit=equivalent,
            alternative_scope=AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES,
            **evidence,  # type: ignore[arg-type]
        )

    # -- PREVENTS_MATE --

    def prevents_mate(self) -> GoodMoveBenefitResult | None:
        opponent = self.mover.opposite
        failed = tuple(a for a in self.alternatives if establishes_mate(a.evidence.line, opponent))
        if not failed:
            return None
        lines = [a.evidence.line for a in failed]
        exact = all(replay_mates_for(line, opponent) for line in lines)
        level = (
            MateEvidenceLevel.EXACT_IMMEDIATE
            if all(_exact_immediate(line, opponent) for line in lines)
            else MateEvidenceLevel.ENGINE_LINE
        )
        mated = [line.final for line in lines if replay_mates_for(line, opponent)]
        candidates: tuple[TacticalCandidate, ...] = _unique(
            candidate
            for step in mated
            for candidate in step.detection.candidates
            if candidate.kind in (_TK.CHECK, _TK.CHECKMATE)
        )
        status = _S.REFUTED if establishes_mate(self.replay.played.line, opponent) else _S.SUPPORTED
        king = _mover_king(self.replay)
        return self.benefit(
            _K.PREVENTS_MATE,
            status,
            (king,),
            tuple(a.alternative for a in failed),
            len(failed) < len(self.alternatives),
            affected_pieces=(king,),
            board_deltas=_unique(step.delta for step in mated),
            tactical_candidates=candidates,
            mate_evidence_level=level,
            replayed_pv_ends_in_checkmate=exact,
        )

    # -- PREVENTS_MATERIAL_LOSS --

    def prevents_material_loss(self) -> GoodMoveBenefitResult | None:
        deficits = [(a, _deficit(a.evidence)) for a in self.alternatives]
        losing = [a for a, deficit in deficits if deficit is not None and deficit > 0]
        if not losing:
            return None

        played = _deficit(self.replay.played)
        incomplete = played is None or any(deficit is None for _, deficit in deficits)
        failed: tuple[GoodMoveAlternativeLineEvidence, ...] = ()
        if played is not None:
            failed = tuple(a for a, deficit in deficits if deficit is not None and deficit > played)
        if incomplete:
            status, equivalent = _S.INCONCLUSIVE, None
        elif failed:
            status = _S.SUPPORTED
            equivalent = len(failed) < len(self.alternatives)
        else:
            status, equivalent = _S.REFUTED, True

        sources = failed or tuple(losing)
        events = []
        for alternative in sources:
            found = _negative_events(alternative.evidence.line, self.mover)
            if not found:
                raise _fail("stable material deficit has no exact negative material event")
            events.extend(found)
        subject = tuple(sorted({base for _, base in events}, key=base_key))
        return self.benefit(
            _K.PREVENTS_MATERIAL_LOSS,
            status,
            subject,
            tuple(a.alternative for a in failed),
            equivalent,
            affected_pieces=subject,
            board_deltas=_unique(delta for delta, _ in events),
            material_evidence=(
                self.replay.played.material,
                *(a.evidence.material for a in self.alternatives),
            ),
        )


def _result(
    prepared: GoodMovePreparedContext,
    status: GoodMoveExplanationStatus,
    benefits: tuple[GoodMoveBenefitResult, ...],
) -> GoodMoveExplanationResult:
    return GoodMoveExplanationResult(
        status=status,
        base_position_id=prepared.base.position_id,
        played_move=prepared.played_move,
        mode=GoodMoveMode.ONLY_MOVE_CANDIDATE,
        alternatives=prepared.alternatives,
        alternative_scope=AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES,
        literal_only_move_proven=False,
        benefits=benefits,
    )


def no_alternative_only_move_result(
    prepared: GoodMovePreparedContext,
) -> GoodMoveExplanationResult:
    """No representative comparator: no preservation reason, and no uniqueness inference."""

    require_only_move(prepared)
    return _result(prepared, GoodMoveExplanationStatus.INCONCLUSIVE, ())


def evaluate_only_move(replay: GoodMoveReplayContext) -> GoodMoveExplanationResult:
    """Apply PREVENTS_MATE and PREVENTS_MATERIAL_LOSS; makes no P7 call."""

    prepared = replay.counterfactual.deterministic.prepared
    require_only_move(prepared)
    if not prepared.alternatives:
        return no_alternative_only_move_result(prepared)
    rules = _Rules(replay)
    found = (rules.prevents_mate(), rules.prevents_material_loss())
    benefits = tuple(
        sorted(
            (benefit for benefit in found if benefit is not None),
            key=lambda b: (_KIND_ORDER[b.kind], tuple(base_key(s) for s in b.subject)),
        )
    )
    statuses = {benefit.status for benefit in benefits}
    if _S.SUPPORTED in statuses:
        status = GoodMoveExplanationStatus.SUPPORTED
    elif benefits and statuses == {_S.REFUTED}:
        status = GoodMoveExplanationStatus.REFUTED
    else:
        status = GoodMoveExplanationStatus.INCONCLUSIVE
    return _result(prepared, status, benefits)
