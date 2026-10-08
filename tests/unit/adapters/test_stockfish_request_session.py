"""StockfishAdapter request-wide sessions: fresh game token, exclusivity, exception safety.

The fake engine records the ``game`` token python-chess uses to decide ``ucinewgame``: a token
change is exactly a new-game boundary, an unchanged token is the same game.
"""

import threading
import time

import pytest
from test_stockfish_adapter import SETTINGS, START, FakeEngine, make

from calliope.errors import EngineClosedError, EngineConfigurationError


def games(engine):
    return [call["game"] for call in engine.calls]


def test_fresh_token_per_session_and_same_token_within():
    adapter, engine = make()
    with adapter.request_session():
        adapter.analyze(START, SETTINGS)
        adapter.analyze(START, SETTINGS)
    with adapter.request_session():
        adapter.analyze(START, SETTINGS)
    first, second, third = games(engine)
    assert first is not None and first is second  # no mid-request new game
    assert third is not None and third is not first  # the next request starts a new game


def test_every_session_gets_a_distinct_token():
    adapter, engine = make()
    for _ in range(5):
        with adapter.request_session():
            adapter.analyze(START, SETTINGS)
    tokens = games(engine)
    assert len({id(t) for t in tokens}) == 5 and len(set(tokens)) == 5


def test_bare_analyze_keeps_the_single_call_contract():
    adapter, engine = make()
    adapter.analyze(START, SETTINGS)
    adapter.analyze(START, SETTINGS)
    assert games(engine) == [None, None]  # original behaviour: one unnamed game


def test_nested_sessions_fail_closed():
    adapter, _ = make()
    with (
        adapter.request_session(),
        pytest.raises(EngineConfigurationError, match="nested"),
        adapter.request_session(),
    ):
        pass


def test_exception_releases_the_session():
    adapter, engine = make()
    with pytest.raises(RuntimeError), adapter.request_session():
        adapter.analyze(START, SETTINGS)
        raise RuntimeError("explanation failed")
    with adapter.request_session():  # would deadlock if the lock leaked
        adapter.analyze(START, SETTINGS)
    assert games(engine)[0] is not games(engine)[1]


def test_closed_adapter_rejects_sessions():
    adapter, _ = make()
    adapter.close()
    with pytest.raises(EngineClosedError), adapter.request_session():
        pass


def _request(adapter, label, events, barrier=None, fail=False):
    if barrier is not None:
        barrier.wait()
    with adapter.request_session():
        events.append((label, "acquire"))
        for _ in range(3):
            adapter.analyze(START, SETTINGS)
            events.append((label, "engine"))
            time.sleep(0.005)
        if fail:
            events.append((label, "fail"))
            raise RuntimeError(label)
    events.append((label, "release"))


def _serial(events, labels=("A", "B")):
    order = [label for label, _ in events]
    first = order[0]
    second = next(label for label in labels if label != first)
    boundary = order.index(second)
    return set(order[:boundary]) == {first} and set(order[boundary:]) == {second}


@pytest.mark.parametrize("fail_first", [False, True])
def test_concurrent_sessions_never_interleave(fail_first):
    engine = FakeEngine(delay=0.002)
    adapter, _ = make(engine)
    events: list = []
    barrier = threading.Barrier(2)
    errors = []

    def run(label):
        try:
            _request(adapter, label, events, barrier, fail=fail_first and label == "A")
        except RuntimeError as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=run, args=(label,)) for label in ("A", "B")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    assert not any(thread.is_alive() for thread in threads)
    assert _serial(events)
    tokens = games(engine)
    assert len(tokens) == 6 and tokens[0] is tokens[1] is tokens[2]
    assert tokens[3] is tokens[4] is tokens[5] and tokens[3] is not tokens[0]
    assert engine.max_active == 1
    if fail_first:
        assert errors == ["A"] and ("B", "release") in events  # B proceeds after A failed


def test_bare_analyze_waits_for_another_threads_session():
    engine = FakeEngine()
    adapter, _ = make(engine)
    events: list = []
    entered = threading.Event()
    leave = threading.Event()

    def holder():
        with adapter.request_session():
            adapter.analyze(START, SETTINGS)
            events.append("session-engine")
            entered.set()
            leave.wait(5)
            events.append("session-end")

    thread = threading.Thread(target=holder)
    thread.start()
    entered.wait(5)
    other = threading.Thread(
        target=lambda: (adapter.analyze(START, SETTINGS), events.append("bare"))
    )
    other.start()
    time.sleep(0.05)
    assert "bare" not in events  # blocked: no interleaving into another request
    leave.set()
    thread.join(5)
    other.join(5)
    assert events == ["session-engine", "session-end", "bare"]
