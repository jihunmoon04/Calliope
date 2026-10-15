# Agent — AG-D design: an MCP server for commentary agents

Status: **rev. 6 — review of rev. 5 NOT_READY (R3) applied (§18)**.
Date: 2026-10-15. Base: `main @ d0658ac` (EF1, DF1 merged). Inputs:
[`reasoning-definitions-design.md`](reasoning-definitions-design.md) (DF-D: the registry, the
verdict model, `analysis`); [`reasoning-explanation-fixes-design.md`](reasoning-explanation-fixes-design.md)
(EF-D: `ATTRIBUTED`, `exposed_v1`); [`application-server-design.md`](application-server-design.md)
(AS-D: the pipeline, the ply cache, the HTTP API); [`application-result-design.md`](application-result-design.md)
(AR-D: `calliope_result_v1`, G7); status and roadmap §5.3.

An agent (an LLM with tools) writes the commentary; Calliope gives it the facts, the judgements
and the claims, explores and judges moves on request, tells it how to reason and how to check
itself, and accepts its commentary only on verified propositions. The trial of 2026-10-14 (status
and roadmap §5.3) showed the agent verifying forward lines well and inventing support for "why"
("the engine says so", its own line attributed to the engine). Calliope cannot read Korean, so it
cannot check that a free sentence follows from its sources; it can check structured propositions.
The design therefore separates **what is claimed** (propositions, verified by Calliope) from **how
it is said** (Korean sentences that cite them, checked as sources only).

## 0. Owner decisions (2026-10-15)

| # | Decision |
| --- | --- |
| O1 | A standard MCP server (Model Context Protocol), stdio first, so that any MCP client can use it |
| O2 | The commentary is in Korean |
| O3 | The agent comments only from what the server provides, and may ask the server to explore new lines |
| O4 | Threat facts, a played-against-alternative view and non-adjacent trades wait until an agent needs them |
| O5 | (later) the viewer gains an AI commentary panel; the server may later offer it as an MCP App |
| O6 | Sentences that state the agent's interpretation are allowed, marked as such (method B, §5.3) |
| O7 | Q1–Q3 as recommended (§13): the package `calliope.agent`; the session budget of §3.5; every accepted commentary kept, the newest current one shown |

## 1. Decisions

| # | Decision |
| --- | --- |
| A1 | **A new package `calliope.agent`** beside `facts`, `reasoning`, `results`, `server`. It imports their public names only (a boundary test) and python-chess (SAN for S3, `ParsedGame`), and nothing imports it. `CLAUDE.md` and `tests/test_package_boundaries.py` gain it (Q1). What the HTTP server also needs — the commentary store and its format — lives in `calliope.server` (§8). |
| A2 | **The official MCP Python SDK** (`mcp`) as an optional dependency group `agent`; the core keeps python-chess as its only dependency. Today's release (2.3.0: `mcp.server.mcpserver.MCPServer`, tools, prompts, resources, `run("stdio")`) is not installed in the venv; AG1 pins a version, verifies these names, and the agent tests skip without the extra. |
| A3 | **Prompts** say how to reason and check (§6); **tools** serve data, judge moves and explore lines (§3); one tool takes the commentary back (§5); **resources** hold the registries and the Korean glossary (§7). The server enforces §4 and S1–S6; the prompts' wording rules are guidance. |
| A4 | **Two layers in a commentary.** *Propositions* are structured statements of a closed set of kinds (§4), each verified by Calliope against the sources it served. *Sentences* are Korean text that cite propositions; their check is a source check (`SOURCE_VERIFIED`), never a check of their wording. |
| A5 | **Two classes of sentence**, neither shown as Calliope-verified. A `sourced` sentence states what its propositions say; its moves, scores, squares and numbers must come from them (§5.3). An `interpretation` sentence (O6) states the agent's reading and is marked as such. What is verified is the propositions, displayed from their structured fields. |
| A6 | **Stored analyses are read-only.** Facts are read from one engine-less facts tree per game, rooted at the game's start; searches run in search trees of their own (§3.4). A stored claim's evidence never changes. One engine path: the fact engine with the profile `d12_mpv5_v1`. |
| A7 | **Accepted commentary is a sidecar**, never written into `result.json` (§8). |
| A8 | **Two processes may share the data directory**: the ply cache takes a per-key inter-process lock and every writer uses unique temporary files (§9). |
| A9 | **The agent's vocabulary is its own registry**, `agent_definitions_v1`, owned by `calliope.agent`; the reasoning registry (`definitions_v1`) and with it every reasoning build, cache key and job id stay as they are (§7, §10). |

## 2. Shape

```text
MCP client ── stdio ──  python -m tools.mcp  (calliope.agent: one session per connection)
                          │
  prompts:   calliope_commentary, calliope_check
  resources: definitions (definitions_v1 + agent_definitions_v1), glossary_ko_v1
  tools:     open_game, ply, judge_move, facts, explore, definitions,
             submit_commentary, commentary
                          │
       read-only:  server.pipeline + PlyCache (stored analyses, AS-D §4)
       session:    a facts tree per game, search trees, the handle table, the budget
       writes:     the commentary store (calliope.server.commentary, §8)
```

A **session** is one stdio connection: its open games, the handles it served (§3.6), its budget,
its trees and its submissions. Only accepted commentary outlives it. A session runs one tool call
at a time (a session lock): its engine slot and facts trees are not shared between calls running
at once.

## 3. Tools

Answers are JSON (MCP structured content) in DF-D's vocabulary: positions by `from_root`, numbers
with the `calliope_result_v1` units, sentinels with their codes. Every citable item carries `"ref"`.

| Tool | Arguments | Answer |
| --- | --- | --- |
| `open_game` | `pgn`, or `fen` and `moves`; `plies` (a range, optional) | `game` (the session's id), the moves, and per ply the move with — for the plies already cached and those in `plies` — the grade, label and Calliope's text; plies in `plies` not cached are analysed (progress notifications) and charged (§3.5). Without `plies` nothing is analysed. |
| `ply` | `game`, `ply` | the ply's record with its `analysis` (DF-D §4.3): judgements, observations, every claim with scope, effective scopes, evidence, relations, checks and findings; the ply is analysed if not cached, and charged (§3.5) |
| `judge_move` | `game`, `position`, `move` | Calliope's judgement of any legal move at any position of the game (§3.2) — played or not — as `ply` answers it (§3.3) |
| `facts` | `game`, `position`, `families` | the position's fact records from the facts tree, projected as DF-D §4.4, piece identities as §3.7 |
| `explore` | `game`, `position`, `moves` (SAN or UCI, may be empty), `search` (bool) | the line from the position: each ply's `move` record and material balance, the end position's `status`, `pieces`, `exchange`; with `search` the end's survey (MultiPV 5, depth 12: scores, WDL, expected points, PVs); `"by": "agent"` on the plies the agent gave, `"by": "engine"` on PV plies |
| `definitions` | `ids`, `kind` or `query` | entries of either registry (§7) |
| `submit_commentary` | §5 | accepted (with its id) or refused with every violation |
| `commentary` | `game`, `ply` | the accepted commentaries of the ply, newest first, with `stale` (§8) |

### 3.1 `ply` is the main entry

The agent starts from Calliope's judgement and claims; facts, exploration and judging are for
checking and for what the catalogue does not cover. `ply` returns the claim graph in full,
REFUTED and INCONCLUSIVE claims and failed checks included (DF-D §4.1).

### 3.2 Positions

A position argument is `{"ply": n, "at": "before" | "after"}` or `{"from_root": [uci…]}`: any
legal path from the game's root — the played moves, a variation, or a path an earlier answer
served. `{"ply": n, …}` is the path of the played moves to P or C of ply n. A position's facts come
from the facts tree (§3.4); a claim, a judgement or a search a handle names comes from its source
(§3.6) — for ply n's claims, ply n's stored tree.

### 3.3 `judge_move`

`judge_move` builds a `ParsedGame` of the game's start and the path to the position + move and
runs its last ply through the pipeline's per-ply path — `normalized_ply`, `PlyCache.key`,
`PlyCache.get`, else `analyse_ply` and `PlyCache.put` — as `analyse_game` does for a played ply.
The reasoner takes any root and any legal line (DF1 §2): a move not played is judged as one that
was, and its analysis is cached like any other. AG1 adds `analyse_ply` and the cache lock (§9) to
`calliope.server`'s public names.

### 3.4 Trees (review B2, re-review N1)

Stored analyses load engine-less (`PlyCache` → `load(FactEngine(), …)`) and are never extended.
The session has two kinds of tree of its own:

- **The facts tree, one per game.** `FactEngine()` (no engine),
  `open(OpenRequest(root = RootSpec(fen = the game's start), engine = None))`. Every path asked for
  is added as `extend(ExtendRequest((InputLine("p-<k>", path),), EXPLORED, NONE))` with a new label
  each time (`k` a session counter: an existing label would continue that line from its head), the
  root needing no extend; on-request families (`exchange`, …) by `ensure`. Piece identities are therefore those of the game's start,
  every position but the root has its edge records (`move`, `delta`, …), and the facts equal the
  stored trees' records — the fact engine is deterministic and both trees are rooted at the game's
  start. All `facts`, all `explore` facts and every proposition about a position are read from it.
- **Search trees, one per searched position.** `FactEngine(engine = slot.port, store = the
  session's engine result store)`, built per request (the slot may restart its engine,
  `analyse_ply`), `open(OpenRequest(root = RootSpec(fen = the game's start, moves = the path),
  engine = the profile, families = (), root_expansion = ExpansionSpec(survey = True,
  comparison = False, attach_lines = False), budget = SessionBudget(max_searches = 1 if a search
  remains else 0)))`: one node, one search. One `explore` with `search` is one search, of the end
  position; the empty line needs no special case. The PVs are read from the survey record
  (`lines[].pv`) and served as moves; a PV is extended into the facts tree only when a position on
  it is asked for. A position searched twice in a session is answered from the session's store
  (the runtime's `reused` is set) and is free.
- **No agreement across trees is relied on** for searches: a search is cited by its own handle and
  checked only against itself. (The engine input is the full history from the start, so equal
  paths give equal inputs, but the stored and session stores differ.)

### 3.5 Budget

Every engine run an MCP request causes is charged; what is already cached is free. The fact
engine's `SessionBudget` belongs to one tree, so the session keeps the totals itself:

- **Uncached analyses** (review R2). Every ply the reasoner analyses for the session because the
  ply cache cannot answer it — from `open_game`'s `plies`, `ply` or `judge_move`, whatever the
  game or FEN — counts against `max_uncached_plies`. A request that would exceed it is refused
  before any engine work (`open_game` counts the uncached plies of its range first). A whole game
  is analysed by the HTTP server (the viewer's analyse panel), after which the MCP server reads it
  from the cache for free; the limit is a server option for the owner to raise.
- **Searches are metered at the engine port** (review R3). The session's engine slot starts its
  engine wrapped in a metering port (`MeteredPort`: the engine's `identity`, `search`, `close`)
  that holds the session's one search meter; after `EngineSlot.restart()` the new engine is
  wrapped again around the same meter. Every `search` call takes one search from the meter
  **before** it reaches the engine and is never refunded — a search that fails, and the work of
  an attempt `analyse_ply` retries after an engine failure, stay charged. A search answered from
  an engine result store never reaches the port and is free. The meter is the hard limit: with no
  search left, `search` raises `SearchBudgetExhausted` (not an `EngineError`, so `analyse_ply`
  does not restart and retry on it).
- **Admission.** Before a search tree is opened, the session checks that a search remains. An
  uncached analysis is admitted only when at least its bound remains, `2 · (min(t, 2) + 1) + 4`
  (≤ 10): round 0 surveys and compares the window's at most `min(t, 2) + 1` nodes
  (`controller.py`), and `max_extra_searches` (4) caps the later rounds. Admission avoids starting
  work that cannot finish; it does not count — the meter does.
- **An analysis the meter cut short is discarded.** When the meter refused a search during an
  analysis (an engine-failure retry can exceed the bound), the analysis is not put into the ply
  cache — a budget-limited analysis must not reach the HTTP server's results — and the tool
  answers with an error naming the budget.
- **Nodes** count the session's facts and search trees only, not the reasoner's trees.

Defaults (Q2): 16 uncached plies, 40 searches (exploration searches and the uncached analyses'
engine calls together), 2000 nodes per session. A refused request is a tool error naming the limit
and what is left.

### 3.6 Handles

Every citable item has `"ref"`: `j<n>` a judgement, `c<n>` a claim, `f<n>` a fact (a record or a
path within it), `s<n>` a search line (score, WDL, PV), `x<n>` an explored line. A handle is bound
to the session and to its **source**: the game key (§8), then a stored analysis (the ply or the
judged path, its bundle's tree and graph digests and the reasoning build digest), the facts tree
(its revision) or a search tree (its position and search id); then the item's address (position,
family and path; claim id; rank; line and plies). A handle resolves only in the session that served
it and only to that source; a handle of another session or game is refused.

### 3.7 Piece identities

The fact tree names pieces by physical identity (`PieceId`, `w.N.g1`: colour, original type, and
the square it stood on at the tree's root, the game's start) in its frames and in the edge records
(`move.piece`, `delta`); position records (`pieces`) name them by square, type and colour. The
facts tool adds the identity to each piece from the node's frame and projects it as
`{"piece": "knight", "type_now": "knight", "color": "white", "origin": "g1", "square": "e3"}`
(`type_now` differs for a promoted pawn); `agent_definitions_v1` has the entry `piece_identity`.
`calliope_result_v1` keeps AR-D G3.

## 4. Propositions (review B1)

A proposition is `{"id", "kind", <fields>, "refs": [handles]}`. Each kind is an entry of
`agent_definitions_v1` (`proposition.<kind>`) with its fields and its rule. Calliope re-reads the
cited items and verifies every field against them; **every field must lie within the sources of
its cited handles** — the facts tree being an implicit source of every proposition that reads a
position (the moves of a cited search line, the records of the facts tree along them). A proposition is VERIFIED or REFUSED (with the field that failed and the
expected value). Positions are `from_root` paths; values carry their units (DF-D §3.1).

| Kind | Fields | Verified when |
| --- | --- | --- |
| `judgement` | `move` (position, uci), `grade`, `label`, `best_move` | they equal the cited judgement (`ply` or `judge_move`) |
| `claim` | `claim` (a `c` handle), `use` (§4.1), `scopes` (a list of the claim's effective scopes, each exactly as `ply` projects it, DF-D §4.3: basis, quantifier, population, at, witnesses, searches, depth, multipv, plies, line_end, policies) | the use fits the claim; `scopes` equals the claim's effective scopes as a set — every field of every scope, its own and its premises' (R0-D §9.4) |
| `engine_score` | a search line, `move`, `score` (`cp_white` or `mate_white`), `depth` | they equal the search record |
| `engine_line` | a search line, `moves` (a prefix of the PV) | the PV starts with them |
| `material` | a line (search or explored), `from`, `to` (plies), `side`, `balance` (`points_v1`) | `material_flow` over the line's path from `from` to `to` gives `balance(side, to − from)`, the change since `from`; a missing record refuses |
| `attack` | position, `attacker`, `target` (squares) | the target is in the attacker's `pieces.attacks.enemy` |
| `defence` | position, `defender`, `defended` | the defender's square is in the defended piece's `pieces.defenders` |
| `exposed` | position, `piece` (square), `exposed` (`exposed`, `not_exposed` or `undecided`), `gain` (`points_v1` or `IN_CHECK`) | `exposed_v1` and `exchange.gain` (computed in the facts tree) agree (EF-D §4); `undecided` (in check without a safe-moves record) verifies only as `undecided`, which a sentence states as not established |
| `pin` | position, `pinned`, `pinner` | `pieces.absolutely_pinned.pinner` of the pinned piece |
| `check` | position, `checkers` | `status.in_check` and `status.checkers` |
| `legal_moves` | position, `moves` or `count` | `status.legal_moves`, `status.legal_move_count` |
| `pattern` | position, `pattern` (a `patterns_v1` list), its participants: `actor`/`targets` (multi-target attacks), `slider`/`line`/`front`/`back` (skewers, relative pins), `defender`/`defended` (sole defenders), `king`/`blockers` (back ranks) | the configuration is in the record; it is a configuration only (`configuration_only`) |
| `after_reply` | `reply` r, `after_a` = P + a + r, `after_b` = P + b + r (one P), `proposition_a`, `proposition_b` (nested, of one kind above, at those positions) | both nested propositions verify: the same reply compared after two moves (EV-D's DEFENDS / COVERS form) |
| `explored_line` | an `x` handle, `moves` | the session explored that line; the agent's plies are named as such |
| `definition` | a registry id | the entry exists in either registry |

### 4.1 Uses of a claim

| Use | Accepted when |
| --- | --- |
| `result` | SUPPORTED, a consequence; a material claim (of a `catalogue/material` template, the templates that carry `ATTRIBUTED`) has its `ATTRIBUTED` check present and passed (absent → refused) |
| `line_fact` | SUPPORTED (any checks): what the line shows |
| `mechanism` | SUPPORTED with an `explains` or `causes` relation; a claim target must be SUPPORTED, a judgement or observation target is accepted |
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
 "sentences": [{"text", "class": "sourced" | "interpretation", "cites": [proposition ids]}]}
```

The subject must have a `judgement` proposition: what the commentary says of the move's grade and
label equals Calliope's.

### 5.2 Propositions

Every proposition is verified (§4); any REFUSED proposition refuses the submission, with the
proposition, the field and the expected value.

### 5.3 Sentences

- **S1** `language` is `ko`; 1–12 sentences, each at most 300 characters; at least one `sourced`.
- **S2** every sentence cites at least one proposition of the submission.
- **S3 tokens.** The text is split into tokens: maximal runs of `[A-Za-z0-9.+\-−#=]` (U+2212
  included); every other character separates (so Korean particles come off: "Ne3는", "Rxe3로"). A
  token `\d+\.` or `\d+\.\.\.` followed by one space and a token is joined with it ("17. Ne3"). A
  trailing `.` is dropped unless the token is a bare move number. Each token that contains a digit,
  or is `O-O` / `O-O-O`, must **fullmatch** the first fitting rule of 1–5, else rule 6:
  1. **a move**: `(\d+(\.|\.\.\.) ?)?(O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8](=[QRBN])?|[a-h][1-8]=[QRBN]|[a-h][1-8])[+#]?`,
     where a bare pawn push (`[a-h][1-8]`) fits only with a move number; without one it is a square
     (4). The move must be a move of a cited proposition (its `move`, `best_move`, `reply`, a move
     of its line) and parse as SAN at that move's position; a move number must equal the move's
     fullmove number, with `...` exactly when Black moves.
  2. **a score**: `[+\-−]?\d+\.\d{1,2}` equal to `round_half_away(cp_white / 100, d)` of a cited
     `engine_score`, `d` its decimals; a negative score has a minus sign (`-` or `−`).
  3. **a mate**: `M\d+` or `#\d+` equal to `|mate_white|` of a cited `engine_score`.
  4. **a square**: `[a-h][1-8]`, a square field of a cited proposition or the from or to square of
     a cited move.
  5. **an integer**: `[+\-−]?\d+`, equal to an integer field of a cited proposition — points, a
     balance, a count, a ply, a depth, or the fullmove number of a cited move's position. A signed
     integer equals a signed field; an unsigned one may equal a field's absolute value.
  6. **a violation**: any other token, e.g. `0-0`, `Stockfish16`, `0.385`, `Ne9`.
- **S4** S3 applies to both classes.
- **S5** an `interpretation` sentence is not checked further; it is stored and shown as the agent's
  interpretation (O6).
- **S6** a sentence citing an `explored_line`, or an `after_reply` resting on one, is stored with
  `by: agent` on that citation; the viewer marks it.

What an accepted commentary guarantees: every proposition was verified against Calliope's data;
every move, score, mate, square and number written as such in a sentence comes from its cited
propositions; interpretation is marked. It does not guarantee that the wording states what the
propositions state, nor catch a move written in words ("나이트가 e3로" checks only the square).
That is the `SOURCE_VERIFIED` level; `commentary_check_v1` says so.

## 6. Prompts: how to reason and how to check

Two MCP prompts in Korean, versioned data (`agent/prompts/*.md`), entries of
`agent_definitions_v1` (`prompt.commentary_ko_v1`, `prompt.check_ko_v1`):

**`calliope_commentary(game, ply)`**
1. `ply` (or `judge_move` for a move asked about): the grade, the label, the best move, the claims.
2. For each claim you use, read its scope, checks and effective scopes; look terms up with
   `definitions`. A SUPPORTED claim with a failed `ATTRIBUTED` is a fact of the engine line, not
   the move's achievement; a `specific_line` scope covers one line, not every reply; a pattern is a
   configuration, not a tactic that works.
3. Answer "why" by comparison: what the better move does that this one does not — the same reply
   after both (`after_reply`), the piece that becomes exposed, the material along each line. Check
   with `facts`, `explore`, `judge_move` before you write.
4. Turn what you checked into propositions; write each `sourced` sentence from its propositions
   only; write your reading as `interpretation`; say what is not established as not established.
5. Submit; on refusal, fix the named propositions and sentences and submit again.

**`calliope_check(game, ply)`** — before submitting: the grade and label match; every move, score,
square and number is in the cited propositions; no `specific_line` became general, no failed
`ATTRIBUTED` became the move's gain, no `associated` became a cause, no REFUTED claim became a
reason, no explored line became the engine's.

The server enforces §4 and S1–S6 (the `claim` proposition's `scopes` and `use` fields make the
scope and use rules checkable at the proposition layer); the wording rules of `calliope_check` are
guidance only and are what `SOURCE_VERIFIED` does not guarantee. The server's MCP `instructions`
say the same in one paragraph for clients without prompts.

## 7. Resources and registries

- **`agent_definitions_v1`**, owned by `calliope.agent`: the proposition kinds and uses, the
  sentence classes and S3's token rules, `piece_identity`, `commentary_check_v1`, the prompt ids,
  the tool set's version. Its digest is part of the agent build (§10), not of the reasoning build.
- `calliope://definitions` — `definitions_v1` (DF-D, unchanged) and `agent_definitions_v1` side by
  side; the `definitions` tool reads both.
- `calliope://glossary/ko` — `glossary_ko_v1`: grades (최선, 우수, 좋음, 부정확, 실수, 블런더) and labels
  (브릴리언트, 그레이트, 미스, 강제) as the viewer names them (`viewer/index.html`), piece names, and the
  words for scopes ("엔진 라인에서", "엔진이 보고한 수들 중") and uncertainty ("확인되지 않았다").

## 8. Storage and delivery (review B3, re-review N2)

- **The package.** The store's format, reader and writer are `calliope.server.commentary`;
  `calliope.agent` writes through it, the HTTP server reads through it.
- **The game key.** `game_key = sha256(canonical({"v": "game_key_v1", "start_fen", "moves": [uci],
  "headers"}))` — the game part of the job id's preimage (`server/jobs.py` `job_id`), without the
  ply range, grading, engine and build.
- **The store.** `<data>/commentary/<game key>/<subject digest>/<id>.json`; the subject digest is
  `sha256(canonical({"v": "subject_v1", "path": [uci…]}))` of the subject's path (the played path
  to the ply, or the judged path), so file names stay short. The record holds the submission with every handle replaced by its resolved source and
  address, each proposition's verified values, the subject's bundle digests (tree, graph), the
  agent build (§10), the reasoning build digest and the time. Files are written once, never
  rewritten; every accepted commentary is kept (Q3).
- **`result.json` stays as it is.** The analysis result is immutable and served `immutable`
  (AS-D §6); a commentary never changes it.
- **The commentary route.** `GET /api/games/{id}/commentary`: the job id gives `job.json`, parsed
  to its game key; the answer lists the game's accepted commentaries by ply, newest first,
  `Cache-Control: no-store`. A commentary whose stored bundle digests equal the ply's `bundle` in
  the job's result is current (`"stale": false`); otherwise `"stale": true` (it was accepted against
  another analysis: another build, or another engine fingerprint between the two processes). A
  commentary of a ply the job's result does not hold (outside its ply range) has `"stale": null`
  (unknown); commentaries of judged moves are listed under `judged`, by their path, with
  `"stale": null`. The viewer's panel (AG3) shows only `"stale": false`, the newest first.
- **Game identity.** A game opened with `fen` and `moves` has no headers; its key differs from the
  same game sent as a PGN with tags, so its commentary does not appear on that PGN's job.
- **The combined document** is built only on request: `tools/explain_game --with-commentary`, or
  `GET /api/games/{id}/result?with=commentary`. The result route then branches on the query (today
  `web.py` drops it and always sends `IMMUTABLE`): with `with=commentary` it builds
  `calliope_result_v1` with an optional `plies[].ai_commentary` (the newest current commentary)
  fresh, never stored over `result.json`, served `no-store`; without it, the stored bytes as now.
  `ai_commentary` enters the shipped schema as an optional per-ply property (an AR-D amendment
  recorded by AG2).

## 9. Two processes, one data directory (review B4)

The HTTP server and the MCP server may run at once on one data directory.

- **The ply cache.** A writer takes an exclusive lock on `<key>.lock` (`fcntl.flock`, one file per
  cache key) for the whole pair, checks again whether the pair now exists (another process may have
  written it), writes each file through a unique temporary name (`<name>.<pid>.<token>.tmp`,
  `fsync`, `os.replace`) and releases. A reader takes the shared lock while it reads the pair. Lock
  files are never removed.
- **Every writer** — `server.files.atomic_write` — uses the unique temporary name.
- **Start-up cleanup.** `remove_temporaries` (AS-D §5.1) today removes every `*.tmp` under the data
  directory, which would delete the other process's file in flight. It removes a temporary only
  when the process named in it is not running (`os.kill(pid, 0)` fails with `ProcessLookupError`;
  `PermissionError` means alive; PID reuse is accepted), and an old-style `<name>.tmp` with no pid;
  the MCP server runs no cleanup.
- **The commentary store** writes new files only, through unique temporary names; no lock needed.
- **Jobs** stay the HTTP server's: the MCP server does not write `games/`; the commentary route
  reads `job.json` as the job table does.

## 10. Build identity

The agent build names the digests of `agent_definitions_v1`, the prompt texts and the glossary, and
the reasoning build digest. It is stored with every accepted commentary; a later build does not
invalidate stored commentary, it records under which it was accepted. Neither AG1 nor AG2 changes
`calliope.reasoning.definitions.current_digest()`, so no cached ply or job id changes.

## 11. Test obligations

1. **Boundary**: `calliope.agent` imports only public names; nothing imports it;
   `reasoning.definitions.current_digest()` is unchanged.
2. **Tools** through the SDK's in-process client on the scripted engine: `open_game` (PGN and FEN,
   with and without `plies`), `ply` equals the document's `analysis`, `judge_move` on a played and
   an unplayed move (equal to a direct `analyse_ply`), `facts` with piece identities (a promoted
   pawn), `explore` with and without `search` and with an empty line (one search each), `by` marks,
   the budget refusals (uncached plies from each of `open_game`, `ply` and `judge_move` — among
   them repeated `open_game` on new FENs — searches, the analysis bound, nodes; a cached ply
   free); the meter on a scripted engine that fails after some searches: failure, restart and
   retry charge the searches of both attempts against one meter, a store hit is free, an
   exhausted meter raises `SearchBudgetExhausted` without a restart, and an analysis cut short is
   not in the ply cache afterwards, `definitions` of both registries, `commentary`.
3. **Isolation**: after exploration and judging, every stored bundle's bytes and digests are
   unchanged; for a played position, the facts tree's records equal the stored tree's for every
   family both hold.
4. **Handles**: unique, bound to their source; refused from another session, another game, or a
   source that is not the served one.
5. **Propositions**: one accepting and one refusing case per kind and per use — among them a gain
   cited as `result` with `ATTRIBUTED` failed and with it absent, a `mechanism` whose target is not
   SUPPORTED, `scopes` of a claim with a premise (`sacrifice_sound_v1` over `sacrifice_offer_v1`:
   `specific_line` and `exists_alternative` together) accepted whole and refused with one scope
   missing or one field changed, an `exposed` in check with `undecided`, a wrong balance, an `after_reply` with two different P or a failing
   nested side, an explored line as an engine line, a field outside its cited source.
6. **Sentences**: S1–S6 and each token rule of S3: a move with particles, a move number of the
   wrong side, a bare square, a score with the wrong sign or rounding, a mate, an integer not in
   the propositions, `Stockfish16`, `-3` against a balance of +3, `0-0`, `0.385`, `−0.38`; an interpretation stored as one; the reviewer's case — a sentence with no
   token citing an unrelated claim is accepted as `SOURCE_VERIFIED` only, and the record says so.
7. **Delivery**: an accepted commentary is stored with resolved citations; `result.json` is
   byte-identical before and after; the commentary route (current and stale) and the combined
   document return it and validate; the plain result route keeps its bytes and `immutable`; a
   refused submission leaves nothing.
8. **Concurrency**: two processes analysing the same uncached ply at once leave one sound cache
   pair; a reader never sees half a pair; `remove_temporaries` spares a live process's temporary
   and removes a dead one's.
9. **Prompts and resources** listed, Korean, their digests in the agent build.
10. **End to end** with real Stockfish (gated): `g1014`, 17.Ne3 — `ply`, `judge_move` of 17.Kd1,
    `explore` of 18...Rxe3's alternative, a commentary with `check`, `engine_score`, `claim`
    (`line_fact` for the exchange, not `result`) and one interpretation; accepted.

## 12. Packets

| Packet | Content | Gate |
| --- | --- | --- |
| AG-D (this) | the server, tools, propositions, the check, storage, concurrency | independent review READY |
| AG1 | `calliope.agent`: the MCP server, `open_game`, `ply`, `judge_move`, `facts`, `explore`, `definitions`, the trees, handles, the budget and its metering port, `agent_definitions_v1`, prompts, resources, `tools/mcp`; in `calliope.server`: the exported `analyse_ply` (`EngineSlot` is public already), the cache lock, unique temporary files, the cleanup rule; `calliope.reasoning` exports `DEFINITIONS`, `REGISTRY_DIGEST`, `current_digest` and `exposed` (`exposed_v1`) — `__all__` only, no build change | READY |
| AG2 | propositions and their verification, `submit_commentary`, S1–S6, `calliope.server.commentary`, `commentary`, the HTTP route and the combined document | READY |
| AG3 | the viewer's AI commentary panel (propositions shown as verified, sentences as sourced or interpretation, stale ones apart); the MCP App (`ui://`) | owner's check |

## 13. Owner questions — decided as recommended (O7, 2026-10-15)

| # | Question | Decision (the recommendation, and the reviews') |
| --- | --- | --- |
| Q1 | A fifth package, `calliope.agent` (changes `CLAUDE.md`'s list) | Yes; it may import `calliope.server`'s public names; the store and the route belong in `server` |
| Q2 | The session budget | 16 uncached plies from any tool, 40 searches (one per searched position, plus the uncached analyses' engine calls), 2000 nodes for the session's trees (§3.5); measured in AG1 on a single move and on a whole game |
| Q3 | Every accepted commentary of a subject, or the newest only | Keep all; show the newest current one; older and stale ones on demand |

## 14. Review dispositions — rev. 1 (`90361a6`), independent review: NOT_READY

The review passed the MCP architecture and SDK, the separation of the agent from the engine, the
tools and resources, `ply` as the entry and the `by` marks.

| Finding | Disposition |
| --- | --- |
| **B1** a source check is not a check that a Korean sentence follows from its sources | Accepted. Two layers (A4): propositions verified field by field (§4); sentences checked as sources only (`SOURCE_VERIFIED`, §5.3), interpretation marked (A5, O6). |
| **B2** exploration on stored trees (no engine, no empty line, changed evidence) | Accepted. Session trees, stored analyses read-only (A6, §3.4; redone in rev. 3, N1). |
| **B3** an accepted commentary would not reach the immutable `result.json` | Accepted. A sidecar store, its own route, a combined document on request (A7, §8; rev. 3, N2). |
| **B4** two processes writing one cache key share a fixed temporary file | Accepted. A per-key lock, unique temporaries, a safe start-up cleanup (A8, §9); test 8. |
| (recommendations) units and perspective; SAN at its position; bound handles; budget for the agent's work; safety in the server; tests | Applied: §5.3 S3, §3.6, §3.5, A3 and §6, §11. |
| `judge_move` (owner discussion, 2026-10-15: "이 수는 어때?") | Added (§3.3). |

## 15. Review dispositions — rev. 2 (`c98f395`), re-review: NOT_READY

The re-review passed the two layers, read-only stored trees, the sidecar, the lock mechanics, handle
binding and the `by` marks, and verified the cited fields, units, routes and pipeline names.

| Finding | Disposition |
| --- | --- |
| **N1** exploration trees rooted at the position name pieces from that position and lack edge records there; a line's expansion surveys every node; search agreement across stores is not guaranteed | Accepted. One engine-less facts tree per game rooted at the game's start for every fact; one search tree per searched position (one search per `explore`); no cross-tree search agreement relied on (§3.4, §3.7); test 3 compares the families both trees hold. |
| **N2** the store in `calliope.agent` contradicts A1; the game key is undefined; staleness; the result route's query | Accepted. `calliope.server.commentary` (A1, §8); `game_key_v1`; `stale` by bundle digests; subject digests; the result route branches on `with=commentary`. |
| **N3** agent entries in `definitions_v1` would change every reasoning build, cache key and job id | Accepted. `agent_definitions_v1` (A9, §7, §10); test 1 pins the reasoning digest. |
| **N4** S3/S4 undecidable on Korean text; §6 contradicted §5.3; the class name `verified` | Accepted. Token rules in order (S3); scopes on the `claim` proposition (a list since rev. 4, R1); §6 says what the server enforces and what is guidance; `verified` renamed `sourced` (A5). |
| **C1** `analyse_ply` not public; the slot restarts | Applied (§3.3, §3.4, §12 AG1). |
| **C2** budget across trees, the `judge_move` bound, nodes, the refusal form | Applied (§3.5); extended in rev. 4 (R2). |
| **C3** field details (`legal_move_count`, the balance as a change, `IN_CHECK`, pattern participants, `after_reply`'s P, `mechanism`'s target, absent `ATTRIBUTED`, fields within sources) | Applied (§4, §4.1). |
| **C4** the source of `{"ply", "at"}`; which `from_root` paths | Applied (§3.2): any legal path. |
| **C5** the current piece type | Applied (§3.7, `type_now`). |
| **C6** the B2 row against §3.4 | Moot after N1; the row is aligned. |
| **C7** test 8 for the cleanup; lock files kept | Applied (§9, §11 test 8). |
| **C8** `mcp` not installed | Applied (A2). |
| **C9** `open_game` on a whole uncached game | Applied: nothing is analysed without `plies` (§3). |

## 16. Review dispositions — rev. 3 (`099e670`), review: NOT_READY

The review passed B1–B4, the MCP interface, the facts and search trees, the sidecar store and the
cache concurrency.

| Finding | Disposition |
| --- | --- |
| **R1** (Major) `claim.scope` as one quantifier cannot state an effective scope, which is the claim's own scope with its premises' (`reasoning/verification.py` `effective_scope`); a SUPPORTED `sacrifice_sound_v1` (`specific_line`) over `sacrifice_offer_v1` (`exists_alternative`) could not be cited | Accepted. `scopes` is the list of the claim's effective scopes, compared as a set, every projected field of every scope (§4); tests with a premised claim (§11 test 5). |
| **R2** (Major) new analyses from `open_game` and `ply` were not charged: repeated `open_game` on new FENs ran the reasoner without limit | Accepted. Every uncached ply analysed for the session, from any tool, counts against `max_uncached_plies` (16) and its engine calls against the searches; cached plies stay free; whole games go through the HTTP server (§3.5, Q2); tests (§11 test 2). |
| (recommendation) `exposed_v1` can be `UNDECIDED` in check; the field was a bool | Applied: the field takes `exposed_v1`'s three values; `undecided` verifies only as such (§4); test 5. |

## 17. Review dispositions — rev. 3 (`099e670`), second re-review: READY_WITH_CORRECTIONS

Run beside the review of §16. It verified against the source that the stored analyses and the facts
tree are rooted alike (equal records), the facts-tree and search-tree recipes (run), the store hit
of a repeated search, the unchanged reasoning digest, the game key as the job id's game part, and
the result route and cleanup changes §8–§9 plan.

| Finding | Disposition |
| --- | --- |
| **C1** the search tree with the default families and attached lines built 61 nodes for one search, against a 2000-node budget, and the attached lines were never read | Applied: `families = ()`, no attached lines, one node, PVs from the survey record, `max_searches` 1 or 0 (§3.4). |
| **C2** `exposed` and the registry are not public names; python-chess | Applied: `calliope.reasoning` exports them in AG1 (§12); A1 names python-chess. |
| **C3** S3 had no tokenizer (`Stockfish16`, `-3`, `0.385`, `Ne9`, `0-0`, `−` cut off; rule 6 unreachable) | Applied: tokens, joining, fullmatch, signed integers, squares of cited moves (§5.3); test 6. |
| **C4** one quantifier per claim | Superseded by R1 (§16): the full effective-scope set. |
| **C5** "material claim"; non-claim targets of `mechanism` | Applied (§4.1). |
| **C6** the analysis bound unstated; a charge beyond the balance | Applied (§3.5). |
| **C7** a reused label continues its line; no empty extend | Applied (§3.4). |
| **C8** staleness for plies outside the job's range and for judged moves; the subject digest's encoding | Applied (§8). |
| **C9** concurrent tool calls in one session | Applied: a session lock (§2). |
| (notes) identities in frames and edge records; the facts tree as an implicit source; old-style temporaries and liveness; FEN games have no headers; engine fingerprints and staleness; `ai_commentary` in the schema | Applied: §3.7, §4, §9, §8 (an AR-D amendment in AG2). |

## 18. Review dispositions — rev. 5 (`2d503ee`), review: NOT_READY

The review passed R1, R2 on the normal path, `undecided`, the one-node search trees, the session
lock and the SDK contract.

| Finding | Disposition |
| --- | --- |
| **R3** (Major) searches counted from the final tree's runtimes miss an attempt `analyse_ply` retried after an engine failure (it restarts the slot and analyses again with a new fact engine): 4 searches before a failure and 6 in the retry were counted as 6, so the session could exceed its 40 | Accepted. A metering port around the session's engine, kept across restarts, takes a search before each engine call and never refunds it; store hits are free; the meter is the hard limit and an analysis it cut short is not cached; admission by the bound stays (§3.5); tests for failure → restart → retry (§11 test 2). |
