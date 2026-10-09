# Fact engine — packet F4-D: Stockfish searches, comparison basis and engine lines

Status: **rev. 3 — independent F4-D re-review READY_WITH_CORRECTIONS applied** (design only).
Date: 2026-10-09. Base: `main @ 3a66eb5` (F1–F3 merged). Reviews: rev. 1 `97434b3` NOT_READY;
rev. 2 `3ca6d0b` READY_WITH_CORRECTIONS. Section 12 maps every finding.

Parent design: [`fact-engine-a0-design.md`](fact-engine-a0-design.md) rev. 4 (sections 2.1,
2.4, 3.1, 3.2, 7, 9, 12, 14; amended by this packet as listed in section 10). Siblings:
[`fact-engine-f2-design.md`](fact-engine-f2-design.md),
[`fact-engine-f3-design.md`](fact-engine-f3-design.md) and their implementation records.

## 0. Scope

A0 §7 already decides the engine model: a fresh state per search; the survey and union
comparison; a revisioned basis; PV attachment up to terminal nodes; the result store; the
budget. This packet freezes what A0 left as a sketch:

- the engine boundary (`EnginePort`), the raw-UCI adapter, the profile, the identity and the
  fresh-state protocol;
- the exact `EngineInput`, and its en passant form as Stockfish 19 actually parses it;
- the search record, normalization, regularity, `SearchId` and the result store;
- tree integration:
  - the root role and expansions;
  - which engine work a request plans;
  - `NodeSearch`, the basis, scores and engine-line attachment;
  - family tiers for engine-only nodes, and an engine-only node gaining an input role
    (F2D-N4);
  - budget and deadline;
- test obligations, including a scripted engine, a fake UCI engine and real-Stockfish
  acceptance.

**Two implementation packets** share this design:

| Packet | Content |
| --- | --- |
| **F4a** | `EnginePort`, the raw-UCI `StockfishEngine`, `EngineProfile`, `EngineIdentity`, `EngineInput` construction (read-only tree access), search records, normalization, regularity, `SearchId`, `EngineResultStore`, `ScriptedEngine`, a fake UCI engine for adapter tests. No tree changes |
| **F4b** | tree integration (§6–§8) |

**Legacy evidence** (frozen MVP, tag `legacy-mvp-g0`): `ADP` =
`src/calliope/adapters/stockfish/adapter.py`.

## 1. Measurements on Stockfish 19 (2026-10-09)

The v1 engine is the Stockfish 19 build at `~/opt/stockfish/stockfish`:
- tag `sf_19`, commit `edb0d9d`, armv8 NEON, g++ 13.3;
- sha256 `70773580…fbb5d`.

With it, all 127 legacy integration tests pass, including the 7 that fail on Stockfish 17.
The review reproduced M2–M8 independently. Scratch scripts are not committed.

| # | Question | Result |
| --- | --- | --- |
| M1 | Options offered | `EvalFile` = `nn-1a298aa575a0.nnue` (embedded). **No `EvalFileSmall`**; A0 §7.1 expected two nets, as in Stockfish 17. `UCI_ShowWDL` is offered; `Clear Hash` is a button. Also offered, and able to change a search: `SyzygyPath`, `Skill Level`, `UCI_LimitStrength`, `UCI_Elo`, `nodestime` (§3.2) |
| M2 | Fresh state | Depth-12 MultiPV-5 results are identical before and after unrelated searches, and in a new process. Fresh state means a new `game` object (so `ucinewgame`) plus `Clear Hash` through python-chess, or the raw protocol of §3.3. With one shared game and no clearing, all 3 positions changed |
| M3 | En passant form | The FEN Stockfish prints (`d`) has exactly python-chess's **legal** en passant square. Tested on 412 positions after double pushes plus constructed pins: 0 mismatches. The review repeated it on 1,500 positions and 14 constructed cases (rank pin of both pawns, diagonal pin, discovered check, king on the pawn's file, a rook pin along the 4th rank), through both of Stockfish's paths (FEN parse and `do_move`): 0 mismatches. Stockfish 19 drops a pseudo-legal-only square, e.g. `7k/8/8/KPp4r/8/8/8/8 w - c6` |
| M4 | Window input vs full history | Window-start FEN + window moves gives lines identical to the full game. Measured on 12 random-game positions and 3 repetition histories, and by the review on windows strictly shorter than the history (9 of 16, 7 of 14, 10 of 12 plies). A bare FEN differs in every repetition case, e.g. startpos after `Nf3 Nf6 Ng1 Ng8` ×2: +14 `d2d4` with history, +32 `e2e4` without |
| M5 | Time stop | Depth 30 with a 30 ms cap stops at depths 6–9, with mixed depths across ranks, a bound on the rank being searched, and ranks out of score order. Two identical runs gave different scores |
| M6 | Depth stop | Depth 12 with a 2000 ms cap: every line depth 12, every score exact |
| M7 | MultiPV above the number of legal moves | One legal move with MultiPV 5 gives one line |
| M8 | `searchmoves` | A restricted search and the survey give different scores for the same move (a2a3 +18 in the survey vs +10 restricted; d2d4 +37 vs +20). A0 §7.3 holds on Stockfish 19 |
| M9 | Cost | 80 surveys from random games (depth 12, MultiPV 5, 1 thread, 16 MB): median 170 ms, p90 417 ms, max 810 ms; 0 irregular. PV plies: median 9, max 22 |
| M10 | Raw-UCI protocol (§3.3) | Deterministic on 3 positions after unrelated searches and in a new process, with or without the pinned options; an adapter-sent `stop` ends a depth-30 search at the cap (the review: 200 ms cap, depths 9–10, an `upperbound`) |
| M11 | Option cost per search (the review) | Sending the full pinned set costs 218–220 ms per search against 8.3 ms without it. `EvalFile` alone costs 195–200 ms: it reloads the network. `Threads` costs about 10.5 ms, `Hash` about 1 ms, every other option at most 0.1 ms. Hence the start-time / per-search split of §3.2 |

## 2. Legacy findings

### 2.1 ADP, by code reading

| # | Legacy behaviour | Where | Here |
| --- | --- | --- | --- |
| E1 | one `game` token per request, so `ucinewgame` once per request; hash carried between searches | ADP:71–84, 134–142 | full fresh-state protocol per search (§3.3) |
| E2 | the engine gets a FEN only, no moves: repetition and fifty-move history invisible (M4) | ADP:126, 208–215 | `EngineInput` with the window moves (§4) |
| E3 | identity = name only, `version=None` | ADP:94–101 | `EngineIdentity` (§3.2) |
| E4 | bound scores **raise**; a time-stopped search cannot be recorded | ADP:301–302 | recorded as irregular (§5.3) |
| E5 | WDL turned into fractions | ADP:320–330 | raw permille, White's view (§5.2) |
| E6 | no stop reason; Hash and Threads only if set | ADP:180–198 | `stopped_by` from the adapter; every option every search (§3.3) |
| E7 | reads python-chess `analyse()`; PV legality checked on what python-chess returned | ADP:134–148, 285–297 | raw UCI; see §2.2 |

### 2.2 python-chess `analyse()` cannot carry the ingestion guarantees (F4D-B1)

The review reproduced this with a fake UCI engine:
- **Merged info lines.** `AnalysisResult` merges every info line of a rank into one dict. A
  depth-11 line `score cp 20 lowerbound wdl … pv e2e4 e7e5`, followed by a depth-12 line
  `score cp 31 pv e2e4 e7e5 e1e3`, comes back as one line: depth 12, `lowerbound`, cp 31, the
  depth-11 WDL.
- **Dropped PV.** python-chess logs the illegal `e1e3`, drops that line's `pv`, and keeps the
  old PV `e2e4 e7e5`.
- **Consequences.** An illegal PV is swallowed, which the A0 STOP list forbids ("repairs or
  truncates"). Stale bounds and WDL make regularity unreliable.
- **Protocol.** python-chess also never resends unchanged options. Threads and Hash were not
  sent at all, and MultiPV only on the first search.

Legacy E7 shared the blind spot. The F4 adapter therefore speaks raw UCI (§3.3).

## 3. Engine boundary (F4a)

### 3.1 `EnginePort`

```text
class EnginePort(Protocol):
    identity: EngineIdentity
    def search(self, request: SearchRequest) -> RawSearch: ...     # one fresh-state search
    def close(self) -> None: ...

SearchRequest(input: EngineInput, profile: EngineProfile, root_moves: tuple[str, ...] | None,
              multipv: int)
RawSearch(lines: tuple[RawLine, ...], stopped_by: DEPTH | TIME, elapsed_ms: int)
RawLine(multipv: int, depth: int, seldepth: int, score: ("cp", int) | ("mate", int),
        bound: EXACT | LOWER | UPPER, wdl: (int, int, int) | None, nodes: int, tbhits: int,
        pv: tuple[str, ...])          # UCI text exactly as printed; side-to-move view
```

- **`StockfishEngine`** is the only module that talks to the engine. It drives a subprocess
  with raw UCI (§3.3), not python-chess's engine module.
- **`ScriptedEngine`** returns `RawSearch` values from a table keyed by `SearchRequest`, and
  counts calls. Tests tape `RawSearch`, not normalized records (F4D-N4).
- **The caller owns the port.** It creates the port, passes it to
  `FactEngine(families, engine=port, store=store)`, and closes it.
- **Locking.** The adapter holds its own lock around each whole search (options to
  `bestmove`), so two trees sharing one port never interleave commands (F4D-C6). The store
  is thread-safe.
- **Normalization** (§5.2) lives in the fact engine. Scripted and real output go through the
  same code.

### 3.2 Profile and identity

```text
EngineProfile(name="d12_mpv5_v1", depth=12, time_cap_ms=2000, multipv=5, threads=1,
              hash_mb=16)
EngineIdentity(name, author, binary_sha256, options: tuple[(name, type, default), ...])
```

- `threads` must be 1: M2 does not hold with more threads. `hash_mb` is fixed per profile.
  WDL is always requested when offered (A0 §7.1), so the profile has no WDL switch.
- **`name` and `author`** are the UCI `id` lines.
- **`binary_sha256`** is the hash of the executable the adapter started, resolved through
  symlinks.
- **`options`** lists every option the engine offers, with its type and default. The
  `EvalFile` default (the network) is therefore part of the identity.
- **Supported engines.** v1 admits `name == "Stockfish 19"` exactly. Any other engine or
  version first re-passes §9.3 (fresh state, the en passant form, window equivalence), because
  `EngineInput` (§4) encodes Stockfish 19's en passant rule. `StockfishEngine` refuses other
  names at start (`EngineUnsupportedError`).
- **Pinned options** (F4D-C9, R2-C2). Every search-affecting option the engine offers is fixed
  in two groups:
  - **At port start**, once: `EvalFile` at its default and `Threads 1`. These are expensive to
    send (M11). The adapter waits for `readyok` and refuses to start on any `info string`
    error. `StockfishEngine` is the only UCI speaker and exposes no `setoption`, so these values
    cannot drift.
  - **Every search**: `Hash 16`, `MultiPV k`, `UCI_ShowWDL true`, `SyzygyPath <empty>`,
    `Skill Level 20`, `UCI_LimitStrength false`, `UCI_Elo` at its default, `nodestime 0`,
    `UCI_Chess960 false`, `Ponder false`.

  The search record names both groups (§5.1). The caller cannot change a search invisibly.

### 3.3 Raw-UCI protocol per search

Under the adapter lock, for every search:
1. Send the per-search pinned options of §3.2, with `MultiPV` = the request's MultiPV.
2. Send `ucinewgame`, then `setoption name Clear Hash`. Send `isready` and wait for `readyok`.
3. Send `position fen <EngineInput.fen>`, then ` moves <window moves>` when the window is not
   empty. It is always the FEN form, never `startpos`.
4. Send `go depth <profile.depth>`, plus ` searchmoves <root moves>` for a restricted search.
   Send **no** `movetime`.
5. Read lines until `bestmove`. If `bestmove` has not arrived when `time_cap_ms` has elapsed,
   send `stop` and read until `bestmove`.
   - `stopped_by = TIME` iff the adapter sent `stop`. Sending `stop` and then receiving
     `bestmove` races, and the race is classed `TIME` (conservative, F4D-C1).
   - Otherwise `stopped_by = DEPTH`.
6. **Per-line info.**
   - For every `info … multipv r … pv …` line, the adapter keeps the **last** such line of
     rank r. It never merges fields across lines.
   - An `info` line with `score` and `multipv` but no `pv`, or one the adapter cannot
     tokenize, refuses the search (`EngineOutputError`).
   - PV moves are passed on as printed. Their legality is checked by normalization (§5.2).
7. **Refusals** (`EngineError`):
   - process death;
   - no `readyok` within 10 s;
   - no `bestmove` within 10 s after `stop`;
   - a rank **gap** (rank r+1 present without r), a duplicate rank, or more than k ranks.

   Whether *fewer* ranks are acceptable is judged by normalization from `stopped_by` (§5.2)
   (R2-C3).
8. `elapsed_ms` is measured from sending `go` to receiving `bestmove` (F4D-R2-N6).

M10 shows the protocol is deterministic for depth-stopped searches.

## 4. `EngineInput` (F4a; amends A0 §3.1, §7.4)

```text
EngineInput(fen: str, moves: tuple[str, ...])
```

- **Window.** `w = min(halfmove_clock(node), known_plies(node))`, the repetition window
  (A0 §7.4).
- **Known history.** It is a copy of `session.start_board` (F1R-N3), followed by the canonical
  pre-root moves and the tree path moves. `moves` = its last `w` moves; `fen` = the position
  before them. The window may start before the root.
- **FEN form:**
  - placement, side and castling;
  - the **legal** en passant square (python-chess `en_passant="legal"`). This equals Stockfish
    19's parse on both its FEN path and its `do_move` path (M3), so window-start parsing can
    never differ from replaying the moves (F4D-N8);
  - the halfmove clock;
  - fullmove number `1`. Stockfish uses it only for time management, and no time management
    applies under `go depth`.

  This replaces A0 §7.4's `en_passant="xfen"`, which described Stockfish 17.
- **Consequence.** On Stockfish 19, two histories that are equal under `PositionKey` and have
  equal windows give one `EngineInput`. `EngineInput` still differs from `PositionKey`: it
  carries the halfmove clock and the window moves.
- **Incomplete history.** The window starts at the start board, whose halfmove clock is the
  one given in the root FEN. A start FEN with a pseudo-legal en passant square or a fullmove
  number other than 1 is written in the form above.

## 5. Search records (F4a)

### 5.1 Record

```text
EngineSearch(search_id, input: EngineInput, kind: SURVEY | COMPARISON | ANALYSIS,
  root_moves: tuple[str, ...] | None,          # sorted as strings; None = unrestricted
  multipv: int,                                 # requested
  profile: EngineProfile, identity: EngineIdentity, pinned_options: tuple[(name, value), ...],
  stopped_by: DEPTH | TIME, regular: bool,
  lines: tuple[EngineLineFact, ...])            # rank order
EngineLineFact(rank, move, score: Cp(int) | Mate(winner: Color, moves: int),
  bound: EXACT | LOWER | UPPER, wdl: Wdl(white_win, draw, black_win) | UNAVAILABLE,
  depth, seldepth, nodes, tbhits, pv: tuple[str, ...])
SearchRuntime(rev, search_id, elapsed_ms, reused: STORE | SESSION | None)  # not a fact
```

- `SURVEY` and `COMPARISON` are the node policy searches (§7). `ANALYSIS` is the restricted
  search an `ANALYSIS(by)` request asks for (§6.3); it never becomes a basis.
- `SearchRuntime` is metadata: keyed by (rev, search_id), outside the digest (F4D-N3).
- Records are frozen and created only by the fact engine (A0 §9).

### 5.2 Normalization

1. **Scores and bounds from White's view.** `Cp(n)`; `Mate(winner, moves)` with `moves ≥ 1`.
   With Black to move, a lower bound becomes an upper bound and vice versa (F4a review C1). "Mate 0"
   (the side to move is mated) cannot reach a search, because terminal nodes are never
   searched; if it arrives, the search is refused.
2. **WDL** in permille from White's view, as integers (`white_win`, `draw`, `black_win`).
   `UNAVAILABLE` only when the engine does not offer `UCI_ShowWDL`. When it is offered and set,
   a line without `wdl` is refused (F4D-R2-N4).
3. **PV.** Every token must be structural UCI (`chess.Move.from_uci`; no SAN fallback,
   F4D-R2-N3). It is then resolved by `canonical_move`, replayed from the window end. An
   illegal, null or unparsable move refuses the whole request (`EngineOutputError`). Nothing is
   repaired or cut.
4. **Lines.**
   - Ranks must be exactly `1..k`, with `k = min(multipv, legal root moves in the
     restriction)` (M7).
   - Each line's `move` is `pv[0]`.
   - With `root_moves`, every `move` is in the restriction, and the moves are distinct.
   - A `TIME`-stopped search may report fewer ranks, `1..j` with `j ≥ 1`; Stockfish skips
     unsearched ranks at depth 1 (`search.cpp:2288`) (F4D-N2). A stop before depth 1
     completes prints lines with an empty PV; those are refused (§3.3), which is unreachable
     at a 2000 ms cap (F4a review N6).
   - Anything else refuses the request.

### 5.3 Regularity

- `regular` iff `stopped_by = DEPTH`, every line has `depth = profile.depth`, and every bound
  is `EXACT`.
- Because `stopped_by` comes from the adapter (§3.3) and not from reported depths, a search
  stopped inside its last iteration is never regular (F4D-C1).
- An irregular search is recorded as reported. It is never a basis (§7.3) and never enters the
  store. Within one session, a committed irregular search is reused for an identical request
  (A0 §7.7).

### 5.4 `SearchId`

`SearchId = "s_" + digest(...)` over a length-prefixed preimage (F4D-N1):
- `"search"`;
- `input.fen`, `len(moves)`, `*moves`;
- `kind`;
- `len(root_moves)` or `-1`, `*root_moves`;
- `multipv`;
- the profile fingerprint (every profile field);
- the identity fingerprint (every identity field);
- the pinned options.

An irregular search's preimage also holds a digest of its normalized lines (A0 §3.1, R3-C3).

### 5.5 `EngineResultStore`

- A thread-safe in-memory map `SearchId → EngineSearch` of **regular** searches. Sessions
  share it when the caller passes the same store to their `FactEngine`.
- A hit runs no engine; `SearchRuntime.reused = STORE`.
- A failed request leaves its finished regular searches in the store. This is safe because
  entries are content-addressed.
- The in-session irregular cache holds the session's committed searches **and** the pending
  request's searches. Two transposed nodes with one `EngineInput` in one request therefore
  share one search. The pending part is discarded if the request is refused (R2-C7).
- Persistence and tape replay are F5.

## 6. Requests and planned engine work (F4b)

### 6.1 Requests and expansions

```text
OpenRequest(root, families, budget, engine: EngineProfile | None = None,
            root_expansion: ExpansionSpec = FULL, defaults: Defaults = Defaults())
ExtendRequest(lines, role, expansion: ExpansionSpec | None = None)
ExpansionSpec(survey: bool, comparison: bool, attach_lines: bool)
FULL = ExpansionSpec(True, True, True); NONE = ExpansionSpec(False, False, False)
Defaults(played = FULL, explored = FULL)
SessionBudget(max_nodes, max_searches: int | None = None, deadline_per_request_ms: int | None)
```

- **Validity.** `comparison` and `attach_lines` require `survey`, so
  `ExpansionSpec(False, True, …)` and `ExpansionSpec(False, …, True)` are refused.
- **No engine.** `engine = None` (the default) gives a tree without attested facts, exactly as
  in F1–F3.
- **Session binding.** An `engine` profile requires a port on the `FactEngine`. The session
  records the profile and the port's identity at `open`. A later `extend` on a `FactEngine`
  without a port, or with a port of another identity, is refused (F4D-C6).
- **`ANALYSIS`** requests must give `expansion` (A0 §2.1). `PLAYED` and `EXPLORED` use the
  session defaults unless `expansion` overrides them.
- **The root at `open`** (F4D-B2.1) gets a role entry `ROOT(index 0)` carrying
  `root_expansion`. `ROOT` is a new input-role kind, ordered first
  (`ROOT < PLAYED < EXPLORED < ANALYSIS < ENGINE`). It plays no part in comparison sets
  (§7.2). It is written only when the session has an engine, so trees without an engine stay
  exactly as in F1–F3 (F4D-R2-N5).

### 6.2 Effective expansion

- Every input role entry stores the expansion of the request that wrote it (F4D-B2.2). The
  start node of a line gets the line's role entry at index 0, so it is part of the request.
- A node's **effective expansion** at revision r is the per-flag OR over its input role entries
  visible at r (A0 §7.6, union), with one split (R2-C1):
  - `survey` and `attach_lines` are OR-ed over **all** input roles. A survey requested by an
    `ANALYSIS` role can therefore become N's survey, and so its basis (A0 §7.6 union).
  - **`comparison` is OR-ed over `ROOT`, `PLAYED` and `EXPLORED` roles only.** It is the
    *policy* comparison (§6.3 step 2, §7.3 row 5). An `ANALYSIS` role's `comparison` flag means
    only the `ANALYSIS`-kind search of its own request (§6.3 step 3). So no `ANALYSIS` request
    can change N's comparison set or which comparison is its basis (A0 R3-C2).
- Every policy decision at a node reads its effective expansion. The expansion of the request
  that added a child does not govern its parent. The one exception is the attachment of
  `ANALYSIS`-kind searches, which reads the binding request's expansion (§6.3 step 4;
  F4D-R2-N8).
- Example: N was surveyed under `FULL`. An `EXPLORED` request with `NONE` starts at N and adds a
  child outside the survey. N's effective expansion still has `comparison`, so N is compared
  in that request.

### 6.3 Which engine work a request plans

The **nodes of a request** are every node on its lines, start nodes included, deduplicated,
in line order. For `open` it is the root. A node is **searchable** iff all hold:
- its effective expansion has `survey`;
- it is not terminal and not `after_terminal` (`UNPROVEN` nodes are searched);
- the session has an engine.

Engine work happens **only at the nodes of the request** (F4D-C3). In this order:

1. **Surveys.** Every searchable request node without a survey gets one. This includes a node
   that gained an input role (F2D-N4) or whose expansion gained `survey` (Q2). A node is never
   surveyed twice: its `EngineInput` is a function of the node.
2. **Comparisons.** A comparison runs at every searchable request node that meets all three
   conditions:
   - its survey is **regular** (R2-C6);
   - its effective (policy) expansion has `comparison`;
   - its comparison set (§7.2) is larger than the set already compared.

   A comparison skipped earlier (budget, deadline) is retried here, and only here.
3. **ANALYSIS searches** (`ANALYSIS` requests with `comparison`). At every request node N that
   is not terminal or `after_terminal` and has at least one child move in this request, one
   search of kind `ANALYSIS` runs:
   - `root_moves` = N's survey moves ∪ this request's child moves at N, over all its lines;
   - one search per node per request;
   - skipped when that set equals the survey moves;
   - it still runs after an irregular survey, because it is an attested probe and never a
     basis. Its `root_moves` then use that survey's moves.

   The validity rule (`comparison` requires `survey`) means an `ANALYSIS` probe with
   `comparison` surveys every node on its line. That is a cost the requesting block chooses
   (F4D-R2-N7).

   Surveys run by an `ANALYSIS` request are ordinary `SURVEY` searches and can be N's basis.
   Because `kind` is in the `SearchId` preimage, an `ANALYSIS` search over the same set as a
   `COMPARISON` runs the engine again (F4D-C5).
4. **Attachment** (§8). For every request node N whose effective expansion has
   `attach_lines`, every `SURVEY` and `COMPARISON` search bound to N and not yet attached at
   anchor N is attached. This includes searches from earlier revisions that were bound while
   attachment was off (F4D-B2.3).

   An `ANALYSIS`-kind search is attached only in the request that binds it, and only if that
   request's expansion has `attach_lines`. A regular `ANALYSIS` search already bound by an
   earlier request is not bound again, so a later request does not attach it (F4D-R2-N2). A
   pair (anchor, `search_id`) is attached at most once (F4D-B2.4).

   **Order** (R2-C8): request-node order, then searches by (rev, kind, search_id), then lines
   by rank. This order decides which lines reach `BUDGET_LIMIT` or a deadline cut.

Nothing else calls the engine. `ensure` never does.

### 6.4 `NodeSearch`

`NodeSearch(node, rev, search_id, kind)` binds a search to a node, at most once per
(node, `search_id`).
- A search reused at another node with the same `EngineInput` is one record referenced twice
  (A0 §7.2).
- `TreeView.searches(node)` lists the bindings in (rev, kind, search_id) order.

## 7. Basis and scores (F4b)

### 7.1 Survey

A `SURVEY` at a searchable node is unrestricted, with MultiPV = profile `multipv`.

### 7.2 Comparison

- The **comparison set** of N is its survey moves ∪ every `PLAYED` / `EXPLORED` child move of N
  at this revision. `ROOT`, `ENGINE`-only and `ANALYSIS` children never enter it (A0 §7.3).
- A comparison is **needed** iff the set is larger than the survey moves. It is one search
  with `root_moves` = the set and MultiPV = its size. Sets only grow, so "larger than the last
  compared set" is the re-comparison trigger (A0 §7.3).

### 7.3 `BasisEntry`

`BasisEntry(node, rev, value)`. The value is the **first** row that applies (F4D-C4):

| # | Situation | `value` |
| --- | --- | --- |
| 1 | N terminal or `after_terminal` | `NOT_APPLICABLE` |
| 2 | N has no survey (engine-only, never searchable, or no engine) | `NOT_COMPUTED(PARENT_NOT_SEARCHED)` |
| 3 | the survey is irregular | `NOT_COMPUTED(IRREGULAR_SEARCH)` |
| 4 | no comparison needed | the survey's `search_id` |
| 5 | comparison needed, effective expansion without `comparison` | `NOT_COMPUTED(COMPARISON_NOT_REQUESTED)` |
| 6 | comparison needed and skipped (budget, deadline) | `NOT_COMPUTED(BUDGET)` / `NOT_COMPUTED(DEADLINE)` |
| 7 | latest comparison irregular | `NOT_COMPUTED(IRREGULAR_SEARCH)` |
| 8 | latest comparison regular | the comparison's `search_id` |

- An entry is written only at a node that has a survey, and only when its value changes. Rows 1
  and 2 are never written. `TreeView.basis(node)` derives them when no entry is visible, so an
  engine-only node costs no rows.
- An irregular survey stops the node's comparisons (row 3).

### 7.4 Scores

- `TreeView.child_score(child)` returns one of:
  - `SearchScore(search_id, rank, score, bound)` from the parent's basis;
  - `NOT_IN_BASIS` when the child's move is not a root move of the basis search;
  - the basis's own `NOT_COMPUTED` / `NOT_APPLICABLE` value.
- `order(a: SearchScore, b: SearchScore)` compares two scores of **one** search, by rank. It
  raises `CrossSearchError` for different searches. The tree stores no score difference.

## 8. Engine lines, tiers, budget (F4b)

### 8.1 Engine lines

- **The walk.** For every line of a search attached at anchor A, the PV is walked from A. Each
  move reuses an existing edge if there is one; otherwise it adds a node.
- **Roles.**
  - Every edge and node on the walk gets `ENGINE(anchor A, search_id, rank, pv_index)`.
  - `pv_index` of the first move is 1. The anchor gets no `ENGINE` role; it is bound through
    `NodeSearch` (F4D-N5a).
  - Role order follows A0 §3.5.
  - Line depth and seldepth live in the search record, not in the role. This amends A0 §3.2.
- **Where the walk stops:**
  - at a terminal node (checkmate, stalemate, automatic draw);
  - at the end of the PV;
  - when `max_nodes` is reached and the next move needs a **new** node (F4D-N5b);
  - when the request deadline has passed (checked before each line).
- **Line record.**
  - Id: `EngineLineId(anchor, search_id, rank)`.
  - End status: `CHECKMATE | STALEMATE | DRAW_RULE(kind) | PV_END | BUDGET_LIMIT`.
  - `unattached_plies` = the PV plies not attached.
  - `EngineLineFact.pv` always keeps the whole PV.
- **`LineRecord` generalization** (F4D-N5).
  - `line_id: LineId | EngineLineId`; `origin`; `unattached_plies` (0 for input lines).
  - Canonical order: input lines first, as now, then engine lines by (anchor, search_id, rank).
- **New nodes.** Nodes created by attachment are engine-only (no input role) and are never
  searched (A0 §7.5, Q3).

### 8.2 Family tiers

- **Input-role nodes:** the session's eager set (F2-D §9).
- **Engine-only nodes:** the **tier** = `{status, material, draw, move}` ∩ the eager set,
  closed under `requires` (F4D-C8). `status`, `draw` and `move` are always included.
- **Shared and resolved records.** The tier is what an engine-only node is guaranteed. Other
  records can still be readable at it:
  - POSITION records are shared by `PositionKey` with a transposed input node;
  - SPAN and EDGE resolution computes requirements at grandparents and parents.

  Tests assert the guarantee, not exclusivity.
- **Reading a missing record.** `TreeView.fact` returns:
  - `NotComputed("tier")` for a family in the eager set, missing at a node with no input role
    visible at the view's revision;
  - `NotComputed("not requested")` for a family outside the eager set.
- **Gaining an input role** (F2D-N4, R2-C8). When an `extend` line passes through, **or starts
  at**, an existing engine-only node, the node gets its input role at that revision, and every
  eager-set family it lacks is computed in that revision. This replaces F1's early return in
  `add_child`, and the start node of a line is handled the same way. The node is then a
  request node (§6.3).

### 8.3 Budget and deadline (F4D-C2, C3)

- **What counts.** `max_searches` counts **engine calls** over the session. Store hits and
  in-session reuses are free (Q4).
- **Pre-check** (before any work, as A0 §2.4). The request is refused (`BudgetExceededError`)
  when either does not fit:
  - its input nodes do not fit `max_nodes`;
  - its **surveys** do not fit the remaining `max_searches`. That is one per request node that
    will become searchable without a survey, counting role gain and expansion upgrades.
- **Skipping.** Comparisons and `ANALYSIS` searches are not part of the pre-check. They run in
  §6.3 order while the budget lasts. A skipped comparison writes
  `BasisEntry = NOT_COMPUTED(BUDGET)` and is retried when N is a request node again. A skipped
  `ANALYSIS` search is listed in the manifest.
- **Deadline.** `deadline_per_request_ms`, when set, is checked before every engine call and
  before every engine line.
  - Past the deadline, the request's remaining surveys still run; the pre-check bounds them.
  - Remaining comparisons are skipped (`NOT_COMPUTED(DEADLINE)`), as are `ANALYSIS` searches.
  - Remaining lines are not attached (`BUDGET_LIMIT`).
  - The revision is marked load-dependent (A0 §3.5).
- **Nodes.** PV nodes use the cumulative `max_nodes`, about 48 per input node on the Opera
  sample. A caller sizing the budget for a long game must account for them (F4D-N6).
- **Failure.** An `EngineError` or refused output refuses the whole request; nothing is
  committed.
- **No retry of lines** (F4D-R2-N1). Attachment is once per (anchor, search). A line cut by the
  budget or a deadline keeps its `BUDGET_LIMIT` record and is not resumed later. A line
  skipped entirely gets a record with `BUDGET_LIMIT` and `unattached_plies = len(pv)`.
  Comparisons, unlike lines, are retried (§6.3), because a node's basis depends on them, while
  an engine line is only an attested continuation.

## 8a. Manifest (R2-C4)

Each revision's delta (A0 §3.3) adds:
- searches run, by kind;
- searches reused, by source (store, session);
- comparisons and `ANALYSIS` searches skipped, with the reason (budget, deadline, not
  requested);
- engine lines attached, by end status, including lines cut or skipped by a deadline;
- `load_dependent: bool`, true when a deadline skipped work **or** an irregular search was
  recorded.

The open delta also names the profile, the engine identity and both pinned-option groups. Run
and reuse counts are metadata outside the digest (A0 §3.5).

## 9. Test obligations

### 9.1 F4a

1. **Adapter, against a fake UCI engine** (a small script speaking UCI; F4D-B1):
   - illegal, null, unparsable and SAN-only PV tokens are passed on and refused by
     normalization;
   - a bound line followed by an exact line of the same rank keeps only the last line;
   - a scored line without `pv` is refused;
   - a rank gap, a duplicate rank and too many ranks are refused; fewer ranks are passed on;
   - `EvalFile` and `Threads` are sent once at start, never per search (M11);
   - a line without `wdl` while WDL is set is refused;
   - a wrong engine name is refused;
   - process death and a missing `bestmove` raise `EngineError`;
   - the exact command sequence of §3.3, including every pinned option, is sent on every
     search;
   - a cap reached sends `stop` and yields `TIME`.
2. **Normalization** through `ScriptedEngine`:
   - Cp and Mate with both sides to move;
   - "mate 0" refused;
   - WDL present and absent, with its sign for Black to move;
   - rank rules, including `TIME` searches with fewer ranks;
   - moves outside `root_moves`.
3. **Regularity:**
   - depth-stopped and exact is regular;
   - `TIME` is irregular even when every line reports full depth;
   - a bound at full depth is irregular;
   - irregular searches are never stored and are reused within a session.
4. **`EngineInput`:**
   - window length on complete and incomplete histories;
   - windows across the root (pre-root moves);
   - en passant form, including a start FEN with a pseudo-legal-only square;
   - fullmove 1;
   - `start_board` never mutated.
5. **`SearchId`:** stable across processes; changed by every preimage field; irregular ids
   include the lines.
6. **Store:** a hit runs no engine (the scripted engine counts calls); regular searches only;
   thread-safe under concurrent sessions.
7. **Real Stockfish** (gated on `CALLIOPE_STOCKFISH_PATH`): §9.3 items 1–4.

### 9.2 F4b

1. **Policy** with `ScriptedEngine`:
   - the root surveyed at `open` under `root_expansion`;
   - survey order;
   - effective expansions (B2.2 cases, including the `NONE` example of §6.2);
   - an `ANALYSIS` request with `FULL` at a `PLAYED` node whose basis is
     `COMPARISON_NOT_REQUESTED` leaves that basis unchanged (R2-C1);
   - no comparison after an irregular survey (R2-C6);
   - two transposed request nodes share one irregular search (R2-C7);
   - attachment order (R2-C8);
   - role gain at a line's start node (R2-C8);
   - invalid expansions refused;
   - comparison trigger and set, re-comparison, and retry after a skip;
   - `ANALYSIS` children never in the set;
   - `ANALYSIS` searches: one per node per request, the end node excluded;
   - attachment after a role gain or an expansion upgrade;
   - no duplicate attachment or `NodeSearch`;
   - every basis row of §7.3 and its precedence;
   - `NOT_IN_BASIS`;
   - `order` refusing cross-search operands.
2. **Zero engine calls:**
   - at terminal, `after_terminal` and engine-only nodes;
   - for `engine=None` sessions;
   - in `ensure`;
   - outside the request's nodes.
3. **Engine lines:**
   - roles and indexes;
   - edges shared with input lines;
   - transpositions (one search record, two `NodeSearch`, two lines);
   - stops at checkmate, stalemate and automatic draws, with `unattached_plies`;
   - `BUDGET_LIMIT` only when a new node is needed.
4. **Tiers and role gain:**
   - the tier guarantee;
   - the `"tier"` vs `"not requested"` readings;
   - `ensure` completes a node;
   - a node gaining an input role gets the missing families at that revision and is surveyed.
5. **Budget:**
   - the pre-check counts surveys, including role gain;
   - comparisons and `ANALYSIS` searches skipped with `NOT_COMPUTED(BUDGET)`;
   - deadline skipping and load-dependence;
   - the manifest delta of §8a;
   - an engine failure commits nothing.
6. **Session binding:**
   - `extend` without a port, or with a different identity, is refused;
   - two trees sharing one port and one store, used from two threads, give the same records as
     sequential use.
7. **Auditor extension:**
   - every attached node and edge equals a python-chess replay of the PV;
   - every `EngineInput` equals the independently computed window;
   - every basis entry follows §7.3 from the recorded searches;
   - no record holds a cross-search difference.
8. **Equivalence:** a tree built with an empty store and the same tree rebuilt from the filled
   store are equal record by record (cold vs warm), with every search regular. Run and reuse
   counts sit in `SearchRuntime` and the manifest, outside that comparison (F4D-N3).

### 9.3 Real-Stockfish acceptance (gated on `CALLIOPE_STOCKFISH_PATH`)

| # | Check | Packet |
| --- | --- | --- |
| 1 | Identity of the configured binary recorded and admitted (§3.2) | F4a |
| 2 | Fresh-state determinism (M2, M10) with the raw protocol, after unrelated searches and in a new process | F4a |
| 3 | En passant form (M3) on constructed and random positions, via the engine's `d` output | F4a |
| 4 | Window equivalence (M4), with windows strictly shorter than the history and repetition histories | F4a |
| 5 | One full game (`PLAYED`) built twice, cold and warm store: identical trees | F4b |
| 6 | Cost record: per-search time, nodes per input node, attachment time (A0 §7.5 redone on Stockfish 19) | F4b |

## 10. Amendments to A0 made by this packet

- **§3.1:** `EngineInput` follows what the configured engine parses. For Stockfish 19 that is
  the legal en passant square (M3). The Stockfish 17 behaviour is kept as history.
- **§2.1:** `OpenRequest` gains `engine`, `root_expansion` and `defaults` as `Defaults(played,
  explored)`; `ExpansionSpec` is (survey, comparison, attach_lines) (F4-D §6.1).
- **§2.4:** the pre-check refuses when input nodes or surveys do not fit; comparisons and
  `ANALYSIS` searches are skipped while the budget lasts (F4-D §8.3).
- **§3.2:**
  - the `ENGINE` role is `ENGINE(anchor, search_id, rank, pv_index)`; line depth and seldepth
    are read from the search record;
  - the input-role kinds gain `ROOT` (F4-D §6.1).
- **§3.5:** role kind order `ROOT < PLAYED < EXPLORED < ANALYSIS`, then `ENGINE`.
- **§7.1:** `EvalFileSmall` and any other network option are recorded when offered. Stockfish
  19 has one network. The identity records the binary's sha256 and the offered options, and
  search-affecting options are pinned (F4-D §3.2).
- **§7.2:**
  - kinds are `SURVEY | COMPARISON | ANALYSIS`;
  - `SearchRuntime` is (rev, search_id, elapsed_ms, reused);
  - `stopped_by` comes from the adapter (F4-D §3.3, §5.3).
- **§7.4:**
  - the FEN form is the legal en passant square for Stockfish 19;
  - a new engine version re-passes the en passant acceptance;
  - the last bullet's `b8g3` / `b8b3` example (two histories kept apart) describes Stockfish
    17. On Stockfish 19 those histories map to one input, correctly.
- **§7.6:** a `ROOT` row (`root_expansion`); the validity rule (`comparison` and
  `attach_lines` require `survey`); `ANALYSIS` comparisons are `ANALYSIS`-kind searches and
  never policy comparisons (F4-D §6.2, §6.3).
- **§12:** "both nets" applies to Stockfish 17. On Stockfish 19 there is one.

## 11. Open questions (answered by the review)

| # | Question | Answer |
| --- | --- | --- |
| Q1 | Should the fact engine own the engine process? | No. The caller owns `EnginePort`. Requirements: the adapter lock, the session bound to the identity, pinned options (§3) |
| Q2 | Re-survey when the expansion gains `survey`? | The node is surveyed then, because it has no survey yet. A node is never surveyed twice. Its earlier searches are attached under §6.3.4 |
| Q3 | Search engine-only nodes on later PVs? | No (A0 §7.5) |
| Q4 | Count store hits in `max_searches`? | No. The pre-check model is §8.3 |
| Q5 | Admit only Stockfish 19? | Yes, by exact name. The en passant acceptance is repeated for any new version |

## 12. Review dispositions (rev. 1 `97434b3`: NOT_READY)

| Finding | Disposition |
| --- | --- |
| F4D-B1 python-chess `analyse()` merges info lines and drops illegal PVs | raw-UCI adapter, last line per rank, refusal rules (§2.2, §3.3); fake-UCI adapter tests (§9.1.1) |
| F4D-B2.1 the root has no role at `open` | `ROOT` role with `root_expansion` (§6.1) |
| F4D-B2.2 expansions per request vs roles per node | expansions stored per role entry; effective expansion = union; refusal of invalid specs; `COMPARISON_NOT_REQUESTED` row (§6.1, §6.2, §7.3) |
| F4D-B2.3 attachment tied to "run in this request" | per-node attachment of unattached searches at request nodes (§6.3.4) |
| F4D-B2.4 duplicate engine lines | (anchor, search) attached once; `NodeSearch` unique (§6.3, §6.4) |
| F4D-C1 a stop inside the last iteration reported as full depth | `go depth` without `movetime`; adapter-sent `stop` ⇒ `TIME` (§3.3, §5.3) |
| F4D-C2 pre-check incomplete and stricter than A0 | refusal only for input nodes and surveys; comparisons and `ANALYSIS` skipped with `BUDGET` (§8.3) |
| F4D-C3 retry of skipped comparisons; deadline before attachment | retried only when the node is a request node; deadline before every line (§6.3, §8.3) |
| F4D-C4 basis row precedence; implicit rows | ordered table; rows 1–2 derived, never written (§7.3) |
| F4D-C5 `ANALYSIS` semantics | §6.3.3 |
| F4D-C6 port sharing and session binding | adapter lock, thread-safe store, identity bound at `open` (§3.1, §6.1) |
| F4D-C7 stated protocol is not what python-chess sends | raw protocol, verified (M10) (§3.3) |
| F4D-C8 tier definition and guarantee | tier ∩ eager set; guarantee, not exclusivity; `"tier"` reading (§8.2) |
| F4D-C9 unrecorded search-affecting options | pinned options; offered options in the identity; threads 1; no WDL switch; exact name (§3.2) |
| F4D-C10 A0 statements left stale | §10 amendments |
| F4D-N1 ambiguous preimage | length-prefixed; root moves sorted as strings (§5.4) |
| F4D-N2 depth-1 time stop with fewer ranks | allowed for `TIME` searches (§5.2) |
| F4D-N3 runtime keyed by search only; counts in the digest | (rev, search_id); outside comparisons and the digest (§5.1, §9.2.8) |
| F4D-N4 what the tape holds | raw `RawSearch` (§3.1) |
| F4D-N5 `LineRecord` generalization; anchor role; `max_nodes` stop | §8.1 |
| F4D-N6 PV nodes consume `max_nodes` | stated (§8.3) |
| F4D-N7 WDL field names | `white_win`, `draw`, `black_win` |
| F4D-N8 window-start parse vs `do_move` | stated (§4) |

### Re-review of rev. 2 (`3ca6d0b`: READY_WITH_CORRECTIONS)

| Finding | Disposition |
| --- | --- |
| R2-C1 `ANALYSIS` `comparison` flag could change a `PLAYED` node's basis | policy `comparison` OR-ed over `ROOT` / `PLAYED` / `EXPLORED` only; STOP line reworded (§6.2) |
| R2-C2 `EvalFile` resent per search costs about 200 ms | start-time and per-search option groups; M11 recorded; adapter test (§3.2, §9.1.1) |
| R2-C3 rank rules contradicted each other | adapter refuses gaps, duplicates and excess; fewer ranks judged by normalization (§3.3) |
| R2-C4 manifest section dropped | §8a |
| R2-C5 A0 §2.1, §2.4, §3.5, §7.6 not amended | amended (§10) |
| R2-C6 comparison after an irregular survey | step 2 requires a regular survey; `ANALYSIS` searches still run (§6.3) |
| R2-C7 irregular cache missed the pending request | pending searches included (§5.5) |
| R2-C8 attachment order; role gain at start nodes | order fixed; start nodes included (§6.3, §8.2) |
| R2-N1 lines not retried | stated, with the skipped-line record (§8.3) |
| R2-N2 already-bound `ANALYSIS` search not re-attached | stated (§6.3) |
| R2-N3 SAN fallback for engine PV tokens | structural UCI only (§5.2) |
| R2-N4 missing WDL while set | refused (§5.2) |
| R2-N5 `ROOT` in engine-less trees | written only with an engine (§6.1) |
| R2-N6 adapter timeouts; elapsed | 10 s; from `go` (§3.3) |
| R2-N7 cost of `ANALYSIS` comparisons | stated (§6.3) |
| R2-N8 exception to "effective expansion governs" | named (§6.2) |

**STOP** if F4:
- adds an evaluative word or value;
- stores any cross-search arithmetic, or lets `order` compare across searches;
- infers an engine terminal state from the board or a board state from the engine;
- repairs, truncates or drops PV plies, or merges info lines across depths;
- re-validates trusted records at runtime;
- makes an engine call outside the request's planned work (§6.3), or reuses a stored search
  for a different `EngineInput`, profile, identity or option set;
- lets an `ANALYSIS` request change a node's comparison set or which comparison is its basis.
