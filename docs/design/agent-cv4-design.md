# Agent — CV4-D design: notes on what a sentence cites; S8 without kana and CJK ideographs

Status: **rev. 1 — for review**. Date: 2026-10-19. Base: `main @ 37cd2a0` (MS-c merged).
Inputs: [`agent-ag8-design.md`](agent-ag8-design.md) (AG8-D: §6.1 `states` and S7, §6.2 which
board item a sentence states and the parts, §6.3 S8, §6.4 the notes),
[`agent-ms-design.md`](agent-ms-design.md) (MS-D: §9 citing by handle),
[`agent-ms-c-implementation.md`](agent-ms-c-implementation.md) (MS-c: §4 the trial, §4.1 `states`
fell away, §5 the owner questions Q1 and Q2).

The owner decided MS-c's Q1 and Q2 as recommended (2026-10-19): the notes N-reason and N-reading
read the reason and consequence items a sentence **cites**, not those it `states`; S8 refuses a
Korean sentence with kana or CJK ideographs. Both are changes to the sentence check, so they are
one check version, `commentary_check_v4`, and this packet.

## 0. What the MS-c trial showed

**The notes.** Since MS-c an agent cites a served item by its handle, and the agents stopped
writing `states` (4.6–11.6 sentences a luna run under AG8, 0–0.6 under MS-c; MS-c §4.1). The notes
read `states` alone, so a commentary that cites its reasons is told it has none. The Opera game's
13.Rxd7 (ply 25), run `c-opera-1`:

| Sentence | `cites` | `states` |
| --- | --- | --- |
| 13.Rxd7는 최선수이자 브릴리언트로 평가됐다. 백은 d7의 룩을 내주고, 흑은 13...Nxd7로 잡을 수 있다. | `j7`, `c32` (`piece_offer_v1`, reason) | — |
| 엔진 라인에는 13...Rxd7 14.Rd1이 이어지며, 흑이 희생을 받아도 백의 기대 점수는 84퍼센트다. | `s43`, `c40` (`capture_holds_v1`, reason) | — |
| (interpretation) 룩을 던져 흑의 응수를 강요한 뒤에도 백의 우세가 유지되는, 공격의 주도권을 위한 희생으로 보인다. | `c32`, `c40`, `s43` | — |

The answer carried N-reason ("…그것을 states로 말하는 문장을 두면 더 좋은 해설이 됩니다") and
N-reading on the interpretation. The commentary states two reasons and reads them; both notes are
false. AG8's run `g-opera-4` at the same ply put its cited `pattern` and `gain` in `states` and got
no note.

The trial's commentaries replayed under the rule of §2 (their stored records;
approximate in two ways: a cited board item is parted by its propositions, not as an item, and the
digest is taken to have held a reason when v3 gave N-reason):

| Arm | Model | Commentaries | N-reason v3 → v4 | N-reading v3 → v4 (interpretations) |
| --- | --- | ---: | ---: | ---: |
| AG8 | luna | 113 | 43 → 12 | 71 → 18 (103) |
| AG8 | Haiku | 34 | 31 → 17 | 15 → 7 (16) |
| MS-c | luna | 121 | 118 → 17 | 96 → 27 (97) |
| MS-c | Haiku | 41 | 41 → 5 | 20 → 11 (20) |

The N-readings left are the ones the note is for: an interpretation citing a grade, a comparison
or a line alone ("…12...Bg4를 더 나은 선택으로 보았으므로, …비숍을 먼저 활용하는 편이 나았다",
citing `j5` and `better_alternative_v1`; "킹을 움직이기보다 룩을 f1으로 옮기는 편이 버티기 나았다는
엔진 판단이다", citing a grade and three lines).

**S8.** Two luna sentences of the MS-c trial mix Japanese into Korean ("…눈에入る場面でも、 먼저
15.Bxf6로…", "…우선하는ほう이 나았던…"). S8 asks for a Hangul syllable, which both have. Of the
3,537 stored `ko` sentences of every trial so far, six contain kana or a CJK
ideograph, every one a mistake of this kind (`計画`, `積極`, `ほうが`, `では`, `を`); no sentence
uses Hanja on purpose. Kana and CJK ideographs are the only letters other than ASCII and Hangul
in them.

## 1. Decisions

| # | Decision | Section |
| --- | --- | --- |
| D1 | N-reason and N-reading read the parts of what a sentence cites; `states` and S7 stay as they are. | §2 |
| D2 | S8 also refuses a `ko` sentence with kana or a CJK ideograph, naming them. | §3 |
| D3 | `commentary_check_v4`; `agent_guidance_v7` for the registry entry; the guide `commentary_ko_v4` unchanged. | §4 |

## 2. The notes on what a sentence cites

AG8-D §6.2's reading applies to `cites` in place of `states`: a sentence **cites a board item
whole** when every proposition of the item belongs to a proposition in its `cites` (a `b` handle
does: it expands to the item's propositions, MS-D §9.1); the **parts a sentence cites** are the
parts of the items it cites whole and of every proposition in its `cites`, parted as AG8-D §6.2
says (a claim by its template, a `material` `consequence`, a position kind `reason`, ...). The
handles in `cites` are expanded first, as for S3.

- `N-reason`: the subject's digest held a reason (AG8-D §6.4, unchanged) and no sentence cites a
  board item whole or a proposition of part `reason`;
- `N-reading`: an interpretation cites no board item whole and no proposition of part `reason` or
  `consequence`.

`states` stays optional with S7a and S7b (AG8-D §6.1), and `states_items` stays what the sentence
states (§6.2): a sentence that states says what it states; the notes no longer depend on it.

Because S7a keeps `states` within `cites`, everything a sentence states it cites: **a note given
under v4 is one v3 gave** (v4's notes are a subset of v3's for the same submission). A sentence
that cites a reason without writing it silences the notes; a note is advice, never a refusal, and
asking a written token of a cited reason (S7b's test) would keep the false note on the example's
interpretation, which writes no move or square. The texts:

- N-reason: "이 수의 ply 답에는 이유(part: reason) 근거가 있습니다. 그것을 인용하는 문장을 두면
  더 좋은 해설이 됩니다";
- N-reading: "이 interpretation 문장은 이유나 결과 근거를 인용하지 않았습니다. 판정이나 'X가 더
  나았다'만으로는 읽기가 아닙니다".

## 3. S8 without kana and CJK ideographs

A sentence of a `ko` commentary contains at least one Hangul syllable (AG8-D §6.3) **and no kana
or CJK ideograph**, read after the check's normalization (NFKC, AM2; a half-width katakana becomes
a full-width one):

- kana: U+3040–309F (Hiragana), U+30A0–30FF (Katakana), U+31F0–31FF (Katakana Phonetic
  Extensions), U+1B000–1B16F (Kana Supplement and Extended-A);
- CJK ideographs: U+3005–3007 (々〆〇), U+2E80–2FDF (radicals), U+3400–4DBF (Extension A),
  U+4E00–9FFF, U+F900–FAFF (compatibility), U+20000–323AF (Extensions B–H).

The violation names the characters as its `token`: `{"sentence": i, "rule": "S8", "token":
"入る場面でも", "problem": "a sentence of a ko commentary is written in Korean, without kana or
CJK ideographs"}`, in Korean "해설 문장은 한국어로 씁니다. 가나나 한자는 쓰지 않습니다". A sentence
with no Hangul keeps the existing violation; one with neither Hangul nor kana gets both.

- Hanja is refused with the rest: the trials have no deliberate use of it, and a commentary for
  Korean readers writes the Korean word.
- CJK punctuation (`、`, `。`, `「」`) is not a letter and is not refused by itself; in the
  trial it came with kana.
- Other scripts (Cyrillic, Greek, ...) are not added: no trial sentence has them, and a letter of
  another script that touches a move or a number is already refused (S3, AM4).

## 4. Versions and what is not changed

- `CHECK = "commentary_check_v4"`; the registry's `commentary_check_v3` entry becomes
  `commentary_check_v4` (S8 as in §3, the notes on `cites`), so `GUIDANCE_VERSION =
  "agent_guidance_v7"` and the agent build change. A record keeps the check it was accepted under;
  readers ignore `check` (AR-D AM2), so no schema change.
- The guide `commentary_ko_v4` is not changed: its rules 1 and 2 ("이유 근거를 … 말하는 문장을 하나
  이상", "interpretation 문장에 이유나 결과 근거를 둡니다") and its line on `notes` do not name
  `states`, and it already says "해설 문장은 한국어로 씁니다"; a sentence that mixes in Japanese is
  told so by its refusal.
- The duplicate key (AG6-D F15) does not hold `check`: a commentary resubmitted unchanged after the
  upgrade is a `duplicate`, answered with the notes of v4.
- The digest, the handles, S1–S7, `states_items` and the stored record's shape are unchanged.

## 5. Implementation (packet CV4) and acceptance

| Item | Change |
| --- | --- |
| C1 | `session._stated` takes the ids to read; the notes read the sentence's `cites`, `states_items` its `states`; the two note texts (§2). |
| C2 | `sentences.check_sentences`: S8's kana and CJK ranges and the violation with `token`; `messages_ko`: the Korean text (§3). |
| C3 | `CHECK`, the registry entry, `GUIDANCE_VERSION` and its pin (§4). |
| C4 | `docs/design/README.md`: this design and the packet's row; MS-c marked merged. |

Tests:

- the example of §0 rebuilt: a commentary citing a reason claim and a `b` handle with no `states`
  gets no N-reason and no N-reading; an interpretation citing a judgement and a comparison claim
  gets N-reading; a digest with a reason and no reason cited gets N-reason;
- v4's notes within v3's: for submissions with and without `states`, every v4 note is one the v3
  rule gives;
- S8: hiragana, katakana, half-width katakana, a kanji, Hanja and an Extension B ideograph refused
  with the characters as `token`; `、` and `。` alone accepted; a sentence of kana only gets both S8
  violations; the Korean text;
- the six trial sentences of §0 refused by S8, and the trial's other stored `ko` sentences not.

Acceptance: the suite passes; the replay of §0 run through the implemented `_notes` and S8 over the
stored records of the AG8 and MS-c trials gives no more notes than v3 for any commentary and
refuses exactly the six sentences. No new agent trial: the change alters no digest and no guide,
and the notes are advice whose effect the replay measures.

## 6. Owner questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | A paid agent trial for this packet? | No: nothing an agent reads before submitting changes; the replay over the 28 MS-c and the AG8 runs measures both changes. |
| Q2 | Tell the agent of the kana and Hanja rule in the guide (`commentary_ko_v5`)? | No: the guide says Korean already, the case is rare (2 of the 497 stored MS-c sentences), and the refusal says what to fix. |

## 7. Next

- The viewer: a sentence's cited reasons shown as its evidence (AG8-D §11).
