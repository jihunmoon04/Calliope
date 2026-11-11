"""RV-1 (docs/design/review-2026-11-11.md), harness rev. 16: the frame check v5 (P5-1, P5-6,
P5-7, P5-8), tier 1's story (P5-2), tools (P5-5), normalized rewrites (P5-9), a bracketed square
(P5-10) and tier 0's start (P5-4)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from test_tb_harness import _Model
from test_wg import LINES, _batch, _reply, _run, _submit

from tools.rx import frames, harness, tiers
from tools.rx import run as rx_run
from tools.rx import score as rx_score

V4, V5 = frames.FRAMES_V4, frames.FRAMES_V5


def _book(start: int, rows: list[tuple[str, int]]) -> dict:
    return {"standing": {"start": {"white_minus_black": start}},
            "plies": [{"san": san, "source": "analysis", "standing_white": x} for san, x in rows]}  # fmt: skip


def _call(text: str, cites: list[str], props: list[dict] = ()) -> dict:
    return {"items": [{"ply": 1, "propositions": list(props),
                       "sentences": [{"text": text, "cites": cites}]}]}  # fmt: skip


def _rules(out: dict) -> list[str]:
    return sorted(h["rule"] for h in out["held"])


def test_v5_holds_a_change_written_as_the_standing_beside_a_loss() -> None:
    records = {"x1.t": ("explored_line", {"ledger": _book(-10, [("Qxa8", -5), ("Kb8", -1)])})}
    m = {"id": "m", "kind": "material", "line": "x1.t", "from": 0, "to": 2, "side": "black",
         "balance": -9}  # fmt: skip
    call = _call("이 라인에서 흑은 9점을 잃고, 라인 끝 물질은 흑 -9입니다.", ["m"], [m])
    assert _rules(frames.check(call, records, V4)) == []  # P5-1: v4 lost it
    assert _rules(frames.check(call, records, V5)) == ["F1"]


def test_v5_reads_a_grown_lead_as_a_change() -> None:
    records = {"x1.t": ("explored_line", {"ledger": _book(2, [("Qxd5", 3), ("Rd8", 5)])})}
    call = _call("이 라인에서 백이 3점 더 앞선다.", ["x1.t"])
    assert _rules(frames.check(call, records, V4)) == ["F1"]  # P5-6: held, though right
    assert _rules(frames.check(call, records, V5)) == []


def test_v5_matches_a_written_move_as_a_whole_token() -> None:
    records = {"x1.t": ("explored_line", {"ledger": _book(2, [("Qxd5", 3), ("Rd8", 3),
                                                              ("Bxa8", 5), ("d5", 5)])})}  # fmt: skip
    call = _call("1.Qxd5 뒤 백이 3점 앞선다.", ["x1.t"])
    assert _rules(frames.check(call, records, V4)) == ["F1"]  # P5-7: read at "d5", ply 4
    assert _rules(frames.check(call, records, V5)) == []


def test_v5_reads_no_grade_in_gangje() -> None:
    j = {"id": "j", "kind": "judgement", "judgement": "j1.t", "grade": "blunder", "label": None}
    call = _call("이 수 뒤 백은 강제로 퀸을 내준다.", ["j"], [j])
    records = {"j1.t": ("judgement", {"grade": "blunder", "label": None, "move": {"san": "Qd2"}})}
    assert "F3" in _rules(frames.check(call, records, V4))  # P5-8: "강제" read as the label forced
    assert "F3" not in _rules(frames.check(call, records, V5))


def test_tier_0_needs_the_line_to_start_at_the_commented_ply() -> None:
    game = ["e2e4", "d7d5", "e4d5", "g8f6", "g1f3", "f6d5", "f1e2", "e7e6", "e1g1"]
    sans = harness.numbered_sans("1. e4 d5 2. exd5 Nf6 3. Nf3 Nxd5 4. Be2 e6 5. O-O *")
    record = {"start": {"from_root": game[:3]}, "end": {"from_root": game}}
    quiet = {p: 0 for p in range(1, 10)}
    assert tiers.followed_sentence(game, sans, 6, quiet, [("x1.t", record)]) is not None  # P5-4
    assert tiers.followed_sentence(game, sans, 6, quiet, [("x1.t", record)], strict=True) is None


def test_a_bracketed_square_stays_whatever_cites_its_name() -> None:
    args = {"items": [{"ply": 6, "sentences": [
        {"text": "약한 칸(c4)이 비었다 (j7).", "cites": ["c4.a", "j7.b"]}]}]}  # fmt: skip
    assert harness.strip_cited_handles(args)[0]["items"][0]["sentences"][0]["text"] == "약한 칸이 비었다."
    kept = harness.strip_cited_handles(args, keep_squares=True)[0]
    assert kept["items"][0]["sentences"][0]["text"] == "약한 칸(c4)이 비었다."  # P5-10


@pytest.fixture
def quiet(monkeypatch):
    async def no_problems(session, game_id, claims, log):
        return [], [], []

    monkeypatch.setattr(harness, "check_claims", no_problems)
    monkeypatch.setattr(frames, "refs_needed", lambda args: set())
    monkeypatch.setattr(frames, "check", lambda args, records, version=None: {
        "held": [], "uncheckable": [], "ambiguous": [], "search_numbers": 0, "version": "t"})  # fmt: skip


def test_rev_16_refuses_a_tool_tier_1_does_not_offer(tmp_path, quiet) -> None:
    explore = ("explore", {"game": "g", "ply": 6, "moves": ["e2e4"]})
    agent = _Model([_reply("FACTS"), _reply(calls=[_submit(3)]), _reply("ok"),
                    _reply(calls=[explore]), _reply(calls=[_batch(6, 8)])])  # fmt: skip
    reason, server, lines = _run(tmp_path, agent, LINES, revision=16)
    assert reason == "done" and "explore" not in [n for n, _ in server.calls]
    assert any(x["type"] == "tool_unsent" and x.get("tier") == 1 for x in lines)


def test_rev_16_rewrites_a_call_whose_items_are_a_json_string(tmp_path, quiet) -> None:
    items = [{"ply": p, "sentences": [{"text": f"수 {p} (j1)", "class": "sourced", "cites": ["j1.t"]}]}
             for p in (6, 8)]  # fmt: skip
    call = ("submit_commentary", {"game": "g", "agent": {"name": "t"}, "items": json.dumps(items)})
    agent = _Model([_reply("FACTS"), _reply(calls=[_submit(3)]), _reply("ok"), _reply(calls=[call])])
    _, server, _ = _run(tmp_path, agent, LINES, revision=16)
    sent = [a for n, a in server.calls if n == "submit_commentary"][1]
    assert [i["sentences"][0]["text"] for i in sent["items"]] == ["수 6", "수 8"]  # P5-9


def test_rev_16_tells_tier_1_the_fixed_moments_inside_its_range() -> None:
    accepted = {12: ["장면 12"], 57: ["장면 57"], 10: ["이미 받은 10"]}
    assert set(harness.story_plies(accepted, [10, 11, 14], False)) == set()  # P5-2: 12 left out
    assert set(harness.story_plies(accepted, [10, 11, 14], True)) == {12, 57}
    assert set(harness.story_plies(accepted, [33, 89], True)) == {10, 12, 57}


def test_revision_16_is_revision_15_with_rv1s_corrections() -> None:
    import inspect

    assert harness.VERSIONS[16] == harness.VERSIONS[15] and harness.FRAMES[16] == V5
    assert harness.REVIEWED == (16,) and 16 in harness.COMPLETE_CITES and 16 in harness.TIERED
    assert harness.TIER1_GUIDES[16] == harness.TIER1_GUIDES[15]
    assert "default=16" in inspect.getsource(rx_score.main)
    info = rx_run._harness_info(SimpleNamespace(arm="H", harness_revision=16, harness_guide=None))
    assert info["harness_reviewed"] is True
