# Reasoning — packet Q1 implementation: the rating-aware grade `quality_v2` (runtime)

Status: **rev. 2 — independent Q1 review NOT_READY (B1, C1, C2) applied (§5); awaiting re-review**.
Date: 2026-10-10. Design: [`reasoning-quality-v2-design.md`](reasoning-quality-v2-design.md)
rev. 5 (Q-D §3–§6, test obligations §9.1–§9.7). Base: `main @ c2904c3` (Q-D merged, #62).

Q1 is the runtime half of Q-D: `GradingSpec` in the request, its resolution, `quality_v2` and the
integer standard curve, the grading passed to the observer and the catalogue, and the identity of
the choice. The shipped build holds no curve table and no conversion (Q-D §10). Explicit and
default scales work. Ratings work only together with an explicit scale; without one they are
refused (`CALIBRATION_UNAVAILABLE`). The table, the conversion and the calibration tool are Q2.

## 1. Scope delivered

| Module | Content |
| --- | --- |
| `reasoning/grading.py` (new) | `LOGISTIC` (4001 integers, computed at import in its own `decimal` context at 40 digits, checked against `LOGISTIC_DIGEST` at import) and `curve_points` (Q-D §4.2); `GradingSpec`, `check_spec` (§3 structural checks); `CurveSource`, `Curve` with the flags of §3 / §3.1; `Grading` (the resolved grading); `resolve` (§3 resolution); `convert` (§3.1); `CurveBand`, `CurveTable`, `ConversionTable`, `GradingBuild` (with `identity()` for `ReasoningBuild`, §6); `load_curve_table` and `load_conversion` (the checks of §7.2–§7.4 and §3.1, at load); `runtime_scale` (§7.4 step 3, integers only); `SHIPPED` (empty) |
| `reasoning/request.py` | `AnalysisRequest.grading: GradingSpec = GradingSpec()`; `check` runs `check_spec` |
| `reasoning/observer.py` | `judge(view, subject, grading)`, `scored(view, subject, search_id, grading)`; `score_points` (§4.1 step 4); `WDL_UNAVAILABLE` only under `quality_v1`; `Judgement.policy` from the grading, `Judgement.curve`; `LineScore.wdl: Wdl \| Unavailable` |
| `reasoning/controller.py` | `Controller(fact_engine, grading_build=SHIPPED)`; the grading is resolved right after `check`, before any fact request; `RoundZero.grading`; both judgements use it |
| `reasoning/hypotheses.py` | `ProposeContext.grading` (required); `HypothesisTemplate.verify(h, view, grading)` |
| `reasoning/runner.py` | `Reasoner(fact_engine, templates, grading_build=SHIPPED)`; passes the grading to proposals and verification |
| `reasoning/catalogue/` | every `verify` takes `grading`; `judgement(view, h, grading)`; `scope(view, h, grading, ranks, …, extra_policies=())` names `("points_v1", grading.policy, *extra)` (R2-D §13); the `POLICIES` constants are gone (`unsafe_v1` is an extra policy) |
| `reasoning/encoding.py` | the registry also holds `GradingSpec`, `CurveSource`, `Curve`, `Grading` |
| `reasoning/__init__.py` | the public names of `grading.py`, and `score_points` |

## 2. Implementation decisions within the design

1. **`Grading` is `ResolvedGrading`.** Q-D §3 names the resolved value `ResolvedGrading` and §5.1
   calls the value passed through the stages `Grading`; they have the same fields (`policy`,
   `curve`), so they are one type, `Grading`.
2. **The build is injected, not global.** `Controller` and `Reasoner` take a `GradingBuild`
   (default `SHIPPED`). Tests build tables with `load_curve_table` / `load_conversion` and inject
   them; the shipped registry stays empty, as Q-D §9.3 requires.
3. **The current table** of a build is its last Lichess-scale curve table, and the current
   conversion its last conversion (Q-D §7.2: requests name the pool, the build fixes the table).
4. **No `ReasoningBuild` yet.** It belongs to storage (R4, R0-D §14). `GradingBuild.identity()`
   returns what Q-D §6 adds to it: the two policies, the `(name, digest)` of the curve tables and
   conversions, and the `LOGISTIC` digest. A table's digest is the SHA-256 of its file bytes.
5. **Load-time checks are the band criteria.** `load_curve_table` refuses floats anywhere, a
   wrong pool or model, `cp_ratio_permille` within 10 % of 1000 but not 1000, a band below
   100 000 positions, a shard spread above `0.15 × source_scale`, `source_scale` at or beyond
   150 / 4000, a runtime `scale` not derived from `source_scale` and the stored ratio, a `low`
   off the band grid, an unknown time class, and duplicate bands (`ReasoningError`, Q-D §8).
   `load_conversion` refuses floats, missing provenance (`source`, `retrieved`, `method`), fewer
   than two anchors, and anchors that do not strictly increase.
   - A curve table must also carry its provenance (Q-D §7.2): `source` and `filters` as non-empty
     strings, `bytes_read`, `games_read` and `games_used` as integers ≥ 0, with
     `games_used ≤ games_read` (review C1).
   - Parse failures (invalid UTF-8 or TOML) and wrong shapes (`[table]`, `[[band]]` or a pool
     section that is not a table) raise `ReasoningError` too, never a `TOMLDecodeError` or an
     `AttributeError` (review C2).
6. **`ProposeContext.grading` is required.** It sits before `pending`, which keeps its default; a
   default grading would let a context built without one grade silently under a policy nobody
   chose.
7. **Existing tests pin `quality_v1`** (Q-D §9.7). Their engine tables are written in WDL
   (`story.WDL`, the helpers of `test_quality`, `test_round_zero`, `test_runner`,
   `test_runner_contract`, and the gated Stockfish test), and they keep their expectations. Test
   templates take the new `verify` argument.
8. **`language` keeps its default `"ko"`.** R3-D amends it to `"en"`; that change belongs to R3.
9. **The standard curve is checked at import** (review B1).
   - `_logistic` runs every operation in its own context, the final rounding included
     (`Context.to_integral_value`). The process's current `decimal` context (its rounding,
     its precision) cannot change a value.
   - The module then compares the SHA-256 of the canonical encoding with `LOGISTIC_DIGEST` and
     raises `ReasoningError` on a mismatch, so a wrong table never loads.
   - A tuple of integers encodes without record types, so the check uses `calliope.facts.canonical`
     directly. The bytes are those of `canonical_bytes`.

## 3. Evidence

**Tests** (`tests/reasoning/test_grading.py`, 72 tests; Q-D §9.1–§9.7):
- §9.1: the curve table and its digest. A first import under `ROUND_DOWN` at precision 3 (a
  subprocess) builds the same table and digest. A copy of the module with a wrong pinned digest
  fails to import with `ReasoningError` (review B1).
- §9.2: `curve_points` and `score_points`.
- §9.3: precedence; the override, accepted by the shipped build; average and single rating; band
  clamping with the lower-on-tie rule; `NO_BAND`; `CALIBRATION_UNAVAILABLE` for both pools.
- §9.3, conversion: exact end anchors; floor between anchors; clamping strictly outside;
  `classical` via `rapid`; conversion before averaging (815 / 1500 → 1542).
- §9.3, structural: thirteen structural refusals, each through `resolve` and through
  `Controller.round_zero`.
- Tables: nine defective curve tables, three defective conversions, five missing provenance
  fields and an inconsistent game count (review C1), four malformed curve tables and three
  malformed conversions (review C2); `runtime_scale(3000, 1234) = 3702`.
- §9.4: band boundaries 39 … 401 from constructed scores; a line without WDL decided under
  `quality_v2`; allowing mate from −5.00 is BLUNDER at `c = 1000` and EXCELLENT under
  `quality_v1`; the previous move uses the same curve.
- §9.5: `only_move_v1` SUPPORTED under WDL and REFUTED under the curve on the same lines (no GREAT
  then); the same for `sacrifice_sound_v1`; scopes name `quality_v2`.
- §9.6: the scale is part of the normalized request and of the judgement's bytes; reruns are
  byte-identical.

| Suite | Result |
| --- | --- |
| `tests/reasoning` and `tests/test_package_boundaries.py` | 243 passed, 1 skipped (the gated Stockfish test without an engine) |
| the gated Stockfish round-0 test with Stockfish 19 | passed |

**The Opera game with Stockfish 19** (round 0 only, depth 12, MultiPV 5; 33 targets under three
gradings, 160 s in total). 10 of the 33 plies change grade:

| Ply | Move | `quality_v1` | `quality_v2`, `c = 1000` | `c = 600` |
| --- | --- | --- | --- | --- |
| 4 | 2…d6 | GOOD (68) | EXCELLENT (22) | EXCELLENT (36) |
| 6 | 3…Bg4 | MISTAKE (359) | GOOD (55) | GOOD (90) |
| 8 | 4…Bxf3 | BLUNDER (786) | INACCURACY (137) | MISTAKE (218) |
| 12 | 6…Nf6 | INACCURACY (110) | INACCURACY (170) | MISTAKE (253) |
| 14 | 7…Qe7 | EXCELLENT (1) | GOOD (91) | INACCURACY (126) |
| 15 | 8.Nc3 | EXCELLENT (1) | GOOD (78) | INACCURACY (106) |
| 18 | 9…b5 | EXCELLENT (1) | MISTAKE (252) | MISTAKE (307) |
| 20 | 10…cxb5 | EXCELLENT (0) | INACCURACY (162) | INACCURACY (145) |
| 24 | 12…Rd8 | EXCELLENT (0) | INACCURACY (139) | INACCURACY (102) |
| 29 | 15.Bxd7+ | EXCELLENT (0) | MISTAKE (361) | MISTAKE (326) |

The early plies show the flatter curve: the WDL's steep slope turned small slips into a MISTAKE or
a BLUNDER. From ply 14 on, Black is lost, and the WDL saturates at 1000 / 0 / 0. `quality_v1` then
grades every move EXCELLENT, 9…b5 included (also seen in R1 §3). `quality_v2` grades them by what
they give away.

**Finding: 15.Bxd7+.** This is the start of a mate in three (Bxd7+ Nxd7 Qb8+ Nxb8 Rd8#), yet S
ranks it fifth with +3.64. Rank 1 is 15.Bxf6 at +8.60, and no line of S reports a mate. The
MISTAKE is therefore the engine's error at this depth and MultiPV, not the curve's. `quality_v1`
hid it, because the saturated WDL made every line worth 2000. Under `quality_v2`, an engine error
inside a won position now shows in the grade. This adds weight to two follow-ups already
proposed: a deeper re-search of moves graded MISTAKE or worse, and the acceptance comparison
against chess.com (Q-D §9.12).

## 4. Not in Q1
- The curve table `human_lichess_2026_08_v1`, the conversion `chesscom_lichess_v1`, the
  calibration tool and its gates (Q2).
- The chess.com acceptance (Q3).
- `ReasoningBuild` and the stored `"grading"` of the document (R4 storage; the values exist and
  encode).

## 5. Independent Q1 review (rev. 1 `6299312`): NOT_READY

The review passed the request policy and its defaults, the scale and rating resolution, the
`quality_v1` path, the `quality_v2` mapping and bands, the one-search rule, the policy reaching
`only_move_v1` and `sacrifice_sound_v1`, the scopes, the controller → context → verify path, and
the scale in the normalized request and the judgement.

| Finding | Disposition |
| --- | --- |
| B1 `LOGISTIC`'s last rounding used the process's current `decimal` context. Under `ROUND_DOWN`, 2 099 of 4 001 values differ, and the digest was checked only in a test. | Applied (§2.9). The rounding runs in the table's own context, and the digest is checked at import. Reproduced before the fix (`LOGISTIC[4]` 1004 under `ROUND_DOWN`). Tests: a subprocess first import under `ROUND_DOWN` and precision 3; a module copy with a wrong digest fails to import. |
| C1 the curve-table loader did not require the provenance of Q-D §7.2 | Applied (§2.5). `source`, `filters`, `bytes_read`, `games_read` and `games_used` are required and consistent; the test fixtures carry them. |
| C2 malformed TOML or shapes escaped as `TOMLDecodeError` / `AttributeError` | Applied (§2.5). Parse and shape failures are `ReasoningError`, and seven malformed inputs are tested. |
