# Fact engine — packet F3 implementation

Status: **rev. 1 — awaiting independent F3 review**.
Date: 2026-10-09. Design: [`fact-engine-f3-design.md`](fact-engine-f3-design.md) rev. 2
(F3-D), on [`fact-engine-a0-design.md`](fact-engine-a0-design.md) rev. 4 with the F2-D and F3-D
amendments. Base: branch `design/fact-engine-f3` @ `bc5f5a7` (PR #44, stacked on F2 PR #43).

## 1. Scope delivered

| Module (`src/calliope/facts/families/`) | Content |
| --- | --- |
| `patterns.py` | `patterns_v1` (POSITION, DEFINED; requires `pieces`, `squares`, `lines`): `PatternsFacts`, `MultiTargetAttack`, `Target`, `Order`, `LinePattern`, `SoleDefender`, `BackRank` |
| `pattern_delta.py` | `pattern_delta_v1` (EDGE, DEFINED; requires `patterns`, `pieces`, `delta`): `PatternDeltaFacts`, `LineTriple`, `TargetSetChange`, `BackRankChange`, `BackRankIds`, `DefenceEnded`, `DefenceEndReason` |
| `__init__.py` | both registered after `same_side_delta`; registry order stays dependency order |

No engine change was needed. The F2 resolver already gives an EDGE family the parent's
records, this edge's EDGE records and the identity step. `pattern_delta` is the first EDGE
family that requires another EDGE family.

## 2. Implementation decisions and design errata

1. **Participants** are F2 `Relation` records built from the `pieces` entry:
   `Relation(square, piece_type, absolutely_pinned is not None)`.
2. **Ray partition.** One pass over `lines.rays` (already in source, direction order) yields
   relative pins, skewers and discovery lines, so their canonical order is the ray order.
   `[enemy, enemy king]` rays are skipped; they are F2's absolute pins.
3. **`pattern_delta` id projections** follow F3-D §4. For `multi_target_attacks` and
   `sole_defenders`, a key present at either end is compared; a key whose piece no longer
   exists ends with `Absent(CAPTURED)`; `()` means the pattern does not hold. Back-rank keys
   are the parent's kings (kings are never captured).
4. **`DEFENCE_ENDED_UNDER_ATTACK`** filters `delta.piece_defences.ended` (already sorted by
   (defender, defended)) with the child's `pieces`. The reason comes from the edge's identity
   step: `captured`, `mover`, and the castling rook.
5. **Errata in F3-D rev. 2**, found by the complete-record fixture tests and corrected in the
   design text:
   - A18 also holds `MULTI_TARGET_ATTACK(c3 bishop → b2, d2)`.
   - A20 also holds `DISCOVERY_LINE(g8, g2 knight, g1 king)` for Black.
   - In the §4 id-projection example, nothing is recorded *for the b5 rook*. The promoted
     queen's own attack (b5, h1) does begin a `multi_target_attacks` entry.

   None changes a definition; the three statements were incomplete.

## 3. Not in F3

- Engine-only nodes and their tier (F4); serialization (F5).
- Any judgement of whether a pattern works: reasoning and explanation blocks (roadmap §5.2).

## 4. Evidence

| Check | Result |
| --- | --- |
| `tests/facts/test_patterns.py`, 52 tests | pass |
| `tests/facts/test_auditor_mutations.py`: unmutated corpus + 43 mutations (33 F2, 10 F3) | pass (every mutation caught) |
| `tests/facts/test_geometry_families.py`, `test_fact_engine.py` | pass (their "unknown family" example changed from `patterns`, now registered, to `no_such_family`) |
| `tests/facts/test_auditor_fuzz.py`, auditor extended to F3, 400 games + 50 endgames | pass (43,530 nodes audited for every F1, F2 and F3 family) |
| legacy `tests/unit`, `tests/golden` | pass (3,163 tests) |
| `pytest tests/facts tests/test_package_boundaries.py` | 219 tests, about 10 min (the fuzz audits every family on every node) |
| `ruff check`, `ruff format` | pass |

### Auditor (`tests/facts/geometry_auditor.py`, F3 part)

- `expected_patterns` recomputes every predicate from the auditor's own ray walking, attack
  sets and pin rule, not from `pieces` / `lines` records.
- `expected_pattern_delta` recomputes every component from the auditor's own pattern sets of
  parent and child, keyed by its independent identity tracker. `DEFENCE_ENDED_UNDER_ATTACK`
  reasons come from python-chess move metadata (en passant, castling, captures).
- It runs on every fuzz node; booleans are compared type-strictly.

### F3-D §7 obligations

| Obligation | Test |
| --- | --- |
| §7.2 side independence | `test_side_independence` |
| §7.2 back-rank free square ⇔ legal king step; ray partition; [enemy, enemy king] = F2 pins; multi-target targets = `attacks.enemy`; sole defender vs `pieces` | `test_pattern_invariants_on_random_games` |
| §7.2 `LINE_BLOCKED` landing square between defender and defended | `test_line_blocked_lands_between_the_defender_and_the_defended` |
| §7.2 `pattern_delta` applied to the parent gives the child | `test_pattern_delta_applied_to_the_parent_gives_the_child` |
| §7.3 eager = minimal + `ensure`; transpositions with different clocks | `test_patterns_equal_across_transpositions_and_ensure`; the F2 test `test_eager_tree_equals_minimal_tree_plus_ensure` now covers both F3 families through the registry |
| §7.4 colour mirror of `patterns` and `pattern_delta` | `test_colour_mirror_of_patterns_and_pattern_delta` |
| §7.5 A1–A21 as complete records; D1–D10; the additional cases; every `pattern_delta` component; root `NotApplicable` | `test_fixture_is_the_complete_record`, `test_defence_ended_under_attack` and the named tests |
| §7.6 mutation check | `test_auditor_mutations.py` |

### Cost

Measured with per-family timers inside the engine, aarch64 with 2 CPUs. The sample is 40
random games, 3,209 positions and 3,171 edges.

| Family | Per computation | F3-D §5 target |
| --- | --- | --- |
| `patterns` | 0.065 ms per position | ≤ 0.3 ms |
| `pattern_delta` | 0.086 ms per edge | ≤ 0.3 ms |

With every family eager, the end-to-end cost is 3.97 ms per node without timers, against
3.77 ms in the F2 record (same sample).
