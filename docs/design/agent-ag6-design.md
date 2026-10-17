# Agent — AG6-D design: a game analysed as a whole, and what an agent is shown

Status: **rev. 4 — independent review of rev. 1 (`7b9ed10`) NOT_READY (B1–B6; N1, N2) applied
(§16); re-review of rev. 2 (`034878e`) NOT_READY (B6 partial, B7, B8; note N3) applied (§17); re-review
of rev. 3 (`15ee5aa`) NOT_READY (B7 partial, B9; notes N4, N5) applied (§18)**. Date: 2026-10-17. Base: `main @ 1f9ef15` (AG5 merged; the deployed build). Inputs:
[`agent-mcp-design.md`](agent-mcp-design.md) (AG-D: §3 tools, §3.5 budget, §3.6 handles, §4
propositions, §5 `submit_commentary`), [`agent-ag3-design.md`](agent-ag3-design.md) (AG3-D:
`show_game`, D10 the document only in `structuredContent`),
[`agent-ag4-design.md`](agent-ag4-design.md) (AG4-D: the budget, §3.1 limits),
[`agent-ag5-design.md`](agent-ag5-design.md) (AG5-D: instructions, guides, descriptions),
[`application-result-design.md`](application-result-design.md) (AR-D: `calliope_result_v1`);
the owner's report from the deployment (2026-10-16, §0.1); measurements on this host (§0.2, §0.3).

AG-D built Calliope's tools around **one ply**: an agent opens a game, reads a ply, checks what it
needs and submits that ply's commentary. Asked to analyse a **game**, an agent drives the engine
one ply at a time, reads every ply's full claim graph, and runs out of budget or context before it
writes. This packet adds a game-level path and decides, field by field, what each answer shows the
agent, what it keeps one call away, and what it never shows.

## 0. What happens today

### 0.1 The owner's report (deployment, 2026-10-16)

HIMARI v3 `3120ef9` with Calliope `1f9ef15` (the MCP App on), model `openai/gpt-6-luna`. One
request: analyse a game.

1. The commentary appeared in the chat, not on Calliope's board.
2. The agent used only `ply` and wrote its own reading of it.
3. The context was summarised during the first request.
4. The board showed "이 수는 분석되지 않았습니다" on most plies.
5. Wanted: the board opens, waits while the engine analyses, then shows the whole game with its
   commentary at once.

Causes, read from the code:

- **(1)** The board shows only *accepted* commentary (`show_game`, AG3-D). Nothing in the
  instructions says that a game's commentary goes through `submit_commentary`: the working order is
  for one ply (AG5-D §3), and one submission is one ply with its propositions written out.
- **(2)** `ply` already carries a grade, a best move and a text, so an agent can stop there;
  `facts` and `explore` are advice (AG5-D found the same).
- **(3)** One `ply` answer is 37,000–167,000 characters (§0.3). HIMARI cuts a result at 64 KiB
  (`MAX_RESULT_CHARS`), so 27 of 33 plies arrive cut in the middle of their JSON, at about 18,000
  tokens each; HIMARI summarises at 160,000 tokens (80% of its default 200,000). About nine plies
  fill it.
- **(4)** `open_game` analyses nothing unless `plies` is given, and the budget stops a game
  early (AG4-D §3.1): 16 uncached plies per call and per 15 minutes, 40 searches per 15 minutes,
  and an analysis is admitted only with room for its search bound (`analysis_bound`, 10 from the
  second ply). In §0.2 the binding limit was the searches: the eleventh ply was refused. Only the
  plies analysed are cached; `show_game` shows those and the viewer marks the rest as not analysed.
- **(5)** There is no game-level analysis an agent can start and wait for; `show_game` refuses a
  game with no cached ply (and `calliope_result_v1` needs at least one ply); HIMARI's views cannot
  call tools yet (its phase 1), so a board shown early is not refreshed.

### 0.2 The request again, measured (baseline)

HIMARI `3120ef9` (its driver, server sandbox, one shared Calliope process, the MCP App on),
Calliope `1f9ef15`, `openai/gpt-6-luna`, an empty data directory, the Opera Game (§0.3) and the
request "이 대국을 분석해 줘." with its PGN. 2026-10-17.

| Run | Calls |
| --- | --- |
| 1–2 | `list_resources`; `read_resource` of both guides — the method was found (AG5 works) |
| 2 | `open_game` with `plies` `1-33`: refused, 16 per call at most |
| 3 | `1-16`: plies 1–10 analysed and cached, then ply 11 refused by the search bound (9 searches left, `retry_after_seconds` 872); the answer is the refusal only, so the ten analyses never reach the agent. `17-33`: refused, 17 in one call |
| 4 | `21,25,27,29,31,33`: refused, a range is one ply or two joined by `-` |
| 5 | `28-33`: refused by the search bound |
| 6 | `open_game` without `plies`: the game id |
| 7 | `ply` 33: refused by the search bound |
| 8 | `facts` (status, material, pieces) after plies 29, 31 and 33 |
| 9 | the reply: a commentary of the whole game, about 1,900 characters, in the chat |

9 Runs, 103 s, 80,640 input tokens (49,397 cached), 6,087 output; no summarising (nothing large
was read), no `submit_commentary`, no `show_game`. The reply says the engine's grades and scores
"could not be checked because of the analysis tool's limits" and comments the game from the moves
and the agent's own knowledge ("필리도르 디펜스", "흑의 킹 주변 방어자들을 없애고 …"), which AG-D O3
does not allow. With room in the budget the same request reads plies instead, at about 18,000
tokens each (§0.3): that is the deployment's summarising.

### 0.3 What the answers weigh

Paul Morphy – Duke Karl / Count Isouard, Paris 1858 (the "Opera Game", 33 plies), every ply
analysed through `calliope.agent.Session` with Stockfish 19 (`d12_mpv5_v1`) on this host
(2 cores, run alone). Sizes are characters of the JSON the MCP SDK sends (`indent=2`); one token
is about 3.6 such characters (HIMARI's V3-P62 trials: a 64 KiB `ply` result added 17,900–19,700
input tokens).

| Measure | Value |
| --- | --- |
| Analysis time | 94.6 s for 33 plies; 1.0–4.1 s per ply, mean 2.9 s |
| `ply` answer | median 91,634, max 166,954, sum 3,048,680 characters (≈ 850,000 tokens for the game) |
| Over HIMARI's 64 KiB cut | 27 of 33 plies |
| Share of `analysis` in the answer | 89.2% |
| … `observations` | 36.9% (three per ply; not citable: no proposition kind names one) |
| … `judgements` | 24.7% (alternatives 13.7%; principal variations 11.1%) |
| … `claims` | 18.4%; by status: SUPPORTED 55%, REFUTED 39%, INCONCLUSIVE 6% |
| Repetition | each evidence target and each finding node carries the whole game's `from_root` (up to 29 UCI moves); every move carries its FEN; `scope` is repeated in `effective_scopes` |
| A digest as §3.2 (prototype) | median 2,311, max 8,363, sum 100,250 characters: **1/30** of the full answers |
| An overview as §3.3 (prototype) | 5,045 characters for 33 plies (3,825 without indentation) |
| `show_game` document (`structuredContent`, compact) | 69,698 characters for 33 plies (≈ 2,100 per ply) |

The game also showed a grading fault outside this packet (§11).

## 1. Decisions

| # | Decision |
| --- | --- |
| F1 | **A game is analysed by Calliope, not driven by the agent.** A new tool `analyze_game` starts a background job over a game's plies in the server process and answers its state; asked to, it waits (bounded) without holding any lock (§4). |
| F2 | **What an agent is shown is decided by the server, by rule** (§3): an answer shows what the agent writes from or cites; everything else is one call away by its `ref`; nothing is left for a host to cut. |
| F3 | **`game_overview`** (new): one line per ply and the game's moments, chosen by a deterministic rule, from the cache (§3.3). |
| F4 | **`ply` and `judge_move` answer a digest by default** (§3.2); `view: "full"` gives today's answer unchanged, field for field (§3.4). |
| F5 | **`detail(game, ref)`** (new): one served item exactly as the full answer projects it today (§3.4). |
| F6 | **Propositions by reference** (§5.1): a `judgement` or a `claim` proposition may give its handle and leave out the fields the handle determines; the server fills them, and verifies as today. |
| F7 | **One submission, several subjects** (§5.2): `submit_commentary` takes `items`, each verified and stored on its own. |
| F8 | **`show_game` shows a game at any stage** in a viewer document of its own, `calliope_view_v1`, that holds the game, a `calliope_result_v1` of the analysed plies or none, and each ply's analysis state (§6). `calliope_result_v1` is unchanged. The document is bounded in bytes; what does not fit is left out by a fixed order and named (§6.2). |
| F9 | **The working order for a game** in the instructions, and **`next`** in every answer of the game path: the call that comes next, from the state, in one Korean sentence (§7). |
| F10 | **A job budget beside the call budget, metered apart** (§4.4, §8): a job's searches are charged to the job's meter, a tool's to AG4-D's; the engine port is wrapped per meter. |
| F11 | **Two locks with one order** (§4.3): the *tool lock* (today's) serialises tool calls over the session's state; a new fair *engine lock* serialises the engine. A tool takes tool → engine; the job takes engine only; waiting for a job takes neither. |
| F12 | **Answers in compact JSON** (§3.5): `content` carries the JSON without indentation; `structuredContent` is unchanged. |
| F13 | **Work done is never lost to a refusal** (§8): an `open_game` whose `plies` are refused part-way answers the plies it analysed with the refusal, instead of the refusal alone. |
| F14 | **A hard size bound** (§3.6): a digest is at most 16,000 characters and an overview at most 48,000, as sent. Every field of free length is capped; over the bound, a fixed order of steps moves items behind `detail`, and `not_shown` counts what moved; the last step leaves only fields of bounded size, so the bound always holds; the size is checked again after the steps, and an answer still over is a size error, never a cut answer. |
| F15 | **A resubmission stores nothing twice** (§5.2): an item equal to a record already stored for its subject answers that record's id. |
| F16 | **A stored commentary is bounded** (§5.3): at most 32 propositions and 64 KiB as the board carries it, checked at submission; so one ply's record and commentary always fit on the board. |
| F17 | **A game up to 600 plies in one job, read in ranges of 200** (§3.3, §6.1, §7): `analyze_game` takes the whole game; `game_overview` gives the whole game's moments with the lines of one range; `show_game` the whole game's moves with the records of one range; `next` names the next range. |

## 2. The flow

The request "이 대국을 분석해 줘" with a PGN, as the instructions (§7) order it:

```text
open_game(pgn)                    → game id, moves                        next: analyze_game
analyze_game(game)                → running 0/33, about 95 s               next: analyze_game (wait)
analyze_game(game, wait=240)      → done 33/33                             next: game_overview
game_overview(game)               → 33 lines, moments 12, 18, 19, 25, 29, 31   next: ply 12
ply(game, 12) … ply(game, 31)     → six digests                            next: the next moment, then submit
submit_commentary(items=[…])      → each item accepted or refused          next: show_game
show_game(game)                   → the whole game with its commentary on the board
reply in chat                     → a few lines and a pointer to the board
```

In a host whose views can call tools (HIMARI's next phase), `show_game` comes right after
`analyze_game` starts and the board follows the job itself (§6.3); the flow is otherwise the same.
In a host without views, `show_game`'s text is the summary and nothing else changes.

## 3. What an agent is shown

### 3.1 Rules

| # | Rule |
| --- | --- |
| V1 | **Shown:** what the agent writes from or cites — the judgement, the scores, the best move, the first plies of the played and the best line, the claims it may use, each with what it says and the scope it holds in. |
| V2 | **One call away (`detail`):** what verifies or explains a shown item — full scopes, evidence, relations, checks, findings, full PVs, the alternatives' lines. Every item keeps its `ref`, served as today (AG-D §3.6), whether or not the digest shows it; verification reads the served item, never the digest. |
| V3 | **Named, not shown:** what would mislead if read as a reason — REFUTED claims (by template and `ref`, so an agent can still cite one as `not_the_case`) and the observations (by count). |
| V4 | **Never shown to the model:** what only the server or the viewer uses — bundle digests, grading curve and policy, search ids, the 64-digit game key, `segments` (the viewer's), the viewer's document of `show_game` (`structuredContent` only, AG3-D D10). |
| V5 | **No repetition, in the digest and the overview only:** a position is given once, as its ply and FEN; a line is a string of SAN; a scope is one line of text (`specific_line/engine 0–16 d12`). `view: "full"`, `detail`, `facts` and `explore` keep today's projection: their `from_root` paths and structured lines are inputs to other tools and to verification (review B5). |
| V6 | **The server says what it left out**: every digest has `not_shown` — the kinds and counts behind `detail` and `view: "full"`, and the steps of §3.6 that ran; no answer of the game path relies on a host's cut. |
| V7 | **The words the agent writes come with the data:** grade and label carry their Korean names from `glossary_ko_v1` (`grade_ko`, `label_ko`), so writing needs no resource read. |

### 3.2 The digest of a ply (`ply`, `judge_move`)

| Field | Shown | Source today |
| --- | --- | --- |
| `ply`, `move` (`15.Bxd7+`), `side` | yes | record |
| `grade`, `grade_ko`, `label`, `label_ko`, `status` | yes | record, glossary |
| `fen_before`, `fen_after` | yes | record |
| `evaluation`: played and best score (`+3.64`), `loss`, `best_move` | yes | `evaluation` |
| `judgement` (its `ref`) | yes | `analysis.judgements[0]` |
| `lines.played`, `lines.best`: `ref`, move, score, the first 8 plies as SAN | yes | judgement lines |
| `lines.others`: `ref`, move, score of up to 3 more candidates | yes (no PV) | alternatives |
| `text` (Calliope's own explanation, English) | yes | record |
| `claims`: SUPPORTED and INCONCLUSIVE — `ref`, template, role, status, `says` (its rendered sentence where it has one), `scope` (V5), `attributed` (passed, failed or absent), findings without positions | yes | `analysis.claims` |
| REFUTED claims | named (V3): `{"template", "ref"}` | `analysis.claims` |
| observations | counted (V3) | `analysis.observations` |
| full scopes, evidence, relations, PVs beyond 8 plies, alternatives' PVs | `detail` (V2) | — |
| `bundle`, `curve`, `policy`, `searches`, `segments` | never (V4) | — |
| `cached`, `budget_left` | yes | session |
| `not_shown`, `next` | yes (V6, §7) | new |

Claims are listed in a fixed order: role (`consequence`, `comparison`, `mechanism`, `function`,
then the others by name), then the order of `analysis.claims`. A claim without a rendered sentence
(`rendered: false`, e.g. `better_alternative_v1`) gets `says` from its template's phrase, rendered
for that claim alone through the R3 renderer; if the renderer has no phrase for it, `says` is
absent and the findings remain.

### 3.3 `game_overview(game, plies?)`

From the cache only: it analyses nothing and is not charged. `plies`: the range of the **lines**,
at most 200 (default: plies 1–200, or the whole game when it is shorter). The moments are always
the whole game's (re-review B9).

- The headers (players, event, result) and the warnings the server can give from the stored game
  record, once: the grading warning (the default curve when the headers carry no ratings, derived
  from them). The PGN reader's warnings (several games in one text, a skipped variation …) are
  not stored (`agent_game_v1` holds the moves and headers) and are `open_game`'s answer only
  (re-review N5).
- Per ply: `ply`, `move`, `grade` / `grade_ko`, `label` / `label_ko`, the score after the move,
  `best_move` when another move was best, `loss`; `analysed: false` for a ply the cache does not
  hold.
- **Moments** (review N1). Each analysed ply gets the reasons it meets:

  | Priority | Reason |
  | --- | --- |
  | 1 | grade `blunder` |
  | 2 | grade `mistake` |
  | 3 | label `miss` |
  | 4 | label `brilliant` |
  | 5 | label `great` |
  | 6 | among the three largest losses of at least 150 (expected points the move gave up, in 1/2000, `unit.expected_2000`; ties: the earlier ply) |
  | 7 | a turning point: White's expected points cross 1000 with a change of at least 300 from the ply before |

  A ply is one moment with all its reasons (no duplicates). The moments are ranked by their best
  (lowest) priority, then the larger loss, then the earlier ply; the first 8 are kept and listed in
  ply order. On the Opera Game: 12 (loss 170), 18 (mistake), 19, 25, 31 (brilliant), 29 (mistake,
  §11). They are where a commentary is most likely wanted; the agent may comment on any ply. They
  are chosen over every analysed ply of the game, whatever range the lines show.
- `ranges`: when the game has more than 200 plies, the ranges of 200 there are (`1-200`,
  `201-400`, `401-600`) and the one shown.
- `next` (§7).

### 3.4 `view: "full"` and `detail(game, ref)`

- **`view: "full"`** is today's answer of `ply` / `judge_move`, unchanged in every field (review
  B5); only its `content` loses the indentation (F12). It may exceed a host's cut; the description
  says so and points to `detail`.
- **`detail(game, ref)`** answers the one item a handle names exactly as the full answer projects
  it: a claim (with its scope, effective scopes, evidence, relations, checks, findings); a
  judgement (with its lines and their PVs); a search line; a fact record; an explored line. Each
  carries the `ref` it was asked with. It analyses and charges nothing; a handle of another process
  is refused as today (AG4-D G4). Measured on §0.3 (indented): a claim 625–12,832 characters, a
  judgement 2,198–13,878.

### 3.5 Compact JSON

The SDK sends a returned dict as JSON with `indent=2`. The tools return a `CallToolResult` whose
`content` is the JSON without indentation (−24% on the overview, §0.3) and whose
`structuredContent` is the dict, so both channels carry the same data.

### 3.6 Size bounds (review B6; re-review B6)

The bound is on the `content` as sent (compact JSON): **digest 16,000 characters, overview 48,000**
(both under a 64 KiB cut with room).

**Caps on fields of free length**, applied first, always (a capped string ends with `…` and its
field's entry in `not_shown.capped` gives its full length):

| Field | Cap |
| --- | --- |
| a header value (overview; the view document, §6.2) | 200 characters; the headers are the eight AR-D keeps (`HEADERS`: players, ratings, time control, site, date, result), so their number is fixed |
| the warnings (overview) | at most 5, each 300 characters |
| `text` (digest) | 2,000 characters |
| `says` (digest, per claim) | 300 characters |
| a finding's string field (digest) | 100 characters |

The input itself may be up to 256 KiB (`games.MAX_BYTES`); these caps keep what an answer carries
of it bounded. **The game path takes games of at most 600 plies** (`analyze_game`,
`game_overview`, `show_game`; AS-D's `MAX_PLIES`, the HTTP jobs' limit); a longer game is refused
there with that message and stays usable with `ply`, `judge_move`, `facts` and `explore`.

**Steps when a digest is over**, in order, each only if the digest is still over after the one
before:

1. findings move behind `detail` (each claim keeps a `findings` count);
2. PV prefixes shorten from 8 to 4 plies;
3. INCONCLUSIVE claims are named only (`{"template", "ref"}`);
4. `text` is left out (it is in `view: "full"`);
5. SUPPORTED claims are named only, from the end of the §3.2 order, one at a time, until it fits;
6. named entries are left out, from the end, with their count.

After step 6 the digest holds only fields of bounded size: the ply, move, grade and label with their
Korean names, two FENs, the evaluation, three refs, two lines of 4 SAN plies, up to 3 other
candidates (move and score), `cached`, `budget_left`, `not_shown` (step names and counts) and `next`
— under 3,000 characters by construction. **The overview** after its caps holds the headers
(≤ 8 × 220), the warnings (≤ 5 × 300), at most 200 ply lines of bounded fields (≤ 160 characters
each) and at most 8 moments — under 40,000 by construction. Should these numbers change, the overview has two steps of its
own, in order: drop `best_move` and `loss` of plies that are not moments, then the lines of plies
that are not moments (with their count).

**The final check:** after the caps and the steps, the answer is serialised and measured again. One
still over its bound — which the constructions above exclude, so a fault — is answered as a tool
error `the answer exceeds its size bound (<n> > <bound>); read it with view: "full" or detail`,
never as a cut answer.

`not_shown.steps` lists the steps that ran and `not_shown.counts` what each moved; nothing that a
step moves loses its `ref` before step 6, and after step 6 `view: "full"` still has all. The
judgement, the scores, the best move and the two lines' first 4 plies are never moved. Tests build
digests and overviews that need each cap and each step, with the largest headers an input of
256 KiB allows.

## 4. `analyze_game`

### 4.1 The tool

`analyze_game(game, plies?, wait_seconds = 0, cancel = false)`:

- `game`: an id from `open_game`. `plies`: a range (default: every ply), at most `max_job_plies`
  (600, the game path's limit: the whole game is always one job, re-review B9).
- **Starts** a job when the game holds none; **answers** the game's job when it is the same range;
  **refuses** another range while a job of the game is `queued`, `running` or `waiting`, naming its
  range. A job that ended (`done`, `failed`, `cancelled`) is replaced by a new one (§4.2).
- **Answers** the job's state with `done` / `total`, `cached` (plies that were already in the
  cache), `failed_plies`, the current ply, the mean seconds per analysed ply, the estimate of the
  time left (as AS-D §5.2), `resume_after_seconds` when waiting for budget, and `next`.
- **Waits** when `wait_seconds` > 0 (re-review B8): while the job is `queued`, `running` **or
  `waiting`**, until it ends (`done`, `failed`, `cancelled`) or the time passes, at most 240 s
  (under a host's 300 s call timeout). A wait never returns early because the job is `waiting`.
  With a `progressToken` it sends a progress notification per ply, and one when the job starts
  waiting for budget.
- **A long budget wait is not a loop:** when the job is `waiting` and its `resume_after_seconds`
  is longer than the wait left, the call still waits out its `wait_seconds` and then answers the
  state with `next` (§7) saying to use the plies analysed so far and to tell the user when the rest
  resumes — not to call `analyze_game` again. An `analyze_game` without `wait_seconds` during a
  `waiting` job answers at once, with the same `next`.
- `cancel: true` cancels the game's job after the ply in progress.

### 4.2 States (review B4)

```text
 queued ──► running ──► done                     (every ply analysed, or failed_plies listed)
              │  ▲
              │  └── waiting ◄─┘ (the hourly budget; resumes by itself)
              ├────► failed     (the engine failed twice on one ply)
              └────► cancelled  (cancel, or the process closes)
```

| From | Event | To |
| --- | --- | --- |
| `queued` | the worker takes it (one job runs at a time) | `running` |
| `running` | next ply cached | (counted as `cached`, free) |
| `running` | next ply uncached, budget has room | analysed, charged |
| `running` | next ply uncached, the hourly ply budget is spent | `waiting` with `resume_after_seconds` |
| `waiting` | room comes back | `running` |
| `running` | a ply fails with `AnalysisFailed` not caused by the engine | the ply goes to `failed_plies` with its message; the job goes on |
| `running` | the engine fails on a ply | the engine restarts and the ply runs once more (AS-D §5.2); a second failure → `failed` |
| `running` / `waiting` / `queued` | `cancel` | `cancelled` (after the ply in progress) |
| `running` | last ply | `done` |
| `done` / `failed` / `cancelled` | `analyze_game` again | a new job: finished plies are cache hits; `failed_plies` are tried again |

- The job lives in the process; its results are the ply cache. A process that restarts forgets
  its jobs; the next `analyze_game` starts a new one whose finished plies are cache hits, so nothing
  is analysed twice. No job files are written (AS-D's `result.json` is the HTTP server's).
- An inconclusive ply is analysed, not failed (AR-D §3).

### 4.3 Locks (review B2)

| Lock | Held by | Guards |
| --- | --- | --- |
| **tool lock** (today's `anyio.Lock`) | a tool call, for its whole run except §4.1's wait | the session's state: games, handles, trees, the analyses cache, AG4-D's budget |
| **engine lock** (new, fair: first come, first served) | a tool call or the job, for one analysis or one search, the cache check before it and the cache write after it | `EngineSlot` (start, search, restart), the identity and build read from its port, the cache key's check-and-write |
| **job lock** (new, short) | anyone reading or changing a job's state | the job table |

- **Order:** tool → engine → job. The job worker takes engine (and job), never the tool lock.
  `analyze_game` takes the tool lock to start or read the job, releases it, waits on the job's
  condition with no lock held, and takes it again only to build the answer. So `show_game`, `ply`
  and the others answer during a wait.
- **The worker's state:** it reads the parsed game it was given and writes only the ply cache and
  the job's state. It does not touch handles, trees or the analyses cache; a tool sees the job's
  plies through the cache, as it sees another process's (AG-D A8).
- **The cache under the engine lock:** a ply is checked in the cache, analysed and written under one
  hold of the engine lock, so the job and a tool never analyse the same ply twice; reads without
  the engine lock see whole files only (AS-D §5.1 atomic writes).
- **The wait bound:** the engine lock is fair, and the worker takes it again only after every
  waiter queued before it has had it. A tool waits at most the remainder of one analysis: at most
  `analysis_bound` (10) searches of the profile's time cap (2,000 ms) plus the analysis' own work —
  about 20 s at worst; 4.1 s was the longest ply measured.

### 4.4 Meters (review B3)

- `EngineSlot` holds the raw port. It gives a port **per meter**: `slot.port_for(meter)` answers a
  `MeteredPort(raw, meter)`, made once per raw port and meter and replaced when the engine
  restarts. A tool uses `port_for(budget.meter)` (AG4-D's 40 searches); the job uses
  `port_for(job_meter)`. `_engine_build` and `_search_engine` key on the tool's port, as they key
  on the port today.
- Every search is charged to the meter of the port it went through, before it is asked (as today);
  a failed search stays charged, and a retried ply charges its searches again, to the same meter.
- A cache hit asks no search and charges nothing on either meter.
- The job's budget is counted in plies (§8); its meter counts the job's searches for the answer
  and the tests, with no limit of its own beyond `analysis_bound` per ply.

## 5. `submit_commentary`

### 5.1 Propositions by reference

- `{"id", "kind": "judgement", "judgement": "<j ref>"}`: move, grade, label and best move are taken
  from the judgement.
- `{"id", "kind": "claim", "claim": "<c ref>", "use": "<use>"}`: the scopes are the claim's
  effective scopes. The `use` stays the agent's (AG-D §4.1): it is the agent's statement of what the
  claim is to the move, and it is checked.
- A proposition that gives the fields is verified as today; one that gives some of them has those
  verified and the others filled.
- Why: the copied fields were verified against the served item and so added no check; what the
  copy was meant to make the agent see — the scope — the digest now shows (V1, V5).

### 5.2 Several subjects

`submit_commentary(game, agent, items=[{ply | position+move, propositions, sentences}, …])`, at most
16 items. Each item is verified and stored on its own, in order: one refused item stores nothing of
itself and changes nothing of another; the answer lists each item's outcome. Proposition ids are
per item. The single-subject form stays.

- **Outcomes per item:** `accepted` (its id), `duplicate` (the id of the equal record already
  stored, nothing written), `refused` (every violation) or `not_stored` (verified, but the write
  failed: the store's message). The tool answers normally whenever it got to the items; a call is
  an error only for what precedes them (the game, the item count).
- **No atomicity across items** (re-review N3): the store writes one file per item (AG-D §9), so a
  write that fails part-way leaves the items before it stored and says so per item.
- **Retrying is safe (F15):** an item is `duplicate` when a record of the same subject has the same
  key: `agent`, `language`, the sentences, the analysis bundle it was accepted against, and its
  propositions (as stored, after §5.1's filling) **without their handles** — every `sources[*].ref`
  and every field that holds a handle is left out, and the stable `source` and `address` of each
  cited item stay (re-review N4). The record format (`ai_commentary_v1`) is unchanged: the key is
  computed from the stored fields.
- **What it guarantees:** the same call sent again — in the same process, or after a restart or an
  eviction with new handles of the same items — answers `duplicate` for what was stored. Proposition
  ids are the agent's labels and are part of the key; a resubmission that renames them, or changes
  any sentence, is a new commentary (AG-D O7 keeps every accepted one, the newest shown).

### 5.3 The size of one commentary (re-review B7)

- At most **32 propositions** per item (a nested `after_reply` counts as one), and a proposition id
  of at most 32 characters; the sentences stay as S1 (1–12, 300 characters each).
- The item's commentary **as the board carries it** — its `ai_commentary` with `display_v1`
  (AG3-D), compact JSON in UTF-8 — is at most **64 KiB**. It is measured after verification and
  before the write; an item over it is `refused` with the rule `size`, the size and the bound.
- The eleven commentaries accepted in the AG5 and V3-P62 trials had 1–3 propositions and 2,732–4,780
  bytes each as stored.
- So one ply's commentary always fits on the board (§6.2). A record stored before AG6 that is over
  the bound is shown as omitted (§6.2) and stays readable whole with `commentary`.

## 6. `show_game`

### 6.1 The viewer's document (review B1)

`calliope_result_v1` stays as it is (at least one ply; every ply a full record). `show_game`'s
`structuredContent` becomes a document of its own:

```text
{"schema": "calliope_view_v1",
 "game": {"start_fen", "moves": [{"san", "uci"}, …], "headers"},      # as calliope_result_v1's game
 "result": <calliope_result_v1 of the analysed plies, with commentary> | null,
 "plies": [{"ply", "state": "analysed" | "pending" | "failed" | "none"}, …],   # every ply of the game
 "job": {"state", "done", "total", "resume_after_seconds"?} | null}
```

- `result` is null when no ply is analysed; otherwise it is today's combined document (AG3-D) over
  the analysed plies of the asked range. `state` is `pending` for a ply in the range of a job that
  has not ended, `failed` for one in its `failed_plies`, `none` otherwise.
- **Schema:** `calliope_view_v1` gets its JSON Schema beside `calliope_result_v1`'s; it references
  that schema for `result`.
- **The viewer** accepts a `calliope_result_v1` (a file, the HTTP server) as today and a
  `calliope_view_v1` (the MCP App). It shows the moves from `game`, a ply's analysis from
  `result` when there, "분석 중" for `pending`, "분석하지 못했습니다" for `failed`, and keeps
  "이 수는 분석되지 않았습니다" for `none`; with a job, a progress line.
- **Ranges (re-review B9):** `game`, `plies` (the states) and `job` always cover the whole game, up
  to 600 plies; `result` covers the asked range, at most 200 plies (`SHOW_LIMIT`; default: plies
  1–200, or the whole game when it is shorter). The model's text names the other ranges. The
  document's size is bounded in bytes as well (§6.2).
- The text for the model (`content`) adds the progress and the plies with commentary; with no ply
  analysed it says so and names `analyze_game`, instead of an error.
- Tests: zero, some and all plies analysed, a running job and a failed ply, each through the viewer.

### 6.2 The document's size (re-review B7)

One ply's accepted commentary may hold 12 sentences of 300 characters (S1) with its propositions
and `display_v1`: tens of kilobytes. Two hundred of them do not fit in a host's view payload
(HIMARI: 1 MiB of UTF-8 JSON). So:

- **The bound:** the serialised `structuredContent` (compact JSON, UTF-8 bytes) is at most
  **768 KiB**, leaving room for `content` and the envelope.
- **Always in the document:** `game` (start, moves, headers), every ply's `state` and `job`. With
  at most 600 plies (§3.6) and header values capped at 200 characters — in `game` and in
  `result.game`, which is built for each call and never stored — this part is under 64 KiB, so it
  always fits.
- **Then, in order, while it fits:** the ply records of the asked range in ply order (≈ 2,000 bytes
  each, at most 5,020 measured, §0.3), then each ply's commentary in this order: the moments of the
  game's overview (§3.3), then the other plies in ply order.
- **One ply always fits** (re-review B7): the always-in part is under 64 KiB; a ply's record over
  64 KiB is left out as `record` (none comes near: the catalogue bounds a ply's claims); a
  commentary is at most 64 KiB (§5.3) and an older one over it is left out as `commentary`. So
  `show_game(plies="n")` carries ply n's record and commentary whenever they are within those
  bounds, and names them as omitted otherwise — under 192 KiB in every case.
- **What does not fit is left out whole** — a ply's commentary, or a ply's record with its
  commentary — never cut inside. The document names it: `omitted: {"commentary": [plies],
  "records": [plies]}`, and each such ply's entry in `plies` says `omitted: "commentary"` or
  `"record"`. The viewer shows such a ply as "이 수의 해설은 판에 다 담지 못했습니다. show_game을
  이 수의 범위로 다시 열어 보세요".
- **The model's text** names the omitted plies and the range to ask for (`show_game(plies=…)`), so
  the commentary of any ply within the bounds of §5.3 can be shown by asking for a smaller range;
  the moves of the whole game stay on the board in every range.
- **The final check:** the document is measured after it is built; one over the bound (a fault) is a
  tool error naming the size, never a cut document.
- Tests: 200 plies each with a commentary of the largest size §5.3 allows, with Korean text; a
  document at the bound ± one ply; one ply with a 64 KiB commentary; an older record over 64 KiB;
  the omitted lists and the viewer's message.

### 6.3 A board that follows the job

The viewer already re-reads `show_game` through the host (`tools/call`, AG3-D §4) when the user
asks it to. While the document's `job` is `queued` or `running`, it re-reads every 5 s; while it is
`waiting`, every `max(5, min(60, resume_after_seconds))` s (re-review B8); after the job ends, once
more. In a host that refuses a view's calls (HIMARI today: -32601), it stops after the first
refusal and says that the board shows the moment it was opened; the agent's final `show_game`
brings the whole game.

## 7. The working order and `next` (review N2)

The instructions (AG5-D §3) gain the order for a game, before the order for one ply:

```text
대국을 분석하는 순서:
1. open_game으로 게임을 열고 analyze_game으로 모든 수의 분석을 시작합니다. 끝날 때까지 analyze_game(wait_seconds)으로 기다립니다.
2. game_overview로 흐름과 중요한 장면(moments)을 봅니다.
3. 장면마다 ply로 요약을 읽고, 필요한 "왜"는 detail·judge_move·explore로 확인합니다. 모든 장면을 읽은 뒤에 씁니다.
4. 해설은 submit_commentary(items)로 한 번에 저장해야 판에 나타납니다. 저장한 뒤 show_game으로 판을 보여 주고, 채팅에는 짧은 요약만 씁니다.
분석이 거부되거나 끝나지 않은 수는 기억으로 해설하지 말고, 기다리거나 분석되지 않았다고 말합니다.
200수가 넘는 대국은 game_overview와 show_game을 200수 범위(plies)로 나누어 봅니다. 중요한 장면은 대국 전체에서 골라집니다.
```

`next` is computed from the state the session holds:

| After | `next` |
| --- | --- |
| `open_game`, the game has no job | `analyze_game` |
| `analyze_game`, the job `queued` / `running` | `analyze_game` with `wait_seconds` |
| `analyze_game`, the job `waiting`, `resume_after_seconds` ≤ 240 | `analyze_game` with `wait_seconds` |
| `analyze_game`, the job `waiting`, `resume_after_seconds` > 240 | `game_overview` of the plies analysed so far; tell the user when the rest resumes (no `analyze_game` until then) |
| `analyze_game`, `done` | `game_overview` |
| `analyze_game`, `failed` / `cancelled` | `analyze_game` again (finished plies are kept) |
| `game_overview` | `ply` of the first moment not yet read in this session (the moments are the whole game's, in any range) |
| a digest of a moment, moments still unread | `ply` of the next unread moment |
| a digest, every moment read (or the ply is not a moment of an overview served) | `submit_commentary` with `items` for the plies read |
| `submit_commentary`, some items `refused` | fix those items and submit them again |
| `submit_commentary`, some items `not_stored` | submit the same items again (F15: nothing is stored twice) |
| `submit_commentary`, every item `accepted` or `duplicate` | `show_game` of the range holding the first moment; with more than 200 plies, the text names the ranges that hold the others |

"Read" means a digest of that ply was served in this session. It is advice; no call is refused for
not following it.

## 8. Budget

| Limit | Default (owner) | Applies to |
| --- | --- | --- |
| `max_job_plies` | 600 | plies of one job (= the game path's limit, §3.6) |
| `max_jobs` | 1 running, 4 queued | per process |
| `max_job_plies_per_window` | 400 per hour | plies analysed by jobs (cache hits free) |
| AG4-D §3.1 limits | unchanged | `ply`, `judge_move`, `explore`, `open_game`'s `plies` |

- A job's plies are charged when analysed, not when queued, on the job's own window; its searches go
  to the job's meter (§4.4), so a job leaves the agent its 40 searches for `judge_move` and
  `explore`.
- A job that reaches the hourly limit waits (§4.2), and does not fail. A job refused at its start
  (too many plies, the queue full) names the limit, what is left and `retry_after_seconds`, as
  AG4-D does. Each value is a server option (`--max-job-plies` …).
- 400 plies an hour is about 19 minutes of engine time on this host (2.9 s a ply, §0.3). A game of
  more than 400 uncached plies is one job that waits (§4.2) for the rest; a 600-ply game takes
  about 29 minutes of engine time over two windows.
- **F13.** `open_game` with `plies` admits its plies one by one, as today; when one is refused after
  others were analysed, the answer is the moves with the analysed plies' summaries, `refused`
  (the ply and the message, with `retry_after_seconds`) and `next` (`analyze_game`), instead of an
  error. A refusal of the first ply stays an error.

## 9. Hosts

- Every host: §2 works with tools alone; every answer of the game path is bounded (§3.6).
- **HIMARI today** (views that cannot call tools, no progress display): the flow of §2 with the board
  at the end. HIMARI's next view phase (views calling their own server's app-visible tools, a
  progress display) is HIMARI's design; this packet needs nothing from it.

## 10. Considered and left out

- **Reusing `calliope.server.jobs`.** Its jobs are files with an environment check and a
  `result.json` for the HTTP API; the agent needs only the cache entries and a progress count.
- **A second engine for the job.** On a 2-core host it halves both; one fair lock keeps a tool's
  wait to one analysis.
- **Unanalysed plies inside `calliope_result_v1`.** Its plies are full records, and files and the
  HTTP server rely on that; the viewer's document carries the state instead (§6.1).
- **A game-level commentary (a summary of the game) on the board.** It needs a subject that is not a
  ply in the store and in `calliope_result_v1` and a place in the viewer; a later packet. Until then
  the summary is the chat's (§7 step 4).
- **V5 for `facts`, `explore` and `view: "full"`.** Their paths are inputs; a compact form for them
  needs its own contract and measurements.
- **Choosing moments with the model.** The server's rule is reproducible and cheap; the agent still
  chooses what to write about.
- **Server-built comparison claims** ("what the best move does that the played move does not"). A
  reasoning packet; `best_stops_reply_v1` (EV-D) covers exchanges only, and the digest shows its
  status when present.

## 11. A finding outside this packet

The Opera Game's 15.Bxd7+ (mate in three: 15...Nxd7 16.Qb8+ Nxb8 17.Rd8#) is graded **mistake**,
loss 361, best 15.Bxf6 (+8.60); the played line is scored +3.64 with the PV 15...Nxd7 16.Qb7 —
the survey at depth 12 (MultiPV 5) did not find 16.Qb8+ in the fifth line. 16.Qb8+ itself is graded
best and brilliant. To be taken up in a reasoning or engine-profile packet; reported to the owner.

## 12. Acceptance

The request of §0.2 again, same host, model and game, after AG6:

- every ply analysed (no "분석되지 않았습니다" at the end);
- no summarising of the context during the turn;
- every moment of the overview has an accepted commentary, shown by the final `show_game`;
- the calls, Runs and tokens measured as in §0.2 and reported beside them.

Experimental: a model may still skip steps; the numbers are what the packet reports.

## 13. Tests (Calliope)

- **Digest:** for a stored analysis, the digest has exactly the fields of §3.2 in the claim order
  of §3.2; REFUTED claims are named with their refs; every `ref` in it resolves; a proposition built
  from a digest's refs verifies as one built from the full answer.
- **Bounds (§3.6):** constructed analyses that need each step 1–6 in turn; the result is under the
  bound, `not_shown` names the steps and counts, the never-moved fields are there; the overview's
  two steps likewise; the Opera Game needs none.
- **Full and `detail`:** `view: "full"` equals today's answer field for field (a golden test from
  `1f9ef15`); `detail` of each kind of handle equals that item in the full answer; a foreign handle
  is refused.
- **Waiting (re-review B8):** a wait across `running` → `waiting` → `running` returns only at the end
  or at `wait_seconds`; a wait during a long `waiting` returns at `wait_seconds` with the
  `game_overview` `next`; a call without a wait during `waiting` answers at once; the viewer's
  interval during `waiting`.
- **`analyze_game` states (§4.2):** every row of the table, with a fake engine and clock — including
  an engine failure retried once then `failed`, an `AnalysisFailed` ply in `failed_plies` with the
  job going on, the hourly limit → `waiting` → `running`, `cancel` from each state, a new job after
  `failed` whose finished plies are cache hits and whose failed plies run again, and a restarted
  process finishing from the cache.
- **Locks (§4.3):** during an `analyze_game` wait, `show_game` and `ply` (cached) answer; a
  `judge_move` during a job waits for at most the analysis in progress (the fake engine's), and
  three tool calls in a row are not overtaken by the worker; the job and a tool asking the same
  uncached ply analyse it once.
- **Meters (§4.4):** a job's searches move the job meter and not AG4-D's; a tool's the reverse;
  after an engine restart both still hold; a cache hit moves neither; a retried ply's searches are
  charged again to the job.
- **Overview:** lines for analysed and unanalysed plies; the moment rules on constructed games —
  more than 8 candidates, ties by loss and by ply, one ply with several reasons, the turning point;
  a 450-ply game: the moments the same in every range, `ranges` listed, lines of the asked range
  only; the grading warning derived from the headers.
- **Long games:** `analyze_game` of a 450-ply game is one job that waits after 400 and ends `done`;
  `show_game` of each range carries that range's records and the whole game's moves and states;
  a 601-ply game is refused on the game path and served by `ply`.
- **`next`:** each row of §7's table; a digest of a moment with moments unread never says
  `submit_commentary`.
- **Submission:** by-reference propositions verify and fill; a wrong `use` is refused; `items`
  stores the accepted, reports the refused, and a refused item leaves the others' stored records
  as they would be alone; ids per item; a store that fails on the third of five items answers
  `accepted`, `accepted`, `not_stored`, then the last two as their own outcomes; resending the call
  answers the first two `duplicate` and stores the rest once; the same call after a process
  restart, with new handles, answers `duplicate`; renamed proposition ids store a new record;
  an item of 33 propositions, or over 64 KiB as the board carries it, is refused with `size`.
- **`show_game` and the viewer:** `calliope_view_v1` validates against its schema with `result`
  null, partial and full; the viewer renders each state; a file `calliope_result_v1` still loads;
  the size cases of §6.2.
- **Budget:** each limit of §8; F13's partial answer.
- **Build:** a new `TOOLS_VERSION` and `GUIDANCE_VERSION`; the pin tests.

## 14. Packets

1. **AG6a** — what an agent is shown: the digest, `view: "full"`, `detail`, the bounds, compact JSON,
   propositions by reference, `items` with F15 and F16, F13, the instructions and `next` for the one-ply path. It
   works in today's hosts and removes the 64 KiB cut.
2. **AG6b** — the game path: `analyze_game` with its states, the locks and the meters, the job
   budget, `game_overview`, `calliope_view_v1` with its size bound and the viewer, the game order in the instructions;
   the trial of §12.

## 15. Owner questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | `ply` answers the digest by default, the full graph with `view: "full"` (§3.2, §3.4) | Yes |
| Q2 | REFUTED claims named, not shown, in the digest (V3) | Yes: 39% of the claim text, and none is a reason |
| Q3 | Propositions by reference for `judgement` and `claim` (§5.1) | Yes |
| Q4 | Job budget values of §8 (600 plies a job, 1 running and 4 queued, 400 plies an hour) | Yes; ≈ 19 min of engine time an hour on this host |
| Q7 | A stored commentary of at most 32 propositions and 64 KiB on the board (§5.3) | Yes: the eleven commentaries accepted in the AG5 and V3-P62 trials had 1–3 propositions and at most 4,780 bytes each |
| Q5 | Moment rules of §3.3 (priorities, at most 8) | Yes |
| Q6 | A game-level commentary on the board in a later packet (§10) | Yes |

## 16. Review dispositions — rev. 1 (`7b9ed10`), independent review: NOT_READY

| # | Finding | Disposition |
| --- | --- | --- |
| B1 | `show_game` with no analysed ply and per-ply states conflict with `calliope_result_v1` (at least one ply, full records, `analysis` already a field; `game_result` raises "no analysed ply") | Applied: a viewer document `calliope_view_v1` holding the game, the result or null, the states and the job; `calliope_result_v1` unchanged; its schema, the viewer's two inputs and their tests (§6.1, F8, §10). |
| B2 | One tool lock: a waiting `analyze_game` blocks the other tools; a worker outside it races the session and `EngineSlot`; "at most one ply" unproven | Applied: tool, engine and job locks with one order; the wait holds none; the worker touches only the cache and the job; the cache check-and-write under the engine lock; a fair engine lock and a wait bound from `analysis_bound` and the time cap (§4.3, F11). |
| B3 | The job budget is not wired: every search goes through one `MeteredPort` on AG4-D's meter | Applied: a port per meter from the slot, kept across restarts; charges per port; cache hits free; retries charged again (§4.4, F10). |
| B4 | No retry or resume for a failed job; budget exhaustion mid-job undefined | Applied: the state machine with `waiting` (budget), `failed` (engine twice), `cancelled`, `failed_plies`, and a new job after an end reusing the cache (§4.2). |
| B5 | V5 everywhere breaks `view: "full"`, whose paths and lines are inputs and evidence | Applied: V5 for the digest and overview only; `view: "full"`, `detail`, `facts`, `explore` keep today's projection; a golden test (§3.1, §3.4, §10). |
| B6 | No hard bound on the digest | Applied: 16,000 / 48,000 characters as sent and a fixed order of steps, with `not_shown` steps and counts and the fields never moved (§3.6, F14). |
| N1 | Moments beyond 8: priority, ties, duplicates | Applied: a priority table, one moment per ply, ranking and ties (§3.3). |
| N2 | `next` after one digest invites an early submission | Applied: `next` goes to the next unread moment, then to one `submit_commentary(items)`; the instructions say to write after reading every moment (§7). |

## 17. Review dispositions — rev. 2 (`034878e`), re-review: NOT_READY

| # | Finding | Disposition |
| --- | --- | --- |
| B6 (partial) | No end condition after the last step; the overview's headers (an input up to 256 KiB) are not reduced | Applied: caps on every field of free length (the eight header values 200 each, warnings 5 × 300, `text`, `says`, finding strings) and 600 plies on the game path; the last step leaves only bounded fields, with the bound shown by construction (digest < 3,000, overview < 40,000); the answer is measured again and one still over is a size error, never cut (§3.6, F14). |
| B7 | 200 plies with the largest commentary S1 allows exceed a 1 MiB view payload | Applied: a byte bound of 768 KiB on `structuredContent`; the game, states and job always in; then records, then commentary (moments first) while they fit; what does not fit left out whole and named, in the document, the viewer and the model's text, with the range to ask for; a final check (§6.2, F8). |
| B8 | A `waiting` job ends the wait at once, inviting a loop of `analyze_game` calls | Applied: a wait holds through `waiting`; a budget wait longer than the call's turns `next` to the analysed plies and the user, not to `analyze_game`; the viewer polls `waiting` at up to 60 s (§4.1, §6.3, §7). |
| N3 | A part-way write failure in `items` and a retry may store duplicates | Applied: per-item outcomes with `not_stored`; no atomicity across items, said so; an equal record answers `duplicate` and is not written again (§5.2, F15). |

## 18. Review dispositions — rev. 3 (`15ee5aa`), re-review: NOT_READY

| # | Finding | Disposition |
| --- | --- | --- |
| B7 (partial) | One commentary may exceed the view bound: propositions have no count or size limit, so a range of one ply may not show it | Applied: at most 32 propositions and 64 KiB as the board carries it, refused with `size` at submission; a ply record over 64 KiB omitted; so a one-ply range always fits (< 192 KiB); an older oversize record omitted and readable with `commentary` (§5.3, §6.2, F16). |
| B9 | 201–600-ply games: the default flow is refused at `analyze_game` (200), and splitting is undefined | Applied: one job for the whole game (`max_job_plies` 600, waiting past the hourly 400); the overview's moments always the whole game's, its lines and `show_game`'s records in ranges of 200 with `ranges` and `next`; the instructions say so (§3.3, §4.1, §6.1, §7, §8, F17). |
| N4 | Duplicate detection compares stored propositions that hold process-local handles | Applied: the key leaves out every handle and keeps the stable source and address; its guarantee stated (same call, any process); renamed ids or changed sentences are new (§5.2). |
| N5 | The overview's PGN warnings are not in `agent_game_v1` | Applied: the overview gives only the warning derivable from the stored record (the grading curve); the reader's warnings stay `open_game`'s (§3.3). |
