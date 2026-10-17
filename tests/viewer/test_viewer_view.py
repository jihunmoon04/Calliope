"""AG6-D §6.1, §6.3 (viewer): the page reads `show_game`'s `calliope_view_v1` — empty and analysed,
from the synthetic engine — and follows a job at the intervals the design gives."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for sub in ("tests/agent", "tests/server", "tests/facts/search", ""):
    if str(ROOT / sub) not in sys.path:
        sys.path.insert(0, str(ROOT / sub))

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    from agent_helpers import G1, GAME, session

    data = tmp_path_factory.mktemp("view")
    s = session(data)
    try:
        s.open_game(pgn=GAME)
        empty, _ = s.show_game(G1)
        s.analyze_game(G1, plies="1-4", wait_seconds=60)
        analysed, _ = s.show_game(G1)
    finally:
        s.close()
    path = data / "cases.json"
    path.write_text(json.dumps({"empty": empty, "analysed": analysed}))
    run = subprocess.run([NODE, str(ROOT / "tests/viewer/check_view.js"),
                          str(ROOT / "viewer/index.html"), str(path)],
                         capture_output=True, text=True, check=False)  # fmt: skip
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def test_an_empty_board_is_the_game_with_no_plies(out) -> None:
    assert out["empty"] == {"schema": "calliope_result_v1", "plies": [], "moves": 10,
                            "provenance": False, "states": ["none"] * 10, "job": None,
                            "kept": 3}  # fmt: skip


def test_an_analysed_board_is_its_result_with_the_states_and_the_job(out) -> None:
    analysed = out["analysed"]
    assert analysed["plies"] == [1, 2, 3, 4] and analysed["provenance"] is True
    assert analysed["states"] == ["analysed"] * 4 + ["none"] * 6
    assert analysed["job"]["state"] == "done" and analysed["job"]["done"] == 4
    assert out["result"]["states"] is None and out["result"]["plies"] == [1, 2, 3, 4]


def test_the_board_follows_a_job_at_its_intervals(out) -> None:
    assert out["intervals"] == [None, 5000, 5000, 5000, 30000, 60000, None]


def test_the_lines_for_a_ply_without_a_record_and_for_the_job(out) -> None:
    none, plain, pending, failed, elsewhere, omitted = out["states"]
    assert none == plain == "이 수는 분석되지 않았습니다."
    assert pending == "분석 중입니다." and failed == "이 수는 분석하지 못했습니다."
    assert "범위 밖" in elsewhere and "다 담지 못했습니다" in omitted
    assert out["jobs"] == ["분석 중 3/10 · 약 20초 남음", "분석 예산 대기 4/10 · 10분 뒤 재개",
                           "분석 완료 10/10"]  # fmt: skip
