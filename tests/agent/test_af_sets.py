"""AF (agent-af-design.md): Test 2's own lifecycle (§7.4: `opened[set]`, `freeze_v2`, a report
holding one test set) and the server worktree (§6: made with the checkout's line endings, its
reasoning data files checked)."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest
from agent_helpers import GAME

from tools.rx import freeze as rx_freeze
from tools.rx import manifest as rx_manifest
from tools.rx import report as rx_report
from tools.rx import run as rx_run
from tools.rx import servers as rx_servers


def freeze_v2(for_set: str = "test2") -> dict:
    return {"version": "freeze_v2", "for": for_set, "judge": "judge_v2",
            "model": rx_run.DEFAULT_MODEL, "commit": "a" * 40,
            "bounds": {"turns": 90, "tool_calls": 150, "tokens": 4_000_000},
            "variants": {
                "A@v9": {"tools": "agent_tools_v9"},
                "H@v9": {"tools": "agent_tools_v9", "harness_revision": 8, "harness": "harness_v4",
                         "harness_judge": "harness_judge_v3",
                         "harness_frames": "harness_frames_v1"}}}  # fmt: skip


# -- freeze_v2 and opened[set] (§7.4) ---------------------------------------------------------


def test_a_freeze_v2_names_its_test_set_and_judge() -> None:
    assert rx_freeze.problems(freeze_v2()) == []
    assert any("for" in w for w in rx_freeze.problems(freeze_v2() | {"for": "validation"}))
    assert any("judge" in w for w in rx_freeze.problems(freeze_v2() | {"judge": "judge_v9"}))
    bad = freeze_v2()
    bad["variants"]["H@v9"]["harness_frames"] = "harness_frames_v0"
    assert any("harness_frames" in w for w in rx_freeze.problems(bad))


def test_test_ones_earlier_record_reads_as_opened_test() -> None:
    record = {"freeze": "f", "freeze_sha256": "d"}
    assert rx_manifest.opened({"test_opened": record}, "test") == record
    assert rx_manifest.opened({"test_opened": record}, "test2") is None
    assert rx_manifest.opened({"opened": {"test2": record}}, "test2") == record


def _setup(tmp_path, monkeypatch, manifest_extra=None):
    pgns = tmp_path / "pgns"
    pgns.mkdir()
    (pgns / "t2.pgn").write_text(GAME, encoding="utf-8")
    entries = [{"name": "t2", "number": "t2", "owner": "white",
                "uci_sha256": rx_manifest.uci_digest(GAME)}]  # fmt: skip
    manifest = tmp_path / "manifest.json"
    doc = {"sets": {"test": [], "test2": entries}} | (manifest_extra or {})
    manifest.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(rx_manifest, "MANIFEST", manifest)
    monkeypatch.setattr(rx_manifest, "RX_DATA", tmp_path)
    monkeypatch.setattr(rx_freeze, "servers_problems", lambda doc: [])
    return pgns, manifest


def test_test2_opens_with_its_own_record_and_test_ones_stays(tmp_path, monkeypatch) -> None:
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps(freeze_v2("test")), encoding="utf-8")
    pgns, _ = _setup(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="is for test, not test2"):
        rx_manifest.open_test(pgns, "e", freeze, out=io.StringIO(), set_name="test2")
    with pytest.raises(RuntimeError, match="not a test set"):
        rx_manifest.open_test(pgns, "e", freeze, out=io.StringIO(), set_name="validation")


def test_a_record_that_opened_test_one_cannot_open_test2(tmp_path, monkeypatch) -> None:
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps(freeze_v2()), encoding="utf-8")
    _, digest = rx_freeze.read(freeze)
    pgns, _ = _setup(tmp_path, monkeypatch,
                     {"test_opened": {"freeze": str(freeze), "freeze_sha256": digest}})  # fmt: skip
    with pytest.raises(RuntimeError, match="opened test: one record opens one set"):
        rx_manifest.open_test(pgns, "e", freeze, out=io.StringIO(), set_name="test2")


def test_an_open_test2_refuses_to_open_again(tmp_path, monkeypatch) -> None:
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps(freeze_v2()), encoding="utf-8")
    pgns, _ = _setup(tmp_path, monkeypatch, {"opened": {"test2": {"freeze": "x",
                                                                  "freeze_sha256": "y"}}})  # fmt: skip
    with pytest.raises(RuntimeError, match="open already"):
        rx_manifest.open_test(pgns, "e", freeze, out=io.StringIO(), set_name="test2")


def test_a_variants_unready_worktree_stops_the_opening(tmp_path, monkeypatch) -> None:
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps(freeze_v2()), encoding="utf-8")
    pgns, _ = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(rx_freeze, "servers_problems", lambda doc: ["A@v7: no worktree"])
    with pytest.raises(RuntimeError, match="server is not ready"):
        rx_manifest.open_test(pgns, "e", freeze, out=io.StringIO(), set_name="test2")


def test_a_test2_run_is_checked_against_its_own_freeze(tmp_path) -> None:
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps(freeze_v2()), encoding="utf-8")
    _, digest = rx_freeze.read(freeze)
    manifest = {"test_opened": {"freeze": "other", "freeze_sha256": "z"},
                "opened": {"test2": {"freeze": str(freeze), "freeze_sha256": digest}}}  # fmt: skip
    spec = rx_run.RunSpec(arm="H", set_name="test2", game="g", pgn="", moments=[1], base=None,
                          records=None, work=None, tools="v9")  # fmt: skip
    spec.bounds.turns, spec.bounds.tool_calls, spec.bounds.tokens = 90, 150, 4_000_000
    assert rx_freeze.run_problems(rx_manifest.opened(manifest, "test2"), spec) == []
    assert rx_freeze.run_problems(rx_manifest.opened({}, "test2"), spec)


def test_a_report_holding_test_and_test2_is_refused(monkeypatch, tmp_path) -> None:
    rows = [{"set": "test", "game": "g", "arm": "A", "result": {"run": "r1"}},
            {"set": "test2", "game": "h", "arm": "A", "result": {"run": "r2"}}]  # fmt: skip
    (tmp_path / "batches").mkdir()
    (tmp_path / "batches" / "b.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    (tmp_path / "keys" / "j").mkdir(parents=True)
    (tmp_path / "keys" / "j" / "bundle_key.json").write_text(json.dumps({"runs": ["r1", "r2"],
                                                                         "key": {}}))  # fmt: skip
    monkeypatch.setattr(rx_report, "RX_DATA", tmp_path)
    monkeypatch.setattr(rx_report, "KEYS", tmp_path / "keys")
    with pytest.raises(ValueError, match="Test alone"):
        rx_report.build("b", "j", tmp_path, [("A", "A")])


def test_test2_is_never_pooled() -> None:
    assert "test2" in rx_report.SETS and "test2" not in rx_report.POOLED_SETS
    assert rx_report.TEST_SETS == rx_manifest.TEST_SETS


# -- the server worktree (§6) -----------------------------------------------------------------


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    data = repo / rx_servers.DATA_ROOT / "curves"
    data.mkdir(parents=True)
    (data / "c.json").write_bytes(b'{"a": 1}\n{"b": 2}\n')
    (repo / rx_servers.DATA_ROOT / "x.py").write_text("x = 1\n")
    _git("init", "-q", cwd=repo)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "add", ".", cwd=repo)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "c", cwd=repo)
    _git("tag", "agent-tools-v7", cwd=repo)
    return repo


def test_the_check_finds_a_data_file_whose_line_endings_differ(tmp_path) -> None:
    repo = _repo(tmp_path)
    worktree = tmp_path / "wt"
    _git("worktree", "add", "-q", "--detach", str(worktree), "agent-tools-v7", cwd=repo)
    assert rx_servers.check(worktree, repo) == []
    path = worktree / rx_servers.DATA_ROOT / "curves" / "c.json"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    [problem] = rx_servers.check(worktree, repo)
    assert "curves/c.json" in problem and "line endings" in problem
    assert rx_servers.check(tmp_path / "none", repo)[0].startswith("no worktree")


def test_server_worktree_makes_it_with_the_checkouts_autocrlf_and_keeps_an_existing_one(
    tmp_path, monkeypatch
) -> None:
    repo = _repo(tmp_path)
    _git("config", "core.autocrlf", "false", cwd=repo)
    root = tmp_path / "servers" / "agent-tools-v7"
    monkeypatch.setattr(rx_servers, "server_root", lambda tools: root)
    out = rx_servers.make("v7", repo)
    assert out["made"] and out["problems"] == [] and root.is_dir()
    again = rx_servers.make("v7", repo)
    assert not again["made"] and again["commit"] == out["commit"]
    monkeypatch.setattr(rx_servers, "server_root", lambda tools: None)
    with pytest.raises(ValueError, match="this repository"):
        rx_servers.make("v9", repo)


def test_test2s_games_are_balanced_and_none_was_used_before() -> None:
    """AF implementation §6, A7: two as White, two as Black, none of an earlier set."""

    numbers = [n for n, _ in rx_manifest.TEST2]
    assert len(numbers) == 4 and sorted(s for _, s in rx_manifest.TEST2) == ["black"] * 2 + ["white"] * 2
    earlier = {n for n, _ in rx_manifest.VALIDATION} | {n for n, _ in rx_manifest.TEST}
    assert not earlier & set(numbers)
