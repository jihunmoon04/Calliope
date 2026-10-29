"""`FactEngine.prefetch_survey` (PF-D §4.2): the survey `open` would ask, asked ahead."""

from __future__ import annotations

from dataclasses import replace

import chess
import pytest
from synthetic import IDENTITY, engine

from calliope.facts import (
    EngineProfile,
    FactEngine,
    InvalidRequestError,
    OpenRequest,
    PrefetchOutcome,
    RootSpec,
)
from calliope.facts.search import EngineResultStore, ScriptedEngine
from calliope.facts.search.records import ReuseSource

PROFILE = EngineProfile()
SCHOLAR = ("e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6", "h5f7")  # checkmate


def test_the_survey_ahead_is_the_one_open_asks() -> None:
    store = EngineResultStore()
    main, ahead = engine(), engine()
    facts = FactEngine(engine=main, store=store)
    root = RootSpec(moves=("e2e4", "e7e5"))
    assert facts.prefetch_survey(root, PROFILE, ahead) == PrefetchOutcome.RAN
    assert facts.prefetch_survey(root, PROFILE, ahead) == PrefetchOutcome.STORED
    assert len(ahead.calls) == 1 and facts.survey_stored(root, PROFILE)
    tree = facts.open(OpenRequest(root=root, engine=PROFILE))
    assert main.calls == []  # the root's survey came from the store
    assert next(r.reused for r in tree.view().runtimes()) == ReuseSource.STORE


def test_a_position_that_ends_the_game_or_follows_one_is_not_searched() -> None:
    store = EngineResultStore()
    ahead = engine()
    facts = FactEngine(engine=engine(), store=store)
    mate = RootSpec(moves=SCHOLAR)
    assert facts.prefetch_survey(mate, PROFILE, ahead) == PrefetchOutcome.NOT_SEARCHED
    bare = "8/8/8/4k3/8/8/8/4K3 w - - 0 1"  # insufficient material: ended by rule
    after = RootSpec(fen=bare, moves=("e1d1",))
    assert facts.prefetch_survey(after, PROFILE, ahead) == PrefetchOutcome.NOT_SEARCHED
    stalemate = RootSpec(fen="7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert facts.prefetch_survey(stalemate, PROFILE, ahead) == PrefetchOutcome.NOT_SEARCHED
    assert ahead.calls == []
    # the fact engine agrees: it surveys none of them
    main = engine()
    for root in (mate, after, stalemate):
        FactEngine(engine=main, store=store).open(OpenRequest(root=root, engine=PROFILE))
    assert main.calls == []


def test_a_reserved_key_is_not_searched_nor_waited_for() -> None:
    store = EngineResultStore()
    facts = FactEngine(engine=engine(), store=store)
    root = RootSpec(moves=("d2d4",))
    first = engine()
    facts.prefetch_survey(root, PROFILE, first)
    key = next(iter(store._searches))
    store._searches.clear()
    token = store.reserve(key)
    ahead = engine()
    assert facts.prefetch_survey(root, PROFILE, ahead) == PrefetchOutcome.RESERVED
    assert ahead.calls == [] and token is not None


def test_an_irregular_answer_is_dropped() -> None:
    fen = chess.Board().fen()
    store = EngineResultStore()
    facts = FactEngine(engine=engine(), store=store)
    ahead = engine(irregular=frozenset({fen}))
    assert facts.prefetch_survey(RootSpec(), PROFILE, ahead) == PrefetchOutcome.IRREGULAR
    assert len(store) == 0


def test_another_engine_is_refused() -> None:
    facts = FactEngine(engine=engine())
    other = ScriptedEngine(replace(IDENTITY, binary_sha256="6" * 64), lambda r: None)
    with pytest.raises(InvalidRequestError):
        facts.prefetch_survey(RootSpec(), PROFILE, other)
    with pytest.raises(InvalidRequestError):
        FactEngine().prefetch_survey(RootSpec(), PROFILE, engine())
