# Agent — learning from failures: a Calliope-run agent, Reflexion and promoted lessons (RX framing)

Status: **framing, rev. 2, for the owner. No design decision and nothing to implement. Owner questions are
in §8. Independent review of rev. 1: READY_WITH_CORRECTIONS (B1–B5; N1, N2; control arms), applied, §9.**
Date: 2026-11-05. Base: `main @ f267641` (ST merged).
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
  `commentary`. It also holds the budget and limits (AG4-D) and the check (`commentary_check_v6`). The check
  reads a sentence's moves, scores, squares and numbers against what the sentence cites (FR §1). It does not
  verify every meaning that a cited item implies.
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

### 2.1 Verification and strategy are two things (review B5)

A failure can teach two kinds of lesson, and they go to different places:

| | Question | Where it goes |
| --- | --- | --- |
| **Verification** | Is what the sentence claims proved by what it cites? | a check, when the check can read it; otherwise the judge (§4) |
| **Strategy** | Which tool, when, to find the evidence a claim needs? | a lesson in the store (§5) |

The owner's example splits along this line:

- "a sentence that claims a gain from a pin must cite something that proves the gain" is **verification**.
  When the check can read it (the gain's material in a cited line), it belongs in the check. A memory helps
  only when retrieval finds it, while a check refuses every time. This follows ST-D §0.6: information and
  checks lowered the errors where guide rules had not.
- "on a pin, call `explore` to see the follow-up" is **strategy**, and it is not a check. The digest may
  already hold a line that proves the gain, and then no `explore` is needed. A strategy lesson is conditional:
  the action is called for only when the claim's evidence is not yet in hand.

Not every verification lesson can become a check, because the check does not verify a cited item's every
meaning (§1). What the check cannot read is measured by the judge (M2b, §4) and stays out of the store. The
store holds strategy only.

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
- **Bounded retry on the check's refusal** (RX3). A refused submission's reason goes back to the model for at
  most *N* retries. This is not Reflexion (review N1): the agent already sees refusals and may resubmit
  today, and a retry changes the sentence, not the analysis. RX3 only makes the policy explicit and measured.
  Diagnosing a failure's cause and changing the strategy begins in RX4.
- **A retrieval slot**, empty until RX5.

**Use.** For batch runs and evaluation only. HIMARI stays the user's host. Streaming, the viewer and follow-up
questions are out of scope (Q1).

### 3.1 The run record: two layers, one run id (review B3)

The server sees tool calls but not the model's side. Reflection needs both, so a run is recorded twice and
joined:

| Layer | Written by | Holds |
| --- | --- | --- |
| Agent | the runner | the model id, the guide version, the server instructions sent, every model request and response, tokens and cost, the bounds, the run's end and its reason |
| Tools | the server | every tool call with its arguments and answer, refusals and their reasons, every submission with the check's result, times, the build identity (tool, digest and check versions) |
| Run | the run store | both layers under one `run_id` |

- **HIMARI's runs** have the tools layer only. That is enough for M1, M2a and M3 (§4), and it is what RX2 can
  compare. The agent layer exists for RX1's runs only.
- **The run id** reaches the server through the MCP connection (a header or an argument at `open_game`). Which
  one is RX0's choice.
- **Answers in full** in RX1–RX4, under a size cap a run, each answer with its digest so a record can be checked
  for integrity (Q3).
- **Sensitive data.** The records hold the owner's games (PGNs, players' names) and model responses. They stay
  local and outside the repository. A record or an excerpt enters a design document only as counts and quoted
  sentences, as the trials do today.

One JSON Lines file a layer a run. The evaluator (§5), the metrics (§4) and the store all read these records,
so the records are the packet's real product.

## 4. Evaluation (packet RX0, before any code)

### 4.1 Sets (review B4)

The four games of ST-D §0 shaped `commentary_ko_v1`–`v8`, so they are not independent of today's guide. A
held-out set that chooses among many candidate lessons also drifts towards them. Three sets:

| Set | Use | Never used for |
| --- | --- | --- |
| Train | failures read by the evaluator; lessons written from them | promotion |
| Validation | a candidate lesson's effect; promotion | writing lessons |
| Test | a final measure of the promoted store and guide | choosing or promoting any candidate |

The four games and their twelve fixed moments are development data: Train, or Validation while no other
games exist. Test needs new games, never read by the evaluator or the owner while choosing (Q4).

RX0 states how many runs a comparison takes: the run-to-run variance of each metric measured on the baseline,
and the smallest effect worth detecting. Today one error moves a rate by about 0.85 per 100 (FR §3.2), and
one judging separates about 1 per 100 (ST-D §0.5). Comparisons stay within one judging.

### 4.2 Metrics

- **M1 fact errors**: refused submissions and their reasons, a run (automatic), and wrong sentences at the
  fixed moments (the blind judge, as in ST §4).
- **M2 omissions**, in two parts (review B1). Citing a reason is not explaining it ("this move had a bad result"
  may cite the right item and still say no cause), and a cause explained in other words than the reference
  is not an omission.
  - **M2a evidence coverage**: at the fixed moments, the reference's key reasons that no sentence cites.
    Automatic, since sentences cite by handle (MS-c).
  - **M2b explanation coverage**: the reference's key causes that no sentence explains, whatever it cites.
    Judged: the blind judge, calibrated on reference cases the owner has reviewed (Q5).
- **M3 strategy**, recorded per reason kind in three states (review B2). The record cannot show what a model
  read: `board.same_reply` is in the default `ply` digest (`agent/board.py`), so a `ply` call serves it whether
  or not the model uses it.

  | State | Observed as |
  | --- | --- |
  | Available | the item was in an answer the agent received (tools layer) |
  | Used | a sentence cites it, or a later tool call acts on it (an `explore` from its position, a `detail` of its handle) |
  | Explained | M2b counts its cause as explained |

  "Used" is what can be observed. It does not prove a model's reading, and M3 claims no more. The patterns
  RX0 writes as rules are of this kind: a gain claimed while its proving line was Available and not Used, or a
  verdict explained by scores alone while `same_reply` was Available and not Used.
- **M4 quality**: the judge's 1–5 score and the owner's reading. Later, and never alone (§5).

### 4.3 Control arms (review §4)

To tell what a lesson store adds from what more trials add, the same moments and model run in four arms:

| Arm | Condition | Separates |
| --- | --- | --- |
| A | one commentary, no retry, no store | the baseline |
| B | A with the bounded retry (RX3) | B − A: the retry |
| C | B with lessons retrieved from the store | C − B: the store, i.e. what was learned |
| D | C with an improved guide | D − C: the guide |

A store that does not beat B on Validation is not promoted, however well C reads.

## 5. Claude as the evaluator (packets RX4, RX5)

A Claude session reads a run's record and diagnoses what fell short. It may call Calliope's tools itself,
for example to play the `explore` the agent should have played and see whether it settles the point. It
then writes strategy lessons in the store's shape. This is a good fit: the session reads the record, the
code, the design documents and the guide directly, and checks its own diagnosis with the tools before
proposing a cure.

Conditions:

1. **Diagnose from Calliope's facts.** The input is the structured failure (a refused sentence and its reason,
   a reason that is Available and not Used, an M2b omission, the tool trajectory), not "find what is wrong".
   Each diagnosis cites a tool answer or a fact. The evaluator's own chess judgement is not evidence, as the
   agent's is not.
2. **Writing is not judging.** The evaluator proposes. A lesson is judged by a re-run: arm C on the failing
   moment and then on Validation, against arm B. The lesson passes when the failure is fixed and nothing
   regresses. Then the owner reviews it. The judge that scores M1, M2b and M4 is another session with its own
   prompt, blind to the arm and to which lesson ran, so the writer of a lesson never grades it (review N2).
3. **A fixed shape.** A lesson has these fields:
   - `condition`: fact kinds, template ids, labels, and which evidence is not yet in hand;
   - `action`: tool calls in order;
   - `success`: what the submission must then cite;
   - `fallback`: what to say when the action does not prove the point;
   - `versions`: the tools, digest and check it was written against;
   - `source`: the Train runs it came from.

   A lesson is short, names only tools and fields that exist, and is refused if it has no executable action
   ("think harder").
4. **Staleness.** When a version a lesson names changes (as `board_v2` became `board_v4`), the lesson is
   re-verified or withdrawn, as a commentary's staleness is judged by the graph digest (PF-D §12).
5. **Tools and state** (review N2). `submit_commentary` stores commentary. `explore` and `judge_move` take
   budget and run engine work that fills the result store (`agent/session.py`). The evaluator is therefore
   given the reading tools (`game_overview`, `ply`, `detail`, `facts`, `definitions`, `commentary`), and
   `explore` and `judge_move` only against a separate data and cache area, never the one the agent's runs and
   their re-runs use. It never gets `submit_commentary`. Re-runs for promotion use their own area too, so one
   arm's cache never warms another's.
6. **Reproducible.** In batch the evaluator runs headless (`claude -p`) with a versioned prompt file, a JSON
   output schema, and read-only file permissions plus the tools of item 5. Each run of the evaluator is
   recorded like the agent's. Usage limits suggest diagnosing only failing moments.

RX4 runs the evaluator by hand on a few failures first. Its prompt and the lesson's shape are settled on real
failures before RX5 automates them.

## 6. Packets, in order

| Packet | Content | Done when |
| --- | --- | --- |
| RX0-D | the three sets, M1–M4 rules, the two-layer record and its run id, the comparison's size, the arms (§4) | reviewed READY |
| RX1 | the Calliope-run agent and its record (§3) | the development set runs end to end; every record complete in both layers |
| RX2 | baseline, arm A: the same games through HIMARI and through RX1, `commentary_ko_v8`, the same model | M1–M3 and their variance for both; anything HIMARI gave that the guide must now state is listed |
| RX3 | arm B: the bounded retry on refusal, at most *N* | B − A on M1, within one judging |
| RX4 | the evaluator by hand: prompt, lesson shape, a few lessons re-run in arm C | some lessons fix their failure and C beats B on Validation without regressions |
| RX5 | batch: the evaluator headless, re-runs in their own area, the owner's review queue, the store and its retrieval | one night produces reviewed candidates without hands |
| later | ExpeL across many runs; GEPA on the guide (arm D); Test measured once per promoted store | after RX5 shows lessons that hold |

RX1 and RX0's record schema go together. The rest follows in order, because each packet's measurement is the
next one's baseline.

## 7. What this note does not decide

The store's format and retrieval beyond "keyed by Calliope's facts, not by embeddings". The lesson-mining
method (ExpeL) and the prompt optimiser (GEPA). The user-facing agent. Any change to the check or the guide.

## 8. Owner questions

Recommendations follow the review (§9).

- **Q1 — Use.** Is the Calliope-run agent for batch and evaluation only, with HIMARI kept as the user's host?
  Recommended: yes, a user-facing agent later.
- **Q2 — Who writes the record.** Recommended: both, as §3.1 lays out. The runner writes the agent layer, the
  server writes the tools layer, and the two are joined by `run_id`.
- **Q3 — Answers in the record.** Recommended: in full in RX1–RX4, with a size cap and a digest an answer;
  revisit in RX5.
- **Q4 — Sets.** Recommended: the four games are development data (Train, Validation for now). New games for
  Validation and Test: which, and how many?
- **Q5 — The reference for M2b.** Recommended: the judge drafts each fixed moment's key causes and the owner
  reviews them.
- **Q6 — The writer model.** Recommended: luna as in the trials; other low-cost models only after RX2's
  baseline.

## 9. Review dispositions — rev. 1 (`a049dbe`), independent review: READY_WITH_CORRECTIONS

| Item | Finding | Disposition |
| --- | --- | --- |
| B1 | M2 counted uncited reasons. Citing is not explaining, and a cause explained differently from the reference is not an omission | Applied: M2a evidence coverage (automatic) and M2b explanation coverage (judge with owner-reviewed cases), §4.2; Q5 |
| B2 | M3's "`same_reply` not read" cannot be observed: the default `ply` digest serves `board.same_reply` | Confirmed in `agent/board.py`. Applied: Available, Used, Explained per reason kind; "Used" claims no internal reading, §4.2 |
| B3 | A server-only record misses prompts, model responses, tokens and the run's end | Applied: two layers joined by `run_id`, size cap, digests, a sensitive-data rule, §3.1; Q2 |
| B4 | The four games shaped v1–v8, so they are not independent, and one held-out set drifts under many candidates | Applied: Train, Validation, Test; the four games as development data; RX0 states runs, variance and the smallest effect, §4.1; Q4 |
| B5 | "A checkable lesson becomes a check" mixed verification with tool strategy, and the check does not verify a cited item's every meaning | Applied: §2.1 splits verification (check or judge) from strategy (the store); the store holds strategy only |
| N1 | A retry on the check's refusal is not Reflexion | Applied: RX3 is "bounded retry on the check's refusal"; diagnosis begins in RX4, §3, §6 |
| N2 | The evaluator's tools change state; the lesson writer and the judge should be apart | Confirmed in `agent/session.py` (`explore` takes budget and runs engine work). Applied: §5 items 2 and 5 |
| §4 | Control arms are needed to tell the store's effect from a retry's | Applied: arms A–D, §4.3; packets RX2–RX4 and "later" name their arm, §6 |
