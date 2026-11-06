# Agent — packet RX4a implementation, part 1: the tooling for lessons

Status: **rev. 3, re-review READY_FOR_MERGE (N5, N6 carried, §6.2). Independent review of rev. 1 (`dd25117`): NOT_READY (B1, B2;
N1, N2), applied, §6. Re-review of rev. 2 (`70a5920`): NOT_READY (C1; N3, N4), applied, §6.1.** Date: 2026-11-06. Design: [`agent-rx4-design.md`](agent-rx4-design.md)
(RX4-D) rev. 3 with the owner's answers (§9), under [`agent-rx0-design.md`](agent-rx0-design.md). Base:
`main @ 08d5a6f` (RX4-D merged, PR #144).

RX4a runs in two parts. **Part 1 (this packet)** builds what the runs need: the lesson arms D and D-min, the
lesson set's file and rendering, screening runs keyed by candidate, the batch's arms and bounds, the bundle's
part size, and the report's labels. No model was called and nothing was judged. **Part 2** (§4) writes the
lessons and runs them; it is reported in this document's next revision.

## 1. Scope delivered

| Place | Change |
| --- | --- |
| `tools/rx/lessons.py` (new) | a set's file (`load`), its checks (`problems`: the four fields, at most 400 characters a lesson, no square or numbered move, an action that uses `explore`, `facts`, `judge_move` or `detail` with what to pass (`action_problems`), each lesson's versions the set's (`version_problems`), at most 8 lessons unless the file is `CANDIDATES`, unique ids), what a set may serve (`use_problems`: its status against the run's set and candidate, the owner's approval, the versions it was written for, a `NOT_PROMOTED` set only with `reproduce`), `select` (the whole set or one candidate alone, at most 8 a run), `render` (the four strategy fields only), `digest` |
| `tools/rx/run.py` | arms D and D-min; `RETRY_ARMS = (B, D)`, `LESSON_ARMS = (D, D-min)`, `MIN_ARMS = (A-min, D-min)`; `lessons(spec)` fills RX1-D §4.4's hook; the retry as `retry_feedback` and `retry_message`; the `start` line records `lesson_set`, `lesson_set_status`, `lesson_ids`, `candidate_id`, `lesson_set_digest`, `rendered_fields`; a candidate on B or A-min only on Train; the `feedback` line names the arm |
| `tools/rx/__main__.py` | `run --lessons --candidate --reproduce --turns --tool-calls --tokens --run-seconds`; `bundle --moments-per-part --max-commentaries` |
| `tools/rx/batch.py` | `--arms --sets --games --lessons --candidate` and the bounds, passed to each run; interleaved game, repeat, arm; RX2's default (A, A-min, both sets) unchanged; a lesson arm without `--lessons` stops the batch before any run |
| `tools/rx/judge.py` | `pack`: parts of whole groups (one moment's commentaries of one candidate) within at most `moments_per_part` moments (6, RX4: 4) and `max_commentaries` commentaries (36); the key keeps each run's `candidate_id` and `lesson_set_digest`, the judge's files neither |
| `tools/rx/report.py` | `--batch` more than once; a screening run reported as `<arm>:<candidate>`; `paired` gives `by_moment` and skips a pair with no moment in a set; `request_fetched` a moment-run (`fetched_value`) paired like M2b |
| `tests/agent/test_rx4.py` (new) | 16 tests (§3) |

## 2. How each design point is met

| RX4-D | Where |
| --- | --- |
| §3.2, C1, N2: D is B with lessons, D-min is A-min with lessons | `RETRY_ARMS`, `MIN_ARMS`, `LESSON_ARMS`; `retry_feedback` is the one place the retry is decided |
| §2.4, N5: only the strategy reaches the agent | `render` writes `condition`, `action`, `success`, `fallback`; `id`, `versions`, `source` stay in the file; the heading says the lessons apply only when their situation holds and that facts come from Calliope's tools |
| §2.3 step 2, N4: screening keyed by candidate | `--candidate` on both runs of a pair: on D it selects the lesson alone, on B it tags the run; the digest of B's (empty) lessons is `sha256("")`; the report's `D:L03` against `B:L03` |
| §2.2: a lesson never names a game | `problems` refuses a square (`a5`) or a numbered move (`29...Bxa5`); a bad set stops `run_once` before any record |
| §3.1: one bound for the arms compared | the run's and the batch's bound flags; the batch log keeps the bounds of every row |
| §4: the part size a setting | `bundle --moments-per-part 4 --max-commentaries 36`: three arms, three runs, 36 commentaries a part; a screening judging of many candidates packed by commentaries |
| §2.3 step 4: only an approved set on Validation | `use_problems`: `CANDIDATES` for screening on Train, `CHECKING` for the set check on Train, `APPROVED` (with the owner's `approval`) or later for Validation |
| §2.3 step 2: kept on M2b or on `request_fetched` | both paired by moment (`report --pair D:<id> B:<id>`: `decisive` and `fetched`) |
| §3.2, N1: interleaved | `batch.jobs`: B, D, B, D … within a game, repeat by repeat |

## 3. Tests

`tests/agent/test_rx4.py`:

1. each lesson arm inherits its base and only its base: the same refused answer gives B and D the same retry
   message, A, A-min and D-min none; D's retries stop at the bound; no retry on another tool or a tool error;
2. only the strategy reaches the prompt: marker strings in `source` and `versions` are not in the rendered
   text, the four fields are; ids and the set's name are not; no lessons for A, B, A-min; B with a set and D
   without one are refused;
3. a screening run carries one candidate alone, B the same candidate with the empty digest;
4. a lesson set is refused for a square, a numbered move, a missing field, nine lessons (twelve pass in a
   `CANDIDATES` file), a lesson too long, a repeated id; `material_gain` is not a square;
5. a bad lesson set stops before any record;
6. the `start` line of a D run records the set, the lesson, the candidate, the fields and the digest, and no
   `source`;
7. the bundle at 4 moments a part: 27 commentaries in parts of 4, 4 and 1 moments, 12 commentaries in a part
   of 4 moments and three arms; the candidate in the key, not in the bundle; a part size of 0 refused;
8. the batch interleaves B and D, passes `--lessons` to D only and the candidate to both, passes a bound, and
   refuses D without a set; RX2's default order unchanged;
9. screening runs paired by candidate, never pooled; `by_moment`; no moments in a set gives `moments: 0`;
10. a set serves only the runs its status allows (B1): twelve candidates without a candidate, or on Validation,
    refused; `CHECKING` on Validation or with a candidate refused; `APPROVED` without the owner's approval
    refused; an unknown status refused; more than 8 lessons in a run refused; B's candidate tag on Validation
    refused;
11. a set runs only on its versions (N2): another guide (D-min on a v8 set) or another build refused;
12. parts hold whole candidates within both limits (B2): twelve candidates on three moments (216 commentaries)
    in parts of at most 36 and 4 moments, each candidate's moment in one part; RX2's 12 moments packed 6 and 6
    as before; a group larger than a part refused;
13. `request_fetched` paired by moment (N1): the share of decisive `on_request` causes fetched, `None` without
    one;
14. an action must use a Calliope tool with what to pass (re-review C1): an abstract instruction, an empty
    step, a tool that does not exist (by name or as a call), a tool's name alone, a non-list refused; steps with
    `explore`, `facts`, `judge_move` and a call `explore(…)` kept;
15. a lesson's versions are the set's (N3): another `tools` value, or a version the set does not fix, refused;
16. a `NOT_PROMOTED` set runs only to reproduce (N4): refused without `reproduce`, recorded in the `start` line
    with it, passed by the batch; a `PROMOTED` set runs.

The runner and record tests: `tests/agent/test_record.py` and `test_rx4.py`, 48 passed, 1 skipped (Stockfish).
The whole suite: §5.

## 4. Part 2: what follows (RX4-D §2.3, §3)

1. **The evaluator.** A fresh Claude session in a directory outside the repository holding only Train
   material: RX2's Train commentaries of arm A with their judgings and key, the Train run records, the Train
   references, and Calliope's tools on a Train data directory. Its brief names those files only. It writes
   `tools/rx/lessons/candidates_v1.json` (`CANDIDATES`, at most 12, `versions`: `commentary_ko_v8` and the
   bases' build `8124217c21b25fb5…`, the same for Train and Validation, and the tools version; each lesson's
   versions are the set's). Its transcript is audited.
2. **Screening.** For each candidate, `batch --arms B D --sets train --runs 1 --games <its source games>
   --lessons candidates_v1.json --candidate <id>` under RX1's starting bounds, all under one batch name; one
   bundle (`--moments-per-part 4 --max-commentaries 36`); one blind judging; `report --pair D:<id> B:<id>` read
   on the candidate's source moments (`decisive` and `fetched` by moment).
3. **The set.** `lessons_v1.json` (`CHECKING`) from the kept candidates; `batch --arms B D --sets train --runs 3`; one
   judging; D's bounds from its runs (RX2 §8's rule).
4. **D-min.** The same from A-min's Train failures by a second evaluator session, screened against A-min.
5. **The owner approves `lessons_v1`** (Q3): its status becomes `APPROVED` with `approval` (`by`, `date`).
6. **The comparison.** `batch --arms B D --sets validation --runs 3` under the larger of D's and RX2's bounds;
   one bundle of A (RX2's), B and D at 4 moments a part; the calibration bundle of A, A-min (RX2's) and D-min on
   Train; the report; `PROMOTED` or `NOT_PROMOTED`; the evidence in `rx-evidence/rx4/`.

## 5. Verification

- `ruff check` and `ruff format` on `tools/rx` and the new test: clean.
- The whole suite in WSL with Stockfish, rev. 3: **1902 passed, 27 skipped, 3 failed, 2 errors** (16 min 50 s;
  rev. 2: 1899, rev. 1: 1895 passed, the new tests the difference). The five
  are the environment's, the same as on `main` (RX2 implementation §8): the digest golden
  (`test_the_full_view_is_todays_answer_field_for_field`, the Linux engine build) and four
  `test_calibrate_curve` tests (`zstd` missing).
- Not verified here: a live run of D or D-min against the model (part 2's first screening batch is that).

## 6. Review dispositions — rev. 1 (`dd25117`), independent review: NOT_READY

| Item | Finding | Disposition |
| --- | --- | --- |
| B1 | Nothing checks a set's status against the run: a `CANDIDATES` file without a candidate would put all twelve candidates into a Validation run | Confirmed. Applied: `lessons.use_problems` (statuses `CANDIDATES`, `CHECKING`, `APPROVED`, `PROMOTED`, `NOT_PROMOTED`; candidates on Train with one candidate only; a set not approved on Train only; approval needs `by` and `date`); `select` refuses more than 8 lessons in a run whatever the file holds; tests 10 |
| B2 | Parts limit moments, not commentaries: twelve candidates on one game's three moments would put 72 commentaries in a part | Confirmed. Applied: `judge.pack`, whole groups (a moment's commentaries of one candidate) within at most 4 moments and 36 commentaries, so a candidate's B and D at a moment stay in one part of one judging; RX2's parts unchanged (6 moments × 2 arms × 3 runs = 36); `--max-commentaries`; test 12 |
| N1 | `by_moment` does not cover M3 `request_fetched`, one of the two keep criteria | Applied: `fetched_value` a moment-run, paired as `fetched` beside `decisive`; test 13 |
| N2 | A lesson's `versions` are not checked | Applied: every set names `versions` (`guide`, `build_id`); a run on another guide or base build is refused with "write and approve the set again"; the bases' build is one for Train and Validation; test 11 |

## 6.1 Review dispositions — rev. 2 (`70a5920`), independent re-review: NOT_READY

B1, B2, N1 and N2 passed.

| Item | Finding | Disposition |
| --- | --- | --- |
| C1 | `problems` checks only that `action` is not empty: an abstract instruction with no tool passes | Confirmed. Applied: `action_problems`, the action a list of non-empty steps, at least one using `explore`, `facts`, `judge_move` or `detail` (RX4-D §2.2) with at least 6 characters beyond the tool's name (what to pass, where); a step that calls something by name (`name(`) must call one of the four; test 14 |
| N3 | Only the set's versions are checked; a lesson may carry older ones | Applied: `version_problems`, each lesson's `versions` must be the set's, key by key, and a key the set does not fix is refused; the set fixes them when written and the owner approves them with it; test 15 |
| N4 | A `NOT_PROMOTED` set can run on Validation again, against RX4-D §5 (kept, not used) | Applied: refused unless the run asks `--reproduce` (run and batch); the `start` line records `reproduce`; test 16 |

## 6.2 Review dispositions — rev. 3 (`9b7dfd6`), independent re-review: READY_FOR_MERGE

C1, N3 and N4 passed; B1 and B2 still hold. No new blocking finding.

| Item | Finding | Disposition |
| --- | --- | --- |
| N5 | `action_problems` checks form, not intent: "explore는 사용하지 말고 더 깊이 생각한다" passes | Accepted as a limit of a check on natural language. In RX4a each lesson is screened on Train and approved by the owner, who reads its action. Carried to RX5: an action with `tool`, `arguments` and `purpose` as fields, before lessons are written or promoted without the owner |
| N6 | A lesson with no `versions` passes `version_problems` | Carried to part 2's first commit: each lesson must carry `versions` equal to the set's, before the evaluator's `candidates_v1.json` is checked |

## 7. Part 2 so far (branch `agent/rx4-lessons`)

**N6** (§6.2): `version_problems` refuses a lesson without `versions` or without a version the set fixes;
`tests/agent/test_rx4.py` test 17.

**The evaluator** (§4 step 1). A fresh session in `D:/00_프로젝트/rx-work/rx4-eval-A` (outside the repository)
holding only Train material: arm A's 12 Train runs (`agent.jsonl`, `tools.jsonl`), their 36 judged
commentaries and verdicts, the 12 Train references, the guide v8, the tool definitions, and `probe.py`
(`tools/rx/probe_train.py`: Calliope's tools on a copy of Train's base only). Brief and notes:
`rx-evidence/rx4/evaluator-A-brief.md`, `evaluator-A-notes.md`. Its transcript was audited (92 calls): no
Validation, Test, `.env` or run data outside `probe.py`; it kept scratch output in its own scratchpad. It
wrote 7 candidates; installed as `tools/rx/lessons/candidates_v1.json` with `versions` (`commentary_ko_v8`,
build `8124217c…`, `tools`: the tool definitions' digest); every lesson passes `problems` and `use_problems`.

**Screening** (§4 step 2). Batch `rx4-screen-1`: for each candidate, B and D (that lesson alone) on its
source games, one run a game, RX1's starting bounds: 26 runs, all `done`, $0.40. One bundle (judging
`6c418b13`, 3 parts, 78 commentaries), three blind judges, all audits passed under A1 below. Report:
`rx-evidence/rx4/screen-report.json`; tool use per run: `screen-tool-use.txt`.

D − B on each candidate's source moments (decisive causes explained, share; wrong sentences per 100; score):

| Candidate | Source moments | Decisive | `fetched` | Wrong | Score | Its action called in D's runs | Rule (RX4-D §2.3 step 2) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| L01 | fourth-37, fresh-62, hung-14 | +1 on hung-14, 0 elsewhere | — | −20 on fourth-37 | +1 | `judge_move` 0 times | kept |
| L02 | 5 moments | 0 | — | −20 on rapid-52 | −2 | `explore` 0 times | dropped |
| L03 | fourth-56 | +1 | +1 | 0 | +3 | `explore` twice | kept |
| L04 | fourth-37, fourth-38, hung-14 | +1 on hung-14 | — | −20, −16.7 | +1 | `explore` 0 times | kept |
| L05 | hung-25 | 0 | — | 0 | 0 | `explore` 0 times | dropped |
| L06 | hung-25, hung-68 | 0 | — | 0 | +1 | `facts` twice | dropped |
| L07 | fourth-56 | 0 | 0 | 0 | 0 | `facts` 0 times | dropped |

Every lesson reached its D runs (`start` lines: `lesson_ids`, digest; the prompt holds `## 상황별 전략`), but
in 11 of 13 D runs the agent never called the tool its lesson names. L01's and L04's gains come from one
pair a moment with the action never taken: the rule keeps them, and the owner decides (open question below)
whether a candidate whose action was never taken counts as one whose condition never held.

**Amendment A1 to the audit (RX2-D §5.1), the owner's decision (2026-11-06).** Two judges were flagged only
for their own scratch files: part 1 wrote and read `refs.txt` (its references, dumped) in its session's
scratchpad, part 2 read the app's file of its own long tool output (`tool-results/`). The audit now also
accepts a path in the judge's **own** scratchpad (`…/Temp/claude/<x>/<session id>/scratchpad/`) or its own
`tool-results/` (`…/.claude/projects/<x>/<session id>/tool-results/`), the session id read from the
exported transcript (`export_session_ids`, `own_dirs`); another session's, or anything else outside the
directory, still fails. `tests/agent/test_record.py`: the audit test.

**Open:** whether L01 and L04 are kept (their action never ran); then `lessons_v1` (`CHECKING`) from the
kept candidates, the set's check on Train (§4 step 3).
