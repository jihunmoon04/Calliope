# Fact engine — packet F4-D: Stockfish searches, comparison basis and engine lines

Status: **rev. 1 — awaiting independent F4-D review** (design only).
Date: 2026-10-09. Base: `main @ 3a66eb5` (F1–F3 merged).

Parent design: [`fact-engine-a0-design.md`](fact-engine-a0-design.md) rev. 4 (sections 2.1,
2.4, 3.1, 3.2, 7, 9, 14; amended by this packet in sections 3.1, 7.1 and 7.4). Siblings:
[`fact-engine-f2-design.md`](fact-engine-f2-design.md),
[`fact-engine-f3-design.md`](fact-engine-f3-design.md) and their implementation records.

## 0. Scope

A0 §7 already decides the engine model: a fresh state per search; the survey and union
comparison; a revisioned basis; PV attachment up to terminal nodes; the result store; the
budget. This packet freezes what A0 left as a sketch:

- the engine boundary (`EnginePort`), profile, identity and fresh-state protocol;
- the exact `EngineInput`, and its en passant form as Stockfish 19 actually parses it;
- the search record, normalization, regularity, `SearchId` and the result store;
- tree integration: `ExpansionSpec`, when searches run, `NodeSearch`, the basis, scores,
  engine-line attachment, family tiers for engine-only nodes, an engine-only node gaining an
  input role (F2D-N4), budget and deadline;
- test obligations, including a scripted engine and real-Stockfish acceptance.

**Two implementation packets.** F4 is large, so it is delivered in two reviewed packets that
share this design:

| Packet | Content |
| --- | --- |
| **F4a** | `EnginePort`, `StockfishEngine` adapter, `EngineProfile`, `EngineIdentity`, `EngineInput` construction, search records, normalization, regularity, `SearchId`, `EngineResultStore`, `ScriptedEngine` for tests. No tree changes |
| **F4b** | tree integration: `ExpansionSpec`, survey / comparison / basis, `NodeSearch`, `SearchScore`, engine-line attachment, tiers, role gain, budget and deadline, manifest |

**Legacy evidence** (frozen MVP, tag `legacy-mvp-g0`): `ADP` =
`src/calliope/adapters/stockfish/adapter.py`.

## 1. Measurements on Stockfish 19 (2026-10-09)

The engine for v1 is the Stockfish 19 build at `~/opt/stockfish/stockfish` (tag `sf_19`,
commit `edb0d9d`, armv8 NEON, g++ 13.3; sha256 `70773580…bb5d`). With it, all 127 legacy
integration tests pass, including the 7 that fail on Stockfish 17. Scratch scripts, not
committed:

| # | Question | Result |
| --- | --- | --- |
| M1 | Options offered | `EvalFile` = `nn-1a298aa575a0.nnue` (embedded); **no `EvalFileSmall`** (A0 §7.1 expected two nets, as in Stockfish 17); `UCI_ShowWDL` offered; `Clear Hash` is a button; `Threads` 1–1024; `Hash` 1–33554432 |
| M2 | Fresh state (new `game` object, so `ucinewgame`, plus `Clear Hash`) | depth-12 MultiPV-5 results identical before and after unrelated searches on 3 positions; with one shared game and no clearing, all 3 changed |
| M3 | En passant form | over 412 positions after double pushes (21 with a legal en passant capture, 3 with only a pseudo-legal one) plus constructed pins, the FEN Stockfish prints (`d`) has exactly python-chess's **legal** en passant square, 0 mismatches. Stockfish 19 drops a pseudo-legal-only square, for example `7k/8/8/KPp4r/8/8/8/8 w - c6` |
| M4 | Window input vs full history | on 12 random-game positions and 3 constructed repetition histories, (window-start FEN + window moves) gives lines identical to the full game; a bare FEN differs in all 3 repetition cases (e.g. startpos after `Nf3 Nf6 Ng1 Ng8` ×2: +14 `d2d4` with history, +32 `e2e4` without) |
| M5 | Time stop | depth 30 with a 30 ms cap stops at depths 6–7 with mixed depths across ranks and an `upperbound` on rank 1 |
| M6 | Depth stop | depth 12 with a 2000 ms cap: every line depth 12, every score exact |
| M7 | MultiPV above the number of legal moves | one legal move, MultiPV 5: one line |
| M8 | `searchmoves` | the comparison and the survey give different scores for the same moves (a2a3 +18 in the survey vs +10 restricted to 3 moves; h2h3 +33 vs +19): A0 §7.3 holds on Stockfish 19 |
| M9 | Cost, 80 surveys from random games, depth 12, MultiPV 5, 1 thread, 16 MB | median 170 ms, p90 417 ms, max 810 ms; 0 irregular; PV plies median 9, max 22 |

## 2. Legacy findings (ADP, by code reading)

| # | Legacy behaviour | Where | Here |
| --- | --- | --- | --- |
| E1 | one `game` token per request, so `ucinewgame` once per request; hash carried between searches | ADP:71–84, 134–142 | new game and `Clear Hash` per search (§3.3) |
| E2 | the engine gets a FEN only, no moves: repetition and fifty-move history invisible (M4) | ADP:126, 208–215 | `EngineInput` with the window moves (§4) |
| E3 | identity = name only, `version=None`; no network, no options, no binary | ADP:94–101 | `EngineIdentity` (§3.2) |
| E4 | bound scores **raise**; a time-stopped search cannot be recorded | ADP:301–302 | recorded as irregular (§5.3) |
| E5 | WDL turned into fractions | ADP:320–330 | raw permille, White's view (§5.2) |
| E6 | no stop reason; Hash and Threads sent only if set | ADP:180–198 | `stopped_by`; every option sent every search (§3.3) |
| E7 | PV legality checked, SAN attached | ADP:285–297 | kept; PV moves go through the one canonicalizer (A0 §2.3) |

## 3. Engine boundary (F4a)

### 3.1 `EnginePort`

```text
class EnginePort(Protocol):
    identity: EngineIdentity
    def search(self, request: SearchRequest) -> RawSearch: ...     # one fresh-state search
    def close(self) -> None: ...

SearchRequest(input: EngineInput, profile: EngineProfile, root_moves: tuple[UCI, ...] | None,
              multipv: int)
RawSearch(lines: tuple[RawLine, ...], elapsed_ms: int)               # unnormalized
RawLine(multipv, pv: tuple[UCI, ...], score: ("cp", int) | ("mate", int), bound,
        wdl: (int, int, int) | None, depth, seldepth, nodes, tbhits)  # side-to-move view
```

- `StockfishEngine` implements it with python-chess (`SimpleEngine.popen_uci`). It is the only
  module that talks UCI. `ScriptedEngine` implements it from a table of
  (request → `RawSearch`) for tests.
- The fact engine never starts or owns a process. The caller creates the port and passes it to
  `FactEngine(families, engine=port, store=store)`, and closes it. One port serves one writer
  at a time; the tree write lock already serializes requests (A0 §3.3).
- Normalization (§5) lives in the fact engine, not in the adapter, so the scripted and the real
  engine go through the same code.

### 3.2 Profile and identity

```text
EngineProfile(name="d12_mpv5_v1", depth=12, time_cap_ms=2000, multipv=5, threads=1,
              hash_mb=16, show_wdl=True)
EngineIdentity(name, author, binary_sha256, eval_files: tuple[(option, value), ...],
               options_offered: tuple[str, ...])
```

- `name` and `author` are the UCI `id` lines. `binary_sha256` is the hash of the executable the
  adapter started (resolved through symlinks). `eval_files` lists every offered option whose
  name starts with `EvalFile`, with its value (Stockfish 19: one entry).
- Every option the profile sets is part of every search record (§5.1), not of the identity.
- **Supported identities.** v1 accepts engines whose `name` starts with `Stockfish 19`. Another
  version must pass the F4 acceptance (§9.3: fresh-state determinism, the en passant form,
  window equivalence) before it is admitted, because `EngineInput` (§4) encodes Stockfish 19's
  en passant rule. `StockfishEngine` refuses other names at start (`EngineUnsupportedError`).

### 3.3 Fresh state per search

Before every search the adapter:
1. passes a **new** `game` object to `analyse`, so python-chess sends `ucinewgame`;
2. sends `setoption name Clear Hash`;
3. sends every profile option: `Threads`, `Hash`, `UCI_ShowWDL` (when offered), `MultiPV`.

Then it sends `position fen <window-start FEN> moves <window moves>` and
`go depth 12 [searchmoves …]` with the time cap enforced by python-chess's limit. M2 shows this
is deterministic for depth-stopped searches.

## 4. `EngineInput` (F4a; amends A0 §3.1, §7.4)

```text
EngineInput(fen: str, moves: tuple[UCI, ...])
```

- `w = min(halfmove_clock(node), known_plies(node))`, the repetition window (A0 §7.4).
- The known history of a node is `session.start_board` (copied before use, F1R-N3) followed by
  the canonical pre-root moves and the tree path moves. `moves` = its last `w` moves;
  `fen` = the position before them.
- **FEN form:** placement, side, castling, the **legal** en passant square (python-chess
  `en_passant="legal"`, which equals Stockfish 19's own parse, M3), the halfmove clock, and
  fullmove number `1` (Stockfish uses it only for time management). This replaces A0 §7.4's
  "Stockfish's own condition (`en_passant="xfen"`)", which described Stockfish 17
  (`position.cpp:268-274, 783-788`).
- **Consequence:** for Stockfish 19, two histories equal under `PositionKey` whose windows are
  equal give the same `EngineInput`. `EngineInput` still differs from `PositionKey`, because it
  carries the halfmove clock and the window moves.
- With incomplete history the window starts at the start board; its halfmove clock is the one
  given in the root FEN (the engine sees exactly the known window, A0 §7.4).

## 5. Search records (F4a)

### 5.1 Record

```text
EngineSearch(search_id, input: EngineInput, kind: SURVEY | COMPARISON | ANALYSIS,
  root_moves: tuple[UCI, ...] | None,          # sorted canonical UCI; None = unrestricted
  multipv: int,                                 # requested
  profile: EngineProfile, identity: EngineIdentity,
  stopped_by: DEPTH | TIME, regular: bool,
  lines: tuple[EngineLineFact, ...])            # rank order
EngineLineFact(rank, move: UCI, score: Cp(int) | Mate(winner: Color, moves: int),
  bound: EXACT | LOWER | UPPER, wdl: Wdl(win, draw, loss) | UNAVAILABLE,
  depth, seldepth, nodes, tbhits, pv: tuple[UCI, ...])
SearchRuntime(search_id, elapsed_ms, reused: bool)   # metadata; not a fact, outside the digest
```

- `kind = ANALYSIS` is a search that an `ANALYSIS(by)` request asked for (§6.1); it is never a
  survey or a basis of any node.
- Records are frozen and created only by the fact engine (A0 §9).

### 5.2 Normalization

Applied to every `RawSearch` before anything is recorded:

1. **Scores from White's view.** `Cp(n)`; `Mate(winner, moves)` with `moves ≥ 1` the moves to
   mate as Stockfish reports them. A side-to-move "mate 0" (the side to move is mated) cannot
   reach a search, because terminal nodes are never searched (A0 §7.8); if it arrives, the
   output is refused.
2. **WDL** in permille from White's view, kept as integers; `UNAVAILABLE` only when the engine
   does not offer `UCI_ShowWDL` (A0 §7.1).
3. **PV:** every move goes through `canonical_move` replayed from the search position (window
   end). An illegal, null or unparsable move refuses the whole request with
   `EngineOutputError`. Nothing is repaired or cut.
4. **Lines:** ranks must be exactly `1..k` with
   `k = min(multipv, number of legal root moves in the restriction)` (M7); `move = pv[0]`;
   with `root_moves`, every `move` is in the restriction and the moves are distinct. Anything
   else refuses the request.

### 5.3 Regularity

- `stopped_by = DEPTH` iff every line has `depth = profile.depth`; otherwise `TIME`.
- `regular` iff `stopped_by = DEPTH` and every bound is `EXACT` (M5, M6).
- An irregular search is recorded as it was reported. It is never a basis (§7.3), never enters
  the store (§5.5), and within one session it is reused for an identical request (A0 §7.7).

### 5.4 `SearchId`

`SearchId = "s_" + digest("search", input.fen, *input.moves, kind, *root_moves or ("*",),
multipv, profile fingerprint, identity fingerprint)` for a regular search. For an irregular
search the preimage also holds a digest of its normalized lines (A0 §3.1, R3-C3). A profile
fingerprint covers every profile field; an identity fingerprint covers every identity field.

### 5.5 `EngineResultStore`

- An in-memory map `SearchId → EngineSearch` of regular searches, shared across sessions by
  passing the same store to `FactEngine`.
- A hit runs no engine and is recorded as reused (`SearchRuntime.reused`, manifest §8).
- Persistence and tape replay are F5. Within F4 the store is the test fixture: a store filled
  by a real-Stockfish run can be replayed through `ScriptedEngine`.

## 6. Tree integration (F4b)

### 6.1 Requests

```text
OpenRequest(root, families, budget, engine: EngineProfile | None = None,
            defaults: Defaults = Defaults())
ExtendRequest(lines, role, expansion: ExpansionSpec | None = None)
ExpansionSpec(survey: bool, comparison: bool, attach_lines: bool)
Defaults(played = ExpansionSpec(True, True, True), explored = ExpansionSpec(True, True, True))
SessionBudget(max_nodes, max_searches: int | None = None, deadline_per_request_ms: int | None)
```

- `engine = None` (the default) gives a tree with no attested facts, exactly as in F1–F3. An
  `engine` profile requires a port on the `FactEngine`; otherwise `open` refuses.
- `ANALYSIS` requests must give `expansion` (no default, A0 §2.1); `PLAYED` / `EXPLORED` use
  the session defaults unless `expansion` overrides them.
- For an `ANALYSIS` expansion, `comparison = True` means one `ANALYSIS`-kind search at each node
  of the line, restricted to the set {survey moves at that node, if any} ∪ {the request's own
  child moves}; it never changes the node's basis (A0 §7.3).

### 6.2 Which nodes are searched

A node N is **searchable** in a request iff all hold:
- N has an input role whose expansion (union over its roles, A0 §7.6) has `survey = True`;
- N is not terminal and not `after_terminal` (A0 §7.8; `UNPROVEN` nodes are searched);
- the session has an engine profile.

In each `open` / `extend`, after the input nodes are built, the fact engine:
1. **Surveys** every searchable node of the request that has no survey yet, in line order
   (the root first at `open`; then each line's nodes from its start node);
2. **Compares** (§7.2) every node that needs a new comparison, in the same order;
3. **Attaches** the PVs of every search run or reused in this request whose expansion has
   `attach_lines = True`, in the same order, rank order within a search (§6.4).

A node already surveyed at an earlier revision is not surveyed again: its `EngineInput` is a
function of the node, so the existing survey is still the answer.

### 6.3 `NodeSearch`

`NodeSearch(node, rev, search_id, kind)` binds a search to a node at a revision. A search with
the same `EngineInput` reused at another node is one record referenced twice (A0 §7.2).
`TreeView.searches(node)` lists them in (rev, kind, search_id) order.

### 6.4 Engine lines

- For every line of an attached search at anchor A, the PV is walked from A. Each move reuses
  the existing edge if there is one; otherwise it adds a node (eager tier, §6.5).
- Every edge and node on the walk gets `ENGINE(anchor A, search_id, rank, pv_index)`; `pv_index`
  of the first move is 1. Role order follows A0 §3.5.
- The walk stops at a **terminal** node (checkmate, stalemate, automatic draw), at the end of
  the PV, or when `max_nodes` is reached. The `LineRecord` is
  `EngineLineId(anchor, search_id, rank)` with end `CHECKMATE | STALEMATE | DRAW_RULE(kind) |
  PV_END | BUDGET_LIMIT` and `unattached_plies` = PV plies not attached. `EngineLineFact.pv`
  always keeps the whole PV.
- New nodes created by attachment are **engine-only** (no input role) and are not searched.

### 6.5 Family tiers

- **Input-role nodes:** the session's eager set (F2-D §9), as now.
- **Engine-only nodes:** the eager tier `status`, `material`, `draw`, `move`, closed under
  `requires`. Other families read `NotComputed("tier")` until `ensure` computes them.
- **Gaining an input role (F2D-N4).** When an `extend` line passes through an existing
  engine-only node, the node gets its input role at that revision and every eager-set family
  it lacks is computed in that revision. F1's `add_child` early return is replaced by this
  path. The node becomes searchable under the new role (§6.2).
- `TreeView.fact` distinguishes `NotComputed("tier")` from `NotComputed("not requested")`.

### 6.6 Budget and deadline

- `max_searches` counts **engine calls** over the session; store hits and in-session reuses are
  free.
- **Pre-check** (before any work): the request's worst case is 2 calls per new searchable node
  plus 1 per existing node that gains a new `PLAYED` / `EXPLORED` child outside its
  comparison set. If that exceeds the remaining budget, the request is refused
  (`BudgetExceededError`), as for `max_nodes`.
- **During the build**, PV attachment stops when `max_nodes` is reached (`BUDGET_LIMIT`).
- `deadline_per_request_ms`, when set, is checked before each engine call. Past the deadline,
  surveys still run (they are bounded by the pre-check), but remaining comparisons are
  skipped (`BasisEntry = NOT_COMPUTED(DEADLINE)`) and no further PVs are attached
  (`BUDGET_LIMIT`). The manifest records it, and the revision is marked load-dependent
  (A0 §3.5).
- An engine failure (`EngineError`) or refused output refuses the whole request; nothing is
  committed. Regular searches already finished stay in the store.

## 7. Basis and scores (F4b)

### 7.1 Survey

`SURVEY` at a searchable node: unrestricted, MultiPV = profile `multipv`.

### 7.2 Comparison

- The **comparison set** of N = survey moves ∪ every `PLAYED` / `EXPLORED` child move of N at
  this revision. `ENGINE`-only and `ANALYSIS` children never enter it (A0 §7.3).
- A comparison runs iff the set is larger than the survey moves and differs from the set of
  N's latest comparison. It is one search with `root_moves` = the set and MultiPV = its size.
- Re-comparison follows A0 §7.3. The set is always rebuilt from the survey and the current
  input children, never from a skipped entry.

### 7.3 `BasisEntry`

`BasisEntry(node, rev, value)` with `value` one of:

| Situation | `value` |
| --- | --- |
| survey regular, no comparison needed | the survey's `search_id` |
| comparison ran and is regular | the comparison's `search_id` |
| comparison needed but skipped (budget, deadline) | `NOT_COMPUTED(BUDGET)` / `NOT_COMPUTED(DEADLINE)` |
| survey or comparison irregular | `NOT_COMPUTED(IRREGULAR_SEARCH)` |
| N terminal or `after_terminal` | `NOT_APPLICABLE` |
| N never searched (engine-only, or no engine in the session) | `NOT_COMPUTED(PARENT_NOT_SEARCHED)` |

A new entry is written only when the value changes. `TreeView.basis(node)` returns the entry
with the highest `rev ≤` the view's revision.

### 7.4 Scores

- `TreeView.child_score(child)` returns `SearchScore(search_id, rank, score, bound)` from the
  parent's basis, or `NOT_IN_BASIS` when the child's move is not a root move of the basis
  search, or the basis's `NOT_COMPUTED` / `NOT_APPLICABLE` value.
- `order(a: SearchScore, b: SearchScore)` compares two scores of **one** search (by rank) and
  raises `CrossSearchError` for different searches. The tree stores no score difference.

## 8. Manifest

Each revision's delta adds: searches run (by kind), searches reused (store, session), searches
skipped (with reason), engine lines attached and their end statuses, and `load_dependent: bool`
(true when a deadline skipped work or an irregular search was recorded). The open delta names
the profile and the engine identity.

## 9. Test obligations

### 9.1 F4a

1. **Normalization** through `ScriptedEngine`:
   - Cp and Mate from both sides to move;
   - "mate 0" refused;
   - WDL present and absent;
   - illegal, null and unparsable PV moves refused, nothing committed;
   - ranks missing, duplicated, or beyond `k`; moves outside `root_moves`.
2. **Regularity:** depth-stopped exact → regular; mixed depths → `TIME`; a bound at full
   depth → irregular; irregular searches never stored, reused within a session.
3. **`EngineInput`:**
   - window length on complete and incomplete histories, across the root (pre-root moves);
   - en passant form legal;
   - fullmove 1;
   - `start_board` never mutated.
4. **`SearchId`:** stable across processes; changes with every preimage field; irregular ids
   include the lines.
5. **Store:** a hit runs no engine (the scripted engine counts calls); regular only.

### 9.2 F4b

1. **Policy** with `ScriptedEngine`:
   - survey order;
   - comparison trigger and set;
   - re-comparison on a new input child;
   - `ANALYSIS` children never in the set;
   - basis values for every row of §7.3;
   - `NOT_IN_BASIS`;
   - `order` refusing cross-search operands.
2. **Engine lines:**
   - PVs attached with roles and indexes;
   - shared edges with input lines;
   - attachment stopping at checkmate, stalemate and automatic draws with `unattached_plies`;
   - `BUDGET_LIMIT`.
3. **Tiers and role gain:**
   - engine-only nodes hold exactly the eager tier;
   - `ensure` completes them;
   - a node gaining an input role gets the missing families at that revision and is surveyed.
4. **Budget:** pre-check refusal; deadline skipping with the manifest's load-dependence; an
   engine failure commits nothing.
5. **Auditor extension:**
   - every attached node and edge equals a python-chess replay of the PV;
   - every `EngineInput` equals the independently computed window;
   - every basis entry follows §7.3 from the recorded searches;
   - no record holds a cross-search difference.
6. **Equivalence:** a tree built with an empty store and the same tree rebuilt from the filled
   store are equal record by record (cold vs warm), with every search regular.

### 9.3 Real-Stockfish acceptance (gated on `CALLIOPE_STOCKFISH_PATH`)

1. Identity of the configured binary recorded and checked against §3.2.
2. Fresh-state determinism (M2) on a fixed position set.
3. En passant form (M3) on constructed and random positions, via the engine's own `d` output.
4. Window equivalence (M4), including repetition histories.
5. One full game (PLAYED) built twice, with an empty store and a warm one: identical trees.
6. Cost record: per-search time, nodes per input node, attachment time (A0 §7.5 numbers redone
   on Stockfish 19).

## 10. Amendments to A0 made by this packet

- **§3.1:** the `EngineInput` paragraph now says the key follows what the engine parses; for
  Stockfish 19 that is the legal en passant square (F4-D M3). The Stockfish 17 behaviour is
  kept as history.
- **§7.1:** `EvalFileSmall` is recorded when offered (Stockfish 19 has one network); the
  identity also records the binary's sha256.
- **§7.4:** the FEN form is the legal en passant square for Stockfish 19 (F4-D §4); a new
  engine version must re-pass the en passant acceptance (§9.3).

## 11. Open questions for the review

| # | Question | Proposed answer |
| --- | --- | --- |
| Q1 | Should the fact engine own the engine process? | No. The caller owns `EnginePort`; this keeps tests, process reuse and shutdown out of the fact engine |
| Q2 | Should a node be re-surveyed when its expansion changes from no-survey to survey? | It is surveyed then, because it has no survey yet; a node is never surveyed twice |
| Q3 | Should engine-only nodes on a PV be searched when they gain `ENGINE` roles from a second search? | No (A0 §7.5); only input roles make a node searchable |
| Q4 | Should `max_searches` count store hits? | No; it limits engine work. Hits are listed in the manifest |
| Q5 | Is admitting only Stockfish 19 too narrow? | It is the measured engine; admitting another one is a small packet that re-runs §9.3 |

**STOP** if F4:
- adds an evaluative word or value;
- stores any cross-search arithmetic, or lets `order` compare across searches;
- infers an engine terminal state from the board or a board state from the engine;
- repairs, truncates or drops PV plies from `EngineLineFact.pv`;
- re-validates trusted records at runtime;
- makes an engine call the request did not plan (§6.2), or reuses a stored search for a
  different `EngineInput`, profile or identity;
- lets an `ANALYSIS` request change a node's basis.
