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
from typing import Annotated, Any

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

# AG5-D §3 as AG6-D §7 amends it for one ply: the working order, the kinds as submitted, where the
# method is, the rules that hold without it. A change here is a new GUIDANCE_VERSION (the pin test
# says so).
INSTRUCTIONS = """\
Calliope는 체스 수를 엔진과 사실 근거로 판정하고, 에이전트가 쓴 해설을 그 근거와 대조해 받아들이는 서버입니다.
해설은 이 서버가 준 정보로만, 한국어로 쓰세요. 분석되지 않은 수는 기억으로 해설하지 않습니다.

대국을 분석하는 순서:
1. open_game으로 게임을 열고 analyze_game으로 모든 수의 분석을 시작합니다. 끝날 때까지 analyze_game(wait_seconds)으로 \
기다립니다.
2. game_overview로 흐름과 중요한 장면(moments)을 봅니다.
3. 장면마다 ply로 요약을 읽고, 필요한 "왜"는 detail·judge_move·explore로 확인합니다. 모든 장면을 읽은 뒤에 씁니다.
4. 해설은 submit_commentary(items)로 저장해야 판에 나타납니다. 장면이 많으면 4~5개씩 나눠 저장하고, 장면마다 \
가이드의 분량(핵심 장면 5~9문장)을 지킵니다. 저장한 뒤 show_game으로 판을 보여 주고, 채팅에는 짧은 요약만 씁니다.
분석이 거부되거나 끝나지 않은 수는 기억으로 해설하지 말고, 기다리거나 분석되지 않았다고 말합니다.
200수가 넘는 대국은 game_overview와 show_game을 200수 범위(plies)로 나누어 봅니다. 중요한 장면은 대국 전체에서 \
골라집니다.

한 수를 해설하는 순서:
1. open_game으로 게임을 엽니다(PGN, 또는 fen과 moves). 받은 게임 id를 계속 씁니다.
2. ply로 그 수의 요약을 읽습니다: 등급·라벨·최선수·라인·클레임과 각 항목의 ref. 두지 않은 수는 judge_move로 \
판정합니다. 요약에 없는 근거(범위 전체, 증거, 관계, 긴 수순)는 detail(ref)로 읽습니다.
3. 쓰려는 근거를 확인합니다. ply의 클레임으로 충분하지 않은 "왜"는 facts·explore·judge_move로 비교해 답합니다: \
더 나은 수가 하고 이 수가 하지 못한 것.
4. 문장마다 근거를 인용해 submit_commentary로 제출합니다. 받은 근거는 cites에 핸들을 그대로 씁니다(판정 j, 클레임 c, \
라인 s, 판의 변화 b, 직접 둔 라인 x). 클레임은 기본 응답의 as의 역할로 저장됩니다. facts로 확인한 것은 명제로 만들어 \
인용합니다. 여러 수의 해설은 items로 제출합니다(많으면 4~5개씩). 거부되면 표시된 곳을 고쳐 다시 제출합니다.
해설은 submit_commentary로 저장해야 판에 나타납니다. 저장한 뒤 show_game으로 판을 보여 주고, 채팅에는 짧은 요약만
씁니다. 응답의 next는 다음에 할 일을 알려 줍니다.

명제의 kind는 judgement, claim, engine_score, engine_line처럼 접두사 없는 이름입니다. proposition.judgement 같은 id는
그 kind의 정의(필드)를 definitions(ids=[...])로 찾는 이름이고, proposition은 등록부의 분류입니다. 둘 다 kind로 쓰지 않습니다.

해설을 쓰기 전에 리소스 calliope://guides/commentary_ko(방법: 명제 형식, 수·숫자 표기)를, 제출 전에
calliope://guides/check_ko(점검 목록)를 읽으세요. 용어는 calliope://glossary/ko, 모르는 정의는
definitions로 찾습니다. 프롬프트 calliope_commentary·calliope_check는 같은 지침을 사용자가 고를 때 쓰는 것입니다.

꼭 지킬 것: SUPPORTED라도 ATTRIBUTED가 실패한 득실은 이 수의 성과가 아닙니다. specific_line은 한 라인에서만
성립하고, 패턴은 배치일 뿐입니다. 직접 탐색한 라인(by: agent)은 엔진의 라인이 아닙니다. 숫자·수·칸은
인용한 근거의 값만 씁니다."""

GUIDE_URIS = {
    "commentary_ko_v8": "calliope://guides/commentary_ko",
    "check_ko_v1": "calliope://guides/check_ko",
}
SUBMIT_COMMENTARY = (
    "Submit Korean commentary: one subject — a played ply (`ply`) or a judged move (`position` and "
    "`move`) — with its `propositions` and `sentences`, or several subjects in `items` "
    '([{"ply" | "position"+"move", "propositions", "sentences"}], at most 16), each verified and '
    "stored on its own and answered per item: accepted, duplicate, refused or not_stored. "
    'A proposition is {"id", "kind", ...its fields}, verified against what this server process served; '
    'a judgement or claim proposition may give only its handle — {"id", "kind": "judgement", '
    '"judgement": "<j ref>"}, {"id", "kind": "claim", "claim": "<c ref>", "use"} — and the server '
    f"fills the rest. `kind` is one of {', '.join(KINDS)} — never `proposition.<kind>`, which is the "
    'id of the kind\'s definition: definitions(ids=["proposition.<kind>"]) gives its fields. One '
    "judgement proposition must cite the subject's own judgement (from `ply` or `judge_move`). A "
    'sentence is {"text", "class": "sourced" | "interpretation", "cites": [proposition ids or handles]}; '
    "a handle this game served (j, c, s, b, x) may be cited as it is: it stands for the "
    "propositions the server builds for it (ids `<handle>:<part>`, so `propositions` may be left "
    "out; each counts toward the 32), and a claim cited without a `use` is stored with the one "
    "the digest shows as `as`. Its "
    "moves, scores, mates, squares and numbers must come from what it cites. At most 32 "
    "propositions and 64 KiB on the board per commentary. The method and examples: resource "
    "calliope://guides/commentary_ko; the checklist before submitting: calliope://guides/check_ko. "
    "Accepted: stored with its id; the same commentary again is not stored twice (duplicate). "
    "Refused: every violation, nothing stored."
)
DETAIL = (
    'One item a `ref` names, in full, exactly as `ply`\'s `view: "full"` projects it: a claim '
    "(scope, effective scopes, evidence, relations, checks, findings), a judgement (its lines with "
    "their PVs), a search line, a fact record or an explored line. Nothing is analysed or charged; "
    "a ref of another server process is refused."
)


VIEWER_URI = "ui://calliope/viewer.html"
APP_MARKER = '<script id="calliope-app" type="application/json">{"v": 1}</script>'
SHOW_GAME = """Show the game on Calliope's board to the user: a calliope_view_v1 document — the
whole game's moves, every ply's state (analysed, pending, failed, none) and the analysis job's
progress, with the records of the analysed plies of `plies` ("17" or "15-20", at most 200;
default: the first 200) and each one's newest current accepted commentary. It opens before any
ply is analysed; none is analysed here, nothing is charged. Analyse the game with analyze_game."""
ANALYZE_GAME = """Analyse a game's plies in the background of this server (all of them by default,
`plies` for a range; a game of at most 600 plies): the job's state — queued, running, waiting
(the hourly budget: it resumes by itself), done, failed or cancelled — with done/total, the plies
from the cache, failed_plies, the seconds per ply and the time left. `wait_seconds` (at most 240)
waits until the job ends or the time passes; call again to wait more. The same game and range
answer the same job; `cancel: true` stops it. Plies already analysed are free and kept across
restarts; the job's plies are charged to its own budget, not to ply's and explore's."""
GAME_OVERVIEW = """A game's overview, from what is analysed (nothing is analysed or charged): per
ply of `plies` (at most 200; default the first 200) its move, grade, label, score after it, the
best move when another was, and the loss; and the whole game's moments — at most 16 plies chosen
by rule (blunders, mistakes, misses, brilliant and great moves, the largest losses, turning points,
inaccuracies), each with its reasons. Read each moment with `ply`; comment any other ply as well."""


# AG6-D F12: every tool's `content` is its JSON without indentation; `structuredContent` the dict.
Answer = Annotated[CallToolResult, dict[str, Any]]


def answer(value: dict[str, Any]) -> CallToolResult:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return CallToolResult(content=[TextContent(type="text", text=text)], structured_content=value)


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


GUIDES = ("commentary_ko_v8", "commentary_min_v1")  # RX1-D §6: the min guide for arm A-min only


def _unrecorded(name: str, kind: str = "call"):
    return lambda fn: fn


def build_server(session: Session, page: str | None = None,
                 guide_name: str = "commentary_ko_v8") -> MCPServer:  # fmt: skip
    """The session's server; `page` is the App page (`app_page`) or None for a plain `show_game`;
    `guide_name` the commentary guide served at its resource and prompt (RX1-D §6)."""

    if guide_name not in GUIDES:
        raise ValueError(f"no guide {guide_name!r}; one of {', '.join(GUIDES)}")
    lock = anyio.Lock()
    # RX1-D §2: one `call` line per MCP tool call, a `read` line per resource or prompt read
    rec = session.recorder.wrap if session.recorder is not None else _unrecorded

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
    show_game = rec("show_game")(show_game)  # once, before either registration (review N3)
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
    @rec("open_game")
    async def open_game(
        pgn: str | None = None,
        fen: str | None = None,
        moves: list[str] | None = None,
        plies: str | None = None,
        ctx: Context = None,
    ) -> Answer:
        """Open a game: a PGN, or a start FEN and moves (SAN or UCI). Returns the game's id and
        the moves. The id (g- and 16 hex digits) is derived from the game: it stays valid across
        calls, conversations and server restarts, and opening the same game again gives it back;
        when two games share its digits it is given in full (g- and 64). `plies` ("17" or
        "15-20", at most 16 uncached) are analysed (cached plies are free, uncached ones count
        against the server's budget per 15 minutes) and get Calliope's grade, label and text."""

        def progress(done: int, total: int, message: str) -> None:
            if ctx is not None:
                anyio.from_thread.run(partial(ctx.report_progress, done, total, message))

        return answer(await run(session.open_game, pgn, fen, moves, plies, progress))

    @server.tool(description=ANALYZE_GAME)
    @rec("analyze_game")
    async def analyze_game(
        game: str,
        plies: str | None = None,
        wait_seconds: float = 0,
        cancel: bool = False,
        ctx: Context = None,
    ) -> Answer:
        # AG6-D §4.3: start or read the job under the tool lock, wait holding none, answer under it
        key = await run(session.analyze_start, game, plies, cancel)
        if wait_seconds and not cancel:

            def progress(done: int, total: int, message: str) -> None:
                if ctx is not None:  # every ply and every change of state (review N2)
                    anyio.from_thread.run(partial(ctx.report_progress, done, total, message))

            await anyio.to_thread.run_sync(partial(session.analyze_wait, key, wait_seconds,
                                                   progress), abandon_on_cancel=True)  # fmt: skip
        return answer(await run(session.analyze_answer, game))

    @server.tool(description=GAME_OVERVIEW)
    @rec("game_overview")
    async def game_overview(game: str, plies: str | None = None) -> Answer:
        return answer(await run(session.game_overview, game, plies))

    @server.tool()
    @rec("ply")
    async def ply(game: str, ply: int, view: str = "digest") -> Answer:
        """Start here for a ply: a digest of Calliope's analysis — grade, label, evaluation, the
        played and the best line, the claims with what each says, its part and the scope it holds
        in, each item with its `ref`; REFUTED claims are named. `board`: what the move changed, by
        the mover's side (threat, weakness, lost_defence), and for a move that is not the best the
        same reply after the best move, each with what it proves and propositions to cite as
        given. How to write its commentary: resource
        calliope://guides/commentary_ko. What the digest leaves out (full scopes, evidence,
        relations, longer PVs) is one `detail(ref)` away; `view: "full"` answers the whole claim
        graph (large: it may exceed a host's limit). A ref lasts only in this server process;
        when one is refused or expired, read it again."""

        return answer(await run(session.ply, game, ply, view))

    @server.tool()
    @rec("judge_move")
    async def judge_move(
        game: str, position: dict[str, Any], move: str, view: str = "digest"
    ) -> Answer:
        """Calliope's judgement of any legal move at a position of the game — played or not —
        answered as `ply` answers it (a digest; `view: "full"` the whole claim graph). position:
        {"ply": n, "at": "before"|"after"} or {"from_root": [uci...]}."""

        return answer(await run(session.judge_move, game, position, move, view))

    @server.tool(description=DETAIL)
    @rec("detail")
    async def detail(game: str, ref: str) -> Answer:
        return answer(await run(session.detail, game, ref))

    @server.tool()
    @rec("facts")
    async def facts(
        game: str,
        position: dict[str, Any],
        families: list[str] | None = None,
        view: str = "brief",
    ) -> Answer:
        """The fact records of a position (default families: status, material, pieces). Pieces
        are named by identity: piece, colour, origin (its square at the game's start), square
        and type_now. `view: "brief"` (the default) keeps in `pieces` only the pieces in play —
        exposed, in an exchange, attacked by a lesser piece, outnumbered, pinned, attacking, in
        check, on the last move's square — and names every piece it left out; `exchange` keeps the
        exposed pieces. `view: "full"` or `detail(ref)` gives the whole record."""

        return answer(await run(session.facts, game, position, families, view))

    @server.tool()
    @rec("explore")
    async def explore(
        game: str,
        position: dict[str, Any],
        moves: list[str] | None = None,
        search: bool = False,
        view: str = "brief",
        continue_with: str | None = None,
        length: int = 8,
    ) -> Answer:
        """Play a line of your own from a position (moves may be empty): each ply's move record
        and the material balance, the end position's status, pieces and exchange; with `search`,
        the end position's engine survey (MultiPV 5, depth 12). Your plies are marked
        by: agent, engine PV plies by: engine. The end position's records come in the brief view
        of `facts` unless `view: "full"`; the line's `ref` holds the whole answer. `ledger`: each
        ply in words (who moved what, what it took from whom), `captured` by each side, `net`
        material per side and for the line's first mover (+ = ahead), `end` (pieces that moved
        or left the board, the status), and with `search` the end score with the side it favours
        and the side to move's view. A line that ends the game answers its terminal status, not a
        search. `continue_with: "engine"` (with `search`) plays the end search's line on, up to
        `length` plies (1-16), without another search; those plies are `source: engine`."""

        return answer(await run(session.explore, game, position, moves, search, view,
                                continue_with, length))  # fmt: skip

    @server.tool()
    @rec("compare_lines")
    async def compare_lines(
        game: str, ply: int, length: int = 16, candidates: list[str] | None = None
    ) -> Answer:
        """The played move's line, the best move's line and the game's own continuation from the
        position before a ply, side by side: each line's moves, the material balance a ply (White's
        view, the position before the move = 0) and its end — the engine's score where it searched
        (`end_score` at ply `end_score_at`) and the next moves. A line that stops in the middle of
        an exchange is extended along that search. `root`: the played and the best move's scores at
        the position before the move. Cite a line's moves and material by its `ref` (an explored
        line) and a score by its `score_ref` (an engine line). length: 1 to 32 plies a line.
        Each line has its `ledger` (captured by each side, net material per side, the end).
        `candidates` (1-4 moves at the position before the ply): each played out with the
        engine's line, and a `ranking` of the played, best and candidate moves for the side to
        move — each scored by one search after the move in the mover's view (`for_mover`, + is
        better for it), `vs_played` against the move played; a move that ends the game is ranked
        from the board; a move the budget could not search is `unranked`. `root` is never
        ranked."""

        return answer(await run(session.compare_lines, game, ply, length, candidates))

    @server.tool()
    @rec("squares")
    async def squares(game: str, position: dict[str, Any], squares: list[str]) -> Answer:
        """Every attacker and defender of up to 8 squares, by name (upper case White, lower case
        Black): an occupied square's from its piece's record, an empty square's attackers by side.
        Pinned pieces are included and marked with their pinner; an attacker says whether it can
        legally move to the square now (`can_move_there`; null for the side not to move). At a
        ply's position after its move
        ({"ply": n, "at": "after"}), `changed_by_move` says which attackers and defenders the move
        removed, added and left. position: {"ply": n, "at": "before"|"after"} or
        {"from_root": [uci...]}. Cite a defence or an attack by `refs.pieces`."""

        return answer(await run(session.squares, game, position, squares))

    @server.tool()
    @rec("definitions")
    async def definitions(
        ids: list[str] | None = None, kind: str | None = None, query: str | None = None
    ) -> Answer:
        """Entries of the definitions registries (definitions_v1 and agent_definitions_v1) by
        id, by kind, or by a text query. kind: e.g. proposition, use, sentence_class, token_rule,
        check, prompt; an unknown kind answers with every kind there is. A query of several words
        finds the entries holding every word (in the id, the statement or the field names).
        `proposition.<kind>` entries give the fields of a submitted proposition."""

        return answer(find_definitions(ids, kind, query))

    @server.tool(description=SUBMIT_COMMENTARY)
    @rec("submit_commentary")
    async def submit_commentary(
        game: str,
        agent: dict[str, Any],
        propositions: list[dict[str, Any]] | None = None,
        sentences: list[dict[str, Any]] | None = None,
        ply: int | None = None,
        position: dict[str, Any] | None = None,
        move: str | None = None,
        language: str = "ko",
        items: list[dict[str, Any]] | None = None,
    ) -> Answer:
        # the description is SUBMIT_COMMENTARY (AG5-D §5.2, AG6-D §5)
        return answer(await run(session.submit_commentary, game, ply, position, move, language,
                                agent, propositions, sentences, items))  # fmt: skip

    @server.tool()
    @rec("commentary")
    async def commentary(
        game: str,
        ply: int | None = None,
        position: dict[str, Any] | None = None,
        move: str | None = None,
    ) -> Answer:
        """The accepted commentaries of a ply (or a judged move), newest first, each with `stale`:
        whether the analysis it was accepted against is no longer the cached one."""

        return answer(await run(session.commentary, game, ply, position, move))

    @server.prompt(name="calliope_commentary")
    @rec("calliope_commentary", "prompt")
    def calliope_commentary(game: str, ply: str) -> str:
        """How to reason about a move and write its commentary (Korean)."""

        return text(f"{guide_name}.md").format(game=game, ply=ply)

    @server.prompt(name="calliope_check")
    @rec("calliope_check", "prompt")
    def calliope_check(game: str, ply: str) -> str:
        """How to check a commentary before submitting it (Korean)."""

        return text("check_ko_v1.md").format(game=game, ply=ply)

    # AG5-D §4: the method for the agent, rendered from the prompts' own files.
    @server.resource(GUIDE_URIS["commentary_ko_v8"], name="commentary_guide", mime_type="text/markdown",
                     title="Calliope 해설 작성 지침",
                     description="How to reason about a move and write its commentary (Korean)",
                     annotations=Annotations(audience=["assistant"], priority=1.0))  # fmt: skip
    @rec("commentary_guide", "resource")
    def commentary_guide() -> str:
        return guide(guide_name)

    @server.resource(GUIDE_URIS["check_ko_v1"], name="check_guide", mime_type="text/markdown",
                     title="Calliope 해설 점검 목록",
                     description="How to check a commentary before submitting it (Korean)",
                     annotations=Annotations(audience=["assistant"], priority=0.8))  # fmt: skip
    @rec("check_guide", "resource")
    def check_guide() -> str:
        return guide("check_ko_v1")

    @server.resource("calliope://definitions", mime_type="application/json")
    @rec("definitions_resource", "resource")
    def definitions_resource() -> str:
        """definitions_v1 and agent_definitions_v1."""

        return json.dumps(definitions_document(), ensure_ascii=False)

    @server.resource("calliope://glossary/ko", mime_type="application/json")
    @rec("glossary_resource", "resource")
    def glossary_resource() -> str:
        """glossary_ko_v1: the viewer's Korean names of grades, labels, pieces and scopes."""

        return text("glossary_ko_v1.json")

    @server.resource("calliope://build", mime_type="application/json")
    @rec("build_resource", "resource")
    async def build_resource() -> str:
        """The agent build (AG-D §10)."""

        async with lock:  # it reads the engine slot: one caller at a time (AG-D C9)
            digest = await anyio.to_thread.run_sync(session.reasoning_digest)
        return json.dumps(agent_build(digest))

    return server
