# Reasoning — R2-D design: observations v1 and hypothesis templates v1

Status: **rev. 11 — rev. 10 merged (#56); fifth independent review (NOT_READY for implementation:
B1–B3, C1) applied (§11.9)**.
Date: 2026-10-10. Base: [`reasoning-r0-design.md`](reasoning-r0-design.md) rev. 8 (R0-D).

R0-D fixes the contracts and names the template catalogue v1 (R0-D §8.5). This packet gives the
exact definition of every observation and template of v1: the hypothesis fields, how it
verifies, which statuses it can reach and why, the typed findings, evidence and scope it
records, its causal check, and the relations it creates.

## 0. Decisions

| # | Decision |
| --- | --- |
| E1 | **No comparator contrast for mechanisms.** A mechanism explains a consequence *on its own line*; the comparison with the best line is `better_move_v1`, and the material loss itself is contrasted with the best line (§3.1). The renderer never says "allows a fork the best move avoids". |
| E2 | **Typed findings** in a fixed order per template (§1.7). No chess strings: moves are `MoveRef` / `SearchRef` (R0-D §4). |
| E3 | **Material is counted, as balance** (R0-D §6.5), along one line; no engine number enters it. |
| E4 | **Claims about the target move are measured from P** (`b_0 = 0`). Material that changed hands before P is not this move's result (re-review B1). |
| E5 | **The baseline B is a veto, not a starting point.** Where an exchange was running into P, a gain or a give-up must also hold when measured from B (§1.4), so a recapture is not a gain and an earlier offer is not re-credited. |
| E6 | **The material window widens until stable,** from `pv_plies` up to `2 · pv_plies` plies (R0-D §6.4). Material reads only tier records, so widening costs no request. |
| E7 | **Mechanisms are tied to the capture.** A configuration must appear on the line by a move of the beneficiary (or be walked into by the loser's move), and it EXPLAINS only if its `REALIZED` check passes: the decisive capture is made through it and the piece was not already losable (R0-D D12, D15). |
| E8 | **v1 explains at most "realized through".** No template of v1 runs a counterfactual check, so none claims `CAUSES`; the renderer says "through the fork", never "because of the fork, decisively" (review 3 B5). The counterfactual "would the same punishment work after the best move?" (legacy P8 comparator replay) is the first template of the next catalogue. |
| E9 | **Hanging pieces are mechanisms too** (owner's legacy comparison). A piece that the played move put en prise, or left en prise, explains a loss as well as a fork does (legacy `NEWLY_HANGING_PIECE`), and is the most common blunder. |

## 1. Notation and shared definitions

### 1.1 Positions, sides and lines
- Subject `(P, C)`; the **mover** `m` = P's side to move; the **opponent** `o`.
- `S` = the judgement's pinned search; `Lk` = its rank-k line; `Lp` = the played move's line, of
  rank `p`; if `p = 1`, `Lp = L1`.
- An attached engine line `EngineLineId(A, s, k)` has `LineRecord.nodes = (A, n1, …, nr)`: the
  anchor, then one node per attached ply (`engine_work._attach_line`). A line cut before its
  first ply (deadline or `max_nodes`) has `nodes = (A,)` and `end = BUDGET_LIMIT`.
- **Standard lines** (R0-D §7.3): `Lp` and `L1`, anchored at P. `N_i` = the i-th node of the
  line under discussion (`N_0` = the anchor).
- **Identity** is by `PieceId` throughout: `FrameNode.pieces` maps squares to ids at a node;
  `move` captures, `delta` and `pattern_delta` carry ids.
- **Squares versus pieces** (review 3 B4). POSITION records are keyed by square: `pieces` holds
  one `PieceFacts` per occupied square, and its attack sets (`attacks.enemy`, `attackers`,
  `defenders`) hold squares. `sq(x, N)` = `N.square_of(x)`. Every test of a piece `x` against a
  POSITION record at `N` reads it at `sq(x, N)`: `pieces(x, N)` is the entry at that square, and
  "`x` is attacked by `y` at `N`" means `sq(x, N) ∈ pieces(y, N).attacks.enemy`. If `sq(x, N)` is
  `None` (`x` is not on the board at `N`), the test is false.
- **References versus ids** (integrated N1). `v`, `w`, `a` and similar names are `PieceRef`s;
  comparisons with record fields that hold ids use `v.piece` (`move.piece = v.piece`,
  `defended = v.piece`, `v.piece ∈ after`, `pinned = v.piece`, `front = v.piece`). `patterns`
  entries hold `Relation`s by square, without id or colour: a relation `rel` at `N` names the
  piece `N.piece_at(rel.square)`, whose colour is read from `pieces` at that square;
  `MultiTargetAttack` target orders are `Target.order` of the entry at `N`.
- **Moves of a search** (review 4): the k-th move of line `Lj` of S is `SearchMoveRef(S, j, k)`,
  available from the search record whether or not the line is attached; a `MoveRef` is used only
  for an attached edge. `outcome` is read from the score when it is a mate, so a line with no
  attached ply can still have a decided outcome, and every finding about such a line cites
  `SearchMoveRef`s.
- A piece **moved** on the edge `N → N'` when `sq(x, N) ≠ sq(x, N')` (this includes the castling
  rook, whose move record names the king; integrated N2).

### 1.2 Balance from P (E4)
`material_flow` (R0-D §6.5) over `line(L, k)` — the path `N_0 … N_k` — gives one `PlyMaterial`
per ply. `b_i` is the mover's balance after ply `i`, measured **from P**: `b_0 = 0`. A ply that
captures and promotes is one ply.

### 1.3 Window and outcome
For a line `L` with `r` attached plies (continued lines included, R0-D §7.3):
1. `k = min(pv_plies, r)`; flow `F` over `line(L, k)`.
2. While `F.stable` is `Unstable(CAPTURE_AT_END | TOO_SHORT)` and `k < min(r, 2 · pv_plies)`:
   `k += 1`, recompute.
3. The window `W(L)` = plies `1 … k`.

`outcome(L)`, first matching:
- `MATE(winner, n)` when `L.score` is a mate (the score decides, whatever the window shows);
- `MISSING(LINE_TOO_SHORT)` when `r = 0` — a cut before the first ply, by the deadline or
  `max_nodes` (re-review N1, re-check N1); `MISSING(NOT_COMPUTED(<family>))` when a record is
  missing;
- `MATE(winner, ⌈k/2⌉)` when the window ends in checkmate (not reachable for a regular search,
  kept total; re-review N2);
- `DRAWN` for `Unstable(DRAWN_END)`;
- `STABLE(Δ)` for `Stable`, `Δ = b_k`;
- `OPEN` otherwise.

**Order** for the mover, best first: `MATE(m, n)` (smaller `n` first) > `STABLE(Δ)` (larger Δ
first) > `MATE(o, n)` (larger `n` first). `DRAWN` ranks below every `MATE(m, ·)` and above
every `MATE(o, ·)` and is incomparable with `STABLE`. `OPEN` and `MISSING` are undecided.

### 1.4 Baseline veto (E5)
Walk back from P along the input line: while the ply into the current node is a capture or a
check and fewer than 4 plies have been passed, step to its parent; the node reached is `B`. If
`B = P`, there is no veto. Otherwise `bB_i` = the mover's balance after ply `i` of the line
measured from `B` (the path `B … P, N_1 … N_i`). Used only as a veto in §3.2 and §3.11.

The 4-ply cap bounds the walk; in a longer trade the veto starts mid-exchange and is weaker
(re-review N8, tested). Examples (checked with python-chess):
- target …dxc6 after 4.Bxc6: from P the recapture is +3, from B it is 0 — no gain.
- 1.d4 e5 2.dxe5 Bb4+, target White's 3rd move, `Lp` = 3.Bd2 Bxd2+ 4.Qxd2: from P Δ = 0 — no gain
  (rev. 2 measured +1 from B and called it a gain).

### 1.5 Decisive event
For `STABLE(Δ)` with `Δ ≤ −1`, the **decisive loss** is the first ply `q ≥ 1` with `b_q ≤ Δ` and
`b_i < 0` for every `i ≥ q` in the window (relative to `b_0 = 0`). That ply is always a capture or
promotion by the opponent: it is where the balance first reaches its final level, not where it
first turns negative (re-check B1: in 1.h3 Nxc2+ 2.Kd2 Nxa1, the pawn capture turns the
balance negative, the rook capture decides it). If ply `q` captures, its victim is the **lost
piece** `v` (it stood on `N_{q−1}`) and the capturing piece is the **capturer** `w`.
Symmetrically for `Δ ≥ 1`: the first `q` with `b_q ≥ Δ` and `b_i > 0` for every `i ≥ q` (the
decisive gain, the won piece). A ply that only promotes has no victim; mechanisms are not proposed
on it.

### 1.6 Safety: `unsafe_v1` (integrated B1)
A piece `x` is **unsafe** at a node `N` (`unsafe_v1`) if its `pieces(x, N)` record has
`attackers_exceed_defenders` (outnumbered; `attacked_without_defender` implies it), **or** its
`lowest_attacker_types.value` (a `Defined` wrapper) contains a type that ranks below `x`'s type under `piece_order_v1` (a
lower piece attacks it, so even a defended piece loses value). It is **safe** otherwise.
Counting alone called the queen of `4k3/8/8/4p3/8/2P5/8/3QK3 w`, 1.Qd4, safe (one attacker, one
defender); with the second clause it is unsafe, as it is.

Without static exchange evaluation (out of v1) this is still an approximation of "not losable
there": it ignores pinned defenders, pinned attackers (an absolutely pinned attacker still
counts) and exchange sequences. Scopes that rely on it list the
policy `unsafe_v1`.

### 1.6a Exposure continuity (review 5 B2)
A lost piece `v` **stays exposed to `w`** from node `N_a` to `N_{q−1}` when, at every node `N_i`
with `a ≤ i ≤ q − 1` of the line (`N_0` = P), all hold:
- `v` stands on the same square: `sq(v, N_i) = sq(v, N_a)` (from `FrameNode.pieces`; a piece that
  left and came back fails);
- `v` is unsafe (`unsafe_v1`);
- `w` attacks `v`: `sq(v, N_i) ∈ pieces(w, N_i).attacks.enemy` (so `w` is on the board and its
  attack is continuous, not re-made later).

It reads `pieces` at each of those nodes. The check **fails** as soon as a present record (or the
always-present square map of `FrameNode.pieces`) fails it; it is **undecided** only when no
present record fails it and some record is missing — then the template returns
`NEEDS_EVIDENCE(FamilyNeed(N_i, "pieces"))` for the missing nodes (within the window cap) rather
than a verdict (re-check C3). Without continuity a mechanism is `ASSOCIATED_WITH`, never
`EXPLAINS`.

### 1.7 Finding records (E2)
Frozen dataclasses in the reasoning type registry (R0-D §14.1).

```text
Outcome(kind: MATE | STABLE | DRAWN | OPEN | MISSING, winner: Color | None, moves: int | None,
        delta: int | None, plies: int, line_end: LineEnd | None, reason: str | None)
DecisiveEvent(ply: int, node: NodeId, victim: PieceRef | None, capturer: PieceRef | None,
              promotion: PieceType | None)
MaterialFinding(amount: MaterialAmount, event: DecisiveEvent, played: Outcome, best: Outcome)
MateFinding(moves: int, mating_move: MoveRef | SearchMoveRef | None)
ComparisonFinding(best_move: SearchMoveRef, best: Outcome, played: Outcome)
MechanismFinding(kind: str, node: NodeId, move: MoveRef, actor: PieceRef,
                 targets: tuple[PieceRef, ...], walked_into: bool)
CausalCheck(kind: str, passed: bool, evidence: tuple[Evidence, ...])        # R0-D §10.2
DefenceFinding(defender: PieceRef, defended: PieceRef, reason: DefenceEndReason)
HangingFinding(kind: MOVED_INTO_ATTACK | LINE_OPENED | LEFT, piece: PieceRef,
               attackers: tuple[PieceRef, ...])
ForcingFinding(check: bool, replies: int)
AlternativeFinding(line: SearchRef, loss: int)                               # 1/2000 units
OfferFinding(amount: MaterialAmount, event: DecisiveEvent, keeping: tuple[SearchRef, ...])
CompensationFinding(kind: MATE | MATERIAL_RETURN | ENGINE, expected: int)
PreventsFinding(kind: MATE | MATERIAL | MIXED, alternatives: int, smallest_loss: int | None)
```

Every `FactRef` names the revision at which its record is visible (R0-D §4); the references
below omit it for brevity.

## 2. Observations v1

Computed at `V_0`, `version = "obs_v1"`. `obs_v1` has no incremental kinds: later rounds add no
observations in v1 (R0-D §6.3 allows them; integrated N4).
- `standard_lines`: `(LineSegment(Lp), LineSegment(L1))` over their windows, or `MISSING`.
- `line_material`: per standard line, the window, `outcome`, the plies with captures and
  promotions, the decisive event, and the baseline veto values. Evidence: `LineRef` of the
  window; `FactRef("move", node, ("events", i))` per event; `FactRef("material", key,
  ("points",))` at the ends.
- `played_edge`: on P → C, the `move` record and `pattern_delta.defences_ended_under_attack`.

The round-0 `ensure` (R0-D §6.1) covers every family on the nodes of `Lp` and `L1` within
`pv_plies`.

## 3. Templates

### 3.0 Hypothesis fields (re-review C6, re-check C2)

A scope's `at` is its target's `at` (R0-D §9.3), so line satisfaction is by construction.
Segments: `seg(L)` = `LineSegment(L.line_id, 0, r)` over all attached plies of line `L` (the
window is chosen at verification and recorded in the scope); `edge` = `LineSegment(played line
id, index of P, index of C)`. Populations: `REP` = `ENGINE_REPORTED(S)`, `RANK` =
`ENGINE_RANKED(S)`, `PLAYED` = `EXPLICIT((MoveRef(C),))`. Horizons are `None` unless stated: the
outcome is judged over the window, whose plies the scope records. `Context` equals
`LineContext(at)` for line targets and `NodeContext(at)` for node targets.

| Template | Role | Target: quantifier, `at`, population | Scope basis | Directions | Origins | Premises: `ScopeRequirement` |
| --- | --- | --- | --- | --- | --- | --- |
| `mate_delivered_v1` | CONSEQUENCE | `SPECIFIC_LINE`, `edge`, `PLAYED`, horizon 1 | `EXACT` | F | `played_edge` | — |
| `mate_found_v1` | CONSEQUENCE | `SPECIFIC_LINE`, `seg(Lp)`, `REP` | `ENGINE` | F | judgement | — |
| `mate_allowed_v1` | CONSEQUENCE | `SPECIFIC_LINE`, `seg(Lp)`, `REP` | `ENGINE` | B | judgement | — |
| `mate_in_one_allowed_v1` | CONSEQUENCE | `EXISTS_RESPONSE`, C, `LEGAL`, horizon 1 | `EXACT` | F, B | `played_edge` | — |
| `mate_missed_v1` | COMPARISON | `SPECIFIC_LINE`, `seg(L1)`, `REP` | `ENGINE` | B | judgement | — |
| `material_loss_v1` | CONSEQUENCE | `SPECIFIC_LINE`, `seg(Lp)`, `REP` | `ENGINE` | B | judgement, `line_material` | — |
| `material_gain_v1` | CONSEQUENCE | `SPECIFIC_LINE`, `seg(Lp)`, `REP` | `ENGINE` | F, B | judgement, `line_material` | — |
| `forcing_v1` | FUNCTION | `SPECIFIC_LINE`, `edge`, `PLAYED`, horizon 1 | `EXACT` | F | `played_edge` | — |
| `only_move_v1` | FUNCTION | `ALL_ALTERNATIVES`, P, `RANK` | `ENGINE` | F | judgement | — |
| `sacrifice_offer_v1` | FUNCTION | `EXISTS_ALTERNATIVE`, P, `REP` | `ENGINE` | F | judgement, `line_material` | — |
| `sacrifice_sound_v1` | FUNCTION | `SPECIFIC_LINE`, `seg(Lp)`, `REP` | `ENGINE` | F | judgement | offer: `(ENGINE, ((EXISTS_ALTERNATIVE, ENGINE_REPORTED),))`, `SAME_CONTEXT`, `SAME_SEARCH` |
| `sacrifice_compensated_v1` | FUNCTION | `SPECIFIC_LINE`, `seg(Lp)`, `REP` | `ENGINE` | F | judgement | offer: `(ENGINE, ((EXISTS_ALTERNATIVE, ENGINE_REPORTED),))`, `SAME_CONTEXT`, `SAME_SEARCH` |
| `prevents_v1` | FUNCTION | `ALL_ALTERNATIVES`, P, `REP` | `ENGINE` | F | judgement | — |
| `fork_v1`, `pin_v1`, `skewer_v1`, `discovery_v1` | MECHANISM | `SPECIFIC_LINE`, `seg(L)` of the premise, `REP` | `ENGINE` | F, B | `line_material` | consequence: `(ENGINE, ((SPECIFIC_LINE, ENGINE_REPORTED),))`, `SAME_CONTEXT`, `SAME_SEARCH` |
| `removed_defender_v1`, `newly_unsafe_v1` | MECHANISM | `SPECIFIC_LINE`, `seg(Lp)`, `REP` | `EXACT` (the change at P → C) | B | `played_edge` | loss: `(ENGINE, ((SPECIFIC_LINE, ENGINE_REPORTED),))`, `SAME_CONTEXT`, `SAME_SEARCH` |
| `left_en_prise_v1` | MECHANISM | `SPECIFIC_LINE`, `seg(Lp)`, `REP` | `ENGINE` (it reads `L1`) | B | `played_edge` | loss: `(ENGINE, ((SPECIFIC_LINE, ENGINE_REPORTED),))`, `SAME_CONTEXT`, `SAME_SEARCH` |
| `better_move_v1` | COMPARISON | `SPECIFIC_LINE`, `seg(L1)`, `REP` | `ENGINE` | B | judgement | consequence on `Lp`: `(ENGINE, ((SPECIFIC_LINE, ENGINE_REPORTED),))`, `ALTERNATIVE_OF`, `SAME_SEARCH` |

Every v1 premise is `SAME_SEARCH` (R0-D §8.1.2): all v1 claims read lines of the one search S,
and `better_move_v1` and the sacrifice templates compare outcomes with their premise's.

Alternatives exclude the played move (R0-D §8.2): for `only_move_v1` the best alternative is rank
2 because the played move is rank 1; for `prevents_v1` and `sacrifice_offer_v1` the other lines of
S are those with `k ≠ p`.

Common rules:
- The judgement must be `DECIDED`, except for the exact templates `mate_delivered_v1`,
  `mate_in_one_allowed_v1` and `forcing_v1`.
- The default scope is `basis = ENGINE`, the target's quantifier and population,
  `searches = (S, rank)`, depth and MultiPV of S, `plies = k`, the line's end,
  `policies = ("points_v1", "quality_v1")`. An effective scope is a set (R0-D §9.4).
- Status rules are evaluated in order; the first that applies decides.

### 3.1 `material_loss_v1`
- **Proposed when:** grade ≥ INACCURACY.
- **Verify** (measured from P; contrasted with `L1` of the same search):
  1. `outcome(Lp)` is `MATE(·)` → `INCONCLUSIVE(MATE_LINE)`.
  2. `MISSING(reason)` → `INCONCLUSIVE(reason)`; `OPEN` → `INCONCLUSIVE(LINE_TOO_SHORT)`;
     `DRAWN` → `INCONCLUSIVE(UNSTABLE)`.
  3. `STABLE(Δp)`, `Δp ≥ 0` → `REFUTED`.
  4. `outcome(L1)` undecided, or `DRAWN` (incomparable with `STABLE`; re-review C1) →
     `INCONCLUSIVE` with its reason (`UNSTABLE` for `DRAWN`).
  5. `outcome(L1)` ranks above `STABLE(Δp)` → `SUPPORTED`.
  6. Otherwise → `REFUTED` (the best line loses at least as much).
- **Findings:** `MaterialFinding(amount, event, played, best)`; `amount = −Δp` if `L1` mates for
  `m`, else `min(−Δp, Δ1 − Δp)`.
- **Evidence:** `SearchRef(S, p)`, `SearchRef(S, 1)`, both window `LineRef`s, the event `FactRef`.
  When `L1` was cut before its first ply, its `LineRef` has zero plies and is not shown; the
  justification then cites `SearchMoveRef(S, 1, 1)` (re-check C5).

A pending recapture into P is shared by `L1`, so it is not this move's loss (rule 6).

### 3.2 `material_gain_v1`
- **Proposed when:** the window of `Lp` contains a capture or a promotion by `m` (a promotion
  without capture raises the balance too; review 5 C1). A decisive gain that is a promotion has
  no victim (§1.5); its finding names the promotion.
- **Verify:** rules 1–2 of §3.1; then with `ΔB` = the balance from `B` at the window's end (or
  `Δp` when `B = P`):
  - `STABLE(Δp)` with `min(Δp, ΔB) ≥ 1` → `SUPPORTED`;
  - `STABLE(Δp)` otherwise → `REFUTED`.
- **Findings:** `MaterialFinding(MaterialAmount(min(Δp, ΔB)), event, played, best = outcome(L1))`.

### 3.3 `mate_allowed_v1`
- **Proposed when:** `outcome(Lp) = MATE(o, n)` and `outcome(L1)` is not `MATE(o, ·)`.
- **Verify:** `SUPPORTED`. **Findings:** `MateFinding(n, MoveRef of the mating edge if Lp ends
  in CHECKMATE within its attached plies, else None)`. **Evidence:** `SearchRef(S, p)`, `SearchRef(S, 1)`.
- It takes no premise. The planner relates it to `mate_in_one_allowed_v1` when both are
  SUPPORTED (§5.3 ranks the exact claim first); a premise would need a relation from a node on
  the line to the line, which R0-D does not define, and would duplicate the claim (focused
  re-check 2, 3).

### 3.3a `mate_in_one_allowed_v1` — CONSEQUENCE, forward and backward, exact
- **Target:** `EXISTS_RESPONSE` at C over `LEGAL`, horizon 1; context `NodeContext(C)`.
  **Operands:** `(MoveRef(C))`.
- **Proposed when:** `status(C).mating_moves` is not empty. No judgement is needed (exact; legacy
  P8 `EXACT_IMMEDIATE`, P10 §25.1).
- **Verify:** `SUPPORTED`, witness = the first mating move in `status` order.
- **Findings:** `MateFinding(1, None)`; the witness (the mating move, canonical UCI from the
  record) is in `ProofScope.witnesses` (R0-D §9.3), where move text is allowed.
- **Evidence:** `FactRef("status", key(C), ("mating_moves",))`. **Scope:** `EXACT`.

### 3.4 `mate_delivered_v1`
- **Proposed when:** `move.gives_mate` on P → C.
- **Verify:** `SUPPORTED`. **Findings:** `MateFinding(1, MoveRef(C))`.
- **Evidence:** `FactRef("move", C, ("gives_mate",))`. **Scope:** `EXACT`.

### 3.5 `mate_found_v1`
- **Proposed when:** `outcome(Lp) = MATE(m, n)` and the move does not give mate.
- **Verify:** `SUPPORTED`. **Findings:** `MateFinding(n, MoveRef of the mating edge if Lp ends
  in CHECKMATE within its attached plies, else None)` (as §3.3).

### 3.6 `mate_missed_v1`
- **Proposed when:** `outcome(L1) = MATE(m, n)` and `outcome(Lp)` is not `MATE(m, ·)`.
- **Verify:** `SUPPORTED`. **Findings:** `ComparisonFinding(SearchMoveRef(S, 1, 1),
  outcome(L1), outcome(Lp))` — the best move cited from the search, so a line cut before its
  first ply (deadline or `max_nodes`) still has its move (review 4 blocker).
  **Evidence:** `SearchRef(S, 1)`, `SearchRef(S, p)`, `FactRef("status", key(P), ("legal_moves",))`
  (the SAN of the cited move; re-check C1). A missed mate that still wins is graded EXCELLENT by `quality_v1`
  and explained by this claim.

### 3.7 Mechanisms: `fork_v1`, `pin_v1`, `skewer_v1`, `discovery_v1`
- **Premise:** one `SUPPORTED` consequence `X` ∈ {`material_loss_v1`, `material_gain_v1`} whose
  decisive event at ply `q` of line `L` has a victim `v` and a capturer `w`; the
  **beneficiary** `s` = `o` for a loss, `m` for a gain.
- **Operands:** `(X.id)`.
- **Appearance** (re-review N4): a configuration **appears at `N_i`** when the record of the edge
  `N_{i−1} → N_i` reports it as begun:

| Template | Begun on the edge into `N_i` (identity by `PieceId`) |
| --- | --- |
| `fork_v1` | `pattern_delta.multi_target_attacks` has a `TargetSetChange` for an actor `a` of `s` with `v ∈ after`, `len(after) ≥ 2`, and `v ∉ before` or `len(before) < 2` |
| `pin_v1` | `delta.pins.began` has a `PinRelation` with `pinned = v` and pinner of `s`, or `pattern_delta.relative_pins.began` has a `LineTriple` with `front = v` and slider of `s` |
| `skewer_v1` | `pattern_delta.skewers.began` has a `LineTriple` with slider of `s` and `back = v` |

- **Who made it appear** (E7, re-review C4): either `N_i.mover = s` (the beneficiary set it up),
  or — for a loss only — `i = 1` (the played move walked into it; `walked_into = true`).
- **Range:** `i = 1 … q − 1`. A `TargetSetChange` whose `after` is `Absent` (the actor was
  captured) is no fork.
- **Records read** (re-check N2): the edge records (`delta`, `pattern_delta`) at every `N_i` of the
  range; `pieces` at every `N_{i−1}` (safety); `pieces` / `patterns` at `N_{q−1}` (pin hold).
- **Candidates:** every appearance with an allowed mover, ordered by node, then record order.
  A candidate **qualifies** when its causal check (below) passes. A candidate whose check reads a
  missing record (for `pin_v1` at `N_{q−1}`, for `discovery_v1` at `N_{i+1}`) is **undecided**
  until that record is present (rev. 4 re-check N1).
- **Verify** (re-check C1):
  1. Scan `i` upward. At the first node where a record read for that node is missing, or at the
     first undecided candidate, stop: if no qualifying candidate was found before it, return
     `NEEDS_EVIDENCE(FamilyNeed(node, family))` for every missing record the scan and the checks
     read (within the window cap).
  2. The first **qualifying** candidate found (all records below and at its node present) →
     `SUPPORTED` with `EXPLAINS → X`.
  3. All records present, no qualifying candidate, some candidate → `SUPPORTED` with the earliest
     candidate and `ASSOCIATED_WITH → X`.
  4. All records present and no candidate → `REFUTED`.

  An unrelated earlier configuration therefore never hides the one the capture went through.
  Example (checked in the fact engine, rev. 4 re-check C1): `4kb2/8/8/6n1/1P1N4/8/P7/4K3 w`,
  1.a3 Bc5 2.b5 Be7 3.b6 Nf3+ 4.Ke2 Nxd4+ — the bishop's double attack begun at `N_2` does not
  qualify (the bishop does not capture); the knight fork begun at `N_6` does (`Nd4` safe at
  `N_5`, the knight captures). In the shorter line 1.a3 Bc5 2.b5 Nf3+ 3.Ke2 Nxd4, `Nd4` is already
  attacked and undefended at `N_3`, so no candidate qualifies and the result is `SUPPORTED`
  with `ASSOCIATED_WITH`.
- **Causal check** — kind `REALIZED` (re-review C2; it decides qualification above), all of:
  - `v` is safe at `N_{i−1}` (it was not losable before the configuration; `unsafe_v1` is listed
    in the scope's policies);
  - the decisive capture is made through the configuration:

| Template | Through the configuration |
| --- | --- |
| `fork_v1` | the capturer `w` is the actor `a`, and another target of `after` is the king of the other side, ranks `ABOVE` / `EQUAL` `a`, or is unsafe at `N_i` (a real second threat) |
| `pin_v1` | the pin still holds at `N_{q−1}` (`pieces(v, N_{q−1}).absolutely_pinned`, or the relative pin with `front` at `sq(v, N_{q−1})` present in `patterns`) |
| `skewer_v1` | the capturer `w` is the skewer's slider |

- **Findings:** `MechanismFinding(kind, N_i, MoveRef(N_i), actor, targets, walked_into)`,
  `CausalCheck`. **Evidence:** the edge record `FactRef`s at `N_i`, the `pieces` flags of `v` at
  `N_{i−1}`, `X`'s evidence.

**`discovery_v1`** (re-review C3) is read around the uncovering move, not by appearance:
- At `N_i` with `s` **to move** (`i ≥ 0`; `i = 0` only when `s = m`), up to `i = q − 2`,
  `patterns.discovery_lines` has an entry with slider and blocker (`front`) of `s`, and the move
  `N_i → N_{i+1}` (by `s`) moves the blocker; and either:
  - (a) `sq(v, N_{i+1}) ∈ pieces(slider, N_{i+1}).attacks.enemy` and
    `sq(v, N_i) ∉ pieces(slider, N_i).attacks.enemy` (review 3 B4: squares, not pieces); or
  - (b) `move.gives_check` on `N_i → N_{i+1}` along that line (the `back` is the king of the other
    side) and `sq(v, N_{i+1}) ∈ pieces(blocker, N_{i+1}).attacks.enemy`.
- The same records, candidates and verify rules as above, over `i`; it also reads `pieces` at
  `N_i` and `N_{i+1}`.
- **Causal check** (`REALIZED`): `v` is safe at `N_i`, and the capturer `w` is the slider
  (a) or the blocker (b).
- Example (b): `4k3/8/8/3q4/8/8/4N3/4RK2 w`, 1.Nc3+ Kd7 2.Nxd5.

### 3.8 `removed_defender_v1`
- **Premise:** a `SUPPORTED` `material_loss_v1` `X` with lost piece `v`.
- **Operands:** `(X.id)`.
- **Verify:**
  1. `played_edge` has a `DefenceEnded(defender = d, defended = v, reason)` with `reason ∈
     {DEFENDER_MOVED, LINE_BLOCKED}` → `SUPPORTED`; the first such entry in record order.
  2. Otherwise → `REFUTED` (`DEFENDED_MOVED`: `v` itself moved; `DEFENDER_CAPTURED` cannot be the
     mover's own defender on the mover's move).
- **Causal check** (`REALIZED`): `v` is safe at P, and `v` stays exposed to the capturer `w`
  from C to `N_{q−1}` (§1.6a). Passed → `EXPLAINS → X`; else `ASSOCIATED_WITH → X`; undecided →
  `NEEDS_EVIDENCE` (§1.6a). (Rev. 5 used `CAUSES`; a count change is not a counterfactual,
  review 3 B5.)
- **Findings:** `DefenceFinding(d, v, reason)`, `CausalCheck`.
- **Evidence:** `FactRef("pattern_delta", C, ("defences_ended_under_attack", i))`, the `pieces`
  records of `v` at P and at every node from C to `N_{q−1}`. **Scope:** `EXACT` for the defence change; the effective scope adds
  `X`'s.

### 3.8a `newly_unsafe_v1` — MECHANISM, backward (E9)
- **Premise:** a `SUPPORTED` `material_loss_v1` `X` on `Lp` with lost piece `v` and capturer `w`;
  relation `SAME_CONTEXT`.
- **Proposed when** (a domain guard, not a verdict; integrated B1): `v` moved on P → C, or `v` is
  safe at P. A piece already unsafe at P that stayed is `left_en_prise_v1`'s domain.
- **Operands:** `(X.id)`.
- **Verify** (records: `pieces` at P and at every node from C to `N_{q−1}`, the edge records of
  P → C):
  1. `v` is safe at C → `REFUTED` (the move did not leave it unsafe).
  2. `v` moved → `SUPPORTED`, kind `MOVED_INTO_ATTACK` (whether or not it was attacked before).
  3. `delta.piece_attacks.began` on P → C has a pair (attacker of `o`, `v.piece`) — the attacker
     did not move, so the played move opened its line → `SUPPORTED`, kind `LINE_OPENED`.
  4. Otherwise → `REFUTED` (the change is a defence that ended: `removed_defender_v1`'s claim).
- **Causal check** (`REALIZED`; integrated N2, N3, review 5 B2): `v` stays exposed to `w` from C
  to `N_{q−1}` (§1.6a) — the capture is the one the move exposed, not a later one after `v` left
  and came back.
- **Findings:** `HangingFinding(kind, v, attackers at C)`, `CausalCheck`.
- **Evidence:** `pieces` of `v` at P and at every node from C to `N_{q−1}`; the move record; the
  `piece_attacks` entry.
- Example (checked in the fact engine): `4k3/8/8/4p3/8/2P5/8/3QK3 w`, 1.Qd4 exd4 2.cxd4 —
  `MOVED_INTO_ATTACK`, `EXPLAINS`.

### 3.8b `left_en_prise_v1` — MECHANISM, backward (E9)
- **Premise:** as §3.8a.
- **Proposed when** (domain guard): `v` did not move on P → C and `v` is unsafe at P.
- **Operands:** `(X.id)`.
- **Verify:**
  1. `v` is safe at C → `REFUTED` (the played move did defend it; integrated B1).
  2. `v` is the victim of `L1`'s decisive loss event (§1.5) → `REFUTED` (the best line loses it
     too). A best line that only trades `v` (no decisive loss of it) counts as keeping it
     (integrated C2).
  3. Otherwise → `SUPPORTED`. (`L1` is decided here: the premise `material_loss_v1` is SUPPORTED
     only with a decided, comparable `L1`.)
- **Causal check** (`REALIZED`; review 5 B2): `v` stays exposed to `w` from P to `N_{q−1}`
  (§1.6a) — the threat was there, was not answered, and was the one carried out.
- **Findings:** `HangingFinding(LEFT, v, attackers at P)`, `CausalCheck`.
- **Evidence:** `SearchRef(S, 1)`; the `L1` event `FactRef` when `L1` has a decisive loss; the
  `pieces` records of `v` at every node from P to `N_{q−1}`. **Scope:** `ENGINE`, `searches = (S, 1)`,
  policies include `unsafe_v1`.
- This is the "ignored threat" that needs no `opponent_view`: the threat is a fact at P, the
  omission is the played move, the contrast is `L1`.
- Example (checked in the fact engine): `4k3/8/8/4p3/3Q4/2P5/8/4K3 w`, 1.Kf2 exd4 — the queen is
  defended by c3 but attacked by a pawn: unsafe at P and C, `SUPPORTED`, `EXPLAINS`.

### 3.9 `forcing_v1`
- **Proposed when:** `move.gives_check` on P → C, or `status(C).legal_move_count = 1`, and the
  move does not give mate.
- **Verify:** `SUPPORTED`. **Findings:** `ForcingFinding(check, replies)`.
- **Evidence:** `FactRef("move", C, ("gives_check",))`, `FactRef("status", key(C),
  ("legal_move_count",))`. **Scope:** `EXACT`.

### 3.10 `only_move_v1` (R0-D D10)
- **Proposed when:** grade = BEST and `status(P).legal_move_count ≥ 2`.
- **Verify:**
  1. `S.kind ≠ SURVEY` → `INCONCLUSIVE(SCOPE_SHORT)` (`ENGINE_RANKED` needs an unrestricted search).
  2. S has no rank-2 line → `INCONCLUSIVE(NOT_COMPUTED(NO_RANK_2))` (MultiPV 1 only).
  3. `E(L1) − E(L2) ≥ 400` → `SUPPORTED`.
  4. Otherwise → `REFUTED` (rank 2 is the counterexample).
- **Findings:** `AlternativeFinding(SearchRef(S, 2), E(L1) − E(L2))`.

### 3.11 Sacrifice

**`sacrifice_offer_v1`.**
- **Proposed when:** grade ∈ {BEST, EXCELLENT} and the window of `Lp` has a capture by `o` at ply
  2 or 4.
- **Candidates:** the plies `j ∈ {2, 4}` (the opponent's; re-review N6) at which `o` captures a
  piece of `m`; its victim is the **given-up piece** `v_j`.
- **A candidate qualifies** when `b_j ≤ −2` and the balance after the mover's next ply `j + 1` is
  still `≤ −2` (not taken straight back), and, when `B ≠ P`, the same holds from `B` (E5). A
  candidate is **evaluated** only if ply `j + 1` is inside the window, or ply `j` ends the game
  (a terminal position shows the material's fate: take `b_{j+1} := b_j`); otherwise it is open.
- **The line is fully examined** when the window reaches ply 5 (every candidate and its follow-up
  inside), or the line ends in checkmate, stalemate or an automatic draw within the window.
- **Keeping alternative** (review 5 B3, re-check C1–C2). For a line `Lk` of S, `k ≠ p`:
  - it **keeps** `v_j` when its outcome is `MATE(m, ·)`; or `STABLE(Δk)` with no decisive loss
    (§1.5), or with a decisive loss whose victim is not `v_j` (by `PieceId`); or `DRAWN` with
    `v_j` not captured in its window;
  - it **loses** `v_j` when its outcome is `MATE(o, ·)`, or `STABLE` with `v_j` the victim of its
    decisive loss;
  - otherwise (`OPEN`, `MISSING`, `DRAWN` with `v_j` captured) it is **undecided**.

  This is the test of §3.8b rule 2. A plain trade of `v_j` (no decisive loss) keeps it; a line
  that loses the same queen but wins a rook elsewhere has the queen as its decisive loss and
  keeps nothing. Losing less material is not keeping the piece.
- **Verify** (review 5 B1: refute only what was examined):
  1. `outcome(Lp)` is `MISSING(reason)` → `INCONCLUSIVE(reason)`.
  2. No candidate qualifies:
     - some candidate is open, or the line is not fully examined → `INCONCLUSIVE(LINE_TOO_SHORT)`
       (for example a PV cut right after the opponent's capture at ply 2);
     - otherwise → `REFUTED`.
  3. With the first qualifying `j`: some keeping alternative → `SUPPORTED` (the witness: an
     `EXISTS_ALTERNATIVE` target).
  4. S has no line other than `Lp` → `REFUTED` if `status(P).legal_move_count = 1`, else
     `INCONCLUSIVE(SCOPE_SHORT)` (re-check N4).
  5. Every other line of S loses `v_j` (none keeps it, none is undecided) → `REFUTED` (a forced
     loss).
  6. Otherwise → `INCONCLUSIVE(LINE_TOO_SHORT)`.
- **Findings:** `OfferFinding(MaterialAmount(−b_j), event at j, keeping lines)`.

**`sacrifice_sound_v1`** — an evaluation, not a return (review 3 B6).
- **Premise:** `sacrifice_offer_v1` SUPPORTED; relation `SAME_CONTEXT`.
- **Verify:** grade ∈ {BEST, EXCELLENT} and `E(Lp) ≥ 1000` → `SUPPORTED`; otherwise `REFUTED`.
- **Findings:** `CompensationFinding(ENGINE, E(Lp))`.
- The threshold 1000 (0.50 expected points) is a policy constant. A sound sacrifice is rendered
  as "the engine keeps the position after giving up …", never as BRILLIANT.

**`sacrifice_compensated_v1`** — a concrete return.
- **Premise:** `sacrifice_offer_v1` SUPPORTED; relation `SAME_CONTEXT`.
- **Verify:**
  1. Grade ∉ {BEST, EXCELLENT} → `REFUTED`.
  2. `outcome(Lp)` undecided → `INCONCLUSIVE` with its reason.
  3. `outcome(Lp)` is `MATE(m, n)`, and every keeping alternative is decided and either not a
     mate for `m` or a slower one (`n` strictly smaller) → `SUPPORTED`, kind `MATE`.
  4. `outcome(Lp)` is `STABLE(Δp)` with `Δp ≥ 0`, and every keeping alternative is `STABLE(Δk)`
     with `Δk < Δp` (strictly; none mates for `m`) → `SUPPORTED`, kind `MATERIAL_RETURN`: the
     material comes back and the line ends with more than the lines that kept it (integrated
     C3). A `DRAWN` keeping alternative is not comparable with `STABLE` and counts as undecided
     here (rule 5).
  5. A keeping alternative is undecided → `INCONCLUSIVE(LINE_TOO_SHORT)`.
  6. Otherwise → `REFUTED` (no concrete return shown).
- **Findings:** `CompensationFinding(kind, E(Lp))`.
- **Why both conditions:** in a won position Stockfish's WDL saturates (1000/0/0), so giving up a
  rook can lose 0 expected points; rule 4 then refutes it, because the keeping lines end with
  more material.

Counterexamples now handled:
- review 5 B3: `Lp` gives the queen (−9); an alternative loses the same queen but wins a rook
  (minimum −4). It does not keep the queen, so it is not a keeping line.
- review 5 B1: `Lp` cut right after the opponent's capture at ply 2 — the candidate is open,
  so the offer is `INCONCLUSIVE(LINE_TOO_SHORT)`, not `REFUTED`.
- `4k3/pp3ppp/8/8/8/8/PPn2PPP/R3K3 w`: every move loses the rook — no keeping line (rule 5).
- `6k1/5ppp/8/8/8/7P/3Q1PP1/r5K1 w` with an alternative scored `MATE(o, 3)`: a mated line is
  not keeping, so a queen given up to avoid mate is not an offer.
- An alternative that keeps the material until ply `j + 1` and loses the queen at ply 4: the
  queen is its decisive loss, so it does not keep it.
- re-check C1: an alternative that trades the queen (1.Qxd8+ Rxd8, no decisive loss) keeps it;
  it then enters `sacrifice_compensated_v1` rule 4 with its `Δk`, so a sacrifice that ends no
  better than that trade is refuted.

### 3.12 `better_move_v1`
- **Premise:** the `SUPPORTED` consequence on `Lp`: `mate_allowed_v1` if supported, else
  `material_loss_v1` if supported, else none. Proposed only when every consequence hypothesis on
  `Lp` is final.
- **Proposed when:** grade ≥ INACCURACY.
- **Verify:**
  1. `outcome(L1)` and `outcome(Lp)` comparable and `L1`'s above → `SUPPORTED`.
  2. Comparable and not above → `REFUTED` (the difference is not in mate or material).
  3. Otherwise → `INCONCLUSIVE` with the undecided outcome's reason, or `UNSTABLE` when both are
     decided but incomparable (`STABLE` against `DRAWN`; re-check N3).
- **Findings:** `ComparisonFinding(SearchMoveRef(S, 1, 1), outcome(L1), outcome(Lp))`
- **Evidence:** `SearchRef(S, 1)`, `SearchRef(S, p)`, the window `LineRef`s of both lines (a
  zero-ply segment is evidence but is not shown, R0-D §13.2), `FactRef("status", key(P),
  ("legal_moves",))` (re-check C1).
  (re-review N7).
- **Relation:** `COMPARES_WITH → premise`.

### 3.13 `prevents_v1`
- **Proposed when:** grade = BEST and S has a line other than `Lp`.
- **Bad outcome:** `MATE(o, ·)` or `STABLE(Δ ≤ −1)` (from P).
- **Verify:**
  1. Some other line of S is decided and not bad → `REFUTED` (one counterexample).
  2. `outcome(Lp)` is bad → `REFUTED`.
  3. Every other line decided (and bad), `outcome(Lp)` decided → `SUPPORTED`.
  4. Otherwise → `INCONCLUSIVE` with the first undecided reason.
- **Findings:** `PreventsFinding(kind, count, smallest loss)`.

## 4. What the catalogue does not do
- No template raises a `LineNeed`; needs are `FamilyNeed`s for `delta` / `pattern_delta` /
  `patterns` / `pieces` past the round-0 `ensure`, within the window cap.
- No template states intent, a plan, or a positional reason.
- No template compares two searches: material counts and mate scores of lines of S only.
- A configuration already present before the line (a standing pin) is not a mechanism in v1;
  the scan then ends `REFUTED`, and the planner does not render a refuted mechanism as "no pin"
  unless it is a `QUALIFIES` pick (R0-D §12.2). Pinned defenders whose defence is illusory are
  not covered.

## 5. Interactions

### 5.1 Typical chains
```text
blunder:   material_loss_v1 ⟵EXPLAINS─ fork_v1            (capture made by the forking piece)
                            ⟵EXPLAINS─ newly_unsafe_v1 | left_en_prise_v1 | removed_defender_v1
                            ⟵COMPARES_WITH─ better_move_v1
           (no CAUSES in v1: "through", not "decisively because", E8)
missed:    mate_missed_v1 (+ better_move_v1 when graded ≥ INACCURACY)
only move: only_move_v1, prevents_v1, forcing_v1 when it checks
sacrifice: sacrifice_offer_v1 ⟵DERIVED_FROM─ sacrifice_compensated_v1 | sacrifice_sound_v1
```

### 5.2 Labels (R0-D §11)
- BRILLIANT: grade ∈ {BEST, EXCELLENT} and `sacrifice_compensated_v1` SUPPORTED.
- GREAT: grade = BEST and `only_move_v1` SUPPORTED.
- MISS: previous grade ∈ {MISTAKE, BLUNDER}, grade ≥ INACCURACY, `better_move_v1` SUPPORTED with
  `outcome(L1)` = `MATE(m, ·)` or `STABLE(Δ1 ≥ 1)`.

### 5.3 Planner priorities (`selection_v1`)
- Primary consequence: `mate_delivered_v1` > `mate_found_v1` > `mate_in_one_allowed_v1` >
  `mate_allowed_v1` >
  `material_loss_v1` / `material_gain_v1` (larger amount first).
- Mechanism (`EXPLAINS` only; one): `fork_v1` > `skewer_v1` > `pin_v1` > `discovery_v1` >
  `newly_unsafe_v1` > `left_en_prise_v1` > `removed_defender_v1`, earliest node first. One
  mechanism in v1 (R0-D §12.2); chained mechanisms wait for `ENABLES` (integrated C4).
- Function: `only_move_v1` > `prevents_v1` > `sacrifice_compensated_v1` > `sacrifice_sound_v1` >
  `forcing_v1`; a label's grounds come first (R0-D §12.2).
- Comparison: `mate_missed_v1` > `better_move_v1`.
- Amount wording: "loses the queen (net 4)" when the victim is worth more than the amount.

## 6. Registry order
`mate_delivered_v1`, `mate_found_v1`, `mate_in_one_allowed_v1`, `mate_allowed_v1`,
`mate_missed_v1`, `material_loss_v1`,
`material_gain_v1`, `forcing_v1`, `only_move_v1`, `sacrifice_offer_v1`, `sacrifice_sound_v1`,
`sacrifice_compensated_v1`, `prevents_v1`, `fork_v1`, `pin_v1`, `skewer_v1`, `discovery_v1`,
`removed_defender_v1`, `newly_unsafe_v1`, `left_en_prise_v1`, `better_move_v1` (21 templates). Results do not depend on this order: proposals are admitted and numbered by (round, pass,
derivation depth, id) (R0-D §6.3, §10.3; integrated C5). The order is part of the build identity.

## 7. Cost
Per target move after round 0: two standard-line windows, one window per other line of S
(MultiPV, or the comparison set size), the baseline veto path, all on tier records; ≤ 4
mechanism scans of at most `q` edges each; constant-time exact templates. Target ≤ 30 ms for §3.

## 8. Test obligations
With the scripted engine (PVs, scores and WDL of S set by the test):
1. Every status rule of every template, positive and negative, Black as mover included; every
   `INCONCLUSIVE` reason a template can return.
2. Material: per-ply balance (capture-promotion as one ply; per-ply sums equal the `material`
   records); `b_0 = 0` from P and the decisive ply relative to it; widening to stability and to
   the cap; `DRAWN_END`; no change at all.
2a. Decisive event (re-check B1): a capture-fork (…Nxc2+ forking king and rook, the rook is `v`)
   as a loss and as a gain; a discovery whose uncovering move captures; "capture, then the main
   loss, then a partial recovery".
3. Baseline veto: 4.Bxc6 dxc6 (no gain); 1.d4 e5 2.dxe5 Bb4+ 3.Bd2 Bxd2+ 4.Qxd2 (no gain); an
   earlier offer re-credited (no sacrifice); a long trade over the 4-ply cap.
4. `material_loss_v1`: a loss shared with `L1` (REFUTED); `L1` `DRAWN` (INCONCLUSIVE); a pending
   recapture into P.
5. Mechanisms: appearance from edge records; the beneficiary's move; walked into (the played move
   into an e-file pin); the earliest node; support before a missing node; each causal check
   passing and failing (`EXPLAINS` vs `ASSOCIATED_WITH`), including a skewer line-up with an
   unrelated capture and a fork whose capture is made by another piece; discovered check winning
   the queen; discovery (a) with a blocker moving along the ray (not a discovery); discovery at
   `i = 0`; an unrelated earlier double attack before the real fork (`4kb2/8/8/6n1/1P1N4/8/P7/4K3
   w`, 1.a3 Bc5 2.b5 Be7 3.b6 Nf3+ 4.Ke2 Nxd4+ → `EXPLAINS` by the knight fork; 1.a3 Bc5 2.b5 Nf3+
   3.Ke2 Nxd4 → `ASSOCIATED_WITH`); several candidates at one node; a captured actor
   (`Absent`); a missing record below a qualifying candidate (`NEEDS_EVIDENCE`); a pin candidate
   whose `N_{q−1}` record is missing (undecided).
6. `removed_defender_v1`: each `DefenceEndReason`; a redundant defender; the edge is `EXPLAINS`,
   never `CAUSES`.
6a. `newly_unsafe_v1`: `4k3/8/8/4p3/8/2P5/8/3QK3 w`, 1.Qd4 exd4 (defended queen attacked by a
   pawn: `MOVED_INTO_ATTACK`, `EXPLAINS`); a piece moving from one attacked square to another; a
   line opened onto a piece by the played move; a castling rook (moved by squares); the piece
   leaving the exposed square before the capture (`ASSOCIATED_WITH`); a piece unsafe at P that
   stayed (not proposed).
6b. `left_en_prise_v1`: `4k3/8/8/4p3/3Q4/2P5/8/4K3 w`, 1.Kf2 exd4 (`SUPPORTED`, `EXPLAINS`); a
   played move that defends it enough (safe at C: REFUTED); `L1` losing the same piece decisively
   (REFUTED); `L1` merely trading it (kept); the moved piece (not proposed).
6c. Squares versus pieces (review 3 B4): every check that reads a POSITION record maps the piece
   through `square_of` at that node, including a piece absent at the node (test false).
6g. A keeping alternative cut before its first ply with a mate score for the mover (it keeps the
   piece: outcome `MATE(m, ·)`) in `sacrifice_offer_v1` and `sacrifice_compensated_v1`.
6f. Engine moves without nodes (review 4 blocker): `L1` cut before its first ply (deadline, and
   `max_nodes`) with a mate score — `mate_missed_v1` SUPPORTED citing `SearchMoveRef(S, 1, 1)`;
   the same for `better_move_v1` with a mate score; a material outcome on such a line stays
   `MISSING(LINE_TOO_SHORT)` and `better_move_v1` is `INCONCLUSIVE`; rendering the move's SAN
   from `status(P)`.
6d. `mate_in_one_allowed_v1`: proposed and SUPPORTED with an inconclusive judgement; its
   `EXACT` scope and witness; with `mate_allowed_v1` also SUPPORTED, exactly one claim of each
   and the planner choosing the exact one.
6e. `unsafe_v1`: outnumbered; attacked by a lower piece while defended; equal attackers of equal
   rank (safe).
7a. Review 5 regressions: a `Lp` cut right after the opponent's capture (offer
   `INCONCLUSIVE(LINE_TOO_SHORT)`); an alternative losing the same piece while winning other
   material (not keeping; offer `REFUTED` when no other line keeps it, no BRILLIANT); a keeping
   line too short to show the piece's fate (undecided); a lost piece that leaves its square and
   returns before the capture (`removed_defender_v1`, `newly_unsafe_v1`, `left_en_prise_v1` →
   `ASSOCIATED_WITH`); a capturer that starts attacking only later (`ASSOCIATED_WITH`); a missing
   `pieces` record in the exposure range (`NEEDS_EVIDENCE`); a promotion without capture
   (`material_gain_v1` proposed and SUPPORTED, finding names the promotion); an alternative that
   trades the given-up queen (keeps it; compensation compared with its `Δk`); an alternative
   `OPEN` with a long window (undecided, never a refutation); a present record failing the
   exposure check while another is missing (`ASSOCIATED_WITH`, no need); a capture at ply `j`
   that ends the game (evaluated with `b_{j+1} = b_j`).
7. Sacrifice: a won position where giving up a rook keeps `E = 2000` (WDL saturated) and the
   keeping lines end with more material — `sacrifice_compensated_v1` REFUTED, no BRILLIANT,
   `sacrifice_sound_v1` SUPPORTED; a mate return faster than every keeping mate; a mate return as
   fast as a keeping mate (REFUTED); a material return equal to the keeping lines (REFUTED);
   a material return strictly above them (SUPPORTED);
   no other line in S (MultiPV 1; one legal move); an ordinary exchange; the forced-loss fen; a mated alternative; an alternative
   losing later; `sacrifice_sound_v1` below 0.50 (REFUTED).
8. `better_move_v1` / `prevents_v1`: the outcome order, `DRAWN` against mates, a mate score with an
   `OPEN` window, undecided outcomes, one counterexample.
9. `only_move_v1` on a comparison S → `SCOPE_SHORT`.
10. Rounds: a mechanism `NEEDS_EVIDENCE` past the round-0 ensure → `ensure` → re-verified
    `SUPPORTED`; a test-only template raising `LineNeed`; a determinism re-run (same bytes).
11. The chains of §5.1 through the fixpoint, and the labels of §5.2.

Real-Stockfish fixtures belong to R4's acceptance corpus (R0-D §18.11).

## 9. Relation to R0-D
R0-D rev. 7 adds `SearchMoveRef` and premise search provenance (`SAME_SEARCH`). R0-D rev. 6
contains: `mate_in_one_allowed_v1` among the exact
templates, the reference to `unsafe_v1`, admission and numbering by (round, pass, depth, id); and
from rev. 5: work limits, `PremiseRelation`, alternatives
without the played move, the strength levels (`REALIZED` → `EXPLAINS`, `CAUSES` only with a
counterfactual check), the sound / compensated split, incremental observations; and from rev. 4: `Verdict.findings`, the quantifiers
`EXISTS_ALTERNATIVE` / `ALL_ALTERNATIVES`, `ScopeRequirement` and set-valued effective scopes,
`MATE_LINE` and `SCOPE_SHORT`, per-ply `material_flow` with `terminal`, the window cap, the
observation kinds of §2, the sacrifice pair, `ASSOCIATED_WITH` with runtime fallback, continued
lines, and R0-D §20 Q6 (settled by E1).

## 10. Open
None for v1. Static exchange evaluation (a stronger safety test than `unsafe_v1`), `opponent_view` (ignored
threats) and standing configurations are later catalogues.

## 11. Review dispositions

### 11.1 Rev. 1 `d66c2b3` — independent R2-D review: NOT_READY
| Finding | Resolution |
| --- | --- |
| B1 balances from P counted a recapture as a gain | E4–E5, §1.4 (rev. 3 form) |
| B2 forced loss as sacrifice | §3.11 offer and compensation |
| C1 loss shared with the best line | §3.1 rules 4–6 |
| C2 discovery indices; discovered check | §3.7 `discovery_v1` |
| C3 pre-existing configurations | §3.7 appearance |
| C4 needs before support | §3.7 scan |
| C5 outcome; premise; draws | §1.3, §3.12 |
| C6 untyped findings | §1.7 |
| C7 R0-D amendments | R0-D rev. 3–4 |
| C8 capture-promotion | per-ply balance |
| C9 reasons; stability | §1.3; R0-D §6.5 |
| N1–N9 | fork second threat; `SCOPE_SHORT`; counterexample first; redundant defender; controller-side `NEED_UNMET`; unused observations dropped; exact `forcing_v1`; qualification cap and wording; cost |

### 11.2 Rev. 2 `6677a48` — re-review: NOT_READY
| Finding | Resolution |
| --- | --- |
| B1 the baseline credited earlier material to the move (false gain, hidden loss, inflated sacrifice, `b_0` contradiction) | E4: every claim measured from P with `b_0 = 0`; E5: B only as a veto for gains and give-ups (§1.2, §1.4, §1.5); tests §8.3 |
| B2 a mated alternative, or one losing later, counted as keeping | §3.11 keeping: decided, not `MATE(o, ·)`, whole-window minimum; tests §8.7 |
| C1 `L1` `DRAWN` refuted a loss | §3.1 rule 4 |
| C2 causal checks not tied to the capture | §3.7 capturer is the actor / slider / blocker; pin holds at `N_{q−1}` |
| C3 discovery under-specified | §3.7 `discovery_v1` rewritten: blocker moved by `s`, attack sets before / after, `gives_check`, count-safe at `N_i` |
| C4 a configuration walked into by the played move was refuted | §3.7 `walked_into` at `i = 1` for losses |
| C5 `SELECTED_ALTERNATIVES` two meanings | R0-D rev. 4 quantifiers; §3.0 targets |
| C6 incomplete hypothesis fields; `requires`; meet of scopes | §3.0 field table; R0-D rev. 4 set-valued effective scope |
| N1 deadline vs `max_nodes` cut | `MISSING(BUDGET_LIMIT)` |
| N2 `MATE_END` | §1.3 mapped to `MATE` |
| N3 count-safe | §1.6 |
| N4 appearance from `pattern_delta` / `delta` by id | §3.7 table |
| N5 chess strings in findings; `FactRef` revs | §1.7 `SearchRef` / `MoveRef`; revision note |
| N6 `j` only at the opponent's plies | §3.11 |
| N7 `MateFinding` with outcomes | `ComparisonFinding` |
| N8 4-ply cap | §1.4, test §8.3 |
| N9 tests for the counterexamples, rounds, determinism | §8.3–§8.10 |

### 11.3 Rev. 3 `3eb8eef` — re-check: NOT_READY (local)
| Finding | Resolution |
| --- | --- |
| B1 the decisive event chose the first negative ply (a capture-fork named the pawn) | §1.5 first ply reaching the final level; tests §8.2a |
| C1 an unrelated earlier appearance hid the real mechanism | §3.7 candidates, qualification by the causal check, fallback to `ASSOCIATED_WITH`; `Absent` actor |
| C2 targets not encodable (population, `at`, horizon, basis, wildcard) | §3.0 segments, populations, horizons, scope basis, concrete requirements; R0-D: basis belongs to scopes |
| C3 R0-D §8.5 / §7.3 wording from rev. 2 | amended in R0-D |
| N1 reasons outside the closed set | `MISSING(LINE_TOO_SHORT)`, `NOT_COMPUTED(<parameter>)` |
| N2 records read by checks not requested; later node reported | §3.7 records read and verify rule 1 |
| N3 `STABLE` vs `DRAWN` in `better_move_v1` | §3.12 rule 3 |
| N4 offer with no other line | §3.11 rule 4 |

### 11.4 Rev. 4 `383be00` — re-check: READY_WITH_CORRECTIONS
| Finding | Resolution |
| --- | --- |
| C1 the §3.7 example's knight fork does not qualify (the knight was already attacked) | example replaced by a checked line; the original kept as an `ASSOCIATED_WITH` test |
| N1 checks reading records above the candidate's node | §3.7 undecided candidates raise needs |
| N2 `NOT_COMPUTED` parameters outside R0-D's set | R0-D §9.2 `NOT_COMPUTED(<parameter>)` |
| N3 `ProofScope` could not name the line | R0-D §9.3 `ProofScope.at`; §3.0 note |

### 11.5 Rev. 5 `a541177` — third independent review of #55 / #56 (NOT_READY) and the owner's legacy comparison
| Finding | Resolution |
| --- | --- |
| B4 discovery compared a piece with a set of squares | §1.1 squares versus pieces (`sq(x, N)`), §3.7 discovery (a)/(b) and the pin check; test §8.6c |
| B5 a count change promoted to a decisive cause | E8; `REALIZED` checks give `EXPLAINS` at most; `removed_defender_v1` no longer `CAUSES`; planner wording; R0-D D15 |
| B6 a sound but uncompensated sacrifice earned BRILLIANT | §3.11 `sacrifice_sound_v1` (evaluation) and `sacrifice_compensated_v1` (mate, or material back and no worse than the keeping lines); WDL-saturation test |
| Owner: the most common blunder (a hanging piece) had no mechanism | E9; §3.8a `newly_unsafe_v1`, §3.8b `left_en_prise_v1` |
| Owner: exact mate evidence unused | §3.3 `mating_moves` at C gives an `EXACT` scope |
| R0-D B2 premise relations, B3 alternatives | §3.0 relations per template; alternatives without the played move |
| Deferred to the next catalogue | the comparator counterfactual (first `CAUSES`), threats for good moves, back-rank and overload mechanisms, two-piece double attacks |

### 11.6 Rev. 6 `30d4887` — integrated re-review of #55 / #56: NOT_READY (local)
| Finding | Resolution |
| --- | --- |
| B1 counting safety refuted the hanging blunders (1.Qd4 exd4; a defended queen left to a pawn); out-of-domain cases refuted; `left_en_prise_v1` never checked C | §1.6 `unsafe_v1` (outnumbered or attacked by a lower piece); §3.8a/b domain guards, safety at C, fact-engine examples; tests §8.6a/b/e |
| C1 exact mate evidence gated by the judgement | §3.3a `mate_in_one_allowed_v1` (exact, no judgement), optional premise of `mate_allowed_v1` |
| C2 a best line trading the piece refuted `left_en_prise_v1` | §3.8b rule 2: only `L1`'s decisive loss of `v` |
| C3 sacrifice return not strict | §3.11 rules 3–4 strict; R0-D §8.5 aligned; tests |
| C4 a second mechanism in a cause position | §5.3 one mechanism |
| C5 order independence | §6 (R0-D §6.3, §10.3) |
| C6 alternatives in satisfaction | R0-D §9.4 |
| N1 references vs ids; `patterns` relations by square | §1.1 |
| N2 castling rook; "that attacker takes it" | §1.1 moved by squares; §3.8a causal check |
| N3 the piece moving away before the capture | §3.8a/b causal checks at `N_{q−1}` |
| N4 incremental observations | §2 no incremental kinds in `obs_v1`; R0-D §7.1 rounds |
| N5, N6 | R0-D §8.3, §6.5 |
| N7 table structure; base revision | §3.0 paragraph after the table; header |

### 11.7 Rev. 7 `65c7fae` — focused re-check: READY_WITH_CORRECTIONS (both PRs)
The re-check confirmed B1 and C1–C6 in the fact engine (1.Qd4 exd4; 1.Kf2 exd4; the fork and
discovered-check examples still qualify under `unsafe_v1`).

| Finding | Resolution |
| --- | --- |
| 1 the judgement gate still covered `mate_in_one_allowed_v1` | §3.0 common rules; R0-D §8.5 exact list |
| 2, 3 the optional premise was refused (C is not `Lp`'s anchor) and would duplicate the claim | §3.3 no premise; the planner relates the two claims; test §8.6d |
| 4 `left_en_prise_v1` scope and evidence | §3.0 row `ENGINE`; §3.8b evidence, scope; unreachable rule removed |
| 5 `Defined` wrapper; pinned attackers; §9 base | §1.6; §9 |

### 11.8 Rev. 8 `dda7792` — fourth independent review of #55 / #56: NOT_READY (one blocker)
| Finding | Resolution |
| --- | --- |
| Blocker: `mate_missed_v1` and `better_move_v1` cited `MoveRef(first node of L1)`, which does not exist when `L1` is cut before its first ply but its mate score decides the outcome | §1.1 moves of a search; findings use `SearchMoveRef(S, 1, 1)` (R0-D §4, option B of the review); test §8.6f |
| Premise search provenance | §3.0 every v1 premise `SAME_SEARCH` (R0-D §8.1.2) |
| `unsafe_v1` approximation | unchanged, stated in §1.6 |

Focused re-check of rev. 9 (`eb84c71`): READY_WITH_CORRECTIONS (both PRs). Applied in rev. 10:
C1 evidence for §3.6 and §3.12 (`status(P).legal_moves`, the searches) and the guard in R0-D;
C3 keeping minimum over `b_0 … b_k`; C4 `mate_found_v1` findings rule; C5 zero-ply lines not
shown (R0-D §13.2).

### 11.9 Rev. 10 `c919df0` (merged, #56) — fifth independent review: NOT_READY for implementation
The review kept the architecture (observation → hypothesis → verification → claim graph, scope
separate from causal strength, the shared hypothesis contract, no `CAUSES` in v1).

| Finding | Resolution |
| --- | --- |
| B1 an offer cut right after the opponent's capture could be `REFUTED` | §3.11 candidates evaluated only with their follow-up ply; `REFUTED` only when the line is fully examined; test §8.7a |
| B2 a removed defence or exposure not tied to the actual capture (a piece leaving and returning; a later capturer) | §1.6a exposure continuity at every node to `N_{q−1}`; §3.8, §3.8a, §3.8b causal checks; needs for missing records; tests §8.7a |
| B3 "keeping" judged by balance, so a line losing the same piece counted | §3.11 keeping by `PieceId`: the given-up piece is not captured, the window long enough; tests §8.7a |
| C1 promotion without capture missed by `material_gain_v1` | §3.2 proposed on a capture or a promotion; test §8.7a |

Focused re-check of rev. 11 (`bbb3006`): READY_WITH_CORRECTIONS. Applied: C1 keeping by the
decisive-loss test of §3.8b (a plain trade keeps the piece; rev. 11's "never captured" re-opened a
false BRILLIANT); C2 "decided for keeping" defined (keeps / loses / undecided), rule 5 refutes only
when every other line loses the piece; C3 §1.6a fails on a present failing record before raising
needs; C4 stale wording; N1 a game-ending capture is evaluated.

