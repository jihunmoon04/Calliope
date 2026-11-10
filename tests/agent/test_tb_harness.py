"""TB-D §3: harness rev. 9 — the tools it serves, `view` hidden, the answer cap, a conversation per
moment with the story so far, the guard (80k / 95k), one compaction a moment, and moment ends apart
from the run's."""

from __future__ import annotations

import json
from types import SimpleNamespace

import anyio
import pytest
from agent_helpers import GAME

from tools.rx import frames as rx_frames
from tools.rx import guard as rx_guard
from tools.rx import harness
from tools.rx import model as rx_model
from tools.rx import run as rx_run


def _reply(content=None, calls=(), stop=None):
    message = {"content": content}
    if calls:
        message["tool_calls"] = [{"id": f"c{i}", "type": "function",
                                  "function": {"name": n, "arguments": json.dumps(a)}}
                                 for i, (n, a) in enumerate(calls)]  # fmt: skip
    return rx_model.Reply(message=message, usage={"input_tokens": 10, "output_tokens": 5,
                                                  "cost": 0.001}, body_fields=[], stop=stop)  # fmt: skip


class _Model:
    """Answers from a list; `sizes` (one a request, then the last repeated) is what `count` says."""

    def __init__(self, replies, sizes=(1_000,)):
        self.replies = list(replies)
        self.sizes = list(sizes)
        self.requests = []
        self.counted = 0

    def count(self, messages, tools, tool_choice=None):
        size = self.sizes[min(self.counted, len(self.sizes) - 1)]
        self.counted += 1
        return size

    def complete(self, messages, tools, tool_choice=None):
        self.requests.append((json.loads(json.dumps(messages)), tool_choice))
        return self.replies.pop(0)


class _Session:
    def __init__(self, answers=None):
        self.calls = []
        self.answers = answers or {}

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        text = self.answers.get(name, json.dumps({"accepted": True}) if name == "submit_commentary"
                                else "{}")  # fmt: skip
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], isError=False)


@pytest.fixture(autouse=True)
def _checks_pass(monkeypatch):
    async def no_problems(session, game_id, claims, log):
        return [], [], []

    monkeypatch.setattr(harness, "check_claims", no_problems)
    monkeypatch.setattr(rx_frames, "refs_needed", lambda args: set())
    monkeypatch.setattr(
        rx_frames,
        "check",
        lambda args, records: {
            "held": [],
            "uncheckable": [],
            "ambiguous": [],
            "search_numbers": 0,
            "version": "t",
        },
    )


def _submit(ply, text="해설 문장"):
    return ("submit_commentary", {"game": "g", "ply": ply, "agent": {"name": "t"},
                                  "sentences": [{"text": text, "class": "interpretation",
                                                 "cites": []}]})  # fmt: skip


PASS = _reply(json.dumps({"pass": True, "problems": []}))


def _run(tmp_path, agent, judge, moments=((3, "2.exd5"), (5, "3.c4")), session=None, cost=None):
    spec = rx_run.RunSpec(arm="H", set_name="validation", game="g", pgn=GAME,
                          moments=[m for m, _ in moments], base=tmp_path, records=tmp_path,
                          work=tmp_path, game_id="g", harness_revision=9)  # fmt: skip
    spec.bounds.cost = cost
    log = rx_run.AgentLog(tmp_path / "RUN" / "agent.jsonl", "RUN")
    session = session or _Session()
    messages = [{"role": "system", "content": "SYSTEM"}, {"role": "user", "content": "TASK"}]
    totals = {"turns": 0, "tool_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}
    reason = anyio.run(harness.harness_loop, session, agent, messages, [], spec, log, totals,
                       rx_run._loop, judge, list(moments))  # fmt: skip
    log.close()
    lines = [
        json.loads(x) for x in (tmp_path / "RUN" / "agent.jsonl").read_text("utf-8").splitlines()
    ]
    return reason, session, lines, messages


def test_the_harness_serves_ten_tools_without_view():
    def tool(name, props):
        return {"type": "function", "function": {"name": name, "description": "",
                                                 "parameters": {"type": "object",
                                                                "properties": props}}}  # fmt: skip

    listed = [
        tool("explore", {"view": {}, "moves": {}}),
        tool("show_game", {}),
        tool("definitions", {}),
        tool("open_game", {}),
        tool("ply", {"view": {}}),
    ]
    out = harness.harness_tools(listed)
    assert [t["function"]["name"] for t in out] == ["explore", "definitions", "ply"]
    assert out[0]["function"]["parameters"]["properties"] == {"moves": {}}
    assert (
        "view" in listed[0]["function"]["parameters"]["properties"]
    )  # the server's list unchanged
    assert len(harness.HARNESS_TOOLS) == 10


def test_the_gate_drops_view_and_refuses_an_answer_over_the_cap():
    big = "가" * 9_000  # 27,000 bytes
    session = _Session({"detail": big, "facts": "small"})
    log = []
    gate = harness.Gate(session, harness.Game(GAME), SimpleNamespace(write=log.append), "g")
    gate.messages = harness.ALL_MESSAGES[9]
    gate.hide_full, gate.cap = True, harness.ANSWER_CAP
    small = anyio.run(gate.call_tool, "facts", {"game": "g", "view": "full"})
    assert session.calls[-1] == ("facts", {"game": "g"}) and not small.isError
    assert any(x["type"] == "view_dropped" for x in log)
    refused = anyio.run(gate.call_tool, "detail", {"game": "g", "ref": "x1"})
    assert refused.isError and "27000바이트" in refused.content[0].text
    assert "from_root" in refused.content[0].text
    assert any(x["type"] == "tool_refused" and x["bytes"] == 27_000 for x in log)


def test_the_guard_compacts_at_80k_and_never_sends_above_95k():
    log = []
    guard = rx_guard.Guard(SimpleNamespace(write=log.append))
    model = _Model([], sizes=[50_000, 81_000, 96_000, 96_000])
    assert guard.check(model, [], []) is None
    assert guard.check(model, [], []) == "compact"
    assert guard.check(model, [], []) == "compact"  # over 95k before the restart
    guard.restarted = True
    assert guard.check(model, [], []) == "moment_budget"
    assert [x["counted_tokens"] for x in log] == [50_000, 81_000, 96_000, 96_000]


def test_openrouters_estimate_has_a_lower_limit():
    guard = rx_guard.Guard(SimpleNamespace(write=lambda x: None))
    plain = SimpleNamespace(complete=None)  # no `count`: estimated
    size, how = guard.size(plain, [{"role": "user", "content": "x" * 200_000}], [])
    assert how == "estimated" and size > rx_guard.ESTIMATED_LIMIT
    assert guard.check(plain, [{"role": "user", "content": "x" * 175_000}], []) == "compact"


def test_each_moment_starts_a_new_conversation_with_the_story(tmp_path):
    agent = _Model([_reply("FACTS 1"), _reply(calls=[_submit(3, "첫 장면 해설")]), _reply("ok"),
                    _reply("FACTS 2"), _reply(calls=[_submit(5)]), _reply("ok")])  # fmt: skip
    reason, _, lines, _ = _run(tmp_path, agent, _Model([PASS, PASS]))
    assert reason == "done"
    first_of_second = agent.requests[3][0]
    text = json.dumps(first_of_second, ensure_ascii=False)
    assert "FACTS 1" not in text  # the first moment's conversation is gone
    assert "첫 장면 해설" in text and "[지금까지의 해설]" in text  # the story carries its prose
    assert first_of_second[0] == {"role": "system", "content": "SYSTEM"}
    starts = [x for x in lines if x["type"] == "moment_start"]
    assert [x["ply"] for x in starts] == [3, 5]
    ends = [x["reason"] for x in lines if x.get("stage") == "moment_end"]
    assert ends == ["submitted", "submitted"]


def test_a_compaction_restarts_the_moment_with_its_notes_once(tmp_path):
    # facts at 85k: compaction (notes 100 tokens), the restart, then the moment goes on
    agent = _Model([_reply("NOTES: e4 x1"), _reply("FACTS"), _reply(calls=[_submit(3)]),
                    _reply("ok")], sizes=[85_000, 85_000, 100, 1_000])  # fmt: skip
    reason, _, lines, _ = _run(tmp_path, agent, _Model([PASS]), moments=((3, "2.exd5"),))
    assert reason == "done"
    compact_request, choice = agent.requests[0]
    assert choice == "none" and "[대화 정리]" in compact_request[-1]["content"]
    restart = next(x for x in lines if x["type"] == "restart")
    text = json.dumps(restart["messages"], ensure_ascii=False)
    assert "NOTES: e4 x1" in text and "[2.exd5 — 사실과 결정적 원인]" in text
    assert [x["reason"] for x in lines if x.get("stage") == "moment_end"] == ["submitted"]


def test_a_budget_end_moves_on_to_the_next_moment(tmp_path):
    # moment 1: over 95k, compaction, still over after the restart: moment_budget; moment 2 runs
    agent = _Model([_reply("NOTES"), _reply("FACTS 2"), _reply(calls=[_submit(5)]),
                    _reply("ok")],
                   sizes=[96_000, 90_000, 100, 96_000, 1_000])  # fmt: skip
    reason, session, lines, _ = _run(tmp_path, agent, _Model([PASS]))
    assert reason == "done"
    ends = [(x["ply"], x["reason"]) for x in lines if x.get("stage") == "moment_end"]
    assert ends == [(3, "moment_budget"), (5, "submitted")]
    assert [a["ply"] for n, a in session.calls if n == "submit_commentary"] == [5]


def test_a_budget_end_in_submit_keeps_the_passed_facts(tmp_path):
    agent = _Model([_reply("PASSED FACTS"), _reply("NOTES"), _reply(calls=[_submit(3)]),
                    _reply("ok")], sizes=[1_000, 85_000, 85_000, 100, 1_000])  # fmt: skip
    reason, _, lines, _ = _run(tmp_path, agent, _Model([PASS]), moments=((3, "2.exd5"),))
    assert reason == "done"
    restart = next(x for x in lines if x["type"] == "restart")
    text = json.dumps(restart["messages"], ensure_ascii=False)
    assert "[판정을 통과한 사실 답]" in text and "PASSED FACTS" in text
    assert "[2.exd5 — 제출]" in text  # the current stage's message, as sent


def test_a_run_bound_inside_a_moment_ends_the_run(tmp_path):
    agent = _Model([_reply("FACTS"), _reply("more")])
    reason, _, lines, _ = _run(tmp_path, agent, _Model([PASS]), cost=0.0005)
    assert reason == "cost"
    assert not [x for x in lines if x.get("stage") == "moment_end"]


def test_two_cuts_end_the_moment_not_the_run(tmp_path):
    agent = _Model([_reply("cut", stop="max_tokens"), _reply("cut", stop="max_tokens"),
                    _reply("FACTS 2"), _reply(calls=[_submit(5)]), _reply("ok")])  # fmt: skip
    reason, _, lines, _ = _run(tmp_path, agent, _Model([PASS]))
    assert reason == "done"
    assert [(x["ply"], x["reason"]) for x in lines if x.get("stage") == "moment_end"] == [
        (3, "moment_cut"),
        (5, "submitted"),
    ]


def test_the_harness_guide_is_v1():
    """TB-D B2 (rev. 6): `harness_guide_v1` (prefix 14,284 tokens by count_tokens) stays the default;
    v2 (9,019) had about twice v1's wrong sentences over two score rows each. v2 stays reachable
    with `--harness-guide`."""

    assert harness.HARNESS_GUIDE == "harness_guide_v1"
    for name in ("harness_guide_v1", "harness_guide_v2"):
        guide = (harness.PROMPTS / f"{name}.md").read_text(encoding="utf-8")
        assert "view" not in guide and "show_game" not in guide
