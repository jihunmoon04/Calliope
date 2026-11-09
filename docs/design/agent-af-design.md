# Agent AF-D — analysis first: one engine record per game position, and sentences framed by their record

Status: rev. 4; re-review of rev. 3 NOT_READY (F1, F2; N1) applied (§10); re-review of rev. 2
NOT_READY (F1–F3; R1, R2, N1, with rev. 1's review) applied in rev. 3; rev. 2: the owner's
discussion of rev. 1, 2026-11-09. Draft for independent review.
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
cited line. The extraction is in the repository (review N2): `rx-evidence/af/wrong_cites.py` reads
the runs (in the data directory, outside git) and the judging, and its output
`rx-evidence/af/test1-wrong-cites.json` holds, for each of the 19 wrong sentences of both arms, the
sentence, each citation resolved as the server resolved it (an explicit proposition by its id; a
cited handle through the `verified` entries whose `by_handle` is that handle — all 31 citations
resolve), each handle's origin restored from the call that served it (§5.1), each material count's
segment origin, and the reference's lines.

| What the sentence's number is true of | Wrong | Cases (game-ply, run) |
| --- | --- | --- |
| **A line from the session's own search**, where the reference holds the analysis record's line | **7** | 186491823816-50 ×5 (runs `TRH87V` #3 #7, `Y2ZKYK` #3 #4, `827V6J` #2): all cite a `material` proposition over plies 0–9 of an `explore` of the played move 25...Rxf7 with `continue_with: "engine"`. The session's search after it plays 26.Rxf7 **d4** 27.Rxb7 dxc3 — Black −4, true of that line; the analysis record (and the reference) plays 26.Rxf7 **Rg5** 27.Rxb7 … 28.Rxf5 — Black −10. 186437361608-38 (`FJ3HFV` #3): 19...Nxb5 continued by a session search, net 0; the reference's line, +4 for Black. 186203030416-38 (`B3NVPP` #5): the agent's four moves, then a session search that reaches …Bxh2 (−5); the reference's line ends 21.Kxc2 g6. |
| **A score from the session's own search**, where the reference holds the analysis record's score | **4** | 186437361608-72 ×3 (`7SRK7C` #6 #8, `XK6CCH` #4): +6.39 and −4.78 from session searches (`s121`, `s126`, `s138`) against +5.18 and −6.80. 186203030416-38 (`B3NVPP` #6): "the engine's evaluation after the move, −4.59", an `engine_score` of a session search of the position after the move; the analysis record holds −3.63. |
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
  one search after each ranked move). These are new searches in the fact engine's own store.

**Both run at the same depth.** The analysis record's search is the profile `d12_mpv5_v1` at
depth 12, multi-PV, of the position **before** the move (the references' `evaluation.search`); the
session's searches use the same profile (`self.profile`), so they also reach depth 12, of the
position **after** the move or at a line's end. They differ in **root**, not in depth, and so in PV
and score. (Rev. 2 said the session's search was shallower; it is not.)

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
known from these cases: both are depth 12 on one profile, a search from the position after the move
looks one ply further down that line, and the analysis is not always right either (LT §15's engine
check). T1's reason is the grade's own record and the product's, not a better search.

### 0.3 Why this direction

| Option | Against it |
| --- | --- |
| Only count these as right (the judge alone) | It fixes 0.2's third point, not the first two: the grade would still be explained from another record than its own. Taken as one part (J1), not alone. |
| Replace the analysis with the latest search made during the commentary | The commentary already written cites the earlier records (handles bind to their records' content); a grade and its claims come from the multi-PV search before the move, which a session search after it cannot replace without recomputing the ply; the latest search is no deeper (both depth 12, one profile); and a run's facts would depend on the order the agent explored in, so no base or reference could hold still. A better analysis is made as a new analysis version, before the commentary (§9), with T3's disagreements as its input. |
| Forbid digits and line outcomes in sentences | H's M2b gain is a line's outcome (LT-D §0.3). |
| Another model check of the sentences | Rev. 5–7's sentence check (a model reading the sentences against the claims) held right sentences on digits (rev. 5), exhausted moments on `unbacked` (rev. 6), and in rev. 7 did not sort wrong from right: the moments it passed clean had the **higher** wrong-sentence rate (M1b 12.2 against 1.5 for `passed_with_unbacked`). It cannot see the problem: the claims it reads agree with their records. |
| **One record per game position in the tools; the agent's own searches allowed with their source; the judge reading what the sentence cited; disagreements shown** | **Chosen.** Where the analysis holds a position or a line, every tool answers from it, so a grade is explained from its own record (T1); past it, the agent's own searches stay usable and say their source. The judge reads, besides the reference, the records each sentence cited, and counts a sentence true only of a session search apart from a wrong one (J1). Where both records answer one position and differ, the answer says so (T3); nothing is overwritten. The misframings left are checked by code (H1). |

## 1. The change

| Part | What |
| --- | --- |
| T1 | **Analysis first.** At a game position, `explore`'s score and `continue_with`, and `compare_lines`' ranking, answer from the analysis record wherever it holds the line; a session search answers only past the analysis's lines. An analysis score is an **`analysis_score`** (read at the root: `root_ply`, `evaluated_move`, `score_at`, `pv_followed`, depth), never an `end_score` (a search at a line's end). Every appended ply says its **source**. |
| T2 | **The ledger's standing.** Beside `net` (the change since the line's start), the material **standing** at the line's start, after each ply and at the end; the note says which is which. |
| T3 | **Disagreements shown.** Where an answer serves an analysis score and a session search's score of one position, and they differ in kind or by more than 1.00, the answer marks it (`disagrees_with_analysis`) and the run counts it. Nothing replaces the analysis. |
| J1 | **Judge v2.** The bundle gives each sentence the records it cited, rendered in one form whatever the tools' version, with their source. A number stated without a source is read as the analysis's; a sentence that **says** it reports a separate search, true by it, where the reference holds another value, is **`search_only`** — outside M1b, with a bar of its own (M1s). |
| H1 | **Harness rev. 8: the frame check** (code) at submission, in place of the model sentence check: a sentence is held when its words state a cited material change as a standing, a cited segment as the whole line, or a grade other than the cited judgement's — only where the sentence maps to one cited proposition and one number; otherwise `uncheckable`, not held. |
| R1 | A command makes the v7 server's worktree with the checkout's line endings and checks the build's data files; `freeze.py` checks it; a `build_id` mismatch names the files (LT §16's three failed `A@v7` runs). |
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

### 2.2 Two scores, two meanings (review F1)

An analysis line's score is **not** a search at the end of the agent's moves: it is the analysis
root's evaluation of choosing that line's first move, read at the root. v9 keeps the two apart, by
name, in every tool:

- **`end_score`** keeps its v8 meaning only: a search **at the line's end position**
  (`source: "search"`, `path`, `fen`, `depth`, `score_ref`). It is never filled from the analysis.
- **`analysis_score`**: an analysis record's score, with where it was read (an illustration; the
  values are not a record's):

```json
"analysis_score": {"source": "analysis", "root_ply": 50, "root": "before",
                   "evaluated_move": "25...Rxf7", "line": "played", "score_at": "root",
                   "pv_followed": 9, "white_view": "+9.68", "for_mover": "-9.68",
                   "mover": "black", "depth": 12, "profile": "d12_mpv5_v1", "score_ref": "s16.…"}
```

  `root_ply` and `root: "before"` name the position searched (ply *N*'s position before its move);
  `evaluated_move` and `line` (`played`, `best`, or `alternative`) name the root move whose line
  the score belongs to; `score_at: "root"` says it is the root's evaluation of that move, not a
  search further down; `pv_followed` is how many plies of the agent's moves (and of `continue_with`'s)
  lie along that line's PV; `for_mover` is for the side to move at the root. The values are the
  record's (`judgements[0].played|best|alternatives[*].score`, `depth`; `evaluation.search.profile`).

### 2.3 `explore`

`explore(game, position, moves, search, continue_with, length)`, `position` a game position:

- **The agent's moves follow an analysis line** when they are a prefix of one (the first such line in
  the order played, best, alternatives). Then:
  - with `search: true`, the answer gives that line's **`analysis_score`** and no `end_score`: no
    search is admitted. Before v9 this was a new search after the agent's last move.
  - with `continue_with: "engine"`, the appended plies are **the rest of that line's PV**
    (`source: "analysis"`), up to `length`. Where the PV ends before `length`, the answer says so
    (`analysis_ends_at`) and appends nothing more: no search continues an analysis line.
  - with `search: "fresh"` (§2.6), both: the `analysis_score` and an `end_score` from a session
    search at the line's end.
- **The agent's moves leave every analysis line** (or the position is off the game's line, or its ply
  is not stored): v8's behaviour, every appended ply `source: "search"`, `end_score` as v8.
  `departs_at` names the first ply where the moves left the longest analysis line they followed, that
  line's move there ("the analysis plays 26...Rg5 here"), and that line's `analysis_score` with its
  `pv_followed`.
- **No moves**, `search: true`, at a game position: the record's root evaluation as two
  `analysis_score`s, **`best`** (`evaluated_move` the record's `evaluation.best_move`: the position's
  value) and **`played`** (the move played there), each with the fields above. No `end_score`.

The ledger's per-ply `source` (LT-D §2: `agent` | `engine`) becomes `agent` | `analysis` |
`search`. The `x` handle's record holds the sources; an `explored_line` proposition backs the moves
as today.

### 2.4 `compare_lines`

The same contract. Each line is built as TO-D §3 builds it today (`session._compared_line`): its
given moves — for `played` and `best`, the analysis PV — then **one** search at their end, and an
extension along that search's PV **without another search**; `end_score_at` is the searched ply, the
end of the given moves, not the extension's end (review F2 of rev. 3: rev. 3 put the score at the
extension's end, which would need a second search). v9 keeps that one search and names it:

```
analysis PV:     A → B → C            analysis_score  (root ply N, evaluated move A, pv_followed 3)
search at C:               ↓          end_score       (source "search", end_score_at 3 = C)
its PV:                    D → E → F  extension plies (source "search"), no score of their own
```

- **`analysis_score`** (§2.2) for the line, `pv_followed` the length of the given moves that lie on
  the analysis PV;
- **`end_score`**: the search at the end of the given moves (C), `source: "search"`, `end_score_at`
  that ply, its `path` and `fen`, as v8. The extension's plies are `source: "search"` and carry no
  score; nothing is searched at F. One search a line, as today, admitted as `explore`'s;
- both are served beside each other, never one in the other's place, and T3 (§2.6) compares them.

The **ranking** (LT-D §3) is one source, never mixed (TO-D §3 N2):

- **When every ranked move has an analysis line at the position** (the played move, the best and
  candidates among the alternatives): ranked by their **`analysis_score`s** (`for_mover`),
  `source: "analysis"`. These are one search's multi-PV, all read at one root. No search is admitted.
- **Otherwise:** v8's ranking (one session search after each move, each an `end_score` of the
  position after the move), `source: "search"`; each entry with an analysis line also carries its
  `analysis_score`, never ranked with the others.

The `k` record holds the source; the checker (LT-D §5.2) reads `better_for_mover` claims from
whichever ranking was served, and a `score` claim from the field its handle backs (`analysis_score`'s
`score_ref` or `end_score`'s).

### 2.5 What the replay of 0.1 must show

For the eleven cases of the first two rows, the same calls (same game, position, moves and options)
answered by v9 give **the analysis record's line and its `analysis_score`**, which are the
reference's — or say `departs_at` where the agent's own moves left the analysis (186203030416-38 #5:
the four typed moves follow the analysis line, then `analysis_ends_at` after 21...g6 instead of a
search reaching …Bxh2). §7.2 step 1 makes this the bar.

### 2.6 T3 — disagreements shown

T1 leaves two places where an answer carries both an `analysis_score` and a session search's
`end_score`:

- `compare_lines`' lines (§2.4): each line's `analysis_score` and its `end_score` at the end of the
  given moves (`pv_followed` = `end_score_at`);
- `compare_lines`' search ranking (§2.4, "otherwise");
- **`explore(..., search: "fresh")`**, a new value beside `true`: where the moves follow an analysis
  line, it also runs a session search at the line's end (admitted and charged as v8's) and serves it
  as `end_score` beside the `analysis_score`, never in its place. For the agent that wants a second
  look; the harness's message does not ask for it.

**They are not one search of one root** (review R2). The `analysis_score` is the root's evaluation
of a move (ply *N*'s position before the move); the `end_score` is a search of the position
`pv_followed` plies down that move's PV. Along a PV the two estimate one value, so they can be
compared, but the record says what was compared: a **`disagreement`** entry in the answer and a
`disagreement` line in the run hold `analysis: {root_ply, root, evaluated_move, line, pv_followed,
white_view, depth, score_ref}` and `search: {path, fen, white_view, depth, score_ref}`, both turned
to White's view for the comparison.

The answer marks **`disagrees_with_analysis`** when the two differ **in kind** (a mate against a
centipawn score, or another side favoured, LT-D §2's `favours`) or by **more than 1.00** (the engine
check's threshold, LT §9.4 Q2). The analysis is never changed by it, and nothing else in the answer
moves: the disagreement is shown, and a sentence about it cites both. The report counts them per arm
and moment; their list is the input of a later re-analysis (§9).

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
(after `normalized`, HS rev. 4 A3), in the place of rev. 7's sentence check.

**What a sentence cites, as the server reads it** (review F2). A sentence's `cites` name either a
proposition of the call's `propositions` (by its `id`) or a handle, which the server expands into the
propositions that handle backs (the `verified` entries with `by_handle`). The frame check reads only
**explicit propositions** of the call — their kind and fields are in the call — and never expands a
handle: a rule whose proposition would have to come from a cited handle does not apply (below). A
test pins that, on a scripted session, the explicit propositions the check reads for a sentence are
the `verified` entries the server answers for that sentence's explicit cites.

**A rule holds only when the sentence maps to it uniquely.** The sentence's number tokens are
`calliope.agent.sentences.tokens` read by `check_token`'s classes; moves, squares and scores are not
counts, so the **counts** are the integer tokens that are not a move's number.

| Rule | Applies when (all of) | Holds when | The reply names |
| --- | --- | --- | --- |
| **F1 change as standing** | the sentence cites **exactly one** explicit `material` proposition (a change from ply `from` to `to`) and no handle that backs material; its counts are **exactly one** token, equal to that proposition's `balance` or its absolute value | a **standing word** is in the sentence, and the standing at `to` is not the change (the line did not start level; the standing from the ledger of the line the proposition names) | the change, and the standing at `to`: "pm21 is White's gain over plies 0–2 (+9); after ply 2 Black still leads by 1" |
| **F2 segment as whole** | as F1 | a **whole-line word** is in the sentence, and `to` is short of the cited line's length | the segment and the line's length, and the standing at its end |
| **F3 grade** | the sentence cites **exactly one** explicit `judgement` proposition and writes **exactly one** grade word | the grade word is not the judgement's grade | the cited judgement's move and grade |

**Otherwise `uncheckable`.** A sentence with a frame word and a cited `material` or `judgement`
where the mapping is not unique — two counts, two cited material propositions, a material number
backed by a cited handle, two grade words — is **not held** and is recorded as `uncheckable` for that
rule. The review's example, "백은 이 수순에서 9점을 얻었지만, 전체 물질은 여전히 흑이 1점 앞선다"
(two counts, 9 and 1), is `uncheckable`, not held, though it has a standing word and a whole-line
word. A frame the check cannot read is left to the judge; a right sentence held costs a retry.

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
`not_run`. The `frames` line of each check holds the moment, the call, each held sentence's rule,
each `uncheckable` sentence's rule and why (which part of the mapping was not unique), and the
`search_numbers` count. Unlike the model check, the frame check makes no request and has no
`unreadable` state.

### 4.3 What stays

The facts stage's claims block, the checker (LT-D §5.1–§5.2), rubric v3 (`harness_judge_v3`) and
the retries stay as rev. 7. The facts message (`harness_v4.md`) adds two lines: quote the analysis
(`analysis_score`, `source: "analysis"`) for the played and best lines and their scores; a number from
a `search` source is from a separate search, and **the sentence says so in its words** ("별도 탐색에서는
…"): judge v2 reads a number without a stated source as the analysis's (§5.2).

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
- for each, its **`origin`**: `analysis`, `search` or `agent` (below).

Nothing from the reference is repeated there, and no arm, variant or run is named.

**Where each record came from** (review F1 of rev. 3). The recorder's `handle` line holds `ref`,
`kind`, `source`, `address`, `identity` and `line_key` (`record.Recorder.handle`). That is enough for
an `s` handle — `source.kind` is `search` for a session search, the ply record's otherwise — but not
for an `x` handle, whose `source` is the facts tree (`facts_tree`) whatever its plies came from. The
origin is therefore defined per ply and per proposition:

- **A ply's origin:** `agent` (typed by the agent: a candidate, an `explore` move), `analysis` (a move
  of an analysis PV: `compare_lines`' `played`/`best` moves, v9's `continue_with` along an analysis
  line) or `search` (appended from a session search's PV: `continue_with` past or without the
  analysis, a `compare_lines` extension).
- **A proposition's origin:** an `engine_score`/`engine_line` takes its `s` handle's; an
  `explored_line` takes the most foreign of its plies' (`search` over `agent` over `analysis`); a
  **`material`** proposition takes that of **its own segment** — plies `from`+1 to `to` of its line —
  so a count over the analysis part of a line that was later extended is `analysis`; a `judgement` or
  `claim` is `analysis`.
- **v9 records it.** The `handle` line gains `origin`: for an `s` handle `analysis` or `search`; for
  an `x` handle `plies_origin`, one entry a ply, written when the handle is served from the answer's
  ledger sources. The bundler reads it from there.
- **v7 and v8 runs are restored** from the records: the handle line's `call_id` names the call that
  served it, and that call's answer gives the plies: an `explore` answer's `ledger.plies[].source`
  (`agent` → `agent`, `engine` → `search`; v7's `explore`, which has no `continue_with`, is all
  `agent`); a `compare_lines` line's `source` (`{kind: n}`: the first n plies, `analysis` for
  `played`/`best`, `agent` for a candidate) and `extended` (the next plies, `search`).
- **One function** in `tools/rx/judge.py` does both (`origin(handle_line, call_line)`), and
  `rx-evidence/af/wrong_cites.py` is its prototype: on Test 1's 19 wrong sentences it resolves every
  citation (31; a cited handle through the `verified` entries whose `by_handle` is that handle) and
  gives the eight material counts behind 0.1's line cases `search` and the two of row 3 `analysis`.

An `agent` origin is a line the agent chose; its material is a board fact, but the line is not the
analysis's, so the rubric reads it as it reads `search` (§5.2).

### 5.2 The rubric (`judge_v2.md`)

`judge_v1`'s verdicts, with one added, one sharpened and one reading fixed (review F3):

- **A number's source as the sentence presents it.** A commentary explains the analysis's verdict,
  so a line, score or material count that the sentence states **without saying where it comes from**
  — "이 수 뒤 엔진 평가는 −4.59다", "이 라인의 평가는 +6.39" — is read as **the analysis's**, and
  judged against the reference. One that names the analysis ("분석 평가는") is the analysis's too. Only
  a sentence that says, in its words, that the number is from a **separate or further search** or the agent's own line ("별도
  탐색에서는", "더 깊이 둔 수순에서는", "에이전트가 이어 둔 수순에서는") presents a search.
- **`search_only`**: the sentence **presents a search** (above), what it states is true by its cited
  evidence of origin `search` or `agent`, and the reference holds **another** value for the same thing (another
  line from that position, another score of it). `why` names both. It is not `ok` and not `wrong`.
- **`wrong`, kind `source`** (new kind): the sentence presents a number as the analysis's (stated
  without a source, or naming the analysis), the reference holds another value, and the number is
  true only by cited evidence of origin `search` or `agent`. The three rows of the review:

  | Sentence | Verdict |
  | --- | --- |
  | "깊이 12의 별도 탐색에서는 −4.59였다." — cited search evidence −4.59 | `search_only` |
  | "이 수에 대한 분석 평가는 −4.59다." — analysis −3.63 | `wrong` (`source`) |
  | "이 수 뒤 엔진 평가는 −4.59다." — no source stated, analysis −3.63 | `wrong` (`source`) |

- **`ok`** also when the sentence is true by its cited evidence of origin `search` or `agent` and the reference
  has **nothing** for that thing (a line beyond the reference's): there is no analysis value it could
  be mistaken for. Such a sentence was `doubtful` under judge_v1.
- Evidence of origin `analysis` that differs from the reference is read as the reference (both are
  the analysis record; a difference is a reference built from another record, LT §9.3, and `why`
  says so).
- `wrong` and `doubtful` otherwise as judge_v1. A sentence that frames a cited number wrongly (a
  change as a standing, a segment as the whole line) is `wrong`: the evidence holds the frame.

### 5.3 What the report counts

- **M1b** counts `wrong` (every kind, `source` included), as before; **M1s** is the rate of
  `search_only` a 100 sentences, per arm, with its paired interval, beside M1b. **M1b + M1s** is
  reported as the judge_v1-like rate (what judge_v1 would have counted wrong, approximately).
- **M1s has a bar of its own** (review F3; §7.3): a candidate that moves its disagreements with the
  analysis from `wrong` into `search_only` does not pass on that.
- judge_v2 judges **every arm of a measurement together** (RX0-D §7.2). Earlier judgings stay
  judge_v1 and are not compared with judge_v2's numbers.

## 6. R1 — the build's line endings

LT §16: the v7 worktree, checked out from WSL with LF line endings, gave another `build_id`
(`40a619e1…` against the base's `8124217c…`) because the reasoning build hashes data files; three
`A@v7` runs stopped before the model. Today nothing makes the worktree: `run.py` only reads it at
`RX_DATA/servers/agent-tools-v7` (`SERVER_ROOTS`), and LT's was made by hand. (Rev. 2 named a
worktree step of `freeze.py`; there is none, review N1.) Three changes, none changing a `build_id`:

- **A command makes it:** `python -m tools.rx server-worktree v7` runs `git worktree add` of the
  variant's tag into `RX_DATA/servers/<name>`, from the repository it runs in and with that
  repository's own `core.autocrlf` (passed as `-c core.autocrlf=<value>`, read from that repository's
  config), so the worktree's files have the line endings of the checkout the base was built from. It
  then compares, byte for byte, every data file the reasoning build hashes (the files
  `record.build_id`'s parts read) in the worktree with the checkout's, and stops naming each one that
  differs. An existing worktree is checked the same way, never replaced.
- **`freeze.py`** runs that check for every variant with a server root before writing the freeze
  record, and records each worktree's commit and the check's result.
- **The runner's mismatch error** lists the data files whose digests differ from the base's build
  record.

## 7. Tests and measurement

### 7.1 Tests

T1: on a fixture game, `explore` of the played move with `continue_with` follows the analysis PV
(`source: "analysis"`), with the line's `analysis_score` (`root_ply`, `root`, `evaluated_move`,
`line`, `score_at: "root"`, `pv_followed`, `depth`, `profile`, `score_ref` equal to the record's) and
**no `end_score`**, no search admitted; `end_score` never carries `source: "analysis"` in any answer;
moves that leave the line give `departs_at` with the line's `analysis_score` and `search` sources;
`analysis_ends_at` where the PV is shorter than `length`; `search: true` with no moves gives the
`best` and `played` `analysis_score`s from the record's `evaluation`; a position inside an explored
line has no analysis lines; ply *N+1*'s record never answers a line that starts with ply *N*'s move; a
ply whose record is not stored answers as v8 and starts no analysis. `compare_lines`: analysis
ranking by `analysis_score` when every move has an analysis line, search ranking with
`analysis_score` beside otherwise, never mixed; a line extended past its given moves has one search
admitted, its `end_score` at the end of the given moves (`end_score_at` = their length), its
extension plies `source: "search"` with no score, and nothing searched at the extension's end. T2:
`net.white` = `standing.end` − `standing.start`; `standing_white` per ply; `leader_at_end`. T3:
`search: "fresh"` serves both scores and never replaces the analysis's; `disagrees_with_analysis` on a
kind difference and above 1.00, not at 1.00 or below; the `disagreement` entry and line hold both
sides' fields (`root_ply`, `evaluated_move`, `pv_followed`; `path`, `fen`). J1 origins (§5.1): a v9
`handle` line carries `origin` (`s`) and `plies_origin` (`x`) equal to the answer's ledger sources;
`origin()` on a v8 run's handle and call lines gives the same per-ply origins as v9 records for the
same moves (`explore` with and without `continue_with`; a `compare_lines` played line with an
extension, a candidate line); a v7 `explore` line all `agent`; a material proposition over the
analysis part of an extended line is `analysis`, over its extension `search`; a cited handle resolved
through `by_handle`; on Test 1's evidence file, every citation resolved and the ten material counts'
origins as 0.1 reads them. J1: the bundle's evidence
holds only verified citations; a line's standing computed from the FEN, not copied; `source` from the
handle lines; a v7 and a v9 citation of the same line render identically; no arm or run in the
bundle; the schema's `search_only` and the kind `source`; the report's M1b (with `source`), M1s, M1b +
M1s and the M1s bar on constructed judgings. H1: each rule holds its 0.1 case (186492056006-22 #2 by
F1 and F2, #3 by F1; a grade named against its judgement by F3) on constructed calls; a level start
never holds F1; the review's two-count sentence `uncheckable`, not held; two cited material
propositions, a material number backed only by a cited handle, two grade words — each `uncheckable`;
the explicit propositions read for a sentence equal the server's `verified` entries for its explicit
cites (scripted session); a sentence outside the word lists not held; two holds then `exhausted`;
`search_numbers` counted. R1: `server-worktree` passes the checkout's `core.autocrlf`, stops on a data
file that differs and names it, and leaves an existing worktree in place; `freeze.py` refuses a
variant whose worktree fails the check; a mismatch names the differing files. M1: §7.4.

### 7.2 Measurement, in order

1. **Replay (no model).** (a) The eleven cases of 0.1's first two rows, put to v9 as in §2.5. **Bar:
   11 of 11** give the analysis record's line and score, or `departs_at` where the agent's moves left
   it. (b) The frame check over **every final sentence** of Test 1's submissions (A 216, H 237) and of
   the evaluation sample's HS rev. 4 submissions, against the judge's verdicts: the wrong sentences it
   holds, and the **false holds** (sentences the judge marked `ok` that it holds). **Bar:** false
   holds at most 2% of the `ok` sentences; held wrong sentences reported case by case; the
   `uncheckable` sentences counted by rule and reason.
2. **Judge v2 on Test 1 (development data).** Test 1's 69 commentaries (both arms) judged again with
   judge_v2, one fresh judging, audited, beside **a constructed bundle**: the 0.1 table's eleven
   sentences rewritten to state their source ("별도 탐색에서는 …", the same numbers and citations).
   **Bar:** in Test 1 as written, none of the eleven states a separate search, so each is `wrong`
   with kind `source` (or `ok` where the reference holds nothing for it); in the constructed bundle,
   each of the eleven is `search_only`; the other wrong sentences (H's four, A's four) still `wrong`;
   every change of verdict from judge_v1 listed with the judge's reason and read before the freeze. It
   checks the rubric, not the agent: no decision is read from it.
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
moment-runs without commentary no more than A's; the worst case holds — **and M1s's upper bound at
most +2.0** (review F3): a candidate may not add, beyond A, more than two sentences a hundred that
present a separate search disagreeing with the analysis. Also reported, each with intervals: **M1b +
M1s** (§5.3); `A@v9 − A@v7` (what the tools do) and `H@v9 − A@v9` (what the harness does with them);
disagreements per arm; the frame check's states, `uncheckable` counts and M1b per state;
`search_numbers`; doubtful sentences per arm; cost.

The M1s bar is the M1b bar's size because a `search_only` sentence is true but disagrees with the
analysis the product shows; it is fixed now, before any Test 2 run.

### 7.4 M1 — the second Test set

- `sets_v1.json` gains a set **`test2`**: four new chess.com games of the owner's, played after
  Test 1 was opened (2026-11-09), PGNs in the data directory, checked by digest as RX0-D §2 says.
- **Its own lifecycle** (review R1). Today `test` is written into the code: `manifest.open_test`
  reads `sets["test"]`, builds `base/test` and writes `test_opened`; `__main__` offers
  `train|validation|test` and checks `test_opened` and `freeze.run_problems` only for `test`;
  `report.py` refuses `test` beside another set and decides from `/test`. v9 makes Test a **kind of
  set**: `TEST_SETS = ("test", "test2")` in one place, and for each test set *t*:
  - `open-test --set t --freeze <record>` opens *t* alone: it refuses a set already opened, a freeze
    record that `freeze.problems` rejects, or a freeze record already used to open another test set;
    it chooses *t*'s moments, builds and seals `base/t`, and writes **`opened[t]`** (`freeze`,
    `freeze_sha256`) in the manifest. `test_opened` is read as `opened["test"]` (Test 1's record
    stays valid).
  - `annotate`, `reference`, `requests` and `run` on *t* refuse unless `opened[t]` is present, and
    `run` checks the spec against *t*'s own freeze (`run_problems(opened[t], spec)`).
  - The freeze record for Test 2 is **`freeze_v2`**: `freeze_v1`'s fields plus the test set it is for
    (`"for": "test2"`) and the judge version (`judge_v2`); `open-test` refuses a record whose `for` is
    not *t*.
  - `report.py`: per-set pairs over every set held; a report that holds any test set holds **only
    that one** (test beside train, validation or the other test set refused); its decision is read
    from `<a> − <b> / t`.
  - Tests: Test 2 opened with a `freeze_v2` record and Test 1's still valid; `test2` refused before
    it is opened and with Test 1's freeze; a run of `test2` checked against `freeze_v2`; a report
    holding `test` and `test2` refused; a Test 2 report deciding from `/test2`.
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
| Q6 | Judge Test 2 with judge_v2 (J1), with `search_only` outside M1b and its own bar (M1s's upper bound at most +2.0)? | Yes. A sentence that says it reports a separate Calliope search, and is true of it, is not a false statement (§0.2), and judge_v1 cannot tell the two apart; the M1s bar keeps a candidate from passing by moving disagreements out of M1b. The cost: Test 2's numbers are not comparable with earlier judgings, which no decision needs (each Test is judged on its own); M1b + M1s is reported as the judge_v1-like rate. |
| Q7 | T3's threshold: a difference in kind, or more than 1.00? | Yes, the engine check's (LT §9.4 Q2), so the two flags mean the same. |
| Q8 | Read a number stated without a source as the analysis's (§5.2)? | Yes. The commentary explains the analysis's verdict, and a reader takes "the engine's evaluation" for the one the product shows; a separate search must say so to be judged as one. |

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
| Replace the analysis with the latest search | §0.3: not done, for four reasons; a better analysis is a new version before the commentary (§9). T3 (now §2.6) shows where the two disagree and records it as that packet's input. |
| §2.1's open point: is every ply in the base? | §2.1: the bases hold the fixed moments' plies; T1 reads only stored records and starts no analysis. |

**rev. 2 → rev. 3.** Re-review of rev. 2 (PR #161, HEAD `19c0882`): **NOT_READY**, three blocking
findings and three others. The re-review also carried rev. 1's review (F1–F4, N1, N2), which had
not been applied in rev. 2; its open items are the rows marked "rev. 1". Each claim was checked
against the code before it was applied.

| # | Finding | Applied |
| --- | --- | --- |
| F1 (P1; rev. 1 F1) | An analysis line's score was put in `end_score`, though it is the root's evaluation of a move, not a search at the prefix's end; with no moves, which of the record's scores is "the root score" was not said. | §2.2: `end_score` keeps v8's meaning only (a search at the line's end); an analysis score is an `analysis_score` with `root_ply`, `root`, `evaluated_move`, `line`, `score_at`, `pv_followed`, `depth`, `profile` and `score_ref`. §2.3: no moves gives the record's `evaluation` as `best` and `played` `analysis_score`s. §2.4: `compare_lines` on the same contract. Tests in §7.1. |
| F2 (P1; rev. 1 F2) | The frame check matched a cited `balance` and a word anywhere in the sentence: "백은 이 수순에서 9점을 얻었지만, 전체 물질은 여전히 흑이 1점 앞선다" (right) would be held; handles cited directly were not related to the server's expansion. | §4.1: a rule applies only when the sentence cites exactly one explicit proposition of its kind, no handle backing material, and exactly one count equal to its number (F3: one judgement, one grade word); otherwise `uncheckable`, recorded, not held. The check reads explicit propositions only, and a test pins them to the server's `verified` entries. The review's sentence is a test. |
| F3 (P1, new) | `search_only` exempted any sentence true of a cited search, including one that presents the number as the analysis's, and M1s did not bar adoption. | §5.2: a number stated without a source, or as the analysis's, is read as the analysis's; `search_only` only when the sentence says it reports a separate search; otherwise `wrong` with the new kind `source`. §5.3, §7.3: an M1s bar (upper bound at most +2.0), fixed before Test 2. §4.3: the harness's message asks for the source in words. §7.2 step 2: a constructed bundle checks both readings. Q6, Q8. |
| R1 (P2; rev. 1 F4) | `test` is written into `manifest.py`, `__main__.py` and `report.py`; `test2` had no lifecycle of its own. | §7.4: `TEST_SETS`, `open-test --set`, `opened[t]` per test set (Test 1's `test_opened` read as `opened["test"]`), `freeze_v2` naming the set it is for, every command and run checked against its own set's freeze, a report holding one test set only. Tests listed there. |
| R2 (P2) | §2.5 called the analysis's score and a new search's "the same position", though one is the root's evaluation of a move and the other a search after it. | §2.6: said as two positions; the `disagreement` entry and line record both (`root_ply`, `evaluated_move`, `pv_followed`; `path`, `fen`), turned to White's view. |
| N1 (P2; rev. 1 N1) | The worktree step named for `freeze.py` does not exist. | §6: confirmed (`run.py` only reads `RX_DATA/servers/agent-tools-v7`); a `server-worktree` command makes it with the checkout's `core.autocrlf` and compares the build's data files; `freeze.py` runs that check before the freeze. |
| N2 (P2; rev. 1 N2) | 0.1's cases rested on material outside the PR. | `rx-evidence/af/wrong_cites.py` and its output `test1-wrong-cites.json` (all 19 wrong sentences of both arms: sentence, verified citations, the serving call and its ledger, the reference's lines); §0.1 names them. |
| rev. 1 F3 | Analysis not stored was started implicitly. | Resolved in rev. 2 (§2.1), as the re-review found. |

**rev. 3 → rev. 4.** Re-review of rev. 3 (PR #161, HEAD `7a6d49a`): rev. 2's findings resolved
(N2 in part); **NOT_READY** on two new blocking findings and one other, each checked against the
code and the records before it was applied.

| # | Finding | Applied |
| --- | --- | --- |
| F1 (P1) | Judge v2's `source` could not be restored for an `x` handle: the recorder's `handle` line holds `ref`, `kind`, `source` (`facts_tree`), `address`, `identity`, `line_key`, nothing of where its plies came from; a `material` count on a session search's line would be read wrong. | Confirmed (`record.Recorder.handle`; Test 1's `x23` is `facts_tree`, its plies' sources only in the `explore` answer). §5.1: origins per ply and per proposition (`agent`, `analysis`, `search`; a material count by its own segment); v9 writes `origin`/`plies_origin` on the `handle` line; v7/v8 runs restored through the handle's `call_id` and the serving call's answer; one function in `judge.py`; tests in §7.1. §5.2: the rubric reads `agent` as it reads `search`. |
| F2 (P1) | §2.4 put a `compare_lines` extension's `end_score` at the extension's end, which needs a second search; today one search runs at the end of the given moves and the extension follows its PV (`end_score_at` that ply). | Confirmed (`session._compared_line`). §2.4: the one search kept, `end_score` at the end of the given moves, `end_score_at` that ply, the extension's plies `search` with no score; the `analysis_score` beside it; T3 compares the two (§2.6). Test in §7.1. |
| N1 (P2) | The evidence script matched a cite against `verified` ids only: 17 of 31 citations unresolved (14 of 19 cases), since a cited handle expands into `<ref>:line`, `<ref>:score` entries. | `wrong_cites.py` resolves a cited handle through `by_handle`, restores each handle's origin as §5.1 specifies and gives each material count its segment origin; regenerated: **0 unresolved**; the eight material counts behind 0.1's line cases `search`, the two of row 3 `analysis` (their segment is the analysis part of a line `compare_lines` extended). |
| Found while checking | Rev. 2 said the session's searches were shallower than the analysis's. | Not so: the analysis is `d12_mpv5_v1` at depth 12 (multi-PV, before the move), the session's searches the same profile. §0.1, §0.2 and §0.3 corrected: the two differ in root, not depth, and T1 rests on the grade's own record and the product's, not on a better search. |

