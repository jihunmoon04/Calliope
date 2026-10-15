"""The MCP server (AG-D §2, A2): the session's tools, prompts and resources over the official SDK.

A session runs one tool call at a time (a session lock, AG-D C9); the work runs in a worker thread
so progress notifications reach the client while a ply is analysed. Every refusal — budget,
handle, input — is a tool error with its message.
"""

from __future__ import annotations

import json
from functools import partial
from typing import Any

import anyio
import anyio.from_thread
import anyio.to_thread
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .budget import BudgetError
from .build import agent_build, definitions_document, find_definitions, text
from .definitions import TOOLS_VERSION
from .handles import HandleError
from .session import AgentError, Session

INSTRUCTIONS = (
    "Calliope은 체스 수를 근거 중심으로 판정합니다. 해설은 이 서버가 제공한 정보로만 쓰세요: "
    "ply로 Calliope의 등급·라벨·클레임을 읽고, facts·explore·judge_move로 확인한 뒤 쓰세요. "
    "SUPPORTED라도 ATTRIBUTED가 실패한 득실은 이 수의 성과가 아니고, specific_line은 한 라인에서만 "
    "성립하며, 패턴은 배치일 뿐입니다. 직접 탐색한 라인(by: agent)은 엔진의 라인이 아닙니다. "
    "해설은 한국어로, 숫자·수·칸은 인용한 명제의 값만 씁니다. 자세한 방법은 프롬프트 "
    "calliope_commentary와 calliope_check, 용어는 calliope://glossary/ko에 있습니다."
)


def build_server(session: Session) -> MCPServer:
    server = MCPServer("calliope", instructions=INSTRUCTIONS, version=TOOLS_VERSION)
    lock = anyio.Lock()

    async def run(fn, *args, **kwargs) -> dict[str, Any]:
        async with lock:  # one tool call at a time per session (AG-D C9)
            try:
                return await anyio.to_thread.run_sync(partial(fn, *args, **kwargs))
            except (AgentError, BudgetError, HandleError) as error:
                raise ToolError(str(error)) from error

    @server.tool()
    async def open_game(
        pgn: str | None = None,
        fen: str | None = None,
        moves: list[str] | None = None,
        plies: str | None = None,
        ctx: Context = None,
    ) -> dict[str, Any]:
        """Open a game: a PGN, or a start FEN and moves (SAN or UCI). Returns the session's game
        id and the moves; `plies` ("17" or "15-20") are analysed (cached plies are free, uncached
        ones count against the session budget) and get Calliope's grade, label and text."""

        def progress(done: int, total: int, message: str) -> None:
            if ctx is not None:
                anyio.from_thread.run(partial(ctx.report_progress, done, total, message))

        return await run(session.open_game, pgn, fen, moves, plies, progress)

    @server.tool()
    async def ply(game: str, ply: int) -> dict[str, Any]:
        """Calliope's analysis of a played ply: grade, label, evaluation, text, and the full
        claim graph (judgements, observations, claims with scope, effective scopes, evidence,
        relations, checks and findings). Every judgement, claim and search line has a `ref`."""

        return await run(session.ply, game, ply)

    @server.tool()
    async def judge_move(game: str, position: dict[str, Any], move: str) -> dict[str, Any]:
        """Calliope's judgement of any legal move at a position of the game — played or not —
        answered as `ply` answers it. position: {"ply": n, "at": "before"|"after"} or
        {"from_root": [uci...]}."""

        return await run(session.judge_move, game, position, move)

    @server.tool()
    async def facts(
        game: str, position: dict[str, Any], families: list[str] | None = None
    ) -> dict[str, Any]:
        """The fact records of a position (default families: status, material, pieces). Pieces
        are named by identity: piece, colour, origin (its square at the game's start), square
        and type_now."""

        return await run(session.facts, game, position, families)

    @server.tool()
    async def explore(
        game: str,
        position: dict[str, Any],
        moves: list[str] | None = None,
        search: bool = False,
    ) -> dict[str, Any]:
        """Play a line of your own from a position (moves may be empty): each ply's move record
        and the material balance, the end position's status, pieces and exchange; with `search`,
        the end position's engine survey (MultiPV 5, depth 12). Your plies are marked
        by: agent, engine PV plies by: engine."""

        return await run(session.explore, game, position, moves, search)

    @server.tool()
    async def definitions(
        ids: list[str] | None = None, kind: str | None = None, query: str | None = None
    ) -> dict[str, Any]:
        """Entries of the definitions registries (definitions_v1 and agent_definitions_v1) by
        id, by kind, or by a text query."""

        return find_definitions(ids, kind, query)

    @server.tool()
    async def submit_commentary(
        game: str,
        propositions: list[dict[str, Any]],
        sentences: list[dict[str, Any]],
        agent: dict[str, Any],
        ply: int | None = None,
        position: dict[str, Any] | None = None,
        move: str | None = None,
        language: str = "ko",
    ) -> dict[str, Any]:
        """Submit a Korean commentary of a played ply (`ply`) or a judged move (`position` and
        `move`). Every proposition is verified against what this session served (kinds and fields:
        resource calliope://definitions, `proposition.*`); every sentence cites propositions, and
        its moves, scores, mates, squares and numbers must come from them. Class `sourced` or
        `interpretation`. Accepted: stored with its id. Refused: every violation, nothing stored."""

        return await run(session.submit_commentary, game, ply, position, move, language, agent,
                         propositions, sentences)  # fmt: skip

    @server.tool()
    async def commentary(
        game: str,
        ply: int | None = None,
        position: dict[str, Any] | None = None,
        move: str | None = None,
    ) -> dict[str, Any]:
        """The accepted commentaries of a ply (or a judged move), newest first, each with `stale`:
        whether the analysis it was accepted against is no longer the cached one."""

        return await run(session.commentary, game, ply, position, move)

    @server.prompt(name="calliope_commentary")
    def calliope_commentary(game: str, ply: str) -> str:
        """How to reason about a move and write its commentary (Korean)."""

        return text("commentary_ko_v1.md").format(game=game, ply=ply)

    @server.prompt(name="calliope_check")
    def calliope_check(game: str, ply: str) -> str:
        """How to check a commentary before submitting it (Korean)."""

        return text("check_ko_v1.md").format(game=game, ply=ply)

    @server.resource("calliope://definitions", mime_type="application/json")
    def definitions_resource() -> str:
        """definitions_v1 and agent_definitions_v1."""

        return json.dumps(definitions_document(), ensure_ascii=False)

    @server.resource("calliope://glossary/ko", mime_type="application/json")
    def glossary_resource() -> str:
        """glossary_ko_v1: the viewer's Korean names of grades, labels, pieces and scopes."""

        return text("glossary_ko_v1.json")

    @server.resource("calliope://build", mime_type="application/json")
    async def build_resource() -> str:
        """The agent build (AG-D §10)."""

        async with lock:  # it reads the engine slot: one caller at a time (AG-D C9)
            digest = await anyio.to_thread.run_sync(session.reasoning_digest)
        return json.dumps(agent_build(digest))

    return server
