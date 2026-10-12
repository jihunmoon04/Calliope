"""The reasoning tests' helpers (the scripted engine, the stories, the corpus) and the synthetic
engine of the fact-engine tests, for `calliope.results` (AR-D §7)."""

from __future__ import annotations

import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTS / "facts" / "search"))
sys.path.insert(0, str(TESTS / "reasoning"))
