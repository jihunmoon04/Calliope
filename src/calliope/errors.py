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


class EngineError(CalliopeError):
    """Base class for chess-engine boundary failures."""


class EngineStartupError(EngineError):
    """The engine process could not be started, initialized, or verified as Stockfish."""


class EngineConfigurationError(EngineError):
    """The requested engine settings or analysis request cannot be applied."""


class EngineAnalysisError(EngineError):
    """The engine failed to complete an analysis."""


class InvalidEngineOutputError(EngineError):
    """The engine returned output that cannot be normalized into a canonical analysis."""


class EngineClosedError(EngineError):
    """An analysis was requested from an adapter that has been closed."""


class MoveJudgementError(CalliopeError):
    """Base class for move-judgement failures."""


class IncompatibleAnalysisError(MoveJudgementError):
    """The supplied analyses cannot be soundly compared to judge a move."""


class ApplicationError(CalliopeError):
    """Base class for application/facade-level failures."""


class InvalidAnalysisBudgetError(ApplicationError):
    """The supplied analysis budget contains a non-positive value."""


class UnsupportedOutputModeError(ApplicationError):
    """The requested output mode is not supported by this build."""


class FeatureUnavailableError(ApplicationError):
    """The requested feature is not available yet."""


class CalliopeClosedError(ApplicationError):
    """The engine facade has been closed."""


class PositionFactError(CalliopeError):
    """Base class for position-fact extraction failures."""


class IncompatiblePositionObservationError(PositionFactError):
    """The observation does not belong to the position being extracted."""


class BoardDeltaError(CalliopeError):
    """Base class for board-delta failures."""


class IncompatibleBoardDeltaError(BoardDeltaError):
    """Before/after facts cannot be fully reconciled with the played move."""


class TacticalDetectionError(CalliopeError):
    """Base class for tactical-detection failures."""


class IncompatibleTacticalContextError(TacticalDetectionError):
    """Supplied facts, delta and rule observations cannot be reconciled."""


class CounterfactualError(CalliopeError):
    """Base class for counterfactual-experiment failures."""


class InvalidProbeRequestError(CounterfactualError):
    """The probe or batch request is malformed, over budget, or cannot be forced."""


class IncompatibleProbeResultError(CounterfactualError):
    """Observations or engine output do not match the requested experiment."""


class BadMoveExplanationError(CalliopeError):
    """Base class for P8 bad-move explanation failures."""


class IncompatibleBadMoveContextError(BadMoveExplanationError):
    """P8 inputs or evidence cannot be reconciled into one causal analysis."""
