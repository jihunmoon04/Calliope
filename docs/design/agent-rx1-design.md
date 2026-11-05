# Agent RX1-D — the Calliope-run agent and its run record

Status: **design, rev. 2, for independent re-review. Owner questions are in §9. Independent review of rev. 1
(`bf78cbb`): NOT_READY (B1–B3; N1, N2), applied, §10.** Date: 2026-11-05.
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
| The tools layer: `call`, `handle`, `submission`, `start`, `end` lines | `calliope.agent`, a new module `record.py`, hooked at each MCP tool's entry and exit in `server.py`, and in `session.py` for handles and submissions | only the server sees tool calls, handle bindings and check outcomes |
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
- **One `call` line per MCP tool call** (review B1). `run` in `build_server` is not the boundary: it runs a
  session method under the tool lock, so `analyze_game` passes through it twice (`analyze_start`,
  `analyze_answer`) and `definitions` never. The recorder wraps **each registered tool function** instead: a
  decorator `recorded(name)` applied in `build_server` to every `@server.tool` function, and to the resource
  and prompt reads (`calliope://guides/…`, `calliope_commentary`), named `resource:<uri>` and `prompt:<name>`.
  `run` stays the session's executor and records nothing. A test lists the server's registered tools and
  checks that each is wrapped once.
- **The call's events stay with it** (review B2). On entry the decorator opens a call context: a `call_id`
  (from 1 within the run), held in a `contextvars.ContextVar`. `Session._serve` and `submit_commentary` do not
  write lines. They hand their events (each new handle's entry; each subject's outcome) to the open context,
  which buffers them. On exit, after an answer or an error, the decorator writes, in order:
  1. the `call` line: `call_id`, `tool`, `arguments`, `ms`, the answer or the error;
  2. the buffered `handle` lines, each with `call_id`;
  3. the buffered `submission` line, if any, with `call_id`.

  An error does not lose the buffer: handles served before the error are written after the `call` line that
  carries the error. An event with no open context (a job's worker thread, `analyze_game` waiting outside the
  lock) is written at once with `call_id: null`. RX0-D §4.2's order ("a `handle` line follows the `call` that
  served it") then holds by construction, and `call_id` links every event to its call.
- **`handle` lines** carry the entry's `ref`, `kind`, `game`, `source`, `address` and `identity`, for refs that
  `Handles.fresh` counted as new. A ref served again writes nothing.
- **`submission` lines** carry, for each subject, the outcome of `_commentary` (`accepted`, `duplicate`,
  `refused`, `not_stored`), the stored `id`, the sentences with their `cites`, and every problem with its
  `rule` (RX0-D §4.2).
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

1. draw a run id; make the run's data directory (§4.6); start `python -m tools.mcp` on it as a child process
   with `CALLIOPE_RUN_ID` and `CALLIOPE_RUN_RECORDS`;
2. connect with the MCP SDK's stdio client; read the server's instructions and its tools;
3. check the game's PGN against the manifest's digest (RX0-D §2). A mismatch stops the run;
4. build the system prompt: the server's instructions, then the guide as the server serves it (the resource
   `calliope://guides/commentary_ko`, `commentary_ko_v8`; `commentary_min_v1` for A-min), then the arm's
   lessons (D, D-min; none in RX1). In HIMARI the agent reads that resource itself when the instructions tell
   it to. The runner puts it in the system prompt so that every run has read it (FR's `min0`: six of eight runs
   skipped a guide they were not told to read). RX2 reports this difference with the HIMARI comparison;
5. send the task (§4.2) and loop: model request → tool calls through MCP → results back → next request;
6. end at the model's final answer or at a bound (turns, tool calls, tokens, time: §4.7); write `end`; close
   the server; check the base cache (§4.6).

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

### 4.6 One starting cache for every run (review B3)

The ply cache is not read-only: `Session._load_or_analyse` writes every analysis it makes (`cache.put` in
`server/cache.py`), for instance a `judge_move` of a move no earlier run judged. A shared cache would carry one
arm's work into the next arm's time and budget. So:

- **The base cache** of a set is built once, by `python -m tools.rx manifest` (§5): every ply of each game
  analysed (`analyze_game`), on the build the runs use. Its files' SHA-256 digests are written to
  `base.json` beside it, and its files are made read-only.
- **Each run copies it.** Step 1 copies the base cache into the run's own data directory. The run reads and
  writes only its copy. Its commentary store starts empty too, so no run sees another run's commentary, and a
  `duplicate` can only repeat the run's own submission.
- **After each run** the runner checks the base cache against `base.json`. A change stops the batch and is
  reported.
- The process's own stores (PF1's result store and POSITION records) are in memory and start empty with each
  server process.

Every arm therefore starts from the same cache. Their analysis costs differ only by what each run asks.

### 4.7 Time bounds (review N2)

- **Each model request**: 120 s. A request past it is retried once, then the run ends with `reason: timeout`.
- **Each tool call**: 600 s, the longest `analyze_game` wait the runner asks for plus a margin. Past it the
  run ends with `reason: timeout`.
- **The whole run**: 30 min of wall-clock time. Past it the run ends with `reason: wall_clock`.

A run ended by a time bound keeps its lines, ends with its reason, and is counted in its arm like any run
that hits a bound (RX0-D §4.4, §8). RX2 revises the values from arm A's runs, as for the other bounds.

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

1. **Unchanged when off** (review N1). The whole suite passes. A fixed script of calls runs against `main`'s
   server and against RX1's server without `CALLIOPE_RUN_RECORDS`. The answers are compared after replacing
   what differs between processes by design: each handle's token (`<prefix><n>.<token>` → `<prefix><n>.T`),
   budget `left` values and times. Everything else must be equal. A second test runs the same script in one
   process with recording on and off and compares the session's answers the same way, so recording changes no
   answer.
2. **Whole runs.** Arm A, luna, once on each Train game that has its PGN (all four): every run's two layers
   are whole by RX0-D §4.4's checker (`python -m tools.rx check <run>`). Every MCP call in the agent layer has
   exactly one `call` line with the same tool, and every `handle` and `submission` line has the `call_id` of
   the call that produced it. The base cache is unchanged after the runs. Each run's final commentaries are
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

## 10. Review dispositions — rev. 1 (`bf78cbb`), independent review: NOT_READY

| Item | Finding | Disposition |
| --- | --- | --- |
| B1 | `run` in `build_server` is not the MCP tool boundary: `analyze_game` passes through it twice, `definitions` never | Confirmed in `agent/server.py`. Applied: §2, a `recorded(name)` decorator on every registered tool function and on resource and prompt reads; `run` records nothing; a test checks each tool is wrapped once |
| B2 | `handle` and `submission` lines written inside the call would come before its `call` line | Applied: §2, a call context with `call_id`; handles and submissions are buffered and written after the `call` line, with `call_id`; kept on error; events outside a call written with `call_id: null` |
| B3 | A shared ply cache takes new analyses (`cache.put`), so one arm's work warms the next | Confirmed in `agent/session.py` (`_analyse_held` → `cache.put`). Applied: §4.6, a read-only base cache with digests, copied into each run's data directory with an empty commentary store, checked after each run |
| N1 | A byte-for-byte comparison fails on handle tokens | Applied: §8 item 1, tokens, budget values and times normalised; a second test compares recording on and off in one process |
| N2 | No time bounds: a hung request or tool call stalls a batch | Applied: §4.7, 120 s a model request (one retry), 600 s a tool call, 30 min a run; `timeout` and `wall_clock` reasons; such runs counted |
