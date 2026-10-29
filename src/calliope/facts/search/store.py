"""Result store and the per-session searcher (F4-D §5.3, §5.5; reservations: PF-D §4.1)."""

from __future__ import annotations

import threading
import time
from enum import StrEnum

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
from calliope.facts.search.uci import search_bound_s


class PrefetchOutcome(StrEnum):
    """What a survey asked ahead did (PF-D §4.2)."""

    STORED = "stored"  # the store already held the answer
    RESERVED = "reserved"  # another searcher was asking it: not waited for
    RAN = "ran"  # searched and stored
    IRREGULAR = "irregular"  # searched; an irregular answer is dropped
    NOT_SEARCHED = "not_searched"  # the fact engine would not search the position


class EngineResultStore:
    """Regular searches by `SearchId`; thread-safe; shared by passing it to several engines.

    With `max_entries`, the least recently used search past the count is dropped (PF-D §2): an
    evicted search is asked again when needed. A key being searched is reserved by its searcher
    (PF-D §4.1): the reservation holds a token, and only its holder's `release` ends it."""

    def __init__(self, max_entries: int | None = None) -> None:
        if max_entries is not None and (type(max_entries) is not int or max_entries < 1):
            raise ValueError(f"max_entries is an integer of at least 1, not {max_entries!r}")
        self.max_entries = max_entries
        self._searches: dict[str, EngineSearch] = {}  # least recently used first
        self._lock = threading.Lock()
        self._released = threading.Condition(self._lock)
        self._reserved: dict[str, object] = {}  # key → its holder's token
        self.waits = 0  # waits for another searcher's answer, and their seconds
        self.wait_seconds = 0.0

    def get(self, search_id: str) -> EngineSearch | None:
        with self._lock:
            search = self._searches.pop(search_id, None)
            if search is not None:
                self._searches[search_id] = search  # now the most recent
            return search

    def put(self, search: EngineSearch) -> EngineSearch:
        """Store a regular search; returns the stored record (the first one, if two raced)."""

        assert search.regular, "irregular searches never enter the store"
        with self._lock:
            stored = self._searches.pop(search.search_id, search)
            self._searches[search.search_id] = stored  # now the most recent
            if self.max_entries is not None:
                while len(self._searches) > self.max_entries:
                    del self._searches[next(iter(self._searches))]
            return stored

    def reserve(self, search_id: str) -> object | None:
        """A token for the key when it is neither stored nor reserved, else None."""

        with self._lock:
            if search_id in self._searches or search_id in self._reserved:
                return None
            token = self._reserved[search_id] = object()
            return token

    def release(self, search_id: str, token: object) -> None:
        """End the reservation if `token` still holds it (a late release ends no other), and wake
        the key's waiters."""

        with self._lock:
            if self._reserved.get(search_id) is token:
                del self._reserved[search_id]
                self._released.notify_all()

    def wait(self, search_id: str, timeout_s: float) -> bool:
        """Block until the key is not reserved (True) or the timeout passes (False)."""

        started = time.monotonic()
        with self._lock:
            ended = self._released.wait_for(lambda: search_id not in self._reserved, timeout_s)
            self.waits += 1
            self.wait_seconds += time.monotonic() - started
            return ended

    def reserved(self, search_id: str) -> bool:
        with self._lock:
            return search_id in self._reserved

    def __len__(self) -> int:
        with self._lock:
            return len(self._searches)


class Searcher:
    """One session's access to the engine: store hits, in-session irregular reuse, engine calls.

    Irregular searches are cached per session: committed ones, plus the pending request's,
    which `discard` drops when a request is refused (F4-D §5.5). An engine search holds the
    store's reservation of its key; a key another searcher holds is waited for, at most `wait_s`
    (default: the adapter's bound on a search, plus 1 s for the release), after which it is
    searched without a reservation — only wasted work, the first answer stored is kept (PF-D §4.1).
    """

    def __init__(
        self,
        port: EnginePort,
        store: EngineResultStore,
        profile: EngineProfile,
        wait_s: float | None = None,
    ) -> None:
        self.port = port
        self.store = store
        self.profile = profile
        self.wait_s = search_bound_s(profile) + 1 if wait_s is None else wait_s
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

        request, key = self._request(engine_input, kind, root_moves, multipv)
        _check_roots(engine_input, request.root_moves)
        # the session's own answer first: one session never holds two results for one
        # question (A0 §7.7), even if another session stored a regular one meanwhile
        cached = self._pending.get(key) or self._committed.get(key)
        if cached is not None:
            return cached, ReuseSource.SESSION, 0
        token = None
        try:  # the reservation is taken inside: an interrupt never leaves it held (review N3)
            while True:
                stored = self.store.get(key)
                if stored is not None:
                    return stored, ReuseSource.STORE, 0
                token = self.store.reserve(key)
                if token is not None or not self.store.wait(key, self.wait_s):
                    break  # reserved; or the holder overran its bound: search without one
            raw = self.port.search(request)
            self.engine_calls += 1
            search = normalize(raw, request, kind, self.port.identity)
            if search.regular:
                search = self.store.put(search)
            else:
                self._pending[key] = search  # keyed by the question, not by the irregular id
        finally:
            if token is not None:
                self.store.release(key, token)  # after the put: a woken waiter finds it
        return search, None, raw.elapsed_ms

    def search_ahead(self, engine_input: EngineInput, kind: SearchKind) -> PrefetchOutcome:
        """Ask a question before the analysis does, into the store only (PF-D §4.2): a stored or
        reserved key is not searched, and nothing is waited for."""

        request, key = self._request(engine_input, kind, None, None)
        if self.store.get(key) is not None:
            return PrefetchOutcome.STORED
        token = None
        try:
            token = self.store.reserve(key)
            if token is None:
                stored = self.store.get(key) is not None
                return PrefetchOutcome.STORED if stored else PrefetchOutcome.RESERVED
            raw = self.port.search(request)
            search = normalize(raw, request, kind, self.port.identity)
            if not search.regular:
                return PrefetchOutcome.IRREGULAR
            self.store.put(search)
            return PrefetchOutcome.RAN
        finally:
            if token is not None:
                self.store.release(key, token)

    def _request(
        self,
        engine_input: EngineInput,
        kind: SearchKind,
        root_moves: tuple[str, ...] | None,
        multipv: int | None,
    ) -> tuple[SearchRequest, str]:
        roots = None if root_moves is None else tuple(sorted(set(root_moves)))
        request = SearchRequest(
            input=engine_input,
            profile=self.profile,
            root_moves=roots,
            multipv=self.profile.multipv if multipv is None else multipv,
        )
        return request, request_key(request, kind, self.port.identity)

    def cached(
        self,
        engine_input: EngineInput,
        kind: SearchKind,
        root_moves: tuple[str, ...] | None = None,
        multipv: int | None = None,
    ) -> bool:
        """Would `search` answer without an engine call (session cache or store)? Never waits: a
        reserved key is a miss (PF-D §4.1)."""

        _, key = self._request(engine_input, kind, root_moves, multipv)
        return key in self._pending or key in self._committed or self.store.get(key) is not None

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
