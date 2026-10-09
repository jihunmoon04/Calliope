"""Typed refusals of the fact engine. Every refusal happens before anything is committed."""

from __future__ import annotations


class FactEngineError(Exception):
    """Base class of every fact-engine refusal."""


class InvalidRequestError(FactEngineError):
    """The request is malformed or inconsistent with the session (unknown node, label reuse)."""


class InvalidPositionError(FactEngineError):
    """A root FEN cannot be parsed or does not describe a valid standard-chess position."""


class UnsupportedVariantError(FactEngineError):
    """The position or move needs a variant other than standard chess (e.g. Chess960 castling)."""


class IllegalMoveError(FactEngineError):
    """A supplied move is unparsable, a null move, or illegal at its point of the line."""

    def __init__(self, label: str, ply: int, move: str, reason: str) -> None:
        super().__init__(f"line {label!r}, ply {ply}: move {move!r} {reason}")
        self.label = label
        self.ply = ply
        self.move = move
        self.reason = reason


class BudgetExceededError(FactEngineError):
    """The request's input alone does not fit the remaining session budget."""


class EngineError(FactEngineError):
    """The engine process failed, timed out or produced output that cannot be ingested (F4-D §3.3)."""


class EngineOutputError(EngineError):
    """Engine output violates an ingestion rule: an illegal PV, a rank gap, a missing field (§5.2)."""


class EngineUnsupportedError(EngineError):
    """The engine is not an admitted identity (F4-D §3.2: exactly "Stockfish 19")."""


class CrossSearchError(FactEngineError):
    """Scores of different engine searches were ordered against each other (F4-D §7.4)."""
