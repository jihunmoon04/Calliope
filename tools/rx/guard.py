"""TB-D B4: the guard — no request above 100k input tokens.

Right before each request `run._loop` asks the guard for the whole request's size: on the Claude API
`messages.count_tokens` on the request as it will be sent (C3's conversion included); on OpenRouter an
estimate (the last answer's total input plus the new messages' characters at one token per two, or the
whole request's characters for a moment's first request) against a lower limit. Over 80k, or over the
send limit before the moment's restart, the loop sends nothing and returns `compact`; over the send
limit after the restart, `moment_budget`.
"""

from __future__ import annotations

import json

from .model import ModelError

COMPACT_AT = 80_000  # B4.2: compaction
SEND_LIMIT = 95_000  # B4.2: never sent above; `count_tokens` is an estimate, 5k of margin
ESTIMATED_LIMIT = 85_000  # B4.5: OpenRouter's estimated contract
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
        self.last_input: int | None = None  # the last answer's total input (OpenRouter's estimate)
        self.last_sent = 0  # how many messages that request held
        self.last_size = 0

    def new_moment(self) -> None:
        self.restarted = False
        self.last_input, self.last_sent, self.last_size = None, 0, 0

    def size(self, model, messages: list[dict], tools: list[dict],
             tool_choice: str | None = None) -> tuple[int, str]:  # fmt: skip
        """The request's input tokens and how they were found: `counted` or `estimated`."""

        if hasattr(model, "count"):
            try:
                return model.count(messages, tools, tool_choice), "counted"
            except ModelError as error:  # B4.1: a failed count, retried once, then estimated
                self.log.write({"type": "guard_count_failed", "error": str(error)[:300]})
        if self.last_input is not None and self.last_sent <= len(messages):
            new = _chars(messages[self.last_sent :], [])
            return self.last_input + new // CHARS_PER_TOKEN, "estimated"
        return _chars(messages, tools) // CHARS_PER_TOKEN, "estimated"

    def check(self, model, messages: list[dict], tools: list[dict]) -> str | None:
        """None to send; `compact` or `moment_budget` to send nothing (B4.2)."""

        size, how = self.size(model, messages, tools)
        limit = SEND_LIMIT if how == "counted" else ESTIMATED_LIMIT
        self.last_size = size
        verdict = None
        if size > limit:
            verdict = "moment_budget" if self.restarted else "compact"
        elif size > COMPACT_AT and not self.restarted:
            verdict = "compact"
        self.log.write({"type": "guard", "counted_tokens": size, "how": how, "limit": limit,
                        "restarted": self.restarted, "verdict": verdict or "send"})  # fmt: skip
        return verdict

    def answered(self, usage: dict, sent: int) -> None:
        """After an answer: its total input, for the next estimate."""

        self.last_input = usage.get("input_tokens")
        self.last_sent = sent

    def limit(self, how: str) -> int:
        return SEND_LIMIT if how == "counted" else ESTIMATED_LIMIT
