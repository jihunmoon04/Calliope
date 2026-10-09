# Calliope redesign — status and roadmap

Status: **living record** (update at the end of every packet). Last update: 2026-10-09,
`main @ bfddc41` (F2, F3-D and F3 merged).

This document records what the redesign has decided and delivered so far, and what comes next.
The binding definitions live in the packet documents it links to. Where this summary and a
packet document disagree, the packet document wins.

## 1. Why the redesign

The MVP (P0–P12, G0, schema 0.2 / 0.3 observations) works, but it grew by adding layers to an
MVP. Three inventories of its code (2026-10-08) found structural problems.

**The same concept was implemented several times.**
- Four independent "replay a line" loops.
- Six or more per-ply record types.
- P8 and P9 duplicated ply pipelines, material metrics, mate checks and outcome ordering.
- Three separate sentence producers.

**Single objects held several roles.**
- `BadMoveExplainer` alone validated judgements, planned and checked probes, replayed lines,
  applied the score gate and built DTOs.
- The rule-to-predicate mapping lived in the validator.

**Validation was repeated instead of trusted.**
- P10 validation ran 6–7 times per request.
- "Rebuild and compare" re-projection was about 40% of the activity cost.

**Engine evidence was mixed into explanation.**
- Scores from different searches were compared (P2-C1 inversion).
- Hash state carried over between searches.
- No position history was sent to the engine.

**Facts and claims blurred.**
- Detector "candidates" drifted toward claims.
- Evaluative words appeared inside facts (`hanging_now` mixed legal and geometric notions).

An earlier plan, the analysis-trace A0 / R1-D (freeze the legacy code, capture its engine calls
and build a parallel path beside it), was abandoned in favour of a ground-up redesign.

## 2. Decisions so far

| Date | Decision |
| --- | --- |
| 2026-10-08 | Ground-up redesign as composable blocks with one role each ("Lego") |
| 2026-10-08 | Analysis-trace A0 / R1-D abandoned (tags `abandoned/analysis-trace-a0`, `abandoned/analysis-trace-r1d`) |
| 2026-10-08 | The public API may break; legacy schema 0.2 / 0.3 is not preserved |
| 2026-10-08 | Scope is analysis and explanation; adapters and `MoveJudge` are reuse candidates only |
| 2026-10-08 | **First block = fact engine**: python-chess and Stockfish normalize input into one tree of frames; facts only; trusted downstream without re-validation; no explanation, hypothesis or cause |
| 2026-10-08 | Legacy is frozen: documents moved to `docs/legacy/` with banners; code stays runnable until replaced; tag `legacy-mvp-g0` |
| 2026-10-08 | Process: design packet → independent review (READY or READY_WITH_CORRECTIONS) → implementation packet → independent review → merge |

The fact-engine decisions taken in discussion are recorded in
[`fact-engine-a0-design.md`](fact-engine-a0-design.md) §14:
- **One tree with roles.** `PLAYED`, `EXPLORED`, `ANALYSIS(by)` and `ENGINE` are roles on
  shared nodes, not separate trees. When the user plays along an engine line, those nodes gain
  input roles.
- **Append-only tree.** One revision per committed request. Readers may pin a revision.
  Take-backs are not modelled.
- **Facts come only from the engine.** A user move and a downstream block's analysis request
  share one path (`extend`); downstream blocks never compute facts themselves.
- **Engine search state.** Each search starts from a fresh state (`ucinewgame` and a cleared
  hash). Finished searches are memoized by the exact engine input. The profile is depth 12 with
  a 2000 ms cap.
- **Comparable searches.** The survey plus a union comparison over input children, with a
  revisioned per-node basis. No arithmetic across searches.
- **Engine lines.** Every PV at a searched input node is attached as tree nodes, until a
  terminal node. MultiPV is 5.
- **Root forms.** All are accepted. History completeness is judged per node, and an unproven
  negative is `HISTORY_UNKNOWN`.
- **Value-ordered geometry.** Included under versioned orders (`piece_order_v1`, `points_v1`).
  `opponent_view` is excluded from v1.

## 3. Delivered

### 3.1 Repository

**Pull requests**

| PR | Content |
| --- | --- |
| #36 | Documentation split: `docs/design/` (current) and `docs/legacy/` (frozen, with banners); `docs/README.md` rules; new top-level README; `CLAUDE.md`; `tests/test_package_boundaries.py` |
| #38 | Fact engine F0 design (#37 was merged into its stacked base by mistake; #38 re-landed it on `main`) |
| #39 | `calliope/__init__` resolves the legacy facade lazily, so `import calliope.facts` loads no legacy module |
| #40 | F1: engine-free core of the fact engine |
| #41 | F2-D design, plus amendments to A0 |
| #42 | This status and roadmap record |
| #43 | F2: geometry families, deltas, `ensure` |
| #44 | F3-D design (patterns, `pattern_delta`), plus amendments to A0 |
| #45 | F3: `patterns`, `pattern_delta` |

**Housekeeping**
- Tags:
  - `legacy-mvp-g0`: the MVP state;
  - `abandoned/*`: the two analysis-trace designs;
  - `archive/*`: 19 MVP branches that were not ancestors of `main`.
- 59 merged or archived remote branches deleted; `main` is the only remote branch.
- Worktrees: only `/home/coder/Calliope` remains.

### 3.2 Fact engine packets

| Packet | Document | State | Review |
| --- | --- | --- | --- |
| F0 (A0 design) | [`fact-engine-a0-design.md`](fact-engine-a0-design.md) | rev. 4 + F2-D amendments | NOT_READY (B1–B3, C1–C9) → READY_WITH_CORRECTIONS (R3-C1–C4) → applied |
| F1 (engine-free core) | [`fact-engine-f1-implementation.md`](fact-engine-f1-implementation.md) | merged | NOT_READY (B1–B2, C1–C3) → READY |
| F2-D (geometry families, deltas, `ensure`) | [`fact-engine-f2-design.md`](fact-engine-f2-design.md) | rev. 2, merged | READY_WITH_CORRECTIONS (C1–C10) → applied |
| F2 (geometry families, deltas, `ensure`) | [`fact-engine-f2-implementation.md`](fact-engine-f2-implementation.md) | rev. 2, merged | READY_WITH_CORRECTIONS (C1–C3) → applied |
| F3-D (patterns, `pattern_delta`) | [`fact-engine-f3-design.md`](fact-engine-f3-design.md) | rev. 2 + errata, merged | READY_WITH_CORRECTIONS (C1–C6) → applied |
| F3 (patterns, `pattern_delta`) | [`fact-engine-f3-implementation.md`](fact-engine-f3-implementation.md) | rev. 2, merged | READY_WITH_CORRECTIONS (C1–C3) → applied |

### 3.3 What exists in code (`src/calliope/facts/`)

**Modules**
- `keys`: `PositionKey`, `RootId`, `NodeId`, `PieceId`.
- `values`: the fact classes and sentinels, `AtLeast`, `Defined`.
- `request`: the request types.
- `board`: the single move canonicalizer and root parsing.
- `identity`: physical piece identity.
- `tree`: the append-only `FactTree`, revisioned `TreeView`, roles, `LineId`, manifest deltas
  and coverage.
- `engine`: `FactEngine.open`, `FactEngine.extend` and `FactEngine.ensure`; one resolver for
  every scope; eager set closed under `requires`.

**Families:**
- F1: `status_v1`, `material_v1`, `draw_v1`, `move_v1`;
- F2: `pieces_v1`, `squares_v1`, `lines_v1`, `pawns_v1`, `king_zone_v1`
  (POSITION), `delta_v1` (EDGE), `same_side_delta_v1` (SPAN);
- F3: `patterns_v1` (POSITION), `pattern_delta_v1` (EDGE).

**Tests**
- `tests/facts/test_fact_engine.py`.
- The auditor `tests/facts/facts_auditor.py`, which keeps two boards per node:
  - the full-history truth;
  - the known history, i.e. what can be proven.
- The fuzz `tests/facts/test_auditor_fuzz.py`:
  - 400 games and 50 endgames;
  - four root forms and branches;
  - about 43k audited nodes.
- F2: the independent geometry auditor `tests/facts/geometry_auditor.py` (own ray walking and
  pawn rules, hooked into every fuzz node), `tests/facts/test_geometry_families.py` and the
  mutation check `tests/facts/test_auditor_mutations.py`.

**Cost:** 0.79 ms per node for the four F1 families (F1 record); F2 figures in
[`fact-engine-f2-implementation.md`](fact-engine-f2-implementation.md) §4.

## 4. Fact engine architecture in brief

```text
open / extend(lines, role) / ensure(nodes, families)        ← the only way facts enter
        │
        ▼
FactTree (append-only, rev per request)
 ├─ positions  PositionKey → POSITION family records (shared by transpositions)
 ├─ nodes      NodeId → header (side to move, fen, clocks, known_plies, history_complete,
 │                          terminal, after_terminal, pieces) + NODE records (draw)
 ├─ edges      child NodeId → EDGE records (move; F2: delta)
 ├─ roles      PLAYED / EXPLORED / ANALYSIS(by) / ENGINE, revision-stamped
 ├─ lines      LineId(kind, by, label, segment) → node path, end status
 ├─ searches   (F4) content-addressed engine searches, keyed by EngineInput
 └─ bases      (F4) revision-stamped comparison basis per node
```

- **Fact classes.** Every record is one of:
  - `RULE`: follows from the rules of chess;
  - `DEFINED`: computed under a versioned definition;
  - `ATTESTED`: an engine report with its provenance.
- **Undefined values** use typed sentinels, never `0` or `false`: `NOT_OBSERVED`,
  `HISTORY_UNKNOWN`, `NOT_APPLICABLE`, `NOT_COMPUTED`, `UNAVAILABLE`, `Absent`.
- **Family connector.** Every family has the same shape: name, version, scope (POSITION, NODE,
  EDGE or SPAN), class, `requires` and `compute(ctx)`. Adding a family takes one module and one
  registry entry.
- **Trust boundary.** Validation happens only at ingestion. Correctness is proven offline by
  the auditor and the fuzz; nothing re-validates at runtime.

## 5. Roadmap

### 5.1 Fact engine: remaining packets

| Packet | Content | Notes carried in |
| --- | --- | --- |
| ~~F2~~ (merged, #43) | Implement `pieces`, `squares`, `lines`, `pawns`, `king`, `delta`, `same_side_delta`; `ensure`; eager set closed under `requires`; scope-aware dependency resolution and context (`parent_records`, `grandparent_records`, piece maps, identity steps); POSITION families fed only a board rebuilt from the `PositionKey` | F2-D §10 test obligations (independent ray-walking auditor, invariants, eager vs `ensure` equivalence, transposition equality, colour mirror, legacy fixtures, §8 defect regressions, mutation check); targets ≤ 2 ms per position, ≤ 1 ms per delta |
| ~~F3-D / F3~~ (merged, #44, #45) | [`fact-engine-f3-design.md`](fact-engine-f3-design.md): `patterns_v1` with `MULTI_TARGET_ATTACK`, `RELATIVE_PIN_GEOMETRY`, `SKEWER_GEOMETRY`, `DISCOVERY_LINE`, `SOLE_DEFENDER`, `BACK_RANK_GEOMETRY`; EDGE family `pattern_delta` with `DEFENCE_ENDED_UNDER_ATTACK` | `ABSOLUTE_PIN`, `UNDEFENDED_ATTACKED` and `ATTACKERS_EXCEED_DEFENDERS` live in `pieces`. F3-D §7 test obligations; targets ≤ 0.3 ms per position and per edge |
| **F4-D / F4** (next) | Stockfish: `EngineProfile` (depth 12, 2000 ms cap, MultiPV 5, 1 thread, `UCI_ShowWDL`), fresh state per search (new `game` object and Clear Hash), engine identity incl. `EvalFile` and `EvalFileSmall`, `EngineInput` (window-start FEN in Stockfish's en passant form + window moves), survey / union comparison / revisioned basis, irregular-search rules, PV attachment to terminal nodes, result store, `max_searches`, deadlines, `ExpansionSpec` per role | copy `start_board` before use (F1R-N3); an engine-only node gaining an input role needs its own path (F2D-N4); eager tier `status`, `material`, `draw`, `move` for engine-only nodes; verify python-chess vs Stockfish en passant keys |
| **F5** | Canonical serialization, digest, tree loading (`facts_build_version`), tape replay of stored searches, cost record | whether the python-chess version in `definitions` belongs to the digest or to `facts_build_version` (F1R-N2); per-node coverage serialization |

### 5.2 Blocks after the fact engine (not designed yet)

These are directions from the 2026-10-08 discussion. They are **not** decisions. Each needs its
own design packet.

1. **Experiment / analysis requests.** The legacy P7 probes (refutation, alternative move,
   ignored threat) become `extend(..., role=ANALYSIS(by))` requests. The requesting block states
   its own expansion and budget.
2. **Reasoning block.**
   - Small rules that each read facts and return a finding (supported / refuted / inconclusive)
     with references to fact records.
   - One rule engine for both good and bad moves.
   - Shared helpers for outcome ordering and material, built only from facts and comparable
     searches.
   - Move-quality judgement is rebuilt here from the comparison basis, never from cross-search
     arithmetic.
3. **Explanation block.**
   - Claims (predicate, operands, confidence, fact references).
   - One selection policy.
   - Data-driven phrasebooks: Korean first, English kept.
   - One renderer for claims and observations.
4. **Application and public API.** A new result model replaces schema 0.2 / 0.3.
5. **Legacy removal.** Once the new blocks cover `analyze_move`, one PR deletes the legacy code,
   tests and `docs/legacy/`. Tag `legacy-mvp-g0` keeps the history.

## 6. Open items

| Item | Where it is resolved |
| --- | --- |
| ~~F1R-N1 cross-scope `requires`~~ | resolved: designed in F2-D §9, implemented in F2 (#43) |
| F1R-N2 python-chess version in the manifest | F5 |
| F1R-N3 mutable `start_board` | F4 copies before use |
| F2D-N4 engine-only node gaining an input role | F4 |
| F2-N1 F2-D §9 lists SPAN `parent_records`, its scope table does not | align F2-D at its next revision (implementation follows the table) |
| F2-C2 note: battery lines map to (−df, dr) under the mirror | add to F2-D §10.4 at its next revision |
| F2-N2 `delta` carries one `FactEntry` class; per-component classes in `COMPONENT_CLASS` | F5 serializes `COMPONENT_CLASS` |
| F2-N5 `pieces` and `squares` each build the attack table | optional sharing in a later cost packet |
| Stockfish 17 vs 19: 7 legacy integration tests fail on Stockfish 17 (goldens were made on 19) | pre-existing, legacy only; F4 fixtures must record their engine build |

## 7. Working notes

- **Python environment:** `/home/coder/Calliope/.venv/bin/python` (python-chess 1.11.2).
- **Tests:**
  - new code: `pytest tests/facts tests/test_package_boundaries.py`;
  - set `FACTS_FUZZ_GAMES` to shorten the fuzz;
  - legacy: `pytest tests/unit tests/golden`.
- **Stockfish** is not on `PATH`.
  - A Stockfish 17 build from an earlier session sits in a temporary scratchpad under
    `/tmp/claude-1002/…` and may disappear.
  - Integration tests read `CALLIOPE_STOCKFISH_PATH`.
  - F4 needs a stable Stockfish install, with its version recorded.
- **Rules for documents and code** (`CLAUDE.md`, `docs/README.md`):
  - only `docs/design/` is current;
  - `docs/legacy/` and legacy code are evidence only;
  - `calliope.facts` and legacy never import each other.
