"""Games and engines for the server tests."""

from __future__ import annotations

from dataclasses import replace

from synthetic import IDENTITY, engine, synthetic

from calliope.facts import EngineError
from calliope.facts.search import ScriptedEngine
from calliope.server import EngineSlot

RATED = """[Event "test"]
[Site "https://www.chess.com/game/live/1"]
[White "Alice"]
[Black "Bob"]
[WhiteElo "1500"]
[BlackElo "1480"]
[TimeControl "600"]

1. e4 d5 2. exd5 Nf6 3. Nf3 Nxd5 4. Be2 e6 5. O-O Be7 *
"""
# SANs that differ from their UCI: a capture, castling (AS-D §10.2)
UNRATED = "1. e4 d5 2. exd5 Nf6 3. Nf3 Nxd5 4. Be2 e6 5. O-O Be7 *\n"
# a FEN header and a promotion
PROMOTION = """[FEN "8/P6k/8/8/8/8/8/K7 w - - 0 1"]

1. a8=Q Kg6 2. Qb8 *
"""


def slot(port=None) -> tuple[EngineSlot, list]:
    """A slot over the synthetic engine; the list records every engine it started."""

    started: list = []

    def start():
        started.append(port if port is not None and not started else engine())
        return started[-1]

    return EngineSlot(start), started


def other_identity():
    return replace(IDENTITY, binary_sha256="6" * 64)


class Failing(ScriptedEngine):
    """The synthetic engine that raises `EngineError` on the calls listed (1-based)."""

    def __init__(self, fail_on: set[int], identity=IDENTITY) -> None:
        super().__init__(identity, synthetic())
        self.fail_on = fail_on

    def search(self, request):
        if len(self.calls) + 1 in self.fail_on:
            self.calls.append(request)
            raise EngineError("engine process exited")
        return super().search(request)
