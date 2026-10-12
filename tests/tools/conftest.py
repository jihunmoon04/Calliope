"""The operator tools live outside `src/`; their tests import them from the repository root."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
# the synthetic engine of the fact-engine tests, for tools/explain_game's test
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "facts" / "search"))
