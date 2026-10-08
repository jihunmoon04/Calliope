# EXCHANGE rules for the common scenario summary — design A1

Status: DRAFT_AWAITING_INDEPENDENT_DESIGN_REVIEW. This is the EXCHANGE policy for
[scenario-line-summary-design.md](scenario-line-summary-design.md), which owns the
single request, analysis, validation and rendering contract. Implementation must
wait for independent design review and contract corrections.
Base: main @ dffd55013834d9f8f824f3913ddfa3e7aaf2ff76.
Predecessors: positional_v1 and activity_v1, independently reviewed READY.

## 1. Purpose and limits

Given an initial position, a supplied legal line and a focus square, answer:
which captures land on this square, which physical pieces participate, what changes
along the line, and what remains at its supplied endpoint?

Selection means relevance to this request, not chess importance. An included fact is
not proof of a reason for move quality. This packet assigns no numerical importance,
material weights, engine evaluations, safety, compensation, causality or forced-play
claims. A single capture qualifies as an observed focus capture; the word exchange
in the request does not assert a recapture or a completed sequence.

The full supplied line is replayed once by ActivityLineAnalyzer. No generated replies,
automatic continuation, quiet-move stop, settled-exchange detector or early termination
is added. End kind retains existing PROVIDED_LINE_END / CHECKMATE semantics, including
existing draw-adjudication limits. Normal engine recommendations and user/LLM lines
use the same input contract; origin does not change evidentiary strength.

## 2. Input and service boundary

ScenarioRequest(kind=ScenarioKind.EXCHANGE, target=SquareTarget(focus_square),
                initial=initial, supplied_line=moves, max_plies=64)
ScenarioLineAnalyzer(activity_lines).analyze(request) -> ScenarioSummary

Only standard chess. Validate focus_square and budget before any observation.
Budget: exact int (not bool), 1..256, len(moves) <= max_plies; empty line is allowed.
Invalid request raises the common Calliope-owned InvalidScenarioRequestError.
Existing replay and observation failures propagate without partial output.
No other public method accepts a supposedly trusted ActivityLineAnalysis.
Private _summarize_observed_line validates frame/step counts, consecutive structural
bindings, position ids, both definition versions, P4 anchors, and identity histories
against frame pieces and P5 correspondences. It then derives every selected value
from those anchored observations; it does not trust caller-provided selected facts.
This is a consistency boundary, not an independent reconstruction of P4 truth.

No ChessRulesPort, TacticalObservationPort, engine, P4/P5/P6 protocol, adapter,
composition, package export or public schema changes. Keep new service out of the
services.position package exports while the known shared-identity import issue remains.
No replay or adapter calls inside summary projection or rendering.

## 3. Exact focus membership

A focus capture is a P5 CaptureDelta whose landing_square equals focus_square.
Select all such captures anywhere in the supplied line, in chronological order.
Do not infer a contiguous exchange chain or merge distant events into one transaction.
Every event retains ply, UCI, capturer base identity, victim base identity, before/after
PieceRefs, captured_square, landing_square and is_en_passant.

En passant is intentionally classified by landing square, not victim square. Both
squares are rendered, so an e.p. capture landing on d6 and removing a pawn on d5
belongs to a d6 request, not a d5 request. The snapshot ep square alone proves nothing.
Capture-promotion is one capture event plus a promotion event with the same ply;
identity follows the physical pawn through promotion, while current type changes.

Participants = union of physical capturers and victims in focus captures only.
Resolve identities exclusively from structural piece_histories at before/after frames.
For every frame build a unique PieceRef -> BasePieceRef inverse. Captured identities
remain available for timeline lookup and never become a different same-type piece.
Focus occupants/attackers without a focus capture are not capture participants.
Zero focus captures is a valid result with empty participant set and explicit status
NO_FOCUS_CAPTURE; otherwise status FOCUS_CAPTURES_OBSERVED. Neither means completed.

## 4. Output and provenance

Use frozen typed records and canonical tuples. Proposed vocabulary:

- ScenarioSummary: common request, observed_line, events, focus_timeline,
  selected_changes, endpoint_changes, feature_histories, selection_accounting.
- ExchangeDetail: exchange_rules_v1, status, focus_capture_events,
  other_capture_events, participants, whole_line_material_changes, focus_capture_losses.
  Capture collections reference partitions of common event ids, not duplicate facts.
- SourceRef: frame_index (0..N), position_id, closed SourceKind enum,
  optional base identity / square / file / ray direction as required by kind.
- SelectedChange: closed FactKind enum, typed before/after values, frame refs,
  subject key and nonempty sorted SelectionReason tuple.
- ParticipantSummary: base identity and references to its N+1 history entries.
- FeatureHistory: subject/property key and maximal contiguous runs of equal values,
  each run with inclusive start/end frame indices and endpoint SourceRefs.

SourceKind is a closed set: CAPTURE, TRANSITION, MATERIAL, PIECE_HISTORY,
SQUARE_ACCESS, PAWN_STRUCTURE, FILE_STRUCTURE, PIECE_ACTIVITY, SLIDER_RAY,
ABSOLUTE_PIN. Step records use their ply and before/after frame references.
Resolvers check kind-specific selectors, index range and exact position binding.
No string paths into arbitrary objects, free-form fact payloads or prose as evidence.
FactKind/value pairs are closed as follows (new records carry source refs):

| FactKind | Value type |
| --- | --- |
| PIECE_STATE | PieceRef or typed CAPTURED sentinel |
| FOCUS_OCCUPANT | (BasePieceRef, PieceRef) or EMPTY sentinel |
| FOCUS_ATTACKERS | Canonical tuple of (BasePieceRef, PieceRef), separated by color |
| FOCUS_LEGAL_CAPTURES_NOW | (side_to_move, canonical current LegalCapture tuple); snapshot-only, never diffed |
| PAWN_FLAGS | (isolated: bool, doubled: bool, passed: bool) or NOT_APPLICABLE |
| PAWN_SUPPORTERS | Canonical tuple of BasePieceRef or NOT_APPLICABLE |
| FILE_STATE | FileStructure (counts; open/semi-open derived) |
| ATTACK_FOOTPRINT | Canonical square tuple or NOT_APPLICABLE |
| ATTACK_PARTITION | Three disjoint canonical square tuples or NOT_APPLICABLE |
| RAY_STATE | SliderRay plus occupant base identities or NOT_APPLICABLE |
| PIN_PRESENT | bool, with subject key (pinner,pinned,king) base identities |

CAPTURED, EMPTY and NOT_APPLICABLE are distinct enum sentinels. Event records for
capture and promotion carry P5 typed payloads, not generic feature values. Material
views carry canonical MaterialChange tuples or typed victim-count records. No further
FactKind/value alternatives may be invented during implementation without a contract
update. Piece state tracks include motion as event/endpoint data; feature histories
compress the remaining property kinds.

All records validate local invariants with typed errors: canonical squares/keys,
nonnegative valid indices, no duplicate events/reasons, before != after for changes,
valid enum/value combinations. Summary factory validates cross-record membership,
source resolution and equality of projections. Exported frozen records alone do not
certify arbitrary caller-constructed summaries; renderer performs summary consistency
validation before returning text. Invalid summary raises a new
InvalidScenarioSummaryError, never silent omission. The common design additionally
requires exact projection completeness, not just reference existence or equal counts.

## 5. Selection rules — relevance, not salience

All selections are derived deterministically over the completed observed line.
Participants discovered late may select observations in earlier frames; this is
retrospective description, never a prediction available at the starting position.

| Fact family | Include when | Selection reason |
| --- | --- | --- |
| Focus captures | Landing equals focus square | FOCUS_CAPTURE |
| Other captures | Any other actual P5 capture in line | LINE_CONTEXT |
| Whole-line material | All nonzero structural endpoint type-count deltas | LINE_CONTEXT |
| Focus occupancy/attackers/current-side captures | Every frame at focus square, even without capture; captures retain side_to_move | FOCUS_SQUARE |
| Participant lifecycle | Movement, capture or promotion of a participant at any ply | PARTICIPANT |
| Pawn structure | A participant is a pawn in either adjacent frame | PARTICIPANT |
| File structure | Changed file is focus file or occupied by a pawn participant in either adjacent frame | FOCUS_FILE / PARTICIPANT_FILE |
| Attack footprint | Physical subject is a participant and value changes | PARTICIPANT |
| Slider ray | Physical source is a participant and its ray changes | PARTICIPANT |
| Absolute pin | Either pin's pinner, pinned piece or king is a participant in its frame | PARTICIPANT_PIN |

No recursively expanded relation graph. A participant's supporter or blocker is named
as the value of its selected fact; that piece's other facts are not selected merely
because it was mentioned. Focus attackers are geometric P4 attackers and are explicitly
labelled; their count is never a legal recapture count.

Select per-subject pawn flags and supporter identities through before/after identity
maps. Mere pawn movement with unchanged flags/support identities is not a structural
change. Pawn capture/promotion ends the pawn-structure track with typed NOT_APPLICABLE,
not a fabricated false flag. Pins are keyed by physical (pinner,pinned,king) identities.
Ray tracks are keyed by (physical source,direction); non-slider/captured state is
NOT_APPLICABLE. Replacing a same-type pinned piece is therefore a distinct pin.
Attack footprints compare geometry; occupancy-class changes are separate values.
Compare full ray geometry/occupants and record blocker physical identities, so relocation
of the same blocker is not described as a replacement. No invented line-opening claim.

Step selections only contain changed values; zero-change frames remain in focus timeline.
A fact matching several reasons is stored once with all matching reasons.
Selection accounting, per implemented family, records changed candidates, included and
excluded counts; included + excluded = candidates. Full anchored observations remain
available to inspect omissions. Counts are descriptive, not importance scores.
Full legal-action fields remain accessible through observed_line. The focus timeline
alone retains current-side legal captures on the focus square as labelled snapshots.
No legal-action field is diffed: changing side to move changes what was measured.

## 6. Compression and material accounting

Three views are distinct and share the same anchored data:

1. Event timeline: every actual capture and participant lifecycle event in ply order.
2. Endpoint changes: selected subject/property values at frame 0 versus frame N,
   retaining only unequal values. Membership uses the same participant set; participant
   files at endpoints use focus file plus pawn participant files at frames 0 and N.
3. Feature histories: all selected tracked properties as maximal equal-value runs,
   including first appearance, disappearance and reversals. A temporary pin that ends
   absent has no endpoint delta but remains in its history. Do not call it causal.

No arbitrary top-k, character-budget deletion or suppression of temporary changes.
Canonical ordering is chronological for events; base-square board order/color/type,
property enum order, square board order, file a..h and (df,dr) order for feature keys.
A zero-change supplied line produces empty changes, not fabricated improvement.

whole_line_material_changes is the existing endpoint count delta by color/type,
including promotion. focus_capture_losses is a separate count of victims' CURRENT
color/type at their capture, classified only by landing. Other captures and promotions
can change whole-line totals. Never label focus losses as the net material result of
an exchange, and never subtract piece counts of different types into a score.
Promoted pawn -> queen -> captured queen therefore records a queen victim and the
same base pawn identity, with an independently reconciled whole-line endpoint delta.

## 7. Deterministic renderer

The common ScenarioSummaryRenderer.render(summary) returns RenderedScenarioReport,
with digest and detail sections made of RenderedFactSentence(text, source_refs).
Each sentence's nonempty references must resolve; structural headings are separate
labels without factual assertions. The report contains:
focus capture sequence, whole-line material, selected endpoint facts, and feature
history details. First implementation uses fixed English templates, consistent with
existing internal renderer conventions; Korean/localization is deferred.

The short view is explicitly an endpoint digest, not an importance-ranked narrative.
It always states focus/status, all focus capture events, all nonzero whole-line
material counts, selected endpoint facts and number of temporary tracks with references
to detail sections. The detailed view contains all selected step/history data.
Long output is acceptable in v1; UI pagination is deferred, never silently truncated.

Mandatory wording: "In the supplied line ...", "at the supplied endpoint", and
"geometric attackers" for P4 attack observations. NO_FOCUS_CAPTURE explicitly says
no capture landed on the requested square, without implying safety or impossibility.
Examples must come from executable fixtures, not invented legal sequences.
Forbidden vocabulary/assertions: good/bad, wins the exchange, loses by force, safe,
compensation, improved mobility, settled, must recapture, caused the evaluation.
Renderer produces no ExplanationClaim, confidence label or P12 integration.

## 8. Acceptance and cost

| Case | Required result |
| --- | --- |
| Empty line | One focus frame; no participants/events/changes; NO_FOCUS_CAPTURE |
| One capture / recapture | Actual participants and losses; no completion assertion |
| Quiet interruption then focus capture | All chronological events, no artificial chain |
| Capture elsewhere | Other event and whole-line count; no focus membership |
| En passant | Landing classification and distinct victim square preserved |
| Capture-promotion then promoted piece captured | One physical history; current-type loss and totals reconcile |
| Two same-type pieces / swapped identity injection | Unique source lookup; injected inconsistent histories refused |
| Stationary pawn gains/loses supporter | Correct base supporter identities, no movement-only change |
| Unrelated pawn/file change | Excluded unless exact selection predicate holds; accounted |
| Temporary pin / footprint reversal | History retained, endpoint delta absent when restored |
| Replaced pin participant / relocated blocker | Physical replacement distinguished from relocation |
| Final non-slider / captured subject | Typed NOT_APPLICABLE, no bogus negative score |
| Side-to-move change / castling | No mobility delta; physical transitions preserved |
| Focus attack with no legal capture / pinned attacker | Geometric wording, no recapture inference |
| Invalid focus, bool/oversized budget | Refusal before any observation |
| Illegal later move | Existing failure, no partial summary |
| Mismatched ids/version/refs/value/event membership | Typed refusal, including renderer boundary |
| Duplicate source facts / multiple reasons | No duplicated selected fact; reasons canonical |
| Counts and material projections | Selection accounting and source equality reconcile |
| Color mirror | Equivalent rules with transformed square/direction keys, not list indices |
| Renderer | Every factual sentence resolves to sources; banned judgement phrases absent |

Measure projection/rendering separately against ActivityLineAnalyzer for 0/1/64/256
plies, including dense activity changes. Additional adapter and engine calls must be
zero. Budget checks precede expensive work. Cost is bounded by supplied frames and
existing per-frame observation size; no branching tree or generated chess search.
Avoid generating every possible relation pair: enumerate existing observations only.
No new CI or full engine suite is required for design. Implementation uses focused
new tests plus existing positional/activity/identity groups, Ruff and diff check;
record performance measurements and any remaining omissions before review.

## 9. Delivery

A1: independent design review of the common design, this EXCHANGE policy and
[executable explanation corpus](scenario-explanation-corpus.md); resolve selection,
provenance, completeness and validation findings.
A2: implement the frozen reviewed record/value contract, summary projection and internal renderer.
A3: independent implementation review and regression evidence; integrate only after READY.
Later packets: compare alternate supplied lines, engine evaluation evidence, additional
scenario kinds and public interface. They must not retroactively turn relevance rules
into causal explanations or chess-strength scores.
