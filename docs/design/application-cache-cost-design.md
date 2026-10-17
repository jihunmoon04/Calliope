# Application — CC-D design: what the ply cache costs, and three ways to pay less

Status: **rev. 1 — for independent review**. Date: 2026-10-17. Base: `main @ d41cd90` (AG6a
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
- R's memory: 3.6 MB of resident memory per kept pair (33 pairs: 37 → 157 MB).

## 1. Decisions

| # | Decision |
| --- | --- |
| C1 | **Write without the replay** (W, §2): the cache saves, writes, reads both files back and compares their bytes with what it wrote, checks the request and build on the analysis it has, and returns that analysis. The replay check moves from every write to the tests (§2.2) and to an option that turns it back on (`--verify-writes`). |
| C2 | **Reuse loaded pairs** (R, §3): the cache keeps the pairs it wrote or loaded in a bounded in-process LRU, keyed by the key and the digests of both files; a read whose files hash to a kept pair's digests returns it without a replay. |
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

### 2.3 AS-D test 3's failure case

"A bundle whose re-load fails on first storage (an injected `load` failure) fails the job" has no
re-load to fail without `--verify-writes`. It becomes: with `--verify-writes`, an injected `load`
failure fails the job and removes the files; without it, an injected difference between the bytes
written and the bytes read back does.

## 3. C2 — reusing loaded pairs

- **Where:** in `PlyCache`, so the HTTP server's jobs and the agent's session both use it.
- **What is kept:** `Loaded` pairs — written by `_put` (C1) or loaded by `_get` — in an LRU of at
  most `max_loaded` pairs (default 64), keyed by `(key, sha256(tree file), sha256(graph file))`.
- **A read** (`get`) reads both files and hashes them (33 plies: well under a second in all). A kept
  pair under the same key and digests whose request and build equal `expected` and `build` is
  returned as it is; otherwise the read goes on as today (`load`, the checks, a miss) and a sound
  result is kept.
- **Changed or removed files** change the digests, so a kept pair is never returned for bytes it was
  not made from; a removed file is a miss as today.
- **Memory:** 3.6 MB a pair measured; 64 pairs ≈ 230 MB at most. AG4-D's `max_analyses` (128
  projected analyses) holds the same analysis objects when they came through the cache, so the two
  bounds share most of their memory rather than adding it. The bound is a server option
  (`--max-loaded`); 0 turns reuse off.
- **Concurrency:** the LRU is per process and guarded by its own lock; two processes share files,
  never pairs (AG-D A8).

What it gives AG6-D: after `analyze_game` (whose plies go through `_put`), the overview and the board
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

The registry check stays on every call (the registry is an argument). The output is the same
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

- **C1:** the write path returns the pipeline's analysis; files removed and `StoreFailed` on a
  read-back difference, a request or build that differs; with `--verify-writes`, today's behaviour
  and AS-D test 3's injected `load` failure; the round-trip test of §2.2 over the scripted corpus,
  and over the Stockfish corpus when Stockfish is set; AS-D test 3's byte equality kept.
- **C2:** a second read of a pair returns the kept object without calling `load`; a changed file (one
  byte) reloads; a removed file is a miss; a different expected request or build is a miss and is
  not served from the LRU; the LRU never holds more than `max_loaded` and evicts the least recently
  used; `max_loaded` 0 keeps nothing; two threads reading the same key may both load it, and
  neither is ever given a pair made from other bytes.
- **C3:** for an instance of every type in the registry (records, enums, keys) and nested lists,
  the new `encode` equals the old one, kept as a test-only reference; a value of no case raises the
  same `TypeError`; an unregistered record or enum raises as before; the corpus' bundle digests are
  unchanged (the existing digest pins).
- **Timing** is recorded in the packet's results (the §0 game again), not asserted.

## 7. Packet

One implementation packet, **CC1**: `server/cache.py` (C1, C2, the options), `facts/storage.py` (C3),
`tools/serve` and `tools/mcp` (`--verify-writes`, `--max-loaded`), the tests of §6, AS-D §4's
amendment, and §0's game measured again with the packet's code.

## 8. Owner questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Move the replay check from every write to the tests, with `--verify-writes` to turn it back on (C1) | Yes: 27% of a ply; the promise measured on 33/33 plies and kept by the round-trip test |
| Q2 | Keep up to 64 loaded pairs per process (≈ 230 MB), a server option (C2) | Yes |
| Q3 | The encoder planned per type, the same bytes (C3) | Yes: no behaviour change |
