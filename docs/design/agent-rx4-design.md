# Agent RX4-D — learning from failures: arm B, lessons (D, D-min), then the critic (C)

Status: **design, rev. 2, for independent re-review. Owner questions are in §9. Independent review of rev. 1
(`2b5ec34`): NOT_READY (B1–B3; N1–N3), applied, §10.** Date: 2026-11-06.
Base: `main @ 179f226` (RX2 merged, PR #143: the baseline, its evidence).
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

### 2.3 Writing and checking the set (review B3)

A lesson is kept or dropped on its own evidence; the set is then checked as a whole. Both checks judge B and D
**together, blind, in one judging**, never against RX2's judging (judges differ, RX0-D §7.2).

1. **Candidates.** The evaluator proposes up to 12 candidate lessons from the Train failures. Each names its
   **source moments** (the Train moment-runs whose failure it answers) and the condition that holds there.
2. **Screening, one lesson at a time.** For each candidate, arm D runs with **that lesson alone** on the Train
   games of its source moments, one run a game, and arm B runs on the same games beside it. One judging holds
   every screening run of B and D. A candidate is **kept** when, on its source moments, D − B is positive on
   decisive causes explained (M2b) or on requested evidence fetched (M3 `request_fetched`), and D has no wrong
   sentence that B does not. It is **dropped** otherwise. A candidate whose condition never held in its runs
   (the agent never met the situation) is dropped too, and so recorded. The screening is an inexpensive
   filter on few runs, not a proof: its result keeps or drops, it promotes nothing.
3. **The set.** The kept candidates, at most 8 (by their M2b gain on their sources when more than 8 are
   kept), make `lessons_v1`. It is checked as a whole on Train: B and D(`lessons_v1`), three runs a game,
   interleaved (§3), one blind judging. The set goes forward if D − B on Train is not negative on M2b and has
   no paired M1b regression of 2 per 100 or more.
4. **Approval.** `lessons_v1` with every candidate, its screening and the set's check goes to the owner, who
   approves it before any Validation run (framing §5).
5. **D-min.** `lessons_min_v1` is written the same way from **A-min's** Train failures by a separate evaluator
   session, screened against A-min, and never enters D's set (RX0-D §8).

### 2.4 How a lesson reaches the agent

The runner's `lessons(arm)` hook (RX1-D §4.4) appends the set to the system prompt after the guide, under a
heading that says these are strategies for situations, with each lesson's condition first. The guide stays
`commentary_ko_v8` (frozen). The `start` line records the set's id and every lesson's id (RX0-D §4.3).

## 3. The runs (RX4a)

### 3.1 One budget for the arms compared (review B1)

Measuring a bound and comparing arms are two steps. D may need more turns and calls than A did: that is what a
lesson asking for `explore` is for (RX2 §9 Q3). But D − B is a fair test of the lessons only if B and D ran
under the **same** bounds.

1. **Measure D's need on Train.** The set check of §2.3 step 3 runs D(`lessons_v1`) on Train with RX1's starting
   bounds (turns 60, tool calls 120, tokens 2 M, 1800 s). Its 95th percentile plus 50% gives D's bounds, as RX2
   §8 did for A; censoring is reported, and more than 5% censored doubles the bound and runs those again
   (RX2-D §6).
2. **One bound for the comparison.** The Validation bounds are the larger of D's and RX2's (turns 27, tool
   calls 48, tokens 1.24 M, 525 s), each limit separately. **B and D both run on Validation under them.**
3. **A from RX2.** B − A uses RX2's `rx2-2` A runs. No A run reached RX2's bounds, so none would have run
   differently under the larger ones; the report says so. The same holds for A-min against D-min.

### 3.2 The runs

| Step | Arms | Set | Runs a game | Runs | Bounds |
| --- | --- | --- | ---: | ---: | --- |
| Screening (§2.3 step 2) | B, D(one lesson) | Train, the source games | 1 | about 2 × 12 × 2 | RX1's starting bounds |
| Set check (§2.3 step 3) | B, D(`lessons_v1`) | Train | 3 | 24 | RX1's starting bounds (D's need, §3.1) |
| D-min screening and set check | A-min, D-min | Train | as above | about 60 | RX1's starting bounds |
| **The comparison** | **B, D(`lessons_v1`)** | **Validation** | **3** | **24** | **§3.1 step 2, the same for both** |

- **Interleaved** (review N1). In every batch, the arms compared run in turn, game by game and repeat by
  repeat (B, D, B, D …), so a change in the provider's behaviour over the batch falls on both.
- **D inherits B** (review N2). D and D-min are B (and A-min with the same retry) with lessons: the runner's
  retry on a refused submission (RX1-D §4.3) applies to B, D and D-min alike, and `lessons(arm)` returns the
  set for D and D-min only. Acceptance: the same refused answer given to B and to D produces the same retry
  message, and only D's system prompt carries the lessons.
- Cost: about $2.5 for every RX4a run (about 160 runs at RX2's $0.016), D's explores aside.

## 4. The judging (review B2)

The bundle's part size becomes a setting of `python -m tools.rx bundle` (`--moments-per-part`, RX2's 6 the
default) instead of the constant `PART_MOMENTS`. With three arms on a moment, RX4a uses **4 moments a part**, so
a part holds 4 × 3 arms × 3 runs = 36 commentaries, the size RX2's judges handled.

| Judging | Arms | Set | Commentaries | Parts of 4 moments |
| --- | --- | --- | ---: | ---: |
| Screening | B, D(one lesson) | Train source moments | as run | parts of at most 36 |
| Set check | B, D(`lessons_v1`) | Train | 72 | 3 (two arms: 4 × 2 × 3 = 24 a part) |
| **The comparison** | **A (RX2's), B, D** | **Validation** | **108** | **3** |
| Calibration | A, A-min (RX2's), D-min | Train | 108 | 3 |

`judge_v1` and `references_v1` are unchanged. Each part is judged by a fresh session in its own directory and
audited as RX2 (outside the directories, at a separator). The report refuses a part that is not checked
(RX2's `checked_judgings`).

## 5. What counts

All comparisons paired by moment, on the arm's three runs a moment (RX2 §6).

| Question | Comparison | Confirmed when |
| --- | --- | --- |
| Does the retry help? | B − A, Validation | reported; no promotion rides on it |
| **Do the lessons help?** | **D − B, Validation** | **M2b decisive +10 points or more, interval above zero**, and no regression: M1b (paired, RX2 implementation §6) not worse by 2 per 100 or more, M4 not lower beyond its interval |
| Do they fetch what was never fetched? | D's M3 for `on_request` decisive causes, Validation | reported (0 of 6 on Validation, 0 of 9 in all, in A and A-min) |
| Does the loop find a known gap? | D-min − A-min against A − A-min, Train | the share of A's +12 points M2b that D-min recovers (calibration; never promotes) |

A lesson set that is confirmed is marked **`PROMOTED`** in RX4 (review N3): `lessons_v1` is kept with its content,
its versions (tools, digest, guide), its sources, its screening, its set check and its Validation result. RX5
registers it as the lesson store's first entry and builds its retrieval; RX4 builds no store. A set that is not
confirmed is kept with its results, marked `NOT_PROMOTED`, and is not used.

## 6. RX4b: the critic (C), decided later

C needs, per moment-run, a critic that reads the commentary and its reference and returns structured
feedback (framing §3.2), up to K = 2 rounds. On Validation that is up to 72 critic calls. Three things are left
for RX4b, after RX4a's result:

- the critic's model and its cost (§9 Q2);
- whether the critic sees the reference's key causes (it would then teach to the test: recommended no; it
  sees the digest and the commentary only);
- whether C is still needed: if D closes the gap, C is not run.

## 6.1 Carried from RX2's review

- **P2 by content** (RX2 implementation §10.2, N4). Before RX4 reads P2 (scores alone) as a result, P2 judges
  each cited proposition by its content: a score or a grade alone, against a line's moves or a claim's
  mechanism. Until then P2 is reported as "by the kinds of handles" and no conclusion rides on it.
- **Related use is the measure of testing.** RX2 found related use 0 in every arm (no `explore`, no
  `judge_move` testing an item) and decisive causes not used were never explained. D's M3 reports related use
  beside `request_fetched`, so a lesson that makes the agent test, and not only cite, shows in the record.

## 7. What RX4 does not do

No change to the guide (E), the check or the references. No Test. No lesson store or retrieval (RX5).

## 8. Packet's acceptance

- The evaluator's transcript audited; `lessons_v1` and `lessons_min_v1` with every candidate, its checks and its
  sources; the owner's approval of `lessons_v1`.
- Every run whole; every judging audited and checked; the report with §5's table, the bounds of §3.1 and their
  censoring, and cost; the runner's retry shared by B, D and D-min (§3.2); the new evidence in
  `rx-evidence/rx4/`.

## 9. Owner questions

- **Q1 — Lessons before the critic.** RX4a (B, D, D-min) first, the critic (C) only if needed. Recommended: yes.
- **Q2 — The critic's model, if C is run.** A Claude model through OpenRouter (the same key), roughly $5–20 for
  C's batch depending on the model, or a fresh Claude session per run by hand (slow). Recommended: decide after
  RX4a.
- **Q3 — Approving the lesson set.** The owner reads `lessons_v1` (at most 8 short lessons) before it runs on
  Validation. Recommended: yes.

## 10. Review dispositions — rev. 1 (`2b5ec34`), independent review: NOT_READY

| Item | Finding | Disposition |
| --- | --- | --- |
| B1 | B ran under RX2's bounds and D under RX1's larger ones, so a D − B gain could be the budget, not the lessons | Applied: §3.1, D's need measured on Train (the set check), then B and D on Validation under one bound (the larger of D's and RX2's, limit by limit); A and A-min from RX2, none of whose runs reached RX2's bounds |
| B2 | Six parts of 36 do not follow from the code's 6 moments a part with three arms (54 a part) | Confirmed (`PART_MOMENTS = 6` in `tools/rx/judge.py`). Applied: §4, the part size a setting of `bundle`, 4 moments a part for three arms (36 a part), a table of every judging |
| B3 | A set run as a whole cannot tell which lesson helped; a new judging compared with RX2's mixes judges | Applied: §2.3, each candidate screened alone on its source games against B in one judging (kept or dropped by its own result), then the set checked as a whole against B in another; never compared with RX2's judging |
| N1 | B and D should run interleaved | Applied: §3.2, every batch alternates the arms compared, game by game, repeat by repeat |
| N2 | The runner retries only for `arm == "B"` and has no D | Confirmed in `tools/rx/run.py`. Applied: §3.2, the retry for B, D and D-min alike, lessons for D and D-min only, an acceptance test |
| N3 | §5 promotes to a store that §7 leaves to RX5 | Applied: §5, RX4 marks `lessons_v1` `PROMOTED` with everything it rests on; RX5 registers and retrieves |
