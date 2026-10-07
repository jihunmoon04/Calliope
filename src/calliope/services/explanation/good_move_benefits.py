"""P9 STRONG_MOVE benefit rules over verified, deterministically replayed evidence.

Pure policy: no engine access and no rules-library access.  Inputs are the I4 replay context
and, optionally, the cause-specific ignored-response threat that the explainer selected with
exact rules.  Only P7 outcomes from the same context are compared; P3 numbers are never read.
Prevention benefits (PREVENTS_MATE, PREVENTS_MATERIAL_LOSS) belong to ONLY_MOVE_CANDIDATE mode
and are not produced here.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from calliope.domain.analysis import (
    AlternativeScope,
    BasePieceRef,
    GoodMoveBenefitKind,
    GoodMoveBenefitResult,
    GoodMoveBenefitStatus,
    GoodMoveExplanationResult,
    GoodMoveExplanationStatus,
    GoodMoveMode,
    MateEvidenceLevel,
    MaterialLineEvidence,
    PieceTransitionKind,
    ProbeResult,
    TacticalCandidate,
    TacticalCandidateKind,
    TerminalKind,
)
from calliope.domain.chess import Color, PieceRef, PieceType, square_index
from calliope.errors import IncompatibleBadMoveContextError, IncompatibleGoodMoveContextError
from calliope.services.explanation.piece_identity import BasePieceIdentityMap

if TYPE_CHECKING:
    from calliope.domain.chess import ChessMove
    from calliope.services.explanation.good_move import (
        GoodMovePreparedContext,
        GoodMoveReplayContext,
        GoodMoveReplayedLineContext,
        GoodMoveReplayStepContext,
    )

_K = GoodMoveBenefitKind
_S = GoodMoveBenefitStatus
_TK = TacticalCandidateKind

STRONG_MOVE_KINDS = (_K.FORCES_RESPONSE, _K.MATE_THREAT, _K.MATERIAL_THREAT)
# P6 kinds that may seed an ignored-response material threat, in declaration order.
MATERIAL_RESOURCE_KINDS = (_TK.DIRECT_ATTACK, _TK.FORK, _TK.DOUBLE_ATTACK)
_KIND_ORDER = {kind: index for index, kind in enumerate(GoodMoveBenefitKind)}


def _fail(message: str) -> IncompatibleGoodMoveContextError:
    return IncompatibleGoodMoveContextError(message)


def base_key(base: BasePieceRef) -> tuple[int, str, str]:
    return (square_index(base.base_square), base.color.value, base.piece_type.value)


def _sorted_bases(bases: Iterable[BasePieceRef]) -> tuple[BasePieceRef, ...]:
    return tuple(sorted(set(bases), key=base_key))


def base_ref(identity: BasePieceIdentityMap, piece: PieceRef) -> BasePieceRef:
    """Base identity of a current piece; P8 identity errors become P9 errors."""

    try:
        return identity.base_ref_for(piece)
    except IncompatibleBadMoveContextError as error:
        raise _fail("piece does not map to a base identity") from error


@dataclass(frozen=True, slots=True)
class GoodMoveMaterialResource:
    """A mover P6 attack resource normalized to base identity; kings are never targets."""

    candidate: TacticalCandidate
    actors: tuple[BasePieceRef, ...]
    targets: tuple[BasePieceRef, ...]


@dataclass(frozen=True, slots=True)
class GoodMoveTestedThreat:
    """A cause-specific ignored response Q chosen by exact rules, never by engine score."""

    kind: GoodMoveBenefitKind
    response: ChessMove
    resource: GoodMoveMaterialResource | None = None

    def __post_init__(self) -> None:
        if self.kind is _K.MATE_THREAT:
            if self.resource is not None:
                raise ValueError("a mate threat carries no material resource")
        elif self.kind is _K.MATERIAL_THREAT:
            if self.resource is None:
                raise ValueError("a material threat requires its P6 resource")
        else:
            raise ValueError("tested threats are MATE_THREAT or MATERIAL_THREAT only")


# ---- P7 outcome ordering ---------------------------------------------------------------------


def outcome_key(result: ProbeResult, mover: Color) -> tuple[int, int] | None:
    """Mate-aware total order key from the mover's view; None (incomparable) for stalemate.

    Rank 2 is a mover-winning mate (shorter is better), rank 1 a centipawn score, rank 0 a
    mover-losing mate (later is better).  An exact checkmate is a mate at distance zero.
    """

    if result.terminal is not None:
        if result.terminal.kind is TerminalKind.STALEMATE:
            return None
        return (2, 0) if result.terminal.winner is mover else (0, 0)
    if result.engine_analysis is None:
        raise _fail("P7 result has neither terminal nor engine evidence")
    score = result.engine_analysis.best_line.score
    if score.mate is not None:
        moves = score.mate.moves
        return (2, -moves) if score.mate.winner is mover else (0, moves)
    centipawns = score.centipawns_for(mover)
    if centipawns is None:
        raise _fail("P7 score has neither mate nor centipawns")
    return (1, centipawns)


# ---- shared evidence predicates --------------------------------------------------------------


def replay_mates_for(line: GoodMoveReplayedLineContext, mover: Color) -> bool:
    """The exact replay ends in checkmate of the mover's opponent."""

    return line.ends_in_checkmate and line.final.position.side_to_move is mover.opposite


def engine_mates_for(result: ProbeResult, mover: Color) -> bool:
    analysis = result.engine_analysis
    if analysis is None:
        return False
    mate = analysis.best_line.score.mate
    return mate is not None and mate.winner is mover


def establishes_mate(line: GoodMoveReplayedLineContext, mover: Color) -> bool:
    """Verified mover-winning mate: exact replayed checkmate or a P7 mate score."""

    return replay_mates_for(line, mover) or engine_mates_for(line.probe_result, mover)


def positive_material_events(
    line: GoodMoveReplayedLineContext, mover: Color
) -> tuple[tuple[GoodMoveReplayStepContext, BasePieceRef], ...]:
    """Exact events that raise the mover's material: opponent captures and own promotions."""

    events = []
    for step in line.plies:
        capture = step.delta.capture
        if capture is not None and capture.captured.color is mover.opposite:
            events.append((step, base_ref(step.before_identity, capture.captured)))
        for transition in step.delta.transitions:
            if transition.kind is PieceTransitionKind.PROMOTION and transition.after.color is mover:
                events.append((step, base_ref(step.before_identity, transition.before)))
    return tuple(events)


def has_direct_mate(replay: GoodMoveReplayContext) -> bool:
    mover = replay.counterfactual.deterministic.prepared.base.side_to_move
    return establishes_mate(replay.played.line, mover)


def has_direct_material(replay: GoodMoveReplayContext) -> bool:
    material = replay.played.material
    return material.stable_at_ply is not None and material.material_delta > 0


def material_resources(
    step: GoodMoveReplayStepContext, mover: Color
) -> tuple[GoodMoveMaterialResource, ...]:
    """Mover attack resources created by M, base-normalized and in deterministic order."""

    kind_order = {kind: index for index, kind in enumerate(MATERIAL_RESOURCE_KINDS)}
    resources = []
    for candidate in step.detection.candidates:
        if candidate.kind not in kind_order:
            continue
        colors = {actor.color for actor in candidate.actors}
        if len(colors) != 1:
            raise _fail("tactical resource has actors of both colors")
        if colors != {mover}:
            continue  # an opponent resource is not a threat by the mover
        if any(target.color is mover for target in candidate.targets):
            raise _fail("mover tactical resource targets the mover's own piece")
        actors = _sorted_bases(base_ref(step.identity, actor) for actor in candidate.actors)
        targets = _sorted_bases(
            base_ref(step.identity, target)
            for target in candidate.targets
            if target.piece_type is not PieceType.KING
        )
        if targets:
            resources.append(GoodMoveMaterialResource(candidate, actors, targets))
    return tuple(
        sorted(
            resources,
            key=lambda r: (
                kind_order[r.candidate.kind],
                tuple(base_key(b) for b in r.actors),
                tuple(base_key(b) for b in r.targets),
            ),
        )
    )


def opponent_king(replay: GoodMoveReplayContext) -> BasePieceRef:
    deterministic = replay.counterfactual.deterministic
    opponent = deterministic.prepared.base.side_to_move.opposite
    kings = [
        base
        for base in deterministic.root_identity.base_pieces
        if base.color is opponent and base.piece_type is PieceType.KING
    ]
    if len(kings) != 1:
        raise _fail("opponent king does not resolve uniquely in the base identity")
    return kings[0]


# ---- benefit rules ---------------------------------------------------------------------------


def _status(equivalents: Iterable[bool | None]) -> tuple[GoodMoveBenefitStatus, bool | None]:
    flags = tuple(equivalents)
    if any(flag is True for flag in flags):
        return _S.REFUTED, True
    if any(flag is None for flag in flags):
        return _S.INCONCLUSIVE, None
    return _S.SUPPORTED, False


@dataclass(frozen=True, slots=True)
class _Rules:
    replay: GoodMoveReplayContext
    tested: GoodMoveTestedThreat | None

    @property
    def prepared(self) -> GoodMovePreparedContext:
        return self.replay.counterfactual.deterministic.prepared

    @property
    def mover(self) -> Color:
        return self.prepared.base.side_to_move

    def batch_a_results(self) -> tuple[ProbeResult, ...]:
        return (
            self.replay.played.line.probe_result,
            *(a.evidence.line.probe_result for a in self.replay.alternatives),
        )

    def benefit(
        self,
        kind: GoodMoveBenefitKind,
        status: GoodMoveBenefitStatus,
        subject: tuple[BasePieceRef, ...],
        equivalent: bool | None,
        **evidence: object,
    ) -> GoodMoveBenefitResult:
        prepared = self.prepared
        return GoodMoveBenefitResult(
            kind=kind,
            status=status,
            mode=GoodMoveMode.STRONG_MOVE,
            subject=subject,
            base_position_id=prepared.base.position_id,
            played_move=prepared.played_move,
            alternatives=prepared.alternatives,
            equivalent_alternative_benefit=equivalent,
            alternative_scope=AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES,
            **evidence,  # type: ignore[arg-type]
        )

    # -- FORCES_RESPONSE --

    def forces_response(self) -> GoodMoveBenefitResult | None:
        first = self.replay.played.line.plies[0]
        legal = first.rules.legal_moves
        forced = [c for c in first.detection.candidates if c.kind is _TK.FORCED_RESPONSE]
        if len(legal) != 1 or first.facts.side_to_move_checkmated:
            if forced:
                raise _fail("P6 forced response contradicts the exact legal-move count")
            return None
        if len(forced) != 1 or forced[0].responses[0].uci != legal[0].uci:
            raise _fail("P6 forced response is missing or names another response")

        subject = _sorted_bases(
            base_ref(first.before_identity, transition.before)
            for transition in first.delta.transitions
        )
        if not subject:
            raise _fail("played move changes no piece")
        played_key = outcome_key(self.replay.played.line.probe_result, self.mover)

        def equivalent(line: GoodMoveReplayedLineContext) -> bool | None:
            if len(line.plies[0].rules.legal_moves) != 1:
                return False
            alternative_key = outcome_key(line.probe_result, self.mover)
            if played_key is None or alternative_key is None:
                return None
            return alternative_key >= played_key

        status, flag = _status(equivalent(a.evidence.line) for a in self.replay.alternatives)
        return self.benefit(
            _K.FORCES_RESPONSE,
            status,
            subject,
            flag,
            tested_response=legal[0],
            affected_pieces=subject,
            board_deltas=(first.delta,),
            tactical_candidates=(forced[0],),
            probe_results=self.batch_a_results(),
        )

    # -- MATE_THREAT --

    def mate_threat(self) -> GoodMoveBenefitResult | None:
        mover = self.mover
        played = self.replay.played
        first = played.line.plies[0]
        tested_response = None
        probes = self.batch_a_results()
        if first.facts.side_to_move_checkmated:
            line, level = played.line, MateEvidenceLevel.EXACT_IMMEDIATE
        elif establishes_mate(played.line, mover):
            line, level = played.line, MateEvidenceLevel.ENGINE_LINE
        elif self.tested is not None and self.tested.kind is _K.MATE_THREAT:
            ignored = self.replay.ignored_response
            if ignored is None or not establishes_mate(ignored.line, mover):
                return None  # the tested Q produced no verified mating consequence
            line, level = ignored.line, MateEvidenceLevel.ENGINE_LINE
            tested_response = self.tested.response
            probes = (*probes, ignored.line.probe_result)
        else:
            return None

        exact = replay_mates_for(line, mover)
        steps = (line.plies[0], line.final) if exact else (line.plies[0],)
        deltas = _unique(step.delta for step in steps)
        candidates = _unique(
            candidate
            for step in steps
            for candidate in step.detection.candidates
            if candidate.kind in (_TK.CHECK, _TK.CHECKMATE)
        )
        king = opponent_king(self.replay)
        # Any verified mover-winning mate on an alternative is equivalent, whatever its distance.
        status, flag = _status(
            establishes_mate(a.evidence.line, mover) for a in self.replay.alternatives
        )
        return self.benefit(
            _K.MATE_THREAT,
            status,
            (king,),
            flag,
            tested_response=tested_response,
            affected_pieces=(king,),
            board_deltas=deltas,
            tactical_candidates=candidates,
            probe_results=probes,
            mate_evidence_level=level,
            replayed_pv_ends_in_checkmate=exact,
        )

    # -- MATERIAL_THREAT --

    def material_threat(self) -> GoodMoveBenefitResult | None:
        mover = self.mover
        played = self.replay.played
        tested_response = None
        resource: tuple[TacticalCandidate, ...] = ()
        materials: tuple[MaterialLineEvidence, ...] = (played.material,)
        probes = self.batch_a_results()
        if has_direct_material(self.replay):
            events = positive_material_events(played.line, mover)
            if not events:
                raise _fail("stable material gain has no exact positive material event")
            gain = played.material.material_delta
        elif self.tested is not None and self.tested.kind is _K.MATERIAL_THREAT:
            ignored = self.replay.ignored_response
            assert self.tested.resource is not None
            if ignored is None:
                return None
            measured = ignored.material
            if measured.stable_at_ply is None or measured.material_delta <= 0:
                return None
            targets = set(self.tested.resource.targets)
            events = tuple(
                (step, base)
                for step, base in positive_material_events(ignored.line, mover)
                if step.delta.capture is not None and base in targets
            )
            if not events:
                return None  # a stable gain of an unrelated piece does not prove the resource
            gain = measured.material_delta
            tested_response = self.tested.response
            resource = (self.tested.resource.candidate,)
            materials = (*materials, measured)
            probes = (*probes, ignored.line.probe_result)
        else:
            return None

        def equivalent(material: MaterialLineEvidence) -> bool | None:
            if material.stable_at_ply is None:
                return None
            return material.material_delta >= gain

        alternatives = tuple(a.evidence.material for a in self.replay.alternatives)
        status, flag = _status(equivalent(material) for material in alternatives)
        subject = _sorted_bases(base for _, base in events)
        return self.benefit(
            _K.MATERIAL_THREAT,
            status,
            subject,
            flag,
            tested_response=tested_response,
            affected_pieces=subject,
            board_deltas=_unique(step.delta for step, _ in events),
            tactical_candidates=resource,
            probe_results=probes,
            material_evidence=(materials[0], *alternatives, *materials[1:]),
        )


def _unique[T](values: Iterable[T]) -> tuple[T, ...]:
    found: list[T] = []
    for value in values:
        if value not in found:
            found.append(value)
    return tuple(found)


# ---- aggregate -------------------------------------------------------------------------------


def _result(
    prepared: GoodMovePreparedContext,
    status: GoodMoveExplanationStatus,
    benefits: tuple[GoodMoveBenefitResult, ...],
) -> GoodMoveExplanationResult:
    return GoodMoveExplanationResult(
        status=status,
        base_position_id=prepared.base.position_id,
        played_move=prepared.played_move,
        mode=GoodMoveMode.STRONG_MOVE,
        alternatives=prepared.alternatives,
        alternative_scope=AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES,
        literal_only_move_proven=False,
        benefits=benefits,
    )


def require_strong_move(prepared: GoodMovePreparedContext) -> None:
    if prepared.mode is not GoodMoveMode.STRONG_MOVE:
        raise _fail("STRONG_MOVE rules cannot evaluate another P9 mode")


def no_alternative_result(prepared: GoodMovePreparedContext) -> GoodMoveExplanationResult:
    """Without a representative comparator the P9 contrast question has no answer."""

    require_strong_move(prepared)
    return _result(prepared, GoodMoveExplanationStatus.INCONCLUSIVE, ())


def evaluate_strong_move(
    replay: GoodMoveReplayContext, tested: GoodMoveTestedThreat | None = None
) -> GoodMoveExplanationResult:
    """Apply the FORCES_RESPONSE, MATE_THREAT and MATERIAL_THREAT rules; makes no P7 call."""

    context = replay.counterfactual
    prepared = context.deterministic.prepared
    require_strong_move(prepared)
    if not prepared.alternatives:
        return no_alternative_result(prepared)
    if tested is not None and (
        context.ignored_response is None
        or replay.ignored_response is None
        or tested.response.uci != context.ignored_response.uci
    ):
        raise _fail("tested threat does not match the retained ignored response")

    rules = _Rules(replay, tested)
    found = (rules.forces_response(), rules.mate_threat(), rules.material_threat())
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
