# Fact engine — packet F6 implementation: the `exchange` family and on-request families

Status: **rev. 2 — independent F6 review READY_WITH_CORRECTIONS (C1, C2) applied (§4)**.
Date: 2026-10-11. Design: [`fact-engine-f6-design.md`](fact-engine-f6-design.md) rev. 3 (F6-D).
Base: `main @ 2fbd253` (F6-D, LV-D and Q3 merged).

## 1. Scope delivered

| Module | Content |
| --- | --- |
| `facts/families/exchange.py` (new) | **Family:** `ExchangeFamily` (POSITION, `DEFINED`, `exchange_v1`, `on_request = True`). **Records:** `ExchangeFacts`, `PieceExchange`. **Functions:** `gain` (F6-D §2.1: legal captures, least valuable first, king last, ties by from-square, queen promotions only, en passant excluded, stop allowed), `exposure` (§2.2: real, or with the turn passed for the side to move), `safe_moves` (§2.3). **Constants:** `IN_CHECK`, `NOT_EXPOSED`, `SEE_V1`. |
| `facts/families/base.py` | `on_request(family)`: the optional class attribute, default `False` (§2.0) |
| `facts/families/__init__.py` | `ExchangeFamily` appended to `REGISTRY`; new public names |
| `facts/engine.py` | `_select(None)` selects only the families that are not on request; `_check_registry` refuses a default family that requires an on-request one |
| `facts/tree.py` | `TreeView.default_families()` |
| `facts/storage.py` | `FamilyEntry.on_request` (last field, default `False`) in the build identity; `FACTS_BUILD_VERSION = "2"` |
| `reasoning/controller.py` | round 0's enrichment ensures `view.default_families()` instead of `view.families()` (amends R1 round 0, R0-D §6.1 step 4) |

## 2. Implementation decisions within the design

1. **`gain` uses python-chess's legal move generation** at every step of the swap-off. Pins, king
   safety and x-rays then follow from the board itself. The board is pushed and popped, never
   copied, except to pass the turn in `exposure`.
2. **A tie between equal capturers goes to the lower from-square index**, as F6-D §2.1 states:
   B on b3 before N on c3 (test).
3. **Passing the turn** clears the en-passant square. A null move cannot keep an en-passant right.
4. **`safe_moves` scans the legal moves in `status` order** (sorted UCI). For each, it evaluates
   only the scanned piece's square after the move.
5. **The guard digest** (F5-D §4) changes because the registry and the build identity changed.
   `FACTS_BUILD_VERSION` is bumped to `"2"` and a row is added to the guard table. Row `"1"` stays,
   as history.

## 3. Evidence

### 3.1 Tests
- **`tests/facts/test_exchange.py`, 23 tests.** It covers F6-D §5.
  - **The swap-off:** thirteen hand positions:
    - an undefended and a defended knight, an undefended rook;
    - two attackers against one defender;
    - a battery that joins, and the same position without it;
    - a pinned attacker that may not capture, and one that captures along its pin;
    - a king that takes only an undefended rook;
    - a capture that promotes, with the bonus 8;
    - en passant not counted;
    - a defender that declines a losing recapture.
  - **Exposure:** hypothetical for the side to move; `IN_CHECK` in check, where every piece is
    scanned.
  - **Safe moves:**
    - a hanging knight's retreats;
    - `NOT_EXPOSED` for a piece that is not exposed;
    - a trapped knight with none, while a capture elsewhere exists (the rev. 1 flaw);
    - a checkmate with none.
  - **On request:** none from an `open` without families; one from an `ensure`; one from an `open`
    that names the family; a default family requiring an on-request one is refused; the flag is in
    the build identity.
  - **Determinism:** two transpositions share a record, and a saved tree loads with the same
    record.
- **`tests/reasoning/test_round_zero.py`:** round 0 computes no `exchange` record on any node, and
  `default_families()` excludes it.

| Suite | Result |
| --- | --- |
| `tests/facts`, `tests/reasoning`, `tests/tools`, `tests/test_package_boundaries.py` | 688 passed, 8 skipped (gated engine tests), about 12 minutes with the 400-game fuzz |

### 3.2 Cost (F6-D §4 bound: 95th percentile ≤ 50 ms)
Every position before a move in the 100 games of the LV-D benchmark (7 552 positions), one record
each:

| median | 95th percentile | 99th percentile | max |
| --- | --- | --- | --- |
| 2.0 ms | 11.2 ms | 20.2 ms | 43.1 ms |

- **Pieces scanned for `safe_moves`:**
  - none in 4 470 positions (59 %);
  - one in 2 037;
  - two in 475;
  - more than two in 570, mostly positions in check, where every piece is scanned.
- **Result:** the bound holds with a wide margin.

### 3.3 Changed existing tests
- `test_eager_tree_equals_minimal_tree_plus_ensure` compared the eager tree with an `ensure` of
  every registered family. It now ensures the default set (`not on_request`), since the eager tree
  holds exactly that (F6-D §2.0).
- `test_build_version_guard`: row `"2"` added (§2.5).

## 4. Independent F6 review (rev. 1 `5ed4124`): READY_WITH_CORRECTIONS

The review passed:
- the on-request contract, with the round-0 test;
- the SEE on legal captures;
- the exposures and the per-piece `safe_moves`;
- the tests;
- the cost.

It found no blocker.

| Finding | Disposition |
| --- | --- |
| C1 `hypothetical` was true for every piece of the side to move, also in check, where no gain was computed | Applied. `hypothetical = own and not in_check`: true exactly when the turn was passed for the gain. F6-D §3 states it, and the in-check test asserts it. |
| C2 the record type of `safe_moves` in F6-D §3 lacked `NotApplicable("NOT_EXPOSED")`, which rev. 3's §2.3 introduced | Applied. F6-D §3 now lists `tuple[str, ...] \| NotApplicable \| NotObserved` with their meanings. The code already had it. |
| Note: measure positions richer in tactics, promotions or exposed pieces | Recorded. The 7 552 benchmark positions include 570 with more than two scanned pieces; the maximum was 43 ms. LV1's benchmark run records the time of each requested record on its own positions. |
