# Calliope I1–I3 단일 구현 패킷 — 실행 인수인계

**Status: PREPARED / DO NOT IMPLEMENT UNTIL PR #33 I2-D + I3-D INDEPENDENT READY**
Baseline: PR #31 A0 READY, PR #32 I1-D READY at 76de645bb3a60bd123da7c6278ea817befc04d14.
Implementation base after approval: exact final approved HEAD of PR #33, NOT main. PR #31/#32/#33 are stacked documents; do not merge them during implementation.

## Preconditions (STOP if any fail)

1. Verify PR #31 A0 READY, PR #32 I1-D READY, and **both** I2-D and I3-D independent READY on PR #33's final head.
2. Fetch and verify branch/HEAD and clean working tree. Create exactly one new implementation branch from the **approved PR #33 HEAD**. Recommended: implementation/i1-i3-observation-bridge.
3. Independently run the frozen I1-D design corpus checker with --schema-only and --full; and joint I2-D/I3-D compact corpus checker with both modes. Preserve JSON expectations; implementation must not rewrite them to pass.
4. Capture baseline EXCHANGE E01–E15 summary + renderer exact serializations, public v0.2 structured/commentary DTO and Stockfish call counts **before touching implementation code**.
5. Review exact final contracts in docs/observation-commentary-bridge-design.md, docs/observation-i1d-played-transition-freeze.md, docs/observation-bridge-i2i3-joint-design.md and both corpus JSON files.

## Commit I1 — shared played transition only

Implement I1-D exactly: PLAYED_TRANSITION/PlayedMoveTarget/PlayedTransitionDetail as closed kind/detail union and version, complete board-effect membership, selected_changes/endpoint_changes, 21 accounting rows, shared SourceRef/physical identities and typed full validation; 2-sentence deterministic presentation selection (CONTEXT_ONLY, SEMANTIC_DUPLICATE, CAP_EXCEEDED) and exact PLAYED_STATUS/PLAYED_CHANGE grammar. D06-q/r/b/n file-a priority, D13 complete census, D19 discovered pin, D20 remote passed pawn. NO public engine/DTO wiring at this stage. Run targeted corpus tests, D17 byte oracle.

## Commit I2 — explicit supplied EXCHANGE compact selector

Implement the joint-frozen explicit origin wrapper; retain original EXCHANGE request/summary/accounting/source validator/legacy renderer bytes. New internal selector/renderer over the complete validated summary, one presentation row per core included fact, exact tiers 0..7 and typed exclusion reasons, max 2 selected sentences. Reuse original EXCHANGE event/material wording, new EXCHANGE_OBS_CHANGE only for eligible supported typed changed facts; snapshots are context only, no cross-turn legal-action diffs. Use already approved frozen E01–E07 compact JSON as independent golden plus E08–E15 sources; do not auto-select PV, infer focus/forced exchange, or render full detail in public path. Measure replay, validation, selection and compact formatting separately.

## Commit I3 — one new explicit public method

New CalliopeEngine.analyze_move_with_observations(ObservedMoveRequest) returns strict outer schema 0.3 result, with the exact previously returned schema 0.2 MoveAnalysisResult nested unchanged, plus separate labelled played/explicit EXCHANGE sections with exact source-anchored sentences. Keep legacy analyze_move method, AnalysisOptions and P12 commentary.text/used_claim_ids fully unchanged.

Implement preflight of new options/count/line syntax **before** old engine call. Execute old AnalyzeMoveService.execute to completion, after P12 and outside Stockfish session perform new factual observation work using SAME rules/facts/delta object instances, root and played-UCI equality, fully typed source ref projection. Max 2 exchange lines of 0..8 plies; max 2 sentences per section, total <=6. Atomic opted-in error on invalid observation, no success with silently omitted data; valid zero eligible facts means zero-sentence section. No added Stockfish calls.

## Focused regression gates (mandatory)

- D01–D20 I1 independent data and negative mutation tests, especially full D06/D13 candidate ranking and remote D19/D20.
- D17 legacy EXCHANGE **byte identical** summary/detail/digest English for E01–E15; D18 v0.2 exact DTO/P12 Claim ID semantics and engine-call count unchanged.
- I2 E01 empty, E02 capture+focus loss, E03 paired focus captures, E04/E05 EP landing-victim split, E06 capture-promotion contextual cap, E07 quiet interruption; existing E08–E15 with exact provenance and full ledger.
- I3 STRUCTURED and COMMENTARY nested legacy outcomes, wrong type/input/cardinality, 2-line limit/8 ply bound, duplicate supplied line, SAN UCI identity, illegal move, wrong base, corrupt source/ledger, fail-closed no partial result, shared adapter/facts/delta object identity.
- Real Stockfish integration in both output modes; compare legacy and opt-in Stockfish analysis request sequence and session boundary; verify **zero added engine calls**.
- Internal stress 0/1/8/16/64/256 plies where appropriate; document measured cold/warm cost and PR #30 L4/L6 risk disposition. Never remove validation to meet a speed target.
- No new GitHub CI jobs. Run targeted pytest/Ruff and a relevant real-Stockfish slice; full suite only if separately requested or existing CI.

## Scope and deliverables

Allowed implementation edits: scenario domain/service/renderer and new internal selectors/wrappers, focused tests, new opt-in DTOs/projection/service, facade and composition wiring, explicit exports, docs. Preserve original AnalyzeMoveService.execute code unless an unavoidable incompatibility triggers independent design review. No database, scheduler, P10/P11/P12 rewiring, external LLM, or auto PV.

Finish only after commit and push with no PR creation, no merge, no deployment. Return:

I1_I3_INTEGRATED_IMPLEMENTATION_RESULT: READY_FOR_INDEPENDENT_REVIEW | NOT_READY
BASE_VERIFIED:
BRANCH:
FINAL_HEAD:
I1_SCOPE:
I2_SCOPE:
I3_SCOPE:
PUBLIC_0_2_DELTA:
EXCHANGE_V1_BYTE_DELTA:
STOCKFISH_CALL_DELTA:
SESSION_BOUNDARY:
I1_CORPUS:
I2_CORPUS:
D06_D13:
D19_D20:
D17_D18:
I3_REAL_STOCKFISH:
TARGETED_TESTS:
RUFF:
LATENCY_EVIDENCE:
DESIGN_DEVIATIONS:
BLOCKERS:
INDEPENDENT_REVIEW_FOCUS:

**STOP** before implementing if the final independent I2-D or I3-D verdict is not READY. Stop and report any frozen-design inconsistency instead of changing the contract/corpus to match implementation.
