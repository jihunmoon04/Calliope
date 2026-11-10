"""The review of 2026-11-10 (four slices) and its corrections: frame check v4 for rev. 12 without
v3's false holds, a batch's single-subject submission counted, tier 0 only for a line followed by
its own moves, the `tiers` line on every end, the checker's pairing of the frame check's reads and
of schema-refused calls, the score row's tier-2 fields, the bundle's reference check."""

from __future__ import annotations

import json

import pytest
from test_frames_v3 import RECORDS, _book, _call
from test_tb_harness import _Model
from test_wg import LINES, SANS, UCIS, _reply, _run, _submit

from tools.rx import check, frames, harness, judge, tiers
from tools.rx import run as rx_run
from tools.rx import score as rx_score

V3, V4 = frames.FRAMES_V3, frames.FRAMES_V4
P2 = {"id": "p2", "kind": "material", "line": "x5.t", "from": 0, "to": 4, "side": "white",
      "balance": -5}  # fmt: skip
P3 = {"id": "p3", "kind": "material", "line": "x5.t", "from": 0, "to": 5, "side": "white",
      "balance": -2}  # fmt: skip


def _rules(out):
    return sorted(h["rule"] for h in out["held"])


# -- slice 2: frame check v4 -----------------------------------------------------------------


@pytest.mark.parametrize("text, cites, props", [
    ("이 라인에서 흑은 3점을 더 얻어 앞선다.", ["x23.t"], []),  # a gain, a standing word
    ("이 라인에서 흑은 3수 만에 크게 앞선다.", ["x23.t"], []),  # a count of plies
    ("백은 5점을 잃었다가 비숍을 되잡아 2점 손해로 줄이지만, 흑이 앞선다.", ["p2", "p3"], [P2, P3]),
    ("17.Kxf1 이후 라인 끝까지 물질 변화가 없다.", ["m"],
     [{"id": "m", "kind": "material", "line": "x5.t", "from": 5, "to": 8, "side": "white",
       "balance": 0}]),  # the proposition's own segment
    ("23...Rxe5로 우위가 흑 쪽으로 넘어갔다가 24.dxe5로 다시 백 쪽으로 넘어간다.", ["x18.t"], []),
])  # fmt: skip
def test_v4_holds_none_of_v3s_false_holds(text, cites, props) -> None:
    assert frames.check(_call(text, cites, props), RECORDS, V3)["held"]  # v3 as it was recorded
    assert frames.check(_call(text, cites, props), RECORDS, V4)["held"] == []


def test_v4_takes_no_signed_standing_for_the_change() -> None:
    records = dict(RECORDS, **{"x9.t": ("explored_line", {"ledger": _book(-2, [("1.a", -2),
                                                                                ("1...b", -1)])})})  # fmt: skip
    q = {"id": "q", "kind": "material", "line": "x9.t", "from": 0, "to": 2, "side": "white",
         "balance": 1}  # fmt: skip
    call = _call("이 수순 뒤 물질은 -1이다.", ["q"], [q])
    assert _rules(frames.check(call, records, V3)) == ["F1"]
    assert frames.check(call, records, V4)["held"] == []


def test_v4_still_holds_what_v3_held_rightly() -> None:
    two = _call("백은 룩을 잃어 물질 차이가 -5가 되었다가 비숍을 되잡고 -2로 남습니다.",
                ["p2", "p3"], [P2, P3])  # fmt: skip
    assert _rules(frames.check(two, RECORDS, V4)) == ["F1", "F1"]  # 8856bf87 #2
    out = frames.check(_call("이 라인이 끝난 뒤 standing은 흑 쪽으로 넘어가 흑이 앞섭니다.", ["x23.t"]),
                       RECORDS, V4)  # fmt: skip
    assert _rules(out) == ["F4", "F6"]  # a869f4f9 #4
    assert _rules(frames.check(_call("16...Bxf1 뒤 이 라인의 백 물질은 -5입니다.", ["x5.t"]),
                               RECORDS, V4)) == ["F1"]  # fmt: skip
    assert _rules(frames.check(_call("백이 16...Bxf1에 룩을 잃고 17.Kxf1로 되잡아도 물질 변화가 없다.",
                                     ["x5.t"]), RECORDS, V4)) == ["F5"]  # fmt: skip
    m = {"id": "m", "kind": "material", "line": "x5.t", "from": 0, "to": 5, "side": "white",
         "balance": -2}  # fmt: skip
    seg = frames.check(_call("이 라인 5수 동안 물질 변화가 없다.", ["m"], [m]), RECORDS, V4)
    assert _rules(seg) == ["F5"]  # its own segment changed: +1 to -1


def test_v4_replies_name_no_ledger_field() -> None:
    out = frames.check(_call("이 라인의 백 물질 차이는 -5입니다.", ["p2"], [P2]), RECORDS, V4)
    assert out["held"] and all("standing" not in h["reply"] for h in out["held"])
    v3 = frames.check(_call("이 라인의 백 물질 차이는 -5입니다.", ["p2"], [P2]), RECORDS, V3)
    assert any("standing" in h["reply"] for h in v3["held"])  # rev. 11 as it ran


def test_an_unknown_frame_check_is_refused() -> None:
    with pytest.raises(ValueError):
        frames.check(_call("x", []), RECORDS, "harness_frames_v9")


def test_revision_12_runs_v4_and_revision_11_v3() -> None:
    assert harness.FRAMES[11] == V3 and harness.FRAMES[12] == V4


# -- slice 3: tier 1 and tier 0 --------------------------------------------------------------


@pytest.fixture
def quiet(monkeypatch):
    """The whole-run stubs' checks, for the tests that run the harness (not the frame tests)."""

    async def no_problems(session, game_id, claims, log):
        return [], [], []

    monkeypatch.setattr(harness, "check_claims", no_problems)
    monkeypatch.setattr(frames, "refs_needed", lambda args: set())
    monkeypatch.setattr(frames, "check", lambda args, records, version=None: {
        "held": [], "uncheckable": [], "ambiguous": [], "search_numbers": 0, "version": "t"})  # fmt: skip


def test_a_single_subject_in_a_batch_counts_by_its_ply() -> None:
    game = harness.Game("1. e4 d5 2. exd5 Nf6 3. Nf3 Nxd5 4. Be2 e6 5. O-O Be7 *")
    single = {"game": "g", "ply": 6, "sentences": [{"text": "A", "cites": ["j1.t"]}]}
    assert harness.accepted_subjects(single, json.dumps({"accepted": True}), game, None) == [
        (6, ["A"], ["j1.t"])]  # fmt: skip


def test_a_line_followed_by_none_of_its_own_moves_writes_nothing() -> None:
    tier_of = {p: 0 for p in range(1, 11)} | {2: 2}
    off = {"start": {"from_root": UCIS[:6]}, "end": {"from_root": UCIS[:6] + ["b1c3"]}}
    assert tiers.followed_sentence(UCIS, SANS, 2, tier_of, [("x1.t", off)]) is None
    later = {"start": {"from_root": UCIS[:4]}, "end": {"from_root": UCIS[:8]}}  # starts at ply 5
    assert tiers.followed_sentence(UCIS, SANS, 2, tier_of, [("x2.t", later)]) is None


def test_a_batch_that_runs_out_of_turns_moves_on(tmp_path, quiet) -> None:
    detail = ("detail", {"game": "g", "ref": "c1.t"})
    agent = _Model([_reply("FACTS"), _reply(calls=[_submit(3)]), _reply("ok")]
                   + [_reply(calls=[detail])] * harness.TIER1_TURNS)  # fmt: skip
    reason, _, lines = _run(tmp_path, agent, LINES)
    assert reason == "done"
    end = next(x for x in lines if x["type"] == "batch_end")
    assert end["reason"] == "batch_turns" and end["accepted"] == []
    assert next(x for x in lines if x["type"] == "tiers")["ends"] == {
        "6": "batch_turns", "8": "batch_turns"}  # fmt: skip


def test_the_tiers_line_is_written_when_the_run_ends_inside_tier_1(
    tmp_path, monkeypatch, quiet
) -> None:
    agent = _Model([_reply("FACTS"), _reply(calls=[_submit(3)]), _reply("ok")])
    spec_cost = 0.0035  # tier 2 spends 0.004: tier 1's first batch is over the bound
    original = rx_run.RunSpec

    def bounded(*args, **kwargs):
        spec = original(*args, **kwargs)
        spec.bounds.cost = spec_cost
        return spec

    monkeypatch.setattr(rx_run, "RunSpec", bounded)
    reason, _, lines = _run(tmp_path, agent, LINES)
    assert reason == "cost"
    summary = next(x for x in lines if x["type"] == "tiers")
    assert summary["reason"] == "cost" and summary["ends"] == {"6": "not_run", "8": "not_run"}
    assert summary["coverage"]["tier1"] == 0


def test_tier_1_has_its_own_refusal_message() -> None:
    assert "tier1_refused" in harness.ALL_MESSAGES[12]
    assert "facts" not in harness.ALL_MESSAGES[12]["tier1_refused"]
    guide = (harness.PROMPTS / f"{harness.TIER1_GUIDE}.md").read_text(encoding="utf-8")
    assert '"agent"' in guide  # the submission's required field
    assert "definitions" not in guide and "judge_move" not in guide


# -- the checker's pairing -------------------------------------------------------------------


def test_the_frame_checks_reads_pair_before_the_call_that_made_them() -> None:
    agent = [{"type": "response", "message": {"tool_calls": [
        {"id": "c1", "function": {"name": "submit_commentary"}}]}},
        {"type": "harness_call", "tool": "detail", "ref": "x1.t", "before": "c1"},
        {"type": "harness_call", "tool": "ply"}]  # fmt: skip
    assert [n for _, n, _ in check.asked_calls(agent)] == ["detail", "submit_commentary", "ply"]


def test_a_schema_refused_call_is_logged_unsent() -> None:
    text = ("Error executing tool submit_commentary: 1 validation error for "
            "submit_commentaryArguments agent Field required")  # fmt: skip
    assert rx_run.SCHEMA_REFUSED.match(text)
    assert not rx_run.SCHEMA_REFUSED.match('{"accepted": false}')


# -- slice 4: the score row and the bundle ---------------------------------------------------


def _write(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_a_rev_12_rows_totals_and_largest_request_are_tier_2s(tmp_path) -> None:
    run = tmp_path / "R"
    run.mkdir()
    usage = {"input_tokens": 0}
    _write(run / "agent.jsonl", [
        {"seq": 1, "type": "start", "game": "g"},
        {"seq": 2, "type": "response", "usage": dict(usage, input_tokens=50_000)},
        {"seq": 3, "type": "tiers_plan", "sample": [6]},
        {"seq": 4, "type": "response", "usage": dict(usage, input_tokens=70_000)},
        {"seq": 5, "type": "tiers", "totals": {"tier2": {}, "tier1": {"cost": 0.03, "turns": 2},
                                                "tier0": {"cost": 0.0, "turns": 0}}},
        {"seq": 6, "type": "end", "reason": "done", "totals": {"cost": 0.13, "turns": 9,
                                                                 "judge_cost": 0.01}}])  # fmt: skip
    got = rx_score.run_numbers(run)
    assert got["largest_request"] == 50_000
    assert got["totals"] == {"cost": 0.1, "turns": 7, "judge_cost": 0.01}
    assert got["totals_whole_run"]["cost"] == 0.13


def test_the_bundle_checks_its_references_before_making_a_part(tmp_path) -> None:
    run = tmp_path / "R"
    run.mkdir()
    _write(run / "agent.jsonl", [
        {"type": "start", "set": "validation", "game": "184800218248", "moments": [12], "arm": "H"},
        {"type": "tiers_plan", "sample": [99]}])  # fmt: skip
    sub = [{"game_ply": p, "outcome": "accepted", "submitted": {"sentences": [{"text": "x"}]}}
           for p in (12, 99)]  # fmt: skip
    _write(run / "tools.jsonl", [{"seq": 1, "type": "submission", "call_id": 1, "subjects": sub}])
    with pytest.raises(ValueError, match="184800218248-99"):
        judge.bundle([run], root=tmp_path / "judging", keys=tmp_path / "keys")
    assert not (tmp_path / "judging").exists() and not (tmp_path / "keys").exists()


def test_the_score_row_carries_tier_1(tmp_path, monkeypatch) -> None:
    from test_tb_score import GOOD

    import tools.rx.judge as rx_judge

    monkeypatch.setattr(rx_score, "PENDING", tmp_path / "score")
    monkeypatch.setattr(rx_score, "RX_DATA", tmp_path)
    (tmp_path / "score").mkdir()
    (tmp_path / "score" / "t.json").write_text(json.dumps({
        "name": "t", "runs": ["R1"], "seconds": {"R1": 5}, "judging": "j", "parts": [],
        "variant": {"harness_revision": 12, "tools": None, "model": "m",
                    "reasoning_effort": None, "harness_guide": None}}))  # fmt: skip
    monkeypatch.setattr(rx_judge, "checked_judgings", lambda j, root: {1: {}})
    monkeypatch.setattr(
        rx_judge, "join", lambda j, docs: [{"run_id": "R1", "ply": 3, "judged": GOOD}]
    )
    one = {"wrong": 1, "search_only": 0, "sentences": 4, "decisive": None, "score": 3.0}
    two = {"wrong": 0, "search_only": 0, "sentences": 2, "decisive": 1.0, "score": 4.0}
    monkeypatch.setattr(rx_score, "moment_rows", lambda runs, judged, tier=2: (
        ([two], {"submitted": 1, "asked": 1}) if tier == 2 else ([one], {"submitted": 1, "asked": 1})))  # fmt: skip
    monkeypatch.setattr(rx_score, "run_numbers", lambda r: {
        "run": r.name, "largest_request": 1, "totals": {"cost": 0.1},
        "totals_whole_run": {"cost": 0.13}, "model": "m", "harness": "harness_v6"})  # fmt: skip
    card = tmp_path / "card.jsonl"
    assert rx_score.main(["finish", "--name", "t", "--scorecard", str(card)]) == 0
    row = json.loads(card.read_text())
    assert row["cost"] == 0.1 and row["cost_whole_run"] == 0.13  # tier 2's, and the whole run's
    assert row["rates"]["M1b"] == 0.0 and row["rates_tier1"]["M1b"] == 25.0
    assert row["completion_tier1"] == {"submitted": 1, "asked": 1}
    assert row["judging"]["items_tier1"] == 1
