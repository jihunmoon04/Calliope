"""Explanation accuracy (EA-D §6): `material_gain_v2` checked against `Lp`'s score, and
`better_alternative_v1`, the better move named for every inaccuracy."""

from __future__ import annotations

import inspect
from dataclasses import replace

import pytest
from story import I, R, S, claim, finding, line, run, status, table
from test_miss_v2 import scenario

from calliope.facts import FactEngine
from calliope.reasoning import StoredGraphError
from calliope.reasoning.catalogue import CATALOGUE_V1
from calliope.reasoning.catalogue.material import GAIN_CP_PER_POINT, MaterialGain
from calliope.reasoning.findings import MaterialFinding, MissedGainFinding
from calliope.reasoning.labels import MISS_LOSS
from calliope.reasoning.planner import COMPARISONS, MATERIAL, MECHANISMS
from calliope.reasoning.render import (
    GuardError,
    Handle,
    bind,
    explain,
    phrase,
    phrasebook,
    plan_analysis,
)
from calliope.reasoning.storage import load, save

WIN, EVEN = (900, 100, 0), (300, 600, 100)
OTHER = "Kf2 Kd7 Kf3 Kd6"
# the h-pawns keep every line out of a dead draw (a DRAWN window is INCONCLUSIVE, rule 1)
ONE = "4k3/7p/8/3p4/8/8/4N2P/4K3 w - - 0 1"  # 1.Nc3 Kd7 2.Nxd5: one pawn at ply 3
ONE_LP = "Nc3 Kd7 Nxd5 Kd6 Ne3 Ke5"
TWO = "4k3/7p/1p6/3p4/8/8/4N2P/4K3 w - - 0 1"  # … 3.Nxb6: two pawns, the event at ply 5
TWO_LP = "Nc3 Kd7 Nxd5 Kd6 Nxb6 Ke6 Kf2 Kf5"
DIRECT = "4k3/7p/8/3p4/8/2N5/7P/4K3 w - - 0 1"  # 1.Nxd5: the move itself takes
BLACK = "4k3/4n2p/8/8/3P4/8/7P/4K3 b - - 0 1"  # 1...Nc6 2.Kd2 Nxd4


def gain(fen: str, played: str, lp: str, other: str = OTHER, **score):
    return run(fen, played, [line(fen, lp, WIN, **score), line(fen, other, EVEN)], multipv=2)


# -- 1: the rules of material_gain_v2 (EA-D §2) ---------------------------------------------------


def test_the_threshold_is_80_per_point_and_inclusive() -> None:
    assert GAIN_CP_PER_POINT == 80
    assert status(gain(ONE, "Nc3", ONE_LP, cp=50), "material_gain_v2") is R
    assert status(gain(ONE, "Nc3", ONE_LP, cp=79), "material_gain_v2") is R
    supported = gain(ONE, "Nc3", ONE_LP, cp=80)
    found = finding(claim(supported, "material_gain_v2"), MaterialFinding)
    assert (found.amount.points, found.event.ply) == (1, 3)


def test_the_threshold_scales_with_the_amount() -> None:
    assert status(gain(TWO, "Nc3", TWO_LP, cp=150), "material_gain_v2") is R
    assert status(gain(TWO, "Nc3", TWO_LP, cp=159), "material_gain_v2") is R
    supported = gain(TWO, "Nc3", TWO_LP, cp=160)
    found = finding(claim(supported, "material_gain_v2"), MaterialFinding)
    assert (found.amount.points, found.event.ply) == (2, 5)


def test_a_gain_by_the_move_itself_ignores_the_score() -> None:
    a = gain(DIRECT, "Nxd5", "Nxd5 Kd7 Ne3 Ke6 Kf2 Kf6", cp=50)
    found = finding(claim(a, "material_gain_v2"), MaterialFinding)
    assert (found.amount.points, found.event.ply) == (1, 1)  # E3: 36...Bxg2 at −7.84 stays


def test_black_as_the_mover_reads_the_score_from_its_side() -> None:
    lp = "Nc6 Kd2 Nxd4 Kd3 Ne6 Ke4"
    # the scripted score is Black's; the engine reports White's (−50, −80)
    assert status(gain(BLACK, "Nc6", lp, "Kf8 Kd2 Kf7 Kd3", cp=50), "material_gain_v2") is R
    assert status(gain(BLACK, "Nc6", lp, "Kf8 Kd2 Kf7 Kd3", cp=80), "material_gain_v2") is S


@pytest.mark.parametrize("mate", [5, -5])
def test_a_mate_line_is_inconclusive_for_either_side(mate: int) -> None:
    # review B1: rule 1 takes every mate score first; rule 3 never sees one
    a = gain(ONE, "Nc3", ONE_LP, mate=mate)
    assert table(a)["material_gain_v2"] == (I, "MATE_LINE")


def test_a_refuted_gain_is_not_said() -> None:
    text = explain(gain(ONE, "Nc3", ONE_LP, cp=50)).text
    assert "wins" not in text and "material gain" not in text
    text = explain(gain(ONE, "Nc3", ONE_LP, cp=80)).text
    assert "Along the engine line, it wins the pawn on d5 at 2.Nxd5" in text


# -- 2: better_alternative_v1 (EA-D §3) -----------------------------------------------------------


def test_an_inaccuracy_below_the_miss_loss_names_the_better_move() -> None:
    a = scenario(0, 120)  # INACCURACY: 100 <= loss < 200, below MISS_LOSS
    assert status(a, "missed_gain_v1") is None
    alt = claim(a, "better_alternative_v1")
    assert alt.verdict.status is S
    found = finding(alt, MissedGainFinding)
    assert (found.best.rank, found.best.ply, found.loss) == (1, 1, 120)
    assert alt.verdict.scope.witnesses == ("e1d2",)
    assert alt.verdict.scope.quantifier.value == "exists_alternative"
    assert explain(a).text == (
        "2.a3 is an inaccuracy. Instead, 2.Kd2 was better. Based on the 2 moves the engine reported."
    )
    assert not a.labels  # it grounds no label


def test_not_proposed_for_a_good_move_or_the_best_move() -> None:
    assert status(scenario(0, 60), "better_alternative_v1") is None  # GOOD
    assert status(scenario(0, 0), "better_alternative_v1") is None  # rank 1


def test_not_proposed_without_a_decided_judgement() -> None:
    from scripted import scripted as table_engine
    from test_catalogue_consequences import MATE_IN_ONE
    from test_quality import NO_WDL

    lines = [("h2h3", ("cp", 0), None), ("e1c1", ("mate", -1), None)]
    engine = table_engine({MATE_IN_ONE: lines}, identity=NO_WDL)
    a = run(MATE_IN_ONE, "Rc1", [], engine=engine, multipv=2)
    assert a.round_zero.judgements[0].reason == "WDL_UNAVAILABLE"
    assert status(a, "better_alternative_v1") is None


def test_the_stronger_comparison_comes_first() -> None:
    a = scenario(0, MISS_LOSS + 10)
    assert status(a, "missed_gain_v1") is S and status(a, "better_alternative_v1") is S
    p = plan_analysis(a)
    assert p.justification == (claim(a, "missed_gain_v1").id,)
    text = explain(a).text
    assert text.count("Instead") == 1 and "Instead, 2.Kd2 was stronger." in text


def test_a_material_comparison_comes_first() -> None:
    from test_catalogue_consequences import _fork

    a = _fork()  # a blunder with better_move_v1 (the knight is lost along Lp)
    assert status(a, "better_move_v1") is S and status(a, "better_alternative_v1") is S
    assert plan_analysis(a).justification[0] == claim(a, "better_move_v1").id
    assert explain(a).text.count("Instead") == 1


# -- 3, 6, 8: tables, build, coverage -------------------------------------------------------------


def test_the_planner_tables_name_only_catalogue_templates() -> None:
    names = {t.name for t in CATALOGUE_V1}
    assert "material_gain_v2" in MATERIAL and "material_gain_v1" not in names
    assert COMPARISONS[-1] == "better_alternative_v1"
    assert set(MATERIAL) | set(COMPARISONS) | set(MECHANISMS) <= names


def test_every_catalogue_template_is_named_and_bound() -> None:
    """EA-D §6.8: every shipped template has a `[claim]` name (for a pending claim) and a branch
    in `render.bind`, so a later template cannot be left out and fail the guard (G5)."""

    book = phrasebook()
    names = {t.name for t in CATALOGUE_V1}
    assert names <= set(book["claim"]), names - set(book["claim"])
    assert "material_gain_v1" not in book and "material_gain_v1" not in book["claim"]
    source = inspect.getsource(bind)
    assert {n for n in names if f'"{n}"' not in source} == set()
    for a in (scenario(0, 120), gain(ONE, "Nc3", ONE_LP, cp=80)):
        for c in a.claims:
            if c.supported and c.hypothesis.template in ("better_alternative_v1",
                                                         "material_gain_v2"):  # fmt: skip
                key, values = bind(c, _handle(a, c), "sentence")
                assert phrase(c.hypothesis.template, key, values, c.id, sentence=True)


def test_a_template_without_a_binding_is_refused() -> None:
    a = scenario(0, 120)
    alt = claim(a, "better_alternative_v1")
    unknown = replace(alt, hypothesis=replace(alt.hypothesis, template="unknown_v1"))
    with pytest.raises(GuardError, match="G5"):
        bind(unknown, _handle(a, alt), "sentence")


def test_a_graph_of_the_v1_build_is_refused() -> None:
    class GainV1(MaterialGain):
        name = "material_gain_v1"  # the old build's catalogue, as far as its identity goes

    old = tuple(GainV1() if t.name == "material_gain_v2" else t for t in CATALOGUE_V1)
    old = tuple(t for t in old if t.name != "better_alternative_v1")
    a = run(ONE, "Nc3", [line(ONE, ONE_LP, WIN, cp=80), line(ONE, OTHER, EVEN)], multipv=2,
            templates=old)  # fmt: skip
    tree_bytes, graph_bytes = save(a, explain(a))
    with pytest.raises(StoredGraphError, match="re-analyse"):
        load(FactEngine(), tree_bytes, graph_bytes)
    current = gain(ONE, "Nc3", ONE_LP, cp=80)
    assert all(name != "material_gain_v1" for name, _ in current.build.templates)
    assert current.build != a.build


def _handle(a, c) -> Handle:
    h = c.hypothesis
    view = a.tree.view(a.rev)
    return Handle(c.id, view, h.operands, c.verdict.evidence, c.verdict.findings, c.verdict.scope)
