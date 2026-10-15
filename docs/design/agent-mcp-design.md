# Agent — AG-D design: an MCP server for commentary agents

Status: **rev. 2 — independent review NOT_READY (B1–B4) applied (§12)**.
Date: 2026-10-15. Base: `main @ d0658ac` (EF1, DF1 merged). Inputs:
[`reasoning-definitions-design.md`](reasoning-definitions-design.md) (DF-D: the registry, the
verdict model, `analysis`); [`reasoning-explanation-fixes-design.md`](reasoning-explanation-fixes-design.md)
(EF-D: `ATTRIBUTED`); [`application-server-design.md`](application-server-design.md) (AS-D: the
pipeline, the ply cache, the HTTP API); [`application-result-design.md`](application-result-design.md)
(AR-D: `calliope_result_v1`, G7); status and roadmap §5.3.

An agent (an LLM with tools) writes the commentary; Calliope gives it the facts, the judgements
and the claims, explores and judges moves on request, tells it how to reason and how to check
itself, and accepts its commentary only on verified propositions. The trial of 2026-10-14 (status
and roadmap §5.3) showed the agent verifying forward lines well and inventing support for "why"
("the engine says so", its own line attributed to the engine). Calliope cannot read Korean, so it
cannot check that a free sentence follows from its sources; it can check structured propositions.
The design therefore separates **what is claimed** (propositions, verified by Calliope) from **how
it is said** (Korean sentences that cite them).

## 0. Owner decisions (2026-10-15)

| # | Decision |
| --- | --- |
| O1 | A standard MCP server (Model Context Protocol), stdio first, so that any MCP client can use it |
| O2 | The commentary is in Korean |
| O3 | The agent comments only from what the server provides, and may ask the server to explore new lines |
| O4 | Threat facts, a played-against-alternative view and non-adjacent trades wait until an agent needs them |
| O5 | (later) the viewer gains an AI commentary panel; the server may later offer it as an MCP App |
| O6 | Sentences that state the agent's interpretation are allowed, marked as such (method B, §5.3) |

## 1. Decisions

| # | Decision |
| --- | --- |
| A1 | **A new package `calliope.agent`** beside `facts`, `reasoning`, `results`, `server`. It imports their public names only (a boundary test), and nothing imports it. `CLAUDE.md` and `tests/test_package_boundaries.py` gain it (Q1). |
| A2 | **The official MCP Python SDK** (`mcp`, pinned in AG1; 2.3.0 today: `mcp.server.mcpserver.MCPServer`, tools, prompts, resources, `run("stdio")`) as an optional dependency group `agent`; the core keeps python-chess as its only dependency. |
| A3 | **Prompts** say how to reason and check (§6); **tools** serve data, judge moves and explore lines (§3); one tool takes the commentary back (§5); **resources** hold the registry and the Korean glossary (§7). Every safety condition is enforced by the server; prompts only guide. |
| A4 | **Two layers in a commentary.** *Propositions* are structured statements of a closed set of kinds (§4), each verified by Calliope against the facts, searches and claims it served. *Sentences* are Korean text that cite propositions. A sentence's check is a source check (`SOURCE_VERIFIED`), never a check of its wording. |
| A5 | **Two classes of sentence.** A `verified` sentence states what its propositions say; its numbers and moves must come from them (§5.4). An `interpretation` sentence (O6) states the agent's reading, cites the propositions it rests on, and is stored and shown as the agent's interpretation, never as Calliope-verified. |
| A6 | **Stored analyses are read-only.** Exploration and judging run in session trees of their own, opened with the engine (§3.4); a stored claim's evidence never changes. One engine path: the fact engine with the profile `d12_mpv5_v1`. |
| A7 | **Accepted commentary is a sidecar**, never written into `result.json` (§8); the HTTP server serves it from its own route. |
| A8 | **Two processes may share the data directory**: the ply cache and the commentary store take a per-key inter-process lock and write through unique temporary files (§9). |

## 2. Shape

```text
MCP client ── stdio ──  python -m tools.mcp  (calliope.agent: one session per connection)
                          │
  prompts: calliope_commentary, calliope_check     resources: definitions_v1, glossary_ko_v1
  tools:   open_game, ply, judge_move, facts, explore, definitions,
           submit_commentary, commentary
                          │
       read-only:  server.pipeline + PlyCache (stored analyses, AS-D §4)
       session:    exploration trees (FactEngine + one Stockfish slot), handle table, budget
       writes:     the commentary store (sidecar, §8)
```

A **session** is one stdio connection: its open games, the handles it served (§3.6), its search
budget, its exploration trees and its submissions. Only accepted commentary outlives it.

## 3. Tools

Answers are JSON (MCP structured content) in DF-D's vocabulary: positions by `from_root`, numbers
with the `calliope_result_v1` units, sentinels with their codes. Every citable item carries `"ref"`.

| Tool | Arguments | Answer |
| --- | --- | --- |
| `open_game` | `pgn`, or `fen` and `moves`; `plies` (a range, default all) | `game` (the session's id for the game), the moves, and per ply the move, grade, label and Calliope's text; plies not cached are analysed (progress notifications) |
| `ply` | `game`, `ply` | the ply's record with its `analysis` (DF-D §4.3): judgements, observations, every claim with scope, effective scopes, evidence, relations, checks and findings |
| `judge_move` | `game`, `position`, `move` | Calliope's judgement of any legal move at a served position — played or not — as `ply` answers it: grade, label, best move, claims (§3.3) |
| `facts` | `game`, `position`, `families` | the position's fact records, projected as DF-D §4.4; piece identities as `{"piece", "color", "origin"}` (§3.7) |
| `explore` | `game`, `position`, `moves` (SAN or UCI, may be empty), `search` (bool) | the line from the position: each ply's `move` record and material balance, the end position's `status`, `pieces`, `exchange`, and with `search` the end's survey (MultiPV 5, depth 12: scores, WDL, expected points, PVs attached); `"by": "agent"` on the plies the agent gave, `"by": "engine"` on PV plies |
| `definitions` | `ids`, `kind` or `query` | registry entries (DF-D §2.1) |
| `submit_commentary` | §5 | accepted (with its id) or refused with every violation |
| `commentary` | `game`, `ply` | the accepted commentaries of the ply, newest first |

### 3.1 `ply` is the main entry

The agent starts from Calliope's judgement and claims; facts, exploration and judging are for
checking and for what the catalogue does not cover. `ply` returns the claim graph in full,
REFUTED and INCONCLUSIVE claims and failed checks included (DF-D §4.1).

### 3.2 Positions

A position argument is `{"ply": n, "at": "before" | "after"}` (P or C of an analysed ply) or
`{"from_root": [uci…]}`: the game's root and legal moves from it — the played moves, a variation,
or a path an earlier answer served.

### 3.3 `judge_move`

`judge_move` builds a `ParsedGame` of the game's start and the path to the position + move and
runs its last ply through the pipeline's per-ply path (`normalized_ply`, `PlyCache.key`,
`analyse_ply`, `PlyCache.put`), as `analyse_game` does for a played ply. The reasoner already takes any root and any legal line (DF1 §2); a move not played is
judged as one that was. The engine work counts against the session budget (§3.5) only when the
analysis is not cached.

### 3.4 Exploration trees (review B2)

Stored analyses are loaded engine-less for replay (`PlyCache` → `load(FactEngine(), …)`) and are
never extended. Exploration runs in the session's own trees:

- **One tree per (game, start position).** `FactEngine(engine = the session's slot, store = the
  session's result store)`; `open(OpenRequest(root = RootSpec(fen = the game's start, moves = the
  path to the position), engine = the profile, root_expansion = NONE))` — the path is the root's
  history, so repetitions are known.
- **A line** is `extend(ExtendRequest((InputLine("agent-<n>", moves, start = the node),),
  analysis("agent"), expansion))`, `expansion` = survey and attached lines when `search`, none
  otherwise. Exploring further from an explored node extends the same tree.
- **An empty line with `search`** (the position itself; `extend` refuses an empty line): the
  tree is opened with `root_expansion = ExpansionSpec(survey = True, comparison = False,
  attach_lines = True)`. A tree opened earlier without the root search is replaced by a new tree
  for the same start opened with it; handles to the old tree stay bound to it (§3.6). An empty
  line without `search` returns the position's facts (as `facts`).
- **Identity across trees** is the path from the game's root: a node of an exploration tree and a
  node of a stored analysis with the same `from_root` are the same position, and the fact engine,
  being deterministic, computes the same facts for them. Searches agree when their inputs agree
  (F4-D: memoized by the exact engine input, fresh engine state per search).

### 3.5 Budget

Only the agent's own engine work is counted: exploration searches and `judge_move` analyses that
the cache cannot answer. Defaults (Q2): `max_searches = 40`, `max_nodes = 2000` per session, each
search under the profile's time cap. Opening a game whose plies are not cached is the analysis the
HTTP server would run and is not counted. A refused request answers with the fact engine's reason
code (`BUDGET`, …) and the budget left.

### 3.6 Handles

Every citable item has `"ref"`: `j<n>` a judgement, `c<n>` a claim, `f<n>` a fact (a record or a
path within it), `s<n>` a search line (score, WDL, PV), `x<n>` an explored line. A handle is bound
to the session and to its **source**: the game key, then either a stored analysis (the ply, the
tree digest and the reasoning build digest) or an exploration tree (its id and revision), then the
item's address (position, family and path; claim id; search and rank; line and plies). A handle
resolves only in the session that served it and only to that source; a handle of another session
or game is refused.

### 3.7 Piece identities

Fact records name pieces by physical identity (`PieceId`, `w.N.g1`: colour, original type, the
square it started on), useful to an agent following a piece along a line. The facts tool projects
it as `{"piece": "knight", "color": "white", "origin": "g1"}` with its current square; the
registry gains the entry `piece_identity`. `calliope_result_v1` keeps AR-D G3.

## 4. Propositions (review B1)

A proposition is `{"id", "kind", <fields>, "refs": [handles]}`. Each kind is a registry entry
(`proposition.<kind>`) with its fields and its verification rule. Calliope re-reads the cited
items and the facts behind them and verifies every field; a proposition is VERIFIED or REFUSED
(with the field that failed). Values carry their units (DF-D §3.1); positions are `from_root` paths
of the cited source.

| Kind | Fields | Verified when |
| --- | --- | --- |
| `judgement` | `move` (position, uci), `grade`, `label`, `best_move` | they equal the cited judgement (`ply` or `judge_move`) |
| `claim` | `claim` (a `c` handle), `use` (§4.1) | the use fits the claim's status, checks and relations |
| `engine_score` | search line, `move`, `score` (`cp_white` or `mate_white`), `depth` | they equal the search record |
| `engine_line` | search line, `moves` (a prefix of the PV) | the PV starts with them |
| `material` | a line (engine or explored), `from`, `to` (plies), `balance` (`points_v1`, for a named side) | `material_flow` over that path gives it |
| `attack` | position, `attacker` (square), `target` (square) | the target's square is in the attacker's `pieces.attacks.enemy` |
| `defence` | position, `defender`, `defended` | the defender is in the defended piece's `pieces.defenders` |
| `exposed` | position, `piece` (square), `exposed` (bool), `gain` (`points_v1`) | `exposed_v1` and `exchange.gain` agree (EF-D §4) |
| `pin` | position, `pinned`, `pinner` | `pieces.absolutely_pinned` names the pinner |
| `check` | position, `checkers` | `status.in_check` and `status.checkers` |
| `legal_moves` | position, `moves` or `count` | `status.legal_moves` |
| `pattern` | position, `pattern` (a `patterns_v1` list), the participants | the configuration is in the record — reported as a configuration (`configuration_only`) |
| `after_reply` | `reply`, `after_a` (the position after move a and the reply), `after_b` (after b and the same reply), `proposition_a`, `proposition_b` (nested, any kind above at those positions) | both nested propositions verify at their positions: the same reply compared after two moves (EV-D's DEFENDS / COVERS form) |
| `explored_line` | an `x` handle, `moves` | the session explored that line; the agent's plies are named as such |
| `definition` | a registry id | the entry exists |

### 4.1 Uses of a claim

| Use | Accepted when |
| --- | --- |
| `result` | SUPPORTED, a consequence; a material claim's `ATTRIBUTED` passed |
| `line_fact` | SUPPORTED (any checks): what the line shows |
| `mechanism` | SUPPORTED with an `explains` or `causes` relation |
| `associated` | SUPPORTED with `associated_with` only: the configuration occurs |
| `comparison` | a comparison claim, SUPPORTED |
| `uncertain` | INCONCLUSIVE: could not be confirmed |
| `not_the_case` | REFUTED |

## 5. `submit_commentary`

### 5.1 The submission

```text
{"game", "ply" | "position" + "move",       # a played ply, or a move judged with judge_move
 "language": "ko",
 "agent": {"name", "model"?},
 "propositions": [Proposition],
 "sentences": [{"text", "class": "verified" | "interpretation", "cites": [proposition ids]}]}
```

The commentary's subject must have a `judgement` proposition: what the commentary says of the
move's grade and label equals Calliope's.

### 5.2 Propositions

Every proposition is verified (§4); any REFUSED proposition refuses the submission, with the
proposition, the field and the expected value.

### 5.3 Sentences

- **S1** `language` is `ko`; 1–12 sentences, each at most 300 characters; at least one `verified`.
- **S2** every sentence cites at least one proposition of the submission.
- **S3** a `verified` sentence's **numbers** — Arabic digits with a sign or decimal point — each
  equal a value of a cited proposition, compared with its unit and perspective: a score as pawns
  from White's view (`cp / 100`, one or two decimals, sign kept) or a mate distance; points of
  material; a ply or move number of a cited move; a count. A number with no matching value is a
  violation.
- **S4** a `verified` sentence's **moves** — tokens that parse as SAN, with or without a move
  number — each parse at a cited proposition's position (the move's own position, or a position
  of a cited line) and are a move of that proposition.
- **S5** an `interpretation` sentence may hold numbers and moves only as S3–S4 allow; it is not
  verified further, and is stored and shown as the agent's interpretation (O6).
- **S6** a sentence citing an `explored_line` or an `after_reply` built on one says the line is
  the agent's (the stored citation carries `by: agent`; the viewer marks it).

What an accepted commentary guarantees: every proposition was verified against Calliope's data;
every number and move of a verified sentence comes from its propositions; interpretation is marked.
It does not guarantee that the Korean wording states exactly what the propositions state — that
is the `SOURCE_VERIFIED` level, the registry entry `commentary_check_v1` says so.

## 6. Prompts: how to reason and how to check

Two MCP prompts in Korean, versioned data (`agent/prompts/*.md`), registry entries
(`prompt.commentary_ko_v1`, `prompt.check_ko_v1`):

**`calliope_commentary(game, ply)`**
1. `ply` (or `judge_move` for a move asked about): the grade, the label, the best move, the claims.
2. For each claim you use, read its scope, checks and effective scopes; look terms up with
   `definitions`. A SUPPORTED claim with a failed `ATTRIBUTED` is a fact of the engine line, not
   the move's achievement; a `specific_line` scope covers one line, not every reply; a pattern is a
   configuration, not a tactic that works.
3. Answer "why" by comparison: what the better move does that this one does not — the same reply
   after both (`after_reply`), the piece that becomes exposed, the material along each line. Check
   with `facts`, `explore`, `judge_move` before you write.
4. Turn what you checked into propositions; write each `verified` sentence from its propositions
   only; write your reading as `interpretation`, citing what it rests on; say what is not
   established as not established.
5. Submit; on refusal, fix the named propositions and sentences and submit again.

**`calliope_check(game, ply)`** — before submitting: every claim of the judgement and the grade
match; every number and move of a verified sentence is in its propositions; no `specific_line`
became general, no failed `ATTRIBUTED` became the move's gain, no `associated` became a cause, no
REFUTED claim became a reason, no explored line became the engine's.

The server's MCP `instructions` say the same in one paragraph for clients without prompts. Nothing
the prompts ask is left to them: the server checks S1–S6 and §4 itself.

## 7. Resources

- `calliope://definitions` — `definitions_v1` (DF-D), including the proposition kinds and uses.
- `calliope://glossary/ko` — `glossary_ko_v1`: grades (최선, 우수, 좋음, 부정확, 실수, 블런더) and labels
  (브릴리언트, 그레이트, 미스, 강제) as the viewer names them (`viewer/index.html`), piece names, and the
  words for scopes ("엔진 라인에서", "엔진이 보고한 수들 중") and uncertainty ("확인되지 않았다").

## 8. Storage and delivery (review B3)

- **The store.** `<data>/commentary/<game key>/<subject>/<id>.json`, where the game key is the
  pipeline's (start, moves, headers) and the subject is the ply (or the judged move's path). The
  record holds the submission with every handle replaced by its resolved source and address, each
  proposition's verified values, the check's version, the agent build (§10), the reasoning build
  digest and the time. Files are never rewritten; every accepted commentary is kept (Q3).
- **`result.json` stays as it is.** The analysis result is immutable and served `immutable`
  (AS-D §6); a commentary never changes it.
- **The HTTP route.** `GET /api/games/{id}/commentary` returns the game's accepted commentaries by
  ply, newest first, `Cache-Control: no-store`. The viewer's panel (AG3) reads it.
- **A combined document** is built only on request (`tools/explain_game --with-commentary`, or the
  route `GET /api/games/{id}/result?with=commentary`): `calliope_result_v1` with an optional
  `plies[].ai_commentary` (the newest commentary of the ply), built fresh, never stored over
  `result.json`, served `no-store`.

## 9. Two processes, one data directory (review B4)

The HTTP server and the MCP server may run at once on one data directory.

- **The ply cache.** A writer takes an exclusive lock on `<key>.lock` (`fcntl.flock`, one file per
  cache key) for the whole pair, checks again whether the pair now exists (another process may have
  written it), writes each file through a unique temporary name (`<name>.<pid>.<token>.tmp`,
  `fsync`, `os.replace`) and releases. A reader takes the shared lock while it reads the pair.
  `server.files.atomic_write` gains the unique temporary name for every writer.
- **Start-up cleanup.** `remove_temporaries` (AS-D §5.1) today removes every `*.tmp` under the
  data directory, which would delete the other process's file in flight. It removes a temporary
  only when the process named in it is not running; the MCP server runs no cleanup.
- **The commentary store** writes new files only, with unique temporary names; no lock needed.
- **Jobs** stay the HTTP server's: the MCP server does not read or write `games/`.

## 10. Build identity

The agent build names the prompt texts and the glossary (their digests), the proposition kinds
(`propositions_v1`), the check (`commentary_check_v1`), the tool set's version and the reasoning
build. It is stored with every accepted commentary; a later build does not invalidate stored
commentary, it records under which it was accepted.

## 11. Test obligations

1. **Boundary**: `calliope.agent` imports only public names; nothing imports it.
2. **Tools** through the SDK's in-process client on the scripted engine: `open_game` (PGN and
   FEN), `ply` equals the document's `analysis`, `judge_move` on a played and an unplayed move
   (equal to a direct `AnalysisRequest`), `facts` with piece identities, `explore` with and without
   `search` and with an empty line, `by` marks, the budget refusal, `definitions`, `commentary`.
3. **Isolation**: after exploration and judging, every stored bundle's bytes and digests are
   unchanged; an exploration node and a stored node with one `from_root` hold equal facts.
4. **Handles**: unique, bound to their source; refused from another session, another game, or a
   source that is not the served one.
5. **Propositions**: one accepting and one refusing case per kind and per use — among them a gain
   cited as `result` with `ATTRIBUTED` failed, an `associated` mechanism as `mechanism`, a wrong
   balance, an `after_reply` whose nested proposition fails at one side, an explored line as an
   engine line.
6. **Sentences**: S1–S6, among them a number not in the propositions, a score with the wrong sign
   or perspective, a SAN move that parses at no cited position, an interpretation stored as one,
   the reviewer's case — a sentence with no number and no move citing an unrelated claim is
   accepted as `SOURCE_VERIFIED` only, its proposition verified, and the record says so.
7. **Delivery**: an accepted commentary is stored with resolved citations; `result.json` is
   byte-identical before and after; the commentary route and the combined document return it and
   validate; a refused one leaves nothing.
8. **Concurrency**: two processes analysing the same uncached ply at once leave one sound cache
   pair; a reader never sees half a pair.
9. **Prompts and resources** listed, Korean, their digests in the agent build.
10. **End to end** with real Stockfish (gated): `g1014`, 17.Ne3 — `ply`, `judge_move` of 17.Kd1,
    `explore` of 18...Rxe3's alternative, a commentary with `check`, `engine_score`, `claim`
    (`line_fact` for the exchange, not `result`) and one interpretation; accepted.

## 12. Packets

| Packet | Content | Gate |
| --- | --- | --- |
| AG-D (this) | the server, tools, propositions, the check, storage, concurrency | independent review READY |
| AG1 | `calliope.agent`: the MCP server, `open_game`, `ply`, `judge_move`, `facts`, `explore`, `definitions`, handles, exploration trees, budget, prompts, resources, `tools/mcp`; the cache lock and unique temporary files | READY |
| AG2 | propositions and their verification, `submit_commentary`, sentences S1–S6, the commentary store, `commentary`, the HTTP route and the combined document | READY |
| AG3 | the viewer's AI commentary panel (verified and interpretation sentences told apart); the MCP App (`ui://`) | owner's check |

## 13. Owner questions

| # | Question | Recommendation (and the review's) |
| --- | --- | --- |
| Q1 | A fifth package, `calliope.agent` (changes `CLAUDE.md`'s list) | Yes |
| Q2 | The session budget | 40 searches and 2000 nodes for the agent's own work only (§3.5); to be measured on a single move and on a whole game |
| Q3 | Every accepted commentary of a subject, or the newest only | Keep all, show the newest |

## 14. Review dispositions (rev. 1 `90361a6`, independent review: NOT_READY)

The review passed the MCP architecture and SDK, the separation of the agent from the engine, the
tools and resources, `ply` as the entry and the `by` marks.

| Finding | Disposition |
| --- | --- |
| **B1** a source check is not a check that a Korean sentence follows from its sources (a sentence with no number or move citing an unrelated SUPPORTED claim passed V1–V6) | Accepted. Two layers (A4): structured propositions of a closed set of kinds, each verified field by field against the data (§4); sentences cite propositions and are checked as sources only (`SOURCE_VERIFIED`, §5.3), interpretation marked (A5, O6). The reviewer's case is a test that records it as source-verified only (§11 test 6). |
| **B2** exploration on stored trees: they load without an engine; `extend` refuses an empty line; extending would change a stored claim's evidence | Accepted. Session exploration trees opened with the engine, stored analyses read-only (A6, §3.4); the empty line by `root_expansion` or the node's incoming move; identity across trees by `from_root`; isolation tested (§11 test 3). |
| **B3** an accepted commentary would not reach the immutable `result.json` | Accepted. A sidecar store, its own route (`no-store`), and a combined document built on request, never stored over `result.json` (A7, §8). |
| **B4** two processes writing one cache key share a fixed temporary file | Accepted. A per-key inter-process lock and unique temporary files (A8, §9); start-up cleanup no longer removes a live process's temporary file (§9); a concurrency test (§11 test 8). |
| (recommendations) numbers with unit and perspective; SAN with its position; handles bound to game, ply, revision and source; the budget for the agent's work only; safety in the server, not the prompts; tests for concurrency, handle reuse and delivery | Applied: §5.3 S3–S4, §3.6, §3.5, A3 and §6, §11 tests 3, 4, 7, 8. |
| `judge_move` (owner discussion, 2026-10-15: "이 수는 어때?") | Added (§3.3): Calliope's judgement of any legal move, the main source for a move the player did not play. |
