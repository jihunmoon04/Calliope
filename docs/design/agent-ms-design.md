# Agent MS-D — one meaning once

Status: **rev. 1 — for independent review**. Date: 2026-10-18. Base: `main @ c9cd4e8` (MS framing
merged).
Framing: [`agent-ms-framing.md`](agent-ms-framing.md) (rev. 3; owner Q1–Q4 as recommended).
Builds on: [`agent-ag8-design.md`](agent-ag8-design.md) (AG8-D: `board`, `part`, `proves`, S7, S8),
[`agent-ag6-design.md`](agent-ag6-design.md) (AG6-D: the digest, its bound, handles behind
`detail`), [`agent-mcp-design.md`](agent-mcp-design.md) (AG-D §4: propositions and uses, §5.3 the
sentence check), R2-D §3.7–§3.11 (the relation and sacrifice templates), R4-D §2.1 (the reasoning
build).

## 0. What the owner decided

| | Decision (2026-10-18) |
| --- | --- |
| Direction | Keep every kind of data; put together what says the same thing twice; cut structure that is not needed. Data today's move commentary does not use leaves the default digest, not the system |
| Rounds | Kept (framing §3); a mechanism's reads requested at once |
| Q1 | A relation lives in the reasoning layer, the fact apart from a claim's causal reading; `board` is a view of it |
| Q2 | `holds` only for the pieces a claim is about; the general setting later |
| Q3 | The simplification agreed after AG8 is in MS; the server derives the roles a claim may take before the agent stops writing `use` (never `part` for `use`) |
| Q4 | Every template and label rule kept; a group shown once in the digest, each member's evidence reachable |
| §4 | `sacrifice_compensated` decides a played mate against an open keeping line by that line's score, and says so |

## 1. Requirements

| # | Requirement | § |
| --- | --- | --- |
| R1 | A mechanism (`fork_v2`, `pin_v2`, `skewer_v2`, `discovery_v2`) requests its `reads` on every node of its scan at once | §2 |
| R2 | `sacrifice_compensated_v2`: a played mate over an open keeping line with a non-mate score; the finding names the basis | §3 |
| R3 | **Piece relations** in the reasoning layer: kind, pieces by identity, place, time (`began`, `held`, `ended`); the relations at a move derived from the facts | §4 |
| R4 | A relation claim's **link**: the relation it states, the consequence it comes with (`explains`, `causes`, `associated_with`), whether the relation did anything | §5 |
| R5 | `board_v2`: a view of the move's relations; an item a claim links carries the link, and that claim is not listed again; a `held` item for a claim's piece | §6 |
| R6 | Claim **groups** shown once (a better move; the move offers material; the move allows a mate) | §7 |
| R7 | A smaller default digest: `proves` for every served claim, in place of `says` and `findings`; `text`, `refuted` and `lines.others` behind `view: "full"` and `detail` | §8 |
| R8 | Citing by handle; the server derives a cited claim's roles; an explicit `use` still accepted and checked as today | §9 |
| R9 | Guide `commentary_ko_v4`, `agent_guidance_v6`, the registry, the bound | §10 |
| R10 | The trial again (MS7) | §13 |

Packets: MS-a (R1–R4), MS-b (R5–R7), MS-c (R8–R10), each reviewed (§14).

## 2. R1 — a mechanism's reads at once

`_Mechanism.verify` (`reasoning/catalogue/mechanisms.py`) today stops at the first step whose
records are missing and asks for that node's `reads`. It now first collects, over every step of
`_steps(scene)`, the `(family, node + offset)` of `reads` whose record is missing, and returns
`NEEDS_EVIDENCE` with all of them; when none is missing it scans as today. A candidate's own check
(`pieces`, `exchange` on one node) is unchanged.

The verdicts are those of today when no limit is reached (framing §3.3: 88 plies, one changed —
11.Bxb5+ decided where today it closes at the round limit). The four templates' `version` becomes
`"2"`: the hypothesis id and the reasoning build change, so every cached analysis is recomputed
when it is next read (R4-D §2.1; no cache migration).

## 3. R2 — `sacrifice_compensated_v2`

`sacrifice_compensated_v1` is renamed `sacrifice_compensated_v2` (its rule changes). Rule 3 today:
the played line's outcome is a mate for the mover and every keeping line's outcome is decided and
strictly below it. Rule 3 now: the played outcome is a mate for the mover, and every keeping line
is either decided and strictly below it, or open (`OPEN`) with an engine score that is no mate for
the mover. When at least one keeping line was taken by its score, the finding's kind is the new
`CompensationKind.MATE_OVER_SCORES` (`"mate_over_scores"`), otherwise `MATE` as today. Rules 4–6
are unchanged: a material return still needs every line decided (13.Rxd7 stays INCONCLUSIVE).

`CompensationKind` gains the value (the types digest and the build change, as in §2). The planner's
`SACRIFICES`, the renderer's key, the definitions registry (`sacrifice_compensated_v2`, and the
kind's statement: "a mate against keeping lines whose material is open, by their engine scores —
an evaluation, not a decided outcome"), `remarks.TEMPLATE_PARTS` and the phrasebook follow the name.
Framing §4: at 16.Qb8+ the open line scores +1.27 (no mate), so the claim is SUPPORTED with
`mate_over_scores`.

## 4. R3 — piece relations

### 4.1 The record

A new module `calliope.reasoning.piece_relations` (format `piece_relations_v1`):

```
PieceRelation:
  kind: attack | defence | exposed | pin | double_attack | check
  pieces: the participants by PieceId and their square at the relation's node
          attack (attacker, target); defence (defender, defended); exposed (piece, gain);
          pin (pinned, pinner); double_attack (actor, targets); check (checkers)
  place: {"at": "move"} | {"at": "line", "line": <the claim's line: rank>, "ply": k}
  time: began | held | ended
```

`place: move` is the subject's move: `began` holds after it and not before; `held` before and
after; `ended` before and not after. `place: line` is ply `k` (from 1) of an engine line from the
subject's position; its time is `began` at that ply (a mechanism's node, §5). The relation of a
pair of pieces is compared by identity (AG8 rev. 3).

### 4.2 The relations at a move

`move_relations(view, parent, child, mover)` derives, from the fact tree's records at the subject's
two nodes, what AG8's `board` derives today — the same rules and limits, moved out of the agent
layer (AG8-D §2.1, AG8 implementation §2 items 6 and 9):

| Time | Kind | From |
| --- | --- | --- |
| began | check | `status` after |
| began | double_attack (the mover's, none before) | `pattern_delta.multi_target_attacks` |
| began | attack (the mover's on the other side; a pawn only if exposed; not by a listed double attack's actor) | `pieces` before and after, by identity |
| began | exposed (either side) | `exchange` gain before and after, by identity |
| began | pin (either side) | `pieces.absolutely_pinned` before and after, by identity |
| ended | defence (of a mover's piece that stayed and is attacked) | `pattern_delta.defences_ended_under_attack` (`defender_moved`, `line_blocked`) |
| held | exposed (only a piece a claim names, §5) | `exchange` gain before and after |

The function reads records (`PiecesFacts`, `PatternsFacts`, `PatternDeltaFacts`, `ExchangeFacts`,
`StatusFacts`) and returns relations with the pieces' squares; it does not verify propositions and
knows no side's `owner`. It is a function of the facts, not of an analysis: nothing is stored with
an analysis and no cached analysis changes for it.

## 5. R4 — a relation claim's link

A claim of `removed_defender_v2`, `newly_exposed_v1`, `left_en_prise_v2`, `fork_v2`, `pin_v2`,
`skewer_v2` or `discovery_v2` that is SUPPORTED has a `relation` and a `link`, read by
`piece_relations.claim_relation(analysis, claim)` from the claim's finding and the claim graph
when a digest is built. They are not stored with the analysis and not added to the result document
(`calliope.results`, the HTTP server's answers): no cached analysis and no result format changes for
them.

| Template | Relation (from its finding) | Place, time |
| --- | --- | --- |
| `removed_defender_v2` | defence (`DefenceFinding`: defender, defended) | move, ended |
| `newly_exposed_v1` | exposed (`HangingFinding.piece`) | move, began |
| `left_en_prise_v2` | exposed (`HangingFinding.piece`) | move, held |
| `fork_v2` | double_attack (`MechanismFinding`: actor, targets) | the finding's node: move (began) when it is the subject's child, else line ply k |
| `pin_v2`, `skewer_v2` | pin / the line's front and back (`MechanismFinding`) | as `fork_v2` |
| `discovery_v2` | attack (`MechanismFinding`: actor → targets) | as `fork_v2` |

`link`: `{"kind": explains | causes | associated_with, "to": <the consequence claim's id>}` from
the claim graph's relation to its consequence (the strongest when several), and for a mechanism
`"did": "won" | "configuration"` — `won` when its REALIZED check passed (the claim explains the
material), `configuration` when it is only associated with it. The claim record and its verdict
are unchanged.

Framing §2.3: of the eleven supported relation claims in 233 plies, five are relations at the move
(the board's), six in the engine line or held.

## 6. R5 — `board_v2`, a view

`board` (AG8-D §2) becomes `board_v2`, built from `move_relations` (§4.2) instead of the agent's
own reading; `owner`, `good_for`, `part`, `proves` and the propositions are as in `board_v1`, the
items' kinds (`threat`, `weakness`, `lost_defence`) and limits too. New:

1. Every item has a `ref`, a handle of the new kind `b` (a board item: the item's canonical
   propositions, its subject and the facts tree's revision; `detail` returns it).
2. **One relation once.** When a supported relation claim's relation (§5) is at the move and is the
   item's — the same kind, the same pieces by identity, the same time — the item carries
   `"leads_to": {"claim": <ref>, "template", "link": <kind>, "to": <the consequence's ref>,
   "did"?}` and its `proves` gains the link's sentence (§8.2); that claim is **not** listed in
   `claims` (its ref is citable as before, and `detail` shows it).
3. **Held.** A `left_en_prise_v2` claim's piece becomes an item of kind `held` (`owner`: the
   mover, `good_for`: the other side, `part: reason`; propositions `exposed` before and `exposed`
   after) with its `leads_to`; nothing else is `held` (Q2).
4. A relation claim whose relation is in the engine line stays in `claims`, with its `relation`
   (place `line`, ply `k`) and `link` shown.

`board_v2`'s order and the bound's step 0 are AG8's; a `held` item and an item with `leads_to` are
kept by step 0 before the others of their kind.

## 7. R6 — groups shown once

| Group | Members | Shown | Why that one |
| --- | --- | --- | --- |
| a better move | `better_move_v1`, `missed_gain_v1`, `better_alternative_v1` | the first present, in that order | it names the most: the consequence avoided, then the margin, then the judgement |
| the move offers material | `piece_offer_v1`, `sacrifice_offer_v1` | `piece_offer_v1` | it names the piece and how it was offered |
| the move allows a mate | `mate_allowed_v1`, `mate_in_one_allowed_v1` | `mate_allowed_v1` | it gives the line and the mate's length |

In `claims`, the shown member's entry gains `"also": [{"ref", "template", "proves"}]` for the others
present; they are not listed apart. Every member stays a claim, cites as today and keeps its label
rules (`missed_gain_v1` for MISS, `piece_offer_v1` for the brilliant rule). `sacrifice_sound_v1`
(an evaluation) and `sacrifice_compensated_v2` (a concrete return) are not members: they answer
other questions and are listed as today.

## 8. R7 — a smaller default digest

### 8.1 What leaves the default

| Field | Today | Default digest | Where it stays |
| --- | --- | --- | --- |
| `claims[].says` | the claim's English sentence | removed | `view: "full"` (`segments`) |
| `claims[].findings` | the findings without positions | removed for a claim with `proves` (§8.2: every served one) | `detail` of the claim's ref; `view: "full"` |
| `text` | Calliope's English text | removed | `view: "full"` |
| `refuted` | REFUTED claims by template and ref | `not_shown.counts.refuted` (a number) | `view: "full"`; `detail` by ref |
| `lines.others` | up to three other candidates | `not_shown.counts.others` | `view: "full"`; `detail` by ref |

On the trial's 199 digests this takes a digest from 5,028 characters on average to about 3,543
(0.70), counting 110 characters of `proves` for each claim that has none today.

### 8.2 `proves` for every served claim

`board_remarks_ko_v1` becomes `board_remarks_ko_v2`: material and mate claims as in AG8-D §4, and
a `proves` for every other template, from its findings, in the same form (a bracket, then the
moves and pieces by colour, type and square; at most 240 characters):

| Template | `proves` |
| --- | --- |
| `better_move_v1` | `[비교] {move} 대신 {best}이면 엔진 라인에서 {the consequence avoided: 물질 손실 / 메이트 허용}이 없다` |
| `missed_gain_v1` | `[비교] {best}가 {move}보다 기대 점수로 {loss ÷ 20}%p 앞선다` |
| `better_alternative_v1` | `[비교] 엔진의 최선은 {best}였다` |
| `best_stops_reply_v1` | `[비교] {best}는 상대의 {reply}를 막는다 ({piece} {square})` |
| `forcing_v1` | `[강제] {move} 뒤 상대의 합법 수는 {replies}개{, 체크}` |
| `check_answer_v1` | `[체크 대응] {move}는 {checkers}의 체크에 대한 응수다 (합법 수 {legal_moves}개)` |
| `only_move_v1` | `[유일한 수] 엔진의 2순위 수는 기대 점수로 {loss ÷ 20}%p 이상 나쁘다` |
| `prevents_v1` | `[막음] {move}는 {메이트 / 물질 손실}을 막는다 (다른 수 {alternatives}개)` |
| `rescue_v1` | `[구출] {move}로 {piece}는 더 이상 잡히지 않는다 (수 전 {exposure_before}점 노출)` |
| `capture_holds_v1` | `[받아도 됨] {piece}를 잡으면 {reply}로 {둔 쪽}이 버틴다` |
| `piece_offer_v1` | `[{mover}(둔 쪽)의 제공] {move}로 {piece}를 내준다 ({offer}점{, 잡으며})` |
| `sacrifice_offer_v1` | `[{mover}(둔 쪽)의 희생] 엔진 라인에서 {amount}점을 내준다` |
| `sacrifice_sound_v1` | `[희생의 평가] 엔진은 희생 뒤를 {둔 쪽}에 손해로 보지 않는다 (평가일 뿐 대가의 증명은 아니다)` |
| `sacrifice_compensated_v2` | `[희생의 대가] {메이트 / 물질 회수}{ — 다른 라인은 엔진 평가로 비교}` |
| `removed_defender_v2`, `newly_exposed_v1`, `left_en_prise_v2` | the relation's sentence (`board_remarks`' `lost_defence` / `exposed` forms) and the link: `… 그 결과 {consequence}{을 설명한다 / 와 함께 나온다}` |
| `fork_v2`, `pin_v2`, `skewer_v2`, `discovery_v2` | the relation at its place (`엔진 라인 {k}수째 {move} 뒤 …`) and `{물질을 얻었다 / 배치일 뿐 물질과 함께 나온다}` |
| `checks_draw_v1`, `checks_draw_missed_v1` | `[무승부] {checker}의 연속 체크 {checks}번으로 {반복 / 50수}` |
| `mate_*`, `material_*` | AG8-D §4 |

A claim whose findings lack what its row needs gets none (and keeps `findings` in the digest), as
AG8 does for material and mate claims. The texts say what the findings hold and nothing more: no
engine score a finding does not carry (the lines' scores stay in `lines`).

## 9. R8 — citing by handle; the server derives a claim's roles

### 9.1 Cites

A sentence's `cites` may name a **handle** served for the subject as well as a proposition's id. A
cited handle stands for these propositions, built and verified by the server as if the agent had
written them:

| Handle | Propositions |
| --- | --- |
| `j` (the subject's judgement) | `judgement` |
| `c` (a claim) | `claim` with the derived `use` (§9.2) |
| `s` (a line of the digest) | `engine_score` (its move, its score) and `engine_line` (the moves the digest shows) |
| `b` (a board item, §6) | every proposition of the item |
| `x` (an explored line) | `explored_line` (its moves) |

`propositions` may then be empty; a submission may mix both. `states` (AG8-D §6.1) may name a
handle; a handle states the item whole (S7). S3 reads the moves, squares, scores and numbers of the
propositions a handle stands for. The stored commentary keeps the built propositions (each `id` the
handle), so a stored record reads as today.

### 9.2 The roles of a claim

`Verifier._use` stays the rule. When a claim is cited by handle, or a `claim` proposition has no
`use`, the server takes the first of the uses `_use` allows, in this order: `result`, `mechanism`,
`associated`, `comparison`, `line_fact`, `uncertain`, `not_the_case`. The stored proposition has
that `use` and `"use_by": "server"`. A claim no use allows is refused as today (`expected`: none).
A `claim` proposition with an explicit `use` is checked as today (`use_by` absent). So the agent
writes less, and every check `use` made is still made — by the server, on the claim's verdict,
relations and checks (review B2).

The digest shows the derived use of each listed claim as `"as"` (beside `part`), so the agent
knows what the claim will be stored as before it writes the sentence.

## 10. R9 — guide, registry, bound

- `prompt.commentary_ko_v4` (from v3): cite by handle first; read `proves` (no `says`, no `text`);
  `board` items' `leads_to` ("이 변화가 그 결과로 이어졌다"는 `explains`일 때만, `associated_with`는
  "함께 나왔다"); `held`; a group's `also`; a relation in the engine line said with its place;
  `as`. `agent_guidance_v6`; `commentary_check_v3` (handles in `cites` and `states`).
- Registry: `board.board_v2`, `board.held`, `board.leads_to`, `piece_relations_v1`,
  `relation.time`, `relation.place`, `claim.link`, `claim.as`, `claim.group`, `board_remarks_ko_v2`,
  `cite.handle`, `use.by_server`, `sacrifice_compensated_v2` and `mate_over_scores`;
  `prompt.commentary_ko_v4` in place of v3.
- The bound (AG6-D §3.6): step 0 as §6; the steps `findings` and `text` apply only to what is
  still shown; a new step after `board` moves a group's `also` to `detail` first.

## 11. What stays

Every fact family; every template's verdict but the five of §2–§3; every label rule; the claim
graph; the result document and `view: "full"` (but `board`, which only digests carry); explicit
propositions and `use`; S1–S8.

## 12. Tests

- R1: a scan with missing records at two nodes asks for both at once; 11.Bxb5+ of the Opera Game
  decided within three rounds (Stockfish, gated); the 33 plies' verdicts unchanged elsewhere.
- R2: 16.Qb8+ SUPPORTED with `mate_over_scores`; 13.Rxd7 INCONCLUSIVE; a played mate against an
  open line whose score is a mate for the other side is not decided.
- R3/R5: `move_relations` gives AG8's board items at the seven fixed moments of
  `test_board_stockfish.py`, and the synthetic cases of AG8 rev. 3–4 (a relation that moved with
  its piece is no change; a double attack that gained a target is none); `board_v2` equal to
  `board_v1` there but for `ref`.
- R4/R5: 31...Qf6's `lost_defence` f8→f5 carries `removed_defender_v2`'s link and the claim is not
  listed; 38...Rxh5's weakness h5 `newly_exposed_v1`'s; 13.Rxd7's double attack `fork_v2`'s with
  `did: won`; 31...Qf6's `held` f5 for `left_en_prise_v2`; 6.Bc4's `pin_v2` stays a claim with place
  line ply 2.
- R6: a digest with two members of a group shows one with `also`; each member's ref still cites.
- R7: the removed fields absent by default, present in `view: "full"`; `detail` of a refuted claim
  and of another candidate; `proves` for every template where its findings allow.
- R8: a sentence citing `j`, `c`, `s`, `b` handles with no propositions is accepted and stored with
  the built propositions; a derived `use` is the first `_use` allows; an associated claim is stored
  `associated`, never `mechanism`; an explicit wrong `use` refused as today; S3 against a handle's
  moves; S7 with a handle in `states`.
- R9: the guidance pin `agent_guidance_v6`; the registry's ids.

## 13. R10 — the trial (MS7)

As AG8's (AG8 implementation §4): luna ×5 and Haiku ×2 on the four games, against `main` (AG8),
and the framing's measurements (`measure.py`, the pairs) on the new records. Criteria:

1. wrong sentences at the fixed moments no more than AG8's;
2. sentences citing a reason at the fixed moments no fewer than AG8's less 10%;
3. every fixed moment saved in 90% of the runs, Haiku every moment;
4. a `ply` digest's characters 25% fewer or more (median);
5. refused submissions no more than AG8's plus one; no sentence outside Korean;
6. cost no more than AG8's; a digest built within AG8's plus 0.5 s.

Reported: the share of cites by handle; the derived uses; how often `leads_to`, `held` and `also`
are cited.

## 14. Packets

| Packet | Contents | Changes the reasoning build |
| --- | --- | --- |
| MS-a | R1, R2, R3 (`piece_relations`, no agent change), R4 (the claim record's `relation`, `link`) | yes (§2, §3) |
| MS-b | R5 (`board_v2` on R3, `b` handles), R6, R7 | no |
| MS-c | R8, R9, R10 | no |

Each packet: implementation, tests, independent review; MS-c ends with the trial.

## 15. Owner questions

1. **`text` out of the default** (§8.1): Calliope's English text was read (framing §2.2, 0.10) but
   is English; `proves` replaces it in Korean. Out of the default, as Q3 implies? Recommended: yes.
2. **The order of a group** (§7): the member naming the most, as above, or the one the agent cited
   most in the trial (`better_alternative_v1`)? Recommended: naming the most.
3. **Packets** (§14): three, or MS-a and MS-b together (MS-b is AG8's board on R3)? Recommended:
   three — MS-a alone changes every cached analysis.

## 16. Not in MS

Removing the rounds; the setting (standing relations not named by a claim); new kinds of
commentary; extending an open keeping line by a search; a Korean renderer for Calliope's `text`.
