# Agent — packet AG6b implementation: the game path

Status: **rev. 3 — reviews of rev. 1 and rev. 2 applied (§5, §6), for re-review**. Date: 2026-10-17. Design:
[`agent-ag6-design.md`](agent-ag6-design.md) rev. 4 (AG6-D: F1, F3, F8–F11, F17, §3.3, §3.6,
§4, §6, §7, §8; check I2), owner decisions Q4–Q6 (2026-10-17, AG6-D §15); with what CC1 measured
for long games ([`application-cc1-implementation.md`](application-cc1-implementation.md) §5). Base:
`main @ 0d13f42` (CC1 merged, PR #109).

## 1. Scope delivered

| Place | Change |
| --- | --- |
| `agent/jobs.py` (new) | `GameJobs`: the job table, one worker thread, the states of §4.2 (`queued`, `running`, `waiting`, `done`, `failed`, `cancelled`), `failed_plies`, the hourly ply window, the queue limit, `wait` (through `waiting`, at most 240 s, progress per ply), `cancel`, `snapshot`, the plies' summaries |
| `agent/budget.py` | `Limits` gains `job_window_seconds` (3600), `max_job_plies` (600), `max_job_plies_per_window` (400), `max_queued_jobs` (4); `MeteredSlot` (the one engine seen through one meter, §4.4); `EngineLock` (first come, first served, re-entrant, §4.3) |
| `agent/session.py` | one raw `EngineSlot`, the tools' `MeteredSlot` on AG4-D's meter, the engine lock around every analysis, search, build and identity read (a cache read takes none; an analysis checks the cache again under the lock); `analyze_start` / `analyze_wait` / `analyze_answer` / `analyze_game`; the jobs' per-ply path `_job_ply` (the job's slot and meter); `game_overview` and its moments; `show_game` answering `calliope_view_v1` within its byte bound; the game path's limit (600 plies); `next` on the game path (§7) |
| `agent/server.py` | the tools `analyze_game` (it starts or reads the job under the tool lock, waits in a thread holding no lock, answers under the lock; progress notifications) and `game_overview`; `show_game`'s description; the instructions' game order (§7) |
| `agent/definitions.py` | `agent_tools_v5`, `agent_guidance_v3`; `budget.jobs_v1` |
| `server/cache.py`, `server/pipeline.py` | `PlyCache.kept_keys()`, `PlyCache.file_digests(key)`; `EngineSlot.current` (the running port, never starting one) |
| `results/schema/calliope_view_v1.json` (new), `results/document.py` | the board's schema, `result` referring to `calliope_result_v1` by `$id`; `view_schema()` |
| `viewer/index.html` | `viewDocument`, `pollInterval`, `stateText`, `jobText`; the page reads either document, shows a ply's state, the job's line, the omitted, and follows a job (5 s, or up to 60 s while it waits), stopping with a note when the host refuses the board's calls |
| `tools/mcp` | `--job-window` and the job limits as options (from `Limits`) |
| tests | §3 below; the tests that read `show_game`'s old document read `result` |

Not changed: the HTTP server's jobs (`calliope.server.jobs`) and its viewer path, the stored
formats, the cache keys, the reasoning build.

## 2. Choices and departures (for the reviewer)

- **Summaries of plies, kept in memory** (beyond AG6-D, from CC1 §5). A job keeps each ply's
  summary (move, grade, label, score, best move, loss, White's expected points) as it finishes the
  ply, and so does a digest; the overview reads them, and replays only a cached ply it has no
  summary of (after a restart). A stored per-ply record beside the bundle would also spare that
  replay; it changes the results contract and is left for its own design.
- **The board reads kept pairs first** (`PlyCache.kept_keys()`), so a range larger than the LRU is
  not read in an order that evicts each pair before it is asked for.
- **A ply whose files exist but do not load** is shown `none`, not `analysed` (a miss, AS-D §4).
- **`slot.port_for(meter)` of §4.4 is an agent-side `MeteredSlot`** over the server's raw
  `EngineSlot`: `calliope.server` is unchanged, `analyse_ply` takes a `MeteredSlot` as it takes a
  slot (`port`, `restart`).
- **The job's meter** counts its searches without a limit of its own (the job's budget is plies,
  §8); `analysis_bound` per ply still holds in the reasoner.
- **The engine lock is re-entrant** for its holder (an analysis reads the build within its hold);
  callers are served by ticket, in arrival order, so the worker re-queues behind every caller that
  came first.
- **Failure classes**: `analyse_ply` raises `JobFailed` both for a ply that fails without the engine
  and for an engine that failed twice; the worker tells them apart by the cause (`AnalysisFailed`):
  the first goes to `failed_plies`, the second fails the job.
- **Waits use real time; the hourly window uses the session's clock** (tests inject one). A job
  waiting for budget looks again at least every 5 s, or when cancelled or stopped.
- **`open_game`'s `next`** names both paths: `analyze_game` for a game, `ply` for one ply.
- **`next` after a digest** follows the moments of the last overview of the game (the next unread,
  then `submit_commentary(items)`); without an overview it is AG6a's.
- **The board's bound** is kept on its result part with 64 KiB left for the moves, the states and the
  job (§6.2's construction); a record over 64 KiB, a commentary over 64 KiB, then commentary
  (plies that are not moments first, from the end), then records (from the end) are left out and
  named; a final check measures the whole document.

## 3. Test obligations (AG6-D §13, the AG6b part; I2)

| Obligation | Where |
| --- | --- |
| A job runs its plies in order, counts cache hits, charges uncached plies to its window, keeps summaries | `test_game_jobs.py::test_a_job_runs_its_plies_in_order_counting_the_cached` |
| The same range answers the same job; another range refused; over 600 plies refused; an ended job replaced | `::test_the_same_range_is_the_same_job_and_another_is_refused` |
| The queue limit | `::test_the_queue_holds_its_limit` |
| A non-engine failure goes to `failed_plies`, the job goes on | `::test_a_ply_that_fails_without_the_engine_is_listed_and_the_job_goes_on` |
| The engine failing twice fails the job; a new job reuses the cache and runs the rest | `::test_the_engine_failing_twice_fails_the_job_and_a_new_job_reuses_the_cache` |
| The hourly limit: `waiting` with `resume_after_seconds`, then `running` and `done` | `::test_the_hourly_limit_waits_and_resumes_by_itself` |
| `cancel` from `queued`, `running`, `waiting` | `::test_cancel_from_each_active_state` |
| B8: a wait holds through `waiting`; progress per ply | `::test_a_wait_holds_through_waiting_and_reports_progress` |
| Stop cancels what is active | `::test_stop_cancels_what_is_active` |
| Meters: a job's searches on its meter, a tool's on AG4-D's, across a restart; a cache hit moves neither | `test_game_path.py::test_a_game_is_analysed_by_one_job_charged_to_its_own_meter` |
| A restarted process finishes from the cache | `::test_the_same_game_again_finds_its_plies_in_the_cache` |
| The job budget: plies a job, the hourly window, cancel | `::test_the_job_budget_holds` |
| `next` after `analyze_game`, every row (B8's long wait) | `::test_next_after_analyze_game` |
| Locks: a cached `ply` answers during a job; `judge_move` waits one analysis; a ply asked by a tool and the job is analysed once | `::test_tools_answer_while_a_job_runs_and_no_ply_is_analysed_twice` |
| The engine lock serves in turn and is re-entrant | `::test_the_engine_lock_serves_in_turn` |
| I2 through the client: `show_game` answers during an `analyze_game` wait; progress per ply | `test_server.py::test_analyze_game_waits_without_the_tool_lock_and_reports_progress` |
| Moments: more than 8 candidates, ranking and ties, several reasons, a turning point | `test_game_path.py::test_the_moments_follow_their_rules` |
| The overview: lines, Korean names, moments, the grading warning, `next` to the moment and then to `items` | `::test_the_overview_of_an_analysed_game` |
| A long game: ranges, lines of the asked range, the whole game's moments in every range | `::test_a_long_game_is_read_in_ranges_with_the_whole_games_moments` |
| Over 600 plies refused on the game path | `::test_a_game_over_600_plies_is_refused_on_the_game_path` |
| The board during a job (`pending`, the job) and after it | `::test_the_board_follows_a_job` |
| The board's bound: commentary left out by its order, records next, a record over its own bound; named in the view, the plies and the text | `::test_what_does_not_fit_the_board_is_left_out_whole_and_named` |
| `calliope_view_v1` validates (empty and analysed); an empty board is not an error | `test_server.py::test_show_game_answers_the_board_of_the_cached_plies`, `::test_show_game_opens_before_any_ply_is_analysed` |
| A range's records and the whole game's states; the limits; an unloadable ply | `test_show_game.py` |
| The viewer reads either document; its intervals and lines | `tests/viewer/test_viewer_view.py`; `check_app.js` reads the view |
| Build: `agent_tools_v5`, `agent_guidance_v3` pinned | `test_guidance.py`, `test_commentary.py` |

## 4. Results

### 4.1 Tests

- The whole suite with Stockfish 19 (`CALLIOPE_STOCKFISH_PATH` set) on `db42b10` (the code of this
  packet; only documents changed after it): **1571 passed** (18.5 min), none failed or skipped — 1536
  at CC1, 35 new here.
- `ruff check` and `ruff format --check` on `src`, `tests`, `tools`: clean.

### 4.2 The acceptance trial (AG6-D §12)

AG6-D §0.2's request again: HIMARI v3 `main @ 9a07e0e` (its driver, server sandbox, one shared
Calliope process, the MCP App on), Calliope at `db42b10`, `openai/gpt-6-luna`, an empty data
directory and a fresh conversation per turn, the Opera Game, "이 대국을 분석해 줘." with its PGN.
2026-10-17. Beside it: §0.2 (Calliope `1f9ef15`) and AG6a's T2 (AG6a §4.3).

| Turn | Runs | Time | Input tokens (cached) | Largest request | Plies analysed | Commentaries on the board | Chat reply |
| --- | --- | --- | --- | --- | --- | --- | --- |
| §0.2 (before AG6) | 9 | 103 s | 80,640 (49,397) | 30,243 | 10 (refused after) | 0 (from memory, in the chat) | about 1,900 characters |
| AG6a T2a / T2b | 9 / 7 | 82 / 104 s | 103,178 / 142,064 | 15,542 / 29,383 | 10 / 10 | 3 / 10 | 253 / 406 characters |
| **AG6b T3a** | 11 | 147 s | 164,061 (139,103) | 23,708 | **33 of 33** | **7** (12, 18, 19, 25, 29, 31, 33) | 213 characters |
| **AG6b T3b** | 11 | 153 s | 155,213 (136,050) | 23,465 | **33 of 33** | **6** (12, 18, 19, 25, 29, 31) | 187 characters |

Against §12:

- **Every ply analysed**: one job of 33 plies, started by `analyze_game` and finished within the
  second call's wait (`wait_seconds` 240): no "분석되지 않았습니다" on the board.
- **No summarising** of the context (every Run a turn's own; the largest request 23.7k tokens).
- **Every moment commented and shown**: the overview's moments — 12 (loss), 18 (mistake, loss),
  19 (brilliant), 25 (brilliant), 29 (mistake, loss), 31 (brilliant), recomputed from the trial's data
  — all carry an accepted commentary in both turns, shown by the final `show_game`; T3a also
  commented the mate.
- **The order followed**: `open_game` → `analyze_game` → (the guides) → `analyze_game` with a wait →
  `game_overview` → `ply` of the moments → `submit_commentary(items)` → `show_game`, as the
  instructions and `next` give it.
- **Cost**: more input than AG6a's turns (more plies read, one longer wait), within the 3M turn
  budget; the time includes about 95 s of analysis.

Seen and left for later:

- The first `items` call of each turn had 1–2 items refused by S3 — a move written that no cited
  proposition holds (`11.Bxb5+`, `14.Bxe7`) — resubmitted alone and accepted.
- The commentaries cite claims; none explores a line (`explore`, `judge_move` unused): the "why" is
  the catalogue's (AG6-D §10).
- 15.Bxd7+ is graded mistake (AG6-D §11), and the commentaries say so: a grading fault shown to the
  user, for its own packet.

## 5. Review of rev. 1 (PR #110, `fddff0f`): NOT_READY — disposition

| ID | Finding | Disposition |
| --- | --- | --- |
| B1 | `Session.close()` closed the engine after a 5 s join whether or not the worker had ended; a cancel during the last ply ended `done` | Fixed. `GameJobs.stop` answers whether the worker ended; `close` waits up to `STOP_SECONDS` (120) and closes the engine only then, under the engine lock; a worker that has not ended keeps the engine (logged; the process's exit ends both). A job cancelled or stopped during its last ply ends `cancelled`. Tests: `test_game_path.py::test_the_engine_closes_only_after_the_worker_ends` (a ply of searches of 2 s each: `close` waits over 5 s, every search ends before the close), `::test_a_worker_that_does_not_end_keeps_the_engine`, `test_game_jobs.py::test_a_cancel_during_the_last_ply_ends_cancelled`, `::test_stop_waits_for_the_worker_and_says_whether_it_ended` |
| B2 | A kept summary was answered after its cache files were gone: the overview said analysed, the board `none` | Fixed. A summary carries the sha256 of the tree and graph it was made from (the record's `bundle`); `_summary` reads the files' digests now (`PlyCache.file_digests`, under the key's shared lock) and answers a kept summary only when they are the same, else reads the cache (a miss: not analysed). Test: `test_game_path.py::test_the_overview_and_the_board_agree_when_files_are_gone` |
| B3 | Every cache key took the engine lock through `_engine_build`, so a cached read waited for the job's analysis | Fixed. The build and its digest, known for the running port (`MeteredSlot.current()`, over `EngineSlot.current`, which never starts an engine), are read without the lock; only a start or a restart builds under it. `_identity` reads the same. Test: `::test_a_cached_ply_never_waits_for_an_analysis` (the job blocked inside a search; `ply`, `ply(view="full")`, `show_game` and `game_overview` of cached plies answer meanwhile) |
| B4 | `max_job_plies_per_window = 0` left a job `waiting` forever | Fixed. A window of no room fails the job at its first uncached ply, with the reason; a job of cached plies only still runs. Tests: `test_game_jobs.py::test_a_job_budget_of_none_fails_the_job_at_its_first_uncached_ply`, `test_game_path.py::test_a_job_budget_of_none_fails_the_job` |
| N1 | A ply admitted as uncached was charged even when a tool analysed it before the job's own look under the engine lock | Fixed. `_admit` only checks room; `_job_ply` charges (`GameJobs.charge`) after its last cache look, just before it analyses. Test: `test_game_jobs.py::test_a_ply_cached_meanwhile_is_not_charged` |
| N2 | `wait` reported changes of `done` only: plies finishing together merged, `waiting` not reported | Fixed. A job keeps its events (each ply finished, each change of state) in order; `wait` reports every one after its start, none merged; `analyze_game` sends each as a progress notification with its message. Tests: `test_game_jobs.py::test_every_ply_and_every_change_of_state_is_reported_in_order`, `::test_a_wait_holds_through_waiting_and_reports_progress` |
| §6.2 | Suggested: the board's bound with 200 commentaries of the largest size | Added: `test_game_path.py::test_the_board_holds_its_bound_with_200_of_the_largest_commentaries` (small records: commentary goes, the moments' last; large records: all commentary, then records from the end, as many as fit). It showed the bound rebuilt the document once per commentary dropped (quadratic in the worst case); it now drops by each one's measured size and rebuilds once per run, the measured document still deciding |

Tests after the fixes, on `c2e59c3`: the whole suite with Stockfish 19 **1582 passed** (19.3 min,
11 new), none failed or skipped; `ruff check` and `ruff format --check` clean. The fixes change no
answer the acceptance trial (§4.2) relied on.

## 6. Re-review of rev. 2 (`ead34f2`): NOT_READY — disposition

B1–B4 and N1–N2 passed. The re-review raised three findings, all fixed:

| ID | Finding | Disposition |
| --- | --- | --- |
| B5 | A ply whose two files exist but do not load passed `_admit` as cached; `_job_ply`'s `charge()` then charged without checking room, so an analysis could run with the budget spent or 0 | Fixed. `GameJobs.charge` checks the room and takes it in one hold of the job lock and raises `NoRoom` when there is none; `_job_ply` calls it after its last cache look, under the engine lock, before any search. On `NoRoom` the engine lock is released (the exception leaves its hold) and the worker returns to `_admit` for that ply without the cache look — `waiting` for room, or `failed` when the limit is 0 — and then runs the ply again. Tests: `test_game_jobs.py::test_a_ply_whose_files_do_not_load_is_charged_and_waits_like_any_analysis` (budget spent: waits, then analysed and charged in the next hour; budget 0: fails, nothing analysed), `test_game_path.py::test_a_corrupt_pair_on_disk_is_not_a_way_around_the_job_budget` (real files overwritten; no search made) |
| B6 | The queue limit counted queued jobs only once a job was running, so jobs started before the worker took one were not limited | Fixed. The limit counts every active job (queued, running, waiting): at most `1 + max_queued_jobs`. Test: `::test_the_queue_limit_holds_before_the_worker_takes_a_job` (the test holds the job lock so the worker can take none: five start, the sixth and seventh are refused) |
| B7 | The end of a finished job was decided in one hold of the job lock and written in another, so a `cancel` between them ended `done` | Fixed. The decision and the write are one hold. Test: `::test_a_cancel_while_the_job_is_active_always_ends_cancelled` (a cancel injected where a separate write would let it in, and cancels timed across the jobs: a job is `cancelled` exactly when a cancel reached it while active) |
| Note | Cancelling a `queued` job reported no event | Fixed: it records `cancelled`. Test: `::test_a_queued_job_cancelled_reports_it` |


Tests after the fixes, on `4a99f33`: the whole suite with Stockfish 19 **1587 passed** (19.3 min,
5 new), none failed or skipped; `ruff check` and `ruff format --check` clean.
