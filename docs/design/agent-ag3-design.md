# Agent — AG3-D design: the AI commentary panel and the MCP App

Status: **rev. 2 — independent review NOT_READY (B1–B4) applied (§8); owner questions decided (§7)**.
Date: 2026-10-15. Base: `main @ 6a2e464` (AG2 merged, PR #97). Inputs:
[`agent-mcp-design.md`](agent-mcp-design.md) (AG-D rev. 6 with AM1–AM5: O5, O6, A5, §5.3, §8, §12
row AG3); [`agent-ag2-implementation.md`](agent-ag2-implementation.md) (the stored record);
[`application-server-design.md`](application-server-design.md) (AS-D: the HTTP API, the viewer's
analyse panel); the static viewer `viewer/index.html`; the MCP Apps extension, SEP-1865, stable
specification `2026-01-26` (`modelcontextprotocol/ext-apps`, `specification/2026-01-26/apps.mdx`);
its reference SDK's message types (`ext-apps` `src/spec.types.ts`: `McpUiInitializeRequest`);
the MCP Python SDK 2.3.0 `mcp.server.apps`.

AG-D §12 gives AG3 one line: *the viewer's AI commentary panel (propositions shown as verified,
sentences as sourced or interpretation, stale ones apart); the MCP App (`ui://`)*, gated by the
owner's check. This document fixes what that line leaves open: where the data comes from, what the
panel shows and how, how stale and judged commentaries are placed, and how the same viewer
becomes an MCP App.

## 1. Goals and non-goals

Goals.

- **G1** A reader of a game in the viewer sees, for each ply, the newest current accepted AI
  commentary beside Calliope's own text, and can tell at a glance what Calliope verified (the
  propositions), what the agent wrote from them (`sourced`), and what is only the agent's reading
  (`interpretation`, O6).
- **G2** Nothing the agent wrote is ever presented as Calliope's: the agent's sentences are shown
  as the agent's, under its name; only the propositions, rendered from their verified fields, are
  shown as verified (A5).
- **G3** The same page works in an MCP host as an MCP App, so an agent's user sees the board and
  the commentary in the conversation.

Non-goals: editing, deleting or rating commentary from the viewer; asking the agent for a
commentary from the viewer (the agent runs in an MCP host, not in the page); authentication (AS-D
S8 stands); any change to `calliope_result_v1`, the commentary record or the routes of AG2.

## 2. Decisions

| # | Decision |
| --- | --- |
| D1 | **Server mode reads the listing route.** After the result loads, the viewer fetches `GET api/games/{id}/commentary` (`ai_commentary_list_v1`, `no-store`) and keeps the plain result route (stored bytes, `immutable`) unchanged. The listing carries what the panel needs and the combined document does not: older commentaries, `stale`, judged moves. A button 「해설 새로고침」 fetches the listing again (an agent may submit while the page is open); nothing polls. |
| D2 | **File and embedded mode read `plies[].ai_commentary`** of the document (a combined document from `explain_game --with-commentary`, the MCP App's document, D9). Only the newest current commentary exists there; the panel shows it and no "other commentaries" section. |
| D3 | **One panel, `#ai`, below the ply panel** in the side column (the phone layout keeps the same order). It is hidden when the document has no commentary for any ply and the page is not in server mode; in server mode it shows 「AI 해설이 없습니다」 for a ply without one. |
| D4 | **The main commentary of a ply** is the newest record with `stale: false` (server mode) or the ply's `ai_commentary` (D2). Its header names the agent (`agent.name`, `agent.model`), the time (`created`, local time) and a level badge 「출처 확인」 with one fixed line: 「명제는 Calliope 데이터로 확인했습니다. 문장은 인용한 명제의 수·평가·칸·숫자만 확인했고, 해석은 에이전트의 의견입니다.」 It never uses Calliope's grade colours or the word 검증 for the sentences. |
| D5 | **Sentences** in order. `sourced`: plain text, then its citations as chips (`p1`, `p2`). `interpretation`: set apart (a left rule, a muted colour) with the tag 「해석」. A sentence with `by_agent: true` gets the tag 「에이전트 탐색」 (S6): it rests on a line the agent played itself, not on the engine. |
| D6 | **Propositions** — 「확인된 명제 N개」, open by default — are rendered from the record's verified fields only, never from agent text, with one Korean line per kind (§3). A chip of a sentence highlights its proposition; a proposition lists the sentences that cite it. |
| D7 | **Board preview.** A proposition that names a position or a line shows it on the board through the existing preview strip (the one Calliope's underlined segments use), from its `display` (D14) only: a position kind marks its squares on `display.fen`; a line kind steps through `display.uci` from `display.fen` with `display.san` as captions. Hover previews, a click pins, Esc clears — as for Calliope's segments. A proposition without `display` has no preview. |
| D8 | **Other commentaries of the ply** — older current ones, and stale ones apart — sit under a closed 「다른 해설 N개」. A stale one (`stale: true`) is labelled 「다른 분석 기준」: it was accepted against another analysis of the ply (another build or engine), and its propositions may not hold for the analysis on screen. A commentary with `stale: null` on a ply the job did not analyse is shown on that ply labelled 「분석 범위 밖」. A judged move's commentary (`judged`, AG-D §8, subject path `P + m`) is placed by its path, never by its length: when `P` is the played path to ply k (`P == played[:k]`, k ≥ 0), it belongs to the panel of ply k's position — the start position's panel for k = 0 — as 「두지 않은 수 <SAN>에 대한 해설」 under the same closed section; when `P` leaves the played game anywhere (`judge_move` from a `from_root` variation, e.g. `1.d4 d5 2.Nf3` judged in a game `1.e4 e5 2.Nf3`), it is shown in a game-level closed section 「본선 밖 해설 N개」 at the foot of the panel on every ply, each entry with its own preview of `P`'s position and the move `m` (D7, from `display.subject`). |
| D9 | **The MCP App is the viewer.** The `ui://calliope/viewer.html` resource is `viewer/index.html`, read when the MCP server starts, with one element added before `</head>`: `<script id="calliope-app" type="application/json">{"v": 1}</script>`. A page with that element speaks the MCP Apps protocol (§4) instead of the HTTP API; the page stays one file with two hosts. |
| D10 | **A new tool `show_game(game, plies?)`**, bound to the resource (`_meta.ui.resourceUri`, visibility `["model", "app"]`). It returns, as `structuredContent`, a `calliope_result_v1` combined document over the requested plies that are **cached** — none is analysed, nothing is charged — with each ply's newest current commentary as `ai_commentary` (the AG2 combined-document rule over the session's cache) and its `display` (D14). `plies` (a range as `open_game`'s) defaults to the game's cached plies; at most 40 in one answer. The tool returns a `CallToolResult` itself, so the document is only in `structuredContent` and `content` holds one short Korean text (the SDK would otherwise serialise a returned object into `content` too): the game, the plies shown, those requested but not cached, and per ply the grade and whether a commentary is attached. **Errors** (`isError: true`, text only, no `structuredContent`): no requested ply is cached — the schema needs at least one ply, so no document is built, and the text says to call `ply` first; more than 40 plies requested or cached without `plies` — the text names the limit and asks for a range. |
| D11 | **No network in the App.** The page is inline (scripts and styles in the file), so the host's restrictive default CSP (`connect-src 'none'`) suffices and the resource declares no `csp`. In App mode the analyse panel, the file picker, the game list and the listing route are off; 「해설 새로고침」 calls `tools/call show_game` with the same arguments through the host (allowed by `"app"` visibility). |
| D12 | **Escaping.** Every string from a commentary record — sentences, agent name and model, ids — goes through the viewer's `esc`; nothing is parsed as HTML or Markdown; no link is made from agent text. A record the viewer cannot read (a missing field) is skipped, as the store skips it (AG2 §6 B1). |
| D14 | **The server writes the moves for display (`display_v1`); the viewer computes no SAN.** The viewer has no move generator (`applyUci` moves pieces; SAN comes from the documents), and the stored propositions hold UCI. `calliope.server.commentary` adds to each proposition, when it reads a record for an answer, a `display` object computed with python-chess from the game's start FEN — never stored, the record unchanged: `fen` (the position the proposition speaks of: its `position`, a line's start — a search line's address FEN, an explored line's `from` path —, the judged move's position), `uci` and `san` (its move or its line, SAN with check and mate marks at each position), and for `after_reply` one `display` per side; a record's `subject` gets `display.subject` the same way (D8). The listing route, the combined document (`with_commentary` reads `game.start_fen`) and `show_game` all pass through it. A proposition whose moves do not replay (a damaged record) gets no `display` and is shown with its UCI and 「표시할 수 없음」. The schema's `AiCommentary.propositions[]` gains the optional `display` (an AR-D amendment recorded by AG3a). |
| D13 | **A missing viewer degrades.** `tools/mcp` passes the viewer path (`--viewer`, default `viewer/` beside `tools/`). If the file cannot be read at start-up, the server registers `show_game` as a plain tool (text and `structuredContent`, no `_meta.ui`) and logs a warning; it never fails to start for the App. |

## 3. Propositions as shown (D6)

One line per kind, from the verified fields; moves are written with the SAN of `display` (D14),
numbered from `display.fen`; without `display`, the stored UCI; `by: agent` lines carry the tag
「에이전트 탐색」.

| Kind | Line (example) | Preview (D7) |
| --- | --- | --- |
| `judgement` | 판정: 17.Ne3 — 최선, 최선수 17.Ne3 (라벨이 있으면 라벨) | — |
| `claim` | 주장 `fork_v2` (확인됨) — 사용: 수순 사실 (`line_fact`), 범위: 한 수순 | — |
| `engine_score` | 엔진 평가: 17.Kd1 이후 +8.95 (깊이 12) | the move |
| `engine_line` | 엔진 수순: 17...Rxe3 18.fxe3 | the line |
| `material` | 기물 득실: 수순 1–3수, 백 +2 | the line |
| `explored_line` | 에이전트 수순: 18.Nc3 Nxd5 … | the line |
| `definition` | 정의: `REFUTED` | — |
| `attack` / `defence` | 공격: e4 → d5 / 방어: d8 → d5 | the position, both squares |
| `exposed` | 노출: g5 (노출됨, 이득 3) | the position, the piece |
| `pin` | 핀: c3 (b4가 고정) | the position, both squares |
| `check` | 체크: b4 / 체크 아님 | the position, the checkers |
| `legal_moves` | 합법수 20개 (or the moves) | the position |
| `pattern` | 배치 `multi_target_attacks`: c7 → e8, a8 (배치일 뿐) | the position, the participants |
| `after_reply` | 응수 비교: 같은 응수 Nf6 뒤 — A: 공격 f6 → d5 / B: 공격 f6 → e4 | each side's position |

The grade and label names are the viewer's (`GRADES`, `LABELS`); the use and scope names follow
the glossary `glossary_ko_v1.json`; an unknown kind (a newer record) shows its `kind` and id only.

## 4. The App protocol (D9–D11)

JSON-RPC 2.0 over `postMessage` to `window.parent`, per SEP-1865 (2026-01-26), implemented inline
in the viewer (no SDK; the specification shows the bare form):

1. On load with `#calliope-app`, the page sends `ui/initialize` with `protocolVersion:
   "2026-01-26"`, `appInfo` (`{"name": "calliope-viewer", "version": <the viewer's>}`) and
   `appCapabilities: {"availableDisplayModes": ["inline", "fullscreen"]}`, waits for the result,
   applies `hostContext.theme` (light/dark, the page's existing theme switch) and sends
   `ui/notifications/initialized`.
2. `ui/notifications/tool-result`: if `structuredContent.format` is `calliope_result_v1`, the page
   loads it as it loads a file; otherwise it shows the `content` text. `ui/notifications/tool-cancelled`
   shows 「취소되었습니다」. `ui/notifications/host-context-changed` re-applies the theme.
   `tool-input` and `tool-input-partial` are ignored.
3. The page sends `ui/notifications/size-changed` (height, width) from a `ResizeObserver`,
   debounced, when the host's container is flexible; it fills a fixed container.
4. `ui/resource-teardown` (a request from the host before it removes the View): the page
   disconnects its `ResizeObserver`, clears its debounce timer, drops pending replies of its own
   requests, and answers the request's id with the result `{}`; after it, the page sends nothing.
5. Messages are accepted only from `window.parent`; a reply is matched by its id; an unknown
   notification is ignored, and an unknown request is answered with the JSON-RPC error `-32601`
   (method not found), so a host never waits on it. A request the host answers with an error shows
   it in the page's error line.

## 5. Tests

- **Viewer (node, `tests/viewer/check.js`):** the proposition lines of §3 for one record of each
  kind; sentence classes and tags (`sourced`, `interpretation`, `by_agent`); escaping of a sentence
  and an agent name holding `<script>`; the main/other split of D4 and D8 over a listing with a
  current, an older current, a stale, an out-of-range and a judged record; judged placement (D8):
  a judged move from the played path at ply k, from the start position (k = 0), and from a
  `from_root` variation that leaves the game (shown under 「본선 밖 해설」, on no ply); a record
  missing a field skipped; a proposition without `display` shown with UCI; the preview frames of
  D7 for a position kind and a line kind against python-chess.
- **Display (`tests/server`):** `display_v1` for each kind against python-chess SAN (a
  disambiguated knight move, a check, a mate, a promotion, castling), a search line from its
  address FEN, an explored line from its `from` path, `after_reply` per side, `subject` of a
  played, a judged and an off-game subject; a damaged proposition gets none; the listing route and
  the combined document carry it and validate with `schema_errors`; the stored file unchanged.
- **Viewer and server (`check_server.js`):** server mode fetches the listing after the result, the
  refresh button fetches it again, a 409 or a network error leaves the panel with a message and the
  board working.
- **App (node):** a fake parent window: the handshake order (`ui/initialize` → result →
  `initialized`), a tool result loads the document, a non-Calliope result shows its text, theme
  from the host context, messages from another source ignored, size notifications sent; teardown:
  `ui/resource-teardown` answered `{}` with its id, the observer disconnected, and no message sent
  after it; an unknown request answered `-32601`.
- **MCP (`tests/agent/test_server.py`):** `show_game` listed with `_meta.ui.resourceUri`;
  `resources/read` of `ui://calliope/viewer.html` gives `text/html;profile=mcp-app` and the page
  with `#calliope-app`; `show_game` returns a document that passes `schema_errors`, carries the
  stored commentary as `ai_commentary` with `display`, and leaves the budget untouched; `content`
  is the short text only (the document is not in it); 0 cached plies → `isError` with no
  `structuredContent`; 1 and 40 cached plies → a document of 1 and 40 plies; 41 → `isError`
  naming the limit; requested plies partly cached → the cached ones, the others named in the
  text; a missing viewer file → a plain tool (D13).
- **Owner's check (AG-D §12):** the panel on a served game with commentary (desktop and phone
  width) and the App in an MCP host that supports MCP Apps.

## 6. Packets

| Packet | Content | Gate |
| --- | --- | --- |
| AG3-D (this) | the panel, the App, `show_game` | independent review READY |
| AG3a | `display_v1` in `calliope.server.commentary` (D14) and its schema amendment; the viewer panel (D1–D8, D12); their tests | independent review; owner's check of the panel |
| AG3b | the MCP App (D9–D11, D13): the bridge in the viewer, `show_game`, the resource, `tools/mcp --viewer`, its tests | independent review; owner's check in HIMARI v3 deferred until it supports MCP Apps (Q3) |

## 7. Owner questions — decided (owner, 2026-10-15)

| # | Question | Decision |
| --- | --- | --- |
| Q1 | AG-D §8 says the panel shows only `stale: false`; AG-D §12 says "stale ones apart". Show stale and out-of-range commentaries at all? | As recommended: apart, closed and labelled (D8); hiding them would lose an accepted commentary from view while it stays in the store. |
| Q2 | The App's tool: a new `show_game` (D10), or bind the existing `commentary` tool to the UI? | As recommended: `show_game`; the model decides when a board is worth showing, and `commentary` stays a data tool. |
| Q3 | Which MCP host will the owner check the App in? | The owner's agent HIMARI v3, in development: it speaks MCP but not yet MCP Apps. AG3b is built and reviewed against the specification and its node tests; the owner's check of the App follows when HIMARI's client side supports Apps. AG3b's gate is therefore its independent review, with the owner's check deferred (§6). |

## 8. Review dispositions (rev. 1 `4e3e86a`, independent review: NOT_READY)

The review passed the compatibility with AG-D and AG2, the split of propositions, sourced
sentences and interpretation, and the data flow of server and file mode.

| Finding | Disposition |
| --- | --- |
| **B1** the viewer cannot write SAN for a variation: `applyUci` only moves pieces, the move list uses the documents' SAN, and `engine_line`, `explored_line` and `material` store UCI only | Accepted: the server writes it (D14, `display_v1`, computed with python-chess when a record is read, never stored); the viewer computes no SAN and shows UCI where `display` is missing (§3, D7). Tests (§5, Display) |
| **B2** a judged move's commentary was placed by the length of its path; `judge_move` from a `from_root` variation judges a position the game never reached | Accepted (D8): placed on ply k only when its path before the move is the played path to ply k (k = 0: the start position); otherwise under 「본선 밖 해설」 at game level, with its own preview of the position and the move. Tests (§5) |
| **B3** `show_game` with no cached ply would put a document with empty `plies` (schema `minItems: 1`) in `structuredContent` | Accepted (D10): an `isError` text answer with no `structuredContent`; tests for 0, 1, 40 and 41 plies and a partly cached range |
| **B4** `ui/resource-teardown` (a host request before removing the View) was ignored as an unknown method, leaving the host waiting | Accepted (§4 step 4): the observer and timer are stopped, pending replies dropped, `{}` answered with its id, nothing sent after; an unknown request gets `-32601`. Tests (§5) |
| (recommendation) the SDK may serialise a returned object into `content` as well | Accepted (D10): `show_game` returns a `CallToolResult` itself — the document in `structuredContent` only, `content` one short Korean text. Test |
| (recommendation) AG-D §8 says the panel shows only `stale: false`, D8 shows other ones apart | Accepted: AG-D amendment AM6 aligns §8 with D8 and records D14's `display` on the routes |
