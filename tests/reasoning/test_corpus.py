"""The acceptance corpus under the scripted engine (R4-D §4.3, R0-D §18.11)."""

from __future__ import annotations

import pytest
from corpus_case import analyse, cases

from calliope.facts import FactEngine
from calliope.reasoning.planner import plan_digest
from calliope.reasoning.render import explain, plan_analysis, render
from calliope.reasoning.storage import load, save

CASES = {case["name"]: case for case in cases()}


def test_the_corpus_has_the_minimum_set() -> None:
    assert len(CASES) >= 12  # R4-D §4.2 (R0-D §18.11 asks for five)


@pytest.mark.parametrize("name", list(CASES))
def test_case(name: str) -> None:
    case = CASES[name]
    expect = case["expect"]
    analysis = analyse(case)
    judgement = analysis.round_zero.judgements[0]
    grade = judgement.grade.value if judgement.grade is not None else judgement.status.value
    assert grade == expect["grade"]
    supported = {c.hypothesis.template for c in analysis.claims if c.supported}
    assert set(expect["supported"]) <= supported
    assert [[lb.kind.value, lb.rule] for lb in analysis.labels] == expect["labels"]
    rendered = explain(analysis)
    assert rendered.text == expect["text"]
    p = plan_analysis(analysis)  # one plan path (R4-D §2.3)
    assert render(p, analysis) == rendered and plan_digest(p) == rendered.plan_digest
    tree_bytes, graph_bytes = save(analysis, rendered)
    loaded, again = load(FactEngine(), tree_bytes, graph_bytes)
    assert save(loaded, again) == (tree_bytes, graph_bytes)
