"""Game ids and records (AG4-D §2): ids derived from the game, records created once.

A game id is `g-` and the first 16 hex digits of its `game_key` (AG-D §8), or all 64 when another
record shares those 16 (§2.1). The record `<data>/agent/games/<game_key>.json` holds exactly the
key's preimage — `start_fen`, `moves` and `headers` as `game_input` normalizes them — in the key's
canonical JSON, so one key is one byte string (§2.2). It is created with `os.link`, only if absent,
and never replaced; a different existing record is damaged and refused. Every game the agent works
on is built from its record by `from_record` (§2.4), in the opening process too.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import chess
import chess.pgn

from calliope.facts import RootSpec
from calliope.reasoning import SHIPPED, CurveSource, resolve
from calliope.results import GameInput, GameMove
from calliope.server import (
    HEADERS,
    ParsedGame,
    canonical,
    game_input,
    game_key,
    grading_for,
    temporary_name,
)

RECORD_VERSION = "agent_game_v1"
MAX_BYTES = 256 * 1024  # a record, and an input text, in UTF-8 bytes (§2.2; web.MAX_BODY)
SHORT = 16  # hex digits of a short id
FIELDS = {"v", "game_key", "start_fen", "moves", "headers"}
TAGS = {name: tag for tag, name in HEADERS.items()}  # internal name -> PGN tag
FALLBACK = (  # `parse_game`'s default-curve warning, for a game built from its record
    "graded with the default curve (logistic10, scale {scale}): "
    "the PGN gives no ratings and time class to choose one"
)
_ID = re.compile(r"g-([0-9a-f]{16}|[0-9a-f]{64})")
_KEY = re.compile(r"[0-9a-f]{64}")


class GameError(ValueError):
    """An id that names no game, or names it ambiguously, or a damaged record (a tool error)."""


def pgn_tags(headers) -> dict[str, str]:
    """The inverse of `HEADERS` (§2.4, review N3): internal names to PGN tags, ratings written as
    decimal strings, so `grading_for` and `game_input` read them as the original tags."""

    return {TAGS[name]: str(value) for name, value in headers.items()}


def record_of(game: GameInput) -> dict:
    """The record of a normalized game (a `ParsedGame`'s `game`)."""

    return {
        "v": RECORD_VERSION,
        "game_key": game_key(game),
        "start_fen": game.start_fen,
        "moves": [m.uci for m in game.moves],
        "headers": dict(game.headers),
    }


def encode(record: dict) -> bytes:
    return canonical(record)


def from_record(record: dict) -> ParsedGame:
    """The game the agent works on, built from the record alone (§2.4): the moves replayed from
    `start_fen`, the root from `start_fen`, the grading from `pgn_tags(headers)`."""

    start = record["start_fen"]
    board = chess.Board(start)
    moves, sans = [], []
    for uci in record["moves"]:
        move = chess.Move.from_uci(uci)
        san = board.san(move)
        before = board.fen()
        board.push(move)
        moves.append(GameMove(san, move.uci(), before, board.fen()))
        sans.append(san)
    headers = dict(record["headers"])
    spec = grading_for(pgn_tags(headers))
    curve = resolve(spec, SHIPPED).curve
    fallback = curve is not None and curve.source == CurveSource.DEFAULT
    return ParsedGame(
        GameInput(start, tuple(moves), headers),
        tuple(sans),
        tuple(m.uci for m in moves),
        RootSpec() if start == chess.STARTING_FEN else RootSpec(fen=start),
        spec,
        (FALLBACK.format(scale=curve.scale),) if fallback else (),
    )


def damage(raw: bytes, key: str) -> str | None:
    """Why the bytes read as `<key>.json` are not a valid record (§2.2), or None."""

    if len(raw) > MAX_BYTES:
        return f"it has {len(raw)} bytes, over {MAX_BYTES}"
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "it is not JSON"
    if not isinstance(record, dict) or set(record) != FIELDS:
        return f"its keys are not {sorted(FIELDS)}"
    if record["v"] != RECORD_VERSION:
        return f"its version is not {RECORD_VERSION}"
    start, moves, headers = record["start_fen"], record["moves"], record["headers"]
    if not isinstance(record["game_key"], str) or not isinstance(start, str):
        return "game_key and start_fen are strings"
    if not isinstance(moves, list) or not all(isinstance(m, str) for m in moves):
        return "moves is a list of strings"
    if not isinstance(headers, dict):
        return "headers is an object"
    try:
        board = chess.Board(start)
    except ValueError:
        return "its start_fen cannot be read"
    if board.fen() != start:
        return "its start_fen is not in normal form"
    for ply, uci in enumerate(moves, start=1):
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            move = None
        if move is None or move.uci() != uci or move not in board.legal_moves:
            return f"move {ply} ({uci!r}) is not a legal move in UCI"
        board.push(move)
    problem = _header_damage(headers)
    if problem is not None:
        return problem
    if record["game_key"] != key or game_key(from_record(record).game) != key:
        return "its key is not the key of its content and name"
    if encode(record) != raw:
        return "it is not in canonical form"
    return None


def _header_damage(headers: dict) -> str | None:
    """Headers in normal form: names of `HEADERS`, ratings non-negative integers, the others
    strings that `game_input` keeps — so `game_input` reading `pgn_tags(headers)` gives them back."""

    for name, value in headers.items():
        if name not in TAGS:
            return f"header {name!r} is not one of {sorted(TAGS)}"
        rating = name.endswith("_rating")
        if rating and (type(value) is not int or value < 0):
            return f"header {name!r} is not a non-negative integer"
        if not rating and not isinstance(value, str):
            return f"header {name!r} is not a string"
    game = chess.pgn.Game.without_tag_roster()
    game.headers.update(pgn_tags(headers))
    if dict(game_input(game, ()).headers) != headers:
        return "its headers are not in normal form"
    return None


class Records:
    """`<data>/agent/games`: one record per game key, created once and never replaced."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def create(self, record: dict) -> None:
        """Create the record if absent (§2.2): a temporary of its own, `fsync`, `os.link` (which
        fails if the name exists), unlink. An existing record is reused when its bytes are ours
        and refused as damaged otherwise; it is never overwritten."""

        data = encode(record)
        if len(data) > MAX_BYTES:
            raise GameError(f"the game's record would have {len(data)} bytes, over {MAX_BYTES}")
        path = self.path(record["game_key"])
        if self._read(path, len(data) + 1) == data:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = temporary_name(path)
        try:
            with open(tmp, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(tmp, path)
                return
            except FileExistsError:
                pass
        finally:
            tmp.unlink(missing_ok=True)
        if self._read(path, len(data) + 1) != data:
            raise GameError(self._damaged(path, "it holds another content than this game's"))

    def load(self, key: str) -> dict:
        """The validated record of `key`; `GameError` when it is missing or damaged."""

        path = self.path(key)
        raw = self._read(path, MAX_BYTES + 1)
        if raw is None:
            raise GameError(f"no game {game_id(key, short=False)} (open it with open_game)")
        problem = damage(raw, key)
        if problem is not None:
            raise GameError(self._damaged(path, problem))
        return json.loads(raw)

    def keys(self, prefix: str) -> list[str]:
        """The keys of the records whose names start with `prefix`."""

        if not self.root.is_dir():
            return []
        names = (p.name[: -len(".json")] for p in self.root.glob(f"{prefix}*.json"))
        return sorted(n for n in names if _KEY.fullmatch(n))

    @staticmethod
    def _read(path: Path, limit: int = -1) -> bytes | None:
        try:
            with open(path, "rb") as handle:
                return handle.read(limit)
        except FileNotFoundError:
            return None
        except OSError as error:
            raise GameError(f"the game record {path} cannot be read: {error}") from error

    @staticmethod
    def _damaged(path: Path, problem: str) -> str:
        return (f"the game record {path} is damaged ({problem}); it is left as it is: remove it "
                "and open the game again with open_game")  # fmt: skip


def game_id(key: str, short: bool = True) -> str:
    return f"g-{key[:SHORT] if short else key}"


def parse_id(text) -> str:
    """The hex digits of a game id (16 or 64); `GameError` for anything else."""

    found = _ID.fullmatch(text) if isinstance(text, str) else None
    if found is None:
        raise GameError(f"no game {text!r}: a game id is g- and 16 (or 64) hex digits, as "
                        "open_game returns it (open the game with open_game)")  # fmt: skip
    return found[1]
