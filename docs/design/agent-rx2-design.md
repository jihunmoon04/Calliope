# Agent RX2-D — the baseline: arm A, A-min and their spread

Status: **design, rev. 3, for independent re-review. Owner questions are in §9. Independent review of rev. 1
(`39670df`): NOT_READY (B1–B3; N1–N3), applied, §10. Owner decision (2026-11-05): the HIMARI arm is out of
RX2. Re-review of rev. 2 (`ae0b752`): NOT_READY (C1, C2; N4, N5), applied, §10.1.** Date: 2026-11-05. Base: `main @ a772669` (RX1 merged, PR #141).
Inputs: [`agent-rx0-design.md`](agent-rx0-design.md) (RX0-D: the evaluation contract), [`agent-rx1-design.md`](agent-rx1-design.md)
and [`agent-rx1-implementation.md`](agent-rx1-implementation.md) (RX1: the runner, the record, the manifest; §5.1 N4),
[`agent-reflection-framing.md`](agent-reflection-framing.md) (§6: RX2's row).

RX2 measures before anything is learned. It runs arm A and the calibration arm A-min on Train and
Validation, judges them once, computes M1–M4, and states each metric's spread and the smallest difference
RX3–RX4 can confirm. Nothing here changes the guide (the freeze, RX0-D §8).

**No HIMARI arm** (owner, 2026-11-05). RX's comparisons (B − A, C − B, D − B) all run inside the Calliope
runner, so none needs HIMARI. What the runner changed against HIMARI is therefore not measured: the guide in
the system prompt, the fixed moments named in the task, and HIMARI's persona, tools and mode rules. The report
says so. If the results hold, the owner may drop HIMARI from the commentary path altogether. A HIMARI
comparison, if one is wanted later, is a packet of its own.

## 1. Scope

| Piece | Where | § |
| --- | --- | --- |
| A request deadline that holds (RX1 review N4) | `tools/rx/model.py`, `tools/rx/request.py` | 2 |
| The build checked before a batch: a `build` line in the record | `agent/record.py`, `agent/session.py`, `tools/rx/manifest.py`, `tools/rx/run.py` | 3 |
| The handles each answer showed the model: `shown` on `call` lines | `agent/record.py` | 7 |
| The references and their key causes | `tools/rx/reference.py`; `tools/rx/references_v1/` | 4 |
| `judge_v1`, the judging directory and its parts | `tools/rx/prompts/judge_v1.md`; `tools/rx/judge.py` | 5 |
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

## 3. The build checked before a batch (reviews N1, C1)

The ply cache's key is the request, the reasoning build's digest, the engine's identity and the analysis
profile (`PlyCache.key(expected_request, digest, port.identity, profile)` in `agent/session.py`). An analysis
made by another build is a cache miss, and its claims have other `evidence_identity`s (RX0-D §5). RX1's
`start` line holds the engine's file name and `agent_build()` without a reasoning build, which cannot tell
two builds apart (re-review C1). RX2 records the build itself:

- **A `build` line.** `Session` hands the recorder, once per engine start, the three parts of the cache key that
  are the build: the engine identity's `fingerprint()`, the profile's `fingerprint()` and the reasoning
  digest (`_engine_build`). The recorder writes them as a `build` line (`call_id` of the call that started the
  engine, or `null`) and their SHA-256 as `build_id`. An engine that restarts writes a new `build` line.
  Nothing in any answer changes.
- **`base.json` gains `build`** (the same three parts and `build_id`). `python -m tools.rx annotate <set>` adds it
  to the sealed bases from a probe session on a copy. It first checks that the probe reads every fixed
  moment's ply from the cache (`cached: true`). A miss means another build, and the command stops.
- **Before the model is called**, the runner reads the resource `calliope://build`, which starts the engine,
  then reads the run's `build` line from `tools.jsonl`. A `build_id` other than `base.json`'s ends the run as
  `error`, with both builds in the agent layer. Every later `build` line in the run is checked the same way
  after the run.
- **The report** counts, per run, the plies the server analysed instead of reading from the cache. Arms A and
  A-min should analyse only what `judge_move` and `explore` ask for, which the base cannot hold.
- **M2a** compares identities only within one `build_id`. A comparison across builds is refused by
  `metrics.py`.
- **Tests:** two synthetic engines with the same file name and different identities (another option or
  version) give different `build_id`s, and the runner refuses the second against a base sealed with the
  first. The `build` line is written once per engine start, after the call that started it.

## 4. References and key causes

### 4.1 The reference (RX0-D §3.3)

`python -m tools.rx reference --set train|validation` builds, for each fixed moment, from the set's base
cache (read on a copy, as RX1's kinds count did):

- the FENs before and after the move; the PGN up to the move;
- the played and the best lines, numbered, and the other candidates with their lines;
- the board items (`changes`, `scene`, structure, file) with their texts, `proves` and since-when;
- the same reply; the claims with their status, `proves` and parts;
- every served item's `evidence_identity`, and each line's `line_key` (RX0-D §5); the build (§3).

The output is one JSON file a moment, `tools/rx/references_v1/<set>/<game>-<ply>.json`, in the repository. Test
gets no reference until measurement (RX0-D §2).

### 4.2 Key causes (RX0-D §3.3, framing Q5)

- **Draft.** A Claude session started for this purpose (a reference session, not a judge) reads each
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

## 5. Judging

### 5.1 The judging directory (review B3)

A new session's fresh context does not keep it from reading files. So the judge works in a directory that
holds only what it may read, and everything else stays out of reach of that directory:

- `python -m tools.rx bundle <runs…>` writes **`judging/<id>/`**, outside the repository
  (`D:/00_프로젝트/rx-judging/<id>/` on this host). It contains only:
  - `bundle.json` (or its parts, §5.3): items `{key, moment, sentences}`, `key` an opaque random 8-hex, no arm,
    model, run id or guide name;
  - the references the items name, copied from `tools/rx/references_v1/`;
  - `judge_v1.md` and `judge_v1.schema.json`.
- **`bundle_key.json`** (`key → {run_id, arm, game, ply, seq}`) and the shuffle's seed go to the RX data
  directory in WSL (`~/.local/share/calliope/rx/judging/<id>/`), beside the run records, never into
  `judging/<id>/`.
- The judge session is started with `judging/<id>/` as its working directory and a brief that tells it to read
  nothing outside it. Its transcript is kept with the judging.
- **The audit.** Before results are joined with the key, `judge.py audit` reads the judge session's transcript
  and lists every path it read or ran a command on. Any path outside `judging/<id>/`, or any command that
  lists or reads the WSL data directory or the repository, voids the judging. A void judging is redone in a
  new directory with a new shuffle.
- Only after the audit passes does `metrics.py` join `judging.json` with `bundle_key.json`.

The isolation is by place and by audit, not by permission: the session runs as the owner (re-review N5).
The audit checks the **tool calls the transcript records**: each file read, search, listing and command, with
its paths and command line. It cannot see a read made inside a command, such as a Python script the judge
writes and runs that opens another path. So the audit also voids a judging whose commands open a path not
named in the command line, such as a script that lists or walks directories, or one whose command line
names a path outside `judging/<id>/`. That is still a check of what is observable, not proof that nothing
else was read. Strong isolation needs a sandbox: a separate user, container or VM that can see only
`judging/<id>/`. RX2 does not use one, and its report says the judging is blind by place and by audit.

### 5.2 `judge_v1`

`judge_v1.md` holds ST-D §0's instructions, extended by RX0-D §6:

- for each sentence: `ok`, `doubtful` or `wrong`, and for `wrong` its kind from RX0-D §6.1's list (or a new
  kind, named), with a one-line reason;
- for each key cause of the moment: `explained`, `partly` or `not` (M2b);
- for each commentary: a score of 1–5 for how concretely it explains the verdict (M4);
- boards and lines are checked with python-chess, against the reference only. The judge's own chess judgement
  is not evidence.

The output is `judging.json` (one a part) in a fixed JSON schema. `metrics.py` refuses an output that does
not validate.

### 5.3 Parts (review N2)

Arm A and A-min give up to 144 commentaries (48 runs × 3 moments). One session may not hold them all with
their references. A judging is one logical unit split into parts:

- a **part** holds every arm's commentaries of the same moments, so each part is balanced across arms: at
  most 6 moments a part (up to 36 commentaries), Train and Validation in separate parts;
- each part is judged by its own fresh session in its own directory, with the same `judge_v1` and schema;
- part assignment and the shuffle within a part are recorded with the key;
- the parts together are the judging. A change to `judge_v1` between parts makes a new judging version, and
  every part is judged again;
- arms are compared within a part's moments first, and the report checks that the arm differences do not
  change sign across parts. Because every part holds every arm, a judge that is stricter in one part shifts
  all arms there alike.

## 6. The runs

| Arm | Sets | Runs a game | Runs | Cost (from RX1) |
| --- | --- | ---: | ---: | ---: |
| A | Train, Validation | 3 | 24 | about $0.50 |
| A-min | Train, Validation | 3 | 24 | about $0.25 (FR §3.4: half of A) |

- Train runs are not compared with Validation. They are the failures RX4's evaluator reads. A-min's Train
  runs are D-min's source (RX0-D §8).
- One batch, arms interleaved by game (A, A-min on game 1, then game 2 …), so a provider's change of behaviour
  over the day falls on both arms alike.
- **The bounds** (RX0-D §8, RX1-D §4.7), with censoring in view (review N3). The batch runs with RX1's
  starting bounds. A run that hits one is **censored**: its count is a lower bound, not its need.
  - If at most 5% of arm A's runs are censored, RX2 sets each bound at the 95th percentile of arm A's runs
    plus 50%, rounded up, and fixes it for every later arm.
  - If more are censored, the censored runs are run again with that bound doubled. The bounds are then set
    from the second batch the same way. Both batches are reported.
  - Censored runs are counted in their arm in every case (RX0-D §4.4).
  - **The comparison keeps one budget** (re-review N4). The second batch only measures the bounds. RX2's
    report compares A and A-min on the first batch, where both ran under the same starting bounds, with
    their censoring shown. If the bounds change, arms A and A-min are run again under the fixed bounds before
    RX3, and that run is the baseline B is compared with. A baseline is always run under the bounds of the
    arm it is compared with.

## 7. Metrics and the report

`tools/rx/metrics.py` computes, from the records, the bundle key and the audited judging:

- **M1a** by RX0-D §6.1, with the classes RX1 met: `subject` is a form refusal; a problem with no `rule` (a
  proposition that does not verify) is a fact refusal; `size` is a form refusal.
- **M1b, M1c** from the judging.
- **M2a** with `covered` (RX1's `check.py`), within one build (§3). **M2b** from the judging.
- **M3** by RX0-D §6.3. **Available** is what the model was shown, not what the session served (re-review
  C2). A session serves handles before it bounds its answer, the digest's steps move items behind `detail`
  (`agent/digest.py`), and a call can still fail after serving. So each `call` line gains **`shown`**: every
  handle ref that occurs in the answer the model received, found by the handle pattern in the answer's text.
  It is written whether or not the answer is capped, and is empty for a call that ended in an error. An item
  is Available at a moment when its identity (or `line_key`) belongs to a ref in `shown` of a successful call
  before the moment's last accepted submission. A ref named only in `not_shown` counts as shown: the model
  saw it and could read it with `detail`. Used, direct comes from the final commentary's cites and `detail`
  calls; Used, related from `explore` and `judge_move` calls by RX0-D §6.3's rules; then P1 and P2.
  **Tests:** a call whose answer errs after serving handles gives an empty `shown`; a digest that moved an
  item behind `detail` lists its ref in `shown` only if the ref is in the text; a capped answer keeps
  `shown`.
- **M4** from the judging.

The report (`agent-rx2-implementation.md`) gives, per arm and set:

- every metric's mean, its spread between runs of a game and between games, and its 90% interval by a
  bootstrap over games, then runs, then moments (RX0-D §7.1);
- the smallest difference each metric can confirm at three runs and four games, and, where it is larger
  than RX0-D §7.1's sizes, the runs or games that would be needed;
- A against A-min: the known gap that D-min must recover in RX4;
- the arm differences by judging part (§5.3);
- the bounds and their censoring (§6), the plies analysed outside the base (§3), the cost, the moments left
  without commentary;
- what is not measured: the HIMARI path (§0).

**Done when** the report is reviewed and the owner accepts the baseline. Nothing is promoted in RX2.

## 8. What RX2 does not do

No HIMARI arm, no retry (RX3), no critic, no lessons, no guide change. Test is not opened.

## 9. Owner questions

- **Q1 — Reviewing 24 moments' key causes.** **Answered as recommended (2026-11-05): all 24.** This is the owner's largest task in RX2: about four causes a
  moment, each a sentence and its items. Recommended: review all 24. If that is too much, review Validation's 12
  first; Train's M2 then waits, and RX2 reports Validation's baseline only.
- **Q2 — Judging by fresh sessions.** **Answered as recommended (2026-11-05).** Start each part's judge as a fresh Claude Code session from this app, in
  its judging directory (§5.1)? Recommended: yes. The alternative is the owner starting each by hand with the
  same brief.

## 10. Review dispositions — rev. 1 (`39670df`), independent review: NOT_READY

| Item | Finding | Disposition |
| --- | --- | --- |
| B1 | HIMARI starts a listing process and a conversation process; one `CALLIOPE_RUN_ID` would give two `start`s and two `seq` runs in one record | Moot: the HIMARI arm is out of RX2 (owner, 2026-11-05). A later HIMARI packet must give each MCP process its own record id and say which one is the run's |
| B2 | HIMARI's data root, conversations, memory and MCP settings (`read_only`, allowed tools, timeouts, process sharing) are not isolated or recorded per run | Moot for the same reason; the later packet's contract |
| B3 | A fresh session is not a file-access boundary; the judge could read `bundle_key.json` or the records | Applied: §5.1, a judging directory outside the repository with only the bundle, its references and `judge_v1`; the key and the records in the WSL data directory; the judge started in that directory; an audit of its transcript before any join, a void judging redone |
| N1 | Another engine build gives cache misses and other identities | Applied: §3, the build in `base.json` (checked by a probe that every fixed moment is a cache hit), each run's build checked against it, analyses outside the base counted, M2a within one build |
| N2 | Up to 180 commentaries are more than one judge session can hold | Applied: §5.3, parts of at most 6 moments holding every arm, each judged by its own session with the same `judge_v1`; differences checked across parts. (Without HIMARI: up to 144 commentaries) |
| N3 | Runs that hit a bound understate the need | Applied: §6, censored runs; bounds from the 95th percentile plus 50% only if at most 5% are censored, else a second batch with doubled bounds for those runs |

### 10.1 Re-review of rev. 2 (`ae0b752`): NOT_READY

B1 and B2 were found moot with the HIMARI arm out. B3 and N1–N3 were found resolved or improved.

| Item | Finding | Disposition |
| --- | --- | --- |
| C1 | The server's `start` line has the engine's file name and `agent_build()` with no reasoning build, so it cannot show the build | Confirmed in `tools/mcp/__main__.py` and `agent/session.py` (the cache key is the request, the digest, `port.identity` and the profile). Applied: §3, a `build` line per engine start with the identity's and the profile's fingerprints and the reasoning digest; `build_id`; the runner reads `calliope://build` and checks the `build` line before the model is called; a test with two engines of one file name |
| C2 | Available from `handle` lines counts what was served, not what the model saw | Confirmed: the digest moves items behind `detail` after handles are served (`agent/digest.py`). Applied: §7, `shown` on every `call` line (the refs in the answer's text, kept when capped, empty on an error); Available from `shown` of successful calls; tests for an erring call, a moved item and a capped answer |
| N4 | A second batch with doubled bounds would compare A and A-min under different budgets | Applied: §6, the second batch only measures bounds; RX2 compares on the first batch; a changed bound means A and A-min run again under it before RX3 |
| N5 | A transcript audit cannot prove that no file was read | Applied: §5.1, the audit is of the tool calls the transcript records, voids commands that walk or name outside paths, and is said to be a check of what is observable; strong isolation would need a sandbox, which RX2 does not use |

## 11. Amendments from the implementation (2026-11-05)

- **A1 — the task names the game by its id.** Batch `rx2-1`: in 22 of 48 runs (21 of Validation's 24) the agent
  passed `open_game` a PGN it had retyped without its headers (ratings, time control). That is another game
  key: the server analysed the whole game again (50–145 plies a run), the grading can differ (it reads the
  ratings), and no `evidence_identity` of those runs can match a reference (the identity holds the game key,
  RX0-D §5). The runner's task now says the game is already open and gives its id (the manifest's
  `game_id`, resolvable from the base's records without `open_game`), with the fixed moments, and no PGN.
  It amends RX1-D §4.2's task. Both arms get it. `rx2-1` is kept as the record of the fault; the baseline is
  batch `rx2-2`, run with A1.
- **A1b — an exception group is logged by its errors.** Three of `rx2-1`'s arm A runs ended `error` during a
  model request, logged only as "unhandled errors in a TaskGroup". The runner now logs each inner error and
  ends a run whose inner error is a timeout as `timeout`.
- **A2 — key causes are causal chains, one decisive** (owner's review, 2026-11-05). The first drafts were true
  but many were observations that stopped at a fact ("both are attacked", "the attack continues") without
  what it leads to. A key cause is now a chain: the move → the opponent's concrete reply or line → an outcome
  (material with its count, mate, or that nothing is won). Each moment has exactly one `decisive` cause (the
  reason for the grade, as a commentator would say first) and at most two `supporting` causes. Each cause
  has a `route`: `in_digest` (its evidence is in what `ply` shows) or `on_request` (it needs a call the agent
  must make: `explore` of a line such as the game's real continuation, or `facts` with `exchange` for
  whether a piece can be won). An `on_request` cause's request is run through Calliope and its outcome
  checked before the owner reviews it. M2b's headline is the share of decisive causes explained; supporting
  causes are reported apart. M2a and M3 match an `on_request` cause by the call that gets its evidence: an
  `x` handle whose `from` is the request's position and whose moves begin with the request's first two
  moves, or an `f` handle of the request's position and family.
- **A3 — what the commentary is aimed at.** Three levels (owner's review): (1) the decisive cause carried to
  its outcome from what the digest shows; (2) evidence the agent must go and get when the engine's line does
  not show the reason (the game's continuation, other lines, whether a piece can be won) — the agents of
  every trial so far never called `explore`, so this is what RX's critic and lessons are for; (3) positional
  reasons (open files, diagonals, piece activity), for which Calliope gives few verified facts. Level 3 is
  out of RX's target: a key cause is never positional, and such sentences can only be interpretations. It
  needs a facts packet first.

