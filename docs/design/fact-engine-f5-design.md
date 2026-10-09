# Fact engine — packet F5-D: canonical encoding, digest, saved trees and the search tape

Status: **rev. 2 — independent F5-D review NOT_READY (B1–B2, C1–C8) applied; awaiting
re-review** (design only).
Date: 2026-10-09. Base: `main @ fa01c1d` (F1–F4 merged). Review: rev. 1 `dd62804`, NOT_READY;
section 13 maps every finding.

Parent design: [`fact-engine-a0-design.md`](fact-engine-a0-design.md) rev. 4 (sections 2.4,
3.3, 3.5, 7.7, 9.1, 9.2, 9.5, 10, 11, 13; amended by this packet in sections 3.5 and 9.5).
Open items carried here: F1R-N2 (python-chess version), F1-N4 (per-node coverage), F2-N2
(`delta` component classes), F4b-N3 (role order).

## 0. Scope

F5 makes a fact tree **storable, verifiable and reproducible**. Module:
`calliope/facts/storage.py` (A0 §11), under the package-boundary test.

- A canonical encoding of every record, and a per-revision **digest chain** (A0 §3.5).
- The **build identity** that a stored tree must match (A0 §9.5).
- A **saved tree**: a normalized header, the normalized request log, per-request replay
  records, the search tape and the digest chain.
- **Loading** by isolated replay through the ordinary construction path, then verification;
  **rebuilding** a stale tree under a new build.
- Persistence of the `EngineResultStore` with re-normalizing ingestion (A0 §7.7, §9.1).
- The cost record against legacy numbers (A0 §13).

## 1. Decision: store requests and searches, rebuild records on load

A scratch prototype measured storing the records themselves:

| Tree | Nodes | Records as canonical JSON | gzip | Encode |
| --- | --- | --- | --- | --- |
| Opera game, 20 plies, no engine | 21 | 1.09 MB | 0.09 MB | 129 ms |
| Same, synthetic engine, PV 9 plies | 939 | 5.97 MB | 0.31 MB | 707 ms |

**Decision.** A saved tree stores the inputs of its construction and rebuilds its records by
replaying them.

- **Construction is the only path** (A0 §9.2). Loaded records are built by the same code; no
  record is decoded and trusted.
- **Verification is total.** Any change in code, python-chess or family behaviour changes a
  digest and refuses the load. A stale tree is rebuilt (§7), never trusted (A0 §9.5).
- **Size.** One real Stockfish 19 search encodes to about 2.8 KB, so the tape is about 3 KB
  per searched input node: about 100 KB for a 33-ply game. Requests are negligible.
- **Load cost** is the build cost without engine time: 2.0 s for the 21-input-node Opera tree
  with 1,264 engine nodes (F4b record).

The review prototyped this. Replaying a tree with an irregular search, an `ANALYSIS` request,
role gain along a PV, an `ensure` on engine-only nodes and a continued line reproduced all
revisions record for record, with zero engine calls. `max_nodes` cuts also replayed
deterministically.

## 2. Canonical encoding (`fact_encoding_v1`)

A deterministic JSON encoding, used for the digest and for export, never for loading records.

**Values**

| Value | Encoding |
| --- | --- |
| `None`, `bool`, `int`, `str` | JSON as is; strings with `ensure_ascii=True`, so every Python string encodes (a lone surrogate becomes `\ud800`) |
| `float`, `set`, `frozenset`, `dict` / mapping | **refused**; records hold none (checked on every record type by the review) |
| `StrEnum` | `{"e": "<EnumName>", "v": "<value>"}` |
| key types: the closed list `NodeId`, `PieceId`, `PositionKey`, `RootId` | `{"k": "<TypeName>", "v": "<value>"}` |
| every other registered frozen dataclass (including the one-field `NotComputed`, `NotApplicable`) | `{"t": "<TypeName>", "f": [<fields in declaration order>]}` |
| `tuple`, `list` | JSON array, order kept |

- **Bytes:** UTF-8 of `json.dumps(…, separators=(",", ":"), ensure_ascii=True)`; no
  whitespace, no key sorting.
- **Types:** a closed registry `TypeName → class`:
  - the core types (keys, values, tree records, requests, search records);
  - every family's record types, which a family declares as `record_types` (a class
    attribute; F5D-N1).

  An unregistered type refuses. The registry's names, field names in order, and enum members
  form the **types digest** in the build identity (§4).
- **Attachments** are encoded as the registered record `Attachment(anchor, search_id, rev)`.
- A **search's revision** is the revision that first bound it (F4b decision 7).

**Canonical record order within a revision.** Strings compare by code point.

| Records | Order |
| --- | --- |
| nodes | by `NodeId` value |
| edges | by child `NodeId` value |
| roles | by (target `NodeId`, `on_edge`), then input roles by (kind order, by, label, index, rev, survey, comparison, attach_lines) and `ENGINE` roles by (anchor, search id, rank, PV index) |
| lines | input lines by (kind order, by, label, segment), then engine lines by (anchor, search id, rank) |
| facts | by (family registry index, target value) |
| searches | by `SearchId` |
| bindings | by (node, rev, kind, search id) |
| basis entries | by (node, rev) |
| attachments | by (anchor, search id) |
| decisions | see §3 |

## 3. Digest chain

- **Sections.** Revision r's content is one JSON array of ten sections: the nine record
  sections above, restricted to records with `rev = r`, plus **decisions**. The decisions
  section holds the engine work of that request that replay must reproduce (F5D-C6):
  - every skipped comparison and `ANALYSIS` search as (node, kind, reason), sorted;
  - every engine line cut by the deadline, by `EngineLineId`, sorted.
- **Chain.** `digest(r) = sha256(digest(r−1) ‖ bytes(r))`, where `digest(r−1)` is the raw
  32 bytes. `digest(0) = sha256(canonical(normalized header))` (§5.1). Digests are shown as
  lowercase hex.
- **Laziness.** Digests are computed lazily and cached per revision (`TreeView.digest()`), not
  at every commit (F5D-N4: encoding costs about a third of a warm build). A view pinned at r has
  `digest(r)`.
- **Excluded:**
  - `SearchRuntime`;
  - manifest run and reuse counts;
  - the request log;
  - everything else in `RevisionDelta`. Its deterministic content is already in the record
    sections or the decisions section.
- **Reproducibility.** A cold and a warm build of the same requests have equal digests **if**
  the tree is *reproducible* at r (F5D-C2):
  - every search is regular;
  - no deadline cut anything (no `DEADLINE` decision, no deadline-cut line);
  - no comparison or `ANALYSIS` search was skipped for budget;
  - `max_searches` is unset, or the number of distinct searches in the tree at r is at most
    `max_searches`. A cold build calls the engine at most once per distinct search, so the
    budget never bites.

  `TreeView.reproducible()` checks these from the records and the decisions.
- **Coverage** (F1-N4): every fact entry carries its revision, and `TreeView.coverage` reads
  them, so a loaded tree reproduces coverage exactly.

## 4. Build identity (closes F1R-N2)

```text
BuildIdentity(facts_build_version: str,        # a constant in calliope.facts
              python_chess: str,                # chess.__version__
              families: tuple[(name, version, scope, class, requires, component_classes), ...],
              encoding: "fact_encoding_v1",
              types: str)                        # the types digest (§2)
```

- **`facts_build_version`** is bumped by hand for any behaviour change that keeps every family
  version (resolver, identity, `board`, engine policy, encoding).
- **Guard test.** It pins the digest of a fixed corpus covering:
  - every family;
  - the synthetic engine, with irregular searches, budget and deadline decisions, `ANALYSIS`
    requests and role gain;
  - an `ensure` revision.

  The test keeps a table of build version → corpus digest. A change of the digest without a new
  row fails. A python-chess upgrade also trips it; that is intended, since python-chess is part
  of the build (F5D-N3).
- **python-chess** belongs to the build identity, not to the records (F1R-N2). The open
  delta's `definitions` keep naming it for readers.
- **`component_classes`** carries `delta`'s `COMPONENT_CLASS` (F2-N2). Families declare it as
  an optional class attribute. **`requires`** is part of the table (F5D-N2).

## 5. Saved tree (`fact_tree_v1`)

### 5.1 Content

```text
SavedTree(
  format: "fact_tree_v1",
  build: BuildIdentity,
  header: SessionHeader(root_id, start_fen (as parsed, with its en passant square),
                        pre_root_moves (canonical UCI), eager (resolved, registry order),
                        budget, engine profile | None, engine identity | None,
                        root_expansion, defaults),
  requests: tuple[OpenRequest | ExtendRequest | EnsureRequest, ...],   # normalized, rev order
  replay: tuple[ReplayRecord, ...],                                    # one per request
  tape: tuple[EngineSearch, ...],                                      # by SearchId
  digests: tuple[str, ...])                                            # digest(1) … digest(n)

ReplayRecord(skips: tuple[(node, kind, reason), ...],     # comparisons and ANALYSIS searches
             deadline_cuts: tuple[EngineLineId, ...],     # lines cut by the deadline
             engine_calls: int)                           # committed engine calls after it
```

**Normalized header** (F5D-C7). The header holds the session as resolved, not as typed:
- the `RootId`, the start position and canonical pre-root moves;
- the eager set after closure;
- the profile and identity.

`digest(0)` is computed over it, so SAN and UCI spellings of one session have one digest. On
load, `requests[0]` must agree with the header.

**Normalized requests** (F5D-C4). A request is logged in normal form, at commit:
- moves as canonical UCI;
- families as a tuple in registry order;
- `EnsureRequest.nodes` as a deduplicated tuple in the given order;
- the expansion resolved: the session default or the stated one;
- labels and `by` as given; they are strings by construction.

Every request type is in the type registry. Sets or other unencodable values given by a caller
are normalized away before logging.

**Logging rules.** `open` / `extend` / `ensure` append the normalized request and its
`ReplayRecord` to the tree's log **before** the revision is published, under the write lock. A
refused request appends nothing. An `ensure` that commits nothing is not a revision and is not
logged.

**Tape.** The tape is exactly the searches bound in the tree at the saved revision, each
encoded in full (identity and profile included). Size is §1; gzip is optional and outside the
format.

### 5.2 API

- `save(tree, rev=None) -> bytes`: as of a revision. The requests, replay records, tape and
  digests are all sliced at `rev` (F5D-N7).
- `FactEngine.load(data, *, rev=None) -> FactTree` (§6).
- `FactEngine.rebuild(data) -> FactTree` (§7).
- `export(tree, rev=None) -> bytes`: the records in canonical encoding (§2). It carries the
  `BuildIdentity` and the type registry with field names, so positional fields are readable
  (F5D-C8).

## 6. Loading

Every step is ingestion (A0 §9.1). Any failure refuses the load with `StoredTreeError`. A
refused load returns no tree, writes nothing to the loading engine's store, and makes no call
on its port.

### 6.1 Steps

1. **Format and build.** `format` must be `fact_tree_v1`, and the `BuildIdentity` must equal
   this build's. The families table is compared against this `FactEngine`'s registry, in
   order.
2. **Decode** the header, requests, replay records and tape through the closed type registry,
   running their constructors. Unknown types and malformed shapes refuse.
3. **Tape ingestion by re-normalization** (F5D-C3).
   - For each tape search, rebuild its `RawSearch`: invert score, bound and WDL back to the
     side to move; set `stopped_by` from the record.
   - Run `normalize` under the search's own profile and identity, and require a record equal
     to the stored one. This re-derives the id (including the irregular preimage), `regular`,
     the pinned options, the k-rank rule, WDL presence, `move = pv[0]` and PV legality.
   - Every tape search's identity and profile must equal the header's.
   - At most one irregular search per question.
4. **Isolated replay** (F5D-B2). The requests are replayed in an **internal** `FactEngine`:
   - its family registry is the loading engine's registry;
   - its port is a `ReplayEngine` with the stored identity; any engine call raises
     `StoredTreeError("search missing from the tape")`;
   - its store is **private**, holding exactly the tape's regular searches;
   - the session's irregular cache is seeded with the tape's irregular searches, by question.

   The loading engine's port and store are not touched.
5. **Replayed decisions** (F5D-B1). In replay mode, `EngineWork` takes its decisions from the
   request's `ReplayRecord`:
   - a comparison or `ANALYSIS` search is skipped iff it is listed, with the listed reason;
   - an engine line is cut iff it is listed in `deadline_cuts`;
   - `max_searches`, the clock and the survey pre-check are not consulted; they passed in the
     original.

   After each request, the replayed decisions must equal the recorded ones.
6. **Verification.** After each replayed request, the revision's digest must equal
   `digests[rev−1]`; the decisions section is part of it. After the last request, the tree's
   searches must equal the tape: no unused entry and no missing one.
7. **Rebinding.** Only after every check passes:
   - **Port.** The session's searcher is rebound to the loading engine's port if its identity
     equals the stored identity. Without a port, the `ReplayEngine` stays: `ensure` and readers
     work, and `extend` refuses. A port with another identity refuses the load.
   - **Store.** The searcher is rebound to the loading engine's store, and the verified regular
     tape searches are put into it. They are now ingested.
   - **Budget** (F5D-C1). `engine_calls` is restored from the last `ReplayRecord`, so the
     cumulative `max_searches` budget continues where it stopped.

### 6.2 Continuation

Extending a loaded tree gives the same records and digests as extending the original **with
the same store contents**. Budget-skip decisions consult the store (F5D-C1).

## 7. Rebuilding a stale tree (F5D-C8)

`FactEngine.rebuild(data)` accepts a saved tree whose build identity differs (A0 §9.5: stale
trees are rebuilt, never trusted):

1. **Decode** with the *current* type registry. A stored type missing from it refuses: the
   tree is too old to rebuild.
2. **Ingest the tape** by re-normalization under the **current** build (§6.1 step 3). A search
   that the current normalization changes is dropped from the tape.
3. **Replay** the requests through the current build. The engine is optional: the tape answers
   what it can, and a miss goes to the rebuilding engine's port, or refuses without one.
   Recorded decisions are applied as in §6.1 step 5, so the same work is skipped or cut.
4. The result is a **new** tree with new digests. It is never treated as a load of the old one,
   and its log starts fresh with the replayed requests.

## 8. Persisted `EngineResultStore` (`engine_store_v1`)

- **`save() -> bytes`** writes:
  - `format`;
  - the full `BuildIdentity` (F5D-C3a), so a normalization fix such as F4a-C1 is never served
    from an old store;
  - the regular searches by `SearchId`;
  - a sha256 over the canonical body.
- **`load(data) -> EngineResultStore`** checks, before anything is used:
  - format, build identity and body digest;
  - every entry by re-normalization (§6.1 step 3);
  - an irregular entry refuses.
- **Mixed identities.** A store may hold searches of several engine identities. Identity,
  profile and pinned options are in every `SearchId` preimage, so each search answers only its
  own questions.

## 9. Cost record (A0 §13)

Measured on aarch64 with 2 CPUs, against the legacy numbers of A0 §10:

| Measure | Legacy reference |
| --- | --- |
| Families per input node (all eager) and per engine-only node (tier) | legacy full extraction 5.6 ms per position |
| Surveys per input node; comparisons per game | legacy I1–I3 opt-in 1,150 ms per request |
| One full `PLAYED` game with engine lines, cold and warm | legacy 8-ply replay 85 ms + validation 227 ms |
| Save size; save time; load (replay + verification) time; digest time | — |

## 10. Amendments to A0 made by this packet

- **§3.5:**
  - the digest is a per-revision chain over the canonical encoding of F5-D §2–§3, including the
    decisions section;
  - manifest counts, runtimes and the request log are outside it;
  - reproducibility follows F5-D §3 ("if", including the budget condition).
- **§9.5:**
  - a stored tree is the normalized header and requests, the replay records, the search tape
    and the digest chain;
  - loading is isolated replay through construction plus verification;
  - the build identity includes python-chess, the families table with `requires`, and the
    types digest;
  - stale trees are rebuilt by F5-D §7.

## 11. Test obligations (F5)

1. **Encoding.**
   - Every record and request type encodes, including a lone-surrogate label.
   - Bytes are identical across processes and hash seeds.
   - Refusals: floats, sets, dicts, unknown types.
   - The registry covers every reachable type; the types digest changes with a renamed field,
     reordered fields or an added enum member.
2. **Digest.**
   - Stable across processes; a pinned view's digest equals the digest at that revision.
   - Cold and warm builds are equal when reproducible, and the budget-condition counterexample
     is reported as not reproducible.
   - A field-level mutation of each record kind, and of the decisions section, changes the
     digest.
   - Runtimes, counts and the request log do not affect it.
3. **Round trip.** `load(save(tree))` equals the tree record by record, digest by digest and in
   decisions. The manifest is compared without counts and runtimes (F5D-N6). Covered trees:
   - engine-less trees over a sample of the F1 fuzz corpus (every root form, branches, `ensure`
     revisions);
   - synthetic-engine trees with irregular searches, budget skips, **deadline-cut lines**,
     `ANALYSIS` requests, role gain and pinned saves;
   - the real Stockfish 19 Opera game.
4. **Isolation** (B2):
   - a refused load leaves the loading store unchanged;
   - the loading engine's port records zero calls during a load;
   - a tape entry already present with other content in the loading store does not win.
5. **Continuation.**
   - Extending a loaded tree equals extending the original with the same store contents.
   - The restored budget refuses exactly where the original would.
6. **Refusals**, each with nothing returned or written:
   - wrong format;
   - `facts_build_version`, python-chess, family table (including the same names in a different
     order), encoding or types mismatch;
   - a tampered request, replay record, tape search (score, depth, `regular` flag, PV, id) or
     digest;
   - a missing or unused tape search;
   - a port identity mismatch.
7. **Rebuild.** A tree saved under a different `facts_build_version` rebuilds to a new tree
   with fresh digests. A tape search changed by a normalization fix is dropped and re-searched
   or refused.
8. **Store persistence.**
   - Round trip.
   - Tampered entries refused: an answer change, a re-key mismatch, an illegal PV, an irregular
     entry, the body digest, the build identity.
   - A loaded store answers with zero engine calls.
9. **Build-version guard** (§4).
10. **Cost record** (§9).

## 12. Open questions for the review (answered)

| # | Question | Answer |
| --- | --- | --- |
| Q1 | Store records instead of requests? | No. The review prototyped replay and confirmed it; the tape also enables rebuilding (§7) |
| Q2 | Accept a different python-chess with equal digests? | No |
| Q3 | Log `ensure` calls that committed nothing? | No |
| Q4 | Should the digest cover `RevisionDelta`? | Only its decisions (§3): skips and deadline cuts. Counts, reuse and runtimes stay out |

## 13. Review dispositions (rev. 1 `dd62804`: NOT_READY)

| Finding | Disposition |
| --- | --- |
| F5D-B1 deadline-cut engine lines not replayable | `ReplayRecord.deadline_cuts`; replay mode takes every decision from the record and requires equality (§5.1, §6.1.5); test obligation 3 |
| F5D-B2 replay not isolated: shared store pollution, store entries winning, real port called | internal replay engine with a `ReplayEngine` and a private store; rebinding only after verification; tape must equal the tree's searches (§6.1.4–7); tests (§11.4) |
| F5D-C1 budget not restored | `ReplayRecord.engine_calls`; continuation qualified by store contents (§6.1.7, §6.2) |
| F5D-C2 reproducibility incomplete, "iff" | budget condition added; "if" (§3) |
| F5D-C3 weak store and tape checks | full build identity and body digest in the store; ingestion by re-normalization; identity and profile checked against the header (§6.1.3, §8) |
| F5D-C4 encoding not total; sets in requests; key-like ambiguity; undefined digest pieces | `ensure_ascii=True`; normalized requests; closed key list; `Attachment` record, search rev, raw-bytes chaining (§2, §3, §5.1) |
| F5D-C5 canonical order not total | lines row fixed; code-point order; role tiebreak defined (§2) |
| F5D-C6 skip reasons outside the digest | decisions section digested (§3) |
| F5D-C7 header duplicates `requests[0]`; spelling-dependent digest(0) | normalized header; `requests[0]` checked against it (§5.1) |
| F5D-C8 rebuild undefined; export unreadable | `rebuild` (§7); export carries the build identity and type registry (§5.2) |
| F5D-N1 how families declare record types; enum members in the types digest | `record_types`; types digest (§2) |
| F5D-N2 `requires` in the families table | added (§4) |
| F5D-N3 guard corpus and history | specified (§4) |
| F5D-N4 digest cost | lazy, cached per revision (§3) |
| F5D-N5 tape size | measured figure stated (§1) |
| F5D-N6 manifest equality on round trip | without counts and runtimes (§11.3) |
| F5D-N7 pinned saves slice everything | stated (§5.2) |
| F5D-N8 module | `storage.py` under the boundary test (§0) |
| F5D-N9 missing tests | added (§11) |

**STOP** if F5:
- loads records by decoding instead of construction;
- trusts any loaded byte without the §6.1 checks, or lets a load write to a shared store before
  verification;
- lets a digest cover runtime metadata, reuse counts or the request log;
- calls an engine during a load (rebuild may, by §7);
- accepts a stored tree or store whose build identity differs (rebuild is not acceptance).
