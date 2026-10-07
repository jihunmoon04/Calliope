"""Deterministic preparation for P8 bad-move explanation.

This layer validates that a MoveJudgement belongs to the supplied base position and builds the
exact first-move branch facts for the played move and the engine-best comparator.  It performs
no engine analysis and draws no causal conclusion: P6 candidates stay DETECTED hypotheses.
"""

from __future__ import annotations

from dataclasses import dataclass

from calliope.application.ports.chess import ChessRulesPort
from calliope.application.ports.tactics import TacticalObservation, TacticalObservationPort
from calliope.domain.analysis import BoardDelta, TacticalDetection
from calliope.domain.chess import ChessMove, PositionFacts, PositionSnapshot
from calliope.domain.engine import MoveJudgement, MoveQuality
from calliope.errors import (
    IllegalMoveError,
    IncompatibleBadMoveContextError,
    InvalidUciError,
    NullMoveNotAllowedError,
)
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


@dataclass(slots=True)
class BadMoveExplainer:
    chess: ChessRulesPort
    facts: PositionFactExtractor
    delta: BoardDeltaAnalyzer
    tactical_rules: TacticalObservationPort
    detector: TacticalDetector

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
        judged_move = self._judged(base, judgement.move, "judged move")
        if played_move.uci != judged_move.uci:
            raise _fail("played move differs from the judged move")
        comparator_move = self._judged(base, judgement.best_move, "comparator")

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
            return self._branch(base, move, base_facts, base_rules, root_identity)

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

    def _judged(self, base: PositionSnapshot, move: ChessMove, label: str) -> ChessMove:
        # A judgement move that is not legal here means the judgement does not describe this
        # position; that is a P8 context contradiction rather than bad caller input.
        try:
            return self.chess.legal_move_from_uci(base, move.uci)
        except (IllegalMoveError, InvalidUciError, NullMoveNotAllowedError) as error:
            raise _fail(f"{label} is not legal in the base position") from error

    def _branch(
        self,
        base: PositionSnapshot,
        move: ChessMove,
        base_facts: PositionFacts,
        base_rules: TacticalObservation,
        root_identity: BasePieceIdentityMap,
    ) -> FirstMoveBranchContext:
        mover = base.side_to_move
        after = self.chess.apply_move(base, move)
        delta = self.delta.analyze(base, move)
        after_facts = self.facts.extract(after)
        after_rules = self.tactical_rules.observe_tactics(after)

        if after.side_to_move is not mover.opposite:
            raise _fail("after position does not have the opponent to move")
        if delta.before_position_id != base.position_id:
            raise _fail("board delta does not start from the base position")
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
            before=base_facts,
            after=after_facts,
            delta=delta,
            before_rules=base_rules,
            after_rules=after_rules,
        )
        if detection.before_position_id != base.position_id:
            raise _fail("tactical detection does not start from the base position")
        if detection.after_position_id != after.position_id:
            raise _fail("tactical detection does not end at the branch position")
        if detection.move.uci != move.uci:
            raise _fail("tactical detection describes another move")
        if detection.mover is not mover:
            raise _fail("tactical detection has the wrong mover")

        identity = root_identity.advance(delta)
        if identity.base_position_id != base.position_id:
            raise _fail("branch identity is not anchored to the base position")
        if identity.position_id != after.position_id:
            raise _fail("branch identity is not bound to the branch position")

        return FirstMoveBranchContext(
            move=move,
            position=after,
            facts=after_facts,
            delta=delta,
            rules=after_rules,
            detection=detection,
            identity=identity,
        )
