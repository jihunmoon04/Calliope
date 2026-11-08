"""LT-D §6.2 step 1, the check: Validation's 9 wrong sentences of H (HS §10) put to the v8 tools.
Writes `lt-replay-validation.json` (agent-lt-implementation.md §9.2)."""

from __future__ import annotations

from replay_common import Cases, arguments, session_on

args = arguments(__doc__)
s = session_on(args.rx_data / "base" / "validation" / "data")
A, B = "185371835722", "185922072242"
pgn = {n: (args.rx_data / "sets" / f"{n}.pgn").read_text(encoding="utf-8") for n in (A, B)}
g = {n: s.open_game(pgn=t)["game"] for n, t in pgn.items()}
case = Cases()


def lines(n, ply, **kw):
    a = s.compare_lines(g[n], ply, length=10, **kw)
    res = {k: {"moves": v["moves"], "ledger": v["ledger"], "end": v["end"]}
           for k, v in a["lines"].items() if k != "candidates"}  # fmt: skip
    if "ranking" in a:
        res["ranking"] = [{k: m.get(k) for k in ("move", "for_mover", "depth", "rank", "vs_played",
                                                 "close")} for m in a["ranking"]["moves"]]  # fmt: skip
    return res


def says(n, position, moves):
    return [p["says"] for p in s.explore(g[n], position, moves)["ledger"]["plies"]]


case("A-30 lines of 15...Nxf2", lambda: lines(A, 30))
case("A-30 after 16.Kxf2 f6: the engine's next", lambda: [
    p["san"] for p in s.explore(g[A], {"ply": 30, "at": "after"}, ["Kxf2", "f6"], search=True,
                                continue_with="engine", length=2)["ledger"]["plies"]])  # fmt: skip
case("A-32 what 16...Bxe3 does", lambda: says(A, {"ply": 32, "at": "before"}, ["Bxe3"]))
case("A-33 Qxe3 or Qe1 for White", lambda: lines(A, 33, candidates=["Qxe3", "Qe1"]))
case("B-138 what 69...Rf1 does", lambda: says(B, {"ply": 138, "at": "before"}, ["Rf1"]))
case(
    "B-138 f6 after the move",
    lambda: s.squares(g[B], {"ply": 138, "at": "after"}, ["f6"])["squares"],
)
case("B-139 lines", lambda: lines(B, 139))
case("B-140 lines", lambda: lines(B, 140))
s.close()
case.save(args.out / "lt-replay-validation.json")
