"""Calliope: evidence-first chess commentary.

The names exported here are the public facade of the legacy MVP implementation (frozen, tag
``legacy-mvp-g0``). They are resolved lazily, on first attribute access, so that importing a
redesign package such as ``calliope.facts`` does not load the legacy implementation.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

_LEGACY_EXPORTS = {
    "AnalysisBudget": "calliope.contracts",
    "AnalysisOptions": "calliope.contracts",
    "AnalyzeGameRequest": "calliope.contracts",
    "AnalyzeMoveRequest": "calliope.contracts",
    "CalliopeEngine": "calliope.engine",
    "GameAnalysisResult": "calliope.contracts",
    "MoveAnalysisResult": "calliope.contracts",
    "ObservationSectionView": "calliope.contracts",
    "ObservationSentenceView": "calliope.contracts",
    "ObservationSourceView": "calliope.contracts",
    "ObservedMoveAnalysisResult": "calliope.contracts",
    "ObservedMoveRequest": "calliope.contracts",
    "OutputMode": "calliope.contracts",
    "SuppliedExchangeObservationRequest": "calliope.contracts",
    "create_calliope_engine": "calliope.composition",
}

__all__ = [
    "AnalysisBudget",
    "AnalysisOptions",
    "AnalyzeGameRequest",
    "AnalyzeMoveRequest",
    "CalliopeEngine",
    "GameAnalysisResult",
    "MoveAnalysisResult",
    "ObservationSectionView",
    "ObservationSentenceView",
    "ObservationSourceView",
    "ObservedMoveAnalysisResult",
    "ObservedMoveRequest",
    "OutputMode",
    "SuppliedExchangeObservationRequest",
    "create_calliope_engine",
]


def __getattr__(name: str) -> Any:
    module = _LEGACY_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


if TYPE_CHECKING:
    from calliope.composition import create_calliope_engine
    from calliope.contracts import (
        AnalysisBudget,
        AnalysisOptions,
        AnalyzeGameRequest,
        AnalyzeMoveRequest,
        GameAnalysisResult,
        MoveAnalysisResult,
        ObservationSectionView,
        ObservationSentenceView,
        ObservationSourceView,
        ObservedMoveAnalysisResult,
        ObservedMoveRequest,
        OutputMode,
        SuppliedExchangeObservationRequest,
    )
    from calliope.engine import CalliopeEngine
