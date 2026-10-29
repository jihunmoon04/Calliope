"""Accepted AI commentary (AG-D §8): a sidecar store beside the games, never inside `result.json`.

`<data>/commentary/<game key>/<subject digest>/<id>.json`, each file written once through a
temporary name of its own (AG-D §9). Every answer built from records — the listing and the
combined document — carries `display_v1` (AG3-D D14, §3.1): the moves of each proposition and the
subject in SAN, computed here with python-chess when read, never stored. The game key is `game_key_v1`, the game part of the job id's
preimage; the subject digest names the subject's path from the game's start (`subject_v1`). The
MCP server writes records (`calliope.agent`); the HTTP server reads them for its commentary route
and the combined document, and marks a commentary stale when the analysis it was accepted against
is not the one the job's result holds.
"""

from __future__ import annotations

import copy
import hashlib
import json
import secrets
import time
from pathlib import Path

import chess

from calliope.results import schema_errors
from calliope.server.cache import canonical
from calliope.server.files import atomic_write, read_or_none

FORMAT = "ai_commentary_v1"
GAME_KEY_VERSION = "game_key_v1"
SUBJECT_VERSION = "subject_v1"
DISPLAY_VERSION = "display_v1"
POSITION_KINDS = ("attack", "defence", "exposed", "pin", "check", "pattern")
ID_LENGTH = 29  # a record id: 20 digits of nanoseconds, "-", 8 hex digits


def game_key(game) -> str:
    """`game_key_v1` of a `GameInput` (a `ParsedGame`'s `game`): start, moves and headers."""

    preimage = {
        "v": GAME_KEY_VERSION,
        "start_fen": game.start_fen,
        "moves": [m.uci for m in game.moves],
        "headers": dict(game.headers),
    }
    return hashlib.sha256(canonical(preimage)).hexdigest()


def subject_digest(path) -> str:
    return hashlib.sha256(canonical({"v": SUBJECT_VERSION, "path": list(path)})).hexdigest()


class CommentaryStore:
    def __init__(self, root: Path) -> None:
        self.root = root  # <data>/commentary

    def write(self, record: dict) -> str:
        """A new file for an accepted commentary; its id orders by time. Returns the id."""

        stamp = f"{time.time_ns():020d}"  # ids order by time, within one second too
        record = dict(record) | {"format": FORMAT, "id": f"{stamp}-{secrets.token_hex(4)}"}
        folder = self.root / record["game_key"] / subject_digest(record["subject"]["path"])
        atomic_write(folder / f"{record['id']}.json", canonical(record))
        return record["id"]

    def for_game(self, key: str) -> list[dict]:
        """Every readable record of the game, newest first."""

        folder = self.root / key
        if not folder.is_dir():
            return []
        out = []
        for path in folder.glob("*/*.json"):
            data = read_or_none(path)
            try:
                record = json.loads(data) if data is not None else None
            except ValueError:
                continue
            if _sound(record):
                out.append(record)
        return sorted(out, key=lambda r: r["id"], reverse=True)

    def for_subject(self, key: str, path) -> list[dict]:
        return [r for r in self.for_game(key) if r["subject"]["path"] == list(path)]


def _sound(record) -> bool:
    """A record the routes can read: a damaged or foreign file is skipped. What a combined
    document carries of it must be a valid `AiCommentary` (AG2 re-review B1)."""

    try:
        return (
            record["format"] == FORMAT
            and isinstance(record["id"], str)
            and isinstance(record["subject"]["path"], list)
            and all(isinstance(m, str) for m in record["subject"]["path"])
            and isinstance(record["bundle"]["tree"], str)
            and isinstance(record["bundle"]["graph"], str)
            and not schema_errors(_ai(record), "AiCommentary")
        )
    except (KeyError, TypeError):
        return False


def _ai(record: dict) -> dict:
    return {k: record[k] for k in AI_FIELDS if k in record}


def _bundles(document: dict | None) -> dict[int, dict]:
    if document is None:
        return {}
    return {p["ply"]: p["bundle"] for p in document.get("plies", []) if "bundle" in p}


def stale(record: dict, played: list[str], bundles: dict[int, dict]) -> bool | None:
    """False when the record's analysis is the result's for its ply, True when another; None when
    the result holds no such ply or the subject is a judged move (AG-D §8). The graph digests are
    compared: the claim graph file holds the tree's F5 digest, while the tree file's bytes depend
    on the searches the process already held (PF-D §12, Q2)."""

    path = record["subject"]["path"]
    if path != played[: len(path)] or len(path) not in bundles:
        return None
    return record["bundle"]["graph"] != bundles[len(path)]["graph"]


# -- display_v1 (AG3-D D14, §3.1) -----------------------------------------------------------


class _Unplayable(ValueError):
    pass


def _board(start_fen: str, path) -> chess.Board:
    board = chess.Board(start_fen)
    for uci in path:
        _push(board, uci)
    return board


def _push(board: chess.Board, uci) -> chess.Move:
    try:
        move = chess.Move.from_uci(uci)
    except (TypeError, ValueError) as error:
        raise _Unplayable(uci) from error
    if move not in board.legal_moves:
        raise _Unplayable(uci)
    board.push(move)
    return move


def _line(fen: str, moves) -> dict:
    """A line from `fen`: each move's SAN at the position the moves before it reach."""

    try:
        board = chess.Board(fen)
    except (TypeError, ValueError) as error:
        raise _Unplayable(fen) from error
    out = []
    for uci in moves:
        before = board.copy(stack=False)
        move = _push(board, uci)
        out.append({"uci": uci, "san": before.san(move)})
    return {"fen": fen, "moves": out}


def _choices(fen: str, moves) -> list[dict]:
    """Alternatives at `fen` (`legal_moves`), each written from `fen` alone — never a line."""

    return [_line(fen, [uci])["moves"][0] for uci in moves]


def _at(start_fen: str, path) -> str:
    return _board(start_fen, path).fen()


def _search_fen(p: dict) -> str:
    address = p["sources"][0]["address"]
    if "fen" not in address:
        raise _Unplayable("a search line without its start")
    return address["fen"]


def _proposition_display(p: dict, start_fen: str) -> dict | None:
    kind = p.get("kind")
    if kind == "judgement":
        path, index = p["judged"]["source"]["path"], p["judged"]["address"]["judgement"]
        at = len(path) - 1 - index  # judgements: the subject's move, then the previous move's
        if not isinstance(index, int) or at < 0 or path[at] != p["move"]:
            raise _Unplayable("a judgement off its source path")
        fen = _at(start_fen, path[:at])
        shown = _line(fen, [p["move"]])
        if p.get("best_move") is None:  # no best move from the engine: the move alone (AG3a B2)
            return shown
        return shown | {"best": _line(fen, [p["best_move"]])}
    if kind == "engine_score":
        return _line(_search_fen(p), [p["move"]])
    if kind == "engine_line":
        return _line(_search_fen(p), p["moves"])
    if kind == "explored_line":
        return _line(_at(start_fen, p["from"]), p["moves"])
    if kind == "material":
        if "base" in p and "moves" in p:  # the line it was verified against (AG-D AM7)
            return _line(_at(start_fen, p["base"]), p["moves"])
        address = p["sources"][0]["address"]
        if "from" not in address:  # a record before AM7 over a search line: no moves kept
            return None
        return _line(_at(start_fen, address["from"]), address["moves"])
    if kind in POSITION_KINDS:
        return _line(_at(start_fen, p["position"]), [])
    if kind == "legal_moves":
        fen = _at(start_fen, p["position"])
        out = _line(fen, [])
        return out | {"choices": _choices(fen, p["moves"])} if "moves" in p else out
    if kind == "after_reply":
        a, b = p["after_a"], p["after_b"]
        fen = _at(start_fen, a[:-2])
        return _line(fen, []) | {"a": _line(fen, a[-2:]), "b": _line(fen, b[-2:])}
    return None  # claim, definition, a newer kind


def displayed(record: dict, start_fen: str) -> dict:
    """The record with `display` on each proposition that has one and on the record (`subject`);
    a proposition whose moves do not replay gets none (AG3-D D14)."""

    out = dict(record)
    propositions = []
    for p in record.get("propositions", []):
        try:
            shown = _proposition_display(p, start_fen)
        except (_Unplayable, KeyError, TypeError, IndexError):
            shown = None
        propositions.append(p if shown is None else p | {"display": {"v": DISPLAY_VERSION} | shown})
    out["propositions"] = propositions
    path = record["subject"]["path"]
    try:
        subject = _line(_at(start_fen, path[:-1]), path[-1:]) if path else None
    except _Unplayable:
        subject = None
    if subject is not None:
        out["display"] = {"v": DISPLAY_VERSION, "subject": subject}
    return out


def listing(records: list[dict], played: list[str], document: dict | None, start_fen: str) -> dict:
    """The commentary route's answer: played plies by number, judged moves apart, newest first."""

    bundles = _bundles(document)
    plies: dict[str, list] = {}
    judged = []
    for record in records:
        entry = displayed(record, start_fen) | {"stale": stale(record, played, bundles)}
        path = record["subject"]["path"]
        if path == played[: len(path)]:
            plies.setdefault(str(len(path)), []).append(entry)
        else:
            judged.append(entry)
    return {"format": "ai_commentary_list_v1", "plies": plies, "judged": judged}


AI_FIELDS = ("format", "id", "created", "agent", "level", "check", "propositions", "sentences")
SHOWN_FIELDS = (*AI_FIELDS, "display")


def board_form(record: dict, start_fen: str) -> dict:
    """What a combined document carries of a record as a ply's `ai_commentary` (AG-D §8): its AI
    fields with `display_v1` (AG3-D D14) — the form whose size AG6-D §5.3 bounds."""

    shown = displayed(_ai(record) | {"subject": record["subject"]}, start_fen)
    return {k: shown[k] for k in SHOWN_FIELDS if k in shown}


def board_size(record: dict, start_fen: str) -> int:
    """The UTF-8 bytes of a record's `board_form` as compact JSON once stored: a record not yet
    written is measured with its format and an id of the store's length (AG6-D §5.3)."""

    stored = {"format": FORMAT, "id": "0" * ID_LENGTH} | record
    form = board_form(stored, start_fen)
    return len(json.dumps(form, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def with_commentary(document: dict, records: list[dict], played: list[str]) -> dict:
    """`calliope_result_v1` with each ply's newest current commentary as `ai_commentary` (AG-D
    §8): a fresh copy, the stored document untouched."""

    out = copy.deepcopy(document)
    bundles = _bundles(document)
    start_fen = document["game"]["start_fen"]
    for ply in out.get("plies", []):
        for record in records:  # newest first
            if (
                len(record["subject"]["path"]) == ply["ply"]
                and stale(record, played, bundles) is False
            ):
                ply["ai_commentary"] = board_form(record, start_fen)
                break
    return out
