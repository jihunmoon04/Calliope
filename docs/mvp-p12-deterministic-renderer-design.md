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
    sentences: tuple[str, ...]
    used_claim_ids: tuple[str, ...]
```

Suggested location:

```text
src/calliope/domain/explanation/render.py
```

or another small internal explanation-domain module.

Structural invariants:

- `text` is a non-empty string;
- `sentences` is a tuple of non-empty strings;
- `used_claim_ids` is a tuple;
- claim ids are canonical request-local `cl_###` ids;
- claim ids are unique;
- for non-empty claim commentary,
  `len(sentences) == len(used_claim_ids)`;
- for non-empty claim commentary,
  `text == " ".join(sentences)`;
- for empty selection, `sentences == ()` and `used_claim_ids == ()`, while `text` is the
  frozen meta-level fallback from §5.

The `sentences` tuple is the auditable 1:1 claim-to-language surface. P13 may consume it later
without reparsing punctuation from aggregate text.

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
- `claim.base_position_id`;
- `subject.move.uci`;
- `predicate`;
- `confidence`;
- `scope`;
- object entity types;
- `MoveClaimEntity.move.uci`;
- `MoveClaimEntity.position_id`, only for the frozen object-signature/frame checks in §11;
- `PieceClaimEntity.base_ref.color`;
- `PieceClaimEntity.base_ref.piece_type`;
- `PieceClaimEntity.base_ref.base_square`;
- `PieceClaimEntity.at_position_id`;
- `PieceClaimEntity.current_square`;
- `PieceClaimEntity.current_piece_type`;
- `SideClaimEntity.color` only if a future reviewed template explicitly needs it.

The piece presentation fields beyond `base_ref` are read only to prove that current retained
pieces are still the frozen base-frame presentation from §8. They are not a source of new board
truth.

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

Current P10 deliberately retains source pieces in the **common base-position frame** so physical
identity survives branch comparison. That means a `PieceClaimEntity.current_square` is not
necessarily the piece's square *after the played move*.

P12 must therefore not render current P10 piece objects as:

```text
the white knight on c3
```

because "on c3" could be read as a post-move board assertion that the selected claim does not
contain.

For every current P8/P9-derived claim, P12 requires the retained piece entity to be in the claim
base frame:

```text
piece.at_position_id == claim.base_position_id
piece.base_ref.base_square == piece.current_square
piece.base_ref.piece_type == piece.current_piece_type
```

and renders the physical identity as:

```text
{color} {base_piece_type} from {base_square}
```

Examples:

```text
white knight from c3
black king from g8
white queen from e7
```

"from" identifies the retained base-frame piece; it does not assert that the piece remains on
that square after the played move.

If a future valid claim uses a non-base-frame piece presentation, strict P12 fails closed until a
new presentation rule is reviewed.

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

Every template is usable only after its exact §11 object signature passes. Objects that are not
printed are still validated; silently ignoring malformed extra objects is forbidden.

### Tier-independent tactical/bad-move rules

#### LEAVES_PIECE_HANGING / ENGINE_VERIFIED / LOCAL

```text
Move {move} leaves {pieces} hanging.
```

#### REMOVES_DEFENDER / ENGINE_VERIFIED / LOCAL

```text
Move {move} removes a defender of {pieces}.
```

#### ALLOWS_FORK / ENGINE_VERIFIED / LOCAL

Current P10 retains the fork actor and targets together as source-piece objects, without an
actor/target role tag. P12 therefore must not label all retained pieces as fork targets.

```text
Move {move} allows a fork.
```

Do not render "fork against {pieces}" until P10 retains reviewed actor/target roles.

### Checkmate/material consequences

#### ALLOWS_CHECKMATE / EXACT / LOCAL

```text
Move {move} allows checkmate.
```

#### ALLOWS_CHECKMATE / ENGINE_VERIFIED / LOCAL

```text
Move {move} allows an engine-verified mating line.
```

The ENGINE_VERIFIED wording deliberately does not say that mate is mathematically forced and does
not require the retained replay itself to end in board-checkmate.

#### ALLOWS_MATERIAL_LOSS / ENGINE_VERIFIED / LOCAL

```text
Move {move} allows an engine-verified line with material loss.
```

### Good-move direct results

#### FORCES_RESPONSE / EXACT / LOCAL

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
Move {move} has an engine-verified line leading to mate.
```

#### WINS_MATERIAL / ENGINE_VERIFIED / LOCAL

```text
Move {move} has an engine-verified line that wins material.
```

### Tested-response threats

The retained tested response Q is the **concrete response that was tested and failed to meet the
resource/threat**. It is not a proven defense, required reply, or unique alternative.

#### THREATENS_MATE_IF_IGNORED / ENGINE_VERIFIED / TESTED_RESPONSE

```text
Move {move} creates a mate threat that tested response {response} does not meet.
```

#### THREATENS_MATERIAL_IF_IGNORED / ENGINE_VERIFIED / TESTED_RESPONSE

```text
Move {move} creates a material threat that tested response {response} does not meet.
```

Forbidden tested-response wording includes:

- "if {response} is not played";
- "unless {response} is played";
- "must play {response}";
- any wording implying that Q is a defense;
- any wording generalizing from Q to all other responses;
- unstoppable / unavoidable / every response fails.

The only authority is: this concrete tested Q does not meet the verified threat/resource.

### Representative-alternative preservation

#### AVOIDS_REPRESENTATIVE_MATE_FAILURE / ENGINE_VERIFIED / REPRESENTATIVE_ALTERNATIVES

```text
Compared with the tested representative alternatives, move {move} avoids the mate failure seen after {alternatives}.
```

#### AVOIDS_REPRESENTATIVE_MATERIAL_LOSS / ENGINE_VERIFIED / REPRESENTATIVE_ALTERNATIVES

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

## 11. Frozen object signatures

P12 may classify already-retained claim objects by entity type and **position frame only**.
This is structural presentation validation, not chess reasoning.

Suggested helpers:

```text
piece_objects(claim)
move_objects(claim)
```

For every current rule, all `PieceClaimEntity` objects must be in the frozen base frame:

```text
piece.at_position_id == claim.base_position_id
piece.current_square == piece.base_ref.base_square
piece.current_piece_type == piece.base_ref.piece_type
```

Move frame classes:

```text
BASE_MOVE:
  move.position_id == claim.base_position_id

AFTER_MOVE:
  move.position_id != claim.base_position_id
```

P12 does not derive what the after-move position actually is. P10/P11 revalidation has already
bound the retained response/punishment entity to its authoritative source position. P12 only
checks the base-vs-non-base frame required by the frozen claim shape.

### Closed signature table

The exact accepted current shapes are:

| Predicate / confidence / scope | Move objects | Move frame | Piece objects |
| --- | ---: | --- | ---: |
| LEAVES_PIECE_HANGING / ENGINE_VERIFIED / LOCAL | exactly 1 | AFTER_MOVE punishment | exactly 1 |
| REMOVES_DEFENDER / ENGINE_VERIFIED / LOCAL | exactly 1 | AFTER_MOVE punishment | exactly 1 |
| ALLOWS_FORK / ENGINE_VERIFIED / LOCAL | exactly 1 | AFTER_MOVE punishment | at least 3 |
| ALLOWS_CHECKMATE / EXACT / LOCAL | exactly 1 | AFTER_MOVE punishment | exactly 1 |
| ALLOWS_CHECKMATE / ENGINE_VERIFIED / LOCAL | exactly 1 | AFTER_MOVE punishment | exactly 1 |
| ALLOWS_MATERIAL_LOSS / ENGINE_VERIFIED / LOCAL | exactly 1 | AFTER_MOVE punishment | at least 1 |
| FORCES_RESPONSE / EXACT / LOCAL | exactly 1 | AFTER_MOVE response | at least 1 |
| DELIVERS_CHECKMATE / EXACT / LOCAL | 0 | — | exactly 1 |
| LEADS_TO_MATE / ENGINE_VERIFIED / LOCAL | 0 | — | exactly 1 |
| WINS_MATERIAL / ENGINE_VERIFIED / LOCAL | 0 | — | at least 1 |
| THREATENS_MATE_IF_IGNORED / ENGINE_VERIFIED / TESTED_RESPONSE | exactly 1 | AFTER_MOVE tested Q | exactly 1 |
| THREATENS_MATERIAL_IF_IGNORED / ENGINE_VERIFIED / TESTED_RESPONSE | exactly 1 | AFTER_MOVE tested Q | at least 1 |
| AVOIDS_REPRESENTATIVE_MATE_FAILURE / ENGINE_VERIFIED / REPRESENTATIVE_ALTERNATIVES | 1 or 2 | every move BASE_MOVE failed alternative | exactly 1 |
| AVOIDS_REPRESENTATIVE_MATERIAL_LOSS / ENGINE_VERIFIED / REPRESENTATIVE_ALTERNATIVES | 1 or 2 | every move BASE_MOVE failed alternative | at least 1 |

This table is frozen to the current P8/P9 -> P10 builders and validators. P12 intentionally fails
closed if a future valid P10 claim changes one of these presentation shapes; that change requires a
P12 design review rather than a permissive template fallback.

### Rendering roles

After the signature passes:

- hanging/removed-defender may render their base-frame piece objects;
- fork renders **no piece roles**, because actor vs target is not retained in P10;
- P8 punishment moves are validated but are not printed by the current consequence/tactical
  templates;
- FORCES_RESPONSE prints its one AFTER_MOVE response;
- TESTED_RESPONSE templates print their one AFTER_MOVE tested Q;
- preservation templates print their one-or-two BASE_MOVE failed alternatives;
- direct mate/material outcome templates validate their pieces even when the sentence does not
  print them.

No template may ignore an unexpected extra object.

P12 must not infer actor/target, defender/attacker, response purpose, or alternative meaning from
piece color, board geometry, or UCI. The role is accepted only where the frozen P10 shape plus
predicate/frame already defines it.

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

A predicate-internal phrase such as "has an engine-verified line leading to mate" is allowed because
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

Add a P12-owned error under `CalliopeError`:

```python
class ExplanationRenderError(CalliopeError):
    """P12 cannot safely render the selected claim set."""
```

P12 exposes **one rendering-boundary error type**.

The renderer must catch P11 validation failures relevant to its input boundary, including
`ExplanationGraphError` and `ExplanationSelectionError`, and raise:

```python
raise ExplanationRenderError(...) from exc
```

The original P11/P10 failure remains available through exception chaining.

P12's own structural/template failures also raise `ExplanationRenderError`.

Fail closed on:

- input not being the expected graph/selection types;
- any P11 pair-validation failure;
- selected claim id failing to resolve after successful validation;
- unsupported predicate/confidence/scope triple;
- any §11 object signature mismatch, including frame mismatch;
- non-base-frame piece presentation;
- non-empty relation selection under the current policy;
- renderer output not using exactly the selected ids in selected order;
- sentence tuple not matching selected-id cardinality/order;
- aggregate text not matching the frozen sentence composition;
- empty/non-string rendered sentence;
- any attempt to route through a fallback generic chess template.

An invalid package must never be converted into prose.

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

- a deterministic fallback `text`;
- `sentences`, with one reviewed sentence per selected claim;
- the exact selected claim ids in the same order.

Therefore:

```text
zip(rendered.used_claim_ids, rendered.sentences)
```

is the canonical claim-to-language provenance surface for later P13 validation.

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
- renderer cannot bypass P11 validation;
- P11 failures are wrapped as `ExplanationRenderError` with chained cause.

### Closed rule table

Programmatically verify:

- all 14 currently P10-valid predicate/confidence pairs have exactly one compatible P12 rule
  when combined with their required scope;
- every other predicate/confidence/scope triple fails closed;
- every FORCED combination fails closed;
- no generic fallback exists.

The **unit P10 corpus must contain golden coverage for all 14 valid forms**, not merely the six real
Stockfish acceptance classes.

### Exact object-signature gate

For each of all 14 forms, pin the §11 signature:

- exact/allowed MoveClaimEntity count;
- BASE_MOVE vs AFTER_MOVE frame;
- exact/minimum PieceClaimEntity count;
- every piece remains in the base frame;
- unexpected extra object fails closed even when the template would not print it.

Negative goldens must include:

- missing P8 punishment;
- punishment moved to the base frame;
- response/tested Q moved to the base frame;
- preservation alternative moved off the base frame;
- extra move object;
- missing/extra piece outside the signature;
- non-base-frame piece presentation.

### Object presentation

Pin:

- subject UCI used;
- SAN is never used even when present;
- piece text identifies the retained base-frame physical piece ("from <square>") and never implies
  a post-move square;
- response/tested-Q UCI comes only from the structurally accepted MoveClaimEntity;
- fork actor/target roles are never invented.

A required fork negative golden must prove that a corpus claim containing the fork actor plus its
targets renders only:

```text
Move {move} allows a fork.
```

and never "fork against {all pieces}".

### Scope preservation

Pin exact wording requirements:

- TESTED_RESPONSE says that the concrete tested response **does not meet** the threat;
- TESTED_RESPONSE never uses "if Q is not played", "unless Q", "must play Q", or any all-response
  generalization;
- REPRESENTATIVE_ALTERNATIVES sentences contain "tested representative alternatives";
- preservation never says only/unique/all/forced/exhaustive.

A required tested-Q negative golden must use a known irrelevant/failed response (for example the
current corpus material-threat Q) and prove the renderer never phrases Q as a defense.

### One claim / one sentence

For every non-empty selection:

- `len(sentences) == len(selected_claim_ids)`;
- `used_claim_ids == selected_claim_ids`;
- `text == " ".join(sentences)`;
- order exact;
- no unselected claim changes any sentence.

For empty selection:

- `sentences == ()`;
- `used_claim_ids == ()`;
- exact frozen meta text is returned.

### Relation safety

Current relation injection must fail before rendering.

No "because", "therefore", "so", "causes", "enables" cross-claim synthesis.

### Empty selection

Exact text:

```text
No verified explanation is available.
```

with no used claim ids and no claim sentences.

### Determinism

Test:

- repeated rendering;
- hash seeds;
- equivalent object reconstruction;
- engine mate-distance variants whose selected P10/P11 semantics are identical.

### Real acceptance

Reuse P11/P10 real Stockfish observations without new P12 engine calls.

Required real classes:

1. exact mate;
2. material + tactical mechanism;
3. FORCES_RESPONSE;
4. representative preservation;
5. equivalent alternatives -> meta fallback;
6. quiet BEST -> meta fallback.

These six are **not** sufficient template coverage. The 14-form unit-corpus golden matrix above is
mandatory and specifically covers fork, tested threats, DELIVERS_CHECKMATE, LEADS_TO_MATE and
WINS_MATERIAL.

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
Move c3e4 allows an engine-verified line with material loss. Move c3e4 leaves white knight from c3 hanging.
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
15. Are `sentences` and `used_claim_ids` a strict 1:1 mapping in selected/render order?
16. Does every one of the 14 rules enforce its frozen object count and base/after-move frame before rendering?
17. Does the tested-response wording correctly say that Q fails to meet the threat rather than presenting Q as a defense?
18. Does fork rendering avoid inventing actor/target roles that P10 does not retain?
19. Is current relation-free P11 policy preserved?
20. Is deterministic output independent of hash seed/runtime/engine noise?
21. Is the internal RenderedCommentary model sufficiently separate from public CommentaryView?
22. Is public ClaimView correctly identified as scope-incomplete for P10/P11 projection?
23. Is deferring public schema/application wiring safe because P12 does not expose internal claims?
24. Is the two-packet P12 implementation sequence small enough for independent review?
25. Can P13 later consume the explicit claim-sentence pairs while keeping P12 as a safe fallback?

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
- returns explicit one-to-one `sentences` + `used_claim_ids` provenance;
- validates the complete frozen object signature even for objects a sentence does not print;
- never reads evidence payloads, scores, PVs or chess rules to write prose.

P12 remains internal. Public evidence-backed claim/commentary exposure waits for an explicit
scope-complete schema/application integration decision; the current scope-less `ClaimView` must
not be used for P10/P11 projection.
