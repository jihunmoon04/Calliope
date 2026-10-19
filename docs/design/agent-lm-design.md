# Agent — LM-D design: more moments, longer commentary

Status: **rev. 1, for independent review**. Date: 2026-10-19. Base: `main @ 3c0e738` (PW merged).
Owner's request (2026-10-19, for a presentation the next day): "가능하다면 많은 수를 해설하고 해설
내용도 늘었으면 좋겠어" — comment more moves, and say more about each.
Inputs: [`agent-ag6-design.md`](agent-ag6-design.md) (AG6-D §3.3 the moments, §3.6 the overview's
bound, §5.2 `items`), [`agent-pw-design.md`](agent-pw-design.md) (`commentary_ko_v6`),
[`agent-pw-implementation.md`](agent-pw-implementation.md) §4 (the trial this packet is measured
against).

An agent comments the moments the overview names and says 4–7 sentences at a key one. This packet
names more moments — the inaccuracies too, up to 16 — and asks for more at each, without changing
what a sentence may say or how it is checked.

## 0. What limits it today

| Limit | Today | Where |
| --- | --- | --- |
| Moments a game | at most 8, chosen by rule: blunder, mistake, miss, brilliant, great, the 3 largest losses (≥ 150), turning points | `session.MOMENTS`, `_moments` (AG6-D §3.3) |
| Length a moment | "핵심 장면 4~7문장, 덜 중요한 수 2~3문장" (advice) | `commentary_ko_v6` |
| Sentences a commentary | at most 12 (S1) | `sentences.MAX_SENTENCES` |
| Subjects a submission | at most 16 | `session.MAX_ITEMS` |

Raising the cap alone adds little: the rule names few plies. On the four games of PW's trial
(`0a94d18`'s analyses, every ply read):

| Game | Plies | Blunders / mistakes / inaccuracies | Moments at a cap of 8 / 16 | With inaccuracies, cap 16 |
| --- | ---: | --- | --- | --- |
| #123's | 71 | 3 / 5 / 6 | 8 / 10 | 16 |
| rapid | 55 | 1 / 4 / 8 | 8 / 8 | 16 |
| fourth | 67 | 0 / 2 / 6 | 5 / 5 | 11 |
| fresh | 78 | 0 / 2 / 7 | 3 / 3 | 10 |

(The last column counts the moments of today's rule plus the inaccuracies not already moments,
capped at 16; the implementation's replay gives the exact numbers, §5.)

In PW's trial a run saved 6.1 plies (luna; Haiku 6.5) of 3.3 sentences on average (Haiku 2.9); the
fixed moments — key ones — got no more than the others (luna 3.3, Haiku 3.0), well under the guide's
4–7.

## 1. Decisions

| # | Decision |
| --- | --- |
| D1 | **More moments** (§2): `inaccuracy` is a moment's reason, ranked last; `MOMENTS` 8 → 16. |
| D2 | **Longer commentary** (§3): the guide `commentary_ko_v7` asks 5–9 sentences at a key moment, 3–5 at an inaccuracy, an opening paragraph at the first moment and a closing one at the last; "분량을 일반론으로 채우지 마세요" and every rule of the check stay. |
| D3 | **Versions** (§4): `commentary_ko_v7`, `agent_guidance_v10` (the overview's description changes, so its pinned digest changes). No check, claim, item or record change. |

## 2. D1 — more moments

`_moments` (AG6-D §3.3) gains one reason and a larger cap:

- a ply graded `inaccuracy` gets the reason `inaccuracy`;
- `MOMENT_REASONS` ranks it **8**, after `turning_point` (7): with the cap, a game with many errors
  keeps its blunders, mistakes, misses, brilliant and great moves, largest losses and turning points
  first, as today;
- `MOMENTS = 16` (= `MAX_ITEMS`: every moment fits one submission).

Nothing else of the rule changes (the order is "best priority, then the larger loss, then the earlier
ply"; the moments are returned in ply order). `game_overview`'s description says "at most 16 plies …
inaccuracies"; the `next` texts already list the moments however many they are.

**The overview's bound** (AG6-D §3.6: under 40,000 characters by construction, `OVERVIEW_LIMIT`
48,000): a moment is `{ply, move, reasons}`, under 100 characters; 8 more add under 800. The bound
holds; its two steps are unchanged.

**Budget.** The moments are read with `ply` from the analysed game (`analyze_game`'s job charged
apart, AG6-D §8); a read of an analysed ply is a cached digest, plus at most two same-reply searches
(`max_searches` 40 a window). 16 moments may ask up to 32 searches in a run; the window holds them.
Each digest is 2.4–2.8 thousand characters (PW §3), so 8 more moments add about 20 thousand
characters to a run's context.

## 3. D2 — longer commentary: `commentary_ko_v7`

`commentary_ko_v6` with these changes only:

1. **분량** (the paragraph after "## 순서"), replaced:
   "분량은 권장입니다: 핵심 장면(블런더, 실수, 놓친 수, 브릴리언트·그레이트, 큰 손실, 흐름이 바뀐
   수) 5~9문장, 부정확(`inaccuracy`) 장면 3~5문장, 그 밖의 수 2~3문장. 등급을 말하는 문장은 하나면
   충분하고, 나머지는 '왜'와 '어떻게'에 씁니다: 이 수가 노린 것, 그 대가, 엔진 라인에서 일어나는 일,
   더 나은 수가 무엇을 했는지(같은 응수 비교), 그리고 그것이 판에 무엇을 남겼는지. 받은 근거
   (`board`의 항목, 클레임, 두 라인)를 하나씩 확인해 쓸 수 있는 만큼 쓰세요. 확인한 말이 적으면
   짧게 쓰세요. 분량을 일반론으로 채우지 마세요."
2. **대국 전체** (the paragraph under "## 제출" that starts "대국 전체를 해설할 때는"), replaced:
   "대국 전체를 해설할 때는 중요한 장면(moments)을 모두 해설하고, 장면끼리 이어지게 하세요(앞
   장면의 실수가 다음 장면에서 어떻게 대가를 치르는지). 첫 장면의 해설에는 오프닝과 초반 구도를
   2~3문장으로 넣고, 마지막 장면의 해설에는 대국이 어떻게 결정됐는지를 2~3문장으로 정리하세요(그
   장면의 근거와 앞서 해설한 장면들의 판정·평가로). 장면이 많으면 `items`로 나눠 보내도 됩니다."

The cap of 12 sentences a commentary (S1) holds 9 + 3. A sentence still cites what it says; an
`interpretation` still reads the evidence it cites.

## 4. D3 — versions

- `prompts/commentary_ko_v7.md`; `build.PROMPTS`, `server.GUIDE_URIS` and the prompt and resource
  in `server.py`; the registry's `prompt.commentary_ko_v7` (v6 kept as data, unserved).
- `server.GAME_OVERVIEW`: "at most 16 plies chosen by rule (blunders, mistakes, misses, brilliant and
  great moves, the largest losses, turning points, inaccuracies)". The tool descriptions are in the
  guidance digest: `GUIDANCE_VERSION = "agent_guidance_v10"` with a new pinned digest.
- Unchanged: `agent_tools_v5` (no tool or argument changes), `board_v3`, `board_remarks_ko_v4`,
  `commentary_check_v5`, the reasoning and facts builds, stored records.

## 5. Implementation (packet LM), tests, acceptance

| Item | Change |
| --- | --- |
| M1 | `agent/session.py`: `MOMENT_REASONS["inaccuracy"] = 8`; `_moments` adds the reason; `MOMENTS = 16`. |
| M2 | `prompts/commentary_ko_v7.md`; `build.py`, `server.py` (the guide, `GAME_OVERVIEW`), `definitions.py`, `GUIDANCE_VERSION` and its pin. |
| M3 | `docs/design/README.md`. |

Tests: an inaccuracy is a moment with its reason; it ranks after a turning point and a loss under the
cap; 16 moments kept, the 17th dropped by priority; today's test of the rules (`test_the_moments_follow_their_rules`)
still holds with the new cap (its game has fewer than 16 candidates); the overview of a game with 16
moments stays under its bound; the guide v7 served and its two paragraphs; the version pins.

Acceptance:

1. The suite passes (with `CALLIOPE_STOCKFISH_PATH`).
2. Replay of the four games' overviews: the moments a game (expected about 16, 16, 11, 10), every
   overview under its bound.
3. A short agent trial (the owner's presentation needs it): PW's trial setup (four games, luna ×2,
   Haiku ×1, warmed analyses), against PW's arm. Reported: moments saved and sentences a run, a
   moment and at the key moments; sentences citing a reason; cost and time a run; wrong sentences at
   PW's fixed moments, judged blind with PW's, and in the new moments' commentaries (read, not
   blind: no baseline has them). Met when the runs comment more moments and more sentences a key
   moment than PW's, and the wrong sentences at the fixed moments are not above PW's (2) by more
   than the noise of 12 runs allows (reported by kind for the owner).

## 6. Owner questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Inaccuracies as moments, up to 16 a game? | Yes: the only reason that adds moments on these games (§0); ranked last, so the key moments come first. |
| Q2 | The guide's lengths (5–9, 3–5, opening and closing paragraphs)? | Yes, with the trial to check that the extra sentences are verified ones, not filler. |
