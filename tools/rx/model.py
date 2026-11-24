"""The writer model over OpenRouter's chat completions (RX1-D §4.5), with the standard library.

The request carries what HIMARI's carries (`provider/openrouter.py`): the model, the messages, the
tools, and `reasoning.effort` only when one is given. No temperature, top_p or seed. The key is read
from `OPENROUTER_API_KEY` and never written anywhere.

MH (agent-mh-implementation.md): the default model is Haiku 5.5. An Anthropic model caches only what
the request marks, so its system message and its last text message carry `cache_control`; the
messages the loop keeps are never changed (`cache=False` sends none). A run's id is OpenRouter's
`session_id`, its sticky-routing key, so a run's requests stay on the provider that holds its cache.
The usage records the cached and cache-written tokens.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
KEY_VAR = "OPENROUTER_API_KEY"
REQUEST_SECONDS = 120  # RX1-D §4.7: a socket timeout, one retry
# TB-D C1: `claude-…` goes to the Claude API (`claude.py`). The owner (2026-11-10): OpenRouter's
# credit first, then the Claude API, so the default stays MH's model on OpenRouter until then
DEFAULT_MODEL = "anthropic/claude-haiku-5.5"


def claude_id(model: str) -> str | None:
    """The Claude API's name of an OpenRouter Anthropic model (`anthropic/claude-haiku-5.5` →
    `claude-haiku-5-5`), for counting its requests (TB-D B4); None for any other model."""

    if is_claude(model):
        return model
    if model.startswith("anthropic/claude-"):
        return model.removeprefix("anthropic/").replace(".", "-")
    return None


CACHE_CONTROL = {"type": "ephemeral"}
CUT_MESSAGE = "답이 출력 한도에서 잘렸어. 더 짧게, 또는 나눠서 다시 써."  # TB-D C4


def is_claude(model: str) -> bool:
    """TB-D C1: the Claude API's models are named `claude-…`; every other name goes to OpenRouter."""

    return model.startswith("claude-")


def needs_cache_marks(model: str) -> bool:
    """OpenRouter caches an Anthropic model's prompt only at the request's `cache_control` marks;
    other providers (OpenAI's luna) cache by themselves."""

    return model.startswith("anthropic/")


def _marked(message: dict) -> dict:
    content = message.get("content")
    if not isinstance(content, str) or not content:
        return message
    return message | {
        "content": [{"type": "text", "text": content, "cache_control": CACHE_CONTROL}]
    }


def cache_marked(messages: list[dict]) -> list[dict]:
    """A copy of the messages with the system message and the last message whose content is text
    marked; the two marks (of Anthropic's four) cache the fixed prefix and the growing history."""

    out = list(messages)
    texts = [i for i, m in enumerate(out) if isinstance(m.get("content"), str) and m["content"]]
    for i in {0, texts[-1]} if texts else set():
        out[i] = _marked(out[i])
    return out


class ModelError(RuntimeError):
    pass


class ModelCancelled(ModelError):
    pass


class ModelTimeout(ModelError):
    pass


# a transport error is retried twice, after 2 s then 10 s; a timeout once (its wait is long)
RETRY_WAITS = (2, 10)


def with_retries(call, cancel_event: threading.Event | None = None):
    """The runner's retries (RX1-D §4.7, HS-D §4; widened after the eight-game run of 2026-11-11,
    where four runs of eight ended on one network error each)."""

    timeouts = 0
    for attempt in range(len(RETRY_WAITS) + 1):
        if cancel_event is not None and cancel_event.is_set():
            raise ModelCancelled("cancelled")
        try:
            return call()
        except ModelCancelled:
            raise
        except ModelTimeout:
            timeouts += 1
            if timeouts > 1 or attempt == len(RETRY_WAITS):
                raise
        except ModelTransient:
            if attempt == len(RETRY_WAITS):
                raise
        wait_s = RETRY_WAITS[attempt]
        if cancel_event is not None:
            if cancel_event.wait(wait_s):
                raise ModelCancelled("cancelled")
        else:
            time.sleep(wait_s)
    raise AssertionError("unreachable")


class ModelTransient(ModelError):
    """HS-D §4 (review N2): the request process reported a transport error (an answer cut short, a
    connection dropped); retried once, as a timeout is."""


def read_env_file(path: Path) -> None:
    """`KEY=value` lines into the environment, as HIMARI's `--env-file`; set variables win."""

    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip().strip("'\"")
        if name and name not in os.environ:
            os.environ[name] = value


def run_request_child(
    payload: bytes, timeout: float, cancel_event: threading.Event | None = None
) -> tuple[bytes, bytes]:
    """Run `python -m tools.rx.request` with `payload`, killing it on timeout or cancel."""

    env = dict(os.environ) | {"PYTHONUTF8": "1"}
    child = subprocess.Popen(
        [sys.executable, "-m", "tools.rx.request"],
        cwd=str(REPO),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if cancel_event is None:
        try:
            return child.communicate(payload, timeout=timeout)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
            raise ModelTimeout(f"no answer in {timeout} s; the request was killed") from None
    if cancel_event.is_set():
        child.kill()
        child.wait()
        raise ModelCancelled("cancelled")

    result: list[tuple[bytes, bytes]] = []
    errors: list[BaseException] = []

    def _communicate() -> None:
        try:
            result.append(child.communicate(payload))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=_communicate, daemon=True)
    thread.start()
    deadline = time.monotonic() + timeout
    while thread.is_alive():
        if cancel_event.is_set():
            child.kill()
            child.wait()
            thread.join(timeout=2)
            raise ModelCancelled("cancelled")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            child.kill()
            child.wait()
            thread.join(timeout=2)
            raise ModelTimeout(f"no answer in {timeout} s; the request was killed") from None
        thread.join(timeout=min(0.2, remaining))
    if errors:
        raise errors[0]
    return result[0]


def post_in_child(
    endpoint: str, body: dict, timeout: float, cancel_event: threading.Event | None = None
) -> dict:
    """RX2-D §2 (RX1 review N4): the request in `python -m tools.rx.request`, killed at the deadline,
    which ends its socket with it. The key reaches the child through the environment only."""

    job = json.dumps({"endpoint": endpoint, "body": body}, ensure_ascii=False).encode("utf-8")
    out, err = run_request_child(job, timeout, cancel_event)
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
    try:
        return json.loads(answer["text"])
    except ValueError as error:  # a body that is not JSON (RX1 review B2)
        raise ModelError(f"the answer is not JSON: {answer['text'][:200]!r}") from error


@dataclass
class Reply:
    message: dict  # the assistant message as returned (content, tool_calls, reasoning fields)
    usage: dict  # tokens in and out, cost when given
    body_fields: list[str]  # the request's top-level fields (RX1-D Q2)
    stop: str | None = None  # TB-D C4: tool_use, end_turn, max_tokens, refusal (OpenRouter mapped)

    @property
    def cut(self) -> bool:
        """C4: the answer stopped at its output limit; it is never kept or run."""

        return self.stop == "max_tokens"

    @property
    def refused(self) -> bool:
        return self.stop == "refusal"


class OpenRouter:
    def __init__(self, model: str, reasoning_effort: str | None = None,
                 endpoint: str = ENDPOINT, timeout: float = REQUEST_SECONDS, *,
                 cache: bool = True, session_id: str | None = None,
                 cancel_event: threading.Event | None = None) -> None:  # fmt: skip
        """`cache`: send Anthropic's cache marks (MH review F1: the one place they are made).
        `session_id`: OpenRouter's sticky-routing key, one a run (MH review F2)."""

        if not os.environ.get(KEY_VAR):
            raise ModelError(f"{KEY_VAR} is not set (environment or --env-file)")
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.endpoint = endpoint
        self.timeout = timeout
        self.cache = cache
        self.session_id = session_id
        self.cancel_event = cancel_event

    def __repr__(self) -> str:  # never the key
        return f"OpenRouter(model={self.model!r})"

    def _post(self, body: dict) -> dict:
        return post_in_child(self.endpoint, body, self.timeout, self.cancel_event)

    def body(self, messages: list[dict], tools: list[dict]) -> dict:
        if self.cache and needs_cache_marks(self.model):
            messages = cache_marked(messages)
        body: dict = {"model": self.model, "messages": messages}
        if tools:
            body["tools"] = tools
        if self.reasoning_effort is not None:
            body["reasoning"] = {"effort": self.reasoning_effort}
        if self.session_id is not None:
            body["session_id"] = self.session_id
        return body

    def complete(self, messages: list[dict], tools: list[dict],
                 tool_choice: str | None = None) -> Reply:  # fmt: skip
        body = self.body(messages, tools)
        if tool_choice is not None and tools:  # TB-D B4.3: compaction sends `none`
            body["tool_choice"] = tool_choice
        doc = with_retries(lambda: self._post(body), self.cancel_event)
        if "error" in doc:
            raise ModelError(
                f"provider error: {json.dumps(doc['error'], ensure_ascii=False)[:500]}"
            )
        choice = (doc.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = doc.get("usage") or {}
        details = usage.get("prompt_tokens_details") or {}
        return Reply(
            message={k: v for k, v in message.items() if v is not None},
            usage={"input_tokens": usage.get("prompt_tokens"),
                   "output_tokens": usage.get("completion_tokens"),
                   "cached_tokens": details.get("cached_tokens"),
                   "cache_write_tokens": details.get("cache_write_tokens"),
                   "cost": usage.get("cost"), "finish": choice.get("finish_reason")},
            body_fields=sorted(body),
            stop={"length": "max_tokens", "tool_calls": "tool_use",
                  "stop": "end_turn"}.get(choice.get("finish_reason")),
        )  # fmt: skip


def make_model(model: str, reasoning_effort: str | None = None, *, cache: bool = True,
               session_id: str | None = None, judge: bool = False,
               cancel_event: threading.Event | None = None):  # fmt: skip
    """TB-D C1: the client for a model name; `judge`: the judge's output limit (C4)."""

    if is_claude(model):
        from .claude import JUDGE_MAX_TOKENS, MAX_TOKENS, Claude

        return Claude(model, reasoning_effort, cache=cache, session_id=session_id,
                      max_tokens=JUDGE_MAX_TOKENS if judge else MAX_TOKENS,
                      cancel_event=cancel_event)  # fmt: skip
    return OpenRouter(model, reasoning_effort, cache=cache, session_id=session_id,
                      cancel_event=cancel_event)  # fmt: skip
