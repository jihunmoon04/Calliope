"""Calliope-owned errors exposed at application and adapter boundaries."""


class CalliopeError(Exception):
    """Base class for errors raised by Calliope."""


class ChessInputError(CalliopeError):
    """Base class for invalid chess input or operations."""


class InvalidFenError(ChessInputError):
    """The supplied FEN cannot be parsed."""


class InvalidPositionError(ChessInputError):
    """The parsed board does not represent a valid chess position."""


class InvalidUciError(ChessInputError):
    """The supplied UCI string cannot be parsed."""


class NullMoveNotAllowedError(ChessInputError):
    """A null move was supplied as a user move."""


class IllegalMoveError(ChessInputError):
    """The parsed move is not legal in the supplied position."""
