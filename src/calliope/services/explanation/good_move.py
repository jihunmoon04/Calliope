"""P9 context validation and representative alternative selection, without analysis."""

from __future__ import annotations

from dataclasses import dataclass

from calliope.application.ports.chess import ChessRulesPort
from calliope.domain.analysis import AlternativeScope, GoodMoveMode, RepresentativeAlternative
from calliope.domain.chess import ChessMove, PositionSnapshot
from calliope.domain.engine import EngineAnalysis, ForcednessLevel, MoveJudgement, MoveQuality
from calliope.errors import (
    IllegalMoveError,
    IncompatibleGoodMoveContextError,
    InvalidUciError,
    NullMoveNotAllowedError,
)

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


@dataclass(slots=True)
class GoodMoveExplainer:
    chess: ChessRulesPort

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
