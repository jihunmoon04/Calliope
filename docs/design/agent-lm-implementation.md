# Agent LM — more moments, longer commentary (implementation)

Status: **rev. 1, for independent review**; two amendments to LM-D from the trial (A1, A2: LM-D §8). Date: 2026-10-19. Design:
[`agent-lm-design.md`](agent-lm-design.md) (LM-D rev. 2; owner Q1, Q2 as recommended).
Base: `design/lm` (LM-D on `main @ 3c0e738`).

## 1. What changed

| Item (LM-D §5) | Change |
| --- | --- |
| M1 | `agent/session.py`: `MOMENT_REASONS["inaccuracy"] = 8` (after `turning_point`); `_moments` gives a ply graded `inaccuracy` that reason; `MOMENTS = 16` (= `MAX_ITEMS`). |
| M2 | `prompts/commentary_ko_v7.md` (v6 with LM-D §3's two paragraphs, as rev. 2 words them); `build.PROMPTS`; every `commentary_ko_v6` in `server.py`; `server.GAME_OVERVIEW` ("at most 16 plies … inaccuracies"); `definitions.py` (`prompt.commentary_ko_v7`); `GUIDANCE_VERSION = "agent_guidance_v10"` with its new pinned digest (the overview's description is in it). |
| M3 | `docs/design/README.md`: this packet's row. |
| A1 (LM-D §8) | `server.INSTRUCTIONS` (step 4 of a game; a ply's step 4), `session._NEXT_SUBMIT_ITEMS` and the guide's submission paragraph: save 4–5 moments at a time, each at the guide's length ("핵심 장면은 5~9문장, 이유가 inaccuracy뿐인 장면은 3~5문장"); the pinned digest again (the instructions are in it). |
| A2 (LM-D §8) | The guide's notation section: "둔 수의 엔진 라인(`lines.played`)은 … 실제 대국의 수순이 아닙니다. '실전 라인', '실제 수순', '실전에서는'이라고 쓰지 말고 '둔 수 뒤 엔진 라인에서는'이라고 쓰세요." |

## 2. Tests

- `tests/agent/test_game_path.py`:
  - `test_the_moments_follow_their_rules` keeps AG6-D's rules under a cap of 8 (patched); ply 9 (an
    inaccuracy labelled miss) now has `["miss", "inaccuracy"]` (LM-D review B1);
  - `test_an_inaccuracy_is_a_moment_ranked_after_the_key_ones`: an inaccuracy is a moment; under the
    cap of 16 the key moments are kept and the inaccuracies with the larger losses;
  - `test_over_the_cap_inaccuracies_go_first_then_turning_points`: 10 turning points and 10
    inaccuracies keep the 10 and the 6 larger losses; 20 turning points push both inaccuracies out
    and keep the 16 earliest;
  - `test_the_next_text_lists_every_moment`: 12 moments listed;
  - `test_an_overview_of_16_moments_and_200_full_lines_is_under_its_construction`: 8 headers at the
    cap, 200 lines all with `best_move` and `loss`, 16 moments up to 4 reasons: under 40,000
    characters with no step run (LM-D review N6).
- `tests/agent/test_guidance.py` (v7, its paragraphs, v10 and its pin, the prompts' entries),
  `tests/agent/test_server.py` (the build's prompts).

The suite (`PYTHONPATH=src`, `CALLIOPE_STOCKFISH_PATH` set): 1795 passed on `87cfd5c` (A1); on the final commit (A2, a guide line and its test) see the PR.

## 3. The replay (LM-D §5, acceptance 2)

The four games' analyses (PW's trial, `0a94d18`), every ply read, with this branch:

| Game | Moments (main → LM) | LM's moments | Overview (characters) | Steps run |
| --- | --- | --- | ---: | --- |
| #123's | 8 → 15 | 5, 12, 13, 14, 15, 19, 20, 22, 25, 27, 52, 53, 56, 62, 68 | 10,567 | none |
| rapid | 8 → 14 | 11, 13, 15, 20, 23, 24, 40, 41, 42, 48, 51, 52, 53, 54 | 8,222 | none |
| fourth | 5 → 10 | 24, 25, 26, 31, 37, 38, 50, 53, 56, 67 | 9,707 | none |
| fresh | 3 → 9 | 23, 24, 41, 56, 62, 64, 66, 67, 76 | 11,165 | none |

As LM-D §0 gives them; every fixed moment of PW's trial is a moment. **Met.**

## 4. The trial (LM-D §5, acceptance 3)

PW's trial setup (HIMARI v3, the four games, analyses warmed once a game), three rounds on this
branch against PW's arm (`3c0e738`'s code, the same day):

| Round | Code | Runs |
| --- | --- | --- |
| LM | rev. 1–2's v7 (one submission, "한 번에") | luna ×2, Haiku ×1 a game (12) |
| LM2 | + A1 (4–5 moments a submission, the length in `next`) | 12 |
| LM3 | + A2 (the played line is not the game) | luna ×2 a game (8) |

Means a run (luna; Haiku in brackets):

| | PW | LM | LM2 | LM3 |
| --- | --- | --- | --- | --- |
| Plies commented | 6.1 (6.5) | 12.1 (11.0) | 12.1 (12.0) | 11.9 |
| Sentences | 21.4 (19.0) | 35.6 (40.8) | 53.1 (46.8) | 57.9 |
| … a fixed (key) moment | 3.3 (3.0) | 3.2 (3.9) | 5.0 (4.6) | 4.9 |
| … another moment | 3.3 (2.9) | 2.9 (3.7) | 4.1 (3.7) | 4.3 |
| Sentences citing a reason | 13.1 (10.2) | 20.9 (17.8) | 31.2 (20.5) | 30.9 |
| N-reading notes | 1.1 (1.8) | 3.3 (3.3) | 4.4 (5.2) | 3.9 |
| Input tokens (thousands) | 188 (341) | 256 (482) | 380 (948) | 437 |
| Cost | $0.009 ($0.018) | $0.012 ($0.029) | $0.015 ($0.040) | $0.017 |
| Seconds | 147 (166) | 236 (260) | 198 (283) | 200 |

`same_reply` was never left uncomputed for the budget. The sentence counts include a ply stored
twice (an agent resubmitting a moment): 3 of PW's 52 commentaries, 10 of LM3's 105.

**LM (rev. 1–2)** commented twice the plies but **not longer**: luna wrote 3.2 sentences a key
moment, as PW. It saved all its moments in one submission (as the guide, the instructions and
`next` asked: "한 번에"), 15 moments of up to 12 sentences in one tool call. **A1** — save 4–5 at a
time, the length in `next` — made it longer (LM2: 5.0 at a key moment).

**LM2's fixed moments**, judged blind with PW's (`blind3.txt`): 3 wrong in 174 sentences (PW 2 in
121; 1.7 and 1.65 per 100), all three an engine line told as the game ("실전 수순에서는 20.Qxd7 …
20...Qxh6로 백 나이트를 잡았다" — the game went 20...Re6). Across LM2's commentaries "실전/실제
수순·라인" was written in 24 of 612 sentences (PW 6 of 247); read by hand, 8 of them gave moves the
game did not play, none in PW. The digest calls the played move's line `lines.played`; the agent
said "실전 라인". **A2** names it. Haiku's long submissions garbled Korean five times at the fixed
moments ("비숋독", "지되", "허를 새 없이 … 고비우는"; none in luna, none in PW): Haiku is not the
model to show this with.

**LM3 (luna)**: "실전/실제 수순·라인" in 0 of 463 sentences ("둔 수 뒤 엔진 라인" instead). Wrong
sentences, read by hand (not blind): at the fixed moments 2 in 117 (1.7 per 100) — "실제로 이어진
8.Qxe2 뒤 백 비숍이 e2의 흑 비숍을 공격" (that bishop was taken by 8.Qxe2), and a comparison
"20...Qd6 뒤 같은 21.dxc6" that cannot be played (no pawn on c6; the digest had no same reply);
at the other moments of the four first runs (35 commentaries) 2, one commentary at 10...c6 giving
the played line's 11...Qb4 as the alternative's. The run-1 commentary of 25...hxg3 now says the pawn
it takes (LM2's said a bishop).

Acceptance 3: more plies and more sentences a key moment than PW's (luna 3.5, Haiku 3.0) — **met**
from LM2 on (luna 5.0, 4.9; Haiku 4.6); wrong sentences at the fixed moments per 100 not above PW's
by more than half again — **met** (LM2 1.7, LM3 1.7, PW 1.65). Reported for the owner: the new
moments' errors are of the kinds seen before (a line's move bound to the wrong line, a time
misread), at about the fixed moments' rate; Haiku garbles long Korean submissions; a run costs about
twice PW's (luna $0.017) and takes about 200 seconds.
