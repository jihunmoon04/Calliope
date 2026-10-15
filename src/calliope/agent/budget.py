"""The session budget (AG-D §3.5): uncached analyses, engine searches and tree nodes.

Searches are metered at the engine port (review R3): the session's engine slot starts every
engine wrapped in a `MeteredPort` around the session's one `Meter`, so a restart keeps the count.
A search is taken from the meter before it reaches the engine and is never refunded; a search an
engine result store answers never reaches the port and is free. With no search left the port
raises `SearchBudgetExhausted` — not a fact-engine error, so neither the fact engine nor
`analyse_ply` turns it into a refusal or a restart: the work in progress stops.
"""

from __future__ import annotations

from dataclasses import dataclass


class BudgetError(Exception):
    """A request the session's budget refuses (a tool error naming the limit and what is left)."""


class SearchBudgetExhausted(Exception):
    """The meter has no search left: raised by `MeteredPort.search` before the engine is asked."""


@dataclass(frozen=True, slots=True)
class Limits:
    """AG-D §3.5 and Q2 (owner, 2026-10-15): per session."""

    max_uncached_plies: int = 16
    max_searches: int = 40
    max_nodes: int = 2000


class Meter:
    """Engine searches of one session: `used` counts every search that reached the port."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0
        self.refused = 0  # searches refused for want of budget

    @property
    def left(self) -> int:
        return max(self.limit - self.used, 0)

    def take(self) -> None:
        if self.used >= self.limit:
            self.refused += 1
            raise SearchBudgetExhausted(f"the session's {self.limit} engine searches are used")
        self.used += 1


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
    def __init__(self, limits: Limits) -> None:
        self.limits = limits
        self.meter = Meter(limits.max_searches)
        self.uncached = 0
        self.nodes = 0

    def left(self) -> dict:
        return {
            "uncached_plies": self.limits.max_uncached_plies - self.uncached,
            "searches": self.meter.left,
            "nodes": self.limits.max_nodes - self.nodes,
        }

    def _refuse(self, what: str) -> BudgetError:
        return BudgetError(f"the session budget refuses {what}; left: {self.left()}")

    def admit_analyses(self, targets: list[int]) -> None:
        """Before uncached analyses: a ply each, and the first one's search bound."""

        if not targets:
            return
        if self.uncached + len(targets) > self.limits.max_uncached_plies:
            raise self._refuse(f"{len(targets)} uncached analyses")
        if self.meter.left < analysis_bound(targets[0]):
            raise self._refuse(f"an analysis of ply {targets[0]} (up to "
                               f"{analysis_bound(targets[0])} searches)")  # fmt: skip

    def admit_analysis(self, target: int) -> None:
        """Before one uncached analysis, which is charged as it is admitted."""

        self.admit_analyses([target])
        self.uncached += 1

    def admit_search(self) -> None:
        if self.meter.left < 1:
            raise self._refuse("a search")

    def admit_nodes(self, count: int) -> None:
        if self.nodes + count > self.limits.max_nodes:
            raise self._refuse(f"{count} new nodes")

    def charge_nodes(self, count: int) -> None:
        self.nodes += count
