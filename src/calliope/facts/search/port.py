"""The engine boundary (F4-D §3.1): requests, raw output and the scripted test engine."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from calliope.facts.errors import EngineError
from calliope.facts.search.inputs import EngineInput
from calliope.facts.search.profile import EngineIdentity, EngineProfile


class Bound(StrEnum):
    EXACT = "exact"
    LOWER = "lower"
    UPPER = "upper"


class StoppedBy(StrEnum):
    DEPTH = "depth"
    TIME = "time"  # the adapter sent `stop` (F4-D §3.3)


@dataclass(frozen=True, slots=True)
class SearchRequest:
    input: EngineInput
    profile: EngineProfile
    root_moves: tuple[str, ...] | None  # sorted as strings; None = unrestricted
    multipv: int


@dataclass(frozen=True, slots=True)
class RawLine:
    """One rank's last `info` line, exactly as printed (side-to-move view)."""

    multipv: int
    depth: int
    seldepth: int
    score: tuple[str, int]  # ("cp", n) | ("mate", n)
    bound: Bound
    wdl: tuple[int, int, int] | None
    nodes: int
    tbhits: int
    pv: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RawSearch:
    lines: tuple[RawLine, ...]  # by rank
    stopped_by: StoppedBy
    elapsed_ms: int  # from `go` to `bestmove`


class EnginePort(Protocol):
    identity: EngineIdentity

    def search(self, request: SearchRequest) -> RawSearch: ...

    def close(self) -> None: ...


class ScriptedEngine:
    """Answers `SearchRequest`s from a table (or a function) and counts calls (F4-D §3.1).

    Tests tape `RawSearch` values, never normalized records (F4D-N4).
    """

    def __init__(
        self,
        identity: EngineIdentity,
        answers: Mapping[SearchRequest, RawSearch] | Callable[[SearchRequest], RawSearch],
    ) -> None:
        self.identity = identity
        self._answers = answers
        self.calls: list[SearchRequest] = []
        self._lock = threading.Lock()

    def search(self, request: SearchRequest) -> RawSearch:
        with self._lock:
            self.calls.append(request)
            if callable(self._answers):
                return self._answers(request)
            try:
                return self._answers[request]
            except KeyError:
                raise EngineError(f"no scripted answer for {request}") from None

    def close(self) -> None:
        pass
