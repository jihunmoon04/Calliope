"""The calibration tool (Q-D §7, test obligations §9.8–§9.10) on fixtures and synthetic data."""

from __future__ import annotations

import math
import random

import pytest

from calliope.reasoning import curve_points, load_curve_table
from calliope.reasoning.grading import runtime_scale
from tools.calibrate_curve.__main__ import table_text
from tools.calibrate_curve.data import Training, Validation
from tools.calibrate_curve.fit import fit
from tools.calibrate_curve.gates import Losses, band_fits, validate
from tools.calibrate_curve.pgn import evals, games, kept, samples, time_class
from tools.calibrate_curve.scale import check

# -- §9.8 the parser ---------------------------------------------------------------------------

PGN = """[Event "Rated Rapid game"]
[Site "https://lichess.org/a"]
[White "w"]
[Black "b"]
[Result "1-0"]
[WhiteElo "1500"]
[BlackElo "1450"]
[TimeControl "600+0"]

1. e4 { [%eval 0.17] } 1... e5 { [%eval 0.2] } 2. Nf3 { [%eval 0.18] } 2... Nc6 { [%eval 0.25] }
3. Bc4 { [%eval 0.1] } 3... Nd4 { [%eval 0.9] } 4. Nxe5 { [%eval -1.5] } 4... Qg5 { [%eval 2.5] }
5. Nxf7 { [%eval -20.0] } 5... Qxg2 { [%eval #-3] } 1-0

[Event "Casual Blitz game"]
[Result "0-1"]
[WhiteElo "1500"]
[BlackElo "1500"]
[TimeControl "180+2"]

1. e4 e5 0-1

[Event "Rated Bullet game"]
[Result "1/2-1/2"]
[WhiteElo "?"]
[BlackElo "1500"]
[TimeControl "60+0"]

1. e4 e5 1/2-1/2

[Event "Rated Classical game"]
[Result "1/2-1/2"]
[WhiteElo "2000"]
[BlackElo "1950"]
[TimeControl "1800+30"]

1. d4 d5 1/2-1/2

[Event "Rated Correspondence game"]
[Result "1-0"]
[WhiteElo "2000"]
[BlackElo "2000"]
[TimeControl "-"]

1. d4 d5 1-0
"""


def test_the_parser_and_the_filters() -> None:
    found = list(games(PGN.splitlines(keepends=True)))
    assert len(found) == 5
    rapid = kept(found[0])
    assert (rapid.time_class, rapid.band, rapid.rating, rapid.score, rapid.evaluated) == (
        "rapid", 1400, 1475, 2, True,
    )  # fmt: skip
    values = evals(found[0].movetext)
    assert values[0] == ("cp", 17) and values[8] == ("cp", -2000) and values[9] == ("mate", -3)
    assert list(samples(values)) == [(8, 250), (9, -1500)]  # from ply 8, clipped, no mates
    assert kept(found[1]) is None  # casual
    assert kept(found[2]) is None  # a missing rating
    classical = kept(found[3])
    assert (classical.time_class, classical.score, classical.evaluated) == ("classical", 1, False)
    assert kept(found[4]) is None  # correspondence


@pytest.mark.parametrize(
    ("control", "expected"),
    [("15+0", "bullet"), ("60+1", "bullet"), ("179+0", "bullet"), ("180+0", "blitz"),
     ("180+2", "blitz"), ("300+3", "blitz"), ("480+0", "rapid"), ("600+5", "rapid"),
     ("1500+0", "classical"), ("-", None), ("", None)],
)  # fmt: skip
def test_time_class(control: str, expected: str | None) -> None:
    assert time_class(control) == expected


# -- synthetic games ---------------------------------------------------------------------------


def _score(rng: random.Random, p: float) -> int:
    """White's half points with mean `p`: draws, then wins, so that E[y] = p."""

    draw = min(0.3, 2 * min(p, 1 - p))
    u = rng.random()
    if u < draw:
        return 1
    return 2 if rng.random() < (p - draw / 2) / (1 - draw) else 0


def _games(c: float, n: int, seed: int, spread: int = 800):
    rng = random.Random(seed)
    for _ in range(n):
        x = rng.randint(-spread, spread)
        yield x, _score(rng, 1 / (1 + 10 ** (-x / c)))


def _training(bands: dict, n: int = 120_000, seed: int = 1) -> Training:
    training = Training()
    for i, (key, c) in enumerate(bands.items()):
        for x, score in _games(c, n, seed + i):
            training.add(key, score, [(8, x)])
    return training


def _validation(bands: dict, n: int = 60_000, seed: int = 100) -> Validation:
    validation = Validation()
    for i, (key, c) in enumerate(bands.items()):
        for x, score in _games(c, n, seed + i):
            validation.add(key, score, [(8, x)])
    return validation


# -- §9.9 the fit, the band criteria and the gates --------------------------------------------


@pytest.mark.parametrize("c", [600, 1000, 1500])
def test_the_fit_recovers_the_scale(c: int) -> None:
    training = _training({("rapid", 1200): c})
    raw = training.cells[("rapid", 1200)]
    found = fit({x: (float(n), hp / 2) for x, (n, hp) in raw.items()})
    assert abs(found - c) <= 0.02 * c


def test_band_criteria_drop_a_thin_band_and_a_band_at_a_bound() -> None:
    training = _training({("rapid", 1200): 900}, n=120_000)
    for key, c, n in ((("rapid", 1400), 900, 50_000), (("rapid", 1600), 9000, 120_000)):
        for x, score in _games(c, n, 7):
            training.add(key, score, [(8, x)])
    fits = band_fits(training)
    assert fits[("rapid", 1200)].kept
    assert "positions" in fits[("rapid", 1400)].reasons[0]
    assert any("bound" in r for r in fits[("rapid", 1600)].reasons)


BANDS = {("rapid", 1000): 1300, ("rapid", 1400): 700}


def test_the_gates_pass_for_the_true_scales() -> None:
    training = _training(BANDS)
    fits = band_fits(training)
    report = validate(training, _validation(BANDS, n=40_000), fits)
    assert all(f.kept for f in fits.values())
    assert report.passed == {"gate1": True, "gate2": True, "gate3": True}
    low, high = report.aggregate["difference_vs_default_95"]
    assert low < high < 0
    assert report.aggregate["bootstrap"]["seed"] == 20261010


def test_the_gates_fail_for_curves_thirty_percent_off() -> None:
    training = _training(BANDS)
    fits = band_fits(training)
    for f in fits.values():
        f.source_scale = round(f.source_scale * (1.3 if f.source_scale > 1000 else 0.7))
    report = validate(training, _validation(BANDS, n=40_000), fits)
    assert not (report.passed["gate2"] and report.passed["gate3"])


def test_left_out_bands_are_scored_as_the_runtime_clamps() -> None:
    training = _training(BANDS)
    fits = band_fits(training)
    validation = _validation({**BANDS, ("rapid", 2000): 600}, n=20_000)
    report = validate(training, validation, fits)
    clamped = report.per_band["rapid 2000"]
    assert clamped["clamped"] and clamped["scale"] == fits[("rapid", 1400)].source_scale
    assert report.aggregate["positions"] == 60_000  # every position of the time class
    assert "rapid 2000" not in report.reliability  # reliability is per kept band


# -- §7.6 the deployed loss -------------------------------------------------------------------


def test_the_deployed_loss_on_hand_values() -> None:
    losses = Losses()
    loss, brier, p = losses.at(1000, 0, 1)  # a draw at p = ½
    assert p == 0.5 and math.isclose(loss, math.log(2)) and brier == 0
    loss, brier, p = losses.at(150, 1500, 0)  # a saturated p, scored against a loss
    assert p == 1.0 and math.isclose(loss, math.log(4000)) and brier == 1.0


# -- §7.4 the engine-scale check --------------------------------------------------------------


def _positions(n: int = 1000, seed: int = 3) -> list[tuple[str, int]]:
    rng = random.Random(seed)
    return [(f"fen{i}", rng.choice((-1, 1)) * rng.randint(0, 1000)) for i in range(n)]


def _evaluator(positions, f):
    table = dict(positions)
    return lambda fen: f(table[fen])


def test_a_consistent_ratio_sets_the_permille() -> None:
    positions = _positions()
    result = check(positions, _evaluator(positions, lambda x: round(1.3 * x)))
    assert result.passed and result.permille == 1300 and abs(result.k - 1.3) < 0.01
    near = check(positions, _evaluator(positions, lambda x: round(1.05 * x)))
    assert near.passed and near.permille == 1000  # within 10 %: no change (Q-D §7.4 step 2)


def test_the_check_fails_for_a_bucket_dependent_ratio_or_flipped_signs() -> None:
    positions = _positions()
    bent = check(positions, _evaluator(positions, lambda x: x if abs(x) < 300 else 2 * x))
    assert not bent.passed and any("bucket" in f for f in bent.failures)
    flipped = check(positions, _evaluator(positions, lambda x: -x if abs(x) % 10 == 0 else x))
    assert not flipped.passed and any("sign" in f for f in flipped.failures)


def test_mates_are_skipped() -> None:
    positions = _positions()
    result = check(positions, _evaluator(positions, lambda x: None if x > 900 else x))
    assert result.skipped_mates > 0 and result.passed


# -- §9.10 the table and the carry-over to Calliope's cp -------------------------------------


def test_the_written_table_loads_with_the_runtime_checks() -> None:
    from tools.calibrate_curve.scale import ScaleResult

    training = _training(BANDS)
    training.games_read = training.games_used  # synthetic games are all used
    fits = band_fits(training)
    scale = ScaleResult(1.3, 1300, {}, 1.0, 1.3, 2000, 0, "d", [])
    table = load_curve_table(table_text("synthetic_v1", "s", 10, training, fits, scale).encode())
    for band in table.bands:
        assert band.scale == runtime_scale(band.source_scale, 1300)
        assert band.source_scale == fits[(band.time_class, band.low)].source_scale


@pytest.mark.parametrize("source", [500, 600, 957, 1307, 3000])
@pytest.mark.parametrize("permille", [700, 1300])
def test_the_runtime_scale_carries_the_curve_to_calliope_cp(source: int, permille: int) -> None:
    """With x_C = k · x_L in integer cp, E read from x_C at `scale` matches E from x_L at
    `source_scale` within 1.15 · (500 / scale + 2) points: half a centipawn of rounding in x_C
    and one truncated step on each side, at the curve's steepest slope (record §2)."""

    k = permille / 1000
    scale = runtime_scale(source, permille)
    worst = max(
        abs(curve_points(round(k * x), scale) - curve_points(x, source))
        for x in range(-1500, 1501)
    )
    assert worst <= math.ceil(1.15 * (500 / scale + 2))
    assert worst <= 3 or scale < 500
