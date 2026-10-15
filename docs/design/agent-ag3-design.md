# Agent — AG3-D design: the AI commentary panel and the MCP App

Status: **rev. 1 — awaiting independent review**.
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
| D7 | **Board preview.** A proposition that names a position or a line shows it on the board through the existing preview strip (the one Calliope's underlined segments use): a position kind marks its squares on the position at `position` (a UCI path from the root); a line kind steps through its moves from the line's start (the FEN in its stored source address, or the explored line's `from` path). Hover previews, a click pins, Esc clears — as for Calliope's segments. |
| D8 | **Other commentaries of the ply** — older current ones, and stale ones apart — sit under a closed 「다른 해설 N개」. A stale one (`stale: true`) is labelled 「다른 분석 기준」: it was accepted against another analysis of the ply (another build or engine), and its propositions may not hold for the analysis on screen. A commentary with `stale: null` on a ply the job did not analyse is shown on that ply labelled 「분석 범위 밖」. A judged move's commentary (`judged`, AG-D §8) is shown on the ply whose position it starts from — the ply panel of the position before the move — as 「두지 않은 수 <SAN>에 대한 해설」, under the same closed section. |
| D9 | **The MCP App is the viewer.** The `ui://calliope/viewer.html` resource is `viewer/index.html`, read when the MCP server starts, with one element added before `</head>`: `<script id="calliope-app" type="application/json">{"v": 1}</script>`. A page with that element speaks the MCP Apps protocol (§4) instead of the HTTP API; the page stays one file with two hosts. |
| D10 | **A new tool `show_game(game, plies?)`**, bound to the resource (`_meta.ui.resourceUri`, visibility `["model", "app"]`). It returns, as `structuredContent`, a `calliope_result_v1` combined document over the requested plies that are **cached** — none is analysed, nothing is charged — with each ply's newest current commentary as `ai_commentary` (the AG2 combined-document rule over the session's cache); `plies` defaults to the game's cached plies, at most 40 in one answer (more is refused, naming the limit). Its `content` is a short Korean text for hosts without Apps: the game, the plies shown, and per ply the grade and whether a commentary is attached. |
| D11 | **No network in the App.** The page is inline (scripts and styles in the file), so the host's restrictive default CSP (`connect-src 'none'`) suffices and the resource declares no `csp`. In App mode the analyse panel, the file picker, the game list and the listing route are off; 「해설 새로고침」 calls `tools/call show_game` with the same arguments through the host (allowed by `"app"` visibility). |
| D12 | **Escaping.** Every string from a commentary record — sentences, agent name and model, ids — goes through the viewer's `esc`; nothing is parsed as HTML or Markdown; no link is made from agent text. A record the viewer cannot read (a missing field) is skipped, as the store skips it (AG2 §6 B1). |
| D13 | **A missing viewer degrades.** `tools/mcp` passes the viewer path (`--viewer`, default `viewer/` beside `tools/`). If the file cannot be read at start-up, the server registers `show_game` as a plain tool (text and `structuredContent`, no `_meta.ui`) and logs a warning; it never fails to start for the App. |

## 3. Propositions as shown (D6)

One line per kind, from the verified fields; moves are written in SAN at their position (computed by
the viewer from the stored UCI and the position, as for the move list); `by: agent` lines carry the
tag 「에이전트 탐색」.

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
4. Messages are accepted only from `window.parent`; a reply is matched by its id; an unknown method
   is ignored. A request the host answers with an error shows it in the page's error line.

## 5. Tests

- **Viewer (node, `tests/viewer/check.js`):** the proposition lines of §3 for one record of each
  kind; sentence classes and tags (`sourced`, `interpretation`, `by_agent`); escaping of a sentence
  and an agent name holding `<script>`; the main/other split of D4 and D8 over a listing with a
  current, an older current, a stale, an out-of-range and a judged record; a record missing a field
  skipped; the preview frames of D7 for a position kind and a line kind against python-chess.
- **Viewer and server (`check_server.js`):** server mode fetches the listing after the result, the
  refresh button fetches it again, a 409 or a network error leaves the panel with a message and the
  board working.
- **App (node):** a fake parent window: the handshake order (`ui/initialize` → result →
  `initialized`), a tool result loads the document, a non-Calliope result shows its text, theme
  from the host context, messages from another source ignored, size notifications sent.
- **MCP (`tests/agent/test_server.py`):** `show_game` listed with `_meta.ui.resourceUri`;
  `resources/read` of `ui://calliope/viewer.html` gives `text/html;profile=mcp-app` and the page
  with `#calliope-app`; `show_game` returns a document that passes `schema_errors`, carries the
  stored commentary as `ai_commentary`, and leaves the budget untouched; more than 40 plies
  refused; a missing viewer file → a plain tool (D13).
- **Owner's check (AG-D §12):** the panel on a served game with commentary (desktop and phone
  width) and the App in an MCP host that supports MCP Apps.

## 6. Packets

| Packet | Content | Gate |
| --- | --- | --- |
| AG3-D (this) | the panel, the App, `show_game` | independent review READY |
| AG3a | the viewer panel (D1–D8, D12), its tests | independent review; owner's check of the panel |
| AG3b | the MCP App (D9–D11, D13): the bridge in the viewer, `show_game`, the resource, `tools/mcp --viewer`, its tests | independent review; owner's check in an MCP host |

## 7. Owner questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | AG-D §8 says the panel shows only `stale: false`; AG-D §12 says "stale ones apart". Show stale and out-of-range commentaries at all? | Show them apart, closed and labelled (D8): hiding them loses an accepted commentary from view while it stays in the store. |
| Q2 | The App's tool: a new `show_game` (D10), or bind the existing `commentary` tool to the UI? | `show_game`: the model decides when a board is worth showing; `commentary` stays a data tool for the agent. |
| Q3 | Which MCP host will the owner check the App in? | One that implements MCP Apps (`2026-01-26`); AG3b's check needs it. If none is at hand, AG3b's node tests stand in until one is. |
