# Reasoning — packet Q3: the chess.com acceptance (tool delivered, acceptance pending)

Status: **rev. 5 — running monitor (§5); monitor entries of 2026-10-11 recorded (§6), with an engine-depth measurement; grading and engine profile unchanged (owner)**.
Date: 2026-10-11. Design: [`reasoning-quality-v2-design.md`](reasoning-quality-v2-design.md)
§9.12 (Q-D), with the Q2 review's notes N1 and N2
([`reasoning-q2-implementation.md`](reasoning-q2-implementation.md) §6). Base: `main @ 37f1b2a`
(Q2 merged, #65).

Q3 compares Calliope's grades with chess.com Game Review on games that were not used in the
design. It needs at least ten such games over at least three rating bands. Its results decide the
open questions:
- the mate floor (Q-D Q10);
- a chess.com-fitted conversion (Q-D §11);
- the `cp_ratio_permille` of the shipped table, 1000 or 1103 (N1);
- whether the table's better Lichess prediction is better agreement with chess.com (N2).

The games must come from the owner, since Game Review's classes are not in public PGNs. Until they
arrive, this packet delivers the tool and records what it has run on.

## 1. The tool (`tools/calibrate_curve/acceptance.py`)

`python -m tools.calibrate_curve.acceptance GAMES [--out STEM] [--include-design-game] [--opera]`

- **Input:** a PGN file, or a folder of PGN files.
  - **Classes:** as NAGs or move suffixes: `$6` / `?!` inaccuracy, `$2` / `?` mistake, `$4` / `??`
    blunder, `$9` miss, `$3` / `!!` brilliant.
  - **Ratings:** `WhiteElo` / `BlackElo`, in pool `chesscom`.
  - **Time class:** from `TimeControl` by Lichess's rule. chess.com's `600` means 600 + 0, and a
    daily game (`1/259200`) has no time class.
- **One search per move.** Round 0 runs once per ply, under the table grading. The same search is
  then judged (`judge(view, subject, grading)`) under four gradings:
  - `quality_v1`;
  - `quality_v2` at `scale = 1000`;
  - the shipped table;
  - the same table with `cp_ratio_permille = 1000` (N1).
- **Excluded game.** The design game of Q-D §2.1 is recognized by its moves and left out unless
  asked for (Q-D B2.4).
- **Output:** a Markdown report and a JSON summary.
  - Agreement on the classes `·` / `?!` / `?` / `??`. chess.com's `miss` and `!!` count as `·`
    here; `miss` is compared with `label_v1` once labels are run.
  - Missed and false marks, and the confusion pairs.
  - Tallies per chess.com band of 400.
  - The number of plies whose grade changes between 1103 ‰ and 1000 ‰.
  - The moves that allow or miss mate, with their grades.
  - **Miss apart** (rev. 2). chess.com marks a missed opportunity Miss instead of a grade. The grade
    agreement therefore leaves those plies out and reports, per grading, how many of them it marks
    as an error.
  - **Labels** (rev. 2, `--labels`). The full reasoner runs per move under the table grading. Its
    labels are compared ply by ply with chess.com's Great (`$1`), Brilliant (`$3`) and Miss (`$9`),
    listing matches, ours only and chess.com only. chess.com's PGN export carries no Best,
    Excellent or Good.
  - Per game, the plies where a class is given or the gradings disagree.
- **Tests** (`tests/tools/test_acceptance.py`, 6, no engine):
  - chess.com time controls;
  - classes from NAGs and suffixes;
  - the design game recognized;
  - the 1000 ‰ build changing only the ratio;
  - tallies, bands, sensitivity and mate moves, with Miss counted apart;
  - the label comparison.

## 2. Runs so far (not acceptance evidence)

**The design game** (`--include-design-game`): 813 / 801 rapid, band rapid 1200, 55 plies.

| grading | agreement | missed marks | false marks |
| --- | --- | --- | --- |
| `quality_v1` | 37 (67 %) | 4 | 9 |
| `scale = 1000` | 49 (89 %) | 1 | 2 |
| table (1103 ‰) | 43 (78 %) | 2 | 5 |
| table (1000 ‰) | 44 (80 %) | 1 | 5 |

- **Ratio sensitivity:** 2 of the 55 plies change grade between 1103 ‰ and 1000 ‰.
- **Mate moves:** both mate-allowing moves (26…Re8, chess.com `??`; 27…Nxf7, `?!`) are graded
  BLUNDER and MISTAKE by every `quality_v2` grading, and EXCELLENT by `quality_v1`.

**An owner game without classes** (2026-10-10, 803 / 813 rapid, 54 plies; the chess.com analysis
page could not be read, since Game Review needs a browser session).
- **Grades only, no agreement:**
  - all three `quality_v2` gradings mark 11…Bh5, 15.g5 and 16.Nxg5 as MISTAKE or worse;
  - the table is harsher than `c = 1000` near equality (11.h3: INACCURACY 150 against GOOD 76);
  - the table is milder with an advantage (14.h5: GOOD 82 against INACCURACY 116);
  - `quality_v1` grades every move EXCELLENT from move 17, once Black is a piece up.
- **Ratio sensitivity:** 1 of the 54 plies changes between 1103 ‰ and 1000 ‰.

## 3. What remains for Q3

1. **Collect the games.** The owner supplies at least ten chess.com games with Game Review classes,
   over at least three rating bands. A game can come as PGN with the classes, or as the moves with
   the list of classified moves.
2. **Run the tool,** and report the four gradings per band.
3. **Decide the open questions** in a Q3 rev. 2: the mate floor, the ratio, and the conversion.
4. **Labels:** add `label_v1`'s GREAT and MISS against chess.com's `Great` and `Miss`. This needs
   the full reasoner per move, not only round 0.

## 4. Owner-supplied games (rev. 3)

Four chess.com games supplied by the owner, exported with Game Review's NAGs (`$1` Great, `$3`
Brilliant, `$9` Miss, `$2` / `$4` / `$6`). chess.com's export carries no Best, Excellent or Good.
The PGNs carry player names and are not committed. The report is reproduced with
`python -m tools.calibrate_curve.acceptance <folder> --labels`.

| game | ratings (chess.com band) | time class | plies | chess.com marks |
| --- | --- | --- | --- | --- |
| 2026-10-10 | 803 / 813 (800–1199) | rapid | 54 | 1 Brilliant, 3 `?`, 4 `?!` |
| 2023-11-21 | 1524 / 1526 (1200–1599) | rapid | 29 | 1 Brilliant, 2 Miss, 1 `??`, 3 `?`, 6 `?!` |
| 2026-10-06 | 2037 / 2603 (2000–2399) | rapid | 66 | 2 Great, 6 Miss, 9 `?`, 10 `?!` |
| 2026-10-04 | 2674 / 2475 (2400–2799) | bullet (30 s) | 45 | 1 Brilliant, 5 Great, 2 Miss, 3 `??`, 4 `?`, 2 `?!` |
| 2023-11-27 (rev. 4) | 1477 / 1520 (1200–1599) | rapid | 27 | 5 `?`, 4 `?!` |

**Grades** (Miss plies left out of the agreement):

| grading | 800–1199 | 1200–1599 | 2000–2399 | 2400–2799 (bullet) | all | Miss marked as an error |
| --- | --- | --- | --- | --- | --- | --- |
| `quality_v1` | 40 / 54 | 18 / 27 | 44 / 60 | **38 / 43** | 140 / 184 (76 %) | 10 / 10 |
| `scale = 1000` | **51 / 54** | **22 / 27** | 45 / 60 | 31 / 43 | 149 / 184 (81 %) | 5 / 10 |
| table (1103 ‰) | 47 / 54 | 21 / 27 | **47 / 60** | 35 / 43 | **150 / 184 (82 %)** | 9 / 10 |
| table (1000 ‰) | 47 / 54 | 22 / 27 | 47 / 60 | 34 / 43 | 150 / 184 (82 %) | 9 / 10 |

- **No grading leads in every band.**
  - `c = 1000` leads in the two low bands.
  - The table leads in the 2000s and overall.
  - The engine's WDL (`quality_v1`) leads in the high bullet game.
- **Miss.** The table marks 9 of chess.com's 10 Misses as errors; `c = 1000` marks 5.
- **The ratio** (N1): 1103 ‰ and 1000 ‰ differ on 2 plies in total.
- **Boundary cases.** Several of the table's false marks sit at the INACCURACY boundary (loss
  100).
- **Reading.** Four games, one per band, decide nothing yet. Q3's decisions (the mate floor, the
  ratio, the conversion) wait for at least ten.

**Labels** (`label_v1` on the table grading; the `label_v2` column projects LV-D's rules with the
prototype of its §2.2):

| label | chess.com | `label_v1`: ours / matched | `label_v2` (LV-D rev. 3): ours / matched |
| --- | --- | --- | --- |
| GREAT | 7 | 9 / 2 | 2 / 2 |
| BRILLIANT | 3 | 0 / 0 | 3 / 2 (`brilliant_p1`) |
| MISS | 10 | 1 / 1 | unchanged |

- **GREAT.**
  - **Matched:** 33…Qe3+ and 19.Nxf6+.
  - **`label_v1`'s seven extra GREATs:** four rescues of an attacked piece (14…Nd8, 12…Bg6, 14…Bh7,
    10.Nxe6) and three recaptures (13…axb5, 24.Nxa1, 12.Bxd6). LV-D's exclusions remove all seven.
  - **Unmatched chess.com Greats:** 5.cxd4, 14.Nh3, 17…Bd6, 22.Kh1, 28…Nc5. Their margin over the
    second line, in the table's expected points, is 45–153, under `only_move_v1`'s 400. 14.Nh3 is
    itself a rescue and 22.Kh1 a check evasion. chess.com's Great therefore follows neither the
    margin nor the move type alone; LV-D rev. 3 marks GREAT provisional.
- **BRILLIANT** (`brilliant_p1`, prototype):
  - **Found:** 9.Nxd4 and 7.Ne4, and also 27.Bxf7+ of the design game.
  - **Missed:** 18.Nh5, which leaves an already hanging rook en prise. That is the kind of move
    excluded to cut false calls (LV-D §2.2).
  - **One false call:** 10.Nxe6, a capture that leaves an already hanging rook.
- **MISS.** One match, 16…Qc7. LV-D §12 records the MISS v2 packet.

**Status.** Four games over four bands. The band condition is met; at least six more games are
needed.

## 5. Decision: grading frozen, Q3 as a monitor (owner, 2026-10-11)

**After the fifth game** (211 plies without Miss):

| grading | agreement | missed marks | false marks | Miss as an error |
| --- | --- | --- | --- | --- |
| `quality_v1` | 159 (75.4 %) | 22 | 11 | 10 / 10 |
| `scale = 1000` | 169 (80.1 %) | 26 | 4 | 5 / 10 |
| table (1103 ‰) | 171 (81.0 %) | 17 | 9 | 9 / 10 |
| table (1000 ‰) | 172 (81.5 %) | 16 | 9 | 9 / 10 |

**Disagreements of the table** (40 plies, by distance of its loss to the boundary that would have
matched chess.com):

| kind | plies | reading |
| --- | --- | --- |
| one class apart | 34 | the same direction, a different degree |
| two classes apart | 6 | the engines disagree |
| within 30 of a boundary (1.5 % of a point) | 13 | noise |
| 31–80 from a boundary | 15 | mostly the one-sided shift below |
| more than 80 | 12 | engine depth (for example best at depth 12, `?!` for chess.com) |

**The one-sided part.** Eight times chess.com marks `?` where the table's loss is 124–165
(INACCURACY), and almost never the reverse. Near the MISTAKE boundary the table's losses run below
chess.com's. Tilting the curve toward chess.com might recover one or two percent, but five games
would over-fit chess.com's unpublished model.

**Decision.** The owner judged that further work on grades has little return. Calliope's aim is
credible grades and explanations, not a copy of chess.com, and the grades already agree on
direction: four in five match exactly, and 85 % of the rest are one class apart.
- **Frozen.** `quality_v2` with `human_lichess_2026_08_v2` (1103 ‰) stays as shipped.
- **Q3 becomes a running monitor.** Owner games are added to the report as they come, with no
  fixed end.
- **Open decisions.** The mate floor (Q10), the ratio (N1) and a chess.com conversion stay open.
  They are taken only if the monitor shows a clear need.
- **No acceptance gate** (review C1 of PR #66, 2026-10-11). With grading frozen, the monitor has no
  pass condition of its own.
  - Its games are the independent evidence for LV-D's provisional labels.
  - The gate for making those final is LV-D §8, which names its metrics: brilliant recall, false
    calls per 1 000 moves, GREAT precision and recall.

## 6. Monitor entries (2026-10-11)

Two more owner games, analysed with the full reasoner (`label_v2`, `brilliant_p2`, the shipped
table, Stockfish 19 at depth 12). These entries are records, not decisions. Grading stays frozen
(§5), and the owner keeps the engine profile `d12_mpv5_v1` for now (§6.3).

### 6.1 2025-10-14, 1700 / 1724, rapid, 100 plies, with Game Review marks

chess.com marks 14 plies: 8 `?!`, 4 `?`, 1 `??`, 2 Miss. It marks no Great or Brilliant.

| result | plies |
| --- | --- |
| same grade | 4…Nge7 `?!`, 8…h6 `?`, 10…Be6 `?!`, 14.f4 `?`, 15.O-O `??`, 15…Ne3 `?!`, 22.f6 `?` |
| Miss matched | 14…Ng4 (`label_v2` MISS) |
| one class apart | 4.a3 (GOOD, loss 76), 13…Ne5 (GOOD, 66), 16.Qd2 (BLUNDER 487 against `?`) |
| not matched | 9.Bxe7 (Miss; ours MISTAKE without MISS), 47.hxg5 (`?!`; ours EXCELLENT, loss 0), 49.c7 (`?!`; ours BEST) |
| ours only | 9…Qxe7+ (INACCURACY, 112), 34…a5 (INACCURACY, 120) |

- **9.Bxe7 (Miss not found).** It is evidence for the MISS v2 packet (LV-D §12).
  - The best line, 9.Bf6, is a stable gain of one point.
  - The played line's exchange (Bxe7 Qxe7+ …) is still open at the PV's end, so `better_move_v1`
    is INCONCLUSIVE (`LINE_TOO_SHORT`) and no MISS is made.
- **47.hxg5 and 49.c7 (engine depth).**
  - At depth 12 the played move ties with rank 1 (−6.33 / −6.33 and −8.95 / −8.95), so the loss
    is 0.
  - The position is lost already (`E` 150–450).
- **No false label.**

### 6.2 2026-10-11, 821 / 814, rapid, 73 plies, without Game Review marks

- **Labels.**
  - No label is made.
  - The only SUPPORTED `only_move_v1` is 14.Qxb7, which is also a rescue (`rescue_v1`), so GREAT
    is withheld.
  - White is at `E ≥ 1700` from move 14, which rules out BRILLIANT (LV-D §5 step 4).
- **16…O-O is ungraded.** Its judgement is INCONCLUSIVE (`IRREGULAR_SEARCH`): a line of S did not
  end at full depth with an exact bound.
- **8…exd5: GOOD, loss 73.** The owner reports that chess.com's evaluation for this move falls
  from about +1.6 to +3.9. Game Review's class for it is not known yet. The owner did not find it a
  GOOD move.
  - **Ours.**
    - S: Ne7, Bg7 and e5 all at about +1.40 (black `E` 821).
    - exd5 is outside MultiPV 5 and is scored by the comparison search: +2.70 (`E` 748).
    - The curve is band 1200, rapid. chess.com 821 converts to 1292, clamped at the conversion's
      lowest anchor.
  - **Engine depth** (the position before 8…exd5, one thread, white's view):

    | depth | best lines | exd5 | drop |
    | --- | --- | --- | --- |
    | 12 | +1.41 … +1.54 | +2.94 | ≈ 1.4 |
    | 18 | +1.39 | +3.54 | ≈ 2.2 |
    | 22 | +1.57 … +1.72 | +4.25 | ≈ 2.6 |

  - **The curve** (black's loss for the same change, by chess.com rating):

    | chess.com rating (band) | +1.40 → +2.70 (ours) | +1.60 → +3.90 (chess.com) |
    | --- | --- | --- |
    | 814 (1200) | 73 GOOD | 127 INACCURACY |
    | 1200 (1400) | 87 GOOD | 151 INACCURACY |
    | 1500 (1600) | 100 INACCURACY | 175 INACCURACY |
    | 2000 (2000) | 127 INACCURACY | 210 MISTAKE |

  - **Reading: both causes contribute.**
    - **Depth.** Depth 12 sees about half of the drop. With chess.com's evaluations alone, the
      grade moves from GOOD to INACCURACY.
    - **The low-band curve.** Even chess.com's 2.3-pawn drop costs a 1200-band player six points
      in a hundred (40 % → 34 %). MISTAKE would need the 2000 band. This matches the one-sided
      shift of §5: the table's losses run below chess.com's.
    - **The clamped conversion.** A lower true equivalent would flatten the curve further.
  - **To check.** Game Review's class for 8…exd5, when the owner can export it.

### 6.3 Engine depth: cost measured, profile unchanged (owner)
The owner reports that chess.com's analysis default is depth 22, a 5 s limit and three lines. One
search each on 28 positions from the two games, with one thread on this machine (two cores):

| profile | median | p90 | max | short of the depth |
| --- | --- | --- | --- | --- |
| d12, 5 lines (shipped) | 0.16 s | 0.62 s | 0.79 s | 0 / 28 |
| d22, 3 lines, 5 s cap | 5.0 s | 5.0 s | 5.0 s | 21 / 28 |
| d22, 3 lines, no cap | 10.8 s | 18.1 s | 48.9 s | 0 / 28 |
| d18, 3 lines | 2.7 s | 5.1 s | 7.8 s | 0 / 28 |
| d18, 5 lines | 5.2 s | 10.0 s | 29.5 s | 0 / 28 |
| d16, 5 lines | 2.9 s | 5.9 s | 29.5 s | 0 / 28 |

- **Depth 22 with a 5 s cap does not fit.** The cap would stop most searches. A time-stopped
  search is irregular by design (results must not depend on load), so most judgements would be
  INCONCLUSIVE.
- **Threads.** chess.com reaches depth 22 in 5 s with many threads. Determinism fixes ours at one
  (F4-D M2).
- **Determinism held.** The same request gave identical scores on repeated runs and after other
  analyses in the same engine process.
- **Owner decision (2026-10-11).** Keep `d12_mpv5_v1`.
  - Candidates for a later profile packet: d16 with 5 lines, or d18 with 3 lines (about 15–25 min
    per 100-ply game).
  - That packet should first compare d12 / d16 / d18 on the marked games: agreement, INCONCLUSIVE
    plies, time.
