# Scenario line analysis and source-linked summary — design A1

Status: A1_READY / A3_READY.
Independent review of PR #29 `c99d6a3`: READY, supplied by the user on 2026-10-08.
It accepts F1-F7 and permits A2; N1/N2 are nonblocking acceptance notes.
Independent A3 review of PR #30 `7d527b2`: READY_WITH_CORRECTIONS (C1).
The reviewed C1 amendment requires every selected participant PROMOTION in digest.
Independent A3 re-review of `672f162`: READY, supplied by the user on 2026-10-08.
Internal implementation evidence: [scenario-summary-a2-implementation.md](scenario-summary-a2-implementation.md).
The first executable scenario is EXCHANGE. Its rules are in [exchange-line-summary-design.md](exchange-line-summary-design.md).

Base: main `dffd55013834d9f8f824f3913ddfa3e7aaf2ff76`.
Reviewed predecessors: positional_v1 and activity_v1.

## 1. Product goal

Answer a bounded question about a supplied legal line with selected, traceable
facts: what happened, what differs at its endpoint, and what changed temporarily?
The first question is: "What happens on this square in this supplied exchange line?"

The quality oracle is [scenario-explanation-corpus.md](scenario-explanation-corpus.md),
with executable inputs and independent observation expectations in
`tests/golden/scenario_explanation_cases.json`. Passing observation fixtures proves
the inputs and their factual expectations, not a future selector or renderer.

Three evidentiary levels stay distinct:

| Level | Available now | Language permitted |
| --- | --- | --- |
| Observed fact in supplied line | positional_v1 / activity_v1 | "In the supplied line ..." |
| Difference between supplied alternatives | Future comparison packet | "These two supplied lines differ in ..." |
| Verified explanation of move quality | Existing bounded P8/P9 claims; future positional verification | Only the exact supported predicate and evidence form |

Scenario relevance does not certify importance, advantage, safety, forcedness or
causality. A file opening and an evaluation difference together are not causal proof.

## 2. Normalized request

Implemented internal frozen types (direct module imports; no package exports):

```text
ScenarioKind = EXCHANGE
SquareTarget(square: str)
ScenarioRequest(kind: ScenarioKind, target: SquareTarget,
                initial: PositionSnapshot, supplied_line: tuple[ChessMove, ...],
                max_plies: int = 64)
ScenarioLineAnalyzer(activity_lines: ActivityLineAnalyzer).analyze(request)
    -> ScenarioSummary
ScenarioSummaryRenderer.render(summary) -> RenderedScenarioReport
```

The v1 accepted kind/target matrix contains only EXCHANGE + SquareTarget. Other
kinds, plain strings in place of enum members, other target types, non-tuple lines,
non-ChessMove entries, malformed squares and bool budgets are rejected before
observation with InvalidScenarioRequestError. Budget is exact int 1..256; empty
lines are allowed; len(supplied_line) must not exceed max_plies. Existing errors for
invalid position or illegal moves propagate with no partial summary.

Pawn advance, piece relocation and general exploration are planned extensions,
not accepted enum placeholders. PieceTarget would be a base-position physical
identity, never a mutable current square. Each new kind requires its own reviewed
kind/target matrix, membership rules and close counterexamples.

No natural-language filters, callbacks, executable predicates, unrestricted fact
names, LLM calls or caller-supplied relevance weights enter this contract. Line
origin (user, engine or LLM) has no effect on evidentiary strength.

## 3. One shared pipeline

```text
validate request
 -> ActivityLineAnalyzer (one supplied-line replay)
 -> validate anchored frames, steps and physical histories
 -> derive scenario membership using the closed kind dispatch
 -> enumerate supported facts and apply explicit relevance predicates
 -> compress selected tracks into events / endpoint changes / histories
 -> validate exact projection and references
 -> optional fixed-template report
```

Common code owns replay invocation, identity lookup, typed facts, reference
resolution, canonical ordering, projection validation, compression and rendering.
EXCHANGE owns only focus capture classification, participant membership, inclusion
predicates, selection reasons, focus loss counts and status. The implementation
uses one private EXCHANGE policy, not an extensible plugin registry. Future policies
reuse this pipeline without creating a second board replay or summary vocabulary.

Only analyze(request) is a service entry point. No public entry accepts an
ActivityLineAnalysis as trusted input. Private projection still validates frame and
step counts, consecutive structural bindings, final frame, definition versions,
P4 anchors, exact one-to-one inverse identities at every frame and P5 correspondence.
Retain the existing F1 move/identity checks and F1/F2 activity record checks.

No engine/adapter work occurs in selection, projection, validation or rendering.
No changes to P4-P12, schema 0.2, composition or package exports. Shared identity
relocation is deferred; these services stay out of services.position.__init__.

## 4. Shared summary and scenario detail

ScenarioSummary contains request, definition_version=scenario_summary_v1,
observed_line, detail: ExchangeDetail, events, focus_timeline, selected_changes,
endpoint_changes, feature_histories and selection_accounting.

ExchangeDetail contains version=exchange_rules_v1, status, participants,
focus_capture_events, other_capture_events, whole_line_material_changes and
focus_capture_losses. No optional fields for unimplemented scenario kinds are added.
The kind/detail pair must match exactly. All records are frozen typed values.

This document alone owns SourceKind, FactKind/value pairs, sentinels, SourceRef,
candidate identities, accounting shapes and the template catalog. EXCHANGE owns
membership and relevance predicates only. New scenarios cannot silently broaden
shared values or add arbitrary payloads.

SelectedChange has FactKind, typed before/after values, exact property key and a
canonical nonempty reason tuple. ParticipantSummary has base identity and N+1
history references. FeatureHistory has property key, complete frame values compressed
into maximal equal runs (inclusive start/end), references and relevant step indices.
CAPTURED, EMPTY and NOT_APPLICABLE are distinct enum sentinels.

| FactKind | Closed value type |
| --- | --- |
| PIECE_STATE | PieceRef or CAPTURED |
| FOCUS_OCCUPANT | (BasePieceRef, PieceRef) or EMPTY |
| FOCUS_ATTACKERS | Separate white/black canonical tuples of (BasePieceRef, PieceRef) |
| FOCUS_LEGAL_CAPTURES_NOW | (side_to_move, canonical LegalCapture tuple); snapshot-only |
| PAWN_FLAGS | (isolated: bool, doubled: bool, passed: bool) or NOT_APPLICABLE |
| PAWN_SUPPORTERS | Canonical BasePieceRef tuple or NOT_APPLICABLE |
| FILE_STATE | FileStructure pawn counts; open/semi-open are derived |
| ATTACK_FOOTPRINT | Canonical square tuple or NOT_APPLICABLE |
| ATTACK_PARTITION | Three disjoint canonical square tuples (empty/friendly/enemy) or NOT_APPLICABLE |
| RAY_STATE | SliderRay with base source and base identities of every occupant, or NOT_APPLICABLE |
| PIN_PRESENT | bool with physical (pinner,pinned,king) key |

EventKind is the separate closed enum CAPTURE, PROMOTION, MOVE, CASTLING_ROOK.
Events retain P5 typed payload and ply. MATERIAL_COUNTS and FOCUS_LOSSES are separate
typed count views, not additional arbitrary FactKind variants. No weighted scores.
All records validate local shape/canonical order with InvalidScenarioSummaryError.
SelectionReason declaration/canonical order is LINE_CONTEXT, FOCUS_CAPTURE,
FOCUS_VICTIM_SQUARE, FOCUS_SQUARE, PARTICIPANT, FOCUS_FILE, PARTICIPANT_FILE,
PARTICIPANT_PIN. ExclusionReason has only NOT_SCENARIO_RELEVANT in this version.

SourceRef is represented as a closed tagged union in implementation: a frame fact
has exact frame_index + position_id + its kind-specific selectors; a step fact has
exact ply (1..N), before/after position ids + its selectors. Material refers to
both endpoint frames. No ignored optional selector fields are permitted. References
resolve against observed_line only; every selected value must equal its projection.
Physical subjects use BasePieceRef; frame PieceRef is retained as observation value.

Exact v1 source selectors (indices are exact ints, never bool):
SourceKind is exactly the closed set of rows below; no alternative optional-field
encoding or extra kind is allowed.

| SourceKind | Anchor and required selector | Resolves to |
| --- | --- | --- |
| CAPTURE | ply + both position ids | That step's P5 capture; must exist |
| TRANSITION | ply + both ids + base subject + PieceTransitionKind | Unique matching P5 transition; its parent step's canonical move UCI is context, not the subject's UCI |
| MATERIAL | frame 0 and N ids + color + non-king PieceType | Endpoint count pair / delta |
| PIECE_HISTORY | frame + id + base subject | Unique physical history state, including CAPTURED |
| SQUARE_ACCESS | frame + id + square | Occupant, geometric attackers, current-side legal captures |
| PAWN_STRUCTURE | frame + id + base subject | Pawn flags/supporters, or NOT_APPLICABLE proven by history |
| FILE_STRUCTURE | frame + id + file a..h | That frame's pawn counts |
| PIECE_ACTIVITY | frame + id + base subject | Geometric footprint/partition, or NOT_APPLICABLE if captured |
| SLIDER_RAY | frame + id + base subject + standard direction | Ray and physical occupants, or NOT_APPLICABLE if no slider |
| ABSOLUTE_PIN | frame + id + three base identities | Presence/absence in the complete observed pin set |

Every identity selector must exist in the initial physical histories, including
captured identities. Absence and NOT_APPLICABLE are projected from complete anchored
sets and physical state; unresolved selectors never resolve to a false/empty value.

Mixed-source values require the complete reference bundle, not one convenient ref:

| Value/event | Mandatory sources at EACH value's frame (or step endpoints) |
| --- | --- |
| FOCUS_OCCUPANT | SQUARE_ACCESS + PIECE_HISTORY for the occupant if nonempty |
| FOCUS_ATTACKERS | SQUARE_ACCESS + PIECE_HISTORY for every attacker |
| RAY_STATE | SLIDER_RAY + PIECE_HISTORY for source and every occupant |
| PAWN_FLAGS / PAWN_SUPPORTERS | PAWN_STRUCTURE + subject history; supporters additionally require all supporter histories |
| PIN_PRESENT | ABSOLUTE_PIN + histories for all three keyed identities (captured states allowed for absence) |
| PIECE_STATE / footprint / partition | Respective history or PIECE_ACTIVITY + subject history |
| FOCUS_LEGAL_CAPTURES_NOW | SQUARE_ACCESS + histories for every capturer/victim in that snapshot |
| Capture event | CAPTURE + before/after capturer histories + before/after victim histories, including captured absence |
| MOVE / PROMOTION / CASTLING_ROOK | TRANSITION + before/after subject histories |

For EMPTY/NOT_APPLICABLE there is no invented missing identity: the complete source
set and, where keyed by a subject, its history prove absence. Both values of a change
need their own bundles. Derived material needs MATERIAL endpoint refs; focus losses
need all contributing CAPTURE refs and victim histories. Resolver validation checks
exact value equality, not mere existence of each reference.

No duplicate factual event exists in the shared events stream. ExchangeDetail's
focus/other collections are partitions referencing the same capture event ids;
capture-promotion additionally has one distinct promotion event at the same ply.
Event ids use chronological ply, then CAPTURE before PROMOTION before other movement
events, then base board order. They are request-local and never claim ids.
Capture already represents the capturer's relocation, so it suppresses that same
subject's ordinary MOVE event. Capture-promotion retains a separate PROMOTION event.
Otherwise selected P5 transitions emit MOVE, PROMOTION or CASTLING_ROOK events.
At equal ply the kind order is CAPTURE, PROMOTION, MOVE, CASTLING_ROOK, then base
board order. Selection of an event requires a capture or participant lifecycle rule;
unrelated quiet motion remains only in the complete observed line.

Canonical property order is FactKind declaration order (the value table above),
then initial base board index, square board index, file a..h, lexicographic direction
(df,dr), or pin triple's base board indices as appropriate. Steps prepend ply;
snapshots prepend frame. Endpoint/history keys use property order. Aggregates use
view order MATERIAL_COUNTS then FOCUS_LOSSES, color WHITE then BLACK, and piece type
PAWN, KNIGHT, BISHOP, ROOK, QUEEN. Identity-valued lists use base board order;
geometric square lists use board order; ray occupants retain near-to-far ray order
with their associated physical identities, never identity-sort the ray itself.

## 5. Complete selection and lossless compression

Candidate domains and EXCHANGE inclusion predicates are frozen row-by-row in the
five-column table in [EXCHANGE section 5](exchange-line-summary-design.md#5-closed-selection-and-accounting).
That table instantiates the following shared enumeration contract, including
PIECE_STATE, ATTACK_PARTITION, PAWN_SUPPORTERS and all event families.

Let B be ALL initial BasePieceRefs, not only participants; P is the policy-selected
participant subset. All property comparisons resolve through B's histories. Let
D(a,b) be the two compared frames, adjacent (p-1,p) for step or (0,N) for endpoint.
For every table property domain enumerate a candidate iff its typed values differ.
PIN keys are the union of actual physical pin triples observed ANYWHERE in 0..N;
its values are presence/absence at compared frames. Ray directions are the union
of directions supported by that subject's slider type in either compared frame;
unsupported/captured values are NOT_APPLICABLE. Pawn domains include every b in B
that is a pawn in either compared frame; capture/promotion produces NOT_APPLICABLE.
No cartesian enumeration of hypothetical pins, rays or relation pairs is permitted.

Focus properties have only the requested square domain. All N+1 unchanged or changed
focus snapshots remain in focus_timeline, separately from step/endpoint candidates.
FOCUS_LEGAL_CAPTURES_NOW is snapshot-only: side changes are not activity deltas.
PIECE_STATE is compared in steps/endpoints but has no feature-history compression;
its temporal information is represented by physical histories and lifecycle events.

There are five independent accounting maps indexed by the closed table family:
`steps`, `endpoints`, `events`, `snapshots`, `aggregates`. A row always exists with
zero counts when its supported family has no candidates; bucket/family combinations
not in the table are forbidden. Each row stores canonical complete
candidate_keys, included_keys, excluded_keys and their lengths; included/excluded
are disjoint and partition candidates. An excluded key has NOT_SCENARIO_RELEVANT.
Key membership must be recomputed exactly; equal cardinalities alone do not pass.
Steps index by ply + property key; endpoints by property key; events by ply + kind
and subject (CAPTURE uses ply alone); snapshots by frame + kind + focus; aggregates
by view + color + piece type. Included reasons are exactly the matching table
reasons; one fact with multiple reasons stays one key. No cross-map count summation
is described as number of unique facts. For E14, a2's MOVE is in events.excluded and
its PIECE_STATE/footprint/partition candidates are in steps/endpoints as applicable.

Lifecycle event candidate enumeration runs BEFORE participant filtering: every P5
capture and every actual P5 transition except ordinary MOVE suppressed by its
same-subject capture. Promotion is never suppressed. Castling has a king MOVE and
rook CASTLING_ROOK candidate. Captured victims have no invented MOVE event. This
enumeration is independent of whether any event is selected.

Aggregates enumerate nonzero whole-line endpoint material deltas and nonzero
focus-loss victim type counts separately. Events and aggregates retain contributing
references and count independently. Snapshot counts are exactly N+1 per focus kind.

Participants are derived over the entire line. Their earlier observations may be
included retrospectively, never described as a prediction known at frame zero.
Participant/file predicates use the exact frame-local rules in the EXCHANGE table.

For every tracked property key selected in at least one step (excluding PIECE_STATE
and snapshot-only legal captures), retain its complete 0..N
value track, including values at steps where the relevance predicate is false.
History runs carry references plus the indices/reasons that made the track relevant;
history context is labelled as such, not falsely counted as selected steps. Endpoint
selection is computed separately with the EXCHANGE endpoint predicate, so a property
visited only in a middle frame need not appear in endpoint_changes. This explicitly
preserves temporary facts without silently expanding endpoint selection.

Focus timeline has N+1 snapshots even with zero captures or zero changes. Events are
chronological; endpoint changes compare frame 0 with N; histories are maximal equal
value runs. CAPTURED, EMPTY and NOT_APPLICABLE are distinct. Disappearance and
promotion must not become false pawn flags or fictitious negative activity values.

Each focus snapshot additionally contains side_to_move and the exact P4 current-side
legal capture records landing on the focus square. This is a labelled instantaneous
observation, not a cross-turn change or mobility metric. It permits E09's explicit
distinction between geometric attack and current legal capture. No other side's legal
captures are inferred; these snapshots are never included in change accounting.

Pin keys use physical (pinner,pinned,king), ray keys physical source + direction.
Stored values retain blocker identities and current geometry. Moving one blocker
does not replace its identity; replacing a same-type piece changes physical identity.
No top-k suppression, salience ranking or character-budget truncation in v1.

`temporary_track_count` is exactly the number of selected feature-history keys
(all tracked FactKinds except PIECE_STATE and snapshot-only legal captures) whose
frame-0 value equals frame-N value AND which differ from that value at least once
inside 1..N-1. Each key counts once, regardless of how many excursions or reasons.
Constant tracks and net-changed tracks count zero; the latter's intermediate runs
still remain in detail. Empty/one-ply lines have count zero. E12's pin key counts
one with presence [false,true,false,false,false] and no endpoint pin candidate.

## 6. Validation and presentation

InvalidScenarioSummaryError is Calliope-owned. Child constructors validate local
shape; the summary validator recomputes membership, all inclusion/exclusion sets,
event partitions, projected values, endpoints, runs and material views from retained
observations without board replay. Checking only reference existence or count sums is
insufficient. Missing included facts, extra selected facts, unresolved references,
wrong rule versions and mismatched kind/detail are errors, never valid silence.
Renderer validates the summary before output, including caller-constructed records.

RenderedScenarioReport has an endpoint digest and full detail. Each factual sentence
retains nonempty resolving SourceRefs. Fixed English templates are first; Korean
localization is a later reviewed presentation packet. Digest includes scenario target
and status, every focus capture, every capture with FOCUS_VICTIM_SQUARE (without
changing membership or focus losses), every nonzero whole-line material count, all selected
endpoint facts, every selected participant PROMOTION and referenced temporary-track count.
Digest events retain their canonical chronological order (capture before promotion
at the same ply), including a participant's earlier quiet promotion. Detail retains all selected
steps and history context. The digest is not an importance-ranked explanation.

Mandatory qualifiers: supplied line, supplied endpoint, geometric attackers where
appropriate. Forbidden assertions include good/bad move, wins the exchange, safe,
must recapture, forced loss, compensation, improved mobility, settled exchange and
caused the evaluation. Rendering creates no P10 claim or P12 output.

### 6.1 Closed rendering templates (F7)

Production rendering accepts only reviewed TemplateIds bound to a FactKind/event/
typed count/status. It never interpolates question text, corpus prose, arbitrary
labels or caller-authored wording. Parameters come only from validated typed values.
Adding a template or paraphrase requires contract review and semantic review of its
fixed wording. Value formatting is closed: colors/types, standard squares/UCI,
integers, booleans, ordered lists, and the three sentinels; no adjective/causal phrase
slot. {context} is closed to "In the supplied line, at the initial frame",
"In the supplied line, after ply {p}", "In the supplied line, at the supplied
endpoint", or "In the supplied line, from frame {a} through frame {b}". Integer
slots name the exact referenced snapshot or maximal equal-value run, not arbitrary
time descriptions. A run's values are validated across every retained frame.

| TemplateId / family | Fixed sentence form (typed placeholders only) |
| --- | --- |
| STATUS_NONE | In the supplied line, no capture lands on {focus}. |
| STATUS_OBSERVED | In the supplied line, {count} capture(s) land on {focus}. |
| CAPTURE_NORMAL | In the supplied line, at ply {p}, {capturer with square} captures {victim color/type without square} on {landing}. |
| CAPTURE_EP | In the supplied line, at ply {p}, {capturer} captures en passant, landing on {landing} and removing {victim} from {victim_square}. |
| MOVE / PROMOTION | In the supplied line, at ply {p}, the piece initially on {base} moves from {from} to {to} [or promotes to {type}]. |
| MOVE (king castling branch) | In the supplied line, at ply {p}, move {uci} is castling; the participant king initially on {base} moves from {from} to {to}. |
| CASTLING_ROOK | In the supplied line, at ply {p}, move {uci} is castling; the participant rook initially on {base} moves from {from} to {to}. |
| PIECE_STATE | {context}, the piece initially on {base} is {current piece on square / captured}. |
| FOCUS_OCCUPANT | {context}, {focus} is {empty / occupied by color type initially on base}. |
| FOCUS_ATTACKERS | {context}, the {color} geometric attackers of {focus} are {piece list / none}. |
| FOCUS_LEGAL_CAPTURES_NOW | {context}, the side to move is {color}; its current legal captures landing on {focus} are {UCI list / none}. |
| PAWN_FLAGS | {context}, the pawn initially on {base} has isolated={bool}, doubled={bool}, passed={bool} [or pawn structure is not applicable]. |
| PAWN_SUPPORTERS | {context}, geometric pawn supporters of the pawn initially on {base} are {base list / none / not applicable}. |
| FILE_STATE | {context}, file {file} contains {w} white pawn(s) and {b} black pawn(s); its derived state is {open / semi-open for color / neither}. |
| ATTACK_FOOTPRINT | {context}, the geometric target squares of {base piece} are {square list / not applicable}. |
| ATTACK_PARTITION | {context}, geometric targets of {base piece} are empty={list}, friendly={list}, enemy={list} [or not applicable]. |
| RAY_STATE | {context}, {base piece}'s ray {direction} has visible squares {list} and occupants {physical piece list} [or not applicable]. |
| PIN_PRESENT_TRUE | {context}, an absolute pin is observed with pinner={piece}, pinned={piece}, king={piece}. |
| PIN_PRESENT_FALSE | {context}, the absolute pin keyed by initial squares {triple} is not observed. |
| MATERIAL_COUNTS | In the supplied line, at the supplied endpoint, the {color} {type} count changes by {signed integer} relative to the initial frame. |
| FOCUS_LOSSES | In the supplied line, captures landing on {focus} remove {count} {color} {current type} piece(s). |
| TEMPORARY_COUNT | In the supplied line, {count} selected feature track(s) differ in intermediate frames and return to their initial value at the supplied endpoint. |

Changes are rendered with these value forms at both referenced times, not an
unreviewed "improvement" or "caused" change template. Histories use the same value
forms for each maximal run. CAPTURE_EP is mandatory in digest for FOCUS_VICTIM_SQUARE.
PROMOTION is mandatory in digest for every selected participant promotion, so a
later capture of its promoted type remains linked to the same initial physical piece.
PIN_PRESENT_FALSE mentions observation time only; no king MOVE or causal connector.
F6: if only the rook is a participant, CASTLING_ROOK is selected and king MOVE is
excluded. Its UCI is the actual step's king castling UCI, explicitly labelled move
context, never presented as the rook's own UCI. The sentence still specifies the
rook's actual endpoints, with TRANSITION/PIECE_HISTORY refs for that rook. If both
transitions are selected, they remain distinct physical events of one step.

A2 tests enumerate every permitted template/branch, reject unknown TemplateIds,
check typed slot restrictions, and resolve every factual sentence's references.
The independent reviewer inspects the entire closed catalog for unsupported
semantics. Phrase blacklists are supplementary; corpus required/excluded structured
facts check selection coverage independently of rendering fluency.

## 7. Explanation quality gate

Before implementing the selector, independently review the corpus expectations,
kind/target matrix, EXCHANGE rules and validation completeness. After implementation:

1. Every corpus input replays legally; manually specified factual expectations pass.
2. Every case's required selected facts and deliberately excluded facts are checked
   against ScenarioSummary, including zero-capture and temporary-history cases.
3. Report qualifiers and per-sentence references pass; unsupported assertions are
   absent semantically, not only by an English word blacklist.
4. Loss counts and endpoint counts remain separate, especially promotion/EP cases.
5. Golden assertions use structured facts; exact prose may change without weakening
   meaning. Missing required facts is a failure even if prose sounds fluent.
6. Mutation tests corrupt identity, selection completeness, references and values;
   the validator must reject them without extra adapter calls.
7. Focused positional/activity/identity regression, changed-file lint and diff check
   pass. Measure projection/render cost separately at 0/1/64/256 plies; no production
   performance claim follows from a development smoke measurement.

The original observation verifier still calls existing analyzers only. Separate
A2 acceptance checks now exercise ScenarioSummary and ScenarioSummaryRenderer
against the frozen JSON, including all structured expectations on color mirrors.
Passing these authored tests does not replace independent A3 review.

## 8. Delivery and next packets

A1: this common contract + EXCHANGE policy + executable explanation corpus; independent
design review and corrections. A2: shared records/validator, EXCHANGE selection and
compression, internal renderer. A3: independent implementation review, regression and
cost evidence; integration after READY. No production implementation begins before
A1 independent review is resolved.

B1 later: paired supplied-line comparison, same initial full position identity and
shared target/physical subjects, independent replay per line, explicit budget and
endpoint alignment rules. Different depths/endpoints are not automatically comparable.
Report factual contrasts only; engine scores alone cannot establish structural cause.
B2 later: narrowly typed positional hypotheses with explicit verification/refutation
criteria using existing P7-P10 boundaries where justified. Full strategic planning,
public integration, Korean presentation and optional LLM remain separate packets.

## 9. Migration from the earlier draft

The earlier PR #29 had no production ExchangeLineRequest/Service/Renderer. Those
proposed entry points are superseded by ScenarioRequest/LineAnalyzer/Renderer, so
no compatibility shim is needed. EXCHANGE-specific semantics remain in the linked
policy document. There is one active request, summary and renderer contract.

## 10. Design packet verification

Historical 094f4df validation against explicit worktree src on 2026-10-08 (Korea date):
14 base factual cases + 14 capture/material mirror controls passed. Combined with
the existing positional/activity/identity/python-chess/composition/facade group:
**265 passed / 0 failed**. Changed Python Ruff check/format and git diff --check pass.
Production src is identical to main `dffd550`. Only docs, corpus data and its
observation verifier changed. No full pytest, real Stockfish, fuzz, performance
measurement or summary-feature acceptance was claimed. An independent design review
then returned READY_WITH_CORRECTIONS. The corrected packet's evidence and F1-F7
traceability are in [scenario-design-review-corrections.md](scenario-design-review-corrections.md).
The 15-case v2 JSON freezes exact membership/status/losses and core fact keys before
A2; expectation values were not generated from a future summary implementation.
