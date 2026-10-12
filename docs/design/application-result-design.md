# Application — AR-D design: the game result schema `calliope_result_v1`

Status: **rev. 2 — independent review NOT_READY (B1–B5) applied (§10); awaiting re-review**.
Date: 2026-10-12. Base: `main @ 9edfedd`. Inputs:
[`reasoning-r4-design.md`](reasoning-r4-design.md) (R4-D: analyses, bundles, `tools/explain_game`);
[`reasoning-r3-design.md`](reasoning-r3-design.md) (R3-D: segments and their sources, H6, H9);
[`redesign-status-and-roadmap.md`](redesign-status-and-roadmap.md) §5.2 item 4 (a new result model
replaces schema 0.2 / 0.3).

R0-D's reasoning packets are complete. A frontend now needs one stable document per analysed game
that does not expose the reasoning's internal types (`Analysis`, `Claim`, `NodeId`, `ProofScope`).
This packet defines that document, `calliope_result_v1`, the code that builds it, and its JSON
Schema. The API server, the job queue and the frontend are later packets (§9).

## 0. Decisions

| # | Decision |
| --- | --- |
| G1 | **One JSON document per game,** `calliope_result_v1`: the game, the grading, a provenance block and one record per ply. It is a projection of the per-ply analyses and renderings (R4), never a second source of truth. The bundles (`fact_tree_v1`, `claim_graph_v1`) stay the record, and each ply names its bundle by digest. |
| G2 | **A new redesign package `calliope.results`.** It imports only `calliope.reasoning` and `calliope.facts` public names and never the legacy MVP (`calliope.application` and the rest). `tests/test_package_boundaries.py` enforces it. |
| G3 | **No internal identifiers leak** except claim ids, which are stable digests and link a ply to its stored graph. Nodes become FENs and UCI moves; refs become squares and moves the board can draw. |
| G4 | **Segments carry their source and board refs** (§4), so a frontend can highlight what each phrase is about: the squares and moves its claim names. |
| G5 | **Engine numbers are data, not text** (R3-D H6 governs the text only). Each ply carries the S scores the grade came from (cp or mate, White's view) for an evaluation bar or graph. The text never states them. |
| G6 | **Provisional labels are flagged, not hedged** (R3-D H9): `label.provisional`. |
| G8 | **The caller normalizes; `calliope.results` checks and projects** (rev. 2, review B1, B2, B5). PGN parsing, SAN → UCI and FENs happen in the calling tool, with python-chess. The builder receives the whole normalized game and the engine run's metadata, and cross-checks them against every analysis. A mismatch raises `ResultError`. |
| G7 | **Versioning.** Adding an optional field keeps `v1`, and readers ignore unknown fields. Removing, renaming or changing a field's meaning needs `calliope_result_v2`. The JSON Schema ships with the package. |

## 1. Scope
- **In scope:**
  - `calliope.results`: the builder, `game_result(...)`, and `results/schema/calliope_result_v1.json`;
  - `tools/explain_game --json`, which writes this document instead of its ad-hoc records;
  - tests;
  - roadmap §5.2 item 4, recorded as started.
- **Out of scope:**
  - the HTTP API, jobs and caching (packet AS-D, §9);
  - the frontend and the static viewer (§9);
  - Korean;
  - game-level judgements such as accuracy or a key-moments list (§8).

## 2. Document

```text
{
  "schema": "calliope_result_v1",
  "provenance": {
    "reasoning_build_version": 1,
    "phrasebook": {"name": "phrases_en_v1", "digest": "<sha256>"},
    "engine": {"name": str, "binary_sha256": "<sha256>", "profile": str,
               "depth": int, "multipv": int},          # from EngineRun (§5), never a default
    "label_rules": {"brilliant": "brilliant_p2", "great": "great_p2", "miss": "miss_p2"}
  },
  "game": {
    "start_fen": "<fen>", "moves": [{"san": "e4", "uci": "e2e4"}, …],
    "headers": {"white": str?, "black": str?, "white_rating": int?, "black_rating": int?,
                "time_control": str?, "site": str?, "date": str?, "result": str?}
  },
  "grading": {"policy": "quality_v2", "model": "monotone_v1", "table": str?,
              "time_class": str?, "pool": "chesscom" | "lichess" | null,
              "band": int?, "clamped": bool, "fallback": bool},
  "plies": [Ply, …],          # in game order; a ply range when only part was analysed
  "summary": {"white": Counts, "black": Counts}
}
```

- **`grading.fallback`** is true when the grading spec could not be read from the headers and
  the default curve was used (R4 record §4, the open warning). A frontend can say so.
- **`summary`**: `Counts = {"grades": {grade: n, …}, "labels": {kind: n, …}, "inconclusive": n}`,
  over the analysed plies of that side.

## 3. `Ply`

```text
{
  "ply": int, "move_number": int, "side": "white" | "black",
  "san": str, "uci": str, "fen_before": str, "fen_after": str,
  "status": "decided" | "inconclusive", "reason": str?,       # reason only when inconclusive
  "grade": "best" | "excellent" | "good" | "inaccuracy" | "mistake" | "blunder" | null,
  "label": {"kind": "brilliant" | "great" | "miss" | "forced",
            "rule": str, "provisional": bool} | null,
  "evaluation": {"played": Score?, "best": Score?, "best_move": {"san", "uci"}?, "loss": int?,
                 "grade_basis": "best_move" | "expected_points" | "mate_distance" | null},
  "text": str,
  "segments": [Segment, …],
  "claims": [ClaimSummary, …],
  "bundle": {"tree": "<sha256>", "graph": "<sha256>", "stored": bool}?
}
Score = {"cp": int} | {"mate": int}      # White's view; mate > 0 means White mates
```

- **`evaluation`** reads the judgement of the target move (R0-D §7):
  - `played` and `best` are S's lines' scores, converted to White's view;
  - `best_move` is rank 1;
  - all are absent when the judgement is inconclusive.
- **`loss` and `grade_basis`** (rev. 2, review B3).
  - `loss` is the expected-points loss in 1/2000 (`Judgement.loss`). It is a measurement in its
    own right, not always the grade's cause.
  - `grade_basis` names what decided the grade, following `observer.grade`:
    - `best_move` when the played move is rank 1 (BEST, whatever the loss);
    - `mate_distance` when the played and best lines both mate for the same side, so the grade is
      the mate-distance table's;
    - `expected_points` otherwise (the loss bands).
  - A frontend explains a grade only through its basis. For example, `loss = 0` with `good` under
    `mate_distance` is a slower mate.
- **`bundle.stored`** (rev. 2, review note) is true only when the caller wrote both documents and
  re-loaded them (R4). Digests computed for `--json` alone have `stored = false`: they identify
  the analysis, but do not promise a file to fetch.
- **`claims`**: every SUPPORTED claim of the target, plus every claim a segment names:
  `{"id": "<claim id>", "template": str, "role": str, "status": str, "reason": str?,
  "rendered": bool}`. INCONCLUSIVE claims named in the qualification are included. REFUTED claims
  are left out (R3-D H7).
- **`bundle`** is present when the analysis was saved (R4). A frontend can fetch the stored graph by
  it later.

## 4. `Segment`

```text
{
  "text": str,
  "source": "judgement" | "label" | "claim" | "scope" | "connective",
  "claim": "<claim id>"?,            # for "claim", and for "scope" of one claim
  "claims": ["<claim id>", …]?,      # for a "scope" sentence over several claims
  "refs": [Ref, …]                   # empty when the source names nothing on the board
}
Ref = {"kind": "square", "square": "e4", "fen": "<fen>"}
    | {"kind": "piece", "square": "e4", "piece": "knight", "color": "white", "fen": "<fen>"}
    | {"kind": "move", "uci": "f3e5", "san": "Nxe5", "fen": "<fen before the move>"}
    | {"kind": "line", "fen": "<fen at its start>", "moves": [{"uci", "san"}, …]}
```

- **Concatenation.** The segments in order rebuild `text` exactly.
- **Where refs come from (rev. 2, review B4).** They are the references **the segment's text
  expressed**: one per slot filled in its chosen variant, in slot order, never the source claim's
  whole reference set.
  - **`render.trace(plan, analysis)`** (new in R3's renderer) returns them per segment. It runs
    the same bindings and the same variant choice as `render`.
  - Each formatter of R3-D §3 also yields the reference it formatted: a `PieceRef` for `piece`; a
    `MoveRef`, `SearchMoveRef` or witness for `move`; a `LineSegment` for `line`.
  - `amount`, `count` and `depth` slots yield none.
  - `render` and `RenderedExplanation` are unchanged, so stored bundles and their bytes are not
    affected.
- **Every ref carries the FEN it applies to.**
  - A piece or square: the position at its node (`PieceRef.node`).
  - A move: the position before it.
  - A line: the position at its start.
  - So a move or piece of a line is drawn in its own position, not the ply's.
- **Judgement and label segments** reference the played move only.
- **The `"source"` value names the kind** of the segment's source (R3-D §7: a claim, the judgement,
  the label, a scope or `CONNECTIVE`).

## 5. Building it

```text
game_result(game: GameInput, engine: EngineRun, plies: Iterable[PlyInput]) -> dict
GameInput = (start_fen, moves: tuple[GameMove, …], headers: dict)
GameMove  = (san, uci, fen_before, fen_after)          # the whole game, normalized by the caller
EngineRun = (identity: EngineIdentity, profile: EngineProfile)   # the run's, from the engine port
PlyInput  = (analysis: Analysis, rendered: RenderedExplanation,
             bundle: (tree_digest, graph_digest, stored) | None)
```

- **Pure.** The document is a function of its inputs: no clock, no engine. Two runs give equal
  JSON.
- **Who normalizes (rev. 2, review B1).** The caller parses the PGN and builds `GameInput` with
  python-chess: `tools/explain_game` today, the API worker later. `calliope.results` does not parse
  SAN. It projects what it is given, so a partial analysis (`--plies 1-10`) still has the whole
  game's moves and FENs.
- **Where the engine provenance comes from (rev. 2, review B2).** `EngineRun` is the engine port's
  `identity` and the request's `EngineProfile`, passed by the caller. No default is written.
- **Cross-checks (rev. 2, review B5).** A failure raises `ResultError`.
  - `game.start_fen` and the analysis's root agree. The root is `TreeView.request(1).root`,
    normalized.
  - Each analysis's moves (`RoundZero.request.moves`, as the tree logged them in UCI) are the
    game's first plies, up to and including the target. Its target ply is the `PlyInput`'s ply,
    and its subject move is `game.moves[ply - 1].uci`.
  - Plies are strictly increasing, with no duplicates.
  - Every analysis has the same normalized grading spec and the same `EngineProfile`. Every search
    of every analysis carries `EngineRun.identity`.
  - `game.moves[i].fen_after` equals `game.moves[i + 1].fen_before`, and the first `fen_before`
    is `start_fen`.
- **Serialization.** UTF-8 JSON with keys in the order of §2–§4, compact.
- **Checks at build time.**
  - Every ply's `text` equals its segments joined.
  - Every segment's `claim` is listed in `claims`.
  - A failure raises `ResultError` (a new error class in `calliope.results`).
- **The JSON Schema** is `results/schema/calliope_result_v1.json` (JSON Schema 2020-12).
  - It is shipped for frontends: validation and type generation.
  - The tests validate every built document against it, with `jsonschema` as a development
    dependency.
  - The runtime does not depend on `jsonschema`. `python-chess` stays the only runtime dependency.
- **Grading fields** come from the target judgement's `Curve` (Q-D):
  - `model`, `table`, `time_class` and `band`;
  - `pool` from the request's `GradingSpec.rating_pool` when ratings were used;
  - `clamped` when the conversion or band was clamped;
  - `fallback` when the spec named no ratings and no scale.

## 6. `tools/explain_game`
- `--json OUT` writes `calliope_result_v1`. Before, it wrote ad-hoc per-ply records (R4 §5); the
  bundle digests are kept in `bundle`.
- The text output is unchanged.
- When the grading falls back to the default curve, the tool also prints one warning line. This
  closes the R4 record's §4 open item.

## 7. Test obligations
1. **Round trip and determinism:** `game_result` twice gives equal JSON. The document validates
   against the schema.
2. **Text and segments:** on every corpus case (R4-D §4), the segments rebuild the text, and each
   claim segment's id is in `claims`.
3. **Refs:**
   - the fork case: the fork segment names the forking piece and the fork move, each with its FEN;
   - the better-move segment names its line;
   - the judgement segment names the played move.
4. **Evaluation:**
   - White's-view conversion for a Black move;
   - mate scores;
   - absent when the judgement is inconclusive (the corpus `inconclusive_exact` case).
5. **Labels:** `forced`, `brilliant` with `provisional = true`, and `miss` with rule `miss_p2`, from
   corpus cases.
6. **Grading block:** a chess.com rated game; a game without ratings (`fallback = true`).
7. **Boundaries:** `calliope.results` imports no legacy module, and nothing in reasoning or facts
   imports it.
7a. **Partial analysis (B1):** plies 3–4 of a game yield a document with the whole game's moves and
   two ply records.
7b. **Provenance (B2):** the engine block equals `EngineRun`. An analysis whose searches carry
   another identity is refused.
7c. **Grade basis (B3):** `best_move` on a rank-1 move; `mate_distance` on a slower mate
   (`loss = 0`, a non-BEST grade); `expected_points` on a blunder.
7d. **Refs (B4):**
   - the fork segment's refs are exactly the forking piece and the fork move, in slot order, each
     with its FEN;
   - no ref of the claim's other evidence appears;
   - `trace` and `render` choose the same variant on every corpus case;
   - a square ref carries its FEN.
7e. **Cross-checks (B5):** each refused with `ResultError`:
   - an analysis of another game;
   - another start position;
   - a target off by one;
   - duplicate plies;
   - two gradings;
   - a broken FEN chain.
8. **Tool:** `--json` writes a valid `calliope_result_v1`, and the fallback warning is printed.

## 8. Open questions
- **Game-level judgements** (accuracy, key moments, a phase split). They are not defined yet. A
  later additive field in `v1`, or a packet of its own.
- **Language.** One `text` per ply, in the request's language (`en`). Several languages per
  document can be added later.
- **Size.** About 6–10 KB per ply with segments and refs, so 0.5–1 MB for a 100-ply game.
  Acceptable for one document; the API may page by ply (§9).

## 9. Delivery and what follows

| Packet | Content | Gate |
| --- | --- | --- |
| AR-D (this) | `calliope_result_v1`, its builder and schema, the tool's JSON | independent review READY |
| AR1 | `calliope.results`, `render.trace` (R3 addition, §4), the schema file, tests, `tools/explain_game --json` | READY |
| then: a static viewer | one HTML page that loads a `calliope_result_v1` file: board, move list, text, segment highlights | — |
| then: AS-D / AS1 | the HTTP API (`POST /games`, progress, `GET /games/{id}`), the job queue, caching by bundle | READY |

## 10. Review dispositions (rev. 1 `6b7452e`, independent review: NOT_READY)

The review passed G1–G7 and the delivery order. Each finding was checked against the code.

| Finding | Disposition |
| --- | --- |
| B1 a partial analysis cannot give the whole game's UCI and FENs | Valid. Applied (G8, §5): the caller normalizes the whole game into `GameMove`s with python-chess, and `calliope.results` checks and projects them. Test 7a. |
| B2 no source for the engine provenance | Valid: the session's identity is private to `FactTree`, and an analysis may have no search to read it from. Applied (§5): `EngineRun` (the port's `identity`, the profile) is an input. Every search must carry that identity. Test 7b. |
| B3 `loss` is not always the grade's cause | Valid: `observer.grade` grades same-side mates by mate distance. Applied (§3): `loss` is described as its own measurement, and `grade_basis` (`best_move`, `mate_distance`, `expected_points`) names the cause. Test 7c. |
| B4 refs without a position, and the claim's whole reference set instead of what the text said | Valid: a bare square has no position, and the R3 `Handle` holds every readable reference. Applied (§4): every ref carries its FEN. Refs are the filled slots of the chosen variant, from a new `render.trace` that reuses `render`'s bindings and variant choice; `render` and the stored bytes are unchanged. Test 7d, including no extra refs. |
| B5 no cross-check between the game and the analyses | Valid. Applied (§5): root, the move prefix, the target, ply order, one grading, one profile and one engine identity, and the FEN chain. Test 7e. |
| (note) a digest is not a fetchable file | Applied (§3): `bundle.stored`. |
