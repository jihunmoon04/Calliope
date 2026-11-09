# Agent AF — tools v9 (analysis first), harness rev. 8, judge v2, Test 2's lifecycle

Status: rev. 7, step 2 — judge v2 on Test 1 (§11), A9, A10; review READY_WITH_CORRECTIONS (F1–F3) applied (§13); merged by the owner (PR #164, 2026-11-09); rev. 5 (the replay, A8) merged by the owner (PR #163, 2026-11-09); rev. 4 merged by the owner (PR #162, 2026-11-09); re-review of rev. 3: F1–F3 resolved, NOT_READY on F4, applied (§9); re-review of rev. 2 NOT_READY (F1, F2; F3) applied in rev. 3 (§8); independent review NOT_READY (F1, F2) applied in rev. 2 (§7). For re-review. Implements `agent-af-design.md` rev. 4 (merged, PR #161).
Branch `agent/af-implementation`.

## 0. The owner's answers (2026-11-09)

AF-D §8 Q1–Q8: **as recommended** — analysis first at game positions (Q1); the code frame check in
place of the model sentence check (Q2); four new games for Test 2 (Q3; being chosen, §6); the
freeze names `H@v9` (Q4); fixed word lists, missed frames over false holds (Q5); judge v2 with
`search_only` outside M1b and the M1s bar (Q6); T3's threshold, a kind or more than 1.00 (Q7); a
number without a stated source read as the analysis's (Q8).

## 1. What changed

| Part | Change | Where |
| --- | --- | --- |
| T1 | `explore` at a game position whose ply record is stored (`_cached`; never analysed here): moves that follow an analysis line answer its **`analysis_score`** (§2.2's fields) and no search; `continue_with` plays the rest of its PV (`source: "analysis"`, `analysis_ends_at`); `search: "fresh"` also searches the line's end; no moves give the `best` and `played` scores; moves that leave answer `departs_at` and v8's search. `end_score` is only ever a search (`source: "search"`, `depth`). | `session.explore`, `_explore_analysis`, `_analysis_at`, `_stored`, `_follow`, `_analysis_score` |
| T1 | `compare_lines`: the played and best lines carry `analysis_score`; the one search at the end of the given moves keeps `end_score_at` = their length (`source: "search"`); extension plies `search`. The ranking reads the analysis (`source: "analysis"`, no search) when every ranked move has a line in it, else v8's searches with `analysis_score` beside. | `compare_lines`, `_compared_line`, `_rank`, `_analysis_entry`, `_scored` |
| T2 | The ledger's `standing` (start, each ply's `standing_white`, end, `leader_at_end`) beside `net`; the note says `net` is not who is ahead. `compare_lines`' outcomes carry it. | `lines.standing_white`, `ledger`, `outcome` |
| T3 | `disagreement` (both sides' fields, White's view) wherever an `analysis_score` and an `end_score` meet; `disagrees_with_analysis` on a kind or more than 1.00; recorded as a `disagreement` line. | `lines.disagrees`, `session._disagreement`, `Recorder.disagreement` |
| J1 | Plies' origins: v9 writes an `origin` line per call that served an `x` handle (A1); v7/v8 runs restored from the serving call (`evidence.Run`). Judge v2's bundle gives each sentence its verified citations rendered in one form with their origin; `judge_v2.md` and its schema (`search_only`, kind `source`); the key records the judge; `checked_judgings` validates by the judging's own schema. | `Recorder.origin`, `tools/rx/evidence.py`, `judge.bundle(judge=…)`, `prompts/judge_v2*` |
| J1 | The report: M1s (`search_only` a 100), M1b + M1s, paired per set and on Test; the M1s bar (`M1S_CEILING` +2.0) in the quality gate. | `report.py` |
| H1 | Harness **rev. 8** (`harness_v4`, `harness_judge_v3`, `harness_frames_v1`), the default: the frame check by code (F1–F3) in place of the model sentence check, `uncheckable` where the mapping is not unique; holds, states, `frames` lines; the start line names `harness_frames`. | `tools/rx/frames.py`, `harness.py` (`FRAMES`, `Gate._frames`), `prompts/harness_v4.md`, `run._harness_info` |
| M1 | `TEST_SETS` (`test`, `test2`); `opened[set]` (Test 1's `test_opened` read as `opened["test"]`); `open-test --set`; `freeze_v2` (`for`, `judge`, `harness_frames`); one record opens one set; every command and run checked against its own set's freeze; a report holds one test set only. `TEST2` empty until chosen. | `manifest.py`, `freeze.py`, `__main__.py`, `report.py` |
| R1 | `python -m tools.rx server-worktree <tools>`: makes the worktree from its tag with the checkout's `core.autocrlf`, checks every reasoning data file equal in git at both commits byte for byte; `open-test` checks each frozen variant's worktree (`servers_problems`). | `tools/rx/servers.py`, `freeze.servers_problems` |
| — | `agent_tools_v9`, `agent_guidance_v14` (descriptions of `explore`, `compare_lines`, the registry entry; digest pinned); the runner's `v9` (repository) and `v8` (a worktree of the tag `agent-tools-v8`, §5). | `definitions.py`, `server.py`, `run.py` |

## 2. Amendments

| # | Amendment | Why |
| --- | --- | --- |
| A1 | The plies' origins are an **`origin` line** of the call (`ref`, `plies_origin`), not a field of the `handle` line. | The `x` handle is served inside `_explore` before the plies' sources are known, and the recorder writes a ref's `handle` line once: the same ref served again by another call (the same moves typed, or continued) may have other origins. |
| A2 | A ply of the game's own moves (`compare_lines`' `game` line) has the origin **`game`**, read as `analysis` by judge v2 (`evidence.foreign`). | §5.1 named three origins; the game's moves are neither the agent's nor a search's, and the reference holds them. |
| A3 | A judgement's evidence is the verified proposition and `origin: "analysis"`; its grade is read in the reference. A score's `depth` is given when the proposition carries it. | The judgement record is the analysis's, as the reference is; the handle line does not hold the record's grade or a search's depth. |
| A4 | "Another side favoured" (T3) is **opposite sides**: a score within ±0.30 against one just outside it is not a difference of side. | `favours`' band would otherwise flag 0.25 against 0.35. |
| A5 | F1/F2 are `uncheckable` when the sentence cites any `x` handle directly. `search_numbers` reads an `s` record without the analysis's `search` index as a session search's. | A cited `x` handle backs material per ply, so the count may be its; `detail` gives no source, and the analysis's lines carry `search`. |
| A7 | **Which games may be Test 2's** (owner, 2026-11-09). **Amends AF-D §7.4** ("played after Test 1 was opened") **and the framing's rule** (`agent-reflection-framing.md` §8.1: "games played after RX0 are new Test material"): a game of the owner's may be Test material when **no record of the project names it** — no number in the repository's tree or history, the manifest, a design document, a reference or a run — so no session can have read it. Its date is not the condition. Test 2's four (§6) and its reserves were checked: none of the seven numbers is in the tree or in any commit. | The owner: a game not written down anywhere was not seen, and what development read of the account (its metadata list on 2026-11-05) bears little on four games of it. The rule's aim — a set no session has read — is kept; the date was a stand-in for it. |
| A8 | **The frame check after the replay** (§10): `best`'s Korean name is not a grade word for F3 (`frames.NOT_GRADE_WORDS`), and F2 holds a segment written as the whole line only when it is a segment (`from` > 0 or `to` short of the line's length) and the whole line's change for that side, **from ply 0 to the end**, differs from the segment's. | The replay's ten false holds: nine F3 on "최선", the commentaries' noun for the best move ("엔진 최선수 28...fxg4는"), one F2 on plies 0–10 of an 11-ply line whose last ply changes no material. AF-D §4.1 sets the word lists from this development data. |
| A9 | **"물질 차이" for a change, counted, not held** (owner, 2026-11-09, §12 Q9 option 2). `harness_v4`'s facts message adds one example line — write a line's material as gained or lost ("흑이 4점을 잃는다") and who is ahead from `standing` ("흑이 1점 앞선다"); the frame check records a sentence that cites a material number with "물질 차이" or "물질은" and no standing word as **`ambiguous`** (on its `frames` line; the report's `frame_check.ambiguous`), and never holds it. Amends `harness_v4` and `harness_frames_v1` before any run used them. | Step 2 (§11): judge v2 reads these phrases as the standing and found about twenty such H sentences false that judge v1 had accepted. Holding them would add retries (rev. 5 and 6); the pilot shows whether the example line alone removes them, and a hold can follow before the freeze if it does not. |
| A10 | **Step 2's bar** (PR #164 review F3). **Amends AF-D §7.2 step 2:** in the constructed bundle each of the eleven is `search_only` **or `ok` where the reference holds nothing for what it states** (the rubric's own rule, as the as-written row already allows); judge v1's other wrong sentences are still `wrong`, a changed verdict on an **interpretation** sentence being recorded as a difference between judges, not a failure. | The bar as first written required what judge v2's rubric (§5.2) does not give: `B3NVPP` 38 #5's continuation lies past the reference's line, so `ok` is its verdict there; A's 186491823816-42 #6 is a reading. Both are in §11; judge v2 is unchanged. |
| A6 | R1's check runs in `server-worktree` and at `open-test` (`servers_problems`), not when a freeze record is written; the runner's `build_id` error is unchanged. | No command writes the freeze record (it is written by hand, as LT's was), and `base.json` holds the build's three parts, not each data file's digest, so the runner cannot name files; the worktree check can. |

## 3. Tests

New: `test_af.py` (T1–T3, origins recorded: 17), `test_af_judge.py` (origins restored, evidence,
the v2 bundle and schema, M1s and its bar, origins as of each submission, Test 2's judge: 14), `test_af_harness.py` (F1–F3, `uncheckable`, the
loop's holds and states, rev. 8's start line: 13), `test_af_sets.py` (`freeze_v2`, `opened[set]`,
one record one set, Test 2's runs and report, the worktree check and command, Test 2's games and freeze: 14). Changed for v9:
the guidance pin (v14), the ledger's keys (`standing`), `engine` → `search` sources, the runner's
`v9`/`v8` roots, revision 7 pinned where LT's tests assume it, the worktree check stubbed where
LT's open-test tests have no worktrees.

## 4. The whole suite

WSL, this packet's code: **2055 passed, 27 skipped**; 5 failed and 2 errors. Five are the known ones of this environment: the digest golden (`test_the_full_view_is_todays_answer_field_for_field`, the Linux engine build) and the four `test_calibrate_curve` tests (`zstd`). Two were this packet's: `test_engine_score_and_engine_line` and `test_a_session_through_the_client` took a session search's lines from `explore(search=true)` at a stored game position, which v9 answers from the analysis (T1); they now ask `search: "fresh"`, and pass. `ruff check` clean.

`test_identities_are_equal_across_stockfish_sessions` failed in one run of this packet's tests and passed in the whole suite; it fails the same way on `main` (231ca97) here — two Stockfish sessions through WSL's interop are not always equal — so it is this environment's, not v9's.

**Again at rev. 3** (HEAD `919715e`): **2067 passed, 27 skipped**; 3 failed and 2 errors, all the known ones above (the digest golden; the four `zstd` tests). `ruff check` clean.

## 5. Before the measurement

1. **Tag `agent-tools-v8`** at `231ca97` (main before this packet merges), as LT tagged v7: only
   needed if a v8 variant is ever run again; AF's variants are `A@v7`, `A@v9`, `H@v9`.
2. **AF-D §7.2 step 1, the replay** (no model): the eleven cases on v9, and the frame check over Test
   1's and the evaluation sample's final sentences (false holds at most 2%).
3. **Step 2**: Test 1's commentaries judged with judge v2, beside the constructed bundle.
4. **Step 3**: the pilot (`H@v9`, one run a game on the development sample).
5. Test 2's games chosen by the owner (§6), then the freeze (`freeze_v2`, `for: "test2"`,
   `judge: "judge_v2"`), `server-worktree v7`, `open-test --set test2`.

## 6. Test 2's games

Chosen by the owner (2026-11-09) from a proposal made in a separate session by metadata only — the
account's public archives (191 games from 2026-09 on), no game's moves printed, saved or read; rules:
rapid 10-minute, rated, ending in mate or resignation, 40 plies or more, the owner's present rating,
the earlier sets and reserves left out, two as White and two as Black, two won and two lost (A7 for
the date).

| Game | Date | Owner | Result | Ending | Plies | Owner's rating | Opening (header) |
| --- | --- | --- | --- | --- | ---: | ---: | --- |
| 186148834544 | 2026-10-29 | White | won | resignation | 77 | 828 | Philidor Defense 3.Bc4 |
| 186141458686 | 2026-10-29 | Black | won | resignation | 61 | 820 | Scandinavian, Modern 3.Nf3 Qxd5 4.Nc3 Qa5 |
| 186508597164 | 2026-11-04 | White | lost | resignation | 52 | 804 | King's Pawn, King's Knight Variation |
| 186014364656 | 2026-10-27 | Black | lost | checkmate | 65 | 812 | Scandinavian Defense 2.e5 |

Reserves: 185790829982 (White, won, mate), 185920835778 (Black, lost, mate), 185573762490 (White,
lost, mate). `manifest.TEST2` holds the four. Their PGNs were fetched from the public archives into
the data directory (2026-11-09; the fetch printed only each file's size and the White/Black, Result
and Termination headers, which agree with the table) and their digests recorded in the manifest
(`python -m tools.rx manifest --sets test2`: `uci_sha256` only). Moments, base and references only at
`open-test --set test2`, after the freeze.

## 7. Review (rev. 1 → rev. 2)

Independent review (PR #162, HEAD `bb860cf`): **NOT_READY**, two blocking findings, both confirmed
in the code and applied.

| # | Finding | Applied |
| --- | --- | --- |
| F1 (P1) | `evidence.Run` kept each ref's **last** `origin` line, so a commentary citing `x17` when it was the analysis's would be judged by `x17`'s origin from a later call (A1 says one ref may be served with other origins). The v7/v8 restoration had the same fault: it read only the call named on the ref's one `handle` line. | `Run.timeline`: every serving of a ref in the run's order — v9's `origin` lines, or (v7/v8) every `explore`/`compare_lines` call whose answer served it (`_served`); `plies_origin(ref, before)` and `origin(ref, before)` take the last serving **before the submission's `seq`**; `evidence` passes each final submission's `seq`. Test: one ref served twice with other origins, a submission after each, on v9 and v8 records. |
| F2 (P1) | Test 2's judge was not enforced: `open_test` took a `freeze_v1` for `test2`; `bundle` defaulted to judge_v1 whatever the freeze named; the report read M1s from any judging. | `freeze.REQUIRED`: Test 2 opens only with a `freeze_v2` for it naming `judge_v2` (`required_problems`, in `open_test`); `freeze.frozen_judge(set)` reads the judge from the set's own opening record; `bundle` refuses runs of a test set with another judge, and the report refuses a test set's judging whose key names another judge. Tests: both refusals, `freeze_v1` and `judge_v1` refused for Test 2. |

## 8. Re-review (rev. 2 → rev. 3)

Re-review (PR #162, HEAD `b11ba98`): rev. 2's F1 and F2 in the code; **NOT_READY** on two new
blocking findings and one other, each confirmed in the code and applied.

| # | Finding | Applied |
| --- | --- | --- |
| F1 (P1) | `_stored` dropped `best` by rank when the played move is the best, so no moves gave only `played`, and `search: "fresh"` compared nothing (`scores.get("best")` empty). | `_stored` keeps **`roles`** (`best`, `played`) by role, both kept when they share a rank; `lines` stay one a rank for following and ranking. No moves read the roles; `_follow` takes the best line by role. Test: the played move made the best — both scores, and `fresh` compares with `best`. |
| F2 (P1) | `compare_lines`' `searched.ref` (the given moves' own `x`, before the extension) had no `origin` line, and judge v2's `Run` used no restoration once a run held any `origin` line: a citation of it would be `unknown`. The same held for `explore`'s first answer before `continue_with`. | `_compared_line` records the searched handle's origins (the given moves') before extending, and `explore` its first answer's before continuing. `evidence.Run` restores from the serving calls every ref that has no recorded `origin` line, in a v9 run too; a recorded line stands over a restored one. Tests: both handles recorded with their own plies; a v9 run's `searched.ref` without its line restored, not `unknown`. |
| F3 (P2) | A negated frame ("백이 9점 앞서지는 않는다", "블런더가 아니다") would be held. | `frames.NEGATIONS` (않, 아니, 못, 없, 말고): a sentence with a negation and a frame word is `uncheckable` for that rule, never held. Test for F1 and F3. The 2% false-hold bar is measured, as AF-D §7.2 step 1 says, by the replay over Test 1's and the evaluation sample's final sentences on v9's records, after this packet merges (§5 step 2): those runs' `x` records are v8's, without `standing`, so F1 cannot be replayed on them as they are. |

## 9. Re-review (rev. 3 → rev. 4)

Re-review (PR #162, HEAD `9e002b7`): F1–F3 resolved (F3's sentence-wide negation noted as the
intended conservative rule); **NOT_READY** on one new blocking finding, confirmed and applied.

| # | Finding | Applied |
| --- | --- | --- |
| F4 (P1) | `explore(moves=[m], search="fresh", continue_with="engine")` on an analysis line whose PV ends the game: `_explore_analysis` asked `_explore` for a search at the finished end, which `_admit_search` refuses, so the call failed instead of answering. | `_explore_analysis` plays the moves and the PV's rest on a board first; a finished end is not searched (`fresh` is dropped there), and the answer gives its terminal value as LT-D §2 does (`search: {"terminal": …}`, `end_score` the terminal score) beside the `analysis_score`, with no `disagreement`. Test: 2.g4 typed, the analysis PV's 2...Qh4# appended, `fresh` and `continue_with`: no search admitted, the terminal value, `analysis_ends_at`, the plies' sources. (A move that mates at once already took the terminal path before the analysis.) |

## 10. The replay (AF-D §7.2 step 1)

No model; v9 at `main` after PR #162. Scripts and outputs in `rx-evidence/af/`: `replay_cases.py` →
`af-replay-cases.json`, `replay_frames.py` → `af-replay-frames.json`.

### 10.1 (a) The eleven cases on v9

Each case's call — the one that served the cited line or score, read from the run's records — made
again on v9 in a session on a copy of Test 1's sealed base.

| Case (§0.1) | The call | v9's answer | The reference |
| --- | --- | --- | --- |
| 186491823816-50 ×5 (`TRH87V` #3 #7, `Y2ZKYK` #3 #4, `827V6J` #2) | `explore` 25...Rxf7, `continue_with` | 25...Rxf7 26.Rxf7 **Rg5** 27.Rxb7 Rf5 28.Rxf5 c5 29.Rxg7 cxb4, plies `analysis`; `analysis_score` played, **+6.72** | played +6.72, the same PV |
| 186437361608-38 (`FJ3HFV` #3) | `explore` 19...Nxb5, `continue_with` | the best line 19...Nxb5 20.a4 Nxc3 21.a5 Ne7 22.Bb2 Ned5 23.Bxc3 Nxc3; **−8.01** | best −8.01, the same PV |
| 186203030416-38 (`B3NVPP` #5) | `explore` 19...Be3+ 20.Kb1 Rxc2 21.Kxc2, `continue_with` | the agent's four moves on the played line, then 21...g6, `analysis_ends_at` 5 (no …Bxh2); **−3.63** | played −3.63, ends 21...g6 |
| 186437361608-72 ×2 (`7SRK7C` #6, `XK6CCH` #4) | `explore` 36...Rxd6+, `continue_with` | the played line to 39...a5, **+5.18** | played +5.18 |
| 186437361608-72 (`7SRK7C` #8) | `compare_lines` 72, candidates Rb2, Rc2+, a5 | the ranking **from the analysis** (no search): Rb2 **−6.80**, Rc2+ −6.40, a5 −6.29, Rxd6+ +5.18 | the same four scores |
| 186203030416-38 (`B3NVPP` #6) | `explore` from **ply 37** (19.Bd5 Be3+), `continue_with` | ply 37's played line (19.Bd5 Be3+ 20.Kb1 Rxc2 21.Kxc2 f5 …), `analysis_score` **−4.77** for 19.Bd5 | ply 38's played line, −3.63 for 19...Be3+ |

**Bar (11 of 11 the analysis record's line and score, or `departs_at`): met.** Ten give the
reference's line and score exactly. The eleventh is the analysis too, but ply 37's record: the agent
started its line at ply 37's position (the move before the moment), and §2.1 answers a line by the
record whose root is its start — ply 37's, whose evaluation of 19.Bd5 is −4.77; the moment's own
record (ply 38's, the reference's) evaluates 19...Be3+ at −3.63. That is the rule as designed, and
the answer says which record it read (`root_ply` 37, `evaluated_move` 19.Bd5); a sentence about ply
38's move needs ply 38's record, which the agent gets by starting there. The harness's message
(`harness_v4`) does not say so; the pilot shows whether agents start lines a ply early.

### 10.2 (b) The frame check over the final sentences

Every final sentence of Test 1's judging (`0dd8fe79`, A 216, H 237) and the evaluation sample's
HS rev. 4 judging (`33814b65`, A 313, H 421), against the judge's verdicts. Arm A never runs the
check; its sentences count for the false-hold rate only. The runs are v7/v8's, so each record is
rebuilt as v9 serves it from the run's own records and the board (a line's `standing` from its
moves, each ply's source restored as of the submission by `evidence.Run`; a judgement's grade from
the run's own `ply` answer; never the judge's or the reference's verdicts); 24 material numbers backed by a cited handle and other non-unique mappings are
`uncheckable`, as §4.1 says.

**As implemented (PR #162), before A8:**

| | Test 1 A | Test 1 H | Evaluation A | Evaluation H | All |
| --- | ---: | ---: | ---: | ---: | ---: |
| `ok` sentences | 210 | 190 | 299 | 370 | 1,069 |
| held and `ok` (false holds) | 0 | 2 | 6 | 2 | **10 (0.94%)** |
| held and `wrong` | 0 | 2 | 0 | 0 | 2 |

**Bar (false holds at most 2% of the `ok` sentences): met**, pooled (0.94%) and for H (4 of 560,
0.71%); A on the evaluation sample alone is 6 of 299 (2.01%). Nine of the ten are F3 on "최선" as
a noun, one F2 on a segment whose line changes no more material (A8).

**After A8** (the same sentences, so in-sample, not independent evidence): no false hold in any of
the four; three wrong sentences held — Test 1's 186492056006-22 #2 and #3 (F1: the change written as
the standing, AF-D §0.1 row 3) and the evaluation sample's `rapid-52` #4 (F3: "판정은 … 실수", the
cited judgement a blunder — LT-D §0.2's grade case). `uncheckable`: 24 material numbers backed by a
cited handle, 10 negated sentences, 3 sentences with two counts or two material propositions, 3 with
two grade words. `search_numbers` (sentences with a number cited from a session search — a `material` count by its own
segment's plies, any other cited line by all of its plies, or a session search's score): Test 1 H 75
of 237 and A 3 of 216 (v8's lines continued by a search counted), the evaluation sample H 44 of 421 and A 19 of
313 (its runs are v7's: no continuation, every typed ply the agent's) — the numbers T1 now answers
from the analysis.

**What the replay does not show:** whether agents on v9 quote the analysis's scores, start lines at
the moment's own ply, and state a separate search when they use one — the pilot's (§5 step 4) and
Test 2's to show.

### 10.3 Review of the replay (PR #163)

Independent review (HEAD `be50cbb`): **NOT_READY**, one blocking finding and one other, both
confirmed and applied; the replay rerun.

| # | Finding | Applied |
| --- | --- | --- |
| F1 (P1) | A8's F2 measured the whole line's change from the **segment's** start (`standing(to_end) − standing(from)`), so plies 1–2's +3 written as the whole line on 0 → +2 → +5 → +3 was held though the whole line is +3 too; and `end < length` alone let a segment that ends at the line's end but starts after ply 0 pass unchecked. | `frames._material_rules`: the whole line's change from ply 0 (`standing(length) − standing(0)`), a segment being `from > 0 or to < length`. Tests: both cases. The replay's holds are unchanged (none of its sentences was such a segment). |
| F2 (P2) | `replay_frames.py` rebuilt every ply as `agent`, so a number cited from a v8 line continued by a session search was not counted in `search_numbers`. | The replay takes each ply's source from `evidence.Run` as of the submission. Test 1 H's `search_numbers` 30 → 77 (→ 75 after the re-review's F3); the evaluation sample's unchanged (v7 runs). A test that a count from a line with search plies is a search number. |

Re-review (HEAD `00472dc`): F1 and F2 resolved; **READY_WITH_CORRECTIONS**, one finding, applied.

| # | Finding | Applied |
| --- | --- | --- |
| F3 (P2) | `search_numbers` counted a cited `material` count as a search's when its line had a search ply anywhere, even after the count's segment (plies 0–2's +9 with only ply 3 from a search). | `frames._search_backed`: a `material` count by its own segment's plies (`from`+1 to `to`); any other cited line still by all its plies. Test 1 H's `search_numbers` 77 → **75**. Test: a search ply after the segment is not counted, one inside it is. |

## 11. Step 2: judge v2 on Test 1 (AF-D §7.2 step 2)

**Bundles.** `b2e612ac`: Test 1's 69 commentaries (24 runs, judging `0dd8fe79`'s), two parts,
judge v2; every one of the 453 sentences has evidence (origins: analysis 1,030, search 151, agent
8). Building it found one origin the code did not know: an `x` line served by a `ply` answer — the
digest's same-reply line (`by: "calliope"`, AG8-D §5), built from the analysis and held by the
reference — now `analysis` (`evidence.Run.plies_origin`; test). `a82bb35a-src`: the seven
commentaries holding AF-D §0.1's eleven sentences, each of the eleven rewritten to state its source
("별도 탐색으로 이어 둔 수순에서는 …", "별도 탐색에서 …"), numbers, citations and evidence unchanged
(`constructed_bundle.py`). Three fresh judge sessions, one a part.

**Audits.** Part 2 and the constructed part passed. Part 1 was flagged on two calls — one command
run twice in its own directory, discarding one run's output with `> /dev/null` — **accepted by the
owner as a false positive** (2026-11-09, `owner_decision` in `audit-part01.json`, the flags kept),
before any join. The judgings, bundles, keys and audits are in `rx-evidence/af/judging-*`;
`step2.py` → `af-step2.json`.

**The bar** (it checks the rubric, not the agent):

| | Result |
| --- | --- |
| The eleven as written: `wrong` (`source`), or `ok` where the reference holds nothing | **11 of 11** |
| The eleven, constructed: `search_only` | **10 of 11**; the eleventh (`B3NVPP` 38 #5, the …Bxh2 continuation) `ok` — the reference's line ends at 21...g6, so it holds nothing for that line, and the rubric's own rule makes a sentence that states its search and is true of it `ok` there. The bar should have allowed `ok` as the as-written row does. |
| judge v1's other wrong sentences still `wrong` | **7 of 8**; A's 186491823816-42 #6 (an interpretation: Black "gave up the queen first … the turning point") now `ok` — a difference between two judges on a reading. |

**What else changed** (every verdict that changed is in `af-step2.json` with the judge's reason):

| | judge v1 | judge v2 |
| --- | --- | --- |
| A (216 sentences) | ok 210, wrong 4, doubtful 2 | ok 211, wrong 4, doubtful 1 |
| H (237 sentences) | ok 190, wrong 15, doubtful 32 | ok 176, **wrong 56**, doubtful 2, search_only 3 |

H's 41 new `wrong` are of two kinds:

- **`source`, 19** (17 of them `doubtful` before): an end score from the agent's own search stated
  as "the line's end score" with no source ("그 라인 끝의 평가 -7.91", the analysis −8.01) — AF-D
  §5.2's reading (Q8) doing what it was set to do; v9 (T1) answers these from the analysis.
- **A material change written as the standing, about 20** (kind `other`, 16 of them `ok` before):
  sentences like "이 라인의 백 물질 차이는 -4입니다" or "두 수째 물질 차이는 -2가 됩니다" citing a
  `material` proposition — a change from the line's start. With the evidence's standing after each
  ply in front of it, judge v2 reads "물질 차이 X" / "물질은 X" as the standing and finds it false
  (−1, not −4); judge v1 took it as the change. Korean "물질 차이" plainly reads as the balance, so
  judge v2's reading is the natural one, but the sentences are ambiguous rather than plainly false.
  The frame check holds none of them: "물질 차이는" and "물질은" are not standing words (§4.1), and
  most cite one count.

**What it means for Test 2.** Judge v2 will read H's commentaries this way on Test 2. If H on v9
still writes "물질 차이 X" for a change, M1b counts it, though T1 and the ledger's `standing` now
give the agent both numbers. Two remedies before the pilot, both in the harness, neither in the
judge (§12 Q9).

## 12. Questions for the owner (step 2)

| # | Question | Recommendation |
| --- | --- | --- |
| Q9 | "백의 물질 차이는 -4" for a change: accept judge v2's reading (the standing), and close the gap on H's side before the pilot? | Recommended at first: the example line and the phrases as F1 standing words (held). **Answered by the owner (2026-11-09): the gentlest way** — the example line in `harness_v4` and the phrases **counted, not held** (A9); judge v2 unchanged. |
| Q10 | The constructed bar's eleventh `ok`, and A's interpretation sentence now `ok`? | Recommended: the rubric's own rule and a judges' difference; neither changes judge v2. **The owner (2026-11-09):** on A's sentence ("… 이 장면이 이 대국의 분수령이다", 186491823816-42 #6) judge v1's reading is the better one — in the game White took the queen first, Black took White's back and stood better (−1.49), so "the game's turning point" does not hold — but it bears little on the measurement; recorded as a judges' difference, judge v2 unchanged. The constructed `ok` raised no objection. |

**A9's baseline** (the replay's `replay_frames.py`, now also against judge v2's Test 1 judging):
sentences that cite a material number with "물질 차이" or "물질은", write that number (a count equal to
the cited `material` proposition's, or with a cited `x` handle any count; PR #164 F1) and no standing
word — Test 1 H **26 of 237**, A 3 of 216; the evaluation sample H 6 of 421, A 2 of 313. Judge v2 marked **23 of
H's 26 `wrong`** (judge v1: 3), A's 3 none: the count follows what judge v2 flags. Holds and false
holds unchanged (none). The pilot reads the same count on v9 with `harness_v4`'s example line.

## 13. Review of step 2 (PR #164)

Independent review (HEAD `404ebe6`): the judge v2 results and their data agree; **READY_WITH_CORRECTIONS**,
three findings, applied.

| # | Finding | Applied |
| --- | --- | --- |
| F1 (P2) | A9's `ambiguous` counted a sentence with the phrase and a cited material proposition whether or not it wrote a number ("이 라인의 물질 차이는 아직 확인되지 않았다"). | Counted only when the sentence writes a count equal to a cited `material` proposition's (or, with a cited `x` handle, any count). Tests: no number, and another number, not counted. The replay: Test 1 unchanged (26), the evaluation sample's H 21 → 6. |
| F2 (P2) | An `exhausted` moment's last call — sent after two holds — was not checked, and `frame_counts` read `passed` lines only, so the worst commentaries fell out of A9's count. | The last call of an exhausted moment is checked **passively**: its `frames` line holds `unsent_holds` (what would have been held), `uncheckable`, `ambiguous`, `search_numbers`; it is sent as before. `frame_counts` reads `passed` and `exhausted` and reports the moments in each state and the unsent holds. Test: two holds, then the third call checked, counted and sent. |
| F3 (P2) | Step 2's bar as AF-D wrote it (each constructed sentence `search_only`, every other wrong sentence still `wrong`) and the two recorded exceptions disagreed. | A10 amends the bar to what the rubric gives: `ok` where the reference holds nothing; an interpretation's changed verdict a difference between judges. Q10 answered by the owner (§12). |

