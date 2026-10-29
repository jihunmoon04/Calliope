"""Reservations of the result store and the searcher that holds them (PF-D §4.1, D3)."""

from __future__ import annotations

import threading
import time

import chess
from synthetic import IDENTITY, engine, synthetic

from calliope.facts import EngineError, EngineProfile, RootSpec
from calliope.facts.search import (
    EngineResultStore,
    ScriptedEngine,
    Searcher,
    SearchKind,
    search_bound_s,
    window_input,
)

PROFILE = EngineProfile()
INPUT = window_input(chess.Board(), [], 0)


class Gated(ScriptedEngine):
    """The synthetic engine whose searches wait for `gate`; `inside` is set as one begins."""

    def __init__(self, answer=None, fail: bool = False) -> None:
        super().__init__(IDENTITY, answer or synthetic())
        self.gate = threading.Event()
        self.inside = threading.Event()
        self.fail = fail

    def search(self, request):
        self.inside.set()
        assert self.gate.wait(30)
        if self.fail:
            self.calls.append(request)
            raise EngineError("engine process exited")
        return super().search(request)


def _key(port, store) -> str:
    return Searcher(port, store, PROFILE)._request(INPUT, SearchKind.SURVEY, None, None)[1]


def _holder(port, store, out: list) -> threading.Thread:
    def run() -> None:
        try:
            out.append(Searcher(port, store, PROFILE).search(INPUT, SearchKind.SURVEY))
        except EngineError as error:
            out.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    assert port.inside.wait(10)
    return thread


def test_the_bound_is_the_whole_search() -> None:
    assert search_bound_s(PROFILE) == 10 + 2 + 10
    assert Searcher(engine(), EngineResultStore(), PROFILE).wait_s == 23


def test_a_reservation_is_held_by_its_token_only() -> None:
    store = EngineResultStore()
    first = store.reserve("k")
    assert first is not None and store.reserve("k") is None and store.reserved("k")
    store.release("k", first)
    second = store.reserve("k")
    store.release("k", first)  # a late release of the old holder
    assert store.reserved("k") and store.reserve("k") is None
    store.release("k", second)
    assert not store.reserved("k")
    assert store.wait("k", 0.01)  # nothing reserved: no wait


def test_a_wait_times_out_while_the_holder_keeps_its_key() -> None:
    store = EngineResultStore()
    token = store.reserve("k")
    started = time.monotonic()
    assert store.wait("k", 0.2) is False and time.monotonic() - started >= 0.2
    assert store.reserved("k")  # nothing expired it
    store.release("k", token)


def test_of_several_waiters_woken_together_exactly_one_reserves() -> None:
    store = EngineResultStore()
    token = store.reserve("k")
    got, ready = [], threading.Barrier(5)

    def waiter() -> None:  # the one that reserves keeps it: the others see it reserved again
        ready.wait()
        got.append(store.reserve("k") if store.wait("k", 1) else None)

    threads = [threading.Thread(target=waiter) for _ in range(4)]
    for thread in threads:
        thread.start()
    ready.wait()
    time.sleep(0.1)
    store.release("k", token)
    for thread in threads:
        thread.join()
    assert sum(t is not None for t in got) == 1


def test_two_searchers_racing_for_one_key_make_one_call_and_the_waiter_finds_it_stored() -> None:
    port, store, out = Gated(), EngineResultStore(), []
    holder = _holder(port, store, out)
    waiter = threading.Thread(target=lambda: out.append(
        Searcher(port, store, PROFILE).search(INPUT, SearchKind.SURVEY)))  # fmt: skip
    waiter.start()
    time.sleep(0.2)
    port.gate.set()
    holder.join()
    waiter.join()
    assert len(port.calls) == 1 and out[0][0] is out[1][0]
    assert {out[0][1], out[1][1]} == {None, "store"} and store.waits == 1


def test_a_holder_that_fails_releases_and_the_waiter_searches() -> None:
    port, store, out = Gated(fail=True), EngineResultStore(), []
    holder = _holder(port, store, out)
    other = engine()
    waiter = threading.Thread(target=lambda: out.append(
        Searcher(other, store, PROFILE).search(INPUT, SearchKind.SURVEY)))  # fmt: skip
    waiter.start()
    time.sleep(0.2)
    port.gate.set()
    holder.join()
    waiter.join()
    assert isinstance(out[0], EngineError) and out[1][1] is None and len(other.calls) == 1
    assert not store.reserved(_key(port, store)) and len(store) == 1


def test_a_holders_irregular_answer_is_not_stored_and_the_waiter_searches() -> None:
    fen = chess.Board().fen()
    port, store, out = Gated(synthetic(irregular=frozenset({fen}))), EngineResultStore(), []
    holder = _holder(port, store, out)
    other = engine()
    waiter = threading.Thread(target=lambda: out.append(
        Searcher(other, store, PROFILE).search(INPUT, SearchKind.SURVEY)))  # fmt: skip
    waiter.start()
    time.sleep(0.2)
    port.gate.set()
    holder.join()
    waiter.join()
    assert not out[0][0].regular and len(other.calls) == 1 and len(store) == 1


def test_a_wait_past_its_bound_searches_without_a_reservation() -> None:
    port, store, out = Gated(), EngineResultStore(), []
    holder = _holder(port, store, out)
    other = engine()
    search, reused, _ = Searcher(other, store, PROFILE, wait_s=0.1).search(INPUT, SearchKind.SURVEY)
    assert reused is None and len(other.calls) == 1 and store.reserved(_key(port, store))
    port.gate.set()
    holder.join()
    assert out[0][0] is search  # the holder's put keeps the first answer
    assert not store.reserved(_key(port, store))


def test_cached_does_not_wait_for_a_reserved_key() -> None:
    port, store, out = Gated(), EngineResultStore(), []
    holder = _holder(port, store, out)
    started = time.monotonic()
    assert not Searcher(port, store, PROFILE).cached(INPUT, SearchKind.SURVEY)
    assert time.monotonic() - started < 1
    port.gate.set()
    holder.join()
    assert Searcher(port, store, PROFILE).cached(INPUT, SearchKind.SURVEY)


def test_search_ahead_outcomes() -> None:
    store = EngineResultStore()
    port = engine()
    ahead = Searcher(port, store, PROFILE)
    assert ahead.search_ahead(INPUT, SearchKind.SURVEY) == "ran"
    assert ahead.search_ahead(INPUT, SearchKind.SURVEY) == "stored"
    assert len(port.calls) == 1
    other = window_input(chess.Board(RootSpec().fen or chess.STARTING_FEN), ["e2e4"], 0)
    token = store.reserve(ahead._request(other, SearchKind.SURVEY, None, None)[1])
    assert ahead.search_ahead(other, SearchKind.SURVEY) == "reserved" and len(port.calls) == 1
    assert token is not None
    fen = chess.Board().fen()
    irregular = Searcher(engine(irregular=frozenset({fen})), EngineResultStore(), PROFILE)
    assert irregular.search_ahead(INPUT, SearchKind.SURVEY) == "irregular"
    assert len(irregular.store) == 0 and not irregular.store.reserved(_key(port, store))
