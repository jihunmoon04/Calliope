# Calliope observation-to-commentary bridge — A0 design draft

Status: **DRAFT / AWAITING INDEPENDENT DESIGN REVIEW** (not frozen, not implemented)  
Date: 2026-10-08 (Asia/Seoul and Asia/Tokyo)  
Reviewed source baseline: `main @ 96c49abd46e664dceed6cb270c06c3d6ade62b70`  
Owner: post-G0 MVP-to-analysis integration design  
Prerequisites: G0 + P2-C1 CLOSED; positional_v1 / activity_v1 independently READY; scenario A1/A3 READY, merged as PRs #29/#30.

This is a design-only proposal. No code, tests, public schema, runtime behavior, or canonical MVP claim rules change in this PR. A separate independent design review is required before implementation.

## 1. Problem and existing authority

The production `CalliopeEngine.analyze_move()` path in `src/calliope/composition.py` wires P0–P12, not the new `PositionAnalyzer`, `TransitionAnalyzer`, `ActivityAnalyzer`, `ActivityTransitionAnalyzer`, `ActivityLineAnalyzer` or `ScenarioLineAnalyzer`.

`AnalyzeMoveService.execute()` performs judgement and P8/P9 verification inside one Stockfish request session, then validates P10/P11 and optionally renders P12. Its strict `CommentaryView` has exactly one sentence per selected claim ID. `MoveExplanationPipeline` can build P10 packages only from the closed P8/P9 families. P10's evidence-family and predicate whitelist and P11's closed selection-family/priority mappings do not accept positional/scenario observations.

New internal position/activity/line services **observe** structural facts and changes, not their benefit. The EXCHANGE scenario takes a legal supplied line and a square target; it does **not** discover an optimal line, prove that recaptures are forced, judge compensation, or assert that a trade is settled. Its current renderer can already produce provenance-linked English fact sentences, but those sentences are not P12 explanation claims.

The product gap is therefore **observation selection and safe presentation**, followed by a separately reviewed **explanatory hypothesis verification** step. It is not primarily a lack of future-line traversal.

## 2. Non-negotiable boundaries

1. **Judgement authority:** Stockfish/MoveJudge exclusively determine move quality. A changed file, attack count, legal destination count or provided PV is never evidence of positional advantage on its own.
2. **Three epistemic levels:** (O) exact observations of a specific position/supplied line; (C) factual contrasts between explicitly aligned, independently validated lines; (H) checked explanatory hypotheses with explicit refutation/comparator contracts. O and C may not be promoted to H by prose.
3. **Claim boundary:** no `ScenarioSummary`, `ActivityTransitionAnalysis`, feature count or rendered scenario sentence can directly become a P10 `ExplanationClaim`. Do not dilute existing P10 validator or reuse existing predicates with wider semantics. A later packet may extend P10 only with individually frozen evidence forms, predicates, scopes and independent validation.
4. **Existing public contract stays intact initially:** `AnalysisOptions`, `AnalyzeMoveRequest`, `MoveAnalysisResult`, `CommentaryView`, `PUBLIC_SCHEMA_VERSION == "0.2"`, P8–P12 rendering and fallback/exception behavior remain unchanged through internal packets I1/I2. No extra fields hidden in `metadata`.
5. **Identity and provenance:** one immutable base `position_id`, exact UCI anchored to the position where legal, physical `BasePieceRef` across captures/promotions/castling, frame/step indices and resolvable typed source references. No SAN or descriptive strings as identity.
6. **Observation is not advantage:** never infer "good", "bad", "improved", "winning", "safe", "forced", "dominates", "strong attack", "compensation" or strategic intent from observational contracts. "The rook has 11 geometric attack squares" is not a mobility-quality claim.
7. **No silent trust:** do not disable `validate_scenario_summary`, observation correspondence validation or P11 validation to save time. Reject broken source refs, partial board-state correspondence, wrong base, illegal PVs, and mismatched track history; no optimistic rendering.
8. **No engine-session expansion:** observation and factual rendering must add zero Stockfish analyses and no calls to the engine session port. If later B2 adds verified probes, they must use the reviewed request-wide session policy and explicit cost budgets; do not re-open/ad-hoc bypass a session.
9. **Fail closed:** unsupported fact/claim kinds or invalid records raise typed failures. An absence of *eligible* explanatory facts may yield an empty observational section, but a corrupted record is never silently dropped.
10. **No LLM authority:** future optional P13 only rephrases already verified rendered semantics.

## 3. Exact pipeline separation

```text
        existing AnalyzeMoveRequest(FEN, move)
                          |
           existing MoveJudge + P8/P9
                          |
              P10 -> P11 -> P12
                          |                   (UNCHANGED v0.2)
                          +--------------------------+
                                                     |
         observation-only, separately reviewed seam |
                          |                          |
   before position + canonical played move         |
                          v                          |
       positional/activity one-ply observations     |
                          |                          |
             typed ObservedFinding[]                |
                          v                          |
           provenance/anchor validator              |
                          v                          |
         deterministic relevance/selection          |
                          v                          |
     optional OBSERVATION sentences (not P10 claims) |
                          |                          |
                future opt-in v0.3 projection <-------+
```

There must be **one public `CalliopeEngine` facade**, not two engines. The first I1/I2 implementation is deliberately internal; public method/option choice and v0.3 DTO must be explicitly frozen at the later public-integration gate. No extra public endpoint or method is authorized by this draft.

## 4. I1 — played-move observation packet (internal)

### Source acquisition

Use existing `TransitionAnalyzer.analyze(before, move)` and (where useful) `ActivityTransitionAnalyzer.analyze(before, move)`. Both validate the legal move and reconcile position/identity. Reuse the same PythonChessAdapter, PositionFactExtractor and BoardDeltaAnalyzer instances from the composition root in a later wiring packet; do not create a competing chess rules implementation.

Start with exact, low-cost feature families supported by `positional_v1`/`activity_v1`:

| Finding family | Allowed meaning | Specifically forbidden inference |
| --- | --- | --- |
| PAWN_STRUCTURE_DELTA | isolated/doubled/passed/supporter flags differ across before/after | pawn is good, supported recapture is legal, promotion is inevitable |
| FILE_STATE_DELTA | open/semi-open/closed file category changed | rook controls or benefits from the file |
| PIECE_RELOCATION / PHYSICAL_CAPTURE | validated piece identity, source/destination and capture/EP/promotion | resulting position is favorable |
| GEOMETRIC_ACTIVITY_DELTA | changed attack footprint/rays/obstructions; accurate side-to-move qualifiers | attack equals legal capture, more squares means stronger move |
| LEGAL_ACTION_DELTA | current-side legal actions on a given observed frame | opponent has zero replies, a destination is tactically safe |

No generic positional score or unbounded "important fact" metric is introduced. If a finding cannot be stated using a closed observational predicate and complete source anchors, omit it as an *ineligible candidate*, not as a fabricated claim.

### Proposed internal data contract (review before freezing)

`ObservedFinding` is a separate immutable type; it is **not** an `ExplanationClaim`. It owns an exact finding kind, base `position_id`, canonical move and frame/subject identity, typed before/after payload, provenance references, and explicit `scope=PLAYED_TRANSITION`. IDs are deterministic per observation request. Observation confidence is not P10 confidence; either provenance is exactly validated or the record is invalid.

Provider-neutral, localized wording must be downstream of this typed contract, not mixed into fact selection. Do not reuse `ClaimView` or `CommentaryView.used_claim_ids` for observations.

### I1 acceptance

- Identical factual output for equivalent canonical UCI/SAN display metadata; invalid UCI/move rejected.
- Golden mirror/color checks for pawn flags and file changes; same physical piece through promotion; EP victim vs landing; castling king/rook correspondence.
- Geometric attackers do not imply legal captures; opponent off-turn legal action is "not observed", not zero.
- Recomputed source validation defeats swapped positions, wrong frame refs, mutated feature values and altered subject identity.
- No P8–P12 production-source changes, no public v0.2 changes, and zero added engine calls. Differential tests compare pre/post `analyze_move` v0.2 responses on representative cases including empty-claim cases.

## 5. I2 — supplied-line scenario observation packet (internal)

EXCHANGE is the **only** current scenario kind; do not pretend that pawn advance, king safety, piece improvement or space-gain scenario policies already exist.

A separate internal request may supply `ScenarioRequest(EXCHANGE, SquareTarget(focus), initial, supplied_line, max_plies)` and use the existing `ScenarioLineAnalyzer`/renderer. Require complete supplied-line legality, max-plies checks and validator provenance. Distinguish user-supplied, Stockfish-PV and test-fixture provenance as **source metadata**, not different evidentiary strengths.

The first I2 acceptance is **explicit line + explicit focus only**. A later automatic dispatcher may choose from played move/verified PV **only after** it defines: initial position and root alignment; `focus_square` selection including EP victim/landing; PV legality and truncation policy; no assumed forcedness; bounded depth/length; a duplicate-selection policy. A PV whose first move is not the requested played move cannot be described as that move's continuation. Do not auto-run EXCHANGE just because a capture appears in an unverified line.

Do not unconditionally render `RenderedScenarioReport.detail` into a user answer. It can have thousands of sentences. Keep exact full summaries internal; select a small number of anchored digest observations with a reviewed family cap and wording whitelist.

### I2 acceptance

- EXCHANGE E01–E15 golden factual and forbidden-language cases retained, including promotion digest, mirrors, EP focus-victim context, pin transient track, rook-only and king-only castling.
- Exact source refs resolve and output predicates stay observational.
- Illegal, root-mismatched, excessive, or falsely labelled PV fails closed.
- 0/1/8/16/64/256-ply stress and cost smoke separated into replay/selection/validation/render phases; no performance shortcut skips complete integrity validation.
- Regression verifies **zero extra Stockfish analyses**.

## 6. Observation narrative selection (I2 or separate I2-S)

Observed facts are plentiful; "truth" alone does not justify explaining them. Use a deterministic, closed candidate/selection policy. It must not depend on an LLM-generated importance score or hidden heuristic claims.

Proposal for first iteration:

1. Candidate must be a verified before/after **change** or a directly relevant EXCHANGE event; suppress unchanged contextual trivia.
2. Bind every candidate to the requested move/subject/frame or explicitly labelled supplied line; deduplicate by semantic identity and physical-piece subject.
3. Prefer one persistent structural change over repeated frame-local restatements; if a temporary change is chosen, state its finite scope and return-to-original condition.
4. Use a small, deterministic output cap (proposed **two** observation sentences per move; not a two-claim P11 limit), stable family tie-breaking and a "no eligible observation" empty result.
5. No causal link to Stockfish judgement, no "because", "therefore better", untested uniqueness, compensation or improvement wording.
6. Preserve per-sentence source provenance/observation IDs and allow identical summary recomputation to validate selection.

Review must freeze exact candidate-family ranking and tied-case goldens before implementation. Selection of observations is **not** P11 Claim selection; P11's existing max-three-Claim ranking remains unchanged.

## 7. Public exposure is a distinct opt-in integration gate

I1/I2 are internal modules. To expose observational prose alongside existing P12, approve a separate, explicit public contract rather than altering v0.2 in place:

- propose `schema 0.3` (or a separately versioned enriched result, subject to design review);
- maintain stable judgement, P10 ClaimView, selected_claim_ids and P12 sentence/claim-id invariants;
- add a separately typed `observation_summary` with observation IDs and source-linked sentences, not merged into P12 `CommentaryView` without a new reviewed contract;
- require explicit opt-in/version negotiation so existing `analyze_move` consumers still receive unchanged schema 0.2 and deterministic text;
- document anchor/line scope as `played_transition` or `supplied_line`; no causal confidence;
- pin serialization, failure semantics and request budgets. No arbitrary `metadata` field for a new observable result;
- implement an end-to-end public golden gate with a real Stockfish binary and before/after compatibility oracle.

The method/option/DTO exact names and migration mechanism are **OPEN** until this separate API review. No default output changes authorized now.

## 8. B1 — comparable supplied lines (future, separately reviewed)

For two lines: validate the **same initial full PositionSnapshot**, explicit line-root pairing and a shared target/physical subject; independently replay both lines. Align measured phenomena by declared frame rule (same ply, supplied endpoint, or per-line event), not by naively comparing unrelated final positions. Compare observational differences only. Candidate "the improvement occurs only in line A" needs full membership checks; a PV score difference does not prove the cause.

Never reuse one line's physical `BasePieceRef` as another frame-local occupancy without independently resolving physical identity. Missing PVs, depth differences, truncated lines, and incompatible endpoints require explicit omission/noncomparability rather than invented equalities.

## 9. B2 — verified positional explanations (future, separately reviewed)

Implement narrow hypothesis templates, each with an explicit **support and refutation oracle**. Suggested first family: `OPEN_FILE_ACCESS`, not generic "positional improvement".

Example:
- O: the played move changes the d-file to open, anchored in two actual states;
- H: this creates a *usable* rook access opportunity absent in selected alternatives;
- necessary observations: relevant physical rook, admissible occupancy/path facts, legal actions at explicitly specified frames; **geometric ray alone is insufficient**;
- counterfactual protocol: define comparator line(s), response set, fixed P7 settings, retained result scope, stop/failure conditions, result stability and contradiction behavior;
- verdicts: `SUPPORTED`, `REFUTED`, `INCONCLUSIVE` as *internal hypothesis outcomes*; inconclusive never enters causal prose;
- when and only when reviewed conditions are satisfied, design a NEW P10 evidence family + `ClaimPredicate` / `ClaimScope`, extend ClaimBuilder/ClaimValidator, P11 priority/family map and P12 template simultaneously.

Always avoid the invalid inference "Stockfish likes this move and a file opened, therefore opening the file caused the advantage." Compare a controlled structural mechanism and restrict scope to the actual tested continuations; do not claim global best play or long-term plans unless proved by a stronger protocol.

The first B2 family and P10 eligibility must pass independent rule-specific counterexamples **before** adding many scenario kinds.

## 10. Performance, semantics and failure contracts

PR #30's recorded scenario smoke (Windows Python 3.12.14) reports for a 256-ply non-capture line approximately **2,748.5 ms projection** and **2,952.3 ms render**, excluding replay. These are separate timings, not a single-product latency SLA. Its long detailed sentence output is unsuitable for unconditional per-move public rendering.

- I1 should use one-ply extraction without a 256-ply scenario analysis.
- I2 should be explicitly requested and bounded. Proposed product default for automatic, future PV observation: **at most 8 plies**; reviewed per-request knobs and absolute limits must precede shipping.
- Benchmark cold/warm replay, structural activity, fact selection, integrity recomputation and compact rendering **separately** on typical and adversarial positions.
- Establish measured latency and output-size gates before public integration; do not declare a speed budget met from the existing smoke.
- Preserve explicit typed errors for malformed requests, observation incompatibility, unverifiable hypothesis and renderer provenance failures.
- If a feature is opt-in, disabling it must leave existing judgement + P8–P12 untouched.
- Do not add external model, database, caching or background jobs in these packets.

## 11. Delivery order and review gates

| Packet | Deliverable | Public delta | Entry/exit |
| --- | --- | --- | --- |
| A0 (this PR) | Design/seams, candidate classes, boundaries, adversarial corpus plan | None | independent design review READY required |
| I1 | One-ply `ObservedFinding` producer + validator + goldens | None | reviewed implementation, no extra engine call, v0.2 unchanged |
| I2 | Explicit EXCHANGE request reuse + compact observation selector/renderer | None | reviewed complete provenance + cost/golden tests |
| I3 | Optional public observation projection and versioned API contract | Explicit reviewed opt-in only | schema compatibility and real-Stockfish gate |
| B1 | Paired supplied-line factual comparison | not presumed | independent comparator/alignment review |
| B2 | One typed causal positional hypothesis and P7 proof/refutation | not presumed | explicit P10/P11/P12 semantic review |
| C | Merge verified positional explanation into primary claim selection | reviewed v0.3+ | adversarial/mutation + backward compatibility |
| P13 | Optional LLM realization of validated content | not presumed | strict semantic validation and deterministic fallback |

The ordering of I3 vs B1/B2 is a product decision: I3 can deliver **observational** commentary early without pretending verified causal quality explanations exist. P13 is not a prerequisite.

## 12. Independent-review questions / STOP conditions

Reviewers must explicitly verify:

1. Is any observational output capable of masquerading as a v0.2 P10 claim or a quality explanation?
2. Can I1 be wired without changing engine session scope, judgement/P8–P12 behavior or constructing duplicate rules/engine instances?
3. Are `ObservedFinding` semantic identity, physical identity, source-ref types and recomputation/validator ownership precise enough to freeze in I1?
4. Does the I2 EXCHANGE dispatcher accidentally infer target, forced recapture, PV alignment, score causality or line completion?
5. Are selection caps and suppressions objectively testable and capable of avoiding 1,800+ sentence dumps?
6. Can an enriched output be exposed without breaking the schema-0.2 `used_claim_ids` invariant or existing clients?
7. Are the B1 comparator equivalence/line alignment and B2 controlled hypothesis/refutation contracts strong enough to keep all causal claims out of I1–I3?
8. Are existing PR #30 L4 (render cost) and L6 (shared private validation helpers) visible as pre-public-integration reviews, without weakening provenance checks?

**STOP** implementation if any answer compromises v0.2 backward compatibility, verified-claim authority, exact provenance, physical identity, full validation or engine-session reproducibility. The first deliverable after A0 review is I1, not immediate P10/P11/P12 rewiring.
