# Reasoning — EV-D design: explanation v2, part 1 (draws by checks, what the better move does about the reply)

Status: **rev. 4 — B7 forced-reply SEE correction documented; awaiting independent review and EV1 measurements**.
Date: 2026-10-14. Base: `main @ 4dd3258`. Inputs:
[`reasoning-r2-design.md`](reasoning-r2-design.md) (R2-D §1 lines, windows, outcome; §3
templates), [`reasoning-r3-design.md`](reasoning-r3-design.md) (R3-D `selection_v1`,
`phrases_en_v1`, H1, guard), [`reasoning-explanation-accuracy-design.md`](reasoning-explanation-accuracy-design.md)
(EA-D: `better_alternative_v1`; its §3a lesson: every place that names a template is listed),
[`fact-engine-f6-design.md`](fact-engine-f6-design.md) (F6-D: `exchange`, `see_v1`, `safe_moves`),
[`reasoning-lv1-implementation.md`](reasoning-lv1-implementation.md) (`piece_offer_v1`: a node
created without a search, then `exchange` on it).

After EA1, every inaccuracy or worse names the better move. It rarely says **why** that move
is better. The owner asked first about 33.b6 of the 836/829 game: White, winning, allows Black's
queen a series of checks, and 33.Qc2 was needed because it covers e2. This packet adds the
explanations that the facts prove: a line that ends in checks the engine scores as a draw (or
that repeats the position a third time), and what the better move does about the opponent's
reply, checked by static exchange evaluation. Positional reasons and lines whose window ends
before the material settles are measured here but left to later packets (§8).

**What rev. 2 changes** (review of rev. 1, §10): the reply claim no longer rests on attack
relations alone. Each kind is decided by `exchange` (SEE) records, and the cover is checked on
the position after the best move and the reply, a node the claim asks for without a search
(B1). The comparison detail gets its own plan field (B2). A repetition by rule (threefold) is told
apart from the engine's draw score, and the score needs the WDL (B3). Every fact path and node
anchor is stated against the real record types (B4). No fact-engine change is needed: the
families (`squares`, `exchange`, `draw`, `move`) and the need types (`LineNeed`, `FamilyNeed`)
exist; `piece_offer_v1` already uses both.

**What rev. 3 changes** (re-review of rev. 2, §10): DEFENDS also requires the reply to be legal
after the best move, and its sentence names the exchange on the square (B5). A third occurrence
is told as a draw that can be claimed, not as a draw; only a fifth occurrence is told as drawn
(FIDE 9.2, 9.6; B6). The reply claim's scope covers the plies it reads (N3), and each kind asks
for `exchange` only where it reads it (N4).

**What rev. 4 changes** (rev. 3 review, B7): DEFENDS no longer uses a square-level SEE
at A1/B1 to infer the gain of a specific reply. Instead it fixes the same reply `r`
in the played branch (`A1 + r = R`) and the best-move counterfactual branch
(`B1 + r = C`), then compares the gain of that *specific first capture*
using existing `exchange` records at R and C (§3). As with COVERS, the
counterfactual node needs no engine search. The previously reported
DEFENDS example is provisional until re-measured in EV1.

## 0. Evidence: every ply of the owner's two games

Both games were re-analysed with the shipped build (Stockfish 19, `d12_mpv5_v1`; 78 + 101
plies). For every ply, a scan recorded, for `Lp` and `L1`, the score, the WDL, the checking runs
of each side, the `draw` facts of each node from the run's first ply, the outcome; and, for the
reply `r` (`Lp` ply 2): the attackers of its square at `A1` and `B1` with their pins, the
`exchange` records at `P`, `A1` and `B1`, and the `exchange` record at the node `B1 + r`, created
without a search. Rev. 4 additionally needs the exchange after the actual reply R, and the exchange after the same reply C: previous square-level measurements do not establish either reply-conditioned gain. EV1 must measure them. Scripts and their output are reproduced in EV1 (§6.6).

### 0.1 Mistakes and blunders that still say no reason

Of the 15 mistakes and blunders in the two games, 7 are explained by material or mate (39.Qe8+,
32...Bc3, 5.d4, 8.O-O, 13...Bb4, 17...Be8, 47.Ne6+). The other 8 say only "Instead, X was
better":

| Move | Loss | What the lines show |
| --- | --- | --- |
| 33.b6 | 447 | `Lp` ends in black checks (35...Qxe1+, 36...Qe2+), score 0.00, WDL draw 991‰, no position repeated; `L1` +5.33 |
| 38...f5 | 530 | `L1` (38...Qe2+) is three black checks; its last node is a third occurrence (`threefold_reached`), 0.00; `Lp` −6.15 |
| 13.c4 | 400 | `Lp` loses the exchange (balance −2, stable) but `L1`'s window ends mid-exchange (`OPEN`), so `material_loss_v1` is `INCONCLUSIVE(LINE_TOO_SHORT)` |
| 28.b5, 28...cxb5, 12.Bd3, 6.Nxd4, 7...Nxe4 | 232–458 | no mate, no material difference that the windows decide: positional, or beyond the window |

### 0.2 Draws by checks

A **checking run** of side `c` in a line is the longest run, ending at the window's last ply of
`c`, of `c`'s plies that all give check without mate. Over all 179 plies, 33 standard lines (a
ply's `Lp` and `L1` counted apiece) have a run of at least 2:

- 24 also have a draw score (|cp| ≤ 10 and WDL draw ≥ 900‰). The WDL was available on every
  line of both games. By what the `draw` facts show from the run's first ply on:
  - **1 reaches a third occurrence** (`threefold_reached`): `L1` of 38...f5.
  - **11 repeat a position** (`occurrences ≥ 2`, no third occurrence): the 35.Bxe1 – 38.Kg2
    lines.
  - **12 repeat nothing inside the window**: among them `Lp` of 33.b6, whose PV stops at
    37.Kg1. A search from there continues 37...Qe1+ 38.Kg2 Qe2+ 39.Kh3 Qh5+ 40.Kg2, still all
    checks, but proves no repetition within the PV either.
- All but two of the 24 belong to plies graded best or excellent in the 33...Qe2 – 38.Kg2
  sequence. Among plies graded INACCURACY or worse they occur exactly twice: 33.b6 (`Lp`,
  Black's checks, no repetition) and 38...f5 (`L1`, the mover's checks, threefold).
- The 9 runs without a draw score (24.Rfb1 +1.21, 47...Ke8 +9.14, …) are checks that are not a
  draw; the score condition excludes them.
- A WDL draw of at least 900‰ alone is common: 11 plies graded INACCURACY or worse have one
  standard line so drawn and the other not (e.g. 13.c4's `L1`, an equal position). A draw score
  without the checks says nothing about checks.

So the cases are told apart in the text (§2): a third occurrence along the line lets a draw be
claimed (FIDE 9.2; only a fifth draws by itself, 9.6); a repetition or a draw score without it is
only what the engine scores.

### 0.3 What the better move does about the reply

Let `s` be the destination of `Lp`'s ply 2, the opponent's reply `r`. In 23 plies the best
move's piece attacks `s` after the best move; in none of them is that piece absolutely pinned.
Among the 10 graded INACCURACY or worse, the static exchange records decide:

| Move | `s` | `Lp` | Best | Static exchange (`see_v1`) | Kind (§3) |
| --- | --- | --- | --- | --- | --- |
| 33.b6 | e2 | 33...Qe2, the queen then checks (35...Qxe1+, 36...Qe2+) | 33.Qc2 | at `B1 + r` (33.Qc2 Qe2), White wins 9 on e2, first capture 34.Qxe2 (from c2) | COVERS |
| 14...O-O | d5 | 15.cxd5 takes the pawn (`material_loss_v1`) | 14...Be6 | Previous square SEE +1 at A1, 0 at B1 is not reply-conditioned. EV1 must prove `g(R) ≥ 1` and `g(C) ≤ 0` for **15.cxd5** | DEFENDS **candidate** |
| 49.Bxa3, 50.Bc5, 51.a4 | e6 | …Kxe6 takes the knight (balance −2 … −4) | 49.Ng5+, 50.Nc5, 51.Nc7 | knight e6: gain 3 at `P` (hypothetical) and at `A1`; the best move is in its `safe_moves` at `P` | RESCUES |
| 32...Bc3 | c2 | 33.Qc2, a defensive move that neither checks nor captures later | — | — | none: the reply does nothing the claim could name |
| 38...f5 | c2 | 39.Qc2, likewise | — | `r` is not legal after 38...Qe2+ (check) | none |
| 3...f5 | d4 | 4.d4 exd4: the mover already attacked d4 at `A1` | — | — | none: not new |
| 26.Rb4, 27...Be6 | b4, e6 | the reply captures the piece the played move put on `s` | — | the piece was not on `s` at `P` | none: the played move's own exchange |

The previous scan nominated five rows; rev. 4 makes the DEFENDS row conditional until the forced-reply check at R and C passes. EV1 must record the final number of supported cases. As an outside check
(not used by any rule; Stockfish 19, depth 16, separate searches): after 33.Qc2 the engine's
reply is 33...Ba5 (+6.04), and 33.Qc2 Qe2 forced scores +11.75 (34.Qxe2).

### 0.4 Lines that end before the material settles (not in this packet)

In 73 of 179 plies a standard line is `OPEN`, every time because the engine's PV ends before the
window can widen to a settled position (attached plies = PV length). One more search from the
line's end would continue it. A rough check of the 16 graded cases (python-chess counting, no
`material_flow`) gives mixed results: some lines settle (13.c4's `L1` at +1 against `Lp`'s −2),
others swing on a truncated continuation (4.f4's `L1` +9). That needs its own design (§8).

## 1. Decisions

| # | Decision |
| --- | --- |
| V1 | **A checking draw** (§2.1) is a property of one line of S: a run of at least `CHECK_RUN = 2` checks by one side ending the window, a `Cp` score with `|cp| ≤ DRAW_CP = 10`, and one of: a node from the run's first ply on with `fivefold_reached` (**FIVEFOLD**) or `threefold_reached` (**THREEFOLD**), or an available WDL with draw ≥ `DRAW_WDL = 900`‰ (**REPEATED** when a node from the run's first ply on has `occurrences ≥ 2`, else **SCORED**). Without the WDL and without a third occurrence there is no claim (rev. 2, B3). |
| V2 | **`checks_draw_v1`** (CONSEQUENCE, backward): the played move's line is a checking draw and the move is graded INACCURACY or worse. Either side may give the checks: the opponent's ("Black gives check after check") or the mover's own (the mover settles for a draw). |
| V3 | **`checks_draw_missed_v1`** (COMPARISON, backward): the best line is a checking draw by the mover and the move is graded INACCURACY or worse. It replaces `missed_gain_v1` / `better_alternative_v1` as the comparison when it holds (planner order, §4). |
| V4 | **`best_stops_reply_v1`** (COMPARISON detail, backward), three kinds decided by `exchange` records (rev. 2, B1): RESCUES (the reply captures a piece the best move moves to one of its `safe_moves`), DEFENDS (the same capture `r` is profitable in the played branch but has no positive static exchange gain after the best move, with a new defender), COVERS (after the best move, the reply would put its piece where the best move's piece wins it: SEE on the node `B1 + r`). |
| V5 | **The detail is its own plan field and sentence** (rev. 2, B2): `ExplanationPlan.detail`, 0–1 claim id, rendered as S6b after the comparison (and after the MISS sentence). The comparison, and MISS, which grounds on `missed_gain_v1`, are unchanged. |
| V6 | **No new fact family, no extra engine search.** Every condition reads shipped facts (`move`, `squares`, `exchange`, `draw`, `status`, material flow) and S. DEFENDS and COVERS may create the rule-only `C = B1 + r` node without a search (`LineNeed`, `ExpansionSpec(False, False, False)`) and request `exchange`, as `piece_offer_v1` does. No comparison between two searches (R2-D §4). |
| V7 | **Wording follows what is proved** (rev. 2, B1, B3; rev. 3, B6). "the game is drawn" only for FIVEFOLD (FIDE 9.6); "a third time, so a draw can be claimed" for THREEFOLD (FIDE 9.2: a claim, not an automatic draw; online platforms that draw it automatically are not assumed, owner 2026-10-14); "repeating the position" only for REPEATED; otherwise "the engine scores it as a draw". Never "perpetual". COVERS says "covers {square}: after {best}, {reply} would lose …", a static exchange result, never "stops", which would need the engine's view of `B1 + r` (§8). |
| V8 | **Versioned.** New templates, finding types, a plan field and phrases change the build digest; stored claim graphs are re-analysed (R4-D §2.1). |

## 2. Draws by checks

### 2.1 The checking draw of a line

For a line `L` of S over its window `N_0 … N_k`, from the mover `m` at P, and a side `c`:
- `plies(c)` = `c`'s plies in the window: odd plies for `m`, even plies for `o`.
- The **run** of `c` = the longest suffix of `plies(c)` in which every ply gives check and none
  gives mate (`MoveFacts.gives_check`, `MoveFacts.gives_mate` of the edge into `N_i`). Its first
  ply is `q`; `N_q` is the node after the run's first check.
- `L` is a **checking draw by `c`** of kind `K` when:
  1. the run has at least `CHECK_RUN` (2) plies;
  2. `L`'s `EngineLineFact.score` is a `Cp` with `|value| ≤ DRAW_CP` (10); a `Mate` is never a
     draw;
  3. the window does not end in checkmate (`N_k` is not terminal by mate);
  4. and `K` is the first that holds:
     - **FIVEFOLD**: some `N_i`, `q ≤ i ≤ k`, has `DrawFacts.fivefold_reached is True` (the
       game is drawn, FIDE 9.6);
     - **THREEFOLD**: some `N_i`, `q ≤ i ≤ k`, has `DrawFacts.threefold_reached is True`
       (`HISTORY_UNKNOWN` is not true): a draw can be claimed (FIDE 9.2), the game is not
       drawn by itself;
     - **REPEATED**: `L`'s WDL is a `Wdl` with `draw ≥ DRAW_WDL` (900‰), and some `N_i`,
       `q ≤ i ≤ k`, has `DrawFacts.occurrences ≥ 2` (an `AtLeast(n)` counts as `n`);
     - **SCORED**: `L`'s WDL is a `Wdl` with `draw ≥ DRAW_WDL`.
  When the WDL is `Unavailable` and no node is a third occurrence, `L` is not a checking draw,
  and a claim that needs it is `INCONCLUSIVE(NOT_COMPUTED(wdl))` (§2.2, §2.3).
- **The repetition belongs to the run** (rev. 2, N1): only nodes from `N_q` on count, so a
  position reached before the first check (`N_{q−1}` and earlier) never makes the run "repeat".
  The earlier occurrence it repeats may lie anywhere in the counted history (the game's moves
  before P included, as the `draw` family counts them): the checks bring the position back.

Why these values (§0.2): a score of exactly 0.00 marks both lines of the owner's games; 10 cp
admits an engine's near-zero rounding but no advantage. The WDL condition excludes a sharp line
that scores 0.00 by balance. A third or fifth occurrence is a rule fact, so FIVEFOLD and THREEFOLD do not need the WDL;
the score condition still applies, as a check that the engine's line is the drawn one. The run
of 2 is the smallest that is "check after check"; both lines of §0.2 reach it inside their
windows.

**Finding:** `ChecksDrawFinding(checker: Color, kind: DrawKind, line: LineSegment, checks: int,
repeat_at: MoveRef | None)`; `DrawKind = FIVEFOLD | THREEFOLD | REPEATED | SCORED`; `line` is
`LineSegment(L, q − 1, k)` (it shows the edges into `N_q … N_k`); `repeat_at` is the edge into the
first node that is a fifth occurrence (FIVEFOLD), a third occurrence (THREEFOLD) or a repetition
(REPEATED), else `None`.

**Evidence** (paths as `lines.fact_ref(view, family, node, path)` builds them; `move` is an
EDGE family keyed by the child node, `draw` a NODE family):
- `SearchRef(S, L.rank)` (score and WDL);
- `fact_ref(view, "move", N_i, ("gives_check",))` for each ply `i` of the run;
- FIVEFOLD: `fact_ref(view, "draw", N_j, ("fivefold_reached",))`; THREEFOLD:
  `fact_ref(view, "draw", N_j, ("threefold_reached",))`, for the node `N_j` of `repeat_at`; REPEATED: `fact_ref(view, "draw", N_j, ("occurrences",))`.

### 2.2 `checks_draw_v1` — CONSEQUENCE, backward

- **Proposed when:** the judgement is decided, its grade is INACCURACY or worse, and `Lp` and
  `L1` are attached.
- **`Template.make`** (rev. 2, N2): `context = LineContext(seg(Lp))`, `operands = (Lp.window,
  L1.window)` (the `line_material` windows), `target = line_target(seg(Lp))` (SPECIFIC_LINE,
  ENGINE_REPORTED S), `premises = ()`, `origins = (judgement_ref(ctx),)`.
- **Verify:** rules 1–2 of R2-D §3.1 do **not** apply (a drawn window is this claim's subject,
  and a mate score is condition 2's business).
  - `SUPPORTED` when `Lp` is a checking draw by either side and `L1` is not a checking draw by
    the same side; the opponent's run is tried first.
  - `REFUTED` when neither side's run meets conditions 1–3, or `L1` is a checking draw by the
    same side.
  - `INCONCLUSIVE(NOT_COMPUTED(<family>))` when a needed `move` or `draw` record is missing,
    `INCONCLUSIVE(NOT_COMPUTED(wdl))` when conditions 1–3 hold, no node is a third occurrence
    and the WDL is `Unavailable`. No template declares a `QUALIFIES` edge to it, so it is never
    rendered as pending.
- **Proof scope:** `scope(view, h, grading, (Lp.rank, L1.rank), line=Lp)`; basis ENGINE (the line
  is the engine's choice, also for FIVEFOLD and THREEFOLD).
- **Phrases** (`checker = o` / `checker = m`, then the kind):
  - `sentence.opponent.scored` = "Along the engine line, {side} then gives check after check,
    {line}, and the engine scores it as a draw."
  - `sentence.opponent.repeated` = "Along the engine line, {side} then gives check after check,
    {line}, repeating the position, and the engine scores it as a draw."
  - `sentence.opponent.threefold` = "Along the engine line, {side} then gives check after check,
    {line}, repeating the position a third time, so a draw can be claimed."
  - `sentence.opponent.fivefold` = "Along the engine line, {side} then gives check after check,
    {line}, repeating the position a fifth time: the game is drawn."
  - `sentence.mover.scored` = "It settles for checks, {line}, which the engine scores as a draw."
  - `sentence.mover.repeated` = "It settles for checks, {line}, repeating the position, which
    the engine scores as a draw."
  - `sentence.mover.threefold` = "It settles for checks, {line}, repeating the position a third
    time, so a draw can be claimed."
  - `sentence.mover.fivefold` = "It settles for checks, {line}, repeating the position a fifth
    time: the game is drawn."
  - `{side}` is "White" or "Black" (`fmt_side`); `{line}` the finding's segment, formatted as
    R3-D's lines (at most six plies, "..." when cut).

### 2.3 `checks_draw_missed_v1` — COMPARISON, backward

- **Proposed when:** the judgement is decided, its grade is INACCURACY or worse, the played move
  is not rank 1, and `Lp` and `L1` are attached.
- **`Template.make`:** `context = LineContext(seg(L1))`, `operands = (L1.window, Lp.window)`,
  `target = line_target(seg(L1))`, `premises = ()`, `origins = (judgement_ref(ctx),)`, as
  `better_move_v1`.
- **Verify:** `SUPPORTED` when `L1` is a checking draw by `m` and `Lp` is not a checking draw by
  either side; `REFUTED` otherwise; `INCONCLUSIVE` as in §2.2. (The loss already shows that the
  draw is better for `m` than `Lp`.)
- **Proof scope:** `scope(view, h, grading, (L1.rank, Lp.rank), line=L1)`.
- **Phrases:**
  - `sentence.scored` = "Instead, {best} was needed: it starts a series of checks, {line}, which
    the engine scores as a draw."
  - `sentence.repeated` = "Instead, {best} was needed: it starts a series of checks, {line},
    repeating the position, which the engine scores as a draw."
  - `sentence.threefold` = "Instead, {best} was needed: it starts a series of checks, {line},
    repeating the position a third time, so a draw can be claimed."
  - `sentence.fivefold` = "Instead, {best} was needed: it starts a series of checks, {line},
    repeating the position a fifth time: the game is drawn."

## 3. `best_stops_reply_v1` — COMPARISON detail, backward

### 3.1 Notation and proposal

- **Proposed when:** the judgement is decided, its grade is INACCURACY or worse, the played move
  is not rank 1, and both `Lp` and `L1` are attached with `Lp` reaching ply 2.
- **Notation:** `b` = the best move (`L1` ply 1, node `B1 = N_1(L1)`), `A1 = N_1(Lp)` (after the
  played move), `r` = `Lp`'s ply 2 (the reply, node `R = N_2(Lp)`), `s` = `r`'s destination, `X`
  = the piece that plays `r` (`MoveFacts.piece`), `C = child(B1, r)` (DEFENDS and COVERS).
- **Square index:** `idx(s) = file + 8 · (rank − 1)` (a1 = 0 … h8 = 63), the order of
  `SquaresFacts.squares`. `att(N, s, m)` = the `Relation`s of `m`'s attackers of `s` in
  `squares` at `N` (`white_attackers` or `black_attackers` of `squares[idx(s)]`) whose
  `absolutely_pinned` is false (rev. 2, B1: a pinned piece is not counted).
- **Exchange record:** `ex(N, sq)` = the `PieceExchange` of `ExchangeFacts.pieces` at `N` whose
  `square` is `sq`, at index `i` in that tuple. Its `gain` is real for a piece of the side not to
  move and hypothetical (turn passed) for the side to move (F6-D X2). "gain = g" means a
  `Defined` gain equal to `g`; a `NotApplicable` gain never satisfies a condition.
- **`Template.make`** (rev. 2, N2): `context = LineContext(seg(L1))`, `operands =
  (LineSegment(L1, 0, 1), LineSegment(Lp, 0, k_p))` (`k_p` = `Lp.window.last`: the plies the
  claim reads), `target = line_target(seg(L1))` (SPECIFIC_LINE, ENGINE_REPORTED S),
  `premises = ()`, `origins = (judgement_ref(ctx),)`.

- **Specified-reply SEE (rev. 4, B7):** For DEFENDS,
  `r` is an ordinary capture of a non-king victim `V` on `s`
  by the same non-king piece `X` in both branches. Let
  `R = A1 + r` (already in Lp), `C = B1 + r`,
  `v = points_v1(V)`, and
  `q(N) = ex(N,s).gain.value` for `N` in `{R,C}`,
  where `ex(N,s)` is the `Defined` SEE record of X at s,
  with mover `m` to play. The *reply-conditioned* static gain
  for the player of r is `g(N) = v - q(N)`.
  Hence `g(R)` measures the played reply r and `g(C)` measures
  that **same** reply after b. The first capture is fixed as r;
  only the continuation is chosen by the existing `see_v1`
  least-valuable-attacker algorithm. This is not a claim that
  all later attacker orders or other-board tactics are optimized.
  Do not substitute `ex(A1,s).gain` or `ex(B1,s).gain` for g.

### 3.2 Needs

`exchange` is on request (F6-D). Before requests, use rule facts
(`move`, `squares`, `status`, identity and line outcome) to exclude
irrelevant kinds. For records still `NotComputed`:

- **RESCUES:** `FamilyNeed(P, "exchange")`, `FamilyNeed(A1, "exchange")`.
- **DEFENDS:** `LineNeed(B1, (r,), ExpansionSpec(False, False, False))`
  if C is absent; `FamilyNeed(R, "exchange")`; and after C exists,
  `FamilyNeed(C, "exchange")`. R and the extension of B1 may be
  requested in the same round.
- **COVERS:** `LineNeed(B1, (r,), ExpansionSpec(False, False, False))`
  if C is absent, then `FamilyNeed(C, "exchange")`.

DEFENDS and COVERS require at most two **request rounds**, and
verification on the third/final round of the default `max_rounds = 3`.
When C already exists, one ensure round may suffice. No new
Stockfish search occurs; C is a rule-only node, with at most one
additional node per claim. Request refusal, budget exhaustion or
missing facts close INCONCLUSIVE (`BUDGET`, `ROUND_LIMIT`,
`NEED_UNMET`, or `NOT_COMPUTED(<error>)`); no detail is rendered.

### 3.3 Kinds

The kind follows from `r`: a capture gives RESCUES or DEFENDS, a non-capture COVERS.

1. **RESCUES** — `r` captures (`Capture` in `r`'s events) a piece `V` of `m` on `s`, `V` stands
   on `s` at P and at `A1` (same `PieceId`), and `b` moves `V` (`b`'s from-square is `s`):
   - `ex(P, s)`: gain ≥ 1 (hypothetical: `V` was exposed before the move), and `b`'s UCI is in
     its `safe_moves` (after `b`, `V` is not exposed);
   - `ex(A1, s)`: gain ≥ 1 (real: still exposed after the played move);
   - `Lp`'s outcome is `STABLE(Δp ≤ −1)` and the balance after ply 2 is below the balance after
     ply 1 (the capture costs material along the line).
2. **DEFENDS** — `r` captures a piece `V` of the mover
   on its destination square s; `V` has the same `PieceId`
   at P, A1 and B1, and b does not move V.
   - `r` is an **ordinary** capture: no en passant, no
     promotion, no king as the capturing piece. Those cases
     are excluded rather than assigned misleading SEE values.
   - `r` is legal at B1, ruling out a supposed defence due
     solely to a check, pin or an otherwise illegal reply.
   - Both incoming `MoveFacts` at R and C record a capture of
     the same victim V on s by the same moving PieceId X,
     and X occupies s afterward. If the captured identity,
     destination or capturer differs, REFUTED.
   - Exchange records of X on s at both R and C have
     `Defined` gains. Compute `g(R)`, `g(C)` as above and
     require **`g(R) ≥ 1` and `g(C) ≤ 0`**. No square-level
     gain substitutes for these individual forced-reply gains.
   - The moved piece at b's destination is a new, unpinned
     attacker of s in `att(B1,s,m)`, not among the attackers
     at A1 (even pinned attackers count as pre-existing).
     The SEE witness `ex(C,s).first_capture` must originate
     from b's destination, tying the actual static recapture
     to the new defender.
   - Lp is `STABLE(Δp ≤ −1)`, with material balance falling
     after ply 2. The explanation thus refers to a genuine
     lost-material opportunity in the played line.
   - Missing records produce INCONCLUSIVE pending §3.2
     needs. Unsupported conditions REFUTE, never degrade
     silently into square-level SEE.

3. **COVERS** — `r` is not a capture:
   - `s` is empty at P and at `A1`;
   - `att(A1, s, m)` is empty; `b`'s piece is in `att(B1, s, m)`;
   - `X` gives check or captures at a later ply of `Lp`'s window (plies 3 … `k_p`): the square
     matters in the line;
   - `L1`'s ply 2, when attached, is not `r` (the opponent does not enter `s` anyway);
   - `r` is legal at `B1` (`status.legal_moves` at `B1`);
   - `ex(C, s)` (the record of `X`, `m` to move): gain ≥ 1 (real), and its `first_capture`
     starts from `b`'s to-square (the best move's piece makes the capture).
- Otherwise `REFUTED`. A missing `move`, `squares` or `status` record is
  `INCONCLUSIVE(NOT_COMPUTED(<family>))`; `exchange` is a need (§3.2).
- **Why:** RESCUES proves a threatened piece is safely moved;
  DEFENDS now compares the **same specific capture** at R and C,
  finding positive material gain after the played move and
  nonpositive gain after b under the shipped SEE continuation.
  The first recapture is made by b's new defender. COVERS
  evaluates a noncapture reply from the position after b and r.
  The exclusions of §0.3 and the older B5 illegality issue
  remain enforced.
- **Epistemic limit (B1, B5, B7):** SEE is a deterministic
  static exchange on one square with least-valuable-attacker
  ordering. Forcing r eliminates ambiguity about **which
  initial capture** is evaluated, but cannot prove tactical
  outcomes elsewhere or optimal choice among all possible
  subsequent attackers. DEFENDS says "under static exchange
  evaluation" and does not claim r is objectively unsound.
  COVERS likewise states its static exchange and never
  says the best move forces the opponent to avoid r.
  `see_v1` stays in the proof policy.

### 3.4 Finding, evidence, scope, phrases

- **Finding:** `ReplyFinding(kind: ReplyKind, best: SearchMoveRef,
  reply: MoveRef, piece: PieceRef, square: SquareRef | None,
  board: NodeId | None, counter: NodeId | None,
  answer: str | None, lost: int | None,
  played_gain: int | None, best_gain: int | None)`.
  This adds the two optional, versioned integer fields for
  reply-conditioned gain and therefore changes the type digest.
  - All kinds: `best = SearchMoveRef(S,1,1)`,
    `reply = MoveRef(R)`.
  - RESCUES: `piece = PieceRef(V,P,s)`; optional fields None.
  - DEFENDS: `piece = PieceRef(V,B1,s)`,
    `square = SquareRef(s)`, `board = B1`,
    `counter = C`, `answer = ex(C,s).first_capture`,
    `played_gain = g(R)`, `best_gain = g(C)`;
    `lost = None`.
  - COVERS: `piece = PieceRef(X,C,s)`,
    `square = SquareRef(s)`, `board = B1`,
    `counter = C`, `answer = ex(C,s).first_capture`,
    `lost = ex(C,s).gain.value`, the two gain fields None.
- **Evidence** (actual fact paths; exchange tuple indices differ
  by node and must be looked up separately):
  - All kinds: `SearchRef(S,1)`,
    `SearchRef(S,Lp.rank)`.
  - RESCUES: `fact_ref(view,"move",R,("events",e_R))`,
    `fact_ref(view,"exchange",P,("pieces",i_P))`,
    `fact_ref(view,"exchange",A1,("pieces",i_A1))`.
  - DEFENDS: both capture events,
    `fact_ref(view,"move",R,("events",e_R))` and
    `fact_ref(view,"move",C,("events",e_C))`;
    exchange records of the capturer X on s,
    `fact_ref(view,"exchange",R,("pieces",i_R))`
    and `fact_ref(view,"exchange",C,("pieces",i_C))`;
    `fact_ref(view,"status",B1,("legal_moves",l))`
    for r; `fact_ref(view,"squares",B1,
    ("squares",idx(s),side,j))` for b's unpinned
    defending relation. Extract v from the victim's
    `Capture.piece_type` using `points_v1`;
    check the PieceIds of both captured victims and
    capturers. Store computed g(R) and g(C) in the finding.
  - COVERS: `fact_ref(view,"move",R,("to_square",))`;
    `fact_ref(view,"squares",A1,("squares",idx(s),side))`;
    `fact_ref(view,"squares",B1,
    ("squares",idx(s),side,j))`;
    `fact_ref(view,"status",B1,("legal_moves",l))`;
    `fact_ref(view,"exchange",C,("pieces",i_C))`;
    the `fact_ref(view,"move",N_i,())` of X's later
    check or capture. G3 resolves all paths.
- **Proof scope:** `scope(view,h,grading,(1,Lp.rank),
  line=Lp,extra_policies=("see_v1",))`, basis ENGINE.
  The recorded plies cover every Lp ply used by the kind.
  The qualification explicitly says exchanges are judged
  by static exchange evaluation.
- **Renderer slots:** `{best}` is
  `fmt_move(SearchMoveRef(S,1,1))`; `{reply}`
  is `fmt_move(MoveRef(R))` for RESCUES/DEFENDS,
  and the move r from B1 for COVERS (with
  `TraceRef("search_move",B1,uci=r)`). `{piece}`
  uses `fmt_piece(piece)`; `{square}` uses
  `fmt_square` and `TraceRef("square",B1,square=s)`.
  `{capture}` is the answer UCI rendered from C;
  `{amount}` is `fmt_amount(lost)`.
- **Phrases:**
  - `sentence.rescues` = "{best} saves {piece} from {reply}."
  - `sentence.defends` = "{best} defends {piece}: if {reply},
    the static exchange on {square} yields no net gain,
    starting with {capture}."
  - `sentence.covers.piece` (lost ≥ value of X) =
    "{best} covers {square}: after {best}, {reply} would
    lose {piece} in the exchange there, starting with {capture}."
  - `sentence.covers.material` (otherwise) =
    "{best} covers {square}: after {best}, {reply} would
    lose material in the exchange there (net {amount}),
    starting with {capture}."
  Examples: "49.Ng5+ saves the knight on e6 from
  49...Kxe6." "33.Qc2 covers e2: after 33.Qc2,
  33...Qe2 would lose the queen on e2 in the exchange
  there, starting with 34.Qxe2." The conditional
  DEFENDS example is §6.

## 4. The plan and the renderer (rev. 2, B2)

`ExplanationPlan.justification` keeps its R3-D meaning: one comparison claim id, then its best
line (`WITH_LINE`). The detail does not go into it.

- **New field** `ExplanationPlan.detail: tuple[str, ...]`, placed after `justification`: 0–1
  claim id, type `str`, template `best_stops_reply_v1`. The field is part of the plan's
  canonical encoding, so `plan_digest` and R4's stored `plan` change (V8).
- **Planner rule 6b** (after rule 6, for MISS too): when the plan's comparison (the first `str`
  of `justification`, from rule 2's MISS ground or rule 6) has a template in
  `DETAIL_AFTER = ("better_move_v1", "missed_gain_v1", "better_alternative_v1")`, `detail` =
  the first SUPPORTED `best_stops_reply_v1` of the subject by id; else `()`. After
  `mate_missed_v1` and `checks_draw_missed_v1` there is no detail (they already say why).
- **Rule 7:** the detail is among the selected claims, so its scope is qualified (see_v1).
- **Renderer, S6b:** after S6 (and after the MISS sentence, which is S6 for MISS), `detail[0]`
  is rendered as its own sentence with its claim as source. R3-D H1 becomes "at most ten
  sentences: S1–S6b at most one each, and S7".
- **Guard G4** gains: `len(detail) ≤ 1`; the detail claim is SUPPORTED and its template is
  `best_stops_reply_v1`; `detail` is non-empty only when `justification` holds a comparison in
  `DETAIL_AFTER`; it is in G4's assertive list beside the other roles.
- **`trace`** reproduces the new segment like any other (it is `render` with references kept).

## 5. Code changes (the contract of EV1)

| Place | Change |
| --- | --- |
| `reasoning/lines.py` | `checking_draw(view, line, side)`: the finding, `None`, or the reason a record is missing (§2.1); its constants `CHECK_RUN`, `DRAW_CP`, `DRAW_WDL` (§2.1) |
| `reasoning/findings.py` | `DrawKind`, `ChecksDrawFinding`, `ReplyKind`, `ReplyFinding`; all in `KINDS` (the type registry: the build digest changes) |
| `reasoning/catalogue/draws.py` (new) | `ChecksDraw` (`checks_draw_v1`), `ChecksDrawMissed` (`checks_draw_missed_v1`) |
| `reasoning/catalogue/comparison.py` | `BestStopsReply` (`best_stops_reply_v1`); DEFENDS forces the same reply in R and C, computes conditional gains and binds the witness recapture; §3.2 needs follow `piece_offer_v1` |
| `reasoning/catalogue/__init__.py` | `CATALOGUE_V1` gains the three, after `material_gain_v2` (`checks_draw_v1`) and after `better_move_v1` (`checks_draw_missed_v1`, `best_stops_reply_v1`) |
| `reasoning/planner.py` | `ExplanationPlan.detail`; rule 3: `DRAWS = ("checks_draw_v1",)` tried after `MATERIAL`; rule 6: `COMPARISONS = ("mate_missed_v1", "better_move_v1", "checks_draw_missed_v1", "missed_gain_v1", "better_alternative_v1")`, `WITH_LINE` unchanged; rule 6b with `DETAILS = ("best_stops_reply_v1",)` and `DETAIL_AFTER` (§4) |
| `reasoning/labels.py` | unchanged: MISS keeps `missed_gain_v1` (a MISS ply's comparison stays its ground, so `checks_draw_missed_v1` is not shown on a MISS ply) |
| `reasoning/render/__init__.py` | `fmt_square(h, ref: SquareRef, board: NodeId)` → `TraceRef("square", board, square=…)`; `fmt_side`; `bind` branches for the three templates (§2.2, §2.3, §3.4); S6b; G4 (§4) |
| `reasoning/render/phrases/en.toml` | `[checks_draw_v1]`, `[checks_draw_missed_v1]`, `[best_stops_reply_v1]` (§2–§3); `[claim]` names "draw by checks", "missed draw by checks", "answer to the reply" |
| `reasoning/encoding.py` | the new finding types (`KINDS`) and the plan field |
| `results/document.py` | `_ref` for kind `square`: `{"kind": "square", "square": s, "fen": <FEN of the board node>}` (the schema and the viewer already accept it) |
| `docs/design` | R2-D (templates), R3-D (H1, §1 rule 6b, §2 S6b, §7 G4) and R4-D (stored `plan`) record the amendments |

The fact engine is unchanged: `squares` (pins), `exchange` (on request), `draw`, `status`,
`move`, and the `LineNeed` / `FamilyNeed` paths of `reasoning/runner.py` are used as shipped.

## 6. What changes in the two games (expected, from §0; EV1 re-runs both)

| Move | Added |
| --- | --- |
| 33.b6 | "Along the engine line, Black then gives check after check, 35...Qxe1+ 36.Kg2 Qe2+ 37.Kg1, and the engine scores it as a draw." and, after the MISS sentence, "33.Qc2 covers e2: after 33.Qc2, 33...Qe2 would lose the queen on e2 in the exchange there, starting with 34.Qxe2."; the qualification names static exchange evaluation |
| 38...f5 | "Instead, 38...Qe2+ was needed: it starts a series of checks, 38...Qe2+ 39.Kg1 Qe1+ 40.Kg2 Qe2+, repeating the position a third time, so a draw can be claimed." (replaces "Instead, 38...Qe2+ was stronger.") |
| 14...O-O | **Conditional on EV1** confirming `g(R) ≥ 1`, `g(C) ≤ 0` and the defender recapture: after the comparison, "14...Be6 defends the pawn on d5: if 15.cxd5, the static exchange on d5 yields no net gain, starting with 15...Bxd5." Otherwise do not render DEFENDS; record the observed gains |
| 49.Bxa3, 50.Bc5, 51.a4 | "49.Ng5+ saves the knight on e6 from 49...Kxe6.", "50.Nc5 saves the knight on e6 from 50...Kxe6.", "51.Nc7 saves the knight on e6 from 51...Kxe6." |
| every other ply | unchanged text; a ply graded INACCURACY or worse may hold a new INCONCLUSIVE or REFUTED claim that is not rendered |

## 7. Test obligations (packet EV1)

1. **The checking draw** (scripted lines): runs of 1, 2 and 3 checks; a run broken by a quiet
   ply of the checker; a checking mate ending the run; a score of 0, ±10, ±11; a mate score; WDL
   draw 899 / 900 / `Unavailable`; each kind: FIVEFOLD and THREEFOLD (each with the WDL
   `Unavailable` too), REPEATED, SCORED; a third occurrence is THREEFOLD with the "can be claimed"
   sentence and a fifth is FIVEFOLD with "the game is drawn" (B6); `HISTORY_UNKNOWN` is not
   THREEFOLD; a repetition at `N_{q−1}` only (not REPEATED: N1); a repetition counted
   from the game's history and from within the window; a Black checker.
2. **`checks_draw_v1`:** the opponent's checks after an inaccuracy (SUPPORTED, each kind's
   sentence); the mover's own checks; the same checks in `L1` too (REFUTED); a good move (not
   proposed); a missing `draw` record and a missing WDL (INCONCLUSIVE, not rendered).
3. **`checks_draw_missed_v1`:** the 38...f5 shape (SUPPORTED THREEFOLD, chosen over
   `missed_gain_v1`, one "Instead"); `Lp` also a checking draw (REFUTED); the best line drawn
   without checks (REFUTED); a MISS ply keeps its ground.
4. **`best_stops_reply_v1`** (scripted positions and owner games):
   - RESCUES: SUPPORTED, with its evidence paths; missing
     `safe_moves` or no exposure REFUTED.
   - DEFENDS (B7): establish `g(R) ≥ 1`, `g(C) ≤ 0`
     with **identical** legal reply/captured victim/attacking PieceId;
     the new defender makes the `ex(C,s).first_capture`.
     Reject cases where square SEE is 0 at B1 but the **fixed**
     reply remains profitable; where `r` is not the
     least-value attacker; equal-valued attackers have different
     continuations; the victim or capturer differs; the new
     defender is pinned or not new; `r` illegal after a checking
     b; or r is en passant, a promotion, or a king capture.
     R and C missing exchange lead to INCONCLUSIVE, **not**
     fallback to A1/B1 square-level SEE.
   - COVERS: the §3.3 positive case; illegal r, no SEE gain,
     first capture from another piece, already-covered square
     or ineffective later reply REFUTED.
   - Needs: RESCUES requests P/A1; DEFENDS requests R and
     C, creating C without search; COVERS requests C after
     the rule-only extension. Test two-round requests and
     a preexisting C, no unneeded family requests, node/
     ensure budget refusal and `max_rounds=1` closure.
     All evidence paths resolve; proof scope covers Lp.
5. **Plan and guard:** `detail` after `better_move_v1`, `missed_gain_v1`, `better_alternative_v1`
   and after the MISS sentence, and not after `mate_missed_v1` or `checks_draw_missed_v1`; G4
   refuses a detail without a comparison, two details, a detail of another template, and an
   unsupported detail; a plan without detail renders as before (golden texts unchanged).
6. **Through the renderer** (EA-D's lesson): each new template in a corpus case through
   `explain`, `trace` = `render`, R4 save/load (the stored plan with `detail`; the node `C` in
   the stored tree), the result document (`schema_errors` empty; a `square` ref with `B1`'s FEN;
   a `piece` ref with `C`'s FEN) and the viewer test; EA1's coverage test reaches the three.
7. **The owner's two games** re-run: record `g(R)`, `g(C)` and the first recapture for 14...O-O; do not assume the former five positives all survive. Record every changed sentence and every exclusion, and rerun the §0 scan with actual counts.
8. **Build identity:** the digest changes; an EA1 graph is refused by `load`.

## 8. Not in this packet

- **"Stops" with the engine:** a search at `B1` that ranks `r` against the best reply within
  that one search, to say that `r` is bad overall rather than that it loses material on `s`.
  It adds a search per claim and belongs with line continuation.
- **Line continuation** (§0.4): a search from the end of a line whose PV stops before the
  material settles, to decide 73 of 179 plies' `OPEN` lines (13.c4's lost exchange). It changes
  what a line is (two searches), so it needs its own design and measurements.
- **Positional reasons** for the six mistakes of §0.1 with no material or mate difference, with
  a rule for when a positional fact explains a loss.
- **A draw saved by checks** for the defender's good moves (33...Qe2 … 38...Qe2+ in the owner's
  game): a FUNCTION claim; left out because it would repeat the same sentence on six
  consecutive plies.
- **Proving a perpetual**: a repetition the PV does not show (33.b6) is not claimed.
- Square-colour weakness, opening knowledge, the decisive event across exchanges (EA-D §8), and
  the LLM narrator and question answering (owner, 2026-10-13: after explanation v2).

## 9. Delivery

| Packet | Content | Gate |
| --- | --- | --- |
| EV-D (this) | the rules and their evidence | independent review READY |
| EV1 | the three templates, the finding types, the plan field and rule 6b, the renderer and phrasebook, `results` `square` refs, tests, the two games re-run | READY |

## 10. Review dispositions

Independent review of rev. 1 (HEAD `5385b35`): **NOT_READY**, four blocking findings and two
notes. It kept the three kinds, the absence of extra searches, the comparison sentence left
intact, the 73 `OPEN` lines as a separate design and the build-version check.

| Finding | Disposition |
| --- | --- |
| **B1** COVERS proved an attack, not that the best move prevents the reply; `squares_v1` counts absolutely pinned pieces; a piece put on an attacked square may still be good; DEFENDS counted attackers instead of the exchange | Accepted. Every kind is now decided by `exchange` (`see_v1`) records (§3.3): RESCUES by the piece's exposure at P and `A1` and `safe_moves`; DEFENDS by the gain falling from ≥ 1 at `A1` to 0 at `B1`, with a new, unpinned defender; COVERS by the gain on `s` at the node `B1 + r`, created without a search (§3.2), and the first capture made by the best move's piece. Pinned attackers are not counted (§3.1). "stops" is removed: the text says "would lose … to …", a static result, and the scope names `see_v1` (V7, §3.3 "What it does not say"); the engine's view of `B1 + r` is §8's. Re-measured (§0.3): the same five plies and no others |
| **B2** the plan had no structure for a second comparison claim; the renderer reads only the first `str` of `justification` | Accepted. A separate field `ExplanationPlan.detail` (0–1 `str`, template `best_stops_reply_v1`), rule 6b, sentence S6b, G4 checks, R3-D H1 at most ten sentences, the plan's encoding and R4's stored plan (§4, §5) |
| **B3** a near-zero score without the WDL was taken as a draw; an engine score is not a proven draw | Accepted. Three kinds (§2.1): THREEFOLD (a third occurrence from the run on: a draw by rule along the line), REPEATED and SCORED (the engine's score, WDL required). Without the WDL and without a third occurrence there is no claim (`INCONCLUSIVE(NOT_COMPUTED(wdl))`, not rendered). The text says "a draw by threefold repetition" only for THREEFOLD and otherwise "the engine scores it as a draw" (V7) |
| **B4** `FactRef("squares", B1, (s,))` does not match `SquaresFacts` (a tuple of 64 records); `TraceRef("square", …)` needs a node that `SquareRef` does not carry | Accepted. Every path is stated as `fact_ref` builds it, with the tuple index `idx(s)` and the `Relation` index (§2.1, §3.4). The finding carries the board node `B1` beside `SquareRef(s)`; `fmt_square` makes `TraceRef("square", B1, square=s)` and `results` turns it into `{"kind": "square", "square", "fen"}` (§3.4, §5). `SquareRef` itself is unchanged (R0-D §4) |
| **N1** the repetition counted from `N_{q−1}`, before the checks | Accepted: only nodes from `N_q` on count (§2.1); a test with a repetition at `N_{q−1}` only (§7.1) |
| **N2** `BestStopsReply` lacked context, operands, target and scope | Accepted: each template states its `Template.make` fields and proof scope (§2.2, §2.3, §3.1, §3.4) |

Re-review of rev. 2 (HEAD `565a9bd`): **NOT_READY**, two blocking findings and two notes. B2,
B4, N1 and N2 resolved; B1 and B3 each left one problem.

| Finding | Disposition |
| --- | --- |
| **B5** DEFENDS did not check that `r` is legal after `b`: a check by `b` makes the capture illegal and SEE (legal captures only) 0, which would read as a defence; SEE's estimate must not be told as a tactical result | Accepted. DEFENDS requires `r` legal at `B1`, with its `status` evidence (§3.3, §3.4). §3.3 states how SEE's count relates to `r` (one start of the exchange on `s` that SEE estimates, least valuable attacker first). Both DEFENDS and COVERS sentences now name "the exchange on {square}" / "the exchange there", and DEFENDS carries the square shown on `B1` (§3.4). Test: a checking `b` (§7.4) |
| **B6** a third occurrence is a right to claim a draw (FIDE 9.2), not a draw; only the fifth draws automatically (9.6) | Accepted. THREEFOLD says "repeating the position a third time, so a draw can be claimed"; a new kind FIVEFOLD (`fivefold_reached`) says "the game is drawn" (§2.1–§2.3, V7). 38...f5's expected sentence changes accordingly (§6). The fact engine is unchanged: `draw_v1` already records `threefold_reached` and `fivefold_reached` separately. The owner considered platforms that draw a third occurrence automatically (Chess.com, Lichess) and chose the rule wording, which holds everywhere (2026-10-14). Tests separate a third from a fifth occurrence (§7.1) |
| **N3** the scope said `plies=2` while COVERS reads `Lp` past ply 2 | Accepted: the scope takes `line=Lp`, so its plies are `Lp`'s window (§3.4) |
| **N4** each kind needs `exchange` at different nodes | Accepted: per-kind needs, raised only after the kind's rule-fact conditions hold (§3.2) |


Re-review of rev. 3 (HEAD `3064a6b`): **NOT_READY**, B7.

| Finding | Disposition |
| --- | --- |
| **B7** A square-level SEE value does not necessarily evaluate the particular reply `r`, since `see_v1` fixes the least valuable first attacker | Accepted **B**: apply `r` after both A1 (actual R) and B1 (counterfactual C), calculate reply-conditioned `g(R)=v-ex(R,s).gain` and `g(C)=v-ex(C,s).gain`, check exact reply/victim identities and the new defender's first recapture, require `g(R)≥1` and `g(C)≤0`. Add rule-only node and exchange needs, typed findings, accurate static-exchange wording and EV1 tests (§3, §6, §7). No added engine search; existing fact families unchanged. |
