"""A normalized `GameInput` from a FEN and SAN moves, as a caller builds it (AR-D §5, G8)."""

from __future__ import annotations

import chess

from calliope.results import EngineRun, GameInput, GameMove, PlyInput


def game_input(fen: str, sans: list[str] | str, headers: dict | None = None) -> GameInput:
    board = chess.Board(fen)
    start = board.fen()
    moves = []
    for san in sans.split() if isinstance(sans, str) else sans:
        before = board.fen()
        move = board.parse_san(san)
        moves.append(GameMove(board.san(move), move.uci(), before, ""))
        board.push(move)
        moves[-1] = GameMove(moves[-1].san, moves[-1].uci, before, board.fen())
    return GameInput(start, tuple(moves), headers or {})


def engine_run(analysis) -> EngineRun:
    """The run's identity (from any search of the analysis) and its request's profile."""

    view = analysis.tree.view(analysis.rev)
    search = next(view.search(b.search_id) for n in view.nodes() for b in view.searches(n.node_id))
    return EngineRun(search.identity, analysis.round_zero.request.profile)


def ply_input(analysis, rendered=None, bundle=None) -> PlyInput:
    from calliope.reasoning import explain

    return PlyInput(analysis.round_zero.request.target, analysis,
                    rendered if rendered is not None else explain(analysis), bundle)  # fmt: skip
