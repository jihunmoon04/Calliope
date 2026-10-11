# Reasoning — packet LV1 implementation: `label_v2`

Status: **rev. 1 — awaiting independent review**.
Date: 2026-10-11. Design: [`reasoning-label-v2-design.md`](reasoning-label-v2-design.md) rev. 5
(LV-D), on [`fact-engine-f6-design.md`](fact-engine-f6-design.md) (F6, merged #69). Base:
`main @ 574b91e`.

## 1. Scope delivered

| Module | Content |
| --- | --- |
| `reasoning/labels.py` | **`label_v2`**, in order: FORCED (exactly one legal move, also without a decided judgement; rule `forced_v1`); BRILLIANT (grade BEST, EXCELLENT or GOOD, with SUPPORTED `piece_sacrifice_v1` and `capture_holds_v1` resting on it; rule `brilliant_p1`, provisional); GREAT (`label_v1`'s rule minus in check, recapture, mate in one and SUPPORTED `rescue_v1`; rule `great_p2`, provisional); MISS (`label_v1`'s rule; `miss_v1`). **`LabelKind.FORCED`.** **`Label.rule`** and **`Label.provisional`**, last, with defaults. `label_v1` is kept. |
| `reasoning/catalogue/exchange.py` (new) | `PieceSacrifice` (`piece_sacrifice_v1`, LV-D §5 steps 1–4), `CaptureHolds` (`capture_holds_v1`, §5 step 5, §6.2), `Rescue` (`rescue_v1`, §4.1); the parameters of `brilliant_p1` as named constants |
| `reasoning/catalogue/__init__.py` | the three templates after `sacrifice_compensated_v1`: 24 templates |
| `reasoning/findings.py` | `SacrificeFinding`, `CaptureHoldsFinding`, `RescueFinding` |
| `reasoning/runner.py` | analyses use `label_v2` |
| `facts/__init__.py` | `ExchangeFacts` and `PieceExchange` become public names, since reasoning may import only the public fact engine (package boundary) |
| `tools/label_bench/` (new) | the benchmark of LV-D §9 |

## 2. Implementation decisions and deviations

1. **The premise runs the other way (deviation from LV-D §6.1).**
   - **Why.** A hypothesis's premises are part of its id, and each must already be a SUPPORTED claim
     when the hypothesis is proposed (R0-D §8.1, `check_premises`). `piece_sacrifice_v1` cannot
     therefore rest on `capture_holds_v1`, whose search does not exist until `piece_sacrifice_v1`
     asks for it.
   - **Implemented flow.**
     - `piece_sacrifice_v1` decides LV-D §5 steps 1–4 from S and the exchange facts.
     - Once those hold, it asks once for the survey after the capture: `LineNeed(C, (x,), survey)`.
       It turns SUPPORTED when X exists. Its verdict rests on S and the facts only.
     - `capture_holds_v1` is then proposed on it: premise `EARLIER_POSITION`, `ANY_SEARCH`. It reads
       the search at X alone.
     - BRILLIANT's grounds are the two claims.
   - **What is kept.** The logic of LV-D is unchanged: the same five steps, the same thresholds, and
     the search at X never compared with S.
2. **`piece_sacrifice_v1`'s target is Lp's first ply** (P → C on S's line). C is then an ancestor
   of X, which `EARLIER_POSITION` checks, and the target still names S.
3. **Rounds.**
   - **Usual path:** exchange facts in round 0; static steps and the survey request in round 1;
     `capture_holds_v1` and the label in round 2 (fixpoint passes). That is two issuing rounds and
     three in all, within the default budget.
   - **A missing alternative child** first gets `LineNeed(P, (m_i,), NONE)` (LV-D review B1).
   - **An unadmitted survey** (no extra searches left) leaves the claim INCONCLUSIVE, with no
     BRILLIANT (test).
4. **INCONCLUSIVE reasons** must be those of R0-D §9.2 or `NOT_COMPUTED(…)`. LV-D's "`IN_CHECK`"
   is therefore `NOT_COMPUTED(IN_CHECK)`. Under `quality_v1`, a missing WDL at X is
   `NOT_COMPUTED(WDL_UNAVAILABLE)`.
5. **`capture_holds_v1` under `quality_v1`** reads the WDL of the search's rank 1, as the observer
   does. Under `quality_v2` it reads the score through the request's curve.
6. **The offer's tie-break and values** are computed without python-chess: square index
   `(rank − 1) · 8 + file`, `points_v1` values by piece type. Reasoning may not import python-chess
   (package boundary).
7. **R0-D §6.2's "catalogue v1 raises no line need" is amended:** `piece_sacrifice_v1` raises the
   capture survey and, if needed, alternative children. The boundary test of line needs was
   updated (§3.2).

## 3. Evidence

### 3.1 Tests
- **`tests/reasoning/test_labels_v2.py`, 14 tests.** It covers LV-D §10:
  - **FORCED:** also without a decided judgement.
  - **GREAT:** a quiet only move is a provisional GREAT; it is withheld in check, on a mate in one,
    on a rescue and on a recapture.
  - **`rescue_v1`:** REFUTED when the piece was not en prise, and when it stays en prise.
  - **The queen sacrifice:** BRILLIANT, with both claims, the premise `ANY_SEARCH`, `see_v1` in the
    scope, and two issuing rounds.
  - **The capture branch:** a lost position after the capture refutes it.
  - **`piece_sacrifice_v1` refuted:** a quiet line already winning, a trapped piece even with a
    capture, a piece left hanging by a quiet move.
  - **`piece_sacrifice_v1` INCONCLUSIVE:** without the survey budget, and in check without a
    capture.
  - **Not proposed:** far from best.
  - **`Label`:** a `label_v1` record stored with the old fields decodes with the defaults.
- **`tests/tools/test_label_bench.py`, 2 tests:** the static prefilter (a bishop sacrifice yes, a
  quiet move and an even trade no) and the summary.
- **Existing tests changed for the new contract:**
  - three scenarios on 1.Qe8+ Rxe8 2.Rxe8# now expect the provisional BRILLIANT, which precedes
    GREAT;
  - "`label_v1` never assigns BRILLIANT" now calls `label_v1` itself;
  - the registry order lists 24 templates;
  - "no line need in catalogue v1" became "line needs only for the capture survey".

| Suite | Result |
| --- | --- |
| `tests/reasoning`, `tests/tools`, `tests/test_package_boundaries.py`, `tests/facts/test_exchange.py` | 355 passed, 1 skipped (gated Stockfish) |

### 3.2 The label benchmark (LV-D §9; `tools/label_bench/reports/brilliant_p1.json`)
- **Data:** the 100 chess.com games of LV-D §2.2. The data file's SHA-256 is `1fa9f85e…6731`, and
  the file stays out of the repository.
- **Run:** the full reasoner on 498 plies, every brilliant ply and every static piece offer, at a
  median of 1.43 s per analysis (max 4.46 s).

| | brilliants found | false calls (per 1 000 other moves) |
| --- | --- | --- |
| all 100 games | **67** | **35 (4.70)** |
| even games | 37 / 50 | 15 (4.72) |
| odd games | 30 / 50 | 20 (4.68) |
| prototype of LV-D §2.2, for comparison | 63 | 28 (3.76) |

- **Where it differs from the prototype.** The implementation finds four more brilliants and makes
  seven more false calls. The main difference is saveability:
  - the implementation reads the offered piece's own `safe_moves` (LV-D review B2);
  - the prototype read an aggregate, which a capture elsewhere could lower.

  Per-piece saveability admits pieces that the aggregate wrongly called lost.
- **The 33 missed brilliants:**
  - 12 were not proposed: loss ≥ 100 at depth 12, or `E(Lp) < 1000`;
  - 19 failed a static step (offer, saveability, created or capture, or a winning non-offering
    line);
  - 2 failed the capture branch.
- **Stability.** The false-call rate is the same in both halves. As LV-D §2.2 says, these figures
  are exploratory, not acceptance evidence.

### 3.3 The Q3 owner games (`label_v2`, five games, `tools.calibrate_curve.acceptance --labels`)

| label | chess.com | ours | matched | ours only | chess.com only |
| --- | --- | --- | --- | --- | --- |
| GREAT | 7 | 2 | 2 | — | 5 (small margins, LV-D §2.3) |
| BRILLIANT | 3 | 4 | 2 (7.Ne4, 9.Nxd4) | 10.Nxe6, 20.Qxf3 | 18.Nh5 |
| MISS | 10 | 1 | 1 | — | 9 (MISS v2, LV-D §12) |

- **GREAT** behaves as LV-D projected: no extra GREAT.
- **BRILLIANT** finds the same two as the prototype, and adds one false call (20.Qxf3, in the
  bullet game) to 10.Nxe6. Both stay under the provisional rule. They are inputs to a later
  `brilliant_p2` amendment (LV-D §8), not changes made here.
