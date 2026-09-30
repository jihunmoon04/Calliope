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

See [docs/architecture.md](docs/architecture.md).
