# Agent HS-D — the staged harness: facts and the decisive cause per moment, a judge, retries

Status: rev. 3; independent review NOT_READY (B1–B3; N1, N2) applied; re-review NOT_READY (C1, C2)
applied (§9). Scope: the RX runner (`tools/rx`), a new arm **H** beside A.
The server, its tools (`agent_tools_v7`, TO) and the guide (`commentary_ko_v8`) are unchanged.

## 0. Why

The owner asked whether forcing the agent through "facts, then the decisive cause, then a check that
sends a weak cause back" would get the decisive cause found more often, and whether such a check
would make the agent fetch evidence itself rather than only when given it (2026-11-06). Two pilots
answered on two Validation games (185264271324: 15.O-O, 23.Rxe5, 34.Bb2+; 184800218248: 6...c5,
29.Ra4, 29...a5), Haiku, read by the author, not blind:

**Pilot 1 (v6 tools, `rx-evidence/to/harness-pilot.md`), two runs an arm.**

| Arm | Decisive cause explained | `explore` a run | 23.Rxe5's decisive evidence fetched | Cost a run |
| --- | --- | --- | --- | --- |
| Plain loop (`trial-haiku-1`, three runs) | 13 / 18 (72%) | 0 | 0 / 3 | $0.15 |
| Line summaries in the task, plain loop | 8 / 12 | 0 | 0 / 2 | $0.36 |
| **Staged harness** | **11 / 12 (92%)** | 3–8 | 1 / 2 | $0.38 |
| Line summaries and staged harness | 10 / 12 | 1–8 | 2 / 2 | $0.36 |

- The judge's verdict sent the agent to the tools: after a failed verdict it called `explore`,
  `facts`, `detail` and played the best and the played line out; in 29.Ra4 it found a fact the key
  cause does not state (30.Rxb4 runs into 30...Rxd1#).
- Information given without the stages was not used (15.O-O's rook loss, in the line summary,
  was not written in either run).
- The first judge rubric refused the right cause three times (a skewer in the engine's line, "not
  played in the game"); rubric v2 (§3) passes it, and fails a cause that stops at "the knight is
  still attacked" and one that claims a defended knight wins three points.

**Pilot 2 (v7 tools, TO §10), two runs a game.** The same harness on the brief views and
`compare_lines`: **$0.137 a run** against $0.375 (−63%); prompts of 56k–90k tokens a request on
average against 81k–154k; `compare_lines` called in three of four runs; 23–39 turns; 1.3M–3.5M
input tokens a run. The judge failed 3 of 12 first attempts; all passed within two retries.

The blind batch of TO (§10) put the plain loop on v7 at M2b 0.727 on Validation. This packet
measures the harness against it.

## 1. The arm

**H = A (v7, Haiku, `commentary_ko_v8`) + the stages of §2 + the judge of §3.** One conversation a
game, as A (one conversation a moment is a separate change, §8).

**One budget for both (review B1).** The comparison runs A and H on the same bounds — 90 turns, 150
tool calls, 4M tokens, 1,800 s (§4) — so H − A measures the stages and the judge, not more room. A
rarely nears RX2's bounds (one of TO's 11 runs reached 2M tokens), so A's runs for this comparison
are new runs on the shared bounds, not TO's.

## 2. The stages

The runner drives each fixed moment in turn (the moments in game order), in the one conversation:

1. **Facts and the decisive cause, one turn** (the pilots' two turns joined: the fact list was
   rewritten on every retry: the agent's own text was 17% of one staged run's conversation). The runner's message (Korean, fixed in
   `tools/rx/prompts/harness_v1.md`):
   - the moment by its numbered move;
   - "with the tools, gather the facts of this moment and list at most eight, each with its `ref`
     (a line you played out counts: its material and its end score); then write its decisive
     cause as a chain: the move → the opponent's concrete reply or line → the outcome (material
     won or lost, mate, or nothing gained); at most two supporting causes; do not submit yet."
   The agent may call any tool. Its reply's text is the facts and the cause.
2. **The judge** (§3) reads the reply. **Pass:** step 3. **Fail:** the runner sends the judge's
   problems back ("the judge did not pass it: … — check with the tools if needed, then write the
   facts and the cause again") and returns to step 1; at most **two** retries a moment. After the
   third failure the runner goes on to step 3 and says so.
3. **Submit:** "submit this moment's commentary with `submit_commentary`; the decisive cause first;
   the guide's form; fix and resubmit if it is refused." The refusals of `submit_commentary` work as
   in arm A (no retry message of arm B).

**The gate (review B2).** The runner holds `(phase, current_ply)`: `phase` is `facts` (steps 1–2) or
`submit` (step 3), `current_ply` the moment being worked. A `submit_commentary` call is sent to the
server only when `phase` is `submit` and **every subject of the call is the current moment**: its
`ply` equals `current_ply`, or, with `items`, every item's `ply` does; a subject named by `position`
and `move` is the current moment when that position is the one before `current_ply` and the move
its played move. Any other call — in `facts`, or naming another ply, a variation, or an empty or
malformed `items` — is not sent: the runner answers "only this moment, at its submit step: ply N"
and writes a `tool_unsent` line with `reason: "harness_gate"`, the call's subjects and the phase
(RX1's line, so the run checker counts the call; the pilots wrote none). One blocked call never
blocks the moment.

**The task message** names the game and the fixed moments and says the stages will follow. Moments
other than the fixed ones are not asked for (arm A's agent may comment more; only the fixed moments
are judged).

## 3. The judge

- **Model:** the run's model (Haiku), one request, no tools, no cache marks; its usage counted in
  the run's totals (`judge_cost`, `judge_tokens` apart).
- **Input:** the moment's header — numbered move, grade, the played and the best move's scores (the
  digest's `evaluation`) — and the agent's reply of step 1. **Never the key causes** or anything of
  the references.
- **Rubric v2** (`tools/rx/prompts/harness_judge_v1.md`), as the pilot's second version: a
  consequence the engine's line shows is a legitimate cause though the game went otherwise; the
  evaluation gap need not be accounted for in material. Fail only on: (1) a claim not in the fact
  list; (2) stopping at an observation without an outcome; (3) material won or lost without a played-
  out line in the list, or a defended piece said to be won; (4) no comparison with the best move.
  Not a better wording. At most three problems, one sentence each; never a move or line to try.
- **Answer:** one JSON `{"pass": bool, "problems": [...]}`; an answer that is not that JSON is asked
  again once; still unreadable, the moment goes on (`"unreadable": true`), never blocked.
- **Record:** a `judge` line a verdict in `agent.jsonl` (moment, attempt, verdict, usage, the reply
  judged).
- **What the judge does not do (review §2).** It checks the reply against itself — that each claim of
  the cause stands in the agent's fact list, that the cause runs to an outcome, that a gain is backed
  by a line in the list — not that the facts are true. Truth is `submit_commentary`'s check, against
  the server's records, as for arm A; the judge is not a second verifier.

## 4. The record and the bounds

- The run's `start` line names the arm H, `harness_v1`, `harness_judge_v1` and the retry limit.
- **Every message is logged** (`request` lines): the pilot's wrapper left the system message and the
  task out of the log; the runner logs them.
- **Bounds:** turns **90**, tool calls **150**, tokens **4M**, 1,800 s, for **both arms** of this
  comparison (B1; the v7 pilot of H read up to 3.5M input tokens; cached reads are counted, MH §7 Q2).
  RX2's bounds stay the runner's defaults; a batch names these with the bound flags it already has.
- **A cut-short answer (review N2).** `http.client.IncompleteRead` is an `HTTPException`, not an
  `OSError`: `tools/rx/request.py`'s child dies with a traceback and no JSON, and the parent sees
  only "the request process gave no answer". The child catches `http.client.HTTPException` (and
  `ConnectionError`) and answers `{"error": …, "kind": "transport"}`; `model.py` raises
  `ModelTransient` (a `ModelError`) for that kind, and `OpenRouter.complete` retries once on
  `ModelTimeout` or `ModelTransient`, for every arm; a second one ends the run as `error` as today.
  A child that still gives no JSON stays a plain `ModelError`.

## 5. Tests

The stages' order and messages on a scripted model (no network): pass, fail-then-pass, three fails
then submit; the gate's answer and its `tool_unsent` line; the judge's input holds no reference
text (a reference's key cause planted in the scripted record never reaches the judge's request); an
unreadable verdict asked again once, then not blocking; the bounds; the logged system message
and task; arm A unchanged (its messages byte for byte). **The gate (B2):** in `facts` any submit is
blocked; in `submit` the current ply passes, another ply, an `items` list holding another ply, an
empty `items` and a variation are blocked with their `tool_unsent` lines. **Transport (N2):** the real
child process (`python -m tools.rx.request`) against a local HTTP server that sends a chunked body
and closes early answers `kind: "transport"`; `complete` retries once and succeeds when the second
answer is whole, and ends as `ModelError` after two. **The pooled report (C1):** as §6 lists.

## 6. Measurement and the bar

**The sample (review B3).** The harness — its stages, its rubric v2, its retries — was shaped on the
six moments of Validation games 185264271324 and 184800218248. Those two games are the
**development sample**: reported, never counted as evidence. The **evaluation sample** is the
moments the harness's development never looked at, all with owner-reviewed key causes:

- **Train**, four games, 12 moments (used by RX4a to write lessons; no lesson is in arm A or H);
- **Validation 185371835722 and 185922072242**, 6 moments.

18 moments, six games. **M2b is computed on 17** (review C2): `train/rapid-40` is reviewed with no
key cause (RX2-D A3: its reason is positional), so its `decisive` is None and the report leaves it
out of M2b; M1b and M4 count all 18. The Test set stays untouched (§7 Q6).

**Runs.** A and H, three runs a game each, on the shared bounds (§4), interleaved by game as RX
batches are; one judging holding both, blind, `judge_v1`, audited. Paired by moment, H − A, 90%
intervals.

**The pooled estimate (review C1).** The RX report pairs arms within one set (`paired(cells,
set_name, …)`): it gives `H − A / train` and `H − A / validation`, not one value over the six games.
This packet adds to `tools/rx/report.py`, for every pair whose cells span more than one set, an
entry **`H − A / pooled`**: the same estimator (each moment's value over its runs, the difference
by moment; M1b as each moment's difference of rates) and the same two-stage bootstrap, games then
moments, over **all the sets' cells together, each game keyed by `(set, game)`** so two sets never
merge a game. The per-set entries stay, beside it, as secondary results. `report.py`'s tests: one
set alone gives the same pooled and per-set values; a game name present in two sets is two games
in the pool; the pooled `moments` count is the sum of the sets'.

**The decision reads the pooled entry**, and the per-set entries guard it: H is not adopted when a
set's M2b point estimate is below **−0.10** (H clearly worse on one set), even if the pooled bar is
met; the report says when the two sets point in opposite directions. A test of the decision on
constructed cells: pooled met and both sets up (adopt); pooled met and one set at −0.15 (not
adopted); pooled not met and one set up by +0.3 (not adopted).

**Every run counts (review N1).** A started run ends `done`, at a bound, or as a failure
(`timeout`, `error`). Reported per arm, for every run started, retries included: its end reason,
whether it was judged, its cost. A failed run is rerun once (as TO's were) and both are reported.
Quality is computed on the runs judged (done or at a bound with its moments saved), and again with
every failed run's moments counted as not explained and without commentary (the worst case); a
conclusion that holds only on the first is said to.

**H is adopted as the runner's commentary arm when all of, on the evaluation sample, read from
`H − A / pooled`:**
- **M2b +0.10 or more, the interval's lower bound above zero** (RX4-D §5's bar), on the 17 moments
  with a decisive cause;
- no set with an M2b point estimate below −0.10 (C1);
- **M1b** no worse: the upper bound at most **+2.0** wrong sentences per 100, on the 18 moments;
- **failures** (runs not judged) and **moment-runs without commentary** no more than A's, in counts;
- the result holds in the worst case of N1.

**Also reported** (the review's last paragraph): the decisive `on_request` evidence fetched by a tool
call (M3); after a failed verdict, how often the moment's final commentary explains its decisive
cause (the improvement after a refusal), against moments passed at once; verdicts and retries a
moment; the final commentaries' wrong sentences (M1b) by whether their moment was retried; cost a
run, the judge's share; the development sample's numbers apart.

## 7. Questions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Join facts and the cause in one turn (the pilots used two)? | Yes: fewer turns and no rewritten lists; the judge still sees both. |
| Q2 | The judge on the run's model (Haiku), or a stronger one? | Haiku: the pilots used it, and a stronger judge would measure the judge, not the stages. |
| Q3 | Two retries a moment? | Yes: in the v7 pilot every failed moment passed by the second retry. |
| Q4 | Bounds 90 turns, 150 calls, 4M tokens, for both arms (B1) | As written; reported per run. |
| Q5 | Fold the transport retry (N2) into this packet? | Yes: a few lines in the runner and its child, and the batches need it. |
| Q6 | The Test set for H, instead of Train and the two other Validation games (B3)? | Not now: Test has no references, and its key causes would need the owner's review first. Train and the two games are untouched by the harness's development; Test stays for a final check of what is adopted. |

## 8. Not in this packet

- One conversation a moment, in parallel, with a short game summary (lower prompts, shorter wall
  time): after H is measured, as H′ against H.
- Korean syllables garbled by Haiku (`agent-mh-implementation.md` §5).
- `game_overview` waiting 600 s under load (TO §10): looked at apart.

## 9. Review (rev. 1 → rev. 2)

Independent review of `4739787`: NOT_READY.

| # | Finding | Disposition |
| --- | --- | --- |
| B1 (P1) | H had larger bounds than A; H − A could not tell the harness from more room | Applied (§1, §4): both arms on 90 / 150 / 4M / 1,800 s; A's runs are new runs on those bounds. |
| B2 (P1) | The gate was open or shut; at the submit step a call could carry another, unjudged ply in `items` | Applied (§2): `(phase, current_ply)`; every subject of the call, `items` included, must be the current moment; anything else is blocked and logged; tests for each case (§5). |
| B3 (P1) | The pilot games, used to shape the harness, were in the evaluation | Applied (§6): the two pilot games are the development sample, reported apart; evaluation on Train (12 moments) and the two other Validation games (6), none seen by the harness's development. Test kept for later (Q6). |
| N1 (P2) | Failed runs could fall out of the statistics unseen | Applied (§6): every started run reported with its end and cost; a failure rerun once, both reported; quality also in the worst case (failed runs' moments unexplained); adoption needs it to hold there and no more failures than A. |
| N2 (P2) | `IncompleteRead` never reached the parent as such (the child dies without JSON) | Applied (§4): the child answers `kind: "transport"`; the parent's `ModelTransient` is retried once; a test through the real child against a server that cuts the body short. Checked: `IncompleteRead` is an `HTTPException`, which the child does not catch today. |
| Note | The judge does not verify the facts | Applied (§3): its scope is stated; truth stays `submit_commentary`'s. |
| Note | Measure the evidence fetched, the improvement after a refusal, the final wrong sentences | Applied (§6, also reported). |

Re-review of `afa8be8`: NOT_READY (B1–B3, N1, N2 resolved).

| # | Finding | Disposition |
| --- | --- | --- |
| C1 (P1) | The report pairs within a set; no single value over the six games, and no rule when the sets disagree | Applied (§6): `report.py` adds `H − A / pooled` (games keyed by `(set, game)`, the same estimator and bootstrap), keeps the per-set entries; the decision reads the pooled entry, and a set with M2b below −0.10 blocks adoption; tests for the pool and for the decision. Checked: `paired()` filters by `set_name` (`report.py`). |
| C2 (P2) | `train/rapid-40` has no key cause: M2b has 17 moments, not 18 | Applied (§6): M2b on 17, M1b and M4 on 18. Checked: `rapid-40` is `reviewed` with `key_causes: []`. |
