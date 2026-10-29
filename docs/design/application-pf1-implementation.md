# Application — packet PF1 implementation: one result store and POSITION records per process

Status: **rev. 2 — independent review of rev. 1 (`0e223e0`) READY_WITH_CORRECTIONS (B1; N1–N5)
applied (§5); re-review READY_FOR_MERGE; the §12 delta (a commentary's staleness by the graph
digest) re-reviewed READY_FOR_MERGE, its N1 applied; merged (PR #132)**. Date: 2026-10-29. Design:
[`application-performance-design.md`](application-performance-design.md) (PF-D) rev. 5: D1 (§2),
D2 (§3), the acceptance (§6), the amendment §12; owner questions Q1–Q3 as recommended (§8). Base:
`design/pf` (PF-D, PR #131), stacked; this record was written after the merge, from the PR's
description (rule 3 of [`docs/README.md`](../README.md): the PR held the record until then).

## 1. Scope delivered

| Place | Change |
| --- | --- |
| `facts/search/store.py` | D1: `EngineResultStore(max_entries=None)` evicts the least recently used search; `get` refreshes it. Unbounded without a bound, as before. A plain dict reordered by pop and reinsert, so two stores with the same searches still compare equal |
| `facts/position_records.py` (new) | D2: `PositionRecords(max_entries)`, bound to the family registry of the first fact engine given it (`bind`, via `storage.family_entries`); `compute(family, key, context)` computes outside the lock and keeps the first record (`setdefault`); `hits`, `misses` |
| `facts/engine.py` | `FactEngine(position_records=…)` passes the memo to the tree's session; in `_Build._position` only `family.compute(...)` is answered from the memo, and the board is built only on a miss. Requirements and records enter the tree as before (PF-D §3) |
| `facts/storage.py` | `family_entries()` factored out of `build_identity` |
| `facts/__init__.py` | `EngineResultStore`, `PositionRecords` exported |
| `server/pipeline.py` | `MAX_STORE_SEARCHES` = 20,000, `MAX_POSITION_RECORDS` = 40,000; `analyse_ply(..., store=None, memo=None)`, `analyse_game(..., store=None, memo=None)` |
| `server/jobs.py` | `Jobs` keeps one store and one memo for every job |
| `tools/serve` | `--max-store-searches` (20,000), `--max-position-records` (40,000) |
| `agent/session.py`, `agent/budget.py` | `Session.analysis_store` and `Session.position_records` serve every `ply`, `judge_move` and game-job analysis; `explore`'s own store is unchanged. `Limits.max_analysis_searches` (20,000) and `Limits.max_position_records` (40,000), AG4-D AM1 memory limits of at least 1, `tools/mcp` options |
| `tools/explain_game` | one store and one memo per run |
| `tools/perf_acceptance` (new) | PF-D §6's acceptance for one game: configurations `today` and `pf1`, `--compare` |
| `server/commentary.py`, `agent/session.py` | PF-D §12: `stale` compares the graph digest only; the agent's `commentary` tool marks a record stale by the current graph file's digest (review N1) |

## 2. Choices and departures

- **The memo answers `compute` only.** Everything around it (which families run, the order their
  records enter the tree, requirements) is today's path, so a tree built with the memo equals one
  built without it, file bytes and F5 digests.
- **The memo's default is 40,000 records, not PF-D rev. 4's 60,000.** Measured with `tracemalloc`
  around a filled memo, the trees dropped: about 7 KB a record, so 40,000 is about 270 MB and 60,000
  would be about 410 MB, past PF-D §3's 300 MB (review B1). PF-D §3 records the measurement
  (`8db76ab`).
- **The tree file's bytes depend on store hits** (`ReplayRecord.engine_calls`, PF-D Q2), its F5
  digest does not. That is why §12 judges a commentary's staleness by the graph.

## 3. Tests

- New:
  - `tests/facts/search/test_store_bound.py`: the bound and LRU order;
  - `tests/facts/test_position_records.py`: a tree with the memo equals one without it (bytes and
    F5 digests), `king`'s requirements, a transposition, a small bound, another family version,
    another registry refused, and a `Barrier(2)` race that keeps the first record (review N4);
  - the pipeline: a whole game with one store and memo gives the same plies and F5 digests, asks
    each search once, and its files load;
  - `Jobs` and the agent session share the store and memo within their limits; option validation;
  - `explain_game`'s plies ask each search once (review N5);
  - `tests/tools/test_perf_acceptance.py` (review N3);
  - §12: a different tree hash leaves a commentary current and a different graph makes it stale,
    for the commentary route and for the agent's `commentary` tool.
- Changed:
  - `tests/agent/golden/full_answers_ms_a.json`: `judge_move_unplayed`'s `bundle.tree` hash and
    `budget_left.searches` (30 → 33). The second analysis's searches already made are free (PF-D
    §2), and its tree bytes differ in `ReplayRecord.engine_calls` (Q2). Nothing else changed.
  - `test_the_engine_closes_only_after_the_worker_ends`: the scripted search takes 4 s instead of
    2 s; with the shared store ply 2 asks fewer searches and no longer outlasted the test's 5 s
    premise.
  - Server job stubs accept the new keyword arguments.
- Full suite with Stockfish: 1825 passed (23.3 min) at `be9006b`, before the §12 delta. The final
  PF1 is contained in PF2's final run (1859 passed at `ea76c40`,
  [`application-pf2-implementation.md`](application-pf2-implementation.md) §3).

## 4. Acceptance (PF-D §6)

Stockfish 19 `d12_mpv5_v1`, this host (2 cores), one run per configuration, empty ply cache; the
tool after the review (`15202e4`).

| Game | Plies | Today | PF1 | Δ | Engine calls (today → PF1) | Distinct | Memo records | Peak RSS (today → PF1) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| opera_game | 33 | 62.0 s | 28.9 s | −53% | 104 → 36 | 36 | 5,434 | 167 → 112 MB |
| hung_queen | 71 | 128.6 s | 72.4 s | −44% | 247 → 90 | 90 | 13,453 | 417 → 234 MB |
| weak_engines_1 | 78 | 199.5 s | 97.3 s | −51% | 260 → 93 | 93 | 16,068 | 520 → 276 MB |
| weak_engines_2 | 67 | 149.9 s | 73.4 s | −51% | 212 → 75 | 75 | 12,661 | 424 → 233 MB |
| chesscom_rapid_813_801 | 55 | 145.8 s | 68.2 s | −53% | 194 → 70 | 70 | 11,890 | 336 → 200 MB |
| **All** | 304 | **685.8 s** | **340.2 s** | **−50%** | 1017 → 364 | | | |

The first run, before the review, gave 669.8 s → 331.1 s with the same counts. PF2's acceptance
(its §4) ran all three configurations again on the same games.

- **Equal answers.** `--compare` gives `equal` on four games: every ply's claim graph digest, text,
  grade and labels, and every tree's F5 digests (`bundle.tree` differs by Q2).
  - **hung_queen:** today's run had one deadline cut (the per-request 5 s deadline, load-dependent)
    at ply 13, so that ply's graph and tree differ; its text is the same. PF1's run had no cut. A
    second run of today had none either and compares `equal` with PF1 (137.5 s, 247 calls). Today's
    two runs differ at that ply, so the difference is today's load-dependent cut (PF-D §4.5), not
    PF1.
- **No new irregular searches or deadline outcomes**: none by F4-D's rule
  (`normalize(...).regular`), no `DEADLINE` skip, no deadline cut, apart from today's cut above.
- **Engine calls = distinct searches** with PF1 on every game.
- **The files replay.** The tool reads every ply back through `PlyCache(max_loaded=0).get`, so every
  tree file is replayed and passes F5's checks (review N1).
- **Memory.** Peak RSS excludes kept pairs and is lower with PF1, because each ply's tree shares its
  POSITION records with the memo. The memo's own size is about 7 KB a record (§2).

## 5. Review dispositions — rev. 1 (`0e223e0`), independent review: READY_WITH_CORRECTIONS

| Finding | Disposition |
| --- | --- |
| B1 the 60,000 memo default exceeds PF-D §3's 300 MB (≈ 7 KB a record, measured) | Applied: 40,000 in `pipeline.MAX_POSITION_RECORDS` and `Limits.max_position_records`; PF-D §3 records the measurement |
| N1 the acceptance read kept pairs, not the files | Applied: `PlyCache(max_loaded=0)`; acceptance rerun |
| N2 irregular counted by the stop reason only | Applied: counted by `normalize(...).regular` |
| N3 `compare` untested, trusts its arguments | Applied: refuses runs that are not today's and the same game; tested |
| N4 the memo's thread test may never race | Applied: a `Barrier(2)` race keeps the first record |
| N5 `explain_game`'s sharing untested | Applied: its plies ask each search once |

Re-review of `15202e4`: **READY_FOR_MERGE**; its note (state today's own non-reproducibility at
ply 13) is applied in §4. Re-review of the §12 delta (`296e2e0`): **READY_FOR_MERGE**; its N1 (the
agent's `commentary` tool by the same rule) applied in `f333685`.
