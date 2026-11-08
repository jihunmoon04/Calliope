# Agent LT-D — line tools for the reasoning the agent does by hand, and a harness that checks against them

Status: rev. 1, for independent review. Scope: the agent's MCP tools (`src/calliope/agent`:
`explore`, `compare_lines`, a new `squares`) and the staged harness of the RX runner
(`tools/rx/harness.py`, its prompts). Not in scope: the guide (`commentary_ko_v8`, frozen for RX),
`submit_commentary`'s checks, HIMARI.

## 0. Why

HS rev. 4 (`agent-hs-implementation.md` §10) measured the staged harness H against arm A on the
evaluation sample a second time, with the faults of §8 fixed. H did what it was built for — the
decisive cause explained, pooled M2b **+0.235 (+0.059 … +0.426)**, both sets up, no commentary
missing, a quarter cheaper — and was **not adopted** on one bar: M1b's upper bound **+5.69** wrong
sentences per 100, above +2.0. H wrote 23 wrong sentences against A's 11, and 28 doubtful against 3.

### 0.1 Where H goes deep, and how

H's tool calls over its 18 runs (`rx-evidence/hs2/batch-hs-eval-2.jsonl`, the runs' `tools.jsonl`):

| Tool | Calls | How |
| --- | --- | --- |
| `explore` | **105** | Every call a line the agent **typed itself** — mostly an engine line copied from a digest or a search, 2–9 moves, `search: true`, the brief view (e.g. `["Rb1","Bxc5","a3","Qa5","d4","Be7"]`). |
| `facts` | 28 | The position's families. |
| `detail` | 17 | A record behind a handle. |
| `judge_move` | 9 | A candidate move's judgement. |
| `compare_lines` | **7** | The played, best and game lines only. |

A barely explores: it reads `ply` digests (9–18 a run). What `explore` answers per ply is the move
(its `events`) and `material_balance_white`; at the end, a search in White's view. From that the
agent works out **by hand**: who took what from whom, who is ahead at the end and by how much,
which of two candidate moves is better for the side that played it, and — from the relation
changes the digest and the brief views list — what still defends a piece.

### 0.2 Where the wrong sentences come from

H's 14 wrong sentences on **Train** (the design reads Train; Validation's 9 are the check, §6 —
they were read once for the §10 write-up, and fall into the same rows):

| What the agent worked out by hand | Train | Examples (judge's reason, abridged) |
| --- | --- | --- |
| **Relations: what attacks or defends a square, and what a move changed** | 7 | `rapid-52` (two runs): "after 26...Re8 only the king defends f7" — the d6 knight does too; the tools gave the change (f8 stopped defending f7), not what remained. `fourth-37`: "d4 has no defender" — two. `rapid-40`: "the d6 knight is undefended" — the queen. `fresh-62`: an attack on d5 as new — it stood since 30.e4. `fourth-38`: "f5 hits the queen" on d7 — it does not. `fresh-56`: "the queen could take g4" — only the f5 pawn could. |
| **A line's outcome: captures by side, material at the end, the end position** | 3 | `fresh-76`: the two h-pawns counted as Black's losses — Black took them. `fourth-56`: the bishop on g3 at the end — it is back on d6; scores −3.95 and −7.54 not the line's (−5.09). |
| **Lines compared: which candidate is better for the mover, what an alternative changes** | 3 | `rapid-52`: the 1-point loss of the best line given to the played one (which ends in mate). `rapid-54`: "no move avoided mate" — 27...Kxf7 does (+7.24). `rapid-54`: "after 27...Kxf7 the king escapes" — the line shows a plain recapture. |
| The grade's name | 1 | `rapid-52`: a blunder called a mistake. |

Validation adds two of the comparison row that are a **sign misread**: at 185371835722 ply 32,
17.Qxe3 (−7.59, White's view) was called White's best over 17.Qe1 (−6.79). The 28 doubtful
sentences are, all but a few, end scores and lines of the agent's own exploration that the
references do not hold — depth beyond the reference, not shown wrong.

**The harness let them through.** Rubric v2 checks the reply against itself (HS-D §3: "not that
the facts are true"). At 185371835722 ply 30 a wrong decisive cause passed at once; at ply 32 the
judge rightly refused a cause, and the retry "fixed" it with the sign misread above, which passed.
`submit_commentary` checks the propositions a sentence cites, not the inference a sentence draws
from them: "f8 defended f7 before the move" is a true proposition under a false sentence.

### 0.3 Why this direction

| Option | Against it |
| --- | --- |
| Drop or forbid what cannot be checked (end scores, alternatives) | The depth is where H's gain comes from: the decisive cause is a line's outcome. It would trade M2b for M1b. |
| Send H back to the digests (A's way) | The same: A explains the decisive cause less (−0.24 pooled). |
| A stronger judge model | It still has nothing to check against but the agent's own text; and it measures the judge, not the harness (HS-D §7 Q2). |
| **Tools that do the hand work, and a harness that checks claims against their records** | **Chosen.** Every row of §0.2 is a computation over data the server already holds: the captures by side, the net material for each side, the candidates ranked for the mover, the full attackers and defenders before and after a move. Done by the tool, it is correct by construction, and a claim that cites it can be checked by code — not by a model reading the agent's text. |

The owner's earlier rule applies: a tool change is a change of **information**, not of the harness,
and is measured apart (§6: A on the new tools as well as H).

## 1. The change

| Part | What |
| --- | --- |
| T1 | `explore` answers a **line ledger**: each ply in words of who moved what and took what, the captures by side, the net material for each side and for the line's first mover, the end position's pieces that changed, the end score with the side it favours. Optional `continue: "engine"` plays the engine's line on from the agent's moves. |
| T2 | `compare_lines` takes **`candidates`**: up to four moves at the position before the ply, each played out with the engine's replies, **ranked for the side to move**, each with its ledger outcome and its difference from the played move. |
| T3 | A tool **`squares(game, position, squares)`**: for each square, its piece and **all** its attackers and defenders by name; at a ply's position after the move, also what the move changed and what stayed. |
| T4 | Every score a new field gives carries the side it favours and a value **for the mover**; White's view stays beside it. |
| H1 | The facts stage writes its facts as a **JSON block** of typed claims, each citing a handle. |
| H2 | A **check by code** (the checker) before the judge: each typed claim against the record its handle serves. A claim that disagrees goes back with the record's value. |
| H3 | **Rubric v3**: the judge reads, beside the reply, the records the reply cites (their ledger and relations), and fails a cause that contradicts them or rests on a line, score or relation no record backs. |
| H4 | **Retry message**: call the tool again and correct from its record; a correction cites the record. |

## 2. T1 — the line ledger of `explore`

Added to every `explore` answer (both views), from records the line already builds (`material_flow`,
the `move` facts, the end position):

An illustration (a rook trade):

```json
"ledger": {
  "plies": [
    {"ply": 1, "san": "70.Rxf6", "says": "White's rook f7→f6 takes Black's rook (5)", "by": "white",
     "captured": {"piece": "rook", "owner": "black", "square": "f6", "points": 5}, "check": false},
    {"ply": 2, "san": "70...Kxf6", "says": "Black's king g7→f6 takes White's rook (5)", "by": "black",
     "captured": {"piece": "rook", "owner": "white", "square": "f6", "points": 5}, "check": false}
  ],
  "captured": {"by_white": ["rook f6 (5)"], "by_black": ["rook f6 (5)"]},
  "net": {"white": 0, "black": 0, "first_mover": "white", "for_first_mover": 0},
  "end": {"moved_pieces": ["Kf6"], "gone": ["Rf6 (white)", "rf6 (black)"], "status": "normal"},
  "end_score": {"white_view": "+0.00", "for_side_to_move": "+0.00", "favours": "neither",
                "score_ref": "s41.…"}
}
```

- `says` is built from the move facts (piece, colour, from, to, captured piece and its owner, check,
  promotion, castling) in a fixed English template; the agent writes Korean from it.
- `net` counts `points_v1` from the line's start: **per side**, and for the side that made the
  line's first move. It equals `material_balance_white` at the end (White) and its negation
  (Black); a test pins that.
- `end.gone` and `end.moved_pieces` name the pieces whose square changed or that left the board,
  so "where is the bishop at the end" is read, not tracked.
- `end_score` only with `search: true`, from the search the answer already makes; `favours` is the
  side the score is good for (`neither` within ±0.30, the digest's draw band — §7 Q3).
- **`continue: "engine"`** (optional; default none): after the agent's moves, play the end search's
  principal variation on, up to `length` (default 8, at most 16) plies **without another search**
  (as `compare_lines`' extension, TO-D §3 B2), so the line's end is the engine's, not a copy. The
  appended plies are marked `by: "engine"` in the ledger; `end_score` stays the search at the
  agent's last move and says so (`end_score_at`). Needs `search: true`.

**Handles.** The `x` handle's record holds the ledger; a proposition of kind `explored_line`
backs its moves and material as today. Nothing new is citable in `submit_commentary`; the ledger is
for the agent's reasoning and the harness's checks (H2).

**Size.** About 90 characters a ply, 150 for `captured`/`net`/`end`: an 8-ply line adds about
900 characters to a brief answer of about 5,400.

## 3. T2 — candidates in `compare_lines`

`compare_lines(game, ply, length=16, candidates=None)`. With `candidates` — 1 to 4 moves (SAN or
UCI) legal at the position before the ply:

- Each candidate is a line: the candidate, then the engine's line from **one search** after it,
  played to `length` (the extension of TO-D §3 B2 applies). The played and the best lines stay as
  today; a candidate equal to either is not repeated.
- **`ranking`**: every line of the answer (best, played, candidates) ordered **for the side to
  move**, each with `for_mover` (the score from that side's view: higher is better for it),
  `white_view`, the `score_ref`, and `vs_played` (the difference for the mover; `+` = better than
  the move played). The root scores of best and played are the analysis record's (as `root` today);
  a candidate's is its search's score at the position after it, negated into the mover's view, and
  says so (`at: "after the candidate, depth N"`).
- Each line carries its T1 `ledger` outcome (`captured`, `net`, `end`), not the per-ply list (the
  `x` handle has it).
- **Handle.** The answer is served under a new handle kind **`k`** (`comparison`, `handles.KINDS`),
  so `detail(k…)` returns it and the harness's checker can read its ranking (§5.2). A `k` handle is
  **not** citable in `submit_commentary` (no proposition kind reads it); the lines' `x` and `s`
  handles stay what a commentary cites (TO-D §3 C1).
- **Bounds:** one search a candidate, admitted as `explore`'s; a candidate the budget cannot search
  answers its moves only, `search: "budget"`. Four candidates and three lines stay within
  `COMPARE_MAX` per line.

This answers "would 27...Kxf7 have avoided mate", "is 17.Qe1 or 17.Qxe3 better for White" and
"which line holds the 1-point loss" from one record, with the sign already turned.

**Not in T2:** a candidate followed by a reply the agent chooses ("the same 28.Rxe8 after
27...Kxf7"). The engine's reply is the fair comparison; a forced reply is `explore` with the moves
typed, whose ledger (T1) now gives its outcome.

## 4. T3 — `squares`

`squares(game, position, squares, view="brief")`, `squares` 1 to 8 square names. For each square:

```json
{"square": "f7", "piece": "pf7", "attackers": ["Bd5"], "defenders": ["Kg8", "Nd6"],
 "exchange": {"first": "white", "gain": 0},
 "changed_by_move": {"lost": ["Rf8 (defender)"], "gained": [], "kept": ["Kg8", "Nd6"]}}
```

- Attackers and defenders are **all** of them, by name (as the brief entries name pieces, TO-D
  §2.1 A2), from the `pieces` family's record of that square's piece; an empty square lists the
  pieces attacking it by side. `exchange` is the `exchange` family's record when the square holds a
  piece.
- `changed_by_move` only when `position` is a ply's position **after** its move: the same lists at
  the position before, compared — what the move removed, added, and left. "Only the king defends
  f7" then has `kept: ["Kg8", "Nd6"]` beside it.
- **Handle:** an `f` handle per position, as `facts`; a `defence` or `attack` proposition cites it
  as today. No search.
- **Size:** about 150 characters a square.

## 5. The harness, rev. 5

### 5.1 H1 — typed claims

The facts stage's message (`harness_v3.md`) asks, besides the facts and the cause in prose, for a
JSON block at the end of the reply:

```json
{"claims": [
  {"kind": "line_net", "ref": "x12.…", "side": "black", "value": -5},
  {"kind": "line_capture", "ref": "x12.…", "by": "white", "piece": "rook", "square": "f6"},
  {"kind": "defenders", "ref": "f15.…", "square": "f7", "value": ["Kg8", "Nd6"]},
  {"kind": "better_for_mover", "ref": "k3.…", "move": "Qe1", "than": "Qxe3"},
  {"kind": "score", "ref": "s41.…", "favours": "black"},
  {"kind": "piece_at_end", "ref": "x12.…", "piece": "bishop", "side": "black", "square": "d6"}
]}
```

Six kinds, each matching a field of T1–T3 (`line_net`, `line_capture`, `piece_at_end` → a ledger;
`defenders`/`attackers` → `squares`; `better_for_mover` → a `compare_lines` ranking, its `k` handle; `score` → a
search line). Every claim of the decisive cause about a line's material, a capture, a defence, a
comparison or a score is to be one of them; the guide's form for the commentary is unchanged.

### 5.2 H2 — the checker

Code in `tools/rx/harness.py`, between the facts stage and the judge. For each claim it reads the
record behind `ref` through the session's `detail` (a harness call: logged as `harness_detail`,
not counted as the agent's tool call and not shown to it) and compares the field:

- **agrees** → kept; **disagrees** → a problem with the record's value ("x12 says Black's net is
  0, not −5"); **no such record or field** (an unknown handle, a ledger without that capture) → a
  problem "no record backs this";
- a reply **without a claims block**, or with a cause whose line, defence or comparison has no
  claim, → one problem ("state the cause's claims with their records").

Problems from the checker send the moment back as the judge's do (they share the two retries). The
checker's verdict is logged (`harness`, `stage: "check"`, the claims and their results). It never
sees the references.

### 5.3 H3 — rubric v3

`harness_judge_v2.md`: rubric v2's four failures, and two more:

5. **Against the records:** the cause or a fact contradicts a record the reply cites (the judge's
   input holds those records' ledger outcomes, `squares` entries and rankings, shortened: at most
   about 2,500 characters);
6. **A claim with no record:** a line's material, a capture, a defence or a comparison the cause
   relies on that no cited record holds.

The judge still never sees the key causes. The rubric's line "you do not check that the facts are
true" becomes "check them only against the records given".

### 5.4 H4 — the retry message

"The check found: … — call the tool again for the record and correct from it; each corrected claim
cites its record." No better wording, never a move to try (as rubric v2).

### 5.5 Versions

- `TOOLS_VERSION` `agent_tools_v7` → **`agent_tools_v8`**; `GUIDANCE_VERSION` `agent_guidance_v12` →
  **`agent_guidance_v13`** (the tool descriptions and the registry's entries for `explore`,
  `compare_lines`, `squares`). The guide stays `commentary_ko_v8`.
- `HARNESS_VERSION` **`harness_v3`**, `JUDGE_VERSION` **`harness_judge_v2`**; `harness_v2.md` and
  `harness_judge_v1.md` stay for the runs that used them.

## 6. Tests and measurement

**Tests.** T1: the ledger on a fixture line with captures by both sides, a promotion, castling and
a check; `net` against `material_flow`'s balance (White, and negated for Black); `end.gone`;
`continue: "engine"` plays the PV without a second search and marks the plies; `favours` at the
band's edges. T2: candidates ranked for Black at a Black move (the sign); a candidate equal to the
best not repeated; a budget that admits no candidate search; an illegal candidate an error naming
it. T3: all defenders (a square defended by king and knight after the rook leaves: `kept` lists
both); an empty square; `changed_by_move` only after a move. H2: each claim kind agreeing,
disagreeing and unbacked on a scripted session; a reply without a block; the checker's problems
share the retries; `harness_detail` calls not in the agent's counts. H3: the judge's input holds the
cited records and no reference text. Both versions pinned.

**Measurement, in order:**

1. **Replay (no model).** For each of Train's 14 wrong sentences of §0.2, the position and line the
   agent was reasoning about, put to T1–T3: does a field of the answer **state the correct fact**
   (e.g. `rapid-52`: `squares` f7 `kept` holds `Nd6`; `fresh-76`: `captured.by_black` holds both
   h-pawns; `rapid-54`: the ranking puts 27...Kxf7 above the played move with no mate)? Reported
   case by case; the grade's name (one case) is outside T1–T3 and said so. Then Validation's 9, as
   the check. **Bar:** 13 of the 13 tool-shaped Train cases, and the Validation cases reported.
2. **Pilot.** The development sample (Validation 184800218248 and 185264271324), H rev. 5 on v8,
   two runs a game: whether the claims block is written, the checker's verdicts, retries, cost.
3. **Blind.** Three arms, three runs a game, the shared bounds (HS-D §4): **A on v7** (today's
   default), **A on v8** (the tools alone), **H rev. 5 on v8**. One judging, `judge_v1`, audited;
   paired by moment, 90%. H rev. 5 − A v7 is the adoption comparison; A v8 − A v7 separates what the
   tools do from what the harness does.

**Where (§7 Q1).** The evaluation sample has been looked at twice and Train's errors shaped this
design; it is the development data now. The blind measurement's moments are the **Test set** (four
games, 12 moments), its key causes reviewed by the owner first, as RX2's were.

**Adopted when**, read from `H rev. 5 − A v7 / pooled`: the HS-D §6 bars unchanged — **M2b +0.10
or more with the interval above zero; no set below −0.10; M1b's upper bound at most +2.0; failures
and moment-runs without commentary no more than A's; the worst case holds.** Also reported: A v8 −
A v7 on the same bars; the checker's verdicts and their share of retries; doubtful sentences per
arm; cost and the judge's and checker's share.

## 7. Questions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Measure on the Test set? | Yes: the evaluation sample shaped the design; Test is the only untouched sample. Its four games' key causes need the owner's review before the batch. |
| Q2 | Typed claims (H1) instead of having the checker read the prose? | Yes: a parser of Korean prose would be a model; typed claims make the check exact and cheap. The prose stays the agent's. |
| Q3 | `favours`' draw band ±0.30 | As the digest's; one constant. |
| Q4 | The new tools for arm A too (A v8)? | Yes, as a third arm: the tools are information and may help A alone; without it a gain cannot be split between tools and harness. |
| Q5 | `continue: "engine"` default off? | Off: the plain loop's `explore` answers stay as they are unless asked; the harness's message names it. |

## 8. Not in this packet

- The checker for the plain loop (arm A): `submit_commentary`'s checks of sentences' inferences are
  a server change of their own.
- One conversation a moment (HS-D §8).
- Korean syllables garbled by Haiku (`agent-mh-implementation.md` §5).
