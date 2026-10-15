# Agent — AG-D design: an MCP server for commentary agents

Status: **rev. 1 — draft for independent review**.
Date: 2026-10-15. Base: `main @ d0658ac` (EF1, DF1 merged). Inputs:
[`reasoning-definitions-design.md`](reasoning-definitions-design.md) (DF-D: the registry, the
verdict model, `analysis`); [`reasoning-explanation-fixes-design.md`](reasoning-explanation-fixes-design.md)
(EF-D: `ATTRIBUTED`); [`application-server-design.md`](application-server-design.md) (AS-D: the
pipeline, the ply cache); [`application-result-design.md`](application-result-design.md) (AR-D:
`calliope_result_v1`, G7); status and roadmap §5.3.

An agent (an LLM with tools) writes the commentary; Calliope gives it the facts, the judgements
and the claims, lets it explore lines, tells it how to reason and how to check itself, and accepts
its commentary only when every sentence rests on what Calliope served. This packet designs that
server. The trial of 2026-10-14 (status and roadmap §5.3) showed the agent verifying forward lines
well and inventing support for "why" ("the engine says so", its own line attributed to the
engine); the design's centre is therefore the check of the submitted commentary, not the tools.

## 0. Owner decisions (2026-10-15)

| # | Decision |
| --- | --- |
| O1 | A standard MCP server (Model Context Protocol), stdio first, so that any MCP client can use it |
| O2 | The commentary is in Korean |
| O3 | The agent comments only from what the server provides, and may ask the server to explore new lines |
| O4 | Threat facts, a played-against-alternative view and non-adjacent trades wait until an agent needs them |
| O5 | (later) the viewer gains an AI commentary panel; the server may later offer it as an MCP App |

## 1. Decisions

| # | Decision |
| --- | --- |
| A1 | **A new package `calliope.agent`** beside `facts`, `reasoning`, `results`, `server`. It imports their public names only (a boundary test), and nothing imports it. `CLAUDE.md` and `tests/test_package_boundaries.py` gain it. |
| A2 | **The official MCP Python SDK** (`mcp`, pinned in AG1; 2.3.0 today: `mcp.server.mcpserver.MCPServer`, tools, prompts, resources, `run("stdio")`) as an optional dependency group `agent`, so the core keeps python-chess as its only dependency. |
| A3 | **Three MCP primitives**: *prompts* say how to reason and check (§4), *tools* serve data and explore lines (§3), one tool takes the commentary back (§5). *Resources* hold the definitions registry and the Korean glossary (§6). |
| A4 | **Everything served is citable, and only what was served is.** Each citable item in a tool's answer carries a session handle (`ref`); a submitted sentence cites handles; the check refuses a handle the session never served (O3). |
| A5 | **The check is structural, not linguistic.** Calliope does not parse Korean. Each citation states its *use* (§5.2), and the check tests the use against the cited item's status, scope and checks; every number and every move written in a sentence must occur in the items it cites (§5.3). |
| A6 | **One engine path.** Explored lines are fact-engine requests (`extend` with role `ANALYSIS("agent")`, profile `d12_mpv5_v1`), never a separate engine call (status and roadmap §5.3, "one engine path"); a session has a search budget (§3.4). |
| A7 | **Accepted commentary is stored with its resolved citations** and appears in `calliope_result_v1` as an optional per-ply `ai_commentary` (AR-D G7). The viewer panel and the MCP App are a later packet (AG3). |

## 2. Shape

```text
MCP client (Claude Code / Desktop, …)  ── stdio ──  python -m tools.mcp   (calliope.agent)
                                                       │
         prompts: calliope_commentary, calliope_check  │  resources: definitions_v1, glossary_ko
         tools:   open_game, ply, facts, explore,      │
                  definitions, submit_commentary       │
                                                       ▼
                     server.pipeline + PlyCache (shared data directory, AS-D §4)
                     FactEngine / Reasoner (one Stockfish slot), calliope.results (analysis)
```

- **Session.** One stdio connection is one session: it holds the open games, the handles it served
  (§3.5), its search budget and its submissions. Nothing of a session is persisted except the
  accepted commentary.
- **Games.** A game is opened from a PGN (as the HTTP server) or from a position and a move
  (`RootSpec(fen)`; the reasoning API already takes it, DF1 §2). Plies are analysed through the
  server's pipeline and its ply cache, so the HTTP server and the MCP server share analyses.

## 3. Tools (reading and exploring)

Answers are JSON (the MCP tool result's structured content), in the vocabulary of DF-D: positions
by `from_root`, references as `calliope_result_v1`'s, sentinels with their codes, numbers with the
document's `units`. Every citable item carries `"ref"` (§3.5).

| Tool | Arguments | Answer |
| --- | --- | --- |
| `open_game` | `pgn` or `fen` + `moves`, `plies` (a range, default all) | `game` (the session's id), the moves, and per ply the move, grade, label and Calliope's text; analyses the plies not cached (engine work, reported as progress notifications) |
| `ply` | `game`, `ply` | the ply's record with its `analysis` (DF-D §4.3): judgements, observations, every claim with scope, effective scopes, evidence, relations, checks and findings |
| `facts` | `game`, `position` (`from_root` or the ply), `families` | the fact records of the position (the 14 families, `exchange` on request), projected as DF-D §4.4; piece identities appear as `{"piece", "color", "origin"}` (§3.6) |
| `explore` | `game`, `position`, `moves` (SAN or UCI, may be empty), `search` (bool) | the line played from the position: each ply's `move` record and material balance, the end position's `status`, `pieces` and `exchange`, and with `search` the end's survey (MultiPV 5, depth 12: scores, WDL, expected points, PVs attached) |
| `definitions` | `ids` or `kind` or `query` | registry entries (DF-D §2.1) |
| `submit_commentary` | §5 | accepted, or refused with every violation |

### 3.1 `ply` is the main entry

The agent starts from Calliope's own judgement and claims; facts and exploration are for checking
and for what the catalogue does not cover. `ply` returns the claim graph in full, including
REFUTED and INCONCLUSIVE claims and the failed checks — what was not established is information
too (DF-D §4.1).

### 3.2 Positions

A position argument is `{"ply": n, "at": "before" | "after"}` (P or C of a ply) or
`{"from_root": [uci…]}` (any node the session served, or a new path of legal moves from the root).

### 3.3 `explore` (O3)

Exploration extends a tree of the game with `ExtendRequest(lines, ANALYSIS("agent"), expansion)`
(`survey` and `attach_lines` when `search`). Its facts and searches are the fact engine's, under
the session's profile, so a line the agent explores and a line the reasoner read are the same kind
of evidence. The answer says which plies of the line came from the agent (`"by": "agent"`) and
which from the engine (PV plies), so the agent cannot present its own line as the engine's (the
trial's fault).

### 3.4 Budget

A session has `max_searches` (default 40) and `max_nodes` (default 2000) for exploration, and each
`explore` a deadline (the profile's time cap per search). A refused request answers with the
reason code of the fact engine (`BUDGET`, …) and the budget left.

### 3.5 Handles

Every citable item in an answer has `"ref"`: `c<n>` a claim, `j<n>` a judgement, `f<n>` a fact
record or field path, `l<n>` a line (an engine line of a search, or an explored line), `s<n>` a
search line's score. A handle is unique in the session and resolves to the item as served
(game, position, family, path, claim id, search and rank, moves). The session keeps the table.

### 3.6 Piece identities

Fact records name pieces by physical identity (`PieceId`, `w.N.g1`: colour, original type, the
square it started on). For the agent the identity is useful — the same knight across a line — so
the facts tool projects it as `{"piece": "knight", "color": "white", "origin": "g1"}`, with the
square it stands on where the record has one. The registry gains the entry (`piece_identity`).
`calliope_result_v1` keeps AR-D G3 (no identities in the document).

## 4. Prompts: how to reason and how to check

Two MCP prompts, in Korean, both versioned registry entries (`prompt.commentary_ko_v1`,
`prompt.check_ko_v1`); the text ships as data (`agent/prompts/*.md`) and is part of the agent
build (§7).

**`calliope_commentary(game, ply)`** — the procedure:
1. Read `ply`: the grade, the label, the best move, and the claims Calliope stated.
2. For each claim you use, read its scope, its checks and its effective scopes; look terms up with
   `definitions`. A claim SUPPORTED with a failed `ATTRIBUTED` check is a fact of the engine line,
   not the move's achievement; a `specific_line` scope covers one line, not every reply.
3. Answer "why" by comparison: what the best move does that the played move does not. Check it with
   `explore` and `facts` (the reply that refutes, the piece that hangs) before writing it.
4. Write only what the served items show. Say what is not established as not established.
5. Write in Korean; cite every sentence (§5); submit with `submit_commentary`; on refusal, correct
   the cited sentences and submit again.

**`calliope_check(game, ply)`** — the self-check before submitting: every sentence has a
citation; every number and move in it is in its citations; no sentence turns a `specific_line` into
a general claim, a failed `ATTRIBUTED` into a gain of the move, an ASSOCIATED_WITH mechanism into a
cause, or a REFUTED claim into a reason.

The server's MCP `instructions` say the same in one paragraph, for clients that do not use
prompts.

## 5. `submit_commentary`

### 5.1 The submission

```text
{"game", "ply", "language": "ko",
 "agent": {"name", "model"?},
 "verdict": {"grade", "label"},            # what the commentary says of the move
 "sentences": [{"text", "citations": [{"ref", "use"}]}]}
```

### 5.2 Uses and their rules

| Use | Cites | Accepted when |
| --- | --- | --- |
| `judgement` | `j` | the item is the ply's judgement; `verdict.grade` and `.label` equal Calliope's |
| `result` | `c` | SUPPORTED, a consequence; a material claim's `ATTRIBUTED` passed |
| `line_fact` | `c`, `l` | SUPPORTED (any checks): "along this line …" |
| `mechanism` | `c` | SUPPORTED with an `explains` or `causes` relation (its causal check passed) |
| `associated` | `c` | SUPPORTED with `associated_with` only: "the configuration occurs" |
| `comparison` | `c`, `l`, `s` | a comparison claim SUPPORTED, or an engine line and score of a served search |
| `uncertain` | `c` | INCONCLUSIVE: "could not be confirmed" |
| `not_the_case` | `c` | REFUTED |
| `fact` | `f` | any served fact |
| `exploration` | `l` | an explored line (`"by": "agent"` plies stated as the agent's) |
| `definition` | registry id | an entry of the registry |

### 5.3 The checks

- **V1** `language` is `ko`; at least one sentence, at most 12; each at most 300 characters.
- **V2** the `verdict` equals the ply's grade and label (no commentary contradicts the judgement).
- **V3** every sentence has at least one citation; every `ref` was served to this session for this
  game; every `use` fits its item (§5.2).
- **V4** **numbers**: every number written in a sentence (Arabic digits, with a sign or a decimal
  point) equals a number of a cited item — a move number, a score in pawns (cp / 100, rounded to
  one or two places), expected points as a percentage, points of material, a mate distance, a ply
  count.
- **V5** **moves**: every move written in SAN (a token that parses as SAN in a cited position, or
  with a move number) is the ply's move or a move of a cited line, claim or fact.
- **V6** a sentence that cites an `exploration` line says the line is the agent's (it cites it with
  that use; the stored citation records `by: agent`).

A refusal lists every violation by sentence and check; nothing is stored. An accepted commentary is
stored (§5.4) and the answer gives its id.

### 5.4 Storage

`<data>/commentary/<game key>/<ply>/<id>.json`: the submission with each `ref` replaced by its
resolved item (claim id, position, family and path, search and rank, moves, the explored line), the
check's version, the agent build (§7), the reasoning build digest and the time. The game key is the
pipeline's (the game's start, moves and headers), so the HTTP server finds it. Several
commentaries per ply are kept; the newest is shown.

### 5.5 In the result document

`calliope_result_v1` gains an optional `plies[].ai_commentary`: the newest accepted commentary of
the ply (`language`, `agent`, `created`, `sentences` with resolved citations, `check`), added when
the document is built and a commentary exists. The schema gains it as optional (AR-D G7).

## 6. Resources

- `calliope://definitions` — `definitions_v1` (DF-D, `tools/definitions`).
- `calliope://glossary/ko` — the Korean terms: grades (최선, 우수, 좋음, 부정확, 실수, 블런더) and
  labels (브릴리언트, 그레이트, 미스, 강제), as the viewer names them (`viewer/index.html`); piece names, the words for a scope ("엔진 라인에서", "엔진이 보고한 수들 중"),
  for uncertainty ("확인되지 않았다"). Data, versioned (`glossary_ko_v1`).

## 7. Build identity

The agent build names the prompt texts and the glossary (their digests), the check's version
(`commentary_check_v1`), the tool set's version and the reasoning build. It is stored with every
accepted commentary; a changed check or prompt does not invalidate stored commentary, it records
under which it was accepted.

## 8. Test obligations

1. **Boundary**: `calliope.agent` imports only public names; nothing imports it.
2. **Tools** through an in-process MCP client (the SDK's), on the scripted engine: `open_game` (PGN
   and FEN), `ply` equals the document's `analysis`, `facts` and its piece identities, `explore`
   with and without `search` (`by` marks, budget refusal), `definitions`.
3. **Handles**: unique, resolving, refused when not served or from another game.
4. **The check**: one test per rule V1–V6 and per use of §5.2, accepting and refusing — among them
   a gain cited as `result` while its `ATTRIBUTED` failed (refused), a mechanism with
   `associated_with` cited as `mechanism` (refused), a number not in the citations (refused), a
   move not in them (refused), an explored line cited as `comparison` (refused).
5. **Storage and document**: an accepted commentary resolves its citations, is found by the HTTP
   server's document build, validates against the schema; a refused one leaves nothing.
6. **Prompts and resources**: listed, Korean, their digests in the agent build.
7. **End to end** with real Stockfish (gated): open `g1014`, read 17.Ne3, explore 18...Rxe3's
   alternative, submit a commentary that cites the blocked check and the concession; accepted.

## 9. Packets

| Packet | Content | Gate |
| --- | --- | --- |
| AG-D (this) | the server, tools, prompts, the check, storage | independent review READY |
| AG1 | `calliope.agent`: the MCP server, `open_game`, `ply`, `facts`, `explore`, `definitions`, handles, budget, prompts, resources, `tools/mcp` | READY |
| AG2 | `submit_commentary`, the check V1–V6, storage, `ai_commentary` in `calliope_result_v1` | READY |
| AG3 | the viewer's AI commentary panel; the MCP App (`ui://`) offering the viewer | owner's check |

## 10. Owner questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | A fifth package, `calliope.agent` (changes `CLAUDE.md`'s list) | Yes |
| Q2 | The default search budget per session | 40 searches, 2000 nodes |
| Q3 | Keep every accepted commentary of a ply, or only the newest | Keep all, show the newest |
