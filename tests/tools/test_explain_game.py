"""`tools/explain_game` with the synthetic engine (R4-D §7.11)."""

from __future__ import annotations

import json

import chess.pgn
from synthetic import engine

from tools.explain_game.__main__ import explain_game, grading_for, line

PGN = """[Event "test"]
[Site "https://www.chess.com/game/live/1"]
[WhiteElo "1500"]
[BlackElo "1480"]
[TimeControl "600"]

1. e4 e5 2. Nf3 Nc6 *
"""


def test_every_ply_is_explained_and_its_bundle_round_trips(tmp_path) -> None:
    records = explain_game(engine(), PGN, bundles=tmp_path)
    assert [r["move"] for r in records] == ["e4", "e5", "Nf3", "Nc6"]
    assert all(r["text"].startswith(f"{(r['ply'] + 1) // 2}.") for r in records)
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        f"{n}.{kind}" for n in range(1, 5) for kind in ("graph", "tree")
    )
    assert all(len(r["bundle"]["graph"]) == 64 for r in records)
    json.dumps(records)  # the --json records are plain data
    assert all(line(r) == r["text"] or line(r).startswith("[") for r in records)


def test_a_ply_range_and_the_grading_from_the_headers() -> None:
    records = explain_game(engine(), PGN, plies="3-4")
    assert [r["ply"] for r in records] == [3, 4]
    import io

    spec = grading_for(chess.pgn.read_game(io.StringIO(PGN)).headers)
    assert (spec.rating_pool, spec.time_class, spec.white_rating) == ("chesscom", "rapid", 1500)
    lichess = grading_for({"WhiteElo": "1500", "BlackElo": "1500", "TimeControl": "180+2"})
    assert (lichess.rating_pool, lichess.time_class) == ("lichess", "blitz")
    assert grading_for({}).white_rating is None  # the default curve
