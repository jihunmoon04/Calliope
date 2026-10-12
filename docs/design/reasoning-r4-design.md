# Reasoning — R4-D design: `claim_graph_v1` storage, the acceptance corpus, the first end-to-end explanation

Status: **rev. 3 — reviews applied (§9, §10); final re-review READY**.
Date: 2026-10-12. Base: `main @ a4fac2e`. Contracts:
[`reasoning-r0-design.md`](reasoning-r0-design.md) rev. 10 (R0-D) §14, §18.10–§18.11, §19,
amended in §30–§32; [`reasoning-quality-v2-design.md`](reasoning-quality-v2-design.md) (Q-D) §6;
[`fact-engine-f5-design.md`](fact-engine-f5-design.md) (F5-D) §6 for the fact tree's load;
[`reasoning-r3-design.md`](reasoning-r3-design.md) (R3-D) for the plan and the rendering.

R4 is the last packet of R0-D §19: storage of an analysis, the acceptance corpus, and the first
end-to-end explanation. R0-D §14 was written before `quality_v2`, `label_v2`, MISS v2 and English
first, so its document still names `phrases_ko_v1`, `quality_v1` and `label_v1`. This packet brings
§14 up to date and fixes what §14 leaves open: how the controller replays on load, what the build
records, what the corpus holds, and where the end-to-end run lives.

## 0. Decisions

| # | Decision |
| --- | --- |
| S1 | **An analysis bundle is two documents:** the fact tree (`fact_tree_v1`, F5) saved at the analysis's final revision, and the claim graph (`claim_graph_v1`, §2). The graph names the tree by its digest and revision. Neither document embeds the other. |
| S2 | **Load replays the reasoner, unchanged, against the loaded tree, through a revision cursor** (§3). A replaying fact engine stands in for `FactEngine`, and a `ReplayTree` stands in for the tree: its `rev` and default `view()` are the replay position, never the final revision (rev. 2, review B1). Each `open`, `extend` and `ensure` the reasoner makes is normalized by the fact engine and checked against the tree's request log instead of being executed (review B2). The re-derived document must equal the stored bytes. This is R0-D §14.3's "replay mode" with no second code path in the controller or the runner. |
| S3 | **The build is part of the identity, taken from the reasoner that ran** (§2.1; rev. 2, review B4): fact build, reasoning build version, the reasoner's templates, policies, label rules, the phrasebook with its file digest, and the reasoner's grading build (curve tables, conversions, `LOGISTIC`). `Analysis` records it; `load` must be given a reasoner configuration with the same build. A graph saved under another build is refused, with no rebuild of graphs: re-analysis is a new analysis (§3.4). |
| S4 | **The acceptance corpus is data** (§4): `tests/reasoning/corpus/*.toml`. It holds positions, scripted engine lines, expected claims, labels and the exact text. A second, gated run uses real Stockfish 19 on the same positions with weaker, engine-robust expectations. |
| S5 | **The first end-to-end explanation is an operator tool,** `tools/explain_game`, outside `src/` (§5). It takes a PGN in and writes per-ply text and, on request, bundles. A public API and result schema remain roadmap item 4. |

## 1. Scope
- **In scope:**
  - `reasoning/storage.py` (save, load, replay) and the build identity;
  - `FactEngine.normalize` (§3.5), the one fact-engine addition;
  - the corpus and its two test runners;
  - `tools/explain_game`;
  - R0-D §14 amended (R0-D §33).
- **Out of scope:**
  - the public API and result schema (roadmap §5.2 item 4);
  - Korean (`phrases_ko_v1`);
  - recorded proposals of non-deterministic proposers (R0-D §8.7). Catalogue v1 is deterministic,
    so `proposals` is empty (§2.2).
  - re-analysis tooling for stale graphs (§3.4).

## 2. `claim_graph_v1`

### 2.1 Build identity

```text
ReasoningBuild(
    reasoning_build_version: int,           # 1; raised by any change that alters stored bytes
    facts: BuildIdentity,                    # the fact engine's (F5-D §2)
    encoding: "fact_encoding_v1",
    types: types_digest(reasoning_registry()),
    templates: ((name, version), …),         # CATALOGUE_V1 in registry order (25 templates)
    policies: ("quality_v1", "quality_v2", "label_v1", "label_v2", "selection_v1"),
    label_rules: ("forced_v1", "brilliant_p2", "great_p2", "miss_v1", "miss_p2"),
    label_parameters: (("brilliant_p2", (OFFER_MIN, NEAR_BEST, NOT_BAD, WINNING)),
                       ("miss_p2", (MISS_OPPORTUNITY, MISS_LOSS))),
    phrasebooks: (("phrases_en_v1", sha256(en.toml)),),
    curves: ((table name, digest), …), conversions: ((name, digest), …),
    logistic: digest of LOGISTIC)            # Q-D §6
```

- **Why the rule parameters and the phrasebook digest.** A changed threshold or a changed word
  changes the claims, the labels or the text. The build is what makes "same request, same bytes"
  checkable.
  - A provisional rule's parameters are named constants in code (LV-D §8, MV-D §3). Listing them
    makes an unannounced change visible as a build mismatch.
  - A phrasebook text change without a new name (as R3-D §16 was, before any user rendering) still
    changes the digest.
- **`label_rules`** lists every rule the code can emit. `miss_v1` stays, because `label_v1` remains
  in the code.
- **Taken from the reasoner that ran** (rev. 2, review B4).
  - `Reasoner` gains `build() -> ReasoningBuild`. It reads its own `templates` and
    `grading_build`, its fact engine's `BuildIdentity`, the label rules and parameters of
    `labels.py`, and the phrasebook.
  - `Analysis` gains a last field `build: ReasoningBuild`, set by `analyse`. `save` writes it, so
    an analysis made with custom templates is stored with those templates, never under
    `CATALOGUE_V1`'s name.
  - `load` takes the configuration to replay with: `templates=None` (the catalogue) and
    `grading_build=SHIPPED` by default, as `Reasoner` does. That reasoner's `build()` must equal
    the stored build; otherwise `StoredGraphError`. Custom templates load when the caller passes
    the same templates, and their record types are registered (`encoding.register`).

### 2.2 Document

```text
{ "format": "claim_graph_v1",
  "build": ReasoningBuild, "types": type table,
  "request": AnalysisRequest (normalized; GradingSpec with its defaults written out, Q-D §6),
  "grading": Grading (resolved, Q-D §6),
  "tree": { "digest": TreeView.digest() at "rev", "rev": final rev, "reproducible": bool },
  "limits_reached": [LimitReached …],
  "rounds": [ { "index", "rev", "admitted": [EvidenceNeed …], "proposals": [],
                "requests": [RequestOutcome …] } … ],
  "judgements": [Judgement …], "observations": [Observation …],
  "claims": [Claim …], "relations": [ClaimRelation …], "labels": [Label …],
  "plan": ExplanationPlan, "rendered": RenderedExplanation,
  "digest": sha256 of the canonical encoding of everything above }
```

- **Encoding.** It is canonical, as R0-D §14.1 requires.
  - **Registry additions (rev. 2, review C1):** `AnalysisRequest`, `ReasoningBudget`, `Round`,
    `RequestOutcome`, `LimitReached`, `ReasoningBuild`, `Segment` and `RenderedExplanation`.
  - **Already registered,** checked: `RootSpec`, `EngineProfile`, `GradingSpec`, `Grading`,
    `OpenRequest`, `ExtendRequest`, `EnsureRequest`, `InputLine`, `SessionBudget`,
    `BuildIdentity` and `ExplanationPlan`.
  - `RoundZero` itself is not stored: it holds the `FactTree`. Its encodable parts are stored as
    their own fields (`request`, `grading`, `judgements`, `observations`, the tree's digest and
    rev).
- **`proposals` is always `[]`** under catalogue v1 (§1).
- **`rendered` is stored.** It is re-derived on load like every other field, so it is checked, not
  trusted.
- **Order.** Lists keep their analysis order: claims by `seq`, relations as the graph returns them,
  rounds by index.

### 2.3 Save

```text
save(analysis, rendered) -> (tree_bytes, graph_bytes)
```

1. `tree_bytes = facts.storage.save(analysis.tree, analysis.rev)`.
2. The graph document is built from the analysis, `rendered` and the current build, and encoded
   canonically.
3. `rendered` must equal `render(plan_analysis(analysis), analysis)`. `save` re-plans and
   compares: it is cheap, and it keeps a hand-built rendering out of storage.

**`plan_analysis` (rev. 3, review B5).** R3's `plan()` takes `(judgements, claims, relations,
labels, ply_of)`, not an `Analysis`. `ply_of` orders mechanisms of one template by their node, and
until now only `explain()` built it. R4 extracts that step into one function in
`reasoning/render`:

```text
plan_analysis(analysis) -> ExplanationPlan
    # plan(judgements, claims, relations, labels, ply_of) with ply_of read from
    # analysis.tree.view(analysis.rev); the only place an analysis becomes a plan
explain(analysis) = render(plan_analysis(analysis), analysis)
```

`save` and `load` use `plan_analysis` too, so a stored plan is never built another way. The
planner itself still reads no tree; `plan_analysis` is the adapter that does.

## 3. Load and replay

```text
load(fact_engine, tree_bytes, graph_bytes, *, templates=None, grading_build=SHIPPED)
    -> (analysis, rendered)
```

### 3.1 Steps
1. **Parse the graph document.** The format and the type table must match. Then the build must
   equal `Reasoner(fact_engine, templates, grading_build).build()` (§2.1). Any difference refuses
   with `StoredGraphError`.
2. **Load the tree** with `fact_engine.load(tree_bytes)` (F5-D §6), which replays and verifies
   every revision. Its digest at `tree.rev` must equal the document's.
3. **Resolve the grading again** from the stored request under the current build. It must equal
   the stored `grading` (Q-D §6).
4. **Replay the reasoner** (§3.2) with the stored request, the given configuration, and a
   `ReplayFactEngine` over a `ReplayTree` of the loaded tree. The cursor must end at the final
   revision.
   - The `ReplayTree` is then replaced by the loaded `FactTree` itself in `RoundZero.tree`
     (rev. 3; review non-blocking note). The returned `Analysis` therefore has the same shape as
     one from `Reasoner.analyse`, and no replay object escapes `load`.
5. **Plan and render again** with `plan_analysis` and `render` (§2.3), and build the document.
6. **Compare bytes.** The re-derived document must equal `graph_bytes`. Otherwise the load refuses
   with `StoredGraphError`, naming the first differing top-level field.

### 3.2 `ReplayTree` and `ReplayFactEngine`
**`ReplayTree` (rev. 2, review B1).** The reasoner reads its tree through two members only, `rev`
and `view(rev=None)`. This was checked in `controller.py`, `runner.py` and `render/`.
- **The members.** `ReplayTree` wraps the loaded `FactTree` and a revision cursor `c`.
  - `rev` is `c`.
  - `view()` is `tree.view(c)`.
  - `view(r)` is `tree.view(r)` for `r ≤ c`, and refuses `r > c`.
  - Nothing at a later revision is visible: not nodes, facts, searches, the basis or the request
    log.
- **Why.** The loaded tree is at its final revision, so `FactTree.rev` and a bare `view()` would
  show round 1's facts to round 0. That would change `RoundZero.rev`, the judgements and every
  later need.
- **How the cursor moves.** The fact-engine calls receive the `ReplayTree` and move `c`.
  - `open` sets `c = 1`.
  - A `rev:<n>` outcome sets `c = n`.
  - `NO_OP` and `REFUSED` leave it.
- **At the end.** `c` must be the final revision. The analysis then holds the loaded `FactTree`
  itself.

**`ReplayFactEngine`.** A stand-in for `FactEngine` with the three methods the reasoner calls. It
holds the `ReplayTree`, a real `FactEngine` for normalization only (§3.5), and the recorded outcomes
from the document's rounds. Round 0's requests are the log's first entries.
- **`open(request)`.** `FactEngine.normalize_open(request)` (§3.5) must equal
  `TreeView.request(1)`. It then returns the `ReplayTree` with `c = 1`. A raw `OpenRequest` is never
  compared directly: the root FEN, SAN moves and default families are resolved first (review B2).
- **`extend` / `ensure`** advance through the recorded outcomes in order.
  - **`rev:<n>`:** the call's request, in the fact engine's normalized form (canonical UCI, sorted
    ensure nodes, families in registry order, resolved expansion; R0-D §14.3), must equal
    `TreeView.request(n)`. The normal form comes from `FactEngine.normalize(view, request)` on
    the view at the cursor (§3.5), never from a copy of its rules in reasoning. The call returns `n`, and the views the
    reasoner then takes are the
    loaded tree's views at `n`.
  - **`NO_OP`:** the call is an `ensure`, and every record it asks for is present in the view at
    the cursor. The call returns `c`.
  - **`REFUSED(<type>)`:** the call raises a new `<type>` from `calliope.facts.errors`. A
    refusal leaves no trace in the tree (R0-D §14.3), so this outcome is trusted from the document.
    The runner then marks the needs refused, as it did when the analysis ran.
  - Round 0's `open`, `extend` and `ensure` are checked the same way. Their outcomes are the log's
    first entries, since round 0 records no `RequestOutcome` (it raises on refusal).
- **No engine, no clock.** Replay never searches and never reads the time. Deadline cuts and
  skipped comparisons are already in the loaded tree (F5-D §6 replays them from its own records).
  A load is therefore deterministic even for a non-reproducible tree (`reproducible = false`).
- **Over-run and under-run.** A call after the last recorded outcome, or recorded outcomes left
  unused when the reasoner finishes, refuses with `StoredGraphError`.

### 3.3 Why replay rather than re-running with a recorded engine
Re-running the reasoner against a fresh tree, with the tape as the engine, would also re-derive the
graph. It would, however, meet the real clock again (deadlines), and it could not reproduce a
refusal. Replaying against the loaded tree uses the tree's own recorded decisions and the
document's recorded refusals. It also checks the reasoner's requests one by one (R2-C3), not only
its output.

### 3.4 Stale graphs
A graph whose build differs is refused, never rebuilt. Re-analysis is a new analysis of the
stored request on a fact tree rebuilt by F5-D §7. It may differ, and it gets a new bundle. A tool
for it is out of scope.

### 3.5 A fact-engine addition: `FactEngine.normalize`
Today the normal form of a request is built inside `open`, `extend` and `ensure`
(`facts/engine.py`) and committed with the revision. Reasoning cannot rebuild it: SAN needs the
board, and reasoning may not import python-chess (R0-D §18.1).
- **The addition (rev. 2, review B2).** R4 factors that step out as two public methods. Neither
  searches nor writes.
  - `FactEngine.normalize_open(request: OpenRequest) -> OpenRequest` needs no tree. It resolves
    the root FEN (the standard start for `fen = None`), SAN to canonical UCI, and `families =
    None` to the engine's eager families.
  - `FactEngine.normalize(view: TreeView, request) -> ExtendRequest | EnsureRequest` returns what
    the call would commit on a tree whose current revision is `view`'s.
  - `open`, `extend` and `ensure` call them, so there is one normal form.
- **Tests.**
  - For every revision of the F5 fixtures, the logged call's raw request normalizes to
    `TreeView.request(rev)`.
  - `normalize_open` on a SAN move list, on `fen = None`, and on `families = None`.
- **Amendment.** This is the one change R4 makes to `calliope.facts`. It is recorded as an
  amendment of F5-D (§6, the request log).

## 4. The acceptance corpus (R0-D §18.11)

### 4.1 Cases
`tests/reasoning/corpus/<name>.toml`, one case per file:

```toml
name = "fork_blunder"
fen = "4kb2/8/8/6n1/1P1N4/8/P7/4K3 w - - 0 1"
before = ""                      # SAN moves before the target, from `fen`
played = "a3"
grading = { policy = "quality_v1" }       # or quality_v2 with an explicit scale or ratings
multipv = 2
[[lines]]                         # S at P, in rank order
san = "Nb3 Ne6 Kd2 Kd7"
wdl = [300, 600, 100]
cp = 0
[[lines]]
san = "a3 Bc5 b5 Be7 b6 Nf3+ Ke2 Nxd4+ Kd3 Nf5"
wdl = [0, 0, 1000]
cp = -500
# [[table."<fen>"]] entries script other positions (G, X, …)

[expect]
grade = "blunder"
supported = ["material_loss_v1", "fork_v1", "better_move_v1"]   # at least these SUPPORTED
labels = []                                                      # [[kind, rule]] exactly
text = "1.a3 is a blunder. Through the fork …"                    # exact
```

### 4.2 The minimum set
R0-D §18.11 asks for five; the corpus starts with twelve:
- a blunder allowing a fork;
- a missed mate after the opponent's blunder (MISS, `miss_p2`, with `better_move_v1`);
- a missed gain without material (MISS through `missed_gain_v1`, the 9.Bxe7 shape);
- a quiet only move (GREAT);
- a queen sacrifice (BRILLIANT);
- a quiet best move with no claim;
- a single legal move (FORCED);
- a mate delivered;
- an inconclusive judgement with an exact claim;
- a rescue (the function `rescue_v1`);
- a promotion (material gain, the promotion form);
- a check with several replies (`forcing_v1.sentence.check`).

The scenarios are R2b's, LV1's, MV1's and R3's test positions, moved into data.

### 4.3 Runners
- **`test_corpus.py` (always):** for each case, it scripts the engine and analyses. It checks the
  grade, the supported claims (a superset check), the labels (exactly) and the text (exactly). It
  then saves and loads the bundle, and checks the round trip of §7.1: bytes, encoded fields, and
  the tree by digest and revision.
- **`test_corpus_stockfish.py` (gated by `CALLIOPE_STOCKFISH_PATH`):** the same positions,
  without scripted lines, under the default profile. It checks only what does not depend on engine
  detail:
  - the analysis completes and renders without `GuardError`;
  - the bundle round-trips;
  - for cases marked `robust = true`, the labels and the claims named in `[expect.robust]`. These
    are cases whose result no engine detail can change: the mate delivered (`mate_delivered_v1`),
    the single legal move (FORCED), and the inconclusive judgement's exact claim
    (`mate_in_one_allowed_v1`).

## 5. `tools/explain_game` (the first end-to-end explanation)

```text
python -m tools.explain_game GAME.pgn [--plies 1-40] [--bundles DIR] [--json OUT]
```

- **Input.** A PGN with ratings and a time control (chess.com or Lichess). The grading spec comes
  from the headers, as `tools/calibrate_curve/acceptance.py` does.
- **Run.** For each ply, it builds an `AnalysisRequest` (the game's moves, the ply as target, the
  default profile), runs `Reasoner` on one Stockfish 19 process, then `explain`.
- **Output.**
  - Text: one line per ply, the rendered explanation. It is prefixed with the label's rule when
    provisional (H9: the caller marks it, not the text).
  - `--bundles DIR` writes `<ply>.tree` and `<ply>.graph` per ply, and re-loads each to check it.
  - `--json OUT` writes per ply the grade, labels, supported claims, text and the bundle's digests.
- **Record.** The R4 implementation record carries the tool's output for one owner game and the
  bundle checks.

## 6. Errors
`StoredGraphError` (R0-D §15) covers:
- a wrong format, types or build;
- a tree digest mismatch;
- a grading mismatch;
- a replay mismatch (a request, an over-run, an under-run);
- a re-derived document that differs.

`StoredTreeError` from the fact tree's load passes through unchanged.

## 7. Test obligations (R0-D §18.10 with this packet)
1. **Round trip (rev. 2, review B3):**
   - `save(load(x)) == x` byte for byte, for both documents;
   - the loaded analysis equals the original field by field in its encoded form: request,
     grading, rounds, judgements, observations, claims, relations, labels, `limits_reached`,
     `build`, plan and rendered;
   - the trees are compared by digest and revision, never by object equality. `FactTree` has no
     value equality, and a loaded tree is a new object;
   - this holds for every corpus case and for a non-reproducible tree (a round-0 deadline cut).
2. **Tampering refused:** one byte of a claim, a label, the rendered text or the digest changed.
3. **Build mismatch refused:**
   - another phrasebook digest;
   - another `miss_p2` threshold;
   - another template version.
4. **Replay cursor (review B1):** during replay, round 0 sees `rev_0`, not the final revision. A
   test template records `view().rev` and the node count at round 0 and at each round, and they
   equal the original run's.
5. **Normalization (review B2):** `normalize_open` on SAN, `fen = None` and `families = None`;
   `normalize` against the log on the F5 fixtures.
6a. **One plan path (review B5):** for every corpus case,
   `render(plan_analysis(a), a) == explain(a)` and
   `plan_digest(plan_analysis(a)) == explain(a).plan_digest`. A case with two mechanisms of one
   template at different plies checks that `ply_of` decides between them.
6b. **Shape after load:** `analysis.round_zero.tree` is a `FactTree`, not a `ReplayTree`.
6. **Configuration (review B4):**
   - an analysis with a custom template set saves that set in its build;
   - loading it with the default catalogue is refused;
   - loading it with the same templates succeeds.
7. **Replay mismatch refused:**
   - a recorded `rev` whose request differs (an ensure node changed in the document);
   - an extra recorded outcome (under-run);
   - a missing one (over-run).
8. **Each outcome kind:**
   - a revision;
   - `NO_OP` (an ensure of records already present);
   - `REFUSED`, by a test fact engine that refuses one ensure. The loaded analysis has the same
     `INCONCLUSIVE(NOT_COMPUTED(<type>))` verdicts.
9. **Grading mismatch refused:** the stored grading altered.
10. **Corpus:** §4.3, both runners.
11. **Tool:** `tools/explain_game` on a short PGN with the scripted engine. Text lines per ply,
   bundles written and re-loaded, JSON fields present.

## 8. Delivery

| Packet | Content | Gate |
| --- | --- | --- |
| R4-D (this) | storage and replay, build identity, corpus format, the tool | independent review READY |
| R4 | `reasoning/storage.py`, `ReplayTree`, `ReplayFactEngine`, `FactEngine.normalize_open` / `normalize`, `Reasoner.build()` and `Analysis.build`, `render.plan_analysis`, registry additions, the corpus and runners, `tools/explain_game`, the record with one owner game end to end | READY |

Amendments on merge, as R0-D §33:
- §14.1: the build of §2.1 replaces R0-D's `policies` and `phrasebooks` lines.
- §14.2: the document of §2.2 (`grading`, `proposals: []`, `rendered` under `phrases_en_v1`).
- §14.3: replay through `ReplayFactEngine` (§3), with round 0 checked against the log's first
  entries.
- §18.11: the corpus as data, with twelve cases and the gated Stockfish runner.
- F5-D §6: `FactEngine.normalize_open` and `FactEngine.normalize` (§3.5).

## 9. Review dispositions (rev. 1 `b7d73b4`, independent review: NOT_READY)

The review passed S1, S4 and S5. Each finding was checked against the code.

| Finding | Disposition |
| --- | --- |
| B1 the final tree shows later revisions to earlier rounds | Valid. `FactTree.rev` is the latest revision, and `view()` without an argument reads it. The controller calls `tree.view()` right after `open`. Applied (S2, §3.2): `ReplayTree` with a revision cursor. The reasoner uses only `rev` and `view(rev=None)` of its tree (checked in `controller.py`, `runner.py` and `render/`). `NO_OP` and normalization read the view at the cursor. Test obligation 4. |
| B2 the raw open cannot be compared with the logged one, and `normalize(tree, …)` has no tree before `open` | Valid. `FactEngine.open` resolves the root FEN, SAN and default families before logging. Applied (§3.5): `normalize_open(request)` without a tree, and `normalize(view, request)` on the view at the cursor. Test obligation 5. |
| B3 `load(save(x)) == x` cannot hold for objects | Valid: `RoundZero` holds the `FactTree`, which has no value equality. Applied (§7.1): byte equality of both documents, field-by-field equality of the encoded analysis, and trees compared by digest and revision. |
| B4 the build is not the reasoner's | Valid: `Reasoner` takes `templates` and `grading_build`. Applied the reviewer's second option (S3, §2.1). `Reasoner.build()` and `Analysis.build` record the configuration that ran, and `load` takes a configuration whose build must match. Test obligation 6. |
| C1 `AnalysisRequest` and `ReasoningBudget` are not registered | Valid, checked with `reasoning_registry()`. Applied (§2.2): the additions are listed, and the types already registered are named. |

## 10. Review dispositions (rev. 2 `e206ad5`, re-review: NOT_READY)

The re-review closed B1–B4 and C1.

| Finding | Disposition |
| --- | --- |
| B5 `render(plan(analysis), analysis)` does not match R3's `plan()`, and drops `ply_of` | Valid. `plan()` takes the claim tuples and `ply_of`, and only `explain()` built `ply_of` from the view. Applied (§2.3): `render.plan_analysis(analysis)` is the one path from an analysis to a plan. `explain`, `save` and `load` use it. Test obligation 6a. |
| (non-blocking) no `ReplayTree` in the returned analysis | Applied (§3.1 step 4): it is replaced by the loaded `FactTree`. Test obligation 6b. |

**Final re-review (rev. 3 `a4c55f9`): READY.** One note for the implementation:
`FactEngine.normalize(view, request)` must read only `view`'s revision. Code that reads the final
tree's internal store directly, as `plan_lines()` does, would let later revisions into the normal
form. The R4 tests check normalization at a cursor before the final revision.
