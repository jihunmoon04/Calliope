# Core Chess and Engine Models

This document freezes the first concrete domain contracts used beneath `CalliopeEngine`.

## Position identity

`PositionSnapshot` is immutable. Its `position_id` is derived from an adapter-normalized full
FEN using SHA-256. The full FEN is intentionally included because draw-state clocks can affect
the legal game state.

The python-chess adapter owns parsing, legality checks, and FEN normalization. Domain objects do
not import python-chess.

## Move identity

`ChessMove.uci` is canonical. SAN is optional presentation because SAN depends on the source
position.

`MoveRecord` links immutable before/after position ids.

## Score convention

All centipawn scores are normalized to **White POV**:

- positive: better for White
- negative: better for Black

Forced mate is not represented with an ambiguous signed integer. It uses:

```text
MateScore(
  winner = WHITE | BLACK,
  moves = non-negative distance
)
```

Consumers can explicitly project either score to a requested color.

## WDL convention

`WDL` stores normalized White-win / draw / Black-win probabilities summing to 1.0. Expected
score is derived explicitly for a requested color.

## EngineAnalysis

An analysis belongs to exactly one immutable `position_id`, engine identity, and engine
settings. MultiPV lines have unique ranks and must contain rank 1.

An `EngineLine` records:

- rank
- first move
- canonical score
- optional WDL
- PV
- depth / seldepth / nodes

`EngineStability` is kept separate from evaluation itself so later repeated-depth sampling can
express whether a best move or score has settled.

## MoveJudgement

`MoveJudgement` is deliberately explanation-free.

It records:

- mover
- played move
- best move
- quality class
- played rank
- best and played score
- centipawn loss when meaningful
- expected-score loss when available
- forcedness

The future `MoveJudge` service derives it from normalized Stockfish observations. Tactical or
positional analyzers are not allowed to change the underlying engine judgement.

## Forcedness

Move quality and forcedness are orthogonal.

A move may be best while many alternatives are equivalent, or best because every alternative
fails. `Forcedness` therefore records a separate level plus evidence-friendly statistics such
as acceptable-move count and best-to-second centipawn gap.

Threshold policy is intentionally not frozen in these value models. It belongs in the future
`MoveJudge` policy/service and can be calibrated independently.
