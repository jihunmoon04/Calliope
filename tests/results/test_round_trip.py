"""CC-D §2.2: the round trip a write without the replay relies on, structural and final, for every
case of the acceptance corpus — under its scripted engine, and under Stockfish 19 when
`CALLIOPE_STOCKFISH_PATH` is set. A ply written without the replay is answered from the analysis
in memory; a later read replays its bytes. Both must give the same bytes and the same document."""

from __future__ import annotations

import hashlib
import os

import pytest
from corpus_case import analyse, cases, stockfish_request
from result_input import engine_run, game_input, ply_input

from calliope.facts import FactEngine
from calliope.reasoning import Reasoner, explain
from calliope.reasoning.storage import load, save
from calliope.results import Bundle, dumps, game_result

CASES = {case["name"]: case for case in cases()}
PATH = os.environ.get("CALLIOPE_STOCKFISH_PATH")


def _round_trip(case: dict, analysis) -> None:
    rendered = explain(analysis)
    tree, graph = save(analysis, rendered)
    loaded, again = load(FactEngine(), tree, graph)
    assert save(loaded, again) == (tree, graph)  # structural
    bundle = Bundle(
        hashlib.sha256(tree).hexdigest(), hashlib.sha256(graph).hexdigest(), stored=True
    )
    game = game_input(case["fen"], [*case.get("before", "").split(), case["played"]])
    first = game_result(game, engine_run(analysis), [ply_input(analysis, rendered, bundle)])
    later = game_result(game, engine_run(loaded), [ply_input(loaded, again, bundle)])
    # final: the document of the first answer and of a later read
    assert dumps(first) == dumps(later)
    assert again.text == rendered.text and again.plan_digest == rendered.plan_digest


@pytest.mark.parametrize("name", list(CASES))
def test_the_round_trip_of_a_scripted_case(name: str) -> None:
    _round_trip(CASES[name], analyse(CASES[name]))


@pytest.fixture(scope="module")
def stockfish():
    from calliope.facts.search import StockfishEngine

    engine = StockfishEngine.start(PATH)
    yield engine
    engine.close()


@pytest.mark.skipif(not PATH, reason="needs CALLIOPE_STOCKFISH_PATH")
@pytest.mark.parametrize("name", list(CASES))
def test_the_round_trip_with_stockfish(name: str, stockfish) -> None:
    case = CASES[name]
    _round_trip(case, Reasoner(FactEngine(engine=stockfish)).analyse(stockfish_request(case)))
