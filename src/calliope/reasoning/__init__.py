"""Reasoning: judgements, hypotheses, claims and explanations over the fact tree.

Design: `docs/design/reasoning-r0-design.md` (contracts) and `reasoning-r2-design.md`
(templates). This package imports the fact engine only through `calliope.facts`; it never
imports python-chess or the legacy MVP modules (`tests/test_package_boundaries.py`).
"""

from calliope.reasoning.controller import Controller, RoundZero
from calliope.reasoning.errors import (
    AnalysisFailed,
    GuardError,
    InvalidAnalysisRequest,
    ReasoningError,
    StoredGraphError,
)
from calliope.reasoning.observer import (
    Grade,
    Judgement,
    JudgementRef,
    JudgementStatus,
    LineScore,
    MissingLine,
    Observation,
    ObservationRef,
    expected,
    grade,
    judge,
)
from calliope.reasoning.refs import (
    FactRef,
    LineSegment,
    MaterialAmount,
    MoveRef,
    MoveSubject,
    PieceRef,
    ScopeRef,
    SearchMoveRef,
    SearchRef,
    SquareRef,
)
from calliope.reasoning.request import AnalysisRequest, ReasoningBudget

__all__ = [
    "AnalysisFailed",
    "AnalysisRequest",
    "Controller",
    "FactRef",
    "Grade",
    "GuardError",
    "InvalidAnalysisRequest",
    "Judgement",
    "JudgementRef",
    "JudgementStatus",
    "LineScore",
    "LineSegment",
    "MaterialAmount",
    "MissingLine",
    "MoveRef",
    "MoveSubject",
    "Observation",
    "ObservationRef",
    "PieceRef",
    "ReasoningBudget",
    "ReasoningError",
    "RoundZero",
    "ScopeRef",
    "SearchMoveRef",
    "SearchRef",
    "SquareRef",
    "StoredGraphError",
    "expected",
    "grade",
    "judge",
]
