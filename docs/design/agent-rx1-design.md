# Agent RX1-D — the Calliope-run agent and its run record

Status: **design, rev. 1, for independent review. Owner questions are in §9.** Date: 2026-11-05.
Base: `main @ 6136d29` (RX0-D merged, PR #139).
Inputs: [`agent-reflection-framing.md`](agent-reflection-framing.md) (the RX framing: §3 the agent, §3.1 the
record), [`agent-rx0-design.md`](agent-rx0-design.md) (RX0-D: §2 the manifest, §3.1 `rx_moments`, §4 the
record, §5 `evidence_identity`, §6.0 the final commentary, §8 the arms and the guide freeze).

RX0-D fixed what a run records and how it is measured. RX1 builds the pieces that make a run: the server's
recording, the runner, the manifest, `rx_moments`, `evidence_identity` and the calibration guide. RX1 runs no
arm for comparison. Its acceptance (§8) runs arm A on Train to show that runs are whole. RX2 then measures.

## 1. Pieces and where they live

| Piece | Where | Why there |
| --- | --- | --- |
| The tools layer: `call`, `handle`, `submission`, `start`, `end` lines | `calliope.agent`, a new module `record.py`, hooked in `server.py` and `session.py` | only the server sees tool calls, handle bindings and check outcomes |
| `evidence_identity` | `calliope.agent.record` | it reads a handle's binding (`Entry` in `handles.py`) |
| `rx_moments` | `calliope.agent.session`, beside `_moments` | both rank by the same reasons (§3) |
| The runner and the agent layer | `tools/rx/` (`python -m tools.rx run …`) | a client of the server, like HIMARI; nothing in `src/` imports it |
| The manifest `sets_v1.json` and its checker | `tools/rx/` | RX0-D §2 |
| `commentary_min_v1` | `src/calliope/agent/prompts/` | beside v8, served the same way (§6) |

`tests/test_package_boundaries.py` needs no change: `record.py` is inside `calliope.agent` and imports
nothing new. `tools/rx` imports the MCP SDK's client (the `agent` extra, `mcp==2.3.0`) and the standard
library only. The model is called over HTTP with `urllib`, so RX1 adds no dependency.

## 2. The server's recording (tools layer)

- **Off by default.** `tools/mcp/__main__.py` reads `CALLIOPE_RUN_RECORDS`. Unset, the session gets no
  recorder and every answer, timing and stored file is as today (RX0-D AM2). Set, it reads `CALLIOPE_RUN_ID`, or
  draws a ULID, and opens `<records>/<run_id>/tools.jsonl`.
- **`call` lines** come from the wrapper every tool already passes through (`run` in `build_server`, one call
  at a time per session, AG-D C9). The wrapper records the tool's name, its arguments, the time and the answer
  (or the error) after the tool returns. It does not change the answer.
- **`handle` lines** come from `Session._serve`. After `Handles.serve` returns a ref that `fresh` counted as
  new, the recorder writes the entry's `ref`, `kind`, `game`, `source`, `address` and `identity`. A ref served
  again writes nothing.
- **`submission` lines** come from `submit_commentary`. For each subject the recorder writes the outcome of
  `_commentary` (`accepted`, `duplicate`, `refused`, `not_stored`), the stored `id`, the sentences with their
  `cites`, and every problem with its `rule` (RX0-D §4.2).
- **The cap.** The recorder counts the bytes of `answer` fields. Past 32 MiB a run it writes `answer_sha256`,
  `answer_bytes` and `capped: true` instead of the answer. `handle` and `submission` lines are never capped
  (RX0-D §4.2).
- **Writing.** One line per event, flushed after each line, so a crash leaves every line before it. A write
  error stops recording, writes nothing more, logs to stderr and never fails the tool call. The run is then
  not whole (RX0-D §4.4) and is counted as a failure.
- **`start` and `end`.** `start` is written when the session opens: the build identity (`agent_build`, the
  reasoning build, `TOOLS_VERSION`), the engine's identity, the limits, the guide versions served. `end` is
  written when the server closes, with the counts and the capped calls.

## 3. `rx_moments`

`_moments` (`session.py`) today computes each ply's reasons, ranks every ply that has one, keeps the first 16
and sorts them by ply. RX1 splits it with no change to its output:

- `_ranking(summaries)` returns every ply with a reason, in ranking order, each with its reasons;
- `_moments(summaries)` is `_ranking`'s first `MOMENTS`, sorted by ply, as before;
- `rx_moments(summaries)` applies RX0-D §3.1 to the whole ranking: two error moments, one special moment,
  filled from the ranking, or refused when the ranking has fewer than three plies.

`Session.rx_moments(game_id)` reads the summaries of a game whose every ply is analysed and returns the three
plies with their reasons and which slots were filled. It is not an MCP tool. `tools/rx` calls it in process
when it builds the manifest (§5), so the agent never sees which moments are fixed until the runner's prompt
names them (§4.2).

Tests (RX0-D §3.1): more than 16 ranked plies with the special moment past 16; only `miss`; one error moment;
fewer than three ranked plies; `_moments` unchanged on the suite's games (its existing tests pass as they are).

## 4. The runner (agent layer)

### 4.1 One run

`python -m tools.rx run --arm A --set train --game hung --runs 3` runs, for each run:

1. draw a run id; start `python -m tools.mcp` as a child process with `CALLIOPE_RUN_ID`, `CALLIOPE_RUN_RECORDS`
   and a fresh data directory whose ply cache is linked to the set's warm analyses (RX0-D §8, "Caches");
2. connect with the MCP SDK's stdio client; read the server's instructions and its tools;
3. check the game's PGN against the manifest's digest (RX0-D §2). A mismatch stops the run;
4. build the system prompt: the server's instructions, then the guide as the server serves it (the resource
   `calliope://guides/commentary_ko`, `commentary_ko_v8`; `commentary_min_v1` for A-min), then the arm's
   lessons (D, D-min; none in RX1). In HIMARI the agent reads that resource itself when the instructions tell
   it to. The runner puts it in the system prompt so that every run has read it (FR's `min0`: six of eight runs
   skipped a guide they were not told to read). RX2 reports this difference with the HIMARI comparison;
5. send the task (§4.2) and loop: model request → tool calls through MCP → results back → next request;
6. end at the model's final answer or at a bound (turns, tool calls, tokens); write `end`; close the server.

Every request and response goes to `agent.jsonl` (RX0-D §4.3). A request line holds the messages added since
the last request, so the file grows with the conversation, not with its square.

### 4.2 The task

The trials' prompt, then the moments in scope:

> 이 대국을 분석하고 중요한 장면들을 해설해서 저장해 줘. 다음 장면은 반드시 포함해 줘: {the three fixed moments
> as numbered moves}.
>
> {the PGN}

The agent comments on `game_overview`'s moments as it does today. `rx_moments` may choose a ply ranked past
16, which `game_overview` would not list. Naming the fixed moments makes sure each has a chance of a
commentary, the same in every arm. Train keeps its trial moments (RX0-D §3.1). They are named the same way,
which the trials did not do (Q1).

### 4.3 Arm B's retry

After each `submit_commentary` result with a refused subject, the runner adds one user message: the refused
subject's problems as the server returned them, and "이 장면을 고쳐서 다시 제출해 줘." It does this at most
*N* = 3 times a subject (RX0-D §8). Each such message is a `feedback` line. In arm A the runner adds nothing,
and the agent sees the refusal in the tool result as today.

### 4.4 Slots for C and D

The runner has two hooks that RX1 leaves empty: `lessons(arm) -> str` (appended to the system prompt) and
`critic(run, subject) -> feedback | None` (called after a subject's last accepted submission). RX4 fills
them. RX1 tests that an empty hook changes nothing in a run's messages.

### 4.5 The model

- OpenRouter's chat completions endpoint, as HIMARI calls luna (`openai/gpt-6-luna`, HIMARI's
  `provider/openrouter.py`). Tools are passed as OpenAI-style function tools built from the MCP tool list.
- The key is read from `OPENROUTER_API_KEY`. It is never written to a record, a log or an error message.
- Sampling parameters are the provider's defaults, as HIMARI sends them, and are recorded in `start` (Q2).
- Tokens and cost come from the response's `usage`. A response without cost records tokens only.

## 5. The manifest

`tools/rx/sets_v1.json`, built by `python -m tools.rx manifest`:

- Train: the four fixtures by path (RX0-D §2) and their trial moments;
- Validation: the four games by chess.com number, with `rx_moments`' three plies and the filled slots;
- Test: the four games by number, with **no moments**. Test's moments are chosen only at measurement (RX0-D §2);
- every game: the owner's side, the UCI digest, and the build identity that ranked its moments.

The command reads the PGNs from the data directory (`~/.local/share/calliope/rx/sets/`). For Validation it
analyses every ply (`analyze_game`, warm thereafter) and calls `rx_moments`. It never opens a Test PGN except
to compute its digest.

RX1 also counts Validation's moments by kind of failure (RX0-D §3.2) and reports the counts. A kind that Train
has and Validation lacks is reported, and the replacement is the owner's call.

## 6. `commentary_min_v1`

A copy of `commentary_ko_v8` with its direction removed (RX0-D §8): the task in one line, and the sections 받는
재료, 인용, 표기, 수 전 상황, 판의 변화 and 제출, word for word. `commentary_ko_v8` is not edited (the guide freeze,
RX0-D §8). The server serves `commentary_min_v1` at the same resource and through the `calliope_commentary`
prompt only when started with `--guide commentary_min_v1`, which the runner passes for A-min. Without the flag
the server is unchanged.

## 7. `evidence_identity`

`record.identity(entry)` implements RX0-D §5: the canonical JSON of the kind's list, hashed with SHA-256.
`line_key(fen, pv)` gives the FEN and the first eight PV plies in UCI.

Tests:

- unit: each kind's list from a constructed `Entry`. The facts tree's `rev` and a board item's `bundle` do not
  change the identity. The analysis and search branches of `s` give different identities for the same moves
  and the same `line_key`;
- with Stockfish (`CALLIOPE_STOCKFISH_PATH`, skipped without it, like `test_board_stockfish.py`): two
  sessions with different handle tokens read the same moments of `rapid` through `ply`, `judge_move`,
  `facts` and `explore` (with `search`). Every handle differs. Every `j`, `c`, analysis `s`, search `s`, `b`, `f`
  and `x` identity is equal (RX0-D §5).

## 8. Acceptance

1. **Unchanged when off.** The whole suite passes. A server started without `CALLIOPE_RUN_RECORDS` answers a
   fixed script of calls byte for byte as `main` does.
2. **Whole runs.** Arm A, luna, once on each Train game that has its PGN (all four): every run's two layers
   are whole by RX0-D §4.4's checker (`python -m tools.rx check <run>`). Each run's final commentaries are
   extracted by RX0-D §6.0, and every fixed moment has one or is counted as without one.
3. **Identities.** §7's Stockfish test passes.
4. **The manifest.** Built for Train and Validation. Test has digests only. The Validation counts by kind are
   reported.
5. **Cost.** The acceptance runs' tokens and cost, from the agent layer.

The runs in item 2 are not RX2's baseline. They show that the record works.

## 9. Owner questions

- **Q1 — The fixed moments in the task.** Name the three fixed moments in the prompt (§4.2), in every arm and
  on Train too? Recommended: yes. Without it a special moment past 16 is never commented, and the trials'
  comparability is lost only in wording, since Train's moments are the same plies.
- **Q2 — Sampling.** The provider's defaults as in HIMARI, or a fixed temperature? Recommended: the defaults.
  The trials ran with them, and RX2's spread measures the variation they cause.
- **Q3 — The acceptance runs.** They need `OPENROUTER_API_KEY` on this machine and cost about $0.10.
  Recommended: the owner sets the key in the environment, and the implementation runs them.
