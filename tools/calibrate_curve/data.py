"""The two passes over Lichess games: training aggregates and the held-out validation set."""

from __future__ import annotations

import random
from array import array
from dataclasses import dataclass, field

from tools.calibrate_curve.pgn import Game, evals, kept, samples

SHARDS = 5
BUCKETS = 2000  # validation games are grouped by arrival order for the bootstrap (record §2)
SAMPLE_EVERY = 997  # every 997th used training game offers positions to the engine-scale check
STRATA = ((0, 100), (100, 300), (300, 600), (600, 1001))  # |eval| ≤ 1000 (Q-D §7.4)

Key = tuple[str, int]  # (time class, band)


@dataclass
class Training:
    """Q-D §7.1 steps 2–3, plus what the gates and the report need from the training month."""

    cells: dict[Key, dict[int, list[int]]] = field(default_factory=dict)  # x -> [n, half points]
    shards: dict[Key, list[dict[int, list[int]]]] = field(default_factory=dict)
    weighted: dict[Key, dict[int, list[float]]] = field(default_factory=dict)  # game weight 1
    selection: dict[tuple[Key, bool], list[int]] = field(default_factory=dict)
    candidates: list[list[tuple[str, int, int]]] = field(
        default_factory=lambda: [[] for _ in STRATA]
    )  # (movetext, ply, x) per stratum
    games_read: int = 0
    games_used: int = 0
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
            self.add(key, k.score, list(samples(evals(game.movetext))), game.movetext)

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


@dataclass
class Validation:
    """The held-out month (Q-D §7.5 gate 1), kept compactly for the gates after the fit."""

    keys: dict[Key, int] = field(default_factory=dict)
    buckets: list[array] = field(default_factory=lambda: [array("I") for _ in range(BUCKETS)])
    mate_allowing: list[tuple[int, int]] = field(default_factory=list)  # (key id, cp before)
    games_read: int = 0
    games_used: int = 0
    positions: int = 0

    def key_id(self, key: Key) -> int:
        if key not in self.keys:
            self.keys[key] = len(self.keys)
        return self.keys[key]

    def feed(self, game: Game) -> None:
        self.games_read += 1
        k = kept(game)
        if k is None or not k.evaluated:
            return
        values = evals(game.movetext)
        self.add((k.time_class, k.band), k.score, list(samples(values)), values)

    def add(
        self, key: Key, score: int, found: list[tuple[int, int]], values: list | None = None
    ) -> None:
        """One held-out game: its samples, White's score in half points, and its evals."""

        if not found:
            return
        kid = self.key_id(key)
        bucket = self.buckets[self.games_used % BUCKETS]
        self.games_used += 1
        self.positions += len(found)
        y = score  # 0, 1, 2: the y code
        for _ply, x in found:
            bucket.append((kid << 14) | ((x + 1500) << 2) | y)
        values = values or []
        for ply in range(2, len(values) + 1):  # Q-D §7.5 gate 6
            before, after = values[ply - 2], values[ply - 1]
            white = ply % 2 == 1  # the mover of this ply
            against = after[0] == "mate" and (after[1] < 0 if white else after[1] > 0)
            if against and before[0] == "cp":
                self.mate_allowing.append((kid, before[1] if white else -before[1]))


def unpack(packed: int) -> tuple[int, int, int]:
    """(key id, x, y code) of a packed validation position."""

    return packed >> 14, ((packed >> 2) & 0xFFF) - 1500, packed & 3
