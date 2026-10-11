# Reasoning — packet Q3: the chess.com acceptance (tool delivered, acceptance pending)

Status: **rev. 1 — tool delivered; the acceptance itself waits for owner-supplied games**.
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
  - Per game, the plies where a class is given or the gradings disagree.
- **Tests** (`tests/tools/test_acceptance.py`, 5, no engine):
  - chess.com time controls;
  - classes from NAGs and suffixes;
  - the design game recognized;
  - the 1000 ‰ build changing only the ratio;
  - tallies, bands, sensitivity and mate moves.

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
