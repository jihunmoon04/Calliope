# MVP-P10 — Evidence and ExplanationClaim design

Status: **design draft for independent review**

Baseline: `main @ c2c75a7cb17992fedc37e3235230493947df60f2`

## 1. Goal

P10 creates the hard trust boundary between chess analysis and language.

P8 and P9 already decide whether a concrete bad-move cause or good-move benefit is
`SUPPORTED`, `REFUTED`, `INCONCLUSIVE`, or not applicable. P10 must not rediscover chess.
It converts only eligible, already-supported machine evidence into:

```text
typed Evidence records
        ↓
validated ExplanationClaim values
```

Only `ExplanationClaim` values are eligible to reach P11/P12/P13.

The central rule is:

> A fact may be true without being an explanation. A proposition may reach language only when
> its complete P10 claim contract is supported by eligible P8/P9 evidence.

P10 performs no Stockfish search, no python-chess analysis, no P7 probe, no tactical detection,
and no LLM call.

## 2. Scope

P10 owns:

- immutable internal evidence records;
- deterministic request-scoped evidence ids;
- immutable `ExplanationClaim` values;
- claim confidence and scope;
- deterministic claim ids;
- P8 supported-cause -> evidence/claim mapping;
- P9 supported-benefit -> evidence/claim mapping;
- claim/evidence compatibility validation;
- strict rejection of unsupported, heuristic, exhaustive-only, or provenance-broken claims.

P10 does **not** own:

- explanation graph relations;
- minimal claim selection;
- importance/ranking policy;
- deterministic prose;
- LLM verbalization;
- public application-pipeline wiring;
- a new forcedness proof;
- positional interpretation.

Those remain P11/P12/P13 or later work.

## 3. Inputs

P10 accepts the already-reviewed P8/P9 internal result families:

```text
BadMoveExplanationResult
  └─ BadMoveCauseResult

GoodMoveExplanationResult
  └─ GoodMoveBenefitResult
```

Only child records with status `SUPPORTED` are claim-eligible.

A parent result that is `REFUTED`, `INCONCLUSIVE`, or `NOT_APPLICABLE` produces no
positive claims.

A `SUPPORTED` parent may contain supported, refuted, and inconclusive child candidates.
P10 uses only the supported children.

P10 never changes the original `MoveJudgement`.

## 4. Package placement

Add internal domain values under:

```text
src/calliope/domain/explanation/
  evidence.py
  claim.py
```

and deterministic services under:

```text
src/calliope/services/explanation/
  evidence_builder.py
  claim_builder.py
  claim_validator.py
```

Domain modules may depend only on Calliope domain values.

No adapter, application facade, Stockfish, python-chess, provider SDK, renderer, or LLM import
is allowed in the P10 domain layer.

## 5. Claim confidence

Freeze:

```python
class ClaimConfidence(StrEnum):
    EXACT = "exact"
    FORCED = "forced"
    ENGINE_VERIFIED = "engine_verified"
```

`HEURISTIC` is deliberately absent from the strict P10 MVP claim vocabulary.

The public option `allow_heuristic_claims` remains dormant until a later positional/heuristic
design explicitly defines evidence eligibility.

### EXACT

The full proposition follows from deterministic board/rule evidence already verified by the
upstream pipeline.

A claim is not `EXACT` merely because one component of it is exact.

### FORCED

Reserved for a separately verified exhaustive forcing proof.

Current P8/P9 do **not** provide that proof.

Therefore:

```text
P8 -> FORCED: never
P9 -> FORCED: never
```

The enum exists as part of the P10 compatibility contract, but the P8/P9 builders must not emit
it.

A single Stockfish PV, a mate score, P2 `ForcednessLevel.ONLY_MOVE`, and a representative set
of alternatives are all insufficient.

### ENGINE_VERIFIED

The proposition is supported by controlled P7/engine counterfactual evidence and the exact
replay/material/identity checks already performed by P8/P9.

## 6. Claim scope

Confidence and scope are orthogonal.

Freeze:

```python
class ClaimScope(StrEnum):
    LOCAL = "local"
    REPRESENTATIVE_ALTERNATIVES = "representative_alternatives"
```

`LOCAL` means the proposition itself does not claim exhaustive alternative coverage.

`REPRESENTATIVE_ALTERNATIVES` means the proposition is explicitly bounded to P9's selected
top engine alternatives.

There is no `ALL_LEGAL_MOVES`, `EXHAUSTIVE`, or `ONLY_MOVE_PROVEN` scope in MVP-P10.

P9 preservation claims must use `REPRESENTATIVE_ALTERNATIVES`.

## 7. Structured claim entities

Claims must not embed prose as chess truth.

Freeze:

```python
class ClaimEntityKind(StrEnum):
    MOVE = "move"
    PIECE = "piece"
    SIDE = "side"

@dataclass(frozen=True, slots=True)
class ClaimEntity:
    kind: ClaimEntityKind
    value: str
```

Canonical encodings:

```text
MOVE  -> canonical UCI
PIECE -> "<color>:<piece_type>:<base_square>"
SIDE  -> "white" | "black"
```

`PIECE` always uses `BasePieceRef` anchored to the common base position. Current-square
identity is never durable claim identity.

For all P8/P9 explanation claims, the primary subject is the played move.

Affected pieces, punishment moves, tested responses, failed representative alternatives, and
kings are claim objects as needed.

## 8. Claim predicate vocabulary

Freeze the strict MVP-P10 vocabulary:

```python
class ClaimPredicate(StrEnum):
    LEAVES_PIECE_HANGING = "leaves_piece_hanging"
    REMOVES_DEFENDER = "removes_defender"
    ALLOWS_FORK = "allows_fork"
    ALLOWS_CHECKMATE = "allows_checkmate"
    ALLOWS_MATERIAL_LOSS = "allows_material_loss"

    FORCES_RESPONSE = "forces_response"
    DELIVERS_CHECKMATE = "delivers_checkmate"
    CREATES_MATE_THREAT = "creates_mate_threat"
    CREATES_MATERIAL_THREAT = "creates_material_threat"

    AVOIDS_REPRESENTATIVE_MATE_FAILURE = "avoids_representative_mate_failure"
    AVOIDS_REPRESENTATIVE_MATERIAL_LOSS = "avoids_representative_material_loss"
```

No predicate may encode:

- literal only move;
- exhaustive uniqueness;
- inferred player intent;
- positional improvement;
- initiative;
- space;
- king-safety narrative;
- strategic plan.

Those propositions do not exist in strict MVP-P10.

## 9. ExplanationClaim

Freeze:

```python
@dataclass(frozen=True, slots=True)
class ExplanationClaim:
    claim_id: str
    base_position_id: str
    subject: ClaimEntity
    predicate: ClaimPredicate
    objects: tuple[ClaimEntity, ...]
    confidence: ClaimConfidence
    scope: ClaimScope
    evidence_ids: tuple[str, ...]
    importance: float | None = None
```

Invariants:

- non-empty `claim_id` and `base_position_id`;
- subject is a canonical played-move entity for current P8/P9 builders;
- objects contain no duplicates;
- evidence ids are non-empty, unique, and deterministically ordered;
- `importance` is `None` in P10 output;
- P11 owns selection/importance policy;
- a preservation predicate requires `REPRESENTATIVE_ALTERNATIVES`;
- all other current predicates use `LOCAL`;
- no claim may use evidence from another base position.

## 10. Request-scoped deterministic ids

P10 ids are deterministic within one built explanation package, not global durable database ids.

After canonical source/evidence ordering:

```text
ev_001
ev_002
...

cl_001
cl_002
...
```

Properties:

- deterministic for identical input evidence;
- no Python `hash()`;
- no UUID/randomness;
- ids must not be treated as globally stable cache keys;
- adding a prior eligible evidence record may renumber later request-local ids.

This is sufficient for P11/P12/P13 claim references and keeps the MVP contract simple.

## 11. Evidence variants

Freeze the five variants already named by the MVP plan.

### 11.1 BoardFactEvidence

Deterministic board/rule evidence retained from the validated P8/P9 source.

It may retain:

- relevant `BoardDelta` values;
- base-normalized subjects;
- played/punishment/response moves;
- exact mate/reply facts represented by the upstream supported record.

It does not run rules again.

### 11.2 EngineEvidence

One retained non-terminal `ProbeResult` carrying its normalized `EngineAnalysis`.

It preserves:

- immutable analysis position;
- engine identity;
- engine settings;
- normalized score/mate result;
- PV.

Raw UCI process output is never evidence-domain data.

### 11.3 VariationEvidence

Evidence that a P8/P9 line was replayed through exact rules before reaching P10.

It retains only already-validated domain data, including when relevant:

- originating `CounterfactualProbe`;
- material evidence;
- relevant replay-backed `BoardDelta` values;
- exact-terminal/checkmate flag.

VariationEvidence does not make a PV `FORCED`.

### 11.4 CounterfactualEvidence

A bounded causal/contrastive experiment over retained P7 results.

It records:

- the relevant P7 probe results in canonical order;
- the tested comparator/representative scope;
- tested response when present;
- upstream equivalence/contrast result when applicable.

It never broadens the tested scope.

### 11.5 MotifEvidence

Relevant P6 `TacticalCandidate` values plus their already-normalized `BasePieceRef` subjects.

A motif record is supporting evidence only.

Generic motif geometry alone cannot create a claim.

## 12. Evidence records

Every evidence variant has at least:

```text
evidence_id
base_position_id
```

and immutable variant-specific data.

All evidence objects must consist exclusively of reviewed Calliope domain values.

No mutable board, adapter handle, engine process, raw provider payload, prose explanation, or
arbitrary dict is allowed.

## 13. Evidence groups

Evidence is grouped by the supported P8/P9 source that produced it.

Freeze an internal source family:

```python
class EvidenceSourceFamily(StrEnum):
    BAD_MOVE_CAUSE = "bad_move_cause"
    GOOD_MOVE_BENEFIT = "good_move_benefit"
```

An evidence group identifies:

- source family;
- source kind;
- source `BasePieceRef` subject tuple;
- ordered evidence ids.

P8/P9 already guarantee that `(kind, subject)` is unique within one result, so this is a
deterministic source key.

The group does not itself become a language claim.

## 14. EvidenceBundle

Freeze:

```python
@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    base_position_id: str
    evidence: tuple[EvidenceRecord, ...]
    groups: tuple[EvidenceGroup, ...]
```

Invariants:

- every evidence id is unique;
- every group evidence id resolves exactly once;
- all records/groups belong to the same base;
- evidence ordering is deterministic;
- groups exist only for supported source children.

## 15. EvidenceBuilder policy

`EvidenceBuilder` is a pure deterministic mapper.

It must not:

- call P4/P5/P6/P7;
- call Stockfish;
- call python-chess;
- change a P8/P9 status;
- reinterpret a refuted/inconclusive source as evidence;
- infer missing evidence.

For every supported source child it retains the already-present machine provenance needed by
its P10 mapping.

A supported source that is structurally missing evidence required by its frozen mapping is an
incompatible P10 input and fails closed.

## 16. ClaimBuilder policy

`ClaimBuilder` consumes:

- the original P8/P9 explanation result;
- the validated `EvidenceBundle`.

It creates only predicates explicitly mapped below.

It does not derive additional chess conclusions.

No supported source -> no claim.

Refuted/inconclusive source -> no positive claim.

## 17. ClaimValidator

`ClaimValidator` validates the completed claim/evidence package before any claim is eligible
for P11.

Minimum compatibility:

### EXACT

Requires predicate-specific deterministic evidence.

Current allowed EXACT mappings are only:

- P8 exact-immediate `MATE_ALLOWED -> ALLOWS_CHECKMATE`;
- P9 `FORCES_RESPONSE -> FORCES_RESPONSE`;
- P9 exact-immediate `MATE_THREAT -> DELIVERS_CHECKMATE`.

### FORCED

Requires a separately marked exhaustive forcing proof.

No current P8/P9 builder can supply one.

Any P8/P9-built `FORCED` claim is invalid.

### ENGINE_VERIFIED

Requires engine/counterfactual provenance appropriate to the predicate.

At least one `CounterfactualEvidence` or eligible `EngineEvidence` must be referenced.

Material claims additionally require replay/material provenance.

Mate claims additionally require the retained mate evidence level.

## 18. P8 mapping

Only `BadMoveCauseStatus.SUPPORTED` maps.

| P8 cause | P10 predicate | confidence | scope |
|---|---|---|---|
| `NEWLY_HANGING_PIECE` | `LEAVES_PIECE_HANGING` | `ENGINE_VERIFIED` | `LOCAL` |
| `REMOVED_DEFENDER` | `REMOVES_DEFENDER` | `ENGINE_VERIFIED` | `LOCAL` |
| `FORK_ALLOWED` | `ALLOWS_FORK` | `ENGINE_VERIFIED` | `LOCAL` |
| `MATE_ALLOWED` + `EXACT_IMMEDIATE` | `ALLOWS_CHECKMATE` | `EXACT` | `LOCAL` |
| `MATE_ALLOWED` + `ENGINE_LINE` | `ALLOWS_CHECKMATE` | `ENGINE_VERIFIED` | `LOCAL` |
| `MATERIAL_LOSS_LINE` | `ALLOWS_MATERIAL_LOSS` | `ENGINE_VERIFIED` | `LOCAL` |

Notes:

- `ENGINE_LINE` mate is never `FORCED`;
- `MATERIAL_LOSS_LINE` is never `FORCED_MATERIAL_LOSS`;
- comparator evidence remains bounded to P8's engine-best comparator;
- a true P6 motif without P8 support creates no claim.

Recommended objects:

- base-normalized source subject pieces;
- punishment move when present.

The comparator move remains evidence/provenance and does not imply an exhaustive claim.

## 19. P9 STRONG_MOVE mapping

Only `GoodMoveBenefitStatus.SUPPORTED` maps.

| P9 benefit | P10 predicate | confidence | scope |
|---|---|---|---|
| `FORCES_RESPONSE` | `FORCES_RESPONSE` | `EXACT` | `LOCAL` |
| `MATE_THREAT` + `EXACT_IMMEDIATE` | `DELIVERS_CHECKMATE` | `EXACT` | `LOCAL` |
| `MATE_THREAT` + `ENGINE_LINE` | `CREATES_MATE_THREAT` | `ENGINE_VERIFIED` | `LOCAL` |
| `MATERIAL_THREAT` | `CREATES_MATERIAL_THREAT` | `ENGINE_VERIFIED` | `LOCAL` |

Objects may include:

- base-normalized affected pieces/king;
- exact sole response;
- tested ignored response when it is part of the supported threat.

An equivalent representative benefit would have made the P9 candidate `REFUTED`; therefore it
does not reach P10.

## 20. P9 ONLY_MOVE_CANDIDATE mapping

Only supported preservation benefits map.

| P9 benefit | P10 predicate | confidence | scope |
|---|---|---|---|
| `PREVENTS_MATE` | `AVOIDS_REPRESENTATIVE_MATE_FAILURE` | `ENGINE_VERIFIED` | `REPRESENTATIVE_ALTERNATIVES` |
| `PREVENTS_MATERIAL_LOSS` | `AVOIDS_REPRESENTATIVE_MATERIAL_LOSS` | `ENGINE_VERIFIED` | `REPRESENTATIVE_ALTERNATIVES` |

The claim objects include:

- affected base-normalized king/pieces;
- exactly the failed representative alternative moves in rank order.

Even when all retained representative alternatives fail:

```text
scope = REPRESENTATIVE_ALTERNATIVES
confidence != FORCED
```

P10 must never mint a predicate or object meaning:

```text
only move
unique legal solution
all legal alternatives fail
```

`GoodMoveExplanationResult.literal_only_move_proven` must still be `False`.

If it is ever not exactly `False`, P10 fails closed.

## 21. Why preservation remains ENGINE_VERIFIED

P9 may contain exact immediate mate or exact material events on a failed representative branch.

That does not make the broader preservation proposition exhaustive.

The P10 claim means:

> the played move avoids the verified failure observed on the selected representative alternatives.

It does not mean:

> every other legal move fails.

Therefore current preservation claims stay `ENGINE_VERIFIED` with representative scope.

## 22. Evidence selection per claim

A claim references only the evidence required for that proposition, not every record in its
source group.

Examples:

### FORCES_RESPONSE

Reference deterministic rule/motif evidence for the exact sole reply.

Do not require the claim itself to reference engine scores.

### DELIVERS_CHECKMATE

Reference exact mate board/motif evidence.

### Engine-line mate/material/threat claims

Reference:

- relevant counterfactual evidence;
- relevant engine evidence;
- variation/material or motif evidence required by that predicate.

### Preservation

Reference:

- played/failed-alternative counterfactual evidence;
- relevant mate or material replay evidence;
- representative-alternative scope metadata.

## 23. Deterministic ordering

Freeze source processing order:

1. P8/P9 child enum declaration order;
2. source subject base-square order.

Within one evidence group:

1. BoardFactEvidence;
2. MotifEvidence;
3. EngineEvidence in retained probe order;
4. VariationEvidence in retained probe/material order;
5. CounterfactualEvidence.

Claims are ordered by `ClaimPredicate` declaration order, then object entity encoding.

Ids are minted only after this canonical ordering.

No set/hash iteration may affect output.

## 24. Failure semantics

P10 fails closed on:

- source/evidence base-position mismatch;
- supported source with missing required machine evidence;
- duplicate evidence id;
- unresolved claim evidence id;
- evidence from another group/base used by a claim;
- invalid base-piece encoding;
- unsupported confidence/predicate combination;
- preservation claim without representative scope;
- P8/P9 claim mapped to `FORCED`;
- any literal-only/unique/exhaustive predicate;
- `literal_only_move_proven is not False`;
- material claim without eligible stable material evidence;
- exact mate claim without exact mate evidence;
- engine-verified claim with no eligible engine/counterfactual provenance.

Use P10-owned errors under `CalliopeError`, for example:

```text
ExplanationEvidenceError
ExplanationClaimError
IncompatibleClaimEvidenceError
```

Ordinary absence of a supported P8/P9 explanation is not an error; it yields an empty
evidence/claim result.

## 25. Empty result semantics

These are valid:

```text
quiet BEST + P9 INCONCLUSIVE -> no evidence groups, no claims
bad move + P8 INCONCLUSIVE   -> no evidence groups, no claims
refuted tested explanation   -> no positive claims
```

P10 must not fill the gap with an engine score, rank, positional narrative, or generic reason.

## 26. Public boundary

P10 remains an **internal** trust-boundary packet.

Do not yet change:

- `CalliopeEngine`;
- `AnalyzeMoveService`;
- `MoveAnalysisResult`;
- `ClaimView`;
- `PUBLIC_SCHEMA_VERSION`;
- renderer/commentary behavior.

The existing public `ClaimView` remains the reserved serialized projection.

P11/P12 application integration will decide which validated claims are selected/projected.

This prevents exposing an unselected raw claim set as if it were the final explanation.

## 27. No importance in P10

`importance` remains `None` on every P10-built claim.

P11 owns minimal sufficient selection and relative priority.

P10 must not encode engine score magnitude as importance.

## 28. Strict no-score rule

P10 may retain normalized engine observations inside evidence.

It must not derive claim eligibility from raw:

- cp magnitude;
- WDL magnitude;
- rank;
- cp loss;
- expected-score loss.

Eligibility is inherited from the reviewed P8/P9 `SUPPORTED` result and predicate-specific
machine evidence.

P10 must never numerically mix P2 and P7 values.

## 29. Test gates

### Domain

Test:

- all claim/evidence invariants;
- canonical entity encoding;
- duplicate ids/objects;
- cross-position rejection;
- confidence/scope compatibility;
- deterministic id/order behavior.

### P8 mapping

Cover all five P8 cause kinds.

At minimum pin:

- detector-only motif -> no claim;
- exact immediate mate -> EXACT;
- engine-line mate -> ENGINE_VERIFIED;
- material-loss line -> ENGINE_VERIFIED, never FORCED;
- refuted/inconclusive cause -> no claim.

### P9 mapping

Cover all five benefit kinds.

At minimum pin:

- sole legal response -> EXACT;
- exact immediate mate -> EXACT;
- engine mate threat -> ENGINE_VERIFIED;
- material threat -> ENGINE_VERIFIED;
- preservation -> representative scope + ENGINE_VERIFIED;
- all representative alternatives failing still not literal-only;
- quiet best -> empty claims;
- equivalent benefit REFUTED -> no positive claim.

### Adversarial

Attempt:

1. P8 engine-line mate -> FORCED;
2. P8 material line -> FORCED;
3. P9 ONLY_MOVE hint -> literal-only predicate;
4. preservation scope changed to LOCAL;
5. claim references unknown evidence id;
6. claim references another base;
7. engine-verified claim with board evidence only;
8. exact claim with engine-only evidence;
9. unsupported source status manually fed to builder;
10. arbitrary P6 motif without P8/P9 support;
11. random/id ordering nondeterminism;
12. heuristic/positional predicate injection.

All must fail or yield no claim as appropriate.

## 30. Real Stockfish gate

P10 should finish with real-engine integration using already-stable P8/P9 semantic fixtures.

Required classes:

1. P8 exact-immediate mate -> `ALLOWS_CHECKMATE / EXACT`;
2. P8 engine-verified material or tactical cause -> `ENGINE_VERIFIED`;
3. P9 supported strong move -> eligible claim;
4. P9 real ONLY_MOVE preservation -> representative-scoped claim, never FORCED;
5. P9 equivalent-move result -> no positive equivalent benefit claim;
6. P9 quiet BEST -> zero claims.

Assert semantic claim/evidence results, not exact cp/PV suffixes.

## 31. Implementation packets

Recommended sequence:

```text
P10-A0  design freeze and independent design review

P10-I0  explanation domain:
        ClaimConfidence / ClaimScope / ClaimEntity / ClaimPredicate
        evidence variants / EvidenceBundle / ExplanationClaim
        P10 error hierarchy / deterministic ids

P10-I1  P8 EvidenceBuilder

P10-I2  P8 ClaimBuilder + compatibility validation

P10-I3  P9 STRONG_MOVE evidence/claim mapping

P10-I4  P9 ONLY_MOVE_CANDIDATE mapping and representative-scope safety

P10-I5  integrated ClaimValidator + adversarial/mutation coverage

P10-I6  real Stockfish evidence -> claim acceptance gate
```

Every packet stops for independent implementation review before the next.

## 32. Review questions

Independent design review must explicitly answer:

1. Can any refuted/inconclusive P8/P9 source create a positive claim? It must not.
2. Can a detector-only motif create a claim? It must not.
3. Can a single PV/mate score become FORCED? It must not.
4. Can P2 ONLY_MOVE become literal/exhaustive uniqueness? It must not.
5. Are preservation claims visibly bounded to representative alternatives? They must be.
6. Can an engine score magnitude create a claim by itself? It must not.
7. Does every claim resolve to same-position evidence ids? It must.
8. Are P8/P9 current piece identities normalized through BasePieceRef before claims? They must be.
9. Are ids/order deterministic without random/hash iteration? They must be.
10. Does P10 remain independent of language generation and public application wiring? It must.

## 33. Frozen summary

```text
P10:
  consumes only reviewed P8/P9 supported explanation records
  converts retained provenance into typed evidence
  emits only closed-vocabulary ExplanationClaim values
  keeps exact / engine-verified / forced semantics distinct
  emits no FORCED claim from current P8/P9
  preserves representative-only scope for P9 preservation
  never turns engine preference into explanation
  never invents positional or intent claims
  remains internal until P11/P12 selection/projection
```
