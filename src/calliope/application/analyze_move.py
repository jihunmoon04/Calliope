"""Analyze-one-move use case: validate, judge, explain strictly, optionally render, project.

All engine work of one request (judgement plus every P7 probe made while explaining) runs
inside one request-wide engine session; P12 rendering and public projection run after it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from calliope.application.explanation import COUNTERFACTUAL_SETTINGS, MoveExplanationPipeline
from calliope.application.ports.chess import ChessRulesPort
from calliope.application.ports.engine import EngineAnalysisPort, EngineRequestSessionPort
from calliope.application.projection import (
    project_claims,
    project_commentary,
    project_selected_ids,
)
from calliope.contracts import (
    PUBLIC_SCHEMA_VERSION,
    AnalysisBudget,
    AnalyzeMoveRequest,
    JudgementSummary,
    MoveAnalysisResult,
    OutputMode,
)
from calliope.domain.engine import EngineAnalysis, EngineLimit, EngineSettings, MoveJudgement
from calliope.errors import (
    ClaimProjectionError,
    CrossSearchInversionError,
    FeatureUnavailableError,
    InvalidAnalysisBudgetError,
    UnsupportedOutputModeError,
)
from calliope.services.explanation import DeterministicExplanationRenderer
from calliope.services.judgement.move_judge import MoveJudge

JUDGEMENT_THREADS = 1
JUDGEMENT_HASH_MB = 16
"""Fixed non-budget judgement engine options; not public knobs in schema 0.2."""


@dataclass(slots=True)
class AnalyzeMoveService:
    chess: ChessRulesPort
    engine: EngineAnalysisPort
    sessions: EngineRequestSessionPort
    judge: MoveJudge
    explanations: MoveExplanationPipeline
    renderer: DeterministicExplanationRenderer
    default_depth: int = 12
    default_multipv: int = 5

    def execute(self, request: AnalyzeMoveRequest) -> MoveAnalysisResult:
        options = request.options
        if options.allow_heuristic_claims:
            raise FeatureUnavailableError("heuristic claims are not available in strict mode")
        # Exact members only: a plain "commentary" string equals the StrEnum value but would
        # skip the identity branch below and silently behave as STRUCTURED.
        if type(options.output_mode) is not OutputMode:
            raise UnsupportedOutputModeError(f"output mode {options.output_mode!r} is unsupported")
        settings = self._resolve_settings(options.budget)

        position = self.chess.position_from_fen(request.fen)
        move = self.chess.legal_move_from_uci(position, request.move_uci)

        # One request-wide engine session: judgement and every P7 probe, nothing else.
        with self.sessions.request_session():
            position_analysis = self.engine.analyze(position, settings)
            played_analysis = self.engine.analyze(
                position, replace(settings, multipv=1), root_moves=(move,)
            )
            try:
                judgement = self.judge.judge(
                    mover=position.side_to_move,
                    move=move,
                    position_analysis=position_analysis,
                    played_analysis=played_analysis,
                )
            except CrossSearchInversionError:
                # P2-C1: one same-session paired search of (initial best, played); at most once.
                comparison_analysis = self.engine.analyze(
                    position,
                    replace(settings, multipv=2),
                    root_moves=(position_analysis.best_line.first_move, move),
                )
                judgement = self.judge.judge_reconciled(
                    mover=position.side_to_move,
                    move=move,
                    position_analysis=position_analysis,
                    played_analysis=played_analysis,
                    comparison_analysis=comparison_analysis,
                )
            outcome = self.explanations.explain(position, move, judgement, position_analysis)

        # Output mode branches only here, after P11 closure and outside the engine session.
        if (
            outcome.graph.claims is not outcome.claims
            or outcome.graph.base_position_id != position.position_id
        ):
            raise ClaimProjectionError(
                "public claims must be the validated P11 claims of this move"
            )
        claims = project_claims(outcome.claims)
        commentary = None
        if options.output_mode is OutputMode.COMMENTARY:
            commentary = project_commentary(self.renderer.render(outcome.graph, outcome.selection))

        return MoveAnalysisResult(
            schema_version=PUBLIC_SCHEMA_VERSION,
            position_fen=position.fen,
            judgement=_summarize(judgement),
            claims=claims,
            selected_claim_ids=project_selected_ids(claims, outcome.selection.selected_claim_ids),
            variations=(),
            commentary=commentary,
            metadata=_metadata(position.position_id, position_analysis, settings, judgement),
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
            limit = EngineLimit(depth=budget.depth, nodes=budget.nodes, time_ms=budget.time_ms)
        multipv = budget.multipv if budget.multipv is not None else self.default_multipv
        return EngineSettings(
            limit=limit,
            multipv=multipv,
            threads=JUDGEMENT_THREADS,
            hash_mb=JUDGEMENT_HASH_MB,
        )


def _settings_metadata(settings: EngineSettings) -> dict[str, Any]:
    return {
        "depth": settings.limit.depth,
        "nodes": settings.limit.nodes,
        "time_ms": settings.limit.time_ms,
        "multipv": settings.multipv,
        "threads": settings.threads,
        "hash_mb": settings.hash_mb,
    }


def _metadata(
    position_id: str,
    position_analysis: EngineAnalysis,
    settings: EngineSettings,
    judgement: MoveJudgement,
) -> dict[str, Any]:
    """Frozen schema-0.2 keys only; no timing, request id, game token or runtime counters."""

    counterfactual = _settings_metadata(COUNTERFACTUAL_SETTINGS)
    del counterfactual["nodes"]
    return {
        "position_id": position_id,
        "engine": {
            "name": position_analysis.engine.name,
            "version": position_analysis.engine.version,
        },
        "analysis": _settings_metadata(settings),
        "forcedness": {
            "acceptable_move_count": judgement.forcedness.acceptable_move_count,
            "best_to_second_gap_cp": judgement.forcedness.best_to_second_gap_cp,
        },
        "explanation": {"mode": "strict", "counterfactual": counterfactual},
    }


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
