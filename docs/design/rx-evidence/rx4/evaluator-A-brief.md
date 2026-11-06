# RX4a evaluator (arm A → lessons for arm D): your brief

You are the **evaluator** of Calliope's RX4a (`docs/design/agent-rx4-design.md` §2 in the Calliope
repository, which you do not need to open). A chess-commentary agent (a small model driving Calliope's MCP
tools) wrote Korean commentaries on fixed moments of four **Train** games; blind judges graded them against
owner-reviewed key causes. Your job: from those failures, propose **up to 12 candidate lessons**, strategies
the agent will read in its prompt next time, each one later screened by re-running the agent with it alone.

## Rules (audited: your transcript is checked afterwards)

- Read and run **only what is in this directory**. Do not open the Calliope repository's files, any
  Validation or Test game, reference, record or commentary, `.env` files, or anything under
  `~/.local/share/calliope/rx/` except through `probe.py`. Do not call any model API.
- Write only into `out/`.

## What is here

| File | What it is |
| --- | --- |
| `commentaries.md` | **Start here.** The 12 Train moments: the owner-reviewed key causes (`[decisive]` and its route), then arm A's three commentaries each with the judge's verdict per sentence (✓ right, ✗ wrong, ? unsupported), per key cause (explained, partly, not) and the 1–5 score |
| `judging.json` | The same verdicts as data, with each run's id, game and ply |
| `references/<game>-<ply>.json` | What the agent's `ply` showed at each moment (the digest), the full record, the board, the PGN to the move, the key causes with their routes; `on_request` causes carry the request that shows them and what Calliope answered |
| `runs.json`, `runs/<run>/agent.jsonl`, `tools.jsonl` | The 12 Train runs of arm A (3 a game): every model turn, tool call and answer, and the submissions |
| `guide_commentary_ko_v8.md` | The guide the agent reads (its system prompt) |
| `tool_definitions.py` | The tools the agent has and what they take |
| `probe.py` | Calliope's tools on Train, to check a cure before proposing it (see below) |

`probe.py` runs in WSL (`wsl -d Ubuntu`), from this directory:

```bash
source ~/calliope-venv/bin/activate
export CALLIOPE_STOCKFISH_PATH=/mnt/d/00_프로젝트/Calliope/.venv/stockfish19/stockfish/stockfish-windows-x86-64-universal.exe
python probe.py fourth ply 37
python probe.py fourth explore '{"ply": 36}' '["f5h6", "f6h6"]'
python probe.py fourth facts '{"ply": 37}' '["exchange"]'
```

The games are `hung`, `rapid`, `fresh`, `fourth`. Each call takes a few seconds to a minute.

## What to find

For each moment, where did the commentaries fail the decisive cause (partly, not), or say something wrong
(✗)? Read the run records to see **why**: what the agent called, what Calliope showed it, what it never
asked for. RX2 found two patterns you may confirm or not: (1) when the move's grade is not explained by the
engine line's material, the agent did not play the game's own continuation with `explore`; (2) when a
capture or a piece left to be taken decides the grade, it did not play it out and give the evaluation where
it happens. Look for others too (wrong sentences, causes said without their outcome, facts that lead nowhere).

## What a lesson is

A lesson is **strategy for the agent, never a fact about a game**. Fields:

```json
{"id": "L01",
 "condition": "when this holds, in terms of what the agent sees (grade, the lines' material, board kinds, claim statuses)",
 "action": ["a step that uses explore, facts, judge_move or detail, with what to pass", "…"],
 "success": "what the submission must then cite or say",
 "fallback": "what to say if the action does not show it",
 "source": ["<run id>:<ply>", "…"],
 "why": "the failures it answers and what you checked with probe.py (not shown to the agent)"}
```

- **Condition, action, success, fallback** are what the agent reads, in Korean, **at most 400 characters
  together** a lesson.
- Never name a square (`e4`), a move (`19.Nh6+`, `Qxd7`), a game or anything only Train has: the lesson must
  serve unseen games. A lesson naming one is refused by the tooling.
- The action must use at least one of `explore`, `facts`, `judge_move`, `detail`, **saying what to pass**
  (e.g. "그 수 직전 국면에서 실제 진행 4수를 explore로 둔다"). An abstract instruction ("더 깊이 생각한다") is
  refused. Do not write a step that names a tool only to say not to use it.
- `source` names the Train moment-runs whose failure it answers: a candidate is screened on its source games,
  so each candidate should have sources where its condition actually held.
- One idea a lesson. Prefer few, clear lessons with evidence over many.

## What to write

`out/candidates_v1.json`:

```json
{"id": "candidates_v1", "status": "CANDIDATES", "lessons": [ … up to 12 … ]}
```

and `out/notes.md`: per moment, the failure you saw and its cause (a few lines each), then for each candidate
what you checked and why you expect it to help. Do not add `versions`; they are added when the file is
installed.
