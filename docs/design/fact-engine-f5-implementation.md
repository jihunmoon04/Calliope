# Fact engine — packet F5 implementation: encoding, digest, saved trees, store persistence

Status: **rev. 2 — independent F5 review READY_WITH_CORRECTIONS applied (§6)**.
Date: 2026-10-09. Design: [`fact-engine-f5-design.md`](fact-engine-f5-design.md) rev. 3 (F5-D).
Base: `main @ 6e13299` (F5-D merged).

## 1. Scope delivered

| Module | Content |
| --- | --- |
| `storage.py` (new) | Implements F5-D §2–§8:<br>• `FACTS_BUILD_VERSION`, `BuildIdentity`, `FamilyEntry`, `SessionHeader`, `Attachment`<br>• the closed type registry (`type_registry`, `type_table`, `types_digest`)<br>• `encode` / `canonical`, a decoder by position or by field name<br>• `revision_sections`, `digest_bytes` / `digest` (lazy, cached per revision), `reproducible`<br>• `save`, `load` (isolated replay, verification and rebinding), rebuild (`load(…, rebuild=True)`), `export`<br>• `ReplayEngine`, `raw_of` and `ingest_search` (re-normalizing ingestion)<br>• `save_store` / `load_store` |
| `tree.py` | `ReplayRecord`; `RevisionDelta.deadline_cuts`; the tree keeps its normalized request log (`_log`), each revision's records (`_revisions`) and the digest cache; `_commit` appends the log entry before publishing the revision; `TreeView.digest()` and `reproducible()` |
| `engine.py` | Normalized `OpenRequest` / `ExtendRequest` / `EnsureRequest` logged at commit with their `ReplayRecord`; replay hooks of an internal engine (`_next_record`, `_strict`, `_irregular_seed`); `FactEngine.load` and `FactEngine.rebuild` |
| `engine_work.py` | `Decisions` (strict replay or rebuild); recorded deadline cuts; the survey pre-check counts **distinct engine inputs** (F4-D §8.3 as amended by F5-D) |
| `families/*.py` | `record_types` on every family; `component_classes` on `delta` |
| `errors.py` | `StoredTreeError` |

## 2. Implementation decisions within the design

1. **Per-revision records.** `FactTree._commit` keeps each revision's `PendingRevision` and
   delta, so `revision_sections(r)` reads exactly the records of revision r without scanning
   the store. A search's revision is the one in which it was first bound (F4b decision 7).
2. **The digest cache** is filled on demand. `digest(r)` computes `digest(r−1)` first; a
   revision's digest never changes once computed.
3. **Decoding.**
   - A load requires the saved type table to equal the current one, and decodes by position.
   - A rebuild decodes by field name against the saved table: fields are mapped by name; a
     field removed from the current type, or added to it without a default, refuses.
4. **Answers versus questions.**
   - Re-normalization re-derives everything that the raw engine output determines: the id,
     `regular`, pinned options, ranks, PV legality and WDL presence.
   - A changed *score* is still a valid engine answer, so re-normalization cannot reject it.
     In a saved tree the digest rejects it (the search is in the digest); in a persisted store
     the body sha256 does.
   - A store has no outside authority: anyone who rewrites a score and recomputes the body
     digest has written a different store, and A0 §9.5 limits loading to storage the fact
     engine itself wrote.
5. **Replay records in a replayed tree.** In strict replay the logged record is the recorded
   one, after its skips and cuts were checked equal, so `save(load(data)) == data`. A rebuild
   logs fresh records.
6. **Engine-call bounds.** They are checked twice:
   - before replay, loosely: integers, non-decreasing, within the tape size and `max_searches`;
   - after replay, exactly: per revision, at most the number of searches first bound in it.
7. **Malformed content.** Anything the decoder or re-normalization raises on stored content
   (`FactEngineError`, `KeyError`, `TypeError`, `ValueError`, `AttributeError`,
   `RecursionError`) refuses with `StoredTreeError`. The build identity is decoded and compared
   before anything else (F5-D §6.1 step 1).
8. **Nothing unused, nothing contradicting.** A tape search id appears once; after a full
   load the tree's searches equal the tape as records (not only as ids), after a pinned load
   they are a subset of it as records; and the replayed session's header equals the saved one
   (the header's `root_id` is otherwise not checked by any digest, since `digest(0)` is
   computed from the replayed session).
9. **`load(data, rev=k)`** replays k requests, requires the tree's searches to be in the tape,
   puts only those into the loading store, keeps in the session cache only the irregular
   answers bound by revision k, and restores the engine calls of record k.
10. **Rebuild** uses the rebuilding engine's port when it has one; the port must have the
   stored identity. Tape searches that fail ingestion under the current build are dropped, and
   their questions go to the port. A rebuild runs live under the budget: the survey pre-check
   applies (only a strict replay skips it), and its replay records count the rebuild's own
   engine calls instead of restoring the saved ones.
11. **Ensure nodes** are logged sorted and deduplicated, so the saved bytes do not depend on
   the collection (or hash seed) the caller used.
12. **`save(tree, rev)`** refuses a revision outside `1..tree.rev`.
13. **The guard corpus** (`test_build_version_guard`) exercises:
   - every family, through an `ensure` of all families on an engine-only node;
   - an irregular search;
   - budget skips of a comparison and of `ANALYSIS` searches;
   - an `ANALYSIS` request;
   - in two more sessions, deadline cuts (`deadline_per_request_ms=0`) and role gain (an
     `EXPLORED` extend through a PV node).

   The sha256 of the three digests is pinned per (`facts_build_version`, python-chess version).

## 3. Not in F5

Nothing from F5-D is deferred. Later blocks (experiment requests, reasoning, explanation, API)
start their own packets (roadmap §5.2).

## 4. Evidence

| Check | Result |
| --- | --- |
| `tests/facts/search/test_storage.py` (24 tests) | pass |
| `tests/facts/search/test_stockfish_acceptance.py`, saved-game round trip (real Stockfish 19) | pass |
| `tests/facts` with the 400-game fuzz, real-Stockfish acceptance, `tests/test_package_boundaries.py` | 339 passed in 11 min |
| legacy `tests/unit`, `tests/golden` | 3,163 passed |
| `ruff check`, `ruff format` | pass |

### F5-D §11 obligations

| Obligation | Tests |
| --- | --- |
| 1 encoding: every type incl. a lone-surrogate label; identical bytes across processes and hash seeds; refusals; types digest tracks fields, order and enum members | `test_every_record_and_request_encodes_including_a_lone_surrogate`, `test_bytes_are_identical_across_processes_and_hash_seeds`, `test_encoding_refuses_floats_sets_dicts_and_unknown_types`, `test_types_digest_tracks_fields_order_and_enum_members` |
| 2 digest: stable; pinned views; cold = warm when reproducible (transposed inputs within one request fit the budget); the budget counterexample; record and decision mutations change it, metadata does not | `test_digest_is_stable_and_pinned_views_match`, `test_cold_and_warm_builds_are_equal_when_reproducible`, `test_transposition_within_one_request_is_counted_once`, `test_budget_counterexample_is_not_reproducible`, `test_a_mutated_record_or_decision_changes_the_digest_but_metadata_does_not` |
| 3 round trip: engine-less trees in every root form with branches and `ensure`; engine trees with irregular searches, budget skips, deadline cuts, `ANALYSIS`, role gain, `ensure` and pinned saves; the real game | `test_round_trip_of_engine_less_trees_in_every_root_form`, `test_round_trip_of_engine_trees_with_every_decision_kind`, `test_saved_game_round_trip_and_cost` |
| 4 isolation: refused load leaves store and port alone; conflicting loading store refuses; pinned load puts only its searches and forgets later irregular answers | `test_isolation_refused_loads_leave_the_store_and_port_alone`, `test_a_conflicting_loading_store_refuses`, `test_pinned_load_puts_only_the_searches_at_that_revision`, `test_pinned_load_forgets_later_irregular_answers` |
| 5 continuation and the restored budget | `test_continuation_equals_the_original_and_the_budget_is_restored` |
| 6 refusals (format, build, python-chess, encoding, type table, requests, decisions, answers, PV, `regular`, depth, missing, duplicate and unused tape entries, root id, engine calls, identity; malformed content of every kind); harmless rewrites accepted | `test_refusals`, `test_malformed_content_refuses_with_stored_tree_error`, `test_unused_or_contradicting_content_refuses`, `test_harmless_rewrites_load` |
| 7 rebuild: another build version; a dropped tape search re-searched; a reordered type decoded by name; another identity refused | `test_rebuild_under_another_build_version_and_with_a_dropped_tape_search`, `test_rebuild_decodes_a_reordered_type_by_field_name` |
| 8 `save(load(data)) == data` | in the round-trip tests |
| 9 store persistence | `test_store_round_trip_and_refusals` |
| 10 build-version guard | `test_build_version_guard` |
| 11 cost record | §5 |

## 5. Cost record (F5-D §9; aarch64, 2 CPUs; against the legacy numbers of A0 §10)

| Measure | Fact engine | Legacy reference |
| --- | --- | --- |
| Families per input node, all 13 eager (F1–F3) | 3.97 ms (F4b record; 40 random games) | full extraction 5.6 ms per position, including re-projection |
| Tier families per engine-only node | about 1.5 ms (warm Opera build: 2.0 s for 21 input + 1,264 engine nodes) | — |
| Survey per input node (Stockfish 19, depth 12, MultiPV 5) | median 170 ms on random games, 484 ms on the Opera game; adapter overhead 12 ms | I1–I3 opt-in 1,150 ms per request |
| One `PLAYED` game, 20 plies, with engine lines | cold 13.0 s (23 searches), warm 2.0 s | 8-ply replay 85 ms + validation 227 ms, without engine lines |
| Save of that game | 79 KB, 8 ms | — |
| Digest of the whole tree (1,285 nodes) | 1.0 s, lazy and cached | — |
| Load (replay and digest verification; the split is estimated from the warm build and the digest, not measured) | 3.0 s, 0 engine calls | — |

The fact engine holds much more than legacy per position (geometry, patterns, deltas, history
facts) and no longer re-validates. Its per-position cost is below legacy's full extraction.
An analysed game with its engine lines is reproduced from a 79 KB file in 3 s, without the
engine.

## 6. Independent F5 review — READY_WITH_CORRECTIONS, applied

| Finding | Resolution |
| --- | --- |
| C1 malformed input raised `TypeError`, `AttributeError`, `InvalidRequestError` or `RecursionError` instead of `StoredTreeError` | §2.7; `test_malformed_content_refuses_with_stored_tree_error` (10 tampered documents and a deeply nested one; nothing written, no engine call) |
| C2 a duplicate tape search with another score, and a changed `header.root_id`, loaded silently | §2.8; `test_unused_or_contradicting_content_refuses` |
| C3 a pinned load kept the irregular answers of later revisions in the session cache | §2.9; `test_pinned_load_forgets_later_irregular_answers` |
| C4 the pre-check test transposed across requests and passed with the old per-node count | `test_transposition_within_one_request_is_counted_once` (fails with the per-node count) |
| C5 the guard corpus lacked deadline cuts and role gain | §2.13; digest re-pinned (the first session's digest is unchanged) |
| N1 partial §11 tests | refusal tests extended (§4 obligation 6); per-kind record mutation and added-field rebuild remain covered by the representative cases listed |
| N2 rebuild skipped the survey pre-check | §2.10 |
| N3 a persisted store accepted a duplicate id | refused |
| N4 ensure node order followed the caller's collection | §2.11 |
| N5 `save` of an out-of-range revision; `engine_calls` as `bool` | §2.12, §2.6 |
| N6 load split was inferred | §5 says so |
| N7 hook state on `FactEngine` | kept: set only on the internal engine of a load |
