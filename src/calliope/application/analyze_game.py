"""Analyze-game use case.

Game analysis is not implemented yet; the composition root injects an explicit
unavailable use case so callers get a clear failure instead of an empty result.
"""

from __future__ import annotations

from calliope.contracts import AnalyzeGameRequest, GameAnalysisResult
from calliope.errors import FeatureUnavailableError


class AnalyzeGameUnavailable:
    def execute(self, request: AnalyzeGameRequest) -> GameAnalysisResult:
        raise FeatureUnavailableError("game analysis is not available yet")
