"""`python -m tools.explain_game GAME.pgn`: every ply of a game, analysed and explained (R4-D §5).

For each ply it builds an `AnalysisRequest` (the game's moves, that ply as the target, the default
profile), runs the reasoner and `explain`. The grading spec comes from the headers: the players'
ratings, the time control, and the pool (chess.com when the `Site` header says so, else Lichess).
`--bundles DIR` writes each ply's `fact_tree_v1` / `claim_graph_v1` pair and re-loads it;
`--json OUT` writes per ply the grade, labels, supported claims, text and bundle digests.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
from pathlib import Path

import chess.pgn

from calliope.facts import EngineProfile, FactEngine, RootSpec
from calliope.reasoning import AnalysisRequest, GradingSpec, Reasoner, explain
from calliope.reasoning.storage import load, save
from tools.calibrate_curve.acceptance import chesscom_time_class
from tools.calibrate_curve.pgn import time_class


def _elo(value: str | None) -> int | None:
    return int(value) if value and re.fullmatch(r"\d+", value) else None


def grading_for(headers) -> GradingSpec:
    """Ratings and time class from the headers; the default curve when either is missing."""

    white, black = _elo(headers.get("WhiteElo")), _elo(headers.get("BlackElo"))
    control = headers.get("TimeControl", "-")
    chesscom = "chess.com" in headers.get("Site", "").lower()
    kind = (
        chesscom_time_class(control)
        if chesscom
        else (time_class(control) if "+" in control else None)
    )
    if white is None or black is None or kind is None:
        return GradingSpec()
    return GradingSpec(white_rating=white, black_rating=black,
                       rating_pool="chesscom" if chesscom else "lichess", time_class=kind)  # fmt: skip


def _plies(text: str | None, count: int) -> range:
    if not text:
        return range(1, count + 1)
    first, _, last = text.partition("-")
    return range(int(first), min(int(last or first), count) + 1)


def explain_game(engine, pgn_text: str, *, plies: str | None = None,
                 bundles: Path | None = None, digests: bool = False) -> list[dict]:  # fmt: skip
    """One record per ply: its move, grade, labels, supported claims and text; the bundle's
    digests when `digests` or `bundles` is set (R4 review B1: `--json` alone needs them too)."""

    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("no game in the PGN")
    board, sans = game.board(), []
    for move in game.mainline_moves():
        sans.append(board.san(move))
        board.push(move)
    spec = grading_for(game.headers)
    root = RootSpec(fen=game.headers["FEN"]) if "FEN" in game.headers else RootSpec()
    records = []
    for ply in _plies(plies, len(sans)):
        request = AnalysisRequest(root, tuple(sans), ply, EngineProfile(), grading=spec)
        analysis = Reasoner(FactEngine(engine=engine)).analyse(request)
        rendered = explain(analysis)
        judgement = analysis.round_zero.judgements[0]
        label = analysis.labels[0] if analysis.labels else None
        record = {
            "ply": ply,
            "move": sans[ply - 1],
            "grade": judgement.grade.value if judgement.grade is not None else None,
            "labels": [[lb.kind.value, lb.rule, lb.provisional] for lb in analysis.labels],
            "supported": sorted({c.hypothesis.template for c in analysis.claims if c.supported}),
            "text": rendered.text,
            "provisional": label.rule if label is not None and label.provisional else None,
        }
        if digests or bundles is not None:
            tree_bytes, graph_bytes = save(analysis, rendered)
            record["bundle"] = {"tree": hashlib.sha256(tree_bytes).hexdigest(),
                                "graph": hashlib.sha256(graph_bytes).hexdigest()}  # fmt: skip
        if bundles is not None:
            bundles.mkdir(parents=True, exist_ok=True)
            (bundles / f"{ply}.tree").write_bytes(tree_bytes)
            (bundles / f"{ply}.graph").write_bytes(graph_bytes)
            loaded, again = load(FactEngine(), tree_bytes, graph_bytes)  # re-loaded and checked
            if save(loaded, again) != (tree_bytes, graph_bytes):
                raise RuntimeError(f"ply {ply}: the bundle did not round-trip")
        records.append(record)
    return records


def line(record: dict) -> str:
    """One output line; a provisional label's rule is marked here, not in the text (R3-D H9)."""

    mark = f"[{record['provisional']}, provisional] " if record["provisional"] else ""
    return f"{mark}{record['text']}"


def main(argv: list[str] | None = None) -> int:
    from calliope.facts.search import StockfishEngine

    parser = argparse.ArgumentParser(prog="python -m tools.explain_game")
    parser.add_argument("pgn", type=Path)
    parser.add_argument("--plies", help="a ply or a range, e.g. 17 or 1-40")
    parser.add_argument("--bundles", type=Path, help="write and re-load each ply's bundle here")
    parser.add_argument("--json", type=Path, help="write the per-ply records here")
    args = parser.parse_args(argv)
    engine = StockfishEngine.start(os.environ["CALLIOPE_STOCKFISH_PATH"])
    try:
        records = explain_game(engine, args.pgn.read_text(), plies=args.plies,
                               bundles=args.bundles, digests=args.json is not None)  # fmt: skip
    finally:
        engine.close()
    for record in records:
        print(line(record))
    if args.json:
        args.json.write_text(json.dumps(records, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
