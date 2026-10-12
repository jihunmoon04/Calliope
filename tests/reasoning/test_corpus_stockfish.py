"""The acceptance corpus under real Stockfish 19 (R4-D §4.3), gated by `CALLIOPE_STOCKFISH_PATH`.

Only what no engine detail can change is asserted: the analysis completes and renders, the bundle
round-trips, and for `robust` cases the labels and claims of `[expect.robust]`.
"""

from __future__ import annotations

import os

import pytest
from corpus_case import cases, stockfish_request

from calliope.facts import FactEngine
from calliope.reasoning import Reasoner
from calliope.reasoning.render import explain
from calliope.reasoning.storage import load, save

PATH = os.environ.get("CALLIOPE_STOCKFISH_PATH")
pytestmark = pytest.mark.skipif(not PATH, reason="needs CALLIOPE_STOCKFISH_PATH")
CASES = {case["name"]: case for case in cases()}


@pytest.fixture(scope="module")
def stockfish():
    from calliope.facts.search import StockfishEngine

    engine = StockfishEngine.start(PATH)
    yield engine
    engine.close()


@pytest.mark.parametrize("name", list(CASES))
def test_case_with_stockfish(name: str, stockfish) -> None:
    case = CASES[name]
    analysis = Reasoner(FactEngine(engine=stockfish)).analyse(stockfish_request(case))
    rendered = explain(analysis)  # no GuardError
    assert rendered.text
    tree_bytes, graph_bytes = save(analysis, rendered)
    loaded, again = load(FactEngine(), tree_bytes, graph_bytes)
    assert save(loaded, again) == (tree_bytes, graph_bytes)
    robust = case["expect"].get("robust")
    if case.get("robust") and robust is not None:
        supported = {c.hypothesis.template for c in analysis.claims if c.supported}
        assert set(robust["supported"]) <= supported
        assert [lb.kind.value for lb in analysis.labels] == robust["labels"]
