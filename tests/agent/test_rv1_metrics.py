"""RV-1 (docs/design/review-2026-11-11.md), metrics: a silent arm is no 0-wrong moment in the
paired rates (P6-3); a tiered run that ends early or fails in tier 1 is counted, not lost (P5-3)."""

from __future__ import annotations

import json

import pytest
import test_wg
from test_tb_harness import _Model
from test_wg import LINES, _reply, _submit

from tools.rx import frames, harness, score
from tools.rx import report as rx_report


def _cell(sentences: int, wrong: int) -> dict:
    return {"sentences": sentences, "wrong": wrong, "search_only": 0}


def test_a_moment_where_an_arm_wrote_nothing_is_left_out_of_the_paired_rates() -> None:
    cells = {("train", "g1", 10): {"H": [_cell(0, 0)] * 3, "A": [_cell(10, 1)]},
             ("train", "g2", 12): {"H": [_cell(10, 2)], "A": [_cell(10, 1)]}}  # fmt: skip
    for field in ("wrong", "search_only", "wrong_or_search"):
        got = rx_report.paired(cells, "train", "H", "A", field)
        assert list(got["by_moment"]) == ["g2-12"], field  # g1-10: H silent, not "0 wrong"
    assert rx_report.paired(cells, "train", "H", "A", "wrong")["diff"] == pytest.approx(10.0)


@pytest.fixture
def quiet(monkeypatch):
    async def no_problems(session, game_id, claims, log):
        return [], [], []

    monkeypatch.setattr(harness, "check_claims", no_problems)
    monkeypatch.setattr(frames, "refs_needed", lambda args: set())
    monkeypatch.setattr(frames, "check", lambda args, records, version=None: {
        "held": [], "uncheckable": [], "ambiguous": [], "search_numbers": 0, "version": "t"})  # fmt: skip


def test_tier_1_failing_still_writes_the_tiers_line(tmp_path, quiet) -> None:
    # tier 1's first request finds no answer: the model raises, as a timeout would
    agent = _Model([_reply("FACTS"), _reply(calls=[_submit(3)]), _reply("ok")])
    with pytest.raises(IndexError):
        test_wg._run(tmp_path, agent, LINES, revision=15)
    lines = [json.loads(x) for x in (tmp_path / "RUN" / "agent.jsonl").read_text("utf-8").splitlines()]
    tiers = [x for x in lines if x["type"] == "tiers"]
    assert len(tiers) == 1 and tiers[0]["reason"] == "IndexError"
    assert set(tiers[0]["ends"].values()) == {"not_run"}


def test_a_tiered_run_that_ended_before_tier_1_asked_its_sample(tmp_path, monkeypatch) -> None:
    run = tmp_path / "R1"
    run.mkdir()
    (run / "agent.jsonl").write_text(json.dumps(
        {"seq": 1, "type": "start", "set": "validation", "game": "g", "moments": [3],
         "harness_tier1": "harness_tier1_v3"}) + "\n")  # fmt: skip
    values, completion = score.moment_rows([run], {}, tier=1)
    assert completion == {"submitted": 0, "asked": 3} and len(values) == 3
    (run / "agent.jsonl").write_text(json.dumps(
        {"seq": 1, "type": "start", "set": "validation", "game": "g", "moments": [3]}) + "\n")  # fmt: skip
    assert score.moment_rows([run], {}, tier=1)[1] == {"submitted": 0, "asked": 0}  # not tiered
