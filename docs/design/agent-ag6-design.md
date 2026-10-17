# Agent — AG6-D design: a game analysed as a whole, and what an agent is shown

Status: **rev. 1 — for independent review**. Date: 2026-10-17. Base: `main @ 1f9ef15` (AG5
merged; the deployed build). Inputs: [`agent-mcp-design.md`](agent-mcp-design.md) (AG-D: §3 tools,
§3.5 budget, §3.6 handles, §4 propositions, §5 `submit_commentary`), [`agent-ag3-design.md`](agent-ag3-design.md)
(AG3-D: `show_game`, D10 the document only in `structuredContent`),
[`agent-ag4-design.md`](agent-ag4-design.md) (AG4-D: the budget, §3.1 limits),
[`agent-ag5-design.md`](agent-ag5-design.md) (AG5-D: instructions, guides, descriptions);
the owner's report from the deployment (2026-10-16, §0.1); measurements on this host (§0.2, §0.3).

AG-D built Calliope's tools around **one ply**: an agent opens a game, reads a ply, checks what it
needs and submits that ply's commentary. Asked to analyse a **game**, an agent drives the engine
one ply at a time, reads every ply's full claim graph, and runs out of context before it writes.
This packet adds a game-level path and decides, field by field, what each answer shows the agent,
what it keeps one call away, and what it never shows.

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
  tokens each; HIMARI summarises at 160,000 tokens (80% of its default 200,000). About nine plies fill it.
- **(4)** `open_game` analyses nothing unless `plies` is given, and the budget stops a game
  early (AG4-D §3.1): 16 uncached plies per call and per 15 minutes, 40 searches per 15 minutes,
  and an analysis is admitted only with room for its search bound (10). In §0.2 the binding limit
  was the searches: the eleventh ply was refused. Only the plies analysed are cached; `show_game`
  shows those and the viewer marks the rest as not analysed.
- **(5)** There is no game-level analysis an agent can start and wait for; `show_game` refuses a
  game with no cached ply; HIMARI's views cannot call tools yet (its phase 1), so a board shown
  early is not refreshed.

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
| F1 | **A game is analysed by Calliope, not driven by the agent.** A new tool `analyze_game` starts a background analysis of a game's plies in the server process and answers with its progress; called again it waits (bounded) and answers the progress or the end (§4). |
| F2 | **What an agent is shown is decided by the server, by rule** (§3): an answer shows what the agent writes from or cites; everything else is one call away by its `ref`; nothing is left for a host to cut. |
| F3 | **`game_overview`** (new): one line per ply and the game's moments chosen by rule, from the cache (§3.3). |
| F4 | **`ply` and `judge_move` answer a digest by default** (§3.2); `view: "full"` gives today's answer. |
| F5 | **`detail(game, ref)`** (new): the full projection of one served item — a claim's scopes, evidence, relations, checks and findings; a judgement's lines with their full PVs; a search line (§3.4). |
| F6 | **Propositions by reference** (§5.1): a `judgement` or a `claim` proposition may give its handle and leave out the fields the handle determines; the server fills them, and verifies as today. |
| F7 | **One submission, several subjects** (§5.2): `submit_commentary` takes `items`, each a subject with its propositions and sentences, each verified and stored on its own. |
| F8 | **`show_game` shows a game at any stage** (§6): with no ply analysed, while `analyze_game` runs (progress per ply) and when done; the whole game in one document up to 200 plies. |
| F9 | **The working order for a game** in the instructions, and **`next`** in every answer of the game path: the call that comes next, in one Korean sentence (§7). |
| F10 | **A job budget beside the call budget** (§8): `analyze_game` is charged per job, not per ply; the per-call limits of AG4-D stay for `ply`, `judge_move` and `explore`. |
| F11 | **One engine per process, shared under a lock** (§4.3): the background analysis takes it per ply; a tool call that needs it waits at most one ply. |
| F12 | **Answers in compact JSON** (§3.5): `content` carries the JSON without indentation; `structuredContent` is unchanged. |
| F13 | **Work done is never lost to a refusal** (§8): an `open_game` whose `plies` are refused part-way answers the plies it analysed with the refusal, instead of the refusal alone. |

## 2. The flow

The request "이 대국을 분석해 줘" with a PGN, as the instructions (§7) order it:

```text
open_game(pgn)                    → game id, moves                       next: analyze_game
analyze_game(game)                → running 0/33, about 95 s              next: analyze_game (waits)
analyze_game(game, wait=240)      → done 33/33                            next: game_overview
game_overview(game)               → 33 lines, moments 12, 18, 19, 25, 29, 31  next: ply per moment
ply(game, 29)  …                  → digests (2–8k characters each)        next: detail / explore / submit
submit_commentary(items=[…])      → each item accepted or refused         next: show_game
show_game(game)                   → the whole game with its commentary on the board
reply in chat                     → a few lines and a pointer to the board
```

In a host whose views can call tools (HIMARI's next phase), `show_game` comes right after
`analyze_game` starts and the board follows the progress itself (§6.2); the flow is otherwise the
same. In a host without views, `show_game`'s text is the summary and nothing else changes.

## 3. What an agent is shown

### 3.1 Rules

| # | Rule |
| --- | --- |
| V1 | **Shown:** what the agent writes from or cites — the judgement, the scores, the best move, the first plies of the played and the best line, the claims it may use, each with what it says and the scope it holds in. |
| V2 | **One call away (`detail`):** what verifies or explains a shown item — full scopes, evidence, relations, checks, findings, full PVs, the alternatives' lines. Every item keeps its `ref`, served as today (AG-D §3.6), whether or not the digest shows it; verification reads the served item, never the digest. |
| V3 | **Named, not shown:** what would mislead if read as a reason — REFUTED claims (by template and `ref`, so an agent can still cite one as `not_the_case`) and the observations (by count). |
| V4 | **Never shown to the model:** what only the server or the viewer uses — bundle digests, grading curve and policy, search ids, the 64-digit game key, `segments` (the viewer's), the full `calliope_result_v1` of `show_game` (already `structuredContent` only, AG3-D D10). |
| V5 | **No repetition**, in every answer of the agent's tools (`facts` and `explore` too): a position is given once, as its ply and FEN; a line is a string of SAN; a scope is one line of text (`specific_line/engine 0–16 d12`); no `from_root` beyond the line itself. |
| V6 | **The server says what it left out**: every digest has `not_shown` with what is behind `detail` and `view: "full"`; no answer of the game path relies on a host's cut. |
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

A claim without a rendered sentence (`rendered: false`, e.g. `better_alternative_v1`) gets `says`
from its template's phrase, rendered for that claim alone through the R3 renderer; if the renderer
has no phrase for it, `says` is absent and the findings remain.

### 3.3 `game_overview(game)`

From the cache only: it analyses nothing and is not charged.

- The headers (players, event, result) and the PGN's warnings, once.
- Per ply: `ply`, `move`, `grade` / `grade_ko`, `label` / `label_ko`, the score after the move,
  `best_move` when another move was best, `loss`; `analysed: false` for a ply the cache does not
  hold.
- **Moments**, at most 8, in ply order, each with its reasons: a grade of `mistake` or `blunder`;
  a label of `brilliant`, `great` or `miss`; the three largest losses of at least 150 (expected
  points the move gave up, in 1/2000, `unit.expected_2000`); a turning point, where White's
  expected points cross 1000 with a change of at least 300. They are where a commentary is most
  likely wanted; the agent may comment on any ply. On the Opera Game: 12 (loss 170), 18 (mistake),
  19, 25, 31 (brilliant), 29 (mistake, §11).
- `next`: read each moment with `ply`.

### 3.4 `detail(game, ref)`

The served item a handle names, in today's projection (AG-D §3, DF-D §4.3) with V5 applied: a
claim with its full scopes, evidence, relations, checks and findings; a judgement with all its
lines and their full PVs; a search line; a fact record; an explored line. It analyses and charges
nothing; a handle of another process is refused as today (AG4-D G4).

### 3.5 Compact JSON

The SDK sends a returned dict as JSON with `indent=2`. The game path's tools return a
`CallToolResult` whose `content` is the JSON without indentation (−24% on the overview, §0.3) and
whose `structuredContent` is the dict, so both channels carry the same data.

## 4. `analyze_game`

### 4.1 The tool

`analyze_game(game, plies?, wait_seconds = 0)`:

- `game`: an id from `open_game`. `plies`: a range (default: every ply).
- **Starts** a job when none holds the game and range: its plies are analysed in order through the
  per-ply path `ply` uses (`normalized_ply`, `PlyCache.key`, `analyse_ply`, `PlyCache.put`), so
  every result is a cache entry like any other.
- **Answers** the job's state — `queued`, `running`, `done`, `failed` — with `done` / `total`,
  `cached` (plies that were already in the cache), the current ply, the mean seconds per analysed
  ply and the estimate of the time left (as AS-D §5.2), and `next`.
- **Waits** when `wait_seconds` > 0: until the job ends or the time passes, at most 240 s (under a
  host's 300 s call timeout), with a progress notification per ply when the request carries a
  `progressToken`.
- A second call for the same game and range answers the same job; a different range of a running
  game is refused with the running job's range.

### 4.2 State and restarts

The job lives in the process; its results are the ply cache. A process that restarts forgets the
job; the next `analyze_game` starts a new one whose finished plies are cache hits, so nothing is
analysed twice. No job files are written (AS-D's `result.json` is the HTTP server's).

### 4.3 The engine

The process keeps one engine (`EngineSlot`). It gains a lock: the job takes it for one ply and
releases it; `ply`, `judge_move` and `explore` take it for their analysis or search. A tool call
during a job waits at most one ply (≤ 4.1 s measured). An engine failure is handled as AS-D §5.2
(restart, one retry of the ply, then the job fails with the message).

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
16 items. Each item is verified and stored on its own; the answer lists each item's outcome (its
id, or every violation). Proposition ids are per item. The single-subject form stays.

## 6. `show_game`

### 6.1 Any stage

- A game with no analysed ply is shown (the board and the moves), not refused.
- Each ply carries `analysis`: `analysed`, `pending` (in the running job's range) or `none`; the
  document carries the job's progress when one runs. The viewer shows a pending ply as
  "분석 중" and keeps "이 수는 분석되지 않았습니다" for `none`.
- `SHOW_LIMIT` becomes 200 plies (≈ 420,000 characters, under HIMARI's 1 MiB view payload).
- The text for the model (`content`) adds the progress and the plies with commentary.

### 6.2 A board that follows the job

The viewer already re-reads `show_game` through the host (`tools/call`, AG3-D §4) when the user
asks it to. While the document
says a job runs, it re-reads every 5 s until the job ends, then once more. In a host that refuses
a view's calls (HIMARI today: -32601), it stays on the document it got and says so; the agent's
final `show_game` brings the whole game.

## 7. The working order and `next`

The instructions (AG5-D §3) gain the order for a game, before the order for one ply:

```text
대국을 분석하는 순서:
1. open_game으로 게임을 열고 analyze_game으로 모든 수의 분석을 시작합니다. 끝날 때까지 analyze_game(wait_seconds)으로 기다립니다.
2. game_overview로 흐름과 중요한 장면(moments)을 봅니다.
3. 장면마다 ply로 요약을 읽고, 필요한 "왜"는 detail·judge_move·explore로 확인합니다.
4. 해설은 submit_commentary(items)로 저장해야 판에 나타납니다. 저장한 뒤 show_game으로 판을 보여 주고, 채팅에는 짧은 요약만 씁니다.
분석이 거부되거나 끝나지 않은 수는 기억으로 해설하지 말고, 기다리거나 분석되지 않았다고 말합니다.
```

`next` is computed from the state: after `open_game` (no job) → `analyze_game`; a running job →
`analyze_game` with `wait_seconds`; a finished job → `game_overview`; the overview → `ply` of the
first moment; a digest → `submit_commentary` (and `detail` when a used claim is INCONCLUSIVE); an
accepted submission → `show_game`. It is advice; no call is refused for not following it.

## 8. Budget

| Limit | Default (owner) | Applies to |
| --- | --- | --- |
| `max_job_plies` | 200 | plies of one job (= `SHOW_LIMIT`) |
| `max_jobs` | 1 running, 4 queued | per process |
| `max_job_plies_per_window` | 400 per hour | plies analysed by jobs (cache hits free) |
| AG4-D §3.1 limits | unchanged | `ply`, `judge_move`, `explore`, `open_game`'s `plies` |

- A job's plies are charged when analysed, not when queued, and are not charged to the AG4-D meter:
  its searches are the job's, so a job leaves the agent its 40 searches for `judge_move` and
  `explore`.
- A refused job names the limit, what is left and `retry_after_seconds`, as AG4-D does. Each value
  is a server option (`--max-job-plies` …).
- 400 plies an hour is about 19 minutes of engine time on this host (2.9 s a ply, §0.3).
- **F13.** `open_game` with `plies` admits its plies one by one, as today; when one is refused after
  others were analysed, the answer is the moves with the analysed plies' summaries, `refused`
  (the ply and the message, with `retry_after_seconds`) and `next` (`analyze_game`), instead of an
  error. A refusal of the first ply stays an error.

## 9. Hosts

- Every host: §2 works with tools alone; the digests keep each answer under 64 KiB (§0.3: max
  8,363 characters).
- **HIMARI today** (views that cannot call tools, no progress display): the flow of §2 with the board
  at the end. HIMARI's next view phase (views calling their own server's app-visible tools, a
  progress display) is HIMARI's design; this packet needs nothing from it.

## 10. Considered and left out

- **Reusing `calliope.server.jobs`.** Its jobs are files with an environment check and a
  `result.json` for the HTTP API; the agent needs only the cache entries and a progress count.
- **A game-level commentary (a summary of the game) on the board.** It needs a subject that is not a
  ply in the store and in `calliope_result_v1` and a place in the viewer; a later packet. Until then
  the summary is the chat's (§7 step 4).
- **The digest as the only `ply` answer.** `view: "full"` stays for clients and tests that read the
  whole graph.
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

- **Digest:** for a stored analysis, the digest has exactly the fields of §3.2; REFUTED claims are
  named with their refs; no `from_root` beyond a line; every `ref` in it resolves; a proposition
  built from a digest's refs verifies as one built from the full answer.
- **Size:** the digest of every ply of the test games stays under 16,000 characters.
- **`detail`:** for each kind of handle, the projection equals the item of the full answer (V5
  applied); a foreign handle is refused.
- **`analyze_game`:** a job analyses its range in order, counts cache hits, answers the same job
  twice, refuses another range of a running game, waits at most `wait_seconds`, sends progress with
  a token, survives an engine failure as §4.3, and a restarted process finishes from the cache.
- **Engine lock:** a `judge_move` during a job is answered after at most one ply (fake engine).
- **Overview:** lines for analysed and unanalysed plies; the moment rules on a constructed game.
- **Submission:** by-reference propositions verify and fill; a wrong `use` is refused; `items` stores
  the accepted and reports the refused; ids per item.
- **`show_game`:** zero analysed plies, a running job, 200 plies; the viewer test shows `pending`.
- **Budget:** each limit of §8 refuses with its message.
- **Build:** a new `TOOLS_VERSION` and `GUIDANCE_VERSION`; the pin tests.

## 14. Packets

1. **AG6a** — what an agent is shown: the digest and `view`, `detail`, compact JSON, propositions by
   reference, `items`, the instructions and `next` for the one-ply path. It works in today's
   hosts and removes the 64 KiB cut.
2. **AG6b** — the game path: `analyze_game`, the engine lock, the job budget, `game_overview`,
   `show_game` at any stage and the viewer's progress, the game order in the instructions; the trial
   of §12.

## 15. Owner questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | `ply` answers the digest by default, the full graph with `view: "full"` (§3.2) | Yes |
| Q2 | REFUTED claims named, not shown, in the digest (V3) | Yes: 39% of the claim text, and none is a reason |
| Q3 | Propositions by reference for `judgement` and `claim` (§5.1) | Yes |
| Q4 | Job budget values of §8 (200 plies a job, 1 running and 4 queued, 400 plies an hour) | Yes; ≈ 19 min of engine time an hour on this host |
| Q5 | Moment rules of §3.3 (at most 8) | Yes |
| Q6 | A game-level commentary on the board in a later packet (§10) | Yes |
