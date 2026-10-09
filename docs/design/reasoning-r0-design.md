# Reasoning — R0 design: contracts from the fact tree to the first explanation

Status: **rev. 1 — draft for independent R0-D review**.
Date: 2026-10-09. Base: `main @ 460aec4` (fact engine F0–F5 complete).

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
| D8 | **Default budget** per target move: 3 rounds, 4 extra engine searches, 64 `ensure` nodes, 10 PV plies examined, 5 s for requested engine work. |
| D9 | **First explanation = one played move.** Game-level move selection, `opponent_view` (null-move threats), static exchange evaluation and LLM wording are out of R0 (§1.2). |

## 1. Scope

### 1.1 In scope
- The package `calliope.reasoning`, its boundaries and its stages (§3).
- The common currency of references (§4) and every stage contract (§5–§13).
- `quality_v1` (§7.2), `label_v1` (§11), `selection_v1` (§12), the renderer and guard (§13).
- The template catalogue v1 by name, role and evidence (§8.4); exact definitions in R2-D.
- Storage, identity and verification of the claim graph (§14).
- Two facts-side read additions, `material_flow` and `TreeView.request` (§6.5), which amend the
  fact engine's API.

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
| Grade thresholds 0.01 / 0.03 / 0.08 / 0.18 expected score, cp fallback 20 / 50 / 100 / 200; rank 1 always BEST; a negative loss floored, never promoted to BEST; slower mates graded by the mate distance | `move_judge` `MoveJudgementPolicy`, `_slower_grade`; p2-c1 §10 | chess.com bands (D3); rank 1 is the only BEST; mate distance table kept (§7.2); no cp fallback |
| `BadMoveExplainer` validated, planned probes, replayed lines, gated scores and built DTOs in one object | roadmap §1 | one stage per role; the controller alone mutates (D2) |
| P8 and P9 duplicated ply pipelines, material metrics, mate checks and outcome ordering; three sentence producers | roadmap §1 | one template engine for good and bad moves (§8); one material helper (§6.5); one renderer (§13) |
| SUPPORTED / REFUTED / INCONCLUSIVE; REFUTED only when every required check was fully evaluated; REFUTED never means "not a mistake" | P8 §4.1 | adopted (§9.2) |
| "Allowed" is a bounded contrast with the engine-best comparator, not a proof about all moves, uniqueness or intent | P8 §13 | the scope of every claim is explicit (§9.3); planner renders it as qualification (§12) |
| A material loss is stable only after checkmate, or after ≥ 2 further plies with the deficit kept after the last material change; a truncated exchange is INCONCLUSIVE | P8 §12.0, §15 | `material_flow` reports stability with this rule (§6.5) |
| Detector geometry alone never supports a cause; detector-only hypotheses never became public claims | P8 §12.3, G0 §4 | a mechanism claim needs a verified consequence as premise (§8.4) |
| MultiPV is not proof of an only move; at most 2 representative alternatives; `literal_only_move_proven = False` | P9 §2, §6, §20–23 | `only_move` states its coverage, the lines of one search (§8.4, §20 Q2) |
| A quiet best move yields no benefit, by requirement | P9 §25 | an empty explanation body is valid (§12.3) |
| Claim = subject, predicate, objects, confidence (EXACT / FORCED / ENGINE_VERIFIED), scope (LOCAL / TESTED_RESPONSE / REPRESENTATIVE_ALTERNATIVES), evidence ids | P10 §5–§11 | `Claim` with `ProofScope` carrying the same two axes (§9.3) |
| An exact local fact stayed silent when its contrastive claim was refuted (a mating move whose MATE_THREAT was refuted because alternatives also mate) | P10 §25.1 | exact claims are separate templates from contrastive ones (§8.4) |
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
  python-chess for chess knowledge. It may use python-chess only for presentation-neutral
  parsing of its own input (none in R0).

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
                pv_plies=10, deadline_ms=5000)
```

- An `AnalysisRequest` is normalized like a fact request (canonical UCI moves, defaults written
  out) before anything else, so equal requests have equal bytes (§14).
- `target` must name a move that exists; `moves` beyond `target` are accepted and ignored in R0.
- Refusals raise `InvalidAnalysisRequest` before any fact request is made.

## 6. Controller (`controller.py`)

### 6.1 Round 0: the base tree

With `t = target`, `g = max(0, t − 2)`:
1. `open(OpenRequest(root, families = every registered family, engine = profile,
   root_expansion = FULL if g = 0 else NONE, budget = SessionBudget(deadline_per_request_ms =
   budget.deadline_ms)))`.
2. If `g > 0`: `extend(PLAYED, moves[0:g], expansion = NONE)` — the prefix gets nodes and facts,
   no engine work.
3. `extend(PLAYED, moves[g:t], start = node after g plies, expansion = FULL)`.

So the grandparent G, the parent P and the child C of the target move are request nodes under
`FULL`: surveyed, compared when the played child is outside the survey, and their lines
attached (F4-D §6.3). P's basis therefore contains the played move unless the comparison was
skipped or irregular (F4-D §7.3), and G's basis grades the opponent's previous move (needed by
MISS, §11).

**Invariant R0-I1.** After round 0 the controller issues only `ANALYSIS` extends and `ensure`.
`ANALYSIS` roles never change a node's comparison set or basis (F4-D §6.2), so the judgement
read at round 0 stays valid at every later revision.

### 6.2 Needs

```text
EvidenceNeed =
    FamilyNeed(node: NodeId, family: str)                     → ensure
  | LineNeed(start: NodeId, moves: tuple[str, ...], expansion: ExpansionSpec)
                                                              → extend(ANALYSIS("reasoning"))
```

- `LineNeed` with `NONE` adds nodes and eager facts without engine work. It is how verification
  extends an engine line cut by `max_nodes` or the deadline (`BUDGET_LIMIT`, F4-D §8.1) — the
  moves come from `EngineLineFact.pv`, which keeps the whole PV.
- A `LineNeed` whose expansion has `survey` costs engine searches: every node of the line is
  surveyed (F4-D §6.3, F4D-R2-N7). The catalogue v1 (§8.4) raises no such need; the search budget
  exists for later templates.
- **Not available:** one search over every legal move at a node. An `ANALYSIS` line per legal
  move with `comparison` would also survey every child (one survey per legal move), far above
  the budget. Such a search needs a fact-engine amendment (an `ANALYSIS` search without surveys
  of the line nodes); see §20 Q2.

### 6.3 Rounds

For `r = 0 … max_rounds − 1`, with `V_r = tree.view(rev_r)`:
1. Observer on `V_0` only (R0-I1): judgements and observations (§7). Observations feed
   proposals; verification always reads the current view `V_r`, where line needs may have
   extended a line.
2. Propose: every template, in registry order, on (`V_r`, judgements, observations, claims so
   far). New hypotheses are those whose id is not yet known (§8.2).
3. Verify every hypothesis whose status is open (new, or `NEEDS_EVIDENCE` last round), in id
   order.
4. Collect the needs of `NEEDS_EVIDENCE` verdicts; deduplicate; order canonically (kind, node,
   moves).
5. Admit needs against the remaining budget, in that order (§6.4). If nothing is admitted, stop.
6. Issue at most one `ensure` (all admitted `FamilyNeed`s) and one `extend` per distinct
   `(start, expansion)` group of line needs, in canonical order. `rev_{r+1}` = the tree's revision
   after them.

After the last round, every verdict still `NEEDS_EVIDENCE` becomes `INCONCLUSIVE` with reason
`ROUND_LIMIT` or `BUDGET`. Hypotheses proposed in the last round are verified once against the
last view under the same rule.

**Determinism.** The order of templates, hypotheses and needs is canonical, so the rounds, the
requests and the resulting graph do not depend on iteration order or timing. The one exception
is the fact engine's deadline: if any revision of the tree is load-dependent
(`TreeView.reproducible()` false), the graph records `reproducible = false` (§14).

### 6.4 Budget
- `max_extra_searches`: engine searches run by the controller's `ANALYSIS` requests, counted
  from the revision manifests (`searches_run`). A line need is admitted only if its planned
  surveys (one per line node without a survey) fit the remainder.
- `max_ensure_nodes`: distinct nodes named by admitted `FamilyNeed`s over all rounds.
- `pv_plies`: templates examine at most this many plies of a line (§8.4); a need beyond it is
  never raised.
- `deadline_ms`: passed to the fact engine as `deadline_per_request_ms`.

Exhausting a budget is not an error. It ends the rounds and records the reason (§9.2).

### 6.5 Facts-side additions (amend A0 §8 and F5-D)

**`TreeView.request(rev)`** returns the normalized request (`OpenRequest`, `ExtendRequest` or
`EnsureRequest`) that committed revision `rev`. F5 already keeps this log for saving; the
accessor makes it public so that the controller's replay (§14.3) does not read private state.

**`material_flow`**

```text
material_flow(view, path: tuple[NodeId, ...]) -> MaterialFlow

MaterialFlow(
    path, points_before: (white, black), points_after: (white, black),   # material.points_v1
    events: tuple[(index, mover, Capture | Promotion), ...],             # from `move` records
    last_change: int | None,            # path index of the last capture or promotion
    stable: Stable | Unstable | NotComputed)
```

- A read helper in `calliope.facts` (module `flow`), like `order`: it reads only `material`
  (POSITION) and `move` (EDGE) records, which every node carries — the tier of engine-only nodes
  included (F4-D §8.2). It stores nothing and changes no digest.
- `path` must be a parent-to-child chain; otherwise `InvalidRequestError`.
- **Stability** (legacy P8 §12.0): `Stable` iff the path ends in checkmate, or at least 2 plies
  follow `last_change` within the path; `Unstable(reason)` otherwise, with reasons
  `CAPTURE_AT_END` (the last ply captures) and `TOO_SHORT`; `NotComputed` if a record is missing.
- Both additions are delivered in packet R1 with their own tests.

## 7. Observer (`observer.py`)

### 7.1 Contract

```text
Judgement(subject: MoveSubject, policy: "quality_v1",
          status: DECIDED | INCONCLUSIVE, reason: str | None,
          search: SearchRef | None,              # the parent's basis search
          played: LineScore | None, best: LineScore | None,
          alternatives: tuple[LineScore, ...],   # every line of that search, by rank
          loss: int | None,                      # in 1/2000 expected points
          grade: Grade | None, bounded: bool)

LineScore(rank, move, score: Cp | Mate, wdl: Wdl, expected: int)   # expected in 1/2000, mover's view

Observation(kind: str, version: str, subject: MoveSubject,
            operands: tuple, evidence: tuple[Evidence, ...])
```

Judgements are produced for the target move and for the previous move (the opponent's, at G →
P) when G exists.

### 7.2 `quality_v1`

Inputs: P = `subject.parent`, C = `subject.child`, B = `view.basis(P)`.
1. B is not a search id → `INCONCLUSIVE`, `reason` = B's reason (`BUDGET`, `IRREGULAR_SEARCH`,
   `PARENT_NOT_SEARCHED`, …) or `NOT_APPLICABLE`.
2. S = `view.search(B)`; `Lp` = the line of S whose move is C's incoming move; none →
   `INCONCLUSIVE(NOT_IN_BASIS)`. `L1` = the rank-1 line.
3. A line without WDL → `INCONCLUSIVE(WDL_UNAVAILABLE)`. Profiles set `UCI_ShowWDL`
   (A0 §12), so this marks a profile error, not a case to estimate. There is no centipawn
   fallback: the logistic cp → win-chance formula needs floating point, and the stored graph
   admits integers only (§14.1).
4. Expected points of a line, from the mover's view (the mover is P's side to move), in units of
   1/2000: `E = 2·win + draw` with `win`, `draw` in permille (Wdl is from White's view, so `win`
   = `white_win` or `black_win`).
5. `loss = E(L1) − E(Lp)`, floored at 0.
6. Grade:
   - **Mate rule first.** If `L1` is a mate for the mover and `Lp` is a mate for the mover, the
     grade follows the mate distance `d = Lp.moves − L1.moves`: rank 1 → `BEST`; otherwise
     `d = 0` → `EXCELLENT`, `d = 1` → `GOOD`, `d ≤ 3` → `INACCURACY`, else `MISTAKE`
     (legacy `_slower_grade`).
   - Otherwise: rank 1 → `BEST`; `loss ≤ 40` → `EXCELLENT`; `≤ 100` → `GOOD`; `≤ 200` →
     `INACCURACY`; `≤ 400` → `MISTAKE`; else `BLUNDER`. (0.02 / 0.05 / 0.10 / 0.20 expected
     points, upper bounds inclusive.)
7. `bounded` = `Lp` or `L1` has a bound other than `EXACT`. The grade stands; the planner
   qualifies it (§12).

Every number in a judgement comes from S. `quality_v1` is a policy constant set: changing a band,
the unit or the mate table is `quality_v2`.

Chess.com's model also weights by player rating. Stockfish WDL models engine-strength play, so
`quality_v1` has no rating input; a rating-aware policy would be a later version.

### 7.3 Observations
Observations name groups of facts so that templates do not each re-derive them (legacy P8/P9
duplication). Each has a kind, a version and evidence references. The catalogue v1 is defined in
R2-D; R0 fixes the kinds templates may rely on:
- `standard_lines`: the played line `Lp` and best line `L1` of S as attached engine lines at P
  (`EngineLineId(P, S, rank)`), and C's own rank-1 line (the reply line at C).
- `line_material`: `material_flow` over the first `pv_plies` plies of each standard line.
- `piece_flag_change`, `pattern_change`, `defence_ended`: entries of `delta.piece_flags`,
  `pattern_delta` and `DEFENCE_ENDED_UNDER_ATTACK` on the played edge and on the reply edge.

An observation is never a claim and is never rendered on its own.

## 8. Hypotheses (`hypotheses/`)

### 8.1 Contract

```text
Hypothesis(id: HypothesisId, template: str, version: str,
           role: ClaimRole, direction: FORWARD | BACKWARD,
           subject: MoveSubject, operands: tuple,
           premises: tuple[ClaimId, ...])

ClaimRole = CONSEQUENCE | MECHANISM | CAUSE | FUNCTION | COMPARISON

class HypothesisTemplate(Protocol):
    name: ClassVar[str]; version: ClassVar[str]
    role: ClassVar[ClaimRole]; direction: ClassVar[Direction]
    relations: ClassVar[tuple[RelationDecl, ...]]      # edges it may create (§10.2)
    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]
    def needs(self, h: Hypothesis, view: TreeView) -> tuple[EvidenceNeed, ...]
    def verify(self, h: Hypothesis, view: TreeView) -> Verdict

ProposeContext(view, subject, judgements, observations,
               claims: tuple[Claim, ...])              # every verdict so far, any status
```

- **Forward** templates start from what the move does (observations); **backward** templates
  start from the judgement and look for an outcome and its mechanism.
- `propose` may read verified claims and must name the ones it builds on in `premises`. This is
  the extension point of D5: a later catalogue adds templates whose premises are claims of
  earlier templates.

### 8.2 Identity
`HypothesisId` = sha256 of the canonical encoding (§14.1) of
`(template, version, subject, operands, premises)`. Proposing the same hypothesis twice yields
the same id, so rounds never duplicate work. `ClaimId` = `HypothesisId`.

### 8.3 Registry
The catalogue is a closed, ordered registry like the fact families: `(name, version)` pairs in a
fixed order. The registry is part of the reasoning build identity (§14.1). Adding, removing or
changing a template changes that identity.

### 8.4 Catalogue v1

Names, roles and evidence. Exact trigger and verification rules are R2-D's.

| Template | Role | Dir. | Proposed when | Verified by | Needs |
| --- | --- | --- | --- | --- | --- |
| `material_loss_v1` | CONSEQUENCE | B | grade ≥ INACCURACY | `line_material` of `Lp`: the mover's points fall and the flow is `Stable` | `LineNeed` (PV beyond `BUDGET_LIMIT`) |
| `material_gain_v1` | CONSEQUENCE | F/B | `line_material` of `Lp` has a mover capture | the mover's points rise and the flow is `Stable` | as above |
| `mate_allowed_v1` | CONSEQUENCE | B | `Lp.score` is a mate for the opponent | the score, plus the attached line ending `CHECKMATE` when attached that far | — |
| `mate_delivered_v1` | CONSEQUENCE | F | `move.gives_mate` on the played edge | exact (the fact itself; scope LOCAL, EXACT) | — |
| `mate_found_v1` | CONSEQUENCE | F | `Lp.score` is a mate for the mover | the score and the line | — |
| `mate_missed_v1` | COMPARISON | B | `L1` is a mate for the mover, `Lp` is not | both scores, same search | — |
| `fork_v1` | MECHANISM | B/F | a premise consequence (loss or gain) and a new `MULTI_TARGET_ATTACK` on its line | the attacking piece's targets include the piece whose capture makes the consequence | `FamilyNeed(node, "patterns")` on line nodes |
| `pin_v1`, `skewer_v1`, `discovery_v1` | MECHANISM | B/F | as `fork_v1`, with `absolutely_pinned` / `RELATIVE_PIN_GEOMETRY`, `SKEWER_GEOMETRY`, `DISCOVERY_LINE` | the geometry's piece is lost (or wins) in the line | `FamilyNeed(…, "pieces" / "patterns")` |
| `removed_defender_v1` | CAUSE | B | a premise `material_loss_v1` and `DEFENCE_ENDED_UNDER_ATTACK` on the played edge | the undefended piece is the one lost | — |
| `forcing_v1` | FUNCTION | F | the played move gives check, or C has one legal reply | `status` at C (exact) | — |
| `only_move_v1` | FUNCTION | F | grade BEST and every other line of S has `loss > 400` | coverage = the lines of S (`TESTED_ALTERNATIVES`; `ALL_LEGAL_MOVES` only when S's root moves are every legal move) | — |
| `sacrifice_v1` | FUNCTION | F | grade ≤ EXCELLENT and `line_material` of `Lp` shows the mover's points fall | the fall is `Stable` within `pv_plies` while the grade holds | `LineNeed` |
| `better_move_v1` | COMPARISON | B | grade ≥ INACCURACY | the outcome of `L1` (material flow or mate) differs from `Lp`'s in the mover's favour | `LineNeed` |
| `prevents_v1` | FUNCTION | F | grade BEST and other lines of S show a mate or `Stable` loss | each tested alternative line shows it; coverage = the lines tested | `FamilyNeed`, `LineNeed` |

Rules carried from legacy:
- A mechanism or cause never stands alone: it needs a verified consequence as premise (P8 §12.3).
- Exact templates (`mate_delivered_v1`, `forcing_v1`) are separate from contrastive ones, so an
  exact fact is never silenced by a refuted contrast (P10 §25.1).
- No template exists merely to improve prose (P8 §17).

## 9. Verification (`verification.py`)

### 9.1 Contract

```text
Verdict(hypothesis: HypothesisId,
        status: SUPPORTED | REFUTED | INCONCLUSIVE | NEEDS_EVIDENCE,
        evidence: tuple[Evidence, ...],
        scope: ProofScope | None,
        needs: tuple[EvidenceNeed, ...],      # only with NEEDS_EVIDENCE
        reason: str | None)
```

### 9.2 Status rules
- `SUPPORTED`: every condition of the template holds on evidence visible at the view.
- `REFUTED`: a condition fails **and every condition the template requires was fully
  evaluated** (P8 §4.1). A missing record or a cut line is never a refutation.
- `INCONCLUSIVE`: a final verdict without decision, with a reason from a closed set:
  `ROUND_LIMIT`, `BUDGET`, `NOT_COMPUTED(<fact reason>)`, `IRREGULAR_SEARCH`, `UNSTABLE`,
  `LINE_TOO_SHORT`.
- `NEEDS_EVIDENCE`: not final; `needs` says what would decide it. Verification never asks for
  more than its template's `needs` declares.
- Monotone: a `SUPPORTED`, `REFUTED` or `INCONCLUSIVE` verdict is final and is never revisited.

### 9.3 Proof scope

```text
ProofScope(basis: EXACT | ENGINE,
           coverage: LOCAL | LINE | TESTED_ALTERNATIVES | ALL_LEGAL_MOVES,
           searches: tuple[SearchRef, ...], depth: int | None, multipv: int | None,
           plies: int | None, line_end: LineEnd | None,
           policies: tuple[str, ...])          # e.g. ("points_v1", "quality_v1")
```

`basis` and `coverage` are the two axes of legacy P10 (confidence, scope). The planner turns a
scope into the qualification of a sentence ("at depth 12", "among the 5 moves the engine
considered").

## 10. Claim graph (`graph.py`)

### 10.1 Nodes

```text
Claim(id: ClaimId, hypothesis: Hypothesis, verdict: Verdict, round: int)
Label(kind: BRILLIANT | GREAT | MISS, subject, policy: "label_v1",
      grounds: tuple[ClaimId, ...])
```

The judgements and observations are part of the graph document (§14) and may be the targets of
`DERIVED_FROM` edges.

### 10.2 Edges

```text
Relation(source: ClaimId, target: ClaimId | ObservationRef | JudgementRef,
         kind: DERIVED_FROM | CAUSES | ENABLES | EXPLAINS | PREVENTS | COMPARES_WITH | QUALIFIES)
RelationDecl(source_template, kind, target_template)
```

- `DERIVED_FROM` edges are created from `premises` and from the observations a template cites.
  They form a DAG; a cycle is a construction error.
- Semantic edges are created only between `SUPPORTED` claims and only as declared by the source
  template's `relations`. Example declarations: `fork_v1 EXPLAINS material_loss_v1`,
  `removed_defender_v1 CAUSES fork_v1`, `better_move_v1 COMPARES_WITH material_loss_v1`,
  `prevents_v1 PREVENTS mate_allowed_v1`.
- `QUALIFIES` links an `INCONCLUSIVE` or `REFUTED` claim to the supported claim it limits.
- No other edges exist. In particular nothing links two searches' scores.

### 10.3 Order and identity
Claims are ordered by (round, id); relations by (kind, source, target). The graph's digest is the
sha256 of its canonical encoding (§14.2).

## 11. Labels (`labels.py`, `label_v1`)

| Label | Conditions (all) |
| --- | --- |
| BRILLIANT | grade ∈ {BEST, EXCELLENT}; `sacrifice_v1` SUPPORTED |
| GREAT | grade = BEST; `only_move_v1` SUPPORTED |
| MISS | the previous move's grade ∈ {MISTAKE, BLUNDER}; this move's grade ∈ {INACCURACY, MISTAKE, BLUNDER}; `better_move_v1` SUPPORTED with a material gain or a mate for the mover |

- At most one label: BRILLIANT, then GREAT, then MISS.
- `grounds` lists the claims used. The label is a node of the graph, with edges to its grounds.
- The grade is computed before any claim exists and never reads claims; `label_v1` reads the
  grade and claims. There is no cycle.
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
- `qualification` holds the scopes of the selected claims, `bounded` judgements and the
  `INCONCLUSIVE` / `REFUTED` claims linked by `QUALIFIES` to selected claims.
- One primary consequence: mate before material, then the larger amount, then claim id.
- The mechanism chain follows `EXPLAINS` / `CAUSES` edges into the primary consequence; at most
  one mechanism and one cause.
- At most one comparison and one function claim (legacy P11: one per family, at most 3–4
  assertions).
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
- Keys: `judgment.<grade>`, `label.<label>`, `<template>.<status>`, `scope.<coverage>`,
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
- `{amount}`: `MaterialAmount.points` with the unit word of the phrasebook.

### 13.3 Korean particles
A template writes a particle pair after a slot, e.g. `{piece|이/가}`, `{square|으로/로}`. The
renderer picks the form from the slot value's final sound:
- piece names: fixed table (킹 ㅇ, 퀸 ㄴ, 룩 ㄱ, 비숍 ㅂ, 나이트 vowel, 폰 ㄴ);
- squares and SAN: the reading of the last digit (1 일 ㄹ, 2 이, 3 삼 ㅁ, 4 사, 5 오, 6 육 ㄱ, 7 칠 ㄹ,
  8 팔 ㄹ), ignoring `+` and `#`; castling reads as 캐슬링 (ㅇ);
- `으로/로`: `로` after a vowel or ㄹ, `으로` after another consonant.

### 13.4 Guard
The guard is structural; it re-verifies nothing.
- G1. The renderer's only input is an `ExplanationPlan` and the graph it references.
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
  registry: every type of §4–§13. Integers only; no floats.
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
  "rounds": [ { "index", "rev", "admitted": [EvidenceNeed…] } … ],
  "judgements": […], "observations": […], "claims": […], "relations": […], "labels": […],
  "plan": ExplanationPlan, "rendered": RenderedExplanation,
  "digest": sha256 of the canonical encoding of everything above }
```

### 14.3 Load
A graph is loaded together with its fact tree (`fact_tree_v1`, F5):
1. The fact tree loads first (F5-D §6); its digest at `tree.rev` must equal `tree.digest`.
2. The build must equal the current build; otherwise refuse (a rebuild re-runs reasoning).
3. **Replay.** The controller runs in replay mode: for each round it computes its requests as
   usual and requires `TreeView.request(rev)` (§6.5) to return exactly those requests at the
   recorded revisions, instead of issuing them.
4. Every stage re-runs on the pinned views; the encoded result must equal the stored bytes.
5. Any mismatch refuses with `StoredGraphError`.

An **analysis bundle** is the pair (`fact_tree_v1` bytes, `claim_graph_v1` bytes). Since reasoning
is a pure function of the tree and the request, the bundle is reproducible on its own.

## 15. Errors (`errors.py`)
- `ReasoningError` (base); `InvalidAnalysisRequest`; `GuardError`; `StoredGraphError`.
- Fact-engine refusals in round 0 propagate as `AnalysisFailed(cause)`. In later rounds, a
  refused request leaves the tree unchanged (A0 §2.1), and the hypotheses that needed it become
  `INCONCLUSIVE(NOT_COMPUTED(<error type>))`.
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
| Round 0 engine work (3 surveys, ≤ 3 comparisons, depth 12) | ≤ 3 s (F5 record: 170–480 ms per survey) |
| Requested engine work | ≤ 4 searches, ≤ `deadline_ms` |
| `ensure` | ≤ 64 nodes, ≤ 0.3 s (about 4 ms per node) |
| Observer, hypotheses, verification, graph, planner, renderer | ≤ 200 ms together |
| Graph encoding and digest | ≤ 50 ms |

## 18. Test obligations
1. **Boundaries:** no legacy imports; `calliope.facts` never imports `calliope.reasoning`;
   reasoning uses no underscore attribute of fact objects.
2. **`material_flow`:** captures, promotions (with capture), castling, en passant; stability rules;
   path validation; equality with point differences of `material` records.
   **`TreeView.request`:** equals the normalized request of every revision, including after a
   `load` (F5).
3. **`quality_v1`:** band boundaries (39/40/41 …) with synthetic WDL; mover perspective for Black;
   the mate table; every `INCONCLUSIVE` reason; every reference in a judgement names one search.
4. **Controller:** round 0 requests for `t` = 1, 2, > 2; R0-I1 (no non-`ANALYSIS` extend after round
   0); need ordering; budget admission; the stop rule; template order shuffled → identical graph.
5. **Templates (R2):** for each template, positive and negative fixtures on real positions with
   the scripted engine, and the REFUTED-only-if-fully-evaluated rule.
6. **Graph:** `DERIVED_FROM` acyclicity; only declared semantic edges; only between SUPPORTED
   claims.
7. **Labels:** the truth table of §11, including precedence.
8. **Planner:** only SUPPORTED claims in assertive slots; tie-breaks; empty and inconclusive plans.
9. **Renderer:** variant choice; every slot type; the particle table for every piece name, every
   rank digit, castling and `+`/`#`; guard mutations (an unsupported claim in a slot, a slot
   value not from its claim) refused.
10. **Storage:** round trip, tampering refused, replay mismatch refused, build mismatch refused,
    `save(load(x)) == x`.
11. **Acceptance:** a corpus of curated positions (`tests/reasoning/corpus/`) with expected claim
    sets and labels — at least a blunder allowing a fork, a missed mate, an only move, a
    sacrifice and a quiet best move — under the synthetic engine and real Stockfish 19.

## 19. Delivery packets

| Packet | Content | Gate |
| --- | --- | --- |
| R0-D (this) | architecture, contracts, `quality_v1`, `label_v1`, `selection_v1`, renderer and guard, storage | independent review READY |
| R1 | `refs`, `request`, controller round 0, observer (`quality_v1`, standard lines), facts additions `material_flow` and `TreeView.request` | READY |
| R2-D | exact definitions of observations v1 and the template catalogue v1 (§8.4) with adversarial cases | READY |
| R2 | hypotheses, verification, rounds and needs, claim graph, labels | READY |
| R3 | planner, Korean phrasebook, renderer, josa, guard | READY |
| R4 | `claim_graph_v1` storage, acceptance corpus, the first end-to-end explanation | READY |

## 20. Questions for the review
1. Is `g = t − 2` (grandparent) enough context for round 0, given that MISS only needs the
   previous move's grade?
2. `only_move_v1` is proven only over the lines of one search (MultiPV 5 plus played moves). A
   search over every legal move without surveying each child needs a fact-engine amendment
   (§6.2). Should R0 accept GREAT on `TESTED_ALTERNATIVES` coverage, with the qualification
   rendered, or should GREAT wait for that amendment?
3. Are the chess.com bands (0.02 / 0.05 / 0.10 / 0.20) right for engine-strength WDL, which
   saturates earlier than rating-aware models? The legacy bands were 0.01 / 0.03 / 0.08 / 0.18.
4. Should the reply line at C (another search) be allowed as evidence for consequences, or should
   consequences use only lines of S so that the story and the grade come from one search?
5. Is replay-on-load (§14.3) worth its cost against storing the graph with only a digest check?
