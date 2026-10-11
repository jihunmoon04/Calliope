# Reasoning — MV-D design: MISS v2 (a missed opportunity, by expected points)

Status: **rev. 1 — awaiting independent review**.
Date: 2026-10-11. Base: `main @ 896c698`. Contracts:
[`reasoning-r0-design.md`](reasoning-r0-design.md) rev. 10 (R0-D) §6.1 (R0-I1), §8.1, §11;
[`reasoning-label-v2-design.md`](reasoning-label-v2-design.md) (LV-D) §7, §8, §12, §15;
[`reasoning-q3-implementation.md`](reasoning-q3-implementation.md) (Q3) §4–§6.

`label_v2` keeps `label_v1`'s MISS (rule `miss_v1`, R0-D §11). It has three conditions:
- the opponent's previous move grades MISTAKE or BLUNDER;
- this move grades INACCURACY or worse;
- `better_move_v1` is SUPPORTED, and its best line mates or wins material.

On the owner's marked chess.com games it finds 2 of chess.com's 12 Misses (§2). LV-D §12 named
the cause: chess.com's Miss is "failing to capitalize on the opponent's mistake", and the
opportunity need not be material. MV-D replaces the rule with a provisional **`miss_p2`** that
reads expected points. Like BRILLIANT and GREAT, it is provisional and changed by amendment (LV-D
§8).

## 0. Decisions

| # | Decision |
| --- | --- |
| M1 | **The opportunity is measured in expected points, not in material.** The material condition (`better_move_v1` with a mate or a gain) is dropped from MISS. |
| M2 | **Two independent conditions, one per search.** The opponent's move lost at least `A` against rank 1 of S_G, its own basis. This move loses at least `B` against rank 1 of S, the target's basis. The two losses are never added, subtracted or compared, so R0-I1 holds: each is a conclusion of its own search, as `label_v1` already reads the previous grade. |
| M3 | **Provisional thresholds `A = 130`, `B = 160`** (1/2000 points; §2.2). The thresholds were chosen on the same 12 Misses they are measured on, so the figures are exploratory (as LV-D §2.2). |
| M4 | **A claim carries the target's side:** `missed_gain_v1` (COMPARISON, §4). The previous move's side is read from its judgement, as `label_v1` does. |
| M5 | **Order unchanged:** FORCED, BRILLIANT, GREAT, MISS (LV-D L5). A move losing at least `B` is never BRILLIANT (loss < 100) or GREAT (BEST), so the order changes nothing in practice. |
| M6 | **`better_move_v1` stays,** for explanation. It is no longer a MISS ground. When it is SUPPORTED on the target, the label lists it as a second ground. |

## 1. Scope
- **In scope:**
  - rule `miss_p2` in `label_v2`;
  - the claim `missed_gain_v1`;
  - tests;
  - the Q3 report's MISS column under `miss_p2`.
- **Out of scope:**
  - **Grades.** Grading stays frozen (Q3 §5).
  - **GREAT's redefinition** (LV-D §1). It is a separate packet.
  - **The engine profile.** It stays `d12_mpv5_v1` (Q3 §6.3).
  - **Rendering of MISS.** That is R3's.

## 2. Evidence (2026-10-11)

### 2.1 The 12 Misses
Six owner games with Game Review marks (Q3 §4, §6.1). Five are rapid (803–2603) and one is
bullet (2475 / 2674). The full reasoner ran on every ply: 315 plies with both judgements decided.

Losses are ours, under the shipped table. "prev" is the opponent's move just before; "cc prev" is
chess.com's mark on it.

| game | Miss | ours | loss | prev, ours | prev loss | cc prev | `better_move_v1` | `miss_v1` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1524 / 1526 | 7.Nbd2 | INACCURACY | 181 | EXCELLENT | 31 | `?` | REFUTED | — |
| 1524 / 1526 | 7…e6 | INACCURACY | 167 | INACCURACY | 181 | Miss | REFUTED | — |
| 1700 / 1724 | 9.Bxe7 | MISTAKE | 317 | MISTAKE | 294 | `?` | INCONCLUSIVE (`LINE_TOO_SHORT`) | — |
| 1700 / 1724 | 14…Ng4 | MISTAKE | 322 | MISTAKE | 322 | `?` | SUPPORTED | MISS |
| 2674 / 2475 (bullet) | 4…Nc6 | GOOD | 83 | INACCURACY | 138 | `?` | not proposed | — |
| 2674 / 2475 (bullet) | 16…Qc7 | MISTAKE | 340 | BLUNDER | 532 | `??` | SUPPORTED | MISS |
| 2037 / 2603 | 7…O-O | INACCURACY | 170 | MISTAKE | 216 | `?` | INCONCLUSIVE (`LINE_TOO_SHORT`) | — |
| 2037 / 2603 | 25.Bb3 | INACCURACY | 181 | INACCURACY | 132 | `?` | INCONCLUSIVE (`LINE_TOO_SHORT`) | — |
| 2037 / 2603 | 25…Qg6 | INACCURACY | 194 | INACCURACY | 181 | Miss | INCONCLUSIVE (`LINE_TOO_SHORT`) | — |
| 2037 / 2603 | 26.Nc2 | MISTAKE | 209 | INACCURACY | 194 | Miss | INCONCLUSIVE (`LINE_TOO_SHORT`) | — |
| 2037 / 2603 | 26…Bg5 | MISTAKE | 360 | MISTAKE | 209 | Miss | REFUTED | — |
| 2037 / 2603 | 27.Qd3 | BLUNDER | 408 | MISTAKE | 360 | Miss | REFUTED | — |

**What the table shows:**
- **The previous move.** Every Miss follows an opponent move that chess.com marked `?`, `??` or
  Miss. Five follow another Miss: chess.com chains them, each side missing in turn.
- **Why `miss_v1` misses ten.**
  - Six follow a previous move we grade INACCURACY or EXCELLENT, below `miss_v1`'s MISTAKE.
  - `better_move_v1` is REFUTED on four and INCONCLUSIVE on five; on 4…Nc6 it is not proposed.
    The best line wins no stable material in the window, or the played line's exchange is still
    open (`LINE_TOO_SHORT`), as on 9.Bxe7.
- **This move.** Eleven of the twelve lose at least 167. The twelfth, 4…Nc6 (83), is in the
  bullet game, where the table is flat (Q3 §4).

### 2.2 Thresholds
Rule: previous loss ≥ `A` and target loss ≥ `B`, on the 315 plies.

| `A` | `B` | Misses found | false calls | chess.com marks on the false calls |
| --- | --- | --- | --- | --- |
| 100 | 100 | 10 / 12 | 11 | `?!` 2, none 3, `?` 3, `??` 3 |
| 100 | 160 | 10 / 12 | 6 | `?` 3, `??` 3 |
| 130 | 130 | 10 / 12 | 5 | none 1, `?` 2, `??` 2 |
| **130** | **160** | **10 / 12** | **4** | **`?` 2, `??` 2** |
| 150 | 160 | 9 / 12 | 3 | `??` 2, `?` 1 |
| 200 | 200 | 5 / 12 | 1 | `??` 1 |
| `miss_v1` | | 2 / 12 | 0 | — |

- **Chosen `A = 130`, `B = 160`.** It is the smallest number of false calls that keeps 10 of the
  12.
- **The four false calls are all errors for chess.com too.** They are 12…O-O (`?`), 15.O-O
  (`??`), 17.Qe2 (`??`) and 11…Bh5 (`?`). Each is a bad move after the opponent's mistake. chess.com
  called it a Mistake or Blunder rather than a Miss, and what separates the two is not visible in
  six games.
  - Losses were tried as a ratio (this loss against the previous one); it does not separate them.
    It is also cross-search, since the two losses come from S_G and S, and R0-I1 forbids it.
- **The two not found:**
  - **7.Nbd2:** chess.com marks the previous move `?`, but we grade it EXCELLENT (31). This is a
    grading disagreement, out of scope.
  - **4…Nc6:** bullet, loss 83.
- **Exploratory.** Twelve Misses in six games decide no threshold. The Q3 monitor's next games are
  the independent evidence (§7).

## 3. The rule `miss_p2`

```text
MISS(target P → C), rule miss_p2 (provisional):
    previous judgement (G → P) DECIDED  ∧  loss_G ≥ A          (read from S_G, as label_v1)
  ∧ target judgement DECIDED            ∧  missed_gain_v1 SUPPORTED on the target
                                            (its verdict: loss ≥ B on S)
```

- **Parameters** (`A`, `B` in 1/2000 expected points): `A = 130`, `B = 160`.
- **No previous move** (the target is the game's first ply, or G is not in the tree): no MISS.
- **Grounds:** `missed_gain_v1`, then `better_move_v1` when it is SUPPORTED on the target.
- **`miss_v1`** stays in the code, as `label_v1` does, for analyses made with it.

## 4. The claim `missed_gain_v1` (COMPARISON)
"Rank 1 of S was better than the played move by at least `B`." It names the move the player
missed, so explanation has something to say beyond the grade.
- **Proposal.**
  - When: the target's judgement is DECIDED, its loss is at least `B`, and the previous judgement
    is DECIDED with a loss of at least `A`. The proposer reads both judgements from
    `ProposeContext.judgements`; the hypothesis rests on S only.
  - Context: S's rank-1 line at P. Target: `VerificationTarget(SPECIFIC_LINE, rank 1's segment
    from P, horizon 1)`, the same form as `piece_offer_v1` (LV-D §6.1). Its searches are `{S}`.
  - Origin: the judgement.
- **Verification.**
  - It re-reads the judgement on S under the request's grading (R0-I1).
  - SUPPORTED when `loss ≥ B` and rank 1 is not the played move; otherwise REFUTED.
  - It needs no extra search, so it is decided in round 0's fixpoint.
- **Scope.** `ProofScope(basis = ENGINE, at = rank 1's segment, quantifier = SPECIFIC_LINE,
  population = S's line, searches = (S,), depth / multipv of S)`. Policies: `("points_v1",
  grading.policy)`.
- **Finding.** `MissedGainFinding(best: SearchMoveRef (S, rank 1, ply 1), loss: int,
  opponent_loss: int)`.
  - `opponent_loss` is copied from the previous judgement for explanation only. Nothing compares
    it with `loss`.
- **Why the opponent's side is not a claim.** A claim about G → P would rest on S_G, so a premise
  from it would need a relation from the edge G → P to the target. Reading the previous judgement
  in the proposer and the label is what `label_v1` already does, and it needs no new R0-D
  relation.
- **Registry.** After `better_move_v1`.

## 5. `label_v2` changes
- MISS uses `miss_p2` (§3): `Label(MISS, …, rule = "miss_p2", provisional = True)`.
- LV-D §7's rule list gains `miss_p2`. `miss_v1` stays the rule of `label_v2` analyses made
  before this packet.
- LV-D §8 applies to `miss_p2` as to `brilliant_p2` and `great_p2`. Any change needs a new rule
  name and the monitor run before and after.

## 6. Test obligations
1. **`miss_p2` assigned, without material:** a scripted previous move losing ≥ 130, and a target
   losing ≥ 160 whose best line wins nothing. The label is MISS (`miss_p2`, provisional), with
   `missed_gain_v1` as its only ground.
2. **Boundaries:**
   - previous loss 129 with target loss 160: no MISS;
   - previous loss 130 with target loss 159: no MISS, and `missed_gain_v1` is not proposed;
   - both exactly at the threshold: MISS.
3. **Undecided judgements:** the previous judgement INCONCLUSIVE, or no previous move. No MISS.
4. **`better_move_v1` SUPPORTED on the target:** it is the second ground.
5. **Order:** a FORCED target is never MISS.
6. **9.Bxe7 (1700 game), scripted:** `better_move_v1` INCONCLUSIVE (`LINE_TOO_SHORT`) and MISS
   under `miss_p2`.
7. **Record:** `miss_p2` and `provisional` are encoded; old `miss_v1` labels decode unchanged.

## 7. Evidence on delivery
- **Q3 report.** The acceptance tool's label table gains `miss_p2`. The implementation record
  reports the six games under `miss_v1` and `miss_p2`: found, false calls, and chess.com's marks
  on the false calls.
- **Making it final** follows LV-D §8: games the rule was not tuned on, with MISS recall and
  precision reported.

## 8. Delivery

| Packet | Content | Gate |
| --- | --- | --- |
| MV-D (this) | `miss_p2`, `missed_gain_v1`, thresholds, tests | independent review READY |
| MV1 | implementation, tests, the Q3 MISS column | READY |

Amendments on implementation:
- R0-D §11: MISS under `label_v2` is `miss_p2`.
- LV-D §7 (rule list) and §12 (resolved by this packet).

## 9. Open questions
- **Miss or Mistake.** In four cases chess.com called a move a Mistake or Blunder rather than a
  Miss after the opponent's mistake. The difference may be how much is given back: back to equal,
  or beyond the position before the opponent's error. Measuring it means comparing S with S_G,
  which R0-I1 forbids. A within-S form would be needed, for example the mover's `E` after the move
  against a fixed level. It needs more games.
- **The bullet game.** The table is flat in bullet, so `B = 160` misses bullet Misses like
  4…Nc6. A time-class `B` waits for more bullet games.
