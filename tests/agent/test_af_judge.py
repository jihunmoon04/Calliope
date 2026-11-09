"""AF (agent-af-design.md) §5: judge v2 — the records each sentence cited and their origins
(§5.1), the bundle, the schema (§5.2) and what the report counts (§5.3, §7.3)."""

from __future__ import annotations

import json
from pathlib import Path

import chess
import jsonschema

from tools.rx import evidence as rx_evidence
from tools.rx import judge as rx_judge
from tools.rx import report as rx_report

REPO = Path(__file__).resolve().parents[2]
PROMPTS = REPO / "tools" / "rx" / "prompts"
START = ["e2e4", "d7d5"]  # the line's start: after 1.e4 d5


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _answer(body: dict) -> str:
    return json.dumps({"content": [{"type": "text", "text": json.dumps(body)}]})


def _run(tmp_path: Path, extra: list[dict] | None = None, explore_ledger: bool = True) -> Path:
    """A v8-style run: an explore line continued by a session search, a compare_lines played line
    (analysis PV, then a search extension), a session search score, an analysis judgement; one
    final submission citing them."""

    run = tmp_path / "run"
    explore = {"ref": "x1.aa", "plies": [{}, {}, {}]}
    if explore_ledger:
        explore["ledger"] = {"plies": [{"source": "agent"}, {"source": "engine"},
                                       {"source": "engine"}]}  # fmt: skip
    compare = {"lines": {"played": {"ref": "x2.aa", "source": {"engine": 2}, "extended": 2,
                                    "moves": ["exd5", "Qxd5", "Nc3", "Qa5"]}}}  # fmt: skip
    rows = [
        {"seq": 1, "type": "call", "call_id": 1, "tool": "explore", "answer": _answer(explore)},
        {"seq": 2, "type": "handle", "call_id": 1, "ref": "x1.aa", "kind": "explored_line",
         "source": {"kind": "facts_tree"}, "address": {"from": START, "moves": ["e4d5", "d8d5", "b1c3"]}},
        {"seq": 3, "type": "call", "call_id": 2, "tool": "compare_lines", "answer": _answer(compare)},
        {"seq": 4, "type": "handle", "call_id": 2, "ref": "x2.aa", "kind": "explored_line",
         "source": {"kind": "facts_tree"},
         "address": {"from": START, "moves": ["e4d5", "d8d5", "b1c3", "d5a5"]}},
        {"seq": 5, "type": "handle", "call_id": 1, "ref": "s9.aa", "kind": "search_line",
         "source": {"kind": "search", "position": [*START, "e4d5"]}, "address": {"rank": 1}},
        {"seq": 6, "type": "handle", "call_id": None, "ref": "j1.aa", "kind": "judgement",
         "source": {"kind": "analysis"}, "address": {"judgement": 0}},
        *(extra or []),
        {"seq": 20, "type": "submission", "call_id": 9, "subjects": [{
            "game_ply": 3, "outcome": "accepted", "id": "c1",
            "submitted": {"sentences": [
                {"text": "a", "cites": ["m1"]}, {"text": "b", "cites": ["m2"]},
                {"text": "c", "cites": ["s9.aa"]}, {"text": "d", "cites": ["j1.aa"]}]},
            "verified": [
                {"id": "m1", "kind": "material", "line": "x1.aa", "from": 0, "to": 3,
                 "side": "white", "balance": 0},
                {"id": "m2", "kind": "material", "line": "x2.aa", "from": 0, "to": 2,
                 "side": "white", "balance": 0},
                {"id": "s9.aa:score", "by_handle": "s9.aa", "kind": "engine_score",
                 "line": "s9.aa", "move": "d8d5", "score": {"cp": 40}},
                {"id": "j1.aa:judgement", "by_handle": "j1.aa", "kind": "judgement",
                 "judgement": "j1.aa"}]}]},
    ]  # fmt: skip
    _write(run / "tools.jsonl", rows)
    _write(run / "agent.jsonl", [{"seq": 1, "type": "start", "arm": "H", "set": "train",
                                  "game": "g1", "moments": [3]}])  # fmt: skip
    return run


def _final(run: Path) -> dict:
    from tools.rx.check import finals

    return finals(run, [3])[3]


# -- origins (§5.1) ---------------------------------------------------------------------------


def test_a_v8_runs_origins_are_restored_from_the_serving_call(tmp_path) -> None:
    run = _run(tmp_path)
    records = rx_evidence.Run(run)
    assert records.plies_origin("x1.aa") == ["agent", "search", "search"]
    assert records.plies_origin("x2.aa") == ["analysis", "analysis", "search", "search"]
    assert records.origin("x1.aa") == "search" and records.origin("s9.aa") == "search"
    assert records.origin("j1.aa") == "analysis"


def test_a_material_count_takes_its_own_segments_origin(tmp_path) -> None:
    cited = rx_evidence.evidence(_run(tmp_path), _final(_run(tmp_path)))
    assert cited[0][0]["kind"] == "material" and cited[0][0]["origin"] == "search"
    assert cited[1][0]["origin"] == "analysis"  # plies 0–2 of a line extended by a search later
    assert cited[1][0]["change"] == 0 and cited[1][0]["from"] == 0 and cited[1][0]["to"] == 2


def test_a_cited_handle_resolves_through_by_handle(tmp_path) -> None:
    run = _run(tmp_path)
    cited = rx_evidence.evidence(run, _final(run))
    assert cited[2] == [{"kind": "engine_score", "score": {"cp": 40}, "move": "d8d5",
                         "origin": "search", "fen": _fen([*START, "e4d5"])}]  # fmt: skip
    assert cited[3][0]["kind"] == "judgement" and cited[3][0]["origin"] == "analysis"
    assert "id" not in cited[3][0] and "by_handle" not in cited[3][0]


def test_a_v9_origin_line_stands_over_the_restoration(tmp_path) -> None:
    run = _run(tmp_path, [{"seq": 10, "type": "origin", "call_id": 1, "ref": "x1.aa",
                           "plies_origin": ["agent", "analysis", "analysis"]}])  # fmt: skip
    assert rx_evidence.Run(run).origin("x1.aa") == "agent"


def test_a_v7_explore_line_is_all_the_agents(tmp_path) -> None:
    run = _run(tmp_path, explore_ledger=False)
    assert rx_evidence.Run(run).plies_origin("x1.aa") == ["agent", "agent", "agent"]


def test_a_lines_standing_is_computed_from_the_board_not_copied(tmp_path) -> None:
    run = _run(tmp_path)
    line = rx_evidence.evidence(run, _final(run))[0][0]
    assert line["start_fen"] == _fen(START) and line["start_standing_white"] == 0
    assert line["moves"] == ["exd5", "Qxd5", "Nc3"] and line["standing_white_after"] == [1, 0, 0]


def _fen(path: list[str]) -> str:
    board = chess.Board()
    for uci in path:
        board.push_uci(uci)
    return board.fen()


def test_test_ones_evidence_resolves_every_citation_and_reads_the_origins_as_af_d() -> None:
    """AF-D §0.1, §5.1 (review N1 of rev. 3): the prototype's output on Test 1's wrong sentences."""

    doc = json.loads((REPO / "docs/design/rx-evidence/af/test1-wrong-cites.json")
                     .read_text(encoding="utf-8"))  # fmt: skip
    assert doc["unresolved_cites"] == 0
    origins = [p["segment_origin"] for c in doc["cases"] for x in c["cites"]
               for p in x["propositions"] if p.get("kind") == "material"]  # fmt: skip
    assert sorted(origins) == ["analysis"] * 2 + ["search"] * 8


# -- the bundle and the schema (§5.1, §5.2) ---------------------------------------------------


def test_a_judge_v2_bundle_carries_each_sentences_evidence_and_no_arm(tmp_path) -> None:
    run = _run(tmp_path)
    refs = tmp_path / "refs"
    (refs / "train").mkdir(parents=True)
    (refs / "train" / "g1-3.json").write_text("{}")
    original = rx_judge.REFERENCES
    rx_judge.REFERENCES = refs
    try:
        out = rx_judge.bundle([run], "J2", seed=1, root=tmp_path / "judging",
                              keys=tmp_path / "keys", judge="judge_v2")  # fmt: skip
        v1 = rx_judge.bundle([run], "J1", seed=1, root=tmp_path / "judging",
                             keys=tmp_path / "keys")  # fmt: skip
    finally:
        rx_judge.REFERENCES = original
    part = tmp_path / "judging" / "J2" / "part01"
    items = json.loads((part / "bundle.json").read_text(encoding="utf-8"))["items"]
    sentences = items[0]["sentences"]
    assert [len(s["evidence"]) for s in sentences] == [1, 1, 1, 1]
    assert '"arm"' not in json.dumps(items) and "x1.aa" not in json.dumps(items)
    assert (part / "judge_v2.md").exists() and (part / "judge_v2.schema.json").exists()
    assert out["judge"] == "judge_v2"
    key = json.loads((tmp_path / "keys" / "J2" / "bundle_key.json").read_text())
    assert key["judge"] == "judge_v2"
    plain = json.loads((tmp_path / "judging" / "J1" / "part01" / "bundle.json").read_text())
    assert "evidence" not in json.dumps(plain) and v1["judge"] == "judge_v1"


def test_the_v2_schema_takes_search_only_and_the_kind_source_and_v1_does_not() -> None:
    v2 = json.loads((PROMPTS / "judge_v2.schema.json").read_text(encoding="utf-8"))
    v1 = json.loads((PROMPTS / "judge_v1.schema.json").read_text(encoding="utf-8"))
    doc = {"version": "judge_v2", "items": [{"key": "0123abcd", "score": 3, "causes": [],
           "sentences": [{"n": 1, "verdict": "search_only", "why": "x"},
                         {"n": 2, "verdict": "wrong", "kind": "source", "why": "y"}]}]}  # fmt: skip
    jsonschema.validate(doc, v2)
    bad = json.loads(json.dumps(doc))
    bad["items"][0]["sentences"][0].pop("why")
    try:
        jsonschema.validate(bad, v2)
        raise AssertionError("search_only without why accepted")
    except jsonschema.ValidationError:
        pass
    doc["version"] = "judge_v1"
    try:
        jsonschema.validate(doc, v1)
        raise AssertionError("judge_v1 took search_only")
    except jsonschema.ValidationError:
        pass


# -- the report (§5.3, §7.3) ------------------------------------------------------------------


def test_m1s_is_counted_apart_from_m1b() -> None:
    judged = {"sentences": [{"verdict": "wrong"}, {"verdict": "search_only"},
                            {"verdict": "search_only"}, {"verdict": "ok"}],
              "causes": [], "score": 3}  # fmt: skip
    v = rx_report.moment_values(judged, [])
    assert v["wrong"] == 1 and v["search_only"] == 2 and v["sentences"] == 4
    assert rx_report.wrong_rate([v]) == 25.0 and rx_report.search_only_rate([v]) == 50.0
    assert rx_report.judge_v1_like_rate([v]) == 75.0
    assert rx_report.search_only_rate([rx_report.moment_values(None, [])]) == 0.0


def _entry(diff, lo, hi, wrong_hi=1.0, search_hi=None):
    out = {"decisive": {"diff": diff, "lo": lo, "hi": hi},
           "wrong": {"diff": 0.0, "lo": -1.0, "hi": wrong_hi}}  # fmt: skip
    if search_hi is not None:
        out["search_only"] = {"diff": 0.0, "lo": -1.0, "hi": search_hi}
    return out


def test_m1s_above_its_ceiling_refuses_and_a_judge_v1_entry_is_not_touched() -> None:
    good = _entry(0.2, 0.05, 0.3)
    assert rx_report.quality_gate(good, {"test2": good})["passed"]
    within = _entry(0.2, 0.05, 0.3, search_hi=rx_report.M1S_CEILING)
    assert rx_report.quality_gate(within, {"test2": within})["passed"]
    above = _entry(0.2, 0.05, 0.3, search_hi=rx_report.M1S_CEILING + 0.5)
    gate = rx_report.quality_gate(above, {"test2": above})
    assert not gate["passed"] and any("M1s" in r for r in gate["reasons"])


# -- review F1 of the implementation: origins as of each submission -----------------------------


def _scene_run(tmp_path: Path, v9: bool) -> Path:
    """One `x` ref served twice with other origins; a submission after each serving."""

    run = tmp_path / ("v9" if v9 else "v8")

    def served(seq, call_id, sources):
        rows = [{"seq": seq, "type": "call", "call_id": call_id, "tool": "explore",
                 "answer": _answer({"ref": "x7.aa", "plies": [{}, {}],
                                    "ledger": {"plies": [{"source": s} for s in sources]}})}]  # fmt: skip
        if v9:
            v9_sources = ["search" if s == "engine" else s for s in sources]
            rows.append({"seq": seq + 1, "type": "origin", "call_id": call_id, "ref": "x7.aa",
                         "plies_origin": v9_sources})  # fmt: skip
        return rows

    def submitted(seq, ply):
        return {"seq": seq, "type": "submission", "call_id": seq, "subjects": [{
            "game_ply": ply, "outcome": "accepted", "id": f"c{ply}",
            "submitted": {"sentences": [{"text": "x", "cites": ["m"]}]},
            "verified": [{"id": "m", "kind": "material", "line": "x7.aa", "from": 0, "to": 2,
                          "side": "white", "balance": 0}]}]}  # fmt: skip

    rows = [{"seq": 1, "type": "handle", "call_id": 1, "ref": "x7.aa", "kind": "explored_line",
             "source": {"kind": "facts_tree"}, "address": {"from": START, "moves": ["e4d5", "d8d5"]}},
            *served(2, 1, ["agent", "agent"]), submitted(5, 3),
            *served(6, 2, ["agent", "engine"]), submitted(9, 5)]  # fmt: skip
    _write(run / "tools.jsonl", rows)
    _write(run / "agent.jsonl", [{"seq": 1, "type": "start", "arm": "H", "set": "train",
                                  "game": "g1", "moments": [3, 5]}])  # fmt: skip
    return run


def test_a_citation_takes_the_origin_of_the_serving_before_its_submission(tmp_path) -> None:
    from tools.rx.check import finals

    for v9 in (True, False):
        run = _scene_run(tmp_path, v9)
        finals_ = finals(run, [3, 5])
        records = rx_evidence.Run(run)
        first = rx_evidence.evidence(run, finals_[3], records)[0][0]
        second = rx_evidence.evidence(run, finals_[5], records)[0][0]
        assert first["origin"] == "agent", v9  # the first scene: the agent's own two moves
        assert second["origin"] == "search", v9  # the second: the same ref, continued by a search
        assert records.plies_origin("x7.aa", before=5) == ["agent", "agent"]


# -- review F2 of the implementation: Test 2's judge -----------------------------------------


def test_a_test2_bundle_must_use_the_judge_its_freeze_fixed(tmp_path, monkeypatch) -> None:
    from tools.rx import freeze as rx_freeze

    run = _run(tmp_path)
    _write(run / "agent.jsonl", [{"seq": 1, "type": "start", "arm": "H", "set": "test2",
                                  "game": "g1", "moments": [3]}])  # fmt: skip
    monkeypatch.setattr(rx_freeze, "frozen_judge", lambda set_name, manifest=None: "judge_v2")
    import pytest

    with pytest.raises(ValueError, match="judged with judge_v2"):
        rx_judge.bundle([run], "J9", seed=1, root=tmp_path / "judging", keys=tmp_path / "keys")


def test_a_test2_report_refuses_a_judging_by_another_judge(tmp_path, monkeypatch) -> None:
    import pytest

    from tools.rx import freeze as rx_freeze

    rows = [{"set": "test2", "game": "h", "arm": "A", "result": {"run": "r2"}}]
    (tmp_path / "batches").mkdir()
    (tmp_path / "batches" / "b.jsonl").write_text(json.dumps(rows[0]))
    (tmp_path / "keys" / "j").mkdir(parents=True)
    (tmp_path / "keys" / "j" / "bundle_key.json").write_text(
        json.dumps({"runs": ["r2"], "judge": "judge_v1", "key": {}}))  # fmt: skip
    monkeypatch.setattr(rx_report, "RX_DATA", tmp_path)
    monkeypatch.setattr(rx_report, "KEYS", tmp_path / "keys")
    monkeypatch.setattr(rx_freeze, "frozen_judge", lambda set_name, manifest=None: "judge_v2")
    with pytest.raises(ValueError, match="freeze fixed judge_v2"):
        rx_report.build("b", "j", tmp_path, [("A", "A")])
