# Positional activity foundation — design A1 corrected contract

Status: IMPLEMENTED_AWAITING_INDEPENDENT_REVIEW. The contract below was frozen after
independent READY_WITH_CORRECTIONS and D1-D8 resolution; the implementation is recorded in
[Implementation record](#implementation-record) and has not yet been independently reviewed.
Base: `main @ 10396988b906cc6daf323e3efb6f00b37d6ccc3e`.
Predecessor: positional foundation v1, independently reviewed READY at `de020c8`.

## Goal and scope

Expose enough exact geometry to ask which pieces affect e4, which slider is obstructed,
and how an actual move opens/closes a line or changes an attack footprint. These are
reusable observations for future scenario selection, not positional scores or explanations.

This packet adds geometric square access, complete slider rays with occupancy, and
current-side legal action summaries. No Stockfish calls, LLM, safe-mobility score,
king-safety score, scenario search, claim generation or public schema changes.

## Reuse and ownership

| Data | Existing source | New work |
| --- | --- | --- |
| Pieces and geometric attacks | P4 PositionFacts | Index and classify existing attacks |
| Legal moves and absolute pins | TacticalObservationPort / observe_tactics | Reuse exact observations, validate binding |
| Move/identity correspondence | P5 BoardDelta and positional TransitionAnalyzer | Retain corrected F1 checks |
| Line identity | LineAnalyzer.piece_histories | Attach activity at each observed frame |
| Ray occupancy | P4 piece map + standard slider directions | Deterministic geometry, never move generation |

The python-chess adapter is the sole legal-move producer. Do not toggle board.turn to
invent opponent mobility, introduce a second rules adapter, or modify P4/P5 protocols.
Ray geometry is computed over immutable pieces; it does not decide legal captures.

## Definitions: activity_v1

### Square access

For every square a1..h8, expose occupant (or None), white geometric attackers, black
geometric attackers and legal captures landing on this square **for the current side**.
Attackers come from P4 AttackRelation, including pinned pieces and friendly-occupied
endpoints. Attacker counts are projections of those lists, not extra authoritative data.

A geometric attacker is not necessarily able to capture. current_legal_captures(square)
is exactly the P4 LegalCapture subset with landing_square == square, including captures
landing on an empty square. En passant records retain both landing and actual captured square;
do not infer the victim from the destination occupant. A current-side capture record
does not imply the opponent has no capture: that opponent is not on move.
The sole en passant marker is LegalCapture.is_en_passant, never snapshot.en_passant_square.
The latter may contain e3 after e2e4 even when no legal en passant capture exists.

### Piece activity

Each piece has a geometric attack footprint, partitioned into empty squares, friendly
occupied squares and enemy occupied squares. These are exact descriptions of P4 attacks,
not destination legality, tactical safety, reachability over multiple moves or advantage.
Use explicit names such as geometric_attack_count, never a bare mobility score.

For current-side pieces only, also expose legal moves, unique legal destination squares,
and legal capture moves. Opponent legal-action fields are **None / not observed**, never
empty tuples or zero counts. Current-side pieces with no legal moves have empty tuples.
Four promotion choices to the same square count as four moves and one destination.
Standard castling is one king move in this summary, not an independently movable rook.
Check can reduce legal destinations without reducing geometric attacks.
Legal destinations are NOT a subset of the attack footprint: pawn advances and castling
are examples outside it. Castling destinations are the canonical king targets g1/c1 or
g8/c8. Conversely, a friendly occupied attacked square is not a legal destination.

Absolute pins are copied from the existing tactical observation as rule-level context.
Relative pins and whether removing a defender loses material remain future interpretations.

### Slider rays

For each bishop/rook/queen, enumerate every applicable unit direction (df, dr): four
diagonals for bishops, four orthogonals for rooks, their union for queens. Directions are
sorted lexicographically by (df, dr). Each ray stores only:

- source PieceRef and direction;
- all squares from the next square to the board edge, in near-to-far order;
- occupied squares/pieces on that ray in the same order;
- first_blocker and visible_squares are read-only properties derived from squares and
  occupants, not independently stored constructor fields. Visibility runs through and
  includes the first blocker, or to the edge.

An **edge-empty ray** has squares == (); an **unblocked ray** has non-empty squares and
no occupants. Both have first_blocker is None, but are different geometries. These terms
replace the ambiguous "empty ray". The source square is excluded.
Visibility includes the first blocker even if friendly, consistent with P4 attack semantics.
Squares after it are geometric ray information only and never advertised as current
attacks. Blocker color determines occupancy, not whether it can be captured legally.
All blockers are recorded so a later move can be inspected without inventing an attack
behind a second blocker. No X_RAY_ATTACK or LINE_WILL_OPEN claim is emitted.

For every slider, union of visible ray squares must equal its P4 attack footprint.
Mismatch is an incompatible observation, not a fallback to guessed geometry.

## Frozen internal contracts

Use frozen typed dataclasses and canonical tuples, not a generic string/value fact bag.
Names below are frozen for this packet, not existing production classes.

```text
SquareAccess(square, occupant, white_attackers, black_attackers, current_legal_captures)
PieceActivity(piece, footprint, empty_attacks, friendly_attacks, enemy_attacks,
              legal_moves_now | None,
              legal_captures_now | None)
SliderRay(source, direction, squares, occupants)
ActivityFacts(source_facts: PositionFacts, position_id, side_to_move, definition_version="activity_v1",
              squares, pieces, rays, absolute_pins)
ActivityPositionAnalysis(structural: PositionAnalysis, activity: ActivityFacts)
ActivityTransitionAnalysis(structural: TransitionAnalysis,
                           before_activity, after_activity,
                           attack_footprint_changes, ray_changes)
ActivityLineAnalysis(structural: LineAnalysis, activity_frames, activity_transitions)
```

Activity frames have exactly len(transitions)+1 entries and match structural frame ids.
Activity transitions have exactly len(structural.transitions) entries, reusing those
structural transitions and the adjacent activity frames. No second replay or extraction.
Retain positional_v1 definitions unchanged; activity_v1 has its own definition version.
Existing PositionAnalysis/TransitionAnalysis/LineAnalysis schemas need not change.

### D1: stored values versus derived values

- SliderRay.__post_init__ verifies slider type/applicable direction, exact complete
  near-to-far source-to-edge squares, and unique occupants whose squares form an ordered
  subsequence of that path. first_blocker and visible_squares are properties.
- PieceActivity.__post_init__ verifies canonical unique footprint and partitions; the
  three partitions are disjoint and their union is the footprint. Legal destinations
  and all counts are read-only properties (legal destinations deduplicate UCI targets,
  preserving None for the unobserved side).
- SquareAccess.__post_init__ verifies its square/occupant binding, canonical unique
  attacker lists with correct colors, and canonical unique capture UCIs with matching
  landing square. Counts are properties. This record alone cannot prove P4 agreement.
- ActivityFacts.__post_init__ retains source_facts: PositionFacts as its validation
  anchor and recomputes square access and per-piece footprint/partitions against that
  anchor. All 64 squares and all observed pieces must be present exactly once in canonical
  order. Ray occupants must match the source piece map, every slider must have every
  applicable direction exactly once, and visibility must match P4 attacks. Position id
  must match source_facts. No full-board copy is stored in each child record.
- ActivityPosition/Transition/LineAnalysis.__post_init__ check ids, versions, side context
  and adjacent frame/structural bindings. Recompute deterministic diffs at the service
  boundary; record-level bindings alone do not certify a supplied diff is correct.

Stored projections are thus validated, while straightforward ray/destination/count
derivations have no second stored authority. Malformed records raise Calliope-owned typed
errors. Acceptance includes wrong blocker geometry, occupant order/duplication, overlapping
or missing partitions, wrong-color attackers and inconsistent source-fact projections.

## Composition and affected files

Proposed new domain module: domain/analysis/activity.py.
Proposed new service module: services/position/activity.py.

- ActivityAnalyzer takes existing PositionAnalyzer and TacticalObservationPort. analyze
  observes a position; private _from_position_analysis consumes the exact structural
  frame from transition/line replay and performs validation steps 1-5 below, even on this
  path. There is no public "trusted facts" bypass or ChessRulesPort dependency.
- ActivityTransitionAnalyzer first invokes the existing corrected TransitionAnalyzer,
  then derives activity for its before/after states and compares geometric observations.
- ActivityLineAnalyzer first invokes existing LineAnalyzer with its limit, then attaches
  activity to those exact frames and computes one activity diff per existing structural
  transition through a shared private diff function. No second replay, duplicate frame
  extraction or alternative line budget.
- New tests live under tests/unit/services/position and, if adapter semantics need direct
  verification, tests/integration/python_chess. Documentation updates reflect actual scope.

No changes to services.position package exports: the F2 shared-identity dependency remains
until its separately reviewed relocation. No new public facade, composition wiring,
engine request or evidence/claim/render changes. Existing P6 observation API is reused.

## Observation validation

Before deriving activity, check:

1. PositionAnalysis position/facts/features identities agree; only supported definition
   versions are accepted. Reject duplicated piece squares and attack relations.
2. Tactical observation id and side-to-move agree with the actual snapshot.
3. Always perform structural move checks: standard lowercase UCI syntax, distinct valid
   source/target squares, unique sorted UCIs, and a mover-owned source piece. Promotion
   suffix q/r/b/n is required exactly for a pawn reaching its last rank and absent on
   other moves. Ignore SAN for identity. This is not a second legality generator.
4. Compare captures by UCI, never ChessMove equality (which includes SAN):
   - Every P4 capture UCI must exist in the tactical legal moves.
   - Every legal move landing on an enemy piece must exist in P4 captures.
   - Every pawn move changing file and landing on an empty square must exist in P4 captures.
   - Matching capture records bind their capturer, UCI source/landing and actual victim
     to observed pieces. Empty landing requires is_en_passant; its victim is the enemy
     pawn on the landing file/source rank. Occupied landing requires non-EP capture.
     Promotion captures retain the same UCI suffix. Duplicate capture UCIs fail.
   - EP classification uses only LegalCapture.is_en_passant; the snapshot ep field is
     never evidence of an available action. The victim cannot be a king; a king may
     itself be the capturer of another enemy piece.
   Absolute-pin refs must belong to the observed position: pinner is an opposing slider,
   pinned is same-color non-king as king, and pinner-to-king ray occupants must begin
   with [pinned, king]. Validate these pins against already computed rays, not a new search.
5. Attack references exist in the observed piece map; ray visibility agrees with P4.

No per-move ChessRulesPort round-trip is performed in production: in actual composition
it reconsults the same stateless PythonChessAdapter and adds FEN parsing/SAN generation
for every move. The design does not claim to prove arbitrary move legality or the
completeness of malicious legal-move lists or pin lists;
their exactness is the adapter contract, protected by adapter tests. State cross-binding,
duplicate data and inconsistent captures/geometry must fail closed with Calliope errors.
Implementation smoke must record actual adapter observation counts, frame/move counts and
wall time for position and bounded-line analysis. Any experimental round-trip comparison
must be explicitly labelled as a development measurement, not an enabled validation path.

## Transition semantics

Geometric footprint changes compare source identities through the already validated P5
correspondence. Use target squares as geometry: moved-piece-only location change does not
itself establish improvement. Record added/removed target squares and occupied-target
partition changes; these are different observations. A footprint count may stay constant
while strategically relevant target squares change.

Ray changes pair source identity and direction. Compare concrete visible target squares
and blocker sequences, mapping blocker identities through P5. Raw PieceRef relocation
alone must not pretend a blocker was replaced by a different physical piece. Capture and
promotion can remove/add rays; represent missing before/after rays explicitly.
For promoted pawns, the initial identity is retained by existing line histories.

Do not subtract before/after legal-move counts as an improvement metric: the side to move
flips, so one state's observation becomes None in the other. Both snapshots remain
available. Same-side future-frame comparisons can be explicitly requested later; they
still do not establish tactical safety or value.

An edge-empty/unblocked ray, first blocker change, opened attack footprint or extra legal destination
is a fact, not proof that a useful line opened, a piece improved or a move is good.

## Costs and limits

Fixed board bounds: 64 square records; at most 32 piece records; at most eight rays per
slider, at most seven squares per ray. They do not add search branches. Structural move
checks scale with the adapter's current legal moves but do not reparse FEN per move.
P4/P6 frame observations still reconstruct boards; measure before claiming cheap summaries.
Line frames obey existing max_plies 1..256 (default 64). No new nested engine budgets.
Keep lists canonical, avoid copying the same full board into every relation record, and
reuse structural frames. Request-local caches are deferred unless measurements justify
them; do not change P5 purely for this packet.

## Acceptance and forbidden semantics

| Case | Required observation |
| --- | --- |
| Pinned attacker | Geometric attack exists; illegal capture absent |
| In-check piece | Geometry retained; only legal check responses listed |
| Friendly/enemy first blocker | Visible ray includes blocker; beyond it is not attacked |
| Two blockers, nearest moves | New visibility stops at the second blocker |
| Unblocked/edge-empty ray | Distinguish non-empty clear path from zero-square direction |
| Knight/pawn | Footprints included, no slider rays manufactured |
| Promotion choices | Four legal actions, one target; promoted slider gets applicable rays |
| En passant | Landing and victim squares distinct; ray effects follow actual removal |
| Castling | One legal king action, both physical moves retained in structural delta |
| Side flips | Opponent legal fields None; no fabricated mobility delta |
| Same-type identity permutation | Corrected TransitionAnalyzer rejects before activity diff |
| Color/rank mirror | Geometry mirrored; directions/support and side context consistent |
| Same count, changed targets | Target changes recorded rather than hidden by count |
| Incorrect ids/duplicate moves/capture mismatch | Typed refusal, no partial result |
| Malformed stored projections | Reject wrong geometry/subsequence, overlapping or missing partitions, P4 mismatch |
| EP field with no EP action | e3 after e2e4 creates no manufactured capture |
| Missing/extra capture UCI | Reject both inconsistent capture directions; SAN differences alone accepted |
| Pawn advance/castling vs attacks | Legal targets need not belong to footprint; canonical king castle target |
| Malformed pin | Reject wrong pinner/pinned/king binding or ray occupant order |
| Line step diffs | Frame and step counts/bindings exact, no second replay, no duplicate frame observation |

Tests must cover corresponding normal cases and close counterexamples, ray/P4 agreement,
and line frame binding. For color/rank mirroring, match transformed directions (df, -dr),
not tuple indexes, because direction sorting changes. Limit rejection must precede any
new activity observation.
Rerun affected foundation/identity/python-chess/composition/facade tests only. Do not add
CI, full pytest or real-engine suites without a concrete finding that warrants them.

Forbidden outputs: safe square, winning exchange, positional compensation, best move,
forced line, opponent has no moves (when not on move), improved mobility solely from
attack count, and automatic P10 claims. These need future verification contracts.

## Delivery sequence

1. Independent design review: READY / READY_WITH_CORRECTIONS / NOT_READY.
2. Apply corrections and freeze definitions/contracts before implementation.
3. Implement position activity, then transition/line wrappers in one bounded packet.
4. Focused acceptance and measured smoke; independent implementation review.
5. Integrate only after review. Next packet can add king-zone structural observations or
   engine-line explanation discovery; neither is silently included in activity_v1.

## Independent A1 review disposition

Reviewed design head: `75b55ab8b0dd2e490e7b8d070509e9f5c8a14a0a`.
Verdict: READY_WITH_CORRECTIONS; reviewer permits implementation after D1/D2 contracts
are resolved, with D3-D7 settled in the same definition freeze.

| Finding | Frozen disposition |
| --- | --- |
| D1 | Ray/destination/count properties; stored projections validated locally and against retained P4 anchor |
| D2 | Captures indexed by P4 landing square, EP record only, bidirectional UCI consistency |
| D3 | No destination-subset-of-footprint invariant; canonical king castle destination |
| D4 | edge-empty versus unblocked terminology |
| D5 | Structural checks always; no default same-producer per-move round-trip; smoke records costs |
| D6 | Pin binding checked against existing ray occupants |
| D7 | Include frame and step activity results; private structural-frame entry retains validation |
| D8 | Mirror rays by transformed direction, not index |

Reviewer-reported premise probes: 150 random legal positions, 1,265 sliders (8 pinned),
all ray/P4 visibility agreements held. These are external review observations, not a
new implementer test run. The present packet changes documentation only; no tests or CI
are run for this contract correction. Implementation remains the next separate packet.

## Implementation record

Implementation branch: `expansion/positional-activity-foundation`, based on the frozen
contract commit `256e2ee`. New files only, besides documentation:

- `src/calliope/domain/analysis/activity.py`
- `src/calliope/services/position/activity.py`
- `tests/unit/domain/test_activity_models.py`
- `tests/unit/services/position/test_activity_foundation.py`

P4/P5/P6 protocols, the python-chess adapter, positional v1 services, shared identity,
`calliope.errors`, `services.position` package exports, composition and public schema are
unchanged.

### Details fixed during implementation

The frozen contract left these shapes open; they are recorded here for review.

- Errors reuse existing types. Record and projection mismatches (including ray/P4
  disagreement and pin/ray disagreement) raise `IncompatiblePositionObservationError`.
  Tactical binding failures (steps 2-4) raise `IncompatibleTacticalContextError`.
  Transition binding failures raise `IncompatibleBoardDeltaError`. No new error class.
- Domain records do not import application ports, so absolute pins are copied into a
  domain-level `AbsolutePin(pinner, pinned, king)`, sorted by pinned square.
- Canonical orders: squares and pieces by board index (a1..h8), attackers by attacker
  square, moves and captures by UCI, rays by source square then (df, dr).
- `PieceActivity.legal_captures_now` holds P4 `LegalCapture` records (victim retained).
- `AttackFootprintChange(before, after | None, added_targets, removed_targets,
  occupancy_changes)` is emitted per physical piece only when something changed; a
  captured piece has `after=None` and every former target removed.
  `TargetOccupancyChange(square, before, after)` covers squares that stayed targets but
  changed between empty/friendly/enemy, separate from added/removed targets.
- `RayChange(direction, before | None, after | None, added_visible, removed_visible,
  blockers_changed)` pairs slider identity and direction through P5. `blockers_changed`
  compares before occupants mapped through correspondence (captured -> None) with after
  occupants, so a blocker sliding along the same ray is not a different piece. A
  promoted slider has `before=None` rays; a captured slider has `after=None` rays.
- Validation step 1 checks ids and the positional version only; it does not recompute
  positional_v1 features, which remain the positional foundation's responsibility.

### Verification

- New tests: 84 (49 service acceptance, 35 domain malformed-record). Every acceptance row
  above has at least one normal case and a close counterexample.
- Affected group: 220 passed / 0 failed —
  `tests/unit/services/position tests/unit/domain/test_activity_models.py
  tests/unit/services/explanation/test_piece_identity.py tests/integration/python_chess
  tests/unit/test_composition.py tests/unit/test_engine_facade.py`.
- Development fuzz outside the suite: 150 seeded lines biased toward castling, en passant
  and promotion, 17,855 plies through `ActivityLineAnalyzer` with `max_plies=256`, with no
  false rejection.
- Changed Python files pass Ruff check/format. No full pytest, real-engine suite or CI.

### Development smoke (not a production benchmark)

One development host, python-chess adapter, no caching:

| Workload | Wall time | Adapter calls |
| --- | --- | --- |
| Start position, `ActivityAnalyzer.analyze` | 4.6 ms | 1 observe_position, 1 observe_tactics |
| Middlegame position | 5.9 ms | 1 observe_position, 1 observe_tactics |
| 64-ply line, structural `LineAnalyzer` | 0.34 s | 257 observe_position, 64 legal_move_from_uci, 128 apply_move |
| Same line, `ActivityLineAnalyzer` (65 frames, 64 steps) | 0.68 s | the above + 65 observe_tactics |

Activity adds exactly one tactical observation per frame, no extra P4 observation and no
per-move `ChessRulesPort` round-trip. Under cProfile, the `ActivityFacts` anchor validation
(re-projecting squares, geometry and rays) is about 40% of the added activity time, because
each projection runs once to build and once to validate. A request-local reuse of those
projections is a measured follow-on candidate, not part of this packet.
