# Calliope I1–I3 통합 구현을 위한 I2-D + I3-D 합동 설계안

Status: **PROPOSED / INDEPENDENT DESIGN REVIEW REQUIRED**
Date: 2026-10-08
Source baseline: main 96c49abd46e664dceed6cb270c06c3d6ade62b70
Stacked on: PR #31 A0 READY at 3432f77; PR #32 I1-D READY at 76de645bb3a60bd123da7c6278ea817befc04d14
Scope: **I2-D EXCHANGE compact observation + I3-D explicit opt-in public contract + single integrated I1/I2/I3 implementation handoff**.
No source, test, public API, migration, CI or runtime change is authorized by this design PR. I1-D is already approved and is not reopened.

## 1. Delivery contract — one implementation PR, three milestones

After one independent joint I2-D/I3-D review returns READY for **both**, implement I1, I2, I3 **as consecutive commits in one implementation branch and one implementation PR**, followed by one integrated independent source review. Never use approval of I1-D alone as approval of I2/I3 implementation. A READY_WITH_CORRECTIONS for either I2-D or I3-D is a hold, not an implementation permit.

Milestones:
- I1: use the exact frozen PR #32 contract: PLAYED_TRANSITION, complete affected facts, 21 core accounting rows, shared typed FactKind/SourceRef, 2-sentence cap, canonical D01–D20 corpus; EXCHANGE v1 bytes unchanged.
- I2: EXCHANGE with explicit user-provided line and focus; unchanged underlying summary and legacy renderer; **new separate complete presentation ledger and max-two-sentence compact renderer**.
- I3: add one explicitly named method to the same CalliopeEngine, plus a distinct schema 0.3 envelope containing the byte/semantic-equivalent original v0.2 DTO, labelled noncausal observations and exact source anchors.

No B1 line comparison, B2 positional causality, C P10 claim extension, P13 LLM, automatic PV, or unreviewed strategic-evaluation heuristics.

## 2. Verified source wiring and non-negotiable boundaries

Main composition.py builds one StockfishAdapter, one PythonChessAdapter, shared PositionFactExtractor and BoardDeltaAnalyzer, and the AnalyzeMoveService. AnalyzeMoveService.execute first validates FEN/played move using the same ChessRulesPort, executes judgement and P8/P9/P10/P11 inside request_session, then renders P12, projects MoveAnalysisResult and returns v0.2 **outside** session.

New opt-in path must call existing AnalyzeMoveService.execute(base) to completion **first**. Only then, entirely outside request_session, using the SAME chess adapter/facts/delta instances, reparse original canonical FEN and played UCI; compare the resultant position_id to the legacy v0.2 metadata position_id and move UCI to legacy judgement.move_uci. Do not interpret SAN as identity. Then run scenario replay/validation/selection/projection.

Legacy CalliopeEngine.analyze_move(AnalyzeMoveRequest) and AnalysisOptions, MoveAnalysisResult, CommentaryView, PUBLIC_SCHEMA_VERSION='0.2' remain unchanged: no fields hidden in metadata, no changed errors, no extra engine calls, no observation work unless new API is used. P12 sentence-to-used_claim_ids remains 1:1. New observations never become P10 Claims or get appended to commentary.text.

## 3. I2-D exact request and budgets

Frozen EXCHANGE ScenarioRequest(kind=EXCHANGE, target=SquareTarget(focus), initial, supplied_line, max_plies) is unchanged. Add only a typed **internal** wrapper ExchangeObservationInput(scenario: ScenarioRequest, origin: LineOrigin), with exact LineOrigin=USER|ENGINE_PV|FIXTURE; origin is descriptive provenance, **not** evaluation evidence. In initial public I3, origin is implicitly USER; there is no public caller-controlled origin and no automatic PV routing.

New public submitted EXCHANGE line has explicit focus square and a tuple of **0–8** canonical UCI moves. At most **2** independent supplied exchange lines per opt-in request. Use max_plies=8 for every submitted EXCHANGE. Reject longer lines; no truncation or synthetic forced variation. Full legality is checked via existing ChessRulesPort.legal_move_from_uci(current, uci), then ChessRulesPort.apply_move(current, move), sequentially from the **same initial position** and with identity/position_id checked against the legacy result. No second FEN/chess legality implementation.

A line rooted on another move is an explicit supplied alternative, **not** a continuation of the played move. Even when it starts with the played move, do not call subsequent replies forced, optimal or Stockfish-approved. Explicit focus may be landing square or en-passant victim square; the underlying A1 policy decides which events meet focus predicates.

Wrong type/kind/focus/size/cardinality/format => InvalidScenarioRequestError; illegal move => canonical ChessInputError subclass; corrupt observed line, provenance, candidate ledger or render => InvalidScenarioSummaryError; I3's opted-in atomic-failure rule applies.

## 4. I2-D complete compact ledger and deterministic ranking

Input: fully validated EXCHANGE ScenarioSummary. The EXISTING five-bucket scenario accounting (STEPS, ENDPOINTS, EVENTS, SNAPSHOTS, AGGREGATES), exact Included/ExcludedCandidate keys, EXCHANGE status, identities and full validation remain **byte identical**. No mutation of original source records or original ScenarioSummaryRenderer.render(summary) output.

New private ExchangeObservationSelector.select(summary) -> ExchangeObservationSelection. For every original scenario-**included** (Bucket, CandidateKey), store exactly one typed presentation ledger entry with canonical origin key, typed source_refs, eligibility, semantic identity, total rank and disposition INCLUDE or EXCLUDE with reason CONTEXT_ONLY, SEMANTIC_DUPLICATE or CAP_EXCEEDED. Underlying core-excluded keys stay in core accounting only. A capped fact always remains fully present in scenario summary. Full ledger partition and original source refs must be recomputed independently and checked; same-count/wrong-key is invalid.

Proposed exact ranking, smaller tier first:

| Tier | Core included candidate | Single allowed renderer |
| --- | --- | --- |
| 0 | EVENTS/CAPTURE with FOCUS_CAPTURE | existing EXCHANGE event text |
| 1 | EVENTS/CAPTURE with FOCUS_VICTIM_SQUARE, no FOCUS_CAPTURE | existing EXCHANGE event text |
| 2 | EVENTS/PROMOTION | existing EXCHANGE event text |
| 3 | AGGREGATES/FOCUS_LOSSES | existing EXCHANGE count text |
| 4 | AGGREGATES/MATERIAL_COUNTS | existing EXCHANGE count text |
| 5 | ENDPOINTS/selected factual changed property | new closed EXCHANGE_OBS_CHANGE |
| 6 | STEPS/selected factual changed property | same closed EXCHANGE_OBS_CHANGE |
| 7 | remaining selected EVENTS (MOVE, CASTLING_ROOK, contextual CAPTURE) | existing EXCHANGE event text |
| context only | SNAPSHOTS and unrenderable or unsupported core kinds | CONTEXT_ONLY, no sentence |

Allowed factual changed-property families: I1-D eight (PIECE_STATE, PAWN_FLAGS, PAWN_SUPPORTERS, FILE_STATE, ATTACK_FOOTPRINT, ATTACK_PARTITION, RAY_STATE, PIN_PRESENT) plus FOCUS_OCCUPANT and FOCUS_ATTACKERS. All other kinds => CONTEXT_ONLY. In particular FOCUS_LEGAL_CAPTURES_NOW is a single side-to-move snapshot, **never** a cross-turn legal-action difference. No score/claim priority.

Within one tier, canonical tie: **ply or frame index first**, then existing typed canonical CandidateKey ordering, then bucket order EVENTS, AGGREGATES, ENDPOINTS, STEPS, SNAPSHOTS. Never string-rendered sorting or dictionary iteration order. All Candidates have a total stable order. For 1-ply EXCHANGE only, a STEP/ENDPOINT pair with the exact same source-backed PropertyKey and 0→1 value difference has the ENDPOINTS copy classified as SEMANTIC_DUPLICATE, leaving STEPS eligible at tier 6; for N>1 duplicate only if both **exact frame pairs** and typed values agree. No text-based deduplication. Mark all ineligible before ranking; select first **2** eligible facts, remaining eligible => CAP_EXCEEDED.

Rendered EXCHANGE section's structured status is exact existing ExchangeDetail.status.value plus focus_capture_count=len(focus_capture_events); it is **not** an extra sentence and makes no assertion of recapture safety or compensation. E01 empty line may yield NO_FOCUS_CAPTURE with zero sentences. Do not always call legacy full-detail renderer: compact renderer reads the validated summary and selected facts only; it must still perform complete summary/source/ledger validation.

For events and count facts, preserve exact existing EXCHANGE event/count TemplateId and English, including the known EP duplicate-square wording (I3 wording debt, do not mutate legacy output). New EXCHANGE_OBS_CHANGE single exact envelope:
'In the supplied line after ply {b}, {label} [{family}] from frame {a} to {b}: {state_a} -> {state_b}.'
The frames a and b come from the exact SelectedChange. Reuse I1-D's closed typed value grammar for the eight families. For FOCUS_OCCUPANT render 'empty' or '{color} {piece_type} on {square} (initially {base_square})'; for FOCUS_ATTACKERS render 'white=(...), black=(...)', each physical attacker as '{color} {piece_type} on {square} (initially {base_square})' in physical base-square canonical order. Every resulting sentence has exact existing before/after source_refs, deduplicated in first-seen order. No free-form wording or LLM.

## 5. I2-D compact golden expectations and explicit approval requirements

Derive the actual test fixture FEN, line and focus from existing tests/golden/scenario_explanation_cases.json (A1 v2 corpus), not newly guessed positions. Freeze new compact **exact key/template/text** expectations as a distinct corpus file during independent review before implementation. These are the **expected top candidates** and a condition for approval (not an assertion that the new code exists):

| Scenario | Selected compact facts (up to two) |
| --- | --- |
| E01 (0 moves, focus e4) | none; NO_FOCUS_CAPTURE; count 0 |
| E02 (e4d5, focus d5) | CAPTURE ply1, FOCUS_LOSSES black:pawn |
| E03 (e2e4 d7d5 e4d5 d8d5, focus d5) | CAPTURE ply3, CAPTURE ply4 |
| E04 (e5d6, focus d6) | EP CAPTURE ply1, FOCUS_LOSSES black:pawn |
| E05 (e5d6, focus d5) | EP CAPTURE ply1 with FOCUS_VICTIM_SQUARE, MATERIAL_COUNTS black:pawn (no FOCUS_LOSSES) |
| E06 (a7b8q c8b8, focus b8) | CAPTURE ply1, CAPTURE ply2; PROMOTION is capped, not removed |
| E07 (e4d5 e8f8 h1g1 d8d5, focus d5) | CAPTURE ply1, CAPTURE ply4 |

For E01–E07, independent reviewer must freeze a new machine-readable read-only JSON including the precise (Bucket, CandidateKey), template ID, exact English, status, complete relevant presentation decisions (including cap-excluded promotion), and source kind expectations. E08–E15 retain original domain golden cases and gain compact selection/identity/cap tests; review must exercise representative EP, promotion, castling, pin and zero-capture contexts. If any proposed selection conflicts with actual existing shared summary, correct **this** design/corpus before authorizing implementation. The I1-D frozen D01–D20 remain unchanged.

## 6. I3-D exact public opt-in interface

**One facade, separate method.** New method:

CalliopeEngine.analyze_move_with_observations(request: ObservedMoveRequest) -> ObservedMoveAnalysisResult

New strict DTO definitions in contracts.py (no existing field or default modified):

- SuppliedExchangeObservationRequest(focus_square: str, moves_uci: tuple[str, ...] = ()).
- ObservedMoveRequest(base: AnalyzeMoveRequest, include_played: bool = True, exchange_lines: tuple[SuppliedExchangeObservationRequest, ...] = ()).
- ObservationSourceView(kind: str, anchor_kind: str, index: int | None, position_ids: tuple[str, ...], selectors: tuple[str, ...]).
- ObservationSentenceView(observation_id: str, template_id: str, text: str, source_refs: tuple[ObservationSourceView, ...]).
- ObservationSectionView(label: str, scope: str, supplied_line_uci: tuple[str, ...], focus_square: str | None, status: str | None, focus_capture_count: int | None, sentences: tuple[ObservationSentenceView, ...]).
- ObservedMoveAnalysisResult(schema_version: str, base_result: MoveAnalysisResult, played: ObservationSectionView | None, exchange_lines: tuple[ObservationSectionView, ...]).

Exact outer schema_version='0.3', embedded legacy base_result.schema_version='0.2'; outer result is a **new type**, legacy never returns 0.3. The explicitly named method itself is opt-in. include_played=False with zero exchange_lines is rejected as malformed opt-in. base.options.output_mode remains STRUCTURED or COMMENTARY unmodified; COMMENTARY retains strict P12 used_claim_ids, STRUCTURED keeps legacy commentary None, irrespective of observational sentences.

Section labels exactly 'Observed facts after the played move' and 'Facts in the supplied line'; scopes exactly 'played_transition' or 'supplied_line_exchange'. For played section, focus/status/count None; for exchange, focus required, status=ExchangeStatus.value, focus_capture_count exact nonnegative integer. Each section has <=2 exact source-linked sentences, total <=6 (one played + two supplied lines). Observations never appear in P12 commentary.text or ClaimView.

observation_id is deterministic request-local, scoped by section index, scope, Bucket and full canonical typed CandidateKey; no text/SAN or global persistence semantics. source_refs are **projected from fully validated internal SourceRef**, never caller-supplied or dynamically inferred. Unknown SourceRef type, wrong selector cardinality or missing source resolution => new ObservationProjectionError(ApplicationError), no guessed fallback.

## 7. Public source-ref closed projection

ObservationSourceView is not a generic metadata bag. Exactly one table rule per existing SourceKind; selectors are canonical positional string tuples, no unknown optional fields:

| Kind | anchor_kind / index / position_ids | selectors |
| --- | --- | --- |
| CAPTURE | step / ply / before,after | () |
| TRANSITION | step / ply / before,after | base-triple + transition kind |
| MATERIAL | endpoints / None / initial,final | color, piece type |
| PIECE_HISTORY | frame / frame index / one id | base-triple |
| SQUARE_ACCESS | frame / frame index / one id | square |
| PAWN_STRUCTURE | frame / frame index / one id | base-triple |
| FILE_STRUCTURE | frame / frame index / one id | file |
| PIECE_ACTIVITY | frame / frame index / one id | base-triple |
| SLIDER_RAY | frame / frame index / one id | base-triple, signed df and dr decimal strings |
| ABSOLUTE_PIN | frame / frame index / one id | pinner triple, pinned triple, king triple |

Base-triple is exactly Color.value, PieceType.value, initial base_square; no current square used as physical identity. Frame position ids must match exact frame index; step position ids match both P5 step endpoints. Public ref integrity is proven by underlying summary validator and closed projection; no SourceRef fed back from public caller.

## 8. I3-D failure and budget contract

Choose **atomic opted-in failure**. Any malformed exchange request, illegal supplied move, incorrect root/position id, corrupt summary/selection, or source projection inconsistency **raises a typed error and returns no partial ObservedMoveAnalysisResult**. Valid absence of eligible facts yields a present section with zero sentences, not an exception or fake claim. Do not silently drop a bad observation while returning successful P12.

Preflight request object/enum, length 0..8 per explicit line, max 2 lines, canonical lowercase UCI shape and duplicate requests **before any Stockfish analysis**. Actual chess legality is delegated to the same existing ChessRulesPort (do not create second pawn/king rule engine). A chess-illegal supplied move may be discovered after legacy analysis but adds zero new engine analyses. Existing legacy errors stay exactly unchanged on legacy path.

No new engine search, no internal call to request_session for observations, no implicit PVs, no automatic comparison, no optional LLM. Measure cold/warm replay, full scenario integrity validation, selection, compact rendering, projection and overall delta on 0/1/8-ply cases. Internal stress covers 16/64/256 for regression/cost but public hard limit is 8. PR #30 L4 rendering cost and L6 shared-private-helper ownership are explicit I3 admission gates; any required refactor needs a separately reviewed amendment and cannot weaken full validation.

## 9. Single implementation handoff after joint READY

Proposed branch from exact PR #32 head: implementation/i1-i3-observation-bridge (branch to be created only when this joint design returns READY).

Commit I1: new scenario kind/detail/projection/selector under unchanged I1-D, run D01–D20 + D17 EXCHANGE byte compatibility.
Commit I2: explicit EXCHANGE wrapper, shared presentation ledger/compact renderer, independently frozen E01–E15 compact goldens; DO NOT change existing renderer's legacy digest/detail.
Commit I3: new DTOs, application service and explicit facade method, composition with same adapter/facts/delta instances; nested v0.2 and strict 0.3 envelope, atomic failure, real Stockfish acceptance, no legacy path changes.
Commit integrated correction, if independently justified: relevant targeted tests only, no new CI or full suite unless requested.

Admissible I1/I2 implementation files: scenario domain/service/renderer, new private selector, unit/corpus tests. I3 may additionally add new DTO exports in contracts.py/__init__.py, engine.py facade method, composition.py factory and separate application orchestration/projection. Do not modify legacy AnalyzeMoveService.execute logic without explicit renewed design review.

Acceptance must prove:
- I1-D D06-q/r/b/n file change precedes material, D13 total census, D19/D20 remote facts, D17 legacy EXCHANGE byte exact.
- I2 compact E01–E15, no supplied-line forcedness, cap accounting/duplicate integrity, independent source references.
- I3 exact nested legacy v0.2 DTO, P12 claim/sentence 1:1, schema 0.3 only via explicit opt-in, no extra Stockfish calls or session leakage, atomic errors, 2-line/8-ply/2-per-section caps and source-reference closure.
- Missing/changed candidate key with same count, broken BasePieceRef, wrong frame, source swap, failed complete validation, forged selection, changed error reason must fail.
- Record measured performance and PR #30 L4/L6 disposition before I3 public acceptance.

## 10. Joint independent review questions / STOP

1. Is I2 selector's total candidate table, status and exact source-linked 2-sentence semantics unambiguous for **all** EXCHANGE cases? Demand machine-readable new E01–E07 exact goldens before READY.
2. Do all existing EXCHANGE v1 source/summary/renderer bytes survive untouched, including EP wording?
3. Is one-ply duplication and multi-ply nonduplication exact and auditable in the shared five-bucket accounting?
4. Is I3 opt-in independent of legacy v0.2, with a complete typed new DTO and authoritative SourceRef projection?
5. Does chosen atomic-failure mode reject invalid observations without incorrect empty-success fallback?
6. Do exact budgets, a single PythonChessAdapter/facts/delta graph and zero extra Stockfish calls remain enforceable?
7. Are PR #30 L4/L6 risks measured and closed before I3 public release?

Return I2-D verdict, I3-D verdict and overall joint verdict as READY / READY_WITH_CORRECTIONS / NOT_READY. **Both READY needed before single integrated I1–I3 implementation starts.** This PR is design-only; no merge/implementation during review.
