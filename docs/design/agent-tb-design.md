# Agent TB-D — a 100k-token request budget, the Claude API, a shorter process

Status: rev. 4 — re-review of rev. 3 READY_WITH_CORRECTIONS (F1–F3 P1, F4–F8 P2, N1–N9) applied
(§10); implementation proceeds by §6. Rev. 3: the full views hidden, not refused (B3; the owner's
Q3). Rev. 2: review of rev. 1 (PR #165) NOT_READY (F1–F3 P1, F4 P2, N1) applied (§9). Rev. 1:
draft for the owner (2026-11-10). Flows (commentary by game segment) are on hold (§7). This
document is also the first one written in the shorter process it proposes (§2): no separate
implementation packet.

## 0. The owner's direction (2026-11-10)

1. Shorten the process: design, implementation and testing take too long. Keep a quantitative
   record of what each change improves; drop the rest.
2. A harness that keeps every model request within 100k input tokens, designed once and fixed.
3. Run with a Claude API key.

Context: the aim is a Calliope that writes commentary, built on what the RX experiments made (the
harness, the tools, the checks). AF is closed (`agent-af-implementation.md` §16).

## 1. What the pilot measured (`af-pilot-2`, H@v9, harness rev. 8, Haiku 5.5 over OpenRouter)

| | 184800218248 | 185264271324 |
| --- | --- | --- |
| Cost | $0.339 (ended on the 4M token bound) | $0.231 |
| Input tokens | 3.95M, 95% cache reads | 2.89M, 94% cache reads |
| Output tokens | 74k | 76k |
| Cost of the requests above 100k input | $0.299 (88%) | $0.182 (79%) |
| Judge | $0.008 | $0.008 |

- **One conversation carries every moment.** A moment adds 35k–76k tokens; the requests grow from
  19k to 147k–183k. In 184800218248 the three moments cost $0.03, $0.13 and $0.17 with about the
  same number of requests each: the later ones re-read the earlier moments, above Haiku 5.5's
  100k price step (input $0.10 → $0.50 per MTok).
- **The fixed prefix is about 19k tokens:** the system message (11,509 characters: the server's
  instructions and the commentary guide `commentary_ko_v8`) and 14 tool definitions (16,729
  characters). Parts of the system message describe steps the harness does itself (opening and
  analysing the game, the one-move procedure).
- **What the model read** (the tool messages' `content`, from `agent.jsonl`; rev. 3 quoted the
  server's `tools.jsonl` lines, which also hold `structuredContent`, and was wrong — re-review F5):
  - the two full explores, 32,010 and about 32,000 characters;
  - `facts` 16.8k–21.8k;
  - `detail` on an explored line, 19,018;
  - `compare_lines` up to 9.9k, `ply` up to 5.8k;
  - every other answer under 3k. `show_game` is 144 characters.
  - The harness's own `detail` reads never reach the model.
- **A submission** is 2.3k–3.6k characters with its citations; its sentences alone about 1k–1.5k.

## 2. P — the process

**P1. One change log.** `docs/design/agent-changelog.md`: one entry a change. Each entry gives
the date, what changed, why, the commit, and the score row it produced (P2). It replaces the
separate design and implementation documents for ordinary changes.

**P2. One score command.** `python -m tools.rx score --name <label>` runs H on the two development
games used by the pilots (184800218248, 185264271324), one run each, at the current revision. It
appends one row to `docs/design/rx-evidence/scorecard.jsonl`. Each row records:

- the commit, the harness revision, the tools version, the writing model and its provider, the
  effort;
- per game: the end reason, the moments' ends (B7), the largest request (total input tokens),
  total tokens, cost and seconds;
- the frame check's holds and `uncheckable`, `search_numbers` and `ambiguous`;
- **completion**: the moments with accepted commentary out of the moments asked;
- the judged rates (M1b, M1s, M2b) by P2a, with the judging's model, prompt version, schema digest
  and failures (an unreadable or missing verdict). A moment without commentary counts as a failure
  in the rates, never left out, so fewer moments cannot read as better commentary.

**P2a. The score judge (re-review F3).** Judge v2 (`judge_v2.md`) is an agent: it reads
`bundle.json` and `references/*.json` from a directory and checks lines with scripts. One request
without tools cannot do that. The score command therefore uses its own prompt:

- `judge_v2r` (new): one request a moment, tools none.
- Its input is given inline: the moment's sentences with their evidence (as `evidence.py` renders
  it for judge v2), the moment's `digest`, its reference `key_causes`, and the position (FEN) with
  the moves cited. The `full` records and scripts are left out.
- Its output follows `judge_v2.schema.json`.
- The judging model is fixed and named apart from the writing model: `claude-sonnet-5-5` on the
  Claude API by default.
- Two rows compare only when their (judging model, prompt, schema digest) are the same.
- These rates are the score's scale, not the milestone's: the milestone's blind measurement keeps
  judge v2 as it is.

A score run costs about what one pilot costs now, less after B (§3).

**P3. Milestones.** The freeze, a Test set's opening, the blind measurement and an independent
review happen only at a milestone, which the owner names. The first milestone is the 100k harness
on Test 2 (§6). Between milestones, a change needs a change-log entry, its tests and a score row.

**P4. CLAUDE.md.** Its rule "design document → independent review → implementation packet →
review" becomes: "a change: an entry in `agent-changelog.md`, its tests, a score row; a design
document only for a new direction; independent review at milestones."

## 3. B — the 100k harness (harness rev. 9, tools v10)

**B1. A conversation per moment.** Each moment starts a new message list with these parts:

1. the fixed prefix (system, tools);
2. the task;
3. **the story so far**: the earlier moments' accepted sentences as text, their moves numbered and
   their citations left out. It is for continuity of the prose, not for citing (re-review N5): a
   handle the agent wants to cite again comes from the tools in this moment;
4. the moment's stage messages (facts, check, judge's retries, submit), as in rev. 8.

Size: about 1k–1.5k characters a moment, so the story stays under 10k tokens for a game of eight
moments. In a longer game, the last four moments keep their sentences and earlier ones keep one
line each. The new list is logged once as a `moment_start` line, and the log index `sent` is set
to its length (re-review N3).

**B2. A smaller fixed prefix: at most 10k tokens.**

- **The tools the harness serves (10):** `ply`, `judge_move`, `detail`, `facts`, `explore`,
  `compare_lines`, `squares`, `game_overview`, `submit_commentary`, `definitions`.
  - `definitions` stays (re-review F7). Both pilot runs used it, and the guide
    (`commentary_ko_v8.md`) and `submit_commentary`'s description send the agent to it for a
    proposition kind's fields.
  - `show_game`, `open_game`, `analyze_game` and `commentary` are not served: the harness opens
    and analyses the game, and the viewer is the reader's. Their answers are small (`show_game`
    144 characters), so this saves descriptions, not answers.
- **The system message becomes a harness guide:** the commentary guide's rules for sentences,
  citations, notation and `board`, without the server's opening and analysis steps.
- **The long tool descriptions are shortened** (`explore` 2.6k, `submit_commentary` 2.9k,
  `compare_lines` 2.1k characters).
- **Measured** with the Claude API's token count (C5), not by characters.

**B3. Answer size.**

- **The full views are hidden, not refused** (the owner, rev. 3). The full view of `explore`,
  `facts`, `ply` and `judge_move` holds nothing the agent cannot get otherwise:
  - The brief keeps every piece in play (attacked, attacking, pinned, defending, giving check, on
    the last move's square). It leaves out idle pieces and the legal-move list.
  - An idle piece is one `squares` call away.
  - One claim, line or record in full is one `detail(ref)` away.
  - In `af-pilot-2`, the agent's two full explores (32k characters each) gave its submission
    nothing the brief lacked: it cited a pin, which the brief shows.
- **How it is hidden.**
  - The harness sends the tool schemas without the `view` property.
  - The gate drops `view` from a call that still sends it, with no error turn. It logs a
    `view_dropped` line (re-review N6).
  - Every pointer to `view: "full"` becomes a pointer to `detail(ref)` (re-review F6). That changes
    answers, so it is `agent_tools_v10`. The places:
    - `brief.py` (the omission note, the `legal_moves` note);
    - `digest.py` (`not_shown.full`, and `DigestTooLarge`'s message);
    - `session.py` (`NEXT_OPENED`);
    - `server.py` (`DETAIL` and the descriptions of `ply`, `judge_move`, `facts`, `explore`);
    - `commentary_ko_v8.md` (line 120) and the harness guide.
  - `DigestTooLarge` names no ref, so `detail` cannot follow it. Its message names what can:
    `squares` on the squares in question, or `judge_move` on one candidate.
  - The harness's own reads (the frame check's `detail`) are not model input and stay as they are.
- **The answer cap: a tool message's `content` above 24,576 bytes (UTF-8) is refused** (re-review
  F5), never cut, since a cut record could be cited half-read. The refusal says what to ask
  instead, by tool:
  - `detail` on an explored line (`x…`): `facts` or `squares` at its end (`from_root`);
  - `explore`, `compare_lines`: a shorter `length` or fewer candidates;
  - `game_overview`: a narrower `plies`;
  - `facts`: fewer families or a narrower position;
  - otherwise: a narrower ref.

  It is logged as a `tool_refused` line. In the pilot this refuses the two full explores (hidden
  anyway). The largest other answers (`facts` 21.8k characters, mostly ASCII) pass.

**B4. The guard: no request above 100k.**

1. **What is counted.** Right before each request, the runner counts the whole request as it will
   be sent: system, tools and messages, after C3's conversion. On the Claude API the count is
   `messages.count_tokens` on that request. It runs in the request child with a 30-second
   deadline (re-review N1); a failed count is retried once, then the request is estimated as on
   OpenRouter (item 5). An earlier answer's usage is never used for the next request's size.
2. **Where.** The guard sits in `_loop`, right before `model.complete`. Over a threshold, `_loop`
   sends nothing and returns `compact` (80k–95k, or above 95k before the moment's restart) or
   `moment_budget` (above 95k after it). `harness_loop` acts on the return (B7).
3. **Compaction (re-review F1).**
   - **The request.** It is the last list that was at most 95k: the current list without its last
     assistant turn and that turn's tool answers, if those pushed it over. Then one message asks
     the agent to keep what the commentary needs as notes (a move, a claim, a handle), at most 2k
     tokens.
   - **Settings.** The tools are sent as always, so the cached prefix holds, with
     `tool_choice: {"type": "none"}`.
   - **Checks.**
     - If even that request counts above 95k, the moment ends (`moment_budget`).
     - Notes counted above 2k tokens are refused and asked for once more, never cut. A second
       refusal ends the moment.
   - **The restart.** The moment's list is rebuilt from B1's parts, the notes and the state B7
     keeps.
   - **One restart a moment.** After it, 80k means nothing and 95k ends the moment.
4. **What a request used** is recorded from its answer: the total input (uncached + cache read +
   cache write, C5) beside its parts, and the count made before sending. The scorecard's largest
   request is the largest total input.
5. **OpenRouter is a weaker contract.** It has no token count. There the size is estimated:
   - from the last answer's `prompt_tokens` (OpenRouter's total input) plus the new messages'
     characters at a conservative ratio (one token per two characters);
   - for a moment's first request, which has no last answer, from the whole request's characters
     at that ratio;
   - against a lower send limit (85k).

   It is recorded as `estimated`. The 100k guarantee is the Claude API path's alone; OpenRouter
   stays for repeating past runs.

B1–B3 should make compaction rare. B4 is the guarantee.

**B5. Bounds.** The per-run 4M token bound becomes a per-run cost bound ($1). Turns and tool calls
stay as now. The 100k limit is B4's, per request. The harness's token-based budget checks (the
judge's budget and the "no judge past the bound" check, `harness.py` 670, 708, 730) read the cost
bound instead (re-review N4).

**B6. What changes and what does not (re-review F6).**
- **Changes in rev. 9:** tools v10 (B3); the gate drops `view` and enforces the 24 KB cap;
  conversations per moment (B1); the guard (B4); moment ends (B7).
- **Unchanged:** the stages, the frame check (F1–F3), the judge and its rubric (`harness_judge_v3`),
  the gate's submission rules.
- **Versions.** Before tools v10 merges:
  - tag the current main `agent-tools-v9` and make its server worktree;
  - add `v10` to `TOOLS_VERSIONS` and `v9` to `SERVER_ROOTS` (`run.py`), so rev. 8 can still run
    on v9.

  (`SERVER_ROOTS`' `v8` names a worktree no tag exists for; it is removed.)
- **First rows.** The scorecard's first rows give rev. 8 (v9) and rev. 9 (v10) on the same two
  games.

**B7. Ends: a moment's or the run's.** Today any end other than `done` from the plain loop ends the
whole run. Rev. 9 separates them:

| End | Where it comes from | What happens |
| --- | --- | --- |
| `done` | the agent answered without a tool call | the moment's next stage, or the next moment |
| `compact` | B4: over 80k, or over 95k before the restart | compaction (B4.3), then the restart |
| `moment_budget` | B4 after the restart; a compaction that cannot be made | the moment is recorded unsubmitted, with the stage it reached; the next moment starts |
| `moment_cut` | C4: an answer cut at `max_tokens` twice in a row | as `moment_budget` |
| `moment_refused` | C6: the model's refusal | as `moment_budget`, with the refusal's category |
| `cost`, `turns`, `tool_calls`, `wall_clock`, `timeout` | the run's bounds (B5) | the run ends, as today |
| `error` | a model or server error after its retries; the engine's build changed | the run ends, as today |

The moment's state across a restart:
- **Kept:**
  - the moment's stage (facts, check, submit) and its retry count;
  - the gate's phase, current ply and holds; what the check accepted (`gate.checked`);
  - **the last facts reply the judge passed, verbatim** (re-review F4), so a restart in the submit
    stage still has it;
  - the run's totals, and the accepted commentary of earlier moments (the story).
- **Rebuilt:** the message list = B1's parts, then the notes, then the passed facts reply (if any),
  then **the current stage's message: the last runner message sent, as it was filled** (with its
  `{problems}` in a retry).
- **Logged:** the new list once, as a `restart` line; `sent` is set to its length.

Tests:
- a compaction in each stage (facts, check's retry, submit); after a restart in submit, the list
  holds the passed facts reply;
- a budget end in each stage, followed by the next moment with the earlier moments' commentary
  intact;
- a run bound reached inside a moment ends the run.

## 4. C — the Claude API

**C1. Provider by model name.** A model named `claude-…` goes to Anthropic's Messages API with
`ANTHROPIC_API_KEY`; `anthropic/…` and others still go through OpenRouter, so past runs repeat.
The default model becomes `claude-haiku-5-5` on the Claude API. The key is read from the
environment or `--env-file` and never written or logged.

**C2. The official SDK, inside the request child.** `tools/rx/request.py` keeps the request in a
child process killed at the deadline (RX2-D §2). For the Claude API, the child calls
`anthropic.Anthropic().messages.create(...)` (and `messages.count_tokens`); it does not use raw
HTTP. The `anthropic` package joins the `agent` extra.

Deadlines (re-review N2):
- the Claude request's deadline is 300 seconds (`REQUEST_SECONDS` stays 120 for OpenRouter);
- the SDK runs with `max_retries=2` and a per-attempt `timeout` of 90 seconds, so its retries fit
  inside the child's deadline;
- the runner's own retry (one, on a timeout or transport error) stays.

**C3. Messages: one contract for the loop, the original blocks for the API.**

The loop and the harness read an answer as `content` (text) and `tool_calls` (OpenAI's shape):
- `_loop` runs `reply.message["tool_calls"]`;
- `last_text` and `claims_of` read the text.

The Claude client keeps that contract and adds one field:

- **The answer, normalized.** `Reply.message` gets:
  - `content`: the answer's `text` blocks joined;
  - `tool_calls`: one entry a `tool_use` block, with `id`, `function.name`, and `function.arguments`
    holding the block's `input` as a JSON string;
  - `blocks`: the answer's whole `content` array exactly as returned, signed `thinking` blocks
    included.
- **The kept message.** `_loop` copies `blocks` into the assistant message it keeps, as it copies
  `reasoning` now. A cut answer is not kept (C4).
- **The next request.** Converting the history for the Claude API:
  - An assistant message that has `blocks` is sent as those blocks, never rebuilt from `content`
    and `tool_calls`.
  - An assistant message without `blocks` (the runner's own, or one from OpenRouter) is built from
    `content` and `tool_calls`.
  - The `tool` messages after an assistant message become one user message: its `tool_result`
    blocks first, in the calls' order (parallel calls answered together), then any text the runner
    added (`feedback`, stage messages). A tool message starting `[tool error]` becomes a
    `tool_result` with `is_error: true` (re-review N9).
  - Consecutive user messages are merged into one.
  - Tool definitions become `input_schema`.
- **Append-only.** Each moment's list (B1) is append-only between restarts. Compaction (B4.3) sends
  a prefix of it plus one message, which is also append-only from that prefix.

Tests:
- a round trip: an answer with thinking, text and two `tool_use` blocks runs both tools, and the
  next request carries the same blocks byte for byte;
- `claims_of` reads a facts reply written across text blocks;
- a history from OpenRouter converts;
- a tool error converts to `is_error`.

**C4. Request settings.** For Haiku 5.5:

- thinking adaptive (its default; never `disabled`);
- `output_config.effort` set explicitly: the run's `reasoning_effort`, or `medium` when it is
  `None` (re-review N7);
- `tool_choice` auto (`none` for compaction, B4.3);
- no temperature;
- **`max_tokens` 16,000**, required by the Messages API. Thinking counts toward it, so it is large
  enough that a facts reply with its claims block, or a submission, is not cut by thinking.
- **The judge's requests: `max_tokens` 4,000** (a new limit; re-review N8). A judge answer cut at
  it is recorded and asked once more; a second cut is `unreadable`, as today.

The answer's `stop_reason`:

| `stop_reason` | Handling |
| --- | --- |
| `tool_use` | run the calls |
| `end_turn` | `done` |
| `max_tokens` | **not kept in the conversation** (re-review F2): a cut `tool_use` has no `tool_result`, and a cut block cannot be sent back. The answer is logged in its `response` line only; its calls are never run. A user message follows ("your answer was cut; write it shorter or in steps"). A second cut in a row is `moment_cut` (B7). |
| `refusal` | `moment_refused` (B7), with `stop_details.category` recorded |
| `pause_turn` | not expected without server tools; recorded as an error |

Tests:
- a cut answer with a `tool_use` block is not run, and the next request holds none of its blocks;
- two cuts end the moment, and the next moment starts.

Caching: `cache_control` on the system block and the last message, as the OpenRouter marks do
now. The order is tools → system → messages, so the fixed prefix is cached across moments.

**C5. Usage and cost (re-review F8).** The Claude API returns tokens, not cost.

- `usage.input_tokens` means the **total input** on both providers: on the Claude API,
  `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`. That keeps the runner's
  sums and bounds comparable with OpenRouter's `prompt_tokens`.
- The parts are kept beside it: `uncached_input_tokens`, `cached_tokens`, `cache_write_tokens`,
  and the pre-send count `counted_tokens`.
- Cost is computed from a price table in `model.py`, including the 100k step. The prices are
  checked against Anthropic's pricing page when written.
- `messages.count_tokens` gives B4 its sizes and B2 its measure.

**C6. Errors.** Rate limits and server errors are retried by the SDK (C2). A refusal
(`stop_reason: "refusal"`) ends the moment and is recorded (B7).

## 5. Ordinary moves: three tiers (after B, not in rev. 9)

The harness spends its effort on a few fixed moments. A whole game's commentary also needs the
moves between them, without an agent run for each. The tiers are read from `game_overview`'s grade
and loss for every ply:

| Tier | Moves | How |
| --- | --- | --- |
| 0 | book, forced, quiet (best/excellent, small loss) | a sentence from code, or none |
| 1 | inaccuracies and mistakes outside the fixed moments | one request without tools for 10–20 moves, given their facts and the moments' accepted commentary; the frame check runs on its sentences |
| 2 | the fixed moments | the harness (B) |

A move that follows a line the commentary already cited gets one sentence ("the line went on as
shown"). This is the next direction after B. Its design waits for B's score rows.

## 6. Order and done

Each step's corrections from the re-review are in the text above. They were applied before the
step starts.

1. **C** (Claude API).
   - Done when: an H run on 185264271324 completes on `claude-haiku-5-5` with cost, total input
     and cache reads recorded.
   - Tests: the conversion (C3), cut answers (C4), the price table and usage (C5), the key never
     logged.
2. **P2** (score command, `judge_v2r`, scorecard).
   - Done when: the first two rows are rev. 8 on OpenRouter and rev. 8 on the Claude API.
3. **B** (rev. 9, tools v10).
   - First the `agent-tools-v9` tag and worktree (B6).
   - Done when: on both games no request exceeds 100k (the scorecard's largest request), no
     moment ends on budget, and cost, completion and frame-check rows are no worse than rev. 8's.
4. **P1, P4**: the change log opened with these entries; CLAUDE.md amended.
5. **First milestone** (when the owner names it): Test 2's freeze and opening, H@rev. 9 measured,
   judged with judge v2.

## 7. On hold: flows

Commentary by game segment (a blunder and its punishment as one flow) was prototyped on the eight
development games, outside the repository. It found about three flows a game, and 22 of the 24
fixed moments fell inside one. Of 18 errors answered by an error within three moves, 16 were
misses (back to about the level before) and 2 were reversals. The owner put flows on hold. B1's
"story so far" and the tiers do not depend on them.

## 8. Questions for the owner

The owner (2026-11-10) answered Q3 and asked for implementation once a re-review passes. Q1, Q2
and Q4–Q6 were not answered one by one; the implementation takes their recommendations, and the
owner may change any of them.

| # | Question | Recommendation | Answer |
| --- | --- | --- | --- |
| Q1 | Score runs: two development games, one run each? | Yes. Enough to see a regression; milestones measure properly. | recommendation |
| Q2 | Arm A in score runs? | No: H only. A stays reachable for milestones. | recommendation |
| Q3 | `view: "full"` under the harness: refuse, or cap? | Refuse (B3); `detail` gives one record in full. | **Hide it** (the owner): B3 rev. 3 |
| Q4 | Effort for Haiku 5.5 | `medium` (its default), set explicitly; a score row at `low` later if cost matters. | recommendation |
| Q5 | The per-run bound | $1 a run, in place of 4M tokens. | recommendation |
| Q6 | The tiers (§5) | After B, as their own design. | recommendation |
| Q7 | The score judge's model (P2a) | `claude-sonnet-5-5`, apart from the writer. | recommendation |

## 9. Review of rev. 1 (PR #165, NOT_READY)

Each finding was checked against the code before it was applied.

| # | Finding | Checked | Applied |
| --- | --- | --- | --- |
| F1 (P1) | The Claude answer's blocks against the loop's contract | True: `_loop` runs `reply.message["tool_calls"]` and keeps only `content`, `tool_calls`, `reasoning`; `last_text` and `claims_of` read text | C3: the normalized answer plus `blocks`, the original blocks sent back, the round-trip tests |
| F2 (P1) | The guard's count cannot come from the last usage | True: Anthropic's `input_tokens` excludes cache reads and writes; `count_tokens` is an estimate | B4: the whole converted request counted before sending, 80k compaction and 95k send limit, the total input recorded; OpenRouter as a weaker, estimated contract |
| F3 (P1) | A moment's budget end would end the run | True: `harness_loop` returns on any end other than `done` | B7: moment ends apart from run ends, the state kept and reset across a restart, tests per stage |
| F4 (P2) | `max_tokens` and `stop_reason` | True: `max_tokens` is required; a cut answer may hold a cut `tool_use` | C4: 16,000, the `stop_reason` table, the cut-answer tests |
| N1 (P2) | The score row's reproducibility and completion | Agreed | P2: the judging's model, prompt, schema and failures; completion, with missing moments counted as failures |

## 10. Re-review of rev. 3 (READY_WITH_CORRECTIONS)

An independent session re-reviewed rev. 3 against the code. Every finding was checked before it
was applied. F5's sizes were measured again from `agent.jsonl`: full explore 32,010 characters,
`show_game` 144, `detail` 19,018.

| # | Finding | Applied |
| --- | --- | --- |
| F1 (P1) | Compaction at 95k would itself be over 95k; compaction undefined | B4.2–3: the guard in `_loop` returning `compact`; the request from the last list at most 95k; `tool_choice` none; notes over 2k refused and asked once; one restart a moment |
| F2 (P1) | A cut answer kept in the conversation makes the next request a 400 | C4: a cut answer is logged only, never kept; a test that the next request holds none of its blocks |
| F3 (P1) | Judge v2 cannot run as one request | P2a: `judge_v2r`, inline input, the judging model fixed and named, rows compare only on the same (model, prompt, schema); not the milestone's scale |
| F4 (P2) | A restart loses the passed facts reply and the stage message | B7: the passed facts reply kept verbatim; the stage message is the last runner message as filled; a test for submit |
| F5 (P2) | §1's sizes were log lines, not model input; 24 KB had no unit | §1 measured from `agent.jsonl`; B3: 24,576 bytes of `content` (UTF-8); refusals named by tool; `tool_refused` |
| F6 (P2) | The `view: "full"` pointers incomplete; B6 contradicted B3; versions | B3 lists the places; `DigestTooLarge` names `squares` or `judge_move`; B6 rewritten; the `agent-tools-v9` tag and worktree before v10 |
| F7 (P2) | `definitions` is used | B2: `definitions` kept (10 tools) |
| F8 (P2) | Claude's `input_tokens` meaning | C5: `input_tokens` is the total input; the parts beside it |
| N1 | `count_tokens` placement and failure | B4.1: in the child, 30 s, one retry, then estimated |
| N2 | Deadlines | C2: 300 s for Claude, SDK timeout 90 s with two retries |
| N3 | `sent` after a restart | B1, B7: `sent` = the new list's length |
| N4 | Token-based judge budgets; end names | B5: the cost bound; B7: `wall_clock`, `timeout` |
| N5 | Story handles vs citations left out | B1: the story is prose only; handles come from the moment's tools; notes only from compaction |
| N6 | A dropped `view` | B3: `view_dropped` |
| N7 | `reasoning_effort` `None` | C4: `medium` |
| N8 | The judge's 4,000 limit | C4: a cut judge answer asked once more, then `unreadable` |
| N9 | `[tool error]` | C3: `is_error` |
