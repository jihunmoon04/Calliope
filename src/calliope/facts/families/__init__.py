"""Registered fact families. Adding a family is one module and one entry here (design F0 §5)."""

from calliope.facts.families.base import FactFamily, FamilyContext, HistoryWindow
from calliope.facts.families.draw import DrawFacts, DrawFamily
from calliope.facts.families.material import MaterialCount, MaterialFacts, MaterialFamily
from calliope.facts.families.move import (
    Capture,
    CastlingSide,
    MoveEvent,
    MoveFacts,
    MoveFamily,
    Promotion,
    RookTransfer,
)
from calliope.facts.families.status import LegalCapture, LegalMove, StatusFacts, StatusFamily

REGISTRY: tuple[FactFamily, ...] = (StatusFamily(), MaterialFamily(), DrawFamily(), MoveFamily())

# Always computed: the node header (terminal, after_terminal) and edges depend on them.
MANDATORY: frozenset[str] = frozenset({"status", "draw", "move"})

__all__ = [
    "MANDATORY",
    "REGISTRY",
    "Capture",
    "CastlingSide",
    "DrawFacts",
    "DrawFamily",
    "FactFamily",
    "FamilyContext",
    "HistoryWindow",
    "LegalCapture",
    "LegalMove",
    "MaterialCount",
    "MaterialFacts",
    "MaterialFamily",
    "MoveEvent",
    "MoveFacts",
    "MoveFamily",
    "Promotion",
    "RookTransfer",
    "StatusFacts",
    "StatusFamily",
]
