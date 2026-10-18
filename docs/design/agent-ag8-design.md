# Agent — AG8-D design: the reasons with the ply, and what each one proves

Status: **rev. 1 — for independent review; owner decided Q1–Q4 as recommended (§10)**. Date: 2026-10-18. Base:
`main @ 392646a` (AG7 merged).
Inputs: [`agent-commentary-path.md`](agent-commentary-path.md) (the framing: the path end to end,
the owner's answers Q1–Q5, the trials §7 and §7.1), [`agent-mcp-design.md`](agent-mcp-design.md)
(AG-D: §4 propositions, §5.3 the sentence check, S6 the agent's lines),
[`agent-ag6-design.md`](agent-ag6-design.md) (AG6-D: the digest and its bound, §3),
[`agent-ag7-design.md`](agent-ag7-design.md) (AG7-D: the guide `commentary_ko_v2`, the acceptance
method §7).

An agent's commentary cites every sentence, but what it can cite is Calliope's verdict and the
engine's line; the reason a move is good or bad is rarely among it, and when it is (a fork, a mate)
it is said every time (framing §2). The trials of the framing note added the reasons to the digest
in three forms (D1, D2, D2′). The last of them found reasons no earlier guide or digest produced —
26...Re8 left f7 without the rook that defended it; 27...Nxf7 took the knight away from the rook it
defended — and its comparison "the same reply after the best move" gave the commentator's "why"
(9...a6 10.Nb5 axb5, -7.12). Its rules, though, raised refusals without preventing misreadings,
and the remaining errors were of one kind: whose piece is meant.

This design puts D2′'s data into the digest — what the move changed, by whose side, and the same
reply — with what each item proves, gives Calliope's claims the same reading, keeps the check as it
is but for two additions, and makes the rule that a key moment states a reason a note, not a
refusal.

## 0. What the trials showed (framing §7, §7.1)

luna (`openai/gpt-6-luna`), the deployment's model, three runs a game; Haiku 5.5 one run; three
games (the Opera Game, the rapid game of the fixtures, a game of two weak Stockfish settings never
annotated). Wrong sentences counted by hand at nine fixed moments.

| | today (AG7) | D2′ |
| --- | --- | --- |
| Sentences citing a reason, rapid game | 1.3 | 13.3 |
| Sentences citing a reason, Opera Game | 5.3 | 12.3 |
| Interpretations that state a reason or a result | 2.7 of 8.7 (rapid) | 6.3 of 6.3 (rapid) |
| Wrong sentences: Opera / rapid / new game | 0 / 0 / 2 | 2 / 0 / 0 (new game: one run after a fix) |
| Refused submissions a run (rapid) | 1.0 | 4.0 |
| Cost a game | $0.010 | $0.016 |

- `lost_defence` gave the reasons of 26...Re8 and 27...Nxf7 in every luna run, and of 31...Qf6
  (the queen on f6 blocks the rook's defence of f5) after its fix.
- The same reply, when shown with what it proves, was the "why" commentators give; cited about
  once or twice a game.
- The errors left were "whose piece": at 9...b5 the White bishop on c4 (which Black's pawn now
  attacks) and the Black bishop the engine line wins on b4 became one bishop in two of three runs.
  The second bishop came from a claim, whose meaning reached the agent only as Calliope's English
  `says`.
- D2's rules — every interpretation states a reason or a result; a moment with a reason states
  one — made the citations happen, not the reading; Haiku stopped after 2 of 8 moments after six
  refusals.
- The new search per digest cost about one second; the game's analysis is most of a run's time
  (2–2.7 s a ply, cold).

The samples are small (three runs a game); the acceptance trial (§9) measures again with more.

## 1. Decisions

| # | Decision |
| --- | --- |
| R1 | **`board` in the digest** of `ply` and `judge_move` (§2): what the move changed, by whose side — `threat`, `weakness`, `lost_defence` — and, for a move that is not the best, `same_reply`. Each item carries propositions that verify as given. `view: "full"` is unchanged. |
| R2 | **What an item proves, by side** (§3): every board item has `side` fields, a `part` and a Korean `proves` built from fixed templates (`board_remarks_ko_v1`), never longer than 240 characters. |
| R3 | **Claims read the same way** (§4): every claim in the digest gets a `part`; the claims of material and mate get a Korean `proves` from their findings, naming who gains or loses what. `says` stays. |
| R4 | **The same reply** (§5): the played line's next reply played after the best move; the mover's next move only when the engine plays it there too; one or two searches, charged to the session's search budget; a refused search leaves the item out with a reason. The line is Calliope's (`by: "calliope"`), not the agent's and not the engine's. |
| R5 | **What a sentence states** (§6): an optional `states` (the cited propositions the sentence says). When given, a stated proposition other than a judgement has one of its moves or squares written (S7). A Korean commentary's sentences contain Hangul (S8). The check is `commentary_check_v2`. |
| R6 | **Notes, not refusals** (§6.3): a commentary whose subject's digest held a reason and that states none, or an interpretation that states no reason or result, is accepted with a note. |
| R7 | **Korean refusals** (§7): a submission in Korean gets its violations' `problem` in Korean; the English text stays as `problem_en`. |
| R8 | **The guide** `commentary_ko_v3` (Appendix A): `commentary_ko_v2` with a section on `board`, parts, `proves` and `states`. `agent_guidance_v5`. |
| R9 | **Not changed** (§8): the propositions and their verification, the uses, S1–S6, the classes, the tools' arguments, the reasoner, the analysis, every cache key, the viewer. |

## 2. `board`

`board` is a digest field, after `claims`:

```json
"board": {
  "v": "board_v1",
  "mover": "black",
  "changes": [ {item}, ... ],
  "same_reply": {item} | {"not_computed": "<reason>"} | absent
}
```

The positions are the subject's: `before` and `after` the move (`{"ply": n, "at": ...}` for
`ply`; `{"from_root": [...]}` for `judge_move`'s judged path). The records are the facts tree's
(`pieces`, `patterns`, `exchange`, `status`), ensured for both positions; no search.

### 2.1 The items

| `kind` | When | Propositions | At most |
| --- | --- | --- | --- |
| `threat` | after the move: the side to move is in check; a double attack (`multi_target_attacks`) of the mover's that was not there before; an attack of a mover's piece on a piece of the other side (not the king; a pawn only if it can be won by exchange) not there before (not by an actor of a listed double attack); a piece of the other side that can be won by exchange (`exchange.gain` > 0) and could not before; an absolute pin of a piece of the other side's that was not there before | `check`, `pattern`, `attack`, `exposed`, `pin` (after) | 2 double attacks, 3 attacks, 3 exposed, 2 pins |
| `weakness` | after the move: a piece of the mover's (not the king) that can be won by exchange and could not before (the moved piece too); an absolute pin of a piece of the mover's that was not there before | `exposed`, `pin` (after) | 3 exposed, 2 pins |
| `lost_defence` | a piece of the mover's (not the king), on the same square with the same type before and after, that had a defender before the move it does not have after, and that a piece of the other side attacks after | `defence` (before: the lost defender), `attack` (after: the other side's attacker of the lowest value) | 3 |

Rules of `lost_defence` (framing §7.1's fix): defenders are compared by square; the moved piece is
no lost defender when it still defends the piece from its new square. A defence lost because the
move blocks a line (31...Qf6 between the rook on f8 and the pawn on f5) is one. Order: fewest
defenders minus attackers after first, then the higher piece value. The reasoner's own claims of
the same relation (`removed_defender_v2`) stay claims; the item is the board's fact, the claim is
the reasoner's verified explanation, and both may be cited.

Ordering of `changes`: for a move graded inaccuracy or worse, `lost_defence`, `weakness`,
`threat`; otherwise `threat`, `weakness`, `lost_defence`. Within a kind, the table's order.

Every item is verified by the server's own verifier before it is served; an item whose proposition
is refused is left out and counted in `not_shown.board_refused` (a fault, logged; the tests make it
zero on the fixtures).

### 2.2 The item's shape

```json
{
  "kind": "lost_defence",
  "part": "reason",
  "owner": "black",
  "good_for": "white",
  "proves": "[흑(둔 쪽)의 수비 상실] 26...Re8 전에는 흑 룩(f8)이 흑 폰(f7)을 지켰다. 수 뒤에는 그 수비가 없고, 백 비숍(d5)이 흑 폰(f7)을 공격한다 (수 뒤 f7을 지키는 기물 2개, 공격하는 백 기물 1개)",
  "propositions": [
    {"kind": "defence", "position": {"ply": 52, "at": "before"}, "defender": "f8", "defended": "f7"},
    {"kind": "attack", "position": {"ply": 52, "at": "after"}, "attacker": "d5", "target": "f7"}
  ]
}
```

- `owner`: the colour of the piece the item is about (the target, the exposed or pinned piece, the
  defended piece; for a check, the checked king's). `good_for`: the side the item favours — the
  mover for a `threat`, the other side for a `weakness` and a `lost_defence`.
- `propositions`: one or more, each a proposition as `submit_commentary` takes it but for its
  `id`, which the agent gives. A single-proposition item has the same list of one (not a second
  field, as in the trial).

### 2.3 Size

`board` counts toward the digest's 16,000-character bound (AG6-D §3.6). The trial's digests with
`board` were 4,300–7,400 characters. One step is added to the bound's steps, run first: `threat`
items beyond the first two are moved to `not_shown.board_left_out`, then `weakness`, then
`lost_defence` beyond the first two; `same_reply` is never left out by the bound (it is at most
one item of three propositions).

## 3. What an item proves

`proves` is built from fixed Korean templates, one per item kind and proposition kind
(`board_remarks_ko_v1`, in the definitions registry with its digest, so a commentary's
`agent_build` names it). Every template begins with a bracket naming the mover and whose the item
is:

| Kind | Bracket |
| --- | --- |
| `threat` | `[<mover>(둔 쪽)의 위협 — <other>의 기물이 걸린 것이고 <mover>이 잃는 것이 아니다]` |
| `weakness` | `[<mover>(둔 쪽)의 약점 — <mover>의 기물이 위험하다]` |
| `lost_defence` | `[<mover>(둔 쪽)의 수비 상실]` |
| `same_reply` | `[같은 수순 비교]` |

after which the template names each piece as colour, type and square (`백 비숍(c4)`), and the move
as numbered SAN. The text says what the propositions hold and nothing beyond: "can be won by
exchange (the side that captures gains 2 points by static exchange)", never "is lost". The
trial's texts (framing §7.1) are the templates' first version.

`part` is `reason` for every board item. The parts and what they mean are in the registry
(`remark.part`): `reason` (why the move is good or bad), `consequence` (what it leads to),
`comparison` (that another move is better), `grade` (the judgement), `line` (an engine line or
score), `other`.

## 4. Claims read the same way

Every claim in the digest gets `part`, by template (in the registry, `remark.part.<template>`):

| `part` | Templates |
| --- | --- |
| `reason` | `fork_v2`, `pin_v2`, `skewer_v2`, `discovery_v2`, `removed_defender_v2`, `left_en_prise_v2`, `newly_exposed_v1`, `prevents_v1`, `rescue_v1`, `only_move_v1`, `best_stops_reply_v1`, `capture_holds_v1`, `sacrifice_offer_v1`, `sacrifice_compensated_v1`, `sacrifice_sound_v1`, `piece_offer_v1`, `forcing_v1`, `check_answer_v1` |
| `consequence` | `material_gain_v3`, `material_loss_v2`, `mate_found_v1`, `mate_allowed_v1`, `mate_delivered_v1`, `mate_in_one_allowed_v1`, `mate_missed_v1`, `checks_draw_v1`, `checks_draw_missed_v1` |
| `comparison` | `better_alternative_v1`, `better_move_v1`, `missed_gain_v1` |

A template not in the table is `other`; a new template enters the table with its packet.

The consequence claims also get `proves`, from their findings, with the same brackets of side:

- material (`material_gain_v3`, `material_loss_v2`): `[<side>의 손실]` or `[<side>의 이득]`,
  the decisive event's victim and capturer by colour, type and square, the move that captures, the
  line's scope and the net points: "[흑(둔 쪽)의 손실] 엔진 라인에서 14.cxb4로 흑 비숍(b4)을
  잃는다 — 백 폰(c3)이 잡는다 (이 라인에서만, 라인 전체 순손실 2점 이상)". An ATTRIBUTED check
  that failed adds "(이 수의 성과가 아니라 라인의 사실)".
- mate (`mate_*`): who mates, in how many, in which line.

The other claims keep `says` only; their `proves` is a later packet's (§11).

## 5. The same reply

For a subject whose played move is not the best (`best` present, of another rank than `played`)
and whose played line has a reply (`played.pv[1]`):

1. `r1` = the reply. If `r1` is not legal after the best move, no item (`not_computed:
   "reply_illegal"`).
2. One search at `before + best + r1` (the session's search, AG-D §3.4). If its first line's move
   equals `played.pv[2]` and `played.pv[3]` is legal after it, a second search at
   `before + best + r1 + pv[2] + pv[3]`. The other side's moves are the played line's; the mover's
   move is kept only when the engine plays it there too — so the comparison never makes the mover
   play, after the best move, a move that loses there (framing §7.1: 26...Bd7 27.Bxf7+ is met by
   ...Nxf7, not by the played line's ...Kxf7).
3. The item: an `explored_line` of `[best, r1(, pv[2], pv[3])]` from `before`, an `engine_score`
   of the last search's first line, an `engine_score` of the played line. `proves`: "[같은 수순
   비교] 둔 수 <move> 뒤 엔진 라인의 <r…>를 최선수 <best> 뒤에 두면, 엔진의 최선은 <m>, 평가
   <s>(백 기준). 둔 수의 평가는 <p>. 상대의 수는 같고, 둔 쪽의 수는 엔진이 그 자리에서도 같은
   수를 고를 때만 이어 두었다".

The searches are charged to the session's search budget (AG4-D §3) like any other, and run under
the engine lock (AG6-D §4.3); a search the store holds is free, so reading the digest again costs
nothing. A refused search (`BudgetError`) leaves `same_reply: {"not_computed": "budget",
"retry_after_seconds": n}`; the digest is still served. A game whose position is over at either
point has no item (`not_computed: "game_over"`).

The line is Calliope's: its handle's address has `by: "calliope"`. A proposition citing it is
verified as an `explored_line` is today; the stored record says `by: "calliope"`, and its
sentences are not marked `by_agent` (AG-D S6 marks the agent's own lines). The guide says the line
is Calliope's comparison and only its last move is the engine's choice.

## 6. What a sentence states

### 6.1 `states`

A sentence may carry `states`: the ids of the cited propositions whose content it says. It is
optional. When given:

- S7a: every id in `states` is in the sentence's `cites`;
- S7b: for every stated proposition other than a judgement, the sentence writes at least one move
  or square that proposition allows (a token S3 accepts against that proposition alone).

A violation refuses the submission like S1–S6. The stored sentence keeps `states` (the result
schema's sentence object allows it; AR-D gets a note).

### 6.2 S8

A sentence of a `ko` commentary contains at least one Hangul syllable. (One D2 run wrote six of its
24 sentences in English; framing §7.)

### 6.3 Notes

An accepted commentary's answer may carry `notes` (Korean, each with its `rule`):

- `N-reason`: the subject's digest held a reason (a board item, or a claim of part `reason`) and no
  sentence states one;
- `N-reading`: an interpretation states nothing of part `reason` or `consequence`.

A note does not refuse; it tells the agent what a better commentary would do, and the trial
measures whether agents act on it (§9). The session remembers, per game and subject, whether the
digest it served held a reason; a subject whose digest was never served gets no `N-reason`.

`commentary_check_v2` names S1–S8 and the notes; a record accepted under it says so in `check`.

## 7. Korean refusals

When the submission's `language` is `ko`, every violation's `problem` is Korean, from fixed
templates per rule and problem (S1–S8, the subject, the size, a proposition's field); the English
text is kept as `problem_en`. Refusals outside `submit_commentary` (tool errors) stay English.

## 8. Not changed

The propositions and their verification, the uses and their rules, S1–S6, the sentence classes
and `SOURCE_VERIFIED`, the tools' arguments, `view: "full"`, `detail`, the reasoner and its
templates, the analysis and its cache keys, the job budget, the viewer. Calliope's `text` and
`says` stay in the digest.

## 9. Implementation (packet AG8) and acceptance

- `agent/board.py` (new): the items of §2, verified before they are served; the same reply of §5.
- `agent/remarks.py` (new): the templates of §3 and §4 (`board_remarks_ko_v1`), the parts.
- `agent/digest.py`: `board`, the claims' `part` and `proves`, the bound's new first step.
- `agent/session.py`: `board` for `ply` and `judge_move`; the comparison line's `by: "calliope"`;
  the per-subject reason record; S7, S8, the notes and the Korean problems in `_commentary`.
- `agent/propositions.py`: an `explored_line` of `by: "calliope"` is not the agent's.
- `agent/sentences.py`: S7, S8.
- `agent/prompts/commentary_ko_v3.md` (Appendix A); `build.PROMPTS =
  ("commentary_ko_v3", "check_ko_v1")`; v2 kept unserved; `GUIDANCE_VERSION =
  "agent_guidance_v5"`; the registry: `prompt.commentary_ko_v3`, `board.*`, `remark.part*`,
  `sentence.states`, `check.commentary_check_v2`; the tool description of `ply` names `board`.
- AG-D gains AM12 (S7, S8, the notes, `commentary_check_v2`, `by: "calliope"`).

Tests (fixtures: the Opera Game, the rapid game, the new game of the trial added as a fixture):

- 26...Re8: a `lost_defence` of f7 (f8 before, d5 after); 27...Nxf7: of e8 (d6 before, e5 after);
  31...Qf6: of f5 (f8 before, e4 after);
- 28...Qe6: no `lost_defence` of f5 or d6 (the queen still defends both from e6);
- 9...b5: `threat` items with `owner: "white"`, `good_for: "black"`; no `weakness`;
- 38...Rxh5: a `weakness` of h5 with `owner: "black"`;
- the same reply: 9...b5 → `[a6, Nb5]`, engine `axb5`; 26...Re8 → `[Bd7, Bxf7+]` and no second
  search (the engine's answer is `Nxf7`, the played line's `Kxf7`); a best move equal to the
  played one, an illegal reply, a game over: no item with the reason;
- a refused search gives `not_computed: "budget"`, the digest served; the second read is free;
- every served proposition verifies as given (all moments of the three fixtures);
- `proves` of `material_loss_v2` at 9...b5 names `흑 비숍(b4)` and `백 폰(c3)`;
- S7a, S7b, S8 refuse; `states` stored; `N-reason`, `N-reading` given and the commentary stored;
- a `ko` refusal's `problem` is Korean and `problem_en` English;
- the bound: a digest over 16,000 characters leaves `threat` items out first;
- the guidance pin `agent_guidance_v5`; the prompt and the resource render `commentary_ko_v3`.

Acceptance trial (in the implementation document), on the implementation's branch against
`main` (AG7), luna ×5 and Haiku ×2 per game and arm, four games — the three of the framing note
and one more of two weak engine settings (generated before the trial, its fixed moments chosen
from its `game_overview` moments before the first run). Fixed moments: Opera 9...b5, 13.Rxd7,
15.Bxd7+; rapid 20...c6, 26...Re8, 27...Nxf7; new game 28...Qe6, 31...Qf6, 38...Rxh5; the fourth
game's three. Each sentence of a fixed moment is marked as AG7-D §7 marks it. AG8 passes when, over
all luna runs:

1. wrong sentences at the fixed moments are no more than `main`'s, and none comes from a board
   item that is wrong (an item's `proves` false on the board is a failure by itself);
2. sentences citing a reason at the fixed moments are at least twice `main`'s;
3. every fixed moment is commented in at least 90% of the runs, and every Haiku run saves every
   moment Calliope lists;
4. refused submissions a run are at most `main`'s plus one;
5. no sentence is outside Korean;
6. the cost a game is at most 1.3 times `main`'s, and a `ply` digest takes at most 2 seconds more.

Reported, not passed or failed: the same reply's citations; the notes given and whether the next
submission acted on them; length.

## 10. Owner questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | `board` in `judge_move`'s digest too, or `ply` only? | Both: a judged alternative is read the same way; its cost is one or two searches the agent asked for by judging. |
| Q2 | The same reply's searches charged to the session's search budget? | Yes: the budget bounds the engine's load whoever asks; a refused search leaves only the item out. |
| Q3 | The key-moment rule and the reading rule as notes (R6), not refusals? | Notes: the trial's refusals cost moments (Haiku 2 of 8) without preventing misreadings. |
| Q4 | `proves` for the consequence claims now, the other claims later (§4)? | Yes: the trial's remaining error came from a material claim; the mechanism claims were read correctly. |

Owner (2026-10-18): Q1–Q4 as recommended.

## 11. Next

- `proves` for every claim template, and `says` replaced by it in the digest once the agents read
  `proves` alone.
- The other side's threats after the move (what the opponent can now do beyond the pieces it
  attacks): checks and mates available, from `status.checking_moves` and `mating_moves`.
- The viewer: a sentence's `states` shown as the evidence it says.

## Appendix A — `agent/prompts/commentary_ko_v3.md`

`commentary_ko_v2.md` (AG7-D Appendix A) byte for byte, then this section:

````markdown

## 판의 변화와 같은 수순 비교 (`board`), 그리고 문장이 말하는 근거 (`states`)

`ply`와 `judge_move`의 답에 `board`가 있습니다. 이유를 말할 재료입니다. 모든 항목은 **수를 둔 쪽**(`mover`) 기준입니다.

- `changes`의 `kind`:
  - `threat`: 둔 쪽이 상대에게 만든 위협(체크, 이중 공격, 상대 기물 공격, 교환으로 잡을 수 있게 된 상대 기물, 핀). 그 수가 **노린 것**입니다. 걸린 기물은 상대의 것(`owner`)이고, 둔 쪽이 잃는 것이 아닙니다.
  - `weakness`: 둔 쪽에 생긴 약점(교환으로 잃을 수 있게 된 둔 쪽 기물, 핀된 둔 쪽 기물). 그 수의 **대가**입니다.
  - `lost_defence`: 둔 쪽 기물이 수 전에 받던 수비를 잃었고, 지금 상대가 그 기물을 공격합니다. 그 수의 **대가**입니다.
- `same_reply`: 둔 수가 최선수가 아닐 때, 둔 수 뒤 엔진 라인의 상대 응수를 최선수 뒤에 둔 결과입니다. 상대의 수는 같고, 둔 쪽의 수는 엔진이 그 자리에서도 같은 수를 고를 때만 이어 둡니다. 같은 응수가 두 수 뒤에서 어떻게 다르게 끝나는지로 "왜 최선수가 나았는지"를 말할 수 있습니다. 이 수순은 Calliope가 비교하려고 둔 라인이고, 엔진이 고른 수는 그 끝의 최선수뿐입니다. 평가치는 백 기준입니다(+는 백, -는 흑이 좋음).

실수의 이유는 보통 `weakness`, `lost_defence`, `same_reply`에 있습니다. `threat`는 둔 쪽이 노린 것이라, 실수를 말할 때는 "노렸지만 …"처럼 대가와 함께 씁니다.

각 항목과 클레임에는 다음이 있습니다.
- `proves`: 이 근거가 증명하는 것. 대괄호 안이 누구의 기물이고 누구에게 좋은지입니다. 이것보다 더 말하면 그것은 당신의 읽기입니다. 결과 클레임(득실, 메이트)에도 `proves`가 있습니다.
- `part`: 해설에서 맡는 역할. `reason`(이유), `consequence`(결과), `comparison`(다른 수가 더 낫다는 것), `grade`(판정), `line`(엔진 라인·평가).
- `owner`, `good_for`: 그 기물의 주인과, 그 변화가 유리한 쪽.
- `propositions`: 그대로 검증을 통과하는 명제. 각각 `id`만 붙여 명제 목록에 넣으세요.

문장에는 `states`를 둘 수 있습니다: 이 문장이 말하는 근거의 명제 id(`cites` 안에서). 두었다면 그 근거(판정 제외)의 수나 칸을 하나 이상 문장에 씁니다.

좋은 해설은:
1. 이유(`reason`) 근거가 있는 수에서 그것을 말하는 문장을 하나 이상 둡니다. 어떤 이유를 고를지는 당신이 정합니다.
2. interpretation 문장에 이유나 결과 근거를 둡니다. 판정이나 "X가 더 나았다"만으로는 읽기가 아닙니다.
3. 근거가 `proves`에서 말하지 않는 것을 그 근거의 내용처럼 쓰지 않습니다. 특히 누구의 기물인지, 누가 잃고 얻는지를 바꾸지 않습니다. 같은 종류의 기물이 둘 나오면 칸으로 구별하세요.

제출이 받아들여져도 `notes`가 올 수 있습니다. 위의 1, 2를 지키지 않았다는 안내입니다. 다음 수의 해설에 반영하세요.

해설 문장은 한국어로 씁니다.

문장 예: `{{"text": "...", "class": "sourced", "cites": ["p1", "p3"], "states": ["p3"]}}`
````
