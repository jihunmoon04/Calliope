# Agent RX2-D — the baseline: arm A, its spread, and the HIMARI comparison

Status: **design, rev. 1, for independent review. Owner questions are in §9.** Date: 2026-11-05.
Base: `main @ a772669` (RX1 merged, PR #141).
Inputs: [`agent-rx0-design.md`](agent-rx0-design.md) (RX0-D: the evaluation contract), [`agent-rx1-design.md`](agent-rx1-design.md)
and [`agent-rx1-implementation.md`](agent-rx1-implementation.md) (RX1: the runner, the record, the manifest; §5.1 N4),
[`agent-reflection-framing.md`](agent-reflection-framing.md) (§6: RX2's row).

RX2 measures before anything is learned. It runs arm A and the calibration arm A-min on Train and
Validation, judges them once, computes M1–M4, and states each metric's spread and the smallest difference
RX3–RX4 can confirm. It also runs the HIMARI path on Validation, to show what leaving HIMARI changed.
Nothing here changes the guide (the freeze, RX0-D §8).

## 1. Scope

| Piece | Where | §  |
| --- | --- | --- |
| A request deadline that holds (RX1 review N4) | `tools/rx/model.py`, `tools/rx/request.py` | 2 |
| The references and their key causes | `tools/rx/reference.py`; `tools/rx/references_v1/` | 3 |
| `judge_v1` and the judging bundle | `tools/rx/prompts/judge_v1.md`; `tools/rx/judge.py` | 4 |
| The HIMARI arm | `tools/rx/himari.py` | 5 |
| The runs | `python -m tools.rx run`, a batch file | 6 |
| M1–M4, the spread and the report | `tools/rx/metrics.py`; `agent-rx2-implementation.md` | 7 |

## 2. A request deadline that holds

RX1's `_read_by` checks its deadline between reads, and a buffered read can block past it. `abandon_on_cancel`
frees the run, not the thread (RX1 implementation §5.1, N4). Before batches run, each model request runs in a
**child process**:

- `tools/rx/request.py` reads the request body from stdin, sends it with `urllib`, and writes the response body
  (or an error line) to stdout. The key reaches it through the environment, never through arguments or stdin.
- `OpenRouter.complete` starts it with `subprocess.Popen`, writes the body, and waits with
  `communicate(timeout=…)`. At the deadline it kills the child (`kill`, then `wait`) and raises
  `ModelTimeout`. The kill ends the socket with the process, so no thread or connection outlives the deadline.
- The retry stays as in RX1 (one retry on a timeout).
- Tests: a local HTTP server that sends one byte every 100 ms is cut at a 0.5 s deadline, and the child is gone
  (`poll()` is not None) within 1 s. A whole body within the deadline is returned unchanged. The key never
  appears in the child's arguments.

## 3. References and key causes

### 3.1 The reference (RX0-D §3.3)

`python -m tools.rx reference --set train|validation` builds, for each fixed moment, from the set's base
cache (read on a copy, as RX1's kinds count did):

- the FENs before and after the move; the PGN up to the move;
- the played and the best lines, numbered, and the other candidates with their lines;
- the board items (`changes`, `scene`, structure, file) with their texts, `proves` and since-when;
- the same reply; the claims with their status, `proves` and parts;
- every served item's `evidence_identity`, and each line's `line_key` (RX0-D §5).

The output is one JSON file a moment, `tools/rx/references_v1/<set>/<game>-<ply>.json`, in the repository. Test
gets no reference until measurement (RX0-D §2).

### 3.2 Key causes (RX0-D §3.3, framing Q5)

- **Draft.** A Claude session started for this purpose (a reference session, not the judge's) reads each
  reference and drafts at most four key causes a moment. Each cause has:
  - a sentence in Korean;
  - the items that hold it, by `identity` (or `line_key` for a line);
  - `kind`: one of `material`, `threat`, `defence`, `line`, `structure`, `other`.

  It writes them into the reference file under `key_causes`, with `status: "draft"`.
- **Review.** The owner reads the 24 moments' drafts (Train 12, Validation 12) and edits, removes or adds
  causes. Each moment then gets `status: "reviewed"` and the reviewer's date. A moment with no reviewed causes
  is left out of M2 and M3, and the report counts it.
- **Frozen.** Reviewed references are committed. Any later change is a `references_v2` and starts a new
  judging (RX0-D §7.2).

## 4. Judging

### 4.1 The bundle

`python -m tools.rx bundle <runs…>` collects, for each run's fixed moments, the **final commentary** (RX0-D
§6.0). It shuffles them over all arms with a recorded seed and writes:

- `bundle.json`: items `{key, moment, sentences}`. `key` is opaque (a random 8-hex), and the moment names the
  reference file. No arm, model, run id or guide name;
- `bundle_key.json`: `key → {run_id, arm, game, ply, seq}`. It stays outside what the judge is given.

A moment-run with no final commentary is not in the bundle. Its absence is counted from the records
(RX0-D §6.0).

### 4.2 `judge_v1`

`tools/rx/prompts/judge_v1.md` holds ST-D §0's instructions, extended by RX0-D §6:

- for each sentence: `ok`, `doubtful` or `wrong`, and for `wrong` its kind from RX0-D §6.1's list (or a new
  kind, named), with a one-line reason;
- for each key cause of the moment: `explained`, `partly` or `not` (M2b);
- for each commentary: a score of 1–5 for how concretely it explains the verdict (M4);
- boards and lines are checked with python-chess, against the reference only. The judge's own chess judgement
  is not evidence.

The output is `judging.json` in a fixed JSON schema (`tools/rx/prompts/judge_v1.schema.json`). `metrics.py`
refuses an output that does not validate.

### 4.3 Who judges

There is no Claude CLI on this host, so `claude -p` cannot run here. A judging is a **fresh Claude Code
session** that the working session starts (the app's `start_session`, context `fresh`) with a brief that names
the files: `judge_v1.md`, its schema, `bundle.json` and the reference files. It has no access to `bundle_key.json`,
the run records or this conversation. It writes `judging.json` and ends. Its transcript is kept with the
comparison. One judging covers every arm compared (RX0-D §7.2).

## 5. The HIMARI arm

RX2 compares the runner (arm A) with HIMARI on Validation, on the tools layer (RX0-D §4.4).

- `tools/rx/himari.py` drives HIMARI v3 through its CLI (`himari new`, `himari send ID -`). Per run it:
  1. copies the set's base cache, as the runner does (RX1-D §4.6);
  2. writes HIMARI's MCP configuration for the Calliope server: `python -m tools.mcp --data <copy>`, with
     `CALLIOPE_RUN_RECORDS` and a fresh `CALLIOPE_RUN_ID`;
  3. starts HIMARI's web server on that configuration, so the Calliope server is a new process for this run;
  4. sends the same task as the runner (RX1-D §4.2: the trials' prompt, the fixed moments, the PGN) in a new
     conversation, waits for the answer, and saves the transcript HIMARI shows;
  5. stops HIMARI, checks the base cache, removes the copy.
- Model: luna, as the trials. HIMARI's reasoning setting as the trials ran it (§9 Q2).
- Its tools layer is whole when it has `start` and `end` and no gap (RX0-D §4.4). Its report says what it cannot
  show: prompts, tokens and cost.
- HIMARI's commentaries go into the same bundle as arm A's and A-min's, so one judging covers all three.

## 6. The runs

| Arm | Sets | Runs a game | Runs | Cost (from RX1) |
| --- | --- | ---: | ---: | ---: |
| A | Train, Validation | 3 | 24 | about $0.50 |
| A-min | Train, Validation | 3 | 24 | about $0.25 (FR §3.4: half of A) |
| HIMARI | Validation | 3 | 12 | about $0.25 |

- Train runs are not compared with Validation. They are the failures RX4's evaluator reads. A-min's Train
  runs are D-min's source (RX0-D §8).
- One batch, arms interleaved by game (A, A-min, HIMARI on game 1, then game 2 …), so a provider's change of
  behaviour over the day falls on all arms alike.
- **The bounds** (RX0-D §8, RX1-D §4.7). After the batch, RX2 sets turns, tool calls, tokens and the time
  bounds at the 95th percentile of arm A's runs plus 50%, rounded up. They are fixed for every later arm. The
  batch itself runs with RX1's starting bounds. A run that hit one is reported.

## 7. Metrics and the report

`tools/rx/metrics.py` computes, from the records, the bundle key and `judging.json`:

- **M1a** by RX0-D §6.1, with the classes RX1 met: `subject` is a form refusal; a problem with no `rule` (a
  proposition that does not verify) is a fact refusal; `size` is a form refusal.
- **M1b, M1c** from the judging.
- **M2a** with `covered` (RX1's `check.py`), **M2b** from the judging.
- **M3** by RX0-D §6.3: Available from the `handle` lines before the moment's last accepted submission; Used,
  direct from the final commentary's cites and `detail` calls; Used, related from `explore` and `judge_move`
  calls by RX0-D §6.3's rules; P1 and P2.
- **M4** from the judging.

The report (`agent-rx2-implementation.md`) gives, per arm and set:

- every metric's mean, its spread between runs of a game and between games, and its 90% interval by a
  bootstrap over games, then runs, then moments (RX0-D §7.1);
- the smallest difference each metric can confirm at three runs and four games, and, where it is larger
  than RX0-D §7.1's sizes, the runs or games that would be needed;
- A against HIMARI on the tools layer's metrics (M1a, M1b, M1c, M2, M3, M4 of their commentaries), and what
  only one of them shows;
- A against A-min: the known gap that D-min must recover in RX4;
- the bounds fixed (§6), the cost, and the moments left without commentary.

**Done when** the report is reviewed and the owner accepts the baseline. Nothing is promoted in RX2.

## 8. What RX2 does not do

No retry (RX3), no critic, no lessons, no guide change. Test is not opened.

## 9. Owner questions

- **Q1 — The HIMARI arm.** Run it (§5, about $0.25 and a harness of its own), or leave the HIMARI comparison
  out? Recommended: run it on Validation only. Leaving HIMARI is RX's premise, and RX2 is the one place it can
  be measured before anything else changes.
- **Q2 — HIMARI's reasoning setting.** Did the trials set `HIMARI_REASONING_EFFORT`? Recommended: run HIMARI as
  the trials ran, and the runner with the same value. If the trials did not set it, neither does RX2.
- **Q3 — Reviewing 24 moments' key causes.** This is the owner's largest task in RX2: about four causes a
  moment, each a sentence and its items. Recommended: review all 24. If that is too much, review Validation's 12
  first; Train's M2 then waits, and RX2 reports Validation's baseline only.
- **Q4 — Judging by a fresh session.** Start the judge as a fresh Claude Code session from this app (§4.3)?
  Recommended: yes. The alternative is the owner starting it by hand with the same brief.
