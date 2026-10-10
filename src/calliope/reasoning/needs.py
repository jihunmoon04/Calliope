"""Evidence needs: what a verdict still requires from the fact engine (R0-D §6.2)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from calliope.facts import ExpansionSpec, NodeId


@dataclass(frozen=True, slots=True)
class FamilyNeed:
    """Records of `family` at `node` (→ one `ensure` per round)."""

    node: NodeId
    family: str


@dataclass(frozen=True, slots=True)
class LineNeed:
    """Moves played from `start` under `expansion` (→ `extend(ANALYSIS("reasoning"))`)."""

    start: NodeId
    moves: tuple[str, ...]  # canonical UCI
    expansion: ExpansionSpec


EvidenceNeed = FamilyNeed | LineNeed

ANALYSIS_BY = "reasoning"


def need_key(need: EvidenceNeed) -> tuple:
    """Canonical order of needs: kind, node, moves, family (R0-D §6.3 step 4)."""

    if isinstance(need, FamilyNeed):
        return (0, need.node.value, (), need.family, ())
    flags = (need.expansion.survey, need.expansion.comparison, need.expansion.attach_lines)
    return (1, need.start.value, need.moves, "", flags)


def line_label(need: LineNeed) -> str:
    """`"r" + sha256(canonical encoding of the need)[:16]` (R0-D §6.2)."""

    from calliope.reasoning.encoding import canonical_bytes

    return "r" + hashlib.sha256(canonical_bytes(need)).hexdigest()[:16]
