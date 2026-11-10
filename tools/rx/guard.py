"""TB-D B4: the guard — no request above 100k input tokens.

Right before each request `run._loop` asks the guard for the whole request's size.
- On the Claude API: `messages.count_tokens` on the request as it will be sent (C3's conversion
  included), `counted`, against the send limit.
- An Anthropic model on OpenRouter, with the Claude key set: the larger of the Claude API's count and
  the usage estimate, `counted+usage`, against the send limit. The count leaves out what OpenRouter
  keeps in `reasoning` fields (implementation review F1: 20–28% late in a moment); the estimate is
  the last answer's total input plus the new messages' characters at one token per two.
- Otherwise the estimate alone (or, for a moment's first request, the whole request's characters),
  `estimated`, against a lower limit.

Over 80k, or over the limit before the moment's restart, the loop sends nothing and returns `compact`;
over the limit after the restart, `moment_budget`.
"""

from __future__ import annotations

import json
import os

from .model import ModelError, claude_id

CLAUDE_KEY = "ANTHROPIC_API_KEY"

COMPACT_AT = 80_000  # B4.2: compaction
SEND_LIMIT = 95_000  # B4.2: never sent above; `count_tokens` is an estimate, 5k of margin
ESTIMATED_LIMIT = 85_000  # B4.5: the estimated contract (no count)
NOTES_LIMIT = 2_000  # B4.3: the notes kept across a restart
CHARS_PER_TOKEN = 2  # B4.5: the conservative ratio for an estimate


def _chars(messages: list[dict], tools: list[dict]) -> int:
    return len(json.dumps(messages, ensure_ascii=False)) + len(
        json.dumps(tools, ensure_ascii=False)
    )


class Guard:
    """One moment's guard: `restarted` after its one compaction (B4.3)."""

    def __init__(self, log) -> None:
        self.log = log
        self.restarted = False
        self.last_input: int | None = None  # the last answer's total input
        self.last_sent = 0  # how many messages that request held
        self.last_size = 0
        self.last_how = "counted"
        self.last_parts: dict = {}
        self._claude = None  # the Claude API counter of an OpenRouter Anthropic model

    def new_moment(self) -> None:
        self.restarted = False
        self.last_input, self.last_sent, self.last_size = None, 0, 0

    def _estimate(self, messages: list[dict], tools: list[dict]) -> int:
        if self.last_input is not None and self.last_sent <= len(messages):
            return self.last_input + _chars(messages[self.last_sent :], []) // CHARS_PER_TOKEN
        return _chars(messages, tools) // CHARS_PER_TOKEN

    def size(self, model, messages: list[dict], tools: list[dict],
             tool_choice: str | None = None) -> tuple[int, str]:  # fmt: skip
        """The request's input tokens and how they were found: `counted`, `counted+usage` or
        `estimated` (the module's docstring)."""

        own = hasattr(model, "count")
        counter = model if own else self._counter(model)
        counted = None
        if counter is not None:
            try:
                counted = counter.count(messages, tools, tool_choice)
            except ModelError as error:  # B4.1: a failed count, retried once, then estimated
                self.log.write({"type": "guard_count_failed", "error": str(error)[:300]})
        if own and counted is not None:
            self.last_parts = {"count": counted}
            return counted, "counted"
        estimate = self._estimate(messages, tools)
        self.last_parts = {"count": counted, "estimate": estimate}
        if counted is not None:  # F1: what the count leaves out is in the usage
            return max(counted, estimate), "counted+usage"
        return estimate, "estimated"

    def _counter(self, model):
        """An OpenRouter Anthropic model's requests counted by the Claude API's free
        `count_tokens` when its key is set (the owner: OpenRouter first, the Claude key at hand)."""

        if self._claude is None:
            name = claude_id(getattr(model, "model", "") or "")
            if name is None or not os.environ.get(CLAUDE_KEY):
                self._claude = False
            else:
                from .claude import Claude

                self._claude = Claude(name, cache=getattr(model, "cache", True))
        return self._claude or None

    @staticmethod
    def limit(how: str) -> int:
        return ESTIMATED_LIMIT if how == "estimated" else SEND_LIMIT

    def check(self, model, messages: list[dict], tools: list[dict]) -> str | None:
        """None to send; `compact` or `moment_budget` to send nothing (B4.2)."""

        size, how = self.size(model, messages, tools)
        limit = self.limit(how)
        self.last_size, self.last_how = size, how
        verdict = None
        if size > limit:
            verdict = "moment_budget" if self.restarted else "compact"
        elif size > COMPACT_AT and not self.restarted:
            verdict = "compact"
        self.log.write({"type": "guard", "counted_tokens": size, "how": how, "limit": limit,
                        "parts": self.last_parts, "restarted": self.restarted,
                        "verdict": verdict or "send"})  # fmt: skip
        return verdict

    def answered(self, usage: dict, sent: int) -> None:
        """After an answer: its total input, for the next estimate."""

        self.last_input = usage.get("input_tokens")
        self.last_sent = sent
