# Reasoning — R0 design: contracts from the fact tree to the first explanation

Status: **rev. 4 — second review (NOT_READY) applied in rev. 3; its re-review (READY_WITH_CORRECTIONS) applied (§23)**.
Date: 2026-10-10 (rev. 1: 2026-10-09; rev. 2: 2026-10-10). Base: `main @ 460aec4` (fact engine F0–F5 complete).

This document designs the blocks that follow the fact engine (roadmap §5.2, items 1–3):
experiment requests, reasoning and explanation. It fixes their **contracts** — the data each stage
receives and returns, who may change what, and how results are identified, stored and checked —
and the policies needed for a first end-to-end explanation of one move. The exact definitions of
the hypothesis templates and observations are left to the design packet R2-D (§19), as A0 left
the pattern definitions to F3-D.

## 0. Decisions (discussion of 2026-10-09)

| # | Decision |
| --- | --- |
| D1 | **Pipeline** (proposed by the project owner, adopted with the adjustments D2–D6): analysis controller → fact engine → semantic observer → hypothesis generator → verification engine → claim graph → explanation planner → template renderer with a claim guard. |
| D2 | **One mutator.** Only the controller calls `FactEngine.open` / `extend` / `ensure`. Every other stage reads a `TreeView` pinned at a revision and returns data, including what evidence it still needs. |
| D3 | **Grade** = `quality_v1`: the expected-points loss of the played move against rank 1, both read from the Stockfish WDL of **one** search (the parent's basis), in the bands of chess.com's Expected Points model. No arithmetic across searches. |
| D4 | **Labels** BRILLIANT / GREAT / MISS are not grades. `label_v1` assigns them once, after verification, from the grade and verified claims. The grade never reads claims; a label never changes the grade. |
| D5 | **Hypotheses come from a closed, versioned template catalogue.** A hypothesis may name earlier claims as premises, so later catalogues can derive new hypotheses from verified ones (semantic breadth) without a contract change. |
| D6 | **The claim graph is stored** (`claim_graph_v1`), bound to the fact tree's digest, with refuted and inconclusive claims kept. |
| D7 | **Template renderer**, Korean first, with typed slots, Korean particle (josa) selection and a structural claim guard. No LLM in this block. |
| D8 | **Default budget** per target move: 3 rounds, 4 extra engine searches, 64 `ensure` nodes, 10 PV plies examined, a 5 s deadline per fact request. |
| D9 | **First explanation = one played move.** Game-level move selection, `opponent_view` (null-move threats), static exchange evaluation and LLM wording are out of R0 (§1.2). |
| D10 | **Only move** (2026-10-10): the played move is rank 1 of the parent's unrestricted search and the rank-2 move would lose at least 0.20 expected points (a blunder). The survey ranks every legal move, so no per-move search is needed; the scope is "the engine at this depth". |
| D11 | **Hypotheses carry their verification target** (rev. 3): a quantifier (one line, some reply, all replies, selected or all alternatives, persistence), a population and a horizon, fixed at proposal; premises carry the scope they must have (§8.1–§8.2, §9.4). |
| D12 | **Co-occurrence is not explanation** (rev. 3): a mechanism EXPLAINS a consequence only after a causal check; otherwise it is ASSOCIATED_WITH it and not rendered as a reason (§10.2). |
| D13 | **Material is balance** (rev. 3): own points minus the opponent's, as a change along a line; a sacrifice must be a choice (some alternative keeps the material) and compensated (§6.5, §8.5, §11). |

## 1. Scope

### 1.1 In scope
- The package `calliope.reasoning`, its boundaries and its stages (§3).
- The common currency of references (§4) and every stage contract (§5–§13).
- `quality_v1` (§7.2), `label_v1` (§11), `selection_v1` (§12), the renderer and guard (§13).
- The template catalogue v1 by name, role and evidence (§8.5); exact definitions in R2-D.
- Storage, identity and verification of the claim graph (§14).
- Three facts-side additions — the read helpers `material_flow` and `TreeView.request`, and the
  planning bound `planned_search_bound` (§6.5) — which amend the fact engine's API.

### 1.2 Out of scope (later packets)
- Explaining a whole game: choosing which moves deserve deep analysis.
- `opponent_view` and "ignored threat" hypotheses (A0 §6.11; needs a new fact family).
- Static exchange evaluation and trapped pieces (A0 §6.11).
- Positional and strategic claims (plans, activity, space). Structural changes stay observations.
- Statements of intent ("played in order to…"). Purpose is stated only as a verified function.
- English phrasebook (the contracts are language-neutral; Korean ships first).
- A public API and result schema (roadmap §5.2 item 4).

## 2. Legacy findings

Legacy is evidence only (`docs/legacy/`, code under `src/calliope/` outside `facts/`, tag
`legacy-mvp-g0`). Short names: `P8` → `mvp-p8-bad-move-design.md`, `P9` →
`mvp-p9-good-move-design.md`, `P10`–`P12` → `mvp-p10-…`, `mvp-p11-…`, `mvp-p12-…`, `p2-c1` →
`p2-c1-judgement-cross-search-stabilization-design.md`, `G0` → `mvp-g0-closure.md`, `move_judge` →
`src/calliope/services/judgement/move_judge.py`.

| Legacy finding | Evidence | Rule here |
| --- | --- | --- |
| The judge compared the MultiPV best with a played-only search when the played move was outside the MultiPV; scores from different search trees inverted by 34 cp; fixed by an extra paired search, residual mate contradictions still failed requests | `move_judge`, p2-c1 §1–§12, G0 §11 | the grade reads only the parent's basis search, which contains the played move by construction (F4-D §7.2); no fallback search (§7.2) |
| Grade thresholds 0.01 / 0.03 / 0.08 / 0.18 expected score, cp fallback 20 / 50 / 100 / 200; rank 1 always BEST; a negative loss floored, never promoted to BEST; slower mates graded by the mate distance | `move_judge` `MoveJudgementPolicy`, `_slower_grade`; p2-c1 §10 | chess.com bands (D3); rank 1 is the only BEST; mate distance table kept for mating and being mated; a missed mate that still wins is a claim, not a grade; no cp fallback (§7.2) |
| `BadMoveExplainer` validated, planned probes, replayed lines, gated scores and built DTOs in one object | roadmap §1 | one stage per role; the controller alone mutates (D2) |
| P8 and P9 duplicated ply pipelines, material metrics, mate checks and outcome ordering; three sentence producers | roadmap §1 | one template engine for good and bad moves (§8); one material helper (§6.5); one renderer (§13) |
| SUPPORTED / REFUTED / INCONCLUSIVE; REFUTED only when every required check was fully evaluated; REFUTED never means "not a mistake" | P8 §4.1 | adopted (§9.2) |
| "Allowed" is a bounded contrast with the engine-best comparator, not a proof about all moves, uniqueness or intent | P8 §13 | the scope of every claim is explicit (§9.3); planner renders it as qualification (§12) |
| A material loss is stable only after checkmate, or after ≥ 2 further plies with the deficit kept after the last material change; a truncated exchange is INCONCLUSIVE | P8 §12.0, §15 | `material_flow` reports stability with this rule (§6.5) |
| Detector geometry alone never supports a cause; detector-only hypotheses never became public claims | P8 §12.3, G0 §4 | a mechanism claim needs a verified consequence as premise (§8.5) |
| MultiPV is not proof of an only move; at most 2 representative alternatives; `literal_only_move_proven = False` | P9 §2, §6, §20–23 | the parent's survey ranks every legal move, so rank 2 is the engine's best alternative; `only_move_v1` states that scope (D10, §8.5) |
| A quiet best move yields no benefit, by requirement | P9 §25 | an empty explanation body is valid (§12.3) |
| Claim = subject, predicate, objects, confidence (EXACT / FORCED / ENGINE_VERIFIED), scope (LOCAL / TESTED_RESPONSE / REPRESENTATIVE_ALTERNATIVES), evidence ids | P10 §5–§11 | `Claim` with `ProofScope` carrying the same two axes (§9.3) |
| An exact local fact stayed silent when its contrastive claim was refuted (a mating move whose MATE_THREAT was refuted because alternatives also mate) | P10 §25.1 | exact claims are separate templates from contrastive ones (§8.5) |
| Selection: priority tiers, one claim per family, at most 3 claims; no relations active | P11 §8–§10, §3–4 | tiers and one-per-slot kept; relations are first-class (§10, §12) |
| P11 and P12 re-ran P10 validation on every use; P10 validation ran 6–7 times per request | P11 §2, P12 §2, roadmap §1 | verification once; the guard checks structure, never re-verifies (§13.4) |
| English templates per (predicate, confidence, scope), no connectives, UCI only, no Korean or josa | P12 §4–§12 | phrasebooks as data, connectives from the phrasebook, SAN from `move` facts, josa (§13) |
| Probe budgets: P8 ≤ 3 probes in 2 batches; P9 ≤ 4 probes; P2-C1 one extra search; "no probe merely to improve prose" | P8 §9, §17; P9 §11; p2-c1 §7 | 4 extra searches per move (D8); needs come only from verification (§6) |

## 3. Architecture

### 3.1 Stages

```text
AnalysisRequest
  └─ Controller ──open/extend/ensure──▶ FactEngine ──▶ FactTree (revisions)
        │  round r: view = tree.view(rev_r)
        ├─ Observer      view → Judgement(s), Observations              (pure)
        ├─ Hypotheses    view, judgement, observations, claims → Hypothesis*  (pure)
        ├─ Verification  view, hypothesis → Verdict (may say NEEDS_EVIDENCE)   (pure)
        │       needs ──▶ Controller (next round)
        └─ after the last round:
             ClaimGraph → label_v1 → Planner (selection_v1) → Renderer + guard
```

- **Pure** means: a function of its inputs and the pinned view; no clock, no randomness, no I/O,
  no engine, no mutation of the tree.
- The controller is the only stage with effects. Its effects are fact-engine requests.

### 3.2 Package layout

```text
src/calliope/reasoning/
  refs.py          common currency (§4)
  request.py       AnalysisRequest, ReasoningBudget (§5)
  controller.py    rounds, needs → requests (§6)
  observer.py      quality_v1, observations (§7)
  hypotheses/      base protocol and registry (§8); one module per template
  verification.py  Verdict, ProofScope, the round runner (§9)
  graph.py         ClaimGraph (§10)
  labels.py        label_v1 (§11)
  planner.py       ExplanationPlan, selection_v1 (§12)
  render/          renderer, guard, josa, phrasebooks (phrases/ko.toml) (§13)
  storage.py       claim_graph_v1 (§14)
  errors.py        ReasoningError and subclasses (§15)
```

### 3.3 Boundaries
- `calliope.reasoning` imports `calliope.facts` only through its public names: the package
  exports, `TreeView` methods, record types and the helpers `order` and `material_flow`. It never
  reads underscore attributes (`_revisions`, `_session`, …).
- `calliope.facts` never imports `calliope.reasoning`. Neither imports legacy modules.
  `tests/test_package_boundaries.py` gains both rules.
- Facts are trusted (A0 §9). Reasoning never re-validates a fact, replays a board or calls
  python-chess. Move parsing and validation happen in the fact engine (§5).

## 4. Common currency (`refs.py`)

Every stage names chess objects and evidence the same way. All types are frozen dataclasses with
a canonical order and enter the reasoning type registry (§14.1).

```text
MoveSubject(parent: NodeId, child: NodeId)            the move parent → child

PieceRef(piece: PieceId, node: NodeId, square: str)    a physical piece at a node (A0 §4)
SquareRef(square: str)
MoveRef(node: NodeId)                                  the move into `node`
MaterialAmount(points: int, policy: "points_v1")
LineSegment(line: LineId | EngineLineId, first: int, last: int)   role indices, inclusive

FactRef(family: str, target: PositionKey | NodeId, rev: int, path: tuple[str | int, ...])
SearchRef(search_id: str, rank: int | None)            a search, or one of its lines
LineRef = LineSegment
Evidence = FactRef | SearchRef | LineRef
ScopeRef(claim: ClaimId)                               the scope of a claim, as qualification
```

- `FactRef.path` addresses a value inside a record (field names and tuple indices), so a claim
  can point at one pin or one capture, not a whole record.
- `rev` is the revision at which the referenced record or search is visible. Every reference is
  resolvable on any view at a revision ≥ `rev` of the same tree (the tree is append-only).
- Operands are always `PieceRef`, `SquareRef`, `MoveRef`, `MaterialAmount`, `LineSegment`,
  `SearchRef` or small enums. Strings that carry chess meaning (SAN, piece names) are produced
  only by the renderer from fact records.

## 5. Input contract (`request.py`)

```text
AnalysisRequest(
    root: RootSpec,                       # as for OpenRequest (A0 §2.2)
    moves: tuple[str, ...],               # the played line from the root (UCI or SAN)
    target: int,                          # ply index into `moves`, 1-based; R0 handles one target
    profile: EngineProfile,
    budget: ReasoningBudget = ReasoningBudget(),
    language: str = "ko")

ReasoningBudget(max_rounds=3, max_extra_searches=4, max_ensure_nodes=64,
                max_tree_nodes=1000, pv_plies=10, deadline_ms=5000)
```

- **Structural checks** before any fact request: `1 ≤ target ≤ len(moves)`, a known language,
  positive budget values. Failures raise `InvalidAnalysisRequest`.
- **Chess validation goes through the fact engine** (R2-C10). Reasoning does not parse moves:
  round 0 hands `moves[0:target]` to `open` / `extend`, and a fact-engine refusal there
  (illegal or unparsable move, invalid root) is re-raised as `InvalidAnalysisRequest(cause)`.
  Nothing is stored for a refused request.
- **Normalization.** Moves after `target` are dropped. After round 0 the moves are replaced by
  their canonical UCI as recorded in the tree (`TreeView.request`, §6.5), and defaults are
  written out, so equal analyses have equal bytes (§14).

## 6. Controller (`controller.py`)

### 6.1 Round 0: the base tree

With `t = target`, `g = max(0, t − 2)`, and the session budget
`SessionBudget(max_nodes = t + 1 + budget.max_tree_nodes, max_searches = None,
deadline_per_request_ms = budget.deadline_ms)` — a hard bound on the tree, input line and
engine lines included (review 2 N3):
1. `open(OpenRequest(root, families = every registered family, engine = profile,
   root_expansion = FULL if g = 0 else NONE, budget = <the session budget above>))`.
2. If `g > 0`: `extend(PLAYED, moves[0:g], expansion = NONE)` — the prefix gets nodes and facts,
   no engine work.
3. `extend(PLAYED, moves[g:t], start = node after g plies, expansion = FULL)`. The start node
   gets a role entry with this request's expansion (F4-D §6.2), so it is a request node under
   `FULL` (verified in `engine.add_line`).
4. **Standard lines** (§7.3) are read from the view after step 3. One `ensure` of every
   registered family on the nodes of their first `pv_plies` plies follows (R2-C5), so `delta`,
   `pattern_delta`, `patterns` and `pieces` exist on those engine-only nodes. This ensure is
   part of round 0 and outside `max_ensure_nodes`.
5. `rev_0` = the revision after step 4 (or after step 3 when step 4 has nothing to compute and
   commits no revision).

So the grandparent G, the parent P and the child C of the target move are request nodes under
`FULL`: surveyed, compared when the played child is outside the survey, and their lines
attached (F4-D §6.3). P's basis therefore contains the played move unless the comparison was
skipped or irregular (F4-D §7.3), and G's basis grades the opponent's previous move (needed by
MISS, §11). The session deadline applies to every request, round 0 included.

**Invariant R0-I1** (rev. 3). The judgement's search is pinned: `Judgement.search` is the
`SearchRef` read at `V_0`, and every template reads S through that reference, never through
`view.basis()` on a later view. After round 0 the controller issues only `ANALYSIS` extends and
`ensure`. An `ANALYSIS` request may start at or pass through G, P or C (review 2 B5): if it
completes a policy comparison skipped in round 0 (`EngineWork` retries it at every searchable
request node), that later basis is new evidence, counted by the budget (§6.4), and never
re-grades the move. No stage compares a score of that search with a score of S.

### 6.2 Needs

```text
EvidenceNeed =
    FamilyNeed(node: NodeId, family: str)                     → ensure
  | LineNeed(start: NodeId, moves: tuple[str, ...], expansion: ExpansionSpec)
                                                              → extend(ANALYSIS("reasoning"))
```

- `LineNeed` with `NONE` adds nodes and eager facts without engine work, from any node — for
  example a reply at C that no PV contains, or an engine line cut by the deadline
  (`BUDGET_LIMIT`, F4-D §8.1; the moves come from `EngineLineFact.pv`, which keeps the whole PV).
  It still runs the engine if it makes a searchable node a request node with pending engine work
  (a skipped comparison at G or P); §6.4 counts that.
- A `LineNeed` whose expansion has `survey` or `comparison` costs engine searches (F4-D §6.3,
  F4D-R2-N7). Catalogue v1 raises no line need; the search budget exists for later templates.
- **Labels.** Each admitted `LineNeed` becomes one `InputLine` with the label
  `"r" + sha256(canonical encoding of the need)[:16]` and role `ANALYSIS("reasoning")`, so labels
  are deterministic and never continue an unrelated line (`engine._plan`).
- A need that names a node or family the tree does not have is a template bug: the fact engine's
  `InvalidRequestError` propagates as `ReasoningError`, not as a verdict.

### 6.3 Rounds

For `r = 0 … max_rounds − 1`, with `V_r = tree.view(rev_r)`:
1. Observer on `V_0` only (R0-I1): judgements and observations (§7). Observations feed
   proposals; verification reads `V_r`, where line needs may have extended a line.
2. **Fixpoint on `V_r`** (R2-C2). Repeat until a pass adds no hypothesis and decides no verdict:
   - propose: every template, in registry order, on (`V_r`, judgements, observations, claims so
     far); new hypotheses are those whose id is not yet known (§8.3);
   - verify every open hypothesis (new, or `NEEDS_EVIDENCE` and not yet re-verified on `V_r`), in
     id order.
   The catalogue is finite and ids deduplicate, so the fixpoint ends. A premise chain such as
   `material_loss_v1` → `fork_v1` → `removed_defender_v1` resolves within one round when no
   evidence is missing.
3. If `r = max_rounds − 1`: stop. **The last round issues no requests.**
4. Collect the needs of `NEEDS_EVIDENCE` verdicts; deduplicate; order canonically (kind, node,
   moves, family). A need already admitted in an earlier round is not admitted again; the
   verdicts that raise it again become `INCONCLUSIVE(NEED_UNMET)`.
5. Admit needs against the remaining budget, in that order (§6.4). If nothing is admitted, stop.
6. Issue at most one `ensure` (all admitted `FamilyNeed`s) and one `extend` per distinct
   expansion of the admitted line needs (one `ExtendRequest` takes lines with different starts),
   in canonical order. Record each request's outcome in the round (§14.2): the revision it
   committed, `NO_OP` (nothing to compute), or `REFUSED(error type)`. `rev_{r+1}` = the tree's
   revision after them.

When the rounds stop, every verdict still `NEEDS_EVIDENCE` becomes `INCONCLUSIVE` with reason
`ROUND_LIMIT` (rounds exhausted), `BUDGET` (needs not admitted) or `NOT_COMPUTED(<error type>)`
(its request was refused).

**Determinism.** Templates, hypotheses and needs are processed in canonical order, so the rounds,
the requests and the resulting graph do not depend on iteration order, timing or the state of
a shared result store (§6.4). The one exception is the fact engine's deadline: if any revision
of the tree is load-dependent (`TreeView.reproducible()` false), the graph records
`reproducible = false` (§14).

### 6.4 Budget
- `max_extra_searches` (R2-C1, review 2 B6): the number of **distinct search ids first bound
  at a revision after `rev_0`** (`TreeView.searches(node)`, `NodeSearch.rev`), whether the fact
  engine ran them or reused them from a store. Engine calls and store hits (`searches_run`,
  `searches_reused`) are never used: they differ between a cold and a warm store and are zero on
  a `load` (F5-D §6).
- **Admission is by an upper bound.** Before issuing the round's extends, the controller computes
  `planned_search_bound(V_r, request)` (§6.5) for each — an upper bound on the searches the
  request can bind: surveys, policy comparisons (including retries of skipped ones) and
  `ANALYSIS` searches, per F4-D §6.3. The **sum** over the round's extends, all computed on
  `V_r`, must fit the remaining budget (summing keeps an upper bound), so the searches actually
  bound never exceed `max_extra_searches` (review 3 C5).
- `max_ensure_nodes`: distinct nodes named by admitted `FamilyNeed`s after round 0.
- `max_tree_nodes` (default 1000): the session's `max_nodes` beyond the input line (§6.1). The
  fact engine treats the two kinds of nodes differently (review 3 C3):
  - **engine-line attachment** stops at the bound (`BUDGET_LIMIT`), deterministically; round 0
    attaches lines at G, then P, then C, so a small bound can cut S's lines at P — templates then
    see a short line (`LINE_TOO_SHORT`), never a wrong one;
  - **input lines** (every `LineNeed`) are refused whole (`BudgetExceededError`) when they do not
    fit. The controller therefore admits line needs by their **new-node count** (moves not yet
    in the tree, computable from the view) against `max_nodes − |nodes|`, summed over the round.
- `pv_plies`: the base window of a line; R2-D widens a material window up to `2 · pv_plies` to
  reach a stable point. Needs are raised only within that cap.
- `deadline_ms`: passed to the fact engine as `deadline_per_request_ms`; it applies to every
  fact request of the analysis.

Exhausting a budget is not an error. It ends the rounds and records the reason (§9.2).

### 6.5 Facts-side additions (amend A0 §8 and F5-D)

**`TreeView.request(rev)`** returns the normalized request (`OpenRequest`, `ExtendRequest` or
`EnsureRequest`) that committed revision `rev`. F5 already keeps this log for saving
(`FactTree._log`, also after `load`); the accessor makes it public so that normalization (§5)
and the controller's replay (§14.3) do not read private state.

**`planned_search_bound(view: TreeView, request: ExtendRequest) -> int`** (review 2 B6, review 3
C5): an upper bound on the searches the request would bind if issued on the pinned `view`,
computed by the same planning rules as `EngineWork` (F4-D §6.3) without running anything.
"Searchable" and "effective expansion" are evaluated with the request's own role entries
added; comparisons use the policy expansion (`effective_expansion(..., policy=True)`). The
bound counts one survey per searchable request node without a survey; one policy comparison per
searchable request node whose policy expansion has `comparison` and whose comparison set could
grow or whose last comparison was skipped; one `ANALYSIS` search per request node with a child
move in the request when the request's expansion has `comparison`. Surveys of new nodes are assumed regular, so comparisons
they could trigger are included. It lives in the fact engine so that the planning rule has one
implementation.

**Public names.** R1 adds to `calliope.facts.__all__` every name reasoning uses (R2-C10):
`EnsureRequest`, `ExpansionSpec`, `FULL`, `NONE`, `SessionBudget`, `EngineProfile`,
`EngineLineId`, `LineId`, `LineEnd`, `NodeSearch`, `SearchScore`, `order`, `material_flow`,
`MaterialFlow`, `PlyMaterial`, the record types reasoning reads (`EngineSearch`, `EngineLineFact`, `Cp`,
`Mate`, `Wdl`, `MoveFacts`, `StatusFacts`, `MaterialFacts`, the `pieces`, `patterns`, `delta`
and `pattern_delta` records) and the value types (`NotComputed`, `NotApplicable`). Reasoning
imports `calliope.facts` only; the boundary test enforces it (§18.1).

**`material_flow`**

```text
material_flow(view, path: tuple[NodeId, ...]) -> MaterialFlow

MaterialFlow(
    path,
    points_before: (white, black), points_after: (white, black),   # material.points_v1
    plies: tuple[PlyMaterial, ...],      # one per edge of the path, in order
    last_change: int | None,             # ply index of the last ply with a capture or promotion
    stable: Stable | Unstable | NotComputed)

PlyMaterial(index: int, mover: Color,
            capture: Capture | None, promotion: Promotion | None,   # from the `move` record
            points: (white, black))                                  # after this ply
```

- A read helper in `calliope.facts` (module `flow`), like `order`: it reads `material`
  (POSITION) and `move` (EDGE) records and each node's `terminal` header — all present at every
  node, the tier of engine-only nodes included (F4-D §8.2). It stores nothing and changes no
  digest.
- **Per ply** (R2-D review C8): a capture-promotion is one ply with both parts, so its victim is
  never separated from it.
- **Balance**, from a colour's view: `balance(c, i) = (own points − opponent points after ply i)
  − (own points − opponent points before the path)`. A capture of the opponent's queen raises
  the capturer's balance by 9 though its own points do not change (review 2 B1). Reasoning
  measures material only as balance (§8.5).
- `path` must be a parent-to-child chain; otherwise `InvalidRequestError`.
- **Stability** (legacy P8 §12.0), first matching rule (review 3 C6):
  - `NotComputed` if a record is missing;
  - `Unstable(DRAWN_END)` if the path ends in stalemate or an automatic draw (the last node's
    `terminal`) — material decides nothing there;
  - `Stable` if the path ends in checkmate, or at least 2 plies follow `last_change` within the
    path, or `last_change` is `None` and the path has at least 2 plies;
  - `Unstable(CAPTURE_AT_END)` if the last ply captures; else `Unstable(TOO_SHORT)`.
- All three additions are delivered in packet R1 with their own tests.

## 7. Observer (`observer.py`)

### 7.1 Contract

```text
Judgement(subject: MoveSubject, policy: "quality_v1",
          status: DECIDED | INCONCLUSIVE, reason: str | None,
          search: SearchRef | None,              # S, pinned at V_0 (R0-I1)
          played: LineScore | None, best: LineScore | None,
          alternatives: tuple[LineScore, ...],   # every line of S, by rank
          loss: int | None,                      # in 1/2000 expected points
          grade: Grade | None)

LineScore(rank, move, score: Cp | Mate, wdl: Wdl, expected: int)   # expected in 1/2000, mover's view
Grade = BEST < EXCELLENT < GOOD < INACCURACY < MISTAKE < BLUNDER   # "≥ X" means X or worse

Observation(kind: str, version: str, subject: MoveSubject,
            operands: tuple, evidence: tuple[Evidence, ...])
JudgementRef(subject: MoveSubject)        ObservationRef(kind, version, subject, index)
```

Judgements are produced for the target move and for the previous move (the opponent's, at G →
P) when G exists.

### 7.2 `quality_v1`

Inputs: P = `subject.parent`, C = `subject.child`, B = `view.basis(P)` at `V_0`.
1. B is not a search id → `INCONCLUSIVE`, `reason` = B's reason (`BUDGET`, `DEADLINE`,
   `IRREGULAR_SEARCH`, `PARENT_NOT_SEARCHED`, …) or `NOT_APPLICABLE`.
2. S = `view.search(B)`; `Lp` = the line of S whose move is C's incoming move; none →
   `INCONCLUSIVE(NOT_IN_BASIS)`. `L1` = the rank-1 line. A basis is always regular, so every
   line of S has an exact bound (F4-D §5.3); there is no bound qualification (R2-C9).
3. A line without WDL → `INCONCLUSIVE(WDL_UNAVAILABLE)`. Profiles set `UCI_ShowWDL`
   (A0 §12), so this marks a profile error, not a case to estimate. There is no centipawn
   fallback: the logistic cp → win-chance formula needs floating point, and the stored graph
   admits integers only (§14.1).
4. Expected points of a line, from the mover's view (the mover is P's side to move), in units of
   1/2000: `E = 2·win + draw` with `win`, `draw` in permille (Wdl is from White's view, so `win`
   = `white_win` or `black_win`).
5. `loss = E(L1) − E(Lp)`, floored at 0.
6. Grade, first matching rule:
   1. `Lp` is rank 1 → `BEST`. Only rank 1 is BEST (legacy p2-c1 §10).
   2. **Mating:** `L1` and `Lp` are both mates for the mover; `d = Lp.moves − L1.moves`:
      `d = 0` → `EXCELLENT`, `d = 1` → `GOOD`, `d ≤ 3` → `INACCURACY`, else `MISTAKE`
      (legacy `_slower_grade`).
   3. **Being mated:** `L1` and `Lp` are both mates for the opponent; `d = L1.moves − Lp.moves`
      (how much sooner the mover is mated), graded with the same table.
   4. Otherwise by `loss`: `< 40` → `EXCELLENT`; `< 100` → `GOOD`; `< 200` → `INACCURACY`;
      `< 400` → `MISTAKE`; `≥ 400` → `BLUNDER` (0.02 / 0.05 / 0.10 / 0.20 expected points;
      lower bounds inclusive, so BLUNDER is "≥ 0.20" as in chess.com's table).

Every number in a judgement comes from S. `quality_v1` is a policy constant set: changing a band,
the unit, a boundary or the mate rules is `quality_v2`.

**Departures from legacy, deliberate** (R2-C9):
- A missed mate while the played move still wins (both WDL 1000/0/0) has loss 0 and grades
  EXCELLENT; legacy graded it BLUNDER. The expected outcome is unchanged; the miss is the claim
  `mate_missed_v1` (§8.5), not a grade.
- Legacy's cp fallback bands are dropped (see step 3).

Chess.com's model also weights by player rating. Stockfish WDL models engine-strength play, so
`quality_v1` has no rating input; a rating-aware policy would be a later version.

### 7.3 Observations
Observations name groups of facts so that templates do not each re-derive them (legacy P8/P9
duplication). Each has a kind, a version and evidence references. Exact definitions: R2-D §2.
R0 fixes the kinds templates may rely on:
- `standard_lines`: the played line `Lp` and best line `L1` of S, as attached engine lines at P
  (`EngineLineId(P, S, rank)`).
- `line_material`: `material_flow` over the window of each standard line (R2-D §1.3), from the
  baseline R2-D defines.
- `played_edge`: the `move`, `delta` and `pattern_delta` records of the edge P → C.

**One-search story.** Engine-evaluated consequence and comparison claims use only lines of S,
so that the grade, the outcome and the comparison come from one search. Lines of other searches
(C's survey, an `ANALYSIS` search) may support mechanisms and functions, and are never compared
numerically with S. Exact claims (basis `EXACT`) may concern any line (review 3 N3).

**Continued lines** (review 3 N2). When a `LineNeed(NONE)` replays more of an S line's PV (its
moves are exactly `EngineLineFact.pv` beyond the attached plies), the nodes it adds are read as
that S line continued: the material path follows them, and the claim stays about S's line.

An observation is never a claim and is never rendered on its own.

## 8. Hypotheses (`hypotheses/`)

### 8.1 Contract (rev. 3, review 2 B4)

A hypothesis states **what** is claimed, **where** it is evaluated, **what verification must
establish** and **where it came from**. The verification target is fixed when the hypothesis is
proposed, not inferred from the result.

```text
Hypothesis(
    id: HypothesisId,
    template: str, version: str, role: ClaimRole,
    predicate: str,                       # the claimed proposition, e.g. "material_loss"
    subject: MoveSubject,
    context: Context,                     # where the proposition is evaluated
    operands: tuple,                      # identifying operands of the proposition
    target: VerificationTarget,           # what verification must establish (§8.2)
    premises: tuple[PremiseUse, ...],     # claims it builds on, with the scope each must have
    origins: tuple[OriginRef, ...],       # provenance: observations, judgements, claims
    directions: frozenset[Direction])     # FORWARD and/or BACKWARD

Context    = NodeContext(node) | LineContext(segment: LineSegment)
           | SpanContext(segment: LineSegment, first: int, last: int)
OriginRef  = ObservationRef | JudgementRef | ClaimId
PremiseUse(claim: ClaimId, requires: ScopeRequirement)          # §9.4
ClaimRole  = CONSEQUENCE | MECHANISM | CAUSE | FUNCTION | COMPARISON

class HypothesisTemplate(Protocol):
    name: ClassVar[str]; version: ClassVar[str]; role: ClassVar[ClaimRole]
    directions: ClassVar[frozenset[Direction]]
    relations: ClassVar[tuple[RelationDecl, ...]]                 # §10.2
    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]
    def verify(self, h: Hypothesis, view: TreeView) -> Verdict      # §9

ProposeContext(view, subject, judgements, observations, claims)   # claims of any status
```

- **Forward** proposals start from what the move does (observations); **backward** proposals
  start from the judgement and look for an outcome and its mechanism. One template may do both;
  the direction is provenance, not identity (review 2 N1).
- **Premises must be SUPPORTED claims whose effective scope is accepted by `requires`** (§9.4). A
  proposal that violates this is a template bug and is refused by the runner.
- `propose` may read claims of any status (for example to avoid proposing what was refuted).
- Needs are returned by `verify` (`Verdict.needs`); there is no separate `needs` method.

### 8.2 Verification target

```text
VerificationTarget(
    quantifier: Quantifier,
    at: NodeId | LineSegment,             # the node whose moves are quantified, or the line
    population: Population,               # which moves count
    horizon: int | None)                  # plies within which the outcome must hold or appear

Quantifier = SPECIFIC_LINE | PERSISTENCE                          # one line, one span
           | EXISTS_RESPONSE | ALL_RESPONSES                      # the side to move at `at` replies
           | EXISTS_ALTERNATIVE | ALL_ALTERNATIVES                 # the mover's moves at `at`
           | SELECTED_ALTERNATIVES                                # each move of an EXPLICIT list
Population = EXPLICIT(moves) | ENGINE_REPORTED(search_id) | ENGINE_RANKED(search_id) | LEGAL
```

| Quantifier | Meaning | SUPPORTED needs | REFUTED needs |
| --- | --- | --- | --- |
| `SPECIFIC_LINE` | the outcome holds on one given line | that line's records | every condition evaluated, one fails |
| `PERSISTENCE` | a condition holds at every node of a span | every node evaluated and holding | one evaluated node failing |
| `EXISTS_RESPONSE` / `EXISTS_ALTERNATIVE` | some member of the population yields the outcome | one evaluated **witness** in the population | every member evaluated, none yields it |
| `ALL_RESPONSES` / `ALL_ALTERNATIVES` | every member yields it | every member evaluated and yielding it | one evaluated counterexample |
| `SELECTED_ALTERNATIVES` | each move of an `EXPLICIT` list yields it | every listed move evaluated and yielding it | one listed move evaluated against |

`RESPONSES` quantify the moves of the side to move at `at` (usually the opponent at C);
`ALTERNATIVES` quantify the mover's moves at `at` (usually P). `SELECTED_ALTERNATIVES` takes
only an `EXPLICIT` population (review 3 C2).

Populations:
- `EXPLICIT(moves)`: exactly these moves.
- `ENGINE_REPORTED(s)`: the moves whose lines search `s` reported (MultiPV lines, plus played
  moves in a comparison).
- `ENGINE_RANKED(s)`: every legal move, as ranked by the **unrestricted** search `s` (kind
  `SURVEY`): the engine searched all of them and reported the best `multipv`; a move it did not
  report was found no better than its last reported line. It is a statement about the engine's
  search, not an evaluation of each move (review 2 N2).
- `LEGAL`: every legal move (`status.legal_moves`), each evaluated individually.
- Order for `ALL_*`: `ENGINE_REPORTED(s)` ⊑ `ENGINE_RANKED(s)` ⊑ `LEGAL`; `EXPLICIT` is
  comparable only with itself (a superset of moves is stronger).

The **expected outcome** is the predicate with its operands; the target says over what it must
hold. Catalogue v1 uses `SPECIFIC_LINE`, `EXISTS_ALTERNATIVE` and `ALL_ALTERNATIVES` (R2-D).
§8.6 shows that later hypotheses (prophylaxis, plans) fit the same contract.

### 8.3 Identity
`HypothesisId` = sha256 of the canonical encoding (§14.1) of
`(template, version, predicate, subject, context, operands, target, premise claim ids)`.
`origins` and `directions` are provenance and not part of the identity: proposing the same
hypothesis again (from another observation, or in the other direction) adds to them as a sorted
union, so neither proposal order nor direction creates a duplicate. A merged origin that is a
claim must have been **proposed before** this hypothesis's first proposal in the run's total
proposal order (§10.1 `seq`); later claim origins are dropped, so `DERIVED_FROM` stays acyclic
(review 3 C4). `PremiseUse.requires` is fixed by the template for each premise template and
therefore follows from the identity (review 3 N4). `ClaimId` = `HypothesisId`.
A stronger target (for example `ALL_RESPONSES` over `LEGAL` instead of `ENGINE_REPORTED`) is a
different hypothesis with its own id.

### 8.4 Registry
The catalogue is a closed, ordered registry like the fact families: `(name, version)` pairs in a
fixed order. The registry is part of the reasoning build identity (§14.1). Adding, removing or
changing a template changes that identity.

### 8.5 Catalogue v1

Names, roles and targets. Exact definitions: [`reasoning-r2-design.md`](reasoning-r2-design.md)
(R2-D). Material is always the mover's **balance** — own points minus the opponent's, measured as
a change along a line (§6.5) — never the mover's own points alone (review 2 B1).

| Template | Role | Target | Claim (summary) |
| --- | --- | --- | --- |
| `material_loss_v1` | CONSEQUENCE | `SPECIFIC_LINE(Lp)` | the played line's balance falls and stays down, and the best line of the same search does better |
| `material_gain_v1` | CONSEQUENCE | `SPECIFIC_LINE(Lp)` | the played line's balance rises and stays up, measured from before the opponent's last capture |
| `mate_allowed_v1` | CONSEQUENCE | `SPECIFIC_LINE(Lp)` | the played line is mated, the best line is not |
| `mate_delivered_v1` | CONSEQUENCE | `SPECIFIC_LINE` (exact) | the move mates |
| `mate_found_v1` | CONSEQUENCE | `SPECIFIC_LINE(Lp)` | the played line mates |
| `mate_missed_v1` | COMPARISON | `SPECIFIC_LINE(L1)` | the best line mates, the played line does not |
| `fork_v1`, `pin_v1`, `skewer_v1`, `discovery_v1` | MECHANISM | `SPECIFIC_LINE` of the premise | the configuration that targets the lost or won piece arises on the line; EXPLAINS only if the causal check passes (§10.2) |
| `removed_defender_v1` | CAUSE | `SPECIFIC_LINE(Lp)` | the move ended the defence of the piece later lost, and that defence mattered |
| `forcing_v1` | FUNCTION | `SPECIFIC_LINE` (exact) | the move checks, or leaves one reply |
| `only_move_v1` | FUNCTION | `ALL_ALTERNATIVES` at P over `ENGINE_RANKED(S)` | rank 2 of the unrestricted search loses ≥ 0.20 (D10) |
| `sacrifice_offer_v1` | FUNCTION | `EXISTS_ALTERNATIVE` at P over `ENGINE_REPORTED(S)` | the played line gives up material that some alternative keeps — a choice, not a forced loss (review 2 B2) |
| `sacrifice_compensated_v1` | FUNCTION | `SPECIFIC_LINE(Lp)`, premise: offer | the engine ranks the offer best or within 0.02, and the mover is not worse than equal after it |
| `better_move_v1` | COMPARISON | `SPECIFIC_LINE(L1)` | the best line's mate or material outcome is better than the played line's |
| `prevents_v1` | FUNCTION | `ALL_ALTERNATIVES` at P over `ENGINE_REPORTED(S)` | each other reported alternative is mated or loses material, the played line is not |

Rules carried from legacy:
- A mechanism or cause never stands alone: it needs a verified consequence as premise, and it
  EXPLAINS that consequence only after its own causal check (P8 §12.3; §10.2).
- Exact templates (`mate_delivered_v1`, `forcing_v1`) are separate from contrastive ones, so an
  exact fact is never silenced by a refuted contrast (P10 §25.1).
- No template exists merely to improve prose (P8 §17).

### 8.6 Expressibility check: later hypotheses in this contract

Not part of catalogue v1. Written to show that prophylactic and multi-move hypotheses need no
contract change (review 2 acceptance criterion).

**Prophylaxis — "h3 stops …Bg4 pinning the knight."**
- `H1` (CONSEQUENCE): predicate `pattern_available`, context `NodeContext(P′)` where `P′` is the
  position after the best alternative's first move, operands `(RELATIVE_PIN_GEOMETRY, f3)`,
  target `EXISTS_RESPONSE` at `P′` over `LEGAL`, horizon 1.
- `H2` (FUNCTION): predicate `pattern_prevented`, context `NodeContext(C)`, same operands,
  target `ALL_RESPONSES` at `C` over `LEGAL`, horizon 1, premise `H1` with
  `requires = ScopeRequirement(EXACT, {(EXISTS_RESPONSE, LEGAL)})`.
- H1 and H2 are exact geometry on lines no search evaluated (basis `EXACT`); the one-search rule
  (§7.3) concerns only engine-evaluated consequences and comparisons.
- Evidence: one `LineNeed` per legal reply with `NONE` (no engine work) and `FamilyNeed`s for
  `patterns` at the reply nodes.

**Plan — "the knight regroups d2–f1–g3 to attack f5."**
- `H3`: predicate `piece_reaches`, context `SpanContext(Lp, 1, 6)`, operands
  `(PieceRef(knight), SquareRef(g3))`, target `SPECIFIC_LINE`, horizon 6.
- `H4`: predicate `attack_persists`, context `SpanContext(Lp, k, k+4)` from the arrival ply,
  operands `(knight, SquareRef(f5))`, target `PERSISTENCE`, premise `H3`.
- Both are claims about the engine's line (scope `LINE`); a claim that the plan works against all
  defences would use `ALL_RESPONSES` and fail or stay inconclusive within the budget.

## 9. Verification (`verification.py`)

### 9.1 Contract

```text
Verdict(hypothesis: HypothesisId,
        status: SUPPORTED | REFUTED | INCONCLUSIVE | NEEDS_EVIDENCE,
        evidence: tuple[Evidence, ...],
        scope: ProofScope | None,               # what was actually established
        needs: tuple[EvidenceNeed, ...],        # only with NEEDS_EVIDENCE
        findings: tuple,                        # typed records established by verification (R2-D)
        reason: str | None)
```

### 9.2 Status rules
- `SUPPORTED`: every condition of the template holds **and the achieved scope satisfies the
  target** (§9.4).
- `REFUTED`: the claim is false **over the target**, by the "REFUTED needs" column of §8.2 (P8
  §4.1). A missing record or a cut line is never a refutation.
- `INCONCLUSIVE`: a final verdict without decision, with a reason from a closed set:
  `ROUND_LIMIT`, `BUDGET`, `NEED_UNMET`, `NOT_COMPUTED(<fact reason or error type>)`,
  `IRREGULAR_SEARCH`, `DEADLINE`, `UNSTABLE`, `LINE_TOO_SHORT`, `MATE_LINE`, `SCOPE_SHORT`
  (evidence exists but cannot reach the target's scope).
- `NEEDS_EVIDENCE`: not final; `needs` says what would decide it. Whether a need was already
  admitted is the controller's knowledge (§6.3 step 4), not the template's.

### 9.3 Proof scope

```text
ProofScope(basis: EXACT | ENGINE,
           quantifier: Quantifier, population: Population,   # what was established (§8.2)
           witnesses: tuple[str, ...],          # for EXISTS_*: the witness move(s)
           searches: tuple[SearchRef, ...], depth: int | None, multipv: int | None,
           plies: int | None, line_end: LineEnd | None,
           policies: tuple[str, ...])           # e.g. ("points_v1", "quality_v1")

ScopeRequirement(min_basis: EXACT | ENGINE,
                 accepted: tuple[tuple[Quantifier, PopulationKind], ...])
```

`basis` and the pair (`quantifier`, `population`) are the two axes of legacy P10 (confidence,
scope); the quantifier distinguishes "some" from "all" over the same population (review 3 C1).
The planner turns a scope into the qualification of a sentence ("at depth 12", "among the 5
moves the engine reported", "for example after …Nd4").

### 9.4 Target satisfaction, effective scope and premises (review 2 B4, N4; review 3 C1)
- **Satisfaction.** A verdict's scope satisfies its target when:
  - the quantifiers are equal;
  - for `EXISTS_*`: the witness is a member of the target's population (one witness suffices);
  - for `ALL_*`: the scope's population is the target's or stronger (§8.2 order);
  - for `SELECTED_ALTERNATIVES`: the scope's `EXPLICIT` list contains the target's;
  - for `SPECIFIC_LINE` / `PERSISTENCE`: the same line or span, and `plies` reach the horizon.
  `basis` never weakens a target: an `EXACT` target needs an `EXACT` scope.
- **Effective scope.** Scopes of different quantifiers are not ordered, so a claim's effective
  scope is the **set** of its own scope and its premises' effective scopes, deduplicated and
  sorted canonically. The planner qualifies a sentence with every member that the selected
  claims bring in.
- **Premise compatibility.** A premise is usable only if every member of its effective scope is
  accepted by the template's `ScopeRequirement` for that premise: `basis` at least `min_basis`,
  and (`quantifier`, population kind) in `accepted`. Example: a hypothesis about all replies may
  not rest on a premise established on one line only.

### 9.5 Finality
Within one run, a final verdict (`SUPPORTED`, `REFUTED`, `INCONCLUSIVE`) is never revisited.
More evidence is used by proposing a different hypothesis (for example a stronger target), which
has its own id. A new run — a new request, or a rebuild under a new build — re-derives every
verdict (review 2 N5).

## 10. Claim graph (`graph.py`)

### 10.1 Nodes

```text
Claim(id: ClaimId, hypothesis: Hypothesis, verdict: Verdict,
      seq: int,                             # position in the run's total proposal order
      proposed: int, decided: int)          # the rounds of first proposal and final verdict
Label(kind: BRILLIANT | GREAT | MISS, subject, policy: "label_v1",
      grounds: tuple[ClaimId, ...])
```

The judgements and observations are part of the graph document (§14) and are the targets of
`DERIVED_FROM` edges from the claims that name them in `origins`.

### 10.2 Edges

```text
Relation(source: ClaimId, target: ClaimId | ObservationRef | JudgementRef,
         kind: DERIVED_FROM | ASSOCIATED_WITH | EXPLAINS | CAUSES | ENABLES | PREVENTS
             | COMPARES_WITH | QUALIFIES)
RelationDecl(source_template, kind, premise_template)
CausalCheck(kind: str, passed: bool, evidence: tuple[Evidence, ...])   # a finding
```

- **`DERIVED_FROM`** from every claim to each of its `origins` and premises. These edges form a
  DAG; a cycle is a construction error.
- **Semantic edges are tied to instances**: from a `SUPPORTED` claim to one of its own premises,
  of a kind its template declares for that premise's template. No edge is inferred from template
  names alone.
- **Co-occurrence is not explanation** (review 2 B3). A mechanism or cause links to its premise
  with `ASSOCIATED_WITH` unless its verdict carries a passed `CausalCheck`; only then is the edge
  `EXPLAINS` (or `CAUSES`). A template declares `EXPLAINS` / `CAUSES`; at runtime the edge
  falls back to `ASSOCIATED_WITH` when the check fails, so `ASSOCIATED_WITH` needs no
  declaration (review 3 N5). Each template's causal check is defined in R2-D. The planner renders
  only `EXPLAINS` / `CAUSES` chains as reasons (§12).
- `QUALIFIES` is created by the graph builder: an `INCONCLUSIVE` or `REFUTED` claim with a
  premise X gets `QUALIFIES → X`.
- `ENABLES` and `PREVENTS` are reserved for later catalogues; catalogue v1 declares none.
- No other edges exist. In particular nothing links two searches' scores.

### 10.3 Order and identity
Claims are ordered by `seq` (assigned in fixpoint order: round, pass, template registry order,
id); relations by (kind, source, target). The graph's digest is
the sha256 of its canonical encoding (§14.2).

## 11. Labels (`labels.py`, `label_v1`)

| Label | Conditions (all) |
| --- | --- |
| BRILLIANT | grade ∈ {BEST, EXCELLENT}; `sacrifice_compensated_v1` SUPPORTED (its premise `sacrifice_offer_v1` makes the loss a choice; its own check makes it sound) |
| GREAT | grade = BEST; `only_move_v1` SUPPORTED |
| MISS | the previous move's grade ∈ {MISTAKE, BLUNDER}; this move's grade ∈ {INACCURACY, MISTAKE, BLUNDER}; `better_move_v1` SUPPORTED with a mate or a material gain for the mover on the best line |

- At most one label: BRILLIANT, then GREAT, then MISS.
- `grounds` lists the claims used. The label is a node of the graph, with edges to its grounds.
- The grade is computed before any claim exists and never reads claims; `label_v1` reads the
  grade and claims. There is no cycle.
- An unavoidable loss is never BRILLIANT: without an alternative that keeps the material, the
  offer is REFUTED (review 2 B2).
- Chess.com's Book label needs opening data the fact engine does not have; it is not defined.

## 12. Planner (`planner.py`, `selection_v1`)

### 12.1 Contract

```text
ExplanationPlan(subject, policy: "selection_v1",
    judgment: JudgementRef, label: Label | None,
    purpose: tuple[ClaimId, ...],        # FUNCTION claims
    mechanism: tuple[ClaimId, ...],      # CAUSE then MECHANISM claims, as a chain
    consequence: tuple[ClaimId, ...],    # CONSEQUENCE claims
    justification: tuple[ClaimId | LineRef, ...],   # COMPARISON claims and the lines to show
    qualification: tuple[ClaimId | ScopeRef, ...])
```

### 12.2 Rules
- Only `SUPPORTED` claims may fill `purpose`, `mechanism`, `consequence` and `justification`.
- `qualification` holds the effective scopes of the selected claims (`ScopeRef`, §9.4) and at
  most two `INCONCLUSIVE` / `REFUTED` claims linked by `QUALIFIES` to selected claims, chosen by
  role priority then claim id (every consequence spawns several mechanism hypotheses, most of them
  refuted; they are kept in the graph, not all rendered).
- One primary consequence: mate before material, then the larger amount, then claim id.
- The mechanism chain follows `EXPLAINS` / `CAUSES` edges into the primary consequence; at most
  one mechanism and one cause. `ASSOCIATED_WITH` claims are never rendered as reasons (D12).
- At most one comparison and one function claim (legacy P11: one per family, at most 3–4
  assertions). A label's grounds take precedence in their slot, so a label is never rendered
  without its reason (review 3 N1).
- Priority tables are policy constants of `selection_v1`.

### 12.3 Empty and inconclusive
- A judgement `INCONCLUSIVE` produces a plan that states only that the move could not be judged
  and why.
- A decided judgement with no supported claim produces a plan with the judgement alone. That is
  valid output (legacy P9 §25).

## 13. Renderer and claim guard (`render/`)

### 13.1 Phrasebook
- Data files per language (`render/phrases/ko.toml`, read with `tomllib`), versioned
  (`phrases_ko_v1`).
- Keys: `judgment.<grade>`, `label.<label>`, `<template>.<status>`, `scope.<quantifier>.<population kind>`,
  `connective.<name>`.
- An entry is a list of variants. A variant is chosen by `int(h[:8], 16) mod len(variants)`,
  where `h` is the segment source's id (the claim id, or the sha256 of the encoded judgement or
  label), so wording is deterministic and stable per source.
- Slots are typed: `{piece}`, `{square}`, `{move}`, `{amount}`, `{line}`, `{depth}`,
  `{count}`. A variant is valid only if every slot it names has an operand of that type.

### 13.2 Slot values
- `{piece}`: the piece type name from the record at the referenced node (킹, 퀸, 룩, 비숍, 나이트,
  폰) and its square.
- `{move}`: SAN from the `move` record of the referenced edge. SAN's `+` / `#` are facts there
  (`gives_check`, `gives_mate`), unlike in legacy P12 §7.
- `{line}`: SAN of the moves of a line segment, numbered from the node's fullmove number.
- `{amount}`: `MaterialAmount.points` followed by the unit word of the phrasebook (점).
- `{depth}`, `{count}`: the number alone, in digits.

### 13.3 Korean particles
A template writes a particle pair after a slot, e.g. `{piece|이/가}`, `{square|으로/로}`. The
renderer picks the form from the slot value's final sound:
- piece names: fixed table (킹 ㅇ, 퀸 ㄴ, 룩 ㄱ, 비숍 ㅂ, 나이트 vowel, 폰 ㄴ);
- squares and SAN: digits are read in Sino-Korean, by the last digit (1 일 ㄹ, 2 이, 3 삼 ㅁ, 4 사,
  5 오, 6 육 ㄱ, 7 칠 ㄹ, 8 팔 ㄹ), ignoring `+` and `#`; a promotion (`e8=Q`, `e8=Q+`) reads by the
  promoted piece's name from the table above; castling reads as 캐슬링 (ㅇ);
- numbers (`{depth}`, `{count}`): Sino-Korean reading of the whole number — by the last non-zero
  position: a units digit as above; else 십 (ㅂ), 백 (ㄱ), 천 (ㄴ), 만 (ㄴ); `{amount}` ends in its
  unit word (점, ㅁ);
- `이/가`, `은/는`, `을/를`, `과/와`: the first form after any consonant, ㄹ included;
- `으로/로`: `로` after a vowel or ㄹ, `으로` after another consonant.

### 13.4 Guard
The guard is structural; it re-verifies nothing.
- G1. The renderer's inputs are an `ExplanationPlan`, the graph it references and the `TreeView`
  pinned at the graph's final revision. The view is read only through the references of the
  segment's source (its operands and evidence), to format SAN, piece names and move numbers
  (R2-C7).
- G2. Every rendered segment is `Segment(text, source)` where `source` is a claim id, a
  judgement, a label, a scope or `CONNECTIVE`; only phrasebook connectives have no claim.
- G3. Slot values come only from the operands and evidence of the segment's source, through the
  typed formatters of §13.2.
- G4. A plan slot that holds a claim not `SUPPORTED` (outside `qualification`) is refused with
  `GuardError`.

```text
RenderedExplanation(plan_digest, language, phrasebook: "phrases_ko_v1",
                    segments: tuple[Segment, ...])         # text = concatenation
```

## 14. Storage (`storage.py`, `claim_graph_v1`)

### 14.1 Build identity and encoding
- The canonical encoding is `fact_encoding_v1` (F5-D §2) with a closed **reasoning** type
  registry: every type of §4–§13 and every fact type they embed (`NodeId`, `PositionKey`,
  `PieceId`, `LineId`, `EngineLineId`, `Cp`, `Mate`, `Wdl`, `EngineProfile`, `ExpansionSpec`,
  `RootSpec`, …). Integers only; no floats.
- `ReasoningBuild(reasoning_build_version, facts: BuildIdentity, encoding, types digest,
  templates: ((name, version), …), policies: (quality_v1, label_v1, selection_v1),
  phrasebooks: (phrases_ko_v1, …))`.

### 14.2 Document

```text
{ "format": "claim_graph_v1",
  "build": ReasoningBuild, "types": type table,
  "request": AnalysisRequest (normalized),
  "tree": { "digest": TreeView.digest() at the final revision, "rev": final rev,
            "reproducible": bool },
  "rounds": [ { "index", "rev", "admitted": [EvidenceNeed…],
                "requests": [ { "request", "outcome": rev | "NO_OP" | "REFUSED(<error type>)" } … ] } … ],
  "judgements": […], "observations": […], "claims": […], "relations": […], "labels": […],
  "plan": ExplanationPlan, "rendered": RenderedExplanation,
  "digest": sha256 of the canonical encoding of everything above }
```

### 14.3 Load
A graph is loaded together with its fact tree (`fact_tree_v1`, F5):
1. The fact tree loads first (F5-D §6); its digest at `tree.rev` must equal `tree.digest`.
2. The build must equal the current build; otherwise refuse (a rebuild re-runs reasoning).
3. **Replay.** The controller runs in replay mode: for each round it computes its requests as
   usual and, instead of issuing them, checks each against the recorded outcome (R2-C3):
   - a revision: `TreeView.request(rev)` must equal the request in the fact engine's normalized
     form (canonical UCI moves, sorted ensure nodes, families in registry order, resolved
     expansion);
   - `NO_OP`: an `ensure` whose records are all present at that point of the view;
   - `REFUSED(type)`: accepted as recorded. A refusal leaves no trace in the tree, and engine
     failures are not reproducible, so this outcome is trusted from the document; the verdicts
     it affected are re-derived as `INCONCLUSIVE(NOT_COMPUTED(type))`.
4. Every stage re-runs on the pinned views; the encoded result must equal the stored bytes.
5. Any mismatch refuses with `StoredGraphError`.

An **analysis bundle** is the pair (`fact_tree_v1` bytes, `claim_graph_v1` bytes). Since reasoning
is a pure function of the tree and the request, the bundle is reproducible on its own.

## 15. Errors (`errors.py`)
- `ReasoningError` (base); `InvalidAnalysisRequest`; `GuardError`; `StoredGraphError`.
- Fact-engine refusals in round 0 propagate as `InvalidAnalysisRequest(cause)` for input errors
  and `AnalysisFailed(cause)` otherwise (engine errors, budget). In later rounds, a refused
  request leaves the tree unchanged (A0 §2.1), its outcome is recorded (§6.3 step 6), and the
  hypotheses that needed it become `INCONCLUSIVE(NOT_COMPUTED(<error type>))`.
- `InvalidRequestError` from a later-round request means a template raised a malformed need; it
  propagates as `ReasoningError` (a bug, not a chess conclusion).
- Engine failures never become chess conclusions (legacy P8 §15).

## 16. Determinism and reproducibility
- Same `AnalysisRequest`, same engine identity, same builds, reproducible tree → identical
  `claim_graph_v1` bytes.
- No stage reads a clock, environment or random source. Iteration over sets and dicts happens
  only after canonical sorting.
- A load-dependent tree (deadline cuts) yields `reproducible = false` in the graph.

## 17. Cost targets (per target move, aarch64, 2 CPUs)
| Part | Target |
| --- | --- |
| Round 0 engine work (3 surveys, ≤ 2 comparisons at G and P, depth 12) | ≤ 3 s (F5 record: 170–480 ms per survey) |
| Requested engine work | ≤ 4 searches, ≤ `deadline_ms` |
| `ensure` (round 0: standard lines, ≤ 30 nodes; later: ≤ 64 nodes) | ≤ 0.4 s (about 4 ms per node) |
| Observer, hypotheses, verification, graph, planner, renderer | ≤ 200 ms together |
| Graph encoding and digest | ≤ 50 ms |

## 18. Test obligations
1. **Boundaries:** no legacy imports; `calliope.facts` never imports `calliope.reasoning`;
   reasoning imports only `calliope.facts` (its `__all__`) and no python-chess.
2. **`material_flow`:** captures, promotions (a capture-promotion as one ply), castling, en
   passant; the balance of a queen capture (+9 for the capturer); stability rules including
   `DRAWN_END` and no change at all; path validation; per-ply points adding up to the `material`
   records; `DRAWN_END` before the two-ply rule. **`planned_search_bound`:** never below the
   searches a request actually binds, over fixtures for surveys, policy comparison retries at G
   and P and `ANALYSIS` searches, and for several extends of one round summed.
   **`TreeView.request`:** equals the normalized request of every revision, including after a
   `load` (F5).
3. **`quality_v1`:** band boundaries (39/40/41, 99/100/101, 199/200/201, 399/400/401) with
   synthetic WDL; mover perspective for Black; both mate tables; the missed-mate departure;
   every `INCONCLUSIVE` reason; every reference in a judgement names one search.
4. **Controller:** round 0 requests for `t` = 1, 2, > 2 (and that G / P / C are surveyed); the
   round-0 ensure of the standard lines; R0-I1 (no non-`ANALYSIS` extend after round 0; an
   `ANALYSIS` line through P that retries a skipped comparison leaves the judgement and S
   unchanged and is counted in the budget); line needs admitted by new-node count; the fixpoint (a premise chain resolves
   in one round); need ordering, re-raised needs, deterministic labels; budget admission by
   bound search ids; the last round issues nothing; template order shuffled → identical graph;
   **a cold and a warm result store → identical graph bytes**; request outcomes recorded.
5. **Templates (R2):** for each template, positive and negative fixtures on real positions with
   the scripted engine, and the REFUTED-only-if-fully-evaluated rule.
6. **Graph:** `DERIVED_FROM` acyclicity, including edges to origins; semantic edges only from a
   SUPPORTED claim to its own premise with the declared kind; `ASSOCIATED_WITH` without a passed
   causal check, `EXPLAINS` only with one; `QUALIFIES` construction.
6a. **Hypothesis contract:** identity excludes origins and directions (re-proposal merges them;
   a later claim origin is dropped, no cycle); each quantifier's SUPPORTED / REFUTED /
   `SCOPE_SHORT` rules, `EXISTS_*` by one witness; effective scope as a set; a premise with an
   unaccepted scope refused; the §8.6 examples encode and decode.
7. **Labels:** the truth table of §11, including precedence; a forced loss (no alternative keeps
   the material) is never BRILLIANT.
8. **Planner:** only SUPPORTED claims in assertive slots; tie-breaks; empty and inconclusive plans.
9. **Renderer:** variant choice; every slot type; the particle rules for every piece name, every
   rank digit, promotions, castling, `+`/`#`, numbers ending in 0 (10, 20, 100, 1000) and ㄹ;
   guard mutations (an unsupported claim in a slot, a slot value not from its source, a view
   read outside the source's references) refused.
10. **Storage:** round trip, tampering refused, replay mismatch refused, build mismatch refused,
    each request outcome kind (revision, `NO_OP`, `REFUSED`), `save(load(x)) == x`.
11. **Acceptance:** a corpus of curated positions (`tests/reasoning/corpus/`) with expected claim
    sets and labels — at least a blunder allowing a fork, a missed mate, an only move, a
    sacrifice and a quiet best move — under the synthetic engine and real Stockfish 19.

## 19. Delivery packets

| Packet | Content | Gate |
| --- | --- | --- |
| R0-D (this) | architecture, contracts, `quality_v1`, `label_v1`, `selection_v1`, renderer and guard, storage | independent review READY |
| R1 | `refs`, `request`, controller round 0, observer (`quality_v1`, standard lines), facts additions `material_flow`, `TreeView.request`, `planned_search_bound` and public names | READY |
| R2-D | exact definitions of observations v1 and the template catalogue v1 (§8.5) with adversarial cases | READY |
| R2 | hypotheses, verification, rounds and needs, claim graph, labels | READY |
| R3 | planner, Korean phrasebook, renderer, josa, guard | READY |
| R4 | `claim_graph_v1` storage, acceptance corpus, the first end-to-end explanation | READY |

## 20. Questions settled and open

Settled in rev. 2:
1. `g = t − 2` is enough context for round 0 (MISS needs only the previous move's grade).
2. Only move: decided by D10 (rank 2 of the unrestricted search, ≥ 0.20); GREAT follows from it.
3. Bands: chess.com's (D3), with the boundary choice of §7.2 and the documented departures.
4. Consequences and comparisons use only lines of S; lines of other searches support mechanisms and functions only
   (§7.3).
5. Replay-on-load is kept (§14.3), with request outcomes recorded.

Open for R2-D:
6. Legacy P8 §12.3 also required that the comparator line has no equivalent fork. Should
   `fork_v1` (and the other mechanisms) keep that contrast with `L1`?

## 21. Review dispositions (rev. 1 `f69d40c`, independent R0-D review: READY_WITH_CORRECTIONS)

| Finding | Resolution |
| --- | --- |
| C1 budget counted engine calls (`searches_run`): differs cold vs warm store and is zero after `load` | §6.4: distinct search ids first bound after `rev_0`; admission from the view; cold/warm test (§18.4) |
| C2 the stop rule cut premise chains | §6.3 step 2: fixpoint of propose/verify per round; the last round issues no requests |
| C3 replay could not reproduce refused or no-op requests | §6.3 step 6 and §14.2 record request outcomes; §14.3 replay per outcome; normalized-form equality stated |
| C4 R0-I1 too strong: `ANALYSIS` lines can retry a skipped policy comparison | §6.1 corrected invariant; judgement pins S; no line need through G, P, C |
| C5 reply-edge observations needed families outside the tier | §6.1 step 4: round-0 `ensure` of every family on the standard lines within `pv_plies` |
| C6 relations not tied to instances; two impossible example declarations; premises of any status; fork need named `patterns` | §10.2 instance-bound edges, `QUALIFIES` by the builder; §8.4 declarations replaced; §8.1 premises SUPPORTED; `fork_v1` needs `pattern_delta` |
| C7 G1 excluded the view the formatters need | §13.4 G1 includes the pinned view, read only through the source's references |
| C8 particle gaps (promotion, numbers ending in 0, ㄹ for 이/가, Sino-Korean) | §13.2, §13.3 |
| C9 `bounded` always false; legacy mate departures undocumented; 0.20 boundary; grade order | §7.1 `bounded` removed, Grade order; §7.2 being-mated rule added, missed-mate departure documented, lower-inclusive bands |
| C10 input parsing vs "no python-chess"; moves beyond target; `ANALYSIS` labels; public names | §5 validation through the fact engine, truncation; §6.2 hash labels; §6.5 public names; §18.1 |
| N1 `max_nodes` unset | §6.1, §6.2 |
| N2 deadline covers round 0; ≤ 2 comparisons | D8, §6.4, §17 |
| N3 stalemate end | §6.5 `DRAWN_END` |
| N4 group line needs by expansion | §6.3 step 6 |
| N5 undefined refs; `Claim.round`; registry with fact types | §4 `ScopeRef`, §7.1 `JudgementRef` / `ObservationRef`, §10.1 `proposed` / `decided`, §14.1 |
| N6 re-raised needs; `InvalidRequestError` | §6.2, §6.3 step 4, §15 |
| N7 only-move needs the legal move count | §8.4 (`status` at P) |
| N8 fork contrast with the comparator | §20 Q6, for R2-D |
| N9 answers to the review questions | §20 |

## 22. Review dispositions (rev. 2 `5b46090`, second independent R0-D review: NOT_READY)

The second review accepted the architecture and asked for contract corrections before R1.

| Finding | Resolution |
| --- | --- |
| B1 material gain measured as the mover's own points (a queen capture does not raise them) | D13; §6.5 balance per colour and per ply; §8.5 every material claim is a balance |
| B2 BRILLIANT on a forced loss | `sacrifice_offer_v1` (a choice: some alternative keeps the material) and `sacrifice_compensated_v1` (engine-sound, mover not worse than equal); §11 BRILLIANT needs the compensated claim; test in §18.7 |
| B3 pattern co-occurrence turned into EXPLAINS | D12; §10.2 `ASSOCIATED_WITH` unless a causal check passes; planner renders only `EXPLAINS` / `CAUSES` |
| B4 the hypothesis contract could not state what must be verified, over which replies, or its origins | D11; §8.1 predicate, context, target, premises with required scope, origins, directions; §8.2 quantifiers and populations; §8.6 prophylaxis and plan examples; §9.2 status rules per quantifier |
| B5 analysis lines forbidden at G, P, C | §6.1 R0-I1 rev. 3: the judgement's search is pinned; analysis may start anywhere; later bases are evidence, not re-grades |
| B6 admission counted only surveys | §6.4 admission by `planned_search_bound`, a fact-engine upper bound over surveys, comparisons and `ANALYSIS` searches (§6.5) |
| N1 F/B direction vs one template direction | §8.1 `directions` set; §8.3 identity excludes direction and origins |
| N2 `ENGINE_RANKED` overstated | §8.2: the engine searched every move and reported the best; requires an unrestricted `SURVEY`; otherwise `ENGINE_REPORTED` |
| N3 no node bound | `max_tree_nodes`, session `max_nodes` (§5, §6.1, §6.4) |
| N4 premise scope compatibility | §9.4 effective scope, `PremiseUse.requires` |
| N5 re-verification policy | §9.5 finality |
| Acceptance: prophylactic and multi-move hypotheses expressible | §8.6 |

Also applied from the R2-D review of the same date, where it concerned R0-D: per-ply material
(R2-D C8), stability with no material change (C9), observation kinds and `pv_plies` widening (C7),
qualification cap (N8), the `NEED_UNMET` decision left to the controller (N5).

## 23. Review dispositions (rev. 3 `7c5edc6`, re-review: READY_WITH_CORRECTIONS)

The re-review found the six blockers of review 2 resolved and walked the acceptance cases
through the contract (fork → material, sacrifice vs forced loss, §8.6 prophylaxis and plan).

| Finding | Resolution |
| --- | --- |
| C1 scope algebra: `ScopeRequirement` undefined, "some" vs "all" indistinguishable, `LINE` unordered, `EXISTS` keyed on population | §9.3 `ProofScope` with quantifier, population and witnesses; `ScopeRequirement`; §9.4 satisfaction per quantifier (one witness for `EXISTS_*`), effective scope as a set |
| C2 `SELECTED_ALTERNATIVES` with two meanings; no REFUTED rule | §8.2 `EXISTS_ALTERNATIVE`; `SELECTED_ALTERNATIVES` only over `EXPLICIT`; REFUTED column; §8.5 offer → `EXISTS_ALTERNATIVE`, prevents → `ALL_ALTERNATIVES` |
| C3 node budget: input lines are refused whole, attachment is cut; round 0 can cut S's lines | §6.4 both behaviours, admission of line needs by new-node count, `max_tree_nodes` 1000; §6.2 example removed |
| C4 merged origins can create `DERIVED_FROM` cycles | §8.3 only earlier claims (total `seq`, §10.1) |
| C5 `planned_search_bound` signature, evaluation and several extends | §6.5 pinned view, request roles added, policy expansion; §6.4 sum over the round |
| C6 stability before `DRAWN_END`; read set | §6.5 rule order; `terminal` header read |
| C7 stale text (§18.4, §1.1, D order) | fixed |
| N1 label without its ground in the function slot | §12.2 grounds take precedence |
| N2 how continued S lines are read | §7.3 continued lines |
| N3 one-search rule vs exact claims | §7.3 limited to engine-evaluated claims; §8.6 note |
| N4 `requires` not in the identity | §8.3 fixed by the template |
| N5 runtime fallback to `ASSOCIATED_WITH` | §10.2 |

