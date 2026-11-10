"""Harness rev. 14 (the change log, "short handles resolved"): rev. 13 with a tier-1 cite written by
its short name ("j7") sent as the handle of that name in its ply's digest."""

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

J6 = "j7." + "a" * 24
S6 = "s94." + "b" * 24
J8 = "j9." + "c" * 24


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    async def no_problems(session, game_id, claims, log):
        return [], [], []

    monkeypatch.setattr(harness, "check_claims", no_problems)
    monkeypatch.setattr(frames, "refs_needed", lambda args: set())
    monkeypatch.setattr(frames, "check", lambda args, records, version=None: {
        "held": [], "uncheckable": [], "ambiguous": [], "search_numbers": 0, "version": "t"})  # fmt: skip


def test_short_names_are_the_digests_handles_and_never_a_shared_one() -> None:
    text = json.dumps(
        {"judgement": J6, "lines": [S6, "s94." + "d" * 24], "claims": ["c3." + "e" * 24]}
    )
    got = harness.short_names(text)
    assert got["j7"] == J6 and got["c3"] == "c3." + "e" * 24
    assert "s94" not in got  # two handles share the name: neither is guessed


def test_a_short_cite_is_resolved_by_its_own_plys_digest() -> None:
    game = harness.Game("1. e4 d5 2. exd5 Nf6 3. Nf3 Nxd5 4. Be2 e6 5. O-O Be7 *")
    refs = {6: {"j7": J6, "s94": S6}, 8: {"j9": J8}}
    args = {"items": [
        {"ply": 6, "propositions": [{"id": "s94", "kind": "x"}],
         "sentences": [{"text": "a", "cites": ["j7", "s94", J6, "j9"], "states": ["j7"]}]},
        {"ply": 8, "sentences": [{"text": "b", "cites": ["j9", "j7"]}]}]}  # fmt: skip
    out, resolved = harness.resolve_short_handles(args, refs, game)
    one, two = out["items"][0]["sentences"][0], out["items"][1]["sentences"][0]
    assert one["cites"] == [J6, "s94", J6, "j9"]  # a proposition's id and another ply's name stay
    assert one["states"] == [J6]
    assert two["cites"] == [J8, "j7"]
    assert resolved == 3
    assert args["items"][0]["sentences"][0]["cites"][0] == "j7"  # the input is not changed


class _Digests(test_wg._Server):
    async def call_tool(self, name, arguments):
        if name == "ply":
            self.calls.append((name, arguments))
            handle = {6: J6, 8: J8}[arguments["ply"]]
            text = json.dumps({"judgement": handle})
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], isError=False)
        return await super().call_tool(name, arguments)


def _short_batch():
    return ("submit_commentary", {"game": "g", "agent": {"name": "t"}, "items": [
        {"ply": p, "sentences": [{"text": f"수 {p}", "class": "sourced", "cites": [name]}]}
        for p, name in ((6, "j7"), (8, "j9"))]})  # fmt: skip


@pytest.mark.parametrize("revision, resolved", [(14, True), (13, False)])
def test_rev_14_sends_full_handles_and_rev_13_does_not(tmp_path, monkeypatch, revision, resolved):
    monkeypatch.setattr(test_wg, "_Server", _Digests)
    agent = _Model([_reply("FACTS"), _reply(calls=[_submit(3)]), _reply("ok"),
                    _reply(calls=[_short_batch()]), _reply("ok")])  # fmt: skip
    reason, server, lines = _run(tmp_path, agent, LINES, revision=revision)
    assert reason == "done"
    batch = [a for n, a in server.calls if n == "submit_commentary"][1]
    cites = [i["sentences"][0]["cites"] for i in batch["items"]]
    assert cites == ([[J6], [J8]] if resolved else [["j7"], ["j9"]])
    logged = [x for x in lines if x["type"] == "handles_resolved"]
    assert (logged[0]["count"] == 2) if resolved else not logged


def test_revision_14_is_revision_13_with_short_handles_resolved() -> None:
    import inspect

    assert harness.VERSIONS[14] == harness.VERSIONS[13] and harness.FRAMES[14] == harness.FRAMES[13]
    assert harness.TIER1_GUIDES[14] == harness.TIER1_GUIDES[13] and 14 in harness.LEAN_TIER1
    assert 14 in harness.SHORT_HANDLES and 14 in harness.TIERED and 14 in harness.PER_MOMENT
    assert 14 not in harness.COMPLETE_CITES
    assert "default=1" in inspect.getsource(rx_score.main)  # rev. 14 or later
    info = rx_run._harness_info(SimpleNamespace(arm="H", harness_revision=14, harness_guide=None))
    assert info["harness_tier1_short_handles"] is True
