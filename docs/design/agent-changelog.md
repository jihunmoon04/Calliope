# Agent change log

One entry a change (TB-D §2 P1). Each entry gives the date, what changed, why, the commit and the score
row it produced (`docs/design/rx-evidence/scorecard.jsonl`, by its `name`). A change between milestones
needs an entry here, its tests and a score row. A design document is written only for a new direction,
and an independent review happens at milestones (CLAUDE.md).

## 2026-11-10 — TB: the Claude API, the score command, harness rev. 9 (branch `agent/tb`)

**Commit:** d891913, 94e5596 (the change; its score row follows it).

Design: `agent-tb-design.md` rev. 4 (re-review READY_WITH_CORRECTIONS, applied).

- **C, the Claude API.** A model named `claude-…` goes to Anthropic's Messages API through the official
  SDK (`anthropic==2.7.0`, in the `agent` extra), in the request child (`tools/rx/claude.py`,
  `tools/rx/request.py`).
  - The answer is normalized for the loop (`content`, `tool_calls`), with its original blocks kept in
    `blocks` and sent back unchanged.
  - Tool answers become `tool_result` blocks first in one user turn; `[tool error]` becomes
    `is_error`.
  - Request settings: `max_tokens` 16,000 (the judge's 4,000), effort `medium` unless named.
  - A cut answer is logged only, never kept or run; two cuts in a row are `moment_cut`. A refusal is
    `moment_refused`.
  - `usage.input_tokens` is the total input (uncached, cache read and cache write); the parts are
    kept beside it.
  - Cost comes from a price table with Haiku 5.5's 100k step.
  - The default model stays `anthropic/claude-haiku-5.5` on OpenRouter: the owner uses OpenRouter's
    credit first (on 2026-11-10, $6.73 left of the key's $50 limit), then the Claude API (about $20 a
    month). An OpenRouter Anthropic model's requests are counted by the Claude API's free
    `count_tokens` when its key is set.
- **P2, the score command** (TB-D rev. 5).
  - `python -m tools.rx score run` runs H on 184800218248 and 185264271324, one run each, and makes
    judge v2's bundle.
  - A Claude Code session judges it with judge v2, and its transcript is audited.
  - `score finish` writes the scorecard row from the audited judgings. A moment without commentary is
    a failure in the rates.
  - `judge_v2r`, an API judge from rev. 4, was removed before any use (the owner: judging runs in
    Claude Code sessions).
- **B, harness rev. 9 (tools v10).**
  - **Tools v10:** answers and descriptions point to `detail(ref)`, never to the full view
    (`agent_tools_v10`, `agent_guidance_v15`).
  - **The rev. 9 harness:**
    - serves 10 tools without `view`; the gate drops a `view` that is still sent;
    - refuses a tool answer above 24,576 bytes, with a message by tool;
    - uses `harness_guide_v1` as its system message;
    - starts each moment in a conversation of its own with the story so far (`harness_v5`).
  - **The guard** (`tools/rx/guard.py`) counts every request before it is sent:
    - over 80k it compacts: notes, `tool_choice` none, at most 2k tokens, one restart a moment;
    - over 95k after the restart, `moment_budget`;
    - on OpenRouter it estimates against 85k.
  - **Ends:** moment ends (`moment_budget`, `moment_cut`, `moment_refused`) go on to the next moment;
    the run's bounds end the run. A run may have a cost bound (`--cost`).
  - **Versions:** tag `agent-tools-v9` (main 5c8a779) and its server worktree, so rev. 8 still runs on
    v9 (`--tools v9`). `server-worktree` now reads the checkout's line endings from its files, since
    WSL's git does not see the Windows checkout's `core.autocrlf`.
- **Smoke run** (not a score row: no judging), rev. 9 on OpenRouter (`anthropic/claude-haiku-5.5`),
  185264271324, run `01M71XY3E06MQBHDVTCJ1SQEX5`. Against the same game in `af-pilot-2` (rev. 8, run
  `01M7040XE87FH2931G9X9HCSJA`):

  | | rev. 8 (af-pilot-2) | rev. 9 (smoke) |
  | --- | --- | --- |
  | End, moments submitted | done, 3 of 3 | done, 3 of 3 |
  | Requests | 38 | 29 |
  | Largest request (input) | 146,721 | 66,952 |
  | First request (fixed prefix + task) | 18,813 | 15,385 |
  | Input tokens | 2.89M | 1.16M |
  | Cost | $0.231 | $0.062 |

  - The guard's estimate (OpenRouter) was 66,502 against 66,952 used.
  - No compaction, refusal or cut happened.
- **Score rows** (`scorecard.jsonl`, both on OpenRouter, judged by judge v2 in Claude Code sessions on
  `claude-opus-5-5`, audits passed):

  | | `tb-rev8-openrouter` (rev. 8, tools v9) | `tb-rev9-openrouter` (rev. 9, tools v10) |
  | --- | --- | --- |
  | Completion | 6 of 6 | 6 of 6 |
  | Largest request (input used) | 148,262 / 130,205 | 75,957 / 76,659 |
  | Cost of the two runs | $0.382 | $0.167 |
  | M1b (wrong per 100 sentences) | 4.55 (2 of 44) | 6.12 (3 of 49) |
  | M1s | 0 | 0 |
  | M2b (decisive causes explained) | 0.667 (4 of 6) | 0.833 (5 of 6) |
  | Score | 4.17 | 4.33 |

  - Every wrong sentence in both rows is the same kind: a side misread (`piece_or_side`), or a
    material change read the wrong way. Rev. 8 had two; rev. 9 had three, plus one `doubtful` (a
    garbled sentence).
  - One run a game and six moments are too few to tell the two revisions' quality apart. A
    difference of one sentence or one cause is inside the noise.
  - What the rows do show: rev. 9 holds every request under 100k and costs 44% of rev. 8, with no
    loss of completion.

## 2026-11-10 — rev. 9's guide condensed (`harness_guide_v2`, TB-D B2)

**Commit:** 1a8dc6b, cef18c3 (the change; its score row follows it).

- **What changed.** The system message of rev. 9 is `harness_guide_v2`.
  - It drops what the stage messages and tool descriptions already say: the writing steps, the
    materials list and the long example.
  - It gathers the rules on whose piece and whom a change favours into one section, because every
    wrong sentence of the first rows was of that kind.
  - The server's tool descriptions are unchanged.
- **Fixed prefix**, counted by `count_tokens`: 9,019 tokens (guide 3,509, ten tools 5,324, task 178);
  with v1 it was 14,284 (guide 8,774).
- **Score row** `tb-rev9-guide2-openrouter` (OpenRouter; judge v2 in a session on `claude-opus-5-5`,
  audit passed):

  | | `tb-rev9-openrouter` (guide v1) | `tb-rev9-guide2-openrouter` (guide v2) |
  | --- | --- | --- |
  | Completion | 6 of 6 | 6 of 6 |
  | First request | 15,385–16,584 | 10,116 / 10,120 |
  | Largest request | 75,957 / 76,659 | 69,783 / 69,245 |
  | Cost of the two runs | $0.167 | $0.152 |
  | M1b | 6.12 (3 of 49) | 9.52 (4 of 42) |
  | M2b | 0.833 (5 of 6) | 0.667 (4 of 6) |
  | Score | 4.33 | 4.00 |

  - Three of the four wrong sentences are in one commentary (185264271324, 23.Rxe5):
    - a line's number read as the analysis's without a source;
    - a segment written as the whole line;
    - a cause the reference does not show.
  - The fourth (184800218248, 6...b5) presents an attack that held before the move as made by it.
  - One run a game is too few to separate this from noise. The difference is one sentence and one
    cause.
- **A second run of each guide** (`tb-rev9-guide1-openrouter-2`, `tb-rev9-guide2-openrouter-2`; same
  judging, audits passed). Pooled over the two rows of each:

  | | guide v1 (2 rows) | guide v2 (2 rows) |
  | --- | --- | --- |
  | Completion | 12 of 12 | 12 of 12 |
  | Largest request | 77k | 80k |
  | Cost a row | $0.15–0.17 | $0.15 |
  | M1b | 6.3 (6 of 95) | 11.5 (10 of 87) |
  | M2b | 0.75 (9 of 12) | 0.667 (8 of 12) |
  | Score | 4.25 | 3.92 |

  - Both pairs point the same way: v2's commentaries have about twice as many wrong sentences.
  - Its added errors are the kinds v1 explains at length and v2 cut short:
    - sides misread: whose pawn d6 is; castling taking the rook, not the king, out of the centre;
    - a change written as a standing ("White -3 remaining");
    - a segment written as the whole line;
    - an attack that held before the move written as new.
  - v2 saves about 5k tokens of cached prefix a request (a cache read: about $0.00005), so its
    saving is mostly context room, not money.

## 2026-11-10 — rev. 9 back to `harness_guide_v1` (TB-D rev. 6)

**Commit:** c20b027 (the change; its score row follows it).

- **Change.** The owner chose v1 after the pooled rows: v2's wrong sentences were 11.5 a 100 against
  v1's 6.3.
  - `HARNESS_GUIDE` is `harness_guide_v1` again; v2 stays reachable with `--harness-guide`.
  - TB-D B2's 10k target is set aside. The 100k request limit holds with v1 (largest request 77k).
- **Score row:** none new. The current configuration is the one `tb-rev9-openrouter` and
  `tb-rev9-guide1-openrouter-2` scored.

## 2026-11-10 — the implementation review applied (TB-D rev. 7, §11)

**Commit:** 2bbd856 (the change; its score row follows it).

- **The review.** An independent session reviewed `agent/tb` (c20b027): READY_WITH_CORRECTIONS, two
  P1 holes in the 100k guarantee.
- **The guard on OpenRouter.** It now takes the larger of the Claude count and the usage estimate.
  The count alone was 20–28% low late in a moment, because OpenRouter keeps the thinking outside it.
  The rows above never came near a limit: their largest count was 64k.
- **Compaction:**
  - the notes re-ask is counted before it is sent;
  - the cut prefix is tried when the whole one is over;
  - the request is logged;
  - a refusal is `moment_refused`;
  - unpassed facts are marked as such.
- **The loop:** a cut answer's calls are logged as `tool_unsent`. C4's handling applies only to rev. 9
  and the Claude API, so rev. 8 and arm A replay as they ran. `pause_turn` is an error.
- **Bounds:** rev. 9 runs get a $1 cost bound by default; `score` passes 20M tokens and $1.
- **C's done criterion is pending:** no `messages.create` has run yet, since the owner uses OpenRouter
  first.
- **Tests:** the review's list was added (twelve in `test_tb_harness.py`, two in `test_tb_claude.py`).
- **Confirming runs** (`tb-rev9-reviewed-openrouter`, after the fixes): 6 of 6 moments, $0.149, the
  largest request 68,388 with the guard's size at 68,142 (`counted+usage`); no compaction.
- **Their first judging was refused.** The judge for `e118b76e` listed the file names of a folder
  outside its directory four times, though it opened none of them; under the rule the judging is
  refused. Its files and audit are kept as `attempt1` beside the new ones.
- **Re-judged** in a new session (the brief now forbids any listing outside the directory); the audit
  passed (36 calls). Row `tb-rev9-reviewed-openrouter`: M1b 6.82, M2b 0.667, score 3.83, 6/6, $0.149.
  This is within the spread of the earlier guide v1 rows (M1b 6.12 and 6.52), so the review's fixes
  left quality unchanged.


## 2026-11-10 — whose piece, and a change written as the standing (tools v11, harness rev. 10)

**Commit:** 123a53e (the change; its score row follows it).

- **What the rows showed.** The five rev. 9 rows (judge v2) hold 19 wrong sentences:
  - 6 on whose piece or whose side;
  - 3 on a change written as the standing, or with the wrong sign;
  - 2 each on a segment written as the whole line, a search number given no source, a cause not in
    the reference's lines and an old attack written as new;
  - 2 others.
  - The largest single case is the same one: four rows (rev. 8 included) give White's d6 pawn at
    184800218248-57/58 to Black.
- **The cause of the d6 case.** The line ledger named captured pieces without their owner
  (`by_black: ["pawn d6 (1)"]`). Pieces at the end were a letter whose case gave the side (`gone: ["Pd6"]`).
  The ply rows' `says` did name the owner, but the summaries the agent quotes did not.
- **Tools v11** (`src/calliope/agent/lines.py`). The ledger names each piece with its owner:
  - `captured`: `by_black: ["White's pawn d6 (1)"]`;
  - `end`: `gone: ["White pawn d6"]`, `moved_pieces: ["Black rook d6"]`;
  - the ledger's note says so.

  v10 is tagged `agent-tools-v10` (acf82b4, local until the merge) and runs from its worktree.
- **Harness rev. 10** is rev. 9 with the frame check `harness_frames_v2` (`tools/rx/frames.py`):
  - "물질 차이" and "물질은" written for a cited change are held under F1 when the standing differs.
    v1 only counted them as `ambiguous`; judge v2 marked them wrong. The reply adds how to write a
    change ("흑이 1점을 잃는다").
  - A sentence whose counts are all the proposition's number ("3점을 잃고 … 물질은 -3") is read as
    one count. v1 left it `uncheckable`, which is why the rev. 9 cases were never held.
  - `ambiguous` is still counted, so rows stay comparable.
- **The score command** defaults to rev. 10.
- **Tests:**
  - new: `tests/agent/test_sides.py`;
  - updated: `test_lt.py` (the owner names), the v11 version tests, and the frame-check stub.
- **Left as they were:**
  - a sign error with a gain verb ("백은 3점을 얻는다" for a change of -3);
  - which piece a castling moved;
  - search numbers, segments.

  These need rules of their own.
- **Score row** `tb-rev10-sides-openrouter` (bundle 94d6ca40, judged by a Claude Code session; the
  audit passed): M1b 10.64, M1s 0, M2b 0.833, score 4.0, $0.154, 6/6 moments. That is within the
  spread of the rev. 9 rows (M1b 6.12–13.33), so it shows no gain.
  - 5 of 47 sentences were wrong. None confused whose piece it was, so the owner names did their job.
  - 3 were still about material standing:
    - a change written as the difference (-5 and -2 where the standing was -4 and -1);
    - "the standing crosses over to Black" when Black was already ahead;
    - "no material change" for a line that went from 0 to -2.
  - The frame check held none of them (holds 0; F1 uncheckable 6, ambiguous 2). The model cited line
    handles directly, and the check cannot read a handle's number. Reading the cited handle's ledger
    at the ply the sentence names is the next rule to try.

## 2026-11-10 — the standing read from the cited line (harness rev. 11, frame check v3)

**Commit:** 748df86 (the change; its score row follows it).

**Why.** In judging 94d6ca40 (rev. 10), three of the five wrong sentences framed material wrongly. The
frame check held none of them:
- one cited two `material` propositions;
- the others cited a line handle with no proposition.

Two ledger field names (`standing`) were also written in the commentary. One of them was in a wrong
sentence.

**What.** Harness rev. 11 is rev. 10 with `harness_frames_v3` (`tools/rx/frames.py`). Like v2, every
rule holds only where the sentence maps to one record:
- **F1 through a handle:** a standing word or phrase with counts, citing one line handle. The line is
  read at the ply the sentence names ("6수 시점", or the last move of the line it writes, else the
  line's end). The sentence is held when its counts are the change there and not the standing.
- **F1 over several propositions:** each count is matched to the one cited `material` proposition
  of that size. 8856bf87 #2 ("-5가 되었다가 … -2로") is held with the standings -4 and -1.
- **F4 crossover:** "흑 쪽으로 넘어간다" is held when that side was already ahead at the line's start
  (a869f4f9 #4: Black was 1 up), or is not ahead at the named ply.
- **F5 no change:** "물질 변화가 없다" is held when the standing at the named ply is not the start's.
- **F6 ledger term:** `standing`, `net`, `captured` and the other field names are held in any
  sentence.
- A search's score handle counts as a line. f8ee0f37 #6 (7.Bxb5 in the explored line, 7...cxb5 in
  the search's) cites two lines, so it stays uncheckable rather than being read wrongly from one.

The score command defaults to rev. 11.

**Tests.** `tests/agent/test_frames_v3.py`. Every case is a 94d6ca40 sentence with its line's
standings; the right sentences of the same items are not held. Also updated: the revision tests in
`test_sides.py` and `test_tb_score.py`.

**Not covered.**
- A claim over two lines, which needs the search line's standings.
- 670e5617 #7: an evaluation gap called unexplained.
- f8ee0f37 #1: an existing weakness written as new.
- **Score row** `tb-rev11-frames3-openrouter` (bundle d5ea37e0, judged by a Claude Code session; the
  audit passed): M1b 5.88, M1s 0, M2b 0.667, score 4.17, $0.187, 6/6 moments.
  - 3 of 51 sentences were wrong; rev. 10 had 5 of 47. This is the lowest M1b of the rev. 9–11 rows,
    but the rev. 9 rows alone ranged 6.12–13.33, so one row does not settle it.
  - The check held one sentence: "라인 끝에서 백 물질은 -2로 내려앉는다", a change written as the
    standing (v2's rule). It was rewritten as "백은 누적 2점을 잃는다". No v3-only rule held, and no
    ledger term was written.
  - One material error was left: "물질은 다시 같아집니다" where the line stood at White +1. "같아지"
    is in no word list.
  - The other two errors were a cause the line does not show and the position after the move
    described as before it.
  - The hold's own reply still writes "(원장의 standing)", against F6.

## 2026-11-10 — whole-game commentary in three tiers (WG-D, harness rev. 12; branch `agent/wg`)

**Commit:** f657d35 (the change; its score row follows it).

**Why.** The owner asked to stop correcting the fixed moments for now and widen the commentary to
the whole game. The owner took WG-D rev. 1's recommendations on Q1–Q5, and asked for the
implementation without a review first.

**What.** Harness rev. 12 is rev. 11 with WG-D §1–§5 after the fixed moments.
- **Tiers** (`tools/rx/tiers.py`): read from `game_overview`, fetched by the harness.
  - Tier 2: the fixed moments.
  - Tier 1: every other ply graded inaccuracy, mistake or blunder, or labelled miss, brilliant or
    great.
  - Tier 0: the rest.
- **Tier 1** runs in batches of up to 8 plies, one conversation a batch:
  - The system message is `harness_tier1_v1`. The first message holds `harness_v6`'s `tier1_task`,
    the story so far and each ply's `ply` digest, fetched by the harness and logged as
    `harness_call`.
  - The tools are `detail` and `submit_commentary` only. The submission has one item a ply.
  - The gate allows only the batch's plies, and the frame check v3 runs as for tier 2.
  - A batch whose first message counts over 60k tokens is halved. A batch has 6 turns at most, no
    compaction, and 2 re-asks when nothing was accepted.
- **Tier 0:** one code sentence ("앞서 본 수순대로 진행되었다 (… 까지).") at the first tier-0 ply after
  a commented ply, when the game followed a cited line at least 2 plies past it. It is logged
  (`tier0`) and not stored or judged.
- **Logs:** `tiers_plan` (tier 1's plies, the judged sample, counts by tier), `batch_start`,
  `batch_end`, and `tiers` (coverage, ends by ply, totals by tier). The frame check's lines carry
  `tier`.
- **Measuring:**
  - `python -m tools.rx reference <set> --tier1` writes unreviewed references for each game's
    sample: the 3 tier-1 plies with the largest loss. The validation set's 12 are added.
  - `judge.bundle` adds the sample's commentaries beside the fixed moments.
  - The score row adds `rates_tier1` and `completion_tier1`; each game adds `tiers` and
    `frames_tier1`.
  - The score command defaults to rev. 12.

**Tests.** `tests/agent/test_wg.py` covers:
- the tier, batch and sample rules;
- the followed-line sentence;
- each accepted item of a batch counted;
- the gate;
- a whole run on stubs: one batch, tier 1's tools, a batch without a submission, a halved batch,
  and rev. 11 without tiers;
- the bundle's sample, the frame counts by tier, and rev. 12's messages and guide.

The score and frame tests take revision 12.

Score row: none yet. The first rev. 12 runs were stopped when the review found R2–R4 (WG-D §8),
and no row was written.

## 2026-11-10 — the review's corrections (frame check v4, WG-D rev. 2)

**Commit:** 4616cd6 (the change; its score row follows it).

**Why.** The owner asked for a review of everything since `acf82b4`, including the merged
`agent/sides`, split into parts. Four reviewers read one slice each. Their findings were
reproduced against the code, and the owner asked for them to be fixed and the runs repeated. The
findings and what was applied are in WG-D §8 (R1–R11).

**What.**
- **Frame check v4** (`harness_frames_v4`, harness rev. 12). It is v3 without v3's false holds:
  - a count written as a gain or a loss is not read as a standing, and a count of plies is no
    count;
  - F5 reads a cited proposition's own segment, and is `uncheckable` when the sentence names a
    segment's start;
  - two crossovers in one sentence are `uncheckable`;
  - F1 on a proposition holds only when the change and the standing differ in size;
  - the replies name no ledger field.

  An unknown version is refused. Rev. 11 keeps v3, as its row ran.
- **Tier 1 and tier 0:**
  - a single-subject call in a batch counts for its ply;
  - tier 0 needs a line followed by its own moves from the commented ply or the next one;
  - the `tiers` line is written on every end;
  - `tier1_refused` replaces a refusal that named tools tier 1 lacks;
  - the tier-1 guide names `agent` in the submission and drops `facts`, `definitions`,
    `judge_move` and explored lines;
  - digests are fetched once a ply.
- **Checker:**
  - the frame check's reads carry `before` (the model's call they were made for), and the checker
    pairs them ahead of it;
  - a call the server's schema refused is logged `tool_unsent` (`server_schema`).
- **Score row:**
  - `cost`, each game's `totals` and `largest_request` are tier 2's;
  - added: `cost_whole_run`, `totals_whole_run` and `judging.items_tier1`;
  - `bundle` checks its references before making a part;
  - `reference --tier1` reads every range of 200 plies;
  - `frames_tier1` keeps every submission.
- **Docs:** WG-D rev. 2 (§2–§5 corrected, §8 the review).

**Tests.** `tests/agent/test_wg_review.py`:
- v4 holds none of the five false holds, and still holds what v3 held rightly;
- v3 is unchanged;
- each tier fix;
- a batch that runs out of turns;
- the `tiers` line on a cost end;
- the checker's pairing and schema-refused calls;
- a rev. 12 row's tier-2 totals;
- the bundle's reference check;
- the row's tier-1 fields.


**Score row** `wg-rev12-openrouter` (bundle 1fc68379, two parts judged by Claude Code sessions;
both audits passed). It is the first whole-game row.
- **Tier 2:** M1b 5.88, M1s 0, M2b 0.833, score 4.33, 3 wrong of 51 sentences, $0.139, 6/6
  moments. This is within the rev. 9–11 rows' spread.
- **Tier-1 sample:** 6 plies, 0 wrong of 18 sentences, score 3.83, 6/6.
- **Tier 1 in full:** all 34 plies of both games were commented (21 and 13), in 5 batches, with no
  hold.
- **Tier 0:** 4 sentences.
- **Cost:** the whole run cost $0.256. Tier 1 cost $0.116, which is 84% of tier 2.
- **The checker:** both runs pass `check` (whole), which neither rev. 11 run did.
- **WG-D §5's done criteria:**
  - three are met: every tier-1 ply commented, tier 2 within the spread, tier 1's M1b at most
    twice tier 2's;
  - "tier 1 costs at most half of tier 2" is not met. WG-D §2 estimated $0.02 a game; the runs
    spent $0.083 and $0.033.
  - The first batch of 184800218248 ended on the guard's limit after all 8 plies were accepted.

## 2026-11-10 — tier 1 cheaper (harness rev. 13)

**Commit:** 9b9db4e (the change; its score row follows it).

**Why.** In `wg-rev12-openrouter`, tier 1 cost 84% of tier 2, against WG-D §5's half. 51–53% of
tier 1's cost went on submissions the server refused whole. 224 of their ~390 violations were one
mistake: the model wrote the handles it cited into the sentence's text ("판정은 부정확입니다
(j11)."). S3 reads such a word as neither a move, a square nor a number. Each batch then took 2–4
rounds, and each round cost $0.005–0.012 (most of it reasoning output and the cache write of a
longer conversation). Each batch also asked the model once more after its last acceptance
($0.001–0.002).

**What.** Harness rev. 13 is rev. 12 with:
- **Handles out of a tier-1 sentence's text.** Before the call is sent, a bracket holding only
  handles that the sentence cites ("(j11)", "(c47, s111)", "[b16.…]") is taken out. A square
  "(e4)", a score "(+0.37)" or an uncited name stay. The run logs `handles_stripped`. Tier 2 is as
  it was.
- **The tier-1 guide v2** (`harness_tier1_v2`): handles go in `cites` only, with a wrong and a
  right example, and each ply needs its own judgement handle.
- **A batch ends once every ply of it is accepted.** The loop sends no further request
  (`Gate.done_early`). A batch with a ply left out still gets its answer.
- The score command defaults to rev. 13. The start line records `harness_tier1` and
  `harness_tier1_lean`.

**Tests.** `tests/agent/test_wg_lean.py` covers:
- what is taken out and what stays;
- rev. 13 sends the stripped text and leaves tier 2 alone;
- a batch ends without a further answer, while rev. 12 still asks for one;
- a ply left out;
- rev. 13's versions and start line.

**Score row** `wg-rev13-openrouter` (bundle 01b80a7b, two parts judged by Claude Code sessions;
both audits passed).
- **Tier 2:** M1b 4.26, M1s 0, M2b 0.833, score 4.5, 2 wrong of 47 sentences, $0.146.
- **Tier-1 sample:** 1 wrong of 16 sentences (M1b 6.25), score 3.17, 6/6.
- **Tier 1 in full:** all 34 plies were commented, and 38 brackets of handles were taken out of
  the text.
- **Tier 0:** 6 sentences.
- **Cost:** tier 1 cost $0.079, against rev. 12's $0.116 (−32%). It is 54% of tier 2, still above
  WG-D §5's half. The whole run cost $0.225.
- **Refusals still made:** 3 of 5 batches had their first submission refused whole. What remains:
  - scores and numbers written without the handle that holds them (S3, about 45);
  - handles cited by their short name ("j7" for "j7.…"), which the server does not resolve (S2,
    about 38);
  - a ply without its own judgement (13).
- **Both runs** pass `check`.

## 2026-11-10 — short handles resolved (harness rev. 14)

**Commit:** f64412b (the change; its score row follows it).

**Why.** After rev. 13, 3 of 5 batches still had their first submission refused whole. About 38
refusals were S2, "no verified proposition ['j7', 's94']": a cite written by the handle's short
name, which the server does not resolve. The digest the model was given holds that handle in
full.

**What.** Harness rev. 14 is rev. 13 with one change. Each tier-1 ply's digest gives each handle
it writes a short name (`short_names`). A name two handles share is left out. Before a tier-1
call is sent, a cite or `states` entry written by such a name is replaced with the full handle,
from that ply's own digest (`resolve_short_handles`). A proposition's own id stays as written, and
so does a name from another ply. The run logs `handles_resolved`. Tier 2 is unchanged. The score
command defaults to rev. 14, and the start line records `harness_tier1_short_handles`.

**Tests.** `tests/agent/test_wg_short.py` covers the short names (a shared name left out), the
resolution by the ply's own digest, rev. 14 sending full handles where rev. 13 does not, and
rev. 14's versions.

**Score row** `wg-rev14-openrouter` (bundle 8504e6b3, two parts judged by Claude Code sessions;
both audits passed).
- **Tier 2:** M1b 7.84, M1s 0, M2b 0.667, score 3.83, 4 wrong of 51 sentences, $0.164. Tier 2 is
  unchanged since rev. 12, so its move from rev. 13's 4.26 is the run-to-run spread. It stays
  within the rev. 9–11 rows' range of 5.88–13.33.
- **Tier-1 sample:** 0 wrong of 18 sentences, score 3.67, 6/6.
- **Tier 1 in full:** all 34 plies were commented. 64 short cites were resolved. One batch in five
  had its first submission refused whole (rev. 13: three; rev. 12: five).
- **Cost:** tier 1 cost $0.058 (rev. 13 $0.079, rev. 12 $0.116). That is 35% of tier 2. The whole
  run cost $0.222.
- **WG-D §5's done criteria are all met in this row:**
  - every tier-1 ply was commented;
  - tier 2 is within the spread;
  - tier 1's M1b (0) is at most twice tier 2's;
  - tier 1 cost at most half of tier 2.
- The refusals left are mostly scores and numbers written without the handle that holds them
  (S3, about 27).

## 2026-11-11 — tier-1 cites completed (harness rev. 15, tier-1 guide v3)

**Commit:** 6b54767 (the change; its score row follows it).

**Why.** Rev. 14's two runs had 36 tier-1 refusals left, all S3:
- **14:** "1순위" read as the number 1. The rank claim that writes it (`[비교] 엔진의 1순위는 …`)
  was in the digest, usually under `also`, but was not cited.
- **11:** a score written with only the judgement cited. A judgement gives the played and best
  moves, not their scores. The digest shows the scores beside the judgement handle
  (`evaluation`).
- **11 others:**
  - a difference the model computed itself ("3.44점", "2.59점");
  - a mate count;
  - a move of another line, or of the game before or after;
  - a square nothing cited holds;
  - a handle written in the text that the sentence does not cite.

**What.** Harness rev. 15 is rev. 14 with two changes, both for tier 1 only.
- **Cites completed.** Each tier-1 ply's digest is read for the handles that give each score
  (`score_text`; the played and best lines first) and each rank ("N순위" in a supported claim's
  `proves`) (`digest_sources`). Before a tier-1 call is sent, a sentence that writes such a score
  or rank, under no handle it cites, gets that handle added to its `cites` (`complete_cites`).
  - This runs after rev. 14's resolution and rev. 13's stripping.
  - The added handle is checked by the server like any cite.
  - A score with no sign is matched only to a positive score.
  - The run logs `cites_completed` with the handles added.
- **Tier-1 guide v3.** v2 with a section on what a number cites:
  - a judgement holds no score;
  - a rank needs its rank claim;
  - no self-computed differences;
  - a mate count, material points, another line's move or a square needs a handle that holds it.

The score command defaults to rev. 15, and the start line records `harness_tier1_cites_completed`.
Tier 2 is unchanged.

Replayed over rev. 14's 36 refusals, completion supplies the needed handle for 23: all 14 ranks
and 9 of 11 scores. The other two scores come from a Calliope line (`x`), which the digest gives
no `score_text` for.

**Tests.** `tests/agent/test_wg_cites.py` covers:
- the digest's sources (played and best lines first; a refuted claim's rank left out);
- the completion (a handle already cited, a difference, an unsigned score of a negative);
- rev. 15 sending completed cites where rev. 14 does not;
- rev. 15's versions.

**Score row** `wg-rev15-openrouter` (bundle cc72e6ed, two parts judged by Claude Code sessions;
both audits passed).
- **Tier 2:** M1b 8.89, M1s 0, M2b 0.833, score 4.17, 4 wrong of 45 sentences, $0.217. Tier 2 is
  unchanged since rev. 12. This is within the rev. 9–11 rows' range of 5.88–13.33 (rev. 14:
  7.84).
- **Tier-1 sample:** 1 wrong of 18 sentences (M1b 5.56), score 3.0, 6/6. The wrong sentence
  places a backward pawn on b2 after the b-pawn has recaptured on c3. That is a reading of a
  board item, not a number's cite.
- **Tier 1 in full:** all 34 plies were commented. 6 refusals were left (rev. 14: 36), all S3:
  - 3: a handle written inside a bracket with a score ("(+1.33, s130)"), which rev. 13's
    stripping leaves;
  - 2: another line's move;
  - 1: a percentage taken from a claim not cited.
- **Completion and re-asks:** 9 handles were added by completion. Re-asks fell to three in five
  batches (rev. 14: four).
- **Cost:** tier 1 cost $0.047 (rev. 14 $0.058, -18%). That is 22% of tier 2. The whole run cost
  $0.264.
- **WG-D §5's done criteria still hold:**
  - every tier-1 ply was commented;
  - tier 2 is within the spread;
  - tier 1's M1b (5.56) is at most twice tier 2's (8.89);
  - tier 1 cost at most half of tier 2.
