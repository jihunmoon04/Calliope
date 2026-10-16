"""The MCP server (AG-D §2, A2): the session's tools, prompts and resources over the official SDK.

The process runs one tool call at a time (a lock, AG-D C9); the work runs in a worker thread so
progress notifications reach the client while a ply is analysed. Every refusal — budget, game id,
handle, input — is a tool error with its message. A game id lasts: it is derived from the game and
names it in every process (AG4-D G1); a handle lasts only in the process that served it (G4). With the viewer's page, `show_game` is an MCP
App tool bound to `ui://calliope/viewer.html` (AG3-D D9–D11); without it, a plain tool (D13).
"""

from __future__ import annotations

import json
import logging
from functools import partial
from pathlib import Path
from typing import Any

import anyio
import anyio.from_thread
import anyio.to_thread
from mcp.server.apps import Apps
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import Annotations, CallToolResult, TextContent

from .budget import BudgetError
from .build import agent_build, definitions_document, find_definitions, guide, text
from .definitions import TOOLS_VERSION
from .games import GameError
from .handles import HandleError
from .propositions import KINDS
from .session import AgentError, Session

# AG5-D §3: the working order, the kinds as submitted, where the method is, the rules that hold
# without it. A change here is a new GUIDANCE_VERSION (the pin test says so).
INSTRUCTIONS = """\
Calliope는 체스 수를 엔진과 사실 근거로 판정하고, 에이전트가 쓴 해설을 그 근거와 대조해 받아들이는 서버입니다.
해설은 이 서버가 준 정보로만, 한국어로 쓰세요.

한 수를 해설하는 순서:
1. open_game으로 게임을 엽니다(PGN, 또는 fen과 moves). 받은 게임 id를 계속 씁니다.
2. ply로 그 수의 등급·라벨·최선수·클레임을 읽습니다. 두지 않은 수는 judge_move로 판정합니다.
3. 쓰려는 근거를 확인합니다. ply의 클레임으로 충분하지 않은 "왜"는 facts·explore·judge_move로 비교해 답합니다: \
더 나은 수가 하고 이 수가 하지 못한 것.
4. 확인한 것을 명제로 만들고 문장마다 명제를 인용해 submit_commentary로 제출합니다. 거부되면 표시된 곳을 고쳐 다시 제출합니다.
판을 사용자에게 보여 주려면 show_game을 씁니다.

명제의 kind는 judgement, claim, engine_score, engine_line처럼 접두사 없는 이름입니다. proposition.judgement 같은 id는
그 kind의 정의(필드)를 definitions(ids=[...])로 찾는 이름이고, proposition은 등록부의 분류입니다. 둘 다 kind로 쓰지 않습니다.

해설을 쓰기 전에 리소스 calliope://guides/commentary_ko(방법: 명제 형식, 수·숫자 표기)를, 제출 전에
calliope://guides/check_ko(점검 목록)를 읽으세요. 용어는 calliope://glossary/ko, 모르는 정의는
definitions로 찾습니다. 프롬프트 calliope_commentary·calliope_check는 같은 지침을 사용자가 고를 때 쓰는 것입니다.

꼭 지킬 것: SUPPORTED라도 ATTRIBUTED가 실패한 득실은 이 수의 성과가 아닙니다. specific_line은 한 라인에서만
성립하고, 패턴은 배치일 뿐입니다. 직접 탐색한 라인(by: agent)은 엔진의 라인이 아닙니다. 숫자·수·칸은
인용한 명제의 값만 씁니다."""

GUIDE_URIS = {
    "commentary_ko_v1": "calliope://guides/commentary_ko",
    "check_ko_v1": "calliope://guides/check_ko",
}
SUBMIT_COMMENTARY = (
    "Submit a Korean commentary of a played ply (`ply`) or a judged move (`position` and `move`). "
    'A proposition is {"id", "kind", ...its fields}, verified against what this server process served. '
    f"`kind` is one of {', '.join(KINDS)} — never `proposition.<kind>`, which is the id of the kind's "
    'definition: definitions(ids=["proposition.<kind>"]) gives its fields. One judgement proposition '
    "must cite the subject's own judgement (from `ply` or `judge_move`). A sentence is "
    '{"text", "class": "sourced" | "interpretation", "cites": [proposition ids]}; its moves, scores, '
    "mates, squares and numbers must come from the propositions it cites. The method and examples: "
    "resource calliope://guides/commentary_ko; the checklist before submitting: calliope://guides/check_ko. "
    "Accepted: stored with its id. Refused: every violation, nothing stored."
)


VIEWER_URI = "ui://calliope/viewer.html"
APP_MARKER = '<script id="calliope-app" type="application/json">{"v": 1}</script>'
SHOW_GAME = """Show the game on Calliope's board to the user: a calliope_result_v1 document over the
plies already analysed (cached) in the server's cache — none is analysed, nothing is charged —
with each ply's newest current accepted commentary. `plies` ("17" or "15-20", at most 40);
default: the game's cached plies. Analyse plies first with `ply` or open_game's `plies`."""


def app_page(viewer: Path) -> str | None:
    """The viewer as the MCP App's page (AG3-D D9): `viewer/index.html` with the App marker before
    `</head>`; None, with a warning, when it cannot be read (D13)."""

    try:
        page = (viewer / "index.html").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        logging.getLogger(__name__).warning("no viewer page, show_game has no App: %s", error)
        return None
    head = page.find("</head>")
    if head < 0:
        logging.getLogger(__name__).warning("the viewer page has no </head>, show_game has no App")
        return None
    return page[:head] + APP_MARKER + "\n" + page[head:]


def build_server(session: Session, page: str | None = None) -> MCPServer:
    """The session's server; `page` is the App page (`app_page`) or None for a plain `show_game`."""

    lock = anyio.Lock()

    async def run(fn, *args, **kwargs) -> Any:
        async with lock:  # one tool call at a time per session (AG-D C9)
            try:
                return await anyio.to_thread.run_sync(partial(fn, *args, **kwargs))
            except (AgentError, BudgetError, GameError, HandleError) as error:
                raise ToolError(str(error)) from error

    async def show_game(game: str, plies: str | None = None) -> CallToolResult:
        document, summary = await run(session.show_game, game, plies)
        # the document only in structuredContent; content is the short text (AG3-D D10)
        return CallToolResult(content=[TextContent(type="text", text=summary)],
                              structured_content=document)  # fmt: skip

    show_game.__doc__ = SHOW_GAME
    extensions = []
    if page is not None:
        apps = Apps()
        apps.tool(resource_uri=VIEWER_URI, visibility=["model", "app"], name="show_game",
                  structured_output=False)(show_game)  # fmt: skip
        apps.add_html_resource(VIEWER_URI, page, name="calliope-viewer",
                               title="Calliope 뷰어", description="Calliope's board and its "
                               "AI commentary panel, as an MCP App")  # fmt: skip
        extensions.append(apps)
    server = MCPServer("calliope", instructions=INSTRUCTIONS, version=TOOLS_VERSION,
                       extensions=extensions)  # fmt: skip
    if page is None:
        server.tool(name="show_game", structured_output=False)(show_game)

    @server.tool()
    async def open_game(
        pgn: str | None = None,
        fen: str | None = None,
        moves: list[str] | None = None,
        plies: str | None = None,
        ctx: Context = None,
    ) -> dict[str, Any]:
        """Open a game: a PGN, or a start FEN and moves (SAN or UCI). Returns the game's id and
        the moves. The id (g- and 16 hex digits) is derived from the game: it stays valid across
        calls, conversations and server restarts, and opening the same game again gives it back;
        when two games share its digits it is given in full (g- and 64). `plies` ("17" or
        "15-20", at most 16 uncached) are analysed (cached plies are free, uncached ones count
        against the server's budget per 15 minutes) and get Calliope's grade, label and text."""

        def progress(done: int, total: int, message: str) -> None:
            if ctx is not None:
                anyio.from_thread.run(partial(ctx.report_progress, done, total, message))

        return await run(session.open_game, pgn, fen, moves, plies, progress)

    @server.tool()
    async def ply(game: str, ply: int) -> dict[str, Any]:
        """Start here for a ply: its grade, label, best move and claims; how to write its
        commentary: resource calliope://guides/commentary_ko. Calliope's analysis of a played
        ply: grade, label, evaluation, text, and the full claim graph (judgements, observations,
        claims with scope, effective scopes, evidence, relations, checks and findings). Every
        judgement, claim and search line has a `ref`. A ref lasts only in this server process;
        when one is refused or expired, read it again."""

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
        id, by kind, or by a text query. kind: e.g. proposition, use, sentence_class, token_rule,
        check, prompt; an unknown kind answers with every kind there is. A query of several words
        finds the entries holding every word (in the id, the statement or the field names).
        `proposition.<kind>` entries give the fields of a submitted proposition."""

        return find_definitions(ids, kind, query)

    @server.tool(description=SUBMIT_COMMENTARY)
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
        `move`). Every proposition is verified against what this server process served (kinds and fields:
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

    # AG5-D §4: the method for the agent, rendered from the prompts' own files.
    @server.resource(GUIDE_URIS["commentary_ko_v1"], name="commentary_guide", mime_type="text/markdown",
                     title="Calliope 해설 작성 지침",
                     description="How to reason about a move and write its commentary (Korean)",
                     annotations=Annotations(audience=["assistant"], priority=1.0))  # fmt: skip
    def commentary_guide() -> str:
        return guide("commentary_ko_v1")

    @server.resource(GUIDE_URIS["check_ko_v1"], name="check_guide", mime_type="text/markdown",
                     title="Calliope 해설 점검 목록",
                     description="How to check a commentary before submitting it (Korean)",
                     annotations=Annotations(audience=["assistant"], priority=0.8))  # fmt: skip
    def check_guide() -> str:
        return guide("check_ko_v1")

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
