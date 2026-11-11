# Eight-game survey of harness rev. 16 (2026-11-11)

**Purpose:** the owner asked to run more games to look for new kinds of error before Test 2.

**Runs:** rev. 16 at `aa57cda`, one run on each of the eight train and validation games (the
pool outside Test). The settings are the score command's: turns 90, tool calls 150, tokens 20M,
$1 a run, Haiku 5.5 over OpenRouter, four runs at a time (`python -m tools.rx.batch`).

**Judging:** bundle 80ab90d8 holds the 24 fixed moments and the 24 tier-1 sample plies, in 8
parts judged by judge v2 in Claude Code sessions.
- All eight audits passed. Parts 7–8 were audited an hour later, after the app's export limit
  (six an hour) lifted.

## 1. What the logs showed (no judging needed)

- **Network errors ended runs.** Four of the first eight runs ended on one network error each:
  an SSL EOF (twice), a connection reset, and a failed DNS lookup. The request child did not mark
  an error before the answer as `transport`, so it was never retried. This is fixed in `aa57cda`
  (change log, "network errors retried"). The four games were run again and all eight then ended
  `done`.
- **Tier 1 is nearly clean, tier 2 is not.** Tier 1 had 4 refusals in 96 plies. Tier 2 had 54
  refused submissions against 25 accepted. Tier 2 lacks what rev. 13–15 gave tier 1:

  | Tier-2 refusal | Count | What tier 1 has |
  |---|---|---|
  | numbers without their source ("1순위" and the like: 1, 3, 5, 0, 6 …) | 60+ | completion (rev. 15) |
  | short handles (`x30`, `b10`) | 13 | resolution (rev. 14) |
  | a malformed `agent` field | 11 | the guide's fixed form |
  | a comparison or fact handle cited alone | 11 | none |
  | the subject's own judgement as a proposition; no proposition | 11 | none |
  | another line's move without that line | 10+ | guide v3's rule |

- **Compactions:** 8 compactions and 7 restarts, in four of the eight games. TB-D B4 meant compaction to
  be rare.
- **Frame check v5:** it held 5 sentences (F6 four times, F1 once), all in tier 2.
- **Cost:** $0.79 for the eight completed runs. The four runs lost to network errors cost $0.17
  more.

## 2. What the judges found

| | Sentences | Wrong | Doubtful | Rate |
|---|---|---|---|---|
| Tier 2 (24 fixed moments) | 191 | 14 | 2 | 7.3 per 100 |
| Tier 1 (24 sample plies) | 67 | 1 | 0 | 1.5 per 100 |

Key causes in tier 2: 29 explained, 7 partly, 1 not.

The wrong sentences, by kind. Kinds A, B and D–F were not seen in earlier rows; C is related to
the old "change as standing" confusion, but is new in that it contradicts the cited claim:

| Kind | Sentences | Example (moment) |
|---|---|---|
| **A. An exclusive claim from one line** ("b5로 막을 수밖에", "Nc6 한 가지뿐") | 2 | hung-14: Kd8, Nbd7, Nfd7, Qb5 and c6 also meet the check |
| **B. A defence miscounted** (a piece said undefended or left to one attacker while still defended) | 2 | fourth-38: f7 still defended twice; rapid-51 (tier 1): the f3 knight still defends e5 |
| **B'. A pin said to void a defence**, though the capture ends the pin (the analysis refuted this mechanism, c34) | 2 | 184800218248-58 |
| **C. Material dismissed against the cited comparison** ("물질이 아니라 위치 평가", "얻은 것이 없다") | 4 | fourth-37 ×2, 185371835722-30, 185264271324-45 |
| **D. A segment's end read as the line's end** (a piece "kept" though taken the next move; −10 at the segment's end, −7 at the PV's) | 2 | fresh-62, 185371835722-32 |
| **E. A rank computed from a partial list** ("셋째 후보", though at least four moves were better) | 1 | 185371835722-30 |
| **F. Check direction reversed** ("체크를 받으며" for a move that gives check) | 1 | 185264271324-67 |
| Known: an old attack written as new | 1 | fresh-76 |
| Doubtful: a grade put on the wrong move; a claim about the game's next moves | 2 | fourth-56, hung-14 |

## 3. What could follow

- **Tier 2's refusals:** carry rev. 14–15's resolution and completion, and the `agent` form, over
  to tier 2. This is the largest cost lever the logs show.
- **Guide rules for kinds A, C, D and E** (both tiers):
  - an exclusive word needs the legal moves or a claim that says so;
  - a cited comparison of material is not denied;
  - a line's end is its PV's, not a segment's;
  - a rank needs a rank claim.
- **Checks by code worth trying:**
  - C: a sentence that cites a material comparison claim and writes "물질이 아니라" or
    "얻은 것이 없";
  - E: an ordinal rank ("셋째 후보") without a rank claim;
  - B: a sentence that calls a piece undefended while a cited board item counts a defender.
