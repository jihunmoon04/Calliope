"""Viewer tests for the local web app AI commentary job client and status text."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def test_commentary_job_client_and_status_text() -> None:
    run = subprocess.run(
        [NODE, str(ROOT / "tests/viewer/check_commentary_job.js"), str(ROOT / "viewer/index.html")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    assert out["urls"] == [
        f"GET api/games/{'b' * 64}/commentary/job",
        f"POST api/games/{'b' * 64}/commentary",
        f"POST api/games/{'b' * 64}/commentary/cancel",
    ]
    assert out["texts"] == [
        "",
        "",
        "AI 해설 대기 중 (곧 시작합니다)",
        "AI 해설 대기 중 (앞에 2개)",
        "AI 해설 준비 중",
        "AI 해설 생성 중 · 핵심 장면 1/3 (14번째 수) · 저장 1수 · $0.04",
        "AI 해설 생성 중 · 주요 수 2/5 (22번째 수) · 저장 3수 · $0.09",
        "AI 해설 마무리 중 · 저장 5수 · $0.12",
        "AI 해설 중단 중… · 저장 2수 · $0.05",
        "AI 해설 완료 · 저장 6수 · $0.14",
        "AI 해설 완료 · 저장 4수 · $1.00 · 비용 기준 도달",
        "AI 해설 대상 수가 없습니다.",
        "AI 해설이 중단되었습니다. · 저장 2수 · $0.06",
        "AI 해설 실패: API error",
    ]
    dom = out["dom"]
    assert dom["delays"] == [2000, 4000, 6000, 2000]
    assert "다시 확인 중" in dom["retryWrapHtml"]
    assert "다시 확인 중" not in dom["clearedErrorWrapHtml"]
    assert "주요 수 1/2" in dom["clearedErrorWrapHtml"]
    assert dom["retryBodyWrites"] <= 2
    assert dom["sentinelDuringPoll"] is True
    assert dom["sentinelAfterDone"] is True
    assert dom["bodyWritesAtDone"] == dom["retryBodyWrites"] + 1
    assert "AI 해설 완료" in dom["finalWrapHtml"]
    assert set(dom["refreshCalls"]) == {
        f"GET api/games/{'b' * 64}/commentary",
        f"GET api/games/{'b' * 64}/commentary/job",
    }
    rt = out["raceAndTier0"]
    assert "ai-tier0" in rt["tier0OnlyHtml"]
    assert "자동 진행 메모 테스트" in rt["tier0OnlyHtml"]
    assert "이 수의 AI 해설이 없습니다." not in rt["tier0OnlyHtml"]
    assert "최신 해설 본문" in rt["afterFastHtml"]
    assert "최신 해설 본문" in rt["afterStaleHtml"]
    assert "자동 진행 메모 테스트" in rt["afterStaleHtml"]
    assert out["cancelRace"]["stateAfterLateCancel"] == "cancelled"
    assert "중단되었습니다" in out["cancelRace"]["wrapHtml"]
    assert "중단 중" not in out["cancelRace"]["wrapHtml"]
