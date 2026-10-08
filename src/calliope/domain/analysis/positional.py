"""Versioned structural observations, not evaluations or explanation claims."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from calliope.domain.analysis.bad_move import BasePieceRef
from calliope.domain.analysis.delta import BoardDelta, MaterialChange
from calliope.domain.chess import Color, PieceRef, PositionFacts, PositionSnapshot

POSITIONAL_DEFINITION_VERSION = "positional_v1"


@dataclass(frozen=True, slots=True)
class PawnStructure:
    pawn: PieceRef
    isolated: bool
    doubled: bool
    passed: bool
    pawn_supporters: tuple[PieceRef, ...]


@dataclass(frozen=True, slots=True)
class FileStructure:
    file: str
    white_pawns: int
    black_pawns: int

    @property
    def open(self) -> bool:
        return self.white_pawns == self.black_pawns == 0

    def semi_open_for(self, color: Color) -> bool:
        own, enemy = (
            (self.white_pawns, self.black_pawns)
            if color is Color.WHITE
            else (self.black_pawns, self.white_pawns)
        )
        return own == 0 and enemy > 0


@dataclass(frozen=True, slots=True)
class PositionalFeatures:
    position_id: str
    pawns: tuple[PawnStructure, ...]
    files: tuple[FileStructure, ...]
    definition_version: str = POSITIONAL_DEFINITION_VERSION


@dataclass(frozen=True, slots=True)
class PositionAnalysis:
    position: PositionSnapshot
    facts: PositionFacts
    features: PositionalFeatures


@dataclass(frozen=True, slots=True)
class PawnStructureChange:
    """Pair one physical pawn across a move; None covers capture or promotion.

    Existing pawns use P5 correspondence. A moved pawn alone is not a feature change.
    """

    before: PawnStructure | None
    after: PawnStructure | None


@dataclass(frozen=True, slots=True)
class FileStructureChange:
    before: FileStructure
    after: FileStructure


@dataclass(frozen=True, slots=True)
class TransitionAnalysis:
    before: PositionAnalysis
    after: PositionAnalysis
    board_delta: BoardDelta
    pawn_changes: tuple[PawnStructureChange, ...]
    file_changes: tuple[FileStructureChange, ...]


class LineEndKind(StrEnum):
    PROVIDED_LINE_END = "provided_line_end"
    CHECKMATE = "checkmate"


@dataclass(frozen=True, slots=True)
class LinePieceHistory:
    """Initial piece identity and its location/type at every frame; None means captured."""

    base: BasePieceRef
    states: tuple[PieceRef | None, ...]


@dataclass(frozen=True, slots=True)
class LineAnalysis:
    """Observations of a supplied line, never proof of forced play or a settled exchange.

    Material changes are counts by type, including promotion, not a weighted score.
    No repetition/draw adjudication is attempted from history-free snapshots.
    """

    initial: PositionAnalysis
    transitions: tuple[TransitionAnalysis, ...]
    final: PositionAnalysis
    material_changes: tuple[MaterialChange, ...]
    end_kind: LineEndKind
    piece_histories: tuple[LinePieceHistory, ...]
