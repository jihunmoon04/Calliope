# MVP-P8 — Bad-Move Explanation design

Status: **READY_FOR_INDEPENDENT_DESIGN_REVIEW**

Baseline: `mvp/p7-counterfactual-core @ 811f28bc50319ac4570ec740e49be17cc4f27542`

This document freezes the design target for MVP-P8. It does not authorize implementation,
merge, or public-schema changes.

## 1. Goal

P8 answers one bounded causal question for a move already judged bad:

> What concrete opponent resource did the played move allow, compared with the engine-best
> alternative?

P8 does not decide whether the move is bad. `MoveJudge` remains authoritative for move quality.
P8 does not write commentary and does not create `ExplanationClaim` objects. It produces
verified internal cause evidence for P10.

The first supported input qualities are:

- `MISTAKE`
- `BLUNDER`

`BEST`, `EXCELLENT`, `GOOD`, and `INACCURACY` are not P8 targets. Good/only-move
explanation belongs to P9.

## 2. Architectural boundary

Existing stages keep their current responsibilities:

- P2 / `MoveJudge`: how bad the move is;
- P5 / `BoardDeltaAnalyzer`: exact board changes caused by one move;
- P6 / `TacticalDetector`: deterministic tactical pattern candidates only;
- P7 / `CounterfactualAnalyzer`: bounded engine experiments;
- P8 / `BadMoveExplainer`: verify whether an observed concrete resource is a supported
  explanation of the bad move;
- P10: convert eligible evidence into claims.

P8 must not:

- call Stockfish directly;
- duplicate move-quality thresholds;
- infer player intent;
- promote a P6 `DETECTED` candidate into public truth by itself;
- compare engine scores from incompatible settings;
- manufacture prose;
- mutate P5/P6/P7 results.

P8 may only access engine analysis through P7.

## 3. Public API and wiring

P8 is internal in this packet.

No changes are made to:

- `CalliopeEngine` public methods;
- `AnalyzeMoveRequest`;
- `MoveAnalysisResult`;
- `PUBLIC_SCHEMA_VERSION`.

The current public `claims=()` and `commentary=None` behavior remains unchanged until the
evidence/claim stages exist.

A later integration packet may wire P8 behind `AnalyzeMoveService`, but P8 itself must be
testable as a standalone internal service.

## 4. New internal models

Suggested module:

`src/calliope/domain/analysis/bad_move.py`

### 4.1 Verification status

```python
class BadMoveExplanationStatus(StrEnum):
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not_applicable"
```

Semantics:

- `SUPPORTED`: the bounded P8 checks support at least one concrete cause;
- `REFUTED`: a concrete candidate was tested and the best-alternative contrast defeats it;
- `INCONCLUSIVE`: the move is eligible, but P8 cannot establish a supported concrete cause;
- `NOT_APPLICABLE`: move quality is outside P8 scope.

Malformed or mutually incompatible inputs are errors, not `INCONCLUSIVE`.

### 4.2 Initial cause kinds

```python
class BadMoveCauseKind(StrEnum):
    NEWLY_HANGING_PIECE = "newly_hanging_piece"
    REMOVED_DEFENDER = "removed_defender"
    FORK_ALLOWED = "fork_allowed"
    MATE_ALLOWED = "mate_allowed"
    MATERIAL_LOSS_LINE = "material_loss_line"
```

`MATERIAL_LOSS_LINE` deliberately does not say "forced". A single engine PV is evidence of an
engine-verified line, not a mathematical proof that all defenses lose material. P10 may later
choose stronger language only when its evidence rules allow it.

### 4.3 Cause result

A cause result must retain machine-readable evidence, not prose. The exact field names may be
adjusted during implementation, but the information contract is:

- cause kind;
- status;
- base position id;
- canonical played move;
- canonical comparator move;
- canonical opponent punishment when one exists;
- affected piece identities normalized to the base position;
- exact P5 deltas used by the decision;
- P6 candidates used by the decision;
- P7 results used by the decision;
- whether the same punishment is legal after the comparator;
- whether a semantically equivalent tactical resource exists on the comparator branch.

No free-form explanation string is authoritative evidence.

## 5. Base-position piece identity

Raw `PieceRef` equality is insufficient across alternative branches because a physical piece
may occupy a different square after a different first move.

P8 therefore needs a branch-normalized identity anchored to the base position.

Suggested private/internal value:

```python
@dataclass(frozen=True, slots=True)
class BasePieceRef:
    color: Color
    piece_type: PieceType
    base_square: str
```

For every branch beginning at the same base position, P8 derives:

```text
BasePieceRef
  -> piece after first move, or captured
  -> piece after punishment, or captured
```

The mapping must be derived from P5 `piece_correspondence` and `capture`; P8 must not guess
piece identity from type and square alone.

Promotions retain the base pawn identity even though the piece type changes after promotion.
Captured pieces map to no after-piece.

This mapping is required for cross-branch tactical comparison.

## 6. Inputs and dependencies

Suggested service:

`src/calliope/services/explanation/bad_move.py`

```python
@dataclass(slots=True)
class BadMoveExplainer:
    chess: ChessRulesPort
    facts: PositionFactExtractor
    delta: BoardDeltaAnalyzer
    tactical_rules: TacticalObservationPort
    detector: TacticalDetector
    counterfactual: CounterfactualAnalyzer
```

Conceptual execute input:

- base `PositionSnapshot`;
- played `ChessMove`;
- `MoveJudgement`;
- explicit P7 `EngineSettings`.

The service canonicalizes the played move and comparator via `ChessRulesPort`.

### 6.1 Context validation

Before any P7 engine call:

1. `judgement.position_id == base.position_id`;
2. `judgement.mover == base.side_to_move`;
3. the supplied played move canonicalizes to `judgement.move.uci`;
4. `judgement.best_move` is legal in the same base position;
5. the canonical best move differs from the canonical played move for an eligible bad-move
   explanation;
6. all deterministic P5/P6 observations bind to the expected position ids.

A mismatch fails closed with a P8-owned incompatibility error.

Recommended errors:

```python
class BadMoveExplanationError(CalliopeError): ...
class IncompatibleBadMoveContextError(BadMoveExplanationError): ...
```

## 7. Eligibility

If the context is valid but quality is not `MISTAKE` or `BLUNDER`, return
`NOT_APPLICABLE` without P7 engine calls.

An eligible move with no verified cause returns `INCONCLUSIVE`; it remains a mistake/blunder
according to P2.

P8 must never downgrade or upgrade `MoveJudgement`.

## 8. Deterministic branch construction

Let:

- `B` = base position;
- `M` = played move;
- `A` = engine-best comparator from `MoveJudgement`;
- `BM` = position after `M`;
- `BA` = position after `A`.

P8 constructs both branches with `ChessRulesPort.apply_move`.

For each first move it obtains:

- before and after `PositionFacts`;
- first-move `BoardDelta`;
- before/after `TacticalObservation`;
- P6 `TacticalDetection`.

These facts are exact/deterministic evidence. They are not by themselves enough to prove that a
detected tactic is the reason for the engine loss.

## 9. Counterfactual protocol

P8 uses at most two P7 batches and at most three probes in the normal path.

### 9.1 Batch A: actual move and best comparator

One batch:

```text
REFUTATION(B, M)
REFUTATION(B, A)
```

The same P7 settings are used for both probes.

For the actual branch, if the result is non-terminal:

```text
P = first move of the rank-1 engine line after M
```

`P` is the opponent punishment candidate.

The comparator `REFUTATION(B, A)` records the opponent's best reply after the best
alternative. It is comparison evidence; it is not required to be the same move as `P`.

If the actual branch is terminal after `M`, there is no opponent punishment move. Terminal
cases are handled conservatively. A stalemating blunder, for example, may remain
`INCONCLUSIVE` in P8 unless one of the initial cause rules explicitly supports it.

### 9.2 Exact punishment branch

If `P` exists, P8 applies `P` to `BM` and derives:

- punishment position `BMP`;
- punishment `BoardDelta(BM, P)`;
- punishment P6 detection.

This establishes the exact board/tactical consequence of the opponent's engine-selected reply.

### 9.3 Comparator replay

P8 checks whether the same UCI move `P` is legal in `BA`.

If it is illegal, that is exact rules evidence that the played move enabled that specific
opponent resource relative to the best comparator. No forced comparator probe is needed.

If it is legal, run a second P7 batch with exactly one probe:

```text
IGNORE_THREAT(B, A, P)
```

This forces the same opponent resource after the best comparator under the same P7 settings.

P8 also applies `P` to `BA` deterministically and computes the comparator punishment delta
and P6 detection.

### 9.4 Why `IGNORE_THREAT`

P7 `IGNORE_THREAT` already has the exact shape needed here:

```text
base B
 -> intervention A
 -> force opponent execution P
 -> analyze with P as the root
```

P8 must not invent a second ad-hoc forced-move engine API.

## 10. Engine compatibility rule

P3 and P7 may use different analysis budgets. Therefore:

**P8 never numerically compares a P3 score with a P7 score.**

All P8 engine comparisons are restricted to P7 results produced with identical
`EngineSettings`.

Across the optional second P7 batch, P8 also verifies that every non-terminal result reports the
same `EngineIdentity`. If identity changes, fail closed with
`IncompatibleBadMoveContextError`.

The existing `MoveJudgement` is used for eligibility and comparator selection only.

## 11. Tactical equivalence across branches

P8 must not compare raw P6 candidate objects between the actual and comparator branches because
their `PieceRef.square` values may differ.

For comparison, a tactical candidate is projected to a private semantic fingerprint:

```text
candidate kind
+ actor BasePieceRef identities
+ target BasePieceRef identities
+ related BasePieceRef identities
+ canonical response UCI values when relevant
```

Only mapped base-origin pieces participate in cross-branch equivalence.

A candidate involving a newly promoted piece may use the base pawn identity plus the after-piece
role. A candidate whose required piece cannot be mapped fails closed rather than being guessed.

## 12. Initial cause rules

P8 supports a small explicit rule set. No generic "LLM decides the cause" path exists.

### 12.1 Newly hanging piece

Support when:

1. the played-move branch creates a `HANGING_PIECE` candidate for one of the mover's
   non-king pieces;
2. the engine-selected punishment `P` concretely captures or exploits that same
   base-normalized target in the verified line;
3. under the best comparator, the same target is not exposed to a semantically equivalent
   resource, or the same punishment is illegal.

A merely hanging piece with no verified exploitation is not sufficient.

### 12.2 Removed defender

Support when:

1. the played `BoardDelta` contains a removed defense involving a base-normalized target;
2. P6 reports `REMOVAL_OF_DEFENDER` or the punishment line concretely exploits the now
   undefended target;
3. the best comparator does not remove the corresponding defense in a semantically equivalent
   way;
4. the actual punishment produces the verified consequence.

### 12.3 Fork allowed

Support when:

1. after the actual opponent punishment, P6 detects a `FORK`;
2. the fork actors/targets can be normalized to base identities;
3. the punishment is engine-selected after the played move;
4. the same punishment is illegal after the comparator, or its comparator replay does not
   produce the equivalent fork.

Detection of fork geometry without an engine-selected/exploited punishment remains insufficient.

### 12.4 Mate allowed

Two MVP forms are eligible:

- immediate mate: the actual punishment produces an exact checkmate position;
- engine-verified mate line: the actual P7 result reports a mate for the opponent and the
  comparator result does not report the corresponding losing mate condition.

The second form remains engine-verified evidence, not an exact rule proof that every defense
loses. P10 must preserve that distinction.

### 12.5 Material-loss line

P8 may replay the canonical PV from the actual P7 refutation through `ChessRulesPort` and inspect
exact material changes along that line.

Support when:

1. the actual verified line contains a material loss for the mover;
2. the loss can be traced to exact captures/deltas;
3. the comparator best-response line or same-punishment replay does not contain a semantically
   equivalent loss under the bounded comparison.

This cause kind is named `MATERIAL_LOSS_LINE`, not `FORCED_MATERIAL_LOSS`.

All PV moves must be revalidated while replaying. An illegal or inconsistent PV fails closed.

## 13. Meaning of "allowed"

P8 proves a bounded contrast:

> the played move permits a concrete opponent resource that the engine-best comparator avoids
> under the P8 verification protocol.

P8 does **not** prove:

- that every other legal move avoids the resource;
- that the played move is the only move that allows it;
- that a human player intended anything;
- that the detected motif is the entire strategic reason for the evaluation loss.

This scope must be preserved when P10/P12 later verbalize the result.

## 14. Result policy

Decision order:

```text
invalid/incompatible input
    -> raise P8-owned error

quality outside P8
    -> NOT_APPLICABLE

eligible, one or more cause rules supported
    -> SUPPORTED + supported causes

eligible, candidates explicitly contrasted and defeated
    -> REFUTED + refuted cause records

eligible, no support and no complete refutation
    -> INCONCLUSIVE
```

If multiple causes are supported, retain them deterministically in enum order and stable
base-square order. P8 does not choose the final minimal explanation; P11 will do that.

## 15. Failure semantics

P8 is fail-closed on incompatible evidence:

- position-id mismatch;
- mover mismatch;
- move/judgement mismatch;
- impossible branch mapping;
- P5/P6 context mismatch;
- P7 result bound to another position/settings;
- cross-batch engine identity mismatch;
- illegal engine PV during replay.

Engine operational failures propagate through the existing P7/engine error hierarchy. P8 must
not convert an engine failure into a chess conclusion.

An ordinary inability to establish causality is `INCONCLUSIVE`, not an exception.

## 16. Determinism

Given identical:

- base position;
- canonical moves;
- `MoveJudgement`;
- P7 results;
- P5/P6 observations;

P8 result ordering and classification must be deterministic.

P8 contains no randomness and no LLM call.

## 17. Budget

Default P8 counterfactual path:

```text
Batch A:
  1. REFUTATION(B, M)
  2. REFUTATION(B, A)

Optional Batch B:
  3. IGNORE_THREAT(B, A, P)
```

Maximum normal P8 probe count: **3**.

No additional P7 probe may be added merely to improve prose.

The P7 per-probe limits remain authoritative. P8 does not relax `MAX_TIME_MS` or batch-size
constraints.

## 18. Test gates

Suggested tests:

`tests/unit/services/explanation/test_bad_move.py`

`tests/integration/stockfish/test_bad_move.py`

### 18.1 Context/fail-closed

- judgement position differs from base;
- mover differs;
- played move differs from judgement;
- comparator illegal;
- P5/P6 position mismatch;
- P7 settings mismatch;
- P7 cross-batch engine identity mismatch;
- invalid PV replay.

All must fail closed and must not return a supported cause.

### 18.2 Eligibility

For `BEST`, `EXCELLENT`, `GOOD`, and `INACCURACY`:

- result is `NOT_APPLICABLE`;
- no P7 engine call occurs.

For `MISTAKE` and `BLUNDER`, P8 runs only the bounded protocol required by the fixture.

### 18.3 Positive fixtures

At least one hand-checked position for each initial cause:

1. newly hanging piece exploited;
2. removed defender exploited;
3. fork allowed;
4. mate allowed;
5. material-loss line.

### 18.4 Negative/adversarial fixtures

Mandatory:

1. piece is hanging after the bad move but the best punishment does not exploit it;
2. fork geometry exists but yields no verified advantage;
3. same punishment and equivalent tactic exist after the best comparator;
4. evaluation drops for a positional reason outside strict MVP vocabulary;
5. detector emits a candidate that cannot be base-normalized;
6. best comparator differs but no concrete P8 cause is established.

The expected outcome for case 4 is `INCONCLUSIVE`, while the original bad-move judgement is
preserved.

### 18.5 Probe-budget assertions

Tests must assert:

- Batch A contains exactly the two required refutations;
- Batch B occurs only when the same punishment is legal after the comparator and its replay is
  needed;
- no case exceeds three probes;
- no P7 call occurs for `NOT_APPLICABLE`.

### 18.6 Real Stockfish integration

Real Stockfish fixtures must demonstrate at least:

- one supported tactical bad-move explanation;
- one supported mate/material consequence;
- one bad move that remains `INCONCLUSIVE` without invented cause.

## 19. Implementation packet boundaries

Recommended implementation order:

```text
P8-I0  domain models + P8 errors
P8-I1  branch/base-piece normalization helpers
P8-I2  BadMoveExplainer context + deterministic branch facts
P8-I3  bounded P7 protocol + compatibility checks
P8-I4  cause rules
P8-I5  unit/adversarial tests
P8-I6  real Stockfish integration tests
```

No public DTO wiring in P8.

## 20. Review questions

Independent review must explicitly answer:

1. Is `MoveJudgement.best_move` an adequate single comparator for MVP-P8 without implying
   uniqueness?
2. Is the two-batch / three-probe protocol sufficient and correctly bounded?
3. Does base-normalized piece identity prevent false cross-branch candidate equality?
4. Are the mate/material labels conservative enough for the evidence actually available?
5. Are `REFUTED` versus `INCONCLUSIVE` semantics unambiguous?
6. Is any cause rule capable of turning a detector-only hypothesis into a supported cause without
   concrete P7 exploitation?
7. Does any design path numerically compare incompatible P3/P7 engine settings?
8. Can P8 remain internal until P10 without weakening the public facade boundary?

Implementation must not begin until the design review returns READY or
READY_WITH_CORRECTIONS and all blockers are resolved.
