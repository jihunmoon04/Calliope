"""The server's tests (AS-D §10): the synthetic engine of the fact-engine tests, and the
repository root for `tools/`."""

from __future__ import annotations

import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTS / "facts" / "search"))
sys.path.insert(0, str(TESTS.parent))
