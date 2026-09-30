# Calliope

Calliope is a chess commentary engine designed around a strict separation of concerns:

1. **Stockfish judges move quality.**
2. **Deterministic chess analysis explains what changed and what can be proven.**
3. **Counterfactual probes verify candidate explanations.**
4. **An LLM verbalizes only pre-validated claims; it does not invent chess facts.**

The project goal is not to make an LLM reason about chess from raw positions. The goal is to build a reliable, inspectable explanation engine whose output can be rendered by an LLM without introducing unsupported claims.

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
Position/Board Delta   Counterfactual Probes
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

## Initial scope

The first implementation should prioritize explanations that can be verified strongly:

- legal state and move effects
- attacks and defenses
- material changes
- checks, captures, mate and promotion
- hanging pieces
- tactical motifs
- created and removed threats
- Stockfish MultiPV comparisons
- counterfactual / refutation analysis
- move-quality judgement and forcedness
- evidence-backed explanation claims

Long-horizon strategic interpretation, player intent, style, and other speculative explanations are intentionally deferred.

See [docs/architecture.md](docs/architecture.md) for the initial architecture.
