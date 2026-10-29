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
| Agent: an MCP server for commentary agents (tools, the digest, the sentence check, stored AI commentary) | `src/calliope/agent/`, `tools/mcp/` |
| Viewer: board, evaluation, explanations; the analyse panel, the AI commentary panel, the MCP App | `viewer/` |
| Operator tools (a game explained, curve calibration, benchmarks, definitions, the performance acceptance) | `tools/` |

## Use

```sh
# one game, explained ply by ply, as text and as a result document
CALLIOPE_STOCKFISH_PATH=… PYTHONPATH=. python -m tools.explain_game game.pgn --json game.json

# the analysis server and the viewer
CALLIOPE_STOCKFISH_PATH=… PYTHONPATH=. python -m tools.serve --port 8765

# the MCP server for commentary agents, on stdio
CALLIOPE_STOCKFISH_PATH=… PYTHONPATH=. python -m tools.mcp
```

Both `tools/explain_game` and `tools/serve` survey the played positions ahead on a second
Stockfish process by default; `--prefetch-engines 0` keeps one.

See [`viewer/README.md`](viewer/README.md).

## History

The MVP implementation (schema 0.2 / 0.3) and its documents were removed; they are kept at the
tags `legacy-final` and `legacy-mvp-g0` ([`docs/README.md`](docs/README.md#history)).
