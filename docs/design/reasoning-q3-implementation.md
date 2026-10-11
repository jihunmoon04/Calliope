# Reasoning — packet Q3: the chess.com acceptance (tool delivered, acceptance pending)

Status: **rev. 2 — tool extended (Miss apart, labels); 2 of at least 10 owner games analysed (§4)**.
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

## 4. Owner games (rev. 2)

Two chess.com rapid games from the owner, exported with Game Review's NAGs. The PGNs carry player
names and are not committed. The report is reproduced with
`python -m tools.calibrate_curve.acceptance <folder> --labels`.

| game | ratings (band) | plies | chess.com marks |
| --- | --- | --- | --- |
| 2026-10-10 | 803 / 813 (rapid 800–1199) | 54 | 1 Brilliant, 3 `?`, 4 `?!` |
| 2026-10-06 | 2037 / 2603 (rapid 2000–2399) | 66 | 2 Great, 6 Miss, 9 `?`, 10 `?!` |

**Grades** (Miss plies left out of the agreement):

| grading | 800–1199 | 2000–2399 | both | Miss marked as an error |
| --- | --- | --- | --- | --- |
| `quality_v1` | 40 / 54 | 44 / 60 | 84 / 114 (74 %) | 6 / 6 |
| `scale = 1000` | **51 / 54** | 45 / 60 | **96 / 114 (84 %)** | 2 / 6 |
| table (1103 ‰) | 47 / 54 | **47 / 60** | 94 / 114 (82 %) | **6 / 6** |
| table (1000 ‰) | 47 / 54 | 47 / 60 | 94 / 114 (82 %) | 6 / 6 |

- **By band.** `c = 1000` agrees best in the low band, as on the design game. The table agrees best
  in the high band, and it is the only grading after `quality_v1` to mark every Miss as an error.
- **The ratio** (N1): 2 of the 120 plies change grade between 1103 ‰ and 1000 ‰.
- **Boundary cases.** Two of the table's false marks in the low game sit exactly on the INACCURACY
  boundary (loss 100).

**Labels** (`label_v1`, table grading):

| label | chess.com | ours | matched | ours only | chess.com only |
| --- | --- | --- | --- | --- | --- |
| GREAT | 2 | 6 | 1 (33…Qe3+) | axb5, Nd8, Nxa1, Bg6, Bh7 | 28…Nc5 |
| BRILLIANT | 1 | 0 | 0 | — | 7.Ne4 (`label_v1` assigns none) |
| MISS | 6 | 0 | 0 | — | all six |

- **GREAT.** Of the five extra GREATs, two are recaptures and three retreat an attacked piece.
  LV-D's exclusions remove the recaptures. The retreats are the evidence for LV-D rev. 2's added
  exclusion.
- **BRILLIANT.** LV-D's provisional `brilliant_p1` passes 7.Ne4 on every condition (prototype):
  - offer 3;
  - created and saveable;
  - loss 59;
  - `E(Lp)` 1095;
  - best non-offering line 1154;
  - after 7…Nxe4, the mover's `E` is 1737, and the capture is a BLUNDER.
- **MISS.** `label_v1` needs the opponent's previous move to grade MISTAKE or worse, and a best line
  that wins material or mates. chess.com's Miss also covers lost positional chances.
  - This is 0 of 7 Miss so far, counting the design game's 21…g6.
  - A MISS packet is recorded in LV-D rev. 2.

**Status.** Two games over two bands. Q3 needs at least ten games over at least three bands before
its decisions: the mate floor, the ratio and the conversion.
