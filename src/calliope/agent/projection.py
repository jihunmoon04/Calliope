"""Fact records as JSON for the agent (AG-D §3, §3.7).

One recursive rule over the fact engine's record types: dataclasses by their fields, enums by
their values, sentinels by their kind and reason code, `Defined` with its definition. Piece
identities become `{"piece", "type_now", "color", "origin", "square"}` from the frame of the node
the record belongs to: the facts tree is rooted at the game's start, so `origin` is the square the
piece stood on there. A type the projection does not know is refused, never guessed.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any

import chess

from calliope.facts import (
    Absent,
    AtLeast,
    Defined,
    HistoryUnknown,
    NotApplicable,
    NotComputed,
    NotObserved,
    PieceId,
    Unavailable,
)

TYPES = {"K": "king", "Q": "queen", "R": "rook", "B": "bishop", "N": "knight", "P": "pawn"}
COLORS = {"w": "white", "b": "black"}


class ProjectionError(ValueError):
    """A value of a type the projection has no case for."""


def identity(piece: PieceId, frame=None) -> dict:
    """`piece_identity` (AG-D §3.7); `frame` (a `FrameNode`) adds the square and current type."""

    color, kind, origin = piece.value.split(".")
    out: dict[str, Any] = {"piece": TYPES[kind], "color": COLORS[color], "origin": origin}
    if frame is not None:
        square = frame.square_of(piece)
        out["square"] = square
        if square is not None:
            now = chess.Board(frame.fen).piece_at(chess.parse_square(square))
            out["type_now"] = chess.piece_name(now.piece_type) if now is not None else None
        else:
            out["type_now"] = None
    return out


def project(value: Any, frame=None) -> Any:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple | list):
        return [project(x, frame) for x in value]
    if isinstance(value, PieceId):
        return identity(value, frame)
    if isinstance(value, Defined):
        return {"value": project(value.value, frame), "definition": value.definition}
    if isinstance(value, NotApplicable):
        return {"sentinel": "not_applicable", "reason": value.reason}
    if isinstance(value, NotComputed):
        return {"sentinel": "not_computed", "reason": value.reason}
    if isinstance(value, Absent):
        return {"sentinel": "absent", "reason": value.reason.value}
    if isinstance(value, NotObserved):
        return {"sentinel": "not_observed"}
    if isinstance(value, Unavailable):
        return {"sentinel": "unavailable"}
    if isinstance(value, HistoryUnknown):
        return {"sentinel": "history_unknown"}
    if isinstance(value, AtLeast):
        return {"at_least": value.n}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: project(getattr(value, f.name), frame) for f in dataclasses.fields(value)}
    raise ProjectionError(f"no projection for {type(value).__name__}")
