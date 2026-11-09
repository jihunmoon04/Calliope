"""AF-D §4: harness rev. 8's frame check (`harness_frames_v1`) — code, no model request — of how a
submitted sentence frames a number it cites.

A rule holds a sentence only when the sentence maps to it uniquely: it cites exactly one explicit
proposition of the rule's kind (never a handle the server would expand), and, for F1 and F2, writes
exactly one count, equal to that proposition's number. Otherwise the sentence is `uncheckable` for
that rule: recorded, never held (AF-D §4.1, review F2 of rev. 2).

- **F1 change as standing:** a `material` proposition (a change from ply `from` to `to`, for
  `side`) written with a standing word, where the standing at `to` is not the change;
- **F2 segment as whole:** the same proposition written with a whole-line word, where `to` is short
  of the line's length;
- **F3 grade:** a grade word against the one cited judgement's grade (or label).

The word lists are fixed here; a frame written in other words is not read (a missed frame, not a
false hold).
"""

from __future__ import annotations

import json
from functools import cache

from calliope.agent.build import text as prompt_text
from calliope.agent.sentences import _INTEGER, tokens

FRAMES_VERSION = "harness_frames_v1"
# who is ahead (not what was gained): stems as they occur in the commentaries
STANDING_WORDS = ("앞서", "앞선", "앞섭", "앞섰", "우세", "우위", "뒤져", "뒤진", "뒤처", "열세")
# the whole line
WHOLE_WORDS = ("전체", "끝에", "끝까지", "끝의", "끝에서", "마지막", "최종", "통틀어")
# a negation in the sentence: its frame may be denied ("앞서지는 않는다", "블런더가 아니다"), so
# the sentence is `uncheckable`, never held (review F3 of the implementation's rev. 2)
NEGATIONS = ("않", "아니", "못", "없", "말고")
# AF implementation A9 (step 2, Q9 option 2): phrases a reader takes for the standing, written by
# the agent for a cited change ("이 라인의 백 물질 차이는 -4"); judge v2 reads them as the standing.
# Counted (`ambiguous`), never held: the pilot shows whether harness_v4's example line removes them.
AMBIGUOUS_STANDING = ("물질 차이", "물질은")


@cache
def grade_words() -> dict[str, str]:
    """Each Korean grade or label name → its key (`blunder`, `miss`, …), from the glossary the
    commentaries are written with."""

    glossary = json.loads(prompt_text("glossary_ko_v1.json"))
    out = {}
    for group in ("grades", "labels"):
        for key, word in (glossary.get(group) or {}).items():
            if word and key not in NOT_GRADE_WORDS:
                out[word] = key
    return out


# AF implementation A8 (the replay, §10): a grade whose Korean name is also the commentaries' noun
# for something else is not read as a grade — `best`'s name is how they write "the best move"
# ("엔진 최선수 28...fxg4는"): nine of the replay's ten false holds
NOT_GRADE_WORDS = ("best",)


def counts(text: str) -> list[int]:
    """The sentence's counts: its integer tokens that are not a move (as `sentences.tokens` splits
    them; a move's number stays inside the move's token)."""

    return [int(t.replace("−", "-")) for t in tokens(text) if _INTEGER.fullmatch(t)]


def items_of(arguments: dict) -> list[dict]:
    subjects = arguments["items"] if isinstance(arguments.get("items"), list) else [arguments]
    return [s for s in subjects if isinstance(s, dict)]


def refs_needed(arguments: dict) -> set[str]:
    """The handles the check reads through `detail`: every explicit `material` proposition's line
    and every explicit `judgement` proposition's judgement."""

    out = set()
    for item in items_of(arguments):
        ids = set()
        for p in item.get("propositions") or []:
            if not isinstance(p, dict):
                continue
            ids.add(p.get("id"))
            if isinstance(p.get("line"), str):
                out.add(p["line"])
            if p.get("kind") == "judgement" and isinstance(p.get("judgement"), str):
                out.add(p["judgement"])
        for sentence in item.get("sentences") or []:
            for cite in (sentence or {}).get("cites") or [] if isinstance(sentence, dict) else []:
                if isinstance(cite, str) and cite not in ids and cite[:1] in ("x", "s"):
                    out.add(cite)  # a cited line or score, for `search_numbers`
    return out


def _standing_at(ledger: dict, ply: int) -> int | None:
    if ply == 0:
        return ((ledger.get("standing") or {}).get("start") or {}).get("white_minus_black")
    plies = ledger.get("plies") or []
    if 0 < ply <= len(plies):
        return plies[ply - 1].get("standing_white")
    return None


def _found(text: str, words) -> list[str]:
    return [w for w in words if w in text]


def check(arguments: dict, records: dict[str, tuple[str | None, object]]) -> dict:
    """Every sentence of a (normalized) `submit_commentary` call: `held` (rule, sentence, reply),
    `uncheckable` (rule, sentence, why), `ambiguous` (A9: a cited material number written with a
    phrase read as the standing, counted and never held) and `search_numbers` (sentences with a count or score that
    cite a line or score from a session search). `records`: ref → (kind, item) from `detail`."""

    held, uncheckable, ambiguous, search_numbers = [], [], [], 0
    n = 0
    grades = grade_words()
    for item in items_of(arguments):
        props = {p.get("id"): p for p in item.get("propositions") or [] if isinstance(p, dict)}
        for sentence in item.get("sentences") or []:
            if not isinstance(sentence, dict) or not isinstance(sentence.get("text"), str):
                continue
            n += 1
            text = sentence["text"]
            cites = [c for c in sentence.get("cites") or [] if isinstance(c, str)]
            explicit = [props[c] for c in cites if c in props]
            handles = [c for c in cites if c not in props]
            materials = [p for p in explicit if p.get("kind") == "material"]
            judgements = [p for p in explicit if p.get("kind") == "judgement"]
            numbers = counts(text)
            if _search_backed(explicit, handles, records) and (numbers or _has_score(text)):
                search_numbers += 1
            standing = _found(text, STANDING_WORDS)
            whole = _found(text, WHOLE_WORDS)
            negated = _found(text, NEGATIONS)
            phrases = _found(text, AMBIGUOUS_STANDING)
            balances = {abs(m["balance"]) for m in materials if isinstance(m.get("balance"), int)}
            numbered = (any(abs(c) in balances for c in numbers) if balances  # PR #164 F1
                        else bool(numbers) and any(h.startswith("x") for h in handles))  # fmt: skip
            if phrases and not standing and numbered:
                ambiguous.append({"sentence": n, "phrases": phrases})  # A9: counted, not held
            if (standing or whole) and (materials or any(h.startswith("x") for h in handles)):
                why = (f"a negation ({', '.join(negated)})" if negated
                       else _not_unique(materials, handles, numbers))  # fmt: skip
                if why:
                    for rule, words in (("F1", standing), ("F2", whole)):
                        if words:
                            uncheckable.append({"rule": rule, "sentence": n, "why": why})
                else:
                    held += _material_rules(n, materials[0], records, standing, whole)
            named = [w for w in grades if w in text]
            if named and judgements:
                if negated:
                    uncheckable.append({"rule": "F3", "sentence": n,
                                        "why": f"a negation ({', '.join(negated)})"})  # fmt: skip
                elif len(judgements) != 1 or len(named) != 1:
                    uncheckable.append({"rule": "F3", "sentence": n,
                                        "why": f"{len(judgements)} judgements, grade words {named}"})  # fmt: skip
                else:
                    held += _grade_rule(n, judgements[0], named[0], grades, records)
    return {"version": FRAMES_VERSION, "held": held, "uncheckable": uncheckable,
            "ambiguous": ambiguous, "search_numbers": search_numbers, "sentences": n}  # fmt: skip


def _not_unique(materials: list, handles: list, numbers: list[int]) -> str | None:
    if any(h.startswith("x") for h in handles):
        return "a material number may come from a cited handle"
    if len(materials) != 1:
        return f"{len(materials)} cited material propositions"
    if len(numbers) != 1:
        return f"{len(numbers)} counts in the sentence"
    balance = materials[0].get("balance")
    if not isinstance(balance, int) or abs(numbers[0]) != abs(balance):
        return "the count is not the cited proposition's"
    return None


def _material_rules(n: int, prop: dict, records: dict, standing: list, whole: list) -> list[dict]:
    _kind, item = records.get(prop.get("line"), (None, None))
    ledger = (item or {}).get("ledger") if isinstance(item, dict) else None
    if not ledger:
        return []
    out = []
    start, end = int(prop.get("from", 0)), int(prop.get("to", 0))
    side = prop.get("side")
    change = prop.get("balance")
    at_end = _standing_at(ledger, end)
    length = len(ledger.get("plies") or [])
    if standing and at_end is not None and side in ("white", "black"):
        for_side = at_end if side == "white" else -at_end
        if for_side != change:
            leader = "백" if at_end > 0 else "흑" if at_end < 0 else "어느 쪽도 아닌"
            out.append({"rule": "F1", "sentence": n, "reply": (
                f"{prop.get('id')}는 {start}–{end}수 동안 {_side(side)}의 물질 변화({change:+d})이지 "
                f"앞선 정도가 아니다. {end}수 뒤 물질은 {leader} 쪽이 {abs(at_end)}점 앞선다(원장의 "
                f"standing).")})  # fmt: skip
    tail = _standing_at(ledger, length)
    origin = _standing_at(ledger, 0)  # the whole line from its start, not the segment's (PR #163 F1)
    whole_change = None
    if tail is not None and origin is not None and side in ("white", "black"):
        whole_change = (tail - origin) if side == "white" else (origin - tail)
    partial = start > 0 or end < length
    # A8: a segment written as the whole line is wrong only when the whole line's change differs
    if whole and partial and whole_change is not None and whole_change != change:
        out.append({"rule": "F2", "sentence": n, "reply": (
            f"{prop.get('id')}는 라인 {length}수 중 {start}–{end}수 구간이다. 라인 끝의 standing은 "
            f"백 기준 {tail:+d}." if tail is not None else
            f"{prop.get('id')}는 라인 {length}수 중 {start}–{end}수 구간이다.")})  # fmt: skip
    return out


def _grade_rule(n: int, prop: dict, word: str, grades: dict, records: dict) -> list[dict]:
    _kind, item = records.get(prop.get("judgement"), (None, None))
    if not isinstance(item, dict):
        return []
    grade, label = item.get("grade"), item.get("label")
    if grades.get(word) in (grade, label):
        return []
    names = {v: k for k, v in grades.items()}
    shown = names.get(grade, grade)
    move = (item.get("move") or {}).get("san") if isinstance(item.get("move"), dict) else None
    return [{"rule": "F3", "sentence": n, "reply": (
        f"인용한 판정({move or prop.get('judgement')})의 등급은 {shown}이다: '{word}'가 아니다.")}]


def _side(side: str) -> str:
    return "백" if side == "white" else "흑"


def _has_score(text: str) -> bool:
    import re

    return bool(re.search(r"[+\-−]\d+\.\d\d", text))


def _search_backed(explicit: list, handles: list, records: dict) -> bool:
    """A number cited from a session search: a `material` count whose own segment (plies `from`+1
    to `to`) holds a session search's ply (PR #163 review F3: not a ply after the segment); another
    cited line with any such ply; or a session search's score (an `s` record without the analysis's
    `search` index)."""

    cited = [(p.get("line"), p) for p in explicit if isinstance(p.get("line"), str)]
    cited += [(ref, None) for ref in handles]
    for ref, prop in cited:
        kind, item = records.get(ref, (None, None))
        if not isinstance(item, dict):
            continue
        plies = (item.get("ledger") or {}).get("plies") or []
        if prop is not None and prop.get("kind") == "material":
            plies = plies[int(prop.get("from", 0)):int(prop.get("to", 0))]
        if any(x.get("source") == "search" for x in plies):
            return True
        if kind == "search_line" and "search" not in item:  # the analysis's lines carry `search`
            return True
    return False
