"""Unit tests for the local web-app AI commentary runner and Windows compatibility helpers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import anyio
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
    blocker = threading.Event()

    def slow_runner(*args, cancel_event, **kwargs):
        cancel_event.wait(timeout=5)
        blocker.set()
        return {"reason": "cancelled", "totals": {"cost": 0.0}, "accepted": 0}

    cjobs.runner = slow_runner
    cjobs.start("c" * 64, "1. c4 *", (1, 1))
    cjobs.start_worker()
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
