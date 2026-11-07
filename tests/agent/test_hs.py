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
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        text = json.dumps({"accepted": True}) if name == "submit_commentary" else "{}"
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], isError=False)


def _gated(phase, ply):
    log, session = _Log(), _Session()
    gate = harness.Gate(session, harness.Game(GAME), log)
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


def _run_stages(tmp_path, agent_replies, judge_replies, moments=((3, "2.exd5"),)):
    spec = rx_run.RunSpec(arm="H", set_name="validation", game="g", pgn=GAME, moments=[m for m, _ in moments],
                          base=tmp_path, records=tmp_path, work=tmp_path)  # fmt: skip
    log = rx_run.AgentLog(tmp_path / "RUN" / "agent.jsonl", "RUN")
    agent, judge, session = _Scripted(agent_replies), _Scripted(judge_replies), _Session()
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
        "harness": "harness_v1",
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


def test_the_decision_reads_the_pool_and_a_set_clearly_worse_blocks_it():
    adopt = rx_report.decision(_entry(0.2, 0.05, 0.3), {"train": _entry(0.25, 0, 0),
                                                        "validation": _entry(0.1, 0, 0)})  # fmt: skip
    assert adopt["adopted"] and not adopt["sets_disagree"]
    one_set_worse = rx_report.decision(
        _entry(0.2, 0.05, 0.3), {"train": _entry(0.4, 0, 0), "validation": _entry(-0.15, 0, 0)}
    )
    assert not one_set_worse["adopted"] and one_set_worse["sets_disagree"]
    assert any("validation" in r for r in one_set_worse["reasons"])
    pool_short = rx_report.decision(
        _entry(0.05, -0.1, 0.2), {"train": _entry(0.3, 0, 0), "validation": _entry(-0.05, 0, 0)}
    )
    assert not pool_short["adopted"]
    wrong_up = rx_report.decision(
        _entry(0.2, 0.05, 0.3, wrong_hi=2.5), {"train": _entry(0.2, 0, 0)}
    )
    assert not wrong_up["adopted"]
