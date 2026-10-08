# Fact engine — packet F1 implementation

Status: **implemented, awaiting independent F1 review**. Date: 2026-10-08.
Design: [`fact-engine-a0-design.md`](fact-engine-a0-design.md) rev. 4 (§13: F1).

## 1. Scope delivered

F1 delivers the engine-free core:
- `keys`, `request`, `tree` (revisions and roles), `identity` and `board`;
- the families `status`, `material`, `draw` and `move`;
- `FactEngine.open` and `FactEngine.extend`;
- a test-only auditor with a 400-game fuzz.

| Module (`src/calliope/facts/`) | Content |
| --- | --- |
| `keys.py` | `Color`, `PieceType`, `PieceId` (`w.N.g1`), `PositionKey` (python-chess EPD with legal en passant), `RootId`, `NodeId` (root node id = `RootId` value; child = digest(parent, canonical UCI)) |
| `values.py` | `FactClass`, sentinels (`NotObserved`, `HistoryUnknown`, `NotApplicable`, `NotComputed`), `AtLeast(n)`, `Defined[T]` |
| `request.py` | `RootSpec`, `InputLine`, `LineRole` (`PLAYED`, `EXPLORED`, `analysis(by)`), `OpenRequest`, `ExtendRequest`, `SessionBudget(max_nodes)` |
| `board.py` | the one canonicalizer `canonical_move` (UCI first, then SAN; all castling notations → king move; null, malformed promotion, illegal and ambiguous moves refused); root FEN parsing (invalid → `InvalidPositionError`, Chess960 rights → `UnsupportedVariantError`) |
| `identity.py` | root identities; advance by the exact move (castling rook, en passant victim, promotion keeps the id) |
| `tree.py` | `FactTree` (append-only store, single writer, atomic publish), `TreeView` (as-of-revision reads), `FrameNode`, `Edge`, `RoleEntry`, `LineRecord`, `FactEntry`, `RevisionDelta` |
| `families/` | `status_v1` (POSITION), `material_v1` (POSITION, `points_v1` as `Defined`), `draw_v1` (NODE), `move_v1` (EDGE) |
| `engine.py` | `FactEngine.open` / `extend`; header `terminal` from `status` + `draw` |

## 2. Implementation decisions within the design

Each item fills a detail that the design leaves open. None changes a design decision.

1. **Line labels continue across requests.** An input line is identified by (role kind, `by`,
   label).
   - A later `extend` with the same label continues it as a new segment
     (`played::game#1`, …), with role indexes continuing.
   - `start=None` continues from the label's end node; an explicit `start` must equal that end
     node.
   - This is how a game is played move by move.
   - Labels must be unique within one request.
2. **Roles.** The start node of a new line gets index 0. Every move gets a node role and an
   edge role with the same index. Identical role entries are not duplicated.
3. **Edges** are identified by their child node, since a tree node has exactly one incoming edge.
4. **Mandatory families.** `status`, `draw` and `move` are always computed, because the node
   header (`terminal`, `after_terminal`) and edges depend on them. `material` is selectable.
5. **Exact unknown-history bound** (design 6.9 and 3.2 updated):
   - `u = halfmove_clock − known_plies` unknown plies can hide at most `ceil(u / 4)` earlier
     occurrences.
   - A threshold is `false` only if it is unreachable even with that many. This makes
     `UNPROVEN` / `NONE` an exact proof rather than the earlier "n ≥ 2" sketch.
6. **`threefold_claimable_by_move`** only generates moves when some earlier position could
   reach three. This is an optimization with identical results, re-checked by the full fuzz.
7. **Node FEN** uses the legal en passant square (`board.fen(en_passant="legal")`). The
   Stockfish form of the FEN (`EngineInput`) belongs to F4.
8. **Concurrency.** One writer per tree (`_write_lock`). Records are published under a short
   lock and the revision number is published last. A view pinned at rev r never sees rev r+1
   records.

## 3. Not in F1 (by design §13)

- `ensure` and family tiers (F2).
- `pieces`, `squares`, `lines`, `pawns`, `king`, `delta` and `same_side_delta` (F2).
- `patterns` (F3).
- Everything engine-related (F4): `EngineProfile`, `ExpansionSpec`, searches, bases, engine
  lines, the result store, `max_searches`, deadlines.
- Serialization, digest and tree loading (F5).

## 4. Evidence

| Check | Result |
| --- | --- |
| `tests/facts/test_fact_engine.py`, 37 tests | pass |
| `tests/facts/test_auditor_fuzz.py`, 400 seeded games plus a bare-FEN rerun of each tail | pass |
| `tests/test_package_boundaries.py` (facts ↔ legacy imports; `import calliope` loads no legacy module) | pass |
| legacy `tests/unit`, `tests/golden` | pass (3205 in total with the above) |
| `ruff check`, `ruff format --check` on `src/calliope/facts`, `tests/facts` | pass |

The unit tests cover:
- all 8 castling notations plus `O-O` / `O-O-O`;
- null, malformed promotion, empty and illegal texts;
- an illegal line refused with label, ply and move, with nothing committed;
- invalid and Chess960 roots;
- legal-en-passant `PositionKey`;
- `RootId` depending on history;
- transpositions sharing position facts;
- castling, en passant and capture-promotion identity;
- branch-global ids;
- revisions and pinned views;
- label continuation;
- role accumulation;
- budget refusal before building;
- typed `NotComputed` / `NotApplicable`;
- threefold reached vs claimable;
- fivefold terminal and `after_terminal`;
- incomplete history (`AtLeast`, `UNPROVEN`);
- FEN + moves completeness;
- seventy-five-move and insufficient-material draws;
- mate-in-1 and checkmate line ends.

**Fuzz** (seed 20261008; 66,044 audited nodes):
- Content: 1,684 plies at threefold, 164 at fivefold, 245 promotions, 149 castlings, 316 en
  passant captures.
- The auditor compares against python-chess on a board that carries the full move stack:
  - legal moves and SAN, check, checkmate, stalemate, insufficient material, captures and
    mate-in-1;
  - material and `points_v1`;
  - occurrences, threefold and fivefold, python-chess's claim, fifty and seventy-five;
  - terminal kind;
  - move facts and event order.
- Piece identity is checked against an independently written tracker.
- On complete history, draw facts must be exact.
- On the bare-FEN tails, they must be sound: `true` and `false` are never contradicted by the
  full history.

**Cost** (engine only, no auditor; aarch64, 2 CPUs; 100 fuzz games, 11,305 nodes):
- 0.79 ms per node with all four F1 families, against an F0 target of about 1 ms for the eager
  tier.
- The full fuzz with the auditor takes about 2.3 minutes.
