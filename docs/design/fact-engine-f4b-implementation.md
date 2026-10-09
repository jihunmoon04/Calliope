# Fact engine — packet F4b implementation: engine work in the tree

Status: **rev. 1 — awaiting independent F4b review**.
Date: 2026-10-09. Design: [`fact-engine-f4-design.md`](fact-engine-f4-design.md) rev. 3
(F4-D §6–§8a, §9.2, §9.3 items 5–6). Base: `main @ 4ad53aa` (F4-D and F4a merged).

## 1. Scope delivered

| Module | Content |
| --- | --- |
| `request.py` | `ExpansionSpec` (`comparison` and `attach_lines` require `survey`), `FULL`, `NONE`, `Defaults`; `RoleKind.ROOT`; `POLICY_ROLE_KINDS`; `OpenRequest.engine` / `root_expansion` / `defaults`; `ExtendRequest.expansion`; `SessionBudget.max_searches` / `deadline_per_request_ms` |
| `tree.py` | `RoleEntry` with `expansion` (input roles) and `anchor` / `search_id` / `rank` (`ENGINE` roles); `EngineLineId`; `LineRecord.unattached_plies`; `LineEnd.PV_END` / `BUDGET_LIMIT`; `NodeSearch`, `BasisEntry`, `SearchScore`, `NOT_IN_BASIS`, `order`; the store and pending revision hold searches, bindings, basis entries, attachments and runtimes. `TreeView` adds `has_input_role`, `effective_expansion`, `search`, `searches`, `basis` (rows 1–2 derived), `child_score`, `attached`, `runtimes`, and the `"tier"` reading. `RevisionDelta` adds the engine manifest (§8a) |
| `engine_work.py` | `EngineWork`: one request's planned work in F4-D §6.3 order. Covers the survey pre-check, surveys, policy comparisons with skips and retries, `ANALYSIS` searches, basis entries by the ordered table, and attach-once engine lines in the fixed order |
| `engine.py` | `FactEngine(families, engine=port, store=store)`; the session binds profile, identity and a `Searcher` at `open`; the `ROOT` role; per-role expansions; role gain at every request node (start nodes included); engine-only nodes get the tier; refused requests discard the searcher's pending work |
| `search/store.py` | `Searcher.cached`, used by the pre-check and the skip rules |
| `errors.py` | `CrossSearchError` |

## 2. Implementation decisions within the design

1. **The survey pre-check** counts surveys that neither the session cache nor the store can
   answer. The design counts "one per request node that becomes searchable without a survey";
   counting only real engine calls is the same rule under "store hits are free" (Q4), and stays
   deterministic for a given store.
2. **Expansions only with an engine.** In a session without an engine, role entries carry no
   expansion, no `ROOT` role is written, and trees are exactly as in F1–F3.
3. **A continued line's start node** receives the request's role entry again when the session
   has an engine, so its effective expansion includes the new request. Identical entries are not
   duplicated.
4. **Role gain** resolves the eager set at every request node; present records are skipped, so
   this costs nothing on nodes that already have them. It covers engine-only nodes on a line
   and at its start.
5. **Port rebinding.** `extend` on another `FactEngine` whose port has the session's identity
   uses that engine's port; a different identity or no port is refused (F4-D §6.1).
6. **Engine lines** are `LineRecord`s with `first_index = 0` and `nodes` starting at the anchor.
   A line skipped by the deadline has `nodes = (anchor,)` and `unattached_plies = len(pv)`.
7. **Bindings** are unique per (node, search). A search record is stored once, at the revision
   that first bound it; `TreeView.search` reads it at that revision.
8. **`ANALYSIS` attachment.** `ANALYSIS`-kind searches are attached only by the request that
   bound them, and only if that request's expansion has `attach_lines`. Later policy
   attachments skip them (F4-D §6.3 step 4).
9. **Basis fallback.** If a node needs a comparison that neither ran nor was skipped in this
   request, its basis reads `NOT_COMPUTED(BUDGET)`. By §6.3 this cannot happen for a request
   node; the branch is a guard.

## 3. Not in F4b

Persistence of the store, tape replay, digest and tree loading (F5).

## 4. Evidence

| Check | Result |
| --- | --- |
| `tests/facts/search/test_tree_engine.py` (24 tests, synthetic engine) | pass |
| `tests/facts/search/test_stockfish_acceptance.py`, full-game test (real Stockfish 19) | pass |
| `tests/facts/search/engine_auditor.py` on the synthetic trees and the real game | pass |
| `tests/facts` (F1–F4b, with the 400-game fuzz and real-Stockfish acceptance) and `tests/test_package_boundaries.py` | 301 passed in 10 min 18 s |
| legacy `tests/unit`, `tests/golden` | 3,163 passed |
| `ruff check`, `ruff format` | pass |

### The synthetic engine (`tests/facts/search/synthetic.py`)

It ranks the legal root moves, or the restriction, by UCI text, and scores them 100, 90, 80, …
It continues every PV with the first legal reply in UCI order. Listed positions answer as
`TIME`-stopped searches. That makes every policy decision predictable: which moves are in the
survey, when a comparison is needed, where lines end.

### F4-D §9.2 obligations

| Obligation | Tests |
| --- | --- |
| 1 policy: root at `open`; survey order; effective expansions incl. the `NONE` example; invalid expansions; comparison trigger, set, re-comparison; `ANALYSIS` children outside the set; `ANALYSIS` searches (one per node, end node excluded); attachment after an expansion upgrade; no duplicate attachment; basis rows incl. precedence; `NOT_IN_BASIS`; `order` refusing cross-search operands; R2-C1 | `test_root_is_surveyed_at_open_under_its_role`, `test_surveys_run_in_line_order_and_only_at_request_nodes`, `test_effective_expansion_union_example`, `test_invalid_expansions_and_missing_analysis_expansion_are_refused`, `test_comparison_trigger_set_and_recomparison`, `test_analysis_children_never_enter_the_comparison_set_and_analysis_searches`, `test_attachment_after_an_expansion_upgrade`, `test_basis_rows_and_scores`, `test_analysis_comparison_never_changes_a_played_basis` |
| 2 zero engine calls: terminal, `after_terminal`, engine-only nodes; `engine=None`; `ensure` | `test_terminal_nodes_are_not_applicable_and_never_searched`, `test_after_terminal_nodes_are_never_searched`, `test_no_engine_session_has_no_root_role_and_no_calls`, `test_ensure_never_calls_the_engine`, `test_tier_and_role_gain` |
| 3 engine lines: roles and indexes, shared edges, stops at terminal nodes with `unattached_plies`, `BUDGET_LIMIT` | `test_engine_lines_roles_shared_edges_and_transpositions`, `test_attachment_stops_at_terminal_nodes_and_counts_unattached_plies`, `test_budget_limit_on_nodes_cuts_lines` |
| 4 tiers and role gain, start nodes included | `test_tier_and_role_gain` |
| 5 budget: survey pre-check; comparisons skipped; deadline; engine failure | `test_survey_precheck_refuses_and_commits_nothing`, `test_comparisons_skipped_for_budget_and_retried`, `test_deadline_skips_comparisons_and_lines`, `test_engine_failure_commits_nothing` |
| 6 session binding; two trees on one port and store from threads | `test_session_is_bound_to_its_engine`, `test_cold_and_warm_store_give_equal_trees_and_threads_share_safely` |
| 7 auditor | `engine_auditor.audit_engine_tree` in the tests above and the real game |
| 8 cold vs warm equivalence | `test_cold_and_warm_store_give_equal_trees_and_threads_share_safely`; real game |
| manifest §8a | `test_manifest_records_engine_work` |

### Cost (F4-D §9.3 item 6; real Stockfish 19, aarch64, 2 CPUs)

The Opera game's first 20 plies, built cold (empty store), then warm:

| Measure | Value |
| --- | --- |
| Input nodes | 21 |
| Engine searches | 23: 21 surveys and 2 comparisons |
| Median search | 488 ms |
| Engine-only nodes attached | 1,264, about 60 per input node (A0 §7.5 measured about 48 on Stockfish 17) |
| Cold build | 13.1 s |
| Warm build (every search from the store) | 2.0 s, i.e. about 1.6 ms per node for the families |
