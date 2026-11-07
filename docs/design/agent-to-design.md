# Agent TO-D — tool outputs for the commentary loop: brief views and a line comparison

Status: rev. 3; independent review NOT_READY (B1–B4; N1, N2) applied; re-review NOT_READY (C1–C3)
applied; second re-review READY_FOR_MERGE (2026-11-07) (§9). Scope: the agent's MCP tools (`src/calliope/agent`), the
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

An entry is kept when its piece is in play. The view computes the position's `exchange` records for
this choice even when the family was not asked for (it is a static computation on one position, F6-D;
the records are shown only when asked, §2.2). Kept:

1. **Exposed:** the `exchange` family finds a non-zero gain for the side that starts captures on its
   square (review B3: the count of attackers and defenders does not decide an exchange; the values
   and the order do);
2. **In that exchange:** every attacker and defender of an exposed piece's square, as the `pieces`
   record lists them (the pieces the capture sequence uses);
3. **Attacked by a lesser piece:** its lowest attacker is worth less than it (`lowest_attacker_types`
   against `points_v1`), defended or not;
4. **Outnumbered:** an attacker and `attacked_without_defender` or `attackers_exceed_defenders`;
5. **Pinned:** `absolutely_pinned`;
6. **Attacking:** it attacks a piece kept by rules 1–5, or two or more enemy pieces;
7. **Check:** the king of the side in check, and the pieces giving check;
8. **Last move:** it stands on the square the path's last move moved to or captured on.

A kept entry carries: `square`, `color`, `piece_type`, `origin` (from `identity`), `attackers` (square,
type, pinned), `defenders` (squares), `attacker_count`, `defender_count`, `attacks.enemy`,
`attacked_without_defender`, `attackers_exceed_defenders`, `absolutely_pinned`,
`legally_capturable_now`. Left out: `attacks.empty`, `attacks.friendly`, `legal_moves`,
`legal_destinations`, the `identity` object (its fields stand in the entry), the definition wrapper of
`lowest_attacker_types` (its value stays).

The family names what it left out, piece by piece, so the agent knows what it has not seen (review
B3): `{"shown": 6, "of": 18, "omitted": ["Ra1", "Nb1", "Bc1", "Kg1", "Pa2", …], "note": "omitted:
not exposed, not outnumbered, not pinned, not attacking a kept piece; view \"full\" or detail(ref)
for their records"}`. Each omitted piece is its letter and square (about five characters).

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

`compare_lines(game, ply, length=16)` answers for a ply of the game (the numbers are 23.Rxe5's):

```json
{"ply": 45, "move": "23.Rxe5", "best_move": "23.dxe5", "from": {"ply": 44, "fen": "…"},
 "root": {"played": {"score": "+0.08", "score_ref": "s50.…"}, "best": {"score": "+4.56", "score_ref": "s51.…"},
          "at": "the position before the move, depth 12"},
 "lines": {
  "best":   {"moves": ["dxe5", "g5", "Qf2", "Re8", "Ne4", "Rfxe5", "Bd2", "Bxe4", "fxe4", "Rxe4", "…"],
             "source": {"engine": 13}, "extended": 0, "material": [3, 3, 3, 3, 3, 2, 2, -1, …],
             "ref": "x7.…", "searched": {"ref": "x10.…", "plies": 13},
             "end": {"ply": 13, "material": …, "end_score": "…", "end_score_at": 13, "score_ref": "s60.…",
                     "continuation": ["…"]}},
  "played": {"moves": ["Rxe5", "Rxe5", "dxe5", "Qxe5", "Nxc4", "Qxc3", "…"],
             "source": {"engine": 6}, "extended": 2, "material": [3, -2, 3, 2, 3, 2, …],
             "ref": "x8.…", "searched": {"ref": "x11.…", "plies": 6},
             "end": {"ply": 8, "material": …, "end_score": "+2.59", "end_score_at": 6, "score_ref": "s65.…",
                     "continuation": ["…"]}},
  "game":   {"moves": ["Rxe5", "Rxe5", "dxe5", "Qxe5", "Ne4", "Bxe4", "Qxf4", "Qxc3", "…"],
             "source": {"game": 16}, "extended": 0, "material": [3, -2, 3, 2, 2, -1, 0, -1, …],
             "ref": "x9.…", "searched": {"ref": "x9.…", "plies": 16},
             "end": {"ply": 16, "material": …, "end_score": "…", "end_score_at": 16, "score_ref": "s70.…"}}},
 "searches": {"run": 3, "stored": 0},
 "units": {"material": "points_v1, White's view, the position before the move = 0",
           "score": "White's view; end_score is the search at ply end_score_at of the line"}}
```

**Sources (review B1).** `best` and `played` are the engine's own lines from the ply's analysis
record — the record `_analysed()` returns, its subject judgement's `played` and `best` lines, their
`pv` in UCI, whole (23.Rxe5's best line holds 13 plies there; the digest shows 8, `PV_PLIES`). The
digest is a view of that record and is not read. `game` is the game's moves from the ply, up to
`length`. A ply whose played move is the best has no `best` line (as the digest).

**The algorithm, per line (review B2).**

1. Play the source moves, at most `length`, through Calliope's `compare` (AG8-D §5: `_explore` with
   `by: "calliope"`), which records the material a ply.
2. One search at the end of those moves (`end_score_at` = that ply). No line gets a second search.
3. **Extension:** if a capture, a check or a promotion stands in the line's last two plies and the
   line is shorter than `length`, append moves of that search's principal variation, one at a time,
   while one of the last two plies is forcing, up to `length`. The appended plies are played through
   `compare` again (material only, no search); `extended` counts them. `end_score` stays the search
   of step 2 and says where it was taken (`end_score_at`), so a score is never shown at a position
   it was not searched at.
4. `continuation`: the next five plies of that search after the last appended one, when it has them.

**Arguments (review C3).** `ply`: an integer, 1 to the game's last ply, checked as `ply` checks it.
`length`: an integer, **1 ≤ length ≤ 32**, default 16; anything else (not an integer, a bool, out of
range) is an error naming the range, before any work. 32 plies bounds the facts tree nodes a call
adds (three lines) and keeps the answer near 3,000 characters.

**The ply's analysis (review C2).** As `ply`: `compare_lines` reads the ply's record through
`_analysed()`, which loads it from the cache or analyses the ply under the same budget and limits as
`ply` (`_load_or_analyse`), and answers `cached` as `ply` does. A refusal there (budget, an
analysis that fails) is the same error `ply` gives. RX's bases hold every fixed moment analysed, so a
run there pays nothing for it.

**Bounds and partial answers.** At most one search a line, three a call; each is admitted as
`explore`'s search (a stored search is free and counted in `searches.stored`). When the budget
cannot admit a line's search, that line answers its moves and material with `end_score: null`,
`score_ref: null` and `"search": "budget"`, the other lines as usual, and the answer carries
`budget_left`. A line that ends the game (mate, stalemate) answers `end.status` instead of a score
and is not extended. A call that cannot play any line is an error.

**Scores apart (review N2).** `root` holds the evaluations of the played and the best move at the
position before the move (the record's `evaluation`, as the digest shows them). Each line's
`end_score` is its own end position's search, at `end_score_at`. The two are never compared in one
field.

**Handles and what each proves (review C1).** A handle backs only what its kind proves
(`session._by_handle`): an `x` handle (`explored_line`) the moves and the material a ply, an `s`
handle (`search_line`) an engine score and the engine's line. So `compare_lines` answers both, and
says which backs what:

- `lines.*.ref`: the `x` handle of the whole line as answered (source moves and extension), `by:
  "calliope"`: its moves and material. A line without an extension has one `x`.
- `lines.*.searched`: the `x` handle of the moves up to the searched ply, when the line was extended
  (the position the search ran at); otherwise the same as `ref`.
- `lines.*.end.score_ref`: the `s` handle of the end search's first line (rank 1) at
  `end_score_at` — the handle `_search` serves for that search. It backs `end_score` and the
  `continuation` (an `engine_score` and an `engine_line` proposition).
- `root.played.score_ref` and `root.best.score_ref`: the `s` handles of the analysis record's
  subject lines, served by `_serve_analysis` (the digest's `lines.played.ref` and `lines.best.ref`).
- The material of a line is cited from its `x`; a score from its `s`. The tool's description says so,
  and the registry's `compare_lines` entry names the fields (§5).

**Size.** About 1,500–3,000 characters.

## 4. C — `game_overview`

Each `lines` entry: `ply`, `move`, `grade`, `score`, `loss`, and `best_move` and `label` when they have
one. `grade_ko` and `label_ko` move to one table at the top (`names`), since there are six grades and a
handful of labels. Expected: about 12,000 → 5,000 characters on a 70-ply game.

## 5. Versions and compatibility

- `TOOLS_VERSION` `agent_tools_v6` → `agent_tools_v7` (the tools' answers change);
  `tests/agent/test_commentary.py` pins it.
- `GUIDANCE_VERSION` `agent_guidance_v11` → `agent_guidance_v12` (review N1): `definitions.py`
  makes any change to the server's instructions, the tool descriptions or what `definitions` finds a
  new version. The registry's `tools` entries are updated: `explore` and `facts` (their `view`),
  `game_overview` (the `names` table), and a new entry for `compare_lines` with its fields (`root`,
  `lines.*.source`, `extended`, `end_score`, `end_score_at`, `search`). Tests pin both versions.
- The guide stays `commentary_ko_v8`. Its line on `facts` remains true (default families unchanged).
  The new tool and the views are described in the tools' own descriptions, which the server sends.
- RX: the tools' definitions are recorded with every run (the lesson sets' `versions`). A run on v7 is
  compared with runs on v7; `trial-haiku-1` (v6) is the baseline the first v7 batch is read against,
  with the version named in the report.

## 6. Tests and measurement

**Tests.** The brief filter: each keep rule of §2.1 on a fixture position, including an exchange one
attacker against one defender that loses material (rules 1–3; review B3), the `omitted` list, and
full equals today's answer. `view` validated as `ply`'s; the handle of a brief answer is the full
record; `detail` returns it; a proposition about an omitted piece is still accepted. `compare_lines`
on a fixture game: the source is the record's whole PV, longer than `PV_PLIES` (B1); the material
against `material_flow`; one search a line, `end_score_at` at the searched ply and the extension
without a search (B2); a line ending in mate; a best played move; a budget that admits no search
(partial answer, B2); `root` apart from the lines' scores (N2). Citation (C1): a commentary that
states a line's material citing its `x` and its end score citing `score_ref` is accepted by
`submit_commentary`; the same score citing only the `x` is refused; `root`'s scores citing their
`score_ref` are accepted. Arguments (C3): `length` 0, 33, a string and `true` are errors; 1 and 32
answer. Analysis (C2): an uncached ply is analysed and answers `cached: false`, a cached one `true`.
`game_overview` keys. Both versions.

**Measurement, in order:**

1. **Replay (no model).** Every `explore` and `facts` call of the RX records (luna, Haiku, the
   staged pilot) replayed through the v7 server on the same bases, in both views. Reported: the brief
   size against the full; and the pieces kept, against three sets of pieces that must be kept
   (review B3):
   - the pieces the reviewed key causes name, at their positions and at every position of the lines
     they cite (the intermediate plies, not only the end);
   - the pieces of the `board` items of the ply digests at the same positions;
   - the pieces the agents' accepted submissions cited from `pieces` records.
   Every piece of the first set is kept; any piece of the other two that is left out is listed with
   its position and read before the pilot.
2. **Pilot.** The two games of the harness pilot, the plain loop and the staged harness, two runs
   each, on v7: cost, tokens a request, turns, and whether `compare_lines` is called.
3. **Blind.** Validation, three runs a game, the plain loop on v7, judged in **one judging together
   with `trial-haiku-1`'s runs** (v6), as RX4 judged RX2's runs with its own, so the two are paired by
   moment within one judging (MH §5: levels move between judgings). The staged harness is measured in
   its own packet (§8).

**Accepted when (review B4), all of:**

- the brief `explore` is at most 8,000 characters at the median of the replay, and no piece of the
  key-cause set is lost;
- **non-inferiority**, paired by moment, v7 − v6, 90% intervals as the RX report computes them:
  M2b's lower bound at least **−0.10**; M1b's upper bound at most **+2.0** wrong sentences per 100;
- the mean cost a run at least **30% lower** than `trial-haiku-1`'s in the same report;
- no more failed runs (an end other than `done`) and no more moment-runs without commentary than
  `trial-haiku-1`'s, each reported as a count.

The margins are fixed here, before the runs. With twelve moments the M2b interval is about ±0.2
wide (MH §4), so a v7 that is truly no worse may still miss the bound; then the report says so and
the owner decides, as with RX4's promotion rule.

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

## 9. Review (rev. 1 → rev. 2)

Independent review of `4dcac6c`: NOT_READY.

| # | Finding | Disposition |
| --- | --- | --- |
| B1 (P1) | `compare_lines` named the digest's `lines.*.pv` as its source; the digest keeps 8 plies (`PV_PLIES`) of a display string | Applied (§3 Sources): the subject judgement's `played` and `best` lines of the record `_analysed()` returns, the whole UCI `pv`; the digest is not read. Checked: 23.Rxe5's best line holds 13 plies in the record. |
| B2 (P1) | Extending a line by its end search moves the end; a new end needs another search; the bound of three searches and the partial cases were undefined | Applied (§3 algorithm, bounds): one search a line at the end of its source moves; the extension plays that search's PV without searching again; `end_score_at` names the searched ply; budget refusals and game ends answer partially. |
| B3 (P1) | The keep rules count attackers and defenders, which do not decide an exchange; the pieces of an exchange may be dropped; the agent cannot ask for what it does not know was omitted | Applied (§2.1): `exchange` computed for the choice; exposed pieces, every attacker and defender of their squares, and pieces attacked by a lesser piece are kept; the answer lists each omitted piece. The replay checks the pieces of the key causes at every position of their lines, the digests' board pieces and the agents' cited pieces (§6.1). |
| B4 (P2) | "No worse than the interval" is ambiguous | Applied (§6): v7 − v6 paired by moment in one judging; non-inferiority margins fixed (M2b ≥ −0.10, M1b ≤ +2.0 per 100, 90% bounds); cost at least 30% lower; failures and moments without commentary reported. |
| N1 | Tool descriptions change `GUIDANCE_VERSION` too | Applied (§5): `agent_guidance_v12`, the registry's `tools` entries, tests pin both. |
| N2 | `end.score` could be read as the root's evaluation | Applied (§3): `root` for the move's evaluations; `end_score` with `end_score_at` per line. |

Re-review of `46371e3`: NOT_READY (B1–B4, N1, N2 resolved).

| # | Finding | Disposition |
| --- | --- | --- |
| C1 (P1) | An `x` handle backs only `explored_line` (moves, material); a score needs an `s` handle (`engine_score`), so `end_score` with only an `x` cannot be cited | Applied (§3 Handles): each line answers its `x` (`ref`, and `searched` for the searched part) and the `s` of its end search (`score_ref`); `root`'s scores carry the analysis record's `s` refs. Checked in `session._by_handle`. Tests: material cited from `x` and score from `s` accepted, score from `x` alone refused. |
| C2 (P2) | "Refused as `ply` refuses" did not match `ply`, which analyses an uncached ply | Applied (§3 analysis): as `ply`, through `_analysed()`, analysing under its budget and limits, answering `cached`. |
| C3 (P2) | `length` had no range | Applied (§3 Arguments): an integer, 1–32, default 16; others an error before any work. |

Second re-review of `3fb7d33`: READY_FOR_MERGE (2026-11-07).
