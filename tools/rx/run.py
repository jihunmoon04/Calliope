"""One run of the Calliope-run agent (RX1-D §4): a fresh server process on a copy of the set's base
cache, the guide in the system prompt, the task with the fixed moments, the model loop, and the
agent layer of the run record (RX0-D §4.3)."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import anyio
import chess.pgn

from calliope.agent.record import new_run_id

from .model import CUT_MESSAGE, DEFAULT_MODEL, ModelTimeout, make_model

REPO = Path(__file__).resolve().parents[2]
# LT-D §6.3 (review F2): a variant's tools, and where its server starts (None: this repository)
TOOLS_VERSIONS = {
    "v7": "agent_tools_v7",
    "v8": "agent_tools_v8",
    "v9": "agent_tools_v9",
    "v10": "agent_tools_v10",
    "v11": "agent_tools_v11",
}  # TB-D B6
# under RX_DATA / "servers": a worktree of the tag. TB-D B6: v9 from its tag once v10 is merged; v8
# had no tag and is not reachable
SERVER_ROOTS = {"v7": "agent-tools-v7", "v9": "agent-tools-v9", "v10": "agent-tools-v10"}


def server_root(tools: str | None) -> Path | None:
    """The directory a variant's server starts in: a worktree of its tag for an earlier tool
    version, the repository otherwise."""

    if tools is None or tools not in SERVER_ROOTS:
        if tools is not None and tools not in TOOLS_VERSIONS:
            raise ValueError(f"no tools {tools!r}; tools: {', '.join(TOOLS_VERSIONS)}")
        return None
    from .manifest import RX_DATA

    return RX_DATA / "servers" / SERVER_ROOTS[tools]


def served_version(init) -> str | None:
    """The tools version a server reports in its `initialize` answer (`TOOLS_VERSION`, the MCP
    server's version): `server_info` in this MCP SDK, `serverInfo` in earlier ones (LT pilot)."""

    info = getattr(init, "server_info", None) or getattr(init, "serverInfo", None)
    return getattr(info, "version", None)


def variant_of(arm: str, tools: str | None) -> str | None:
    return f"{arm}@{tools}" if tools else None


def git_commit(root: Path) -> str | None:
    import subprocess

    done = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=False)  # fmt: skip
    return done.stdout.strip() or None if done.returncode == 0 else None


GUIDE_URI = "calliope://guides/commentary_ko"
BUILD_URI = "calliope://build"
TASK = "이 대국을 분석하고 중요한 장면들을 해설해서 저장해 줘. 다음 장면은 반드시 포함해 줘: {moments}."
# RX2 amendment A1: the game is named by its id, already open in Calliope, instead of a PGN the agent
# could retype (RX2 batch rx2-1: 22 of 48 runs opened a PGN without its headers, another game)
TASK_BY_ID = (
    "이 대국은 Calliope에 이미 열려 있어. 게임 id는 {game_id}야. open_game을 다시 부르지 말고 "
    "이 id로 분석하고 중요한 장면들을 해설해서 저장해 줘. 다음 장면은 반드시 포함해 줘: {moments}."
)
RETRY = (
    "위 제출에서 거부된 장면이 있습니다: {subject}. 표시된 문제를 고쳐서 이 장면을 다시 제출해 줘."
)
ARMS = ("A", "B", "A-min", "D", "D-min", "H")  # RX4a adds D and D-min; HS-D adds H; C, E not run
HARNESS_ARMS = ("H",)  # HS-D: the staged harness (`harness.py`)
# RX4-D §3.2 (review N2, re-review C1): each lesson arm inherits its base and only its base. D is B
# with lessons (the retry); D-min is A-min with lessons (no retry, RX0-D §8).
RETRY_ARMS = ("B", "D")
LESSON_ARMS = ("D", "D-min")
MIN_ARMS = ("A-min", "D-min")


@dataclass
class Bounds:  # RX0-D §8, RX1-D §4.7: starting values, fixed by RX2
    turns: int = 60
    tool_calls: int = 120
    tokens: int = 2_000_000
    retries_per_subject: int = 3  # arm B's N
    tool_seconds: float = 600
    run_seconds: float = 1800
    cost: float | None = None  # TB-D B5: a run's cost bound (USD); None: none


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
    model: str = DEFAULT_MODEL
    reasoning_effort: str | None = None
    bounds: Bounds = field(default_factory=Bounds)
    game_id: str | None = None  # RX2 A1: the base's id of the game; None: the PGN in the task
    lessons_path: Path | None = None  # RX4-D §2.4: the set's file, for D and D-min only
    candidate_id: str | None = None  # RX4-D §2.3 step 2: the screened lesson; on B, the pair's tag
    reproduce: bool = (
        False  # RX4a re-review N4: a NOT_PROMOTED set runs only to reproduce its result
    )
    harness_revision: int = 8  # arm H: 8 (AF), 7 (LT), 6 and 5 (LT pilots), 4 (HS rev. 4)
    harness_guide: str | None = None  # TB-D B2: rev. 9's system message; None: HARNESS_GUIDE
    tools: str | None = None  # LT-D §6.3: the variant's tools (`v7`, `v8`); None: the repository's
    server: Path | None = None  # where the server starts; None: the repository
    cache: bool = True  # MH review F1: Anthropic's cache marks, made in `OpenRouter.body` only


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


def _leaves(error: BaseException) -> list[BaseException]:
    if isinstance(error, BaseExceptionGroup):
        return [leaf for sub in error.exceptions for leaf in _leaves(sub)]
    return [error]


def build_problem(tools_path: Path, base: Path) -> str | None:
    """RX2-D §3: None when every `build` line of the run is the base's build; else what differs."""

    sealed = json.loads((base / "base.json").read_text(encoding="utf-8")).get("build")
    if not sealed:
        return f"{base / 'base.json'} has no build: run `python -m tools.rx annotate` first"
    builds = []
    for raw in tools_path.read_text(encoding="utf-8").splitlines() if tools_path.exists() else []:
        line = json.loads(raw)
        if line.get("type") == "build":
            builds.append(line)
    if not builds:
        return "the server wrote no build line"
    for line in builds:
        if line["build_id"] != sealed["build_id"]:
            return (f"build {line['build_id'][:12]} is not the base's {sealed['build_id'][:12]}: "
                    f"engine {line['engine']} against {sealed['engine']}")  # fmt: skip
    return None


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


# the MCP server's answer to arguments its input schema refuses: the tool never ran (the review of
# 2026-11-10: one rev. 11 run's checker count was one short)
SCHEMA_REFUSED = re.compile(r"Error executing tool \S+: \d+ validation errors? for ")


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


def _server_info(spec: RunSpec) -> dict:
    """LT-D §6.3: the variant and the server's root and commit, on the `start` line."""

    if spec.tools is None and spec.server is None:
        return {}
    root = spec.server or REPO
    return {"variant": variant_of(spec.arm, spec.tools),
            "server": {"root": str(root), "commit": git_commit(root),
                       "tools_expected": TOOLS_VERSIONS.get(spec.tools)}}  # fmt: skip


def _harness_info(spec: RunSpec) -> dict:
    """HS-D §4: what the `start` line records of arm H."""

    if spec.arm not in HARNESS_ARMS:
        return {}
    from .harness import FRAMES, RETRIES, VERSIONS, revision_of

    rev = revision_of(spec)
    messages, judge, sentences = VERSIONS[rev]
    out = {"harness": messages, "harness_judge": judge, "harness_retries": RETRIES}
    out |= {"harness_frames": FRAMES[rev]} if FRAMES.get(rev) else {}  # AF-D §4.4
    from .harness import HARNESS_GUIDE, PER_MOMENT

    if rev in PER_MOMENT:  # TB-D B2: the guide a rev. 9 run's system message is
        out["harness_guide"] = spec.harness_guide or HARNESS_GUIDE
    from .harness import LEAN_TIER1, TIER1_GUIDES, TIERED

    if rev in TIERED:  # WG-D §2.1: tier 1's batches have their own guide
        out["harness_tier1"] = TIER1_GUIDES[rev]
        out["harness_tier1_lean"] = rev in LEAN_TIER1
        from .harness import SHORT_HANDLES

        out["harness_tier1_short_handles"] = rev in SHORT_HANDLES
    return out | ({"harness_sentences": sentences} if sentences else {})


def guide_of(arm: str) -> str:
    return "commentary_min_v1" if arm in MIN_ARMS else "commentary_ko_v8"


def lessons(spec: RunSpec) -> tuple[str, dict]:
    """RX1-D §4.4, filled by RX4-D §2.4: the rendered lessons for D and D-min, and what the `start`
    line records of them. Any other arm carries none; its digest is that of no lessons (N4)."""

    from . import lessons as lesson_sets

    if spec.arm not in LESSON_ARMS:
        if spec.lessons_path is not None:
            raise ValueError(f"arm {spec.arm} carries no lessons")
        if spec.candidate_id is not None and spec.set_name != "train":
            raise ValueError("a candidate's pair is screened on Train only")
        return "", {"lesson_set": None, "lesson_set_status": None, "lesson_ids": [],
                    "candidate_id": spec.candidate_id,
                    "lesson_set_digest": lesson_sets.digest(""), "rendered_fields": []}  # fmt: skip
    if spec.lessons_path is None:
        raise ValueError(f"arm {spec.arm} needs a lesson set")
    doc = lesson_sets.load(spec.lessons_path)
    base = json.loads((spec.base / "base.json").read_text(encoding="utf-8"))
    wrong = lesson_sets.problems(doc) + lesson_sets.use_problems(
        doc, set_name=spec.set_name, candidate=spec.candidate_id, guide=guide_of(spec.arm),
        build_id=(base.get("build") or {}).get("build_id"), reproduce=spec.reproduce)  # fmt: skip
    if wrong:
        raise ValueError(f"{spec.lessons_path}: " + "; ".join(wrong))
    chosen = lesson_sets.select(doc, spec.candidate_id)
    text = lesson_sets.render(chosen)
    return text, {"lesson_set": doc.get("id"), "lesson_set_status": doc.get("status"),
                  "reproduce": spec.reproduce,
                  "lesson_ids": [x["id"] for x in chosen],
                  "candidate_id": spec.candidate_id, "lesson_set_digest": lesson_sets.digest(text),
                  "rendered_fields": list(lesson_sets.RENDERED_FIELDS)}  # fmt: skip


def retry_feedback(arm: str, name: str, arguments: dict, text: str, error: bool, retries: dict,
                   limit: int) -> list[tuple[str, list, int]]:  # fmt: skip
    """RX1-D §4.3: the refused subjects to send back, for the retry arms only (B, D)."""

    if arm not in RETRY_ARMS or name != "submit_commentary" or error:
        return []
    out = []
    for subject, problems in _refused_subjects(arguments, text):
        if retries.get(subject, 0) < limit:
            retries[subject] = retries.get(subject, 0) + 1
            out.append((subject, problems, retries[subject]))
    return out


def retry_message(subject: str, problems: list) -> str:
    return RETRY.format(subject=subject) + "\n" + json.dumps(problems, ensure_ascii=False)


def critic(run_id: str, subject: str):  # RX1-D §4.4: filled in RX4
    return None


async def run_once(spec: RunSpec, run_id: str | None = None) -> dict:
    """One run. Whatever ends it, the agent layer gets its `end`, the server is closed and the
    working copy removed (review B2); the base cache is checked last."""

    if spec.arm not in ARMS:
        raise ValueError(f"arm {spec.arm} is not run ({', '.join(ARMS)})")
    run_id = run_id or new_run_id()
    # the base cache first (review N3): a missing or broken base stops before any record is made
    base_before = json.loads((spec.base / "base.json").read_text(encoding="utf-8"))
    lesson_text, lesson_info = lessons(spec)  # a bad set stops before any record too
    log = AgentLog(spec.records / run_id / "agent.jsonl", run_id)
    log.write({"type": "start", "model": spec.model,
               "parameters": {"reasoning_effort": spec.reasoning_effort, "cache": spec.cache,
                              "session_id": run_id}, "arm": spec.arm,
               "set": spec.set_name, "game": spec.game, "moments": spec.moments,
               "bounds": vars(spec.bounds)} | lesson_info | _harness_info(spec)
              | _server_info(spec))  # fmt: skip
    work = spec.work / run_id
    totals = {"turns": 0, "tool_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}
    reason = "error"
    try:
        reason = await _run(spec, run_id, log, work, totals, lesson_text, lesson_info)
    except TimeoutError:  # the run's wall-clock bound (RX1-D §4.7)
        reason = "wall_clock"
    except ModelTimeout:
        reason = "timeout"
    except Exception as error:  # noqa: BLE001 - any other failure ends the run as an error
        leaves = _leaves(error)  # an exception group's own errors, not the group (rx2-1)
        reason = (
            "timeout"
            if any(isinstance(e, (ModelTimeout, TimeoutError)) for e in leaves)
            else "error"
        )
        for leaf in leaves:
            log.write({"type": "error", "error": f"{type(leaf).__name__}: {leaf}"[:2000]})
    finally:  # also on cancellation and KeyboardInterrupt, which then propagate
        log.write({"type": "end", "reason": reason, "totals": totals})
        log.close()
        shutil.rmtree(work, ignore_errors=True)
    after = json.loads((spec.base / "base.json").read_text(encoding="utf-8"))
    changed = tree_digests(spec.base / "data") != base_before["files"] or after != base_before
    if changed:
        raise RuntimeError(f"the base cache {spec.base} changed during run {run_id}; batch stopped")
    return {"run": run_id, "reason": reason, "totals": totals}


async def _run(spec: RunSpec, run_id: str, log: AgentLog, work: Path, totals: dict,
               lesson_text: str = "", lesson_info: dict | None = None) -> str:  # fmt: skip
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    shutil.copytree(spec.base / "data", work)  # RX1-D §4.6: one starting cache for every run
    for path in work.rglob("*"):
        path.chmod(0o644 if path.is_file() else 0o755)
    guide = guide_of(spec.arm)
    model = make_model(spec.model, spec.reasoning_effort, cache=spec.cache, session_id=run_id)
    env = dict(os.environ) | {"CALLIOPE_RUN_ID": run_id, "CALLIOPE_RUN_RECORDS": str(spec.records)}
    root = spec.server or REPO  # LT-D §6.3: a variant's server from its own tree
    if spec.server is not None:
        env["PYTHONPATH"] = os.pathsep.join([str(root / "src"), str(root)])
    params = StdioServerParameters(command=sys.executable, cwd=str(root), env=env,
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
            served = served_version(init)
            if spec.tools is not None or spec.server is not None:  # LT-D §6.3
                log.write({"type": "server", "tools_version": served, "root": str(root)})
                expected = TOOLS_VERSIONS.get(spec.tools)
                if expected is not None and served != expected:
                    log.write({"type": "error", "error": f"the server serves {served}, "
                                                         f"not the variant's {expected}"})  # fmt: skip
                    return "error"
            listed = await session.list_tools()
            tools = [{"type": "function", "function": {
                "name": t.name, "description": t.description or "",
                "parameters": t.input_schema if hasattr(t, "input_schema") else t.inputSchema}}
                for t in listed.tools]  # fmt: skip
            await session.read_resource(BUILD_URI)  # starts the engine: its `build` line (RX2-D §3)
            wrong = build_problem(spec.records / run_id / "tools.jsonl", spec.base)
            if wrong:
                log.write({"type": "error", "error": wrong})
                return "error"
            read_guide = await session.read_resource(GUIDE_URI)
            guide_text = read_guide.contents[0].text
            system = "\n\n".join(x for x in (init.instructions or "", guide_text,
                                              lesson_text) if x)  # fmt: skip
            if spec.arm in HARNESS_ARMS:
                from .harness import HARNESS_GUIDE, PER_MOMENT, PROMPTS, harness_tools, revision_of

                if revision_of(spec) in PER_MOMENT:  # TB-D B2: the harness guide and its tools
                    name = spec.harness_guide or HARNESS_GUIDE
                    guide_text = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
                    system = "\n\n".join(x for x in (guide_text, lesson_text) if x)
                    tools = harness_tools(tools)
            in_order = sorted(zip(spec.moments, moments))  # HS-D §2: the moments in game order
            if spec.arm in HARNESS_ARMS:
                from .harness import ALL_MESSAGES, revision_of

                if not spec.game_id:
                    raise ValueError("arm H names the game by its id (RX2 A1)")
                task = ALL_MESSAGES[revision_of(spec)]["task"].format(
                    game_id=spec.game_id, moments=", ".join(m for _, m in in_order)
                )
            elif spec.game_id:
                task = TASK_BY_ID.format(game_id=spec.game_id, moments=", ".join(moments))
            else:
                task = TASK.format(moments=", ".join(moments)) + "\n\n" + spec.pgn
            messages = [{"role": "system", "content": system}, {"role": "user", "content": task}]
            log.write({"type": "setup", "request_fields": sorted(model.body(messages, tools)),
                       "moments_named": moments, "guide": guide,
                       "system_sha256": hashlib.sha256(system.encode()).hexdigest(),
                       "lessons": (lesson_info or {}).get("lesson_ids", []),
                       "tools": [t["function"]["name"] for t in tools]})  # fmt: skip
            if spec.arm in HARNESS_ARMS:
                from .harness import harness_loop

                judge_model = make_model(
                    spec.model, spec.reasoning_effort, cache=False, session_id=run_id, judge=True
                )
                reason = await harness_loop(
                    session, model, messages, tools, spec, log, totals, _loop, judge_model, in_order
                )
            else:
                reason = await _loop(session, model, messages, tools, spec, log, totals, {}, 0)
    wrong = build_problem(spec.records / run_id / "tools.jsonl", spec.base)
    if wrong:  # an engine that restarted on another build during the run
        log.write({"type": "error", "error": wrong})
        return "error"
    return reason


async def _loop(
    session, model, messages, tools, spec, log, totals, retries, sent, guard=None
) -> str:
    bounds = spec.bounds
    while True:
        if totals["turns"] >= bounds.turns:
            return "turns"
        if totals["input_tokens"] + totals["output_tokens"] >= bounds.tokens:
            return "tokens"
        if bounds.cost is not None and totals["cost"] >= bounds.cost:  # TB-D B5
            return "cost"
        if guard is not None:  # TB-D B4.2: counted before sending; over a limit, nothing is sent
            verdict = await anyio.to_thread.run_sync(
                guard.check, model, messages, tools, abandon_on_cancel=True
            )
            if verdict is not None:
                return verdict
        log.write({"type": "request", "messages": messages[sent:],
                   "tools_offered": len(tools)})  # fmt: skip
        sent = len(messages)
        reply = await anyio.to_thread.run_sync(  # abandoned at the run's bound (N1)
            model.complete, messages, tools, abandon_on_cancel=True
        )
        if guard is not None:
            guard.answered(reply.usage, sent)
        totals["turns"] += 1
        for k in ("input_tokens", "output_tokens"):
            totals[k] += reply.usage.get(k) or 0
        totals["cost"] += reply.usage.get("cost") or 0.0
        log.write({"type": "response", "message": reply.message, "usage": reply.usage})
        # TB-D C4, for rev. 9 (a guard) and the Claude API only (implementation review F6): rev. 8
        # and arm A on OpenRouter replay as they ran
        strict = guard is not None or getattr(model, "provider", None) == "claude"
        if strict and getattr(reply, "cut", False):  # re-review F2: never kept, never run
            cuts = retries.get("_cuts", 0) + 1
            retries["_cuts"] = cuts
            log.write({"type": "cut", "count": cuts})
            for call in reply.message.get("tool_calls") or []:  # review F4: the checker knows
                log.write({"type": "tool_unsent", "tool_call_id": call.get("id"),
                           "tool": (call.get("function") or {}).get("name"), "reason": "cut"})  # fmt: skip
            if cuts >= 2:
                return "moment_cut"
            messages.append({"role": "user", "content": CUT_MESSAGE})
            continue
        retries["_cuts"] = 0
        if strict and getattr(reply, "refused", False):  # C4: the refusal ends the moment
            log.write({"type": "refusal", "category": reply.usage.get("refusal")})
            return "moment_refused"
        if strict and getattr(reply, "stop", None) == "pause_turn":  # review N4: not expected
            log.write({"type": "error", "error": "pause_turn without server tools"})
            return "error"
        message = {"role": "assistant", "content": reply.message.get("content")}
        for key in ("tool_calls", "reasoning", "reasoning_details", "blocks"):  # TB-D C3: blocks
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
                if hasattr(session, "next_call_id"):  # HS-D §2: the gate logs a call it holds back
                    session.next_call_id = call.get("id")
                try:
                    with anyio.fail_after(bounds.tool_seconds):
                        result = await session.call_tool(name, arguments)
                except TimeoutError:
                    log.write(
                        {"type": "error", "error": f"{name}: no answer in {bounds.tool_seconds} s"}
                    )
                    raise ModelTimeout("tool timeout") from None
                text, error = _tool_text(result)
                if error and SCHEMA_REFUSED.match(text):  # the tool never ran, nor logged a call
                    log.write({"type": "tool_unsent", "tool_call_id": call.get("id"), "tool": name,
                               "reason": "server_schema"})  # fmt: skip
            messages.append({"role": "tool", "tool_call_id": call.get("id"),
                             "content": f"[tool error] {text}" if error else text})  # fmt: skip
            if isinstance(arguments, dict):
                feedback += retry_feedback(spec.arm, name, arguments, text, error, retries,
                                           bounds.retries_per_subject)  # fmt: skip
        if getattr(session, "done_early", None) is not None and session.done_early():
            return "done"  # rev. 13: every ply of the batch accepted; no answer needed after it
        for subject, problems, round_ in feedback:  # RX1-D §4.3: after every tool result
            messages.append({"role": "user", "content": retry_message(subject, problems)})
            log.write({"type": "feedback", "arm": spec.arm, "subject": subject, "round": round_,
                       "problems": problems})  # fmt: skip
