"""MH (agent-mh-implementation.md): the runner's default model, Anthropic's cache marks and the cached
tokens in the usage."""

from __future__ import annotations

import copy

import pytest

from tools.rx import model as rx_model
from tools.rx import run as rx_run

TOOLS = [{"type": "function", "function": {"name": "ply", "description": "", "parameters": {}}}]


def _messages() -> list[dict]:
    return [
        {"role": "system", "content": "guide"},
        {"role": "user", "content": "task"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "result"},
    ]


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setenv(rx_model.KEY_VAR, "test-key-not-real")


def _marks(message: dict) -> list:
    content = message.get("content")
    return [part.get("cache_control") for part in content] if isinstance(content, list) else []


def test_the_default_model_is_haiku():
    assert rx_model.DEFAULT_MODEL == "anthropic/claude-haiku-5.5"
    assert rx_run.RunSpec.__dataclass_fields__["model"].default == rx_model.DEFAULT_MODEL


def test_an_anthropic_request_marks_the_system_and_the_last_text_message(keyed):
    messages = _messages()
    kept = copy.deepcopy(messages)
    body = rx_model.OpenRouter("anthropic/claude-haiku-5.5").body(messages, TOOLS)
    sent = body["messages"]
    assert _marks(sent[0]) == [{"type": "ephemeral"}]
    assert sent[0]["content"][0]["text"] == "guide"
    assert _marks(sent[3]) == [{"type": "ephemeral"}]  # the tool result, the last text
    assert sent[1] == kept[1] and sent[2] == kept[2]  # unmarked, as they were
    assert messages == kept  # the loop's own list is never changed


def test_one_text_message_gets_one_mark(keyed):
    body = rx_model.OpenRouter("anthropic/claude-haiku-5.5").body(
        [{"role": "system", "content": "g"}], []
    )
    assert _marks(body["messages"][0]) == [{"type": "ephemeral"}]


def test_another_provider_is_sent_as_before(keyed):
    messages = _messages()
    body = rx_model.OpenRouter("openai/gpt-6-luna").body(messages, TOOLS)
    assert body["messages"] == messages
    assert sorted(body) == ["messages", "model", "tools"]


def test_the_usage_keeps_cached_tokens(keyed, monkeypatch):
    doc = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
           "usage": {"prompt_tokens": 1000, "completion_tokens": 10, "cost": 0.001,
                     "prompt_tokens_details": {"cached_tokens": 900, "cache_write_tokens": 100}}}  # fmt: skip
    monkeypatch.setattr(rx_model.OpenRouter, "_post", lambda self, body: doc)
    reply = rx_model.OpenRouter("anthropic/claude-haiku-5.5").complete(_messages(), TOOLS)
    assert reply.usage["cached_tokens"] == 900
    assert reply.usage["cache_write_tokens"] == 100
    assert reply.usage["input_tokens"] == 1000
