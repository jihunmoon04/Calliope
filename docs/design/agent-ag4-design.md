# Agent — AG4-D design: an MCP server that keeps no connection state

Status: **rev. 1 — design, for independent review**. Date: 2026-10-15. Base: `main @ 61be8cc`
(AG3b merged). Inputs: [`agent-mcp-design.md`](agent-mcp-design.md) (AG-D: the session, §3.5 the
budget, §3.6 handles, §8 the game key, §9 two processes on one data directory); MCP
[2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/changelog) (SEP-2567, SEP-2575);
HIMARI V3-P59 (an MCP client that runs stdio servers, one process per server by default).

Calliope's MCP server ties three things to the process it runs in, which is also its one
connection ("one session per connection", AG-D §2):

1. the game ids it hands out (`g1`, `g2`, … counted from 1 in every process);
2. the budget (16 uncached plies, 40 searches, 2000 nodes, used once and never refilled);
3. the handles (`c3.k7f2a9`: a random token per process, so a foreign handle is refused).

Hosts run that process differently:
- Most hosts start **one process per server** and share it across every conversation.
- HIMARI does the same by default and can start **one per conversation**.
- Any host restarts the process when it dies or has been idle.

So the same agent sees different behaviour from host to host, and two of the three are wrong:
- **An old id can name a new game.** After a restart, a game opened in the new process is `g1`
  again, so the agent's earlier `g1` silently names that game. Its analysis is served as if it
  were the old game's.
- **The budget runs out for good, or it can be dodged.** Under a shared process, the first
  conversations spend it for every later one. Under per-conversation processes or restarts, it is
  fresh every time.

The latest MCP revision (2026-07-28) removes protocol sessions altogether. It says: "Servers that
need cross-call state use explicit, server-minted handles passed as ordinary tool arguments", and
list results "no longer vary per-connection". AG4-D makes Calliope's server behave the same
whichever process or connection answers a call.

## 0. Owner decisions

| # | Decision |
| --- | --- |
| O1 | (2026-10-15) The server keeps no connection state that changes what an id means or how much an agent may spend: content-based game ids, and a budget not tied to the connection (HIMARI V3-P59 §5.7). |
| O2 | (open, §6) The budget window: its length and its amounts. Recommended: §3.2. |

## 1. Decisions

| # | Decision |
| --- | --- |
| G1 | **A game id is derived from the game**: `g-` + the first 16 hex digits of its `game_key` (AG-D §8). The same game gets the same id in every process, every connection and every host. `open_game` on a game already opened returns the same id; that is not an error. |
| G2 | **A game id resolves from a record, not from memory.** `open_game` writes `<data>/agent/games/<game_key>.json` once. A process that has not opened the game reads it from there. An id with no record, or with two records sharing its 16 digits, is refused with a tool error naming what to do. |
| G3 | **The budget is the process's, over a rolling window**, not the connection's (§3). Every tool call is also bounded by itself (§3.1). |
| G4 | **Handles stay as they are** (AG-D §3.6). They point into the process's own trees (facts, searches), keep their per-process token, and are refused by another process with the existing error. The tool texts say so. Making them outlive the process is not in this packet. |
| G5 | **Nothing else changes.** Tools keep their names, arguments and answers; only the value of `game` changes. The commentary store, the ply cache, the HTTP server and the viewer already key by `game_key`. |

## 2. Game ids and records

### 2.1 The id

- `game_id = "g-" + game_key[:16]`, lowercase hex, for example `g-3fa2c1d9e8b74a10`. 64 bits keep
  ids distinct among a host's games; a clash is still caught (§2.3).
- 16 digits, not 64, because the agent copies the id into every call: a short id costs fewer tokens
  and fewer copying mistakes. The full key stays in `open_game`'s answer (`game_key`), as today.
- Opening the same game again (same start, moves and headers) returns the same id, re-reads nothing
  and charges nothing beyond what the call itself asks (`plies`).

### 2.2 The record

```json
{"v": "agent_game_v1", "game_key": "<64 hex>", "pgn": "<the text open_game parsed>"}
```

- `pgn` is exactly the text `parse_game` read: the `pgn` argument, or what `pgn_of(fen, moves)`
  made. Reading it back with `parse_game` gives the same `ParsedGame`, and its `game_key` must
  equal the record's. Otherwise the record is refused as damaged (a tool error; nothing is served
  from it).
- **Written once, never rewritten**, through `server.files.atomic_write` (unique temporary name,
  `fsync`, `os.replace`; AG-D §9). If the file already exists, it is read and its `game_key`
  compared; the same key is fine. Two processes opening the same game at once both write the same
  bytes, and the replace keeps one.
- **Size.** At most 256 KiB, the same as the analysis server's request body (`web.MAX_BODY`), as
  an agent constant of its own. `open_game` refuses a longer text before writing anything, and a
  longer record is refused on read. Today `open_game` has no such limit beyond the MCP message.
- **Kept**, like the commentary store; a record is a few kilobytes. Removing a record only makes
  its id unknown (G2), never wrong.

### 2.3 Resolving an id (`Session.game`)

1. In memory (this process opened or read it before): use it.
2. Otherwise list `<data>/agent/games/` for `<16 digits>*.json`:
   - none: refuse with "no game g-… (open it with open_game)";
   - more than one: refuse with "game id g-… is ambiguous; open the game again" — `open_game` then
     answers with the same id, and the agent should use the full `game_key` (§6 Q3);
   - one: read, check (§2.2), parse, keep in memory.
3. The facts tree and search trees of a game are built on first use in each process, as today
   (AG-D §3.4). Their handles are this process's (G4).

## 3. The budget (G3)

The budget limits the engine work an agent can cause. It used to count per connection, which every
host maps differently. Two layers replace it:

### 3.1 Per call

| Call | Bound |
| --- | --- |
| `open_game` with `plies` | at most `max_uncached_plies_per_call` (16) uncached analyses; admitted only if the window has them (§3.2) |
| `ply`, `judge_move` | one uncached analysis (its search bound, AG-D §3.5) |
| `explore` with `search` | one search |
| `facts`, `explore` | the nodes they add to one game's facts tree: at most `max_nodes_per_tree` (2000) per tree, a memory bound per process |

### 3.2 Per process, over a rolling window (recommended defaults; O2 open)

| Amount | Default | Window |
| --- | --- | --- |
| uncached analyses | 16 | 15 minutes |
| engine searches (metered at the port, as today) | 40 | 15 minutes |

- **A rolling window** counts what was charged in the last `window` seconds (`time.monotonic`).
  Charges older than that fall out. The meter still charges a search before it reaches the engine
  and never refunds it (AG-D §3.5, R3). A search answered from a store stays free.
- **A refusal names the limit, what is left and when the oldest charge falls out**, for example
  `"the budget refuses 3 uncached analyses: 1 left, 2 more at 14:05:10"`. The agent can tell the
  user, or wait.
- **The amounts are server options** (`--max-uncached-plies`, `--max-searches`, and a new
  `--budget-window`). The owner may raise them, as today.
- **What this gives each host:**
  - A shared process limits all of its conversations together. It never runs out for good; it
    refills as time passes.
  - Per-conversation processes each get their own window, so the host's total is that many times
    larger. HIMARI bounds the number of processes (`processes.max`).
  - A restart starts an empty window. That was true before too; it is no worse.
- **Admission** (AG-D §3.5) works as before against what the window has left. A search the
  meter refuses mid-analysis still discards that analysis (it never enters the ply cache).

`budget_left` in answers stays, with the window's numbers. A new field `budget_window_seconds`
says how long the window is.

## 4. What changes in the code

- `session.py`:
  - `Game.id` comes from `game_key`; `open_game` writes the record (G2) and reuses a game already
    open; `game()` resolves through §2.3.
  - Budget calls go to the windowed budget.
- `budget.py`:
  - `Limits` gains `window_seconds` and the per-call amounts.
  - `Budget` keeps timestamps of charges instead of totals. `Meter.take` stamps each search.
  - `left()` and refusals compute from the window. A clock is injected for tests.
- `tools/mcp/__main__.py`: `--budget-window` (seconds, default 900).
- `server.py`: tool descriptions say that a game id lasts and a handle does not (G4).
- `prompts/`: the method text says to keep using a game id across calls, and to open the game again
  when a handle is refused.
- No change to `calliope.server`, the viewer, the commentary store or the HTTP API.

## 5. Test obligations

- **Ids:**
  - The same game gives the same id in two `Session`s on one data directory.
  - `open_game` twice on one game gives one id and writes one record.
  - A different game (other headers) gives another id.
- **Records:**
  - A second `Session` resolves an id the first opened, from the record.
  - An id with no record is refused with the message.
  - A damaged record (its key does not match its text) is refused.
  - Two records with the same 16 digits (made by hand) give the ambiguity refusal.
  - Concurrent writers of one record leave one valid file and no temporaries.
- **Budget (fake clock):**
  - A charge leaves the window after `window` seconds.
  - A refusal names when room comes back.
  - Admission refuses an uncached analysis whose search bound the window cannot hold.
  - A search refused mid-analysis still keeps the analysis out of the cache.
  - The per-call caps hold.
  - Searches answered from a store are free.
- **Handles:** a handle served by one `Session` is refused by another with the existing error (G4).
- **Server:**
  - `show_game` with an id opened by another process works.
  - The App bridge's refresh call (`show_game` with the same arguments) works after a restart.
- **The whole suite**, and the agent trial of AG-D §11 repeated once on the new ids.

## 6. Open questions for the owner

1. **O2 — the budget window.** 15 minutes with 16 uncached analyses and 40 searches (the old
   per-session amounts per window), or another length or other amounts.
2. **Handles across processes** (G4): leave as is (refused, the agent re-reads), or make them
   outlive a process later. Recommended: leave as is. A handle names a node of a tree the process
   built; rebuilding it on demand is possible but is a packet of its own.
3. **Id length**: 16 hex digits (recommended), or the full 64 (no ambiguity case, more tokens per
   call).
