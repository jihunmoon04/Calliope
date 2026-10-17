# Application — packet CC1 implementation: what the ply cache checks and keeps

Status: **rev. 1 — for independent review**. Date: 2026-10-17. Design:
[`application-cache-cost-design.md`](application-cache-cost-design.md) rev. 2 (CC-D: C1–C5, §2–§4,
§6; implementation checks N1, N2 and the two gates, §10), owner decisions Q1–Q3 (2026-10-17). Base:
`main @ 52ae13e` (CC-D merged, PR #108).

## 1. Scope delivered

| Place | Change |
| --- | --- |
| `server/cache.py` | C1: `_put` saves, writes, reads both files back and compares the bytes, checks the request and build, and returns the pipeline's analysis (`checked: "written"`); with `verify_writes`, today's replay and second save (`checked: "replayed"`). C2: an LRU of `Loaded` pairs keyed by `(key, tree digest, graph digest)` of the bytes read under the key's lock, bounded by `max_loaded` (64) and `max_loaded_mb` (256, the estimate files × `BYTES_PER_FILE_BYTE` 60, §2), under its own lock; `_get` returns a kept pair whose request and build match, else loads as before and keeps it; `_put` keeps what it wrote. C5: `Loaded.checked`. `counts` (`written`, `replayed`, `reused`) and `kept()` for diagnostics |
| `facts/storage.py` | C3: `encode` with a plan per type (`_PLANS`, `_plan`): F5-D §2's cases decided once per type, the record's field names kept; the registry checked on every call |
| `server/pipeline.py` | the failure message: "the stored analysis of ply N failed its check: …" |
| `server/jobs.py`, `agent/session.py` | the cache options (`verify_writes`, `max_loaded`, `max_loaded_mb`); the session logs the cache's counts when it closes |
| `tools/serve`, `tools/mcp` | `--verify-writes`, `--max-loaded`, `--max-loaded-mb` (refused below 0); `tools/serve` logs the counts when it stops |
| `server/__init__.py` | `MAX_LOADED`, `MAX_LOADED_MB` |
| `tests/server/test_cache_cost.py` (new) | C1, C5, C2, one generation (§3 below) |
| `tests/agent/test_cache_shared.py` (new) | shared, never copied; N1, N2 |
| `tests/results/test_round_trip.py` (new) | the round trip, structural and final, over the corpus, scripted and with Stockfish |
| `tests/results/test_encode_plan.py` (new) | C3 against the encoder as it was |
| `tests/server/test_pipeline.py` | AS-D test 3 as CC-D §2.4 keeps it; the second run of the byte-equality test reads the files through a new cache |
| `docs/design/application-server-design.md` | amendment §16 |

Not changed: the key, the file format and digests, `load`, what a miss is, the documents,
`tools/explain_game` (it still re-loads what it writes, AS-D §15).

## 2. Choices and departures (for the reviewer)

- **The LRU is per `PlyCache` instance**, and each process has one (the session's, the jobs'). A
  test or a tool that makes a new `PlyCache` on the same directory reads the files again — which is
  what AS-D test 3's second run now does on purpose.
- **A kept pair that does not match the asked request or build is not served, and the bytes are then
  loaded** (as before): the LRU never answers a request it was not made for, and a miss stays a miss
  by §4's rule.
- **A pair whose estimate alone passes `max_loaded_mb` is not kept** (it is still returned).
- **The estimate factor is 60 bytes of memory per byte of files, not CC-D §3.2's 120** (owner,
  2026-10-17; CC-D §11). With 120 — the largest ratio measured — the 256 MB bound kept 31 of the
  Opera Game's 33 pairs, and a second read in ply order then reused none: each pair was evicted just
  before it was asked for again (§4.2). 60 is about the mean ratio measured (0.055 MB per KB); the
  same read then reused all 33 and the process held 162 MB. The resident memory is reported beside
  the estimate (§4.2).
- **Diagnostics are counts, not log lines per write**: `PlyCache.counts` and `kept()`, logged when a
  session closes and when `tools/serve` stops.
- **The failure message** of the pipeline no longer says "did not re-load" (there is no re-load
  without `--verify-writes`); the test matches the new text.
- **The encoder's plan** keeps, per type, the case and a record's field names; enum subclasses of
  `int` and `str` are planned as enums, as the old order decided (tested).

## 3. Test obligations (CC-D §6, §10)

| Obligation | Where |
| --- | --- |
| C1: the write returns the pipeline's analysis, `written`, no `load`; the bytes on disk are its `save` | `test_cache_cost.py::test_a_write_returns_the_pipelines_analysis_as_written` |
| C1: `verify_writes` replays, `replayed`, same bytes | `::test_with_verify_writes_the_written_bytes_are_replayed` |
| C1: a read-back difference, a request or a build that differs: `StoreFailed`, both files removed, nothing kept | `::test_a_failed_check_removes_both_files` |
| AS-D test 3: an injected `load` failure fails the job with `verify_writes`; bytes read back otherwise fail it without | `test_pipeline.py::test_3_with_verify_writes_…`, `::test_3_files_read_back_otherwise_fail_the_job` |
| AS-D test 3: a second run gives the same bytes, read from the files | `test_pipeline.py::test_3_a_second_run_searches_nothing_and_gives_the_same_bytes` |
| The round trip, structural and final (record, rendered text), every corpus case, scripted and with Stockfish | `test_round_trip.py` |
| C2: a second read reuses without `load`; another process replays once then reuses | `test_cache_cost.py::test_a_second_read_reuses_the_pair_without_a_replay` |
| C2: another build or request is not served from the LRU; a changed byte replays; a removed file is a miss before the LRU | `::test_changed_removed_or_foreign_files_never_reuse_a_pair` |
| C2: both bounds evict the least recently used; 0 keeps nothing; below 0 refused | `::test_the_kept_pairs_hold_both_bounds` |
| C2: threads never get a pair of other bytes | `::test_two_threads_never_get_a_pair_of_other_bytes` |
| One generation: a reader waits for a writer's lock and reads the pair whole; a mixed pair is a miss | `::test_a_reader_waits_for_a_writer_and_never_mixes_two_writes` |
| Files replaced outside the lock go through `load` | `::test_files_replaced_outside_the_lock_go_through_load` |
| Shared, never copied (N1): after a digest, a full answer, a commentary check and `show_game`, the kept pair saves to its files' bytes | `test_cache_shared.py::test_a_kept_pair_is_unchanged_by_its_readers` |
| N2: the session's projected analyses hold the same object as the LRU | same test |
| C3: every stored analysis (synthetic game, corpus) saves to the same bytes under both encoders | `test_encode_plan.py::test_every_stored_analysis_saves_to_the_same_bytes` |
| C3: each case, enum subclasses of `int` and `str`, nested records; refusals with the same messages; the registry on every call (two registries in turn) | `::test_the_cases_give_the_same_output`, `::test_what_is_not_encodable_is_refused_as_before`, `::test_the_registry_is_checked_on_every_call` |

## 4. Results

### 4.1 Gate 1 — the stored data (correctness): passed

- The whole suite with Stockfish 19 (`CALLIOPE_STOCKFISH_PATH` set) on `70dcd8b`: **1532 passed**
  (18.8 min; 21.0 at AG6a), none failed or skipped — 64 new, the round trip over the 18 corpus
  cases under Stockfish among them. After the factor change (§2) the cache and shared-pair tests
  again: 12 passed.
- `ruff check` and `ruff format --check` on `src`, `tests`, `tools`: clean.
- The three measured games (§4.2): **every ply's tree and graph digests are equal under `main` and
  CC1** (a digest of all bundle digests per game: Réti `402ad9b5…`, Opera `ce8c00d5…`, QGD
  `45258887…`, the same in every run of either code, cold or warm).

### 4.2 Gate 2 — speed and memory

Three games on this host (2 cores, run alone), Stockfish 19 `d12_mpv5_v1`, through
`calliope.agent.Session` (`ply`, `view: "full"`, every ply in order): Réti – Tartakower, Vienna 1910
(21 plies, a short tactical game); the Opera Game (33 plies, CC-D §0); a long game — **not a human
game**: Stockfish 19 at depth 10 playing both sides from a Queen's Gambit Declined (12 book plies)
to 120 plies, generated for this measurement, the repository having no long game. **Cold**: an
empty data directory, every ply analysed and written. **Warm**: a new process reading every ply,
twice. `max_analyses` was raised to 1000 for the runs, so the session's projected analyses held
every ply. RSS: the process's resident memory at the end.

| Game | Cold `main` | Cold CC1 | Warm 1st read `main` → CC1 | Warm 2nd read `main` → CC1 (factor 120) → CC1 (factor 60) | RSS warm `main` / CC1 (60) |
| --- | --- | --- | --- | --- | --- |
| Réti, 21 | 49.4 s | **32.7 s (−34%)** | 12.9 → 10.9 s | 14.3 → 0.2 → **0.2 s** | 112 / 101 MB |
| Opera, 33 | 92.9 s | **62.1 s (−33%)** | 25.1 → 21.1 s | 26.8 → 21.8 → **0.3 s** | 178 / 162 MB |
| QGD self-play, 120 | 390.8 s | **221.5 s (−43%)** | 134.1 → 109.7 s | 141.6 → 117.1 → **117.0 s** | 765 / 763 MB |

- **Cold: −33 to −43%** (C1 and C3). The long game gains most: its plies have larger trees, so the
  replay CC1 removes weighed more.
- **First read: −15 to −19%** (C3: the replay remains, with a faster encoding).
- **Second read**: what fits the bounds is reused (Réti 21 pairs, Opera 33 at factor 60); the long
  game's 120 plies pass `max_loaded` (64), and a read in ply order evicts each pair before it is asked
  for again, so nothing is reused. AG6-D's game path will not read a long game whole again for its
  overview: AG6b is to keep a small per-ply summary when it analyses (§5).
- **N2 (shared objects)**: warm with the LRU off (`max_loaded` 0) held the same memory as with it on —
  Opera 177 / 177 MB, QGD 763 / 763 MB at factor 120 — and the shared-pair test finds the session's
  analysis and the kept one the same object. In the agent's process the LRU adds little beside the
  session's projected analyses; the HTTP server, which has none, carries the LRU's own.
- **Memory to note (AG4-D, unchanged here):** 120 projected analyses held 763 MB, about 6 MB each,
  so the default `max_analyses` of 128 can hold about 0.8 GB in one process.

## 5. For AG6b

- A full read of a game longer than `max_loaded` replays every ply (about 0.9 s each). AG6b's overview
  and board should read per-ply summaries kept by `analyze_game`, not every analysis.
- Raising `max_loaded` for the HTTP server, or a cheaper cold load (CC-D §5), remain open.
