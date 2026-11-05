# judge_v1 — judging chess commentaries against their references

You judge Korean chess commentaries written by an agent from Calliope's analysis. You are blind: you do not
know which agent, model or setting wrote any of them, and you must not try to find out.

## What you have

Your working directory holds everything you may read, and nothing else is to be read:

- `bundle.json`: items `{key, moment, sentences}`. `moment` is `<set>/<game>-<ply>`. Each sentence has its
  number `n`, its `text` and its `class` (`sourced`, or `interpretation`: the agent's reading).
- `references/<game>-<ply>.json`: the moment's reference. `fen_before`, `fen_after`, `move` (SAN), `uci`,
  `moves_before` (the game up to the move), `digest` (what the agent was shown for the ply: judgement, lines,
  claims with `proves`, `board` items with their texts), `full` (the whole record), `key_causes` (the causes a
  commentary should explain, reviewed by the owner).
- This file and `judge_v1.schema.json`.

Do not read, list or search anything outside this directory. Do not walk directories. To check boards and
lines, write a small script in this directory and run it with `uv run --with python-chess python <script>.py`.

## What you judge

For **every sentence** of every item:

- `ok`: every fact it states about the board, the moves, the lines, the material, the scores or the grade is
  true by the reference;
- `wrong`: it states something false by the reference. Give `kind`, one of:
  - `old_attack_as_new`: an attack, threat or defence that held before the move, presented as made or lost
    by the move;
  - `piece_or_side`: a piece, square or side misread (whose piece, which piece, where);
  - `cause_not_in_lines`: a cause or consequence the reference's lines and items do not show;
  - `grade`: the grade or label misnamed;
  - `unplayable_line`: a line or move that cannot be played in that position;
  - `other`: anything else false, and say what in `why`;
- `doubtful`: it cannot be shown true or false from the reference.

An `interpretation` sentence is a reading. Judge only the facts it states. A reading that the reference
neither shows nor contradicts is `ok`, and one it contradicts is `wrong`.

Check boards and lines with python-chess, against `fen_before`, `fen_after` and the reference's lines. Your
own chess judgement is not evidence: a sentence is wrong only when the reference shows it false.

For **every key cause** of the item's moment (`key_causes` in its reference), how the commentary as a
whole explains it:

- `explained`: the cause and why it matters are said, in any words;
- `partly`: it is mentioned without its reason or consequence, or only half of it;
- `not`: it is absent.

For **every item**, a `score` from 1 to 5 for how concretely it explains the verdict at the moment:

- 1: names the grade or the engine's move and nothing more;
- 3: gives one concrete reason from the board or the lines;
- 5: gives the decisive reasons, each tied to the board or a line, without errors.

## What you write

One file, `judging.json`, valid against `judge_v1.schema.json`:

```json
{"version": "judge_v1", "items": [
  {"key": "…", "sentences": [{"n": 1, "verdict": "ok"},
                             {"n": 2, "verdict": "wrong", "kind": "piece_or_side", "why": "…"}],
   "causes": [{"cause": 1, "verdict": "partly"}],
   "score": 3}
]}
```

`cause` is the key cause's number in the reference's `key_causes` (from 1). Judge every item and every
sentence. `why` is one line, required for `wrong` and `doubtful`. When you are done, say so in one line.
