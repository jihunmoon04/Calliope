> **LEGACY — FROZEN, NOT THE CURRENT DESIGN.** This document describes the MVP-era implementation preserved at tag `legacy-mvp-g0`. It is kept only as historical reference for the redesign; nothing in it is a current requirement or decision. Current design: [`docs/design/`](../design/README.md). Index: [`docs/README.md`](../README.md).

# I1-D — PLAYED_TRANSITION single-ply observation design freeze candidate

**Status:** DESIGN CANDIDATE / AWAITING INDEPENDENT REVIEW (**NOT YET READY FOR I1 IMPLEMENTATION**)  
**Date:** 2026-10-08  
**Stacked base:** PR #31 A0 accepted by independent re-review at `3432f77`; upstream main `96c49abd46e664dceed6cb270c06c3d6ade62b70`.  
**Scope:** I1-D only: exact closed kind/target/detail, policy membership, accounting, compact observational selection, renderer templates, guards, and independent corpus.  
**Non-scope:** production implementation, public schema/DTO, composer changes, engine/P7/P8/P9/P10/P11/P12 semantics, EXCHANGE replay/claims/English, I2 explicit EXCHANGE compact projection, B1 comparisons, B2 hypotheses, P13 LLM.

The reviewer reported A0 **READY**, including M1–M4/L1–L5, with nonblocking N1 (closed kind/detail/version/dispatch/byte-stability) and N2 (PLAYED-specific status/digest/template). This document provides **specific proposed frozen decisions** for independent I1-D adjudication. Source edits do not start until **I1-D independently READY**.

## 1. Source-verified present behavior

- `ScenarioKind` currently contains only `EXCHANGE`; `ScenarioRequest(kind, target: SquareTarget, initial, supplied_line, max_plies=64)` rejects all other kinds and target types. EXCHANGE accepts zero to 256 supplied moves subject to budget; do not weaken this.
- `ScenarioSummary` is a frozen Record with `detail: ExchangeDetail`, `definition_version="scenario_summary_v1"`, `events`, `focus_timeline`, `selected_changes`, `endpoint_changes`, `feature_histories`, and `selection_accounting`.
- Five accounting buckets: STEPS, ENDPOINTS, EVENTS, SNAPSHOTS, AGGREGATES. Only *value-changing* properties are candidates in STEPS/ENDPOINTS; unchanged snapshots are frame records, and legal actions are snapshot-only.
- `_Projection` already projects typed properties/events and resolves ten typed `SourceRef` kinds from the retained `ActivityLineAnalysis`. `_ExchangePolicy` and `_build` currently implement EXCHANGE selection. `validate_scenario_summary` checks exact re-projection.
- `ScenarioSummaryRenderer` assumes EXCHANGE focus/status/counts and validates before rendering. `TemplateId` is a closed StrEnum.
- The installed public facade does **not** wire any new scenario service. MVP v0.2 and Stockfish requests must remain untouched in I1.

Source: `src/calliope/domain/analysis/scenario.py`, `src/calliope/services/position/scenario.py`, `src/calliope/services/position/scenario_renderer.py`, `src/calliope/services/position/activity.py`, `src/calliope/services/position/line.py`.

## 2. Typed request, details, dispatch and version (N1)

Choose a **single shared scenario contract**, additive closed-union form; no separate fact/board ontology and no plugin/registration framework.

### New and preserved types (design signatures)

```python
class ScenarioKind(StrEnum):
    EXCHANGE = "EXCHANGE"               # UNCHANGED
    PLAYED_TRANSITION = "PLAYED_TRANSITION"

@dataclass(frozen=True, slots=True)
class PlayedMoveTarget:
    move: ChessMove                     # canonical domain move, not SAN/string

@dataclass(frozen=True, slots=True)
class PlayedTransitionDetail(Record):
    mover: BasePieceRef                 # physical base identity at frame 0
    participants: tuple[ParticipantSummary, ...]
    capture_event: CaptureKey | None
    transition_events: tuple[TransitionKey, ...]
    definition_version: str = "played_transition_rules_v1"

# Existing ScenarioRequest gains the exact target union, preserving field order/default:
ScenarioRequest.target: SquareTarget | PlayedMoveTarget

# Existing ScenarioSummary gains exact detail union, preserving every other field:
ScenarioSummary.detail: ExchangeDetail | PlayedTransitionDetail
ScenarioSummary.definition_version: str = "scenario_summary_v1"  # KEEP default
```

**Matrix, exact types and cardinality:**

| Kind | Target | Supplied line | Budget | Detail | Summary version |
| --- | --- | --- | --- | --- | --- |
| `EXCHANGE` | **exact** `SquareTarget` | tuple, length 0..max_plies | int 1..256 | **exact** `ExchangeDetail` | `scenario_summary_v1` |
| `PLAYED_TRANSITION` | **exact** `PlayedMoveTarget` | tuple, length **exactly 1**, with exact `target.move.uci == supplied_line[0].uci` (SAN ignored) | **exact int 1** | **exact** `PlayedTransitionDetail` | **`scenario_summary_v2`** |

Wrong kind/target, bool budget, non-tuple, empty/multi-ply PLAYED, nonmatching `target.move.uci`/`supplied_line[0].uci`, and either noncanonical UCI are `InvalidScenarioRequestError` **before ActivityLineAnalyzer**. Independently require both UCIs to exactly match lowercase `[a-h][1-8][a-h][1-8][qrbn]?`, no surrounding whitespace, unequal from/to squares, and only suffix rank shape: when a promotion suffix is present, require rank 7→8 or 2→1. Do **not** parse FEN or reimplement pawn-type or missing-promotion rules in preflight; the canonical chess adapter owns those. SAN is never identity. Legal-but-different SAN must still be accepted. Final move legality remains the canonical adapter's check. PLAYED **requires explicit `max_plies=1`**; the preserved default 64 is deliberately invalid for PLAYED. Render `{uci}` only from the fully validated `observed_line.structural.transitions[0].board_delta.move.uci`, never raw request text. For PLAYED, the move is independently checked against the initial board by the canonical chess rules during one-ply replay; `ChessMove` type alone never grants legality. `request.initial.position_id` is the one true base anchor; no redundant editable "base id" in target.

**Versioning choice:** keep legacy EXCHANGE records and serialized/repr form exactly as in v1, including default value and field order; new PLAYED records explicitly set `scenario_summary_v2` and `played_transition_rules_v1`. The validator independently enforces the cross-product `(kind, target type, detail type, detail version, summary version)` **before** projection comparison. Old EXCHANGE `definition_version` remains v1; no silent v1->v2 migration. If a downstream serializer lacks v2 awareness, it must reject PLAYED rather than misdecode it as EXCHANGE.

**Detail contract:** `mover` is the unique initial `BasePieceRef` at the move's from-square. `participants` is canonical in base-square order and includes exactly: mover; capture victim (including off-landing en passant victim), if any; castling rook, if any. `ParticipantSummary.history_refs` uses exactly frames 0 and 1, including post-capture `CAPTURED`. `capture_event` equals `CaptureKey(1)` iff the board delta captures, else `None`. `transition_events` is the exact canonical tuple of included, non-capture `TransitionKey`s at ply 1 (promotion and both castling participants where present). `detail` does **not** assert advantage, trade resolution, strategic purpose, forcedness, or material compensation.

### Closed dispatch; preserve legacy function

```text
ScenarioLineAnalyzer.analyze(request)
  -> request kind/target/length preflight
  -> ActivityLineAnalyzer.analyze(initial, supplied_line, max_plies) EXACTLY ONCE
  -> _validate_observed(request, observed) (existing full validation)
  -> _Projection(request, observed) (reuse typed facts and refs)
  -> switch exact ScenarioKind:
      EXCHANGE          -> existing _build() + _ExchangePolicy (no reordering)
      PLAYED_TRANSITION -> new _build_played() + closed _PlayedPolicy
      otherwise         -> typed failure
  -> ScenarioSummary
```

In particular, `_Projection.properties()` today dereferences `request.target.square` for FOCUS. For PLAYED, use a separate focus-free property enumerator over the existing same key/value/source methods, or parameterize *internally* without changing EXCHANGE iteration order. No fictitious default focus on destination square. `validate_scenario_summary` performs **same exact kind-dispatch projection recomputation**, not just local record checks.

Do not make a general registry, dynamic callbacks, plugin maps, or a second replay/analyzer; a closed two-kind dispatch is enough. Do not relax the existing `Record`, `_local`, `VALUE_TYPES`, source-selector validation or `_validate_observed` invariants.

## 3. Effect-complete membership and five-bucket census (M3)

**Chosen option (a), broad but truthful:** for one legal move, **every supported actual typed value change from frame 0 to frame 1 belongs to the scenario**, regardless of whether its physical subject moved. This includes discovered nonparticipant rays/pins, changes to a stationary pawn's passed status and newly exposed attacks. Such observations prove **what changed**, not why the move is good. No score/engine input enters this membership rule.

Let `B` be all physical BasePieceRefs from the initial frame and `P` only the directly moved/captured pieces: mover, captured victim (EP off-landing included), and castling rook if any. `P` is reserved for `PlayedTransitionDetail.participants` and deterministic presentation tiebreak preference; `P` **never filters scenario facts**. For pinned triples enumerate the union of actual observed pin triples at both frames; slider directions from real piece type at 0 or 1. No hypothetical pairs or new geometry oracle.

| Bucket | Complete candidate domain | Core inclusion |
| --- | --- | --- |
| STEPS | `StepKey(1,key)` for every value change in 8 shared families: PIECE_STATE, PAWN_FLAGS, PAWN_SUPPORTERS, FILE_STATE, ATTACK_FOOTPRINT, ATTACK_PARTITION, RAY_STATE, PIN_PRESENT | ALL |
| ENDPOINTS | matching PropertyKey of the exact same 0→1 changes | ALL |
| EVENTS | all real CAPTURE, PROMOTION, MOVE and CASTLING_ROOK P5 events in canonical order; redundant captured mover MOVE suppressed as in EXCHANGE | ALL |
| SNAPSHOTS | no focus square: none | no rows |
| AGGREGATES | every nonzero MATERIAL_COUNTS delta (pawn decrement and promoted-role increment separately when relevant) | ALL |

**Exactly 21 rows**: 8 STEPS + 8 ENDPOINTS + 4 EVENTS + 1 AGGREGATES; zero SNAPSHOTS and no FOCUS_LOSSES. Every allowed family has a row even with no candidates. In every PLAYED core row: `candidate_keys == included_keys` and `excluded=()`; EXCHANGE's original five-bucket accounting remains unchanged. Two core rows can hold the same one-ply changed fact under different bucket keys; this is intentional.

Append the new closed shared `SelectionReason.PLAYED_CHANGE` **after** all existing EXCHANGE reasons. Every PLAYED changed-property/event inclusion has exact reason `(PLAYED_CHANGE,)`, never a misleading `PARTICIPANT` for stationary subjects. EXCHANGE never uses the new reason and existing enum ordering/repr remains unchanged. Material CountFact has source evidence but no separate selected-change reason field.

Keep `selected_changes` and `endpoint_changes` as the complete independently accounted 0→1 differences; complete two-frame histories for eligible non-PIECE_STATE tracks. `focus_timeline=()`. No cross-turn legal-action diff, opponent action assumed zero, automatic focus, or invented FOCUS_LOSSES.

**D19:** bishop e2f3 uncovers rook e1's ray and pin of unmoved knight e7 to king e8; the ray and PIN_PRESENT key must be core-INCLUDED despite rook/knight not being directly moved. **D20:** e4xd5 removes d5 black pawn, leaving stationary white c4 pawn newly passed; c4 PAWN_FLAGS must be core-INCLUDED despite c4 not in P.

All fact values and ten SourceRef forms are the existing shared domain types. Changed FILE_STATE uses exact open/semi-open-for-color/neither as derived from white/black pawn counts.

## 4. Closed narrative candidate ledger, precedence and cap (M4)

This section **freezes a proposed implementable selection algorithm for independent review**, not chess importance/advantage. The observer never reads judgement, score, rank, MultiPV, P10 Claims, or P11 selection.

### Candidate domain and auditable record

Only the **scenario-accounting included keys** are eligible as presentation candidates; core excluded keys remain fully auditable in core `selection_accounting` and are **not** spuriously reentered into presentation. For every *included* `StepKey`, `PropertyKey` endpoint, `EventKey`, or `CountKey`, emit exactly one typed presentation-ledger record:

```text
PresentationCandidate(
  origin_bucket: Bucket, origin_key: CandidateKey,
  family: FactKind | EventKind | CountView,
  base_position_id: str, subject_or_key: typed existing shared key,
  frames_or_ply: exact 0→1 or ply=1,
  source_refs: tuple[SourceRef,...],
  semantic_key: typed immutable tuple from shared key + exact before/after values,
  rank_key: typed total ordering key,
  decision: INCLUDE | EXCLUDE,
  exclusion_reason: None | CONTEXT_ONLY | SEMANTIC_DUPLICATE | CAP_EXCEEDED
)
PlayedObservationSelection(
  candidates: tuple[PresentationCandidate,...],   # full auditable ledger
  selected_keys: tuple[(Bucket,CandidateKey),...], # only INCLUDE
)
```

The presentation wrapper/ledger does **not** introduce a second `FactKind`, SourceRef resolver, scenario truth-value schema, or P10 claim. IDs are keyed by the pair `(Bucket,CandidateKey)` inside this request; no synthetic root UCI or rendered text participates in identity.

**Core accounting vs presentation accounting:** core `NOT_SCENARIO_RELEVANT` stays in five-bucket rows. All and only core included keys appear exactly once in presentation ledger. Presentation-excluded candidates remain recorded with typed `CONTEXT_ONLY`, `SEMANTIC_DUPLICATE` or `CAP_EXCEEDED`. Do **not** add either to core `ExclusionReason` without a separate versioned core design.

### Presentation eligibility, semantic dedup, exact rank and cap (M4/L4)

- **Every ENDPOINTS changed candidate is a semantic duplicate of its STEPS counterpart for one ply.** Retain both in core accounting; exclude every ENDPOINTS presentation candidate as `SEMANTIC_DUPLICATE` with its typed STEPS anchor, regardless of wording, template or display cap.
- Independently, a property candidate whose frame-0 or frame-1 value is `Sentinel.NOT_APPLICABLE` or `Sentinel.CAPTURED` is not suitable for compact prose: exclude its STEPS presentation record with `CONTEXT_ONLY`. This does not remove a captured/promoted piece, pin or changed fact from core accounting. ENDPOINTS duplicate exclusion still takes precedence on its own record.
- Exact family priority tiers (ascending): CAPTURE=0, PROMOTION=1, CASTLING_ROOK=2, PIN_PRESENT=3, FILE_STATE=4, MATERIAL_COUNTS=5, PAWN_FLAGS=6, PAWN_SUPPORTERS=7, MOVE=8, ATTACK_FOOTPRINT=9, ATTACK_PARTITION=10, RAY_STATE=11, PIECE_STATE=12. Tier measures **narrative order**, not chess value.
- Exact tie-key within a family: subject `in P` before subject outside P; for FileKey/PinKey non-subject keys use no direct-participant privilege; then existing canonical `_candidate_index(key)` (StepKey unwrapped to its PropertyKey for duplicate canonical tie). Full rank `(tier, direct_participant_priority, canonical_key_index, bucket_order)`; bucket_order is STEPS, ENDPOINTS, EVENTS, AGGREGATES, though one-ply step/endpoint duplicates are already reconciled. For event/aggregate tier use canonical source key ordering. All rank components use typed shared keys, never SAN or arbitrary Python object order.
- Select **at most 2** remaining candidates in rank order. Every other eligible candidate is excluded as `CAP_EXCEEDED`. No silent omission, truncation or feature-count superiority judgement.
- Every **core included** key has exactly one presentation ledger record with source bucket/key, typed source refs, family, physical subject/frames, semantic identity and one disposition: INCLUDE, or EXCLUDE with exactly `CONTEXT_ONLY`, `SEMANTIC_DUPLICATE` or `CAP_EXCEEDED`. Core excluded keys remain only in core accounting. Empty eligible set yields no digest, not a fabricated explanation.
- `len(digest)==len(selected_keys)<=2`; exact selected order, template ID, words and referenced typed values are independently regenerated and compared. Changed keys, equal-length substitution and forged ledger entries fail closed.

### One exact PLAYED template catalog (N2/M1)

**Exactly one** PLAYED_STATUS string (not an alternative):

```text
In the supplied one-move line, the played move is {uci}.
```

It is the **sole** `RenderedScenarioReport.detail` sentence for PLAYED and has `TemplateId.PLAYED_STATUS`. Its `source_refs` is the **entire exact `source_refs` tuple of the canonical first included ply-1 `ScenarioEvent`**, in existing event order. Every legal one-ply move yields at least one event. The `uci` is taken from the validated `board_delta.move.uci`, not the request string. Status does **not** count toward the digest cap.

**Exactly one** PLAYED_CHANGE envelope:

```text
In the supplied one-move line {uci}, {label} [{family}]: {state_before} -> {state_after}.
```

- `uci` is the validated ply-1 board delta's canonical UCI. `family` is the exact shared `FactKind.value`, not free-form prose.
- `label`: `piece initially on {base_square}` for SubjectKey/RayKey; `file {letter}` for FileKey; `absolute pin (pinner={base square}, pinned={base square}, king={base square})` for PinKey. Squares are physical initial bases.
- Each `state` comes from the validated frame-specific typed Fact; no engine, SAN, `repr()` fallback or natural-language inference.

| Shared kind | Exact state representation |
| --- | --- |
| PIECE_STATE | `captured` or `{color.value} {PieceType.value} on {square}` |
| PAWN_FLAGS | `not applicable` or `isolated={true/false}, doubled={true/false}, passed={true/false}` |
| PAWN_SUPPORTERS | `not applicable` or `geometric pawn supporters=({initial square list})` |
| FILE_STATE | `white_pawns={n}, black_pawns={n}, state={open / semi-open for white / semi-open for black / neither}` |
| ATTACK_FOOTPRINT | `not applicable` or `geometric squares=({canonical board-order square list})` |
| ATTACK_PARTITION | `not applicable` or `geometric empty=({squares}), friendly=({squares}), enemy=({squares})` |
| RAY_STATE | `not applicable` or `visible=({ray-ordered squares}), occupants=({physical occupants with initial/current square})` |
| PIN_PRESENT | exact `true` / `false` for the fixed physical triple |

All tuple strings use parentheses and `, ` separation, with `()` for empty; booleans lowercase. Canonical square order is **rank-major board order (`a1,b1,...,h1,a2,...,h8`)**, not alphabetic-string order. Physical ray traversal/occupants remain near-to-far along the ray. `CAPTURED` / `NOT_APPLICABLE` are not coerced into numerical zero. PLAYED_CHANGE is one sentence for one source-backed STEPS fact; its `source_refs` combines exact before and after `Fact.source_refs` in stable first-seen order.

Event candidates retain **the exact existing EXCHANGE `_event` English and TemplateId** (CAPTURE_NORMAL, CAPTURE_EP, PROMOTION, CASTLING_ROOK, MOVE); material candidates retain **the exact existing MATERIAL_COUNTS** formatter. No second English wording is permitted. **Known wording debt (L3):** EXCHANGE's en-passant template repeats the victim square (e.g., `removing black pawn on d5 from d5`). Preserve the existing English bytes in I1; record an **I3-D** public-wording review action rather than changing EXCHANGE here.

`ScenarioSummaryRenderer.render(summary)` remains returning the same `RenderedScenarioReport(digest, detail)`, with EXCHANGE byte-exact unchanged and PLAYED dispatched to this one-line status plus at most two selected factual digest sentences. `PlayedObservationSelector.select(summary) -> PlayedObservationSelection` returns the independent, fully auditable typed presentation ledger. The PLAYED renderer calls that selector **again**, fully recomputes and validates returned selection against the summary, and checks every source ref; it never trusts a caller-supplied selected list or exposes the separate ledger through the legacy RenderedScenarioReport. A corrupted summary or ledger raises **existing `InvalidScenarioSummaryError`**. The displayed enum label `[ATTACK_FOOTPRINT]` remains **internal**; I3-D must separately review public Korean/English wording.

No quality adjective, causality ("because"), forcedness, safety, strategic plan or score appears in PLAYED templates. Existing EXCHANGE templates/status/English/data shape, full-detail behavior and byte-for-byte goldens stay unchanged.

## 5. Independent validator, failures and performance gates

**Preflight:** exact kind/target/one-ply/max_plies=1, lowercase canonical UCI on both sides, source≠destination, and suffix-rank shape only (suffix permits 7→8 or 2→1), matched by UCI regardless of SAN, **before** `ActivityLineAnalyzer` invocation. The adapter owns pawn kind, missing/incorrect promotion suffix and move legality; never parse FEN a second time. Illegal-but-well-typed ChessMove fails via the existing canonical chess legality path, not trusted string validation.

**Observed-line closure:** existing `_validate_observed()` re-checks initial position equality, frame counts, `position_id` anchors, exact played UCI and both delta endpoints, P4 derived features, P5 material/physical histories, activity frames, attacks and current-side legality. Preserve the same full check for both kinds. The same rules/facts/delta port instances used in MVP remain reusable at a *future* composition gate; I1 does not wire public `analyze_move`.

**Scenario closure:** kind-specific exact candidate-census/selection row matrix, `ScenarioSummary` detail/version pairing, zero focus timeline for PLAYED, complete physical participant refs, source resolver coverage, exact material count and changed property values. `validate_scenario_summary(summary)` must detect corruption by *full independent recomputation from retained observed line*, including wrong but equal-length candidate-key substitutions. No reduced "status flag" or trusted cached projection.

**Narrative closure:** presentation selector/renderer revalidates scenario; independently re-derives all included candidate ledger rows, exact dedup, rank/tie, cap and selected-key binding. Every selected sentence must have closed template, real source refs and exact match to the typed values; explicitly reject stale, injected, repeated or swapped sentences.

**Typed failure mapping:**

| Failure source | Outcome |
| --- | --- |
| Wrong kind/target, invalid budget/cardinality, malformed or noncanonical UCI, or target.move.uci != line[0].uci | `InvalidScenarioRequestError`, zero analyzer/engine calls |
| Illegal ChessMove in initial position | existing chess legality error, never a partial summary |
| Malformed retained structural/activity frame, physical history, source or summary | `InvalidScenarioSummaryError` or existing typed observation incompatibility, no output |
| Forged/tampered presentation candidate/ledger/sentence | existing `InvalidScenarioSummaryError`, no repaired or guessed prose |
| No *eligible* presentation observations | valid empty `digest`, complete core summary/accounting still retained |
| Need to report observation failure publicly | **I3-D decision**, not I1; v0.2 path unchanged |

No Stockfish calls, request_session changes, db, new LLM, caching shortcuts or scheduler. Benchmark replay, projection, full validation, ledger recomputation and digest rendering **separately** on 1-ply quiet/capture/promotion/castling/EP positions; the old 1-ply smoke (~17.7 ms projection/~19.9 ms render, replay excluded) is historical, not acceptance latency. Benchmark before implementation; report actual measurements without inventing a universal time SLA.

## 6. Independent I1-D corpus and mutation oracle (fixed before implementation)

All tests require independently authored expectations for **domain facts, candidate-key sets, included/excluded disposition, selected digest keys/template IDs/text, error types, and count of Stockfish calls**. Implementation-derived goldens do not count as oracle.

| Case | Independent assertion |
| --- | --- |
| D01 start position `e2e4` | one legal ply, exact physical mover, 21 accounting rows, no focus/snapshot, two digest entries at most, no strategic language |
| D02 quiet rook on an open file | factual geometrical/destination changes; "open file" does not imply benefit |
| D03 normal capture | one CAPTURE event; no capturer's duplicate ordinary MOVE; captured victim `CAPTURED` at frame 1 |
| D04 en passant | victim's **captured_square** differs from landing; both physical histories and all changed FILE_STATE candidates agree |
| D05 castling each side (K/Q) | king MOVE and rook CASTLING_ROOK are distinct physical events; canonical order and 2-cap |
| D06 quiet promotion and four underpromotions | mover retains base pawn identity; promoted role is factual, material counts are not an evaluation |
| D07 capture-promotion | CAPTURE and PROMOTION are distinct event keys, both source-linked and candidate-accounted |
| D08 pin created / pin removed by one participant | exact observed physical pin triple only; no hypothetical pins |
| D09 file state transitions | open / semi-open-white / semi-open-black / neither derived from pawn counts, not asserted as advantage |
| D10 pawn flag/supporter changes | affected physical subject inclusion and unselected nonparticipant accounting remain distinct |
| D11 off-turn snapshot bait | PLAYED produces **no** focus snapshots or cross-turn legal-action deltas; opponent action never fabricated as zero |
| D12 step vs endpoint duplicate | both core buckets retain their candidate key; presentation excludes exactly the endpoint copy with `SEMANTIC_DUPLICATE` |
| D13 cap overflow / multiway equal tier | canonical key and tie order fix exactly which 2 are included; every excluded eligible candidate uses `CAP_EXCEEDED` |
| D14 mismatched target / wrong kind / bool budget / empty or 2-ply line | typed preflight rejects before analyzer invocation |
| D15 invalid real move | chess legality error; no partial summary |
| D16 mutated summary | wrong version/detail kind, same-count-wrong-key, wrong actor, broken frame/source, altered reason/position and missing row all rejected |
| D17 EXCHANGE E01–E15 | exact `ScenarioSummary` and `RenderedScenarioReport` reproducibility plus golden English **byte-for-byte** against pre-I1 head |
| D18 legacy public MVP | `analyze_move` schema 0.2, P10/P11/P12 strings, `used_claim_ids`, error behavior and Stockfish call count identical on existing golden cases |

**Representative immutable FEN/UCI fixtures (the committed JSON contains all reviewed cases):**

| Fixture | Initial FEN | UCI | Oracle focus |
| --- | --- | --- | --- |
| D01 | `rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1` | `e2e4` | expected presentation first: `EVENTS/MOVE` for initial white pawn e2; second: `STEPS/ATTACK_FOOTPRINT` for same physical pawn, subject to independent source fact proof; STEP/ENDPOINT copies retained in core |
| D04 | `8/8/8/3pP3/8/8/8/4K2k w - d6 0 1` | `e5d6` | EP victim on d5, capturer lands d6, one capture event |
| D05 | `r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1` | `e1g1` and separately `e1c1` | distinct king/rook transition events |
| D06 | `4k3/P7/8/8/8/8/8/4K3 w - - 0 1` | `a7a8q`, `a7a8r`, `a7a8b`, `a7a8n` | physical promotion identity and exact material count |
| D07 | `1r2k3/P7/8/8/8/8/8/4K3 w - - 0 1` | `a7b8q` | one capture + one promotion event with separately resolvable sources |

The review/test author must independently resolve full typed `BasePieceRef`, every core candidate row, source refs and exact digest outputs, using the committed JSON as a read-only oracle; **never replace expected JSON values with implementation output**. The JSON currently pins crucial included/ledger keys and exact digest, not every source ref: I1 implementation must supply exhaustive reconciliation tests in addition to this design checker.

**Committed independent design corpus**: [`docs/legacy/corpus/played-transition-i1d-v1.json`](corpus/played-transition-i1d-v1.json) includes concrete FEN/UCI, base-square participants, core-included critical keys, selected/excluded presentation ledger assertions, exact digest keys/TemplateIds/sentences, and canonical PLAYED_STATUS event reference for D01–D13 and D19/D20 (including underpromotion/castling variants). [`docs/legacy/corpus/check_played_transition_i1d.py`](corpus/check_played_transition_i1d.py) validates the JSON ledger/key/cap/wording closure in `--schema-only` mode and uses python-chess in `--full` mode to check legal positions and independent board-geometry observations. **C1 full-census goldens:** D06-q/r/b/n and D13 also freeze an `exhaustive_one_ply_oracle` with **every** changed shared-fact/event/material core key, complete ranked presentation-eligible order, and a full disposition ledger with typed reasons/tiers. The enhanced `--full` checker derives and compares the **complete one-ply census** of these five critical cases independently from python-chess; it does not rely solely on critical-key subsets. For remaining cases the JSON pins a verified critical-key subset/digest; I1 implementation must still exhaustively derive complete source-backed candidates for all cases and compare EXCHANGE byte stability. D17/D18 are integration acceptance oracles against the actual pre-I1 baseline and cannot be certified by this corpus checker alone.

**Fresh review execution required:** `python docs/legacy/corpus/check_played_transition_i1d.py --schema-only` and `python docs/legacy/corpus/check_played_transition_i1d.py --full` under installed python-chess. Earlier independent review reported `--full` PASS for the pre-C1 checker; the **new exhaustive C1 oracle has not yet been independently executed**. **No full pytest/CI runs in this docs-only PR.** I1 implementation can run focused Linux/Windows-independent deterministic tests first, with a separately approved targeted real-Stockfish compatibility slice. No GitHub CI addition authorized.

## 7. Implementation seam and explicit STOP conditions

Intended edit boundaries after I1-D READY: `domain/analysis/scenario.py` (closed union/versions/new status/TemplateId); `services/position/scenario.py` (fixed kind dispatch/new policy/complete core projection); `services/position/scenario_renderer.py` (PLAYED-only renderer branch and presentation selector); focused unit/golden tests, fixtures and reviewed docs. Do **not** update `composition.py`, `application/analyze_move.py`, `contracts.py` or P8–P12.

- Keep existing EXCHANGE construction, reason ordering and status/render behavior identical, not merely semantically similar.
- Do not refactor shared private helpers across layers as a side effect; PR #30 L6 remains separately visible for I3. If such a refactor proves unavoidable, return for design review.
- No duplicate ontology, made-up relation/event keys, unbounded detail emission, scorer-based "importance", score-to-causality assertion or unreviewed user-facing API.
- A1 frozen `ScenarioRequest` fields retain field order; only additive closed target union/new-kind acceptance is proposed, with old EXCHANGE preserved.
- Do not assume a one-ply sample latency is a performance guarantee; do not bypass complete summary re-projection or source resolution.
- An independent design reviewer must return **READY** with the exact N1/N2 and detailed golden oracles adjudicated before code.

## 8. Questions to the independent reviewer

1. Is `PlayedMoveTarget(move: ChessMove)` and exactly-one-ply, max_plies=1 safe with current ChessMove validation and frame identities? Is any redundant check missing?
2. Does `ScenarioSummary.detail: ExchangeDetail | PlayedTransitionDetail` plus per-kind version binding preserve EXCHANGE's v1 data/repr/renderer bit-for-bit, including `Record._matches` union handling?
3. Does the source-verified event enumeration always supply a real source ref for `PLAYED_STATUS` on a legal move, including captures, castling and underpromotion?
4. Is exactly **21 accounting rows and no SNAPSHOTS/FOCUS_LOSSES** valid and fully provable under `AccountingRow`/summary validation? Does the shared property-key enumeration remain complete?
5. Are direct participants `P` correctly limited to mover/victim/castling rook while *all* supported remote changes (D19/D20) remain core INCLUDED, and are EP/castling/promotion physical histories sound?
6. Is the exact one-ply no-focus, no-cross-turn-legal-action policy enforced in source-domain and renderer?
7. Can step/endpoint semantic duplicates be identified by closed typed values with complete source provenance, and can rank/tie/cap and presentation exclusions be validated without changing core accounting?
8. Are `PLAYED_STATUS` and `PLAYED_CHANGE` templates and the **two-sentence digest cap** precise enough for golden fixtures, or must wording and per-family formatter be frozen more concretely in this same I1-D?
9. Do error authority, full re-projection, session isolation and v0.2/EXCHANGE regression prevent the new kind becoming an unjustified explanatory claim?
10. Does the **full** D06-q/r/b/n and D13 census correctly rederive FILE_STATE preceding MATERIAL_COUNTS and preserve other digest goldens? Does the `--full` checker pass after independent execution?

Return **READY / READY_WITH_CORRECTIONS / NOT_READY**, with specific blockers and test cases. No implementation, merge, or public integration follows automatically from reviewing this design.

---
**Proposed status on submission:** `I1_D_DESIGN_REVIEW_REQUESTED`, **not** `READY`.