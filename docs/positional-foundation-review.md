# Positional foundation: implementer review and correction

Status: READY_FOR_INDEPENDENT_REVIEW, not an independent approval.

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
