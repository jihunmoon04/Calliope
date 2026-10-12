# Application — packet AS1 implementation: `calliope.server`, `tools/serve`

Status: **rev. 3 — review NOT_READY applied (§6); re-review NOT_READY applied (§7); awaiting re-review**.
Date: 2026-10-12. Design: [`application-server-design.md`](application-server-design.md) rev. 3
(AS-D, final re-review READY, #82). Base: `design/application-server @ 531ba16`.

## 1. Scope delivered

| Module | Content |
| --- | --- |
| `server/__init__.py` (new package) | the public names of the pipeline and the cache |
| `server/pipeline.py` | `parse_game`, `grading_for`, `game_input`, `plies_range`, `ply_request`, `normalized_ply`, `analyse_game`, `EngineSlot`, the engine-failure rules (`is_engine_failure`, `refused_by_engine_failure`), `InputError`, `JobFailed` (AS-D §3, §5.2) |
| `server/cache.py` | `PlyCache`: the `ply_key_v1` key, `get` (misses: a missing file, `StoredTreeError`, `StoredGraphError`, another request or build), `put` (write, read back, re-load, save again to the same bytes) (AS-D §3, §4) |
| `server/files.py` | `atomic_write` (`.tmp`, `fsync`, rename), `remove_temporaries`, `read_or_none` (AS-D §5.1) |
| `server/jobs.py` | `Jobs`: `job_key_v1` ids, the environment, `job.json` / `result.json` / `error.json`, recovery, the damaged-file rules, one lock, the worker thread, progress and estimates, `QueueFull` (AS-D §5) |
| `server/web.py` | `Server` (`ThreadingHTTPServer`), the routes and status codes of AS-D §6 |
| `tools/serve/` (new) | `python -m tools.serve [--host] [--port] [--data] [--viewer]` (AS-D §8) |
| `tools/explain_game/__main__.py` | the intake, grading and requests from the pipeline (AS-D S3); options, output and bundle bytes unchanged |
| `reasoning/grading.py`, `reasoning/__init__.py` | public `time_class`, `chesscom_time_class` (AS-D S10) |
| `tools/calibrate_curve/{pgn,acceptance}.py`, `tools/label_bench` | import the moved functions; no copy left |
| `tests/test_package_boundaries.py` | `server` in `NEW_PACKAGES`; nothing below imports it; it imports only `calliope.facts`, `calliope.reasoning`, `calliope.reasoning.storage` and `calliope.results` |
| `tests/server/` (new) | AS-D §10 tests 1–8, 6a, 7a, 10–12 |

The viewer's analyse panel and test 9 are AS2.

## 2. Implementation decisions and deviations
1. **The tool and the server share the per-ply path** (rev. 2, review D1; AS-D §15). The tool
   calls `parse_game`, `analyse_ply` (analysis, rendering, the engine-failure rule, the engine
   binding) and `document`. Only storage differs: the server's ply cache, the tool's three
   bundle modes. `explain_game` takes an engine port or an `EngineSlot`; `main` passes a slot
   that can restart Stockfish. Its requests are the same as before, so its text and bundle bytes
   are unchanged (test 1 compares the pipeline's digests with the tool's).
2. **One change in the tool's intake.** `parse_game` refuses a PGN that python-chess could not
   read (`game.errors`, for example an illegal move) with `InputError`, a `ValueError`. Before,
   the tool analysed the moves before the error. A PGN that is read without error is treated as
   before.
3. **`calliope.reasoning.storage`.** The server imports R4's `save` and `load` from there, as the
   tool does; they are not re-exported by `calliope.reasoning`. The boundary test names this
   module explicitly.
4. **The environment is computed at start-up.** `Jobs(...)` starts the engine (a missing or
   unsupported binary stops `tools/serve` with status 2) and records
   `{engine fingerprint, profile fingerprint, build digest}`. Every job id and every resume uses it.
5. **The build digest** is `build_digest(Reasoner(FactEngine(engine=port)).build())`. The
   build does not depend on the engine port, so computing it once is enough.
6. **Engine failures.** `analyse_ply` runs a ply at most twice. Before each attempt it checks
   that the slot's engine still has the job's engine fingerprint (rev. 2, review B1: the job's,
   from `job.json`, never the current engine's). A round-0 `AnalysisFailed` whose cause is an
   engine failure, or a recorded `REFUSED(EngineError)`, restarts the engine. Any other
   `AnalysisFailed` fails the job at once.
7. **Re-posting a failed job** removes `error.json` and queues it again. When its `job.json` was
   damaged, or the text differs (the same game, other whitespace), `job.json` is written again.
8. **Status.** `current` is the ply being analysed and its SAN. `eta_seconds` is the mean time of
   the plies analysed so far (cache hits excluded) times the plies left. `cached` counts hits.
9. **HTTP details.**
   - A missing `Content-Length` is 411, a negative one 400 (rev. 2, review note).
   - A method other than GET or POST is answered 501 by `http.server` itself, with no CORS
     header.
   - The viewer page is read from disk on every request, so editing it needs no restart.
   - The log line is `http.server`'s request line and code, never a body.
10. **Engine-failure test for later rounds.** The synthetic engine's later rounds reuse round 0's
    searches: on plies 1–10 of the test game they make no new search. So that test injects a
    `REFUSED(EngineError)` outcome into the first analysis. The round-0 tests use a real
    failing engine port.

11. **A job runs only in its own environment** (rev. 2, review B1). Before a job starts, the
    worker computes the environment now (engine fingerprint, profile, build). If it differs from
    the server's, the server's environment follows it, so a new POST gets an id that names the
    new engine. A job whose `job.json` environment differs fails with the environment message.
    `analyse_game` receives the job's engine fingerprint. After any failed job the slot's engine
    is closed, so the next job starts a fresh one.
12. **Recovery re-derives the id** (rev. 2, review B2). `job_id` is recomputed from the stored
    PGN, ply range and environment; a mismatch with the directory's name, or an environment
    without its fields, isolates the job as damaged.
13. **A result is checked before it counts as done** (rev. 2, review B3). `result_matches`
    reads `result.json` and requires the schema name, the build digest, the engine name and
    binary, the profile, the start FEN, the moves, the headers, the ply list and every
    `bundle.stored`. A result that fails is not served; the job is resumed and the file
    replaced. No new runtime dependency.
14. **The shipped schema, checked without `jsonschema`** (rev. 3, re-review B3).
    `calliope.results.schema_errors(document)` validates against
    `results/schema/calliope_result_v1.json` itself, implementing exactly the 20 keywords that
    schema uses (2020-12 semantics: `type`, `required`, `properties`, `additionalProperties`,
    `items`, `const`, `enum`, `$ref`, `minLength`, `minimum`, `minItems`, `maxItems`, `pattern`,
    `allOf`, `anyOf`, `oneOf`, `not`, `if`/`then`/`else`). An unknown keyword raises
    `ResultError`, so a grown schema is never half-checked. `result_matches` runs it first.
    It takes 0.03 s on the owner's 101-ply game (125 KB).
15. **One check for reading and writing** (rev. 3). The worker runs the same `result_matches`
    on a fresh document before `result.json` is written; a document that fails it fails the job.
    `Jobs(check=...)` replaces it only in the tests whose stub analysis returns a minimal
    document.

## 3. Tests (AS-D §10)

| Obligation | Test (`tests/server/`) |
| --- | --- |
| 1 | `test_pipeline.py::test_1_the_pipeline_matches_the_tool`: same texts, same graph digests as `explain_game`, schema-valid, `stored` true |
| 2 | `test_2_the_normalized_request_is_the_recorded_one` (a capture, castling, a rated game, a `FEN` header with a promotion); `test_2_the_moves_after_the_target_change_no_byte`; `test_2_a_missing_fen_header_and_the_standard_fen_share_a_key` |
| 3 | `test_3_a_second_run_searches_nothing_and_gives_the_same_bytes` (no engine call, equal bytes, `stored` true in both); `test_3_a_shared_opening_is_analysed_once`; `test_3_other_ratings_share_nothing`; `test_3_damaged_or_foreign_files_are_misses_and_are_replaced` (`.graph` → `StoredGraphError`, `.tree` → `StoredTreeError`, a missing `.tree`, another build); `test_3_a_left_over_temporary_file_is_ignored`; `test_3_a_bundle_that_does_not_re_load_fails_the_job` |
| 4 | `test_jobs.py::test_4_the_same_game_is_one_job_and_other_headers_another` |
| 5 | `test_5_states_progress_and_a_failed_job_posted_again`, `test_5_running_progress_reports_the_current_move_and_an_estimate`, `test_the_worker_thread_runs_the_queue` |
| 6 | `test_6_restart_resumes_and_cached_plies_are_not_analysed_again`, `test_6_another_environment_is_never_resumed` (engine), `test_6_another_build_is_never_resumed` |
| 6a | `test_6a_a_damaged_job_file_is_isolated` (truncated, not JSON, no `pgn`, a wrong type; a left-over `.tmp` removed), `test_6a_damaged_result_and_error_files`, `test_6a_an_interrupted_write_keeps_the_previous_file` |
| 7 | `test_engine_failure.py`: round 0 once (restart, success) and twice (job fails, the next runs); a later round's `REFUSED(EngineError)` (discarded, re-analysed, only the clean analysis cached); not retried (`EngineOutputError`, `BudgetExceededError`, another `AnalysisFailed` cause); a restarted engine with another identity |
| 7a | `test_7a_concurrent_posts_make_one_job_and_respect_the_queue_limit` (8 threads, one job; 25 threads, 20 queued, 5 refused) |
| 8 | `test_web.py`: routes, 409 before done, `Cache-Control`, every row of §6.3 (404, 415, 413, 400 ×10, 503), no other path, no `OPTIONS`, no CORS |
| 10 | `tests/test_package_boundaries.py`: two new tests and `server` in `NEW_PACKAGES` |
| 11 | the existing time-class tests (`test_calibrate_curve.py`, `test_acceptance.py`, `test_explain_game.py`) pass unchanged against the moved functions |
| review B1 | `test_jobs.py::test_b1_a_job_never_runs_on_an_engine_it_was_not_posted_for` (J1's restart brings engine B; J2, posted for A, fails through `run_next` and writes no result; J2's game posted again runs under B), `test_b1_an_engine_that_failed_twice_is_not_reused` |
| review B2 | `test_b2_a_job_file_with_another_game_is_damaged` (another PGN, another range), `test_6_a_job_file_edited_to_another_environment_is_damaged` |
| review B3 | `test_b3_a_sound_result_is_done_after_a_restart`, `test_b3_a_result_that_is_not_this_jobs_is_not_done` (`{}`, another schema, build, engine, another game's result, fewer plies, `stored` false) |
| re-review B3 | `tests/results/test_validate.py`: every corpus document valid; on all 12 documents, 8 940 mutations (every field deleted, nulled, retyped, emptied, out of range) where `schema_errors` and `jsonschema` give the same verdict; missing `text`, `segments`, `claims`, `evaluation`, `refs`, `build_digest`, `grading`, `summary`; four bad bundle digests; an extra field still valid; an unsupported keyword raises. `test_jobs.py::test_b3_a_result_that_is_not_this_jobs_is_not_done` adds no `text`, no `segments`, no `claims`, no `evaluation`, a bad digest and a wrong grade type |
| review D1 | `test_engine_failure.py::test_the_tool_takes_the_same_per_ply_path` (the tool restarts after one engine failure and stops after two) |
| review note | `test_web.py::test_a_negative_content_length_is_refused` |
| 12 | `test_web.py::test_12_a_real_game_end_to_end` (gated on `CALLIOPE_STOCKFISH_PATH`): four plies of a rated game through HTTP, `done`, schema-valid, `stored` true |

## 4. Verification
- Suites (rev. 3): see §7. Rev. 2: the whole suite 4098 passed, 132 skipped; `tests/server` 77
  passed. Rev. 1: 4083 and 62. Test 12 is skipped without Stockfish and passes with it.
- Stockfish 19 (`d12_mpv5_v1`): test 12 passes in 11 s for four plies.
- **Cost of the cache.** Ten plies of the rated test game: 28.1 s analysed (2.8 s a ply,
  including the write, the read-back and the re-load), 6.4 s from the cache (0.64 s a ply, the
  replay by `load`). A 100-ply game therefore takes about 5 minutes the first time and about one
  minute when it is posted again or resumed.

## 5. What follows
AS2: the viewer's analyse panel (AS-D §7) and test 9.

## 6. Review dispositions (rev. 1 `e7093a3`, independent review: NOT_READY)

| Finding | Disposition |
| --- | --- |
| B1 `run_next` passed the current engine's identity, so after a restart to another engine the next job could run on it under an id that names the old one; an engine that failed twice was reused | Valid: `identity=self.slot.port.identity` made `analyse_game`'s check always pass. Applied (§2 items 6, 11): the job's engine fingerprint is passed; the environment now is checked against the job's before it runs, and the server's environment follows a changed engine; any failed job closes the engine. Tests B1. |
| B2 recovery did not re-derive the id from `job.json` | Valid. Applied (§2 item 12). Tests B2. |
| B3 any JSON `result.json` counted as done | Valid: `{}` was served as a result with an `immutable` header. Applied (§2 item 13): `result_matches`. Tests B3. |
| D1 the tool and the server shared only the intake and the requests | Valid. Applied (§2 item 1): `analyse_ply` and `document` are shared, so the tool also takes the engine-failure rule. Storage stays apart, recorded as AS-D §15. Test D1. |
| (note) a negative `Content-Length` reached `rfile.read` | Valid: `read(-5)` waits for the connection to close. Applied: 400. |

## 7. Re-review dispositions (rev. 2 `5a7946c`: NOT_READY)

The re-review passed B1, B2, D1 and the `Content-Length` note.

Suites (rev. 3): the whole suite 4142 passed, 132 skipped (16 min 24 s); `tests/server` 83
passed and test 12 skipped (passing with Stockfish); `tests/results/test_validate.py` 38 passed.

| Finding | Disposition |
| --- | --- |
| B3 (remainder) `result_matches` checked identity but not the schema's structure: a result without `plies[0].text` (or `segments`, `claims`, the evaluation, a valid digest) was still done and served `immutable` | Valid. Applied (§2 items 14, 15): `schema_errors` checks the whole shipped schema with no new dependency, `result_matches` requires it, and the worker applies the same check before writing. Tests: re-review B3. |
