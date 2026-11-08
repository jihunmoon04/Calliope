"""HS (agent-hs-design.md): arm H's stages, gate and judge (§2, §3, review B2), the logged system
message and task (§4), the transport retry through the real request child (§4, review N2), and the
pooled report with its decision (§6, review C1)."""

from __future__ import annotations

import http.server
import json
import threading
from types import SimpleNamespace

import anyio
import pytest
from agent_helpers import GAME

from tools.rx import harness
from tools.rx import model as rx_model
from tools.rx import report as rx_report
from tools.rx import run as rx_run

# -- the transport retry (§4, N2) ----------------------------------------------------------------------


class _CutShort(http.server.BaseHTTPRequestHandler):
    """Answers a chunked body and closes before its last chunk: `http.client.IncompleteRead`."""

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        self.wfile.write(
            b"40\r\n" + b'{"choices": [' + b"x" * 10
        )  # a chunk of 64 promised, 23 sent
        self.wfile.flush()
        self.close_connection = True

    def log_message(self, *args):  # quiet
        pass


@pytest.fixture
def cut_short_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), _CutShort)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/chat"
    server.shutdown()


def test_a_cut_short_answer_comes_back_from_the_child_as_transport(cut_short_server, monkeypatch):
    monkeypatch.setenv(rx_model.KEY_VAR, "test-key-not-real")
    with pytest.raises(rx_model.ModelTransient, match="cut short"):
        rx_model.post_in_child(cut_short_server, {"model": "m", "messages": []}, timeout=30)


def test_complete_retries_a_transport_error_once(monkeypatch):
    monkeypatch.setenv(rx_model.KEY_VAR, "test-key-not-real")
    monkeypatch.setattr(rx_model.time, "sleep", lambda s: None)
    doc = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {}}
    answers = [rx_model.ModelTransient("cut"), doc]

    def post(self, body):
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(rx_model.OpenRouter, "_post", post)
    assert rx_model.OpenRouter("m").complete([], []).message["content"] == "ok"
    answers[:] = [rx_model.ModelTransient("cut"), rx_model.ModelTransient("cut again")]
    with pytest.raises(rx_model.ModelTransient):
        rx_model.OpenRouter("m").complete([], [])


# -- the gate (§2, B2) -----------------------------------------------------------------------------------


class _Log:
    def __init__(self):
        self.lines = []

    def write(self, line):
        self.lines.append(line)


class _Session:
    def __init__(self, submit_answers=None):
        self.calls = []
        self.submit_answers = list(submit_answers or [])

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "submit_commentary":
            answer = self.submit_answers.pop(0) if self.submit_answers else {"accepted": True}
            text = json.dumps(answer)
        else:
            text = "{}"
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], isError=False)


def _gated(phase, ply):
    log, session = _Log(), _Session()
    gate = harness.Gate(session, harness.Game(GAME), log, "g")
    gate.phase, gate.current_ply, gate.next_call_id = phase, ply, "call-7"
    return gate, session, log


def _send(gate, arguments):
    return anyio.run(gate.call_tool, "submit_commentary", arguments)


def test_the_gate_holds_every_submit_in_the_facts_phase():
    gate, session, log = _gated("facts", 3)
    result = _send(gate, {"game": "g", "ply": 3})
    assert result.isError and session.calls == []
    [line] = log.lines
    assert line["type"] == "tool_unsent" and line["reason"] == "harness_gate"
    assert line["tool_call_id"] == "call-7" and line["phase"] == "facts" and line["subjects"] == [3]


def test_the_gate_passes_only_the_current_moment_at_its_submit_step():
    gate, session, log = _gated("submit", 3)
    assert not _send(gate, {"game": "g", "ply": 3}).isError  # the current ply
    played = {"position": {"ply": 3, "at": "before"}, "move": "exd5"}
    assert not _send(gate, {"game": "g"} | played).isError  # by position and move
    assert not _send(gate, {"game": "g", "items": [{"ply": 3}, played]}).isError
    assert len(session.calls) == 3 and log.lines == []
    for held in ({"ply": 4},  # another ply
                 {"items": [{"ply": 3}, {"ply": 5}]},  # an unjudged ply in items
                 {"items": []},  # empty
                 {"items": "x"},  # malformed
                 {"position": {"ply": 3, "at": "before"}, "move": "Nc3"},  # a variation
                 {"position": {"ply": 2, "at": "after"}, "move": "e4"}):  # fmt: skip
        assert _send(gate, {"game": "g"} | held).isError, held
    assert len(session.calls) == 3 and len(log.lines) == 6
    assert log.lines[1]["subjects"] == [3, 5]


# -- the stages (§2, §3, §4) -----------------------------------------------------------------------------


def _reply(content=None, calls=()):
    message = {"content": content}
    if calls:
        message["tool_calls"] = [{"id": f"c{i}", "type": "function",
                                  "function": {"name": n, "arguments": json.dumps(a)}}
                                 for i, (n, a) in enumerate(calls)]  # fmt: skip
    return rx_model.Reply(message=message, usage={"input_tokens": 10, "output_tokens": 5,
                                                  "cost": 0.001}, body_fields=[])  # fmt: skip


class _Scripted:
    """A model answering from a list; it keeps every request it was sent."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def complete(self, messages, tools):
        self.requests.append([dict(m) for m in messages])
        return self.replies.pop(0)


def _verdict(passed, problems=()):
    return _reply(json.dumps({"pass": passed, "problems": list(problems)}))


def _run_stages(tmp_path, agent_replies, judge_replies, moments=((3, "2.exd5"),), tokens=None,
                judge=None, submit_answers=None):  # fmt: skip
    spec = rx_run.RunSpec(arm="H", set_name="validation", game="g", pgn=GAME, moments=[m for m, _ in moments],
                          base=tmp_path, records=tmp_path, work=tmp_path, game_id="g")  # fmt: skip
    if tokens is not None:
        spec.bounds.tokens = tokens
    log = rx_run.AgentLog(tmp_path / "RUN" / "agent.jsonl", "RUN")
    agent, session = _Scripted(agent_replies), _Session(submit_answers)
    judge = judge if judge is not None else _Scripted(judge_replies)
    messages = [{"role": "system", "content": "SYSTEM"}, {"role": "user", "content": "TASK"}]
    totals = {"turns": 0, "tool_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}
    reason = anyio.run(harness.harness_loop, session, agent, messages, [], spec, log, totals,
                       rx_run._loop, judge, list(moments))  # fmt: skip
    log.close()
    lines = [
        json.loads(x)
        for x in (tmp_path / "RUN" / "agent.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    return reason, agent, judge, session, lines, messages, totals


SUBMIT = ("submit_commentary", {"game": "g", "ply": 3, "agent": {"name": "t"}, "sentences": []})


def test_a_moment_passed_at_once_goes_to_submit(tmp_path):
    reason, _agent, judge, session, lines, messages, totals = _run_stages(
        tmp_path,
        [_reply("FACTS AND CAUSE"), _reply(calls=[SUBMIT]), _reply("submitted")],
        [_verdict(True)],
    )
    assert reason == "done"
    assert [n for n, _ in session.calls] == ["submit_commentary"]
    users = [m["content"] for m in messages if m["role"] == "user"]
    assert users[0] == "TASK" and users[1].startswith("[2.exd5 — 사실과 결정적 원인]")
    assert users[2].startswith("[2.exd5 — 제출] 판정을 통과했어")
    # §4: the first request line logs the system message and the task
    first = next(x for x in lines if x["type"] == "request")
    assert [m["content"] for m in first["messages"][:2]] == ["SYSTEM", "TASK"]
    # §3: the judge reads the header and the reply, nothing else
    [request] = judge.requests
    assert request[0]["content"] == harness.JUDGE_SYSTEM
    assert request[1]["content"] == "장면: 2.exd5\n\n## 해설자의 답\nFACTS AND CAUSE"
    assert totals["judge_cost"] == pytest.approx(0.001) and totals["cost"] == pytest.approx(0.004)
    assert [x["attempt"] for x in lines if x["type"] == "judge"] == [0]


def test_a_failed_verdict_sends_its_problems_back_then_passes(tmp_path):
    _, _agent, judge, _, lines, messages, _ = _run_stages(
        tmp_path,
        [_reply("FIRST"), _reply("SECOND"), _reply(calls=[SUBMIT]), _reply("submitted")],
        [_verdict(False, ["결과가 없다"]), _verdict(True)],
    )
    users = [m["content"] for m in messages if m["role"] == "user"]
    assert users[2].startswith("[2.exd5 — 판정: 통과하지 못함] 이유: 결과가 없다")
    assert judge.requests[1][1]["content"].endswith("SECOND")
    assert [x["attempt"] for x in lines if x["type"] == "judge"] == [0, 1]


def test_three_failed_verdicts_go_to_submit_and_say_so(tmp_path):
    _, _, judge, session, _, messages, _ = _run_stages(
        tmp_path,
        [_reply("A"), _reply("B"), _reply("C"), _reply(calls=[SUBMIT]), _reply("submitted")],
        [_verdict(False, ["x"])] * 3,
    )
    assert len(judge.requests) == 3 and [n for n, _ in session.calls] == ["submit_commentary"]
    assert "세 번 통과하지 못했지만" in [m["content"] for m in messages if m["role"] == "user"][-1]


def test_an_unreadable_verdict_is_asked_again_once_then_never_blocks(tmp_path):
    _, _, judge, session, lines, _, _ = _run_stages(
        tmp_path,
        [_reply("A"), _reply(calls=[SUBMIT]), _reply("submitted")],
        [_reply("not json"), _reply("still not")],
    )
    assert len(judge.requests) == 2 and session.calls
    [verdict] = [x["verdict"] for x in lines if x["type"] == "judge"]
    assert verdict["unreadable"] is True


def test_a_submit_in_the_facts_phase_is_held_and_logged(tmp_path):
    _, _, _, session, lines, _, _ = _run_stages(
        tmp_path,
        [_reply(calls=[SUBMIT]), _reply("FACTS"), _reply(calls=[SUBMIT]), _reply("submitted")],
        [_verdict(True)],
    )
    assert [n for n, _ in session.calls] == ["submit_commentary"]  # only the submit step's
    [held] = [x for x in lines if x["type"] == "tool_unsent"]
    assert held["reason"] == "harness_gate" and held["tool_call_id"] == "c0"


def test_arm_a_is_unchanged_and_h_records_its_versions():
    a = rx_run.RunSpec(arm="A", set_name="validation", game="g", pgn=GAME, moments=[3],
                       base=None, records=None, work=None)  # fmt: skip
    assert rx_run._harness_info(a) == {}
    assert rx_run._harness_info(a.__class__(**{**vars(a), "arm": "H"})) == {
        "harness": "harness_v2",
        "harness_judge": "harness_judge_v1",
        "harness_retries": 2,
    }
    assert "H" in rx_run.ARMS and rx_run.TASK_BY_ID.startswith(
        "이 대국은 Calliope에 이미 열려 있어."
    )


# -- the pooled report and the decision (§6, C1) ---------------------------------------------------------


def _v(decisive, wrong=0, sentences=5):
    return {"decisive": decisive, "wrong": wrong, "sentences": sentences, "score": 4.0,
            "fetched": None}  # fmt: skip


def _cells(per_set):
    """{(set, game, ply): {arm: [values]}} from {set: {game: [(h_decisive, a_decisive)]}}."""

    cells = {}
    for set_name, games in per_set.items():
        for game, moments in games.items():
            for ply, (h, a) in enumerate(moments, start=1):
                cells[(set_name, game, ply)] = {"H": [_v(h)], "A": [_v(a)]}
    return cells


def test_one_set_pools_to_its_own_value_and_games_stay_apart_by_set():
    one = _cells({"train": {"g1": [(1.0, 0.0), (1.0, 1.0)], "g2": [(0.0, 0.0)]}})
    alone = rx_report.paired(one, "train", "H", "A", "decisive")
    pooled = rx_report.paired(one, None, "H", "A", "decisive")
    assert pooled["diff"] == alone["diff"] and pooled["moments"] == alone["moments"] == 3
    both = _cells({"train": {"g1": [(1.0, 0.0)]}, "validation": {"g1": [(0.0, 0.0)]}})
    pooled = rx_report.paired(both, None, "H", "A", "decisive")
    assert pooled["games"] == 2 and pooled["moments"] == 2  # g1 of each set is its own game
    assert set(pooled["by_moment"]) == {"train/g1-1", "validation/g1-1"}


def _entry(diff, lo, hi, wrong_hi=1.0):
    return {"decisive": {"diff": diff, "lo": lo, "hi": hi},
            "wrong": {"diff": 0.0, "lo": -1.0, "hi": wrong_hi}}  # fmt: skip


def _decide(pooled, per_set, worst=None, failed=(0, 0), missing=(0, 0)):
    worst = worst if worst is not None else pooled
    return rx_report.decision(pooled, per_set, worst, {"failed": failed[0]}, {"failed": failed[1]},
                              missing[0], missing[1])  # fmt: skip


def test_the_decision_reads_the_pool_and_a_set_clearly_worse_blocks_it():
    adopt = _decide(_entry(0.2, 0.05, 0.3), {"train": _entry(0.25, 0, 0),
                                             "validation": _entry(0.1, 0, 0)})  # fmt: skip
    assert adopt["adopted"] and adopt["quality_gate_passed"] and not adopt["sets_disagree"]
    one_set_worse = _decide(
        _entry(0.2, 0.05, 0.3), {"train": _entry(0.4, 0, 0), "validation": _entry(-0.15, 0, 0)}
    )
    assert not one_set_worse["adopted"] and one_set_worse["sets_disagree"]
    assert any("validation" in r for r in one_set_worse["reasons"])
    pool_short = _decide(
        _entry(0.05, -0.1, 0.2), {"train": _entry(0.3, 0, 0), "validation": _entry(-0.05, 0, 0)}
    )
    assert not pool_short["adopted"]
    wrong_up = _decide(_entry(0.2, 0.05, 0.3, wrong_hi=2.5), {"train": _entry(0.2, 0, 0)})
    assert not wrong_up["adopted"]


def test_quality_alone_does_not_adopt_failures_missing_commentary_or_the_worst_case_do_not():
    """HS review F3: `adopted` needs the runs too; the quality gate alone is reported apart."""

    good = (_entry(0.2, 0.05, 0.3), {"train": _entry(0.2, 0, 0), "validation": _entry(0.2, 0, 0)})
    failures = _decide(*good, failed=(5, 0))  # H: 5 of its runs not judged, A: none
    assert failures["quality_gate_passed"] and not failures["adopted"]
    assert any("failed runs 5 against 0" in r for r in failures["reasons"])
    missing = _decide(*good, missing=(4, 1))
    assert missing["quality_gate_passed"] and not missing["adopted"]
    worst = _decide(*good, worst=_entry(0.08, -0.02, 0.2))
    assert worst["quality_gate_passed"] and not worst["adopted"]
    assert any("worst case" in r for r in worst["reasons"])


def test_the_ledger_counts_every_started_run_and_how_it_ended():
    rows = [{"arm": "H", "result": {"run": "r1", "reason": "done"}},
            {"arm": "H", "result": {"run": "r2", "reason": "error"}},
            {"arm": "H", "result": None},
            {"arm": "A", "result": {"run": "r3", "reason": "tokens"}}]  # fmt: skip
    out = rx_report.ledger(rows, {"r2"})
    assert out["H"] == {"started": 3, "judged": 1, "failed": 2,
                        "ends": {"done": 1, "error": 1, "no result": 1}}  # fmt: skip
    assert out["A"] == {"started": 1, "judged": 1, "failed": 0, "ends": {"tokens": 1}}


def test_the_gate_holds_a_submit_to_another_game():
    """HS review F1: the same ply of another game is held, by the call's `game` or an item's."""

    gate, session, log = _gated("submit", 3)
    assert _send(gate, {"game": "other", "ply": 3}).isError
    assert _send(gate, {"game": "g", "items": [{"ply": 3, "game": "other"}]}).isError
    assert _send(gate, {"ply": 3}).isError  # no game named
    assert session.calls == [] and len(log.lines) == 3
    assert not _send(gate, {"game": "g", "items": [{"ply": 3, "game": "g"}]}).isError


def test_the_judges_tokens_count_against_the_runs_bound(tmp_path):
    """HS review F2: the judge's tokens join the agent's in the bound `_loop` checks."""

    big = rx_model.Reply(message={"content": json.dumps({"pass": True, "problems": []})},
                         usage={"input_tokens": 500, "output_tokens": 0, "cost": 0.0},
                         body_fields=[])  # fmt: skip
    reason, _, _, session, _, _, totals = _run_stages(
        tmp_path, [_reply("FACTS"), _reply(calls=[SUBMIT]), _reply("done")], [big], tokens=400
    )
    assert reason == "tokens" and session.calls == []  # the submit step never ran
    assert totals["input_tokens"] == 10 + 500 and totals["judge_tokens"] == 500


def test_a_slow_judge_is_abandoned_at_the_runs_bound(tmp_path):
    """HS review N1: the run's wall-clock bound cancels a judge request still waiting."""

    import time

    class Slow:
        def complete(self, messages, tools):
            time.sleep(5)
            return _verdict(True)

    started = time.monotonic()

    def run():
        async def bounded():
            with anyio.fail_after(0.5):
                await harness.harness_loop(
                    _Session(), _Scripted([_reply("FACTS")]), [{"role": "user", "content": "T"}],
                    [], rx_run.RunSpec(arm="H", set_name="v", game="g", pgn=GAME, moments=[3],
                                       base=tmp_path, records=tmp_path, work=tmp_path,
                                       game_id="g"),
                    rx_run.AgentLog(tmp_path / "S" / "agent.jsonl", "S"),
                    {"turns": 0, "tool_calls": 0, "input_tokens": 0, "output_tokens": 0,
                     "cost": 0.0},
                    rx_run._loop, Slow(), [(3, "2.exd5")],
                )  # fmt: skip

        anyio.run(bounded)

    with pytest.raises(TimeoutError):
        run()
    assert time.monotonic() - started < 3  # not the judge's 5 s


def test_a_failure_without_a_log_counts_in_the_worst_case_as_one_with_one():
    """HS review R1: A and H each fail once; H's failure left no result (no run, no log). Both
    count, at every fixed moment of their game from the manifest, as unexplained."""

    cells = {("train", "g1", 4): {"H": [_v(1.0)], "A": [_v(1.0)]}}
    started = [{"arm": "A", "set": "train", "game": "g1", "result": {"run": "a-fail", "reason": "error"}},
               {"arm": "H", "set": "train", "game": "g1", "result": None},
               {"arm": "H", "set": "train", "game": "g1", "result": {"run": "h-ok", "reason": "done"}}]  # fmt: skip
    roles = {("train", "g1", 4): ["decisive"], ("train", "g1", 9): ["decisive"]}
    worst = rx_report.worst_case(cells, started, {"a-fail"}, roles, lambda s, g: [4, 9])
    assert [v["decisive"] for v in worst[("train", "g1", 4)]["H"]] == [
        1.0,
        0.0,
    ]  # the judged, the failed
    assert [v["decisive"] for v in worst[("train", "g1", 4)]["A"]] == [1.0, 0.0]
    assert [v["decisive"] for v in worst[("train", "g1", 9)]["H"]] == [0.0]  # a moment never judged
    assert cells[("train", "g1", 4)]["H"] == [_v(1.0)]  # the judged cells untouched
    led = rx_report.ledger(started, {"a-fail"})
    assert led["H"]["failed"] == led["A"]["failed"] == 1


def test_no_judge_request_once_the_agent_used_the_budget(tmp_path):
    """HS review R2: the agent's last reply reaches the bound; the judge is not asked."""

    reason, _, judge, session, _, _, _ = _run_stages(
        tmp_path, [_reply("FACTS")], [_verdict(True)], tokens=15
    )
    assert reason == "tokens" and judge.requests == [] and session.calls == []


def test_the_judges_re_ask_waits_for_the_budget(tmp_path):
    """HS review R2: an unreadable first answer that used the rest is not asked again."""

    first = rx_model.Reply(message={"content": "not json"},
                           usage={"input_tokens": 300, "output_tokens": 0, "cost": 0.0},
                           body_fields=[])  # fmt: skip
    reason, _, judge, _, lines, _, _ = _run_stages(
        tmp_path, [_reply("FACTS"), _reply("x")], [first, _verdict(True)], tokens=200
    )
    assert len(judge.requests) == 1 and reason == "tokens"
    [verdict] = [x["verdict"] for x in lines if x["type"] == "judge"]
    assert verdict["budget"] is True and verdict["unreadable"] is True


# -- HS rev. 4: the submit step ends with the moment accepted (A2), JSON-string arguments (A3) ---------


def test_the_submit_step_re_asks_until_the_moment_is_accepted(tmp_path):
    """A2: the agent answers in text at the submit step (the 185922072242 run of §8); the runner asks
    again and the moment is submitted."""

    _, _, _, session, lines, messages, _ = _run_stages(
        tmp_path,
        [_reply("FACTS"), _reply("이 장면은 제출할 필요가 없어 보여."), _reply(calls=[SUBMIT]),
         _reply("submitted")],
        [_verdict(True)],
    )  # fmt: skip
    assert [n for n, _ in session.calls] == ["submit_commentary"]
    assert any(
        m["content"].startswith("[2.exd5 — 제출 안 됨]") for m in messages if m["role"] == "user"
    )
    assert [x["ask"] for x in lines if x.get("stage") == "submit_again"] == [1]
    assert not [x for x in lines if x.get("stage") == "submit_missing"]


def test_a_refused_submission_is_not_a_submission(tmp_path):
    _, _, _, session, lines, _, _ = _run_stages(
        tmp_path,
        [_reply("FACTS"), _reply(calls=[SUBMIT]), _reply("done?"), _reply(calls=[SUBMIT]),
         _reply("submitted")],
        [_verdict(True)],
        submit_answers=[{"accepted": False, "violations": [{"rule": "S2"}]}, {"accepted": True}],
    )  # fmt: skip
    assert len(session.calls) == 2
    assert [x["ask"] for x in lines if x.get("stage") == "submit_again"] == [1]


def test_a_moment_never_submitted_is_logged_after_the_re_asks(tmp_path):
    _, agent, _, session, lines, _, _ = _run_stages(
        tmp_path,
        [_reply("FACTS")] + [_reply("text only")] * (1 + harness.SUBMIT_ASKS),
        [_verdict(True)],
    )
    assert session.calls == [] and agent.replies == []
    [missing] = [x for x in lines if x.get("stage") == "submit_missing"]
    assert missing["ply"] == 3 and missing["asks"] == harness.SUBMIT_ASKS


def test_the_gate_reads_json_string_arguments_as_the_server_does():
    """A3: `items` (or a `position`) given as a JSON string is read as the server's
    `pre_parse_json` reads it (the fresh ply-56 run of §8)."""

    gate, session, log = _gated("submit", 3)
    item = {"ply": 3, "sentences": []}
    assert not _send(gate, {"game": "g", "items": json.dumps([item])}).isError
    position = json.dumps({"ply": 3, "at": "before"})
    assert not _send(gate, {"game": "g", "position": position, "move": "exd5"}).isError
    assert not _send(gate, {"game": "g", "items": [{"position": position, "move": "exd5"}]}).isError
    assert len(session.calls) == 3 and log.lines == []
    assert _send(
        gate, {"game": "g", "items": json.dumps([{"ply": 4}])}
    ).isError  # still another ply
    assert session.calls[0][1]["items"] == json.dumps([item])  # sent on as the agent wrote it


def test_accepted_reads_both_answers():
    assert harness.accepted(json.dumps({"accepted": True}))
    assert not harness.accepted(json.dumps({"accepted": False}))
    assert harness.accepted(json.dumps({"items": [{"index": 0, "outcome": "duplicate"}]}))
    assert not harness.accepted(json.dumps({"items": [{"index": 0, "outcome": "refused"}]}))
    assert not harness.accepted("not json")
