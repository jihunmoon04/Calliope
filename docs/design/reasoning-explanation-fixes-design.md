# Reasoning — EF-D design: explanation fixes (trades, concessions, one safety test, check answers)

Status: **rev. 2 — independent review NOT_READY (B1–B3) applied (§12)**.
Date: 2026-10-14. Base: `main @ 14f071d`. Inputs:
[`reasoning-r2-design.md`](reasoning-r2-design.md) (R2-D §1.3 window and outcome, §1.5 decisive
event, §1.6a exposure continuity, §3.1–§3.2 material, §3.7–§3.8 mechanisms and hanging pieces);
[`reasoning-explanation-accuracy-design.md`](reasoning-explanation-accuracy-design.md) (EA-D §2
`material_gain_v2`, §5 "the decisive event across exchanges", §8);
[`fact-engine-f6-design.md`](fact-engine-f6-design.md) (F6-D: `exchange`, `see_v1`);
[`reasoning-r3-design.md`](reasoning-r3-design.md) (R3-D: `selection_v1`, `phrases_en_v1`);
[`reasoning-r0-design.md`](reasoning-r0-design.md) (R0-D §9.2 reasons, §10.2 causal checks).

The owner read a third game (2026-10-14) and found two sentences that state something false and one
that credits a move with what the opponent gave away. A scan of every supported material claim of
that game found the cause of each. This packet fixes them and removes one inconsistency the scan
also showed: two different tests of whether a piece is safe. It is the first of two packets before
the agent tools (status and roadmap §5.3); the second, DF-D
([`reasoning-definitions-design.md`](reasoning-definitions-design.md)), states the definitions and
the result data. Line continuation (EV-D §0.4, the open lines) is not in this packet (§10).

## 0. Evidence (the third game)

`g1014`: a chess.com blitz game (180 s) of 2026-10-14, 308 / 291, analysed through the server
(`calliope_result_v1`, 75 plies). Stockfish 19, `d12_mpv5_v1`; grading `quality_v2` on
`human_lichess_2026_08_v2`, chess.com 308 converted to 1090 and clamped to band 1000. The bundles
were re-loaded without the engine and every supported `material_gain_v2` and `material_loss_v1`
claim (23) was read on its `Lp` window.

### 0.1 The three sentences

- **12.Qxe4** (excellent): "it wins the queen on e4 at 13.Nxe4 (net material gain over the line: at
  least 1 point)". `Lp` = 12.Qxe4 Qxe4+ 13.Nxe4 d5 14.Ng3 O-O 15.Be2 Re8 16.Be3; balances from P
  0, 1, −8, 1, 1, …. The point is the e4 pawn taken by the move; the queens are traded.
  `decisive_ply` ("the first ply where the balance reaches its final level and stays on its side
  of 0") cannot return ply 1 because ply 2 falls to −8, so it names the recapture 13.Nxe4 and its
  victim, the queen. EA-D §5 recorded the same fault for 10.O-O (it names 13.bxc3, a recapture;
  the gain is 11.dxc5) and left it for "a rule that pairs captures and recaptures on a square".
  EA-D's score filter (E2) does not catch it: the line scores +8.98.
  The same claim graph holds `fork_v1` and `pin_v1` as SUPPORTED, with their `REALIZED` check
  failed (relation `ASSOCIATED_WITH`, not rendered): 12.Qxe4 attacks c6, h7 and the queen on e7,
  and pins that queen to the king, but the queen takes back along the pin.
- **17.Ne3** (best): "it wins the rook on e3 at 19.fxe3 (… at least 2 points)". White was in
  check from the rook on e8 (five legal moves); 17.Ne3 blocks. `Lp` = 17.Ne3 Re6 18.Kd1 Rxe3
  19.fxe3 Kg6 20.Bd3+ Kg7. Black gives the exchange at 18...Rxe3 with a rook that nothing
  attacked. Re-searched after 18.Kd1 (Stockfish 19, fresh process), 18...Rxe3 is not among the
  first four moves at depth 12 nor at depth 22 (18...Nc6, b4, Kg8, d5 at +8.5 … +8.7). In a lost
  position the depth-12 PV's later moves for the losing side are close to arbitrary. The text also
  does not say that the move answers a check.
- **11.Nd2** (inaccuracy, +8.19 against 11.Ba3 +11.04): "Along the engine line, it wins the pawn
  on c6 at 14.Nxc6". `Lp` = 11.Nd2 O-O 12.Qe3 d5 13.N2b3 Nd7 14.Nxc6. The c6 pawn became
  capturable at 12...d5, which removed its defender d7; the knight on d4 attacked c6 from the
  start. The gain is Black's choice in the engine line, not the move's.

### 0.2 Every supported material claim of the game

For each claim: the decisive event today (`q`), the event under the trade rule of §2 (`q′`), and
where the lost piece's exposure (§4, `exposed_v1`) began, `N_o` (`o = 0` is P). The loser is the
side whose piece is captured at `q′`.

| Ply | Move | Claim | Amount | `q` | `q′` | Exposed from | Loser's ply? | §3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | 2.Nf3 | loss | 1 | 2 | 2 | `N_0` | — | credited |
| 10 | 5...f5 | loss | 2 | 4 | 4 | `N_2` | no | credited |
| 11 | 6.d3 | gain | 2 | 3 | 3 | `N_1` | no | credited |
| 12 | 6...Bb4+ | loss | 1 | 4 | 4 | `N_2` | no | credited |
| 13 | 7.c3 | gain | 5 | 5 | 5 | `N_1` | no | credited |
| 14 | 7...Bxc3+ | loss | 1 | 4 | 4 | `N_2` | no | credited |
| 15 | 8.bxc3 | gain | 4 | 3 | 3 | `N_1` | no | credited |
| 17 | 9.dxe4 | gain | 2 | 1 | 1 | `N_0` | — | credited |
| **21** | **11.Nd2** | gain | 1 | 7 | 7 | `N_4` (12...d5) | **yes** | **not attributed** |
| **23** | **12.Qxe4** | gain | 1 | **3** | **1** | `N_0` | — | credited |
| 25 | 13.Qxe7+ | gain | 1 | 3 | 3 | `N_2` | — (`o < 3`) | credited |
| **33** | **17.Ne3** | gain | 2 | 5 | 5 | `N_4` (18...Rxe3) | **yes** | **not attributed** |
| **35** | **18.Bxa6** | gain | 2 | 7 | 7 | `N_6` (20...Rxe3) | **yes** | **not attributed** |
| 38 | 19...bxc3 | gain | 1 | 1 | 1 | `N_0` | — | credited |
| 41 | 21.Nd6+ | gain | 2 | 3 | 3 | `N_2` | — | credited |
| 43 | 22.Nxe8 | gain | 3 | 1 | 1 | `N_0` | — | credited |
| 49 | 25.Rxe8 | gain | 1 | 1 | 1 | `N_0` | — | credited |
| 51 | 26.Rf8+ | gain | 3 | 3 | 3 | `N_2` | — | credited |
| 53 | 27.Rxf4 | gain | 4 | 5 | 5 | `N_3` | no | credited |
| 59 | 30.Rxc3 | gain | 1 | 1 | 1 | `N_0` | — | credited |
| 61 | 31.Rcxc4 | gain | 1 | 1 | 1 | `N_0` | — | credited |
| 63 | 32.Rfd4+ | gain | 1 | 5 | 5 | `N_3` | no | credited |
| 65 | 33.Rc5+ | gain | 2 | 5 | 5 | `N_3` | no | credited |

The trade rule changes one event (12.Qxe4). The concession rule withholds three gains from the
move (each keeps its line fact, §3): the two of
§0.1 and 18.Bxa6, whose line repeats the same exchange sacrifice ...Rxe3. Neither of §0.1's is
forced (§3.3): before 18...Rxe3 Black has 27 legal moves and before 12...d5 35, none allowing mate
in one; 18.Bxa6's is checked by EF1. Every other claim keeps its sentence, among them the losses of 6...Bb4+ and 7...Bxc3+ (the knight on e4 was exposed before
the mover's later choices).

### 0.3 Two safety tests in one sentence

2.Nf3 (mistake) ends: "Based on the engine line at depth 12, piece safety judged by attackers and
defenders, without exchange evaluation and piece exchanges judged by static exchange evaluation."
Two templates of one explanation used two tests: `unsafe_v1` (R2-D §1.6: outnumbered, or attacked
by a lower piece) and `see_v1` (F6-D). Since F6, the fact engine computes the exchange directly;
R2-D §10 named it "a stronger safety test than `unsafe_v1`" for a later catalogue.

### 0.4 Moves out of check

13 of the 75 plies are played out of check: 2 blocks (7.c3, 17.Ne3), 2 captures of the checker
(8.bxc3, 24...Nxd5), 9 king moves. Nine of the thirteen texts are the grade sentence alone
("14...Ke6 is an excellent move."). No template states the check.

### 0.5 A rule that was tried and dropped

Re-searching the loser's choices along `Lp` (a survey at each, keeping the gain only when the PV
move is the survey's first choice, or when the first choice keeps the gain) was measured on the
ten claims whose deciding choice lies beyond the reply. It does not fix 17.Ne3: at depth 12 the
first choice after 18.Kd1 varied between runs of one Stockfish process (hash state), and its own
PV gave the exchange again (18...Kg8 19.Ke1 Rxe3+). It costs one search per claim and makes the
verdict depend on the PV's noise it is meant to remove. The exposure rule of §3 needs no search
and reads only facts.

## 1. Decisions

| # | Decision |
| --- | --- |
| E1 | **Trades are paired before the decisive event is chosen** (§2, `trade_pairs_v1`). A capture answered at once by the recapture of the capturing piece, on that square, for equal `points_v1`, does not move the balance the event rule reads. The amount is unchanged. |
| E2 | **Material along the line and its attribution to the move are kept apart** (§3, `concession_v1`). The material claim states what the line shows; a new causal check, `ATTRIBUTED`, states whether the move is shown to bring it about. When the loser's own move at ply 3 or later exposed the lost piece and that move was not forced (§3.3), the check fails: the claim stays SUPPORTED as a fact of the line and is not rendered. A failed check means "not shown to be forced by the move", never "the loser could have kept it". An origin that an undecided node could move is INCONCLUSIVE. No search. |
| E3 | **One safety test, `exposed_v1`** (§4). A piece is exposed when the opponent wins at least one point by starting captures on it (`see_v1`; for the side to move, with the turn passed). It replaces `unsafe_v1` in every template and in exposure continuity (R2-D §1.6a). Attacker and defender counts stay facts (`pieces`), not a safety test. |
| E4 | **Check answers are stated** (§5, `check_answer_v1`): a FUNCTION claim, exact, for every move played out of check: a block, a capture of the checking piece, or a king move. |
| E5 | **Versioned, not edited** (EA-D E6): `material_gain_v3`, `material_loss_v2`, `newly_exposed_v1` (was `newly_unsafe_v1`), `left_en_prise_v2`, `removed_defender_v2`, `fork_v2`, `pin_v2`, `skewer_v2`, `discovery_v2`, `check_answer_v1`. The build identity changes with the template names (`ReasoningBuild.templates`); stored graphs of the old build are re-analysed, never re-read (R4-D §2.1; the server's cache misses, AS-D §4). |
| E6 | **No new reason.** An `exposed_v1` test at a node whose side to move is in check, for that side's piece, is undecided (`see_v1` is `NotApplicable(IN_CHECK)` there); a template that cannot decide for that reason closes `INCONCLUSIVE(NOT_COMPUTED(IN_CHECK))`, the form `piece_offer_v1` already uses (LV1). |
| E8 | **One new causal check kind**, `ATTRIBUTED` (R0-D §10.2 amended): a check on a consequence claim itself, not on a relation. It changes no relation rule (`EXPLAINS` still needs `REALIZED`, `CAUSES` `COUNTERFACTUAL`). |
| E7 | **The planning tests read a clock, not the wall** (§6). |

## 2. `trade_pairs_v1` and the decisive event (R2-D §1.5, amended)

**Notation.** `Lp`'s window `N_0 … N_k` (`N_0` = P), ply `i` the move `N_{i−1} → N_i`, `b_i` the
mover's balance from P after ply `i` (R2-D §1.2; `b_0 = 0`), `c_i` = `b_i − b_{i−1}`.

**Trade.** Plies `i` and `i + 1` form a trade when all of these hold:
1. both capture (a `Capture` event in `move`), and neither promotes;
2. ply `i + 1` captures on ply `i`'s destination square, and its victim is the piece that moved at
   ply `i` (physical identity, `PieceId`);
3. the two victims have the same `points_v1` value.

Trades are taken left to right and do not overlap: a ply that closes a trade cannot open the next.
A capture with en passant can be the first ply of a trade only when its recapture lands on the
capturing pawn's square, which condition 2 already states.

**Reduced balances.** `b′_i = b_{i−1}` when ply `i` opens a trade, otherwise `b′_i = b_i`. (A trade
nets 0, so the balances differ only at the first ply of each trade.)

**The decisive event** is `decisive_ply` (unchanged) over `b′`: the first ply where `b′` reaches its
final level and stays on its side of 0. The amount, the outcome and every other rule of R2-D §1.3
read `b`, as today.

| Case | `b` | Trades | `b′` | Event |
| --- | --- | --- | --- | --- |
| 12.Qxe4 (§0.1) | 0, 1, −8, 1, 1 | plies 2–3 (Q for Q on e4) | 0, 1, 1, 1, 1 | ply 1, 12.Qxe4, the e4 pawn |
| 10.O-O (EA-D §0.1) | 0, 0, 0, 1, 1, 1, −2, 1, 1 | plies 6–7 (B for N on c3) | 0, 0, 0, 1, 1, 1, 1, 1, 1 | ply 3, 11.dxc5, the c5 pawn |
| 24.Rfb1 (EA-D §5) | 0, 0, −1, 0, 0, 5, 0, 5, 0, 1, 1, 1 | the rook trades (if any) | `b′_8 = b_8 = 0`, `b′_9 … b′_11 = 1` | ply 9, 28.Qxa4 (unchanged: `b′` differs from `b` only at a trade's first ply) |

10.O-O stays REFUTED by EA-D's score filter (−13 cp); the event changes what a re-run reports, not
its verdict. A recapture by a different-valued piece is not a trade (17.Ne3: R for N); naming such
an exchange as one ("the rook for the knight") is left for later (§10).

Mechanisms read the material claim's event (R2-D §3.7: the scan runs to `q`), so for 12.Qxe4 their
scan ends at ply 1.

## 3. `concession_v1` and the `ATTRIBUTED` check

### 3.1 Inputs

A material claim that passed every rule of R2-D §3.1 / §3.2 and EA-D §2, with its event at ply `q`
under §2 and the capture of a piece `y` at `q`. The **loser** `L` is `y`'s owner: the opponent for
a gain, the mover for a loss. The window is `Lp`'s material window, which R2-D §1.3 widens up to
`2 · pv_plies` (20) plies while the material is unsettled for want of plies (`observer.window`), so
`q ≤ 20`.

### 3.2 The exposure origin

Each node `N_i`, `0 ≤ i ≤ q − 1`, has a state for `y` (§4): `EXPOSED`, `NOT_EXPOSED` (also when
`y` is not on the board) or `UNDECIDED` (`y`'s owner is in check at `N_i`). Walking back from
`N_{q−1}`, two origins are computed:

- `o⁺`: the run continues through `UNDECIDED` nodes (read as exposed);
- `o⁻`: the run stops at the first `UNDECIDED` node (read as not exposed).

Each is the index of the run's first node; a run that is empty at `N_{q−1}` gives `q`.
`UNDECIDED` is never read as `EXPOSED` for the verdict: the origin is **decided** when `o⁺` and
`o⁻` give the same classification under §3.3, and **undecided** otherwise.

### 3.3 Classification

With an origin `o`:

1. `o < 3`, or ply `o` was played by the move's side when `L` is the opponent (and by the opponent
   when `L` is the mover): **attributed**. The lost piece was exposed from P, by the reply, or by
   the winner's own play.
2. Otherwise ply `o` is `L`'s own move after the reply (R3-D `IMMEDIATE_PLIES = 2`); it exposed `y`
   by moving `y` onto an attacked square, by moving a defender away, or by capturing with `y` into
   a recapture. It is **forced** when, at `N_{o−1}`:
   - `L`'s move at ply `o` is its only legal move (`status(N_{o−1}).legal_move_count = 1`), or
   - every other legal move allows mate in one: each child `N_{o−1} + m` has
     `status.mating_moves ≠ ()`.

   Forced: **attributed**. Not forced: **a concession**.

The second test needs the children of `N_{o−1}`: `LineNeed(N_{o−1}, (m,), NO_SEARCH)` for each
legal move `m` that is not yet a node (at most the legal move count, within `max_tree_nodes`; no
search). It is evaluated only for a concession candidate.

### 3.4 Verdict

| Origin | Classification | `material_gain_v3` / `material_loss_v2` |
| --- | --- | --- |
| decided | attributed | SUPPORTED with `CausalCheck(ATTRIBUTED, passed = true, evidence)` |
| decided | concession | SUPPORTED with `CausalCheck(ATTRIBUTED, passed = false, evidence)` and `ConcessionFinding(piece y, ply o, node N_o)` |
| undecided | — | `INCONCLUSIVE(NOT_COMPUTED(IN_CHECK))` |

The evidence is the `exchange` references of `N_o` and `N_{o−1}` and, for a forced move, the
`status` references read. An event that is a promotion without a capture is not tested and carries
`ATTRIBUTED` passed with the move reference of the event as evidence.

**What the check says.** `passed = false`: along the engine line the material changes hands because
of `L`'s own later move, and the move does not force that move (by the two tests of §3.3). It does
not say that `L` had a move that keeps the material, nor that the line is wrong; the material claim
stays SUPPORTED as what the line shows. `passed = true`: the material was exposed before `L`'s later
choices or `L` had no other move (as tested); it is not a proof that every defence fails.

**Selection.** `selection_v1` does not choose a material claim whose `ATTRIBUTED` check failed (rule
of R3-D §1 for consequences, amended), and drops the mechanisms and hanging-piece claims built on
it (they speak of that material). Templates that read a material claim as a premise still run on
it: they describe the line.

### 3.5 Records

`exchange` at `N_0 … N_{q−1}`, at most 20 nodes, through `FamilyNeed` (on request, F6-D §2.0), within
`max_ensure_nodes = 64` (`ReasoningBudget`); `status` at the children of §3.3 is mandatory and
comes with the nodes. A missing record is NEEDS_EVIDENCE, then `INCONCLUSIVE(NOT_COMPUTED(exchange))`
(or the refusal's reason) at the last round (R0-D §6). EF1 records the added `ensure` work per game
(the corpus and the three games of §8).

### 3.6 Templates

`material_gain_v3` = `material_gain_v2` + §2 + §3 (after EA-D's rule 3); `material_loss_v2` =
`material_loss_v1` + §2 + §3 (after R2-D's rule 6). Their proposals, operands and targets are
unchanged; the scope adds the policies `see_v1` (§4) and `concession_v1`.

## 4. `exposed_v1` — one safety test

**Definition.** For a piece `y` at node `N`, with `X = exchange(N)` and `e` its entry for `y`:
- exposed when `e.gain` is `Defined(see_v1, g)` with `g ≥ 1` (for `y` of the side to move, F6-D
  §2.2 passes the turn);
- not exposed when `g = 0`;
- undecided when `e.gain` is `NotApplicable(IN_CHECK)` (its owner is in check); a template that
  needs the answer closes `INCONCLUSIVE(NOT_COMPUTED(IN_CHECK))` (E6);
- a missing `exchange` record is a need, as in §3.

`y` absent from the board at `N` is not exposed there (R2-D §1.1, unchanged).

**Where it replaces `unsafe_v1`.**

| Place | Today | After |
| --- | --- | --- |
| `lines.exposure` (R2-D §1.6a, exposure continuity) | `unsafe` and `attacks(w, v)` at every node of the span | `exposed_v1` and `attacks(w, v)` |
| `removed_defender_v1`, `newly_unsafe_v1`, `left_en_prise_v1` (R2-D §3.8) | `unsafe` at P and C | `exposed_v1`; the templates become `removed_defender_v2`, `newly_exposed_v1`, `left_en_prise_v2` |
| `fork_v1`, `pin_v1`, `skewer_v1`, `discovery_v1` (R2-D §3.7): the victim was safe before the step (`_safe`) | `unsafe` | `exposed_v1`; `*_v2` |
| `fork_v1`'s "real second threat" (a second target below the actor's order) | `unsafe(target)` | `exposed_v1(target)` |

**Scope and text.** These templates name the policy `see_v1` (the definition reads only `see_v1`
records). `policy.unsafe_v1` leaves the phrasebook; the scope sentence names exchange evaluation
once (§0.3). `UNSAFE_POLICY` and `lines.unsafe` are removed from the reasoning package.

**What changes.** `unsafe_v1` called a piece defended once and attacked twice unsafe even when every
capture loses (a pawn defending it), and a piece attacked by a lower piece unsafe even when the
lower piece is pinned absolutely; `see_v1` plays the captures legally (F6-D §2.1). Pieces that
`unsafe_v1` called safe but lose an exchange (an attacker behind an x-ray) become exposed. EF1
reports every claim of the three games (§7) whose verdict changes.

## 5. `check_answer_v1` — FUNCTION, forward, exact

**Proposal.** At P the mover is in check (`status(P).in_check`).

**Verify.** With `ch = status(P).checkers` and the move `m` (`move(C)`):
- `KING` when `m` moves the king;
- `CAPTURE` when `m`'s `Capture` event takes a checking piece, en passant included (the victim is
  not on `m`'s destination; one checker; with two checkers only the king moves);
- `BLOCK` otherwise (`m` lands on a square between the king and the checking slider).

SUPPORTED, always, with `CheckAnswerFinding(kind, checkers: tuple[PieceRef, …], legal_moves)`;
evidence `status(P)` (`in_check`, `checkers`, `legal_move_count`) and `move(C)`. Proof scope exact
(`Basis.EXACT`), no search.

**Plan.** `selection_v1`'s FUNCTIONS list gains `check_answer_v1` last: a move with another
supported function keeps it as the purpose. Under the FORCED label `check_answer_v1` is not
rendered: the label's sentence ("It is the only legal move.") already covers it.

**Phrases** (`phrases_en_v1`, data): `check_answer_v1.block` = "It blocks the check from the
{checker}."; `.capture` = "It takes the checking {checker}."; `.king` = "It moves the king out of
check." — `{checker}` is "the rook on e8" (R3-D H8); two checkers render the king form only.

## 6. The planning tests read a clock

`tests/facts/search/test_planning.py`'s two deadline tests (R4 §4, EV1 §3.3) sleep 20 ms per search
under a 5 ms deadline and fail under load. `FactEngine` takes an optional `clock` (default
`time.monotonic`) that `engine_work` reads for the deadline; the tests pass a clock the scripted
port advances by a fixed step per search. No runtime behaviour changes.

## 7. Code changes (the contract of EF1)

| Place | Change |
| --- | --- |
| `reasoning/lines.py` | `trade_pairs(line)`, `reduced_balances(line)`; `decisive_event` reads them (§2); `exposed(view, piece, node)` → `EXPOSED / NOT_EXPOSED / UNDECIDED` or a need (§4); `exposure` on `exposed`; `attribution(view, line, event)` → the origins `o⁺`, `o⁻`, the classification and the needs (§3); `unsafe` and `UNSAFE_POLICY` removed |
| `reasoning/findings.py` | `ConcessionFinding`, `CheckAnswerKind`, `CheckAnswerFinding`; in `KINDS` |
| `reasoning/catalogue/material.py` | `MaterialGain` → `material_gain_v3`, `MaterialLoss` → `material_loss_v2` |
| `reasoning/catalogue/hanging.py`, `mechanisms.py` | the seven templates of §4 on `exposed`, renamed |
| `reasoning/catalogue/functions.py` | `CheckAnswer` (§5); in `CATALOGUE_V1` after `Forcing` |
| `reasoning/verification.py` | `ATTRIBUTED` beside `REALIZED` and `COUNTERFACTUAL` |
| `reasoning/planner.py` | the renamed templates in `MATERIAL`, `MECHANISMS`; a material claim with a failed `ATTRIBUTED` check, and the claims built on it, are not chosen (§3.4); `check_answer_v1` last in `FUNCTIONS` |
| `reasoning/render/`, `phrases/en.toml` | the renamed keys; `check_answer_v1.*`; `policy.unsafe_v1` removed |
| `facts/engine.py`, `facts/engine_work.py` | the injectable `clock` (§6) |
| `tests/reasoning/corpus/` | the acceptance corpus re-recorded under the new build (R4-D) |

## 8. What changes in `g1014` (expected, from §0; EF1 re-runs it)

| Ply | Today | After |
| --- | --- | --- |
| 12.Qxe4 | "it wins the queen on e4 at 13.Nxe4" | "It wins the pawn on e4" (event ply 1, R3-D's immediate form) |
| 17.Ne3 | "it wins the rook on e3 at 19.fxe3" | the gain SUPPORTED, `ATTRIBUTED` failed (concession at 18...Rxe3), not rendered; "It blocks the check from the rook on e8." |
| 11.Nd2 | "it wins the pawn on c6 at 14.Nxc6" | the gain SUPPORTED, `ATTRIBUTED` failed (concession at 12...d5), not rendered; the text keeps the grade and "Instead, 11.Ba3 was better." |
| 18.Bxa6 | "… wins the rook on e3 …" | the gain SUPPORTED, `ATTRIBUTED` failed (concession at 20...Rxe3), not rendered |
| 2.Nf3 | two safety phrases in the scope | one (`see_v1`) |
| 13 moves out of check | 9 without a reason | each states the check answer, unless FORCED or another function leads |

EF1 also re-runs the owner's two games of EA-D §0 and reports every changed sentence.

## 9. Test obligations (packet EF1)

1. **Trades.** The three cases of §2 as balance sequences, with their events; a recapture by a
   different piece of the same value (B for N) is a trade, one of different value (R for N) is not;
   non-overlap (`P×P, P×P, P×P` on one square pairs plies 1–2 only); a capture-promotion is never in
   a trade; the amount and the outcome do not change.
2. **Attribution.** 17.Ne3 and 11.Nd2 as fixtures (the trees of `g1014`): SUPPORTED with
   `ATTRIBUTED` failed at origins 4 and 4, not rendered, their mechanisms not rendered; 6...Bb4+'s
   loss and 9.dxe4's gain SUPPORTED with `ATTRIBUTED` passed. Synthetic lines for: a run broken by a
   `NOT_EXPOSED` node; `o = 2` (the reply) and `o = 3` by the winner (attributed); a concession by
   the loser's only legal move (attributed, forced); a concession where every other legal move
   allows mate in one (attributed) and one where a single other move does not (concession); an
   `UNDECIDED` node where `o⁺` and `o⁻` agree (decided) and where they differ
   (`INCONCLUSIVE(NOT_COMPUTED(IN_CHECK))`); a promotion event (not tested, passed); a missing
   `exchange` record (NEEDS_EVIDENCE); a widened window with `q > 10` (§3.1).
3. **`exposed_v1`.** A piece attacked twice and defended once, where every capture loses (not
   exposed; `unsafe_v1` said unsafe); a piece behind an x-ray that loses the exchange (exposed;
   `unsafe_v1` said safe); a side-to-move piece (turn passed); a side in check (`IN_CHECK`).
   No template of the catalogue imports `unsafe` (a static test).
4. **Check answers.** One position per kind; a checking pawn taken en passant (`CAPTURE`); a
   double check (king only); FORCED with a check
   (no `check_answer_v1` sentence); a move with `only_move_v1` keeps it as the purpose.
5. **Scope text.** No explanation of the three games names two safety policies.
6. **Clock.** The two planning tests pass with the injected clock under a CPU load (a busy thread).
7. **Selection.** A plan never contains a material claim with a failed `ATTRIBUTED` check nor a
   mechanism or hanging-piece claim whose premise is one.
8. **Corpus and build.** The R4-D acceptance corpus re-records; a claim graph of build 1 is refused
   as a different build (R4-D §2.1).
9. **The games.** `g1014` matches §8; the owner's two games' changed sentences are listed in EF1.

## 10. Not in this packet

- **Line continuation** (EV-D §0.4; the owner, 2026-10-14: later). The 73 open lines and the
  "why is the better move better" sentences that need it (11.Ba3, 34...Kf6).
- **Naming an unequal exchange as one** ("wins the rook for the knight").
- **Whether the loser could have kept the material** (a search at the concession, §0.5); with it,
  a failed `ATTRIBUTED` check could become a stronger statement.
- **The definitions and the result data** (one vocabulary, units, verdict scopes and relations in
  `calliope_result_v1`): DF-D.

## 11. Delivery

| Packet | Content | Gate |
| --- | --- | --- |
| EF-D (this) | the rules and their evidence | independent review READY |
| EF1 | §7, the tests of §9, the three games re-run | READY |

## 12. Review dispositions (rev. 1 `f609af1`, independent review: NOT_READY)

The review kept `trade_pairs_v1`, the reduced balances for the event only, `exposed_v1` replacing
`unsafe_v1`, `check_answer_v1`, the renames and the injected clock. Each finding was checked against
the code.

| Finding | Disposition |
| --- | --- |
| **B1** a concession REFUTED the claim, although the loser exposing a piece does not show that the move did not force it (a single legal reply, or every other reply mated) | Accepted. The line's material and its attribution are separate (E2, E8, §3.4): the claim stays SUPPORTED and a causal check `ATTRIBUTED` records the attribution; a forced concession (only legal move, or every other move allows mate in one, §3.3) is attributed; a failed check is defined as "not shown to be forced", not as an avoidable loss; selection drops the claim and the claims built on it. |
| **B2** an `IN_CHECK` node continued the exposure run as if exposed | Accepted. Nodes have three states; the origin is computed with undecided nodes read both ways and is decided only when both give the same classification, otherwise `INCONCLUSIVE(NOT_COMPUTED(IN_CHECK))` (§3.2, §3.4). `IN_CHECK` is not a new reason: the existing `NOT_COMPUTED(IN_CHECK)` form (E6). |
| **B3** the window can widen to `2 · pv_plies`, not 10 | Accepted (`observer.window`): up to 20 nodes, within `max_ensure_nodes`; a fixture with `q > 10`; EF1 records the `ensure` work (§3.1, §3.5, test 2). |
| (note) a checking pawn captured en passant | Applied: `CAPTURE` reads the `Capture` event's victim (§5), test 4. |
