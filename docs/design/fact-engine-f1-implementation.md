# Fact engine — packet F1 implementation

Status: **rev. 2 — independent F1 re-review READY** (`5aa3f02`).
Date: 2026-10-08. Design: [`fact-engine-a0-design.md`](fact-engine-a0-design.md) rev. 4
(§13: F1). Section 5 maps the review findings.

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
| `board.py` | the one canonicalizer `canonical_move` (UCI first, then SAN; all castling notations → king move; null moves on either path, malformed promotion, illegal and ambiguous moves refused); root FEN parsing (invalid → `InvalidPositionError`, Chess960 rights → `UnsupportedVariantError`) |
| `identity.py` | root identities; advance by the exact move (castling rook, en passant victim, promotion keeps the id) |
| `tree.py` | `FactTree` (append-only store with a no-overwrite guard, single writer, atomic publish), `TreeView` (as-of-revision reads, `input_line`, `coverage`), `FrameNode`, `Edge`, `RoleEntry`, `LineId`, `LineRecord`, `FactEntry`, `RevisionDelta` |
| `families/` | `status_v1` (POSITION), `material_v1` (POSITION, `points_v1` as `Defined`), `draw_v1` (NODE), `move_v1` (EDGE) |
| `engine.py` | `FactEngine.open` / `extend`; header `terminal` from `status` + `draw`; `after_terminal` from known history |

## 2. Implementation decisions within the design

Each item fills a detail the design leaves open; none changes a design decision.

1. **Line labels continue across requests.**
   - An input line is identified by `LineId(kind, by, label, segment)`, a structured key that is
     never a joined string.
   - A later `extend` with the same (kind, `by`, label) continues it as the next segment, with
     role indexes continuing.
   - `start=None` continues from the label's end node; an explicit `start` must equal that end
     node.
   - This is how a game is played move by move.
   - Labels must be unique within one request.
   - `TreeView.input_line(label, kind, by)` returns the latest segment visible at the view's
     revision.
2. **Roles.** The start node of a new line gets index 0. Every move gets a node role and an
   edge role with the same index. Identical role entries are not duplicated.
3. **Edges** are identified by their child node, since a tree node has exactly one incoming edge.
4. **Mandatory families.** `status`, `draw` and `move` are always computed, because the node
   header (`terminal`, `after_terminal`) and edges depend on them. `material` is selectable.
   A family receives only the records it lists in `requires`.
5. **Exact unknown-history bound** (design 6.9 and 3.2 updated):
   - `u = halfmove_clock − known_plies` unknown plies can hide at most `ceil(u / 4)` earlier
     occurrences.
   - A threshold is `false` only if it is unreachable even with that many. This makes
     `UNPROVEN` / `NONE` an exact proof.
6. **`after_terminal` = proven ended before** (design 3.2 updated). It is true iff:
   - an earlier known position (pre-root or path) ended the game by rule
     (insufficient material, clock ≥ 150, or fivefold on the known stack); or
   - a clock above 150 proves that an earlier position did.

   `false` claims nothing about unknown history.
7. **`seventy_five_move_reached`** follows design §6.9: clock ≥ 150 and not checkmate. It
   therefore differs from python-chess `is_seventyfive_moves()` (which requires a legal move)
   exactly at a stalemate with clock ≥ 150. The terminal is `STALEMATE` either way.
8. **`threefold_claimable_by_move`** only generates moves when some earlier position could
   reach three. This is an optimization with identical results, checked by the fuzz.
9. **Session state for later packets.** The session keeps:
   - the start board exactly as parsed, including a pseudo-legal en passant square that the
     node FEN normalizes away;
   - the canonical pre-root moves.

   F4 needs both to build the Stockfish-form `EngineInput`. Node FENs and `RootId` use the
   legal en passant square.
10. **Manifest.**
    - The open revision names rule implementations (`definitions`:
      insufficient material = python-chess `Board.is_insufficient_material`, `points_v1`).
    - `TreeView.coverage(family)` lists every target with the revision that added it.
    - Per-revision deltas carry counts.
11. **Concurrency and append-only.**
    - One writer per tree.
    - A commit refuses to replace any committed node, edge, line or fact record.
    - Records are published under a short lock, with the revision number last. A view pinned at
      rev r never sees rev r+1 records.

## 3. Not in F1 (by design §13)

- `ensure` and family tiers (F2).
- `pieces`, `squares`, `lines`, `pawns`, `king`, `delta` and `same_side_delta` (F2).
- `patterns` (F3).
- Everything engine-related (F4): `EngineProfile`, `ExpansionSpec`, searches, bases, engine
  lines, the result store, `max_searches`, deadlines, `EngineInput` construction.
- Serialization, digest and tree loading (F5).
- A per-node coverage *view* in the manifest beyond `TreeView.coverage` (F5 serializes it).

## 4. Evidence

| Check | Result |
| --- | --- |
| `tests/facts/test_fact_engine.py`, 47 tests | pass |
| `tests/facts/test_auditor_fuzz.py`, 400 games + 50 endgames, every root form, one branch per game | pass |
| `tests/test_package_boundaries.py` | pass |
| legacy `tests/unit`, `tests/golden` | pass (3215 tests in total with the above) |
| review mutations (§5, F1-C3) re-applied by monkeypatching against the 40-game fuzz | all 11 caught |
| `ruff check`, `ruff format` on `src/calliope/facts`, `tests/facts` | pass |

### Auditor (`tests/facts/facts_auditor.py`)

**Two boards per node, both python-chess.**
- `full` is the true game from a clock-0 start, carrying the whole move stack.
- `known` is the root's start FEN plus the moves the engine was given.

**Where the node is `history_complete`**, these must equal `full` exactly:
- occurrences;
- threefold and fivefold;
- claimable-by-move (oracle: some legal move makes `is_repetition(3)` true);
- terminal kind.

**Elsewhere they must be sound against `full`**, and complete against `known`: whatever the
known stack proves must be reported as proven.

**Fields compared every time:**
- `status`: legal moves and SAN, count, check and checkers, checkmate, stalemate, insufficient
  material, checking moves, promotions, mate-in-1, and every `LegalCapture` field (victim square
  computed by a different formula);
- material counts by type and bishop square colour, and `points_v1`;
- clocks and fifty;
- seventy-five against python-chess, with the stalemate divergence of §2.7;
- `after_terminal` against `is_game_over` replayed on `known` (exact) and on `full` (soundness);
- `known_plies` and `history_complete`;
- move facts: uci, SAN, mover, piece and type, squares, check, mate, castling side, and the
  ordered capture, promotion and rook events;
- piece identity against an independent tracker.

### Fuzz

Seed 20261008, 43,530 audited nodes.

**Root forms:**

| Form | Nodes |
| --- | --- |
| startpos | 16,270 |
| startpos + pre-root moves | 11,902 |
| FEN + moves | 6,399 |
| bare FEN | 8,462 |

**Content:**
- one explored branch per game;
- 50 pawnless endgames of up to 320 plies that continue past automatic draws;
- 1,734 plies at threefold and 157 at fivefold;
- 254 promotions, 182 castlings and 338 en passant captures;
- 2,868 incomplete-history nodes;
- 641 `UNPROVEN` nodes and 5,001 `AUTOMATIC_DRAW` nodes;
- 5,510 `after_terminal` nodes;
- 4,798 nodes with clock ≥ 150.

The test asserts that each of these categories occurs. It takes about 2.5 minutes.

### Cost

Engine only, without the auditor; aarch64 with 2 CPUs; 100 fuzz games, 11,305 nodes:
- 0.79 ms per node with all four F1 families;
- the F0 target is about 1 ms for the eager tier.

## 5. Review dispositions (independent F1 review of `d8acc2e`: NOT_READY)

| Finding | Disposition |
| --- | --- |
| F1-B1 null move accepted through SAN (`--`, `Z0`, `@@@@`) | refused after either parse path; parametrized tests and an `open` / `extend` regression |
| F1-B2 root `after_terminal` always false | computed from the known pre-root stack and from a clock above 150 (`_ended_by_rule`); regression tests; audited on every node |
| F1-C1 line-id collisions overwrote committed records | structured `LineId`; head index per (kind, by, label); commit refuses overwrites; regression test |
| F1-C2 `after_terminal=false` as an unproven negative | defined as "proven ended before" in design 3.2 and §2.6; `UNPROVEN` ancestors do not set it; regression test |
| F1-C3 auditor blind spots; record overclaimed | auditor rewritten (§4): exact claimable oracle, every status / capture / move field, known-stack completeness, every root form, branches, long endgames; all 11 review mutations caught; wording corrected |
| F1-N1 75-move at stalemate | stated in §2.7 and in the auditor |
| F1-N2 F4 lacks the start board and pre-root moves | kept in the session (§2.9) |
| F1-N3 families saw undeclared records | only `requires` records are passed (§2.4) |
| F1-N4 manifest coverage / definition naming | `definitions` in the open delta, `TreeView.coverage`; per-node serialization deferred to F5 (§3) |
| F1-N5 dynamic session attribute; quadratic label lookup | session is a constructor argument; head index makes the lookup O(1). A legal en passant square with a non-zero clock is accepted as given (sound, less informative) |

Re-review of `5aa3f02`: **READY**, with notes. The notes are carried forward as follows:

| Note | Disposition |
| --- | --- |
| F1R-N1 `requires` not threaded into POSITION and EDGE families | F2: required records go to `_position_record`, EDGE records join the per-node map, and `_select` forbids a POSITION family from requiring a NODE or EDGE family |
| F1R-N2 python-chess version inside the insufficient-material definition | F5 decides whether it belongs to the digest or to `facts_build_version` |
| F1R-N3 line order; mutable `start_board` | lines now sort in canonical role order (test added); F4 copies `start_board` before use |
| F1R-N4 thin boundary coverage of the 150 rule | unit test with clock 148 plus two pre-root moves added |
