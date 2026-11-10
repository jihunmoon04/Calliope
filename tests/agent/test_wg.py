"""WG-D: whole-game commentary in three tiers (harness rev. 12) — the tiers and batches from
`game_overview`, tier 1's batch conversation, tier 0's followed-line sentence, the judged sample,
and the score row's tier-1 fields."""

from __future__ import annotations

import json
from types import SimpleNamespace

import anyio
import pytest
from agent_helpers import GAME
from test_tb_harness import PASS, _Model, _reply

from tools.rx import frames as rx_frames
from tools.rx import harness, judge, report, tiers
from tools.rx import run as rx_run
from tools.rx import score as rx_score

# GAME: 1.e4 d5 2.exd5 Nf6 3.Nf3 Nxd5 4.Be2 e6 5.O-O Be7
UCIS = ["e2e4", "d7d5", "e4d5", "g8f6", "g1f3", "f6d5", "f1e2", "e7e6", "e1g1", "f8e7"]
SANS = ["1.e4", "1...d5", "2.exd5", "2...Nf6", "3.Nf3", "3...Nxd5", "4.Be2", "4...e6", "5.O-O",
        "5...Be7"]  # fmt: skip


def _lines(**marks) -> list[dict]:
    """Ten plies: `g6="inaccuracy"` grades ply 6, `l7="great"` labels ply 7, `x6=120` its loss."""

    out = []
    for ply in range(1, 11):
        line = {"ply": ply, "move": SANS[ply - 1], "grade": marks.get(f"g{ply}", "best"),
                "loss": marks.get(f"x{ply}", 0)}  # fmt: skip
        if f"l{ply}" in marks:
            line["label"] = marks[f"l{ply}"]
        out.append(line)
    return out


# -- §1–§3: the pure rules -------------------------------------------------------------------


def test_the_tiers_read_the_grade_and_the_label() -> None:
    lines = _lines(g3="blunder", g6="inaccuracy", g8="mistake", l7="great", l9="forced")
    got = tiers.tiers_of(lines, [3])
    assert got[3] == 2  # a fixed moment first
    assert [p for p, t in got.items() if t == 1] == [6, 7, 8]  # graded errors and "great"
    assert got[9] == 0 and got[1] == 0  # "forced" and quiet moves


def test_batches_hold_eight_plies_and_halve() -> None:
    plies = list(range(20, 0, -1))
    got = tiers.batches(plies)
    assert [len(b) for b in got] == [8, 8, 4] and got[0][0] == 1
    assert tiers.halves([1, 2, 3, 4, 5]) == [[1, 2, 3], [4, 5]] and tiers.halves([7]) == [[7]]


def test_the_sample_is_the_largest_losses_the_earlier_on_a_tie() -> None:
    lines = _lines(g2="inaccuracy", g4="mistake", g6="mistake", g8="inaccuracy",
                   x2=60, x4=200, x6=200, x8=90)  # fmt: skip
    got = tiers.sample(lines, tiers.tiers_of(lines, []))
    assert got == [4, 6, 8]  # 200, 200 (4 before 6), then 90; in ply order
    assert tiers.sample(lines, tiers.tiers_of(lines, [])) == got  # the same in every run


def test_a_followed_engine_line_gets_one_sentence_at_the_first_quiet_ply() -> None:
    tier_of = tiers.tiers_of(_lines(g3="blunder", g6="inaccuracy"), [3])
    played = {"pv": [{"uci": u} for u in ("e4d5", "g8f6", "g1f3", "f6d5")]}  # from ply 3
    got = tiers.followed_sentence(UCIS, SANS, 3, tier_of, [("s1.t", played)])
    assert got["ply"] == 4 and got["until_ply"] == 6 and got["source"] == "code"
    assert got["text"] == "앞서 본 수순대로 진행되었다 (3...Nxd5까지)."
    short = {"pv": [{"uci": u} for u in ("e4d5", "g8f6", "b1c3")]}  # left the game at ply 5
    assert tiers.followed_sentence(UCIS, SANS, 3, tier_of, [("s1.t", short)]) is None


def test_an_explored_line_must_start_on_the_games_own_moves() -> None:
    tier_of = tiers.tiers_of(_lines(), [2])
    on = {"start": {"from_root": UCIS[:2]}, "end": {"from_root": UCIS[:6]}}
    assert tiers.followed_sentence(UCIS, SANS, 2, tier_of, [("x1.t", on)])["until_ply"] == 6
    off = {"start": {"from_root": ["d2d4"]}, "end": {"from_root": ["d2d4", "d7d5", "c2c4"]}}
    assert tiers.followed_sentence(UCIS, SANS, 2, tier_of, [("x2.t", off)]) is None


def test_a_batch_submission_counts_each_accepted_item() -> None:
    game = harness.Game(GAME)
    args = {"game": "g", "items": [
        {"ply": 6, "sentences": [{"text": "A", "cites": ["j1.t", "s1.t"]}]},
        {"ply": 8, "sentences": [{"text": "B", "cites": []}]}]}  # fmt: skip
    answer = json.dumps({"items": [{"index": 0, "outcome": "accepted"},
                                   {"index": 1, "outcome": "refused", "violations": []}]})  # fmt: skip
    assert harness.accepted_subjects(args, answer, game, None) == [(6, ["A"], ["j1.t", "s1.t"])]
    single = {"game": "g", "ply": 3, "sentences": [{"text": "C", "cites": ["c1.t"]}]}
    assert harness.accepted_subjects(single, json.dumps({"accepted": True}), game, 3) == [
        (3, ["C"], ["c1.t"])]  # fmt: skip


def test_the_gate_lets_a_batch_through_and_nothing_else() -> None:
    gate = harness.Gate(None, harness.Game(GAME), None, "g")
    gate.phase, gate.current_ply, gate.current_plies = "submit", None, [6, 8]
    ok, _ = gate.allows({"game": "g", "items": [{"ply": 6}, {"ply": 8}]})
    assert ok
    assert not gate.allows({"game": "g", "items": [{"ply": 6}, {"ply": 7}]})[0]


# -- §2–§4: a whole run on the stubs ---------------------------------------------------------


@pytest.fixture(autouse=True)
def _quiet_checks(monkeypatch):
    async def no_problems(session, game_id, claims, log):
        return [], [], []

    monkeypatch.setattr(harness, "check_claims", no_problems)
    monkeypatch.setattr(rx_frames, "refs_needed", lambda args: set())
    monkeypatch.setattr(rx_frames, "check", lambda args, records, version=None: {
        "held": [], "uncheckable": [], "ambiguous": [], "search_numbers": 0, "version": "t"})  # fmt: skip


class _Server:
    """`game_overview` from `lines`, `ply` a digest, `detail` a played line, submissions accepted."""

    def __init__(self, lines):
        self.lines = lines
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "game_overview":
            text = json.dumps({"lines": self.lines})
        elif name == "ply":
            text = json.dumps({"digest_of": arguments["ply"]})
        elif name == "detail":
            text = json.dumps({"kind": "search_line", "item": {
                "pv": [{"uci": u} for u in ("e4d5", "g8f6", "g1f3", "f6d5")]}})  # fmt: skip
        elif name == "submit_commentary" and "items" in arguments:
            text = json.dumps({"items": [{"index": i, "outcome": "accepted"}
                                         for i in range(len(arguments["items"]))]})  # fmt: skip
        else:
            text = json.dumps({"accepted": True})
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], isError=False)


def _submit(ply, text="해설", cites=()):
    return ("submit_commentary", {"game": "g", "ply": ply, "agent": {"name": "t"},
                                  "sentences": [{"text": text, "class": "interpretation",
                                                 "cites": list(cites)}]})  # fmt: skip


def _batch(*plies):
    return ("submit_commentary", {"game": "g", "agent": {"name": "t"}, "items": [
        {"ply": p, "sentences": [{"text": f"수 {p}", "class": "interpretation", "cites": []}]}
        for p in plies]})  # fmt: skip


TOOLS = [{"type": "function", "function": {"name": n, "parameters": {}}}
         for n in ("ply", "explore", "detail", "submit_commentary")]  # fmt: skip


def _run(tmp_path, agent, lines, revision=12):
    spec = rx_run.RunSpec(arm="H", set_name="validation", game="g", pgn=GAME, moments=[3],
                          base=tmp_path, records=tmp_path, work=tmp_path, game_id="g",
                          harness_revision=revision)  # fmt: skip
    log = rx_run.AgentLog(tmp_path / "RUN" / "agent.jsonl", "RUN")
    server = _Server(lines)
    messages = [{"role": "system", "content": "SYSTEM"}, {"role": "user", "content": "TASK"}]
    totals = {"turns": 0, "tool_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}
    reason = anyio.run(harness.harness_loop, server, agent, messages, TOOLS, spec, log, totals,
                       rx_run._loop, _Model([PASS, PASS]), [(3, "2.exd5")])  # fmt: skip
    log.close()
    out = [
        json.loads(x) for x in (tmp_path / "RUN" / "agent.jsonl").read_text("utf-8").splitlines()
    ]
    return reason, server, out


LINES = _lines(g3="blunder", g6="inaccuracy", g8="mistake", x6=80, x8=150)


def test_a_whole_run_comments_tier_1_in_one_batch_and_writes_tier_0(tmp_path) -> None:
    agent = _Model([_reply("FACTS"), _reply(calls=[_submit(3, "장면", ["s1.t"])]), _reply("ok"),
                    _reply(calls=[_batch(6, 8)]), _reply("ok")])  # fmt: skip
    reason, server, lines = _run(tmp_path, agent, LINES)
    assert reason == "done"
    batch = next(x for x in lines if x["type"] == "batch_start")
    assert batch["plies"] == [6, 8] and batch["tier"] == 1
    first = agent.requests[3][0]
    assert first[0]["content"].startswith("# Calliope 해설 작성 — 수 해설")  # tier 1's guide
    text = first[1]["content"]
    assert "3...Nxd5 (ply 6)" in text and '"digest_of": 8' in text and "장면" in text  # the story
    assert [c[0] for c in server.calls].count("ply") == 2  # the digests, fetched by the harness
    end = next(x for x in lines if x["type"] == "batch_end")
    assert end["accepted"] == [6, 8] and end["reason"] == "done"
    note = next(x for x in lines if x["type"] == "tier0")
    assert note["ply"] == 4 and note["until_ply"] == 6
    summary = next(x for x in lines if x["type"] == "tiers")
    assert summary["coverage"] == {"plies": 10, "tier2": 1, "tier1": 2, "tier1_asked": 2,
                                   "tier0_sentences": 1}  # fmt: skip
    assert summary["sample"] == [6, 8] and summary["ends"] == {"6": "submitted", "8": "submitted"}
    assert set(summary["totals"]) == {"tier2", "tier1", "tier0"}
    plan = next(x for x in lines if x["type"] == "tiers_plan")
    assert plan["counts"] == {"0": 7, "1": 2, "2": 1}
    # the harness's own calls are logged, so the run checker pairs them with the server's
    own = [x["tool"] for x in lines if x["type"] == "harness_call"]
    assert own.count("ply") == 2 and "game_overview" in own and "detail" in own


def test_tier_1_offers_detail_and_submit_only(tmp_path) -> None:
    agent = _Model([_reply("FACTS"), _reply(calls=[_submit(3)]), _reply("ok"),
                    _reply(calls=[_batch(6, 8)]), _reply("ok")])  # fmt: skip

    offered = []
    complete = agent.complete

    def spy(messages, tools, tool_choice=None):
        offered.append(sorted(t["function"]["name"] for t in tools))
        return complete(messages, tools, tool_choice)

    agent.complete = spy
    _run(tmp_path, agent, LINES)
    assert offered[3] == ["detail", "submit_commentary"]


def test_a_batch_without_a_submission_is_asked_twice_then_logged(tmp_path) -> None:
    agent = _Model([_reply("FACTS"), _reply(calls=[_submit(3)]), _reply("ok"),
                    _reply("생각 중"), _reply("아직"), _reply("끝")])  # fmt: skip
    reason, _, lines = _run(tmp_path, agent, LINES)
    assert reason == "done"
    end = next(x for x in lines if x["type"] == "batch_end")
    assert end["accepted"] == [] and end["reason"] == "unsubmitted"
    summary = next(x for x in lines if x["type"] == "tiers")
    assert summary["ends"] == {"6": "unsubmitted", "8": "unsubmitted"}
    assert summary["coverage"]["tier1"] == 0


def test_a_batch_over_its_first_limit_is_halved(tmp_path) -> None:
    agent = _Model([_reply("FACTS"), _reply(calls=[_submit(3)]), _reply("ok"),
                    _reply(calls=[_batch(6)]), _reply("ok"), _reply(calls=[_batch(8)]), _reply("ok")],
                   sizes=(1_000, 1_000, 1_000, 70_000, 1_000))  # fmt: skip
    reason, _, lines = _run(tmp_path, agent, LINES)
    assert reason == "done"
    assert next(x for x in lines if x["type"] == "batch_split")["plies"] == [6, 8]
    assert [x["plies"] for x in lines if x["type"] == "batch_start"] == [[6], [8]]


def test_revision_11_has_no_tiers(tmp_path) -> None:
    agent = _Model([_reply("FACTS"), _reply(calls=[_submit(3)]), _reply("ok")])
    reason, server, lines = _run(tmp_path, agent, LINES, revision=11)
    assert reason == "done" and not any(x["type"].startswith("tier") for x in lines)
    assert "game_overview" not in [c[0] for c in server.calls]


# -- §5: the sample judged, the row's fields --------------------------------------------------


def test_the_bundle_reads_the_runs_sample(tmp_path) -> None:
    run = tmp_path / "R"
    run.mkdir()
    (run / "agent.jsonl").write_text("\n".join(json.dumps(x) for x in (
        {"type": "start", "moments": [3]}, {"type": "tiers_plan", "sample": [6, 8]})), "utf-8")  # fmt: skip
    assert judge.tier1_sample(run) == [6, 8]
    (run / "agent.jsonl").write_text(json.dumps({"type": "start", "moments": [3]}), "utf-8")
    assert judge.tier1_sample(run) == []  # before rev. 12


def test_the_frame_counts_are_kept_apart_by_tier(tmp_path) -> None:
    run = tmp_path / "R"
    run.mkdir()
    rows = [{"type": "frames", "ply": 3, "state": "passed", "uncheckable": [{"rule": "F1"}]},
            {"type": "frames", "ply": None, "plies": [6, 8], "tier": 1, "state": "held"},
            {"type": "frames", "ply": None, "plies": [6, 8], "tier": 1, "state": "passed",
             "uncheckable": [{"rule": "F5"}]}]  # fmt: skip
    (run / "agent.jsonl").write_text("\n".join(json.dumps(x) for x in rows), "utf-8")
    two, one = report.frame_counts(run), report.frame_counts(run, 1)
    assert two["holds"] == 0 and two["uncheckable"] == {"F1": 1}
    assert one["holds"] == 1 and one["uncheckable"] == {"F5": 1}


def test_revision_12_is_revision_11_with_the_tiers() -> None:
    import inspect

    assert harness.VERSIONS[12][1:] == harness.VERSIONS[11][1:] and 12 in harness.TIERED
    assert harness.FRAMES[11] == rx_frames.FRAMES_V3 and harness.FRAMES[12] == rx_frames.FRAMES_V4
    v5, v6 = harness.ALL_MESSAGES[11], harness.ALL_MESSAGES[12]
    assert all(v6[k] == v5[k] for k in v5)  # rev. 11's messages unchanged
    assert {"tier1_task", "tier1_story", "tier1_digest", "tier1_gate", "tier1_unsubmitted"} <= set(
        v6
    )
    guide = (harness.PROMPTS / f"{harness.TIER1_GUIDE}.md").read_text(encoding="utf-8")
    assert "standing" in guide and "1~3문장" in guide and "explore" in guide
    assert "default=1" in inspect.getsource(rx_score.main)  # rev. 12 or later
    info = rx_run._harness_info(SimpleNamespace(arm="H", harness_revision=12, harness_guide=None))
    assert info["harness_tier1"] == "harness_tier1_v1"
