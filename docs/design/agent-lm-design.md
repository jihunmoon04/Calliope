# Agent — LM-D design: more moments, longer commentary

Status: **rev. 2 with amendments A1, A2 from the trial (§8) — independent review of rev. 1 (`66063bb`) READY_WITH_CORRECTIONS (B1, B2; N1–N7) applied (§7); owner Q1, Q2 as recommended (the owner asked for this work, 2026-10-19)**. Amends AG6-D §3.3 ("the first 8") and §3.6 ("at most 8 moments"): 16, with inaccuracies. Date: 2026-10-19. Base: `main @ 3c0e738` (PW merged).
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
| #123's | 71 | 3 / 5 / 6 | 8 / 10 | 15 |
| rapid | 55 | 1 / 4 / 8 | 8 / 8 | 14 |
| fourth | 67 | 0 / 2 / 6 | 5 / 5 | 10 |
| fresh | 78 | 0 / 2 / 7 | 3 / 3 | 9 |

(The last column by the new rule over the games' analyses (review N1); five inaccuracies are
moments already — misses or among the largest losses — and every moment of today stays one. The cap
of 16 binds on none of these games, so the trial does not exercise D1's ranking; the unit tests do.)

In PW's trial a run saved 6.1 plies (luna; Haiku 6.5) of 3.5 sentences on average (Haiku 2.9); the
fixed moments — key ones — got no more than the others (luna 3.3, Haiku 3.0; implementation review N3), under the guide's 4–7
(review B2: the numbers of PW's arm).

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
(`max_searches` 40 a window, shared with the agent's own `explore(search)` and `judge_move`). 15
moments may ask about 30, leaving about 10 for the agent. When the window runs out, `same_reply`
answers `{"not_computed": "budget", "retry_after_seconds": …}` and the digest is still served; the
agent's own searches are refused with a time to retry (review N5). The trial reports it.
Each digest is 2.4–2.8 thousand characters (PW §3), so 8 more moments add about 20 thousand
characters to a run's context.

## 3. D2 — longer commentary: `commentary_ko_v7`

`commentary_ko_v6` with these changes only:

1. **분량** (the paragraph after "## 순서"), replaced:
   "분량은 권장입니다: 핵심 장면(블런더, 실수, 놓친 수, 브릴리언트·그레이트, 큰 손실, 흐름이 바뀐
   수) 5~9문장, 이유가 `inaccuracy`뿐인 장면 3~5문장, 그 밖의 수 2~3문장. 등급을 말하는 문장은 하나면
   충분하고, 나머지는 '왜'와 '어떻게'에 씁니다: 이 수가 노린 것, 그 대가, 엔진 라인에서 일어나는 일,
   더 나은 수가 무엇을 했는지(같은 응수 비교), 그리고 그것이 판에 무엇을 남겼는지. 받은 근거
   (`board`의 항목, 클레임, 두 라인)를 하나씩 확인해 쓸 수 있는 만큼 쓰세요. 확인한 말이 적으면
   짧게 쓰세요. 분량을 일반론으로 채우지 마세요."
2. **대국 전체** (the paragraph under "## 제출" that starts "대국 전체를 해설할 때는"), replaced:
   "대국 전체를 해설할 때는 중요한 장면(moments)을 모두 해설하고, 장면끼리 이어지게 하세요(앞
   장면의 실수가 다음 장면에서 어떻게 대가를 치르는지). 첫 장면의 해설에는 오프닝과 초반 구도를
   2~3문장으로 넣고, 마지막 장면의 해설에는 대국이 어떻게 결정됐는지를 2~3문장으로 정리하세요(그
   장면의 근거와 앞서 해설한 장면들의 판정·평가로). 정리 문장도 이유나 결과 근거를 하나 이상
   인용하세요."
   (Review N2: "이유가 `inaccuracy`뿐인" — a moment with another reason is a key one; N3: no "나눠
   보내도 됩니다", which pulled against "여러 수는 `items`로 한 번에 보냅니다" — 16 moments fit one
   submission; N4: the closing sentences cite a reason or consequence, as N-reading asks.)

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

Tests: an inaccuracy is a moment with its reason; an inaccuracy that is also a miss or a top loss
keeps both reasons in priority order; under the cap of 16, 17 or more candidates drop by priority —
inaccuracies first, then turning points; `_next_moment` lists more than 8 plies. Today's test of the
rules (`test_the_moments_follow_their_rules`) does **not** hold unchanged (review B1: its game has 10
candidates under the new rule; ply 9 gains `inaccuracy`, ply 15 becomes a moment): it keeps AG6-D's
rules under a cap of 8 (patched) with ply 9's new reason, and the new tests take the cap of 16. The
overview of a game with the largest headers, 200 lines all with `best_move` and `loss`, and 16 moments
of the longest moves and 4 reasons stays under 40,000 characters with no step run (review N6). The
guide v7 served and its two paragraphs; the version pins.

Acceptance:

1. The suite passes (with `CALLIOPE_STOCKFISH_PATH`).
2. Replay of the four games' overviews: the moments a game (15, 14, 10, 9), every overview under its
   bound.
3. A short agent trial (the owner's presentation needs it): PW's trial setup (four games, luna ×2,
   Haiku ×1, warmed analyses), against PW's arm. Reported: moments saved and sentences a run, a
   moment and at the key moments; sentences citing a reason; cost and time a run; wrong sentences at
   PW's fixed moments, judged blind with PW's, and in the new moments' commentaries (read, not
   blind: no baseline has them); N-reading notes; `same_reply` not computed for the budget; input
   tokens. Met when the runs comment more moments and more sentences a key moment than PW's (luna
   3.3 at a fixed moment — 85 sentences in 26 commentaries; 3.5 a commented ply —, Haiku 3.0), and the wrong sentences at the fixed moments, per 100 sentences there, are not
   above PW's (2 wrong in 121 sentences of its 38 fixed-moment commentaries: 1.7 per 100) by more than half again; reported by kind for the
   owner. Blind judging is weaker here: v7's commentaries are visibly longer (review N7).

## 6. Owner questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Inaccuracies as moments, up to 16 a game? | Yes: the only reason that adds moments on these games (§0); ranked last, so the key moments come first. |
| Q2 | The guide's lengths (5–9, 3–5, opening and closing paragraphs)? | Yes, with the trial to check that the extra sentences are verified ones, not filler. |

## 7. Review dispositions — rev. 1 (`66063bb`), independent review: READY_WITH_CORRECTIONS

The review found §0's limits and table (but its last column), the overview bound, the budget, the
versions (the pin moves with `GAME_OVERVIEW`), the guide's anchors, and handles of other plies
citable from one commentary (`_by_handle` per game) as stated.

| # | Finding | Disposition |
| --- | --- | --- |
| B1 | `test_the_moments_follow_their_rules` does not still hold (10 candidates under the new rule). | Applied (§5, Tests). |
| B2 | §0's luna sentence numbers were the "as today" arm's. | Applied: PW's 3.5 / 3.5; acceptance's baseline luna 3.5, Haiku 3.0. |
| N1 | The replay gives 15 / 14 / 10 / 9 moments; the cap binds on none. | Applied (§0, §5 acceptance 2). |
| N2 | "부정확 장면 3~5문장" is ambiguous for a moment with two reasons. | Applied: "이유가 `inaccuracy`뿐인 장면". |
| N3 | "`items`로 나눠 보내도 됩니다" pulls against the guide and `next`. | Applied: dropped. |
| N4 | The closing paragraph invites interpretations citing judgements only (N-reading). | Applied: "정리 문장도 이유나 결과 근거를 하나 이상 인용하세요"; the trial reports N-reading notes. |
| N5 | The budget wording: what happens when searches run out. | Applied (§2). |
| N6 | An overview-bound test that tests the construction; amend AG6-D. | Applied: the test (§5); the amendment named in the status line and the README row. |
| N7 | Acceptance 3's noise undefined. | Applied: per 100 sentences, at most half again PW's; the blind judging's weakness stated. |

## 8. Amendments from the trial (implementation §4)

| # | Amendment | Why |
| --- | --- | --- |
| A1 | Save 4–5 moments a submission, each at the guide's length: the instructions (a game's step 4, a ply's step 4), `next` after every moment is read ("…4~5개씩 나눠 저장하세요. 핵심 장면은 5~9문장, 이유가 inaccuracy뿐인 장면은 3~5문장입니다(근거로 확인한 만큼)…") and the guide's submission paragraph. This reverses review N3's "16 moments fit one submission": they fit, but an agent writing 15 commentaries in one call wrote 3 sentences each. | LM's run: luna 3.2 sentences a key moment, as PW, all moments in one call. |
| A2 | The guide's notation section: the played move's engine line (`lines.played`) is no game move; "'실전 라인', '실제 수순', '실전에서는'이라고 쓰지 말고 '둔 수 뒤 엔진 라인에서는'이라고 쓰세요." | LM2: "실전 수순/라인" for the engine line in 24 of 612 sentences, 8 giving moves the game did not play (none in PW). |
