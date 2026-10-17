# Application — CC-D design: what the ply cache costs, and three ways to pay less

Status: **rev. 2 — independent review of rev. 1 (`1060f94`) CHANGES REQUESTED (C1, C2 major; C3, measurements minor) applied (§9); re-review of rev. 2 READY, implementation checks N1, N2 recorded (§10); owner decided Q1–Q3 as recommended (2026-10-17); merged (PR #108)**. Date: 2026-10-17. Base: `main @ d41cd90` (AG6a
merged). Inputs: [`application-server-design.md`](application-server-design.md) (AS-D: §3 the
pipeline, §4 the ply cache and its promise, §10 test 3), [`reasoning-r4-design.md`](reasoning-r4-design.md)
(R4-D: `claim_graph_v1`, save and load with replay), [`fact-engine-f5-design.md`](fact-engine-f5-design.md)
(F5-D: §2 the canonical encoding, §6 load with replay),
[`agent-ag4-design.md`](agent-ag4-design.md) (AG4-D §3.1: the memory limits),
[`agent-ag6-design.md`](agent-ag6-design.md) (AG6-D: the game path, which reads every ply of a game
again and again); measurements on this host (§0).

The owner asked where a ply's analysis spends its time (2026-10-17). A ply of the Opera Game takes
2.85 s. The engine is under half of it. The largest single part is not analysing at all: it is the
ply cache proving, on every write, that what it stored replays to the same bytes. The same replay
is paid again by every read of a cached ply. AG6-D's game path reads every ply of a game for an
overview, for the board, and again on each refresh, so this cost has to fall before AG6b.

## 0. Measurements (2026-10-17)

Paul Morphy – Duke Karl / Count Isouard, Paris 1858 (33 plies), every ply through
`calliope.agent.Session` (`ply`, the per-ply path of AS-D §3), Stockfish 19 `d12_mpv5_v1`, a fresh
data directory, this host (2 cores, run alone). Times are wall clock, without a profiler; the split
of the Python time is by profile shares.

### 0.1 One ply, today

| Part | 33 plies | Per ply | Share |
| --- | --- | --- | --- |
| Stockfish searches (104) | 41.7 s | 1.26 s | 44% |
| Facts tree, reasoning, render (`analyse_ply` less the engine) | 15.1 s | 0.46 s | 16% |
| The cache's write path (`PlyCache._put`) | 36.3 s | 1.10 s | 39% |
| — `save` (twice) | 10.7 s | | |
| — writing both files | 0.2 s | | |
| — **`load`: the replay of what was just written** | **25.4 s** | **0.77 s** | **27%** |
| Total | 93.5 s | 2.83 s | |

Starting the engine (0.67 s) and the session (0.00 s) are paid once.

### 0.2 Reading cached plies

A second process reading all 33 plies from the cache (no search): **26–27 s**, 0.8 s a ply — each
read is a `load`, which replays the facts tree (`FactEngine.extend`, `add_child`, the canonical
encoding and the digests of every record). `show_game` of the 33 cached plies in one process:
**25.5 s, and 25.4 s again** on a second call: nothing is reused.

### 0.3 Three changes, prototyped

| Change | Analysis of 33 plies | Per ply | Reading 33 cached plies | `show_game` again | Bytes |
| --- | --- | --- | --- | --- | --- |
| Today | 94.1 s | 2.85 s | 27.1 s | 25.4 s | — |
| **W**: write without the replay (§2) | 65.8 s | 1.99 s | 26.2 s | — | same 33/33 |
| **E**: a canonical encoder planned per type (§4) | 85.0 s | 2.57 s | 22.7 s | — | same 33/33 |
| **W + E** | **62.5 s (−34%)** | **1.90 s** | 21.8 s | — | same 33/33 |
| **R**: reuse of loaded pairs (§3), with E | — | — | 20.8 s (first) | **0.1 s** | — |

- "Bytes same" is the tree and graph digest of every ply equal to today's (`bundle.tree`,
  `bundle.graph`); the analysis is deterministic on this game (one thread, depth-bound searches).
- Under W, the full answers of the run that stored each ply equal, field for field, those of a
  second process reading the plies from the cache (33/33; handles made neutral, `cached` and
  `budget_left` left out) — AS-D §4's promise, measured.
- Variant B (keep the replay, drop only the second `save` and the comparison) measured 93.4 s: the
  replay is the cost, not the comparison.
- R's memory: 33 kept pairs grew the resident memory by 120–125 MB. Per pair, measured one load at a
  time: 0.6–9.3 MB, mean 3.8 MB; the pair's files were 52–100 KB, and the ratio of memory to file
  bytes was 0.055 MB per KB on average and 0.118 at most — the file size is a poor predictor (§3.2).

## 1. Decisions

| # | Decision |
| --- | --- |
| C1 | **Write without the replay** (W, §2): the cache saves, writes, reads both files back and compares their bytes with what it wrote, checks the request and build on the analysis it has, and returns that analysis. The replay check moves from every write to the tests (§2.2) and to an option that turns it back on (`--verify-writes`). |
| C2 | **Reuse loaded pairs** (R, §3): the cache keeps the pairs it wrote or loaded in an in-process LRU bounded by a count and by an estimate of their memory, keyed by the key and the digests of both files read under the key's shared lock; a read whose files hash to a kept pair's digests returns it without a replay. |
| C5 | **A pair says how it was checked** (§2.3): `Loaded.checked` is `"written"` (bytes read back equal what was written; the round trip is the tests') or `"replayed"` (loaded from the bytes, as every read and `--verify-writes`). |
| C3 | **A faster canonical encoding with the same bytes** (E, §4): `encode` decides once per type which of F5-D §2's cases applies; its output, every digest and every cache key are unchanged. |
| C4 | **Nothing else changes**: the key, the files, their format and digests, `load` (and its replay, for every read the LRU does not hold), what a miss is, the build digest, the documents. |

## 2. C1 — writing without the replay

### 2.1 The write path

`PlyCache._put(key, analysis, rendered, expected, build)` under the key's exclusive lock (AS-D §4,
AG-D §9), as today up to the files:

1. `tree, graph = save(analysis, rendered)`; write the tree, then the graph (atomic, §5.1).
2. Read both back; **their bytes must equal `tree` and `graph`**.
3. `analysis.round_zero.request` must equal `expected` and `analysis.build` must equal `build`.
4. Return `Loaded(analysis, rendered, bundle(tree, graph))` — the analysis the pipeline made.

Any failure removes both files and raises `StoreFailed`, as today. With `--verify-writes` (server
and agent option; default off), step 2 is followed by today's check — `load` of the read bytes,
`save` of what it loads, equality with `(tree, graph)` — and step 4 returns the loaded pair, as
today.

### 2.2 Where the promise is kept

AS-D §4 promises that the document of the run that first stored a ply and the documents of later
hits on it are equal, because both come from the same loaded files. Under C1 the first comes from
the analysis in memory and the later ones from a replay of its bytes; they are equal when `save` and
`load` are a faithful round trip. That is a property of the code, not of a run, so it is checked
where code is checked:

- **A round-trip test over every stored analysis the suite makes**: the scripted corpus (R4-D §4)
  and, with Stockfish, the corpus games — for each, `save(load(save(x))) == save(x)` and the ply's
  result document from `x` equals the one from `load(save(x))`.
- **AS-D test 3** stays: a second `analyse_game` of the same game answers a document equal to the
  first's, byte for byte (the first from memory now, the second from the files).
- **A first read in another process** still loads and checks request and build (AS-D §4): a pair
  that does not load is a miss, analysed again and replaced, as today.

The remaining risk is a fault that makes `load` give back something `save` did not write, in a
case the tests do not reach. Then a first answer (from memory) and a later one (from the files)
would differ for that ply; the files and their digests would not. `--verify-writes` exists to look
for such a case on a real workload.

### 2.3 What a pair written without the replay is trusted for (review C1)

- **Two levels, recorded on the pair.** `Loaded` gains `checked`: `"written"` for the pair `_put`
  returns without `--verify-writes` — its bytes on disk are proved equal to what was saved, its
  analysis is the one the pipeline made, and that loading those bytes gives the same analysis is a
  property the tests prove, not this run; `"replayed"` for a pair loaded from bytes (every `_get`
  miss of the LRU, and `_put` with `--verify-writes`).
- **What depends on the level: nothing behaves differently.** Every consumer — the pipeline's
  document, the agent's answers and handles, the commentary check — uses a pair the same way; the
  level is for diagnostics and for the record of what a run checked (a job's or a session's log
  counts both).
- **Who is responsible for the round trip**: the storage code (F5-D `save`/`load`, R4-D
  `claim_graph_v1`), through the tests of §6 that run before every merge; and, on a live workload,
  whoever turns on `--verify-writes`.
- **`--verify-writes`**: an option of both servers (`tools/serve`, `tools/mcp`), **off by default**;
  when on, it covers every `_put` of the process: today's replay and byte comparison, the replayed
  pair returned (`checked: "replayed"`), and a failure removes the files and raises `StoreFailed`
  as today.

### 2.4 AS-D test 3's failure case

"A bundle whose re-load fails on first storage (an injected `load` failure) fails the job" has no
re-load to fail without `--verify-writes`. It becomes: with `--verify-writes`, an injected `load`
failure fails the job and removes the files; without it, an injected difference between the bytes
written and the bytes read back does.

## 3. C2 — reusing loaded pairs

- **Where:** in `PlyCache`, so the HTTP server's jobs and the agent's session both use it.
- **What is kept:** `Loaded` pairs — written by `_put` (C1) or loaded by `_get` — keyed by
  `(key, sha256(tree file), sha256(graph file))`, least recently used first.
- **A read** (`get`) takes the key's shared lock (as today), reads both files, hashes **the bytes it
  read** (33 plies: well under a second in all) and looks them up. A kept pair under the same key and
  digests whose request and build equal `expected` and `build` is returned as it is; otherwise the
  read goes on with those same bytes as today (`load`, the checks, a miss) and a sound result is
  kept.

### 3.1 One generation of both files (review C2)

- Calliope's writers take the key's **exclusive** lock for the whole write (`put`, AS-D §4, AG-D
  §9); a reader holds the **shared** lock while it reads both files, so among Calliope's processes a
  read never sees a tree of one write and a graph of another. The digests are of the bytes read under
  that lock, so a kept pair is only ever matched to the generation it was made from.
- A change by anything else (a person, another program) is not under the lock. It changes the
  digests, so the LRU does not answer, and the bytes go through `load` and its checks as today: a
  mismatched pair fails to load or fails the request check and is a miss.
- A removed file is a miss before the LRU is asked (`read_or_none`, as today); its entry ages out.

### 3.2 Memory (review C2)

- **A count and an estimate, both bounds, neither a hard limit.** At most `max_loaded` pairs
  (default 64) and at most `max_loaded_mb` of estimated memory (default 256), the estimate of a pair
  being its two files' bytes × 120 — the largest ratio measured (§0.3: 0.118 MB per KB of files). The
  LRU evicts until both hold. Python gives no cheap measure of an object graph's size, so the bound
  is on the estimate; the results of the packet report the process's resident memory with the LRU
  full, beside the estimate.
- AG4-D's `max_analyses` (128 projected analyses) holds the same analysis objects when they came
  through the cache, so the two bounds share memory rather than add it; the results measure that
  too.
- Both are server options (`--max-loaded`, `--max-loaded-mb`); 0 for either turns reuse off.

### 3.3 Kept pairs are shared, never copied

`Loaded` is a frozen dataclass and stored analyses are read-only (AG-D A6): no consumer changes an
analysis or its rendered text (projections, documents and answers are new objects). A kept pair is
returned to every reader as it is, under the LRU's own lock; a test saves a kept pair after it has
served a document, a session's answers and a commentary check, and finds the bytes it was made from.

### 3.4 Concurrency

The LRU is per process and guarded by its own lock; two processes share files, never pairs (AG-D A8).
Two threads reading one key may both load it; either result is kept, and both are made from the same
bytes.

### 3.5 What it gives AG6-D

After `analyze_game` (whose plies go through `_put`), the overview and the board
read the game without a replay while it fits in `max_loaded`; a refresh of the board costs the
hashing of its files, not 25 s.

## 4. C3 — a canonical encoding planned per type

F5-D §2's `encode` tests every value against six cases in order and calls
`dataclasses.fields` for every record it meets (2.2 million calls in §0's profile). The new
`encode` computes, once per type, which case applies and the record's field names, and keeps that
plan:

| Plan | When (F5-D §2's order) | Output |
| --- | --- | --- |
| `same` | `None`; a `bool`, `str` or `int` that is not an enum | the value |
| `enum` | an enum | `{"e": name, "v": value}`, after the registry check |
| `key` | one of `KEY_TYPES` | `{"k": name, "v": value}` |
| `record` | a dataclass instance | `{"t": name, "f": [fields in order]}`, after the registry check |
| `list` | a tuple or list | the encoded items |
| `error` | anything else | `TypeError`, as today |

The plan is per type and holds no registry; **the registry check stays on every call**, against the
registry given to that call (review C3). The output is the same
object, so `_dumps`, every digest and every key are the same bytes; §0.3 found every bundle of the
game identical.

## 5. Considered and left out

- **A load that trusts the stored digests and skips the replay.** It would cut the remaining
  0.66 s of a cold read, but the replay is how F5-D and R4-D verify a stored tree (ingestion,
  replay, verification); changing that is a storage design of its own.
- **Storing each ply's projected record beside its bundle**, so the board reads JSON. A second
  artifact to keep in step with the bundle; C2 gives the same for a game read twice.
- **Dropping only the second `save`** (variant B): no gain (§0.3).
- **A second engine** (two plies at once on two cores): a scheduling question for AG6b's jobs.

## 6. Tests

- **C1:** the write path returns the pipeline's analysis with `checked: "written"`; files removed and
  `StoreFailed` on a read-back difference, a request or build that differs; with `--verify-writes`,
  today's behaviour, `checked: "replayed"`, and AS-D test 3's injected `load` failure; AS-D test 3's
  byte equality kept.
- **The round trip (§2.2), structural and final** (review C1), over the scripted corpus and, with
  Stockfish, the corpus games: `save(load(save(x))) == save(x)`; the ply's `calliope_result_v1`
  record from `x` equals the one from `load(save(x))`; the agent's full `ply` answer and digest from
  each are equal (handles made neutral); and a commentary accepted against `x` is shown identically
  (`board_form`, the combined document) whether the ply is read from `x` or from `load(save(x))`.
- **C2:** a second read of a pair returns the kept object without calling `load`; a changed file (one
  byte) reloads; a removed file is a miss; a different expected request or build is a miss and is
  not served from the LRU; both bounds evict the least recently used until they hold; either at 0
  keeps nothing; two threads reading the same key may both load it, and neither is ever given a pair
  made from other bytes.
- **One generation** (review C2): a reader while a writer holds the exclusive lock waits and then
  reads the new pair whole (a writer stopped between its tree and its graph); a file replaced by
  another program between two reads changes the digests and goes through `load`; a file removed
  between reads is a miss; a tree of one generation with a graph of another fails to load or to
  match and is a miss.
- **Shared, never copied:** a kept pair saved after serving a document, an agent's answers and a
  commentary check gives the bytes it was made from.
- **C3:** for an instance of every type in the registry (records, enums, keys) and nested lists,
  the new `encode` equals the old one, kept as a test-only reference; a value of no case raises the
  same `TypeError`; an unregistered record or enum raises as before; one type encoded in turn under
  two registries, one that holds it and one that does not, is encoded and refused in turn (the plan
  holds no registry; review C3); the corpus' bundle digests are unchanged (the existing digest pins).
- **Timing** is recorded in the packet's results, not asserted (review, measurements): the §0 game,
  a short tactical game and a long positional one, each **cold** (an empty cache: analysis and
  writes) and **warm** (every ply cached: a first read in a new process, then a second read), with
  the resident memory at the end of each.

## 7. Packet

One implementation packet, **CC1**: `server/cache.py` (C1, C2, the options), `facts/storage.py` (C3),
`tools/serve` and `tools/mcp` (`--verify-writes`, `--max-loaded`), the tests of §6, AS-D §4's
amendment, and §0's game measured again with the packet's code.

## 8. Owner questions

| # | Question | Recommendation | Owner |
| --- | --- | --- | --- |
| Q1 | Move the replay check from every write to the tests, with `--verify-writes` to turn it back on (C1) | Yes: 27% of a ply; the promise measured on 33/33 plies and kept by the round-trip test | Yes (2026-10-17) |
| Q2 | Keep loaded pairs up to 64 and 256 MB of estimated memory per process, both server options (C2) | Yes | Yes (2026-10-17) |
| Q3 | The encoder planned per type, the same bytes (C3) | Yes: no behaviour change | Yes (2026-10-17) |

## 9. Review dispositions — rev. 1 (`1060f94`), independent review: CHANGES REQUESTED

The direction stands (C1–C3 adoptable); two safety conditions before merging, two points for the
implementation.

| # | Finding | Disposition |
| --- | --- | --- |
| C1 (major) | The bytes are checked at write time, the replay only by tests; the corpus cannot cover every state. Distinguish a written pair from a verified one; state `--verify-writes`' default and scope; test both the structural round trip and the final documents | Applied: `Loaded.checked` (`written` / `replayed`, C5) and what depends on it (nothing behaves differently; diagnostics and logs); who answers for the round trip; `--verify-writes` off by default, every `_put` of the process when on (§2.3); tests of the structural round trip and of the final record, the agent's answers and a commentary's display (§6). |
| C2 (major) | A count is not a memory bound; two files read in turn may mix generations; mutability of kept pairs | Applied: a count and an estimated-memory bound (files × 120, the worst measured ratio; 256 MB), with the resident memory reported (§3.2); the read under the key's shared lock with the digests of the bytes read, writers under the exclusive lock, outside edits going through `load` (§3.1); kept pairs frozen and read-only, shared not copied, with a test (§3.3); the tests of reads during a write, a replacement and a removal (§6). |
| C3 (minor) | Keep the type plan and the registry check apart | Applied: the plan holds no registry; the check is per call (§4); a test with two registries in turn (§6). |
| Measurements (minor) | One game; separate cold and warm | Applied for the packet's results: three games, cold and warm, with memory (§6). |

## 10. Review dispositions — rev. 2 (`35d01a1`), re-review: READY

C1, C2, C3 and the measurements passed; no blocking finding. Two checks are handed to CC1, and the
reviewer recommends separate acceptance gates for speed and for the correctness of stored data.

| # | Check | Where |
| --- | --- | --- |
| N1 | `Loaded` is frozen, but not its analysis: the read-only contract of §3.3 must hold in every consumer's code | CC1: the consumers read (document, session, commentary check) and the "shared, never copied" test of §6 |
| N2 | The LRU and AG4-D's `max_analyses` are assumed to share analysis objects | CC1: object identity checked, and the resident memory measured with both full |
| Gates | Speed and stored-data correctness judged apart | CC1's results: the round-trip tests and the byte pins as one gate, the timings of §6 as another |

