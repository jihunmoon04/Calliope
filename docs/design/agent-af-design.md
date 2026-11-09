# Agent AF-D — analysis first: one engine record per game position, and sentences framed by their record

Status: rev. 1, draft for independent review. Scope: the agent's MCP tools (`src/calliope/agent`:
`explore`, `compare_lines`, the line ledger), the staged harness of the RX runner
(`tools/rx/harness.py`, its prompts), and the runner and report for a second Test set (`tools/rx`).
Not in scope: the guide (`commentary_ko_v8`, frozen for RX), `submit_commentary`'s server checks,
the judge (`judge_v1`), HIMARI.

## 0. Why

LT (`agent-lt-implementation.md` §16) measured `H@v8` (line tools v8, harness rev. 7) against
`A@v7` on Test: **not adopted** — M2b **+0.083 (−0.167 … +0.333)**, M1b **+4.57 (+0.89 …
+8.48)**, three moment-runs without commentary. H wrote 15 wrong sentences against A's 4, and 32
doubtful against 2. HS rev. 4 had failed on the same bar (M1b +2.24, upper bound +5.69). Each
revision since HS rev. 4 aimed at H's wrong sentences, and none brought them down.

### 0.1 What H's 15 wrong sentences on Test cited

LT §16 sorted the 15 by what the sentence says. This design reads them **from the run records**: for
each wrong sentence, its submission (`tools.jsonl`, the `submission` line the bundle key's `seq`
names), the propositions it cites as the server verified them, and the `explore` call behind each
cited line. (Script and output kept outside git with the runs; the table names each run.)

| What the sentence's number is true of | Wrong | Cases (game-ply, run) |
| --- | --- | --- |
| **A line from the session's own search**, where the reference holds the analysis record's line | **7** | 186491823816-50 ×5 (runs `TRH87V` #3 #7, `Y2ZKYK` #3 #4, `827V6J` #2): all cite a `material` proposition over plies 0–9 of an `explore` of the played move 25...Rxf7 with `continue_with: "engine"`. The session's search after it plays 26.Rxf7 **d4** 27.Rxb7 dxc3 — Black −4, true of that line; the analysis record (and the reference) plays 26.Rxf7 **Rg5** 27.Rxb7 … 28.Rxf5 — Black −10. 186437361608-38 (`FJ3HFV` #3): 19...Nxb5 continued by a session search, net 0; the reference's line, +4 for Black. 186203030416-38 (`B3NVPP` #5): the agent's four moves, then a session search that reaches …Bxh2 (−5); the reference's line ends 21.Kxc2 g6. |
| **A score from the session's own search**, where the reference holds the analysis record's score | **4** | 186437361608-72 ×3 (`7SRK7C` #6 #8, `XK6CCH` #4): +6.39 and −4.78 from session searches (`s121`, `s126`, `s138`) against +5.18 and −6.80. 186203030416-38 (`B3NVPP` #6): "the engine's evaluation after the move, −4.59", an `engine_score` of a session search **at depth 12**; the record holds −3.63. |
| **A change in material, written as the standing** | 2 | 186492056006-22 (`0XS8VZ` #2 #3): each cites a `material` proposition over plies 0–2 (White +9, White +4) and writes "White is 9 ahead", "White is 4 ahead"; Black is still ahead at ply 2 (by 1 and by 6). #2 also says "over the whole line" of a 16-ply line. |
| A grade named against the cited judgement | 1 | 186203030416-38 (`B3NVPP` #2): "a blunder" for 19...Be3+, the reference's best move. |
| An inference | 1 | 186491823816-43 (`827V6J` #1): "takes the queen, but it was already attacked, so nothing is gained". |

**Eleven of the fifteen are true of the record they cite.** The server verified every number of
them (`sentences.check_token` against the cited propositions; the `material` proposition's balance
recomputed by `material_flow`), and the harness's checker agreed with the claims. What makes them
wrong is that the line or the score comes from **another search of the same position** than the one
the references hold. LT §16 read the seven line cases as "a line's material, misread" and "a line's
outcome stated for another line"; the records show the agent read its line correctly — the line was
the session's.

The replay of the evaluation sample had already found this class (`agent-lt-implementation.md`
§9.3, "another record, another search"): three of Validation's nine wrong sentences of H. A barely
explores (v7 has no `continue_with`), which is why its wrong sentences are few.

### 0.2 Why two searches answer the same position

A game position has **two engine records** once the agent explores it:

- **The analysis record** of the ply (`ply`, the digest; `session._serve_analysis`): the subject's
  judgement with its played, best and alternative lines, each with its PV, score and depth, served
  as `s` handles. The references are built from it (RX2-D §4), and it is what the product shows a
  user for that move.
- **The session's searches** (`session._search`): `explore` with `search: true`, its
  `continue_with: "engine"` (LT-D §2: the end search's PV), and `compare_lines`' `ranking` (LT-D §3:
  one search after each ranked move). These are new searches in the fact engine's own store, often
  shallower (depth 12 at 186203030416-38) and with another PV.

The tools answer both, label neither as "the analysis" or "a new search" in the sentence's terms,
and the agent quotes whichever it read last. A commentary that says "the engine's evaluation after
the move is −4.59" while the analysis shown beside it says −3.63 contradicts the product, whatever
the judge holds.

### 0.3 Why this direction

| Option | Against it |
| --- | --- |
| Count these as right (change M1b) | Half of the problem is real: the session's shallow line (26...d4) is a worse account of the position than the analysis's (26...Rg5), and a commentary quoting it disagrees with the analysis the product shows. Changing what the judge counts would hide it. |
| Forbid digits and line outcomes in sentences | H's M2b gain is a line's outcome (LT-D §0.3). |
| Another model check of the sentences | Rev. 5–7's sentence check (a model reading the sentences against the claims) held right sentences on digits (rev. 5), exhausted moments on `unbacked` (rev. 6), and in rev. 7 did not sort wrong from right: the moments it passed clean had the **higher** wrong-sentence rate (M1b 12.2 against 1.5 for `passed_with_unbacked`). It cannot see the problem: the claims it reads agree with their records. |
| **One engine record per game position, and a code check of how a sentence frames a cited number** | **Chosen.** Where the analysis holds a position or a line, every tool answers from it; a session search answers only past it and says so. The two misframings left (a change as a standing, a segment as the whole line) and a grade named against its judgement are checked by code against the cited propositions. Neither reads the references. |

## 1. The change

| Part | What |
| --- | --- |
| T1 | **Analysis first.** At a game position, `explore`'s end score and `continue_with`, and `compare_lines`' ranking, answer from the analysis record wherever it holds the line; a session search answers only past the analysis's lines. Every score and every appended ply says its **source** (`analysis` or `search`) and depth. |
| T2 | **The ledger's standing.** Beside `net` (the change since the line's start), the material **standing** at the line's start, after each ply and at the end; the note says which is which. |
| H1 | **Harness rev. 8: the frame check** (code) at submission, in place of the model sentence check: a sentence is held when its words state a cited material change as a standing, a cited segment as the whole line, or a grade other than the cited judgement's. |
| R1 | A `build_id` mismatch names the data files whose digests differ; the v7 server's worktree is checked out with the repository's line endings (LT §16's three failed `A@v7` runs). |
| M1 | A **second Test set** (`test2`, four new games) for the blind measurement (RX0-D §2: a later candidate is measured only on new Test games). |

## 2. T1 — analysis first

### 2.1 The analysis's lines at a position

For a game position — ply *N*'s position before its move, which is ply *N−1*'s after — the
**analysis lines** are the lines of the analysis record **whose root is that position**: ply *N*'s
subject judgement's played, best and alternative lines (their PVs, scores and depths, as
`_serve_analysis` serves them). The record is read as `ply` reads it (from the sealed base: free, no
search admitted). A position off the game's line (inside an explored line) has no analysis lines.

One record per position, by its root: a line that starts with ply *N*'s move is ply *N*'s line,
never ply *N+1*'s root search of the position after it (LT §9.3: `fourth-56`, −3.95 from ply 57's
record against −5.09 from ply 56's).

### 2.2 `explore`

`explore(game, position, moves, search, continue_with, length)`, `position` a game position:

- **The agent's moves follow an analysis line** when they are a prefix of one (the first such line in
  the order played, best, alternatives). Then:
  - with `search: true`, `end_score` is **that line's score** (`source: "analysis"`, its depth and
    its `s` handle as `score_ref`), and no search is admitted. Before v9 this was a new search after
    the agent's last move.
  - with `continue_with: "engine"`, the appended plies are **the rest of that line's PV**
    (`source: "analysis"`), up to `length`. Where the PV ends before `length`, the answer says so
    (`analysis_ends_at`) and appends nothing more: no search continues an analysis line.
- **The agent's moves leave every analysis line** (or the position is off the game's line): v8's
  behaviour, with every appended ply `source: "search"` and `end_score` `source: "search"` with the
  search's depth. `departs_at` names the first ply where the moves left the longest analysis line they
  followed, and that line's move there ("the analysis plays 26...Rg5 here").
- `search: true` with no moves at a game position: the analysis record's root score
  (`source: "analysis"`).

The ledger's per-ply `source` (LT-D §2: `agent` | `engine`) becomes `agent` | `analysis` |
`search`. The `x` handle's record holds the sources; an `explored_line` proposition backs the moves
as today.

### 2.3 `compare_lines`

`lines` (played, best) start from the analysis's PVs, but TO-D §3 extends them by a session search
and scores each at its end by one (`end_score`, `end_score_at`). In v9 a line's `end_score` is **the
analysis line's score** (`source: "analysis"`) while the line is that PV; an extension past the PV
stays a session search, its plies `source: "search"` and its score marked so, beside the analysis
score, never in its place. The **ranking** (LT-D §3) is one source, never mixed (TO-D §3 N2):

- **When every ranked move has an analysis line at the position** (the played move, the best and
  candidates among the alternatives): ranked by the **analysis lines' scores**, turned for the mover
  as v8 does, `source: "analysis"`. These scores are one search's multi-PV, which makes them a fairer
  ranking than six separate searches. No search is admitted.
- **Otherwise:** v8's ranking (one session search after each move), `source: "search"`, and each
  entry with an analysis line also shows that line's score as `analysis_score` beside it, never
  ranked with the others.

The `k` record holds the source; the checker (LT-D §5.2) reads `better_for_mover` claims from
whichever ranking was served.

### 2.4 What the replay of 0.1 must show

For the eleven cases of the first two rows, the same calls (same game, position, moves and options)
answered by v9 give **the analysis record's line and score**, which are the reference's — or say
`departs_at` where the agent's own moves left the analysis (186203030416-38 #5: the four typed
moves follow the analysis line, then `analysis_ends_at` after 21...g6 instead of a search reaching
…Bxh2). §6.2 step 1 makes this the bar.

## 3. T2 — the ledger's standing

LT-D §2's `net` counts material **from the line's start** (`material_balance_white` at the end, per
side). Its note says "+ = ahead", which invites reading a change as a standing (0.1, row 3). v9 adds,
from the same records:

```json
"standing": {"start": {"white_minus_black": -10}, "end": {"white_minus_black": -1},
             "leader_at_end": "black"},
"plies": [{"ply": 1, "san": "11...Qe5+", "...": "...", "standing_white": -10}, ...]
```

- `standing.start` is the material balance at the line's start (the `points_v1` count of the start
  position, White minus Black); `standing.end` the same at the end; `net.white` = end − start (a test
  pins it). `leader_at_end` is `white`, `black` or `level`.
- Every ply carries `standing_white` after it, so "at ply 9" is read, not counted.
- The note becomes: "net: what each side gained (+) or lost (−) since the line's start — not who is
  ahead; standing: who is ahead, White minus Black, at the start, after each ply and at the end".
- `compare_lines`' line outcomes carry `standing` too (not the per-ply list).

## 4. H1 — harness rev. 8: the frame check

### 4.1 What it checks

Code in `tools/rx/harness.py` (`frames`), run on each `submit_commentary` call the gate lets through
(after `normalized`, HS rev. 4 A3), in the place of rev. 7's sentence check. For each sentence, from
the propositions it cites (their fields in the call's `propositions`, and for a cited handle, its
record through the harness's `detail`):

| Rule | Holds a sentence when | The reply names |
| --- | --- | --- |
| **F1 change as standing** | it cites a `material` proposition (a change from ply `from` to `to`), writes that proposition's number with a **standing word**, and the standing at `to` is not the change (the line did not start level) | the change, and the standing at `to` from the ledger: "pm21 is White's gain over plies 0–2 (+9); after ply 2 Black still leads by 1" |
| **F2 segment as whole** | it writes a **whole-line word** and cites a `material` proposition whose `to` is short of the cited line's length | the segment and the line's length, and the standing at its end |
| **F3 grade** | it writes a **grade word** and cites exactly one `judgement` whose label is another grade | the cited judgement's move and grade |

**Words.** Each rule reads a fixed Korean word list in the code (`harness_frames_v1`): standing
words (앞서-, 앞선-, 우세, 뒤져-, 뒤진-, 열세, …), whole-line words (전체, 끝, 마지막, 최종, …) and
the guide's grade names (the glossary's labels). A sentence that states a frame in words outside the
lists is not held: a missed frame is reported (§6), a held right sentence costs the agent a retry.
The lists are set from Test 1's and the evaluation sample's sentences (development data) and tested
on them (§6.2).

**Not checked by code.** A number from a `search`-sourced record (T1) is not held — after T1 such a
number is a line the agent typed past the analysis — but counted per moment (`search_numbers`), and
reported beside M1b. Inferences (0.1, last row) are not checked.

### 4.2 Holds, states, record

As rev. 7's check (LT-D §5.5, A12): a held call is not sent, the runner answers with the rules and
the reply text above, and logs `tool_unsent`, `reason: "frame_check"`. At most **two** holds a moment,
then the call is sent and the moment's state is `exhausted`. States: `passed`, `exhausted`,
`not_run`. The `frames` line of each check holds the moment, the call, each held sentence's rule and
the `search_numbers` count. Unlike the model check, the frame check makes no request and has no
`unreadable` state.

### 4.3 What stays

The facts stage's claims block, the checker (LT-D §5.1–§5.2), rubric v3 (`harness_judge_v3`) and
the retries stay as rev. 7. The facts message (`harness_v4.md`) adds two lines: quote the analysis
(`source: "analysis"`) for the played and best lines and their scores; a number from a `search`
source is the agent's own line, and the sentence says so.

### 4.4 Versions

- `TOOLS_VERSION` **`agent_tools_v9`**, `GUIDANCE_VERSION` **`agent_guidance_v14`** (the tool
  descriptions of `explore` and `compare_lines`: the sources, `departs_at`, `analysis_ends_at`,
  `standing`). The guide stays `commentary_ko_v8`.
- Harness **revision 8**: `harness_v4`, `harness_judge_v3`, `harness_frames_v1`. Revisions 4–7 stay
  selectable for their runs.

## 5. R1 — the build's line endings

LT §16: the v7 worktree, checked out from WSL with LF line endings, gave another `build_id`
(`40a619e1…` against the base's `8124217c…`) because the reasoning build hashes data files; three
`A@v7` runs stopped before the model. Two changes, neither changing a `build_id`:

- the runner's mismatch error lists the data files whose digests differ from the base's build record;
- `freeze.py`'s worktree step (and its documentation) checks out with the repository's
  `core.autocrlf`, and the freeze record checks the worktree's `build_id` before the freeze is written.

## 6. Tests and measurement

### 6.1 Tests

T1: on a fixture game, `explore` of the played move with `continue_with` follows the analysis PV
(`source: "analysis"`), with `end_score` the line's score and no search admitted; moves that leave the
line give `departs_at` and `search` sources; `analysis_ends_at` where the PV is shorter than `length`;
`search: true` with no moves gives the root score; a position inside an explored line has no analysis
lines; ply *N+1*'s record never answers a line that starts with ply *N*'s move. `compare_lines`:
analysis ranking when every move has an analysis line, search ranking with `analysis_score` beside
otherwise, never mixed. T2: `net.white` = `standing.end` − `standing.start`; `standing_white` per ply;
`leader_at_end`. H1: each rule holds its 0.1 case (186492056006-22 #2 by F1 and F2, #3 by F1; a grade
named against its judgement by F3) on constructed calls; a level start never holds F1; a sentence
outside the word lists not held; two holds then `exhausted`; `search_numbers` counted. R1: a mismatch
names the differing files. M1: §6.4.

### 6.2 Measurement, in order

1. **Replay (no model).** (a) The eleven cases of 0.1's first two rows, put to v9 as in §2.4. **Bar:
   11 of 11** give the analysis record's line and score, or `departs_at` where the agent's moves left
   it. (b) The frame check over **every final sentence** of Test 1's submissions (A 216, H 237) and of
   the evaluation sample's HS rev. 4 submissions, against the judge's verdicts: the wrong sentences it
   holds, and the **false holds** (sentences the judge marked `ok` that it holds). **Bar:** false
   holds at most 2% of the `ok` sentences; held wrong sentences reported case by case.
2. **Pilot.** The development sample (Validation 184800218248 and 185264271324), `H@v9` (harness
   rev. 8), one run a game (LT A6): sources in the answers, frame-check holds, `search_numbers`,
   cost.
3. **Freeze**, then **Test 2** opened (RX0-D §2's order: moments, base, references, the engine check
   of LT §9.4 Q2, key causes reviewed by the owner).
4. **Blind on Test 2.** `A@v7`, `A@v9`, `H@v9`; three runs a game; the frozen bounds; one judging,
   `judge_v1`, audited; paired by moment, 90%.

### 6.3 The decision

**Adopted when**, read from `H@v9 − A@v7 / test2`: the HS-D §6 bars unchanged (LT-D §6.5) — M2b
+0.10 or more with the interval above zero; M1b's upper bound at most +2.0; failures and moment-runs
without commentary no more than A's; the worst case holds. Also reported, each with intervals:
`A@v9 − A@v7` (what the tools do) and `H@v9 − A@v9` (what the harness does with them); the frame
check's states and M1b per state; `search_numbers` and M1b with and without them; doubtful sentences
per arm; cost.

### 6.4 M1 — the second Test set

- `sets_v1.json` gains a set **`test2`**: four new chess.com games of the owner's, played after
  Test 1 was opened (2026-11-09), PGNs in the data directory, checked by digest as RX0-D §2 says.
- `test2` is handled as `test` (LT-D §6.4): opened only after a freeze, never pooled, a report mixing
  it with another set refused; its decision read from `<a> − <b> / test2`.
- **Test 1 is development data from here on**: its moments, references and runs may be read for
  this design (they were, in 0.1) and its sentences tune the frame check's word lists. Nothing is
  measured on it again.

## 7. Questions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Answer from the analysis record at game positions (T1)? | Yes. A commentary should agree with the analysis the product shows for the same move. That it also agrees with the references follows from that and is not the aim: the analysis can be wrong (LT §15's engine check: seven reference scores differ from depth 20 by more than 1.00), and the fix for that is the analysis, not a second search in the commentary. |
| Q2 | Replace rev. 7's model sentence check with the code frame check? | Yes. The model check did not sort wrong sentences from right ones on Test and costs a request a submission; the frame check is exact on what it covers and says what it does not cover. |
| Q3 | Four new games for Test 2? | Yes: required by RX0-D §2 for any later candidate. Their key causes need the owner's review before the batch, as Test 1's did. |
| Q4 | Which candidate does the freeze name: `H@v9` or `A@v9`? | `H@v9`. RX0-D §2 lets Test decide one frozen candidate and never choose among candidates; H holds the M2b gain, and `A@v9 − A@v7` is reported, not decided. If A@v9 does better, it is the next candidate, measured on new games. |
| Q5 | Fixed word lists for the frame check, missed frames accepted rather than false holds? | Yes: a false hold costs a retry and pushes moments to `exhausted` (rev. 5 and 6); a missed frame is counted and visible in the report. |

## 8. Not in this packet

- `rapid-54`'s `references_v2` (LT §9.4 Q1): when its moments are judged again.
- Any change to the judge or to what M1b counts (LT §16, review F2): T1 makes most of that question
  moot for H; the verdicts of earlier judgings stay.
- A frame check in the server for arm A: a server change of its own.
- Inferences in a sentence (0.1, last row), and Korean syllables garbled by Haiku
  (`agent-mh-implementation.md` §5).
