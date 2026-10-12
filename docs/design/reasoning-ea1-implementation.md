# Reasoning — packet EA1 implementation: explanation accuracy

Status: **rev. 1 — independent implementation review READY; notes N1, N2 applied (§4)**.
Date: 2026-10-12. Design: [`reasoning-explanation-accuracy-design.md`](reasoning-explanation-accuracy-design.md)
rev. 2 (EA-D, review NOT_READY applied, re-review READY, #87). Base: EA-D's branch at `0ebd120`
(`main @ b7ffa4c` and the design commits).

## 1. Scope delivered (EA-D §3a)

| Place | Change |
| --- | --- |
| `reasoning/catalogue/material.py` | `MaterialGain` is `material_gain_v2`: after v1's rules, a decisive event at ply ≥ 3 with `score_m(Lp) < GAIN_CP_PER_POINT × amount` is `REFUTED` (`GAIN_CP_PER_POINT = 80`, beside the template). `_score_for` turns `Lp`'s `Cp` (White's view) to the mover's. `played_line_rules` unchanged: every mate line stops at rule 1 (review B1) |
| `reasoning/catalogue/comparison.py` | `BetterAlternative` (`better_alternative_v1`, COMPARISON, backward): proposed for a decided judgement graded INACCURACY or worse whose played move is not rank 1; SUPPORTED when rank 1 is the best line and the loss is positive; finding `MissedGainFinding`; witness rank 1's move |
| `reasoning/catalogue/__init__.py` | `CATALOGUE_V1`: `material_gain_v2` in v1's place; `better_alternative_v1` after `missed_gain_v1` (26 templates) |
| `reasoning/catalogue/mechanisms.py` | `CONSEQUENCES` and the `EXPLAINS` relation name `material_gain_v2` |
| `reasoning/planner.py` | `MATERIAL = ("material_loss_v1", "material_gain_v2")`; `COMPARISONS` ends with `better_alternative_v1`; `WITH_LINE` unchanged |
| `reasoning/render/__init__.py` | `bind`: `material_gain_v2` shares the material branch; `better_alternative_v1` binds `best` as `missed_gain_v1` does |
| `reasoning/render/phrases/en.toml` | `[material_gain_v2]` replaces `[material_gain_v1]` (same sentences); `[better_alternative_v1] sentence = ["Instead, {best} was better."]`; claim names `material_gain_v2 = ["material gain"]`, `better_alternative_v1 = ["better alternative"]`; `material_gain_v1` removed |
| `docs/design` | R2-D §14 and R3-D §18 record the amendments |

`labels.py` and `build.py` are unchanged: MISS still grounds on `missed_gain_v1`, and the build
digest changes through the template list and the phrasebook digest.

## 2. Implementation notes
1. **The event ply.** Rule 3 reads `DecisiveEvent.ply`, the same event the sentence names. A gain
   cannot be decided on the opponent's ply, so "ply ≥ 3" and "not the move itself" are the same.
2. **The refuted evidence** is v1's (`SearchRef(S, Lp.rank)`, `Lp`'s window): the score rule 3
   reads is that line's fact, already cited.
3. **`better_alternative_v1`'s verify** re-reads the judgement, as `missed_gain_v1`, and refutes
   when rank 1 is not the best line, the played move is rank 1, or the loss is not positive.
   The grade is the proposer's condition (EA-D §3).
4. **The constant `CATALOGUE_V1` keeps its name** (EA-D §3a): the build identity records the
   template names and versions, so a v1 graph is refused whatever the constant is called.

## 3. Evidence

### 3.1 Tests (EA-D §6)

| Obligation | Test |
| --- | --- |
| 1 rules of `material_gain_v2` | `tests/reasoning/test_explanation_accuracy.py`: one pawn at ply 3, +50 / +79 → `REFUTED`, +80 → `SUPPORTED` (amount 1, event ply 3); two pawns, event ply 5, +150 / +159 → `REFUTED`, +160 → `SUPPORTED`; 1.Nxd5 at +50 (ply 1) → `SUPPORTED`; Black mover, the scripted +50 / +80 for Black (−50 / −80 from White's view) → `REFUTED` / `SUPPORTED`; a mate score for either side → `INCONCLUSIVE(MATE_LINE)`; a refuted gain has no sentence. Rules 1–2 and the v1 cases: `test_catalogue_consequences.py` under the new name |
| 2 `better_alternative_v1` | an inaccuracy (loss 120 < `MISS_LOSS`): `SUPPORTED`, finding (rank 1, ply 1, 120), witness `e1d2`, `EXISTS_ALTERNATIVE`, text "2.a3 is an inaccuracy. Instead, 2.Kd2 was better. Based on the 2 moves the engine reported.", no label; not proposed for a GOOD move (loss 60), the best move, or a judgement without WDL; with `missed_gain_v1` (loss 170) the plan takes `missed_gain_v1` and the text has one "Instead"; with `better_move_v1` (the fork blunder) the plan takes `better_move_v1` |
| 3 mechanisms | `test_catalogue_mechanisms.py` (skewer `EXPLAINS` `material_gain_v2`) and the other mechanism tests pass under the new name |
| 4 corpus | `promotion.toml` expects `material_gain_v2`; every other case's text is unchanged. Two new cases: `later_gain` (a later-line gain at +80, the sentence "Along the engine line, it wins the pawn on d5 at 2.Nxd5 …") and `better_alternative` (the inaccuracy above) |
| 5 the owner's games | §3.2 |
| 6 build identity | a graph made with a catalogue that names `material_gain_v1` (and lacks `better_alternative_v1`) is refused by `load` ("re-analyse instead"); the shipped build names no `material_gain_v1` |
| 7 through the renderer | the two corpus cases run `explain`, `trace` = `render`, save/load and the result document (`schema_errors` empty, the jsonschema mutation check) like every case; `tests/results/test_result.py::test_the_new_claims_name_their_capture_and_their_move`: the gain segment's references are the pawn on d5 and 2.Nxd5 (its FEN before the move); the alternative's is `e1d2` "Kd2" at P; `tests/viewer/test_viewer.py` draws both: the pawn ringed on d5 then the arrow c3→d5 captioned 2.Nxd5, and the arrow e1→d2 (the corpus count there is now 14) |
| 8 coverage | every `CATALOGUE_V1` name has a `[claim]` phrase and appears in `bind`; the planner's tables name only catalogue templates; a claim whose template has no binding raises `GuardError` G5 |

**Mutations** of rule 3, each caught by the new tests: the rule disabled (4 failures), applied
also at ply 1 (1), the score not turned for Black (1), the boundary made exclusive (4).

### 3.2 The owner's two games (EA-D §6.5)

Both games re-run with `tools/explain_game --json` (Stockfish 19, `d12_mpv5_v1`) and compared,
sentence by sentence, with the documents of §0 (build `89c35f0b…` → `52dcd83d…`). In both, every
ply's grade, loss and best move is the same as before, so every change below is the new rules.

**836/829** (Caro-Kann Advance, 78 plies): 7 plies changed.

| Ply | Grade (loss) | Removed | Added |
| --- | --- | --- | --- |
| 3.e5 | best (0) | "Along the engine line, it wins the pawn on c5 at 4.dxc5 (…)" and its scope "the engine line at depth 12" | — |
| 7.Nc3 | inaccuracy (105) | — | "Instead, 7.Nbd2 was better. Based on the 5 moves the engine reported." |
| 9.Nh4 | inaccuracy (146) | — | "Instead, 9.O-O was better. Based on the 6 moves …" |
| 10.O-O | best (0) | "Along the engine line, it wins the bishop on c3 at 13.bxc3 (…)" and its scope | — |
| 10...Nf5 | inaccuracy (130) | — | "Instead, 10...c5 was better. Based on the 6 moves …" |
| 26.Rb4 | inaccuracy (151) | — | "Instead, 26.Rxb8+ was better. Based on the 5 moves …" |
| 31.g3 | inaccuracy (169) | "Along the engine line, it wins the pawn on a4 at 32.Qxa4 (…)"; the scope loses "the engine line at depth 12" | — ("Instead, 31.Qc1 was stronger." stays) |

**829/808** (`g1012`, 101 plies): 7 plies changed.

| Ply | Grade (loss) | Removed | Added |
| --- | --- | --- | --- |
| 2...Nc6 | best (0) | "Along the engine line, it wins the pawn on d4 at 4...exd4 (…)" and its scope | — |
| 3...f5 | inaccuracy (135) | — | "Instead, 3...Bc5 was better. Based on the 6 moves …" |
| 5...exd4 | good (90) | "Along the engine line, it wins the pawn on d6 at 7...Qxd6 (…)" and its scope | — |
| 11.b3 | inaccuracy (126) | — | "Instead, 11.Bf4 was better. Based on the 6 moves …" |
| 13...Bb4 | mistake (324) | "Along the engine line, it wins the rook on e1 at 18...Bxe1 (…)" | — (its MISS sentence stays) |
| 39...Kc7 | inaccuracy (112) | — | "Instead, 39...Bg4 was better. Based on the 6 moves …" |
| 49.Bxa3 | inaccuracy (126) | — | "Instead, 49.Ng5+ was better. Based on the 6 moves …" |

- **Gains:** the six false gains of EA-D §0.2 are gone; the twelve sound ones remain `SUPPORTED`
  (836/829: 18.Nxb7, 24.Rfb1, 29.cxb5, 39...Qxe8; 829/808: 18.Rxb4, 27.Nxc7, 32.Ne8+, 33.Nxg7,
  36...Bxg2, 44.Ka7, 45.b7, 46.Kxb7) and their sentences are unchanged.
- **Better moves:** every ply graded INACCURACY or worse in both games now has an "Instead"
  sentence (0 without, before: 8).
- **Against EA-D §4.** §4 predicted the removals exactly, but listed only 7.Nc3 and 9.Nh4 among
  the additions: its source table (§0.3) covered the owner's White moves of one game. The same
  rule adds the sentence to six more inaccuracies (10...Nf5, 26.Rb4, 3...f5, 11.b3, 39...Kc7,
  49.Bxa3), all below `MISS_LOSS` with no other comparison. No change outside the two rules.

### 3.3 Suite
`pytest tests` with `CALLIOPE_STOCKFISH_PATH` (Stockfish 19): **1011 passed**, none skipped, in
15 min 9 s. The first run had one failure: `tests/viewer/test_viewer.py` pinned the corpus at 12
documents; it now expects 14 and checks the two new sentences' drawings (§3.1, 7). `ruff check`
passes on `src` and `tests`; the changed files are formatted.

## 4. Review dispositions

Independent implementation review of `79f3d4e`: **READY**, no blocking finding. The review
checked the code against EA-D and read the record; it did not re-run the two games. EA-D #87 was
merged first (`main @ d397666`) and this PR retargeted to `main`, still 21 files.

| Note | Disposition |
| --- | --- |
| **N1** the coverage test looks for each template's name in `bind`'s source, which does not show that a claim of it can be bound | Kept as the name check, and a new test, `test_every_supported_claim_binds_and_phrases`, runs `bind` and `phrase` on every SUPPORTED claim of the 14 corpus cases, eight catalogue scenarios (mate allowed, pin, skewer, discovery, removed defender, newly unsafe, left en prise, prevents) and four of this packet's, in every form its phrasebook section has. It requires every one of the 26 templates to be reached |
| **N2** the viewer test pinned the corpus at 14 | It now expects one document per corpus case, `len(cases())` |
