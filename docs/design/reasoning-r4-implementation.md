# Reasoning — packet R4 implementation: `claim_graph_v1`, replay, the corpus, `explain_game`

Status: **rev. 3 — R4 review (B1, B2) and re-review (B2 remainder) applied (§5, §6); awaiting re-review**.
Date: 2026-10-12. Design: [`reasoning-r4-design.md`](reasoning-r4-design.md) rev. 3 (R4-D, final
re-review READY, #75). Base: `main @ d708945`.

## 1. Scope delivered

| Module | Content |
| --- | --- |
| `reasoning/storage.py` (new) | `save(analysis, rendered) -> (tree_bytes, graph_bytes)` and `load(fact_engine, tree_bytes, graph_bytes, *, templates, grading_build)`. Also `ReplayTree` (revision cursor), `ReplayFactEngine` and `REFUSALS`. |
| `reasoning/build.py` (new) | `ReasoningBuild` and `reasoning_build(families, templates, grading_build)` (R4-D §2.1) |
| `reasoning/runner.py` | `Reasoner.build()`; `Analysis.build`, last field, set by `analyse` |
| `reasoning/render/__init__.py` | `plan_analysis(analysis)`, the one plan path (R4-D §2.3); `explain` uses it |
| `reasoning/encoding.py` | registry: `AnalysisRequest`, `ReasoningBudget`, `RequestOutcome`, `Round`, `LimitReached`, `ReasoningBuild`, `Segment`, `RenderedExplanation` |
| `facts/engine.py` | `FactEngine.normalize_open`, `FactEngine.normalize(view, request)`, `plan_lines_at(view, request)` (one core with `plan_lines`), `FactEngine.families` |
| `facts/planning.py` | `planned_search_bound` reads its view only (§2.2) |
| `facts/storage.py`, `facts/__init__.py` | `decode`; public `save_tree`, `decode`, `build_identity`, `BuildIdentity`, `types_digest`, `type_table`, `StoredTreeError` and the engine errors |
| `tests/reasoning/corpus/*.toml` (new) | the twelve cases of R4-D §4.2 |
| `tools/explain_game/` (new) | the end-to-end tool of R4-D §5 |
| `docs/design` | R0-D §33, F5-D §14 |

## 2. Implementation decisions and deviations
1. **Fact-engine changes beyond `normalize`.** R4-D §3.5 named `normalize` as the one change to
   `calliope.facts`. Implementing replay needed three more, all recorded in F5-D §14:
   - `plan_lines_at(view, request)`, so `normalize` reads line heads as of the view (the final
     review's note);
   - **`planned_search_bound` reads its view only** (§2.2);
   - public names for storage, the build identity and refusals, and `FactEngine.families`.
     `calliope.reasoning` may import only the public fact engine.
2. **`planned_search_bound` at a cursor.**
   - **The failure.** The first replay failed: the runner computes this bound on its live view,
     which during replay is the cursor's. The function required the tree's head and read the live
     line heads.
   - **The fix.** It now plans with `plan_lines_at` and accepts a pinned view.
   - **Test.** Its old test ("a stale view is refused") became "a pinned view gives the bound as
     of that revision". It continues a line whose live head would make the move illegal; with
     `plan_lines` restored, the test fails.
3. **`NO_OP` in replay.** A call is `NO_OP` when every requested `(family, node)` record is
   visible at the cursor (`TreeView.fact_entry`). The real `ensure` commits nothing exactly then:
   dependencies of a present record are present.
4. **Refusals.** `REFUSALS` maps the recorded type name to the exported fact-engine error
   classes: `FactEngineError`, `BudgetExceededError`, `CrossSearchError`, `EngineError`,
   `EngineOutputError` and `EngineUnsupportedError`. An unknown name refuses the load.
5. **Matching a call.**
   - It is a revision when its normal form equals the log's next entry, else `NO_OP` when it
     qualifies, else the next recorded refusal when that refusal's request equals the call.
   - The whole re-derived document is then compared byte for byte. So the recorded outcome
     kinds are also checked: rounds are part of the document.
6. **`Analysis.build` defaults to `None`** so existing constructions stay valid. `save` refuses an
   analysis without a build.
7. **The document's fields** are a fixed tuple (`FIELDS`). It is serialized like `fact_tree_v1`:
   compact ASCII JSON. A load refuses a document whose field list differs.
8. **`tools/explain_game`'s grading.**
   - **Pool:** chess.com when the `Site` header names it, else Lichess.
   - **Time class:** chess.com's `600` form, or Lichess's `600+0`.
   - **Fallback:** the default curve when a rating or the time class is missing.
   - **Provisional labels:** the output line is prefixed `[<rule>, provisional]`, while the
     text stays unmarked (R3-D H9).

## 3. Evidence

### 3.1 Tests

| R4-D §7 obligation | Tests |
| --- | --- |
| 1 round trip | `test_storage_graph.py`: six scenarios (fork, BRILLIANT with two issuing rounds, MISS, GREAT, FORCED, the open-exchange MISS). Both documents are byte-equal after `save(load(x))`, the encoded fields are equal, and the trees match by digest and rev. Plus a non-reproducible tree (a round-0 deadline cut, loaded under a calm clock). |
| 2 tampering | rendered text, labels, a claim dropped, the digest, truncated bytes |
| 3 build | another phrasebook digest, another `MISS_LOSS`, another template version |
| 4 cursor | a probe template records `(view.rev, node count)` at each proposal; the replay's list equals the original's |
| 5 normalization | `tests/facts/search/test_normalize.py`: `normalize_open` on SAN, `fen = None` and default families. Each revision's raw request, normalized on the view before it, equals the log; this covers a `NO_OP`, line continuation and an engine session's expansion. |
| 6, 6a, 6b configuration, one plan path, shape | a custom template set is saved in the build, refused with the default, and loads with the same set. `render(plan_analysis(a), a) == explain(a)` with equal `plan_digest`, on every scenario and corpus case. The loaded tree is a `FactTree`. |
| 7 replay mismatch | a recorded revision turned `NO_OP` is refused at `rounds`; an under-run is refused by `finish()` |
| 8 outcome kinds | revisions; `NO_OP` (a probe asking for `status` already present); `REFUSED(BudgetExceededError)` from a fact engine that refuses the first `exchange` ensure. That one replays to the same `INCONCLUSIVE(NOT_COMPUTED(BudgetExceededError))`. |
| 9 grading | the stored grading altered |
| 10 corpus | `test_corpus.py`: 12 cases plus the minimum-set check. `test_corpus_stockfish.py`: 12 cases under Stockfish 19. |
| 11 tool | `tests/tools/test_explain_game.py`: four plies with bundles written and re-loaded; a ply range; the grading from chess.com and Lichess headers and the fallback |

**Mutation checks:**
- A `ReplayTree` that shows the final revision fails 13 of the 15 storage tests.
- `planned_search_bound` with the live `plan_lines` fails the pinned-view test.

| Suite | Result |
| --- | --- |
| `tests/reasoning`, `tests/tools`, boundaries, `tests/facts/test_exchange.py`, `tests/facts/search/{test_planning,test_normalize,test_storage}.py` | 463 passed, 13 skipped; the timing-sensitive planning test below deselected |
| `tests/reasoning/test_corpus_stockfish.py` with `CALLIOPE_STOCKFISH_PATH` | 12 passed (10.8 s) |
| `tests/facts` (the whole fact-engine suite, after the `normalize` / `planned_search_bound` changes) | 374 passed, 7 skipped; the same test deselected |

**A timing-sensitive test fails on `main` too.**
`tests/facts/search/test_planning.py::test_retries_at_several_nodes_and_a_summed_round` mixes a
5 ms deadline with 20 ms engine delays. On this machine it failed 4 of 5 runs on an unchanged
`main` worktree, and the same on this branch. It is not changed here.

### 3.2 The first end-to-end explanation

`python -m tools.explain_game` on the owner's 1700 / 1724 rapid game (Q3 §6.1, 100 plies). It
used Stockfish 19 at the default profile, chess.com rapid grading from the headers, and
`--bundles --json`.
- **Run:** 100 explanations, no error. It took 5 min 0 s, about 3 s per ply with save and re-load.
- **Bundles:** 200 written (6.5 MB). Each was re-loaded by replay and saved again to the same
  bytes.
- **Grades:** best 35, excellent 33, good 20, inaccuracy 5, mistake 5, blunder 2.
- **Labels:** three MISS (`miss_p2`, marked provisional in the output line).
  - 9.Bxe7 and 14…Ng4 are chess.com's two Misses.
  - 15.O-O is chess.com's `??`: the Miss / Mistake confusion of MV-D review N2.
- **Samples:**

> 8...h6 is a mistake. It loses the pawn on d5 at 10.Bxd5 (net material loss over the line: at
> least 1 point). Instead, 8...Qd6 was better: 8...Qd6 9.Nge2 Bg7 10.Qd2 Be6 11.O-O-O ... Based
> on the engine line at depth 12.
>
> [miss_p2, provisional] 9.Bxe7 is a mistake. This is a missed opportunity. Instead, 9.Bf6 was
> stronger. Based on the 5 moves the engine reported.

**Input note.** A first run used a copy of the PGN without its `Site` header. The tool then could
not tell a chess.com game, could not read the time control `600` as Lichess, and used the
default curve: 8…h6 graded INACCURACY instead of MISTAKE. With the original header, the grades
match the Q3 §6.1 analysis. The tool states its pool rule (§2.8). Whether to warn when it falls
back to the default curve is open (§4).

## 4. Open
- **A warning on the default-curve fallback** in `tools/explain_game`, when ratings or the time
  control cannot be read.
- **The timing-sensitive planning test** (§3.1) belongs to a fact-engine packet. The 5 ms
  deadline could be made deterministic with recorded decisions.

## 5. Review dispositions (rev. 1 `13cca53`, independent R4 review: NOT_READY)

The review passed storage, `ReplayTree`, `ReplayFactEngine`, `ReasoningBuild`, `plan_analysis`,
`normalize`, `planned_search_bound` and the corpus. Each finding was checked against the code.

| Finding | Disposition |
| --- | --- |
| B1 `--json` without `--bundles` records no digests | Valid: `save` ran only when `bundles` was set. Applied: `explain_game(…, digests=True)` saves and records both digests without writing files, and `main` passes `digests` when `--json` is given. Tests: the function with `digests` alone, and `main` with `--json` only, run against the synthetic engine; no bundle files appear. |
| B2 a malformed document raises `TypeError` or `KeyError` | Valid: `doc["tree"]["digest"]` and the round fields were read outside any check. Applied without a broad `except`. `_check_shape` checks the plain-JSON structure `load` reads directly (`tree`, `rounds`, `digest`). The decoded `build`, `request` and `grading` must be of their types. A recorded outcome must be a string. An `InvalidAnalysisRequest` from the stored request becomes `StoredGraphError`. Test: eight corruptions (a null tree, a missing digest, rounds as a dict, a round without requests, request and grading swapped, a numeric outcome, a numeric digest) are all `StoredGraphError`. Without `_check_shape` the test fails. |

Suite after the fixes: 465 passed, 13 skipped, the timing-sensitive test deselected.

## 6. Re-review (rev. 2 `d7c9fd1`: NOT_READY, B2 remainder)

B1 passed, and so did the eight corruptions of §5.

| Finding | Disposition |
| --- | --- |
| B2 remainder: `rounds[*].requests = null` reaches the refusal list as `None`; a stored `AnalysisRequest` with `grading = null` fails in `resolve`, outside the conversion | Valid. Rather than patch the two cases, `load` now validates every value it consumes, not only its shape. The values the replay uses are `build`, `grading` (compared), the request and the rounds' outcomes; every other field is only compared as JSON. Applied: each round's requests must be a tuple of `RequestOutcome` with a string outcome. The stored request must pass `request.check` (R0-D §5, which includes `check_spec` of its grading). `resolve` and the replay run inside one `InvalidAnalysisRequest` → `StoredGraphError` conversion. Test: three more corruptions (null round requests, null request grading, a target out of range), eleven in all. They fail on the rev. 2 code and pass now. |
