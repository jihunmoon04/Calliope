# Scenario line analysis and source-linked summary — design A1

Status: DRAFT_AWAITING_INDEPENDENT_DESIGN_REVIEW.
This is a proposed contract, not an implemented feature. The first executable
scenario will be EXCHANGE. Its rules are in [exchange-line-summary-design.md](exchange-line-summary-design.md).

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

Proposed frozen types (names below do not currently exist in production):

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

The SourceKind, FactKind/value table, sentinels and SourceRef selector rules in
the EXCHANGE document are the v1 **shared** fact vocabulary. New scenarios may use
these kinds but cannot silently broaden their meaning or add arbitrary payloads.

SourceRef is represented as a closed tagged union in implementation: a frame fact
has exact frame_index + position_id + its kind-specific selectors; a step fact has
exact ply (1..N), before/after position ids + its selectors. Material refers to
both endpoint frames. No ignored optional selector fields are permitted. References
resolve against observed_line only; every selected value must equal its projection.
Physical subjects use BasePieceRef; frame PieceRef is retained as observation value.

Exact v1 source selectors (indices are exact ints, never bool):

| SourceKind | Anchor and required selector | Resolves to |
| --- | --- | --- |
| CAPTURE | ply + both position ids | That step's P5 capture; must exist |
| TRANSITION | ply + both ids + base subject + PieceTransitionKind | Unique matching P5 transition; must exist |
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

## 5. Complete selection and lossless compression

Enumerate supported changed candidates from the anchored line, independently of
selection. A candidate key is (adjacent frame pair, FactKind, physical subject or
square/file/ray/pin key). Multiple applicable reasons are canonicalized on one
candidate. Per family, included + excluded must equal enumerated candidates.
Events and unchanged focus snapshots have separate counts, not mixed into change
accounting. Accounted exclusion has a rule reason, not an importance judgement.

Participants are derived over the entire line. Their earlier observations may be
included retrospectively, never described as a prediction known at frame zero.
Participant/file predicates use the exact frame-local rules in the EXCHANGE table.

For every property key selected in at least one step, retain its complete 0..N
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
and status, every focus capture, every nonzero whole-line material count, all selected
endpoint facts and referenced temporary-track count. Detail retains all selected
steps and history context. The digest is not an importance-ranked explanation.

Mandatory qualifiers: supplied line, supplied endpoint, geometric attackers where
appropriate. Forbidden assertions include good/bad move, wins the exchange, safe,
must recapture, forced loss, compensation, improved mobility, settled exchange and
caused the evaluation. Rendering creates no P10 claim or P12 output.

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

Current corpus verification calls existing analyzers only. It is not acceptance of
unimplemented ScenarioSummary or ScenarioSummaryRenderer.

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

Verified against the local worktree's explicit src path on 2026-10-08 (Korea date):
14 base factual cases + 14 capture/material mirror controls passed. Combined with
the existing positional/activity/identity/python-chess/composition/facade group:
**265 passed / 0 failed**. Changed Python Ruff check/format and git diff --check pass.
Production src is identical to main `dffd550`. Only docs, corpus data and its
observation verifier changed. No full pytest, real Stockfish, fuzz, performance
measurement, independent design verdict or summary-feature acceptance is claimed.
