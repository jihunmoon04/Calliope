# Reasoning — LV-D design: `label_v2` (FORCED, a narrower GREAT, a provisional BRILLIANT)

Status: **rev. 4 — independent review NOT_READY (B1–B3, C1–C3) applied (§13); awaiting re-review**.
Date: 2026-10-11. Base: `main @ 37f1b2a`. Contracts:
[`reasoning-r0-design.md`](reasoning-r0-design.md) rev. 10 (R0-D) §4 D4, §6.2, §11;
[`reasoning-r2-design.md`](reasoning-r2-design.md) rev. 11 (R2-D) §3.10, §5.2, E10. It needs the
`exchange` family of [`fact-engine-f6-design.md`](fact-engine-f6-design.md) (F6-D).

`label_v1` assigns GREAT and MISS (R0-D §11), and BRILLIANT was deferred to v2 (R2-D E10). Two
surveys on 2026-10-11 found the following (§2):
- GREAT fires on 4.5 % of all moves. 71 % of those are routine: check evasions, recaptures, mates
  in one, retreats.
- A forced move, one with a single legal move, gets no label at all.

`label_v2` makes three changes:
- it adds **FORCED**;
- it narrows **GREAT** by three plain board tests;
- it brings back **BRILLIANT** as a **provisional** rule, measured on 100 chess.com games where
  Game Review awarded a brilliant.

**The BRILLIANT and GREAT rules are not settled.** The owner decided this for BRILLIANT on
2026-10-11; rev. 3 extends it to GREAT on the evidence of §2.3. Their conditions and thresholds are
expected to change as evidence arrives (§8). Every label carries the rule that made it, and a label
made under a provisional rule is marked so.

## 0. Decisions

| # | Decision |
| --- | --- |
| L0 | **Direction** (owner, 2026-10-11): add FORCED; narrow GREAT; define BRILLIANT as a sound piece sacrifice, provisional and open to revision. MISS is unchanged in this packet. |
| L1 | **FORCED = exactly one legal move** (owner). The target's parent has `legal_move_count = 1`. It is a mechanical fact with no threshold. Since only one move exists, the grade is BEST. |
| L2 | **GREAT** (provisional from rev. 3, rule `great_p2`) is `label_v1`'s rule (grade BEST, `only_move_v1` SUPPORTED) minus four routine cases: the mover is in check at P; the move recaptures on the square where the previous move captured; the move mates in one; the move rescues a piece that was en prise (rev. 2, claim `rescue_v1`, §4). `only_move_v1` and its margin of 400 are unchanged. |
| L3 | **BRILLIANT** (provisional, rule `brilliant_p1`): a sound piece sacrifice that stays close to best, by the five conditions of §5. The owner's definition is "the piece may be captured, and the position is fine whether the opponent takes it or not". |
| L4 | **Claims carry the evidence.** BRILLIANT is assigned from the grade and a SUPPORTED `piece_sacrifice_v1` claim (§6), whose capture branch is the premise claim `capture_holds_v1` (§6.2). The rescue exclusion of GREAT reads a SUPPORTED `rescue_v1` claim (§4.1). Both follow R0-D D4: labels read grades and claims, and the grade never reads claims. The R2-D sacrifice claims (`sacrifice_offer_v1`, `sacrifice_sound_v1`, `sacrifice_compensated_v1`) stay as they are, for explanation. |
| L5 | **At most one label per move, in order:** FORCED, BRILLIANT, GREAT, MISS. |
| L6 | **Labels name their rule.** `Label` gains `rule` (for example `great_p2`, `brilliant_p1`) and `provisional`. `label_v2` is the build's label policy. |

## 1. Scope
- **In scope:**
  - FORCED;
  - the GREAT exclusions;
  - BRILLIANT with its claim `piece_sacrifice_v1`;
  - the `Label` fields;
  - the label benchmark tool (§9);
  - tests.
- **Out of scope:**
  - **MISS.** It finds none of chess.com's seven Misses so far (§2.3). It is its own packet, and
    §12 records what that packet must address.
  - **Redefining GREAT.** chess.com's Greats so far mostly have small margins (§2.3), so a rule
    nearer chess.com's "critical move" needs its own packet, together with MISS v2 (§12). This packet
    only removes routine moves from GREAT and marks the rule provisional.
  - **Rendering.** How a provisional BRILLIANT is worded, or whether it is shown, is R3's.

## 2. Evidence (2026-10-11)

### 2.1 Labels on real games (`label_v1`, shipped table, Stockfish 19, depth 12)
**Two chess.com rapid games** (813 / 801 with Game Review symbols, and 803 / 813), 109 plies:

| move | chess.com | `label_v1` | note |
| --- | --- | --- | --- |
| 27.Bxf7+ (bishop sacrifice, mate follows) | Brilliant | GREAT | no BRILLIANT in v1 |
| 28.Rxe8# | — | GREAT | mate in one |
| 12…Bg6, 14…Bh7 (bishop driven off by a pawn) | — (unannotated game) | GREAT | retreat of an attacked piece |
| 21…g6 | Miss | — | MISS blocked (§1) |

**Fifteen Lichess rapid games** (2026-08, average 1100–1500), 941 plies:
- GREAT 42 (4.5 % of moves, 11 % of BEST moves), MISS 19, single-legal-move plies 13.
- The GREATs break down as:
  - check evasions 15;
  - recaptures 11;
  - retreats of a statically hanging piece 3;
  - mate in one 1;
  - other 12.
- L2 removes 27 of them and leaves 15, about one per game.

### 2.2 The chess.com brilliant benchmark
- **Data:** [Chessigma's brilliant benchmark](https://www.chessigma.com/benchmarks/brilliant).
  - **Content:** 100 chess.com games (2020–2026; rapid, blitz, bullet; movers rated 445–3186,
    median 1089), each with the ply Game Review marked brilliant.
  - **Source and storage:** it is published as JSON by a third party. It is not committed, and the
    tool of §9 downloads it.
  - **Caveats:** it lists one brilliant per game, so some "false" calls below may be unlisted
    brilliants. The 100 were picked from 671 by an unstated method.
- **Prototype:** an SEE equal to F6-D's `see_v1`, round 0 under the shipped table, and one extra
  search after the opponent's capture.
  - **Scale:** 7 552 plies; 495 static candidates (piece offer ≥ 1), all 100 brilliants among
    them.
  - **Variants:** with `near-best` < 40 and the other §5 thresholds:

| variant | brilliants found | false calls (per 1 000 other moves) |
| --- | --- | --- |
| offer ≥ 1, any origin, capture branch A | 65 | 57 (7.65) |
| offer ≥ 1, saveable, A | 63 | 48 (6.44) |
| offer ≥ 1, newly exposed only, A | 40 | 20 (2.68) |
| offer ≥ 2, newly exposed only, A | 37 | 17 (2.28) |
| offer ≥ 1, saveable, **B** (taking must be the opponent's mistake) | 27 | 27 (3.62) |

- **What the variants show:**
  - **Capture branch.** "Fine whether taken or not" (A) finds more than twice what "taking is a
    mistake" (B) finds. chess.com awards sound accepted sacrifices.
  - **Offer size.** A net offer of 1 (a piece for two pawns, the exchange for a pawn) loses nothing
    against 2.
  - **Near-best.** Widening it from 40 to 100 lifts recall to 77 %. Under depth 12, chess.com's
    brilliants grade BEST 62, EXCELLENT 17, GOOD 16, INACCURACY 5.
  - **The main source of false calls** is a piece already hanging elsewhere and left there (42 of
    61). Requiring the move itself to expose the piece, or to capture, keeps 63 brilliants for 28
    false calls.
- **Chosen (`brilliant_p1`):** offer ≥ 1, saveable, created or a capture, near-best < 100,
  branch A.

  | half (games) | brilliants found | false calls (per 1 000) |
  | --- | --- | --- |
  | even | 36 / 50 | 12 (3.78) |
  | odd | 27 / 50 | 16 (3.74) |
  | all | **63 / 100** | **28 (3.76; 0.28 per game)** |

  The false-call rate is the same in both halves. Recall differs by 18 points between halves of
  50, which is within sampling noise at this size.
- **For comparison, the benchmark page reports:**
  - Chessigma: 82 %, and one unconfirmed badge per 20 games;
  - WintrChess: 45 %;
  - the other tools: one false badge every 3–6 games.

  Those are the publisher's own figures.
- **Limits:**
  - the thresholds were chosen on the same 100 games;
  - one search depth (12) was used;
  - this is chess.com's rule as measured on its output, not its specification.

### 2.3 chess.com games supplied by the owner (Q3 record §4, 2026-10-11)
Four games, exported with Game Review's NAGs (`$1` Great, `$3` Brilliant, `$9` Miss):
- rapid 803 / 813, rapid 1524 / 1526, rapid 2037 / 2603, and bullet 2674 / 2475;
- 194 plies in all.

chess.com's export carries no Best, Excellent or Good, so an absent `$1` means "not Great".

**GREAT** (chess.com 7):

| | matched | ours only | chess.com only |
| --- | --- | --- | --- |
| `label_v1` | 2 (33…Qe3+, 19.Nxf6+) | 7 | 5 |
| L2 (four exclusions) | 2 | 0 | 5 |

- **The seven extra GREATs** are all routine: four rescues of an attacked piece (14…Nd8, 12…Bg6,
  14…Bh7, 10.Nxe6) and three recaptures (13…axb5, 24.Nxa1, 12.Bxd6). Each has a margin of at
  least 400. L2 removes all of them and keeps both matches.
- **chess.com's five unmatched Greats** (5.cxd4, 14.Nh3, 17…Bd6, 22.Kh1, 28…Nc5) have margins
  of 45–153 over the second line, in the table's expected points.
  - 14.Nh3 is a rescue and 22.Kh1 a check evasion.
  - chess.com's Great therefore follows neither a large margin nor the move type. It looks
    nearer chess.com's own words, "critical to the outcome".
  - The bullet game adds a time-class effect: the bullet table is flat, which shrinks margins.
- **Hence rev. 3:** GREAT keeps L2 as a precision fix. It finds no false Great here, but it is
  marked provisional (`great_p2`), and its redefinition is left to a later packet (§1).
- **A caution for that packet.** The exclusions would remove true Greats such as 14.Nh3 and
  22.Kh1 if the margin were ever lowered.

**BRILLIANT** (chess.com 3; `brilliant_p1` with the prototype of §2.2, every ply of the four games
and of the design game):

| move | chess.com | `brilliant_p1` | reason |
| --- | --- | --- | --- |
| 27.Bxf7+ (design game) | Brilliant | BRILLIANT | — |
| 7.Ne4 | Brilliant | BRILLIANT | offer 3; loss 59 (GOOD); after 7…Nxe4 the mover's `E` is 1737 |
| 9.Nxd4 | Brilliant | BRILLIANT | offer 2; BEST; after 9…cxd4 the mover's `E` is 1757 |
| 18.Nh5 | Brilliant | — | leaves an already hanging rook (§5 step 2, "created or a capture") |
| 10.Nxe6 | — | BRILLIANT (false) | a capture that leaves an already hanging rook |

- **Result:** 3 of 4 found, 1 false call in about 250 plies.
- **What it supports.** 7.Ne4 and 27.Bxf7+ need near-best < 100 and branch A (a poisoned piece
  counts). 18.Nh5 and 10.Nxe6 are the two sides of the step-2 trade-off measured on the benchmark,
  where the excluded kind made 42 of 61 false calls.

**MISS.** chess.com 10, `label_v1` 1 (16…Qc7). See §12.

## 3. FORCED (L1)

```text
FORCED(target P → C):  status(P).legal_move_count = 1
```

FORCED needs no claim: it reads a RULE fact. Its grounds are empty, and its evidence is the
status fact. R0-D §11 is amended: a label without claim grounds is allowed when its condition is a
RULE fact.

**Without a decided judgement (review C2).** FORCED needs no grade. It is assigned even when the
target's judgement is INCONCLUSIVE, for example when the basis search failed. `label_v1` returned
early on such judgements; `label_v2` checks FORCED first, and returns early only after it.

## 4. GREAT (L2)

```text
GREAT(target):  grade = BEST
                ∧ only_move_v1 SUPPORTED                       (as label_v1)
                ∧ ¬ status(P).in_check
                ∧ ¬ recapture(G → P, P → C)
                ∧ ¬ move(P → C).gives_mate

recapture: the previous move captured on square s (move(G → P).events) and the target captures on s
```

    ∧ ¬ rescue_v1 SUPPORTED                                    (rev. 2, §4.1)

The first three are RULE facts that already exist (`status`, `move`). Without a previous move,
there is no recapture.

### 4.1 The claim `rescue_v1` (FUNCTION)
"The move saves a piece that was en prise." It reads the `exchange` facts (F6-D) at P and C.

```text
rescue(P → C):  the moved piece p is not a king
                ∧ exposure_P(p at its from-square) ≥ 1          (hypothetical: the mover is to move)
                ∧ exposure_C(p at its to-square) = 0            (real)
```

- **Proposal.**
  - When: for a target graded BEST whose moved piece has an attacker at P (`pieces` facts,
    already there).
  - Context: the edge. Target: the specific line Lp, horizon 1.
- **Verification.**
  - It needs `FamilyNeed(P, "exchange")` and `FamilyNeed(C, "exchange")`, then decides
    statically.
  - When P is in check, the exposure at P is `NotApplicable`, and the claim is REFUTED. A check
    evasion is already excluded from GREAT.
- **Explanation.** The claim is also a function the explanation can use: "saves the bishop".
- **Registry.** It follows `piece_sacrifice_v1` in the registry order.

**What it does not cover.** A rescue that is also deep, where the only safe square holds and every
other square loses to a tactic, would lose its GREAT. Whether chess.com calls such moves Great is
not known yet. It is measured as owner games arrive.

## 5. BRILLIANT (L3, provisional rule `brilliant_p1`)

Notation:
- `exposure_X(p)` is `PieceExchange.gain` at node X (F6-D);
- `captured(m)` is the `points_v1` value taken by `m`;
- `E` is expected points from the mover's view, under the request's grading.

1. **A piece is offered.** At C, the mover's non-king, non-pawn pieces are not to move, so their
   exposures are real. For each such piece, `offer = exposure_C(p) − captured(P → C)`.
   - The offered piece is the one with the largest offer, the lower square index on a tie.
   - The rule requires `offer ≥ 1` (owner: a net loss; measured: 1, §2.2).
2. **The loss was a choice, and this move made it.** `p` at P means the offered piece's record
   at P: its from-square if it moved, otherwise its own square (rev. 4).
   - **Saveable (review B2):** `safe_moves_P(p)` is not empty (F6-D §2.3). Some legal move would
     have kept this very piece unexposed. A piece that was lost anyway is no sacrifice (R0-D
     review 2 B2). The material of other pieces does not enter: rev. 1's aggregate let a capture
     elsewhere make a lost piece look saveable.
   - **Created or a capture:** either the piece's exposure grew with this move,
     `exposure_P(p) < exposure_C(p)`, or this move captures.
   - **In check (review B3).** When P is in check, `exposure_P(p)` is `NotApplicable("IN_CHECK")`,
     and "created" cannot be established.
     - The step then passes only through "a capture".
     - Otherwise the claim is INCONCLUSIVE (`IN_CHECK`), and no BRILLIANT is assigned.
     - An unknown exposure is never read as 0.
3. **Close to best and not bad.** The move's loss is under 100, so its grade is BEST, EXCELLENT
   or GOOD. Also `E(Lp) ≥ 1000`.
4. **Not already completely winning.** Every line of S whose move offers less than 1 (step 1,
   applied to that line's child) has `E < 1700`. Without such a line, the condition holds.
5. **Fine if taken (branch A).**
   - Let `x` be `first_capture` of the offered piece at C: the least valuable legal capture.
   - At X = C·x, a survey search must show `E ≥ 1000` for the mover at rank 1.
   - This is the premise claim `capture_holds_v1` (§6.2), not a number read by
     `piece_sacrifice_v1`.
   - The decline branch is step 3: the position after the move.

**Not compared across searches.** `piece_sacrifice_v1` reads S only (steps 3–4) and the exchange
facts. It uses `capture_holds_v1` through its conclusion (`ANY_SEARCH`, R0-D §8.1.2), never its
numbers, so the search at X and S are never compared (R0-I1). This is also why the capture branch
must be a claim of its own. A verdict may rest only on searches its target names (R2a §2.14), and
S's line names S, not the search at X.

**Parameters of `brilliant_p1`:**

| parameter | value |
| --- | --- |
| offer | ≥ 1 point |
| near-best | loss < 100 |
| not bad | `E ≥ 1000` |
| completely winning otherwise | non-offering line `E ≥ 1700` |
| capture branch | `E ≥ 1000` |

## 6. The claims (review C1)

### 6.1 `piece_sacrifice_v1` (FUNCTION)
- **Proposal.**
  - When: the target's judgement is DECIDED, its loss is under 100, `E(Lp) ≥ 1000`, and P has at
    least two legal moves.
  - Origin: the judgement.
- **Target.** `VerificationTarget(SPECIFIC_LINE, Lp's segment from P, horizon 1)`. It is S's line
  of the played move, so the hypothesis's searches are `{S}`.
- **Premise.** `capture_holds_v1` (§6.2).
  - **Uses:** `PremiseUse(requires = ScopeRequirement(ENGINE, ((EXISTS_RESPONSE, ENGINE_RANKED),)),
    relation, search = ANY_SEARCH)`.
  - **Relation:** `SAME_LINE` when `x` is Lp's second ply, otherwise `ALTERNATIVE_OF` (a reply at C
    beside Lp's).
- **Verification, in rounds** (R0-D §6.3):
  1. **Round r** (first verification). It needs `FamilyNeed(P, "exchange")`, `FamilyNeed(C,
     "exchange")` and `FamilyNeed(C_i, "exchange")` for the child `C_i` of every other line of S
     (step 4).
     - **Missing children (review B1).** S's line children normally exist: round 0 extends S's
       lines to `pv_plies` and ensures their nodes. A `C_i` cut by the node budget does not exist,
       and `FamilyNeed` cannot create it (`ensure` refuses unknown nodes). For it, the round raises
       `LineNeed(P, (m_i,), NONE)` instead, and `FamilyNeed(C_i, "exchange")` follows in the next
       round.
  2. **Round r + 1.** The static steps 1, 2 and 4 are computed. If one fails, the claim is REFUTED
     with that step as its finding, or INCONCLUSIVE (`IN_CHECK`, step 2). If all hold, it needs
     `LineNeed(C, (x,), survey)`: one extra search, which creates X and its search.
  3. **Round r + 2.** `capture_holds_v1` is proposed and verified (§6.2). `piece_sacrifice_v1` is
     SUPPORTED if its premise is SUPPORTED, and REFUTED if the premise is REFUTED.
- **Budget.**
  - With the defaults (three rounds, four extra searches, 64 ensure nodes), the usual path ends in
    the third round, at a cost of one search and at most six exchange records.
  - A missing `C_i` adds a round. Under the default three rounds the claim is then INCONCLUSIVE
    (`ROUND_LIMIT`), and so is any exhausted budget (`BUDGET`). No BRILLIANT is assigned then.
  - The benchmark of §9 reports how often that happens.
- **Scope.**
  - `ProofScope(basis = ENGINE, at = Lp's segment, quantifier = SPECIFIC_LINE, population = S's
    line, searches = (S,), depth / multipv of S)`.
  - Policies: `("points_v1", grading.policy, "see_v1")`.
  - The exchange facts enter as evidence (`fact_ref` to the `exchange` records at P, C and each
    `C_i`), and the premise enters as a premise.
- **Findings.** A `SacrificeFinding` records:
  - the offered piece (`PieceId`, square) and `offer`;
  - `created` (or `UNKNOWN` in check) and `capture`;
  - `x`;
  - the non-offering line used in step 4 and its `E`.
- **Registry.** The template follows `sacrifice_compensated_v1` (R2-D §6).

### 6.2 `capture_holds_v1` (CONSEQUENCE)
"After the opponent takes the offered piece with `x`, the mover still holds at least half a point."
- **Proposal.**
  - When: `piece_sacrifice_v1` is pending (`ProposeContext.pending`) and the view holds X = C·x
    with a survey search.
  - Target: `VerificationTarget(EXISTS_RESPONSE, X, ENGINE_RANKED(search at X))`. The
    hypothesis's searches are `{search at X}`.
  - Origin: the pending `piece_sacrifice_v1`.
- **Verification.**
  - Rank 1 of the search at X, scored under the request's grading from the mover's view (the side
    to move at X), has `E ≥ 1000`. It is then SUPPORTED, with rank 1 as its witness; otherwise
    REFUTED.
  - The search must be an unrestricted survey; otherwise the verdict is INCONCLUSIVE
    (`SCOPE_SHORT`), as for `only_move_v1`.
- **Scope.** `ProofScope(basis = ENGINE, at = X, quantifier = EXISTS_RESPONSE, population =
  ENGINE_RANKED(X), witnesses = (rank 1,), searches = (X,))`.
  - Policies: `("points_v1", grading.policy)`.
- **Explanation.** The claim is also usable there: "if Black takes, White still …". It does not
  record whether the capture is the opponent's mistake. That would compare the search at X with C's
  search, which is cross-search.
- **Registry.** It follows `piece_sacrifice_v1`.

## 7. `label_v2` and the `Label` record

```text
Label(kind: FORCED | BRILLIANT | GREAT | MISS, subject, grounds, policy: "label_v2",
      rule: str = "",            # "forced_v1", "brilliant_p1", "great_p2", "miss_v1"
      provisional: bool = False) # True under a p-rule (BRILLIANT, GREAT)
```

**Compatibility (review C3).**
- The two fields come last, with defaults. A `label_v1` record has no such fields. The canonical
  decoder reads a record by field name when the saved field list differs from the current one
  (F5-D), and the defaults fill the rest.
- `rule = ""` means "before `label_v2`".
- A test decodes a `label_v1` record encoded with the old field list.

- **Kinds.** `LabelKind` gains FORCED.
- **Policy.** `label_v1` stays in the code, as the policy of analyses made with it. Runs use
  `label_v2`.
- **Graph.** The label is a graph node with edges to its grounds, as before.

## 8. Changing the provisional rule

BRILLIANT (`brilliant_p1`) and GREAT (`great_p2`) are provisional until chess.com's own judgements
on games outside this evidence confirm them: Q3, or a larger labelled set.
- **Changing a threshold or condition.**
  - It needs an amendment section here, with the benchmark run of §9 before and after the
    change.
  - It needs a new rule name (`brilliant_p2`, `great_p3`, …). Labels already made keep their rule.
  - It does not need a new design packet, but the amendment is reviewed like an implementation
    record.
- **Making it final.** That is a design decision (a `brilliant_v1` rule, `provisional = false`).
  It needs Q3-type evidence and an independent review.

## 9. The label benchmark (`tools/label_bench/`)

An operator tool, outside `src/`.
- **Data.** It downloads the benchmark JSON (§2.2) into a cache, never into the repository, and
  records the file's SHA-256 in its report.
- **Runs.** For each game, it runs the full reasoner on the plies that pass step 1 statically (the
  `exchange` facts) and on every brilliant ply.
- **Report.**
  - Recall and false calls per 1 000 moves.
  - The same split by game halves.
  - The step that rejected each missed brilliant.
  - The rule name and the build identity.

## 10. Test obligations
1. **FORCED:**
   - a single legal move gives FORCED (no grounds), also when the judgement is INCONCLUSIVE;
   - two legal moves never give it.
2. **GREAT:**
   - `label_v1`'s GREAT test still passes on a quiet only move;
   - it is withheld in check, on a recapture, on a mate in one, and on a rescue (12…Bg6 of the
     owner game);
   - it is kept on a capture that is not a recapture.
3. **`rescue_v1`:**
   - SUPPORTED on a retreat from a pawn attack;
   - REFUTED when the piece was not en prise, when it remains en prise at C, and in check.
4. **`piece_sacrifice_v1` with `capture_holds_v1`, on scripted positions:**
   - SUPPORTED on 27.Bxf7+ of the design game and on 7.Ne4 of the owner game;
   - the three rounds: exchange facts; static steps then the capture search; the premise;
   - a missing alternative child: `LineNeed(NONE)`, then its exchange facts; INCONCLUSIVE
     (`ROUND_LIMIT`) under three rounds;
   - in check: SUPPORTED through a capture, INCONCLUSIVE (`IN_CHECK`) otherwise;
   - saveability per piece: REFUTED when the offered piece had no safe move, even if another
     move captured something;
   - REFUTED at each step: no offer; an unsavable piece (a trapped piece's last move); a piece
     already hanging and left, by a non-capture; loss ≥ 100; `E(Lp) < 1000`; a non-offering line
     ≥ 1700; `E` at X < 1000;
   - INCONCLUSIVE when the search budget is 0.
5. **Order and labels:**
   - FORCED before BRILLIANT before GREAT before MISS;
   - `rule` and `provisional` are encoded;
   - a `label_v1` record encoded with the old field list decodes, with the defaults.
6. **Benchmark** (gated): the tool's report on the benchmark reproduces §2.2 within the noise of
   engine timing (same depth). Its numbers go in the LV1 record.

## 11. Delivery

| Packet | Content | Gate |
| --- | --- | --- |
| F6-D, F6 | the `exchange` family | READY |
| LV-D (this) | `label_v2`, `piece_sacrifice_v1`, the provisional BRILLIANT, the benchmark tool | independent review READY |
| LV1 | the implementation, the tool, the benchmark record | READY |

Amendments on implementation:
- R0-D §11: FORCED, the order, a RULE-fact label without grounds, `rule` and `provisional`.
- R2-D §5.2 and §6: the GREAT exclusions, the new template.
- R2-D E10: BRILLIANT returns, provisionally.

## 12. MISS: what its own packet must address

`label_v1`'s MISS (R0-D §11) has three conditions:
- the opponent's previous move graded MISTAKE or BLUNDER;
- this move grades INACCURACY or worse;
- `better_move_v1` SUPPORTED with a best line that mates or wins material.

On chess.com's seven Misses so far (21…g6 of the design game; 7…O-O and 25.Bb3 to 27.Qd3 of the
2000s game), it finds none:
- Four of them follow an opponent move graded INACCURACY or better under the table, for example
  24…h6 (132) before 25.Bb3.
- Where the previous move was a MISTAKE (7.h3, 216, before 7…O-O), `better_move_v1` is REFUTED:
  the best line wins no material.

chess.com defines Miss as failing to capitalize on the opponent's mistake. The opportunity can be
positional. A MISS v2 packet should define the opportunity by expected points instead of the
previous move's grade and material. One direction to measure: rank 1 at P is well above the
position before the opponent's move, and the played move gives most of that back. Every
threshold would come from the Q3 games. This packet leaves MISS unchanged.

## 13. Review dispositions (rev. 1 `6a7406f`, independent review: NOT_READY)

The review kept the direction:
- FORCED as a RULE fact;
- GREAT without routine replies;
- BRILLIANT as a versioned provisional rule;
- the capture branch checked by its own search.

Each finding was checked against the code (`engine.py`, `controller.py`, `hypotheses.py`, R2a
§2.14).

| Finding | Disposition |
| --- | --- |
| B1 alternatives' child nodes may not exist, and `FamilyNeed` cannot create them | Valid: `ensure` refuses unknown nodes. Children normally exist, since round 0 extends S's lines, but a node budget can cut them. Applied (§6.1): a missing `C_i` gets `LineNeed(P, (m_i,), NONE)` first and its exchange facts next round. The extra round, the budget and INCONCLUSIVE (`ROUND_LIMIT` / `BUDGET`) are defined. |
| B2 the aggregate exposure does not show that the offered piece could be saved | Valid: rev. 1's prototype had the same flaw. Applied with F6-D rev. 2: saveability is `safe_moves_P(p) ≠ ∅` for the offered piece itself (§5 step 2). The LV1 benchmark re-measures §2.2 with it, so its numbers may move. |
| B3 an exposure unknown in check was read as 0 | Valid. Applied (§5 step 2): in check, "created" is unknown. The step passes only through a capture, otherwise INCONCLUSIVE (`IN_CHECK`). |
| C1 target and scope undefined | Applied (§6). Checking it found one more constraint: a verdict may rest only on searches its target names (R2a §2.14). The capture branch is therefore the premise claim `capture_holds_v1` on the search at X, used through its conclusion only (`ANY_SEARCH`). `piece_sacrifice_v1`'s target is S's line. Targets, scopes, rounds and findings are fixed. |
| C2 FORCED when the judgement is not DECIDED | Applied (§3): FORCED needs no grade and is checked first. |
| C3 decoding older labels with the new fields | Applied (§7): the fields come last with defaults, decoding goes by field name, and a test covers it. |
| N1 thresholds chosen and measured on the same 100 games | Recorded (§2.2, §8): the rule is provisional. The Q3 monitor's independent games so far find 3 of 4 chess.com brilliants with one false call (§2.3). |
| Integration N1 both PRs edit `docs/design/README.md` | They touch different rows, under F5 and under Q2. The second merge is re-checked against the first. |
