# Application — PF-D design: a game's analysis time: each search asked once, each position's facts computed once, the game's searches run ahead

Status: **rev. 4 (+ PF1's measured memo default, §3) — re-review of rev. 3 (`4116999`)
READY_WITH_CORRECTIONS (N1–N10) applied (§11);
review of rev. 2 (`066f8ec`) NOT_READY applied in rev. 3 (§10); review of rev. 1 (`c192114`) applied
in rev. 2 (§9)**. Date: 2026-10-29. Base: `main @ 40f3e54` (LM merged). Inputs:
[`fact-engine-f4-design.md`](fact-engine-f4-design.md) (F4-D: §3 the engine port and its
determinism, §5.3 regularity, §5.5 the result store and the searcher, §8.3 the budget, §13 AM1),
[`fact-engine-f2-design.md`](fact-engine-f2-design.md) (F2-D §1.5: a POSITION record depends on its
`PositionKey` alone; §9 what a family may require), [`fact-engine-f5-design.md`](fact-engine-f5-design.md)
(F5-D §3: what the digest covers and excludes), [`reasoning-r0-design.md`](reasoning-r0-design.md)
(R0-D §6.1: round 0's window), [`application-server-design.md`](application-server-design.md)
(AS-D: §3 the pipeline, §4 the ply cache), [`application-cache-cost-design.md`](application-cache-cost-design.md)
(CC-D: the previous cost study), [`agent-ag6-design.md`](agent-ag6-design.md) (AG6-D §4 game jobs
and the engine lock, §10 "a second engine for the job" left out), [`agent-mcp-design.md`](agent-mcp-design.md)
(AG-D AM10: one engine under a fair lock), [`agent-ag4-design.md`](agent-ag4-design.md) (AG4-D §3:
the budget, the meter and the limits); measurements on this host (§0).

The owner asked how to shorten the tools' running time — an asynchronous engine, parallel work, a
rebuilt re-verification loop, or a rebuilt Calliope (2026-10-29). The measurements answer it: two
thirds of a game's engine time asks questions the same process has already answered, and the
re-verification rounds cost under 3% of the run. Three changes that keep every answer give about
−65% on a game on this host, with no change of structure.

## 0. Measurements (2026-10-29)

Paul Morphy – Duke Karl / Count Isouard, Paris 1858 (the Opera Game, 33 plies), through
`server.pipeline.analyse_game` into a fresh ply cache, Stockfish 19 `d12_mpv5_v1`, this host
(2 cores, aarch64, run alone). Wall clock; Python shares from a profile (`cProfile`) of the same run.
**Each configuration was run once** (today's twice: 63.0 s and 62.9 s); differences of a few
seconds are within what one run cannot separate. The review reproduced the main result on a second
game (§0.4).

### 0.1 Where the time goes today

| Part | Time | Share |
| --- | --- | --- |
| Stockfish searches: 104 calls | 42.1 s | 67% |
| — of which **68 calls repeat a question already answered in the run** (36 distinct) | **27.6 s** | 44% |
| Facts tree, reasoning and rendering (Python) | 13.3 s | 21% |
| The ply cache's write (`PlyCache.put`: `save`, the files) | 7.5 s | 12% |
| **Total** | **63.0 s** (1.9 s a ply) | |

- **Why the repeats.** `analyse_ply` builds `FactEngine(engine=port)` per ply (`pipeline.py`), so
  every ply has a fresh `EngineResultStore`. Round 0 of ply *t* surveys the played positions of its
  window (R0-D §6.1, `controller.py`: from *g* = max(0, *t*−2) on), so each played position is
  surveyed by up to three plies.
- **By round.** Round 0 makes 101 of the 104 calls (41.5 s). The later rounds — the
  re-verification loop — make 3 calls (0.6 s) in the whole game, and their Python (propose, verify,
  render: `_fixpoint`, `explain`) is under 1 s of the profile.
- **The Python.** Building the trees dominates: `status` (`status_v1`: every legal move's SAN and
  check test, on every node) is about 29% of the profiled Python and is recomputed for the same
  positions in every ply's tree; the canonical encoding of `save` is about another 29% (CC-D §4
  already made it faster).

### 0.2 Prototypes

| Change | Total | vs today | Engine calls |
| --- | --- | --- | --- |
| Today | 63.0 s | — | 104 |
| **S**: one result store for the run (§2) | 35.2 s | −44% | 36 |
| **S + A**: the played positions' surveys run ahead on one more engine (§4) | 24.6 s | −61% | 36 |
| **S + P**: POSITION records kept per process (§3), nothing ahead — PF1 | 30.1 s | −52% | 36 |
| **S + A + P** — PF1 and PF2 | **21.4 s** | **−66%** | 36 |
| S + A with two engines ahead | 26.6 s | −58% | 36 |

- PF1 alone (S + P) gives −52%; PF2's prefetch adds 8.7 s of the 63.0 s (S + P → S + A + P). S + P
  was measured after the review of rev. 2 (its N1); its answers equal today's (33/33).
- Two engines ahead were not faster than one on 2 cores in this single run, plausibly because the
  Python and three engines share two cores; the default of one (§4.3) rests on that.
- Under S + A, the 33 searches run ahead were exactly the 33 round-0 surveys: 36 calls in all, none
  repeated, 8 waits for a search still running (1.5 s). No search ahead was irregular. The prototype
  ran a lone game: it did not measure a tool call during a job (§4.4).
- Two engines answering the 33 played positions gave the same lines, scores and PVs as one engine
  (33/33).

### 0.3 The answers are the same

Every ply's claim graph, grade, label and rendered text in the `calliope_result_v1` document is equal
under S, S + A and S + A + P to today's (33/33). The F5 digest of every ply's fact tree is equal too
(33/33, loaded and compared). The tree **files** differ in one place: `ReplayRecord.engine_calls`,
the count of engine calls the replay may make, which F5-D §3 excludes from the digest. So the
`bundle.tree` digest in the document (the sha256 of the file) differs for a ply analysed with store
hits. A tree written under S loads and passes F5's replay checks (33/33, a second process reading
the cache). P changes nothing in the files: S + A + P and S + A wrote the same bytes.

Size: the run's store held 36 searches (33 KB pickled, about 1 KB each). The memo under P held 5,434
records (12,230 hits, 69%), 4.9 MB pickled; dropping the store and the memo after the run freed
23.9 MB of traced memory (`tracemalloc` around the prototype; the script is not in the repository —
PF1 measures the resident size with its own tool, §6).

### 0.4 The review's reproduction (`chesscom_rapid_813_801.pgn`, 55 plies)

Today 139.8 s, 194 engine calls (193 in round 0); S + A + P 49.3 s (−65%), 70 calls = 70 distinct
searches; 55 searches ahead, none irregular, 11 waits (2.9 s); the documents differ only in the 55
`bundle.tree` hashes; the memo held 11,890 records (11 MB pickled).

## 1. Decisions

| # | Decision |
| --- | --- |
| D1 | **One result store per process** (§2): the server's jobs, the agent session's analyses and `tools/explain_game` keep one `EngineResultStore` and give it to every `FactEngine` they build for an analysis. It is bounded by a count, least recently used first. |
| D2 | **POSITION records kept per process** (§3): a `PositionRecords` memo, given to the fact engine like the store, that replaces only a POSITION family's `compute` call; keyed by family name, family version and `PositionKey`, bound to one family registry; bounded by a count of records. |
| D3 | **Every engine search of a store holds a reservation** (§4.1): a searcher that misses the store reserves the question, searches, puts a regular answer and releases; one that finds it reserved waits until its holder releases and asks the store again. A reservation carries its holder's token and moves only by that holder's release; a wait past the adapter's bound on a search (`search_bound_s`) searches without reserving. |
| D4 | **A server game job's uncached plies are surveyed ahead** (§4.2–§4.3): `analyse_game` (server jobs) and `tools/explain_game` survey the played positions of the plies the ply cache does not hold, in order, at most a few plies ahead of the analysis, on a second engine kept by the process, into the process store. Not the agent (§4.4, Q3). |
| D5 | **Nothing else changes** (§5): the profile (`d12_mpv5_v1`, the owner's), the reasoner and its rounds, the families and the build identity, every key, every file format, F5's digests and reproducibility rule, the ply cache and its keys. Existing cached plies stay valid. Amendments are listed in §7. |

## 2. D1 — one result store per process

- **Where it lives.** `server.jobs.Jobs` (one per `tools/serve` process); `agent.session.Session`
  (one per `tools/mcp` process, used by every analysis: `ply`, `judge_move`, the game jobs — not by
  `explore`'s search trees, whose store and its reset stay as AG4 made them); `tools/explain_game`,
  one per run, created in `explain_game()` around its `analyse_ply` loop. `analyse_ply(slot, parsed,
  ply, profile, engine, *, store=None, memo=None)` and `analyse_game(…, store=None, memo=None,
  prefetch=None)` take them; with `None` they make a fresh store per ply and no memo, as today
  (tests). `tools/label_bench` and `tools/calibrate_curve` build their own `FactEngine`s and are
  unaffected.
- **Why it is safe.** A store entry is a regular search keyed by `request_key` — the engine input,
  kind, root moves, MultiPV, profile and the engine's identity including its binary's sha256 (F4-D
  §5.4). One thread, a cleared hash and a depth-bound search give one answer to one key (F4-D M2).
  An irregular search (the time cap) never enters the store (F4-D §5.3, §5.5), so it is never shared.
  The store is already shared between fact engines by design (`FactEngine(store=…)`).
- **An engine restart** (`EngineSlot.restart`, AS-D §5.2) keeps the store: the new process has the
  same identity, so the same keys. Another binary has another identity and other keys.
- **The bound.** `EngineResultStore(max_entries=None)` (unbounded, as today, when not given); with a
  count it evicts the least recently used search past it, and `get` refreshes. The process owners
  pass **20,000** (≈1 KB each pickled). It is an option: `tools/serve --max-store-searches`, the
  agent's `Limits.max_analysis_searches` (`tools/mcp --max-analysis-searches`, AG4-D §3 style; a
  memory limit of AG4-D AM1, at least 1 — the bound cannot be switched off). The agent's
  `max_store_results` (4,000) stays the limit of `explore`'s own store; the new name says which
  store it bounds. An evicted search is asked again when needed. This amends F4-D §5.5 (the store was unbounded).
- **What a hit changes in the records.** Only metadata outside the digest: `SearchRuntime.reused`,
  the delta's run and reuse counts, `ReplayRecord.engine_calls` (F5-D §3 "Excluded"). F5 digests
  and the claim graph are unchanged (§0.3). The tree file's bytes, and so `bundle.tree` in the
  document, can differ from a run without hits, because the bytes now depend on what the process
  had already searched. AS-D §4 ("everything that can change the bundle's bytes is in the key") and
  AS-D §3 (`explain_game` keeps its bundles' bytes) are amended accordingly (§7, Q2). The ply cache
  keeps the first pair it stored (AS-D §4), so the document of a cached ply is unchanged.
- **Budgets.** A hit is free (F4-D §8.3): the agent's search meter (AG4-D §3.1, counted at the port)
  counts fewer calls. The reasoner's sessions set no `max_searches` (`controller.py`: only
  `max_nodes` and the deadline), so the budget pre-check and `BUDGET` skips are unaffected by hits.
  The per-request deadline (`deadline_ms`, 5 s) is reached later or not at all.

## 3. D2 — POSITION records kept per process

- **The hook.** In `_Build._position(family, key)` (`facts/engine.py`), the compute branch stays as
  it is — the required POSITION records are resolved through `_position` and stored in the tree, then
  the record is stored with `_store_record` — and only the call
  `family.compute(FamilyContext(board=…, records=required))` is replaced by
  `memo.compute(family, key, context)`, which returns the kept record or computes and keeps it;
  `context` is a callable that builds `FamilyContext(board=self._key_board(key), records=required)`
  only on a miss, so a hit rebuilds no board (a saving the prototype did not measure). So every
  record, its requirements included, enters the tree at the same revision as today, and the tree, its
  encoding and its F5 digest are unchanged. (This is what the prototype measured: it wrapped
  `compute` only.)
- **Why it is safe.** A POSITION family computes from a board rebuilt from the `PositionKey` alone
  (F2-D §1.5) and may require only POSITION records of the same key (`ALLOWED_REQUIRES`, F2-D §9),
  which are themselves pure in the key; every record type is a frozen dataclass of tuples, so a record
  can be shared between trees.
- **Bound to one registry.** The memo records the families' build identity (the `FamilyEntry` list of
  F5-D §4) of the first fact engine given it; a fact engine with other families is refused
  (`InvalidRequestError`) rather than served records of another build. The key still carries the
  family's name and version.
- **Which families.** Every registered POSITION family (`status`, `material`, `pieces`, `squares`,
  `lines`, `pawns`, `king`, `patterns`, `exchange`). NODE, EDGE and SPAN families are not kept: they
  depend on the history or the edge.
- **The bound.** `PositionRecords(max_entries)` counts **records** (one per family and key) and evicts
  the least recently used past the count. The process owners pass **40,000** (about three 55-ply
  games' worth, §0.4: 11,890 for one). PF1 measured what a filled memo retains (`tracemalloc`, the
  trees dropped): about 7 KB a record (6.96 KB over the five fixture games' played lines, 7.17 KB
  over random games), so rev. 4's 60,000 would hold about 410 MB, past the 300 MB check; 40,000
  holds about 270 MB. An option like the store's: `--max-position-records`, `Limits.max_position_records`
  (at least 1).
  Thread-safe (one lock): the server's job thread and the agent's tool threads may build trees at
  once.
- **Where it lives.** With the store (§2). Loads of the ply cache (`FactEngine()` in `cache.py`, a
  replay of stored records) and `explore` do not use it.

## 4. D3, D4 — reservations, and the played positions surveyed ahead

### 4.1 Reservations (D3)

A reservation says "this key's engine search is running; wait for its answer". It moves from one
holder to the next **only by its release**: nothing expires it, so no waiter ever takes over a key
whose holder is still searching.

- **The store's state.** Under the store's one lock: the stored answers, and per reserved key its
  holder's token (a fresh object per reservation). `reserve(key) -> Token | None` gives a token when
  the key is neither stored nor reserved, else None; `release(key, token)` removes the reservation
  only if `token` is still the key's holder (a late or repeated release does nothing to another
  holder's reservation) and wakes the key's waiters; `put` stores an answer and does not touch the
  reservation; `wait(key, timeout_s) -> bool` blocks until the key is not reserved, True, or the
  timeout passes, False. Every transition is one step under the lock, so of several woken waiters
  exactly one `reserve` succeeds and the others see the key reserved (or stored) again.
- **`Searcher.search`** loops:
  1. the session's own answer (pending or committed), as today;
  2. `store.get(key)`: a hit (`ReuseSource.STORE`);
  3. `reserve(key)`: with a token, search on the port, `put` a regular answer (an irregular answer is
     kept in the session as today), and `release(key, token)` in a `finally` — after the `put`, so a
     waiter woken by the release finds the answer stored;
  4. else the key is reserved: `wait`, then from step 2 again.

  A wait that times out (below) does not reserve: the waiter searches **without** a reservation and
  `put`s a regular answer with `setdefault`, as today. That search is only wasted work: a depth-bound
  search's answer is the same whoever runs it (F4-D M2), and the first `put` is kept.
- **Why every wait ends.** A holder holds a reservation only around one `port.search` of its own and
  never waits in the store while holding one: the prefetch never waits for a reservation (§4.2: a
  reserved key is `reserved`, not waited for; its lookahead gate and stop flag are waited on only
  between searches, holding nothing), and an analysis waits only before it reserves. So there is no cycle
  of waits, and a wait lasts at most the holder's `port.search`. Each port is driven by one thread
  at a time (the job thread, the prefetch thread, or the agent under its `EngineLock`), and an engine
  is started or restarted before a search is reserved, never inside one.
- **The bound of a search.** The shipped adapter's `StockfishEngine.search` returns or raises within
  `READY_TIMEOUT_S` (the `isready` before `go`) + `profile.time_cap_ms` + `STOP_TIMEOUT_S`: **22 s**
  with the default profile; past it the adapter kills the process and raises `EngineError`. The
  adapter exports this as `search_bound_s(profile)`, and the store's wait timeout and the prefetch's
  stop (§4.2) both use it plus 1 s for the release to arrive. The wait timeout is a parameter of
  the `Searcher` (default that bound), so tests can make it short. The timeout is a guard against a port
  without such bounds, not a hand-over: it never fires against the shipped adapter, and when it does,
  the answers stay correct (above).
- **`cached()`** (used by the survey pre-check and `_skip`) never waits and treats a reserved key as
  a miss. That is safe because the reasoner's sessions set no `max_searches` (§2), so no `BUDGET`
  decision reads it; a session with `max_searches` would make its budget decisions depend on timing,
  and none exists among the analyses.
- **The deadline.** The per-request deadline (5 s) is read by the fact engine around the search, as
  today, so a long wait can cut that request's later engine lines (`DEADLINE`). With depth-12
  searches of at most 1.2 s measured (§4.5), a wait is shorter than the search it replaces; the
  acceptance (§6) checks that no `DEADLINE` decision appears that today's run has not.

### 4.2 The prefetch (D4)

- **API (facts).** `FactEngine.prefetch_survey(root: RootSpec, profile, port) -> PrefetchOutcome`
  (`stored` / `reserved` / `ran` / `irregular` / `not_searched`). It builds the engine input by the
  same code path as `survey_stored` (F4-D §13 AM1) and `open`; a position that the fact engine would
  not search — the rule of `EngineWork._searchable`: the node's terminal ends the game, or it is after
  a terminal — is `not_searched`. A stored or reserved key is not searched (`stored` / `reserved`).
  Otherwise it reserves, searches on `port`, puts a regular answer (`ran`) or drops an irregular one
  (`irregular`), and releases. Refused (`InvalidRequestError`) when `port`'s identity is not the fact
  engine's engine identity.
- **Which positions.** `analyse_game` lists at its start the plies of the range whose files the ply
  cache does not hold: `PlyCache.holds(key)`, a new check that the pair's graph file (written last,
  CC-D §3.1) exists, without reading or loading it — so a cached game is not read twice (the loop
  reads each ply once with `get`, as today). The list is a guess for the prefetch only: a ply
  listed as held whose files fail to load is analysed as today, without surveys ahead; a ply
  listed as missing that another job stores meanwhile is found by the loop's `get`, and its surveys
  ahead were only wasted. Let *u*₁ < *u*₂ < … be the listed plies. For each *u*ⱼ, in order, the
  prefetch surveys the positions after the first *k* played moves for *k* = max(0, *u*ⱼ−2) … *u*ⱼ —
  round 0's window (R0-D §6.1) — skipping a position it has already asked in this job. A held ply
  asks nothing ahead.
- **How far ahead.** The prefetch starts on *u*ⱼ's window only once the analysis has started on
  *u*ⱼ₋₃ or a later ply (**L = 3** listed plies; the first three windows at once). A job that ends,
  fails or is cancelled while the analysis is on *u*ᵢ has therefore asked in vain at most the windows
  of *u*ᵢ₊₁ … *u*ᵢ₊₃ — at most **nine positions** when those plies are three or more apart, three when
  they are consecutive (their windows overlap) — plus the one search running at the stop.
- **`explain_game`** has no ply cache: it lists every ply of its range, and its own `analyse_ply`
  loop drives the lookahead gate as `analyse_game`'s does. It takes the ahead slot as a parameter
  (or a function that starts one); with none — tests, callers that pass a bare port — the prefetch
  is off.
- **Who runs it.** A `Prefetch` in `server.pipeline`: one thread per job (started by `analyse_game`,
  by `explain_game()`), driving an `EngineSlot` the **process** keeps (`Jobs.ahead_slot`, the tool's
  own), started on the first job that has two or more uncached plies — so the binary is hashed once
  per process, not per job. The prefetch thread touches only the ahead slot, never the main one
  (`EngineSlot.port` starts an engine lazily and is not thread-safe): `analyse_game` builds the
  prefetch's `FactEngine` in the job thread, with the process store and the main port it already
  holds, so `prefetch_survey`'s identity check reads no slot.
- **Failures.** Any exception in the prefetch thread ends that job's prefetch, is logged, and never
  fails the job; the analysis goes on and searches for itself. An engine failure or an identity
  mismatch (`InvalidRequestError`: say the binary was replaced between the two engines' starts)
  closes the ahead slot from the prefetch thread before it ends; the next job that wants a prefetch
  starts it again, in the job thread, before its prefetch thread runs.
- **Stopping.** `analyse_game` sets the prefetch's stop flag when the plies are done or on any
  exception, and joins its thread; the thread finishes its current search (at most `search_bound_s(profile)`, §4.1), releases its reservation and ends. Its engine is never closed from another thread
  mid-search. At shutdown, `Jobs.stop` returns whether the worker thread ended (today it returns
  nothing and `tools/serve` closes the main slot regardless); `tools/serve` closes `ahead_slot` and
  then the main slot only if it did, and otherwise leaves both to the process's exit — the rule of
  `Session.close` (AG6's review B1). Neither server jobs nor `explain_game` can be cancelled
  mid-game, so a job ends by finishing or failing (and `explain_game` also by an interrupt, which
  sets the stop flag in a `finally`).

### 4.3 How many engines

`prefetch_engines`, default **1**; 0 turns the prefetch off. An option of `tools/serve` and
`tools/explain_game`. One engine ahead is enough to stay ahead of a single analysis (§0.2: 8–11 waits
in a game); more is for hosts with more cores, measured there before it is made a default.

### 4.4 Not the agent, in this packet

AG6-D §10 left "a second engine for the job" out ("on a 2-core host it halves both"), and AG-D AM10
keeps "one engine under a fair lock for every analysis and search". A prefetch engine during an agent
game job would compete with a tool's `ply`, `judge_move` or `explore` for the two cores — slower
tool answers and a higher chance of the time cap, which §0 did not measure. So D4 does not apply to
the agent's game jobs; the agent gets D1–D3 (its job's analyses and its tools share the process store
and memo). Extending D4 to the agent, with the prefetch paused while a tool holds or waits for the
`EngineLock`, is owner question Q3 and would amend AG6-D §10 and AG-D AM10.

### 4.5 What could make it give another answer

- **The time cap under load.** With the Python and two engines on two cores, a search takes longer;
  past `time_cap_ms` (2 s; today's longest on the Opera Game is 1.2 s) it is irregular. An irregular
  search ahead is dropped and the analysis searches itself, as today, so the rule is unchanged; the
  acceptance (§6) requires no irregular search and no `DEADLINE` decision that today's run of the same
  game does not have. This depends on the host: it is checked on this one.
- **A wrong key.** A prefetch whose key differs from the analysis's question is only wasted: the
  acceptance requires engine calls = distinct searches on a full run.

## 5. Considered and left out

- **Rebuilding the re-verification loop.** Rounds after round 0 make 3 of 104 calls (0.6 s) and under
  1 s of Python in the game (§0.1). There is nothing there to gain.
- **An asynchronous engine whose changed results re-run the pipeline.** A depth-bound search with
  one thread and a cleared hash gives one answer (F4-D M2), so a result never changes and there is
  nothing to re-run. The part of the idea that pays — not waiting for the engine — is D3 and D4.
  Showing a shallow result first and a deep one later is a display feature with more total work and
  a second profile (the owner kept d12); not for this packet.
- **Rebuilding Calliope.** The time is in repeated work, not in the structure; the structure's
  determinism is what makes D1–D4 safe.
- **Plies in parallel in several processes.** Python's lock and two cores: workers would compete
  with the engines. Worth measuring on a host with more cores, each worker with its own memo and the
  store shared through `save_store` / `load_store` (F5).
- **A store kept on disk between runs** (`save_store` exists): it pays when a new build misses the
  ply cache but the searches would hit. A later packet.
- **Encoding memoized per record.** With D2 the records of a position are shared objects; their
  canonical bytes could be kept too (≈29% of the Python). Measure after PF1.
- **More threads per search, lower depth or MultiPV.** Not deterministic (F4-D M2), or the owner's
  profile.

## 6. Tests and acceptance

- **Store**: the bound evicts the least recently used and `get` refreshes; `reserve` / `release` /
  `wait`: a second reservation refused; a late or repeated release with an old token leaves the new
  holder's reservation in place; a release with nothing stored lets exactly one of several waiters
  (threads woken together) reserve, the others wait again; a holder's `put` then `release` races a
  waiter, which finds the answer stored and does not search; a wait that times out searches without
  a reservation and its `put` keeps the first answer; two searchers racing for one key make one
  engine call; `cached()` does not wait; an irregular answer is never put. The adapter: a search
  stalled at `isready` raises within `search_bound_s`.
- **Memo**: a tree built with the memo equals (F5 digest and file bytes) one built without it,
  including a position whose POSITION records have requirements; a new family version misses; a
  fact engine with another registry is refused; the bound; two threads building trees.
- **Prefetch**: `prefetch_survey`'s outcomes, the identity refusal, a game-ending position and one
  after it; with the scripted engine, the keys asked ahead equal round 0's survey keys for a game; a
  partly cached game asks nothing for its cached plies; the lookahead bound L; stop on the end and
  on a failure, with the reservation released and the engine not closed mid-search; an engine
  failure, an identity mismatch and another exception in the prefetch thread end the prefetch, are
  logged, close the ahead slot where §4.2 says so, and leave the analysis to search for itself;
  `explain_game` without an ahead slot runs no prefetch; `Jobs.stop`'s result and the shutdown
  order.
- **Searcher with reservations** (a short wait timeout injected): a holder whose `port.search`
  raises releases in its `finally`, and the waiter then reserves and searches; a holder's irregular
  answer is not stored, and the waiter searches for itself.
- **Pipeline**: `analyse_game` with a store, a memo and a prefetch gives every ply the same claim
  graph, rendered text and F5 tree digest as without them (scripted corpus; with Stockfish, the
  corpus below). AS-D test 3 holds.
- **Acceptance with Stockfish** (each implementation packet reports it, one run per configuration
  stated as such): the five games in `tests/agent/fixtures/` and `tests/reasoning/fixtures/`, today
  and with the packet — per game the time, engine calls, distinct searches, irregular searches,
  `DEADLINE` skips (`report.skipped`) and deadline line cuts (`report.deadline_cuts`), the store's and the memo's entries and the process's resident size; every
  ply's claim graph digest, text, grade and label equal to today's; F5 tree digests equal (which a
  skip or a cut that today's run lacks would break); no irregular search, `DEADLINE` skip or
  deadline cut that today's run lacks; engine calls = distinct searches on
  a full run; a second run over a half-cached game asks no survey for its cached plies. PF2 reports
  PF1's configuration (S + P) and its own (S + A + P) on the same games, each from an empty ply cache,
  so the prefetch's own gain is stated. The suite passes.

## 7. Amendments

| To | Amendment |
| --- | --- |
| F4-D §5.5 | The result store may be bounded (`max_entries`, least recently used) and holds reservations with holder tokens, released only by their holder; `Searcher.search` reserves its engine searches and waits for reserved keys, bounded by the adapter's `search_bound_s` (§4.1); `cached()` never waits. |
| F4-D §3 (the adapter) | `search_bound_s(profile)`: the longest `StockfishEngine.search` runs before it returns or raises (§4.1). |
| AS-D §4 | `PlyCache.holds(key)`: the pair's graph file exists, nothing read (§4.2). |
| AS-D §5 / AS1 (`tools/serve`) | `Jobs.stop` returns whether the worker ended; the engines are closed only then, the ahead slot first (§4.2). |
| AG4-D §3.1 | `Limits.max_analysis_searches` (20,000) and `Limits.max_position_records` (40,000), memory limits of at least 1 (AM1) (§2, §3). |
| F4-D §13 (AM1) | `FactEngine.prefetch_survey` beside `survey_stored` (§4.2). |
| F2-D §9 / F1 engine | A POSITION record may come from the process's `PositionRecords` (§3); the tree records it as computed. |
| AS-D §3, §4 | A bundle's bytes (not its F5 digest) may depend on the searches the process already held: `ReplayRecord.engine_calls` (Q2). `explain_game`'s bundles keep their digests, not always their bytes. |
| AS-D §3 | `analyse_ply` / `analyse_game` take `store`, `memo`, `prefetch`; the server and the tool pass the process's. |

## 8. Packets and owner questions

| Packet | Content |
| --- | --- |
| PF1 | D1 and D2: the bounded process store and the POSITION memo, wired into the server, the agent and `explain_game`, with their options; their tests; the acceptance |
| PF2 | D3 and D4: reservations and waits, `prefetch_survey`, `Prefetch` in the pipeline and `explain_game`, the process's ahead slot, `prefetch_engines`; their tests; the acceptance |

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | The prefetch on by default with one engine for server jobs and `explain_game`, or off unless asked? | On, one engine — once PF2's acceptance (§6) passes: the second largest gain, and it asks only what the analysis would ask, at most three plies ahead. If the acceptance fails, PF2 ships it off by default and reports why. |
| Q2 | A ply analysed with store hits writes a tree file whose bytes (not its F5 digest) differ from a run without hits, in `ReplayRecord.engine_calls`. Accept, or make the count not depend on hits? | Accept: metadata the digest excludes; the ply cache keeps the first pair anyway. |
| Q3 | Extend the prefetch to the agent's game jobs, paused while a tool holds or waits for the engine lock (amending AG6-D §10, AG-D AM10)? | Not now: measure tool latency during a job with PF2 on the server first. |

## 9. Review dispositions — rev. 1 (`c192114`), independent review: NOT_READY

The review reproduced §0 on a 55-ply game (§0.4) and found D1 and D2 sound.

| Finding | Disposition |
| --- | --- |
| B1 the prefetch ignores the ply cache and has no lookahead bound; "charged no more" false on partly cached runs | Applied (§4.2): only uncached plies are surveyed ahead, at most L = 3 plies ahead; a stopped job wastes at most three plies' surveys; a half-cached run in tests and acceptance. |
| B2 a second engine for agent jobs reverses AG6-D §10 and AG-D AM10 unstated; tool latency unmeasured | Applied (§4.4): D4 is for server jobs and `explain_game` only; the agent keeps one engine and gets D1–D3; extending it is Q3 with the amendments named. |
| B3 the reservation protocol is incomplete (the analysis does not reserve; release wakes every waiter; `cached()` and budgets) | Applied (§4.1): every engine search reserves; a failed holder hands over to exactly one waiter; `cached()` never waits, safe because the analyses set no `max_searches`. |
| B4 the memo lookup placed before the requirements are stored would change the tree | Applied (§3): the memo replaces only `family.compute(...)`; requirements resolved and stored as today. |
| N1 `explain_game` does not call `analyse_game`; the memo parameter unnamed | Applied (§2, §4.2): signatures given; `explain_game()` creates its store, memo and prefetch. |
| N2 amendments to AS-D §3/§4 unstated; F4-D section numbers; README row | Applied (§7; header; README row). |
| N3 the job meter's infinite limit; `Meter.take` without a lock | Moot for this packet: the agent has no prefetch (§4.4); to be handled with Q3. |
| N4 memo bound to the registry; loads and `explore` excluded; what the bound counts; 20,000 too small | Applied (§3): bound to the families' build identity, records counted, 60,000 by default with a 300 MB check, loads and `explore` excluded. |
| N5 stopping order; a prefetch engine per job hashes the binary each time | Applied (§4.2): stop flag and join, never closed mid-search, shutdown order; one ahead slot per process, started on the first job with two or more uncached plies. |
| N6 the wait bound misstated; host dependence | Applied (§4.1, §4.5). |
| N7 the terminal rule; the input code path | Applied (§4.2): `EngineWork._searchable`'s rule, `survey_stored`'s input path. |
| N8 single runs; "slower" rests on one difference; the 24 MB figure's source | Applied (§0, §0.2, §0.3): single runs stated, wording softened, the figure's source stated. |
| N9 the bounds as options and agent `Limits` | Applied (§2, §3). |

## 10. Review dispositions — rev. 2 (`066f8ec`), independent review: NOT_READY

The review found rev. 1's B1, B2 and B4 resolved, B3 partly; PF1 (D1, D2) ready for implementation,
PF2 not ready; Q2 and Q3 kept, Q1 conditional on PF2's acceptance.

| Finding | Disposition |
| --- | --- |
| B1 a waiter's timeout hands over a reservation whose holder may still be searching; a late release could remove a new holder's reservation | Applied (§4.1): reservations carry a holder token and move only by their holder's release, under the store's lock; a late release with an old token does nothing; a timed-out waiter searches **without** reserving (only wasted work: deterministic answers, first `put` kept); tests for a late release, several waiters woken together and a `put`/release racing a waiter (§6). |
| B2 the 12 s bound omits the `isready` before `go` (`READY_TIMEOUT_S`): `port.search` can take 22 s | Applied (§4.1, §4.2): the bound is the whole `port.search`, `search_bound_s(profile)` = ready + time cap + stop (22 s), exported by the adapter and used by the wait and the prefetch's stop; why every wait ends (no cycle of waits; one thread per port; engines started outside a reservation); the timeout is a guard, not a hand-over. |
| B3 "at most five positions" is false when the uncached plies are apart (10, 20, 30 → nine); *t*−3 should index the uncached plies | Applied (§4.2): the lookahead counts listed plies *u*ⱼ; at most nine positions in vain, three when consecutive. |
| N1 S + P not measured, so PF2's own gain is not separated | Applied (§0.2, §6): S + P measured (30.1 s, −52%, answers equal); PF2's acceptance reports S + P and S + A + P on the same games and cache state. |
| N2 the cache read twice: once to find the uncached plies, once in the loop | Applied (§4.2): `PlyCache.holds(key)` checks the graph file's presence without reading it; the loop reads each ply once as today and remains the final check. |
| Q1 approve the default on only after PF2's acceptance | Applied (§8). |

## 11. Review dispositions — rev. 3 (`4116999`), independent re-review: READY_WITH_CORRECTIONS

The re-review verified rev. 2's B1–B3, N1 and N2 resolved against the code and found no blocking
problem; PF1 implementable as written once N1 and N9 are fixed.

| Finding | Disposition |
| --- | --- |
| N1 `tools/label_bench` and `tools/calibrate_curve` do not call `analyse_ply` | Applied (§2): they build their own fact engines and are unaffected. |
| N2 `explain_game` has no ply cache and may get a bare port | Applied (§4.2): it lists every ply, its loop drives the gate, the ahead slot is a parameter; without one, no prefetch. |
| N3 the shutdown order is not what `tools/serve` does; no cancel exists | Applied (§4.2, §6, §7): `Jobs.stop` returns whether the worker ended, the engines are closed only then, ahead slot first; "cancel" dropped (an interrupt for `explain_game`). |
| N4 the prefetch's failures beyond engine failures | Applied (§4.2): any exception ends the prefetch, logged, never fails the job; an engine failure or identity mismatch closes the ahead slot; it is restarted in the next job's thread. |
| N5 the prefetch thread must not touch the main slot | Applied (§4.2): the prefetch's fact engine is built in the job thread with the port it holds. |
| N6 "the prefetch never waits"; the 1.2 s reference | Applied (§4.1). |
| N7 an injectable wait timeout; Searcher-level tests | Applied (§4.1, §6). |
| N8 name both deadline outcomes | Applied (§6): `report.skipped` and `report.deadline_cuts`; equal F5 digests catch either. |
| N9 `max_store_searches` beside the agent's `max_store_results` | Applied (§2, §7): the agent's option is `max_analysis_searches`; both new limits are AM1 memory limits of at least 1. |
| N10 the board built lazily | Applied (§3): `context` is a callable. |
