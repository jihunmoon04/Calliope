"""`tools/explain_game` with the synthetic engine (R4-D §7.11; AR-D §7.8)."""

from __future__ import annotations

import json

import chess.pgn
import jsonschema
from synthetic import engine

from calliope.results import schema
from tools.explain_game.__main__ import explain_game, fallback_warning, grading_for, line

PGN = """[Event "test"]
[Site "https://www.chess.com/game/live/1"]
[WhiteElo "1500"]
[BlackElo "1480"]
[TimeControl "600"]

1. e4 e5 2. Nf3 Nc6 *
"""
UNRATED = """[Event "test"]
[White "?"]

1. e4 e5 2. Nf3 *
"""


def test_every_ply_is_explained_and_its_bundle_round_trips(tmp_path) -> None:
    records, document = explain_game(engine(), PGN, bundles=tmp_path)
    assert [r["move"] for r in records] == ["e4", "e5", "Nf3", "Nc6"]
    assert all(r["text"].startswith(f"{(r['ply'] + 1) // 2}.") for r in records)
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        f"{n}.{kind}" for n in range(1, 5) for kind in ("graph", "tree")
    )
    assert all(len(r["bundle"]["graph"]) == 64 for r in records)
    json.dumps(records)  # the --json records are plain data
    assert all(line(r) == r["text"] or line(r).startswith("[") for r in records)
    assert [p["bundle"]["stored"] for p in document["plies"]] == [True] * 4  # written, re-loaded
    assert [p["bundle"]["graph"] for p in document["plies"]] == [
        r["bundle"]["graph"] for r in records
    ]


def test_a_ply_range_and_the_grading_from_the_headers() -> None:
    records, document = explain_game(engine(), PGN, plies="3-4")
    assert [r["ply"] for r in records] == [3, 4]
    assert [p["ply"] for p in document["plies"]] == [3, 4] and len(document["game"]["moves"]) == 4
    assert document["grading"]["curve"]["source"] == "table"
    assert document["game"]["headers"] == {"white_rating": 1500, "black_rating": 1480,
                                           "time_control": "600",
                                           "site": "https://www.chess.com/game/live/1", "result": "*"}  # fmt: skip
    assert fallback_warning(document) is None
    import io

    spec = grading_for(chess.pgn.read_game(io.StringIO(PGN)).headers)
    assert (spec.rating_pool, spec.time_class, spec.white_rating) == ("chesscom", "rapid", 1500)
    lichess = grading_for({"WhiteElo": "1500", "BlackElo": "1500", "TimeControl": "180+2"})
    assert (lichess.rating_pool, lichess.time_class) == ("lichess", "blitz")
    assert grading_for({}).white_rating is None  # the default curve


def test_json_alone_carries_the_digests(tmp_path, monkeypatch) -> None:
    """R4 review B1: `--json` without `--bundles` still records both documents' digests."""

    records, document = explain_game(engine(), PGN, plies="1-2", digests=True)
    assert all(len(r["bundle"]["tree"]) == len(r["bundle"]["graph"]) == 64 for r in records)
    assert [p["bundle"]["stored"] for p in document["plies"]] == [False, False]
    assert not any(tmp_path.iterdir())  # nothing written

    from calliope.facts import search
    from tools.explain_game import __main__ as tool

    class Synthetic:
        @staticmethod
        def start(path):
            port = engine()
            port.close = lambda: None
            return port

    monkeypatch.setattr(search, "StockfishEngine", Synthetic)
    monkeypatch.setenv("CALLIOPE_STOCKFISH_PATH", "synthetic")
    pgn, out = tmp_path / "g.pgn", tmp_path / "r.json"
    pgn.write_text(PGN)
    assert tool.main([str(pgn), "--plies", "1-2", "--json", str(out)]) == 0
    saved = json.loads(out.read_bytes().decode("utf-8"))
    jsonschema.validate(saved, schema(), cls=jsonschema.Draft202012Validator)
    assert saved["schema"] == "calliope_result_v1"
    assert [len(p["bundle"]["graph"]) for p in saved["plies"]] == [64, 64]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["g.pgn", "r.json"]  # no bundles


def test_json_writes_the_result_and_warns_on_the_default_curve(tmp_path, monkeypatch, capsys):
    """AR-D §7.8: `--json` writes a valid `calliope_result_v1`; the fallback prints a warning."""

    from calliope.facts import search
    from tools.explain_game import __main__ as tool

    class Synthetic:
        @staticmethod
        def start(path):
            port = engine()
            port.close = lambda: None
            return port

    monkeypatch.setattr(search, "StockfishEngine", Synthetic)
    monkeypatch.setenv("CALLIOPE_STOCKFISH_PATH", "synthetic")
    pgn, out = tmp_path / "g.pgn", tmp_path / "r.json"
    pgn.write_text(UNRATED)
    assert tool.main([str(pgn), "--json", str(out)]) == 0
    saved = json.loads(out.read_bytes().decode("utf-8"))
    jsonschema.validate(saved, schema(), cls=jsonschema.Draft202012Validator)
    assert saved["grading"]["fallback"] is True and saved["game"]["headers"] == {"result": "*"}
    assert [p["ply"] for p in saved["plies"]] == [1, 2, 3]
    captured = capsys.readouterr()
    assert captured.err.count("warning: graded with the default curve") == 1
    assert len(captured.out.splitlines()) == 3  # the text output is unchanged: one line a ply


def test_an_empty_range_prints_nothing_and_json_refuses_it(tmp_path, monkeypatch, capsys):
    """AR1 review B2: text-only keeps R4's empty output; `--json` is a clear input error."""

    assert explain_game(engine(), PGN, plies="9-12") == ([], None)
    assert explain_game(engine(), '[Event "empty"]\n\n*\n') == ([], None)

    from calliope.facts import search
    from tools.explain_game import __main__ as tool

    class Synthetic:
        @staticmethod
        def start(path):
            port = engine()
            port.close = lambda: None
            return port

    monkeypatch.setattr(search, "StockfishEngine", Synthetic)
    monkeypatch.setenv("CALLIOPE_STOCKFISH_PATH", "synthetic")
    pgn, out = tmp_path / "g.pgn", tmp_path / "r.json"
    pgn.write_text(PGN)
    assert tool.main([str(pgn), "--plies", "9-12"]) == 0
    assert capsys.readouterr() == ("", "")
    assert tool.main([str(pgn), "--plies", "9-12", "--json", str(out)]) == 2
    assert "no ply to analyse" in capsys.readouterr().err and not out.exists()


def test_analysis_puts_every_claim_in_the_document() -> None:
    """DF-D §4.3: `--analysis` (here `detail=True`) adds each ply's `analysis`."""

    _records, plain = explain_game(engine(), PGN, plies="1-2")
    _records, full = explain_game(engine(), PGN, plies="1-2", detail=True)
    assert all("analysis" not in p for p in plain["plies"])
    assert all(p["analysis"]["claims"] == [] or p["analysis"]["claims"][0]["id"]
               for p in full["plies"])  # fmt: skip
    jsonschema.validate(full, schema(), cls=jsonschema.Draft202012Validator)
    assert [p["text"] for p in full["plies"]] == [p["text"] for p in plain["plies"]]
