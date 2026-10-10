"""Typed refusals of the reasoning blocks (design `docs/design/reasoning-r0-design.md` §15)."""

from __future__ import annotations


class ReasoningError(Exception):
    """Base class of every reasoning refusal; also a template or controller bug."""


class InvalidAnalysisRequest(ReasoningError):
    """The analysis request is malformed, or the fact engine refused its root or moves."""

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class AnalysisFailed(ReasoningError):
    """Round 0 could not build the base tree (engine failure, budget)."""

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class GuardError(ReasoningError):
    """The renderer was asked to state something no supported claim backs (§13.4)."""


class StoredGraphError(ReasoningError):
    """A stored claim graph failed loading, replay or verification (§14.3)."""
