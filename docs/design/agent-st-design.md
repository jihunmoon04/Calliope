# Agent — ST-D design: the scene before the move, since when, and a guide that only says what the material is

Status: **rev. 3 — re-review of rev. 2 (`f384211`) READY_WITH_CORRECTIONS (C1; N-a–N-c) applied (§12); rev. 2 — independent review of rev. 1 (`208f73b`) NOT_READY (B1–B6; N1–N13) applied (§11). Owner
decisions taken (2026-10-29, §8).** Date: 2026-10-29. Base: `main @ bf2ee80` (PF and its record merged).
Owner's direction (2026-10-29): "모델에게 제약을 하기보다는 자유롭게 하는 쪽" — free the model rather than
constrain it, and fix its errors by what it is given, not by deterministic readings or checks; and, after the
trial: "실험 결과를 문서에 포함해서 넣어줘 권장대로 진행해줘".
Inputs: the FR framing note (PR #130, `agent-free-commentary-framing.md` on `design/fr`, rev. 3 `162e99f`),
whose trials §0 restates in full so this document stands alone; [`agent-ag8-design.md`](agent-ag8-design.md)
(`board`, `proves`, the notes), [`agent-ms-design.md`](agent-ms-design.md) §1.1 and §6 (invariants,
`board_v2`, `held`), [`agent-bl-design.md`](agent-bl-design.md) (`board_v3`, held items from the facts, the
weak-move order), [`agent-pw-implementation.md`](agent-pw-implementation.md) §4 and
[`agent-bl-implementation.md`](agent-bl-implementation.md) §4.1 (the error this packet targets, counted),
[`agent-lm-design.md`](agent-lm-design.md) (`commentary_ko_v7`), [`agent-cv4-design.md`](agent-cv4-design.md)
(the notes), issue #123.

The agent's commonest error today is an attack that held before the move written as made by it ("백 비숍
d5가 그 폰을 공격하게 됐습니다", when the bishop hit f7 since 24.Bxd5). The items it reads do not say what
held before the move, and a guide line against the reading did not stop it. This packet gives the agent
what held before — the scene the opponent's last move set, and since when an attack has stood — together
with the material of the FR trial's rich arm, and replaces the guide's method with a guide that says what
each piece of material is.

## 0. The trials (FR rev. 1–3, 2026-10-20 and 2026-10-29)

Setup for all three: HIMARI v3, one conversation a run, the prompt "이 대국을 분석하고 중요한 장면들을 해설해서
저장해 줘." with the PGN, the four games of PW's and LM's trials (#123's game "hung", "rapid", "fresh",
"fourth") with their warm analyses, luna (`openai/gpt-6-luna`) ×2 a game an arm, scratch copies of
`main @ 40f3e54` (the agent code `main` still has, apart from PF1's store wiring). The twelve fixed moments
are PW's and LM's (hung 14, 25, 68; rapid 40, 52, 54; fresh 56, 62, 76; fourth 37, 38, 56). Errors are counted
blind: the fixed moments' commentaries of every arm shuffled without their arm, read by a fresh-context judge
against each moment's reference (FENs, lines, other candidates, board items, the same reply, claims, PGNs),
boards and lines checked with python-chess.

### 0.1 The arms

| Arm | Guide | Material | Notes |
| --- | --- | --- | --- |
| v7 | `commentary_ko_v7` as merged: the 12-type table, "유형 2~4개", "핵심 장면에서는 유형 1·3·6·8", "좋은 해설은" rules 1–2, "~로 보인다" for interpretations | today's digest | on |
| free | the method replaced: write the scene's story; the grade need not open; vary openings; no frame repeated; join scenes; interpretations need no "~로 보인다" (forcedness words still forbidden); one bad and one good example; the materials as a list. Kept: notation, evidence strengths, whose piece, length advice, submission | today's | off |
| rich | free's, plus two paragraphs on the new material | `structure` and `file` board items (pawns that became passed, isolated, doubled or backward; files whose pawn state changed), the digest's other candidates as `others` with their numbered 6-ply lines | off |
| min | only the task, the tools and the data's fields, and what the check refuses | today's | off |
| story (rev. 3) | rich's, plus two lines saying what the new items are | rich's, plus `scene` items and since-when on `lost_defence` and `held` | off |

### 0.2 Rev. 1 (2026-10-20): v7, free, rich

Means a run (8 runs an arm; v7 = LM3's runs):

| | v7 | free | rich |
| --- | ---: | ---: | ---: |
| Sentences | 52.4 | 53.4 | 49.6 |
| Sentences citing a reason | 29.2 | 21.2 | 21.2 |
| Commentaries opening with the move's name | 94% | 33% | 49% |
| … with the grade in the first sentence | 78% | 39% | 52% |
| Interpretations ending in "보입니다/보인다" | 28% | 0% | 0% |
| Cost | $0.017 | $0.017 | $0.015 |

Blind, at the fixed moments: v7 2 wrong of 117 sentences, free 5 of 122, rich 0 of 113; mean score (1–5) 2.75,
2.42, 2.54. That judge left "an old attack read as new" as borderline (as PW §4 had).

Read: freeing the guide changed the surface (openings, the frame, the hedges), not the content; without the
table and the notes a quarter fewer reasons were cited; material was said where it existed (rapid 8.cxd4:
both rich runs wrote that d4 became isolated).

### 0.3 Rev. 2 (2026-10-20): min

With only the task, the tools and the check, luna wrote about two sentences a scene (20–23 a run against
52), opened 97–100% with the move and the grade, wrote no interpretation, and scored lowest. Removing the
method also removes what the data means; the typed feel is the model's default, not the guide's.

### 0.4 Rev. 3 (2026-10-29): v7, rich and story, the same day

Means a run (8 runs an arm; all new runs):

| | v7 | rich | story |
| --- | ---: | ---: | ---: |
| Sentences | 52.1 | 52.0 | 50.0 |
| … at a fixed moment | 5.0 | 5.0 | 4.7 |
| Sentences citing a reason | 26.9 | 22.6 | 25.6 |
| Interpretations | 12.9 | 13.0 | 12.6 |
| Commentaries opening with the move's name | 88% | 43% | 44% |
| Interpretations ending in "보입니다/보인다" | 19% | 0% | 0% |
| Sentences with "이미", "여전히", "○ 뒤부터", "노리자" … | 0.9 | 0.9 | 4.1 |
| Sentences citing another candidate's line | 4.0 | 2.0 | 3.4 |
| Refused submissions | 3.8 | 4.3 | 3.8 |
| Cost | $0.018 | $0.016 | $0.018 |

Blind, at the fixed moments (72 commentaries, 24 an arm; the reference is story's, which holds every arm's
facts; the judge listed separately the sentences that present an attack that held before the move as made by
it). Every wrong sentence is listed in Appendix B.

| | v7 | rich | story |
| --- | ---: | ---: | ---: |
| Sentences | 121 | 119 | 112 |
| Wrong | 11 | 7 | 3 |
| … per 100 | 9.1 | 5.9 | 2.7 |
| … of them an old attack read as new | 7 | 7 | 1 |
| … other kinds | 4 | 0 | 2 |
| Doubtful | 11 | 3 | 1 |
| Mean score (1–5) | 2.67 | 2.79 | 2.96 |

- **The old attack read as new** is most of the errors once it is counted (26...Re8 "백 비숍 d5가 그 폰을
  공격하게 됐습니다", Bd5 on f7 since 24.Bxd5; 34...Qb3 "백 룩 c4가 그 폰을 공격하게 됐습니다", since 26.Kc1;
  19.Nh6+ "흑 퀸은 그 폰을 공격하게 됐습니다", since 15...Qf6). v7 and rich have 7 each; story 1, at 19...Kh8,
  where its `lost_defence` item says the f7 attack stood since 19.Nh6+ and the sentence still says the king's
  move made it. v7's guide already has a line against this reading for `held` items; it did not stop it on
  `lost_defence` items, which never say what held before.
- **Other kinds.** v7's four are causes or lines misread; rich has none, as in rev. 1; story's two are the
  wrong bishop named at 28...Bxg3 and "최소 룩 하나의 손실" for a rook against two pawns.
- **#123's moment.** story: "34...Qb3는 이미 f3 룩의 공격을 받던 흑 퀸을 b3로 옮겼지만, 공격을 벗어나지 못한
  블런더입니다". v7's second run reads the c5 attack as new.
- **What the scene changes.** The commentary tells the move against what came before: "20.Qf4 뒤 백 퀸은 흑의
  c7 폰과 f5 나이트를 함께 공격하고 있었습니다. 20...c6는 c폰을 공격에서 피하게 했지만, f5 나이트는 여전히
  퀸의 공격을 받았습니다." Reason-citing sentences come back near v7's (25.6 against 26.9) while the surface
  stays free.

### 0.5 What the trials do not show (review N11)

- **Judges differ.** Between rev. 1 and rev. 3, v7's count went from 2 to 11 and rich's from 0 to 7, mostly by
  what the judge counted (rev. 3's judge was told to list the old-attack kind; rev. 1's left it borderline). The
  absolute rates are not comparable across revisions, only the arms within one judging. Rich's "no other
  kind" in both is consistent, not a confirmation.
- **The judging is not fully blind to the arm.** The reference is story's material, and story's commentaries
  carry its markers ("이미", "○ 뒤부터": 4.1 sentences a run against 0.9), which a judge can notice.
- **Confounded.** story differs from v7 in the guide, the notes (off) and the material at once; against rich
  it differs in the material and two guide lines only. The old-attack difference (rich 7, story 1) is the one
  that separates the material; the rest is within one judge's noise (about 0.9 per 100 a sentence).
- **Not trialled.** D2's extension to `weakness` and exposed threats, the third since outcome (§3.1), the scene
  as its own list (§2.6), and the 240-character cap on claims (§7: the trial capped every `proves` at 420).
- **The records** live in session `e058e396`'s scratchpad (`fr3`, the arm key apart in `fr3key`). The counts
  and every wrong sentence are kept here (Appendix B).

### 0.6 What follows

Information, not constraint, lowers the errors: the commonest error comes from items that do not say what
held before the move, and saying it in the item cut it where a guide rule had not. The free guide keeps the
surface free; the material brings the reasons back. This packet takes story into `main` (D1–D5), extends
since-when to the other items whose attack can predate the move (D2), and fixes the trial's rough edges
(rev. 1 review).

## 1. Decisions

| # | Decision | § |
| --- | --- | --- |
| D1 | `board.scene`: what the opponent's previous move began against the mover's pieces, and whether each still stands after the move, as its own list | §2 |
| D2 | Since when, on every item whose attack can predate the move: `lost_defence`, `held`, `weakness` of kind `exposed`, `threat` of kind `exposed`; three outcomes | §3 |
| D3 | rich's material: `board` items `structure` and `file` (proposition kinds `pawn` and `file`), the digest's `others` with their numbered lines; their display | §4 |
| D4 | The guide `commentary_ko_v8` (Appendix A) | §5 |
| D5 | The reading notes N-reason and N-reading off: `commentary_check_v6` | §6 |
| D6 | Versions, the registry, caps and bounds | §7 |

What does not change: the fact engine, the reasoning layer (grades, labels, claims and their verification),
the result document's schema, the server's routes, the tools and their names, the sentence check S1–S8 (a
sentence's moves, squares and numbers must be in what it cites). Existing board items keep their
propositions; D2 adds propositions to an item only where it adds a since sentence (§3.3). The server's
`display_v1` and the viewer gain the two new proposition kinds (§4.4).

## 2. D1 — the scene before the move (`board.scene`)

For a subject at the position after `p` plies of **the subject's path** (the game path for `ply`; for
`judge_move`, the path it was asked at, which may leave the game; `p ≥ 1`, none at the root):

1. **Which relations.** `piece_relations.move_relations` at the previous move of that path (nodes `p−1` →
   `p`, the move the opponent made), kept when `time == "began"`, `side == mover` (the relation bears on the
   mover's pieces), and `kind` is `attack`, `exposed`, `check`, `double_attack` or `absolute_pin`. Dropped:
   - an `attack` on a piece that also has an `exposed` relation there (said once, by the `exposed` item);
   - an `attack` or `exposed` on a piece that is the subject of a `held` item of this board (the `held` item
     says it, with since-when; review N4). A double attack stays: it names more than the held piece. The scene
     is built after `_link`, which can add `held` items from claims (re-review N-c). Should step 0 later cut
     that `held` item, the dropped scene relation is not restored; accepted, since step 0 cuts scene, structure
     and file items first and no step ran on the trial's 271 plies (§7).

   The rest go through `limited(…, opponent)` and are ordered check first, then by `_stake` (largest first),
   then by the largest target's value (`VALUE`), then by square (review N3); at most `SCENE_ITEMS = 3`.
2. **What each says.** By kind, from the opponent's previous move `prev` (numbered SAN):
   - `attack`: "[수 전 상황: 상대의 직전 수가 만든 것] {prev} 뒤 {attacker}이 {target}을 공격하기 시작했다";
   - `double_attack`: "… {prev} 뒤 {actor}이 {t1}, {t2}을 동시에 공격하기 시작했다";
   - `exposed`: "… {prev} 뒤 {piece}은 잡힐 수 있게 됐다: {attacker}이 공격하고, 그 칸의 잡고 되잡기만 셈하면
     {mover}이 {gain}점을 잃는다" (the attacker is the exchange's first capture at node `p`, as `weakness`'s);
   - `check`: "… {prev} 뒤 {mover} 킹이 체크를 받았다 ({squares}에서)";
   - `absolute_pin`: "… {prev} 뒤 {pinned}이 {pinner}에게 킹 쪽으로 핀됐다".

   "시작했다" and "됐다" are `move_relations`' `time == "began"`, a reading of the facts, as the existing
   items' "(수 전에는 아니었다)" (review N1).
3. **Its fate after the subject's move**, for each (attacker, target) pair of an attack, a double attack or an
   exposure, by piece identity at the position after the move (review B5): "{move} 뒤: " then, per target,
   - "{target}은 {attacker}의 공격을 계속 받는다" (with "{square}로 옮겼지만" when the target moved), with the
     `attack` after the move as a proposition;
   - "{target}은 {attacker}의 공격을 더는 받지 않는다" (with "{square}로 옮겨" when it moved), a reading of
     the facts without a proposition, as "(수 전에는 아니었다)";
   - "공격하던 {attacker}를 잡았다" (the attacker is gone).

   The fate is about that attacker only; other attackers are the move's own items. A check and a pin get no
   fate. For `judge_move` of a move not played, the scene's relations and first part are those of the
   position; the fate is the judged move's (review N2).
4. **Propositions.** The relation at the position before the subject's move (`attack`; `pattern`
   `multi_target_attacks`; `exposed` with its attacker's `attack`; `check`; `pin`), and for each target still
   attacked, the `attack` at the position after. They verify like every board item (`Board._verify`); an item
   whose propositions are refused is no item and counts in `refused`.
5. **Tokens.** Citing the item allows what its `proves` shows (`board_tokens`) and the move `prev` with its
   FEN before (`Allowed.add_move`), which the text names. `add_move` also allows the move's from-square and
   number, as it does for the subject's move today; that is accepted (review N5).
6. **Place.** `board.scene` is a list of its own beside `changes` (review B3): `changes` keeps BL-D §5's order
   (on a weak move the costs first, by stake) and `bounded`'s weak-move guard (`changes[0]`). Each scene item
   has `ref` (a `b` handle), `kind: "scene"`, `relation` (the relation's kind), `part: "reason"`, `owner` the
   mover, `good_for` the opponent, `proves`, `propositions`. The served items (`_stated`'s indexes) are the
   changes' in order, then the scene's, then `same_reply` and `played_material` as today.
7. **Size.** `proves` up to `ITEM_CAP` (§7).

## 3. D2 — since when

For an (attacker, target) pair, by piece identity along the subject's path: the attack holds at a position
when the attacker's attack set there (python-chess `attacks`, as `pieces_v1`'s footprint: pins ignored, no
x-rays, en passant no attack) holds the target's square.

1. **Three outcomes** (review B1). Let `p` be the position before the subject's move. If the attack does not
   hold at `p`: **new**. Otherwise walk back while it holds at the position before and the attacker's type is
   the same (a promotion ends the walk; review N9), at most `SINCE_PLIES = 16` plies:
   - **since k**: the walk stops at a position after ply `k ≥ 1` where it held but not at `k−1` (or the type
     changed at `k`): "{k의 수} 뒤부터";
   - **long**: the walk reached its bound at `k = p − 16` and the attack still held at `k − 1`: "적어도 {k의 수}
     뒤부터";
   - **from the start**: it held at every position back to the root (`k = 0`, a game from the initial
     position or a FEN): "시작 국면부터".
2. **Which items, and what they add** (a sentence appended to the item's `proves`; `{when}` is the outcome's
   words):
   - `lost_defence` (the attacker after the move and the defended piece): new — "{attacker}의 이 공격은
     {move}로 새로 생겼다"; otherwise — "{attacker}의 {defended} 공격은 이 수 전에도 있었다({when}).
     {move}로 새로 생긴 것은 공격이 아니라 수비가 사라진 것이다";
   - `held` (one piece attacks it before and after, `first == then`): otherwise — "{attacker}의 이 공격은
     {when} 이어졌고, {move}는 그 공격을 피하지 못했다"; when `first != then`, nothing;
   - `weakness` of kind `exposed` (its attacker the exchange's first capture after the move): otherwise —
     "{attacker}의 이 공격은 이 수 전에도 있었다({when}). {move}로 바뀐 것은 공격이 아니라 그 칸의 잡고
     되잡기 셈이다"; new — nothing (the item already says "수 전에는 아니었다" of the exposure);
   - `threat` of kind `exposed` (an opponent piece the mover can now take; its attacker found by
     `_attacker(child, square)`, review B4): otherwise — "그 기물을 공격하는 {attacker}의 공격은 이 수 전에도
     있었다({when}). {move}로 바뀐 것은 공격이 아니라 그 칸의 잡고 되잡기 셈이다"; new — nothing. When
     `_attacker` names none, the item stays as today, with no since sentence and no fault (re-review N-a).

   The other `threat` kinds (`attack`, `double_attack`, `check`, `pin`) are relations that began with the move
   by `move_relations`' definition; their text already says "(수 전에는 아니었다)" and gets nothing. A
   `weakness` of kind `pin` gets nothing.
3. **Propositions** (review N1, B4), added only with a since sentence that is not "new": the `attack` at `p`
   (the squares there; already present on `held`), and the `attack` at the run's first position (`k`, or `0`
   from the start), when it is not `p`. A `threat` of kind `exposed` also gets the `attack` after the move
   (attacker, target), so the attacker it names is verified. Continuity between those positions is the facts
   reading, as "(수 전에는 아니었다)"; the walk is deterministic. Positions are `{"ply": k, "at": "after"}` in
   a ply's answer (`{"ply": 1, "at": "before"}` for the root, `k = 0`, since `Session.path` takes plies from 1;
   re-review C1) and `{"from_root": path[:k]}` in `judge_move`'s (as `Board.before`/`after` today).
4. **Tokens.** The move of ply `k` (since k and long), with its FEN before, is a token the item allows; nothing
   for "new" or "from the start".

## 4. D3 — rich's material

1. **`structure` items** in `changes`, after the move's relation items: for each pawn of the position after
   the move flagged `passed`, `isolated`, `doubled` or `backward` (`pawns_v1`) that was not so before (at its
   square before, following the moved pawn), grouped by colour and flag: "[{owner}의 폰, {good}에게 좋음]
   {move} 뒤 {owner} 폰 {squares}은 {flag}이 됐다(수 전에는 아니었다)"; `owner` the pawns' colour, `good_for`
   the owner for `passed`, the opponent otherwise. Propositions: `pawn` (square, flag, true) after, and
   (square before, flag, false) before where the pawn existed before.
2. **`file` items** in `changes`, after `structure`: each file whose state (`open`, `semi_open_white`,
   `semi_open_black`, `closed`) changed: "{move} 뒤 {file}파일은 {before}에서 {after}이 됐다"; `owner` the
   mover, `good_for` none (review N6). Propositions: `file` before and after.
3. **Two proposition kinds**, verified from `pawns_v1` at a position: `pawn` (`square`, `flag` in
   `passed|isolated|doubled|backward`, `value`), refused for a square without a pawn or another flag; `file`
   (`file` a–h, `state`), refused for another letter or state. In S3 a `pawn` allows its square; a `file` allows
   nothing beyond its letter, which S3 does not read.
4. **Display** (review N7): `server.commentary.POSITION_KINDS` gains `pawn` and `file` (the position shown);
   the viewer's `propositionLine` writes "폰: {square} ({flag_ko})" and "파일: {file} ({state_ko})", and
   `positionMarks` rings a `pawn`'s square.
5. **`others`** in the digest: the other candidates (at most `OTHERS = 3`), each `{"ref", "move"` (numbered),
   `"score", "score_text", "pv"` (numbered, 6 plies)`}`, cited by their `s` handles, which the session already
   serves; citing one allows the line's moves as any `s` handle does (8 plies, as `lines` shortened). `bounded`'s
   step 2 shortens `others`' `pv` to 4 plies with the lines' (review N8). `not_shown.others` and
   `BEHIND_DETAIL`'s "the other candidates" go.

## 5. D4 — the guide `commentary_ko_v8`

Appendix A holds the text. Against the story arm's guide (rich's, §0.1, with two lines on scene and since):
`others` shown, not behind `detail`; `scene` as `board.scene`; since-when on the four item kinds with its three
outcomes; the notes not mentioned. Against v7 it drops the method (the type table, "유형 2~4개", "핵심 장면에서는
유형 1·3·6·8", "좋은 해설은" 1–2, "~로 보인다" for interpretations, the notes) and adds the story advice and the
material's descriptions.

It is not rule-free (review B6). It keeps v7's rules on what a sentence may claim: forcedness words only when
the board shows them; whose piece and who loses, as `proves` says; `held` and since-when not written as new
attacks; the played line not called the game ('실전 라인'); '교환' only for like values; the claim readings
(ATTRIBUTED, `specific_line`, configurations, INCONCLUSIVE, the agent's own lines); notation. It advises
against the same frame each scene. It adds no rule beyond these. `commentary_ko_v7` stays as data, unserved
(as v1–v6).

## 6. D5 — the notes off

`_notes` (N-reason, N-reading; AG8-D §6.4, CV4-D §2) gives none: `commentary_check_v6` is v5 without the
notes. All rich and story runs ran with the notes off. `_keep_board`'s `reason` flag, read only by the notes,
stays (it is part of the served record) and is documented as unused by the check. `states_items` and the
refusals S1–S8 are unchanged.

## 7. D6 — versions, registry, caps, bounds

- **Versions:** `board_v4`, `board_remarks_ko_v5` (`REMARKS_VERSION`: the texts change), `commentary_ko_v8`,
  `agent_guidance_v11`, `commentary_check_v6`. `TOOLS_VERSION` changes only if a tool's description changes
  (stated by the implementation).
- **Registry** (`agent/definitions.py`): `board_v4` (with `scene`; the weak-move order unchanged), `board.scene`,
  `board.structure`, `board.file`; the statements of `held`, `lost_defence`, `weakness`, `threat` (since-when);
  `proposition.pawn`, `proposition.file`; `commentary_check_v6`. The registry digest in
  `tests/agent/test_guidance.py` is updated.
- **Caps** (review B2). `remarks.PROVES_CAP` (240) stays for one remark, for a board item's first part, and
  for claims' `proves` (one too long is none, MS-b N3). A board item's full `proves` is capped at
  `ITEM_CAP = 480`, built in this order: the first part (≤ 240, as today); the since sentence (§3) or the
  scene's fate (§2.3); `link_remark` (`_link`); `OPPONENT_FIRST` (`with_opponent_first`, a threat's suffix).
  Room for the suffix is kept; each appended part goes in whole or not at all, so no text is cut mid-way: a
  part left out takes its propositions and its extra move token with it, and the item keeps only what its
  text states (re-review N-b). Deviation from the trial: it capped every `proves` (claims too) at
  420; claims' `proves` of 241–420 characters are none again, as on `main`.
- **Bounds.** `DIGEST_LIMIT` (16,000 characters) and its steps stay. Step 0 (review B3) cuts, while the digest
  is over: first `file` items, then `structure` items beyond the first, then scene items beyond the first, then
  today's kinds by `BOARD_KEEP` (with its weak-move guard on `changes[0]`). `BOARD_KEEP` gains `file: 0`,
  `structure: 1`; `SCENE_KEEP = 1`. Measured on the trial arm (`cal-story`), the four games' every ply (271):
  the largest digest is 8,344 characters (means 3,311–3,707), no step ran. `MAX_PROPOSITIONS` (32 in one
  commentary) and `MAX_BOARD_BYTES` stay; larger items (a `held` with since has up to 5 propositions, a
  scene double attack up to 5) press against the 32, so the acceptance counts size refusals (review N8).
- **Cost** (review N10). The scene reads the relation families at node `p` and `FAMILIES` at `p−1`;
  `structure`/`file` read `pawns` at two nodes; since-when reads node headers along up to 16 plies and
  `pieces` at its proposition positions. The acceptance measures a ply's tool time against `main`.

## 8. Owner decisions (2026-10-29, as recommended)

| # | Question | Decision |
| --- | --- | --- |
| O1 | Since-when on `lost_defence` and `held` only (as the trial), or also on `weakness` and `threat`? | Also on `weakness` and `threat` of kind `exposed` (D2); the other threat kinds began with the move by definition |
| O2 | The reading notes: off (as the trial) or kept? | Off (D5) |
| O3 | Scene items a move | At most 3 (as the trial) |

## 9. Implementation (packet ST), tests, acceptance

**Code.** `calliope.agent`: `board.py` (scene, since-when, structure, file, caps), `digest.py` (`others`,
step 0, step 2, `BEHIND_DETAIL`), `propositions.py` (`pawn`, `file`), `remarks.py` (texts, `ITEM_CAP`,
`REMARKS_VERSION`), `session.py` (`_notes` off, `CHECK`), `definitions.py`, `build.py`/`server.py` (the guide
v8), `prompts/commentary_ko_v8.md`. `calliope.server.commentary` (`POSITION_KINDS`) and `viewer/index.html`
(§4.4).

**Tests** (review N13).
1. Scene, on #123's game and rapid: 34...Qb3 (the queen made capturable by 34.Rf3 dropped for the `held`
   item; the double attack on e3 and f7 kept, the queen still attacked on b3 by the f3 rook); 26...Re8 (the
   double attack by 26.Qh6, f8 "더는 받지 않는다" of the queen); 27...Nxf7 (the attacker taken); no scene at
   ply 1; the attack dropped when an exposure says it; the order (a check first); at most three;
   `judge_move` of another move at that position (same relations, the judged move's fate); `judge_move` on a
   path off the game.
2. Since-when: 34...Qb3's `lost_defence` (Rc4 on c5 since 26.Kc1) and `held` (Rf3 since 34.Rf3); 26...Re8's
   `lost_defence` (Bd5 on f7 since 24.Bxd5); "new"; "long" at the 16-ply bound; "from the start" in a game from
   a FEN; a promotion ending the walk; a `weakness` whose attacker attacked before and one whose did not; a
   `threat` of kind exposed with its three attack propositions.
3. Caps: an item with a since sentence and a `link_remark`; a threat with since and `opponent_first`; a part
   that does not fit is left out whole; claims' `proves` still capped at 240.
4. Every item's propositions verify; the since and scene moves are allowed tokens when the item is cited and
   only then; a sentence citing a scene item and writing `prev` passes S3.
5. `pawn` and `file`: verification and refusals; their display line and marks.
6. `others` in the digest and step 2; `not_shown` without them; step 0's order with the new kinds and the
   weak-move guard.
7. `_notes` gives none; the check version; the registry entries and digest; the guide served at its URI.
8. The golden answers updated where the digest changes (stated per file).

**Acceptance.**
1. **The replay.** Every commentary stored by the FR rev. 3 runs and by LM's and PW's trials is checked again
   by `commentary_check_v6`: its stored propositions re-verified against freshly built answers, cited items
   matched by their canonical propositions (handles differ), tokens by what those allow. None refused that v5
   accepted, apart from what the new digest no longer serves (stated if any).
2. **The bound.** Over the four games' every ply on the implementation: digest sizes, step 0's cuts against
   `main`, size refusals (`MAX_PROPOSITIONS`) in the trial below.
3. **Tool time.** A ply's `ply` answer time over the four games against `main` (warm cache, the same host).
4. **A short trial** (luna ×2 a game on the four games, the same setup): blind, mixed with rev. 3's v7 and
   story commentaries at the fixed moments, one fresh-context judge with the same instructions. Met when, in
   that judging (review N12):
   - ST's old attacks read as new are no more than story's plus one;
   - ST's other kinds are no more than story's plus one;
   - no wrong sentence comes from a scene's or a since sentence's own text (a false fact in it);
   - and ST's wrong sentences per 100 are below v7's.

## 10. Not in this packet, and not chosen

- **A check on the reading** (refuse or note a sentence that says "새로", "공격하게 됐다" of an attack that
  held before): not chosen, by the owner's direction (2026-10-29): errors are fixed by what the agent is given.
- **E2's other items** (a natural move's refutation, the opponent's threat after the move, the king's
  shelter) and **E3** (a stronger writer at key moments): later packets (FR §5).
- **Issue #123's candidates 3 and 5** (settling with a size; binding the threat's move and the reply to the
  moment): not here. The scene states the threat's move as information, not as a moment.
- **The FR note** (PR #130) stays a framing note; its trials are restated in §0.

## 11. Review dispositions — rev. 1 (`208f73b`), independent review: NOT_READY

| Finding | Disposition |
| --- | --- |
| B1 the 16-ply bound and the root give false "since" and "새로 생겼다" | Applied (§3.1): three outcomes — since k, "적어도 … 뒤부터" at the bound, "시작 국면부터" at the root; "새로 생겼다" only when the attack is absent before the move |
| B2 `ITEM_CAP` against `_link`'s and `with_opponent_first`'s re-caps; the trial's global 420 | Applied (§7): one build order, `ITEM_CAP = 480`, parts whole or not at all; claims stay at 240, stated as a deviation |
| B3 scene-first breaks step 0's weak-move guard and the weak-move order; new kinds not in step 0 | Applied (§2.6, §7): `board.scene` as its own list; `structure`/`file` after the relation items; step 0's order and keeps for the new kinds |
| B4 an exposed threat has no attacker to walk from nor propositions | Applied (§3.2–3.3): the attacker by `_attacker(child, square)`, its attacks after, before and at k; §1 says which items gain propositions |
| B5 "더는 공격받지 않는다" says more than shown | Applied (§2.3): the fate names the attacker; "계속" carries the attack after; "더는" is the facts reading |
| B6 the guide defined only by an ephemeral file; stale lines; "no rule added" false | Applied (§5, Appendix A): the text in full, corrected; the kept rules listed |
| N1 "before" in since not verified | Applied (§3.3): the attack at `p` added; continuity stated as the facts reading |
| N2 "game path" wrong for `judge_move`; the fate depends on the judged move | Applied (§2, §3, test 1) |
| N3 `_stake` 0 for checks and attacks | Applied (§2.1): check first, then stake, value, square |
| N4 the scene duplicates `held` | Applied (§2.1): attack/exposed on a held piece dropped |
| N5 `add_move` allows a from-square the text does not show | Accepted as for the subject's move (§2.5) |
| N6 versions and registry incomplete | Applied (§7, §4.2): `board_remarks_ko_v5`, item kinds, statements, `BEHIND_DETAIL`, the registry digest, `file`'s owner |
| N7 new kinds not displayed | Applied (§4.4): server `POSITION_KINDS` and the viewer |
| N8 `MAX_PROPOSITIONS`, step 2 and `others`, 6 against 8 plies | Applied (§4.5, §7, acceptance 2) |
| N9 identity edge cases | Applied (§3.1: promotion ends the walk; test 2) |
| N10 cost | Applied (§7, acceptance 3) |
| N11 §0's limits understated; evidence ephemeral | Applied (§0.5, Appendix B) |
| N12 acceptance criteria weak; replay mapping | Applied (§9 acceptance 1 and 4) |
| N13 tests missing | Applied (§9 tests 1–8) |

## 12. Review dispositions — rev. 2 (`f384211`), independent re-review: READY_WITH_CORRECTIONS

B1–B6 and N1–N13 resolved.

| Finding | Disposition |
| --- | --- |
| C1 `{"ply": 0, …}` refused by `Session.path` for "from the start" | Applied (§3.3): `{"ply": 1, "at": "before"}`; test 2 asserts the FEN case verifies |
| N-a an exposed threat with no attacker | Applied (§3.2): no since sentence, no fault |
| N-b whole-or-nothing for propositions | Applied (§7): a part left out takes its propositions and token |
| N-c dedup after `_link`; a cut `held` item | Applied (§2.1): after `_link`; the cut case accepted and stated |

## Appendix A — `agent/prompts/commentary_ko_v8.md`

```text
# Calliope 해설 작성 (prompt.commentary_ko_v8)

대상: 게임 {game}, 수 {ply}.

## 당신의 일

당신은 체스 해설가입니다. 정해진 틀은 없습니다. 사람 해설가처럼 이 장면의 이야기를 자유롭게 쓰세요. 지켜야 할 것은 하나입니다: **판에 대한 사실 주장에는 근거를 붙입니다.** Calliope는 등급, 평가, 엔진 라인, 클레임, 판의 변화 같은 데이터와 그것을 확인하는 도구를 줍니다. 각 근거의 `proves`는 그 근거가 증명하는 것입니다. `proves`를 이어 붙이지 말고, 재료로 삼아 당신의 말로 쓰세요.

## 어떻게 쓰는가

1. **판을 읽습니다.** `ply`로 등급, 평가, 최선수, 둔 수와 최선수의 라인, 다른 후보수, 수 전후 FEN, 수 전 상황(`board.scene`), 판의 변화(`board.changes`), 클레임을 받습니다. FEN과 라인을 직접 읽으세요.
2. **이 장면의 이야기를 정합니다.** 이 수 전에 무엇이 걸려 있었는지, 이 수로 무슨 일이 일어났는지, 둔 사람은 무엇을 원했을지, 무엇을 놓쳤는지, 다른 수였다면 어땠는지, 이 장면이 대국의 흐름에서 어떤 의미인지. 장면마다 가장 흥미로운 것이 다릅니다. 어떤 장면은 전술 하나가 전부이고, 어떤 장면은 계획의 충돌이고, 어떤 장면은 앞의 실수에 대한 대가입니다. 그 장면에 맞는 이야기를 고르세요.
3. **근거를 확인합니다.** 받은 근거는 핸들로 바로 인용합니다. 더 필요한 것은 도구(`facts`, `explore`, `judge_move`, `detail`)로 확인합니다. 예를 들어 "왜 자연스러운 수 ○는 안 되는가"는 `explore(moves: [○, 응수])`로 볼 수 있습니다.
4. **씁니다.**

### 피할 것: 매 장면 같은 틀

나쁜 해설은 모든 장면을 같은 순서로 씁니다: "○는 부정확 판정입니다. 엔진은 △를 권했습니다. 엔진 라인은 …로 이어집니다. 따라서 △가 더 나았던 것으로 보입니다." 이렇게 쓰지 마세요.
- 등급은 꼭 첫 문장에 둘 필요가 없고, 등급 단어를 쓰지 않고 판단을 전해도 됩니다("이 수로 흑은 큰 대가를 치른다"). 단 그 수의 판정(`j…`)은 한 문장에서 인용합니다.
- 장면마다 첫 문장을 다르게 시작하세요: 판의 상황, 둔 사람의 의도, 상대의 위협, 앞 장면과의 연결 등.
- 문장의 끝을 반복하지 마세요. "~것으로 보입니다"를 매번 붙이지 않습니다(아래 해석 문장 참고).
- 장면끼리 이어 쓰세요. 앞 장면의 실수가 다음 장면에서 어떻게 대가를 치르는지, 같은 기물이나 칸이 어떻게 다시 등장하는지.

### 문장 두 가지

- **sourced**: 판에 대한 사실(무엇이 무엇을 공격한다, 어떤 수순에서 무엇을 잃는다, 평가가 얼마다). 그 사실을 담은 근거를 인용합니다.
- **interpretation**: 해설가의 판단 — 의도, 계획, 흐름, 심리, 어느 쪽이 편한가, 교훈, 비유. 인용한 근거와 **모순되지 않아야** 합니다. 뷰어는 이 문장을 해설가의 판단으로 표시하므로, 매번 "~로 보인다"를 붙일 필요는 없습니다. 다만 판이 보여 주지 않는 강제성("반드시", "막을 수 없다", "유일한 수")은 해석 문장에서도 쓰지 않습니다.
- 구체적 사실·인과("○가 △를 공격한다", "○ 때문에 △를 잃는다")는 해석이 아니라 사실 주장입니다. 해석 문장으로 바꿔 쓰지 말고, 확인해서 sourced로 쓰거나 쓰지 않습니다.

해석 문장은 판의 구체적인 것(기물, 칸, 수순)에 닿아야 합니다. "기회를 놓쳤다", "흐름이 넘어갔다"처럼 어느 대국에나 맞는 말만 있는 문장은 쓰지 마세요.

### 근거의 세기

근거에는 세 가지 세기가 있습니다. **배치**(지금 판에 있는 관계), **가능한 수순**(한 라인에서 일어나는 일), **엔진의 판단**(엔진 평가와 수순으로 얻은 결론). 확인한 세기만큼만 말하세요. 엔진 평가와 몇 개의 수순으로는 강제성이 증명되지 않습니다. "엔진 기준으로는"처럼 쓰세요. "유일한 수"는 둘 수 있는 수가 하나뿐일 때(`legal_moves`)나 체크메이트일 때만 씁니다.

### 예시 (다른 대국, 형식만 보세요)

같은 실수를 두 가지로 쓴 예입니다.

나쁜 예(틀): "18...Qd6는 실수 판정입니다. 엔진은 18...Qf6를 권했습니다. 둔 수 뒤 엔진 라인은 19.Rxe7로 이어집니다. 따라서 18...Qf6가 더 나았던 것으로 보입니다."

좋은 예(이야기):
- [interpretation] "흑은 d파일을 먼저 막고 싶었다." (cites: 판정 j, 판의 변화 b)
- [sourced] "하지만 퀸이 d6로 가면서 e7의 룩은 지켜 주던 기물을 잃었고, 백 룩 e1이 그 룩을 바로 노린다." (cites: `lost_defence` 항목 b)
- [sourced] "둔 수 뒤 엔진 라인에서 백은 19.Rxe7로 룩을 그대로 가져간다." (cites: 둔 수의 라인 s)
- [sourced] "같은 19.Rxe7을 18...Qf6 뒤에 두면 퀸이 되잡아 물질은 그대로다." (cites: `same_reply` b)
- [interpretation] "d파일보다 e7의 룩이 먼저였다. 이 실수로 흑은 다음 장면에서 룩 하나가 모자란 채로 싸운다." (cites: b, s)

## 받는 재료

위치는 `{{"ply": n, "at": "before" | "after"}}`(그 수를 두기 전/후)입니다.

- `board`: 수 전 상황(`scene`)과 이 수가 판에 만든 변화(`changes`)(아래). 기물 관계뿐 아니라 **폰 구조**(`structure`: 패스트·고립·더블·백워드 폰이 새로 생김)와 **파일**(`file`: 열린·반열린 파일이 바뀜)도 있습니다. 구조는 전술보다 오래 남는 이야기입니다: 고립된 폰은 이후 표적이 되고, 반열린 파일은 룩이 쓸 길이고, 패스트 폰은 엔드게임의 무기입니다. 이런 계획과 장기적 의미는 해석 문장으로 쓰고, 그 항목(`b`)을 인용하세요.
- `others`: 최선수와 둔 수 말고 엔진이 본 다른 후보수와 그 라인(`s` 핸들, 번호 붙은 수순). "○도 생각할 수 있었지만 엔진 라인에서는 △로 이어진다", "자연스러운 ○는 …"처럼 둔 사람이 고민했을 선택지를 말할 수 있습니다.
- `lines`: 둔 수와 최선수의 엔진 라인(`s` 핸들). 수순과 평가를 말할 수 있습니다.
- `claims`: Calliope가 확인한 결론(`c` 핸들).
- `facts(위치)`: 국면의 사실(공격, 방어, 핀, 패턴, 노출, 폰). 기록으로 명제를 만들어 인용합니다. 공격·방어·핀은 family `pieces`, 체크·둘 수 있는 수는 `status`, 패턴은 `patterns`, 노출은 `exchange`, 폰과 파일은 `pawns`입니다. 기본 family는 `status`, `material`, `pieces`입니다.
- `explore(moves)`: 당신이 두어 보는 수순(`x` 핸들). `search` 없이 두면 엔진 예산을 쓰지 않습니다.
- `judge_move(위치, 수)`: 두지 않은 수의 판정.
- `detail(ref)`: 기본 응답에 보이지 않는 것(반박된 클레임, 클레임의 findings).

## 인용: 핸들로 바로

받은 근거는 문장의 `cites`에 **핸들을 그대로** 씁니다. 명제를 만들 필요가 없습니다.

- `j…`: 판정. 이 수 자신의 판정을 인용한 문장이 하나 있어야 합니다.
- `c…`: 클레임. 그 클레임이 어떤 역할로 저장되는지는 기본 응답의 `as`에 있습니다(`claims`의 항목, `also`의 항목, `board`의 `leads_to`)(`result`, `mechanism`, `associated`, `comparison`, `line_fact`, `uncertain`, `not_the_case`). `associated`는 "함께 나온다"이지 원인이 아닙니다.
- `s…`: 엔진 라인. 그 수와 평가, 그리고 라인의 수순(8수까지, 기본 응답이 줄여 보였어도)을 말합니다.
- `b…`: 수 전 상황과 판의 변화 항목. 그 항목의 명제 전부를 말합니다.
- `x…`: 당신이 `explore`로 둔 라인.

핸들 하나는 명제 하나 이상으로 저장되고 한 해설의 명제 32개에 들어갑니다(`s`는 라인이 있으면 둘, 없으면 하나, `b`는 그 항목의 명제 수).

`f…`(facts의 기록)는 바로 인용하지 않습니다. 그 기록으로 명제를 만들어 인용하세요(`{{"id": "p1", "kind": "attack", ...}}`, 필드는 `definitions`에서 `proposition.<kind>`). 핸들과 직접 만든 명제를 한 문장에 함께 써도 됩니다. 직접 만든 명제의 `id`에는 콜론(`:`)을 쓰지 않습니다. 클레임 명제를 직접 만들 때 `use`를 생략하면 `as`의 값으로 저장되고, 쓰면 그 값이 허용되는지 검사합니다.

## 표기

- 문장의 수·평가치·칸·숫자는 인용한 근거에 있어야 합니다. 인용한 근거의 `proves`에 쓰인 수·칸·숫자는 문장에 쓸 수 있습니다. 라인의 수를 쓰려면 그 라인을, 판의 칸을 쓰려면 그 칸을 담은 근거를 인용하세요.
- 수는 SAN(17.Ne3, 17...Rxe3, 흑의 수는 ...Rxe3도 됨), 평가치는 백 기준(+0.38, -1.20)이고 부호는 숫자에 붙입니다. 숫자 앞에 대시를 두지 마세요. 검사를 피하려고 숫자를 한글로 쓰지 마세요. `en_passant`가 있으면 그 수는 앙파상입니다: SAN의 칸은 폰이 가는 빈 칸이고, 잡히는 폰은 그 옆 칸에 있습니다.
- 엔진 라인(`pv`)과 최선수에는 수 번호가 붙어 있습니다(`15.f5 Qxd4 16.Ne2`). 라인의 수를 말할 때는 번호를 붙인 SAN으로 쓰세요(17.O-O). '킹사이드 캐슬링'처럼 말로 바꾸거나 번호를 빼면 둔 수나 최선수로 읽히고, 검사도 그 수가 어디서 나왔는지 확인하지 못합니다. `judge_move`, `explore`, 명제의 수에도 번호를 붙여 써도 됩니다(번호는 그 국면과 맞아야 합니다).
- 둔 수의 엔진 라인(`lines.played`)은 그 수 뒤 엔진이 본 수순이지 실제 대국의 수순이 아닙니다. '실전 라인', '실제 수순', '실전에서는'이라고 쓰지 말고 '둔 수 뒤 엔진 라인에서는'이라고 쓰세요. 실제 대국에서 이어진 수는 대국의 다음 수(ply)에서 확인한 것만 씁니다.
- 용어: '교환'은 비슷한 값의 기물을 서로 잡을 때만 씁니다. 퀸을 룩과 바꾸면 '퀸 교환'이 아니라 '퀸을 내주고 룩을 얻는다'(또는 '룩으로 퀸을 얻는다')입니다. 한쪽만 잡는 것은 교환이 아닙니다.
- 클레임 읽기: ATTRIBUTED가 실패한 득실은 이 수의 성과가 아닙니다. `specific_line`은 그 라인에서만 성립합니다. 배치(이중 공격, 핀)는 통하는 전술이 아닙니다. INCONCLUSIVE·REFUTED는 이유로 쓰지 않습니다. 직접 둔 라인(by: agent)을 엔진의 라인이라고 쓰지 않습니다.

## 수 전 상황 (`board.scene`)

`scene`의 항목은 **상대의 직전 수**가 둔 쪽 기물에 만든 것입니다: 공격, 잡힐 수 있게 된 기물, 체크, 핀. 그리고 이 수 뒤 그것이 어떻게 됐는지(그 기물의 공격을 계속 받는지, 더는 받지 않는지)가 함께 나옵니다. 이 수가 답해야 했던 질문입니다. 장면을 "상대가 ○로 △를 노리자 □를 두었지만 …"처럼 흐름으로 쓸 때 씁니다.

## 판의 변화 (`board.changes`)와 클레임

`ply`와 `judge_move`의 답에 `board`가 있습니다. 모든 항목은 **수를 둔 쪽**(`mover`) 기준입니다.

- `changes`의 `kind`:
  - `threat`: 둔 쪽이 상대에게 만든 위협(체크, 이중 공격, 상대 기물 공격, 잡힐 수 있게 된 상대 기물, 핀). 그 수가 **노린 것**입니다. 걸린 기물은 상대의 것(`owner`)이고, 둔 쪽이 잃는 것이 아닙니다. 수 뒤에는 그 기물의 주인이 둘 차례입니다(잃는다는 값은 주인이 그 차례에 그 기물을 두고 다른 수를 둔다고 보고 셈한 것입니다).
  - `weakness`: 둔 쪽에 생긴 약점(잡힐 수 있게 된 둔 쪽 기물, 핀된 둔 쪽 기물). 그 수의 **대가**입니다. 잡힐 수 있는 기물에는 그 기물을 공격하는 상대 기물(`attack`)이 함께 나옵니다.
  - `lost_defence`: 둔 쪽 기물이 수 전에 받던 수비를 잃었고, 지금 상대가 그 기물을 공격합니다. 그 수의 **대가**입니다.
  - `held`: 수 전에도 수 뒤에도 잡힐 수 있는 둔 쪽 기물입니다. 그 기물을 공격하는 상대 기물이 수 전과 수 뒤에 함께 나옵니다(같은 기물이면 "같은 ○가 계속 노린다"를 말할 수 있습니다). 수 전에도 공격받던 기물이니 "이 수로 공격받게 됐다", "○가 공격하게 됐다"고 쓰지 않고, "수 전에도 공격받던 ○가 수 뒤에도 공격받는다"처럼 씁니다.
  - `structure`: 이 수 뒤 새로 패스트·고립·더블·백워드가 된 폰(`owner`는 그 폰의 주인). 패스트 폰은 주인에게, 나머지는 상대에게 좋습니다.
  - `file`: 이 수 뒤 폰 상태가 바뀐 파일(열린 파일: 폰 없음, 반열린 파일: 한쪽 폰만 있음 — "백 폰이 없는 반열린 파일"은 백 룩이 쓰기 좋은 파일).
- **언제부터**: `lost_defence`, `held`, 잡힐 수 있는 기물의 `weakness`와 `threat`에는 그 공격이 이 수 전에도 있었는지, 언제부터였는지가 나옵니다: "○ 뒤부터", "적어도 ○ 뒤부터", "시작 국면부터". 그 공격은 이 수로 새로 생긴 것이 아닙니다. 이 수로 바뀐 것(수비가 사라짐, 잡고 되잡기 셈)이 무엇인지도 그 항목에 있습니다. `lost_defence`에 "이 수로 새로 생겼다"가 있으면 그 공격은 이 수로 생긴 것입니다.
- "그 칸의 잡고 되잡기만 셈하면 N점을 잃는다": 그 칸에서 잡고 되잡는 것만 셈한 값입니다(각 쪽은 손해가 되면 멈춥니다). 엔진 라인이 아니고, 다른 수는 셈하지 않습니다. 잃는 쪽은 그 기물의 주인입니다.
- `leads_to`: 그 변화가 엔진 라인의 결과와 어떻게 이어지는지입니다. `link`가 `explains`(또는 `causes`)이면 "이 변화가 그 결과를 설명한다", `associated_with`이면 "그 결과와 함께 나온다"(원인이라고 쓰지 않음)입니다. 전술에는 `did`가 있습니다: `won`이면 그 전술로 물질을 얻었고, `configuration`이면 배치일 뿐입니다. 그 클레임은 `leads_to.claim` 핸들로 인용합니다.
- `same_reply`: 둔 수가 최선수가 아닐 때, 둔 수 뒤 엔진 라인의 상대 응수를 최선수 뒤에 둔 결과입니다. 상대의 수는 같고, 둔 쪽의 수는 엔진이 그 자리에서도 같은 수를 고를 때만 이어 둡니다. 같은 응수가 두 수 뒤에서 어떻게 다르게 끝나는지로 "왜 최선수가 나았는지"를 말할 수 있습니다. 이 수순은 Calliope가 비교하려고 둔 라인이고, 엔진이 고른 수는 그 끝의 최선수뿐입니다. 평가치는 백 기준입니다(+는 백, -는 흑이 좋음).
- `opponent_first`: 위협 항목에 붙습니다. 그 위협보다 상대가 먼저 둔 쪽 기물을 잡을 수 있습니다. 그 항목(값의 핸들)을 먼저 보세요.
- `played_material`: 물질 클레임이 INCONCLUSIVE이고 최선수 라인이 더 나을 때, 둔 수의 엔진 라인에서 둔 쪽의 물질 차이가 **수 전보다** 얼마나 나빠지는지 두 지점으로 보여 줍니다(결과, `consequence`). "엔진 라인에서 35.Rxb3 뒤 흑의 물질 차이는 수 전보다 9점 나빠진다"처럼 그 라인의 일로, 수 전과 비교해 씁니다. "수 전보다"를 빼고 "9점 뒤진다", "9점 우위"라고 쓰면 두 쪽의 물질 차이로 읽히는데, 수 전에 이미 차이가 있었다면 그것은 틀린 말입니다. 라인 뒤의 결과나 최선수와의 비교로도 쓰지 않습니다.

실수 수에서 `changes`는 걸린 점수가 큰 대가부터 놓입니다. 실수의 이유는 보통 `weakness`, `lost_defence`, `held`, `same_reply`에 있습니다. `threat`는 둔 쪽이 노린 것입니다.

클레임(`claims`):
- 엔진 라인 뒤쪽의 전술은 `relation`에 위치가 있습니다(`place.at`이 `line`이면 그 라인의 `ply`번째 수). 둔 수의 변화처럼 쓰지 마세요("엔진 라인에서 ○수 뒤 …").
- `also`: 같은 것을 다른 근거로 말하는 클레임들입니다(더 나은 수, 기물을 내줌, 메이트 허용). 맨 앞의 것이 가장 확실하고 구체적입니다. 각각의 `status`를 보세요.

각 항목과 클레임에는 다음이 있습니다.
- `proves`: 이 근거가 증명하는 것. 대괄호 안이 누구의 기물이고 누구에게 좋은지입니다. 이것보다 더 말하면 그것은 당신의 읽기입니다.
- `part`: 해설에서 맡는 역할. `reason`(이유), `consequence`(결과), `comparison`(다른 수가 더 낫다는 것), `grade`(판정), `line`(엔진 라인·평가).
- `owner`, `good_for`: 그 기물의 주인과, 그 변화가 유리한 쪽.

근거가 `proves`에서 말하지 않는 것을 그 근거의 내용처럼 쓰지 마세요. 특히 누구의 기물인지, 누가 잃고 얻는지를 바꾸지 않습니다. 같은 종류의 기물이 둘 나오면 칸으로 구별하세요.

기본 응답에 보이지 않는 것(반박된 클레임, 클레임의 findings, Calliope의 영어 문장)은 `not_shown`의 핸들로 `detail`을 부르거나 `view: "full"`로 봅니다.

문장에는 `states`를 둘 수 있습니다: 이 문장이 말하는 근거(`cites` 안에서, 핸들도 됨). 두었다면 그 근거(판정 제외)의 수나 칸을 하나 이상 문장에 씁니다.

## 분량

핵심 장면(블런더, 실수, 놓친 수, 브릴리언트·그레이트, 큰 손실, 흐름이 바뀐 수)은 5~9문장, 이유가 `inaccuracy`뿐인 장면은 3~5문장, 그 밖의 수는 2~3문장을 권합니다. 확인한 말이 적으면 짧게 쓰세요. 분량을 일반론으로 채우지 마세요.

## 제출

`submit_commentary`로 제출합니다(문장: `{{"text", "class": "sourced" | "interpretation", "cites": [핸들 또는 명제 id]}}`, 한 해설에 12문장까지). 여러 수는 `items`로 보냅니다. 장면이 많으면 4~5개씩 나눠 보내고, 장면마다 위의 분량을 지키세요. 거부되면 표시된 곳만 고쳐 다시 보냅니다. 저장한 뒤 `show_game`으로 판을 보여 주고, 채팅에는 짧은 요약만 씁니다.

대국 전체를 해설할 때는 중요한 장면(moments)을 모두 해설하고, 장면끼리 이어지게 하세요. 첫 장면의 해설에는 오프닝과 초반 구도를 2~3문장으로 넣고, 마지막 장면의 해설에는 대국이 어떻게 결정됐는지를 2~3문장으로 정리하세요(그 장면의 근거와 앞서 해설한 장면들의 판정·평가로).

용어는 `calliope://glossary/ko`를 따릅니다. 예산은 응답의 `budget_left`에 있고, 거부되면 `retry_after_seconds` 뒤에 다시 시도합니다. 게임 id는 계속 같습니다. 핸들이 만료되면 `ply`·`facts`·`explore`로 다시 읽습니다.

해설 문장은 한국어로 씁니다.
```

## Appendix B — rev. 3's wrong sentences at the fixed moments (blind judge, unblinded after)

N = an old attack read as new.

| Arm | Run | Moment | Sentence | Why (judge) |
| --- | --- | --- | --- | --- |
| rich | fourth-1 | 19.Nh6+ | N "…d4 폰을 지키던 수비도 사라졌고, 흑 퀸은 그 폰을 공격하게 됐습니다." | Qf6 attacked d4 since 15...Qf6 |
| rich | fourth-2 | 19.Nh6+ | N "…d4 폰을 지키던 기능도 사라져 흑 퀸의 표적이 됐습니다." | as above |
| story | fourth-2 | 19...Kh8 | N "킹이 g8을 떠나자 h6 나이트가 f7 폰을 공격하고, 백 퀸은 d7 나이트와 h5 폰을 노리게 됐습니다." | Nh6 on f7 and Qg4 on d7 since 19.Nh6+, on h5 since 18...h5 |
| v7 | fourth-1 | 19...Kh8 | N "킹을 피하자 백 퀸은 d7 나이트와 h5 폰을 공격하게 됐고, h6 나이트는 f7 폰을 공격하는 한편…" | as above |
| v7 | fourth-1 | 19...Kh8 | N "…흑은 그 나이트를 잡지 않고 킹을 옮겨 백 퀸의 공격을 허용했습니다." | Qg4 already hit d7; 20.Qxd7 follows 19...Qxh6 too |
| rich | fourth-1 | 19...Kh8 | N "킹이 g8을 떠난 뒤에는 그 나이트가 f7 폰도 공격하게 됐고…" | Nh6 on f7 since 19.Nh6+ |
| v7 | fourth-2 | 19...Kh8 | "…킹을 움직이면서 백에게 먼저 20.Qxd7을 둘 시간을 준다." | 20.Qxd7 follows the best move too |
| story | fourth-1 | 28...Bxg3 | "28...Bxg3는 흑 비숍 d5로 백 g3폰을 잡는 동시에…" | the d6 bishop captured |
| v7 | fourth-1 | 28...Bxg3 | "…흑 비숍 d5는 백 퀸의 공격에 노출된 상태로 남았습니다." | Qd7 did not attack d5 before (Bd6 blocked) |
| v7 | fresh-2 | 28...Qe6 | N "이 수 뒤에는 백의 g4 폰이 새로 공격받을 수 있게 됐고…" | f5 attacked g4 since 28.hxg4 |
| rich | fresh-2 | 31...Qf6 | N "…f5 폰은 수 뒤 백 폰 e4의 공격을 받게 됐습니다." | e4 attacked f5 since 30.e4 |
| story | fresh-2 | 38...Rxh5 | "…흑은 라인 전체에서 최소 룩 하나의 손실을 입습니다." | a rook for two pawns |
| v7 | fresh-1 | 38...Rxh5 | N "…백 나이트 e4가 그 폰을 공격하는 배치가 됐습니다." | Ne4 attacked d6 since 37.Ne4 |
| v7 | fresh-2 | 38...Rxh5 | "대신 38...fxg3 … 룩이 곧바로 잡히는 전개를 피할 수 있었고…" | the rook is taken at once there too |
| v7 | hung-2 | 34...Qb3 | N "…백 룩 c4가 그 폰을 공격하게 됐습니다." | Rc4 attacked c5 since 26.Kc1 |
| rich | rapid-1 | 26...Re8 | N "…백 비숍은 그 폰을 공격할 수 있게 됐다." | Bd5 attacked f7 since 24.Bxd5 |
| v7 | rapid-2 | 26...Re8 | N "…백 비숍 d5가 그 폰을 공격하게 됐습니다." | as above |
| v7 | rapid-1 | 26...Re8 | N "…백 비숍 d5가 그 폰을 공격하게 됩니다." | as above |
| rich | rapid-2 | 27...Nxf7 | N "…백의 e5룩이 그 룩을 공격했고…" | Re5 attacked e8 since 26...Re8 |
| rich | rapid-1 | 27...Nxf7 | N "백 룩 e5가 이제 흑 룩 e8을 공격하고…" | as above |
| v7 | rapid-2 | 27...Nxf7 | "엔진은 체크를 건 기물을 잡는 대신 27...Kxf7를 우선했습니다." | 27...Kxf7 also takes the checking bishop |
