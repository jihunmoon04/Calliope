> **LEGACY — FROZEN, NOT THE CURRENT DESIGN.** This document describes the MVP-era implementation preserved at tag `legacy-mvp-g0`. It is kept only as historical reference for the redesign; nothing in it is a current requirement or decision. Current design: [`docs/design/`](../design/README.md). Index: [`docs/README.md`](../README.md).

# Positional foundation: implementer review and correction

Status: READY. Independent re-review of
`de020c8edee3461365aa6adf7b433bebc8af0a0b` verified F1 and found no new issues.

Implementation baseline reviewed: `be4cb661bcfe65d0ef2da716ec7c8c158cfede9d`.
MVP baseline: `b0f99e453c0df52ee8cf19bf98ee22ff663ae6d6`.

## Findings and corrections

1. **Standalone transition boundary accepted incompatible same-id deltas.** Injecting
   a delta with a missing pawn correspondence, a wrong after-piece location, or a false
   material change retained the correct position ids but returned incorrect structural
   observations. These were fault-injected boundary failures, not a demonstrated defect
   in the normal P5 producer. Reproduction: all three new rejection tests failed on the
   reviewed head. Correction: reuse physical identity reconciliation, compare surviving
   pieces against the after facts, and independently reconcile material counts. A delta
   with the wrong mover is also rejected.
2. **Line consistency errors were untyped and accumulated material lacked endpoint
   reconciliation.** Disconnected transitions already failed, but with ValueError rather
   than the established delta incompatibility error. Correction: use
   IncompatibleBoardDeltaError for state inconsistency and compare accumulated material
   against initial/final pieces. Budget/input limit errors remain ValueError.

No P4/P5 implementation, identity helper, adapter, judgement, application composition,
schema, P8/P9 protocol, or P10-P12 code was modified. Corrections are restricted to the
new services, their tests and documentation.

## Verification

After corrections, the focused group passed: **111 passed / 0 failed**.

```bash
pytest -q tests/unit/services/position \
  tests/unit/services/explanation/test_piece_identity.py \
  tests/integration/python_chess \
  tests/unit/test_composition.py tests/unit/test_engine_facade.py
```

Coverage includes original structural/special-move tests, new fault-injected boundary
cases, and eight fixed-seed legal lines of 32 plies replayed against a separate board.
Every replayed frame checks piece locations/types/colors and identity coverage; final
counts independently check the aggregate result. This is not a different rules-engine
oracle: both paths use python-chess, but the checking path avoids the new services/P5.

The initial implementation also passed 2,024 related explanation/application tests.
That larger group was not repeated after these new-service-only corrections.
Changed Python files pass Ruff check/format; git diff --check passes.
Real Stockfish acceptance and full pytest were not run for this correction.

## Remaining scope and observations

- Features remain structural; no positional value/causality claim is produced.
- A supplied line is not necessarily forced or optimal, and its endpoint is not a
  settled-exchange proof. Draw adjudication remains out of scope.
- Some repeated P4/P5 observations remain. This is a measured optimization follow-on,
  not a reason to add an alternative rules or delta implementation now.
- Shared identity currently lives under explanation and BasePieceRef under bad_move.
  Reuse prevents divergent identity semantics; relocation to a neutral shared module
  can be considered separately with P8/P9 regression review, not silently folded into
  this additive feature branch.
  Until that relocation, the new services must remain outside `services.position`
  package exports because the explanation package imports position. Re-exporting the
  analyzers would introduce import-order-dependent cyclic loading (independent F2).

## Independent review F1 correction

Reviewed head: `2d03dbaabae5f6d3f0b669c51be9a7668e2e2464`.
Verdict supplied by the independent reviewer: READY_WITH_CORRECTIONS.

F1 correctly identified that complete piece sets/counts still allow permutation of
same-type identities. The first implementer correction checked accounting but did not
close geometric move correspondence. This follow-up adds a validation-only check:

- The mover pair must connect canonical UCI source/target pieces.
- Castling must connect the standard rook source/target and include CASTLING_ROOK.
- Every other surviving correspondence must keep the complete PieceRef unchanged.
- The transition tuple must exactly contain the required MOVE or PROMOTION plus any
  castling rook, in existing P5 canonical order. Missing/extra/wrong-kind transitions fail.

P5 remains the sole delta producer; no library access, legality search or second delta
engine was added. Existing adapter, identity helper, public pipeline and package exports
are unchanged.

Regression proof: all **13** new rejection cases fail on `2d03dba` when run against its
source in a detached temporary worktree. Cases cover stationary pawn swaps, mover rebinding,
false isolated/non-isolated pawn changes during a king move, absent transitions on a pawn
move/castling, and castling rook swaps/missing/wrong-kind transitions. The main F1 cases
are exercised through both standalone TransitionAnalyzer and LineAnalyzer.

Corrected focused group: **136 passed / 0 failed**. Positive controls include all four
standard castlings and all four promotion choices for each color. Changed Python Ruff
check/format and diff checks pass. No full pytest, real-engine suite or new CI was run.
Use `PYTHONPATH=<worktree>/src` to select the reviewed source explicitly when an editable
installation points at a different checkout; verify the imported module's `__file__`.

Independent F3 is addressed by distinguishing the historical 2,024-test run from the
current corrected checks. The subsequent independent re-review below closes verification.

## Independent re-review closure (2026-10-08)

Reviewed head: `de020c8edee3461365aa6adf7b433bebc8af0a0b`.
Verdict: **READY**, supplied by the independent reviewer.

- Focused group: 136 passed / 0 failed; worktree source selected with PYTHONPATH and
  confirmed through imported __file__.
- Changed-Python Ruff check/format and git diff --check passed.
- All 13 new rejection cases fail against `2d03dba`; the other 55 tests in the new test
  file pass there. All F1 probes reject on the corrected head; normal capture-promotion
  and stalemate endpoints still pass.
- Reviewer-reported fuzz: 400 fixed-seed legal games, 62,403 plies, zero false rejections.
  Special moves: 219 castlings, 133 en passant, 105 queen / 101 knight / 98 rook / 89 bishop
  promotions. The implementer did not rerun this external fuzz experiment.
- MVP-relative source delta remains the three new modules only; existing package exports,
  P5, identity helper and public pipeline are unchanged. F2/F3 documentation is verified.
- Full pytest, real-engine suites and new CI were not run. Standard chess only; Chess960
  is not supported. Temporary review worktrees were removed by the reviewer.

Review status is closed. The final status-document update is docs-only and must preserve
the reviewed source tree during integration.

## Independent reviewer brief

Fetch `expansion/positional-analysis-foundation` and pin its current head. Review the
complete diff against the MVP baseline above, not just the correction commit.

1. Verify definitions and bounded supplied-line semantics against
   positional-foundation.md. Check that geometric support cannot imply legal recapture
   or safety, and structure cannot imply move quality.
2. Review stationary pawn changes, physical correspondence, en passant, castling,
   promotion identity, and intermediate/end-of-line material semantics.
3. Challenge position/delta binding and both standalone-transition and line boundaries.
   Check normal cases and close counterexamples, not only test counts.
4. Verify no change to the existing public pipeline and assess the shared-identity
   dependency. Run the focused group above and changed-file Ruff checks. Do not create
   new CI or run full/real-engine suites unless a specific finding warrants it.
5. Report READY / READY_WITH_CORRECTIONS / NOT_READY with concrete findings, affected
   files, severity and tests. Do not merge or extend features as part of review.
