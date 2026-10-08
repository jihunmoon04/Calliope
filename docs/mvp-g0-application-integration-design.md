# MVP-G0 Application Integration and Public Contract Design

Status: **A0 design draft for independent review**

This document defines the application/public integration required to expose the already-frozen
P4-P12 explanation pipeline through the single public `CalliopeEngine.analyze_move()` entry point.

MVP-P13 is optional and is **not** a prerequisite for G0. G0 completes the deterministic,
evidence-backed MVP with the LLM disabled.

---

## 1. Goal

G0 closes the gap between the deployed public P3 judgement-only slice and the internally complete
P4-P12 explanation pipeline.

Canonical public path:

```text
AnalyzeMoveRequest
  -> CalliopeEngine
  -> AnalyzeMoveService
  -> P0/P1/P2 judgement
  -> strict explanation pipeline
       P4 PositionFacts
       P5 BoardDelta
       P6 TacticalDetector
       P7 CounterfactualAnalyzer
       P8 or P9 explanation
       P10 EvidenceBundle + ExplanationClaim
       P11 ExplanationGraph + ExplanationSelection
       P12 deterministic commentary when requested
  -> scope-complete public projection
  -> MoveAnalysisResult
```

There is no parallel public explanation path.

---

## 2. Global invariants

G0 must preserve all previously frozen contracts.

1. `CalliopeEngine` remains the only public analysis facade.
2. Initial judgement remains P0-P2 and is not recomputed by P8/P9.
3. P8/P9 remain the only current sources of strict explanation truth.
4. P10 remains the hard evidence/claim trust boundary.
5. P11 selection remains deterministic and relation-free.
6. P12 remains presentation-only.
7. A missing explanation remains a valid result.
8. No public projection may strengthen confidence or scope.
9. No public field may erase a scope limitation needed to interpret a claim correctly.
10. No G0 code may infer additional chess truth while projecting DTOs.

---

## 3. Public schema version

G0 changes the public response shape and therefore bumps:

```python
PUBLIC_SCHEMA_VERSION = "0.2"
```

from `"0.1"`.

The schema bump is required because:

- public claims gain explicit `scope`;
- claim entities become structured and frame-preserving rather than opaque strings;
- P11 selected claim ids become a first-class public field;
- commentary gains sentence-level provenance.

Do not silently ship these changes under schema `0.1`.

---

## 4. Public claim entity projection

The current `ClaimView.subject: str` and `objects: tuple[str, ...]` are insufficient for
P10/P11 claims because they can discard:

- the exact move position frame;
- the physical base-piece identity;
- the piece presentation frame.

G0 replaces opaque entity strings with closed public entity DTOs.

### 4.1 Discriminator

```python
class ClaimEntityKind(StrEnum):
    MOVE = "move"
    PIECE = "piece"
    SIDE = "side"
```

### 4.2 Move entity

```python
@dataclass(frozen=True, slots=True)
class MoveClaimEntityView:
    move_uci: str
    position_id: str
    kind: ClaimEntityKind = field(
        default=ClaimEntityKind.MOVE,
        init=False,
    )
```

Only canonical UCI is public. SAN is not projected.

### 4.3 Piece entity

```python
@dataclass(frozen=True, slots=True)
class PieceClaimEntityView:
    color: str
    base_piece_type: str
    base_square: str
    at_position_id: str
    current_piece_type: str
    current_square: str
    kind: ClaimEntityKind = field(
        default=ClaimEntityKind.PIECE,
        init=False,
    )
```

This preserves the same identity/presentation distinction as internal `PieceClaimEntity`.

G0 must not collapse this to a phrase such as `"white knight on c3"`.

### 4.4 Side entity

```python
@dataclass(frozen=True, slots=True)
class SideClaimEntityView:
    color: str
    kind: ClaimEntityKind = field(
        default=ClaimEntityKind.SIDE,
        init=False,
    )
```

### 4.5 Public union

```python
ClaimEntityView = (
    MoveClaimEntityView
    | PieceClaimEntityView
    | SideClaimEntityView
)
```

Projection dispatch is by exact internal entity type only. There is no generic `repr()` fallback.

---

## 5. ClaimView v0.2

Freeze:

```python
@dataclass(frozen=True, slots=True)
class ClaimView:
    claim_id: str
    base_position_id: str
    confidence: str
    scope: str
    subject: MoveClaimEntityView
    predicate: str
    objects: tuple[ClaimEntityView, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    importance: float | None = None
```

### Required projection

For each validated P10 claim:

```text
claim_id          <- exact claim id
base_position_id  <- exact claim base
confidence        <- ClaimConfidence.value
scope             <- ClaimScope.value
subject           <- lossless typed entity projection
predicate         <- ClaimPredicate.value
objects           <- exact object order, typed projection
evidence_ids      <- exact evidence-id tuple
importance        <- exact value; strict current P10 requires None
```

No P11/P12 code may rewrite a claim before public projection.

---

## 6. Which claims are public

`MoveAnalysisResult.claims` contains **all validated P10 claims** in canonical P10 tuple order.

P11 does not delete claims. It identifies the compact primary explanation.

Therefore G0 separately exposes:

```python
selected_claim_ids: tuple[str, ...]
```

which is exactly:

```text
ExplanationSelection.selected_claim_ids
```

in P11 priority/render order.

This separation gives structured callers both:

- the complete strict claim set;
- the minimal selected explanation.

Every `selected_claim_id` must resolve exactly once in `claims`.

---

## 7. CommentaryView v0.2

Freeze:

```python
@dataclass(frozen=True, slots=True)
class CommentaryView:
    text: str
    sentences: tuple[str, ...]
    used_claim_ids: tuple[str, ...]
```

Projection from P12 is exact:

```text
text           <- RenderedCommentary.text
sentences      <- RenderedCommentary.sentences
used_claim_ids <- RenderedCommentary.used_claim_ids
```

For COMMENTARY mode:

```text
commentary.used_claim_ids == result.selected_claim_ids
```

For a non-empty selection:

```text
len(commentary.sentences) == len(result.selected_claim_ids)
commentary.text == " ".join(commentary.sentences)
```

For an empty selection:

```text
commentary.text == "No verified explanation is available."
commentary.sentences == ()
commentary.used_claim_ids == ()
```

---

## 8. MoveAnalysisResult v0.2

Freeze the public result as:

```python
@dataclass(frozen=True, slots=True)
class MoveAnalysisResult:
    schema_version: str
    position_fen: str
    judgement: JudgementSummary
    claims: tuple[ClaimView, ...]
    selected_claim_ids: tuple[str, ...] = ()
    variations: tuple[VariationView, ...] = ()
    commentary: CommentaryView | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

Current G0 keeps `variations == ()`.

A separate public evidence/variation schema is not required to complete the deterministic MVP.

`evidence_ids` remain opaque request-local provenance handles. G0 does not invent a public
EvidenceView.

---

## 9. OutputMode semantics

`OutputMode` controls **presentation**, not the underlying explanation analysis.

### 9.1 STRUCTURED

```text
P0-P11 execute
claims populated
selected_claim_ids populated
commentary = None
```

### 9.2 COMMENTARY

```text
same P0-P11 execution
same claims
same selected_claim_ids
+ P12 render
commentary populated
```

Within one application execution path, the mode branch occurs **only after P11 closure**. Thus mode
selection itself may not change any engine call, P7 probe, claim, graph, or selection.

The contract is therefore structural:

```text
mode has no authority before P12
P12 performs no engine/P7 work
```

Application-unit parity is proven with deterministic fakes/spies over the same semantic inputs.

Cross-request byte equality on a real engine is required only under the reproducible G0 engine
profile from §15. Arbitrary caller-supplied time-based budgets are not promised to produce
byte-identical repeated engine observations across separate requests.

This distinction avoids making nondeterministic wall-clock scheduling part of the public semantic
contract.

---

## 10. Strict heuristic policy

Current MVP has no public HEURISTIC claim contract.

If:

```python
request.options.allow_heuristic_claims is True
```

G0 must fail closed with `FeatureUnavailableError` **before FEN parsing, request-session reset,
or any engine work**.

This is an explicit schema-0.2 behavior change. Schema 0.1 accepted the flag but effectively
ignored it because no explanation path was wired.

Do not silently interpret the flag as permission to surface detector-only hypotheses.

---

## 11. Internal explanation outcome

Introduce one internal application/service boundary value, for example:

```python
@dataclass(frozen=True, slots=True)
class MoveExplanationOutcome:
    claims: tuple[ExplanationClaim, ...]
    graph: ExplanationGraph
    selection: ExplanationSelection
```

The exact module is an implementation choice.

This value is internal and must not be exported from top-level `calliope`.

It deliberately excludes commentary; P12 remains optional presentation invoked only for
COMMENTARY mode.

---

## 12. Canonical explanation pipeline

Use one internal pipeline service, for example:

```python
class MoveExplanationPipeline:
    def explain(
        self,
        base: PositionSnapshot,
        played: ChessMove,
        judgement: MoveJudgement,
        position_analysis: EngineAnalysis,
    ) -> MoveExplanationOutcome:
        ...
```

The pipeline owns:

- `BadMoveExplainer`;
- `GoodMoveExplainer`;
- frozen P7 probe settings;
- `EvidenceBuilder`;
- `ClaimBuilder`;
- `GraphBuilder`;
- `ExplanationSelector`;
- `ExplanationSelectionValidator`.

It must not own or create another engine process.

---

## 13. Quality routing

Routing is closed over the current `MoveQuality` vocabulary.

### MISTAKE / BLUNDER

Use P8 only:

```text
BadMoveExplainer.explain(...)
 -> BadMoveExplanationResult
 -> EvidenceBuilder.build_bad_move
 -> ClaimBuilder.build_bad_move
```

### BEST / EXCELLENT / GOOD

Use P9 only:

```text
GoodMoveExplainer.prepare(...)
 -> build_branches(...)
 -> verify_counterfactuals(...)
 -> explain_strong_move(...) OR explain_only_move(...)
 -> GoodMoveExplanationResult
 -> EvidenceBuilder.build_good_move
 -> ClaimBuilder.build_good_move
```

The P9 mode is the already-frozen result of `GoodMoveExplainer.prepare`:

```text
STRONG_MOVE
ONLY_MOVE_CANDIDATE
```

G0 must not recreate the mode decision from public DTO fields.

### INACCURACY

No current strict P8/P9 explanation family applies.

Create the canonical empty P10 package:

```python
EvidenceBundle(base.position_id, (), ())
claims = ()
```

Then still pass through P11 normally.

Do not manufacture a generic reason.

### Routing closure test

G0 must pin, against the imported frozen service constants:

```text
P8 route set == bad_move.ELIGIBLE_QUALITIES
P9 route set == good_move.ELIGIBLE_QUALITIES
P8 ∩ P9 == {}
all MoveQuality values - P8 - P9 == {INACCURACY}
```

If a quality is routed to P8 or P9 and that explainer returns its `NOT_APPLICABLE` outcome,
G0 treats that as an internal contract error. It must **not** silently convert a routing mismatch
into an empty explanation.

### Public MultiPV effect on P9

P9 representative alternatives come from the public base-position MultiPV basis, capped at two.

Therefore public `AnalysisBudget.multipv` materially affects explainability:

- `multipv=1`: P9 has no representative alternative and current strict P9 returns silence;
- `multipv>=2`: at least one representative alternative may be available;
- larger values still feed only the frozen at-most-two alternatives into P9.

This changes explanation availability, not P9 semantics.

All real G0 fixtures must specify their `AnalysisBudget` explicitly rather than relying on a
mutable default.

---

## 14. Empty/silent path still uses P11

All silent cases, including:

- INACCURACY;
- P8/P9 supported pipeline producing no eligible P10 claim;
- equivalent alternatives;
- quiet BEST;
- other current strict vocabulary gaps;

must end in:

```text
EvidenceBundle(base, (), ())
-> GraphBuilder
-> ExplanationSelector
-> selected_claim_ids == ()
```

COMMENTARY mode then produces the P12 frozen meta text.

STRUCTURED mode returns empty claims/selection and no commentary.

---

## 15. Reproducible engine and P7 policy

The judgement budget and the P7 verification budget remain distinct contracts, but G0 also needs a
request-level engine-state policy so repeated public tests are meaningful.

### 15.1 Request isolation

One Stockfish process is still shared for the lifetime of `CalliopeEngine`, but **each public
`AnalyzeMoveService.execute()` request begins a new UCI game/session before its first engine
analysis**.

Freeze an internal request-session port, for example:

```python
class EngineRequestSessionPort(Protocol):
    def begin_request(self) -> None: ...
```

`StockfishAdapter` implements this without starting another process.

The production adapter must ensure:

- every request receives a fresh opaque game token;
- all engine analyses within that request use the same token;
- the first analysis of a new token causes the UCI new-game boundary;
- the next public request uses a different token;
- no unexpected new-game boundary is inserted between judgement analysis and that request's P7
  probes.

Using python-chess's `game=` analysis parameter with a fresh request token is an acceptable
implementation, because it drives `ucinewgame` at the request boundary. An equivalent explicit
hash-clear/new-game implementation is also acceptable if independently tested.

The request boundary must reset prior-request search state sufficiently that the G0 reproducibility
profile does not inherit the preceding request's transposition-table history.

### 15.2 Judgement engine options

G0 fixes the non-budget engine options used by the public judgement path:

```python
threads = 1
hash_mb = 16
```

The public `AnalysisBudget` still controls:

- depth;
- nodes;
- time_ms;
- multipv.

These fixed options are not new public knobs in schema 0.2.

The default public judgement profile remains depth-bounded:

```text
depth = 12 when no explicit depth/nodes/time limit is supplied
multipv = 5 when not supplied
threads = 1
hash_mb = 16
```

### 15.3 P7 settings

P7 uses one injected frozen profile:

```python
EngineSettings(
    limit=EngineLimit(depth=12, time_ms=2000),
    multipv=1,
    threads=1,
    hash_mb=16,
)
```

This matches the established P9 real-acceptance profile and satisfies the current P7 contract:

- `time_ms` is present;
- `time_ms <= 2000`;
- `multipv == 1`;
- `threads == 1`.

The 2000 ms value is a safety cap. G0 real reproducibility fixtures must assert that every relevant
non-terminal P7 engine line reaches the requested depth 12; otherwise that run does not qualify as
a reproducibility golden.

Do not pass the top-level judgement settings directly into P7.

There is no public P7-budget option in schema 0.2.

### 15.4 What G0 promises

For arbitrary caller budgets, especially wall-clock `time_ms` limits, G0 guarantees semantic
safety and validation but does **not** promise byte-identical repeated Stockfish observations
across separate executions.

Real cross-request parity and byte-exact deterministic commentary goldens are required only when
all of the following hold:

- request session starts clean;
- judgement uses an explicit deterministic G0 fixture budget;
- `threads=1`;
- `hash_mb=16`;
- P7 uses the frozen profile above;
- depth-bound completion is observed rather than time-cap preemption.

Application-unit mode parity remains a structural property independent of real-engine scheduling.

---

## 16. P10-P12 closure

After P8/P9 projection:

1. construct P10 EvidenceBundle;
2. build P10 claims;
3. rerun P10 ClaimValidator;
4. build P11 graph with exact bundle/claims identity;
5. select P11 primary claims;
6. rerun P11 selection validation;
7. return `MoveExplanationOutcome`.

No application code may bypass a P10/P11 validator because the pipeline itself produced the
objects.

For COMMENTARY mode only:

8. call `DeterministicExplanationRenderer.render(graph, selection)`;
9. project the returned immutable P12 value to `CommentaryView`.

---

## 17. AnalyzeMoveService orchestration

The application service keeps ownership of the public use case.

Recommended dependency shape:

```python
@dataclass(slots=True)
class AnalyzeMoveService:
    chess: ChessRulesPort
    engine: EngineAnalysisPort
    judge: MoveJudge
    explanations: MoveExplanationPipeline
    renderer: DeterministicExplanationRenderer
    ...
```

Canonical order:

1. validate public options that must fail before work;
2. resolve judgement settings;
3. parse FEN;
4. canonicalize played move;
5. run base MultiPV analysis;
6. run played-move forced analysis;
7. produce `MoveJudgement`;
8. run strict explanation pipeline P4-P11;
9. if COMMENTARY, run P12;
10. project DTOs;
11. return one `MoveAnalysisResult`.

The service must not call P12 before P11 closure.

---

## 18. Error policy

### Invalid public input / engine / judgement

Existing typed errors continue to propagate.

### Public projection error

Add:

```python
class ClaimProjectionError(ApplicationError):
    """A validated internal claim cannot be losslessly projected to schema 0.2."""
```

Use it for unknown entity types or any impossible projection shape. Do not fall back to
`repr()`, raw `TypeError`, or dropped fields.

### Explanation semantic inconsistency

P4-P12 owned errors propagate.

Important error families that may reach the application caller include:

- `IncompatiblePositionObservationError`;
- `IncompatibleBoardDeltaError`;
- `IncompatibleTacticalContextError`;
- `InvalidProbeRequestError` / `IncompatibleProbeResultError`;
- `IncompatibleBadMoveContextError`;
- `IncompatibleGoodMoveContextError`;
- `ExplanationEvidenceError`;
- `ExplanationClaimError` / `IncompatibleClaimEvidenceError`;
- `ExplanationGraphError`;
- `ExplanationSelectionError`;
- `ExplanationRenderError`;
- `ClaimProjectionError`.

All remain `CalliopeError` descendants.

Do **not** silently convert an internal validation failure into an empty explanation.

"Unable to explain" is represented by a valid empty strict result, not by swallowing errors.

### Unsupported heuristic mode

`FeatureUnavailableError` before FEN parsing, request-session reset, or engine work.

### COMMENTARY

P12 deterministic renderer failure is an analysis failure in G0 because it indicates an internal
contract violation. The "commentary failure does not invalidate analysis" fallback rule applies
to optional P13 LLM verbalization later, not to a broken deterministic P12 invariant.

---

## 19. Projection is not reasoning

Public projection helpers may only copy/serialize already-validated values.

They may:

- use enum `.value`;
- copy canonical UCI;
- copy position ids;
- copy exact tuples;
- dispatch by exact entity type.

They may not:

- inspect a board;
- derive SAN;
- infer actor/target roles;
- infer only-move semantics;
- change confidence;
- change scope;
- drop object frame fields;
- select different claims;
- use engine scores to rank claims.

Unknown entity type fails closed with an application-owned/projection error rather than `repr()`.

If a new error is needed, use a narrow Calliope-owned typed error; do not use raw `TypeError`.

---

## 20. Composition root

`create_calliope_engine()` must wire one shared PythonChess adapter and one shared Stockfish
process.

Conceptual graph:

```text
PythonChessAdapter --------------------------+
  |                                         |
  +-> PositionFactExtractor                 |
  +-> BoardDeltaAnalyzer                    |
  +-> tactical observation port             |
  +-> CounterfactualAnalyzer.chess/rules    |
  +-> BadMoveExplainer                      |
  +-> GoodMoveExplainer                     |
                                            |
StockfishAdapter ----------------------------+
  +-> EngineRequestSessionPort
  +-> AnalyzeMoveService initial analysis
  +-> CounterfactualAnalyzer engine

TacticalDetector
CounterfactualAnalyzer
BadMoveExplainer
GoodMoveExplainer
MoveExplanationPipeline
DeterministicExplanationRenderer
AnalyzeMoveService
CalliopeEngine
```

Do not start a second Stockfish process for explanation.

At the start of each valid public request, after public/FEN/move validation and before the first
engine analysis, `AnalyzeMoveService` begins exactly one new request session on the same
`StockfishAdapter`.

All judgement and P7 calls in that request use that same request session.

The existing `CalliopeEngine.close()` still closes the one owned Stockfish process exactly once.

Composition tests must prove:

- one adapter/process;
- one request reset per analyzed request;
- no mid-request reset;
- the same adapter serves judgement and P7;
- close once.

---

## 21. Public facade

No method is added to `CalliopeEngine`.

Public invocation remains:

```python
engine.analyze_move(request)
```

G0 must not expose P8/P9/P10/P11/P12 analyzers as public facade methods.

Top-level `calliope` may continue exporting the existing request/result/facade types. The new
nested claim entity DTOs do not need top-level exports for G0; they remain available from
`calliope.contracts`.

---

## 22. Metadata

Retain the existing engine/analysis/forcedness metadata and add one strict-explanation section.

Freeze the semantic metadata keys for schema 0.2:

```python
{
    "position_id": ...,
    "engine": {
        "name": ...,
        "version": ...,
    },
    "analysis": {
        "depth": ...,
        "nodes": ...,
        "time_ms": ...,
        "multipv": ...,
        "threads": 1,
        "hash_mb": 16,
    },
    "forcedness": {
        "acceptable_move_count": ...,
        "best_to_second_gap_cp": ...,
    },
    "explanation": {
        "mode": "strict",
        "counterfactual": {
            "depth": 12,
            "time_ms": 2000,
            "multipv": 1,
            "threads": 1,
            "hash_mb": 16,
        },
    },
}
```

No timing measurements, elapsed milliseconds, engine node counters, request ids, hash tokens, or
other execution-noise fields belong in public metadata.

For otherwise equivalent structured/commentary results, the **entire metadata mapping must be
equal**, not merely an unspecified subset.

Do not put P10/P11 semantic truth into ad-hoc metadata. Claims and selection have typed public
fields.

---

## 23. Output-mode equivalence and reproducibility

The strongest invariant is structural:

```text
STRUCTURED and COMMENTARY execute the same code and work through P11.
Only COMMENTARY invokes P12 afterwards.
```

A deterministic fake-engine/application test must prove that switching output mode does not
change:

- initial engine call count or arguments;
- request-session reset count;
- P7 probe count or arguments;
- judgement;
- claims;
- selected ids;
- variations;
- metadata.

It must also prove:

```text
structured.commentary is None
commentary.commentary is not None
```

### Real cross-request parity

A real Stockfish structured request and a separate real Stockfish commentary request may be
compared byte/semantically only under the §15 reproducibility profile.

For those G0 parity fixtures require identical:

- schema version;
- position FEN;
- judgement;
- claims;
- selected claim ids;
- variations;
- complete metadata.

COMMENTARY adds only `CommentaryView`.

### Arbitrary time-based budgets

Do not write a test or public claim that arbitrary wall-clock-budget requests are byte-identical
across separate executions. They are only required to remain semantically safe and validated.

P12 itself never adds an engine or P7 call.

---

## 24. Public scope safety

Required G0 public fixtures must prove:

### TESTED_RESPONSE

Public ClaimView includes:

```text
scope == "tested_response"
```

and commentary retains the failed-tested-response wording.

### REPRESENTATIVE_ALTERNATIVES

Public ClaimView includes:

```text
scope == "representative_alternatives"
```

and public entity views preserve the failed alternatives' base-position frame.

No DTO projection may imply exhaustive alternatives.

---

## 25. Public piece-frame safety

For a selected hanging-piece claim such as the existing knight fixture, the public piece object
must retain at minimum:

```text
color
base_piece_type
base_square
at_position_id
current_piece_type
current_square
```

and the values must match the internal P10 object exactly.

This is separate from P12 text such as:

```text
white knight from c3
```

The public structured representation must remain richer than the prose.

---

## 26. G0 real golden gate

G0 must exercise the public facade, not internal helpers.

The primary real test shape is:

```python
with create_calliope_engine(stockfish_path, ...) as engine:
    result = engine.analyze_move(AnalyzeMoveRequest(...))
```

or an equivalent direct `CalliopeEngine` composed through the production composition root.

No G0 fixture may call P8-P12 directly as the system under test.

Every real golden request must specify its `AnalysisBudget` explicitly.

For fixtures intended to prove reproducibility or structured/commentary parity:

- use the §15 request-isolation policy;
- use depth-bounded judgement settings with explicit `multipv`;
- keep threads/hash at the frozen 1/16 values;
- require P7 non-terminal lines to reach depth 12 before the 2000 ms safety cap;
- run from a clean request session each time.

Existing P10/P11/P12 real FEN/move fixtures may be reused, but their earlier result is not assumed
to carry over automatically. G0 must re-observe them through the public path under the G0
reproducibility profile and independently assert the expected surfaced semantics.

Internal helper assertions may inspect the returned public DTO only.

---

## 27. Required real fixture classes

The integrated public golden gate covers at least:

1. newly hanging piece / material-loss blunder;
2. fork allowed;
3. removal-of-defender tactic;
4. exact immediate mate allowed;
5. engine-verified mate line;
6. exact forced response;
7. representative only-move preservation;
8. equivalent alternatives -> strict silence;
9. verified tested-response material or mate threat;
10. quiet BEST -> strict silence.

Where an existing real Stockfish fixture already proves the internal class, reuse its FEN/move and
re-observe it under the G0 profile rather than inventing a weaker replacement.

Not every internal 14-form template must have a separate real Stockfish public fixture; P12 already
has complete 14-form unit goldens. G0's purpose is full public-path integration.

### Mate-missed roadmap class

The older roadmap listed a separate "mate missed" fixture. Current strict P8/P9/P10 vocabulary has
no dedicated `MISSED_MATE` claim family. G0 therefore does **not** invent one.

If a concrete missed-mate position maps to an already-existing strict predicate, it may be covered
under that predicate's fixture. Otherwise a dedicated missed-mate explanation class is deferred
until its evidence/claim semantics are separately designed.

---

## 28. Golden assertions

For each public real fixture:

- `schema_version == "0.2"`;
- judgement matches the configured policy;
- every public claim corresponds exactly to an internal validated P10 claim shape;
- every claim has explicit confidence and scope;
- every selected id resolves in public claims;
- selection order is preserved;
- COMMENTARY used ids equal selected ids;
- no detector-only claim leaks;
- no unsupported FORCED claim leaks;
- no speculative intent statement appears;
- relation-free P11 remains relation-free in the surfaced semantics;
- quiet/unsupported cases retain judgement and empty strict explanation.

The public golden oracle is semantic first; commentary wording may also be byte-exact because P12
is intentionally deterministic.

---

## 29. STRUCTURED and COMMENTARY public acceptance

Every representative G0 fixture should be run in both output modes where cost is reasonable.

At minimum, a shared subset must prove:

```text
structured.claims == commentary.claims
structured.selected_claim_ids == commentary.selected_claim_ids
structured.judgement == commentary.judgement
structured.commentary is None
commentary.commentary is not None
```

The engine/P7 call count must not increase merely because P12 text is requested.

---

## 30. Existing P3 unit tests

Update the old judgement-only application tests rather than deleting their guarantees.

Retain tests for:

- budget resolution;
- invalid input short circuit;
- two initial judgement analyses;
- played analysis root move;
- judge error propagation;
- engine error propagation;
- metadata.

Replace the old:

```text
COMMENTARY rejected before any work
```

assertion with new mode-parity/wiring tests.

Add explicit tests that:

- `allow_heuristic_claims=True` fails before FEN parsing/session reset/engine work;
- judgement settings always carry `threads=1, hash_mb=16`;
- `multipv=1` can legitimately yield P9 silence because no representative alternative exists;
- one request-session reset happens before the first engine call;
- P8/P9 routing sets are exactly the imported frozen eligibility sets;
- a routed explainer returning NOT_APPLICABLE is treated as an internal error, not silence.

Use injected fake explanation/session/renderer dependencies in application-unit tests so P3/G0
orchestration can be tested without invoking real P4-P12 services.

---

## 31. Integration dependency tests

Add a production-composition test proving:

- one PythonChessAdapter instance is shared where appropriate;
- one StockfishAdapter process is owned;
- the same Stockfish adapter serves initial analysis and P7;
- close hook closes it once;
- no hidden engine constructor exists in P4-P12 services.

Implementation may test this through spies/fakes rather than process introspection.

---

## 32. No P13 dependency

G0 does not implement or import an LLM.

There is:

- no LLM client;
- no prompt;
- no free-form generated prose;
- no LLM validation path.

The MVP is considered deterministic-complete after G0.

P13 becomes a post-G0 optional extension:

```text
P13 optional LLM verbalizer
 -> consumes already-public/validated semantics
 -> validated output or P12 fallback
```

If P13 is later implemented, its failure/rejection tests are added then.

---

## 33. G0 completion definition

After G0:

```text
FEN + played move
 -> public CalliopeEngine
 -> real python-chess + Stockfish
 -> judgement
 -> strict P4-P10 evidence-backed claims
 -> P11 minimal selection
 -> optional deterministic P12 commentary by OutputMode
 -> scope-complete schema 0.2 MoveAnalysisResult
```

works end-to-end.

This is the deterministic Calliope MVP.

---

## 34. Recommended implementation packet

Because all P4-P12 internals are already independently frozen and accepted, G0 should be one
integrated implementation packet after this A0 review.

Suggested scope:

```text
G0-I0 integrated application/public wiring

production:
- contracts schema 0.2
- scope-complete entity/claim/commentary DTOs
- internal MoveExplanationPipeline
- AnalyzeMoveService integration
- composition root integration

tests:
- application unit updates
- projection/adversarial tests
- structured/commentary parity
- production composition tests
- real Stockfish public golden gate
- full regression
```

Do not split by P8/P9/P10/P11/P12 again; those semantics are already frozen.

---

## 35. Independent review questions

The A0 reviewer must explicitly answer:

1. Is schema 0.2 required by the public shape change?
2. Does ClaimView preserve ClaimScope?
3. Do typed public entities preserve move/piece frame semantics without board re-analysis?
4. Is exposing all P10 claims plus separate selected ids sound?
5. Does structured mode expose the same strict claims/selection as commentary mode?
6. Does COMMENTARY add presentation only?
7. Is CommentaryView sentence-level provenance sufficient?
8. Is the public entity discriminator stable enough for transports?
9. Are opaque evidence ids acceptable without introducing a public EvidenceView in G0?
10. Is INACCURACY safe-silent under current P8/P9 vocabulary?
11. Is quality routing exactly aligned with current P8/P9 eligibility?
12. Does P9 mode remain owned by GoodMoveExplainer rather than G0?
13. Are P7 settings correctly separated from public judgement AnalysisBudget?
14. Does one shared Stockfish process serve both initial and counterfactual analyses?
15. Can explanation semantic failures accidentally be swallowed as silence?
16. Is heuristic mode correctly fail-closed?
17. Does public projection avoid new chess reasoning?
18. Is base-frame piece identity loss prevented?
19. Is tested-response scope preserved publicly?
20. Is representative-alternative scope preserved publicly?
21. Can OutputMode change engine/P7 work?
22. Does G0 preserve the single CalliopeEngine facade?
23. Are existing P3 guarantees retained?
24. Is P13 genuinely optional rather than a hidden G0 dependency?
25. Is one integrated G0 implementation packet reviewable?

---

## 36. Frozen summary

G0 connects the already-trusted P4-P12 internals to the product boundary.

The central decisions are:

- public schema bumps to `0.2`;
- claims become scope-complete and entity-frame-preserving;
- all validated P10 claims are public;
- P11 selected ids are public separately;
- STRUCTURED and COMMENTARY run identical strict analysis through P11;
- COMMENTARY alone adds deterministic P12 prose;
- P7 uses its own frozen bounded settings, not the top-level MultiPV budget;
- one PythonChess adapter and one Stockfish process are shared through composition;
- valid silence is surfaced as empty claims/selection, not hidden errors;
- internal validation errors propagate rather than being swallowed;
- public projection copies semantics and performs no chess reasoning;
- P13 is optional and moves after deterministic G0 completion.

After G0, Calliope is a complete deterministic evidence-first chess commentary engine through its
actual public `CalliopeEngine.analyze_move()` path.
