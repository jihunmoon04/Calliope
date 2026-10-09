"""`draw` (NODE, RULE): clocks, repetition and the draw rules over known history (§2.2, §6.9).

Over incomplete history a value is `true` only when the known plies prove it, `false` only when
the unknown plies cannot change the answer, and `HISTORY_UNKNOWN` otherwise.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import ClassVar

import chess

from calliope.facts.families.base import FamilyContext, HistoryWindow
from calliope.facts.families.status import StatusFacts
from calliope.facts.keys import PositionKey
from calliope.facts.tree import Scope
from calliope.facts.values import HISTORY_UNKNOWN, AtLeast, FactClass, HistoryUnknown

Tri = bool | HistoryUnknown


@dataclass(frozen=True, slots=True)
class DrawFacts:
    halfmove_clock: int
    fullmove_number: int
    occurrences: int | AtLeast  # of this position within the repetition window, this node included
    threefold_reached: Tri
    threefold_claimable_by_move: Tri  # a legal move reaches a third occurrence
    fivefold_reached: Tri
    fifty_move_reached: bool  # halfmove clock >= 100
    seventy_five_move_reached: bool  # halfmove clock >= 150 and not checkmate


class DrawFamily:
    name: ClassVar[str] = "draw"
    version: ClassVar[str] = "draw_v1"
    scope: ClassVar[Scope] = Scope.NODE
    fact_class: ClassVar[FactClass] = FactClass.RULE
    requires: ClassVar[tuple[str, ...]] = ("status",)
    # record types of this family, for the closed type registry (F5-D §2)
    record_types: ClassVar[tuple[type, ...]] = (DrawFacts,)

    def compute(self, ctx: FamilyContext) -> DrawFacts:
        board = ctx.board
        history = ctx.history
        assert history is not None
        status: StatusFacts = ctx.records["status"]
        here = PositionKey.of(board)
        seen = 1 + history.keys.count(here)
        bound = max_unknown_occurrences(history.unknown_plies)
        return DrawFacts(
            halfmove_clock=board.halfmove_clock,
            fullmove_number=board.fullmove_number,
            occurrences=seen if history.complete else AtLeast(seen),
            threefold_reached=reaches(seen, bound, 3),
            threefold_claimable_by_move=_claimable_by_move(board, here, history, bound),
            fivefold_reached=reaches(seen, bound, 5),
            fifty_move_reached=board.halfmove_clock >= 100,
            seventy_five_move_reached=board.halfmove_clock >= 150 and not status.checkmate,
        )


def max_unknown_occurrences(unknown_plies: int) -> int:
    """Upper bound of earlier occurrences hidden in `unknown_plies` plies of the window.

    Two occurrences of one position are at least 4 plies apart (same side to move, and a
    position cannot recur after 2 plies), so `u` plies hold at most `ceil(u / 4)` of them.
    """

    return (unknown_plies + 3) // 4


def reaches(seen: int, bound: int, threshold: int) -> Tri:
    if seen >= threshold:
        return True
    if seen + bound < threshold:
        return False
    return HISTORY_UNKNOWN


def _claimable_by_move(
    board: chess.Board, here: PositionKey, history: HistoryWindow, bound: int
) -> Tri:
    # After a reversible move the new position's window is this node plus this node's window,
    # so the move reaches a third occurrence iff its position occurs twice in `earlier`.
    earlier = Counter((here, *history.keys))
    proving = {key for key, count in earlier.items() if count >= 2}
    open_keys = {key for key, count in earlier.items() if count + bound >= 2}
    open_everywhere = bound >= 2  # even a never-seen position may hide two occurrences
    if not proving and not open_keys and not open_everywhere:
        return False  # no position after any move can reach three: skip move generation
    probe = board.copy(stack=False)
    reversible = [move for move in probe.legal_moves if not probe.is_zeroing(move)]
    if not reversible:
        return False
    if not proving and open_everywhere:
        return HISTORY_UNKNOWN
    answer: Tri = HISTORY_UNKNOWN if open_everywhere else False
    for move in reversible:
        probe.push(move)
        after = PositionKey.of(probe)
        probe.pop()
        if after in proving:
            return True
        if after in open_keys:
            answer = HISTORY_UNKNOWN
    return answer
