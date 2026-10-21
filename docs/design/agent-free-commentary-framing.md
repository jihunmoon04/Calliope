# Agent — free commentary with evidence: the question and a trial (FR framing)

Status: **framing, rev. 2, for the owner. No design decision and nothing to implement. The trial is in §3; rev. 2 adds the arm `min` (§3.4).** Date: 2026-10-20. Base: `main @ 40f3e54` (LM merged).
Owner's question (2026-10-20): "해설이 너무 유형에 제약되어있다는 느낌을 받는데 자유롭게 해설하되 근거만
붙이도록 하면 안되는건가? 혹은 해설을 더욱 풍성하게 만들 방법이 뭐가 있을까". The commentary feels bound to
types. Could the agent write freely and only attach evidence? What else would make it richer?
Inputs: [`agent-commentary-path.md`](agent-commentary-path.md) (AG8 framing: F1–F6, the D1/D2 trial),
[`agent-pw-design.md`](agent-pw-design.md) §0.3 (the trial without `proves`),
[`agent-lm-design.md`](agent-lm-design.md) and [`agent-lm-implementation.md`](agent-lm-implementation.md) §4
(`commentary_ko_v7`, LM3's runs, used here as the baseline).

## 1. Where the types come from

The check (S1–S6, AG-D §5.3) already allows free text. It reads only the moves, scores, squares and
numbers of a sentence against what the sentence cites. It does not check the wording or the order. The
typed feel comes from four other places:

| Source | What it does |
| --- | --- |
| `commentary_ko_v7`'s method | "아래 표에서 이 장면에 맞는 유형을 2~4개 고르세요" — a table of 12 types; "핵심 장면에서는 유형 1·3·6·8 중 하나"; "좋은 해설은" 1–3 |
| The reading notes (AG8-D §6.4) | N-reason, N-reading after each accepted submission: cite a reason, an interpretation needs a reason or a result |
| One check a sentence | sentences that join scenes or read a flow become interpretations, with "~로 보인다" |
| The data and the model | AG8 F6: the digest sets the shape; luna sets the ceiling |

LM3's commentaries (v7, luna) show the shape. 94% open with the move's name, 78% say the grade in the first
sentence, and 28% of interpretations end in "~것으로 보입니다". A typical commentary reads: "8.cxd4는 부정확 판정으로, 엔진의 첫 선택은
8.O-O였습니다. … 먼저 캐슬링하고 나서 되잡는 순서가 더 안정적이었던 것으로 보입니다."

## 2. Arms

These are scratch copies of `main @ 40f3e54`, never `main`:

- **v7**: `main` as merged. Its runs are LM3's eight luna runs (LM implementation §4, 2026-10-19).
  `main`'s `src/` differs from LM3's tree by one comment.
- **free**: the guide's method replaced; the check is unchanged. It differs from v7 in these ways:
  - the 12-type table, "유형 2~4개", "핵심 장면에서는 유형 1·3·6·8" and the "좋은 해설은" rules 1–2 are gone;
  - in their place: write the scene's story; avoid the same frame each scene (grade → engine's move →
    line → "더 나았던 것으로 보입니다"); the grade need not open; vary openings; join scenes;
  - an interpretation needs no "~로 보인다" (the viewer marks it as the commentator's). Forcedness words
    stay forbidden;
  - one worked example, a bad and a good version of the same scene;
  - the materials listed as a list instead of a table;
  - kept: the notation rules, the evidence strengths, whose piece, the length advice, submission;
  - the reading notes are off (`_notes` returns none).
- **rich**: free, plus material (AG8 gap 1). Each new item verifies like any board item, through two new
  proposition kinds in the scratch copy, `pawn` and `file`, which read `pawns_v1`:
  - `board` items `structure`: a pawn that became passed, isolated, doubled or backward with the move.
    The pawn's flag is false before (at its square before) and true after;
  - `board` items `file`: a file whose pawn state changed (open, semi-open, closed);
  - the digest's other candidates as `others`, each with its engine line (6 plies, numbered). They are
    cited by their `s` handles, which the session already served.

The rich guide adds two paragraphs on these items.

- **min** (rev. 2, the owner's follow-up, 2026-10-20: "기본적인 해당 수가 왜 좋은지, 안좋은지 해설하고, 도구의
  사용방법만 알려주고 문장을 만들어서 근거를 붙이라고 해봐. 이외의 제약은 포함하지 말고"). free's tree with a guide
  that holds only:
  - the task, one line: explain why the move is good or not good, write sentences, attach evidence to each;
  - the tools, the data's fields (what `lines`, `board` kinds, `proves`, `part`, claims' `status` are), the handles,
    how to build a proposition;
  - the submission's format and what the check refuses (S1–S8 and the judgement, stated as what the server checks).

  Gone besides free's removals: the story, frame and opening advice, the worked example, the evidence strengths,
  forcedness words, the length advice, the notation advice beyond what the check reads, the terms, the claim
  readings, and the server instructions' length and "꼭 지킬 것" lines. `check_ko` points to the guide's check
  section. The notes stay off. It ran twice:
  - **min0**: the server instructions only said where the guide is. Six of eight runs did not read it;
  - **min**: the instructions say to read it before writing, as `main`'s do. All eight read it.

Runs: PW's setup (HIMARI v3, one conversation a run, the four games, the warm analyses of LM's trial,
the same prompt). luna ×2 a game an arm: 16 new runs, about $0.26; min0 and min 16 more, about $0.14.

## 3. The trial (2026-10-20)

### 3.1 Means a run (luna, 8 runs an arm)

| | v7 | free | rich |
| --- | ---: | ---: | ---: |
| Plies commented | 11.9 | 12.0 | 12.1 |
| Sentences | 52.4 | 53.4 | 49.6 |
| … at a fixed moment | 4.9 | 5.1 | 4.7 |
| Sentences citing a reason | 29.2 | 21.2 | 21.2 |
| Interpretations | 12.4 | 12.5 | 13.2 |
| Commentaries opening with the move's name | 94% | 33% | 49% |
| … with the grade in the first sentence | 78% | 39% | 52% |
| Interpretations ending in "보입니다/보인다" | 28% | 0% | 0% |
| Sentences citing a `structure`/`file` item | — | — | 0.9 |
| Sentences citing a line the agent played (`explore`) | 0 | 0 | 0 |
| Refused submissions | 4.9 | 5.3 | 4.5 |
| Cost | $0.017 | $0.017 | $0.015 |
| Seconds | 200 | 266 | 221 |

A reason means a reason claim, a board item, a position proposition, an `after_reply` or an explored line,
as in LM's trial.

### 3.2 Wrong sentences at the fixed moments (blind)

The fixed moments are the twelve of PW's and LM's trials. All three arms' commentaries there (72) were shuffled
without their arm. A fresh-context judge read them against each moment's reference: FENs, lines, other
candidates, board items, the same reply, claims and the PGNs. It checked the board with python-chess and scored
each commentary 1–5 for how concretely it explains the verdict.

| | v7 | free | rich |
| --- | ---: | ---: | ---: |
| Sentences | 117 | 122 | 113 |
| Wrong | 2 | 5 | 0 |
| … per 100 | 1.7 | 4.1 | 0 |
| Doubtful | 3 | 1 | 2 |
| Mean score (1–5) | 2.75 | 2.42 | 2.54 |

- v7's two errors are the same two that LM implementation §4 counted by hand, not blind: "실제로 이어진
  8.Qxe2 뒤 … e2의 흑 비숍", and a same reply after 20...Qd6 that cannot be played.
- free's five, in three commentaries:
  - one commentary at 19...Kh8 has three: a cause the lines do not show ("흑이 나이트를 먼저 제거하지 않아
    백은 d7 나이트를 잡을 기회를 얻었다"; 20.Qxd7 follows the best move too), White's queen read as Black's
    problem, and the grade misnamed;
  - "35.Bxb6까지 백은 흑 룩을 잡습니다" (it takes a bishop);
  - an interpretation at 7...Bxe2, "체크를 먼저 활용할 여지를 놓쳤습니다" (the best move is no check).

  The 19...Kh8 and 7...Bxe2 errors are of the kind v7's N-reading guards against: a reading the citations do
  not hold.
- rich shares free's guide and had none. So the arms' error rates differ by noise as much as by arm: one error
  moves a rate by about 0.85 per 100. free and rich together have 5 in 235 (2.1 per 100).

### 3.3 What the commentaries say

The same scene in the three arms (rapid, 26...Re8, run 1) carries the same content. In each, the rook left
f8, f7 lost its defender, 27.Bxf7+ follows, and the line ends 30.Ng5#; 26...Bd7 was better. Only the opening
changes:
- v7: "26...Re8은 블런더로 판정됐고, 엔진은 26...Bd7을 선택했습니다."
- free: "26...Re8는 룩으로 백 룩 e5를 공격했지만, 동시에 f7 폰을 지키던 흑 룩의 수비를 풀었습니다."
- rich: "26...Re8은 백 룩 e5를 공격했지만, 동시에 f8 룩이 f7 폰을 지키던 수비를 없앴다."

Where the new material applied, it was said. At rapid 8.cxd4 both rich runs wrote that the d4 pawn became
isolated ("8.cxd4는 폰을 되찾았지만 d4의 백 폰을 고립폰으로 만들었다"); v7's said only the grade, the engine's
8.O-O and a reading. A `structure` or `file` item appears at few moves, though, so rich cited one 0.9 times a
run. The other candidates' lines were not cited more than in v7.

No arm played a line of its own (`explore`, as in AG8 F5).

### 3.4 min (rev. 2)

Means a run (luna, 8 runs each):

| | v7 | free | min0 | min |
| --- | ---: | ---: | ---: | ---: |
| Plies commented | 11.9 | 12.0 | 12.1 | 12.1 |
| Sentences | 52.4 | 53.4 | 20.2 | 22.9 |
| … at a fixed moment | 4.9 | 5.1 | 1.8 | 2.0 |
| Sentences citing a reason | 29.2 | 21.2 | 10.1 | 10.4 |
| Interpretations | 12.4 | 12.5 | 0.1 | 0 |
| Commentaries opening with the move's name | 94% | 33% | 99% | 100% |
| … with the grade in the first sentence | 78% | 39% | 86% | 97% |
| Refused submissions | 4.9 | 5.3 | 1.8 | 1.9 |
| Cost | $0.017 | $0.017 | $0.008 | $0.009 |

Two runs of min0 that read the guide wrote as short as those that did not (22 and 28 sentences in 10 and 14
plies). Nearly every commentary is one frame: "13.Qe2는 부정확한 수였고, 엔진의 1순위는 13.Nf5였습니다." and, where the
board has an item, one sentence of it. Some sentences read the data's fields aloud: "이는 … 별도로 확인해야 하는
배치상의 위협입니다", "해설 태그에는 브릴리언트가 붙었습니다".

Blind judging, a set each: min0's and min's 24 fixed-moment commentaries, each mixed with the same 24 anchors
(8 of v7, free and rich, judged in §3.2). The judge's scale moved between sets: the anchors scored 2.54 in §3.2,
3.29 and 3.25 here; their wrong sentences stayed close (4 in §3.2, 4 and 4 here). Scores compare within a set:

| | min0's set | | min's set | |
| --- | ---: | ---: | ---: | ---: |
| | min0 | anchors | min | anchors |
| Sentences | 43 | 118 | 49 | 118 |
| Wrong | 2 | 4 | 1 | 4 |
| Doubtful | 7 | 5 | 0 | 4 |
| Mean score (1–5) | 2.46 | 3.29 | 2.54 | 3.25 |

min's wrong sentence puts the played line's 32.exd5 in the other line; min0's are "엔진의 최선 라인은 8.Qa4+로
이어집니다" (8.Qa4+ is in the played line) and a material loss the line does not show. Few sentences give few
errors and the lowest scores.

## 4. What the trial shows

1. **Freeing the guide changes the surface, not the content.** The openings, the grade-first frame and
   the hedged endings mostly go: 94% → 33–49%, 78% → 39–52%, 28% → 0%. The material is the same: the grade, the
   engine's move, the lines, one board item. The judge scored free and rich no higher than v7 (2.42 and 2.54
   against 2.75).
2. **Without the type table and the notes, fewer reasons are cited.** Reason-citing sentences fall by a
   quarter (29.2 → 21.2), at the same length. The notes and the table are what pushed reasons in (AG8 §7: the
   rules made citations happen).
3. **No sign of fewer errors, and readings drift.** free's errors include two readings the citations do not
   hold. These are of the kind N-reading targets. rich had none, so the rate difference is not shown.
4. **Material is said when it exists.** Pawn structure was used where a move changed it (8.cxd4). What
   limits richness is what the digest holds at each move and a model that does not test its own lines.
5. **Removing the method does not free the commentary; it shrinks it to the frame** (min, §3.4). With only the
   task, the tools and the check, luna writes two sentences a scene, opens 97–100% with the move and the grade,
   and writes no interpretation. The typed feel is luna's default; the guide's types, notes and length advice are
   what make it write reasons and readings at all. Richness has to be asked for (E1's surface rules) and given
   material (E2), not reached by removing rules.

## 5. Directions

- **E1. Keep v7's evidence rules and take free's surface rules into the guide** (a small packet). Add: no
  frame repeated a scene, the grade need not open, varied openings, interpretations without "~로 보인다".
  Keep the type table as a reference, not a step ("2~4개 고르세요" goes), and keep the notes. This targets the
  typed feel without losing finding 2.
- **E2. More material per move** (rich, extended). Keep `structure`/`file` items. Add the items commentators use
  most that the digest lacks:
  - a refutation of the most natural other move (a capture or check among the candidates, by its line);
  - the opponent's threat after the move (the first move of the played line and what it attacks);
  - the king's shelter changes (`king_zone_v1` exists).

  Each is a verified item. This is AG8 D1/D2's route, and the trial shows such items are said.
- **E3. A stronger writer at key moments.** AG8 F6 measured Sonnet as the most concrete, at about thirty
  times luna's cost. One Sonnet run a game on free and v7 (about $2) would show whether free's surface plus a
  stronger model gives the richness luna does not.
- Not recommended: free as is (finding 2, finding 3); min (finding 5).

## 6. Owner questions

- **Q1.** E1 as the next packet (recommended), with E2 designed after it?
- **Q2.** E3: run the Sonnet check now, or keep luna as the only model designed for (AG8 Q4)?
- **Q3.** For E2, which items first: natural-move refutations (recommended), the opponent's threat, king
  shelter?

## 7. Not in this note

The scratch trees and run records stay in the session scratchpad. Nothing in `main` changes.
