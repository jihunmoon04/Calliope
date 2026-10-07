"""Deterministic preparation and bounded counterfactual protocol for P8 bad-move explanation.

``prepare`` validates that a MoveJudgement belongs to the supplied base position and builds the
exact first-move branch facts for the played move and the engine-best comparator, without any
engine access.  ``verify_counterfactuals`` runs the frozen P7 protocol (at most three probes in
two batches), validates the returned evidence, and builds the immediate punishment steps.
Neither draws a causal conclusion: P6 candidates stay DETECTED hypotheses and no cause is
classified here.
"""

from __future__ import annotations

from dataclasses import dataclass

from calliope.application.ports.chess import ChessRulesPort
from calliope.application.ports.tactics import TacticalObservation, TacticalObservationPort
from calliope.domain.analysis import (
    BoardDelta,
    CounterfactualBatchRequest,
    CounterfactualBatchResult,
    CounterfactualProbe,
    ProbeKind,
    ProbeResult,
    TacticalDetection,
    TerminalKind,
    TerminalOutcome,
)
from calliope.domain.chess import ChessMove, Color, PositionFacts, PositionSnapshot
from calliope.domain.engine import (
    EngineIdentity,
    EngineScore,
    EngineSettings,
    MoveJudgement,
    MoveQuality,
)
from calliope.errors import (
    IllegalMoveError,
    IncompatibleBadMoveContextError,
    InvalidUciError,
    NullMoveNotAllowedError,
)
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.explanation.piece_identity import BasePieceIdentityMap
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.tactics import TacticalDetector

ELIGIBLE_QUALITIES = frozenset({MoveQuality.MISTAKE, MoveQuality.BLUNDER})


def _fail(message: str) -> IncompatibleBadMoveContextError:
    return IncompatibleBadMoveContextError(message)


@dataclass(frozen=True, slots=True)
class FirstMoveBranchContext:
    """Exact deterministic facts for one first move played from the common base."""

    move: ChessMove
    position: PositionSnapshot
    facts: PositionFacts
    delta: BoardDelta
    rules: TacticalObservation
    detection: TacticalDetection
    identity: BasePieceIdentityMap


@dataclass(frozen=True, slots=True)
class BadMovePreparedContext:
    """Validated eligible context with independent actual and comparator branches."""

    base: PositionSnapshot
    judgement: MoveJudgement

    played_move: ChessMove
    comparator_move: ChessMove

    base_facts: PositionFacts
    base_rules: TacticalObservation
    root_identity: BasePieceIdentityMap

    actual: FirstMoveBranchContext
    comparator: FirstMoveBranchContext


@dataclass(frozen=True, slots=True)
class BadMoveNotApplicable:
    """Validated context whose move quality is outside P8; no branch facts are built."""

    base: PositionSnapshot
    judgement: MoveJudgement
    played_move: ChessMove
    comparator_move: ChessMove


@dataclass(frozen=True, slots=True)
class PunishmentBranchContext:
    """Exact deterministic facts for the opponent's punishment move after one first move."""

    before: PositionSnapshot
    move: ChessMove
    position: PositionSnapshot
    facts: PositionFacts
    delta: BoardDelta
    rules: TacticalObservation
    detection: TacticalDetection
    identity: BasePieceIdentityMap


@dataclass(frozen=True, slots=True)
class BadMoveCounterfactualContext:
    """Validated P7 evidence for one eligible bad move; no cause is decided here.

    ``comparator_strictly_better`` is True only when the comparator refutation is strictly
    better for the original mover under the mate-aware P7 ordering, False when the ordering was
    established and the comparator is equal or worse, and None when no safe ordering exists
    (a stalemate on either side).
    """

    prepared: BadMovePreparedContext
    settings: EngineSettings

    batch_a: CounterfactualBatchResult
    actual_refutation: ProbeResult
    comparator_refutation: ProbeResult

    punishment_move: ChessMove | None
    actual_punishment: PunishmentBranchContext | None

    same_punishment_legal_after_comparator: bool | None

    batch_b: CounterfactualBatchResult | None
    comparator_replay: ProbeResult | None
    comparator_punishment: PunishmentBranchContext | None

    engine_identity: EngineIdentity | None
    comparator_strictly_better: bool | None

    @property
    def probe_count(self) -> int:
        batch_b = len(self.batch_b.results) if self.batch_b is not None else 0
        return len(self.batch_a.results) + batch_b


def _outcome_key(outcome: EngineScore | TerminalOutcome, mover: Color) -> tuple[int, int] | None:
    """Total order key for one P7 outcome from the mover's view; None if not comparable.

    Rank 2 is a mover-winning mate (shorter is better), rank 1 a centipawn score, rank 0 a
    mover-losing mate (later is better).  An exact checkmate is a mate at distance zero.
    """

    if isinstance(outcome, TerminalOutcome):
        if outcome.kind is TerminalKind.STALEMATE:
            return None
        return (2, 0) if outcome.winner is mover else (0, 0)
    if outcome.mate is not None:
        moves = outcome.mate.moves
        return (2, -moves) if outcome.mate.winner is mover else (0, moves)
    centipawns = outcome.centipawns_for(mover)
    assert centipawns is not None
    return (1, centipawns)


def comparator_strictly_better(
    mover: Color,
    actual: EngineScore | TerminalOutcome,
    comparator: EngineScore | TerminalOutcome,
) -> bool | None:
    """Mate-aware strict ordering of two same-settings P7 outcomes; no thresholds."""

    actual_key = _outcome_key(actual, mover)
    comparator_key = _outcome_key(comparator, mover)
    if actual_key is None or comparator_key is None:
        return None
    return comparator_key > actual_key


def _outcome(result: ProbeResult) -> EngineScore | TerminalOutcome:
    if result.terminal is not None:
        return result.terminal
    assert result.engine_analysis is not None
    return result.engine_analysis.best_line.score


@dataclass(slots=True)
class BadMoveExplainer:
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
    ) -> BadMovePreparedContext | BadMoveNotApplicable:
        """Validate the judgement context and build deterministic first-move branches."""

        if judgement.position_id != base.position_id:
            raise _fail("judgement belongs to another position")
        if judgement.mover is not base.side_to_move:
            raise _fail("judgement mover is not the side to move")

        played_move = self.chess.legal_move_from_uci(base, played.uci)
        judged_move = self._canonical(base, judgement.move, "judged move")
        if played_move.uci != judged_move.uci:
            raise _fail("played move differs from the judged move")
        comparator_move = self._canonical(base, judgement.best_move, "comparator")

        if judgement.quality not in ELIGIBLE_QUALITIES:
            return BadMoveNotApplicable(
                base=base,
                judgement=judgement,
                played_move=played_move,
                comparator_move=comparator_move,
            )
        if comparator_move.uci == played_move.uci:
            raise _fail("eligible bad move must differ from its comparator")

        base_facts = self.facts.extract(base)
        base_rules = self.tactical_rules.observe_tactics(base)
        root_identity = BasePieceIdentityMap.from_facts(base_facts)
        if base_facts.position_id != base.position_id:
            raise _fail("base facts belong to another position")
        if base_rules.position_id != base.position_id:
            raise _fail("base tactical observation belongs to another position")
        if base_rules.side_to_move is not base.side_to_move:
            raise _fail("base tactical observation has the wrong side to move")
        if not (root_identity.base_position_id == root_identity.position_id == base.position_id):
            raise _fail("root identity is not bound to the base position")

        def branch(move: ChessMove) -> FirstMoveBranchContext:
            step = self._step(base, move, base_facts, base_rules, root_identity, "base", base)
            return FirstMoveBranchContext(
                move=move,
                position=step.position,
                facts=step.facts,
                delta=step.delta,
                rules=step.rules,
                detection=step.detection,
                identity=step.identity,
            )

        return BadMovePreparedContext(
            base=base,
            judgement=judgement,
            played_move=played_move,
            comparator_move=comparator_move,
            base_facts=base_facts,
            base_rules=base_rules,
            root_identity=root_identity,
            actual=branch(played_move),
            comparator=branch(comparator_move),
        )

    def verify_counterfactuals(
        self, prepared: BadMovePreparedContext, settings: EngineSettings
    ) -> BadMoveCounterfactualContext:
        """Run the frozen P8 P7 protocol and validate its evidence; decides no cause.

        Batch A is always REFUTATION(B,M), REFUTATION(B,A).  Batch B is exactly
        IGNORE_THREAT(B,A,P), run only when the actual punishment P exists and its canonical UCI
        is a legal move after A.  At most three probes in two P7 calls.
        """

        base = prepared.base
        actual_branch, comparator_branch = prepared.actual, prepared.comparator

        request_a = CounterfactualBatchRequest(
            probes=(
                CounterfactualProbe(ProbeKind.REFUTATION, base, prepared.played_move),
                CounterfactualProbe(ProbeKind.REFUTATION, base, prepared.comparator_move),
            ),
            settings=settings,
        )
        batch_a = self.counterfactual.execute(request_a)
        actual, comparator = self._check_batch(
            batch_a, request_a, (actual_branch, comparator_branch), (None, None), base
        )
        engine_identity = self._engine_identity(batch_a, None)

        punishment: ChessMove | None = None
        actual_punishment: PunishmentBranchContext | None = None
        legal_after_comparator: bool | None = None
        batch_b: CounterfactualBatchResult | None = None
        replay: ProbeResult | None = None
        comparator_punishment: PunishmentBranchContext | None = None

        if actual.engine_analysis is not None:
            punishment = self._canonical(
                actual_branch.position,
                actual.engine_analysis.best_line.first_move,
                "engine punishment",
            )
            actual_punishment = self._punishment(base, actual_branch, punishment)

            # Frozen rule: canonical-UCI membership, never exception flow.
            comparator_legal = {move.uci for move in comparator_branch.rules.legal_moves}
            legal_after_comparator = punishment.uci in comparator_legal
            if legal_after_comparator:
                replayed = self._canonical(
                    comparator_branch.position, punishment, "comparator punishment"
                )
                request_b = CounterfactualBatchRequest(
                    probes=(
                        CounterfactualProbe(
                            ProbeKind.IGNORE_THREAT,
                            base,
                            intervention_move=prepared.comparator_move,
                            execution_move=replayed,
                        ),
                    ),
                    settings=settings,
                )
                batch_b = self.counterfactual.execute(request_b)
                (replay,) = self._check_batch(
                    batch_b, request_b, (comparator_branch,), ((replayed,),), base
                )
                engine_identity = self._engine_identity(batch_b, engine_identity)
                comparator_punishment = self._punishment(base, comparator_branch, replayed)

        return BadMoveCounterfactualContext(
            prepared=prepared,
            settings=settings,
            batch_a=batch_a,
            actual_refutation=actual,
            comparator_refutation=comparator,
            punishment_move=punishment,
            actual_punishment=actual_punishment,
            same_punishment_legal_after_comparator=legal_after_comparator,
            batch_b=batch_b,
            comparator_replay=replay,
            comparator_punishment=comparator_punishment,
            engine_identity=engine_identity,
            comparator_strictly_better=comparator_strictly_better(
                base.side_to_move, _outcome(actual), _outcome(comparator)
            ),
        )

    # ---- evidence checks -----------------------------------------------------------------

    @staticmethod
    def _check_batch(
        batch: CounterfactualBatchResult,
        request: CounterfactualBatchRequest,
        branches: tuple[FirstMoveBranchContext, ...],
        roots: tuple[tuple[ChessMove, ...] | None, ...],
        base: PositionSnapshot,
    ) -> tuple[ProbeResult, ...]:
        if batch.settings != request.settings:
            raise _fail("P7 batch used different settings")
        if len(batch.results) != len(request.probes):
            raise _fail("P7 batch returned the wrong number of results")

        for result, probe, branch, root in zip(
            batch.results, request.probes, branches, roots, strict=True
        ):
            if result.probe != probe:
                raise _fail("P7 result does not echo the requested probe")
            if result.analysis_position != branch.position:
                raise _fail("P7 result analysed a different position")
            if result.intervention_position != branch.position:
                raise _fail("P7 result has a different intervention position")

            if result.engine_analysis is None:
                if root is not None:
                    raise _fail("forced P7 replay unexpectedly ended in a terminal position")
                BadMoveExplainer._check_terminal(result, branch, base)
                continue

            if result.root_moves is None:
                if root is not None:
                    raise _fail("forced P7 replay lost its root move")
            elif root is None or tuple(m.uci for m in result.root_moves) != tuple(
                m.uci for m in root
            ):
                raise _fail("P7 result has unexpected root moves")

            analysis = result.engine_analysis
            if analysis.settings != request.settings:
                raise _fail("P7 engine analysis used different settings")
            if analysis.position_id != branch.position.position_id:
                raise _fail("P7 engine analysis belongs to another position")
            if len(analysis.lines) != 1 or analysis.best_line.rank != 1:
                raise _fail("P7 engine analysis must contain exactly the rank-1 line")
            if root is not None and analysis.best_line.first_move.uci != root[0].uci:
                raise _fail("P7 engine line does not start with the forced move")
        return batch.results

    @staticmethod
    def _check_terminal(
        result: ProbeResult, branch: FirstMoveBranchContext, base: PositionSnapshot
    ) -> None:
        terminal = result.terminal
        assert terminal is not None
        if branch.rules.legal_moves:
            raise _fail("P7 reports a terminal position that still has legal moves")
        if branch.facts.side_to_move_checkmated:
            expected = TerminalOutcome(TerminalKind.CHECKMATE, base.side_to_move)
        else:
            expected = TerminalOutcome(TerminalKind.STALEMATE, None)
        if terminal != expected:
            raise _fail("P7 terminal outcome contradicts the exact branch facts")

    @staticmethod
    def _engine_identity(
        batch: CounterfactualBatchResult, expected: EngineIdentity | None
    ) -> EngineIdentity | None:
        identities: list[EngineIdentity] = []
        for result in batch.results:
            if result.engine_analysis is not None:
                engine = result.engine_analysis.engine
                if engine not in identities:
                    identities.append(engine)
        if len(identities) > 1:
            raise _fail("engine identity differs within one P7 batch")
        if not identities:
            return expected
        if expected is not None and identities[0] != expected:
            raise _fail("engine identity differs across P7 batches")
        return identities[0]

    # ---- deterministic steps -------------------------------------------------------------

    def _punishment(
        self,
        base: PositionSnapshot,
        branch: FirstMoveBranchContext,
        move: ChessMove,
    ) -> PunishmentBranchContext:
        step = self._step(
            branch.position, move, branch.facts, branch.rules, branch.identity, "branch", base
        )
        return PunishmentBranchContext(
            before=branch.position,
            move=move,
            position=step.position,
            facts=step.facts,
            delta=step.delta,
            rules=step.rules,
            detection=step.detection,
            identity=step.identity,
        )

    def _canonical(self, position: PositionSnapshot, move: ChessMove, label: str) -> ChessMove:
        # A judgement or engine move that is not legal where it claims to be played means that
        # evidence does not describe this position: a P8 context contradiction.
        try:
            return self.chess.legal_move_from_uci(position, move.uci)
        except (IllegalMoveError, InvalidUciError, NullMoveNotAllowedError) as error:
            raise _fail(f"{label} is not legal in its position") from error

    def _step(
        self,
        before: PositionSnapshot,
        move: ChessMove,
        before_facts: PositionFacts,
        before_rules: TacticalObservation,
        before_identity: BasePieceIdentityMap,
        label: str,
        base: PositionSnapshot,
    ) -> _Step:
        mover = before.side_to_move
        after = self.chess.apply_move(before, move)
        delta = self.delta.analyze(before, move)
        after_facts = self.facts.extract(after)
        after_rules = self.tactical_rules.observe_tactics(after)

        if after.side_to_move is not mover.opposite:
            raise _fail("after position does not have the opponent to move")
        if delta.before_position_id != before.position_id:
            raise _fail(f"board delta does not start from the {label} position")
        if delta.after_position_id != after.position_id:
            raise _fail("board delta does not end at the branch position")
        if delta.move.uci != move.uci:
            raise _fail("board delta describes another move")
        if delta.mover is not mover:
            raise _fail("board delta has the wrong mover")
        if after_facts.position_id != after.position_id:
            raise _fail("branch facts belong to another position")
        if after_rules.position_id != after.position_id:
            raise _fail("branch tactical observation belongs to another position")
        if after_rules.side_to_move is not mover.opposite:
            raise _fail("branch tactical observation has the wrong side to move")

        detection = self.detector.detect(
            before=before_facts,
            after=after_facts,
            delta=delta,
            before_rules=before_rules,
            after_rules=after_rules,
        )
        if detection.before_position_id != before.position_id:
            raise _fail(f"tactical detection does not start from the {label} position")
        if detection.after_position_id != after.position_id:
            raise _fail("tactical detection does not end at the branch position")
        if detection.move.uci != move.uci:
            raise _fail("tactical detection describes another move")
        if detection.mover is not mover:
            raise _fail("tactical detection has the wrong mover")

        identity = before_identity.advance(delta)
        if identity.base_position_id != base.position_id:
            raise _fail("branch identity is not anchored to the base position")
        if identity.position_id != after.position_id:
            raise _fail("branch identity is not bound to the branch position")

        return _Step(after, after_facts, delta, after_rules, detection, identity)


@dataclass(frozen=True, slots=True)
class _Step:
    position: PositionSnapshot
    facts: PositionFacts
    delta: BoardDelta
    rules: TacticalObservation
    detection: TacticalDetection
    identity: BasePieceIdentityMap
