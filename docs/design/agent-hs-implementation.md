# Agent HS — the staged harness as arm H of the RX runner

Status: rev. 4; the measurement (§8) found two faults of the stage loop, fixed here (§9) for review;
rev. 3 merged by the owner (PR #152); rev. 4 merged by the owner (PR #153, 2026-11-08). Implements `agent-hs-design.md` rev. 3 (merged, PR #151).
The measurement of §6 runs after this review (§5).

## 1. What changed

| File | Change |
| --- | --- |
| `tools/rx/harness.py` (new) | Re-review R2: no judge request at or past the token bound, and no re-ask past what is left. Review F1: the gate holds a submit whose `game` (the call's, or an item's) is not the run's. Review F2: the judge's tokens are added to the run's input and output tokens (the token bound counts them), its share kept in `judge_tokens`; the turn bound counts the agent's requests only. Review N1: the judge request is abandoned at the run's bound. Arm H: `harness_loop` drives each fixed moment, in game order, through the stages on `run._loop` (facts and the decisive cause in one turn → the judge → at most two retries → submit); `Gate` (`(phase, current_ply)`, review B2): `submit_commentary` reaches the server only at the current moment's submit step and only when every subject — `ply`, `position` and `move`, each of `items` — is that moment, else the runner answers and writes `tool_unsent` (`reason: "harness_gate"`, the call's id, phase, subjects); `judge` (one request on the run's model, no tools; asked again once when its answer is not the JSON; never blocking); `subject_ply`, `subjects_of`. |
| `tools/rx/prompts/harness_v1.md`, `harness_judge_v1.md` (new) | The runner's messages (task, facts, retry, submit, gate) and the judge's rubric v2, as the pilot's, facts and cause joined. |
| `tools/rx/run.py` | `ARMS` adds H (`HARNESS_ARMS`); H's task from `harness_v1.md`, its loop `harness_loop` with a judge model (the run's model, no cache marks, the run's `session_id`); the `start` line names `harness_v1`, `harness_judge_v1` and the retries; `_loop` sets `next_call_id` on a session that has it, so the gate can log the call it holds. Arm A's messages and loop are unchanged. |
| `tools/rx/request.py`, `tools/rx/model.py` | Review N2: the child answers a body cut short or a dropped connection (`http.client.HTTPException`, `ConnectionError`) as `{"error", "kind": "transport"}`; the parent raises `ModelTransient`, which `complete` retries once, as a timeout. |
| `tools/rx/report.py` | Re-review R1: `worst_case` counts every failed run (no result, or not judged) at its game's fixed moments from the manifest; `failed` serves it and `ledger`. Review C1: for a pair spanning both sets, `H − A / pooled` — the same estimator and bootstrap over every set's games, a game keyed by `(set, game)`; `paired(cells, None, …)` pools. Review F3: `ledger` (per arm, every started run: judged, failed, how each ended), `H − A / pooled, worst case` (every run not judged counted, its moments without commentary and their decisive causes unexplained), `quality_gate` (the pooled M2b +0.10 with its interval above zero, no set's M2b below −0.10, the pooled M1b's upper bound at most +2.0) and `decision`: `adopted` only with the gate passed, no more failed runs and no more moment-runs without commentary than A, and the worst case meeting the M2b bar; `quality_gate_passed` and `sets_disagree` beside it. |
| `tests/agent/test_hs.py` (new) | 20 tests (§3). |

## 2. Amendments

- **A1 — the judge's header is the numbered move.** HS-D §3 gave the judge the moment's grade and the
  played and best moves' scores, from the digest. The runner has no way to them that leaves the
  record as it is: a `ply` call would be recorded as the agent's (in `tools.jsonl`, counted in M3),
  and the references, which hold them, also hold the key causes the judge must never see. The header
  is `장면: <numbered move>`; the grade and the scores come from the agent's own reply, as its facts
  state them (rubric v2's fourth check reads whether the reply compares with the best move, which
  the reply names). The pilots' judges had the digest header.
- **Bounds** are not changed in code: the comparison names them per batch with the runner's flags
  (`--turns 90 --tool-calls 150 --tokens 4000000`, HS-D §4), for A and H alike.

## 3. Tests

`tests/agent/test_hs.py`, 20 tests, no network and no engine:

- **Transport (N2):** the real child (`python -m tools.rx.request`) against a local HTTP server that
  promises a 64-byte chunk and closes after 23: `ModelTransient`, "cut short"; `complete` retries
  once and returns the second answer, and raises after two.
- **The gate (B2):** in `facts` a submit is held, with its `tool_unsent` line (the call's id, the
  phase, the subjects); in `submit` the current ply passes by `ply`, by `position` and `move` and in
  `items`; another ply, an `items` holding an unjudged ply, an empty or malformed `items`, a
  variation, and a position-and-move that is not the played move are held.
- **The stages, on a scripted model and judge through the runner's `_loop`:** a moment passed at once
  goes to submit; the first `request` line logs the system message and the task (§4); the judge's
  request is its rubric, the header and the reply, nothing else (§3); its cost in the run's totals
  and `judge_cost`. A failed verdict sends its problems back, the next reply is judged; three
  failures go to submit with the runner saying so; an unreadable verdict is asked again once and
  never blocks; a submit in the facts phase is held and logged with its call id.
- **Arm A** has no harness fields, H records its versions; the task of A is as before.
- **Review F1:** a submit naming another game — by the call's `game`, an item's `game`, or no game — is
  held at the submit step of the current ply.
- **Review F2:** a judge answer of 500 tokens on a 400-token bound ends the run at `tokens` before the
  submit step; the run's input tokens hold the agent's 10 and the judge's 500, `judge_tokens` 500.
- **Review N1:** a judge that answers after 5 s, under a 0.5 s run bound: `TimeoutError` in under 3 s.
- **Re-review R1:** A fails once with a log, H once with no result at all; both count in the worst
  case at every fixed moment of their game (from the manifest), unexplained; the judged cells are
  left as they were; the ledger has one failure each.
- **Re-review R2:** the agent's reply reaches the bound: no judge request, the run ends at `tokens`;
  a judge's unreadable first answer that uses the rest is not asked again (`budget: true`).
- **The pooled report (C1):** one set pools to its own value; a game name in two sets is two games;
  the decision: pool met and both sets up (adopted), one set at −0.15 (not), the pool short with a
  set up by 0.3 (not), M1b's bound at 2.5 (not). **Review F3:** with the quality gate passed, H with
  five failed runs against none, with more moment-runs without commentary, or with a worst case short
  of the bar is not adopted (`quality_gate_passed` true, `adopted` false); the ledger counts every
  started run (judged, failed, how each ended, a row without a result).

## 4. The whole suite

WSL, rev. 3's code: **1951 passed, 27 skipped**; 3 failed and 2 errors, all known (the digest golden
on the Windows engine build; the four `zstd` tests, RX1 §3). `ruff check` clean. (rev. 2: 1948
passed; rev. 1: 1943, the same known failures.)

## 5. The measurement (HS-D §6), after review

Arms A and H on the evaluation sample (Train's four games, Validation 185371835722 and
185922072242), three runs a game each, on the shared bounds:

```
python -m tools.rx.batch --name hs-eval-1 --env-file .env --arms A H --sets train validation \
  --games hung rapid fresh fourth 185371835722 185922072242 --runs 3 --workers 3 \
  --turns 90 --tool-calls 150 --tokens 4000000
```

Every started run, its end and cost, reported (N1); failures rerun once; one judging of both arms,
blind and audited; the report's `H − A / pooled` and its decision, the per-set entries, and the worst
case computed from the batches. Expected cost on OpenRouter: about $5 (36 runs).

## 6. Questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Accept A1 (the judge's header is the move only)? | Yes: anything more would come through the references or a recorded call. |
| Q2 | Run §5 after this review? | Yes. |

## 7. Review (rev. 1 → rev. 2)

Independent review of `a6d3319`: NOT_READY.

| # | Finding | Disposition |
| --- | --- | --- |
| F1 (P1) | The gate checked the ply, not the game: the same ply of another game passed | Applied: `Gate` holds the run's game id; the call's `game` and every item's must be it; tests for a call, an item and a call naming none. |
| F2 (P1) | The judge's tokens were outside the token bound | Applied: added to the run's input and output tokens, which `_loop`'s bound reads; `judge_tokens` kept as the judge's share; the turn bound defined as the agent's requests. Test: a judge answer that passes the bound ends the run before the submit step. |
| F3 (P1) | `adopted` could be true with failed runs, missing commentary or a worst case short of the bar | Applied: `decision` takes the ledger, the moment-runs without commentary and the worst-case pooled entry; `quality_gate_passed` reports the quality part alone. Tests for each. |
| N1 (P2) | The judge request was not abandoned at the run's bound | Applied: `abandon_on_cancel=True`, as the agent's; test with a 5 s judge under a 0.5 s bound. |

Re-review of `451a947`: NOT_READY (F1, F2, N1 resolved; F3 in part).

| # | Finding | Disposition |
| --- | --- | --- |
| R1 (P1) | The worst case skipped a failed run without a result or an `agent.jsonl`, which the ledger counted | Applied: `worst_case` (a function now) takes the fixed moments of every failed run from the manifest by `(set, game)`, whatever the run left; `failed` is one definition for it and `ledger`. Test: one failure each, H's without a result. |
| R2 (P2) | A judge request could start after the agent's reply used the token budget | Applied: the harness checks the bound before the judge request; `judge` takes the tokens left and does not re-ask past them. Tests for both. |

## 8. The measurement (HS-D §6)

**Runs** (`rx-evidence/hs/batch-hs-eval-1.jsonl`): arms A and H on the evaluation sample (Train's
four games; Validation 185371835722 and 185922072242), three runs a game each, on the shared bounds
(90 turns, 150 tool calls, 4M tokens). **36 started, 36 `done`, none failed** (the ledger); none
rerun. Cost: A $2.77 ($0.154 a run), H $1.85 ($0.103 a run).

**Judging `4066c0df`:** 104 commentaries in three parts, fresh sessions, `judge_v1`; all three audits
passed. Report (`rx-evidence/hs/report.json`, `--pair H A`, 90%):

| | A | H | H − A |
| --- | --- | --- | --- |
| **M2b, pooled (17 moments)** | | | **+0.157 (−0.093 … +0.431)** |
| M2b, Train (11) | 0.64 | **0.94** | +0.303 (0.000 … +0.611) |
| M2b, Validation (6) | 0.78 | 0.67 | −0.111 (−0.333 … +0.167) |
| M1b, pooled (18) | | | +0.59 (−2.11 … +3.40) |
| M4, pooled | | | +0.35 (0.00 … +0.70) |
| Moment-runs without commentary | 0 | **4** (Train 1, Validation 3) | |
| Decisive `on_request` evidence fetched | 0 of 6 | 0 of 6 | |
| Cost a run | $0.154 | $0.103 | −33% |

**Decision: not adopted.** The report's reasons: the pooled M2b's interval holds zero; Validation's
M2b is below −0.10; the pooled M1b's upper bound is above +2.0; H has 4 moment-runs without
commentary against A's 0; the worst case (equal to the pooled entry here: no failed runs) misses the
M2b bar. The sets disagree.

**Where the four missing commentaries came from — two faults of the harness:**

1. **The submit step moves on without a submission.** In one H run of 185922072242 the agent, at
   each of the three submit steps, answered in text and called no tool: `_loop` returned `done` on
   that answer and the harness went to the next moment with nothing submitted (no submission line
   in its `tools.jsonl`). Three of the four missing commentaries are this run; they are three of
   Validation's 18 H moment-runs, each counted as not explained.
2. **The gate is stricter than the server.** In an H run of `fresh` (ply 56) the agent's first two
   submissions passed `items` as a JSON **string**: the gate read no subject in it and held both
   (`subjects: [None]`); the server, whose `pre_parse_json` (`mcp/server/mcpserver/utilities/
   func_metadata.py`) parses a JSON string given for a list, would have taken them. Three later
   submissions were refused by the server's checks, the agent stopped, and the harness moved on.

Neither fault showed in the pilots. Both are in the stage loop, not in the stages' idea; as a
diagnostic only (not the decision), H's Validation M2b over the 15 moment-runs it commented is
12 of 15 (0.80), A's 0.78.

**Not changed by this result:** the Train gain is large (+0.30) on 11 moments the harness's
development never saw, and H costs a third less than A on the shared bounds (A uses the room it is
given: its runs are longer).

| # | Question | Recommendation |
| --- | --- | --- |
| Q3 | Fix the two faults (the submit step ends only with an accepted submission of its moment, re-asked a bounded number of times; the gate reads a JSON-string `items` as the server does) and measure again? | Yes, as HS rev. 4 with its own review. |
| Q4 | Measure the fixed harness on which moments? | The evaluation sample has now been seen; a second run on it is a second look, not independent evidence. The Test set (four games, its key causes reviewed by the owner first) is the independent check. Recommended: rerun on the evaluation sample to see the faults gone, and the Test set for the adoption decision. |

## 9. rev. 4 — the two faults of §8

| # | Change | Where |
| --- | --- | --- |
| A2 | **The submit step ends with its moment accepted.** The gate reads each `submit_commentary` answer it lets through (`accepted`: a single answer's `accepted: true`, or an item `accepted` or `duplicate`); when `_loop` returns at the submit step and the moment is not accepted — the agent answered in text, or every submission was refused — the runner asks again (`unsubmitted`: "this moment (ply N) is not in yet; submit it"), at most `SUBMIT_ASKS` = 3 times, each logged (`harness`, `stage: "submit_again"`); after the third the moment is left and logged (`stage: "submit_missing"`). | `harness.py` (`accepted`, `Gate.call_tool`, `harness_loop`) |
| A3 | **The gate reads arguments as the server does.** `items`, `position` and each item's `position` given as a JSON string are read as their value (`normalized`, as the server's `pre_parse_json`); the call goes to the server as the agent wrote it. A string that is not JSON stays a string and is held, as before. | `harness.py` (`_json`, `normalized`, `Gate.allows`) |
| — | The messages are `harness_v2.md` (v1 and the `unsubmitted` section); `HARNESS_VERSION` `harness_v2`, on every H run's `start` line. `harness_v1.md` stays for the runs of §8. | `tools/rx/prompts/` |

**Tests** (`test_hs.py`, 25 now): a text answer at the submit step is asked again and the moment then
submitted (§8's 185922072242 run); a refused submission is not a submission (asked again, then
accepted); a moment never submitted is left after three re-asks and logged; the gate takes `items`
and `position` as JSON strings and passes the call on unchanged, and still holds a JSON string that
names another ply (§8's `fresh` run); `accepted` on both answers' shapes.

**The whole suite** (WSL, rev. 4): **1956 passed, 27 skipped**; 3 failed and 2 errors, all known (the
digest golden on the Windows engine build; the four `zstd` tests). `ruff check` clean.

**The measurement again.** HS-D §6's evaluation sample has been looked at once (§8): a second run on
it shows whether the faults are gone and how H fares without them, but it is a second look, not
independent evidence. The independent check is the Test set (four games; its key causes reviewed by
the owner first, as RX2's were). Proposed: run A and H on the evaluation sample again (36 runs, about
$5) as the check of rev. 4, reported as such; the adoption decision on the Test set.
