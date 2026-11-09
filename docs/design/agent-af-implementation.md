# Agent AF — tools v9 (analysis first), harness rev. 8, judge v2, Test 2's lifecycle

Status: rev. 1, for independent review. Implements `agent-af-design.md` rev. 4 (merged, PR #161).
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
| A6 | R1's check runs in `server-worktree` and at `open-test` (`servers_problems`), not when a freeze record is written; the runner's `build_id` error is unchanged. | No command writes the freeze record (it is written by hand, as LT's was), and `base.json` holds the build's three parts, not each data file's digest, so the runner cannot name files; the worktree check can. |

## 3. Tests

New: `test_af.py` (T1–T3, origins recorded: 17), `test_af_judge.py` (origins restored, evidence,
the v2 bundle and schema, M1s and its bar: 11), `test_af_harness.py` (F1–F3, `uncheckable`, the
loop's holds and states, rev. 8's start line: 13), `test_af_sets.py` (`freeze_v2`, `opened[set]`,
one record one set, Test 2's runs and report, the worktree check and command: 11). Changed for v9:
the guidance pin (v14), the ledger's keys (`standing`), `engine` → `search` sources, the runner's
`v9`/`v8` roots, revision 7 pinned where LT's tests assume it, the worktree check stubbed where
LT's open-test tests have no worktrees.

## 4. The whole suite

WSL, this packet's code: **2055 passed, 27 skipped**; 5 failed and 2 errors. Five are the known ones of this environment: the digest golden (`test_the_full_view_is_todays_answer_field_for_field`, the Linux engine build) and the four `test_calibrate_curve` tests (`zstd`). Two were this packet's: `test_engine_score_and_engine_line` and `test_a_session_through_the_client` took a session search's lines from `explore(search=true)` at a stored game position, which v9 answers from the analysis (T1); they now ask `search: "fresh"`, and pass. `ruff check` clean.

`test_identities_are_equal_across_stockfish_sessions` failed in one run of this packet's tests and passed in the whole suite; it fails the same way on `main` (231ca97) here — two Stockfish sessions through WSL's interop are not always equal — so it is this environment's, not v9's.

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
