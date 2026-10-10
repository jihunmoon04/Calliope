# Reasoning — packet R1 implementation: foundation, round 0, `quality_v1`

Status: **rev. 2 — independent R1 review READY_WITH_CORRECTIONS applied (§4)**.
Date: 2026-10-10. Design: [`reasoning-r0-design.md`](reasoning-r0-design.md) rev. 9 (R0-D) and
[`reasoning-r2-design.md`](reasoning-r2-design.md) rev. 10 (R2-D §2, `standard_lines`).
Base: `main @ 0028823` (R0-D and R2-D merged, #55, #56).

## 1. Scope delivered (R0-D §19, packet R1)

| Module | Content |
| --- | --- |
| `facts/flow.py` (new) | `material_flow`, `MaterialFlow`, `PlyMaterial` (one per ply: a capture-promotion stays one ply), `MaterialFlow.balance(color, ply)`, stability `Stable` / `Unstable(DRAWN_END, CAPTURE_AT_END, TOO_SHORT)` / `NotComputed` (R0-D §6.5) |
| `facts/planning.py` (new) | `planned_search_bound(view, request)`: the upper bound on searches an `extend` binds — surveys, policy comparisons (incl. retries of skipped ones) and `ANALYSIS` searches, by the planning rules of `EngineWork` (R0-D §6.4–§6.5) |
| `facts/engine.py` | `plan_lines` — the line planning of `extend`, now a module function shared with the bound (one rule) |
| `facts/tree.py` | `TreeView.request(rev)`: the normalized request of a revision, kept per revision at commit (also after `load`) |
| `facts/__init__.py` | the public names reasoning uses (R0-D §6.5): requests, expansions, profile, ids, line and search records, the family records reasoning reads with their enums, value types, `order`, `material_flow`, `planned_search_bound` |
| `reasoning/refs.py` | the common currency (R0-D §4): `MoveSubject`, `PieceRef`, `SquareRef`, `MoveRef`, `SearchMoveRef`, `MaterialAmount`, `LineSegment`, `FactRef`, `SearchRef`, `ScopeRef` |
| `reasoning/request.py` | `AnalysisRequest`, `ReasoningBudget`, structural checks, normalization from the tree's requests (R0-D §5) |
| `reasoning/errors.py` | `ReasoningError`, `InvalidAnalysisRequest`, `AnalysisFailed`, `GuardError`, `StoredGraphError` (R0-D §15) |
| `reasoning/observer.py` | `quality_v1` (`expected`, `grade`, `judge`), `Grade` ordered BEST < … < BLUNDER (comparisons and sorting by rank), `Judgement`, `LineScore`, `Observation`, `JudgementRef`, `ObservationRef`, the material `window` (R2-D §1.3) and the observation `standard_lines` over the windows (R2-D §2) |
| `reasoning/controller.py` | `Controller.round_zero`: the base tree (R0-D §6.1), the round-0 `ensure` of the standard lines, judgements of the target and previous moves on `V_0`, `RoundZero` |

Not in R1 (R0-D §19): needs and later rounds, hypotheses and verification, the claim graph and
labels (R2); planner and renderer (R3); storage and the acceptance corpus (R4). The observations
`line_material` and `played_edge` (R2-D §2) come with the templates that read them (R2).

## 2. Implementation decisions within the design

1. **Round 0 opens with a `NONE` root — an amendment of R0-D §6.1, applied to R0-D.** With
   `g = 0`, a `FULL` root attaches its engine lines at `open`, before the played moves are counted
   against `max_nodes`; a small tree bound then refused the played move itself
   (`BudgetExceededError`, found by `test_a_small_tree_bound_cuts_engine_lines_deterministically`).
   The window `extend` starts at the root and gives it `FULL` through its start role (F4-D §6.2),
   so the root is still surveyed, compared and attached, after its input nodes are counted.
2. **`TreeView.request` reads a per-revision map** (`FactTree._requests`) filled where F5 logs
   the request, so it is exact for every committed revision and after `load`. It is metadata of
   the log, outside records and digests; the build-version guard digest is unchanged.
3. **`planned_search_bound` assumes the worst where the view cannot know**: new nodes are
   searchable (their terminal state is unknown before they exist) and their surveys regular. It
   requires the view to be the tree's current revision (a request is issued now).
4. **Basis reasons pass through.** An `INCONCLUSIVE` judgement carries the fact engine's reason
   (`PARENT_NOT_SEARCHED`, `BUDGET`, `DEADLINE`, `IRREGULAR_SEARCH`, `COMPARISON_NOT_REQUESTED`),
   `NOT_APPLICABLE` for a terminal parent, `NOT_IN_BASIS`, or `WDL_UNAVAILABLE`. A line without
   WDL exists only for an engine that does not offer `UCI_ShowWDL`; the fact engine refuses such
   output otherwise.
5. **A standard line not attached at P** (no record) is the operand `MissingLine(search_id, rank,
   reason)` of `standard_lines`; a line cut before its first ply is a zero-ply `LineSegment`.
6. **Played-line nodes** are read from the PLAYED input line's segments (prefix and window), not
   recomputed from moves; reasoning never parses moves (R0-D §3.3).
7. **One expansion rule.** `request_expansion` (fact engine) resolves an `extend`'s expansion for
   both `FactEngine.extend` and `planned_search_bound`; `plan_lines` likewise plans its lines.
8. **`TreeView.request`** keeps a per-revision map next to the F5 log (`_log[rev − 1]` holds the
   same object); the map makes the lookup independent of how the log is indexed.
9. **`judge` follows R0-D §7.2's step order**: `NOT_IN_BASIS` (step 2) before `WDL_UNAVAILABLE`
   (step 3).
10. **Input checks** reject a profile that is not an `EngineProfile`, a budget that is not a
    `ReasoningBudget`, and `bool` budget values; `max_extra_searches = 0` is valid (R0-D §27).

## 3. Evidence

| Check | Result |
| --- | --- |
| `tests/reasoning/test_quality.py` — bands 39/40/41 … 399/400/401, rank-1 rule, flooring, both mate tables, missed-mate departure, mover perspective, the grade order (comparisons, sorting), Black in a survey, a played move graded in a comparison, mate scores on a tree; every `INCONCLUSIVE` reason: `PARENT_NOT_SEARCHED`, `COMPARISON_NOT_REQUESTED`, `BUDGET`, `DEADLINE`, `IRREGULAR_SEARCH`, `NOT_IN_BASIS`, `NOT_APPLICABLE` (after the 75-move rule), `WDL_UNAVAILABLE` | 31 passed |
| `tests/reasoning/test_round_zero.py` — requests for `t` = 1, 2, 5; the root searched and attached through its start role (`t` = 1, 2); G / P / C searched and judged; standard lines over their windows and the round-0 ensure; the window widening to stability and stopping at `2 · pv_plies`; `material_flow` on engine-only nodes; SAN normalized, moves after the target dropped; refusals before engine work; an illegal move; a small tree bound (deterministic cuts); cold vs warm store vs fresh (identical digests, judgements, observations); a deadline cut → not reproducible | 14 passed |
| `tests/reasoning/test_stockfish_round_zero.py` — real Stockfish 19, Opera game: 17.Qb8+ graded BEST with `Mate(WHITE, 2)` | pass |
| `tests/facts/test_flow.py` — captures, a queen capture (+9 balance, own points unchanged), capture-promotion as one ply, en passant, castling, every stability rule incl. a stalemate after quiet plies, per-ply points = `material` records, path validation, a missing record, `balance` outside the path refused | 15 passed |
| `tests/facts/search/test_planning.py` — bound ≥ actual for a PLAYED extension, `ANALYSIS` lines with and without comparison, a skipped comparison retried at the root, retries at two nodes and a round of two extends summed (R0-D §18.2); stale view; engine-less session; `TreeView.request` normalized and after `load` | 6 passed |
| `tests/test_package_boundaries.py` — `reasoning` added to the new packages; `facts` never imports `reasoning`; `reasoning` imports only `calliope.facts` and no python-chess (checked to fail on a planted `import chess` / `calliope.facts.tree`) | 6 passed |
| Reviewer's fuzz of `planned_search_bound` (synthetic engine; PLAYED / EXPLORED / ANALYSIS, every expansion, irregular positions, 3 ms deadlines, `max_nodes` cuts): 2,779 requests and 522 summed pairs | 0 cases above the bound |
| full `tests/facts` (400-game fuzz, real-Stockfish acceptance), `tests/reasoning`, boundaries — rev. 1 / rev. 2 | 399 passed in 11 min 20 s / 408 passed in 11 min 12 s |
| legacy `tests/unit`, `tests/golden` | 3,163 passed |
| `ruff check`, `ruff format` | pass |

### Cost (R0-D §17; aarch64, 2 CPUs, Stockfish 19, depth 12, MultiPV 5)

| Target (Opera game) | Round 0 | Tree nodes | Grade |
| --- | --- | --- | --- |
| 7.Qb3 (ply 13) | 2.28 s | 191 | BEST |
| 9…b5 (ply 18) | 2.17 s | 264 | EXCELLENT (loss 1; rank 6, WDL saturated) |
| 10.Nxb5 (ply 19) | 2.13 s | 234 | BEST |
| 13.Rxd7 (ply 25) | 1.09 s | 180 | BEST |
| 17.Qb8+ (ply 33) | 0.34 s | 96 | BEST, mate in 2 |

Round 0 stays within the ≤ 3 s target. 9…b5 shows WDL saturation in a lost position: the
grade is EXCELLENT although the move is rank 6, as R0-D §7.2 documents.

## 4. Independent R1 review (rev. 1 `69d3f8d`): READY_WITH_CORRECTIONS

The review found no undercount of `planned_search_bound` by reading against `EngineWork.run` and
by fuzzing, and confirmed the §6.1 amendment for `t` = 1, 2, 3.

| Finding | Resolution |
| --- | --- |
| C1 `standard_lines` covered the whole attached line, not its window | `observer.window` (R2-D §1.3); `standard_lines(view, judgement, pv_plies)`; tests for widening and the cap |
| C2 `Grade` compared and sorted alphabetically (a `StrEnum`) | comparisons by rank; tests for `>`, `>=` and `sorted` |
| C3 missing test obligations (summed bound, retries at G / P, every `INCONCLUSIVE` reason, G / P / C at `t` = 1, 2) | §3 tests added |
| N1 `judge` check order | §2.9 |
| N2 `balance` accepted negative plies | range check, test |
| N3 profile / budget types; `max_extra_searches = 0` | §2.10; R0-D §27 |
| N4 duplicated expansion rule; `_requests` beside `_log` | `request_expansion` shared (§2.7); the map kept (§2.8) |
| N5 R0-D amendment without a disposition; `MissingLine` outside §4; lock note | R0-D rev. 9 §27 and §4; docstring of `planned_search_bound` |

