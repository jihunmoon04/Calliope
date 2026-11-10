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
  - The default model is `claude-haiku-5-5`; OpenRouter stays for `anthropic/…` and other names.
- **P2, the score command.** `python -m tools.rx score` runs H on 184800218248 and 185264271324, one run
  each. It judges each moment with `judge_v2r` (`claude-sonnet-5-5` by default, one request a moment,
  inline input) and appends one row to the scorecard. A moment without commentary is a failure in the
  rates.
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
- **Score rows:** none yet. The Claude API key (`ANTHROPIC_API_KEY`) is not in `.env`; the first rows
  (rev. 8 on OpenRouter, rev. 8 on the Claude API, then rev. 9) wait for it.
