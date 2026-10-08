"""Fact engine: normalized chess facts over a frame tree (design `docs/design/fact-engine-a0-design.md`).

This package is the redesign; it never imports the legacy MVP modules (`tests/test_package_boundaries.py`).
"""

from calliope.facts.engine import FactEngine
from calliope.facts.errors import (
    BudgetExceededError,
    FactEngineError,
    IllegalMoveError,
    InvalidPositionError,
    InvalidRequestError,
    UnsupportedVariantError,
)
from calliope.facts.keys import Color, NodeId, PieceId, PieceType, PositionKey, RootId
from calliope.facts.request import (
    EXPLORED,
    PLAYED,
    ExtendRequest,
    InputLine,
    LineRole,
    OpenRequest,
    RoleKind,
    RootSpec,
    SessionBudget,
    analysis,
)
from calliope.facts.tree import FactTree, FrameNode, Terminal, TerminalKind, TreeView

__all__ = [
    "EXPLORED",
    "PLAYED",
    "BudgetExceededError",
    "Color",
    "ExtendRequest",
    "FactEngine",
    "FactEngineError",
    "FactTree",
    "FrameNode",
    "IllegalMoveError",
    "InputLine",
    "InvalidPositionError",
    "InvalidRequestError",
    "LineRole",
    "NodeId",
    "OpenRequest",
    "PieceId",
    "PieceType",
    "PositionKey",
    "RoleKind",
    "RootId",
    "RootSpec",
    "SessionBudget",
    "Terminal",
    "TerminalKind",
    "TreeView",
    "UnsupportedVariantError",
    "analysis",
]
