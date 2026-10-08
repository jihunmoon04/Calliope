# MVP-G0 Closure — Deterministic MVP Baseline

Status: **CLOSED**

Baseline:

```text
main @ d49d60a90388d7acd48d9bf1eaf4035518c9b8e1
```

This document closes the deterministic Calliope MVP after G0 application integration.

No production behavior is changed by this closure packet.

---

## 1. Closed scope

The following delivery chain is complete on the baseline above:

```text
P0-P3   public Stockfish judgement core
P4-P6   deterministic position facts, deltas and tactical candidates
P7-P9   bounded counterfactual verification and strict move-explanation families
P10     evidence-backed claims
P11     explanation graph + deterministic minimal selection
P12     deterministic LLM-free commentary
G0      public schema 0.2 application integration + integrated real golden gate
```

P13 is not part of the deterministic closure.

P13 remains an optional post-MVP verbalization layer.

---

## 2. Canonical public path

The closed production path is:

```text
AnalyzeMoveRequest
  -> CalliopeEngine.analyze_move()
  -> AnalyzeMoveService
  -> Stockfish judgement
  -> P4-P9 strict analysis
  -> P10 validated evidence/claims
  -> P11 graph + selection
  -> optional P12 deterministic renderer
  -> schema 0.2 MoveAnalysisResult
```

There is no alternate public explanation path.

Internal explanation services are not public facade methods.

---

## 3. Public contract baseline

`PUBLIC_SCHEMA_VERSION == "0.2"`.

The public move result preserves:

- engine judgement;
- all validated P10 claims;
- explicit claim confidence;
- explicit claim scope;
- typed move/piece/side entities;
- move position frames;
- base-piece identity/presentation frames;
- P11 `selected_claim_ids` separately from the full claim tuple;
- deterministic P12 sentence-level provenance in COMMENTARY mode.

Current presentation modes:

### STRUCTURED

```text
P0-P11
commentary = None
```

### COMMENTARY

```text
same P0-P11
+ P12
```

The output mode does not own chess truth.

Only exact `OutputMode` enum members are accepted at runtime.
Plain strings such as `"structured"` and `"commentary"` fail closed before chess/engine work.

---

## 4. Strict explanation boundary

Current strict explanation families are owned only by frozen P8/P9 semantics.

Routing:

```text
MISTAKE, BLUNDER          -> P8
BEST, EXCELLENT, GOOD    -> P9
INACCURACY               -> valid strict silence
```

Detector-only hypotheses never become public claims.

A routed P8/P9 `NOT_APPLICABLE` outcome is an internal inconsistency, not silence.

Valid silence is represented by an empty P10 package that still passes through P11.

COMMENTARY then renders:

```text
No verified explanation is available.
```

No generic reason is invented.

---

## 5. P10-P12 trust chain

The closed trust chain is:

```text
P8/P9 result
 -> EvidenceBuilder
 -> ClaimBuilder
 -> ClaimValidator
 -> GraphBuilder
 -> ExplanationSelector
 -> ExplanationSelectionValidator
 -> optional DeterministicExplanationRenderer
```

Application code may not bypass these validators merely because it created the objects.

P12 is presentation-only and runs after the request-wide engine session is released.

---

## 6. Engine reproducibility and concurrency baseline

One `CalliopeEngine` owns one Stockfish process.

The public request path uses request-wide engine sessions:

```text
validate public input
parse/canonicalize chess input

acquire request-wide Stockfish session
  fresh game token
  judgement analyses
  all P7 probes
  P11 closure
release session

optional P12
public projection
```

Guarantees:

- one shared Stockfish process;
- concurrent public requests cannot interleave engine calls on that process;
- every request receives a fresh game token;
- all engine calls in one request use that token;
- no mid-request new-game/reset;
- exceptions release the request lock;
- invalid input does not acquire/reset the engine session;
- P12 performs no engine/P7 work.

Judgement fixed non-budget options:

```text
threads = 1
hash_mb = 16
```

Frozen P7 profile:

```text
depth = 12
time_ms = 2000
multipv = 1
threads = 1
hash_mb = 16
```

The time limit is a safety cap. Reproducibility goldens qualify only when relevant non-terminal
engine lines actually reach depth 12.

Arbitrary wall-clock public budgets are semantically validated but are not promised to be
byte-identical across independent runs.

---

## 7. Real integrated acceptance classes

The G0 public-path real Stockfish acceptance includes:

1. hanging-piece / material-loss blunder;
2. fork allowed;
3. removal-of-defender claim retained publicly;
4. exact immediate mate allowed;
5. engine-verified mating line;
6. exact forced response;
7. representative only-move preservation;
8. equivalent alternatives -> strict silence;
9. tested-response material threat;
10. tested-response mate threat;
11. quiet BEST -> strict silence;
12. INACCURACY -> strict silence;
13. STRUCTURED / COMMENTARY semantic parity;
14. request-session/concurrency isolation;
15. fresh-process reproducibility subset.

The real public gate uses `CalliopeEngine.analyze_move()`, not direct P8-P12 helper invocation.

---

## 8. Test evidence at closure preparation

Implementation acceptance reported at pre-B1 G0 head:

```text
TARGETED_TESTS:       163 passed
P8_P12_REGRESSION:   2401 passed
REAL_G0_TESTS:         46 passed
integration total:    101 passed / 0 skipped
FULL_PYTEST:          2694 passed / 0 skipped
```

After the B1 exact-`OutputMode` correction, the implementation reported:

```text
output-mode targeted:   9 passed
test_analyze_move.py:  38 passed
related application/composition/facade: 90 passed
Ruff changed files: PASS
format changed files: PASS
```

The B1 correction changed only:

- `src/calliope/application/analyze_move.py`;
- `tests/unit/application/test_analyze_move.py`.

The independent B1 review found no remaining blocker.

Final closure rerun on the source-equivalent closure HEAD reported:

```text
FULL_PYTEST:                 2700 passed / 0 failed / 0 skipped
REAL_STOCKFISH_INTEGRATION:  101 passed
REAL_G0_PUBLIC_GATE:          46 passed
REAL_STOCKFISH_SKIP_COUNT:     0
Stockfish:                    19
```

There is no GitHub CI status/workflow run attached to the closure baseline SHA; the closure gate
above was executed directly by the independent reviewer against the exact source-equivalent
closure tree.

A docs-only closure branch may use the source tree from that baseline; documentation changes do
not require a second semantic implementation review.

---

## 9. Architecture status after closure

The deterministic MVP is now an implemented baseline, not an initial design sketch.

The following are no longer "future" components:

- shared PythonChess adapter;
- shared Stockfish process;
- request-wide Stockfish session serialization;
- judgement application wiring;
- P4-P12 deterministic explanation pipeline;
- evidence/claim/selection projection;
- deterministic COMMENTARY mode.

The optional LLM verbalizer remains future work.

---

## 10. Explicitly deferred

Closure does not add:

- P13 constrained LLM verbalization;
- LLM commentary validation/fallback;
- heuristic public claims;
- a dedicated `MISSED_MATE` claim family;
- deep positional strategy;
- long-horizon strategic plans;
- player-intent inference;
- opening narrative;
- tablebase explanation;
- UI;
- arbitrary internal-service access for external callers;
- PGN/game analysis: `CalliopeEngine.analyze_game()` is currently wired to
  `AnalyzeGameUnavailable` and raises `FeatureUnavailableError`.

These are post-closure work and must not be inferred from the deterministic MVP baseline.

---

## 11. Known deterministic-MVP limitation

The G0 closure records one pre-existing P2/MoveJudge limitation for follow-up.

The judgement path compares the base MultiPV observation with a separately forced played-move
observation. If the separately analyzed played move appears better than the base observation's
best/candidate score by more than the current 20 cp noise tolerance, `MoveJudge` fails closed
with `IncompatibleAnalysisError` rather than reconciling the two observations.

A known reproducible position is:

```text
FEN:  r1b2rk1/pp3p1p/3n2p1/3BR3/5QP1/P4N1P/1q4PK/3R4 w - - 1 26
move: f4h6
```

This behavior predates G0 and does not invalidate the evidence/claim pipeline, but it means the
closed deterministic MVP is not guaranteed to return a result for every otherwise legal move.
A later stabilization packet may review cross-observation engine stability/reconciliation without
changing P8-P12 semantics.

---

## 12. P13 boundary

P13, if implemented, must be downstream of already validated semantics.

It may consume only the frozen trusted projection needed for verbalization.

It must not:

- become a chess authority;
- create new unsupported chess propositions;
- bypass P10/P11;
- change judgement;
- change claim confidence or scope;
- change selected claim identity;
- require a second Stockfish reasoning path.

A future P13 failure/rejection policy should preserve P12 as the deterministic fallback.

P13 requires its own design review before implementation.

---

## 13. Closure invariants

The deterministic MVP closure is valid only while all of the following remain true:

1. `CalliopeEngine.analyze_move()` is the canonical public move path.
2. Stockfish owns move-quality observations.
3. strict commentary contains only validated P10 claims selected by P11.
4. P12 does not discover chess truth.
5. missing verified explanation remains a valid result.
6. public claim scope/frame semantics are not discarded.
7. detector-only hypotheses do not leak into claims.
8. request mode cannot change P0-P11 semantics.
9. one shared Stockfish process remains request-isolated.
10. external callers cannot bypass the application trust chain through the public facade.

A later phase that intentionally changes one of these must explicitly reopen the relevant
architecture contract.

---

## 14. Final closure review gate

The independent reviewer must verify:

- baseline/source correspondence;
- closure branch is docs-only;
- architecture and roadmap agree with current source;
- schema 0.2 public contract matches production;
- P8/P9 routing matches frozen eligibility;
- P10/P11 validation remains mandatory;
- P12 remains deterministic/presentation-only;
- request-wide engine serialization matches production;
- P7 profile matches production;
- no P13/LLM production dependency exists;
- deferred features are not accidentally claimed complete;
- full pytest passes on the baseline/source-equivalent closure head;
- real Stockfish tests are not skipped;
- changed docs introduce no source/test delta.

Final successful state:

```text
G0_DETERMINISTIC_MVP_CLOSURE:
CLOSED
```

After that, the next optional roadmap item is P13 design.
