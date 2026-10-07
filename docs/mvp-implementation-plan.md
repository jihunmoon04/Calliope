# Calliope MVP Implementation Plan

Status: **implementation baseline**

This document defines the staged implementation plan for the first Calliope MVP. It inherits the architectural invariants in `docs/architecture.md`.

## 1. MVP definition

The MVP is not merely a Stockfish wrapper. It is complete when Calliope can:

1. accept a FEN and played move;
2. judge the move with Stockfish;
3. derive concrete board/tactical explanation candidates;
4. verify causal claims where needed;
5. expose only evidence-backed claims;
6. render useful commentary without requiring an LLM;
7. optionally use an LLM only to verbalize already-verified claims.

Canonical flow:

```text
FEN + played move
 -> CalliopeEngine
 -> python-chess validation
 -> Stockfish judgement
 -> PositionFacts / BoardDelta
 -> tactical candidates
 -> counterfactual verification
 -> Evidence
 -> ExplanationClaim
 -> minimal selection
 -> deterministic commentary
 -> optional validated LLM verbalization
```

## 2. Global implementation rules

### 2.1 One public engine

External callers use only:

```text
CalliopeEngine.analyze_move(...)
CalliopeEngine.analyze_game(...)
```

Agent tools, skills, MCP, HTTP, CLI and Python integrations must not bypass the canonical pipeline.

### 2.2 Keep an executable vertical slice

Each packet leaves the repository in a coherent, testable state. New functionality extends the existing engine instead of creating a parallel analysis path.

### 2.3 Detector output is not explanation truth

```text
detected motif/effect != ExplanationClaim
```

A detector may propose a reason. A surfaced claim requires eligible evidence.

### 2.4 "Unable to explain" is a valid result

If Stockfish strongly prefers a move but the strict MVP analyzers cannot verify why, preserve the judgement and omit speculative causal claims. Missing explanation is preferable to invented explanation.

### 2.5 Deterministic commentary before LLM commentary

The engine must produce useful commentary with the LLM disabled. The LLM is an optional presentation layer.

### 2.6 Commentary failure does not invalidate analysis

If LLM verbalization fails or introduces unsupported content, preserve structured analysis and fall back to deterministic commentary.

## 3. Packet map

| Packet | Scope | Completion result |
| --- | --- | --- |
| MVP-P0 | python-chess boundary | validated positions and moves |
| MVP-P1 | Stockfish boundary | normalized `EngineAnalysis` |
| MVP-P2 | MoveJudge | engine-derived `MoveJudgement` |
| MVP-P3 | AnalyzeMove wiring | first executable Calliope slice |
| MVP-P4 | PositionFacts | deterministic board facts |
| MVP-P5 | BoardDelta | before/after semantic changes |
| MVP-P6 | TacticalDetector | tactical explanation candidates |
| MVP-P7 | Counterfactual core | controlled causal verification |
| MVP-P8 | Bad-move explanation | explain what a mistake newly allowed |
| MVP-P9 | Good/only-move explanation | contrast/refutation explanations |
| MVP-P10 | Evidence / Claims | hallucination-control contract |
| MVP-P11 | Explanation selection | minimal sufficient explanation |
| MVP-P12 | Deterministic renderer | useful LLM-free commentary |
| MVP-P13 | LLM verbalizer | optional natural-language polish |
| MVP-G0 | Integrated golden gate | MVP completion |

## 4. MVP-P0 — python-chess boundary

**Goal:** convert external FEN/UCI input into validated Calliope domain values without leaking mutable `python-chess.Board` objects into the domain.

Implement `PythonChessAdapter` for:

- FEN parsing and validation;
- `PositionSnapshot` construction;
- UCI parsing;
- legality checking;
- applying a legal move and producing the resulting snapshot;
- SAN derivation;
- board primitives later needed by fact extraction.

Gate:

- valid FEN -> correct snapshot;
- invalid FEN -> explicit error;
- legal UCI -> move + resulting position;
- illegal UCI -> explicit error;
- castling, en passant and promotion fixtures pass.

## 5. MVP-P1 — Stockfish boundary

**Goal:** normalize a Stockfish analysis into `EngineAnalysis`.

Canonical adapter operation:

```python
analyze(position, settings, root_moves=None) -> EngineAnalysis
```

The same operation supports normal MultiPV, played-move forced analysis and later counterfactual probes.

Implement:

- UCI process lifecycle;
- depth / nodes / time limits;
- MultiPV;
- `root_moves`;
- PV conversion;
- White-POV score normalization;
- explicit mate normalization;
- WDL normalization;
- engine identity/settings metadata.

Gate:

- starting position;
- MultiPV >= 5;
- Black-to-move score orientation;
- forced mate;
- `root_moves=[played_move]`;
- explicit engine failure handling.

## 6. MVP-P2 — MoveJudge

**Goal:** derive move quality from Stockfish observations only.

Initial quality vocabulary:

- `BEST`
- `GOOD`
- `INACCURACY`
- `MISTAKE`
- `BLUNDER`

Initial forcedness vocabulary:

- `MANY_EQUIVALENT`
- `FLEXIBLE`
- `NARROW`
- `ONLY_MOVE`

Judgement may consider:

- centipawn loss;
- WDL / expected-score loss;
- mate gained/lost;
- result-class transitions;
- best-to-alternative gap.

Thresholds belong in a replaceable judgement policy, not hard-coded value objects.

Gate fixtures cover best move, near-equivalent move, inaccuracy, mistake/blunder, mate loss, only move and several near-equal top moves.

## 7. MVP-P3 — first executable AnalyzeMove slice

**Goal:** make `CalliopeEngine.analyze_move()` work end-to-end for judgement.

```text
FEN + move
 -> python-chess validation
 -> Stockfish
 -> MoveJudge
 -> MoveAnalysisResult
```

Claims may still be empty.

Gate: a real analyze-move request returns a structured judgement with no LLM dependency.

## 8. MVP-P4 — PositionFacts

**Goal:** extract deterministic chess facts needed for initial explanations.

Initial scope:

- piece locations;
- material;
- attackers;
- defenders;
- check/checkmate state;
- legal captures;
- basic piece safety / hanging status.

Broad strategic scoring is deferred.

Gate: curated positions have exact expected facts independent of Stockfish.

## 9. MVP-P5 — BoardDelta

**Goal:** answer: **what changed because of the played move?**

Initial effect vocabulary:

- `NEW_ATTACK`
- `REMOVED_ATTACK`
- `NEW_DEFENSE`
- `REMOVED_DEFENSE`
- `MATERIAL_GAIN`
- `MATERIAL_LOSS`
- `PIECE_BECAME_HANGING`
- `PIECE_BECAME_SAFE`
- `CHECK_CREATED`
- `CHECK_REMOVED`
- `LEGAL_CAPTURE_ENABLED`
- `LEGAL_CAPTURE_DISABLED`

Prefer one compact `MoveEffect` structure with a `kind` enum over a deep class hierarchy.

Gate: hand-checked before/after fixtures match exactly. BoardDelta remains deterministic and engine-independent.

## 10. MVP-P6 — TacticalDetector

**Goal:** generate tactical explanation candidates, not final claims.

Initial supported motifs/effects:

- check;
- checkmate;
- hanging piece;
- double attack;
- fork;
- pin;
- removal of defender;
- direct threat;
- forced response.

Lifecycle:

```text
DETECTED -> VERIFIED
         -> REFUTED
```

Geometry alone is insufficient for `VERIFIED`.

Gate: each motif family includes positive, negative and false-positive fixtures.

## 11. MVP-P7 — Counterfactual core

**Goal:** provide reusable controlled verification of causal explanation candidates.

Initial probe kinds:

- `BEST_RESPONSE`
- `IGNORE_THREAT`
- `ALTERNATIVE_MOVE`
- `REFUTATION`

Each probe binds:

- immutable base position;
- intervention;
- probe kind;
- exact engine settings/budget;
- engine result;
- conclusion.

Probe results must never be reused across a different position or incompatible engine configuration.

## 12. MVP-P8 — bad-move explanation

**Goal:** answer: **What did this move newly allow?**

Canonical design: [`mvp-p8-bad-move-design.md`](mvp-p8-bad-move-design.md).

Algorithm:

```text
played mistake/blunder
 -> compare with engine-best alternative
 -> opponent best punishment after the played move
 -> identify concrete consequence
 -> replay the same punishment after the comparator when legal
 -> normalize piece identity back to the common base position
 -> inspect BoardDelta / tactical candidates on both branches
 -> verify bounded causal contrast
 -> internal explanation evidence for P10
```

Primary fixtures:

- newly hanging piece;
- removed defender;
- fork allowed;
- mate allowed;
- material-loss line.

A single PV is not sufficient to label material loss as mathematically forced. Stronger
`FORCED` wording belongs to the later evidence/claim rules.

P8 remains internal: it does not change the public DTOs, render prose, or create
`ExplanationClaim` objects.

## 13. MVP-P9 — good-move and only-move explanation

Good-move question:

> What does this move achieve that serious alternatives do not?

Flow:

```text
best/strong move
 -> compare top alternatives
 -> identify differing effects/threats
 -> verify best response
 -> run ignored-threat probe when meaningful
 -> retain unique verified benefit
```

Only-move question:

> Why do representative alternatives fail?

Flow:

```text
best move
 -> detect evaluation/result cliff
 -> inspect second/third serious alternatives
 -> verify compact refutations
 -> identify what the best move uniquely preserves
```

The MVP does not need to explain every legal alternative.

## 14. MVP-P10 — Evidence and ExplanationClaim

**Goal:** create the hard boundary between analysis and language.

Initial evidence variants:

- `BoardFactEvidence`
- `EngineEvidence`
- `VariationEvidence`
- `CounterfactualEvidence`
- `MotifEvidence`

Initial strict claim confidence:

- `EXACT`
- `FORCED`
- `ENGINE_VERIFIED`

`HEURISTIC` remains excluded from strict MVP commentary.

Claim/evidence compatibility examples:

```text
EXACT
 -> board/rule evidence required

FORCED
 -> verified variation evidence required

ENGINE_VERIFIED
 -> engine/counterfactual evidence required
```

No eligible evidence -> no claim.

## 15. MVP-P11 — Explanation graph and minimal selection

**Goal:** turn verified claims into a compact causal explanation.

Initial relations:

- `ENABLES`
- `PREVENTS`
- `LEADS_TO`
- `CAUSES`
- `CONTRASTS_WITH`
- `SUPPORTS`

No graph database is required; claim and relation lists are enough.

Prefer the minimal sufficient explanation, usually 1-3 primary claims.

General priority:

1. checkmate / forced mate;
2. forced major material consequence;
3. sound tactical motif;
4. forced response;
5. direct verified threat;
6. lower-value board effects.

## 16. MVP-P12 — deterministic renderer

**Goal:** produce useful human commentary with no LLM.

The renderer operates from selected claim types and relations. It does not re-analyze the position.

Gate:

- deterministic output for golden claims;
- no chess proposition absent from selected claims;
- structured result remains primary.

At this point Calliope is already a functional evidence-first commentary engine.

## 17. MVP-P13 — optional LLM verbalizer

**Goal:** improve fluency without granting the model chess authority.

Input is restricted to:

- judgement summary;
- selected verified claims;
- claim ids;
- verified variations when needed;
- presentation/style settings.

Output:

- commentary text;
- used claim ids.

Failure policy:

```text
valid LLM output -> use it
LLM unavailable -> deterministic commentary
unsupported content -> reject and fall back
```

## 18. MVP-G0 — integrated golden gate

MVP completion requires real python-chess + Stockfish integration and structured/deterministic commentary paths.

Required fixture classes include:

1. queen/piece hanging blunder;
2. fork allowed;
3. removal-of-defender tactic;
4. forced mate allowed;
5. mate missed;
6. only move;
7. several equivalent best moves;
8. strong forcing best move;
9. verified threat where ignoring it loses material;
10. quiet positional best move that strict MVP cannot explain.

Fixture 10 is mandatory: Calliope must preserve the engine judgement while declining to invent a reason.

Pass conditions:

- judgement matches configured Stockfish policy;
- every surfaced chess claim has eligible evidence;
- detector-only hypotheses never reach commentary;
- false-positive tactical fixtures are suppressed;
- only-move/equivalent-move language is not overstated;
- deterministic renderer works with LLM disabled;
- LLM failure/rejection preserves structured result;
- public invocation still goes through `CalliopeEngine`;
- no speculative player-intent statement is emitted.

## 19. Test organization

```text
tests/
  unit/
    domain/
    judgement/
    facts/
    tactics/
    explanation/

  integration/
    python_chess/
    stockfish/

  golden/
    mistakes/
    best_moves/
    only_moves/
    tactical/

  adversarial/
    false_motif/
    unsupported_claim/
    llm_hallucination/
```

The primary oracle is the set of allowed and forbidden claims, not byte-identical prose.

## 20. MVP scope boundary

Included:

- FEN + played-move analysis;
- Stockfish judgement;
- MultiPV / played-move forced evaluation;
- basic board facts/deltas;
- concrete tactical motifs;
- counterfactual verification;
- evidence-backed claims;
- deterministic commentary;
- optional constrained LLM commentary;
- single-engine integration surface.

Deferred until after MVP:

- deep positional strategy;
- generalized prophylaxis;
- long maneuver explanations;
- opening-theory narratives;
- player intent/style;
- broad pawn-structure strategic ontology;
- Syzygy/tablebase explanation;
- UI;
- arbitrary external-agent reasoning bypasses.

## 21. Immediate implementation tranche

The first implementation tranche is:

```text
MVP-P0  PythonChessAdapter
MVP-P1  StockfishAdapter
MVP-P2  MoveJudge
MVP-P3  AnalyzeMove wiring
```

Completion criterion:

```text
FEN + move
 -> CalliopeEngine
 -> validated position/move
 -> Stockfish judgement
 -> MoveAnalysisResult
```

Only after this vertical slice is proven should the "why" engine begin with P4.
