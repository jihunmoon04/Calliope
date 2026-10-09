"""Registered fact families. Adding a family is one module and one entry here (design F0 §5)."""

from calliope.facts.families.base import FactFamily, FamilyContext, HistoryWindow
from calliope.facts.families.delta import DeltaFacts, DeltaFamily
from calliope.facts.families.draw import DrawFacts, DrawFamily
from calliope.facts.families.king import KingFacts, KingFamily
from calliope.facts.families.lines import LinesFacts, LinesFamily
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
from calliope.facts.families.pattern_delta import PatternDeltaFacts, PatternDeltaFamily
from calliope.facts.families.patterns import PatternsFacts, PatternsFamily
from calliope.facts.families.pawns import PawnsFacts, PawnsFamily
from calliope.facts.families.pieces import PiecesFacts, PiecesFamily
from calliope.facts.families.same_side_delta import SameSideDelta, SameSideDeltaFamily
from calliope.facts.families.squares import SquaresFacts, SquaresFamily
from calliope.facts.families.status import LegalCapture, LegalMove, StatusFacts, StatusFamily

# Registry order is dependency order: every family follows the families it requires.
REGISTRY: tuple[FactFamily, ...] = (
    StatusFamily(),
    MaterialFamily(),
    DrawFamily(),
    MoveFamily(),
    PiecesFamily(),
    SquaresFamily(),
    LinesFamily(),
    PawnsFamily(),
    KingFamily(),
    DeltaFamily(),
    SameSideDeltaFamily(),
    PatternsFamily(),
    PatternDeltaFamily(),
)

# Always computed: the node header (terminal, after_terminal) and edges depend on them.
MANDATORY: frozenset[str] = frozenset({"status", "draw", "move"})

__all__ = [
    "MANDATORY",
    "REGISTRY",
    "Capture",
    "CastlingSide",
    "DeltaFacts",
    "DeltaFamily",
    "DrawFacts",
    "DrawFamily",
    "FactFamily",
    "FamilyContext",
    "HistoryWindow",
    "KingFacts",
    "KingFamily",
    "LegalCapture",
    "LegalMove",
    "LinesFacts",
    "LinesFamily",
    "MaterialCount",
    "MaterialFacts",
    "MaterialFamily",
    "MoveEvent",
    "MoveFacts",
    "MoveFamily",
    "PatternDeltaFacts",
    "PatternDeltaFamily",
    "PatternsFacts",
    "PatternsFamily",
    "PawnsFacts",
    "PawnsFamily",
    "PiecesFacts",
    "PiecesFamily",
    "Promotion",
    "RookTransfer",
    "SameSideDelta",
    "SameSideDeltaFamily",
    "SquaresFacts",
    "SquaresFamily",
    "StatusFacts",
    "StatusFamily",
]
