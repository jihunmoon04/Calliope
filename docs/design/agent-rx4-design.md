# Agent RX4-D — learning from failures: arm B, lessons (D, D-min), then the critic (C)

Status: **design, rev. 1, for independent review. Owner questions are in §9.** Date: 2026-11-05.
Base: `agent/rx2 @ e66f48e` (RX2: the baseline, its evidence).
Inputs: [`agent-reflection-framing.md`](agent-reflection-framing.md) (§2 the ladder, §3.2 the two loops, §5 the
critic, evaluator and judge), [`agent-rx0-design.md`](agent-rx0-design.md) (the contract: §7 comparisons, §8 the
arms), [`agent-rx2-design.md`](agent-rx2-design.md) §11 (A1–A3), [`agent-rx2-implementation.md`](agent-rx2-implementation.md)
(the baseline), [`rx-evidence/`](rx-evidence/README.md).

## 0. What the baseline asks of RX4

RX2 measured arm A and found (RX2 implementation §7):

1. the decisive key cause is carried to its outcome in about half the commentaries (50% on Validation);
2. a decisive cause whose evidence the agent must fetch was **never** fetched (0 of 9 moment-runs, both arms and sets), as in every trial;
3. the guide v8 beats the min guide on Train, the games it was tuned on, and not on Validation;
4. facts are rarely wrong (0.5–2 per 100), and refusals are corrected within each run;
5. paired by moment, four games and three runs confirm about ±8 points of M2b and ±0.2 of M4.

So RX4 aims at (1) and (2), measures on Validation only for promotion (3), watches (4) for regressions, and
compares arms paired by moment (5). **RX3 is folded in** (owner, 2026-11-05): arm B (the bounded retry, RX1-D
§4.3) is run as RX4's base arm, not as a packet of its own. Finding (4) predicts B ≈ A.

## 1. The order

| Step | Arms | Why first |
| --- | --- | --- |
| **RX4a** | B; D (lessons written by hand from Train); D-min (lessons from A-min's Train failures) | cheap (no critic at run time), the deployable path (lessons need no critic for users), aims straight at finding (2) |
| **RX4b** | C (the critic in the loop) | needs a critic model and its cost (§9 Q2); run only if RX4a's lessons leave a gap a critic could close |

The rest of this document designs RX4a and fixes what RX4b must decide.

## 2. The evaluator and the lessons (RX4a)

### 2.1 What the evaluator reads

A fresh Claude session (the evaluator, framing §5) reads **Train only**:

- RX2's judged Train commentaries of arm A (`rx-evidence/rx2/commentaries.md` filtered to Train, and the
  judging's `judging.json` with its key): each moment's decisive cause with its verdict (explained, partly,
  not), the wrong sentences and why;
- the Train run records of those runs (tool calls, `shown`, submissions), from the raw archive or WSL;
- the Train references with their key causes and routes;
- Calliope's tools, in a data directory of its own (framing §5 item 5), to check a cure before proposing it.

It never sees a Validation or Test game, reference, record or commentary. Its brief names the Train files
only, and its transcript is audited like a judge's (RX2-D §5.1, outside its directories).

### 2.2 What a lesson is

A lesson is **strategy**, never a fact about a game (framing §2.1). Its fields (framing §5 item 3):

```json
{"id": "L01", "condition": "…when the situation holds, in terms of what ply shows…",
 "action": ["explore …", "…"], "success": "…what the submission must then cite or say…",
 "fallback": "…what to say if the action does not show it…", "versions": {"tools": "…", "digest": "…", "guide": "commentary_ko_v8"},
 "source": ["<run>:<ply>", "…"]}
```

- **Condition** in terms of what the agent sees (grade, the lines' material, `board` kinds, claim statuses),
  never a game, move or square of Train. A lesson that names one is refused.
- **Action** in tool calls that exist (`explore`, `facts`, `judge_move`, `detail`), with what to pass.
- **Short.** At most 400 characters a lesson in Korean; at most **8 lessons** in a set.
- The lessons the baseline points at (findings 1, 2), as examples of the shape, not as the set:
  - when the move's grade is not explained by the engine line's material (`material_*` inconclusive, or the
    line ends level), play the game's own continuation with `explore` from the ply and say what it led to;
  - when a capture or a piece left to be taken decides the grade, play it out with `explore` and give the
    evaluation where it happens (RX2-D A2's rule, as a strategy for the agent);
  - say the decisive cause first and carry it to its outcome (material with its count, mate, or that nothing
    is won); a fact that leads nowhere is left out.

### 2.3 Writing and checking the set

1. The evaluator proposes up to 12 candidate lessons from the Train failures, each with its source moments.
2. **Checked on Train by re-run** (framing §5 item 2, writing is not judging): arm D runs the candidate set on
   the failing Train moments (one run a game), and the evaluator keeps a lesson only if its source failures
   improve and nothing it touches gets a new wrong sentence. The check's judging is by a judge session, not by
   the evaluator.
3. The surviving set (at most 8) is frozen as `lessons_v1` with its candidates and checks kept, and goes to the
   owner. The owner approves the set before Validation (framing §5).
4. D-min's set, `lessons_min_v1`, is written the same way from **A-min's** Train failures, by a separate
   evaluator session, and never enters D's set (RX0-D §8).

### 2.4 How a lesson reaches the agent

The runner's `lessons(arm)` hook (RX1-D §4.4) appends the set to the system prompt after the guide, under a
heading that says these are strategies for situations, with each lesson's condition first. The guide stays
`commentary_ko_v8` (frozen). The `start` line records the set's id and every lesson's id (RX0-D §4.3).

## 3. The runs (RX4a)

| Arm | Set | Runs a game | Runs | Guide | Lessons |
| --- | --- | ---: | ---: | --- | --- |
| B | Validation | 3 | 12 | v8 | — |
| D | Validation | 3 | 12 | v8 | `lessons_v1` |
| D-min | Train | 3 | 12 | min | `lessons_min_v1` |

- A and A-min are not run again: RX2's `rx2-2` runs are the baseline, and their commentaries are judged again
  in RX4a's judging (§4), so every comparison is within one judging (RX0-D §7.2).
- **Bounds** (RX2 §9 Q3): B uses RX2's fixed bounds (turns 27, tool calls 48, tokens 1.24 M, 525 s). D and D-min
  run their first batch with RX1's starting bounds (60, 120, 2 M, 1800 s); their bounds are then fixed the same
  way (95th percentile plus 50%), with censoring reported.
- Cost: about $0.6 (36 runs; D may cost more for its explores).

## 4. The judging

One judging, `judge_v1` unchanged, references `references_v1` unchanged:

- **Validation**: A (RX2's `rx2-2`), B and D; 3 arms × 12 runs × 3 moments = 108 commentaries;
- **Train**: A, A-min (RX2's) and D-min; 108 commentaries.

Parts of at most six moments holding every arm of those moments (RX2-D §5.3): six parts of 36, two judged
apart for each set as before. The audit as RX2 (outside the directories).

## 5. What counts

All comparisons paired by moment, on the arm's three runs a moment (RX2 §6).

| Question | Comparison | Confirmed when |
| --- | --- | --- |
| Does the retry help? | B − A, Validation | reported; no promotion rides on it |
| **Do the lessons help?** | **D − B, Validation** | **M2b decisive +10 points or more, interval above zero**, and no regression: M1b (paired, RX2 implementation §6) not worse by 2 per 100 or more, M4 not lower beyond its interval |
| Do they fetch what was never fetched? | D's M3 for `on_request` decisive causes, Validation | reported (0 of 6 on Validation, 0 of 9 in all, in A and A-min) |
| Does the loop find a known gap? | D-min − A-min against A − A-min, Train | the share of A's +12 points M2b that D-min recovers (calibration; never promotes) |

A lesson set that is confirmed is **promoted** to the lesson store's first version (RX5 builds the store and its
retrieval). One that is not confirmed is kept with its result and is not used.

## 6. RX4b: the critic (C), decided later

C needs, per moment-run, a critic that reads the commentary and its reference and returns structured
feedback (framing §3.2), up to K = 2 rounds. On Validation that is up to 72 critic calls. Three things are left
for RX4b, after RX4a's result:

- the critic's model and its cost (§9 Q2);
- whether the critic sees the reference's key causes (it would then teach to the test: recommended no; it
  sees the digest and the commentary only);
- whether C is still needed: if D closes the gap, C is not run.

## 7. What RX4 does not do

No change to the guide (E), the check or the references. No Test. No lesson store or retrieval (RX5).

## 8. Packet's acceptance

- The evaluator's transcript audited; `lessons_v1` and `lessons_min_v1` with every candidate, its checks and its
  sources; the owner's approval of `lessons_v1`.
- 36 runs whole; the judging audited; the report with §5's table, censoring and cost; the new evidence in
  `rx-evidence/rx4/`.

## 9. Owner questions

- **Q1 — Lessons before the critic.** RX4a (B, D, D-min) first, the critic (C) only if needed. Recommended: yes.
- **Q2 — The critic's model, if C is run.** A Claude model through OpenRouter (the same key), roughly $5–20 for
  C's batch depending on the model, or a fresh Claude session per run by hand (slow). Recommended: decide after
  RX4a.
- **Q3 — Approving the lesson set.** The owner reads `lessons_v1` (at most 8 short lessons) before it runs on
  Validation. Recommended: yes.
