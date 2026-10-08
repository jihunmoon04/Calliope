> **LEGACY — FROZEN, NOT THE CURRENT DESIGN.** This document describes the MVP-era implementation preserved at tag `legacy-mvp-g0`. It is kept only as historical reference for the redesign; nothing in it is a current requirement or decision. Current design: [`docs/design/`](../design/README.md). Index: [`docs/README.md`](../README.md).

# Calliope Architecture

Status: **deterministic MVP baseline — G0 closed**

Closure baseline: [`mvp-g0-closure.md`](mvp-g0-closure.md).

## 1. Goal

Calliope explains a chess move without asking an LLM to discover why it is good or bad.

The system separates three questions:

1. **How good is the move?** — Stockfish.
2. **What facts and consequences explain that judgement?** — deterministic analysis plus engine-verified counterfactual probes.
3. **How should verified claims be expressed to a human?** — the implemented deterministic P12 renderer, with an optional constrained LLM verbalizer only in a future P13.

An LLM is not part of the closed G0 production path and, if added later, is not a chess authority.

## 2. Invariants

### 2.1 Stockfish owns move-quality judgement

Calliope may derive labels such as BEST, GOOD, MISTAKE, or BLUNDER from normalized engine output, but does not override Stockfish's underlying ranking/evaluation.

Judgement may use:

- best-move and played-move score
- MultiPV rank
- WDL / expected-score change
- forced-mate transitions
- distance from second-best / acceptable alternatives
- analysis stability

### 2.2 Facts and explanations are separate

```text
raw board fact
  -> candidate effect
  -> tactical/positional hypothesis
  -> verification
  -> evidence
  -> explanation claim
```

A true fact such as "Nf5 attacks Qd6" is not automatically the reason Nf5 is best.

### 2.3 Claims require evidence

Confidence vocabulary:

- `EXACT`: follows from the reviewed deterministic rule/board contract.
- `ENGINE_VERIFIED`: supported by controlled Stockfish/counterfactual evidence.
- `FORCED`: reserved confidence value, but current P10/P11 strict public paths admit no FORCED claim from P8/P9.
- `HEURISTIC`: reserved for future reviewed work; schema 0.2 does not expose heuristic claims and `allow_heuristic_claims=True` fails closed.

The active P10 validator, not this vocabulary list, decides which predicate/confidence pairs are
currently legal.

### 2.4 No inferred player intent

Allowed: "this move prevents ...Bg4", "this move enables Qh5".

Disallowed by default: "the player intended...", "the player wanted...", "the plan was...".

### 2.5 Immutable analysis basis

Every result refers to an immutable `PositionSnapshot` / `position_id`. Mutable `python-chess.Board` objects are runtime adapter objects, not durable domain truth.

## 3. Dependency direction

```text
application
   |
   +------> services ------+
   |                       |
   +------> adapters ------+
                           |
                           v
                         domain
```

Domain modules must not depend on Stockfish, python-chess, LLM SDKs, frameworks, databases, or UI code.

## 4. Package layout

Current implemented packages:

```text
src/calliope/
  domain/
    chess/          immutable positions, moves and piece identity
    engine/         score, WDL, PV, settings and MoveJudgement
    analysis/       P4-P9 deterministic/counterfactual analysis models
    explanation/    P10-P12 evidence, claims, graph, selection and rendered commentary
    commentary/     placeholder package only; no active P13 contract

  services/
    position/       PositionFactExtractor and BoardDeltaAnalyzer
    judgement/      MoveJudge
    tactics/        TacticalDetector
    counterfactual/ CounterfactualAnalyzer
    explanation/    P8-P12 explain/build/validate/select/render services

  adapters/
    python_chess/   active python-chess boundary
    stockfish/      active UCI/Stockfish boundary + request-wide session isolation
    llm/            placeholder boundary only; no production LLM implementation

  application/
    analyze_move.py active canonical move use case
    analyze_game.py explicit unavailable use case
    explanation.py  P8-P11 application pipeline
    projection.py   schema-0.2 public projection
```

Placeholder packages do not count as implemented P13 functionality.

## 5. Core models

### PositionSnapshot

Immutable position identity: `position_id`, FEN and rule state. Mutable `python-chess.Board`
instances remain adapter-local.

### ChessMove

Canonical move value. UCI is semantic identity; SAN is optional position-dependent presentation
metadata and is not public claim identity.

### EngineAnalysis / EngineLine

Normalized Stockfish observations with exact `EngineSettings`, ranked lines, score/WDL, PV,
depth/seldepth and nodes.

### MoveJudgement

Answers **how good was this move according to the configured engine policy?** It contains no
prose reason.

### PositionFacts / BoardDelta / tactical analysis models

Deterministic P4-P6 observations and candidate mechanisms. They are not explanation authority by
themselves.

### CounterfactualProbe and verified P7 results

Controlled engine experiments used by P8/P9. The P7 settings/profile are separately bounded and
are not copied from the public judgement MultiPV budget.

### EvidenceBundle

P10 provenance package retained together with its claims. Evidence remains internal in schema 0.2.

### ExplanationClaim

The smallest proposition allowed to reach public structured output or commentary. Current public
claims preserve:

- canonical claim id and base position;
- structured move subject;
- predicate;
- confidence;
- explicit scope;
- typed move/piece/side objects;
- evidence ids;
- `importance=None` under current P10 builders.

Current P8/P9 -> P10 production paths emit only the reviewed EXACT / ENGINE_VERIFIED combinations.
FORCED is not an active public claim confidence in the deterministic MVP.

### ExplanationGraph

Retains the exact validated P10 evidence/claim package.

The relation vocabulary exists structurally, but **no relation rule is active in MVP-P11**:

```text
relations == ()
```

Shared pieces, moves, evidence ids, PVs or ordering do not authorize a causal relation.

### ExplanationSelection

Contains selected claim ids in deterministic render/priority order, at most three claims.

Current selection has no WHY_GOOD/WHY_BAD intent object. It is recomputed from the frozen:

- predicate -> selection-family map;
- valid (predicate, confidence) -> priority tier map;
- canonical claim tuple order.

Current families are mate outcome, material outcome, tactical mechanism, forced response and
tested threat.

### RenderedCommentary

P12 deterministic output:

```text
text
sentences
used_claim_ids
```

For a non-empty result, sentences pair 1:1 with selected claim ids. P12 does not inspect the board
or engine to discover new truth.

### P13 verbalization models — future, not implemented

A future P13 may introduce a constrained verbalization request/result contract and validation
policy. `VerbalizationRequest`, generated LLM commentary and a commentary validator are **not
part of the closed G0 production model**.

## 6. Main analysis flows

### Good / best move

```text
Stockfish judgement
 -> before/after delta
 -> useful effects/threats
 -> compare serious alternatives
 -> best-response / ignored-threat tests when relevant
 -> evidence
 -> verified claims
 -> minimal explanation
```

Primary question: **What does this move achieve that comparable alternatives do not?**

### Mistake / blunder

```text
Stockfish judgement
 -> strongest punishment
 -> opponent resources before/after
 -> trace lost defense/control/safety
 -> verify punishment
 -> evidence and causal claims
```

Primary question: **What did this move newly allow?**

### Only / forced move

```text
MultiPV distribution
 -> evaluation/result cliff
 -> analyze why alternatives fail
 -> minimal refutations
 -> explain what the move uniquely preserves
```

Primary question: **Why do the alternatives fail?**

### Quiet / near-equivalent move

Do not invent strategic depth merely because one move is ranked first. When several moves are effectively equivalent, state only concrete supported effects and avoid overstating uniqueness.

## 7. Service responsibilities

Implemented deterministic services include:

- **PositionFactExtractor**: position -> deterministic facts;
- **BoardDeltaAnalyzer**: before/after facts + move -> reconciled delta;
- **MoveJudge**: normalized engine analyses -> `MoveJudgement`;
- **TacticalDetector**: deterministic candidate tactical observations;
- **CounterfactualAnalyzer**: bounded P7 engine interventions;
- **BadMoveExplainer / GoodMoveExplainer**: frozen P8/P9 explanation protocols;
- **EvidenceBuilder**: accepted P8/P9 result -> P10 evidence package;
- **ClaimBuilder**: eligible evidence -> P10 claims;
- **ClaimValidator**: exact P10 evidence/claim compatibility;
- **GraphBuilder**: revalidate P10 package and construct a relation-free P11 graph;
- **ExplanationGraphValidator**: validate retained P10 package and enforce the empty-relation policy;
- **ExplanationSelector**: deterministic family/priority selection;
- **ExplanationSelectionValidator**: exact selection recomputation;
- **DeterministicExplanationRenderer**: P12 selected claims -> deterministic commentary;
- **MoveExplanationPipeline**: application-level P8-P11 routing/closure.

There is no standalone `ThreatDetector`, no service named `ExplanationGraphBuilder`, and no
production `CommentaryValidator` in the G0 baseline. Those names must not be read as implemented
components.

An additive internal positional foundation provides `PositionAnalyzer`,
`TransitionAnalyzer` and `LineAnalyzer` on top of P4/P5 and existing piece identity.
It currently adds pawn/file features and bounded supplied-line observations, with no
engine calls, judgement or public commentary integration. Definitions, scope and review
status are in [positional-foundation.md](positional-foundation.md). Independent re-review
of `de020c8` returned READY; the F1 correspondence fix is verified.

The [activity foundation](positional-activity-design.md) (`activity_v1`) adds slider rays,
square-access indexes and current-side legal-action summaries as internal services
(`ActivityAnalyzer`, `ActivityTransitionAnalyzer`, `ActivityLineAnalyzer`). It is
independently reviewed READY at `7628ed5` after F1/F2 corrections; it has no engine calls,
judgement, public schema or commentary integration.

The internal [common scenario line summary](scenario-line-summary-design.md)
implements shared observation, typed selection, source-linked compression and rendering,
with [EXCHANGE rules](exchange-line-summary-design.md) as its first scenario.
The [explanation corpus](scenario-explanation-corpus.md) supplies executable factual
oracles and required/forbidden explanation semantics. Independent design re-review
of PR #29 `c99d6a3` returned READY. ScenarioLineAnalyzer and ScenarioSummaryRenderer
now exist as direct internal modules, with no public schema/composition/export changes.
[A2 evidence](scenario-summary-a2-implementation.md) records acceptance and cost smoke;
Independent A3 review of `7d527b2` returned READY_WITH_CORRECTIONS (C1).
[Correction evidence](scenario-summary-a3-corrections.md) records the promotion digest
fix and related low notes. Independent re-review of `672f162` returned READY;
L4 render cost and L6 shared-validation refactor remain pre-public-integration work.

The observation bridge ([A0](observation-commentary-bridge-design.md),
[I1-D](observation-i1d-played-transition-freeze.md),
[I2-D/I3-D](observation-bridge-i2i3-joint-design.md)) is implemented on
`implementation/i1-i3-observation-bridge`: a one-ply `PLAYED_TRANSITION` scenario, a
dependency-closed compact EXCHANGE ledger, and the explicit opt-in
`CalliopeEngine.analyze_move_with_observations()` returning a schema-0.3 envelope around the
unchanged schema-0.2 result, with zero added Stockfish work. Evidence and cost are in the
[implementation record](observation-bridge-i1-i3-implementation.md); independent review pending.

## 8. Adapter responsibilities

### python-chess — implemented

FEN parsing, legal-move normalization, rule observations, attack/defense primitives and
position reconstruction. Domain values cross the adapter boundary; mutable boards do not.

### Stockfish — implemented

Owns one UCI process per composed `CalliopeEngine`, normalizes analysis results and supports a
request-wide session. Engine-using portions of concurrent public move requests are serialized,
with one fresh game token per request and no mid-request reset.

### LLM — placeholder only

`src/calliope/adapters/llm` currently contains only a boundary placeholder. There is no provider
client, prompt, generated commentary or production P13 path in G0.

If P13 is designed later, provider choice still must not affect chess truth.

## 9. Application use cases

### analyze_move — implemented canonical MVP path

```text
FEN + played move
 -> PositionSnapshot
 -> Stockfish judgement
 -> P4-P9 strict deterministic/counterfactual analysis
 -> P10 EvidenceBundle + validated ExplanationClaim tuple
 -> P11 relation-free graph + deterministic selection
 -> optional P12 deterministic commentary
 -> schema 0.2 MoveAnalysisResult
```

### analyze_game — public method reserved, implementation deferred

`CalliopeEngine.analyze_game()` exists in the facade/contracts, but production composition wires
`AnalyzeGameUnavailable`.

Current behavior is an explicit:

```text
FeatureUnavailableError("game analysis is not available yet")
```

PGN iteration, game-level budgeting, caching and explanation density are future work and are not
part of the deterministic MVP closure.

## 10. Testing strategy

Current repository test layout:

```text
tests/
  unit/
    adapters/
    application/
    domain/
    services/
    test_composition.py
    test_engine_facade.py

  integration/
    python_chess/
    stockfish/
    test_analyze_move_slice.py
```

Real Stockfish acceptance, adversarial claim checks and golden expected/forbidden semantics are
currently implemented inside the unit/integration modules, including
`tests/integration/stockfish/test_g0_public.py`.

There are **no current top-level `tests/golden/` or `tests/adversarial/` directories**.

The primary correctness oracle remains the evidence-backed claim set plus explicitly forbidden
claims/language. P12 also has exact deterministic sentence goldens where its wording is frozen.

## 11. Historical implementation sequence

The original design sequence was:

1. chess and engine value models;
2. python-chess adapter and immutable position identity;
3. Stockfish adapter + normalized `EngineAnalysis`;
4. `MoveJudgement` + forcedness;
5. position facts + board delta;
6. tactical candidates;
7. counterfactual probes;
8. evidence and `ExplanationClaim`;
9. P11 graph/selection;
10. LLM verbalizer/commentary validation;
11. positional feature expansion;
12. Syzygy/tablebase evidence.

Items 1-9 evolved into P0-P12 plus G0 and are complete in their reviewed deterministic forms.

Items 10-12 were **historical planned follow-ons**, not completed G0 components:

- LLM verbalization is optional P13 and requires its own design review;
- positional expansion remains deferred;
- Syzygy/tablebase evidence remains deferred.

## 12. Explicitly deferred

- inferred player intent
- style/personality analysis
- broad opening narratives
- long-range strategic plans without verifiable support
- marketing-style "brilliant move" labels
- UI
- provider-specific prompt optimization


## 13. Public engine facade

Calliope is internally modular but externally behaves as one engine.

The only public application facade is `CalliopeEngine`.

Current method status:

```text
CalliopeEngine
  ├─ analyze_move(AnalyzeMoveRequest) -> MoveAnalysisResult   IMPLEMENTED
  └─ analyze_game(AnalyzeGameRequest) -> GameAnalysisResult  RESERVED / UNAVAILABLE
```

`analyze_game()` currently raises `FeatureUnavailableError` through
`AnalyzeGameUnavailable`; it is not a completed game-analysis pipeline.

External integrations must not call `PositionFactExtractor`, `MoveJudge`,
`CounterfactualAnalyzer`, `ClaimBuilder`, or other internal services directly.

This is an architectural safety rule: every caller must traverse the same judgement,
verification, evidence, claim-validation, and selection pipeline.

### 13.1 Stable public contracts

Public request/result DTOs live outside the internal domain model and are designed to be
serializable. They are an anti-corruption boundary between Calliope internals and callers.

Initial contracts:

- `AnalyzeMoveRequest`
- `AnalyzeGameRequest`
- `AnalysisOptions`
- `AnalysisBudget`
- `MoveAnalysisResult`
- `GameAnalysisResult`
- `JudgementSummary`
- `ClaimView`
- `VariationView`
- `CommentaryView`

Internal models may evolve without forcing every tool/agent integration to understand those
changes.

### 13.2 Output levels

A caller can ask for different presentation depth without changing chess truth:

- `STRUCTURED`: judgement + all validated P10 claims + P11 selected claim ids; no prose.
- `COMMENTARY`: the same P0-P11 result plus P12 deterministic commentary.

The engine always returns the same structured chess semantics regardless of output mode.
P12 is an optional presentation projection over P11, not the canonical analysis.
A future P13 LLM verbalizer, if implemented, remains downstream of this deterministic baseline.

### 13.3 Strictness

Default external-agent usage is strict:

- unsupported claims are never surfaced;
- schema 0.2 rejects heuristic-claim requests before chess/engine work;
- missing verified explanation is a valid empty strict result and is preferable to invention;
- P12 invariant/render failure is an analysis-contract failure and is not silently converted to silence;
- a future optional P13 verbalizer must fall back to the already-valid deterministic P12 result when its generated output fails validation.

## 14. Integration architecture

```text
                         external callers
        ┌───────────────┬───────────────┬───────────────┐
        │ Python        │ Agent Tool    │ MCP/HTTP/CLI  │
        └───────┬───────┴───────┬───────┴───────┬───────┘
                │               adapters         │
                └───────────────┬────────────────┘
                                v
                         CalliopeEngine
                                |
                         application pipeline
                                |
          ┌─────────────────────┼─────────────────────┐
          v                     v                     v
       services              adapters               domain
   analysis/reasoning   Stockfish/python-chess/LLM   truth
```

An agent "skill" is therefore instructions/schema around Calliope, not an alternate reasoning
implementation. An agent "tool" is a transport adapter around `CalliopeEngine`.

## 15. Composition and lifecycle

`CalliopeEngine` owns the application-level composition of move/game use cases.

The G0 composition root now creates and shares:

- one `PythonChessAdapter` across chess/rule observation services;
- one `StockfishAdapter` process for judgement and P7 counterfactual probes;
- request-wide Stockfish sessions that serialize engine-using portions of concurrent public requests;
- deterministic position/tactical/counterfactual services;
- the P8-P11 evidence/claim/selection pipeline;
- the P12 deterministic renderer.

The public facade remains independent of transport.

Long-lived hosts may keep one engine instance. Every public move-analysis request receives a fresh
UCI game token and retains exclusive access to the shared Stockfish process from the first
judgement analysis through the final P7/P11 engine work. P12 and public projection run after that
request session is released.

An optional LLM verbalizer is not part of the closed G0 composition.

## 16. External tool design rule

Prefer small explicit operations over exposing arbitrary internal functions.

Public facade/tool surface:

```text
analyze_move(fen, move_uci, options?)   implemented
analyze_game(pgn, options?)             reserved; currently FeatureUnavailableError
```

Future operations such as `explain_alternative` or `compare_moves` should still delegate into
the same engine and evidence pipeline rather than bypassing it.

Transport adapters may translate JSON to the public DTOs, but must not manufacture
`ExplanationClaim` values themselves.


## 17. MVP implementation baseline

The concrete staged MVP plan is maintained in
[`docs/legacy/mvp-implementation-plan.md`](mvp-implementation-plan.md).

The deterministic delivery sequence is now complete:

```text
P0-P3   executable Stockfish judgement core                         CLOSED
P4-P6   deterministic board facts/deltas and tactical candidates    CLOSED
P7-P9   counterfactual verification and causal explanation flows    CLOSED
P10-P11 evidence-backed claims and minimal explanation selection    CLOSED
P12     deterministic LLM-free commentary                           CLOSED
G0      public integration + integrated real golden gate            CLOSED

P13     optional constrained LLM verbalization                      POST-CLOSURE
```

Two constraints override implementation convenience:

1. detector output never becomes an `ExplanationClaim` without eligible evidence;
2. inability to verify a reason is a valid result and must not be replaced by speculative prose.

The deterministic renderer and G0 public integration are sufficient for the closed deterministic
MVP. Calliope therefore remains a complete evidence-first move-commentary engine without model
availability. P13 is an optional downstream presentation extension, not a completion dependency.
