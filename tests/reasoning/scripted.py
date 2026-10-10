"""A table-driven engine for reasoning tests: exact scores and WDL per position.

`table` maps a position's `board.fen()` (the engine input's window end) to candidate lines
`(move, score, wdl)` in rank order, with `score` as `("cp", n)` or `("mate", n)` and `wdl` as
`(win, draw, loss)` permille — both from the side to move, as UCI reports them — or `wdl=None`.
A fourth element, when present, is the line's whole PV (UCI, starting with the move); otherwise the
PV continues with the first legal reply. Unlisted positions answer like the synthetic engine.
"""

from __future__ import annotations

import time

import chess
from synthetic import IDENTITY, synthetic

from calliope.facts.search import (
    Bound,
    EngineIdentity,
    RawLine,
    RawSearch,
    ScriptedEngine,
    SearchRequest,
    StoppedBy,
)
from calliope.facts.search.inputs import window_end

Line = tuple  # (move, score, wdl) or (move, score, wdl, pv)


def scripted(
    table: dict[str, list[Line]],
    pv_plies: int = 4,
    delay: dict | None = None,
    identity: EngineIdentity = IDENTITY,
) -> ScriptedEngine:
    fallback = synthetic(pv_plies)
    table = {_position(fen): lines for fen, lines in table.items()}

    def answer(request: SearchRequest) -> RawSearch:
        if delay and delay.get("seconds"):
            time.sleep(delay["seconds"])
        board = window_end(request.input)
        lines = table.get(_position(board.fen()))
        if lines is None:
            return fallback(request)
        lines = _complete(board, lines)  # every legal move ranked, as a full MultiPV search
        if request.root_moves is not None:
            lines = [line for line in lines if line[0] in request.root_moves]
        out = []
        for rank, (move, score, wdl, *given) in enumerate(lines[: request.multipv], start=1):
            walker = board.copy(stack=False)
            pv = [move]
            walker.push_uci(move)
            if given:
                pv = list(given[0])
                assert pv[0] == move
            while not given and len(pv) < pv_plies:
                replies = sorted(m.uci() for m in walker.legal_moves)
                if not replies:
                    break
                pv.append(replies[0])
                walker.push_uci(replies[0])
            out.append(
                RawLine(
                    rank,
                    request.profile.depth,
                    request.profile.depth + 2,
                    score,
                    Bound.EXACT,
                    wdl,
                    1000 * rank,
                    0,
                    tuple(pv),
                )
            )
        return RawSearch(tuple(out), StoppedBy.DEPTH, 1)

    return ScriptedEngine(identity, answer)


def _position(fen: str) -> str:
    """A FEN without its clocks: the engine input may restart the move counters."""

    return " ".join(fen.split()[:4])


def _complete(board: chess.Board, lines: list[Line]) -> list[Line]:
    """The listed lines, then the other legal moves below them (lower cp, the last WDL)."""

    listed = {line[0] for line in lines}
    _, (kind, value), wdl, *_pv = lines[-1]
    low = value if kind == "cp" else -1000
    rest = [m for m in sorted(m.uci() for m in board.legal_moves) if m not in listed]
    return [*lines, *((m, ("cp", low - 10 * (i + 1)), wdl) for i, m in enumerate(rest))]


def fen_after(*moves: str, fen: str | None = None) -> str:
    board = chess.Board(fen) if fen else chess.Board()
    for move in moves:
        board.push_san(move)
    return board.fen()


def all_moves(fen: str) -> list[str]:
    return sorted(m.uci() for m in chess.Board(fen).legal_moves)
