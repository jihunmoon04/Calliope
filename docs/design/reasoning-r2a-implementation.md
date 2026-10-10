# Reasoning — packet R2a implementation: hypotheses, verification, rounds, claim graph

Status: **rev. 2 — independent R2a review READY_WITH_CORRECTIONS applied (§4)**.
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
11. **Ids are recomputed**: a proposal whose id is not `hypothesis_id(h)`, or whose id another
    template already uses, is refused (`ReasoningError`), so no template order decides a winner.
12. **Limits count distinct refusals** per (limit, round): a proposal refused again in later passes
    counts once.
13. **Every malformed need surfaces as `ReasoningError`**, whether it fails at admission (the
    bound, the new-node count) or when issued; a target or premise naming an unknown node or line
    likewise.
14. **The verdict's searches stay within the target's** (R0-D §8.1.2): any verdict whose scope rests
    on a search its target does not name is a template bug.
15. **Satisfaction compares moves**: `members` turns every population into the UCI moves at `at`
    (`LEGAL` and `ENGINE_RANKED` from `status.legal_moves`), refusing references that are not moves
    at `at`; `EXISTS_*` witnesses must be members; `ALL_*` and `SELECTED_ALTERNATIVES` need the
    scope's moves to cover the target's (the played move removed for alternatives) and at least its
    strength (`ENGINE_REPORTED` ⊑ `ENGINE_RANKED` ⊑ `LEGAL`, the same search).
16. **Premise relations as R0-D §8.1.1 defines them**: `LINE_EXTENSION` is a proper prefix (same
    first index); `ALTERNATIVE_OF` needs sibling nodes, or two different lines from one node with
    different first moves; segments outside their line are refused.
17. **Closing reasons**, in order: refused → `NOT_COMPUTED(<type>)`; admitted earlier and still
    needed → `NEED_UNMET` (also in the last round); never admitted → `BUDGET`; else `ROUND_LIMIT`.
18. **Targets are well-formed**: line quantifiers take a `LineSegment`, node quantifiers a
    `NodeId`; INCONCLUSIVE reasons come from R0-D §9.2's closed set (or `NOT_COMPUTED(…)`).
19. **The round's single `ensure`** covers all requested nodes × all requested families — a
    superset of the requested pairs, within the node budget. `Analysis.rounds` lists the rounds
    that issued requests.

## 3. Evidence

| Check | Result |
| --- | --- |
| `tests/reasoning/test_runner.py` (test-only templates): a premise chain resolved in one round with `EXPLAINS`; a failed check → `ASSOCIATED_WITH`; a refutation → `QUALIFIES`; effective scope includes the premise's; template order shuffled → identical claims, relations and digest; refused premises (not SUPPORTED, wrong relation) → `ReasoningError`; derivation-depth and hypothesis-count limits recorded; `SCOPE_SHORT`; a `FamilyNeed` ensured and re-verified next round; a `LineNeed` extended with a deterministic label; `BUDGET`, `ROUND_LIMIT` (no request in the last round), `NEED_UNMET`; line needs admitted by searches and by nodes; origins and directions merged without changing the id; `EXISTS` witnesses and alternatives without the played move; `ALL_*` population order; a refused request → `REFUSED(EngineError)` and `NOT_COMPUTED(EngineError)`; ids identical across processes with different hash seeds; every premise relation; search provenance; a `DERIVED_FROM` cycle refused | 17 passed |
| `tests/reasoning/test_runner_contract.py` (review C9): each premise relation refused through the runner; an unaccepted scope; an INCONCLUSIVE premise; an accepted `ALTERNATIVE_OF` premise and `SAME_SEARCH` enforced; a wrong id; a later claim origin dropped; limit counts once per proposal, `max_fixpoint_passes`; satisfaction of `EXISTS_RESPONSE` over `LEGAL`, `SELECTED_ALTERNATIVES`, `PERSISTENCE` with a horizon; line needs grouped by expansion in canonical order; `NO_OP` then `NEED_UNMET`; an `ANALYSIS` line through P that would retry a skipped comparison is counted (BUDGET with no search left); cold vs warm store identical claims, relations, rounds and limits; the R0-D §8.6 examples encode | 16 passed |
| `tests/reasoning` (R1 + R2a), `tests/facts` without the 400-game fuzz (unchanged code), boundaries | 432 passed, 8 skipped (real Stockfish, gated) |
| `ruff check`, `ruff format` | pass |

## 4. Independent R2a review (rev. 1 `edc61b7`): READY_WITH_CORRECTIONS

| Finding | Resolution |
| --- | --- |
| C1 `ALTERNATIVE_OF` held between two segments of one line | §2.16 |
| C2 `LINE_EXTENSION` tested containment | §2.16 |
| C3 a malformed `LineNeed` escaped as a raw fact-engine error at admission | §2.13 |
| C4 ids never recomputed; cross-template collisions merged by registry order | §2.11 |
| C5 limit counts inflated by repeated passes | §2.12 |
| C6 `EXISTS_*` witnesses unchecked for `LEGAL` / `ENGINE_RANKED` | §2.15 |
| C7 `EXPLICIT` compared as references; subject not removed | §2.15 |
| C8 verdict searches not bounded by the target's | §2.14 |
| C9 missing obligation tests | `test_runner_contract.py`; the shuffle test also compares rounds and limits |
| N1 closing reason depended on `max_rounds` | §2.17 |
| N2 reasons not checked | §2.18 |
| N3 segment bounds | §2.16 |
| N4 `members` ignored `at` | §2.15 |
| N5 malformed targets raised `AssertionError` | §2.18 |
| N6 the ensure's cross product | §2.19 |
| N7 relation order by `repr`; rounds that issue nothing | relations ordered by canonical bytes; §2.19 |

## 5. Post-merge independent review of R2a (#59, `b723ce1`): NOT_READY

Applied in packet R2b (`reasoning-r2b-implementation.md` §4), since R2a was merged.

| Finding | Resolution |
| --- | --- |
| B1 a SUPPORTED verdict on a line or segment the view does not hold passed (a target without premises was never anchored; §2.13 above claimed it was) | `check_target` at proposal: the target's and context's node or segment exist and lie within their line, the population's search exists and is bound at a node target; `check_scope` anchors the scope and refuses `plies` beyond its segment (`ReasoningError`) |
| B2 `ENGINE_RANKED` accepted over any search | satisfaction requires every `ENGINE_RANKED` search of the scope and the target to be a `SURVEY` (R0-D §8.2), for every quantifier (R2b re-review C2); otherwise `SCOPE_SHORT` |
| C1 proposers did not see hypotheses still open | `ProposeContext.pending`: hypotheses proposed and not yet final, by `seq` (R0-D §29) |

