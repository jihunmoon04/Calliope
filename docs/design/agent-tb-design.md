# Agent TB-D — a 100k-token request budget, the Claude API, a shorter process

Status: rev. 1, draft for the owner (2026-11-10). Flows (commentary by game segment) are on hold
(§7). This document is also the first one written in the shorter process it proposes (§2): no
separate implementation packet; one review, by the owner.

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
  characters). Five tools are not used inside the harness (`show_game`, `open_game`,
  `analyze_game`, `commentary`, `definitions`: 4.3k characters). Parts of the system message
  describe steps the harness does itself (opening and analysing the game, the one-move procedure).
- **The heaviest answers in the conversation:** `explore` with `view: "full"` (72 KB, twice),
  `show_game` (the reader's viewer, 39 KB, three times), then `compare_lines`, `facts`, `squares`.
  The harness's own `detail` reads (2.3 MB) never reach the model.
- **A submission** is 2.3k–3.6k characters with its citations; its sentences alone about 1k–1.5k.

## 2. P — the process

**P1. One change log.** `docs/design/agent-changelog.md`: one entry a change. Each entry gives
the date, what changed, why, the commit, and the score row it produced (P2). It replaces the
separate design and implementation documents for ordinary changes.

**P2. One score command.** `python -m tools.rx score --name <label>` runs H on the two development
games used by the pilots (184800218248, 185264271324), one run each, at the current revision. It
appends one row to `docs/design/rx-evidence/scorecard.jsonl`. Each row records:

- the commit, the harness revision, the tools version, the model and its provider;
- per game: the end reason, the largest request (input tokens), total tokens, cost and seconds;
- the frame check's holds and `uncheckable`, `search_numbers` and `ambiguous`;
- judge v2's rates (M1b, M1s, M2b), read by one judging request a run, so a row needs no manual
  bundle.

The scorecard is the quantitative history: any two rows compare. A score run costs about what
one pilot costs now, less after B (§3).

**P3. Milestones.** The freeze, a Test set's opening, the blind measurement and an independent
review happen only at a milestone, which the owner names. The first milestone is the 100k harness
on Test 2 (§6). Between milestones, a change needs a change-log entry, its tests and a score row.

**P4. CLAUDE.md.** Its rule "design document → independent review → implementation packet →
review" becomes: "a change: an entry in `agent-changelog.md`, its tests, a score row; a design
document only for a new direction; independent review at milestones."

## 3. B — the 100k harness (harness rev. 9)

**B1. A conversation per moment.** Each moment starts a new message list with these parts:

1. the fixed prefix (system, tools);
2. the task;
3. **the story so far**: the earlier moments' accepted sentences as text (their moves numbered,
   their citations left out) and the notes kept for later moments (B4);
4. the moment's stage messages (facts, check, judge's retries, submit), as in rev. 8.

The server's handles live as long as the game is open, so a note's or a sentence's handle stays
citable. Size: about 1k–1.5k characters a moment, so the story stays under 10k tokens for a game of
eight moments. In a longer game, the last four moments keep their sentences and earlier ones keep
one line each.

**B2. A smaller fixed prefix: at most 10k tokens.**

- The harness serves only the tools it uses: `ply`, `judge_move`, `detail`, `facts`, `explore`,
  `compare_lines`, `squares`, `game_overview`, `submit_commentary`.
- The system message becomes a harness guide: the commentary guide's rules for sentences,
  citations, notation and `board`, without the server's opening and analysis steps.
- The long tool descriptions (`explore` 2.6k, `submit_commentary` 2.9k, `compare_lines` 2.1k
  characters) are shortened.
- Measured with the Claude API's token count (C5), not by characters.

**B3. Answer size.** Under the harness, `explore`'s `view: "full"` and `ply`'s full view are
refused, with the message "the brief view and `detail` on one ref". Any tool answer above 24 KB is
refused the same way, never cut: a cut record could be cited half-read.

**B4. The guard: no request above 100k.**

- Before each request the runner knows its size: the last answer's input tokens plus the new
  messages, counted by C5's token count on the Claude API (on OpenRouter, estimated from
  characters with a margin).
- **At 80k:** one message tells the agent to keep what the commentary needs as notes (a move, a
  claim, its handle; at most 2k tokens). Then the moment's conversation restarts from B1's parts
  plus the notes, and the old tool answers are dropped.
- **At 95k after that restart:** the moment ends unsent (`budget`), recorded like a token end
  today, and the next moment starts.

B1–B3 should make the restart rare. B4 is the guarantee.

**B5. Bounds.** The per-run 4M token bound becomes a per-run cost bound ($1). Turns and tool calls
stay as now. The 100k limit is B4's, per request.

**B6. Unchanged:** the stages, the frame check (F1–F3), the judge and its rubric, the gate, tools
v9. The scorecard's first rows give rev. 8 and rev. 9 on the same two games.

## 4. C — the Claude API

**C1. Provider by model name.** A model named `claude-…` goes to Anthropic's Messages API with
`ANTHROPIC_API_KEY`; `anthropic/…` and others still go through OpenRouter, so past runs repeat.
The default model becomes `claude-haiku-5-5` on the Claude API. The key is read from the
environment or `--env-file` and never written or logged.

**C2. The official SDK, inside the request child.** `tools/rx/request.py` keeps the request in a
child process killed at the deadline (RX2-D §2). For the Claude API, the child calls
`anthropic.Anthropic().messages.create(...)` and does not use raw HTTP. The `anthropic` package
joins the `agent` extra.

**C3. Messages.** The loop keeps its messages as today; the Claude client converts them at the
request:

- system → `system`;
- an assistant message with `tool_calls` → `tool_use` blocks;
- consecutive `tool` messages → one user message of `tool_result` blocks (parallel calls answered
  together);
- tool definitions → `input_schema`.

The answer's content blocks are kept unchanged in the assistant message and sent back unchanged.
Thinking blocks need that. Each moment's list (B1) is append-only between restarts.

**C4. Request settings.** For Haiku 5.5:

- thinking adaptive (its default; never `disabled`);
- `output_config.effort` set explicitly from the run's `reasoning_effort` (Haiku 5.5's default is
  `medium`);
- `tool_choice` auto;
- no temperature.

Caching: `cache_control` on the system block and the last message, as the OpenRouter marks do
now. The order is tools → system → messages, so the fixed prefix is cached across moments.

**C5. Usage and cost.** The Claude API returns tokens, not cost.

- The usage line records input, cache read, cache write and output tokens.
- Cost is computed from a price table in `model.py`, including the 100k step; the prices are
  checked against Anthropic's pricing page when written.
- `messages.count_tokens` gives B4 its sizes and B2 its measure.

**C6. Errors.** Rate limits and server errors are retried by the SDK (2 retries). The deadline
and the transport retry stay as now. A refusal (`stop_reason: "refusal"`) ends the moment and is
recorded.

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

1. **C** (Claude API).
   - Done when: an H run on 185264271324 completes on `claude-haiku-5-5` with cost and cache read
     recorded.
   - Tests: the conversion, the price table, the key never logged.
2. **P2** (score command and scorecard).
   - Done when: the first two rows are rev. 8 on OpenRouter and rev. 8 on the Claude API.
3. **B** (rev. 9).
   - Done when: on both games no request exceeds 100k (the scorecard's largest request), no
     moment ends on budget, and cost and frame-check rows are no worse than rev. 8's.
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

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Score runs: two development games, one run each? | Yes. Enough to see a regression; milestones measure properly. |
| Q2 | Arm A in score runs? | No: H only. A stays reachable for milestones. |
| Q3 | `view: "full"` under the harness: refuse, or cap? | Refuse (B3); `detail` gives one record in full. |
| Q4 | Effort for Haiku 5.5 | `medium` (its default), set explicitly; a score row at `low` later if cost matters. |
| Q5 | The per-run bound | $1 a run, in place of 4M tokens. |
| Q6 | The tiers (§5) | After B, as their own design. |
