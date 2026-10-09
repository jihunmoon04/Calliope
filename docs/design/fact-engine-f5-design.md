# Fact engine — packet F5-D: canonical encoding, digest, saved trees and the search tape

Status: **rev. 1 — awaiting independent F5-D review** (design only).
Date: 2026-10-09. Base: `main @ fa01c1d` (F1–F4 merged).

Parent design: [`fact-engine-a0-design.md`](fact-engine-a0-design.md) rev. 4 (sections 3.3, 3.5,
7.7, 9.1, 9.2, 9.5, 10, 13; amended by this packet in sections 3.5 and 9.5). Open items carried
here: F1R-N2 (python-chess version), F1-N4 (per-node coverage), F2-N2 (`delta` component
classes), F4b-N3 (role order).

## 0. Scope

F5 makes a fact tree **storable, verifiable and reproducible**:
- a canonical encoding of every record, and a per-revision **digest chain** (A0 §3.5);
- the **build identity** (`facts_build_version`, python-chess version) that a stored tree must
  match (A0 §9.5);
- a **saved tree**: the session header, the request log, the search tape and the digest chain;
- **loading** by replay through the ordinary construction path, then digest verification;
- persistence of the `EngineResultStore` (A0 §7.7), with ingestion checks (A0 §9.1);
- the cost record against legacy numbers (A0 §13).

## 1. Decision: store requests and searches, rebuild records on load

A0 §9.5 says a stored tree is accepted only when versions, engine identity, build version and
digest match. It does not say whether the records themselves are stored. A scratch prototype
measured the alternative of storing them:

| Tree | Nodes | Records as canonical JSON | gzip | Encode |
| --- | --- | --- | --- | --- |
| Opera game, 20 plies, no engine | 21 | 1.09 MB | 0.09 MB | 129 ms |
| Same, synthetic engine, PV 9 plies | 939 | 5.97 MB | 0.31 MB | 707 ms |

Most of the size is the per-position geometry: `squares` alone holds 64 entries.

**Decision.** A saved tree stores the **inputs** of its construction, not its records:
- the session header;
- every request, in order;
- every engine search the tree holds (the tape);
- the digest of every revision.

Loading replays the requests through `open` / `extend` / `ensure`, answering every engine
question from the tape. It then requires every revision's digest to equal the stored one.

Why this is the right trade:
- **Construction is the only path** (A0 §9.2). Loaded records are built by the same code that
  built the original, and never decoded from bytes and trusted.
- **Size** is the request log plus the searches, a few kilobytes per input line.
- **Verification is total.** Any difference in code, python-chess or a family's behaviour
  changes some digest and refuses the load. A stale tree is rebuilt, never trusted (A0 §9.5).
- **Load cost** is the build cost without engine time: 2.0 s for the 21-input-node Opera tree
  with 1,264 engine nodes (F4b record, warm build).

The canonical encoding (§2) still exists: the digest is computed over it, and it is the export
format for consumers that need records outside Python.

## 2. Canonical encoding (`fact_encoding_v1`)

A deterministic JSON encoding of records. It is used for the digest and for export, never for
loading.

**Values**

| Value | Encoding |
| --- | --- |
| `None`, `bool`, `int`, `str` | JSON as is |
| `float` | **refused**: no record holds one (WDL and scores are integers) |
| `StrEnum` | `{"e": "<EnumName>", "v": "<value>"}` |
| key-like dataclass with one `str` field (`NodeId`, `PieceId`, `PositionKey`, `RootId`) | `{"k": "<TypeName>", "v": "<value>"}` |
| other frozen dataclass | `{"t": "<TypeName>", "f": [<fields in declaration order>]}` |
| `tuple`, `list` | JSON array, order kept |
| `frozenset` / `set` | refused (records use sorted tuples) |
| `dict` / mappings | refused (none in records) |

**Bytes**: UTF-8, `separators=(",", ":")`, `ensure_ascii=False`, no whitespace, no key sorting
(field order is the declaration order).

**Types**: a closed registry `TypeName → class` of every record type. An unknown type refuses
encoding. Each type's field names go into the build identity (§4), so a renamed or reordered
field changes it.

**Canonical record order within a revision** (A0 §3.5, made total; F4b-N3):

| Records | Order |
| --- | --- |
| nodes | by `NodeId` value |
| edges | by child `NodeId` value |
| roles | by (target `NodeId`, `on_edge`), then the role order (input roles by kind, by, label, index, rev, expansion; `ENGINE` by anchor, search id, rank, PV index) |
| lines | input lines, then engine lines (A0 §3.5) |
| facts | by (family registry index, target value) |
| searches | by `SearchId` |
| bindings | by (node, rev, kind, search id) |
| basis entries | by (node, rev) |
| attachments | by (anchor, search id) |

## 3. Digest chain

- **Revision digest.** For revision r, take the canonical encoding of every record whose
  `rev = r`, as one JSON array of the nine sections above in that order. Then:
  `digest(r) = sha256(digest(r−1) ‖ bytes(r))`, with
  `digest(0) = sha256(canonical(session header))` (§5.1).
- **Pinned views.** `TreeView.digest()` returns `digest(view.rev)`, so a view pinned at r has
  the digest of r.
- **Excluded** (not facts; A0 §3.5):
  - `SearchRuntime`;
  - manifest run and reuse counts;
  - the whole `RevisionDelta`. The deltas summarize records that are already in the digest,
    and some fields (counts, store hits) depend on the store, not on the facts.
- **Reproducibility.** A cold and a warm build of the same requests have equal digests iff the
  tree is *reproducible*:
  - every search is regular;
  - no deadline skipped work;
  - no comparison or `ANALYSIS` search was skipped for budget, because a budget skip depends on
    which searches the store already held.

  `TreeView.reproducible()` folds this from the deltas (`load_dependent`, `skipped`). This
  extends A0 §3.5, which named only irregular searches and deadline skips: budget skips are
  store-dependent.
- **Coverage** (F1-N4) needs no separate record. Every fact entry carries its revision, and
  `TreeView.coverage` reads them. A loaded tree reproduces it exactly.

## 4. Build identity (closes F1R-N2)

```text
BuildIdentity(facts_build_version: str,      # a constant in calliope.facts, e.g. "1"
              python_chess: str,              # chess.__version__
              families: tuple[(name, version, scope, class, component_classes), ...],
              encoding: "fact_encoding_v1",
              types: digest of the type registry (names and field names))
```

- **`facts_build_version`** is bumped by hand for any behaviour change that keeps every family
  version: a bug fix in the resolver, identity, `board`, the engine policy, or the encoding.
  A test guards it: the digest of a fixed corpus is pinned in the test suite. A change to that
  digest fails the test until the constant and the pinned value are updated together.
- **python-chess** affects legal moves, SAN and the insufficient-material rule. Its version
  therefore belongs to the build identity, not to the records (F1R-N2). The open delta's
  `definitions` keep naming it for readers.
- **`component_classes`** carries `delta`'s `COMPONENT_CLASS` (F2-N2). A family declares it as
  an optional class attribute; it is empty for every other family.

## 5. Saved tree (`fact_tree_v1`)

### 5.1 Content

```text
SavedTree(
  format: "fact_tree_v1",
  build: BuildIdentity,
  header: (root_spec as given, eager families, budget, engine profile | None,
           engine identity | None, root_expansion, defaults),
  requests: tuple[OpenRequest | ExtendRequest | EnsureRequest, ...],   # rev order, rev 1 = open
  replay: tuple[ReplayRecord, ...],      # per request: the skip decisions it made (§6.2)
  tape: tuple[EngineSearch, ...],        # every search bound in the tree, by SearchId
  digests: tuple[str, ...])              # digest(1) … digest(n)
```

- `requests[i]` is the request that committed revision i+1. An `ensure` that committed nothing
  is not a revision and is not logged.
- Everything is encoded with §2. The saved bytes are canonical JSON; gzip is optional and lies
  outside the format.
- **API.**
  - `save(tree, rev=None) -> bytes` saves as of a revision, so a pinned view can be saved.
  - `FactEngine.load(data, *, rev=None) -> FactTree` replays up to `rev`.

### 5.2 Request log

`FactEngine.open` / `extend` / `ensure` append the request to the tree's log **at commit**,
under the write lock. A refused request appends nothing. The log is session state, not a fact;
it is excluded from the digest, because the records it produces are already in the digest.

## 6. Loading

### 6.1 Steps

Every step is ingestion (A0 §9.1); any failure refuses the load with `StoredTreeError`, and no
tree is returned.

1. **Format and build.**
   - `format` must be `fact_tree_v1`.
   - Every `BuildIdentity` field must equal this build's: the families table compared
     against this `FactEngine`'s registry, python-chess, `facts_build_version`, encoding, types.
2. **Decode.** The requests, the tape and the replay records are decoded through the closed
   type registry, and their constructors run. Unknown types and malformed shapes refuse.
3. **Tape ingestion.** Each tape search is checked:
   - its `SearchId` is recomputed from its content (`request_key` for a regular search; plus
     the lines digest for an irregular one) and must equal the stored id;
   - every PV is replayed for legality from its window end;
   - ranks and moves follow F4-D §5.2.
4. **Replay.**
   - **Engine.** The session's engine is a `ReplayEngine`. Its identity is the stored identity,
     and any engine call raises `StoredTreeError("search missing from the tape")`.
   - **Searches.** Regular tape searches seed the session's result store. Irregular ones seed
     the session's committed cache, keyed by their question (F4a decision 2).
   - **Requests.** Each request in the log is replayed in order, through the ordinary
     `open` / `extend` / `ensure`.
5. **Verification.** After each replayed request the revision's digest must equal
   `digests[rev−1]`.
6. **Continuing.**
   - The loaded tree's session is bound to the loading `FactEngine`'s port, whose identity must
     equal the stored identity. A loading engine without a port gives a tree that `ensure` and
     the readers accept, and that `extend` refuses (F4-D §6.1).
   - Engine sessions loaded without a port keep the `ReplayEngine`.

### 6.2 Replaying skip decisions

Deadline and budget skips depend on the clock and on what the store held, so replay cannot
recompute them. Each `ReplayRecord` lists, for its request, the (node, kind) pairs that were
skipped and their reasons. In replay mode, `EngineWork`:
- skips exactly those pairs with the recorded reasons;
- skips nothing else;
- ignores `max_searches`, the deadline and the survey pre-check, which all passed in the
  original.

The digest check then proves the replay reproduced the original.

## 7. Persisted `EngineResultStore` (`engine_store_v1`)

- `EngineResultStore.save() -> bytes` writes every regular search, by `SearchId`, with §2
  encoding and the build identity's encoding and types fields.
- `EngineResultStore.load(data) -> EngineResultStore` ingests: format, encoding and types, then
  every entry is checked as tape searches are (§6.1 step 3). An irregular entry refuses.
- A loaded store answers questions as a warm store does; this is the "test tape" of A0 §7.7.
  The engine identity is inside every search (and its id), so a store holding searches of two
  identities is valid: each answers only its own questions.

## 8. Cost record (A0 §13)

F5 measures, on aarch64 with 2 CPUs, and records against the legacy numbers of A0 §10:

| Measure | Legacy reference |
| --- | --- |
| Families per input node (all eager), per engine-only node (tier) | legacy full extraction 5.6 ms per position |
| Survey per input node; comparisons per game | legacy I1–I3 opt-in 1,150 ms per request |
| One full PLAYED game with engine lines, cold and warm | legacy 8-ply replay 85 ms + validation 227 ms |
| Save size and time; load (replay + digest) time | — |
| Digest of a pinned revision | — |

## 9. Amendments to A0 made by this packet

- **§3.5:**
  - the digest is a per-revision chain over the canonical encoding of F5-D §2–§3;
  - manifest deltas are outside it;
  - reproducibility also excludes budget skips.
- **§9.5:**
  - a stored tree is the request log, the search tape and the digest chain;
  - loading is replay through construction plus digest verification;
  - the build identity includes the python-chess version and the type registry.

## 10. Test obligations (F5)

1. **Encoding.**
   - Every record type of every family, and every tree record, encodes.
   - Encoding is byte-identical across processes and refuses floats, sets, dicts and unknown
     types.
   - The registry covers every type reachable from a record.
2. **Digest.**
   - Stable across processes.
   - A pinned view's digest equals the digest at that revision.
   - Cold and warm builds have equal digests when reproducible.
   - The digest changes when any single record changes: field-level mutation of each record
     kind, the F2 mutation method.
   - Runtimes and manifest counts do not affect it.
3. **Round trip.** `load(save(tree))` equals the tree record by record and digest by digest,
   for:
   - engine-less trees over the F1 fuzz corpus (a sample of games, every root form, branches,
     `ensure` revisions);
   - synthetic-engine trees with irregular searches, budget skips, deadline skips, `ANALYSIS`
     requests, role gain and pinned saves;
   - the real Stockfish 19 Opera game.
4. **Continuation.** Extending a loaded tree equals extending the original, records and
   digests.
5. **Refusals**, each with nothing returned:
   - wrong format;
   - `facts_build_version`, python-chess, a family version, encoding or types mismatch;
   - a tampered request, tape search (id, PV or line) or digest;
   - a missing tape search;
   - an engine identity mismatch when continuing with a port.
6. **Store persistence.**
   - Round trip.
   - Tampered entries refused: re-key mismatch, illegal PV, irregular entry.
   - A loaded store answers with zero engine calls.
7. **Build-version guard.** The pinned corpus digest test (§4).
8. **Cost record** (§8).

## 11. Open questions for the review

| # | Question | Proposed answer |
| --- | --- | --- |
| Q1 | Store records instead of requests? | No (§1): construction is the only path, size, total verification |
| Q2 | Should loading accept a different python-chess with equal digests? | No: the build identity must match first. A digest-equal mismatch is a coincidence nobody should rely on |
| Q3 | Should `ensure` calls that committed nothing be logged? | No: they made no revision |
| Q4 | Should the digest cover `RevisionDelta`? | No (§3): deltas summarize records and hold store-dependent counts |

**STOP** if F5:
- loads records by decoding instead of construction;
- trusts any loaded byte without the §6.1 checks;
- lets a digest cover runtime metadata or reuse counts;
- calls an engine during a load;
- accepts a stored tree or store whose build identity differs.
