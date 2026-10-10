# Reasoning — R3-D design: the explanation plan, the English phrasebook and the guarded renderer

Status: **rev. 2 — English first (owner decision, 2026-10-10); awaiting independent R3-D review**.
Date: 2026-10-10. Base: `main @ 43ce741` (R2b merged, #60). Contracts:
[`reasoning-r0-design.md`](reasoning-r0-design.md) rev. 10 §12–§13 (R0-D), amended in R0-D §30;
claims: [`reasoning-r2-design.md`](reasoning-r2-design.md) rev. 11 (R2-D) as implemented by R2b.

R0-D fixes the plan, the renderer and the guard as contracts. This packet gives what they leave
open: the exact selection rules of `selection_v1`, the sentence order, the English text of every
claim that can be rendered (`phrases_en_v1`), how each slot is bound to a claim's findings, how
two claims joined by an edge become one sentence, and the guard's checks. It changes no claim.

Rev. 1 (`2c5ace7`) was written for Korean. The owner made English the default language; the
Korean wording and particle rules of rev. 1 are the starting point of a later `phrases_ko_v1`
packet (§11).

## 0. Decisions

| # | Decision |
| --- | --- |
| H0 | **English is the default and first language** (owner, 2026-10-10). `AnalysisRequest.language` defaults to `"en"`; R0-D D7 and §13 are amended (R0-D §30). Further languages are further phrasebooks plus their inflection rules (Korean particles, R0-D §13.3). |
| H1 | **One sentence per role, in a fixed order**: judgement, label, primary consequence (with its mechanism), function, comparison, qualification. A label's ground sentence follows the label directly. At most six sentences; each ends with `.`. |
| H2 | **Edges become words only where an edge exists.** A mechanism with `EXPLAINS` to the primary consequence is rendered as the consequence's means ("Through the fork …, it loses …"), never as a cause ("because"); a sacrifice claim renders its `sacrifice_offer_v1` premise (`DERIVED_FROM`) as a concessive lead ("Giving up …, …"). Any other two claims stand in separate sentences without relation words (legacy P12 §12). |
| H3 | **Named, typed slots.** R0-D §13.1's slot types stay (`piece`, `square`, `move`, `amount`, `line`, `depth`, `count`); a variant names slots as `{name}` or, for number agreement, `{name|singular/plural}`. Each template declares its slots' names, types and finding fields (§4). A variant is usable only when all its slots have values (R0-D §13.1), so one key covers optional values (a capture with or without a victim). |
| H4 | **Forms, not only statuses.** Keys are `<template>.<form>`: `sentence` (a SUPPORTED claim as a sentence), `means` (a mechanism before a consequence), `lead` (an offer before a sacrifice claim), `name` (a claim named in the qualification); a kind of a finding selects a suffix (`means.walked`, `sentence.check`). R0-D §13.1's `<template>.<status>` is amended accordingly (R0-D §30). |
| H5 | **SAN with move numbers.** Moves are SAN from fact records (R0-D §13.2), numbered `27.Nd4` / `27...Nd4`; a line is shown up to 6 plies, then `...`. |
| H6 | **No engine numbers in the text.** No centipawns, WDL, ranks or expected points; the grade carries the evaluation. The only numbers are material points, mate distances, depth and counts. (Legacy P12 §13; the owner may revisit.) |
| H7 | **Refuted claims are not rendered.** The qualification names at most two INCONCLUSIVE claims linked by `QUALIFIES` to selected claims, with their reason; a REFUTED mechanism ("not a pin") tells the reader nothing in v1. R0-D §12.2 is narrowed (R0-D §30). |
| H8 | **English terms** (phrasebook data, `phrases_en_v1`; the owner may change them): grades *best move*, *excellent move*, *good move*, *inaccuracy*, *mistake*, *blunder*; labels *great move*, *missed opportunity*; pieces *king*, *queen*, *rook*, *bishop*, *knight*, *pawn*, written as "the knight on d4". |

## 1. The plan (`selection_v1`)

```text
ExplanationPlan(subject, policy: "selection_v1",
    judgement: JudgementRef, label: Label | None,
    purpose: tuple[ClaimId, ...],          # FUNCTION: 0–1, preceded by its offer premise as a lead
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
   larger `MaterialFinding.amount`. Exact claims compete here like any consequence, so a decided
   contrast never silences them (legacy P10 §25.1).
4. **Mechanism**: among SUPPORTED claims with an `EXPLAINS` edge to the selected consequence, the
   first of `fork_v1`, `skewer_v1`, `pin_v1`, `discovery_v1`, `newly_unsafe_v1`,
   `left_en_prise_v1`, `removed_defender_v1`; within a template, the earliest
   `MechanismFinding.node` on the line, then id. `ASSOCIATED_WITH` is never selected (R0-D D12).
5. **Function** (unless filled by rule 2): the first SUPPORTED of `only_move_v1`, `prevents_v1`,
   `sacrifice_compensated_v1`, `sacrifice_sound_v1`, `forcing_v1`. A sacrifice claim brings its
   `sacrifice_offer_v1` premise into `purpose` before it, as its lead (H2). `sacrifice_offer_v1`
   alone is not a function sentence: without soundness or a return, the reader learns only that
   material was given (it remains in the graph).
6. **Comparison** (unless filled by rule 2): `mate_missed_v1`, then `better_move_v1`; the
   justification adds the comparison's best-line window (its first operand) as a `LineRef`.
7. **Qualification**: the effective scopes (R0-D §9.4) of every selected claim, deduplicated and
   in canonical order; then at most two INCONCLUSIVE claims with a `QUALIFIES` edge to a selected
   claim, by role (CONSEQUENCE, MECHANISM, FUNCTION, COMPARISON), then id (H7).

A plan's identity is the sha256 of its canonical encoding (`plan_digest`).

## 2. Sentence order and composition

```text
S1  judgement                       "{move} is a blunder."
S2  label                           "This is a great move."          (when a label exists)
S3  the label's ground              its own sentence form
S4  [mechanism.means] consequence   "Through ..., it loses ..."
S5  [offer.lead] function           "Giving up ..., in return it ..."
S6  comparison (+ its line)         "{best} was better: {line}."
S7  qualification                   "Based on {scopes}." then one sentence per pending claim
```

- A label's ground is rendered once, as S3, and its role's own sentence is skipped.
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
| `amount` | `<n> point` / `<n> points` | `MaterialAmount` |
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
| `material_loss_v1` | `victim` (piece) ← `event.victim`; `capture` (move) ← `MoveRef(event.node)`; `amount` ← `amount` |
| `material_gain_v1` | as `material_loss_v1`; a promotion has no `victim`, and the variant without it is used |
| `forcing_v1` | `count` ← `ForcingFinding.replies`; suffix `check` / `single` |
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
great = ["This is a great move."]
miss = ["This is a missed opportunity."]

[mate_delivered_v1]
sentence = ["It is checkmate."]
[mate_found_v1]
sentence = ["It forces mate in {count} along {line}."]
[mate_in_one_allowed_v1]
sentence = ["It allows mate in one with {reply}."]
[mate_allowed_v1]
sentence = ["It allows mate in {count} along {line}."]
[mate_missed_v1]
sentence = ["There was mate in {count} with {best}."]

[material_loss_v1]
sentence = ["It loses {victim} at {capture} ({amount})."]
[material_gain_v1]
sentence = ["It wins {victim} at {capture} ({amount}).",
            "It promotes at {capture} ({amount})."]

[forcing_v1]
"sentence.check" = ["It gives check and forces the reply."]
"sentence.single" = ["It leaves the opponent a single legal reply."]
[only_move_v1]
sentence = ["Every other move, including {second}, is clearly worse."]
[prevents_v1]
"sentence.mate" = ["The other {count|move/moves} the engine reported all allow mate."]
"sentence.material" = ["The other {count|move/moves} the engine reported all lose at least {amount}."]
"sentence.mixed" = ["The other {count|move/moves} the engine reported all allow mate or lose material."]
[sacrifice_offer_v1]
lead = ["Giving up {victim} ({amount}),"]
[sacrifice_sound_v1]
sentence = ["The engine still rates the position as holding."]
[sacrifice_compensated_v1]
"sentence.mate" = ["In return it mates faster than any move that keeps the material."]
"sentence.material_return" = ["In return it wins back more than any move that keeps the material."]

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

[scope]
"engine.specific_line" = ["the engine line at depth {depth}"]
"engine.all_alternatives.engine_ranked" = ["the engine's full search at depth {depth}"]
"engine.all_alternatives.engine_reported" = ["the {count|move/moves} the engine reported"]
"engine.exists_alternative.engine_reported" = ["the {count|move/moves} the engine reported"]
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
```

Notes:
- `{grade}` is never a slot: each grade has its own key (H6, no number).
- `NOT_COMPUTED(<parameter>)` reads `reason.NOT_COMPUTED` (the parameter is internal).
- A scope of basis `EXACT` has no phrase: exact facts are not qualified.
- `only_move_v1` does not state the 0.20 threshold (H6); "clearly worse" is its rendering of
  R0-D D10.
- Scopes are joined as an English list: `A`, `A and B`, `A, B and C`.

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
| G4 | a claim not SUPPORTED in `purpose`, `mechanism`, `consequence` or `justification`; a mechanism without an `EXPLAINS` edge to the plan's consequence; a lead that is not the function claim's premise |
| G5 | a key, form or slot outside `phrases_en_v1`; a variant whose slots are not all bound; a `sentence` form beginning with a slot |

`RenderedExplanation(plan_digest, language: "en", phrasebook: "phrases_en_v1", segments)`;
`text` is the concatenation of the segments' text.

## 8. Golden examples (expected output of the acceptance tests)

Built from R2b's test scenarios.

1. **Blunder allowing a fork** (R2-D §3.7: 1.a3 Bc5 2.b5 Be7 3.b6 Nf3+ 4.Ke2 Nxd4+):
   `1.a3 is a blunder. Through the fork by the knight on f3 at 3...Nf3+, it loses the knight on
   d4 at 4...Nxd4+ (3 points). Instead, 1.Nb3 was better: 1.Nb3 Ne6 2.Kd2 Kd7. Based on the engine
   line at depth 12 and piece safety judged by attackers and defenders, without exchange
   evaluation.`
2. **Missed mate after the opponent's blunder** (MISS; the label's ground `better_move_v1` fills
   the comparison, so `mate_missed_v1` is not rendered): `2.h3 is a blunder. This is a missed
   opportunity. Instead, 2.Qe8+ was better: 2.Qe8+ Rxe8 3.Rxe8#. Based on the engine line at
   depth 12.`
3. **Only move** (GREAT; the label's ground takes the one function slot, so the sacrifice claims
   stay in the graph): `1.Qe8+ is the best move. This is a great move. Every other move,
   including 1.h3, is clearly worse. It forces mate in 2 along 1.Qe8+ Rxe8 2.Rxe8#. Based on the
   engine's full search at depth 12 and the engine line at depth 12.`
4. **Mate delivered** (exact): `1.Ra8# is the best move. It is checkmate.`
5. **Judgement inconclusive with an exact claim**: `1.Rc1 could not be judged (the engine gave no
   win/draw/loss figures). It allows mate in one with 1...Rxc1#.`

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
7. **Golden examples** of §8 on R2b's scenarios, and a determinism re-run (same bytes).

## 10. Relation to R0-D (amended in R0-D §30)
- D7, §1.2, §3.2, §5, §13: English first (`language = "en"`, `render/phrases/en.toml`,
  `phrases_en_v1`); Korean particles (§13.3) apply when the Korean phrasebook is added.
- §12.2: refuted claims are not rendered (H7); the offer is a lead, not a function (§1 rule 5).
- §13.1: named typed slots and forms (H3, H4).
- §13.2: English piece names; `SearchRef(s, k)` renders its first move; a witness UCI renders
  through `status`.

## 11. Open
- Owner choices: the English terms of H8 and the wording of §5 (data, versioned).
- Rendering engine numbers (H6) is deferred.
- **Korean** (`phrases_ko_v1`): a later packet; rev. 1 of this document (`2c5ace7`, §5–§6) holds
  its draft wording and the particle rules of R0-D §13.3 applied to it.
