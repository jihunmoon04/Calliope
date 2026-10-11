"""The calibration tool (QM-D §5–§8, test obligations QM-D §10.6–§10.10 and Q-D §9.8) on fixtures
and synthetic data."""

from __future__ import annotations

import json
import math
import random
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from calliope.reasoning import MONOTONE_V1_KNOTS, curve_points, load_curve_table
from tools.calibrate_curve import __main__ as cli
from tools.calibrate_curve.data import Training, Validation
from tools.calibrate_curve.fit import estimates, monotone
from tools.calibrate_curve.gates import (
    BandFit,
    Curves,
    _cross,
    points_of,
    pooled,
    rows,
    select,
    validate,
    weight_flags,
)
from tools.calibrate_curve.pgn import evals, games, kept, samples, time_class
from tools.calibrate_curve.scale import ScaleResult, check

# -- Q-D §9.8, QM-D §8.1: the parser ------------------------------------------------------------

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


GAP = "1. e4 { [%eval 0.17] } 1... e5 { [%clk 0:10:00] } 2. Nf3 { [%eval 0.18] } 1-0"
TAIL = "1. e4 { [%eval 0.17] } 1... e5 { [%eval 0.2] } 2. Qh5 2... Ke7 3. Qxe5# 1-0"


def test_evals_are_bound_to_their_moves() -> None:
    """QM-D §8.1: an eval missing mid-game skips the game; a missing tail is allowed."""

    assert evals(GAP) is None
    assert evals(TAIL) == [("cp", 17), ("cp", 20)]
    assert evals("1. e4 { [%eval 0.1] } (1. d4 { [%eval 0.2] }) 1... e5 { [%eval 0.3] }") is None
    assert evals("1.e4 { [%eval 0.1] } 1...e5 { [%eval 0.2] } $1 2. Nf3 { [%eval 0.3] }") == [
        ("cp", 10), ("cp", 20), ("cp", 30),
    ]  # fmt: skip


def test_a_game_with_an_eval_gap_is_skipped_and_counted() -> None:
    head = '[Event "Rated Rapid game"]\n[Result "1-0"]\n[WhiteElo "1500"]\n[BlackElo "1500"]\n'
    head += '[TimeControl "600+0"]\n\n'
    long = " ".join(
        f"{i}. a3 {{ [%eval 0.{i}] }} {i}... a6 {{ [%eval 0.{i}] }}" for i in range(1, 8)
    )
    pgn = f"{head}{long.replace('{ [%eval 0.2] } 2... a6', '2... a6', 1)} 1-0\n\n{head}{long} 1-0\n"
    training = Training()
    for game in games(pgn.splitlines(keepends=True)):
        training.feed(game)
    assert (training.games_read, training.games_eval_gap, training.games_used) == (2, 1, 1)
    assert training.positions == 7  # plies 8 … 14


@pytest.mark.parametrize(
    ("control", "expected"),
    [("15+0", "bullet"), ("60+1", "bullet"), ("179+0", "bullet"), ("180+0", "blitz"),
     ("180+2", "blitz"), ("300+3", "blitz"), ("480+0", "rapid"), ("600+5", "rapid"),
     ("1500+0", "classical"), ("-", None), ("", None)],
)  # fmt: skip
def test_time_class(control: str, expected: str | None) -> None:
    assert time_class(control) == expected


# -- QM-D §10.6: the fit --------------------------------------------------------------------------


def logistic(x: float, c: float) -> float:
    return 1 / (1 + 10 ** (-x / c))


def shelf(x: float) -> float:
    """Steep near 0, gentle from 100 to 400; monotone and antisymmetric (QM-D §10.6)."""

    return 0.35 * logistic(x, 150) + 0.65 * logistic(x, 900)


def exact(f, n: float = 1000.0) -> dict[int, tuple[float, float]]:
    """Deterministic aggregates: `n(x) = n`, `s(x) = n · f(x)` on [−1500, 1500]."""

    return {x: (n, n * f(x)) for x in range(-1500, 1501)}


@pytest.mark.parametrize(
    "f",
    [lambda x: logistic(x, 600), lambda x: logistic(x, 2400), shelf],
    ids=["c600", "c2400", "shelf"],
)
def test_smoothing_bias_on_smooth_curves(f) -> None:
    table = monotone(exact(f))
    assert table.points is not None and table.points[0] == 1000 and table.interpolated == ()
    assert max(abs(e - 2000 * f(k)) for e, k in zip(table.points, MONOTONE_V1_KNOTS)) <= 20


def test_seeded_draws_stay_within_their_standard_errors() -> None:
    rng = random.Random(20261010)
    cells: dict[int, list[float]] = {}
    for _ in range(10**6):
        x = rng.randint(-1500, 1500)
        y = 1.0 if rng.random() < shelf(x) else 0.0
        cell = cells.setdefault(x, [0.0, 0.0])
        cell[0] += 1
        cell[1] += y
    aggregates = {x: (n, s) for x, (n, s) in cells.items()}
    table = monotone(aggregates)
    assert table.points is not None
    for i, found in enumerate(estimates(aggregates)):
        assert found is not None
        v, w = found
        if i:
            se = 2000 * math.sqrt(v * (1 - v) / w)
            assert abs(table.points[i] - 2000 * shelf(MONOTONE_V1_KNOTS[i])) <= 4 * se + 1
    errors = [abs(e - 2000 * shelf(k)) for e, k in zip(table.points, MONOTONE_V1_KNOTS)]
    assert sum(errors) / len(errors) <= 8


def test_a_dip_gives_a_non_decreasing_table() -> None:
    def dipped(x: float) -> float:
        return logistic(x, 800) - (0.05 if 200 <= abs(x) <= 300 else 0.0) * (1 if x > 0 else -1)

    table = monotone(exact(dipped))
    assert table.points[0] == 1000
    assert all(a <= b for a, b in zip(table.points, table.points[1:]))


def test_coverage_interpolates_holds_and_refuses() -> None:
    """QM-D §5 steps 3–5 and re-review B1: never a division by an empty window."""

    near = {x: (50.0, 50.0 * logistic(x, 800)) for x in range(-700, 701)}
    far = {x: (50.0, 50.0 * logistic(x, 800)) for x in range(1300, 1501)}
    table = monotone({**near, **far})
    assert table.points is not None and table.points[0] == 1000
    assert 1000 in table.interpolated and 1500 not in table.interpolated  # between: interpolated
    i, j, k = (MONOTONE_V1_KNOTS.index(x) for x in (900, 1000, 1300))
    assert table.points[i] <= table.points[j] <= table.points[k]
    held = monotone(near)
    assert held.points[-1] == held.points[MONOTONE_V1_KNOTS.index(max(
        x for x in MONOTONE_V1_KNOTS if x not in held.interpolated))]  # fmt: skip
    thin = monotone({x: (1.0, 0.5) for x in range(-500, 501)})
    assert thin.points is None and thin.unestimated_below  # coverage below 600 cp: refused
    extreme = {
        x: (1000.0, 1000.0 * logistic(x, 800)) for x in (*range(-1100, -899), *range(900, 1101))
    }
    refused = monotone(extreme)
    assert refused.points is None and refused.unestimated_below[0] == 0  # W_0 = 0


# -- synthetic games -------------------------------------------------------------------------------


def _score(rng: random.Random, p: float) -> int:
    """White's half points with mean `p`: draws, then wins, so that E[y] = p."""

    draw = min(0.3, 2 * min(p, 1 - p))
    if rng.random() < draw:
        return 1
    return 2 if rng.random() < (p - draw / 2) / (1 - draw) else 0


def _draws(f, n: int, seed: int, spread: int = 800):
    rng = random.Random(seed)
    for _ in range(n):
        x = rng.randint(-spread, spread)
        yield x, _score(rng, f(x))


def _training(bands: dict, n: int = 120_000, seed: int = 1) -> Training:
    training = Training()
    for i, (key, f) in enumerate(bands.items()):
        for x, score in _draws(f, n, seed + i):
            training.add(key, score, [(8, x)])
    return training


def _validation(curves: Curves, bands: dict, n: int = 100_000, seed: int = 100) -> Validation:
    validation = Validation(curves)
    for i, (key, f) in enumerate(bands.items()):
        for x, score in _draws(f, n, seed + i):
            validation.add(key, score, [(8, x)])
    return validation


def other(x: float) -> float:
    return 0.35 * logistic(x, 250) + 0.65 * logistic(x, 1400)


BANDS = {("rapid", 1000): other, ("rapid", 1400): shelf}


@pytest.fixture(scope="module")
def trained() -> tuple[Training, dict, dict]:
    """500 000 positions per band: shards of 100 000 keep the deviation under 10 (QM-D §6.1); a
    band near the 100 000 minimum is refused by the deviation alone."""

    training = _training(BANDS, n=500_000)
    return training, select(training), pooled(training)


@pytest.fixture
def fast(monkeypatch) -> None:
    """Fewer resamples: the gates' tests check decisions, not the interval's precision."""

    from tools.calibrate_curve import gates

    monkeypatch.setattr(gates, "RESAMPLES", 100)


# -- QM-D §10.7: selection in the training month -----------------------------------------------


def test_selection_keeps_good_bands_and_refuses_thin_or_unstable_ones(trained) -> None:
    _, fits, _ = trained
    assert all(fits[key].kept for key in BANDS), {k: f.reasons for k, f in fits.items()}
    assert all(fits[key].shard_deviation <= 10 for key in BANDS)
    assert fits[("rapid", 1400)].cross["log_loss"]["table"] < fits[("rapid", 1400)].cross[
        "log_loss"]["logistic"]  # fmt: skip
    thin = _training({("rapid", 1600): shelf}, n=99_999)
    assert "positions" in select(thin)[("rapid", 1600)].reasons[0]
    noisy = select(_training({("rapid", 1600): shelf}, n=120_000))[("rapid", 1600)]
    assert any("shard deviation" in r for r in noisy.reasons)  # shards of 24 000: too noisy
    unstable = Training()
    for index, (x, score) in enumerate(_draws(shelf, 500_000, 5)):
        if index % 5 == 4:  # shard 4 from another curve
            score = _score(random.Random(index), logistic(x, 3000))
        unstable.add(("rapid", 1800), score, [(8, x)])
    assert any("shard deviation" in r for r in select(unstable)[("rapid", 1800)].reasons)


def test_the_cross_fitted_reliability_refuses_a_band() -> None:
    training = Training()
    for index, (x, score) in enumerate(_draws(shelf, 120_000, 9)):
        if index % 5 == 2:
            score = 2 - score  # one shard's results reversed
        training.add(("rapid", 1200), score, [(8, x)])
    fit_ = BandFit(("rapid", 1200), 120_000, 700, True)
    _cross(training, ("rapid", 1200), fit_)
    assert any("reliability" in r for r in fit_.reasons) and fit_.cross["failing_bins"]


def test_selection_never_reads_the_validation_month(trained, fast) -> None:
    training, fits, pools = trained
    before = {k: (f.points, f.reasons[:]) for k, f in fits.items()}
    curves = Curves(fits, pools)
    validate(training, _validation(curves, BANDS, n=5_000), curves)
    assert {k: (f.points, f.reasons) for k, f in fits.items()} == before


# -- QM-D §10.8: the gates -------------------------------------------------------------------------


def test_the_gates_pass_for_the_true_curves(trained, fast) -> None:
    training, fits, pools = trained
    curves = Curves(fits, pools)
    report = validate(training, _validation(curves, BANDS), curves)
    assert report.passed == {"gate1": True, "gate2": True, "gate3": True}
    for interval in report.aggregate["difference_95"].values():
        assert interval[0] < interval[1] < 0
    assert report.aggregate["bootstrap"]["units"] == "games"
    assert report.aggregate["games"] == 200_000


def _substitute(fits: dict, make) -> dict:
    return {key: replace(f, points=make(f), reasons=f.reasons[:]) for key, f in fits.items()}


def test_a_logistic_table_fails_gate_3_on_the_shelf_curve(trained, fast) -> None:
    training, fits, pools = trained
    logistic_tables = _substitute(
        fits, lambda f: tuple(curve_points(x, f.logistic) for x in MONOTONE_V1_KNOTS)
    )
    curves = Curves(logistic_tables, pools)
    report = validate(training, _validation(curves, BANDS), curves)
    assert not report.passed["gate3"]
    assert set(report.per_band) == {"rapid 1000", "rapid 1400"}  # no band is dropped (review B2)


def test_a_curve_thirty_percent_off_fails_gate_2(trained, fast) -> None:
    training, fits, pools = trained
    off = _substitute(fits, lambda f: tuple(curve_points(x, round(f.logistic * 1.3))
                                            for x in MONOTONE_V1_KNOTS))  # fmt: skip
    curves = Curves(off, pools)
    assert not validate(training, _validation(curves, BANDS), curves).passed["gate2"]


def test_the_band_logistic_falls_back_to_the_nearest_fittable_band(trained, fast) -> None:
    """Re-review B2: a band with no training positions, or a logistic at a bound."""

    training, fits, pools = trained
    bound = BandFit(("rapid", 1600), 150_000, 4000, False, reasons=["not selected"])
    curves = Curves({**fits, ("rapid", 1600): bound}, pools)
    unseen = curves.of(("rapid", 2400))
    assert (unseen.table_band, unseen.logistic_band, unseen.fallback) == (1400, 1400, True)
    at_bound = curves.of(("rapid", 1600))
    assert (at_bound.logistic_band, at_bound.fallback) == (1400, True)
    own = curves.of(("rapid", 1000))
    assert (own.logistic_band, own.fallback, own.own) == (1000, False, True)
    assert curves.of(("blitz", 1200)) is None  # no kept band in the time class: outside
    validation = _validation(curves, {**BANDS, ("rapid", 2400): shelf}, n=5_000)
    report = validate(training, validation, curves)
    assert report.aggregate["fallback_positions"] == 5_000
    assert report.per_band["rapid 2400"]["clamped"] and "rapid 2400" not in report.reliability


def test_the_plateau_report_counts_worsening_moves_inside_a_plateau(trained, fast) -> None:
    """QM-D §5 (review C3, re-review C3): improving moves never count."""

    training, fits, pools = trained
    flat = list(fits[("rapid", 1400)].points)
    i, j = MONOTONE_V1_KNOTS.index(100), MONOTONE_V1_KNOTS.index(300)
    flat[i : j + 1] = [flat[i]] * (j - i + 1)
    plateau = _substitute(fits, lambda f: tuple(flat) if f.key == ("rapid", 1400) else f.points)
    curves = Curves(plateau, pools)
    validation = Validation(curves)
    # plies 1–8 at +0.20; ply 9 is White's move, ply 10 Black's (mover's view in comments)
    opening = [("cp", 20)] * 8
    improving = [*opening, ("cp", 250), ("cp", -150)]  # White +0.20 → +2.50; Black −2.50 → +1.50
    validation.add(("rapid", 1400), 1, [(8, 20)], improving)
    inside = [*opening, ("cp", -250), ("cp", -150)]  # White +0.20 → −2.50; Black +2.50 → +1.50
    validation.add(("rapid", 1400), 1, [(8, 20)], inside)
    leaving = [*opening, ("cp", -150), ("cp", -250)]  # White +0.20 → −1.50; Black +1.50 → +2.50
    validation.add(("rapid", 1400), 1, [(8, 20)], leaving)
    sums = validation.sums[("rapid", 1400)]
    # worse: the three White moves of `inside` and `leaving`, and Black's 2.50 → 1.50; only the
    # last stays inside the plateau [1.00, 3.00]
    assert (sums.moves, sums.worse, sums.plateau_zero) == (6, 3, 1)
    report = validate(training, validation, curves)
    assert report.plateaus["rapid 1400"]["plateaus_below_600"][0] == [100, 300]


def test_gate_4_reports_every_kept_band(trained) -> None:
    """Q2 review C1: a kept band is MEASURED or UNESTIMABLE, never silently missing."""

    _, fits, _ = trained
    sparse = BandFit(("classical", 1800), 150_000, 800, True, points=fits[("rapid", 1400)].points,
                     weighted_unestimated=(0, 10))  # fmt: skip
    refused = BandFit(("classical", 2000), 50_000, 800, False, reasons=["positions"])
    flags = weight_flags({**fits, sparse.key: sparse, refused.key: refused})
    assert set(flags) == {"rapid 1000", "rapid 1400", "classical 1800"}
    assert flags["classical 1800"] == {"status": "UNESTIMABLE", "unestimated": [0, 10]}
    assert flags["rapid 1400"]["status"] == "MEASURED"
    assert flags["rapid 1400"]["flagged"] == (flags["rapid 1400"]["deviation"] > 10)


def test_the_deployed_loss_on_hand_values() -> None:
    row = rows([1000])[0]
    assert row[6] == 0.5 and math.isclose(row[1], math.log(2)) and row[4] == 0  # a draw at ½
    saturated = rows([2000])[0]  # a saturated p, scored against a loss
    assert saturated[6] == 1.0 and math.isclose(saturated[0], math.log(4000)) and saturated[3] == 1


def test_points_of_reads_the_source_knots() -> None:
    points = tuple(curve_points(x, 900) for x in MONOTONE_V1_KNOTS)
    values = points_of(points)
    assert values[1500] == 1000 and values[1500 + 100] == points[10]
    assert values[1500 - 100] == 2000 - points[10]


# -- Q-D §7.4: the engine-scale check --------------------------------------------------------------


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


# -- QM-D §10.10: streams and the run ---------------------------------------------------------------


def _zst(path: Path, text: str) -> Path:
    path.with_suffix("").write_text(text)
    subprocess.run(["zstd", "-qf", str(path.with_suffix("")), "-o", str(path)], check=True)
    return path


def test_a_truncated_stream_fails(tmp_path: Path) -> None:
    good = _zst(tmp_path / "g.pgn.zst", PGN * 50)
    stream = cli.Stream(good.as_uri())
    assert len(list(games(stream.lines()))) == 250
    assert stream.status()["failures"] == []
    cut = tmp_path / "cut.pgn.zst"
    cut.write_bytes(good.read_bytes()[:-20])
    stream = cli.Stream(cut.as_uri())
    list(stream.lines())
    assert any("zstd" in f for f in stream.status()["failures"])


def test_a_short_read_fails(tmp_path: Path, monkeypatch) -> None:
    good = _zst(tmp_path / "g.pgn.zst", PGN)
    size = good.stat().st_size
    monkeypatch.setattr(cli, "content_length", lambda url: size + 1)
    stream = cli.Stream(good.as_uri())
    list(stream.lines())
    assert stream.status()["failures"] == [f"read {size} bytes of {size + 1}"]


def _synthetic_pgn(n: int, seed: int) -> str:
    """Rapid 1200 games: evals on plies 1–8, ply 8 at x, the result drawn from shelf(x)."""

    rng = random.Random(seed)
    out = []
    for _ in range(n):
        x = rng.randint(-800, 800)
        score = _score(rng, shelf(x))
        result = {2: "1-0", 1: "1/2-1/2", 0: "0-1"}[score]
        moves = []
        for ply in range(1, 9):
            value = 0.1 if ply < 8 else x / 100
            number = f"{(ply + 1) // 2}." if ply % 2 else f"{ply // 2}..."
            moves.append(f"{number} a3 {{ [%eval {value:.2f}] }}")
        out.append(f'[Event "Rated Rapid game"]\n[Result "{result}"]\n[WhiteElo "1250"]\n'
                   f'[BlackElo "1250"]\n[TimeControl "600+0"]\n\n{" ".join(moves)} {result}\n')  # fmt: skip
    return "\n".join(out)


@pytest.fixture(scope="module")
def months(tmp_path_factory) -> tuple[str, str]:
    root = tmp_path_factory.mktemp("months")
    train = _zst(root / "train.pgn.zst", _synthetic_pgn(110_000, 1))
    validate_ = _zst(root / "validate.pgn.zst", _synthetic_pgn(30_000, 2))
    return train.as_uri(), validate_.as_uri()


class _Engine:
    def close(self) -> None:
        pass


def _run(monkeypatch, tmp_path: Path, months, *extra: str) -> tuple[int, dict]:
    from calliope.facts.search import StockfishEngine
    from calliope.reasoning import grading
    from tools.calibrate_curve import gates

    # a synthetic month of 110 000 positions has noisy shards: the deviation bound is not
    # what this test is about, so both the tool and the loader take a looser one
    monkeypatch.setattr(gates, "MAX_SHARD_DEVIATION", 100)
    monkeypatch.setattr(grading, "MAX_SHARD_DEVIATION", 100)
    monkeypatch.setattr(gates, "RESAMPLES", 100)
    monkeypatch.setattr(StockfishEngine, "start", staticmethod(lambda path: _Engine()))
    monkeypatch.setattr(cli, "sample", lambda training: [])
    monkeypatch.setattr(cli, "engine_evaluator", lambda engine: None)
    monkeypatch.setattr(cli, "check", lambda positions, evaluate: ScaleResult(
        1.0, 1000, {}, 1.0, 1.0, 2000, 0, "d", []))  # fmt: skip
    monkeypatch.setattr(cli, "published_games", lambda url: None)
    train, validate_ = months
    code = cli.main(["--name", "synthetic_v2", "--train", train, "--validate", validate_,
                     "--table-dir", str(tmp_path), "--report-dir", str(tmp_path), *extra])  # fmt: skip
    return code, json.loads((tmp_path / "synthetic_v2.json").read_text())


def test_a_whole_run_writes_a_table_that_loads(monkeypatch, tmp_path: Path, months) -> None:
    code, report = _run(monkeypatch, tmp_path, months)
    assert report["gates"] == {"gate1": True, "gate2": True, "gate3": True}, report["bands"]
    assert code == 0 and report["table_written"] and not report["partial"]
    assert report["training"]["stream"]["failures"] == []
    assert report["validation"]["stream"]["stopped_at_target"]
    table = load_curve_table((tmp_path / "synthetic_v2.toml").read_bytes())
    assert [(b.time_class, b.low) for b in table.bands] == [("rapid", 1200)]
    assert table.bands[0].positions == 110_000


def test_a_byte_limited_run_is_exploratory(monkeypatch, tmp_path: Path, months) -> None:
    """QM-D §8.3, re-review C4: a partial report and never a table, even when the gates pass."""

    size = Path(months[0].removeprefix("file://")).stat().st_size
    code, report = _run(monkeypatch, tmp_path, months, "--train-bytes", str(size + 1))
    assert report["partial"] and all(report["gates"].values())
    assert code == 0 and not report["table_written"]
    assert not (tmp_path / "synthetic_v2.toml").exists()
