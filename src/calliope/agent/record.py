"""The run record's tools layer (RX0-D §4, RX1-D §2) and `evidence_identity` (RX0-D §5).

Recording is off unless the server is started with `CALLIOPE_RUN_RECORDS`: the session then holds a
`Recorder`, and every MCP tool call writes one `call` line, followed by the `handle` and `submission`
lines its work produced, each with the call's `call_id` (RX1-D §2, review B1, B2). Resource and
prompt reads are `read` lines (review N3). Nothing here changes an answer; a write error stops
recording and never fails a tool call.
"""

from __future__ import annotations

import contextvars
import functools
import hashlib
import inspect
import json
import logging
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from calliope.server import canonical

CAP_BYTES = 32 * 1024 * 1024  # answers held in full under this, a run (RX0-D §4.2)
LINE_KEY_PLIES = 8  # RX0-D §5: a line's FEN and its first eight PV plies

_log = logging.getLogger(__name__)
_CALL: contextvars.ContextVar[_Call | None] = contextvars.ContextVar(
    "calliope_rx_call", default=None
)


# -- evidence_identity (RX0-D §5) ------------------------------------------------------------------


def identity_fields(kind: str, game: str, source: dict, address: dict) -> list:
    """The list RX0-D §5 hashes: the handle's binding without what belongs to one process (the
    facts tree's `rev`, a board item's `bundle`)."""

    origin = source.get("kind")
    if kind in ("judgement", "claim"):
        return [kind, game, source.get("path"), source.get("tree"), source.get("graph"),
                source.get("build"), address]  # fmt: skip
    if kind == "search_line":
        if origin == "analysis":  # served by `ply` or `judge_move` (review B2)
            return [kind, "analysis", game, source.get("path"), source.get("tree"),
                    source.get("graph"), source.get("build"), address.get("judgement"),
                    address.get("rank")]  # fmt: skip
        return [kind, "search", game, source.get("position"), source.get("lines"),
                address.get("rank")]  # fmt: skip
    if kind == "board_item":
        return [kind, game, source.get("subject"), address.get("propositions")]
    if kind == "fact":
        return [kind, game, address.get("position"), address.get("family")]
    if kind == "explored_line":
        return [kind, game, address.get("from"), address.get("moves"), address.get("by")]
    return [kind, game, {k: v for k, v in source.items() if k != "rev"}, address]


def identity(kind: str, game: str, source: dict, address: dict) -> str:
    return hashlib.sha256(canonical(identity_fields(kind, game, source, address))).hexdigest()


def line_key(fen: str, pv: list[str]) -> str:
    """A line by its position and its first eight PV plies in UCI, whatever served it."""

    return hashlib.sha256(canonical([fen, list(pv)[:LINE_KEY_PLIES]])).hexdigest()


# -- the recorder -----------------------------------------------------------------------------------


@dataclass
class _Call:
    call_id: int
    events: list[dict] = field(default_factory=list)


def new_run_id() -> str:
    """A ULID: 48 bits of milliseconds and 80 random bits, Crockford base 32."""

    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    value = (int(time.time() * 1000) << 80) | secrets.randbits(80)
    return "".join(alphabet[(value >> shift) & 31] for shift in range(125, -1, -5))


class Recorder:
    """One run's `tools.jsonl`. Lines carry `run`, `seq`, `t` and `type`."""

    def __init__(self, directory: Path, run_id: str | None = None, cap: int = CAP_BYTES) -> None:
        self.run_id = run_id or new_run_id()
        self.path = Path(directory) / self.run_id / "tools.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.cap = cap
        self._file = open(self.path, "a", encoding="utf-8")  # noqa: SIM115 (held for the run)
        self._lock = threading.Lock()
        self._seq = 0
        self._calls = 0
        self._answer_bytes = 0
        self._started = time.monotonic()
        self._handles: set[str] = set()
        self._counts = {"calls": 0, "reads": 0, "handles": 0, "submissions": 0}
        self._capped: list[int] = []
        self.failed = False

    # lines

    def _write(self, line: dict) -> None:
        if self.failed:
            return
        with self._lock:
            self._seq += 1
            full = {"run": self.run_id, "seq": self._seq,
                    "t": round(time.monotonic() - self._started, 3)} | line  # fmt: skip
            try:
                self._file.write(json.dumps(full, ensure_ascii=False, default=str) + "\n")
                self._file.flush()
            except (OSError, TypeError, ValueError) as error:  # recording stops; tools go on
                self.failed = True
                _log.error("run record %s: writing stopped: %s", self.run_id, error)

    def start(self, info: dict) -> None:
        self._write({"type": "start"} | info)

    def end(self, reason: str = "closed") -> None:
        self._write({"type": "end", "reason": reason, "counts": dict(self._counts),
                     "capped_calls": list(self._capped)})  # fmt: skip
        try:
            self._file.close()
        except OSError:
            pass

    def _event(self, line: dict) -> None:
        """A handle or submission: kept with the open call, or written at once (`call_id: null`)."""

        call = _CALL.get()
        if call is None:
            self._write(line | {"call_id": None})
        else:
            call.events.append(line)

    def handle(self, entry) -> None:
        if entry.ref in self._handles:
            return
        self._handles.add(entry.ref)
        self._counts["handles"] += 1
        self._event({"type": "handle", "ref": entry.ref, "kind": entry.kind, "game": entry.game,
                     "source": entry.source, "address": entry.address,
                     "identity": identity(entry.kind, entry.game, entry.source, entry.address)})  # fmt: skip

    def submission(self, subjects: list[dict]) -> None:
        self._counts["submissions"] += 1
        self._event({"type": "submission", "subjects": subjects})

    # the boundary (RX1-D §2)

    def _answer(self, result: Any) -> dict:
        try:
            value = result.model_dump(mode="json", by_alias=True, exclude_none=True)
        except AttributeError:
            value = result
        text = json.dumps(value, ensure_ascii=False, default=str)
        size = len(text.encode("utf-8"))
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        out = {"answer_sha256": digest, "answer_bytes": size}
        if self._answer_bytes + size > self.cap:
            return out | {"capped": True}
        self._answer_bytes += size
        return out | {"answer": value}

    def wrap(self, name: str, kind: str = "call"):
        """The decorator on one registered tool (`kind: call`) or a resource or prompt read."""

        def enter():
            if kind != "call":
                return None, None
            self._calls += 1
            call = _Call(self._calls)
            return call, _CALL.set(call)

        def leave(call, token, kwargs, began, outcome):
            arguments = {k: v for k, v in kwargs.items() if k != "ctx"}
            ms = round((time.monotonic() - began) * 1000)
            if call is None:
                self._counts["reads"] += 1
                self._write({"type": "read", "kind": kind, "name": name,
                             "arguments": arguments, "ms": ms} | outcome)  # fmt: skip
                return
            _CALL.reset(token)
            self._counts["calls"] += 1
            if outcome.get("capped"):
                self._capped.append(call.call_id)
            self._write({"type": "call", "call_id": call.call_id, "tool": name,
                         "arguments": arguments, "ms": ms} | outcome)  # fmt: skip
            for event in call.events:  # after the call, in order (review B2)
                self._write(event | {"call_id": call.call_id})

        def decorate(fn):
            if inspect.iscoroutinefunction(fn):

                @functools.wraps(fn)
                async def recorded(*args, **kwargs):
                    call, token = enter()
                    began, outcome = time.monotonic(), {}
                    try:
                        result = await fn(*args, **kwargs)
                        outcome = self._answer(result)
                        return result
                    except BaseException as error:
                        outcome = {"error": f"{type(error).__name__}: {error}"}
                        raise
                    finally:
                        leave(call, token, kwargs, began, outcome)

                return recorded

            @functools.wraps(fn)
            def recorded_sync(*args, **kwargs):
                call, token = enter()
                began, outcome = time.monotonic(), {}
                try:
                    result = fn(*args, **kwargs)
                    outcome = self._answer(result)
                    return result
                except BaseException as error:
                    outcome = {"error": f"{type(error).__name__}: {error}"}
                    raise
                finally:
                    leave(call, token, kwargs, began, outcome)

            return recorded_sync

        return decorate


def recorder_from_environment() -> Recorder | None:
    """`CALLIOPE_RUN_RECORDS` set: a recorder under it, named by `CALLIOPE_RUN_ID` or a new id."""

    directory = os.environ.get("CALLIOPE_RUN_RECORDS")
    if not directory:
        return None
    return Recorder(Path(directory), os.environ.get("CALLIOPE_RUN_ID") or None)
