# Reasoning — EA-D design: explanation accuracy (material gains, the better move)

Status: **rev. 2 — independent review NOT_READY applied (§9)**.
Date: 2026-10-12. Base: `main @ b7ffa4c`. Inputs:
[`reasoning-r2-design.md`](reasoning-r2-design.md) (R2-D §1.3 window and outcome, §3.2
`material_gain_v1`, §3.12 `better_move_v1`, §4); [`reasoning-miss-v2-design.md`](reasoning-miss-v2-design.md)
(MV-D: `missed_gain_v1`, `MISS_LOSS`); [`reasoning-r3-design.md`](reasoning-r3-design.md) (R3-D:
`selection_v1`, `phrases_en_v1`).

The owner read the explanations of two of their games and found sentences that state something
false, and inaccuracies that name no better move. This packet fixes both. It adds no positional
reasoning; that is a later packet (§8).

## 0. Evidence (the owner's games)

Two `calliope_result_v1` documents: the 829/808 game of 2026-10-12 (`g1012`) and the 836/829
game analysed through the server the same day (Caro-Kann Advance). Stockfish 19, `d12_mpv5_v1`.

### 0.1 Gains that are not gains

`material_gain_v1` (R2-D §3.2) reads `Lp` alone: when the material at the end of its window
(10 plies) is `STABLE` and ahead by `Δ ≥ 1`, it is `SUPPORTED`. It never asks whether the engine
counts that material as an advantage.

- **3.e5** (best): "Along the engine line, it wins the pawn on c5 at 4.dxc5 (net material gain
  over the line: at least 1 point)."
  - `Lp` = 3...c5 4.dxc5 Nc6 5.Bb5 e6 6.Bxc6+ bxc6 7.Qd4 Ne7 | 8.Nf3 Nf5: White is a pawn up
    where the window ends.
  - Continued from that point, Black takes the pawn back: depth 12 …Bxc5, depth 20 and 24
    …Rxb2; the material is equal 16 plies later, at +0.47 / +0.32 / +0.26.
  - The line's score is +0.51 for White: the engine does not count the pawn.
  - In the game Black played 3...Bf5; at depth 22, 3...Bf5 (+0.32) and 3...c5 (+0.36) are
    equal choices. The "win" is a pawn Black may give back for play, not one White wins.
- **10.O-O** (best): "it wins the bishop on c3 at 13.bxc3 (… at least 1 point)". `Lp` = 10...c5
  11.dxc5 Nc6 12.a3 Bxc3 13.bxc3; balances 0,0,0,1,1,1,−2,1,1,1,1. The +1 is the c5 pawn; the
  bishop recaptures a knight. Score −0.13 for White.
- **31.g3** (inaccuracy, 2.16 → 0.24): "it wins the pawn on a4 at 32.Qxa4" while the move throws
  away the advantage.

### 0.2 Every supported gain in the two documents

The event ply is the decisive event's ply in `Lp` (1 = the move itself), counted from the
move and the event's move number; the score is `Lp`'s, for the mover, in centipawns.

| Game | Move | Grade | Gain (points) | Event ply | Score | Sound? |
| --- | --- | --- | --- | --- | --- | --- |
| 836/829 | 3.e5 | best | 1 | 3 | +51 | no (§0.1) |
| 836/829 | 10.O-O | best | 1 | 7 | −13 | no |
| 836/829 | 31.g3 | inaccuracy | 1 | 3 | +24 | no |
| g1012 | 2...Nc6 | best | 1 | 5 | −33 | no (the line scores below the gain) |
| g1012 | 5...exd4 | good | 1 | 5 | −15 | no (likewise) |
| g1012 | 13...Bb4 | mistake | 1 | 11 | +59 | doubtful (a mistake that "wins") |
| 836/829 | 24.Rfb1 | best | 1 | 9 | +121 | yes |
| 836/829 | 18.Nxb7 | best | 2 | 9 | +208 | yes |
| 836/829 | 29.cxb5 | best | 2 | 7 | +376 | yes |
| g1012 | 45.b7 | good | 2 | 3 | +877 | yes |
| g1012 | 32.Ne8+ | best | 1 | 3 | +724 | yes |
| g1012 | 44.Ka7 | best | 7 | 5 | +1240 | yes |
| g1012 | 18.Rxb4, 27.Nxc7, 33.Nxg7, 46.Kxb7 | best | 3, 1, 1, 2 | 1 | +571 … +949 | yes |
| g1012 | 36...Bxg2 | best | 1 | 1 | −784 | yes (a real capture in a lost position) |
| 836/829 | 39...Qxe8 | best | 9 | 1 | +453 | yes |

Two observations decide the rule (§1):
- Every false gain happens later in the line (event ply ≥ 3), with a score at or below +0.59
  per point gained. Every sound later-line gain scores at least +1.04 per point.
- A gain made by the move itself (event ply 1) is a fact of the board, whatever the score:
  36...Bxg2 takes a pawn in a lost position. An absolute score rule would refute it.

### 0.3 Inaccuracies with no better move

| Move | Loss (1/2000) | Text |
| --- | --- | --- |
| 4.f4 | 168 | "Instead, 4.Be2 was stronger." (`missed_gain_v1`) |
| 7.Nc3 | 105 | "7.Nc3 is an inaccuracy." |
| 9.Nh4 | 146 | "9.Nh4 is an inaccuracy." |

`missed_gain_v1` needs `loss ≥ MISS_LOSS` (160; MV-D), and `better_move_v1` (R2-D §3.12) is
`REFUTED` when the lines differ in neither mate nor material. Below 160 and without a material
difference, nothing names the better move, although the judgement already proves that it exists.

## 1. Decisions

| # | Decision |
| --- | --- |
| E1 | **`material_gain_v2` replaces `material_gain_v1`** in the shipped catalogue. Rules 1–2 and the `Δ` test of v1 are kept; one rule is added (§2). |
| E2 | **A later-line gain must not contradict the engine's score.** When the decisive event is not the move itself (event ply ≥ 3), `Lp`'s score for the mover must be at least `GAIN_CP_PER_POINT × amount`, with `GAIN_CP_PER_POINT = 80`. Otherwise the claim is `REFUTED`. The rule is an empirical filter, not a proof that the material is kept (§2). |
| E3 | **A gain made by the move itself is unchanged** (event ply 1): it is a capture or promotion on the board, kept as v1 decides it. |
| E4 | **`better_alternative_v1`**, a new COMPARISON: for a move graded INACCURACY or worse that is not rank 1 of S, "Instead, {best} was better." It is the planner's last comparison, used only when no other is `SUPPORTED`. |
| E5 | **The event rule is not changed** (§5): naming the capture that made a gain across exchanges needs more than a balance rule, and the cases that went wrong are refuted by E2 anyway. |
| E6 | **Versioned, not edited.** The threshold is part of `material_gain_v2`; a new value is a new template version. The build identity changes, so stored claim graphs of the old build are re-analysed, never re-read (R4-D §2.1; the server's cache misses, AS-D §4). |

## 2. `material_gain_v2` (R2-D §3.2, amended)

- **Target, context, operands, proposal, findings, evidence:** as v1.
- **Verify:**
  1. Rules 1–2 of R2-D §3.1, unchanged (`material.played_line_rules`): a mate line →
     `INCONCLUSIVE(MATE_LINE)`; a missing, open or drawn window → `INCONCLUSIVE`. A mate line is
     any `Lp` whose `EngineLineFact.score` is a `Mate`, for either side, or whose window ends in
     checkmate (`lines._outcome` makes both `OutcomeKind.MATE`); so a mate, for the mover or
     against it, is decided here and never reaches rule 3 (review B1).
  2. With `ΔB` as in v1: `STABLE(Δp)` with `min(Δp, ΔB) < 1` → `REFUTED`.
  3. Let `q` be the decisive event's ply (`decisive_ply`, unchanged) and
     `amount = min(Δp, ΔB)`. If `q ≥ 3` and `score_m(Lp) < GAIN_CP_PER_POINT × amount` →
     `REFUTED`. Here `score_m(Lp)` is `Lp`'s engine score in centipawns for the mover `m`.
     Rule 3 is reached only with a `STABLE` outcome, hence a `Cp` score (rule 1).
  4. Otherwise → `SUPPORTED`, as v1.
- **Why the score of `Lp` and not a difference.** The score before the move already contains a
  win the opponent left hanging (18.Rxb4 after 17...Be8: +5.71 before and after), so a
  difference would refute sound gains. The score of the line, per point, separates the cases of
  §0.2: the largest false gain scores +59 per point, the smallest sound later-line gain +104.
  80 lies between them.
- **What the rule is (review, non-blocking).** It filters out a gain sentence that the engine's
  own score plainly contradicts; it does not prove that the material is kept. A line may end a
  pawn up and score high for positional reasons while the pawn is given back later, and the
  rule then lets the sentence through, as v1 does. The value 80 separates the 19 cases of §0.2;
  it is not shown to separate every game. A new value, or a better test (for example a check of
  the material past the window), is a new template version (E6).
- **Why only `q ≥ 3`.** At `q = 1` the move itself captures or promotes, and the window is
  `STABLE` (the capture is not undone within it). The score then says how good the position is,
  not whether the capture happened (36...Bxg2, −7.84).
- **Score source.** `Lp`'s `EngineLineFact.score` (S, `played` of the judgement); `Cp` values in
  White's view are turned to the mover's. The rule reads S alone, like v1 (R2-D §4: no template
  compares two searches).
- **Phrases.** `phrases_en_v1` gains `[material_gain_v2]` with v1's sentences and the claim
  name `material_gain_v2 = ["material gain"]`; v1's section and claim name are removed with the
  v1 template. No v1 claim is ever rendered again: a stored graph of the old build is refused
  (E6), and the renderer binds only the shipped templates (§3a).

## 3. `better_alternative_v1` — COMPARISON, backward

- **Proposed when:** the judgement is decided, its grade is INACCURACY or worse, and the played
  move is not rank 1 of S.
- **Target:** `EXISTS_ALTERNATIVE` at P over `ENGINE_REPORTED(S)`, as `missed_gain_v1`.
- **Verify:** the judgement's best line is rank 1 and its loss is positive → `SUPPORTED`;
  otherwise `REFUTED`.
- **Findings:** `MissedGainFinding(SearchMoveRef(S, best.rank, 1), loss)` (the same finding type
  as `missed_gain_v1`; the planner and renderer tell them apart by template).
- **Evidence:** `SearchRef(S, best.rank)`, `SearchRef(S, played.rank)`.
- **Scope:** the engine-reported moves of S, as `missed_gain_v1` ("Based on the N moves the
  engine reported").
- **Phrase:** `[better_alternative_v1] sentence = ["Instead, {best} was better."]`.
- **Planner (`selection_v1`, R3-D §1 rule 6):** `COMPARISONS` becomes `("mate_missed_v1",
  "better_move_v1", "missed_gain_v1", "better_alternative_v1")`; the first `SUPPORTED` one is
  taken, so the new claim speaks only when the others do not. It never grounds a label: MISS
  keeps `missed_gain_v1` and its threshold (MV-D).

## 3a. Code changes (the contract of EA1; review B2)

Every place that names a template, so that both new claims are proposed, selected, bound and
phrased. A template that `render.bind` cannot bind raises `GuardError` (G5); one the planner's
tables do not name is verified but never said.

| Place | Today | EA1 |
| --- | --- | --- |
| `catalogue/material.py` | `MaterialGain`, `name = "material_gain_v1"` | replaced by the v2 template (`name = "material_gain_v2"`, rule 3 of §2, `GAIN_CP_PER_POINT = 80` beside it); `played_line_rules` unchanged |
| `catalogue/comparison.py` | `BetterMove`, `MissedGain` | adds `BetterAlternative` (§3) |
| `catalogue/__init__.py` | `CATALOGUE_V1`: … `MaterialGain()` … `MissedGain()` | the v2 template in v1's place; `BetterAlternative()` right after `MissedGain()`. The constant keeps its name: the build identity records the template list by name and version (`build.reasoning_build`), not the constant |
| `catalogue/mechanisms.py` | `CONSEQUENCES = ("material_loss_v1", "material_gain_v1")`; `RelationDecl(EXPLAINS, "material_gain_v1")` | `material_gain_v2` in both |
| `planner.py` | `MATERIAL = ("material_loss_v1", "material_gain_v1")` (rule 3) | `("material_loss_v1", "material_gain_v2")` |
| `planner.py` | `COMPARISONS = ("mate_missed_v1", "better_move_v1", "missed_gain_v1")` (rule 6) | `better_alternative_v1` appended; `WITH_LINE` unchanged (the new claim has no line operand) |
| `render/__init__.py` `bind` | `t in ("material_loss_v1", "material_gain_v1")`; `t == "missed_gain_v1"` binds `best` from `MissedGainFinding` | `("material_loss_v1", "material_gain_v2")`; `t in ("missed_gain_v1", "better_alternative_v1")` binds `best` the same way |
| `render/phrases/en.toml` | `[material_gain_v1]`, `[missed_gain_v1]`; `[claim]` names | `[material_gain_v2]` (v1's sentences) replaces `[material_gain_v1]`; `[better_alternative_v1] sentence = ["Instead, {best} was better."]`; `[claim]` gains `material_gain_v2 = ["material gain"]` and `better_alternative_v1 = ["better alternative"]`, loses `material_gain_v1`. The scope phrase `engine.exists_alternative.engine_reported` is reused |
| `labels.py` | MISS (`miss_p2`) grounds on `missed_gain_v1` | unchanged (§3) |
| `build.py` | — | unchanged; the digest changes through the template list and the phrasebook's file digest (E6) |

## 4. What changes in the two games

Computed from the documents of §0 by the rules above (to be confirmed by re-running both games
in EA1, §6):

| Move | Before | After |
| --- | --- | --- |
| 3.e5 | "… wins the pawn on c5 at 4.dxc5 …" | the sentence is gone (+51 < 80) |
| 10.O-O | "… wins the bishop on c3 at 13.bxc3 …" | gone (−13) |
| 31.g3 | "… wins the pawn on a4 at 32.Qxa4 …" | gone (+24); "Instead, 31.Qc1 was stronger." stays |
| 2...Nc6, 5...exd4, 13...Bb4 (g1012) | a gain sentence | gone (−33, −15, +59) |
| 7.Nc3 | "7.Nc3 is an inaccuracy." | "… Instead, 7.Nbd2 was better." |
| 9.Nh4 | "9.Nh4 is an inaccuracy." | "… Instead, 9.O-O was better." |
| the other gains of §0.2 | unchanged | unchanged |

## 5. Not changed, recorded

- **The decisive event across exchanges.** For 10.O-O the rule "the first ply where the balance
  reaches its final level and stays positive" names 13.bxc3, a recapture, while the gain is
  11.dxc5. Taking instead "the first ply that reaches the final level" names 11.dxc5 there, but
  names a rook capture inside a rook exchange for 24.Rfb1 (balances 0,0,−1,0,0,5,0,5,0,1,1,1,
  where today's rule correctly names 28.Qxa4). A correct rule pairs captures and recaptures on a
  square; it is left for a later packet, with these two cases as its tests. After E2 neither
  wrong sentence of §0 remains.
- **`material_loss_v1`** keeps its rules: a loss along the line is what the engine predicts
  against the mover, and no false loss was reported.
- **Positional reasons** (why 7.Nc3 or 9.Nh4 is worse, 33.b6's perpetual check, light-square
  weakness) and opening knowledge: §8.

## 6. Test obligations (packet EA1)

1. **`material_gain_v2` rules** (scripted lines): a later-line gain (event ply 3) with the line
   scored +50 for one point → `REFUTED`; +80 → `SUPPORTED` (the boundary is inclusive); +150
   for two points → `REFUTED`, +160 → `SUPPORTED`; the same +50 with the event at ply 1 →
   `SUPPORTED`; a Black mover (scores turned); a mate score for the mover and a mate score
   against the mover, each with a material gain at ply 3 → `INCONCLUSIVE(MATE_LINE)` (rule 1,
   review B1); rules 1–2 otherwise as v1.
2. **`better_alternative_v1`:** proposed for an inaccuracy at rank 2 with loss below
   `MISS_LOSS`; not proposed for rank 1, a GOOD move, or an inconclusive judgement; when
   `missed_gain_v1` is also `SUPPORTED`, the planner takes `missed_gain_v1` and the text has one
   "Instead" sentence.
3. **Mechanisms** that took `material_gain_v1` as premise take `material_gain_v2` (fork, pin,
   skewer, discovery for the mover): the existing mechanism tests pass with the new name.
4. **Corpus** (R4-D §4): `promotion.toml` expects `material_gain_v2`; every other case keeps its
   texts, or the record lists each change with its reason.
5. **The owner's two games** re-run with Stockfish 19: the changes are exactly those of §4, and
   the record lists every changed sentence of both games.
6. **Build identity:** the build digest changes; a v1 claim graph is refused by `load` with the
   build message (re-analysis, not re-reading).
7. **Through the renderer (review B2):** for a position where `material_gain_v2` is the selected
   consequence, and one where `better_alternative_v1` is the selected comparison: `explain()`
   returns the expected sentence, `trace()` returns the same texts with the references each
   sentence names (the capture and its victim; the better move), and the
   `calliope_result_v1` document built from the analysis has no `schema_errors`.
8. **Coverage of the tables:** every template of `CATALOGUE_V1` has a `[claim]` name and is
   bound by `render.bind` without `GuardError` (a test over the catalogue, so a later template
   cannot be left out); the planner's tables name only catalogue templates.

## 7. Delivery

| Packet | Content | Gate |
| --- | --- | --- |
| EA-D (this) | the two rules, their evidence | independent review READY |
| EA1 | `material_gain_v2`, `better_alternative_v1`, the planner and phrasebook entries, tests, the two games re-run | READY |

## 8. After this packet (not designed here)

- **Explanation v2**: consequences beyond material and mate — a line that ends in a draw by
  perpetual check (33.b6: 33...Qe2 … Qe2+, 0.00 against +5.33 for 33.Qc2), a best move that
  denies a square the opponent's line uses (33.Qc2 covers e2), and positional facts the fact
  engine already computes (a pin on c3, a blocked c-pawn, a knight on the rim, doubled or
  isolated pawns), with a rule for when such a fact may be said to explain a loss.
- **Square-colour weakness** (White without a light-squared bishop, light squares around the
  king after 31.g3): new facts.
- **Opening knowledge**: opening names (a public ECO table) and, with frequency data, "leaves
  the main lines".
- **The decisive event across exchanges** (§5).

## 9. Review dispositions

Independent review of rev. 1 (HEAD `914d9de`): **NOT_READY**, two blocking findings.

| Finding | Disposition |
| --- | --- |
| **B1** rule 3 counted a mate against the mover as below the threshold, and §6 expected `REFUTED`; but `lines._outcome` makes every `Mate` score `OutcomeKind.MATE` and `played_line_rules` returns `INCONCLUSIVE(MATE_LINE)` first, so rule 3 is never reached | Accepted, the smallest change: rule 1 decides every mate line, for either side, as in v1; the mate clause is removed from rule 3, which now states that it sees only `STABLE` lines with a `Cp` score (§2); §6.1 expects `INCONCLUSIVE(MATE_LINE)` for both mates. No false gain follows: a mate line never says a gain |
| **B2** the planner's `MATERIAL`, the renderer's `bind` and the phrasebook name templates; the design did not say how they change, so `material_gain_v2` could be verified but not selected, and either new claim could fail G5 | Accepted: §3a lists every place and its change; §6.7 requires `explain()`, `trace()` and the result document for both new claims; §6.8 adds a test that every catalogue template is named and bound |
| Non-blocking: 80 per point is an empirical filter against a contradicting score, not a sufficient condition | Accepted: E2 and §2 ("What the rule is") say so |
| Own correction while applying B2 | rev. 1 kept `[material_gain_v1]` in the phrasebook "to render a v1 graph"; `render.bind` will not bind v1 and no v1 graph is re-read, so the section and its claim name are removed (§2, §3a) |

The review did not re-run the games; §6.5 keeps that for EA1.
