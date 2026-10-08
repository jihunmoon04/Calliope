# Fact engine — packet F2-D: board-geometry families, deltas, `ensure` and tiers

Status: **rev. 2 — independent F2-D review READY_WITH_CORRECTIONS applied** (design only).
Date: 2026-10-08. Base: `main @ c8c4096` (F1 merged). Review: rev. 1 `46c2b12`,
READY_WITH_CORRECTIONS (F2D-C1–C10, N1–N7); section 12 maps every finding.

Parent design: [`fact-engine-a0-design.md`](fact-engine-a0-design.md) rev. 4 (sections 1, 5,
6.3–6.10, 13; amended by this packet in sections 1, 6.8 and 6.10). F1 record:
[`fact-engine-f1-implementation.md`](fact-engine-f1-implementation.md).

## 0. Scope

This packet freezes the exact definitions, record shapes, dependencies and test obligations of:
- `pieces`, `squares`, `lines`, `pawns`, `king` (all POSITION scope);
- `delta` (EDGE) and `same_side_delta` (SPAN);
- `FactEngine.ensure`, the family tiers, and dependency resolution across scopes (closes F1R-N1).

No engine work is involved (F4); `patterns` is F3.

**Legacy evidence** is the frozen MVP (tag `legacy-mvp-g0`), used only as evidence. Short names
used below:

| Short name | Path |
| --- | --- |
| ACT D1–D8 | `docs/legacy/positional-activity-design.md` |
| PF | `docs/legacy/positional-foundation.md` |
| SLS §4 | `docs/legacy/scenario-line-summary-design.md` |
| I1D M3 / D-cases | `docs/legacy/observation-i1d-played-transition-freeze.md` and `docs/legacy/corpus/played-transition-i1d-v1.json` |
| I2I3 L2 | `docs/legacy/observation-bridge-i2i3-joint-design.md` |

Two inventories of legacy code and documents (not committed) found the following:

1. The legacy geometry primitives are sound and are reused as definitions:
   - python-chess attack sets;
   - near-to-far ray occupants;
   - absolute pins validated against ray contents;
   - `positional_v1` isolated, doubled, passed, supporters and files;
   - identity-keyed defences and pins;
   - footprint and ray deltas.
2. Eleven legacy defects were reproduced. §8 lists each with its FEN and the definition here
   that removes it.
3. Legacy never defined these, so they are new definitions here:
   - backward pawns, phalanx, chains, islands, enemy pawn cones;
   - everything in `king`;
   - x-ray relations and batteries;
   - the lowest attacker;
   - attacks on pieces keyed by identity;
   - `same_side_delta`.

## 1. Common rules for every F2 family

1. **Geometry means python-chess attack sets**, the legacy primitive, reused:
   - `Board.attacks_mask(sq)`;
   - a slider stops at, and includes, the first piece of either colour;
   - a pawn attacks its two forward diagonals only. That includes an empty en passant target
     square, but never its push square and never the en passant **victim** square (F2D-C1);
   - a king attacks its neighbours regardless of defence;
   - an absolutely pinned piece keeps its full attack set.
2. **Legal data has one source: `status`** (F2D-C2).
   - Every legal field in `pieces` and `king` is a projection of `status.legal_moves` /
     `status.legal_captures`. These families declare `requires=("status",)` and never generate
     legal moves themselves.
   - Legal fields exist only for the side to move; for the other side they are `NOT_OBSERVED`,
     never empty or zero (legacy E7).
3. **En passant.**
   - The en passant capturer attacks the empty target square, not the victim. The victim
     therefore has no geometric pawn attacker.
   - The victim is still `legally_capturable_now`, through the en passant legal capture.
   - The en passant flag comes only from `status.legal_captures` (`is_en_passant`). This removes
     legacy defects E5 and E6.
4. **Every relation carries the participants' type and an `absolutely_pinned` boolean.**
   - This applies to attackers, defenders, square attackers and zone attackers.
   - The king and pinned pieces are included and flagged, never dropped (legacy E1–E3; F2D-C5).
5. **POSITION families see only the position** (F2D-C7).
   - They receive a board rebuilt from the `PositionKey`: placement, side, castling, legal en
     passant, clocks 0 and an empty move stack. They never receive the node's board.
   - So a record depends on nothing that differs between transpositions, or between an eager
     computation and an `ensure`.
6. **References.**
   - POSITION records refer to squares, which the node resolves to `PieceId`s (A0 §4).
   - EDGE and SPAN records are keyed by `PieceId`.
7. **Canonical order:**
   - squares in board order a1…h8;
   - pieces by square;
   - rays by direction (df, dr) in lexicographic order;
   - ray contents near to far, never re-sorted (SLS §4);
   - piece-type sets in `PieceType` order.
8. **No evaluative names** (A0 §1). Counts are named for what they count.
9. **Computation.**
   - Each POSITION family is computed once per `PositionKey`, from bitboards, without
     re-validation.
   - Targets: ≤ 2 ms per position for the five POSITION families together, and ≤ 1 ms per edge
     for `delta`.
   - The review prototype measured 0.74 ms and 0.025 ms (aarch64, 2 CPUs).

## 2. `pieces` (POSITION, RULE; `pieces_v1`; requires `status`)

One record per piece, keyed by square.

| Field | Definition |
| --- | --- |
| `square`, `color`, `type` | from the board |
| `attacks` | `attacks_mask(square)`, split into `empty`, `friendly` and `enemy` target squares. The three parts are disjoint and cover the footprint (ACT D1) |
| `attackers` | for each enemy piece P with `square ∈ attacks_mask(P)`: `(P.square, P.type, P.absolutely_pinned: bool)` |
| `defenders` | the same, for friendly pieces other than itself |
| `attacker_count`, `defender_count` | lengths of the two lists |
| `lowest_attacker_types` | `Defined("piece_order_v1", types)`: the attacker types of the lowest rank under K > Q > R > B = N > P, as a tuple in `PieceType` order. The set is over all geometric attackers, pinned ones and the king included. Empty if there are no attackers |
| `attacked_without_defender` | `attacker_count ≥ 1 ∧ defender_count = 0` (A0 N3; replaces legacy `hanging_now`). For a king it is computed the same way and is purely geometric (a checked king is in `status`) |
| `attackers_exceed_defenders` | `attacker_count > defender_count` |
| `absolutely_pinned` | see the pin definition below |
| `legal_destinations` | side to move: the distinct destination squares of this piece's moves in `status.legal_moves` (castling destination = g1/c1/g8/c8; four promotions = one destination); otherwise `NOT_OBSERVED` (ACT D3: not a subset of `attacks`) |
| `legal_moves` | side to move: this piece's moves in `status.legal_moves`; otherwise `NOT_OBSERVED` |
| `legally_capturable_now` | piece of the side **not** to move: its square is the victim square of some capture in `status.legal_captures` (en passant included); otherwise `NOT_OBSERVED` |

**Absolute pin** (F2D-C4). A piece X of colour C is absolutely pinned iff all of these hold:
1. walking from C's king in a direction d, the first occupant is X;
2. the next occupant after X is an enemy slider that moves along d (a rook or queen
   orthogonally, a bishop or queen diagonally).

The record is `(pinner square, direction)`, where `direction` is the unit step **from the king
toward the pinner**.

- python-chess `pin_mask` is only a cross-check, called with X's own colour. It returns the
  whole line, may report empty squares or enemy pieces, and cannot identify the pinner.
- The ray rule above is the definition. Fixtures:
  - `3r3k/3r4/8/3N4/3K4/8/8/7r w`: the pin mask contains d7 and d8; the pinner is d7;
  - a wrong-colour query;
  - an empty-square query.
- **En passant pins** are not absolute pins. The illegal en passant capture is simply missing
  from `status.legal_moves`. The node keeps no other trace: its FEN and `PositionKey` drop the
  pseudo-legal en passant square (F2D-N1). F2 records no extra fact for it.
- **Battery backers** (legacy E4: a rear battery piece is not a defender) are correct geometry;
  they appear in `lines.xray` and `lines.batteries`.

## 3. `squares` (POSITION, RULE; `squares_v1`)

For each of the 64 squares:
- `occupant`: (color, type) or `None`;
- `white_attackers`, `black_attackers`: (square, type, absolutely_pinned) per attacking piece;
- `white_count`, `black_count`.

Invariant: on an occupied square, the occupant colour's attackers are its `pieces.defenders`,
and the other colour's attackers are its `pieces.attackers`.

Not included: legacy `current_legal_captures`. It depends on the side to move and duplicates
`status`.

## 4. `lines` (POSITION, RULE; `lines_v1`)

**Rays.** One `Ray(source, direction, squares, occupants)` per slider and applicable direction.
- Bishops have the 4 diagonals, rooks the 4 orthogonals, queens all 8.
- `squares` runs to the board edge.
- `occupants` lists every piece on the ray, near to far, as (square, color, type).

The derived parts below are stored:

| Field | Definition |
| --- | --- |
| `edge_empty` | `squares = ()` (ACT D4; distinct from `unblocked`) |
| `unblocked` | `squares ≠ () ∧ occupants = ()` |
| `first_blocker` | `occupants[0]` or `None` |
| `visible` | squares up to and including the first blocker. Invariant: the union over a slider's rays equals `attacks_mask(slider)` |
| `xray` | if there are ≥ 2 occupants: the squares strictly after the first blocker up to and including the second, marked `XRAY`, plus the `(first, second)` occupants. **Never an attack** |

**Batteries** (F2D-C3). A battery is an **unordered** pair of same-colour sliders {A, B} such
that:
- B is the first blocker on a ray of A;
- both move along that line (rooks or queens on a rank or file; bishops or queens on a
  diagonal).

It is recorded once, as `Battery(pieces=(lower square, higher square), line=(df, dr))`, with the
direction normalized to point from the lower to the higher square.

- A pawn, knight or king in front is never part of a battery. A rook and a bishop never form
  one.
- Three aligned sliders give two batteries (consecutive pairs).

## 5. `pawns` (POSITION, DEFINED; `pawns_v1`)

Forward and behind are relative to the pawn's colour (White forward = rank +1). File distance
means |file − file′|.

| Fact | Definition |
| --- | --- |
| `isolated` | no friendly pawn on a file at distance 1 (PF, `positional_v1`) |
| `doubled` | ≥ 2 friendly pawns on its file; every pawn on that file is marked (PF) |
| `passed` | no enemy pawn at file distance ≤ 1 strictly ahead (PF) |
| `own_pawn_ahead` | a friendly pawn on the same file strictly ahead. **New.** Recorded beside `passed` instead of changing it: legacy marks both pawns of a doubled passed pair as passed (defect S1) |
| `supporters` | friendly pawns on a file at distance 1 exactly one rank behind (PF; pinned ones included) |
| `phalanx` | friendly pawns on a file at distance 1 on the same rank |
| `backward` | not `isolated`; no friendly pawn at file distance 1 on the same rank or behind; and its stop square (one ahead) is attacked by an enemy pawn. Whether the stop square is occupied, and whether a double step exists, do not affect the flag. Geometric only; no claim about advancing safely |
| `chains` | the connected components (≥ 2 pawns) of the graph whose edges are supporter relations. Each is recorded as its member squares, its bases (members with no supporter in the component) and its heads (members supporting no member). Branching chains have several bases or heads |
| `islands` | per colour: maximal runs of adjacent files that contain at least one own pawn, as file tuples |
| `files` | per file: white and black pawn counts, and a `state` ∈ {`OPEN`, `SEMI_OPEN_WHITE`, `SEMI_OPEN_BLACK`, `CLOSED`}. `OPEN` = no pawns. `SEMI_OPEN_<C>` = none of C's pawns and ≥ 1 enemy pawn. `CLOSED` otherwise |
| `outside_enemy_pawn_cones` | per colour C: squares in no current enemy pawn's span. The span of an enemy pawn is every square on a file at distance 1, on ranks strictly ahead of that pawn up to its last rank, ignoring blockers (F2D-N5). It describes the current pawn set, not the future (A0 N2) |

A promoted pawn is no longer a pawn and leaves every pawn fact.

## 6. `king` (POSITION, DEFINED; `king_zone_v1`; requires `status`, `squares`, `pawns`)

Per king:

| Fact | Definition |
| --- | --- |
| `square` | the king's square |
| `zone` | the king's square plus its neighbour squares (`attacks_mask(king)`), each with its enemy attackers from `squares` as (square, type, absolutely_pinned) |
| `shield` | own pawns on the king's file and the adjacent files, on the first and second rank in front of the king (forward relative to colour). Empty when the king is on its colour's last rank |
| `files_near` | for the king's file ± 1 on the board: the `pawns.files` state |
| `flight_squares` | side to move: destinations of the king's moves in `status.legal_moves`, excluding castling, labelled `LEGAL`. Other side: neighbour squares not occupied by its own pieces and not attacked by enemy pieces, labelled `GEOMETRIC` |

- **No king removal is needed for the geometric variant.** The side not to move is never in
  check in a legal position. The review checked the definition against null-move legal king
  moves on 17,473 random positions, with 0 mismatches.
- **Zone attackers are geometric** (F2D-N2). A square behind a **checked** king on the
  checking line has no geometric attacker, because the king blocks the ray. Example:
  `8/8/8/R3k3/8/8/8/K7 b`, square f5. The legal flight squares of the side to move are
  nevertheless correct, because they come from `status`.

## 7. Deltas

### 7.1 `delta` (EDGE, keyed by `PieceId`; `delta_v1`; requires `pieces`, `lines`, `pawns`, `king` at both ends)

`delta` holds the set differences between the parent's and child's POSITION records for
side-independent facts. Pieces are mapped through the edge's identity step (A0 §4), so a moved
piece is the same piece.

Each component lists `began` and `ended` entries, or `(before, after)` pairs:

| Component | Key | Source | Class |
| --- | --- | --- | --- |
| `square_control` | (attacker id, square) | `pieces.attacks` | RULE |
| `piece_attacks` | (attacker id, victim id). **New:** catches a target walking into an attack (legacy D1) | `pieces.attackers` | RULE |
| `piece_defences` | (defender id, defended id) | `pieces.defenders` | RULE |
| `piece_flags` | piece id → (before, after) of `attacked_without_defender`, `attackers_exceed_defenders` (F2D-C8) | `pieces` | RULE |
| `pins` | (pinner id, pinned id, king id) | `pieces.absolutely_pinned` | RULE |
| `xrays` | (slider id, first id, second id) | `lines.xray` | RULE |
| `batteries` | unordered (id, id) | `lines.batteries` | RULE |
| `pawn_flags` | pawn id → (before, after) of `isolated`, `doubled`, `passed`, `own_pawn_ahead`, `backward` | `pawns` | DEFINED |
| `pawn_supports` | (supporter id, supported id) (F2D-C8; legacy tracked support removal) | `pawns.supporters` | DEFINED |
| `files` | file → (before, after) of (white count, black count, state) | `pawns.files` | DEFINED |
| `islands` | colour → (before, after) | `pawns.islands` | DEFINED |
| `zone_attacks` | (king id, square, attacker id) | `king.zone` | DEFINED |
| `shield` | (king id, pawn id) | `king.shield` | DEFINED |

Rules:
- **Only changes are recorded.** Unmoved pieces are included whenever their facts changed
  (I1D M3, D19, D20).
- **A captured piece** ends every relation it took part in; its flags appear with
  `after = Absent(CAPTURED)`.
- **A promoted pawn** appears in `pawn_flags` with `after = Absent(PROMOTED)` and continues in
  `piece_flags` under the same id.
- **Not in `delta`:**
  - side-dependent facts (legal moves and destinations, captures, `legally_capturable_now`,
    legal flight squares) go to `same_side_delta`;
  - check changes are in `move` (`gives_check`) and `status`;
  - material changes are in `move` events (A0 §6.10 amended below).
- **Patterns (F3)** get their own EDGE family `pattern_delta`, so `delta_v1` stays fixed when F3
  arrives (A0 §6.10 amended).

### 7.2 `same_side_delta` (SPAN, grandparent → node; `same_side_delta_v1`; requires `status`, `pieces`, `king` at both ends)

This compares a node with its grandparent (same side to move). Pieces are mapped by `PieceId`
across both edges.

| Component | Content |
| --- | --- |
| `pieces` | every piece id of the grandparent's side-to-move set and of the node's: (type at grandparent, type at node). A piece gone at the node is `Absent(CAPTURED)` (F2D-C9). A promotion shows as a type change under the same id |
| `legal_destinations` | per piece id present at both: destinations gained and lost |
| `legal_captures` | (capturer id, victim id) gained and lost |
| `capturable_now` | pieces of the side not to move that became or stopped being `legally_capturable_now`. A piece captured in between is listed as `Absent(CAPTURED)`, never silently dropped |
| `flight_squares` | the moving side's king: legal flight squares gained and lost |
| `legal_move_count` | (grandparent, node) |

- A node with ply < 2 within the tree has a **stored** record
  `NotApplicable("no same-side ancestor in the tree")`. Pre-root history is not a tree node, so
  this includes the root's children.
- The legacy rule "never subtract legal-move counts across a side flip" holds by construction.

## 8. Legacy defects and the definition that removes each

| Defect (reproduced) | FEN / move | Fix |
| --- | --- | --- |
| D1 a target walking into an attack never "begins" | `7k/8/8/8/2n5/8/8/K2R4 b`, `c4d2` | `delta.piece_attacks` keyed by (attacker id, victim id) |
| E1 a pinned defender counts silently | `4r2k/8/8/8/1b2P3/8/3N4/4K3 b` | defenders carry `absolutely_pinned` |
| E2 the king defends a square the enemy attacks | `4r2k/8/6b1/8/4P3/3K4/8/8 b` | defenders carry their type; geometry kept, flagged |
| E3 a king attacker that cannot capture | `8/8/8/3k4/4P3/5P2/8/K7 b` | attackers carry their type; `legally_capturable_now` separate |
| E4 a battery backer is not counted | `3r3k/8/8/3P4/8/8/3R4/3RK3 w` | correct geometry, exposed as `lines.xray` / `batteries` |
| E5 en passant victim: no attacker, yet capturable | `7k/8/8/3pP3/8/8/8/K7 w - d6` | rule §1.3; the two facts are separate by definition |
| E6 en passant masks `hanging` | `7k/8/8/3pP3/8/8/8/K2R4 w - d6` | `attacked_without_defender` is purely geometric |
| E7 `false` instead of unknown for the side to move | `7k/8/8/3n4/8/8/8/K2R4 b` | `NOT_OBSERVED` |
| S1 both doubled pawns passed | `7k/8/8/4P3/4P3/8/8/K7 w` | `own_pawn_ahead` beside `passed` |
| EP-pin not represented | `7k/8/8/KPp4r/8/8/8/8 w - c6` | stated (§2): the capture is absent from `status`; nothing else |
| P1 attacked ∧ ¬defended ≠ capturable | `7k/8/8/4r2b/8/5N2/8/3K4 w` | both facts kept, named distinctly |

## 9. `ensure`, tiers and dependency resolution (closes F1R-N1)

**Registry vs eager set.**
- Every registered family belongs to the session.
- `OpenRequest.families` names the **eager set**. It defaults to all families, and `status`,
  `draw` and `move` are always included.
- The eager set is **closed automatically under `requires`**: asking for `king` also makes
  `status`, `squares` and `pawns` eager.
- A family outside the eager set reads `NotComputed("not requested")` until `ensure` computes
  it.

**`FactEngine.ensure(tree, EnsureRequest(nodes, families)) -> rev`**
- It computes the missing records of `families`, and of their dependencies, for `nodes`. For
  EDGE families that includes the parents; for SPAN families, the grandparents. All records go
  in at one new revision.
- Validation happens before any work. Unknown nodes or families refuse the request, and
  nothing is committed.
- A present record is never recomputed.
- If nothing is missing, `ensure` commits **no** revision and returns the current one
  (F2D-N4).

**Dependency scopes:**

| Family scope | May require | Resolved on |
| --- | --- | --- |
| POSITION | POSITION | the same `PositionKey` |
| NODE | POSITION, NODE | the same node |
| EDGE | POSITION, NODE (both ends), EDGE (this edge) | parent and child |
| SPAN | POSITION, NODE (both ends) | grandparent and node |

`_select` refuses any other combination.

**Context shape** (F2D-C6). `FamilyContext` gains:
- `records`: required records of this target (for EDGE, the child's and this edge's);
- `parent_records`: the parent's required records (EDGE, SPAN);
- `grandparent_records`: the grandparent's required records (SPAN);
- `pieces_maps`: the `PieceId` maps of every node involved;
- `identity_steps`: the identity steps of every edge involved (one for EDGE, two for SPAN).

A family receives exactly its declared records.

**`requires` per F2 family:**

| Family | `requires` |
| --- | --- |
| `pieces` | `status` |
| `squares` | — |
| `lines` | — |
| `pawns` | — |
| `king` | `status`, `squares`, `pawns` |
| `delta` | `pieces`, `lines`, `pawns`, `king` |
| `same_side_delta` | `status`, `pieces`, `king` |

**Tiers.**
- In F2 every node is an input-role node, so the eager set applies to all nodes.
- F4 adds engine-only nodes, which get the A0 §7.5 eager tier (`status`, `material`, `draw`,
  `move`). The rest comes through `ensure`.
- F4 must also give "an engine-only node gains an input role" its own path, because F1's
  `add_child` returns early for existing nodes (F2D-N4).

## 10. Test obligations (F2 implementation)

1. **Independent auditor extension.**
   - It recomputes every F2 field with its own ray walking (no `attacks_mask`, no `pin_mask`)
     and its own pawn rules.
   - Same corpus as F1: four root forms, branches, endgames.
   - Equality checks: legal projections equal `status`; `squares` vs `pieces`; zone attackers
     vs `squares`.
2. **Invariants:**
   - footprint parts are disjoint and cover the attack set;
   - the union of visible ray squares = the attack set;
   - an absolute pin's ray from the king starts with `[pinned, pinner]`;
   - `delta` applied to the parent's relation sets gives the child's;
   - every battery is recorded once.
3. **Equivalences:**
   - a tree built with every family eager equals, record by record, a minimal-eager tree plus
     `ensure` on all nodes;
   - POSITION records are equal across transpositions with different clocks;
   - `ensure` refuses atomically, never recomputes, resolves parent and grandparent
     dependencies, commits nothing when nothing is missing, and keeps pinned views correct.
4. **Colour mirror:** mirrored positions give mirrored records, with directions mapped
   (df, −dr) (ACT D8).
5. **Fixtures adopted from legacy:**
   - the `positional_v1` pawn table, pinned supporter, open / semi-open and mirror tests
     (`tests/unit/services/position/test_positional_foundation.py:53-111`);
   - the activity tests: pinned attacker, in check, first and second blockers, relocated
     blocker, discovery, edge-empty vs unblocked, en passant ray, pin behind a blocker
     (`tests/unit/services/position/test_activity_foundation.py`);
   - I1D D04, D05, D07, D08, D09, D10, D19, D20 (`docs/legacy/corpus/played-transition-i1d-v1.json`);
   - E12 and E15 (`tests/golden/scenario_explanation_cases.json`).
6. **New fixtures:**
   - every row of §8;
   - the pin cases of §2 (line mask with two sliders, wrong colour, empty square);
   - batteries (Rd1+Rd2, Qd1+Bc2, a bishop behind a pawn);
   - `same_side_delta` with a capture, promotion, castling or en passant in either ply.
7. **Mutation check:** the auditor must catch field-level mutations of every family (the F1
   review method).

## 11. Amendments to A0 made by this packet

- **§1 sentinel table** gains `Absent(reason)` with the closed reason set {`CAPTURED`,
  `PROMOTED`}: "the piece no longer exists in the role this fact describes".
- **§6.8:**
  - `UNDEFENDED_ATTACKED` and `ATTACKERS_EXCEED_DEFENDERS` leave `patterns`;
  - they are the `pieces` fields `attacked_without_defender` and `attackers_exceed_defenders`;
  - their changes are in `delta.piece_flags`.
- **§6.10:**
  - `delta` is defined by F2-D §7.1;
  - material changes are `move` events;
  - pattern changes go to a separate EDGE family `pattern_delta` (F3).

## 12. Review dispositions (rev. 1 `46c2b12`: READY_WITH_CORRECTIONS)

| Finding | Disposition |
| --- | --- |
| F2D-C1 en passant wording | rule 1.1 says "never the en passant victim square" |
| F2D-C2 legal data computed twice | `status` is the only legal source; `pieces` / `king` project from it (§1.2, §2, §6) |
| F2D-C3 batteries counted twice | unordered pair, recorded once (§4) |
| F2D-C4 pin direction and pinner | ray definition; direction king→pinner; `pin_mask` only as an own-colour cross-check; fixtures (§2) |
| F2D-C5 pin flag missing on some relations | added to `squares` and the `king` zone; boolean in `pieces`; invariants (§1.4, §3, §6) |
| F2D-C6 `requires` and context shape | per-family table; context fields; automatic closure of the eager set (§9) |
| F2D-C7 POSITION records depending on node data | board rebuilt from the `PositionKey` (§1.5); equivalence tests (§10.3) |
| F2D-C8 A0 change unrecorded; missing components | A0 amendments (§11); `attackers_exceed_defenders`, `piece_flags`, `pawn_supports`, file state defined; `pattern_delta` decided |
| F2D-C9 `same_side_delta` dropped pieces | `pieces` component with `Absent(CAPTURED)` and types; renamed `legal_destinations`; stored `NotApplicable` (§7.2) |
| F2D-C10 sentinel outside A0 | `Absent` added to A0 §1 with a closed reason set (§11) |
| N1 en passant pin trace | wording corrected (§2) |
| N2 square behind a checked king | stated (§6) |
| N3 `lowest_attacker` scope; king flag | stated (§2) |
| N4 empty `ensure`; F4 role-gain path | no revision when nothing is missing; F4 note (§9) |
| N5 cone wording | reworded (§5) |
| N6 legacy path map | short-name table (§0) |
| N7 extra test obligations | added (§10.3, §10.6) |
| Q1 king zone | narrow zone for v1 |
| Q2 backward | stop-square condition only; future-support claims excluded |
| Q3 shapes | `lowest_attacker_types` as a tuple in `PieceType` order; `Absent` as a closed enum |

**STOP** if F2:
- adds an evaluative name;
- drops a relation instead of flagging it;
- records a side-dependent fact for the side not to move;
- diffs side-dependent facts across a side flip;
- computes legal data outside `status`;
- gives a POSITION family anything but the position;
- re-validates trusted records at runtime.
