# Fact engine — packet F2 implementation

Status: **rev. 2 — independent F2 review READY_WITH_CORRECTIONS applied**.
Date: 2026-10-09. Design: [`fact-engine-f2-design.md`](fact-engine-f2-design.md) rev. 2 (F2-D),
on [`fact-engine-a0-design.md`](fact-engine-a0-design.md) rev. 4 with the F2-D amendments. Base:
`main @ 375f9fa`. Review of rev. 1 (`11f478a`): READY_WITH_CORRECTIONS (F2-C1–C3, N1–N8);
section 5 maps every finding.

## 1. Scope delivered

F2 delivers:
- the POSITION families `pieces`, `squares`, `lines`, `pawns` and `king`;
- the EDGE family `delta` and the SPAN family `same_side_delta`;
- `FactEngine.ensure`, the eager set closed under `requires`, and dependency resolution across
  scopes (closes F1R-N1);
- the `Absent(reason)` sentinel (A0 §1 as amended by F2-D §11);
- an independent geometry auditor, invariants, equivalences, the colour mirror, legacy and new
  fixtures, and a mutation check (F2-D §10).

| Module (`src/calliope/facts/`) | Content |
| --- | --- |
| `families/geometry.py` | shared primitives: ray table, `Relation`, `Pin`, the ray-rule `absolute_pins`, the `AttackTable` (every piece's `attacks_mask` and, per square, the pieces whose set holds it) |
| `families/pieces.py` | `pieces_v1`: `PieceFacts`, `Footprint`, `piece_order_v1` (`lowest_attacker_types`), legal projections of `status` |
| `families/squares.py` | `squares_v1`: `SquareFacts`, `Occupant` |
| `families/lines.py` | `lines_v1`: `Ray`, `RayOccupant`, `XRay`, `Battery` |
| `families/pawns.py` | `pawns_v1`: `PawnFacts`, `PawnChain`, `FileFacts`, `FileState`, `ByColor` |
| `families/king.py` | `king_zone_v1`: `KingFacts`, `ZoneSquare`, `FlightSquares`, `FlightKind` |
| `families/delta.py` | `delta_v1`: `DeltaFacts`, `SetChange`, `FlagChange`, relation keys, `COMPONENT_CLASS`, `relations_of` |
| `families/same_side_delta.py` | `same_side_delta_v1`: `SameSideDelta`, `SideMember`, `DestinationChange`, `CapturableChange`, `SetDiff` |
| `families/base.py` | `FamilyContext` gains `parent_records`, `grandparent_records`, `pieces_maps`, `identity_steps` |
| `engine.py` | `ensure`; registry check; eager closure; one recursive resolver for all scopes |
| `request.py`, `tree.py`, `values.py` | `EnsureRequest`; the session's eager set and `TreeView.eager()`; `Absent`, `CAPTURED`, `PROMOTED` |

## 2. Implementation decisions within the design

Each item fills a detail the design leaves open; none changes a design decision.

1. **One resolver for every scope** (`_Build.resolve`).
   - POSITION records are computed once per `PositionKey`, from `key_board(key)`: the board
     rebuilt from the key alone (clocks 0, fullmove 1, empty stack; F2-D §1.5). One such board
     is built per key per request and shared by the families, which never mutate it.
   - NODE, EDGE and SPAN records resolve their `requires` where the scope table puts them; a
     record already in the store or in the pending revision is never recomputed.
   - `status` and `draw` are computed before the node header exists, because the header's
     `terminal` needs them. The eager set is then resolved on the new node.
2. **Registry check at construction.** `FactEngine(families)` refuses a registry in which a
   family requires one registered after it, or requires a scope its own scope may not require
   (F2-D §9 table). This is where F2-D says `_select` refuses; doing it once per engine refuses
   earlier and covers `ensure` too.
3. **Eager set.** `OpenRequest.families` plus `status`, `draw`, `move`, closed under `requires`.
   Every registered family belongs to the session; a family outside the eager set reads
   `NotComputed("not requested")` until `ensure` computes it. The open revision's manifest
   entry names the eager set (`RevisionDelta.eager`).
4. **`ensure`.**
   - An empty node or family list, a family the tree's session does not have, or an unknown
     node refuses the request before any work; nothing is committed. Families are checked
     against the session, not against the calling engine's registry (F2-C3).
   - Duplicate nodes are computed once.
   - An EDGE family at the root has no target; `TreeView.fact` reads `NotApplicable` there, as
     in F1.
   - When nothing is missing, no revision is committed and the current revision is returned.
5. **SPAN context.** F2-D §9 lists `parent_records` for SPAN, but its scope table resolves
   SPAN only on the grandparent and the node; the implementation follows the table (F2-N1). The
   scope table resolves a SPAN family's `requires` on the node and the
   grandparent only, so `parent_records` is empty for SPAN. `pieces_maps` holds all three maps
   (grandparent, parent, node) and `identity_steps` both steps. A node with ply < 2 stores
   `NotApplicable("no same-side ancestor in the tree")` without resolving any requirement.
6. **Record shapes.**
   - Squares are names; relations are `Relation(square, piece_type, absolutely_pinned)`.
   - `PieceFacts.absolutely_pinned` is `Pin(pinner, direction) | None`; `None` means not pinned.
   - `legal_destinations` is in board order; `legal_moves` keeps `status` order (canonical UCI).
   - Per-colour values use `ByColor(white, black)`; `king` is a `ByColor[KingFacts]`.
   - Collections that hold only changes (`delta` flag and file changes, `same_side_delta`
     destination and capturability changes) list only entries whose value changed.
     `same_side_delta.pieces` lists every member, as F2-D §7.2 asks.
7. **`delta` class.** A `FactEntry` carries one class, so `delta` is stored as `DEFINED` (it holds
   DEFINED components) and `COMPONENT_CLASS` names the class of each component as F2-D §7.1
   tabulates it; F5 serialization must carry it (F2-N2). Internally relation sets are plain tuples of piece-id strings and square
   indexes, which sort in canonical order; only the differences become record objects.
8. **Castling and flight squares.** A king move of two files is castling and is never a legal
   flight square. Castling destinations stay in `pieces.legal_destinations` (g1/c1/g8/c8).
9. **Definitions in the manifest.** The open revision also names `piece_order_v1`
   (`K > Q > R > B = N > P`).
10. **Cost.** Families read one `AttackTable` per computation instead of calling
    `attackers_mask` per square; pawn rules are bitboard masks. See §4.

## 3. Not in F2 (by design)

- `patterns` and `pattern_delta` (F3).
- Engine-only nodes, their eager tier and the "engine-only node gains an input role" path (F4;
  F2D-N4). In F2 every node is an input-role node, so the eager set applies to all nodes.
- Serialization of records and coverage (F5).

## 4. Evidence

| Check | Result |
| --- | --- |
| `tests/facts/test_geometry_families.py`, 71 tests | pass |
| `tests/facts/test_auditor_mutations.py`: unmutated corpus + 33 field-level mutations of every F2 family | pass (every mutation caught) |
| `tests/facts/test_fact_engine.py`, 47 tests | pass |
| `tests/facts/test_auditor_fuzz.py` with the F2 auditor, 400 games + 50 endgames | pass (43,530 nodes audited for every F1 and F2 family) |
| `tests/test_package_boundaries.py` | pass |
| legacy `tests/unit`, `tests/golden` | pass (3,163 tests) |
| `ruff check`, `ruff format` on `src/calliope/facts`, `tests/facts` | pass |

### Auditor (`tests/facts/geometry_auditor.py`)

- It never calls `attacks_mask`, `attackers_mask`, `pin_mask` or any `calliope.facts` helper. It
  walks rays square by square on a `{square: (colour, type)}` map and follows the F2-D §5
  wording for pawns with file / rank arithmetic. python-chess supplies only the placement and,
  as the legal oracle, `Board.legal_moves`.
- Comparisons are type-strict for booleans: `1` in place of `True` is a difference (F2-N3).
- On every audited fuzz node it compares, field by field: all five POSITION families; `delta`
  against its own relation sets of the parent and child, keyed by the auditor's independent
  identity tracker; `same_side_delta` against the grandparent, or the stored `NotApplicable`
  below ply 2.
- Equalities checked through it: legal projections equal the legal oracle; `squares` and
  `pieces` attackers / defenders; zone attackers against the square attackers.

### Other F2-D §10 obligations

| Obligation | Test |
| --- | --- |
| §10.2 footprint disjoint and covering, visible union = attack set, pin ray `[pinned, pinner]`, pins vs `Board.is_pinned`, `squares` vs `pieces`, battery once | `test_geometry_invariants_on_random_games` |
| §10.2 `delta` applied to the parent's sets gives the child's | `test_delta_applied_to_the_parent_sets_gives_the_child_sets` |
| §10.3 eager tree = minimal tree + `ensure` | `test_eager_tree_equals_minimal_tree_plus_ensure` |
| §10.3 transpositions with different clocks; POSITION families never see the node board | `test_position_records_are_equal_across_transpositions_with_different_clocks`, `test_position_families_never_see_the_node_board` |
| §10.3 `ensure`: atomic refusal, no recomputation, parent and grandparent dependencies, no revision when nothing is missing, pinned views | `test_ensure_*` |
| §10.4 colour mirror over every POSITION family: pieces, squares, rays (squares, occupants, visible, x-ray), batteries, pawns (flags, supporters, phalanx, chains, islands, files, cones), king (zone, shield, files near, flight squares). Directions map to (df, −dr); a battery line, normalized lower → higher, maps to (−df, dr) on diagonals and verticals because the mirror swaps which square is lower (F2-C2) | `test_colour_mirror_gives_mirrored_records`, `test_battery_lines_under_the_mirror` |
| §10.5 legacy fixtures: `positional_v1` table, pinned supporter, open / semi-open, mirror; activity (pinned attacker, in check, first and second blockers, relocated blocker, discovery, edge-empty vs unblocked, en passant ray, pin behind a blocker); I1D D04, D05 (`D05-K`, `D05-Q`), D07, D08, D09, D10, D19, D20; E12, E15 | named tests in `test_geometry_families.py` |
| §10.6 every §8 row; pin cases; batteries; `same_side_delta` with capture, promotion and en passant in either ply, and castling | named tests in `test_geometry_families.py` |
| §10.7 mutation check | `test_auditor_mutations.py` |

### Fuzz

The F1 fuzz (seed 20261008) is unchanged; every node it audits is now also audited for the
five POSITION families, `delta` (every non-root node) and `same_side_delta` (`NotApplicable`
below ply 2).

- 43,530 audited nodes over the four root forms, one explored branch per game, and 50 long
  pawnless endgames;
- 254 promotions, 182 castlings and 338 en passant captures in the games.

`pytest tests/facts tests/test_package_boundaries.py`: 157 tests in about 7 min (F1: about
2.5 min). The auditor's naive geometry accounts for the difference.

### Cost

Measured without the auditor, aarch64 with 2 CPUs, the 40-game random sample of 3,171 edges.
The machine was shared with a concurrent test run, so absolute numbers are high: on the same
machine and run, `main` measured 1.14 ms per node for the four F1 families, against 0.79 ms in
the F1 record.

| Item | Per computation | F2-D §1.9 target |
| --- | --- | --- |
| `pieces` | 0.63 ms | |
| `squares` | 0.55 ms | |
| `lines` | 0.43 ms | |
| `pawns` | 0.13 ms | |
| `king` | 0.05 ms | |
| five POSITION families together | 1.79 ms per position | ≤ 2 ms |
| `delta` | 0.49 ms per edge | ≤ 1 ms |
| `same_side_delta` | 0.15 ms per node | — |

Per node, end to end:
- 1.32 ms for the four F1 families. On `main` the same tier measured 1.14 ms in the same
  run. The difference is the board rebuilt from the `PositionKey` (about 0.10 ms per new
  position, F2-D §1.5) and the resolver.
- 3.77 ms with every family eager.

## 5. Review dispositions (independent F2 review of `11f478a`: READY_WITH_CORRECTIONS)

| Finding | Disposition |
| --- | --- |
| F2-C1 activity fixtures "relocated blocker", "discovery", "en passant ray" missing; record overclaimed | adopted as `test_relocated_blocker_keeps_its_identity`, `test_nearest_blocker_moving_exposes_only_up_to_the_second_blocker`, `test_en_passant_capture_opens_the_file_ray_to_the_landing_square`; record list corrected |
| F2-C2 colour mirror only partly tested | the mirror test now covers every POSITION family field (§4 table); the battery-line mapping (−df, dr) is stated here and pinned by `test_battery_lines_under_the_mirror`; F2-D §10.4 gets the same note at its next revision |
| F2-C3 `ensure` accepted a family the session lacks | validated against the session's families; `test_ensure_refuses_a_family_the_session_does_not_have` |
| F2-N1 SPAN `parent_records` contradiction inside F2-D §9 | implementation follows the scope table (§2.5); F2-D to be aligned at its next revision |
| F2-N2 `delta` single class | stated in §2.7; F5 serializes `COMPONENT_CLASS` (roadmap) |
| F2-N3 auditor did not tell `1` from `True` | `same()` compares booleans type-strictly; mutation "pinned flag stored as an int" added and caught |
| F2-N4 mutations stop at family records | accepted: engine paths (key board, eager closure, `ensure`) have dedicated tests |
| F2-N5 `absolute_pins` and `AttackTable` built by both `pieces` and `squares` | accepted: within the cost target; sharing per position is an option for a later cost packet |
| F2-N6 unused `HEADER_FAMILIES` | removed |
| F2-N7 record counts | corrected (§4) |
| F2-N8 `same_side_delta` promotion only in the first ply | second-ply promotion fixture added |
