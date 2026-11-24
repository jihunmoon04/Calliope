"""Unit tests for the local web-app AI commentary runner and Windows compatibility helpers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from calliope.server.files import running
from tools.serve import __main__ as serve_main
from tools.serve import commentary as mod


def test_resolve_config(monkeypatch) -> None:
    monkeypatch.setattr(mod, "_has_package", lambda name: True)

    disabled = mod.resolve_config(enabled=False, env={"ANTHROPIC_API_KEY": "k"})
    assert not disabled.enabled and disabled.model is None and "--no-commentary" in disabled.reason

    both = mod.resolve_config(env={"ANTHROPIC_API_KEY": "ak", "OPENROUTER_API_KEY": "ok"})
    assert both.enabled and both.model == mod.DEFAULT_CLAUDE_MODEL

    openrouter_only = mod.resolve_config(env={"OPENROUTER_API_KEY": "ok"})
    assert openrouter_only.enabled and openrouter_only.model == mod.DEFAULT_OPENROUTER_MODEL

    none_set = mod.resolve_config(env={})
    assert not none_set.enabled and "API 키" in none_set.reason

    explicit_claude_missing_key = mod.resolve_config(
        model="claude-sonnet-5-5", env={"OPENROUTER_API_KEY": "ok"}
    )
    assert not explicit_claude_missing_key.enabled
    assert "ANTHROPIC_API_KEY" in explicit_claude_missing_key.reason

    explicit_or = mod.resolve_config(model="openai/gpt-5", env={"OPENROUTER_API_KEY": "ok"})
    assert explicit_or.enabled and explicit_or.model == "openai/gpt-5"

    monkeypatch.setattr(mod, "_has_package", lambda name: name != "anthropic")
    no_sdk = mod.resolve_config(env={"ANTHROPIC_API_KEY": "ak"})
    assert not no_sdk.enabled and "anthropic" in no_sdk.reason

    monkeypatch.setattr(mod, "_has_package", lambda name: False)
    no_mcp = mod.resolve_config(env={"OPENROUTER_API_KEY": "ok"})
    assert not no_mcp.enabled and "MCP" in no_mcp.reason


def test_select_moments_picks_errors_special_and_fallbacks() -> None:
    lines = [
        {"ply": 1, "move": "1.e4", "grade": "best", "loss": 0},
        {"ply": 2, "move": "1...e5", "grade": "mistake", "loss": 120},
        {"ply": 3, "move": "2.Nf3", "grade": "best", "label": "great", "loss": 0},
        {"ply": 4, "move": "2...Nc6", "grade": "blunder", "loss": 400},
        {"ply": 5, "move": "3.Bb5", "grade": "blunder", "loss": 550},
        {"ply": 6, "move": "3...a6", "analysed": False},
    ]
    # `game_overview` sorts moments by ply, not severity.
    moments = [
        {"ply": 2, "move": "1...e5", "reasons": ["mistake"]},
        {"ply": 3, "move": "2.Nf3", "reasons": ["great"]},
        {"ply": 4, "move": "2...Nc6", "reasons": ["blunder"]},
        {"ply": 5, "move": "3.Bb5", "reasons": ["blunder"]},
    ]
    # Top 2 errors (blunder 5 and blunder 4, NOT earlier mistake 2) + 1 special (great 3).
    assert mod.select_moments(lines, moments) == [3, 4, 5]

    # Partial range ignores plies outside 1..3 and still chooses analysed plies.
    assert mod.select_moments(lines, moments, ply_range=(1, 3)) == [2, 3]

    # Clean game with no moments falls back to largest-loss / latest analysed ply.
    clean = [
        {"ply": 1, "move": "1.e4", "grade": "best", "loss": 0},
        {"ply": 2, "move": "1...e5", "grade": "excellent", "loss": 12},
        {"ply": 3, "move": "2.Nf3", "grade": "good", "loss": 8},
    ]
    assert mod.select_moments(clean, []) == [2]
    assert mod.select_moments([{"ply": 1, "move": "1.e4", "analysed": False}], []) == []


def test_progress_log_tracks_tier2_tier1_and_cost() -> None:
    totals = {"cost": 0.0125}
    snapshots: list[dict] = []
    sink = mod.ProgressLog(totals, snapshots.append, tier2_total=2)
    sink.write({"type": "moment_start", "ply": 4})
    assert snapshots[-1]["phase"] == "tier2" and snapshots[-1]["current_ply"] == 4
    sink.write({"type": "harness", "stage": "moment_end", "ply": 4, "reason": "submitted"})
    assert snapshots[-1]["tier2_done"] == 1 and snapshots[-1]["accepted"] == 1

    totals["cost"] = 0.045
    sink.write({"type": "tiers_plan", "tier1": [7, 9, 11]})
    sink.write({"type": "batch_start", "plies": [7, 9]})
    assert snapshots[-1]["phase"] == "tier1" and snapshots[-1]["tier1_total"] == 3
    sink.write({"type": "batch_end", "plies": [7, 9], "accepted": [7, 9]})
    assert snapshots[-1]["tier1_done"] == 2 and snapshots[-1]["accepted"] == 3

    sink.write({"type": "tiers", "coverage": {"tier2": 1, "tier1": 2}})
    assert snapshots[-1]["phase"] == "finishing" and snapshots[-1]["cost"] == 0.045


def test_range_session_masks_plies_outside_range() -> None:
    payload = {
        "lines": [
            {"ply": 1, "move": "1.e4", "grade": "best", "loss": 0},
            {"ply": 2, "move": "1...e5", "grade": "blunder", "loss": 300},
            {"ply": 3, "move": "2.Nf3", "grade": "mistake", "loss": 150},
        ],
        "moments": [
            {"ply": 2, "move": "1...e5", "reasons": ["blunder"]},
            {"ply": 3, "move": "2.Nf3", "reasons": ["mistake"]},
        ],
    }

    class FakeSession:
        async def call_tool(self, name, arguments):
            if name == "game_overview":
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text=json.dumps(payload))],
                    isError=False,
                )
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="ok")], isError=False)

    wrapped = mod._RangeSession(FakeSession(), (2, 2))

    async def check():
        res = await wrapped.call_tool("game_overview", {"game": "g", "plies": "1-3"})
        data = json.loads(res.content[0].text)
        assert data["lines"][0] == {"ply": 1, "move": "1.e4", "analysed": False}
        assert data["lines"][1]["ply"] == 2 and data["lines"][1]["grade"] == "blunder"
        assert data["lines"][2] == {"ply": 3, "move": "2.Nf3", "analysed": False}
        assert [m["ply"] for m in data["moments"]] == [2]
        other = await wrapped.call_tool("ply", {"game": "g", "ply": 2})
        assert other.content[0].text == "ok"

    anyio = pytest.importorskip("anyio")
    anyio.run(check)


def test_commentary_jobs_queue_failure_and_stop(tmp_path: Path) -> None:
    def failing_runner(*args, **kwargs):
        raise RuntimeError("boom")

    config = mod.CommentaryConfig(enabled=True, model="claude-haiku-5-5", cost_limit=0.5)
    cjobs = mod.CommentaryJobs(tmp_path, "sf", config, runner=failing_runner, queue_limit=2)
    s1, active1 = cjobs.start("a" * 64, "1. e4 *", (1, 1))
    s2, active2 = cjobs.start("b" * 64, "1. d4 *", (1, 1))
    assert not active1 and not active2
    assert s1["queue_position"] == 1 and s2["queue_position"] == 2

    # Failing runner marks first job failed without crashing worker
    assert cjobs.run_next() is True
    failed = cjobs.status("a" * 64)
    assert failed["state"] == "failed" and "boom" in failed["error"]

    # Cancelling a queued job removes it from queue
    cancelled = cjobs.cancel("b" * 64)
    assert cancelled["state"] == "cancelled"
    assert cjobs.run_next() is False

    # Worker start/stop cleanly terminates
    entered = threading.Event()
    blocker = threading.Event()

    def slow_runner(*args, cancel_event, **kwargs):
        entered.set()
        cancel_event.wait(timeout=5)
        blocker.set()
        return {"reason": "cancelled", "totals": {"cost": 0.0}, "accepted": 0}

    cjobs.runner = slow_runner
    cjobs.start("c" * 64, "1. c4 *", (1, 1))
    cjobs.start_worker()
    assert entered.wait(timeout=5)
    assert cjobs.stop(timeout=5) is True
    assert blocker.is_set()
    assert cjobs.status("c" * 64)["state"] == "cancelled"


def test_running_helper_handles_invalid_and_live_pids() -> None:
    assert running(0) is False
    assert running(-10) is False
    assert running(os.getpid()) is True


def test_rx_request_writes_utf8_korean_regardless_of_console_codepage() -> None:
    code = (
        "from tools.rx.request import _write_json; "
        "_write_json({'status': 200, 'text': '한국어 해설 — 1.e4 최선'})"
    )
    env = dict(os.environ) | {"PYTHONUTF8": "0", "PYTHONIOENCODING": "cp949"}
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(mod.REPO),
        env=env,
        capture_output=True,
        check=True,
    )
    decoded = json.loads(proc.stdout.decode("utf-8"))
    assert decoded["text"] == "한국어 해설 — 1.e4 최선"


def test_serve_cli_validates_cost_limit_and_missing_env_file(tmp_path: Path, capsys) -> None:
    with pytest.raises(SystemExit):
        serve_main.main(["--cost-limit", "0"])
    missing = tmp_path / "missing.env"
    code = serve_main.main(["--env-file", str(missing)])
    assert code == 2
    assert "cannot read env file" in capsys.readouterr().err


def test_serve_imports_without_agent_dependencies() -> None:
    code = (
        "import sys; "
        "sys.modules['anyio'] = None; "
        "sys.modules['mcp'] = None; "
        "sys.modules['anthropic'] = None; "
        "import tools.serve.__main__ as m; "
        "from tools.serve import commentary as c; "
        "cfg = c.resolve_config(enabled=True, env={'ANTHROPIC_API_KEY': 'k'}); "
        "assert not cfg.enabled and m is not None"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(mod.REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_progress_log_tier0_notes_and_timeout_failure(tmp_path: Path) -> None:
    totals = {"cost": 0.02}
    snapshots: list[dict] = []
    sink = mod.ProgressLog(totals, snapshots.append, tier2_total=1)
    sink.write({"type": "tier0", "ply": 11, "text": "유일한 수"})
    assert len(snapshots[-1]["tier0_notes"]) == 1
    assert snapshots[-1]["tier0_notes"][0] == {"ply": 11, "text": "유일한 수"}

    def timeout_runner(*args, on_update, **kwargs):
        on_update(
            {
                "phase": "tier1",
                "current_ply": 5,
                "tier2_done": 1,
                "tier2_total": 1,
                "tier1_done": 0,
                "tier1_total": 1,
                "accepted": 1,
                "cost": 0.02,
                "tier0_notes": [{"ply": 11, "text": "유일한 수", "source": "code"}],
            }
        )
        return {
            "reason": "timeout",
            "totals": {"cost": 0.02},
            "accepted": 1,
            "tier0_notes": [{"ply": 11, "text": "유일한 수", "source": "code"}],
            "error": "AI 해설 생성 제한 시간(1800초)을 초과했습니다.",
        }

    config = mod.CommentaryConfig(enabled=True, model="claude-haiku-5-5")
    cjobs = mod.CommentaryJobs(tmp_path, "sf", config, runner=timeout_runner, queue_limit=1)
    cjobs.start("d" * 64, "1. d4 *", (1, 12))
    assert cjobs.run_next() is True
    st = cjobs.status("d" * 64)
    assert st["state"] == "failed"
    assert "제한 시간" in st["error"]
    assert st["tier0"] == 1
    assert st["tier0_notes"] == [{"ply": 11, "text": "유일한 수", "source": "code"}]


def test_numbered_sans_preserves_fen_start_move_numbers() -> None:
    from tools.rx.harness import numbered_sans

    pgn = '[FEN "4k3/8/8/8/8/8/8/4K3 b - - 5 19"]\n\n19...Kd7 20.Kd2 *'
    assert numbered_sans(pgn) == ["19...Kd7", "20.Kd2"]


def test_model_cancel_aborts_retries_and_kills_child(monkeypatch) -> None:
    import time

    from tools.rx import model

    cancel_retry = threading.Event()
    calls = 0

    def flaky():
        nonlocal calls
        calls += 1
        raise model.ModelTransient("transient")

    timer = threading.Timer(0.1, cancel_retry.set)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(model.ModelCancelled):
            model.with_retries(flaky, cancel_retry)
    finally:
        timer.cancel()
    assert calls == 1
    assert time.monotonic() - started < 1.5

    real_popen = subprocess.Popen

    def slow_popen(*args, **kwargs):
        return real_popen(
            [sys.executable, "-c", "import sys, time; sys.stdin.read(); time.sleep(30)"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    monkeypatch.setattr(model.subprocess, "Popen", slow_popen)
    cancel_child = threading.Event()
    kill_timer = threading.Timer(0.15, cancel_child.set)
    kill_timer.start()
    started_child = time.monotonic()
    try:
        with pytest.raises(model.ModelCancelled):
            model.run_request_child(b"{}", timeout=10, cancel_event=cancel_child)
    finally:
        kill_timer.cancel()
    assert time.monotonic() - started_child < 2.0


def test_resolve_config_rejects_unpriced_claude_model(monkeypatch) -> None:
    monkeypatch.setattr(mod, "_has_package", lambda name: True)
    unpriced = mod.resolve_config(
        model="claude-unpriced-99", env={"ANTHROPIC_API_KEY": "ak"}
    )
    assert not unpriced.enabled
    assert "비용 추적" in unpriced.reason


def test_resolve_stockfish_path_resolves_relative_paths(tmp_path: Path, monkeypatch) -> None:
    rel = Path("bin") / "stockfish.exe"
    full = tmp_path / rel
    full.parent.mkdir(parents=True)
    full.write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert mod.resolve_stockfish_path(f".{os.sep}{rel}") == str(full.resolve())


def test_run_commentary_deadline_sets_abort_and_returns_timeout(
    tmp_path: Path, monkeypatch
) -> None:
    import contextlib

    anyio = pytest.importorskip("anyio")
    mcp = pytest.importorskip("mcp")
    import mcp.client.stdio as mcp_stdio

    from tools.rx import harness
    from tools.rx import model as rx_model

    captured_cancel_events: list[threading.Event] = []
    teardown_abort_states: list[bool] = []
    seen_args: list[list[str]] = []

    def fake_make_model(name, *, cache=True, session_id="", judge=False, cancel_event=None):
        if cancel_event is not None:
            captured_cancel_events.append(cancel_event)
        return SimpleNamespace(model=name, cancel_event=cancel_event)

    @contextlib.asynccontextmanager
    async def fake_stdio_client(params, errlog=None):
        seen_args.append(list(params.args))
        try:
            yield ("r", "w")
        finally:
            teardown_abort_states.extend(ev.is_set() for ev in captured_cancel_events)

    class FakeSession:
        def __init__(self, read, write):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def initialize(self):
            return None

        async def list_tools(self):
            return SimpleNamespace(tools=[])

        async def call_tool(self, name, arguments):
            if name == "open_game":
                return SimpleNamespace(
                    content=[
                        SimpleNamespace(
                            type="text", text=json.dumps({"game": "g-1", "moves": ["e7e6"]})
                        )
                    ],
                    isError=False,
                )
            if name == "game_overview":
                return SimpleNamespace(
                    content=[
                        SimpleNamespace(
                            type="text",
                            text=json.dumps(
                                {
                                    "total": 1,
                                    "lines": [{"ply": 1, "move": "1...Kd7", "grade": "blunder", "loss": 300}],
                                    "moments": [{"ply": 1, "move": "1...Kd7", "reasons": ["blunder"]}],
                                }
                            ),
                        )
                    ],
                    isError=False,
                )
            raise AssertionError(name)

    async def slow_harness(*args, **kwargs):
        await anyio.sleep(5)
        return "done"

    monkeypatch.setattr(mcp_stdio, "stdio_client", fake_stdio_client)
    monkeypatch.setattr(mcp, "ClientSession", FakeSession)
    monkeypatch.setattr(rx_model, "make_model", fake_make_model)
    monkeypatch.setattr(harness, "harness_loop_v9", slow_harness)

    user_cancel = threading.Event()
    expected_env = {"engine": ["sf"], "profile": ["p"], "build": "b"}
    pgn = '[SetUp "1"]\n[FEN "4k3/8/8/8/4P3/8/8/4K3 b - e3 0 1"]\n\n1... Kd7 *'
    config = mod.CommentaryConfig(enabled=True, model="claude-haiku-5-5", cost_limit=0.5)
    result = anyio.run(
        lambda: mod.run_commentary(
            pgn,
            tmp_path,
            "stockfish",
            config,
            cancel_event=user_cancel,
            run_seconds=0.1,
            expected_env=expected_env,
        )
    )
    assert result["reason"] == "timeout"
    assert "제한 시간" in result["error"]
    assert not user_cancel.is_set()
    assert len(captured_cancel_events) == 2
    assert all(ev.is_set() for ev in captured_cancel_events)
    assert len(teardown_abort_states) == 2 and all(teardown_abort_states)
    assert "--root-fen" in seen_args[0]
    assert "--expect-env" in seen_args[0]


def test_serve_tests_collect_without_anyio() -> None:
    tests_dir = mod.REPO / "tests"
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(tests_dir / 'server')!r}); "
        f"sys.path.insert(0, {str(tests_dir / 'facts' / 'search')!r}); "
        f"sys.path.insert(0, {str(mod.REPO)!r}); "
        "sys.modules['anyio'] = None; "
        "import test_serve_commentary"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(mod.REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_session_root_overrides_and_expect_env_and_long_cache_paths(
    tmp_path: Path, monkeypatch
) -> None:
    from helpers import slot
    from synthetic import engine

    from calliope.agent import Limits, Session
    from calliope.facts import EngineProfile, RootSpec
    from calliope.facts.search import StockfishEngine
    from calliope.server import PlyCache, game_key, parse_game
    from calliope.server.jobs import Jobs, environment
    from tools.mcp import __main__ as mcp_main

    pgn = '[SetUp "1"]\n[FEN "4k3/8/8/8/4P3/8/8/4K3 b - e3 0 1"]\n\n1... Kd7 2. Kd2 *'
    parsed = parse_game(pgn)
    key = game_key(parsed.game)

    # HTTP job analysis caches under parsed.root (which keeps untakeable EP square 'e3').
    jobs_root = tmp_path / "env_game"
    table = Jobs(jobs_root, slot()[0], queue_limit=2)
    try:
        table.recover()
        job, _ = table.submit(pgn, "1-2")
        assert table.run_next() is True

        plain = Session(jobs_root, engine, Limits())
        try:
            assert plain.environment() == table.environment_of(job["id"])
            without_override = plain.open_game(pgn=pgn)
            assert not all(m["cached"] for m in without_override["moves"])
        finally:
            plain.close()

        aligned = Session(
            jobs_root, engine, Limits(), root_overrides={key: RootSpec(fen=parsed.root.fen)}
        )
        try:
            with_override = aligned.open_game(pgn=pgn)
            assert all(m["cached"] for m in with_override["moves"])
        finally:
            aligned.close()

        # Mismatched --expect-env exits 2 cleanly before serving.
        monkeypatch.setenv("CALLIOPE_STOCKFISH_PATH", "synthetic")
        monkeypatch.setattr(StockfishEngine, "start", staticmethod(lambda _p: engine()))
        mismatch = json.dumps({"engine": ["other"], "profile": [], "build": "x"})
        assert mcp_main.main(["--data", str(jobs_root), "--expect-env", mismatch]) == 2
        assert environment(engine(), EngineProfile()) == table.environment
    finally:
        table.slot.close()

    # PlyCache.paths returns Windows long-path-safe paths for direct Session callers (>260 chars).
    deep = tmp_path
    for _ in range(5):
        deep = deep / ("c" * 45)
    sess = Session(deep, engine, Limits(), profile=EngineProfile())
    try:
        p_key = sess._key(parsed, 1)[0]
        tree_p, graph_p = PlyCache(deep / "plies").paths(p_key)
        assert len(str(tree_p)) > 260
        tree_p.parent.mkdir(parents=True, exist_ok=True)
        tree_p.write_bytes(b"t")
        graph_p.write_bytes(b"g")
        assert sess._cached(parsed, 1) is True
    finally:
        sess.close()
