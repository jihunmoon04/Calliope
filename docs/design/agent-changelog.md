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

## 2026-11-11 — RV-1's corrections (harness rev. 16, frame check v5)

**Why.** The overnight review RV-1 ([`review-2026-11-11.md`](review-2026-11-11.md)) found 53
problems: 11 major, 32 minor and 10 nits. On the owner's word each was reproduced by a test, then
fixed or set aside with a reason (that document, §5).

**What.**
- **The sentence check (S3):**
  - symbols drawn as a minus (˗ ➖ ∓ ⁃ ⎯, box-drawing horizontals) or as a capture mark (× ✕ ⨯)
    are read as one (P4-1);
  - a lone Hangul jamo touching a token is a foreign letter (P4-2);
  - a null move (`--`, `0000`) is no move (P4-5);
  - a handle spelling never issued is "no handle", not "expired" (P4-8).
- **The audit and the bundle:**
  - the audit flags `..` steps and changes of directory (P6-1);
  - it reads only against the judging's own part directory (P6-6);
  - a judging is checked against the counts and reference digests the bundle fixed in
    `bundle_key.json` (P6-2);
  - no handle reaches a bundle (P6-8);
  - a run of another build than its references is not bundled (P6-9).
- **Metrics:**
  - a moment where an arm judged nothing is left out of the paired rates (P6-3);
  - M1c counts the fixed moments only (P6-7);
  - a material count over an engine line gets the line's FEN and moves in judge v2's evidence
    (P6-4);
  - the `tiers` line is written however tier 1 ends, and a tiered run that ended before tier 1
    counts its sample as asked (P5-3);
  - a row's game counts its compactions and restarts (P7-5).
- **Harness rev. 16** is rev. 15 with frame check v5 and tier 1's corrections. Earlier revisions
  run as they ran.
  - **Frame check v5** (P5-1, P5-6, P5-7, P5-8): only the spans written as gains or losses leave
    the standing's counts; "N점 더 앞선다" is a change; a written move is matched as a whole
    token; "강제" is no grade word.
  - **Tier 1:** its story holds every accepted ply outside the batch (P5-2). It refuses tools it
    does not offer (P5-5), rewrites normalized arguments (P5-9), and keeps a bracketed square
    (P5-10).
  - **Tier 0:** it needs the line to start at the commented ply or the next one (P5-4).
  - The score command defaults to rev. 16, and the start line records `harness_reviewed`.
- **Before Test 2:**
  - a Test run is held to the frozen guide, effort, cost bound and commit (P6-5);
  - `batch` passes the revision, model, guide, effort and cost to each run (P6-12).
- **The server:**
  - a body that is not valid Unicode is a 400 (P3-2);
  - ply 0 is refused by the shared range rule (P3-4);
  - a schema pattern's `$` is the string's end (P3-5).
- **The documents (P7):**
  - the status record points to this log from ST on;
  - the READMEs state TB-D P4's process;
  - TB-D's C2, P2 and C5 are corrected, and §5 is marked replaced;
  - WG-D's tier-2 rows name the frame check;
  - the index rows are updated;
  - each entry here names its commit.

**For the owner:** P4-3 (how a Black mate is written) and P4-4 (a spaced "... Rxe3").

**Tests.** `tests/agent/test_rv1_checker.py`, `test_rv1_scoring.py`, `test_rv1_metrics.py`,
`test_rv1_harness.py` and `test_rv1_rest.py`, one or more for each fix.

**Suite.** 2,235 passed. The only failures are the known environment ones (`test_digest`'s full
view; `test_calibrate_curve`, no zstd). Six revision tests failed in the full run because
`score.py` was edited while the suite ran (`inspect.getsource` read the shifted file). Rerun after
the edit, all 75 tests of those files pass.

**Score row** `rv1-rev16-openrouter` (bundle e7e21545, two parts judged by Claude Code sessions;
both audits passed under the new P6-1 and P6-6 rules).
- **Tier 2:** M1b 13.04, M1s 0, M2b 0.667, score 3.67, 6 wrong of 46 sentences, $0.147. That is
  inside the rev. 9–11 rows' range of 5.88–13.33, but at its top (rev. 15: 8.89). Frame check v5
  held 2 sentences in tier 2 and none in tier 1.
- **Tier-1 sample:** 0 wrong of 18 sentences, score 3.5, 6/6.
- **Tier 1 in full:** all 34 plies were commented, with 8 tier-0 sentences.
- **Cost:** tier 1 cost $0.044 (rev. 15 $0.047), 30% of tier 2. The whole run cost $0.192.
- **Compactions:** one compaction and one restart, in 185264271324 (P7-5's new field).
- **WG-D §5's done criteria hold:** full tier-1 coverage, tier 2 within the spread, tier 1's M1b
  (0) at most twice tier 2's, and tier 1 at most half of tier 2's cost.

**Re-measured** (`rv1-rev16b-openrouter`, bundle ff09b62d, the same code at afbe926; both audits
passed). Part 1's first judging was voided:
- **Why voided:** its audit flagged a `\` inside a Python string (`'references\'`) as a UNC path,
  though the script only globbed `references/*.json` inside its directory.
- **What was kept:** the first judge's files are under `rx-judging/void/ff09b62d-part01-first/`,
  and its audit is kept as `audit-part01-first-voided.json`.
- **The retry:** a fresh judge judged part 1 again.

The rule itself is RX2's and is still open: a `\` should count only when it starts a token.

Results against rev. 16's first row:
- **Tier 2:** M1b 6.25 (rev. 16's first row 13.04), M1s 0, M2b 0.833, score 4.17, 3 wrong of 48
  sentences, $0.220. The two rows straddle the rev. 9–11 range, which puts the first row's 13.04
  within the run-to-run spread.
- **Tier-1 sample:** 0 wrong of 18 again, score 3.0.
- **Tier 1:** all 34 plies; $0.050, 23% of tier 2. The whole run cost $0.270.
- **Compactions:** three compactions and three restarts over the two games.

## 2026-11-11 — the audit's UNC rule narrowed

**Why.** The audit of ff09b62d part 1 failed on `.replace('references\','')`, a `\` inside a
Python string in a script that only globbed `references/*.json` inside its directory. RX2's rule
read any `\` in a command that lists or walks as a UNC path, so a judge writing a backslash in a
string voided its judging (re-judged, as the entry above says).

**What.** `OUTWARD` counts a `\` only when it starts a token (at the start, or after a space, a
quote, `=` or `(`) and a name follows: `\server\share`, `\wsl$`, `'\nas\x'`. A `\` inside a
string is none. The rule is narrower than before, so an audit that passed under it still passes.
Replayed, the voided transcript now passes.

**Tests.** `tests/agent/test_rv1_scoring.py`: the voided judge's command passes, and three UNC
listings are still flagged. No score row: the harness is unchanged, and the audit only reads
transcripts.

## 2026-11-11 — network errors retried (the eight-game run)

**Why.** Rev. 16 was run once on all eight train and validation games, four at a time. Four of the
eight runs ended on a single network error, with no retry:
- an SSL EOF in train rapid and train fourth;
- a connection reset in 185264271324;
- a failed DNS lookup in 184800218248.

The request child marked only an answer cut short as `transport`, the kind the parent retries. A
`URLError` before the answer (a reset, an SSL EOF, a DNS failure) came back as a plain error and
ended the run. Those four runs cost $0.17 together.

**What.** The child marks a `URLError` or `OSError` as `transport`. Both clients retry through
`with_retries`: a transport error twice (after 2 s, then 10 s), and a timeout once, as before (its
wait is long). The harness is unchanged.

**Tests.** `tests/agent/test_hs.py`:
- a refused connection comes back as `transport`;
- `complete` retries a transport error twice and a timeout once.

## 2026-11-11 — tier 2's rewrites (harness rev. 17)

**Why.** In the eight-game survey, tier 2 had 54 refused submissions against 25 accepted, while
tier 1 had 4 refusals in 96 plies. What the model sent to tier 2:
- `agent: null`;
- short cites (`j1`, `x17`), which also bring "no proposition" and "no judgement" with them;
- a comparison (`k`) or fact (`f`) handle cited alone;
- handles written in the text;
- scores and ranks without the handle that gives them.

Rev. 13–15 fixed all of this for tier 1 only.

**What.** Harness rev. 17 is rev. 16 with one change. Before a tier-2 `submit_commentary` is sent,
the harness:
- sets a missing or malformed `agent` to the commentator;
- resolves a short cite from the handles this moment's answers wrote (a name two handles share is
  left as written);
- drops a lone `k` or `f` handle from `cites` and `states`;
- takes cited handles out of the text (a bracketed square stays);
- cites a score or rank a `ply` answer of the game gives by its handle (rev. 15's completion).

It logs `tier2_rewrites`. Tier 1 is unchanged. The score command defaults to rev. 17, and the
start line records `harness_tier2_lean`.

**Tests.** `tests/agent/test_tier2_lean.py`:
- a tier-2 submission rewritten under rev. 17 and sent as written under rev. 16;
- a shared short name never resolved;
- rev. 17's versions.

**Score row** `tier2-rev17-openrouter` (bundle 24a11530, two parts judged by Claude Code sessions;
both audits passed).
- **Tier 2:** M1b 6.25, M1s 0, M2b 0.833, score 4.33, 3 wrong of 48 sentences, $0.145. Rev. 16's
  two rows gave 13.04 and 6.25.
- **Tier-2 refusals:** in the two games, 9 refused submissions against 6 accepted (rev. 16: 12
  against 6). The refusals for `agent`, short handles and lone `k` handles are gone. The rewrites
  set `agent` 16 times, resolved 4 short cites, dropped 9 `k` handles and completed 10 cites.
- **What is left:** mostly standings and ply counts that no cited proposition writes ("흑이 1점
  앞선다", "6수 라인 끝에서 백이 2점"). A material proposition gives the change, not the standing.
  Allowing a cited line's ledger standing would be a server rule (S3), so it is left for the owner.
- **Tier-1 sample:** 0 wrong of 17 sentences (1 doubtful), score 2.83. Tier 1 cost $0.047.
- **The whole run** cost $0.193.

## 2026-11-11 — the survey's kinds (harness rev. 18, frame check v6, guides v3 and v4)

**Why.** The eight-game survey ([`rx-evidence/eight-game-survey-2026-11-11.md`](rx-evidence/eight-game-survey-2026-11-11.md))
found six new kinds of wrong sentence. Rev. 17's row added one more of kind E: a Black move's
rank read the wrong way round. The kinds:
- A: an exclusive claim from one line;
- B: a defence miscounted, or a pin said to void it;
- C: material denied against the cited comparison;
- D: a segment's end read as the line's end;
- E: a rank counted from a partial list;
- F: check direction reversed.

**What.** Harness rev. 18 is rev. 17 with:
- **Frame check v6:** v5 with two rules.
  - **F7:** a sentence that denies material ("물질 손실이 아니라", "물질 셈으로 비교할 수 없",
    "얻은 것이 없") while it cites a supported comparison claim whose finding counts material
    (best or played delta not 0). The cited claims are read through `detail` (`claims_needed`).
  - **F8:** a rank from the third down that the sentence counted itself ("셋째 후보", "3위",
    "4번째 후보"). Only the rank claims give a rank, and they name the first and second.
- **The tier-2 guide `harness_guide_v3` and the tier-1 guide `harness_tier1_v4`:** v1 and v3 with
  a section on all six kinds. A sentence should:
  - use an exclusive word only with the legal moves or a claim behind it;
  - leave a counted comparison's material undenied;
  - read a line's end at its PV's end;
  - take ranks from rank claims only, remembering that a lower score is better for Black;
  - count defences and pins as the board items do;
  - check which side gives check.
- **The tier-2 guide is now chosen by revision** (`guide_of`): v3 from rev. 18, v1 before. A
  `--harness-guide` flag still wins.

The score command defaults to rev. 18.

**A bug caught on the way.** `run.py` already had a `guide_of(arm)`, and importing the harness's
under the same name inside the run function would have shadowed it. Ruff flagged the shadowing
(F823). The harness's is imported as `harness_guide_of`.

**Tests.** `tests/agent/test_survey_rules.py`:
- F7 by handle and by explicit claim (v5 leaves it);
- F7 left alone with no material comparison cited;
- F8's ranks against ply counts and words like 위치 and 위협;
- rev. 18's versions and guides.

**Score row** `survey-rev18-openrouter` (bundle f34a7bba, two parts judged by Claude Code
sessions; both audits passed).
- **Tier 2:** M1b 4.08, M1s 0, M2b 0.667, score 3.83, 2 wrong of 49 sentences, $0.181. This is the
  lowest tier-2 rate so far (rev. 17 6.25; rev. 16 13.04 and 6.25), but two games cannot separate
  it from the spread.
  - The wrong sentences are known kinds: an old attack written as new, and a change written as
    the standing.
  - No sentence of kinds A–F was judged wrong.
  - F7 and F8 held nothing in either run, so the guides, not the checks, are what changed the
    writing, if anything did.
- **Tier-1 sample:** 1 wrong of 18 sentences (M1b 5.56), score 3.0. It is the backward-b2-pawn
  sentence at 185264271324-25 again: the same mistake as rev. 15's row, a board item read after
  the recapture.
- **Tier-2 refusals:** 11 against 7 accepted (rev. 17: 9 against 6).
- **Cost:** tier 1 $0.052. The whole run cost $0.233.

## 2026-11-15 — a writing turn of its own (harness rev. 19; kept and merged 2026-11-24)

Unattended work while the owner was away; the owner chose the direction beforehand ("결정은 추천대로":
classify the wrong sentences, try a separate writing turn, try S3's standing on a branch only).

**Why.** [`rx-evidence/rev19-wrong-sentence-causes.md`](rx-evidence/rev19-wrong-sentence-causes.md)
classifies the 59 sentences judged wrong or doubtful in the eleven judgings of revs. 14–18:
- 37 (63%) restate wrongly a fact that their own cited evidence held in structured form: standing
  and change mixed up (12), a board item read at the wrong time (9), a relation that held before the
  move written as made by it (7), a segment written as the analysis line (3), a side swapped (4), a
  rank read the wrong way (2);
- 16 (27%) give a mechanism the data does not hold (an invented pin, "forced", "not material");
- 6 (10%) add something unsupported.

Reading the run logs of 13 of them showed that most were already in the facts answer the harness
judge passed; the submit step copied them. The writer has the whole facts conversation, raw tool
answers included, and the facts answer's prose is checked only where a claim backs it.

**What.** Harness rev. 19 is rev. 18 with:
- **A writing turn of its own.** After the facts step, the moment's conversation is rebuilt: the
  system message, the story, and one `write` message (`harness_v7`) holding the moment's `ply`
  answer (fetched by the harness), the facts answer as a draft, and the checked claims as code
  writes them (`render_checked`): a line's standing at its start and end apart from its change,
  its last move, a square's attackers and defenders "at the record's position, not when they
  began", a ranking in order for the mover, a score's side. The writer is offered `detail` and
  `submit_commentary` only (the gate refuses others and logs `tool_unsent` with `writer`). Its
  rules: copy numbers from the checked lines; standing is not change; a line ends at its last move;
  drop a relation only the draft states (defence, pin, blockade, "made by this move") unless a cited
  proposition states it; every sentence cites a proposition.
- **S3's standing (the owner's open question of rev. 17, trialled here).** With
  `CALLIOPE_STANDING_NUMBERS=1` the server lets a `material` proposition also allow the standing
  (White minus Black) at its segment's two ends (`propositions.standing_integers`). The runner sets
  it for rev. 19 only and never passes it on from its own environment; the start line records
  `harness_writer` and `server_standing_numbers`.
- **Not done: a 3-sample vote on the decisive cause.** The wrong causes recur across runs of the
  same moment (the 29...a5 pin story in 3 of 11 judgings, "6...c5 removed b5's defence" in 4), so a
  majority of three samples would cut such an error only from about 0.36 to 0.30, for three times the
  facts step's cost.

**Trials** (OpenRouter, the score command's two games, not judged):
- First: 4 of 6 moments unsubmitted. Without the `ply` answer the writer had no judgement handle for
  the subject's own proposition. Fixed by giving it the answer (18974e9).
- Second: 6 of 6 submitted; tier-2 refusals 22 against rev. 18's 11. S3 number refusals fell from 40
  to 15, but 14 sentences cited nothing (rev. 18: 1). Fixed by the rule above (715fccb).
- Third: 6 of 6 submitted; 16 refusals (13 S3 numbers, 12 S3 moves, 8 attack or defence
  propositions the server refused, such as "no piece on c3", 2 S2). Cost $0.229.

**Tests.** `tests/agent/test_rev19_writer.py`: the writer's conversation (no tool answers, the
`write` message with the digest, the offered tools); a refused tool; rev. 18 unchanged;
`render_checked`; `standing_integers` off and on; rev. 19's versions and start line.

**A bug caught by the 8-game batch.** A compaction inside the writing turn sent every tool, and the
Claude API refused the writer's thinking blocks, which are bound to the tools they were made with
(HTTP 400, run `01M7DF9S4C6MQ592HA8P5KH005`). Compaction now offers the writer's tools (f1be5c9);
the game was run again.

**Measurement** (Claude API, `claude-haiku-5-5`, the eight train and validation games, one run
each, the survey's bounds; `python -m tools.rx.batch`). Rev. 18 ran twice to show the spread between
two passes of the same revision. From the logs:

| | rev. 19 | rev. 18 (a) | rev. 18 (b) |
| --- | --- | --- | --- |
| Tier-2 moments submitted | 24 of 24 | 24 of 24 | 23 of 24 |
| Tier-2 refused submissions | 44 | 41 | 49 |
| Cost of the pass | $0.959 | $0.763 | $0.828 |
| Bundle (judge v2, 8 parts) | `b9505a57` (48 items) | `bfdeec9a` (48) | `ab949ae3` (47) |

On the Claude API the writer's refusals are within rev. 18's spread, unlike the OpenRouter trials;
rev. 19 costs about 20% more (the writing turn's own requests). The whole night's API spend was
$3.44 ($0.74 OpenRouter, $2.70 Claude API, including a run cut by the machine's restart).

**Judging (2026-11-24).** The 24 parts were judged by judge v2, each in a fresh **headless Claude
Code session** (`claude -p "Read judge_v2.md in this directory and do exactly what it says."
--model claude-opus-5-5`, tools Read, Write, Edit and Bash, run with the part as its working
directory). This replaces opening each session in the app: a headless session needs no folder
trust. The sessions ran on the owner's claude.ai login (`apiKeySource: none`), not the Claude API,
so this is not the API judge the owner declined (`judge_v2r`, P2 above). Each session's JSON Lines
transcript was zipped and audited as an exported one (`python -m tools.rx audit`); the session ran
on the default config directory, so its own `tool-results` path is the one `own_dirs` knows. The
owner agreed to the method (2026-11-24).

Three judgings failed their audit and were discarded before any join; each part was judged again
in a new session, and every part's audit then passed:
- `b9505a57` part 1: the session ran under the Orca profile's config directory, and the judge
  read its own `tool-results` file there, which `own_dirs` does not know.
- `bfdeec9a` parts 1 and 7: the judge wrote a scratch output to a parent directory
  (`../../../scratch_out.txt`, `../../_tmp_out.txt`), read it back and removed it. Nothing outside
  its directory was read.

**Score rows** `m8-rev19-claude`, `m8-rev18a-claude`, `m8-rev18b-claude` (`score finish` from
pending files written from each bundle's key and batch log):

| | rev. 19 | rev. 18 (a) | rev. 18 (b) |
| --- | --- | --- | --- |
| Tier 2 M1b (wrong per 100) | **6.19** (12 of 194) | 9.18 (18 of 196) | 7.25 (14 of 193) |
| Tier 2 M2b (decisive causes explained) | 0.826 | **0.870** | 0.739 |
| Tier 2 score | 4.25 | 4.08 | 4.22 |
| Tier 1 M1b (sample, 24 plies) | 0.0 (70 sentences) | 0.0 (71) | 4.35 (69) |

**Reading.** Rev. 19 has the lowest tier-2 M1b, below both rev. 18 passes, but its M2b is 4.4 points
below rev. 18 (a)'s, so the rule set above (no lower M2b) is not met as written. Neither gap reaches
RX0-D §7's bar (2 per 100 for M1b, 10 points for M2b): rev. 19 against rev. 18 (b) is 1.06 per 100,
while the two rev. 18 passes differ by 1.93 per 100 and 13 points. The difference is within the
spread of one revision run twice. The owner chose to run rev. 19 again to see its own spread.

**Rev. 19's second pass (2026-11-24).** The same batch (`m8-rev19b-claude`, the first pass's bounds,
at 61bb916; a first start was stopped by the owner after four cut runs, $0.23, none judged), all
eight runs `done`, $0.93. Bundle `54fa1a41` (48 items, 8 parts), judged as above; all eight audits
passed at the first judging. **Score row** `m8-rev19b-claude`:

| | rev. 19 (a) | rev. 19 (b) | rev. 18 (a) | rev. 18 (b) |
| --- | --- | --- | --- | --- |
| Tier 2 M1b | 6.19 (12 of 194) | **4.64** (9 of 194) | 9.18 (18 of 196) | 7.25 (14 of 193) |
| Tier 2 M2b | 0.826 | 0.826 | 0.870 | 0.739 |
| Tier 2 score | 4.25 | 4.21 | 4.08 | 4.22 |
| Tier 1 M1b | 0.0 (70) | 0.0 (67) | 0.0 (71) | 4.35 (69) |
| Cost of the pass | $0.959 | $0.928 | $0.763 | $0.828 |

**Reading.** Both rev. 19 passes are below both rev. 18 passes on tier-2 M1b. Pooled, rev. 19 has
21 wrong of 388 sentences (5.41 per 100) against rev. 18's 32 of 389 (8.23), a gap of 2.8 per 100,
above RX0-D §7's bar of 2. M2b is 0.826 in both rev. 19 passes against rev. 18's 0.870 and 0.739
(mean 0.804): not lower on the mean, lower than one rev. 18 pass. The gap is not firm: as
independent sentences, 21 of 388 against 32 of 389 gives z ≈ 1.56 (p ≈ 0.12, two-sided), and
sentences of one commentary are not independent. Rev. 19 costs about 20% more a pass.

**Decision (owner, 2026-11-24): rev. 19 kept** and merged into `main`; the score command's default
revision is now 19 (`tools/rx/score.py`, `test_tb_score.py`).

## 2026-11-24 — AI commentary from the local web app; Windows (PR #166, merged 2026-11-27)

**Commit:** 64aab5e and six review fixes (5a5a1e8 … 0190f39); merged as 8495a08. Entry written after
the merge (2026-11-27); the PR carried none.

**Why.** The commentary harness ran only from the RX runner (`python -m tools.rx …`) in WSL; the
local web app (`tools/serve` and the viewer) could only show a commentary stored beforehand. The
server needed `fcntl`, so it did not start on Windows at all.

**What.**
- **Commentary jobs in `tools/serve`** (`tools/serve/commentary.py`). After a game's analysis, the
  viewer's AI commentary panel offers 「AI 해설 생성」 and 「해설 중단」. The server runs the
  three-tier Korean harness on the analysed game: tier-2 moments chosen by grade
  (`MOMENT_PRIORITY`), default revision 19 at the time (20 since PR #167), model
  `claude-haiku-5-5` with `ANTHROPIC_API_KEY` or `anthropic/claude-haiku-5.5` with
  `OPENROUTER_API_KEY`. The job's progress and the stored commentary are served on
  `/api/games/<key>/commentary/job` and `/commentary/cancel`. Options: `--model`, `--cost-limit`
  (default $1, a stop checked between requests), `--env-file`, `--no-commentary`,
  `--allow-host`, `--open`.
- **The HTTP server** (`calliope.server.web`) checks `Host` and `Origin` against the bound host and
  `--allow-host` before a commentary POST (start or cancel), since those spend API money. It drains a request's unread body before closing, so Windows
  sends no TCP reset.
- **Windows** (`calliope.server.files`, `cache`). File locks use `LockFileEx` where `fcntl` is
  missing. Paths go through `long_path` (extended-length paths past `MAX_PATH`). Replacing a file
  retries a sharing violation. Private data directories get an owner-only DACL (`0o700` on POSIX).
- **The RX runner.** A request can be cancelled (`ModelCancelled`, a `cancel_event` through the
  request child). The harness judge is not asked again once its first answer has spent the cost
  left under the bound (`cost_left`, TB-D B5). Numbered SAN counts from the game's own starting
  position (a FEN start at a later move or with Black to move). `tools/mcp` takes `--root-fen`
  (ply-cache root overrides) for the web app's games.

**Tests.** `tests/server/test_serve_commentary.py`, `test_commentary_jobs_web.py`,
`tests/viewer/test_viewer_commentary_job.py` with `check_commentary_job.js`, and updates to the
server, agent and viewer tests (`test_jobs.py`, `test_concurrency.py`, `test_games.py`, …).

**No score row of its own.** The harness's text and tools are unchanged. The runner's changes
(cancellation, `cost_left`, numbered SAN from the starting position) are inside rev. 20's rows
`rev20-codes-claude` and `m8-rev20-claude`, measured at 8fa4a70, which contains 8495a08. None of
the eight score games starts from a FEN, and no judge retry in those rows was cut by `cost_left`
(each run's spend stayed under its $1 bound).

## 2026-11-27 — code-only citations and lightweight submission (harness rev. 20)

**Commit:** e497b9c … 8fa4a70 (the change and eight review rounds), f5d073f (the default and the
score rows); merged as ebaeac4. Both score rows were measured at 8fa4a70. Their `commit` was written
as `null` and filled in afterwards. The runs carry b6d814f's writer prompt, and their logs end at
15:45 and 17:49–18:03 KST, between 8fa4a70 (14:47) and f5d073f (18:37).

**Why.** Under rev. 19 (`claude-haiku-5-5`, `effort="medium"`), the model spends extra output tokens
and retries writing full `propositions` JSON blocks, `agent`/`game`/`states` boilerplate, and
failing standalone `f`/`k` handles or move-vs-score citation pairs. Keeping `sentences.py` S3 rules
untouched, Phase 1 moves citation construction to server-issued atomic codes (`b`, `m`) and minimal
code-only submissions (`cites` + `text` + `class` only).

**What.**
- **Atomic `m` (material ledger) & `b` (board/facts) handles.** `src/calliope/agent/handles.py`
  and `record.py` add `m` (`material`, keyed with ply `origins`). `session.py` serves per-side
  `m` handles on `explore` (`ledger.ref` and `ledger.side_refs`) and `compare_lines`
  (`material_ref` and `material_refs`), atomic `b` handles on non-empty `squares` entries (with
  canonical `changed_by_move`-free items) and `facts()["citable"]`, and persists `m` handle
  `origins` in `record["sources"]` so commentary deduplication (`_content_key`) and
  `tools/rx/evidence.py` distinguish same-move lines with different search vs agent provenance.
  `tools/rx/metrics.py` (`requested()`) matches `material` (`m`) and `facts_tree` `board_item` (`b`)
  handles for `on_request` coverage metrics.
- **Frame check v7 & harness rev. 20 (`harness_v8`, `harness_guide_v4`, `harness_tier1_v5`).**
  `tools/rx/frames.py` (`FRAMES_V7`) resolves cited `m` and direct `j` handles per sentence with
  isolated ledgers for F1/F3/F4/F5, segment-level grouping when both per-side `m` handles are cited
  together, and segment-scoped `_search_backed`. `tools/rx/harness.py` serves stripped
  `submit_commentary` schemas (`_codes_only_tools`), renders checked evidence with short codes,
  per-side `m` codes, standalone `score` origin labels, carried-over `facts().citable` board
  facts, position-exact square refs, citable piece descriptions, and move refs on searched
  candidates, resolves short handles on `submit_commentary`/`detail`, drops lone `f`/`k` cites,
  auto-injects `game`, `agent`, and non-colliding ply `j` handles, and resolves `m` citations in
  Tier 0 follow-ups.
- **Default promotion (`tools/serve`, `tools/rx/score`).** `DEFAULT_HARNESS_REVISION` in
  `tools/serve/commentary.py` and the default `--harness-revision` in `tools/rx/score.py` are
  promoted from `19` to `20` (with `--harness-revision 19` retained as fallback) and
  `CALLIOPE_STANDING_NUMBERS=1` gating per revision.

**Tests.** `tests/agent/test_rev20_codes.py`, `tests/agent/test_tb_score.py`,
`tests/agent/test_survey_rules.py`, and `tests/server/test_serve_commentary.py` verify atomic
`b`/`m` handles, per-side `m` S3 verification, provenance isolation, `FRAMES_V7`, `evidence`
rendering, `metrics.requested`, `Gate` rewrites/carry-over, Tier 0 `m` resolution, default
revision `20`, and `--harness-revision 19` fallback.

**Measurement & judging (2026-11-27).**
- **2-game dev score row (`rev20-codes-claude`):** Validation games `184800218248` and `185264271324`,
  Claude API `claude-haiku-5-5` (`effort="medium"`), bundle `140f2324` (11 items across 2 parts;
  `185264271324` Tier 1 ply `28` ended `left_out`), judged by `judge_v2` via headless Windows Claude
  Code (`claude-opus-5-5`); both audits passed on the first judging (`passed: true`). Tier 2: `6/6`
  completed, `M1b 2.27` (1 of 44), `M1s 0.0`, `M2b 0.667`, `score 4.33`, cost `$0.11216`. Tier 1
  sample: `5/6`, `M1b 0.0` (15 sentences), `score 3.40`, whole-run cost `$0.16850`.
- **8-game promotion batch (`m8-rev20-claude`):** `python -m tools.rx.batch` across the eight train
  and validation games (`hung`, `rapid`, `fresh`, `fourth`, `184800218248`, `185264271324`,
  `185371835722`, `185922072242`), one run each (`turns=90`, `tool_calls=150`, `tokens=20000000`,
  `cost=1.0`, `run_seconds=2700`, `--workers 4`), `claude-haiku-5-5` (`effort="medium"`). All eight
  runs finished `whole: true` and `end: "done"` (`24/24` Tier 2, `96/96` Tier 1, `1` compaction,
  `1` restart, `235` Tier 2 turns / `271` total turns). Bundle `97ef7175` (48 items, 8 parts) was
  judged by `judge_v2` (`claude-opus-5-5`); all eight audits passed on the first judging:

| | rev. 20 | rev. 19 (a) | rev. 19 (b) | rev. 18 (a) | rev. 18 (b) |
| --- | --- | --- | --- | --- | --- |
| Tier 2 completed | 24 of 24 | 24 of 24 | 24 of 24 | 24 of 24 | 23 of 24 |
| Tier 2 M1b (wrong per 100) | **4.57** (8 of 175) | 6.19 (12 of 194) | 4.64 (9 of 194) | 9.18 (18 of 196) | 7.25 (14 of 193) |
| Tier 2 M1s (search_only per 100) | 0.57 | 0.52 | **0.0** | 0.51 | 0.52 |
| Tier 2 M2b (decisive causes explained) | **0.870** | 0.826 | 0.826 | **0.870** | 0.739 |
| Tier 2 score | **4.33** | 4.25 | 4.21 | 4.08 | 4.22 |
| Tier 1 M1b (sample, 24 plies) | 3.03 (2 of 66) | **0.0** (70) | **0.0** (67) | **0.0** (71) | 4.35 (3 of 69) |
| Tier 1 score (sample) | **3.12** | 3.04 | 2.96 | 3.08 | 3.04 |
| Tier 2 cost | **$0.528** | $0.814 | $0.796 | $0.629 | $0.684 |
| Whole-run cost | **$0.672** | $0.958 | $0.928 | $0.763 | $0.828 |

Rev. 20 cuts Tier 2 cost by ~34% and whole-run cost by ~28–30% vs rev. 19 (`$0.52832` vs `$0.796`–`$0.814`,
`$0.67184` vs `$0.928`–`$0.958`) with fewer compactions (`1` vs `5`–`6`), highest Tier 2 `score` (`4.33`),
lowest Tier 2 `M1b` (`4.57`), and highest-tied `M2b` (`0.870`). Remaining Tier 2 errors are led by
unsourced `search`-extended lines (`source`, 3 of 8).

**Decision (owner, 2026-11-27): rev. 20 kept** and merged into `main`; the default harness revision is
now `20` (`tools/rx/score.py`, `tools/serve/commentary.py`, `tests/agent/test_tb_score.py`,
`tests/agent/test_survey_rules.py`, `tests/server/test_serve_commentary.py`).

## 2026-11-27 — the run's waits: no token count under a bound, summaries prewarmed

**Why.** One rev. 20 run of train `hung` (`01M8EC0KHXE71AZKE69GGCGM4W`, Claude API, $0.084) took
615 s:

| Part | Time | Share |
| --- | --- | --- |
| The model's answers (facts 203 s, writer 153 s, tier 1 93 s) | 449 s | 73% |
| The harness judge | 41 s | 7% |
| The guard's `count_tokens` (37 requests, 1.6 s each) | 61 s | 10% |
| Server tools, of which `game_overview` 39 s | 49 s | 8% |

A model answer's time is about 1.8 s plus its output tokens at about 200 a second (85% of the
model's time, over rev. 20's eight runs too). The first `game_overview` replayed every cached ply
(71 plies, 39 s; 105 s for the 145-ply game in `m8-rev20-claude`) for a summary of each. Neither
wait changes what the model is sent or answered.

**What.**
- **The guard's bound** (`tools/rx/guard.py`), **opt-in** (`CALLIOPE_GUARD_BOUND=1`; off by
  default, so the guard counts every request as before). On the Claude API only, `check` skips the
  count when an upper bound is under 80k (`how: "bounded"`). The bound applies only when the request extends
  the last one checked and answered: the same messages before it (their digest) and the same tools.
  That answer's usage must also hold both its input and its output tokens: the adapter marks an
  absent count (`usage_missing`, `tools/rx/claude.py`) instead of reading it as 0. The bound is
  the larger of the last request's size (counted or bounded) and the answer's total input, plus the
  answer's output tokens, plus the new messages' UTF-8 bytes, plus 50 a new message and 1,000 of
  margin. Under 80k the counted verdict is `send` too, so wherever the bound is not under the count
  the verdicts are the counted ones.
  - The old path stays for a request asked through `size` alone (compaction, a batch's split), for
    a new moment, and for OpenRouter (`counted+usage`: its usage does not stand for the Claude count).
  - The bound is measured, not proven. It reads the internal messages, while the count is of the
    converted request (blocks merged, the system lifted). Replayed over 1,460 counted requests of
    earlier Haiku 5.5 runs, the first form of the bound (without the allowance, the margin and the
    floor) was never under the count, its tightest gap 144 tokens, and it fell under 80k for 93% of
    them. Outside that sample (another model, other thinking or tool data) it may be under.
  - It is opt-in because B4's 100k is TB-D's guarantee: turning it on by default is the owner's
    decision (re-review R1).
  - The score row's `largest_counted` leaves out `bounded` lines (`tools/rx/score.py`).
- **Summaries prewarmed** (`Session.prewarm`, on in `tools/mcp`; `--no-prewarm`). A held game
  (by `open_game`, or by a work tool on a game an earlier process opened: the RX runner calls no
  `open_game`) is queued once a process, by `_hold` or a later work tool's `game`. One daemon worker
  summarizes the queued games' cached plies in turn: the summaries `game_overview` reads
  (`_summary`). Nothing is analysed.
  - A game is queued only once the engine's build exists. Queueing never starts or waits for the
    engine, so a tool that needs none (`facts`) is never delayed or failed by it. The worker keys
    and records with that build and never starts an engine, even after `close`.
  - The queue holds a game's key and parsed moves, not its work state, and at most 4 games, the
    oldest dropped. Eviction takes a game out of the queue and its mark. A game over the game path's
    600 plies is not queued.
  - Each queued game carries the number of the hold it was queued for. Evicted, or evicted and held
    again, its running prewarm stops at the next ply, and the new hold queues its own.
  - A lock a game keeps the worker and `game_overview` from replaying one ply twice. It exists only
    while the game is queued, prewarmed or worked on, so an overview of an unheld game takes none.
    It is dropped once neither its mark nor the worker uses it: an evicted game being worked on
    keeps the same lock until the worker leaves it. Under the lock, the files' digests are read
    again before a kept summary is accepted.
  - `close` asks the worker and the jobs to stop at once, within one deadline.

**Review (Codex, 2026-11-27): NOT_READY**, on 7681853. Seven findings:
- F1 (blocker): an absent usage count read as 0 could seed a low bound. Fixed: `usage_missing`, and
  the last request's size as the floor.
- F2: OpenRouter's usage does not stand for the Claude count. Fixed: the bound is for the Claude API
  only.
- F3: `game_overview`, waiting for the lock, could accept a summary of files another process
  replaced meanwhile. Fixed: the digests are read again under the lock.
- F4: a prewarm past `close`'s wait could start the engine. Fixed: the build is taken at queueing,
  and one deadline covers the worker and the jobs.
- F5: a thread a game, eviction ignored, games over 600 plies walked. Fixed: one worker and a queue,
  evicted games dropped, long games skipped.
- F6: a first `ply` and the prewarm can replay the same cold ply at once, and the prewarm's pairs
  take places in the kept-pair LRU (64). Not fixed: it is a duplicated replay, no wrong answer, and
  coalescing it belongs to the ply cache.
- F7: tests at the boundaries. Fixed with the tests below.

**Re-review (Codex, 2026-11-27): NOT_READY**, on d3d3991. F2, F3 and F4 were resolved, F1 and F5
partly, F6 deferred, F7 mostly resolved. New findings:
- R1 (a blocker while B4's 100k is the contract): the bound is still a heuristic. Fixed: it is
  opt-in, and the default is the owner's decision.
- N1 (blocker): with the prewarm on, holding a game took the engine build, so `facts` on a game an
  earlier process opened failed when the engine could not start. Fixed: a game is queued only
  once a build exists.
- N2: the queue kept evicted games, with their work state, past the open-games limit. Fixed: key
  and moves only, at most 4, and pruned on eviction.
- N3 (nit): the entry promised unchanged verdicts without saying where. Fixed above.

**Second re-review (Codex, 2026-11-27): READY_WITH_CORRECTIONS**, on 61fca2c. R1, N1, N2, N3 and F1
were resolved, F7 resolved for the earlier scenarios, F5 partly, and F6 deferred as agreed. Its
corrections, applied:
- N4: an overview of an unheld game left a lock behind for the process's life. Now a lock exists
  only for a game the prewarm may be on.
- N5: a game evicted and held again while the worker replayed one of its plies got a second lock,
  and the old run went on, since the key was held again. Now the lock lives on while the worker
  uses it, and the run checks its hold's number.
- Nit: the guard hashed every request it sent even with the bound off. Now only an opted-in run
  does.

**Tests.** `tests/agent/test_latency.py`:
- a request extending the last one is bounded and not counted;
- a bound of 80k or over is counted, and the count decides;
- a changed earlier message, or other tools, is counted;
- no bound after a request the guard did not check, or in a new moment;
- the bound is off by default;
- no bound without the answer's output tokens, or without a counter;
- a Claude answer missing a usage count, through the real adapter, gives no bound (F1);
- the last request's size is the bound's floor (F1);
- OpenRouter keeps `counted+usage` (F2);
- `largest_counted` leaves out `bounded` lines;
- prewarmed summaries make `game_overview` read no ply, and its whole answer equals a replay's;
- no prewarm by default (no lock either), and nothing analysed without cached plies;
- a game held by `ply` alone is prewarmed once the build exists;
- one worker takes the games in turn, keeps at most 4 queued without their work state, and skips a
  game over 600 plies (F5, N2);
- eviction takes a game out of the queue, its mark and its lock (N2);
- `facts` on an earlier process's game never starts the engine (N1);
- an evicted game's prewarm is dropped (F5);
- an overview of an unheld game leaves no lock (N4);
- a game evicted and held again while its ply is replayed keeps one lock, its old run stops, and
  the new hold's run summarizes it (N5);
- a summary published while `_summary` waited is checked against the files read again (F3);
- a prewarm still reading at `close` returns within the deadline and never uses the engine (F4).

Agent, server and boundary suites: 1,074 passed, the known `test_digest` full-view failure apart.

**Measurement** (at 7681853, with the bound on and before the reviews' fixes, which change no
request or answer). `hung` again with this change (`01M8EERVZWNCSA5ZEC05BBWAVT`, $0.075): 453 s. The guard counted 8 requests, each
conversation's first, and bounded 24 (11 s against 61 s). The prewarm summarized 71 plies in 42 s in the background, and `game_overview` answered in 23 ms (49 s against
11 s of tool time). The two parts together saved 88 s, 14% of the first run. The rest of the 162 s
difference is the model's: 32 turns against 37, so 389 s against 449 s of answers, within one run's
spread. Both runs submitted all three moments, and every guard verdict was `send`.

**No score row.** By default the guard counts as before, and the prewarm changes no tool's answer,
only when a summary is made. One run on each side measures the waits, and neither run was judged.
With the bound off, the default keeps the prewarm's part (49 s → 11 s of tool time on `hung`) and
not the guard's (61 s → 11 s).
