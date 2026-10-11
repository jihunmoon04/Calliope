# Reasoning — packet LV1 implementation: `label_v2`

Status: **rev. 3 — LV1 review NOT_READY applied (§4); re-review READY_WITH_CORRECTIONS applied (§5)**.
Date: 2026-10-11. Design: [`reasoning-label-v2-design.md`](reasoning-label-v2-design.md) rev. 5
(LV-D), on [`fact-engine-f6-design.md`](fact-engine-f6-design.md) (F6, merged #69). Base:
`main @ 574b91e`.

## 1. Scope delivered

| Module | Content |
| --- | --- |
| `reasoning/labels.py` | **`label_v2`**, in order: FORCED (exactly one legal move, also without a decided judgement; rule `forced_v1`); BRILLIANT (grade BEST, EXCELLENT or GOOD, with a sound sacrifice: SUPPORTED `piece_offer_v1` and `capture_holds_v1` resting on it, read by `sound_sacrifice`; rule `brilliant_p2`, provisional, LV-D §15); GREAT (`label_v1`'s rule minus in check, recapture, mate in one and a `rescue_v1` proposed and not REFUTED; rule `great_p2`, provisional); MISS (`label_v1`'s rule; `miss_v1`). **`LabelKind.FORCED`.** **`Label.rule`** and **`Label.provisional`**, last, with defaults. `label_v1` is kept. |
| `reasoning/catalogue/exchange.py` (new) | `PieceOffer` (`piece_offer_v1`, LV-D §5 steps 1–4, §15.1), `CaptureHolds` (`capture_holds_v1`, §5 step 5, §6.2), `Rescue` (`rescue_v1`, §4.1); the parameters of `brilliant_p2` as named constants; a just-promoted piece is never offered (§15.3) |
| `reasoning/catalogue/__init__.py` | the three templates after `sacrifice_compensated_v1`: 24 templates |
| `reasoning/findings.py` | `PieceOfferFinding`, `CaptureHoldsFinding`, `RescueFinding` (`OfferFinding` is R2-D's `sacrifice_offer_v1`) |
| `reasoning/runner.py` | analyses use `label_v2` |
| `facts/__init__.py` | `ExchangeFacts` and `PieceExchange` become public names, since reasoning may import only the public fact engine (package boundary) |
| `tools/label_bench/` (new) | the benchmark of LV-D §9 |

## 2. Implementation decisions and deviations

1. **The premise runs the other way (deviation from LV-D §6.1).**
   - **Why.** A hypothesis's premises are part of its id, and each must already be a SUPPORTED claim
     when the hypothesis is proposed (R0-D §8.1, `check_premises`). `piece_offer_v1` cannot
     therefore rest on `capture_holds_v1`, whose search does not exist until `piece_offer_v1`
     asks for it.
   - **Implemented flow.**
     - `piece_offer_v1` decides LV-D §5 steps 1–4 from S and the exchange facts.
     - Once those hold, it asks once for the survey after the capture: `LineNeed(C, (x,), survey)`.
       It turns SUPPORTED when X exists. Its verdict rests on S and the facts only.
     - `capture_holds_v1` is then proposed on it: premise `EARLIER_POSITION`, `ANY_SEARCH`. It reads
       the search at X alone.
     - BRILLIANT's grounds are the two claims.
   - **Meaning (rev. 2, review B1).** Rev. 1 kept the name `piece_sacrifice_v1`, so a SUPPORTED
     claim read as "a sound sacrifice" while its capture branch could be REFUTED. The claim is now
     `piece_offer_v1`: a static offer, soundness unchecked. A sound sacrifice is the pair, read
     only through `labels.sound_sacrifice` (LV-D §15.1).
   - **What is kept.** The logic of LV-D is unchanged: the same five steps, the same thresholds, and
     the search at X never compared with S.
2. **`piece_offer_v1`'s target is Lp's first ply** (P → C on S's line). C is then an ancestor
   of X, which `EARLIER_POSITION` checks, and the target still names S.
3. **Rounds.**
   - **Usual path:** exchange facts in round 0; static steps and the survey request in round 1;
     `capture_holds_v1` and the label in round 2 (fixpoint passes). That is two issuing rounds and
     three in all, within the default budget.
   - **A missing alternative child** first gets `LineNeed(P, (m_i,), NONE)` (LV-D review B1).
     - Under a node-budget cut, that need is never admitted, since the room is spent. The claim
       ends `BUDGET`.
     - With room left, as after a round-0 deadline cut, it recovers in one more round (LV-D
       §15.4, test).
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
7. **R0-D §6.2's "catalogue v1 raises no line need" is amended:** `piece_offer_v1` raises the
   capture survey and, if needed, alternative children. The boundary test of line needs was
   updated (§3.2).

## 3. Evidence

### 3.1 Tests
- **`tests/reasoning/test_labels_v2.py`, 20 tests** (14 in rev. 1, six added for review B4). It
  covers LV-D §10:
  - **FORCED:** also without a decided judgement.
  - **GREAT:** a quiet only move is a provisional GREAT; it is withheld in check, on a mate in one,
    on a rescue and on a recapture.
  - **GREAT (rev. 2):** it is kept on a BEST capture that is not a recapture. It is withheld when
    `rescue_v1` is INCONCLUSIVE (`BUDGET`, `max_ensure_nodes = 0`; review B2).
  - **`rescue_v1`:** REFUTED when the piece was not en prise, and when it stays en prise.
  - **The queen sacrifice:** BRILLIANT, with both claims, the premise `ANY_SEARCH`, `see_v1` in the
    scope, and two issuing rounds.
  - **The capture branch:** a lost position after the capture refutes it. `piece_offer_v1` stays
    SUPPORTED, and `sound_sacrifice` is `None` (review B1).
  - **`piece_offer_v1` (rev. 2):**
    - in check, a capture passes step 2, with `created` unknown (`None`): BRILLIANT;
    - `E(Lp)` 999 is never proposed, and 1000 is;
    - a missing alternative child: `LineNeed(P, (h2h3,), NONE)`, then its exchange facts, then
      the survey. It is BRILLIANT under four rounds and `ROUND_LIMIT` under three. The round-0
      cut is made by a deadline cut of rank 2, patched for the test;
    - a just-promoted queen en prise is not offered (`brilliant_p2`; review B3).
  - **`piece_offer_v1` refuted:** a quiet line already winning, a trapped piece even with a
    capture, a piece left hanging by a quiet move.
  - **`piece_offer_v1` INCONCLUSIVE:** without the survey budget, and in check without a
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
| `tests/reasoning`, `tests/tools`, `tests/test_package_boundaries.py`, `tests/facts/test_exchange.py` | rev. 1: 355 passed, 1 skipped (gated Stockfish); rev. 2: 361 passed, 1 skipped |

The two rev. 2 fixes were checked against their tests. With either fix reverted, its test fails
(the undecided rescue; the promoted queen).

### 3.2 The label benchmark (LV-D §9; `tools/label_bench/reports/brilliant_p1.json`, rev. 2: `brilliant_p2.json`)
- **Data:** the 100 chess.com games of LV-D §2.2. The data file's SHA-256 is `1fa9f85e…6731`, and
  the file stays out of the repository.
- **Run:** the full reasoner on 498 plies, every brilliant ply and every static piece offer, at a
  median of 1.43 s per analysis (max 4.46 s).

| | brilliants found | false calls (per 1 000 other moves) |
| --- | --- | --- |
| `brilliant_p1` (rev. 1), all 100 games | **67** | **35 (4.70)** |
| `brilliant_p1`, even games | 37 / 50 | 15 (4.72) |
| `brilliant_p1`, odd games | 30 / 50 | 20 (4.68) |
| prototype of LV-D §2.2, for comparison | 63 | 28 (3.76) |
| **rev. 2, `brilliant_p2`** (LV-D §15.3) | **66** (even 37, odd 29) | **34 (4.56)** (even 14, odd 20) |

- **Rev. 2 against rev. 1.** It is the same data (SHA-256 `1fa9f85e…`), the same 498 plies, and
  a median of 1.40 s per analysis. Exactly two plies change, both promotions: 34…exf1=Q+ is no
  longer a false call, and 100…e1=Q+ (a chess.com brilliant) is no longer found. 42…c1=Q stays a
  false call. Its offered piece is the old queen on d1 (LV-D §15.3).

The figures below are for the current rule, `brilliant_p2`; `brilliant_p1`'s are in brackets.
- **Where it differs from the prototype.** The implementation finds three more brilliants [four]
  and makes six more false calls [seven]. The main difference is saveability:
  - the implementation reads the offered piece's own `safe_moves` (LV-D review B2);
  - the prototype read an aggregate, which a capture elsewhere could lower.

  Per-piece saveability admits pieces that the aggregate wrongly called lost.
- **The 34 missed brilliants [33]:**
  - 12 were not proposed: loss ≥ 100 at depth 12, or `E(Lp) < 1000`;
  - 20 failed a static step [19]: offer, saveability, created or capture, or a winning
    non-offering line. The one more is 100…e1=Q+;
  - 2 failed the capture branch.
- **Stability.** The false-call rate is the same in both halves. As LV-D §2.2 says, these figures
  are exploratory, not acceptance evidence.

### 3.3 The Q3 owner games (`label_v2`, five games, `tools.calibrate_curve.acceptance --labels`)

Run under `brilliant_p1` (rev. 1) and again under `brilliant_p2` (rev. 2). The two tables are
identical; the games have no promotion that the amendment touches.

| label | chess.com | ours | matched | ours only | chess.com only |
| --- | --- | --- | --- | --- | --- |
| GREAT | 7 | 2 | 2 | — | 5 (small margins, LV-D §2.3) |
| BRILLIANT | 3 | 4 | 2 (7.Ne4, 9.Nxd4) | 10.Nxe6, 20.Qxf3 | 18.Nh5 |
| MISS | 10 | 1 | 1 | — | 9 (MISS v2, LV-D §12) |

- **GREAT** behaves as LV-D projected: no extra GREAT.
- **BRILLIANT** finds the same two as the prototype, and adds one false call (20.Qxf3, in the
  bullet game) to 10.Nxe6. `brilliant_p2` (LV-D §15.3) changes neither: it only concerns
  promotions. Both stay under the provisional rule. They are inputs to a later amendment
  (`brilliant_p3`, LV-D §8), not changes made here.

## 4. Review dispositions (rev. 1 `1e6537d`, independent LV1 review: NOT_READY)

The review kept the structure: `label_v2` apart from the grade, and BRILLIANT from the SEE facts and
the extra search through claims. Each finding was checked against the code. B2 was reproduced by
running it, and B3 was found in the benchmark report.

| Finding | Disposition |
| --- | --- |
| B1 the sacrifice claim does not prove a sound sacrifice | Valid. Reversing the premise kept the name `piece_sacrifice_v1`, so it could be SUPPORTED while `capture_holds_v1` was REFUTED. Applied (LV-D §15.1): the claim is `piece_offer_v1`, a static offer whose soundness is unchecked. A sound sacrifice is the pair, read only by `labels.sound_sacrifice`. One combined claim was rejected: no R0-D premise relation fits a claim at P → C resting on one at X. |
| B2 GREAT on missing evidence | Valid. Reproduced with `max_ensure_nodes = 0`: `only_move_v1` was SUPPORTED, `rescue_v1` INCONCLUSIVE (`BUDGET`), and GREAT was assigned. Applied (LV-D §15.2): GREAT needs `rescue_v1` not proposed or REFUTED. Test. |
| B3 a promotion read as a piece sacrifice | Valid. Three promotions were called BRILLIANT on the benchmark, and two of them are not chess.com brilliants (84.c1=Q, 34…exf1=Q+). The owner chose to amend the rule. Applied as `brilliant_p2` (LV-D §15.3): a just-promoted piece is not offered. The benchmark was run before and after (§3.2): found 67 → 66, false calls 35 → 34. 84.c1=Q remains, since the piece it leaves en prise is the old queen. Test. |
| B4 LV-D §10 obligations not all tested | Valid. Six tests added (§3.1): the missing child and its recovery, in check through a capture, the undecided rescue, the `E(Lp)` boundary, a non-recapture BEST capture keeping GREAT, and the promotion. |

**Noted, unchanged.** A BRILLIANT left undecided, for example `piece_offer_v1` at `ROUND_LIMIT`,
does not withhold GREAT when GREAT's own rule holds. GREAT asserts no "no sacrifice", so the
undecided claim is not read as a negative. This is the reading the missing-child test shows under
three rounds.

## 5. Review dispositions (rev. 2 `99bdedf`, re-review: READY_WITH_CORRECTIONS)

The re-review found B1–B4 resolved and no new defect in the implementation. Its corrections are
about documents only.

| Finding | Disposition |
| --- | --- |
| §3.2 still gave rev. 1's missed count and prototype differences | Valid. The figures now refer to `brilliant_p2`: 34 missed, three more found and six more false calls than the prototype. `brilliant_p1`'s figures stay in brackets, and its table rows are marked. |
| §3.3 spoke of `brilliant_p2` as a future amendment | Valid. The five owner games were re-run under `brilliant_p2`, with identical labels. The text names the next amendment `brilliant_p3`. |
| LV-D's old name `piece_sacrifice_v1` is replaced only in §15 | Applied. LV-D now opens with a box listing §15's replacements, and §4, §5, §6.1, §6.2 and §10.4 point to §15. The original text stays as history. |
