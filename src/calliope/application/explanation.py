"""Internal strict explanation pipeline: judged move -> P8/P9 -> P10 claims -> P11 selection.

Application glue only.  It routes by the frozen P8/P9 eligibility sets, runs the explainers'
own frozen protocols with one fixed P7 profile, and closes every package through the P10 and
P11 validators.  It makes no chess decision of its own and never turns an internal failure
into silence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from calliope.domain.analysis import (
    BadMoveExplanationStatus,
    GoodMoveExplanationResult,
    GoodMoveMode,
)
from calliope.domain.chess import ChessMove, PositionSnapshot
from calliope.domain.engine import (
    EngineAnalysis,
    EngineLimit,
    EngineSettings,
    MoveJudgement,
    MoveQuality,
)
from calliope.domain.explanation import (
    EvidenceBundle,
    ExplanationClaim,
    ExplanationGraph,
    ExplanationSelection,
)
from calliope.errors import (
    IncompatibleBadMoveContextError,
    IncompatibleGoodMoveContextError,
    MoveJudgementError,
)
from calliope.services.explanation import (
    BadMoveExplainer,
    ExplanationSelectionValidator,
    ExplanationSelector,
    GoodMoveExplainer,
    GraphBuilder,
)
from calliope.services.explanation.claim_builder import ClaimBuilder
from calliope.services.explanation.claim_validator import ClaimValidator
from calliope.services.explanation.evidence_builder import EvidenceBuilder
from calliope.services.explanation.good_move import GoodMoveNotApplicable

COUNTERFACTUAL_SETTINGS = EngineSettings(
    limit=EngineLimit(depth=12, time_ms=2000),
    multipv=1,
    threads=1,
    hash_mb=16,
)
"""Frozen G0 P7 reproducibility profile; independent of the public judgement budget."""

BAD_MOVE_QUALITIES = frozenset({MoveQuality.MISTAKE, MoveQuality.BLUNDER})
GOOD_MOVE_QUALITIES = frozenset({MoveQuality.BEST, MoveQuality.EXCELLENT, MoveQuality.GOOD})
UNEXPLAINED_QUALITIES = frozenset({MoveQuality.INACCURACY})
"""No current strict P8/P9 family applies; the result is the canonical empty package."""


@dataclass(frozen=True, slots=True)
class MoveExplanationOutcome:
    """Validated P10 claims plus the validated P11 graph/selection pair (internal)."""

    claims: tuple[ExplanationClaim, ...]
    graph: ExplanationGraph
    selection: ExplanationSelection


@dataclass(slots=True)
class MoveExplanationPipeline:
    """P4-P11 for one judged move.  Owns no engine; P7 runs through the explainers' ports."""

    bad_moves: BadMoveExplainer
    good_moves: GoodMoveExplainer
    settings: EngineSettings = COUNTERFACTUAL_SETTINGS
    evidence: EvidenceBuilder = field(default_factory=EvidenceBuilder)
    claim_builder: ClaimBuilder = field(default_factory=ClaimBuilder)
    claim_validator: ClaimValidator = field(default_factory=ClaimValidator)
    graphs: GraphBuilder = field(default_factory=GraphBuilder)
    selector: ExplanationSelector = field(default_factory=ExplanationSelector)
    selections: ExplanationSelectionValidator = field(default_factory=ExplanationSelectionValidator)

    def explain(
        self,
        base: PositionSnapshot,
        played: ChessMove,
        judgement: MoveJudgement,
        position_analysis: EngineAnalysis,
    ) -> MoveExplanationOutcome:
        quality = judgement.quality
        if quality in BAD_MOVE_QUALITIES:
            bundle, claims = self._bad_move(base, played, judgement)
        elif quality in GOOD_MOVE_QUALITIES:
            bundle, claims = self._good_move(base, played, judgement, position_analysis)
        elif quality in UNEXPLAINED_QUALITIES:
            bundle, claims = EvidenceBundle(base.position_id, (), ()), ()
        else:
            raise MoveJudgementError(f"unroutable move quality {quality!r}")

        graph = self.graphs.build(bundle, claims)  # reruns P10 validation
        selection = self.selector.select(graph)
        self.selections.validate(graph, selection)
        return MoveExplanationOutcome(claims=claims, graph=graph, selection=selection)

    def _bad_move(
        self, base: PositionSnapshot, played: ChessMove, judgement: MoveJudgement
    ) -> tuple[EvidenceBundle, tuple[ExplanationClaim, ...]]:
        result = self.bad_moves.explain(base, played, judgement, self.settings)
        if result.status is BadMoveExplanationStatus.NOT_APPLICABLE:
            raise IncompatibleBadMoveContextError(
                f"P8 rejected a {judgement.quality.value} move routed to it"
            )
        bundle = self.evidence.build_bad_move(result)
        claims = self.claim_builder.build_bad_move(bundle)
        return bundle, self.claim_validator.validate_bad_move(bundle, claims)

    def _good_move(
        self,
        base: PositionSnapshot,
        played: ChessMove,
        judgement: MoveJudgement,
        position_analysis: EngineAnalysis,
    ) -> tuple[EvidenceBundle, tuple[ExplanationClaim, ...]]:
        prepared = self.good_moves.prepare(base, played, judgement, position_analysis)
        if isinstance(prepared, GoodMoveNotApplicable):
            raise IncompatibleGoodMoveContextError(
                f"P9 rejected a {judgement.quality.value} move routed to it"
            )
        deterministic = self.good_moves.build_branches(prepared)
        context = self.good_moves.verify_counterfactuals(deterministic, self.settings)
        # The mode is P9's own frozen decision; G0 never re-derives it.
        result: GoodMoveExplanationResult
        if prepared.mode is GoodMoveMode.STRONG_MOVE:
            result = self.good_moves.explain_strong_move(context)
        elif prepared.mode is GoodMoveMode.ONLY_MOVE_CANDIDATE:
            result = self.good_moves.explain_only_move(context)
        else:
            raise IncompatibleGoodMoveContextError(f"unsupported P9 mode {prepared.mode!r}")
        bundle = self.evidence.build_good_move(result)
        claims = self.claim_builder.build_good_move(bundle)
        return bundle, self.claim_validator.validate_good_move(bundle, claims)
