"""LT-D §6.2 step 1, the check: Validation's 9 wrong sentences of H (HS §10) put to the v8 tools."""
import io, json, os, shutil, sys, tempfile
from dataclasses import replace
from pathlib import Path

import chess.pgn

sys.path.insert(0, "/mnt/d/00_프로젝트/Calliope")
from calliope.agent import Limits, Session  # noqa: E402
from calliope.facts.search import StockfishEngine  # noqa: E402

RX = Path(os.path.expanduser("~/.local/share/calliope/rx"))
work = Path(tempfile.mkdtemp()) / "data"
shutil.copytree(RX / "base/validation/data", work)
for p in work.rglob("*"):
    p.chmod(0o644 if p.is_file() else 0o755)
s = Session(work, lambda: StockfishEngine.start(os.environ["CALLIOPE_STOCKFISH_PATH"]),
            replace(Limits(), max_searches=400))
A, B = "185371835722", "185922072242"
pgn = {n: (RX / "sets" / f"{n}.pgn").read_text() for n in (A, B)}
g = {n: s.open_game(pgn=t)["game"] for n, t in pgn.items()}
for n, plies in ((A, range(28, 36)), (B, range(136, 143))):
    game = chess.pgn.read_game(io.StringIO(pgn[n])); b = game.board(); row = []
    for i, m in enumerate(game.mainline_moves(), start=1):
        if i in plies:
            row.append(f"{i}:{b.fullmove_number}{'.' if b.turn else '...'}{b.san(m)}")
        b.push(m)
    print(n, " ".join(row))
out = {}


def case(key, fn):
    try:
        out[key] = fn()
    except Exception as error:  # noqa: BLE001
        out[key] = {"error": f"{type(error).__name__}: {error}"}
    print(key, json.dumps(out[key], ensure_ascii=False)[:1400], flush=True)


def lines(n, ply, **kw):
    a = s.compare_lines(g[n], ply, length=10, **kw)
    res = {k: {"moves": v["moves"], "ledger": v["ledger"], "end": v["end"]}
           for k, v in a["lines"].items() if k != "candidates"}
    if "ranking" in a:
        res["ranking"] = [{k: m.get(k) for k in ("move", "for_mover", "rank", "vs_played")}
                          for m in a["ranking"]["moves"]]
    return res


def says(n, position, moves):
    a = s.explore(g[n], position, moves)
    return [p["says"] for p in a["ledger"]["plies"]]


case("A-30 lines of 15...Nxf2", lambda: lines(A, 30))
case("A-30 after 16.Kxf2 f6: the engine's next", lambda: {
    "ledger": (lambda a: [p["san"] for p in a["ledger"]["plies"]])(
        s.explore(g[A], {"ply": 30, "at": "after"}, ["Kxf2", "f6"], search=True,
                  continue_with="engine", length=2))})
case("A-32 what 16...Bxe3 does", lambda: says(A, {"ply": 32, "at": "before"}, ["Bxe3"]))
case("A-33 Qxe3 or Qe1 for White", lambda: lines(A, 33, candidates=["Qxe3", "Qe1"]))
case("B-138 what 69...Rf1 does", lambda: says(B, {"ply": 138, "at": "before"}, ["Rf1"]))
case("B-138 f6 after the move", lambda: s.squares(g[B], {"ply": 138, "at": "after"}, ["f6"])["squares"])
case("B-139 lines", lambda: lines(B, 139))
case("B-140 lines", lambda: lines(B, 140))
s.close()
json.dump(out, open("/mnt/d/00_프로젝트/rx-trial/lt-replay-validation.json", "w"), ensure_ascii=False, indent=1)
print("saved")
