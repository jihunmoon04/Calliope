"""AG5-D §9: the guidance an agent reaches by itself — the instructions, the guide resources, the
tool descriptions, the refusal of a prefixed kind, `definitions`' search and the guidance version
in the agent build. What a host shows its model is the host's (§2); these check what Calliope
sends."""

from __future__ import annotations

import hashlib
import re

import anyio
import pytest
from agent_helpers import G1, GAME, session

from calliope.agent.build import agent_build, find_definitions, guide, text
from calliope.agent.definitions import GUIDANCE_VERSION
from calliope.agent.propositions import KINDS, Refused, Verifier

pytest.importorskip("mcp", reason="the MCP SDK is the optional group `agent`")

from mcp import Client

from calliope.agent.server import GUIDE_URIS, INSTRUCTIONS, app_page, build_server
from tools.mcp.__main__ import VIEWER

COMMENTARY_GUIDE, CHECK_GUIDE = "calliope://guides/commentary_ko", "calliope://guides/check_ko"
# The digest of the instructions and every tool's description under `agent_guidance_v1` (§6). A
# change to them fails here: give it a new GUIDANCE_VERSION and pin the new digest with it.
PINNED = {"agent_guidance_v1": "2ff07c9e635007b8d38cbfd85951ea5820f24bd7dc68c8aafaacf1f294421a63"}


def _run(tmp_path, body):
    s = session(tmp_path)
    server = build_server(s, app_page(VIEWER))

    async def main():
        async with Client(server) as client:
            return await body(client)

    try:
        return anyio.run(main)
    finally:
        s.close()


def guidance_digest(instructions: str, tools) -> str:
    described = "\n".join(f"{t.name}\n{t.description}" for t in sorted(tools, key=lambda t: t.name))
    return hashlib.sha256(f"{instructions}\n{described}".encode()).hexdigest()


# -- the instructions -------------------------------------------------------------------------------


def test_the_instructions_give_the_order_the_kinds_and_where_the_method_is(tmp_path) -> None:
    async def body(client):
        uris = {str(r.uri) for r in (await client.list_resources()).resources}
        return client.instructions, uris

    instructions, uris = _run(tmp_path, body)
    assert instructions == INSTRUCTIONS
    for name in ("open_game", "ply", "judge_move", "facts", "explore", "submit_commentary",
                 "judgement", "claim", "engine_score", "engine_line", "proposition.judgement"):  # fmt: skip
        assert name in instructions, name
    named = set(re.findall(r"calliope://[a-z/_]+", instructions))
    assert named == {COMMENTARY_GUIDE, CHECK_GUIDE, "calliope://glossary/ko"}
    assert named <= uris  # every URI it names is listed
    assert (
        "calliope_commentary" in instructions and "calliope_check" in instructions
    )  # as the user's


# -- the guides -------------------------------------------------------------------------------------


def test_the_guides_are_listed_for_the_model_and_are_the_prompts_text(tmp_path) -> None:
    async def body(client):
        listed = {str(r.uri): r for r in (await client.list_resources()).resources}
        read = {
            uri: (await client.read_resource(uri)).contents[0].text for uri in GUIDE_URIS.values()
        }
        prompts = {name: (await client.get_prompt(name, {"game": "<game>", "ply": "<ply>"})).messages[0].content.text
                   for name in ("calliope_commentary", "calliope_check")}  # fmt: skip
        return listed, read, prompts

    listed, read, prompts = _run(tmp_path, body)
    for uri, priority in ((COMMENTARY_GUIDE, 1.0), (CHECK_GUIDE, 0.8)):
        entry = listed[uri]
        assert entry.mime_type == "text/markdown"
        assert (
            entry.annotations.audience == ["assistant"] and entry.annotations.priority == priority
        )
    assert read[COMMENTARY_GUIDE] == prompts["calliope_commentary"]  # character for character
    assert read[CHECK_GUIDE] == prompts["calliope_check"]
    assert "대상: 게임 <game>, 수 <ply>." in read[COMMENTARY_GUIDE]
    for body_text in read.values():
        assert (
            '{{"' not in body_text
        )  # no escaped brace is left: `.format` turned each into the one shown
    assert read[COMMENTARY_GUIDE] == guide("commentary_ko_v1")
    assert (
        '{"id": "p1", "kind": "judgement"' in read[COMMENTARY_GUIDE]
    )  # the escaped braces, as the prompt shows them
    assert text("commentary_ko_v1.md").count("{{") > 0  # the file itself is unchanged


# -- the descriptions -------------------------------------------------------------------------------


def test_the_descriptions_carry_the_essentials(tmp_path) -> None:
    async def body(client):
        return {t.name: t.description for t in (await client.list_tools()).tools}

    described = _run(tmp_path, body)
    assert (
        described["ply"].startswith("Start here for a ply") and COMMENTARY_GUIDE in described["ply"]
    )
    submit = described["submit_commentary"]
    listed = re.search(r"`kind` is one of (.+?) —", submit)
    assert listed is not None and tuple(listed.group(1).split(", ")) == KINDS
    assert (
        "never `proposition.<kind>`" in submit
        and 'definitions(ids=["proposition.<kind>"])' in submit
    )
    assert '"cites": [proposition ids]' in submit
    assert COMMENTARY_GUIDE in submit and CHECK_GUIDE in submit
    assert "calliope://definitions" not in submit  # it pointed to `proposition.*` there (§0)
    assert "an unknown kind answers with every kind" in described["definitions"]


# -- the refusal of a prefixed kind -----------------------------------------------------------------


@pytest.fixture
def s(tmp_path):
    s = session(tmp_path)
    s.open_game(pgn=GAME)
    yield s
    s.close()


def refusal(s, kind: str) -> Refused:
    with pytest.raises(Refused) as error:
        Verifier(s, s.game(G1)).verify({"id": "p", "kind": kind})
    assert error.value.field == "kind" and error.value.expected == list(KINDS)
    return error.value


def test_a_prefixed_kind_is_refused_saying_what_to_write(s) -> None:
    assert refusal(s, "proposition.judgement").problem == (
        "no proposition kind 'proposition.judgement': write 'judgement' "
        "('proposition.judgement' is the id of its definition)"
    )
    assert refusal(s, "proposition.engine_line").problem.endswith(
        ": write 'engine_line' ('proposition.engine_line' is the id of its definition)"
    )
    assert refusal(s, "foo").problem == "no proposition kind 'foo'"
    assert refusal(s, "proposition.foo").problem == "no proposition kind 'proposition.foo'"
    assert refusal(s, "proposition").problem == "no proposition kind 'proposition'"


# -- definitions --------------------------------------------------------------------------------------


def ids(answer: dict) -> list[str]:
    return [e["id"] for e in answer["definitions"]]


def test_a_query_of_several_words_finds_the_entries_with_every_word() -> None:
    both = ids(find_definitions(query="proposition move grade", limit=1000))
    assert "proposition.judgement" in both  # by its fields `move` and `grade` (re-review N3)
    assert all(
        "move" in e and "grade" in e
        for e in (
            " ".join([d["id"], d["statement"], *d.get("fields", ())]).lower()
            for d in find_definitions(query="proposition move grade", limit=1000)["definitions"]
        )
    )
    one = ids(find_definitions(query="proposition", limit=1000))
    assert set(both) <= set(one) and len(both) < len(one)
    assert (
        ids(find_definitions(query="calliope_commentary calliope_check", limit=1000)) == []
    )  # no entry holds both


def test_a_one_word_query_answers_as_before() -> None:
    answer = find_definitions(query="ATTRIBUTED")
    assert answer["total"] == len(
        [
            e
            for e in find_definitions(limit=10_000)["definitions"]
            if "attributed" in e["id"].lower() or "attributed" in e["statement"].lower()
        ]
    )
    assert "kinds" not in answer
    # one word looks at the id and the statement only, as before: `best_move` is only a field name of
    # proposition.judgement, found by a query of several words (§5.1)
    (judgement,) = find_definitions(ids=["proposition.judgement"])["definitions"]
    assert "best_move" in judgement["fields"] and "best_move" not in judgement["statement"]
    assert "proposition.judgement" not in ids(find_definitions(query="best_move", limit=1000))
    assert "proposition.judgement" in ids(find_definitions(query="best_move judgement", limit=1000))


def test_an_unknown_kind_answers_with_the_kinds_there_are() -> None:
    unknown = find_definitions(kind="agent_definition")
    every = sorted({e["kind"] for e in find_definitions(limit=10_000)["definitions"]})
    assert unknown["definitions"] == [] and unknown["total"] == 0 and unknown["kinds"] == every
    assert len(every) == 26 and "proposition" in every and "prompt" in every
    known = find_definitions(kind="proposition")
    assert known["total"] == 15 and "kinds" not in known


# -- the build ----------------------------------------------------------------------------------------


def test_the_guidance_is_in_the_agent_build_and_pinned(tmp_path) -> None:
    build = agent_build("r" * 64)
    assert build["guidance"] == GUIDANCE_VERSION == "agent_guidance_v1"
    assert set(build) == {
        "agent_definitions",
        "prompts",
        "glossary",
        "tools",
        "guidance",
        "reasoning_build",
    }

    async def body(client):
        return client.instructions, (await client.list_tools()).tools

    instructions, tools = _run(tmp_path, body)
    assert guidance_digest(instructions, tools) == PINNED[GUIDANCE_VERSION], guidance_digest(
        instructions, tools
    )
