"""Accepted AI commentary (AG-D §8): a sidecar store beside the games, never inside `result.json`.

`<data>/commentary/<game key>/<subject digest>/<id>.json`, each file written once through a
temporary name of its own (AG-D §9). The game key is `game_key_v1`, the game part of the job id's
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

from calliope.server.cache import canonical
from calliope.server.files import atomic_write, read_or_none

FORMAT = "ai_commentary_v1"
GAME_KEY_VERSION = "game_key_v1"
SUBJECT_VERSION = "subject_v1"


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

        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
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
            if isinstance(record, dict) and record.get("format") == FORMAT:
                out.append(record)
        return sorted(out, key=lambda r: r["id"], reverse=True)

    def for_subject(self, key: str, path) -> list[dict]:
        return [r for r in self.for_game(key) if r["subject"]["path"] == list(path)]


def _bundles(document: dict | None) -> dict[int, dict]:
    if document is None:
        return {}
    return {p["ply"]: p["bundle"] for p in document.get("plies", []) if "bundle" in p}


def stale(record: dict, played: list[str], bundles: dict[int, dict]) -> bool | None:
    """False when the record's analysis is the result's for its ply, True when another; None when
    the result holds no such ply or the subject is a judged move (AG-D §8)."""

    path = record["subject"]["path"]
    if path != played[: len(path)] or len(path) not in bundles:
        return None
    bundle = bundles[len(path)]
    return (record["bundle"]["tree"], record["bundle"]["graph"]) != (
        bundle["tree"],
        bundle["graph"],
    )


def listing(records: list[dict], played: list[str], document: dict | None) -> dict:
    """The commentary route's answer: played plies by number, judged moves apart, newest first."""

    bundles = _bundles(document)
    plies: dict[str, list] = {}
    judged = []
    for record in records:
        entry = record | {"stale": stale(record, played, bundles)}
        path = record["subject"]["path"]
        if path == played[: len(path)]:
            plies.setdefault(str(len(path)), []).append(entry)
        else:
            judged.append(entry)
    return {"format": "ai_commentary_list_v1", "plies": plies, "judged": judged}


AI_FIELDS = ("format", "id", "created", "agent", "level", "check", "propositions", "sentences")


def with_commentary(document: dict, records: list[dict], played: list[str]) -> dict:
    """`calliope_result_v1` with each ply's newest current commentary as `ai_commentary` (AG-D
    §8): a fresh copy, the stored document untouched."""

    out = copy.deepcopy(document)
    bundles = _bundles(document)
    for ply in out.get("plies", []):
        for record in records:  # newest first
            if (
                len(record["subject"]["path"]) == ply["ply"]
                and stale(record, played, bundles) is False
            ):
                ply["ai_commentary"] = {k: record[k] for k in AI_FIELDS if k in record}
                break
    return out
