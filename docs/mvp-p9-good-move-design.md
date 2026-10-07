# MVP-P9 Good-Move / Only-Move Explanation Design

Status: **design freeze candidate**

Base: `main @ ac1b030989ea9910a7d53e1ea3c484fb8d478cd3`

This document is the canonical design for MVP-P9. It extends the P7 counterfactual core and the
completed P8 evidence-first causal machinery without changing the public facade.

## 1. Goal

P9 answers two bounded questions.

### Good / strong move

> What concrete benefit does the played strong move achieve that the serious alternatives tested
> here do not?

### Only-move candidate

> Why do the representative serious alternatives fail compared with the played best move?

P9 does **not** prove player intent and does not infer a strategic narrative that is absent from
board/rule/engine evidence.

## 2. Core safety rule: representative alternatives are not exhaustive proof

The current `MoveJudge.forcedness` value is derived from the MultiPV candidate set. In
particular, `ForcednessLevel.ONLY_MOVE` is not by itself an exhaustive proof that every legal
alternative fails.

Therefore P9 must distinguish:

```text
ONLY_MOVE candidate / narrow-engine context
    !=
literal exhaustive "only legal/acceptable move" proof
```

P9 may verify why selected top alternatives fail. Its strongest default conclusion is:

> the representative alternatives tested here fail to preserve the verified benefit / outcome.

P10 must not emit a literal "only move" claim from P9 representative evidence alone.

A future separate exhaustive forcedness proof may upgrade that language.

## 3. Applicability

P9 is eligible for:

- `BEST`
- `EXCELLENT`
- `GOOD`

P9 is not applicable to:

- `INACCURACY`
- `MISTAKE`
- `BLUNDER`

The only-move mode is considered only when all are true:

- the played move canonical UCI equals `MoveJudgement.best_move`;
- `MoveJudgement.quality == BEST`;
- `MoveJudgement.forcedness.level == ONLY_MOVE`.

This only selects the P9 mode. It is **not** causal proof.

## 4. Required inputs

P9 requires:

- immutable base `PositionSnapshot B`;
- canonical played move `M`;
- `MoveJudgement J`;
- the original base-position `EngineAnalysis position_analysis` used for judgement candidate
  ranking;
- P4/P5/P6 deterministic services;
- P7 `CounterfactualAnalyzer`;
- exact P9 `EngineSettings`.

The base `position_analysis` is used only to select representative alternatives by rank and to
validate the candidate set.

P9 must never numerically compare a P3 / judgement score against a P7 score.

## 5. Position-analysis compatibility

Before selecting alternatives, verify:

```text
position_analysis.position_id == B.position_id
position_analysis contains rank 1
rank values are unique and contiguous
canonical rank-1 UCI == J.best_move.uci
```

The played move must canonicalize to `J.move.uci`.

For an eligible `BEST` move:

```text
M.uci == J.best_move.uci
```

For `EXCELLENT` / `GOOD`, the played move may differ from rank 1.

A malformed or incompatible basis raises `IncompatibleGoodMoveContextError` (or the canonical
existing lower-layer error where appropriate).

## 6. Representative serious alternatives

P9 selects at most **two** alternatives.

Selection:

1. sort `position_analysis.lines` by rank;
2. canonicalize each first move against B;
3. remove duplicate canonical UCI;
4. exclude the played move M;
5. take the first two remaining moves.

For `EXCELLENT` / `GOOD`, the engine-best move must be included when it is not M.

The alternative set is frozen before any P7 call.

The retained scope is:

```text
REPRESENTATIVE_TOP_ENGINE_LINES
```

P9 never claims this set contains every legal move.

If no representative alternative exists, P9 returns `INCONCLUSIVE`, not a uniqueness claim.

## 7. Result vocabulary

Internal only. No public DTO change in P9.

### Explanation status

```text
SUPPORTED
REFUTED
INCONCLUSIVE
NOT_APPLICABLE
```

### Mode

```text
STRONG_MOVE
ONLY_MOVE_CANDIDATE
```

### Initial benefit kinds

```text
FORCES_RESPONSE
MATE_THREAT
MATERIAL_THREAT
PREVENTS_MATE
PREVENTS_MATERIAL_LOSS
```

These are machine evidence categories, not prose.

## 8. Meaning of each benefit kind

### FORCES_RESPONSE

The played move deterministically leaves the opponent exactly one legal reply.

Support additionally requires that the representative alternative branches do not establish the
same exact one-reply forcing property with an equivalent verified consequence.

Geometry / move count alone must not be used to claim a material or mating consequence.

### MATE_THREAT

A concrete tested line after M establishes a mating threat or mating consequence that the
representative alternatives do not establish equivalently.

Evidence level must distinguish exact board checkmate from engine-line mate.

A single engine mate score is never upgraded to exhaustive forcedness.

### MATERIAL_THREAT

A concrete tested line after M establishes a stable material gain for the original mover under
the fixed P8 material metric / stability contract.

Representative alternatives must not establish an equivalent-or-greater stable material gain
for the mover.

### PREVENTS_MATE

Used in `ONLY_MOVE_CANDIDATE` mode when one or more selected alternatives allow verified mate
against the mover while M does not.

### PREVENTS_MATERIAL_LOSS

Used in `ONLY_MOVE_CANDIDATE` mode when one or more selected alternatives allow a stable
material deficit that M avoids.

The cause is representative-alternative preservation, not literal global uniqueness.

## 9. Reuse of P8 deterministic contracts

P9 reuses these already reviewed contracts:

- canonical UCI from `ChessRulesPort`;
- P4 `PositionFacts`;
- P5 `BoardDelta`;
- P6 candidate status remains `DETECTED` until a P9 rule verifies it;
- `BasePieceIdentityMap` physical identity;
- full-PV deterministic replay;
- fixed material values:
  - pawn 100
  - knight 320
  - bishop 330
  - rook 500
  - queen 900
  - king excluded;
- P8 stable-material criterion;
- exact-checkmate board truth;
- fail-closed illegal/incompatible PV handling.

P9 may extract shared pure replay/material helpers from P8 if implementation review proves the
refactor preserves P8 behavior byte-for-byte / test-for-test.

P9 must not call P8 by constructing fake `MoveJudgement` values.

## 10. Deterministic branch context

For M and every selected alternative A_i, derive from the same B:

```text
B --X--> BX

PositionFacts(BX)
BoardDelta(B,X)
TacticalObservation(BX)
TacticalDetection(B,X)
BasePieceIdentityMap after X
```

where `X in {M, A1, A2}`.

Branches are immutable and independent.

No alternative may be derived from BM or from another alternative branch.

## 11. Frozen P7 protocol

### Batch A — mandatory

Run one batch containing:

```text
REFUTATION(B,M)
REFUTATION(B,A1)   if A1 exists
REFUTATION(B,A2)   if A2 exists
```

Order is frozen: played move first, then alternative rank order.

Batch A therefore contains 1..3 probes.

For normal eligible P9 execution with at least one alternative:

```text
2..3 probes
```

### Batch B — optional ignored-response probe

At most one additional probe is allowed:

```text
IGNORE_THREAT(B,M,Q)
```

where Q is one concrete legal opponent response after M selected by a P9 threat rule.

Batch B is allowed only when the threat rule can name:

- the concrete tested opponent move Q;
- the concrete threat/resource being tested;
- why Q qualifies as the tested "ignored response".

P9 must never add Batch B simply because the actual explanation is unclear.

### Budget

```text
maximum P9 probes: 4
maximum P9 P7 calls: 2
```

No adaptive probe expansion in MVP.

## 12. Batch compatibility

Every returned batch must exactly match:

- requested `EngineSettings`;
- requested probe count;
- requested probe order;
- requested intervention/execution UCI;
- expected branch position;
- expected root move when forced.

All non-terminal analyses across both batches must use one `EngineIdentity`.

Mismatch raises `IncompatibleGoodMoveContextError`.

Operational P7/engine failures propagate unchanged.

## 13. P7 score usage

P9 score comparison is restricted to P7 results produced with identical settings.

Never compare:

```text
MoveJudgement.best_score / played_score / cp_loss / expected_score_loss
```

against P7 results.

Use P3 values only for:

- eligibility;
- move binding;
- forcedness mode selection;
- ranked alternative selection through `position_analysis`.

## 14. Mate-aware P7 ordering

Where a P9 rule needs relative outcome ordering, use the same mover-oriented ordering already
reviewed in P8:

- mover-winning mate > every centipawn score;
- centipawn > mover-losing mate;
- shorter mover-winning mate is better;
- later mover-losing mate is better;
- higher centipawns-for-mover is better;
- equal outcome is not strictly better;
- stalemate has no invented centipawn equivalent.

This ordering is a compatibility / contrast tool, not proof of a cause.

## 15. STRONG_MOVE mode

The strong-move mode asks whether M has a concrete tested benefit absent from the selected
alternatives.

A supported benefit requires:

1. deterministic candidate/effect on M or its verified replay;
2. concrete consequence under exact rules / P7 replay;
3. completed comparator checks for every selected representative alternative required by that
   benefit rule;
4. no equivalent-or-stronger benefit on those alternatives;
5. no incompatible/truncated comparator evidence required for support.

If the actual benefit is established but one required alternative comparison is incomplete:

```text
INCONCLUSIVE
```

not `SUPPORTED`.

If a representative alternative establishes an equivalent benefit:

```text
REFUTED
```

for that benefit candidate.

## 16. FORCES_RESPONSE rule

Create a candidate only when after M:

```text
len(legal_moves(BM)) == 1
```

and BM is not checkmate/stalemate.

Retain the sole canonical response.

Support requires every selected alternative branch to be fully observed and not to establish an
equivalent exact one-response forcing consequence.

A raw single legal reply is exact board evidence, but P9 must not claim that this alone explains
the engine preference if alternatives achieve an equivalent forcing result.

## 17. Threat rules and ignored-response semantics

P9 must not interpret "some bad opponent move loses" as proof that the opponent is universally
forced to answer a threat.

Therefore `IGNORE_THREAT(B,M,Q)` proves only this bounded statement:

> this concrete tested response Q fails to meet the verified resource/threat.

P10/P12 must later verbalize it accordingly unless a separate exhaustive response proof exists.

A threat candidate may be supported only when:

- the resource is tied to exact P5/P6/base-normalized evidence;
- Batch A actual replay demonstrates the resource remains relevant under best defense or identifies
  the defensive response;
- the optional ignored-response line demonstrates a concrete mate/material consequence;
- selected serious alternatives do not create an equivalent verified threat/consequence.

No arbitrary quiet legal move may be chosen merely because it loses.

The Q-selection rule must be deterministic and cause-specific.

## 18. MATE_THREAT

Eligible evidence forms:

### EXACT_IMMEDIATE

M itself ends in exact checkmate.

This is exact board truth. P9 may retain it, though final claim creation still belongs to P10.

### TESTED_MATE_THREAT

A concrete ignored-response test or replayed line after M reaches exact checkmate or reports
engine mate for the mover.

Support requires selected serious alternatives not to establish an equivalent mating consequence.

Retain whether the replay actually ends in exact checkmate.

Do not label a single PV as `FORCED`.

## 19. MATERIAL_THREAT

A candidate requires an exact base-normalized material-changing event on the M branch / tested
ignored-response replay.

Use the fixed P8 material metric and stability rule.

Let `G_M` be the stable material gain magnitude for the original mover.

Representative alternative equivalence is value-based:

```text
stable gain on A_i >= G_M
    -> equivalent-or-better benefit on that alternative
```

A truncated alternative material line is `INCONCLUSIVE`, not absence.

The physical identity of the captured piece may be retained as evidence, but value equivalence
does not require the same piece.

## 20. ONLY_MOVE_CANDIDATE mode

This mode is triggered only by the P2 forcedness hint described in §3.

It asks why the selected representative alternatives fail.

For each A_i, P9 replays `REFUTATION(B,A_i)` and classifies only concrete failure types:

- mate against the original mover;
- stable material deficit for the original mover.

A representative alternative with only a positional / centipawn disadvantage and no supported
P9 failure type remains unexplained.

P9 must not create a generic "bad alternative" cause.

## 21. PREVENTS_MATE

Support requires:

- M branch does not establish mate against the mover under the verified P9 evidence;
- at least one representative A_i establishes mate against the mover;
- every selected alternative required by the candidate is fully evaluated;
- the evidence record names which A_i failed and whether the mate is exact-board or engine-line.

This supports:

> M preserves the position against the representative mating failure seen after A_i.

It does not support:

> M is literally the only move.

## 22. PREVENTS_MATERIAL_LOSS

Support requires:

- M branch has no equivalent stable material deficit;
- at least one representative A_i has a stable material deficit;
- material tracing is exact P5 capture/promotion evidence;
- required comparator lines are complete under the P8 stability rule.

If an alternative PV ends mid-exchange:

```text
INCONCLUSIVE
```

for that preservation comparison.

## 23. Only-move aggregation semantics

P9 may retain per-alternative failure records.

The aggregate may be `SUPPORTED` when at least one concrete preservation benefit is verified
and all comparisons required by that benefit are complete.

However the result must carry:

```text
mode = ONLY_MOVE_CANDIDATE
alternative_scope = REPRESENTATIVE_TOP_ENGINE_LINES
literal_only_move_proven = False
```

for MVP-P9.

This flag is frozen false in P9.

P10 must reject any literal-only-move claim whose evidence contains only this representative
scope.

## 24. Equivalent / many-good-move safety

When P2 reports:

- `MANY_EQUIVALENT`;
- `FLEXIBLE`;
- multiple top engine lines with similar verified outcomes;

P9 must be especially conservative.

If a representative alternative establishes the same benefit:

- the benefit candidate is `REFUTED` as a unique contrast;
- P9 must not use "only", "unique", or "necessary" semantics.

The engine judgement remains unchanged.

## 25. Quiet positional best move

A quiet best move with no strict P9 benefit is a valid:

```text
INCONCLUSIVE
causes/benefits = ()
```

This is mandatory behavior, not a failure.

P9 must not convert raw centipawn superiority into speculative positional prose.

## 26. Candidate / result status policy

Per-benefit status:

```text
SUPPORTED
REFUTED
INCONCLUSIVE
```

Aggregate decision order:

```text
invalid/incompatible evidence
    -> raise

quality outside P9
    -> NOT_APPLICABLE

no representative alternatives
    -> INCONCLUSIVE

one or more benefit candidates SUPPORTED
    -> SUPPORTED

at least one candidate,
all candidates REFUTED,
none SUPPORTED/INCONCLUSIVE
    -> REFUTED

otherwise
    -> INCONCLUSIVE
```

A failed support condition is not automatically `REFUTED`.

Missing/truncated evidence required for the decision is `INCONCLUSIVE`.

## 27. Evidence retention

Each P9 benefit record should retain enough machine evidence for P10:

- kind;
- status;
- mode;
- base position id;
- played move;
- representative alternative moves;
- concrete failed alternative(s), when relevant;
- tested ignored response Q, when relevant;
- base-normalized affected pieces;
- P5 deltas;
- P6 tactical candidates;
- P7 probe results;
- material evidence;
- mate evidence level;
- equivalent-alternative result: True / False / None;
- alternative scope.

No prose.

## 28. Deterministic ordering

Alternative order:

```text
position_analysis rank
```

Benefit result order:

1. benefit-kind declaration order;
2. subject base-square order;
3. failed-alternative rank order.

No hash/set iteration may affect retained result ordering.

## 29. Failure semantics

Fail closed on:

- basis position mismatch;
- played/judged/best UCI mismatch;
- malformed/non-contiguous rank set;
- duplicate canonical alternative;
- illegal selected alternative;
- P5/P6 branch mismatch;
- P7 settings/probe/order mismatch;
- cross-batch engine identity mismatch;
- illegal engine PV during replay;
- broken base-piece identity;
- candidate piece that cannot be normalized;
- material change not backed by exact P5 capture/promotion evidence.

Use `IncompatibleGoodMoveContextError` for P9-owned contradictions.

Operational engine/P7 errors propagate.

Ordinary inability to explain a strong move is `INCONCLUSIVE`.

## 30. Public boundary

P9 remains internal.

Do not change:

- `CalliopeEngine`;
- public request/result DTOs;
- `PUBLIC_SCHEMA_VERSION`;
- `ClaimView`;
- renderer/commentary;
- LLM integration.

P10 owns the first evidence/claim boundary.

## 31. Probe budget assertions

Required:

```text
NOT_APPLICABLE: 0 P9 probes

eligible + 1 alternative:
  Batch A = 2
  optional Batch B = 0 or 1

eligible + 2 alternatives:
  Batch A = 3
  optional Batch B = 0 or 1

absolute maximum = 4
```

No I9 implementation path may execute a fifth probe.

## 32. Required adversarial cases

At minimum:

1. `ONLY_MOVE` forcedness hint but representative alternative has no concrete failure ->
   no literal-only benefit;
2. several equivalent best moves share the same verified benefit -> unique benefit REFUTED;
3. quiet positional BEST with P7 superiority but no strict cause -> INCONCLUSIVE;
4. selected alternative PV truncated mid-exchange -> preservation/material comparison
   INCONCLUSIVE;
5. raw rank / score superiority without concrete evidence -> no benefit;
6. alternative set contains duplicate canonical castling notation -> fail/normalize before
   selection, never duplicate probe;
7. candidate references unmappable piece -> fail closed before any early result gate;
8. different physical piece on the same square across branches -> not identity-equivalent;
9. material alternative loses a different piece of equal/greater value -> value-equivalent;
10. same benefit exists on best and alternative branches -> REFUTED as unique contrast;
11. tested ignored response Q loses, but no rule establishes it as the concrete tested threat ->
    do not manufacture MATE/MATERIAL_THREAT;
12. P7 batch mismatch -> fail closed;
13. engine identities differ across batches -> fail closed;
14. BLACK mover symmetry.

## 33. Real Stockfish integration gates

Real Stockfish must eventually demonstrate at least:

1. supported forcing / threat best move;
2. representative-only-move candidate where a selected alternative loses material or mate;
3. several-equivalent-moves position with no overstated uniqueness;
4. quiet positional best move -> INCONCLUSIVE with no invented benefit.

Tests should assert semantic outcomes, not exact PV suffixes or centipawn values.

## 34. Implementation packet boundaries

Recommended order:

```text
P9-I0  domain models + P9 error hierarchy
P9-I1  context validation + representative alternative selection
P9-I2  deterministic M/A branch contexts
P9-I3  bounded P7 protocol + compatibility checks
P9-I4  shared replay/material normalization
P9-I5  STRONG_MOVE benefit rules
P9-I6  ONLY_MOVE_CANDIDATE preservation rules
P9-I7  adversarial / coverage tests
P9-I8  real Stockfish integration
```

Each packet must stop for independent implementation review before the next begins.

## 35. Review questions

Independent review must explicitly answer:

1. Does P9 avoid treating P2 `ONLY_MOVE` as exhaustive proof?
2. Are representative alternatives selected deterministically and bounded to two?
3. Is P3 analysis used only for candidate selection, never mixed numerically with P7?
4. Is the maximum four-probe P9 protocol hard-bounded?
5. Can a raw evaluation gap become a benefit without concrete causal evidence? It must not.
6. Are truncated alternative lines treated as INCONCLUSIVE rather than absence?
7. Does material equivalence remain value-based while physical tactical identity remains
   `BasePieceRef`-based?
8. Can an arbitrary losing opponent response be mislabeled as proof of a universal threat?
   It must not.
9. Can P10 later distinguish representative-only evidence from literal exhaustive only-move
   proof? It must.
10. Does P9 remain internal until P10? It must.

## 36. Frozen design summary

```text
P9:
  explains verified benefits of BEST/EXCELLENT/GOOD moves
  compares at most two ranked serious alternatives
  uses max four P7 probes
  reuses exact P8 replay/material/identity rules
  never mixes P3 and P7 scores
  never turns MultiPV forcedness into literal uniqueness
  never invents positional reasons
  remains internal until P10
```
