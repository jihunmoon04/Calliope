# Agent — AG4-D design: connection-independent game ids, process-local work state

Status: **rev. 4 — re-review of rev. 3 NOT_READY (N3, N4; C10) applied (§9); earlier reviews
applied (§7, §8); owner decided O2 and O3 as recommended; independent re-review of rev. 4
(`67f41e5`): mergeable (owner, 2026-10-15); amendment AM1 (§10, limit values)**. Date: 2026-10-15. Base: `main @ 61be8cc` (AG3b merged). Inputs:
[`agent-mcp-design.md`](agent-mcp-design.md) (AG-D: the session, §3.5 the budget, §3.6 handles,
§8 the game key, §9 two processes on one data directory); MCP
[2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/changelog) (SEP-2567,
SEP-2575); HIMARI V3-P59 (an MCP client that runs stdio servers, one process per server by
default).

Calliope's MCP server ties three things to the process it runs in, which is also its one
connection ("one session per connection", AG-D §2):
1. the game ids it hands out (`g1`, `g2`, … counted from 1 in every process);
2. the budget (16 uncached plies, 40 searches, 2000 nodes, used once and never refilled);
3. the handles (`c3.k7f2a9`: a random 24-bit token per process, so a foreign handle is refused).

Hosts run that process differently. Most start one process per server and share it across every
conversation. HIMARI does the same by default and can start one per conversation. Any host restarts
the process when it dies or has been idle. So the same agent sees different behaviour from host to
host, and two of the three are wrong:

- **An old id can name a new game.** After a restart, a game opened in the new process is `g1`
  again, and the agent's earlier `g1` silently names it. Its analysis is served as the old game's.
- **The budget runs out for good, or it can be dodged.** A shared process spends it for every later
  conversation. Per-conversation processes and restarts make it fresh every time.

The latest MCP revision (2026-07-28) removes protocol sessions: "Servers that need cross-call state
use explicit, server-minted handles passed as ordinary tool arguments".

AG4-D does three things:
- **Game ids are independent of the connection.** The same id names the same game in every
  process, or is refused; it never names another game.
- **The budget is a load limit of the process,** over a rolling window.
- **The work state of a process stays local and bounded:** trees, handles and analyses, evicted by
  a least-recently-used rule.

It is **not** a fully stateless server. Handles and trees stay per process (G4).

## 0. Owner decisions

| # | Decision |
| --- | --- |
| O1 | (2026-10-15) The server keeps no connection state that changes what an id means or how much an agent may spend: content-based game ids, and a budget not tied to the connection (HIMARI V3-P59 §5.7). |
| O2 | (2026-10-15, as recommended by the author and the rev. 1 review) The budget is **a local load limit of each process, not a global usage limit**: per 15 minutes, 16 uncached analyses and 40 searches; at most 16 uncached analyses per call. |
| O3 | (2026-10-15, as recommended) Handles stay process-local (G4). Game ids are 16 hex digits by default, and 64 when the short form is ambiguous (§2.1). Memory has a per-tree and a per-process limit with the defaults of §3.1 (§3.3). |

## 1. Decisions

| # | Decision |
| --- | --- |
| G1 | **A game id is derived from the game** (§2.1). The same game gets the same id everywhere. `open_game` on a game already opened returns its id; that is not an error. |
| G2 | **A game resolves from a record, not from memory.** The record is created once, if absent, and never replaced (§2.2). It holds the game's normalized form, so one key is always one content. An id with no record, a damaged record, or an ambiguous short id is refused with a message saying what to do. |
| G3 | **The budget is the process's, over a rolling window,** plus per-call bounds (§3). It limits the engine load one process takes. It does not count an agent's use across processes or hosts (O2). |
| G4 | **Handles and trees stay per process** (AG-D §3.6). A handle of another process is refused with the existing error. A handle of a game this process evicted is refused with "expired" (§3.3). The same item served again gets the same handle (§3.3). |
| G5 | **Nothing else changes.** Tools keep their names and arguments; only the value of `game` changes. The commentary store, the ply cache, the HTTP server and the viewer already key by `game_key`. |
| G6 | **Read-only tools change no work state** (`show_game`, `commentary`, `definitions`). They load no game into memory, evict nothing and serve no handles, so calling them, or not knowing whether they ran, changes nothing an agent relies on. This is the `read` contract of HIMARI V3-P59 §5.1 (review N2). |

## 2. Game ids and records

### 2.1 The id (review B1)

- **Short form:** `g-` + the first 16 hex digits of `game_key` (AG-D §8), lowercase, for example
  `g-3fa2c1d9e8b74a10`.
- **Full form:** `g-` + all 64 digits. Every tool that takes `game` accepts both.
- **What `open_game` returns:**
  - the short form, unless another record shares its first 16 digits;
  - the full form when another record does. The answer always carries `game_key` too.

  16 digits keep the id cheap to copy and hard to mistype. The full form exists only for the rare
  clash.
- **Resolving the short form always checks the record directory for clashes**, whether or not the
  game is in memory (§2.3). A short id is never resolved by memory alone.
- **Stability (review C9):**
  - **A full id always resolves** while its record exists, or while the process holds the game.
  - **A short id resolves until a clashing record appears.** It is refused as ambiguous from then
    on, in every process, and is never resolved to the other game. The refusal names the full
    forms to use.
  - An agent that must not be interrupted by a clash can always pass the full id.
- Opening the same game again (same start, moves and headers) returns the same id, re-reads nothing
  and charges nothing beyond what the call itself asks (`plies`).

### 2.2 The record (reviews B2, C5)

The record holds exactly the `game_key` preimage (AG-D §8), so one key has one content.

```json
{"v": "agent_game_v1", "game_key": "<64 hex>",
 "start_fen": "<FEN>", "moves": ["e2e4", "e7e5", "..."],
 "headers": {"white": "...", "white_rating": 1500, "time_control": "180+2", "...": "..."}}
```

`start_fen`, `moves` and `headers` are `GameInput`'s (`game_input`): the start as `board.fen()`,
moves as UCI, and the headers under their internal names (`pipeline.HEADERS`) with ratings as
integers and PGN's "unknown" values left out.

- **Encoded canonically.** It is written with the same canonical JSON as the key, so the bytes of a
  record are a function of its key. A PGN's comments, variations and spacing are not part of the
  key and are not kept. Two texts with one key therefore make one record.
- **Created once, never replaced:**
  1. Write the bytes to a unique temporary name (`server.files.temporary_name`), `fsync`.
  2. `os.link(temporary, <data>/agent/games/<game_key>.json)`. This creates the record only if
     absent; an existing one makes it fail with `EEXIST`.
  3. Unlink the temporary.
  4. On `EEXIST`, read the existing record and compare its bytes with ours.
     - **Equal:** reuse it.
     - **Different:** it is damaged; refuse, and leave it as it is.

  `os.replace` is never used on a record, so no record is ever overwritten. Concurrent openers of
  one game make one record and leave no temporaries.
- **Size:** at most 256 KiB of UTF-8 bytes, counted on the encoded record; the same figure as the
  analysis server's request body (`web.MAX_BODY`), as an agent constant of its own. `open_game`
  also refuses an input text over 256 KiB of UTF-8 bytes before any parsing.
- **A record is valid only if all of these hold:**
  - it is at most 256 KiB;
  - it parses as JSON with exactly the keys above, of those types;
  - `v` is `agent_game_v1`;
  - its moves are legal from its `start_fen`, and `start_fen` is the `board.fen()` of itself;
  - its headers are in normal form: names from `pipeline.HEADERS`'s values, ratings non-negative
    integers, the others non-empty strings that `game_input` keeps (so `pgn_tags`, §2.4, read
    back by `game_input` gives them unchanged);
  - the key computed from its fields equals both its `game_key` and its file name;
  - re-encoding it gives the same bytes.

  Anything else is damaged.
- **Kept**, like the commentary store; a record is a few kilobytes. A removed record makes its id
  unknown to processes that have not loaded it (§2.3), never wrong.

### 2.3 Resolving an id (reviews B1, C2)

1. **The full form** names the file directly. Load it if this process does not hold the game,
   validate it (§2.2) and keep it in memory.
2. **The short form** lists `<data>/agent/games/<16 digits>*.json` on every resolution:
   - **none:** refused with "no game g-… (open it with open_game)" — unless this process holds a
     game with that prefix and no other record exists; then that game (its record was removed after
     loading);
   - **more than one:** refused with "game id g-… is ambiguous; use the full id g-<64 digits> given
     by open_game or its game_key";
   - **one:** that game. Load and validate it if not held.
3. **The invariant**, whichever process answers: an id names one game or is refused. It never names
   a different game.
   - A game this process already validated stays usable even if its record is later damaged or
     removed. Its content is the record's validated content.
   - Other processes then refuse the id rather than serve something else.
4. Facts trees, search trees, analyses and handles of a game are built on first use in each
   process, as today (AG-D §3.4), and belong to the game's in-memory entry (§3.3).
5. **Read-only tools resolve without holding (G6, review N2).** `show_game` and `commentary`:
   - use the game if this process holds it, without changing its place in the LRU;
   - otherwise read the record into a transient game used for this call only — not held, not
     counted, evicting nothing.

   Everything else they read is the ply cache and the commentary store, both on disk.

### 2.4 The agent's game is built from the record (reviews C7, N3, N4)

`ParsedGame` (`calliope.server`) is `game`, `sans`, `uci`, `root` (`RootSpec`), `spec`
(`GradingSpec`) and `warnings`.

**One constructor, `from_record(record) -> ParsedGame`, makes every game the agent works on**:
- `open_game` reads its input with `parse_game` as today, makes the record from `parsed.game`
  (§2.2), and then works on `from_record(record)`, not on `parsed`;
- a process that resolves an id it does not hold works on `from_record` of the record it read.

So a game opened in one process and resolved in another are the same value by construction. No
second parse is compared with the first, and no PGN is rebuilt (review N3).

`from_record` builds each field from the record alone:

| Field | Built from the record |
| --- | --- |
| `game` | `GameInput(start_fen, moves, headers)`. Each `GameMove` replays the moves from `start_fen` with python-chess (SAN, UCI, `board.fen()` before and after), as `game_input` does |
| `sans`, `uci` | the replayed SANs; `moves` |
| `root` | `RootSpec()` when `start_fen` is `chess.STARTING_FEN`, else `RootSpec(fen=start_fen)` |
| `spec` | `grading_for(pgn_tags(headers))` |
| `warnings` | the default-curve warning when `spec` falls back to it; nothing else |

**`pgn_tags(headers)` is the inverse of `pipeline.HEADERS` (N3).** Internal name → PGN tag
(`white_rating` → `WhiteElo`, `time_control` → `TimeControl`, `site` → `Site`, …), and ratings
written as decimal strings. It gives `grading_for` the same answer as the original tags:
- **Ratings:** the record holds `_elo(tag)`, and `_elo(str(n))` is `n`. A tag `_elo` rejects is
  absent from the record and from the original's reading alike.
- **`TimeControl` and `Site`:** the record leaves out only empty and "unknown" values (`?`, `.`).
  Such a time control has no digits, so it gives no time class, the same as an absent tag. Such a
  site does not contain `chess.com`, the same as an absent tag.

**The root, and why not `parsed.root` (N4).** `parse_game` gives `RootSpec()` (`fen=None`) when
there is no FEN tag, and the tag's raw text otherwise. Neither can be compared with the record's
`start_fen`:
- **No FEN tag:** `fen` is `None`, while `start_fen` is the standard FEN.
- **Raw text:** it may carry spaces, or an en passant square no pawn can take
  (`4k3/8/8/8/4P3/8/8/4K3 b - e3 0 1`). `normalize_open` keeps that square (`en_passant="fen"`);
  `board.fen()`, and so `start_fen` and `game_key`, drop it.

So two texts with one `game_key` can have different normalized roots, and the record cannot tell
which one the opener had. Building the root from `start_fen` gives every opener of one key one
root, and so one ply-cache key per ply (`normalized_ply`).

**What this changes:**
- **For every game without such an en passant square, nothing.** The root normalizes as before,
  and `sans`, `uci`, `game` and `spec` equal `parse_game`'s (§5).
- **For a game whose FEN tag has an untakeable en passant square:** the agent analyses it from the
  same position without that square. That square allows no move, so the position plays the same.
  Its ply-cache keys differ from the analysis server's (which keeps `parse_game`'s root), so the
  agent does not reuse that server's cached analyses of such a game; it analyses them again.

**Checks on a record read from disk:** the validity rules of §2.2, then
`game_key(from_record(record).game)` equals the record's key. Nothing else is compared, since
everything else is computed from those fields.

A rough probe on today's code (`parse_game` versus `from_record` of its record) gives one key,
`game`, `sans`, `uci`, `spec` and per-ply `normalized_ply` for each of these games:
- no FEN tag;
- normalized ratings (`01500`);
- chess.com with and without a known time control;
- `?` headers;
- comments and variations;
- a FEN tag equal to the standard start, a custom FEN with surrounding spaces, and a takeable en
  passant square.

The untakeable en passant square is the one case that differs, as described above. The raw-root
comparison of rev. 3 failed for every game without a FEN tag (N4).

## 3. The budget and memory (reviews B3, C1, C3, C4)

The budget limits the engine work one process takes. It used to count per connection, which every
host maps differently. It is now explicitly **a local load limit** (O2):
- in a shared process, the conversations share it;
- with one process per conversation, each has its own;
- a restart starts an empty window.

A limit on an agent's use across processes or hosts would need a shared store and a lock. It is not
in this packet.

### 3.1 Limits (`Limits`, each a server option)

| Field | Option | Default | Meaning |
| --- | --- | --- | --- |
| `window_seconds` | `--budget-window` | 900 | the rolling window |
| `max_uncached_plies` | `--max-uncached-plies` | 16 | uncached analyses per window |
| `max_searches` | `--max-searches` | 40 | engine searches per window (metered at the port, as today) |
| `max_uncached_plies_per_call` | `--max-uncached-plies-per-call` | 16 | uncached analyses one `open_game` may ask |
| `max_nodes_per_tree` | `--max-nodes-per-tree` | 2000 | nodes in one game's facts tree |
| `max_nodes_total` | `--max-nodes-total` | 20000 | nodes in all of the process's trees (facts and search) |
| `max_open_games` | `--max-open-games` | 16 | games held in memory |
| `max_store_results` | `--max-store-results` | 4000 | engine results kept by the search engine's store |
| `max_handles` | `--max-handles` | 20000 | handles held by the process (all games) |
| `max_analyses` | `--max-analyses` | 128 | projected analyses held in memory (all games) |

The per-call and per-window amounts are independent fields. A call is admitted only if both hold.

### 3.2 The rolling window

- Each charge is a timestamp (`time.monotonic`; the clock is injected for tests). A charge older
  than `window_seconds` no longer counts.
- The meter still charges a search before it reaches the engine and never refunds it (AG-D §3.5,
  R3). A search answered from the store stays free.
- **Admission** (AG-D §3.5) works against what the window has left. A search the meter refuses
  mid-analysis still discards that analysis: it never enters the ply cache.
- **Retry time (C3).** When a request needs `n` units and the window has `left < n`:
  - `need = n − left` charges must first expire;
  - with the window's charges sorted oldest first, the `need`-th one expires at
    `t_need + window_seconds`;
  - `retry_after_seconds = ceil(that − now)`.

  The refusal names the limit, what is left and `retry_after_seconds`. An admission needing a search
  bound uses that bound as `n`. A request larger than the limit itself is refused with no retry
  time.
- `budget_left` in answers stays, computed from the window, and gains `window_seconds`.

### 3.3 Memory (reviews B3, N1, C6, C8)

- **The game owns its work state.** Each in-memory game holds:
  - its facts tree;
  - its search trees and its searched-path set (today `Session.searched`);
  - its handles (today one `Handles` table).

  Projected analyses are a process cache keyed by bundle (below). Dropping a game drops its trees,
  searched paths and handles.
- **The same item gets the same handle (N1).** A handle is keyed by (game key, kind, source,
  address). Serving that item again — `ply` on the same ply, `judge_move` on the same move — returns
  the existing handle instead of a new one. Repeated reads therefore add no entries.
- **Limits.** Before work that adds nodes or handles, the process makes room:

  | Limit | When it would be passed |
  | --- | --- |
  | `max_nodes_per_tree` | the call is refused |
  | `max_nodes_total`, `max_open_games`, `max_handles` | the least recently used game is evicted first, never the one the call is using; if the call's own game alone passes a limit, the call is refused |

  Only tools that do work evict (`open_game`, `ply`, `judge_move`, `facts`, `explore`,
  `submit_commentary`). HIMARI classifies all of these as `scoped_write`. Read-only tools never
  evict (G6).
- **Projected analyses are a cache, not state (N1).** At most `max_analyses` are held, least
  recently used dropped first. A handle whose analysis was dropped is resolved by loading that
  analysis again from the ply cache (`PlyCache.get` with the source's path and bundle digests; no
  engine). If the ply cache no longer holds those exact digests, the handle is refused as expired.
  So dropping an analysis never changes what a handle means.
- **The search engine's result store** holds at most `max_store_results` results. Past that it is
  replaced by an empty one, and **every game's searched-path set is cleared with it (C6).** So
  admission checks the window again before a search that is no longer a store hit. The meter at the
  port stays the hard limit either way: a search is charged before the engine and refused when the
  window is empty.
- **After eviction:** the game's record stays, so its id still resolves and the game is rebuilt on
  next use. Its handles are refused as expired.
- **The process token is 96 bits (review C10).** It is `secrets.token_hex(12)`, up from 24 bits
  (`token_hex(3)`), so another process's handle is not taken for one of ours by chance. A handle
  becomes `c3.` followed by 24 hex digits; its form is otherwise unchanged.
- **Telling expired from foreign without the entry (C8).** A handle is `<kind><n>.<token>`. The
  process keeps its token and, per kind, the highest `n` it has issued. A handle is then judged in
  this order:
  1. another process's token: "served by another process" (existing message);
  2. this token and `n` above the highest issued: "not a handle this server served";
  3. this token, `n` issued, no entry: `HandleExpired` — "c3.<token> expired: the game was put away
     or its analysis is gone; read it again with ply/facts/explore".

  Nothing per evicted handle is kept.

## 4. What changes in the code

- `session.py`:
  - `Game` gains the per-game state of §3.3; `Session` keeps an LRU of games by key.
  - `open_game` normalizes, writes the record (§2.2) and returns the id (§2.1); `game()` resolves
    (§2.3).
  - Budget and node charges go through the windowed budget and the memory limits.
- `budget.py`:
  - `Limits` gets the fields of §3.1; `Budget` keeps charge timestamps instead of totals.
  - `Meter.take` stamps each search; refusals carry `retry_after_seconds`.
  - The node count is per tree and per process.
- `handles.py`:
  - entries grouped by game key and keyed by (kind, source, address) for reuse;
  - `drop(game_key)`, the per-kind highest-issued numbers, and `HandleExpired` (§3.3).
- `session.py` additionally:
  - a read-only resolution path for `show_game` and `commentary` (§2.3, step 5);
  - analyses as a bounded cache with reload from the ply cache;
  - searched sets cleared with the store;
  - `open_game` and resolution both work on `from_record(record)` (§2.4).
- `games.py` (new, in `calliope.agent`): `from_record` and `pgn_tags` (§2.4). They use only
  public names:
  - `calliope.server`: `grading_for`, `ParsedGame`, `game_key`, and `HEADERS` (below);
  - `calliope.results`: `GameInput`, `GameMove`;
  - `calliope.facts`: `RootSpec`.
- `handles.py` additionally: the 96-bit token (C10).
- `tools/mcp/__main__.py`: the options of §3.1.
- `server.py`: tool descriptions say a game id lasts, a handle does not, and the full form exists.
- `prompts/`: keep using a game id across calls; read again when a handle is refused or expired.
- `calliope.server` exports three existing names it does not export today: `canonical`
  (`cache.py`, the key's canonical JSON), `temporary_name` (`files.py`) and `HEADERS`
  (`pipeline.py`, PGN tag → internal name, which `pgn_tags` inverts). The agent may import
  only public names (`tests/test_package_boundaries.py`). There is no change to their behaviour, and
  no change to the viewer, the commentary store or the HTTP API.

## 5. Test obligations

- **Ids (B1):**
  - The same game gives the same id in two `Session`s on one data directory.
  - `open_game` twice gives one id and one record.
  - Other headers give another id.
  - Two records sharing 16 digits (made by hand): the short id is refused as ambiguous even when
    the game is in memory, the full id resolves, and `open_game` returns the full form.
- **Records (B2, C5):**
  - Two texts with one key (comments, spacing), registered by two processes at once, leave one
    record with the canonical bytes and no temporaries.
  - An existing record is never replaced.
  - A damaged record (each rule of §2.2 broken) is refused and left as it is.
  - A record over 256 KiB, and an input text over 256 KiB of UTF-8 bytes, are refused.
- **Resolution (C2):**
  - A second `Session` resolves an id the first opened.
  - A record removed or damaged after loading: the holding process keeps serving the validated
    game, and another process refuses the id.
  - No case serves a different game.
- **Budget (C1, C3, C4; fake clock):**
  - Charges leave the window after `window_seconds`.
  - `retry_after_seconds` is exact when several charges must expire.
  - Per-call and per-window limits hold independently.
  - Admission refuses an analysis whose search bound the window cannot hold.
  - A search refused mid-analysis keeps the analysis out of the cache.
  - Store hits are free.
- **Memory (B3):**
  - Many games, each up to its tree limit, keep the total nodes and held games within limits.
  - The least recently used game is evicted, never the current one.
  - The evicted game's handles are refused as expired; its id still works.
  - The store is replaced past its limit.
- **Handles (G4, N1, C8):**
  - A handle served by one `Session` is refused by another with the existing message.
  - `ply` on the same ply 10,000 times leaves the handle count unchanged.
  - Many distinct analyses keep handles within `max_handles` and analyses within `max_analyses`.
  - A handle whose analysis was dropped resolves by reloading it. It is refused as expired when
    the ply cache no longer holds those digests.
  - Expired, never-issued and foreign handles each get their own message.
  - The process token has 24 hex digits (C10).
- **Read-only tools (G6, N2):** with 16 games held and an open handle `c1` of game A:
  - `show_game` and `commentary` on 20 other games (not held) evict nothing;
  - `c1` still resolves and `submit_commentary(A, refs=[c1])` still works;
  - the held games and the LRU order are unchanged.
- **Store reset (C6):** after the store is replaced, a repeated search is admitted against the
  window again, and with the window empty it is refused before the engine.
- **The agent's game (C7, N3, N4):** a corpus with, as separate cases:
  - a game with no FEN tag;
  - normalized rating headers (`WhiteElo "01500"`, `BlackElo "?"`);
  - chess.com and lichess time controls, and an unknown one (`?`) with a chess.com site;
  - `?` and `????.??.??` headers;
  - comments and variations;
  - a FEN tag equal to the standard start; a custom FEN with surrounding spaces;
  - a takeable and an untakeable en passant square.

  For each case:
  - `from_record` of the record that `open_game` writes, in another `Session`, equals the opener's
    game;
  - its `game`, `sans`, `uci` and `spec` equal `parse_game`'s, and `game_key` agrees;
  - its root normalizes to the same FEN as `parse_game`'s, except the untakeable en passant case;
  - `from_record` of its own record gives it back.

  A game opened in one `Session` and analysed there is read by a second `Session` from the ply
  cache, without the engine.
- **`pgn_tags`:** for every header name, `game_input` reading `pgn_tags(headers)` gives `headers`
  back. A record whose headers are not in normal form is damaged.
- **Id stability (C9):** a short id resolves, a clashing record is added, the short id is now
  refused in a fresh process and in the holding one, and the full id still resolves.
- **Server:**
  - `show_game` with an id opened by another process works.
  - The App's refresh works after a restart.
- **Hosts (review 4.6):** one process shared by two conversations, and one process per
  conversation. In both, the same game gets the same id, and the budget behaves as §3 says (shared
  in the first, separate in the second).
- **The whole suite**, and the agent trial of AG-D §11 repeated once on the new ids.

## 6. Open questions for the owner

None. O2 and O3 were decided by the owner on 2026-10-15, as recommended (§0).

## 7. Review dispositions — rev. 1, independent review: NOT_READY

| # | Finding | Disposition |
| --- | --- | --- |
| B1 | A 16-digit clash had no recovery: the full key was not accepted as an id, re-opening gave the same short id, and the memory-first lookup could miss a clash | Full form `g-<64>` accepted everywhere. `open_game` returns it on a clash. A short id always checks the directory, whether or not the game is in memory (§2.1, §2.3) |
| B2 | "Written once" used `atomic_write`, which replaces; texts with one key (comments) give different bytes | The record holds the key's normalized preimage in canonical JSON, so one key gives one byte string. It is created with `os.link`, so it is made only if absent, and never replaced. A different existing record is damaged and refused (§2.2) |
| B3 | A per-tree node limit let a long-lived process grow without bound (games, handles, analyses) | Per-tree and per-process node limits, `max_open_games`, and LRU eviction of a game with all its work state. Expired handles get their own error; the engine result store is bounded (§3.3) |
| C1 | A per-process budget is still not host-independent | Stated as a local load limit, not a global usage limit (O2, §3). A global limit needs a shared store and is out of scope |
| C2 | The memory-first lookup skipped record checks | Short ids always check the directory. A validated in-memory game stays authoritative in its process. The invariant is "never a different game" (§2.3) |
| C3 | "When the oldest charge expires" is wrong when several must expire | `retry_after_seconds` from the `need`-th oldest charge (§3.2) |
| C4 | Per-call and per-window amounts were not separate | Separate `Limits` fields and options (§3.1) |
| C5 | 256 KiB unit and record validation unclear | UTF-8 bytes of the encoded record and of the input text. Record validity is listed rule by rule (§2.2) |
| Note | The title overstated "stateless" | Retitled: connection-independent game ids, process-local work state |

## 8. Review dispositions — rev. 2 (`6598e7e`), re-review: NOT_READY

| # | Finding | Disposition |
| --- | --- | --- |
| N1 | Nodes and games were bounded, handles and analyses were not: `ply` on a cached ply served new handles every time, and `Session.analyses` grew with every distinct analysis | The same item gets the same handle, keyed by (game, kind, source, address). `max_handles` with LRU game eviction. Analyses are a bounded cache (`max_analyses`) reloaded from the ply cache when a handle needs them, so dropping one changes no handle's meaning (§3.3) |
| N2 | A read-only tool (`show_game`, `commentary`) loaded a game, which could evict another game and expire its handles; HIMARI classifies both as `read` | G6: read-only tools resolve without holding. They use a held game without touching the LRU, or a transient one, and never evict or serve handles (§2.3 step 5). Only the work tools, all `scoped_write` in HIMARI, evict |
| C6 | Replacing the engine store left `searched` claiming store hits | Every searched-path set is cleared with the store. The meter stays the hard limit (§3.3) |
| C7 | How a `ParsedGame` is rebuilt from a record, and that it matches | §2.4: rebuilt through `parse_game`, identity checked (key, root, moves, headers). `spec` and the ply-cache keys follow from those fields; a corpus test is added |
| C8 | Telling an expired handle without its entry | Per-kind highest issued number and the process token: foreign, never issued or expired (§3.3) |
| C9 | A short id stops resolving once a clash appears | Stated as the stability contract. The full id always resolves (§2.1) |

## 9. Review dispositions — rev. 3 (`3c62ee9`), re-review: NOT_READY

N1, N2, C6, C8 and C9 were found resolved. C7 was partly resolved.

| # | Finding | Disposition |
| --- | --- | --- |
| N3 | Rebuilding a PGN from the stored headers would use internal names (`white_rating`) as tags. `parse_game` would not read them, so the key, the ratings and the time control, and with them `spec` and the cache keys, could change | No PGN is rebuilt. One constructor, `from_record`, builds every game the agent works on, in the opening process too. `spec` is `grading_for(pgn_tags(headers))`, with `pgn_tags` the inverse of `pipeline.HEADERS` and ratings as decimal strings; §2.4 shows it equals the original's. Headers in normal form become a record validity rule (§2.2) |
| N4 | `parsed.root.fen` is `None` for a game without a FEN tag, so comparing it with `start_fen` fails for ordinary games | The root is built from `start_fen`, not compared with it. The review's alternative (normalized root FEN against `start_fen`) also fails, for an untakeable en passant square that `normalize_open` keeps and `board.fen()` drops. Building from `start_fen` gives one root per key. The one cost is no reuse of the analysis server's cache for such games (§2.4) |
| C10 | A 24-bit process token can repeat across processes | 96 bits (`token_hex(12)`), §3.3 |
| §5 | The restore corpus must include a game with no FEN tag and normalized rating headers | Included as separate cases, with the other edges of §2.4 and a `pgn_tags` round trip |

## 10. Amendment AM1 (2026-10-16, AG4 re-review follow-up): limit values

§3.1 named the limits but not their ranges. With `--max-store-results 0` the store was replaced and
then held one new result, so a limit of 0 was not kept (non-blocking finding of the re-review of
AG4 rev. 4). `Limits` now refuses values out of range (`ValueError`), and `tools/mcp` reports one
as a usage error (exit 2) before it starts:

| Limits | Range | Meaning of the least value |
| --- | --- | --- |
| `window_seconds` | a finite number above 0 | — |
| `max_uncached_plies`, `max_searches`, `max_uncached_plies_per_call` | integers ≥ 0 | 0: none allowed (a server that only reads its caches; store hits stay free) |
| `max_nodes_per_tree`, `max_nodes_total`, `max_open_games`, `max_store_results`, `max_handles`, `max_analyses` | integers ≥ 1 | 1: room for the call's own game, node, result, handle or analysis |

Booleans are neither integers nor seconds here, and a window too large for a float is out of range
(review C1 of PR #103). Tests: `tests/agent/test_budget.py`.
