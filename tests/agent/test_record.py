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


def test_a_missing_base_stops_before_any_record(tmp_path, monkeypatch) -> None:
    """Re-review N3: no `base.json`, no run record at all (not a `start` without an `end`)."""

    from tools.rx import run as rx_run

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    spec = rx_run.RunSpec(arm="A", set_name="train", game="g", pgn=GAME, moments=[3],
                          base=tmp_path / "none", records=tmp_path / "runs", work=tmp_path / "w")  # fmt: skip
    with pytest.raises(FileNotFoundError):
        anyio.run(rx_run.run_once, spec, "RUN9")
    assert not (tmp_path / "runs" / "RUN9").exists()


# -- RX2 (agent-rx2-design.md) ---------------------------------------------------------------------


def test_a_request_is_killed_at_its_deadline(tmp_path, monkeypatch) -> None:
    """RX2-D §2: the request runs in a child process, killed at the deadline; a whole body comes
    back; the key is never in the child's arguments."""

    import http.server
    import subprocess
    import threading
    import time

    from tools.rx import model as rx_model

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                if self.path == "/drip":
                    for _ in range(100):
                        self.wfile.write(b" ")
                        self.wfile.flush()
                        time.sleep(0.1)
                self.wfile.write(b'{"choices": [{"message": {"content": "ok"}}]}')
            except (BrokenPipeError, ConnectionResetError):  # the killed child's socket
                pass

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-key-123")
    started = []
    real = subprocess.Popen

    def spy(args, **kwargs):
        started.append(args)
        child = real(args, **kwargs)
        started.append(child)
        return child

    monkeypatch.setattr(rx_model.subprocess, "Popen", spy)
    try:
        doc = rx_model.post_in_child(base + "/whole", {"x": 1}, 10)
        assert doc["choices"][0]["message"]["content"] == "ok"
        began = time.monotonic()
        with pytest.raises(rx_model.ModelTimeout):
            rx_model.post_in_child(base + "/drip", {"x": 1}, 0.5)
        assert time.monotonic() - began < 3
        child = started[-1]
        assert child.poll() is not None  # gone, not left running
        assert not any("secret-key-123" in str(a) for a in started[0])
    finally:
        server.shutdown()


def test_shown_is_what_the_answer_showed(tmp_path) -> None:
    """RX2-D §7 (re-review C2): `shown` lists the refs in the answer's text; an error shows none; a
    capped answer keeps it."""

    recorder = Recorder(tmp_path / "runs", "RUN10", cap=10)  # every answer capped

    @recorder.wrap("fails")
    async def fails():
        recorder.handle(type("E", (), {"ref": "c1." + "a" * 24, "kind": "claim", "game": "g",
                                       "source": {}, "address": {}, "item": {}})())  # fmt: skip
        raise ValueError("after serving")

    @recorder.wrap("answers")
    async def answers():
        return {
            "claims": [{"ref": "c2." + "b" * 24}],
            "not_shown": {"named": [{"ref": "b3." + "c" * 24}]},
        }

    async def main():
        with pytest.raises(ValueError):
            await fails()
        await answers()

    anyio.run(main)
    recorder.end()
    calls = [x for x in _lines(recorder) if x["type"] == "call"]
    assert calls[0]["shown"] == [] and "error" in calls[0]
    assert calls[1]["capped"] and calls[1]["shown"] == ["b3." + "c" * 24, "c2." + "b" * 24]


def test_the_build_line_and_the_runner_s_check(tmp_path) -> None:
    """RX2-D §3 (re-review C1): one `build` line per engine start; two engines of one name and
    different identities give different build ids, and the runner refuses the other one."""

    import dataclasses

    import synthetic

    from tools.rx.run import build_problem

    def one(tag, start):
        recorder = Recorder(tmp_path / "runs", tag)
        s = session(tmp_path / tag, start=start, recorder=recorder)

        async def main():
            async with Client(build_server(s, None)) as client:
                await client.call_tool("open_game", {"pgn": GAME})
                await client.call_tool("ply", {"game": G1, "ply": 3})
                await client.call_tool("ply", {"game": G1, "ply": 4})

        try:
            anyio.run(main)
        finally:
            s.close()
        recorder.end()
        return [x for x in _lines(recorder) if x["type"] == "build"], recorder

    other = dataclasses.replace(synthetic.IDENTITY, binary_sha256="6" * 64)
    a, rec_a = one("B1", synthetic.engine)
    b, rec_b = one(
        "B2", lambda: synthetic.ScriptedEngine(other, synthetic.synthetic(4, frozenset()))
    )
    assert len(a) == 1 and len(b) == 1  # once per engine start
    assert a[0]["engine"][0] == b[0]["engine"][0]  # the same name
    assert a[0]["build_id"] != b[0]["build_id"]
    base = tmp_path / "base"
    base.mkdir()
    build = {k: a[0][k] for k in ("engine", "profile", "reasoning", "build_id")}
    (base / "base.json").write_text(json.dumps({"files": {}, "build": build}))
    assert build_problem(rec_a.path, base) is None
    assert "is not the base's" in build_problem(rec_b.path, base)
    (base / "base.json").write_text(json.dumps({"files": {}}))
    assert "annotate" in build_problem(rec_a.path, base)


def test_the_bundle_parts_and_the_audit(tmp_path) -> None:
    """RX2-D §5: parts of at most six moments holding every arm, no arm in the judge's files, the key
    apart; the audit flags reads outside, walks and the key."""

    from tools.rx import judge

    refs = tmp_path / "refs"
    runs = []
    for arm in ("A", "A-min"):
        for game in ("g1", "g2", "g3"):
            run = tmp_path / "runs" / f"{arm}-{game}"
            plies = [3, 5, 7]
            _write(run / "agent.jsonl", [{"seq": 1, "type": "start", "arm": arm, "set": "train",
                                          "game": game, "moments": plies}])  # fmt: skip
            _write(run / "tools.jsonl", [
                {"seq": i, "type": "submission", "call_id": i,
                 "subjects": [{"game_ply": p, "outcome": "accepted",
                               "submitted": {"sentences": [{"text": f"{game} {p} {len(arm)}"}]}}]}
                for i, p in enumerate(plies, start=1)])  # fmt: skip
            runs.append(run)
            for p in plies:
                (refs / "train").mkdir(parents=True, exist_ok=True)
                (refs / "train" / f"{game}-{p}.json").write_text("{}")
    original = judge.REFERENCES
    judge.REFERENCES = refs
    try:
        out = judge.bundle(runs, "J1", seed=7, root=tmp_path / "judging", keys=tmp_path / "keys")
    finally:
        judge.REFERENCES = original
    assert out["items"] == 18 and len(out["parts"]) == 2  # 9 moments: 6 and 3
    for part in out["parts"]:
        items = json.loads((tmp_path / "judging" / "J1" / part.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
                            / "bundle.json").read_text())["items"]  # fmt: skip
        text = json.dumps(items)
        assert "A-min" not in text and '"arm"' not in text
        moments = {i["moment"] for i in items}
        assert len(items) == 2 * len(moments)  # every arm's commentary of each moment
        assert not list((tmp_path / "judging" / "J1").rglob("bundle_key.json"))
    key = json.loads((tmp_path / "keys" / "J1" / "bundle_key.json").read_text())
    assert key["seed"] == 7 and len(key["key"]) == 18
    part = tmp_path / "judging" / "J1" / "part01"
    assert (
        judge.audit([{"tool": "Read", "input": {"file_path": str(part / "bundle.json")}}], part)
        == []
    )
    assert judge.audit([{"tool": "Read", "input": {"file_path": str(tmp_path / "keys")}}], part)
    # RX2 Q2: a listing inside the directory passes, one that can reach outside does not
    bash = lambda c: [{"tool": "Bash", "input": {"command": c}}]
    assert judge.audit(bash("find . -name '*.json'"), part) == []
    assert judge.audit(bash("python -c \"import os; print(os.listdir('references'))\""), part) == []
    assert judge.audit(bash("python -c \"s='ab'; print(s.find('b'))\""), part) == []
    assert judge.audit(bash("find .. -name '*.json'"), part)
    assert judge.audit(bash("python -c \"import os; print(os.listdir('/home'))\""), part)
    assert judge.audit([{"tool": "Bash", "input": {"command": "cat bundle_key.json"}}], part)
    ok = {"tool": "Bash", "input": {"command": "uv run --with python-chess python check.py"}}
    assert judge.audit([ok], part) == []


def test_metrics_m1a_and_the_bootstrap() -> None:
    from tools.rx.metrics import bootstrap, judged_metrics, refusal_class

    assert [refusal_class(r) for r in ("S3", None, "S7", "S1", "subject", "size", "Z9")] == [
        "fact",
        "fact",
        "fact",
        "form",
        "form",
        "form",
        "other",
    ]
    rows = [{"judged": {"sentences": [{"n": 1, "verdict": "ok"},
                                      {"n": 2, "verdict": "wrong", "kind": "grade", "why": "x"}],
                        "causes": [{"cause": 1, "verdict": "explained"},
                                   {"cause": 2, "verdict": "not"}], "score": 3}}]  # fmt: skip
    m = judged_metrics(rows)
    assert m["wrong_per_100"] == 50 and m["wrong_kinds"] == {"grade": 1}
    assert m["explained_share"] == 0.5 and m["score_mean"] == 3
    point, lo, hi = bootstrap({"g1": {"r1": [1, 1], "r2": [0, 1]}, "g2": {"r1": [0, 0]}})
    assert lo <= point <= hi and point == 0.5


def test_an_exception_group_is_logged_by_its_errors(tmp_path, monkeypatch) -> None:
    """RX2 batch rx2-1: a model error inside the MCP client's task group was logged as the group
    alone; the run now logs each inner error, and a timeout inside a group ends as `timeout`."""

    import contextlib

    import mcp.client.stdio

    from tools.rx import run as rx_run
    from tools.rx.model import ModelTimeout

    base = tmp_path / "base"
    (base / "data").mkdir(parents=True)
    (base / "base.json").write_text(json.dumps({"files": {}}))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    for inner, reason in ((ValueError("HTTP 502: bad gateway"), "error"),
                          (ModelTimeout("no answer"), "timeout")):  # fmt: skip

        @contextlib.asynccontextmanager
        async def broken(*args, inner=inner, **kwargs):
            raise ExceptionGroup("unhandled errors in a TaskGroup", [inner])
            yield  # pragma: no cover

        monkeypatch.setattr(mcp.client.stdio, "stdio_client", broken)
        spec = rx_run.RunSpec(arm="A", set_name="train", game="g", pgn=GAME, moments=[3],
                              base=base, records=tmp_path / "runs", work=tmp_path / "w")  # fmt: skip
        run_id = "RUN-" + reason
        assert anyio.run(rx_run.run_once, spec, run_id)["reason"] == reason
        agent = (tmp_path / "runs" / run_id / "agent.jsonl").read_text(encoding="utf-8")
        assert type(inner).__name__ in agent and "TaskGroup" not in agent


def test_the_task_names_the_game_by_its_id() -> None:
    """RX2 amendment A1: with the base's game id the task carries the id, not the PGN."""

    from tools.rx.run import TASK_BY_ID

    task = TASK_BY_ID.format(game_id="g-0123456789abcdef", moments="2.exd5")
    assert "g-0123456789abcdef" in task and "open_game" in task and "[Event" not in task


# -- the review of PR #143 -------------------------------------------------------------------------


def _ref_file(root, set_name, game, ply, causes):
    path = root / set_name / f"{game}-{ply}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"set": set_name, "game": game, "ply": ply, "build_id": "B",
                                "status": "reviewed", "key_causes": causes}), encoding="utf-8")  # fmt: skip


def test_an_on_request_cause_is_fetched_only_by_its_request(tmp_path) -> None:
    """Review B1: citing the cause's digest items is not fetching its request."""

    from tools.rx.metrics import record_moments

    refs = tmp_path / "refs"
    resolved = {"tool": "explore", "from": ["e2e4"], "moves": ["d7d5", "e4d5"]}
    _ref_file(refs, "train", "g", 3, [{"role": "decisive", "route": "on_request",
                                       "items": [{"identity": "I-C1"}],
                                       "request": {"resolved": resolved}}])  # fmt: skip
    sub = {"seq": 5, "type": "submission", "call_id": 3,
           "subjects": [{"game_ply": 3, "outcome": "accepted",
                         "submitted": {"sentences": [{"text": "t", "cites": ["c1.x"]}]}}]}  # fmt: skip

    def run(name, explore):
        r = tmp_path / name
        tools = [{"seq": 1, "type": "build", "build_id": "B", "call_id": None},
                 {"seq": 2, "type": "call", "call_id": 1, "tool": "ply", "shown": ["c1.x"]},
                 {"seq": 3, "type": "handle", "call_id": 1, "ref": "c1.x", "kind": "claim",
                  "identity": "I-C1", "address": {}}]  # fmt: skip
        if explore:
            tools += [{"seq": 4, "type": "call", "call_id": 2, "tool": "explore", "shown": ["x1.x"]},
                      {"seq": 4.5, "type": "handle", "call_id": 2, "ref": "x1.x", "kind": "explored_line",
                       "identity": "I-X", "address": {"from": ["e2e4"], "moves": ["d7d5", "e4d5", "g8f6"]}}]  # fmt: skip
        _write(r / "tools.jsonl", tools + [sub])
        _write(r / "agent.jsonl", [{"seq": 1, "type": "start", "arm": "A", "set": "train", "game": "g",
                                    "moments": [3]}])  # fmt: skip
        return record_moments(r, refs)[0]["causes"][0]

    cited_only = run("R1", explore=False)
    assert cited_only["covered"] and not cited_only["request_fetched"]
    assert not cited_only["available"] and not cited_only["used_direct"]
    explored = run("R2", explore=True)
    assert explored["request_fetched"] and explored["available"]


def test_shown_is_the_text_content_only(tmp_path) -> None:
    """Review B2: a handle only in a result's structured content is not shown to the model."""

    from mcp.types import CallToolResult, TextContent

    in_text, only_structured = "c1." + "a" * 24, "c2." + "b" * 24
    recorder = Recorder(tmp_path / "runs", "RUN11")

    @recorder.wrap("tool")
    async def tool():
        return CallToolResult(content=[TextContent(type="text", text=f"see {in_text}")],
                              structured_content={"doc": only_structured})  # fmt: skip

    anyio.run(tool)
    recorder.end()
    call = next(x for x in _lines(recorder) if x["type"] == "call")
    assert call["shown"] == [in_text]
    # and on the real `show_game`, every shown ref is in the text the model receives
    recorder2 = Recorder(tmp_path / "runs", "RUN12")
    s = session(tmp_path / "data", recorder=recorder2)

    async def main():
        async with Client(build_server(s, None)) as client:
            await client.call_tool("open_game", {"pgn": GAME})
            await client.call_tool("ply", {"game": G1, "ply": 3})
            return await client.call_tool("show_game", {"game": G1, "plies": "1-4"})

    try:
        result = anyio.run(main)
    finally:
        s.close()
    recorder2.end()
    text = "\n".join(c.text for c in result.content if c.type == "text")
    shown = next(x for x in _lines(recorder2) if x["type"] == "call" and x["tool"] == "show_game")[
        "shown"
    ]
    assert all(ref in text for ref in shown)


def test_the_report_refuses_an_unchecked_judging(tmp_path) -> None:
    """Review B3: no passed audit, an item missing or twice, a cause unjudged: refused."""

    from tools.rx import judge

    keys, parts = tmp_path / "keys", tmp_path / "judging" / "J2"
    part = parts / "part01"
    (part / "references").mkdir(parents=True)
    (part / "references" / "g-3.json").write_text(
        json.dumps({"key_causes": [{"role": "decisive"}]})
    )
    (part / "bundle.json").write_text(json.dumps({"items": [
        {"key": "0000000a", "moment": "train/g-3", "sentences": [{"n": 1, "text": "t"}]}]}))  # fmt: skip
    (keys / "J2").mkdir(parents=True)
    (keys / "J2" / "bundle_key.json").write_text(json.dumps({"seed": 1, "key": {
        "0000000a": {"part": 1, "game": "g", "ply": 3, "run_id": "R", "arm": "A", "set": "train"}}}))  # fmt: skip
    good = {"version": "judge_v1", "items": [
        {"key": "0000000a", "sentences": [{"n": 1, "verdict": "ok"}],
         "causes": [{"cause": 1, "verdict": "explained"}], "score": 4}]}  # fmt: skip

    def check(doc, audit_passed=True):
        (part / "judging.json").write_text(json.dumps(doc))
        if audit_passed is None:
            (keys / "J2" / "audit-part01.json").unlink(missing_ok=True)
        else:
            (keys / "J2" / "audit-part01.json").write_text(json.dumps({"passed": audit_passed}))
        return judge.checked_judgings("J2", parts, keys=keys)

    assert check(good)[1]["items"][0]["score"] == 4
    for doc, passed in ((good, None), (good, False),
                        ({"version": "judge_v1", "items": []}, True),
                        ({"version": "judge_v1", "items": good["items"] * 2}, True),
                        ({"version": "judge_v1", "items": [good["items"][0] | {"causes": []}]}, True),
                        ({"version": "judge_v1", "items": [good["items"][0] | {"score": 9}]}, True)):  # fmt: skip
        with pytest.raises(Exception):  # noqa: B017 - ValueError or a schema error
            check(doc, passed)


def test_the_interval_is_of_the_reported_ratio_and_moments_without_commentary_count() -> None:
    """Review B4: M1b's interval is centred on its ratio of sums. Review N1: a moment-run with no
    commentary counts as its decisive cause not explained."""

    from tools.rx.report import interval, mean_of, moment_values, wrong_rate

    v = lambda w, n: {"wrong": w, "sentences": n, "decisive": 1.0, "score": 4.0}
    tree = {"g1": {"r1": [v(1, 10), v(0, 2)]}, "g2": {"r1": [v(0, 4)]}}
    point, lo, hi = interval(tree, wrong_rate)
    assert point == 100 * 1 / 16 and lo <= point <= hi
    missing = moment_values(None, ["decisive"])
    assert missing["decisive"] == 0.0 and missing["sentences"] == 0 and missing["score"] is None
    assert moment_values(None, [])["decisive"] is None  # a moment with no key cause
    assert mean_of("decisive")([v(0, 1), missing]) == 0.5


def test_the_audit_flags_explicit_outside_paths() -> None:
    """RX2 re-review C1: a direct read outside the directory, by any program, is flagged."""

    from tools.rx.judge import audit

    part = "D:/00_x/rx-judging/J/part01"
    bash = lambda c: [{"tool": "Bash", "input": {"command": c}}]
    for outside in ("cat /tmp/other-run.json", "python -c \"print(open('/tmp/x.json').read())\"",
                    "cat ../other-data/results.json", "head -n 3 ~/notes.txt", "sed -n 1p C:/Users/x/a.txt"):  # fmt: skip
        assert audit(bash(outside), part), outside
    for inside in (f'cd "{part}" && cat bundle.json', f'cat "{part}/bundle.json"',
                   f'cd "{part}" && uv run --with python-chess python check.py',
                   f'cd "{part}" && python - <<\'EOF\'\nprint("a\\nb")\nEOF'):  # fmt: skip
        assert audit(bash(inside), part) == [], inside


def test_used_related_p1_and_p2() -> None:
    """RX2 re-review C2: an explore through the item's line, or touching its squares, or a
    judge_move of its move, is related use; a piece only shown is not."""

    from tools.rx.metrics import item_facts, related

    facts = item_facts([{"pv": [{"uci": "d4e5"}, {"uci": "g7g5"}], "proves": "23.dxe5 keeps the knight on e5",
                         "move": {"san": "dxe5", "uci": "d4e5"}}])  # fmt: skip
    x = lambda moves: {"kind": "explored_line", "address": {"moves": moves, "by": "agent"}}
    calliope_line = {
        "kind": "explored_line",
        "address": {"moves": ["d4e5", "g7g5"], "by": "calliope"},
    }
    assert not related(calliope_line, facts, None)  # Calliope's own same-reply line is not a test
    assert related(x(["d4e5", "g7g5", "f2f4"]), facts, None)  # the item's line
    assert related(x(["h2h3", "c6e5"]), facts, None)  # a move to e5, a square it names
    assert not related(x(["h2h3", "a7a6"]), facts, None)  # nothing it names
    judge = {"tool": "judge_move", "arguments": {"move": "dxe5"}}
    assert related({"kind": "judge"}, facts, judge)
    assert not related(
        {"kind": "judge"}, facts, {"tool": "judge_move", "arguments": {"move": "Nc3"}}
    )
