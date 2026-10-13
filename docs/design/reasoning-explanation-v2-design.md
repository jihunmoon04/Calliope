# Reasoning — EV-D design: explanation v2, part 1 (draws by checks, what the better move stops)

Status: **rev. 1 — awaiting independent review**.
Date: 2026-10-13. Base: `main @ 4dd3258`. Inputs:
[`reasoning-r2-design.md`](reasoning-r2-design.md) (R2-D §1 lines, windows, outcome; §3
templates), [`reasoning-r3-design.md`](reasoning-r3-design.md) (R3-D `selection_v1`,
`phrases_en_v1`), [`reasoning-explanation-accuracy-design.md`](reasoning-explanation-accuracy-design.md)
(EA-D: `better_alternative_v1`; its §3a lesson: every place that names a template is listed).

After EA1, every inaccuracy or worse names the better move. It rarely says **why** that move
is better. The owner asked first about 33.b6 of the 836/829 game: White, winning, allows Black's
queen a series of checks, and 33.Qc2 was needed because it covers e2. This packet adds the
explanations that the engine's lines already prove: a line that ends in a draw by checks, and
what the better move does about the opponent's reply. Positional reasons and lines whose window
ends before the material settles are measured here but left to later packets (§8).

## 0. Evidence: every ply of the owner's two games

Both games were re-analysed with the shipped build (Stockfish 19, `d12_mpv5_v1`; 78 + 101
plies). For every ply, a scan recorded, for `Lp` and `L1`, the score, the WDL, the checks given
by each side within the window, the repetition count of each node (`draw` facts), the outcome,
and whether the best move's piece attacks the square of `Lp`'s reply. Scripts and their output
are reproduced in EV1 (§6.6).

### 0.1 Mistakes and blunders that still say no reason

Of the 15 mistakes and blunders in the two games, 7 are explained by material or mate (39.Qe8+,
32...Bc3, 5.d4, 8.O-O, 13...Bb4, 17...Be8, 47.Ne6+). The other 8 say only "Instead, X was
better":

| Move | Loss | What the lines show |
| --- | --- | --- |
| 33.b6 | 447 | `Lp` ends in black checks (35...Qxe1+, 36...Qe2+), score 0.00, WDL draw 991‰; `L1` +5.33 |
| 38...f5 | 530 | `L1` (38...Qe2+) is three black checks, the position repeated (3 occurrences), 0.00; `Lp` −6.15 |
| 13.c4 | 400 | `Lp` loses the exchange (balance −2, stable) but `L1`'s window ends mid-exchange (`OPEN`), so `material_loss_v1` is `INCONCLUSIVE(LINE_TOO_SHORT)` |
| 28.b5, 28...cxb5, 12.Bd3, 6.Nxd4, 7...Nxe4 | 232–458 | no mate, no material difference that the windows decide: positional, or beyond the window |

### 0.2 Draws by checks

A **checking run** of side `c` in a line is the longest run, ending at the window's last ply of
`c`, of `c`'s plies that all give check. Over all 179 plies:

- Runs of at least 2 checks with a draw score (|cp| ≤ 10, WDL draw ≥ 900‰) occur in 24 standard
  lines (a ply's `Lp` and `L1` counted apiece). All but two belong to
  plies graded best or excellent in the 33...Qe2 – 38.Kg2 sequence, where both lines draw by the
  same checks. Among plies graded INACCURACY or worse they occur exactly twice: 33.b6 (`Lp`,
  Black's checks) and 38...f5 (`L1`, the mover's checks).
- Runs of at least 2 checks without a draw score occur in 11 lines (24.Rfb1 +1.21,
  47...Ke8 +9.14, mates …): checks that are not a draw. The score condition excludes them.
- A WDL draw of at least 900‰ alone is common: 11 plies graded INACCURACY or worse have one
  standard line so drawn and the other not (e.g. 13.c4's `L1`, an equal position). A draw score
  without the checks says nothing about checks.
- Repetition inside the window: `L1` of 38...f5 (3 occurrences, counting the game's history) and
  the 35.Bxe1 – 38.Kg2 lines (2). `Lp` of 33.b6 has none: its PV stops at 37.Kg1. A search from
  there continues 37...Qe1+ 38.Kg2 Qe2+ 39.Kh3 Qh5+ 40.Kg2, still all checks, but proves no
  repetition within the PV either. So the claim says what the facts show, checks and a draw
  score, and adds "repeating the position" only when a node of the window repeats (§2).

### 0.3 What the better move does about the reply

Let `s` be the destination of `Lp`'s ply 2, the opponent's reply. In 23 plies the best move's
piece attacks `s` after the best move. Among the 10 graded INACCURACY or worse:

| Move | `s` | `Lp` | Best | Kind (§3) |
| --- | --- | --- | --- | --- |
| 33.b6 | e2 | 33...Qe2, the queen then checks (35...Qxe1+, 36...Qe2+) | 33.Qc2 | COVERS |
| 14...O-O | d5 | 15.cxd5 takes the pawn (`material_loss_v1`) | 14...Be6 (defends d5; `L1` recaptures, balance 0) | DEFENDS |
| 49.Bxa3, 50.Bc5, 51.a4 | e6 | …Kxe6 takes the knight (balance −2 … −4) | 49.Ng5+, 50.Nc5, 51.Nc7 move the knight | RESCUES |
| 32...Bc3, 38...f5 | c2 | 33.Qc2 / 39.Qc2, a defensive move that neither checks nor captures later | — | none: the reply does nothing the claim could name |
| 3...f5 | d4 | 4.d4 exd4: the mover already attacked d4 at P | — | none: not new |
| 26.Rb4, 27...Be6 | b4, e6 | the reply captures the piece the played move put on `s` | — | none: that is the played move's own exchange |

The three kinds below keep exactly the five first rows and exclude the others (§3, rules).

### 0.4 Lines that end before the material settles (not in this packet)

In 73 of 179 plies a standard line is `OPEN`, every time because the engine's PV ends before the
window can widen to a settled position (attached plies = PV length). One more search from the
line's end would continue it. A rough check of the 16 graded cases (python-chess counting, no
`material_flow`) gives mixed results: some lines settle (13.c4's `L1` at +1 against `Lp`'s −2),
others swing on a truncated continuation (4.f4's `L1` +9). That needs its own design (§8).

## 1. Decisions

| # | Decision |
| --- | --- |
| V1 | **A checking draw** (§2.1) is a property of one line of S: a run of at least `CHECK_RUN = 2` checks by one side ending the window, and a score of a draw (`|cp| ≤ DRAW_CP = 10`, and WDL draw ≥ `DRAW_WDL = 900`‰ when the WDL is available). |
| V2 | **`checks_draw_v1`** (CONSEQUENCE, backward): the played move's line is a checking draw and the move is graded INACCURACY or worse. Either side may give the checks: the opponent's ("Black can give check after check") or the mover's own (the mover settles for a draw). |
| V3 | **`checks_draw_missed_v1`** (COMPARISON, backward): the best line is a checking draw by the mover and the move is graded INACCURACY or worse. It replaces `missed_gain_v1` / `better_alternative_v1` as the comparison when it holds (planner order, §4). |
| V4 | **`best_stops_reply_v1`** (COMPARISON detail, backward), three kinds, each read from `P`, `Lp`'s first two plies and `L1`'s first ply: COVERS (the best move attacks the empty square the opponent's piece enters, and that piece later checks or captures in `Lp`), DEFENDS (the best move defends the piece the reply captures), RESCUES (the best move moves the piece the reply captures). |
| V5 | **The detail is its own sentence**, after the comparison sentence, so the comparison (and MISS, which grounds on `missed_gain_v1`) is unchanged: "This is a missed opportunity; instead, 33.Qc2 was stronger. 33.Qc2 stops 33...Qe2: it covers e2." |
| V6 | **Facts only.** Every condition reads shipped facts (`move`, `squares`, `draw`, material flow) and S. No new fact family, no extra search, no comparison between two searches (R2-D §4). |
| V7 | **"Repeating the position" only when a node of the window repeats** (`draw.occurrences ≥ 2`); otherwise the claim says checks and a draw score, never "perpetual". |
| V8 | **Versioned.** New templates, new finding types and phrases change the build digest; stored claim graphs are re-analysed (R4-D §2.1). |

## 2. Draws by checks

### 2.1 The checking draw of a line

For a line `L` of S over its window `N_0 … N_k`, from the mover `m` at P, and a side `c`:
- `plies(c)` = `c`'s plies in the window: odd plies for `m`, even plies for `o`.
- The **run** of `c` = the longest suffix of `plies(c)` in which every ply gives check
  (`MoveFacts.gives_check`). Its first ply is `q`.
- `L` is a **checking draw by `c`** when:
  1. the run has at least `CHECK_RUN` (2) plies;
  2. `L`'s `EngineLineFact.score` is a `Cp` with `|value| ≤ DRAW_CP` (10); a `Mate` is never a
     draw;
  3. `L`'s WDL, when available, has `draw ≥ DRAW_WDL` (900‰); when the WDL is `Unavailable`,
     condition 2 alone decides;
  4. no ply of the run gives mate, and the window does not end in checkmate.
- **Repeated** when a node `N_i`, `i ≥ q − 1`, has `draw.occurrences ≥ 2` (the game's history
  counts, as the `draw` family counts it).

Why these values (§0.2): a score of exactly 0.00 marks both lines of the owner's games; 10 cp
admits an engine's near-zero rounding but no advantage. The WDL condition excludes a sharp line
that scores 0.00 by balance. The run of 2 is the smallest that is "check after check"; both
lines of §0.2 reach it inside their windows.

**Finding:** `ChecksDrawFinding(checker: Color, line: LineSegment, first: MoveRef, checks: int,
repeated: bool)`; `line` is `LineSegment(L, q − 1, k)`, the plies the sentence shows.

**Evidence:** `SearchRef(S, L.rank)` (score and WDL), `FactRef("move", N_i, ("gives_check",))`
for each ply of the run, and `FactRef("draw", N_i, ("occurrences",))` for a repeated node.

### 2.2 `checks_draw_v1` — CONSEQUENCE, backward

- **Proposed when:** the judgement is decided, its grade is INACCURACY or worse, and `Lp` is
  attached.
- **Target, context, operands:** as `material_loss_v1` (`LineContext(Lp)`, operands `(Lp.window,
  L1.window)`).
- **Verify:** rules 1–2 of R2-D §3.1 do **not** apply (a drawn window is this claim's subject,
  and a mate score is condition 2's business). `SUPPORTED` when `Lp` is a checking draw by
  either side and `L1` is not a checking draw by the same side; `REFUTED` otherwise;
  `INCONCLUSIVE(NOT_COMPUTED)` when a needed `move` or `draw` record is missing.
- **Phrases** (`checker = o` / `checker = m`; `.repeated` when repeated):
  - `sentence.opponent` = "Along the engine line, {side} then gives check after check, {line},
    and the engine scores it as a draw."
  - `sentence.opponent.repeated` = "Along the engine line, {side} then gives check after check,
    {line}, repeating the position: the engine scores it as a draw."
  - `sentence.mover` = "It settles for checks, {line}, which the engine scores as a draw."
  - `sentence.mover.repeated` = "It settles for checks, {line}, repeating the position: the
    engine scores it as a draw."
  - `{side}` is "White" or "Black"; `{line}` the finding's segment, formatted as R3-D's lines
    (at most six plies, "..." when cut).

### 2.3 `checks_draw_missed_v1` — COMPARISON, backward

- **Proposed when:** the judgement is decided, its grade is INACCURACY or worse, the played move
  is not rank 1, and `L1` is attached.
- **Target:** `line_target` of `L1`, as `better_move_v1`.
- **Verify:** `SUPPORTED` when `L1` is a checking draw by `m` and `Lp` is not a checking draw;
  `REFUTED` otherwise; `INCONCLUSIVE(NOT_COMPUTED)` on a missing record. (The loss already shows
  that the draw is better for `m` than `Lp`.)
- **Phrases:** `sentence` = "Instead, {best} was needed: it starts a series of checks, {line},
  which the engine scores as a draw." and `sentence.repeated` = "Instead, {best} was needed: it
  starts a series of checks, {line}, repeating the position, which the engine scores as a
  draw."

## 3. `best_stops_reply_v1` — COMPARISON detail, backward

- **Proposed when:** the judgement is decided, its grade is INACCURACY or worse, the played move
  is not rank 1, and both `Lp` and `L1` are attached with `Lp` reaching ply 2.
- **Notation:** `b` = the best move (`L1` ply 1, node `B1 = N_1(L1)`), `r` = `Lp`'s ply 2 (the
  reply, node `R = N_2(Lp)`), `s` = `r`'s destination square, `X` = the piece that plays `r`,
  `A1 = N_1(Lp)` (after the played move).
- **Kinds, tried in this order; the first that holds is the finding:**
  1. **RESCUES:** `r` captures a piece `V` of `m` that stands on `s` at `P`; `b` moves `V` (its from-square is
     `s`); `V` is not captured in `L1`'s window; `Lp`'s outcome is `STABLE(Δp ≤ −1)` and the
     balance after ply 2 is below the balance after ply 1.
  2. **DEFENDS:** `r` captures a piece `V` of `m` that stands on `s` at `P`; `b` does not move `V`; after `b`, the
     square `s` holds `V` and `b`'s piece is among `m`'s attackers of `s` (`squares` at `B1`);
     `Lp`'s outcome is `STABLE(Δp ≤ −1)` with the balance falling at ply 2; `L1`'s outcome is
     `STABLE(Δ1)` with `Δ1 > Δp`.
  3. **COVERS:** `s` is empty at `P` and at `A1`; `m` has no attacker of `s` at `A1`; after `b`,
     `b`'s piece attacks `s`; `X` gives check or captures at a later ply of `Lp`'s window; in
     `L1`, ply 2 does not move to `s`.
  Otherwise `REFUTED`. `INCONCLUSIVE(NOT_COMPUTED)` when a needed record is missing.
- **Why these conditions** (§0.3): RESCUES and DEFENDS name a capture that costs material in
  `Lp`; COVERS names a square whose occupant then acts. The three excluded patterns of §0.3
  (a reply that does nothing later; a square already covered; the played move's own exchange,
  where `s` is the played move's destination, so `V` was not on `s` at `P` and `s` is not empty
  at `A1`) fail them.
- **Finding:** `ReplyFinding(kind, best: SearchMoveRef, reply: MoveRef, square: SquareRef,
  piece: PieceRef | None)` (`piece` = `V` for RESCUES and DEFENDS, at `P`).
- **Evidence:** `SearchRef(S, 1)`, `SearchRef(S, p)`, `FactRef("move", R, ("events", i))` of the
  capture (RESCUES, DEFENDS) or `FactRef("move", R, ())` (COVERS), `FactRef("squares", B1,
  (s,))`, and for COVERS the later check or capture's `FactRef("move", …)`.
- **Phrases** (`sentence.<kind>`):
  - rescues: "{best} saves {piece} from {reply}."
  - defends: "{best} defends {piece} against {reply}."
  - covers: "{best} stops {reply}: it covers {square}."
  Examples: "49.Ng5+ saves the knight on e6 from 49...Kxe6." "14...Be6 defends the pawn on d5
  against 15.cxd5." "33.Qc2 stops 33...Qe2: it covers e2."

## 4. Code changes (the contract of EV1)

| Place | Change |
| --- | --- |
| `reasoning/lines.py` | `checking_draw(view, line, side) -> ChecksDrawFinding \| None` and its constants `CHECK_RUN`, `DRAW_CP`, `DRAW_WDL` (§2.1) |
| `reasoning/findings.py` | `ChecksDrawFinding`, `ReplyKind`, `ReplyFinding`; both in `KINDS` (the type registry: the build digest changes) |
| `reasoning/catalogue/draws.py` (new) | `ChecksDraw` (`checks_draw_v1`), `ChecksDrawMissed` (`checks_draw_missed_v1`) |
| `reasoning/catalogue/comparison.py` | `BestStopsReply` (`best_stops_reply_v1`) |
| `reasoning/catalogue/__init__.py` | `CATALOGUE_V1` gains the three, after `material_gain_v2` (`checks_draw_v1`) and after `better_move_v1` (`checks_draw_missed_v1`, `best_stops_reply_v1`) |
| `reasoning/planner.py` | rule 3: a consequence table `DRAWS = ("checks_draw_v1",)` tried after `MATERIAL`; rule 6: `COMPARISONS = ("mate_missed_v1", "better_move_v1", "checks_draw_missed_v1", "missed_gain_v1", "better_alternative_v1")`, `WITH_LINE` unchanged; new rule 6b: `DETAILS = ("best_stops_reply_v1",)`, its first SUPPORTED claim for the subject is added to the justification after the comparison, when a comparison was chosen and it is not `mate_missed_v1` or `checks_draw_missed_v1` (those already say why) |
| `reasoning/labels.py` | unchanged: MISS keeps `missed_gain_v1`; when MISS is the label, its ground sentence is kept and the detail follows it |
| `reasoning/render/__init__.py` | `fmt_square(h, ref: SquareRef)` with `TraceRef("square", node, square=…)`; `fmt_side`; `bind` branches for the three templates; the detail sentence placed after the comparison (and after the MISS sentence) |
| `reasoning/render/phrases/en.toml` | `[checks_draw_v1]`, `[checks_draw_missed_v1]`, `[best_stops_reply_v1]` (§2–§3); `[claim]` names "draw by checks", "missed draw by checks", "answer to the reply" |
| `results/document.py` | the `square` ref kind (the schema and the viewer already accept it; R3-D had no slot that named a bare square) |
| `docs/design` | R2-D and R3-D record the amendments |

## 5. What changes in the two games (expected, from §0; EV1 re-runs both)

| Move | Added |
| --- | --- |
| 33.b6 | "Along the engine line, Black then gives check after check, 35...Qxe1+ 36.Kg2 Qe2+ 37.Kg1, and the engine scores it as a draw." and, after the MISS sentence, "33.Qc2 stops 33...Qe2: it covers e2." |
| 38...f5 | "Instead, 38...Qe2+ was needed: it starts a series of checks, 38...Qe2+ 39.Kg1 Qe1+ 40.Kg2 Qe2+, repeating the position, which the engine scores as a draw." (replaces "Instead, 38...Qe2+ was stronger.") |
| 14...O-O | after "Instead, 14...Be6 was better: 14...Be6 15.cxd5 Bxd5 …": "14...Be6 defends the pawn on d5 against 15.cxd5." |
| 49.Bxa3, 50.Bc5, 51.a4 | "49.Ng5+ saves the knight on e6 from 49...Kxe6.", "50.Nc5 saves the knight on e6 from 50...Kxe6.", "51.Nc7 saves the knight on e6 from 51...Kxe6." |
| every other ply | unchanged |

## 6. Test obligations (packet EV1)

1. **The checking draw** (scripted lines): runs of 1, 2 and 3 checks; a run broken by a quiet
   ply of the checker; a score of 0, ±10, ±11; WDL draw 899 / 900 / unavailable; a mate score;
   a run ending in mate; repetition counted from the game's history and from within the window;
   a Black checker.
2. **`checks_draw_v1`:** the opponent's checks after an inaccuracy (SUPPORTED); the mover's own
   checks; the same checks in `L1` too (REFUTED); a good move (not proposed); a missing `draw`
   record (INCONCLUSIVE).
3. **`checks_draw_missed_v1`:** the 38...f5 shape (SUPPORTED, chosen over `missed_gain_v1`, one
   "Instead"); `Lp` also a checking draw (REFUTED); the best line drawn without checks (REFUTED).
4. **`best_stops_reply_v1`:** each kind SUPPORTED on a scripted position; each exclusion of §0.3
   REFUTED (a reply that does nothing later, a square already covered, the played move's own
   exchange); the kind order (a capture that RESCUES is not reported as DEFENDS); the planner adds
   the detail after `better_move_v1`, `missed_gain_v1` and `better_alternative_v1` and after the
   MISS sentence, and not after `mate_missed_v1` or `checks_draw_missed_v1`.
5. **Through the renderer** (EA-D's lesson): each new template in a corpus case through
   `explain`, `trace` = `render`, save/load, the result document (`schema_errors` empty; a
   `square` ref with its FEN) and the viewer test; the coverage test of EA1 reaches the three.
6. **The owner's two games** re-run: the changes are those of §5, and the record lists every
   changed sentence; the scan of §0 is re-run with the shipped code and its counts recorded.
7. **Build identity:** the digest changes; an EA1 graph is refused by `load`.

## 7. Delivery

| Packet | Content | Gate |
| --- | --- | --- |
| EV-D (this) | the rules and their evidence | independent review READY |
| EV1 | the three templates, the finding types, planner rule 6b, the renderer and phrasebook, tests, the two games re-run | READY |

## 8. Not in this packet

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
