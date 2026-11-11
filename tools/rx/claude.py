"""TB-D C: the writer (or judge) on the Claude API.

The loop keeps its messages in OpenAI's shape (`content`, `tool_calls`, `tool` answers); `to_claude`
converts them at the request and `from_claude` normalizes the answer back, keeping the answer's
blocks exactly as returned in `blocks`, which are what the next request sends (C3). The request
runs in `python -m tools.rx.request` through the official SDK, killed at its deadline (C2). The key
is read from `ANTHROPIC_API_KEY` and never written anywhere.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys

from .model import (
    CACHE_CONTROL,
    REPO,
    ModelError,
    ModelTimeout,
    ModelTransient,
    Reply,
    with_retries,
)

KEY_VAR = "ANTHROPIC_API_KEY"
REQUEST_SECONDS = 600  # C2 (re-review N2; review N5): the child's deadline for one request
ATTEMPT_SECONDS = (
    280  # review N5: a 16k-token answer fits one attempt; one SDK retry fits the deadline
)
COUNT_SECONDS = 30  # B4.1: the token count's deadline
MAX_TOKENS = 16_000  # C4: the writer's answers, thinking included
JUDGE_MAX_TOKENS = 4_000  # C4 (re-review N8): the judge's answers
DEFAULT_EFFORT = "medium"  # C4 (re-review N7): sent when the run names none
# C5: USD per MTok, Anthropic's pricing page (2026-11-10): (prompts up to this many tokens, input,
# 5-minute cache write, cache read, output). A request's prompt counts all its input tokens, cache
# reads and writes included, and a prompt over the limit pays the higher prices on all of it.
PRICES = {
    "claude-haiku-5-5": [(100_000, 0.10, 0.125, 0.01, 0.50), (None, 0.50, 0.625, 0.05, 2.50)],
    "claude-sonnet-5-5": [(None, 2.00, 2.50, 0.10, 10.00)],
}


def cost(model: str, uncached: int, cache_read: int, cache_write: int, output: int) -> float | None:
    """C5: a request's cost at the tier its whole prompt falls in; None for a model not priced."""

    prompt = uncached + cache_read + cache_write
    for limit, inp, write, read, out in PRICES.get(model) or []:
        if limit is None or prompt <= limit:
            return (uncached * inp + cache_write * write + cache_read * read + output * out) / 1e6
    return None


def _text(text: str) -> dict:
    return {"type": "text", "text": text}


def _tool_use(call: dict) -> dict:
    function = call.get("function") or {}
    try:
        arguments = json.loads(function.get("arguments") or "{}")
    except ValueError:
        arguments = {}
    return {"type": "tool_use", "id": call.get("id"), "name": function.get("name"),
            "input": arguments if isinstance(arguments, dict) else {}}  # fmt: skip


def _tool_result(message: dict) -> dict:
    text = message.get("content") or ""
    out = {"type": "tool_result", "tool_use_id": message.get("tool_call_id"), "content": text}
    if text.startswith("[tool error]"):  # C3 (re-review N9)
        out["is_error"] = True
    return out


def to_claude(messages: list[dict]) -> tuple[list[dict], list[dict]]:
    """C3: the loop's messages as the Messages API's `system` blocks and `messages`.

    An assistant message with `blocks` is sent as those blocks, unchanged; one without is built from
    `content` and `tool_calls`. Tool answers and the runner's text after them form one user message
    with the `tool_result` blocks first; consecutive user messages merge."""

    system: list[dict] = []
    out: list[dict] = []

    def user(blocks: list[dict]) -> None:
        if out and out[-1]["role"] == "user":
            last = out[-1]["content"]
            if blocks[0]["type"] == "tool_result":
                results = [b for b in last if b["type"] == "tool_result"]
                rest = [b for b in last if b["type"] != "tool_result"]
                out[-1]["content"] = results + blocks + rest
            else:
                last.extend(blocks)
        else:
            out.append({"role": "user", "content": list(blocks)})

    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role == "system":
            if content:
                system.append(_text(content))
        elif role == "assistant":
            if message.get("blocks"):
                blocks = copy.deepcopy(message["blocks"])
            else:
                blocks = [_text(content)] if content else []
                blocks += [_tool_use(c) for c in message.get("tool_calls") or []]
            out.append({"role": "assistant", "content": blocks or [_text("")]})
        elif role == "tool":
            user([_tool_result(message)])
        elif content:
            user([_text(content)] if isinstance(content, str) else list(content))
    return system, out


def tools_of(tools: list[dict]) -> list[dict]:
    """The runner's tool list (OpenAI's `function` shape) as the Messages API's."""

    out = []
    for tool in tools:
        f = tool.get("function", tool)
        out.append({"name": f["name"], "description": f.get("description") or "",
                    "input_schema": f.get("parameters") or {"type": "object"}})  # fmt: skip
    return out


def from_claude(doc: dict, model: str) -> Reply:
    """C3, C5: the answer normalized for the loop (`content`, `tool_calls`) with its blocks kept as
    returned (`blocks`); `usage.input_tokens` is the total input, the parts beside it."""

    blocks = doc.get("content") or []
    texts = [b.get("text") or "" for b in blocks if b.get("type") == "text"]
    calls = [{"id": b.get("id"), "type": "function",
              "function": {"name": b.get("name"),
                           "arguments": json.dumps(b.get("input") or {}, ensure_ascii=False)}}
             for b in blocks if b.get("type") == "tool_use"]  # fmt: skip
    message: dict = {"role": "assistant", "content": "".join(texts) or None, "blocks": blocks}
    if calls:
        message["tool_calls"] = calls
    raw = doc.get("usage") or {}
    uncached = raw.get("input_tokens") or 0
    read = raw.get("cache_read_input_tokens") or 0
    write = raw.get("cache_creation_input_tokens") or 0
    output = raw.get("output_tokens") or 0
    stop = doc.get("stop_reason")
    usage = {"input_tokens": uncached + read + write, "output_tokens": output,
             "uncached_input_tokens": uncached, "cached_tokens": read, "cache_write_tokens": write,
             "cost": cost(model, uncached, read, write, output), "finish": stop}  # fmt: skip
    if stop == "refusal":
        usage["refusal"] = (doc.get("stop_details") or {}).get("category")
    return Reply(message={k: v for k, v in message.items() if v is not None}, usage=usage,
                 body_fields=[], stop=stop)  # fmt: skip


def call_in_child(job: dict, timeout: float) -> dict:
    """C2: one SDK call in `python -m tools.rx.request`, killed at the deadline. The key reaches the
    child through the environment only."""

    data = json.dumps(job, ensure_ascii=False).encode("utf-8")
    child = subprocess.Popen([sys.executable, "-m", "tools.rx.request"], cwd=str(REPO),
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)  # fmt: skip
    try:
        out, err = child.communicate(data, timeout=timeout)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()
        raise ModelTimeout(f"no answer in {timeout} s; the request was killed") from None
    try:
        answer = json.loads(out.decode("utf-8"))
    except ValueError as error:
        raise ModelError(f"the request process gave no answer: {err[-300:]!r}") from error
    if "error" in answer:
        if answer.get("kind") == "transport":
            raise ModelTransient(f"request cut short: {answer['error']}")
        raise ModelError(f"request failed: {answer['error']}")
    if answer.get("status") != 200:
        raise ModelError(f"HTTP {answer.get('status')}: {answer.get('text', '')[:500]}")
    return answer["doc"]


class Claude:
    """The same `complete(messages, tools)` as `OpenRouter`; `count(messages, tools)` gives the
    request's input tokens before it is sent (B4.1)."""

    def __init__(self, model: str, reasoning_effort: str | None = None,
                 timeout: float = REQUEST_SECONDS, *, cache: bool = True,
                 session_id: str | None = None, max_tokens: int = MAX_TOKENS) -> None:  # fmt: skip
        if not os.environ.get(KEY_VAR):
            raise ModelError(f"{KEY_VAR} is not set (environment or --env-file)")
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.timeout = timeout
        self.cache = cache
        self.session_id = session_id  # OpenRouter's routing key: not sent here
        self.max_tokens = max_tokens

    provider = "claude"

    def __repr__(self) -> str:  # never the key
        return f"Claude(model={self.model!r})"

    def _call(self, call: str, body: dict, timeout: float) -> dict:
        return call_in_child({"provider": "claude", "call": call, "body": body,
                              "attempt_seconds": ATTEMPT_SECONDS}, timeout)  # fmt: skip

    def body(self, messages: list[dict], tools: list[dict], tool_choice: str | None = None) -> dict:
        system, converted = to_claude(messages)
        body: dict = {"model": self.model, "max_tokens": self.max_tokens, "messages": converted,
                      "output_config": {"effort": self.reasoning_effort or DEFAULT_EFFORT}}  # fmt: skip
        if system:
            body["system"] = system
        if tools:
            body["tools"] = tools_of(tools)
            body["tool_choice"] = {"type": tool_choice or "auto"}
        if (
            self.cache
        ):  # C4: the fixed prefix (tools, system) and the history, as OpenRouter's marks
            if system:
                system[-1] = system[-1] | {"cache_control": CACHE_CONTROL}
            for message in reversed(converted):
                block = message["content"][-1] if message["content"] else None
                if block and block.get("type") in ("text", "tool_result", "tool_use"):
                    message["content"][-1] = block | {"cache_control": CACHE_CONTROL}
                    break
        return body

    def count(self, messages: list[dict], tools: list[dict], tool_choice: str | None = None) -> int:
        """B4.1: `messages.count_tokens` on the request as it would be sent, retried once."""

        body = self.body(messages, tools, tool_choice)
        body.pop("max_tokens", None)
        try:
            return int(self._call("count_tokens", body, COUNT_SECONDS)["input_tokens"])
        except ModelError:
            return int(self._call("count_tokens", body, COUNT_SECONDS)["input_tokens"])

    def complete(self, messages: list[dict], tools: list[dict],
                 tool_choice: str | None = None) -> Reply:  # fmt: skip
        body = self.body(messages, tools, tool_choice)
        doc = with_retries(lambda: self._call("create", body, self.timeout))
        reply = from_claude(doc, self.model)
        reply.body_fields = sorted(body)
        return reply
