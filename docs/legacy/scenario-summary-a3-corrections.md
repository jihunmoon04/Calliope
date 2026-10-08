> **LEGACY — FROZEN, NOT THE CURRENT DESIGN.** This document describes the MVP-era implementation preserved at tag `legacy-mvp-g0`. It is kept only as historical reference for the redesign; nothing in it is a current requirement or decision. Current design: [`docs/design/`](../design/README.md). Index: [`docs/README.md`](../README.md).

# PR #30 A3 review corrections

Status: A3_READY.
Reviewed head: `7d527b2`; independent verdict supplied by the user:
READY_WITH_CORRECTIONS (C1, medium). This record describes authored corrections;
the subsequent independent re-review of `672f162` returned READY, supplied by the
user on 2026-10-08. The authored correction alone did not establish that verdict.

## 1. Independent evidence at the reviewed head

The reviewer reported 2,954 passed / 2 skipped using the original command without
Stockfish, changed-file Ruff check/format and diff check, unchanged P4-P12/public
schema/composition/exports, and deterministic output. Their 100 independently
computed python-chess trials included 137 promotions and three en passant captures
with zero mismatches, including mirrored checks. This is the reviewer's evidence;
the authored correction did not repeat or regenerate those random expectations.

## 2. Finding-to-change traceability

| Finding | Correction / disposition | Verification |
| --- | --- | --- |
| C1: capture-promotion absent from digest | Digest now includes every selected participant PROMOTION, in existing event order. Capture precedes promotion at the same ply; promotion precedes later recapture. Earlier quiet participant promotion is included; nonparticipant promotion stays excluded. Contract and E06 required_digest_events amended explicitly. | E06 base/mirror golden acceptance; eight capture-promotion/recapture cases (N/B/R/Q, both colors); earlier quiet promotion; nonparticipant exclusion; actual promotion transition/physical identity refs resolve. |
| L1: repeated victim square | CAPTURE_NORMAL formats victim color/type without its square, then names landing once. Capturer retains its source square. | All eight promotion cases assert no repeated landing phrase; actual reviewer reproduction below. |
| L2: king-only castling context missing | MOVE has a closed king-castling branch, using validated parent UCI and actual king endpoints. Nonparticipant rook remains excluded. Existing rook-only branch unchanged. | Two king-only base/mirror cases; E15 rook-only base/mirror acceptance remains passing. |
| L3: ambiguous Stockfish test count | Reproduction separates the engine-independent group from two optional real-binary analyze_move_slice tests. Historical counts and binary dependency corrected. | 2,966 pure-group tests passed; two real-binary slice tests passed separately in this environment. Without a binary, both slice tests skip. |
| L4: full validation/render cost | Deferred to a reviewed public-integration performance packet. Full recomputation remains the integrity boundary; no caller-asserted trusted flag or cache bypass introduced. | Existing 0/1/64/256 cost record remains attributed to 7d527b2; no new performance measurement claimed. |
| L5: unvalidated standalone resolver looks public | Renamed to _resolve_source; docstring explicitly marks internal selector lookup and directs untrusted summaries through renderer validation. No package export or compatibility alias added. | Updated internal tests; malformed selectors and no-extra-port-call checks still pass. |
| L6: private foundation helpers | Deferred to a separately reviewed shared-validation refactor. P4-P12/activity/positional producer modules remain unchanged by this correction. | Existing foundation regressions pass; dependency is explicitly recorded here. |

The C1 addition is a reviewer-requested product-contract correction, not adjustment
of observed chess expectations to make implementation pass. E06 retains all original
participants, losses, material and selected/excluded keys. The existing independent
P5 observation verifier checks the newly specified promotion payload/endpoints/type;
the separate scenario acceptance checks the actual digest sentence and references.

## 3. Concrete reviewer reproduction after correction

Input: `1nr4k/P7/8/8/8/8/8/4K3 w - - 0 1`, focus b8,
supplied line a7b8n, c8b8. Actual digest event excerpt:

```text
In the supplied line, at ply 1, white pawn on a7 captures black knight on b8.
In the supplied line, at ply 1, the piece initially on a7 moves from a7 to b8 and promotes to knight.
In the supplied line, at ply 2, black rook on c8 captures white knight on b8.
```

The promotion sentence has that step's TRANSITION plus before/after PIECE_HISTORY
refs for the physical piece initially on a7. This keeps the promoted victim type
linked to the original pawn before reporting its capture and focus loss.

## 4. Executed correction validation

Explicit PYTHONPATH points to this worktree's src; Python UTF-8 mode, bytecode and
pytest cache disabled. 2026-10-08 (Korea):

- **2,966 passed / 0 skipped / 0 failed**:
  tests/unit, tests/golden, tests/integration/python_chess.
- **2 passed / 0 skipped / 0 failed**, separately:
  tests/integration/test_analyze_move_slice.py with a Stockfish binary available
  through CALLIOPE_STOCKFISH_PATH or PATH in this environment.
- A2-specific coverage is now **100 tests** (88 previous + 12 regression cases).
  Original 45 independent corpus observation checks also pass.
- Changed Python Ruff check/format and git diff --check pass.
- No dedicated tests/integration/stockfish suite, new fuzz/CI run or new cost smoke
  was performed. The unchanged prior raw cost record is historical evidence.

Reproduce independently of Stockfish:

```text
python -X utf8 -m pytest -q -p no:cacheprovider tests/unit tests/golden tests/integration/python_chess
```

Optional real-binary slice (both tests skip without a configured/on-PATH binary):

```text
python -X utf8 -m pytest -q -p no:cacheprovider tests/integration/test_analyze_move_slice.py
```

## 5. Re-review scope

Confirm the chronological promotion digest obligation and source-linked physical
identity in E06 and the underpromotion/quiet-promotion cases. Review the corrected
normal-capture wording and closed king-only castling branch against the common
template catalog. L4/L6 remain nonblocking integration/refactor work. The correction
head was pushed to the same PR and independently accepted as recorded below.

## 6. Independent re-review closure

The reviewer independently re-reviewed PR #30 source head `672f162` and returned
READY. C1 is resolved; L1/L2/L3/L5 introduce no new issue. They executed 284 scenario
golden/position unit tests, changed Python Ruff check/format and git diff --check.
They did not repeat the full authored 2,966-test group. Their 30 independent trials
in promotion-heavy positions included 54 promotions and two en passant captures,
with zero mismatches. These are user-supplied independent results, not new authored
random verification claims.

L4 (render cost) and L6 (private shared-helper dependencies) remain nonblocking
follow-ups before public integration. Integration order: design PR #29, then
retarget implementation PR #30 to main. This closure update changes documentation
only; src and tests remain byte-for-byte identical to reviewed `672f162`.
