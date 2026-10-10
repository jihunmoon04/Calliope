# Reasoning — R3-D design: the explanation plan, the Korean phrasebook and the guarded renderer

Status: **rev. 1 — awaiting independent R3-D review**.
Date: 2026-10-10. Base: `main @ 43ce741` (R2b merged, #60). Contracts:
[`reasoning-r0-design.md`](reasoning-r0-design.md) rev. 10 §12–§13 (R0-D); claims:
[`reasoning-r2-design.md`](reasoning-r2-design.md) rev. 11 (R2-D) as implemented by R2b.

R0-D fixes the plan, the renderer and the guard as contracts. This packet gives what they leave
open: the exact selection rules of `selection_v1`, the sentence order, the Korean text of every
claim that can be rendered (`phrases_ko_v1`), how each slot is bound to a claim's findings, how
two claims joined by an edge become one sentence, and the guard's checks. It changes no claim.

## 0. Decisions

| # | Decision |
| --- | --- |
| H1 | **One sentence per role, in a fixed order**: judgement (and label), primary consequence (with its mechanism), function, comparison, qualification. A label's ground sentence follows the judgement directly. At most five sentences; every sentence ends with `.`. |
| H2 | **Edges become words only where an edge exists.** A mechanism with `EXPLAINS` to the primary consequence is rendered as the consequence's means ("…를 거쳐"), never as a cause ("때문에"); a sacrifice claim renders its `sacrifice_offer_v1` premise (`DERIVED_FROM`) as a concessive lead ("…를 내주지만"). Any other two claims stand in separate sentences without relation words (legacy P12 §12). |
| H3 | **Named, typed slots.** R0-D §13.1's slot types stay (`piece`, `square`, `move`, `amount`, `line`, `depth`, `count`); a variant names slots as `{name}` or `{name|은/는}`, and each template declares its slots' names, types and finding fields (§4). A variant is usable only when all its slots have values (R0-D §13.1), so one key covers optional values (a capture with or without a victim). |
| H4 | **Forms, not only statuses.** Keys are `<template>.<form>`: `sentence` (a SUPPORTED claim as a sentence), `means` (a mechanism before a consequence), `lead` (an offer before a sacrifice claim), `pending` (an INCONCLUSIVE claim in the qualification); kinds of a finding select a form suffix (`means.walked`, `sentence.promotion`). R0-D §13.1's `<template>.<status>` is amended accordingly (R0-D §30). |
| H5 | **SAN with move numbers.** Moves are SAN from fact records (R0-D §13.2), numbered `27.Nd4` / `27…Nd4`; a line is shown up to 6 plies, then `…`. |
| H6 | **No engine numbers in the text.** No centipawns, WDL, ranks or expected points; the grade carries the evaluation. The only numbers are material points, mate distances, depth and counts. (Legacy P12 §13; owner may revisit.) |
| H7 | **Refuted claims are not rendered.** The qualification renders at most two INCONCLUSIVE claims linked by `QUALIFIES` to selected claims, with their reason; a REFUTED mechanism ("not a pin") tells the reader nothing in v1. R0-D §12.2 is narrowed (R0-D §30). |
| H8 | **Korean terms** (owner may change; they are phrasebook data, `phrases_ko_v1`): grades 최선의 수 / 훌륭한 수 / 좋은 수 / 부정확한 수 / 실수 / 대실수; labels GREAT 결정적인 한 수, MISS 놓친 기회; pieces 킹 / 퀸 / 룩 / 비숍 / 나이트 / 폰. |

## 1. The plan (`selection_v1`)

```text
ExplanationPlan(subject, policy: "selection_v1",
    judgement: JudgementRef, label: Label | None,
    purpose: tuple[ClaimId, ...],          # FUNCTION: 0–1, plus its offer premise as a lead
    mechanism: tuple[ClaimId, ...],        # MECHANISM: 0–1, only with EXPLAINS to the consequence
    consequence: tuple[ClaimId, ...],      # CONSEQUENCE: 0–1, the primary one
    justification: tuple[ClaimId | LineRef, ...],   # COMPARISON: 0–1, and the line it shows
    qualification: tuple[ClaimId | ScopeRef, ...])  # effective scopes; ≤ 2 INCONCLUSIVE claims
```

Rules, in order (R0-D §12.2 with the priority tables of R2-D §5.3; claim ids break every tie):

1. **Judgement INCONCLUSIVE** (R0-D §12.3): the plan holds the judgement and every SUPPORTED claim
   of basis `EXACT` — `mate_delivered_v1`, `mate_in_one_allowed_v1` as consequences (that order),
   `forcing_v1` as the function. Nothing else.
2. **Label** (`label_v1`): its ground claims fill their slots first (`only_move_v1` → purpose,
   `better_move_v1` → justification).
3. **Consequence**: the first SUPPORTED claim of `mate_delivered_v1`, `mate_found_v1`,
   `mate_in_one_allowed_v1`, `mate_allowed_v1`, then `material_loss_v1` / `material_gain_v1` by
   larger `MaterialFinding.amount`.
4. **Mechanism**: among SUPPORTED claims with an `EXPLAINS` edge to the selected consequence, the
   first of `fork_v1`, `skewer_v1`, `pin_v1`, `discovery_v1`, `newly_unsafe_v1`,
   `left_en_prise_v1`, `removed_defender_v1`; within a template, the earliest
   `MechanismFinding.node` on the line (by its index), then id. `ASSOCIATED_WITH` is never
   selected (R0-D D12).
5. **Function** (unless filled by rule 2): the first SUPPORTED of `only_move_v1`, `prevents_v1`,
   `sacrifice_compensated_v1`, `sacrifice_sound_v1`, `forcing_v1`. A sacrifice claim brings its
   `sacrifice_offer_v1` premise into `purpose` before it, as its lead (H2). `sacrifice_offer_v1`
   alone is not a function sentence: without a soundness or a return, the reader learns only that
   material was given (it remains in the graph).
6. **Comparison** (unless filled by rule 2): `mate_missed_v1`, then `better_move_v1`; the
   justification adds the comparison's best-line window (its first operand) as a `LineRef`.
7. **Qualification**: the effective scopes (R0-D §9.4) of every selected claim, deduplicated and
   in canonical order; then at most two INCONCLUSIVE claims with a `QUALIFIES` edge to a selected
   claim, by role priority (CONSEQUENCE, MECHANISM, FUNCTION, COMPARISON), then id (H7).
8. **Exact claims are never dropped by a contrast** (legacy P10 §25.1): when the judgement is
   decided, `mate_in_one_allowed_v1` competes in rule 3 like any consequence (and ranks above
   `mate_allowed_v1`), and `forcing_v1` in rule 5.

A plan's identity is the sha256 of its canonical encoding (`plan_digest`).

## 2. Sentence order and composition

```text
S1  judgement                       "{move|은/는} {grade}입니다."
S1' label + its ground              "{label} — {ground sentence}"        (when a label exists)
S2  [mechanism.means] consequence   "{means} {consequence sentence}"
S3  [offer.lead] function           "{lead} {function sentence}"
S4  comparison (+ its line)         "{comparison sentence}"
S5  qualification                   "{scope phrases joined by ', '} 기준입니다." + pending claims
```

- S1' replaces the label's ground in S3/S4 (it is rendered once, after the label).
- A sentence's segments keep their sources (R0-D §13.4 G2): `means` belongs to the mechanism
  claim, `sentence` to the consequence; spaces and the final `.` are `CONNECTIVE` segments.
- Empty roles are skipped. A decided judgement without any selected claim renders S1 alone
  (R0-D §12.3, legacy P9 §25).

## 3. Slot values (R0-D §13.2, refined)

| Type | Value | Source fields |
| --- | --- | --- |
| `piece` | `<square> <piece name>` at the reference's node, e.g. `d4 나이트`; the type is read from `pieces` at `PieceRef.node` (a promoted pawn reads as its new type) | `PieceRef` |
| `square` | the square, e.g. `e4` | `SquareRef`, `PieceRef.square` |
| `move` | numbered SAN (`27.Nd4`, `27…Nf3+`): `move.san` of the edge into `MoveRef.node`; for `SearchMoveRef(s, k, 1)` the SAN from `status.legal_moves` at the search's node; a `SearchRef(s, k)` renders its first move like `SearchMoveRef(s, k, 1)`; a witness UCI (`ProofScope.witnesses`) renders through `status` at the scope's node | `MoveRef`, `SearchMoveRef`, `SearchRef`, witness |
| `line` | the numbered SAN of the segment's plies `1 … min(k, 6)`, then `…` if longer; a zero-ply segment renders its first move from the search followed by `…` | `LineSegment` |
| `amount` | `<points>점` | `MaterialAmount` |
| `depth`, `count` | digits | scope `depth`; finding integers |

Move numbers come from `FrameNode.fullmove_number` and side to move at the edge's parent.

## 4. Slot bindings per template

Each row lists the slots a template's forms may use and where each value comes from. A form
naming a slot without a value is not usable (H3).

| Template | Slots → source |
| --- | --- |
| `mate_delivered_v1` | `move` ← `MateFinding.mating_move` |
| `mate_found_v1` | `count` ← `MateFinding.moves`; `line` ← operand 0 (the `Lp` window) |
| `mate_in_one_allowed_v1` | `reply` (move) ← `scope.witnesses[0]` at the scope's node |
| `mate_allowed_v1` | `count` ← `MateFinding.moves`; `line` ← operand 0 |
| `mate_missed_v1` | `best` (move) ← `ComparisonFinding.best_move`; `count` ← `ComparisonFinding.best.moves` |
| `material_loss_v1` | `victim` (piece) ← `event.victim`; `capture` (move) ← `MoveRef(event.node)`; `amount` ← `amount` |
| `material_gain_v1` | as `material_loss_v1`; a promotion has no `victim` (form `sentence` falls to the variant without it) |
| `forcing_v1` | `count` ← `ForcingFinding.replies`; kind suffix `check` / `single` |
| `only_move_v1` | `second` (move) ← `AlternativeFinding.line` |
| `prevents_v1` | `count` ← `PreventsFinding.alternatives`; `amount` ← `smallest_loss` (points); kind suffix `mate` / `material` / `mixed` |
| `sacrifice_offer_v1` (lead) | `victim` (piece) ← `OfferFinding.event.victim`; `amount` ← `OfferFinding.amount` |
| `sacrifice_sound_v1` | — |
| `sacrifice_compensated_v1` | kind suffix `mate` / `material_return` |
| `fork_v1`, `pin_v1`, `skewer_v1` (means) | `actor` (piece) ← `MechanismFinding.actor`; `move` ← `MechanismFinding.move`; suffix `walked` when `walked_into` |
| `discovery_v1` (means) | `actor` (piece), `move` as above |
| `removed_defender_v1` (means) | `defender` (piece) ← `DefenceFinding.defender`; `defended` (piece) ← `DefenceFinding.defended` |
| `newly_unsafe_v1` (means) | `piece` ← `HangingFinding.piece`; kind suffix `moved_into_attack` / `line_opened` |
| `left_en_prise_v1` (means) | `piece` ← `HangingFinding.piece` |
| `better_move_v1` | `best` (move) ← `ComparisonFinding.best_move`; `line` ← operand 0 (the `L1` window) |
| any (pending) | `reason` ← the verdict reason, through `reason.<REASON>` phrases |

## 5. `phrases_ko_v1`

File `render/phrases/ko.toml`, read with `tomllib`. Each key holds a list of variants (§6 picks
one). The listed text is the complete v1 vocabulary; anything else fails closed.

```toml
[judgement]
best = ["{move|은/는} 최선의 수입니다."]
excellent = ["{move|은/는} 훌륭한 수입니다."]
good = ["{move|은/는} 좋은 수입니다."]
inaccuracy = ["{move|은/는} 부정확한 수입니다."]
mistake = ["{move|은/는} 실수입니다."]
blunder = ["{move|은/는} 대실수입니다."]
inconclusive = ["{move|은/는} 평가하지 못했습니다({reason})."]

[label]
great = ["결정적인 한 수입니다:"]
miss = ["놓친 기회입니다:"]

[mate_delivered_v1]
sentence = ["{move|으로/로} 체크메이트입니다."]
[mate_found_v1]
sentence = ["{line} 수순으로 {count}수 안에 메이트합니다."]
[mate_in_one_allowed_v1]
sentence = ["상대에게 {reply|으로/로} 바로 메이트할 기회를 줍니다."]
[mate_allowed_v1]
sentence = ["{line} 수순으로 {count}수 안에 메이트당합니다."]
[mate_missed_v1]
sentence = ["{best|으로/로} {count}수 메이트가 있었습니다."]

[material_loss_v1]
sentence = ["{capture}에서 {victim|을/를} 잃어 {amount} 손해를 봅니다."]
[material_gain_v1]
sentence = ["{capture}에서 {victim|을/를} 잡아 {amount}{을/를} 얻습니다.",
            "{capture|으로/로} 승격해 {amount}{을/를} 얻습니다."]

[forcing_v1]
"sentence.check" = ["체크로 상대의 응수를 강요합니다."]
"sentence.single" = ["상대의 응수는 하나뿐입니다."]
[only_move_v1]
sentence = ["다른 수는 {second|을/를} 포함해 모두 크게 불리해지는 유일한 수입니다."]
[prevents_v1]
"sentence.mate" = ["엔진이 보고한 다른 {count}개 수는 모두 메이트당합니다."]
"sentence.material" = ["엔진이 보고한 다른 {count}개 수는 모두 {amount} 이상 손해를 봅니다."]
"sentence.mixed" = ["엔진이 보고한 다른 {count}개 수는 모두 메이트당하거나 기물을 잃습니다."]
[sacrifice_offer_v1]
lead = ["{victim|을/를} 내주지만"]
[sacrifice_sound_v1]
sentence = ["엔진은 그 뒤에도 형세가 유지된다고 봅니다."]
[sacrifice_compensated_v1]
"sentence.mate" = ["그 대가로 기물을 지키는 어떤 수보다 빠른 메이트가 있습니다."]
"sentence.material_return" = ["내준 것 이상을 되찾아 기물을 지키는 수보다 앞섭니다."]

[fork_v1]
means = ["{move}의 {actor} 포크를 거쳐"]
"means.walked" = ["{actor}의 포크에 걸려"]
[pin_v1]
means = ["{move}의 {actor} 핀을 거쳐"]
"means.walked" = ["{actor}의 핀에 스스로 걸려"]
[skewer_v1]
means = ["{move}의 {actor} 꼬치 공격을 거쳐"]
"means.walked" = ["{actor}의 꼬치 공격에 걸려"]
[discovery_v1]
means = ["{move}의 {actor} 디스커버드 공격을 거쳐"]
[removed_defender_v1]
means = ["{defender}{이/가} {defended|을/를} 지키지 않게 되어"]
[newly_unsafe_v1]
"means.moved_into_attack" = ["{piece|을/를} 공격받는 칸으로 옮겨"]
"means.line_opened" = ["{piece}에 대한 공격선을 열어"]
[left_en_prise_v1]
means = ["공격받던 {piece|을/를} 그대로 두어"]

[better_move_v1]
sentence = ["대신 {best}{이/가} 나았습니다: {line}."]

[scope]
"engine.specific_line" = ["엔진 깊이 {depth}의 수순"]
"engine.all_alternatives.engine_ranked" = ["엔진 깊이 {depth}의 전체 수 검토"]
"engine.all_alternatives.engine_reported" = ["엔진이 보고한 {count}개 수"]
"engine.exists_alternative.engine_reported" = ["엔진이 보고한 {count}개 수"]
"policy.unsafe_v1" = ["공격·방어 수로 본 기물 안전(교환 계산 제외)"]
sentence = ["{scopes} 기준입니다."]
pending = ["{claim}은 확인하지 못했습니다({reason})."]

[reason]
LINE_TOO_SHORT = ["수순이 짧음"]
UNSTABLE = ["결과가 정해지지 않음"]
MATE_LINE = ["메이트 수순"]
SCOPE_SHORT = ["검토 범위 부족"]
BUDGET = ["예산 초과"]
ROUND_LIMIT = ["라운드 한도"]
NEED_UNMET = ["필요한 사실을 얻지 못함"]
NOT_COMPUTED = ["계산하지 않음"]
# judgement reasons (R1 §2.4)
PARENT_NOT_SEARCHED = ["탐색하지 않은 국면"]
DEADLINE = ["시간 제한"]
IRREGULAR_SEARCH = ["엔진 탐색이 불완전함"]
NOT_IN_BASIS = ["둔 수가 엔진 결과에 없음"]
WDL_UNAVAILABLE = ["엔진이 승률을 주지 않음"]
NOT_APPLICABLE = ["게임이 끝난 국면"]
COMPARISON_NOT_REQUESTED = ["비교 탐색 없음"]

[claim]   # names used by scope.pending
material_loss_v1 = ["기물 손실"]
material_gain_v1 = ["기물 이득"]
fork_v1 = ["포크"]
pin_v1 = ["핀"]
skewer_v1 = ["꼬치 공격"]
discovery_v1 = ["디스커버드 공격"]
removed_defender_v1 = ["수비 해제"]
newly_unsafe_v1 = ["기물 노출"]
left_en_prise_v1 = ["방치된 기물"]
only_move_v1 = ["유일한 수 여부"]
prevents_v1 = ["다른 수의 손실"]
sacrifice_compensated_v1 = ["희생의 보상"]
sacrifice_sound_v1 = ["희생의 타당성"]
better_move_v1 = ["더 나은 수"]
mate_missed_v1 = ["놓친 메이트"]
```

Notes:
- `{grade}` is never a slot: each grade has its own key (H6, no number).
- `NOT_COMPUTED(<parameter>)` reads `reason.NOT_COMPUTED` (the parameter is internal).
- A scope of basis `EXACT` has no phrase: exact facts are not qualified.
- `only_move_v1`'s wording does not state the 0.20 threshold (H6); "크게 불리해지는" is its
  rendering, fixed by D10 of R0-D.

## 6. Variants, particles and determinism

- **Variant choice** (R0-D §13.1): among the usable variants of a key (H3), the one at index
  `int(h[:8], 16) mod n`, `h` = the source id (claim id; for a judgement or label the sha256 of
  its canonical encoding; for a scope the sha256 of the `ProofScope`).
- **Particles** (R0-D §13.3) apply to the final sound of the slot's rendered text: a piece by its
  name (킹 ㅇ, 퀸 ㄴ, 룩 ㄱ, 비숍 ㅂ, 나이트 vowel, 폰 ㄴ); a move or square by its last digit read
  in Sino-Korean, ignoring `+`, `#` and `…`, a promotion by the promoted piece, castling `O-O` /
  `O-O-O` as 캐슬링 (ㅇ); a number by its Sino-Korean reading (units digit, else 십 ㅂ, 백 ㄱ,
  천 ㄴ, 만 ㄴ); an amount by 점 (ㅁ); a line by its last move. `이/가`, `은/는`, `을/를`, `과/와`:
  first form after any consonant; `으로/로`: `로` after a vowel or ㄹ.
- Particles are written only in the phrasebook; a slot never carries one.
- Rendering is a pure function of (plan, graph, view at the final revision, phrasebook): no clock,
  no locale, no randomness (R0-D §16).

## 7. Guard (R0-D §13.4)

The renderer builds every segment from a **source handle**: an object holding the source (a
claim, the judgement, the label, a scope) and the set of references it may resolve — its
operands, evidence, finding fields, scope witnesses and, for a `SearchMoveRef` / `SearchRef`,
the search record and `status` at the search's node. Formatters receive the handle, never the
view (G1, G3).

| Check | Refusal (`GuardError`) |
| --- | --- |
| G1 | a formatter asks the handle for a node, record or search outside its reference set |
| G2 | a segment without a source, or a non-phrasebook text with source `CONNECTIVE` |
| G3 | a slot value whose reference is not among the source's references (operands, evidence, findings, witnesses) |
| G4 | a claim not SUPPORTED in `purpose`, `mechanism`, `consequence` or `justification`; a mechanism without an `EXPLAINS` edge to the plan's consequence; a lead that is not the function claim's premise |
| G5 | a key, form or slot outside `phrases_ko_v1`, or a variant whose slots are not all bound |

`RenderedExplanation(plan_digest, language: "ko", phrasebook: "phrases_ko_v1", segments)`;
`text` is the concatenation of the segments' text.

## 8. Golden examples (expected output of the acceptance tests)

Built from R2b's test scenarios; move numbers as in those positions.

1. **Blunder allowing a fork** (R2-D §3.7 example, 1.a3 Bc5 2.b5 Be7 3.b6 Nf3+ 4.Ke2 Nxd4+):
   `1.a3은 대실수입니다. 3…Nf3+의 f3 나이트 포크를 거쳐 4…Nxd4+에서 d4 나이트를 잃어 3점 손해를
   봅니다. 대신 1.Nb3이 나았습니다: 1.Nb3 Ne6 2.Kd2 Kd7. 엔진 깊이 12의 수순, 공격·방어 수로 본
   기물 안전(교환 계산 제외) 기준입니다.`
2. **Missed mate after the opponent's blunder** (MISS; the label's ground `better_move_v1` fills
   the comparison, so `mate_missed_v1` is not rendered): `2.h3은 대실수입니다. 놓친 기회입니다:
   대신 2.Qe8+이 나았습니다: 2.Qe8+ Rxe8 3.Rxe8#. 엔진 깊이 12의 수순 기준입니다.`
3. **Only move** (GREAT; the label's ground takes the one function slot, so the sacrifice claims
   stay in the graph): `1.Qe8+은 최선의 수입니다. 결정적인 한 수입니다: 다른 수는 1.h3을 포함해
   모두 크게 불리해지는 유일한 수입니다. 1.Qe8+ Rxe8 2.Rxe8# 수순으로 2수 안에 메이트합니다. 엔진
   깊이 12의 전체 수 검토, 엔진 깊이 12의 수순 기준입니다.`
4. **Mate delivered** (exact): `1.Ra8#은 최선의 수입니다. 1.Ra8#로 체크메이트입니다.`
5. **Judgement inconclusive with an exact claim**: `1.Rc1은 평가하지 못했습니다(엔진이 승률을 주지
   않음). 상대에게 1…Rxc1#로 바로 메이트할 기회를 줍니다.`

Particles in these examples follow §6: `a3`, `Nb3`, `h3` end in 삼 (ㅁ); `Qe8+`, `Ra8#`, `Rc1`,
`Rxc1#` end in 팔 / 일 (ㄹ), so `은`, `이` and `로`.

The R3 packet records the exact strings its tests assert; any wording change is `phrases_ko_v2`.

## 9. Test obligations (R0-D §18.8–§18.9)

1. **Planner**: every rule of §1, including ties by id, the label's grounds first, the exact
   claims of an inconclusive judgement, an `ASSOCIATED_WITH` mechanism never selected, the
   two-pending cap, a decided judgement with no claim.
2. **Composition**: means + consequence, lead + function, the label sentence, sentence order,
   empty roles skipped.
3. **Slots**: every slot type and source of §3–§4, including `SearchMoveRef` of a zero-ply line
   (`…`), a witness UCI, a promotion, castling, and a variant falling back when a slot is unbound.
4. **Particles**: every piece name; every rank digit 1–8; `+`, `#`, `…`; promotion to each piece;
   `O-O`, `O-O-O`; numbers 1–9, 10, 20, 100, 1000, 10000 and a number ending in ㄹ (1, 7, 8);
   amounts.
5. **Variants**: deterministic choice, unusable variants skipped, an empty usable set refused.
6. **Guard mutations**: an unsupported claim in each assertive slot; a mechanism without
   `EXPLAINS`; a slot value from another claim; a formatter reading outside its handle; an
   unknown key; an unbound slot.
7. **Golden examples** of §8 on R2b's scenarios, and a determinism re-run (same bytes).

## 10. Relation to R0-D (amended in R0-D §30 when this design is accepted)
- §12.2: refuted claims are not rendered (H7); the offer is a lead, not a function (§1 rule 5).
- §13.1: named typed slots and forms (H3, H4).
- §13.2: `SearchRef(s, k)` renders its first move; a witness UCI renders through `status`.

## 11. Open
- Owner choices: the Korean terms of H8 and the wording of §5 (data, versioned).
- Rendering engine numbers (H6) is deferred.
