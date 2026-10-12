# Reasoning — R3-D design: the explanation plan, the English phrasebook and the guarded renderer

Status: **rev. 5 — reviews applied (§13–§15); re-review READY; amended by R3 (§16) and A2 (§17), owner, and EA-D (§18)**.
Date: 2026-10-11 (rev. 1–2: 2026-10-10). Base: `main @ 7c3aa7c`. Contracts:
[`reasoning-r0-design.md`](reasoning-r0-design.md) rev. 10 §12–§13 (R0-D), amended in R0-D §30–§32;
claims: [`reasoning-r2-design.md`](reasoning-r2-design.md) rev. 11 (R2-D) as implemented by R2b;
[`reasoning-label-v2-design.md`](reasoning-label-v2-design.md) (LV-D, with §15–§16) and
[`reasoning-miss-v2-design.md`](reasoning-miss-v2-design.md) (MV-D) as implemented by LV1 and MV1;
grades: [`reasoning-quality-v2-design.md`](reasoning-quality-v2-design.md) (Q-D).

R0-D fixes the plan, the renderer and the guard as contracts. This packet gives what they leave
open: the exact selection rules of `selection_v1`, the sentence order, the English text of every
claim that can be rendered (`phrases_en_v1`), how each slot is bound to a claim's findings, how
two claims joined by an edge become one sentence, and the guard's checks. It changes no claim.

Rev. 1 (`2c5ace7`) was written for Korean. The owner made English the default language; the
Korean wording and particle rules of rev. 1 are the starting point of a later `phrases_ko_v1`
packet (§11).

**Rev. 3** (§12) follows what merged after rev. 2:
- **grades:** `quality_v2` (Q-D). The text is unchanged, since grades carry no numbers (H6).
- **labels:** `label_v2` (LV-D, MV-D): FORCED, and the provisional BRILLIANT (`brilliant_p2`),
  GREAT (`great_p2`) and MISS (`miss_p2`).
- **claims:** `piece_offer_v1`, `capture_holds_v1`, `rescue_v1` and `missed_gain_v1`.
- **the wording limits** set by the LV1 and MV-D / MV1 reviews (H10).

## 0. Decisions

| # | Decision |
| --- | --- |
| H0 | **English is the default and first language** (owner, 2026-10-10). `AnalysisRequest.language` defaults to `"en"`; R0-D D7 and §13 are amended (R0-D §30). Further languages are further phrasebooks plus their inflection rules (Korean particles, R0-D §13.3). |
| H1 | **One sentence per role, in a fixed order**: judgement, label, primary consequence (with its mechanism), function, comparison, qualification. A label's ground sentence follows the label directly. At most nine sentences (rev. 4, review C1): S1–S6 at most one each, and S7 the scope sentence plus at most two pending sentences (§1 rule 7). Nothing is dropped to meet a lower count. Each sentence ends with `.`. |
| H2 | **Edges become words only where an edge exists.** A mechanism with `EXPLAINS` to the primary consequence is rendered as the consequence's means ("Through the fork …, it loses …"), never as a cause ("because"); a sacrifice claim renders its `sacrifice_offer_v1` premise (`DERIVED_FROM`) as a concessive lead ("Giving up …, …"). Any other two claims stand in separate sentences without relation words (legacy P12 §12). |
| H3 | **Named, typed slots.** R0-D §13.1's slot types stay (`piece`, `square`, `move`, `amount`, `line`, `depth`, `count`); a variant names slots as `{name}` or, for number agreement, `{name|singular/plural}`. Each template declares its slots' names, types and finding fields (§4). A variant is usable only when all its slots have values (R0-D §13.1). A variant never states a fact its slots do not carry: where the finding's kind decides the wording (a capture or a promotion), the kind selects a suffix, not the bound slots (rev. 5, review B4). |
| H4 | **Forms, not only statuses.** Keys are `<template>.<form>`: `sentence` (a SUPPORTED claim as a sentence), `means` (a mechanism before a consequence), `lead` (an offer before a sacrifice claim), `name` (a claim named in the qualification); a kind of a finding selects a suffix (`means.walked`, `sentence.check`). R0-D §13.1's `<template>.<status>` is amended accordingly (R0-D §30). |
| H5 | **SAN with move numbers.** Moves are SAN from fact records (R0-D §13.2), numbered `27.Nd4` / `27...Nd4`; a line is shown up to 6 plies, then `...`. |
| H6 | **No engine numbers in the text.** No centipawns, WDL, ranks or expected points; the grade carries the evaluation. The only numbers are material points, mate distances, depth and counts. (Legacy P12 §13; the owner may revisit.) |
| H7 | **Refuted claims are not rendered.** The qualification names at most two INCONCLUSIVE claims linked by `QUALIFIES` to selected claims, with their reason; a REFUTED mechanism ("not a pin") tells the reader nothing in v1. R0-D §12.2 is narrowed (R0-D §30). |
| H8 | **English terms** (phrasebook data, `phrases_en_v1`; the owner may change them): grades *best move*, *excellent move*, *good move*, *inaccuracy*, *mistake*, *blunder*; labels *brilliant move*, *great move*, *missed opportunity*, and FORCED as *the only legal move*; pieces *king*, *queen*, *rook*, *bishop*, *knight*, *pawn*, written as "the knight on d4". |
| H9 | **Provisional labels read like settled ones** (rev. 3; owner decision, 2026-10-11). The text of a BRILLIANT, GREAT or MISS is the same under a provisional rule (`brilliant_p2`, `great_p2`, `miss_p2`). `RenderedExplanation` carries the label's `rule` and `provisional` (§7), so a caller can mark them. A hedge in the text ("by a provisional rule") would tell the reader about rule maturity, not about the move. The owner chose no hedge. Should that change, a hedge is a `label.<kind>.provisional` variant in a later phrasebook. |
| H10 | **Claims are rendered only as far as they prove** (rev. 3; LV-D §15.1, MV-D review N3, MV1 review). Details after this table. |

H10 in detail:
- **"Sacrifice" with BRILLIANT.** The word comes only from the pair `piece_offer_v1` +
  `capture_holds_v1`, both SUPPORTED (`sound_sacrifice`).
  - `piece_offer_v1` alone is never rendered: it is an offer whose soundness is unchecked.
  - `capture_holds_v1` is rendered only inside that pair.
- **"Sacrifice" elsewhere.** R2-D's line sacrifice (`sacrifice_offer_v1` with `sacrifice_sound_v1`
  or `sacrifice_compensated_v1`) keeps its lead and function forms. When the label is BRILLIANT,
  they are not selected, so the sacrifice is not told twice.
- **"Missed opportunity"** is said only by the MISS label sentence.
  - `missed_gain_v1` alone says only that a stronger move existed.
  - Its `loss` is an expected-points loss. It names no material gain, mate or tactic. Those words
    come only from another SUPPORTED claim that carries them, such as `better_move_v1` with a
    material or mate outcome, or `mate_missed_v1`.

## 1. The plan (`selection_v1`)

```text
ExplanationPlan(subject, policy: "selection_v1",
    judgement: JudgementRef, label: Label | None,
    purpose: tuple[ClaimId, ...],          # FUNCTION: 0–1; its lead is derived, never stored (rev. 5)
    mechanism: tuple[ClaimId, ...],        # MECHANISM: 0–1, only with EXPLAINS to the consequence
    consequence: tuple[ClaimId, ...],      # CONSEQUENCE: 0–1, the primary one
    justification: tuple[ClaimId | LineRef, ...],   # COMPARISON: 0–1, and the line it shows
    qualification: tuple[ClaimId | ScopeRef, ...])  # effective scopes; ≤ 2 INCONCLUSIVE claims
```

Rules, in order (R0-D §12.2 with the priority tables of R2-D §5.3; claim ids break every tie):

1. **Judgement INCONCLUSIVE** (R0-D §12.3): the plan holds the judgement, then the FORCED label
   when `label_v2` made one, then every SUPPORTED claim of basis `EXACT`:
   `mate_delivered_v1`, `mate_in_one_allowed_v1` as consequences (that order), and `forcing_v1`
   as the function. Nothing else.
   - FORCED needs no grade (LV-D §3, review C2), so it survives an inconclusive judgement (rev. 4,
     review B2).
   - No other label exists without a decided judgement.
2. **Label** (`label_v2`, rev. 3): its ground claims are placed first.
   - **FORCED:** no grounds. Its label sentence says it all, and the other roles follow as usual.
   - **BRILLIANT:** the pair `piece_offer_v1` + `capture_holds_v1` is the label's ground sentence
     (S3, §2), not a role.
     - The R2-D sacrifice claims (`sacrifice_offer_v1`, `sacrifice_sound_v1`,
       `sacrifice_compensated_v1`) are not selected for function (H10).
   - **GREAT:** `only_move_v1` goes to purpose.
   - **MISS:** to justification, `better_move_v1` when it is among the grounds (it carries a line
     and an outcome), otherwise `missed_gain_v1`.
3. **Consequence**: the first SUPPORTED claim of `mate_delivered_v1`, `mate_found_v1`,
   `mate_in_one_allowed_v1`, `mate_allowed_v1`, then `material_loss_v1` / `material_gain_v1` by
   larger `MaterialFinding.amount`. Exact claims compete here like any consequence, so a decided
   contrast never silences them (legacy P10 §25.1).
4. **Mechanism**: among SUPPORTED claims with an `EXPLAINS` edge to the selected consequence, the
   first of `fork_v1`, `skewer_v1`, `pin_v1`, `discovery_v1`, `newly_unsafe_v1`,
   `left_en_prise_v1`, `removed_defender_v1`; within a template, the earliest
   `MechanismFinding.node` on the line, then id. `ASSOCIATED_WITH` is never selected (R0-D D12).
5. **Function** (unless filled by rule 2): the first SUPPORTED of `only_move_v1`, `prevents_v1`,
   `sacrifice_compensated_v1`, `sacrifice_sound_v1`, `rescue_v1` (rev. 3), `forcing_v1`.
   - **The lead is derived, not stored** (rev. 5, review B6). For a sacrifice claim, `purpose`
     holds that claim alone. The renderer finds the `sacrifice_offer_v1` premise among the
     claim's `hypothesis.premises` and renders it as the lead (H2). G4 checks that the lead is
     that premise. BRILLIANT's lead is derived the same way, from `capture_holds_v1`'s premise.
   - `sacrifice_offer_v1` alone is not a function sentence. Without soundness or a return, the
     reader learns only that material was given; it stays in the graph.
   - Under a BRILLIANT label the sacrifice claims are skipped (rule 2).
   - `piece_offer_v1` and `capture_holds_v1` are never selected here (H10).
6. **Comparison** (unless filled by rule 2): `mate_missed_v1`, then `better_move_v1`, then
   `missed_gain_v1` (rev. 3).
   - The justification adds the comparison's best-line window as a `LineRef`, when the claim has
     one: the first operand of `mate_missed_v1` and `better_move_v1`.
   - `missed_gain_v1` has no line. It proves an alternative in S, not a PV (MV-D §4).
7. **Qualification**: the effective scopes (R0-D §9.4) of every selected claim, deduplicated and
   in canonical order; then at most two INCONCLUSIVE claims with a `QUALIFIES` edge to a selected
   claim, by role (CONSEQUENCE, MECHANISM, FUNCTION, COMPARISON), then id (H7).

A plan's identity is the sha256 of its canonical encoding (`plan_digest`).

## 2. Sentence order and composition

```text
S1  judgement                       "{move} is a blunder."
S2  label                           "This is a great move."          (when a label exists)
S3  the label's ground              its own sentence form; for BRILLIANT, [piece_offer_v1.lead]
                                    capture_holds_v1.sentence (rev. 3)
S4  [mechanism.means] consequence   "Through ..., it loses ..."
S5  [offer.lead] function           "Giving up ..., in return it ..."
S6  comparison (+ its line)         "{best} was better: {line}."
S7  qualification                   "Based on {scopes}." then one sentence per pending claim
```

- A label's ground is rendered once, as S3, and its role's own sentence is skipped.
- **BRILLIANT's ground** is one sentence joined like a lead (rev. 3): "Offering the queen on e8
  (net 4 points) to 1...Rxe8, it still holds after the capture, with 2.Rxe8#." The amount is
  `PieceOfferFinding.offer`: the exchange's net, here 9 for the queen less 5 for the rook that
  retakes.
  - The lead belongs to `piece_offer_v1`, the sentence to `capture_holds_v1`.
  - G4 refuses either one without the other (H10).
- FORCED has no grounds, so no S3.
- **Joining** (H2): a `means` or `lead` form ends with `,`; the following `sentence` form then
  starts with its first letter lowercased. Every `sentence` form therefore begins with phrasebook
  text, never with a slot (checked by G5).
- Segments keep their sources (R0-D §13.4 G2): `means` belongs to the mechanism claim, `sentence`
  to the consequence; spaces between sentences are `CONNECTIVE` segments.
- Empty roles are skipped. A decided judgement without any selected claim renders S1 alone
  (R0-D §12.3, legacy P9 §25).

## 3. Slot values (R0-D §13.2, refined)

| Type | Value | Source |
| --- | --- | --- |
| `piece` | `the <piece name> on <square>` at the reference's node, e.g. `the knight on d4`; the type is read from `pieces` at `PieceRef.node` (a promoted pawn reads as its new type) | `PieceRef` |
| `square` | the square, e.g. `e4` | `SquareRef`, `PieceRef.square` |
| `move` | numbered SAN (`27.Nd4`, `27...Nf3+`): `move.san` of the edge into `MoveRef.node`; for `SearchMoveRef(s, k, 1)` the SAN from `status.legal_moves` at the search's node; a `SearchRef(s, k)` renders its first move like `SearchMoveRef(s, k, 1)`; a witness UCI (`ProofScope.witnesses`) renders through `status` at the scope's node | `MoveRef`, `SearchMoveRef`, `SearchRef`, witness |
| `line` | numbered SAN of the segment's plies `1 … min(k, 6)`, then `...` if longer; a zero-ply segment renders its first move from the search followed by `...` | `LineSegment` |
| `amount` | `<n> point` / `<n> points` | `MaterialAmount`; an integer of `points_v1` (`PieceOfferFinding.offer`, rev. 3) |
| `depth`, `count` | digits | scope `depth`; finding integers |

Move numbers come from `FrameNode.fullmove_number` and the side to move at the edge's parent.
`{name|singular/plural}` renders the number and the singular word when it is 1, else the plural.

## 4. Slot bindings per template

A form naming a slot without a value is not usable (H3).

| Template | Slots → source |
| --- | --- |
| `mate_delivered_v1` | `move` ← `MateFinding.mating_move` |
| `mate_found_v1` | `count` ← `MateFinding.moves`; `line` ← operand 0 (the `Lp` window) |
| `mate_in_one_allowed_v1` | `reply` (move) ← `scope.witnesses[0]` at the scope's node |
| `mate_allowed_v1` | `count` ← `MateFinding.moves`; `line` ← operand 0 |
| `mate_missed_v1` | `best` (move) ← `ComparisonFinding.best_move`; `count` ← `ComparisonFinding.best.moves` |
| `material_loss_v1` | `victim` (piece) ← `event.victim`; `capture` (move) ← `MoveRef(event.node)`; `amount` ← `amount`. The suffix follows the event (rev. 5, review B4): `capture_promotion` when `event.victim` and `event.promotion` are both set, `promotion` when only `event.promotion` is, `capture` otherwise |
| `material_gain_v1` | as `material_loss_v1`, with the same suffix rule. "promotes" is said only when `event.promotion` is set (rev. 5, review B4) |
| `forcing_v1` | `count` ← `ForcingFinding.replies`. The suffix follows the finding exactly (rev. 4, review B1): `check_single` when `check` and `replies = 1`; `check` when `check` and `replies > 1`; `single` when not `check` and `replies = 1`. Only a single legal reply is called forced: a check alone proves no particular reply. |
| `only_move_v1` | `second` (move) ← `AlternativeFinding.line` |
| `prevents_v1` | `count` ← `PreventsFinding.alternatives`; `amount` ← `smallest_loss` (points); suffix `mate` / `material` / `mixed` |
| `sacrifice_offer_v1` (lead) | `victim` (piece) ← `OfferFinding.event.victim`; `amount` ← `OfferFinding.amount` |
| `sacrifice_sound_v1` | — |
| `sacrifice_compensated_v1` | suffix `mate` / `material_return` |
| `fork_v1`, `pin_v1`, `skewer_v1` (means) | `actor` (piece) ← `MechanismFinding.actor`; `move` ← `MechanismFinding.move`; suffix `walked` when `walked_into` |
| `discovery_v1` (means) | `actor` (piece), `move` as above |
| `removed_defender_v1` (means) | `defender` (piece) ← `DefenceFinding.defender`; `defended` (piece) ← `DefenceFinding.defended` |
| `newly_unsafe_v1` (means) | `piece` ← `HangingFinding.piece`; suffix `moved_into_attack` / `line_opened` |
| `left_en_prise_v1` (means) | `piece` ← `HangingFinding.piece` |
| `better_move_v1` | `best` (move) ← `ComparisonFinding.best_move`; `line` ← operand 0 (the `L1` window) |
| `piece_offer_v1` (lead, BRILLIANT only) | `piece` ← `PieceOfferFinding.piece`; `amount` ← `PieceOfferFinding.offer`; `capture` (move) ← `PieceOfferFinding.taken_by` (rev. 3) |
| `capture_holds_v1` (BRILLIANT only) | `reply` (move) ← `CaptureHoldsFinding.reply` (a `SearchRef` at X, its first move). The capture is the lead's slot, since a slot reads only its own claim's references (G3) (rev. 3) |
| `rescue_v1` | `piece` ← `RescueFinding.piece` (rev. 3) |
| `missed_gain_v1` | `best` (move) ← `MissedGainFinding.best` (a `SearchMoveRef`, rendered without its PV); `loss` is not a slot (H6, H10) (rev. 3) |
| any (pending) | `reason` ← the verdict reason, through `reason.<REASON>` |

## 5. `phrases_en_v1`

File `render/phrases/en.toml`, read with `tomllib`. Each key holds a list of variants (§6 picks
one). The text below is the complete v1 vocabulary; anything else fails closed (G5).

```toml
[judgement]
best = ["{move} is the best move."]
excellent = ["{move} is an excellent move."]
good = ["{move} is a good move."]
inaccuracy = ["{move} is an inaccuracy."]
mistake = ["{move} is a mistake."]
blunder = ["{move} is a blunder."]
inconclusive = ["{move} could not be judged ({reason})."]

[label]
forced = ["It is the only legal move."]
brilliant = ["This is a brilliant move."]
great = ["This is a great move."]
miss = ["This is a missed opportunity."]
"miss.lead" = ["This is a missed opportunity;"]

[mate_delivered_v1]
sentence = ["It is checkmate."]
[mate_found_v1]
sentence = ["The engine line leads to mate in {count}: {line}."]
[mate_in_one_allowed_v1]
sentence = ["It allows mate in one with {reply}."]
[mate_allowed_v1]
sentence = ["It allows mate in {count} along {line}."]
[mate_missed_v1]
sentence = ["There was mate in {count} with {best}."]

[material_loss_v1]
"sentence.capture" = ["It loses {victim} at {capture} (net material loss over the line: at least {amount})."]
"sentence.promotion" = ["It allows a promotion at {capture} (net material loss over the line: at least {amount})."]
"sentence.capture_promotion" = ["It loses {victim} to a promotion at {capture} (net material loss over the line: at least {amount})."]
"sentence.line.capture" = ["Along the engine line, it loses {victim} at {capture} (net material loss over the line: at least {amount})."]
"sentence.line.promotion" = ["Along the engine line, it allows a promotion at {capture} (net material loss over the line: at least {amount})."]
"sentence.line.capture_promotion" = ["Along the engine line, it loses {victim} to a promotion at {capture} (net material loss over the line: at least {amount})."]
[material_gain_v1]
"sentence.capture" = ["It wins {victim} at {capture} (net material gain over the line: at least {amount})."]
"sentence.promotion" = ["It promotes at {capture} (net material gain over the line: at least {amount})."]
"sentence.capture_promotion" = ["It wins {victim} and promotes at {capture} (net material gain over the line: at least {amount})."]
"sentence.line.capture" = ["Along the engine line, it wins {victim} at {capture} (net material gain over the line: at least {amount})."]
"sentence.line.promotion" = ["Along the engine line, it promotes at {capture} (net material gain over the line: at least {amount})."]
"sentence.line.capture_promotion" = ["Along the engine line, it wins {victim} and promotes at {capture} (net material gain over the line: at least {amount})."]

[forcing_v1]
"sentence.check" = ["It gives check."]
"sentence.single" = ["It leaves the opponent a single legal reply."]
"sentence.check_single" = ["It gives check and leaves a single legal reply."]
[only_move_v1]
sentence = ["Every other move, including {second}, is clearly worse."]
[prevents_v1]
"sentence.mate" = ["The other {count|move/moves} the engine reported all allow mate."]
"sentence.material" = ["The other {count|move/moves} the engine reported all lose at least {amount}."]
"sentence.mixed" = ["The other {count|move/moves} the engine reported all allow mate or lose material."]
"sentence.mate.one" = ["The only other move the engine reported allows mate."]
"sentence.material.one" = ["The only other move the engine reported loses at least {amount}."]
"sentence.mixed.one" = ["The only other move the engine reported allows mate or loses material."]
[sacrifice_offer_v1]
lead = ["Giving up {victim} ({amount}),"]
[sacrifice_sound_v1]
sentence = ["The engine still rates the position as holding."]
[sacrifice_compensated_v1]
"sentence.mate" = ["In return the engine line leads to mate, while the moves that keep the material, among those the engine reported, all end worse."]
"sentence.material_return" = ["In return it wins back more than the moves that keep the material, among those the engine reported."]

[fork_v1]
means = ["Through the fork by {actor} at {move},"]
"means.walked" = ["Walking into the fork by {actor},"]
[pin_v1]
means = ["Through the pin by {actor} at {move},"]
"means.walked" = ["Walking into the pin by {actor},"]
[skewer_v1]
means = ["Through the skewer by {actor} at {move},"]
"means.walked" = ["Walking into the skewer by {actor},"]
[discovery_v1]
means = ["Through the discovered attack by {actor} at {move},"]
[removed_defender_v1]
means = ["With {defender} no longer defending {defended},"]
[newly_unsafe_v1]
"means.moved_into_attack" = ["Moving {piece} onto an attacked square,"]
"means.line_opened" = ["Opening a line onto {piece},"]
[left_en_prise_v1]
means = ["Leaving {piece} under attack,"]

[better_move_v1]
sentence = ["Instead, {best} was better: {line}."]
[missed_gain_v1]
sentence = ["Instead, {best} was stronger."]
[piece_offer_v1]
lead = ["Offering {piece} (net {amount}) to {capture},"]
[capture_holds_v1]
sentence = ["It still holds after the capture, with {reply}."]
[rescue_v1]
sentence = ["It moves {piece} out of danger."]

[scope]
"engine.specific_line" = ["the engine line at depth {depth}"]
"engine.all_alternatives.engine_ranked" = ["the engine's full search at depth {depth}"]
"engine.all_alternatives.engine_reported" = ["the {count|move/moves} the engine reported"]
"engine.exists_alternative.engine_reported" = ["the {count|move/moves} the engine reported"]
"engine.exists_response.engine_ranked" = ["the engine's search after the capture at depth {depth}"]
"policy.see_v1" = ["piece exchanges judged by static exchange evaluation"]
"policy.unsafe_v1" = ["piece safety judged by attackers and defenders, without exchange evaluation"]
sentence = ["Based on {scopes}."]
pending = ["The {claim} could not be confirmed ({reason})."]

[reason]
LINE_TOO_SHORT = ["the line is too short"]
UNSTABLE = ["the outcome is not settled"]
MATE_LINE = ["the line ends in mate"]
SCOPE_SHORT = ["the search does not cover it"]
BUDGET = ["the analysis budget ran out"]
ROUND_LIMIT = ["the round limit was reached"]
NEED_UNMET = ["the needed facts were not obtained"]
NOT_COMPUTED = ["not computed"]
# judgement reasons (R1 §2.4)
PARENT_NOT_SEARCHED = ["the position was not searched"]
DEADLINE = ["the time limit was reached"]
IRREGULAR_SEARCH = ["the engine search was incomplete"]
NOT_IN_BASIS = ["the move is not in the engine's results"]
WDL_UNAVAILABLE = ["the engine gave no win/draw/loss figures"]
NOT_APPLICABLE = ["the game was already over"]
COMPARISON_NOT_REQUESTED = ["no comparison search was made"]

[claim]   # names used by scope.pending
material_loss_v1 = ["material loss"]
material_gain_v1 = ["material gain"]
fork_v1 = ["fork"]
pin_v1 = ["pin"]
skewer_v1 = ["skewer"]
discovery_v1 = ["discovered attack"]
removed_defender_v1 = ["removed defender"]
newly_unsafe_v1 = ["exposed piece"]
left_en_prise_v1 = ["piece left en prise"]
only_move_v1 = ["only-move test"]
prevents_v1 = ["losses of the other moves"]
sacrifice_compensated_v1 = ["return on the sacrifice"]
sacrifice_sound_v1 = ["soundness of the sacrifice"]
better_move_v1 = ["better move"]
mate_missed_v1 = ["missed mate"]
piece_offer_v1 = ["piece offer"]
capture_holds_v1 = ["position after the capture"]
rescue_v1 = ["rescue of the piece"]
missed_gain_v1 = ["stronger move"]
```

Notes:
- `{grade}` is never a slot: each grade has its own key (H6, no number).
- `NOT_COMPUTED(<parameter>)` reads `reason.NOT_COMPUTED` (the parameter is internal).
- A scope of basis `EXACT` has no phrase: exact facts are not qualified.
- `only_move_v1` does not state the 0.20 threshold (H6); "clearly worse" is its rendering of
  R0-D D10.
- Scopes are joined as an English list: `A`, `A and B`, `A, B and C`.
- Rev. 3:
  - **The grade sentences stand under both `quality_v1` and `quality_v2`.** The grade is a word,
    and the curve is not rendered (H6).
  - **`missed_gain_v1`'s sentence says "stronger", never "wins".** Its proof is an
    expected-points loss (H10).
  - **`piece_offer_v1.lead` and `capture_holds_v1.sentence` exist only as BRILLIANT's ground.**
    G4 refuses them anywhere else.

## 6. Variants, inflection and determinism

- **Variant choice** (R0-D §13.1): among the usable variants of a key (H3), the one at index
  `int(h[:8], 16) mod n`, `h` = the source id (the claim id; for a judgement or label the sha256
  of its canonical encoding; for a scope the sha256 of the `ProofScope`).
- **Inflection in English**: number agreement only — `{name|singular/plural}` and the `amount`
  unit (`1 point`, `3 points`). Articles are written in the phrasebook ("the knight on d4", "a
  blunder", "an inaccuracy"); no slot carries an article.
- **Capitalization**: only the first letter of a `sentence` form that follows a `means` or `lead`
  form is lowercased (§2); SAN and squares are never changed.
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
| G2 | a segment without a source, or text with source `CONNECTIVE` that is not a phrasebook connective (a space) |
| G3 | a slot value whose reference is not among the source's references |
| G4 | a claim not SUPPORTED in `purpose`, `mechanism`, `consequence` or `justification`; a mechanism without an `EXPLAINS` edge to the plan's consequence; a lead that is not a premise of the claim whose sentence follows it (rev. 3: the function claim's offer, or BRILLIANT's `piece_offer_v1` before `capture_holds_v1`); `piece_offer_v1` or `capture_holds_v1` rendered other than as BRILLIANT's ground, or one without the other; BRILLIANT's ground not equal to the label's grounds (H10) |
| G5 | a key, form or slot outside `phrases_en_v1`; a variant whose slots are not all bound; a `sentence` form beginning with a slot |

`RenderedExplanation(plan_digest, language: "en", phrasebook: "phrases_en_v1", segments,
label_rule: str | None, label_provisional: bool)`.
- `text` is the concatenation of the segments' text.
- The two label fields (rev. 3, H9) copy the plan's `Label.rule` and `Label.provisional`. They are
  `None` and `False` without a label. A caller can mark provisional labels without parsing the
  text.

## 8. Golden examples (expected output of the acceptance tests)

Built from R2b's test scenarios.

1. **Blunder allowing a fork** (R2-D §3.7: 1.a3 Bc5 2.b5 Be7 3.b6 Nf3+ 4.Ke2 Nxd4+):
   `1.a3 is a blunder. Through the fork by the knight on f3 at 3...Nf3+, along the engine line, it loses the knight
   on d4 at 4...Nxd4+ (net material loss over the line: at least 3 points). Instead, 1.Nb3 was better: 1.Nb3 Ne6 2.Kd2 Kd7. Based on the engine
   line at depth 12 and piece safety judged by attackers and defenders, without exchange
   evaluation.`
2. **Missed mate after the opponent's blunder** (MISS, `miss_p2`). The grounds are
   `missed_gain_v1` and `better_move_v1`, and `better_move_v1` fills the comparison, so neither
   `missed_gain_v1` nor `mate_missed_v1` is rendered: `2.h3 is a blunder. This is a missed
   opportunity; instead, 2.Qe8+ was better: 2.Qe8+ Rxe8 3.Rxe8#. Based on the engine line at
   depth 12.`
3. **Only move** (GREAT, `great_p2`; rev. 3 uses LV1's quiet only move, since 1.Qe8+ is now
   BRILLIANT): `1.a3 is the best move. This is a great move. Every other move, including 1.Kd2,
   is clearly worse. Based on the engine's full search at depth 12.`
4. **Mate delivered** (exact): `1.Ra8# is the best move. It is checkmate.`
5. **Judgement inconclusive with an exact claim**: `1.Rc1 could not be judged (the engine gave no
   win/draw/loss figures). It allows mate in one with 1...Rxc1#.`
5b. **Judgement inconclusive, FORCED** (rev. 4, review B2: LV1's one-move position with the judgement
   made INCONCLUSIVE): `1.Kxb2 could not be judged (the engine search was incomplete). It is the
   only legal move.`
6. **Brilliant** (rev. 3: `brilliant_p2` on LV1's 1.Qe8+ Rxe8 2.Rxe8#).
   - The ground is the pair.
   - The R2-D sacrifice claims are SUPPORTED but not selected (H10).
   - `only_move_v1` takes the function.

   `1.Qe8+ is the best move. This is a brilliant move. Offering the queen on e8 (net 4 points) to
   1...Rxe8, it still holds after the capture, with 2.Rxe8#. The engine line leads to mate in 2:
   1.Qe8+ Rxe8 2.Rxe8#. Every other move, including 1.h3, is clearly worse. Based on the engine line at
   depth 12, piece exchanges judged by static exchange evaluation, the engine's search after the
   capture at depth 12 and the engine's full search at depth 12.`
7. **Forced** (rev. 3: LV1's one-move position): `1.Kxb2 is the best move. It is the only legal
   move.`
8. **Missed opportunity without material** (rev. 3: MV1's 9.Bxe7 shape). `better_move_v1` is
   INCONCLUSIVE, so the ground `missed_gain_v1` names the stronger move with no line and no
   material: `9.Bxe7 is a mistake. This is a missed opportunity; instead, 9.Bf6 was stronger. Based
   on the 2 moves the engine reported.`
   - No sentence names the INCONCLUSIVE `better_move_v1` (rev. 4, review B3).
     - `QUALIFIES` runs from an INCONCLUSIVE claim only to its own premises: `material_loss_v1`
       and `mate_allowed_v1` for `better_move_v1`, not `missed_gain_v1`.
     - Nothing more needs qualifying: the SUPPORTED `missed_gain_v1` already proves that a
       stronger move existed. What stays open is a concrete result, and v1 does not render one.

The R3 packet records the exact strings its tests assert; any wording change is `phrases_en_v2`.

## 9. Test obligations (R0-D §18.8–§18.9)

1. **Planner**: every rule of §1, including ties by id, the label's grounds first, the exact
   claims of an inconclusive judgement, an `ASSOCIATED_WITH` mechanism never selected, the
   two-pending cap, a decided judgement with no claim.
2. **Composition**: means + consequence (lowercased join), lead + function, the label sentence
   and its ground, sentence order, empty roles skipped.
3. **Slots**: every slot type and source of §3–§4, including a `SearchMoveRef` of a zero-ply
   line (`...`), a witness UCI, a promotion, castling, a promoted piece's name, and a variant
   falling back when a slot is unbound.
4. **Inflection**: `1 move` / `2 moves`, `1 point` / `3 points`; scope lists of one, two and three.
5. **Variants**: deterministic choice, unusable variants skipped, an empty usable set refused.
6. **Guard mutations**: an unsupported claim in each assertive slot; a mechanism without
   `EXPLAINS`; a slot value from another claim; a formatter reading outside its handle; an
   unknown key; an unbound slot; a sentence form starting with a slot.
7. **Golden examples** of §8, on the scenarios of R2b, LV1 and MV1, and a determinism re-run
   (same bytes).
8. **Rev. 3, labels and limits (H9, H10):**
   - each `label_v2` kind and its ground placement (rule 2);
   - BRILLIANT renders the pair as one sentence and suppresses the R2-D sacrifice claims;
   - G4 refuses `piece_offer_v1` alone, `capture_holds_v1` alone, or either outside BRILLIANT;
   - a SUPPORTED `missed_gain_v1` without a MISS renders "stronger", never "missed opportunity";
   - MISS prefers `better_move_v1` over `missed_gain_v1` in justification;
   - `rescue_v1` as a function;
   - `label_rule` and `label_provisional` copied to `RenderedExplanation`;
   - the same text under `quality_v1` and `quality_v2` for equal grades.
9. **Rev. 4:**
   - `forcing_v1` renders each of `check`, `check_single` and `single` from its finding;
   - a check with several replies never says "forces" or "single" (review B1);
   - INCONCLUSIVE judgement with FORCED renders the label (review B2, example 5b);
   - example 8 renders no pending sentence (review B3);
   - a plan with all six roles and two pending claims renders nine sentences, and none is dropped
     (review C1).
10. **Rev. 5:**
    - `material_gain_v1` and `material_loss_v1` on a plain capture, a promotion, and a capture that
      promotes, each with its suffix. A plain capture never says "promotes" (review B4).
    - `mate_found_v1` says "the engine line"; `sacrifice_compensated_v1` names only the reported
      keeping moves (review B5).
    - `sacrifice_compensated_v1.sentence.mate` on keeping lines without a mate, and on keeping
      lines with a slower mate. The text is the same and says "all end worse", never "faster".
    - `purpose` holds one claim for a sacrifice. The lead is derived from its premises, and a plan
      with a stored lead is refused (review B6).

## 10. Relation to R0-D (amended in R0-D §30)
- D7, §1.2, §3.2, §5, §13: English first (`language = "en"`, `render/phrases/en.toml`,
  `phrases_en_v1`); Korean particles (§13.3) apply when the Korean phrasebook is added.
- §12.2: refuted claims are not rendered (H7); the offer is a lead, not a function (§1 rule 5).
- §13.1: named typed slots and forms (H3, H4).
- §13.2: English piece names; `SearchRef(s, k)` renders its first move; a witness UCI renders
  through `status`.
- Rev. 3: §12.2 and §13.4 for `label_v2`, H9 and H10 (R0-D §30, last two rows).

## 11. Open
- Owner choices: the English terms of H8 and the wording of §5 (data, versioned).
- Rendering engine numbers (H6) is deferred.
- **Korean** (`phrases_ko_v1`): a later packet; rev. 1 of this document (`2c5ace7`, §5–§6) holds
  its draft wording and the particle rules of R0-D §13.3 applied to it.

## 12. Rev. 3 (2026-10-11): what changed since rev. 2

Rev. 2 waited for review while grades and labels moved on. Rev. 3 merges `main @ 7c3aa7c` and
follows these changes. It does not re-open rev. 2's decisions H0–H8.

| Merged since rev. 2 | Change here |
| --- | --- |
| Q-D, Q1–Q3: `quality_v2` | None in the text, since grades carry no numbers (H6). The grade sentences hold for both policies (test 8). |
| LV-D, LV1: `label_v2`, FORCED, `brilliant_p2`, `great_p2`, `piece_offer_v1`, `capture_holds_v1`, `rescue_v1` | Labels: H8, rule 2, the `[label]` keys. BRILLIANT's ground sentence (§2, §4, §5). `rescue_v1` as a function (rule 5). The sacrifice limits (H10, G4). Examples 3, 6 and 7. |
| LV-D §8: provisional rules | H9 (owner decision): the text is unmarked; `RenderedExplanation` carries `label_rule` and `label_provisional` (§7). |
| MV-D, MV1: `miss_p2`, `missed_gain_v1`; MV-D review N3; MV1 review notes | MISS grounds (rule 2). `missed_gain_v1` as the last comparison (rule 6), with the sentence "… was stronger" and no line or amount (§4, §5). H10: "missed opportunity" only through the label. Example 8. |
| R0-D §31, §32 | R0-D §30 stays R3-D's section; §31 (Q-D) and §32 (LV-D, MV-D) follow it. |

## 13. Review dispositions (rev. 3 `fcd3be4`, independent review: NOT_READY)

The review passed H9 (the owner's decision) and the rev. 3 limits on sacrifice and missed-gain
wording. Each finding was checked against the code.

| Finding | Disposition |
| --- | --- |
| B1 "It gives check and forces the reply" exceeds `forcing_v1` | Valid: `Forcing.verify` supports a check or a single legal reply, and `ForcingFinding` records `check` and `replies`. Applied (§4, §5): `check` says "It gives check."; `single` and `check_single` say that one legal reply is left. The suffix follows the finding. |
| B2 FORCED dropped under an INCONCLUSIVE judgement | Valid: rule 1's "nothing else" would drop a label that `label_v2` makes without a grade. Applied (§1 rule 1): the plan keeps FORCED. Example 5b, test 9. |
| B3 example 8's pending sentence cannot be produced | Valid: `graph.relations` makes `QUALIFIES` only from an INCONCLUSIVE claim to its premises, and `missed_gain_v1` is not one of `better_move_v1`'s. Applied (§8): the sentence is removed and the example fixed. A later design may add a relation and a wording for unsettled concrete results. |
| C1 at most seven sentences against the pending sentences | Applied (H1): at most nine, S1–S6 one each, and S7 with at most two pending sentences. Nothing is dropped to meet a lower count. Test 9. |

## 14. Review dispositions (rev. 4 `3fd92a1`, re-review: NOT_READY)

The re-review closed B1–B3 and C1, and kept H9 and H10. It found three new points, checked against
the code.

| Finding | Disposition |
| --- | --- |
| B4 a plain capture could read "It promotes" | Valid: the promotion variant binds no `victim`, so it was usable on any capture. The same rule left `material_loss_v1` with no usable variant on an opponent's promotion. Applied (H3, §4, §5): the suffix follows `DecisiveEvent.victim` and `.promotion` (`capture`, `promotion`, `capture_promotion`) for both claims. Test 10. |
| B5 wording stronger than the scope | Valid: `mate_found_v1` is proved on S's played line (`SPECIFIC_LINE`), and `sacrifice_compensated_v1` against the reported keeping lines. Applied (§5): "The engine line leads to mate in …", and "… than the moves that keep the material, among those the engine reported". Example 6 updated. |
| B6 `purpose` 0–1 against the inserted lead | Valid. Applied (§1): `purpose` holds the function claim alone. The renderer derives the lead from that claim's premises, and BRILLIANT's lead from `capture_holds_v1`'s premise. G4 already checks the premise. |
| (non-blocking) PR title and description out of date | Applied on the PR. |

## 15. Review disposition (rev. 5 `3416128`, re-review: NOT_READY, one remainder)

B4 and B6 passed. B5 passed for `mate_found_v1`.

| Finding | Disposition |
| --- | --- |
| B5 remainder: "mates faster" | Valid. `SacrificeCompensated.verify` rule 3 needs the sacrificing line to mate and to beat every keeping line under `lines.compare`. There a mate beats any STABLE outcome, so the keeping lines need not mate at all, and "faster" is not proved. Applied (§5): "In return the engine line leads to mate, while the moves that keep the material, among those the engine reported, all end worse." Test 10 covers keeping lines with no mate and with a slower mate. |

## 16. Amendment from implementation packet R3 (owner, 2026-10-12; corrected after R3 review B1)

R3 rendered every ply of two real games (R3 record §3.2). The text exposed two wording problems in
`phrases_en_v1`. The owner decided both before anything was rendered for users, so the phrasebook
stays `phrases_en_v1`.

| Change | Reason |
| --- | --- |
| **Material sentences say what the amount guarantees** (§5; R3 review B1): "It wins {victim} at {capture} (net material gain over the line: at least {amount})." The loss forms say "net material loss over the line: at least {amount}", and the promotion forms follow the same pattern. Example 1 changes accordingly. | `{amount}` is not the decisive victim's value. The bare "(5 points)" after "the pawn on h6" read as the pawn's value; in 17 of 30 material sentences of the two games the two numbers differ. Nor is it the line's total: `material_loss_v1` takes `min(−Δp, Δ1 − Δp)`, and `material_gain_v1` takes `min(Δp, Δb)`. These are conservative sizes the claim guarantees, so "at least" is true and "total" was not. |
| **No closing "." after a truncated line** (§2, H5): a sentence whose last slot is a line cut with " ..." ends there, as in "… 3.Ke3 Ke7 ..." | " ..." followed by "." printed "....". |

## 17. Amendment A2 (owner, 2026-10-12): MISS after the move, verb agreement, events later in the line

An end-to-end explanation of an owner game (829 / 808) showed three wording problems. The owner
decided all three before any user rendering, so the phrasebook stays `phrases_en_v1`; its digest
changes, and the build identity records that (R4-D §2.1).

| Change | Reason |
| --- | --- |
| **MISS is told after what the move did** (§2). The order becomes S1 judgement, S4 consequence, S5 function, then the MISS label joined to its ground as one sentence: "This is a missed opportunity; instead, 13...Bf6 was better: …" (`label.miss.lead`, the ground lowercased). GREAT and BRILLIANT keep S2–S3, since their label praises the move itself. | With the ground first, the played move's consequence followed "Instead, 13...Bf6 was better: …" and read as that line's ("It wins the rook on e1 at 18...Bxe1"). |
| **A single alternative agrees with its verb** (§4, §5). `prevents_v1` takes the suffix `.one` when `alternatives = 1`: "The only other move the engine reported loses at least 5 points." | "The other 1 move … all lose" (47...Ke8). |
| **An event later in the line says so** (§4, §5). A material event after the move and the reply (`DecisiveEvent.ply > 2`) uses `sentence.line.<kind>`: "Along the engine line, it wins the pawn on d4 at 4...exd4 (…)". The move itself and the immediate reply stay plain. Example 1 changes accordingly. | "It promotes at 46.b8=Q" after 44.Ka7, or "wins the pawn on d4 at 4...exd4" after 2...Nc6, read as the move's own act. |

**The threshold of 2 plies.** The owner's proposal marked every event after the move itself. The
implementation keeps the reply plain too. A loss on the opponent's immediate reply ("Leaving the
bishop on b4 under attack, it loses the bishop on b4 at 18.Rxb4") is the move's direct
consequence, and "along the engine line" there would hedge the clearest blunders. It is one
constant (`IMMEDIATE_PLIES`). **The owner confirmed 2 (2026-10-12).**

## 18. Amendment from design packet EA-D (`reasoning-explanation-accuracy-design.md`)

| Change | Reason |
| --- | --- |
| §1 rule 3: `MATERIAL = ("material_loss_v1", "material_gain_v2")` | `material_gain_v1` is replaced (EA-D E1) |
| §1 rule 6: `COMPARISONS` ends with `better_alternative_v1`, taken only when no other comparison is `SUPPORTED`; it is not in `WITH_LINE` | EA-D §3 |
| §5 `phrases_en_v1`: `[material_gain_v2]` (v1's sentences) replaces `[material_gain_v1]`; `[better_alternative_v1] sentence = ["Instead, {best} was better."]`; claim names `material_gain_v2`, `better_alternative_v1`. The phrasebook keeps its name; its digest changes, and the build identity records that (R4-D §2.1) | EA-D §2, §3a |
