# Agent AF-D — analysis first: one engine record per game position, and sentences framed by their record

Status: rev. 2 (the owner's discussion of rev. 1, 2026-11-09: §10), draft for independent review.
Scope: the agent's MCP tools (`src/calliope/agent`: `explore`, `compare_lines`, the line ledger),
the staged harness of the RX runner (`tools/rx/harness.py`, its prompts), the judge's bundle and
rubric (`tools/rx/judge.py`, `judge_v2`), and the runner and report for a second Test set
(`tools/rx`). Not in scope: the guide (`commentary_ko_v8`, frozen for RX), `submit_commentary`'s
server checks, the analysis itself (a re-analysis is its own packet, §9), HIMARI.

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

Nothing links the two. The session's search engine starts with an **empty result store**
(`session._engine`: a new `FactEngine` a port), and `survey_stored` asks only that store, so a ply
record frozen in the base is never found by `explore`. And the two search different roots: the
analysis searches the position **before** the move (multi-PV; the played line is its PV that starts
with the move), `explore` of the played move with `search: true` searches the position **after** it.
No decision to keep them apart is recorded: `explore` was built to try any line, and LT-D §2's
`continue_with` took "the end search's PV" without looking at the analysis's; LT §9.3 (item 3) saw
the two PVs differ and noted it for the replay only.

**Both are Calliope's facts.** A session search is the same engine on the same profile
(`self.profile`), served under a handle and verified by the server; "Black −4 in 26...d4" is true of
it. So the problem is not that eleven sentences are false. It is three things:

1. **The grade and its reason rest on different records.** "25...Rxf7 is a blunder" is the analysis
   record's verdict, from its search of the position before the move and its line (26...Rg5, Black
   −10). A sentence that explains it by the session's line (26...d4, −4) gives a reason the verdict
   was not computed from; the reader cannot see why it is a blunder.
2. **Comparisons across searches.** A played move's score from the analysis beside a candidate's from
   a session search is a difference of two searches as much as of two moves (TO-D §3 N2).
3. **The judge counts them as wrong.** The references hold the analysis record only, so a sentence
   true of a session search is `wrong` or `doubtful` (LT §16 review F2). That part is the
   measurement's, not the agent's.

A commentary that says "the engine's evaluation after the move is −4.59" while the analysis shown
beside it says −3.63 also disagrees with the product. Which of the two searches is better is not
known from these cases: the session's was at depth 12 in one of them, and the analysis is not always
right either (LT §15's engine check).

### 0.3 Why this direction

| Option | Against it |
| --- | --- |
| Only count these as right (the judge alone) | It fixes 0.2's third point, not the first two: the grade would still be explained from another record than its own. Taken as one part (J1), not alone. |
| Replace the analysis with the latest search made during the commentary | The commentary already written cites the earlier records (handles bind to their records' content); a grade and its claims come from the multi-PV search before the move, which a session search after it cannot replace without recomputing the ply; the latest search is not the deeper one (depth 12 here); and a run's facts would depend on the order the agent explored in, so no base or reference could hold still. A better analysis is made as a new analysis version, before the commentary (§9), with T3's disagreements as its input. |
| Forbid digits and line outcomes in sentences | H's M2b gain is a line's outcome (LT-D §0.3). |
| Another model check of the sentences | Rev. 5–7's sentence check (a model reading the sentences against the claims) held right sentences on digits (rev. 5), exhausted moments on `unbacked` (rev. 6), and in rev. 7 did not sort wrong from right: the moments it passed clean had the **higher** wrong-sentence rate (M1b 12.2 against 1.5 for `passed_with_unbacked`). It cannot see the problem: the claims it reads agree with their records. |
| **One record per game position in the tools; the agent's own searches allowed with their source; the judge reading what the sentence cited; disagreements shown** | **Chosen.** Where the analysis holds a position or a line, every tool answers from it, so a grade is explained from its own record (T1); past it, the agent's own searches stay usable and say their source. The judge reads, besides the reference, the records each sentence cited, and counts a sentence true only of a session search apart from a wrong one (J1). Where both records answer one position and differ, the answer says so (T3); nothing is overwritten. The misframings left are checked by code (H1). |

## 1. The change

| Part | What |
| --- | --- |
| T1 | **Analysis first.** At a game position, `explore`'s end score and `continue_with`, and `compare_lines`' ranking, answer from the analysis record wherever it holds the line; a session search answers only past the analysis's lines. Every score and every appended ply says its **source** (`analysis` or `search`) and depth. |
| T2 | **The ledger's standing.** Beside `net` (the change since the line's start), the material **standing** at the line's start, after each ply and at the end; the note says which is which. |
| T3 | **Disagreements shown.** Where an answer serves an analysis score and a session search's score of one position, and they differ in kind or by more than 1.00, the answer marks it (`disagrees_with_analysis`) and the run counts it. Nothing replaces the analysis. |
| J1 | **Judge v2.** The bundle gives each sentence the records it cited, rendered in one form whatever the tools' version, with their source; a sentence true only by a cited session search, where the reference holds another value, is **`search_only`** — counted apart from `wrong`, not in M1b. |
| H1 | **Harness rev. 8: the frame check** (code) at submission, in place of the model sentence check: a sentence is held when its words state a cited material change as a standing, a cited segment as the whole line, or a grade other than the cited judgement's. |
| R1 | A `build_id` mismatch names the data files whose digests differ; the v7 server's worktree is checked out with the repository's line endings (LT §16's three failed `A@v7` runs). |
| M1 | A **second Test set** (`test2`, four new games) for the blind measurement (RX0-D §2: a later candidate is measured only on new Test games). |

## 2. T1 — analysis first

### 2.1 The analysis's lines at a position

For a game position — ply *N*'s position before its move, which is ply *N−1*'s after — the
**analysis lines** are the lines of the analysis record **whose root is that position**: ply *N*'s
subject judgement's played, best and alternative lines (their PVs, scores and depths, as
`_serve_analysis` serves them). A position off the game's line (inside an explored line) has no
analysis lines.

**Only a stored record answers.** RX's sealed bases hold the fixed moments' ply records (RX2-D §3:
the probe checks every fixed moment is `cached: true`); another ply is analysed only when the agent
asks for it, and counted as analysed outside the base. T1 reads a ply's record only when it is
already stored (in the base, or analysed earlier in the session); it **never starts an analysis**.
A position whose record is not stored has no analysis lines, and the tools answer as v8 with
`source: "search"`. So at a fixed moment's ply — where the commentary's grade comes from — T1 always
applies; at the position after the move (ply *N+1*'s root) it applies only if that ply is stored.

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
…Bxh2). §7.2 step 1 makes this the bar.

### 2.5 T3 — disagreements shown

T1 leaves two places where one position gets both an analysis score and a session search's:

- `compare_lines`' search ranking (§2.3, "otherwise"), whose entries carry `analysis_score` beside
  the search's score;
- **`explore(..., search: "fresh")`**, a new value beside `true`: at a game position with analysis
  lines, it also runs a session search (admitted and charged as v8's) and serves it **beside** the
  analysis's `end_score`, `source: "search"`, never in its place. For the agent that wants a second
  look; the harness's message does not ask for it.

There, the answer marks **`disagrees_with_analysis`** when the two differ **in kind** (a mate against
a centipawn score, or another side favoured, LT-D §2's `favours`) or by **more than 1.00** for the
mover (the engine check's threshold, LT §9.4 Q2), with both values, both depths and both handles.
The run records each one (a `disagreement` line: position, both scores, depths). The analysis is
never changed by it, and nothing else in the answer moves: the disagreement is shown, and a sentence
about it cites both. The report counts them per arm and moment; their list is the input of a later
re-analysis (§9).

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
lists is not held: a missed frame is reported (§7), a held right sentence costs the agent a retry.
The lists are set from Test 1's and the evaluation sample's sentences (development data) and tested
on them (§7.2).

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
  `standing`, `search: "fresh"`, `disagrees_with_analysis`). The guide stays `commentary_ko_v8`.
- The judge: **`judge_v2`** (`judge_v2.md`, its schema with `search_only`); `judge_v1` stays for the
  judgings that used it.
- Harness **revision 8**: `harness_v4`, `harness_judge_v3`, `harness_frames_v1`. Revisions 4–7 stay
  selectable for their runs.

## 5. J1 — judge v2: what the sentence cited

`judge_v1` reads one reference a moment, built from the analysis record (RX2-D §4.1), and marks a
sentence `wrong` when the reference shows it false and `doubtful` when it cannot. A sentence true of
the session search it cited is `wrong` when the reference's line or score differs (0.1) and
`doubtful` when the reference has nothing there (most of H's 32 doubtful on Test). J1 gives the judge
what the sentence cited, and one more verdict.

### 5.1 The bundle's evidence

`tools/rx/judge.py` adds, to each bundle item's sentence, **`evidence`**: the records the sentence
cites that the server **verified** (the submission's `verified` list), each rendered by the bundler
in **one form** whatever the tools' version, so the judge cannot tell v7 from v9 (it stays blind,
judge_v1 §1):

- a line: the start FEN, the moves in SAN, and the material standing after each ply **computed by the
  bundler** with python-chess from the FEN (not copied from the tool's answer); its end score if
  cited;
- a score: the position's FEN, the score, its depth;
- a judgement: the move and its grade;
- for each, **`source`**: `analysis` (a handle served from a ply record, `_serve_analysis`) or
  `search` (a handle from `session._search`, or a line whose plies past the agent's came from one),
  read from the run's `handle` lines (as `reference.py` reads served handles' identities).

Nothing from the reference is repeated there, and no arm, variant or run is named.

### 5.2 The rubric (`judge_v2.md`)

`judge_v1`'s verdicts, with one added and one sharpened:

- **`search_only`**: what the sentence states is true by its cited evidence of `source: search`, and
  the reference holds **another** value for the same thing (another line from that position, another
  score of it). `why` names both. It is not `ok` and not `wrong`.
- **`ok`** also when the sentence is true by its cited evidence of `source: search` and the reference
  has nothing for that thing (a line beyond the reference's): such a sentence was `doubtful` under
  judge_v1.
- Evidence of `source: analysis` that differs from the reference is read as the reference (both are
  the analysis record; a difference is a reference built from another record, LT §9.3, and `why`
  says so).
- `wrong` and `doubtful` otherwise as judge_v1. A sentence that frames a cited number wrongly (a
  change as a standing, a segment as the whole line) is `wrong`: the evidence holds the frame.

### 5.3 What the report counts

- **M1b** counts `wrong` only, as before; **M1s** is the rate of `search_only` a 100 sentences, per
  arm, with its paired interval, beside M1b. **M1b + M1s** is reported as the judge_v1-like rate
  (what judge_v1 would have counted wrong, approximately).
- judge_v2 judges **every arm of a measurement together** (RX0-D §7.2). Earlier judgings stay
  judge_v1 and are not compared with judge_v2's numbers.

## 6. R1 — the build's line endings

LT §16: the v7 worktree, checked out from WSL with LF line endings, gave another `build_id`
(`40a619e1…` against the base's `8124217c…`) because the reasoning build hashes data files; three
`A@v7` runs stopped before the model. Two changes, neither changing a `build_id`:

- the runner's mismatch error lists the data files whose digests differ from the base's build record;
- `freeze.py`'s worktree step (and its documentation) checks out with the repository's
  `core.autocrlf`, and the freeze record checks the worktree's `build_id` before the freeze is written.

## 7. Tests and measurement

### 7.1 Tests

T1: on a fixture game, `explore` of the played move with `continue_with` follows the analysis PV
(`source: "analysis"`), with `end_score` the line's score and no search admitted; moves that leave the
line give `departs_at` and `search` sources; `analysis_ends_at` where the PV is shorter than `length`;
`search: true` with no moves gives the root score; a position inside an explored line has no analysis
lines; ply *N+1*'s record never answers a line that starts with ply *N*'s move; a ply whose record is
not stored answers as v8 and starts no analysis. `compare_lines`: analysis ranking when every move has
an analysis line, search ranking with `analysis_score` beside otherwise, never mixed; a line's
`end_score` the analysis line's score until an extension, the extension's marked `search`. T2:
`net.white` = `standing.end` − `standing.start`; `standing_white` per ply; `leader_at_end`. T3:
`search: "fresh"` serves both scores and never replaces the analysis's; `disagrees_with_analysis` on a
kind difference and above 1.00, not at 1.00 or below; the `disagreement` line written. J1: the
bundle's evidence holds only verified citations; a line's standing computed from the FEN, not copied;
`source` from the handle lines; a v7 and a v9 citation of the same line render identically; no arm or
run in the bundle; the report's M1s and M1b + M1s on constructed judgings. H1: each rule holds its 0.1
case (186492056006-22 #2 by F1 and F2, #3 by F1; a grade named against its judgement by F3) on
constructed calls; a level start never holds F1; a sentence outside the word lists not held; two
holds then `exhausted`; `search_numbers` counted. R1: a mismatch names the differing files. M1: §7.4.

### 7.2 Measurement, in order

1. **Replay (no model).** (a) The eleven cases of 0.1's first two rows, put to v9 as in §2.4. **Bar:
   11 of 11** give the analysis record's line and score, or `departs_at` where the agent's moves left
   it. (b) The frame check over **every final sentence** of Test 1's submissions (A 216, H 237) and of
   the evaluation sample's HS rev. 4 submissions, against the judge's verdicts: the wrong sentences it
   holds, and the **false holds** (sentences the judge marked `ok` that it holds). **Bar:** false
   holds at most 2% of the `ok` sentences; held wrong sentences reported case by case.
2. **Judge v2 on Test 1 (development data).** Test 1's 69 commentaries (both arms) judged again with
   judge_v2, one fresh judging, audited. **Bar:** of the 0.1 table's eleven, each `search_only` or
   `ok`, none `wrong`; the other wrong sentences (H's four, A's four) still `wrong`; every change of
   verdict from judge_v1 listed with the judge's reason and read before the freeze. It checks the
   rubric, not the agent: no decision is read from it.
3. **Pilot.** The development sample (Validation 184800218248 and 185264271324), `H@v9` (harness
   rev. 8), one run a game (LT A6): sources in the answers, `departs_at`, disagreements, frame-check
   holds, `search_numbers`, cost.
4. **Freeze**, then **Test 2** opened (RX0-D §2's order: moments, base, references, the engine check
   of LT §9.4 Q2, key causes reviewed by the owner).
5. **Blind on Test 2.** `A@v7`, `A@v9`, `H@v9`; three runs a game; the frozen bounds; one judging,
   **judge_v2**, audited; paired by moment, 90%.

### 7.3 The decision

**Adopted when**, read from `H@v9 − A@v7 / test2` under judge_v2: the HS-D §6 bars unchanged (LT-D
§6.5) — M2b +0.10 or more with the interval above zero; M1b's upper bound at most +2.0; failures and
moment-runs without commentary no more than A's; the worst case holds. Also reported, each with
intervals: **M1s** and **M1b + M1s** (§5.3); `A@v9 − A@v7` (what the tools do) and `H@v9 − A@v9`
(what the harness does with them); disagreements per arm; the frame check's states and M1b per
state; `search_numbers`; doubtful sentences per arm; cost.

M1s is reported, not a bar. A gain that holds only because `search_only` left M1b is visible beside
it: M1b + M1s above +2.0 is said in the report's reasons, though it does not by itself refuse.

### 7.4 M1 — the second Test set

- `sets_v1.json` gains a set **`test2`**: four new chess.com games of the owner's, played after
  Test 1 was opened (2026-11-09), PGNs in the data directory, checked by digest as RX0-D §2 says.
- `test2` is handled as `test` (LT-D §6.4): opened only after a freeze, never pooled, a report mixing
  it with another set refused; its decision read from `<a> − <b> / test2`.
- **Test 1 is development data from here on**: its moments, references and runs may be read for
  this design (they were, in 0.1), its sentences tune the frame check's word lists, and its
  commentaries check judge_v2 (§7.2 step 2). Nothing is measured on it again.

## 8. Questions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Answer from the analysis record at game positions (T1)? | Yes. A grade should be explained from the record it was computed from, and a commentary should agree with the analysis the product shows for the same move. That it also agrees with the references follows and is not the aim: the analysis can be wrong (LT §15's engine check: seven reference scores differ from depth 20 by more than 1.00), and the fix for that is a better analysis (§9), not a second search inside the commentary. |
| Q2 | Replace rev. 7's model sentence check with the code frame check? | Yes. The model check did not sort wrong sentences from right ones on Test and costs a request a submission; the frame check is exact on what it covers and says what it does not cover. |
| Q3 | Four new games for Test 2? | Yes: required by RX0-D §2 for any later candidate. Their key causes need the owner's review before the batch, as Test 1's did. |
| Q4 | Which candidate does the freeze name: `H@v9` or `A@v9`? | `H@v9`. RX0-D §2 lets Test decide one frozen candidate and never choose among candidates; H holds the M2b gain, and `A@v9 − A@v7` is reported, not decided. If A@v9 does better, it is the next candidate, measured on new games. |
| Q5 | Fixed word lists for the frame check, missed frames accepted rather than false holds? | Yes: a false hold costs a retry and pushes moments to `exhausted` (rev. 5 and 6); a missed frame is counted and visible in the report. |
| Q6 | Judge Test 2 with judge_v2 (J1), with `search_only` outside M1b? | Yes. A sentence true of a verified Calliope search is not a false statement (§0.2), and judge_v1 cannot tell the two apart. The cost: Test 2's numbers are not comparable with earlier judgings, which no decision needs (each Test is judged on its own), and M1b + M1s is reported as the judge_v1-like rate. |
| Q7 | T3's threshold: a difference in kind, or more than 1.00? | Yes, the engine check's (LT §9.4 Q2), so the two flags mean the same. |

## 9. Not in this packet

- **A re-analysis.** A new analysis version (deeper, or re-run where T3's disagreements and the engine
  check's flags cluster), with new bases and a new reference version, before commentaries are written
  from it. Its own design packet, from the disagreements this packet records.
- `rapid-54`'s `references_v2` (LT §9.4 Q1): when its moments are judged again.
- A frame check in the server for arm A: a server change of its own.
- Inferences in a sentence (0.1, last row), and Korean syllables garbled by Haiku
  (`agent-mh-implementation.md` §5).

## 10. Revisions

**rev. 1 → rev. 2** (the owner's discussion, 2026-11-09). The owner asked why a session search of a
position does not use the analysis frozen for it, whether a search from Calliope's own fact engine
should count whatever its time, and whether the analysis could be replaced by the latest search.

| Point | Applied |
| --- | --- |
| A session search is Calliope's fact too | §0.2: both records are verified facts; the problem restated as the grade explained from another record, comparisons across searches, and the judge counting such sentences wrong. J1 (§5): judge v2 reads the cited records, `search_only` apart from `wrong`, M1s reported. |
| Why the frozen analysis is not reused | §0.2: the session's search engine starts with an empty store and searches another root; no decision to separate them is recorded. |
| Replace the analysis with the latest search | §0.3: not done, for four reasons; a better analysis is a new version before the commentary (§9). T3 (§2.5) shows where the two disagree and records it as that packet's input. |
| §2.1's open point: is every ply in the base? | §2.1: the bases hold the fixed moments' plies; T1 reads only stored records and starts no analysis. |

