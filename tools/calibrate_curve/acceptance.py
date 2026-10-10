"""The regression record of Q-D §9.11: two games under three gradings, against chess.com's symbols.

`python -m tools.calibrate_curve.acceptance` (needs `CALLIOPE_STOCKFISH_PATH`). The design game is
not evidence of agreement (Q-D B2.4, §9.12); this records how the gradings differ on it.
"""

from __future__ import annotations

import io
import os
import sys
from collections import Counter
from pathlib import Path

import chess.pgn

from calliope.facts import EngineProfile, FactEngine, RootSpec
from calliope.facts.search import StockfishEngine
from calliope.reasoning import SHIPPED, AnalysisRequest, Controller, GradingSpec

ROOT = Path(__file__).resolve().parents[2]
ANNOTATED = ROOT / "tests/reasoning/fixtures/chesscom_rapid_813_801.pgn"
OPERA = [
    "e4",
    "e5",
    "Nf3",
    "d6",
    "d4",
    "Bg4",
    "dxe5",
    "Bxf3",
    "Qxf3",
    "dxe5",
    "Bc4",
    "Nf6",
    "Qb3",
    "Qe7",
    "Nc3",
    "c6",
    "Bg5",
    "b5",
    "Nxb5",
    "cxb5",
    "Bxb5+",
    "Nbd7",
    "O-O-O",
    "Rd8",
    "Rxd7",
    "Rxd7",
    "Rd1",
    "Qe6",
    "Bxd7+",
    "Nxd7",
    "Qb8+",
    "Nxb8",
    "Rd8#",
]
SYMBOL = {6: "?!", 2: "?", 4: "??", 3: "!!", 9: "miss"}
CLASS = {"inaccuracy": "?!", "mistake": "?", "blunder": "??"}


def annotated() -> tuple[list[str], list[str], dict[str, str]]:
    game = chess.pgn.read_game(io.StringIO(ANNOTATED.read_text()))
    board = game.board()
    moves, symbols = [], []
    for node in game.mainline():
        moves.append(board.san(node.move))
        board.push(node.move)
        symbols.append(next((SYMBOL[n] for n in sorted(node.nags) if n in SYMBOL), ""))
    return moves, symbols, dict(game.headers)


def grades(engine, moves: list[str], spec: GradingSpec) -> list[tuple[str, int | None]]:
    out = []
    for t in range(1, len(moves) + 1):
        request = AnalysisRequest(RootSpec(), tuple(moves), t, EngineProfile(), grading=spec)
        judgement = Controller(FactEngine(engine=engine), SHIPPED).round_zero(request).judgements[0]
        out.append((judgement.grade.value if judgement.grade else judgement.reason, judgement.loss))
    return out


def main() -> int:
    engine = StockfishEngine.start(os.environ["CALLIOPE_STOCKFISH_PATH"])
    moves, symbols, headers = annotated()
    rated = {"white_rating": int(headers["WhiteElo"]), "black_rating": int(headers["BlackElo"]),
             "rating_pool": "chesscom", "time_class": "rapid"}  # fmt: skip
    specs = {"quality_v1": GradingSpec("quality_v1"), "scale 1000": GradingSpec(scale=1000)}
    if SHIPPED.curve_table() is not None:
        specs["table (chesscom)"] = GradingSpec(**rated)
    try:
        games = {
            "annotated": (moves, symbols, {n: grades(engine, moves, s) for n, s in specs.items()}),
            "opera": (OPERA, [""] * len(OPERA), {n: grades(engine, OPERA, s) for n, s in
                                                 specs.items() if not n.startswith("table")}),
        }  # fmt: skip
    finally:
        engine.close()
    for name, (game_moves, game_symbols, by_spec) in games.items():
        print(f"\n## {name}\n")
        print("| ply | move | chess.com | " + " | ".join(by_spec) + " |")
        print("| --- | --- | --- |" + " --- |" * len(by_spec))
        for i, move in enumerate(game_moves):
            cells = [f"{g} ({loss})" if loss is not None else g for g, loss in
                     (by_spec[n][i] for n in by_spec)]  # fmt: skip
            if game_symbols[i] or len({c.split(" ")[0] for c in cells}) > 1:
                print(f"| {i + 1} | {move} | {game_symbols[i]} | " + " | ".join(cells) + " |")
        if name == "annotated":
            for spec, rows in by_spec.items():
                mine = [CLASS.get(g, "") for g, _ in rows]
                theirs = [s if s in ("?!", "?", "??") else "" for s in game_symbols]
                agree = sum(a == b for a, b in zip(mine, theirs, strict=True))
                confusion = Counter(zip(theirs, mine, strict=True))
                print(f"\n{spec}: agreement {agree}/{len(mine)}; (chess.com, ours) "
                      + ", ".join(f"{a or '·'}→{b or '·'} {n}" for (a, b), n in
                                  sorted(confusion.items()) if a != b))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
