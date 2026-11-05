"""The writer model over OpenRouter's chat completions (RX1-D §4.5), with the standard library.

The request carries what HIMARI's carries (`provider/openrouter.py`): the model, the messages, the
tools, and `reasoning.effort` only when one is given. No temperature, top_p or seed. The key is read
from `OPENROUTER_API_KEY` and never written anywhere.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

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


def _read_by(response, deadline: float, chunk: int = 65536) -> bytes:
    """The whole body by a deadline: the socket timeout bounds each read, this bounds the request
    (review N1: a server that sends a little at a time)."""

    parts = []
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError("the answer took longer than the request's bound")
        part = response.read(chunk)
        if not part:
            return b"".join(parts)
        parts.append(part)


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

    def body(self, messages: list[dict], tools: list[dict]) -> dict:
        body: dict = {"model": self.model, "messages": messages}
        if tools:
            body["tools"] = tools
        if self.reasoning_effort is not None:
            body["reasoning"] = {"effort": self.reasoning_effort}
        return body

    def complete(self, messages: list[dict], tools: list[dict]) -> Reply:
        body = self.body(messages, tools)
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        last: Exception | None = None
        for attempt in range(2):  # one retry on a timeout (RX1-D §4.7)
            request = urllib.request.Request(self.endpoint, data=data, method="POST", headers={
                "Authorization": "Bearer " + os.environ[KEY_VAR],
                "Content-Type": "application/json",
            })  # fmt: skip
            try:
                began = time.monotonic()
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = _read_by(response, began + self.timeout)
                try:
                    doc = json.loads(raw.decode("utf-8"))
                except ValueError as error:  # a body that is not JSON (review B2)
                    raise ModelError(f"the answer is not JSON: {raw[:200]!r}") from error
                break
            except TimeoutError as error:
                last = error
                if attempt == 0:
                    time.sleep(2)
                    continue
                raise ModelTimeout(f"no answer in {self.timeout} s, twice") from error
            except urllib.error.HTTPError as error:
                detail = error.read().decode("utf-8", "replace")[:500]
                raise ModelError(f"HTTP {error.code}: {detail}") from error
            except urllib.error.URLError as error:
                if isinstance(error.reason, TimeoutError) and attempt == 0:
                    last = error
                    time.sleep(2)
                    continue
                raise ModelError(f"request failed: {error.reason}") from error
        else:  # pragma: no cover - the loop breaks or raises
            raise ModelError(str(last))
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
