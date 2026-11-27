"""Harness rev. 19 (the change log, "a writing turn of its own"): a tier-2 moment is written in a
conversation of its own holding the facts answer and the checked claims as code writes them, with
`detail` and `submit_commentary` only; the server allows a material proposition's standings (S3)
when the run sets `CALLIOPE_STANDING_NUMBERS`."""

from __future__ import annotations

import json
from types import SimpleNamespace

import chess
import pytest
from test_tb_harness import _Model
from test_wg import LINES, _batch, _reply, _run

from calliope.agent import propositions
from tools.rx import frames, harness
from tools.rx import guard as rx_guard
from tools.rx import run as rx_run


@pytest.fixture(autouse=True)
def _scripted_counts(monkeypatch):
    """`_Model`'s counts are scripted, its usage is not: the guard's bound (on by default) would
    skip them, so it is off here."""

    monkeypatch.setenv(rx_guard.BOUND_ENV, "0")


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    async def no_problems(session, game_id, claims, log):
        return [], [], []

    monkeypatch.setattr(harness, "check_claims", no_problems)
    monkeypatch.setattr(frames, "refs_needed", lambda args: set())
    monkeypatch.setattr(frames, "check", lambda args, records, version=None: {
        "held": [], "uncheckable": [], "ambiguous": [], "search_numbers": 0, "version": "t"})  # fmt: skip


class _Tools(_Model):
    """Records the tools each request offered."""

    def __init__(self, replies, sizes=(1_000,)):
        super().__init__(replies, sizes)
        self.offered = []

    def complete(self, messages, tools, tool_choice=None):
        self.offered.append([t["function"]["name"] for t in tools or []])
        return super().complete(messages, tools, tool_choice)


def _submit3():
    return ("submit_commentary", {"game": "g", "ply": 3, "agent": {"name": "t"}, "sentences": [
        {"text": "해설", "class": "interpretation", "cites": []}]})  # fmt: skip


def _agent(writer_calls=()):
    return _Tools([_reply(calls=[("explore", {"game": "g", "ply": 3})]), _reply("FACTS-ANSWER"),
                   *[_reply(calls=[c]) for c in writer_calls],
                   _reply(calls=[_submit3()]), _reply("ok"), _reply(calls=[_batch(6, 8)])])  # fmt: skip


def test_rev_19_writes_in_a_conversation_of_its_own(tmp_path) -> None:
    agent = _agent()
    reason, server, lines = _run(tmp_path, agent, LINES, revision=19)
    assert reason == "done"
    writer = agent.requests[2][0]
    assert [m["role"] for m in writer] == ["system", "user", "user"]  # no tool answers
    assert "[2.exd5 — 쓰기]" in writer[-1]["content"] and "FACTS-ANSWER" in writer[-1]["content"]
    assert "(확인된 주장 없음)" in writer[-1]["content"]
    assert "[이 수의 ply 결과]" in writer[-1]["content"]
    assert any(x["type"] == "harness_call" and x.get("tool") == "ply" and x.get("ply") == 3
               for x in lines)  # the moment's digest, fetched by the harness  # fmt: skip
    assert agent.offered[2] == ["detail", "submit_commentary"]
    assert "explore" in agent.offered[0]  # the facts step keeps every tool
    assert next(x for x in lines if x["type"] == "writer_start")["ply"] == 3
    assert any(n == "submit_commentary" and a.get("ply") == 3 for n, a in server.calls)


def test_the_writer_is_refused_a_tool_it_is_not_offered(tmp_path) -> None:
    agent = _agent(writer_calls=[("explore", {"game": "g", "ply": 3})])
    reason, server, lines = _run(tmp_path, agent, LINES, revision=19)
    assert reason == "done"
    refused = [x for x in lines if x["type"] == "tool_unsent" and x.get("writer")]
    assert [x["tool"] for x in refused] == ["explore"]
    assert [n for n, _ in server.calls].count("explore") == 1  # the facts step's only


def test_a_compaction_in_the_writer_offers_the_writers_tools(tmp_path) -> None:
    # the 8-game batch (2026-11-15): compaction sent every tool, and the Claude API refused the
    # writer's thinking blocks, bound to the tools they were made with
    agent = _Tools([_reply(calls=[("explore", {"game": "g", "ply": 3})]), _reply("FACTS-ANSWER"),
                    _reply("NOTES"), _reply(calls=[_submit3()]), _reply("ok"),
                    _reply(calls=[_batch(6, 8)])],
                   sizes=[1_000, 1_000, 85_000, 1_000, 100, 1_000])  # fmt: skip
    reason, _, lines = _run(tmp_path, agent, LINES, revision=19)
    assert reason == "done"
    compact_request, choice = agent.requests[2]
    assert choice == "none" and "[대화 정리]" in compact_request[-1]["content"]
    assert agent.offered[2] == ["detail", "submit_commentary"]
    assert agent.offered[3] == ["detail", "submit_commentary"]  # the restarted writer
    assert any(x["type"] == "restart" for x in lines)


def test_rev_18_submits_in_the_facts_conversation(tmp_path) -> None:
    agent = _agent()
    _, _, lines = _run(tmp_path, agent, LINES, revision=18)
    submit = agent.requests[2][0]
    assert any(m["role"] == "tool" for m in submit) and "FACTS-ANSWER" not in submit[-1]["content"]
    assert agent.offered[2] == agent.offered[0]
    assert not [x for x in lines if x["type"] == "writer_start"]


def test_render_checked_names_standing_and_change_apart() -> None:
    checked = [
        {"n": 1, "claim": {"kind": "line_net", "ref": "x4.t", "side": "white", "value": -2},
         "record": {"moves": ["15...Bd3", "16.Qe3", "16...Bxf1", "17.Kxf1"],
                    "captured": {"by_white": ["black bishop f1"], "by_black": ["white rook f1"]},
                    "net": {"white": -2, "black": 2},
                    "standing": {"start": {"white_minus_black": 1}, "end": {"white_minus_black": -1},
                                 "leader_at_end": "black"}}},
        {"n": 2, "claim": {"kind": "defenders", "ref": "f1.t", "square": "b5"},
         "record": {"square": "b5", "piece": "black pawn b5", "attackers": [{"piece": "Nc3"}],
                    "defenders": []}},
        {"n": 3, "claim": {"kind": "better_for_mover", "ref": "k1.t"},
         "record": [{"move": "Rxd6", "rank": 1, "for_mover": "+0.04", "vs_played": "+2.70"},
                    {"move": "a5", "rank": 2, "for_mover": "+2.74", "vs_played": "+0.00"}]},
        {"n": 4, "claim": {"kind": "score", "ref": "s1.t", "favours": "neither"},
         "record": {"score": {"cp": 8}, "move": "Rxe5"}},
    ]  # fmt: skip
    text = harness.render_checked(checked).splitlines()
    assert "형세(백−흑): 시작 +1 → 끝 -1 (흑이 앞섬)" in text[0]
    assert "변화(시작 대비 얻고 잃은 양): 백 -2, 흑 +2" in text[0]
    assert "마지막 수 17.Kxf1" in text[0] and "흑이 잡은 것: white rook f1" in text[0]
    assert "공격자 Nc3; 수비자 없음" in text[1] and "언제 생겼는지는 말하지 않음" in text[1]
    assert "1. Rxd6 (+0.04" in text[2] and "2. a5" in text[2]
    assert "어느 쪽에도 기울지 않음" in text[3]


def test_standing_integers_only_when_the_run_sets_them(monkeypatch) -> None:
    board = chess.Board()
    for san in ("e4", "d5", "exd5"):
        board.push_san(san)
    fen, moves = board.fen(), ["d8d5", "b1c3", "d5a5"]  # 3...Qxd5 4.Nc3 Qa5
    monkeypatch.delenv(propositions.STANDING_NUMBERS, raising=False)
    assert propositions.standing_integers(fen, moves, 0, 3) == set()
    monkeypatch.setenv(propositions.STANDING_NUMBERS, "1")
    assert propositions.standing_integers(fen, moves, 0, 3) == {1, 0}  # White +1, then level
    assert propositions.standing_integers(fen, moves, 1, 2) == {0}


def test_revision_19_is_revision_18_with_the_writer() -> None:
    assert harness.VERSIONS[19][1:] == harness.VERSIONS[18][1:]
    assert harness.VERSIONS[19][0] == "harness_v7" and harness.FRAMES[19] == harness.FRAMES[18]
    assert harness.guide_of(19) == harness.guide_of(18)
    assert all(19 in t for t in (harness.TIERED, harness.LEAN_TIER1, harness.SHORT_HANDLES,
                                 harness.COMPLETE_CITES, harness.REVIEWED, harness.PER_MOMENT,
                                 harness.TIER2_LEAN))  # fmt: skip
    v6, v7 = harness.ALL_MESSAGES[18], harness.ALL_MESSAGES[19]
    assert set(v7) - set(v6) == {"write"} and all(v7[k] == v6[k] for k in v6)
    assert all(f"{{{k}}}" in v7["write"] for k in ("facts", "checked", "digest"))
    info = rx_run._harness_info(SimpleNamespace(arm="H", harness_revision=19, harness_guide=None))
    assert info["harness_writer"] is True and info["server_standing_numbers"] is True
    old = rx_run._harness_info(SimpleNamespace(arm="H", harness_revision=18, harness_guide=None))
    assert old["harness_writer"] is False and old["server_standing_numbers"] is False
    json.dumps(info)
