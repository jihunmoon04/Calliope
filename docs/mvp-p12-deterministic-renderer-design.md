# MVP-P12 Deterministic Renderer Design

Status: **A0 design draft for independent review**

This document is the canonical MVP-P12 design. It assumes MVP-P10 Evidence/Claims and MVP-P11
graph validation/minimal selection are already frozen and independently accepted.

---

## 1. Purpose

MVP-P12 turns a validated P11 `(ExplanationGraph, ExplanationSelection)` pair into useful,
deterministic, LLM-free commentary.

Canonical internal flow:

```text
P10 EvidenceBundle + ExplanationClaim tuple
  -> P11 ExplanationGraph
  -> P11 ExplanationSelection
  -> P12 pair revalidation
  -> deterministic claim rendering
  -> RenderedCommentary
```

P12 is a **presentation layer**. It is not a chess-analysis stage.

It must not:

- analyze a board;
- call chess rules;
- call Stockfish/P7;
- inspect engine scores, rank, WDL, mate distance or PV length;
- read P8/P9 raw result objects;
- derive a new claim;
- strengthen confidence or scope;
- infer a causal relation;
- combine two selected claims into an unproved causal proposition;
- reconstruct an omitted relation from shared pieces, moves, evidence or variations.

A missing strict explanation remains valid.

---

## 2. Input trust boundary

The renderer accepts exactly:

```python
ExplanationGraph
ExplanationSelection
```

The pair is never trusted merely because the objects are frozen or because a caller says they
came from P11.

Before reading any selected claim, P12 must call:

```python
ExplanationSelectionValidator().validate(graph, selection)
```

This transitively:

1. reruns `ExplanationGraphValidator`;
2. reruns P10 claim/evidence validation;
3. verifies the current empty-relation policy;
4. recomputes the exact P11 selection;
5. requires exact graph/selection agreement.

P12 must not provide a second weaker validation path.

---

## 3. Internal output model

Freeze an internal immutable value:

```python
@dataclass(frozen=True, slots=True)
class RenderedCommentary:
    text: str
    used_claim_ids: tuple[str, ...]
```

Suggested location:

```text
src/calliope/domain/explanation/render.py
```

or another small internal explanation-domain module.

Structural invariants:

- `text` is a non-empty string;
- `used_claim_ids` is a tuple;
- ids are canonical request-local `cl_###` ids;
- ids are unique.

P12 must not import the public `CommentaryView` into the explanation domain/service layer.

The public DTO and application projection remain a later application-boundary concern (§15).

---

## 4. Provenance contract: one selected claim -> one sentence

For a non-empty selection, P12 renders **exactly one sentence per selected claim**.

The sentence order is exactly:

```text
selection.selected_claim_ids
```

which P11 already froze as priority/default render order.

Therefore, for non-empty output:

```text
number of rendered sentences == len(selection.selected_claim_ids)
used_claim_ids == selection.selected_claim_ids
```

P12 does not:

- merge two claims into one sentence;
- split one claim into multiple chess propositions;
- use an unselected claim to enrich a selected sentence;
- insert a causal connective between separate claims.

Aggregate text is the rendered sentences joined by exactly one ASCII space.

This one-claim/one-sentence rule is the primary auditability boundary for P12 and later P13.

---

## 5. Empty selection

An empty validated P11 selection is not an error.

Freeze the deterministic meta-commentary:

```text
No verified explanation is available.
```

and:

```python
used_claim_ids == ()
```

This sentence is meta-level status, not a chess proposition.

P12 must not inspect the engine judgement, unselected claims, evidence or board state to invent a
fallback chess reason.

---

## 6. Allowed rendering authority

After P11 pair validation, P12 may read only these fields from **selected claims**:

- `claim_id`;
- `subject.move.uci`;
- `predicate`;
- `confidence`;
- `scope`;
- object entity types;
- `MoveClaimEntity.move.uci`;
- `PieceClaimEntity.base_ref.color`;
- `PieceClaimEntity.current_piece_type`;
- `PieceClaimEntity.current_square`;
- `SideClaimEntity.color` if a future reviewed template explicitly needs it.

P12 may also read the selected-id order from `ExplanationSelection`.

P12 must not read for prose generation:

- `graph.evidence` records or evidence payload fields;
- evidence ids as semantic content;
- unselected claims;
- relation inference candidates;
- SAN;
- engine analysis;
- cp/WDL/rank/mate distance;
- PV moves or PV length;
- tactical detector output;
- board facts/deltas directly;
- raw P8/P9 objects.

The retained EvidenceBundle exists only because P11/P10 revalidation needs it.

---

## 7. Move notation policy: UCI only

Strict P12 renders moves using canonical UCI only.

Example:

```text
e2e4
g7g8q
```

Do **not** render SAN in strict MVP-P12.

Reason: SAN may itself expose additional board propositions that are not part of the selected
claim, such as:

- check (`+`);
- checkmate (`#`);
- capture notation;
- castling semantics;
- disambiguation derived from board geometry.

Even when SAN is retained as presentation metadata, P12's core rule is:

```text
selected claim authority only
```

UCI is already the semantic move identity used throughout P8-P11 and does not require P12 to add
a new board-derived proposition.

Localized or richer notation can be designed later if its authority is explicit.

---

## 8. Piece presentation

A `PieceClaimEntity` is rendered only from its retained presentation fields.

Canonical English form:

```text
{color} {piece_type} on {current_square}
```

Examples:

```text
white knight on c3
black king on g8
white queen on e7
```

Use enum values directly through a closed lexical mapping.

Do not query the board to recover a piece name or square.

For deterministic lists:

- one item: `A`
- two items: `A and B`
- three or more: `A, B, and C`

Object order is the already validated claim object order; do not re-rank objects by value.

---

## 9. Current rendering vocabulary is closed

P12 supports exactly the currently P10-valid
`(ClaimPredicate, ClaimConfidence, ClaimScope)` combinations.

There is no fallback template.

An unsupported predicate/confidence/scope combination fails closed with a P12-owned rendering
error even if some future object can be structurally constructed.

Current P10 does not accept `FORCED`; P12 therefore has no FORCED template.

---

## 10. Frozen render rules

The following templates are the strict MVP-P12 canonical English wording.

`{move}` is the subject UCI.

### Tier-independent tactical/bad-move rules

#### LEAVES_PIECE_HANGING / ENGINE_VERIFIED / LOCAL

Requires at least one `PieceClaimEntity` object.

```text
Move {move} leaves {pieces} hanging.
```

#### REMOVES_DEFENDER / ENGINE_VERIFIED / LOCAL

Requires at least one `PieceClaimEntity` object.

```text
Move {move} removes a defender of {pieces}.
```

#### ALLOWS_FORK / ENGINE_VERIFIED / LOCAL

Requires at least one `PieceClaimEntity` object.

```text
Move {move} allows a fork against {pieces}.
```

### Checkmate/material consequences

#### ALLOWS_CHECKMATE / EXACT / LOCAL

```text
Move {move} allows checkmate.
```

#### ALLOWS_CHECKMATE / ENGINE_VERIFIED / LOCAL

```text
Move {move} allows a verified line ending in checkmate.
```

The ENGINE_VERIFIED wording deliberately does not say that mate is mathematically forced.

#### ALLOWS_MATERIAL_LOSS / ENGINE_VERIFIED / LOCAL

```text
Move {move} allows a verified line with material loss.
```

### Good-move direct results

#### FORCES_RESPONSE / EXACT / LOCAL

Requires exactly one non-subject `MoveClaimEntity` object.

```text
Move {move} forces response {response}.
```

This wording is allowed because `FORCES_RESPONSE / EXACT` is itself the selected P10 claim.
It must not be expanded to "only move", "unique move", or any global exhaustiveness statement.

#### DELIVERS_CHECKMATE / EXACT / LOCAL

```text
Move {move} delivers checkmate.
```

#### LEADS_TO_MATE / ENGINE_VERIFIED / LOCAL

```text
Move {move} has a verified line leading to mate.
```

#### WINS_MATERIAL / ENGINE_VERIFIED / LOCAL

```text
Move {move} has a verified line that wins material.
```

### Tested-response threats

#### THREATENS_MATE_IF_IGNORED / ENGINE_VERIFIED / TESTED_RESPONSE

Requires exactly one non-subject `MoveClaimEntity` object representing the retained tested
response.

```text
Move {move} threatens mate if tested response {response} is not played.
```

#### THREATENS_MATERIAL_IF_IGNORED / ENGINE_VERIFIED / TESTED_RESPONSE

Requires exactly one non-subject `MoveClaimEntity` object.

```text
Move {move} threatens material gain if tested response {response} is not played.
```

These templates must retain the tested-response limitation. They must not become a general
unconditional threat statement.

### Representative-alternative preservation

#### AVOIDS_REPRESENTATIVE_MATE_FAILURE / ENGINE_VERIFIED / REPRESENTATIVE_ALTERNATIVES

Requires at least one non-subject `MoveClaimEntity` object corresponding to retained failed
representative alternatives.

```text
Compared with the tested representative alternatives, move {move} avoids the mate failure seen after {alternatives}.
```

#### AVOIDS_REPRESENTATIVE_MATERIAL_LOSS / ENGINE_VERIFIED / REPRESENTATIVE_ALTERNATIVES

Requires at least one non-subject `MoveClaimEntity` object.

```text
Compared with the tested representative alternatives, move {move} avoids the material loss seen after {alternatives}.
```

The words "tested representative alternatives" are mandatory scope language.

Never render:

- only move;
- unique move;
- all alternatives;
- every legal move;
- forced preservation;
- exhaustive proof.

---

## 11. Object-role extraction is structural presentation logic

P12 may classify already-retained claim objects by entity type only.

Suggested helpers:

```text
piece_objects(claim)
move_objects(claim)
```

This is not chess reasoning.

Template-specific presentation closure:

- tactical mechanism templates require one or more PieceClaimEntity objects;
- FORCES_RESPONSE requires exactly one MoveClaimEntity object in `claim.objects`;
- TESTED_RESPONSE templates require exactly one MoveClaimEntity object;
- preservation templates require one or more MoveClaimEntity objects;
- mate/material outcome templates that do not mention objects need no extra object extraction.

Unexpected object cardinality/type for a template fails closed.

P12 must not decide that an arbitrary object "must be" a response or failed alternative from board
geometry. That role has already been frozen by P10 claim construction/validation.

---

## 12. No cross-sentence relation language

Current P11 validates:

```text
relations == ()
```

Therefore P12 must not insert relation words between separate selected claims.

Forbidden cross-sentence transformations include:

```text
A because B
A, so B
A and therefore B
A which causes B
B is why A
A enables B
```

unless a future P11 relation-specific provenance design activates and P12 is separately revised.

Plain sentence adjacency is the only current composition rule.

A predicate-internal phrase such as "has a verified line leading to mate" is allowed because
`LEADS_TO_MATE` itself is the selected claim. That is not a cross-claim edge.

---

## 13. Determinism

For the same validated graph/selection pair, output must be byte-identical.

Output must not depend on:

- hash seed;
- dict/set iteration;
- engine score;
- WDL;
- mate distance;
- rank;
- PV content/length;
- timing;
- object identity/address;
- locale/environment;
- Stockfish version;
- random state.

The strict MVP renderer has one fixed language: canonical English.

Localization is out of scope for P12. It may be added after the strict renderer has a separate
reviewed authority contract.

---

## 14. P12-owned failure semantics

Add a P12-owned error under `CalliopeError`, for example:

```python
class ExplanationRenderError(CalliopeError):
    """P12 cannot safely render the validated selected claim set."""
```

Fail closed on:

- input not being the expected graph/selection types;
- any P11 pair-validation failure;
- selected claim id failing to resolve after successful validation;
- unsupported predicate/confidence/scope triple;
- template-required object type/cardinality missing;
- non-empty relation selection under the current policy;
- renderer output not using exactly the selected ids in selected order;
- empty/non-string rendered sentence;
- any attempt to route through a fallback generic chess template.

P12 should preserve P11/P10 errors as chained causes when wrapping is useful, but must not convert
an invalid package into prose.

---

## 15. Public/application boundary decision

### 15.1 P12 remains internal

MVP-P12 does **not** yet modify:

- `CalliopeEngine`;
- `AnalyzeMoveService`;
- `MoveAnalysisResult`;
- `ClaimView`;
- `CommentaryView`;
- `PUBLIC_SCHEMA_VERSION`;
- `OutputMode` behavior;
- composition-root wiring.

The current public application is still the earlier judgement-only vertical slice. Mixing the
entire P4-P12 orchestration into the renderer packet would obscure the renderer trust boundary.

### 15.2 Why public ClaimView is not safe yet

Current public `ClaimView` does not contain `ClaimScope`.

Projecting a P10/P11 claim such as:

```text
AVOIDS_REPRESENTATIVE_MATE_FAILURE
scope = REPRESENTATIVE_ALTERNATIVES
```

without its scope would lose a material semantic limitation.

Likewise a tested-response threat must retain:

```text
scope = TESTED_RESPONSE
```

Therefore no P12 implementation packet may expose current internal claims through `ClaimView`
as it exists today.

### 15.3 G0/application integration requirement

Before public evidence-backed claims/commentary are enabled, the application-integration packet
must make an explicit public schema decision, at minimum:

- expose claim scope in a stable public representation or replace ClaimView with a scope-complete
  typed representation;
- bump `PUBLIC_SCHEMA_VERSION` if the public serialized shape changes;
- project P10/P11 claims without dropping confidence/scope limitations;
- map internal `RenderedCommentary` to public `CommentaryView`;
- ensure `used_claim_ids` resolve against the same public claim projection;
- wire the canonical P4-P12 pipeline behind `CalliopeEngine`.

Until then, `OutputMode.COMMENTARY` remains unsupported by the public application.

This is an explicit deferral, not permission to project scope-less claims.

---

## 16. Relationship to P13

P13 is optional LLM verbalization.

P13 must not replace the P12 trust boundary.

P12 provides:

- a deterministic fallback text;
- the exact selected claim ids;
- a reviewed phrase-level interpretation of each selected claim.

P13 may improve fluency only under its own validation/fallback contract.

If P13 is unavailable or rejected, P12 output remains usable.

---

## 17. Suggested implementation layout

Suggested domain value:

```text
src/calliope/domain/explanation/render.py
```

Suggested service:

```text
src/calliope/services/explanation/renderer.py
```

Suggested API:

```python
class DeterministicExplanationRenderer:
    def render(
        self,
        graph: ExplanationGraph,
        selection: ExplanationSelection,
    ) -> RenderedCommentary:
        ...
```

Implementation sequence:

1. call `ExplanationSelectionValidator.validate(graph, selection)`;
2. resolve selected ids to graph claims without changing order;
3. render each claim through one closed rule;
4. join sentences with one ASCII space;
5. return `RenderedCommentary(text, selection.selected_claim_ids)`.

Do not pass EvidenceBundle records into individual render functions.

---

## 18. Testing gates

### Pair trust boundary

Pin:

- valid P11 pair accepted;
- tampered graph rejected;
- stale/wrong selection rejected;
- manual graph still revalidated through P11;
- renderer cannot bypass P11 validation.

### Closed rule table

Programmatically verify:

- all 14 currently P10-valid predicate/confidence pairs have exactly one compatible P12 rule
  when combined with their required scope;
- every other predicate/confidence/scope triple fails closed;
- every FORCED combination fails closed;
- no generic fallback exists.

### Object presentation

Pin:

- subject UCI used;
- SAN is never used even when present;
- piece text comes only from retained PieceClaimEntity fields;
- response UCI comes only from retained MoveClaimEntity;
- required object omission/type/cardinality fails closed.

### Scope preservation

Pin exact wording requirements:

- TESTED_RESPONSE sentences contain the tested-response limitation;
- REPRESENTATIVE_ALTERNATIVES sentences contain "tested representative alternatives";
- preservation never says only/unique/all/forced/exhaustive.

### One claim / one sentence

For every non-empty selection:

- sentence count == selected claim count;
- used ids == selected ids;
- order exact;
- no unselected claim changes text.

### Relation safety

Current relation injection must fail before rendering.

No "because", "therefore", "so", "causes", "enables" cross-claim synthesis.

### Empty selection

Exact text:

```text
No verified explanation is available.
```

with no used claim ids.

### Determinism

Test:

- repeated rendering;
- hash seeds;
- equivalent object reconstruction;
- engine mate-distance variants whose selected P10/P11 semantics are identical.

### Real acceptance

Reuse P11/P10 real Stockfish observations without new P12 engine calls.

Required cases:

1. exact mate;
2. material + tactical mechanism;
3. FORCES_RESPONSE;
4. representative preservation;
5. equivalent alternatives -> meta fallback;
6. quiet BEST -> meta fallback.

P12 itself must still work when engine/rules/P7 methods are patched to fail.

---

## 19. Golden examples

These examples illustrate the frozen wording. They are not permission to synthesize the claims.

### Exact mate allowed

Selected:

```text
ALLOWS_CHECKMATE / EXACT / LOCAL
subject = d1d7
```

Output:

```text
Move d1d7 allows checkmate.
```

### Material + hanging

Selected in P11 order:

```text
ALLOWS_MATERIAL_LOSS
LEAVES_PIECE_HANGING
```

Example output:

```text
Move c3b5 allows a verified line with material loss. Move c3b5 leaves white knight on c3 hanging.
```

The period boundary is important: P12 does not say the hanging knight **causes** the material loss.

### Forced response

```text
Move b1b8 forces response a8b8.
```

No "only legal move globally" wording is added beyond the exact selected claim.

### Preservation

```text
Compared with the tested representative alternatives, move a8a1 avoids the mate failure seen after a8a2 and a8a3.
```

The exact UCI values depend on the retained claim objects.

### Silent strict explanation

```text
No verified explanation is available.
```

---

## 20. Implementation packets

Recommended compressed P12 sequence:

```text
P12-A0  canonical renderer design + independent review

P12-I0  internal production renderer:
        RenderedCommentary
        ExplanationRenderError
        closed render rules
        P11 pair revalidation
        deterministic UCI/entity presentation
        all current predicate/confidence/scope forms

P12-I1  adversarial/golden/real acceptance:
        rule-table mutation gate
        no-SAN/no-score/no-evidence-reading gate
        one-claim/one-sentence gate
        scope wording gate
        real P10/P11 fixture acceptance
        production delta expected NONE
```

Public application integration is not part of these two packets; §15.3 is a hard prerequisite for
the later application/G0 wiring.

---

## 21. Independent review questions

The A0 reviewer must explicitly answer:

1. Does P12 validate the exact P11 graph/selection pair before rendering?
2. Can P12 create a chess proposition absent from one selected claim?
3. Is one selected claim mapped to exactly one sentence?
4. Can P12 use an unselected claim to enrich a sentence?
5. Can P12 infer a relation between separately selected claims?
6. Does the UCI-only rule prevent SAN-derived extra propositions?
7. Are all 14 current P10-valid predicate/confidence forms renderable with their required scopes?
8. Is every unsupported pair/triple fail-closed with no generic fallback?
9. Do TESTED_RESPONSE templates retain the tested-response limitation?
10. Do REPRESENTATIVE_ALTERNATIVES templates retain representative-only wording?
11. Can preservation language accidentally imply only/unique/forced/exhaustive semantics?
12. Are ENGINE_VERIFIED mate/material templates weaker than mathematical forcedness wording?
13. Does P12 avoid EvidenceBundle, score, WDL, rank, mate distance and PV inspection for prose?
14. Is empty selection handled without inventing a chess reason?
15. Are `used_claim_ids` exactly the selected ids in selected/render order?
16. Is current relation-free P11 policy preserved?
17. Is deterministic output independent of hash seed/runtime/engine noise?
18. Is the internal RenderedCommentary model sufficiently separate from public CommentaryView?
19. Is public ClaimView correctly identified as scope-incomplete for P10/P11 projection?
20. Is deferring public schema/application wiring safe because P12 does not expose internal claims?
21. Is the two-packet P12 implementation sequence small enough for independent review?
22. Can P13 later use P12 as a safe deterministic fallback without gaining chess authority?

---

## 22. Frozen summary

MVP-P12 is a **deterministic selected-claim renderer**, not another reasoning layer.

It consumes only a P11-validated graph/selection pair, revalidates that pair, and renders each
selected claim independently as one canonical English sentence.

Strict P12:

- uses UCI, not SAN;
- uses only explicit selected-claim fields;
- has a closed rule table with no generic fallback;
- preserves TESTED_RESPONSE and REPRESENTATIVE_ALTERNATIVES scope in wording;
- distinguishes exact mate wording from engine-verified line wording;
- emits no causal connective between separate claims while P11 relations are empty;
- renders an empty selection as a meta-level "No verified explanation is available.";
- returns exact selected claim provenance in `used_claim_ids`;
- never reads evidence payloads, scores, PVs or chess rules to write prose.

P12 remains internal. Public evidence-backed claim/commentary exposure waits for an explicit
scope-complete schema/application integration decision; the current scope-less `ClaimView` must
not be used for P10/P11 projection.
