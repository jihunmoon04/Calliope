# Agent TO-D — tool outputs for the commentary loop: brief views and a line comparison

Status: rev. 1, for independent review. Scope: the agent's MCP tools (`src/calliope/agent`), the
answers the model reads. Not in scope: the staged harness and per-moment conversations (a packet of
their own, §8), the guide (`commentary_ko_v8`, frozen for RX), HIMARI.

## 0. Why

MH made Haiku the runner's default (`agent-mh-implementation.md`). A harness pilot after it (a judge
that sends a weak decisive cause back; two Validation games, two runs an arm, read by the author, not
blind; `D:/00_프로젝트/rx-trial/harness-pilot.md`) found:

- The judge made the agent look for evidence itself: 3–8 `explore` calls a run against none in the
  plain loop, and the decisive `on_request` evidence of 23.Rxe5 fetched in 3 of 4 runs against 0 of 3.
- Cost and time grew: about $0.37 a run against $0.14, 25–41 turns against 10–19. About 90% of every
  arm's cost came from requests over 100,000 prompt tokens, which Haiku bills at five times the rate.
- Requests grew because `explore` and `facts` answers are large and stay in the conversation.

Tool use and answer sizes over every RX run (luna 171, Haiku 44, staged 9; `rx2-1` left out):

| Tool | Calls a run (luna / Haiku / staged) | Answer, median characters (p90) | About tokens |
| --- | --- | --- | --- |
| `ply` | 14.4 / 13.4 / 3.4 | 4,156 (6,324) | 5k |
| `submit_commentary` | 6.1 / 7.8 / 7.8 | 508 | 0.7k |
| `show_game` | 1.3 / 1.2 / 3.9 | 1,433 | 2k |
| `analyze_game` | 1.0 / 1.0 / 0 | 176 | 0.2k |
| `game_overview` | 1.0 / 1.0 / 0.1 | 10,658 (15,447) | 14k |
| `definitions` | 0.9 / 0.5 / 0.9 | 663 | 0.9k |
| `explore` | 0.18 / 0 / 5.4 | **23,209 (27,595)** | **30k** |
| `facts` | 0.02 / 0.08 / 4.8 | **16,279 (28,701)** | **21k** |
| `detail` | 0.08 / 0.25 / 1.7 | 867 | 1k |
| `judge_move` | 0.01 / 0.08 / 0.1 | 6,710 | 9k |
| `open_game`, `commentary` | about 0 | — | — |

What fills them (means over the pilot's 80 `explore` and 45 `facts` answers):

- `explore`: 23,000 characters, of which `end_facts` 17,090 and in it `pieces` 12,455; the line itself
  (`plies`, each move and the material balance) 1,953; the end search 545.
- `facts`: `families` 20,300, of which `pieces` 13,078.
- `pieces` lists **every** piece of the position, about 18, at about 690 characters each: identity,
  attacks on empty, friendly and enemy squares, attackers, defenders, legal moves and destinations.
  Most entries are pieces nothing happens to; the guide sends the agent to `pieces` for attacks,
  defences and pins.
- `game_overview`: `lines` 12,072 of 13,400 (one entry a ply, Korean and English names of each grade).

The pilot also showed that the agent compares lines badly when it has to assemble the comparison
from long answers. Of the four staged runs at 23.Rxe5, one compared the two lines' material (+3
against +2); two stopped at "the evaluation gap is not explained by material" (one of them after
finding both lines at +2 at the sixth ply), and one wrote a line that is not the engine's. The
difference lies at the lines' ends (after 23.dxe5 the engine goes on to 25.Nf6+). A summary built by the pilot's harness from the same Calliope calls — per ply the material
balance, at the end the engine's evaluation — was a few hundred bytes a line and matched the reviewed
key causes' numbers exactly (23.Rxe5: [3, −2, 3, 2, 3, 2]).

## 1. The change

| Part | What |
| --- | --- |
| A | `explore` and `facts` take `view`: `"brief"` (the default) or `"full"` (today's answer). The handle each serves stays the full record, so `detail(ref)` returns everything and citations are checked as today. |
| B | A tool `compare_lines(game, ply)`: the played move's line, the best move's line and the game's own continuation from the position before the move, each with the material balance a ply and its end, side by side. |
| C | `game_overview`'s `lines` without the repeated names: one compact entry a ply. |

## 2. A — brief views

### 2.1 `pieces` in a brief view

An entry is kept when its piece is in play:

- it has an attacker and `attacked_without_defender` or `attackers_exceed_defenders`;
- it is `absolutely_pinned`;
- it attacks an enemy piece that is kept by the first rule, or attacks two or more enemy pieces;
- it is the king of the side in check;
- it stands on the square the last move of the path moved to, or captured on.

A kept entry carries: `square`, `color`, `piece_type`, `origin` (from `identity`), `attackers` (square,
type, pinned), `defenders` (squares), `attacker_count`, `defender_count`, `attacks.enemy`,
`attacked_without_defender`, `attackers_exceed_defenders`, `absolutely_pinned`,
`legally_capturable_now`. Left out: `attacks.empty`, `attacks.friendly`, `legal_moves`,
`legal_destinations`, the `identity` object (its fields stand in the entry), the definition wrapper of
`lowest_attacker_types` (its value stays).

The family answers what it left out: `{"shown": n, "of": 18, "omitted": "pieces without an attacker
in excess, a pin or a double attack; view: \"full\" for all"}`.

### 2.2 Other families in a brief view

- `exchange`: the exposed pieces only (a non-zero gain for the side that starts); the others counted.
- `status`, `material`, `pawns`, `patterns`: as today (small).

### 2.3 `explore` in a brief view

`start`, `end`, `plies`, `units`, `search` (with `search`), `ref` and `budget_left` as today;
`end_facts` in the brief views of §2.1–§2.2. Expected: about 23,000 → 5,000–7,000 characters (§6
measures it).

### 2.4 What does not change

- The handles (`x`, `f`) are served with the full record; `detail(ref)` returns it.
- `submit_commentary`'s checks read the facts tree, not the answer; a proposition the agent can cite
  today it can cite tomorrow, with `view: "full"` or `detail` to find it.
- The default families of `facts` (`status`, `material`, `pieces`), which the guide states.
- The run record's `shown` (refs in the answer's text): an answer's own `ref` stays.

## 3. B — `compare_lines`

`compare_lines(game, ply, length=16)` answers for a ply of the game:

```json
{"ply": 45, "move": "23.Rxe5", "best_move": "23.dxe5", "from": {"ply": 44, "fen": "…"},
 "lines": {
  "best":   {"moves": ["dxe5", "g5", "Qf2", "…"], "material": [3, 3, 3, 3, 3, 2, 2, -1],
             "end": {"material": -1, "score": "+5.12", "continuation": ["Nf6+", "…"]}, "ref": "x7.…"},
  "played": {"moves": ["Rxe5", "Rxe5", "dxe5", "Qxe5", "Nxc4", "Qxc3"], "material": [3, -2, 3, 2, 3, 2],
             "end": {"material": 2, "score": "+2.59", "continuation": ["Bb2", "…"]}, "ref": "x8.…"},
  "game":   {"moves": ["Rxe5", "Rxe5", "dxe5", "Qxe5", "Ne4", "Bxe4", "Qxf4", "Qxc3"], "material": […],
             "end": {"material": -1, "score": "-0.43"}, "ref": "x9.…"}},
 "units": {"material": "points_v1, White's view, the position before the move = 0"}}
```

- **Lines.** `best` and `played` are the engine lines the ply's digest holds (`lines.best.pv`,
  `lines.played.pv`); `game` is the game's next plies, up to `length`. A ply whose played move is the
  best has no `best` line.
- **Length.** A line is extended by its end search's principal variation while a capture, a check or
  a promotion stands in its last two plies, up to `length` plies, so a line does not stop in the
  middle of an exchange. `end.continuation` is the next five plies of the end search.
- **The machinery.** Each line is Calliope's own `compare` (AG8-D §5: `_explore` with `by:
  "calliope"`, one search at its end); each serves an `x` handle the agent may cite. A line that ends
  the game answers its end status instead of a score.
- **Cost.** Three searches a call, admitted as `explore`'s (a stored search is free).
- **Size.** About 1,500–2,500 characters.

## 4. C — `game_overview`

Each `lines` entry: `ply`, `move`, `grade`, `score`, `loss`, and `best_move` and `label` when they have
one. `grade_ko` and `label_ko` move to one table at the top (`names`), since there are six grades and a
handful of labels. Expected: about 12,000 → 5,000 characters on a 70-ply game.

## 5. Versions and compatibility

- `TOOLS_VERSION` `agent_tools_v6` → `agent_tools_v7` (the tools' descriptions and answers change);
  `tests/agent/test_commentary.py` pins it.
- The guide stays `commentary_ko_v8`. Its line on `facts` remains true (default families unchanged).
  The new tool and the views are described in the tools' own descriptions, which the server sends.
- RX: the tools' definitions are recorded with every run (the lesson sets' `versions`). A run on v7 is
  compared with runs on v7; `trial-haiku-1` (v6) is the baseline the first v7 batch is read against,
  with the version named in the report.

## 6. Tests and measurement

**Tests.** The brief filter (each keep rule; the `omitted` note; full equals today's answer); `view`
validated as `ply`'s; the handle of a brief answer is the full record; `detail` returns it; a
proposition from an omitted entry is still accepted; `compare_lines` on a fixture game (the lines'
material against `material_flow`, the extension rule, a line ending in mate, a best played move);
`game_overview` keys; `TOOLS_VERSION`.

**Measurement, in order:**

1. **Replay (no model).** Every `explore` and `facts` call of the RX records replayed through the v7
   server on the same bases, in both views: the brief size against the full, and the kept entries
   against the pieces the reviewed key causes name (none of them lost).
2. **Pilot.** The two games of the harness pilot, the plain loop and the staged harness, two runs
   each, on v7: cost, tokens a request, turns, and whether `compare_lines` is called.
3. **Blind.** Validation, three runs a game, the plain loop on v7 against `trial-haiku-1`, judged as
   RX judges (M2b, M4, M1b, cost). The staged harness is measured in its own packet (§8).

**Accepted when** the brief `explore` is at most 8,000 characters at the median, no key cause's
piece is lost in the replay, and on Validation M2b and M1b are no worse than `trial-haiku-1` (its
interval) at a lower cost a run.

## 7. Questions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | A tool that resolves every hanging piece by playing the captures out? | Not yet: `exchange` already plays legal captures on a square, least valuable first, either side free to stop (F6-D), and the brief view shows its exposed pieces. A tool that also plays checks and other forcing moves in between is a larger piece of work; decide after §6.2. |
| Q2 | Hide `open_game` and `commentary` from RX runs? | The runner may offer a subset of tools (a runner option, not a server change); not in this packet. |
| Q3 | `brief` as the default, or opt-in? | Default: the plain loop never asks for a view, and the size is what costs. |
| Q4 | `compare_lines`' length 16 and the extension rule | As written; the replay of §6.1 shows how long the lines get. |

## 8. Not in this packet

- The staged harness (facts and the decisive cause in one turn, a judge, retries) and one
  conversation a moment, run in parallel: a packet of its own once the tools are lean, since its cost
  depends on them.
- Korean syllables garbled by Haiku (`agent-mh-implementation.md` §5).
