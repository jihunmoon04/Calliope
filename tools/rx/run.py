"""One run of the Calliope-run agent (RX1-D §4): a fresh server process on a copy of the set's base
cache, the guide in the system prompt, the task with the fixed moments, the model loop, and the
agent layer of the run record (RX0-D §4.3)."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import anyio
import chess.pgn

from calliope.agent.record import new_run_id

from .model import ModelTimeout, OpenRouter

REPO = Path(__file__).resolve().parents[2]
GUIDE_URI = "calliope://guides/commentary_ko"
TASK = "이 대국을 분석하고 중요한 장면들을 해설해서 저장해 줘. 다음 장면은 반드시 포함해 줘: {moments}."
RETRY = (
    "위 제출에서 거부된 장면이 있습니다: {subject}. 표시된 문제를 고쳐서 이 장면을 다시 제출해 줘."
)
ARMS = ("A", "B", "A-min")  # RX1 runs these; C, D, E and D-min fill the hooks in RX4 (§4.4)


@dataclass
class Bounds:  # RX0-D §8, RX1-D §4.7: starting values, fixed by RX2
    turns: int = 60
    tool_calls: int = 120
    tokens: int = 2_000_000
    retries_per_subject: int = 3  # arm B's N
    tool_seconds: float = 600
    run_seconds: float = 1800


@dataclass
class RunSpec:
    arm: str
    set_name: str
    game: str  # the manifest's name of the game
    pgn: str
    moments: list[int]
    base: Path  # the set's base cache
    records: Path
    work: Path
    model: str = "openai/gpt-6-luna"
    reasoning_effort: str | None = None
    bounds: Bounds = field(default_factory=Bounds)


def numbered(pgn: str, plies: list[int]) -> list[str]:
    """`14...Qb3`-style names of the plies (1-based) of the game."""

    game = chess.pgn.read_game(io.StringIO(pgn))
    board = game.board()
    names = {}
    for index, move in enumerate(game.mainline_moves(), start=1):
        if index in plies:
            number = (index + 1) // 2
            names[index] = f"{number}{'.' if index % 2 else '...'}{board.san(move)}"
        board.push(move)
    return [names[p] for p in plies]


def tree_digests(root: Path) -> dict[str, str]:
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


class AgentLog:
    """`agent.jsonl` (RX0-D §4.3)."""

    def __init__(self, path: Path, run_id: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = open(path, "a", encoding="utf-8")  # noqa: SIM115
        self.run_id = run_id
        self.seq = 0
        self.began = time.monotonic()

    def write(self, line: dict) -> None:
        self.seq += 1
        full = {"run": self.run_id, "seq": self.seq,
                "t": round(time.monotonic() - self.began, 3)} | line  # fmt: skip
        self.file.write(json.dumps(full, ensure_ascii=False, default=str) + "\n")
        self.file.flush()

    def close(self) -> None:
        self.file.close()


def _tool_text(result) -> tuple[str, bool]:
    parts = [c.text for c in (result.content or []) if getattr(c, "type", None) == "text"]
    return "\n".join(parts), bool(
        getattr(result, "is_error", False) or getattr(result, "isError", False)
    )


def _refused_subjects(arguments: dict, text: str) -> list[tuple[str, list]]:
    """The subjects a `submit_commentary` answer refused, with their problems."""

    try:
        answer = json.loads(text)
    except ValueError:
        return []
    out = []
    if "items" in answer:
        items = arguments.get("items") or []
        for outcome in answer["items"]:
            if outcome.get("outcome") == "refused":
                index = outcome.get("index", 0)
                item = items[index] if index < len(items) and isinstance(items[index], dict) else {}
                out.append((_subject_name(item), outcome.get("violations", [])))
    elif answer.get("accepted") is False:
        out.append((_subject_name(arguments), answer.get("violations", [])))
    return out


def _subject_name(item: dict) -> str:
    if item.get("ply") is not None:
        return f"ply {item['ply']}"
    return f"{item.get('move')} at {json.dumps(item.get('position'), ensure_ascii=False)}"


def lessons(arm: str) -> str:  # RX1-D §4.4: filled in RX4
    return ""


def critic(run_id: str, subject: str):  # RX1-D §4.4: filled in RX4
    return None


async def run_once(spec: RunSpec, run_id: str | None = None) -> dict:
    """One run. Whatever ends it, the agent layer gets its `end`, the server is closed and the
    working copy removed (review B2); the base cache is checked last."""

    if spec.arm not in ARMS:
        raise ValueError(f"arm {spec.arm} is not run in RX1 ({', '.join(ARMS)})")
    run_id = run_id or new_run_id()
    # the base cache first (review N3): a missing or broken base stops before any record is made
    base_before = json.loads((spec.base / "base.json").read_text(encoding="utf-8"))
    log = AgentLog(spec.records / run_id / "agent.jsonl", run_id)
    log.write({"type": "start", "model": spec.model,
               "parameters": {"reasoning_effort": spec.reasoning_effort}, "arm": spec.arm,
               "set": spec.set_name, "game": spec.game, "moments": spec.moments,
               "bounds": vars(spec.bounds)})  # fmt: skip
    work = spec.work / run_id
    totals = {"turns": 0, "tool_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}
    reason = "error"
    try:
        reason = await _run(spec, run_id, log, work, totals)
    except TimeoutError:  # the run's wall-clock bound (RX1-D §4.7)
        reason = "wall_clock"
    except ModelTimeout:
        reason = "timeout"
    except Exception as error:  # noqa: BLE001 - any other failure ends the run as an error
        reason = "error"
        log.write({"type": "error", "error": f"{type(error).__name__}: {error}"[:2000]})
    finally:  # also on cancellation and KeyboardInterrupt, which then propagate
        log.write({"type": "end", "reason": reason, "totals": totals})
        log.close()
        shutil.rmtree(work, ignore_errors=True)
    after = json.loads((spec.base / "base.json").read_text(encoding="utf-8"))
    changed = tree_digests(spec.base / "data") != base_before["files"] or after != base_before
    if changed:
        raise RuntimeError(f"the base cache {spec.base} changed during run {run_id}; batch stopped")
    return {"run": run_id, "reason": reason, "totals": totals}


async def _run(spec: RunSpec, run_id: str, log: AgentLog, work: Path, totals: dict) -> str:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    shutil.copytree(spec.base / "data", work)  # RX1-D §4.6: one starting cache for every run
    for path in work.rglob("*"):
        path.chmod(0o644 if path.is_file() else 0o755)
    guide = "commentary_min_v1" if spec.arm == "A-min" else "commentary_ko_v8"
    model = OpenRouter(spec.model, spec.reasoning_effort)
    env = dict(os.environ) | {"CALLIOPE_RUN_ID": run_id, "CALLIOPE_RUN_RECORDS": str(spec.records)}
    params = StdioServerParameters(command=sys.executable, cwd=str(REPO), env=env,
                                   args=["-m", "tools.mcp", "--data", str(work), "--guide", guide])  # fmt: skip
    moments = numbered(spec.pgn, spec.moments)
    with (
        anyio.fail_after(spec.bounds.run_seconds),
        open(spec.records / run_id / "server.stderr", "w", encoding="utf-8") as stderr,  # noqa: ASYNC230
    ):
        async with (
            stdio_client(params, errlog=stderr) as (read, write),
            ClientSession(read, write) as session,
        ):
            init = await session.initialize()
            listed = await session.list_tools()
            tools = [{"type": "function", "function": {
                "name": t.name, "description": t.description or "",
                "parameters": t.input_schema if hasattr(t, "input_schema") else t.inputSchema}}
                for t in listed.tools]  # fmt: skip
            read_guide = await session.read_resource(GUIDE_URI)
            guide_text = read_guide.contents[0].text
            system = "\n\n".join(x for x in (init.instructions or "", guide_text,
                                              lessons(spec.arm)) if x)  # fmt: skip
            task = TASK.format(moments=", ".join(moments)) + "\n\n" + spec.pgn
            messages = [{"role": "system", "content": system}, {"role": "user", "content": task}]
            log.write({"type": "setup", "request_fields": sorted(model.body(messages, tools)),
                       "moments_named": moments, "guide": guide,
                       "system_sha256": hashlib.sha256(system.encode()).hexdigest(),
                       "lessons": [], "tools": [t["function"]["name"] for t in tools]})  # fmt: skip
            return await _loop(session, model, messages, tools, spec, log, totals, {}, 0)


async def _loop(session, model, messages, tools, spec, log, totals, retries, sent) -> str:
    bounds = spec.bounds
    while True:
        if totals["turns"] >= bounds.turns:
            return "turns"
        if totals["input_tokens"] + totals["output_tokens"] >= bounds.tokens:
            return "tokens"
        log.write({"type": "request", "messages": messages[sent:],
                   "tools_offered": len(tools)})  # fmt: skip
        sent = len(messages)
        reply = await anyio.to_thread.run_sync(  # abandoned at the run's bound (N1)
            model.complete, messages, tools, abandon_on_cancel=True
        )
        totals["turns"] += 1
        for k in ("input_tokens", "output_tokens"):
            totals[k] += reply.usage.get(k) or 0
        totals["cost"] += reply.usage.get("cost") or 0.0
        log.write({"type": "response", "message": reply.message, "usage": reply.usage})
        message = {"role": "assistant", "content": reply.message.get("content")}
        for key in ("tool_calls", "reasoning", "reasoning_details"):  # kept as HIMARI keeps them
            if key in reply.message:
                message[key] = reply.message[key]
        messages.append(message)
        calls = reply.message.get("tool_calls") or []
        if not calls:
            return "done"
        feedback = []
        for index, call in enumerate(calls):
            name = call["function"]["name"]
            if totals["tool_calls"] >= bounds.tool_calls:
                for rest in calls[index:]:  # never sent: the checker knows (RX1 rev. 2)
                    log.write({"type": "tool_unsent", "tool_call_id": rest.get("id"),
                               "tool": rest["function"]["name"], "reason": "tool_calls"})  # fmt: skip
                return "tool_calls"
            totals["tool_calls"] += 1
            try:
                arguments = json.loads(call["function"].get("arguments") or "{}")
            except ValueError:
                arguments = None
            if not isinstance(arguments, dict):
                text, error = "arguments are not a JSON object", True
                log.write({"type": "tool_unsent", "tool_call_id": call.get("id"), "tool": name,
                           "reason": "arguments are not a JSON object"})  # fmt: skip
            else:
                try:
                    with anyio.fail_after(bounds.tool_seconds):
                        result = await session.call_tool(name, arguments)
                except TimeoutError:
                    log.write(
                        {"type": "error", "error": f"{name}: no answer in {bounds.tool_seconds} s"}
                    )
                    raise ModelTimeout("tool timeout") from None
                text, error = _tool_text(result)
            messages.append({"role": "tool", "tool_call_id": call.get("id"),
                             "content": f"[tool error] {text}" if error else text})  # fmt: skip
            if spec.arm == "B" and name == "submit_commentary" and not error:
                for subject, problems in _refused_subjects(arguments, text):
                    if retries.get(subject, 0) < bounds.retries_per_subject:
                        retries[subject] = retries.get(subject, 0) + 1
                        feedback.append((subject, problems, retries[subject]))
        for subject, problems, round_ in feedback:  # RX1-D §4.3: after every tool result
            content = (
                RETRY.format(subject=subject) + "\n" + json.dumps(problems, ensure_ascii=False)
            )
            messages.append({"role": "user", "content": content})
            log.write({"type": "feedback", "arm": "B", "subject": subject, "round": round_,
                       "problems": problems})  # fmt: skip
