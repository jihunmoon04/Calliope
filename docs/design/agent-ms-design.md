# Agent MS-D — one meaning once

Status: **rev. 3 — for re-review**: review NOT_READY (B1–B5; N1, N2) applied in rev. 2, re-review
NOT_READY (B6, B7; N3) in rev. 3, second re-review READY_WITH_CORRECTIONS (B8), §17; owner Q1–Q3 as recommended; the invariants of §1.1 (owner, 2026-10-18). Date: 2026-10-18. Base: `main @ c9cd4e8` (MS framing merged).
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

### 1.1 What MS never simplifies

MS makes the agent's input and the default digest smaller; it does not make a verified meaning
smaller. Every requirement keeps these five (owner, 2026-10-18, after the review of rev. 1):

| # | Invariant | Held by |
| --- | --- | --- |
| I1 | **A relation's exact kind**: an absolute pin, a relative pin and a skewer are three kinds, a discovered attack is not an attack | §4.1, §5 |
| I2 | **A claim's status** is shown wherever the claim is: chosen or listed under another | §7 |
| I3 | **What was verified, and no more**: a `proves` says what its finding holds, within its finding's scope (one square's static exchange is one square's) | §8.2 |
| I4 | **Reachability**: an item the digest does not show keeps its handle in the digest (`not_shown`) or under the item that shows it | §6, §8.1 |
| I5 | **Citability**: what a `proves` writes — moves, squares, numbers — may be written in a sentence that cites the item, and no other token is added for it | §8.3 |

## 2. R1 — a mechanism's reads at once

`_Mechanism.verify` (`reasoning/catalogue/mechanisms.py`) today scans its steps in order: at each
step it reads the node's `reads`, and returns SUPPORTED at the first realized candidate; at the
first step whose records are missing it returns `NEEDS_EVIDENCE` for that node. **The scan stays as
it is up to that point** (review B6): a candidate realized at a step whose records are present is
returned at once, before anything later is asked for. Only the request at the first missing step
changes: it asks for the `reads` of that node and of the following steps' nodes that miss a record,
in scan order, up to four nodes in all (`BATCH_NODES = 4`; the first is always today's node). A
candidate's own check (`pieces`, `exchange` on one node) is unchanged.

So a verdict today's scan reaches with the records it has is reached at the same step, and a later
node is read only where today's scan would have stopped for a missing record anyway (the framing's
§3.3 cost, 147 → 151 needs, is of that kind).

**A small budget** (review N2, B6). The runner admits wanted needs by `need_key` while the round's
ensure room lasts (`max_ensure_nodes`, default 64; no request Calliope builds sets another —
`ply_request` and the agent's take the default). With room for every need nothing changes. With less
— a request setting `max_ensure_nodes` below four — the runner would admit some of a batch's nodes
by key and could leave today's node out. So the runner admits a claim's needs **in the order the
claim lists them** when the room cannot take all wanted needs (today: by `need_key` across claims,
which stays the order between claims). A batch's first node is then admitted whenever today's
single request would be.

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
  kind: attack | defence | exposed | check | double_attack
        | absolute_pin | relative_pin | skewer | discovered_attack
  pieces: the participants by PieceId and their square at the relation's node
          attack (attacker, target); defence (defender, defended); exposed (piece, gain);
          check (checkers); double_attack (actor, targets);
          absolute_pin (slider, pinned, king); relative_pin (slider, front, back);
          skewer (slider, front, back); discovered_attack (slider, front, targets)
  place: {"at": "move"} | {"at": "line", "line": <the claim's line: rank>, "ply": k}
  time: began | held | ended
```

The line relations keep their kinds apart (review B3, I1): an absolute pin is the pinned piece's
line to its king (`pieces.absolutely_pinned`), a relative pin a more valuable piece behind
(`patterns.relative_pins`), a skewer the more valuable piece in front (`patterns.skewers`), a
discovered attack a slider's line opened by the piece in front moving (`patterns.discovery_lines`).
Two relations are the same only when their kinds are; no kind stands for another.

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
| began | absolute_pin (either side; AG8's `board` has no other pin) | `pieces.absolutely_pinned` before and after, by identity |
| ended | defence (of a mover's piece that stayed and is attacked) | `pattern_delta.defences_ended_under_attack` (`defender_moved`, `line_blocked`) |
| held | exposed (only a piece a claim names, §5) | `exchange` gain before and after |

The function reads records (`PiecesFacts`, `PatternsFacts`, `PatternDeltaFacts`, `ExchangeFacts`,
`StatusFacts`) and returns relations with the pieces' squares; it does not verify propositions and
knows no side's `owner`. It is a function of the facts, not of an analysis: nothing is stored with
an analysis and no cached analysis changes for it.

## 5. R4 — a relation claim's link

A claim of `removed_defender_v2`, `newly_exposed_v1`, `left_en_prise_v2`, `fork_v2`, `pin_v2`,
`skewer_v2` or `discovery_v2` that is SUPPORTED has a `relation` and a `link`, read by
`piece_relations.claim_relation(analysis, claim, view)` when a digest is built. They are not stored
with the analysis and not added to the result document (`calliope.results`, the HTTP server's
answers): no cached analysis and no result format changes for them.

**What it reads** (review B7). A finding names the pieces but not always the relation's exact kind
or every participant; the verdict's evidence names the exact record. So `claim_relation` takes the
analysis's `TreeView` and reads, besides the finding and the claim graph, the fact records the
verdict's evidence points at (`fact_ref`: family, node, path):

| Template | Relation | From | Place |
| --- | --- | --- | --- |
| `removed_defender_v2` | defence (defender, defended) | `DefenceFinding` | move |
| `newly_exposed_v1`, `left_en_prise_v2` | exposed (piece, gain) | `HangingFinding.piece`; the gain from `exchange` at the child | move |
| `fork_v2` | double_attack (actor, targets) | `MechanismFinding`; its evidence `pattern_delta.multi_target_attacks` | the finding's node: move when it is the subject's child, else line ply k |
| `pin_v2` | absolute_pin when its evidence is `delta` `("pins", "began")` (pinned, pinner, king), relative_pin when it is `pattern_delta` `("relative_pins", "began")` (slider, front, back) | the evidence's record entry | as `fork_v2` |
| `skewer_v2` | skewer (slider, front, back) | its evidence `pattern_delta` `("skewers", "began")` | as `fork_v2` |
| `discovery_v2` | discovered_attack (slider, front, back) — the front the piece that moved | its evidence `patterns` `("discovery_lines", index)`, at the position before the front piece moves | the ply of the front piece's move (move when that is the subject's) |

A relation `claim_relation` cannot read whole — an evidence missing or not of its row — gets no
`relation`; the claim is listed as today, unmatched (I1, I4). Nothing in the findings or the stored
format changes.

**The time is read from the facts, never from the template's name** (review N3). At the move, a
relation's time is `began`, `held` or `ended` by comparing the positions before and after, by piece
identity, with the rules of §4.2 (an exposed piece: its exchange gain before and after). So
`newly_exposed_v1`, which skips the check before when its piece moved (`NewlyExposed.verify`), may
come out `held` — a piece already en prise that moved to another square where it is en prise — and
`left_en_prise_v2` `held`. A relation in the engine line is `began` at its ply (its evidence is a
change: `began`, or a line present at the node). Section 6 matches by kind, pieces and time, so a
`held` relation never merges with a `began` board item; a `held` relation of a claim's piece is a
`held` item (§6 item 3), whichever template it comes from.

A claim's relation is matched to a board item (§6) only of the same kind (I1): `pin_v2`'s
relative pin never matches the board's absolute pin, `discovery_v2` never the board's `attack`.

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
3. **Held.** A relation claim whose relation at the move is `held` (§5: `left_en_prise_v2`, or
   `newly_exposed_v1` for a piece that was en prise before it moved) becomes an item of kind `held`
   (`owner`: the piece's side, `good_for`: the other side, `part: reason`; propositions `exposed`
   before and `exposed` after) with its `leads_to`; nothing else is `held` (Q2).
4. A relation claim whose relation is in the engine line stays in `claims`, with its `relation`
   (place `line`, ply `k`) and `link` shown.

`board_v2`'s order and the bound's step 0 are AG8's; a `held` item and an item with `leads_to` are
kept by step 0 before the others of their kind.

**One relation once is settled on what the digest shows** (review B4, I4). The digest is built with
every claim listed; the bound runs; then a claim leaves `claims` only when the board item that
carries its `leads_to` is still shown. When step 0 moves such an item out, its claim stays in
`claims` (with its `relation` and `link`), and the item's handle is named in `not_shown.named`; when
a later step moves the claim out, its handle is named there too. So a claim's evidence is shown
once — under its board item or as a claim — or its handle is in `not_shown`, never neither. The
bound counts the digest after this settling (the settling only removes entries, so a digest within
the bound before it is within after).

## 7. R6 — groups shown once

| Group | Members, by what they name |
| --- | --- |
| a better move | `better_move_v1` (the consequence avoided), `missed_gain_v1` (the margin), `better_alternative_v1` (the judgement) |
| the move offers material | `piece_offer_v1` (the piece and how it was offered), `sacrifice_offer_v1` (the material in the line) |
| the move allows a mate | `mate_allowed_v1` (the line and the mate's length), `mate_in_one_allowed_v1` (exact, without a judgement) |

**The member shown** (review B5, I2): of the members present, the first SUPPORTED one in the order
above; when none is SUPPORTED, the first INCONCLUSIVE one (a REFUTED member is in `refuted`, never a
group's). So a SUPPORTED `missed_gain_v1` is shown over an INCONCLUSIVE `better_move_v1`.

In `claims`, the shown member's entry gains `"also": [{"ref", "template", "status", "proves"}]` for
the others present; they are not listed apart. Every member stays a claim, cites as today and keeps its label
rules (`missed_gain_v1` for MISS, `piece_offer_v1` for the brilliant rule). `sacrifice_sound_v1`
(an evaluation) and `sacrifice_compensated_v2` (a concrete return) are not members: they answer
other questions and are listed as today.

## 8. R7 — a smaller default digest

### 8.1 What leaves the default

| Field | Today | Default digest | Where it stays |
| --- | --- | --- | --- |
| `claims[].says` | the claim's English sentence | removed | `view: "full"` (`segments`) |
| `claims[].findings` | the findings without positions | removed for a claim with `proves` (§8.2) | `detail` of the claim's ref; `view: "full"` |
| `text` | Calliope's English text | removed | `view: "full"` |
| `refuted` | REFUTED claims by template and ref | `not_shown.refuted`: their refs | `detail` by ref; `view: "full"` |
| `lines.others` | up to three other candidates | `not_shown.others`: their refs | `detail` by ref; `view: "full"` |

A ref left in `not_shown` keeps the item reachable (I4): `detail` gives it whole, and it cites as
today (a REFUTED claim as `not_the_case`). On the trial's 199 digests this takes a digest from 5,028
characters on average to about 3,543 (0.70), counting 110 characters of `proves` for each claim that
has none today (the refs left in `not_shown` add about 30 characters each).

### 8.2 `proves` for every served claim

`board_remarks_ko_v1` becomes `board_remarks_ko_v2`: material and mate claims as in AG8-D §4, and a
`proves` for every other template, from its findings, in the same form (a bracket, then the moves
and pieces by colour, type and square; at most 240 characters). Each says what its template verifies
and stops there (I3); `{pct}` is a loss in expected points ÷ 20, rounded half up to an integer:

| Template | What it verifies | `proves` |
| --- | --- | --- |
| `better_move_v1` | the best move's line ends better than the played one's | `[비교] 둔 수의 라인은 {played outcome}, {best}의 라인은 {best outcome}` |
| `missed_gain_v1` | a reported move beat the played one by at least `MISS_LOSS` | `[비교] {best}가 둔 수보다 기대 점수로 {pct}%p 앞선다` |
| `better_alternative_v1` | rank 1 was not the played move | `[비교] 엔진의 1순위는 {best}였다` |
| `best_stops_reply_v1` | one square's static exchange (RESCUES / DEFENDS / COVERS) — never that the reply is stopped (review N1) | RESCUES `[비교] {best}는 {reply}가 잡을 {piece}를 옮긴다 ({square}, 정적 교환 기준)`; DEFENDS `[비교] {best} 뒤에는 {reply}로 {square}를 잡아도 정적 교환상 이득이 없다`; COVERS `[비교] {best} 뒤 {reply}를 두면 {square}의 {piece}를 정적 교환상 잃는다` |
| `forcing_v1` | the move checks, or leaves one reply | `[강제] {move}는 체크다` / `[강제] {move} 뒤 상대의 응수는 1개다` |
| `check_answer_v1` | the move is played out of check (a block, a capture of the checker, a king move) | `[체크 대응] {move}는 {checkers}의 체크를 {막는 / 잡는 / 킹으로 피하는} 수다` |
| `only_move_v1` | rank 2 of the unrestricted search loses at least 0.20 | `[유일한 수] 엔진의 2순위 수는 기대 점수로 {pct}%p 나쁘다` |
| `prevents_v1` | every other reported line is mated or loses material, the played line not | `[막음] 엔진이 보고한 다른 {alternatives}개 라인은 {메이트당하거나 물질을 잃고}, {move}의 라인은 그렇지 않다` |
| `rescue_v1` | the moved piece was en prise and is not | `[구출] {move}로 {piece}는 더 이상 잡히는 자리에 있지 않다` |
| `capture_holds_v1` | after the offered piece is taken, the mover holds half a point | `[받아도 됨] {piece}가 잡혀도 {reply} 뒤 {둔 쪽}의 기대 점수는 절반 이상이다` |
| `piece_offer_v1` | the move offers a piece (not that the offer is sound) | `[{mover}(둔 쪽)의 제공] {move}로 {piece}를 내준다 (옳은지는 따로)` |
| `sacrifice_offer_v1` | the line gives material up | `[{mover}(둔 쪽)의 희생] 엔진 라인에서 물질을 내준다` |
| `sacrifice_sound_v1` | an evaluation, not a return | `[희생의 평가] 엔진은 희생 뒤를 {둔 쪽}에 손해로 보지 않는다 (평가일 뿐 대가의 증명은 아니다)` |
| `sacrifice_compensated_v2` | a mate or a material return over every keeping line | `[희생의 대가] {메이트 / 물질 회수}`, and for `mate_over_scores` ` — 다른 라인과는 엔진 평가로 비교` |
| relation claims (§5) | their relation and its link | the relation in `board_remarks`' form at its place (`엔진 라인 {k}수째 {move} 뒤 …` in the line), then `그 결과 {consequence}{을 설명한다 / 와 함께 나온다}` by the link, and for a mechanism `{물질을 얻었다 / 배치일 뿐이다}` |
| `checks_draw_v1`, `checks_draw_missed_v1` | a run of checks ending in a repetition or the 50-move rule | `[무승부] {checker}의 연속 체크 {checks}번으로 {반복 / 50수}` |
| `mate_*`, `material_*` | AG8-D §4 | AG8-D §4 |

A claim whose findings lack what its row needs gets none and keeps its `findings` in the digest, as
AG8 does. No `proves` carries an engine score its finding does not (the lines' scores stay in
`lines`).

### 8.3 What a `proves` writes may be written (review B2, I5)

Every `proves` is built with the tokens it writes: its moves (with their positions), its squares and
its numbers. When the item is cited — by its handle (§9) or by a proposition of its claim — those
tokens join the cited propositions' S3 tokens (`Allowed`), and nothing else does. Today a claim adds
its moves, squares and `points` (`Verifier._harvest`); a number such as `forcing_v1`'s one reply,
`missed_gain_v1`'s `{pct}`, `prevents_v1`'s line count or a board item's defender count is in no
proposition, so a sentence repeating its `proves` is refused. The server builds the `proves` again
from the record when it verifies (the same function, `board_remarks_ko_v2`), so what is allowed is
what was shown. A number a `proves` does not write stays refused.

## 9. R8 — citing by handle; the server derives a claim's roles

### 9.1 Cites

A sentence's `cites` may name a **handle** served for the subject as well as a proposition's id. A
handle is a **unit of citation**, not a proposition (review B1): it stands for one or more
propositions, which the server builds, verifies and stores as if the agent had written them, each
with its own id — the handle, a colon and a fixed part name:

| Handle | Propositions, with their ids |
| --- | --- |
| `j` (the subject's judgement) | `judgement` — `<h>:judgement` |
| `c` (a claim) | `claim` with the derived `use` (§9.2) — `<h>:claim` |
| `s` (a line of the digest) | `engine_score` (its move, its score) — `<h>:score`; and, only when the line has a PV, `engine_line` (the moves the digest shows) — `<h>:line` (review B8: `Verifier._engine_line` refuses an empty line, and a line may be served without a PV) |
| `b` (a board item, §6) | the item's propositions in its order — `<h>:0`, `<h>:1`, … |
| `x` (an explored line) | `explored_line` (its moves) — `<h>:line` |

The contract:

1. **Expansion.** Before verification, every handle in a sentence's `cites` or `states` is replaced
   by the ids of the propositions actually built for it (an `s` handle without a PV: `<h>:score`
   alone); the sentence check (S1–S8) and the storage see only proposition ids,
   as today. A handle cited by several sentences is built once.
2. **Unique ids.** The built ids contain `:`, which no handle and no id the agent writes may contain
   (an agent's id with `:` is refused: "a proposition's id has no colon"); so a built id never
   meets an agent's, and `Session._commentary`'s uniqueness check and `verified[id]` hold as today.
3. **Mixing.** `propositions` may be empty; a submission may cite handles and its own propositions
   together. An agent's proposition and a handle's that are the same canonical record are kept both
   (the uniqueness is of ids, as today).
4. **States.** A handle in `states` states every proposition it stands for (S7 on each; AG8-D §6.2's
   "an item stated whole" holds by construction).
5. **Stored.** The stored commentary keeps the built propositions under their ids and each
   sentence's expanded `cites`; a stored record reads as today, with `"by_handle": "<h>"` on each
   built proposition.

### 9.2 The roles of a claim

`Verifier._use` stays the rule. When a claim is cited by handle, or a `claim` proposition has no
`use`, the server takes the first of the uses `_use` allows, in this order: `result`, `mechanism`,
`associated`, `comparison`, `line_fact`, `uncertain`, `not_the_case`. The stored proposition has
that `use` and `"use_by": "server"`. A claim no use allows is refused as today (`expected`: none).
A `claim` proposition with an explicit `use` is checked as today (`use_by` absent). So the agent
writes less, and every check `use` made is still made — by the server, on the claim's verdict,
relations and checks (the framing review's B2).

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
- The bound (AG6-D §3.6): step 0 as §6, and the settling of §6 after the last step; the steps
  `findings` and `text` apply only to what is still shown; a new step after `board` moves a group's
  `also` out first, its refs named in `not_shown` (I4).

## 11. What stays

Every fact family; every template's verdict but the five of §2–§3; every label rule; the claim
graph; the result document and `view: "full"` (but `board`, which only digests carry); explicit
propositions and `use`; S1–S8.

## 12. Tests

- R1: a scan with missing records at two nodes asks for both at once, and at six nodes for the first
  four; 11.Bxb5+ of the Opera Game decided within three rounds (Stockfish, gated); the 33 plies'
  verdicts unchanged elsewhere. **Small budgets** (review N2): the Opera Game and the rapid game
  with `max_ensure_nodes` 1, 2, 4 and 8 and `max_rounds` 2 and 3 — no verdict worse than today's at
  the same budget (worse: SUPPORTED or REFUTED today, INCONCLUSIVE now). **The scan first** (review
  B6): a line whose first step has its records and a realized candidate, and whose later steps miss
  theirs, is SUPPORTED in the same round as today with no need asked; with room for one node, a
  batch's first node is admitted (the runner's order within a claim).
- R2: 16.Qb8+ SUPPORTED with `mate_over_scores`; 13.Rxd7 INCONCLUSIVE; a played mate against an
  open line whose score is a mate for the other side is not decided; a SUPPORTED `MATE` decided by
  outcomes alone keeps `mate`.
- R3/R5: `move_relations` gives AG8's board items at the seven fixed moments of
  `test_board_stockfish.py`, and the synthetic cases of AG8 rev. 3–4 (a relation that moved with
  its piece is no change; a double attack that gained a target is none); `board_v2` equal to
  `board_v1` there but for `ref`. **Kinds** (review B3): a relative pin, an absolute pin and a
  skewer of one line are three relations; `pin_v2`'s relative pin is not matched to the board's
  absolute pin; `discovery_v2` is not matched to an `attack` item.
- R4/R5: 31...Qf6's `lost_defence` f8→f5 carries `removed_defender_v2`'s link and the claim is not
  listed; 38...Rxh5's weakness h5 `newly_exposed_v1`'s; 13.Rxd7's double attack `fork_v2`'s with
  `did: won`; 31...Qf6's `held` f5 for `left_en_prise_v2`; 6.Bc4's `pin_v2` stays a claim with place
  line ply 2. **The records read** (review B7): `pin_v2` from `delta.pins` gives an absolute pin and
  from `relative_pins` a relative one; `discovery_v2` gives its front piece from the
  `discovery_lines` entry its evidence names; a claim whose evidence is missing gets no `relation`
  and is listed unmatched. **The time** (review N3): a `newly_exposed_v1` piece that was en prise
  before it moved is `held`, becomes a `held` item and does not merge with a `began` exposed item;
  one that was not is `began` and merges. **The bound** (review B4): a digest over its bound whose step 0 moves the item with
  `leads_to` out lists the claim again and names the item's handle in `not_shown`; no claim's handle
  is both absent from the digest and from `not_shown`.
- R6 (review B5): a group with an INCONCLUSIVE `better_move_v1` and a SUPPORTED `missed_gain_v1`
  shows `missed_gain_v1`, with `better_move_v1` and its status in `also`; each member's ref still
  cites.
- R7: the removed fields absent by default, present in `view: "full"`; the refs of `refuted` and
  `others` in `not_shown`, and `detail` of each; `proves` for every template where its findings
  allow. **Within what was verified** (review N1): `best_stops_reply_v1`'s three kinds say one
  square's static exchange, none says the reply is stopped.
- R7/R8 **citability** (review B2): for every template with a `proves`, and for every board item
  kind, a sentence that cites the item by handle and repeats its `proves`' moves, squares and
  numbers is accepted (Stockfish fixtures where a template needs one); a number not in the `proves`
  is refused as today.
- R8 (review B1): a sentence citing `j`, `c`, `s`, `b` handles with no propositions is accepted and
  stored with the built propositions under `<h>:<part>` ids; `s` builds two, or one for a line
  without a PV — a sentence citing such a line by handle is accepted and stored with `<h>:score`
  alone (review B8); `b` one per proposition,
  all distinct; one handle cited by two sentences is built once; an agent's id with `:` is refused;
  a derived `use` is the first `_use` allows; an associated claim is stored `associated`, never
  `mechanism`; an explicit wrong `use` refused as today; S3 against a handle's moves; S7 with a
  handle in `states` stating every proposition.
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
   is English; `proves` replaces it in Korean, and it stays in `view: "full"`. Recommended (and the
   review's): out.
2. **A group's member shown** (§7): rev. 1 asked between "names the most" and "cited most";
   rev. 2 puts the status first (review B5): the first SUPPORTED member by what it names, then the
   first INCONCLUSIVE. Recommended (and the review's): this rule.
3. **Packets** (§14): three, MS-a reviewed before MS-b starts. Recommended (and the review's): three.

**Owner (2026-10-18): Q1–Q3 as recommended** — `text` out of the default; a group shows its first
SUPPORTED member by what it names, then its first INCONCLUSIVE; three packets, each reviewed before
the next.

## 16. Not in MS

Removing the rounds; the setting (standing relations not named by a claim); new kinds of
commentary; extending an open keeping line by a search; a Korean renderer for Calliope's `text`.

## 17. Reviews (rev. 2, rev. 3)

Independent review of rev. 1: NOT_READY — the direction kept (the relation in the reasoning layer,
apart from the causal reading; the rounds; the templates and label rules; `held` only for a claim's
piece; `says`, `text` and the little-used data out of the default; the derived `use` on `_use`;
three packets); the citation contract and three simplifications to fix. The owner asked whether MS
was simplifying what it must not; §1.1's invariants answer it, and each fix below holds one.

| Item | Applied |
| --- | --- |
| B1 — one id for several propositions | §9.1: a handle is a unit of citation; built ids `<h>:<part>`, expanded before the check; agents' ids without `:` |
| B2 — `proves` numbers refused by S3 | §8.3: a `proves`' own tokens are allowed when its item is cited, built again by the server; tests per template (I5) |
| B3 — a skewer as a pin | §4.1, §5: absolute pin, relative pin, skewer and discovered attack are kinds of their own; matched only within a kind (I1) |
| B4 — a deduplicated claim lost to the bound | §6: one relation once settled after the bound; the claim listed again or its handle in `not_shown` (I4) |
| B5 — the shown member ignores the status | §7: SUPPORTED first, then by what it names; `also` carries the status (I2) |
| N1 — `best_stops_reply_v1`'s `proves` too strong | §8.2: per kind, one square's static exchange; every row now names what its template verifies (I3) |
| N2 — the batch under a small budget | §2: at most four nodes, the first missing always in; §12 compares small budgets |

Re-review of rev. 2: NOT_READY — B1–B5 and N1 resolved, N2 completed; three more:

| Item | Applied (rev. 3) |
| --- | --- |
| B6 — the batch could delay a verdict the scan reaches | §2: the scan returns a realized candidate before anything later is asked; the batch starts at the first missing step; the runner admits a claim's needs in its order when the room is short |
| B7 — a finding does not name the pin's source or the discovery's front piece | §5: `claim_relation(analysis, claim, view)` reads the record the verdict's evidence names; a relation not read whole is left out, the claim unmatched |
| N3 — `newly_exposed_v1` taken as `began` | §5: every time read from the positions before and after; a `held` one is a `held` item and never merges with a `began` one |

Second re-review of rev. 3: READY_WITH_CORRECTIONS — B6, B7 and N3 resolved; one more: **B8** — an
`s` handle whose line has no PV would build an `engine_line` the verifier refuses. Applied: §9.1
builds `engine_line` only for a line with a PV and expands a handle to what was built; §12 a test.
