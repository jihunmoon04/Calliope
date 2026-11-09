"""AF-D §5.1: what each judged sentence cited, for judge v2 — every citation resolved as the server
resolved it, each record's origin (`analysis`, `search`, `agent`), rendered in one form whatever the
tools' version, so the judge stays blind to the arm.

Origins come from the run's `tools.jsonl`:

- v9 writes an `origin` line per call that served an `x` handle (`plies_origin`, one entry a ply);
- v7 and v8 runs are restored: the handle line's `call_id` names the call that served it, and that
  call's answer gives the plies — an `explore` answer's `ledger.plies[].source` (`agent` → `agent`,
  `engine` → `search`; v7's `explore`, which has no ledger, is all `agent`), a `compare_lines` line's
  `source` (`{kind: n}`: the first n plies, `analysis` for `played`/`best`, `game` for the game's own
  moves, `agent` for a candidate) and `extended` (the next plies, `search`);
- an `s` handle is `search` when its `source.kind` is `search`, the analysis's otherwise.

`docs/design/rx-evidence/af/wrong_cites.py` is this module's prototype (AF-D review N1 of rev. 3).
"""

from __future__ import annotations

import json
from pathlib import Path

import chess

from calliope.agent.lines import standing_white

from .check import lines

ORDER = ("search", "agent", "analysis")  # the most foreign origin wins (AF-D §5.1)
GIVEN = {"engine": "analysis", "played": "analysis", "best": "analysis", "game": "game"}
LINE_FIELDS = ("line", "judgement", "claim")
DROP = ("id", "by_handle")


def foreign(origins) -> str:
    """The most foreign of some plies' origins: `search` over `agent` over `analysis` (a game move
    counts as the analysis's: both are what the reference holds)."""

    kinds = {"analysis" if o == "game" else o for o in origins}
    for kind in ORDER:
        if kind in kinds:
            return kind
    return "analysis" if not kinds else "unknown"


def _answer(call: dict | None) -> dict | None:
    if call is None:
        return None
    answer = call.get("answer")
    try:
        body = json.loads(answer) if isinstance(answer, str) else answer
        if isinstance(body, dict) and "content" in body:
            body = json.loads(body["content"][0]["text"])
        return body if isinstance(body, dict) else None
    except (ValueError, KeyError, IndexError, TypeError):
        return None


class Run:
    """A run's records, indexed for the origins of its handles."""

    def __init__(self, run_dir: Path):
        self.records = lines(run_dir / "tools.jsonl")
        self.handles = {r["ref"]: r for r in self.records if r.get("type") == "handle"}
        self.calls = {r["call_id"]: r for r in self.records if r.get("type") == "call"}
        self.origins: dict[str, list[str]] = {}
        for r in self.records:  # v9: the last call's origin of a handle stands
            if r.get("type") == "origin":
                self.origins[r["ref"]] = list(r.get("plies_origin") or [])

    def plies_origin(self, ref: str) -> list[str] | None:
        """An `x` handle's plies' origins (v9's line, else restored from the serving call)."""

        if ref in self.origins:
            return self.origins[ref]
        handle = self.handles.get(ref)
        call = self.calls.get((handle or {}).get("call_id"))
        body = _answer(call)
        if call is None or body is None:
            return None
        if call.get("tool") == "explore":
            plies = (body.get("ledger") or {}).get("plies")
            if plies is None:  # v7: no ledger, no continuation: every ply the agent's
                return ["agent"] * len(body.get("plies") or [])
            return [{"engine": "search"}.get(p.get("source"), p.get("source") or "agent")
                    for p in plies]  # fmt: skip
        if call.get("tool") == "compare_lines":
            for name, line in (body.get("lines") or {}).items():
                for entry in (line if isinstance(line, list) else [line]):
                    if not isinstance(entry, dict) or ref not in (
                            entry.get("ref"), (entry.get("searched") or {}).get("ref")):  # fmt: skip
                        continue
                    if name == "candidates":
                        n = len(entry.get("moves") or [])
                        return ["agent"] + ["search"] * (n - 1)
                    ((kind, given),) = (entry.get("source") or {"engine": 0}).items()
                    origin = GIVEN.get(kind, "agent")
                    return [origin] * given + ["search"] * int(entry.get("extended") or 0)
        return None

    def origin(self, ref: str) -> str:
        """A handle's origin."""

        handle = self.handles.get(ref)
        if handle is None:
            return "unknown"
        kind = handle.get("kind")
        if kind == "search_line":
            return "search" if (handle.get("source") or {}).get("kind") == "search" else "analysis"
        if kind == "explored_line":
            plies = self.plies_origin(ref)
            return foreign(plies) if plies is not None else "unknown"
        return "analysis"  # judgements, claims, board items: the analysis record's

    def start_fen(self, ref: str) -> str | None:
        """The FEN a handle's line starts from (its address's path from the game's start)."""

        handle = self.handles.get(ref) or {}
        path = (handle.get("address") or {}).get("from")
        if not isinstance(path, list):
            return None
        board = chess.Board()
        try:
            for uci in path:
                board.push_uci(uci)
        except ValueError:
            return None
        return board.fen()


def resolve(cite: str, verified: list[dict]) -> list[dict]:
    """A citation as the server resolved it: an explicit proposition by its id, or a cited
    handle's expansion (the `verified` entries whose `by_handle` is that handle)."""

    explicit = [p for p in verified if p.get("id") == cite]
    return explicit or [p for p in verified if p.get("by_handle") == cite]


def _line(fen: str | None, moves: list[str]) -> dict:
    """A line in one form: the start FEN, its moves in SAN, the standing after each ply computed
    here from the FEN (never copied from a tool's answer)."""

    if fen is None:
        return {"moves_uci": moves}
    board = chess.Board(fen)
    sans, standing = [], []
    for uci in moves:
        try:
            move = chess.Move.from_uci(uci)
            sans.append(board.san(move))
            board.push(move)
        except ValueError:
            break
        standing.append(standing_white(board.fen()))
    return {"start_fen": fen, "start_standing_white": standing_white(fen), "moves": sans,
            "standing_white_after": standing}  # fmt: skip


def render(prop: dict, run: Run) -> dict:
    """One verified proposition as the judge reads it, with its origin."""

    kind = prop.get("kind")
    ref = next((prop[f] for f in LINE_FIELDS if isinstance(prop.get(f), str)), None)
    out = {"kind": kind}
    if kind in ("explored_line", "engine_line", "material") and ref:
        moves = prop.get("moves")
        handle = run.handles.get(ref) or {}
        if moves is None:
            moves = list((handle.get("address") or {}).get("moves") or [])
        fen = run.start_fen(ref)
        if kind == "engine_line" and fen is None:
            fen = (handle.get("address") or {}).get("fen")
        out |= _line(fen, list(moves))
        if kind == "material":
            plies = run.plies_origin(ref) or []
            start, end = int(prop.get("from", 0)), int(prop.get("to", 0))
            out |= {"from": start, "to": end, "side": prop.get("side"),
                    "change": prop.get("balance"),
                    "origin": foreign(plies[start:end]) if plies else run.origin(ref)}  # fmt: skip
        else:
            out["origin"] = run.origin(ref)
        return out
    if kind == "engine_score" and ref:
        handle = run.handles.get(ref) or {}
        out |= {"score": prop.get("score"), "move": prop.get("move"), "origin": run.origin(ref)}
        fen = (handle.get("address") or {}).get("fen")
        if fen is None and isinstance((handle.get("source") or {}).get("position"), list):
            board = chess.Board()
            for uci in handle["source"]["position"]:
                board.push_uci(uci)
            fen = board.fen()
        if fen:
            out["fen"] = fen
        if prop.get("depth") is not None:
            out["depth"] = prop["depth"]
        return out
    return {k: v for k, v in prop.items() if k not in DROP} | {"origin": "analysis"}


def evidence(run_dir: Path, final: dict, run: Run | None = None) -> list[list[dict]]:
    """Each sentence's evidence for a final submission (`check.finals`' entry): the verified
    propositions its citations resolve to, rendered (AF-D §5.1)."""

    run = run or Run(run_dir)
    submission = next((r for r in run.records if r.get("seq") == final["seq"]), None)
    subject = next((s for s in (submission or {}).get("subjects") or []
                    if s.get("id") == final.get("id")), None)  # fmt: skip
    verified = (subject or {}).get("verified") or []
    out = []
    for sentence in final.get("sentences") or []:
        items = []
        for cite in sentence.get("cites") or []:
            items += [render(p, run) for p in resolve(cite, verified)]
        out.append(items)
    return out
