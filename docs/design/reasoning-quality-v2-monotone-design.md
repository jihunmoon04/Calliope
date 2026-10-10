# Reasoning — QM-D design: a monotone curve table for `quality_v2`

Status: **rev. 1 — awaiting independent review**.
Date: 2026-10-10. Base: `main @ d146c77` (Q1 merged, #63). Amends
[`reasoning-quality-v2-design.md`](reasoning-quality-v2-design.md) rev. 5 (Q-D): Q2 of §0, §4.1,
§6, §7.1–§7.6, §9.8–§9.11, §10. Evidence: the Q2 run on branch `calibration/q2-curve-table`
(`c4477f5`, report `tools/calibrate_curve/reports/human_lichess_2026_08_v1.json`).

Q-D fitted one scale `c` per (time class, rating band) to a logistic curve. The full-month Q2 run
fitted it on 413 million positions. It then scored the curve on 82.7 million held-out positions,
and the curve failed the reliability gate (Q-D §7.5 gate 3) in 51 of 334 bins. The failure is
systematic, and it comes from the curve's shape, not from noise (§2). Human results rise faster
than the logistic near equality, more slowly with an advantage of one or two pawns, and faster
again from about a piece. One scale cannot follow that shape.

This packet replaces the curve of a table band with a **monotone, antisymmetric, piecewise-linear
table in integers**, fitted directly from the data. It keeps everything else in place: the single
search, the integer expected points, the bands, the resolution, the flags, the logistic for an
explicit or default scale, and the gates. It also takes in the corrections that the independent
Q2 review asked of the tool (§8).

## 0. Decisions

| # | Decision |
| --- | --- |
| M0 | **Direction** (owner, 2026-10-10): the curve of a table band becomes a monotone lookup table. This replaces Q-D Q2 ("one-parameter curve") for table curves. |
| M1 | **Curve of a band.** The mover's expected points at `m` centipawns (mover's view), in 1/2000, are read from knots `(x_i, e_i)` with `x_0 = 0` and `e_0 = 1000`, non-decreasing `e_i`, linear interpolation in integers between knots, and `e_n` beyond the last knot. Negative `m` is read by antisymmetry: `E(−m) = 2000 − E(m)` (§4). |
| M2 | **Explicit and default scales stay logistic.** `scale` in the request and the default 1000 keep `curve_points` and `LOGISTIC` (Q-D §4.2) unchanged. A table is needed only to resolve ratings, and only a table band is monotone. |
| M3 | **The policy stays `quality_v2`.** Q-D defines `quality_v2` as expected points read from a human curve chosen by rating and time class. The form of the curve is data of the build, recorded in `Curve.model` and the table's digest. No build has shipped a curve table, since Q1's shipped build is empty (Q-D §10). So no stored judgement changes meaning. |
| M4 | **Fit.** The fit is direct: no search and no parameter. The samples are symmetrized, then smoothed with a Gaussian kernel at fixed knots whose bandwidth equals the local knot spacing. A weighted isotonic regression follows, and each value is rounded half-even to 1/2000 (§5). |
| M5 | **Band criteria in curve terms.** A band needs at least 100 000 positions, and a shard deviation of at most 10 units (§6.1). The old search-bound criterion has no counterpart. |
| M6 | **Gates.** Gates 1 and 3 are unchanged. Gate 2 adds a fourth curve, the per-band logistic of Q-D, which the table must beat on aggregate (§6.2). |
| M7 | **Recorded function.** The resolved grading stores the band's runtime knots. A judgement keeps only the curve's identity. Loading a document re-resolves the grading and compares the knots (§7). |
| M8 | **Table name.** The first table is `human_lichess_2026_08_v2`. The name `…_v1` stays with the failed logistic run and its report, and no table carries it. |
| M9 | **Tool corrections** (independent Q2 review, B1, B2, C1): evals are bound to their move, the bootstrap resamples games, and a stream that ends early or abnormally fails the run (§8). |

## 1. Scope

**In scope:**
- the band curve model and its integer evaluation (§4);
- the fit (§5);
- the band criteria and gates as they apply to the new model (§6);
- the identity of the band's curve (§7);
- the tool corrections (§8);
- the table format (§9);
- the tests (§10);
- delivery (§11).

**Out of scope:**
- **A side-to-move or White-advantage term.** The runtime curve is antisymmetric in the mover's
  view, as in Q-D. The measured White score at an eval near 0 is 0.46–0.52 per band (§2.3). Gate 3
  scores in White's view, so a material asymmetry shows there.
- **A monotone default curve.** The default stays the logistic `c = 1000` (M2). A pooled
  monotone default would need its own evidence of benefit.
- The mate floor, the rating-gap offset and the chess.com-fitted conversion stay as Q-D §11
  leaves them.

## 2. Evidence

### 2.1 Full-month run, logistic table (Q2, `c4477f5`)
- **Data.** Training was the whole 2026-08 file: 30 145 862 359 bytes, equal to the server's
  `Content-Length`, and 91 912 325 games, equal to Lichess's published count. From it, 7.47 M games
  and 413 M positions were used. The validation set was 2026-09, read up to 82.7 M positions
  (1.50 M games).
- **Fit.** 38 of 58 bands met Q-D §7.3, and 35 remained after the per-band test of gate 2. The
  engine-scale check passed (`k` = 1.099, `cp_ratio_permille` = 1000).
- **Gate 2 passed.** The log loss was 0.61087 for the table, against 0.61787 at `c = 1000` and
  0.61315 for the pooled curve. Both 95 % intervals were below 0, with upper bounds of −0.0068 and
  −0.0022.
- **Gate 3 failed** in 51 of 334 bins. Over all kept bands, the bins show this pattern:

  | bin of `p` | mean `p` | mean `y` | `y − p` | failing bins (sign) |
  | --- | --- | --- | --- | --- |
  | [0.0, 0.1) | 0.063 | 0.079 | +0.016 | 8 (y > p) |
  | [0.4, 0.5) | 0.466 | 0.445 | −0.021 | 12 (y < p), 1 (y > p) |
  | [0.5, 0.6) | 0.529 | 0.542 | +0.013 | 0 |
  | [0.7, 0.8) | 0.750 | 0.735 | −0.015 | 5 (y < p), 1 (y > p) |
  | [0.9, 1.0] | 0.936 | 0.920 | −0.017 | 8 (y < p) |

  Results rise faster than `p` across equality, between bins 4 and 5, and slower than `p` in the
  tails. The per-bin cluster standard errors put the central deviations at 9 to 14 standard errors.

### 2.2 The shape of human results (sample, 2026-08)
- **Sample.** The first 2.5 GB of the 2026-08 file: 606 202 evaluated games kept by Q-D's filters.
  The games were split alternately into a fit half and a test half.
- **Raw curve.** Symmetrized samples, 25 cp bins, White's view folded to the side ahead. The
  logistic is the band's `source_scale` at the bin centre.

  | rapid 1200–1399, `x` | 0–24 | 100–124 | 200–224 | 300–324 | 400–424 | 500–524 | 600–624 | 700–724 |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | observed | 0.516 | 0.588 | 0.619 | 0.644 | 0.690 | 0.750 | 0.810 | 0.862 |
  | logistic `c = 1020` | 0.506 | 0.562 | 0.617 | 0.668 | 0.717 | 0.760 | 0.799 | 0.833 |

  The observed curve is steep up to about 100 cp and flatter from 100 to 350. It is steeper again
  from 350 to 700, which is about the value of a minor piece. Blitz 1400 and blitz 800 show the same
  shape, and the flat middle is longer at lower ratings.
- **Gate 3 on the test half.** Here gate 3 means bins with ≥ 2 000 positions and a tolerance of
  0.03. It covers the 19 bands with ≥ 300 000 fit positions in the sample.

  | curve | failing bins | per band, log loss against the logistic |
  | --- | --- | --- |
  | logistic, the band's `source_scale` | 26 | — |
  | monotone, bandwidth = 1 × knot spacing (§5) | **3** | −0.0002 … −0.0014 |
  | monotone, 2 × spacing | 4 | — |
  | monotone, 4 × spacing | 38 (over-smoothed tails) | — |

- **Grades** (proxy: the loss of a played move is `E(eval before) − E(eval after)`, with the
  Lichess evals of the test half). Against the logistic, the monotone table (1 × spacing, fitted on
  the fit half) changes the grade of 16.5 % of moves overall, 12–26 % per band. Changes of two
  bands or more are 0.14 %. Every other change is one band:

  | logistic grade | share of all moves that change, and to what |
  | --- | --- |
  | EXCELLENT | 4.9 % → GOOD |
  | GOOD | 2.6 % → EXCELLENT, 3.5 % → INACCURACY |
  | INACCURACY | 2.1 % → GOOD, 1.6 % → MISTAKE |
  | MISTAKE | 1.1 % → INACCURACY, 0.24 % → BLUNDER |
  | BLUNDER | 0.33 % → MISTAKE |
- **Noise floor.** Tables built from the two halves differ in 4–12 % of grades. Lower bands have
  the larger effect. Their gap between the change and the noise floor is about 10–15 points, and
  about 5 points from 1800 up. A full month holds about 13 times the sample, so its noise floor is
  lower.

### 2.3 White's score near equality
In the test half, White's score at `|x| ≤ 20` is between 0.49 and 0.515 in 17 of the 19 bands. It
is 0.480 in rapid 1000 and 0.464 in rapid 800. The antisymmetric table cannot represent this.
Gate 3 measures in White's view, so a band where it matters fails there.

### 2.4 The Q2 review's alignment question (B1)
In the first 30 000 evaluated games of each of 2026-08 and 2026-09, no game misses an eval before
its last evaluated move. About 30 % miss only the eval after the last move, almost all of them
because the game ends in checkmate. The Q2 tool's alignment was therefore correct on this data. It
was never checked, though, and §8.1 makes the check part of the tool.

## 3. What changes, and what does not

| Area | Change |
| --- | --- |
| Request, `GradingSpec`, structural checks | none |
| Resolution order, refusals (`CALIBRATION_UNAVAILABLE`, `NO_BAND`), flags, the chess.com conversion | none |
| `Curve` | gains `model`. `scale` becomes `int \| None`, with `None` for a table band (§7) |
| `Grading` | gains `points`, the band's runtime knots (§7) |
| Observer, Q-D §4.1 step 4 | `E` comes from the band's table under `TABLE`, and from `curve_points(m, scale)` otherwise (§4) |
| Grades, bands, mate rules, `only_move_v1`, `sacrifice_sound_v1`, scopes | none. Each reads `E` through the grading, as Q-D §5 has it |
| Table format and loader | the `logistic10` model is retired before any table shipped, and `monotone_v1` is the only table model (§9) |
| Fit, band criteria, gates | §5, §6 |
| Tool | §8 |

## 4. The band curve (amends Q-D §4.1)

```text
Knots  (x_0, e_0) … (x_n, e_n):  x_0 = 0 < x_1 < … < x_n          runtime cp (mover's view)
                                 e_0 = 1000 ≤ e_1 ≤ … ≤ e_n ≤ 2000   1/2000 expected points

table_points(m, knots):
  a = |m|
  a ≥ x_n                 → v = e_n
  x_i ≤ a < x_{i+1}       → v = e_i + (a − x_i) · (e_{i+1} − e_i) // (x_{i+1} − x_i)
  m ≥ 0 → v;   m < 0 → 2000 − v
```

- **Integers only.** Floor division makes it deterministic. As with `curve_points`,
  `table_points(m) + table_points(−m) = 2000` holds exactly, and `m = 0` gives 1000.
- **Monotone.** For non-decreasing `e_i`, `table_points` is non-decreasing in `m`. A better line
  never has lower `E`, so `loss ≥ 0` keeps its meaning.
- **Beyond the last knot** the value is `e_n`, the smoothed score at the clip (§5). A mate stays at
  2000 or 0 (Q-D §4.1).
  - **Allowing mate.** From beyond the clip, a move that allows mate loses `e_n` (a BLUNDER in every
    band of §2.2). Q10's accepted risk is unchanged.
  - **Missing a mate.** A move that misses a mate for a centipawn line loses `2000 − E(Lp)`. Human
    results do not saturate where the logistic does. In the sample, `e_n` is 1562 in bullet
    1200–1399 and 1915 in rapid 1800–1999. So a missed mate at +15 grades harsher than under the
    logistic: 438 (BLUNDER) in bullet 1200, against 121 (INACCURACY) in rapid 1200. The mate-distance
    rules (R0-D §7.2) apply only when both lines are mates and are unchanged. This is a new
    consequence of the human curve, not a new rule. It is recorded as a risk (§12) for Q3 to judge.
- **Step 4 of Q-D §4.1** becomes: `Cp(v)` → `m` as before, then `E = table_points(m,
  grading.points)` when `curve.source = TABLE`, else `curve_points(m, curve.scale)`.

## 5. The fit (amends Q-D §7.1 step 4)

Inputs: the training aggregates of a key per integer `x` in `[−1500, 1500]` (Q-D §7.1 step 3).

1. **Symmetrize.** Every sample `(x, y)` also counts as `(−x, 1 − y)`. This gives `n(x)` and
   `s(x)`, the count and score sum per `x`. At `x = 0` the mean is exactly ½, which makes the curve
   antisymmetric, as the runtime reads it.
2. **Knots.** These are fixed, in source (Lichess) cp:
   - `0, 10, …, 290` (30 knots);
   - `300, 325, …, 575` (12 knots);
   - `600, 650, …, 1500` (19 knots).

   That is 61 in all: dense where positions and slope are concentrated, sparse in the tails.
3. **Smooth.** At knot `i`, with spacing `Δ_i = x_{i+1} − x_i` (the last knot uses `Δ_{n−1}`) and
   bandwidth `h_i = Δ_i`:
   `w(x) = exp(−((x − x_i) / h_i)² / 2)` for integer `x` with `|x − x_i| ≤ 3 h_i` in the range;
   `v_i = Σ w·s / Σ w·n` and `W_i = Σ w·n`.
4. **Isotonic.** Weighted pool-adjacent-violators over `(v_i, W_i)` gives a non-decreasing
   sequence, which is then raised to at least ½ (`v_i ← max(v_i, ½)`).
5. **Integers.** `e_0 = 1000` and `e_i = round_half_even(2000 · v_i)`, using Python's `round` on
   the float. Rounding preserves the order, so the integers stay non-decreasing.

The fit runs in floats, and only the integers are data. Two settings are fixed in advance rather
than fitted: the bandwidth multiplier 1 and the grid. §2.2 is why. A multiplier of 4 over-smooths
the tails and fails gate 3 in 38 bins, against 3 bins at 1 and 4 at 2. The report gives each band's
table at multiplier 2 as a sensitivity, with its log-loss and gate-3 results (report only).

**Plateaus.** Where the data are flat or noisy, the isotonic step can make neighbouring knots
equal. Inside a plateau a move loses nothing. The report lists, per band, the plateaus that start
below 600 cp. They are not a gate: §2.2 shows them mostly in the thinnest bands, and a full month
reduces them. Q3's acceptance comparison (Q-D §9.12) is where a grade they cause would show.

## 6. Criteria and gates

### 6.1 Band criteria (replaces Q-D §7.3)
Every value is in source units. A fitted band is written only if:
- it has ≥ 100 000 positions;
- **shard deviation ≤ 10.** Each of the five shards (Q-D §7.1 step 3) is fitted alone by §5. The
  deviation of a shard is the position-weighted mean `|E_shard(x) − E_band(x)|` over the band's
  samples, in 1/2000 units. `shard_deviation`, the largest of the five, must be at most 10.

In the sample, curves from two independent halves differ by 6–19 units on this measure. A full-month
shard holds about 2.6 times a sample half, and is compared with the band, not with another shard.
The expected deviation is about 2.5–7.5, so 10 admits stable bands and refuses thin ones. The
report gives every band's value.

### 6.2 Validation gates (amends Q-D §7.5)
- **Gate 1:** unchanged.
- **Gate 2** scores four curves on the same population as Q-D:
  - (a) the table, with each band's knots in source units, or the nearest kept band's for a band
    left out;
  - (b) the default `c = 1000`;
  - (c) one logistic `c` per time class (pooled);
  - (d) one logistic `c` per band, fitted as in Q-D §7.1 step 4 on the same samples.
  - **Per band:** a kept band stays only if its log loss is not worse than (b) or (d).
  - **Aggregate:** (a) must beat (b), (c) and (d), each with the game-level 95 % interval of the
    difference excluding 0 (§8.2).
- **Gate 3:** unchanged, with `p = table_points(x, source knots) / 2000`. The report also gives
  gate 3 for (d), so the change is visible.
- **Gate 4** (report only): a band whose game-weighted table deviates from its table by more than
  10 units, on the measure of §6.1, is flagged.
- **Gates 5 and 6:** unchanged, with the band's table.

### 6.3 The loss (amends Q-D §7.6)
- **Deployed form:** `p = table_points(x, source knots) / 2000`, clamped to `[1/4000, 1 − 1/4000]`
  for `L`, unclamped for `B`.
- **Fit form:** none. The fit is not an optimization, though step 3 of §5 is the kernel estimate
  of the mean score, which minimizes `L` locally.
- (b), (c) and (d) keep the logistic forms of Q-D.

### 6.4 Engine-scale check (amends Q-D §7.4 step 3)
- **Check:** unchanged.
- **Runtime knots:** the runtime knots are `x'_i = round_half_even(x_i · cp_ratio_permille /
  1000)`, in integers as in Q-D §7.4. They must remain strictly increasing, and the loader refuses
  the table otherwise. The `e_i` are unchanged.
- **Identity:** with `cp_ratio_permille = 1000`, the runtime knots are the source knots.

## 7. Identity (amends Q-D §3 and §6)

```text
Curve(model: "logistic10" | "monotone_v1",
      scale: int | None,          # logistic10: c; monotone_v1: None
      source, table, time_class, conversion, conversion_pool, conversion_clamped,
      rating, band, band_clamped, ratings_overridden)            # as Q-D §3
Grading(policy, curve,
        points: tuple[tuple[int, int], ...] | None)   # (x'_i, e_i) of the band under TABLE; else None
```

- **Two models.** `EXPLICIT` and `DEFAULT` give `model = "logistic10"` with `scale`. `TABLE`
  gives `model = "monotone_v1"`, `scale = None` and the band's runtime knots in
  `Grading.points`.
- **Stored once.** The document's `"grading"` (Q-D §6) stores `points`. So the stored analysis
  holds the exact function it was graded with, and the load-time re-resolution compares it too.
- **Judgements** carry `Judgement.curve` as before, as the identity of the curve
  (table, time class, band and flags), without repeating the knots.
- **Build.** The build keeps `curves: ((table name, digest), …)` and the `LOGISTIC` digest.
  `GradingBuild.identity()` is unchanged in shape.

## 8. Tool corrections (independent Q2 review)

### 8.1 Evals bound to moves (B1)
- **Reading.** Evals are read per mainline move. A move's ply is its index in the movetext, not
  the count of eval comments before it.
- **Skipped games.** A game whose eval comments do not cover every ply from 1 up to its last
  evaluated ply is skipped. It is counted in the report as `games_eval_gap`. A missing tail (the
  move after the last eval) is allowed, as in §2.4.
- **Who uses the ply.** The samples, the mate-allowing report (gate 6) and the engine-scale sample
  all use the same ply.
- **Test:** a fixture with an eval missing mid-game is skipped and counted. A fixture missing only
  the last eval is used.

### 8.2 Game-level bootstrap (B2)
- **What is stored.** The validation set stores, per game, its position count and its summed
  losses under each curve of gate 2. Positions are still packed by key for gate 3.
- **Resampling.** The bootstrap draws games: 1 000 resamples with replacement, from
  `random.Random(20261010)`. The interval of a difference is the 2.5 % and 97.5 % quantile of the
  ratio of summed differences to summed positions.
- **Gate 3 errors.** The report's cluster standard errors (gate 3, report only) use games as
  clusters.
- **What the report records.** `"units": "games"`, and the number of games.

### 8.3 Stream integrity (C1)
- **Exit codes.** The tool checks the exit codes of `curl` and `zstd`.
- **Whole file.** A read of a whole file passes only if both exit with 0, and the bytes read equal
  the `Content-Length` of a `HEAD` request made before the read.
- **Early stop.** The only allowed early stop is the validation target of gate 1. Its byte and
  game counts are recorded with `stopped_at_target = true`.
- **Failure.** Any other early end fails the run: no table, and a report that names the failing
  process.
- **Game counts.** When Lichess publishes a game count for the file (`counts.txt`), the report
  compares `games_read` with it. This is reported, not a gate.

## 9. Table format (replaces Q-D §7.2)

```toml
[table]
name = "human_lichess_2026_08_v2"
pool = "lichess"
model = "monotone_v1"
band_width = 200
knots = [0, 10, 20, …, 290, 300, 325, …, 575, 600, 650, …, 1500]   # source cp (§5)
source = "https://database.lichess.org/standard/lichess_db_standard_rated_2026-08.pgn.zst"
bytes_read = 30145862359
games_read = 91912325
games_used = 0                  # filled by the tool
filters = "rated; standard; |dElo| <= 100; %eval contiguous; ply >= 8; no mate evals; cp clipped to 1500"
fit = "symmetrized; gaussian h = knot spacing; weighted isotonic; round half-even"
cp_ratio_permille = 1000

[[band]]
time_class = "rapid"
low = 1200
points = [1000, …]              # e_i at each knot, 1/2000
positions = 869589
shard_deviation = 6             # §6.1
```

**Loader checks** (`ReasoningError` at load, as in Q-D §8):
- The table holds integers and strings only, and its provenance is present and consistent (as in
  Q1).
- `model = "monotone_v1"`.
- `knots` are strictly increasing integers from 0.
- Every band has `len(points) = len(knots)`, `points[0] = 1000`, non-decreasing points of at most
  2000, `positions ≥ 100 000` and `shard_deviation ≤ 10`.
- The runtime knots of §6.4 are strictly increasing.
- `low` is on the band grid, the time class is known, and no band is duplicated.

## 10. Test obligations (amend Q-D §9)

**Runtime:**
1. `table_points`:
   - `m = 0` gives 1000, and every knot gives its `e_i`;
   - the floor between knots;
   - beyond the last knot;
   - `E(m) + E(−m) = 2000`;
   - non-decreasing over `[−2000, 2000]` for a table with a plateau;
   - mates are 2000 and 0.
2. Resolution: a `TABLE` curve has `model = "monotone_v1"`, `scale = None` and the band's runtime
   knots in `Grading.points`, including for a clamped band (the nearest band's knots).
   `EXPLICIT` and `DEFAULT` keep `logistic10` and `points = None`.
3. Observer: Q-D §9.4's band boundaries 39 / 40 / 41 … 399 / 400 / 401, with constructed knots
   under a `TABLE` grading. The same lines under `EXPLICIT` give the logistic values.
4. Identity: two gradings that differ in one knot value give different normalized analyses. The
   grading with `points` round-trips through the canonical encoding.
5. Loader: one refusal per check of §9, and the runtime knots collide at a small
   `cp_ratio_permille`.

**Tool:**

6. **Fit:**
   - On 10⁶ synthetic samples, `x` uniform on `[−1500, 1500]`, drawn from a known monotone
     curve, the table is within 20 units at every knot, and within 5 units weighted.
   - On logistic samples, the table matches `curve_points` within the same bounds.
   - On a curve with a dip, the result is non-decreasing.
   - `e_0 = 1000` holds exactly.
7. **Criteria:** a band of 99 999 positions is refused, and so is a band whose shards are drawn
   from different curves.
8. **Gates, on synthetic data:**
   - the true monotone curve passes gates 2 and 3;
   - a logistic table fails gate 3 on data from an S-shaped curve with a flat middle;
   - a curve 30 % off fails gate 2.
9. **Engine scale:** with `x_C = 1.3 · x_L` and `cp_ratio_permille = 1300`, the observer reading
   `x_C` on the runtime knots gives the source `E` within `⌈s⌉ + 1` units. Here `s` is the table's
   steepest slope in units per runtime cp. This replaces Q-D §9.10's "within one unit", which did
   not hold for the logistic either.
10. **§8:** the fixtures of §8.1. Game resampling, checked on a tiny set against an enumeration of
    one resample. A truncated stream (a `zstd` error) fails the run. A byte count short of
    `Content-Length` fails the run.
11. **Record:** the table `human_lichess_2026_08_v2` loads, meets §6.1 and passed §6.4 and gates
    1–3. Its report is in the packet. The gated real-engine records of Q-D §9.11 are rerun with
    the table.

## 11. Delivery (amends Q-D §10)

| Packet | Content | Gate |
| --- | --- | --- |
| QM-D (this) | the monotone band curve, its fit, criteria, gates, identity, tool corrections | independent review READY |
| Q2 (revised) | the tool corrections of §8; the fit, criteria and gates of §5–§6; the runtime support of §4, §7, §9 (`table_points`, `Curve.model`, `Grading.points`, the loader); a full-month run producing `human_lichess_2026_08_v2` with its report; the conversion `chesscom_lichess_v1`, unchanged. Ratings are accepted from Q2 on | READY |
| Q3 | unchanged (Q-D §9.12) | READY |

The Q2 branch keeps its first run and report (`human_lichess_2026_08_v1.json`) as the record of the
logistic attempt. The revised run writes a separate report.

## 12. Risks

- **Plateaus** (§5): a slip inside a plateau grades EXCELLENT. The risk is measured and reported
  per band, and judged in Q3.
- **Proxy evidence:** the grade shares of §2.2 use Lichess's eval before the move in place of
  Calliope's rank 1. They indicate the size of the change, not the final grades.
- **Selection:** as in Q-D gate 5, evaluated games are a requested-analysis subset. The table
  inherits that bias, and it is reported.
- **Missed mates in won positions** (§4): mates stay at 2000 or 0, while the human curve ends at
  `e_n` (1562–1915 in §2.2). So in low bands a missed mate from a winning centipawn line grades
  harsher than under the logistic, up to BLUNDER. The report gives `e_n` per band. Q3 judges it
  together with the mate floor (Q10): on the same evidence it can choose a mate value per band (for
  example `e_n` itself), or keep 2000.
- **White's advantage** (§2.3): a low band with a material asymmetry can fail gate 3 for that
  reason alone. It is then left out, and its ratings clamp to the nearest kept band.
