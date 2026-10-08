> **LEGACY — FROZEN, NOT THE CURRENT DESIGN.** This document describes the MVP-era implementation preserved at tag `legacy-mvp-g0`. It is kept only as historical reference for the redesign; nothing in it is a current requirement or decision. Current design: [`docs/design/`](../design/README.md). Index: [`docs/README.md`](../README.md).

# MVP-P8 — Bad-Move Explanation design

Status: **CORRECTIONS_APPLIED — READY_FOR_INDEPENDENT_DESIGN_REVIEW**

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

Result-level status:

```python
class BadMoveExplanationStatus(StrEnum):
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not_applicable"
```

Per-candidate status:

```python
class BadMoveCauseStatus(StrEnum):
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"
```

A **cause candidate** is a pair of:

```text
(cause kind, base-normalized subject)
```

that has passed that cause rule's deterministic pre-filter. Merely seeing a P6 pattern does not
automatically create a supported cause.

Result semantics:

- `SUPPORTED`: at least one cause candidate is `SUPPORTED`;
- `REFUTED`: at least one candidate exists, every candidate is `REFUTED`, and none is
  `SUPPORTED` or `INCONCLUSIVE`;
- `INCONCLUSIVE`: the move is eligible but no candidate is supported and either no candidate
  exists or at least one candidate cannot be completely tested;
- `NOT_APPLICABLE`: move quality is outside P8 scope.

`REFUTED` means only that P8 refuted all concrete cause candidates it tested. It never means
the move is not a mistake/blunder.

Per-candidate semantics are shared by every cause rule:

- `REFUTED`: every input required by that candidate's rule was fully evaluated through a
  stable material point or applicable terminal/rule check, all comparator checks completed, and
  either:
  - the actual line does not exploit the base-normalized subject as required by the rule; or
  - the comparator branch demonstrates an equivalent resource/consequence.
- `INCONCLUSIVE`: at least one required check cannot be completed soundly, including a
  truncated PV before the stable point or the absence of a punishment move needed by that
  candidate.

A failed support condition is **not automatically REFUTED**; it is REFUTED only when the
evidence needed to decide that condition was fully evaluated. Otherwise it is INCONCLUSIVE.

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
- per-candidate status;
- base-normalized subject;
- base position id;
- canonical played move;
- canonical comparator move;
- canonical opponent punishment when one exists;
- affected piece identities normalized to the base position;
- exact P5 deltas used by the decision;
- P6 candidates used by the decision;
- P7 results used by the decision;
- whether the same punishment is legal after the comparator;
- whether a semantically equivalent tactical resource exists on the comparator branch;
- the material measurement/evaluation point when material exploitation is used.

Mate evidence additionally carries:

```python
class MateEvidenceLevel(StrEnum):
    EXACT_IMMEDIATE = "exact_immediate"
    ENGINE_LINE = "engine_line"
```

and an optional machine-readable flag indicating whether a replayed engine PV itself ends in an
exact rule-verified checkmate position.

`EXACT_IMMEDIATE` and `ENGINE_LINE` are not interchangeable. P10 must preserve this evidence
level.

No free-form explanation string is authoritative evidence.


## 5. Base-position piece identity

Raw `PieceRef` equality is insufficient across alternative branches because a physical piece
may occupy a different square after a different first move.

P8 therefore uses a branch-normalized identity anchored to the common base position:

```python
@dataclass(frozen=True, slots=True)
class BasePieceRef:
    color: Color
    piece_type: PieceType
    base_square: str
```

In a valid base position, `(color, piece_type, base_square)` identifies one physical base piece.

For every replayed branch, identity is propagated by **composing the P5 correspondence of every
move in sequence**, not only the first move and punishment:

```text
BasePieceRef
  -> after first move
  -> after punishment
  -> after PV ply 2
  -> ...
  -> after final replayed PV ply
```

For each move:

- `BoardDelta.piece_correspondence` carries surviving physical pieces forward;
- `BoardDelta.capture` terminates the captured piece's live mapping;
- castling propagates king and rook independently through their correspondences;
- en passant uses `capture.captured_square`, not the landing square;
- promotion preserves the base pawn identity while the current branch piece records the promoted
  role/type;
- a piece captured on one branch and surviving on another retains one common `BasePieceRef`,
  with no live after-piece on the captured branch.

P8 must not guess physical identity from current type/square alone. Any missing, duplicate, or
contradictory correspondence while composing a replayed PV raises
`IncompatibleBadMoveContextError`.

This full-PV mapping is required both for cross-branch tactical fingerprints and for proving that
a later PV capture actually exploits the candidate subject.

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


### 9.3 Comparator replay and resource contrast

Let `P_A` be the comparator branch's own rank-1 reply from `REFUTATION(B, A)`.

P8 always replays the comparator's own PV deterministically and derives its per-ply P5 deltas,
P6 detections, base-piece mappings, and material observations. This costs no additional P7 probe.

P8 determines whether the actual punishment UCI `P` is legal after `A` by canonical-UCI
membership in `TacticalObservation(BA).legal_moves`; legality is not inferred from exceptions.

If `P` is illegal after `A`:

- Batch B is skipped;
- P8 may conclude only that **that specific UCI move** is unavailable after the comparator;
- illegality alone never proves that the underlying tactical resource is absent.

Whether or not `P` is legal, P8 must also inspect:

1. deterministic P6/fact state immediately after `A` (for example whether the same
   base-normalized piece is still hanging); and
2. the comparator's own reply `P_A` and fully replayed `REFUTATION(B,A)` PV for a
   semantically equivalent base-normalized resource/consequence.

If `P` is legal after `A`, run the optional second P7 batch:

```text
IGNORE_THREAT(B, A, P)
```

P8 deterministically replays that line as well. For any capture made by the replayed `P`, the
captured target is compared by `BasePieceRef`, not merely by destination square or UCI. If the
same UCI captures a different physical piece (or no piece) on the comparator branch, it is a
different concrete resource.

No cause rule may use "P is illegal after A" as a substitute for the base-normalized comparator
checks above.

### 9.4 Why `IGNORE_THREAT`

P7 `IGNORE_THREAT` already has the exact shape needed here:

```text
base B
 -> intervention A
 -> force opponent execution P
 -> analyze with P as the root
```

P8 must not invent a second ad-hoc forced-move engine API.


## 10. Engine compatibility and P8 score-order gate

P3 and P7 may use different analysis budgets. Therefore:

**P8 never numerically compares a P3 score with a P7 score.**

`MoveJudgement` is read only for:

- eligibility/quality;
- base/played move binding;
- engine-best comparator selection.

P8 must not read `MoveJudgement.best_score`, `played_score`, `cp_loss`, or
`expected_score_loss` to establish a cause.

All P8 engine comparisons are restricted to P7 results produced with identical
`EngineSettings`. Each returned batch must bind to exactly the requested settings, probe order,
and probe values. Any mismatch fails closed.

Across the optional second P7 batch, every non-terminal result must also report the same
`EngineIdentity` as Batch A.

Before **any** cause may become `SUPPORTED`, the P7 comparator result
`REFUTATION(B,A)` must be strictly better for the original mover than
`REFUTATION(B,M)`, using only a mate-aware ordering under the same P7 settings:

- a forced mate for the mover is better than every non-mate score;
- a non-mate score is better than a forced mate against the mover;
- between mover-winning mates, shorter mate is better;
- between mover-losing mates, later mate is better;
- between two centipawn scores, higher `centipawns_for(mover)` is better.

This is an ordering check only; P8 adds no centipawn/WDL threshold. If the comparator is not
strictly better under the P7 run, the result is `INCONCLUSIVE` even if P3 originally classified
the move as `MISTAKE` or `BLUNDER`.

Settings, probe/result binding, or engine-identity mismatches raise
`IncompatibleBadMoveContextError`.


## 11. Tactical equivalence across branches

P8 must not compare raw P6 candidate objects between the actual and comparator branches because
their `PieceRef.square` values may differ.

For P8's initial cause vocabulary, a tactical candidate is projected to a private semantic
fingerprint:

```text
candidate kind
+ actor BasePieceRef identities
+ target BasePieceRef identities
+ related BasePieceRef identities
+ current promoted role/type when relevant
```

Generic response UCI values are deliberately excluded from the cross-branch fingerprint because
they are position-dependent. A future rule that needs response equivalence must define its own
base-normalized semantics rather than comparing raw UCI strings.

Only mapped base-origin pieces participate in cross-branch equivalence. Promotions keep the
base-pawn identity plus the current promoted role. A candidate whose required piece cannot be
mapped through the full replayed branch raises `IncompatibleBadMoveContextError`; it is not an
ordinary negative or inconclusive chess finding.


## 12. Initial cause rules

P8 supports a small explicit rule set. No generic "LLM decides the cause" path exists.

### 12.0 Shared exploitation and material rules

P8 owns a deterministic material metric used only for causal verification. It is not an engine
evaluation and does not affect `MoveJudge`:

```text
PAWN   = 100
KNIGHT = 320
BISHOP = 330
ROOK   = 500
QUEEN  = 900
KING   = excluded
```

For a replayed position `X`, define mover material advantage as:

```text
value(mover pieces in X) - value(opponent pieces in X)
```

and measure its change relative to base `B`. A negative change is a net material deficit for
the mover.

A PV material deficit is **stable enough for P8** only when either:

1. the replay reaches an exact **checkmate** position; or
2. after the final capture/promotion that changes weighted material, at least two further plies
   are present in the replay and the mover remains in a negative material delta throughout
   those subsequent positions.

A stalemate is not a material stable point for P8: if the material candidate reaches stalemate
before satisfying rule 2, that candidate is `INCONCLUSIVE`.

If a time-limited PV ends in the middle of an exchange before this stable point, material-based
cause rules return `INCONCLUSIVE`, not `SUPPORTED`.

Within P8, **exploits a piece** means that the fully replayed P7 line contains a
`CaptureDelta` whose captured piece maps to that candidate's `BasePieceRef`, and the required
cause-specific consequence (stable net material deficit or mate) is subsequently established.

Comparator material is measured on the replayed `REFUTATION(B,A)` PV and, when Batch B exists,
also on the replayed `IGNORE_THREAT(B,A,P)` PV.

### 12.1 Newly hanging piece

A candidate is created when, after `M`, P6 reports `HANGING_PIECE` for a mover non-king piece.

"Newly" is defined relative to the same `BasePieceRef` in `B`: before `M`, that piece was
**not simultaneously attacked by an opponent piece and undefended** according to the exact
`attacked_by` / `defended_by` relations in the base facts. This avoids mislabelling a piece
that was already exposed before the played move.

Support requires all of:

1. the actual post-`M` hanging candidate maps to the base-normalized subject;
2. the actual replayed P7 PV exploits that same subject by a traced `CaptureDelta` and reaches
   the shared stable material criterion;
3. neither the immediate comparator state nor the comparator's own replayed refutation contains
   a semantically equivalent exposure/exploitation of that subject;
4. if Batch B exists, forcing the same UCI `P` after `A` does not exploit the same
   base-normalized subject with an equivalent consequence.

The illegality of `P` after `A` is evidence only about that specific move and is never enough
by itself for support.

### 12.2 Removed defender

This rule concerns the bad move removing **its own** defensive relation, not P6's capture-based
`REMOVAL_OF_DEFENDER` candidate on `B -> M`.

A deterministic pre-filter requires an entry in `delta(B,M).removed_defenses` where:

- both `defender` and `defended` belong to the mover;
- both map to base identities;
- the defended piece is not the moved piece itself (that case belongs to the hanging/exposure
  rule).

Support additionally requires:

1. the actual replayed opponent line captures the base-normalized defended piece;
2. that exploitation reaches the shared stable net material-loss criterion;
3. `delta(B,A).removed_defenses` plus the comparator resource checks in §9.3 show no equivalent
   removal/exploitation of the same defended base piece;
4. if P6 emits `REMOVAL_OF_DEFENDER`, it may be used only on a punishment/replayed capture
   delta such as `BM -> P`, with the surviving target belonging to the original mover. It is
   corroborating motif evidence, never an OR-alternative to the exploitation requirement.

### 12.3 Fork allowed

A candidate is created when the actual punishment/replayed branch contains a P6 `FORK` whose
actor and targets can all be normalized to base identities.

Support requires all of:

1. the fork is reached on the actual engine-selected/replayed refutation line;
2. the full actual replay subsequently either:
   - captures at least one base-normalized fork target and reaches the shared stable net material
     deficit for the mover; or
   - produces verified mate involving a king target under §12.4;
3. the comparator's immediate detection and own refutation replay contain no semantically
   equivalent fork/exploitation;
4. if Batch B exists, replaying the same UCI `P` after `A` does not produce an equivalent
   base-normalized fork with the same verified consequence.

Fork geometry alone is never sufficient for `SUPPORTED`.

### 12.4 Mate allowed

Two evidence forms are eligible and must be recorded distinctly.

**EXACT_IMMEDIATE**

The actual opponent punishment `P` is applied by chess rules and the resulting position is
exact checkmate. Support additionally requires an exhaustive one-ply rule check after `A`:
enumerate every legal opponent move in `BA`, apply each move, and confirm that none produces
immediate checkmate. This uses no extra P7 probe.

**ENGINE_LINE**

The actual `REFUTATION(B,M)` result reports a mate for the opponent. Support requires the
same-settings `REFUTATION(B,A)` result not to report a mate against the mover. If the replayed
actual PV itself ends in an exact checkmate, record that separately; otherwise this remains
engine-line evidence only.

The comparator checks in §9.3 still apply to any concrete motif/resource attached to the mate.

`ENGINE_LINE` is at most `ENGINE_VERIFIED` evidence for P10. P8 does not establish
`FORCED` confidence from a single PV or mate score alone.

### 12.5 Material-loss line

P8 replays the canonical actual P7 refutation PV through `ChessRulesPort`, computes a P5 delta
for each move, composes base-piece identity through the entire line, and evaluates material with
§12.0.

Let `D_actual` be the magnitude of the actual branch's stable mover deficit under §12.0.

Support requires:

1. the actual replay reaches a stable net material deficit for the mover relative to `B`;
2. every material-changing event used by the decision is traced to exact P5 capture/promotion
   deltas;
3. the comparator's own `REFUTATION(B,A)` replay does **not** reach a stable mover deficit
   whose magnitude is greater than or equal to `D_actual`;
4. if Batch B exists, the same-punishment replay is also checked and likewise must not reach a
   stable mover deficit whose magnitude is greater than or equal to `D_actual`.

For `MATERIAL_LOSS_LINE`, comparator equivalence is therefore value-based under the fixed
§12.0 metric; it does not require loss of the same base-normalized physical piece. Losing a
different piece or exchange of equal-or-greater total value counts as an equivalent material
consequence.

If the PV ends before the stable point, return `INCONCLUSIVE` for this candidate.

This cause kind is intentionally named `MATERIAL_LOSS_LINE`, not
`FORCED_MATERIAL_LOSS`. Its strongest later P10 confidence is `ENGINE_VERIFIED` unless a
separate forcedness proof is introduced outside P8.

All PV moves must be revalidated while replaying. An illegal/inconsistent PV or a broken
base-piece mapping fails closed.

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

P7 comparator is not strictly better under same P8 settings
    -> INCONCLUSIVE

one or more cause candidates SUPPORTED
    -> SUPPORTED + all deterministically ordered candidate records

at least one candidate exists,
all candidates REFUTED,
none SUPPORTED or INCONCLUSIVE
    -> REFUTED

otherwise
    -> INCONCLUSIVE
```

Candidate order is deterministic: cause-kind enum order, then stable base-square order of the
subject identities.

`REFUTED` is a statement about the tested P8 explanations only. It never changes or negates the
P2 `MoveJudgement`.

P8 does not choose the final minimal explanation; P11 will do that.


## 15. Failure semantics

P8 is fail-closed on incompatible evidence:

- position-id mismatch;
- mover mismatch;
- move/judgement mismatch;
- impossible or broken base-piece mapping at any PV ply;
- P5/P6 context mismatch;
- P7 result bound to another position/settings;
- P7 batch result settings, probe order, or probe values differing from the request;
- cross-batch engine identity mismatch;
- illegal engine PV during replay;
- a candidate requiring a piece that cannot be base-normalized.

These raise `IncompatibleBadMoveContextError` (or the existing lower-level error when it is the
canonical failure).

Engine operational failures propagate through the existing P7/engine error hierarchy. P8 must
not convert an engine failure into a chess conclusion.

Ordinary inability to establish causality, a truncated exchange before the stable material
point, or P7 failing the strict-better comparator gate is `INCONCLUSIVE`, not an exception.

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

1. piece is hanging after the bad move but a fully evaluated stable actual line never exploits
   that subject -> candidate `REFUTED`;
2. fork geometry exists but a fully evaluated stable actual line yields no verified
   material/mate consequence -> candidate `REFUTED`;
3. same punishment and equivalent tactic/consequence exist after the best comparator ->
   candidate `REFUTED`;
4. evaluation drops for a positional reason outside strict MVP vocabulary -> `INCONCLUSIVE`;
5. detector/candidate references a piece that cannot be base-normalized -> raised
   `IncompatibleBadMoveContextError`;
6. best comparator differs but no concrete P8 cause is established -> `INCONCLUSIVE`;
7. `P` is illegal after `A`, but a fully evaluated comparator line shows an equivalent
   resource through another UCI -> candidate `REFUTED`, not `SUPPORTED`;
8. `P` is legal after `A` but captures a different physical base piece -> that replay is not
   the same subject/resource; candidate status is then decided from the remaining fully
   evaluated actual/comparator evidence (`REFUTED` if an equivalent consequence is shown,
   otherwise according to the rule's completed support checks);
9. PV stops in the middle of an exchange before the stable material point -> material cause
   `INCONCLUSIVE`;
10. material PV reaches stalemate before satisfying the non-terminal stability rule ->
   material cause `INCONCLUSIVE`;
11. comparator material replay loses a different piece but reaches a stable deficit with
   magnitude >= the actual deficit -> `MATERIAL_LOSS_LINE` candidate `REFUTED`;
12. `REFUTATION(B,A)` is not strictly better than `REFUTATION(B,M)` under P8 settings ->
    result `INCONCLUSIVE`;
13. actual or comparator first-move branch is terminal;
14. returned P7 batch settings/order/probes do not match the request -> fail closed.

P8-I1 identity unit tests additionally cover:

- ordinary move chains;
- castling;
- promotion;
- capture-promotion;
- en passant;
- a base piece captured on only one branch;
- correspondence composition across multiple PV plies.

Mate tests assert the `EXACT_IMMEDIATE` versus `ENGINE_LINE` evidence level and the optional
exact-PV-checkmate flag.


### 18.5 Probe-budget assertions

Tests must assert:

- Batch A contains exactly, in order:
  `REFUTATION(B,M)`, `REFUTATION(B,A)`;
- Batch B runs **exactly when** actual punishment `P` exists and canonical `P.uci` is present
  in `TacticalObservation(BA).legal_moves`;
- Batch B, when run, contains exactly `IGNORE_THREAT(B,A,P)`;
- each batch result echoes the requested settings and probes in the same order;
- no case exceeds three probes;
- no P7 call occurs for `NOT_APPLICABLE`.

The comparator's own PV, immediate P6 state, exhaustive one-ply mate check, and all deterministic
PV replays are free of additional P7 probes.

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
