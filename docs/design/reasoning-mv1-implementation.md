# Reasoning — packet MV1 implementation: MISS v2 (`miss_p2`)

Status: **rev. 1 — independent review READY; notes applied (§4)**.
Date: 2026-10-11. Design: [`reasoning-miss-v2-design.md`](reasoning-miss-v2-design.md) rev. 2
(MV-D, re-review READY, #72). Base: `main @ eaf5290`.

## 1. Scope delivered

| Module | Content |
| --- | --- |
| `reasoning/labels.py` | `label_v2`'s MISS is **`miss_p2`** (provisional). The previous judgement is DECIDED with `loss ≥ MISS_OPPORTUNITY` (130), read from `judgements[1]`. `missed_gain_v1` is SUPPORTED on the target. Grounds: `missed_gain_v1`, then `better_move_v1` when it is SUPPORTED. `MISS_OPPORTUNITY` and `MISS_LOSS` are named constants, with the grading they were chosen under. `label_v1` is unchanged. |
| `reasoning/catalogue/comparison.py` | **`MissedGain`** (`missed_gain_v1`, COMPARISON, MV-D §4). It is proposed when the played move is not rank 1 and `loss ≥ MISS_LOSS` (160). Target `EXISTS_ALTERNATIVE(P, ENGINE_REPORTED(S))`. On verification it re-reads the judgement on S. Witness: rank 1's move. |
| `reasoning/catalogue/__init__.py` | registry: `missed_gain_v1` after `better_move_v1` (25 templates) |
| `reasoning/findings.py` | `MissedGainFinding(best: SearchMoveRef, loss)` |
| `tools/calibrate_curve/acceptance.py` | the label table counts our extra labels by chess.com's mark on the ply (MV-D review N2) |
| `docs/design` | R0-D §32 and LV-D §16 record the amendments (MV-D §8) |

## 2. Implementation decisions
1. **Where the constants live.** `MISS_OPPORTUNITY` and `MISS_LOSS` are in `labels.py`, beside the
   rule that names them. `comparison.py` imports `MISS_LOSS`, so the claim and the rule cannot
   drift apart. `labels.py` imports nothing from the catalogue, so there is no cycle.
2. **The claim reads S only.** The proposer does not look at `judgements[1]` (MV-D review B1). A
   target losing ≥ 160 after a harmless opponent move gets a SUPPORTED `missed_gain_v1` and no
   MISS (test).
3. **Rank 1 is never the played move** for a SUPPORTED claim. `EXISTS_ALTERNATIVE` rejects the
   subject's move as a witness (`satisfies()`). The verifier refutes that case first.
4. **Mate scores.** `loss` is the judgement's loss under the request's grading, so a missed mate
   (rank 1 mates, the played move does not) counts like any other loss. When both rank 1 and the
   played move mate for the same side, the loss is usually 0 and no claim is proposed. Mate
   distance is the grade's business (R0-D §7.2), not MISS's.

## 3. Evidence

### 3.1 Tests
- **`tests/reasoning/test_miss_v2.py`, 8 tests** (MV-D §6):
  - **MISS without material:** `missed_gain_v1` is the only ground. Its finding is `(best,
    loss)`, the witness is rank 1, and the quantifier is `EXISTS_ALTERNATIVE`.
  - **Thresholds:**
    - previous 129 / target 160: claim SUPPORTED, no MISS;
    - previous 130 / target 159: claim not proposed;
    - previous 0 / target 300: claim SUPPORTED, no MISS.
  - **No decided previous judgement:** an INCONCLUSIVE one, none at all, or the game's first ply.
    No MISS.
  - **A FORCED target** is never a MISS.
  - **Rank 1's PV left unattached** (a round-0 deadline cut, patched as in LV1): the claim and the
    MISS stand (review B2).
  - **An explicit scale** (`quality_v2`, `c = 1000`): MISS by the same thresholds (review N1).
  - **The 9.Bxe7 shape:** an open exchange makes `better_move_v1` INCONCLUSIVE
    (`LINE_TOO_SHORT`), and `miss_p2` still makes the MISS.
  - **A `miss_p2` label** round-trips through the canonical encoding.
- **`tests/tools/test_acceptance.py`:** extra labels counted by chess.com's mark (one new test,
  one assertion added).
- **Changed for the new contract:**
  - `test_miss_after_the_opponents_blunder`: grounds `(missed_gain_v1, better_move_v1)`, rule
    `miss_p2`;
  - the registry order lists 25 templates.
- **Mutation check:** with `MISS_OPPORTUNITY = 0`, the threshold test fails.

| Suite | Result |
| --- | --- |
| `tests/reasoning`, `tests/tools`, `tests/test_package_boundaries.py` | 370 passed, 1 skipped (gated Stockfish) |

### 3.2 The six marked owner games (Stockfish 19, depth 12, the shipped table; 321 plies)

**Counting.** 321 is every ply of the six games. MV-D §2 counts 315: the plies whose previous
judgement exists too, which leaves out each game's first ply (321 − 6). No Miss falls on a first
ply, so the two counts give the same Misses.

| rule | chess.com Misses found | extra MISS | chess.com's mark on the extras |
| --- | --- | --- | --- |
| `miss_v1` | 2 / 12 (14…Ng4, 16…Qc7) | 0 | — |
| **`miss_p2`** | **10 / 12** | **4** | `?` 2 (12…O-O, 11…Bh5), `??` 2 (15.O-O, 17.Qe2) |

- **The figures match MV-D §2.2's projection exactly.** The projection read the same judgements
  offline; this run is the full reasoner with the implemented rule.
- **Not found:**
  - 7.Nbd2: we grade the previous move EXCELLENT (31); chess.com marks it `?`.
  - 4…Nc6: bullet, loss 83.
- **The four extras are the Miss / Mistake confusion** that MV-D review N2 asks the monitor to
  keep apart. None falls on a move chess.com left unmarked.
- **Other labels are unchanged** by this packet: BRILLIANT 4 and GREAT 2, as in LV1's owner-game
  table (LV1 §3.3). The only other label is one FORCED.
- **Exploratory,** as MV-D §2.2 says: the thresholds were chosen on these twelve Misses.

## 4. Review (rev. 1 `a6065f6`, independent MV1 review: READY)

The review found MV-D rev. 2's contract met: the claim reads S only, the target is
`EXISTS_ALTERNATIVE`, the evidence keeps its sources apart, the label order holds, and `label_v1`
is kept. Its notes:

| Note | Disposition |
| --- | --- |
| `missed_gain_v1` also exists on bad moves after a harmless opponent move | By design (test: previous 0 / target 300). Recorded for R3-D rev. 3: explanation calls a move a missed opportunity only through the MISS label, never from `missed_gain_v1` alone. |
| 321 plies here, 315 in MV-D | Applied (§3.2): the counting basis is stated. |
| `MissedGainFinding.loss` is an expected-points loss only | Recorded for R3-D rev. 3, with MV-D review N3: no material gain or forcing tactic is named without another SUPPORTED claim that carries it. |
