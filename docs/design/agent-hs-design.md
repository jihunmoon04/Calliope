# Agent HS-D — the staged harness: facts and the decisive cause per moment, a judge, retries

Status: rev. 1, for independent review. Scope: the RX runner (`tools/rx`), a new arm **H** beside A.
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
game, as A, so H − A is the harness alone (one conversation a moment is a separate change, §8).

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

**The gate.** Before step 3 of a moment, a `submit_commentary` call is not sent to the server: the
runner answers it with "not the submit step yet" and writes a `tool_unsent` line with
`reason: "harness_gate"` (RX1's line, so the run checker counts the call; the pilots wrote none).

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

## 4. The record and the bounds

- The run's `start` line names the arm H, `harness_v1`, `harness_judge_v1` and the retry limit.
- **Every message is logged** (`request` lines): the pilot's wrapper left the system message and the
  task out of the log; the runner logs them.
- **Bounds:** turns 60 → **90**, tool calls 120 → **150**, tokens 2M → **4M** for H (the v7 pilot
  read up to 3.5M input tokens; cached reads are counted, MH §7 Q2); A keeps RX2's.
- **A cut-short answer** (`IncompleteRead`, three runs of TO's batch): retried once, as a timeout is
  (`tools/rx/model.py`), for every arm; a second one ends the run as `error` as today.

## 5. Tests

The stages' order and messages on a scripted model (no network): pass, fail-then-pass, three fails
then submit; the gate's answer and its `tool_unsent` line; the judge's input holds no reference
text (a reference's key cause planted in the scripted record never reaches the judge's request); an
unreadable verdict asked again once, then not blocking; the bounds of H; the logged system message
and task; the `IncompleteRead` retry; arm A unchanged (its messages and bounds byte for byte).

## 6. Measurement and the bar

**Validation, H × 3 runs a game**, judged blind in one judging with TO's v7 arm A runs
(`to-validation-1*`, 11 runs). Paired by moment, H − A, 90% intervals (the RX report).

**H is adopted as the runner's commentary arm when all of:**
- **M2b +0.10 or more, the interval's lower bound above zero** (RX4-D §5's bar for a lesson set);
- M1b no worse: the upper bound at most **+2.0** wrong sentences per 100;
- no more moment-runs without commentary than A;
- the cost a run reported (expected about $0.14, against A's $0.126).

Also reported: `on_request` decisive evidence fetched (A: 1 of 6), retries a moment, verdicts a
moment, the judge's share of the cost.

The two pilot games are part of Validation; their pilot runs are not judged again. The Test set is
not touched.

## 7. Questions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Join facts and the cause in one turn (the pilots used two)? | Yes: fewer turns and no rewritten lists; the judge still sees both. |
| Q2 | The judge on the run's model (Haiku), or a stronger one? | Haiku: the pilots used it, and a stronger judge would measure the judge, not the stages. |
| Q3 | Two retries a moment? | Yes: in the v7 pilot every failed moment passed by the second retry. |
| Q4 | Bounds 90 turns, 150 calls, 4M tokens for H | As written; reported per run. |
| Q5 | Fold the `IncompleteRead` retry into this packet? | Yes: it is a few lines in the runner and the batch needs it. |

## 8. Not in this packet

- One conversation a moment, in parallel, with a short game summary (lower prompts, shorter wall
  time): after H is measured, as H′ against H.
- Korean syllables garbled by Haiku (`agent-mh-implementation.md` §5).
- `game_overview` waiting 600 s under load (TO §10): looked at apart.
