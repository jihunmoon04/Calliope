"""AG-D §11 tests 2 and 9 through the MCP SDK's in-process client: the tools, a refusal as a tool
error, the Korean prompts, the resources and the agent build."""

from __future__ import annotations

import json

import anyio
import pytest
from agent_helpers import GAME, session

from calliope.agent import AGENT_DIGEST, Limits
from calliope.reasoning import REGISTRY_DIGEST

pytest.importorskip("mcp", reason="the MCP SDK is the optional group `agent`")

from mcp import Client

from calliope.agent.server import build_server


def _run(tmp_path, body, limits: Limits | None = None):
    s = session(tmp_path, limits)
    server = build_server(s)

    async def main():
        async with Client(server) as client:
            return await body(client)

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
    assert tools == {"open_game", "ply", "judge_move", "facts", "explore", "definitions"}
    assert prompts == {"calliope_commentary", "calliope_check"}
    assert uris == {"calliope://definitions", "calliope://glossary/ko", "calliope://build"}


def test_a_session_through_the_client(tmp_path) -> None:
    progress = []

    async def body(client):
        async def on_progress(done, total, message):
            progress.append((done, total, message))

        opened = await client.call_tool(
            "open_game", {"pgn": GAME, "plies": "1-2"}, progress_callback=on_progress
        )
        ply = await client.call_tool("ply", {"game": "g1", "ply": 3})
        judged = await client.call_tool(
            "judge_move", {"game": "g1", "position": {"ply": 3, "at": "before"}, "move": "Nc3"}
        )
        facts = await client.call_tool(
            "facts", {"game": "g1", "position": {"from_root": ["e2e4"]}, "families": ["move"]}
        )
        explored = await client.call_tool(
            "explore",
            {"game": "g1", "position": {"ply": 2, "at": "after"}, "moves": ["exd5"],
             "search": True},
        )  # fmt: skip
        found = await client.call_tool("definitions", {"ids": ["proposition.claim", "REFUTED"]})
        return opened, ply, judged, facts, explored, found

    results = _run(tmp_path, body)
    assert not any(r.is_error for r in results)
    opened, ply, judged, facts, explored, found = (r.structured_content for r in results)
    assert opened["game"] == "g1" and opened["moves"][0]["grade"] is not None
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
            await client.call_tool("ply", {"game": "g1", "ply": 1}),
            await client.call_tool("ply", {"game": "g1", "ply": 99}),
        )

    refused, wrong = _run(tmp_path, body, Limits(max_uncached_plies=0))
    assert refused.is_error and "budget" in refused.content[0].text
    assert wrong.is_error and "plies 1 to 10" in wrong.content[0].text


def test_the_prompts_are_korean_and_the_resources_carry_the_build(tmp_path) -> None:
    async def body(client):
        prompt = await client.get_prompt("calliope_commentary", {"game": "g1", "ply": "33"})
        check = await client.get_prompt("calliope_check", {"game": "g1", "ply": "33"})
        definitions = await client.read_resource("calliope://definitions")
        glossary = await client.read_resource("calliope://glossary/ko")
        build = await client.read_resource("calliope://build")
        return prompt, check, definitions, glossary, build

    prompt, check, definitions, glossary, build = _run(tmp_path, body)
    text = prompt.messages[0].content.text
    assert "게임 g1, 수 33" in text and "ATTRIBUTED" in text
    assert "제출하기 전에" in check.messages[0].content.text
    registries = json.loads(definitions.contents[0].text)
    assert registries["definitions_v1"]["digest"] == REGISTRY_DIGEST
    assert registries["agent_definitions_v1"]["digest"] == AGENT_DIGEST
    assert json.loads(glossary.contents[0].text)["grades"]["blunder"] == "블런더"
    agent_build = json.loads(build.contents[0].text)
    assert agent_build["agent_definitions"] == AGENT_DIGEST
    assert set(agent_build["prompts"]) == {"commentary_ko_v1", "check_ko_v1"}
    assert len(agent_build["reasoning_build"]) == 64
