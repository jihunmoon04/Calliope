# Application — PF-D design: a game's analysis time: each search asked once, each position's facts computed once, the game's searches run ahead

Status: **rev. 1 — awaiting independent review**. Date: 2026-10-29. Base: `main @ 40f3e54` (LM
merged). Inputs: [`fact-engine-f4-design.md`](fact-engine-f4-design.md) (F4-D: §3 the engine port
and its determinism, §5.3 the result store, §5.5 the searcher), [`fact-engine-f2-design.md`](fact-engine-f2-design.md)
(F2-D §1.5: a POSITION record depends on its `PositionKey` alone), [`fact-engine-f5-design.md`](fact-engine-f5-design.md)
(F5-D §3: what the digest covers and excludes), [`application-server-design.md`](application-server-design.md)
(AS-D: §3 the pipeline, §4 the ply cache), [`application-cache-cost-design.md`](application-cache-cost-design.md)
(CC-D: the previous cost study), [`agent-ag6-design.md`](agent-ag6-design.md) (AG6-D §4: game jobs,
the engine lock), [`agent-ag4-design.md`](agent-ag4-design.md) (AG4-D §3: the budget and the
meter); measurements on this host (§0).

The owner asked how to shorten the tools' running time — an asynchronous engine, parallel work, a
rebuilt re-verification loop, or a rebuilt Calliope (2026-10-29). The measurements answer it: two
thirds of a game's engine time asks questions the same process has already answered, and the
re-verification rounds cost under 3% of the run. Three changes that keep every answer give −66% on
the Opera Game on this host, with no change of structure.

## 0. Measurements (2026-10-29)

Paul Morphy – Duke Karl / Count Isouard, Paris 1858 (33 plies), through `server.pipeline.analyse_game`
into a fresh ply cache, Stockfish 19 `d12_mpv5_v1`, this host (2 cores, aarch64, run alone). Wall
clock; Python shares from a profile (`cProfile`) of the same run.

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
  window (R0-D §6.1: from ply *t*−2 on), so each played position is surveyed by up to three plies.
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
| **S + A + P**: POSITION records kept per process (§3) | **21.4 s** | **−66%** | 36 |
| S + A with two engines ahead | 26.6 s | −58% | 36 |

- Two engines ahead are slower than one on 2 cores: the Python and three engines share two cores.
- Under S + A, the 33 searches run ahead are exactly the 33 round-0 surveys: 36 calls in all, none
  repeated, 8 waits for a search still running (1.5 s). No search ahead was irregular.
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

Memory: the run's store held 36 searches (33 KB pickled, about 1 KB each). The POSITION records kept
under P were 5,434 records of the game's trees (12,230 hits, 69%), about 24 MB in memory with the
store (`tracemalloc`).

## 1. Decisions

| # | Decision |
| --- | --- |
| D1 | **One result store per process** (§2): the server's jobs, the agent session's analyses and `tools/explain_game` keep one `EngineResultStore` and give it to every `FactEngine` they build for an analysis. It is bounded: least recently used searches go past a count. |
| D2 | **POSITION records kept per process** (§3): a `PositionRecords` memo, given to the fact engine like the store, keyed by family name, family version and `PositionKey`; bounded by a count. A record found there is used as if computed. |
| D3 | **A search in flight is waited for** (§4.1): the store can mark a question as being answered; a searcher that misses the store waits for that answer (bounded), and searches itself only if none comes or it is irregular. |
| D4 | **A game job's played positions are surveyed ahead** (§4.2): `analyse_game` and the agent's game jobs start a prefetch over the played positions the job's plies need, in order, on a separate engine (default one), into the process store. The prefetch only puts regular searches the analysis would have asked for. |
| D5 | **Nothing else changes** (§5): the profile (`d12_mpv5_v1`, the owner's), the reasoner and its rounds, the families and the build identity, every key, every file format, F5's digests and reproducibility rule, the ply cache. Existing cached plies stay valid. |

## 2. D1 — one result store per process

- **Where it lives.** `server.jobs.Jobs` (one per `tools/serve` process), `agent.session.Session`
  (one per `tools/mcp` process; used by `ply`, `judge_move`'s analyses and the game jobs — not by
  `explore`'s search trees, whose store and its reset stay as AG4 made them), and one per run of
  `tools/explain_game`. `analyse_ply(…, store=…)` and `analyse_game(…, store=…)` take it; without
  one they make one per call, as today (tests, `tools/label_bench`, `tools/calibrate_curve`).
- **Why it is safe.** A store entry is a regular search keyed by `request_key` — the engine input,
  kind, root moves, MultiPV, profile and the engine's identity including its binary's sha256 (F4-D
  §5.4). One process, one thread, a cleared hash and a depth-bound search give one answer to one
  key (F4-D M2). An irregular search (the time cap) never enters the store (F4-D §5.3), so it is never
  shared. The store is already shared between fact engines by design (`FactEngine(store=…)`).
- **An engine restart** (`EngineSlot.restart`, AS-D §5.2) keeps the store: the new process has the
  same identity, so the same keys. Another binary has another identity and other keys.
- **The bound.** `EngineResultStore(max_entries=…)` evicts the least recently used search past the
  count; `get` refreshes. Default **20,000** searches (≈1 KB each pickled; the implementation measures
  the resident size and states it). An evicted search is asked again when needed. This amends F4-D
  §5.3 (the store was unbounded).
- **What a hit changes in the records.** Only metadata outside the digest: `SearchRuntime.reused`,
  the delta's run and reuse counts, `ReplayRecord.engine_calls` (F5-D §3 "Excluded"). F5 digests
  and the claim graph are unchanged (§0.3). The tree file's bytes, and so `bundle.tree` in the
  document, can differ from a run without hits; the ply cache keeps the first pair it stored (AS-D
  §4), so a document of cached plies is unchanged.
- **Budgets.** A hit is free (F4-D §8.3): `max_searches` and the agent's search meter (AG4-D §3.1,
  counted at the port) count fewer calls; a `BUDGET` skip can only become rarer. The per-request
  deadline (`deadline_ms`, 5 s) is reached later or not at all.

## 3. D2 — POSITION records kept per process

- **The hook.** `_Build._position(family, key)` (`facts/engine.py`) computes a POSITION record once per
  key and tree today. With a memo it looks there after the tree's store and before computing, and
  puts what it computes. The record then enters the tree exactly as a computed one
  (`_store_record`), so the tree, its encoding and its digest are unchanged.
- **Why it is safe.** A POSITION family computes from a board rebuilt from the `PositionKey` alone
  (F2-D §1.5) and requires only POSITION records of the same key (`ALLOWED_REQUIRES`, F2-D §9); every record
  type is a frozen dataclass of tuples (the F5 type registry), so a record can be shared between
  trees. The memo key carries the family's version, so a new version never reads an old record.
- **Which families.** Every registered POSITION family (`status`, `material`, `pieces`, `squares`,
  `lines`, `pawns`, `king`, `patterns`, `exchange`). NODE, EDGE and SPAN families are not kept:
  they depend on the history or the edge.
- **The bound.** `PositionRecords(max_entries=…)` evicts the least recently used key past the count.
  Default **20,000** records (≈4.4 KB each measured, so ≈90 MB at the bound; the implementation
  measures and may lower it). Thread-safe (one lock), since the server's job thread and the agent's
  tool threads may build trees at once.
- **Where it lives.** With the store (§2): one per process, given as `FactEngine(memo=…)`.

## 4. D3, D4 — the played positions surveyed ahead

### 4.1 Waiting for a search in flight

- `EngineResultStore` gains `reserve(key) -> bool` (False if stored or already reserved), `release(key)`
  (always, in a `finally`) and `wait(key, timeout_s) -> EngineSearch | None`.
- `Searcher.search` on a miss: if the key is reserved, it waits; a stored answer is a store hit
  (`ReuseSource.STORE`). On a timeout, or when the reservation ends with nothing stored (an
  irregular answer, a failed engine), it searches itself, as today.
- The wait is bounded by `profile.time_cap_ms` plus the adapter's stop timeout (`STOP_TIMEOUT_S`), so
  never longer than the search the waiter would have run itself.

### 4.2 The prefetch

- **API (facts).** `FactEngine.prefetch_survey(root: RootSpec, profile, port) -> PrefetchOutcome`
  (`stored` / `reserved` / `ran` / `irregular` / `terminal`): the same engine input, kind and key as
  `open` and `survey_stored` (F4-D §4, §13 AM1); refused (`InvalidRequestError`) when `port`'s
  identity is not the fact engine's engine identity. A game-ending position (the fact engine's
  terminal rule) is not searched. A regular answer is put in the store; an irregular one is
  dropped.
- **Which positions.** For a job over plies *a*..*b*: the positions after the first *k* played moves
  for *k* = max(0, *a*−2) … *b*, in order — round 0's window (R0-D §6.1). Positions in the store are
  skipped.
- **Who runs it.** A `Prefetch` in `server.pipeline`: a daemon thread and its own `EngineSlot`(s),
  started by `analyse_game` and the agent's game job (`_job_ply` loop), stopped when the job ends,
  fails or is cancelled (it releases its reservation and closes its engines). An engine failure in
  the prefetch stops the prefetch; the analysis goes on and searches for itself.
- **How many engines.** `prefetch_engines`, default **1**; 0 turns it off. An option of `tools/serve`,
  `tools/mcp` and `tools/explain_game`. On this host 2 are slower than 1 (§0.2).
- **Not for one ply.** The agent's `ply` and `judge_move` do not prefetch: one ply needs at most three
  surveys, and the store (§2) already serves neighbours.
- **The agent's budget.** The prefetch's port is wrapped in the job's meter (`MeteredPort`, AG4-D
  §3.1), so each search ahead is charged like the analysis's own and a refused charge stops the
  prefetch. It asks only round 0's surveys, which the analysis would ask anyway (§0.2: 36 calls
  with and without it), so a job is charged no more than today with D1. The engine lock (AG6-D §4.3)
  still serializes analyses on the session's engine; the prefetch's engine is another process and
  writes only to the store.

### 4.3 What could make it give another answer

- **The time cap under load.** With the Python and two engines on two cores, a search takes longer;
  past `time_cap_ms` (2 s; today's longest on the Opera Game is 1.2 s) it is irregular. An irregular
  search ahead is dropped and the analysis searches itself, as today, so the rule is unchanged; the
  acceptance (§6) requires no more irregular searches and no more `DEADLINE` decisions than today on
  the corpus.
- **A wrong key.** A prefetch whose key differs from the analysis's question is only wasted: the
  acceptance requires engine calls = distinct searches (nothing asked twice, nothing asked in vain).

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
  `wait` (a stored answer, a timeout, a release with nothing stored, a second reservation refused);
  a searcher that finds the key reserved waits and counts a store hit; an irregular answer is never
  put.
- **Memo**: a POSITION record found in the memo gives a tree equal (F5 digest and file bytes) to one
  computed without it; a new family version misses; the bound; two threads building trees.
- **Prefetch**: `prefetch_survey`'s outcomes, the identity refusal, the terminal position; with the
  scripted engine, the keys asked ahead equal round 0's survey keys for a game; cancel and engine
  failure stop it and release its reservation; the agent's meter is charged for each search ahead.
- **Pipeline**: `analyse_game` with a store, a memo and a prefetch gives every ply the same claim
  graph and rendered text, and the same F5 tree digest, as without them (scripted corpus; with
  Stockfish, the corpus below). AS-D test 3 holds.
- **Acceptance with Stockfish** (the implementation reports it): the games in `tests/agent/fixtures/`
  and `tests/reasoning/fixtures/` analysed today and with each packet — per game the time, engine
  calls, distinct searches, irregular searches and `DEADLINE` decisions; every ply's claim graph
  digest, text, grade and label equal; F5 tree digests equal; no more irregular searches or
  `DEADLINE` decisions than today; engine calls = distinct searches. The suite passes.

## 7. Packets

| Packet | Content |
| --- | --- |
| PF1 | D1 and D2: the bounded process store and the POSITION memo, wired into the server, the agent and `explain_game`; their tests; the acceptance above |
| PF2 | D3 and D4: reservations and waits in the store, `prefetch_survey`, `Prefetch` in the pipeline and the agent's game jobs, `prefetch_engines`; their tests; the acceptance above |

## 8. Owner questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | The prefetch on by default with one engine for game jobs, or off unless asked? | On, one engine: it is the second largest gain and asks nothing the analysis would not. |
| Q2 | A ply analysed with store hits writes a tree file whose bytes (not its F5 digest) differ from a run without hits, in `ReplayRecord.engine_calls`. Accept, or make the count not depend on hits? | Accept: it is metadata the digest excludes, and the ply cache keeps the first pair anyway. |
