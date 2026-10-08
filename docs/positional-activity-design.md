# Positional activity foundation — design A1

Status: DRAFT_FOR_INDEPENDENT_DESIGN_REVIEW. No implementation in this packet.
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

A geometric attacker is not necessarily able to capture. An empty attacked square has
no capture by default. En passant records retain both landing and actual captured square;
do not infer the victim from the destination occupant. A current-side capture record
does not imply the opponent has no capture: that opponent is not on move.

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

Absolute pins are copied from the existing tactical observation as rule-level context.
Relative pins and whether removing a defender loses material remain future interpretations.

### Slider rays

For each bishop/rook/queen, enumerate every applicable unit direction (df, dr): four
diagonals for bishops, four orthogonals for rooks, their union for queens. Directions are
sorted lexicographically by (df, dr). Each ray stores:

- source PieceRef and direction;
- all squares from the next square to the board edge, in near-to-far order;
- occupied squares/pieces on that ray in the same order;
- first blocker (or None);
- visible attacked squares, through and including the first blocker, or to the edge.

An outward edge ray exists with empty squares/occupants. The source square is excluded.
Visibility includes the first blocker even if friendly, consistent with P4 attack semantics.
Squares after it are geometric ray information only and never advertised as current
attacks. Blocker color determines occupancy, not whether it can be captured legally.
All blockers are recorded so a later move can be inspected without inventing an attack
behind a second blocker. No X_RAY_ATTACK or LINE_WILL_OPEN claim is emitted.

For every slider, union of visible ray squares must equal its P4 attack footprint.
Mismatch is an incompatible observation, not a fallback to guessed geometry.

## Proposed internal contracts

Use frozen typed dataclasses and canonical tuples, not a generic string/value fact bag.
Names below are proposed contracts for review, not existing production classes.

```text
SquareAccess(square, occupant, white_attackers, black_attackers, current_legal_captures)
PieceActivity(piece, empty_attacks, friendly_attacks, enemy_attacks,
              legal_moves_now | None, legal_destinations_now | None,
              legal_captures_now | None)
SliderRay(source, direction, squares, occupants, first_blocker, visible_squares)
ActivityFacts(position_id, side_to_move, definition_version="activity_v1",
              squares, pieces, rays, absolute_pins)
ActivityPositionAnalysis(structural: PositionAnalysis, activity: ActivityFacts)
ActivityTransitionAnalysis(structural: TransitionAnalysis,
                           before_activity, after_activity,
                           attack_footprint_changes, ray_changes)
ActivityLineAnalysis(structural: LineAnalysis, activity_frames)
```

Activity frames have exactly len(transitions)+1 entries and match structural frame ids.
Retain positional_v1 definitions unchanged; activity_v1 has its own definition version.
Existing PositionAnalysis/TransitionAnalysis/LineAnalysis schemas need not change.

## Composition and affected files

Proposed new domain module: domain/analysis/activity.py.
Proposed new service module: services/position/activity.py.

- ActivityAnalyzer takes existing PositionAnalyzer, ChessRulesPort and TacticalObservationPort. analyze
  observes a position; an internal method can consume a trusted PositionAnalysis from
  transition/line replay to avoid repeating P4 feature extraction.
- ActivityTransitionAnalyzer first invokes the existing corrected TransitionAnalyzer,
  then derives activity for its before/after states and compares geometric observations.
- ActivityLineAnalyzer first invokes existing LineAnalyzer with its limit, then attaches
  activity to those exact frames. No second replay or alternative line budget.
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
3. Legal UCI identities are unique/canonical and their source piece belongs to the mover.
   Canonicalize/validate every observation move through ChessRulesPort once for this
   packet; count the cost in the development smoke. Ignore supplied SAN for identity.
   This validates returned candidates, not completeness of a malicious move producer.
4. The capture subset of tactical legal moves agrees with P4 legal captures (including
   promotion and en passant). Absolute-pin pieces belong to the observed position.
5. Attack references exist in the observed piece map; ray visibility agrees with P4.

ChessRulesPort is therefore also a required ActivityAnalyzer dependency. The design does
not claim to prove the completeness of arbitrary malicious legal-move lists or pin lists;
their exactness is the adapter contract, protected by adapter tests. State cross-binding,
duplicate data and inconsistent captures/geometry must fail closed with Calliope errors.

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

An empty ray, first blocker change, opened attack footprint or extra legal destination
is a fact, not proof that a useful line opened, a piece improved or a move is good.

## Costs and limits

Fixed board bounds: 64 square records; at most 32 piece records; at most eight rays per
slider, at most seven squares per ray. They do not add search branches. Legal-action
validation costs scale with the adapter's current legal moves and repeat board parsing
in the current stateless adapter; measure this before claiming cheap activity summaries.
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
| Clear/edge ray | Near-to-far canonical squares, including empty outward ray |
| Knight/pawn | Footprints included, no slider rays manufactured |
| Promotion choices | Four legal actions, one target; promoted slider gets applicable rays |
| En passant | Landing and victim squares distinct; ray effects follow actual removal |
| Castling | One legal king action, both physical moves retained in structural delta |
| Side flips | Opponent legal fields None; no fabricated mobility delta |
| Same-type identity permutation | Corrected TransitionAnalyzer rejects before activity diff |
| Color/rank mirror | Geometry mirrored; directions/support and side context consistent |
| Same count, changed targets | Target changes recorded rather than hidden by count |
| Incorrect ids/duplicate moves/capture mismatch | Typed refusal, no partial result |

Tests must cover corresponding normal cases and close counterexamples, ray/P4 agreement,
and line frame binding. Limit rejection must precede any new activity observation.
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
