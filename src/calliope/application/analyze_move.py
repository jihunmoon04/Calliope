"""Analyze-one-move use case: validate input, run engine analyses, judge, project to DTOs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from calliope.application.ports.chess import ChessRulesPort
from calliope.application.ports.engine import EngineAnalysisPort
from calliope.contracts import (
    PUBLIC_SCHEMA_VERSION,
    AnalysisBudget,
    AnalyzeMoveRequest,
    JudgementSummary,
    MoveAnalysisResult,
    OutputMode,
)
from calliope.domain.engine import EngineLimit, EngineSettings, MoveJudgement
from calliope.errors import InvalidAnalysisBudgetError, UnsupportedOutputModeError
from calliope.services.judgement.move_judge import MoveJudge


@dataclass(slots=True)
class AnalyzeMoveService:
    chess: ChessRulesPort
    engine: EngineAnalysisPort
    judge: MoveJudge
    default_depth: int = 12
    default_multipv: int = 5

    def execute(self, request: AnalyzeMoveRequest) -> MoveAnalysisResult:
        options = request.options
        if options.output_mode is not OutputMode.STRUCTURED:
            raise UnsupportedOutputModeError(
                f"output mode {options.output_mode.value!r} is not supported yet"
            )
        settings = self._resolve_settings(options.budget)

        position = self.chess.position_from_fen(request.fen)
        move = self.chess.legal_move_from_uci(position, request.move_uci)

        position_analysis = self.engine.analyze(position, settings)
        played_analysis = self.engine.analyze(
            position, replace(settings, multipv=1), root_moves=(move,)
        )

        judgement = self.judge.judge(
            mover=position.side_to_move,
            move=move,
            position_analysis=position_analysis,
            played_analysis=played_analysis,
        )

        return MoveAnalysisResult(
            schema_version=PUBLIC_SCHEMA_VERSION,
            position_fen=position.fen,
            judgement=_summarize(judgement),
            claims=(),
            variations=(),
            commentary=None,
            metadata={
                "position_id": position.position_id,
                "engine": {
                    "name": position_analysis.engine.name,
                    "version": position_analysis.engine.version,
                },
                "analysis": {
                    "depth": settings.limit.depth,
                    "nodes": settings.limit.nodes,
                    "time_ms": settings.limit.time_ms,
                    "multipv": settings.multipv,
                    "threads": settings.threads,
                    "hash_mb": settings.hash_mb,
                },
                "forcedness": {
                    "acceptable_move_count": judgement.forcedness.acceptable_move_count,
                    "best_to_second_gap_cp": judgement.forcedness.best_to_second_gap_cp,
                },
            },
        )

    def _resolve_settings(self, budget: AnalysisBudget) -> EngineSettings:
        values: dict[str, Any] = {
            "depth": budget.depth,
            "nodes": budget.nodes,
            "time_ms": budget.time_ms,
            "multipv": budget.multipv,
        }
        for name, value in values.items():
            if value is not None and value <= 0:
                raise InvalidAnalysisBudgetError(f"{name} must be positive, got {value}")

        if budget.depth is None and budget.nodes is None and budget.time_ms is None:
            limit = EngineLimit(depth=self.default_depth)
        else:
            limit = EngineLimit(
                depth=budget.depth, nodes=budget.nodes, time_ms=budget.time_ms
            )
        multipv = budget.multipv if budget.multipv is not None else self.default_multipv
        return EngineSettings(limit=limit, multipv=multipv, threads=None, hash_mb=None)


def _summarize(judgement: MoveJudgement) -> JudgementSummary:
    return JudgementSummary(
        move_uci=judgement.move.uci,
        best_move_uci=judgement.best_move.uci,
        quality=judgement.quality.value,
        rank=judgement.rank,
        cp_loss=judgement.cp_loss,
        expected_score_loss=judgement.expected_score_loss,
        forcedness=judgement.forcedness.level.value,
    )
