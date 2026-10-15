# Reasoning — packet EF1 implementation: explanation fixes

Status: **rev. 2 — independent review NOT_READY (B1, B2) applied (§7)**. EF-D carries the
amendments as its §15.
Date: 2026-10-15. Design: [`reasoning-explanation-fixes-design.md`](reasoning-explanation-fixes-design.md)
rev. 4 (EF-D, final re-review READY). Base: `main @ bcb3612`.

## 1. Scope delivered (EF-D §7)

| Place | Change |
| --- | --- |
| `reasoning/lines.py` | `trade_pairs`, `reduced_balances`; `decisive_event` reads `b′` (§2). `Exposed`, `exposed` (`exposed_v1`, with A1), `exchange_ref`; `exposure` on `exposed_v1`, with its needs and an `IN_CHECK` state. `Attribution`, `AttributionResult`, `attribution` (`concession_v1`: the origins `o⁺`, `o⁻`, the classification, the needs, the evidence of §3.4). `SEE_POLICY`, `CONCESSION_POLICY`, `IN_CHECK` (the reason `NOT_COMPUTED(IN_CHECK)`). `unsafe` and `UNSAFE_POLICY` removed |
| `reasoning/findings.py` | `ConcessionFinding`, `CheckAnswerKind`, `CheckAnswerFinding`; in `KINDS` (the type registry reads them) |
| `reasoning/verification.py` | `ATTRIBUTED` beside `REALIZED` and `COUNTERFACTUAL`; no relation rule reads it |
| `reasoning/catalogue/material.py` | `material_loss_v2` (rule 7), `material_gain_v3` (rule 4): `attributed()` adds the check, the concession finding, the needs or `INCONCLUSIVE(NOT_COMPUTED(IN_CHECK))`; the scope adds `see_v1`, `concession_v1`. EA-D's score check (rule 3) reads the line's own decisive ply, not the trade-reduced one (§2, "E2") |
| `reasoning/catalogue/hanging.py` | `removed_defender_v2`, `newly_exposed_v1`, `left_en_prise_v2` on `exposed_v1` |
| `reasoning/catalogue/mechanisms.py` | `fork_v2`, `pin_v2`, `skewer_v2`, `discovery_v2` on `exposed_v1` (the victim's safety before the step, the fork's second threat) |
| `reasoning/catalogue/functions.py` | `check_answer_v1`; in `CATALOGUE_V1` after `forcing_v1` |
| `reasoning/catalogue/comparison.py` | `better_move_v1` compares with `material_loss_v2` |
| `reasoning/observer.py` | `OBSERVATIONS_VERSION = "obs_v2"`: `line_material`'s event is the trade-reduced one (§3) |
| `reasoning/planner.py` | the renamed templates; a material claim whose `ATTRIBUTED` check failed is not chosen as the consequence, so nothing explaining it is chosen (rule 4 keys on the consequence); `check_answer_v1` last in `FUNCTIONS`, left out under FORCED |
| `reasoning/render/`, `phrases/en.toml` | the renamed keys; `check_answer_v1.{block,capture,king}`; `policy.unsafe_v1` removed |
| `facts/engine.py`, `facts/engine_work.py` | `FactEngine(clock=…)`, read by the per-request deadline (§6) |
| tests | `tests/reasoning/test_explanation_fixes.py` (new); the safety tests of `test_catalogue_lines.py` rewritten for `exposed_v1`; the planning tests on an injected clock, with a busy-thread run; renames throughout; the fork fixture's victim and the corpus texts (§4) |

The build identity changes with the template names; no constant was raised for it.

## 2. Amendments to EF-D (for the reviewer)

### A1 — `exposed_v1` for a side in check reads the piece's safe moves

**Found.** EF-D §3.2 read every node where the loser is in check as `UNDECIDED` (`see_v1` is
`NotApplicable(IN_CHECK)` there) and made the attribution INCONCLUSIVE when the two readings
disagreed. The catalogue's own fork scenario (`…Nf3+ Ke2 Nxd4+`), the commonest way a fork wins a
piece, came out `INCONCLUSIVE(NOT_COMPUTED(IN_CHECK))`: the check node is exactly where a fork
puts the loser. It would hide every check-fork past the reply.

**Amended.** F6 already records, for every piece of a side in check, the legal moves after which
it is no longer exposed (`safe_moves`, F6-D §2.3). `exposed_v1` of such a piece is now:
EXPOSED when it has no safe move (no answer to the check keeps it out of the exchange),
NOT_EXPOSED when it has one. `UNDECIDED` remains only for an in-check entry without a safe-moves
record, which F6 never produces; the `o⁺` / `o⁻` machinery and `INCONCLUSIVE(NOT_COMPUTED(IN_CHECK))`
stay for it. The same definition serves the hanging-piece and mechanism templates.

**Consequence.** A real check-fork is attributed (the run passes the check node and starts at the
forking ply, the winner's). A "fork" the loser could answer by saving the piece is a concession —
the catalogue's fixture was one: the white knight on d4, forked by `…Nf3+`, takes the knight back
(`Nxf3`), and the engine line's `Ke2` gives it up. Its loss is now SUPPORTED with `ATTRIBUTED`
failed; the fixture is changed to a bishop on d4, which cannot take back (§4).

**Forced test, narrowed accordingly.** When the loser is in check at `N_{o−1}`, the alternatives
of §3.3 rule 2 are its other legal moves that save the piece (its safe moves there); the move is
forced when none of them avoids mate in one. Outside check the test is EF-D's.

### A2 — the hanging templates decide their guard in `verify`

`newly_exposed_v1` and `left_en_prise_v2` were proposed only when the piece's safety at P was
known (`_guard`). `exchange` is computed on request, so at proposal time it is usually missing.
The guards now propose unless the answer is known to fail, and `verify` decides it first (a
"rule 0"): `left_en_prise_v2` is REFUTED when the piece was not exposed at P, `newly_exposed_v1`
when it was exposed at P and did not move. The claim graph holds these REFUTED claims where it
held none; no sentence changes.

### A3 — an exposing capture linked to the loss is an exchange

**Found.** Re-running the owner's 836/829 game, 24.Rfb1's gain (EA-D §0.2: sound, +121) came out
a concession: `Lp` = 24.Rfb1 dxc4 25.Qxc4 Qc8 26.Rxb8 Rxb8 27.Rxb8 Qxb8 28.Qxa4; the black rook
that recaptures on b8 (ply 6) stops defending a4. Black's recapture is not a free choice — without
it Black is a rook down — but neither static test of §3.3 (only legal move, mate in one) sees that.
18.Nxb7 (sound, +208) failed the same way: Black's ...exf5 takes a pawn with the pawn that is later
lost on f5, an even exchange.

**Amended (rev. 2, review B1).** The loser's exposing move at ply `o` is attributed when it
captures at least the lost piece's value (`|c_o| ≥ |c_q|`, neither ply promoting) **and** is linked
to the loss:
- a **recapture**: ply `o` takes the piece that captured at ply `o − 1` (26...Rxb8), or
- the **same exchange**: the lost piece `y` itself captures at ply `o` and is taken at `q` on that
  square, not having moved in between (...exf5 … Rxf5).

Rev. 1 compared the values alone, so an unrelated capture elsewhere that happened to be worth as
much would have passed. 17.Ne3's ...Rxe3 (a knight for the rook) and 29.cxb5's ...Bxb6 (a pawn for
the bishop) are linked but worth less: concessions.

### E2 — EA-D's score check keeps its own event

**Found.** With the trade rule, 5...exd4 of the 829/808 game names ply 1 (the capture) instead of
ply 5; EA-D §2 rule 3 applies only to events at ply 3 or later, so its refusal (EA-D §0.2: the
line scores −15, below the gain) lapsed and "It wins the pawn on d4" returned.

**Applied.** Rule 3 reads the line's own decisive ply (unreduced balances), as EF-D §2 says every
rule but the naming does. 12.Qxe4's gain still passes it (+898 against 80 per point).

### Smaller choices

- **Check-answer phrases.** EF-D's "It takes the checking {checker}." reads "the checking the
  rook on e8" with R3-D's piece phrase; the phrases are "It blocks the check from {checker}.",
  "It answers the check by taking {checker}." and "It moves the king out of check."
- **The loser's colour** is the opposite of the side that captures at `q` (`N_q`'s mover), not
  read from `pieces` (absent beyond the round-0 ensure).
- **Rounds.** `attribution` asks for `exchange` on every node `N_0 … N_{q−1}` at once: one round,
  not one per node (rounds are three).

## 3. Correction to EF-D §0

**11.Nd2's origin is ply 6 (13...Nd7), not ply 4 (12...d5).** The knight on b8 still defended c6
after 12...d5; 13...Nd7 took that defence away. The classification (a concession) and the
sentence of §8 are unchanged. The scan of EF-D §0.2 read the exchange on boards rebuilt outside
the fact tree.

## 4. Test changes beyond the renames

| Test | Change | Why |
| --- | --- | --- |
| the fork fixture (`4kb2/8/8/6n1/1P1N4/…`, six files and the corpus case `fork_blunder`) | the white knight on d4 becomes a bishop; the quiet line's `Nb3` becomes `Bb2`, `Nf5` `Be5`; `Kf6` `Kd6` where the bishop covers f6 | A1: a knight forked by a knight takes it back (concession); the bishop makes it a fork. Amounts and plies are unchanged |
| `test_line_needs_only_for_the_capture_survey_and_no_causes` | admits the forced test's `LineNeed(…, NONE)` | EF-D §3.3 |
| `test_exposure_fails_on_a_present_record_before_asking_for_a_missing_one` | the needs are `exchange` / `pieces` needs; with one round the loss itself ends `ROUND_LIMIT` | EF-D §3.5 |
| `test_a_pin_past_the_round_zero_ensure_is_decided_in_the_next_round` | the pin is decided in round 2; the starved run ends the loss `BUDGET` | the loss first ensures `exchange` |
| `test_covers`, `test_defends` | allow `exchange` needs on `Lp`'s nodes | the loss's attribution |
| corpus `fork_blunder`, `reply_defends` | one safety phrase in the scope (EF-D §0.3) | E3 |
| corpus `later_gain`, `promotion` | the scope names `see_v1` | §3.6 |
| corpus `reply_covers` | the loss of 1.h3 is not rendered: 2.Kh2, White's own move, left f2 undefended (concession) | E2 |
| render goldens `fork`, `miss` | the scope names `see_v1` once | E3, §3.6 |

## 5. The games re-run

The three games of EF-D §8 — `g1014` and the owner's 829/808 and 836/829 games of EA-D §0 — run
with `tools/explain_game --json` (Stockfish 19, `d12_mpv5_v1`), against `main @ bcb3612` run the
same day on the same machine (an EV1-era document differed on two plies of the 829/808 game by
engine runs alone: 4...Nf6 judged instead of "the engine search was incomplete", 5.d4 with its
loss sentence; both are the same under `main` and EF1 today). Grades, labels and evaluations are
unchanged on every ply.

| Game | Plies | Scope phrase only | A check answer added | Other sentences changed |
| --- | --- | --- | --- | --- |
| `g1014` | 75 | 23 | 12 | 4 |
| 829/808 | 101 | 12 | 3 | 0 |
| 836/829 | 78 | 5 | 2 | 1 |

"Scope phrase only": the scope names exchange evaluation (`see_v1`) once — added to material
claims (EF-D §3.6), or replacing the two safety phrases (EF-D §0.3: 2.Nf3, 21.Nd6+, 32.Rfd4+,
33.Rc5+ of `g1014`).

**The other sentences:**

| Game | Move | Before | After |
| --- | --- | --- | --- |
| `g1014` | 11.Nd2 | "Along the engine line, it wins the pawn on c6 at 14.Nxc6 …" | not rendered: concession, origin 13...Nd7 (§3) |
| `g1014` | 12.Qxe4 | "… it wins the queen on e4 at 13.Nxe4 …" | "It wins the pawn on e4 at 12.Qxe4 (… at least 1 point)." |
| `g1014` | 17.Ne3 | "… it wins the rook on e3 at 19.fxe3 …" | not rendered (concession at 18...Rxe3); "It blocks the check from the rook on e8." |
| `g1014` | 18.Bxa6 | "… it wins the rook on e3 at 21.fxe3+ …" | not rendered (concession at 20...Rxe3) |
| 836/829 | 29.cxb5 | "… it wins the bishop on b6 at 32.cxb6 (… at least 2 points)." | not rendered: 31...Bxb6 gives the bishop for a pawn (concession; EA-D §0.2 had counted the gain sound at +376) |

29.cxb5 is the one change against an EA-D "sound" gain: the engine line has Black take the b6
pawn with the bishop, which the static tests cannot tell from 17.Ne3's ...Rxe3. A3 kept the other
two sound gains EF-D would have lost (24.Rfb1, 18.Nxb7).

**Claims whose verdict changed** (EF-D §4 asks for them): `check_answer_v1` is new on 22 plies
(13, 4 and 5 — each move out of check; rendered unless FORCED, as 13...Kxe7, or another function
leads); 12.Qxe4's
`fork_v2` and `pin_v2` are no longer SUPPORTED (their scan ends at the new event, ply 1, EF-D §2).
No mechanism or hanging-piece verdict changed with `exposed_v1` in these games. Concessions keep
their material claims SUPPORTED (with `ATTRIBUTED` failed), so the result documents list them as
before.

**Run time** (EF1): 129 s, 198 s and 182 s; the added `exchange` and child-node work is inside
those figures (EF-D §3.5); `main`'s runs were not timed apart.

**Open, not fixed here.** 18.Nxb7's gain names "the pawn on f5 at 22.Rxf5": ...exf5 (ply 4) and
Rxf5 (ply 9) are an even exchange, but not adjacent, so `trade_pairs_v1` does not pair them and
the event is the recapture. The gains are b7 and a5. Pairing a capture with a later recapture of
the same piece needs a design change to EF-D §2.

## 6. Test runs

- The whole suite with Stockfish 19, alone (rev. 2): **1125 passed, 0 skipped, 0 failed**
  (15 min 38 s); rev. 1: 1117. The baseline of `main @ 9f5033c` was 1097 passed (status and
  roadmap §7); the difference is `test_explanation_fixes.py` (27) and the busy-thread planning
  test (1).
- The three games re-run with rev. 2: the same changes as §5 (A3 rev. 2 changes no verdict there).
- `ruff check` and `ruff format --check` on `src`, `tests`, `tools`: clean.

## 7. Review dispositions (rev. 1 `2c23220`, independent review: NOT_READY)

The review passed the trades, the material templates with `ATTRIBUTED`, `exposed_v1`,
`check_answer_v1`, the plan, the clock and the registrations, and accepted A1 and A2 (asking that
EF-D carry A1).

| Finding | Disposition |
| --- | --- |
| **B1** A3 credited any exposing capture worth as much, linked or not | Accepted. A3 requires a recapture or the lost piece's own capture on its square (§2, `_exchange_at`). Tests: a recapture (26...Rxb8) and the same exchange (...exf5) attributed; an unrelated capture of equal value and a capture worth less (...Rxe3) concessions; 24.Rfb1, 18.Nxb7 (attributed) and 29.cxb5 (a concession at 31...Bxb6) on the game positions. |
| **B2** EF-D §9's boundary cases were not tested directly | Accepted. On a fake view, with the origins and the evidence checked: two agreeing origins `o⁺ = 4 < o⁻ = 6` (the range, both origins' `exchange` records and the undecided node's `status`); the empty run `o = q` (`exchange(N_{q−1})` and the capture event, attributed); `o = 0` (`exchange(N_0)` first, no `N_{−1}`); a widened window with the origin at ply 10 and `q = 13`. |
| (note) EF-D should carry A1 | Applied: EF-D §15 lists A1–A3, E2 and the §0.2 correction. |
