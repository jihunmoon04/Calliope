# Fact engine — packet F6-D: the `exchange` family (static exchange evaluation)

Status: **rev. 3 — re-review READY_WITH_CORRECTIONS (C2) applied (§8); record types aligned by the F6 review (§3)** (design only).
Date: 2026-10-11. Base: `main @ 37f1b2a`. Parent design:
[`fact-engine-a0-design.md`](fact-engine-a0-design.md) rev. 4. This packet amends §6.11 there,
which excluded static exchange evaluation "(attacker-order choice needs a policy)". The
consumer is the provisional BRILLIANT rule of
[`reasoning-label-v2-design.md`](reasoning-label-v2-design.md) (LV-D).

A0 left SEE out until it had a reviewed definition. This packet gives one: a `DEFINED` family
`exchange` under the convention `see_v1`. For every piece it records how much material the
opponent wins by starting captures on that piece's square.

## 0. Decisions

| # | Decision |
| --- | --- |
| X0 | **One new family, `exchange`** (POSITION scope, `DEFINED`, version `exchange_v1`, convention `see_v1`). It is the first **on-request** family (§2.0): it is computed only when a request names it, never by default. It is not mandatory, and no other family requires it. |
| X1 | **The swap-off is played with legal captures.** At each step, the capturing side picks its least valuable legal capture onto the square, and either side may stop. Pins and moving into check therefore count, and x-rays and batteries appear as pieces are removed. Checks given, threats elsewhere and discovered attacks are not seen: that is what "static" means, and the reason the family is `DEFINED`. |
| X2 | **Both colours.** For a piece of the side not to move, the gain is the real one: the opponent is to move. For a piece of the side to move, the gain is hypothetical: the turn is passed (a null move, with en passant cleared), and the record marks it `hypothetical`. When the side to move is in check, a null move is not a position, so its pieces' gains are `NotApplicable("IN_CHECK")`. |
| X3 | **Safe moves per piece** (rev. 2, review C1). For each piece of the side to move, `safe_moves` lists the legal moves after which that piece is not exposed (§2.3). It states, piece by piece, whether a piece could be kept, without a tree node per legal move. The rev. 1 aggregate `least_piece_exposure` is dropped: a capture elsewhere lowered it, so it never showed that a given piece could be saved. |
| X4 | **Values are `points_v1`** (P 1, N 3, B 3, R 5, Q 9), shared with `material`. A capture that promotes adds `9 − 1`. A king is never a victim, and as a capturer it is ordered last. |

## 1. Scope
- **In scope:**
  - the family, its records and the `see_v1` convention;
  - its registry entry and record types (F5-D §2);
  - tests.
- **Out of scope:**
  - any use of the family. The BRILLIANT rule that reads it is LV-D.
  - A dynamic or engine-checked exchange, which is the consumer's business (LV-D checks the
    capture with a search).
  - "Trapped piece", which A0 §6.11 still excludes.

## 2. The `see_v1` convention and the on-request contract

### 2.0 On-request families (review B1; amends A0 §2.1, §5)
Today an `OpenRequest` or `ExtendRequest` without `families` makes every registered family eager
(`FactEngine._select(None)`), and round 0 ensures `view.families()` on the standard lines'
nodes. Registered as is, `exchange` would be computed on every node of every analysis, at up to
about 0.1 s each.

- **The flag.** A family may declare `on_request = True`. Families without the attribute are
  on-request `False`.
- **The default set.** `None` in an `OpenRequest` / `ExtendRequest` selects the families with
  `on_request = False`, closed under `requires`, as before. An on-request family is computed only
  when a request names it: `families` of an open or extend, or an `EnsureRequest`.
- **Registry check.** A default family may not require an on-request family. The engine refuses
  such a registry at construction.
- **`TreeView.default_families()`** returns the default set of the tree's session. Reasoning's round
  0 enrichment ensures `default_families()` instead of `families()` (amends R1's round 0, R0-D
  §6.1 step 4).
- **Identity.** The flag is part of each family's entry in the build identity (F5-D §4), next to
  version, scope and class. Changing it is a build change.
- **Replay.** Saved trees replay their request log (F5-D). A request that named `exchange` names
  it again; a request that did not still does not compute it.

### 2.1 Gain on one square
`gain(board, s)` is the material the side to move wins by starting captures on `s`, which holds a
piece of the other side:

```text
gain(board, s):
  captures = legal moves of the side to move that land on s (en passant excluded: its victim is
             not on s); promotions only as a queen
  if none: return 0
  c = the capture by the least valuable piece (points_v1; king last; ties by from-square index)
  won = value(victim on s) + (8 if c promotes else 0)
  return max(0, won − gain(board after c, s))
```

- **Integers only.** The recursion ends because every step removes a piece.
- **Legality.** Legality is decided by python-chess in the board after each capture. So a pinned
  attacker cannot join, unless it captures along the pin, and a king joins only when `s` is no
  longer defended.
- **Order.** "Least valuable first" is the attacker-order policy A0 asked for. It is the usual
  swap-off convention and is what `see_v1` names.

### 2.2 Exposure of a piece
For a piece `p` on `s`, owned by `o`:
- if `o` is not to move: `gain(board, s)`, real;
- if `o` is to move and not in check: `gain(board with the turn passed, s)`, `hypothetical =
  true`;
- if `o` is to move and in check: `NotApplicable("IN_CHECK")`.

The first capture of the swap-off (canonical UCI) is recorded with the gain, or `None` when the
gain is 0.

### 2.3 Safe moves (side to move only; rev. 2)
For each non-king piece `p` of the side to move **that is exposed** (rev. 3), and for every
non-king piece of the side to move **when it is in check**:
- `safe_moves(p)` lists the legal moves `m`, in `status` order (canonical UCI), after which `p`
  is not exposed: `gain(board after m, square of p after m) = 0`.
- A piece is exposed when its hypothetical `gain ≥ 1`. Its `safe_moves` then answers "could this
  piece have been kept?".
- A piece that is not exposed has nothing to save. Its `safe_moves` is
  `NotApplicable("NOT_EXPOSED")`, and the scan is skipped.
  - The square of `p` after `m` is its destination if `m` moves `p`, otherwise its own square.
  - The gain is real, since the opponent is to move after `m`.
- **It is defined in check too:** the legal moves are then the evasions.
- **Empty means no legal move keeps this piece:** a trapped or lost piece.
- **It says nothing about other pieces.** Saving `p` may expose another piece. A consumer that
  needs more combines it with the other pieces' records.

For pieces of the side not to move, `safe_moves` is `NotObserved`, as for the other facts that
depend on the side to move (A0 §6.3).

## 3. Records

```text
ExchangeFacts(
    pieces: tuple[PieceExchange, ...])                       # every non-king piece, by square

PieceExchange(
    square: str, color: Color, piece_type: PieceType,
    gain: Defined[int] | NotApplicable,                      # see_v1; NotApplicable("IN_CHECK")
    first_capture: str | None,                               # canonical UCI, None when gain is 0
    hypothetical: bool,                                      # gain computed with the turn passed
    safe_moves: tuple[str, ...]                              # §2.3: exposed pieces of the side
              | NotApplicable                                #   to move, every piece in check;
              | NotObserved)                                 #   "NOT_EXPOSED"; side not to move
```

- **Scope.** The family is POSITION, so the record depends only on the `PositionKey`. It is
  computed from the board rebuilt from it (F2-D §1.5).
- **`hypothetical`** is true exactly when the gain was computed with the turn passed: for a piece
  of the side to move, outside check. In check the gain is `NotApplicable("IN_CHECK")` and
  `hypothetical` is false. Whose turn it is comes from `status` (F6 review C1).
- **Registry.** The record types join the closed registry (F5-D §2). The family is appended to
  `REGISTRY` after `patterns` / `pattern_delta`, with `on_request = True`; it requires nothing.
- **Build identity.** `exchange_v1` and `see_v1` enter the build identity like every family
  version (F5-D §4). A changed definition is a new version, never a silent replacement (A0 §5).

## 4. Cost
- **Measured on 7 552 plies of chess.com games** (the LV-D benchmark, prototype outside the
  repository): exposures of one side's pieces after a move took about 2 ms, and one SEE about
  0.1–0.3 ms.
- **Cost of a record (re-review C2):**
  - The gains cost one SEE per non-king piece, about 30 at most.
  - `safe_moves` costs, for each **exposed** piece, one board push and one SEE per legal move: about
    35 SEE per exposed piece in a middlegame.
  - Most positions have no or one exposed piece of the side to move (the benchmark's 7 552 plies:
    6.6 % had a net piece offer after the move). A record therefore costs a few ms to about 30 ms.
  - The worst case is many exposed pieces, or check with every piece scanned. A check has few
    legal moves.
  - Before rev. 3, scanning every piece after every move would have cost up to about 500 SEE per
    record.
- **Budget.** F6's record measures the time per record on the benchmark positions: median, 95th
  percentile and maximum. Above 50 ms at the 95th percentile, F6 stops for a design change. The
  cost is paid only where a request names the family (§2.0).
- **On request only.** The family is never eager, so cost arises only where a consumer asks for
  it. LV-D asks at P and at C of a target move, and only when a sacrifice is possible.

## 5. Tests
1. **Gain on hand positions:**
   - a simple trade (B takes a defended N: 0) and a winning capture (an undefended R: 5);
   - a defended piece attacked twice (N with one defender, two attackers);
   - a battery and an x-ray that join as pieces leave;
   - a pinned attacker that may not capture, and one that captures along its pin;
   - a king that captures only an undefended piece;
   - a capture that promotes;
   - en passant ignored;
   - a stop: the side declines a losing recapture.
2. **Exposure:**
   - real for the side not to move;
   - `hypothetical` for the side to move;
   - `NotApplicable("IN_CHECK")` when the side to move is in check;
   - `first_capture` is the least valuable legal capturer.
3. **Safe moves:**
   - a hanging piece's retreats are listed;
   - a piece that is not exposed has `NotApplicable("NOT_EXPOSED")` and is not scanned;
   - a trapped piece has none;
   - a capture elsewhere does not count as saving the piece (the rev. 1 flaw);
   - evasions in check are scanned;
   - `NotObserved` for the side not to move;
   - empty in a terminal position.
4. **On request** (review B1):
   - an `open` without `families` computes no `exchange` record;
   - round 0 of an analysis computes none (no record on any node);
   - an `ensure` naming `exchange` computes it;
   - a registry where a default family requires an on-request family is refused;
   - `default_families()` excludes `exchange`.
5. **Determinism:**
   - the same `PositionKey` gives the same record whatever the move order;
   - records round-trip through the canonical encoding;
   - a saved tree with `exchange` records loads and verifies (F5-D).
6. **Isolation:** the boundary test still holds, and the family imports nothing from reasoning or
   legacy code.

## 6. Delivery

| Packet | Content | Gate |
| --- | --- | --- |
| F6-D (this) | the `exchange` family and `see_v1` | independent review READY |
| F6 | `families/exchange.py`, the on-request flag in `families/base.py` and `engine._select`, `TreeView.default_families()`, the registry entry, round 0's `default_families()` in reasoning, tests; record `fact-engine-f6-implementation.md` | READY |

F6 comes before LV1 (LV-D), which is the first reader.

## 7. Review dispositions (rev. 1 `08e4325`, independent review: NOT_READY)

The review kept the design: a deterministic SEE fact in its own family, read by reasoning. It
confirmed the swap-off rule, legal captures, pins and king safety, the promotion bonus and the
POSITION scope.

| Finding | Disposition |
| --- | --- |
| B1 "on request" contradicts the engine: `_select(None)` makes every registered family eager, and round 0 ensures `view.families()` | Confirmed in `engine.py` and `controller.py`. Applied (§2.0): families may declare `on_request`; `None` selects the default set; a default family may not require an on-request one; `TreeView.default_families()`; round 0 ensures the default set; the flag is in the build identity. Tests: no `exchange` record from an open or from round 0, one from an explicit ensure (§5.4). |
| C1 `least_piece_exposure` can be negative, and a capture elsewhere makes a lost piece look saveable | Applied (§2.3, X3): the aggregate is dropped. Each piece of the side to move gets `safe_moves`, the legal moves after which that piece is not exposed. Whether a given piece could be kept is read from its own record. The consumer (LV-D) is updated to match. |

## 8. Review dispositions (rev. 2 `c19fd3f`, re-review: READY_WITH_CORRECTIONS)

The re-review found B1 and C1 resolved and the SEE definition clear.

| Finding | Disposition |
| --- | --- |
| C2 the cost of `safe_moves` was understated ("about the same" as one scan, while it pushes and evaluates per legal move) | Applied (§2.3, §4). `safe_moves` is computed only for exposed pieces, or for every piece in check (`NOT_EXPOSED` otherwise). The cost is stated per exposed piece, and F6 measures the time per record against a 50 ms 95th-percentile bound. |
