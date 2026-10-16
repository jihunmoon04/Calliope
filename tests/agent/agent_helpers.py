"""Sessions over the synthetic engine for the agent's tests."""

from __future__ import annotations

from helpers import Failing
from synthetic import engine

from calliope.agent import Limits, Session
from calliope.agent.session import pgn_of
from calliope.server import game_key, parse_game

GAME = "1. e4 d5 2. exd5 Nf6 3. Nf3 Nxd5 4. Be2 e6 5. O-O Be7 *\n"
PROMOTION = '[FEN "8/P6k/8/8/8/8/8/K7 w - - 0 1"]\n\n1. a8=Q Kg6 2. Qb8 *\n'


def gid(pgn: str | None = None, fen: str | None = None, moves: list[str] | None = None) -> str:
    """The id `open_game` gives a game when no other record shares its 16 digits (AG4-D §2.1)."""

    text = pgn if pgn is not None else pgn_of(fen, moves or [])
    return "g-" + game_key(parse_game(text).game)[:16]


G1 = gid(GAME)


def session(tmp_path, limits: Limits | None = None, start=engine, **options) -> Session:
    return Session(tmp_path, start, limits if limits is not None else Limits(), **options)


class Starts:
    """Engines started in turn: the first may fail on some calls (`Failing`), later ones not."""

    def __init__(self, fail_on: set[int]) -> None:
        self.fail_on = fail_on
        self.started: list = []

    def __call__(self):
        port = Failing(self.fail_on) if not self.started else engine()
        self.started.append(port)
        return port
