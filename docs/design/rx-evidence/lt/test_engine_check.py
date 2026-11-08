"""LT implementation §9.4 Q2 (answered as recommended, 2026-11-08): each Test reference's engine facts
against a depth-20 score of every legal move at its moment. A reference is flagged when its played
or best line's score disagrees with that move's depth-20 score in kind (a mate against a centipawn
score, or mates for different sides) or by more than 1.00. Writes `test-engine-check.json`; the
flags are read with the key causes in the owner's review.

    python docs/design/rx-evidence/lt/test_engine_check.py [--out DIR]
"""

from __future__ import annotations

import json

import chess
import chess.engine
from replay_common import REPO, arguments, engine_path

DEPTH = 20
LIMIT_CP = 100
args = arguments(__doc__)
folder = REPO / "tools" / "rx" / "references_v1" / "test"
engine = chess.engine.SimpleEngine.popen_uci(engine_path())


def white(score) -> dict:
    s = score.white()
    return {"mate": s.mate()} if s.is_mate() else {"cp": s.score()}


def disagree(ref: dict | None, deep: dict | None) -> str | None:
    if not ref or not deep:
        return None
    if ("mate" in ref) != ("mate" in deep):
        return "a mate against a score"
    if "mate" in ref:
        return None if (ref["mate"] > 0) == (deep["mate"] > 0) else "mates for different sides"
    return f"{abs(ref['cp'] - deep['cp'])} cp apart" if abs(ref["cp"] - deep["cp"]) > LIMIT_CP else None


out = {"depth": DEPTH, "limit_cp": LIMIT_CP, "engine": engine.id.get("name"), "moments": {}}
for path in sorted(folder.glob("*.json")):
    ref = json.loads(path.read_text(encoding="utf-8"))
    board = chess.Board(ref["fen_before"])
    scores = {}
    for move in board.legal_moves:
        after = board.copy()
        after.push(move)
        if after.is_game_over(claim_draw=False):
            outcome = after.outcome(claim_draw=False)
            scores[board.san(move)] = {"terminal": outcome.termination.name.lower()}
            continue
        info = engine.analyse(after, chess.engine.Limit(depth=DEPTH))
        scores[board.san(move)] = white(info["score"]) | {"depth": info.get("depth")}
    lines = (ref.get("digest") or {}).get("lines") or {}
    flags = []
    for role in ("played", "best"):
        line = lines.get(role)
        if not line:
            continue
        san = str(line.get("move", "")).split(".")[-1]
        deep = scores.get(san)
        reason = disagree(line.get("score"), {k: v for k, v in (deep or {}).items() if k in ("cp", "mate")})
        if reason:
            flags.append({"role": role, "move": line.get("move"), "reference": line.get("score"),
                          "depth_20": deep, "why": reason})  # fmt: skip
    def for_mover(v, white_moves=board.turn):
        """Higher is better for the side to move: its mates first (shorter first), then scores,
        then mates against it (longer first)."""
        sign = 1 if white_moves else -1
        if "mate" in v:
            m = sign * v["mate"]
            return (2, -m) if m > 0 else (0, -m)
        return (1, sign * v["cp"])

    ranked = sorted(((k, v) for k, v in scores.items() if "cp" in v or "mate" in v),
                    key=lambda kv: for_mover(kv[1]), reverse=True)  # fmt: skip
    out["moments"][path.stem] = {"move": ref.get("move"), "flags": flags,
                                 "depth_20_top": [(k, v) for k, v in ranked[:5]]}  # fmt: skip
    print(path.stem, "flags:", flags or "none", flush=True)
engine.quit()
target = args.out / "test-engine-check.json"
target.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("saved", target)
