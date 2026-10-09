# Fact engine — packet F3-D: geometric patterns and `pattern_delta`

Status: **rev. 2 — independent F3-D review READY_WITH_CORRECTIONS applied** (design only).
Date: 2026-10-09. Base: branch `facts/f2-geometry` @ `10ead6e` (F2, PR #43, stacked). The
definitions here use only F2 records, whose shapes are fixed by F2-D rev. 2 and the F2 record.
Review: rev. 1 `7163429`, READY_WITH_CORRECTIONS (F3D-C1–C6, N1–N11); section 10 maps every
finding.

Parent design: [`fact-engine-a0-design.md`](fact-engine-a0-design.md) rev. 4 (sections 1, 5,
6.8, 6.10, 7.5, 9; amended by this packet in sections 6.8, 6.10 and 7.5). Siblings:
[`fact-engine-f2-design.md`](fact-engine-f2-design.md) (F2-D) and
[`fact-engine-f2-implementation.md`](fact-engine-f2-implementation.md) (F2 record).

## 0. Scope

This packet freezes the exact definitions, record shapes, dependencies and test obligations of:
- `patterns` (POSITION, DEFINED, `patterns_v1`): six geometric configurations;
- `pattern_delta` (EDGE, DEFINED, `pattern_delta_v1`): their changes across a move, plus the
  removal-of-defender geometry carried over from the roadmap (`DEFENCE_ENDED_UNDER_ATTACK`).

No engine work is involved (F4).

**What a pattern is.** A pattern asserts only that a geometric configuration holds in the
position (A0 §6.8). It never asserts that the configuration wins material, works, is a threat,
or is legal to exploit. Legality stays in `status`; consequences belong to later blocks that
read engine evidence.

**Legacy evidence** is the frozen MVP (tag `legacy-mvp-g0`), used only as evidence:

| Short name | Path |
| --- | --- |
| DET | `src/calliope/services/tactics/detector.py` (P6 `TacticalDetector`) |
| CAND | `src/calliope/domain/analysis/tactics.py` (`TacticalCandidateKind`) |
| P6 | `docs/legacy/mvp-implementation-plan.md` §10 |
| P8 | `docs/legacy/mvp-p8-bad-move-design.md` §12.2–§12.3 |

## 1. Legacy findings (by code reading of DET and CAND)

| # | Legacy behaviour | Where | Consequence here |
| --- | --- | --- | --- |
| L1 | `FORK` = one piece attacking ≥ 2 enemy pieces **with at least one relation new on this move**. A position configuration is gated by an edge condition, and the name implies a working tactic | DET:206–218 | `MULTI_TARGET_ATTACK` is a POSITION predicate with a neutral name; "new" is a `pattern_delta` fact |
| L2 | `DOUBLE_ATTACK` groups the new attacks of **different** actors onto different targets into one candidate; it is not one configuration | DET:220–226 | dropped; per-piece attacks are already in `pieces` and `delta.piece_attacks` |
| L3 | `DIRECT_ATTACK` per new attack duplicates the attack relation | DET:200–204 | not a pattern; it is `delta.piece_attacks.began` (F2) |
| L4 | `HANGING_PIECE` from `hanging_now` | DET:172–182 | replaced in F2 by `attacked_without_defender` and `legally_capturable_now` |
| L5 | `REMOVAL_OF_DEFENDER` only when the defender was **captured**; a defender that moved away or whose line was blocked is invisible, so P8 §12.2 had to define "removed its own defensive relation" separately | DET:262–289; P8 §12.2 | `DEFENCE_ENDED_UNDER_ATTACK` with an exact reason (§4) |
| L6 | `CHECK`, `CHECKMATE`, `FORCED_RESPONSE` | DET:142–168, 294–297 | not patterns: `move.gives_check`, `status.checkmate`, `status.legal_move_count = 1` |
| L7 | `ABSOLUTE_PIN` only when the pin is new on the move | DET:232–257 | the pin is `pieces.absolutely_pinned` (F2) and its change is `delta.pins` (F2); see §2.1 |
| L8 | No relative pins, skewers, discovery lines, sole defenders or back-rank geometry | CAND | new definitions here |

## 2. `patterns` (POSITION, DEFINED, `patterns_v1`; requires `pieces`, `squares`, `lines`)

### 2.1 Common rules

1. **Inputs.** `patterns` reads only the F2 records of the same position. It walks no board and
   recomputes no attack set (A0 §9: trusted records, no re-validation).
2. **Both colours.** Every predicate is recorded for both colours; the colour of a pattern is
   the colour of its actor (the slider, the attacker, the defender, the king).
3. **Participants** are F2 `Relation(square, piece_type, absolutely_pinned)` records, taken from
   the corresponding `pieces` entry. A pinned participant is kept and flagged, never dropped
   (F2-D §1.4).
4. **Value order** is `piece_order_v1` (K > Q > R > B = N > P, F2 `PIECE_ORDER_RANK`).
   "Above" and "below" are strict. Equal rank (B and N, or two pieces of one type) gives
   neither a relative pin nor a skewer. `patterns_v1` is defined over `piece_order_v1`; a new
   order means a new `patterns` version (F3D-N5).
5. **Side-independent.** No predicate reads who is to move; the same placement with the other
   side to move gives an equal record. This is what lets `pattern_delta` compare adjacent nodes
   (F3D-C5).
6. **Lines** are `lines` rays. Only the first two occupants of a ray matter here; the
   direction is the ray's direction, from the slider outward.
7. **Not here.** Absolute pins are F2 facts: `pieces.absolutely_pinned`, with changes in
   `delta.pins`. A0 §6.8 listed `ABSOLUTE_PIN` as a pattern; it leaves `patterns` (§6), as
   `UNDEFENDED_ATTACKED` and `ATTACKERS_EXCEED_DEFENDERS` did in F2-D §11. The ray case
   [enemy, enemy king] is the same set of pins (invariant §7.2).
8. **Canonical order:** each predicate's records by actor square, then by line direction, then
   by the remaining squares; participant lists in board order.

### 2.2 The ray partition

For every ray R of a slider S (colour C) with at least two occupants, let `a` = R's first
occupant and `b` = its second. Exactly one of these holds:

| `a` | `b` | Result |
| --- | --- | --- |
| enemy | enemy king | absolute pin of `a` (F2 `pieces`, not recorded here) |
| enemy | enemy, not king, **above** `a` | `RELATIVE_PIN_GEOMETRY(S, a, b)` |
| enemy | enemy, **below** `a` | `SKEWER_GEOMETRY(S, a, b)` |
| enemy | enemy, equal rank | nothing |
| own | enemy | `DISCOVERY_LINE(S, a, b)` |
| enemy | own | nothing (`b` is behind an x-ray; F2 `lines.xray`) |
| own | own | nothing (a battery, if both slide along R, is F2 `lines.batteries`) |

Among the recorded rows, `a` is a king only in `DISCOVERY_LINE` (a king can block its own
slider's line) and in `SKEWER_GEOMETRY` (an enemy king in front is above anything behind it);
`b` is a king only in the absolute-pin row and in `DISCOVERY_LINE`. Kings occur in the
"nothing" rows too, for example `8/8/8/8/R2k3B/8/8/7K b` (`a` enemy king, `b` own bishop)
(F3D-N1).

### 2.3 Predicates

| Predicate | Record | Definition |
| --- | --- | --- |
| `MULTI_TARGET_ATTACK` | `MultiTargetAttack(actor, targets)`; each target `Target(piece, order)` with `order` ∈ {`ABOVE`, `EQUAL`, `BELOW`} the target's rank against the actor's | a piece whose `pieces.attacks.enemy` holds **≥ 2** squares. Targets are those enemy pieces, kings included. Any actor type, pawns and kings included; for a king actor every target is `BELOW` (two kings are never adjacent). An empty en passant target square is not a piece and never a target |
| `RELATIVE_PIN_GEOMETRY` | `LinePattern(slider, line, front, back)` | §2.2: `a` and `b` enemy, `b` not a king, `b` strictly above `a` |
| `SKEWER_GEOMETRY` | `LinePattern(slider, line, front, back)` | §2.2: `a` and `b` enemy, `a` strictly above `b` |
| `DISCOVERY_LINE` | `LinePattern(slider, line, front, back)` with `front` the own blocker and `back` the enemy target | §2.2: `a` own, `b` enemy. The blocker may be any own piece, the king included, and also a piece that moves along the line (a pawn on a file); the target may be the king. Random games show about five per position; the start position has six (F3D-N4) |
| `SOLE_DEFENDER` | `SoleDefender(defender, defended)` | for colour C: for every non-king piece X of C with `attacker_count ≥ 1` and `defender_count = 1`, let D be its only defender. When one D is that only defender for **≥ 2** such pieces, `defended` lists them. Kings are excluded as defended pieces: a king is never captured, so its "defenders" are no defence relation. D may be a king or a pinned piece (flagged) |
| `BACK_RANK_GEOMETRY` | `BackRank(king, blockers, covered)` | the king of colour C stands on C's first rank (rank 1 for White, 8 for Black). Its **forward squares** are the squares of C's second rank on the king's file ± 1 (2 on a corner file, else 3). Each forward square is own-occupied (a *blocker*), or not own-occupied and attacked by an enemy piece per `squares` (*covered*), or neither (*free*). An enemy-occupied forward square is therefore covered exactly when another enemy piece defends it, and free otherwise. The predicate holds iff no forward square is free and at least one is a blocker |

Remarks:
- A forward square is free exactly when the king of the side to move could legally step there
  (checked on 34,650 forward squares by the review), so the predicate needs no legal input.
- `BACK_RANK_GEOMETRY` is purely geometric and the same for both sides to move. It says nothing
  about whether an enemy rook or queen can reach the first rank; consumers combine it with
  `lines`. The F2-D §6 note on squares behind a checked king does not reach a forward square,
  because every line through a first-rank king and a second-rank square continues off the board
  or along the first rank.
- `MULTI_TARGET_ATTACK` with a king target is a check by that actor (from the attacked side's
  view). The record keeps it; `status` says who is to move.
- `SOLE_DEFENDER` uses geometric defence (F2). Whether the defender can legally recapture is
  not part of it (`status`).

### 2.4 Record

```text
PatternsFacts
  multi_target_attacks: tuple[MultiTargetAttack, ...]
  relative_pins:        tuple[LinePattern, ...]
  skewers:              tuple[LinePattern, ...]
  discovery_lines:      tuple[LinePattern, ...]
  sole_defenders:       tuple[SoleDefender, ...]
  back_ranks:           tuple[BackRank, ...]          # at most one per colour

MultiTargetAttack(actor: Relation, targets: tuple[Target, ...])
Target(piece: Relation, order: Order)                  # Order: ABOVE | EQUAL | BELOW
LinePattern(slider: Relation, line: (df, dr), front: Relation, back: Relation)
SoleDefender(defender: Relation, defended: tuple[Relation, ...])
BackRank(king: Relation, blockers: tuple[Relation, ...], covered: tuple[str, ...])
```

## 3. Adversarial cases (fixtures for F3)

Every FEN below was checked against a prototype over F2 records and against an independent
board-walking implementation (§9). Each "Expected" is the **complete** `PatternsFacts`: every
list not mentioned is empty (F3D-C1).

| # | FEN | Expected |
| --- | --- | --- |
| A1 | `r3k3/2N5/8/8/8/8/8/4K3 b - - 0 1` | `MULTI_TARGET_ATTACK(c7 knight → a8 rook ABOVE, e8 king ABOVE)` |
| A2 | `4k3/8/8/2n1b3/3P4/8/8/4K3 w - - 0 1` | pawn d4 → c5 knight, e5 bishop, both ABOVE |
| A3 | `4k3/8/2r1qb2/8/3N4/8/1K6/8 w - - 0 1` | knight d4 is absolutely pinned (f6) and still `MULTI_TARGET_ATTACK` → c6, e6, with `actor.absolutely_pinned = true` |
| A4 | `4k3/8/2r1B3/8/3N4/8/8/4K3 w - - 0 1` | no `MULTI_TARGET_ATTACK` for d4: one enemy and one own target |
| A5 | `4k3/8/8/3q4/8/1n6/B7/4K3 w - - 0 1` | `RELATIVE_PIN_GEOMETRY(a2, (1,1), b3 knight, d5 queen)`; also `DISCOVERY_LINE(d5, (−1,−1), b3, a2)` for Black |
| A6 | `4k3/8/8/3b4/8/1n6/B7/4K3 w - - 0 1` | no relative pin or skewer from a2 (knight and bishop are equal rank); `DISCOVERY_LINE(d5, b3, a2)` remains |
| A7 | `8/8/8/8/R2k3q/8/8/1K6 b - - 0 1` | `SKEWER_GEOMETRY(a4, (1,0), d4 king, h4 queen)`; `DISCOVERY_LINE(h4, (−1,0), d4 king, a4)` for Black (king as blocker) |
| A8 | `4k3/8/8/8/R2q3r/8/8/4K3 w - - 0 1` | `SKEWER_GEOMETRY(a4, (1,0), d4 queen, h4 rook)`; `DISCOVERY_LINE(h4, (−1,0), d4 queen, a4)` for Black |
| A9 | `3qk3/8/8/8/3B4/8/8/3RK3 w - - 0 1` | `DISCOVERY_LINE(d1, (0,1), d4 bishop, d8 queen)` and, from Black, `RELATIVE_PIN_GEOMETRY(d8, (0,−1), d4 bishop, d1 rook)`: one ray pair, two patterns of opposite colours |
| A10 | `4k3/8/8/8/8/8/8/R2K3q w - - 0 1` | `DISCOVERY_LINE(a1, d1 king, h1 queen)` and `SKEWER_GEOMETRY(h1, d1 king, a1 rook)` |
| A11 | `4k3/8/3p4/2n1b3/8/8/8/2R1R2K b - - 0 1` | `SOLE_DEFENDER(d6 pawn: c5, e5)`; the e5 bishop is also absolutely pinned (e1), which is F2's |
| A12 | `4k3/q7/3p4/2n1b3/8/8/8/2R1R2K b - - 0 1` | no `SOLE_DEFENDER`: c5 has two defenders (d6, a7) |
| A13 | `6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1` | `BACK_RANK_GEOMETRY(g8: blockers f7 g7 h7, covered —)`; none for White (no blocker on the second rank) |
| A14 | `6k1/5pp1/7p/8/8/8/8/R5K1 w - - 0 1` | none for Black: h7 is free |
| A15 | `6k1/5p1p/8/8/8/8/1B6/R5K1 w - - 0 1` | `BACK_RANK_GEOMETRY(g8: blockers f7 h7, covered g7)` (the b2 bishop) |
| A16 | `8/5ppp/6k1/8/8/8/8/R5K1 w - - 0 1` | none: the black king is not on its first rank |
| A17 | `3r3k/3r4/8/3N4/3K4/8/8/7r w - - 0 1` (F2-D §2 pin fixture) | no relative pin or skewer: [d5 knight, d4 king] from d7 is the F2 absolute pin; `DISCOVERY_LINE(d8, (0,−1), d7 rook, d5 knight)` for Black, beside the F2 battery d7–d8 |

| A18 | `4k3/8/8/8/8/2b5/1N1N4/2K1r3 w - - 0 1` | `SOLE_DEFENDER(c1 king: b2, d2)` (a king defender) |
| A19 | `k7/8/8/8/8/8/PP6/K7 w - - 0 1` | `BACK_RANK_GEOMETRY(a1: blockers a2 b2)`: a corner king has two forward squares |
| A20 | `k5r1/8/8/8/8/8/5PnP/6K1 w - - 0 1` | `BACK_RANK_GEOMETRY(g1: blockers f2 h2, covered g2)`: the enemy knight on g2 is defended by g8 |
| A21 | `k7/8/8/8/8/8/5PnP/6K1 w - - 0 1` | no back-rank pattern: the undefended knight leaves g2 free |

Additional cases the F3 tests must include: a pawn attacking two pieces where one is the king;
a king as `MULTI_TARGET_ATTACK` actor; a pinned `SOLE_DEFENDER`; three sliders on one line
(only the first two occupants count); both colours' back ranks at once; promotion creating a
new slider's rays; a `MULTI_TARGET_ATTACK` pawn whose attack set holds an empty en passant
target square.

## 4. `pattern_delta` (EDGE, DEFINED, `pattern_delta_v1`; requires `patterns`, `pieces` at both ends and `delta` on this edge)

Pattern participants are mapped to `PieceId` through each end's piece map, as in `delta`. Only
these **id projections** are compared: a change of a participant's type, `order` or pinned
flag with the same ids is not a `pattern_delta` change (it is visible in `patterns` and F2
records). Example: `7k/8/8/1R2n3/8/8/1p6/7K b`, `b2b1q` keeps the b5 rook's target ids
{b.P.b2, b.N.e5}, so nothing is recorded, although the promoted target's `order` goes from
`BELOW` to `ABOVE` (F3D-C4).

| Component | Key / value | Change recorded |
| --- | --- | --- |
| `multi_target_attacks` | actor id → target ids | `TargetSetChange(piece, before, after)` when the target id set changed; `()` means "fewer than two targets"; a captured actor ends with `after = Absent(CAPTURED)`; a promoted actor continues under its id |
| `relative_pins` | (slider id, front id, back id) | `SetChange` began / ended |
| `skewers` | (slider id, front id, back id) | `SetChange` |
| `discovery_lines` | (slider id, blocker id, target id) | `SetChange` |
| `sole_defenders` | defender id → defended ids | `TargetSetChange(piece, before, after)` as for `multi_target_attacks` |
| `back_ranks` | king id → (blocker ids, covered squares) or `None` | `BackRankChange(king, before, after)` when it changed |
| `defences_ended_under_attack` | `DefenceEnded(defender, defended, reason)` | see below |

**`DEFENCE_ENDED_UNDER_ATTACK`** (the removal-of-defender geometry). For every
`(defender d, defended x)` in `delta.piece_defences.ended` such that x still exists at the
child, **x is not a king** (as in `SOLE_DEFENDER`, F3D-C2), and x has `attacker_count ≥ 1`
there, record one entry. It is a filtered view of `delta.piece_defences.ended` with a reason
added, not a second copy of it (F3D-N11). Whether x keeps other defenders is read from the
child's `pieces.defender_count` (F3D-N9). Its `reason` is the first that
applies, from the edge's identity step:

1. `DEFENDER_CAPTURED`: d is the captured piece;
2. `DEFENDER_MOVED`: d is the mover or the castling rook;
3. `DEFENDED_MOVED`: x is the mover or the castling rook;
4. `LINE_BLOCKED`: otherwise. Neither piece moved, so only a slider's line can have changed,
   and it can only have been blocked (a defence that begins is not an ending). The landing
   square of the mover or of the castling rook then lies strictly between d and x.

A captured d and a moved x always have different colours, so rules 1 and 3 never both apply;
the review's fuzz found no ended pair in which both pieces moved.

A defended piece that was captured is not listed (its relations end in `delta`, F2-D §7.1).
A defended piece that is no longer attacked is not listed (`delta.piece_defences` keeps the
plain ending).

| # | FEN, move | Expected |
| --- | --- | --- |
| D1 | `4k3/8/2n5/4b3/B7/8/8/4R1K1 w - - 0 1`, `a4c6` | (b.N.c6, b.B.e5, `DEFENDER_CAPTURED`) |
| D2 | `4k3/8/2n5/4b3/8/8/8/4R1K1 b - - 0 1`, `c6a5` | (b.N.c6, b.B.e5, `DEFENDER_MOVED`) |
| D3 | `3k4/8/2n5/4r3/8/8/8/4R1K1 b - - 0 1`, `e5e4` | (b.N.c6, b.R.e5, `DEFENDED_MOVED`) |
| D4 | `4k3/8/8/r3b3/1N6/8/8/4R1K1 w - - 0 1`, `b4d5` | (b.R.a5, b.B.e5, `LINE_BLOCKED`) |
| D5 | `4k3/8/8/8/8/8/5PPP/4K2R w K - 0 1`, `e1g1` | nothing: (w.R.h1, w.P.h2) ends, but h2 is not attacked |
| D6 | `4k3/8/3b4/8/8/8/7P/4K2R w K - 0 1`, `e1g1` | (w.R.h1, w.P.h2, `DEFENDER_MOVED`): the castling rook |
| D7 | `4k3/8/8/3pP3/4n3/8/8/4RK2 w - d6 0 1`, `e5d6` | (b.P.d5, b.N.e4, `DEFENDER_CAPTURED`): the en passant victim was the defender |
| D8 | `4k3/8/r5b1/3pP3/8/8/7K/6R1 w - d6 0 1`, `e5d6` | (b.R.a6, b.B.g6, `LINE_BLOCKED`): the en passant landing square blocks the rank |
| D9 | `2R5/1P1k4/8/8/8/8/8/K7 w - - 0 1`, `b7b8n` | (w.P.b7, w.R.c8, `DEFENDER_MOVED`): a promoting defender |
| D10 | `r3k3/8/8/8/8/8/8/2R1K3 w - - 0 1`, `c1c8` | nothing: (b.R.a8, b.K.e8) ends with the king in check, but kings are excluded |

**Record**

```text
PatternDeltaFacts
  multi_target_attacks:        tuple[TargetSetChange, ...]     # by piece id
  relative_pins:               SetChange[LineTriple]
  skewers:                     SetChange[LineTriple]
  discovery_lines:             SetChange[LineTriple]
  sole_defenders:              tuple[TargetSetChange, ...]     # by piece id
  back_ranks:                  tuple[BackRankChange, ...]      # by king id
  defences_ended_under_attack: tuple[DefenceEnded, ...]        # by (defender, defended)

LineTriple(slider: PieceId, front: PieceId, back: PieceId)     # front = blocker for discovery
TargetSetChange(piece: PieceId, before: tuple[PieceId, ...], after: tuple[PieceId, ...] | Absent)
BackRankChange(king: PieceId, before: BackRankIds | None, after: BackRankIds | None)
BackRankIds(blockers: tuple[PieceId, ...], covered: tuple[str, ...])
DefenceEnded(defender: PieceId, defended: PieceId, reason: DefenceEndReason)
DefenceEndReason: DEFENDER_CAPTURED | DEFENDER_MOVED | DEFENDED_MOVED | LINE_BLOCKED
```

`SetChange` is F2's (`began`, `ended`). Id tuples are sorted by `PieceId`, squares in board
order, and every list by its key ids, as in F2 `delta`.

Rules:
- At the root, `pattern_delta` reads `NotApplicable`, like every EDGE family.
- Only changes are recorded, as in `delta`.
- `pattern_delta` holds no side-dependent fact; it compares records of adjacent nodes, which is
  allowed because `patterns` is side-independent.
- Absolute pins are not repeated here (`delta.pins`).

## 5. Tiers, `requires` and cost

| Family | Scope | `requires` |
| --- | --- | --- |
| `patterns` | POSITION | `pieces`, `squares`, `lines` |
| `pattern_delta` | EDGE | `patterns`, `pieces`, `delta` |

- Both register after `same_side_delta`; registry order stays dependency order, and the F2
  scope table admits both (EDGE may require POSITION at both ends and EDGE on its edge).
  `pattern_delta` is the first EDGE family that requires another EDGE family (`delta`); the
  engine already resolves EDGE requirements on the same edge only.
- Requiring `pattern_delta` pulls in `delta`, and through it `pawns` and `king`, at both ends:
  about 0.7 ms per edge by the F2 record (F3D-N6).
- Both are in the default eager set (every registered family). `OpenRequest(families=(…))`
  can leave them out, and `ensure` computes them later, as for every F2 family.
- Engine-only nodes (F4) do not get them eagerly (A0 §7.5 tier).
- **Targets:** ≤ 0.3 ms per position for `patterns` and ≤ 0.3 ms per edge for
  `pattern_delta`. Unoptimized prototypes over F2 records measured 0.04–0.05 ms per position
  for `patterns` and 0.027 ms per edge for `pattern_delta` including
  `DEFENCE_ENDED_UNDER_ATTACK` (aarch64, 2 CPUs, about 2,400 positions from 30 random games).

## 6. Amendments to A0 made by this packet

- **§6.8:**
  - `ABSOLUTE_PIN` leaves `patterns`: it is `pieces.absolutely_pinned`, with changes in
    `delta.pins` (F2). The ray form "[pinned, king]" is the same set (F3-D §2.2).
  - The sketch table is replaced by F3-D §2.3, including `BACK_RANK_GEOMETRY`'s exact
    blocker / covered rule and `SOLE_DEFENDER`'s exclusion of kings as defended pieces.
- **§6.10:** `pattern_delta` is defined by F3-D §4 and adds `DEFENCE_ENDED_UNDER_ATTACK`.
- **§7.5:** the families that read `NOT_COMPUTED(TIER)` on engine-only nodes include
  `pattern_delta` (F3D-C6).

## 7. Test obligations (F3 implementation)

1. **Independent auditor extension.**
   - It recomputes every predicate from its own ray walking and attack sets (the F2
     `geometry_auditor` primitives), not from `pieces` / `lines` records.
   - It recomputes `pattern_delta` from its own pattern sets of parent and child, keyed by its
     own identity tracker, and the reasons of `DEFENCE_ENDED_UNDER_ATTACK` from python-chess
     move metadata.
   - Same corpus as F1 and F2: four root forms, branches, endgames.
2. **Invariants:**
   - side independence: the same placement with the other side to move gives an equal
     `patterns` record (§2.1.5);
   - a back-rank forward square is free exactly when the side to move's king has a legal move
     to it;
   - every `LINE_BLOCKED` has the mover's or castling rook's landing square strictly between
     the defender and the defended piece;
   - the ray partition (§2.2) covers every ray with ≥ 2 occupants exactly once;
   - [enemy, enemy king] rays equal the set of `pieces.absolutely_pinned`;
   - `MULTI_TARGET_ATTACK` targets equal `pieces.attacks.enemy` for every actor with ≥ 2;
   - `SOLE_DEFENDER` agrees with `pieces.defenders` and attacker counts;
   - `pattern_delta` applied to the parent's pattern sets gives the child's.
3. **Equivalences:** eager tree = minimal tree + `ensure(("patterns", "pattern_delta"))`;
   transpositions with different clocks give equal `patterns` records.
4. **Colour mirror:** mirrored positions give mirrored `patterns` and `pattern_delta`
   records, with line directions (df, −dr) (line patterns are not normalized like batteries).
5. **Fixtures:** A1–A21, D1–D10 and the additional cases of §3, plus `pattern_delta` cases for
   every component:
   - a `MULTI_TARGET_ATTACK` beginning, and its actor captured (`Absent(CAPTURED)`);
   - a promoted actor continuing under its id;
   - a sole defender captured;
   - a back-rank change on castling;
   - a skewer turning into a relative pin when the back piece promotes in place;
   - `NotApplicable` at the root.
6. **Mutation check:** field-level mutations of both families are caught by the auditor
   (the F2 method, booleans compared type-strictly).
7. **Cost:** both targets of §5, measured as in the F2 record.

## 8. Open questions for the review

| # | Question | Proposed answer |
| --- | --- | --- |
| Q1 | Should `MULTI_TARGET_ATTACK` count only undefended or higher-ranked targets? | No. Any filter is a policy of a later block; the `order` field and `pieces` give what it needs |
| Q2 | Should `SOLE_DEFENDER` with one defended piece be recorded? | No; one defended piece is `pieces.defender_count = 1`. The pattern is the sharing of one defender |
| Q3 | Should `BACK_RANK_GEOMETRY` require an enemy heavy piece with access to the first rank? | No for v1; that is a line fact the consumer reads from `lines` |
| Q4 | `DISCOVERY_LINE` when the blocker cannot move legally (pinned elsewhere, or no legal move) | Recorded; legality is `status`, and `blocker.absolutely_pinned` is in the record. Blockers that move along the line are included too |

The review agreed with all four proposed answers.

## 9. Prototype

A scratch prototype (not committed) computed §2.3 from F2 records. It confirmed A1–A17 and
measured the cost in §5. It also confirmed D1–D5 from F2's `delta.piece_defences` and child
`pieces`. The review re-checked every fixture with a second, board-walking implementation (0
mismatches against the record-based one on 2,430 random-game nodes; [enemy, enemy king] rays
equal `pieces.absolutely_pinned` on every node) and added A18–A21 and D6–D10.

**STOP** if F3:
- adds an evaluative name, or asserts that a pattern wins, works or threatens;
- reads anything but its declared `requires` records and, for `pattern_delta`, the edge's
  identity step and piece maps (F3D-C3);
- drops a pinned or king participant instead of flagging it;
- records a side-dependent fact;
- duplicates an F2 fact as a pattern (absolute pins, attacked-without-defender).

## 10. Review dispositions (rev. 1 `7163429`: READY_WITH_CORRECTIONS)

| Finding | Disposition |
| --- | --- |
| F3D-C1 A8 incomplete; "Expected" scope unstated | A8 completed; §3 states every "Expected" is the complete record |
| F3D-C2 kings listed as defended in `DEFENCE_ENDED_UNDER_ATTACK` | kings excluded (§4); fixture D10 |
| F3D-C3 STOP bullet contradicted §4 | reworded to "declared `requires` records, identity step and piece maps" |
| F3D-C4 `pattern_delta` record shape, order, comparison basis missing | record block, ordering and id-projection rule added (§4) |
| F3D-C5 test-obligation gaps | side independence, back-rank ⇔ legal-step, `LINE_BLOCKED` geometry, per-component `pattern_delta` fixtures, D6–D9, root, mirror of `pattern_delta`, A18–A21 (§3, §4, §7) |
| F3D-C6 A0 §7.5 and roadmap not amended | A0 §6.8, §6.10, §7.5 amended in this packet; roadmap updated |
| F3D-N1 king statements in §2.2 | limited to recorded rows, with a counter-example |
| F3D-N2 back-rank enemy-occupied squares; free ⇔ legal step | stated (§2.3) |
| F3D-N3 `order` for a king actor | stated: always `BELOW` |
| F3D-N4 `DISCOVERY_LINE` volume; along-the-line blockers | stated; no extra flag in v1 |
| F3D-N5 `patterns_v1` tied to `piece_order_v1` | stated (§2.1.4) |
| F3D-N6 `pattern_delta` pulls in `delta`; first EDGE-on-EDGE | stated (§5) |
| F3D-N7 `pattern_delta` cost figure | added (§5) |
| F3D-N8 circular `SOLE_DEFENDER` wording | reworded |
| F3D-N9 other defenders of x | stated: read the child's `defender_count` |
| F3D-N10 vocabulary | no change needed |
| F3D-N11 `DEFENCE_ENDED` is a filtered view, not a duplicate | stated (§4) |
