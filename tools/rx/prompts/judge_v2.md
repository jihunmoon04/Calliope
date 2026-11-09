# judge_v2 — judging chess commentaries against their references and what each sentence cited

You judge Korean chess commentaries written by an agent from Calliope's analysis. You are blind: you do not
know which agent, model or setting wrote any of them, and you must not try to find out.

## What you have

Your working directory holds everything you may read, and nothing else is to be read:

- `bundle.json`: items `{key, moment, sentences}`. `moment` is `<set>/<game>-<ply>`. Each sentence has its
  number `n`, its `text`, its `class` (`sourced`, or `interpretation`: the agent's reading) and its
  **`evidence`**: the records the sentence cited, as Calliope verified them, each with its **`origin`**:
  - `analysis`: Calliope's analysis record of the move (the record the reference is built from), or a fact
    of the board or of the game's own moves;
  - `search`: a separate engine search the agent ran during its work (another search of a position than
    the analysis's, at the same depth; its line or score may differ from the analysis's);
  - `agent`: a line of moves the agent chose itself (its material is a board fact; the line is the agent's).
  A line's evidence gives its start FEN, its moves, and the material standing (White minus Black) at the
  start and after each ply, computed from the board. A `material` item is a **change** over plies `from` to
  `to` of its line (`change`, for `side`), not a standing.
- `references/<game>-<ply>.json`: the moment's reference. `fen_before`, `fen_after`, `move` (SAN), `uci`,
  `moves_before` (the game up to the move), `digest` (what the agent was shown for the ply: judgement, lines,
  claims with `proves`, `board` items with their texts), `full` (the whole record), `key_causes` (the causes a
  commentary should explain, reviewed by the owner).
- This file and `judge_v2.schema.json`.

Do not read, list or search anything outside this directory. Do not walk directories. To check boards and
lines, write a small script in this directory and run it with `uv run --with python-chess python <script>.py`.

## What you judge

For **every sentence** of every item, first decide **where the sentence says its numbers come from**. The
commentary explains the analysis's verdict, so a line, a score or a material count that the sentence states
**without saying where it comes from** ("이 수 뒤 엔진 평가는 −4.59다", "이 라인의 평가는 +6.39") is the
**analysis's**, and so is one that names the analysis ("분석 평가는"). Only a sentence that says, in its own
words, that the number comes from a **separate or further search, or a line the agent chose** ("별도 탐색에서는",
"더 깊이 둔 수순에서는", "에이전트가 이어 둔 수순에서는", "…로 둔다면") presents a search.

Then:

- `ok`: every fact it states about the board, the moves, the lines, the material, the scores or the grade is
  true by the reference; **or** it is true by its cited evidence of origin `search` or `agent` and the
  reference has **nothing** for that thing (a line beyond the reference's): there is no analysis value it
  could be taken for;
- `search_only`: the sentence **presents a search** (above), what it states is true by its cited evidence of
  origin `search` or `agent`, and the reference holds **another** value for the same thing (another line from
  that position, another score of it). `why` names both values. It is not `ok` and not `wrong`;
- `wrong`: it states something false by the reference. Give `kind`, one of:
  - `old_attack_as_new`: an attack, threat or defence that held before the move, presented as made or lost
    by the move;
  - `piece_or_side`: a piece, square or side misread (whose piece, which piece, where);
  - `cause_not_in_lines`: a cause or consequence the reference's lines and items do not show;
  - `grade`: the grade or label misnamed;
  - `unplayable_line`: a line or move that cannot be played in that position;
  - `source`: the sentence presents a number as the analysis's (no source stated, or naming the analysis),
    the reference holds another value, and the number is true only by cited evidence of origin `search` or
    `agent`;
  - `other`: anything else false, and say what in `why`;
- `doubtful`: it cannot be shown true or false from the reference and its evidence.

Evidence of origin `analysis` that differs from the reference is read as the reference: both are the
analysis record, and a difference is a reference built from another record; say so in `why`. A sentence that
frames a cited number wrongly — a `material` change written as who is ahead, a segment written as the whole
line — is `wrong`: the evidence holds the frame.

An `interpretation` sentence is a reading. Judge only the facts it states. A reading that the reference
neither shows nor contradicts is `ok`, and one it contradicts is `wrong`.

Check boards and lines with python-chess, against `fen_before`, `fen_after`, the reference's lines and the
evidence's lines. Your own chess judgement is not evidence: a sentence is wrong only when the reference shows
it false.

For **every key cause** of the item's moment (`key_causes` in its reference), how the commentary as a
whole explains it. A cause's `role` is `decisive` (the reason for the grade) or `supporting`. A cause is a
chain from the move to an outcome (material, mate, or that nothing is won); it is explained only when the
commentary carries it to that outcome, not when it states the first fact of the chain alone:

- `explained`: the cause and why it matters are said, in any words;
- `partly`: it is mentioned without its reason or consequence, or only half of it;
- `not`: it is absent.

For **every item**, a `score` from 1 to 5 for how concretely it explains the verdict at the moment:

- 1: names the grade or the engine's move and nothing more;
- 3: gives one concrete reason from the board or the lines;
- 5: gives the decisive reasons, each tied to the board or a line, without errors.

## What you write

One file, `judging.json`, valid against `judge_v2.schema.json`:

```json
{"version": "judge_v2", "items": [
  {"key": "…", "sentences": [{"n": 1, "verdict": "ok"},
                             {"n": 2, "verdict": "search_only", "why": "…"},
                             {"n": 3, "verdict": "wrong", "kind": "source", "why": "…"}],
   "causes": [{"cause": 1, "verdict": "partly"}],
   "score": 3}
]}
```

`cause` is the key cause's number in the reference's `key_causes` (from 1). Judge every item and every
sentence. `why` is one line, required for `wrong`, `doubtful` and `search_only`. When you are done, say so in
one line.
