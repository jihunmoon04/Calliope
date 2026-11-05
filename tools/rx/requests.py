"""RX2-D A2: run each `on_request` key cause's request through Calliope and record what it shows.

For every reference whose key causes include an `on_request` cause, a probe session on a copy of the set's
base runs the request (`explore` of a line, or `facts` with its families) and writes into the cause's
`request`:
- `resolved`: the position as a UCI path from the root and the moves in UCI, as the record's handles name
  them, so M2a and M3 can match an agent's own call (`metrics.requested`);
- `result`: what Calliope answered: for `explore`, the material balance (White's view) after each ply and
  the end position's status and exchange records; for `facts`, the records of the families.

It changes nothing else. The owner reviews the cause with its result beside it.
"""

from __future__ import annotations

import json
from pathlib import Path

import chess

from .manifest import MANIFEST, RX_DATA, pgn_text
from .reference import REFERENCES, probe_session


def _position(request_from) -> dict:
    if isinstance(request_from, dict):
        return request_from
    return {"from_root": list(request_from)}


def run_requests(set_name: str, engine: str, root: Path = REFERENCES) -> list[str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = {e["name"]: e for e in manifest["sets"][set_name]}
    report = []
    with probe_session(set_name, engine) as session:
        opened = {}
        for path in sorted((root / set_name).glob("*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            causes = [c for c in doc.get("key_causes") or [] if c.get("route") == "on_request"]
            if not causes:
                continue
            name = doc["game"]
            if name not in opened:
                pgn = pgn_text(set_name, entries[name], RX_DATA / "sets")
                opened[name] = session.open_game(pgn=pgn)["game"]
            gid = opened[name]
            game = session.game(gid)
            for cause in causes:
                request = cause.get("request") or {}
                position = _position(request.get("from") or request.get("position"))
                at = list(session.path(game, position))
                try:
                    if request.get("tool") == "explore":
                        board = session._board(game, tuple(at))
                        uci = []
                        for move in request.get("moves") or []:
                            m = (
                                board.parse_san(move)
                                if not _is_uci(board, move)
                                else chess.Move.from_uci(move)
                            )
                            uci.append(m.uci())
                            board.push(m)
                        answer = session.explore(gid, {"from_root": at}, uci, search=True)
                        request["resolved"] = {"tool": "explore", "from": at, "moves": uci}
                        request["result"] = {
                            "plies": [{"move": p["move"].get("san"),
                                       "material_balance_white": p["material_balance_white"]}
                                      for p in answer["plies"]],
                            "end_status": (answer["end_facts"].get("status") or {}),
                            "end_exchange": (answer["end_facts"].get("exchange") or {}),
                            # the engine at the line's end: its best line's score (a mate shows here)
                            "end_search": [{"score": x.get("score"), "pv": [m.get("san") for m in
                                                                           (x.get("pv") or [])][:8]}
                                           for x in ((answer.get("search") or {}).get("lines") or [])[:2]],
                        }  # fmt: skip
                    elif request.get("tool") == "facts":
                        families = request.get("families") or ["exchange"]
                        answer = session.facts(gid, {"from_root": at}, families)
                        request["resolved"] = {
                            "tool": "facts",
                            "position": at,
                            "families": families,
                        }
                        request["result"] = {
                            k: v.get("record") for k, v in answer["families"].items()
                        }
                    else:
                        raise ValueError(f"unknown tool {request.get('tool')!r}")
                    cause["request"] = request
                    report.append(f"{path.name}: {request['tool']} ok")
                except Exception as error:  # noqa: BLE001 - reported for the owner, file untouched
                    report.append(
                        f"{path.name}: {request.get('tool')} FAILED {type(error).__name__}: {error}"
                    )
            path.write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str) + "\n",
                            encoding="utf-8")  # fmt: skip
    return report


def _is_uci(board: chess.Board, move: str) -> bool:
    try:
        return chess.Move.from_uci(move) in board.legal_moves
    except ValueError:
        return False
