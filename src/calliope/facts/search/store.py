"""Result store and the per-session searcher (F4-D §5.3, §5.5)."""

from __future__ import annotations

import threading

from calliope.facts.errors import InvalidRequestError
from calliope.facts.search.inputs import EngineInput, window_end
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

    def put(self, search: EngineSearch) -> EngineSearch:
        """Store a regular search; returns the stored record (the first one, if two raced)."""

        assert search.regular, "irregular searches never enter the store"
        with self._lock:
            return self._searches.setdefault(search.search_id, search)

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
        self.engine_calls = 0  # committed requests plus the pending one
        self._committed_calls = 0

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
        _check_roots(engine_input, roots)
        key = request_key(request, kind, self.port.identity)
        # the session's own answer first: one session never holds two results for one
        # question (A0 §7.7), even if another session stored a regular one meanwhile
        cached = self._pending.get(key) or self._committed.get(key)
        if cached is not None:
            return cached, ReuseSource.SESSION, 0
        stored = self.store.get(key)
        if stored is not None:
            return stored, ReuseSource.STORE, 0
        raw = self.port.search(request)
        self.engine_calls += 1
        search = normalize(raw, request, kind, self.port.identity)
        if search.regular:
            search = self.store.put(search)
        else:
            self._pending[key] = search  # keyed by the question, not by the irregular id
        return search, None, raw.elapsed_ms

    def commit(self) -> None:
        self._committed.update(self._pending)
        self._pending.clear()
        self._committed_calls = self.engine_calls

    def discard(self) -> None:
        """A refused request: its irregular searches and its engine calls do not count."""

        self._pending.clear()
        self.engine_calls = self._committed_calls


def _check_roots(engine_input: EngineInput, roots: tuple[str, ...] | None) -> None:
    """Root moves are validated before any engine call (F4a-N4)."""

    if roots is None:
        return
    legal = {m.uci() for m in window_end(engine_input).legal_moves}
    if not roots or not set(roots) <= legal:
        raise InvalidRequestError(f"root moves {roots} are empty or not all legal")
