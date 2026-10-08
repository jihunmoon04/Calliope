# Fact engine — packet F2-D: board-geometry families, deltas, `ensure` and tiers

Status: **DRAFT / AWAITING INDEPENDENT F2-D REVIEW** (design only). Date: 2026-10-08.
Base: `main @ c8c4096` (F1 merged). Parent design:
[`fact-engine-a0-design.md`](fact-engine-a0-design.md) rev. 4, sections 5, 6.3–6.10 and 13.
F1 record: [`fact-engine-f1-implementation.md`](fact-engine-f1-implementation.md).

## 0. Scope

This packet freezes the exact definitions, record shapes and test obligations of:
- `pieces`, `squares`, `lines`, `pawns`, `king` (all POSITION scope);
- `delta` (EDGE) and `same_side_delta` (SPAN);
- `FactEngine.ensure`, the family tiers, and dependency resolution across scopes (closes F1R-N1).

No engine work is involved (F4); `patterns` is F3.

**Legacy evidence** is the frozen MVP (tag `legacy-mvp-g0`; `docs/legacy/`), used only as
evidence. Two inventories of legacy code and documents were made for this packet. Their
conclusions are:

1. The legacy geometry primitives are sound and are reused as definitions:
   - python-chess attack sets;
   - near-to-far ray occupants;
   - absolute pins validated against ray contents;
   - `positional_v1` isolated, doubled, passed, supporters and files;
   - P5 identity-keyed defences and pins;
   - activity footprint and ray deltas.
2. Eleven legacy defects were reproduced (§8). Each is fixed by a definition below.
3. Legacy never defined these, so they are new definitions here:
   - backward pawns, phalanx, chains, islands, enemy pawn cones;
   - everything in `king`;
   - x-ray relations and batteries;
   - the lowest attacker;
   - attacks on pieces keyed by identity;
   - `same_side_delta`.

## 1. Common rules for every F2 family

1. **Geometry means python-chess attack sets**, the legacy primitive, reused:
   - `Board.attacks_mask(sq)` and `attackers_mask(color, sq)`;
   - a slider stops at, and includes, the first piece of either colour;
   - a pawn attacks its two forward diagonals only (never its push square, never an en
     passant target);
   - a king attacks its neighbours regardless of defence;
   - an absolutely pinned piece keeps its full attack set.
2. **Legal means `Board.legal_moves`**, and is recorded only for the side to move. For the
   other side the value is `NOT_OBSERVED`, never empty or zero (legacy ACT; defect E7).
3. **En passant.**
   - The en passant capturer is **not** a geometric attacker of the victim: it attacks the
     empty target square.
   - The victim is still `legally_capturable_now`, through its legal capture.
   - The en passant flag of a capture comes only from `is_en_passant`.
   - This removes the legacy inconsistency (defects E5, E6).
4. **Every relation carries the participants' types and pin status** instead of being filtered:
   - the king as attacker or defender, and pinned attackers or defenders, are included and
     flagged;
   - consumers see them and decide; F2 never drops them (defects E1, E2, E3).
5. **Square references inside POSITION records are squares.** The node resolves them to
   `PieceId`s (design §4). EDGE and SPAN records are keyed by `PieceId`.
6. **Canonical order:**
   - squares in board order a1…h8;
   - pieces by square;
   - rays by direction (df, dr) in lexicographic order;
   - ray contents near to far, never re-sorted (legacy SLS §4).
7. **Names.** No evaluative names (design §1). Counts are named for what they count (for
   example `geometric_attackers`, never "mobility").
8. **Computation.**
   - Each POSITION family is computed **once per `PositionKey`**, directly from bitboards, in
     one pass, without re-validation.
   - Legacy `activity_v1` cost 5.6 ms per position, mostly SAN for every move and
     re-projection in `__post_init__`. The F2 target is ≤ 2 ms for all five POSITION families
     together (§9).

## 2. `pieces` (POSITION, RULE; `pieces_v1`)

One record per piece, keyed by square.

| Field | Definition |
| --- | --- |
| `square`, `color`, `type` | from the board |
| `attacks` | `attacks_mask(square)`, split into `empty`, `friendly` and `enemy` target squares. The three parts are disjoint and cover the footprint (legacy ACT D1) |
| `attackers` | for each enemy piece P with `square ∈ attacks_mask(P)`: `(P.square, P.type, P.absolutely_pinned)` |
| `defenders` | the same for friendly pieces other than itself |
| `attacker_count`, `defender_count` | lengths of the two lists |
| `lowest_attacker` | `Defined("piece_order_v1", types)`: the attacker types of the lowest rank under K > Q > R > B = N > P (a set, because B = N). Empty if there are no attackers |
| `attacked_without_defender` | `attacker_count ≥ 1 ∧ defender_count = 0` (design N3; replaces legacy `hanging_now`) |
| `absolutely_pinned` | `None`, or `(pinner square, direction)` for an absolute pin (exactly one piece, this one, between its king and an enemy slider moving along that line; python-chess `pin_mask`). The legacy ray check `occupants[:2] == (pinned, king)` is kept as an F2 test invariant |
| `legal_moves` | side to move: canonical UCI moves of this piece; otherwise `NOT_OBSERVED` |
| `legal_destinations` | side to move: distinct destination squares (castling destination = g1/c1/g8/c8; four promotions = one destination); otherwise `NOT_OBSERVED` (legacy ACT D3: not a subset of `attacks`) |
| `legally_capturable_now` | piece of the side **not** to move: some legal capture removes it (en passant included); otherwise `NOT_OBSERVED` |

Notes:
- **En passant pins.** An en passant capture that is illegal because both pawns leave a rank
  between king and enemy slider is not an absolute pin. It is visible only as the missing
  legal move (legacy defect EP-pin). F2 records no extra fact for it.
- **Battery backers.** A rear battery piece is not a defender or attacker (legacy E4 is correct
  geometry); it appears in `lines` x-ray relations.
- **Overlap with F3.** `UNDEFENDED_ATTACKED` and `ATTACKERS_EXCEED_DEFENDERS` (design 6.8) are
  plain functions of these counts. F3 drops them from `patterns` and refers to `pieces`, so the
  same fact never exists twice.

## 3. `squares` (POSITION, RULE; `squares_v1`)

For each of the 64 squares:
- `occupant`: (color, type) or `None`;
- `white_attackers`, `black_attackers`: (square, type) per attacking piece;
- `white_count`, `black_count`.

Not included: legacy `current_legal_captures` per square. It depends on the side to move,
duplicates `status`, and would contaminate `delta`.

## 4. `lines` (POSITION, RULE; `lines_v1`)

**Rays.** One `Ray(source, direction, squares, occupants)` per slider and applicable direction.
- Bishops have the 4 diagonals, rooks the 4 orthogonals, queens all 8.
- `squares` runs to the board edge.
- `occupants` lists every piece on the ray, near to far, as (square, color, type).

The derived parts below are stored, because they are cheap and consumers must not derive them:

| Field | Definition |
| --- | --- |
| `edge_empty` | `squares = ()` (legacy ACT D4: distinct from `unblocked`) |
| `unblocked` | `squares ≠ () ∧ occupants = ()` |
| `first_blocker` | `occupants[0]` or `None` |
| `visible` | squares up to and including the first blocker. Invariant: the union over a slider's rays equals `attacks_mask(slider)` |
| `xray` | if there are ≥ 2 occupants: the squares strictly after the first blocker up to and including the second, marked `XRAY`, plus `(first, second)` occupants. **Never an attack** |

**Batteries.** `Battery(rear, front, direction)` where:
- `front` is the first blocker on a ray of slider `rear`;
- `front` has the same colour;
- `front` is a slider that also moves along `direction` (a rook or queen orthogonally, a bishop
  or queen diagonally).

Longer batteries appear as consecutive pairs.

## 5. `pawns` (POSITION, DEFINED; `pawns_v1`)

Forward and behind are relative to the pawn's colour (White forward = rank +1). File distance
means |file − file′|.

| Fact | Definition |
| --- | --- |
| `isolated` | no friendly pawn on a file at distance 1 (legacy `positional_v1`) |
| `doubled` | ≥ 2 friendly pawns on its file; every pawn on that file is marked (legacy) |
| `passed` | no enemy pawn at file distance ≤ 1 strictly ahead (legacy) |
| `own_pawn_ahead` | a friendly pawn on the same file strictly ahead. **New.** Recorded beside `passed` instead of changing it: legacy marks both pawns of a doubled passed pair as `passed` (defect S1). Both facts are stated, so no rule is hidden |
| `supporters` | friendly pawns on a file at distance 1 exactly one rank behind (legacy; pinned ones included) |
| `phalanx` | friendly pawns on a file at distance 1 on the same rank |
| `backward` | not `isolated`; no friendly pawn at file distance 1 on the same rank or behind; and its stop square (one ahead) is attacked by an enemy pawn. Geometric only; no claim about advancing safely |
| `chain` | the connected component of the pawn under the relation "supports or is supported by". Recorded per component (≥ 2 pawns) as its member squares, its bases (members with no supporter) and its heads (members supporting no member) |
| `islands` | per colour: maximal runs of adjacent files that contain at least one own pawn, as file sets |
| `files` | per file: white and black pawn counts; `open` = no pawns; `semi_open_for(color)` = none of that colour's pawns and ≥ 1 enemy pawn (legacy) |
| `outside_enemy_pawn_cones` | per colour C: squares in **no** current enemy pawn's attack span. A span is the diagonally-forward squares on adjacent files, from the pawn's next rank to the last rank, ignoring blockers. It describes the current pawn set, not the future (design N2) |

A promoted pawn is no longer a pawn and leaves every pawn fact.

## 6. `king` (POSITION, DEFINED; `king_zone_v1`)

Per king:

| Fact | Definition |
| --- | --- |
| `square` | the king's square |
| `zone` | the king's square plus its neighbour squares (`attacks_mask(king)`), each with the enemy pieces geometrically attacking it as (square, type) |
| `shield` | own pawns on the king's file and the adjacent files, on the first and second rank in front of the king (forward relative to colour). Empty when the king is on its last rank seen from its side |
| `files_near` | for the king's file ± 1 (on board): `open`, semi-open for own colour, semi-open for enemy colour, or neither (from `pawns.files`) |
| `flight_squares` | side to move: legal king destinations **excluding castling**, labelled `LEGAL`. Other side: neighbour squares not occupied by its own pieces and not attacked by enemy pieces, labelled `GEOMETRIC` |

The geometric variant needs no king removal: the side not to move is never in check in a legal
position, so no enemy ray passes through its king (legacy inventory).

## 7. Deltas

### 7.1 `delta` (EDGE, keyed by `PieceId`; `delta_v1`)

`delta` holds the set differences between the parent's and child's POSITION records for
side-independent facts. Pieces are mapped through the edge's identity step (design §4), so a
moved piece is the same piece (legacy ACT "a blocker sliding along the same ray is not a
different piece").

Each component lists `began` and `ended` entries:

| Component | Key | Source |
| --- | --- | --- |
| `square_control` | (attacker id, square) | `pieces.attacks` |
| `piece_attacks` | (attacker id, victim id). **New:** catches a target walking into an attack (legacy defect D1) | `pieces.attackers` |
| `piece_defences` | (defender id, defended id) | `pieces.defenders` |
| `pins` | (pinner id, pinned id, king id) | `pieces.absolutely_pinned` |
| `xrays` | (slider id, first id, second id) | `lines.xray` |
| `batteries` | (rear id, front id) | `lines` |
| `zone_attacks` | (king id, square, attacker id) | `king.zone` |
| `shield` | (king id, pawn id) | `king.shield` |
| `pawn_flags` | pawn id → (before flags, after flags) for `isolated`, `doubled`, `passed`, `own_pawn_ahead`, `backward`. Only pawns whose flags changed | `pawns` |
| `files` | file → (before, after) state | `pawns.files` |
| `islands` | colour → (before, after) | `pawns.islands` |

Rules:
- **Only changes are recorded.** Unmoved pieces are included whenever their facts changed
  (legacy I1D M3, D19, D20).
- **A captured piece** ends every relation it took part in. Its pawn flags appear with
  `after = Absent(CAPTURED)`.
- **A promoted pawn** appears with `after = Absent(PROMOTED)`.
- `Absent(reason)` is a new typed sentinel. It is never `False` and never `0` (legacy I2I3 L2).
- **Not in `delta`:**
  - side-dependent facts (legal moves, captures, flight squares, `legally_capturable_now`) go
    to `same_side_delta`;
  - check changes are in `move` (`gives_check`) and `status`;
  - material changes are in `move` events.
- **Class per component** (A0 R3-N2): `RULE` for the geometric components; `DEFINED` for
  `pawn_flags`, `files`, `islands`, `zone_attacks` and `shield`.

### 7.2 `same_side_delta` (SPAN, grandparent → node; `same_side_delta_v1`)

This compares a node with its grandparent (same side to move), mapped by `PieceId` across both
edges.

| Component | Content |
| --- | --- |
| `legal_moves` | per piece id present in both: destinations gained and lost |
| `legal_captures` | (capturer id, victim id) gained and lost |
| `capturable_now` | pieces of the other side that became or stopped being `legally_capturable_now` |
| `flight_squares` | the moving side's king: legal flight squares gained and lost |
| `legal_move_count` | (grandparent, node) |

- It is defined only when the node's ply ≥ 2 within the tree. Otherwise it is
  `NOT_APPLICABLE("no same-side ancestor")`.
- The legacy rule "never subtract legal-move counts across a side flip" holds by construction.

## 8. Legacy defects and the definition that removes each

| Defect (reproduced) | FEN / move | Fix |
| --- | --- | --- |
| D1 a target walking into an attack never "begins" | `7k/8/8/8/2n5/8/8/K2R4 b`, `c4d2` | `delta.piece_attacks` keyed by (attacker id, victim id) |
| E1 a pinned defender counts silently | `4r2k/8/8/8/1b2P3/8/3N4/4K3 b` | defenders carry `absolutely_pinned` |
| E2 the king defends a square the enemy attacks | `4r2k/8/6b1/8/4P3/3K4/8/8 b` | defenders carry their type; geometry kept, flagged |
| E3 a king attacker that cannot capture | `8/8/8/3k4/4P3/5P2/8/K7 b` | attackers carry their type; `legally_capturable_now` separate |
| E4 a battery backer is not counted | `3r3k/8/8/3P4/8/8/3R4/3RK3 w` | correct geometry, exposed as `lines.xray` / `batteries` |
| E5 en passant victim: no attacker, yet capturable | `7k/8/8/3pP3/8/8/8/K7 w - d6` | stated rule §1.3; the two facts are separate by definition |
| E6 en passant masks `hanging` | `7k/8/8/3pP3/8/8/8/K2R4 w - d6` | `attacked_without_defender` is purely geometric |
| E7 `false` instead of unknown for the side to move | `7k/8/8/3n4/8/8/8/K2R4 b` | `NOT_OBSERVED` |
| S1 both doubled pawns passed | `7k/8/8/4P3/4P3/8/8/K7 w` | `own_pawn_ahead` beside `passed` |
| EP-pin not represented | `7k/8/8/KPp4r/8/8/8/8 w - c6` | stated: visible only in legal moves |
| P1 attacked ∧ ¬defended ≠ capturable | `7k/8/8/4r2b/8/5N2/8/3K4 w` | both facts kept, named distinctly |

## 9. `ensure`, tiers and dependency resolution (closes F1R-N1)

**Registry vs eager set.**
- Every registered family is part of the session.
- `OpenRequest.families` now names the **eager set** (default: all; mandatory: `status`,
  `draw`, `move`).
- A family outside the eager set reads `NOT_COMPUTED("not requested")` until `ensure` computes
  it.

**`FactEngine.ensure(tree, EnsureRequest(nodes, families)) -> rev`**
- It computes the missing records of `families` for `nodes`, appended at one new revision.
- It follows the same validation-before-work rule as `extend`: unknown nodes or families
  refuse the request, and nothing is committed.
- An already present record is never recomputed.

**Dependencies** are declared in `requires` and resolved per scope:

| Family scope | May require | Resolved on |
| --- | --- | --- |
| POSITION | POSITION | the same position |
| NODE | POSITION, NODE | the same node |
| EDGE | POSITION, NODE (both ends), EDGE | parent and child |
| SPAN | POSITION, NODE (both ends) | grandparent and node |

- `_select` refuses any other combination.
- `ensure` computes missing dependencies first, on every node involved (A0 C7).
- A family receives exactly its declared records, now for every scope (F1R-N1).

**Tiers.**
- In F2 every node is an input-role node, so the eager set applies to all nodes.
- F4 adds engine-only nodes, which get the A0 §7.5 eager tier (`status`, `material`, `draw`,
  `move`); the rest comes through `ensure`.

**Cost record.** Per-family milliseconds per position are measured and recorded in the F2
implementation record. Targets:
- ≤ 2 ms for the five POSITION families together;
- ≤ 1 ms for `delta` per edge.

Compute from bitboards once per `PositionKey`.

## 10. Test obligations (F2 implementation)

1. **Independent auditor extension.**
   - It recomputes every F2 field with its own ray walking (no `attacks_mask`), and pawn rules
     from the piece list.
   - Same fuzz corpus as F1: four root forms, branches, endgames.
2. **Invariants:**
   - the footprint parts are disjoint and cover the attack set;
   - the union of visible ray squares = the attack set;
   - an absolute pin's ray starts with `[pinned, king]`;
   - `delta` applied to the parent's relation sets gives the child's.
3. **Colour mirror:** mirrored positions give mirrored records, with directions mapped
   (df, −dr) (legacy ACT D8).
4. **Fixtures adopted from legacy tests and corpora:**
   - the `positional_v1` 9-row pawn table;
   - pinned supporter;
   - open / semi-open;
   - the mirror structure;
   - I1-D D08/D19 (discovered ray and pin), D09, D10, D20 (stationary pawn becomes passed),
     D04, D05, D07;
   - the activity tests: pinned attacker, in check, friendly or enemy first blocker, second
     blocker, relocated blocker, discovery, edge-empty vs unblocked, en passant ray, two
     blockers;
   - scenario E12 (pin began and ended), E15.
5. **Every defect row of §8** as a regression test.
6. **Mutation check:** the auditor must catch field-level mutations of every family (the F1
   review method).

## 11. Open questions for review

1. `king_zone_v1` uses the king square plus its neighbours. Some definitions add squares two
   ranks ahead. Is the narrow zone the right v1?
2. `backward_v1` uses the stop-square attacked-by-enemy-pawn condition. Should it instead (or
   also) require that no friendly pawn can ever support the stop square?
3. Are `lowest_attacker` as a type set (B = N) and `Absent(reason)` the right shapes?

**STOP** if F2:
- adds an evaluative name;
- drops a relation instead of flagging it;
- records a side-dependent fact for the side not to move;
- diffs side-dependent facts across a side flip;
- re-validates trusted records at runtime.
