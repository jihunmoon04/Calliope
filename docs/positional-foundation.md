# Positional analysis foundation v1

This is an additive internal extension of the closed MVP at `b0f99e4`. It is not a
replacement for P4/P5 and does not change the public schema, composition, judgement,
P8/P9 protocols, P10 evidence eligibility, or P12 output. Independent re-review returned
READY at `de020c8edee3461365aa6adf7b433bebc8af0a0b`; F1 is corrected and verified.

## Existing components reused

| Foundation | MVP component | New responsibility |
| --- | --- | --- |
| PositionAnalyzer | P4 PositionFactExtractor / PositionFacts | Attach versioned structural features |
| TransitionAnalyzer | P5 BoardDeltaAnalyzer / BoardDelta | Compare structural features through physical-piece correspondence |
| LineAnalyzer | P5 replay and existing BasePieceIdentityMap | Expose bounded supplied-line observations and piece histories |

Existing P8/P9 already replay selected lines and track identity for their own protocols.
The new service makes a general supplied-line result without changing those protocols.
There is no new board implementation or Stockfish search implementation.

## Definitions: positional_v1

- Isolated pawn: no friendly pawn anywhere on either adjacent file.
- Doubled pawn: at least two friendly pawns on its file; every pawn on that file is marked.
- Passed pawn: no enemy pawn strictly ahead on its own or adjacent files, in its color's
  forward direction. Same-rank/behind pawns do not disqualify it. This is structural,
  not a claim that advancement is safe, promotion is possible, or en passant is impossible.
- Pawn supporters: friendly pawns geometrically attacking its square. Pinned supporters
  are included; this does not assert a legal recapture.
- Open file: no pawns of either color.
- Semi-open file for a color: no own pawns, at least one opposing pawn. Open files are
  excluded. File state says nothing about rook access or whether occupying it is beneficial.

P4 attack/defense/capture/material/check observations remain accessible as `analysis.facts`.
No heuristic weights or centipawn values are assigned to these features.

## Transition semantics

The first move is normalized through ChessRulesPort; caller SAN is not trusted. P5 then
reconciles the move. Before/after ids, mover and canonical move identity must agree.
The standalone transition boundary also checks physical-piece accounting against both
observed states and material changes against the actual piece counts. Matching position
ids alone do not make incompatible intermediate data acceptable.
Correspondences are also checked against the canonical move: the mover must go from
its source to its target; a castling rook must use its standard rook endpoints; every
other surviving piece must be unchanged. The exact MOVE/PROMOTION and CASTLING_ROOK
transitions are required. This is validation of P5 output, not a second delta producer.

Pawn features are compared through P5 physical-piece correspondences, including supporter
identity. Changing a pawn's square alone is not an improvement or a structural feature
change. Stationary pawns can change features when other pawns move or are captured.
An absent after-pawn feature can mean capture or promotion; BoardDelta distinguishes them.
Existing retained attacks/defenses remain governed by P5 semantics.

## Supplied-line semantics

- Default maximum 64 plies, caller-selectable integer limit 1..256. Over-budget input is
  rejected before observation; no silent truncation.
- Every move is revalidated in its actual position. Illegal later moves raise; no partial
  result is returned. The service keeps no mutable board or persistent analysis state.
- Initial pieces are tracked at every frame, including captures, castling and promotion.
  A pawn retains its initial identity after promotion. `None` in its history means capture.
- Aggregate material changes are counts per color/type. Promotion is a pawn decrease and
  promoted-piece increase, not necessarily a material loss. These are not SEE scores.
  The accumulated changes are cross-checked against initial/final piece counts.
- `provided_line_end` only means the supplied line ended. `checkmate` is an exact final
  board observation. Neither implies all opposing replies were explored.
- No automatic repetition/draw adjudication, settled-exchange declaration, strategic
  valuation, causal proof, best-response proof, or forced-line claim is produced.

## Internal usage

```python
from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.chess import ChessMove
from calliope.services.position import (
    PositionFactExtractor, BoardDeltaAnalyzer,
)
from calliope.services.position.positional import PositionAnalyzer, TransitionAnalyzer
from calliope.services.position.line import LineAnalyzer

rules = PythonChessAdapter()
facts = PositionFactExtractor(rules)
positions = PositionAnalyzer(facts)
transitions = TransitionAnalyzer(rules, positions, BoardDeltaAnalyzer(rules, facts))
lines = LineAnalyzer(transitions)

position = rules.position_from_fen(
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
)
result = lines.analyze(
    position,
    tuple(ChessMove(m) for m in ("e2e4", "d7d5", "e4d5", "d8d5")),
)
# Both sides lose one pawn in this particular line. It does not prove optimal play.
```

These are internal services, not a newly supported external facade/tool surface.
Keep these services out of `services.position.__init__` exports until shared identity is
relocated to a neutral module. It currently lives under `services.explanation`, whose
package imports `services.position`; re-exporting creates an import-order-dependent cycle.

## Efficiency and next scope

V1 deliberately recalculates facts through existing P4/P5 services instead of adding a
second board/delta implementation. This repeats some observations; request-local caching
or a reviewed P5 facts-reuse seam can follow measured need. There are no engine calls.
No claim about production speed or engine-budget savings is made by this implementation.

The foundation is usable now for pawn/file changes and supplied-line events. It is not the
entire future positional analyzer: mobility with precise legality/safety definitions,
explicit slider ray/blocker data, king-zone features, scenario generation, adversarial
response search, evidence/claim integration and explanation selection remain follow-ons.

## Verification

Tests cover structural definitions and counterexamples, color/rank mirroring, pinned pawn
support, moving vs stationary pawn feature changes, castling normalization, en passant,
promotion identity, recaptures and aggregate counts, empty/mating lines, strict budgets,
illegal later moves, and incompatible delta binding. Existing P4/P5 and identity tests are
also rerun. No Stockfish is required to verify this deterministic foundation.

Current F1-corrected validation: **136 focused regression tests passed**, including eight
deterministic 32-ply legal-line replays, all standard castlings and both colors' promotion
choices. The 13 new F1 rejection cases all failed against the reviewed `2d03dba` head in a
separate worktree, with PYTHONPATH explicitly selecting that worktree's source.
Changed Python files pass Ruff check/format. No full pytest, real-engine suite or new CI.

Historical checks: the initial implementation passed 2,024 related tests; this larger
group was not repeated after corrections. Earlier boundary corrections passed 111 focused
tests. The initial 64-ply knight-shuffle smoke took approximately 0.19 seconds; it was not
a production benchmark and was not repeated after extra validation was added.

Findings, corrections and external-review status are recorded in
[positional-foundation-review.md](positional-foundation-review.md).

The independent reviewer also reported 400 fixed-seed legal games / 62,403 plies with no
false rejection, including 219 castlings, 133 en passant captures and 393 promotions
(105 queen, 101 knight, 98 rook, 89 bishop). This fuzz result was supplied in the review;
it was not independently rerun by the implementer. Full pytest, real-engine suites and
new CI remain outside this integration's validation scope.
