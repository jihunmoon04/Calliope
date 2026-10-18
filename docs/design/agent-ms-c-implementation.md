# Agent MS-c — citing by handle, the server's use, `commentary_ko_v4`, the trial

Status: **rev. 1 — for independent review**. Date: 2026-10-18. Base: `main @ 7ba8828` (MS-b
merged). Design: [`agent-ms-design.md`](agent-ms-design.md) §9–§10, §13 (R8–R10).

## 1. What was built

| MS-D | Where |
| --- | --- |
| R8 §9.1 citing by handle | `agent/session.py` `Session._by_handle`: every handle in a sentence's `cites` or `states` is resolved (`Session.resolve`, so only this game's handles) and replaced by the ids of the propositions built for it, once per submission: `j` → `judgement` (`<h>:judgement`), `c` → `claim` (`<h>:claim`, no `use`), `s` → `engine_score` (`<h>:score`) and, when the line has a PV, `engine_line` over the moves a digest shows (`<h>:line`), `b` → the item's propositions (`<h>:0`…), `x` → `explored_line` (`<h>:line`); `f` is refused ("write its proposition"). The built propositions join the submission's and are verified and stored as the agent's would be, with `by_handle`. An agent's id with `:` is refused |
| R8 §8.3 a `b` handle's `proves` | `remarks.board_tokens`: the subject's move, the squares and the counts and points its `proves` writes, read from the server's own text; kept per game (`Session.board_tokens`, cleared with the game) and merged into the S3 tokens of the item's first built proposition |
| R8 §9.2 the server's use | `propositions.Verifier._claim`: without a `use`, the first of `DERIVED_ORDER` (result, mechanism, associated, comparison, line_fact, uncertain, not_the_case) that `_use` allows; the stored proposition has `use_by: "server"`; none allowed is refused; an explicit `use` is checked as before. `Session._derived_uses`: each listed claim and each `also` member of a digest has `as` |
| R9 | `prompts/commentary_ko_v4.md` (new; v1–v3 kept as data, unserved); `build.PROMPTS`; the server's prompt and resource; `GUIDANCE_VERSION = "agent_guidance_v6"` (`submit_commentary`'s description: handles, `<handle>:<part>`, `as`); `CHECK = "commentary_check_v3"`; the registry's `prompt.commentary_ko_v4`, `commentary_check_v3`, `cite.handle`, `use.by_server`, `claim.as`, `claim.group`, `claim.relation` |

## 2. Where the implementation departs from the design, and why

1. **A built id is not held to the 32 characters of an agent's id.** A handle is 27–30
   characters, and `<h>:judgement` is longer; the limit is on what the agent writes. A built id
   carries `by_handle`, and no agent's id has a colon, so the two never meet.
2. **A built proposition counts toward the 32 a commentary may hold** (AG6-D §5.3), as the
   agent's would: the bound is on what is stored.
3. **A `b` handle's tokens are read from its `proves` text**, not built with it as a claim's are
   (`Tokens`, MS-b): a board item's `proves` comes from AG8's functions, which return text; the
   server reads its own text (squares, the numbers before 점, 개, 수, and the subject's move),
   which is what the item shows. A cut `proves` (AG8's `capped`) gives the tokens of what is shown.
4. **`f` handles are refused, not expanded.** A fact record is a family's whole record; which
   proposition of it a sentence means is the agent's to write (MS-D §9.1 lists `j c s b x`).
5. **A handle is one this game served, not only the subject's.** §9.1 says "a handle served for
   the subject"; the expansion resolves any handle of the game (`Session.resolve`), as a
   proposition the agent wrote with that handle would be verified ("as if the agent had written
   them"). A sentence of ply 40 may so cite ply 41's judgement (the trial has one: "백의 다음 수
   21.Re5는 엔진이 권한 21.dxc6를 놓쳤습니다", correct). The subject's own judgement is still
   required (one judgement proposition of the subject). The guide and the registry say "a handle
   this game served".
6. **The registry's relation entries** are `piece_relations_v1`, `relation.time`,
   `relation.place`, `claim.link` and `mate_over_scores` (§10's list); `board.*`,
   `board_remarks_ko_v2` and `sacrifice_compensated_v2` were registered by MS-a and MS-b.

## 3. Tests

- `tests/agent/test_ms_c.py` (synthetic engine, 8): handles alone cite a judgement, a claim, a line
  and a board item; built ids `<h>:<part>`, built once, a handle in `states` states all it stands
  for; a line without a PV builds its score alone (review B8); an agent's id with a colon is
  refused; a claim cited without a use is stored with the digest's `as` and `use_by: server`; an
  explicit wrong use refused, a right one stored without `use_by`; a move no cited handle holds
  is refused (S3); a handle the game did not serve is refused.
- `tests/agent/test_ms_c_stockfish.py` (Stockfish 19, gated, 13): every board item of the trial's
  twelve fixed moments, cited by its `b` handle with its `proves` as the sentence, is accepted (I5);
  31...Qf6's `removed_defender_v2` (only associated with its consequence), cited by handle, is
  stored `associated`, never `mechanism`.
- `tests/agent/test_guidance.py`: `commentary_ko_v4` served and its content (handles, `as`,
  `leads_to`, `held`, `also`, `proves`, `states`, `not_shown`, `en_passant`; no `says`, no
  `text`); `agent_guidance_v6` pinned; the prompts' registry.
- Changed: `commentary_check_v3` in two tests; the server's prompt names.

Full suite (Stockfish 19): **1716 passed**. ruff check and format clean.

## 4. The trial (MS-D §13)

As AG8's (AG8 implementation §4): HIMARI v3 drove one conversation a run, luna
(`openai/gpt-6-luna`) ×5 and Haiku 5.5 ×2 on each of the four games, on this branch (`c4e66f0`;
the later commits change only the registry's text and the tool description's wording), against
the AG8 records of `main` (the AG8 acceptance runs on its merged head: same games, same counts,
same harness). 28 new runs, about $0.27.

Means a run (luna; Haiku in brackets):

| Game | Arm | Moments saved | Fixed moments saved | Sentences citing a reason at the fixed moments | Refused submissions | Cost |
| --- | --- | --- | --- | --- | --- | --- |
| Opera | AG8 | 6.0 (2.5) | 3.0 (1.0) | 4.4 (1.0) | 1.6 (2.0) | $0.011 ($0.015) |
| Opera | MS-c | 6.2 (6.0) | 3.0 (3.0) | 6.0 (4.0) | 1.4 (1.5) | $0.009 ($0.020) |
| Rapid | AG8 | 8.2 (9.0) | 3.0 (3.0) | 5.4 (0.5) | 1.6 (2.0) | $0.013 ($0.026) |
| Rapid | MS-c | 8.6 (7.0) | 2.8 (3.0) | 4.6 (5.0) | 0.6 (1.5) | $0.008 ($0.023) |
| New game | AG8 | 3.0 (3.0) | 3.0 (3.0) | 6.6 (4.0) | 1.4 (1.5) | $0.009 ($0.018) |
| New game | MS-c | 3.2 (3.0) | 3.0 (3.0) | 5.8 (5.0) | 0.4 (0.5) | $0.007 ($0.013) |
| Fourth | AG8 | 5.0 (2.5) | 3.0 (1.5) | 8.2 (4.0) | 1.6 (1.0) | $0.011 ($0.013) |
| Fourth | MS-c | 6.0 (5.0) | 3.0 (3.0) | 6.0 (6.5) | 0.2 (1.5) | $0.009 ($0.017) |

A `ply` or `judge_move` digest: 3,711 characters against 5,273 (median over the runs' 176 and
151 digests, −30%); 0.18 s against 0.16 s a `ply` (median of the batches of `ply` calls).

Wrong sentences at the twelve fixed moments, by hand (AG7-D §7's marks), over luna's five runs:

| Game | AG8 | MS-c |
| --- | --- | --- |
| Opera | 1 — 9...b5: "그 비숍을 지키지 못하는 대가" of White's c4 bishop, for the bishop Black loses on b4 | 0 |
| Rapid | 0 | 0 |
| New game | 3 — 38...fxg3 "g3에서 비숍을 교환" (one run), "비숍을 먼저 교환" (one run, in two submissions) | 0 — two runs write "38...fxg3는 앙파상" (one: "앙파상으로 백 g4 폰을 잡는 수") |
| Fourth | 0 | 0 |
| **All** | **4** | **0** |

Two MS-c luna sentences mix Japanese into Korean (Opera 15.Bxd7+: "눈에入る場面でも、"; Rapid
20...c6: "…우선하는ほう이 나았던"); AG8's 361 luna and 108 Haiku sentences have none, MS-c's 155
Haiku sentences none. S8 accepts them: each contains Hangul.

The criteria (MS-D §13):

1. wrong sentences at the fixed moments no more than AG8's: **met** — 0 against 4;
2. sentences citing a reason at the fixed moments no fewer than AG8's less 10%: **met, narrowly**
   for luna — 22.4 against 24.6 a run over the four games (−9%; the bound is 22.1); Haiku 20.5
   against 9.5;
3. every fixed moment in 90% of the runs, Haiku every moment: **met** — luna 59 of 60 run-moments
   (one Rapid run saved two of three), every Haiku run every fixed moment (AG8's Haiku: both Opera
   runs saved one of three, one fourth-game run saved nothing);
4. a digest 25% smaller (median): **met** — −30%;
5. refused submissions no more than AG8's plus one: **met** (0.2–1.4 against 1.4–1.6; Haiku
   0.5–1.5 against 1.0–2.0); no sentence outside Korean: **met by S8, not in substance** — the two
   sentences above;
6. cost no more than AG8's, a digest within 0.5 s: **met for luna** (every game lower) and for the
   digest (+0.02 s); **Haiku's mean is $0.0183 against $0.0180**, higher on the Opera and the fourth
   game, where MS-c's Haiku runs saved the whole game (6 and 5 moments against AG8's 2.5 and 2.5).

Reported (MS-D §13):

- **Cites by handle**: 1,456 of 1,483 (98%); no MS-c run wrote a board item's proposition itself.
- **Derived uses**: 271 of 280 claim propositions have `use_by: server` — comparison 123, result
  84, line_fact 62, associated 2; 9 have the agent's `use` (comparison 6, associated 1, result 1,
  mechanism 0). Every `associated` is 31...Qf6's `discovery_v2` (twice by the server, once the
  agent's), never `mechanism`.
- **Cited items**: a `b` handle 202 times — 19 with `leads_to`, 2 `held`, 181 others; a group's
  `also` member 34 times.
- **What a saved subject was served and cited** (`measure.py` on the new records, against the
  framing's): the judgement 100% (97%), the played line 68% (36%), the best line 75% (28%),
  `lost_defence` 73%, `threat` 31–67% by kind, a comparison claim 72–79%, `piece_offer_v1` 95%;
  never cited: `prevents_v1`, `rescue_v1` (2 served each), the `en_passant` text (7).

### 4.1 What the trial shows besides the criteria: `states` fell away

`states` was on 4.6–11.6 sentences a luna run under AG8 and is on 0–0.6 under MS-c (6 of 33
submissions send it; 40 of 52 under AG8). Citing a `b` handle is now the way a sentence names a
board item, and the agents no longer add `states`. The notes (AG8-D §6: N-reason, N-reading) are
keyed on `states`, so they now fire on sentences that cite a reason by handle: 214 notes against
115 (N-reason 118 against 44), 4.4–14.8 a luna run against 1.4–8.0. The checks are unchanged and
the commentaries are not worse (criteria 1–2), but the notes now say less. Whether the notes
should count a reason or consequence cited by handle in `cites`, or the guide should ask for
`states` again, changes AG8-D §6's rule: it is an owner question (§5), not done here.

## 5. Owner questions

- **Q1 (§4.1)**: the notes N-reason and N-reading — keyed on `states` (as now), or on the reason
  and consequence items a sentence cites (a `b` handle, a `c` handle of part reason or
  consequence)? Recommended: on what it cites, `states` kept for S7; a check change
  (`commentary_check_v4`), its own packet.
- **Q2 (§4, criterion 5)**: refuse a Korean sentence with kana or CJK ideographs (S8 widened)?
  Recommended: yes, in the same packet as Q1.
