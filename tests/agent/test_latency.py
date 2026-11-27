"""The run's waits cut without changing what it decides: the guard skips `count_tokens` under an upper
bound (`tools/rx/guard.py`), and an opened game's cached plies are summarized in the background
for `game_overview` (`Session.prewarm`)."""

from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

from agent_helpers import G1, GAME, session

import tools.rx.guard as rx_guard
from calliope.agent import session as session_module
from tools.rx import claude as rx_claude
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


def test_a_claude_answer_missing_its_usage_counts_gives_no_bound():
    """Review F1: the adapter reads an absent count as 0; it marks it, and the guard counts."""

    for usage in ({"output_tokens": 50}, {"input_tokens": 30_000}, None):
        doc = {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}
        if usage is not None:
            doc["usage"] = usage
        reply = rx_claude.from_claude(doc, "claude-haiku-5-5")
        assert reply.usage["usage_missing"]
        guard, log = _guard()
        model = _Counter(79_000, 96_000)
        messages = [SYSTEM, {"role": "user", "content": "장면"}]
        _sent(guard, model, messages, reply.usage)
        assert (
            guard.check(model, messages + [{"role": "tool", "content": "답"}], TOOLS) == "compact"
        )
        assert model.calls == 2 and log[-1]["how"] == "counted"
    whole = rx_claude.from_claude({"content": [], "usage": {"input_tokens": 1, "output_tokens": 2}},
                                  "claude-haiku-5-5")  # fmt: skip
    assert "usage_missing" not in whole.usage


def test_the_last_requests_size_is_the_bounds_floor():
    """Review F1: an answer's input below what its request was counted at does not lower it."""

    guard, log = _guard()
    model = _Counter(79_000, 79_500)
    messages = [SYSTEM, {"role": "user", "content": "장면"}]
    _sent(guard, model, messages, {"input_tokens": 10, "output_tokens": 10})
    guard.check(model, messages + [{"role": "tool", "content": "답"}], TOOLS)
    assert model.calls == 2 and log[-1]["how"] == "counted"  # 79,000 + ... is not under 80k


def test_openrouter_keeps_its_count_and_usage(monkeypatch):
    """Review F2: OpenRouter's usage does not stand for the Claude count, so it is never skipped."""

    class Counter:
        calls = 0

        def __init__(self, name, cache=True):
            pass

        def count(self, messages, tools, tool_choice=None):
            Counter.calls += 1
            return 1_000

    monkeypatch.setattr(rx_claude, "Claude", Counter)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    guard, log = _guard()
    openrouter = SimpleNamespace(model="anthropic/claude-haiku-5.5", cache=True)
    messages = [SYSTEM, {"role": "user", "content": "장면"}]
    _sent(guard, openrouter, messages, {"input_tokens": 1_000, "output_tokens": 10})
    guard.check(openrouter, messages + [{"role": "tool", "content": "답"}], TOOLS)
    assert Counter.calls == 2 and log[-1]["how"] == "counted+usage"


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


def _settle(s) -> None:
    worker = s._prewarm_worker
    if worker is not None:
        worker.join(timeout=60)


def _blocked(s, monkeypatch):
    """The cache's reads held until `release` is set; `entered` once one is waiting."""

    entered, release = threading.Event(), threading.Event()
    original = s.cache.get

    def get(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=60)
        return original(*args, **kwargs)

    monkeypatch.setattr(s.cache, "get", get)
    return entered, release


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
        _settle(s)
        key = s.game(G1).key
        assert all(s.jobs.summary(key, p) is not None for p in range(1, 11))

        def no_replay(*args, **kwargs):
            raise AssertionError("game_overview replayed a ply")

        monkeypatch.setattr(s.cache, "get", no_replay)
        overview = s.game_overview(G1)
        assert overview == expected  # the whole answer, on the same files
        s.open_game(pgn=GAME)  # once a game a process
        assert s._prewarm_worker is None and not s._prewarm_queue
    finally:
        s.close()


def test_no_prewarm_by_default_or_without_cached_plies(tmp_path):
    s = session(tmp_path)
    try:
        s.open_game(pgn=GAME)
        assert s._prewarm_worker is None and not s._prewarmed and not s._summary_locks
    finally:
        s.close()
    fresh = session(tmp_path / "fresh", prewarm=True)
    try:
        fresh.open_game(pgn=GAME)  # nothing cached: nothing summarized, nothing analysed
        _settle(fresh)
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
        _settle(s)
        key = s.game(G1).key
        assert all(s.jobs.summary(key, p) is not None for p in range(1, 11))
    finally:
        s.close()


def test_one_worker_takes_the_games_in_turn_and_skips_a_game_over_the_path_limit(
    tmp_path, monkeypatch
):
    """Review F5: one worker, a queue; a game `game_overview` refuses is not queued."""

    _analysed(tmp_path)
    s = session(tmp_path, prewarm=True)
    entered, release = _blocked(s, monkeypatch)
    try:
        s.open_game(pgn=GAME)
        assert entered.wait(timeout=60)
        s.open_game(moves=["e4", "e5", "Nf3"])
        assert [t.name for t in threading.enumerate()].count("prewarm") == 1
        assert len(s._prewarm_queue) == 1
        long = s.open_game(moves=" ".join(["Nf3 Nf6 Ng1 Ng8"] * 151).split())
        assert s.game(long["game"]).key not in s._prewarmed
        release.set()
        _settle(s)
        assert s._prewarm_worker is None and not s._prewarm_queue
    finally:
        release.set()
        s.close()


def test_an_evicted_games_prewarm_is_dropped(tmp_path, monkeypatch):
    _analysed(tmp_path)
    s = session(tmp_path, prewarm=True)
    entered, release = _blocked(s, monkeypatch)
    try:
        s.open_game(pgn=GAME)
        key = s.game(G1).key
        assert entered.wait(timeout=60)
        del s.held[key]  # evicted while its first ply is read
        release.set()
        _settle(s)
        assert all(s.jobs.summary(key, p) is None for p in range(2, 11))
    finally:
        release.set()
        s.close()


def test_a_summary_published_while_waiting_is_checked_against_the_files_read_again(tmp_path):
    """Review F3: the files may be replaced while `_summary` waits for the game's lock."""

    _analysed(tmp_path)
    s = session(tmp_path, prewarm=True)
    s._prewarm_stop.set()  # no worker: the interleaving is scripted
    try:
        s.open_game(pgn=GAME)
        game = s.game(G1)
        real = s.cache.file_digests
        reads = []

        def digests(key):
            reads.append(key)
            found = real(key)
            return found if len(reads) == 1 else ("b" * 64, "c" * 64)  # replaced meanwhile

        stale = {"stale": True}
        answers = iter([None])

        def summary(key, ply):  # none at first; then the replaced files' summary appears
            found = next(answers, "published")
            if found == "published":
                return stale | {"bundle": list(real(s._key(game.parsed, ply)[0]))}
            return found

        s.cache.file_digests = digests
        s.jobs.summary = summary
        got = s._summary(game, 4)
        assert len(reads) == 2  # read again under the lock
        assert got is not None and "stale" not in got  # replayed, not the stale summary
    finally:
        s.close()


def test_a_prewarm_still_running_at_close_never_uses_the_engine(tmp_path, monkeypatch):
    """Review F4: one deadline for both workers; the prewarm keys and records with the build it
    took, so a ply finishing after `close` starts no engine."""

    _analysed(tmp_path)
    monkeypatch.setattr(session_module, "STOP_SECONDS", 0.2)
    s = session(tmp_path, prewarm=True)
    entered, release = _blocked(s, monkeypatch)
    s.open_game(pgn=GAME)
    worker = s._prewarm_worker
    assert entered.wait(timeout=60)
    started = time.monotonic()
    s.close()
    assert time.monotonic() - started < 5
    used = []
    monkeypatch.setattr(s, "_engine_build", lambda: used.append(1))
    monkeypatch.setattr(s, "_identity", lambda: used.append(1))
    release.set()
    worker.join(timeout=60)
    assert not worker.is_alive() and used == []
