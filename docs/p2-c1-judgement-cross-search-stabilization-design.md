# P2-C1 — Judgement Cross-Search Inversion Stabilization

Status: **DESIGN_DRAFT_FOR_INDEPENDENT_REVIEW**

Baseline:

```text
main @ a6dae11afa45aa143e750d200e77940e3646302c
```

This is a post-G0 stabilization packet.

It changes P2 judgement orchestration only. It does not reopen P8-P12 or the G0 public trust chain.

---

## 1. Problem

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

Current P2 treats an inversion beyond the fixed noise tolerance as incompatible and fails the
request.

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

Current result:

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

Malformed/mismatched reconciliation input remains `IncompatibleAnalysisError`.

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

## 10. Reconciled loss policy

For normal centipawn/WDL scores in the paired analysis:

```text
cp_loss = max(0, reference_best_cp - played_cp)
expected_score_loss = max(
    0,
    reference_best_expected_score - played_expected_score,
)
```

Use the same mover POV and existing grading thresholds.

If WDL is available, quality remains governed by expected-score loss as today.

Otherwise quality is governed by cp loss as today.

### If paired search still ranks played above the reference best

Do **not** promote the played move to BEST.

A paired two-root search proves only that the old reference-best-vs-played ordering is unstable; it
does not prove the played move is rank 1 among all legal moves.

Negative paired loss is therefore floored to zero.

With zero loss, the maximum reconciled quality is:

```text
EXCELLENT
```

not BEST.

Thus:

```text
rank = None
best_move = original MultiPV best move
cp_loss = 0          # when paired cp comparison favors played
expected_score_loss = 0.0  # when paired WDL comparison favors played
quality = EXCELLENT  # if the authoritative available loss is zero
```

If the paired comparison instead shows a positive loss, use the existing thresholds and return
GOOD / INACCURACY / MISTAKE / BLUNDER as appropriate.

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

If the original or paired comparison enters an existing mate/result-class contradiction such as:

- played mate for mover contradicts non-mate best;
- played mate is faster than reference-best mate;
- played escapes a forced loss;
- played loses later than the supposed best;

retain the existing `IncompatibleAnalysisError` behavior.

A future packet may design broader search-stability semantics if needed.

---

## 13. Application orchestration

The G0 move path becomes:

```text
request validation
FEN/move validation

request-wide engine session
  1. unrestricted position MultiPV
  2. played single-root analysis

  try normal MoveJudge.judge()
  if CrossSearchInversionError:
      3. paired roots=(initial_best, played), MultiPV 2
      MoveJudge.judge_reconciled(...)

  P4-P11 using the resulting MoveJudgement
release session

optional P12
projection
```

The third engine call is conditional.

Normal G0 requests still use the existing two judgement calls.

Reconciliation occurs before P4-P11, so all downstream explanation stages see one final
`MoveJudgement`.

---

## 14. Downstream semantics

P8/P9 route from the **final reconciled quality** exactly as they route any ordinary judgement.

The original `position_analysis` remains the P9 candidate/alternative basis.

P2-C1 does not add a new explanation family or evidence form.

For example, a reconciled zero-loss move outside the original MultiPV may become EXCELLENT and
therefore enter P9. P9 may then produce a verified explanation or valid strict silence under its
existing contract.

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

Use the production public facade and an explicit deterministic judgement budget.

The regression must prove:

- the request no longer fails with the old cross-search inversion;
- the initial played move is outside the initial MultiPV for the qualifying run;
- the original two observations reproduce an inversion beyond the configured tolerance;
- exactly one paired MultiPV-2 judgement call is added;
- roots are initial reference best + `f4h6`;
- all three judgement observations remain in one request session/game token;
- no extra `ucinewgame`;
- the final judgement has `rank is None`;
- the final judgement is never BEST solely because of reconciliation;
- loss values equal the frozen paired-search policy;
- the request continues into the ordinary strict explanation path.

Do not hard-code the old +588/+622 values as a correctness requirement; they are reproduction
evidence, not stable semantic outputs.

If the current engine build no longer reproduces the initial inversion, the fixture does not prove
the recovery path and must not be counted as this gate's PASS. Keep a deterministic fake/unit
reproduction regardless.

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
