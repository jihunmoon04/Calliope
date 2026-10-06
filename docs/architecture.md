# Calliope Initial Architecture

Status: **initial design baseline**

## 1. Goal

Calliope explains a chess move without asking an LLM to discover why it is good or bad.

The system separates three questions:

1. **How good is the move?** — Stockfish.
2. **What facts and consequences explain that judgement?** — deterministic analysis plus engine-verified counterfactual probes.
3. **How should verified claims be expressed to a human?** — an LLM verbalizer or deterministic renderer.

The LLM is not a chess authority.

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

Initial confidence classes:

- `EXACT`: follows from board state or deterministic rules.
- `FORCED`: follows from a verified forcing sequence.
- `ENGINE_VERIFIED`: supported by a controlled Stockfish comparison/probe.
- `HEURISTIC`: modelled positional interpretation; initially excluded from strict commentary unless explicitly enabled.

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

```text
src/calliope/
  domain/
    chess/          position, move, game and board-fact models
    engine/         score, WDL, PV and move-judgement models
    analysis/       deltas, effects, motifs, threats and probes
    explanation/    evidence, claims, graph and selection
    commentary/     strict rendering/LLM contracts

  services/
    position/       fact extraction and board-delta analysis
    judgement/      move judgement and forcedness
    tactics/        motif/threat detection and validation
    counterfactual/ controlled alternative/refutation probes
    explanation/    evidence, claims, graph, selection

  adapters/
    python_chess/   python-chess boundary
    stockfish/      UCI/Stockfish boundary
    llm/            verbalization boundary

  application/
    analyze_move.py
    analyze_game.py
```

## 5. Core models

### PositionSnapshot
Immutable position identity: `position_id`, FEN, ply, side to move, castling rights, en-passant state and clocks.

### ChessMove / MoveRecord
`ChessMove` is a canonical move value. UCI is durable identity; SAN is position-dependent presentation. `MoveRecord` connects before-position, move, after-position and ply.

### PositionFacts
Deterministic facts. Initial submodels: `MaterialState`, `AttackMap`, `DefenseMap`, `PieceState`, `KingState`, `PawnStructure`.

### EngineAnalysis
Normalized Stockfish observation for one immutable position and configuration: `EngineIdentity`, `EngineSettings`, `EngineLine[]`, `EngineStability`.

### EngineLine
Rank, first move, canonical score, WDL when available, PV, depth/seldepth and nodes. Engine score must use one canonical POV internally.

### MoveJudgement
Answers only **how good was this move according to the engine?** It contains move, rank, quality, best move, best/played score, cp/WDL loss where meaningful, result transition, forcedness and engine-stability reference. It contains no prose reason.

### Forcedness
Represents whether many equivalent moves exist or the position has a narrow/only move. Candidate inputs: best-to-second gap, count of acceptable moves, WDL/result-class transitions and mate preservation.

### BoardDelta
Mechanically derived before/after difference: attacks, defenses, material, piece safety, mobility, king safety, pawn structure, opened/closed files and diagonals. A delta is not yet an explanation.

### MoveEffect
Semantic interpretation of deltas. Candidate types: `AttackEffect`, `DefenseEffect`, `MaterialEffect`, `MobilityEffect`, `KingSafetyEffect`, `PawnStructureEffect`, `FileEffect`, `SquareControlEffect`, `MoveEnablingEffect`.

### TacticalMotif
Pattern independent of tactical soundness. Initial vocabulary: fork, pin, skewer, discovered attack, double attack, overload, removal of defender, deflection, decoy, interference, back-rank motif, mating net.

Lifecycle:

```text
DETECTED -> LEGAL -> VERIFIED
                 \-> REFUTED
```

### Threat
A concrete future consequence made available by a move: creating move, execution move/line, target, consequence and verification status.

### CounterfactualProbe
Controlled engine experiment. Initial types: `ALTERNATIVE_MOVE`, `BEST_RESPONSE`, `IGNORE_THREAT`, `TACTICAL_REFUTATION`, `DEFENSIVE_TEST`.

Every probe records base position, intervention, engine settings, result and conclusion.

### AlternativeMoveComparison
Compares chosen/played move with another serious candidate to answer what the better move uniquely achieves or what a mistake newly allows.

### Evidence
Provenance layer between analysis and language. Initial variants:
`BoardFactEvidence`, `EngineEvidence`, `VariationEvidence`, `CounterfactualEvidence`, `FeatureDeltaEvidence`, `MotifEvidence`; later `TablebaseEvidence`.

### ExplanationClaim
Smallest chess proposition allowed to reach commentary. Fields: claim id, structured subject, predicate, objects, confidence, evidence ids and importance.

Example:

```text
C1: Nf5 attacks the queen on d6.              [EXACT]
C2: Nf5 creates the threat Nxh6+.             [FORCED/VERIFIED]
C3: Ignoring the threat loses a pawn.         [ENGINE_VERIFIED]
C4: Re1 creates no equivalent forcing threat. [ENGINE_VERIFIED]
```

### ExplanationGraph
Connects claims with explicit relations: `CAUSES`, `ENABLES`, `PREVENTS`, `LEADS_TO`, `CONTRASTS_WITH`, `SUPPORTS`.

### ExplanationSelection
Chooses the minimal sufficient explanation. Initial intents: `WHY_GOOD`, `WHY_BAD`, `WHY_ONLY_MOVE`, `WHY_NOT_ALTERNATIVE`, `TACTICAL_EXPLANATION`. Positional explanation follows later.

### VerbalizationRequest
The LLM receives only a constrained projection: move/judgement summary, allowed claims and claim ids, optional verified variations and presentation style.

### VerbalizedCommentary
Final text plus used claim ids. A later validator rejects or repairs unsupported chess propositions.

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

- **PositionFactExtractor**: `PositionSnapshot -> PositionFacts`
- **BoardDeltaAnalyzer**: before facts + move + after facts -> `BoardDelta`
- **MoveJudge**: normalized engine analyses -> `MoveJudgement`
- **TacticalDetector**: board/delta -> candidate `TacticalMotif[]`
- **ThreatDetector**: effects/motifs/continuations -> candidate `Threat[]`
- **CounterfactualAnalyzer**: bounded engine interventions verifying causal hypotheses
- **EvidenceBuilder**: accepted analysis -> provenance-bearing evidence
- **ClaimBuilder**: eligible evidence -> structured claims
- **ClaimValidator**: claim/evidence compatibility and strict-commentary policy
- **ExplanationGraphBuilder**: explicit causal/contrastive graph
- **ExplanationSelector**: smallest sufficient set of claims
- **CommentaryValidator**: reject unsupported LLM-added chess propositions

## 8. Adapter responsibilities

### python-chess
FEN/PGN parsing, legal moves, SAN, reconstruction, attack/defense primitives and game-state rules. Translate to domain values at the boundary.

### Stockfish
UCI lifecycle, analysis budget, MultiPV, score/WDL normalization, PV conversion and engine metadata. Raw engine output must not leak upward.

### LLM
Serialize `VerbalizationRequest`, enforce output schema and return `VerbalizedCommentary`. Provider choice must not affect chess truth.

## 9. Application use cases

### analyze_move
Canonical MVP path:

```text
FEN + played move
 -> PositionSnapshot
 -> EngineAnalysis
 -> MoveJudgement
 -> deterministic effects
 -> bounded counterfactual verification
 -> evidence
 -> claims
 -> graph/selection
 -> optional commentary
```

### analyze_game
Iterates the canonical move pipeline over PGN and owns game-level budgeting, caching and explanation density. It must not reimplement move analysis.

## 10. Testing strategy

- **unit/**: domain invariants and deterministic services
- **integration/**: python-chess and real Stockfish normalization
- **golden/**: curated positions with expected and forbidden claims
- **adversarial/**: attempts to introduce unsupported commentary claims

The main correctness oracle is the set of evidence-backed chess claims, not exact prose.

## 11. Initial implementation sequence

1. Chess and engine value models.
2. python-chess adapter and immutable position identity.
3. Stockfish adapter + normalized `EngineAnalysis`.
4. `MoveJudgement` + forcedness.
5. `PositionFacts` + `BoardDelta`.
6. Tactical motifs, hanging pieces and direct threats.
7. Counterfactual probe infrastructure.
8. Evidence and `ExplanationClaim` contracts.
9. `ExplanationGraph` + minimal selection.
10. LLM verbalizer + commentary validator.
11. Positional feature expansion.
12. Syzygy/tablebase evidence.

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

The only canonical application facade is:

```text
CalliopeEngine
  ├─ analyze_move(AnalyzeMoveRequest) -> MoveAnalysisResult
  └─ analyze_game(AnalyzeGameRequest) -> GameAnalysisResult
```

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

- `STRUCTURED`: judgement + verified claims/evidence-facing views; no LLM required.
- `COMMENTARY`: structured result plus validated natural-language commentary.

The engine should always be capable of returning the structured result. Commentary is an
optional projection, not the canonical analysis.

### 13.3 Strictness

Default external-agent usage should be strict:

- unsupported claims are never surfaced;
- heuristic claims are excluded unless explicitly enabled;
- missing explanation is preferable to invented explanation;
- commentary failure must not invalidate the structured chess analysis.

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

`CalliopeEngine` owns the application-level composition of move/game use cases. The concrete
composition root will later create and share:

- python-chess adapter
- Stockfish process/pool
- analysis services
- bounded counterfactual executor
- evidence/claim pipeline
- optional LLM verbalizer

The public facade must remain independent of transport.

Long-lived hosts may keep one engine instance so Stockfish lifecycle and caches can be reused.
Per-request chess state remains immutable and request-scoped.

## 16. External tool design rule

Prefer small explicit operations over exposing arbitrary internal functions.

Initial tool surface:

```text
analyze_move(fen, move_uci, options?)
analyze_game(pgn, options?)
```

Future operations such as `explain_alternative` or `compare_moves` should still delegate into
the same engine and evidence pipeline rather than bypassing it.

Transport adapters may translate JSON to the public DTOs, but must not manufacture
`ExplanationClaim` values themselves.


## 17. MVP implementation baseline

The concrete staged MVP plan is maintained in
[`docs/mvp-implementation-plan.md`](mvp-implementation-plan.md).

The delivery sequence is:

```text
P0-P3   executable Stockfish judgement core
P4-P6   deterministic board facts/deltas and tactical candidates
P7-P9   counterfactual verification and causal explanation flows
P10-P11 evidence-backed claims and minimal explanation selection
P12     deterministic LLM-free commentary
P13     optional constrained LLM verbalization
G0      integrated golden/adversarial MVP gate
```

Two constraints override implementation convenience:

1. detector output never becomes an `ExplanationClaim` without eligible evidence;
2. inability to verify a reason is a valid result and must not be replaced by speculative prose.

The deterministic renderer precedes LLM integration so Calliope remains a complete chess-analysis
engine without model availability.
