# Reasoning — packet Q2 implementation: the calibrated curve table (monotone) and its tool

Status: **rev. 2 — independent Q2 review READY_WITH_CORRECTIONS (C1; notes N1, N2) applied (§6)**.
Date: 2026-10-11. Design: [`reasoning-quality-v2-design.md`](reasoning-quality-v2-design.md) rev. 5
(Q-D §3.1, §7) as amended by [`reasoning-quality-v2-monotone-design.md`](reasoning-quality-v2-monotone-design.md)
rev. 3 (QM-D). Base: `main @ 3077478` (QM-D merged, #64).

Q2 delivers four things:
- the calibration tool `tools/calibrate_curve/`;
- the runtime support for the monotone band curve;
- the curve table `human_lichess_2026_08_v2`, fitted on the whole 2026-08 Lichess file and validated
  on 2026-09;
- the chess.com conversion `chesscom_lichess_v1`.

From Q2 on, ratings with a time class resolve to a table band.

The branch also keeps the first, logistic run of the tool (`human_lichess_2026_08_v1.json` and
`.log`). It failed Q-D gate 3 and wrote no table. That failure is what QM-D answers.

## 1. Scope delivered

| Module | Content |
| --- | --- |
| `reasoning/grading.py` | **Grid and evaluation:** `MONOTONE_V1_KNOTS` (the 61-knot grid of QM-D §5 step 2) and `table_points` (QM-D §4). **Values:** `Curve.model` (`logistic10` or `monotone_v1`), with `Curve.scale` `None` under a table; `Grading.points` (the band's runtime knots, QM-D §7). **Tables:** `CurveBand` (`points`, `positions`, `shard_deviation`, `interpolated`); `CurveTable.knots` (runtime knots, QM-D §6.4); `runtime_knots`. **Loader:** `load_curve_table` takes only `monotone_v1` on the exact grid, with the checks of QM-D §9. The logistic table form is retired, since no logistic table ever shipped. |
| `reasoning/observer.py` | `score_points(score, mover, grading)`: a `TABLE` curve reads `grading.points`; an explicit or default scale reads `curve_points` |
| `reasoning/curves/human_lichess_2026_08_v2.toml` | the table: 28 bands, `cp_ratio_permille = 1103` (§3) |
| `reasoning/curves/chesscom_lichess_v1.toml` | the conversion (Q-D §3.1), unchanged since the first Q2 commit |
| `tools/calibrate_curve/pgn.py` | **Evals bound to moves** (QM-D §8.1): `evals` counts the moves between comments. It returns `None` for a game with an eval missing before its last eval, or with variations. |
| `tools/calibrate_curve/fit.py` | **The monotone fit** (QM-D §5): `symmetric`, `estimates` (coverage 400), `monotone` (refusal below 600 cp, isotonic, fill, rounding). **The logistic fit** of Q-D §7.1 step 4, for the baselines. |
| `tools/calibrate_curve/data.py` | **`Training`:** the aggregates and shards, plus `games_eval_gap`. **`Validation`:** the held-out month scored as it streams against fixed curves. It keeps per-game loss sums for the bootstrap, per-band sums, reliability bins with game-cluster sums, the gate 6 counts and the plateau counts. |
| `tools/calibrate_curve/gates.py` | **Selection** in the training month (QM-D §6.1): `select`, with positions, coverage, shard deviation and cross-fitted log loss and reliability. **Curves:** `Curves`, which builds (a)–(e) per key with the (d) fallback (QM-D §6.2). **Gates:** `validate`, with gates 1–3, the game-level bootstrap, and the per-band, plateau, gate 5 and gate 6 reports; `weight_flags` gives gate 4. |
| `tools/calibrate_curve/__main__.py` | **Streams:** `Stream`, with the `HEAD` `Content-Length`, both exit codes and the byte count (QM-D §8.3). **Runs:** exploratory runs (`--train-bytes`, `partial = true`, never a table). **Output:** the published game count, and the table and the report. |

## 2. Implementation decisions within the design

1. **The validation month is scored as it streams.** QM-D §6.1 fixes the table before the
   validation month is read. So every curve the gates need is known in advance, and the positions are
   never stored. Each game adds its loss sums under (a)–(d) to per-game arrays for the bootstrap,
   and its sums to its band. Memory falls from about 330 MB of packed positions to the per-game
   arrays (12 MB for 1.5 M games).
2. **(e)** is the table at twice the bandwidth (QM-D §5's sensitivity). It is scored with the
   others, and reported only.
3. **The bootstrap** draws `random.Random(20261010).choices` over the games, 1 000 times. The sums
   use `map` over precomputed per-game differences, which takes about 15 minutes for 1.5 M games.
4. **The gate 3 cluster standard error** uses per-bin sums of `r_g`, `n_g`, `r_g²`, `r_g·n_g` and
   `n_g²` over games. These give `Σ (r_g − mean · n_g)²` without storing the games.
5. **The plateau report** uses gate 6's consecutive centipawn evals, ply ≥ 9, in the mover's
   view. A move is *worse* when the eval falls by at least 10 cp. It is *plateau-zero* when it is
   worse and its table loss is 0.
6. **`shard_deviation` in the table** is the ceiling of the measured value. "Stored ≤ 10" is then
   exactly "measured ≤ 10".
7. **`Curve` field order** follows QM-D §7: `Curve(model, scale, source, …)`.

## 3. Evidence

### 3.1 Tests
- **`tests/reasoning/test_grading.py`, 99 tests.** It covers QM-D §10.1–§10.5 and §10.11:
  - `table_points`, including a plateau;
  - score points under a table;
  - resolution with knots, including a clamped band;
  - band boundaries 39 … 401 under a table;
  - knots in the identity, round-tripped through the encoding;
  - 17 defective tables, including a two-knot grid and a moved knot;
  - six missing provenance fields;
  - the carry-over at 1300 ‰ within `⌈s⌉ + 1`;
  - the shipped table.
- **`tests/tools/test_calibrate_curve.py`, 38 tests.** It covers QM-D §10.6–§10.10 and Q-D §9.8:
  - eval gaps, tails and variations;
  - smoothing bias at most 20 on two logistics and the shelf curve;
  - seeded draws within 4 SE and 8 units weighted;
  - a dip, and the coverage paths (interpolate, hold, refuse, `W_0 = 0`);
  - selection: thin, noisy, an unstable shard, a cross-fitted reliability failure, and no reads of
    the validation month;
  - the gates on the true curves, a logistic table failing gate 3, and a curve 30 % off failing
    gate 2;
  - the (d) fallback and the plateau counts;
  - a truncated stream, a short read, and a whole run that writes a loadable table;
  - an exploratory run that writes none;
  - gate 4 reports every kept band as MEASURED or UNESTIMABLE (review C1).

| Suite | Result |
| --- | --- |
| `tests/reasoning`, `tests/tools`, `tests/test_package_boundaries.py` | 309 passed, 1 skipped (the gated Stockfish test) |

### 3.2 Exploratory run (first 1 GB of 2026-08, `partial = true`)
- **Streams and the mode:** both streams ended as designed. The training stream stopped at the
  limit, the validation stream at its target, and neither failed. The report was written and no
  table.
- **Bands:** none was kept. With about 3 500 games per shard, shard deviations were 15–42. The
  positions of a game share its result, so the effective sample is the games.

### 3.3 The full run (`tools/calibrate_curve/reports/human_lichess_2026_08_v2.json`, `.log`)
- **Training:**
  - 30 145 862 359 bytes, equal to `Content-Length`, with both exit codes 0;
  - 91 912 325 games, equal to Lichess's published count;
  - 7 473 129 games used, 413 314 079 positions;
  - 278 games skipped for an eval gap.
- **Validation (2026-09):** 1 497 046 games and 82 662 816 positions, stopped at the target with no
  failure. No game was skipped for an eval gap.
- **Selection:** 28 of 58 bands kept (blitz 800–2400, bullet 1000–2400, rapid 600–2200, classical
  1600–1800). Kept bands have shard deviations of 2.1–8.9.
  - 15 bands were left out for fewer than 100 000 positions.
  - 13 bands were left out for a shard deviation above 10, all at the edges, with 0.2–2.7 M
    positions.
  - 2 bands were left out because a shard left knots below 600 cp unestimated.
  - No band failed the cross-fitted checks. On held-out shards, the table beat the band logistic by
    0.0002–0.0023 per position.
- **Engine scale:** `k` = 1.1031, so `cp_ratio_permille` = 1103. The bucket ratios were 1.098,
  1.162 and 1.066, the sign agreement 0.999, and the trimmed `k` 1.106. The runtime knots run up to
  1654.
- **Gate 2** (82.66 M positions, 1.50 M games, 669 681 positions on a (d) fallback):

  | curve | log loss | difference of the table, 95 % (games) |
  | --- | --- | --- |
  | (a) table | 0.61000 | — |
  | (b) `c = 1000` | 0.61787 | −0.00801 … −0.00773 |
  | (c) pooled logistic | 0.61315 | −0.00324 … −0.00307 |
  | (d) band logistic | 0.61086 | −0.00089 … −0.00083 |

- **Gate 3:** 0 failing bins of 256 tested. On the same positions, (d) fails 31.
- **Gate 4** (report only, review C1):
  - 27 of the 28 kept bands are measured and flagged. Their game-weighted tables deviate by 23–42
    units (§4.3).
  - Classical 1800 is unestimable: with each game weighing 1, a knot below 600 cp has a coverage
    under 400, so its weighted fit stops (QM-D §5 step 3). Its `weighted_deviation` is `null`.
  - The committed report predates the fix and lists the 27 under `game_weighted_flags`. From the fix
    on, `game_weighted` lists every kept band as MEASURED (deviation, flagged) or UNESTIMABLE (the
    knots).
- **Plateaus:** the erased share is at most 0.39 % (bullet 2400), and no band is flagged. The
  plateau-zero share is at most 0.75 % of worsening moves (rapid 2000, bullet 2400).
- **The table's shape** (rapid 1200, `e` at 10 / 100 / 300 / 600 / 1000 / 1500 source cp): 1024,
  1159, 1283, 1578, 1838, 1881. `e_n` runs from 1504 (bullet 1000) to 1942 (classical 1800).

### 3.4 Gated real-engine record (Q-D §9.11)
`python -m tools.calibrate_curve.acceptance` was run with Stockfish 19 and the shipped build.
- **The annotated game of Q-D §2.1:** 813 and 801 chess.com rapid ratings, both converted to 1290 and
  clamped, give band rapid 1200. Agreement with chess.com's symbols on its 55 plies:

  | grading | agreement |
  | --- | --- |
  | `quality_v1` | 37 / 55 |
  | `quality_v2`, `scale = 1000` | 49 / 55 |
  | `quality_v2`, table | 43 / 55 |

  - The table marks four moves `?!` that chess.com left unmarked, and grades three `?!` moves
    MISTAKE.
  - It is harsher than `c = 1000` near equality and milder with an advantage of one or two pawns,
    as QM-D §2.2 predicts.
  - This is one game, and the design game. It is a regression record, not evidence of agreement
    (Q-D B2.4). The acceptance comparison is Q3.
- **The Opera game** under `quality_v1` and `scale = 1000` is unchanged from Q1 (§3 of the Q1
  record). It has no ratings, so the table does not apply.

## 4. Findings for the reviewer

1. **QM-D §6.1's shard-size estimate was wrong, but its criterion holds.**
   - The design said a full-month shard holds about 2.6 times a sample half. It holds about 4.8
     times.
   - More important, the positions of one game share its result, so the deviation scales with the
     number of games per shard.
   - At full scale the bound falls between about 1.4 M positions (classical 1800 kept at 8.9) and
     2.7 M (bullet 800 left out at 12.0): the noisier the time class, the more positions a band
     needs. It keeps every band of the main rating range and leaves out the edges. The 1 GB run
     kept nothing.
2. **`cp_ratio_permille` sits at the 10 % boundary.** The logistic run measured `k` = 1.0988
   (stored 1000), and this run 1.1031 (stored 1103). The months were the same, and only the sampled
   positions differed. The rule is applied as designed. A 2 000-position sample cannot settle which
   side of 1.10 the true ratio lies on, though, and the stored value then moves every knot by
   10 %. A later revision could widen the sample, or replace the threshold by always storing the
   rounded ratio.
3. **Gate 4 flags every measured band** (27 of 28; classical 1800 is unestimable, §3.3).
   Weighting each game 1 instead of each position 1 moves every measured table by 23–42 units, so
   long games weigh heavily. The logistic run showed the same (26 of 35 bands
   over 10 %). It is report only by design. The open question for Q3 is which weighting matches
   chess.com's grading.
4. **Missed mates in won positions** (QM-D §12): `e_n` is as low as 1504. In bullet 1000, a
   missed mate from +15 loses about 496 (BLUNDER).

## 5. Not in Q2
- The chess.com acceptance on owner-supplied games, the mate floor and a chess.com-fitted
  conversion (Q3). Q3 also grades its games with `cp_ratio_permille` 1000 and 1103 (§6 N1), and
  judges the table on agreement with chess.com's classes, not on Lichess log loss (§6 N2).
- `ReasoningBuild` and storage of the document's `"grading"` (R4).

## 6. Independent Q2 review (rev. 1 `23b6211`): READY_WITH_CORRECTIONS

The review passed:
- gates 1–3 and the engine-scale check;
- the whole-file read;
- the selection and the clamping of left-out bands;
- the eval binding;
- the monotone fit, the 61 knots and the integer interpolation;
- the shard and cross-fit selection;
- the game-level bootstrap and the stream checks;
- Q1 compatibility and the shipped build.

It found no blocker.

| Finding | Disposition |
| --- | --- |
| C1 gate 4 reported 27 bands, not "all 28"; classical 1800's weighted fit is unestimable and was silent | Applied. `weight_flags` lists every kept band as MEASURED (deviation, flagged) or UNESTIMABLE (`weighted_unestimated`, the knots below 600 cp without coverage). The report key is `game_weighted`. A test covers both statuses and the omission of refused bands. §3.3 and §4.3 are corrected. |
| N1 `cp_ratio_permille` 1000 or 1103 changes the runtime knots by about 10 % | Recorded (§4.2, §5). Q3 grades its games under both values and reports the grade changes. Until then, 1103 is a measurement on one sample, not a settled constant. |
| N2 better Lichess prediction is not better agreement with chess.com | Recorded (§3.4, §5). The one design game favours `c = 1000` (49 against 43 of 55). Q3's acceptance on unseen games decides. |
