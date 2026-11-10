"""TB-D C: the Claude API client — the conversion both ways, the original blocks sent back, cut
answers never kept or run, refusals, usage as the total input, the price table, the key."""

from __future__ import annotations

import json
from types import SimpleNamespace

import anyio
import pytest

from tools.rx import claude as rx_claude
from tools.rx import model as rx_model
from tools.rx import run as rx_run

TOOLS = [{"type": "function", "function": {"name": "ply", "description": "d",
                                           "parameters": {"type": "object"}}}]  # fmt: skip
THINKING = {"type": "thinking", "thinking": "", "signature": "sig-abc"}


def _doc(blocks, stop="end_turn", usage=None, **extra):
    return {"content": blocks, "stop_reason": stop,
            "usage": usage or {"input_tokens": 10, "output_tokens": 5}} | extra  # fmt: skip


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setenv(rx_claude.KEY_VAR, "test-key-not-real")


def test_a_claude_model_name_goes_to_the_claude_api(keyed, monkeypatch):
    monkeypatch.setenv(rx_model.KEY_VAR, "test-key-not-real")
    assert rx_model.DEFAULT_MODEL == "claude-haiku-5-5"
    assert isinstance(rx_model.make_model("claude-haiku-5-5"), rx_claude.Claude)
    assert isinstance(rx_model.make_model("anthropic/claude-haiku-5.5"), rx_model.OpenRouter)
    assert rx_model.make_model("claude-haiku-5-5", judge=True).max_tokens == 4_000
    assert rx_model.make_model("claude-haiku-5-5").max_tokens == 16_000


def test_the_key_is_needed_and_never_shown(monkeypatch):
    monkeypatch.delenv(rx_claude.KEY_VAR, raising=False)
    with pytest.raises(rx_model.ModelError, match="ANTHROPIC_API_KEY"):
        rx_claude.Claude("claude-haiku-5-5")
    monkeypatch.setenv(rx_claude.KEY_VAR, "secret-value-123")
    client = rx_claude.Claude("claude-haiku-5-5")
    assert "secret-value-123" not in repr(client)
    body = client.body([{"role": "user", "content": "hi"}], TOOLS)
    assert "secret-value-123" not in json.dumps(body)


def test_the_answer_is_normalized_and_its_blocks_kept():
    blocks = [
        THINKING,
        {"type": "text", "text": "facts "},
        {"type": "text", "text": "here"},
        {"type": "tool_use", "id": "t1", "name": "ply", "input": {"ply": 3}},
        {"type": "tool_use", "id": "t2", "name": "squares", "input": {"squares": ["e4"]}},
    ]
    reply = rx_claude.from_claude(_doc(blocks, "tool_use"), "claude-haiku-5-5")
    assert reply.message["content"] == "facts here"  # last_text and claims_of read this
    assert [c["function"]["name"] for c in reply.message["tool_calls"]] == ["ply", "squares"]
    assert json.loads(reply.message["tool_calls"][0]["function"]["arguments"]) == {"ply": 3}
    assert reply.message["blocks"] == blocks and reply.stop == "tool_use"
    assert not reply.cut and not reply.refused


def test_the_next_request_sends_the_blocks_byte_for_byte(keyed):
    """C3's round trip: an answer with thinking, text and two tool calls; both answered in one user
    turn, results first, then the runner's text."""

    blocks = [
        THINKING,
        {"type": "text", "text": "t"},
        {"type": "tool_use", "id": "t1", "name": "ply", "input": {"ply": 3}},
        {"type": "tool_use", "id": "t2", "name": "ply", "input": {"ply": 4}},
    ]
    reply = rx_claude.from_claude(_doc(blocks, "tool_use"), "claude-haiku-5-5")
    kept = {
        "role": "assistant",
        "content": reply.message["content"],
        "tool_calls": reply.message["tool_calls"],
        "blocks": reply.message["blocks"],
    }
    messages = [{"role": "system", "content": "guide"}, {"role": "user", "content": "task"}, kept,
                {"role": "tool", "tool_call_id": "t1", "content": "a"},
                {"role": "tool", "tool_call_id": "t2", "content": "[tool error] no"},
                {"role": "user", "content": "feedback"}]  # fmt: skip
    body = rx_claude.Claude("claude-haiku-5-5", cache=False).body(messages, TOOLS)
    assert body["system"] == [{"type": "text", "text": "guide"}]
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
    assert json.dumps(body["messages"][1]["content"]) == json.dumps(blocks)
    turn = body["messages"][2]["content"]
    assert [b["type"] for b in turn] == ["tool_result", "tool_result", "text"]
    assert [b["tool_use_id"] for b in turn[:2]] == ["t1", "t2"]
    assert "is_error" not in turn[0] and turn[1]["is_error"] is True
    assert body["tools"] == [{"name": "ply", "description": "d",
                              "input_schema": {"type": "object"}}]  # fmt: skip
    assert body["max_tokens"] == 16_000 and body["output_config"] == {"effort": "medium"}
    assert body["tool_choice"] == {"type": "auto"} and "temperature" not in body


def test_a_history_from_openrouter_converts(keyed):
    messages = [{"role": "user", "content": "task"},
                {"role": "assistant", "content": None,
                 "tool_calls": [{"id": "c1", "function": {"name": "ply",
                                                          "arguments": "{\"ply\": 2}"}}]},
                {"role": "tool", "tool_call_id": "c1", "content": "r"}]  # fmt: skip
    body = rx_claude.Claude("claude-haiku-5-5", "low", cache=False).body(messages, TOOLS, "none")
    assert body["messages"][1]["content"] == [{"type": "tool_use", "id": "c1", "name": "ply",
                                               "input": {"ply": 2}}]  # fmt: skip
    assert body["tool_choice"] == {"type": "none"} and body["output_config"]["effort"] == "low"


def test_cache_marks_on_the_system_and_the_last_block(keyed):
    body = rx_claude.Claude("claude-haiku-5-5").body(
        [{"role": "system", "content": "g"}, {"role": "user", "content": "t"}], TOOLS
    )
    assert body["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert body["messages"][-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}


def test_usage_is_the_total_input_and_cost_follows_the_100k_step():
    usage = {"input_tokens": 1_000, "cache_read_input_tokens": 50_000,
             "cache_creation_input_tokens": 2_000, "output_tokens": 500}  # fmt: skip
    reply = rx_claude.from_claude(_doc([{"type": "text", "text": "x"}], usage=usage),
                                  "claude-haiku-5-5")  # fmt: skip
    u = reply.usage
    assert u["input_tokens"] == 53_000 and u["uncached_input_tokens"] == 1_000
    assert u["cached_tokens"] == 50_000 and u["cache_write_tokens"] == 2_000
    assert u["cost"] == pytest.approx((1_000 * 0.10 + 2_000 * 0.125 + 50_000 * 0.01
                                       + 500 * 0.50) / 1e6)  # fmt: skip
    over = rx_claude.cost(
        "claude-haiku-5-5", 1_000, 100_000, 0, 500
    )  # 101k: all at the higher price
    assert over == pytest.approx((1_000 * 0.50 + 100_000 * 0.05 + 500 * 2.50) / 1e6)
    assert rx_claude.cost("claude-sonnet-5-5", 1_000_000, 0, 0, 0) == pytest.approx(2.0)
    assert rx_claude.cost("claude-unknown", 1, 0, 0, 0) is None


def test_a_refusal_carries_its_category():
    reply = rx_claude.from_claude(_doc([], "refusal", stop_details={"category": "cyber"}),
                                  "claude-haiku-5-5")  # fmt: skip
    assert reply.refused and reply.usage["refusal"] == "cyber"


def test_openrouter_finish_reasons_map_to_stops(monkeypatch):
    monkeypatch.setenv(rx_model.KEY_VAR, "test-key-not-real")
    doc = {"choices": [{"message": {"content": "x"}, "finish_reason": "length"}], "usage": {}}
    monkeypatch.setattr(rx_model.OpenRouter, "_post", lambda self, body: doc)
    assert rx_model.OpenRouter("m").complete([], []).cut


# -- the loop: cut answers and refusals (C4) ---------------------------------------------------


class _Scripted:
    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def complete(self, messages, tools):
        self.seen.append(json.loads(json.dumps(messages)))
        return self.replies.pop(0)


class _Session:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append(name)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="{}")], isError=False)


class _Log:
    def __init__(self):
        self.lines = []

    def write(self, line):
        self.lines.append(line)


def _loop(replies):
    model, session, log = _Scripted(replies), _Session(), _Log()
    spec = rx_run.RunSpec(arm="A", set_name="v", game="g", pgn="", moments=[1], base=None,
                          records=None, work=None)  # fmt: skip
    totals = {"turns": 0, "tool_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}
    messages = [{"role": "user", "content": "task"}]
    reason = anyio.run(rx_run._loop, session, model, messages, TOOLS, spec, log, totals, {}, 0)
    return reason, model, session, log, messages


def _reply(doc):
    return rx_claude.from_claude(doc, "claude-haiku-5-5")


CUT = _doc([THINKING, {"type": "tool_use", "id": "t9", "name": "ply", "input": {}}], "max_tokens")


def test_a_cut_answer_is_never_run_or_kept():
    reason, model, session, log, _ = _loop(
        [_reply(CUT), _reply(_doc([{"type": "text", "text": "done"}]))]
    )
    assert reason == "done" and session.calls == []  # its tool call never ran
    second = json.dumps(model.seen[1])
    assert "t9" not in second and "sig-abc" not in second  # none of its blocks are sent again
    assert model.seen[1][-1] == {"role": "user", "content": rx_model.CUT_MESSAGE}
    assert any(x.get("type") == "cut" for x in log.lines)
    assert any(x.get("type") == "response" and x["message"].get("blocks") for x in log.lines)


def test_two_cuts_in_a_row_end_the_moment():
    reason, _, session, _, _ = _loop([_reply(CUT), _reply(CUT)])
    assert reason == "moment_cut" and session.calls == []


def test_a_refusal_ends_the_moment():
    reason, _, _, log, messages = _loop(
        [_reply(_doc([], "refusal", stop_details={"category": "bio"}))]
    )
    assert reason == "moment_refused"
    assert {"type": "refusal", "category": "bio"} in [
        {k: v for k, v in x.items() if k in ("type", "category")}
        for x in log.lines
        if x.get("type") == "refusal"
    ]
    assert messages == [{"role": "user", "content": "task"}]  # the refusal is not kept


def test_the_kept_assistant_message_has_its_blocks():
    blocks = [THINKING, {"type": "tool_use", "id": "t1", "name": "ply", "input": {"ply": 1}}]
    reason, _, session, _, messages = _loop(
        [_reply(_doc(blocks, "tool_use")), _reply(_doc([{"type": "text", "text": "ok"}]))]
    )
    assert reason == "done" and session.calls == ["ply"]
    assert messages[1]["blocks"] == blocks
