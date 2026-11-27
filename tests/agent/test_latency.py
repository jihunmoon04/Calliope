"""The run's waits cut without changing what it decides: the guard skips `count_tokens` under a sure
bound (`tools/rx/guard.py`), and an opened game's cached plies are summarized in the background
for `game_overview` (`Session.prewarm`)."""

from __future__ import annotations

import json
from types import SimpleNamespace

from agent_helpers import G1, GAME, session

import tools.rx.guard as rx_guard
from tools.rx import score as rx_score

# -- the guard's bound -----------------------------------------------------------------------------


class _Counter:
    """A model with `count`: the sizes it says, in turn; the calls it got."""

    def __init__(self, *sizes):
        self.sizes = list(sizes)
        self.calls = 0

    def count(self, messages, tools, tool_choice=None):
        self.calls += 1
        return self.sizes[min(self.calls, len(self.sizes)) - 1]


def _guard():
    log = []
    return rx_guard.Guard(SimpleNamespace(write=log.append)), log


SYSTEM = {"role": "system", "content": "가이드"}
TOOLS = [{"name": "ply"}]


def _sent(guard, model, messages, usage):
    """One request through the loop's steps: checked, sent, answered."""

    assert guard.check(model, messages, TOOLS) is None
    guard.answered(usage, len(messages))


def test_a_request_extending_the_last_one_is_bounded_and_not_counted():
    guard, log = _guard()
    model = _Counter(30_000)
    messages = [SYSTEM, {"role": "user", "content": "장면"}]
    _sent(guard, model, messages, {"input_tokens": 30_000, "output_tokens": 2_000})
    messages += [{"role": "assistant", "content": "x"}, {"role": "tool", "content": "답" * 100}]
    assert guard.check(model, messages, TOOLS) is None
    assert model.calls == 1  # only the first request was counted
    line = log[-1]
    tail = len(json.dumps(messages[2:], ensure_ascii=False).encode("utf-8"))
    bound = 30_000 + 2_000 + tail + 2 * rx_guard.BOUND_PER_MESSAGE + rx_guard.BOUND_MARGIN
    assert line["how"] == "bounded" and line["counted_tokens"] == bound
    assert line["verdict"] == "send"


def test_a_bound_at_80k_or_over_is_counted_and_the_count_decides():
    guard, log = _guard()
    model = _Counter(70_000, 81_000)
    messages = [SYSTEM, {"role": "user", "content": "장면"}]
    _sent(guard, model, messages, {"input_tokens": 78_000, "output_tokens": 2_000})
    messages.append({"role": "tool", "content": "답"})
    assert guard.check(model, messages, TOOLS) == "compact"  # the count, not the bound
    assert model.calls == 2 and log[-1]["how"] == "counted"


def test_a_changed_earlier_message_or_other_tools_are_counted():
    guard, _ = _guard()
    model = _Counter(1_000)
    messages = [SYSTEM, {"role": "user", "content": "장면"}]
    _sent(guard, model, messages, {"input_tokens": 1_000, "output_tokens": 10})
    rewritten = [
        SYSTEM,
        {"role": "user", "content": "다른 장면"},
        {"role": "tool", "content": "답"},
    ]
    guard.check(model, rewritten, TOOLS)
    assert model.calls == 2  # the prefix changed: no bound
    guard.answered({"input_tokens": 1_000, "output_tokens": 10}, len(rewritten))
    guard.check(model, rewritten + [{"role": "tool", "content": "답"}], [{"name": "detail"}])
    assert model.calls == 3  # the tools changed: no bound


def test_no_bound_after_a_request_the_guard_did_not_check_or_in_a_new_moment():
    guard, _ = _guard()
    model = _Counter(1_000)
    messages = [SYSTEM, {"role": "user", "content": "장면"}]
    _sent(guard, model, messages, {"input_tokens": 1_000, "output_tokens": 10})
    guard.size(model, messages + [{"role": "user", "content": "노트"}], [])  # a compaction's ask
    guard.answered({"input_tokens": 1_100, "output_tokens": 10}, len(messages) + 1)
    guard.check(model, messages + [{"role": "tool", "content": "답"}], TOOLS)
    assert model.calls == 3  # the answer was not the checked request's
    _sent(guard, model, messages, {"input_tokens": 1_000, "output_tokens": 10})
    guard.new_moment()
    guard.check(model, messages + [{"role": "tool", "content": "답"}], TOOLS)
    assert model.calls == 5


def test_no_bound_without_the_answers_output_or_without_a_counter():
    guard, _ = _guard()
    model = _Counter(1_000)
    messages = [SYSTEM, {"role": "user", "content": "장면"}]
    _sent(guard, model, messages, {"input_tokens": 1_000})  # no output tokens in the usage
    guard.check(model, messages + [{"role": "tool", "content": "답"}], TOOLS)
    assert model.calls == 2
    plain, log = _guard()
    estimated = SimpleNamespace(complete=None)  # no counter: the estimate, as before
    _sent(plain, estimated, messages, {"input_tokens": 1_000, "output_tokens": 10})
    plain.check(estimated, messages + [{"role": "tool", "content": "답"}], TOOLS)
    assert log[-1]["how"] == "estimated"


def test_the_score_rows_largest_count_leaves_out_bounded_lines(tmp_path):
    run = tmp_path / "01RUN"
    run.mkdir()
    lines = [{"seq": 1, "type": "start", "game": "hung"},
             {"seq": 2, "type": "guard", "counted_tokens": 12_000, "how": "counted"},
             {"seq": 3, "type": "guard", "counted_tokens": 79_000, "how": "bounded"},
             {"seq": 4, "type": "end", "reason": "done", "totals": {}}]  # fmt: skip
    (run / "agent.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines), "utf-8")
    (run / "tools.jsonl").write_text("", "utf-8")
    game = rx_score.run_numbers(run)
    assert game["largest_counted"] == 12_000 and game["guard"] == ["bounded", "counted"]


# -- the summaries prewarmed -----------------------------------------------------------------------


def _analysed(tmp_path) -> None:
    first = session(tmp_path)
    try:
        first.open_game(pgn=GAME)
        first.analyze_game(G1, wait_seconds=60)
    finally:
        first.close()


def test_an_opened_games_cached_plies_are_summarized_in_the_background(tmp_path, monkeypatch):
    _analysed(tmp_path)
    plain = session(tmp_path)
    try:
        plain.open_game(pgn=GAME)
        expected = plain.game_overview(G1)  # replays every ply
    finally:
        plain.close()
    s = session(tmp_path, prewarm=True)
    try:
        s.open_game(pgn=GAME)
        for thread in s._prewarm_threads:
            thread.join(timeout=60)
        key = s.game(G1).key
        assert all(s.jobs.summary(key, p) is not None for p in range(1, 11))

        def no_replay(*args, **kwargs):
            raise AssertionError("game_overview replayed a ply")

        monkeypatch.setattr(s.cache, "get", no_replay)
        overview = s.game_overview(G1)
        assert overview["analysed"] == 10
        assert overview["lines"] == expected["lines"] and overview["moments"] == expected["moments"]
        s.open_game(pgn=GAME)  # once a game a process
        assert len(s._prewarm_threads) == 1
    finally:
        s.close()


def test_no_prewarm_by_default_or_without_cached_plies(tmp_path):
    s = session(tmp_path)
    try:
        s.open_game(pgn=GAME)
        assert s._prewarm_threads == []
    finally:
        s.close()
    fresh = session(tmp_path / "fresh", prewarm=True)
    try:
        fresh.open_game(pgn=GAME)  # nothing cached: nothing summarized, nothing analysed
        for thread in fresh._prewarm_threads:
            thread.join(timeout=60)
        key = fresh.game(G1).key
        assert all(fresh.jobs.summary(key, p) is None for p in range(1, 11))
        assert not any(fresh._cached(fresh.game(G1).parsed, p) for p in range(1, 11))
    finally:
        fresh.close()


def test_a_game_held_by_a_work_tool_is_prewarmed_too(tmp_path):
    """The RX runner's server never calls `open_game`: its first `ply` holds the game."""

    _analysed(tmp_path)
    s = session(tmp_path, prewarm=True)
    try:
        s.ply(G1, 3)
        for thread in s._prewarm_threads:
            thread.join(timeout=60)
        key = s.game(G1).key
        assert len(s._prewarm_threads) == 1
        assert all(s.jobs.summary(key, p) is not None for p in range(1, 11))
    finally:
        s.close()
