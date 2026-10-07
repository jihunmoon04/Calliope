# Integration Contract

Calliope is one chess-analysis engine with multiple transport adapters.

## Canonical Python API

```python
from calliope import AnalyzeMoveRequest, CalliopeEngine

result = engine.analyze_move(
    AnalyzeMoveRequest(
        fen="...",
        move_uci="f3e5",
    )
)
```

Concrete engine construction will be supplied by the composition root once the Stockfish and
python-chess adapters are implemented.

## Agent tool / skill

An external agent should treat Calliope as an authoritative chess-analysis tool, not as a prompt
template.

Recommended tool operations:

```text
analyze_move
  input:
    fen: string
    move_uci: string
    options?: object

analyze_game
  input:
    pgn: string
    options?: object
```

The tool adapter converts transport JSON into Calliope public request DTOs, invokes
`CalliopeEngine`, then serializes the public result DTOs.

The agent must not independently add chess facts that are absent from the returned verified
claims.

## Why one facade?

Keeping one engine facade guarantees that Python users, UI clients, MCP servers, HTTP APIs, and
agents share:

- identical Stockfish judgement policy;
- identical deterministic analysis;
- identical counterfactual verification;
- identical claim-validation rules;
- identical commentary safety policy.

Integrations differ only in transport and presentation.

## Failure semantics

The structured analysis is primary.

If optional LLM verbalization fails, the engine should still return the verified structured
analysis whenever possible. A transport adapter must not convert commentary failure into a false
chess result.

## Versioning

Every public result includes `schema_version`. Breaking transport-contract changes require a
schema-version change even when internal domain models can evolve freely.
