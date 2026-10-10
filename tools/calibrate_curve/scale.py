"""The engine-scale check of Q-D §7.4: Lichess cp against Calliope's release profile."""

from __future__ import annotations

import hashlib
import io
import random
import statistics
from collections.abc import Callable
from dataclasses import dataclass

import chess
import chess.pgn

from calliope.facts import EngineProfile
from calliope.facts.search import EngineInput, SearchRequest
from tools.calibrate_curve.data import Training

PER_STRATUM = 500  # 2 000 positions over four strata of |eval|
BUCKETS = ((100, 300), (300, 600), (600, 1001))
BUCKET_TOLERANCE = 0.15
SIGN_MIN = 0.95
TRIM = 0.02
TRIM_TOLERANCE = 0.03
SEED = 20261010

Evaluate = Callable[[str], int | None]  # FEN → White-view cp, None for a mate


@dataclass
class ScaleResult:
    k: float
    permille: int  # the stored cp_ratio_permille (Q-D §7.4 steps 1–2)
    bucket_ratios: dict[str, float]
    sign_agreement: float
    trimmed_k: float
    positions: int
    skipped_mates: int
    sample_digest: str
    failures: list[str]

    @property
    def passed(self) -> bool:
        return not self.failures


def sample(training: Training) -> list[tuple[str, int]]:
    """(FEN, Lichess cp) of up to 500 positions per stratum, drawn with a fixed seed."""

    rng = random.Random(SEED)
    out = []
    for candidates in training.candidates:
        chosen = rng.sample(candidates, min(PER_STRATUM, len(candidates)))
        for movetext, ply, x in chosen:
            out.append((fen_at(movetext, ply), x))
    return out


def fen_at(movetext: str, ply: int) -> str:
    """The position after `ply` plies, as the engine adapter expects it (legal ep, fullmove 1)."""

    game = chess.pgn.read_game(io.StringIO(movetext))
    board = game.board()
    for i, move in enumerate(game.mainline_moves()):
        if i == ply:
            break
        board.push(move)
    fields = board.fen(en_passant="legal").split(" ")
    fields[5] = "1"
    return " ".join(fields)


RELEASE = EngineProfile()


def engine_evaluator(engine, profile: EngineProfile = RELEASE) -> Evaluate:
    """Rank 1 of a release-profile search, from White's view; None for a mate score."""

    def evaluate(fen: str) -> int | None:
        raw = engine.search(SearchRequest(EngineInput(fen, ()), profile, None, profile.multipv))
        kind, value = raw.lines[0].score
        if kind != "cp":
            return None
        return value if fen.split(" ")[1] == "w" else -value

    return evaluate


def _ratio(pairs: list[tuple[int, int]]) -> float:
    """Theil–Sen through the origin: the median of the slopes `x_C / x_L`."""

    return statistics.median(c / lichess for lichess, c in pairs)


def check(positions: list[tuple[str, int]], evaluate: Evaluate) -> ScaleResult:
    pairs: list[tuple[int, int]] = []
    skipped = 0
    for fen, lichess in positions:
        mine = evaluate(fen)
        if mine is None:
            skipped += 1
            continue
        pairs.append((lichess, mine))
    digest = hashlib.sha256("\n".join(f for f, _ in positions).encode()).hexdigest()
    scored = [(lx, cx) for lx, cx in pairs if abs(lx) >= 100]
    failures = []
    if len(scored) < 100:
        return ScaleResult(float("nan"), 1000, {}, 0.0, float("nan"), len(pairs), skipped,
                           digest, ["fewer than 100 positions with |eval| ≥ 100"])  # fmt: skip
    k = _ratio(scored)
    r = round(1000 * k)
    permille = 1000 if abs(r - 1000) <= 100 else r
    buckets = {}
    for lo, hi in BUCKETS:
        part = [(lx, cx) for lx, cx in scored if lo <= abs(lx) < hi]
        if part:
            buckets[f"{lo}-{hi - 1}"] = _ratio(part)
            if abs(buckets[f"{lo}-{hi - 1}"] - k) > BUCKET_TOLERANCE * k:
                failures.append(
                    f"bucket {lo}-{hi - 1} ratio {buckets[f'{lo}-{hi - 1}']:.3f} vs k {k:.3f}"
                )
    signs = sum((lx > 0) == (cx > 0) for lx, cx in scored) / len(scored)
    if signs < SIGN_MIN:
        failures.append(f"sign agreement {signs:.3f} < {SIGN_MIN}")
    residuals = sorted(scored, key=lambda p: abs(p[1] - k * p[0]))
    keep = residuals[: len(residuals) - int(TRIM * len(residuals))]
    trimmed = _ratio(keep)
    if abs(trimmed - k) > TRIM_TOLERANCE:
        failures.append(f"trimming 2 % moves k from {k:.3f} to {trimmed:.3f}")
    return ScaleResult(k, permille, buckets, signs, trimmed, len(pairs), skipped, digest, failures)
