# Agent CV4 — the notes on what a sentence cites, S8 without kana and CJK ideographs

Status: **rev. 2 — review 1 READY_WITH_CORRECTIONS (N1–N7) applied (§6); review 2 READY (§7)**. Date: 2026-10-19. Base:
`agent/check-v4 @ d1f490d` (CV4-D rev. 3, PR #120). Design: [`agent-cv4-design.md`](agent-cv4-design.md) (C1–C4).

## 1. What was built

| CV4-D | Where |
| --- | --- |
| C1 §2 the notes on `cites` | `agent/session.py`: `_stated(ids, verified, served)` reads the ids it is given; `_commentary` reads a sentence's `states` for `states_items` and its `cites` (handles expanded) for the parts the notes read; `_notes` takes those parts; the two note texts say "인용". |
| C2 §3 S8 | `agent/sentences.py`: `_KANA_CJK` (the ranges of §3: Kana Extended-B with them, `・` without) and a second S8 violation naming each run of the characters, read after `normalized` (NFKC), as `token`; `agent/messages_ko.py`: "해설 문장은 한국어로 씁니다. 가나나 한자는 쓰지 않습니다". |
| C3 §4 versions | `CHECK = "commentary_check_v4"`; the registry's `commentary_check_v3` entry is `commentary_check_v4`; `GUIDANCE_VERSION = "agent_guidance_v7"`. |
| C4 | `docs/design/README.md`: this packet's row. |

## 2. Where the implementation departs from the design, and why

1. **`agent_guidance_v7` pins v6's digest.** The pinned digest covers the instructions, the tool
   descriptions and `definitions`' answers to fixed queries over a fixed registry (AG5 review N2),
   so the real registry's new `commentary_check_v4` text does not move it. What `definitions`
   finds for the check did change, so the version is new (as AG7's v4 pinned v3's digest); the
   test says why.

A half-width katakana is named in its full-width form in the violation's `token` (`ﾀｲﾐﾝｸﾞ` →
`タイミング`), as §3 says (S8 reads the normalized text).

## 3. Tests

- `tests/agent/test_cv4.py` (21):
  - the notes: reasons cited by a `b` handle with no `states` get no note and store no
    `states`/`states_items` (§0's example); an interpretation citing a grade and a same reply's
    line gets N-reading, and no N-reason since a sentence cites a reason; a consequence claim
    cited by handle silences N-reading, not N-reason; an interpretation citing a judgement, a
    comparison claim and a line is told, one citing a reason, a consequence or a board fact is
    not (review N3); the new texts;
  - `states_items` from `states`, not `cites` (the review's focus): a sentence citing two items
    and stating one stores the one;
  - v4's notes within v3's: every sentence of seven records of every part (a board item of two
    among them), each not cited, cited or stated, in both classes, and 2,000 random pairs, under a
    served reason, none, and no served digest; v4 drops notes v3 gave;
  - S8: hiragana, katakana, half-width katakana, a kanji, Hanja, Extension B, Kana Extended-B
    (design review N1), `々` and a compatibility ideograph NFKC keeps (U+FA0E; review N7) refused
    with the characters as `token`; `、`, `。`, `・` and `･` accepted (review N1); each run named
    apart (review N2); the two conditions apart (design review N2): English → the existing violation alone, Korean with kana → the
    new one alone, kana only → both; the six trial sentences refused, three plain ones not; the
    Korean refusal with `problem_en`.
- Changed: `commentary_check_v4` in `test_board.py` and `test_commentary.py`; the pins in
  `test_guidance.py`. The AG8 notes tests (`test_board.py`) pass unchanged: their sentences either
  state what they cite or cite no reason.
- Each fix reverted fails its tests: the notes on `states` fail three; `states_items` on `cites`
  fails one; the kana range without Kana Extended-B fails one; a comparison counted as a reading
  fails one (review N3). The reviewer's own mutations: §6.
- The suite: §5.

## 4. Acceptance (CV4-D §5)

The stored records of the AG8 and MS-c trials through the implemented `_stated` and `_notes`
(v3: the parts of `states`; v4: of `cites`; the served board items are not stored, so a cited item
is parted by its propositions, and the digest is taken to have held a reason when the agent was
told N-reason or stated one). The v3 replay gives the notes the agents were told for 308 of the
309 commentaries. The one apart, `g-opera-4` `01792301071019713652-1f5bae51`, states a served
item whole: without the served items the replay parts it by its propositions (`line`), so it
counts an N-reading the agent was not told, under v3 and v4 alike; AG8 luna's v3 N-reading is
so 72 here against the design's 71 (review N4).

| Arm | Model | Commentaries | N-reason v3 → v4 | N-reading v3 → v4 |
| --- | --- | ---: | ---: | ---: |
| AG8 | luna | 113 | 43 → 12 | 72 → 18 |
| AG8 | Haiku | 34 | 31 → 17 | 15 → 7 |
| MS-c | luna | 121 | 118 → 17 | 96 → 27 |
| MS-c | Haiku | 41 | 41 → 5 | 20 → 11 |

- v4's notes are within v3's for every commentary (none outside).
- S8 over the 3,537 stored `ko` sentences of every trial: the new violation refuses exactly the six
  sentences of CV4-D §0 (tokens `計画`, `ほう`, `積極 ほうが`, `では`, `を`, `入る場面でも`); six
  English sentences of an early run (before S8) get the existing violation alone; no other
  sentence is refused.

## 5. The suite

On rev. 2 (`0ef5114`; the same src and tests as its rebase onto CV4-D's last wording), with
`CALLIOPE_STOCKFISH_PATH` set: **1748 passed** (MS-c's 1727 and the 21 of `test_cv4.py`), none
skipped. A run without the engine path skips the 108 engine tests (1637 passed, 108 skipped) and is
not counted.

## 6. Review 1 (`8e899cd`): READY_WITH_CORRECTIONS

An independent reviewer (a fresh agent given the design, the diff and the replay) confirmed D1–D3,
v4's notes within v3's in the code (S7a runs on the expanded sentences; `_stated` only gains with
more ids), the edge cases (no served digest, an item cited whole by a `b` handle, the agent's own
propositions, an unverified cite refused by S2 first, duplicates removed in the expansion), the
duplicate key, the Korean templates (neither shadows the other), the versions, and every number of
§4. Its mutations: the notes on `states`, `states_items` on `cites`, no Kana Extended-B, kana read
from the raw text, the two S8 conditions merged, no Extension B, no `々`, no item part, N-reading
on `reason` only — each fails a test.

| # | Finding | Disposition |
| --- | --- | --- |
| N1 [design] | The Katakana range held `・` (U+30FB; the half-width `･` becomes it), which §3 says is punctuation and not refused. | §3 at odds with itself: CV4-D rev. 3 leaves U+30FB out; code and test. |
| N2 | The token joined characters apart (`積極ほうが`; `計 画` → `計画`). | Each run named apart, joined by a space; CV4-D rev. 3 says so; test. |
| N3 | No test of an interpretation citing a comparison claim; counting a comparison as a reading passed every test. | Test added; it fails on that mutation. |
| N4 | AG8 luna's v3 N-reading 72 against the design's 71, unexplained. | Explained in §4. |
| N5 | §5 unfilled. | Filled (§5). |
| N6 | Departure 2 (half-width katakana named full-width) is what §3 says. | Moved out of §2. |
| N7 | No test of the compatibility range; Extension J outside the range, as designed. | Test with U+FA0E (kept by NFKC). |

## 7. Review 2 (`0ef5114`): READY

Each fix of review 1 checked against its mutation (N1: the full U+30A0–30FF range fails the `・`
test; N2: runs joined without a space fail; N3, N7 as in §6); the run class against the range
list over every code point (no difference; no endpoint special in a class; astral ranges single
characters); docs and code agree; the rebase changed no source or test. Its two optional notes
(two wraps, `・` and the runs in CV4-D §5) applied.
