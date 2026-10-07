# MVP-P10 — Evidence and ExplanationClaim design

Status: **design revision 2 for independent review**

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
    TESTED_RESPONSE = "tested_response"
    REPRESENTATIVE_ALTERNATIVES = "representative_alternatives"
```

`LOCAL` means the proposition itself does not claim exhaustive alternative coverage.

`TESTED_RESPONSE` means the proposition is explicitly conditional on one concrete opponent
response Q that was selected by the frozen P9 cause-specific selector and tested by
`IGNORE_THREAT`. It never means all ignored responses fail or that the threat is unstoppable.

`REPRESENTATIVE_ALTERNATIVES` means the proposition is explicitly bounded to P9's selected
top engine alternatives.

There is no `ALL_LEGAL_MOVES`, `EXHAUSTIVE`, or `ONLY_MOVE_PROVEN` scope in MVP-P10.

P9 preservation claims must use `REPRESENTATIVE_ALTERNATIVES`.
P9 Batch-B tested-threat claims must use `TESTED_RESPONSE`.

## 7. Structured claim entities

Claims must not embed prose as chess truth, but P11/P12 must also not reconstruct board truth
from a bare identity token.

Freeze three typed entities:

```python
@dataclass(frozen=True, slots=True)
class MoveClaimEntity:
    move: ChessMove
    position_id: str

@dataclass(frozen=True, slots=True)
class PieceClaimEntity:
    base_ref: BasePieceRef
    at_position_id: str
    current_square: str
    current_piece_type: PieceType

@dataclass(frozen=True, slots=True)
class SideClaimEntity:
    color: Color

ClaimEntity = MoveClaimEntity | PieceClaimEntity | SideClaimEntity
```

### 7.1 Identity authority

`BasePieceRef` remains the only physical piece identity.

`current_square`, `current_piece_type`, and `at_position_id` are presentation context only.
They must never participate in physical identity/equivalence decisions.

This handles:

- a moved piece whose base square differs from its current square;
- promotion, where the base identity remains the pawn but the current role is the promoted
  piece;
- castling/en-passant identity;
- later P12 naming without guessing from a square.

### 7.2 Presentation context derivation

P10 does not run python-chess or replay moves again.

Piece presentation context is derived only from already-retained P8/P9 `BoardDelta` /
identity-normalized evidence.

Move entities always carry the exact `position_id` from which the move is legal:

- played move and representative alternatives: base position;
- punishment / sole response / tested ignored response: the exact retained post-move position
  in which that move was legal.

If P10 cannot derive the correct position/square/current-role context from retained evidence,
it fails closed. P11/P12 must never infer or repair it.

### 7.3 Current P8/P9 claim subject

For all current P8/P9 explanation claims, the primary claim subject is the played
`MoveClaimEntity`.

Affected pieces, kings, punishment moves, sole responses, tested responses, and failed
representative alternatives are claim objects as required by the predicate.

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
    LEADS_TO_MATE = "leads_to_mate"
    WINS_MATERIAL = "wins_material"
    THREATENS_MATE_IF_IGNORED = "threatens_mate_if_ignored"
    THREATENS_MATERIAL_IF_IGNORED = "threatens_material_if_ignored"

    AVOIDS_REPRESENTATIVE_MATE_FAILURE = "avoids_representative_mate_failure"
    AVOIDS_REPRESENTATIVE_MATERIAL_LOSS = "avoids_representative_material_loss"
```

The vocabulary deliberately separates three propositions that P9 stores in nearby fields:

1. **direct Batch-A consequence under best defence**
   - `LEADS_TO_MATE`
   - `WINS_MATERIAL`
2. **one cause-specific ignored-response experiment**
   - `THREATENS_MATE_IF_IGNORED`
   - `THREATENS_MATERIAL_IF_IGNORED`
3. **exact sole legal response**
   - `FORCES_RESPONSE`

For `FORCES_RESPONSE`, P9's overloaded `tested_response` field means the exact sole legal
reply. It is **not** an `IGNORE_THREAT` experiment.

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
- subject is the canonical played-move entity for current P8/P9 builders;
- subject move is legal from `base_position_id`;
- objects contain no duplicates;
- every subject/object is present in the claim's referenced eligible evidence;
- every piece object preserves a `BasePieceRef` identity plus presentation context;
- every move object carries the exact position from which it is legal;
- evidence ids are non-empty, unique, and deterministically ordered;
- `importance` is `None` in P10 output;
- P11 owns selection/importance policy;
- preservation predicates require `REPRESENTATIVE_ALTERNATIVES`;
- tested-response predicates require `TESTED_RESPONSE`;
- every other current predicate uses `LOCAL`;
- no claim may use evidence from another group or base position.

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
- records are **per evidence group**; there is no cross-group evidence-record sharing;
- each P10 package consumes exactly one parent P8 result or one parent P9 result, so P8/P9
  family ordering never competes inside one package;
- adding a prior eligible evidence record may renumber later request-local ids.

P12/public projection must namespace package-local claim ids by analyzed move (for example by
move index or another request-local move key) before exposing claims from `analyze_game`.
P10 ids alone are not game-global identifiers.

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

One retained **non-terminal** `ProbeResult` carrying its normalized `EngineAnalysis`.

It preserves:

- immutable analysis position;
- engine identity;
- engine settings;
- normalized score/mate result;
- PV.

Exact terminal P7 outcomes do not become `EngineEvidence`; they remain inside
`CounterfactualEvidence`.

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

- **the complete ordered probe-result tuple used by the upstream P8/P9 decision for this
  source**, not a selected subset;
- exact terminal P7 outcomes as well as non-terminal probe results;
- the tested comparator/representative scope;
- tested response when present;
- whether the source form is direct or tested-response;
- upstream equivalence/contrast result when applicable.

For P8 this includes the actual line, comparator, and same-punishment probe when present.

For P9 this includes the played line, every retained representative alternative, and Batch B
only when the claim form is the tested-response form.

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

Evidence is grouped by the supported P8/P9 child source that produced it.

Freeze:

```python
class EvidenceSourceFamily(StrEnum):
    BAD_MOVE_CAUSE = "bad_move_cause"
    GOOD_MOVE_BENEFIT = "good_move_benefit"

class EvidenceForm(StrEnum):
    DIRECT = "direct"
    TESTED_RESPONSE = "tested_response"
    PRESERVATION = "preservation"
```

An `EvidenceGroup` carries the complete source descriptor needed by downstream builders:

- source family;
- exact source kind enum;
- source `BasePieceRef` subject tuple;
- canonical played move entity;
- evidence form;
- mate evidence level / exact-replay mate flag when applicable;
- sole response or tested response when applicable, with its legal-source position;
- representative alternatives and failed alternatives when applicable;
- the exact ordered `required_probe_results` used by the upstream decision;
- ordered evidence ids.

Only `EvidenceBuilder` reads raw P8/P9 result objects.

`ClaimBuilder` must build from validated `EvidenceGroup` + referenced evidence records and
must not re-read the raw P8/P9 result. This avoids two competing sources of truth.

P8/P9 already guarantee that `(kind, subject)` is unique within one parent result, so this is
a deterministic group key.

Records are owned by exactly one group and are never shared across groups.

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
- every evidence record belongs to exactly one group;
- every group evidence id resolves exactly once;
- all records/groups belong to the same base;
- each group's `CounterfactualEvidence` contains exactly that group's
  `required_probe_results` in retained order;
- evidence ordering is deterministic;
- groups exist only for supported source children;
- a bundle is built from one P8 parent result **or** one P9 parent result, never both.

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

`ClaimBuilder` consumes only a validated `EvidenceBundle`.

It does not receive or re-read the original P8/P9 explanation result.

It creates only predicates explicitly mapped below from each `EvidenceGroup.source_kind`,
`EvidenceGroup.evidence_form`, and the group's typed evidence.

It does not derive additional chess conclusions.

No supported evidence group -> no claim.

There is no fallback from engine rank, score, detector geometry, or an ungrouped evidence
record.

## 17. ClaimValidator

`ClaimValidator` validates the completed claim/evidence package before any claim is eligible
for P11.

### 17.1 Entity/provenance closure

For every claim:

- subject must equal the group's played-move entity;
- every claim object must appear in the claim's referenced eligible evidence;
- all move entities must carry the exact retained legal-source `position_id`;
- all piece entities must carry the same `BasePieceRef` identity and presentation context
  established by referenced evidence;
- every evidence id must belong to the same group and base.

### 17.2 EXACT

Requires predicate-specific deterministic evidence.

Current allowed EXACT mappings are only:

- P8 exact-immediate `MATE_ALLOWED -> ALLOWS_CHECKMATE`;
- P9 `FORCES_RESPONSE -> FORCES_RESPONSE`;
- P9 exact-immediate `MATE_THREAT -> DELIVERS_CHECKMATE`.

For `FORCES_RESPONSE`, exact board-fact evidence is built only from:

- the exact sole response retained by P9; and
- the matching P6 `FORCED_RESPONSE` candidate that P9 already cross-checked against legal
  moves.

The claim asserts only the local one-reply fact. It does not assert the P9 representative
contrast.

### 17.3 FORCED

`FORCED` is **unconditionally rejected in MVP-P10**.

No current evidence variant can carry the separately verified exhaustive forcing proof needed
to make it satisfiable.

This remains true for:

- one Stockfish PV;
- a mate score;
- P2 `ONLY_MOVE`;
- all retained representative alternatives failing.

### 17.4 ENGINE_VERIFIED

Requires a `CounterfactualEvidence` record whose probe-result tuple is exactly the group's
complete `required_probe_results`.

The validator rejects a subset that omits any comparator/representative probe used by the
upstream decision.

All referenced non-terminal engine analyses must share exactly one `EngineIdentity` and one
`EngineSettings` value.

Material claims additionally require replay/material provenance.

Mate claims additionally require the retained mate evidence level.

Tested-response predicates additionally require:

- `ClaimScope.TESTED_RESPONSE`;
- exactly the retained tested-response move object;
- an `IGNORE_THREAT` probe for that exact response inside the referenced
  `CounterfactualEvidence`.

Preservation predicates additionally require:

- `ClaimScope.REPRESENTATIVE_ALTERNATIVES`;
- failed-alternative move objects exactly matching the group's retained failed alternatives.

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

### 19.1 FORCES_RESPONSE

```text
FORCES_RESPONSE
 -> FORCES_RESPONSE
 -> EXACT
 -> LOCAL
```

The response object is the sole exact legal reply. Although P9 stores it in
`tested_response`, it is not an ignored-response experiment.

### 19.2 MATE_THREAT

The mapping depends on evidence form:

| P9 form | P10 predicate | confidence | scope |
|---|---|---|---|
| exact immediate mate by M | `DELIVERS_CHECKMATE` | `EXACT` | `LOCAL` |
| direct Batch-A mate consequence | `LEADS_TO_MATE` | `ENGINE_VERIFIED` | `LOCAL` |
| cause-specific Batch-B Q | `THREATENS_MATE_IF_IGNORED` | `ENGINE_VERIFIED` | `TESTED_RESPONSE` |

The tested form must include the exact Q move object and complete `IGNORE_THREAT`
counterfactual evidence.

### 19.3 MATERIAL_THREAT

The mapping depends on evidence form:

| P9 form | P10 predicate | confidence | scope |
|---|---|---|---|
| direct stable gain under Batch A | `WINS_MATERIAL` | `ENGINE_VERIFIED` | `LOCAL` |
| cause-specific Batch-B Q | `THREATENS_MATERIAL_IF_IGNORED` | `ENGINE_VERIFIED` | `TESTED_RESPONSE` |

A direct stable gain is deliberately not called a "threat".

A tested form must include the exact Q object and evidence that the tested line captured the
selected resource target, as already required by P9.

An equivalent representative benefit would have made the P9 candidate `REFUTED`; therefore
it does not reach P10.

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
source group, but an `ENGINE_VERIFIED` claim must always include the group's **complete**
`CounterfactualEvidence`.

Examples:

### FORCES_RESPONSE

Reference the deterministic board-fact/motif evidence built from the P9-validated sole reply
and matching `FORCED_RESPONSE` candidate.

Do not reference engine score to establish the local one-reply proposition.

### DELIVERS_CHECKMATE

Reference exact mate board/motif evidence.

### Direct engine-line mate/material consequences

Reference:

- the complete group `CounterfactualEvidence`;
- all required non-terminal `EngineEvidence`;
- variation/material or motif evidence required by the predicate.

### Tested-response threat claims

Reference:

- the complete group `CounterfactualEvidence` containing `IGNORE_THREAT(Q)`;
- the exact tested-response move entity;
- the relevant engine evidence;
- the exact mate/material/resource replay evidence.

### Preservation

Reference:

- the complete played/representative counterfactual evidence;
- relevant mate or material replay evidence;
- the exact failed-alternative move entities;
- representative-alternative scope metadata.

## 23. Deterministic ordering

Each P10 package contains exactly one parent family: P8 or P9.

Freeze source processing order:

1. child enum declaration order;
2. source subject base-square order.

Within one evidence group:

1. BoardFactEvidence;
2. MotifEvidence;
3. EngineEvidence in retained probe order;
4. VariationEvidence in retained probe/material order;
5. CounterfactualEvidence.

Evidence records are per-group and never shared.

Claims are ordered by `ClaimPredicate` declaration order, then canonical typed object
encoding.

Ids are minted only after this canonical ordering.

No set/hash iteration may affect output.

## 24. Failure semantics

P10 fails closed on:

- source/evidence base-position mismatch;
- supported source with missing required machine evidence;
- duplicate evidence id;
- unresolved claim evidence id;
- evidence from another group/base used by a claim;
- subject or object not present in referenced evidence;
- missing/invalid move source-position context;
- missing/invalid piece presentation context;
- invalid base-piece encoding;
- unsupported confidence/predicate combination;
- tested-response claim without tested-response scope and exact Q;
- preservation claim without representative scope;
- incomplete `CounterfactualEvidence` that omits any probe result used by upstream decision;
- mixed engine identity/settings inside one engine-verified claim;
- any P8/P9 claim mapped to `FORCED`;
- any literal-only/unique/exhaustive predicate;
- `literal_only_move_proven is not False`;
- material claim without eligible stable material evidence;
- exact mate claim without exact mate evidence;
- engine-verified claim with no eligible complete counterfactual provenance.

Use P10-owned errors under `CalliopeError`, for example:

```text
ExplanationEvidenceError
ExplanationClaimError
IncompatibleClaimEvidenceError
```

Ordinary inability to establish causality or absence of a supported P8/P9 source is not an
exception; it yields an empty evidence/claim result.

## 25. Empty result semantics

These are valid:

```text
quiet BEST + P9 INCONCLUSIVE -> no evidence groups, no claims
bad move + P8 INCONCLUSIVE   -> no evidence groups, no claims
refuted tested explanation   -> no positive claims
```

P10 must not fill the gap with an engine score, rank, positional narrative, or generic reason.

### 25.1 Explicit MVP limitation: exact local facts can remain silent

If P9's contrastive candidate is `REFUTED`, P10 emits no positive claim from that source even
when a local exact fact is independently true.

Example: the real P9 S3 fixture is an exact checkmating move, but its `MATE_THREAT` candidate
is REFUTED because representative alternatives also mate. Under MVP-P10 that source yields no
checkmate claim.

This is intentionally safe-but-silent.

P11/P12 must not backfill the missing local fact by re-analyzing the board or by stripping the
contrast from a refuted source.

A separate local-exact-fact claim path may be designed later.

## 26. Public boundary

P10 remains an **internal** trust-boundary packet.

Do not yet change:

- `CalliopeEngine`;
- `AnalyzeMoveService`;
- `MoveAnalysisResult`;
- `ClaimView`;
- `PUBLIC_SCHEMA_VERSION`;
- renderer/commentary behavior.

The existing public `ClaimView` remains only a reserved projection shape and is currently
insufficient for final P10 semantics because it has no explicit claim scope.

Before P12/public projection, the public contract must carry `ClaimScope` (and namespace
package-local claim ids for game-level output), with the appropriate schema-version decision.

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
5. tested-response threat changed to LOCAL or missing Q;
6. direct Batch-A consequence mislabeled as an ignored-response threat;
7. claim references unknown evidence id;
8. claim references another base;
9. claim subject/object absent from referenced evidence;
10. engine-verified claim with only a subset of required probes;
11. mixed engine identity/settings inside one claim;
12. exact claim with engine-only evidence;
13. unsupported source status manually fed to builder;
14. arbitrary P6 motif without P8/P9 support;
15. missing move source-position context;
16. promoted/moved piece rendered from base square/role only;
17. random/id ordering nondeterminism;
18. heuristic/positional predicate injection.

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
        ClaimConfidence / ClaimScope
        typed move/piece/side ClaimEntity values with presentation context
        ClaimPredicate / EvidenceForm
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
11. Are direct Batch-A consequences distinguishable from one tested ignored response? They must be.
12. Can P11/P12 render every move/piece entity without reconstructing board truth? They must be able to.
13. Does every ENGINE_VERIFIED claim retain the complete probe set used by the upstream decision? It must.

## 33. Frozen summary

```text
P10:
  consumes only reviewed P8/P9 supported explanation records
  converts retained provenance into typed evidence
  emits only closed-vocabulary ExplanationClaim values
  distinguishes direct consequence from one tested ignored response
  carries render-safe move/piece context without changing BasePieceRef identity
  keeps exact / engine-verified / forced semantics distinct
  rejects FORCED unconditionally in MVP
  requires complete upstream probe provenance for ENGINE_VERIFIED claims
  preserves representative-only scope for P9 preservation
  never turns engine preference into explanation
  never invents positional or intent claims
  remains internal until P11/P12 selection/projection
```
