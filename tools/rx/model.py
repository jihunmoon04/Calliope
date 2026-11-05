"""The writer model over OpenRouter's chat completions (RX1-D §4.5), with the standard library.

The request carries what HIMARI's carries (`provider/openrouter.py`): the model, the messages, the
tools, and `reasoning.effort` only when one is given. No temperature, top_p or seed. The key is read
from `OPENROUTER_API_KEY` and never written anywhere.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
KEY_VAR = "OPENROUTER_API_KEY"
REQUEST_SECONDS = 120  # RX1-D §4.7: a socket timeout, one retry


class ModelError(RuntimeError):
    pass


class ModelTimeout(ModelError):
    pass


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


def post_in_child(endpoint: str, body: dict, timeout: float) -> dict:
    """RX2-D §2 (RX1 review N4): the request in `python -m tools.rx.request`, killed at the deadline,
    which ends its socket with it. The key reaches the child through the environment only."""

    job = json.dumps({"endpoint": endpoint, "body": body}, ensure_ascii=False).encode("utf-8")
    child = subprocess.Popen([sys.executable, "-m", "tools.rx.request"], cwd=str(REPO),
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)  # fmt: skip
    try:
        out, err = child.communicate(job, timeout=timeout)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()
        raise ModelTimeout(f"no answer in {timeout} s; the request was killed") from None
    try:
        answer = json.loads(out.decode("utf-8"))
    except ValueError as error:
        raise ModelError(f"the request process gave no answer: {err[-300:]!r}") from error
    if "error" in answer:
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


class OpenRouter:
    def __init__(self, model: str, reasoning_effort: str | None = None,
                 endpoint: str = ENDPOINT, timeout: float = REQUEST_SECONDS) -> None:  # fmt: skip
        if not os.environ.get(KEY_VAR):
            raise ModelError(f"{KEY_VAR} is not set (environment or --env-file)")
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.endpoint = endpoint
        self.timeout = timeout

    def __repr__(self) -> str:  # never the key
        return f"OpenRouter(model={self.model!r})"

    def _post(self, body: dict) -> dict:
        return post_in_child(self.endpoint, body, self.timeout)

    def body(self, messages: list[dict], tools: list[dict]) -> dict:
        body: dict = {"model": self.model, "messages": messages}
        if tools:
            body["tools"] = tools
        if self.reasoning_effort is not None:
            body["reasoning"] = {"effort": self.reasoning_effort}
        return body

    def complete(self, messages: list[dict], tools: list[dict]) -> Reply:
        body = self.body(messages, tools)
        for attempt in range(2):  # one retry on a timeout (RX1-D §4.7)
            try:
                doc = self._post(body)
                break
            except ModelTimeout:
                if attempt == 0:
                    time.sleep(2)
                    continue
                raise
        if "error" in doc:
            raise ModelError(
                f"provider error: {json.dumps(doc['error'], ensure_ascii=False)[:500]}"
            )
        choice = (doc.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = doc.get("usage") or {}
        return Reply(
            message={k: v for k, v in message.items() if v is not None},
            usage={"input_tokens": usage.get("prompt_tokens"),
                   "output_tokens": usage.get("completion_tokens"),
                   "cost": usage.get("cost"), "finish": choice.get("finish_reason")},
            body_fields=sorted(body),
        )  # fmt: skip
