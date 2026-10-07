"""Deterministic interpretation of Stockfish observations as a MoveJudgement.

Pure policy over normalized engine models: no engine calls, no board access.
"""

from __future__ import annotations

from dataclasses import dataclass

from calliope.domain.chess.move import ChessMove
from calliope.domain.chess.position import Color
from calliope.domain.engine.analysis import EngineAnalysis, EngineLine
from calliope.domain.engine.judgement import (
    Forcedness,
    ForcednessLevel,
    MoveJudgement,
    MoveQuality,
)
from calliope.domain.engine.score import WDL, EngineScore
from calliope.errors import IncompatibleAnalysisError

_EPS = 1e-9
_ACCEPTABLE = frozenset({MoveQuality.BEST, MoveQuality.EXCELLENT, MoveQuality.GOOD})


@dataclass(frozen=True, slots=True)
class MoveJudgementPolicy:
    """MVP provisional calibration."""

    expected_excellent: float = 0.01
    expected_good: float = 0.03
    expected_inaccuracy: float = 0.08
    expected_mistake: float = 0.18

    cp_excellent: int = 20
    cp_good: int = 50
    cp_inaccuracy: int = 100
    cp_mistake: int = 200

    expected_noise_tolerance: float = 0.01
    cp_noise_tolerance: int = 20


@dataclass(frozen=True, slots=True)
class _Assessment:
    quality: MoveQuality
    cp_loss: int | None
    expected_score_loss: float | None


class MoveJudge:
    def __init__(self, policy: MoveJudgementPolicy | None = None) -> None:
        self._policy = policy or MoveJudgementPolicy()

    def judge(
        self,
        *,
        mover: Color,
        move: ChessMove,
        position_analysis: EngineAnalysis,
        played_analysis: EngineAnalysis,
    ) -> MoveJudgement:
        self._validate(move, position_analysis, played_analysis)

        lines = sorted(position_analysis.lines, key=lambda line: line.rank)
        best_line = lines[0]
        played_line = next(
            (line for line in lines if line.first_move.uci == move.uci), None
        )
        rank = played_line.rank if played_line is not None else None
        source = played_line if played_line is not None else played_analysis.best_line

        if rank == 1:
            assessment = self._assess(mover, best_line, best_line, exact_best=True)
        else:
            assessment = self._assess(mover, best_line, source)

        return MoveJudgement(
            position_id=position_analysis.position_id,
            mover=mover,
            move=move,
            best_move=best_line.first_move,
            quality=assessment.quality,
            rank=rank,
            best_score=best_line.score,
            played_score=source.score,
            cp_loss=assessment.cp_loss,
            expected_score_loss=assessment.expected_score_loss,
            forcedness=self._forcedness(mover, lines),
        )

    # -- validation -------------------------------------------------------

    @staticmethod
    def _validate(
        move: ChessMove, position: EngineAnalysis, played: EngineAnalysis
    ) -> None:
        if position.position_id != played.position_id:
            raise IncompatibleAnalysisError("analyses are for different positions")
        if position.engine != played.engine:
            raise IncompatibleAnalysisError("analyses use different engines")
        ps, qs = position.settings, played.settings
        if ps.limit != qs.limit:
            raise IncompatibleAnalysisError("analyses use different engine limits")
        if ps.threads != qs.threads:
            raise IncompatibleAnalysisError("analyses use different thread counts")
        if ps.hash_mb != qs.hash_mb:
            raise IncompatibleAnalysisError("analyses use different hash sizes")

        if qs.multipv != 1 or len(played.lines) != 1:
            raise IncompatibleAnalysisError("played analysis must be single-line")
        if played.best_line.first_move.uci != move.uci:
            raise IncompatibleAnalysisError("played analysis root is not the played move")

        ranks = sorted(line.rank for line in position.lines)
        if ranks != list(range(1, len(ranks) + 1)):
            raise IncompatibleAnalysisError("position analysis ranks are not contiguous")
        ucis = [line.first_move.uci for line in position.lines]
        if len(ucis) != len(set(ucis)):
            raise IncompatibleAnalysisError("position analysis has duplicate candidates")

    # -- assessment -------------------------------------------------------

    def _assess(
        self,
        mover: Color,
        best: EngineLine,
        played: EngineLine,
        *,
        exact_best: bool = False,
    ) -> _Assessment:
        cp_loss = self._cp_loss(mover, best.score, played.score)
        expected_loss = self._expected_loss(mover, best.wdl, played.wdl)

        if exact_best:
            quality = MoveQuality.BEST
        elif best.score.mate is not None or played.score.mate is not None:
            quality = self._mate_quality(mover, best.score, played.score)
        elif expected_loss is not None:
            quality = self._grade(
                expected_loss,
                self._policy.expected_excellent,
                self._policy.expected_good,
                self._policy.expected_inaccuracy,
                self._policy.expected_mistake,
            )
        else:
            assert cp_loss is not None
            quality = self._grade(
                cp_loss,
                self._policy.cp_excellent,
                self._policy.cp_good,
                self._policy.cp_inaccuracy,
                self._policy.cp_mistake,
            )
        return _Assessment(quality, cp_loss, expected_loss)

    @staticmethod
    def _grade(
        loss: float, excellent: float, good: float, inaccuracy: float, mistake: float
    ) -> MoveQuality:
        if loss <= excellent + _EPS:
            return MoveQuality.EXCELLENT
        if loss <= good + _EPS:
            return MoveQuality.GOOD
        if loss <= inaccuracy + _EPS:
            return MoveQuality.INACCURACY
        if loss <= mistake + _EPS:
            return MoveQuality.MISTAKE
        return MoveQuality.BLUNDER

    def _cp_loss(
        self, mover: Color, best: EngineScore, played: EngineScore
    ) -> int | None:
        best_cp = best.centipawns_for(mover)
        played_cp = played.centipawns_for(mover)
        if best_cp is None or played_cp is None:
            return None
        raw = best_cp - played_cp
        if raw >= 0:
            return raw
        if -raw <= self._policy.cp_noise_tolerance:
            return 0
        raise IncompatibleAnalysisError("played move scores better than best beyond noise")

    def _expected_loss(
        self, mover: Color, best: WDL | None, played: WDL | None
    ) -> float | None:
        if best is None or played is None:
            return None
        raw = best.expected_score(mover) - played.expected_score(mover)
        if raw >= 0.0:
            return raw
        if -raw <= self._policy.expected_noise_tolerance + _EPS:
            return 0.0
        raise IncompatibleAnalysisError(
            "played move has better expected score than best beyond noise"
        )

    @staticmethod
    def _mate_view(score: EngineScore, mover: Color) -> tuple[bool, int] | None:
        """(mover_is_winner, distance) for a mate score, else None."""

        if score.mate is None:
            return None
        return score.mate.winner is mover, score.mate.moves

    @staticmethod
    def _slower_grade(delta: int) -> MoveQuality:
        if delta == 0:
            return MoveQuality.EXCELLENT
        if delta == 1:
            return MoveQuality.GOOD
        if delta <= 3:
            return MoveQuality.INACCURACY
        return MoveQuality.MISTAKE

    def _mate_quality(
        self, mover: Color, best: EngineScore, played: EngineScore
    ) -> MoveQuality:
        b = self._mate_view(best, mover)
        p = self._mate_view(played, mover)

        if b is None:
            # best is a normal score, so played involves a mate.
            assert p is not None
            if p[0]:
                raise IncompatibleAnalysisError(
                    "played mate for mover contradicts non-mate best"
                )
            return MoveQuality.BLUNDER

        b_wins, b_moves = b
        if b_wins:
            if p is None or not p[0]:
                return MoveQuality.BLUNDER
            if p[1] < b_moves:
                raise IncompatibleAnalysisError("played mate is faster than best mate")
            return self._slower_grade(p[1] - b_moves)

        # best is a forced loss for the mover
        if p is None or p[0]:
            raise IncompatibleAnalysisError("played escapes a forced loss that best does not")
        if p[1] > b_moves:
            raise IncompatibleAnalysisError("played loses later than best")
        return self._slower_grade(b_moves - p[1])

    # -- forcedness -------------------------------------------------------

    def _candidate_acceptable(
        self, mover: Color, best: EngineLine, candidate: EngineLine
    ) -> bool:
        b = self._mate_view(best.score, mover)
        if b is not None and b[0]:
            p = self._mate_view(candidate.score, mover)
            if p is not None and p[0] and p[1] < b[1]:
                raise IncompatibleAnalysisError("candidate mate is faster than best mate")
            return p is not None and p[0]
        return self._assess(mover, best, candidate).quality in _ACCEPTABLE

    def _forcedness(self, mover: Color, lines: list[EngineLine]) -> Forcedness:
        best = lines[0]
        gap = self._gap(mover, best, lines[1]) if len(lines) > 1 else None

        b = self._mate_view(best.score, mover)
        if len(lines) == 1 or (b is not None and not b[0]):
            return Forcedness(ForcednessLevel.UNKNOWN, None, gap)

        acceptable = 1
        unacceptable_seen = False
        for candidate in lines[1:]:
            if not self._candidate_acceptable(mover, best, candidate):
                unacceptable_seen = True
                break
            acceptable += 1

        if unacceptable_seen:
            count: int | None = acceptable
            if acceptable == 1:
                level = ForcednessLevel.ONLY_MOVE
            elif acceptable == 2:
                level = ForcednessLevel.NARROW
            elif acceptable <= 4:
                level = ForcednessLevel.FLEXIBLE
            else:
                level = ForcednessLevel.MANY_EQUIVALENT
        else:
            count = None
            if acceptable >= 5:
                level = ForcednessLevel.MANY_EQUIVALENT
            elif acceptable >= 3:
                level = ForcednessLevel.FLEXIBLE
            else:
                level = ForcednessLevel.UNKNOWN
        return Forcedness(level, count, gap)

    def _gap(self, mover: Color, best: EngineLine, second: EngineLine) -> int | None:
        best_cp = best.score.centipawns_for(mover)
        second_cp = second.score.centipawns_for(mover)
        if best_cp is None or second_cp is None:
            return None
        raw = best_cp - second_cp
        if raw >= 0:
            return raw
        if -raw <= self._policy.cp_noise_tolerance:
            return 0
        raise IncompatibleAnalysisError("second candidate scores better than best beyond noise")
