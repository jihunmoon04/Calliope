# Agent — BL-D design: a blunder's reason from the facts

Status: **rev. 1 — for independent review**. Date: 2026-10-19. Base: `main @ f07b8d8` (CV4 merged).
Issue: [#123](https://github.com/jihunmoon04/Calliope/issues/123) (fix candidates 1, 3 and 4; the
owner chose these three, 2026-10-19).
Inputs: [`agent-ag8-design.md`](agent-ag8-design.md) (AG8-D: `board`, §2.1 the items, §2.3 the
bound's step 0, §3 `proves`, §6.2 the parts),
[`agent-ms-design.md`](agent-ms-design.md) (MS-D: §1.1 the invariants I1–I5, §4 piece relations,
§5 a relation claim's link, §6 `board_v2` and `held`, §8.3 what a `proves` writes, §9 handles),
[`agent-cv4-design.md`](agent-cv4-design.md) (CV4-D: the notes on what a sentence cites).

A blunder's reason is in the facts, yet it can reach the agent as nothing. This packet serves it
from the facts: a mover's piece left en prise, named with the piece that takes it (D1, D2), what the
played engine line does to the mover's material when the material claim cannot decide (D3), and
the board's order on a weak move (D4). It changes no claim's verdict and no rule of the reasoning
layer.

## 0. What happened

**34...Qb3 (issue #123).** 34.Rf3 attacks the queen on e3; 34...Qb3?? stays on the third rank and
35.Rxb3 takes it. The ply was a moment (blunder, loss 1302); the commentary did not say why. The
digest on `f07b8d8`:

| Item | `proves` (shortened) |
| --- | --- |
| `lost_defence` | the queen no longer defends c5; Rc4 attacks it |
| `threat` | the queen on b3 attacks the rook on c4 |
| `threat` | the pawn on a3 can be won by exchange |
| `threat` | b2 is pinned by the queen on b3 |
| `material_loss_v2` | INCONCLUSIVE, `LINE_TOO_SHORT` |

The `exchange` record after the move holds the answer — `b3`, queen, `gain` 9, `first_capture`
`f3b3`, not hypothetical — but no item serves it:

1. `move_relations` (MS-D §4.2) makes an `exposed` relation only when it **began**: a piece exposed
   before the move (by identity) is skipped. The queen was exposed on e3.
2. A `held` item (MS-D §6 item 3) comes only from a SUPPORTED relation claim (owner's MS-D Q2:
   "`holds` only for the pieces a claim is about"). `newly_exposed_v1` and `left_en_prise_v2` are
   absent here, and the material claim is INCONCLUSIVE.
3. The played line `Qb3 Rxb3 Nb6 Rg4 e5 axb4 cxb4 Rd3` leaves Black at −9 from its second ply to its
   end (−10 for one ply); the pawn trade at its end leaves it OPEN under `settle_v1`, so
   `material_loss_v2` is INCONCLUSIVE, and the guide says an INCONCLUSIVE claim is no reason.
4. Three of the four items read as the mover's gains; on a weak move the guide puts `threat` last
   but the agent still has nothing that says the queen is lost.

**The survey** (`f07b8d8`, four games, 271 plies: this game, `chesscom_rapid_813_801`, and the trial
games `fourth` and `fresh`):

- A mover's piece capturable after the move (`exchange` gain ≥ 3, not hypothetical) at 28 plies;
  at 9 no board item names its square — each one exposed before the move as well (checked on the
  `exchange` records before: gain above 0 at the piece's square), on 2 blunders, 2 inaccuracies,
  3 best and 2 excellent moves. One (`34.Qxd6`) is taken by another piece after than before
  (`e7` by `d6`, then `d6` by `c7`). Among them `34...Qb3` and `7...Bxe2` (the queen on e5,
  attacked by the pawn on f4 since 7.f4, left there).
- `material_loss_v2` INCONCLUSIVE other than `MATE_LINE` at 9 plies of grade inaccuracy or worse.
  At 5 the played line ends with the mover behind (`34...Qb3` −9; `10.c5`, `13.Rb1`, `20...c6`,
  `34.Rb4` −1); at 4 it does not (the claim is about the comparison only).
- `13.Rb1`: the played line is STABLE (−1 from its second ply, `13...Bxc5`), but the best line is
  OPEN, and `material_loss_v2` needs both decided (its rule 4). So "in the engine line White loses
  the c5 pawn" has no citable form.

## 1. Decisions

| # | Decision | § |
| --- | --- | --- |
| D1 | `move_relations` also gives a **held** `exposed` relation for each of the **mover's** pieces exposed before and after the move; the board makes it a `held` item whether or not a claim names the piece. MS-D Q2 is revised for the mover's pieces (owner question Q1). | §2 |
| D2 | Every `exposed` item of the mover's (`weakness`, `held`) names the piece that takes it first (`exchange.first_capture`), with an `attack` proposition; a `held` item names it before and after the move. | §3 |
| D3 | `board.line_material`: on a weak move whose `material_loss_v2` is INCONCLUSIVE (not `MATE_LINE`) and whose played line ends with the mover behind, the line's material at two of its plies, as `material` propositions, cited by a `b` handle. | §4 |
| D4 | On a weak move the board's items are ordered by what is at stake; the first is kept by the bound's step 0; a `threat` after which the opponent can take a mover's piece first says so. | §5 |
| D5 | `piece_relations_v2`, `board_v3`, `board_remarks_ko_v3`, guide `commentary_ko_v5`, `agent_guidance_v8`; the check stays `commentary_check_v4`. | §6 |

Not in this packet: the settling rule (`settle_v1`, issue #123 candidate 2), the moments' trigger
(candidate 5), the other side's pieces left en prise (a missed capture), and the deployed `feac72f`
(it has neither MS's `held` nor this; it gets both by deploying `main`).

## 2. D1 — the mover's held pieces from the facts

`move_relations(view, parent, child)` (MS-D §4.2) gains one row:

| Time | Kind | From |
| --- | --- | --- |
| held | exposed (**the mover's** pieces, not the king) | `exchange` before and after, by identity: `held_exposed(view, parent, child, piece) == "held"` |

`held_exposed` is the existing function (`exposed_v1` after, and before with the turn passed; an
undecided state before is no proof and gives no relation). The relation is
`PieceRelation("exposed", (("piece", <after>),), MOVE, "held", mover, (("gain", <gain after>),))` —
the same shape and identity as the `held` relation `claim_relation` reads from a claim (MS-D §5), so
the two are one relation (I1: the kind, the pieces by identity, the place and the time agree).

- **Limits.** The mover's `exposed` relations, began and held together, are sorted by the piece's
  value (then its square) and limited to 3 (`limited`'s key stays `(kind, side)`). The other side's
  pieces exposed before and after give no relation (unchanged): a piece the mover did not take is
  another question (a missed capture), not this packet's.
- **The board.** A held relation becomes a `held` item (`owner`: the mover, `good_for`: the other
  side, `part: reason`), its propositions `exposed` before and `exposed` after as `_held` builds them
  today, with D2's `attack` propositions.
- **A claim on the same piece.** `Board._link` matches a claim's held relation to the board's `held`
  item by `identity()` and attaches its `leads_to`, as it does for the other kinds (MS-D §6 item 2);
  the claim is then shown once, under the item (MS-D §6's settling). A claim's held relation that
  matches no item (its piece beyond the limit, or not the mover's) becomes a `held` item as today.
- **Every grade.** The relation is a fact of the move, made on every subject (a played ply, a judged
  move) whatever its grade, as a `weakness` is. Of the survey's 9, five are on best or excellent
  moves (a piece left en prise on purpose); the `proves` says only what the exchange verifies (I3).

## 3. D2 — the piece that takes it

For an `exposed` item of the mover's piece (`weakness` began, `held`), the board reads
`first_capture` of the piece's `exchange` entry at each position the item covers (defined whenever
the gain is above 0, MS-D §4.2's precondition; absent in check, where the item stays without it):

- `weakness` (began): `[exposed after, attack after]`, the attack `{"kind": "attack", "position":
  <after>, "attacker": <first_capture's from-square>, "target": <the piece's square>}`;
- `held`: `[exposed before, attack before, exposed after, attack after]`, each attack from that
  position's `first_capture`.

Every `attack` is verified as given (`Verifier._attack`: the attacker attacks the target in
`pieces`); an item whose `attack` is refused is a fault (`refused`, AG8-D §2.1), never served
without it. The `proves` (`board_remarks_ko_v3`):

- weakness: `{bracket} {move} 뒤 {piece}은 교환으로 잃을 수 있다 ({capturer}이 잡을 수 있다; 정적 교환으로 잡는 쪽이 {gain}점 이득; 수 전에는 아니었다)`;
- held, one capturer by identity before and after:
  `[{m}(둔 쪽)이 둔 채로 둔 기물: {m}의 기물이 위험하다] {move} 전에도 뒤에도 {piece}은 {capturer}에게 잡힐 수 있었다 (수 전 {from}, 수 뒤 {to}; 수 뒤 정적 교환으로 잡는 쪽이 {gain}점 이득)`;
- held, two capturers: `… 수 전 {from}은 {capturer before}이, 수 뒤 {to}는 {capturer after}이 잡을 수 있다 (…)`.

`{piece}` and `{capturer}` are written as `remarks.piece` writes them (colour, type, square); the
squares and the gain are what the propositions verify (I3), and they are the tokens the item allows
(I5, `board_tokens`). For 34...Qb3: "34...Qb3 전에도 뒤에도 흑 퀸은 백 룩(f3)에게 잡힐 수
있었다 (수 전 e3, 수 뒤 b3; …9점 이득)".

A claim-derived `held` item (MS-D §6 item 3) gets the same propositions and `proves`.

## 4. D3 — the played line's material

**When.** The subject's grade is inaccuracy or worse (as `material_loss_v2` asks), its
`material_loss_v2` is INCONCLUSIVE for a reason other than `MATE_LINE`, its played line has a PV of
at least 2 plies, and the mover's balance at the PV's end (`material_flow(...).balance(mover, n)`,
`n` the PV's length) is `e ≤ −1`.

**What.** `k` is the first ply of the PV from which every balance up to `n` is at most `e` (so the
mover is never better off than at the end from `k` on); `b_k` its balance (`b_k ≤ e`). The item:

```
"line_material": {
  "ref": "<b handle>", "kind": "line_material", "part": "consequence",
  "owner": <mover>, "good_for": <the other side>,
  "proves": "[{m}(둔 쪽)의 물질, 둔 수의 엔진 라인에서] {k의 수} 뒤 {m}의 물질은 수 전보다 {|b_k|}점 적고, 라인의 마지막 수 {n의 수} 뒤에도 {|e|}점 적다 (보인 라인의 두 지점일 뿐, 라인 뒤와 최선수와의 비교는 아니다)",
  "propositions": [
    {"kind": "material", "line": <the played line's s handle>, "from": 0, "to": k, "side": <mover>, "balance": b_k},
    {"kind": "material", "line": <the same>, "from": 0, "to": n, "side": <mover>, "balance": e}
  ]
}
```

`{k의 수}` and `{n의 수}` are numbered SAN (`35.Rxb3`, `38.Rd3`; issue #122's lesson). When `k = n`
the item has the second proposition only and the `proves` its second clause alone. For 34...Qb3:
"35.Rxb3 뒤 흑의 물질은 수 전보다 9점 적고, 라인의 마지막 수 38.Rd3 뒤에도 9점 적다". For 13.Rb1:
"13...Bxc5 뒤 … 1점 적고, … 19.O-O 뒤에도 1점 적다".

- **Why `consequence`.** It says what the move's line does, like `material_loss_v2`'s own `proves`
  ("엔진 라인에서 … 잡는다 (이 라인에서만 …)"); it is no reason by itself, so it does not answer
  N-reason (CV4-D §2), and an interpretation citing it does not get N-reading.
- **I3.** The two propositions verify the two balances and nothing between them; the `proves` says
  two points of the shown line and says that it is not a settled outcome or a comparison. The claim
  stays INCONCLUSIVE and is shown as today.
- **I5.** Citing the handle builds the two `material` propositions; `Verifier._material` allows the
  line's moves up to `to` and the integers `from`, `to` and the balance; `board_tokens` adds the
  `proves`' points. `|b_k|` and `|e|` are written positive ("9점 적다"): the integers allowed are the
  points the `proves` writes.
- **Where.** `board.line_material`, beside `same_reply`; served through `Session._serve` like the
  changes (a `b` handle bound to the subject and the analysis), kept by the bound like
  `same_reply` (outside step 0).

## 5. D4 — the order on a weak move

On a subject of grade inaccuracy or worse (`WEAK_GRADES`):

1. **By stake.** The items other than `threat` are ordered by what is at stake, largest first: an
   `exposed` item (`weakness`, `held`) its gain; a pin `weakness` the pinned piece's value; a
   `lost_defence` the defended piece's value (points_v1). Ties keep today's kind order
   (`lost_defence`, `held`, `weakness`). Then the `threat` items, as today. For 34...Qb3 the
   `held` queen (9) comes before the `lost_defence` of c5 (1).
2. **Kept.** The bound's step 0 (AG8-D §2.3, MS-D §6) keeps the first item of this order whatever its
   kind, before the kept counts of `BOARD_KEEP` apply to the rest.
3. **The opponent first.** When the board has a mover's `exposed` item (`weakness` or `held`) with
   gain ≥ 3 and the side to move after the move is not in check, every `threat` item carries
   `"opponent_first": "<that item's ref>"` (the largest such) and its `proves` ends with
   " (단, 상대 차례이고 둔 쪽 기물이 먼저 잡힐 수 있다: opponent_first의 항목)". The suffix names no
   square and no number, so the item allows no new token and verifies nothing it does not hold
   (I3, I5); what it points at is cited by its own handle. A check is never annotated: the opponent
   must answer it first.

Other grades keep today's order and kept counts.

## 6. D5 — versions, guide, registry

- `piece_relations_v1` → `piece_relations_v2` (§2's row); `board_v2` → `board_v3` (D2's
  propositions, `line_material`, `opponent_first`, the order); `board_remarks_ko_v2` → `v3`.
- The guide `commentary_ko_v4` → `commentary_ko_v5`, changed only in its `board` section:
  - `held`: "수 전에도 수 뒤에도 잡힐 수 있는 둔 쪽 기물. 그 수가 **방치한 것**이고, 잡는 기물이
    함께 나옵니다";
  - `weakness`/`held`: the item names the piece that takes it (`attack`);
  - `line_material`: "물질 클레임이 INCONCLUSIVE일 때 둔 수의 엔진 라인에서 둔 쪽 물질이 어떻게
    되는지 두 지점으로 보여 줍니다. '엔진 라인에서 35.Rxb3 뒤 9점 적다'처럼 그 라인의 일로 씁니다.
    라인 끝의 결과나 최선수와의 비교로 쓰지 않습니다";
  - `opponent_first`: "그 위협보다 상대가 먼저 둔 쪽 기물을 잡을 수 있습니다. 실수의 이유는 그
    항목입니다";
  - "실수의 이유는 보통 …" gains `line_material` (as a consequence).
  The rule "INCONCLUSIVE·REFUTED는 이유로 쓰지 않습니다" stays.
- `GUIDANCE_VERSION = "agent_guidance_v8"`; registry: `board.board_v3`, `board.line_material`,
  `board.opponent_first`, `piece_relations_v2`, `board_remarks_ko_v3`, `prompt.commentary_ko_v5` in
  place of their predecessors.
- `commentary_check_v4` unchanged: no sentence rule changes; `line_material` is parted
  `consequence` by its `material` propositions (AG8-D §6.2), as any `material` proposition is.

## 7. Invariants (MS-D §1.1)

| # | How BL keeps it |
| --- | --- |
| I1 | The held relation has the claim's shape and identity; an `attack` is an `attack` (the capturer attacks the piece), not a capture or a pin. |
| I2 | No claim's status changes; `material_loss_v2` stays INCONCLUSIVE beside `line_material`. |
| I3 | Each `proves` writes what its propositions verify: two exchanges and two attacks (held), two balances of the shown line (`line_material`); the `opponent_first` suffix states only the pointer. |
| I4 | A claim matched to a facts-made `held` item is reachable under it, by the same settling as MS-D §6. |
| I5 | The tokens allowed by an item are those its `proves` writes and its propositions verify. |

## 8. Implementation (packet BL) and tests

| Item | Change |
| --- | --- |
| L1 | `piece_relations.move_relations`: the held row (§2); `limited` over began and held together; `FORMAT`. |
| L2 | `agent/board.py`: held items from relations; `_link` matching held by identity; D2's `attack` propositions; `line_material` (§4); the order, `opponent_first` (§5); `FORMAT`. |
| L3 | `agent/remarks.py`: the `proves` of §3, §4 and §5 (`board_remarks_ko_v3`). |
| L4 | `agent/digest.py`: step 0 keeps the first item on a weak move; `line_material` outside step 0. |
| L5 | `prompts/commentary_ko_v5.md`; `server.py` guide URI; `definitions.py` registry entries; `GUIDANCE_VERSION` and its pin. |
| L6 | `docs/design/README.md`: this design and the packet's row. |

Tests (unit, with records built as the existing board tests build them; and gated on Stockfish 19):

- the held row: a mover's piece exposed before and after → one held relation; exposed after only →
  began (unchanged); undecided before → none; the other side's held piece → none; the limit of 3
  over began and held, by value;
- a claim's held relation and the facts' held relation are one (`identity()`), the claim shown under
  the item; a claim's held relation beyond the limit → a claim-made `held` item as today;
- D2: the `attack` propositions verify; the one-capturer and two-capturer `proves`; no
  `first_capture` in check → the item without it;
- D3: the conditions (grade, INCONCLUSIVE not `MATE_LINE`, `e ≤ −1`); `k` on `[0, −9, −9, −9, −9,
  −10, −9, −9]` is 2 with `b_k = −9`; `k = n` gives one proposition; both propositions verify; the
  `b` handle expands to them;
- D4: the order by stake; step 0 keeps the first item; `opponent_first` on threats but not on a
  check, nor when the side to move is in check, nor below gain 3; non-weak grades unchanged;
- with Stockfish (this game as a fixture, moves only): 34...Qb3's first item is the `held` queen
  with `f3` before and after, its threats carry `opponent_first`, its `line_material` is
  `35.Rxb3 −9 / 38.Rd3 −9`; 7...Bxe2 has a `held` queen on e5 taken by f4; 13.Rb1 has
  `line_material` `13...Bxc5 −1`; every served proposition of these digests verifies as given
  (`test_board_stockfish._all_verify`'s way).

## 9. Acceptance

1. The suite passes (with `CALLIOPE_STOCKFISH_PATH`).
2. Replay of the four games' digests: 9 new `held` items where the survey found them (and no item
   lost that `f07b8d8` serves); 5 `line_material` items (`10.c5`, `13.Rb1`, `20...c6`, `34...Qb3`,
   `34.Rb4`); no digest over its bound; the digest size change reported.
3. A short agent trial (owner Q3): the four games' fixed moments `7...Bxe2`, `13.Rb1`, `34...Qb3`
   and the moments each game's overview gives; luna and Haiku. Met when a sentence at 34...Qb3 and
   at 7...Bxe2 says the queen is taken (citing the `held` item or `line_material`), and the count of
   wrong sentences at the fixed moments is not above MS-c's.

## 10. Owner questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Revise MS-D Q2 ("`holds` only for the pieces a claim is about") for the mover's pieces: a held item from the facts? | Yes: the claim templates miss the case (34...Qb3, 7...Bxe2), and the fact is exact. The other side's pieces stay out. |
| Q2 | Held items on every grade, or only on weak moves? | Every grade, as `weakness`: a piece left en prise on a good move is part of its story (a sacrifice); D4's order and step 0 keep it out of the way there. |
| Q3 | A paid agent trial for this packet? | Yes, short (§9.3): the digest and the guide change, which a replay cannot measure. |

## 11. Review dispositions

(none yet)
