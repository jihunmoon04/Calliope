"""Review F2 (agent-lt-implementation.md §9.3): every legal Black move at `rapid` ply 54, each scored
by Stockfish at depths 12, 20 and 26 — its UCI and SAN, the score, the depth reached, the PV and the
engine's name. Writes `rapid54-all-moves.json`."""

from __future__ import annotations

import json

import chess
import chess.engine
from replay_common import REPO, arguments, engine_path

args = arguments(__doc__)
reference = json.loads(
    (REPO / "tools/rx/references_v1/train/rapid-54.json").read_text(encoding="utf-8")
)
board = chess.Board(reference["fen_before"])
engine = chess.engine.SimpleEngine.popen_uci(engine_path())
out = {"fen_before": reference["fen_before"], "engine": engine.id.get("name"),
       "reference_best": reference["digest"]["lines"]["best"], "moves": []}  # fmt: skip
for move in sorted(board.legal_moves, key=lambda m: m.uci()):
    after = board.copy()
    after.push(move)
    row = {"uci": move.uci(), "san": board.san(move), "searches": []}
    for depth in (12, 20, 26):
        info = engine.analyse(after, chess.engine.Limit(depth=depth))
        score = info["score"].white()
        row["searches"].append({
            "depth_asked": depth, "depth": info.get("depth"),
            "score_white": {"mate": score.mate()} if score.is_mate() else {"cp": score.score()},
            "pv": after.variation_san(info.get("pv", [])[:10]),
        })  # fmt: skip
    out["moves"].append(row)
    print(row["san"], [(x["depth"], x["score_white"]) for x in row["searches"]], flush=True)
engine.quit()
path = args.out / "rapid54-all-moves.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("saved", path)
