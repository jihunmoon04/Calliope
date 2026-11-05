"""RX1-D: the run record's tools layer (§2), `evidence_identity` (§7), `rx_moments` (§3), the
min guide (§6), and the runner's checker and finals (RX0-D §4.4, §6.0)."""

from __future__ import annotations

import json
import os
import re

import anyio
import pytest
from agent_helpers import G1, GAME, session

from calliope.agent.build import guide, text
from calliope.agent.record import Recorder, identity, identity_fields, line_key
from calliope.agent.session import MOMENTS, _moments, _ranking, rx_moments

pytest.importorskip("mcp", reason="the MCP SDK is the optional group `agent`")

from mcp import Client

from calliope.agent.server import app_page, build_server
from tools.mcp.__main__ import VIEWER
from tools.rx.check import check, finals
from tools.rx.run import _refused_subjects, numbered

PAGE = app_page(VIEWER)
TOKEN = re.compile(r"\b([jcsbfx]\d+)\.[0-9a-f]{24}\b")


def _lines(recorder: Recorder) -> list[dict]:
    return [json.loads(x) for x in recorder.path.read_text(encoding="utf-8").splitlines()]


def _script(client):
    """One of each kind of call a run makes."""

    async def go():
        out = {}
        out["open"] = await client.call_tool("open_game", {"pgn": GAME})
        out["analyze"] = await client.call_tool("analyze_game", {"game": G1, "wait_seconds": 30})
        out["overview"] = await client.call_tool("game_overview", {"game": G1})
        out["ply"] = await client.call_tool("ply", {"game": G1, "ply": 3})
        out["judge"] = await client.call_tool(
            "judge_move", {"game": G1, "position": {"ply": 3, "at": "before"}, "move": "Nc3"}
        )
        out["definitions"] = await client.call_tool("definitions", {"ids": ["proposition.claim"]})
        ref = out["ply"].structured_content["judgement"]
        sentence = {"text": "2.exd5로 폰을 잡았다.", "class": "sourced", "cites": [ref]}
        out["refused"] = await client.call_tool("submit_commentary", {
            "game": G1, "ply": 3, "agent": {"name": "t"},
            "sentences": [sentence | {"text": "2.exd4로 폰을 잡았다."}]})  # fmt: skip
        out["accepted"] = await client.call_tool("submit_commentary", {
            "game": G1, "ply": 3, "agent": {"name": "t"}, "sentences": [sentence]})  # fmt: skip
        out["show"] = await client.call_tool("show_game", {"game": G1, "plies": "1-4"})
        out["guide"] = await client.read_resource("calliope://guides/commentary_ko")
        return out

    return go()


def _run(tmp_path, recorder=None, page=PAGE, guide_name="commentary_ko_v8"):
    s = session(tmp_path / "data", recorder=recorder)
    server = build_server(s, page, guide_name)

    async def main():
        async with Client(server) as client:
            tools = sorted(t.name for t in (await client.list_tools()).tools)
            return tools, await _script(client)

    try:
        return anyio.run(main)
    finally:
        s.close()


def _neutral(value):
    """Answers across processes: handle tokens, budget left and times differ by design (N1)."""

    text = TOKEN.sub(r"\1.T", json.dumps(value, ensure_ascii=False, sort_keys=True))
    doc = json.loads(text)

    def walk(v):
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()
                    if k not in ("budget_left", "seconds_per_ply", "seconds_left", "created",
                                 "id", "ms")}  # fmt: skip
        if isinstance(v, list):
            return [walk(x) for x in v]
        return v

    return walk(doc)


def _answers(out):
    return {k: (v.structured_content if hasattr(v, "structured_content") else
                [c.text for c in v.contents]) for k, v in out.items()}  # fmt: skip


# -- the server's recording ------------------------------------------------------------------------


@pytest.mark.parametrize("page", [PAGE, None], ids=["app", "plain"])
def test_one_call_line_per_tool_call_and_its_events_after_it(tmp_path, page) -> None:
    recorder = Recorder(tmp_path / "runs", "RUN1")
    _, out = _run(tmp_path, recorder, page)
    recorder.end()
    lines = _lines(recorder)
    assert [x["seq"] for x in lines] == list(range(1, len(lines) + 1))
    calls = [x for x in lines if x["type"] == "call"]
    assert [c["tool"] for c in calls] == ["open_game", "analyze_game", "game_overview", "ply",
                                          "judge_move", "definitions", "submit_commentary",
                                          "submit_commentary", "show_game"]  # fmt: skip
    assert [c["call_id"] for c in calls] == list(range(1, 10))  # analyze_game once (review B1)
    reads = [x for x in lines if x["type"] == "read"]
    assert [(r["kind"], r["name"]) for r in reads] == [("resource", "commentary_guide")]
    # every handle and submission follows its call, with its call_id (review B2)
    current = None
    for line in lines:
        if line["type"] == "call":
            current = line["call_id"]
        elif line["type"] in ("handle", "submission"):
            assert line["call_id"] == current
    handles = [x for x in lines if x["type"] == "handle"]
    assert handles and {h["call_id"] for h in handles} >= {4, 5}  # ply, judge_move
    assert len({h["ref"] for h in handles}) == len(handles)  # a ref served again writes nothing
    subs = [x for x in lines if x["type"] == "submission"]
    assert [s["subjects"][0]["outcome"] for s in subs] == ["refused", "accepted"]
    ref = out["ply"].structured_content["judgement"]
    accepted = subs[1]["subjects"][0]
    assert accepted["submitted"]["sentences"][0]["cites"] == [ref]  # as the agent sent it (N5)
    assert any(p["id"].startswith(ref + ":") for p in accepted["verified"])  # as checked
    assert accepted["id"] == out["accepted"].structured_content["id"]
    assert subs[0]["subjects"][0]["problems"][0]["rule"] == "S3"


def test_recording_changes_no_answer(tmp_path) -> None:
    """RX1-D §8 item 1 (review N1): the same script with recording off and on, tokens normalised."""

    tools_off, off = _run(tmp_path / "off")
    tools_on, on = _run(tmp_path / "on", Recorder(tmp_path / "runs", "RUN2"))
    assert tools_off == tools_on
    assert _neutral(_answers(off)) == _neutral(_answers(on))


def test_the_tool_schemas_are_the_same_with_the_recorder(tmp_path) -> None:
    async def listed(recorder):
        s = session(tmp_path / ("a" if recorder is None else "b"), recorder=recorder)
        try:
            async with Client(build_server(s, PAGE)) as client:
                return {t.name: (t.input_schema if hasattr(t, "input_schema") else t.inputSchema,
                                 t.description) for t in (await client.list_tools()).tools}  # fmt: skip
        finally:
            s.close()

    plain = anyio.run(listed, None)
    recorded = anyio.run(listed, Recorder(tmp_path / "runs", "RUN3"))
    assert plain == recorded


def test_events_outside_a_call_errors_and_the_cap(tmp_path) -> None:
    recorder = Recorder(tmp_path, "RUN4", cap=120)

    class Entry:
        def __init__(self, ref):
            self.ref, self.kind, self.game = ref, "fact", "g"
            self.source, self.address = (
                {"kind": "facts_tree", "rev": 3},
                {"position": [], "family": "move"},
            )

    recorder.handle(Entry("f1.x"))  # no open call: written at once

    @recorder.wrap("boom")
    async def boom():
        recorder.handle(Entry("f2.x"))
        raise ValueError("no")

    @recorder.wrap("big")
    async def big():
        return {"text": "x" * 200}

    @recorder.wrap("small")
    async def small():
        return {"ok": 1}

    async def main():
        with pytest.raises(ValueError):
            await boom()
        await big()
        await small()

    anyio.run(main)
    recorder.end()
    lines = _lines(recorder)
    assert lines[0]["type"] == "handle" and lines[0]["call_id"] is None
    assert lines[1]["type"] == "call" and lines[1]["error"] == "ValueError: no"
    assert lines[2]["type"] == "handle" and lines[2]["call_id"] == 1  # kept on error
    assert lines[3]["tool"] == "big" and lines[3]["capped"] and "answer" not in lines[3]
    assert lines[4]["tool"] == "small" and lines[4]["answer"] == {"ok": 1}
    assert lines[-1]["type"] == "end" and lines[-1]["capped_calls"] == [2]


# -- evidence_identity (RX0-D §5, RX1-D §7) --------------------------------------------------------


def test_identity_drops_what_belongs_to_one_process() -> None:
    fact = {"position": ["e2e4"], "family": "move"}
    assert identity("fact", "g", {"kind": "facts_tree", "rev": 1}, fact) == \
        identity("fact", "g", {"kind": "facts_tree", "rev": 9}, fact)  # fmt: skip
    board = {"propositions": [{"kind": "x"}]}
    assert identity("board_item", "g", {"kind": "board", "subject": ["e2e4"], "bundle": "a"},
                    board) == identity("board_item", "g", {"kind": "board", "subject": ["e2e4"],
                                                            "bundle": "b"}, board)  # fmt: skip
    analysis = {"kind": "analysis", "path": ["e2e4"], "tree": "t", "graph": "g", "build": "b",
                "analysis": "t:g"}  # fmt: skip
    search = {"kind": "search", "position": ["e2e4"], "search": "s1", "lines": "L"}
    a = identity_fields("search_line", "g", analysis, {"judgement": 0, "rank": 1, "fen": "F"})
    b = identity_fields("search_line", "g", search, {"rank": 1, "fen": "F", "path": ["e2e4"]})
    assert a[1] == "analysis" and b[1] == "search" and a != b  # review B2
    assert line_key("F", ["e7e5", "g1f3"]) == line_key("F", ["e7e5", "g1f3"])
    assert line_key("F", list("abcdefghij")) == line_key("F", list("abcdefgh"))  # eight plies


def test_identities_are_equal_across_sessions_and_handles_differ(tmp_path) -> None:
    """RX1-D §7: two sessions read the same plies, lines, facts and explored lines."""

    def script(tag):
        recorder = Recorder(tmp_path / "runs", tag)
        _run(tmp_path / tag, recorder)
        recorder.end()
        return [x for x in _lines(recorder) if x["type"] == "handle"]

    one, two = script("ONE"), script("TWO")
    assert len(one) == len(two)
    assert all(a["ref"] != b["ref"] for a, b in zip(one, two))
    assert [a["identity"] for a in one] == [b["identity"] for b in two]
    assert {h["kind"] for h in one} >= {"judgement", "claim", "search_line"}


# -- rx_moments (RX0-D §3.1, RX1-D §3) --------------------------------------------------------------


def _s(grade=None, label=None, loss=0, we=500):
    return {"move": "m", "grade": grade, "label": label, "loss": loss, "white_expected": we}


def test_moments_unchanged_and_the_ranking_whole() -> None:
    summaries = {p: _s("mistake" if p % 3 == 0 else "inaccuracy", loss=p) for p in range(1, 60)}
    ranked = _ranking(summaries)
    assert len(ranked) == 59
    assert [m["ply"] for m in _moments(summaries)] == sorted(m["ply"] for m in ranked[:MOMENTS])


def test_rx_moments_reads_past_sixteen() -> None:
    summaries = {p: _s("blunder", loss=300) for p in range(1, 21)}
    summaries[21] = _s(label="great")  # ranked 21st, past `_moments`' 16
    chosen = rx_moments(summaries)["moments"]
    assert [(m["slot"], m["ply"], m["filled"]) for m in chosen] == [
        ("error", 1, False),
        ("error", 2, False),
        ("special", 21, False),
    ]
    assert 21 not in [m["ply"] for m in _moments(summaries)]


def test_rx_moments_a_miss_only_and_filling() -> None:
    summaries = {1: _s("inaccuracy", loss=10), 2: _s(label="miss"), 3: _s("mistake", loss=200),
                 4: _s("inaccuracy", loss=50)}  # fmt: skip
    chosen = rx_moments(summaries)["moments"]
    # ranked 3 (mistake), 2 (miss), 4, 1: one error moment, the second slot filled by 4
    assert [(m["slot"], m["ply"], m["filled"]) for m in chosen] == [
        ("error", 3, False),
        ("error", 4, True),
        ("special", 2, False),
    ]
    assert rx_moments({1: _s("blunder"), 2: _s()})["moments"] is None  # fewer than three ranked


# -- the min guide (RX1-D §6) ------------------------------------------------------------------------


def test_the_min_guide_keeps_the_contract_and_v8_is_unchanged(tmp_path) -> None:
    v8, mini = text("commentary_ko_v8.md"), text("commentary_min_v1.md")
    for section in ("## 받는 재료", "## 인용: 핸들로 바로", "## 표기", "## 제출"):
        assert section in mini and section in v8
    for gone in ("## 어떻게 쓰는가", "### 예시", "## 분량"):
        assert gone not in mini
    assert guide("commentary_min_v1")  # it formats
    _, out = _run(tmp_path, guide_name="commentary_min_v1")
    assert out["guide"].contents[0].text == guide("commentary_min_v1")
    with pytest.raises(ValueError):
        build_server(session(tmp_path / "x"), None, "commentary_ko_v7")


# -- the runner's checker and finals (RX0-D §4.4, §6.0) -------------------------------------------


def _write(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")


def test_check_and_finals(tmp_path) -> None:
    run = tmp_path / "R"
    sub = lambda seq, cid, outcome, text: {"seq": seq, "type": "submission", "call_id": cid,
        "subjects": [{"subject": {"ply": 14}, "game_ply": 14, "outcome": outcome,
                      "submitted": {"sentences": [{"text": text}]}}]}  # fmt: skip
    _write(run / "tools.jsonl", [
        {"seq": 1, "type": "start"},
        {"seq": 2, "type": "call", "call_id": 1, "tool": "ply"},
        {"seq": 3, "type": "call", "call_id": 2, "tool": "submit_commentary"},
        sub(4, 2, "accepted", "first"),
        {"seq": 5, "type": "call", "call_id": 3, "tool": "submit_commentary"},
        sub(6, 3, "duplicate", "second"),
        {"seq": 7, "type": "end", "capped_calls": []}])  # fmt: skip
    tool_calls = lambda *names: {"tool_calls": [{"function": {"name": n}} for n in names]}
    _write(run / "agent.jsonl", [
        {"seq": 1, "type": "start", "moments": [14, 25]},
        {"seq": 2, "type": "response", "message": tool_calls("ply", "submit_commentary")},
        {"seq": 3, "type": "response", "message": tool_calls("submit_commentary")},
        {"seq": 4, "type": "response", "message": {}},
        {"seq": 5, "type": "end", "reason": "done"}])  # fmt: skip
    result = check(run)
    assert result["whole"], result["problems"]
    final = finals(run, [14, 25])
    assert final[14]["sentences"][0]["text"] == "second" and final[25] is None
    _write(run / "agent.jsonl", [{"seq": 1, "type": "start"}, {"seq": 3, "type": "end"}])
    assert not check(run)["whole"]


def test_refused_subjects_and_numbered_moves() -> None:
    items = {"items": [{"ply": 3}, {"ply": 5}]}
    answer = json.dumps(
        {
            "items": [
                {"index": 0, "outcome": "accepted"},
                {"index": 1, "outcome": "refused", "violations": [{"rule": "S3"}]},
            ]
        }
    )
    assert _refused_subjects(items, answer) == [("ply 5", [{"rule": "S3"}])]
    assert _refused_subjects({"ply": 3}, json.dumps({"accepted": False, "violations": []})) == [
        ("ply 3", [])
    ]
    assert numbered(GAME, [3, 4]) == ["2.exd5", "2...Nf6"]


# -- the review of PR #141 -------------------------------------------------------------------------


def test_search_lines_carry_their_line_key_whichever_source(tmp_path) -> None:
    """Review B1: `handle` lines of `s` handles carry `line_key`; M2a matches across sources."""

    from tools.rx.check import covered

    recorder = Recorder(tmp_path / "runs", "RUN5")
    _run(tmp_path, recorder)
    recorder.end()
    lines = [x for x in _lines(recorder) if x["type"] == "handle"]
    lines_s = [x for x in lines if x["kind"] == "search_line"]
    assert lines_s and all(x.get("line_key") for x in lines_s)
    assert not any("line_key" in x for x in lines if x["kind"] != "search_line")

    class Entry:
        def __init__(self, ref, source, address):
            self.ref, self.kind, self.game = ref, "search_line", "g"
            self.source, self.address = source, address
            self.item = {"pv": [{"uci": "e7e5"}, {"uci": "g1f3"}]}

    pair = Recorder(tmp_path / "runs", "RUN6")
    analysis = {"kind": "analysis", "path": [], "tree": "t", "graph": "g", "build": "b"}
    pair.handle(Entry("s1.a", analysis, {"judgement": 0, "rank": 1, "fen": "F"}))
    search = {"kind": "search", "position": [], "search": "x", "lines": "L"}
    pair.handle(Entry("s2.a", search, {"rank": 1, "fen": "F", "path": []}))
    pair.end()
    a, b = [x for x in _lines(pair) if x["type"] == "handle"]
    assert a["identity"] != b["identity"] and a["line_key"] == b["line_key"]
    served = {x["ref"]: {"identity": x["identity"], "line_key": x["line_key"]} for x in (a, b)}
    assert covered({"s2.a"}, served, [{"line_key": a["line_key"]}])  # the other source's line
    assert covered({"s1.a:line"}, served, [{"identity": a["identity"]}])  # a built proposition id
    assert not covered({"s2.a"}, served, [{"identity": a["identity"]}])


def test_a_subject_by_position_and_move_counts_as_its_ply(tmp_path) -> None:
    """Review B3: `position` + the played move is the played ply; another move at it is not."""

    recorder = Recorder(tmp_path / "runs", "RUN7")
    s = session(tmp_path / "data", recorder=recorder)
    server = build_server(s, PAGE)
    texts = {"exd5": "2.exd5로 폰을 잡았다.", "Nc3": "2.Nc3을 둘 수 있었다."}

    async def main():
        async with Client(server) as client:
            await client.call_tool("open_game", {"pgn": GAME})
            before = {"ply": 3, "at": "before"}
            out = {}
            for move, said in texts.items():
                judged = await client.call_tool(
                    "judge_move", {"game": G1, "position": before, "move": move}
                )
                ref = judged.structured_content["judgement"]
                sentence = {"text": said, "class": "sourced", "cites": [ref]}
                out[move] = await client.call_tool(
                    "submit_commentary",
                    {"game": G1, "position": before, "move": move, "agent": {"name": "t"},
                     "sentences": [sentence]},
                )  # fmt: skip
            return out

    try:
        out = anyio.run(main)
    finally:
        s.close()
    recorder.end()
    assert all(r.structured_content["accepted"] for r in out.values()), out
    subjects = [x["subjects"][0] for x in _lines(recorder) if x["type"] == "submission"]
    assert [x["game_ply"] for x in subjects] == [3, None]
    assert subjects[0]["path"] == ["e2e4", "d7d5", "e4d5"]
    assert subjects[1]["path"] == ["e2e4", "d7d5", "b1c3"]
    final = finals(recorder.path.parent, [3])
    assert final[3]["sentences"][0]["text"] == texts["exd5"]  # not 2.Nc3's


def test_a_run_that_fails_anywhere_ends_and_cleans_up(tmp_path, monkeypatch) -> None:
    """Review B2: an unexpected exception still writes the agent layer's `end` and removes the
    working copy."""

    import contextlib

    import mcp.client.stdio

    from tools.rx import run as rx_run

    base = tmp_path / "base"
    (base / "data" / "plies").mkdir(parents=True)
    (base / "data" / "plies" / "x").write_text("x")
    files = rx_run.tree_digests(base / "data")
    (base / "base.json").write_text(json.dumps({"set": "t", "files": files}))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    @contextlib.asynccontextmanager
    async def broken(*args, **kwargs):
        raise json.JSONDecodeError("bad", "{", 0)
        yield  # pragma: no cover

    monkeypatch.setattr(mcp.client.stdio, "stdio_client", broken)
    spec = rx_run.RunSpec(arm="A", set_name="train", game="g", pgn=GAME, moments=[3],
                          base=base, records=tmp_path / "runs", work=tmp_path / "work")  # fmt: skip
    result = anyio.run(rx_run.run_once, spec, "RUN8")
    assert result["reason"] == "error"
    text_ = (tmp_path / "runs" / "RUN8" / "agent.jsonl").read_text(encoding="utf-8")
    agent = [json.loads(x) for x in text_.splitlines()]
    assert agent[0]["type"] == "start"
    assert agent[-1]["type"] == "end" and agent[-1]["reason"] == "error"
    assert any(x["type"] == "error" and "JSONDecodeError" in x["error"] for x in agent)
    assert not (tmp_path / "work" / "RUN8").exists()


def test_a_model_answer_is_bounded_as_a_whole() -> None:
    """Review N1: a body sent a little at a time is cut at the request's deadline."""

    import time

    from tools.rx.model import _read_by

    class Drip:
        def read(self, n):
            time.sleep(0.05)
            return b"x"

    with pytest.raises(TimeoutError):
        _read_by(Drip(), time.monotonic() + 0.2)

    class Whole:
        def __init__(self):
            self.parts = [b'{"a":', b"1}", b""]

        def read(self, n):
            return self.parts.pop(0)

    assert _read_by(Whole(), time.monotonic() + 5) == b'{"a":1}'


STOCKFISH = os.environ.get("CALLIOPE_STOCKFISH_PATH")


@pytest.mark.skipif(not STOCKFISH or not os.path.exists(STOCKFISH),
                    reason="needs CALLIOPE_STOCKFISH_PATH")  # fmt: skip
def test_identities_are_equal_across_stockfish_sessions(tmp_path) -> None:
    """Review N2, RX1-D §7: two sessions on Stockfish read the same ply, move, facts and a
    searched explored line; every handle differs, every identity is equal."""

    from calliope.facts.search import StockfishEngine

    def one(tag):
        recorder = Recorder(tmp_path / "runs", tag)
        s = session(tmp_path / tag, start=lambda: StockfishEngine.start(STOCKFISH),
                    recorder=recorder)  # fmt: skip

        async def main():
            async with Client(build_server(s, None)) as client:
                await client.call_tool("open_game", {"pgn": GAME})
                await client.call_tool("ply", {"game": G1, "ply": 3})
                await client.call_tool("judge_move", {
                    "game": G1, "position": {"ply": 3, "at": "before"}, "move": "Nc3"})  # fmt: skip
                await client.call_tool("facts", {
                    "game": G1, "position": {"from_root": ["e2e4"]}, "families": ["move"]})  # fmt: skip
                await client.call_tool("explore", {
                    "game": G1, "position": {"ply": 2, "at": "after"}, "moves": ["exd5"],
                    "search": True})  # fmt: skip

        try:
            anyio.run(main)
        finally:
            s.close()
        recorder.end()
        return [x for x in _lines(recorder) if x["type"] == "handle"]

    a, b = one("SF1"), one("SF2")
    assert len(a) == len(b) and all(x["ref"] != y["ref"] for x, y in zip(a, b, strict=True))
    assert [x["identity"] for x in a] == [y["identity"] for y in b]
    assert [x.get("line_key") for x in a] == [y.get("line_key") for y in b]
    kinds = {x["kind"] for x in a}
    assert {"judgement", "search_line", "fact", "explored_line"} <= kinds


def test_a_call_the_runner_did_not_send_keeps_the_run_whole(tmp_path) -> None:
    """RX1 rev. 2, from the live run: the model sent cut-off JSON arguments; the runner told it so,
    sent nothing, and wrote `tool_unsent`. Such a call is not a lost one; a lost one still fails."""

    run = tmp_path / "R"
    _write(run / "tools.jsonl", [
        {"seq": 1, "type": "start"},
        {"seq": 2, "type": "call", "call_id": 1, "tool": "ply"},
        {"seq": 3, "type": "end", "capped_calls": []}])  # fmt: skip
    asked = {"tool_calls": [{"id": "a", "function": {"name": "submit_commentary"}},
                            {"id": "b", "function": {"name": "ply"}}]}  # fmt: skip
    agent = [{"seq": 1, "type": "start"}, {"seq": 2, "type": "response", "message": asked},
             {"seq": 3, "type": "tool_unsent", "tool_call_id": "a", "tool": "submit_commentary",
              "reason": "arguments are not a JSON object"},
             {"seq": 4, "type": "end", "reason": "done"}]  # fmt: skip
    _write(run / "agent.jsonl", agent)
    assert check(run)["whole"]
    lines_ = [x for x in agent if x["type"] != "tool_unsent"]
    for i, x in enumerate(lines_, start=1):
        x["seq"] = i
    _write(run / "agent.jsonl", lines_)
    assert not check(run)["whole"]
