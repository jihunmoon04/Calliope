"""Harness rev. 17 (the change log, "tier 2's rewrites"; the eight-game survey): a tier-2
submission gets tier 1's rewrites — a missing `agent`, short cites resolved from the moment's
answers, a lone comparison or fact handle dropped, handles taken out of the text, a score or rank
cited by the handle its `ply` answer gives."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import test_wg
from test_tb_harness import _Model
from test_wg import LINES, _batch, _reply, _run

from tools.rx import frames, harness
from tools.rx import run as rx_run
from tools.rx import score as rx_score

H = "." + "d" * 24
DIGEST3 = {"ply": 3, "judgement": "j1" + H,
           "lines": {"played": {"ref": "s1" + H, "score_text": "+0.50"},
                     "best": {"ref": "s2" + H, "score_text": "+1.20"}},
           "claims": [{"ref": "c3" + H, "status": "supported", "proves": "[비교] 엔진의 1순위는 Nf3였다"}]}  # fmt: skip


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    async def no_problems(session, game_id, claims, log):
        return [], [], []

    monkeypatch.setattr(harness, "check_claims", no_problems)
    monkeypatch.setattr(frames, "refs_needed", lambda args: set())
    monkeypatch.setattr(frames, "check", lambda args, records, version=None: {
        "held": [], "uncheckable": [], "ambiguous": [], "search_numbers": 0, "version": "t"})  # fmt: skip


class _Digests(test_wg._Server):
    async def call_tool(self, name, arguments):
        if name == "ply" and arguments.get("ply") == 3:
            self.calls.append((name, arguments))
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(DIGEST3))],
                                   isError=False)  # fmt: skip
        if name == "explore":
            self.calls.append((name, arguments))
            text = json.dumps({"line": "x7" + H, "compare": "k1" + H})
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], isError=False)
        return await super().call_tool(name, arguments)


def _moment_submit():
    return ("submit_commentary", {"game": "g", "ply": 3, "agent": None, "sentences": [
        {"text": "판정은 실수다 (j1). 둔 수는 +0.50, 엔진의 1순위는 Nf3였다.", "class": "sourced",
         "cites": ["j1"]},
        {"text": "라인에서 백이 앞선다.", "class": "sourced", "cites": ["x7", "k1" + H]}]})  # fmt: skip


def _agent():
    return _Model([_reply(calls=[("ply", {"game": "g", "ply": 3}), ("explore", {"game": "g", "ply": 3})]),
                   _reply("FACTS"), _reply(calls=[_moment_submit()]), _reply("ok"),
                   _reply(calls=[_batch(6, 8)])])  # fmt: skip


def test_rev_17_rewrites_a_tier_2_submission(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(test_wg, "_Server", _Digests)
    reason, server, lines = _run(tmp_path, _agent(), LINES, revision=17)
    assert reason == "done"
    sent = next(a for n, a in server.calls if n == "submit_commentary")
    assert sent["agent"] == {"name": "commentator"}
    one, two = sent["sentences"]
    assert one["text"] == "판정은 실수다. 둔 수는 +0.50, 엔진의 1순위는 Nf3였다."
    assert one["cites"] == ["j1" + H, "s1" + H, "c3" + H]  # resolved, then completed
    assert two["cites"] == ["x7" + H]  # the lone comparison handle dropped
    logged = next(x for x in lines if x["type"] == "tier2_rewrites")
    assert logged["agent_set"] and logged["resolved"] == 2 and logged["dropped"] == ["k1" + H]


def test_rev_16_sends_a_tier_2_submission_as_written(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(test_wg, "_Server", _Digests)
    _, server, lines = _run(tmp_path, _agent(), LINES, revision=16)
    sent = next(a for n, a in server.calls if n == "submit_commentary")
    assert sent["agent"] is None and sent["sentences"][0]["cites"] == ["j1"]
    assert not [x for x in lines if x["type"] == "tier2_rewrites"]


def test_a_short_name_two_handles_share_is_never_resolved() -> None:
    gate = harness.Gate(None, harness.Game(test_wg.GAME), None, "g")
    gate._learn("explore", {}, json.dumps({"a": "x7" + H}))
    gate._learn("explore", {}, json.dumps({"a": "x7." + "e" * 24}))
    gate._learn("explore", {}, json.dumps({"a": "x7" + H}))
    assert "x7" not in gate.moment_names and "x7" in gate.moment_shared
    gate.new_moment()
    assert gate.moment_names == {} and gate.moment_shared == set()


def test_revision_17_is_revision_16_with_tier_2_rewrites() -> None:
    import inspect

    assert harness.VERSIONS[17] == harness.VERSIONS[16] and harness.FRAMES[17] == harness.FRAMES[16]
    assert harness.guide_of(17) == "harness_guide_v1"
    assert 17 in harness.TIER2_LEAN and all(17 in t for t in (
        harness.TIERED, harness.LEAN_TIER1, harness.SHORT_HANDLES, harness.COMPLETE_CITES,
        harness.REVIEWED, harness.PER_MOMENT))  # fmt: skip
    assert "default=1" in inspect.getsource(rx_score.main)  # rev. 17 or later
    info = rx_run._harness_info(SimpleNamespace(arm="H", harness_revision=17, harness_guide=None))
    assert info["harness_tier2_lean"] is True
