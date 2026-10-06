# Calliope

Calliope is an evidence-first chess commentary engine.

1. **Stockfish judges move quality.**
2. **Deterministic chess analysis explains what changed and what can be proven.**
3. **Counterfactual probes verify candidate explanations.**
4. **An LLM verbalizes only pre-validated claims; it does not invent chess facts.**

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
        ExplanationGraph
                v
      ExplanationSelection
                v
      VerbalizationRequest
                v
               LLM
```

The LLM is the final presentation layer only.

See [docs/architecture.md](docs/architecture.md).\n\nMVP delivery plan: [docs/mvp-implementation-plan.md](docs/mvp-implementation-plan.md).


## One engine, multiple integrations

Calliope exposes one canonical public facade: `CalliopeEngine`.

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
