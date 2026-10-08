# Calliope

Calliope is an evidence-first chess commentary engine.

1. **Stockfish judges move quality.**
2. **Deterministic chess analysis explains what changed and what can be proven.**
3. **Counterfactual probes verify candidate explanations.**
4. **P10/P11 retain only validated claims and choose a minimal explanation.**
5. **P12 renders deterministic commentary with no LLM dependency.**
6. **A future P13 LLM verbalizer is optional and may only rephrase already-validated semantics.**

## Architectural invariant

```text
Position + Move
      |
      v
EngineAnalysis --> MoveJudgement
      |
      +------------------+
      |                  |
      v                  v
Board Delta        Counterfactual Probes
      |                  |
      +---------+--------+
                v
             Evidence
                v
        ExplanationClaim
                v
   relation-free ExplanationGraph
                v
      ExplanationSelection
                v
 DeterministicExplanationRenderer
                v
      schema 0.2 commentary

        [optional future P13]
                |
                v
      constrained LLM verbalizer
                |
       validate / fallback to P12
```

The deterministic P12 path is complete without an LLM. P13, if implemented later, is presentation
only and cannot become a source of chess truth.

See [docs/architecture.md](docs/architecture.md).\n\nMVP delivery plan: [docs/mvp-implementation-plan.md](docs/mvp-implementation-plan.md).


## One engine, multiple integrations

Calliope exposes one canonical public facade: `CalliopeEngine`.

`analyze_move()` is the implemented deterministic MVP path. `analyze_game()` is reserved in
the facade but currently raises `FeatureUnavailableError`; PGN/game analysis is deferred.

External callers do not orchestrate internal analyzers directly. Python applications, CLIs,
HTTP services, MCP servers, and agent tools/skills all adapt their inputs to the same engine
requests and receive the same stable result contracts.

```text
agent skill/tool ─┐
MCP / HTTP ───────┼─> CalliopeEngine ─> canonical analysis pipeline
CLI ──────────────┤
Python library ───┘
```

This preserves one source of chess truth regardless of how the engine is invoked.
