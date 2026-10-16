# Agent — packet AG4 implementation: connection-independent game ids, process-local work state

Status: **rev. 1 — for independent review**.
Date: 2026-10-16. Design: [`agent-ag4-design.md`](agent-ag4-design.md) rev. 4 (AG4-D: G1–G6, §2–§5;
owner decisions O1–O3). Base: `main @ 755a869` (AG4-D merged, PR #101).

## 1. Scope delivered

| Place | Change |
| --- | --- |
| `agent/games.py` (new) | Ids `g-<16 hex>` / `g-<64 hex>` (`game_id`, `parse_id`); the record `agent_game_v1` (`record_of`, `encode` = the key's canonical JSON); `Records`: `create` (temporary of its own, `fsync`, `os.link`, unlink; an existing record reused when its bytes are ours, refused as damaged otherwise, never replaced), `load` (validated), `keys(prefix)`; `damage(raw, key)`: every validity rule of §2.2; `from_record` and `pgn_tags` (§2.4); `GameError` |
| `agent/budget.py` | `Limits` with the ten fields of §3.1; `Window` (charges stamped with an injected clock, `retry_after` per C3); `Meter` over a window (`total` counts every search taken); `Budget`: per-call and per-window admission, refusals with `retry_after_seconds` (as text and as `BudgetError.retry_after_seconds`); `left()` gains `window_seconds` |
| `agent/handles.py` | 96-bit token (`token_hex(12)`); one handle per (game, kind, source, address); entries grouped by game, `drop(game)`, per-kind highest issued number; foreign, never issued and expired (`HandleExpired`) told apart without the entry (C8) |
| `agent/session.py` | `Session.held`: an LRU of games by key, each owning its facts tree, node counts, searched paths and (through `Handles`) its handles; `game(id, hold)` resolves per §2.3 (a short id always lists the records); `open_game` checks the input's UTF-8 size, parses, builds the record, works on `from_record` of it (or on the held game), admits, then creates the record and holds the game; `_room` applies the per-tree limit and evicts least recently used other games for `max_open_games`, `max_nodes_total` and `max_handles`; `analyses` is a bounded cache, `analysis(game, source)` reloads from the ply cache by path and bundle digests or raises `HandleExpired`; `resolve(ref, game)` for the verifier; the search engine's store is replaced past `max_store_results`, clearing every game's searched paths; `show_game` and `commentary` resolve without holding (G6); `clock` is a field |
| `agent/propositions.py` | handles resolved through `Session.resolve`; a `mechanism`'s analysis through `Session.analysis` |
| `agent/server.py` | `GameError` is a tool error; the module and the `open_game`, `ply` and `submit_commentary` descriptions say a game id lasts (derived from the game, the full form on a clash) and a handle lasts only in its process |
| `agent/definitions.py` | `budget.session_v1` replaced by `budget.window_v1` (the window, the per-call bound, the per-tree nodes, `retry_after_seconds`) |
| `agent/prompts/commentary_ko_v1.md` | the window and `retry_after_seconds`; keep using a game id; read again when a handle is refused or expired |
| `calliope.server` | exports `canonical`, `temporary_name` and `HEADERS` (no change in behaviour) |
| `tools/mcp` | the options of §3.1 (`--budget-window`, `--max-uncached-plies`, …, `--max-analyses`), one per `Limits` field; `--max-nodes` is gone |

## 2. Choices and departures (for the reviewer)

- **`budget.session_v1` → `budget.window_v1`.** §4 does not list `definitions.py`, but the old
  entry described a per-session budget that no longer exists, so `AGENT_DIGEST` changes.
  `TOOLS_VERSION` stays `agent_tools_v3`: tool names and arguments are unchanged (G5).
- **`GameError`** is its own exception (a tool error, exported). Unknown, malformed, ambiguous and
  damaged ids and a too large record raise it. A too large input text is an `AgentError`, like
  every other input refusal.
- **The default-curve warning text is repeated in `games.py`** (`FALLBACK`), since
  `calliope.server` does not export `pipeline.FALLBACK`. The corpus test compares it with
  `parse_game`'s warning. `open_game` still answers the input's own warnings (among them "only
  the first game"); a game built from its record carries only the default-curve warning.
- **A short id's candidates** are its records plus held games with that prefix whose record is
  gone. One candidate resolves; more than one is ambiguous. This is §2.3's "none … unless this
  process holds a game with that prefix and no other record exists", applied to every case.
- **The record's size is checked before any work** (cache checks, admission), so a refusal leaves
  nothing.
- **The result store's count** is the searches the meter took while opening search trees: each
  one is a regular search, so one stored result. The store is replaced **before a search that is
  not a store hit**, when the count has reached `max_store_results` (a hit adds no result). An
  engine restart also means a new store (the search engine is per port), so every game's searched
  paths are cleared then too. Before, a restart left them stale; the meter still refused the
  search.
- **Room for handles is made before serving, for an upper bound**: the items about to be served,
  without counting those that reuse a handle. A call can therefore evict, or be refused, slightly
  early.
- **One line, one handle.** A judgement whose played line is also its best line used to get two
  `s` handles for it. With G4's reuse it gets one. The uniqueness test now allows exactly that.
- **`budget_left.nodes`** is what the game's facts tree has left (`max_nodes_per_tree` minus its
  nodes). It used to be what was left of the session's 2000.
- **A foreign handle keeps the existing message** ("was not served in this session"), as G4 says.
  A never-issued one is "not a handle this server served". An expired one names the handle and
  what to do.
- **`Session.resolve` re-raises an analysis that cannot be reloaded** as
  `HandleExpired("<ref> expired: …")`.
- **The 10,000-call test** (`ply` on one ply) keeps the ply-cache load of the first call. A cached
  `ply` costs about 0.19 s here (the stored tree is replayed), so 10,000 real loads would take
  about half an hour. The serving path, handles included, runs in full on every call, and 20 real
  calls before it go through the ply cache.

## 3. Test obligations (AG4-D §5)

| Obligation | Where |
| --- | --- |
| Ids: one id in two sessions; `open_game` twice gives one id and one record; other headers give another id; a clash by hand: short id ambiguous even when held, full id resolves, `open_game` returns the full form | `tests/agent/test_games.py` |
| Records: two texts of one key opened by two processes at once leave one canonical record and no temporaries; an existing record is never replaced (same inode and mtime); each validity rule broken (23 cases) is refused for short and full ids and by `open_game`, and left as it is; a too large input (counted in UTF-8 bytes) and record | `tests/agent/test_games.py` |
| Resolution: a second session resolves; a removed or damaged record keeps serving in the holding process and is refused in another; no case serves another game | `tests/agent/test_games.py` |
| Budget (fake clock): charges leave the window; exact `retry_after_seconds` with several charges to expire; per-call and per-window limits independent; admission against the search bound; a refusal names what is left; the meter refuses and takes again once the window moves; a session's window refills; analysis cut short not cached and store hits free (kept) | `tests/agent/test_budget.py` |
| Memory: many games within the node and game limits; per-tree refusal; least recently used evicted, never the current, refusal when the game alone passes; evicted handles expire, the id still works; the store replaced past its limit | `tests/agent/test_memory.py` |
| Handles: another session's handle refused (kept, `test_session.py`); 10,000 `ply` calls add no handle; handles and analyses within `max_handles` and `max_analyses`; a dropped analysis reloaded, expired once the ply cache lost its digests; expired, never-issued and foreign messages; a 24-hex-digit token | `tests/agent/test_memory.py` |
| Read-only tools: with 16 games held and a handle of game A, `show_game` and `commentary` on 20 other games evict nothing, the LRU order is unchanged, and a commentary citing A's handle (also in `refs`) is accepted | `tests/agent/test_memory.py` |
| Store reset (C6): a repeated search charged again after the store is replaced, refused before the engine with the window empty | `tests/agent/test_memory.py` |
| The agent's game: 11 corpus cases (no FEN tag; `01500` / `?` ratings; chess.com, lichess, `?` time control on chess.com; `?` and `????.??.??` headers; comments and variations; the standard start as a FEN tag; a custom FEN with spaces; a takeable and an untakeable en passant square): another session's `from_record` equals the opener's game; `game`, `sans`, `uci`, `spec` and the key equal `parse_game`'s; per-ply `normalized_ply` equal, except the untakeable square, whose root is `start_fen`; `from_record` of the record gives the game back; a second session reads the analysis from the ply cache without a search | `tests/agent/test_games.py` |
| `pgn_tags`: `game_input` gives every header back; `grading_for` agrees with the original tags; headers not in normal form are damaged (among the 23 cases) | `tests/agent/test_games.py` |
| Id stability (C9): short id resolves, a clashing record appears, the short id is refused in the holding and in a fresh process, the full id resolves | `tests/agent/test_games.py` |
| Server: `show_game` through the MCP client for a game another process opened (also the App's refresh after a restart) | `tests/agent/test_memory.py` |
| Hosts: one process shared by two connections (one id, one budget: 15 then 14 uncached left) and one process per conversation (one id, two budgets: 15 each) | `tests/agent/test_memory.py` |
| The whole suite, and AG-D §11 test 10 (Stockfish end to end) on the new ids | §4 |

The existing agent, viewer, tool and server tests now take ids from `open_game` or from
`agent_helpers.gid` (the id a game gets with no clash). They no longer use `g1`.

## 4. Results

- The whole suite with Stockfish 19 (`CALLIOPE_STOCKFISH_PATH` set): 1405 passed (1404 in the
  full run, 20.5 min; its one failure, `test_stockfish.py` still reading `budget.uncached` as a
  number, fixed and re-run alone: passed).
- A stdio check of `python -m tools.mcp` with Stockfish, through the SDK's stdio client: process 1
  opens the game with ply 1 analysed (`g-01923fd591c94f2d`). After it exits, process 2 resolves
  the same id: `ply` 1 is cached, `show_game` shows it, the budget is fresh. The old-style `g1`
  is refused, and the message says what a game id is.
- `ruff check` and `ruff format --check` on `src`, `tests` and `tools`: clean.
