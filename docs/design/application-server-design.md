# Application — AS-D design: the local analysis server

Status: **rev. 3 — review NOT_READY applied (§13); re-review READY_WITH_CORRECTIONS applied (§14); final re-review READY; amended by AS1 (§15) and CC1 (§16)**.
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
| S4 | **One normalized request per ply** (rev. 2, review B1 and note). The analysis records its request as `request.normalized()` makes it (`RoundZero.request`): the root as `FactEngine.normalize_open` resolves it, the moves up to the target as canonical UCI, nothing after the target. The cache key (§4) and the check of a cache hit both use exactly this form, computed before the analysis. Two games that share an opening therefore share its plies' analyses (S5), when every other key field is equal too: the grading spec (ratings, time class, pool), the profile, the engine and the build (rev. 3, re-review note). |
| S5 | **A ply cache keyed by the request.** Every analysed ply is saved as its bundle pair (`fact_tree_v1`, `claim_graph_v1`). A later request with the same key is answered by `load` (replay, no engine) instead of a new analysis. A document built from the cache has `bundle.stored = true`. |
| S6 | **A job is named by its content and its environment.** The job id is a digest of the normalized game, the ply range, the grading spec, the engine and the reasoning build. Posting the same game again returns the same job and computes nothing new. A job is only ever run in the environment its id names (rev. 2, review B4, §5.1). |
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
- **`ply_request`** builds `AnalysisRequest(root, sans, ply, profile, grading=spec)`, as the tool
  does today. Budget and language are the defaults.
- **`normalized_ply(parsed, ply, profile)`** (rev. 2, review B1) is the request the analysis will
  record (S4), computed before it runs:
  `replace(ply_request(...), root=FactEngine().normalize_open(OpenRequest(root=parsed.root)).root,
  moves=uci[:ply])`, where `uci` are the game's moves as python-chess's `Move.uci()`, the form the
  fact engine's `extend` records. It feeds the cache key and the hit check (§4).
- **`analyse_game`** runs one ply after another, in order. For each ply it uses the cache when the
  key is there (§4), and otherwise analyses, renders (`explain`), saves the bundle and stores it.
  It reports each ply to `on_ply`. At the end it returns `game_result(...)` with
  `EngineRun(engine.identity, profile)`.
- **One path into the document** (rev. 3, re-review B1). Every ply enters `game_result` as it was
  loaded from its cache files, whether it was just analysed or found in the cache:
  1. a fresh analysis that passed the engine-failure check (§5.2) is saved and its two files are
     written (§4);
  2. the pair is read back and `load`ed, and `save(loaded, again)` must give the same bytes, as
     the tool's `--bundles` does (R4);
  3. only then is the ply a `PlyInput` of the loaded analysis and rendering, with
     `Bundle(tree, graph, stored=True)` (AR-D §3: stored means written and re-loaded).

  If step 2 fails, the files are removed, the ply is not published, and the job fails with
  "the stored analysis of ply N did not re-load: …". This is a defect, not an engine failure,
  and is not retried. The tool keeps its own rule: `stored` only with `--bundles`.
- **The profile** is `EngineProfile()`, as in the tool (Stockfish `d12_mpv5_v1`, owner's choice).
- **`tools/explain_game`** keeps its options, its text output and its bundles' bytes: the requests
  are the same as today's. With `--bundles DIR` it still writes `{ply}.tree` / `{ply}.graph` there.
  (rev. 1 said the digests would change; they do not, because the stored request is the
  normalized one, which already drops the moves after the target. Review note.)

## 4. The ply cache

- **Key.** The sha256 of the compact UTF-8 JSON (sorted keys) of:

  ```text
  {"v": "ply_key_v1",
   "build": build_digest(reasoner.build()),
   "engine": engine.identity.fingerprint(), "profile": profile.fingerprint(),
   "root": {"fen": str, "moves": [uci, …]},   # normalized_ply(...).root (§3), never null
   "moves": [uci, …],               # normalized_ply(...).moves: plies 1 … target, as UCI
   "target": int, "budget": {field: int, …}, "language": "en",
   "grading": {field: value, …}}    # the GradingSpec, field by field
  ```

  Every request field comes from `normalized_ply` (§3), the form the stored analysis carries
  (rev. 2, review B1). A PGN without a `FEN` header and one whose `FEN` header is the standard
  start position give the same key.

  Everything that can change the bundle's bytes is in it. The build digest covers the fact
  families, templates, policies, label rules and their parameters, the phrasebook and the grading
  build (R4-D §2.1).
- **Files.** `<data>/plies/<key[:2]>/<key>.tree` and `.graph`. Each is written atomically (§5.1).
  The graph is written last, so a present graph means a complete pair.
- **Reuse.** `load(FactEngine(), tree, graph)` replays the analysis without an engine (R4). Before
  it is used, its `round_zero.request` must equal `normalized_ply(...)` (§3), never the raw
  `ply_request`, whose root may be `None` and whose moves are SAN (rev. 2, review B1). Its
  `build` must equal `reasoner.build()`.
  - **A miss** (rev. 2, review B2) is any of: a missing or unreadable file; `StoredTreeError`
    (the fact tree fails ingestion, replay or verification; `load` reads it through
    `fact_engine.load`); `StoredGraphError` (the claim graph); a request or build that differs.
    The ply is analysed again and both files are replaced.
  - Any other exception is a defect, not a miss: it fails the job (§5.2).
  - The document of the run that first stored a ply and the documents of later hits on it are
    equal, byte for byte, because both are built from the same loaded files (§3; test 3). This
    says nothing about a second, independent analysis of the same request (below).
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
- **The environment** (rev. 2, review B4) is `{"engine": identity.fingerprint(), "profile":
  profile.fingerprint(), "build": build_digest(...)}`: the parts of the id that do not come from
  the PGN. It is written into `job.json`, and a job runs only while the server's current
  environment equals it.
- **Atomic writes** (rev. 3, re-review B2). Every file the server writes (`job.json`,
  `result.json`, `error.json` and the cache pair) is written to `<name>.tmp` in the same
  directory, flushed and `fsync`ed, then renamed over `<name>`. A reader never sees a partial
  file under its real name. Left-over `*.tmp` files are ignored, and removed at start-up.
- **Files** under `<data>/games/<id>/`:
  - `job.json`: the PGN text, the ply range text, the environment, the creation time (UTC,
    ISO 8601);
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
  - **Engine failure** (rev. 2, review B3). The reasoner never lets `EngineError` out, so the
    worker reads it from the result. An *engine failure* is an `EngineError` that is neither
    `EngineOutputError` nor `EngineUnsupportedError`: the process failed, exited or timed out
    (`uci.py`). The two subclasses are refusals about the engine's answer or identity, not about
    the process, and are not retried.
    - **Round 0:** `AnalysisFailed` whose `cause` is an engine failure (`controller.py`, round 0
      and its ensure).
    - **Later rounds:** a recorded outcome `REFUSED(EngineError)` in any `analysis.rounds[*]
      .requests` (`runner._submit` records the exact type name, so the subclasses appear under
      their own names). The analysis completed, but some evidence was refused only because the
      process failed. It is discarded, never cached.
    - **On either,** the worker closes the engine, starts a new one, checks that its identity
      still equals the job's environment, and runs the ply again once. A second engine failure
      on the same ply fails the job; the next job starts with a fresh engine.
    - Other refusals (`REFUSED(BudgetExceededError)`, `REFUSED(EngineOutputError)`, …) and
      `AnalysisFailed` with another cause are part of the analysis as the reasoner defines it:
      the first are kept, the second fails the job as above. Neither is retried.
- **Start-up.**
  - Stockfish is started once; a missing or unsupported binary stops the server with a message.
  - **A damaged job is isolated** (rev. 3, re-review B2). A directory whose `job.json` is
    missing, unreadable, not JSON, or lacks a field or a field's type (§5.1) is not resumed. It
    is listed as `failed` with "the job file is damaged; post the game again", and `error.json` is
    written for it when the directory is writable. One log line names it. The server starts and
    the other jobs resume. A damaged `error.json` reads as `failed` with that same message, and a
    `result.json` that is not JSON is treated as absent, so the job is resumed if its `job.json`
    is sound.
  - Every `<data>/games/<id>/` with a sound `job.json` and neither `result.json` nor `error.json` is
    resumed, oldest first, **only if its stored environment equals the current one** (rev. 2,
    review B4). Its finished plies are cache hits.
  - Otherwise the job is marked `failed` with "the engine or the reasoning build changed since
    this game was posted; post it again". Posting the PGN again gives a new id under the new
    environment, so the old id never names a result of another environment, and `result`'s
    `immutable` header stays true.
  - A job that is `done` keeps its result whatever the current environment: that result is the
    record of the environment its id names.
- **Limits.** At most 20 queued jobs; a further POST gets HTTP 503.
- **One lock** (rev. 2, review note). `ThreadingHTTPServer` answers POSTs concurrently. Looking up
  an id, the queue-capacity check, writing `job.json` and enqueueing happen under one lock, which
  the worker also holds for every state change. Two simultaneous POSTs of the same game make one
  job; the 21st queued job is refused even when the POSTs race. The PGN is parsed and the id
  computed before the lock is taken.

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
2. **Normalized requests (S4; rev. 2, review B1 and note).**
   - `normalized_ply` equals the analysis's `round_zero.request` on: a game whose SANs differ
     from their UCI (castling, a capture, a promotion); a PGN without a `FEN` header (the
     standard start); a PGN with a `FEN` header.
   - For a ply in the middle of a game, the bundle bytes with all SANs and with `sans[:ply]` are
     equal, so the key may ignore the moves after the target.
3. **Cache.**
   - A second `analyse_game` of the same game runs no search: the scripted engine is never called.
   - Its document equals the first's, byte for byte, and every ply of both has
     `bundle.stored = true` (re-review B1).
   - A bundle whose re-load fails on first storage (an injected `load` failure) fails the job: no
     `result.json`, and its cache files are removed.
   - A game sharing the first ten plies with a cached one analyses only the plies after them.
   - A hit is found for a game given in SAN without a `FEN` header (the raw request and the
     stored one differ in form, the normalized ones do not; review B1).
   - A corrupted `.graph` (`StoredGraphError`), a corrupted `.tree` (`StoredTreeError`), a
     missing `.tree` and a graph of another build are each a miss and are replaced (review B2).
   - A temporary file left by a crash is ignored.
4. **Job identity.** The same PGN posted twice gives one id and one job. Other headers give
   another id.
5. **States.** queued → running → done; a failing analysis gives `failed` with its message, and a
   new POST queues it again. Queue position and `cached` are reported. These tests inject a stub
   in place of the per-ply analysis, so they need no engine.
6a. **Damaged files** (re-review B2): a `job.json` truncated mid-write, one that is not JSON, one
   missing `pgn`, and a left-over `job.json.tmp` next to a sound job. The server starts; the
   damaged jobs are `failed` with the damaged-file message; the sound job resumes; the `.tmp`
   file is gone. A write interrupted before its rename (simulated by failing `os.replace`) leaves
   the previous file intact.
6. **Restart.** A data directory with an unfinished job is queued again at start-up, and its
   cached plies are not analysed again. The same job with another stored engine fingerprint or
   build digest is marked `failed` with the environment message, and its id is never resumed
   (review B4).
7. **Engine failure** (review B3), with an engine port that fails on demand:
   - round 0: `AnalysisFailed` caused by an `EngineError` restarts the engine and the ply
     succeeds; the same failure twice fails the job, and the next job runs;
   - a later round: a `REFUSED(EngineError)` outcome discards the analysis (nothing cached), the
     engine restarts and the ply is analysed again;
   - not retried: `REFUSED(EngineOutputError)` and `REFUSED(BudgetExceededError)` keep the
     analysis; `AnalysisFailed` with another cause fails the job at once;
   - a restarted engine with another identity fails the job.
7a. **Concurrency** (review note): two threads posting the same PGN at once make one job; with the
   worker held, 25 distinct concurrent POSTs give exactly 20 queued jobs and five 503s.
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

## 13. Review dispositions (rev. 1 `228825e`, independent review: NOT_READY)

The review passed the architecture, the package boundary, the shared pipeline, the reuse of
`calliope_result_v1` and the relative-URL API. Each finding was checked against the code.

| Finding | Disposition |
| --- | --- |
| B1 a cache hit is compared with the raw request, whose root may be `None` and whose moves are SAN, while the stored request is normalized | Valid: `request.normalized()` stores the root from `normalize_open` (`start.fen(en_passant="fen")`) and canonical UCI. Applied (S4, §3, §4): `normalized_ply` computes that form before the analysis; the key and the hit check both use it. Tests 2 and 3. |
| B2 a corrupted tree raises `StoredTreeError`, not `StoredGraphError` | Valid: `storage.load` reads the tree through `fact_engine.load`. Applied (§4): both errors, and missing or unreadable files, are misses; any other exception fails the job. Test 3 corrupts the `.tree` too. |
| B3 the worker never sees `EngineError` | Valid: round 0 wraps it in `AnalysisFailed(cause=…)`, and later rounds record `REFUSED(EngineError)` and go on. Applied (§5.2): an engine failure is an `EngineError` other than `EngineOutputError` and `EngineUnsupportedError`, read from the round-0 cause or a later round's outcome; the ply is discarded, the engine restarted and the ply run once more. Other refusals are not retried. Test 7. |
| B4 a resumed job could run in another environment than its id names | Valid. Applied (§5.1, §5.2): `job.json` stores the environment; a job resumes only when it equals the current one, otherwise it is marked failed and a new POST gives a new id. A restarted engine must keep the job's identity. Test 6. |
| (note) S4: the stored request already drops the moves after the target, so the bundle digests do not change | Valid: `normalized()` keeps `extends`' moves only. Applied (S4, §3): the tool's requests and bundle bytes are unchanged; test 2 checks that the key may ignore later moves. |
| (note) concurrent POSTs | Applied (§5.2): one lock over lookup, capacity, `job.json` and enqueue, shared with the worker. Test 7a. |

## 14. Re-review dispositions (rev. 2 `f873db59`: READY_WITH_CORRECTIONS)

The re-review passed B1–B4 and both notes of §13.

| Finding | Disposition |
| --- | --- |
| B1 when a newly stored bundle is re-loaded is not defined, so a first run's `stored = true` would not mean what AR-D §3 says | Valid. Applied (§3): one path. A fresh ply is saved, written, re-loaded and saved again to the same bytes before it becomes a `PlyInput`; fresh and cached plies both enter the document from the loaded files, with `stored = true`. A failed re-load removes the files and fails the job. Test 3. |
| B2 `job.json` is not written atomically, and a damaged one could stop the restart | Valid. Applied (§5.1, §5.2): every file is written to a `.tmp`, `fsync`ed and renamed; a damaged `job.json`, `error.json` or `result.json` is isolated as described, and the server still starts. Test 6a. |
| (note) "a hit and a fresh analysis give the same bytes" overstates it | Applied (§4): limited to the run that first stored a ply and later hits on it. |
| (note) sharing an opening needs the other key fields equal | Applied (S4): the grading spec, profile, engine and build must also be equal. |

## 15. Amendment by AS1 (review D1): what the tool and the server share

S3 said the tool would become a thin command line over one pipeline. The AS1 review found that
rev. 1 of AS1 shared only the intake and the requests. AS1 rev. 2 shares the whole per-ply path:

| Step | Shared | Where |
| --- | --- | --- |
| PGN intake, normalization, grading from the headers | yes | `parse_game` |
| the per-ply request | yes | `ply_request`, `normalized_ply` |
| analysing and rendering one ply, the engine-failure rule (§5.2), the engine binding | yes | `analyse_ply` |
| the document | yes | `document` (`game_result` with `EngineRun`) |
| storing the ply | **no** | the server: the ply cache (§4); the tool: its three modes (none, digests, `--bundles DIR` with `{ply}.tree` / `{ply}.graph`) |

Storage stays apart on purpose. The tool's files are named by ply for a person to open, its
digest-only mode writes nothing, and its `stored` flag follows R4 and AR1. The server's cache is
keyed by request and always re-loads. Both re-load what they write before calling it stored.
A tool run therefore applies the same engine-failure rule as the server: one restart, then it
stops with `JobFailed`.

## 16. Amendment by CC1 (CC-D, owner Q1–Q3, 2026-10-17): what the cache checks and keeps

[`application-cache-cost-design.md`](application-cache-cost-design.md) changes §4's write and read
paths; the key, the files, their digests, what a miss is and the documents are unchanged.

- **A write** saves, writes, reads both files back and compares their bytes with what it saved,
  checks the request and build, and uses the analysis the pipeline made (`Loaded.checked:
  "written"`). The replay of the written bytes — §4's "re-load" — runs only with
  `--verify-writes` (`checked: "replayed"`). §4's promise that the first document and later ones
  are equal now rests on the round trip of `save` and `load`, which the tests prove for every case
  of the corpus, structurally and on the final document (CC-D §2.2). A failed check is
  `JobFailed("the stored analysis of ply N failed its check: …")`.
- **A read** of bytes the process already loaded or wrote returns the kept pair (an LRU of at most
  `--max-loaded` pairs and `--max-loaded-mb` of estimated memory, keyed by the key and the digests
  of the bytes read under the key's shared lock); other bytes are loaded as §4 says.
- **Test 3** (§10): the second `analyse_game` reads the files through a new cache; the injected
  `load` failure fails the job with `--verify-writes`; without it, bytes read back otherwise do.
- §15's table is unchanged: `tools/explain_game` still re-loads what it writes before calling it
  stored; only the server's cache changed.

