"""The result store's bound (PF-D §2, D1): least recently used first; the trees are unchanged."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from synthetic import engine

from calliope.facts import PLAYED, EngineProfile, ExtendRequest, FactEngine, InputLine, OpenRequest
from calliope.facts.search import EngineResultStore
from calliope.facts.storage import digest

PROFILE = EngineProfile()


def _search(search_id: str):
    return SimpleNamespace(search_id=search_id, regular=True)


def test_the_least_recently_used_search_is_dropped_and_get_refreshes() -> None:
    store = EngineResultStore(2)
    a, b, c = _search("a"), _search("b"), _search("c")
    store.put(a)
    store.put(b)
    assert store.get("a") is a  # a is now the most recent
    store.put(c)
    assert len(store) == 2
    assert store.get("b") is None
    assert store.get("a") is a and store.get("c") is c


def test_a_second_put_keeps_the_first_and_refreshes_it() -> None:
    store = EngineResultStore(2)
    first = _search("a")
    store.put(first)
    store.put(_search("b"))
    assert store.put(_search("a")) is first
    store.put(_search("c"))
    assert store.get("b") is None and store.get("a") is first


def test_unbounded_by_default() -> None:
    store = EngineResultStore()
    for i in range(100):
        store.put(_search(str(i)))
    assert len(store) == 100


@pytest.mark.parametrize("bound", [0, -1, 1.5, True])
def test_the_bound_is_an_integer_of_at_least_one(bound) -> None:
    with pytest.raises(ValueError):
        EngineResultStore(bound)


def _tree(store, port):
    fact_engine = FactEngine(engine=port, store=store)
    tree = fact_engine.open(OpenRequest(engine=PROFILE))
    fact_engine.extend(tree, ExtendRequest((InputLine("g", ("e4", "e5", "Nf3", "Nc6")),), PLAYED))
    return tree


def test_an_evicted_search_is_asked_again_and_the_tree_is_the_same() -> None:
    unbounded, small = engine(), engine()
    plain = _tree(EngineResultStore(), unbounded)
    store = EngineResultStore(1)
    first, second = _tree(store, small), _tree(store, small)
    assert len(store) == 1
    assert len(small.calls) > len(unbounded.calls)  # the second tree asked again
    for tree in (first, second):
        assert digest(tree) == digest(plain)
