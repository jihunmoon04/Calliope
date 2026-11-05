# Agent — learning from failures: a Calliope-run agent, Reflexion and promoted lessons (RX framing)

Status: **framing, rev. 1, for the owner. No design decision and nothing to implement. Owner questions are
in §8.** Date: 2026-11-05. Base: `main @ f267641` (ST merged).
Owner's direction (2026-11-05): "Reflexion 기반 반복 평가·수정과 ExpeL 형태의 경험 학습을 결합하여, 해설의 품질과
분석 전략을 점진적으로 개선 추후 프롬프트 최적화까지 확장". The idea is to use repeated evaluation and revision
(Reflexion) with lessons learned across tasks (ExpeL), and later to optimise the prompt (GEPA). The commentary
would then run in an agent Calliope runs itself, because HIMARI's persona, other tools and mode rules have
nothing to do with commentary. A Claude session would evaluate the runs and write the reflections.
Inputs: [`agent-mcp-design.md`](agent-mcp-design.md) (AG-D: the server, its tools, the check),
[`agent-st-design.md`](agent-st-design.md) §0 (the trial setup, its limits),
[`agent-st-implementation.md`](agent-st-implementation.md) §4 (the latest trial), the FR framing note
(`agent-free-commentary-framing.md` on branch `design/fr`, PR #130, not merged: the arm `min`).

## 1. What exists today

- **Host.** Every trial since PW ran in HIMARI v3, one conversation a run, with luna (`openai/gpt-6-luna`) and
  the prompt "이 대국을 분석하고 중요한 장면들을 해설해서 저장해 줘." (ST-D §0). HIMARI adds its persona, its
  other tools and its mode rules to every run. Calliope controls none of it.
- **Tools.** The MCP server (`src/calliope/agent/server.py`) serves `open_game`, `analyze_game`,
  `game_overview`, `ply`, `judge_move`, `detail`, `facts`, `explore`, `definitions`, `submit_commentary`,
  `commentary`. It also holds the budget and limits (AG4-D) and the check (`commentary_check_v6`).
- **Guide.** `commentary_ko_v1` … `v8` under `src/calliope/agent/prompts/`. Each version came from a trial of
  the one before. This is prompt optimisation by hand, packet by packet.
- **Evaluation.** Twelve fixed moments in four games (ST-D §0). Errors are counted by a blind fresh-context
  judge against a reference built by the code, with boards checked by python-chess. Means a run come from
  the server's stored commentaries.
- **Records.** The server keeps no record of a run's tool calls. Trial records live in a session's scratchpad
  (ST-D §0.5: session `e058e396`, `fr3`), outside the repository.

What the trials already show that bears on this note:

| Observation | Where |
| --- | --- |
| Sentences citing a line the agent played with `explore`: **0** in every arm | FR §3.1 |
| Refused submissions: about 4 a run (3.8–5.3). Each refusal is a failure with its reason stated by the server | FR §3.1, ST §4 |
| The commonest error (an old attack read as new) was cut by adding material, where a guide rule had not cut it | ST-D §0.6 |
| A minimal guide (task, tools, check only) was not read in six of eight runs unless the instructions said to read it | FR §2 (`min0`) |
| Judges differ: v7 counted 7 wrong by one judge and 11 by another; arms compare only within one judging | ST §4, ST-D §0.5 |

## 2. Three mechanisms, one ladder

| | Scope | Where the lesson lives | Lifetime |
| --- | --- | --- | --- |
| Reflexion | one task: fail, reflect, retry | the task's context | the run |
| ExpeL / meta-reflection | across tasks: lessons and successful runs | a store retrieved by situation | until stale or withdrawn |
| GEPA | the prompt itself, evolved against an evaluation set | the guide (`commentary_ko_vN`) | until the next version |

GEPA also mutates prompts by reflection, so the three differ less in method than in **where the result lands**.
They can be read as one ladder of promotion:

> a reflection in one run → the same reflection in many runs (a candidate lesson) → a verified lesson in the
> store, retrieved when its condition holds → a lesson true whatever the situation, folded into the guide.

**One rule comes before the ladder: a lesson that a machine can check becomes a check, not a memory.** The
owner's example, "핀을 근거로 물질 획득을 주장하려면 explore로 후속 수순을 확인하고, 획득이 증명되지 않으면 배치 사실만
설명하라", is a check. A sentence that claims a gain must cite something that proves the gain. A memory helps
only when retrieval finds it, while a check refuses every time. This follows ST-D §0.6: information and checks
lowered the errors where guide rules had not. The store is for what cannot be checked: which tool to read
first in which situation, when to explore and how far, what is worth saying at a moment.

The owner's second example is the store's shape:

> "실제 수와 최선수를 비교하면서 평가치만 참고했다. 다음에는 ply의 board.same_reply를 먼저 확인하고, 설명 가능한
> 차이가 없다면 explore를 사용해 동일한 응수를 두 수 뒤에 적용해 본다. 결과가 다르면 해당 수순과 그 차이를 인용한다."

It has a situation, an action in tool calls, a test of success and a fallback.

## 3. A Calliope-run agent (packet RX1)

A loop, not a second tool layer:

- **Tools**: the MCP server, as an MCP client. The tool contract is HIMARI's, so the HIMARI path and this path
  can be compared on the same games, and the budget and limits apply unchanged.
- **System prompt**: the guide (`commentary_ko_vN`) and the server's instructions, nothing else.
- **Excluded**: persona, tools other than Calliope's, mode rules, a conversation's history across runs.
- **Bounds**: turns, tool calls and tokens a run. A run ends with its last accepted submission or at a bound.
- **Model**: behind a thin interface, so the writer (today luna) and other models can be swapped. Every run
  records the model id.
- **Retry on refusal** (Reflexion's first step, RX3): a refused submission's reason goes back to the model
  for at most *N* retries. Today the agent already sees the refusal; RX3 makes the retry policy explicit and
  measured.
- **A retrieval slot**, empty until RX4.

**Use.** For batch runs and evaluation only. HIMARI stays the user's host. Streaming, the viewer and follow-up
questions are out of scope (Q1).

**The run record.** One JSON Lines file a run. Its header holds the model id, the guide version, the server's
build identity (tool, digest and check versions), the game, the bounds and the start time. Then every tool
call with its arguments, its answer (or its digest and size, Q3), its time and refusals with their reasons,
and every submission with the check's result. The evaluator (§5), the metrics (§4) and the store (RX4) all
read this record, so it is the packet's real product. The record could instead be written by the server,
which would cover HIMARI's runs too (Q2).

## 4. Evaluation (packet RX0, before any code)

- **Sets.** A training set (the games whose failures produce reflections) and a held-out set (games never
  read by the evaluator). A lesson is promoted only on the held-out set. The four games and twelve fixed
  moments of ST-D §0 are the natural start. Which of them is held out, and which games join, is Q4.
- **Metrics**, from the run record and the stored commentary:
  - **M1 fact errors**: refused submissions and their reasons, a run (automatic), and wrong sentences at the
    fixed moments (the blind judge, as in ST §4).
  - **M2 omissions**: at the fixed moments, reasons in the moment's reference that no sentence cites. Sentences
    cite by handle (MS-c), so counting is automatic once the reference marks which reasons a commentary
    should carry. Writing those marks is the owner's call (Q5).
  - **M3 strategy**: patterns in the record, such as a gain claimed with no proving citation before the
    submission, or a verdict compared on scores alone with `same_reply` not read. Each pattern is counted
    by a rule written in RX0.
  - **M4 quality**: the judge's 1–5 score and the owner's reading. Later, and never alone (§5).
- **Noise.** One judge, one model and 24 commentaries an arm separate about 1 wrong sentence per 100
  (ST-D §0.5). RX0 states the number of runs a comparison needs, and comparisons stay within one judging.

## 5. Claude as the evaluator (packets RX4, RX5)

A Claude session reads a run's record and diagnoses what fell short. It may call Calliope's tools itself,
for example to play the `explore` the agent should have played and see whether it settles the point. It
then writes reflections in the store's shape. This is a good fit: the session reads the record, the code, the
design documents and the guide directly, and checks its own diagnosis with the tools before proposing a cure.

Conditions:

1. **Diagnose from Calliope's facts.** The input is the structured failure (a refused sentence and its reason,
   an uncited reason of the reference, the tool trajectory), not "find what is wrong". Each diagnosis cites a
   tool answer or a fact. The evaluator's own chess judgement is not evidence, as the agent's is not.
2. **Writing is not judging.** The evaluator proposes. A lesson is judged by a re-run: the agent runs again on
   the failing moment with the lesson retrieved, and then on the held-out set. The lesson passes when the
   failure is fixed and nothing regresses. Then the owner reviews it.
3. **A fixed shape.** A lesson has these fields:
   - `condition`: fact kinds, template ids, labels;
   - `action`: tool calls in order;
   - `success`: what the submission must then cite;
   - `fallback`: what to say when the action does not prove the point;
   - `versions`: the tools, digest and check it was written against;
   - `source`: the runs it came from.

   A lesson is short, names only tools and fields that exist, and is refused if it has no executable action
   ("think harder").
4. **Staleness.** When a version a lesson names changes (as `board_v2` became `board_v4`), the lesson is
   re-verified or withdrawn, as a commentary's staleness is judged by the graph digest (PF-D §12).
5. **Reproducible.** In batch the evaluator runs headless (`claude -p`) with a versioned prompt file, a JSON
   output schema, and read-only permissions plus Calliope's MCP tools. Each run of the evaluator is recorded
   like the agent's. Usage limits suggest diagnosing only failing moments.

RX4 runs the evaluator by hand on a few failures first. Its prompt and the lesson's shape are settled on real
failures before RX5 automates them.

## 6. Packets, in order

| Packet | Content | Done when |
| --- | --- | --- |
| RX0-D | the sets, M1–M3 rules, the run record's schema, the comparison's size (§4) | reviewed READY |
| RX1 | the Calliope-run agent and its run record (§3) | the evaluation set runs end to end; every record complete |
| RX2 | baseline: the same games through HIMARI and through RX1, `commentary_ko_v8`, the same model | M1–M3 for both; anything HIMARI gave that the guide must now state is listed |
| RX3 | retry on refusal, at most *N* | M1 against RX2, within one judging |
| RX4 | the evaluator by hand: prompt, lesson shape, a few lessons re-run | some lessons fix their failure on re-run and do not regress on the held-out set |
| RX5 | batch: the evaluator headless, re-runs, the owner's review queue, the store and its retrieval | one night produces reviewed candidates without hands |
| later | ExpeL across many runs; GEPA on the guide; M4 | after RX5 shows lessons that hold |

RX1 and RX0's record schema go together. The rest follows in order, because each packet's measurement is the
next one's baseline.

## 7. What this note does not decide

The store's format and retrieval beyond "keyed by Calliope's facts, not by embeddings". The lesson-mining
method (ExpeL) and the prompt optimiser (GEPA). The user-facing agent. Any change to the check or the guide.

## 8. Owner questions

- **Q1 — Use.** Is the Calliope-run agent for batch and evaluation only, with HIMARI kept as the user's host?
  Recommended: yes.
- **Q2 — Who writes the run record.** The runner, or the server? A server-side record also covers HIMARI's
  runs, which RX2 needs, and would hold no persona. Recommended: the server, with the runner adding its own
  header (model, bounds).
- **Q3 — Answers in the record.** Store tool answers in full, or a digest and size with the full answer
  rebuilt from the build identity? Recommended: full in RX1–RX4 (small games, needed by the evaluator), revisit
  in RX5.
- **Q4 — Sets.** Which of the four games is held out, and which games join the training set?
- **Q5 — The reference for M2.** Who marks, at each fixed moment, the reasons a commentary should carry? The
  owner, or the evaluator with the owner's review?
- **Q6 — The writer model.** luna as in the trials, or another low-cost model alongside it?
