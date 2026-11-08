"""LT (agent-lt-design.md §6.3–§6.4): variants by tool version (review F2) and the Test set in the
runner and the report (review F1); the sentence check's states in the report (re-review R3)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from tools.rx import batch as rx_batch
from tools.rx import freeze as rx_freeze
from tools.rx import manifest as rx_manifest
from tools.rx import report as rx_report
from tools.rx import run as rx_run


def freeze_record() -> dict:
    return {"version": "freeze_v1", "model": rx_run.DEFAULT_MODEL, "commit": "a" * 40,
            "bounds": {"turns": 90, "tool_calls": 150, "tokens": 4_000_000},
            "variants": {
                "A@v7": {"tools": "agent_tools_v7", "commit": "b" * 40},
                "H@v8": {"tools": "agent_tools_v8", "harness_revision": 6, "harness": "harness_v3",
                         "harness_judge": "harness_judge_v2",
                         "harness_sentences": "harness_sentences_v2"}}}  # fmt: skip


# -- variants (§6.3) ----------------------------------------------------------------------------


def test_a_variant_names_an_arm_and_its_tools() -> None:
    assert rx_batch.split_variant("A@v7") == ("A", "v7")
    assert rx_batch.split_variant("H") == ("H", None)
    for bad in ("A@v9", "Z@v7", "Z"):
        with pytest.raises(argparse.ArgumentTypeError):
            rx_batch.split_variant(bad)


def test_variant_jobs_carry_their_tools_to_the_run_command(monkeypatch, tmp_path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sets": {"test": [{"name": "t1"}]}}), encoding="utf-8")
    monkeypatch.setattr(rx_batch, "MANIFEST", manifest)
    jobs = rx_batch.jobs(1, ["A@v7", "A@v8", "H@v8"], ["test"])
    assert [(j["arm"], j.get("variant")) for j in jobs] == [
        ("A", "A@v7"), ("A", "A@v8"), ("H", "H@v8")]  # fmt: skip
    cmd = rx_batch.command(jobs[0], Path(".env"))
    assert cmd[cmd.index("--tools") + 1] == "v7" and cmd[cmd.index("--set") + 1] == "test"


def test_two_variants_of_one_arm_are_two_arms_in_the_report() -> None:
    assert rx_report.label({"arm": "A", "variant": "A@v7"}) == "A@v7"
    assert rx_report.label({"arm": "A", "variant": "A@v8"}) == "A@v8"
    assert rx_report.label({"arm": "D", "candidate": "L03"}) == "D:L03"  # earlier batches
    assert rx_report.label({"arm": "A"}) == "A"


def test_a_variants_server_root_and_its_start_line() -> None:
    assert rx_run.server_root(None) is None and rx_run.server_root("v8") is None
    assert rx_run.server_root("v7").name == "agent-tools-v7"
    with pytest.raises(ValueError, match="no tools"):
        rx_run.server_root("v9")
    spec = rx_run.RunSpec(arm="A", set_name="test", game="g", pgn="", moments=[1], base=None,
                          records=None, work=None, tools="v8")  # fmt: skip
    info = rx_run._server_info(spec)
    assert info["variant"] == "A@v8" and info["server"]["tools_expected"] == "agent_tools_v8"
    assert info["server"]["root"] == str(rx_run.REPO)
    plain = rx_run.RunSpec(arm="A", set_name="train", game="g", pgn="", moments=[1], base=None,
                           records=None, work=None)  # fmt: skip
    assert rx_run._server_info(plain) == {}  # every earlier run's start line unchanged


# -- the Test set (§6.4) ------------------------------------------------------------------------


def _value(decisive, wrong=0, sentences=10, score=4.0):
    return {"wrong": wrong, "sentences": sentences, "decisive": decisive, "score": score,
            "fetched": None}  # fmt: skip


def _cells(set_name, gain):
    cells = {}
    for g in ("g1", "g2", "g3", "g4"):
        for ply in (10, 20, 30):
            cells[(set_name, g, ply)] = {"H": [_value(min(1.0, 0.5 + gain))] * 3,
                                         "A": [_value(0.5)] * 3}  # fmt: skip
    return cells


def test_a_test_only_report_decides_from_its_test_entry() -> None:
    report = {"arms": {}, "paired": {}, "decisions": {}, "ledger": {}}
    cells = _cells("test", 0.5)
    rx_report.pair_up(report, cells, cells, {}, [("H", "A")])
    assert "H - A / test" in report["paired"] and "H - A / pooled" not in report["paired"]
    decision = report["decisions"]["H - A"]
    assert decision["read_from"] == "test" and decision["quality_gate_passed"] is True


def test_train_and_validation_still_pool_and_test_never_joins_them() -> None:
    report = {"arms": {}, "paired": {}, "decisions": {}, "ledger": {}}
    cells = _cells("train", 0.5) | _cells("validation", 0.5)
    rx_report.pair_up(report, cells, cells, {}, [("H", "A")])
    assert "H - A / pooled" in report["paired"]
    assert report["decisions"]["H - A"].get("read_from") is None


def test_a_report_holding_test_beside_another_set_is_refused(monkeypatch, tmp_path) -> None:
    rows = [{"set": "test", "game": "g", "arm": "A", "result": {"run": "r1"}},
            {"set": "train", "game": "h", "arm": "A", "result": {"run": "r2"}}]  # fmt: skip
    batches = tmp_path / "batches"
    batches.mkdir()
    (batches / "b.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    keys = tmp_path / "keys" / "j"
    keys.mkdir(parents=True)
    (keys / "bundle_key.json").write_text(json.dumps({"runs": ["r1", "r2"], "key": {}}),
                                          encoding="utf-8")  # fmt: skip
    monkeypatch.setattr(rx_report, "RX_DATA", tmp_path)
    monkeypatch.setattr(rx_report, "KEYS", tmp_path / "keys")
    with pytest.raises(ValueError, match="Test alone"):
        rx_report.build("b", "j", tmp_path, [("A", "A")])


def test_test_opens_only_with_a_freeze_record(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="no freeze record"):
        rx_manifest.open_test(tmp_path, "engine", tmp_path / "freeze.json")


# -- the sentence check's states (§5.5, re-review R3) -------------------------------------------


def test_m1b_per_sentence_check_state() -> None:
    values = [("passed", _value(1.0, wrong=1, sentences=10)),
              ("passed", _value(1.0, wrong=0, sentences=10)),
              ("exhausted", _value(0.0, wrong=3, sentences=10)),
              ("not_run", _value(None, wrong=0, sentences=0))]  # fmt: skip
    states = rx_report.by_state(values)
    assert states["passed"] == {"moment_runs": 2, "sentences": 20, "M1b_wrong_per_100": 5.0}
    assert states["exhausted"]["M1b_wrong_per_100"] == 30.0
    assert states["not_run"]["M1b_wrong_per_100"] == 0.0


def test_sentence_states_are_read_from_the_run(tmp_path) -> None:
    lines = [{"type": "start"},
             {"type": "harness", "stage": "sentence_state", "ply": 10, "state": "passed"},
             {"type": "harness", "stage": "sentence_state", "ply": 20, "state": "unreadable"}]  # fmt: skip
    (tmp_path / "agent.jsonl").write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    assert rx_report.sentence_states(tmp_path) == {10: "passed", 20: "unreadable"}


def test_open_test_chooses_the_moments_and_seals_the_base(tmp_path, monkeypatch) -> None:
    """LT review F1: Test's moments chosen as Validation's, its base sealed, the freeze recorded;
    a second opening refused. The synthetic engine stands in for Stockfish."""

    import io

    from agent_helpers import GAME
    from synthetic import engine

    from calliope.agent import Session
    from calliope.facts.search import StockfishEngine

    monkeypatch.setattr(StockfishEngine, "start", staticmethod(lambda path: engine()))
    chosen = {"moments": [{"ply": 3, "slot": "error"}, {"ply": 5, "slot": "special"}]}
    # every ply is analysed for real (the synthetic engine); the choice itself is rx_moments' own,
    # tested with its sessions, and these short games rank too few plies for it
    monkeypatch.setattr(Session, "rx_moments", lambda self, game_id: chosen | {"plies": 10})
    pgns = tmp_path / "pgns"
    pgns.mkdir()
    other = "1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. Bg5 Be7 5. e3 O-O *\n"
    entries = []
    for i, pgn in enumerate((GAME, other)):
        (pgns / f"t{i}.pgn").write_text(pgn, encoding="utf-8")
        entries.append({"name": f"t{i}", "number": f"t{i}", "owner": "white",
                        "uci_sha256": rx_manifest.uci_digest(pgn)})  # fmt: skip
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sets": {"test": entries}}), encoding="utf-8")
    monkeypatch.setattr(rx_manifest, "MANIFEST", manifest)
    monkeypatch.setattr(rx_manifest, "RX_DATA", tmp_path)
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps(freeze_record()), encoding="utf-8")
    doc = rx_manifest.open_test(pgns, "stockfish", freeze, out=io.StringIO())
    for entry in doc["sets"]["test"]:
        assert entry["game_id"] and isinstance(entry["moments"], list)
        assert entry["moments"] == [m["ply"] for m in entry["moment_slots"]]
    assert (tmp_path / "base" / "test" / "base.json").is_file()
    assert doc["test_opened"]["freeze_sha256"] and json.loads(manifest.read_text())["test_opened"]
    with pytest.raises(RuntimeError, match="open already"):
        rx_manifest.open_test(pgns, "stockfish", freeze, out=io.StringIO())


def test_open_test_stops_before_sealing_when_a_game_has_no_moments(tmp_path, monkeypatch) -> None:
    import io

    from agent_helpers import GAME
    from synthetic import engine

    from calliope.facts.search import StockfishEngine

    monkeypatch.setattr(StockfishEngine, "start", staticmethod(lambda path: engine()))
    pgns = tmp_path / "pgns"
    pgns.mkdir()
    (pgns / "t0.pgn").write_text(GAME, encoding="utf-8")
    entries = [{"name": "t0", "number": "t0", "owner": "white",
                "uci_sha256": rx_manifest.uci_digest(GAME)}]  # fmt: skip
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sets": {"test": entries}}), encoding="utf-8")
    monkeypatch.setattr(rx_manifest, "MANIFEST", manifest)
    monkeypatch.setattr(rx_manifest, "RX_DATA", tmp_path)
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps(freeze_record()), encoding="utf-8")
    with pytest.raises(RuntimeError, match="no moments"):  # a short game ranks too few plies
        rx_manifest.open_test(pgns, "stockfish", freeze, out=io.StringIO())
    assert not (tmp_path / "base" / "test" / "base.json").exists()
    assert "test_opened" not in json.loads(manifest.read_text())


# -- the freeze record (implementation review N1) ----------------------------------------------


def test_a_freeze_record_must_fix_the_candidate(tmp_path) -> None:
    assert rx_freeze.problems(freeze_record()) == []
    assert rx_freeze.problems({}) and rx_freeze.problems([])
    bad = freeze_record()
    bad["variants"]["H@v8"]["harness"] = "harness_v2"  # not revision 5's messages
    bad["variants"]["A@v7"]["tools"] = "agent_tools_v8"
    bad["bounds"]["tokens"] = 0
    wrong = rx_freeze.problems(bad)
    assert any("H@v8: harness" in w for w in wrong) and any("A@v7: tools" in w for w in wrong)
    assert any("bounds" in w for w in wrong)
    for path_text in ("", "{}"):  # an empty file or {} opens nothing
        freeze = tmp_path / "freeze.json"
        freeze.write_text(path_text, encoding="utf-8")
        with pytest.raises(RuntimeError, match="is not one"):
            rx_manifest.open_test(tmp_path, "engine", freeze)


def _spec(**changes):
    spec = rx_run.RunSpec(arm="H", set_name="test", game="g", pgn="", moments=[1], base=None,
                          records=None, work=None, tools="v8")  # fmt: skip
    spec.bounds.turns, spec.bounds.tool_calls, spec.bounds.tokens = 90, 150, 4_000_000
    for key, value in changes.items():
        setattr(spec, key, value)
    return spec


def test_a_test_run_must_be_the_frozen_variant(tmp_path) -> None:
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps(freeze_record()), encoding="utf-8")
    _, digest = rx_freeze.read(freeze)
    opened = {"freeze": str(freeze), "freeze_sha256": digest}
    assert rx_freeze.run_problems(opened, _spec()) == []
    assert rx_freeze.run_problems(None, _spec())  # Test not open
    assert "not a frozen variant" in rx_freeze.run_problems(opened, _spec(tools="v7"))[0]
    assert "model" in rx_freeze.run_problems(opened, _spec(model="other/model"))[0]
    assert "harness revision" in rx_freeze.run_problems(opened, _spec(harness_revision=4))[0]
    loose = _spec()
    loose.bounds.tokens = 2_000_000
    assert "bound tokens" in rx_freeze.run_problems(opened, loose)[0]
    freeze.write_text(json.dumps(freeze_record() | {"model": "x"}), encoding="utf-8")
    assert "changed" in rx_freeze.run_problems(opened, _spec())[0]


def test_the_served_version_is_read_from_the_initialize_answer() -> None:
    """LT pilot: the SDK's `InitializeResult` names it `server_info` (`serverInfo` before); both
    pilot runs stopped at `None`. Read from the SDK's own type, and from the older shape."""

    from types import SimpleNamespace

    from mcp import types

    from calliope.agent.definitions import TOOLS_VERSION

    init = types.InitializeResult(
        protocol_version="2025-06-18",
        capabilities=types.ServerCapabilities(),
        server_info=types.Implementation(name="calliope", version=TOOLS_VERSION),
    )
    assert rx_run.served_version(init) == TOOLS_VERSION
    assert rx_run.served_version(SimpleNamespace(serverInfo=SimpleNamespace(version="w"))) == "w"
    assert rx_run.served_version(SimpleNamespace()) is None
