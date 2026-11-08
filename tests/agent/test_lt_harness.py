"""LT (agent-lt-design.md §5): harness rev. 5 — typed claims (H1), the checker by code against the
records (H2, review F3), rubric v3's input (H3), the retry from the check (H4), the sentence check at
submission and its states (H5, review F3, re-review R3); the run checker pairs the harness's own
`detail` calls."""

from __future__ import annotations

import json
from types import SimpleNamespace

import anyio
from agent_helpers import GAME

from tools.rx import check as rx_check
from tools.rx import harness
from tools.rx import model as rx_model
from tools.rx import run as rx_run

LINE = {  # an explored line: 2.exd5 Qxd5 from the position before ply 3 (agent_helpers.GAME)
    "start": {"fen": "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"},
    "end": {"fen": "rnb1kbnr/ppp1pppp/8/3q4/8/8/PPPP1PPP/RNBQKBNR w KQkq - 0 3"},
    "plies": [
        {"ply": 1, "material_balance_white": 1, "move": {
            "san": "exd5", "mover": "white", "piece_type": "pawn", "from_square": "e4",
            "to_square": "d5", "castling": None, "gives_check": False, "gives_mate": False,
            "piece": {"piece": "pawn", "color": "white", "origin": "e2", "square": "d5"},
            "events": [{"piece": {"color": "black", "origin": "d7"}, "piece_type": "pawn",
                        "square": "d5", "en_passant": False}]}},
        {"ply": 2, "material_balance_white": 0, "move": {
            "san": "Qxd5", "mover": "black", "piece_type": "queen", "from_square": "d8",
            "to_square": "d5", "castling": None, "gives_check": False, "gives_mate": False,
            "piece": {"piece": "queen", "color": "black", "origin": "d8", "square": "d5"},
            "events": [{"piece": {"color": "white", "origin": "e2"}, "piece_type": "pawn",
                        "square": "d5", "en_passant": False}]}},
    ],
}  # fmt: skip
PIECES = {"pieces": [
    {"square": "f7", "color": "black", "piece_type": "pawn", "attackers": [{"square": "d5"}],
     "defenders": [{"square": "g8"}, {"square": "d6"}], "attacks": {"empty": []},
     "identity": {"color": "black", "origin": "f7"}},
    {"square": "g8", "color": "black", "piece_type": "king", "identity": {"color": "black", "origin": "e8"}},
    {"square": "d6", "color": "black", "piece_type": "knight", "identity": {"color": "black", "origin": "b8"}},
    {"square": "d5", "color": "white", "piece_type": "bishop", "legal_destinations": ["f7"],
     "identity": {"color": "white", "origin": "f1"}},
]}  # fmt: skip
RANKING = {"ranking": {"for": "white", "moves": [
    {"move": "17.Qe1", "rank": 1, "for_mover": {"cp": -679}},
    {"move": "17.Qxe3", "rank": 2, "for_mover": {"cp": -759}},
]}}  # fmt: skip
RECORDS = {
    "x1.t": ("explored_line", LINE),
    "f1.t": ("fact", PIECES),
    "k1.t": ("comparison", RANKING),
    "s1.t": ("search_line", {"score": {"cp": -250}, "move": {"san": "Qe1"}}),
}
GOOD = [
    {"kind": "line_net", "ref": "x1.t", "side": "white", "value": 0},
    {"kind": "line_capture", "ref": "x1.t", "by": "black", "piece": "pawn", "square": "d5"},
    {"kind": "piece_at_end", "ref": "x1.t", "side": "black", "piece": "queen", "square": "d5"},
    {"kind": "defenders", "ref": "f1.t", "square": "f7", "value": ["Kg8", "Nd6"]},
    {"kind": "better_for_mover", "ref": "k1.t", "move": "Qe1", "than": "17.Qxe3"},
    {"kind": "score", "ref": "s1.t", "favours": "black"},
]


def test_each_claim_kind_agrees_with_its_record() -> None:
    for claim in GOOD:
        kind, item = RECORDS[claim["ref"]]
        assert harness.check_claim(claim, kind, item)[0] == "agrees", claim


def test_claims_that_disagree_or_have_no_record() -> None:
    """The cases of LT-D §0.2: only the king defends f7; Black five points ahead after a trade;
    17.Qxe3 better than 17.Qe1 for White."""

    wrong = [
        ({"kind": "defenders", "ref": "f1.t", "square": "f7", "value": ["Kg8"]}, "disagrees"),
        ({"kind": "line_net", "ref": "x1.t", "side": "black", "value": -5}, "disagrees"),
        ({"kind": "better_for_mover", "ref": "k1.t", "move": "Qxe3", "than": "Qe1"}, "disagrees"),
        (
            {
                "kind": "piece_at_end",
                "ref": "x1.t",
                "side": "black",
                "piece": "bishop",
                "square": "g3",
            },
            "disagrees",
        ),
        ({"kind": "score", "ref": "s1.t", "favours": "white"}, "disagrees"),
        ({"kind": "better_for_mover", "ref": "k1.t", "move": "Qd1", "than": "Qe1"}, "unbacked"),
        ({"kind": "line_net", "ref": "f1.t", "side": "black", "value": 0}, "unbacked"),
        ({"kind": "mood", "ref": "x1.t"}, "unbacked"),
    ]
    for claim, expected in wrong:
        kind, item = RECORDS[claim["ref"]]
        assert harness.check_claim(claim, kind, item)[0] == expected, claim
    _verdict, held = harness.check_claim(wrong[0][0], *RECORDS["f1.t"])
    assert held == ["kg8", "nd6"]  # the record's value goes back to the agent


def test_the_claims_block_is_read_fenced_or_not() -> None:
    block = json.dumps({"claims": GOOD[:1]})
    assert harness.claims_of(f"사실…\n```json\n{block}\n```") == GOOD[:1]
    assert harness.claims_of(f"사실… {block}") == GOOD[:1]
    assert harness.claims_of("사실만 있음") is None
    assert harness.claims_of('```json\n{"claims": "x"}\n```') is None


# -- the loop, on a scripted session and models --------------------------------------------------


class _Log:
    def __init__(self):
        self.lines = []

    def write(self, line):
        self.lines.append(line)


class _Session:
    """`detail` answers from RECORDS; `submit_commentary` is accepted."""

    def __init__(self):
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "detail":
            kind, item = RECORDS.get(arguments["ref"], (None, None))
            if kind is None:
                text, error = "no handle", True
            else:
                text, error = (
                    json.dumps({"ref": arguments["ref"], "kind": kind, "item": item}),
                    False,
                )
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], isError=error)
        text = json.dumps({"accepted": True}) if name == "submit_commentary" else "{}"
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], isError=False)


class _Scripted:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def complete(self, messages, tools):
        self.requests.append([dict(m) for m in messages])
        return self.replies.pop(0)


def _reply(content=None, calls=()):
    message = {"content": content}
    if calls:
        message["tool_calls"] = [{"id": f"c{i}", "type": "function",
                                  "function": {"name": n, "arguments": json.dumps(a)}}
                                 for i, (n, a) in enumerate(calls)]  # fmt: skip
    return rx_model.Reply(message=message, usage={"input_tokens": 10, "output_tokens": 5,
                                                  "cost": 0.001}, body_fields=[])  # fmt: skip


def _facts(claims):
    return _reply("사실과 원인\n```json\n" + json.dumps({"claims": claims}) + "\n```")


def _submit(text="f7은 Kg8과 Nd6가 지킨다.", items=False):
    sentence = {"text": text}
    if items:
        arguments = {"game": "g", "agent": {"name": "t"},
                     "items": json.dumps([{"ply": 3, "sentences": [sentence]}])}  # fmt: skip
    else:
        arguments = {"game": "g", "ply": 3, "agent": {"name": "t"}, "sentences": [sentence]}
    return _reply(calls=[("submit_commentary", arguments)])


def _verdict(passed, problems=()):
    return _reply(json.dumps({"pass": passed, "problems": list(problems)}))


def _sentences(*verdicts):
    return _reply(json.dumps({"sentences": [{"n": i + 1, **v} for i, v in enumerate(verdicts)]}))


def _run(tmp_path, agent_replies, judge_replies):
    spec = rx_run.RunSpec(arm="H", set_name="validation", game="g", pgn=GAME, moments=[3],
                          base=tmp_path, records=tmp_path, work=tmp_path, game_id="g")  # fmt: skip
    log = rx_run.AgentLog(tmp_path / "RUN" / "agent.jsonl", "RUN")
    agent, judge, session = _Scripted(agent_replies), _Scripted(judge_replies), _Session()
    messages = [{"role": "system", "content": "SYSTEM"}, {"role": "user", "content": "TASK"}]
    totals = {"turns": 0, "tool_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}
    reason = anyio.run(harness.harness_loop, session, agent, messages, [], spec, log, totals,
                       rx_run._loop, judge, [(3, "2.exd5")])  # fmt: skip
    log.close()
    lines = [json.loads(x) for x in (tmp_path / "RUN" / "agent.jsonl").read_text(
        encoding="utf-8").splitlines()]  # fmt: skip
    return reason, judge, session, lines, messages, totals


def test_checked_claims_reach_the_judge_and_the_sentence_check(tmp_path) -> None:
    reason, judge, _session, lines, messages, totals = _run(
        tmp_path,
        [_facts(GOOD[3:4]), _submit(), _reply("submitted")],
        [_verdict(True), _sentences({"verdict": "ok"})],
    )
    assert reason == "done"
    [check] = [x for x in lines if x.get("stage") == "check"]
    assert check["problems"] == [] and check["results"][0]["result"] == "agrees"
    judge_request, sentence_request = judge.requests
    assert judge_request[0]["content"] == harness.JUDGES[7]
    assert "## 확인된 주장과 기록" in judge_request[1]["content"]
    assert '"Kg8"' in judge_request[1]["content"]
    assert sentence_request[0]["content"] == harness.SENTENCE_SYSTEMS[6]
    assert "f7은 Kg8과 Nd6가 지킨다." in sentence_request[1]["content"]
    [state] = [x for x in lines if x.get("stage") == "sentence_state"]
    assert state["state"] == "passed"
    assert [x["tool"] for x in lines if x["type"] == "harness_call"] == ["detail"]
    assert totals["judge_cost"] == totals["cost"] - 0.003  # three agent requests, the rest judged
    # the harness's own call does not go to the agent: no tool message for it
    assert not any(m.get("role") == "tool" and "f1.t" in str(m.get("content")) for m in messages)


def test_a_claim_that_disagrees_goes_back_before_the_judge(tmp_path) -> None:
    wrong = [{"kind": "defenders", "ref": "f1.t", "square": "f7", "value": ["Kg8"]}]
    reason, judge, _session, lines, messages, _ = _run(
        tmp_path,
        [_facts(wrong), _facts(GOOD[3:4]), _submit(), _reply("submitted")],
        [_verdict(True), _sentences({"verdict": "ok"})],
    )
    assert reason == "done"
    checks = [x for x in lines if x.get("stage") == "check"]
    assert checks[0]["problems"] and not checks[1]["problems"]
    users = [m["content"] for m in messages if m["role"] == "user"]
    assert users[2].startswith("[2.exd5 — 주장 확인: 기록과 다름]") and "nd6" in users[2]
    assert len(judge.requests) == 2  # the judge only after the check passed, then the sentences


def test_a_reply_without_a_claims_block_goes_back(tmp_path) -> None:
    _reason, _judge, _, lines, _messages, _ = _run(
        tmp_path,
        [_reply("사실만"), _facts(GOOD[:1]), _submit("백이 앞선다."), _reply("submitted")],
        [_verdict(True), _sentences({"verdict": "ok"})],
    )
    first = next(x for x in lines if x.get("stage") == "check")
    assert first["problems"] == [harness.MESSAGES_NO_CLAIMS]


def test_a_contradicting_sentence_is_held_then_corrected(tmp_path) -> None:
    """H5: "only the king defends f7" under a checked claim [Kg8, Nd6] is held; the corrected
    submission passes."""

    reason, _judge, session, lines, messages, _ = _run(
        tmp_path,
        [_facts(GOOD[3:4]), _submit("f7은 킹만 지킨다."), _submit(), _reply("submitted")],
        [_verdict(True), _sentences({"verdict": "contradicts", "claim": 1, "why": "Nd6도 지킴"}),
         _sentences({"verdict": "ok"})],
    )  # fmt: skip
    assert reason == "done"
    held = [x for x in lines if x["type"] == "tool_unsent"]
    assert [h["reason"] for h in held] == ["sentence_check"]
    assert [n for n, _ in session.calls].count("submit_commentary") == 1
    tool_answers = [m["content"] for m in messages if m["role"] == "tool"]
    assert "[제출 보류: 문장 확인]" in tool_answers[0] and "Nd6도 지킴" in tool_answers[0]
    [state] = [x for x in lines if x.get("stage") == "sentence_state"]
    assert state == state | {"state": "passed", "holds": 1}


def test_two_holds_then_the_call_goes_unchecked(tmp_path) -> None:
    bad = {"verdict": "contradicts", "claim": 1}
    reason, _judge, session, lines, _, _ = _run(
        tmp_path,
        [_facts(GOOD[3:4]), _submit("x"), _submit("y"), _submit("z"), _reply("submitted")],
        [_verdict(True), _sentences(bad), _sentences(bad)],
    )
    assert reason == "done"
    assert [x["reason"] for x in lines if x["type"] == "tool_unsent"] == ["sentence_check"] * 2
    assert [n for n, _ in session.calls].count("submit_commentary") == 1
    [state] = [x for x in lines if x.get("stage") == "sentence_state"]
    assert state["state"] == "exhausted" and state["holds"] == 2


def test_an_unreadable_sentence_check_sends_the_call(tmp_path) -> None:
    _reason, _, session, lines, _, _ = _run(
        tmp_path,
        [_facts(GOOD[3:4]), _submit(), _reply("submitted")],
        [_verdict(True), _reply("?"), _reply("??")],
    )
    assert [n for n, _ in session.calls].count("submit_commentary") == 1
    [state] = [x for x in lines if x.get("stage") == "sentence_state"]
    assert state["state"] == "unreadable"


def test_json_string_items_are_checked_as_the_server_reads_them(tmp_path) -> None:
    """Re-review R3: `items` given as a JSON string."""

    _, judge, _, _lines, _, _ = _run(
        tmp_path,
        [_facts(GOOD[3:4]), _submit(items=True), _reply("submitted")],
        [_verdict(True), _sentences({"verdict": "ok"})],
    )
    assert "f7은 Kg8과 Nd6가 지킨다." in judge.requests[1][1]["content"]
    assert harness.sentences_of({"items": json.dumps([{"sentences": [{"text": "a"}]}])}) == ["a"]


def test_the_run_checker_pairs_the_harness_calls(tmp_path) -> None:
    run = tmp_path / "r"
    run.mkdir()
    agent = [{"seq": 1, "type": "start"},
             {"seq": 2, "type": "response", "message": {"tool_calls": [
                 {"id": "c0", "function": {"name": "explore"}}]}},
             {"seq": 3, "type": "harness_call", "tool": "detail", "ref": "x1.t"},
             {"seq": 4, "type": "end", "reason": "done"}]  # fmt: skip
    tools = [{"seq": 1, "type": "start"}, {"seq": 2, "type": "call", "call_id": 1, "tool": "explore"},
             {"seq": 3, "type": "call", "call_id": 2, "tool": "detail"}, {"seq": 4, "type": "end"}]  # fmt: skip
    (run / "agent.jsonl").write_text("\n".join(json.dumps(x) for x in agent), encoding="utf-8")
    (run / "tools.jsonl").write_text("\n".join(json.dumps(x) for x in tools), encoding="utf-8")
    assert rx_check.check(run)["whole"] is True


def test_the_harness_calls_are_left_out_of_the_metrics() -> None:
    agent = [{"type": "response", "message": {"tool_calls": [
                 {"id": "c0", "function": {"name": "explore"}}]}},
             {"type": "harness_call", "tool": "detail", "ref": "x1.t"}]  # fmt: skip
    tools = [{"type": "call", "call_id": 1, "tool": "explore"},
             {"type": "call", "call_id": 2, "tool": "detail"}]  # fmt: skip
    assert rx_check.harness_call_ids(agent, tools) == {2}
    assert rx_check.harness_call_ids(agent, tools[:1]) == set()  # unpaired: none


def test_a_tie_is_not_better_and_an_unranked_move_backs_nothing() -> None:
    """LT review F3: the scores, not the places."""

    tied = {"ranking": {"for": "white", "moves": [
        {"move": "17.Qe1", "rank": 1, "for_mover": {"cp": 0}},
        {"move": "17.Qxe3", "rank": 2, "for_mover": {"cp": 0}}],
        "unranked": [{"move": "17.Qd1", "for_mover": None}]}}  # fmt: skip
    claim = {"kind": "better_for_mover", "ref": "k2.t", "move": "Qe1", "than": "Qxe3"}
    assert harness.check_claim(claim, "comparison", tied)[0] == "disagrees"
    claim = {"kind": "better_for_mover", "ref": "k2.t", "move": "Qd1", "than": "Qe1"}
    assert harness.check_claim(claim, "comparison", tied)[0] == "unbacked"


def test_a_partial_or_malformed_sentence_check_is_never_a_pass() -> None:
    """LT review F2: every sentence 1..N exactly once, each verdict known; otherwise asked again,
    then unreadable."""

    sentences = ["a", "b", "c"]
    for bad in ({"sentences": [{"n": 1, "verdict": "ok"}]},  # partial
                {"sentences": [{"n": 1, "verdict": "ok"}, {"n": 1, "verdict": "ok"},
                               {"n": 2, "verdict": "ok"}]},  # duplicated, one missing
                {"sentences": [{"n": 1, "verdict": "ok"}, {"n": 2, "verdict": "ok"},
                               {"n": 4, "verdict": "ok"}]},  # misnumbered
                {"sentences": [{"n": 1, "verdict": "ok"}, {"n": 2, "verdict": "ok"},
                               {"n": 3, "verdict": "fine"}]}):  # an unknown verdict  # fmt: skip
        model = _Scripted([_reply(json.dumps(bad)), _reply(json.dumps(bad))])
        verdict, _ = harness.check_sentences(model, "S", sentences, [])
        assert verdict.get("unreadable") is True and len(model.requests) == 2, bad
    whole = {"sentences": [{"n": i, "verdict": "ok"} for i in (3, 1, 2)]}
    model = _Scripted([_reply(json.dumps(bad)), _reply(json.dumps(whole))])
    verdict, _ = harness.check_sentences(model, "S", sentences, [])
    assert verdict["bad"] == [] and len(verdict["sentences"]) == 3  # the re-ask's whole answer
    verdict, usage = harness.check_sentences(_Scripted([]), "S", [], [])
    assert verdict == {"sentences": [], "bad": []} and usage["cost"] == 0.0  # nothing to read


def test_the_sentence_check_v2_reads_scores_by_side_not_digits() -> None:
    """The LT pilot (A10): half the holds were score digits from another record (+7.15 against
    +7.16). Revision 6 asks the sentence check to compare a score's side and mate only."""

    assert harness.VERSIONS[6][2] == harness.VERSIONS[7][2] == "harness_sentences_v2"
    rubric = harness.SENTENCE_SYSTEMS[6]
    assert "+7.15와 +7.16" in rubric and "유리한 쪽" in rubric
    assert harness.SENTENCE_SYSTEMS[5] != rubric  # the pilot's runs keep theirs


def test_rev_7_holds_on_contradictions_only_and_records_the_unbacked(tmp_path) -> None:
    """A12: an `unbacked` sentence is recorded, not held; a contradiction still holds."""

    _, _, session, lines, _, _ = _run(
        tmp_path,
        [_facts(GOOD[3:4]), _submit("f7은 Kg8과 Nd6가 지킨다."), _reply("submitted")],
        [_verdict(True), _sentences({"verdict": "unbacked"})],
    )
    assert [x for x in lines if x["type"] == "tool_unsent"] == []
    assert [n for n, _ in session.calls].count("submit_commentary") == 1
    [check] = [x for x in lines if x["type"] == "sentences"]
    assert check["state"] == "passed" and check["unbacked"] == 1
    assert harness.HOLD_ON[7] == ("contradicts",) and "unbacked" in harness.HOLD_ON[6]
    assert "평가 숫자의 차이는 모순이 아니다" in harness.JUDGES[7]
