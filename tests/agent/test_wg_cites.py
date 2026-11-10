"""Harness rev. 15 (the change log, "tier-1 cites completed"): rev. 14 with a tier-1 sentence that
writes a score or a rank its ply's digest gives under a handle it does not cite sent with that
handle added, and the tier-1 guide v3 that says what a number cites."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import test_wg
from test_tb_harness import _Model
from test_wg import LINES, _reply, _run, _submit

from tools.rx import frames, harness
from tools.rx import run as rx_run
from tools.rx import score as rx_score

H = "." + "a" * 24
DIGEST = {
    "ply": 6, "judgement": "j7" + H,
    "lines": {"played": {"ref": "s1" + H, "score_text": "+6.99"},
              "best": {"ref": "s2" + H, "score_text": "+9.58"}},
    "others": [{"ref": "s3" + H, "score_text": "+6.99"}, {"ref": "s4" + H, "score_text": "-0.40"}],
    "claims": [{"ref": "c5" + H, "status": "supported", "proves": "[비교] 물질 7점 이득",
                "also": [{"ref": "c6" + H, "status": "supported", "proves": "[비교] 엔진의 1순위는 Nf3였다"},
                         {"ref": "c9" + H, "status": "refuted", "proves": "[유일한 수] 엔진의 2순위 수는 …"}]}],
}  # fmt: skip


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    async def no_problems(session, game_id, claims, log):
        return [], [], []

    monkeypatch.setattr(harness, "check_claims", no_problems)
    monkeypatch.setattr(frames, "refs_needed", lambda args: set())
    monkeypatch.setattr(frames, "check", lambda args, records, version=None: {
        "held": [], "uncheckable": [], "ambiguous": [], "search_numbers": 0, "version": "t"})  # fmt: skip


def test_a_digests_scores_take_the_played_and_best_lines_first_and_ranks_only_supported() -> None:
    got = harness.digest_sources(json.dumps(DIGEST))
    assert got["scores"]["6.99"] == ["s1" + H, "s3" + H]  # the played line before another's
    assert got["scores"]["-0.40"] == ["s4" + H]
    assert got["ranks"] == {1: ["c6" + H]}  # a refuted claim's rank is none
    assert harness.digest_sources("not json") == {"scores": {}, "ranks": {}}


def test_a_score_or_rank_cited_nowhere_gets_its_handle_and_nothing_else_changes() -> None:
    game = harness.Game("1. e4 d5 2. exd5 Nf6 3. Nf3 Nxd5 4. Be2 e6 5. O-O Be7 *")
    sources = {6: harness.digest_sources(json.dumps(DIGEST))}
    args = {"items": [{"ply": 6, "sentences": [
        {"text": "판정은 부정확이고, 둔 수 +6.99는 엔진 1순위 Nf3(+9.58)보다 2.59점 낮다.",
         "cites": ["j7" + H]},
        {"text": "둔 수의 평가는 6.99였다.", "cites": ["s3" + H]},
        {"text": "흑의 평가 0.40은 쓰지 않는다.", "cites": ["j7" + H]}]}]}  # fmt: skip
    out, added = harness.complete_cites(args, sources, game)
    one, two, three = out["items"][0]["sentences"]
    assert one["cites"] == ["j7" + H, "s1" + H, "s2" + H, "c6" + H]  # 2.59: no score of it
    assert two["cites"] == ["s3" + H]  # a handle with the score is already cited
    assert three["cites"] == ["j7" + H]  # "0.40" is not "-0.40": a sign is never guessed
    assert added == ["s1" + H, "s2" + H, "c6" + H]
    assert args["items"][0]["sentences"][0]["cites"] == ["j7" + H]  # the input is not changed


class _Digests(test_wg._Server):
    async def call_tool(self, name, arguments):
        if name == "ply":
            self.calls.append((name, arguments))
            digest = dict(DIGEST, ply=arguments["ply"])
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(digest))],
                                   isError=False)  # fmt: skip
        return await super().call_tool(name, arguments)


def _scored_batch():
    return ("submit_commentary", {"game": "g", "agent": {"name": "t"}, "items": [
        {"ply": p, "sentences": [{"text": f"수 {p}는 +6.99, 엔진의 1순위는 Nf3였다.",
                                  "class": "sourced", "cites": ["j7"]}]}
        for p in (6, 8)]})  # fmt: skip


@pytest.mark.parametrize("revision, completed", [(15, True), (14, False)])
def test_rev_15_sends_the_completed_cites_and_rev_14_does_not(tmp_path, monkeypatch, revision,
                                                              completed):  # fmt: skip
    monkeypatch.setattr(test_wg, "_Server", _Digests)
    agent = _Model([_reply("FACTS"), _reply(calls=[_submit(3)]), _reply("ok"),
                    _reply(calls=[_scored_batch()]), _reply("ok")])  # fmt: skip
    reason, server, lines = _run(tmp_path, agent, LINES, revision=revision)
    assert reason == "done"
    batch = [a for n, a in server.calls if n == "submit_commentary"][1]
    cites = [i["sentences"][0]["cites"] for i in batch["items"]]
    want = ["j7" + H, "s1" + H, "c6" + H] if completed else ["j7" + H]
    assert cites == [want, want]  # the short name resolved first (rev. 14), then completed
    logged = [x for x in lines if x["type"] == "cites_completed"]
    assert (logged[0]["count"] == 4) if completed else not logged


def test_revision_15_is_revision_14_with_cites_completed_and_guide_v3() -> None:
    import inspect

    assert harness.VERSIONS[15] == harness.VERSIONS[14] and harness.FRAMES[15] == harness.FRAMES[14]
    assert harness.TIER1_GUIDES[15] == "harness_tier1_v3" and 15 in harness.LEAN_TIER1
    assert 15 in harness.SHORT_HANDLES and harness.COMPLETE_CITES == (15,)
    assert 15 in harness.TIERED and 15 in harness.PER_MOMENT
    guide = (harness.PROMPTS / "harness_tier1_v3.md").read_text(encoding="utf-8")
    assert "판정(`j…`)은 평가치를 담지 않습니다" in guide and "핸들은 `cites`에만" in guide
    assert "default=15" in inspect.getsource(rx_score.main)
    info = rx_run._harness_info(SimpleNamespace(arm="H", harness_revision=15, harness_guide=None))
    assert info["harness_tier1"] == "harness_tier1_v3"
    assert info["harness_tier1_cites_completed"] is True and info["harness_tier1_short_handles"]
