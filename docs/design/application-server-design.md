# Application — AS-D design: the local analysis server

Status: **rev. 1 — awaiting independent review**.
Date: 2026-10-12. Base: `main @ 3d1f974`. Inputs:
[`application-result-design.md`](application-result-design.md) (AR-D: `calliope_result_v1`, §9's
AS-D row); [`application-ar1-implementation.md`](application-ar1-implementation.md) (AR1, §5);
[`reasoning-r4-design.md`](reasoning-r4-design.md) (R4-D: bundles, `load` by replay,
`tools/explain_game`); [`redesign-status-and-roadmap.md`](redesign-status-and-roadmap.md) §5.2
item 4.

Today a game is analysed by running `tools/explain_game` in a shell and opening the JSON in the
static viewer. This packet defines a small server: paste a PGN in the viewer, wait while it is
analysed, and read the result, from a phone. It also defines the one game pipeline that the tool
and the server share.

## 0. Owner answers (2026-10-12)

| Question | Answer | Consequence here |
| --- | --- | --- |
| Audience | the owner alone | one user, one process, no accounts and no rate limits (S1, S8) |
| Hosting | not decided; during development code-server's port proxy, later a Caddy site with `basic_auth` | bind to loopback, relative URLs only, no authentication in the app (S7, S8, §8) |
| Frontend | extend the static viewer | `viewer/index.html` gains an analyse panel; no build chain (§7) |
| Input | a PGN, pasted or picked as a file | no chess.com or Lichess download |

## 1. Decisions

| # | Decision |
| --- | --- |
| S1 | **One process, standard library only.** `http.server.ThreadingHTTPServer` serves the API and the viewer. One worker thread runs the jobs, one at a time, with one Stockfish process. No new runtime dependency: python-chess stays the only one (AR-D §5). |
| S2 | **A new redesign package `calliope.server`.** It imports the public names of `calliope.results`, `calliope.reasoning` and `calliope.facts`, and python-chess (it is AR-D G8's caller, which normalizes the game). It never imports the legacy MVP, and nothing in facts, reasoning or results imports it. `tests/test_package_boundaries.py` enforces both. |
| S3 | **One game pipeline for the tool and the server** (`calliope.server.pipeline`): PGN intake, normalization, grading from the headers, the per-ply loop and the document. `tools/explain_game` becomes a thin command line over it. |
| S4 | **Each ply's request holds the moves up to its target only.** The controller reads only `request.moves[:target]` (`controller.py`, round 0), so the analysis is the same; only the stored request differs. Two games that share an opening then share its plies' analyses (S5). |
| S5 | **A ply cache keyed by the request.** Every analysed ply is saved as its bundle pair (`fact_tree_v1`, `claim_graph_v1`). A later request with the same key is answered by `load` (replay, no engine) instead of a new analysis. A document built from the cache has `bundle.stored = true`. |
| S6 | **A job is named by its content.** The job id is a digest of the normalized game, the ply range, the grading spec, the engine and the reasoning build. Posting the same game again returns the same job and computes nothing new. |
| S7 | **Relative URLs and polling.** The API lives under `api/`, the viewer at the server root. The page reaches the API by relative URLs only, so it works under any path prefix (`/proxy/<port>/` today, a domain root later). Progress is read by polling every 2 s; no WebSocket and no server-sent events. |
| S8 | **Loopback by default, no authentication in the app.** The server binds `127.0.0.1`. Access from elsewhere goes through a proxy that authenticates: code-server's login during development, Caddy's `basic_auth` later. A POST must be `application/json`, which a cross-site form cannot send without a CORS preflight that the server never grants. |
| S9 | **State lives on disk, outside the repository.** Jobs, results and the ply cache live in a data directory (default `~/.local/share/calliope`). A restart re-queues unfinished jobs, and their finished plies come from the cache. |
| S10 | **The time-class rules move into `calliope.reasoning.grading`.** `time_class` (Lichess's rule, Q-D §3) and `chesscom_time_class` become public there, because a `src` package cannot import `tools/`. `tools/calibrate_curve` imports them from there. The grading build identity is unchanged. |

## 2. Scope
- **In scope:**
  - `calliope.server`: the pipeline (§3), the ply cache (§4), jobs (§5), the HTTP API (§6);
  - `tools/serve`, which starts the server (§8);
  - `tools/explain_game` rebuilt on the pipeline;
  - the viewer's analyse panel (§7);
  - tests (§10) and the roadmap entry.
- **Out of scope:**
  - several users, accounts, rate limits;
  - downloading games from chess.com or Lichess;
  - parallel plies, partial results while running, cancelling and deleting jobs (§11);
  - the Caddy site itself (owner, root; §8);
  - Korean.

## 3. The game pipeline (`calliope.server.pipeline`)

```text
parse_game(pgn_text: str) -> ParsedGame           # refuses with InputError (§6.3)
ParsedGame = (game: GameInput, sans: tuple[str, …], root: RootSpec, spec: GradingSpec,
              warnings: tuple[str, …])
plies_range(text: str | None, count: int) -> range
ply_request(parsed, ply, profile) -> AnalysisRequest
analyse_game(engine, parsed, plies: range, *, cache: PlyCache | None,
             on_ply: Callable[[PlyProgress], None] | None) -> dict   # calliope_result_v1
```

- **`parse_game`** moves `tools/explain_game`'s intake here, unchanged in meaning:
  - the first game of the text, read by `chess.pgn.read_game`;
  - SANs from python-chess, the root from the `FEN` header, `GameInput` normalized as AR-D §5
    (`game_input` today);
  - the grading spec from the headers (`grading_for` today), using the moved time-class rules
    (S10);
  - `warnings`: the default-curve fallback (the tool's message), and "only the first game is
    analysed" when the text holds more than one.
- **`ply_request`** builds `AnalysisRequest(root, sans[:ply], ply, profile, grading=spec)`: the
  prefix only (S4). Budget and language are the defaults.
- **`analyse_game`** runs one ply after another, in order. For each ply it uses the cache when the
  key is there (§4), and otherwise analyses, renders (`explain`), saves the bundle and stores it.
  It reports each ply to `on_ply`. At the end it returns `game_result(...)` with
  `EngineRun(engine.identity, profile)`.
- **The profile** is `EngineProfile()`, as in the tool (Stockfish `d12_mpv5_v1`, owner's choice).
- **`tools/explain_game`** keeps its options and its text output. Its document changes in one way:
  each ply's bundle digests are those of the prefix request (S4), so they differ from R4's. With
  `--bundles DIR` the tool still writes `{ply}.tree` / `{ply}.graph` there.

## 4. The ply cache

- **Key.** The sha256 of the compact UTF-8 JSON (sorted keys) of:

  ```text
  {"v": "ply_key_v1",
   "build": build_digest(reasoner.build()),
   "engine": engine.identity.fingerprint(), "profile": profile.fingerprint(),
   "root": {"fen": str | null, "moves": [uci, …]},
   "moves": [uci, …],               # the game's plies 1 … target, as UCI
   "target": int, "budget": {field: int, …}, "language": "en",
   "grading": {field: value, …}}    # the GradingSpec, field by field
  ```

  Everything that can change the bundle's bytes is in it. The build digest covers the fact
  families, templates, policies, label rules and their parameters, the phrasebook and the grading
  build (R4-D §2.1).
- **Files.** `<data>/plies/<key[:2]>/<key>.tree` and `.graph`. Each is written to a temporary
  file and renamed. The graph is written last, so a present graph means a complete pair.
- **Reuse.** `load(FactEngine(), tree, graph)` replays the analysis without an engine (R4). Before
  it is used, its request must equal `ply_request(...)`, and its build `reasoner.build()`.
  - A file that fails to load (`StoredGraphError`), or whose request or build differs, is a miss.
    The ply is analysed again and the files are replaced.
  - A hit and a fresh analysis give the same document bytes (test 3).
- **What the cache does not promise.** A search stopped by its time cap (2 s) or a round cut by
  its deadline can end differently on another run, so the bytes of a fresh analysis are not
  always reproducible (R4: "a non-reproducible tree"). The cache keeps the first result; it never
  claims a second run would agree.
- **Size.** About 65 KB of bundles per ply (R4 record: 200 files, 6.5 MB, for 100 plies), plus
  0.5–1 MB per game document (AR-D §8). Nothing is evicted in this packet (§11).

## 5. Jobs

### 5.1 Identity and files
- **Job id.** The sha256 of the compact UTF-8 JSON (sorted keys) of
  `{"v": "job_key_v1", "game": {"start_fen", "moves": [uci, …], "headers": {…}}, "plies":
  [first, last], "grading": {…}, "profile": […], "engine": […], "build": "<digest>"}`. The
  headers are those of `GameInput`, so the same moves with other players are another job.
- **Files** under `<data>/games/<id>/`:
  - `job.json`: the PGN text, the ply range text, the creation time (UTC, ISO 8601);
  - `result.json`: the `calliope_result_v1` bytes (`dumps`), written once, at the end, by rename;
  - `error.json`: `{"message": str, "at": time}` when the job failed.
- The data directory is created with mode `0700`. It holds PGNs with players' names.

### 5.2 States

```text
POST ──► queued ──► running ──► done
                       │
                       └──────► failed ──(POST again)──► queued
```

- **`POST` of a known id:**
  - `done`: answered at once (HTTP 200);
  - `queued` or `running`: its status (HTTP 202);
  - `failed`: `error.json` is removed and the job is queued again.
- **The worker** takes jobs in order and runs `analyse_game` with the cache. Progress is held in
  memory: plies done, plies from the cache, the current ply and its SAN, and the mean seconds of
  the plies analysed so far, which gives an estimate of the time left.
- **Failures.**
  - `InvalidAnalysisRequest` or `AnalysisFailed` on a ply fails the job with its message. No
    partial document is written.
  - An inconclusive ply is not a failure: the document records it (AR-D §3).
  - On `EngineError` the worker closes the engine, starts a new one and runs the ply again once.
    A second `EngineError` fails the job, and the next job starts a fresh engine.
- **Start-up.**
  - Stockfish is started once; a missing or unsupported binary stops the server with a message.
  - Every `<data>/games/<id>/` with `job.json` and neither `result.json` nor `error.json` is
    queued again, oldest first. Its finished plies are cache hits.
- **Limits.** At most 20 queued jobs; a further POST gets HTTP 503.

## 6. HTTP API

All paths are relative to the server root. Every API answer is JSON (UTF-8). Errors are
`{"error": "<message>"}`.

### 6.1 Routes

| Method and path | Answer |
| --- | --- |
| `GET ` (root) and `GET index.html` | the viewer page (§7), `text/html` |
| `POST api/games` | body `{"pgn": str, "plies": str?}`; 202 with a `Status` when queued or running, 200 when already done |
| `GET api/games` | `{"games": [Summary, …]}`, newest first |
| `GET api/games/{id}` | a `Status` |
| `GET api/games/{id}/result` | the `calliope_result_v1` document; 409 with a `Status` when not done |

Nothing else is served: no directory listing, no other file, no `OPTIONS`.

### 6.2 Bodies

```text
Status  = {"id": str, "state": "queued" | "running" | "done" | "failed",
           "created": str, "game": {"white"?, "black"?, "date"?, "result"?, "site"?},
           "plies": {"first": int, "last": int, "total": int, "done": int, "cached": int},
           "current": {"ply": int, "san": str}?,        # while running
           "queue_position": int?,                    # while queued, 1 = next
           "eta_seconds": int?,                       # while running, once a ply was analysed
           "error": str?,                             # when failed
           "warnings": [str, …]}
Summary = {"id", "state", "created", "game", "plies"}
```

- `plies.total` is the range's length; `done` counts finished plies, `cached` those from the cache.
- `GET api/games` lists every job in the data directory. Its `game` comes from the stored PGN.

### 6.3 Status codes and input checks

| Case | Code |
| --- | --- |
| an id that is not 64 lower-case hex digits, or unknown | 404 |
| a POST body that is not `application/json` | 415 |
| a body over 256 KiB | 413 |
| invalid JSON, `pgn` missing or not a string, `plies` not a string | 400 |
| no game in the text, no moves, an illegal move (`game.errors`), a `Variant` other than standard | 400, with python-chess's message |
| more than 600 plies | 400 |
| a ply range outside the game (the tool's rule: the first ply must exist, the last is clamped) | 400 |
| 20 jobs already queued | 503 |

- **Caching headers.** `result` is `Cache-Control: private, max-age=31536000, immutable`, since
  its id names its content. Status and lists are `no-store`.
- **Logging.** One line per request: method, path, code. Never the PGN.

## 7. Viewer (`viewer/index.html`)

- **When it appears.** On start, with neither `?file=` nor an embedded document, the page calls
  `GET api/games`. If that answers, the page shows an **analyse panel**:
  - a text area for the PGN, a file picker that reads a `.pgn` file into it, and an optional ply
    range;
  - the list of earlier games (players, date, state), each opening its result.

  Opened from a file, or from a server without the API, the page behaves exactly as today.
- **Running.** After the POST the page sets `?game=<id>` (`history.replaceState`) and polls
  `api/games/<id>` every 2 s. It shows the plies done out of the total, the current move, the
  queue position and the estimated time left, and any warning. When the job is done it fetches
  `api/games/<id>/result` and shows it with the existing `load`.
- **Reload.** `?game=<id>` reopens the job: its progress, or its result.
- **Relative URLs only** (S7): `fetch("api/games")`, never `fetch("/api/games")`. When the page's
  path ends neither in `/` nor in `.html` (for example `/proxy/8765`), the page first moves to the
  same path with a `/` added, so relative URLs resolve under the prefix.
- The text of the panel is Korean, like the rest of the page's interface.

## 8. Running it

```sh
CALLIOPE_STOCKFISH_PATH=$HOME/opt/stockfish/stockfish PYTHONPATH=. \
  .venv/bin/python -m tools.serve --port 8765
# options: --host 127.0.0.1 (default), --data ~/.local/share/calliope (default),
#          --viewer viewer (default: the repository's viewer/)
```

- **During development:** open code-server's `/proxy/8765/` (with the trailing slash). code-server
  asks for its login, so the app needs none.
- **Later (owner, root):** a Caddy site with `basic_auth` in front of `127.0.0.1:8765`, for
  example:

  ```text
  calliope.example.org {
  	basic_auth {
  		owner <hash from caddy hash-password>
  	}
  	encode gzip
  	reverse_proxy 127.0.0.1:8765
  }
  ```

  The page and the API need no change: they live at the site's root, and every URL is relative.
- `--host` other than a loopback address prints a warning that the app has no authentication.

## 9. Security

- Loopback bind; authentication by the proxy in front (S8).
- Fixed routes only; no path is mapped to a file except the one viewer page.
- POSTs must be `application/json`. No CORS header is ever sent.
- Size, ply and queue limits (§6.3).
- The data directory is `0700`, outside the repository, and never logged.

## 10. Test obligations

1. **Pipeline equals the tool.** On the scripted corpus (R4-D §4), `analyse_game` and the rebuilt
   `tools/explain_game` give the same text output as before and a document that validates.
2. **Prefix requests (S4).** For a ply in the middle of a game, the analysis with `sans[:ply]` and
   the one with all SANs have equal judgements, labels, claims and rendering. Only the stored
   request differs.
3. **Cache.**
   - A second `analyse_game` of the same game runs no search: the scripted engine is never called.
   - Its document equals the first's, byte for byte.
   - A game sharing the first ten plies with a cached one analyses only the plies after them.
   - A corrupted graph file, or one with another build, is a miss and is replaced.
   - A temporary file left by a crash is ignored.
4. **Job identity.** The same PGN posted twice gives one id and one job. Other headers give
   another id.
5. **States.** queued → running → done; a failing analysis gives `failed` with its message, and a
   new POST queues it again. Queue position and `cached` are reported. These tests inject a stub
   in place of the per-ply analysis, so they need no engine.
6. **Restart.** A data directory with an unfinished job is queued again at start-up, and its
   cached plies are not analysed again.
7. **Engine failure.** One `EngineError` restarts the engine and the ply succeeds; two fail the
   job, and the next job runs.
8. **HTTP.** Every row of §6.3, with its code; the routes of §6.1; `result` is 409 before done;
   `Cache-Control` headers; no `OPTIONS`, no other path.
9. **Viewer** (node, like `tests/viewer`):
   - no `fetch` or link in the page starts with `/`;
   - with a mocked `fetch`, the panel appears only when `api/games` answers, a POST leads to
     polling, and `done` loads the document;
   - a path without a trailing `/` is moved to one with it.
10. **Boundaries.** `calliope.server` imports no legacy module. Facts, reasoning and results never
    import it.
11. **Time classes (S10).** The existing time-class tests (`tests/tools/test_calibrate_curve.py`,
    `tests/tools/test_acceptance.py`, `tests/tools/test_explain_game.py`) pass unchanged against
    the moved functions, and `tools/calibrate_curve` keeps no copy of them.
12. **End to end (gated on Stockfish, like R4's corpus runner).** A short real game posted through
    HTTP reaches `done`, and its result validates against the schema.

## 11. Open questions (not in this packet)

- **Parallel plies.** The machine has two cores. Two engines would halve the wait, but searches
  that hit the time cap may end differently under load. To be measured first.
- **Partial results.** Showing the finished plies while a game is still running.
- **Cancel, delete, evict.** Removing a job, and limits on the cache's size.
- **Grading override.** Ratings and time class given in the POST, for PGNs without them.
- **Korean text.** Still postponed.

## 12. Delivery

| Packet | Content | Gate |
| --- | --- | --- |
| AS-D (this) | the server's design | independent review READY |
| AS1 | `calliope.server` (pipeline, cache, jobs, HTTP), `tools/serve`, `tools/explain_game` on the pipeline, the moved time classes, tests 1–8 and 10–12 | READY |
| AS2 | the viewer's analyse panel, test 9 | — (like the static viewer; the owner checks it on the phone) |
| later | the Caddy site (owner, root) | — |
