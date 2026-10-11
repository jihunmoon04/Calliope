"""The two passes over Lichess games: training aggregates, then the held-out month scored against
the fixed curves (QM-D §6.2: the table is fixed before the validation month is read)."""

from __future__ import annotations

import random
from array import array
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from tools.calibrate_curve.pgn import CLIP, FIRST_PLY, Game, evals, kept, samples

if TYPE_CHECKING:
    from tools.calibrate_curve.gates import Curves

SHARDS = 5
SAMPLE_EVERY = 997  # every 997th used training game offers positions to the engine-scale check
STRATA = ((0, 100), (100, 300), (300, 600), (600, 1001))  # |eval| ≤ 1000 (Q-D §7.4)
BANDS = ((40, "EXCELLENT"), (100, "GOOD"), (200, "INACCURACY"), (400, "MISTAKE"))
WORSE = 10  # a move that worsens the mover's eval by at least 10 cp (QM-D §5, plateaus)

Key = tuple[str, int]  # (time class, band)


def grade_name(loss: int) -> str:
    return next((name for bound, name in BANDS if loss < bound), "BLUNDER")


@dataclass
class Training:
    """Q-D §7.1 steps 2–3, plus what the selection and the report need from the training month."""

    cells: dict[Key, dict[int, list[int]]] = field(default_factory=dict)  # x -> [n, half points]
    shards: dict[Key, list[dict[int, list[int]]]] = field(default_factory=dict)
    weighted: dict[Key, dict[int, list[float]]] = field(default_factory=dict)  # game weight 1
    selection: dict[tuple[Key, bool], list[int]] = field(default_factory=dict)
    candidates: list[list[tuple[str, int, int]]] = field(
        default_factory=lambda: [[] for _ in STRATA]
    )  # (movetext, ply, x) per stratum
    games_read: int = 0
    games_used: int = 0
    games_eval_gap: int = 0  # evaluated games skipped: an eval missing before the last (QM-D §8.1)
    positions: int = 0
    rng: random.Random = field(default_factory=lambda: random.Random(20261010))

    def feed(self, game: Game) -> None:
        self.games_read += 1
        k = kept(game)
        if k is None:
            return
        key = (k.time_class, k.band)
        sel = self.selection.setdefault((key, k.evaluated), [0, 0, 0, 0])
        sel[0] += 1  # games
        sel[1] += k.score  # White's half points
        sel[2] += k.score == 1  # draws
        sel[3] += k.rating
        if k.evaluated:
            values = evals(game.movetext)
            if values is None:
                self.games_eval_gap += 1
                return
            self.add(key, k.score, list(samples(values)), game.movetext)

    def add(self, key: Key, score: int, found: list[tuple[int, int]], movetext: str = "") -> None:
        """One used game: its samples `(ply, x)` and White's score in half points."""

        if not found:
            return
        index = self.games_used
        self.games_used += 1
        self.positions += len(found)
        cells = self.cells.setdefault(key, {})
        shard = self.shards.setdefault(key, [{} for _ in range(SHARDS)])[index % SHARDS]
        weighted = self.weighted.setdefault(key, {})
        w = 1.0 / len(found)
        for _ply, x in found:
            c = cells.get(x)
            if c is None:
                cells[x] = [1, score]
            else:
                c[0] += 1
                c[1] += score
            s = shard.get(x)
            if s is None:
                shard[x] = [1, score]
            else:
                s[0] += 1
                s[1] += score
            g = weighted.get(x)
            if g is None:
                weighted[x] = [w, w * score / 2]
            else:
                g[0] += w
                g[1] += w * score / 2
        if movetext and index % SAMPLE_EVERY == 0:
            for i, (lo, hi) in enumerate(STRATA):
                eligible = [(p, x) for p, x in found if lo <= abs(x) < hi]
                if eligible:
                    ply, x = self.rng.choice(eligible)
                    self.candidates[i].append((movetext, ply, x))


CURVES = 5  # (a) table, (b) default, (c) pooled, (d) band logistic, (e) table at 2 × bandwidth


@dataclass
class BandSums:
    """One key's validation sums, for the report (QM-D §6.2) and the plateau report (§5)."""

    positions: int = 0
    fallback: int = 0  # positions whose (d) is a fallback (QM-D §6.2, re-review B2)
    log_loss: list[float] = field(default_factory=lambda: [0.0] * CURVES)
    brier: list[float] = field(default_factory=lambda: [0.0] * CURVES)
    # reliability per curve a, d, e: ten bins of [n, Σp, Σy] (own bands only, gate 3)
    bins: list[list[list[float]]] = field(
        default_factory=lambda: [[[0.0, 0.0, 0.0] for _ in range(10)] for _ in range(3)]
    )
    # cluster sums of y − p per bin of (a), games as clusters: Σr, Σn, Σr², Σrn, Σn²
    clusters: list[list[float]] = field(default_factory=lambda: [[0.0] * 5 for _ in range(10)])
    mate_allowing: dict[str, int] = field(default_factory=dict)
    moves: int = 0
    worse: int = 0
    plateau_zero: int = 0
    erased: int = 0
    converse: int = 0


@dataclass
class Validation:
    """The held-out month (Q-D §7.5 gate 1), scored as it streams against fixed curves."""

    curves: Curves
    sums: dict[Key, BandSums] = field(default_factory=dict)
    # per game of the population, for the game-level bootstrap (QM-D §8.2): positions, then the
    # summed log loss under (a), (b), (c), (d)
    game_n: array = field(default_factory=lambda: array("I"))
    game_loss: list[array] = field(default_factory=lambda: [array("d") for _ in range(4)])
    games_read: int = 0
    games_used: int = 0
    games_eval_gap: int = 0
    positions: int = 0

    def feed(self, game: Game) -> None:
        self.games_read += 1
        k = kept(game)
        if k is None or not k.evaluated:
            return
        values = evals(game.movetext)
        if values is None:
            self.games_eval_gap += 1
            return
        self.add((k.time_class, k.band), k.score, list(samples(values)), values)

    def add(
        self, key: Key, score: int, found: list[tuple[int, int]], values: list | None = None
    ) -> None:
        """One held-out game: its samples, White's score in half points, and its evals."""

        if not found:
            return
        self.games_used += 1
        self.positions += len(found)
        scored = self.curves.of(key)
        if scored is None:  # a time class with no kept band: outside the population
            return
        sums = self.sums.setdefault(key, BandSums())
        y = score  # 0, 1, 2: the y code
        t = y / 2
        game = [0.0] * CURVES
        clusters: dict[int, list[float]] = {}
        for _ply, x in found:
            row = scored.rows[x + CLIP]
            for c in range(CURVES):
                loss = row[c][y]
                game[c] += loss
                sums.brier[c] += row[c][3 + y]
            for slot, c in ((0, 0), (1, 3), (2, 4)):
                p = row[c][6]
                b = sums.bins[slot][min(9, int(p * 10))]
                b[0] += 1
                b[1] += p
                b[2] += t
            pa = row[0][6]
            cell = clusters.setdefault(min(9, int(pa * 10)), [0.0, 0.0])
            cell[0] += t - pa
            cell[1] += 1
        n = len(found)
        sums.positions += n
        sums.fallback += n if scored.fallback else 0
        for c in range(CURVES):
            sums.log_loss[c] += game[c]
        for index, (r, m) in clusters.items():
            acc = sums.clusters[index]
            acc[0] += r
            acc[1] += m
            acc[2] += r * r
            acc[3] += r * m
            acc[4] += m * m
        self.game_n.append(n)
        for c in range(4):
            self.game_loss[c].append(game[c])
        if values:
            self._moves(values, scored, sums)

    def _moves(self, values: list[tuple[str, int]], scored, sums: BandSums) -> None:
        """Gate 6 (mate-allowing moves) and the plateau report (QM-D §5) on consecutive evals."""

        for ply in range(2, len(values) + 1):
            before, after = values[ply - 2], values[ply - 1]
            sign = 1 if ply % 2 == 1 else -1  # the mover of this ply: White on odd plies
            if before[0] != "cp":
                continue
            b = max(-CLIP, min(CLIP, sign * before[1]))
            if after[0] == "mate" and sign * after[1] < 0:  # Q-D §7.5 gate 6
                name = grade_name(scored.table[b + CLIP])
                sums.mate_allowing[name] = sums.mate_allowing.get(name, 0) + 1
                continue
            if after[0] != "cp" or ply <= FIRST_PLY:
                continue
            a = max(-CLIP, min(CLIP, sign * after[1]))
            loss_a = max(0, scored.table[b + CLIP] - scored.table[a + CLIP])
            loss_d = max(0, scored.logistic[b + CLIP] - scored.logistic[a + CLIP])
            sums.moves += 1
            if a <= b - WORSE:
                sums.worse += 1
                sums.plateau_zero += loss_a == 0
            sums.erased += loss_a < 40 and loss_d >= 100
            sums.converse += loss_d < 40 and loss_a >= 100
