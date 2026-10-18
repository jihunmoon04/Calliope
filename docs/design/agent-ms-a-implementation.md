# Agent MS-a — the reasoning layer's part of MS-D

Status: **rev. 2 — for re-review**: review NOT_READY (B1–B3; N1) applied, §5. Date: 2026-10-18. Base: `main @ befbb4a` (MS-D rev. 3
merged). Design: [`agent-ms-design.md`](agent-ms-design.md) §2–§5 (R1–R4). No agent change: the
digest, `board` and the guide are MS-b's and MS-c's.

## 1. What was built

| MS-D | Where |
| --- | --- |
| R1 §2 a mechanism's reads at once | `reasoning/catalogue/mechanisms.py`: `_Mechanism.verify` scans as before; at its first step missing a record its `needs` are that step's missing `reads` (today's request) and `_batch` asks **ahead** for the next steps' (`Verdict.prefetch`), `BATCH_NODES = 4` steps in all; `Fork`, `Pin`, `Skewer`, `Discovery` `version = "2"`. `reasoning/verification.py`: `Verdict.prefetch` (NEEDS_EVIDENCE only). `reasoning/runner.py`: every open verdict's `needs` are admitted by `need_key` as before; then the prefetch, by key, with the ensure room left (review B3) |
| R2 §3 `sacrifice_compensated_v2` | `reasoning/catalogue/sacrifice.py`: rule 3 takes an OPEN keeping line whose engine score is no mate for the mover as below a played mate; the finding's kind is the new `CompensationKind.MATE_OVER_SCORES` when one did. The name follows in the planner, the renderer and its phrasebook (`sentence.mate_over_scores`), the definitions registry (the statement says it is an evaluation) and `agent/remarks.TEMPLATE_PARTS` |
| R3 §4 piece relations | `reasoning/piece_relations.py` (new, `piece_relations_v1`): `PieceRelation` (kind, roles by piece, place, time, side, data), `move_relations(view, parent, child)` — AG8's rules on the records, by identity, unlimited — and `limited` (AG8's limits); `held_exposed` |
| R4 §5 a claim's relation and link | `piece_relations.claim_relation(analysis, claim, view, move_view=None)`: the relation from the finding and the records the verdict's evidence names (`pin_v2` absolute or relative by `delta.pins` / `relative_pins`; `skewer_v2` by `skewers`; `discovery_v2`'s front piece from the `discovery_lines` entry), its time from the facts (`held_exposed`, the defence before and after), its place (the move, or ply k of the line), the link (`explains` › `causes` › `associated_with`) and a mechanism's `did`; None when the relation is not read whole |

## 2. Where the implementation departs from the design, and why

1. **`claim_relation` takes a second view.** MS-D §5 reads the analysis's tree. An on-request
   family the analysis did not ask for is not there: `newly_exposed_v1` skips the check before for
   a moved piece, so `exchange` before the move can be missing, and the relation's time (review N3)
   cannot be read. `move_view` — the game's facts tree, which holds the same node ids for the same
   path (`NodeId.child` is a digest of the parent and the move) — supplies the records of the
   move's two nodes when the analysis's tree lacks them. Without it, such a relation is not read
   (§5's rule), as a test shows.
2. **The open keeping line's score is never a mate.** A line whose engine score is a mate has a
   MATE outcome (`lines.outcome`), so only a line with a centipawn score is OPEN. MS-D §3's "no mate
   for the mover" holds by construction; the code checks it anyway. MS-D §12's test "an open line
   whose score is a mate for the other side is not decided" cannot be built: such a line is MATE
   for the other side, below the played mate, and decided as today (`MATE`), which is what the test
   checks instead.
3. **A test of R2b review B1 changes with the owner's decision.** `test_a_mate_return_over_an_
   undecided_keeping_line_is_inconclusive` (R2b review B1: "strictly above" needs the keeping line's
   outcome) is now `..._over_an_open_keeping_line_rests_on_its_score`: SUPPORTED with
   `mate_over_scores` (MS-D §0, §3).
4. **The small-budget comparison is against today's scan in the same build.** The tests run each
   ply twice, with `BATCH_NODES = 1` (nothing asked ahead: the scan before MS-a) and as built, at
   `max_ensure_nodes` 1, 2, 4, 8 and the default and at `max_rounds` 2, on the Opera Game's plies
   21 and 25: no claim decided today is undecided or decided differently now, and none later.
5. **`move_relations` returns every relation, `limited` cuts.** MS-D §4.2 moves the board's
   reading; the limits belong to the view (`board_v2`, MS-b). `limited(move_relations(...))` is the
   board's set, as the tests check.
6. **The golden full answers are made again.** MS-D §2 changes the mechanisms' `version`, so their
   claims' ids change, the claims' order by id with them, and the claim graphs' digests. The golden
   test of the full view (AG6a, `full_answers_1f9ef15.json`) is replaced by
   `full_answers_ms_a.json`; against the old file the answers differ in exactly four claim ids, the
   order of two claims (`fork_v2` and `pin_v2` at ply 3) and two `bundle.graph` digests — every
   other field is equal (MS-D §11: "the result document and `view: "full"`" — but these ids).
7. **`BATCH_NODES` is a registered threshold.** Every numeric constant of a reasoning rule is in the
   definitions registry (DF-D); `BATCH_NODES` (4, `count`, MS-D §2) is, which changes the
   registry's digest and with it the reasoning build (already changed by §2).

## 3. Tests

- `tests/agent/test_piece_relations.py` (synthetic engine, 6): `limited(move_relations)` is the
  digest's `board` at the game's plies and at AG8 rev. 3–4's cases (a relation moved with its
  piece; a double attack that gained a target; a moved piece newly exposed); a relation's kind,
  side, place, time and identity; the limits.
- `tests/reasoning/test_piece_relations_claims.py` (scripted lines, 4): a piece moved into attack
  is an exposure that `began`; one en prise before that moved to another attacked square `held`
  (review N3); another claim has no relation; without the record before, no relation, and with
  `move_view` the relation.
- `tests/agent/test_ms_a_stockfish.py` (Stockfish 19, gated, 14): the seven fixed moments'
  relations are the board's; 31...Qf6's defence ended f8→f5, its f5 held, its discovery at line ply
  2; 38...Rxh5's exposure began; 13.Rxd7's fork at the move; 6.Bc4's relative pin at line ply 3;
  11.Bxb5+'s fork SUPPORTED within three rounds; the batch never worse and never later at six
  budgets on two plies; 16.Qb8+ `mate_over_scores`, 13.Rxd7 INCONCLUSIVE `LINE_TOO_SHORT`.
- `tests/reasoning/test_catalogue_sacrifice.py`: §2 item 3; a keeping line with a mate score is
  decided by its outcome.
- Changed by the rename: the tests naming `sacrifice_compensated_v1`.

Full suite: see §4.

## 4. Results

Full suite (Stockfish 19): **1652 passed**. ruff check and format clean.

The reasoning build changes (MS-D §2, §3; §2 item 7 here): every cached analysis is recomputed
when it is next read; nothing migrates. The agent's digest and `board` are unchanged in this packet
(MS-b builds `board_v2` on `move_relations` and `claim_relation`).

## 5. Review (rev. 2)

Independent review of rev. 1: NOT_READY — R2, R3 and the build change sound; three defects.

| Item | Applied |
| --- | --- |
| B1 — one double attack, two identities (the board's targets by square, the claim's in its finding's order) | `PieceRelation.__post_init__` puts every relation's roles in one order: the kind's roles as first given, the pieces of one role by square; the test reads 13.Rxd7's fork from the claim and from the board and finds one identity |
| B2 — a line's place without the line | `Place` has `search` and `rank`, read from the mechanism's proof scope (`LineSegment` of an `EngineLineId`); its ply counted from the line's anchor; a line place that cannot be read leaves the relation unread |
| B3 — one claim's batch could take another claim's needed node | MS-D §2's runner order replaced by `Verdict.prefetch`: a mechanism's needs are today's (the first missing step's reads), the later steps' are asked ahead; the runner admits every verdict's needs first, as before MS-a, then the prefetch with the room left. A test with two claims and room for two (`test_a_need_is_admitted_before_another_claims_prefetch`) fails when the prefetch is taken first and passes as built |
| N1 — UNDECIDED before taken as not exposed | `held_exposed` gives no time when the piece's exposure before is UNDECIDED |
| — | the golden full answers made again: `Verdict` gained `prefetch`, so the claim graphs' encoding and their two `bundle.graph` digests change; every other field is rev. 1's file |

This departs from MS-D §2's text ("the runner admits a claim's needs in the order the claim lists
them"): the needs a verdict cannot do without are now admitted exactly as before MS-a, whatever the
room, and only what is asked ahead depends on room left — the review's requirement, met more
strictly than the design's rule.
