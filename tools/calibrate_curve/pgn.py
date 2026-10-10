"""Streaming Lichess PGN: games, the filters of Q-D §7.1 step 2, and the samples of step 3."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

EVAL = re.compile(r"\[%eval (-?\d+(?:\.\d+)?|#-?\d+)\]")
RESULTS = {"1-0": 2, "1/2-1/2": 1, "0-1": 0}  # White's score in half points
CLIP = 1500
FIRST_PLY = 8
MAX_GAP = 100
BAND_WIDTH = 200


@dataclass(slots=True)
class Game:
    headers: dict[str, str]
    movetext: str


def games(lines: Iterable[str]) -> Iterator[Game]:
    """Games of a PGN stream: header lines, then movetext lines up to the next `[Event`."""

    headers: dict[str, str] = {}
    movetext: list[str] = []
    for line in lines:
        if line.startswith("["):
            if line.startswith("[Event ") and headers:
                yield Game(headers, " ".join(movetext))
                headers, movetext = {}, []
            key, _, value = line[1:].partition(" ")
            headers[key] = value.strip().rstrip("]").strip('"')
        elif line.strip():
            movetext.append(line.strip())
    if headers:
        yield Game(headers, " ".join(movetext))


def time_class(control: str) -> str | None:
    """Lichess's rule on `base + 40 × increment` seconds (Q-D §3); None for correspondence."""

    base, sep, increment = control.partition("+")
    if not sep or not base.isdigit() or not increment.isdigit():
        return None
    duration = int(base) + 40 * int(increment)
    if duration < 180:
        return "bullet"
    if duration < 480:
        return "blitz"
    if duration < 1500:
        return "rapid"
    return "classical"


@dataclass(frozen=True, slots=True)
class Kept:
    """A game that passes every filter but `%eval` (Q-D §7.1 step 2)."""

    time_class: str
    band: int  # of the average rating
    rating: int  # the average rating, floored
    score: int  # White's score in half points
    evaluated: bool


def kept(game: Game) -> Kept | None:
    h = game.headers
    if "Rated" not in h.get("Event", "") or h.get("Variant", "Standard") != "Standard":
        return None
    score = RESULTS.get(h.get("Result", ""))
    if score is None:
        return None
    try:
        white, black = int(h["WhiteElo"]), int(h["BlackElo"])
    except (KeyError, ValueError):
        return None
    if abs(white - black) > MAX_GAP:
        return None
    tc = time_class(h.get("TimeControl", "-"))
    if tc is None:
        return None
    rating = (white + black) // 2
    band = rating // BAND_WIDTH * BAND_WIDTH
    return Kept(tc, band, rating, score, "%eval" in game.movetext)


def evals(movetext: str) -> list[tuple[str, int]]:
    """Every eval comment in ply order, White's view: ("cp", n) or ("mate", n), n < 0 = Black."""

    out: list[tuple[str, int]] = []
    for token in EVAL.findall(movetext):
        if token.startswith("#"):
            out.append(("mate", int(token[1:])))
        else:
            out.append(("cp", round(float(token) * 100)))
    return out


def samples(values: list[tuple[str, int]]) -> Iterator[tuple[int, int]]:
    """(ply, x) of step 3: centipawn evals from ply 8 on, clipped to ±1500; mates left out."""

    for ply, (kind, value) in enumerate(values, start=1):
        if ply >= FIRST_PLY and kind == "cp":
            yield ply, max(-CLIP, min(CLIP, value))
