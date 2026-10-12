"""The static viewer's pure part, run with node against python-chess and real documents."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import chess
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "results"))
sys.path.insert(0, str(ROOT / "tests" / "reasoning"))
sys.path.insert(0, str(ROOT / "tests" / "facts" / "search"))

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def _moves() -> list[dict]:
    """Castling both ways, en passant, promotions (with capture) and ordinary moves."""

    out = []
    for fen, sans in [
        (chess.STARTING_FEN, "e4 e5 Nf3 Nc6 Bc4 Bc5 O-O Nf6 d4 exd4 e5 d5 exd6"),
        ("r3k2r/pppq1ppp/8/8/8/8/PPPQ1PPP/R3K2R w KQkq - 0 1", "O-O-O O-O-O Kb1 Kb8"),
        ("r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1", "O-O O-O-O"),
        ("1n6/P6k/8/8/8/8/6p1/K6R w - - 0 1", "axb8=Q gxh1=N"),
        ("8/P7/8/8/8/8/k7/4K3 w - - 0 1", "a8=R"),
    ]:
        board = chess.Board(fen)
        for san in sans.split():
            before = board.fen()
            move = board.parse_san(san)
            board.push(move)
            out.append({"fen": before, "uci": move.uci(), "after": board.fen()})
    return out


def _documents() -> list[dict]:
    from corpus_case import analyse, cases
    from result_input import engine_run, game_input, ply_input

    from calliope.results import game_result

    docs = []
    for case in cases():
        a = analyse(case)
        game = game_input(case["fen"], [*case.get("before", "").split(), case["played"]])
        docs.append(game_result(game, engine_run(a), [ply_input(a)]))
    return docs


def test_the_viewer_draws_every_position_and_reference(tmp_path) -> None:
    cases = {"moves": _moves(), "documents": _documents()}
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases))
    run = subprocess.run([NODE, str(ROOT / "tests/viewer/check.js"), str(ROOT / "viewer/index.html"),
                          str(path)], capture_output=True, text=True, check=False)  # fmt: skip
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    assert out["moves"] == len(cases["moves"])
    assert out["plies"] == len(cases["documents"]) == 12
    assert out["svgPieces"] > 0

    # the fork: the knight on f3 and the move that put it there, drawn in one position
    fork = next(f for f in out["frames"] if f["text"].startswith("Through the fork"))
    (frame,) = fork["frames"]
    assert frame["rings"] == ["f3"] and frame["arrows"] == [["g5", "f3"]]
    # the better move and its four-ply line: one frame per shown ply, the first merged
    better = next(f for f in out["frames"] if f["text"].startswith("Instead, 1.Nb3 was better"))
    assert [a for fr in better["frames"] for a in fr["arrows"]] == [
        ["d4", "b3"], ["g5", "e6"], ["e1", "d2"], ["e8", "d7"]
    ]  # fmt: skip
    assert len(better["frames"]) == 4
    assert better["frames"][0]["caption"] == "<b>1.Nb3</b> Ne6 2.Kd2 Kd7"  # merged, not repeated
    assert "<b>2.Kd2</b>" in better["frames"][2]["caption"]
