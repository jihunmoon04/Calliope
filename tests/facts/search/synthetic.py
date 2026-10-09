"""A deterministic synthetic engine for tree-integration tests (F4-D §9.2). Not a chess engine.

Ranks the legal root moves (or the restriction) by UCI text, scores them 100, 90, 80, …, and
gives each a PV of up to `pv_plies` moves, continuing with the first legal reply in UCI order.
Inputs listed in `irregular` answer as a TIME-stopped search; `mate_in_one` gives mate scores.
"""

from __future__ import annotations

import chess

from calliope.facts.search import (
    Bound,
    EngineIdentity,
    EngineOption,
    RawLine,
    RawSearch,
    ScriptedEngine,
    SearchRequest,
    StoppedBy,
)
from calliope.facts.search.inputs import window_end

IDENTITY = EngineIdentity(
    "Stockfish 19",
    "synthetic",
    "5" * 64,
    (
        EngineOption("Threads", "spin", "1"),
        EngineOption("Hash", "spin", "16"),
        EngineOption("MultiPV", "spin", "1"),
        EngineOption("UCI_ShowWDL", "check", "false"),
        EngineOption("EvalFile", "string", "nn-synthetic.nnue"),
    ),
)


def synthetic(pv_plies: int = 4, irregular: frozenset[str] = frozenset()):
    def answer(request: SearchRequest) -> RawSearch:
        board = window_end(request.input)
        legal = sorted(m.uci() for m in board.legal_moves)
        roots = legal if request.root_moves is None else sorted(request.root_moves)
        k = min(request.multipv, len(roots))
        stopped = StoppedBy.TIME if board.fen() in irregular else StoppedBy.DEPTH
        lines = []
        for rank, move in enumerate(roots[:k], start=1):
            walker = board.copy(stack=False)
            pv = [move]
            walker.push_uci(move)
            while len(pv) < pv_plies:
                replies = sorted(m.uci() for m in walker.legal_moves)
                if not replies:
                    break
                pv.append(replies[0])
                walker.push_uci(replies[0])
            depth = request.profile.depth if stopped is StoppedBy.DEPTH else 7
            lines.append(
                RawLine(
                    multipv=rank,
                    depth=depth,
                    seldepth=depth + 2,
                    score=("cp", 110 - 10 * rank),
                    bound=Bound.EXACT,
                    wdl=(100, 800, 100),
                    nodes=1000 * rank,
                    tbhits=0,
                    pv=tuple(pv),
                )
            )
        return RawSearch(tuple(lines), stopped, 1)

    return answer


def engine(pv_plies: int = 4, irregular: frozenset[str] = frozenset()) -> ScriptedEngine:
    return ScriptedEngine(IDENTITY, synthetic(pv_plies, irregular))


def board_fen(fen: str) -> str:
    return chess.Board(fen).fen()
