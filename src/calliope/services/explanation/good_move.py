"""P9 preparation, deterministic branches and bounded P7 evidence compatibility."""

from __future__ import annotations

from dataclasses import dataclass, replace

from calliope.application.ports.chess import ChessRulesPort
from calliope.application.ports.tactics import TacticalObservation, TacticalObservationPort
from calliope.domain.analysis import (
    AlternativeScope,
    BoardDelta,
    CounterfactualBatchRequest,
    CounterfactualBatchResult,
    CounterfactualProbe,
    GoodMoveMode,
    ProbeKind,
    ProbeResult,
    RepresentativeAlternative,
    TacticalDetection,
    TerminalKind,
    TerminalOutcome,
)
from calliope.domain.chess import ChessMove, PositionFacts, PositionSnapshot
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
from calliope.services.explanation.piece_identity import BasePieceIdentityMap
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.tactics import TacticalDetector

ELIGIBLE_QUALITIES = frozenset({MoveQuality.BEST, MoveQuality.EXCELLENT, MoveQuality.GOOD})


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
