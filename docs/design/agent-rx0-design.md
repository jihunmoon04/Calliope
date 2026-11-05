# Agent RX0-D — the evaluation contract: sets, moments, the run record, metrics and arms

Status: **design, rev. 2, for independent re-review. Owner questions are in §10. Independent review of rev. 1
(`e6dd665`): NOT_READY (B1–B4; N1–N3), applied, §11.** Date: 2026-11-05.
Base: `main @ e8fe04f` (RX framing merged, PR #138).
Inputs: [`agent-reflection-framing.md`](agent-reflection-framing.md) (the RX framing, rev. 4: §3 the
Calliope-run agent and its record, §3.2 the two loops, §4 sets, metrics and arms, §5 the critic, evaluator and
judge, §8 the owner's answers Q1–Q6, §8.1 the sets), [`agent-st-design.md`](agent-st-design.md) §0 (the trial
setup and the blind judge), [`agent-st-implementation.md`](agent-st-implementation.md) §4 (the latest trial).

The framing settled what is measured and why. RX0-D settles **how**: which moments, what a run writes, how
each metric is computed from it, how large a comparison must be, and what each arm runs. It changes no code.
RX1 implements §4 (the record) with the runner. RX2 is the first packet that runs the arms.

## 1. Scope

RX0-D fixes:

- the sets' manifest and where their PGNs live (§2);
- the rule that chooses each game's fixed moments, and each moment's reference (§3);
- the run record's two layers, its lines and its run id (§4);
- `evidence_identity`, the key that compares cited evidence across runs (§5);
- M1–M4 as computations over the record and the judge's output (§6);
- the comparison's size and the judging protocol (§7);
- the arms A–E as runs (§8).

It does not fix the runner's code, the critic's and evaluator's prompts (RX4), the lesson store (RX5) or any
change to the server's answers, the check or the guide.

## 2. Sets

The sets are the framing's §8.1: Train is the four trial games (`hung`, `rapid`, `fresh`, `fourth`); Validation
and Test are four new chess.com games each.

- **The manifest** is a file in the repository, `tools/rx/sets_v1.json`. For each game it holds the set, the
  chess.com game number (or, for Train, the fixture's path), the owner's side, and the SHA-256 of the game's moves as UCI joined by spaces (the
  same digest whatever the PGN's headers or comments). It holds no PGN.
- **Validation's and Test's PGNs** live outside the repository, in the data directory (`~/.local/share/calliope/rx/sets/`), one
  file per game named by its number. The runner checks each against the manifest's digest before a run. A
  mismatch stops the run.
- **Test stays closed while anything is chosen** (review B3). While lessons, prompts and guides are written,
  compared and promoted, no session sees a Test PGN, reference or commentary. Test is opened once a lesson set
  (and guide) is **frozen** for measurement:
  1. the frozen candidate runs on Test;
  2. Test's moments (§3.1) and references (§3.3) are built then, and the owner reviews their key causes;
  3. an independent judge session, not one used during selection, judges Test's commentaries once;
  4. nothing learned from Test's judging changes that candidate or chooses among candidates. A later candidate
     is measured on Test again only with new Test games (framing §8.1: games played after RX0).
- **Train's PGNs** are the repository's fixtures: `hung` = `tests/agent/fixtures/hung_queen.pgn`, `rapid` =
  `tests/reasoning/fixtures/chesscom_rapid_813_801.pgn`, `fresh` = `tests/agent/fixtures/weak_engines_1.pgn`,
  `fourth` = `tests/agent/fixtures/weak_engines_2.pgn` (the last two are engine games, not chess.com's;
  framing §8.1). The manifest names them by path instead of a chess.com number.

## 3. Moments and references

### 3.1 The rule

Each game gets **three fixed moments**, chosen by code from `game_overview`'s moments before any run of any
arm. `game_overview` ranks a game's plies by their reasons (`_moments` in `agent/session.py`: blunder 1,
mistake 2, miss 3, brilliant 4, great 5, loss ≥ 150 6, turning point 7, inaccuracy 8; then the larger loss,
then the earlier ply). From that ranking:

1. **two error moments**: the first two plies of the ranking whose reasons include `blunder` or `mistake`;
2. **one good moment**: the first ply whose reasons include `miss`, `brilliant` or `great`;
3. **filling** (review N1): a slot step 1 or 2 cannot fill takes the next ply of the ranking not yet chosen,
   in ranking order, until three are chosen. The manifest records which slots were filled this way.

Both sides' moves count, as in the trials' fixed moments. If the whole ranking has fewer than three plies, the
game is replaced from the framing's reserve. The chosen plies are written into the manifest with the build
identity of the analysis that ranked them.

The Train games keep their trial moments (ST-D §0: hung 14, 25, 68; rapid 40, 52, 54; fresh 56, 62, 76; fourth
37, 38, 56), so Train results stay comparable with the trials.

### 3.2 Kinds of failure

After the rule runs, RX1 counts each set's moments by the items their digests serve: a `held` piece (a piece
left en prise), a `lost_defence` or threat whose since-when is older than the move (ST), a `same_reply`, a
pin or another relation claim. If Validation lacks a kind that Train has, one Validation game is replaced
from the reserve and the rule runs again. Test is not inspected.

### 3.3 The reference

Each moment's reference is built by Calliope's code, as in ST-D §0: the FENs before and after the move, the
best and played lines numbered, the other candidates, the board items with their since-when, the same reply,
the claims with their `proves`, and the game's PGN. The reference also gets one thing it did not have:

- **Key causes** (framing Q5). For each moment the judge drafts the causes a commentary should explain, at most
  four. Each cause names the reference items that hold it, by `evidence_identity` (§5). The owner reviews the
  draft, then the causes are frozen with the reference. M2a and M2b read them.

## 4. The run record

### 4.1 Where and how a run is named

- **The run id** is a ULID. The runner draws it and starts the server process with `CALLIOPE_RUN_ID` set. The
  server writes it into every line it records.
- **Recording is on only when `CALLIOPE_RUN_RECORDS` is set** to a directory. Unset, as in HIMARI today, the
  server writes nothing and answers exactly as before. For RX2's HIMARI arm the variable is set in HIMARI's
  server configuration. Without a `CALLIOPE_RUN_ID` the server then draws its own run id once, at start
  (framing §3.1: one HIMARI conversation is one server process).
- **Files**: `<records>/<run_id>/agent.jsonl` (the runner) and `<records>/<run_id>/tools.jsonl` (the server).
  The directory is outside the repository and holds the owner's games and the models' text.

### 4.2 Lines of the tools layer (server)

Every line has `run`, `seq` (from 1), `t` (seconds since the run's start) and `type`.

| `type` | Fields |
| --- | --- |
| `start` | the server's build identity (tool, digest, board and check versions; the reasoning build), the engine's identity, the limits, the guide and instructions served |
| `call` | `tool`, `arguments`, `ms`, `answer` (in full), `answer_sha256`, `answer_bytes`, or `error` |
| `handle` | one per newly served handle: `ref`, `kind`, `game`, `source`, `address`, `identity` (§5) |
| `submission` | `game`, `plies`, the sentences with their `cites`, `accepted`, every `problem` with its `rule` |
| `end` | `reason` (`closed`, `bound`, `error`), counts of calls, handles, submissions, the capped calls |

A `handle` line follows the `call` that served it. A tool answer is held in full (framing Q3) under a cap of
**32 MiB a run**. Past the cap, `answer` is left out and `answer_sha256` and `answer_bytes` remain, and the
`call` line says `capped: true`. `handle` and `submission` lines are always written in full: they are small,
and M1, M2a and M3 read them. The cap does not end the run. Its `end` lists the capped calls (review B4).

### 4.3 Lines of the agent layer (runner)

| `type` | Fields |
| --- | --- |
| `start` | the model id and its parameters, the arm (§8), the set and game, the moments in scope, the bounds (turns, tool calls, tokens), the system prompt's SHA-256 and the guide version, the lessons put in (arm D: their ids) |
| `request` | the messages sent since the last request (not the whole history again), the tools offered |
| `response` | the model's text and tool calls, tokens in and out, cost |
| `feedback` | arm B: the refusal restated; arm C: the critic's feedback (§8), with its round |
| `end` | `reason` (`done`, `turns`, `tool_calls`, `tokens`, `error`), totals of tokens and cost |

### 4.4 Integrity

What a run must record depends on who ran it (review B1):

| Run | Layers required | Not observable |
| --- | --- | --- |
| the Calliope runner (arms A–E) | agent and tools | — |
| HIMARI (RX2's baseline) | tools | prompts, model responses, tokens and cost, HIMARI's own context |
| the critic, evaluator and judge | their session's own record (prompt file, input, output) and, when they call Calliope's tools, a tools layer under their own run id | — |

- A run is **whole** when each required layer has `start` and `end` and its `seq` has no gap, and, for the
  runner, when every tool call in the agent layer has its `call` line in the tools layer, in order.
- **No run is dropped for being capped** (review B4). A capped run is whole if its lines are. Every metric that
  its lines still give is computed: M1a, M1b, M2a, M2b, M3 and M4 read `handle` and `submission` lines and the
  stored commentary. A metric that needs a capped answer's body is marked **missing** for that run, not zero.
  Each comparison reports, per arm, the runs, the capped runs, the runs that hit a bound and the runs not whole.
- A run that is not whole (a crash, a lost file) is reported with its reason and counted as a failure of its
  arm in the run counts. An arm that fails more must not look better by losing its hard runs.
- A report on a HIMARI run states what it cannot show (the table's last column). RX2 compares HIMARI and the
  runner on the tools layer's metrics only, and reports cost and tokens for the runner alone.

## 5. `evidence_identity`

A handle (`c3.<token>`) changes from process to process (framing C1). The server already keys each handle by
`canonical([prefix, source, address])` (`agent/handles.py`). The identity is that key **with the fields that
belong to one process removed**:

| Kind | Source | Address | Identity |
| --- | --- | --- | --- |
| `j` judgement, `c` claim | `analysis`: path, `tree`, `graph`, `build` (content digests) | judgement index and move; claim id | `[kind, game, path, tree, graph, build, address]` |
| `s` engine line served by `ply` or `judge_move` | `analysis` (as `j`, `c`) | judgement index, rank, FEN | `[kind, "analysis", game, path, tree, graph, build, judgement, rank]` |
| `s` line of a search (`_search`) | `search`: position, search id, lines digest | rank, FEN, path | `[kind, "search", game, position, lines digest, rank]` |
| `b` board item | `board`: subject, `bundle` | the item's canonical propositions | `[kind, game, subject, propositions]` |
| `f` fact record | `facts_tree`: **`rev`** (one process's revision) | position, family | `[kind, game, position, family]` |
| `x` explored line | `facts_tree`: **`rev`** | from, moves, by | `[kind, game, from, moves, by]` |

The identity is the SHA-256 of the canonical JSON of that list, written into each `handle` line.

- A board item's identity omits `bundle`, so the same relation stays the same evidence when an analysis is
  rebuilt. A claim's identity keeps its digests: a claim from another build is other evidence. Coverage is
  therefore compared within one build. Each comparison names its build.
- **An `s` handle has two sources** (review B2). `ply` and `judge_move` serve the judgements' lines with the
  analysis as source (`_serve_analysis` in `agent/session.py`). A search serves its lines with the search as
  source (`_search`). The identity keeps the branch, so the two are different evidence even when their moves
  agree. A key cause that means "this line", whichever served it, also names the line by **`line_key`**: the
  FEN and the first eight plies of the PV in UCI. M2a counts a cited `s` handle of either source whose
  `line_key` matches.
- Two runs on the same build and the same cached analyses give the same identities for `j`, `c`, analysis `s`,
  `b` and `f`. Search `s` lines and `x` lines agree when the searches and the moves agree, which the engine does
  here (MS framing §1: 111 of 111 plies).
- **RX1's test**: the same moments read in two server processes give different handles and equal identities
  for every `j`, `c`, `b` and `f` handle, for the analysis `s` lines of `ply` and of `judge_move`, for the `s`
  lines of the same search, and for `x` lines of the same `explore` (moves and `search`).

## 6. Metrics

Units: a **moment-run** is one fixed moment in one run. Rates are per 100 sentences of the stored commentary
at the fixed moments, unless stated.

### 6.1 M1 — fact errors

- **M1a check refusals**, from `submission` lines: refused submissions a run, and each problem by class.
  - **fact**: S3 (a move, score, square or number no cited proposition gives), S7 (`states`), and a proposition
    that does not verify;
  - **form**: S1 (shape, count, length, class, language field), S2 (no citation, or one not served), S8
    (script);
  - **other**: any rule not listed here, named in the report.
- **M1b factual errors**: the judge's wrong sentences per 100 (§7.2).
- **M1c accepted but wrong**: M1b's wrong sentences by kind. The kinds start from the trials' list: an attack
  older than the move read as new; a piece or side misread; a cause the lines do not show; a grade misnamed; a
  line that cannot be played; other. A kind the judge adds is kept and named.

### 6.2 M2 — omissions

- **M2a evidence coverage**: for each key cause (§3.3), whether some stored sentence at that moment cites an
  item whose identity is among the cause's items. Reported as the share of key causes covered, over
  moment-runs.
- **M2b explanation coverage**: for each key cause, the judge's verdict on the moment's commentary: explained,
  partly, or not. A cause explained without citing its items counts as explained for M2b and uncovered for
  M2a, and the report lists those cases.

### 6.3 M3 — strategy

For each key cause's items in a moment-run:

- **Available**: some `call` answer before the moment's last accepted submission contained a handle with
  that identity.
- **Used**, in two grades (review N2). A call at the same position may look into another question, so a
  shared position alone is not use:
  - **Used, direct**: a stored sentence cites it, or a `detail` of its ref;
  - **Used, related**: an `explore` whose moves begin with the item's line, or whose moves or end facts touch a
    square or piece the item names; a `judge_move` of a move the item names. An `explore` from the item's
    position that touches none of these is not use.
- **Explained**: M2b says explained.

M3 reports, over moment-runs, the shares Available → Used, direct → Used, related → Explained, and two
patterns:

- **P1, evidence left unread**: a key cause Available and not Used in either grade.
- **P2, scores alone**: a moment whose accepted sentences cite only `j` handles and score propositions,
  while a `b` item or a `same_reply` of a key cause was Available.

"Used" is an observed act. It does not say what the model read (framing B2).

### 6.4 M4 — quality

The judge's score of each commentary at a fixed moment, 1–5, for how concretely it explains the verdict (as
in ST §4), and the owner's reading of a sample. M4 is never the only reason to promote.

## 7. Comparisons

### 7.1 Size

- **Runs.** Three runs a game an arm (the trials ran two). On Validation, that is 12 runs and 36 moment-runs an
  arm.
- **The independent unit is the game** (review N3). Runs of one game and moments of one game are correlated.
  Validation has four games, so a comparison rests on four units however many runs it has.
- **Variance.** RX2 measures, on arm A, each metric's spread between games and between runs of the same game.
  From it RX2 states the smallest difference each metric can show at this size, with a bootstrap that
  resamples games, then runs within a game, then moments within a run (two-sided 90%). Arms are compared
  paired, game by game, on the same moments.
- **Confirmed or exploratory.** A difference is **confirmed** when it is at least the size below and its
  interval excludes zero. Otherwise it is **exploratory**: reported, never a reason to promote. With four
  games the intervals may be too wide to confirm anything. RX2 then states how many Validation games are
  needed, and the next packet adds them from the reserve and from games played after RX0.
- **What counts as a difference.** One worth acting on is at least **2 wrong sentences per 100** for M1b (about
  the trials' v7–ST gap), **10 points** of key-cause coverage for M2a and M2b, and **1 refusal a run** for M1a.
  If RX2's spread says three runs cannot show these, RX2 states the runs (or games) needed and the next packet
  uses them. Promotion (framing §5 item 2) needs a confirmed difference on Validation.

### 7.2 Judging

- One judge session per comparison. All arms' commentaries at the fixed moments are shuffled together,
  without their arm, as in ST-D §0.
- The judge gets each moment's reference with its key causes, checks boards and lines with python-chess, and
  returns for each sentence `ok`, `doubtful` or `wrong` with the kind (§6.1), for each key cause its M2b
  verdict, and for each commentary its 1–5 score.
- The judge's prompt is a versioned file (`judge_v1`). Its output is JSON in a fixed schema, kept with the
  comparison.
- Arms are compared only within one judging (ST-D §0.5). A re-judging of earlier commentaries is a new
  judging.
- The judge never sees the critic's feedback or the lessons, and is not the critic's or the evaluator's
  session (framing §5).

## 8. Arms

| Arm | Runs | Bounds and parameters |
| --- | --- | --- |
| **A** | the runner with `commentary_ko_v8` and the server's instructions; the agent sees refusals as today and may resubmit on its own | starting bounds of turns 60 and tool calls 120 a run; RX2 fixes them from arm A's runs, as for tokens below |
| **B** | A, and after a refused submission the runner restates its problems and asks for one corrected submission | at most *N* = 3 restated refusals a moment |
| **C** | B, and after the last accepted submission of a moment the critic returns structured feedback (framing §3.2); the agent may call tools and resubmit | at most *K* = 2 rounds a moment; the critic reads Train and Validation only |
| **D** | B, and the lessons in the system prompt, after the guide | RX4: put in by hand; RX5: retrieved from the store |
| **E** | D with a new guide version | — |

- **A is today's behaviour.** The framing's table calls A "no retry". Today the agent already resubmits on its
  own, and RX0-D does not take that away. A is the agent as it runs in HIMARI, without HIMARI. B adds the
  runner's explicit retry. This is an amendment to framing §4.3 (§9).
- **The writer** is luna (`openai/gpt-6-luna`) in every arm (framing Q6).
- **The bounds.** RX2 sets the turns, tool calls and tokens a run from arm A's runs (the 95th percentile and a
  margin) and fixes them for every later arm. A run that reaches a bound ends with `end.reason` naming it, and
  is counted, not dropped.
- **Caches.** All arms run on the same warm analyses of the sets. Each arm's runs use a fresh server process
  and a fresh facts tree. The critic, evaluator and judge each use a data directory of their own (framing §5
  item 5).

## 9. Amendments to the framing

- **AM1 (§4.3, arm A).** A is "one commentary as the agent makes it today, without the runner's retry, the
  critic or lessons", not "no retry": the agent's own resubmissions stay.
- **AM2 (§3.1, recording).** The server records only when `CALLIOPE_RUN_RECORDS` is set, so HIMARI's present
  use is unchanged unless the variable is set for a trial.

## 10. Owner questions

- **Q1 — Validation's and Test's PGNs outside the repository.** The manifest (numbers and digests) in the
  repository, the new games' PGNs in the data directory; Train's stay the fixtures they are. Recommended: yes.
  Validation's could go into the repository like the fixtures, but Test's must not, since the critic, evaluator
  and judge read the repository, and one rule for the new games is simpler.
- **Q2 — Three runs a game an arm.** On luna this is about $0.02 a run (ST §4), 12 runs an arm on Validation.
  Recommended: three, revised by RX2's spread.
- **Q3 — The judge's model.** The trials' fresh-context judge was a Claude session. Recommended: the same, with
  `judge_v1` fixed for RX2–RX4.

## 11. Review dispositions — rev. 1 (`e6dd665`), independent review: NOT_READY

The review read `e6dd665`. The next commit on the branch, `8143f59`, made before this revision, had already
corrected §2 on `fresh` and `fourth` (they are the engine fixtures) and dropped rev. 1's Q4.

| Item | Finding | Disposition |
| --- | --- | --- |
| B1 | The completeness rule asks for both layers, but HIMARI's runs have the tools layer only, so RX2's HIMARI baseline would be dropped | Applied: §4.4 requires layers by who ran the run; a HIMARI report states what it cannot observe; RX2 compares on the tools layer's metrics |
| B2 | An `s` handle served by `ply` has an `analysis` source, not `search` | Confirmed in `agent/session.py` (`_serve_analysis` serves `s` with the analysis source; `_search` with the search source). Applied: two `s` rows in §5, `line_key` to match one line across sources, RX1's test extended to analysis and search `s` lines and `x` lines |
| B3 | "No Test PGN to the judge" conflicts with measuring on Test | Applied: §2, Test closed while anything is chosen, opened once for a frozen candidate, judged once by an independent judge, its judging never feeds back into that candidate |
| B4 | Dropping capped runs favours arms that explore more (C) by losing their hardest runs | Applied: §4.2 the cap leaves `handle` and `submission` lines whole and does not end the run; §4.4 no run is dropped for the cap; metrics that cannot be computed are missing, not zero; capped, bound and not-whole runs reported per arm; not-whole runs count as failures |
| N1 | The moment rule can choose fewer than three when a kind is short | Applied: §3.1 step 3 fills from the ranking, recorded in the manifest |
| N2 | "Used" by an `explore` at the same position overstates use | Applied: §6.3 Used, direct and Used, related; the same position alone is not use |
| N3 | Four games are four independent units; a 90% interval on them is unstable | Applied: §7.1 the game is the unit, paired comparisons, confirmed or exploratory, only confirmed differences promote, RX2 states the games needed |
