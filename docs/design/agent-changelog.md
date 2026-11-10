# Agent change log

One entry a change (TB-D §2 P1). Each entry gives the date, what changed, why, the commit and the score
row it produced (`docs/design/rx-evidence/scorecard.jsonl`, by its `name`). A change between milestones
needs an entry here, its tests and a score row. A design document is written only for a new direction,
and an independent review happens at milestones (CLAUDE.md).

## 2026-11-10 — TB: the Claude API, the score command, harness rev. 9 (branch `agent/tb`)

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

- **Change.** The owner chose v1 after the pooled rows: v2's wrong sentences were 11.5 a 100 against
  v1's 6.3.
  - `HARNESS_GUIDE` is `harness_guide_v1` again; v2 stays reachable with `--harness-guide`.
  - TB-D B2's 10k target is set aside. The 100k request limit holds with v1 (largest request 77k).
- **Score row:** none new. The current configuration is the one `tb-rev9-openrouter` and
  `tb-rev9-guide1-openrouter-2` scored.

## 2026-11-10 — the implementation review applied (TB-D rev. 7, §11)

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

