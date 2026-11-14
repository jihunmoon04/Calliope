# Wrong sentences of revs. 14–18 by cause (input to harness rev. 19)

Source: every sentence judged `wrong` or `doubtful` in the eleven judgings 94d6ca40, d5ea37e0,
1fc68379, 01b80a7b, 8504e6b3, cc72e6ed, e7e21545, ff09b62d, 80ab90d8, 24a11530, f34a7bba
(`rx-judging/<id>/partNN/judging.json` with the part's `bundle.json`): 59 sentences. Each was read
with the judge's reason and the sentence's cited evidence, and put in one class.

| class | what went wrong | n | share |
| --- | --- | --- | --- |
| A1 | standing and change mixed up, or a line's end value misstated (cited `explored_line`/`material` holds the right numbers) | 12 | 20% |
| A2 | a board item read at the wrong time (before vs after the move, after a recapture) or a defender count misread | 9 | 15% |
| A3 | a relation that held before the move written as made or removed by it (cited `exposed`/`attack` says held) | 7 | 12% |
| A4 | score order or sign misread (lower is better for Black) | 2 | 3% |
| A5 | the agent's own segment written as the analysis line, or the line cut before a recapture | 3 | 5% |
| A6 | side or piece swapped (subject, square, who gives up what) | 4 | 7% |
| B | a mechanism or decisive cause not in the data (an invented pin, "forced", "cannot compare by material") | 16 | 27% |
| C | an unsupported addition (a blockade, "keeps the king safer", next scene) | 6 | 10% |

**A (37 of 59, 63%)**: the fact the sentence needed was already in its own cited evidence, in
structured form, and the sentence restated it wrongly. Checks pass because the claim cited is right;
the words around it are not read (frame check rules read only fixed frames).

**B (16, 27%)** is concentrated: the 29...a5 "pin makes a5's defence void" story appears in 5
sentences over 3 judgings; "6...c5 removed b5's defence" (A3) in 4 judgings. They recur across runs
of the same moment at roughly a third of the runs, so they are frequent but not certain per sample:
a 3-sample majority would cut such a cause error from about 0.36 to about 0.30, a small effect.

## What it implies for rev. 19

1. The largest class (A) is a rewriting error, not a reasoning error. A writing turn that sees the
   checked items as code-rendered text — standing and change both named, the time of every board
   item named, "held since" written out — and not the raw tool output targets A1–A3 and A5.
2. Majority voting on the decisive cause targets B but is expected to help little, because the
   wrong causes recur across samples. It is trialled, and kept only if the measured gain shows.
