# Calliope

Calliope is an evidence-first chess commentary engine: it explains a chess move from facts it
can prove (rules, versioned definitions, attested engine reports) and says nothing it cannot.

## Status

Calliope is built as composable blocks with one role each, each designed and reviewed in a
packet ([`docs/design/`](docs/design/README.md); start with the
[status and roadmap](docs/design/redesign-status-and-roadmap.md)).

| Block | Where |
| --- | --- |
| Fact engine: positions, lines and engine reports as one tree of facts | `src/calliope/facts/` |
| Reasoning: grades, labels, claims, the rendered explanation | `src/calliope/reasoning/` |
| Results: the game document `calliope_result_v1` | `src/calliope/results/` |
| Local analysis server | `src/calliope/server/`, `tools/serve/` |
| Viewer: board, evaluation, explanations; the analyse panel | `viewer/` |
| Operator tools (a game explained, curve calibration, benchmarks) | `tools/` |

## Use

```sh
# one game, explained ply by ply, as text and as a result document
CALLIOPE_STOCKFISH_PATH=… PYTHONPATH=. python -m tools.explain_game game.pgn --json game.json

# the analysis server and the viewer
CALLIOPE_STOCKFISH_PATH=… PYTHONPATH=. python -m tools.serve --port 8765
```

See [`viewer/README.md`](viewer/README.md).

## History

The MVP implementation (schema 0.2 / 0.3) and its documents were removed; they are kept at the
tags `legacy-final` and `legacy-mvp-g0` ([`docs/README.md`](docs/README.md#history)).
