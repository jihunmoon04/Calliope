# Agent — WS-D design: where the pieces stood, and what a kept attack costs

Status: **rev. 2 — independent review of rev. 1 (`8628b88`) READY_WITH_CORRECTIONS (B1, B2; N1–N10) applied (§7);
re-review of `4af77eb` READY (N11, N12: record slips in the roadmap and the index, applied).**
Date: 2026-10-30. Base: `main @ f267641` (ST-D #135 and ST
#136 merged).
Owner's direction (2026-10-30): "N4 진행하자", the note ST's implementation review left for the owner
([`agent-st-implementation.md`](agent-st-implementation.md) §5, N4). The direction of ST-D stands: fix the
agent's errors by what it is given, not by deterministic readings or checks of its sentences.
Inputs: [`agent-st-design.md`](agent-st-design.md) §2.3 (the scene's fate) and §3 (since when),
[`agent-st-implementation.md`](agent-st-implementation.md) §4–§5 (the acceptance, the trial, N4).

ST's two texts are true by piece identity but leave out where the pieces were:

- **Since when.** "흑 퀸(f6)의 이 공격은 이 수 전에도 있었다(15...Qf6 뒤부터). 19.Nh6+로 바뀐 것은 공격이
  아니라 그 칸의 잡고 되잡기 셈이다". The knight stood on f5 before the move and moved to h6 with it. "그 칸"
  reads as one square, and the sentence does not say that the knight walked into the attack. When the attacker
  or the target moved during the run ("흑 퀸(a5)의 백 폰(d2) 공격은 이 수 전에도 있었다(2...Qxd5 뒤부터)"),
  the text names only today's squares. In this example the queen stood on d5 then.
- **The scene's fate.** "흑 나이트(f5)은 백 퀸(f4)의 공격을 계속 받는다" says nothing of whether the knight is
  lost. In ST's trial the knight was defended, and two of ST's eight runs wrote it as the danger (below).

This packet adds what is missing: the squares where the run began and where the pieces stood before the
move, and the count on a still-attacked square. It adds no rule and no check.

## 0. Evidence (ST's acceptance data and trial, 2026-10-29)

**Survey.** Every item served by `main @ f267641` was taken at every ply of the four trial games (271 plies,
632 items, warm caches; script and output under the session scratchpad `fr3/n4/`):

| Text | Count | With a piece elsewhere |
| --- | ---: | ---: |
| since sentences (`lost_defence` 49, `threat` 24, `held` 18, `weakness` 12) | 103 | 12 |
| the scene's "계속 받는다" (kept) | 94 | 8 with "{square}로 옮겼지만" |

The 12 since sentences are those whose `attack` propositions (at the run's first position, before the move
and after it) name more than one square for the attacker or the target:
- 9: the attacker moved (e.g. hung 9 "5.Nd4", hung 61, fresh 32, fourth 67);
- 6: the target moved (e.g. fourth 37 "19.Nh6+", hung 68, rapid 39);
- 3 of these counted in both (hung 51, hung 62 twice).

The table does not count a since sentence whose pieces moved and came back. It needs no new text: this design
names a square only where it differs. Of the 12, 11 change: hung 68's `held` has `k = p` and gets no W2 (§2.2).
W2 appears at hung 62 (a threat's attacker) and fourth 37 (a weakness's target); the others get W1 (review N8).

The 94 items with a kept fate carry 114 kept targets. After the move, 83 of these are not exposed and 20 are
exposed (mostly pawns of gain 1). The other 11 follow a check, where the count is not a reading of danger
(§3; review B1).

**Trial.** ST's blind judge (8 luna runs, 12 fixed moments) marked these sentences wrong or doubtful:

| Run | Moment | Sentence | Judge |
| --- | --- | --- | --- |
| B058 | rapid 40 (20...c6) | "흑은 백의 d폰을 압박했지만, 백 퀸이 이미 f5 나이트까지 겨누고 있다는 점도 함께 계산해야 했다" | the knight is defended by Bc8; the line turns on dxc6 |
| B059 | rapid 40 | "흑은 c폰을 전진시켜 … 그 전진이 백 퀸의 압박을 다루지 못했다" | the knight is safely defended |
| B010 | fourth 38 (19...Kh8) | "백이 체크로 만든 기회를 흑이 바로 정리하지 못하면서, 흑은 공격을 받던 나이트까지 위험에 빠뜨렸다" | the d7 knight was already attacked and lost in the best line too |

What the agent was given:
- **Rapid 40.** The only item on the knight was the scene: "20.Qf4 뒤 백 퀸(f4)이 흑 폰(c7), 흑 나이트(f5)을
  동시에 공격하기 시작했다. 20...c6 뒤: …, 흑 나이트(f5)은 백 퀸(f4)의 공격을 계속 받는다". Nothing said the
  knight was safe.
- **B010.** This one is not N4. Its `weakness` said "(수 전에는 체크 중이었다)" and the since sentence's "바뀐
  것은 … 그 칸의 잡고 되잡기 셈이다", which reads as a change. Before the move the count was not defined, since
  Black was in check. §6 keeps it out of this packet.

## 1. Decisions

| # | Decision | § |
| --- | --- | --- |
| W1 | A since sentence names where the attacker and the target stood at the run's first position, when that differs from before the move | §2.1 |
| W2 | A since sentence names where they stood before the move, when the subject's move moved one of them; an exposed item's tail then names the square the target moved to | §2.2 |
| W3 | The scene's "계속 받는다" carries the count on the target's square after the move, with its `exposed` proposition | §3 |
| W4 | `board_remarks_ko_v6`; no guide, check, format or tool change | §4 |

## 2. W1, W2 — the squares in a since sentence

ST-D §3's walk is unchanged: it follows the attacker and the target by identity from the position before
the move (`p`) back to the run's first position (`k`; `0` from the start). Write `sq_k(x)`, `sq_p(x)` and
`sq_a(x)` for a piece's square at `k`, at `p` and after the move. The item already names `sq_a`. A `held`
item names `sq_p` and `sq_a` of the target.

1. **At the run's first position (W1).** When `k ≠ p` and `sq_k(x) ≠ sq_p(x)` for the attacker or the target,
   the since sentence is followed by one sentence for the pieces that differ, in that order (attacker, target):
   - since and long: "{k의 수} 뒤에는 {piece}이 {sq_k}에 있었다" (two pieces: "{a}이 {sq}에, {t}이 {sq}에
     있었다");
   - from the start: "시작 국면에서는 {piece}이 {sq_k}에 있었다".

   `{piece}` is colour and type without a square ("흑 퀸"), **the type the piece has at that position**
   (review B2): a pawn that promoted later is named a pawn on its earlier square. The walk ends on a change
   of the attacker's type (ST-D N9) but not of the target's, so the target's type is read at `k` and at `p`
   from the board there. The particle is computed: 가 after 나이트, 이 after the other names (`remarks.subject`,
   review N6); W2's tail (§2.3) uses it too. The squares at `k` are those of the item's `attack` at the run's
   first position (ST-D §3.3), already among its propositions. For `k = p` there is no such sentence: the
   squares at `k` are those at `p`.

   On a `held` item, W1's sentence goes in brackets inside the since sentence, before its last clause:
   "{attacker}의 이 공격은 {when} 이어졌고({k의 수} 뒤에는 … 있었다), 이 수는 그 공격을 피하지 못했다". A
   `link_remark` (", 이 변화가 …") attaches to the item's last clause; this keeps that clause about the attack,
   not about where a piece stood (review N3). On the other items the since part ends with its tail sentence,
   as in ST.
2. **Before the move (W2).** When `sq_p(x) ≠ sq_a(x)` for the attacker or the target, the since sentence is
   followed (after W1's sentence) by "이 수 전에는 {piece}이 {sq_p}에 있었다", for the pieces that differ. This
   happens only for the subject's moved piece: a `weakness`'s target, or a `threat`'s attacker (the castling
   rook too, which needs no other text). It never happens on `lost_defence`, whose defended piece stays in place
   (`LOST_REASONS`) and whose attacker is the opponent's (review N2). The squares at `p` are those of the
   item's `attack` before the move (ST-D §3.3), already among its propositions. A `held` item gets no W2
   sentence: its first part already names both squares ("수 전 e3에서 … 수 뒤 b3에서도").
3. **The exposed items' tail.** The tail of `weakness` and `threat` ("{move}로 바뀐 것은 공격이 아니라 그 칸의
   잡고 되잡기 셈이다") becomes, when the target moved with the move, "{move}로 바뀐 것은 공격이 아니라
   {target}이 옮겨 간 {sq_a}의 잡고 되잡기 셈이다". Only `weakness` can have this, since a threat's target is
   the opponent's. `lost_defence`'s tail ("새로 생긴 것은 공격이 아니라 수비가 사라진 것이다") stays.
4. **Examples.**
   - **Fourth 37** (W2 on a moved target): "… 흑 퀸(f6)의 이 공격은 이 수 전에도 있었다(15...Qf6 뒤부터). 이
     수 전에는 백 나이트가 f5에 있었다. 19.Nh6+로 바뀐 것은 공격이 아니라 백 나이트가 옮겨 간 h6의 잡고
     되잡기 셈이다" (the knight stood on f5 after 15...Qf6 too, so there is no W1).
   - **Hung 9** (W1): "흑 퀸(a5)의 백 폰(d2) 공격은 이 수 전에도 있었다(2...Qxd5 뒤부터). 2...Qxd5 뒤에는 흑
     퀸이 d5에 있었다. 5.Nd4로 새로 생긴 것은 공격이 아니라 수비가 사라진 것이다".
5. **What a reader can cite.** `board_tokens` reads the squares the text writes. The new squares are the
   `attack` propositions' squares at `k` and `p`, so a sentence citing the item may write them. Nothing new is
   proposed.
6. **Whole or nothing.** W1's and W2's sentences belong to the since part. ST-D §7's appended part is the
   since sentence with them and with the tail, put in whole or not at all under `ITEM_CAP`.

## 3. W3 — the count on a kept target

ST-D §2.3's "kept" fate is a target the attacker still attacks after the move. W3 appends, in brackets, what
`exposed_v1` (`reasoning.lines.exposed`) says of the target after the move, with the gain of the same
`exchange` entry (review N5). **Only when the side to move after the move is not in check** (`status` at the
position after the move, as `_opponent_first` reads it; review B1). `exchange_v1` counts legal captures only,
so after a check most captures on a kept target are illegal and the count reads 0 even for a hanging piece
(11 kept targets in the survey, e.g. the queen on g4 after 19.Nh6+, count 8 if the check were ignored). After
a check, and after mate, the fate stays as in ST, with no bracket and no proposition. Otherwise:
- **exposed** (gain ≥ 1): "{target}은 {attacker}의 공격을 계속 받는다(그 칸의 잡고 되잡기만 셈하면 {mover}이
  {gain}점을 잃는다)";
- **not exposed**: "…계속 받는다(그 칸의 잡고 되잡기만 셈하면 잃는 것이 없다)";
- **undecided**, or no entry (no record): the text stays as today.

The target's "{square}로 옮겼지만" stays before the attacker, as today. For a target that moved, the bracket
names its square: "({sq_a}의 잡고 되잡기만 셈하면 …)", not "그 칸의" (review N4). Each bracket comes with an `exposed`
proposition at the position after the move (piece `sq_a`, the state, the record's gain), as `weakness` gives
its own. In S3 it allows the square and the gain, which the text writes; for not exposed it also allows a
gain of 0, which is accepted. The bracket uses PW-D §3's words ("그 칸의 잡고 되잡기만 셈하면 … 잃는다"),
said from the target's owner, the mover.

The bracket goes in with the fate through `_append`'s `also`, whole or not at all. Its state is computed as
the verifier computes it, so the proposition is not refused (a refused `exposed` would drop the whole scene
item without a fault, review N5). Most kept targets will read "잃는 것이 없다" (83 of the survey's 103 outside
a check), which is what rapid 40 lacked. 20 read a loss. A target exposed before and after the move is not
always a `held` item: `held` items are gated, and a double attack stays in the scene (hung 68's queen, gain 9)
(review N1).

## 4. W4 — versions, registry, sizes

- **Versions:**
  - `REMARKS_VERSION = "board_remarks_ko_v6"`.
  - `board_v4` stays: no field changes; a scene item gains one `exposed` per kept target outside a check.
  - `commentary_ko_v8` stays: its lines on `scene` (§"수 전 상황": "계속 받는지, 더는 받지 않는지") and on
    since-when stay true.
  - `commentary_check_v6`, `TOOLS_VERSION` and `GUIDANCE_VERSION` stay. The registry change moves the
    registry digest (`AGENT_DIGEST`), not the guidance digest; the implementation pins what moves.
- **Registry:**
  - `board_remarks_ko_v6` replaces v5.
  - `board.since` adds "with where the attacker and the target stood at the run's first position and before
    the move, where that differs".
  - `board.scene` adds "a kept target's count on its square after the move, with its `exposed`".
- **Sizes.** On the survey's 271 plies the largest digest was 9,206 characters (bound 16,000). The appended
  parts are whole or nothing under `ITEM_CAP = 480`. The acceptance counts how many since parts and fates no
  longer fit, against `main`.

## 5. Implementation (packet WS), tests, acceptance

**Code:**
- `remarks.py`: the since texts take the W1/W2 sentences and the tail's square; `scene_fate` takes each kept
  target's gain and square; `subject()`, a piece name without a square, with its particle.
- `board.py`:
  - `_since` returns the squares and types at `k` and at `p` for both pieces (it already reads the squares
    for its propositions);
  - the four since callers pass them with `sq_a`;
  - `_scene`, outside a check after the move, reads `exposed_v1` and the `exchange` gain for each kept
    target and adds the `exposed` proposition with the bracket.
- `definitions.py`: as §4.

**Tests** (`tests/agent/test_ws.py`; existing tests updated where a text now carries more):
1. W1: an attacker that moved during the run gives "{k의 수} 뒤에는 … 있었다"; one that did not, nothing. From
   the start gives "시작 국면에서는". The squares written are those of the item's `attack` at `k`.
2. W2 on a moved target: a `weakness` whose piece moved with the move into an attack that stood before. The
   item says "이 수 전에는 … 있었다" and "옮겨 간 {sq_a}"; a `held` item gets no W2 sentence.
3. W2 on a moved attacker: a `threat` whose attacker captured with the move.
4. W3: a defended kept target says "잃는 것이 없다" with `exposed: not_exposed`. An exposed one says the gain
   with `exposed: exposed`. Both propositions verify through `Board._verify`.
5. Whole or nothing: a since part or fate that does not fit leaves the item as ST-D's first part, with the
   part's propositions and tokens out.
6. Particle: "백 나이트가", "흑 퀸이".
7. Review N9:
   - the long outcome's W1 ("{k의 수} 뒤에는");
   - a checking move with a kept, undefended target gets no bracket (B1);
   - a promotion names the pawn on its earlier square (B2);
   - a `held` with W1 and a `leads_to` keeps the link on the attack's clause (N3);
   - a moved kept target names its square (N4);
   - a double attack with two kept targets gets two brackets.
8. The full suite passes.

**Acceptance** (as ST's §4):
1. **Replay.** On the four games' 271 plies, against `main @ f267641`:
   - every item still served, with the same kinds and propositions or more;
   - the largest digest and any bound step;
   - since parts, fates and link remarks that no longer fit, and `MAX_PROPOSITIONS`/`MAX_BOARD_BYTES`
     refusals (review N7);
   - the 12 since sentences and the 94 items' 114 kept fates of §0, with their new texts listed.
2. **Re-verification.** The stored commentaries' position propositions re-verify (ST's 852).
3. **Tool time.** Within noise of `main`.
4. **Short trial.** ST's eight luna runs again on this packet, judged blind together with ST's eight by a
   fresh judge. Passed when:
   - wrong per 100 sentences is not above ST's in the same judging;
   - "old attack read as new" stays 0;
   - no sentence reads a kept, defended target as lost or as the danger at rapid 40.

   One judge and eight runs a side: a check that nothing got worse and that the targeted reading is gone, not
   a measurement.

## 6. Not in this packet

- **B010's case.** A `weakness` whose position before the move was in check says "(수 전에는 체크 중이었다)"
  and then the since tail "바뀐 것은 … 그 칸의 잡고 되잡기 셈이다". Before the move the count was not defined.
  A later wording packet could replace the tail there; it is not N4.
- **B050** (hung 68, "c5 stays defended"): `lost_defence` already gives the counts after the move (1 defender,
  1 attacker). It is not a missing fact.
- **The scene's first part** ("공격하기 시작했다") gets no count. The fate after the move is what the subject
  answered, and it now carries one.

## 7. Review dispositions — rev. 1 (`8628b88`), independent review: READY_WITH_CORRECTIONS

| Finding | Disposition |
| --- | --- |
| B1 after a check, `exchange_v1` counts legal captures only: 11 kept targets would read "잃는 것이 없다" though hanging | Applied (§3): the bracket only when the side to move is not in check; test |
| B2 a promotion: a piece named by its type after the move on an earlier square | Applied (§2.1): the type at that position, the target's read at `k` and `p`; test |
| N1 "exposed before and after is a `held` item" is false (gating, double attacks) | Applied (§3): restated with the survey's counts |
| N2 W2 cannot occur on `lost_defence` | Applied (§2.2, §2.3) |
| N3 on a `held` with W1, a link remark would attach to the W1 sentence | Applied (§2.1): W1 in brackets inside held's since sentence; test |
| N4 a moved kept target's bracket said "그 칸" | Applied (§3): "{sq_a}의"; test |
| N5 compute the state as the verifier does; add the proposition with the fate | Applied (§3, §5) |
| N6 particles computed, not literal; "the one place" inaccurate | Applied (§2.1): `remarks.subject` |
| N7 count link remarks that no longer fit and proposition/size refusals; the denominator | Applied (§5 acceptance, §0) |
| N8 11 of 12 change; W2 only at hung 62 and fourth 37; the fourth 37 parenthetical | Applied (§0, §2.4) |
| N9 more tests | Applied (§5 tests 7) |
| N10 the roadmap's stale lines (header, §3.3 versions, branch count) | Applied in the roadmap |
