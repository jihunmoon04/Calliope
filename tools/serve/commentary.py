"""Local web-app runner for 3-tier AI commentary over a completed game analysis."""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import secrets
import shutil
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from calliope.server.jobs import QueueFull
from calliope.server.web import CommentaryUnavailable

REPO = Path(__file__).resolve().parents[2]
DEFAULT_COST_LIMIT = 1.0
DEFAULT_HARNESS_REVISION = 19
DEFAULT_CLAUDE_MODEL = "claude-haiku-5-5"
DEFAULT_OPENROUTER_MODEL = "anthropic/claude-haiku-5.5"
MOMENT_PRIORITY = {
    "blunder": 1,
    "mistake": 2,
    "miss": 3,
    "brilliant": 4,
    "great": 5,
    "loss": 6,
    "turning_point": 7,
    "inaccuracy": 8,
}
ERROR_REASONS = {"blunder", "mistake"}
SPECIAL_REASONS = {"miss", "brilliant", "great"}

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _has_package(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def resolve_stockfish_path(path: str) -> str:
    """Resolve a Stockfish path against the caller's cwd before launching subprocesses elsewhere."""

    expanded = Path(path).expanduser()
    if expanded.is_absolute():
        return str(expanded)
    if expanded.parent != Path(".") or expanded.exists():
        return str(expanded.resolve())
    found = shutil.which(path)
    return str(Path(found).resolve()) if found else path


def _exception_leaves(error: BaseException) -> list[BaseException]:
    """Flatten nested ExceptionGroup / BaseExceptionGroup leaf exceptions."""

    if isinstance(error, BaseExceptionGroup):
        out: list[BaseException] = []
        for item in error.exceptions:
            out.extend(_exception_leaves(item))
        return out
    return [error]


@dataclass(frozen=True, slots=True)
class CommentaryConfig:
    """Resolved runtime configuration for AI commentary generation."""

    enabled: bool
    model: str | None
    reason: str | None = None
    cost_limit: float = DEFAULT_COST_LIMIT
    harness_revision: int = DEFAULT_HARNESS_REVISION


def resolve_config(
    *,
    enabled: bool = True,
    model: str | None = None,
    cost_limit: float = DEFAULT_COST_LIMIT,
    env: Mapping[str, str] | None = None,
) -> CommentaryConfig:
    """Determine whether AI commentary can run and which model/provider to use."""

    if not enabled:
        return CommentaryConfig(
            enabled=False,
            model=None,
            reason="AI 해설 생성이 비활성화되어 있습니다 (--no-commentary).",
            cost_limit=cost_limit,
        )
    if not _has_package("mcp"):
        return CommentaryConfig(
            enabled=False,
            model=None,
            reason='MCP 패키지가 설치되지 않았습니다 (pip install -e ".[agent]").',
            cost_limit=cost_limit,
        )
    environ = os.environ if env is None else env
    anthropic_key = (environ.get("ANTHROPIC_API_KEY") or "").strip()
    openrouter_key = (environ.get("OPENROUTER_API_KEY") or "").strip()
    has_anthropic = _has_package("anthropic")

    if model is not None:
        from tools.rx.claude import PRICES as CLAUDE_PRICES
        from tools.rx.model import is_claude

        if is_claude(model):
            if not has_anthropic:
                return CommentaryConfig(
                    enabled=False,
                    model=model,
                    reason='anthropic 패키지가 설치되지 않았습니다 (pip install -e ".[agent]").',
                    cost_limit=cost_limit,
                )
            if not anthropic_key:
                return CommentaryConfig(
                    enabled=False,
                    model=model,
                    reason="ANTHROPIC_API_KEY가 설정되지 않았습니다.",
                    cost_limit=cost_limit,
                )
            if model not in CLAUDE_PRICES:
                supported = ", ".join(sorted(CLAUDE_PRICES))
                return CommentaryConfig(
                    enabled=False,
                    model=model,
                    reason=(
                        f"비용 추적이 지원되지 않는 Claude 모델입니다 ({model}). "
                        f"지원 모델({supported}) 또는 OpenRouter 모델을 사용하세요."
                    ),
                    cost_limit=cost_limit,
                )
        elif not openrouter_key:
            return CommentaryConfig(
                enabled=False,
                model=model,
                reason="OPENROUTER_API_KEY가 설정되지 않았습니다.",
                cost_limit=cost_limit,
            )
        return CommentaryConfig(
            enabled=True,
            model=model,
            reason=None,
            cost_limit=cost_limit,
        )

    if anthropic_key and has_anthropic:
        return CommentaryConfig(
            enabled=True,
            model=DEFAULT_CLAUDE_MODEL,
            reason=None,
            cost_limit=cost_limit,
        )
    if openrouter_key:
        return CommentaryConfig(
            enabled=True,
            model=DEFAULT_OPENROUTER_MODEL,
            reason=None,
            cost_limit=cost_limit,
        )
    if anthropic_key:
        return CommentaryConfig(
            enabled=False,
            model=None,
            reason='anthropic 패키지가 설치되지 않았습니다 (pip install -e ".[agent]").',
            cost_limit=cost_limit,
        )
    return CommentaryConfig(
        enabled=False,
        model=None,
        reason="API 키가 설정되지 않았습니다 (ANTHROPIC_API_KEY 또는 OPENROUTER_API_KEY).",
        cost_limit=cost_limit,
    )


def select_moments(
    overview_lines: list[dict],
    moments: list[dict],
    ply_range: tuple[int, int] | None = None,
    limit: int = 3,
) -> list[int]:
    """Choose up to `limit` Tier-2 plies from analysed moves, mirroring `rx_moments`."""

    if limit <= 0:
        return []
    first, last = ply_range if ply_range is not None else (None, None)
    analysed = [
        line
        for line in overview_lines
        if isinstance(line, dict)
        and isinstance(line.get("ply"), int)
        and line.get("analysed") is not False
        and (ply_range is None or first <= line["ply"] <= last)
    ]
    if not analysed:
        return []

    by_ply = {line["ply"]: line for line in analysed}
    analysed_set = set(by_ply)
    reasons_by_ply: dict[int, set[str]] = {}
    for m in moments:
        if isinstance(m, dict) and m.get("ply") in analysed_set and m.get("reasons"):
            reasons_by_ply.setdefault(m["ply"], set()).update(m["reasons"])

    for line in analysed:
        ply = line["ply"]
        reasons = reasons_by_ply.setdefault(ply, set())
        if line.get("grade") in ("blunder", "mistake", "inaccuracy"):
            reasons.add(line["grade"])
        if line.get("label") in SPECIAL_REASONS:
            reasons.add(line["label"])

    big_losses = sorted(
        (line for line in analysed if (line.get("loss") or 0) >= 150),
        key=lambda line: (-(line.get("loss") or 0), line["ply"]),
    )[:3]
    for line in big_losses:
        reasons_by_ply.setdefault(line["ply"], set()).add("loss")

    def rank_key(item: dict) -> tuple[int, float, int]:
        ply = item["ply"]
        pri = min(MOMENT_PRIORITY.get(r, 99) for r in item["reasons"])
        loss = by_ply[ply].get("loss") or 0
        return (pri, -loss, ply)

    ranked = sorted(
        (
            {"ply": ply, "reasons": sorted(reasons)}
            for ply, reasons in reasons_by_ply.items()
            if reasons
        ),
        key=rank_key,
    )
    errors = [m["ply"] for m in ranked if set(m["reasons"]) & ERROR_REASONS][:2]
    chosen = list(errors)
    special = next(
        (
            m["ply"]
            for m in ranked
            if (set(m["reasons"]) & SPECIAL_REASONS) and m["ply"] not in chosen
        ),
        None,
    )
    if special is not None and len(chosen) < limit:
        chosen.append(special)
    for m in ranked:
        if len(chosen) >= limit:
            break
        if m["ply"] not in chosen:
            chosen.append(m["ply"])

    if not chosen:
        fallback = max(analysed, key=lambda line: (line.get("loss") or 0, line["ply"]))
        chosen.append(fallback["ply"])

    return sorted(chosen[:limit])


def _tool_text(result) -> str:
    return "\n".join(
        getattr(c, "text", "")
        for c in (getattr(result, "content", None) or [])
        if getattr(c, "type", None) == "text"
    )


def _is_tool_error(result) -> bool:
    return bool(getattr(result, "is_error", False) or getattr(result, "isError", False))


class _RangeSession:
    """Wrap an MCP `ClientSession` so `game_overview` masks plies outside `ply_range`."""

    def __init__(self, session, ply_range: tuple[int, int]) -> None:
        self._session = session
        self._first, self._last = ply_range

    async def call_tool(self, name: str, arguments: dict | None = None):
        result = await self._session.call_tool(name, arguments)
        if name != "game_overview" or _is_tool_error(result):
            return result
        text = _tool_text(result)
        if not text:
            return result
        try:
            data = json.loads(text)
        except ValueError:
            return result
        if not isinstance(data, dict) or not isinstance(data.get("lines"), list):
            return result
        masked = []
        for line in data["lines"]:
            if isinstance(line, dict) and isinstance(line.get("ply"), int):
                ply = line["ply"]
                if not (self._first <= ply <= self._last):
                    masked.append({"ply": ply, "move": line.get("move", ""), "analysed": False})
                    continue
            masked.append(line)
        data = dict(data)
        data["lines"] = masked
        if isinstance(data.get("moments"), list):
            data["moments"] = [
                m
                for m in data["moments"]
                if isinstance(m, dict)
                and isinstance(m.get("ply"), int)
                and self._first <= m["ply"] <= self._last
            ]
        encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=encoded)],
            isError=False,
            is_error=False,
            structuredContent=data,
        )

    def __getattr__(self, name: str):
        return getattr(self._session, name)


class ProgressLog:
    """Log sink passed to `harness_loop_v9` that emits live job progress snapshots."""

    def __init__(
        self,
        totals: dict,
        on_update: Callable[[dict], None],
        *,
        tier2_total: int = 0,
    ) -> None:
        self.totals = totals
        self.on_update = on_update
        self.tier0_notes: list[dict] = []
        self.accepted_plies: set[int] = set()
        self.state = {
            "phase": "tier2",
            "current_ply": None,
            "tier2_done": 0,
            "tier2_total": tier2_total,
            "tier1_done": 0,
            "tier1_total": 0,
            "accepted": 0,
            "cost": 0.0,
        }

    def snapshot(self) -> dict:
        return dict(self.state) | {
            "cost": round(float(self.totals.get("cost") or 0.0), 6),
            "tier0_notes": list(self.tier0_notes),
        }

    def record_submit(self, arguments: dict, text: str, game) -> None:
        """Count accepted commentary immediately when `submit_commentary` succeeds."""

        from tools.rx import harness

        if not harness.accepted(text):
            return
        subjects = harness.accepted_subjects(
            harness.normalized(arguments), text, game, self.state.get("current_ply")
        )
        added = False
        for ply, _, _ in subjects:
            if isinstance(ply, int) and ply not in self.accepted_plies:
                self.accepted_plies.add(ply)
                added = True
        if added:
            self.state["accepted"] = max(int(self.state["accepted"]), len(self.accepted_plies))
            self.on_update(self.snapshot())
        elif not subjects:
            self.state["accepted"] += 1
            self.on_update(self.snapshot())

    def write(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "moment_start":
            self.state["phase"] = "tier2"
            self.state["current_ply"] = event.get("ply")
        elif kind == "harness" and event.get("stage") == "moment_end":
            self.state["tier2_done"] += 1
            if event.get("reason") == "submitted":
                ply = event.get("ply")
                if isinstance(ply, int):
                    self.accepted_plies.add(ply)
                    self.state["accepted"] = max(
                        int(self.state["accepted"]), len(self.accepted_plies)
                    )
                else:
                    self.state["accepted"] += 1
        elif kind == "tiers_plan":
            self.state["phase"] = "tier1"
            self.state["tier1_total"] = len(event.get("tier1") or [])
            self.state["tier1_done"] = 0
        elif kind == "batch_start":
            self.state["phase"] = "tier1"
            plies = event.get("plies") or []
            self.state["current_ply"] = plies[0] if plies else None
        elif kind == "batch_end":
            self.state["tier1_done"] += len(event.get("plies") or [])
            accepted = [p for p in (event.get("accepted") or []) if isinstance(p, int)]
            if accepted:
                self.accepted_plies.update(accepted)
                self.state["accepted"] = max(
                    int(self.state["accepted"]), len(self.accepted_plies)
                )
            else:
                self.state["accepted"] += len(event.get("accepted") or [])
        elif kind == "tier0":
            self.tier0_notes.append(
                {
                    k: event[k]
                    for k in ("ply", "from_ply", "until_ply", "ref", "text", "source")
                    if k in event
                }
            )
        elif kind == "tiers":
            self.state["phase"] = "finishing"
            self.state["current_ply"] = None
            cov = event.get("coverage") or {}
            if "tier2" in cov and "tier1" in cov:
                self.state["accepted"] = max(
                    int(self.state["accepted"]), int(cov["tier2"]) + int(cov["tier1"])
                )
        self.on_update(self.snapshot())


class _TrackingSession:
    """Wrap a session so accepted `submit_commentary` calls update `ProgressLog` live."""

    def __init__(self, session, progress_log: ProgressLog, game) -> None:
        self._session = session
        self._progress = progress_log
        self._game = game

    async def call_tool(self, name: str, arguments: dict | None = None):
        result = await self._session.call_tool(name, arguments)
        if name == "submit_commentary" and not _is_tool_error(result) and isinstance(arguments, dict):
            self._progress.record_submit(arguments, _tool_text(result), self._game)
        return result

    def __getattr__(self, name: str):
        return getattr(self._session, name)


async def _overview_all(session, game_id: str, total_plies: int) -> tuple[list[dict], list[dict]]:
    lines: list[dict] = []
    moments: list[dict] = []
    for start in range(1, total_plies + 1, 200):
        end = min(start + 199, total_plies)
        result = await session.call_tool(
            "game_overview", {"game": game_id, "plies": f"{start}-{end}"}
        )
        if _is_tool_error(result):
            raise RuntimeError(_tool_text(result) or "game_overview failed")
        data = json.loads(_tool_text(result))
        lines.extend(
            x for x in (data.get("lines") or []) if isinstance(x, dict) and isinstance(x.get("ply"), int)
        )
        if start == 1:
            moments = list(data.get("moments") or [])
    return lines, moments


async def run_commentary(
    pgn: str,
    data_dir: Path,
    stockfish_path: str,
    config: CommentaryConfig,
    *,
    ply_range: tuple[int, int] | None = None,
    cancel_event: threading.Event | None = None,
    on_update: Callable[[dict], None] | None = None,
    run_seconds: float | None = None,
    expected_env: dict | None = None,
) -> dict:
    """Run 3-tier AI commentary for one analysed game via `tools.mcp`."""

    import sys

    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    from calliope.agent.record import new_run_id
    from calliope.facts import FactEngine, OpenRequest
    from calliope.server import game_key, parse_game
    from tools.rx import harness
    from tools.rx import run as rx_run
    from tools.rx.model import make_model

    if not config.enabled or not config.model:
        raise CommentaryUnavailable(config.reason or "AI 해설 생성기를 사용할 수 없습니다.")

    update = on_update or (lambda _snap: None)
    cancel = cancel_event or threading.Event()
    timed_out = threading.Event()
    abort = threading.Event()
    run_id = new_run_id()
    totals = {"turns": 0, "tool_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}
    resolved_data = data_dir.expanduser().resolve()
    resolved_stockfish = resolve_stockfish_path(stockfish_path)
    timeout_s = float(rx_run.Bounds().run_seconds if run_seconds is None else run_seconds)

    env = dict(os.environ)
    env.pop("CALLIOPE_RUN_RECORDS", None)
    env.pop("CALLIOPE_RUN_ID", None)
    env["PYTHONUTF8"] = "1"
    env["CALLIOPE_STANDING_NUMBERS"] = "1"
    env["CALLIOPE_STOCKFISH_PATH"] = resolved_stockfish
    py_entries = [str(REPO / "src"), str(REPO)]
    existing_pp = env.get("PYTHONPATH")
    if existing_pp:
        py_entries.append(existing_pp)
    env["PYTHONPATH"] = os.pathsep.join(py_entries)

    mcp_args = ["-m", "tools.mcp", "--data", str(resolved_data), "--guide", "commentary_ko_v8"]
    parsed_pgn = parse_game(pgn)
    if parsed_pgn.root.fen is not None:
        norm_fen = FactEngine().normalize_open(OpenRequest(root=parsed_pgn.root)).root.fen
        if norm_fen != parsed_pgn.game.start_fen:
            mcp_args.extend(["--root-fen", f"{game_key(parsed_pgn.game)}={parsed_pgn.root.fen}"])
    if expected_env is not None:
        mcp_args.extend(
            ["--expect-env", json.dumps(expected_env, separators=(",", ":"), sort_keys=True)]
        )

    params = StdioServerParameters(
        command=sys.executable,
        cwd=str(REPO),
        env=env,
        args=mcp_args,
    )

    progress_log: ProgressLog | None = None
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as errlog:
        try:
            if cancel.is_set():
                abort.set()
                return {
                    "reason": "cancelled",
                    "totals": totals,
                    "accepted": 0,
                    "tier0_notes": [],
                }
            reason = "cancelled"
            async with anyio.create_task_group() as tg:
                done = anyio.Event()
                deadline = time.monotonic() + timeout_s
                with anyio.CancelScope() as run_scope:

                    async def watch_cancel() -> None:
                        while not done.is_set():
                            if cancel.is_set():
                                abort.set()
                                run_scope.cancel()
                                return
                            remaining = deadline - time.monotonic()
                            if remaining <= 0:
                                timed_out.set()
                                abort.set()
                                run_scope.cancel()
                                return
                            with anyio.move_on_after(min(0.2, remaining)):
                                await done.wait()

                    tg.start_soon(watch_cancel)
                    try:
                        with anyio.fail_after(timeout_s):
                            async with (
                                stdio_client(params, errlog=errlog) as (read, write),
                                ClientSession(read, write) as session,
                            ):
                                await session.initialize()
                                open_res = await session.call_tool("open_game", {"pgn": pgn})
                                if _is_tool_error(open_res):
                                    raise RuntimeError(_tool_text(open_res) or "open_game failed")
                                open_data = json.loads(_tool_text(open_res))
                                game_id = open_data["game"]
                                total_plies = len(open_data.get("moves") or [])

                                overview_lines, overview_moments = await _overview_all(
                                    session, game_id, total_plies
                                )
                                chosen = select_moments(
                                    overview_lines, overview_moments, ply_range
                                )
                                if not chosen:
                                    reason = "no_plies"
                                else:
                                    all_sans = harness.numbered_sans(pgn)
                                    in_order = [(p, all_sans[p - 1]) for p in sorted(chosen)]
                                    progress_log = ProgressLog(
                                        totals, update, tier2_total=len(in_order)
                                    )
                                    update(progress_log.snapshot())

                                    listed = await session.list_tools()
                                    tools = [
                                        {
                                            "type": "function",
                                            "function": {
                                                "name": t.name,
                                                "description": t.description or "",
                                                "parameters": (
                                                    t.input_schema
                                                    if hasattr(t, "input_schema")
                                                    else t.inputSchema
                                                ),
                                            },
                                        }
                                        for t in listed.tools
                                    ]
                                    rev = config.harness_revision
                                    tools = harness.harness_tools(tools)
                                    system = (
                                        harness.PROMPTS / f"{harness.guide_of(rev)}.md"
                                    ).read_text(encoding="utf-8")
                                    task = harness.ALL_MESSAGES[rev]["task"].format(
                                        game_id=game_id,
                                        moments=", ".join(m for _, m in in_order),
                                    )
                                    messages = [
                                        {"role": "system", "content": system},
                                        {"role": "user", "content": task},
                                    ]
                                    model = make_model(
                                        config.model,
                                        cache=True,
                                        session_id=run_id,
                                        cancel_event=abort,
                                    )
                                    judge_model = make_model(
                                        config.model,
                                        cache=False,
                                        session_id=run_id,
                                        judge=True,
                                        cancel_event=abort,
                                    )
                                    spec = rx_run.RunSpec(
                                        arm="H",
                                        set_name="local",
                                        game=run_id[:12],
                                        pgn=pgn,
                                        moments=[p for p, _ in in_order],
                                        base=resolved_data,
                                        records=resolved_data,
                                        work=resolved_data,
                                        model=config.model,
                                        bounds=rx_run.Bounds(cost=config.cost_limit),
                                        game_id=game_id,
                                        harness_revision=rev,
                                    )
                                    base_session = (
                                        _RangeSession(session, ply_range)
                                        if ply_range is not None
                                        and ply_range != (1, total_plies)
                                        else session
                                    )
                                    target_session = _TrackingSession(
                                        base_session, progress_log, harness.Game(pgn)
                                    )
                                    reason = await harness.harness_loop_v9(
                                        target_session,
                                        model,
                                        messages,
                                        tools,
                                        spec,
                                        progress_log,
                                        totals,
                                        rx_run._loop,
                                        judge_model,
                                        in_order,
                                    )
                    except TimeoutError:
                        timed_out.set()
                        abort.set()
                        reason = "timeout"
                    finally:
                        done.set()

            snap = progress_log.snapshot() if progress_log is not None else {}
            if timed_out.is_set():
                return {
                    "reason": "timeout",
                    "totals": totals,
                    "accepted": snap.get("accepted", 0),
                    "tier0_notes": snap.get("tier0_notes", []),
                    "error": f"AI 해설 생성 제한 시간({int(timeout_s)}초)을 초과했습니다.",
                }
            if cancel.is_set():
                abort.set()
                reason = "cancelled"
            return {
                "reason": reason,
                "totals": totals,
                "accepted": snap.get("accepted", 0),
                "tier0_notes": snap.get("tier0_notes", []),
            }
        except TimeoutError:
            timed_out.set()
            abort.set()
            snap = progress_log.snapshot() if progress_log is not None else {}
            return {
                "reason": "timeout",
                "totals": totals,
                "accepted": snap.get("accepted", 0),
                "tier0_notes": snap.get("tier0_notes", []),
                "error": f"AI 해설 생성 제한 시간({int(timeout_s)}초)을 초과했습니다.",
            }
        except BaseException as error:
            abort.set()
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            snap = progress_log.snapshot() if progress_log is not None else {}
            leaves = _exception_leaves(error)
            if timed_out.is_set() or any(isinstance(item, TimeoutError) for item in leaves):
                return {
                    "reason": "timeout",
                    "totals": totals,
                    "accepted": snap.get("accepted", 0),
                    "tier0_notes": snap.get("tier0_notes", []),
                    "error": f"AI 해설 생성 제한 시간({int(timeout_s)}초)을 초과했습니다.",
                }
            if cancel.is_set():
                return {
                    "reason": "cancelled",
                    "totals": totals,
                    "accepted": snap.get("accepted", 0),
                    "tier0_notes": snap.get("tier0_notes", []),
                }
            errlog.seek(0)
            tail = errlog.read()[-800:].strip()
            detail = "; ".join(f"{type(item).__name__}: {item}" for item in leaves) or str(error)
            if tail:
                raise RuntimeError(f"{detail} (mcp stderr: {tail})") from error
            if leaves != [error]:
                raise RuntimeError(detail) from error
            raise


def _run_sync(
    pgn: str,
    data_dir: Path,
    stockfish_path: str,
    config: CommentaryConfig,
    *,
    ply_range: tuple[int, int] | None,
    cancel_event: threading.Event,
    on_update: Callable[[dict], None],
    expected_env: dict | None = None,
) -> dict:
    import anyio

    return anyio.run(
        lambda: run_commentary(
            pgn,
            data_dir,
            stockfish_path,
            config,
            ply_range=ply_range,
            cancel_event=cancel_event,
            on_update=on_update,
            expected_env=expected_env,
        )
    )


@dataclass
class CommentaryJob:
    id: str
    pgn: str
    ply_range: tuple[int, int] | None
    created: str
    run_id: str = field(default_factory=lambda: secrets.token_hex(8))
    expected_env: dict | None = None
    state: str = "queued"  # queued | running | done | cancelled | failed
    cancelling: bool = False
    phase: str | None = None
    current_ply: int | None = None
    tier2_done: int = 0
    tier2_total: int = 0
    tier1_done: int = 0
    tier1_total: int = 0
    accepted: int = 0
    cost: float = 0.0
    end_reason: str | None = None
    error: str | None = None
    started: str | None = None
    finished: str | None = None
    tier0_notes: list[dict] = field(default_factory=list)
    cancel_event: threading.Event = field(default_factory=threading.Event)


Runner = Callable[..., dict]


class CommentaryJobs:
    """In-memory single-worker queue for local AI commentary generation."""

    def __init__(
        self,
        data: Path,
        stockfish_path: str,
        config: CommentaryConfig,
        *,
        runner: Runner | None = None,
        queue_limit: int = 10,
    ) -> None:
        self.data = data.expanduser().resolve()
        self.stockfish_path = resolve_stockfish_path(stockfish_path)
        self.config = config
        self.runner = runner if runner is not None else _run_sync
        self.queue_limit = queue_limit
        self.lock = threading.Condition()
        self.jobs: dict[str, CommentaryJob] = {}
        self.queue: list[str] = []
        self._thread: threading.Thread | None = None
        self._stopping = False

    def capabilities(self) -> dict:
        return {
            "available": self.config.enabled,
            "model": self.config.model,
            "reason": self.config.reason,
            "cost_limit": self.config.cost_limit,
        }

    def status(self, jid: str) -> dict:
        with self.lock:
            job = self.jobs.get(jid)
            if job is None:
                return self._idle_status()
            return self._status(job)

    def start(
        self,
        jid: str,
        pgn: str,
        ply_range: tuple[int, int] | None = None,
        *,
        expected_env: dict | None = None,
    ) -> tuple[dict, bool]:
        if not self.config.enabled:
            raise CommentaryUnavailable(self.config.reason or "AI 해설 생성기를 사용할 수 없습니다.")
        with self.lock:
            existing = self.jobs.get(jid)
            if existing is not None and existing.state in ("queued", "running"):
                return self._status(existing), True
            if len(self.queue) >= self.queue_limit:
                raise QueueFull(f"{len(self.queue)} commentary jobs are already queued")
            job = CommentaryJob(
                id=jid,
                pgn=pgn,
                ply_range=ply_range,
                created=_now(),
                expected_env=dict(expected_env) if expected_env is not None else None,
            )
            self.jobs[jid] = job
            self.queue.append(jid)
            self.lock.notify_all()
            return self._status(job), False

    def cancel(self, jid: str) -> dict:
        with self.lock:
            job = self.jobs.get(jid)
            if job is None:
                return self._idle_status()
            if job.state == "queued":
                if jid in self.queue:
                    self.queue.remove(jid)
                job.state = "cancelled"
                job.end_reason = "cancelled"
                job.finished = _now()
            elif job.state == "running":
                job.cancelling = True
                job.cancel_event.set()
            return self._status(job)

    def start_worker(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._work, name="calliope-commentary", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> bool:
        with self.lock:
            self._stopping = True
            for jid in list(self.queue):
                job = self.jobs.get(jid)
                if job is not None and job.state == "queued":
                    job.state = "cancelled"
                    job.end_reason = "cancelled"
                    job.finished = _now()
            self.queue.clear()
            for job in self.jobs.values():
                if job.state == "running":
                    job.cancelling = True
                    job.cancel_event.set()
            self.lock.notify_all()
        if self._thread is not None:
            self._thread.join(timeout)
            return not self._thread.is_alive()
        return True

    def run_next(self) -> bool:
        with self.lock:
            if not self.queue or self._stopping:
                return False
            job = self.jobs[self.queue.pop(0)]
            job.state = "running"
            job.started = _now()
            job.phase = "starting"
            pgn, ply_range, cancel_event, expected_env = (
                job.pgn,
                job.ply_range,
                job.cancel_event,
                job.expected_env,
            )

        def on_update(snap: dict) -> None:
            with self.lock:
                job.phase = snap.get("phase")
                job.current_ply = snap.get("current_ply")
                job.tier2_done = int(snap.get("tier2_done") or 0)
                job.tier2_total = int(snap.get("tier2_total") or 0)
                job.tier1_done = int(snap.get("tier1_done") or 0)
                job.tier1_total = int(snap.get("tier1_total") or 0)
                job.accepted = int(snap.get("accepted") or 0)
                job.cost = float(snap.get("cost") or 0.0)
                if "tier0_notes" in snap:
                    job.tier0_notes = list(snap.get("tier0_notes") or [])

        try:
            kwargs = {
                "ply_range": ply_range,
                "cancel_event": cancel_event,
                "on_update": on_update,
            }
            if expected_env is not None:
                import inspect

                params = inspect.signature(self.runner).parameters.values()
                if any(
                    p.name == "expected_env" or p.kind is inspect.Parameter.VAR_KEYWORD
                    for p in params
                ):
                    kwargs["expected_env"] = expected_env
            result = self.runner(
                pgn,
                self.data,
                self.stockfish_path,
                self.config,
                **kwargs,
            )
        except Exception as error:
            log.exception("commentary job %s failed", job.id)
            with self.lock:
                job.phase = None
                job.current_ply = None
                job.finished = _now()
                job.cancelling = False
                if cancel_event.is_set():
                    job.state = "cancelled"
                    job.end_reason = "cancelled"
                else:
                    job.state = "failed"
                    job.error = f"{type(error).__name__}: {error}"
            return True

        with self.lock:
            totals = result.get("totals") or {}
            if "cost" in totals:
                job.cost = round(float(totals.get("cost") or 0.0), 6)
            if "accepted" in result:
                job.accepted = int(result["accepted"] or 0)
            if "tier0_notes" in result:
                job.tier0_notes = list(result.get("tier0_notes") or [])
            reason = result.get("reason")
            job.end_reason = reason
            job.phase = None
            job.current_ply = None
            job.finished = _now()
            job.cancelling = False
            if cancel_event.is_set() or reason == "cancelled":
                job.state = "cancelled"
                job.end_reason = "cancelled"
            elif reason in ("error", "timeout"):
                job.state = "failed"
                job.error = str(result.get("error") or "AI 해설 생성 중 오류가 발생했습니다.")
            else:
                job.state = "done"
        return True

    def _work(self) -> None:
        while True:
            with self.lock:
                while not self.queue and not self._stopping:
                    self.lock.wait()
                if self._stopping:
                    return
            self.run_next()

    def _idle_status(self) -> dict:
        return self.capabilities() | {
            "run_id": None,
            "state": "idle",
            "cancelling": False,
            "phase": None,
            "current_ply": None,
            "tier2": {"done": 0, "total": 0},
            "tier1": {"done": 0, "total": 0},
            "tier0": 0,
            "tier0_notes": [],
            "accepted": 0,
            "cost": 0.0,
            "end_reason": None,
            "error": None,
            "queue_position": None,
            "created": None,
            "started": None,
            "finished": None,
        }

    def _status(self, job: CommentaryJob) -> dict:
        return self.capabilities() | {
            "run_id": job.run_id,
            "state": job.state,
            "cancelling": job.cancelling,
            "phase": job.phase,
            "current_ply": job.current_ply,
            "tier2": {"done": job.tier2_done, "total": job.tier2_total},
            "tier1": {"done": job.tier1_done, "total": job.tier1_total},
            "tier0": len(job.tier0_notes),
            "tier0_notes": list(job.tier0_notes),
            "accepted": job.accepted,
            "cost": job.cost,
            "end_reason": job.end_reason,
            "error": job.error,
            "queue_position": (
                self.queue.index(job.id) + 1
                if job.state == "queued" and job.id in self.queue
                else None
            ),
            "created": job.created,
            "started": job.started,
            "finished": job.finished,
        }
