"""The Q3 acceptance tool (Q-D §9.12) without an engine: input, builds and tallies."""

from __future__ import annotations

from pathlib import Path

from tools.calibrate_curve.acceptance import (
    DESIGN_GAME,
    Ply,
    builds,
    chesscom_time_class,
    read_games,
    summarize,
)

TWO = """[Event "Live Chess"]
[WhiteElo "1520"]
[BlackElo "1480"]
[TimeControl "180+2"]

1. e4 e5 2. Nf3 $6 Nc6 3. Bc4?! Nf6?? 4. Ng5 $9 d5 1-0

[Event "Live Chess"]
[WhiteElo "2010"]
[BlackElo "?"]
[TimeControl "1/259200"]

1. d4 d5 1/2-1/2
"""


def test_chesscom_time_controls() -> None:
    assert chesscom_time_class("600") == "rapid"  # 10 | 0
    assert chesscom_time_class("180+2") == "blitz"
    assert chesscom_time_class("60") == "bullet"
    assert chesscom_time_class("1/259200") is None  # daily


def test_classes_from_nags_and_suffixes(tmp_path: Path) -> None:
    (tmp_path / "a.pgn").write_text(TWO)
    first, second = read_games(tmp_path)
    assert first.symbols[:8] == ["", "", "?!", "", "?!", "??", "miss", ""]
    assert (first.white, first.black, first.time_class) == (1520, 1480, "blitz")
    assert (second.white, second.black, second.time_class) == (2010, None, None)
    assert first.name == "a#1" and first.digest != second.digest


def test_the_design_game_is_recognised() -> None:
    design = read_games(DESIGN_GAME)[0]
    assert len(design.moves) == 55 and design.symbols[51] == "??"


def test_the_unit_build_changes_only_the_ratio() -> None:
    made = builds()
    shipped, unit = made["shipped"].curve_table(), made["unit"].curve_table()
    assert unit.cp_ratio_permille == 1000 and shipped.cp_ratio_permille != 1000
    assert unit.bands == shipped.bands and unit.knots[-1] == 1500


def _ply(n: int, theirs: str, table: str, unit: str, **kind) -> Ply:
    grades = {"quality_v1": ("excellent", 0), "scale 1000": ("good", 50),
              "table": (table, 0), "table 1000 ‰": (unit, 0)}  # fmt: skip
    return Ply(n, "m", theirs, grades, kind.get("allows", False), kind.get("misses", False))


def test_tallies_bands_sensitivity_and_mates(tmp_path: Path) -> None:
    (tmp_path / "a.pgn").write_text(TWO)
    game = read_games(tmp_path)[0]
    plies = [
        _ply(1, "", "excellent", "excellent"),
        _ply(2, "?!", "inaccuracy", "good"),
        _ply(3, "??", "blunder", "blunder", allows=True),
        _ply(4, "miss", "mistake", "mistake", misses=True),
    ]
    summary = summarize([(game, plies)])
    table = summary["overall"]["table"]
    assert (table["plies"], table["agree"], table["false_marks"], table["missed_marks"]) == (
        3,
        3,
        0,
        0,
    )
    assert (table["chesscom_miss"], table["miss_flagged"]) == (1, 1)  # Miss is counted apart
    assert summary["overall"]["quality_v1"]["missed_marks"] == 2
    assert summary["overall"]["quality_v1"]["miss_flagged"] == 0
    assert summary["labels"] is None  # no --labels
    assert list(summary["by_band"]) == ["1200–1599"]
    assert summary["permille_sensitivity"] == {"plies": 4, "changed": 1}
    assert [m["kind"] for m in summary["mate_moves"]] == ["allows mate", "misses mate"]


def test_labels_against_chesscom(tmp_path: Path) -> None:
    (tmp_path / "a.pgn").write_text(TWO)
    game = read_games(tmp_path)[0]
    plies = [_ply(1, "!", "best", "best"), _ply(2, "", "best", "best"), _ply(3, "!!", "best", "best"),
             _ply(4, "miss", "mistake", "mistake")]  # fmt: skip
    for p, ours in zip(plies, (("great",), ("great",), (), ()), strict=True):
        p.labels = ours
    labels = summarize([(game, plies)])["labels"]
    assert (labels["great"]["chesscom"], labels["great"]["ours"], labels["great"]["matched"]) == (
        1,
        2,
        1,
    )
    assert labels["great"]["extra"] == ["a#1 ply 2 m"]
    assert labels["brilliant"]["missed"] == ["a#1 ply 3 m"] and labels["miss"]["matched"] == 0
    assert labels["great"]["extra_by_mark"] == {"none": 1}  # MV-D review N2


def test_an_extra_miss_is_counted_by_chesscoms_mark(tmp_path: Path) -> None:
    """MV-D review N2: a MISS on a move chess.com marks `?` is the Miss / Mistake confusion."""

    (tmp_path / "a.pgn").write_text(TWO)
    game = read_games(tmp_path)[0]
    plies = [_ply(1, "?", "mistake", "mistake"), _ply(2, "", "good", "good"),
             _ply(3, "??", "blunder", "blunder"), _ply(4, "miss", "mistake", "mistake")]  # fmt: skip
    for p, ours in zip(plies, (("miss",), ("miss",), ("miss",), ("miss",)), strict=True):
        p.labels = ours
    row = summarize([(game, plies)])["labels"]["miss"]
    assert (row["matched"], row["extra_by_mark"]) == (1, {"?": 1, "??": 1, "none": 1})
