# Agent — ST-D design: the scene before the move, since when, and a guide that only says what the material is

Status: **rev. 1 — for independent review. Owner decisions taken (2026-10-29, §8).** Date: 2026-10-29.
Base: `main @ bf2ee80` (PF and its record merged). Owner's direction (2026-10-29): "모델에게 제약을 하기보다는
자유롭게 하는 쪽" — free the model rather than constrain it, and fix its errors by what it is given, not by
deterministic readings or checks; and, after the trial: "실험 결과를 문서에 포함해서 넣어줘 권장대로 진행해줘".
Inputs: the FR framing note (PR #130, `agent-free-commentary-framing.md` on `design/fr`, rev. 3 `162e99f`),
whose trials §0 restates in full so this document stands alone; [`agent-ag8-design.md`](agent-ag8-design.md)
(`board`, `proves`, the notes), [`agent-ms-design.md`](agent-ms-design.md) §6 (`board_v2`, `held`),
[`agent-bl-design.md`](agent-bl-design.md) (`board_v3`, held items from the facts),
[`agent-pw-implementation.md`](agent-pw-implementation.md) §4 and
[`agent-bl-implementation.md`](agent-bl-implementation.md) §4.1 (the error this packet targets, counted),
[`agent-lm-design.md`](agent-lm-design.md) (`commentary_ko_v7`), [`agent-cv4-design.md`](agent-cv4-design.md)
(the notes), issue #123.

The agent's commonest error today is an attack that held before the move written as made by it ("백 비숍
d5가 그 폰을 공격하게 됐습니다", when the bishop hit f7 since 24.Bxd5). The items it reads do not say what
held before the move, and a guide line against the reading did not stop it. This packet gives the agent
what held before — the scene the opponent's last move set, and since when an attack has stood — together
with the material of the FR trial's rich arm, and replaces the guide's method with a guide that only says
what each piece of material is.

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
| story (rev. 3) | rich's, plus two lines saying what the new items are | rich's, plus `scene` items and since-when on `lost_defence` and `held` (§2, §3) | off |

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
it):

| | v7 | rich | story |
| --- | ---: | ---: | ---: |
| Sentences | 121 | 119 | 112 |
| Wrong | 11 | 7 | 3 |
| … per 100 | 9.1 | 5.9 | 2.7 |
| … of them an old attack read as new | 7 | 7 | 1 |
| … other kinds | 4 | 0 | 2 |
| Doubtful | 11 | 3 | 1 |
| Mean score (1–5) | 2.67 | 2.79 | 2.96 |

- **The old attack read as new** is most of the errors once it is counted. Examples (by the judge, checked
  with python-chess):
  - 26...Re8: "백 비숍 d5가 그 폰을 공격하게 됐습니다" (Bd5 hit f7 since 24.Bxd5);
  - 34...Qb3: "백 룩 c4가 그 폰을 공격하게 됐습니다" (since 26.Kc1);
  - 19.Nh6+: "흑 퀸은 그 폰을 공격하게 됐습니다" (since 15...Qf6);
  - 27...Nxf7: "백 룩 e5가 이제 흑 룩 e8을 공격하고" (since 26...Re8);
  - 19...Kh8: "백 퀸은 d7 나이트와 h5 폰을 노리게 됐습니다" (since 19.Nh6+ and 18...h5).

  v7 and rich have 7 each; story 1, at 19...Kh8, where its `lost_defence` item says the f7 attack stood since
  19.Nh6+ and the sentence still says the king's move made it. v7's guide already has a line against this
  reading for `held` items ("수 전에도 공격받던 기물이니 '이 수로 공격받게 됐다'고 쓰지 않는다"); it did not
  stop it on `lost_defence` items, which never say what held before.
- **Other kinds.** v7's four are causes or lines misread (19...Kh8 "백에게 20.Qxd7을 둘 시간을 준다", when
  20.Qxd7 follows the best move too; 38...fxg3 said to save the rook; 27...Kxf7 said to come "instead of taking
  the checking piece"; 28...Bxg3 with a before/after state wrong). rich has none, as in rev. 1. story's two:
  the wrong bishop named at 28...Bxg3 (d5 for d6), and "최소 룩 하나의 손실" for a rook against two pawns.
- **Rev. 1 and rev. 3 agree.** Rev. 1's rich 0 and rev. 3's rich 7 are the same finding under two judges:
  rich has no other kind in either trial, and the kind it has is the one its material does not tell.
- **#123's moment.** story: "34...Qb3는 이미 f3 룩의 공격을 받던 흑 퀸을 b3로 옮겼지만, 공격을 벗어나지 못한
  블런더입니다". v7's second run reads the c5 attack as new.
- **What the scene changes.** The commentary tells the move against what came before: "20.Qf4 뒤 백 퀸은 흑의
  c7 폰과 f5 나이트를 함께 공격하고 있었습니다. 20...c6는 c폰을 공격에서 피하게 했지만, f5 나이트는 여전히
  퀸의 공격을 받았습니다." Reason-citing sentences come back near v7's (25.6 against 26.9) while the surface
  stays free.
- **Limits.** One judge, one model, 24 commentaries an arm: one sentence moves a rate by about 0.9 per 100.
  The old-attack difference (7, 7, 1) is the largest and has a cause one can point at; the score differences
  are small. Rev. 3 cost about $0.41; its records are in session `e058e396`'s scratchpad (`fr3`, the arm key
  apart in `fr3key`).

### 0.5 What follows

Information, not constraint, lowers the errors: the error comes from items that do not say what held before
the move, and saying it in the item cut it where a guide rule had not. The free guide keeps the surface
free; the material brings the reasons back. This packet takes story as it ran into `main` (D1–D5), and
extends since-when to the other items whose attack can predate the move (D2).

## 1. Decisions

| # | Decision | § |
| --- | --- | --- |
| D1 | `board` items `scene`: what the opponent's previous move began against the mover's pieces, and whether each still stands after the move | §2 |
| D2 | Since when, on every item whose attack can predate the move: `lost_defence`, `held`, `weakness`, and a `threat` of kind `exposed` | §3 |
| D3 | rich's material: `board` items `structure` and `file` (with proposition kinds `pawn` and `file`), and the digest's `others` with their numbered lines | §4 |
| D4 | The guide `commentary_ko_v8`: rich's free guide plus what the new items are; no rule added | §5 |
| D5 | The reading notes N-reason and N-reading off: `commentary_check_v6` | §6 |
| D6 | Versions, the registry, the size bounds | §7 |

What does not change: the fact engine, the reasoning layer (grades, labels, claims and their verification),
the result document, the server, the viewer, the tools and their names, the sentence check S1–S8 (a
sentence's moves, squares and numbers must be in what it cites), and every existing item's propositions.

## 2. D1 — the scene before the move (`scene`)

For a subject at the position after `p` plies of the game path (`p ≥ 1`; none at the root):

1. **Which relations.** `piece_relations.move_relations` at the previous move (nodes `p−1` → `p`, the move
   the opponent made), kept when `time == "began"`, `side == mover` (the relation bears on the mover's
   pieces), and `kind` is `attack`, `exposed`, `check`, `double_attack` or `absolute_pin`. An `attack` on a
   piece that also has an `exposed` relation there is dropped (said once, by the `exposed` item). The rest go
   through `limited(…, opponent)` and are ordered by `_stake` (largest first); at most `SCENE_ITEMS = 3`.
2. **What each says.** By kind, from the opponent's previous move `prev` (numbered SAN):
   - `attack`: "[수 전 상황: 상대의 직전 수가 만든 것] {prev} 뒤 {attacker}이 {target}을 공격하기 시작했다";
   - `double_attack`: "… {prev} 뒤 {actor}이 {t1}, {t2}을 동시에 공격하기 시작했다";
   - `exposed`: "… {prev} 뒤 {piece}은 잡힐 수 있게 됐다: {attacker}이 공격하고, 그 칸의 잡고 되잡기만 셈하면
     {mover}이 {gain}점을 잃는다" (the attacker is the exchange's first capture, as `weakness`);
   - `check`: "… {prev} 뒤 {mover} 킹이 체크를 받았다 ({squares}에서)";
   - `absolute_pin`: "… {prev} 뒤 {pinned}이 {pinner}에게 킹 쪽으로 핀됐다".
3. **Its fate after the move**, for each (attacker, target) pair of an attack, a double attack or an
   exposure, by piece identity at the position after the subject's move: "{move} 뒤: " then, per target,
   "{target}은 계속 공격받는다" (with "은 {square}로 옮겼지만" when it moved), "{target}은 더는 공격받지
   않는다" (with "은 {square}로 옮겨"), or "공격하던 기물을 잡았다" (the attacker was taken). A check and a
   pin get no fate (the move answered the check by rule; a pin's fate is the next scene's business).
4. **Propositions.** The relation at the position before the subject's move (`attack`, `pattern`
   `multi_target_attacks`, `exposed` with its attacker's `attack`, `check`, `pin`), and for each target still
   attacked, the `attack` at the position after. They verify like every board item (`Board._verify`); an
   item whose propositions are refused is no item and counts in `refused` as today.
5. **Tokens.** Citing the item allows what its `proves` shows (`board_tokens`) and the move `prev` (with its
   FEN before), which the text names.
6. **Place and part.** `kind: "scene"`, `part: "reason"`, `owner` the mover, `good_for` the opponent. Scene
   items come first in `changes`, before the move's own items. For `judge_move` of a move not played, the
   scene is the same: it is about the position before the move.
7. **Size.** `proves` up to `ITEM_CAP = 420` characters (§7).

## 3. D2 — since when

For an (attacker, target) pair named by an item, by piece identity along the game path: the attack holds
at a position when the attacker's attack set (python-chess `attacks`, as `pieces_v1`'s) holds the target's
square there.

1. **The rule.** If the attacker attacks the target at the position before the subject's move, walk back
   while it also attacked it at the position before that, at most `SINCE_PLIES = 16` plies; the first
   position of that unbroken run is after ply `k`, and the move of ply `k` (numbered SAN) is "since". At the
   root (`k = 0`) or when the attack does not hold before the move, there is no since.
2. **Which items, and what they add** (a sentence appended to the item's `proves`):
   - `lost_defence` (the attacker after the move and the defended piece): with since, "{attacker}의
     {defended} 공격은 이 수 전에도 있었다({k의 수} 뒤부터). {move}로 새로 생긴 것은 공격이 아니라 수비가
     사라진 것이다"; without, "{attacker}의 이 공격은 {move}로 새로 생겼다";
   - `held` (when one piece attacks it before and after, `first == then`): "{attacker}의 이 공격은 {k의 수}
     뒤부터 이어졌고, {move}는 그 공격을 피하지 못했다";
   - `weakness` of kind `exposed` (the attacker is the exchange's first capture after the move): with since,
     "{attacker}의 이 공격은 이 수 전에도 있었다({k의 수} 뒤부터). {move}로 바뀐 것은 공격이 아니라 그 칸의
     잡고 되잡기 셈이다"; without, nothing (the item already says "수 전에는 아니었다" of the exposure);
   - `threat` of kind `exposed` (an opponent piece the mover can now take; its attacker the first capture):
     with since, as `weakness`'s; without, nothing.

   The other `threat` kinds (`attack`, `double_attack`, `check`, `pin`) are relations that began with the move
   by `move_relations`' definition; their text already says "(수 전에는 아니었다)" and gets nothing.
3. **The proposition.** With since, the `attack` at the position after ply `k` (the squares there), added to
   the item's propositions, so citing the item cites it; the move of ply `k` is a token the item allows.
   Positions are `{"ply": k, "at": "after"}` in a ply's answer and `{"from_root": path[:k]}` in
   `judge_move`'s (as `Board.before`/`after` today).
4. **Size.** The appended sentence makes room under `ITEM_CAP` (§7); the item's first part keeps its own cap.

## 4. D3 — rich's material

As the trial's rich arm, unchanged:

1. **`structure` items**: for each pawn of the position after the move flagged `passed`, `isolated`,
   `doubled` or `backward` (`pawns_v1`) that was not so before (at its square before, following the moved
   pawn), grouped by colour and flag: "[{owner}의 폰, {good}에게 좋음] {move} 뒤 {owner} 폰 {squares}은
   {flag}이 됐다(수 전에는 아니었다)"; `good` is the owner for `passed`, the opponent otherwise. Propositions:
   `pawn` (square, flag, value true) after, and false before where the pawn existed before.
2. **`file` items**: each file whose state (`open`, `semi_open_white`, `semi_open_black`, `closed`) changed:
   "{move} 뒤 {file}파일은 {before}에서 {after}이 됐다". Propositions: `file` before and after.
3. **Two proposition kinds**, verified from `pawns_v1` at a position: `pawn` (`square`, `flag` in
   `passed|isolated|doubled|backward`, `value`), and `file` (`file` a–h, `state`). They take part in S3 as
   other position kinds (the square of a `pawn`; nothing for a `file` beyond its letter).
4. **`others`** in the digest: the other candidates (at most `OTHERS = 3`), each `{"ref", "move"` (numbered),
   `"score", "score_text", "pv"` (numbered, 6 plies)`}`, cited by their `s` handles, which the session already
   serves. `not_shown.others` goes (they are shown).

## 5. D4 — the guide `commentary_ko_v8`

The story arm's guide as it ran (rich's free guide, §0.1, with the two lines on `scene` and since-when),
with the `weakness`/`threat` since-when of D2 added to the second line. It states the one rule the server
holds (a statement about the board carries its evidence), how a scene can be told, what each material is,
the evidence strengths, the notation, the length advice and the submission. It adds no rule or prohibition
beyond v7's kept ones (forcedness words, whose piece). `commentary_ko_v7` stays as data, unserved (as v1–v6).

## 6. D5 — the notes off

`_notes` (N-reason, N-reading; AG8-D §6.4, CV4-D §2) gives none: `commentary_check_v6` is v5 without the
notes. All rich and story runs ran with the notes off. The guide no longer mentions `notes`. `states_items`
and the refusals S1–S8 are unchanged.

## 7. D6 — versions, registry, bounds

- `board_v4` (scene items; since-when; `structure`, `file`), `commentary_ko_v8`, `agent_guidance_v11`,
  `commentary_check_v6`; proposition kinds `pawn`, `file` in the registry (`agent/definitions.py`), with
  `board_v4`'s item kinds.
- `remarks.PROVES_CAP` (240) stays for one remark and for claims' `proves` (a claim's `proves` too long is
  none, MS-b N3). A board item's `proves` with an appended since sentence or a scene's fate is capped at
  `ITEM_CAP = 420`.
- The digest's bound (`DIGEST_LIMIT`, 16,000 characters) and its steps are unchanged; scene and structure
  items are board items for step 0. The implementation reports how often step 0 cut an item on the four
  games' every ply, against `main`.

## 8. Owner decisions (2026-10-29, as recommended)

| # | Question | Decision |
| --- | --- | --- |
| O1 | Since-when on `lost_defence` and `held` only (as the trial), or also on `weakness` and `threat`? | Also on `weakness` and on `threat` of kind `exposed` (D2); the other threat kinds began with the move by definition |
| O2 | The reading notes: off (as the trial) or kept? | Off (D5) |
| O3 | Scene items a move | At most 3 (as the trial) |

## 9. Implementation (packet ST), tests, acceptance

**Code** (`calliope.agent` only): `board.py` (scene, since-when, structure, file; `ITEM_CAP`), `digest.py`
(`others`), `propositions.py` (`pawn`, `file`), `remarks.py` (texts), `session.py` (`_notes` off, `CHECK`),
`definitions.py`, `build.py`/`server.py` (the guide v8), `prompts/commentary_ko_v8.md`.

**Tests.**
1. Scene: the opponent's previous move's began relations at #123's 34...Qb3 (the queen made capturable by
   34.Rf3, still attacked on b3; the double attack on e3 and f7), 26...Re8 (the double attack by 26.Qh6, f8
   no longer attacked), 27...Nxf7 (the attacker captured); no scene at ply 1; the attack dropped when an
   exposure says it; at most three; the same scene for `judge_move` of another move at that position.
2. Since-when: 34...Qb3's `lost_defence` (Rc4 on c5 since 26.Kc1) and `held` (Rf3 since 34.Rf3); 26...Re8's
   `lost_defence` (Bd5 on f7 since 24.Bxd5); an attack that began with the move says so; the walk-back bound;
   the root; a `weakness` whose attacker attacked before (and one whose did not); a `threat` of kind exposed.
3. Every item's propositions verify; the since and scene moves are allowed tokens when the item is cited and
   only then; a sentence citing a scene item and writing `prev` passes S3.
4. `pawn` and `file`: verification, refusal of a wrong flag or state, a square without a pawn.
5. `others` in the digest; `not_shown` without them.
6. `_notes` gives none; the check version; the registry entries; the guide served at its URI.
7. The golden answers updated where the digest changes (stated per file).

**Acceptance.**
1. **The replay.** Every commentary stored by the FR rev. 3 runs and by LM's and PW's trials is checked again
   by `commentary_check_v6` against freshly built answers: none refused that v5 accepted, apart from what the
   new digest no longer serves (stated if any).
2. **The bound.** Over the four games' every ply: digest sizes, and step 0's cuts against `main` (§7).
3. **A short trial** (luna ×2 a game on the four games, the same setup): blind, mixed with rev. 3's v7 and story
   commentaries at the fixed moments, one fresh-context judge. Met when ST's wrong sentences per 100 are no
   more than v7's in that judging, and its old attacks read as new no more than story's plus one.

## 10. Not in this packet, and not chosen

- **A check on the reading** (refuse or note a sentence that says "새로", "공격하게 됐다" of an attack that
  held before): not chosen, by the owner's direction (2026-10-29): errors are fixed by what the agent is given.
- **E2's other items** (a natural move's refutation, the opponent's threat after the move, the king's
  shelter) and **E3** (a stronger writer at key moments): later packets (FR §5).
- **Issue #123's candidates 3 and 5** (settling with a size; binding the threat's move and the reply to the
  moment): not here. The scene states the threat's move as information, not as a moment.
- **The FR note** (PR #130) stays a framing note; its trials are restated in §0.
