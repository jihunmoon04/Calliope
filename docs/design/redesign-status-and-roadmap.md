# Calliope redesign — status and roadmap

Status: **living record** (update at the end of every packet). Last update: 2026-10-29, after PF
(PF-D, PF1, PF2; `main @ 3431cfd`); open: the FR framing note (PR #130) awaits the owner (§5.3).
- **Fact engine:** F0–F6 complete; DF1's definitions registry; PF's process-wide result store,
  POSITION records and reservations.
- **Reasoning:** R0-D's packets R1–R4 complete (round 0, hypotheses, catalogue v1, claim graph,
  plan, `phrases_en_v1`, guarded renderer, `claim_graph_v1` storage).
- **Grades:** `quality_v2` merged (Q-D, Q1, QM-D, Q2) and frozen. Q3 is a running monitor.
- **Labels:** `label_v2` merged (LV-D, LV1, MV-D, MV1): FORCED, and the provisional BRILLIANT,
  GREAT and MISS.
- **Explanation accuracy, v2 part 1 and fixes:** EA-D, EA1 (`material_gain_v2`,
  `better_alternative_v1`), EV-D, EV1 (draws by checks, `best_stops_reply_v1`), EF-D, EF1 (trades,
  concessions, `exposed_v1`, check answers) and DF-D, DF1 (definitions, units, the verdict model)
  merged.
- **Application:** `calliope_result_v1` (AR-D, AR1), the static viewer, the local analysis server
  and the viewer's analyse panel (AS-D, AS1, AS2), the ply cache's cost (CC-D, CC1) and a game's
  analysis time (PF-D, PF1, PF2: −66% on five games) merged.
- **Agent:** `calliope.agent`, an MCP server for commentary agents (AG-D, AG1–AG8, MS, CV4, BL, PW,
  LM) merged: read and exploration tools, the game path, the digest and `board`, propositions and
  the sentence check, Korean commentary guides up to `commentary_ko_v7`, the viewer's AI commentary
  panel and the MCP App.
- **Legacy:** removed (LR-D, LR1); the MVP is history at tag `legacy-final`.

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
| 2026-10-10 | English is the default and first language ([R3-D](reasoning-r3-design.md) H0); Korean is a later phrasebook |
| 2026-10-10 | BRILLIANT deferred to v2 ([R0-D](reasoning-r0-design.md) §28); `label_v2` ships it as provisional `brilliant_p2` |
| 2026-10-11 | Grading frozen: `quality_v2` with `human_lichess_2026_08_v2`; Q3 a running monitor ([Q3](reasoning-q3-implementation.md) §5); engine profile kept at `d12_mpv5_v1` (§6.3) |
| 2026-10-12 | The analysis server: one user, local, the viewer extended, PGN input only ([AS-D](application-server-design.md) §0) |
| 2026-10-12 | The MVP is removed; its observation sections are dropped ([LR-D](legacy-removal-design.md) §9); history at tag `legacy-final` |
| 2026-10-13 | The LLM narrator and question answering come after explanation v2 ([EV-D](reasoning-explanation-v2-design.md) §8) |
| 2026-10-14 | Calliope gets tools and an MCP server for agents; existing features are first tidied for agent use (§5.3) |
| 2026-10-14 | First the known faults and the definitions (EF-D, DF-D); line continuation later |
| 2026-10-15 | The agent server: a standard MCP server, stdio first; commentary in Korean; the agent comments only from what the server provides and may ask it to explore lines; interpretations allowed, marked as such ([AG-D](agent-mcp-design.md) §0, O1–O7) |
| 2026-10-15 | Game ids derived from the game, records created once; a rolling-window budget ([AG4-D](agent-ag4-design.md), O2, O3) |
| 2026-10-17 | The ply cache writes without the replay and keeps loaded pairs ([CC-D](application-cache-cost-design.md) Q1–Q3; estimate factor 60, §11) |
| 2026-10-18 | After AG8, simplify what the agent is given and asked: one meaning once ([AG8-D](agent-ag8-design.md) §11, [MS framing](agent-ms-framing.md)) |
| 2026-10-19 | The digest keeps Calliope's Korean sentences; their wording is fixed instead ([PW-D](agent-pw-design.md) §0) |
| 2026-10-19 | More moments and longer commentary: inaccuracies as moments, up to 16 ([LM-D](agent-lm-design.md)) |
| 2026-10-29 | The tools' run time first: each search once per process, POSITION records kept, the played positions surveyed ahead on a second engine, on by default ([PF-D](application-performance-design.md) §1, §8) |

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
| #46 | Status update after F2 / F3 |
| #47 | F4-D design (Stockfish searches, basis, engine lines), Stockfish 19 setup, amendments to A0 |
| #48 | F4a: engine boundary (`calliope.facts.search`) |
| #49 | Status update after F4a |
| #50 | F4b: engine work in the tree (surveys, comparisons, basis, engine lines) |
| #51–#54 | F4b record, F5-D, F5 (encoding, digest, saved trees, store persistence), status after F5 |
| #55–#60 | Reasoning: R0-D contracts, R2-D catalogue v1 (rev. 11 in #58), R1 foundation, R2a machinery, R2b catalogue v1 and `label_v1` |
| #61, #74, #77, #78 | R3-D (plan, English phrasebook, renderer, guard), R3, R3-D §17 wording (owner), A2 `IMMEDIATE_PLIES = 2` |
| #62–#66, #71 | Grades: Q-D, Q1, QM-D, Q2 (`human_lichess_2026_08_v2`), Q3 acceptance tool and monitor entries |
| #67, #69 | F6-D, F6: `exchange` (`see_v1`) and on-request families |
| #68, #70, #72, #73 | Labels: LV-D, LV1 (`label_v2`), MV-D, MV1 (`miss_p2`, `missed_gain_v1`) |
| #75, #76 | R4-D, R4: `claim_graph_v1` storage and replay, acceptance corpus, `tools/explain_game` |
| #79–#81 | AR-D, AR1 (`calliope_result_v1`, `render.trace`, `explain_game --json`), the static viewer |
| #82–#84 | AS-D, AS1 (`calliope.server`, `tools/serve`), AS2 (the viewer's analyse panel) |
| #85, #86 | LR-D, LR1: the MVP removed, tag `legacy-final` |
| #87, #88 | EA-D, EA1: `material_gain_v2`, `better_alternative_v1` |
| #89, #90 | EV-D, EV1: `checks_draw_v1`, `checks_draw_missed_v1`, `best_stops_reply_v1`, `plan.detail` |
| #91 | Status after EV1, the roadmap refreshed, the test baseline |
| #92–#94 | EF-D and DF-D, EF1 (trades, concessions, `exposed_v1`, check answers), DF1 (definitions registry, units, the verdict model) |
| #95–#100 | AG-D (the MCP server), AG1 (read tools, exploration, the metered budget), AG2 (propositions, the sentence check, stored commentary), AG3-D, AG3a (the viewer's AI commentary panel), AG3b (the MCP App, `show_game`) |
| #101–#105 | AG4-D, AG4 (content game ids, the rolling-window budget, bounded work state), AG4-D AM1 (limit values), AG5-D, AG5 (guidance an agent reaches by itself) |
| #106–#110 | AG6-D, AG6a (digests, `detail`), CC-D, CC1 (the ply cache's cost), AG6b (the game path: `analyze_game`, `game_overview`) |
| #111–#114 | AG7-D, AG7 (`commentary_ko_v2`), the AG8 framing and AG8-D, AG8 (`board`, `proves`) |
| #115–#119 | MS framing, MS-D, MS-a (piece relations, `sacrifice_compensated_v2`), MS-b (`board_v2`), MS-c (citing by handle, `commentary_ko_v4`) |
| #120, #121 | CV4-D, CV4 (`commentary_check_v4`) |
| #124, #125 | BL-D, BL (a blunder's reason from the facts, issue #123) |
| #126, #127 | PW-D, PW (numbered lines and plain words, issue #122) |
| #128, #129 | LM-D, LM (more moments, longer commentary, `commentary_ko_v7`) |
| #131–#133 | PF-D, PF1 (one result store and POSITION records per process), PF2 (reservations, surveys ahead) |

**Housekeeping**
- Tags:
  - `legacy-final`: the last state with the MVP code (LR1);
  - `legacy-mvp-g0`: the MVP state;
  - `abandoned/*`: the two analysis-trace designs;
  - `archive/*`: 19 MVP branches that were not ancestors of `main`.
- 59 merged or archived remote branches deleted on 2026-10-08. Since then the packet branches
  stay on the remote after their merge: 44 besides `main` on 2026-10-29, one of them (`design/fr`,
  PR #130) not merged.
- Worktrees: `/home/coder/Calliope`, besides temporary ones that other sessions keep in their
  scratchpads; the PF worktrees were removed after the merge (2026-10-29).

### 3.2 Fact engine packets

Packets from R0-D on (reasoning, grades, labels, explanation, application, agent, legacy removal) are
listed with their reviews in the design index, [`README.md`](README.md).


| Packet | Document | State | Review |
| --- | --- | --- | --- |
| F0 (A0 design) | [`fact-engine-a0-design.md`](fact-engine-a0-design.md) | rev. 4 + F2-D amendments | NOT_READY (B1–B3, C1–C9) → READY_WITH_CORRECTIONS (R3-C1–C4) → applied |
| F1 (engine-free core) | [`fact-engine-f1-implementation.md`](fact-engine-f1-implementation.md) | merged | NOT_READY (B1–B2, C1–C3) → READY |
| F2-D (geometry families, deltas, `ensure`) | [`fact-engine-f2-design.md`](fact-engine-f2-design.md) | rev. 2, merged | READY_WITH_CORRECTIONS (C1–C10) → applied |
| F2 (geometry families, deltas, `ensure`) | [`fact-engine-f2-implementation.md`](fact-engine-f2-implementation.md) | rev. 2, merged | READY_WITH_CORRECTIONS (C1–C3) → applied |
| F3-D (patterns, `pattern_delta`) | [`fact-engine-f3-design.md`](fact-engine-f3-design.md) | rev. 2 + errata, merged | READY_WITH_CORRECTIONS (C1–C6) → applied |
| F3 (patterns, `pattern_delta`) | [`fact-engine-f3-implementation.md`](fact-engine-f3-implementation.md) | rev. 2, merged | READY_WITH_CORRECTIONS (C1–C3) → applied |
| F4-D (Stockfish searches, basis, engine lines) | [`fact-engine-f4-design.md`](fact-engine-f4-design.md) | rev. 3, merged | NOT_READY (B1–B2, C1–C10) → READY_WITH_CORRECTIONS (R2-C1–C8) → applied |
| F4a (engine boundary) | [`fact-engine-f4a-implementation.md`](fact-engine-f4a-implementation.md) | rev. 2, merged | READY_WITH_CORRECTIONS (C1–C8) → applied |
| F4b (engine work in the tree) | [`fact-engine-f4b-implementation.md`](fact-engine-f4b-implementation.md) | rev. 2, merged | READY_WITH_CORRECTIONS (C1–C4) → applied |
| F5-D (encoding, digest, saved trees) | [`fact-engine-f5-design.md`](fact-engine-f5-design.md) | rev. 3, merged (#52) | NOT_READY → READY_WITH_CORRECTIONS (R2-C1–C6) → applied |
| F5 (encoding, digest, saved trees, store persistence) | [`fact-engine-f5-implementation.md`](fact-engine-f5-implementation.md) | rev. 2, merged (#53) | READY_WITH_CORRECTIONS (C1–C5) → applied |

### 3.3 What exists in code

#### `calliope.facts`

**Modules**
- `keys`: `PositionKey`, `RootId`, `NodeId`, `PieceId`.
- `values`: the fact classes and sentinels, `AtLeast`, `Defined`.
- `request`: the request types.
- `board`: the single move canonicalizer and root parsing.
- `identity`: physical piece identity.
- `tree`: the append-only `FactTree`, revisioned `TreeView`, roles, `LineId`, manifest deltas
  and coverage.
- `engine`: `FactEngine.open`, `FactEngine.extend` and `FactEngine.ensure`; one resolver for
  every scope; eager set closed under `requires`; `survey_stored` and `stored_results` (F4-D AM1,
  AG4), `prefetch_survey` (PF2).
- `search` (F4a): `EnginePort`, the raw-UCI `StockfishEngine`, `EngineProfile` /
  `EngineIdentity`, `EngineInput` windows, search records and normalization, `SearchId`,
  `EngineResultStore` (PF: an LRU bound, reservations and waits), the per-session `Searcher`,
  `search_bound_s`, `ScriptedEngine`.
- `position_records` (PF1): `PositionRecords`, POSITION family records kept per process and
  shared by the trees built with it.
- `definitions` (DF1): the fact engine's entries of the definitions registry.
- `engine_work` (F4b): the planned engine work of a request — surveys, policy comparisons,
  `ANALYSIS` searches, the basis table, attach-once engine lines; `open` / `extend` run it when
  the session has an engine profile.
- `storage` (F5): the closed type registry, canonical encoding `fact_encoding_v1`, the
  per-revision digest chain (`TreeView.digest()`, `reproducible()`), the build identity,
  saved trees `fact_tree_v1` (`FactEngine.load`, `FactEngine.rebuild`), `export`, and the
  persisted result store `engine_store_v1`.
- `flow` (R1): material along a path of the tree, a read helper over `material` and `move`;
  `settle_v1` (DF1: plies after the last capture or promotion).
- `planning` (R1): `planned_search_bound`, an upper bound on the searches an `extend` binds.

**Families:**
- F1: `status_v1`, `material_v1`, `draw_v1`, `move_v1`;
- F2: `pieces_v1`, `squares_v1`, `lines_v1`, `pawns_v1`, `king_zone_v1`
  (POSITION), `delta_v1` (EDGE), `same_side_delta_v1` (SPAN);
- F3: `patterns_v1` (POSITION), `pattern_delta_v1` (EDGE);
- F6: `exchange` (POSITION, `see_v1`, computed on request only).

**Tests**
- `tests/facts/test_fact_engine.py`.
- The auditor `tests/facts/facts_auditor.py`, which keeps two boards per node:
  - the full-history truth;
  - the known history, i.e. what can be proven.
- The fuzz `tests/facts/test_auditor_fuzz.py`:
  - 400 games and 50 endgames;
  - four root forms and branches;
  - about 43k audited nodes.
- F4a / F4b: `tests/facts/search/` — adapter tests against a fake UCI engine
  (`fake_uci.py`), record tests, tree-integration tests with a deterministic synthetic engine
  (`synthetic.py`) and the engine auditor (`engine_auditor.py`), and real-Stockfish acceptance
  gated on `CALLIOPE_STOCKFISH_PATH` (including a full game built with a cold and a warm store).
- F2: the independent geometry auditor `tests/facts/geometry_auditor.py` (own ray walking and
  pawn rules, hooked into every fuzz node), `tests/facts/test_geometry_families.py` and the
  mutation check `tests/facts/test_auditor_mutations.py`.
- F5: `tests/facts/search/test_storage.py` (encoding, digest, round trips, isolation,
  refusals, rebuild, store persistence, the build-version guard) and a real-Stockfish saved
  game round trip.

**Cost:** 0.79 ms per node for the four F1 families (F1 record); F2 figures in
[`fact-engine-f2-implementation.md`](fact-engine-f2-implementation.md) §4; the whole-engine
cost record against legacy in [`fact-engine-f5-implementation.md`](fact-engine-f5-implementation.md)
§5 (a 20-ply game with engine lines: cold 13 s, warm 2 s; saved in 79 KB; loaded in 3 s
without the engine).


#### `calliope.reasoning`

- Contracts (R0-D): `request` (`AnalysisRequest`, budget), `refs`, `controller` (the only stage
  that changes the tree), `observer` (judgement, grade, observations), `hypotheses`,
  `verification`, `runner` (rounds to a fixpoint), `graph` (claim graph), `needs`, `errors`.
- `grading`: `quality_v1`, `quality_v2` with the curve tables in `curves/`
  (`human_lichess_2026_08_v2`, `chesscom_lichess_v1`); `labels`: `label_v2`.
- `catalogue`: R2-D's 21 templates and those of LV-D, MV-D, EA-D, EV-D, EF-D and MS-D; shared
  line definitions in `lines`, typed findings in `findings`.
- `piece_relations` (MS-a, BL): what stands between pieces at a move or at a ply of an engine
  line, by piece identity (`piece_relations_v2`).
- `definitions` (DF1): the definitions registry (units, statuses, thresholds, templates), the
  fact engine's entries included.
- `planner` (`selection_v1`, `plan.detail`), `render` (`phrases_en_v1` in `render/phrases/en.toml`,
  the guard, `explain`, `trace`, `plan_analysis`).
- `storage` (`claim_graph_v1` save, load and replay), `build` (the reasoning build identity),
  `encoding`.

#### `calliope.results`

`calliope_result_v1`: `game_result` builds one game's document from its per-ply analyses and
cross-checks them against the game; the optional per-ply `analysis` (DF1); the combined document's
`ai_commentary` with `display_v1` (AG2, AG3a); `schema_errors` checks a stored document against
the shipped schemas (`results/schema/`: `calliope_result_v1`, and `calliope_view_v1` for
`show_game`, AG6b).

#### `calliope.server`

`pipeline` (PGN intake, grading from the headers, per-ply requests, `analyse_ply`,
`analyse_game` with the process's result store and POSITION records, PF1, and `Prefetch`, the
uncached plies' positions surveyed ahead on a second engine, PF2), `cache` (one bundle pair per
normalized ply request, reused by replay; written without the replay and kept loaded within
bounds, CC1), `jobs` (content-named, queued in memory, one at a time, persisted on disk),
`commentary` (accepted AI commentary in a sidecar store, `display_v1`; stale when the graph
changes, PF-D §12), `web` (HTTP on loopback: `POST /api/games`, `GET /api/games`, a game's status,
result and commentary, the viewer at `/`), `files` (atomic writes). Input is a PGN game; there is
no position (FEN + move) entry point.

#### `calliope.agent`

The MCP server for commentary agents (AG-D), on stdio through the official SDK (`server`). The
session (`session`) holds the process's games (`games`: ids derived from the game, records
created once), trees, handles (`handles`) and the rolling-window budget (`budget`), and answers the
tools: `open_game`, `ply`, `judge_move`, `facts`, `explore`, `detail`, `definitions`,
`analyze_game` (background jobs, `jobs`), `game_overview`, `submit_commentary`, `commentary`,
`show_game` (`agent_tools_v5`). What an agent is shown: the digest (`digest`), `board` (`board`: threats,
weaknesses, lost defences, held pieces, the same reply; `board_v3`) and the remarks' `proves`
(`remarks`), facts as JSON (`projection`). What it submits: propositions verified field by field
(`propositions`) and the sentence check (`sentences`, `commentary_check_v5`), Korean refusals
(`messages_ko`). Prompts and guides in `prompts/` (`commentary_ko_v7`), the agent build and
vocabulary in `build` and `definitions`.

#### Tools and viewer

- `tools/explain_game` (a game explained ply by ply; `--json`, `--bundles`,
  `--with-commentary`, `--prefetch-engines`), `tools/serve` (the server; `--prefetch-engines`,
  `--max-store-searches`, `--max-position-records`), `tools/mcp` (the agent's MCP server, its
  limits as options), `tools/definitions` (the registry as `definitions_v1` JSON),
  `tools/calibrate_curve` (Q2, Q3), `tools/label_bench` (LV1, MV1), `tools/perf_acceptance`
  (PF-D §6).
- `viewer/index.html`: a static page for `calliope_result_v1` (board, evaluation bar, move list,
  text with highlighted segments, phone layout), the analyse panel against the server, the AI
  commentary panel (AG3a) and, served by `tools/mcp`, the MCP App behind `show_game` (AG3b).

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
| ~~F4-D, F4a, F4b~~ (merged, #47, #48, #50) | [`fact-engine-f4-design.md`](fact-engine-f4-design.md): raw-UCI Stockfish 19 adapter with fresh state per search (`ucinewgame`, Clear Hash, pinned options), identity with the binary sha256 and offered options, `EngineInput` with the legal en passant square, survey / policy comparison / ordered basis, `ROOT` role and per-role expansions, attach-once engine lines, tiers and role gain, budget and deadline, result store | F4a: [`fact-engine-f4a-implementation.md`](fact-engine-f4a-implementation.md). F4b notes: copy `start_board` before use (F1R-N3); role gain incl. line start nodes (F2D-N4); tier = base ∩ eager set |
| ~~F5-D, F5~~ (merged, #52, #53) | Canonical serialization, digest, tree loading (`facts_build_version`), tape replay of stored searches, cost record | whether the python-chess version in `definitions` belongs to the digest or to `facts_build_version` (F1R-N2); per-node coverage serialization |
| ~~F6-D, F6~~ (merged, #67, #69) | [`fact-engine-f6-design.md`](fact-engine-f6-design.md): `exchange` (`see_v1`), static exchange evaluation; families computed on request only | used by EV1's RESCUES / DEFENDS / COVERS |

No fact-engine packet is open.

### 5.2 Blocks after the fact engine: delivered

The 2026-10-08 directions (analysis requests, a reasoning block, an explanation block, an
application API, legacy removal) are delivered by these packets; the binding text is each
packet's document, listed in [`README.md`](README.md).

| Direction | Delivered by |
| --- | --- |
| Analysis requests as `extend(..., role=ANALYSIS(by))` | R0-D, R1, R2a: the controller and the runner's rounds |
| Reasoning: findings with fact references, one rule engine, judgement from the basis | R0-D, R2-D, R2a, R2b (catalogue v1); grades Q-D … Q2 (`quality_v2`, frozen); labels LV-D, LV1, MV-D, MV1 (`label_v2`) |
| Explanation: claims, one selection policy, phrasebooks, one renderer | R3-D, R3 (`selection_v1`, `phrases_en_v1`, guard; English first, owner 2026-10-10), R4-D, R4 (`claim_graph_v1`); accuracy EA-D, EA1; v2 part 1 EV-D, EV1 |
| Application and public API | AR-D, AR1 (`calliope_result_v1`), the static viewer, AS-D, AS1, AS2 (local server and analyse panel; checked by the owner on the phone, 2026-10-12) |
| Legacy removal | LR-D, LR1 (tag `legacy-final`) |

### 5.3 Agent tools and an MCP server (owner, 2026-10-14): delivered, and what is open

The block is delivered (§3.1, #92–#129): EF-D, EF1 and DF-D, DF1 first tidied the faults and the
definitions, then AG-D and its packets built `calliope.agent` (§3.3); each packet's document and
reviews are listed in [`README.md`](README.md). The gaps known on 2026-10-14 (a trial with an agent
loop over Calliope's facts, run outside this repository and since deleted, on four moves of the
owner's 829/808 game), and where they stand:

- **No position entry point.** Still true for the server, which takes PGN games only. The agent
  opens a game (`open_game`) and judges any legal move at one of its positions (`judge_move`).
- **No stable JSON view of facts.** `agent/projection` (AG-D §3) and the digest (AG6-D §3).
- **One engine path.** The agent's lines and judgements come from the fact tree's searches; it
  comments only from what the server provides (AG-D O3).
- **Threats and comparisons.** `board` (AG8-D) shows threats, weaknesses, lost defences and the
  same reply after the best move; the other parts of AG-D O4 wait until an agent needs them.
- **Terms.** The definitions registry (DF1) and the `definitions` tool (AG5).
- **Latency.** The rolling-window budget (AG4-D) bounds a tool's work; PF cut a game's analysis
  by 66% on five games (PF2 §4).

Open, for the owner:

- **FR framing** (free commentary with evidence, PR #130, not merged): directions E1 (surface
  rules into the guide), E2 (more verified material per move), E3 (a stronger writer), owner
  questions Q1–Q3.
- **Issue #123** (a hung queen left out of the commentary) is still open after BL.
- **AG3b:** the owner's check of the MCP App in HIMARI v3 waits until it supports MCP Apps.
- **A follow-up after PW:** an attack that existed before the move, read as new (PW §4, §5;
  trial criterion 1 accepted unmet by the owner).

### 5.4 Postponed

Recorded in the packets; not scheduled.

| Item | Where |
| --- | --- |
| Line continuation: a search from the end of a PV that stops before the material settles (73 of 179 plies' `OPEN` lines) | EV-D §0.4, §8 |
| Positional reasons; proving a perpetual; "stops" checked by the engine; a draw saved by checks for the defender; square-colour weakness; opening names; the decisive event across exchanges | EV-D §8, EA-D §8 |
| The LLM narrator and question answering (after explanation v2, owner 2026-10-13) | EV-D §8 |
| Korean (`phrases_ko_v1`); engine numbers in the text (H6) | R3-D §11 |
| Game-level judgements (accuracy, key moments, phases); several languages per document | AR-D §8 |
| Parallel plies, partial results, cancel / delete / evict, a grading override in the POST, the Caddy site (owner, root) | AS-D §11, §12 |
| BRILLIANT v2; MISS against Mistake; a time-class threshold for bullet | R0-D §28, MV-D §9 |
| A conversion from chess.com's judgements; a rating-gap offset; a mate floor (grading is frozen) | Q-D §11 |
| More than one ahead engine (measured first on a host with more cores); the agent's own prefetch | PF-D §4.3, §4.4 |
| Threat facts beyond `board`, a played-against-alternative view, non-adjacent trades | AG-D §0 (O4) |

## 6. Open items

| Item | Where it is resolved |
| --- | --- |
| ~~F1R-N1 cross-scope `requires`~~ | resolved: designed in F2-D §9, implemented in F2 (#43) |
| ~~F1R-N2 python-chess version in the manifest~~ | resolved in F5: part of the build identity |
| F1R-N3 mutable `start_board` | F4 copies before use |
| F2D-N4 engine-only node gaining an input role | F4 |
| F2-N1 F2-D §9 lists SPAN `parent_records`, its scope table does not | align F2-D at its next revision (implementation follows the table) |
| F2-C2 note: battery lines map to (−df, dr) under the mirror | add to F2-D §10.4 at its next revision |
| ~~F2-N2 `delta` per-component classes~~ | resolved in F5: `component_classes` in the closed type registry |
| F2-N5 `pieces` and `squares` each build the attack table | optional sharing in a later cost packet |
| ~~Stockfish 17 vs 19: 7 legacy integration tests fail on Stockfish 17~~ | resolved 2026-10-09: with the Stockfish 19 build all 127 legacy integration tests pass |
| R4 §4: the planning test with a 5 ms deadline depends on timing (EV1 §3.3: two planning tests failed under load and passed alone) | a fact-engine packet; recorded decisions would make it deterministic |
| Remote branches: 43 merged packet branches remain (§3.1) | housekeeping, owner's choice |

## 7. Working notes

- **Python environment:** `/home/coder/Calliope/.venv/bin/python` (python-chess 1.11.2).
- **Tests:**
  - `pytest tests` (the MVP's suites were removed by LR1); with `CALLIOPE_STOCKFISH_PATH` set
    the whole suite takes about 24 minutes on this 2-core host; run it alone, since timing tests
    slow down under load; `pytest-xdist` is not installed, so it runs serially;
  - set `FACTS_FUZZ_GAMES` to shorten the fuzz;
  - baseline (2026-10-29, PF2 `ea76c40`, the tree of `main @ 3431cfd`, Stockfish 19, run alone):
    1859 passed, 0 failed, 23 min 30 s. The previous baseline was 1097 passed at `9f5033c`
    (2026-10-14).
- **Stockfish 19** (chosen 2026-10-09):
  - binary `/home/coder/opt/stockfish/stockfish`, built from `~/opt/stockfish-src` (tag
    `sf_19`, commit `edb0d9d`, `ARCH=armv8`, g++ 13.3; log `~/opt/stockfish-build.log`);
  - sha256 `70773580789eff48f8b889f72427babebc111130efa3e5415c6844eddb1fbb5d`; network
    `nn-1a298aa575a0.nnue` embedded;
  - symlinked as `.venv/bin/stockfish` (found by `which stockfish` in the activated venv);
  - tests read `CALLIOPE_STOCKFISH_PATH`; set it to the binary path;
  - all 127 legacy integration tests passed with it (2026-10-09; history at `legacy-final`).
- **Rules for documents and code** (`CLAUDE.md`, `docs/README.md`):
  - only `docs/design/` is current;
  - the MVP is history at tag `legacy-final`, evidence only (LR-D);
  - `src/calliope/` holds only the redesign packages.
