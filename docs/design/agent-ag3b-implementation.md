# Agent — packet AG3b implementation: the MCP App and `show_game`

Status: **rev. 1 — awaiting independent review; the owner's check in HIMARI v3 deferred until it
supports MCP Apps (AG3-D Q3)**.
Date: 2026-10-15. Design: [`agent-ag3-design.md`](agent-ag3-design.md) rev. 4 (AG3-D: D9–D11, D13,
§4, §5 App and MCP). Base: `main @ e503cc5` (AG3a merged, PR #99).

## 1. Scope delivered

| Place | Change |
| --- | --- |
| `agent/session.py` | `Session.show_game(game, plies)`: a combined `calliope_result_v1` over the asked plies the ply cache holds — read with `PlyCache.get`, never analysed, nothing charged — through `with_commentary` (the AG2 rule: each ply's newest current commentary, with `display`), and its short Korean text; at most 40 plies (`SHOW_LIMIT`) |
| `agent/server.py` | `app_page(viewer)`: `viewer/index.html` with `<script id="calliope-app" type="application/json">{"v": 1}</script>` before `</head>`, or None with a warning (D13); `build_server(session, page)`: with a page, `show_game` is bound through the SDK's `mcp.server.apps.Apps` to `ui://calliope/viewer.html` (`_meta.ui.resourceUri`, visibility `["model", "app"]`) and the page is served as `text/html;profile=mcp-app`; without one, `show_game` is a plain tool. The tool returns a `CallToolResult` itself: the document in `structuredContent` only, `content` the short text; no output schema |
| `agent/definitions.py` | tools `agent_tools_v3` (`show_game` added) |
| `tools/mcp` | `--viewer` (default `viewer/` beside `tools/`), read once at start-up |
| `viewer/index.html` | the pure part: `appBridge` (§4), `showGameArguments`, `toolText`, `keptPly`; the page: with `#calliope-app` it starts the bridge instead of the HTTP API (no redirect, no file, no server), applies the host's theme and container dimensions, loads tool results, and the AI panel's 「해설 새로고침」 calls `show_game` through the host |

## 2. Choices and departures (for the reviewer)

- **A Calliope document is recognised by `schema`.** §4 says `structuredContent.format`; a
  `calliope_result_v1` document names itself in `schema` (`"schema": "calliope_result_v1"`) and has
  no `format`, so the bridge checks `schema`.
- **`ping` is answered `{}`.** The specification's lifecycle includes `ping` (a health check of
  the host); answering it −32601 as an unknown request (§4 step 6) would report a live View as
  broken. Every other request but `ui/resource-teardown` gets −32601.
- **After teardown the page also ignores what it receives**, not only sends nothing: a late reply
  of a dropped refresh, a late tool result.
- **The App's AI panel is always shown** (D3 hides it in file mode when no ply has a commentary):
  it holds 「해설 새로고침」, the only way to bring in a commentary submitted after the View opened.
  A ply without one shows 「이 수의 AI 해설이 없습니다」, as in server mode.
- **The theme switch, the file picker and 「새 분석」 are hidden in the App**, and a dropped file is
  ignored: the host owns the theme (`hostContext.theme`, re-applied on
  `host-context-changed`, never stored), and D11 turns the file picker off.
- **Sizes.** A container is flexible unless both `height` and `width` are fixed; then the page
  sends `size-changed` with its body's size, 100 ms after the last change seen by a
  `ResizeObserver` on the body, and only when the size changed. A fixed dimension is filled
  (`100vh` / `100vw`), a `maxHeight` / `maxWidth` applied (the specification's View behaviour).
- **`appInfo.version` is `VIEWER_VERSION = "1.0.0"`**: the viewer had no version.
- **`show_game` without `plies`** asks for the game's cached plies, so only a ply whose cache files
  exist but do not load is named as left out; with `plies`, every asked ply not shown is named.
- **Errors** are tool errors (`isError`, text only): no game, a range outside the game (the
  analysis server's rule and wording), more than 40 plies asked, more than 40 cached without
  `plies`, none of the asked plies cached; the last three in Korean, since the App shows them.
- **Cost.** `show_game` replays each cached ply (`game_result` checks every one): about 0.6 s a
  ply on the synthetic engine, 25 s for 40.

## 3. Test obligations (AG3-D §5, the AG3b part)

| Test | Where |
| --- | --- |
| `show_game` listed with `_meta.ui` (`resourceUri`, visibility); the resource listed and read as `text/html;profile=mcp-app`, the viewer with the marker once before `</head>`; a document that passes `schema_errors`, carries the stored commentary as `ai_commentary` with `display`, leaves the budget untouched; `content` the short text only; 0 cached plies → `isError` without `structuredContent`; a partly cached range → the cached plies, the others named; a missing viewer (and a page without `</head>`) → a plain tool and a warning | `tests/agent/test_server.py` |
| 1 and 40 cached plies → documents of 1 and 40 plies; 41 asked, or 41 cached without `plies` → the limit named; nothing charged | `tests/agent/test_show_game.py` (a game of 41 plies, cached once for the module) |
| the handshake order (`ui/initialize` → result → `initialized`), its parameters; a tool result loads the document, another tool's result shows its text, a cancellation; the host's theme and its change; size notifications debounced, only on a change, none for a fixed container; another window's message, a message that is not JSON-RPC, `tool-input-partial`, an unknown notification ignored; `ping` → `{}`, an unknown request → −32601; an `ui/initialize` error | `tests/viewer/test_viewer_app.py` (node, `check_app.js`) |
| refresh: `tool-input` `{"game": "g1", "plies": "15-20"}` kept → `tools/call` `show_game` with exactly those arguments → the updated document (a new `ai_commentary`) on the same ply; an `isError` result and a JSON-RPC error shown, the document kept; without `tool-input`, or with arguments that are not `show_game`'s, refresh disabled; a second click while pending sends nothing; teardown during a pending refresh: `{}` with its id, the observer disconnected, the timer cleared, the reply dropped, nothing sent after | same |

Besides the suite, the page was run in headless Chromium inside a fake host page (an iframe, the
host side of §4 in a few lines of script): the handshake, the host's dark theme, the hidden file
picker, size notifications, 「해설 새로고침」 disabled while pending and the new commentary on the
ply on screen, −32601 for an unknown request, `{}` for teardown. It is not part of the suite (no
browser in CI). And `python -m tools.mcp` was run over stdio with Stockfish 19: `show_game` bound
to the resource and answering a document of two plies; with `--viewer` at a missing folder, the
warning and a plain `show_game`.

Related tests run for this packet (the whole suite was not run): `tests/agent`, `tests/viewer`,
`tests/tools`, `tests/server`, `tests/results`, `tests/test_package_boundaries.py` (Stockfish 19)
— 445 passed.

## 4. Not in this packet

The owner's check of the App in an MCP host (HIMARI v3, once it supports MCP Apps).
