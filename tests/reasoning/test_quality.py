"""`quality_v1` (reasoning R0-D §7.2, §18.3): grades from one search's WDL."""

from __future__ import annotations

import pytest
from scripted import fen_after, scripted
from synthetic import IDENTITY
from synthetic import engine as synthetic_engine

from calliope.facts import Color, Cp, EngineProfile, FactEngine, Mate, RootSpec, Wdl
from calliope.facts.search import EngineIdentity
from calliope.reasoning import (
    AnalysisRequest,
    Controller,
    Grade,
    JudgementStatus,
    LineScore,
    expected,
    grade,
)

PROFILE = EngineProfile()
# an engine that does not offer UCI_ShowWDL: its lines carry `Unavailable` WDL (A0 §12)
NO_WDL = EngineIdentity(
    "Stockfish 19",
    "no-wdl",
    "6" * 64,
    tuple(o for o in IDENTITY.options if o.name != "UCI_ShowWDL"),
)


def _line(rank: int, exp: int, score=None) -> LineScore:
    wdl = Wdl(exp // 2, exp % 2, 1000 - exp // 2 - exp % 2)  # any WDL with that expectation
    return LineScore(rank, f"m{rank}", score or Cp(0), wdl, exp)


# -- the pure policy ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("loss", "expected_grade"),
    [
        (0, Grade.EXCELLENT),
        (39, Grade.EXCELLENT),
        (40, Grade.GOOD),
        (41, Grade.GOOD),
        (99, Grade.GOOD),
        (100, Grade.INACCURACY),
        (101, Grade.INACCURACY),
        (199, Grade.INACCURACY),
        (200, Grade.MISTAKE),
        (201, Grade.MISTAKE),
        (399, Grade.MISTAKE),
        (400, Grade.BLUNDER),
        (401, Grade.BLUNDER),
        (1999, Grade.BLUNDER),
    ],
)
def test_band_boundaries_are_lower_inclusive(loss: int, expected_grade: Grade) -> None:
    best = _line(1, 2000)
    played = _line(3, 2000 - loss)
    assert grade(played, best, Color.WHITE) == (loss, expected_grade)


def test_only_rank_one_is_best_and_a_negative_loss_is_floored() -> None:
    assert grade(_line(1, 1000), _line(1, 1000), Color.WHITE) == (0, Grade.BEST)
    assert grade(_line(2, 1500), _line(1, 1000), Color.WHITE) == (0, Grade.EXCELLENT)


@pytest.mark.parametrize(
    ("d", "expected_grade"),
    [
        (0, Grade.EXCELLENT),
        (1, Grade.GOOD),
        (2, Grade.INACCURACY),
        (3, Grade.INACCURACY),
        (4, Grade.MISTAKE),
    ],
)
def test_mate_tables(d: int, expected_grade: Grade) -> None:
    mating = grade(
        _line(2, 2000, Mate(Color.WHITE, 2 + d)), _line(1, 2000, Mate(Color.WHITE, 2)), Color.WHITE
    )
    assert mating[1] is expected_grade
    mated = grade(
        _line(2, 0, Mate(Color.BLACK, 6 - d)), _line(1, 0, Mate(Color.BLACK, 6)), Color.WHITE
    )
    assert mated[1] is expected_grade


def test_a_missed_mate_that_still_wins_is_graded_by_wdl() -> None:
    played = _line(2, 2000, Cp(900))
    best = _line(1, 2000, Mate(Color.WHITE, 3))
    assert grade(played, best, Color.WHITE) == (0, Grade.EXCELLENT)  # the miss is a claim (R2-D)


def test_expected_points_are_from_the_mover() -> None:
    wdl = Wdl(white_win=600, draw=300, black_win=100)
    assert expected(wdl, Color.WHITE) == 1500
    assert expected(wdl, Color.BLACK) == 500


def test_grade_order() -> None:
    assert Grade.BLUNDER.at_least(Grade.INACCURACY)
    assert Grade.INACCURACY.at_least(Grade.INACCURACY)
    assert not Grade.GOOD.at_least(Grade.INACCURACY)


# -- on a tree --------------------------------------------------------------------------------------


def _analyse(port, moves: tuple[str, ...], target: int):
    request = AnalysisRequest(RootSpec(), moves, target, PROFILE)
    return Controller(FactEngine(engine=port)).round_zero(request)


def test_black_mover_in_a_survey() -> None:
    after_e4 = fen_after("e4")
    table = {
        after_e4: [
            ("e7e5", ("cp", 20), (300, 500, 200)),
            ("c7c5", ("cp", 10), (250, 550, 200)),
            ("e7e6", ("cp", 0), (200, 600, 200)),
        ]
    }
    result = _analyse(scripted(table), ("e4", "c5"), 2)
    judgement = result.judgements[0]
    assert judgement.status is JudgementStatus.DECIDED
    assert (judgement.best.expected, judgement.played.expected) == (1100, 1050)
    assert (judgement.loss, judgement.grade) == (50, Grade.GOOD)
    assert {s.rank for s in judgement.alternatives} == {1, 2, 3, 4, 5}  # MultiPV 5


def test_a_played_move_outside_the_survey_is_graded_in_the_comparison() -> None:
    start = fen_after()
    candidates = [
        ("e2e4", ("cp", 30), (400, 500, 100)),
        ("d2d4", ("cp", 30), (400, 500, 100)),
        ("g1f3", ("cp", 25), (380, 520, 100)),
        ("c2c4", ("cp", 25), (380, 520, 100)),
        ("b1c3", ("cp", 10), (300, 550, 150)),
        ("g2g4", ("cp", -150), (100, 300, 600)),
    ]
    result = _analyse(scripted({start: candidates}), ("g4",), 1)
    judgement = result.judgements[0]
    view = result.tree.view(result.rev)
    assert view.search(judgement.search.search_id).kind.value == "comparison"
    assert judgement.played.rank == 6
    assert (judgement.loss, judgement.grade) == (800, Grade.BLUNDER)
    # every number of the judgement comes from that one search
    search = view.search(judgement.search.search_id)
    assert {line.move for line in search.lines} == {s.move for s in judgement.alternatives}


def test_mate_scores_on_a_tree() -> None:
    fen = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"
    table = {
        fen_after(fen=fen): [
            ("a1a8", ("mate", 1), (1000, 0, 0)),
            ("g1f1", ("cp", 300), (900, 100, 0)),
            ("h2h3", ("cp", 280), (880, 120, 0)),
        ]
    }
    request = AnalysisRequest(RootSpec(fen=fen), ("Kf1",), 1, PROFILE)
    result = Controller(FactEngine(engine=scripted(table))).round_zero(request)
    judgement = result.judgements[0]
    assert judgement.best.score == Mate(Color.WHITE, 1)
    assert (judgement.loss, judgement.grade) == (100, Grade.INACCURACY)  # 2000 − (2·900 + 100)


def test_inconclusive_reasons() -> None:
    start = fen_after()
    no_wdl = [("e2e4", ("cp", 30), None), ("d2d4", ("cp", 20), None)]
    result = _analyse(scripted({start: no_wdl}, identity=NO_WDL), ("e4",), 1)
    assert (result.judgements[0].status, result.judgements[0].reason) == (
        JudgementStatus.INCONCLUSIVE,
        "WDL_UNAVAILABLE",
    )
    irregular = synthetic_engine(irregular=frozenset({start}))
    result = _analyse(irregular, ("e4",), 1)
    assert result.judgements[0].reason == "IRREGULAR_SEARCH"
    assert result.observations == ()  # no standard lines without a decided judgement
