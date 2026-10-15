"""The agent's tests (AG-D §11): the synthetic engine of the fact-engine tests, the server tests'
games and failing engine, and the repository root for `tools/`."""

from __future__ import annotations

import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTS / "facts" / "search"))
sys.path.insert(0, str(TESTS / "server"))
sys.path.insert(0, str(TESTS.parent))
