"""AG-D §11 tests 2 and 9 through the MCP SDK's in-process client: the tools, a refusal as a tool
error, the Korean prompts, the resources and the agent build; AG3-D §5 (MCP): `show_game`, its App
resource and the plain tool without the viewer."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import anyio
import pytest
from agent_helpers import G1, GAME, session

from calliope.agent import AGENT_DIGEST, Limits
from calliope.reasoning import REGISTRY_DIGEST
from calliope.results import schema_errors

pytest.importorskip("mcp", reason="the MCP SDK is the optional group `agent`")

from mcp import Client

from calliope.agent.server import APP_MARKER, VIEWER_URI, app_page, build_server
from tools.mcp.__main__ import VIEWER

PAGE = app_page(VIEWER)


def _run(tmp_path, body, limits: Limits | None = None, page: str | None = PAGE):
    s = session(tmp_path, limits)
    server = build_server(s, page)

    async def main():
        async with Client(server) as client:
            return await body(client, s) if body.__code__.co_argcount == 2 else await body(client)

    try:
        return anyio.run(main)
    finally:
        s.close()


def test_the_tools_prompts_and_resources_are_listed(tmp_path) -> None:
    async def body(client):
        tools = {t.name for t in (await client.list_tools()).tools}
        prompts = {p.name for p in (await client.list_prompts()).prompts}
        uris = {str(r.uri) for r in (await client.list_resources()).resources}
        return tools, prompts, uris

    tools, prompts, uris = _run(tmp_path, body)
    assert tools == {"open_game", "ply", "judge_move", "facts", "explore", "definitions",
                     "submit_commentary", "commentary", "show_game"}  # fmt: skip
    assert prompts == {"calliope_commentary", "calliope_check"}
    assert uris == {"calliope://definitions", "calliope://glossary/ko", "calliope://build",
                    "calliope://guides/commentary_ko", "calliope://guides/check_ko",
                    VIEWER_URI}  # fmt: skip


def test_a_session_through_the_client(tmp_path) -> None:
    progress = []

    async def body(client):
        async def on_progress(done, total, message):
            progress.append((done, total, message))

        opened = await client.call_tool(
            "open_game", {"pgn": GAME, "plies": "1-2"}, progress_callback=on_progress
        )
        ply = await client.call_tool("ply", {"game": G1, "ply": 3})
        judged = await client.call_tool(
            "judge_move", {"game": G1, "position": {"ply": 3, "at": "before"}, "move": "Nc3"}
        )
        facts = await client.call_tool(
            "facts", {"game": G1, "position": {"from_root": ["e2e4"]}, "families": ["move"]}
        )
        explored = await client.call_tool(
            "explore",
            {"game": G1, "position": {"ply": 2, "at": "after"}, "moves": ["exd5"],
             "search": True},
        )  # fmt: skip
        found = await client.call_tool("definitions", {"ids": ["proposition.claim", "REFUTED"]})
        return opened, ply, judged, facts, explored, found

    results = _run(tmp_path, body)
    assert not any(r.is_error for r in results)
    opened, ply, judged, facts, explored, found = (r.structured_content for r in results)
    assert opened["game"] == G1 and opened["moves"][0]["grade"] is not None
    assert [p[0] for p in progress] == [1, 2]
    assert ply["ply"] == 3 and ply["analysis"]["claims"]
    assert judged["san"] == "Nc3" and not judged["played"]
    assert facts["families"]["move"]["record"]["san"] == "e4"
    assert explored["search"]["lines"][0]["pv"][0]["by"] == "engine"
    assert {d["id"] for d in found["definitions"]} == {"proposition.claim", "REFUTED"}


def test_a_refusal_is_a_tool_error(tmp_path) -> None:
    async def body(client):
        await client.call_tool("open_game", {"pgn": GAME})
        return (
            await client.call_tool("ply", {"game": G1, "ply": 1}),
            await client.call_tool("ply", {"game": G1, "ply": 99}),
        )

    refused, wrong = _run(tmp_path, body, Limits(max_uncached_plies=0))
    assert refused.is_error and "budget" in refused.content[0].text
    assert wrong.is_error and "plies 1 to 10" in wrong.content[0].text


def test_the_prompts_are_korean_and_the_resources_carry_the_build(tmp_path) -> None:
    async def body(client):
        prompt = await client.get_prompt("calliope_commentary", {"game": G1, "ply": "33"})
        check = await client.get_prompt("calliope_check", {"game": G1, "ply": "33"})
        definitions = await client.read_resource("calliope://definitions")
        glossary = await client.read_resource("calliope://glossary/ko")
        build = await client.read_resource("calliope://build")
        return prompt, check, definitions, glossary, build

    prompt, check, definitions, glossary, build = _run(tmp_path, body)
    text = prompt.messages[0].content.text
    assert f"게임 {G1}, 수 33" in text and "ATTRIBUTED" in text
    assert "제출하기 전에" in check.messages[0].content.text
    registries = json.loads(definitions.contents[0].text)
    assert registries["definitions_v1"]["digest"] == REGISTRY_DIGEST
    assert registries["agent_definitions_v1"]["digest"] == AGENT_DIGEST
    assert json.loads(glossary.contents[0].text)["grades"]["blunder"] == "블런더"
    agent_build = json.loads(build.contents[0].text)
    assert agent_build["agent_definitions"] == AGENT_DIGEST
    assert set(agent_build["prompts"]) == {"commentary_ko_v1", "check_ko_v1"}
    assert len(agent_build["reasoning_build"]) == 64


def test_a_commentary_through_the_client(tmp_path) -> None:
    async def body(client):
        await client.call_tool("open_game", {"pgn": GAME})
        ply = (await client.call_tool("ply", {"game": G1, "ply": 1})).structured_content
        j = ply["analysis"]["judgements"][0]
        proposition = {"id": "p1", "kind": "judgement", "judgement": j["ref"], "move": "e4",
                       "grade": j["grade"], "label": j["label"],
                       "best_move": j["best"]["move"]["uci"]}  # fmt: skip
        sentence = {"text": "1.e4로 시작했다.", "class": "sourced", "cites": ["p1"]}
        refused = await client.call_tool("submit_commentary", {
            "game": G1, "ply": 1, "agent": {"name": "t"}, "propositions": [proposition],
            "sentences": [sentence | {"text": "1.d4로 시작했다."}]})  # fmt: skip
        accepted = await client.call_tool("submit_commentary", {
            "game": G1, "ply": 1, "agent": {"name": "t"}, "propositions": [proposition],
            "sentences": [sentence]})  # fmt: skip
        listed = await client.call_tool("commentary", {"game": G1, "ply": 1})
        return refused, accepted, listed

    refused, accepted, listed = (r.structured_content for r in _run(tmp_path, body))
    assert not refused["accepted"] and refused["violations"][0]["token"] == "1.d4"
    assert accepted["accepted"]
    assert [c["id"] for c in listed["commentaries"]] == [accepted["id"]]


# -- show_game and the MCP App (AG3-D D9–D11, D13; §5 MCP) -----------------------------------------


def _commentary_on_ply_1(client) -> dict:
    """Ply 1 analysed and an accepted commentary of it; returns the submission's answer."""

    async def go():
        ply = (await client.call_tool("ply", {"game": G1, "ply": 1})).structured_content
        j = ply["analysis"]["judgements"][0]
        proposition = {"id": "p1", "kind": "judgement", "judgement": j["ref"], "move": "e4",
                       "grade": j["grade"], "label": j["label"],
                       "best_move": j["best"]["move"]["uci"]}  # fmt: skip
        return (await client.call_tool("submit_commentary", {
            "game": G1, "ply": 1, "agent": {"name": "t"}, "propositions": [proposition],
            "sentences": [{"text": "1.e4로 시작했다.", "class": "sourced", "cites": ["p1"]}]}
        )).structured_content  # fmt: skip

    return go()


def test_show_game_is_bound_to_the_viewer_page(tmp_path) -> None:
    async def body(client):
        tool = next(t for t in (await client.list_tools()).tools if t.name == "show_game")
        page = await client.read_resource(VIEWER_URI)
        listed = next(r for r in (await client.list_resources()).resources
                      if str(r.uri) == VIEWER_URI)  # fmt: skip
        return tool, page, listed

    tool, page, listed = _run(tmp_path, body)
    assert tool.meta == {"ui": {"resourceUri": VIEWER_URI, "visibility": ["model", "app"]}}
    assert tool.output_schema is None
    assert listed.mime_type == "text/html;profile=mcp-app"
    [content] = page.contents
    assert content.mime_type == "text/html;profile=mcp-app"
    html = (VIEWER / "index.html").read_text(encoding="utf-8")
    assert content.text.count(APP_MARKER) == 1
    assert content.text.replace(APP_MARKER + "\n", "") == html  # the viewer, one element added
    assert content.text.index(APP_MARKER) < content.text.index("</head>")


def test_show_game_answers_a_combined_document_of_the_cached_plies(tmp_path) -> None:
    async def body(client, s):
        await client.call_tool("open_game", {"pgn": GAME, "plies": "1-3"})
        accepted = await _commentary_on_ply_1(client)
        left = s.budget.left()
        shown = await client.call_tool("show_game", {"game": G1})
        part = await client.call_tool("show_game", {"game": G1, "plies": "2-5"})
        return accepted, left, s.budget.left(), shown, part

    accepted, left, after, shown, part = _run(tmp_path, body)
    assert accepted["accepted"] and left == after  # nothing analysed, nothing charged
    assert not shown.is_error
    document = shown.structured_content
    assert document["schema"] == "calliope_result_v1" and schema_errors(document) == []
    assert [p["ply"] for p in document["plies"]] == [1, 2, 3]
    ai = document["plies"][0]["ai_commentary"]
    assert ai["id"] == accepted["id"]
    assert ai["display"]["subject"]["moves"] == [{"uci": "e2e4", "san": "e4"}]
    assert ai["propositions"][0]["display"]["v"] == "display_v1"
    assert all("ai_commentary" not in p for p in document["plies"][1:])
    [text] = shown.content  # the short text only: the document is not in it
    assert text.type == "text" and "calliope_result_v1" not in text.text
    assert text.text.splitlines() == [f"게임 {G1}: 분석된 수 3개를 판에 보여 줍니다 (수 1–3).",
                                      f"1.e4 (수 1): {_ko(document, 0)} · AI 해설 있음",
                                      f"1...d5 (수 2): {_ko(document, 1)}",
                                      f"2.exd5 (수 3): {_ko(document, 2)}"]  # fmt: skip
    assert [p["ply"] for p in part.structured_content["plies"]] == [2, 3]
    assert "분석되지 않아 빠진 수: 4–5" in part.content[0].text


def _ko(document: dict, k: int) -> str:
    grades = {"best": "최선", "excellent": "우수", "good": "좋음", "inaccuracy": "부정확",
              "mistake": "실수", "blunder": "블런더"}  # fmt: skip
    return grades[document["plies"][k]["grade"]]


def test_show_game_with_no_cached_ply_is_an_error_without_a_document(tmp_path) -> None:
    async def body(client):
        await client.call_tool("open_game", {"pgn": GAME})
        return (
            await client.call_tool("show_game", {"game": G1}),
            await client.call_tool("show_game", {"game": G1, "plies": "4-6"}),
            await client.call_tool("show_game", {"game": G1, "plies": "20-30"}),
            await client.call_tool("show_game", {"game": "g-0000000000000000"}),
        )

    answers = _run(tmp_path, body)
    assert all(a.is_error and a.structured_content is None for a in answers)
    none, part, outside, unknown = (a.content[0].text for a in answers)
    assert "캐시된) 수가 없습니다" in none and "ply" in none
    assert "캐시된) 수가 없습니다" in part
    assert "outside the game's 10 plies" in outside
    assert "no game g-0000000000000000 (open it with open_game)" in unknown


def test_without_the_viewer_show_game_is_a_plain_tool(tmp_path, caplog) -> None:
    with caplog.at_level(logging.WARNING):
        assert app_page(tmp_path / "missing") is None
    assert "show_game has no App" in caplog.text
    (tmp_path / "headless").mkdir()
    (tmp_path / "headless" / "index.html").write_text("<html><body></body></html>")
    assert app_page(tmp_path / "headless") is None

    async def body(client):
        tool = next(t for t in (await client.list_tools()).tools if t.name == "show_game")
        uris = {str(r.uri) for r in (await client.list_resources()).resources}
        await client.call_tool("open_game", {"pgn": GAME, "plies": "1"})
        return tool, uris, await client.call_tool("show_game", {"game": G1})

    tool, uris, shown = _run(tmp_path / "data", body, page=None)
    assert tool.meta is None and VIEWER_URI not in uris
    assert not shown.is_error and shown.structured_content["plies"][0]["ply"] == 1
    assert shown.content[0].text.startswith(f"게임 {G1}: 분석된 수 1개")


def test_the_default_viewer_is_the_repository_viewer() -> None:
    assert VIEWER == Path(__file__).resolve().parents[2] / "viewer"
    assert PAGE is not None and APP_MARKER in PAGE
