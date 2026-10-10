"""Shared helpers: the synthetic engine of the fact-engine tests and a scripted table engine."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "facts" / "search"))
