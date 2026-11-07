"""HS-D: arm H of the RX runner — per fixed moment, the facts and the decisive cause in one turn, a
judge that never sees the key causes, at most two retries, then the submit step behind a gate.

The stages drive `run._loop` (the plain loop) with the runner's messages from `harness_v1.md`; the
judge is one request on the run's model with `harness_judge_v1.md`. The gate (`(phase, current_ply)`,
review B2) sends `submit_commentary` to the server only at the current moment's submit step and only
when every subject of the call is that moment; anything else is answered by the runner and logged as
`tool_unsent` with `reason: "harness_gate"`.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path
from types import SimpleNamespace

import anyio
import chess.pgn

PROMPTS = Path(__file__).resolve().parent / "prompts"
HARNESS_VERSION = "harness_v1"
JUDGE_VERSION = "harness_judge_v1"
RETRIES = 2


def messages_of(path: Path = PROMPTS / f"{HARNESS_VERSION}.md") -> dict[str, str]:
    """The `## name` sections of `harness_v1.md`, each its text."""

    out, name, lines = {}, None, []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if name:
                out[name] = "\n".join(lines).strip()
            name, lines = line[3:].strip(), []
        elif name:
            lines.append(line)
    if name:
        out[name] = "\n".join(lines).strip()
    return out


MESSAGES = messages_of()
JUDGE_SYSTEM = (PROMPTS / f"{JUDGE_VERSION}.md").read_text(encoding="utf-8").strip()


class Game:
    """The game's moves, for the gate's check of a subject named by position and move."""

    def __init__(self, pgn: str) -> None:
        game = chess.pgn.read_game(io.StringIO(pgn))
        board = game.board()
        self.uci, self.san = [], []
        for move in game.mainline_moves():
            self.uci.append(move.uci())
            self.san.append(board.san(move))
            board.push(move)

    def before(self, ply: int) -> list[str]:
        return self.uci[: ply - 1]


def _position_path(position, game: Game) -> list[str] | None:
    if not isinstance(position, dict):
        return None
    if isinstance(position.get("from_root"), list):
        return [str(m) for m in position["from_root"]]
    ply, at = position.get("ply"), position.get("at", "after")
    if isinstance(ply, int) and not isinstance(ply, bool):
        return game.uci[: ply if at == "after" else ply - 1]
    return None


def subject_ply(subject, game: Game) -> int | None:
    """The game ply a subject of `submit_commentary` names, or None (a variation, a malformed
    subject). By `ply`, or by `position` and `move` when the position is the one before a played
    move and the move is that move (in UCI or SAN)."""

    if not isinstance(subject, dict):
        return None
    ply = subject.get("ply")
    if ply is not None:
        return ply if isinstance(ply, int) and not isinstance(ply, bool) else None
    path, move = _position_path(subject.get("position"), game), subject.get("move")
    if path is None or not isinstance(move, str):
        return None
    candidate = len(path) + 1
    if candidate > len(game.uci) or path != game.before(candidate):
        return None
    return candidate if move in (game.uci[candidate - 1], game.san[candidate - 1]) else None


def subjects_of(arguments: dict) -> list:
    """Every subject of a `submit_commentary` call: its `items`, or the call itself."""

    if "items" in arguments:
        items = arguments.get("items")
        return list(items) if isinstance(items, list) else [None]
    return [arguments]


class Gate:
    """HS-D §2 (review B2): `(phase, current_ply)`; a submit passes only at the current moment's
    submit step with every subject the current moment."""

    def __init__(self, session, game: Game, log) -> None:
        self.session = session
        self.game = game
        self.log = log
        self.phase = "facts"
        self.current_ply: int | None = None
        self.blocked = 0
        self.next_call_id = None  # set by `run._loop` before each call (the checker's id)

    def allows(self, arguments: dict) -> tuple[bool, list]:
        subjects = subjects_of(arguments)
        named = [subject_ply(s, self.game) for s in subjects]
        ok = (self.phase == "submit" and bool(subjects)
              and all(p is not None and p == self.current_ply for p in named))  # fmt: skip
        return ok, named

    async def call_tool(self, name, arguments):
        if name == "submit_commentary":
            ok, named = self.allows(arguments if isinstance(arguments, dict) else {})
            if not ok:
                self.blocked += 1
                self.log.write({"type": "tool_unsent", "tool_call_id": self.next_call_id,
                                "tool": name, "reason": "harness_gate",
                                "phase": self.phase, "current_ply": self.current_ply,
                                "subjects": named})  # fmt: skip
                text = MESSAGES["gate"].format(ply=self.current_ply)
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text=text)], isError=True
                )
        return await self.session.call_tool(name, arguments)

    def __getattr__(self, item):
        return getattr(self.session, item)


def _parse(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return {}
    for candidate in (match.group(0), match.group(0).replace('\\"', '"')):
        try:
            verdict = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(verdict, dict) and isinstance(verdict.get("pass"), bool):
            return verdict
    return {}


def judge(model, header: str, reply: str) -> tuple[dict, dict]:
    """HS-D §3: one request on the run's model, no tools; the moment's header and the agent's reply
    only. An answer that is not the JSON asked for is asked again once; still unreadable, it never
    blocks the moment."""

    messages = [{"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": f"{header}\n\n## 해설자의 답\n{reply}"}]  # fmt: skip
    usage = {"cost": 0.0, "input_tokens": 0, "output_tokens": 0}
    text = ""
    for _ in range(2):
        answer = model.complete(messages, [])
        for key in usage:
            usage[key] += answer.usage.get(key) or 0
        text = answer.message.get("content") or ""
        verdict = _parse(text)
        if verdict:
            verdict["problems"] = [str(p) for p in (verdict.get("problems") or [])][:3]
            return verdict, usage
    return {"pass": False, "problems": [], "unreadable": True, "raw": text[:500]}, usage


def last_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "assistant" and message.get("content"):
            return message["content"]
    return ""


async def harness_loop(session, model, messages, tools, spec, log, totals, plain_loop, judge_model,
                       moments: list[tuple[int, str]]) -> str:  # fmt: skip
    """The stages over the fixed moments, in game order (HS-D §2). `moments`: (ply, numbered move)."""

    gate = Gate(session, Game(spec.pgn), log)
    sent = 0  # the first request logs the system message and the task (HS-D §4)
    for ply, move in moments:
        gate.current_ply, gate.phase = ply, "facts"
        messages.append({"role": "user", "content": MESSAGES["facts"].format(move=move)})
        how = MESSAGES["passed"]
        attempt = 0
        while True:
            log.write({"type": "harness", "stage": "facts", "ply": ply, "attempt": attempt})
            reason = await plain_loop(gate, model, messages, tools, spec, log, totals, {}, sent)
            sent = len(messages)
            if reason != "done":
                return reason
            reply = last_text(messages)
            verdict, usage = await anyio.to_thread.run_sync(
                judge, judge_model, f"장면: {move}", reply
            )
            totals["cost"] += usage["cost"]
            totals["judge_cost"] = totals.get("judge_cost", 0.0) + usage["cost"]
            totals["judge_tokens"] = (totals.get("judge_tokens", 0) + usage["input_tokens"]
                                      + usage["output_tokens"])  # fmt: skip
            log.write({"type": "judge", "ply": ply, "attempt": attempt, "verdict": verdict,
                       "usage": usage, "reply": reply})  # fmt: skip
            if verdict["pass"] or verdict.get("unreadable"):
                break
            if attempt >= RETRIES:
                how = MESSAGES["exhausted"]
                break
            attempt += 1
            problems = "; ".join(verdict.get("problems") or [])
            messages.append(
                {"role": "user", "content": MESSAGES["retry"].format(move=move, problems=problems)}
            )
        gate.phase = "submit"
        messages.append({"role": "user", "content": MESSAGES["submit"].format(move=move, how=how)})
        log.write({"type": "harness", "stage": "submit", "ply": ply, "attempts": attempt + 1})
        reason = await plain_loop(gate, model, messages, tools, spec, log, totals, {}, sent)
        sent = len(messages)
        if reason != "done":
            return reason
    log.write({"type": "harness", "stage": "end", "blocked_submissions": gate.blocked})
    return "done"
