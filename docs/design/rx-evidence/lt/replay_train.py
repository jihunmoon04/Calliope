"""LT-D §6.2 step 1: Train's 13 tool-shaped cases of LT-D §0.2 put to the v8 tools (no model).
Writes `lt-replay-train.json` (agent-lt-implementation.md §9.1)."""

from __future__ import annotations

from replay_common import REPO, Cases, arguments, session_on

args = arguments(__doc__)
PGNS = {"rapid": "tests/reasoning/fixtures/chesscom_rapid_813_801.pgn",
        "fresh": "tests/agent/fixtures/weak_engines_1.pgn",
        "fourth": "tests/agent/fixtures/weak_engines_2.pgn"}  # fmt: skip
s = session_on(args.rx_data / "base" / "train" / "data")
g = {n: s.open_game(pgn=(REPO / p).read_text(encoding="utf-8"))["game"] for n, p in PGNS.items()}
case = Cases()


def sq(game, position, squares):
    return s.squares(g[game], position, squares)["squares"]


def end_squares(game, position, moves, squares):
    a = s.explore(g[game], position, moves)
    return {"moves": [p["san"] for p in a["ledger"]["plies"]], "end": a["ledger"]["end"],
            "squares": sq(game, {"from_root": a["end"]["from_root"]}, squares)}  # fmt: skip


# relations (7)
case("fourth-37 d4 defenders", lambda: sq("fourth", {"ply": 37, "at": "after"}, ["d4"]))
case(
    "fourth-38 f5 vs queen d7",
    lambda: end_squares(
        "fourth", {"ply": 38, "at": "before"}, ["Qxh6", "Qxd7", "f5"], ["d7", "f5"]
    ),
)
case("fresh-56 who takes g4", lambda: sq("fresh", {"ply": 56, "at": "before"}, ["g4"]))
case("fresh-62 d5 change", lambda: sq("fresh", {"ply": 62, "at": "after"}, ["d5"]))
case(
    "rapid-40 d6 defenders",
    lambda: end_squares(
        "rapid", {"ply": 40, "at": "after"}, ["dxc6", "Nd6", "Bd3", "bxc6"], ["d6"]
    ),
)
case("rapid-52 f7 (two runs)", lambda: sq("rapid", {"ply": 52, "at": "after"}, ["f7"]))
# a line's outcome (3)
case(
    "fourth-56 ranking after 28...Bxg3",
    lambda: {
        k: v
        for k, v in s.compare_lines(g["fourth"], 57, length=8, candidates=["Rxg3"]).items()
        if k in ("ranking", "root")
    },
)
# review F1: the line the sentence was about — the reference's played line of 28...Bxg3
# (references_v1/train/fourth-56.json: 28...Bxg3 29.Rg2 Qh1+ 30.Rg1 Qh4 31.Bf5 Bd6 32.Re2) — played
# as given, not the engine's own line from a new search
case(
    "fourth-56 the reference line's end",
    lambda: end_squares(
        "fourth",
        {"ply": 56, "at": "after"},
        ["Rg2", "Qh1+", "Rg1", "Qh4", "Bf5", "Bd6", "Re2"],
        ["d6", "g3", "f2"],
    ),
)


def h_pawns():
    a = s.explore(g["fresh"], {"ply": 76, "at": "before"}, ["Rxh5", "gxh5", "Qxh5"])
    return {"moves": [p["san"] for p in a["ledger"]["plies"]], "captured": a["ledger"]["captured"],
            "net": a["ledger"]["net"]}  # fmt: skip


case("fresh-76 who took the h-pawns", h_pawns)


# lines compared (3)
def rapid52():
    a = s.compare_lines(g["rapid"], 52, length=16)
    return {k: {"moves": v["moves"], "ledger": v["ledger"], "end": v["end"]}
            for k, v in a["lines"].items()}  # fmt: skip


case("rapid-52 which line holds the 1-point loss", rapid52)
case(
    "rapid-54 does 27...Kxf7 avoid mate",
    lambda: s.compare_lines(g["rapid"], 54, length=8, candidates=["Kxf7", "Kh8"])["ranking"],
)


def recapture():
    a = s.explore(g["rapid"], {"ply": 54, "at": "before"}, ["Kxf7", "Rxe8", "Nxe8"])
    return {"plies": [{k: p.get(k) for k in ("san", "says", "captured")}
                      for p in a["ledger"]["plies"]], "net": a["ledger"]["net"]}  # fmt: skip


case("rapid-54 after 27...Kxf7 28.Rxe8", recapture)
s.close()
case.save(args.out / "lt-replay-train.json")
