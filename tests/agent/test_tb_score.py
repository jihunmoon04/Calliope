"""TB-D P2 (rev. 5): the score command — two steps around a Claude Code session's judge v2 judging;
a moment without commentary counted as a failure; the row's judging fields; the guard counting an
OpenRouter Anthropic model with the Claude API's `count_tokens`."""

from __future__ import annotations

import json
from types import SimpleNamespace

from tools.rx import guard as rx_guard
from tools.rx import score as rx_score

GOOD = {"sentences": [{"n": 1, "verdict": "ok"},
                      {"n": 2, "verdict": "wrong", "kind": "grade", "why": "x"}],
        "causes": [{"cause": 1, "verdict": "explained"}], "score": 4}  # fmt: skip


def test_a_moment_without_commentary_is_a_failure_in_the_rates():
    from tools.rx.report import moment_values

    judged = moment_values(GOOD, ["decisive"])
    missing = moment_values(None, ["decisive"])
    out = rx_score.rates([judged, missing])
    assert out["M2b"] == 0.5  # the missing moment's decisive cause is not explained
    assert out["M1b"] == 50.0 and out["sentences"] == 2
    assert out["score"] == 4.0


def test_the_score_is_judged_by_judge_v2_in_a_session():
    assert rx_score.JUDGE == "judge_v2"
    assert (rx_score.PROMPTS / "judge_v2.md").exists()
    assert not (rx_score.PROMPTS / "judge_v2r.md").exists()  # no API judge (rev. 5)
    assert rx_score.GAMES == ("184800218248", "185264271324")
    assert rx_score.BOUNDS["cost"] == 1.0 and rx_score.BOUNDS["tokens"] == 20_000_000  # F8


def test_run_then_finish(tmp_path, monkeypatch):
    """`run` keeps what `finish` needs; `finish` reads the audited judgings and writes one row."""

    monkeypatch.setattr(rx_score, "PENDING", tmp_path / "score")
    monkeypatch.setattr(rx_score, "RX_DATA", tmp_path)
    for run in ("R1", "R2"):
        (tmp_path / "runs" / run).mkdir(parents=True)
    monkeypatch.setattr(rx_score, "run_game", lambda g, args: {
        "game": g, "exit": 0, "run": "R1" if g == rx_score.GAMES[0] else "R2", "seconds": 7,
        "stderr": ""})  # fmt: skip
    import tools.rx.judge as rx_judge

    monkeypatch.setattr(rx_judge, "bundle", lambda runs, judge: {
        "judging": "abcd1234", "parts": ["p1"], "items": 2, "judge": judge})  # fmt: skip
    assert rx_score.main(["run", "--name", "t1"]) == 0
    pending = json.loads((tmp_path / "score" / "t1.json").read_text())
    assert pending["runs"] == ["R1", "R2"] and pending["judging"] == "abcd1234"
    assert pending["variant"]["harness_revision"] == 12

    monkeypatch.setattr(rx_judge, "checked_judgings", lambda j, root: {1: {}})
    monkeypatch.setattr(rx_judge, "join", lambda j, docs: [
        {"run_id": "R1", "ply": 3, "judged": GOOD}])  # fmt: skip
    monkeypatch.setattr(rx_score, "moment_rows", lambda runs, judged, tier=2: (
        [{"wrong": 1, "search_only": 0, "sentences": 2, "decisive": 1.0, "score": 4.0},
         {"wrong": 0, "search_only": 0, "sentences": 0, "decisive": 0.0, "score": None}],
        {"submitted": 1, "asked": 2}) if tier == 2 else ([], {"submitted": 0, "asked": 0}))  # fmt: skip
    monkeypatch.setattr(rx_score, "run_numbers", lambda r: {
        "run": r.name, "largest_request": 60_000, "totals": {"cost": 0.05},
        "model": "anthropic/claude-haiku-5.5", "harness": "harness_v5"})  # fmt: skip
    card = tmp_path / "scorecard.jsonl"
    assert rx_score.main(["finish", "--name", "t1", "--scorecard", str(card)]) == 0
    row = json.loads(card.read_text().splitlines()[0])
    assert row["completion"] == {"submitted": 1, "asked": 2}
    assert row["rates"]["M2b"] == 0.5 and row["cost"] == 0.1
    assert row["judging"]["judge"] == "judge_v2" and row["judging"]["by"] == "claude_code_session"
    assert row["variant"]["provider"] == "openrouter" and row["variant"]["effort"] is None


def test_an_openrouter_anthropic_model_is_counted_by_the_claude_api(monkeypatch):
    seen = {}

    class Counter:
        def __init__(self, name, cache=True):
            seen["name"] = name

        def count(self, messages, tools, tool_choice=None):
            return 42_000

    import tools.rx.claude as rx_claude

    monkeypatch.setattr(rx_claude, "Claude", Counter)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    guard = rx_guard.Guard(SimpleNamespace(write=lambda x: None))
    openrouter = SimpleNamespace(model="anthropic/claude-haiku-5.5", cache=True)
    assert guard.size(openrouter, [], []) == (42_000, "counted+usage")  # review F1
    assert seen["name"] == "claude-haiku-5-5"
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    other = rx_guard.Guard(SimpleNamespace(write=lambda x: None))
    assert other.size(openrouter, [{"role": "user", "content": "x" * 100}], [])[1] == "estimated"
