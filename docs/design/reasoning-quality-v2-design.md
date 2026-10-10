# Reasoning — Q-D design: the rating-aware grade `quality_v2`

Status: **rev. 3 — independent review NOT_READY applied (§12); re-review NOT_READY (B1, C1, C2) applied (§13); awaiting re-review**.
Date: 2026-10-10. Base: `main @ 43ce741` (R2b merged, #60). Contracts:
[`reasoning-r0-design.md`](reasoning-r0-design.md) rev. 10 (R0-D) §5, §7, §14;
[`reasoning-r2-design.md`](reasoning-r2-design.md) rev. 11 (R2-D) §3 as implemented by R2b.

`quality_v1` (R0-D D3, §7.2) reads the expected points of a move from Stockfish's WDL. That WDL
models engine-strength play: +1.40 is already about 91 % and anything past +3 saturates at 0 % or
100 %. Played against human games this misgrades in both directions (§2.1): small slips of
low-rated players become blunders, and in a position the engine already counts as lost every move,
including one that allows mate, loses nothing and grades EXCELLENT. Chess.com's Expected Points
model, whose bands D3 adopted, converts the evaluation into a win chance that depends on the
players' rating.

This packet adds `quality_v2`: the same one-search loss and the same bands, with expected points
read from the evaluation of S through a **human expected-score curve** chosen by the players' average
rating and the time class, calibrated on rated Lichess games. It also fixes how a request selects the
curve, how the choice is recorded, and how the curve table is produced offline. `quality_v1` stays
selectable and unchanged.

## 0. Decisions

| # | Decision |
| --- | --- |
| Q0 | **Direction** (owner, 2026-10-10): the grade uses a human expected-score curve chosen by rating and time class and calibrated on Lichess game data, with a default scale and a per-request override. R0-D D3 is amended (R0-D §31); `quality_v1` remains a selectable policy. |
| Q1 | **One search, as before.** Every number still comes from S, the parent's basis (D3, R0-I1). `quality_v2` reads the `score` (`Cp` or `Mate`) of the lines of S instead of their WDL; nothing is compared across searches. |
| Q2 | **One-parameter curve.** The mover's expected score at `cp` centipawns (mover's view) is `1 / (1 + 10^(−cp / c))`, with the scale `c > 0`; larger `c` is flatter. It is evaluated in integers through a frozen table of the standard curve (§4.2), so the stored graph stays float-free (R0-D §14.1). |
| Q3 | **One curve per game, from the average rating** (owner, 2026-10-10). Both judged moves (the target and the previous move, R0-D §7.1) use the curve of the average of the two ratings, the quantity the table is fitted on; with one rating known, that rating. Up to a 200-point gap the average's scale fits as well as for equal players (§2.3). |
| Q4 | **Resolution order:** an explicit `scale` in the request; otherwise, when ratings and a time class are given, the curve table entry for (pool, time class, band of the average rating); otherwise the default scale **1000**, recorded as `DEFAULT` (uncalibrated). Ratings are never silently dropped: an explicit `scale` overrides them and the curve records the override (`ratings_overridden`); without a scale, ratings the build cannot resolve refuse the request (§3, reviews B1 and re-review C2). |
| Q5 | **Grades as in `quality_v1`.** Rank 1 is the only BEST; the mate-distance tables; the bands 40 / 100 / 200 / 400 in 1/2000 expected points. Only the source of `E` changes. |
| Q6 | **Readers of `E` follow the policy.** `only_move_v1` (D10, margin 400), `sacrifice_sound_v1` (`E ≥ 1000`) and every template reading `LineScore.expected` read the request's policy; their thresholds and versions are unchanged; their scopes name the policy (§5.3). |
| Q7 | **Recorded choice.** The resolved curve is part of the stored document and of each judgement; the curve table and the standard-curve table are part of the build (§6). Two analyses that differ only in scale never share bytes. |
| Q8 | **Default policy** (owner, 2026-10-10): a request that does not say uses `quality_v2`. |
| Q9 | **The curve table is data.** It is produced by an offline tool run by an operator (§7) and checked in; the runtime never downloads or fits anything. |
| Q10 | **No mate floor** (owner, 2026-10-10): a move that allows mate is graded by its loss like any other; a floor ("`Lp` is mated and `L1` is not → at least MISTAKE") is decided after the acceptance comparison of Q3 (§10). **Accepted risk:** in a position already very bad for the mover, a move that allows mate can still grade GOOD or EXCELLENT (§2.2). Q2 reports how often, per band (§7.5), so the risk is measured, not assumed. |
| Q11 | **Before R3** (owner, 2026-10-10): Q1 is implemented before R3, so the explanation is built on the human-graded judgement (§10). |
| Q12 | **Chess.com ratings are converted** (owner, 2026-10-10): the pool `chesscom` converts each rating to the Lichess scale with a versioned anchor table per time class, by piecewise-linear interpolation in integers, before averaging (§3.1). Unconverted, low chess.com ratings grade too leniently (§2.4). |

## 1. Scope

### 1.1 In scope
- `GradingSpec` in `AnalysisRequest` and its resolution (§3).
- `quality_v2` and the standard-curve table (§4).
- Passing the resolved grading to the observer and the catalogue (§5).
- Identity and storage of the choice (§6).
- The calibration tool, the curve-table format and the acceptance criteria of a band (§7).

### 1.2 Out of scope
- **Rating-gap correction.** In games with a gap the stronger side scores as if about a pawn
  better (§2.3). That offset shifts both lines of S alike and is not modelled. Gaps over 200 are too
  rare in Lichess pairings to calibrate. They are graded with the average's curve.
- The other problems found in the 2026-10-10 game analyses: GREAT on forced replies (checks,
  recaptures; `quality_v2` reduces it, §2.1, but a rule belongs to `label_v2`), positional
  blunders that no v1 template explains, and misleading `material_gain_v1` claims. Each is its own
  packet.
- Rendering the curve or the rating in the explanation (R3-D H6 keeps engine numbers out of the
  text).

## 2. Evidence

### 2.1 One annotated game (2026-10-10)
A chess.com rapid game between players rated 813 and 801 (55 plies, chess.com Game Review symbols
`?!`, `?`, `??`) was analysed move by move with Stockfish 19 at depth 12 and the R2b code. Each move
was put in one of four classes (no symbol / `?!` / `?` / `??`) and compared with chess.com's.

| Expected score from | Agreement | Moves marked without a chess.com symbol | GREAT candidates |
| --- | --- | --- | --- |
| Stockfish WDL (`quality_v1`) | 39/55 | 7 | 5...Nxd5, 28.Rxe8# |
| logistic, `c = 625` | 43/55 | 6 | 28.Rxe8# |
| logistic, `c = 800` | 46/55 | 4 | 28.Rxe8# |
| logistic, `c = 1000` | 49/55 | 1 | 28.Rxe8# |

Under `quality_v1`, 26...Re8 (`??`, allows mate) and 24...Qxb2 (`?`) graded EXCELLENT, because the
position was already 0 % for Black (R1 §3 saw the same saturation at 9…b5). One game with twelve
marked moves fits nothing; it shows the direction. The scripts of that session were not kept; the
acceptance test of Q2 (§9) re-runs the comparison.

### 2.2 Pilot calibration on Lichess data (2026-10-10)
The first 2 644 422 games of `lichess_db_standard_rated_2026-08.pgn.zst` were streamed; the
200 000 rated games with `%eval` comments and `|WhiteElo − BlackElo| ≤ 100` were kept. Each
evaluated position from ply 8 on (mate evaluations excluded, cp clipped to ±1500) contributed
(cp from White's view, White's result). `c` was fitted per (time class, average-rating band of
200) by maximum likelihood; the kept games were split into five shards and fitted again for the
spread.

| Rating | bullet | blitz | rapid | classical |
| --- | --- | --- | --- | --- |
| 800–999 | 4000 (at the search bound; 3110–4000) | 1485 (1377–1632) | 1307 (1256–1382) | — |
| 1000–1199 | 2687 (2296–3175) | 1287 (1239–1398) | 1124 (1063–1193) | — |
| 1200–1399 | 2237 (2076–2438) | 1190 (1115–1288) | 957 (910–990) | 1017 (794–1384) |
| 1400–1599 | 1937 (1804–2032) | 1048 (1022–1075) | 908 (872–950) | 850 (822–888) |
| 1600–1799 | 1717 (1674–1775) | 936 (903–1015) | 834 (790–860) | 751 (708–856) |
| 1800–1999 | 1500 (1436–1547) | 877 (857–897) | 752 (718–822) | 679 (568–824) |
| 2000–2199 | 1262 (1103–1447) | 866 (844–897) | 728 (689–788) | — |
| 2200–2399 | 1161 (1084–1266) | 774 (676–891) | 594 (572–620) | — |

`—`: fewer than 20 000 positions. The scale falls with rating and with longer time controls, so a
single constant cannot fit all games. The pilot is evidence only; the curve table of §7 is produced
from a larger sample with the band criteria of §7.3.

Expected points (1/2000) at a few scales, for comparison with the bands:

| `c` | +0.50 | +1.00 | +3.00 | +5.00 | +8.00 |
| --- | --- | --- | --- | --- | --- |
| 600 | 1096 | 1190 | 1519 | 1744 | 1911 |
| 750 | 1077 | 1152 | 1431 | 1645 | 1842 |
| 1000 | 1058 | 1115 | 1332 | 1519 | 1726 |
| 1300 | 1044 | 1088 | 1260 | 1416 | 1610 |

A move that allows mate from −5.00 loses 481 at `c = 1000` (BLUNDER) and from −8.00 loses 274
(MISTAKE); under `quality_v1` both lose 0.

### 2.3 Rating gaps (2026-10-10)
The first 5 467 024 games of the same file were streamed again; 400 000 rated blitz and rapid
games with `%eval` and `|ΔElo| ≤ 600` were kept. Per (time class, average band, gap bucket of 100,
White minus Black), `c` was fitted alone, and with an offset `d` in `E = 1/(1+10^(−(cp + d)/c))`.

| rapid, average 1200–1399 | positions | `c` | `c`, `d` |
| --- | --- | --- | --- |
| gap −200…−101 | 60 537 | 928 | 922, −116 |
| gap −100…−1 | 603 853 | 986 | 981, −40 |
| gap 0…+99 | 633 216 | 977 | 980, +23 |
| gap +100…+199 | 66 767 | 965 | 985, +115 |

The other bands (rapid and blitz, 1000–1799) look the same.
- Up to a gap of 200, the average's `c` stays within about 10 % of the equal-rating value (13 % at
  most).
- The gap shows as an offset of about 100–150 cp in favour of the stronger side. An offset of 100
  changes the slope of the curve near equality by about 1 % at `c = 1000`, so losses barely move.
- Gaps over 200 have under 50 000 positions, and only in blitz 1600–1799. There the fit is
  implausible: the offset has the wrong sign, and `c` reaches 1600. Pairing at those gaps is not
  representative.

Grading by the mover's own rating is not a model of the game's result: the two sides' curves would
disagree on the same position. The average is the quantity the data supports.

### 2.4 Chess.com ratings (2026-10-10)
Chess.com ratings run well below Lichess ratings at the low end. The converter of
[Chessiro](https://chessiro.com/chess-rating-converter) interpolates over anchor points measured
from a survey of about 20 000 players active on both sites (rating deviation under 150). It puts
chess.com rapid 815 at Lichess 1290 and 1500 at 1795; the two scales meet only near 2200 in blitz.
A community study on Lichess
([blog, 2025](https://lichess.org/@/lucb3/blog/converting-chesscom-to-lichess-ratings-a-new-data-driven-method/Ww3v70WB))
also reports a 300–500 point gap at the low end that narrows with rating. It is a personal study,
not a Lichess publication, and it compares engine move precision, a different method. It supports
the direction of the anchors but is not an independent validation of them (review, other).

For the game of §2.1 (813 and 801, rapid), the two readings differ:
- unconverted: band 800–999, `c ≈ 1307` (pilot);
- converted (≈ 1290): band 1200–1399, `c ≈ 957`;
- best fit on the game itself: `c ≈ 1000`.

Unconverted, a +1.00 → 0.00 move loses 88 (GOOD) instead of about 120 (INACCURACY).

## 3. Input (`request.py`)

```text
AnalysisRequest(root, moves, target, profile, budget, language,
                grading: GradingSpec = GradingSpec())

GradingSpec(policy: str = "quality_v2",       # "quality_v2" | "quality_v1"
            scale: int | None = None,           # explicit c, both sides
            white_rating: int | None = None,
            black_rating: int | None = None,
            rating_pool: str = "lichess",       # "lichess" | "chesscom" (§3.1)
            time_class: str | None = None)      # "bullet" | "blitz" | "rapid" | "classical"
```

**Structural checks** (R0-D §5, `InvalidAnalysisRequest`):
- `policy` is a grading policy of the build.
- Under `quality_v1`, `scale`, the ratings and `time_class` are `None` (a curve that is not used
  must not look used).
- `scale`, when given, is an integer in `[100, 20000]`; a rating, an integer in `[0, 4000]`;
  `rating_pool` is `lichess` or `chesscom`; `time_class` is one of the four.
- At least one rating and `time_class` come together: a rating without a time class, or a time
  class without a rating, is refused. A rating that cannot select a band must not be silently
  dropped (review B1).
- Reasoning does not read PGN headers. The caller passes ratings and the time class; Lichess's rule
  (estimated duration `base + 40 × increment` seconds: < 180 bullet, < 480 blitz, < 1500 rapid,
  else classical) is the recommended mapping, and it is the one the calibration tool uses (§7.1).

**Resolution**, after the structural checks (Q3, Q4):

```text
Curve(scale: int, source: "EXPLICIT" | "TABLE" | "DEFAULT",
      table: str | None, time_class: str | None,
      conversion: str | None,            # the conversion table, under `chesscom`
      conversion_pool: str | None,       # the chess.com pool whose anchors were used
      conversion_clamped: bool,          # a rating fell outside the anchors (§3.1)
      rating: int | None,                # the Lichess-scale rating the band was read from
      band: int | None,
      band_clamped: bool,                # the band was not in the table; nearest band used
      ratings_overridden: bool)          # ratings given, not used: an explicit scale won
ResolvedGrading(policy: str, curve: Curve | None)   # None under quality_v1
```

1. `scale` given → `Curve(scale, EXPLICIT, …)`; every other field `None` or `False`, except
   `ratings_overridden`, which is set when ratings are also given. The override is intended: it
   lets a caller grade a rated game on a chosen curve. It needs no table, so it is accepted in Q1
   too (re-review C2). The ratings stay in the normalized request.
2. Ratings and `time_class` given:
   - The build has no curve table for the Lichess scale → `InvalidAnalysisRequest(
     CALIBRATION_UNAVAILABLE)`. Under `chesscom`, the build also needs a conversion; without one
     the request is refused the same way. A Q1 build holds neither (§10), so Q1 accepts ratings
     only together with an explicit `scale` (step 1); otherwise it accepts the default scale.
   - Under `chesscom`, each given rating is first converted to the Lichess scale (§3.1).
   - `rating` = the average of the two, floored, or the one rating given.
   - Read the current curve table: `band = rating // 200 · 200`, the entry for (`time_class`,
     `band`). If that band is not in the table, use the nearest band of the same time class (the
     lower one on a tie) and set `band_clamped`. If the time class has no band at all →
     `InvalidAnalysisRequest(NO_BAND)`; the caller may pass an explicit `scale`.
3. No scale and no ratings → `Curve(1000, DEFAULT, …)`.

The resolution is a pure function of the request and the build; it runs before round 0 and the
result is part of the normalized analysis (§6).

### 3.1 The `chesscom` conversion
A conversion table (`src/calliope/reasoning/curves/<name>.toml`, current: `chesscom_lichess_v1`)
holds anchor pairs (chess.com rating, Lichess rating) per chess.com pool: `bullet`, `blitz`,
`rapid`. Chess.com has no live classical pool, so the time class `classical` converts with the
`rapid` anchors, and `conversion_pool = "rapid"` records that proxy (review C2).

```text
convert(r, anchors):            # anchors (x_0, y_0) … (x_n, y_n), x and y strictly increasing
  r < x_0  → y_0, clamped
  r > x_n  → y_n, clamped
  r = x_n  → y_n
  x_i ≤ r < x_{i+1} → y_i + (r − x_i) · (y_{i+1} − y_i) // (x_{i+1} − x_i)   # r = x_i → y_i
```

- **Integers only.** Floor division makes the conversion deterministic.
- **Clamping.** A rating strictly outside the anchors converts to the end anchor and sets
  `conversion_clamped`; a rating equal to an end anchor is a measured point and is not clamped
  (re-review C1). Nothing is extrapolated, because the source measured nothing there. The
  lowest anchors are 815 in rapid, 500 in blitz and 550 in bullet, so rapid players below 815 all
  read as Lichess 1290. This is a conservative policy for missing information, not a conversion:
  how far it is from those players' true level is unknown (review C2).
- **Two flags, two causes.** `conversion_clamped` (outside the anchors) and `band_clamped` (no
  band in the curve table) are kept apart, so a changed grade can be traced to its cause.
- **Provenance.** The table records its source URL, the retrieval date and the source's stated
  method. The anchors are a survey estimate (about half of players fall within the source's
  "typical range"), not a measurement of play.
- **Replacing it.** A later `chesscom_lichess_v2` may come from chess.com-annotated games by
  fitting the band against chess.com's own symbols (§11). Like a curve table, a new conversion is
  a new name in the build.

## 4. `quality_v2` (`observer.py`)

### 4.1 Steps
Inputs as in R0-D §7.2: P, C, B = `view.basis(P)` at `V_0`; the mover is P's side to move; `curve`
= the resolved curve.
1. B is not a search id → `INCONCLUSIVE` with B's reason (as `quality_v1` step 1).
2. `Lp`, `L1` as in `quality_v1` step 2; none → `INCONCLUSIVE(NOT_IN_BASIS)`.
3. No WDL requirement: every line of a regular basis has an exact score (F4-D §5.3).
4. Expected points of a line, from the mover's view, in 1/2000:
   - `Mate` for the mover → 2000; `Mate` for the opponent → 0;
   - `Cp(v)` (White's view) → `m = v` if the mover is White, else `−v`; `E = curve_points(m, c)`
     (§4.2).
5. `loss = E(L1) − E(Lp)`, floored at 0.
6. Grade: `quality_v1` step 6 unchanged (rank 1, mating, being mated, bands).

`Judgement` gains `curve: Curve | None` (`None` under `quality_v1`), and `policy`
holds `"quality_v2"`. `LineScore.wdl` becomes `Wdl | Unavailable`: kept when the engine reports it,
not read by `quality_v2`.

`quality_v1` is unchanged, including `WDL_UNAVAILABLE`.

### 4.2 The standard curve in integers

```text
T = 4000
LOGISTIC[t] = round_half_even(2000 / (1 + 10^(−t/1000)))      for t = 0 … T
curve_points(m, c) = LOGISTIC[min(T, (|m| · 1000) // c)]          if m ≥ 0
                   = 2000 − LOGISTIC[min(T, (|m| · 1000) // c)]   if m < 0
```

- `LOGISTIC` is computed at import with `decimal` at 40 digits, which is platform-independent; a
  test pins the SHA-256 of its canonical encoding, so any difference fails loudly.
- `LOGISTIC[0] = 1000`, the table is non-decreasing, and `LOGISTIC[t] = 2000` from about
  `t = 3602` on, so `T = 4000` loses nothing.
- Truncating `t` costs at most one step: the steepest slope, at `t = 0`, is about 1.15 points of
  2000 per step.
- By construction `curve_points(m, c) + curve_points(−m, c) = 2000`, so the mover's view is exact.

## 5. Passing the grading through

### 5.1 Values
`Grading` is the resolved grading as a frozen value: `policy` and `curve: Curve | None`.
The controller builds it once from the normalized request; no stage reads the request for it.

### 5.2 Signatures
- `judge(view, subject, grading)` and `scored(view, subject, search_id, grading)`.
- `ProposeContext.grading`.
- `HypothesisTemplate.verify(h, view, grading)`, and `catalogue.base.judgement(view, h, grading)`.
  Templates that read no judgement ignore it.
- `label_v1` reads grades only and is unchanged.

### 5.3 Scopes
The default scope's policies (R2-D §3.0) are `("points_v1", grading.policy)`; the templates that add
`unsafe_v1` add it after. The scale is not repeated in the scope: it is in the judgement and the
document (§6).

### 5.4 Thresholds
- `only_move_v1` (D10): rank 2 loses ≥ 400 under the request's policy. Under `quality_v2` that is
  0.20 expected points for players of this level, which is the intent of D10; the 2026-10-10
  experiment lost the GREAT on 5...Nxd5 this way (§2.1).
- `sacrifice_sound_v1`: `E(Lp) ≥ 1000` under the request's policy. R2-D §3.11's note on WDL
  saturation still applies at large evaluations: a flatter curve saturates later, not never.
- `material_loss_v1` and the other templates proposed from a grade follow the grade.

## 6. Identity and storage (amends R0-D §14)

- `ReasoningBuild.policies` lists `quality_v1`, `quality_v2`, `label_v1`, `selection_v1`; the build
  gains `curves: ((table name, digest), …)`, `conversions: ((name, digest), …)` and the digest of
  `LOGISTIC`.
- The normalized request keeps `GradingSpec` with its defaults written out.
- The document gains `"grading": ResolvedGrading` after `"request"`. On load (R0-D §14.3) the
  resolution re-runs under the current build and must equal it; otherwise `StoredGraphError`.
- `Judgement.curve` is encoded with the judgement. All values are integers or strings.

## 7. The curve table and its calibration

### 7.1 The tool (`tools/calibrate_curve/`)
An operator-run script outside `src/`. It may import the public names of `calliope.facts` (for the
check in §7.4) and never a legacy module; `tests/test_package_boundaries.py` is extended to
`tools/`.

1. **Input.** A Lichess monthly standard rated file (URL), read as a stream, either whole or up to
   a byte limit. The URL, the byte range read, and the counts of games read and used are recorded.
2. **Games used.** Rated, standard, a result of `1-0`, `0-1` or `1/2-1/2`, both ratings present,
   `|ΔElo| ≤ 100`, `%eval` on the moves, and a time class by the rule of §3.
3. **Samples.** Every position from ply 8 on with a centipawn evaluation: `x` = cp from White's
   view, an integer clipped to ±1500, and `y` = White's score (1, ½, 0). Mate evaluations are left
   out (fixed at 0 / 2000 by §4.1). The key is (time class, band of the average rating); games go
   to five shards by arrival order. Samples are aggregated per (key, `x`) as counts and score sums;
   there is no coarser binning.
4. **Fit.** `c` minimizes the mean loss of §7.6 over the key's samples, with the float curve
   `p(x, c) = 1 / (1 + 10^(−x/c))`. The search is golden-section on `log c` in `[150, 4000]`,
   run until the interval is below `10^−6`. The result is rounded half-even to an integer. The fit
   runs in floats; only the rounded integer is data.
5. **Output.** The table file (§7.2), and a report with the pilot-style matrix and spreads.

### 7.2 Format (`src/calliope/reasoning/curves/<name>.toml`)

```toml
[table]
name = "human_lichess_2026_08_v1"
pool = "lichess"
model = "logistic10"            # E = 1 / (1 + 10^(−cp / c))
band_width = 200
source = "https://database.lichess.org/standard/lichess_db_standard_rated_2026-08.pgn.zst"
bytes_read = 0                  # filled by the tool
games_read = 0
games_used = 0
filters = "rated; |dElo| <= 100; %eval; ply >= 8; no mate evals; cp clipped to 1500"
cp_ratio_permille = 1000        # §7.4

[[band]]
time_class = "rapid"
low = 800                       # the band is [low, low + band_width)
scale = 1307
positions = 210364
shard_low = 1256
shard_high = 1382
```

Integers and strings only. The name carries the source month and a version. A new month or new
filters make a new table; a build may hold several, and requests name the pool, not the table, so
the build fixes which table of a pool is current.

### 7.3 Band criteria
A fitted band is written to the table only if:
- it has ≥ 100 000 positions;
- `shard_high − shard_low ≤ 15 %` of `scale`;
- the fit is strictly inside the search interval (not at 150 or 4000).

Bands that fail are left out, and the resolution clamps to the nearest band (§3). In the pilot, for
example, bullet 800–999 fails (the fit stops at the bound), and so do blitz and rapid 600–799 and
every classical band (too few positions).

### 7.4 Engine-scale check
Lichess's `%eval` comes from Lichess's servers (Stockfish, varying versions and depths). Calliope's
centipawns come from its own profile (Stockfish 19, depth 12). The tool samples 2 000 used
positions, stratified by `|eval| ≤ 1000`, evaluates them with the release profile, and fits the
ratio `k` of Calliope's cp to Lichess's by Theil–Sen through the origin.
- If `|k − 1| ≤ 0.10`, then `cp_ratio_permille = 1000`.
- Otherwise every `scale` is multiplied by `k` (rounded), and `round(1000 · k)` is recorded.

This keeps the curve in the units the observer reads. One ratio is applied only if one ratio
describes the two scales (review C1). The check **fails** if any of these holds:
- the ratio of a bucket of Lichess's `|eval|` (100–300, 300–600, 600–1000), fitted the same way, is
  more than 15 % from `k`;
- the sign agrees in fewer than 95 % of the positions with Lichess `|eval| ≥ 100`;
- leaving out the 2 % of positions with the largest absolute residual moves `k` by more than 0.03.

A failed check writes no table. The tool reports the bucket ratios, the sign agreement and the
residuals, and the operator investigates. The sample (position digests), the engine identity and
the profile are recorded with the result.

### 7.5 Validation gates (review B2)
The band criteria of §7.3 check that a fit is stable inside its own data. They do not show that
the curve predicts results in new games. The table is written only if, in addition, it passes on
held-out games:

1. **Held out by game and by time.** The validation set is the next month's file (for
   `human_lichess_2026_08_v1`: 2026-09), with the same filters and at least a fifth of the
   training positions. No game is in both sets, and the positions of a game are never split.
2. **Prediction.** For each kept band, on the validation set, the log loss and the Brier score
   (§7.6, deployed form) of three curves: (a) the band's curve, (b) the default `c = 1000`, and (c)
   one `c` fitted on all bands of the time class.
   - A band is kept only if its log loss is not worse than (b).
   - The table as a whole must beat (b) and (c) in aggregate log loss, with the 95 % interval of
     the difference from a game-level bootstrap (1 000 resamples) excluding 0.
3. **Reliability.** Per band, positions are binned by the deployed prediction `p` into ten
   fixed-width bins `[0, 0.1)`, …, `[0.9, 1]`. Every bin with at least 2 000 positions must have
   a mean `y` within 0.03 of its mean `p`.
4. **Dependence.** Positions of one game share a result, so a long game weighs more. Each band is
   refitted with every game weighted 1 in total. A band whose game-weighted `c` differs from `c` by
   more than 10 % is flagged in the report.
5. **Selection.** About 6 % of Lichess games carry `%eval` (the requested analyses). The report
   compares, per band, the evaluated games with all games: score rate, draw rate and mean rating.
   The bias cannot be removed with this data; it is reported with the table.
6. **Mate-allowing moves** (Q10). On the validation set, the moves after which Lichess's eval turns
   into a mate against the mover are graded with `E(before) − E(after)` (the played move against
   the eval before it, a stand-in for `L1`). The report gives the share per grade and per band.

The report (all numbers above, per band) is part of the Q2 packet. Gates 1–3 block; gates 4–6 are
reported.

### 7.6 The loss (re-review B1)
The curve predicts one number, White's expected score. It does not give separate probabilities of
a win, a draw and a loss, so a categorical likelihood over three outcomes does not apply. The fit
and the gates use the fractional binary cross-entropy, with a draw as the observation `y = ½`:

```text
L(y, p) = −y · ln p − (1 − y) · ln(1 − p)        log loss, y ∈ {0, ½, 1}
B(y, p) = (p − y)²                                Brier score
```

- **What it fits.** This is an objective for the expected score (a quasi-likelihood), not a model
  of how often draws happen. For a group of samples, its minimum over `p` is the group's mean
  score, which is the quantity the observer uses.
- **Weights.** Every sample weighs 1. A long game weighs more; gate 4 measures how much that
  matters. Aggregates are means over positions; the bootstrap resamples whole games.
- **Fit form.** `p = p(x, c)` in floats (§7.1 step 4), clamped to `[10^−12, 1 − 10^−12]`.
- **Deployed form.** The gates score what ships: `p = curve_points(x, c) / 2000`, with the integer
  `c` of the table and the integer table `LOGISTIC` (§4.2). That `p` reaches 0 or 1 where
  `LOGISTIC` saturates, so it is clamped to `[1/4000, 1 − 1/4000]`, half a unit of 1/2000, before
  `L` is taken. `B` uses the unclamped `p`.
- **Bootstrap.** 1 000 resamples of the validation games with replacement. The random generator
  and its seed are recorded in the report, so the interval is reproducible.

## 8. Errors
- A bad `GradingSpec`, or a resolution refusal (`CALIBRATION_UNAVAILABLE`, `NO_BAND`) →
  `InvalidAnalysisRequest` before any fact request.
- A curve table that does not load, has a float, or breaks §7.3 → `ReasoningError` at import (a
  build defect, never a chess conclusion).

## 9. Test obligations

**Q1 (runtime):**
1. `LOGISTIC`: length `T + 1`, `LOGISTIC[0] = 1000`, non-decreasing, pinned digest, spot values
   (`t = 1000` → 1818).
2. `curve_points`: the mover's view for White and Black, `E(m) + E(−m) = 2000`, the
   floor-division boundary, mate scores 0 / 2000, a larger `c` gives a flatter value.
3. Resolution:
   - the precedence explicit > table > default;
   - the average of two ratings (floored), one rating missing;
   - `band_clamped`, and `NO_BAND` for a time class with no band;
   - `chesscom`: exact at an anchor (including both end anchors, not clamped), floor between
     anchors, `conversion_clamped` strictly below and above,
     `classical` via `rapid` anchors with `conversion_pool = "rapid"`, conversion before averaging
     (815 and 1500 rapid → 1290 and 1795 → 1542);
   - every structural refusal of §3: a curve field under `quality_v1`, a rating without a time
     class, a time class without a rating;
   - an explicit `scale` with ratings → `EXPLICIT` with `ratings_overridden`, accepted by the
     shipped Q1 build;
   - the shipped Q1 build: ratings without a scale, under `lichess` and `chesscom` →
     `CALIBRATION_UNAVAILABLE`.
     Tables used by the other resolution tests are injected into a test build and are never in
     the shipped registry.
4. Grades: `quality_v1`'s band and mate tests repeated under `quality_v2` with constructed cp
   (39 / 40 / 41 … 399 / 400 / 401). In addition:
   - a line without WDL is decided under `quality_v2` and `INCONCLUSIVE(WDL_UNAVAILABLE)` under
     `quality_v1`;
   - the saturated lost position: allowing mate from −5.00 is BLUNDER at `c = 1000` and EXCELLENT
     under `quality_v1`.
5. Passing the grading through:
   - a scripted S where rank 2's WDL margin is ≥ 400 but the `quality_v2` margin is < 400:
     `only_move_v1` is SUPPORTED under `quality_v1` and REFUTED under `quality_v2`;
   - the same contrast for `sacrifice_sound_v1`;
   - scopes name the request's policy.
6. Identity: two requests that differ only in `scale` give different normalized analyses; the
   resolved grading round-trips through the canonical encoding.
7. Existing reasoning tests that assert grades pin `GradingSpec(policy="quality_v1")` and keep
   their expectations.

**Q2 (calibration and table):**
8. The tool's parser on a fixture PGN: headers, eval comments, mate evals, a missing rating, an
   unrated game, each time class.
9. The fit recovers `c` within 2 % from synthetic samples drawn at known `c`. The band criteria
   drop a thin band and a band at a bound. On synthetic data, the validation gates of §7.5 pass
   for the true `c` and fail for a curve 30 % off. §7.6 is checked on hand-computed values: a draw
   at `p = ½` costs `ln 2`, and a saturated deployed `p` is clamped to `1/4000`. The engine-scale check fails for a
   bucket-dependent ratio and for flipped signs.
10. The table `human_lichess_2026_08_v1` loads, holds integers only, meets §7.3, and passed
    §7.4 and §7.5 (its report is in the packet); its digest is in the build. The conversion `chesscom_lichess_v1` loads, has strictly increasing anchors in
    each pool, and its digest is in the build.
11. Gated (real Stockfish): the engine-scale check of §7.4 on its recorded sample. Also, as a
    regression record only, the Opera game and the annotated game of §2.1 (player names removed)
    under `quality_v1`, `quality_v2` with `scale = 1000`, and the table. The design game is not
    evidence of agreement (review B2.4); that is Q3.

**Q3 (chess.com acceptance):**
12. Gated: at least ten chess.com Game Review games not used in this design, over at least three
    rating bands, analysed under `quality_v1`, `quality_v2` with `scale = 1000`, and the table
    (`chesscom`). For each:
    - overall agreement with chess.com's classes;
    - a confusion matrix of INACCURACY / MISTAKE / BLUNDER against `?!` / `?` / `??`, with misses
      and false marks;
    - the moves that allow mate, and their grades.

## 10. Delivery

| Packet | Content | Gate |
| --- | --- | --- |
| Q-D (this) | `GradingSpec`, `quality_v2`, the standard curve, passing the grading through, identity, the curve table and tool | independent review READY |
| Q1 | §3–§6. The shipped build has no curve table and no conversion: explicit and default scales only; ratings without a scale refused (`CALIBRATION_UNAVAILABLE`) | READY |
| Q2 | §7: the tool; the table `human_lichess_2026_08_v1` from at least one full month, validated on 2026-09 (§7.5 gates 1–3) with the engine-scale check (§7.4); the conversion `chesscom_lichess_v1` (§3.1). Ratings are accepted from Q2 on | READY |
| Q3 | §9.12: the chess.com acceptance on owner-supplied games; the mate floor (Q10) and a chess.com-fitted conversion (§11) are decided on it | READY |

Q1 comes before R3 (Q11). The R3-D review can go on in parallel. R3 is then built on Q1: its
golden examples are graded by `quality_v2` and recomputed where R3-D's differ. Q1 touches
`request.py`, where R3-D amends `language`, and the `Judgement` encoding.

## 11. Later

- **A conversion from chess.com's own judgements.** Fit the conversion, or the band per chess.com
  rating directly, against chess.com Game Review symbols on annotated games, a few dozen per rating
  band. That would replace the survey anchors of §3.1 with a measurement of the grading being
  imitated.
- **A rating-gap offset** (§1.2, §2.3), if acceptance shows gap games misgraded.
- **A mate floor** (Q10), decided by the acceptance of Q3 (§9.12) and the report of §7.5.6.

## 12. Review dispositions (rev. 1 `c2c00b7`, independent Q-D review: NOT_READY)

The review passed the one-search grade, the integer curve and its determinism, the Chessiro
anchors and the interpolation, and the identity of versions, sources and builds.

| Finding | Disposition |
| --- | --- |
| B1 Q1 declares `chesscom` but the conversion ships in Q2 | Applied, and widened: the Lichess curve table also ships in Q2, so ratings under either pool were unresolvable in Q1. Ratings now resolve only with the build's tables, otherwise `CALIBRATION_UNAVAILABLE`. The Q1 build ships none (§3, §10). A rating must come with a time class, and a time class with no band refuses (`NO_BAND`) instead of falling back to the default. |
| B2 no held-out test of the calibration | Applied: §7.5 adds a next-month holdout disjoint by game, log loss and Brier against two baselines with a game-level bootstrap, reliability per decile, game-weighted refits, the selection report and the mate-allowing report. Gates 1–3 block the table. The chess.com agreement on games outside the design (B2.4) is packet Q3 (§9.12). It needs owner-supplied games and blocks the decisions that depend on it (mate floor, conversion v2), not the Lichess table. |
| C1 one ratio may not describe the cp scales | Applied: bucket ratios, sign agreement and a residual-trim test; a failed check writes no table (§7.4). |
| C2 one `clamped` flag mixes two causes; the classical proxy is not recorded | Applied: `conversion_clamped`, `band_clamped` and `conversion_pool` (§3, §3.1). |
| C3 mate-allowing moves can still grade GOOD / EXCELLENT | Recorded as an accepted risk in Q10. It is measured per band in §7.5.6 and §9.12. |
| Other: the Lichess blog is a community study with a different method | Wording corrected (§2.4): supporting, not an independent validation. |

## 13. Review dispositions (rev. 2 `dc9dd2c`, independent re-review: NOT_READY)

The re-review found B1, B2 and C1–C3 of §12 resolved, and passed the Q1 / Q2 boundary, the holdout
and the engine-scale check.

| Finding | Disposition |
| --- | --- |
| B1 the fit objective and the validation metrics with draws are undefined | Applied: §7.6 defines the fractional binary cross-entropy with `y = ½` for a draw (an expected-score objective, not a draw model), the Brier score, weight 1 per position, the float fit form, and the deployed integer form the gates score, clamped at half a unit. It also fixes the bootstrap seed. §7.1 now fits per integer cp with a defined stop and rounding. §7.5 gate 3 uses fixed-width bins, since "deciles" was ambiguous. |
| C1 an exact end anchor was marked clamped | Applied: `r < x_0` and `r > x_n` clamp; end anchors are exact (§3.1, test §9.3). |
| C2 an explicit scale with ratings contradicted "ratings are never ignored" | Applied: the override is intended and recorded (`ratings_overridden`). It is accepted in Q1 because it needs no table (Q4, §3, tests §9.3). |
