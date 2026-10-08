> **LEGACY — FROZEN, NOT THE CURRENT DESIGN.** This document describes the MVP-era implementation preserved at tag `legacy-mvp-g0`. It is kept only as historical reference for the redesign; nothing in it is a current requirement or decision. Current design: [`docs/design/`](../design/README.md). Index: [`docs/README.md`](../README.md).

# Calliope observation-to-commentary bridge — A0 corrected design

Status: **CORRECTED / AWAITING INDEPENDENT RE-REVIEW** (design only; not frozen/implemented)  
Date: 2026-10-08  
Base: `main @ 96c49abd46e664dceed6cb270c06c3d6ade62b70`  
Initial A0 commit: `9271576`; independent verdict: **READY_WITH_CORRECTIONS**, M1–M4 / L1–L5. No STOP finding.

This revision resolves the architectural findings for independent A0 re-review. Even after A0 READY, **I1-D independent design freeze is a mandatory separate gate before I1 implementation**. No source/test/public API changes are authorized by this draft.

## 1. Verified state and objective

The public `CalliopeEngine.analyze_move()` is composed in `src/calliope/composition.py` from existing Stockfish judgement, P8/P9 explanation, P10 evidence/claims, P11 selection, and P12 deterministic rendering. The new `PositionAnalyzer`, `TransitionAnalyzer`, `ActivityAnalyzer`, `ActivityTransitionAnalyzer`, `ActivityLineAnalyzer`, `ScenarioLineAnalyzer` and `ScenarioSummaryRenderer` are internal only. `AnalyzeMoveService.execute()` performs engine judgement and P8/P9 probes within `request_session()`, closes P10/P11 there, then projects/renders after that session. Public schema is `0.2`; P12 `CommentaryView.sentences` and `used_claim_ids` are paired 1:1.

Recent internal analysis answers **what is observed along a supplied legal line**, not **whether an observed change causes a good/bad evaluation**. Current `ScenarioKind` accepts **EXCHANGE** and `SquareTarget` only; additional scenario kinds do not exist yet. Its shared schema already owns `FactKind`, `EventKind`, typed keys/values, ten `SourceRef` variants, sentinels, `ScenarioSummary`, five-bucket `selection_accounting`, full recomputation validation and a source-linked English renderer. An EXCHANGE line is not automatically forced, optimal, settled or favorable. The first integration is for **observational prose**, with verified explanatory hypotheses deferred to B2/C.

## 2. Boundaries: O / C / H

- **O — observed fact:** exact, typed board geometry, pawn/file structure, physical-piece transition, capture, or a frame-local action snapshot, with provenance and no value judgement.
- **C — compared observation:** a factually aligned contrast between independently validated lines from the same immutable base; cannot infer cause of score change.
- **H — supported hypothesis:** separately scoped, adversarially tested explanation of *why* a move's judged quality is supported by the observed mechanism. Requires explicit controls, refutation, engine/line provenance and a reviewed P10 claim mapping.

Stockfish/MoveJudge retain exclusive move-quality authority. An open file, larger geometric attack footprint, material count in one supplied line, or an engine score next to a fact does **not** prove strategic value or causality. No P13/LLM is a chess truth source.

Do not produce P10 `ExplanationClaim`, `ClaimView`, a fake `used_claim_id`, or judgement-grade prose from O/C. Existing P8–P12 authority, priority mappings and strict validation remain unchanged until a separately reviewed causal P10 extension. Unsupported records and broken provenance **fail closed**, not optimistically render.

## 3. Chosen shared-architecture approach (M2)

**Choose reviewer option (a):** represent the played move as a one-ply supplied line, using a **proposed** additive `ScenarioKind.PLAYED_TRANSITION` and a typed played-move target (working name `PlayedMoveTarget`). Neither type is implemented or frozen at A0. **I1-D** must freeze the exact kind/target matrix and its request/target identity and membership policy. `supplied_line=(canonical_played_move,)` always begins from the same base `PositionSnapshot`.

**Do not build the previously proposed stand-alone `ObservedFinding` fact ontology.** Share `FactKind`, event and value records, source references, sentinels, physical `BasePieceRef`, identity correspondence checks, `ScenarioSummary` and summary validation. Any missing fact kind or template is an **additive versioned extension to the one shared vocabulary**, reviewed in I1-D, never a parallel set of chess facts. Existing EXCHANGE behavior/corpus remains unchanged; a new kind needs **its own** closed target/membership, candidate inclusion/exclusion and independent validator/corpus rules. Existing EXCHANGE validation must not be assumed to cover it automatically.

A separate compact **presentation selection ledger**, downstream of the completely validated `ScenarioSummary`, may have typed selection-state wrappers. This is **not** a new board-observation model, P10 evidence or `ExplanationClaim`. It references existing shared typed keys and source refs.

Execution in future I3: after P11 closure and **outside** Stockfish `request_session()`, preferably after the existing P12 rendering and public v0.2 computation. The observation path must make **zero** new engine/Stockfish analyses, re-use the same `PythonChessAdapter`, `PositionFactExtractor`, `BoardDeltaAnalyzer` instances, and never bypass legacy explanation selection. I1/I2 themselves remain internal; no public wiring occurs before I3.

```text
existing analyze_move(FEN, played move)
    -> Stockfish judgement -> P8/P9 -> P10 -> P11
    -> request_session ends -> existing P12 / v0.2 projection (unchanged)
                                    |
                            [later I3 opt-in only]
                                    v
shared scenario analyzer: PLAYED_TRANSITION (1 ply) / EXCHANGE (explicit line)
    -> shared complete validation / source references / five-bucket accounting
    -> compact presentation candidate ledger, stable selection/cap
    -> separate labelled observation output (proposed v0.3, NEVER P12 text)
```

No second public engine, no new tool endpoint, no public schema change, no `metadata` side channel is authorized in A0.

## 4. I1 facts: only reviewed shared kinds (M1 / M2 / L1)

The following **describes views over existing facts**, not new independent scenario-family enum values:

| View | Shared representation | Correct observational meaning |
| --- | --- | --- |
| Pawn structure | `PAWN_FLAGS`, `PAWN_SUPPORTERS` | isolated/doubled/passed/supporter facts at anchored frames; not an advantageous or legally safe pawn |
| File state | `FILE_STATE` | **open / semi-open for specified color / neither**; there is no independently defined `closed` `FileStructure` category |
| Physical transition | `PIECE_STATE`, `MOVE`, `CAPTURE`, `PROMOTION`, `CASTLING_ROOK` | validated move/piece identity, EP actual victim vs landing square, castling rook endpoints and promotion identity |
| Geometric activity | `ATTACK_FOOTPRINT`, `ATTACK_PARTITION`, `RAY_STATE`, `PIN_PRESENT` | frame-anchored attacks, occupancy and ray facts; no safe-mobility or better-move conclusion |
| **LEGAL_ACTION_SNAPSHOT** (replaces illegal DELTA) | `FOCUS_LEGAL_CAPTURES_NOW` on an explicitly focused square, or a newly **reviewed shared** per-piece kind | **one frame and its explicit side-to-move** only; neither current-side legal moves nor captures may be diffed across a move that flips the side to move |

The `LEGAL_ACTION_DELTA` concept from A0 is **retracted**. Opponent off-turn actions are **not observed**, not empty or zero. Geometric attacks do not imply a legal capture, and different side-to-move frames do not establish an action-count change. If `PLAYED_TRANSITION` cannot identify an explicit focus for `FOCUS_LEGAL_CAPTURES_NOW`, omit that candidate until I1-D defines the required target/snapshot extension.

I1-D must freeze the exact `PLAYED_TRANSITION` target shape, candidate fact kinds, allowed events, before/after semantics, frame-local snapshot fields, version/migration of shared vocabulary, source-ref resolution, and negative examples. No free-form string categories.

## 5. Integrity, reuse and execution contract (L2 / L5)

`TransitionAnalyzer` and `ActivityTransitionAnalyzer` may recompute some P4/P5 facts already traversed by P8/P9; **no extra Stockfish calls** does not mean zero additional Python/board work. Require the same immutable base `position_id` and canonical played UCI as the public move judgement, plus validated move transitions, exact physical correspondence (including en passant, all promotions, and king/rook castling), and common port-instance identities when wired.

Do not create a new chess adapter/engine instance. Reuse existing source domain facts and recorded frames. Validation must recheck entire relevant shared projection; altered subject, malformed canonical UCI, inconsistent rule/move, missing source, wrong frame, lost promotion identity and identical candidate-count/wrong-key mutations fail. Confirm no source/validator downgrade for existing EXCHANGE.

I1/I2 internal records may be requested without a public `analyze_move` change. At I3, the optional observation path runs **after** P11 has settled, **outside** engine session and after the existing P12 result is complete. I3-D must explicitly settle whether observation corruption in opted-in mode aborts the whole request or returns a typed error section alongside intact P12 output. No silent degradation of invalid records. With opt-in off, existing output and failures are unchanged.

## 6. Selection, cap, accounting: mandatory I1-D/I2-D freeze (M3 / M4)

The underlying shared `ScenarioSummary.selection_accounting` retains its full five-bucket domain: `STEPS`, `ENDPOINTS`, `EVENTS`, `SNAPSHOTS`, `AGGREGATES`. It expresses **scenario fact selection**, not a capped public narration. A compact **presentation candidate ledger** sits *after* this authoritative accounting and may not mutate it. `CAP_EXCEEDED` is a **presentation-layer exclusion reason**, not a silent addition to the existing EXCHANGE `ExclusionReason` enum.

I1-D (one ply) and I2-D (EXCHANGE line) must independently freeze a closed table with **one row per complete narrative candidate**:

| Field | Exact requirement for implementation/independent test |
| --- | --- |
| Candidate key | reference to existing typed shared fact/event/count key + the original scenario bucket + canonical subject/frame/line scope |
| Eligibility | defined by reviewed membership and actual change or directly relevant event; unchanged contextual trivia excluded with typed reason |
| Semantic duplicate key | stable shared kind/key + physical subject + anchored event/transition identity; **not** rendered string/SAN |
| Persistence | for multi-ply: compare validated initial and endpoint values for the same key/physical subject; transient = intermediate deviation returning to initial at endpoint; one-ply snapshot never compared across opposite side-to-move |
| Family ranking and tie | **total** deterministic family order, stable keys, and golden tie cases; not yet fixed at A0 |
| Disposition | **exactly one** of included/excluded per candidate; typed reasons for ineligible, semantic duplicate, and **`CAP_EXCEEDED`** for otherwise eligible lower-ranked facts |
| Source coverage | every included sentence resolves source refs back to the full validated shared summary; excluded entries remain auditable |

The ledger must partition **all candidates** exactly once: no missing keys, duplicate rows, included/excluded overlap, stale counts, unknown reasons, score-dependent ties or unrecorded cap loss. Selection is reproducibly recomputed, not caller-trusted. Golden corpus must include equal-priority conflicts, output overflow (including long-line >1,800 source sentences), transient vs persistent value comparisons, mirrors, same-count-wrong-key mutations, and an empty eligible set.

**Two observational sentences per move** is only an A0 *proposed* cap, NOT an implemented or accepted cap. Both exact cap and family ranking/ties are frozen in I1-D or I2-D, with independent corpus oracle defined before implementation. P11 continues to cap strict verified `ExplanationClaim` selection by its existing policy; observational sentences are separate and never consume a P11 slot. No inference that "because the move is BEST" a selected observation is the reason.

## 7. I2 wrapper and explicit-line rules (L3)

EXCHANGE in main already accepts `ScenarioRequest(EXCHANGE, SquareTarget(focus), initial, supplied_line, max_plies)`, validates the full legal line, emits a provenance-linked summary and renders closed observational English templates. I2 must use this **unchanged** frozen A1 request. A typed **I2 wrapper** (exact type frozen at I2-D) owns the supplied-line **origin label** (user/PV/test fixture), public anchoring, budget and compact presentation selection; the origin label conveys **no evidentiary strength**.

Initial I2: **explicit legal line + explicit focus square only**. No automatic focus, engine PV selection or inference that multiple focus captures constitute a settled/forced exchange. Any later automatic chooser requires a separately reviewed policy for initial root and move identity, requested played move vs PV first move, legality/replay/truncation, en passant victim vs landing, focus selection, length budget, and no untested forcedness. A PV rooted on another move cannot be explained as the requested played move's continuation.

I2-D (freeze + independent READY) is required **before I2 source edits**: exact wrapper, selection ledger/cap, stable priority/ties, source and origin contract, fail-closed behavior, golden E01–E15 including castling, EP and promotion; cost and no-extra-engine tests. Long `RenderedScenarioReport.detail` is never unconditionally sent to a user.

## 8. I3 separate public exposure and failure gate (L2 / L4)

I3 requires a **distinct I3-D frozen API proposal/independent review**. Candidate design: optional versioned **schema 0.3** projection with a separately typed and visibly labelled **"관찰된 사실" / "Observed facts"** section, distinct observation IDs and refs. Never append observational sentences to P12 `commentary.text` or pretend they are in `used_claim_ids`. An evaluation such as "MISTAKE" next to "the d-file opens" must be visibly noncausal rather than a single implied "mistake because the file opens" sentence.

Exact `AnalysisOptions` opt-in mechanism, version/serialization negotiation, DTO, rendered empty and error states, scope labels and failure policy remain **OPEN until I3-D**. Choose and adversarially test either **atomic failure on corrupt observation** or **typed observation-section error while preserving separately validated P12**; neither fallback is authorized without review. With opt-in disabled, the existing `analyze_move` response remains v0.2, including P12 strict claim-to-sentence 1:1 binding, selection order and original error semantics. No unreviewed `metadata` enrichment.

**I3 entry gate explicitly includes PR #30's L4 (validation/render cost) and L6 (shared-private-helper dependencies)**, with no validation shortcut. A real Stockfish end-to-end golden and before/after public compatibility tests are required before enabling opt-in exposure.

## 9. Later comparison and causal verification

**B1 — supplied-line comparison:** same immutable initial full `PositionSnapshot`; independent legal replay, common explicitly anchored target and physical-piece identities, declared frame/ply/endpoints alignment, cost bound and clear noncomparable outcomes for mismatched depths/line roots. Produce factual contrasts only. Similarity or score gap alone is not causal proof.

**B2 — verified positional hypotheses:** start with **one** closed family (working example `OPEN_FILE_ACCESS`), not an open-ended evaluation system. Define concrete O facts, admissible line/position controls, legal access mechanism (geometric ray alone insufficient), which alternative/response observations are required, P7 engine probe/session budget and stability, refutation and contradiction conditions, and a three-way internal verdict `SUPPORTED/REFUTED/INCONCLUSIVE`. An inconclusive outcome cannot generate causal prose.

**C — strict-claim integration:** only a separately reviewed SUPPORTED hypothesis may be mapped into an **extended** P10 evidence source/predicate/scope, independent `ClaimValidator` checks, P11 total family/priority table and P12 closed render template. Preserve existing P8/P9 interpretation and compatibility; do not attach a new string "reason" to old `ClaimView`.

**P13:** optional constrained LLM verbalization after all semantic checks, never before.

## 10. Performance and acceptance

Historical PR #30 one-shape Windows/Python 3.12.14 smoke measured (projection/render separately, replay excluded): 256 plies **2748.502 / 2952.347 ms**; 1 ply **17.662 / 19.859 ms**. These do **not** establish an end-to-end SLA, nor guarantee one-ply cost under other positions. Never render all 1,800 detailed sentences as a normal observational response.

I1: focus on one-ply exact observations, zero added engine analyses and complete v0.2 differential compatibility. I2: explicit bounded supplied lines, stress 0/1/8/16/64/256 plies, independent golden observation oracles and measured cold/warm replay, projection, selection, validation and compact rendering. Potential later PV auto-mode defaults (**proposed**, not frozen) at most eight plies.

Acceptance includes mirrored/colors, all promotions, en passant landing/victim, both castling transitions, legal-action side-to-move snapshots, source refs, full membership/accounting mutations, large-output suppression, same root/played UCI consistency, deterministic tie goldens, and refusal of causal/forced/safety language. An empty set of *eligible* observations is valid; broken structural evidence fails closed. No new external models, databases or cache trust flag.

## 11. Delivery and independent review gates (M3)

| Packet | Deliverable | Public delta | Mandatory gate |
| --- | --- | --- | --- |
| **A0 correction** | Shared-vocabulary direction, M1–M4/L1–L5, ordered gates | None | **A0 independent re-review READY** |
| **I1-D** | **Freeze** new `PLAYED_TRANSITION` kind/target, typed common fact/source change, scenario membership, candidate/ledger/accounting, selection cap/family rank/ties and adversarial corpus, precise failures | None | **independent design READY before I1** |
| I1 | One-ply shared scenario observation implementation | None | I1-D READY; independent implementation READY; zero engine calls, legacy unchanged |
| **I2-D** | **Freeze** EXCHANGE wrapper origin/explicit target, output ledger and cap, limits, error semantics, goldens | None | **independent design READY before I2** |
| I2 | EXCHANGE line compact selection and observation rendering | None | I2-D READY; independent implementation READY |
| **I3-D** | **Freeze** opt-in public version/DTO, visual noncausal separation, atomic/section error decision and L4/L6 performance/helper gates | None | **independent design READY before I3** |
| I3 | Versioned opt-in public observation output | Reviewed opt-in only | I3-D READY, real Stockfish + backward compatibility |
| B1 | Independently aligned line factual contrasts | Not presumed | independent design and implementation review |
| B2 | One falsifiable positional hypothesis with P7 | Not presumed | independent design and implementation review |
| C | Verified hypothesis in P10/P11/P12 | Reviewed schema+semantic change | strict adversarial, mutation and legacy gates |
| P13 | Optional LLM wording | Not presumed | semantic validator and P12 fallback |

I3 can expose **observational** content before B1/B2 causal integration. **A0 READY does not authorize I1 implementation**; it authorizes I1-D design work only. This also applies to I2-D and I3-D.

## 12. Re-review checklist and STOP conditions

1. **M1:** no current-side legal-action diff across changing side-to-move; `LEGAL_ACTION_SNAPSHOT` frame-local only, with explicit side.
2. **M2:** one shared `FactKind`/`SourceRef`/scenario validation ontology; proposed additive `PLAYED_TRANSITION`, never standalone `ObservedFinding`; new kind requires I1-D contract.
3. **M3:** independent frozen-design review before I1 and I2 source implementation; no candidate or tie implementation before corresponding corpus.
4. **M4:** narrative cap excluded via typed `CAP_EXCEEDED` ledger entry; all shared five-bucket scenario accounting stays complete; total deterministic priority and golden ties mandatory at design freeze.
5. **L1:** file-state output is open/semi-open-for-color/neither only.
6. **L2:** observational work after P11 outside session; public opt-in failure policy explicitly frozen in I3-D.
7. **L3:** origin metadata in I2 wrapper, never a new field in frozen `ScenarioRequest`.
8. **L4:** visually and structurally separate observations from P12 `commentary.text`; no implicit causal wording.
9. **L5:** shared port instances; exact same base `position_id`/canonical played move; independently check recomputation correspondence.
10. **Integration:** I3 explicitly rechecks PR #30 L4/L6, performance, real Stockfish, output cap, stable v0.2 clients.

**STOP** any implementation/promotion that weakens source integrity, physical identity, P10 Claim authority, engine-session isolation, fully accountable candidates, v0.2 compatibility or noncausal presentation. No new CI, merge, or runtime change is in scope here.

### A0 independent review disposition

Initial independent review: **READY_WITH_CORRECTIONS** at `9271576`; M1–M4 medium, L1–L5 low, no STOP. All points are mapped above. This correction is an **authored response**, not a claim of independent READY. Require independent re-review of this document/PR before I1-D.