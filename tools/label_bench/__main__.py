"""`python -m tools.label_bench`: `label_v2`'s BRILLIANT against chess.com Game Review (LV-D §9).

The data is Chessigma's brilliant benchmark: 100 chess.com games, each with the ply Game Review
marked brilliant. It is downloaded into a cache, never into the repository, and its SHA-256 goes
in the report. The full reasoner runs on every brilliant ply and on every ply whose move leaves a
piece statically offered (LV-D §5 step 1 on the `exchange` facts); every other ply cannot carry a
BRILLIANT, so it counts as a correct "no".

The figures are exploratory, not acceptance evidence (LV-D §2.2, re-review C1): the rule's
thresholds were chosen on these games.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import chess
import chess.pgn

from calliope.facts import EngineProfile, FactEngine, RootSpec
from calliope.facts.families import ExchangeFamily, FamilyContext
from calliope.facts.families.material import POINTS_V1
from calliope.facts.storage import build_identity
from calliope.facts.values import Defined
from calliope.reasoning import AnalysisRequest, GradingSpec, Reasoner, chesscom_time_class

URL = "https://www.chessigma.com/benchmarks/brilliant/data"
CACHE = Path.home() / ".cache" / "calliope" / "brilliant_benchmark.json"
RULE = "brilliant_p2"
FAMILY = ExchangeFamily()


def download(path: Path) -> bytes:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["curl", "-sSL", "--fail", URL, "-o", str(path)], check=True)
    return path.read_bytes()


def offered(board: chess.Board, move: chess.Move) -> bool:
    """LV-D §5 step 1, statically: after the move, a non-king, non-pawn piece of the mover is
    exposed by at least one point more than the move captured. It keeps a just-promoted piece, so
    it is a superset of `brilliant_p2`'s step 1 (LV-D §15.3); the reasoner decides."""

    side = board.turn
    victim = board.piece_type_at(move.to_square)
    captured = POINTS_V1[victim] if victim is not None and victim != chess.KING else 0
    after = board.copy(stack=False)
    after.push(move)
    record = FAMILY.compute(FamilyContext(board=after, records={}))
    for p in record.pieces:
        mine = (p.color.value == "white") == (side == chess.WHITE)
        if not mine or p.piece_type.value in ("pawn", "king") or not isinstance(p.gain, Defined):
            continue
        if p.gain.value - captured >= 1:
            return True
    return False


def run(engine, games: list[dict]) -> list[dict]:
    rows = []
    for i, item in enumerate(games):
        game = chess.pgn.read_game(io.StringIO(item["pgn"]))
        h = game.headers
        spec = GradingSpec(white_rating=int(h["WhiteElo"]), black_rating=int(h["BlackElo"]),
                           rating_pool="chesscom",
                           time_class=chesscom_time_class(h.get("TimeControl", "-")) or "rapid")  # fmt: skip
        board = game.board()
        sans: list[str] = []
        brilliant = int(item["ply"])
        for ply, move in enumerate(game.mainline_moves(), start=1):
            san = board.san(move)
            candidate = ply == brilliant or offered(board, move)
            sans.append(san)
            if candidate:
                start = time.perf_counter()
                request = AnalysisRequest(
                    RootSpec(), tuple(sans), ply, EngineProfile(), grading=spec
                )
                analysis = Reasoner(FactEngine(engine=engine)).analyse(request)
                labels = [(lb.kind.value, lb.rule) for lb in analysis.labels]
                verdicts = {c.hypothesis.template: (c.verdict.status.value, c.verdict.reason)
                            for c in analysis.claims
                            if c.hypothesis.template in ("piece_offer_v1", "capture_holds_v1")}  # fmt: skip
                rows.append({"game": i, "ply": ply, "san": san, "brilliant": ply == brilliant,
                             "labels": labels, "verdicts": verdicts,
                             "seconds": round(time.perf_counter() - start, 2)})  # fmt: skip
            board.push(move)
        print(f"game {i + 1}/{len(games)}: {len(sans)} plies", file=sys.stderr, flush=True)
    return rows


def summary(rows: list[dict], plies: list[int]) -> dict:
    def called(r: dict) -> bool:
        return any(kind == "brilliant" for kind, _rule in r["labels"])

    out: dict = {}
    for name, keep in (("all", lambda g: True), ("even", lambda g: g % 2 == 0),
                       ("odd", lambda g: g % 2 == 1)):  # fmt: skip
        sel = [r for r in rows if keep(r["game"])]
        found = sum(r["brilliant"] and called(r) for r in sel)
        false = sum(not r["brilliant"] and called(r) for r in sel)
        n_games = sum(1 for g in range(len(plies)) if keep(g))
        negatives = sum(n - 1 for g, n in enumerate(plies) if keep(g))  # one brilliant per game
        out[name] = {"games": n_games, "found": found, "false_calls": false,
                     "false_per_1000": round(1000 * false / max(negatives, 1), 2)}  # fmt: skip
    missed = Counter()
    for r in rows:
        if r["brilliant"] and not called(r):
            v = r["verdicts"]
            step = v.get("capture_holds_v1") or v.get("piece_offer_v1") or ("not proposed", None)
            missed[
                f"{'capture' if 'capture_holds_v1' in v else 'offer'}: {step[0]} {step[1] or ''}".strip()
            ] += 1
    out["missed_by"] = dict(missed)
    return out


def main(argv: list[str] | None = None) -> int:
    from calliope.facts.families import REGISTRY
    from calliope.facts.search import StockfishEngine

    parser = argparse.ArgumentParser(prog="python -m tools.label_bench")
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--out", type=Path, required=True, help="report path (.json)")
    parser.add_argument("--games", type=int, default=None, help="first N games only")
    args = parser.parse_args(argv)
    data = download(args.cache)
    games = json.loads(data)[: args.games]
    plies = [len(list(chess.pgn.read_game(io.StringIO(g["pgn"])).mainline_moves())) for g in games]
    engine = StockfishEngine.start(os.environ["CALLIOPE_STOCKFISH_PATH"])
    try:
        rows = run(engine, games)
    finally:
        engine.close()
    times = sorted(r["seconds"] for r in rows)
    report = {
        "rule": RULE,
        "data": {"url": URL, "sha256": hashlib.sha256(data).hexdigest(), "games": len(games),
                 "plies": sum(plies)},
        "build": {"facts": [f.name + ":" + f.version for f in build_identity(REGISTRY).families]},
        "summary": summary(rows, plies),
        "analysed_plies": len(rows),
        "seconds_per_analysis": {"median": times[len(times) // 2], "max": times[-1]} if times else None,
        "rows": rows,
    }  # fmt: skip
    args.out.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report["summary"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
