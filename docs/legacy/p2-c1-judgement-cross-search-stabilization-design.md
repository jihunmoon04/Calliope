> **LEGACY — FROZEN, NOT THE CURRENT DESIGN.** This document describes the MVP-era implementation preserved at tag `legacy-mvp-g0`. It is kept only as historical reference for the redesign; nothing in it is a current requirement or decision. Current design: [`docs/design/`](../design/README.md). Index: [`docs/README.md`](../README.md).

# P2-C1 — Judgement Cross-Search Inversion Stabilization

Status: **IMPLEMENTED / MERGED**

Baseline:

```text
main @ a6dae11afa45aa143e750d200e77940e3646302c
```

This is a post-G0 stabilization packet.

Implementation baseline:

```text
main @ 713350f20f07e81a95f38d6cc7ad8b2b60811a5d
```

It changes P2 judgement orchestration only. It does not reopen P8-P12 or the G0 public trust chain.

---

## 1. Problem before P2-C1

The current public move path obtains two judgement observations:

1. one unrestricted base-position MultiPV analysis;
2. one single-root analysis restricted to the played move.

If the played move is outside the initial MultiPV, `MoveJudge` compares:

```text
initial MultiPV best score
vs
separately searched played-move score
```

These scores come from different search trees.

Because the second search runs later in the same request/session, it may benefit differently from
the existing transposition table and search history.

A legal played move can therefore appear to score better than the earlier MultiPV best even though
the observations are not directly comparable.

Before P2-C1, P2 treated an inversion beyond the fixed noise tolerance as incompatible and failed
the request.

Known reproduction:

```text
FEN:
r1b2rk1/pp3p1p/3n2p1/3BR3/5QP1/P4N1P/1q4PK/3R4 w - - 1 26

played:
f4h6
```

Observed at depth 12 in the existing request session:

```text
initial MultiPV best Re3: +588
separate Qh6 search:      +622
inversion:                 34 cp
cp noise tolerance:        20 cp
```

Pre-P2-C1 result:

```text
IncompatibleAnalysisError(
    "played move scores better than best beyond noise"
)
```

The position has effectively saturated WDL for the mover, so this cross-search cp inversion does
not establish a meaningful move loss.

---

## 2. Root cause

This is not a G0 explanation failure.

It occurs before P4-P12, inside the P2 judgement boundary.

The current `MoveJudge` is intentionally pure:

```text
normalized EngineAnalysis values
 -> MoveJudge
 -> MoveJudgement
```

It owns no engine and must remain pure.

Therefore the repair must separate:

- **detection/policy** — `MoveJudge`;
- **conditional engine re-observation** — application orchestration.

Do not put engine calls inside `MoveJudge`.

---

## 3. Goals

P2-C1 must:

1. stop treating cross-search score inversion as an unrecoverable error when the played move is
   outside the initial MultiPV;
2. compare the initial reference-best move and played move in one shared restricted search;
3. perform that extra search only when the existing observations cross the current inversion
   tolerance;
4. keep the extra search inside the same G0 request-wide Stockfish session;
5. preserve one process, one request token and no mid-request reset;
6. preserve the original MultiPV basis for rank and forcedness;
7. avoid falsely promoting an unranked played move to global BEST;
8. leave all normal/non-inverted judgement behavior unchanged;
9. leave P8-P12 semantics unchanged.

---

## 4. Non-goals

P2-C1 does not:

- increase the 20 cp tolerance;
- change expected-score thresholds;
- clear Hash or issue a mid-request `ucinewgame`;
- change the public `AnalysisBudget` contract;
- add public reconciliation metadata;
- change schema 0.2 DTO shape;
- change G0 request serialization;
- change P7 settings;
- change P8/P9 eligibility;
- change P10 claims;
- change P11 selection;
- change P12 wording;
- implement engine stability sampling generally;
- guarantee a result for every possible engine contradiction.

Mate/result-class contradictions remain fail-closed unless explicitly covered below.

---

## 5. Trigger scope

Reconciliation is eligible only when all of these are true:

```text
played move is NOT present in initial position_analysis.lines
AND
the played single-root analysis is otherwise compatible
AND
normal non-mate score comparison produces a negative loss beyond current tolerance
```

The initial MultiPV already owns direct same-search comparisons for moves present in it.

Therefore:

- rank 1 -> no reconciliation;
- rank 2+ -> no reconciliation;
- played outside MultiPV, no inversion -> no reconciliation;
- played outside MultiPV, inversion within current tolerance -> existing zero-loss clamp, no
  reconciliation;
- played outside MultiPV, cp or expected-score inversion beyond tolerance -> reconciliation;
- mate/result-class contradiction -> existing fail-closed policy, no automatic P2-C1 recovery.

This keeps P2-C1 specific to **cross-search numeric inversion**, not every
`IncompatibleAnalysisError`.

---

## 6. Typed retry signal

Introduce a dedicated internal error subtype:

```python
class CrossSearchInversionError(IncompatibleAnalysisError):
    """Separate played-move search outranked the initial reference best beyond noise."""
```

It is a control signal between the pure judge and `AnalyzeMoveService`.

It may be raised only for the eligible cross-search numeric inversion described in §5.

Do not catch or reinterpret generic `IncompatibleAnalysisError`.

Direct/internal callers of `MoveJudge` may observe this subtype; the canonical application path
must catch it once and attempt the frozen reconciliation.

---

## 7. Conditional paired reanalysis

When `AnalyzeMoveService` catches `CrossSearchInversionError`, while still inside the current
request-wide engine session, run exactly one additional judgement analysis:

```python
reference_best = position_analysis.best_line.first_move

paired_settings = replace(
    judgement_settings,
    multipv=2,
)

comparison_analysis = engine.analyze(
    position,
    paired_settings,
    root_moves=(reference_best, played_move),
)
```

Required properties:

- same immutable base position;
- same engine;
- same depth/nodes/time limit as the judgement request;
- same `threads=1`;
- same `hash_mb=16`;
- `multipv=2`;
- roots are exactly the initial reference-best move and played move;
- same request session/game token;
- no reset/hash clear;
- at most one reconciliation analysis per public request.

The root tuple order is canonical:

```text
(initial reference best, played move)
```

Engine output rank may reorder those two moves; root tuple order is not a ranking assertion.

---

## 8. MoveJudge reconciliation API

Keep `judge()` as the normal pure entry.

Add one explicit pure reconciliation entry, for example:

```python
MoveJudge.judge_reconciled(
    *,
    mover,
    move,
    position_analysis,
    played_analysis,
    comparison_analysis,
) -> MoveJudgement
```

Do not make `MoveJudge` call the engine.

`judge_reconciled()` must rerun all compatibility checks relevant to the original analyses and
must additionally validate the paired observation.

### Retry-signal rule

`CrossSearchInversionError` belongs only to the **initial** `judge()` attempt.

`judge_reconciled()` must **never raise `CrossSearchInversionError`**.

It has only two outcomes:

```text
valid paired reconciliation -> MoveJudgement
invalid/contradictory paired package -> ordinary IncompatibleAnalysisError
```

This structurally caps reconciliation at one application-owned retry.

### Paired observation validation

Require:

- same `position_id`;
- same `EngineIdentity`;
- same engine limit;
- same thread count;
- same hash size;
- `multipv == 2`;
- exactly two contiguous lines with ranks 1 and 2;
- candidate UCI set exactly:
  ```text
  {initial_reference_best, played_move}
  ```
- played move was not already in the original MultiPV;
- the original invocation really represents the cross-search case.

Malformed/mismatched reconciliation input remains ordinary `IncompatibleAnalysisError`.

---

## 9. Authority after paired search

The paired search becomes the authority **only for the best-vs-played loss comparison**.

The original unrestricted MultiPV remains authority for:

- original reference-best move identity;
- played move's public rank (`None`);
- global candidate set;
- forcedness;
- best-to-second gap;
- P9 representative alternatives.

This avoids turning a two-root experiment into a claim about the whole legal-move space.

---

## 10. Reconciled assessment policy

The paired comparison reuses the existing `MoveJudge` assessment semantics.

The intended implementation is one reconciliation variant of the existing `_assess` path:

- same mover POV;
- same WDL-preferred grading rule;
- same cp thresholds;
- same expected-score thresholds;
- same mate handling through `_mate_quality`;
- same quality vocabulary.

The **only numeric policy difference** is that negative non-mate losses are floored to zero
instead of producing another retry signal or incompatibility.

For ordinary cp/WDL values:

```text
cp_loss = max(0, reference_best_cp - played_cp)

expected_score_loss = max(
    0,
    reference_best_expected_score - played_expected_score,
)
```

If WDL is available, quality remains governed by expected-score loss exactly as today.
Otherwise quality is governed by cp loss.

### If paired search ranks played above the reference best

Do **not** promote the played move to BEST.

A paired two-root search proves only that the old reference-best-vs-played ordering is unstable; it
does not prove the played move is rank 1 among all legal moves.

Negative paired numeric loss is therefore floored to zero.

With authoritative loss zero, the maximum reconciled quality is:

```text
EXCELLENT
```

not BEST.

Thus a numeric paired inversion may yield:

```text
rank = None
best_move = original MultiPV best move
cp_loss = 0
expected_score_loss = 0.0   # when WDL is available and non-negative floor applies
quality = EXCELLENT
```

If the paired comparison instead shows positive loss, use the existing grading thresholds.

### Mate values are not floored

If either paired score enters mate/result-class semantics, do **not** apply the numeric floor
above. Use the existing `_mate_quality` path unchanged.

Any mate/result-class contradiction remains ordinary `IncompatibleAnalysisError`.

This makes §10 and §12 one policy: paired reconciliation changes only negative **numeric** loss
handling; mate semantics stay exactly as before.

---

## 11. Score fields after reconciliation

For a reconciled judgement:

- `best_move` remains the original unrestricted MultiPV rank-1 move;
- `best_score` is the paired-search score for that reference-best move;
- `played_score` is the paired-search score for the played move;
- `rank` remains `None`.

Therefore `best_score` means **the current authoritative score observation of the move retained
as the original global reference best**.

In the rare case where the paired search ranks the played move above that reference move,
`played_score` may numerically exceed `best_score`; the zero-loss/EXCELLENT policy records that
the original data no longer proves a loss without falsely claiming global BEST.

No score is fabricated or overwritten merely to make ordering look monotonic.

---

## 12. Mate/result-class behavior

P2-C1 is not a mate reconciliation feature.

`judge_reconciled()` evaluates paired mate values using the existing `_mate_quality` policy.

If the original or paired package enters an existing mate/result-class contradiction such as:

- played mate for mover contradicts non-mate best;
- played mate is faster than reference-best mate;
- played escapes a forced loss;
- played loses later than the supposed best;

raise ordinary `IncompatibleAnalysisError`.

Never convert such a contradiction to `CrossSearchInversionError`, never floor a mate
contradiction to zero, and never perform another paired retry.

These mate/search-order contradictions remain a known post-P2-C1 limitation.

---

## 13. Application orchestration

The G0 move path becomes:

```text
request validation
FEN/move validation

request-wide engine session
  1. unrestricted position MultiPV
  2. played single-root analysis

  try:
      judgement = MoveJudge.judge(...)
  except CrossSearchInversionError:
      3. paired roots=(initial_best, played), MultiPV 2
      judgement = MoveJudge.judge_reconciled(...)
      # no second catch / no retry loop

  P4-P11 using the resulting MoveJudgement
release session

optional P12
projection
```

The application catches `CrossSearchInversionError` **only around the first `judge()` call**.

After the paired engine observation, it calls `judge_reconciled()` without any retry-signal
catch. Any error from reconciliation propagates normally.

Therefore the third judgement engine call is conditional and the total reconciliation count is
structurally capped at one.

Normal G0 requests still use the existing two judgement calls.

Reconciliation occurs before P4-P11, so all downstream explanation stages see one final
`MoveJudgement`.

---

## 14. Downstream semantics

P8/P9 route from the **final reconciled quality** exactly as they route any ordinary judgement.

The original `position_analysis` remains the P9 candidate/alternative basis.

P2-C1 does not add a new explanation family or evidence form.

For example, a reconciled zero-loss move outside the original MultiPV may become EXCELLENT and
therefore enter P9. Under the frozen P9 mode rule:

```text
BEST + ForcednessLevel.ONLY_MOVE -> ONLY_MOVE_CANDIDATE
otherwise                         -> STRONG_MOVE
```

a reconciled EXCELLENT move remains STRONG_MOVE even if the original MultiPV forcedness is
`ONLY_MOVE`.

This is intentional.

### Forcedness reconciliation boundary

Forcedness remains computed exclusively from the original unrestricted MultiPV.

Therefore it is possible to observe:

```text
quality = EXCELLENT
rank = None
forcedness = ONLY_MOVE
```

after reconciliation.

This is not newly contradictory state: an out-of-MultiPV move already could be clamped to zero
loss within the original noise tolerance while forcedness remained based on the original MultiPV.

P2-C1 does not reinterpret forcedness from the two-root paired experiment.

Add a unit test that pins this case and proves P9 uses STRONG_MOVE rather than
ONLY_MOVE_CANDIDATE.

P9 may then produce a verified explanation or valid strict silence under its existing contract.

No G0 layer catches a later explanation error merely because reconciliation occurred.

---

## 15. Metadata and public schema

No public schema change.

Keep:

```text
PUBLIC_SCHEMA_VERSION = "0.2"
```

Do not add:

- reconciliation flag;
- extra engine call count;
- game token;
- TT/reset state;
- paired-search raw lines;

to public metadata.

The existing analysis metadata continues to describe the caller's judgement settings, not every
internal conditional observation.

---

## 16. G0 session and mode invariants

P2-C1 must preserve:

- one Stockfish process;
- one request session/token;
- no mid-request reset;
- complete concurrent-request serialization;
- exception-safe session release;
- P12 outside the session;
- STRUCTURED/COMMENTARY identical P0-P11 work.

For a fixture that triggers reconciliation, both output modes must perform the same three
judgement calls before any P7 work.

---

## 17. Unit gates

### MoveJudge

Add deterministic unit coverage for:

1. played outside MultiPV + cp inversion > tolerance -> `CrossSearchInversionError`;
2. played outside MultiPV + expected-score inversion > tolerance -> same typed retry;
3. inversion within tolerance -> existing zero-loss path, no retry signal;
4. played already in MultiPV -> no retry signal;
5. same-search contradiction remains hard `IncompatibleAnalysisError`;
6. mate contradiction remains hard `IncompatibleAnalysisError`;
7. valid paired analysis with played worse -> existing grading thresholds;
8. valid paired analysis with played better -> loss 0, maximum EXCELLENT, never BEST;
9. paired WDL better -> expected loss 0, EXCELLENT;
10. invalid paired position/engine/settings/roots/ranks -> `IncompatibleAnalysisError`;
11. rank remains None;
12. forcedness remains exactly the original MultiPV forcedness.

### Application

Use fakes/spies to prove:

- normal request -> 2 judgement calls;
- eligible inversion -> exactly 3 judgement calls;
- third settings are original limit + `multipv=2`;
- roots exactly `(initial_best, played)`;
- third call remains inside the same request session;
- no new request token/reset;
- only `CrossSearchInversionError` triggers reconciliation;
- generic `IncompatibleAnalysisError` propagates unchanged;
- paired-engine failure propagates;
- reconciled judgement is passed to P4-P11;
- STRUCTURED/COMMENTARY perform identical reconciliation work.

---

## 18. Real regression gate

Preserve the known real fixture:

```text
FEN:
r1b2rk1/pp3p1p/3n2p1/3BR3/5QP1/P4N1P/1q4PK/3R4 w - - 1 26

move:
f4h6
```

Use the production public facade with exactly:

```python
AnalysisBudget(depth=12, multipv=3)
```

for the judgement request.

Do not use the public default MultiPV 5 for this regression: on the reviewed Stockfish 19 run,
MultiPV 5 did not reproduce the cross-search inversion and therefore would not exercise the
recovery path.

Run the real regression in **both**:

```text
OutputMode.STRUCTURED
OutputMode.COMMENTARY
```

and require identical P0-P11 judgement/reconciliation work.

### Qualifying real run

For each mode, an observational spy must prove:

- initial judgement budget is depth 12 / MultiPV 3;
- the played move is outside the initial MultiPV;
- the separate single-root played observation numerically outranks the initial reference best
  beyond the configured tolerance;
- exactly one paired MultiPV-2 judgement call is added;
- roots are initial reference best + `f4h6`;
- all three judgement observations remain in one request session/game token;
- no extra `ucinewgame`;
- the request no longer fails with the old cross-search inversion;
- final judgement has `rank is None`;
- final judgement is never BEST solely because of reconciliation;
- the request continues into the ordinary strict explanation path.

The loss values must be recomputed from the **observed paired EngineLine values** and compared with
the frozen §10 policy.

Do not hard-code historical cp values such as +588/+622 or the reviewed paired +593/+575 as
correctness requirements. They are reproduction evidence, not stable semantic outputs.

### Which branch the real fixture covers

On the reviewed Stockfish 19 run, the paired search restored the ordinary ordering:

```text
reference best > played
```

so the real fixture covers the **positive paired-loss** branch.

The separate branch:

```text
paired played > reference best
 -> numeric negative loss floored to zero
 -> at most EXCELLENT
```

must be proven with deterministic unit/fake-engine coverage. Do not claim the real `f4h6`
fixture proves that branch.

If the current engine build no longer reproduces the initial inversion under
`AnalysisBudget(depth=12, multipv=3)`, the fixture does not prove the recovery path and must not
be counted as this gate's PASS. Deterministic unit reproduction remains mandatory regardless.

---

## 19. Existing G0 regression

P2-C1 must not weaken:

- G0 public golden classes;
- real Stockfish skip count = 0;
- request concurrency isolation;
- output-mode parity;
- P8-P12 regression;
- schema 0.2 projection;
- exact P12 wording.

Existing non-inversion fixtures should retain two judgement engine calls.

---

## 20. Scope of implementation packet

Recommended production delta:

```text
src/calliope/errors.py
src/calliope/services/judgement/move_judge.py
src/calliope/application/analyze_move.py
```

Expected tests:

```text
tests/unit/services/test_move_judge.py
tests/unit/application/test_analyze_move.py
tests/integration/stockfish/<P2-C1 regression location>
```

A small dedicated regression test file is acceptable.

No P8-P12 production file should need semantic modification.

---

## 21. Independent design review questions

The reviewer must answer:

1. Is typed `CrossSearchInversionError` narrow enough that generic incompatibilities cannot be
   swallowed?
2. Is application-owned paired reanalysis the correct layer while `MoveJudge` remains pure?
3. Is the trigger correctly limited to played-outside-MultiPV numeric cross-search inversion?
4. Are same-search and mate contradictions still fail-closed?
5. Is `roots=(initial_best, played), multipv=2` a valid same-search comparator?
6. Should the paired search use exactly the original judgement limit/threads/hash?
7. Is one retry maximum sufficient to prevent loops?
8. Is original MultiPV correctly retained for best identity, rank, forcedness and P9 alternatives?
9. Is flooring paired negative loss to zero sounder than promoting the move to BEST?
10. Is EXCELLENT the correct maximum for an unranked reconciled move?
11. Are reconciled `best_score`/`played_score` semantics internally coherent even if played
    scores higher?
12. Does the design preserve G0 request-session/new-game invariants?
13. Does conditional reconciliation preserve STRUCTURED/COMMENTARY parity?
14. Is the lack of public reconciliation metadata acceptable for schema 0.2?
15. Is the real fixture gate strong without freezing exact cp values?
16. Are any additional P2/P3 contracts unintentionally changed?
17. Can this remain one small implementation packet after review?

---

## 22. Success condition

After implementation and independent acceptance:

```text
the known legal f4h6 request no longer fails merely because two separate searches inverted
their cp ordering
```

while all non-inverted judgement and P8-P12 behavior remains unchanged.


---

## 23. Implementation outcome

P2-C1 was implemented and independently reviewed READY.

Production delta:

```text
src/calliope/errors.py
src/calliope/services/judgement/move_judge.py
src/calliope/application/analyze_move.py
```

The known `f4h6` fixture with `AnalysisBudget(depth=12, multipv=3)` now reconciles through one
same-session paired search and completes through the ordinary P9/P10/P11/P12 path.

Reviewed acceptance:

```text
2740 passed / 0 failed
integration 104 passed / 0 skipped
G0 public 46 passed
P8-P12 production semantic delta: NONE
PUBLIC_SCHEMA_VERSION: 0.2 unchanged
```

Residual mate/result-class contradictions remain outside this packet and continue to fail closed.
