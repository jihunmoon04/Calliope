# Agent CV4 — the notes on what a sentence cites, S8 without kana and CJK ideographs

Status: **rev. 1 — for review**. Date: 2026-10-19. Base: `agent/check-v4 @ e78024e` (CV4-D rev. 2,
PR #120). Design: [`agent-cv4-design.md`](agent-cv4-design.md) (C1–C4).

## 1. What was built

| CV4-D | Where |
| --- | --- |
| C1 §2 the notes on `cites` | `agent/session.py`: `_stated(ids, verified, served)` reads the ids it is given; `_commentary` reads a sentence's `states` for `states_items` and its `cites` (handles expanded) for the parts the notes read; `_notes` takes those parts; the two note texts say "인용". |
| C2 §3 S8 | `agent/sentences.py`: `_KANA_CJK` (the ranges of §3, Kana Extended-B with them) and a second S8 violation with the characters, read after `normalized` (NFKC), as `token`; `agent/messages_ko.py`: "해설 문장은 한국어로 씁니다. 가나나 한자는 쓰지 않습니다". |
| C3 §4 versions | `CHECK = "commentary_check_v4"`; the registry's `commentary_check_v3` entry is `commentary_check_v4`; `GUIDANCE_VERSION = "agent_guidance_v7"`. |
| C4 | `docs/design/README.md`: this packet's row. |

## 2. Where the implementation departs from the design, and why

1. **`agent_guidance_v7` pins v6's digest.** The pinned digest covers the instructions, the tool
   descriptions and `definitions`' answers to fixed queries over a fixed registry (AG5 review N2),
   so the real registry's new `commentary_check_v4` text does not move it. What `definitions`
   finds for the check did change, so the version is new (as AG7's v4 pinned v3's digest); the
   test says why.
2. **A half-width katakana is named in its full-width form** in the violation's `token` (`ﾀｲﾐﾝｸﾞ`
   → `タイミング`): S8 reads the normalized text, as every token of the check is read (AM2).

## 3. Tests

- `tests/agent/test_cv4.py` (18):
  - the notes: reasons cited by a `b` handle with no `states` get no note and store no
    `states`/`states_items` (§0's example); an interpretation citing a grade and a same reply's
    line gets N-reading, and no N-reason since a sentence cites a reason; a consequence claim
    cited by handle silences N-reading, not N-reason; the new texts;
  - `states_items` from `states`, not `cites` (the review's focus): a sentence citing two items
    and stating one stores the one;
  - v4's notes within v3's: every sentence of seven records of every part (a board item of two
    among them), each not cited, cited or stated, in both classes, and 2,000 random pairs, under a
    served reason, none, and no served digest; v4 drops notes v3 gave;
  - S8: hiragana, katakana, half-width katakana, a kanji, Hanja, Extension B, Kana Extended-B
    (review N1) and `々` refused with the characters as `token`; `、` and `。` accepted; the two
    conditions apart (review N2): English → the existing violation alone, Korean with kana → the
    new one alone, kana only → both; the six trial sentences refused, three plain ones not; the
    Korean refusal with `problem_en`.
- Changed: `commentary_check_v4` in `test_board.py` and `test_commentary.py`; the pins in
  `test_guidance.py`. The AG8 notes tests (`test_board.py`) pass unchanged: their sentences either
  state what they cite or cite no reason.
- Each fix reverted fails its tests: the notes on `states` fail three; `states_items` on `cites`
  fails one; the kana range without Kana Extended-B fails one.
- The suite: §5.

## 4. Acceptance (CV4-D §5)

The stored records of the AG8 and MS-c trials through the implemented `_stated` and `_notes`
(v3: the parts of `states`; v4: of `cites`; the served board items are not stored, so a cited item
is parted by its propositions, and the digest is taken to have held a reason when the agent was
told N-reason or stated one). The v3 replay gives the notes the agents were told for 308 of the
309 commentaries.

| Arm | Model | Commentaries | N-reason v3 → v4 | N-reading v3 → v4 |
| --- | --- | ---: | ---: | ---: |
| AG8 | luna | 113 | 43 → 12 | 72 → 18 |
| AG8 | Haiku | 34 | 31 → 17 | 15 → 7 |
| MS-c | luna | 121 | 118 → 17 | 96 → 27 |
| MS-c | Haiku | 41 | 41 → 5 | 20 → 11 |

- v4's notes are within v3's for every commentary (none outside).
- S8 over the 3,537 stored `ko` sentences of every trial: the new violation refuses exactly the six
  sentences of CV4-D §0 (tokens `計画`, `ほう`, `積極ほうが`, `では`, `を`, `入る場面でも`); six
  English sentences of an early run (before S8) get the existing violation alone; no other
  sentence is refused.

## 5. The suite

(filled in when the run ends)
