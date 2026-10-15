# Agent — packet AG1 implementation: the MCP server, its read tools, exploration and the budget

Status: **rev. 1 — for independent review**.
Date: 2026-10-15. Design: [`agent-mcp-design.md`](agent-mcp-design.md) rev. 6 (AG-D, approved
and merged by the owner, PR #95). Base: `main @ 4ca7812`.

## 1. Scope delivered

| Place | Change |
| --- | --- |
| `agent/` (new package) | `calliope.agent` (AG-D A1, Q1): imports only the public names of `facts`, `reasoning`, `results`, `server`, python-chess and — in `agent/server.py` only — the MCP SDK |
| `agent/session.py` | `Session`: games (`open_game` by PGN, or FEN and moves in SAN or UCI), `ply`, `judge_move`, `facts`, `explore`; plies from the ply cache or analysed through `analyse_ply` and put into it (§3.3); one engine-less facts tree per game rooted at the game's start, every asked path extended as `EXPLORED` with a new label each time, on-request families by `ensure` (§3.4); one-node search trees (`families = ()`, survey only, no attached lines) on one fact engine per engine port; `game_key_v1` (§8) |
| `agent/budget.py` | `Limits` (16 uncached plies, 40 searches, 2000 nodes, Q2), `Meter`, `MeteredPort` (the session's engine slot wraps every engine it starts around the one meter, R3), `SearchBudgetExhausted`, `analysis_bound` (`2·(min(t,2)+1)+4`), `Budget` (admission and charges, §3.5) |
| `agent/handles.py` | `Handles`: `j`, `c`, `f`, `s`, `x` refs carrying the session (`c3.k7f2a9`), each bound to its game key, source and address; resolved only in its session and game (§3.6) |
| `agent/projection.py` | fact records as JSON; piece identities `{piece, color, origin, square, type_now}` from the node's frame (§3.7) |
| `agent/definitions.py` | `agent_definitions_v1` (37 entries: the 15 proposition kinds, the 7 uses, the 2 sentence classes, the 7 token rules, `piece_identity`, `commentary_check_v1`, the 2 prompts, the tool set, the budget) and its digest (A9) |
| `agent/server.py` | `build_server(session)`: `MCPServer` with the six AG1 tools, the prompts `calliope_commentary` and `calliope_check`, the resources `calliope://definitions` (both registries), `calliope://glossary/ko`, `calliope://build` (the agent build, §10); one tool call at a time (a session lock, C9); refusals are tool errors |
| `agent/prompts/` | `commentary_ko_v1.md`, `check_ko_v1.md` (Korean, §6), `glossary_ko_v1.json` (the viewer's grade and label names, pieces, scopes, populations, statuses, sentence classes) |
| `tools/mcp` (new) | `python -m tools.mcp [--data] [--max-uncached-plies] [--max-searches] [--max-nodes]`: one session on stdio, logs on stderr |
| `server/cache.py` | `PlyCache.lock(key, exclusive)`: `fcntl.flock` on `<key>.lock`; `get` under the shared lock, `put` under the exclusive lock, using a sound pair another process wrote meanwhile (§9) |
| `server/files.py` | `atomic_write` through `<name>.<pid>.<token>.tmp`; `remove_temporaries` spares a running process's temporaries and removes dead processes' and old-style ones (§9) |
| `server/__init__.py` | exports `analyse_ply` (C1) |
| `reasoning/__init__.py` | exports `DEFINITIONS`, `REGISTRY_DIGEST`, `current_digest`, `exposed`, `Exposed` (C2; `__all__` only, no build change) |
| `facts/__init__.py` | exports `AtLeast`, `HistoryUnknown`, `NotObserved` (record value types the projection names) |
| `pyproject.toml` | the optional group `agent`: `mcp==2.3.0` (A2, C8) |
| `CLAUDE.md`, `tests/test_package_boundaries.py`, `tests/README.md` | the fifth package (Q1) |

## 2. Choices and departures (for the reviewer)

- **`open_game` summaries.** AG-D §3 lists the grade, label and text "for the plies already cached
  and those in `plies`". Loading a cached ply replays its stored tree and projects it: 0.9 s per
  ply on `g1014` (measured), about a minute for a whole game. `open_game` therefore marks every
  ply `cached` (a file check) and gives the summary only for the plies in `plies`; `ply` reads any
  one. Proposed as an AG-D amendment.
- **An exhausted meter stops the work.** `SearchBudgetExhausted` is neither a fact-engine error nor
  an engine error, so neither the fact engine, the reasoner nor `analyse_ply` absorbs it: an
  analysis it interrupts ends with the exception, is never put into the cache, and the slot is not
  restarted. (Were it a `FactEngineError`, the reasoner would record later rounds as refused and
  return an analysis, and DF-D's closed refusal list would have to name it.) The session also
  compares the meter's refusals before and after, so an analysis that absorbed one would still be
  discarded.
- **Admission.** An uncached analysis needs a ply of `max_uncached_plies` (charged on admission)
  and at least `analysis_bound(t)` searches left; `open_game` counts the uncached plies of its range
  first and checks the first ply's bound; a search needs one search left unless the session
  searched that path before (a store hit), and one node.
- **The search engine.** One `FactEngine(engine = slot.port)` per port object holds the session's
  search store; after a restart a new one is made (its store starts empty; correctness is not
  affected, a repeated search after a restart is charged again).
- **The facts tree's eager families** are the default set, as the stored trees'; the facts tree and
  a stored tree hold equal records for every family both computed (test).
- **FEN games.** A game opened with `fen` and `moves` has the header `result: "*"` (the PGN
  parser's default) and no other; AG-D §8's note on game keys holds.
- **Search answers.** Each line: rank, move (UCI, SAN), score (`cp_white` or `mate_white`), WDL
  (`permille_white`, null when the engine gives none), `expected` (`quality_v1`, 1/2000 for the
  side to move), depth, the PV with SAN and `by: engine`.
- **Handles in AG1** are served and resolvable; their use — propositions citing them — is AG2.

## 3. Measurements (Q2, AG-D §3.5)

Stockfish 19, profile `d12_mpv5_v1`, `g1014`:

| Step | Engine calls | Time |
| --- | --- | --- |
| `open_game` with ply 33 (17.Ne3, uncached) | 3 | 3.2 s |
| `judge_move` 17.Kd1 (uncached) | 3 | 1.9 s |
| `explore` after 17.Ne3 with `search` | 1 | 0.4 s |
| `ply` 33 from the cache (load and projection) | 0 | 0.9 s |
| `ply` 33 answer size | — | 41.8 kB |

An uncached analysis took 3 searches here; the bound admits it with 10 left. With the defaults, a
session can analyse about 13 uncached plies and search the rest — consistent with
`max_uncached_plies = 16`.

## 4. Test obligations (AG-D §11, the AG1 part)

| # | Test |
| --- | --- |
| 1 | `tests/test_package_boundaries.py`: `src/calliope` holds the five packages; the agent imports only public names; nothing imports it; `current_digest()` with the agent loaded equals it without, and the two registries share no id |
| 2 | `tests/agent/test_session.py`: `open_game` (PGN; FEN and moves in SAN and UCI; with and without `plies`); `ply` equals `analyse_game(…, detail=True)`'s `analysis`; `judge_move` of a played move equals `ply`, of an unplayed one equals a direct `analyse_ply`, and by `from_root` is cached; `facts` with identities (a promoted pawn: `type_now` queen), the root's edge family, span and unknown families refused; `explore` without and with `search` (one search) and with an empty line, `by` marks, balances. `tests/agent/test_budget.py`: the meter charges before the engine and keeps a failed search; failure → restart → retry charge both attempts to one meter; a store hit is free; an exhausted meter stops the analysis, without a restart, and caches nothing; uncached analyses from `open_game`, `ply` and `judge_move` count, a new FEN included, cached plies are free; `open_game` counts its range first; searches and nodes refused. `tests/agent/test_server.py`: the tools, prompts and resources listed; every tool through the MCP client, progress notifications; a budget refusal and a wrong ply as tool errors |
| 3 | `test_session.py`: after exploring, judging and `facts`, every stored bundle's bytes are unchanged; the facts tree's records equal the stored tree's for every family both hold (≥ 8) |
| 4 | `test_session.py`: refs unique; resolved to their source (path, tree digest); refused for another game, from another session, and when unknown |
| 8 | `tests/server/test_concurrency.py`: two processes analysing one uncached ply write one pair (the second uses the first's under the lock); a reader during a writer's pause between tree and graph waits for the whole pair (both tests fail with the lock disabled); the cleanup spares a running process's temporary and removes a dead one's and an old-style one |
| 9 | `test_server.py`: the prompts in Korean, the resources' digests (`definitions_v1`, `agent_definitions_v1`), the glossary, the agent build |
| 10 | `tests/agent/test_stockfish.py` (gated): 17.Ne3 from its position — `ply` (its supported material gain fails `ATTRIBUTED`), `judge_move` 17.Kd1, a search after 17.Ne3, the budget used |

Tests 5–7 (propositions, sentences, delivery) belong to AG2.

The whole suite with Stockfish and the `agent` group: **1217 passed** (17 min; DF1's baseline 1189).
`python -m tools.mcp` was also run over stdio with the SDK's client on `g1014`.

## 5. Running it

```json
{"mcpServers": {"calliope": {"command": "/home/coder/Calliope/.venv/bin/python",
  "args": ["-m", "tools.mcp"], "cwd": "/home/coder/Calliope",
  "env": {"CALLIOPE_STOCKFISH_PATH": "/home/coder/opt/stockfish/stockfish"}}}}
```

The server shares the analysis server's data directory (`~/.local/share/calliope`) and its ply
cache; both may run at once (§9).

## 6. Not in this packet

AG2: propositions and their verification, `submit_commentary`, the sentence check S1–S6,
`calliope.server.commentary`, `commentary`, the HTTP route and the combined document. AG3: the
viewer's panel and the MCP App.
