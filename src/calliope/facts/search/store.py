"""Result store and the per-session searcher (F4-D §5.3, §5.5)."""

from __future__ import annotations

import threading

from calliope.facts.search.inputs import EngineInput
from calliope.facts.search.port import EnginePort, SearchRequest
from calliope.facts.search.profile import EngineProfile
from calliope.facts.search.records import (
    EngineSearch,
    ReuseSource,
    SearchKind,
    normalize,
    request_key,
)


class EngineResultStore:
    """Regular searches by `SearchId`; thread-safe; shared by passing it to several engines."""

    def __init__(self) -> None:
        self._searches: dict[str, EngineSearch] = {}
        self._lock = threading.Lock()

    def get(self, search_id: str) -> EngineSearch | None:
        with self._lock:
            return self._searches.get(search_id)

    def put(self, search: EngineSearch) -> None:
        assert search.regular, "irregular searches never enter the store"
        with self._lock:
            self._searches.setdefault(search.search_id, search)

    def __len__(self) -> int:
        with self._lock:
            return len(self._searches)


class Searcher:
    """One session's access to the engine: store hits, in-session irregular reuse, engine calls.

    Irregular searches are cached per session: committed ones, plus the pending request's,
    which `discard` drops when a request is refused (F4-D §5.5).
    """

    def __init__(self, port: EnginePort, store: EngineResultStore, profile: EngineProfile) -> None:
        self.port = port
        self.store = store
        self.profile = profile
        self._committed: dict[str, EngineSearch] = {}
        self._pending: dict[str, EngineSearch] = {}
        self.engine_calls = 0

    def search(
        self,
        engine_input: EngineInput,
        kind: SearchKind,
        root_moves: tuple[str, ...] | None = None,
        multipv: int | None = None,
    ) -> tuple[EngineSearch, ReuseSource | None, int]:
        """The search for this question: (record, reuse source or None, elapsed ms)."""

        roots = None if root_moves is None else tuple(sorted(set(root_moves)))
        request = SearchRequest(
            input=engine_input,
            profile=self.profile,
            root_moves=roots,
            multipv=self.profile.multipv if multipv is None else multipv,
        )
        key = request_key(request, kind, self.port.identity)
        stored = self.store.get(key)
        if stored is not None:
            return stored, ReuseSource.STORE, 0
        cached = self._pending.get(key) or self._committed.get(key)
        if cached is not None:
            return cached, ReuseSource.SESSION, 0
        raw = self.port.search(request)
        self.engine_calls += 1
        search = normalize(raw, request, kind, self.port.identity)
        if search.regular:
            self.store.put(search)
        else:
            self._pending[key] = search  # keyed by the question, not by the irregular id
        return search, None, raw.elapsed_ms

    def commit(self) -> None:
        self._committed.update(self._pending)
        self._pending.clear()

    def discard(self) -> None:
        self._pending.clear()
