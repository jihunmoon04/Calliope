# Agent — BL-D design: a blunder's reason from the facts

Status: **rev. 2 — independent review of rev. 1 (`efb0ae2`) NOT_READY (B1–B7; N1–N9) applied (§11); for re-review**. Date: 2026-10-19. Base: `main @ f07b8d8` (CV4 merged).
Issue: [#123](https://github.com/jihunmoon04/Calliope/issues/123), fix candidates **1** (the board
from the facts), **2** (the board's order on a weak move) and **4** (the played line's material).
The owner chose these three on 2026-10-19 (named "1, 3, 4" in the reply's own list: the board from
the facts, the line-only material, the order). Candidates 3 (settling with a size) and 5 (the
trigger) are not in this packet (review B1).
Inputs: [`agent-ag8-design.md`](agent-ag8-design.md) (AG8-D: `board`, §2.1 the items, §2.3 the
bound's step 0, §3 `proves`, §6.2 the parts),
[`agent-ms-design.md`](agent-ms-design.md) (MS-D: §1.1 the invariants I1–I5, §4 piece relations,
§5 a relation claim's link, §6 `board_v2` and `held`, §8.3 what a `proves` writes, §9 handles),
[`agent-cv4-design.md`](agent-cv4-design.md) (CV4-D: the notes on what a sentence cites).

A blunder's reason is in the facts, yet it can reach the agent as nothing. This packet serves it
from the facts: a mover's piece en prise before and after the move, with the piece that attacks it
(D1, D2); what the played engine line does to the mover's material when the material claim cannot
decide and the best line does better (D3); and the board's order on a weak move (D4). It changes no
claim's verdict and no rule of the reasoning layer.

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
   before the move (by identity) is skipped. The queen was exposed on e3 (gain 4, `f3e3`).
2. A `held` item (MS-D §6 item 3) comes only from a SUPPORTED relation claim (owner's MS-D Q2:
   "`holds` only for the pieces a claim is about"). `newly_exposed_v1` and `left_en_prise_v2` are
   absent here, and the material claim is INCONCLUSIVE.
3. The played line `Qb3 Rxb3 Nb6 Rg4 e5 axb4 cxb4 Rd3` leaves Black at a balance of −9 from its
   second ply to its end (−10 for one ply); the pawn trade at its end leaves it OPEN under
   `settle_v1`, so `material_loss_v2` is INCONCLUSIVE, and the guide says an INCONCLUSIVE claim is
   no reason.
4. Three of the four items read as the mover's gains.

**The survey** (`f07b8d8`, four games, 271 plies: this game, `chesscom_rapid_813_801`, and the trial
games `fourth` and `fresh`; the review's probe recomputed and extended it):

- A mover's piece capturable after the move (`exchange` gain ≥ 3, not hypothetical) at 24 plies
  (25 pieces); at 9 no board item names its square, each exposed before the move as well (2
  blunders, 2 inaccuracies, 3 best, 2 excellent). Among them `34...Qb3` and `7...Bxe2` (the queen on
  e5, attacked by the pawn on f4 since 7.f4, left there); at `34.Qxd6` the queen is attacked by
  another piece after the move than before (`e7` by `d6`, then `d6` by `c7`).
- Pieces of the mover exposed (`exposed_v1`, gain ≥ 1) before and after the move, the mover not in
  check before: 50 on 44 plies, 37 of them pawns and 36 of the plies best, excellent or good moves
  (recaptures such as `2.exd5`, gambit pawns left for several moves). §2's gate keeps 19 of them.
- `material_loss_v2` INCONCLUSIVE other than `MATE_LINE` at 9 plies of grade inaccuracy or worse;
  at 5 the played line ends with the mover behind. At 2 of the 5 the best line ends as far behind
  (`13.Rb1`, `20...c6`: the pawn is lost either way, which is why the comparison is undecided); at
  `10.c5` the line stops on the opponent's capture; at `34...Qb3` (−9 against +1) and `34.Rb4` (−1
  against +3) the best line does better.

## 1. Decisions

| # | Decision | § |
| --- | --- | --- |
| D1 | `move_relations` also gives a **held** `exposed` relation for each of the **mover's** pieces exposed before and after the move (the mover not in check before). The board makes a `held` item of it when its gain after is at least 3, or on any gain when the move is weak; whether or not a claim names the piece. MS-D Q2 is revised for the mover's pieces (owner question Q1). | §2 |
| D2 | Every `exposed` item of the mover's (`weakness`, `held`) names the piece that attacks it first in the exchange (`exchange.first_capture`), with an `attack` proposition; a `held` item names it before and after the move. | §3 |
| D3 | `board.line_material`: on a weak move whose `material_loss_v2` is INCONCLUSIVE (not `MATE_LINE`), when the played line (as the digest shows it) ends with the mover behind, not on a capture, and the best line ends better, the played line's balance at two of its plies, as `material` propositions, cited by a `b` handle. | §4 |
| D4 | On a weak move the board's items are ordered by what is at stake; the first is kept by the bound's step 0; a `threat` while the opponent can take a mover's piece first says so. | §5 |
| D5 | `piece_relations_v2`, `board_v3`, `board_remarks_ko_v3`, guide `commentary_ko_v5`, `agent_guidance_v8`; the check stays `commentary_check_v4`. | §6 |

Not in this packet: the settling rule (`settle_v1`, issue #123 candidate 3), the moments' trigger
(candidate 5), the other side's pieces left en prise (a missed capture), and the deployed `feac72f`
(it has neither MS's `held` nor this; it gets both by deploying `main`).

## 2. D1 — the mover's held pieces from the facts

`move_relations(view, parent, child)` (MS-D §4.2) gains one row:

| Time | Kind | From |
| --- | --- | --- |
| held | exposed (**the mover's** pieces, not the king; **the mover not in check before the move**) | `exchange` before and after, by identity: `held_exposed(view, parent, child, piece) == "held"` |

`held_exposed` is the existing function (`exposed_v1` after, and before with the turn passed; an
undecided state before gives no relation). The relation is
`PieceRelation("exposed", (("piece", <after>),), MOVE, "held", mover, (("gain", <gain after>),))` —
the shape and identity of the `held` relation `claim_relation` reads from a claim (MS-D §5), so the
two are one relation (I1).

- **Not in check before** (review B2). When the mover was in check, a piece's gain before is
  `IN_CHECK` and its exposure before is read from its safe moves, while the existing `began` row
  reads the gain; the two tests can both answer for one piece. This row asks for a `Defined` gain
  before, so a piece is `began` or `held`, never both, and `began` keeps today's test. (In the
  survey: 4 plies, `33.Kb1`, `19...Kh8`, `30.Rg1`, `32.Rg1`, stay as today.)
- **The gate** (review B5). `move_relations` gives every such relation (it is a function of the
  facts and knows no grade). `Board.build` keeps a held relation when its gain after is **at least
  3**, or when the subject's grade is in `WEAK_GRADES` (any gain), and drops the others **before**
  `limited`. Over the survey this gives 19 items on 17 plies: 3 queens, 3 knights, 3 bishops and 10
  pawns; 3 blunders, 3 mistakes, 8 inaccuracies, 3 best, 2 excellent. The recaptures and gambit
  pawns of good moves give none.
- **Limits.** The mover's `exposed` relations kept, began and held together, are sorted by the
  piece's value (then its square) and limited to 3 (`limited`'s key stays `(kind, side)`). The other
  side's pieces exposed before and after give no relation (unchanged).
- **The board.** A held relation becomes a `held` item (`owner`: the mover, `good_for`: the other
  side, `part: reason`), its propositions as §3 gives them.
- **A claim on the same piece.** `Board._link` looks for a claim's held relation among the board's
  `held` items by `identity()` (today it looks only among `threat`, `weakness` and `lost_defence`)
  and attaches its `leads_to`; the claim is then shown once, under the item (MS-D §6's settling). A
  claim's held relation that matches no item (its piece beyond the limit or below the gate) becomes
  a `held` item as today (`_held`; it needs a `Defined` gain before, so never in check).

## 3. D2 — the piece that attacks it

For an `exposed` item of the mover's piece (`weakness` began, `held`), the board reads
`first_capture` of the piece's `exchange` entry at each position the item covers. It is defined
whenever the gain is above 0 (`exchange.py`), which holds for every such entry: after the move the
mover is not in check, and §2 asks for a `Defined` gain before.

- `weakness` (began): `[exposed after, attack after]`;
- `held`: `[exposed before, attack before, exposed after, attack after]`;

each `attack` `{"kind": "attack", "position": <that position>, "attacker": <first_capture's
from-square>, "target": <the piece's square there>}`, verified as given (`Verifier._attack`); an
item whose `attack` is refused is a fault (`refused`, AG8-D §2.1), never served without it.

The `proves` (`board_remarks_ko_v3`) say only what the propositions verify (review B3, N3): that
the piece can be lost by exchange (the `exposed` propositions, with the gain) and which piece
attacks it (the `attack` propositions). They do not say that the piece was left or neglected (it may
have moved, as at 34...Qb3) or which piece captures in the end.

- weakness: `{bracket} {move} 뒤 {piece}은 교환으로 잃을 수 있다 ({attacker}이 공격하고, 정적 교환으로 잡는 쪽이 {gain}점 이득; 수 전에는 아니었다)`;
- held: `[{o}의 약점: 수 전에도 수 뒤에도 {o}의 기물이 위험하다] {move} 전에도 뒤에도 {o} {type}은 교환으로 잃을 수 있다: {attackers} (수 뒤 정적 교환으로 잡는 쪽이 {gain}점 이득)`, where `{attackers}` is
  - one attacker by identity before and after: `수 전 {from}에서도 수 뒤 {to}에서도 {attacker}이 공격한다` (for a piece that did not move: `{from}에서 수 전에도 뒤에도 {attacker}이 공격한다`);
  - two: `수 전 {from}은 {attacker before}이, 수 뒤 {to}는 {attacker after}이 공격한다`.

`{o}` is the piece's owner's colour (the mover's for a facts-made item; the piece's colour for a
claim-made one, as `held_proves` does today); `{piece}` and `{attacker}` are as `remarks.piece`
writes them (colour, type, square); the held piece is written by colour and type (`흑 퀸`) with its
squares in `{from}` and `{to}` (review N2). For 34...Qb3: "[흑의 약점: 수 전에도 수 뒤에도 흑의
기물이 위험하다] 34...Qb3 전에도 뒤에도 흑 퀸은 교환으로 잃을 수 있다: 수 전 e3에서도 수 뒤
b3에서도 백 룩(f3)이 공격한다 (수 뒤 정적 교환으로 잡는 쪽이 9점 이득)". The squares and the gain are
what the propositions verify (I3) and the tokens the item allows (I5, `board_tokens`).

A claim-made `held` item gets the same propositions and `proves`. Adding `attack` to every exposed
`weakness` changes its canonical form: a sentence stating only its `exposed` proposition no longer
states the item whole, which shifts `states_items` against the MS-c and CV4 baselines (review N9;
§9.3 compares by sentences, not by `states_items`).

## 4. D3 — the played line's material

**The window** (review N4). The played line and the best line are read over their first
`n = min(len(PV), PV_PLIES)` plies (`PV_PLIES = 8`, what the digest's `lines` and an `s` handle's
`engine_line` show). `b_j` is the mover's balance after ply `j` of the played line
(`material_flow(...).balance(mover, j)`: the mover's points minus the opponent's, relative to the
position before the move), `e = b_n`; `e_best` the same at the best line's own window end.

**When** (review B6). All of:

1. the subject's grade is inaccuracy or worse (as `material_loss_v2` asks), and the subject has a
   best line of another move;
2. its `material_loss_v2` is INCONCLUSIVE for a reason other than `MATE_LINE`;
3. `e ≤ −1`, and the played window's last ply is not a capture or a promotion (a line cut in the
   middle of an exchange is no point to read: `10.c5` ends on `12...Qxc5`);
4. `e_best > e`: the best line ends better for the mover. Where it ends as far behind, the loss is
   not the move's (`13.Rb1`, `20...c6`), and no item is served.

Over the survey: `34...Qb3` and `34.Rb4`.

**What.** `k` is the first ply of the window from which every balance up to `n` is at most `e`; `b_k`
its balance (`b_k ≤ e`). The item:

```
"line_material": {
  "ref": "<b handle>", "kind": "line_material", "part": "consequence",
  "owner": <mover>, "good_for": <the other side>,
  "proves": "[{m}(둔 쪽)의 물질, 둔 수의 엔진 라인에서] {k의 수} 뒤 {m}은 수 전보다 물질에서 {|b_k|}점 뒤지고, 보인 라인의 마지막 수 {n의 수} 뒤에도 {|e|}점 뒤진다 (보인 라인의 두 지점일 뿐, 라인 뒤의 결과는 아니다)",
  "propositions": [
    {"kind": "material", "line": <the played line's s handle>, "from": 0, "to": k, "side": <mover>, "balance": b_k},
    {"kind": "material", "line": <the same>, "from": 0, "to": n, "side": <mover>, "balance": e}
  ]
}
```

`{k의 수}` and `{n의 수}` are numbered SAN (`35.Rxb3`, `38.Rd3`; issue #122's lesson). When `k = n`
the item has the second proposition only and the `proves` its second clause alone. "물질에서 …점
뒤진다" is the balance the `material` proposition verifies (the mover's points against the
opponent's), not the mover's own points (review B4: after `38.Rd3` Black has 10 points fewer of its
own and is 9 behind). For 34...Qb3: "35.Rxb3 뒤 흑은 수 전보다 물질에서 9점 뒤지고, 보인 라인의
마지막 수 38.Rd3 뒤에도 9점 뒤진다".

- **Why `consequence`.** It says what the move's line does, like `material_loss_v2`'s own `proves`;
  it is no reason, so it does not answer N-reason (CV4-D §2) and must not cause it (§4, *the
  session*). An interpretation citing it does not get N-reading.
- **I3.** The two propositions verify the two balances and nothing between them; the `proves` says
  two points of the shown line and that it is not the line's outcome. The gate (4) compares with the
  best line but the item states no comparison: `better_move_v1` and the claim stay as they are
  (INCONCLUSIVE, shown as today).
- **I5.** Citing the handle builds the two `material` propositions; `Verifier._material` allows the
  line's moves up to `to` and the integers `from`, `to` and the balance — so 0, `k` and `n` are
  citable too, as for any `material` proposition (review N5); `board_tokens` adds the `proves`'
  points (`|b_k|`, `|e|`; `sentences.py` matches a balance by its absolute value).
- **Where.** `board.line_material`, after `same_reply`. It is served through `Session._serve` like the
  changes (a `b` handle bound to the subject and the analysis), and the bound never removes it
  (outside step 0, as `same_reply`).
- **The session** (review B7). `Session._keep_board` lists it as a kept item after `same_reply`
  (built and shown alike, so the strict zip holds and `states_items` can name it), and the flag "the
  digest held a reason" becomes `any(item["part"] == "reason" for item in kept) or any(claim part
  reason)`: a digest whose only board item is `line_material` gives no N-reason.

## 5. D4 — the order on a weak move

On a subject of grade inaccuracy or worse (`WEAK_GRADES`):

1. **By stake.** The items other than `threat` are ordered by what is at stake, largest first: an
   `exposed` item (`weakness`, `held`) its gain; a pin `weakness` the pinned piece's value; a
   `lost_defence` the defended piece's value (points_v1). Ties keep today's kind order
   (`lost_defence`, `held`, `weakness`). Then the `threat` items, as today. For 34...Qb3 the `held`
   queen (9) comes before the `lost_defence` of c5 (1).
2. **Kept.** The bound's step 0 (AG8-D §2.3, MS-D §6) keeps the first item of this order and the
   `opponent_first` target (3), whatever their kinds, before the counts of `BOARD_KEEP` apply to the
   rest. This is a safeguard: no digest of the survey reached step 0 (largest 5,899 characters of
   16,000; review N7); the order (1) is what the agent reads.
3. **The opponent first.** When the board serves a mover's `exposed` item (`weakness` or `held`)
   with gain ≥ 3 and the side to move after the move is not in check, every `threat` item carries
   `"opponent_first": "<ref>"` — the served item with the largest gain — and its `proves` gains
   " (단, 상대 차례이고 둔 쪽 기물이 먼저 잡힐 수 있다: opponent_first의 항목)". The suffix is added
   after `remarks.capped` (the 240-character cap applies to the item's own text and its link's), so
   it is never cut (review N6). It names no square and no number: it allows no new token and states
   only the pointer (I3, I5); the item it points at is cited by its own handle. The pointer is set
   after verification, so it names a served item. A check is never annotated: the opponent must
   answer it first.

Other grades keep today's order and kept counts. (A facts-made `held` item has no `leads_to`, so on
other grades step 0 treats it as a plain item, which MS-D §6 says of `held` items in general;
today's code keeps only linked items first. Unchanged here.)

## 6. D5 — versions, guide, registry

- `piece_relations_v1` → `piece_relations_v2` (§2's row); `board_v2` → `board_v3` (D2's
  propositions, `line_material`, `opponent_first`, the order); `board_remarks_ko_v2` → `v3`
  (`remarks.REMARKS_VERSION`).
- The guide `commentary_ko_v4` → `commentary_ko_v5`, changed only in its `board` section:
  - `held`: "수 전에도 수 뒤에도 교환으로 잃을 수 있는 둔 쪽 기물입니다. 그 기물을 공격하는 상대
    기물이 함께 나옵니다";
  - `weakness`: the item names the piece that attacks it (`attack`);
  - `line_material`: "물질 클레임이 INCONCLUSIVE이고 최선수 라인이 더 나을 때, 둔 수의 엔진 라인에서
    둔 쪽이 물질에서 얼마나 뒤지는지 두 지점으로 보여 줍니다(결과, `consequence`). '엔진 라인에서
    35.Rxb3 뒤 9점 뒤진다'처럼 그 라인의 일로 씁니다. 라인 뒤의 결과나 최선수와의 비교로 쓰지
    않습니다";
  - `opponent_first`: "그 위협보다 상대가 먼저 둔 쪽 기물을 잡을 수 있습니다. 그 항목을 먼저
    보세요".
  "실수의 이유는 보통 …" is unchanged (`line_material` is a consequence, not a reason); the rule
  "INCONCLUSIVE·REFUTED는 이유로 쓰지 않습니다" stays.
- `GUIDANCE_VERSION = "agent_guidance_v8"`; `build.PROMPTS` names `commentary_ko_v5` (its pin in
  `tests/agent/test_server.py` with it); `server.GUIDE_URIS` maps it to
  `calliope://guides/commentary_ko`.
- Registry (`definitions.py`): `board.board_v3` (fields: `changes`, `same_reply`, `line_material`,
  `refused`; an item's `opponent_first`), `board.held` (rule: "a mover's piece exposed before and
  after the move, from the facts (gain ≥ 3, or any on a weak move), or a piece a relation claim
  names"), `board.weakness` (with its `attack`), `board.line_material`, `board.opponent_first`,
  `piece_relations_v2`, `board_remarks_ko_v3`, `prompt.commentary_ko_v5`, in place of their
  predecessors (review N8).
- `commentary_check_v4` unchanged: no sentence rule changes; `line_material` is parted `consequence`
  by its `material` propositions (AG8-D §6.2; `proposition_part("material")`).

## 7. Invariants (MS-D §1.1)

| # | How BL keeps it |
| --- | --- |
| I1 | The held relation has the claim's shape and identity, and one test of "exposed before" decides `began` or `held` (§2); an `attack` is an `attack`, not a capture or a pin. |
| I2 | No claim's status changes; `material_loss_v2` stays INCONCLUSIVE beside `line_material`. |
| I3 | Each `proves` writes what its propositions verify: two exchanges and two attacks (held), an exchange and an attack (weakness), two balances of the shown line (`line_material`); the `opponent_first` suffix states only the pointer. |
| I4 | A claim matched to a facts-made `held` item is reachable under it, by the same settling as MS-D §6. |
| I5 | The tokens allowed by an item are those its `proves` writes and its propositions verify (`line_material`: the line's moves to `n`, 0, `k`, `n` and the points). |

## 8. Implementation (packet BL) and tests

| Item | Change |
| --- | --- |
| L1 | `piece_relations.move_relations`: the held row (§2); `FORMAT`. |
| L2 | `agent/board.py`: the gate before `limited`; held items from relations; `_link` matching held by identity; D2's `attack` propositions; `line_material` (§4); the order and `opponent_first` (§5); `FORMAT`. |
| L3 | `agent/remarks.py`: the `proves` of §3, §4 and §5; `REMARKS_VERSION`. |
| L4 | `agent/digest.py`: step 0 keeps the first item and the `opponent_first` target on a weak move; `line_material` outside step 0. |
| L5 | `agent/session.py`: `_keep_board` with `line_material` and the reason flag (§4). |
| L6 | `prompts/commentary_ko_v5.md`; `build.PROMPTS` and its pin; `server.GUIDE_URIS`; `definitions.py`; `GUIDANCE_VERSION` and its pin. |
| L7 | `docs/design/README.md`: this design and the packet's row. |

Tests (unit, with records built as the existing board tests build them; and gated on Stockfish 19):

- the held row: a mover's piece exposed before and after → one held relation; exposed after only →
  began (unchanged); undecided before → none; the mover in check before → `began` as today, no held
  relation; the other side's held piece → none;
- the gate: gain 1 on a best move → no item; gain 1 on a mistake → an item; gain 3 on a best move →
  an item; the limit of 3 over began and held after the gate, by value;
- a claim's held relation and the facts' are one (`identity()`), the claim shown under the item; a
  claim's held relation below the gate or beyond the limit → a claim-made `held` item as today;
- D2: the `attack` propositions verify; the one-attacker (moved and not moved) and two-attacker
  `proves`; a claim-made held item's owner colour;
- D3: the conditions (grade, best line of another move, INCONCLUSIVE not `MATE_LINE`, `e ≤ −1`, no
  capture at the window's end, `e_best > e`); the window of 8 plies; `k` on `[0, −9, −9, −9, −9,
  −10, −9, −9]` (plies 1–8) is 2 with `b_k = −9`; `k = n` gives one proposition; both propositions
  verify; the `b` handle expands to them; the `proves` says "물질에서 … 뒤진다";
- the session: a digest whose only board item is `line_material` gives no N-reason; `_keep_board`
  keeps it with its index;
- D4: the order by stake; step 0 keeps the first item and the target; `opponent_first` on threats
  but not on a check, nor when the side to move is in check, nor below gain 3; the suffix after the
  cap; non-weak grades unchanged;
- with Stockfish (this game as a fixture, moves only): 34...Qb3's first item is the `held` queen
  attacked by `f3` before and after, its threats carry `opponent_first`, its `line_material` is
  `35.Rxb3 −9 / 38.Rd3 −9`; 7...Bxe2 has a `held` queen on e5 attacked by f4; 13.Rb1 has a `held`
  c5 pawn (a mistake) and no `line_material`; every served proposition of these digests verifies as
  given (`test_board_stockfish._all_verify`'s way).

## 9. Acceptance

1. The suite passes (with `CALLIOPE_STOCKFISH_PATH`).
2. Replay of the four games' digests: the 19 `held` items of §2 (on the plies the survey lists) and
   no item lost that `f07b8d8` serves; 2 `line_material` items (`34...Qb3`, `34.Rb4`); no digest
   over its bound; the digest size change reported.
3. A short agent trial (owner Q3): the four games' fixed moments `7...Bxe2`, `13.Rb1`, `34...Qb3`
   and the moments each game's overview gives; luna and Haiku. Met when a sentence at 34...Qb3 and
   at 7...Bxe2 says the queen can be lost (citing the `held` item or `line_material`), and the count
   of wrong sentences at the fixed moments is not above MS-c's.

## 10. Owner questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Revise MS-D Q2 ("`holds` only for the pieces a claim is about") for the mover's pieces: a `held` item from the facts? | Yes: the claim templates miss the case (34...Qb3, 7...Bxe2), and the fact is exact. The other side's pieces stay out. |
| Q2 | The gate: held items from the facts at gain ≥ 3 on every grade, any gain on a weak move (19 items on 17 of 271 plies), rather than every gain on every grade (50 on 44, mostly pawns on good moves) or weak moves only (14 on 12)? | Yes: a piece left en prise on a good move is part of its story (a sacrifice), a pawn there is mostly a recapture or a gambit; on a weak move any piece can be the reason (`13.Rb1`'s c5 pawn). |
| Q3 | A paid agent trial for this packet? | Yes, short (§9.3): the digest and the guide change, which a replay cannot measure. |

## 11. Review dispositions — rev. 1 (`efb0ae2`), independent review: NOT_READY

| # | Finding | Disposition |
| --- | --- | --- |
| B1 | The issue's candidate numbers do not match the packet. | Applied: the header names the issue's candidates 1, 2 and 4 and how the owner's "1, 3, 4" maps to them; "not in this packet" names candidate 3. The owner chose by the reply's list, so no decision changes. |
| B2 | In check before the move: one piece `began` and `held`, an item `_held` cannot build. | Applied (the review's option ii): the held row asks for the mover not in check before (§2); tests. |
| B3 | The held `proves` says the piece was left as it was (I3). | Applied: a bracket and text that state only the exposure before and after and the attackers; the guide's "방치한 것" dropped (§3, §6). |
| B4 | `line_material` reads as the side's own material (I3). | Applied: "물질에서 …점 뒤진다", the balance (§4, §6). |
| B5 | D1 makes far more items than counted. | Applied: the gate (gain ≥ 3, or any on a weak move), its counts, §9.2 and Q2 restated with the three options' numbers. |
| B6 | `line_material` where the best line ends the same. | Applied: served only when the best line ends better and the window does not end on a capture (§4); kept out of the guide's "reasons" sentence (§6). 2 items in the survey. |
| B7 | `session.py` missing: the strict zip and the N-reason flag. | Applied: L5; `_keep_board` keeps `line_material`; the reason flag on parts (§4); a test. |
| N1 | 24 plies, not 28. | Applied (§0). |
| N2 | The `{piece}` form in the held `proves`. | Applied: colour and type, the squares in `{from}`/`{to}` (§3). |
| N3 | "잡을 수 있다" for an `attack`. | Applied: "공격한다"; the capture is the exchange's gain (§3). |
| N4 | `line_material` past the digest's PV. | Applied: the window `min(len(PV), 8)` (§4). |
| N5 | I5 wording. | Applied: 0, `k` and `n` named as citable (§4, §7). |
| N6 | `opponent_first`: cap, pointer target, step 0. | Applied: the suffix after the cap; the target a served item; step 0 keeps it (§5). |
| N7 | D4.2 inert at today's sizes. | Applied: said so (§5); the existing `held`-without-`leads_to` behaviour noted. |
| N8 | Registry and build entries. | Applied (§6, L6). |
| N9 | Canonical form of `weakness` items changes. | Applied: noted (§3) and §9.3 compares by sentences. |
