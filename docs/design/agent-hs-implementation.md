# Agent HS — the staged harness as arm H of the RX runner

Status: rev. 1, for independent review. Implements `agent-hs-design.md` rev. 3 (merged, PR #151).
The measurement of §6 runs after this review (§5).

## 1. What changed

| File | Change |
| --- | --- |
| `tools/rx/harness.py` (new) | Arm H: `harness_loop` drives each fixed moment, in game order, through the stages on `run._loop` (facts and the decisive cause in one turn → the judge → at most two retries → submit); `Gate` (`(phase, current_ply)`, review B2): `submit_commentary` reaches the server only at the current moment's submit step and only when every subject — `ply`, `position` and `move`, each of `items` — is that moment, else the runner answers and writes `tool_unsent` (`reason: "harness_gate"`, the call's id, phase, subjects); `judge` (one request on the run's model, no tools; asked again once when its answer is not the JSON; never blocking); `subject_ply`, `subjects_of`. |
| `tools/rx/prompts/harness_v1.md`, `harness_judge_v1.md` (new) | The runner's messages (task, facts, retry, submit, gate) and the judge's rubric v2, as the pilot's, facts and cause joined. |
| `tools/rx/run.py` | `ARMS` adds H (`HARNESS_ARMS`); H's task from `harness_v1.md`, its loop `harness_loop` with a judge model (the run's model, no cache marks, the run's `session_id`); the `start` line names `harness_v1`, `harness_judge_v1` and the retries; `_loop` sets `next_call_id` on a session that has it, so the gate can log the call it holds. Arm A's messages and loop are unchanged. |
| `tools/rx/request.py`, `tools/rx/model.py` | Review N2: the child answers a body cut short or a dropped connection (`http.client.HTTPException`, `ConnectionError`) as `{"error", "kind": "transport"}`; the parent raises `ModelTransient`, which `complete` retries once, as a timeout. |
| `tools/rx/report.py` | Review C1: for a pair spanning both sets, `H − A / pooled` — the same estimator and bootstrap over every set's games, a game keyed by `(set, game)` — and `decisions[pair]`: adopted when the pooled M2b gains 0.10 with its interval above zero, no set's M2b is below −0.10, and the pooled M1b's upper bound is at most +2.0; `sets_disagree` when the sets point opposite ways. `paired(cells, None, …)` pools. |
| `tests/agent/test_hs.py` (new) | 12 tests (§3). |

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

`tests/agent/test_hs.py`, 12 tests, no network and no engine:

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
- **The pooled report (C1):** one set pools to its own value; a game name in two sets is two games;
  the decision: pool met and both sets up (adopted), one set at −0.15 (not), the pool short with a
  set up by 0.3 (not), M1b's bound at 2.5 (not).

## 4. The whole suite

WSL: **1943 passed, 27 skipped**; 3 failed and 2 errors, all known (the digest golden on the Windows
engine build; the four `zstd` tests, RX1 §3). `ruff check` clean.

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
