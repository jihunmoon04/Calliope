"""Harness rev. 13 (the change log, "tier 1 cheaper"): rev. 12 with handles taken out of a tier-1
sentence's text before it is sent, a batch that ends once every ply of it is accepted, and the
tier-1 guide v2 that says so."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from test_tb_harness import _Model
from test_wg import LINES, _batch, _reply, _run, _submit

from tools.rx import frames, harness
from tools.rx import run as rx_run
from tools.rx import score as rx_score


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    async def no_problems(session, game_id, claims, log):
        return [], [], []

    monkeypatch.setattr(harness, "check_claims", no_problems)
    monkeypatch.setattr(frames, "refs_needed", lambda args: set())
    monkeypatch.setattr(frames, "check", lambda args, records, version=None: {
        "held": [], "uncheckable": [], "ambiguous": [], "search_numbers": 0, "version": "t"})  # fmt: skip


def test_a_bracket_of_cited_handles_is_taken_out_and_nothing_else() -> None:
    args = {"items": [{"ply": 6, "sentences": [
        {"text": "판정은 부정확입니다 (j11).", "cites": ["j11.abc"]},
        {"text": "1순위는 3...cxd4(+0.37)였고 (c47, s111) e4 칸(e4)을 본다 [b16.f0].",
         "cites": ["c47.a", "s111.a", "b16.f0"]},
        {"text": "(x9) 라인은 인용하지 않았다.", "cites": ["j11.abc"]}]}]}  # fmt: skip
    out, removed = harness.strip_cited_handles(args)
    texts = [s["text"] for s in out["items"][0]["sentences"]]
    assert removed == 3
    assert texts[0] == "판정은 부정확입니다."
    assert texts[1] == "1순위는 3...cxd4(+0.37)였고 e4 칸(e4)을 본다."  # a score, a square stay
    assert texts[2] == "(x9) 라인은 인용하지 않았다."  # not a cited handle: kept
    assert args["items"][0]["sentences"][0]["text"].endswith("(j11).")  # the input is not changed


def _note(ply):
    return ("submit_commentary", {"game": "g", "agent": {"name": "t"}, "items": [
        {"ply": p, "sentences": [{"text": f"수 {p} (j1)", "class": "interpretation",
                                  "cites": ["j1.t"]}]} for p in ply]})  # fmt: skip


def test_rev_13_sends_the_text_without_the_handles_and_logs_it(tmp_path) -> None:
    agent = _Model([_reply("FACTS"), _reply(calls=[_submit(3, "장면 (j1)", ["j1.t"])]), _reply("ok"),
                    _reply(calls=[_note([6, 8])])])  # fmt: skip
    reason, server, lines = _run(tmp_path, agent, LINES, revision=13)
    assert reason == "done"
    sent = [a for n, a in server.calls if n == "submit_commentary"]
    assert sent[0]["sentences"][0]["text"] == "장면 (j1)"  # tier 2 is as it was
    assert [s["sentences"][0]["text"] for s in sent[1]["items"]] == ["수 6", "수 8"]
    assert next(x for x in lines if x["type"] == "handles_stripped")["count"] == 2


def test_rev_13_ends_a_batch_once_every_ply_is_accepted(tmp_path) -> None:
    # no answer after the accepted batch: rev. 12 would ask the model once more
    agent = _Model(
        [_reply("FACTS"), _reply(calls=[_submit(3)]), _reply("ok"), _reply(calls=[_batch(6, 8)])]
    )
    reason, _, lines = _run(tmp_path, agent, LINES, revision=13)
    assert reason == "done" and agent.replies == []
    end = next(x for x in lines if x["type"] == "batch_end")
    assert end["accepted"] == [6, 8] and end["reason"] == "done"
    with pytest.raises(IndexError):  # rev. 12 asks for the answer rev. 13 does without
        _run(tmp_path / "r12", _Model([_reply("FACTS"), _reply(calls=[_submit(3)]), _reply("ok"),
                                      _reply(calls=[_batch(6, 8)])]), LINES, revision=12)  # fmt: skip


def test_a_batch_with_a_ply_left_out_still_gets_its_answer(tmp_path) -> None:
    agent = _Model([_reply("FACTS"), _reply(calls=[_submit(3)]), _reply("ok"),
                    _reply(calls=[_batch(6)]), _reply("8은 뺐다")])  # fmt: skip
    reason, _, lines = _run(tmp_path, agent, LINES, revision=13)
    assert reason == "done" and agent.replies == []
    assert next(x for x in lines if x["type"] == "tiers")["ends"] == {
        "6": "submitted",
        "8": "left_out",
    }


def test_revision_13_is_revision_12_with_a_lean_tier_1() -> None:
    import inspect

    assert harness.VERSIONS[13] == harness.VERSIONS[12] and harness.FRAMES[13] == harness.FRAMES[12]
    assert 13 in harness.TIERED and 13 in harness.PER_MOMENT and harness.LEAN_TIER1 == (13,)
    guide = (harness.PROMPTS / f"{harness.TIER1_GUIDES[13]}.md").read_text(encoding="utf-8")
    assert "핸들은 `cites`에만" in guide and "harness_tier1_v2" in guide
    assert "default=13" in inspect.getsource(rx_score.main)
    info = rx_run._harness_info(SimpleNamespace(arm="H", harness_revision=13, harness_guide=None))
    assert info["harness_tier1"] == "harness_tier1_v2" and info["harness_tier1_lean"] is True
    info12 = rx_run._harness_info(SimpleNamespace(arm="H", harness_revision=12, harness_guide=None))
    assert info12["harness_tier1"] == "harness_tier1_v1" and info12["harness_tier1_lean"] is False
    assert json.dumps(info)  # the start line takes it as written
