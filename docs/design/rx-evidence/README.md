# RX evidence

What the RX packets ran and decided, kept so that every result and judgement can be checked later. Design
documents state the decisions (`docs/design/agent-reflection-framing.md`, `agent-rx0-design.md`,
`agent-rx1-design.md`, `agent-rx2-design.md`) and the implementation documents report what was found
(`agent-rx1-implementation.md`, `agent-rx2-implementation.md`). This folder holds the data behind them.

## Where everything is

| What | Where | Size |
| --- | --- | --- |
| Small evidence: batch logs, the judging's inputs and outputs, its key, the audit, the metrics, the owner's reviews, every judged commentary | `docs/design/rx-evidence/rx2/` (this repository) | 0.5 MB |
| The references the judges read (key causes reviewed by the owner) | `tools/rx/references_v1/` (this repository) | 2.7 MB |
| The sets: game numbers, digests, fixed moments | `tools/rx/sets_v1.json` (this repository) | — |
| Raw run records: both layers of all 96 runs (`agent.jsonl`, `tools.jsonl`, `server.stderr`), the batch logs, the judging key, the four judges' transcripts, the bases' `base.json` | `D:/00_프로젝트/rx-archive/rx2-2026-11-05.zip` (outside the repository: 25,753,551 bytes, SHA-256 `f0bdfe5f9260a18e8c630f9e508084176bd370715154c242698a412dddf5b74b`) | 25.7 MB |
| RX4's raw records: the 123 runs' layers (`agent.jsonl`, `tools.jsonl`, `server.stderr`), the six batch logs, the six judgings' keys and audits, the 21 exported transcripts of the evaluators and judges, the rejected part 1 of `6b7d0bb5` | `D:/00_프로젝트/rx-archive/rx4-2026-11-06.zip` (outside the repository: 40,936,573 bytes, SHA-256 `5b8a6e53e3af144c87fda8ebe23ae29f036c09000527b55762cf16ca2a517e03`) | 40.9 MB |
| Working data the runs use (base caches, the PGNs of the owner's games, run records) | WSL, `~/.local/share/calliope/rx/` | 165 MB+ |

The raw archive is kept outside git because of its size and because it holds the models' full text and the
owner's games. Check it with `sha256sum` against the line above before relying on it.

## RX2 (`rx2/`)

| File | What it is |
| --- | --- |
| `commentaries.md` | **Start here.** Every one of the 144 judged commentaries, by moment: the reviewed key causes, then each commentary with its arm and run, the judge's verdict on each sentence (✓ ✗ ?), on each key cause and the 1–5 score |
| `report.json` | M1a–M4 per arm and set with their intervals, and A − A-min paired by moment (`python -m tools.rx.report`, through the checked judging) |
| `bounds.txt` | The bounds fixed from arm A's runs |
| `batch-rx2-1.jsonl`, `batch-rx2-2.jsonl` | Every run of both batches: arm, set, game, run id, end reason, turns, tool calls, tokens, cost |
| `batch-rx2-2-summary.txt` | The baseline batch summarised (wholeness, moments commented, re-analysis) |
| `judging-80ad6cfd/partNN/bundle.json` | What each judge was given (anonymous items) |
| `judging-80ad6cfd/partNN/judging.json` | What each judge returned |
| `judging-80ad6cfd/bundle_key.json` | The key: anonymous item → run, arm, game, ply (and the shuffle's seed) |
| `audit.txt`, `judging-80ad6cfd/audit-partNN.json` | The audit of each judge's exported transcript (all four pass); `audit-flagged-commands.txt`: the six commands rev. 1's rule flagged, all inside the directory |
| `owner-review-round1.md` | The owner's review of the first key-cause drafts (2026-11-05) |
| `key-causes-round2-sheet.md` | The second-round sheet the owner reviewed, with the Calliope runs of every `on_request` cause |

**Not kept.** The first-round drafts of the key causes were replaced in place by the second round and were
never committed; `owner-review-round1.md` quotes the ones the owner commented on. The causes of `rx2-1`'s three
errors were not recorded (the reason for amendment A1b).

## MH (`mh/`): Haiku as the default model

| File | What it is |
| --- | --- |
| `validation-report.json` | Haiku (`A:haiku`) against luna (RX2's arm A) on Validation, paired by moment, through judging `8b95714f` |
| `batch-trial-haiku-1.jsonl` | The 12 Haiku runs (arm A, cached): run id, end reason, turns, tool calls, tokens, cost |
| `cache-usage.json` | Each cached run's requests: prompt, cached and cache-written tokens, cost |
| `judging-8b95714f/` | The key, both parts' bundle and judging, the audits (part 2's flag accepted by the owner, recorded in its file) |
| `pilot/` | The two-game pilot: the wrapper (`trial.py`), the A2 rules, the Claude Code folders' maker, the collector, its runs and `results.md` (every commentary against the key causes, read by the author) |

The raw records of the 12 Haiku runs and the pilot's runs are in WSL (`runs/`, `trial/runs/`), not archived yet.

## TO (`to/`): tool outputs

| File | What it is |
| --- | --- |
| `replay.json` | TO-D §6.1: brief against full sizes of every recorded `explore` and `facts` call; key-cause and cited squares kept, and the one cited square left out |
| `replay_to.py`, `variants_to.py` | The replay, and the comparison of the keep rules (A1) |
| `compare-lines-24.txt`, `compare_to.py` | `compare_lines` on the 24 fixed moments: sizes, lines, extensions, searches; 23.Rxe5 in full |
| `harness-pilot.md` | The harness pilot that led to TO-D: every commentary of the four arms against the key causes, read by the author |
| `validation-report.json`, `batch-to-validation-1*.jsonl`, `judging-8341bd37/` | TO-D §6.3: the plain loop on v7 against `trial-haiku-1`, one judging, its key, audits and parts |
| `pilot-staged-v7.jsonl`, `staged.py` | TO-D §6.2: the staged harness on v7 (two games, two runs each) and its wrapper |

## Decision log

| Date | Decision | By | Where |
| --- | --- | --- | --- |
| 2026-11-05 | Learn from failures: a Calliope-run agent, Reflexion, lessons, prompt optimisation later | owner | RX framing |
| 2026-11-05 | The agent for batch and evaluation; HIMARI stays the user's host | owner (Q1) | RX framing §8 |
| 2026-11-05 | Eight new chess.com games for Validation and Test | owner (Q4) | RX framing §8.1 |
| 2026-11-05 | The guide frozen until arm E; the calibration arms A-min and D-min | owner | RX0-D §8, AM3 |
| 2026-11-05 | No HIMARI arm in RX2 (HIMARI may be dropped later if results hold) | owner | RX2-D §0 |
| 2026-11-05 | The task names the game by id (A1), after `rx2-1` opened other games | implementation | RX2-D §11 |
| 2026-11-05 | Key causes as causal chains, one decisive, with a route (A2); a capture a cause names is played out | owner's review | RX2-D §11 |
| 2026-11-05 | Three levels of target; positional causes out of RX (A3) | owner's review | RX2-D §11 |
| 2026-11-05 | The baseline accepted (`rx2-2`, judging `80ad6cfd`) | owner (Q1) | RX2 implementation §9 |
| 2026-11-05 | The audit voids only listings outside the judge's directory | owner (Q2) | RX2 implementation §9 |
| 2026-11-05 | Bounds from arm A for A and B; C and D measured for their own | owner (Q3) | RX2 implementation §8, §9 |
| 2026-11-05 | RX3 kept minimal; RX4 next (RX3 folded in as arm B) | owner | RX4-D |
| 2026-11-06 | Try the model, the reference's input and the A2 rules on two games, and Haiku in Claude Code | owner | MH §2 |
| 2026-11-06 | Judging `8b95714f` part 2's audit flag (a backslash in a string) accepted as a false positive | owner | MH §4 |
| 2026-11-06 | One packet with the trial and the switch to Haiku; switch on merge | owner | MH |

## The baseline in one table

From `report.json` (arm A, `commentary_ko_v8`, luna; Validation):

| | |
| --- | --- |
| Decisive key cause carried to its outcome (M2b) | 50% (Train 55%) |
| Wrong sentences (M1b) | 0.5 per 100 (Train 1.0) |
| Score (M4) | 3.69 / 5 |
| Decisive causes that needed `explore`, fetched | 0 of 9 (both arms, both sets) |
| v8 against the min guide, paired | Train: +12 points M2b, +0.33 M4; Validation: −6 points M2b, −0.25 M4 |
| Smallest difference a paired comparison confirms (these four games) | about ±8 points M2b, ±0.2 M4, ±2 per 100 M1b |

## Reproducing

In WSL with `~/calliope-venv` and `CALLIOPE_STOCKFISH_PATH` set (see the RX1 implementation §2): the sets and
bases (`python -m tools.rx manifest`, `annotate`), the references (`reference`, `requests`), a batch
(`python -m tools.rx.batch`), a bundle (`bundle`), the judges (fresh sessions in each part's directory with
`judge_v1.md`), the audit, and `python -m tools.rx.report`. The model's answers are not deterministic; the
records are what was measured.
