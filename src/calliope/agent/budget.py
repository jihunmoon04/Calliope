"""The budget (AG-D §3.5, AG4-D §3): a local load limit of the process over a rolling window.

Uncached analyses and engine searches are counted as charges stamped with the clock; a charge older
than `window_seconds` no longer counts (§3.2). The budget limits the engine work one process takes;
it does not count an agent's use across processes or hosts (O2). Per-call bounds are separate
fields, and a call is admitted only if both hold.

Searches are metered at the engine port (review R3): the server's engine slot starts every engine
wrapped in a `MeteredPort` around the one `Meter`, so a restart keeps the count. A search is taken
from the meter before it reaches the engine and is never refunded; a search an engine result store
answers never reaches the port and is free. With no search left the port raises
`SearchBudgetExhausted` — not a fact-engine error, so neither the fact engine nor `analyse_ply`
turns it into a refusal or a restart: the work in progress stops.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Self


class BudgetError(Exception):
    """A request the budget refuses (a tool error naming the limit, what is left and, when room
    comes back, `retry_after_seconds`)."""

    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class SearchBudgetExhausted(Exception):
    """The meter has no search left: raised by `MeteredPort.search` before the engine is asked."""


@dataclass(frozen=True, slots=True)
class Limits:
    """AG4-D §3.1 (O2, O3: owner, 2026-10-15); each is a server option."""

    window_seconds: float = 900
    max_uncached_plies: int = 16  # per window
    max_searches: int = 40  # per window
    max_uncached_plies_per_call: int = 16
    max_nodes_per_tree: int = 2000  # one game's facts tree
    max_nodes_total: int = 20000  # all of the process's trees, facts and search
    max_open_games: int = 16
    max_store_results: int = 4000
    max_handles: int = 20000
    max_analyses: int = 128
    # PF-D §2, §3: the analyses' searches and POSITION records, kept for the process
    max_analysis_searches: int = 20_000
    max_position_records: int = 40_000
    # AG6-D §8 (owner Q4, 2026-10-17): `analyze_game`'s jobs, charged apart from the above
    job_window_seconds: float = 3600
    max_job_plies: int = 600  # plies of one job (the game path's limit)
    max_job_plies_per_window: int = 400  # plies analysed by jobs (cache hits free)
    max_queued_jobs: int = 4  # beside the one that runs

    def __post_init__(self) -> None:
        """AG4-D AM1: a budget amount may be 0 (none allowed); the window is longer than 0
        seconds; a memory limit is at least 1, room for the call's own item."""

        for name in ("window_seconds", "job_window_seconds"):
            window = getattr(self, name)
            try:  # a boolean is not a number of seconds; an integer too large for a float overflows
                finite = type(window) in (int, float) and math.isfinite(window)
            except OverflowError:
                finite = False
            if not (finite and window > 0):
                raise ValueError(f"{name} is a finite number of seconds above 0, not "
                                 f"{window!r}")  # fmt: skip
        for name in BUDGET_AMOUNTS + MEMORY_LIMITS:
            value, least = getattr(self, name), 0 if name in BUDGET_AMOUNTS else 1
            if type(value) is not int or value < least:
                raise ValueError(f"{name} is an integer of at least {least}, not {value!r}")


BUDGET_AMOUNTS = ("max_uncached_plies", "max_searches", "max_uncached_plies_per_call",
                  "max_job_plies_per_window", "max_queued_jobs")  # fmt: skip
MEMORY_LIMITS = ("max_nodes_per_tree", "max_nodes_total", "max_open_games", "max_store_results",
                 "max_handles", "max_analyses", "max_job_plies", "max_analysis_searches",
                 "max_position_records")  # fmt: skip


class Window:
    """Charges within the last `seconds`, oldest first."""

    def __init__(self, limit: int, seconds: float, clock: Callable[[], float]) -> None:
        self.limit = limit
        self.seconds = seconds
        self.clock = clock
        self._charges: deque[float] = deque()

    def _expire(self) -> float:
        now = self.clock()
        while self._charges and now - self._charges[0] >= self.seconds:
            self._charges.popleft()
        return now

    @property
    def used(self) -> int:
        self._expire()
        return len(self._charges)

    @property
    def left(self) -> int:
        return max(self.limit - self.used, 0)

    def charge(self) -> None:
        self._charges.append(self._expire())

    def retry_after(self, n: int) -> int | None:
        """Seconds until `n` units fit (review C3): the `need`-th oldest charge must expire, with
        `need = n - left`. None when `n` exceeds the limit itself; 0 when they fit now."""

        if n > self.limit:
            return None
        now = self._expire()
        need = n - max(self.limit - len(self._charges), 0)
        if need <= 0:
            return 0
        return max(math.ceil(self._charges[need - 1] + self.seconds - now), 1)


class Meter:
    """Engine searches over the window: every search that reached the port is a charge."""

    def __init__(self, window: Window) -> None:
        self.window = window
        self.refused = 0  # searches refused for want of budget
        self.total = 0  # every search taken, for the result store's count

    @property
    def limit(self) -> int:
        return self.window.limit

    @limit.setter
    def limit(self, value: int) -> None:
        self.window.limit = value

    @property
    def used(self) -> int:
        return self.window.used

    @property
    def left(self) -> int:
        return self.window.left

    def take(self) -> None:
        if self.window.left < 1:
            self.refused += 1
            retry = self.window.retry_after(1)
            raise SearchBudgetExhausted(
                f"the {self.limit} engine searches of the {self.window.seconds:g}-second window "
                f"are used (retry_after_seconds: {retry})"
            )
        self.window.charge()
        self.total += 1


class MeteredPort:
    """An `EnginePort` that takes one search from the meter before each call to `inner`."""

    def __init__(self, inner, meter: Meter) -> None:
        self.inner = inner
        self.meter = meter

    @property
    def identity(self):
        return self.inner.identity

    def search(self, request):
        self.meter.take()  # charged before the engine is asked; a failed search stays charged
        return self.inner.search(request)

    def close(self) -> None:
        self.inner.close()


def analysis_bound(target: int) -> int:
    """The most engine searches one uncached analysis of ply `target` can ask (AG-D §3.5): round 0
    surveys and compares the window's at most `min(t, 2) + 1` nodes, and `max_extra_searches`
    (4) caps the later rounds."""

    return 2 * (min(target, 2) + 1) + 4


class Budget:
    def __init__(self, limits: Limits, clock: Callable[[], float] = time.monotonic) -> None:
        self.limits = limits
        seconds = limits.window_seconds
        self.uncached = Window(limits.max_uncached_plies, seconds, clock)
        self.meter = Meter(Window(limits.max_searches, seconds, clock))

    def left(self) -> dict:
        return {
            "uncached_plies": self.uncached.left,
            "searches": self.meter.left,
            "window_seconds": self.limits.window_seconds,
        }

    def _refuse(self, what: str, window: Window, n: int) -> BudgetError:
        retry = window.retry_after(n)
        if retry is None:
            return BudgetError(f"the budget refuses {what}: it is more than the limit "
                               f"{window.limit} per {window.seconds:g} seconds")  # fmt: skip
        return BudgetError(f"the budget refuses {what}; left: {self.left()}; "
                           f"retry_after_seconds: {retry}", retry)  # fmt: skip

    def admit_analyses(self, targets: list[int]) -> None:
        """Before uncached analyses: the per-call bound, a ply each in the window, and the first
        one's search bound."""

        if not targets:
            return
        if len(targets) > self.limits.max_uncached_plies_per_call:
            raise BudgetError(f"the budget refuses {len(targets)} uncached analyses in one call: "
                              f"at most {self.limits.max_uncached_plies_per_call}")  # fmt: skip
        if self.uncached.left < len(targets):
            raise self._refuse(f"{len(targets)} uncached analyses", self.uncached, len(targets))
        bound = analysis_bound(targets[0])
        if self.meter.left < bound:
            raise self._refuse(f"an analysis of ply {targets[0]} (up to {bound} searches)",
                               self.meter.window, bound)  # fmt: skip

    def admit_analysis(self, target: int) -> None:
        """Before one uncached analysis, which is charged as it is admitted."""

        self.admit_analyses([target])
        self.uncached.charge()

    def admit_search(self) -> None:
        if self.meter.left < 1:
            raise self._refuse("a search", self.meter.window, 1)


class MeteredSlot:
    """The process's one engine seen through one meter (AG6-D §4.4): the raw slot's port wrapped in
    a `MeteredPort` of this meter, made once per raw port and made again after a restart. The
    tools see it through AG4-D's meter, `analyze_game`'s jobs through theirs."""

    def __init__(self, raw, meter: Meter) -> None:
        self.raw = raw  # the server's `EngineSlot`, shared by every meter
        self.meter = meter
        self._port: MeteredPort | None = None

    @property
    def port(self) -> MeteredPort:
        inner = self.raw.port
        if self._port is None or self._port.inner is not inner:
            self._port = MeteredPort(inner, self.meter)
        return self._port

    def current(self) -> MeteredPort | None:
        """This meter's port of the running engine, or None; never starts the engine."""

        inner = self.raw.current
        return self._port if self._port is not None and self._port.inner is inner else None

    def restart(self) -> MeteredPort:
        self.raw.restart()
        return self.port

    def close(self) -> None:
        self.raw.close()


class EngineBusy(Exception):
    """The engine lock is held or queued for: a caller that must not wait (AG8-D §5) answers
    without the engine."""


class EngineLock:
    """The engine lock (AG6-D §4.3): first come, first served, so the job worker takes it again
    only after every caller queued before it has had it; re-entrant for the thread that holds it
    (an analysis reads the engine's build within its own hold)."""

    def __init__(self) -> None:
        self._turns = threading.Condition()
        self._next = 0  # the next ticket to give
        self._serving = 0  # the ticket that may hold the lock
        self._owner: int | None = None
        self._depth = 0

    def __enter__(self) -> Self:
        me = threading.get_ident()
        with self._turns:
            if self._owner == me:
                self._depth += 1
                return self
            ticket = self._next
            self._next += 1
            while ticket != self._serving:
                self._turns.wait()
            self._owner, self._depth = me, 1
        return self

    def try_enter(self) -> bool:
        """Take the lock only if no one holds it or waits for it (or this thread holds it)."""

        me = threading.get_ident()
        with self._turns:
            if self._owner == me:
                self._depth += 1
                return True
            if self._owner is None and self._next == self._serving:
                self._next += 1
                self._owner, self._depth = me, 1
                return True
            return False

    @contextmanager
    def now(self):
        """The lock without waiting: `EngineBusy` when it is held or queued for (AG8-D §5)."""

        if not self.try_enter():
            raise EngineBusy("the engine is busy")
        try:
            yield self
        finally:
            self.__exit__(None, None, None)

    def __exit__(self, *exc) -> None:
        with self._turns:
            self._depth -= 1
            if self._depth == 0:
                self._owner = None
                self._serving += 1
                self._turns.notify_all()

    def waiting(self) -> int:
        """Callers queued behind the holder (the worker yields to them, §4.3)."""

        with self._turns:
            return self._next - self._serving - (1 if self._owner is not None else 0)
