"""P9 preparation, branches, bounded P7 evidence, exact replay and STRONG_MOVE orchestration.

Replay measures material with the frozen P8 metric and stability contract; it decides no
benefit.  Material values are a fixed causal-verification metric, never an engine evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from calliope.application.ports.chess import ChessRulesPort
from calliope.application.ports.tactics import TacticalObservation, TacticalObservationPort
from calliope.domain.analysis import (
    AlternativeScope,
    BasePieceRef,
    BoardDelta,
    CounterfactualBatchRequest,
    CounterfactualBatchResult,
    CounterfactualProbe,
    GoodMoveBenefitKind,
    GoodMoveExplanationResult,
    GoodMoveMode,
    MaterialLineEvidence,
    PieceTransitionKind,
    ProbeKind,
    ProbeResult,
    RepresentativeAlternative,
    TacticalDetection,
    TerminalKind,
    TerminalOutcome,
)
from calliope.domain.chess import ChessMove, Color, PieceType, PositionFacts, PositionSnapshot
from calliope.domain.engine import (
    EngineAnalysis,
    EngineIdentity,
    EngineSettings,
    ForcednessLevel,
    MoveJudgement,
    MoveQuality,
)
from calliope.errors import (
    IllegalMoveError,
    IncompatibleBadMoveContextError,
    IncompatibleGoodMoveContextError,
    InvalidUciError,
    NullMoveNotAllowedError,
)
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.explanation.good_move_benefits import (
    GoodMoveTestedThreat,
    base_ref,
    evaluate_strong_move,
    has_direct_mate,
    has_direct_material,
    material_resources,
    no_alternative_result,
    require_strong_move,
)
from calliope.services.explanation.piece_identity import BasePieceIdentityMap
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.tactics import TacticalDetector

ELIGIBLE_QUALITIES = frozenset({MoveQuality.BEST, MoveQuality.EXCELLENT, MoveQuality.GOOD})

# Frozen P8 material metric (kings excluded); duplicated, not imported, and parity-tested.
PIECE_VALUES: dict[PieceType, int] = {
    PieceType.PAWN: 100,
    PieceType.KNIGHT: 320,
    PieceType.BISHOP: 330,
    PieceType.ROOK: 500,
    PieceType.QUEEN: 900,
}
_COUNT_FIELD = {
    PieceType.PAWN: "pawns",
    PieceType.KNIGHT: "knights",
    PieceType.BISHOP: "bishops",
    PieceType.ROOK: "rooks",
    PieceType.QUEEN: "queens",
}
_MOVE_ERRORS = (IllegalMoveError, InvalidUciError, NullMoveNotAllowedError)


@dataclass(frozen=True, slots=True)
class GoodMovePreparedContext:
    """Validated original ranking basis and at most two canonical alternatives."""

    base: PositionSnapshot
    played_move: ChessMove
    best_move: ChessMove
    judgement: MoveJudgement
    position_analysis: EngineAnalysis
    mode: GoodMoveMode
    alternatives: tuple[RepresentativeAlternative, ...]
    alternative_scope: AlternativeScope


@dataclass(frozen=True, slots=True)
class GoodMoveNotApplicable:
    """Validated non-eligible move; contains no selection or explanation evidence."""

    base_position_id: str
    played_move: ChessMove


@dataclass(frozen=True, slots=True)
class GoodMoveFirstMoveBranchContext:
    """Exact one-move evidence and identity propagated from the common base."""

    move: ChessMove
    position: PositionSnapshot
    facts: PositionFacts
    delta: BoardDelta
    rules: TacticalObservation
    detection: TacticalDetection
    identity: BasePieceIdentityMap


@dataclass(frozen=True, slots=True)
class GoodMoveAlternativeBranchContext:
    """A retained ranked alternative paired with its independent board branch."""

    alternative: RepresentativeAlternative
    branch: GoodMoveFirstMoveBranchContext


@dataclass(frozen=True, slots=True)
class GoodMoveDeterministicContext:
    """Shared base evidence and independently constructed played/alternative branches."""

    prepared: GoodMovePreparedContext
    base_facts: PositionFacts
    base_rules: TacticalObservation
    root_identity: BasePieceIdentityMap
    played: GoodMoveFirstMoveBranchContext
    alternatives: tuple[GoodMoveAlternativeBranchContext, ...]


@dataclass(frozen=True, slots=True)
class GoodMoveAlternativeRefutation:
    """An original representative alternative paired with its P7 observation."""

    alternative: RepresentativeAlternative
    result: ProbeResult


@dataclass(frozen=True, slots=True)
class GoodMoveCounterfactualContext:
    """Bounded P7 observations without score ordering or benefit classification."""

    deterministic: GoodMoveDeterministicContext
    settings: EngineSettings
    batch_a: CounterfactualBatchResult
    played_refutation: ProbeResult
    alternative_refutations: tuple[GoodMoveAlternativeRefutation, ...]
    engine_identity: EngineIdentity | None
    batch_b: CounterfactualBatchResult | None = None
    ignored_response: ChessMove | None = None
    ignored_response_result: ProbeResult | None = None

    @property
    def probe_count(self) -> int:
        return len(self.batch_a.results) + (len(self.batch_b.results) if self.batch_b else 0)


@dataclass(frozen=True, slots=True)
class GoodMoveReplayStepContext:
    """One exact replayed ply; ply 1 is the first move from the common base."""

    ply: int
    before: PositionSnapshot
    move: ChessMove
    position: PositionSnapshot
    facts: PositionFacts
    delta: BoardDelta
    rules: TacticalObservation
    detection: TacticalDetection
    before_identity: BasePieceIdentityMap
    identity: BasePieceIdentityMap


@dataclass(frozen=True, slots=True)
class GoodMoveReplayedLineContext:
    """A retained P7 line replayed through exact rules: the first move, then every PV move."""

    probe_result: ProbeResult
    plies: tuple[GoodMoveReplayStepContext, ...]

    @property
    def final(self) -> GoodMoveReplayStepContext:
        return self.plies[-1]

    @property
    def ends_in_checkmate(self) -> bool:
        return self.final.facts.side_to_move_checkmated

    @property
    def ends_in_stalemate(self) -> bool:
        return not self.final.rules.legal_moves and not self.final.facts.side_to_move_in_check


@dataclass(frozen=True, slots=True)
class GoodMoveLineEvidence:
    """A replayed line and its original-mover material measurement."""

    line: GoodMoveReplayedLineContext
    material: MaterialLineEvidence


@dataclass(frozen=True, slots=True)
class GoodMoveAlternativeLineEvidence:
    """A representative alternative paired with its replayed REFUTATION evidence."""

    alternative: RepresentativeAlternative
    evidence: GoodMoveLineEvidence


@dataclass(frozen=True, slots=True)
class GoodMoveReplayContext:
    """Exact replay/material evidence for every retained P7 line; no benefit decision."""

    counterfactual: GoodMoveCounterfactualContext
    played: GoodMoveLineEvidence
    alternatives: tuple[GoodMoveAlternativeLineEvidence, ...]
    ignored_response: GoodMoveLineEvidence | None


@dataclass(slots=True)
class GoodMoveExplainer:
    chess: ChessRulesPort
    facts: PositionFactExtractor
    delta: BoardDeltaAnalyzer
    tactical_rules: TacticalObservationPort
    detector: TacticalDetector
    counterfactual: CounterfactualAnalyzer

    def prepare(
        self,
        base: PositionSnapshot,
        played: ChessMove,
        judgement: MoveJudgement,
        position_analysis: EngineAnalysis,
    ) -> GoodMovePreparedContext | GoodMoveNotApplicable:
        """Validate the complete basis before applicability; select by rank, never score."""

        if judgement.position_id != base.position_id:
            raise IncompatibleGoodMoveContextError("judgement belongs to another position")
        if judgement.mover is not base.side_to_move:
            raise IncompatibleGoodMoveContextError("judgement mover is not the side to move")

        played_move = self._canonical(base, played, "supplied played move")
        judged_move = self._canonical(base, judgement.move, "judged move")
        if played_move.uci != judged_move.uci:
            raise IncompatibleGoodMoveContextError("played move differs from the judged move")
        best_move = self._canonical(base, judgement.best_move, "best move")

        if position_analysis.position_id != base.position_id:
            raise IncompatibleGoodMoveContextError("position analysis belongs to another position")
        ordered = sorted(position_analysis.lines, key=lambda line: line.rank)
        if not ordered or [line.rank for line in ordered] != list(range(1, len(ordered) + 1)):
            raise IncompatibleGoodMoveContextError(
                "engine ranks must be unique and contiguous 1..N"
            )

        ranked = tuple(
            (line.rank, self._canonical(base, line.first_move, "ranked engine move"))
            for line in ordered
        )
        ucis = tuple(move.uci for _, move in ranked)
        if len(ucis) != len(set(ucis)):
            raise IncompatibleGoodMoveContextError(
                "ranked basis contains duplicate canonical moves"
            )
        if ranked[0][1].uci != best_move.uci:
            raise IncompatibleGoodMoveContextError("rank-1 move differs from the judged best move")

        played_rank = next((rank for rank, move in ranked if move.uci == played_move.uci), None)
        if judgement.rank != played_rank:
            raise IncompatibleGoodMoveContextError(
                "judgement rank differs from the played basis rank"
            )

        if judgement.quality not in ELIGIBLE_QUALITIES:
            return GoodMoveNotApplicable(base.position_id, played_move)
        if judgement.quality is MoveQuality.BEST and played_move.uci != best_move.uci:
            raise IncompatibleGoodMoveContextError("BEST played move must equal the best move")

        mode = GoodMoveMode.STRONG_MOVE
        if (
            judgement.quality is MoveQuality.BEST
            and judgement.forcedness.level is ForcednessLevel.ONLY_MOVE
        ):
            mode = GoodMoveMode.ONLY_MOVE_CANDIDATE

        alternatives = tuple(
            RepresentativeAlternative(rank, move)
            for rank, move in ranked
            if move.uci != played_move.uci
        )[:2]
        return GoodMovePreparedContext(
            base=base,
            played_move=played_move,
            best_move=best_move,
            judgement=judgement,
            position_analysis=position_analysis,
            mode=mode,
            alternatives=alternatives,
            alternative_scope=AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES,
        )

    def _canonical(self, base: PositionSnapshot, move: ChessMove, label: str) -> ChessMove:
        try:
            return self.chess.legal_move_from_uci(base, move.uci)
        except (IllegalMoveError, InvalidUciError, NullMoveNotAllowedError) as error:
            raise IncompatibleGoodMoveContextError(
                f"{label} is not legal in the base position"
            ) from error

    def build_branches(self, prepared: GoodMovePreparedContext) -> GoodMoveDeterministicContext:
        """Build each selected first move from one shared base, without reselecting alternatives."""

        base = prepared.base
        base_facts = self.facts.extract(base)
        base_rules = self.tactical_rules.observe_tactics(base)
        if base_facts.position_id != base.position_id:
            raise IncompatibleGoodMoveContextError("base facts belong to another position")
        if base_rules.position_id != base.position_id:
            raise IncompatibleGoodMoveContextError(
                "base tactical observation belongs to another position"
            )
        if base_rules.side_to_move is not base.side_to_move:
            raise IncompatibleGoodMoveContextError(
                "base tactical observation has the wrong side to move"
            )

        try:
            root_identity = BasePieceIdentityMap.from_facts(base_facts)
        except IncompatibleBadMoveContextError as error:
            raise IncompatibleGoodMoveContextError("base piece identity is inconsistent") from error
        if not (root_identity.base_position_id == root_identity.position_id == base.position_id):
            raise IncompatibleGoodMoveContextError(
                "root identity is not bound to the base position"
            )

        played = self._first_move_branch(
            base, prepared.played_move, base_facts, base_rules, root_identity
        )
        alternatives = tuple(
            GoodMoveAlternativeBranchContext(
                alternative=alternative,
                branch=self._first_move_branch(
                    base, alternative.move, base_facts, base_rules, root_identity
                ),
            )
            for alternative in prepared.alternatives
        )
        return GoodMoveDeterministicContext(
            prepared=prepared,
            base_facts=base_facts,
            base_rules=base_rules,
            root_identity=root_identity,
            played=played,
            alternatives=alternatives,
        )

    def _first_move_branch(
        self,
        base: PositionSnapshot,
        move: ChessMove,
        base_facts: PositionFacts,
        base_rules: TacticalObservation,
        root_identity: BasePieceIdentityMap,
    ) -> GoodMoveFirstMoveBranchContext:
        canonical = self._canonical(base, move, "branch move")
        if canonical.uci != move.uci:
            raise IncompatibleGoodMoveContextError("prepared branch move is not canonical")
        try:
            after = self.chess.apply_move(base, move)
        except (IllegalMoveError, InvalidUciError, NullMoveNotAllowedError) as error:
            raise IncompatibleGoodMoveContextError(
                "branch move cannot be applied to the base"
            ) from error
        if after.side_to_move is not base.side_to_move.opposite:
            raise IncompatibleGoodMoveContextError("branch position has the wrong side to move")
        delta = self.delta.analyze(base, move)
        after_facts = self.facts.extract(after)
        after_rules = self.tactical_rules.observe_tactics(after)

        if delta.before_position_id != base.position_id:
            raise IncompatibleGoodMoveContextError(
                "board delta does not start from the base position"
            )
        if delta.after_position_id != after.position_id:
            raise IncompatibleGoodMoveContextError(
                "board delta does not end at the branch position"
            )
        if delta.move.uci != move.uci:
            raise IncompatibleGoodMoveContextError("board delta describes another move")
        if delta.mover is not base.side_to_move:
            raise IncompatibleGoodMoveContextError("board delta has the wrong mover")
        if after_facts.position_id != after.position_id:
            raise IncompatibleGoodMoveContextError("branch facts belong to another position")
        if after_rules.position_id != after.position_id:
            raise IncompatibleGoodMoveContextError(
                "branch tactical observation belongs to another position"
            )
        if after_rules.side_to_move is not base.side_to_move.opposite:
            raise IncompatibleGoodMoveContextError(
                "branch tactical observation has the wrong side to move"
            )

        detection = self.detector.detect(
            before=base_facts,
            after=after_facts,
            delta=delta,
            before_rules=base_rules,
            after_rules=after_rules,
        )
        if detection.before_position_id != base.position_id:
            raise IncompatibleGoodMoveContextError(
                "tactical detection does not start from the base"
            )
        if detection.after_position_id != after.position_id:
            raise IncompatibleGoodMoveContextError("tactical detection does not end at the branch")
        if detection.move.uci != move.uci:
            raise IncompatibleGoodMoveContextError("tactical detection describes another move")
        if detection.mover is not base.side_to_move:
            raise IncompatibleGoodMoveContextError("tactical detection has the wrong mover")

        try:
            identity = root_identity.advance(delta)
        except IncompatibleBadMoveContextError as error:
            raise IncompatibleGoodMoveContextError(
                "branch piece identity is inconsistent"
            ) from error
        if identity.base_position_id != base.position_id:
            raise IncompatibleGoodMoveContextError("branch identity is not anchored to the base")
        if identity.position_id != after.position_id:
            raise IncompatibleGoodMoveContextError(
                "branch identity is not bound to the branch position"
            )
        return GoodMoveFirstMoveBranchContext(
            move, after, after_facts, delta, after_rules, detection, identity
        )

    def verify_counterfactuals(
        self, deterministic: GoodMoveDeterministicContext, settings: EngineSettings
    ) -> GoodMoveCounterfactualContext:
        """Execute exactly one played-first REFUTATION batch with supplied settings."""
        branches = self._counterfactual_branches(deterministic)
        request = self._refutation_request(deterministic, settings)
        batch = self.counterfactual.execute(request)
        self._check_counterfactual_batch(batch, request, branches, (None,) * len(branches))
        identity = self._counterfactual_identity(batch)
        return GoodMoveCounterfactualContext(
            deterministic=deterministic,
            settings=settings,
            batch_a=batch,
            played_refutation=batch.results[0],
            alternative_refutations=tuple(
                GoodMoveAlternativeRefutation(alternative.alternative, result)
                for alternative, result in zip(
                    deterministic.alternatives, batch.results[1:], strict=True
                )
            ),
            engine_identity=identity,
        )

    def verify_ignored_response(
        self, context: GoodMoveCounterfactualContext, response: ChessMove
    ) -> GoodMoveCounterfactualContext:
        """Attach one explicit IGNORE_THREAT experiment; never select Q or repeat B."""
        if any(
            value is not None
            for value in (
                context.batch_b,
                context.ignored_response,
                context.ignored_response_result,
            )
        ):
            raise IncompatibleGoodMoveContextError("Batch B is already attached")
        deterministic = context.deterministic
        branches = self._counterfactual_branches(deterministic)
        request_a = self._refutation_request(deterministic, context.settings)
        self._check_counterfactual_batch(
            context.batch_a, request_a, branches, (None,) * len(branches)
        )
        identity = self._counterfactual_identity(context.batch_a)
        if identity != context.engine_identity:
            raise IncompatibleGoodMoveContextError("stored Batch-A engine identity differs")
        if context.played_refutation is not context.batch_a.results[0] or len(
            context.alternative_refutations
        ) != len(deterministic.alternatives):
            raise IncompatibleGoodMoveContextError("stored Batch-A refutations differ")
        for retained, alternative, result in zip(
            context.alternative_refutations,
            deterministic.alternatives,
            context.batch_a.results[1:],
            strict=True,
        ):
            if retained.alternative != alternative.alternative or retained.result is not result:
                raise IncompatibleGoodMoveContextError("stored alternative refutation differs")
        played = deterministic.played
        if not played.rules.legal_moves or played.facts.side_to_move_checkmated:
            raise IncompatibleGoodMoveContextError(
                "played branch is terminal; no ignored response exists"
            )
        if identity is None:
            raise IncompatibleGoodMoveContextError(
                "non-terminal played branch lacks engine identity"
            )
        try:
            canonical = self.chess.legal_move_from_uci(played.position, response.uci)
        except (IllegalMoveError, InvalidUciError, NullMoveNotAllowedError) as error:
            raise IncompatibleGoodMoveContextError(
                "ignored response is not legal after the played move"
            ) from error
        prepared = deterministic.prepared
        request = CounterfactualBatchRequest(
            probes=(
                CounterfactualProbe(
                    ProbeKind.IGNORE_THREAT, prepared.base, prepared.played_move, canonical
                ),
            ),
            settings=context.settings,
        )
        batch = self.counterfactual.execute(request)
        self._check_counterfactual_batch(batch, request, (played,), ((canonical,),))
        if self._counterfactual_identity(batch) != identity:
            raise IncompatibleGoodMoveContextError("engine identity differs across P7 batches")
        return replace(
            context,
            batch_b=batch,
            ignored_response=canonical,
            ignored_response_result=batch.results[0],
        )

    @staticmethod
    def _counterfactual_branches(
        deterministic: GoodMoveDeterministicContext,
    ) -> tuple[GoodMoveFirstMoveBranchContext, ...]:
        prepared = deterministic.prepared
        if len(prepared.alternatives) > 2 or len(deterministic.alternatives) > 2:
            raise IncompatibleGoodMoveContextError("P9 permits at most two alternatives")
        if len(prepared.alternatives) != len(deterministic.alternatives):
            raise IncompatibleGoodMoveContextError("alternative branch count differs")
        if deterministic.played.move.uci != prepared.played_move.uci:
            raise IncompatibleGoodMoveContextError("played branch move differs")
        for retained, expected in zip(
            deterministic.alternatives, prepared.alternatives, strict=True
        ):
            if retained.alternative != expected or retained.branch.move.uci != expected.move.uci:
                raise IncompatibleGoodMoveContextError("alternative branch metadata differs")
        base_id = prepared.base.position_id
        if (
            not (
                deterministic.base_facts.position_id
                == deterministic.base_rules.position_id
                == deterministic.root_identity.base_position_id
                == deterministic.root_identity.position_id
                == base_id
            )
            or deterministic.base_rules.side_to_move is not prepared.base.side_to_move
        ):
            raise IncompatibleGoodMoveContextError("deterministic base evidence differs")
        branches = (deterministic.played, *(a.branch for a in deterministic.alternatives))
        for branch in branches:
            if (
                branch.identity.base_position_id != base_id
                or branch.delta.before_position_id != base_id
            ):
                raise IncompatibleGoodMoveContextError("branch is not anchored to the common base")
            if not (
                branch.position.position_id
                == branch.identity.position_id
                == branch.facts.position_id
                == branch.rules.position_id
                == branch.delta.after_position_id
            ):
                raise IncompatibleGoodMoveContextError(
                    "deterministic branch position bindings differ"
                )
        return branches

    @staticmethod
    def _refutation_request(
        deterministic: GoodMoveDeterministicContext, settings: EngineSettings
    ) -> CounterfactualBatchRequest:
        prepared = deterministic.prepared
        moves = (prepared.played_move, *(a.move for a in prepared.alternatives))
        return CounterfactualBatchRequest(
            tuple(CounterfactualProbe(ProbeKind.REFUTATION, prepared.base, move) for move in moves),
            settings,
        )

    @staticmethod
    def _check_counterfactual_batch(
        batch: CounterfactualBatchResult,
        request: CounterfactualBatchRequest,
        branches: tuple[GoodMoveFirstMoveBranchContext, ...],
        roots: tuple[tuple[ChessMove, ...] | None, ...],
    ) -> None:
        if batch.settings != request.settings or len(batch.results) != len(request.probes):
            raise IncompatibleGoodMoveContextError("P7 batch settings or result count differ")
        for result, probe, branch, root in zip(
            batch.results, request.probes, branches, roots, strict=True
        ):
            if result.probe != probe:
                raise IncompatibleGoodMoveContextError("P7 probe echo or order differs")
            if (
                result.analysis_position != branch.position
                or result.intervention_position != branch.position
            ):
                raise IncompatibleGoodMoveContextError("P7 result position differs from its branch")
            if result.root_moves != root:
                raise IncompatibleGoodMoveContextError("P7 result has unexpected root moves")
            analysis = result.engine_analysis
            if analysis is None:
                if root is not None:
                    raise IncompatibleGoodMoveContextError(
                        "forced response unexpectedly returned terminal evidence"
                    )
                if branch.rules.legal_moves:
                    raise IncompatibleGoodMoveContextError(
                        "terminal evidence contradicts legal moves"
                    )
                checkmated = branch.facts.side_to_move_checkmated
                if checkmated != branch.facts.side_to_move_in_check:
                    raise IncompatibleGoodMoveContextError(
                        "terminal branch checkmate facts contradict check"
                    )
                expected = (
                    TerminalOutcome(TerminalKind.CHECKMATE, probe.base.side_to_move)
                    if checkmated
                    else TerminalOutcome(TerminalKind.STALEMATE, None)
                )
                if result.terminal != expected:
                    raise IncompatibleGoodMoveContextError(
                        "P7 terminal kind or winner contradicts board truth"
                    )
                continue
            if not branch.rules.legal_moves or result.terminal is not None:
                raise IncompatibleGoodMoveContextError(
                    "engine analysis contradicts terminal branch truth"
                )
            if (
                analysis.settings != request.settings
                or analysis.position_id != branch.position.position_id
            ):
                raise IncompatibleGoodMoveContextError(
                    "P7 engine analysis settings or position differ"
                )
            if len(analysis.lines) != 1 or analysis.lines[0].rank != 1:
                raise IncompatibleGoodMoveContextError("P7 requires exactly one rank-1 engine line")
            if root is not None and analysis.best_line.first_move.uci != root[0].uci:
                raise IncompatibleGoodMoveContextError(
                    "P7 forced line does not start with the response"
                )

    @staticmethod
    def _counterfactual_identity(batch: CounterfactualBatchResult) -> EngineIdentity | None:
        if any(
            r.engine_analysis is not None
            and not isinstance(r.engine_analysis.engine, EngineIdentity)
            for r in batch.results
        ):
            raise IncompatibleGoodMoveContextError("non-terminal P7 result lacks engine identity")
        identities = {
            r.engine_analysis.engine for r in batch.results if r.engine_analysis is not None
        }
        if len(identities) > 1:
            raise IncompatibleGoodMoveContextError("engine identity differs within a P7 batch")
        return next(iter(identities), None)

    def replay_lines(self, context: GoodMoveCounterfactualContext) -> GoodMoveReplayContext:
        """Replay every retained P7 line through exact rules and measure material; no P7 call."""

        branches = self._revalidate_counterfactual_context(context)
        deterministic = context.deterministic
        mover = deterministic.prepared.base.side_to_move
        base_facts = deterministic.base_facts

        def evidence(
            result: ProbeResult,
            branch: GoodMoveFirstMoveBranchContext,
            forced: ChessMove | None = None,
        ) -> GoodMoveLineEvidence:
            line = self._replay_line(result, branch, deterministic, forced)
            return GoodMoveLineEvidence(line, _material_evidence(line, base_facts, mover))

        played = evidence(context.played_refutation, branches[0])
        alternatives = tuple(
            GoodMoveAlternativeLineEvidence(retained.alternative, evidence(retained.result, branch))
            for retained, branch in zip(context.alternative_refutations, branches[1:], strict=True)
        )
        ignored = None
        if context.ignored_response_result is not None:
            ignored = evidence(
                context.ignored_response_result, branches[0], context.ignored_response
            )
        return GoodMoveReplayContext(context, played, alternatives, ignored)

    def _revalidate_counterfactual_context(
        self, context: GoodMoveCounterfactualContext
    ) -> tuple[GoodMoveFirstMoveBranchContext, ...]:
        """Re-run the I3 compatibility checks on retained evidence without executing P7."""

        if context.probe_count > 4:
            raise IncompatibleGoodMoveContextError("retained P7 evidence exceeds four probes")
        deterministic = context.deterministic
        branches = self._counterfactual_branches(deterministic)
        for branch in branches:
            self._check_board_truth(branch)
        request_a = self._refutation_request(deterministic, context.settings)
        self._check_counterfactual_batch(
            context.batch_a, request_a, branches, (None,) * len(branches)
        )
        identity = self._counterfactual_identity(context.batch_a)
        if identity != context.engine_identity:
            raise IncompatibleGoodMoveContextError("stored Batch-A engine identity differs")
        if context.played_refutation is not context.batch_a.results[0] or len(
            context.alternative_refutations
        ) != len(deterministic.alternatives):
            raise IncompatibleGoodMoveContextError("stored Batch-A refutations differ")
        for retained, alternative, result in zip(
            context.alternative_refutations,
            deterministic.alternatives,
            context.batch_a.results[1:],
            strict=True,
        ):
            if retained.alternative != alternative.alternative or retained.result is not result:
                raise IncompatibleGoodMoveContextError("stored alternative refutation differs")
        ranks = [retained.alternative.rank for retained in context.alternative_refutations]
        if ranks != sorted(set(ranks)):
            raise IncompatibleGoodMoveContextError("alternatives are not in representative order")

        retained_b = (context.batch_b, context.ignored_response, context.ignored_response_result)
        if all(value is None for value in retained_b):
            return branches
        if any(value is None for value in retained_b):
            raise IncompatibleGoodMoveContextError("Batch-B evidence is only partially retained")
        assert context.batch_b is not None and context.ignored_response is not None
        played = deterministic.played
        if identity is None or not played.rules.legal_moves:
            raise IncompatibleGoodMoveContextError("Batch B exists for a terminal played branch")
        response = self._legal_in(played.position, context.ignored_response, "ignored response")
        if response.uci != context.ignored_response.uci:
            raise IncompatibleGoodMoveContextError("retained ignored response is not canonical")
        prepared = deterministic.prepared
        request_b = CounterfactualBatchRequest(
            (
                CounterfactualProbe(
                    ProbeKind.IGNORE_THREAT, prepared.base, prepared.played_move, response
                ),
            ),
            context.settings,
        )
        self._check_counterfactual_batch(context.batch_b, request_b, (played,), ((response,),))
        if context.ignored_response_result is not context.batch_b.results[0]:
            raise IncompatibleGoodMoveContextError("stored ignored-response result differs")
        if self._counterfactual_identity(context.batch_b) != identity:
            raise IncompatibleGoodMoveContextError("engine identity differs across P7 batches")
        return branches

    def _replay_line(
        self,
        result: ProbeResult,
        branch: GoodMoveFirstMoveBranchContext,
        deterministic: GoodMoveDeterministicContext,
        forced: ChessMove | None,
    ) -> GoodMoveReplayedLineContext:
        """Ply 1 is the retained I2 branch; every engine PV move is revalidated and replayed."""

        base = deterministic.prepared.base
        if result.analysis_position != branch.position:
            raise IncompatibleGoodMoveContextError(
                "P7 line does not start at its first-move branch"
            )
        plies = [
            GoodMoveReplayStepContext(
                ply=1,
                before=base,
                move=branch.move,
                position=branch.position,
                facts=branch.facts,
                delta=branch.delta,
                rules=branch.rules,
                detection=branch.detection,
                before_identity=deterministic.root_identity,
                identity=branch.identity,
            )
        ]
        self._check_board_truth(plies[0])
        analysis = result.engine_analysis
        if analysis is None:
            if forced is not None:
                raise IncompatibleGoodMoveContextError("forced response line has no engine PV")
        else:
            pv = analysis.best_line.pv
            if forced is not None:
                first = self._legal_in(branch.position, pv[0], "forced-response PV move")
                if not (first.uci == forced.uci == analysis.best_line.first_move.uci):
                    raise IncompatibleGoodMoveContextError(
                        "forced-response PV does not begin with the ignored response"
                    )
            for pv_move in pv:
                plies.append(self._replay_step(plies[-1], pv_move, base))
                self._check_board_truth(plies[-1])
        return GoodMoveReplayedLineContext(probe_result=result, plies=tuple(plies))

    @staticmethod
    def _check_board_truth(
        step: GoodMoveReplayStepContext | GoodMoveFirstMoveBranchContext,
    ) -> None:
        """Checkmate is exactly check with no legal move; no engine score may override it."""

        no_moves = not step.rules.legal_moves
        if step.facts.side_to_move_checkmated != (no_moves and step.facts.side_to_move_in_check):
            raise IncompatibleGoodMoveContextError(
                "replayed checkmate state contradicts legal moves"
            )

    def _legal_in(self, position: PositionSnapshot, move: ChessMove, label: str) -> ChessMove:
        try:
            return self.chess.legal_move_from_uci(position, move.uci)
        except _MOVE_ERRORS as error:
            raise IncompatibleGoodMoveContextError(
                f"{label} is not legal in its replay position"
            ) from error

    def _replay_step(
        self,
        previous: GoodMoveReplayStepContext,
        pv_move: ChessMove,
        base: PositionSnapshot,
    ) -> GoodMoveReplayStepContext:
        before = previous.position
        if not previous.rules.legal_moves:
            raise IncompatibleGoodMoveContextError("engine PV continues after a terminal position")
        move = self._legal_in(before, pv_move, "engine PV move")
        mover = before.side_to_move
        try:
            after = self.chess.apply_move(before, move)
        except _MOVE_ERRORS as error:
            raise IncompatibleGoodMoveContextError("engine PV move cannot be applied") from error
        delta = self.delta.analyze(before, move)
        facts = self.facts.extract(after)
        rules = self.tactical_rules.observe_tactics(after)

        if after.side_to_move is not mover.opposite:
            raise IncompatibleGoodMoveContextError("replayed position has the wrong side to move")
        if delta.before_position_id != before.position_id:
            raise IncompatibleGoodMoveContextError("replay delta does not start from its ply")
        if delta.after_position_id != after.position_id:
            raise IncompatibleGoodMoveContextError("replay delta does not end at its ply")
        if delta.move.uci != move.uci:
            raise IncompatibleGoodMoveContextError("replay delta describes another move")
        if delta.mover is not mover:
            raise IncompatibleGoodMoveContextError("replay delta has the wrong mover")
        if facts.position_id != after.position_id:
            raise IncompatibleGoodMoveContextError("replay facts belong to another position")
        if rules.position_id != after.position_id:
            raise IncompatibleGoodMoveContextError(
                "replay tactical observation belongs to another position"
            )
        if rules.side_to_move is not after.side_to_move:
            raise IncompatibleGoodMoveContextError(
                "replay tactical observation has the wrong side to move"
            )

        detection = self.detector.detect(
            before=previous.facts,
            after=facts,
            delta=delta,
            before_rules=previous.rules,
            after_rules=rules,
        )
        if detection.before_position_id != before.position_id:
            raise IncompatibleGoodMoveContextError("replay detection does not start from its ply")
        if detection.after_position_id != after.position_id:
            raise IncompatibleGoodMoveContextError("replay detection does not end at its ply")
        if detection.move.uci != move.uci:
            raise IncompatibleGoodMoveContextError("replay detection describes another move")
        if detection.mover is not mover:
            raise IncompatibleGoodMoveContextError("replay detection has the wrong mover")

        try:
            identity = previous.identity.advance(delta)
        except IncompatibleBadMoveContextError as error:
            raise IncompatibleGoodMoveContextError(
                "replayed piece identity is inconsistent"
            ) from error
        if identity.base_position_id != base.position_id:
            raise IncompatibleGoodMoveContextError("replay identity is not anchored to the base")
        if identity.position_id != after.position_id:
            raise IncompatibleGoodMoveContextError("replay identity is not bound to its ply")
        return GoodMoveReplayStepContext(
            ply=previous.ply + 1,
            before=before,
            move=move,
            position=after,
            facts=facts,
            delta=delta,
            rules=rules,
            detection=detection,
            before_identity=previous.identity,
            identity=identity,
        )

    def explain_strong_move(
        self, context: GoodMoveCounterfactualContext
    ) -> GoodMoveExplanationResult:
        """Complete at most one cause-specific Batch B, replay, then apply the I5 rules."""

        prepared = context.deterministic.prepared
        require_strong_move(prepared)
        if not prepared.alternatives:
            self._revalidate_counterfactual_context(context)
            return no_alternative_result(prepared)
        replay = self.replay_lines(context)
        allow_mate = not has_direct_mate(replay)
        allow_material = not has_direct_material(replay)
        if context.batch_b is not None:
            # An explicit I3 experiment proves nothing unless its Q is itself cause-specific.
            assert context.ignored_response is not None
            tested = self._select_tested_threat(
                replay, allow_mate, allow_material, context.ignored_response
            )
            return evaluate_strong_move(replay, tested)
        if not (allow_mate or allow_material):
            return evaluate_strong_move(replay)
        if context.probe_count > 3:
            raise IncompatibleGoodMoveContextError("no probe budget remains for Batch B")
        tested = self._select_tested_threat(replay, allow_mate, allow_material)
        if tested is None:
            return evaluate_strong_move(replay)
        context = self.verify_ignored_response(context, tested.response)
        if context.probe_count > 4:
            raise IncompatibleGoodMoveContextError("Batch B exceeded the P9 probe budget")
        return evaluate_strong_move(self.replay_lines(context), tested)

    def _select_tested_threat(
        self,
        replay: GoodMoveReplayContext,
        allow_mate: bool,
        allow_material: bool,
        only: ChessMove | None = None,
    ) -> GoodMoveTestedThreat | None:
        """First exact mate-in-one Q, else first (resource, Q) leaving a target capturable.

        Q ranges over the opponent's legal replies to M in canonical UCI order, excluding the
        Batch-A best response, which Batch A already observes.  No engine score is consulted.
        """

        played = replay.played.line.plies[0]
        mover = played.before.side_to_move
        line = replay.played.line.plies
        best = line[1].move.uci if len(line) > 1 else None
        responses = sorted(played.rules.legal_moves, key=lambda move: move.uci)
        if only is not None:
            responses = [move for move in responses if move.uci == only.uci]
        responses = [move for move in responses if move.uci != best]

        if allow_mate:
            for response in responses:
                if self._leaves_mate_in_one(played.position, response):
                    return GoodMoveTestedThreat(GoodMoveBenefitKind.MATE_THREAT, response)
        if not allow_material:
            return None
        resources = material_resources(played, mover)
        if not resources:
            return None
        capturable: dict[str, tuple[BasePieceIdentityMap, frozenset[BasePieceRef]]] = {}
        for resource in resources:
            for response in responses:
                if response.uci not in capturable:
                    capturable[response.uci] = self._capturable_after(played, response)
                identity, targets = capturable[response.uci]
                if any(
                    identity.current_piece(target) is not None and target in targets
                    for target in resource.targets
                ):
                    return GoodMoveTestedThreat(
                        GoodMoveBenefitKind.MATERIAL_THREAT, response, resource
                    )
        return None

    def _leaves_mate_in_one(self, position: PositionSnapshot, response: ChessMove) -> bool:
        """Whether some legal mover reply after Q is exact checkmate (exhaustive, one ply)."""

        after = self._apply(position, response)
        rules = self.tactical_rules.observe_tactics(after)
        if rules.position_id != after.position_id:
            raise IncompatibleGoodMoveContextError("Q observation belongs to another position")
        for reply in sorted(rules.legal_moves, key=lambda move: move.uci):
            mated = self._apply(after, reply)
            mated_rules = self.tactical_rules.observe_tactics(mated)
            if mated_rules.legal_moves:
                continue
            facts = self.facts.extract(mated)
            if facts.position_id != mated.position_id or mated_rules.position_id != (
                mated.position_id
            ):
                raise IncompatibleGoodMoveContextError("mate test evidence is unbound")
            if facts.side_to_move_checkmated != facts.side_to_move_in_check:
                raise IncompatibleGoodMoveContextError(
                    "mate test checkmate state contradicts check"
                )
            if facts.side_to_move_checkmated:
                return True
        return False

    def _capturable_after(
        self, played: GoodMoveReplayStepContext, response: ChessMove
    ) -> tuple[BasePieceIdentityMap, frozenset[BasePieceRef]]:
        """Play one exact Q ply; base pieces the original mover may then legally capture."""

        after = self._apply(played.position, response)
        delta = self.delta.analyze(played.position, response)
        facts = self.facts.extract(after)
        if (
            delta.before_position_id != played.position.position_id
            or delta.after_position_id != after.position_id
            or delta.move.uci != response.uci
            or facts.position_id != after.position_id
        ):
            raise IncompatibleGoodMoveContextError("Q ply evidence is unbound")
        try:
            identity = played.identity.advance(delta)
        except IncompatibleBadMoveContextError as error:
            raise IncompatibleGoodMoveContextError(
                "Q ply piece identity is inconsistent"
            ) from error
        if identity.position_id != after.position_id:
            raise IncompatibleGoodMoveContextError("Q ply identity is not bound to its position")
        mover = played.before.side_to_move
        targets = frozenset(
            base_ref(identity, capture.captured)
            for capture in facts.legal_captures
            if capture.capturer.color is mover
        )
        return identity, targets

    def _apply(self, position: PositionSnapshot, move: ChessMove) -> PositionSnapshot:
        try:
            return self.chess.apply_move(position, move)
        except _MOVE_ERRORS as error:
            raise IncompatibleGoodMoveContextError("selector move cannot be applied") from error


# ---- material (frozen P8 contract) ---------------------------------------------------------


def _piece_value(piece_type: PieceType) -> int:
    if piece_type not in PIECE_VALUES:
        raise IncompatibleGoodMoveContextError("kings carry no material value")
    return PIECE_VALUES[piece_type]


def _material_advantage(facts: PositionFacts, mover: Color) -> int:
    """Weighted material of ``mover`` minus the opponent's, from exact P4 counts."""

    def total(color: Color) -> int:
        counts = getattr(facts.material, color.value)
        return sum(
            getattr(counts, field) * PIECE_VALUES[kind] for kind, field in _COUNT_FIELD.items()
        )

    return total(mover) - total(mover.opposite)


def _traced_change(delta: BoardDelta, mover: Color) -> int:
    """Material-advantage change explained by the delta's exact capture/promotion events."""

    change = 0
    if delta.capture is not None:
        captured = delta.capture.captured
        value = _piece_value(captured.piece_type)
        change += -value if captured.color is mover else value
    for transition in delta.transitions:
        if transition.kind is PieceTransitionKind.PROMOTION:
            gain = _piece_value(transition.after.piece_type) - PIECE_VALUES[PieceType.PAWN]
            change += gain if transition.after.color is mover else -gain
    return change


def _material_evidence(
    line: GoodMoveReplayedLineContext, base_facts: PositionFacts, mover: Color
) -> MaterialLineEvidence:
    """Measure one replayed line from the original mover's side and decide its stable point.

    Plies: base = 0, first move = 1, first PV move = 2, ...  Stable when the line ends in exact
    checkmate, or when at least two further plies follow the last weighted-material change (or
    the first move, if nothing changed).  A stalemate ending must come after that point.
    """

    base_advantage = _material_advantage(base_facts, mover)
    previous = base_advantage
    last_change: int | None = None
    for step in line.plies:
        current = _material_advantage(step.facts, mover)
        if current - previous != _traced_change(step.delta, mover):
            raise IncompatibleGoodMoveContextError(
                "weighted material change is not traced by exact capture/promotion"
            )
        if current != previous:
            last_change = step.ply
        previous = current

    material_delta = previous - base_advantage
    final_ply = line.final.ply
    if line.ends_in_checkmate:
        return MaterialLineEvidence(line.probe_result.probe, material_delta, final_ply, True)

    reference = last_change if last_change is not None else line.plies[0].ply
    stable_at = reference + 2
    stable = stable_at < final_ply if line.ends_in_stalemate else stable_at <= final_ply
    return MaterialLineEvidence(
        line.probe_result.probe, material_delta, stable_at if stable else None
    )
