# Fact engine — packet F6-D: the `exchange` family (static exchange evaluation)

Status: **rev. 1 — awaiting independent review** (design only).
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
| X0 | **One new family, `exchange`** (POSITION scope, `DEFINED`, version `exchange_v1`, convention `see_v1`). It is computed only on request. It is not eager, not mandatory, and no other family requires it. |
| X1 | **The swap-off is played with legal captures.** At each step, the capturing side picks its least valuable legal capture onto the square, and either side may stop. Pins and moving into check therefore count, and x-rays and batteries appear as pieces are removed. Checks given, threats elsewhere and discovered attacks are not seen: that is what "static" means, and the reason the family is `DEFINED`. |
| X2 | **Both colours.** For a piece of the side not to move, the gain is the real one: the opponent is to move. For a piece of the side to move, the gain is hypothetical: the turn is passed (a null move, with en passant cleared), and the record marks it `hypothetical`. When the side to move is in check, a null move is not a position, so its pieces' gains are `NotApplicable("IN_CHECK")`. |
| X3 | **The safest move.** For the side to move, `least_piece_exposure` is the smallest net exposure one legal move can leave (§2.3). It answers "could the material have been saved?" without a tree node per legal move. |
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

## 2. The `see_v1` convention

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

### 2.3 The safest move (side to move only)
For each legal move `m` of the side to move `o`:
- `exposure(m)` is the largest exposure of `o`'s non-king, non-pawn pieces in the board after
  `m`, minus `value(captured by m)`;
- `least_piece_exposure` is the minimum of `exposure(m)` over legal moves. It is 0 when some move
  leaves no net exposure, and `NotApplicable("NO_LEGAL_MOVE")` in a terminal position.

Pawns are left out of the maximum: the field serves piece-sacrifice rules, and a pawn exposure
would make almost every position exposed.

## 3. Records

```text
ExchangeFacts(
    pieces: tuple[PieceExchange, ...],                       # every non-king piece, by square
    least_piece_exposure: Defined[int] | NotApplicable)      # see_v1, side to move

PieceExchange(
    square: str, color: Color, piece_type: PieceType,
    gain: Defined[int] | NotApplicable,                      # see_v1; NotApplicable("IN_CHECK")
    first_capture: str | None,                               # canonical UCI, None when gain is 0
    hypothetical: bool)                                      # the owner is to move (turn passed)
```

- **Scope.** The family is POSITION, so the record depends only on the `PositionKey`. It is
  computed from the board rebuilt from it (F2-D §1.5).
- **Registry.** The record types join the closed registry (F5-D §2). The family is appended to
  `REGISTRY` after `patterns` / `pattern_delta`; it requires nothing.
- **Build identity.** `exchange_v1` and `see_v1` enter the build identity like every family
  version (F5-D §4). A changed definition is a new version, never a silent replacement (A0 §5).

## 4. Cost
- **Measured on 7 552 plies of chess.com games** (the LV-D benchmark, prototype outside the
  repository): exposures of one side's pieces after a move took about 2 ms. The safest move took
  about 70 ms in a middlegame (about 35 legal moves).
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
3. **The safest move:**
   - 0 when a hanging piece can retreat;
   - the forced loss when it cannot (a trapped piece);
   - net of a capture;
   - `NotApplicable` in a terminal position.
4. **Determinism:**
   - the same `PositionKey` gives the same record whatever the move order;
   - records round-trip through the canonical encoding;
   - a saved tree with `exchange` records loads and verifies (F5-D).
5. **Isolation:** the boundary test still holds, and the family imports nothing from reasoning or
   legacy code.

## 6. Delivery

| Packet | Content | Gate |
| --- | --- | --- |
| F6-D (this) | the `exchange` family and `see_v1` | independent review READY |
| F6 | `families/exchange.py`, the registry entry, tests; record `fact-engine-f6-implementation.md` | READY |

F6 comes before LV1 (LV-D), which is the first reader.
