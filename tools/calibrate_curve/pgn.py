"""Streaming Lichess PGN: games, the filters of Q-D §7.1 step 2, and the samples of step 3."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from calliope.reasoning.grading import time_class  # the rule lives in grading (AS-D S10)

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


COMMENT = re.compile(r"\{([^}]*)\}")
MOVE_NUMBER = re.compile(r"\d+\.+")
NOT_MOVES = {"1-0", "0-1", "1/2-1/2", "*"}


def _moves(text: str) -> int:
    """The number of moves in a stretch of movetext without comments."""

    n = 0
    for token in text.split():
        if token in NOT_MOVES or token.startswith("$"):
            continue
        number = MOVE_NUMBER.match(token)
        if number and number.end() == len(token):
            continue  # `12.` or `12...`
        n += 1
    return n


def _value(token: str) -> tuple[str, int]:
    if token.startswith("#"):
        return "mate", int(token[1:])
    return "cp", round(float(token) * 100)


def evals(movetext: str) -> list[tuple[str, int]] | None:
    """The eval after each ply from 1 to the last evaluated one, White's view: ("cp", n) or
    ("mate", n), n < 0 = Black. Each eval belongs to the move it follows (QM-D §8.1): None when a
    ply before the last eval has none, or the movetext has variations (the game is skipped)."""

    if "(" in movetext:
        return None
    out: list[tuple[str, int]] = []
    ply = 0
    for i, part in enumerate(COMMENT.split(movetext)):
        if i % 2 == 0:
            ply += _moves(part)
            continue
        found = EVAL.search(part)
        if found is None:
            continue
        if ply != len(out) + 1:
            return None  # a gap before this eval, or a second eval on one ply
        out.append(_value(found.group(1)))
    return out


def samples(values: list[tuple[str, int]]) -> Iterator[tuple[int, int]]:
    """(ply, x) of step 3: centipawn evals from ply 8 on, clipped to ±1500; mates left out."""

    for ply, (kind, value) in enumerate(values, start=1):
        if ply >= FIRST_PLY and kind == "cp":
            yield ply, max(-CLIP, min(CLIP, value))
