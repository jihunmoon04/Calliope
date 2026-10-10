# Reasoning — packet R2a implementation: hypotheses, verification, rounds, claim graph

Status: **rev. 1 — awaiting independent R2a review**.
Date: 2026-10-10. Design: [`reasoning-r0-design.md`](reasoning-r0-design.md) rev. 10 (R0-D §6.2–§6.4,
§8–§10, §18.4–§18.6). Base: `main @ 919df2d` (R1 merged #57; R2-D rev. 11 merged #58).

R2 is split like F4: **R2a** (this packet) is the machinery, tested with test-only templates;
**R2b** is catalogue v1 (the 21 templates of R2-D) and the labels (`label_v1`: GREAT, MISS).

## 1. Scope delivered

| Module | Content |
| --- | --- |
| `reasoning/hypotheses.py` | the hypothesis contract (R0-D §8.1–§8.3): `ClaimRole`, `Direction`, `Quantifier`, `Population` / `PopulationKind`, `VerificationTarget`, `NodeContext` / `LineContext` / `SpanContext`, `Basis`, `PremiseRelation`, `SearchCompat`, `ScopeRequirement`, `PremiseUse`, `Hypothesis`, `RelationKind`, `RelationDecl`, `ProposeContext`, the `HypothesisTemplate` protocol, and `hypothesis(...)`, which computes the id |
| `reasoning/verification.py` | `Verdict`, `VerdictStatus`, `ProofScope`, `CausalCheck`, `Claim` (§9, §10.1); target satisfaction `satisfies` (§9.4: witnesses for `EXISTS_*`, the played move excluded from alternatives, population order for `ALL_*`, explicit lists, horizons); premise checks `check_premises` — SUPPORTED, `accepted` by the requirement, `relation_holds` (§8.1.1), `search_compatible` (§8.1.2); `effective_scope` (a set); `check_scope` (SUPPORTED → `INCONCLUSIVE(SCOPE_SHORT)` when the scope misses the target) |
| `reasoning/needs.py` | `FamilyNeed`, `LineNeed`, the canonical need order, deterministic `ANALYSIS` labels (§6.2) |
| `reasoning/graph.py` | relations (§10.2): `DERIVED_FROM` to origins and premises with a DAG check; semantic edges only from a SUPPORTED claim to its own premise with the declared kind, at the strength its checks reach (`CAUSES` ← `COUNTERFACTUAL`, `EXPLAINS` ← `REALIZED`, else `ASSOCIATED_WITH`); `QUALIFIES` from an INCONCLUSIVE or REFUTED claim to its premises |
| `reasoning/runner.py` | `Reasoner.analyse`: round 0 (R1), then rounds (§6.3): the propose / verify fixpoint per round with the work limits, need collection, admission (§6.4), one `ensure` and one `extend` per expansion, request outcomes, closing verdicts (`NEED_UNMET`, `BUDGET`, `ROUND_LIMIT`, `NOT_COMPUTED(<error>)`); `Analysis`, `Round`, `RequestOutcome`, `LimitReached` |
| `reasoning/encoding.py` | the closed reasoning type registry over the fact registry, `canonical_bytes` (F5's `fact_encoding_v1`); `register` for R2b's finding types |
| `facts/__init__.py` | exports `canonical`, `encode`, `type_registry` and `REGISTRY`, so reasoning encodes through the fact engine's public names |

## 2. Implementation decisions within the design

1. **The runner enforces the contract**, not the templates (R0-D §8.1): a premise that is not
   SUPPORTED, not accepted by its requirement, not in its declared relation, or not of the declared
   search provenance raises `ReasoningError` at proposal; a SUPPORTED verdict whose scope does not
   satisfy the target is turned into `INCONCLUSIVE(SCOPE_SHORT)`.
2. **Proposals are admitted per pass in (derivation depth, id) order** and numbered `seq` in that
   order, so the result does not depend on template registry order (R0-D §6.3, §10.3). Work limits
   (`max_derivation_depth`, `max_hypotheses`, `max_fixpoint_passes`) refuse proposals in that
   order and are recorded in `Analysis.limits_reached`.
3. **Re-proposals merge provenance**: origins (a canonically sorted union, claim origins only if
   proposed earlier) and directions; the id is unchanged (R0-D §8.3).
4. **Each open hypothesis is verified at most once per view**; a NEEDS_EVIDENCE verdict waits for
   the next round's view.
5. **Admission** (R0-D §6.4), needs in canonical order:
   - `FamilyNeed`: distinct `ensure` nodes after round 0 ≤ `max_ensure_nodes`;
   - `LineNeed`: new nodes (moves not yet in the tree) ≤ `max_nodes − |nodes|`, and the **sum** of
     `planned_search_bound` over the round's extends ≤ the remaining searches; searches used are
     distinct search ids first bound after `rev_0` (store hits included).
6. **Closing order for an open verdict**: a refused request → `NOT_COMPUTED(<error type>)` (checked
   first, so a re-raised refused need is not `NEED_UNMET`); a need admitted earlier and raised
   again → `NEED_UNMET`; a need never admitted → `BUDGET`; rounds exhausted → `ROUND_LIMIT`.
7. **Request failures**: `InvalidRequestError` and `IllegalMoveError` from a later-round request mean
   a template raised a malformed need → `ReasoningError`; any other `FactEngineError` is recorded as
   `REFUSED(<type>)` (R0-D §15).
8. **Search provenance reads every search a scope rests on**: its listed searches and the searches
   named by its population and its line (`scope_searches`), so a scope that forgets to list a
   search cannot pass `SAME_SEARCH` vacuously.
9. **`max_ensure_nodes = 0`** is valid (no `ensure` after round 0), like `max_extra_searches = 0`;
   recorded in R0-D §27.
10. **Observations after round 0**: `obs_v1` has no incremental kinds (R2-D §2), so the runner
    reads round 0's observations in every round; the hook for incremental kinds comes with a
    catalogue that needs them.

## 3. Evidence

| Check | Result |
| --- | --- |
| `tests/reasoning/test_runner.py` (test-only templates): a premise chain resolved in one round with `EXPLAINS`; a failed check → `ASSOCIATED_WITH`; a refutation → `QUALIFIES`; effective scope includes the premise's; template order shuffled → identical claims, relations and digest; refused premises (not SUPPORTED, wrong relation) → `ReasoningError`; derivation-depth and hypothesis-count limits recorded; `SCOPE_SHORT`; a `FamilyNeed` ensured and re-verified next round; a `LineNeed` extended with a deterministic label; `BUDGET`, `ROUND_LIMIT` (no request in the last round), `NEED_UNMET`; line needs admitted by searches and by nodes; origins and directions merged without changing the id; `EXISTS` witnesses and alternatives without the played move; `ALL_*` population order; a refused request → `REFUSED(EngineError)` and `NOT_COMPUTED(EngineError)`; ids identical across processes with different hash seeds; every premise relation; search provenance; a `DERIVED_FROM` cycle refused | 17 passed |
| `tests/reasoning` (R1 + R2a), `tests/facts` without the 400-game fuzz (unchanged code), boundaries | 416 passed, 8 skipped (real Stockfish, gated) |
| `ruff check`, `ruff format` | pass |
