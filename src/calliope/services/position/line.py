"""Bounded replay of a supplied line using the existing P5 and P8 identity machinery."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from calliope.domain.analysis import MaterialChange
from calliope.domain.analysis.positional import LineAnalysis, LineEndKind, LinePieceHistory
from calliope.domain.chess import ChessMove, Color, PieceType, PositionSnapshot
from calliope.services.explanation.piece_identity import BasePieceIdentityMap
from calliope.services.position.positional import TransitionAnalyzer


@dataclass(slots=True)
class LineAnalyzer:
    transitions: TransitionAnalyzer

    def analyze(
        self,
        initial: PositionSnapshot,
        moves: tuple[ChessMove, ...],
        *,
        max_plies: int = 64,
    ) -> LineAnalysis:
        if type(max_plies) is not int or not 1 <= max_plies <= 256:
            raise ValueError("max_plies must be an integer between 1 and 256")
        if len(moves) > max_plies:
            raise ValueError("supplied line exceeds max_plies; no silent truncation")
        first = self.transitions.positions.analyze(initial)
        identity = BasePieceIdentityMap.from_facts(first.facts)
        histories = {base: [identity.current_piece(base)] for base in identity.base_pieces}
        steps = []
        current = first
        totals: dict[tuple[Color, PieceType], int] = defaultdict(int)
        for move in moves:
            step = self.transitions.analyze(current.position, move)
            if step.before != current:
                raise ValueError("line transition does not continue the previous analysis")
            identity = identity.advance(step.board_delta)
            if set(identity.live_pieces) != {s.piece for s in step.after.facts.pieces}:
                raise ValueError("line identity does not reconcile with after-position facts")
            for base in identity.base_pieces:
                histories[base].append(identity.current_piece(base))
            steps.append(step)
            for change in step.board_delta.material_changes:
                totals[change.color, change.piece_type] += change.count_delta
            current = step.after
        material_changes = tuple(
            MaterialChange(color, kind, totals[color, kind])
            for color in (Color.WHITE, Color.BLACK)
            for kind in (
                PieceType.PAWN,
                PieceType.KNIGHT,
                PieceType.BISHOP,
                PieceType.ROOK,
                PieceType.QUEEN,
            )
            if totals[color, kind]
        )
        return LineAnalysis(
            first,
            tuple(steps),
            current,
            material_changes,
            LineEndKind.CHECKMATE
            if current.facts.side_to_move_checkmated
            else LineEndKind.PROVIDED_LINE_END,
            tuple(LinePieceHistory(base, tuple(states)) for base, states in histories.items()),
        )
