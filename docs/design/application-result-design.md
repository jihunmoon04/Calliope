# Application — AR-D design: the game result schema `calliope_result_v1`

Status: **rev. 1 — awaiting independent review**.
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
    "engine": {"name": "Stockfish 19", "binary_sha256": "<sha256>", "profile": "d12_mpv5_v1",
               "depth": 12, "multipv": 5},
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
  "evaluation": {"played": Score?, "best": Score?, "best_move": {"san", "uci"}?, "loss": int?},
  "text": str,
  "segments": [Segment, …],
  "claims": [ClaimSummary, …],
  "bundle": {"tree": "<sha256>", "graph": "<sha256>"}?
}
Score = {"cp": int} | {"mate": int}      # White's view; mate > 0 means White mates
```

- **`evaluation`** reads the judgement of the target move (R0-D §7):
  - `played` and `best` are S's lines' scores, converted to White's view;
  - `loss` is the expected-points loss in 1/2000, the number the grade came from;
  - `best_move` is rank 1;
  - all are absent when the judgement is inconclusive.
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
Ref = {"kind": "square", "square": "e4"}
    | {"kind": "piece", "square": "e4", "piece": "knight", "color": "white", "fen": "<fen>"}
    | {"kind": "move", "uci": "f3e5", "san": "Nxe5", "fen": "<fen before the move>"}
    | {"kind": "line", "fen": "<fen at its start>", "moves": [{"uci", "san"}, …]}
```

- **Concatenation.** The segments in order rebuild `text` exactly.
- **Where refs come from.** They are the source claim's own references (R3-D §7, the handle's
  set), restricted to what a board can show:
  - pieces (`PieceRef`) and squares (`SquareRef`);
  - moves (`MoveRef`, `SearchMoveRef`, witnesses);
  - lines (`LineSegment`, its attached plies).
- **Each ref carries the FEN it applies to.** A move or piece of a line is shown in its own
  position, not the ply's.
- **Judgement and label segments** reference the played move only.
- **The `"source"` value names the kind** of the segment's source (R3-D §7: a claim, the judgement,
  the label, a scope or `CONNECTIVE`).

## 5. Building it

```text
game_result(game: GameInput, plies: Iterable[PlyInput]) -> dict
GameInput = (start_fen, moves (SAN), headers: dict)
PlyInput  = (analysis: Analysis, rendered: RenderedExplanation, bundle_digests | None)
```

- **Pure.** The document is a function of its inputs: no clock, no engine. Two runs give equal
  JSON.
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
| AR1 | `calliope.results`, the schema file, tests, `tools/explain_game --json` | READY |
| then: a static viewer | one HTML page that loads a `calliope_result_v1` file: board, move list, text, segment highlights | — |
| then: AS-D / AS1 | the HTTP API (`POST /games`, progress, `GET /games/{id}`), the job queue, caching by bundle | READY |
