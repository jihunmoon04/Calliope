"""LT-D §6.2 step 1: Train's 13 tool-shaped cases of §0.2 put to the v8 tools (no model)."""
import json, os, shutil, sys, tempfile
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, "/mnt/d/00_프로젝트/Calliope")
from calliope.agent import Limits, Session  # noqa: E402
from calliope.facts.search import StockfishEngine  # noqa: E402

REPO = Path("/mnt/d/00_프로젝트/Calliope")
BASE = Path(os.path.expanduser("~/.local/share/calliope/rx/base/train/data"))
ENGINE = os.environ["CALLIOPE_STOCKFISH_PATH"]
PGNS = {"rapid": "tests/reasoning/fixtures/chesscom_rapid_813_801.pgn",
        "fresh": "tests/agent/fixtures/weak_engines_1.pgn",
        "fourth": "tests/agent/fixtures/weak_engines_2.pgn"}

work = Path(tempfile.mkdtemp()) / "data"
shutil.copytree(BASE, work)
for p in work.rglob("*"):
    p.chmod(0o644 if p.is_file() else 0o755)
s = Session(work, lambda: StockfishEngine.start(ENGINE), replace(Limits(), max_searches=400))
g = {n: s.open_game(pgn=(REPO / p).read_text(encoding="utf-8"))["game"] for n, p in PGNS.items()}
out = {}


def case(key, fn):
    try:
        out[key] = fn()
    except Exception as error:  # noqa: BLE001
        out[key] = {"error": f"{type(error).__name__}: {error}"}
    print(key, json.dumps(out[key], ensure_ascii=False)[:1500], flush=True)


def sq(game, position, squares):
    return s.squares(g[game], position, squares)["squares"]


def end_squares(game, position, moves, squares):
    a = s.explore(g[game], position, moves)
    return {"moves": [p["san"] for p in a["ledger"]["plies"]],
            "squares": sq(game, {"from_root": a["end"]["from_root"]}, squares)}


# relations (7)
case("fourth-37 d4 defenders", lambda: sq("fourth", {"ply": 37, "at": "after"}, ["d4"]))
case("fourth-38 f5 vs queen d7", lambda: end_squares("fourth", {"ply": 38, "at": "before"},
                                                     ["Qxh6", "Qxd7", "f5"], ["d7", "f5"]))
case("fresh-56 who takes g4", lambda: sq("fresh", {"ply": 56, "at": "before"}, ["g4"]))
case("fresh-62 d5 change", lambda: sq("fresh", {"ply": 62, "at": "after"}, ["d5"]))
case("rapid-40 d6 defenders", lambda: end_squares("rapid", {"ply": 40, "at": "after"},
                                                  ["dxc6", "Nd6", "Bd3", "bxc6"], ["d6"]))
case("rapid-52 f7 (two runs)", lambda: sq("rapid", {"ply": 52, "at": "after"}, ["f7"]))
# a line's outcome (3)
case("fourth-56 ranking after 28...Bxg3", lambda: {
    k: v for k, v in s.compare_lines(g["fourth"], 57, length=8, candidates=["Rxg3"]).items()
    if k in ("ranking", "root")})


def bishop_end():
    a = s.explore(g["fourth"], {"ply": 56, "at": "after"}, [], search=True,
                  continue_with="engine", length=8)
    return {"moves": [p["san"] for p in a["ledger"]["plies"]], "end": a["ledger"]["end"],
            "end_score": a["ledger"].get("end_score")}


case("fourth-56 bishop at the line's end", bishop_end)


def h_pawns():
    a = s.explore(g["fresh"], {"ply": 76, "at": "before"}, ["Rxh5", "gxh5", "Qxh5"])
    return {"moves": [p["san"] for p in a["ledger"]["plies"]], "captured": a["ledger"]["captured"],
            "net": a["ledger"]["net"]}


case("fresh-76 who took the h-pawns", h_pawns)
# lines compared (3)


def rapid52():
    a = s.compare_lines(g["rapid"], 52, length=16)
    return {k: {"moves": v["moves"], "ledger": v["ledger"], "end": v["end"]}
            for k, v in a["lines"].items()}


case("rapid-52 which line holds the 1-point loss", rapid52)
case("rapid-54 does 27...Kxf7 avoid mate", lambda: s.compare_lines(
    g["rapid"], 54, length=8, candidates=["Kxf7"])["ranking"])


def recapture():
    a = s.explore(g["rapid"], {"ply": 54, "at": "before"}, ["Kxf7", "Rxe8", "Nxe8"])
    return {"plies": [{k: p.get(k) for k in ("san", "says", "captured")} for p in a["ledger"]["plies"]],
            "net": a["ledger"]["net"]}


case("rapid-54 after 27...Kxf7 28.Rxe8", recapture)
s.close()
json.dump(out, open("/mnt/d/00_프로젝트/rx-trial/lt-replay-train.json", "w"), ensure_ascii=False, indent=1)
print("saved")
