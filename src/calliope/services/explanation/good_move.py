"""P9 preparation and deterministic first-move branches, without engine analysis."""

from __future__ import annotations

from dataclasses import dataclass

from calliope.application.ports.chess import ChessRulesPort
from calliope.application.ports.tactics import TacticalObservation, TacticalObservationPort
from calliope.domain.analysis import (
    AlternativeScope,
    BoardDelta,
    GoodMoveMode,
    RepresentativeAlternative,
    TacticalDetection,
)
from calliope.domain.chess import ChessMove, PositionFacts, PositionSnapshot
from calliope.domain.engine import EngineAnalysis, ForcednessLevel, MoveJudgement, MoveQuality
from calliope.errors import (
    IllegalMoveError,
    IncompatibleBadMoveContextError,
    IncompatibleGoodMoveContextError,
    InvalidUciError,
    NullMoveNotAllowedError,
)
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


@dataclass(slots=True)
class GoodMoveExplainer:
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
