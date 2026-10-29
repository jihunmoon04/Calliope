"""POSITION records kept per process (PF-D §3, D2).

A POSITION family computes from a board rebuilt from its `PositionKey` alone and requires only
POSITION records of the same key (F2-D §1.5, §9), so its record is the same in every tree. The fact
engine still resolves and stores every requirement and every record in the tree as it always has;
only the family's `compute` call is answered from here when the record is kept.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable, Sequence
from typing import Any

from calliope.facts.errors import InvalidRequestError
from calliope.facts.families.base import FactFamily, FamilyContext
from calliope.facts.keys import PositionKey
from calliope.facts.storage import FamilyEntry, family_entries


class PositionRecords:
    """POSITION records by family name, family version and key; thread-safe; the least recently
    used past `max_entries` records is dropped. Bound to the families of the first fact engine
    given it: an engine with other families is refused."""

    def __init__(self, max_entries: int) -> None:
        if type(max_entries) is not int or max_entries < 1:
            raise ValueError(f"max_entries is an integer of at least 1, not {max_entries!r}")
        self.max_entries = max_entries
        self.hits = 0
        self.misses = 0
        self._records: OrderedDict[tuple[str, str, PositionKey], Any] = OrderedDict()
        self._families: tuple[FamilyEntry, ...] | None = None
        self._lock = threading.Lock()

    def bind(self, families: Sequence[FactFamily]) -> None:
        entries = family_entries(families)
        with self._lock:
            if self._families is None:
                self._families = entries
            elif entries != self._families:
                raise InvalidRequestError(
                    "these POSITION records were kept for another family registry"
                )

    def compute(
        self, family: FactFamily, key: PositionKey, context: Callable[[], FamilyContext]
    ) -> Any:
        """The kept record, or `family.compute(context())` kept (the first, if two raced)."""

        memo_key = (family.name, family.version, key)
        with self._lock:
            record = self._records.get(memo_key)
            if record is not None:
                self._records.move_to_end(memo_key)
                self.hits += 1
                return record
        record = family.compute(context())  # outside the lock: trees build in parallel
        with self._lock:
            self.misses += 1
            record = self._records.setdefault(memo_key, record)
            self._records.move_to_end(memo_key)
            while len(self._records) > self.max_entries:
                self._records.popitem(last=False)
            return record

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)
