# Reasoning — packet R3 implementation: plan, `phrases_en_v1`, renderer and guard

Status: **rev. 1 — awaiting independent review**.
Date: 2026-10-11. Design: [`reasoning-r3-design.md`](reasoning-r3-design.md) rev. 5 (R3-D, re-review
READY, #61). Base: `main @ f4465c6`.

## 1. Scope delivered

| Module | Content |
| --- | --- |
| `reasoning/planner.py` (new) | `ExplanationPlan` and `plan()`: `selection_v1`, rules 1–7 of R3-D §1, with the priority tables as constants. `plan_digest()`. |
| `reasoning/render/__init__.py` (new) | The renderer: `render(plan, analysis)`, `explain(analysis)`, `Segment`, `RenderedExplanation` (with `label_rule` and `label_provisional`). Also the `Handle` (G1, G3), the slot formatters of §3, the bindings of §4, variant choice (§6), sentence composition (§2) and G4 / G5. |
| `reasoning/render/phrases/en.toml` (new) | `phrases_en_v1`: R3-D §5 verbatim, plus six claim names (§2.2) |
| `reasoning/request.py` | `language` defaults to `"en"`, and `LANGUAGES = ("en",)` (R0-D §30) |
| `reasoning/encoding.py` | `ExplanationPlan` joins the registry, for `plan_digest` |
| `reasoning/__init__.py` | exports `ExplanationPlan`, `plan`, `plan_digest`, `RenderedExplanation`, `Segment` and `explain` |

## 2. Implementation decisions and deviations
1. **`GuardError`** is the existing `reasoning.errors.GuardError` (R0-D §13.4), not a second
   class.
2. **Six more claim names** in `[claim]`: `mate_delivered_v1`, `mate_found_v1`,
   `mate_in_one_allowed_v1`, `mate_allowed_v1`, `forcing_v1` and `sacrifice_offer_v1`. The design's
   list left them out.
   - Without them, a pending claim of these templates would fail G5.
   - This is data, not wording of a SUPPORTED claim.
3. **G5's slot-start check** applies to claim `sentence` forms, which can follow a lead or a means
   and are then lowercased (R3-D §2). Judgement, label and scope phrases start a sentence of their
   own, and the judgement's begins with `{move}` by design.
4. **Rule 7 qualifies what is rendered.**
   - BRILLIANT's pair is qualified, since both claims are rendered.
   - A MISS ground that is not rendered is not qualified. When `better_move_v1` is chosen,
     `missed_gain_v1` is left out.
   - Example 2 depends on this reading: "Based on the engine line at depth 12." only.
5. **`plan()` takes `ply_of`** to order mechanisms of one template by their node (rule 4). The
   planner itself never reads the tree. `explain()` passes the view's node ply.
6. **The package exports `explain`, not `render`.** A package-level `render` function would shadow
   the `calliope.reasoning.render` subpackage, and a test caught it. `render` stays at
   `calliope.reasoning.render.render`.
7. **Piece names come from the node's FEN** (`FrameNode.fen`), which every node has. The
   `pieces` facts are not ensured at every referenced node. FEN reads a promoted pawn as its new
   type, as R3-D §3 asks.
8. **`SearchMoveRef` beyond ply 1 is refused (G3).** No v1 claim cites one. R0-D §13.2's
   attached-edge route for deeper plies is left for when a claim needs it.
9. **The scope sentence's source** is the `ScopeRef` of its single scope, or the tuple of
   `ScopeRef`s when several scopes are joined.

## 3. Evidence

### 3.1 Tests (`tests/reasoning/test_render.py`, 28 tests)

| R3-D §9 obligation | Tests |
| --- | --- |
| 1 planner | the plan of the fork (roles, the justification's line, `plan_digest`); an `ASSOCIATED_WITH` mechanism never selected; a decided judgement alone; the label grounds first (GREAT → purpose, MISS → `better_move_v1` before `missed_gain_v1`) |
| 2 composition | means + consequence lowercased (the fork); lead + function (a sacrifice with a derived lead); the label sentence and its ground; empty roles skipped (examples 3, 4, 7) |
| 3 slots | numbered SAN from edges and from `SearchRef`; a witness UCI (example 5); a line of 4 plies; a promotion; a piece named from FEN |
| 4 inflection | `1 move` / `2 moves`; `1 point` / `3 points`; scope lists of one, two and four |
| 5 variants | deterministic choice; unusable variants skipped; an unknown key and an empty usable set refused |
| 6 guard | a REFUTED claim in a role; a mechanism without `EXPLAINS`; another claim's reference (G3); a node outside the handle (G1); a sentence form beginning with a slot (G5) |
| 7 golden | examples 1–4, 5, 5b, 6–8 verbatim, each rendered twice to the same segments and digest |
| 8 rev. 3 | BRILLIANT renders the pair and suppresses the three R2-D sacrifice claims; `piece_offer_v1` alone in a role and a BRILLIANT label without its pair are refused; a `missed_gain_v1` without MISS says "stronger" only; `rescue_v1` as the function; `label_rule` / `label_provisional`; the same grade sentence under `quality_v1` and `quality_v2` |
| 9 rev. 4 | `forcing_v1`: `check`, `check_single` and `single`, from positions (a check with three replies never says "forces" or "single"); INCONCLUSIVE + FORCED (5b); example 8 without a pending sentence |
| 10 rev. 5 | a promotion says "promotes" and not "wins"; a capture says "wins" and not "promotes"; "The engine line leads to mate"; the compensated-mate phrase has no "faster"; a stored lead (two claims in `purpose`) is refused |

**Not covered by a single scenario:** a plan filling all six roles with two pending claims (the
nine-sentence case of test 9). The cap holds by construction: S1–S6 emit at most one sentence each,
S7 one scope sentence and `MAX_PENDING = 2`. The tests check the bound on rendered output, not the
full case.

| Suite | Result |
| --- | --- |
| `tests/reasoning`, `tests/tools`, `tests/test_package_boundaries.py`, `tests/facts/test_exchange.py` | 398 passed, 1 skipped (gated Stockfish) |

### 3.2 Real games (Stockfish 19, depth 12)

`explain()` ran on every ply of the two Q3 §6 games: 1700 / 1724 (100 plies) and 821 / 814 (73
plies), with the full reasoner. **No ply raised an error**, and every text passed the guard.
Samples (1700 game):

> 9.Bxe7 is a mistake. This is a missed opportunity. Instead, 9.Bf6 was stronger. Based on the 5
> moves the engine reported.
>
> 14.f4 is a mistake. It loses the pawn on h2 at 19...Bxh2 (1 point). Instead, 14.Qa4+ was better:
> 14.Qa4+ Kf8 15.O-O Rd8 16.Be4 Nxd3 .... Based on the engine line at depth 12.

**Two wording problems of `phrases_en_v1` that real lines expose** (open, §4):
1. **The material sentence reads as the victim's value.**
   - `{amount}` is the line's net balance (`MaterialFinding.amount`). `{victim}` is the decisive
     capture's victim.
   - Joined in "It wins {victim} at {capture} ({amount})", they read as "the pawn on h6 (5
     points)". 14 of the 821 game's material sentences are like that, for example "wins the rook
     on d5 at 22.Qxd5 (2 points)".
   - The claim is right. The sentence suggests a value the claim does not state.
2. **A truncated line ends its sentence with four dots** ("11.O-O-O ...."): H5's " ..." meets
   the sentence's ".".

## 4. Open for review
- **The two wording problems of §3.2.** Both are text of `phrases_en_v1`, and nothing has been
  rendered for users yet. A fix before merge would be a small amendment of R3-D §5. Candidates:
  - **material:** "It ends {amount} ahead; the decisive capture is {capture}, taking {victim}." The
    loss and promotion forms follow the same pattern.
  - **truncated line:** no closing "." after a line that ends in "...".
  
  The owner decides. This rev. 1 renders R3-D rev. 5 as reviewed.
