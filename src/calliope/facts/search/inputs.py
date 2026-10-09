"""`EngineInput`: exactly what the engine receives for a node (F4-D §4)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import chess

from calliope.facts.keys import NodeId


@dataclass(frozen=True, slots=True)
class EngineInput:
    """Window-start FEN (legal en passant square, fullmove 1) and the window moves (UCI)."""

    fen: str
    moves: tuple[str, ...]


def window_input(
    start_board: chess.Board, history: Sequence[str], halfmove_clock: int
) -> EngineInput:
    """The input for the position after `history` (canonical UCI) played from `start_board`.

    The window is the last `min(halfmove_clock, len(history))` moves (A0 §7.4). `start_board`
    is copied, never mutated (F1R-N3).
    """

    w = min(halfmove_clock, len(history))
    board = start_board.copy(stack=False)
    for uci in history[: len(history) - w]:
        board.push(chess.Move.from_uci(uci))
    fields = board.fen(en_passant="legal").split(" ")
    fields[5] = "1"  # fullmove: time management only (F4-D §4)
    return EngineInput(" ".join(fields), tuple(history[len(history) - w :]))


def node_input(tree, node_id: NodeId) -> EngineInput:
    """The input of a committed node; read-only access to the tree and its session."""

    session = tree._session
    view = tree.view()
    path = view.path(node_id)
    history = list(session.pre_root_moves)
    history.extend(view.node(n).incoming_move for n in path[1:])
    node = view.node(node_id)
    assert node.known_plies == len(history)
    return window_input(session.start_board, history, node.halfmove_clock)


def window_end(engine_input: EngineInput) -> chess.Board:
    """The searched position: the window start with the window moves played."""

    board = chess.Board(engine_input.fen)
    for uci in engine_input.moves:
        board.push(chess.Move.from_uci(uci))
    return board
