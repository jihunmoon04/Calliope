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
| `PLAYED_TRANSITION` | **exact** `PlayedMoveTarget` | tuple, length **exactly 1**, equal to `target.move` | **exact int 1** | **exact** `PlayedTransitionDetail` | **`scenario_summary_v2`** |

All other pairs, booleans instead of integer budgets, strings instead of enum values, surrogate move objects, non-tuples, empty/multi-ply PLAYED lines and mismatching `target.move` are rejected as `InvalidScenarioRequestError` **before any activity-line/adapter call**. For PLAYED, the move is independently checked against the initial board by the canonical chess rules during one-ply replay; `ChessMove` type alone never grants legality. `request.initial.position_id` is the one true base anchor; no redundant editable "base id" in target.

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

## 3. Membership and five-bucket candidate census

Define initial physical set `B` from frame-0 BasePieceIdentityMap and participants `P` from the exact ply-1 `BoardDelta`. Both sets are independent of displayed `ScenarioEvent` filtering. Let `M` be the base mover, `V` the captured physical victim when present, and `R` the physically identified castling rook when present. `P={M,V?,R?}`. The participant file set `F` contains the **actual from and to files of those moved/captured physical pieces in frame 0/1**; for en passant include the victim's *captured_square* file and the capturer's landing file. A square may change occupancy without its file being marked advantageous.

For every property key in the existing shared catalog below, include a **scenario candidate** only when the typed values differ across frame 0 and frame 1. Candidate enumeration is over the complete `B` (and actual physical pin triples/ray directions) **before** policy membership selection. No hypothetical king/pin triples, no cartesian new relation space. Excluded candidates remain in the five-bucket ledger.

| Bucket | Complete candidate family and identity | PLAYED relevance predicate (scenario inclusion) |
| --- | --- | --- |
| STEPS | `StepKey(1,key)` for changed `PIECE_STATE, PAWN_FLAGS, PAWN_SUPPORTERS, FILE_STATE, ATTACK_FOOTPRINT, ATTACK_PARTITION, RAY_STATE, PIN_PRESENT` | selected if the shared key is relevant under per-family rules below |
| ENDPOINTS | same changed property domain, keyed by `PropertyKey` | **same relevance predicate**, independent bucket and key (even if duplicates narratively) |
| EVENTS | all real P5 capture and non-suppressed P5 transition event keys, chronological ply/kind/base order | select every actual event at ply 1 involving `P`; capture is always included and never double-counted as ordinary mover MOVE |
| SNAPSHOTS | **no** `SquareTarget` and no focus: supported-family row set is **empty** | `focus_timeline=()`; no `FOCUS_OCCUPANT/ATTACKERS/LEGAL_CAPTURES_NOW` snapshot is invented |
| AGGREGATES | all nonzero endpoint material changes as `CountKey(MATERIAL_COUNTS,color,piece_type)` | include every such whole-transition material count; `FOCUS_LOSSES` has no candidate/row |

Per-family inclusion (unchanged complete family/key order from shared `FactKind` and `_property_order`):

- **Subject** `PIECE_STATE, PAWN_FLAGS, PAWN_SUPPORTERS, ATTACK_FOOTPRINT, ATTACK_PARTITION, RAY_STATE`: select only if physical subject belongs to `P`. For PAWN families, enumerate only initial physical pawns applicable at either compared frame, including capture/promotion `NOT_APPLICABLE`; never turn NOT_APPLICABLE into false/zero.
- **FILE_STATE**: select if `FileKey.file in F`; factual state is pawn counts and derived **open / semi-open for WHITE/BLACK / neither**. Do not select unchanged files; do not imply rook control.
- **PIN_PRESENT**: select an actually observed pin triple if any physical `pinner/pinned/king` base identity belongs to `P`; enumerated triple universe is the union of observed pins across both frames. Both appearance and disappearance are admissible and exact.
- **Events**: capture event, promotion event, normal move and castling-rook event retain existing P5 event identity, source references and exact dedup suppression rule. For castling preserve both king and rook lifecycle events. No invented victim MOVE.
- **Material**: nonzero `MATERIAL_COUNTS` remains an exact count delta; a promotion can change both pawn and promoted piece counts without asserting a material win.
- **Legal actions**: there is **no `LEGAL_ACTION_DELTA`**. PLAYED has no focus square in I1-D, so it generates **no legal-action snapshot**. Adding a frame-local `LEGAL_ACTION_SNAPSHOT` later requires a focus-bearing reviewed kind/target extension with `side_to_move`; never diff across alternating turns.

The existing `CHANGED` set includes FOCUS geometric keys; PLAYED explicitly uses the **eight-family non-FOCUS subset above**, not the entire `CHANGED` tuple. The existing EXCHANGE `CHANGED` and `FOCUS` values/order remain untouched.

**Selection reasons:** retain existing typed `SelectionReason` values: `PARTICIPANT` for subject/event participation, `PARTICIPANT_FILE` for selected changed files, `PARTICIPANT_PIN` for selected actual pin triples, and `LINE_CONTEXT` for whole-transition material count context if existing aggregates require reason provenance. Maintain canonical enum declaration order. No new `SelectionReason` enum is necessary. Every included step/endpoint/event has its exact nonempty reason tuple; excluded scenario keys use existing `NOT_SCENARIO_RELEVANT`.

**Census order and cardinality:** one `AccountingRow` for each permitted (bucket,family) in the declared order (STEPS 8 families, ENDPOINTS same 8, EVENTS 4, AGGREGATES 1; total **21 rows**), including zero-count rows, and **zero SNAPSHOTS rows**. Recompute exact candidate/included/excluded key partitions, canonical order, source-backed values, all counts and reasons. No extra focus-loss CountFact, focus timeline, focus capture status or EXCHANGE-participant selection leaks. `selected_changes` uses 0→1 step changes, `endpoint_changes` uses 0→1 independently; `feature_histories` stores fully verified two-frame maximal runs for included non-PIECE_STATE step keys. Exact step/endpoint duplication is preserved **inside** scenario accounting; it is eliminated only by later narrative selection. One-ply persistent means actual 0→1 endpoint value differs, never a long-term assertion; there is no transient 0→1→0 sequence at I1.

> **Independent-review risk to confirm:** existing core `AccountingRow` checks allow an empty SNAPSHOTS row set, but current EXCHANGE construction always adds focus rows. Confirm kind-specific exact required-row validation, not a weakened global row-set check. Also verify that the generic `_Projection.properties` currently returns all FOCUS kinds except snapshot legal capture, so PLAYED's focus-free enumeration is genuinely restricted and complete.

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
  exclusion_reason: None | SEMANTIC_DUPLICATE | CAP_EXCEEDED
)
PlayedObservationSelection(
  candidates: tuple[PresentationCandidate,...],   # full auditable ledger
  selected_keys: tuple[(Bucket,CandidateKey),...], # only INCLUDE
)
```

The presentation wrapper/ledger does **not** introduce a second `FactKind`, SourceRef resolver, scenario truth-value schema, or P10 claim. IDs are keyed by the pair `(Bucket,CandidateKey)` inside this request; no synthetic root UCI or rendered text participates in identity.

**Core accounting vs presentation accounting:** core `NOT_SCENARIO_RELEVANT` stays in five-bucket rows. All and only core included keys appear exactly once in presentation ledger. Presentation-excluded candidates remain recorded with typed `SEMANTIC_DUPLICATE` or `CAP_EXCEEDED`. Do **not** add either to core `ExclusionReason` without a separate versioned core design.

### Semantic dedup and exact ordering

- Step and endpoint copies of the same typed changed `PropertyKey` with the same frame-0 and frame-1 exact source-backed values are semantically duplicates. **Keep STEPS and exclude ENDPOINTS as SEMANTIC_DUPLICATE**, with the canonical STEPS key as its duplicate anchor. This only applies to same-property duplicates; an EventKey is **never silently collapsed** with a PIECE_STATE fact or a material-count fact. Keep every candidate's original source references.
- All other candidates are different unless their typed family, base subject/key, exact before/after values, and precise frame/ply scope are identical. Compare typed values rather than rendered language or SAN. A missing/corrupt value fails before deduplication.
- Stable **family priority**, from earlier to later: event `CAPTURE` (tier 0), event `PROMOTION` (1), event `CASTLING_ROOK` (2), aggregate `MATERIAL_COUNTS` (3), event `MOVE` (4), change `PIN_PRESENT` (5), change `FILE_STATE` (6), change `PAWN_FLAGS` (7), change `PAWN_SUPPORTERS` (8), change `ATTACK_FOOTPRINT` (9), change `ATTACK_PARTITION` (10), change `RAY_STATE` (11), change `PIECE_STATE` (12). Ranking is **presentation order, not strength/importance proof**.
- Exact tie-break: `(priority_tier, _candidate_index(origin_key), bucket_order)`, with existing canonical `_candidate_index` over typed keys, and bucket order `STEPS < ENDPOINTS < EVENTS < AGGREGATES` when needed. **Do not sort opaque Python objects or rely on dict iteration**. This is a total order for distinct included typed candidate keys; duplicates already have unique `(bucket,key)`.
- Run **semantic dedup first**, then sort eligible unique candidates, select at most **2 observation sentences** per PLAYED request. Every other eligible candidate becomes EXCLUDE with reason **CAP_EXCEEDED**. This cap is independent of P11 max-three-Claim selection.
- If all candidates are excluded by the *core* scenario relevance policy, `selected_keys=()` and `digest=()`; no invented explanation. (A legal single ply should normally have at least one lifecycle event, but tests must allow the selector's empty-set contract.)
- Every included candidate contributes **exactly one** closed-template digest sentence with at least one source ref. Never generate two "before" and "after" digest sentences for one change candidate. Core selected changes still retain both frames in full detail.

**Output invariant:** `len(digest) == len(selected_keys) <= 2`, digest order equals selection order, no unknown `source_refs`, no selected key that is absent from complete candidate ledger. Validation recomputes candidates, exact semantic duplicate anchors, total order, cap decisions and the digest mapping. A mismatched count but same length is still a violation. Full scenario accounting is untouched by cap.

### Noncausal template catalog (N2)

For **PLAYED** only, introduce a closed set of kind-specific templates:

| New `TemplateId` | Output contract | Where used |
| --- | --- | --- |
| `PLAYED_STATUS` | "The supplied one-move line is `<uci>` from the anchored position." No quality assertion. | `RenderedScenarioReport.detail` only, with real ply-1 event source reference |
| `PLAYED_CHANGE` | Exactly one bounded, before→after *typed fact* sentence (frame 0 vs 1, subject/key named, both states factual; no evaluated adjectives). A closed formatter handles each of the eight shared changed-fact families, including `NOT_APPLICABLE`. | `digest` only when selected |
| Existing `CAPTURE_EP`, `CAPTURE_NORMAL`, `PROMOTION`, `MOVE`, `CASTLING_ROOK` | Reuse the currently validated event formatter `_event`, including castling king wording. | `digest` only when selected |
| Existing `MATERIAL_COUNTS` | Use current count-delta formatter, never compensation/advantage phrasing. | `digest` only when selected |

The exact public-facing English strings of `PLAYED_CHANGE` must be **frozen as a closed, deterministic per-family catalog in I1-D review**; proposed canonical template is:

```text
"In the supplied one-move line <UCI>, <typed subject/key> changes from
 <typed fact at frame 0> to <typed fact at frame 1>."
```

The formatter values are strictly derived from existing typed `Fact` payloads and their source refs; no free-text renderer input or ad-hoc LLM language. For `PIECE_STATE`, name initial base piece and squares, including captured; pawn flags print exact isolated/doubled/passed true/false or not applicable; `FILE_STATE` prints pawn counts and derived open/semi-open-for-color/neither; `PIN_PRESENT` names keyed physical triplet and boolean; `RAY_STATE` explicitly lists visible squares and blocker physical identities; `ATTACK_FOOTPRINT` and `ATTACK_PARTITION` explicitly say **geometric**. No "improved", "good", "safe", "forces", "wins", or "because".

### Closed PLAYED_CHANGE state formatter (proposed golden grammar)

The `PLAYED_CHANGE` envelope is **exactly**:

```text
In the supplied one-move line {uci}, {label} [{family}]: {state_before} -> {state_after}.
```

- `uci`: `request.supplied_line[0].uci`, unchanged lowercase canonical notation.
- `family`: the exact shared `FactKind.value`, no translated or human-inferred synonym.
- `label`: `piece initially on {base_square}` for `SubjectKey/RayKey`; `file {a-h}` for `FileKey`; `absolute pin (pinner={base_square}, pinned={base_square}, king={base_square})` for `PinKey`.
- `state_before` and `state_after` are independently formatted *existing* typed values from frames 0 and 1; the renderer does not consult Stockfish or a prose source.

| Shared fact kind | Exact `state` grammar and ordering |
| --- | --- |
| `PIECE_STATE` | `captured` or `{color} {current PieceType.value} on {current square}` |
| `PAWN_FLAGS` | `not applicable` or `isolated={true/false}, doubled={true/false}, passed={true/false}`, in that order |
| `PAWN_SUPPORTERS` | `not applicable` or `geometric pawn supporters=({base squares in canonical order})`; empty tuple prints `()` |
| `FILE_STATE` | `white_pawns={int}, black_pawns={int}, state={open / semi-open for white / semi-open for black / neither}` |
| `ATTACK_FOOTPRINT` | `not applicable` or `geometric squares=({canonical square list})`; empty `()` |
| `ATTACK_PARTITION` | `not applicable` or `geometric empty=({squares}), friendly=({squares}), enemy=({squares})`; each list canonical |
| `RAY_STATE` | `not applicable` or `visible=({ray visible squares in ray order}), occupants=({color/type/current square/base square in ray order})`; one physical identity per occupant |
| `PIN_PRESENT` | exact `true` or `false`; the triplet in `label` is a physical identity, not a new inferred pin |

Canonical tuples use ASCII `, ` separators, explicit parentheses, and no extra free-text item; booleans are lowercase. `NOT_APPLICABLE`, `CAPTURED` and `EMPTY` are distinct, and the supported value mapping is exact by `FactKind`. No generic `repr()` of unvalidated domain values, no type-driven fallback. `PLAYED_STATUS` is exactly `In the supplied one-move line, the played move is {uci}.` with at least one actual ply-1 source ref. The status uses no evaluation words and is retained only in internal `detail`.

The reviewer should treat the formatting table and punctuation as proposed frozen goldens. If any exact value grammar cannot be implemented without an unsupported type/branch, return READY_WITH_CORRECTIONS before I1 implementation.

This is a **new** PLAYED renderer branch; **do not modify EXCHANGE templates, status, digest contents/order, `RenderedScenarioReport` field layout, source strings or full-detail length**. PLAYED `detail` consists of exactly **one** `PLAYED_STATUS` sentence, not a 1,800-sentence detailed dump; all observations remain in the source-linked `ScenarioSummary` / ledger. `PLAYED_STATUS` is **not** counted against the capped digest and must not be appended to a future public observational section by default. The two-sentence cap applies to digest only.

Review STOP if the exact English catalog cannot be uniquely rendered from the closed values. In that case, the reviewer must request a concrete correction **before** marking I1-D READY; the implementation cannot fill unspecified wording with improvisation.

## 5. Independent validator, failures and performance gates

**Preflight:** exact request-kind/target/line/budget shape and base move consistency **before** `ActivityLineAnalyzer` invocation. Illegal-but-well-typed ChessMove fails via the existing canonical chess legality path, not trusted string validation.

**Observed-line closure:** existing `_validate_observed()` re-checks initial position equality, frame counts, `position_id` anchors, exact played UCI and both delta endpoints, P4 derived features, P5 material/physical histories, activity frames, attacks and current-side legality. Preserve the same full check for both kinds. The same rules/facts/delta port instances used in MVP remain reusable at a *future* composition gate; I1 does not wire public `analyze_move`.

**Scenario closure:** kind-specific exact candidate-census/selection row matrix, `ScenarioSummary` detail/version pairing, zero focus timeline for PLAYED, complete physical participant refs, source resolver coverage, exact material count and changed property values. `validate_scenario_summary(summary)` must detect corruption by *full independent recomputation from retained observed line*, including wrong but equal-length candidate-key substitutions. No reduced "status flag" or trusted cached projection.

**Narrative closure:** presentation selector/renderer revalidates scenario; independently re-derives all included candidate ledger rows, exact dedup, rank/tie, cap and selected-key binding. Every selected sentence must have closed template, real source refs and exact match to the typed values; explicitly reject stale, injected, repeated or swapped sentences.

**Typed failure mapping:**

| Failure source | Outcome |
| --- | --- |
| Wrong kind/target, invalid budget/cardinality, target.move != line[0] | `InvalidScenarioRequestError`, zero analyzer/engine calls |
| Illegal ChessMove in initial position | existing chess legality error, never a partial summary |
| Malformed retained structural/activity frame, physical history, source or summary | `InvalidScenarioSummaryError` or existing typed observation incompatibility, no output |
| Forged/tampered presentation candidate/ledger/sentence | typed internal presentation validation error to be declared and tested in I1; no repaired or guessed prose |
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
| D04 en passant | victim's **captured_square** differs from landing; both physical histories and file set `F` agree |
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

**Concrete initial fixtures for independent golden creation (verified legality is a required gate, not claimed by this document):**

| Fixture | Initial FEN | UCI | Oracle focus |
| --- | --- | --- | --- |
| D01 | `rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1` | `e2e4` | expected presentation first: `EVENTS/MOVE` for initial white pawn e2; second: `STEPS/ATTACK_FOOTPRINT` for same physical pawn, subject to independent source fact proof; STEP/ENDPOINT copies retained in core |
| D04 | `8/8/8/3pP3/8/8/8/4K2k w - d6 0 1` | `e5d6` | EP victim on d5, capturer lands d6, one capture event |
| D05 | `r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1` | `e1g1` and separately `e1c1` | distinct king/rook transition events |
| D06 | `4k3/P7/8/8/8/8/8/4K3 w - - 0 1` | `a7a8q`, `a7a8r`, `a7a8b`, `a7a8n` | physical promotion identity and exact material count |
| D07 | `1r2k3/P7/8/8/8/8/8/4K3 w - - 0 1` | `a7b8q` | one capture + one promotion event with separately resolvable sources |

The review/test author must resolve full typed `BasePieceRef`, source refs, exact core candidate rows and expected rendered strings **independently** using the reviewed chess domain API; the listed UCI/FEN fixtures are not substitutes for these oracles.

Reviewers must require a small **pre-implementation golden corpus** with real FEN, UCI, expected physical `BasePieceRef` and candidate/ledger identities for D01–D13; the table above is the **required matrix**, not a substitute for that executable oracle. Freeze those fixtures in I1-D before I1 implementation; negative mutation tests for every listed invariant are mandatory. If any test needs an illegal position or non-existent scenario fact, revise the design rather than silently changing the expected result.

**No full pytest/CI runs in this docs-only PR.** I1 implementation can run focused Linux/Windows-independent deterministic tests first, with a separately approved targeted real-Stockfish compatibility slice. No GitHub CI addition authorized.

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
5. Are participants `P` and changed-file set `F` defined precisely enough for EP, captured victim, castling rook, promotion and pin involvement, without leaking EXCHANGE membership rules?
6. Is the exact one-ply no-focus, no-cross-turn-legal-action policy enforced in source-domain and renderer?
7. Can step/endpoint semantic duplicates be identified by closed typed values with complete source provenance, and can rank/tie/cap and presentation exclusions be validated without changing core accounting?
8. Are `PLAYED_STATUS` and `PLAYED_CHANGE` templates and the **two-sentence digest cap** precise enough for golden fixtures, or must wording and per-family formatter be frozen more concretely in this same I1-D?
9. Do error authority, full re-projection, session isolation and v0.2/EXCHANGE regression prevent the new kind becoming an unjustified explanatory claim?
10. Are D01–D18 golden/mutation expectations sufficient **as a design freeze**, or does the reviewer require concrete FEN/UCI/predicted outputs in this PR before READY?

Return **READY / READY_WITH_CORRECTIONS / NOT_READY**, with specific blockers and test cases. No implementation, merge, or public integration follows automatically from reviewing this design.

---
**Proposed status on submission:** `I1_D_DESIGN_REVIEW_REQUESTED`, **not** `READY`.