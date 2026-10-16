# Agent — packet AG4 implementation: connection-independent game ids, process-local work state

Status: **rev. 4 — re-review of rev. 3 (`6c5ff5d`) NOT_READY (N2) applied (§7), with the owner's choice
of a facts API (F4-D AM1); earlier reviews applied (§5, §6); for re-review**.
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
- **A store hit is the store's own answer** (rev. 4, N2; the owner chose a facts API over dropping
  the search admission). §3.3 lists searched paths among a game's work state. Rev. 3 kept a
  process set keyed by (start, path) (N1). Both were keys of their own and missed a transposition
  that reaches one `EngineInput`. Now `FactEngine.survey_stored(root, profile)` (F4-D AM1) asks
  the store with `open`'s own input and key, and `FactEngine.stored_results` is its size. The
  agent keeps no set of its own:
  - **Admission:** a search the store holds is free; a miss needs one search left.
  - **Replacement:** the store is replaced just before an admitted miss runs, when it holds
    `max_store_results`.
  - **Irregular searches:** the store never holds one, so it is never a hit (B5).
  - **Restarts:** a restarted engine gets a new search engine, so a new, empty store (N1).
  This touches `calliope.facts`, outside AG4-D §4's list.
- **The store is replaced only for a search that is about to run** (rev. 2, B4): one that is not a
  store hit, was admitted, and has its line's facts. It happens just before the engine is asked,
  when the count has reached `max_store_results` (a hit adds no result). A refused search leaves
  the store as it is. An engine restart also means a new store (the search engine is per port), so
  every game's searched paths are cleared then too. Before, a restart left them stale, though the
  meter still refused the search.
- **Search trees are not counted as nodes** (rev. 2, B3). §3.1 counts "facts and search" trees in
  `max_nodes_total`. A survey's one-node search tree is not kept after the call (its result lives in
  the store, bounded by `max_store_results`), so the process holds only facts-tree nodes, and those
  are what is counted.
- **Room for handles is made for the handles not served before** (rev. 2, B1):
  `Handles.fresh(game, keys)` counts the distinct (kind, source, address) with no handle yet.
  Reading an item again at the limit needs no room.
- **A search handle is bound to its result** (rev. 2, B2). A regular search's `search_id` names
  its request, not its lines (`records.py`), so after a store reset the same id can carry another
  result. The search source therefore gains `lines`, the sha256 of the served lines' canonical
  JSON: another result gets other handles, the same result the same ones.
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
| Rev. 2 (B1–B5): reading an item again at the handle limit; another search result after a store reset gets other handles, the same result the same ones; 50 repeated searches leave the counted nodes equal to the facts tree's; a refused search keeps the store (the earlier search is still a hit); an irregular search is admitted again (refused by admission, not at the port) | `tests/agent/test_memory.py` |
| Rev. 3 (N1): one search request from two games is one store hit (no budget used, a full store not replaced); a restarted engine has no store hits (charged again, then refused by admission, not at the port) | `tests/agent/test_memory.py` |
| Rev. 4 (N2): a transposition to one engine input is one store hit (no budget, the full store kept); the store never holds more than its limit over nine searches; `FactEngine.survey_stored` and `stored_results` in the facts tests (F4-D AM1) | `tests/agent/test_memory.py`, `tests/facts/search/test_tree_engine.py` |
| The whole suite, and AG-D §11 test 10 (Stockfish end to end) on the new ids | §4 |

The existing agent, viewer, tool and server tests now take ids from `open_game` or from
`agent_helpers.gid` (the id a game gets with no clash). They no longer use `g1`.

## 4. Results

- Rev. 4, the whole suite with Stockfish 19, in one run on the committed code: **1417 passed**
  (21 min), none failed or skipped.
- Rev. 3, the whole suite with Stockfish 19, in one run on the committed code: **1412 passed**
  (21.5 min), none failed or skipped.
- Rev. 2, the whole suite with Stockfish 19 (`CALLIOPE_STOCKFISH_PATH` set), in one run on the
  committed code: **1410 passed** (21 min), none failed or skipped.
- Rev. 1: 1405 passed (1404 in the full run, 20.5 min; its one failure, `test_stockfish.py` still
  reading `budget.uncached` as a number, fixed and re-run alone: passed).
- A stdio check of `python -m tools.mcp` with Stockfish, through the SDK's stdio client: process 1
  opens the game with ply 1 analysed (`g-01923fd591c94f2d`). After it exits, process 2 resolves
  the same id: `ply` 1 is cached, `show_game` shows it, the budget is fresh. The old-style `g1`
  is refused, and the message says what a game id is.
- `ruff check` and `ruff format --check` on `src`, `tests` and `tools`: clean.

## 5. Review dispositions — rev. 1 (`6dadddd`), independent review: NOT_READY

| # | Finding | Disposition |
| --- | --- | --- |
| B1 | Room was made for every item served, reused handles included: at `max_handles` the same `ply` read again was refused | `Session._serve` makes room for `Handles.fresh(...)`, the items with no handle yet; analyses, facts, explored lines and search lines all serve through it |
| B2 | After a store reset, another result of the same search (same `search_id`) reused the old handles, whose items are the old result | The search source gains `lines`, the digest of the served lines; test with an engine whose result changes |
| B3 | `search_nodes` grew by one per search though the search trees are not kept | `search_nodes` removed; only facts-tree nodes are counted and checked (§2) |
| B4 | A full store was replaced before the budget refused the search, losing the hits it held | Admission first; the store is replaced in `_search`, just before an admitted search that is not a hit runs |
| B5 | An irregular search, which the store does not keep, was marked searched and skipped admission next time | A search marks its path as searched, and counts as a stored result, only when it is regular |

## 6. Review dispositions — rev. 2 (`c81d5ae`), re-review: NOT_READY

B1–B5 were found resolved.

| # | Finding | Disposition |
| --- | --- | --- |
| N1 | The store hit was judged by a per-game path set, but the store is the process's: a second game's search of the same request was refused for want of budget (or a full store replaced) though the store held it; after an engine restart the set still claimed hits the new store did not have | One process set keyed by (start FEN, path), emptied with the store and synced with the engine port before admission and before the search (§2). Tests: one request from two games is one free hit, the full store kept; after a restart the search is charged again and, with the window used, refused by admission |

## 7. Review dispositions — rev. 3 (`6c5ff5d`), re-review: NOT_READY

B1–B5 and N1 were found resolved.

| # | Finding | Disposition |
| --- | --- | --- |
| N2 | The agent's hit key (start FEN, path) was not the store's key: a transposition reaching one `EngineInput` was refused for want of budget though the store held it, and the set could outgrow `max_store_results` | The owner chose a facts API (2026-10-16): `FactEngine.survey_stored` and `stored_results` (F4-D AM1). The agent asks the store and keeps no set of its own (§2). Tests: a transposition is one free hit; the store size stays within its limit; the facts members in `test_tree_engine.py` |
