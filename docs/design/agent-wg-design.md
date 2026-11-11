# WG-D: whole-game commentary in three tiers

Status: rev. 2 — the review of 2026-11-10 applied (§8; harness rev. 12 now runs the frame
check v4). Rev. 1: the owner (2026-11-10) took the recommendations on Q1–Q5 and asked for the
implementation without a review first; WG1 and WG2 implemented as harness rev. 12 (the change log,
"whole-game commentary in three tiers"). The owner had asked to stop correcting the fixed moments
for now and widen the commentary to the whole game (TB-D §5, Q6: "after B, as their own design").

## 0. Where we are

The harness (TB-D B, now rev. 11) writes commentary for three fixed moments a game: two errors and
one special move, chosen by `rx_moments`. Each moment costs about $0.03 on Haiku 5.5. Its score rows
(`docs/design/rx-evidence/scorecard.jsonl`) measure only those moments:
- M1b, the share of wrong sentences: 5.88 at rev. 11; the rev. 9–11 rows range 5.88–13.33 (rev. 8's row is 4.55);
- M2b, the share of key causes stated: 0.667–0.833.

A reader of a whole game sees three commented moves in 50–145.

**What the rest of a game holds.** The validation set's four games, from their sealed base cache,
with `game_overview`'s grade for every ply:

| Game | Plies | Fixed | Other inaccuracies, mistakes, blunders | The rest |
| --- | --- | --- | --- | --- |
| 184800218248 | 107 | 3 | 20 | 84 |
| 185264271324 | 86 | 3 | 8 | 75 |
| 185371835722 | 50 | 3 | 5 | 42 |
| 185922072242 | 145 | 3 | 18 | 124 |

"The rest" are best, excellent and good moves. Of the 327 plies not graded an error (the rest plus
two fixed moments of 185371835722), 159 lose nothing and 131 lose under 50 centipawns. A few of the
rest are labelled miss, brilliant or great; §1 puts them in tier 1, and the table's count leaves
them out.

## 1. The tiers

TB-D §5's table, made exact:

| Tier | Plies | What is written | How |
| --- | --- | --- | --- |
| 2 | the fixed moments (`rx_moments`) | a commentary, as now | the harness as rev. 11, with frame check v4 (v5 from rev. 16) |
| 1 | every other ply graded inaccuracy, mistake or blunder, or labelled miss, brilliant or great | 1–3 sentences a ply, with evidence | a batch conversation (§2) |
| 0 | every other ply | nothing, or one sentence from code (§3) | code |

- A ply is in one tier only. Tier 2 is chosen first, then tier 1.
- The tiers are read from `game_overview`'s `grade` and `label` only. No new analysis, and no
  engine time beyond what the game's analysis already spent.
- Labels: "forced" is tier 0, since a forced move needs no comment. Brilliant and great are tier 1
  even when graded best, because the reader wants to know why.

## 2. Tier 1: a batch conversation

**Why not the harness per ply.** At about $0.03 a moment, 20 tier-1 plies would cost $0.60 a game.
Most of what a moment's run spends goes on reading and exploring. A tier-1 ply needs less: what was
played, what was better, and the line that shows why. The `ply` digest already holds all three.

**The conversation.**
1. **Order.** Tier 2 runs first. Tier 1's batches follow in ply order.
2. **Batches.** One batch holds up to 8 consecutive tier-1 plies, cut so that the first message
   stays under 60k tokens by the guard's count (TB-D B4). A ply's digest is about 15 KB, roughly
   5k tokens.
3. **The first message:**
   - the harness guide, shortened to tier 1's task (§2.1);
   - each ply's `ply` digest, fetched by the harness, not by the model;
   - the commentary accepted before the batch (the fixed moments' and earlier batches'), so tier 1
     does not contradict them or retell them.
4. **Tools.** The model has `submit_commentary` and `detail` only: no `explore`, no searches, no
   `ply`. Evidence is the digest's handles. A `detail` answer over the cap gets `tier1_refused`,
   which names no tool tier 1 lacks.
5. **The submission.** One call with `items`, one item a ply (AG6-D's several subjects). A refused
   item may be sent again, as in tier 2. A call naming one ply without `items` counts for that ply.
   The server's verification and the frame check (v4) run as for tier 2. A hold answers the model
   as now (at most `HOLDS` holds, then checked passively).
6. **Bounds:**
   - at most 6 turns a batch;
   - a batch that ends without a submission leaves its plies without text, logged as such;
   - the run's $1 bound (TB-D Q5) covers both tiers.

**Expected cost.** Haiku 5.5's price (≤100k: $0.125/M cache write, $0.01/M cache read, $0.50/M
output) puts one batch at about $0.01: a 45k-token first message written to the cache, one retry
after a hold, and about 4k tokens of output. A game of 13 tier-1 plies needs 2 batches, about $0.02.
That is 20–25% more than its three moments ($0.08–0.11). It is an estimate; the first run measures
it.

### 2.1 The tier-1 guide (`harness_tier1_v1`)

A new prompt beside `harness_guide_v1`. It keeps:
- the guide's rules on evidence, sides and material (the frame words, the ledger's owner names);
- the glossary.

It drops the moment's method (reading, exploring, comparing lines) and asks for:
- **what happened:** the move and what it changed, from `board.changes` and the claims;
- **what was better**, when the digest has a better move and its line;
- **one sentence linking the ply to the story so far**, only when the accepted commentary already
  set it up (a weakness named at a fixed moment, now taken).

It asks for no evaluation numbers unless they explain something. A grade is named only as the
digest gives it.

## 3. Tier 0: nothing, with one exception

Tier 0 writes nothing in rev. 1. The viewer already shows every ply's move and grade name. The
exception is one code sentence: when the game's moves follow a line the commentary cited earlier,
the first such ply gets "앞서 본 수순대로 진행되었다 (N수까지)".
- This sentence is recorded as `source: code`. It is not judged.
- It appears only when the played moves match the cited line's own moves exactly from its first
  move, and that first move is the commented ply or the next one. An explored line's moves before
  its start (`from_root`) count for nothing.

Anything more for tier 0 (opening names, phase notes) needs facts the server does not serve yet.
It is left out.

## 4. What a run produces and stores

- **The run's log:**
  - `tiers_plan`: tier 1's plies, the judged sample, the counts by tier;
  - per batch, `batch_start` and `batch_end` (its plies, what was accepted, its end), and
    `batch_split` when a batch is halved;
  - `tier0` per code sentence;
  - `tiers`: coverage, each tier-1 ply's end, and the totals by tier. It is written however the run
    ends; a ply never reached ends `not_run`.
  - `frames` lines carry `tier`. `guard`, `request` and `response` are logged as now.
- **The commentary records.** Each accepted item is stored by `submit_commentary` as now. The
  store does not mark a tier: which plies were tier 1 is in the run's log. The viewer's AI panel
  already lists records by ply; it needs no change in rev. 1.

## 5. Measuring it

**Judging.** Judge v2 judges an item against its moment's reference. Tier-1 plies have no
reviewed key causes, so:
- References for tier-1 plies are written by `tools.rx reference` for any ply: digest, full record,
  board and handles. They have `key_causes: []` and `status: "unreviewed"`.
- Judge v2 is used unchanged. An item with no key causes is judged on its sentences. Its `causes`
  stay empty, so it has no M2b, but judge v2 still gives its 1–5 score.
- `judge.bundle` checks every reference before it makes a part.
- A score row judges every tier-2 item plus a **fixed sample of tier-1 plies**: per game, the 3
  tier-1 plies with the largest loss, the same plies in every row. Two games then give 6 + 6 items,
  two judging parts (`PART_MOMENTS = 6`). Judging every tier-1 ply would take about five parts a
  row.

**The score row.** Today's fields stay tier 2's, so rows stay comparable: `cost`, each game's
`totals` and `largest_request` leave tier 1 and tier 0 out. Beside them:
- `rates_tier1` and `completion_tier1`: M1b, M1s, the score and the sentence count over the
  sampled tier-1 items;
- `cost_whole_run`, `judging.items_tier1`;
- per game: `totals_whole_run`, `tiers` (coverage, totals by tier, ends, sample) and
  `frames_tier1`.

A game's `seconds` is still the whole run's.

**Done for rev. 1:** on both development games (184800218248, 185264271324):
- every tier-1 ply is either commented or logged as without text;
- tier 2's rates are within the spread of the rev. 9–11 rows;
- tier 1's M1b is at most twice tier 2's;
- tier 1 costs at most half of tier 2.

## 6. Order

1. **WG1 (tiers and the batch):**
   - `tier_of` from `game_overview` (§1) and the batches (§2);
   - the batch conversation in the harness as rev. 12 (rev. 11 with frame check v4 for tier 2,
     plus tier 1);
   - `harness_tier1_v1`, and tier 0's followed-line sentence;
   - the log fields (§4).

   Tests: the tier and batch rules on the four validation games' grades, the batch bounds, a batch
   without a submission, the followed-line sentence's exact match.
2. **WG2 (measuring):**
   - references for any ply, and the tier-1 sample in `judge.bundle`;
   - the row's new fields.

   Tests: the sample is the same across runs, and a row with no tier-1 items still writes.
3. **The first whole-game score row** on OpenRouter, judged in Claude Code sessions as now.

Each step adds a change-log entry. The owner names whether rev. 1 of this document is reviewed
before WG1.

## 7. Questions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Tier 1's plies: inaccuracies too, or mistakes and blunders only? | Inaccuracies too: 5–20 plies a game is affordable (§2). |
| Q2 | Tier 0: nothing, or a code sentence for every ply? | Nothing but the followed-line sentence (§3). A sentence per quiet move adds length, not meaning. |
| Q3 | Tier 1's tools: `submit_commentary` and `detail` only, or `explore` too? | Without `explore`. If the first row shows tier 1 citing too little, add it as its own row. |
| Q4 | Judging tier 1: a fixed sample of 3 a game, or every ply? | The sample (§5). Every ply when a milestone needs it. |
| Q5 | Review this design before WG1? | Not required by the process (a milestone review only). Recommended, since it is a new direction. |

## 8. Review of rev. 1 and its implementation (2026-11-10)

Four reviewers each read one slice of the work since `acf82b4`:
- tools v11;
- the frame check v2 and v3;
- the harness side of WG;
- WG's measuring and the documents.

Each finding below was reproduced against the code before it was fixed.

| # | Finding | Applied |
| --- | --- | --- |
| R1 | v3 holds right sentences: a gain written with a standing word ("3점을 더 얻어 앞선다"), a count of plies ("3수 만에"), "no change" over a named segment, two crossovers, and a standing written with its sign ("물질은 -1" for a change of +1) | `harness_frames_v4` for rev. 12 (frames.py's docstring). v3 stays as rev. 11 ran |
| R2 | A batch's call naming one ply without `items` was stored but not counted, and was not asked again | counted by its own ply (§2) |
| R3 | Tier 0 could say a line was followed when none of its own moves were | §3's exact rule |
| R4 | The row's `cost`, `totals` and `largest_request` covered tier 1, against §5 | §5's tier-2 fields |
| R5 | The frame check's own `detail` reads were logged after the call that made them, so the run checker's pairing failed. This dates from rev. 8; both rev. 11 runs fail `check` | `harness_call.before`, paired ahead of that call |
| R6 | A call the server's schema refuses never runs and is not logged by the server, so the checker's count was one short | logged `tool_unsent` (`server_schema`) |
| R7 | The `tiers` line was missing when a run ended inside tier 1 | written on every end |
| R8 | A missing tier-1 reference stopped `bundle` after its first parts were made | checked before any part |
| R9 | The tier-1 guide named tools tier 1 lacks, and its submission omitted the required `agent` | corrected; `tier1_refused` |
| R10 | §2.3, §4 and §5 described a log, a store mark and row fields that differ from the code | this revision |
| R11 | `frames_tier1` kept one submission a batch; `reference --tier1` fetched two ranges at most; a halved batch fetched its digests again; the split's count could reuse the last batch's usage | fixed |

Left as they are:
- tools v11 has no test of an en passant label;
- a row's `tools: "repository"` does not name the tools version;
- the `squares` tool still marks a piece's side by its letter's case.

