# Agent — packet RX1 implementation: the Calliope-run agent and its run record

Status: **rev. 2, for independent re-review. Independent review of rev. 1 (`23bb2ac`): NOT_READY (B1–B3; N1, N2), applied, §5.** Date: 2026-11-05. Design: [`agent-rx1-design.md`](agent-rx1-design.md)
(RX1-D) rev. 3, under [`agent-rx0-design.md`](agent-rx0-design.md) (RX0-D) rev. 4. Base: `main @ 2519677`
(RX1-D merged, PR #140).

## 1. Scope delivered

| Place | Change |
| --- | --- |
| `agent/record.py` (new) | `identity_fields`, `identity`, `line_key` (RX0-D §5); `Recorder`: `tools.jsonl` lines with `run`, `seq`, `t`; `wrap(name, kind)` for async and sync functions: one `call` line per MCP tool call (`kind: "call"`) or one `read` line (`"resource"`, `"prompt"`); a call context (`contextvars`) with `call_id` whose `handle` and `submission` events are written after the `call` line, kept on error; events outside a call written at once with `call_id: null`; the 32 MiB answer cap (`capped: true`, digest and size kept); a write error stops recording and never fails a call; `recorder_from_environment` |
| `agent/server.py` | `build_server(session, page, guide_name)`; `GUIDES = (commentary_ko_v8, commentary_min_v1)`; `rec` = the session's recorder's `wrap`, or the identity; `show_game` wrapped once before either registration; every `@server.tool`, `@server.prompt`, `@server.resource` wrapped beneath its decorator; the guide resource and the `calliope_commentary` prompt serve `guide_name` |
| `agent/session.py` | `Session.recorder` (None by default); `_serve` hands each served handle's entry to the recorder; `submit_commentary` hands each subject's `submitted` (as the arguments carried it), `verified` (the propositions after `_by_handle`, as the check read them), outcome, id and problems; `_ranking` (every ply with a reason, in ranking order) under `_moments`, whose output is unchanged; `rx_moments` (RX0-D §3.1) and `Session.rx_moments(game_id)` (every ply analysed, or refused) |
| `agent/prompts/commentary_min_v1.md` (new) | v8's task in one line and its sections 받는 재료, 인용, 표기, 수 전 상황, 판의 변화, 제출, word for word |
| `tools/mcp/__main__.py` | `--guide`; the recorder from `CALLIOPE_RUN_RECORDS` and `CALLIOPE_RUN_ID`; its `start` line (tools version, agent build, guide, engine, limits, data, app) and `end` line (`closed` or `error`) |
| `tools/rx/` (new) | `model.py` (OpenRouter over `urllib`, HIMARI's request fields, a 120 s socket timeout and one retry, the key from the environment or `--env-file`, never written); `run.py` (one run: a copy of the base cache, the server as a child over MCP stdio, the guide in the system prompt, the task with the fixed moments, the loop, arm B's retry, empty hooks `lessons` and `critic`, the bounds, the agent layer, the base cache checked after the run); `manifest.py` (base caches analysed and sealed, `sets_v1.json`); `check.py` (wholeness, RX0-D §4.4; finals, §6.0); `__main__.py` (`manifest`, `run`, `check`, `finals`) |
| `tools/rx/sets_v1.json` (new) | the manifest (§4) |
| `tests/agent/test_record.py` (new) | §3 |

## 2. Choices and departures

- **Where the suite runs.** `server/cache.py` imports `fcntl`, so Calliope's server and its tests run on Linux
  only. This host is Windows. Everything here ran in WSL (Ubuntu 24.04, Python 3.12.3) in a venv outside the
  repository (`~/calliope-venv`, `pip install -e ".[dev,agent]"`), with the repository's Stockfish 19 Windows
  build called through WSL's interop. The trials ran on HIMARI's host, with a Linux build.
- **The engine build changes one golden.** `tests/agent/test_digest.py::test_the_full_view_is_todays_answer_field_for_field`
  fails on `main` too in this environment (§3): its golden holds tree digests made with the Linux build. It
  is not a regression of RX1.
- **Stopping a run** (RX1-D §4.7, review N4). The tool timeout and the run's wall-clock bound are
  `anyio.fail_after` scopes. Leaving them leaves `stdio_client`, whose shutdown closes the server's stdin,
  waits, then terminates its process tree (the MCP SDK's own termination, a process group on POSIX, a job
  object on Windows). RX1 relies on it rather than a second kill of its own. The agent layer's `end` is
  written by the runner in every case (rev. 2: under a `try/finally` around the whole run, review B2). The
  model call runs in a worker thread that the run's bound abandons (`abandon_on_cancel`), and the body is
  read by a deadline as well as a socket timeout (review N1), so the bound holds against a stalled or
  slow-dripping request. An abandoned thread ends at its own deadline.
- **The min guide is not registered.** `commentary_min_v1` is served only with `--guide commentary_min_v1`,
  for arm A-min. `agent_build`'s `prompts` digests stay those of the served-by-default prompts (v8), so a
  commentary accepted in A-min carries v8's prompt digest in its record. RX0-D §8 keeps A-min's commentaries
  out of every promotion, and the run's `start` line names the guide served.
- **The checker's call order** (rev. 2). The runner writes a `tool_unsent` line for every call it does not
  make (arguments that are not a JSON object, calls past the tool-call bound). `check` removes those from the
  model's calls and compares the rest with the server's `call` lines one for one (§5).

## 3. Tests

- `tests/agent/test_record.py`, 13 tests in rev. 1, 19 in rev. 2 (§5):
  - one `call` line per MCP tool call, with the App page and without it: `analyze_game` once, `definitions`
    once, `show_game` once; each `handle` and `submission` after its call with its `call_id`; a ref served
    again writes nothing; the guide read as a `read` line (reviews B1, B2, N3);
  - the submission keeps the handle the agent cited (`submitted`) and the server's propositions
    (`verified`), the stored id, and a refusal's rule S3 (N5);
  - recording changes no answer: the same script with recording off and on, handle tokens, budget values,
    times and ids normalised (N1); the tool schemas and descriptions equal with and without the recorder;
  - an event outside a call, an error that keeps its call's events, the cap;
  - identities: the facts tree's `rev` and a board item's `bundle` ignored; analysis and search `s` apart;
    `line_key`; two sessions' handles all different and their identities all equal;
  - `_moments` equal to `_ranking`'s first 16 in ply order; `rx_moments` past 16; a `miss` as the special
    moment and a filled error slot; fewer than three ranked plies refused;
  - the min guide keeps the contract sections and drops the direction, formats, and is served by `--guide`;
    an unknown guide refused;
  - the checker and finals on a written run; arm B's refused subjects; numbered moves.
- The whole suite in WSL, with the repository's Stockfish 19 Windows build: **1866 passed, 27 skipped,
  3 failed, 2 errors** (19 min 50 s). `main @ 2519677` in a worktree, in the same environment: 1853 passed,
  27 skipped, and the same 3 failed and 2 errors (35 min 20 s, beside the base caches' analysis). The five,
  on both:
  - `tests/agent/test_digest.py::test_the_full_view_is_todays_answer_field_for_field`: the golden's tree
    digests were made with the Linux build (§2);
  - `tests/tools/test_calibrate_curve.py`: two failed and two errors, `FileNotFoundError: 'zstd'`; the
    calibration tool calls the `zstd` program, which this WSL lacks.

  The difference, 13 passed, is `test_record.py`.

  Rev. 2 (review §5): the whole suite again, **1871 passed, 27 skipped**, the same 3 failed and 2 errors
  (17 min 4 s); the difference from `main`, 18 passed, is `test_record.py` as it then stood. Its 19th test
  (`test_a_call_the_runner_did_not_send_keeps_the_run_whole`), added after the suite started, passed with
  the file's other tests: 19 passed.

## 4. Acceptance (RX1-D §8)

1. **Unchanged when off.** `test_recording_changes_no_answer` and the tool-schema test (§3); the whole suite (§3).
2. **Whole runs.** Arm A, `openai/gpt-6-luna`, once on each Train game, 2026-11-05, in WSL. The request's fields
   were `messages`, `model`, `tools`, as HIMARI sends them (RX1-D Q2). `python -m tools.rx check`: all four whole.

   | Game | Run | Turns | Tool calls | Submissions (subjects: accepted / duplicate / refused) | Plies commented | Fixed moments with a final commentary | Seconds | Cost |
   | --- | --- | ---: | ---: | --- | ---: | --- | ---: | ---: |
   | hung | `01M6NEGY…` | 16 | 27 | 7 (15 / 1 / 8) | 15 | 3 of 3 (5, 5, 6 sentences) | 246 | $0.0201 |
   | rapid | `01M6NERH…` | 15 | 28 | 6 (15 / 0 / 7) | 15 | 3 of 3 (4, 6, 6) | 191 | $0.0187 |
   | fresh | `01M6NEYK…` | 12 | 24 | 5 (9 / 0 / 6) | 9 | 3 of 3 (6, 5, 7) | 272 | $0.0156 |
   | fourth | `01M6NF76…` | 16 | 25 | 6 (11 / 0 / 6) | 11 | 3 of 3 (5, 5, 6) | 236 | $0.0173 |

   - Every model tool call has its `call` line in order. Every `handle` and `submission` line carries the
     `call_id` of the call that made it. No call was capped: the tools layers are 1.0–1.5 MB.
   - The refusals' rules (M1a's classes, RX0-D §6.1): S3 38, S8 4, S2 1, `subject` 2, and 1 problem with no
     `rule` (a proposition that did not verify, which RX0-D §6.1 counts as a fact refusal). RX2's M1a needs
     `subject` placed in a class: it is the item's subject not holding, a form refusal.
   - The base cache was unchanged after every run (the runner's digest check), and each run's working copy
     was removed.
   - The agents called `open_game`, `analyze_game`, `game_overview`, `ply`, `submit_commentary`, `show_game` and
     `definitions`. None called `explore`, `judge_move` or `detail`, as in the trials (FR §3.1).
3. **Identities.** `test_identities_are_equal_across_sessions_and_handles_differ` (§3), over the synthetic
   engine: two sessions, every handle different, every identity equal. Rev. 2 adds
   `test_identities_are_equal_across_stockfish_sessions` (review N2): two sessions on Stockfish 19 read a
   ply, a judged move, facts and a searched explored line; every handle differs, every identity and every
   `line_key` is equal. It passed in WSL, and is skipped without `CALLIOPE_STOCKFISH_PATH`.
4. **The manifest.** `tools/rx/sets_v1.json`: Train by fixture path with the trials' moments; Validation with
   `rx_moments`' three plies and their slots; Test with digests only. Base caches: Train 271 plies, Validation
   388 plies, analysed in WSL, sealed with `base.json`.

   | Validation game | Moments (slot, rank, reasons) |
   | --- | --- |
   | 184800218248 | 12 error #1 (mistake, miss, loss); 57 error #2 (mistake, loss); 58 special #5 (mistake, miss) |
   | 185264271324 | 67 error #1 (blunder, loss, turning point); 45 error #2 (mistake, loss); 29 special #5 (mistake, miss) |
   | 185371835722 | 31 error #1 (blunder, loss); 32 error **filled** #3 (great); 30 special #2 (brilliant) |
   | 185922072242 | 138 error #1 (blunder, loss); 140 error #2 (blunder, miss, loss); 139 special #3 (blunder, miss, loss) |

   Two things for RX2 to weigh: a `miss` is often also a mistake, so a special moment can be an error as well;
   and in 185922072242 the three moments are three consecutive plies of one endgame sequence. Both follow
   RX0-D §3.1 as written.

   **Kinds of failure** (RX0-D §3.2), from each fixed moment's `ply` digest, read on a copy of each base cache
   (moments with the kind, of 12 a set):

   | Kind | Train | Validation |
   | --- | ---: | ---: |
   | `held` (a piece left en prise) | 5 | 3 |
   | `lost_defence` | 7 | 1 |
   | `same_reply` | 11 | 11 |
   | a relation claim (pin, fork, removed defender, discovery, newly exposed) | 1 | 1 |
   | `scene` (what the opponent's last move began) | 7 | 6 |
   | `threat` | 10 | 9 |
   | `weakness` | 6 | 5 |
   | `file` / `structure` | 2 / 0 | 1 / 2 |

   Every kind Train has is in Validation, so no game is replaced. The count of since-when texts older than the
   move is not in this table: the script read item kinds, not their since texts. Test is not inspected.
5. **Cost.** Four runs, $0.0717 in all, 2.14 M input and 53 k output tokens.

## 5. Review dispositions — rev. 1 (`23bb2ac`), independent review: NOT_READY

| Item | Finding | Disposition |
| --- | --- | --- |
| B1 | `line_key` is computed nowhere in the record, so M2a cannot match a line across sources, least of all when an answer is capped | Applied: `Recorder.handle` writes `line_key` on every `s` handle line, from the served item's PV and its address's FEN (`entry_line_key`); `tools/rx/check.py` gains `evidence`, `cites` and `covered` (M2a by identity, or by `line_key` for a line). Tests: every `s` handle line of a session carries it; an analysis and a search line of the same moves differ in identity and agree in `line_key`; `covered` by either, and by a built proposition id |
| B2 | An exception outside the four caught leaves no `end` and the working copy behind | Applied: `run_once` writes `start` first, runs the rest in `_run` under `try/except Exception/finally`: `end` (`error` with the exception logged), the log closed and the working copy removed in every case; the base cache checked after. A body that is not JSON is a `ModelError`. Test: a failing MCP connection (`JSONDecodeError`) ends `error`, the working copy gone |
| B3 | A subject named by `position` and the played move has `ply: null` in the record, so `finals` misses it | Applied: `_subject_record` adds the subject's `path` (UCI) and `game_ply`, set only when the path is the game's own line; `finals` reads `game_ply`. Test: `position` + 2.exd5 counts as ply 3, `position` + 2.Nc3 does not |
| N1 | The wall-clock bound waits for a model request in its thread; a slow-dripping body outlives the socket timeout | Applied: the request runs with `abandon_on_cancel=True`; the body is read by a deadline (`_read_by`). Test: a body that drips is cut at the deadline |
| N2 | Identities only on the synthetic engine | Applied: `test_identities_are_equal_across_stockfish_sessions` (§4 item 3) |

**Found while checking the fixes live.** A second live run on `hung` (`01M6NKF8…`, 22 turns, 34 tool calls,
$0.029, every fixed moment commented) failed the checker: the agent asked 34 calls and the server had 33. The
missing one was a `submit_commentary` whose arguments luna cut off mid-string (789 characters). The runner did
what RX1-D says: it sent nothing and told the model "arguments are not a JSON object". The record had no
line saying so, so the checker could not tell an unsent call from a lost one. Rev. 2 writes a `tool_unsent`
line in the agent layer for such a call and for calls left at the tool-call bound, and `check` compares the
calls sent with the server's `call` lines one for one (no longer a prefix). Test:
`test_a_call_the_runner_did_not_send_keeps_the_run_whole`. A third live run on `hung` after the change (`01M6NKXB…`): 19 turns, 32 tool calls, $0.0225, whole by the checker, the three fixed moments commented (6, 6, 6 sentences); its 789 `s` handle lines all carry `line_key`, its 21 submitted subjects all carry `game_ply`; it had no unsent call. The unsent case is covered by the test, not by this run.

