# MVP-P11 — Explanation Selection and Relation-Safe Graph

Status: **A0 design draft for independent review**

P11 is the deterministic layer between the verified P10 claim package and later rendering.

Its job is to choose a compact set of already-verified claims. It does **not** discover new
chess facts, strengthen confidence, reinterpret engine scores, or verbalize the position.

The central safety rule is:

> **P10 proves claims. P11 may select claims, but it may not invent relations between them
> unless a frozen relation rule has independent retained provenance.**

The current P10 package contains per-claim evidence authority but no cross-claim relation
provenance. Therefore the initial MVP-P11 implementation freezes relation vocabulary and graph
shape, while emitting **no automatic claim-to-claim edges**. Selection remains useful and
complete without speculative causal edges.

---

## 1. Purpose

Canonical pipeline:

```text
validated P10 EvidenceBundle + ExplanationClaim tuple
  -> P11 P10 revalidation
  -> relation-safe ExplanationGraph
  -> deterministic minimal selection
  -> ExplanationSelection
  -> P12 deterministic renderer
```

P11 owns:

- deterministic claim priority;
- compact selection, normally 1–3 claims;
- duplicate semantic-family suppression;
- relation/graph domain contracts;
- selection integrity and determinism.

P11 does **not** own:

- chess analysis;
- move legality;
- Stockfish/P7 execution;
- score interpretation;
- new evidence;
- new claims or predicates;
- confidence/scope strengthening;
- public DTO projection;
- prose;
- LLM behavior.

---

## 2. Inputs

P11 accepts exactly one complete P10 package:

```python
EvidenceBundle
tuple[ExplanationClaim, ...]
```

The package must already be valid under the canonical P10 ClaimValidator.

P11 nevertheless re-runs the correct P10 validation entrypoint before selection:

- BAD_MOVE_CAUSE bundle -> `ClaimValidator.validate_bad_move`
- GOOD_MOVE_BENEFIT bundle -> `ClaimValidator.validate_good_move`

P11 never treats caller possession of an `ExplanationClaim` as proof that the package is valid.

Mixed P8/P9 families remain invalid.

Empty P10 package:

```text
EvidenceBundle(base, (), ()) + ()
```

is valid and produces an empty graph/selection.

---

## 3. Why P11 must not infer cross-claim causality

P10 deliberately guarantees:

- evidence is owned by exactly one EvidenceGroup;
- one claim maps to one group;
- claims are independently evidence-backed;
- cross-group evidence sharing is forbidden.

P10 does **not** provide a record saying, for example:

```text
LEAVES_PIECE_HANGING(cl_001)
  CAUSES
ALLOWS_MATERIAL_LOSS(cl_002)
```

Two claims may:

- share a BasePieceRef;
- occur on the same retained engine line;
- have related predicates;
- both be true;

without P10 proving that one claim causes the other.

Therefore P11 must not create relation edges merely from:

- shared piece identity;
- shared move identity;
- same base position;
- same engine identity/settings;
- adjacent claim order;
- predicate names;
- overlapping board deltas;
- similar variation lines.

Those observations are insufficient relation authority.

A future packet may activate individual relation rules only after the required relation provenance
is explicitly designed and independently reviewed.

---

## 4. Relation vocabulary

Reserve the roadmap vocabulary internally:

```python
class ExplanationRelationKind(StrEnum):
    ENABLES = "enables"
    PREVENTS = "prevents"
    LEADS_TO = "leads_to"
    CAUSES = "causes"
    CONTRASTS_WITH = "contrasts_with"
    SUPPORTS = "supports"
```

The enum is internal and does not change the public schema.

### Initial MVP activation rule

For MVP-P11:

```text
ACTIVE_RELATION_RULES = ()
```

Therefore the canonical P11 graph builder emits:

```text
relations == ()
```

for every current P8/P9 package.

This is intentional, not an unfinished fallback.

A non-empty relation supplied by a caller must not be silently accepted as if P11 had verified it.

---

## 5. Relation domain model

Freeze the internal shape:

```python
@dataclass(frozen=True, slots=True)
class ExplanationRelation:
    relation_id: str
    base_position_id: str
    source_claim_id: str
    kind: ExplanationRelationKind
    target_claim_id: str
    evidence_ids: tuple[str, ...]
```

Structural invariants:

- canonical request-local `rel_001`, `rel_002`, ... id;
- non-empty base position id;
- source and target claim ids are canonical claim ids;
- source != target;
- kind is an exact `ExplanationRelationKind`;
- evidence ids are non-empty, canonical, unique;
- relation evidence ids must later resolve inside the same P10 package;
- duplicate `(source_claim_id, kind, target_claim_id)` relations are forbidden.

Although the model can represent future reviewed relations, current P11 policy does not mint any.

---

## 6. ExplanationGraph

Freeze:

```python
@dataclass(frozen=True, slots=True)
class ExplanationGraph:
    base_position_id: str
    claims: tuple[ExplanationClaim, ...]
    relations: tuple[ExplanationRelation, ...]
```

Graph invariants:

- base id is non-empty;
- claims are exactly the validated P10 claim tuple;
- every claim belongs to the graph base;
- claim ids are unique and canonical;
- relations belong to the same base;
- every relation endpoint resolves to exactly one graph claim;
- every relation evidence id belongs to the union of its two endpoint claims' evidence ids;
- relation ids are unique and canonical;
- relation tuple order is deterministic.

Current graph-builder policy additionally requires:

```text
relations == ()
```

because there is no active relation rule.

The builder does not clone, rewrite, renumber, or mutate P10 claims.

---

## 7. ExplanationSelection

Freeze:

```python
@dataclass(frozen=True, slots=True)
class ExplanationSelection:
    base_position_id: str
    selected_claim_ids: tuple[str, ...]
    selected_relation_ids: tuple[str, ...] = ()
```

Invariants:

- base id is non-empty;
- selected claim ids are unique and canonical;
- maximum selected claim count is 3;
- selected relation ids are unique and canonical;
- every selected relation has both endpoints selected;
- empty graph -> empty selection.

The selection contains ids rather than copied claims. P12 resolves them against the graph.

P11 never writes `ExplanationClaim.importance`; P10 claims remain byte/structurally unchanged.

---

## 8. Selection families

Minimal selection suppresses multiple claims that serve the same explanatory role.

Freeze these internal selection families:

### MATE_OUTCOME

- `ALLOWS_CHECKMATE`
- `DELIVERS_CHECKMATE`
- `LEADS_TO_MATE`
- `AVOIDS_REPRESENTATIVE_MATE_FAILURE`

### MATERIAL_OUTCOME

- `ALLOWS_MATERIAL_LOSS`
- `WINS_MATERIAL`
- `AVOIDS_REPRESENTATIVE_MATERIAL_LOSS`

### TACTICAL_MECHANISM

- `LEAVES_PIECE_HANGING`
- `REMOVES_DEFENDER`
- `ALLOWS_FORK`

### FORCED_RESPONSE

- `FORCES_RESPONSE`

### TESTED_THREAT

- `THREATENS_MATE_IF_IGNORED`
- `THREATENS_MATERIAL_IF_IGNORED`

At most one claim from each family may be selected.

This is presentation minimization only. Suppressing a claim from the primary selection does not
invalidate or delete it from the graph.

---

## 9. Priority policy

P11 priority is semantic and deterministic. It never reads score magnitude, WDL, engine rank,
cp loss, expected-score loss, PV length, mate distance, or MultiPV position.

Freeze these tiers, lower number first:

### Tier 0 — exact checkmate outcome

- `DELIVERS_CHECKMATE / EXACT`
- `ALLOWS_CHECKMATE / EXACT`

### Tier 1 — verified mate/material consequence

- `ALLOWS_CHECKMATE / ENGINE_VERIFIED`
- `LEADS_TO_MATE`
- `AVOIDS_REPRESENTATIVE_MATE_FAILURE`
- `ALLOWS_MATERIAL_LOSS`
- `WINS_MATERIAL`
- `AVOIDS_REPRESENTATIVE_MATERIAL_LOSS`

### Tier 2 — verified tactical mechanism

- `LEAVES_PIECE_HANGING`
- `REMOVES_DEFENDER`
- `ALLOWS_FORK`

### Tier 3 — exact forced response

- `FORCES_RESPONSE`

### Tier 4 — tested threat

- `THREATENS_MATE_IF_IGNORED`
- `THREATENS_MATERIAL_IF_IGNORED`

No current P10 claim is allowed to use `FORCED`. If P10 validation rejects it, P11 never ranks it.

Within the same tier, use the already-frozen canonical P10 claim order. Do not add a second
predicate-specific ranking table.

---

## 10. Minimal selection algorithm

Given a validated canonical claim tuple:

1. If no claims exist, return the empty selection.
2. Assign each claim its frozen priority tier and selection family.
3. Stable-sort by:
   - priority tier;
   - existing canonical P10 claim tuple position.
4. Iterate in that order.
5. Select the first claim whose selection family has not yet been selected.
6. Stop after 3 selected claims or after all claims are exhausted.
7. Select only relations whose two endpoints are selected.
8. Under current relation policy, selected relations are always empty.

Properties:

- no claim synthesis;
- no claim deletion from the graph;
- no confidence/scope rewrite;
- no score-based tie break;
- deterministic;
- output size 0–3;
- at most one primary claim per explanatory family.

---

## 11. Examples

### P8 hanging piece + material loss

If P10 contains:

```text
LEAVES_PIECE_HANGING / ENGINE_VERIFIED
ALLOWS_MATERIAL_LOSS / ENGINE_VERIFIED
```

selection is:

```text
ALLOWS_MATERIAL_LOSS
LEAVES_PIECE_HANGING
```

because consequence tier precedes tactical-mechanism tier.

No `CAUSES` or `LEADS_TO` edge is minted.

### P8 exact mate + tactical mechanism

An exact `ALLOWS_CHECKMATE` is the anchor. A distinct mechanism family may also be selected,
up to the three-claim cap.

### P9 FORCES_RESPONSE only

Selection contains exactly that claim.

### P9 ONLY_MOVE preservation

A representative-scoped preservation claim remains representative-scoped in P11. P11 must not
rewrite it into "only move", "unique solution", or `FORCED`.

### Equivalent / quiet P9

An empty P10 package remains an empty P11 graph and selection.

---

## 12. GraphBuilder policy

Suggested service:

```text
src/calliope/services/explanation/graph_builder.py
```

Responsibilities:

- accept one P10 bundle + claim tuple;
- dispatch and run the correct P10 ClaimValidator;
- preserve the exact validated claim tuple;
- produce an `ExplanationGraph`;
- emit no relations under current activation policy.

It must not:

- read raw P8/P9 result objects;
- call chess rules;
- call P7/Stockfish;
- inspect score magnitude;
- create claims;
- infer claim-to-claim causality.

---

## 13. ExplanationSelector policy

Suggested service:

```text
src/calliope/services/explanation/selector.py
```

Responsibilities:

- accept a validated `ExplanationGraph`;
- apply only the frozen family/priority algorithm;
- return `ExplanationSelection`.

It must not:

- mutate graph claims;
- assign `importance`;
- inspect EvidenceRecord internals;
- access engine analysis;
- run chess logic;
- render text.

The selector's only chess-semantic knowledge is the closed P10 predicate -> selection-family /
priority-tier mapping frozen in this document.

---

## 14. Deterministic ordering

### Relations

Future relation ordering:

```text
source claim ordinal
-> ExplanationRelationKind declaration order
-> target claim ordinal
-> evidence id tuple
```

Relation ids are minted only after this ordering.

### Selection

Selection order is the priority order defined in §10.

The selector must never iterate over a set/dict in a way that determines output order.

---

## 15. Failure semantics

Use P11-owned errors under `CalliopeError`, for example:

```text
ExplanationGraphError
ExplanationSelectionError
```

Fail closed on:

- invalid/non-P10 claim package;
- mixed P8/P9 package;
- claim base mismatch;
- duplicate/noncanonical claim ids;
- unknown predicate/confidence/scope values;
- any P10 validation failure;
- non-empty relation output while no relation rule is active;
- relation endpoint missing from graph;
- relation evidence outside endpoint evidence union;
- duplicate relation;
- noncanonical relation id/order;
- selection referencing a missing claim/relation;
- more than three selected claims;
- duplicate selected family;
- selector output that differs from the frozen priority algorithm.

An absence of claims is not an error.

---

## 16. Strict no-score / no-analysis rule

P11 must not read or derive selection from:

- centipawns;
- WDL;
- engine rank;
- mate distance;
- cp loss;
- expected-score loss;
- PV length;
- alternative rank magnitude.

P11 may observe only P10 claim vocabulary, confidence, scope, canonical order, ids, and graph
structure needed by the frozen selection policy.

No imports from Stockfish/python-chess adapters or chess-rule execution ports are permitted.

---

## 17. Public boundary

P11 remains internal.

Do not yet change:

- `CalliopeEngine`;
- `AnalyzeMoveService`;
- `MoveAnalysisResult`;
- `ClaimView`;
- `PUBLIC_SCHEMA_VERSION`;
- commentary/renderer behavior.

In particular, public `ClaimView` still lacks explicit P10 `ClaimScope`. Public projection is
not allowed to expose P11-selected claims until the P12/application boundary makes the required
schema decision.

---

## 18. Test gates

### Domain

Test:

- relation kind/model invariants;
- canonical relation ids;
- graph endpoint/base closure;
- selection id uniqueness;
- three-claim cap;
- selected relation endpoint closure.

### P10 boundary

Pin:

- P11 reruns P10 validation;
- malformed P10 packages do not enter selection;
- P8/P9 family mixing is rejected;
- P10 claims are unchanged by graph building/selection.

### Selection mapping

Cover every current ClaimPredicate.

Pin:

- exact mate outranks all lower tiers;
- verified outcome outranks tactical mechanism;
- tactical mechanism outranks forced response;
- forced response outranks tested threat;
- at most one claim per selection family;
- maximum three claims;
- canonical-order tie break;
- empty input -> empty selection.

### Relation safety

Attempt to inject:

- `CAUSES` from shared piece;
- `LEADS_TO` from same PV;
- `ENABLES` from predicate pairing;
- arbitrary non-empty relation.

All must be rejected while `ACTIVE_RELATION_RULES == ()`.

### Adversarial

Attempt:

1. FORCED claim injection;
2. representative claim rewritten to local semantics;
3. score/rank-based priority hook;
4. claim reorder before P10 revalidation;
5. fourth selected claim;
6. two claims from one selection family;
7. unknown selected claim id;
8. importance mutation;
9. non-empty relation injection;
10. relation endpoint/evidence outside graph.

All must fail closed.

---

## 19. Real-fixture acceptance

Reuse existing P10 fixtures without new engine runs.

Required classes:

1. P8 exact mate -> exact mate selected first;
2. P8 hanging + material consequence -> material consequence then tactical mechanism;
3. P9 supported FORCES_RESPONSE -> selected;
4. P9 ONLY_MOVE preservation -> representative claim selected unchanged;
5. equivalent P9 -> empty;
6. quiet P9 -> empty.

A later real-Stockfish P11 gate should reuse the already-observed P10-I6 results rather than
introducing new engine fixtures.

---

## 20. Implementation packets

Recommended sequence:

```text
P11-A0  design freeze + independent design review

P11-I0  domain:
        ExplanationRelationKind / ExplanationRelation
        ExplanationGraph / ExplanationSelection
        relation ids / P11 errors

P11-I1  GraphBuilder:
        P10 revalidation
        exact claim preservation
        relation-safe empty-edge graph

P11-I2  ExplanationSelector:
        frozen family mapping
        priority tiers
        max-3 minimal selection

P11-I3  integrated adversarial/determinism gate

P11-I4  real P10 fixture acceptance
```

Every implementation packet stops for independent implementation review before the next.

---

## 21. Review questions

Independent design review must explicitly answer:

1. Can P11 create a chess claim not emitted by P10? It must not.
2. Can P11 strengthen confidence or scope? It must not.
3. Can P11 infer claim-to-claim causality from shared entities/PVs alone? It must not.
4. Is the empty-relation policy explicit rather than accidental? It must be.
5. Does P11 rerun P10 validation before graph construction? It must.
6. Can invalid/reordered P10 claims be silently normalized? They must not be.
7. Is selection independent of cp/WDL/rank/mate distance/PV length? It must be.
8. Are selection family and priority mappings closed over every current predicate? They must be.
9. Is selection deterministic and capped at three claims? It must be.
10. Does selection leave every P10 claim object unchanged? It must.
11. Can representative preservation semantics be upgraded to literal-only/forced? It must not.
12. Can a caller inject a relation while no relation rule is active? It must be rejected.
13. Does P11 remain internal with no public/schema/rendering change? It must.
14. Can P12 resolve every selected claim solely from graph + selection without chess re-analysis?
    It must.

---

## 22. Frozen summary

MVP-P11 is a **selection layer, not a new chess reasoner**.

It receives a complete validated P10 package, preserves all verified claims in an internal graph,
and selects at most three primary claims by a closed deterministic semantic priority policy.

Current P10 does not carry sufficient cross-claim provenance to prove causal edges. Therefore
P11 freezes relation vocabulary and domain shape but emits no automatic relations. This prevents
the explanation layer from reintroducing the exact kind of unsupported inference that P10 was
built to eliminate.

P12 may render the selected claims. It may not reconstruct omitted relations or board truth.
