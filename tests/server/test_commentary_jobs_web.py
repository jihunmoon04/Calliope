"""Tests for the HTTP server's local AI commentary job routes."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from helpers import RATED, slot
from test_jobs import DOC, accept, stub
from test_web import call

from calliope.server.jobs import Jobs
from calliope.server.web import serve
from tools.serve.commentary import CommentaryConfig, CommentaryJobs


def _start_server(tmp_path: Path, commentary_jobs=None, *, analyse=stub, allowed_hosts=None):
    table = Jobs(tmp_path, slot()[0], analyse=analyse, queue_limit=3, check=accept)
    table.recover()
    server = serve(
        table,
        Path(__file__).resolve().parents[2] / "viewer",
        port=0,
        commentary_jobs=commentary_jobs,
        allowed_hosts=allowed_hosts,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return table, server, server.server_address[1]


def test_commentary_job_routes_without_runner(tmp_path: Path) -> None:
    table, server, port = _start_server(tmp_path, commentary_jobs=None)
    try:
        status, _ = table.submit(RATED, "1-4")
        jid = status["id"]

        code, _, body = call(port, "GET", f"/api/games/{'0' * 64}/commentary/job")
        assert code == 404

        code, _, body = call(port, "GET", f"/api/games/{jid}/commentary/job")
        assert code == 200
        job_doc = json.loads(body)
        assert job_doc["state"] == "idle" and job_doc["available"] is False

        # Analysis is still queued -> 409 Conflict
        code, _, _ = call(
            port, "POST", f"/api/games/{jid}/commentary", b"{}",
            {"Content-Type": "application/json"},
        )
        assert code == 409

        table.run_next()
        # Analysis is done, but commentary_jobs=None -> 503
        code, _, _ = call(
            port, "POST", f"/api/games/{jid}/commentary", b"{}",
            {"Content-Type": "application/json"},
        )
        assert code == 503

        code, _, _ = call(
            port, "POST", f"/api/games/{jid}/commentary/cancel", b"{}",
            {"Content-Type": "application/json"},
        )
        assert code == 503
    finally:
        server.shutdown()
        server.server_close()


def test_commentary_job_routes_lifecycle_and_validation(tmp_path: Path) -> None:
    entered = threading.Event()
    release = threading.Event()

    def fake_runner(pgn, data_dir, stockfish, config, *, ply_range, cancel_event, on_update):
        entered.set()
        on_update(
            {
                "phase": "tier2",
                "current_ply": 2,
                "tier2_done": 1,
                "tier2_total": 2,
                "tier1_done": 0,
                "tier1_total": 0,
                "accepted": 1,
                "cost": 0.02,
            }
        )
        release.wait(timeout=5)
        if cancel_event.is_set():
            return {"reason": "cancelled", "totals": {"cost": 0.02}, "accepted": 1}
        return {"reason": "done", "totals": {"cost": 0.05}, "accepted": 2}

    config = CommentaryConfig(enabled=True, model="claude-haiku-5-5", cost_limit=1.0)
    cjobs = CommentaryJobs(tmp_path, "stockfish", config, runner=fake_runner, queue_limit=1)
    cjobs.start_worker()
    table, server, port = _start_server(tmp_path, commentary_jobs=cjobs)
    try:
        assert DOC["schema"] == "calliope_result_v1"
        job, _ = table.submit(RATED, "1-4")
        jid = job["id"]
        table.run_next()

        # Input validation
        assert call(port, "POST", f"/api/games/{jid}/commentary", b"{}",
                    {"Content-Type": "text/plain"})[0] == 415
        assert call(port, "POST", f"/api/games/{jid}/commentary", b"[]",
                    {"Content-Type": "application/json"})[0] == 400
        assert call(port, "POST", f"/api/games/{jid}/commentary", b"{bad",
                    {"Content-Type": "application/json"})[0] == 400
        assert call(port, "POST", f"/api/games/{'0' * 64}/commentary", b"{}",
                    {"Content-Type": "application/json"})[0] == 404

        # Start via POST with empty JSON body
        code, _, body = call(
            port, "POST", f"/api/games/{jid}/commentary", b"",
            {"Content-Type": "application/json"},
        )
        assert code == 202
        assert json.loads(body)["state"] in ("queued", "running")
        assert entered.wait(timeout=5)

        # Idempotent second POST returns 200 while active
        code, _, body = call(
            port, "POST", f"/api/games/{jid}/commentary", b"{}",
            {"Content-Type": "application/json"},
        )
        assert code == 200
        assert json.loads(body)["state"] == "running"

        # Status reflects live progress
        code, _, body = call(port, "GET", f"/api/games/{jid}/commentary/job")
        assert code == 200
        live = json.loads(body)
        assert live["phase"] == "tier2" and live["accepted"] == 1 and live["cost"] == 0.02

        # Finish normally
        release.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            _, _, raw = call(port, "GET", f"/api/games/{jid}/commentary/job")
            done = json.loads(raw)
            if done["state"] == "done":
                break
            time.sleep(0.02)
        assert done["state"] == "done" and done["accepted"] == 2 and done["cost"] == 0.05

        # Cancel flow on another run
        entered.clear()
        release.clear()
        code, _, _ = call(
            port, "POST", f"/api/games/{jid}/commentary", b"{}",
            {"Content-Type": "application/json"},
        )
        assert code == 202
        assert entered.wait(timeout=5)
        code, _, body = call(
            port, "POST", f"/api/games/{jid}/commentary/cancel", b"{}",
            {"Content-Type": "application/json"},
        )
        assert code == 200
        assert json.loads(body)["cancelling"] is True
        release.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            _, _, raw = call(port, "GET", f"/api/games/{jid}/commentary/job")
            cancelled = json.loads(raw)
            if cancelled["state"] == "cancelled":
                break
            time.sleep(0.02)
        assert cancelled["state"] == "cancelled"
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        cjobs.stop(timeout=5)


def test_commentary_route_disabled_returns_503(tmp_path: Path) -> None:
    config = CommentaryConfig(enabled=False, model=None, reason="API 키가 없습니다.")
    cjobs = CommentaryJobs(tmp_path, "stockfish", config)
    table, server, port = _start_server(tmp_path, commentary_jobs=cjobs)
    try:
        job, _ = table.submit(RATED, "1-4")
        jid = job["id"]
        table.run_next()
        code, _, body = call(port, "GET", f"/api/games/{jid}/commentary/job")
        assert code == 200
        assert json.loads(body)["available"] is False
        code, _, body = call(
            port, "POST", f"/api/games/{jid}/commentary", b"{}",
            {"Content-Type": "application/json"},
        )
        assert code == 503
        assert "API 키" in json.loads(body)["error"]
    finally:
        server.shutdown()
        server.server_close()


def test_commentary_queue_full_returns_503(tmp_path: Path) -> None:
    config = CommentaryConfig(enabled=True, model="claude-haiku-5-5")
    cjobs = CommentaryJobs(tmp_path, "stockfish", config, queue_limit=1)
    table, server, port = _start_server(tmp_path, commentary_jobs=cjobs)
    try:
        j1, _ = table.submit(RATED, "1-4")
        table.run_next()
        j2, _ = table.submit(RATED.replace("Alice", "Carol"), "1-4")
        table.run_next()
        assert (
            call(
                port,
                "POST",
                f"/api/games/{j1['id']}/commentary",
                b"{}",
                {"Content-Type": "application/json"},
            )[0]
            == 202
        )
        code, _, _ = call(
            port,
            "POST",
            f"/api/games/{j2['id']}/commentary",
            b"{}",
            {"Content-Type": "application/json"},
        )
        assert code == 503
    finally:
        server.shutdown()
        server.server_close()


def test_commentary_post_rejects_stale_environment_with_409(tmp_path: Path) -> None:
    config = CommentaryConfig(enabled=True, model="claude-haiku-5-5")
    cjobs = CommentaryJobs(tmp_path, "stockfish", config, queue_limit=1)
    table, server, port = _start_server(tmp_path, commentary_jobs=cjobs)
    try:
        j, _ = table.submit(RATED, "1-4")
        table.run_next()
        with table.lock:
            table.jobs[j["id"]].environment = ("stale-engine",)
        code, _, body = call(
            port,
            "POST",
            f"/api/games/{j['id']}/commentary",
            b"{}",
            {"Content-Type": "application/json"},
        )
        assert code == 409
        assert "다시 분석" in json.loads(body)["error"]
    finally:
        server.shutdown()
        server.server_close()


def test_commentary_post_rejects_untrusted_host_and_origin_with_403(tmp_path: Path) -> None:
    config = CommentaryConfig(enabled=True, model="claude-haiku-5-5")
    cjobs = CommentaryJobs(tmp_path, "stockfish", config, queue_limit=1)
    table, server, port = _start_server(
        tmp_path, commentary_jobs=cjobs, allowed_hosts=["proxy.example.org"]
    )
    try:
        j, _ = table.submit(RATED, "1-4")
        table.run_next()
        jid = j["id"]

        # Untrusted Host on /commentary and /commentary/cancel -> 403
        code, _, _ = call(
            port,
            "POST",
            f"/api/games/{jid}/commentary",
            b"{}",
            {"Content-Type": "application/json", "Host": "evil.example:8765"},
        )
        assert code == 403
        code, _, _ = call(
            port,
            "POST",
            f"/api/games/{jid}/commentary/cancel",
            b"{}",
            {"Content-Type": "application/json", "Host": "evil.example:8765"},
        )
        assert code == 403

        # Trusted Host + untrusted Origin -> 403
        code, _, _ = call(
            port,
            "POST",
            f"/api/games/{jid}/commentary",
            b"{}",
            {
                "Content-Type": "application/json",
                "Host": f"127.0.0.1:{port}",
                "Origin": "https://evil.example",
            },
        )
        assert code == 403

        # Explicitly allowed reverse-proxy Host + Origin -> 202
        code, _, _ = call(
            port,
            "POST",
            f"/api/games/{jid}/commentary",
            b"{}",
            {
                "Content-Type": "application/json",
                "Host": "proxy.example.org",
                "Origin": "https://proxy.example.org",
            },
        )
        assert code == 202
    finally:
        server.shutdown()
        server.server_close()


def test_commentary_post_rejects_malformed_origin_and_forwards_env(tmp_path: Path) -> None:
    seen_env: list[dict | None] = []

    def fake_runner(pgn, data_dir, stockfish, config, *, expected_env=None, **kwargs):
        seen_env.append(expected_env)
        return {"reason": "done", "totals": {"cost": 0.0}, "accepted": 0}

    config = CommentaryConfig(enabled=True, model="claude-haiku-5-5")
    cjobs = CommentaryJobs(tmp_path, "stockfish", config, runner=fake_runner, queue_limit=1)
    table, server, port = _start_server(tmp_path, commentary_jobs=cjobs)
    try:
        j, _ = table.submit(RATED, "1-4")
        table.run_next()
        jid = j["id"]

        # Malformed Origin returns 403 JSON instead of dropping connection.
        for suffix in ("commentary", "commentary/cancel"):
            code, _, body = call(
                port,
                "POST",
                f"/api/games/{jid}/{suffix}",
                b"{}",
                {
                    "Content-Type": "application/json",
                    "Host": f"127.0.0.1:{port}",
                    "Origin": "http://[::1",
                },
            )
            assert code == 403
            assert "error" in json.loads(body)

        code, _, _ = call(
            port,
            "POST",
            f"/api/games/{jid}/commentary",
            b"{}",
            {"Content-Type": "application/json"},
        )
        assert code == 202
        assert cjobs.run_next() is True
        assert seen_env == [table.environment_of(jid)]
    finally:
        server.shutdown()
        server.server_close()


def test_commentary_cancel_requires_matching_run_id_when_provided(tmp_path: Path) -> None:
    entered = threading.Event()
    release = threading.Event()

    def slow_runner(pgn, data_dir, stockfish, config, *, cancel_event, **kwargs):
        entered.set()
        cancel_event.wait(timeout=5)
        release.wait(timeout=5)
        return {"reason": "cancelled" if cancel_event.is_set() else "done", "totals": {"cost": 0.0}, "accepted": 0}

    config = CommentaryConfig(enabled=True, model="claude-haiku-5-5")
    cjobs = CommentaryJobs(tmp_path, "stockfish", config, runner=slow_runner, queue_limit=1)
    cjobs.start_worker()
    table, server, port = _start_server(tmp_path, commentary_jobs=cjobs)
    try:
        j, _ = table.submit(RATED, "1-4")
        table.run_next()
        jid = j["id"]

        code, _, body = call(
            port, "POST", f"/api/games/{jid}/commentary", b"{}", {"Content-Type": "application/json"}
        )
        assert code == 202
        run_b_id = json.loads(body)["run_id"]
        assert entered.wait(timeout=5)

        # Invalid non-string run_id -> 400
        code, _, _ = call(
            port,
            "POST",
            f"/api/games/{jid}/commentary/cancel",
            json.dumps({"run_id": 123}).encode(),
            {"Content-Type": "application/json"},
        )
        assert code == 400

        # Stale run_id from a previous run does NOT cancel run B
        code, _, body = call(
            port,
            "POST",
            f"/api/games/{jid}/commentary/cancel",
            json.dumps({"run_id": "stale-run-id"}).encode(),
            {"Content-Type": "application/json"},
        )
        assert code == 200
        st = json.loads(body)
        assert st["run_id"] == run_b_id and st["cancelling"] is False and st["state"] == "running"

        # Matching run_id DOES cancel run B
        code, _, body = call(
            port,
            "POST",
            f"/api/games/{jid}/commentary/cancel",
            json.dumps({"run_id": run_b_id}).encode(),
            {"Content-Type": "application/json"},
        )
        assert code == 200
        assert json.loads(body)["cancelling"] is True
        release.set()
    finally:
        release.set()
        cjobs.stop(timeout=5)
        server.shutdown()
        server.server_close()
