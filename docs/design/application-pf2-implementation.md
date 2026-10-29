# Application — packet PF2 implementation: reservations, and the played positions surveyed ahead

Status: **rev. 3 — independent review of rev. 1 (`e59375f`) READY_WITH_CORRECTIONS (N1–N8)
applied (§5); re-review READY_FOR_MERGE, its N9 applied (`ea76c40`); merged (PR #133)**. Date:
2026-10-29. Design: [`application-performance-design.md`](application-performance-design.md) (PF-D)
rev. 5: D3 (§4.1), D4 (§4.2), engines (§4.3), the acceptance (§6); owner question Q1 (the prefetch
on by default) conditional on the acceptance, which passed (§4). Base: PF1
([`application-pf1-implementation.md`](application-pf1-implementation.md), PR #132), stacked; this
record was written after the merge, from the PR's description.

## 1. Scope delivered

| Place | Change |
| --- | --- |
| `facts/search/store.py` | D3: `reserve(key) -> token \| None`, `release(key, token)` (only the holder's token ends it; a late release does nothing), `wait(key, timeout_s) -> bool`, `reserved(key)`; every transition under the store's one lock (a `Condition`); `waits` and `wait_seconds` counted. `PrefetchOutcome` (`stored` / `reserved` / `ran` / `irregular` / `not_searched`) |
| `facts/search/store.py` (`Searcher`) | `search`: the session's answer; then the store; then reserve, search, `put`, release in `finally` after the `put`; else wait and ask again. A wait past `wait_s` (default the adapter's bound + 1 s, injectable) searches without a reservation, which only wastes work, since the first `put` is kept. `search_ahead` never waits. `cached()` treats a reserved key as a miss |
| `facts/search/uci.py` | `search_bound_s(profile)` = `READY_TIMEOUT_S` + time cap + `STOP_TIMEOUT_S` = 22 s; exported |
| `facts/engine.py` | `FactEngine.prefetch_survey(root, profile, port) -> PrefetchOutcome`: the input `survey_stored` and `open` build (a shared `_root_input`); no search for a position that ends the game by rule or follows one that did (`open`'s rule); `InvalidRequestError` for a port of another identity |
| `server/cache.py` | `PlyCache.holds(key)`: the graph file exists; nothing is read |
| `server/pipeline.py` | D4: `LOOKAHEAD` = 3; `Prefetch(ahead_slot)`, one run per job. `analyse_game(..., prefetch=)` lists the plies the cache does not hold and starts a run only for two or more; the run's `FactEngine` is built in the job thread, so the prefetch thread never touches the main slot; the loop calls `reach(ply)` each ply and `stop()` in `finally`. The run surveys each listed ply's round-0 window (k = u−2 … u), at most three listed plies ahead, never a position twice, checking the stop flag between searches. Any exception is logged and ends only the prefetch; an `EngineError` or an identity mismatch closes the ahead slot, which the next job starts again |
| `server/jobs.py` | `Jobs(..., ahead_slot=)` keeps `jobs.prefetch`; `Jobs.stop` returns whether the worker ended |
| `tools/serve` | `--prefetch-engines {0,1}` (default 1); `close_engines`: at shutdown the ahead engine, then the main one, are closed only if the worker ended, else both are left to the process's exit |
| `tools/explain_game` | `explain_game(..., prefetch=)` (a `Prefetch` over the second engine's slot); `--prefetch-engines {0,1}` (default 1); every ply of the range listed, its own loop drives the gate; an interrupt stops the run in `finally`; engines closed ahead first |
| `tools/perf_acceptance` | the `pf2` configuration, `--half` (the first half of the game cached first), the prefetch's outcomes and waits, `windows_of_cached_plies`, `--searches PF1 PF2` |

## 2. Choices and departures

- **`--prefetch-engines` accepts 0 or 1.** PF-D §4.3 leaves more than one ahead engine to a host
  with more cores, measured there before it is made a default; no pool is implemented.
- **`explain_game` takes a `Prefetch`, not the ahead slot** (departure from PF-D §4.2's wording,
  re-review N9): its caller closes the `Prefetch`, which skips the close while a stuck run lives,
  so no engine is closed mid-search.
- **A run that outlives `stop()`'s bounded join** (`search_bound_s` + 1 s) is logged and keeps the
  prefetch off until its thread ends, so two threads never use one engine (review N1).
- **The agent has no prefetch** (PF-D §4.4, Q3 as recommended).

## 3. Tests

- `tests/facts/search/test_reservations.py` (10): the bound; tokens and a late release; a wait that
  times out leaves the holder's key reserved; of four waiters woken together exactly one reserves;
  two searchers racing make one call and the waiter finds the answer stored; a failing holder
  releases and the waiter searches; an irregular answer is not stored and the waiter searches; a
  wait past its bound searches unreserved and the holder's first `put` is kept; `cached()` does not
  wait; `search_ahead`'s outcomes. The waiter tests poll `Condition._waiters` (a private CPython
  attribute, named in a comment) instead of sleeping.
- `tests/facts/search/test_prefetch_survey.py` (5): the survey ahead is the one `open` asks
  (`ReuseSource.STORE`, no main call); checkmate, stalemate and a position after an
  insufficient-material position are `not_searched`, as the fact engine also does not survey them;
  a reserved key is not waited for; an irregular answer is dropped; another identity is refused.
- `tests/server/test_prefetch.py` (15): answers and F5 digests equal with and without the prefetch, and
  no search asked twice across the two engines; the keys asked ahead a subset of the analysis's; a
  partly cached game asks windows only for its uncached plies; one uncached ply starts no engine;
  the lookahead bound and the gate; stopping at the gate releases everything; a failing analysis
  stops the run without closing its engine; a failing or foreign ahead engine is closed and the
  analysis unchanged; another exception logged, engine kept; a stuck run; `explain_game` with and
  without an ahead slot; `Jobs` passes the prefetch, `stop`'s result, and `tools/serve`'s shutdown
  order (`close_engines`).
- Full suite with Stockfish: **1859 passed** (23.5 min) at `ea76c40`, the tree merged as `main @
  3431cfd`.

## 4. Acceptance (PF-D §6)

Stockfish 19 `d12_mpv5_v1`, this host (2 cores), one run per configuration. Each configuration
starts from an empty ply cache, except **half-cached**: the first half of the game is cached first
(untimed, today's path), then the whole game runs with PF2 in a fresh store.

| Game | Plies | Today | PF1 (S + P) | PF2 (S + A + P) | PF2 vs today | PF2 vs PF1 | Half-cached |
| --- | --- | --- | --- | --- | --- | --- | --- |
| opera_game | 33 | 62.5 s | 29.0 s | 20.4 s | −67% | −30% | 19.3 s |
| hung_queen | 71 | 126.5 s | 66.8 s | 51.6 s | −59% | −23% | 52.2 s |
| weak_engines_1 | 78 | 200.2 s | 98.2 s | 64.7 s | −68% | −34% | 66.9 s |
| weak_engines_2 | 67 | 150.5 s | 74.3 s | 49.0 s | −67% | −34% | 53.9 s |
| chesscom_rapid_813_801 | 55 | 138.4 s | 67.1 s | 47.4 s | −66% | −29% | 45.0 s |
| **All** | 304 | **678.1 s** | **335.4 s** | **233.1 s** | **−66%** | **−30%** | |

- **Equal answers.** `--compare` against today gives `equal` for PF1, PF2 and half-cached on all
  five games: every ply's claim graph, text, grade, labels and F5 digests.
- **No new irregular searches or deadline outcomes**: no configuration has an irregular search, a
  `DEADLINE` skip or a deadline cut; this run's today had none either.
- **Engine calls = distinct searches** for PF2, both engines together: 36, 90, 93, 75 and 70, the
  same as PF1.
  - The prefetch's outcomes are `ran` for each played position (33/72/79/68/55) and
    `not_searched` for a final checkmate (opera_game, chesscom_rapid_813_801).
  - The analysis waited for a reserved search 13/7/5/3/11 times, 3.3/1.4/1.1/1.1/3.1 s in all.
- **The prefetch asks nothing the analysis would not.** `--searches PF1 PF2` compares distinct
  searches, both engines together, with PF1's on the same game and cache state: `equal` on all five
  games, full and half-cached (review N4).
- **Half-cached runs** (16–39 plies cached; 20–47 engine calls, all distinct): PF2
  19.3/52.2/66.9/53.9/45.0 s against PF1's 23.9/56.2/81.5/66.8/55.6 s. They are close to the full
  runs because the tool's cache keeps no loaded pairs (`max_loaded=0`), so every cached ply is
  replayed from its files within the timed run.
- **Peak RSS** (the Python process, `RUSAGE_SELF`) is the same as PF1's; the prefetch keeps nothing.
  Each Stockfish process, the second included, adds its own memory (Hash 16 MB plus the binary),
  not counted.
- **Q1.** The acceptance passed, so the prefetch is on by default (one engine) for server jobs and
  `explain_game`.

## 5. Review dispositions — rev. 1 (`e59375f`), independent review: READY_WITH_CORRECTIONS

| Finding | Disposition |
| --- | --- |
| N1 `stop()` joins without a bound | Applied: joins for `search_bound_s + 1`; a run that outlives it is logged and keeps the prefetch off until its thread ends. Tested with a port without a bound |
| N2 `windows` / `counts` grow for the process's life | Applied: per run, reset in `start` |
| N3 a reservation could leak on an asynchronous interrupt | Applied: the reservation is taken inside the `try` that releases it (`search`, `search_ahead`) |
| N4 `windows_of_cached_plies == []` close to vacuous | Applied: `--searches PF1 PF2`; `pf1 --half` baselines; `equal` on all five games, full and half |
| N5 RSS excludes the second engine; the half-cached times read oddly | Applied: both stated in §4 |
| N6 an assertion that cannot fail; sleep-based tests | Applied: `active_count` removed; the failing-analysis test asserts released reservations; tests poll for the waiter inside `wait` and for completed surveys |
| N7 coverage gaps | Applied: another exception (logged, engine kept); `Jobs.stop` False with a stuck worker; `tools/serve`'s shutdown factored into `close_engines` and tested; `caplog` assertions |
| N8 a second interrupt in `explain_game` | Applied: `run.stop()` catches a `KeyboardInterrupt`, joins the thread and re-raises. An interrupt inside `Prefetch.start` after the thread starts is left: the process is exiting |

Re-review of `a58636c`: **READY_FOR_MERGE**. Its follow-ups, applied in `ea76c40`: N9
(`Prefetch.close()` logs and skips while a stuck run lives, so neither `tools/serve` nor
`explain_game` closes an engine mid-search; hence §2's departure); a comment naming the test's
`Condition._waiters` dependency; the stuck-run test joins its second run.
