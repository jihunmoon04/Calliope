# EXCHANGE rules for the common scenario summary — design A1

Status: A1_READY / A3_CORRECTED_AWAITING_RE_REVIEW.
Independent review of PR #29 c99d6a3: READY; F1-F7 accepted.
Shared contract: [scenario-line-summary-design.md](scenario-line-summary-design.md).
Base: main dffd55013834d9f8f824f3913ddfa3e7aaf2ff76.
Internal implementation evidence: [scenario-summary-a2-implementation.md](scenario-summary-a2-implementation.md).

## 1. Purpose and evidentiary limit

For a supplied legal line and focus square, identify captures related to that
square, physical participants, selected changes, endpoint differences and transient
histories. Relevance to the question does not prove chess importance, move quality,
safety, compensation, forcedness or causality. No generated replies, early stopping,
settled-exchange detector, weights or engine calls are added.

The complete line is observed once by ActivityLineAnalyzer. The common document
owns request validation, replay, shared values, source resolution, accounting,
compression, validation and the closed renderer catalog. This policy owns only
EXCHANGE membership, inclusion predicates, reasons and status/loss projections.

## 2. Input

Use ScenarioRequest(kind=ScenarioKind.EXCHANGE, target=SquareTarget(focus_square),
initial=initial, supplied_line=moves, max_plies=64) with ScenarioLineAnalyzer.
No exchange-only request/service/renderer entry is introduced. Shared section 2
defines exact types, standard chess, pre-observation refusal, integer 1..256 budget
and the allowed empty line. Existing illegal replay failures propagate without a
partial summary. No public schema, composition, adapter or P4-P12 changes.

## 3. Physical membership and FOCUS_VICTIM_SQUARE (F1)

Focus capture iff the actual P5 capture landing_square equals focus_square.
P = union of physical capturers and victims of these focus captures, over the
ENTIRE supplied line. Resolve initial identities via structural piece_histories.
NO_FOCUS_CAPTURE iff this set of capture events is empty, otherwise
FOCUS_CAPTURES_OBSERVED. Neither status asserts completion or impossibility.

FOCUS_VICTIM_SQUARE applies iff captured_square equals focus_square AND
landing_square differs from focus_square. Valid standard P5 captures make this
an en-passant case. It is included as a related non-focus capture, with both
LINE_CONTEXT and FOCUS_VICTIM_SQUARE reasons. Its victim/capturer do not become
participants through this rule. It contributes nothing to focus_capture_losses.
It MUST be rendered in the digest using the common CAPTURE_EP template, naming
both landing and victim square; merely reporting empty focus occupancy is insufficient.
E05 therefore states that no capture landed on d5 but the d5 pawn was removed
by en passant landing on d6.

All non-focus captures remain in other_capture_events as chronological line context.
Focus/other events partition the common capture event ids; related victim events
remain in the other partition, not a new third partition. Multiple matching reasons
do not duplicate an event. The rules do not infer a contiguous or forced exchange.

## 4. Output and provenance

ScenarioSummary and ExchangeDetail use ONLY the shared vocabulary in common
sections 4-6. This document defines no alternate SourceRef, FactKind/value table
or optional selectors. Mixed-source values require the full common reference bundles:
for example focus occupant/attackers require square access plus physical histories;
rays require the ray plus source/occupant histories.

ExchangeDetail retains status, P, focus_capture_events, other_capture_events,
whole_line_material_changes and focus_capture_losses. Physical subjects are
BasePieceRefs (initial type/color/square); current types and squares are values.
Promotion preserves physical identity. A captured identity never becomes a different
same-type piece. Full observations remain available for facts excluded by this policy.

## 5. Closed selection and accounting

This table is the complete v1 EXCHANGE instantiation of shared candidate domains.
B = ALL initial physical identities. D(a,b) is an adjacent pair for steps or the
initial/final pair for endpoints. P is the global physical set from section 3,
not a set recomputed "in its frame". N is line length.

Definitions:
- P(b): base identity b belongs to P, even before its later focus capture.
- PinP(k): at least one of the physical pinner/pinned/king identities belongs to P.
  Apply whether that pin is present or absent in either compared frame.
- FileP(f,a,b): file f contains a pawn whose base identity belongs to P in frame a
  OR frame b. Captured/promoted subjects are not pawns there. For endpoints use
  frames 0,N only, never files occupied solely in middle frames.
- Changed candidates exist iff the resolved typed before/after values differ.
  All sets below enumerate independently of inclusion; a false inclusion predicate
  means NOT_SCENARIO_RELEVANT, not no candidate.
- Matching reasons are combined exactly, without duplication.

| Family / candidate range | Inclusion predicate | Bucket / views | Included reasons | Accounting location |
| --- | --- | --- | --- | --- |
| CAPTURE: every actual P5 capture at each ply | Always; landing-focus / victim-focus rules add reasons | event | LINE_CONTEXT; plus FOCUS_CAPTURE if landing=focus; plus FOCUS_VICTIM_SQUARE if victim=focus and landing!=focus | events.CAPTURE |
| MOVE: every P5 MOVE except capturer MOVE suppressed by same-step capture | P(subject) | event | PARTICIPANT | events.MOVE |
| PROMOTION: every P5 PROMOTION, including capture-promotion | P(subject) | event | PARTICIPANT | events.PROMOTION |
| CASTLING_ROOK: every P5 CASTLING_ROOK | P(rook) | event | PARTICIPANT | events.CASTLING_ROOK |
| PIECE_STATE: every b in B, compare PieceRef/CAPTURED | P(b) | changed step and endpoint; no feature history | PARTICIPANT | steps.PIECE_STATE / endpoints.PIECE_STATE |
| FOCUS_OCCUPANT: requested square only | Always | snapshots plus changed steps/endpoints/history | FOCUS_SQUARE | snapshots.FOCUS_OCCUPANT / steps.FOCUS_OCCUPANT / endpoints.FOCUS_OCCUPANT |
| FOCUS_ATTACKERS: requested square's complete color-separated geometric lists | Always | snapshots plus changed steps/endpoints/history | FOCUS_SQUARE | snapshots.FOCUS_ATTACKERS / steps.FOCUS_ATTACKERS / endpoints.FOCUS_ATTACKERS |
| FOCUS_LEGAL_CAPTURES_NOW: current-side captures landing on requested square, labelled side_to_move | Always | N+1 snapshots only, never a delta/history | FOCUS_SQUARE | snapshots.FOCUS_LEGAL_CAPTURES_NOW |
| PAWN_FLAGS: each b in B pawn in either D(a,b); otherwise NOT_APPLICABLE | P(b) | changed step/endpoint/history | PARTICIPANT | steps.PAWN_FLAGS / endpoints.PAWN_FLAGS |
| PAWN_SUPPORTERS: same pawn domain; supporters mapped to base identities | P(b) | changed step/endpoint/history | PARTICIPANT | steps.PAWN_SUPPORTERS / endpoints.PAWN_SUPPORTERS |
| FILE_STATE: all eight files | file=focus file OR FileP(file,a,b) | changed step/endpoint/history | FOCUS_FILE for first predicate; PARTICIPANT_FILE for second | steps.FILE_STATE / endpoints.FILE_STATE |
| ATTACK_FOOTPRINT: all b in B, geometric target tuple or NOT_APPLICABLE when captured | P(b) | changed step/endpoint/history | PARTICIPANT | steps.ATTACK_FOOTPRINT / endpoints.ATTACK_FOOTPRINT |
| ATTACK_PARTITION: all b in B, empty/friendly/enemy target tuples or NOT_APPLICABLE | P(b) | changed step/endpoint/history | PARTICIPANT | steps.ATTACK_PARTITION / endpoints.ATTACK_PARTITION |
| RAY_STATE: each b in B with every direction supported by its type in either D(a,b); missing state NOT_APPLICABLE | P(b) | changed step/endpoint/history | PARTICIPANT | steps.RAY_STATE / endpoints.RAY_STATE |
| PIN_PRESENT: every physical triple actually observed anywhere in 0..N, bool at D(a,b) | PinP(key) | changed step/endpoint/history | PARTICIPANT_PIN | steps.PIN_PRESENT / endpoints.PIN_PRESENT |
| MATERIAL_COUNTS: all nonzero initial/final type-count deltas, each color and non-king type | Always | aggregate | LINE_CONTEXT | aggregates.MATERIAL_COUNTS |
| FOCUS_LOSSES: nonzero victim CURRENT color/type counts among landing-focus captures | Always | aggregate | FOCUS_CAPTURE | aggregates.FOCUS_LOSSES |

All changed step/endpoint rows exclude unchanged pairs BEFORE inclusion accounting;
all event candidates exist BEFORE participant filtering. Counts and exact key
sets are independent per bucket/family, including zero rows. No event is counted
as a changed property. A2 validator must recompute all keys, not just length sums.
Snapshot candidates are exactly N+1 per focus family. Histories have deterministic
derived keys, not a second included/excluded selection count.

Mentioning a supporter/blocker/pinner/king as a selected value does not recursively
include its other properties. Geometric attackers do not certify legal recaptures.
Location-only pawn movement does not change flags/supporter identities. Capture or
promotion ends its pawn feature track with NOT_APPLICABLE, not false flags.

E14's a2 MOVE is an excluded events.MOVE key at ply 3. Its changed PIECE_STATE,
footprint and partition keys are excluded in steps/endpoints where unequal.
E13's c4 PAWN_FLAGS step/endpoint keys are excluded despite genuine structural change.
E12's pin uses physical key (base a8 rook, base e2 knight, base e1 king); P contains
the knight, so both appearance and disappearance steps are selected regardless
of the king/rook being nonparticipants. No nonexistent endpoint pin delta is emitted.

## 6. Compression and material

Apply common section 5: full tracks for keys selected at some step, including
labelled context at other steps; endpoint selection uses its own D(0,N) predicate.
The temporary-track count includes exactly selected tracks with equal endpoint
values and a differing interior value, once per property key. E12 pin values
[false,true,false,false,false] form one temporary track and zero endpoint pin changes.

whole_line_material_changes is structural initial/final counts by color/type;
focus_capture_losses counts victims' CURRENT types at landing-focus captures.
Never label either a weighted score or settled exchange balance. In E06 a base
pawn becomes a queen and is captured: focus losses include that queen, while the
endpoint delta is one fewer white pawn. FOCUS_VICTIM_SQUARE adds no focus losses.

All actual captures and selected participant lifecycle events retain chronological
ply; quiet intervening moves do not stop selection or imply one continuous exchange.
No arbitrary top-k, truncation, importance ranking or causal explanation is added.

## 7. Required rendering and F6/F7

Use the common closed TemplateId catalog ONLY. Digest must include:
status/focus; every focus capture; every FOCUS_VICTIM_SQUARE capture explicitly
naming EP landing and victim square; every selected participant PROMOTION;
every nonzero whole-line material delta;
all selected endpoint facts; and the exactly defined temporary-track count with
references to detail. Detail retains all selected steps and complete tracked runs.
Digest events use their canonical chronological order; capture-promotion retains
capture then promotion at that ply before later recapture. An earlier quiet
participant promotion is also included; nonparticipant promotions remain excluded.

E12 wording is temporal: "After ply 1, the pin is observed; after ply 2 it is not
observed." No "king move releases the pin" or king motion assertion is inferred
from the selected false value. The king MOVE remains excluded. Corpus frame 3
also explicitly verifies absence.

For castling with a participant rook and nonparticipant king, select only
CASTLING_ROOK, exclude king MOVE and label e1g1 as step castling context. The
closed template names the rook's actual from/to squares; it never treats e1g1
as the rook's own move. E15 freezes this case. References resolve to the selected
rook transition and its before/after history, without requiring selected king MOVE.
For king-only participation, the selected MOVE uses the closed king-castling
template branch with the actual parent UCI; the nonparticipant rook event stays excluded.

Templates use typed slots, no arbitrary text. Entire fixed catalog and each allowed
branch are semantically reviewed; tests reject unknown template ids or slot types.
A word blacklist is supplementary. Korean corpus examples are target semantics,
not a promise of a Korean renderer in the first implementation.

## 8. Acceptance and delivery

| Case | Mandatory result |
| --- | --- |
| Empty / no focus capture | N+1 snapshots, empty participants, NO_FOCUS_CAPTURE |
| EP captured-square focus, different landing (E05) | LINE_CONTEXT + FOCUS_VICTIM_SQUARE, required EP digest, no participants/losses from this event |
| Capture-promotion / recapture (E06) | Separate capture/promotion, one physical history, current loss versus endpoint counts |
| Temporary pin (E12) | Both step keys and one temporary history; no endpoint pin candidate; no causal king wording |
| Unrelated pawn (E13/E14) | Exact excluded property/event keys in their proper accounting buckets |
| Participant rook castles (E15) | CASTLING_ROOK included, king MOVE excluded, root UCI labelled context |
| Missing or extra facts / sources / counts | Typed refusal, even if cardinalities or prose appear plausible |
| Mixed-source value | All mandated observation + history refs; corrupted/omitted history refused |
| Templates | Closed catalog/slots, per-sentence resolving refs, no unsupported semantic assertion |

A1: independently re-review common contract, EXCHANGE policy and structured corpus;
accept all corrections before A2. A2: shared records/validator, policy, compression
and internal renderer with no extra replay/engine calls. A3: independent implementation
review, focused regression and 0/1/64/256-ply projection/render cost evidence; merge
only after READY. Public integration, additional kinds, alternate-line comparison,
causal verification, localization and LLM remain later packets.
