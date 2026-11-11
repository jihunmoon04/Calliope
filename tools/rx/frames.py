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

`harness_frames_v2` (harness rev. 10; the change log, 2026-11-10) adds to F1 the phrases a reader
takes for the standing (`AMBIGUOUS_STANDING`: "이 라인의 백 물질 차이는 -4"). v1 only counted them
(`ambiguous`); judge v2 marked them wrong in every row where they were written. v2 also reads a
sentence whose counts are all the cited proposition's number ("백은 3점을 잃고 … 물질은 백 -3"), which
v1 left `uncheckable`.

`harness_frames_v3` (harness rev. 11; the change log, 2026-11-10, "the standing read from the cited
line") is v2 with these readings, each holding only where the sentence maps to one record:

- **F1 through a handle:** a standing word or phrase with counts, citing one line handle and no
  material proposition: the line's standing and change at the ply the sentence names ("6수 시점",
  a move of the line, else the line's end); held when every count is the change and none the
  standing;
- **F1 over several propositions:** each count matched to the one cited `material` proposition of
  that size ("-5가 되었다가 … -2로": the changes to plies 4 and 5, not the standings -4 and -1);
- **F4 crossover:** "흑 쪽으로 넘어간다" for one cited line, held when that side was already ahead
  at the line's start or is not ahead at the named ply;
- **F5 no change:** "물질 변화가 없다" for one cited line, held when the standing at the named ply
  is not the line's start;
- **F6 ledger term:** a ledger field's name (`standing`, `net`, `captured`, …) written in the
  sentence; the reader does not know it.

`harness_frames_v4` (harness rev. 12; the change log, "the review's corrections") is v3 without its
false holds, found by the review of 2026-11-10:
- a count written as a gain or a loss ("3점을 더 얻어", "2점 손해로") is not read as a standing,
  and a count of plies ("3수 만에") is no count;
- F5 reads a cited `material` proposition's own segment, and a sentence that names a segment's
  start ("17.Kxf1 이후") without one is `uncheckable`;
- F4 with two crossovers in the sentence is `uncheckable`;
- F1 on a proposition holds only when the change and the standing differ in size (a standing
  written with its sign, "물질은 -1", is not taken for the change +1);
- the replies name no ledger field.

The word lists are fixed here; a frame written in other words is not read (a missed frame, not a
false hold).
"""

from __future__ import annotations

import json
import re
from functools import cache

from calliope.agent.build import text as prompt_text
from calliope.agent.sentences import _INTEGER, tokens

FRAMES_VERSION = "harness_frames_v1"
FRAMES_V2 = "harness_frames_v2"
FRAMES_V3 = "harness_frames_v3"
FRAMES_V4 = "harness_frames_v4"
# v5 (harness rev. 16; RV-1 P5-1, P5-6, P5-7, P5-8): v4 with only the gain or loss spans left out of
# the standing's counts, "N점 더 앞선다" read as a change, a written move matched as a whole token,
# and "강제" (the label forced) no grade word
FRAMES_V5 = "harness_frames_v5"
VERSIONS = (FRAMES_VERSION, FRAMES_V2, FRAMES_V3, FRAMES_V4, FRAMES_V5)
# who is ahead (not what was gained): stems as they occur in the commentaries
STANDING_WORDS = ("앞서", "앞선", "앞섭", "앞섰", "우세", "우위", "뒤져", "뒤진", "뒤처", "열세")
# the whole line
WHOLE_WORDS = ("전체", "끝에", "끝까지", "끝의", "끝에서", "마지막", "최종", "통틀어")
# a negation in the sentence: its frame may be denied ("앞서지는 않는다", "블런더가 아니다"), so
# the sentence is `uncheckable`, never held (review F3 of the implementation's rev. 2)
NEGATIONS = ("않", "아니", "못", "없", "말고")
# AF implementation A9 (step 2, Q9 option 2): phrases a reader takes for the standing, written by
# the agent for a cited change ("이 라인의 백 물질 차이는 -4"); judge v2 reads them as the standing.
# v1 counts them (`ambiguous`) and never holds them; v2 and later also read them as the standing.
AMBIGUOUS_STANDING = ("물질 차이", "물질은")
# v3 F4: the lead passing to a side ("흑 쪽으로 넘어가", "흑 쪽 우위로 넘어갑니다")
CROSSOVER = re.compile(r"(백|흑)\s*쪽\s*(?:우위|우세)?\s*으?로\s*(?:넘어|뒤집)")
# v3 F5: no change of material over the line (its own negation is the claim, not a denial)
NO_CHANGE = ("물질 변화가 없", "물질 변화는 없", "물질 변화 없", "물질은 그대로", "순득실은 0")
# v3 F6: the ledger's field names (`calliope.agent.lines.ledger`), never the reader's words
LEDGER_TERMS = re.compile(
    r"(?<![A-Za-z_])(standing_white|standing|white_minus_black|leader_at_end|for_first_mover|"
    r"first_mover|moved_pieces|by_white|by_black|captured|balance|net)(?![A-Za-z_])",
    re.IGNORECASE,
)
# v3: the ply a sentence names ("6수 시점", "8수 뒤", "16반수 동안")
NAMED_PLY = re.compile(r"(\d+)\s*반?수\s*(?:시점|뒤|째|동안|까지|후)")
# v4: a count of plies ("3수 만에", "16반수 동안") is no material count
PLY_COUNT = re.compile(r"[+\-−]?\d+\s*반?수(?![A-Za-z0-9])")
# v4: a count written as a gain or a loss ("3점을 더 얻어", "2점 손해로", "5점을 잃었다가")
GAIN_COUNT = re.compile(
    r"([+\-−]?\d+)\s*점\s*(?:을|를|의)?\s*(?:더\s*|다시\s*)?(?:얻|잃|벌|내주|되찾|손해|이득|손실)")
# v5: a lead written as grown or shrunk ("3점 더 앞선다", "2점 더 우세") is a change too
GROWN_LEAD = re.compile(r"([+\-−]?\d+)\s*점\s*(?:을|를)?\s*더\s*(?:앞|우세|벌어|뒤지|뒤처)")
# v4: a segment's start named in the sentence ("17.Kxf1 이후", "6수부터")
SEGMENT_START = ("이후", "부터")


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


def check(arguments: dict, records: dict[str, tuple[str | None, object]],
          version: str = FRAMES_VERSION) -> dict:  # fmt: skip
    """Every sentence of a (normalized) `submit_commentary` call: `held` (rule, sentence, reply),
    `uncheckable` (rule, sentence, why), `ambiguous` (A9: a cited material number written with a
    phrase read as the standing; counted, and from v2 read as the standing) and `search_numbers`
    (sentences with a count or score that cite a line or score from a session search). `records`:
    ref → (kind, item) from `detail`."""

    if version not in VERSIONS:
        raise ValueError(f"no frame check {version!r}")
    held, uncheckable, ambiguous, search_numbers = [], [], [], 0
    v5 = version == FRAMES_V5
    v4 = version == FRAMES_V4 or v5
    v3 = version == FRAMES_V3 or v4
    v2 = version == FRAMES_V2 or v3
    n = 0
    grades = grade_words()
    if v5:  # RV-1 P5-8: "강제로" is no grade
        grades = {w: k for w, k in grades.items() if k != "forced"}
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
            if v4:  # a count of plies is none; a count written as a gain is not the standing
                numbers = counts(PLY_COUNT.sub(" ", text))
                gains = [int(g.replace("−", "-")) for g in GAIN_COUNT.findall(text)]
                framed = [c for c in numbers if c not in gains and -c not in gains]
                if v5:  # RV-1 P5-1: only the spans written as gains leave; "물질은 흑 -9" stays
                    rest = GROWN_LEAD.sub(" ", GAIN_COUNT.sub(" ", PLY_COUNT.sub(" ", text)))
                    framed = counts(rest)
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
                ambiguous.append({"sentence": n, "phrases": phrases})  # A9: counted
                if v2:
                    standing = phrases  # v2: read as the standing, held when it is not
            if v4 and standing and numbers and not framed:
                uncheckable.append({"rule": "F1", "sentence": n,
                                    "why": "its counts are written as gains or losses"})  # fmt: skip
                standing = []
            elif v4:
                numbers = framed
            if v3:
                found, done = _v3_rules(n, text, materials, explicit, handles, numbers, records,
                                        standing, negated, v4, v5)  # fmt: skip
                held += found["held"]
                uncheckable += found["uncheckable"]
                if done:  # F1 read here: not again below
                    standing = []
            if (standing or whole) and (materials or any(h.startswith("x") for h in handles)):
                why = (f"a negation ({', '.join(negated)})" if negated
                       else _not_unique(materials, handles, numbers, v2))  # fmt: skip
                if why:
                    for rule, words in (("F1", standing), ("F2", whole)):
                        if words:
                            uncheckable.append({"rule": rule, "sentence": n, "why": why})
                else:
                    held += _material_rules(n, materials[0], records, standing, whole,
                                            phrased=v2 and bool(phrases) and standing == phrases,
                                            strict=v4)  # fmt: skip
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
    return {"version": version, "held": held, "uncheckable": uncheckable,
            "ambiguous": ambiguous, "search_numbers": search_numbers, "sentences": n}  # fmt: skip


def _v3_rules(n: int, text: str, materials: list, explicit: list, handles: list,
              numbers: list[int], records: dict, standing: list,
              negated: list, v4: bool = False, v5: bool = False) -> tuple[dict, bool]:  # fmt: skip
    """v3's readings of one sentence: (`held`/`uncheckable` entries, whether F1 was read here);
    `v4` without v3's false holds (the module's docstring)."""

    held, uncheckable = [], []
    for term in sorted({m.group(1) for m in LEDGER_TERMS.finditer(text)}, key=str.lower):
        held.append({"rule": "F6", "sentence": n, "reply": (
            f"'{term}'는 원장의 필드 이름이라 독자는 모른다: '백이 2점 앞선다', '흑이 3점을 "
            f"잃는다'처럼 우리말로 쓰라.")})  # fmt: skip
    lines = _cited_lines(explicit, handles)
    one = None
    if len(lines) == 1 and _ledger_of(records, lines[0]):
        one = (_ledger_of(records, lines[0]), lines[0])
    no_change = _found(text, NO_CHANGE)
    crossover = CROSSOVER.search(text)
    crossings = len(CROSSOVER.findall(text))
    rules = [("F5", bool(no_change)), ("F4", bool(crossover))]
    denied = [w for w in negated if not any(w in phrase for phrase in no_change)]
    segment = None  # v4: F5 reads a cited proposition's own segment
    if v4 and no_change and one is not None:
        own = [m for m in materials if m.get("line") == one[1]]
        if len(own) == 1 and isinstance(own[0].get("from"), int) and isinstance(own[0].get("to"), int):
            segment = (own[0]["from"], own[0]["to"])
    if (no_change or crossover) and (one is None or denied):
        why = (f"a negation ({', '.join(denied)})" if one is not None
               else f"{len(lines)} cited lines" if len(lines) != 1
               else "the cited line has no ledger")  # fmt: skip
        uncheckable += [{"rule": rule, "sentence": n, "why": why} for rule, on in rules if on]
    elif one is not None:
        book, ref = one
        ply = _named_ply(text, book, v5)
        start, at = _standing_at(book, 0), _standing_at(book, ply)
        name = ref.split(".")[0]
        if v4 and crossover and crossings > 1:
            uncheckable.append({"rule": "F4", "sentence": n, "why": f"{crossings} crossovers"})
            crossover = None
        if v4 and no_change and segment is not None:
            start, at = _standing_at(book, segment[0]), _standing_at(book, segment[1])
            ply = segment[1]
        elif v4 and no_change and _found(text, SEGMENT_START):
            uncheckable.append({"rule": "F5", "sentence": n,
                                "why": "the sentence names a segment's start"})  # fmt: skip
            no_change = []
        if no_change and start is not None and at is not None and at != start:
            held.append({"rule": "F5", "sentence": n, "reply": (
                f"인용한 라인({name})은 {ply}수 동안 물질이 바뀐다: 백 기준 {start:+d}에서 "
                f"{at:+d}로. '물질 변화가 없다'가 아니라 '{_gain_words(at - start)}'처럼 쓰라.")})  # fmt: skip
        if crossover and start is not None and at is not None:
            sign = 1 if crossover.group(1) == "백" else -1
            if start * sign > 0 or at * sign <= 0:
                held.append({"rule": "F4", "sentence": n, "reply": (
                    f"인용한 라인({name})의 물질은 백 기준 {start:+d}에서 {ply}수 뒤 {at:+d}다: "
                    f"{_lead_words(start)}에서 {_lead_words(at)}로, 우위가 "
                    f"{crossover.group(1)} 쪽으로 넘어간 것이 아니다.")})  # fmt: skip
    if not standing or negated or not numbers:
        return {"held": held, "uncheckable": uncheckable}, False
    if not materials and one is not None:
        book, ref = one
        ply = _named_ply(text, book, v5)
        start, at = _standing_at(book, 0), _standing_at(book, ply)
        if start is None or at is None:
            return {"held": held, "uncheckable": uncheckable}, False
        change = at - start
        if abs(change) != abs(at) and all(abs(c) == abs(change) for c in numbers):
            held.append({"rule": "F1", "sentence": n, "reply": (
                f"인용한 라인({ref.split('.')[0]})의 {ply}수 뒤 {change:+d}는 물질 변화이지 앞선 "
                f"정도가 아니다: 그때 물질은 {_lead_words(at)}다. 변화는 '{_gain_words(change)}'"
                f"처럼 쓰라.")})  # fmt: skip
        elif not any(abs(c) == abs(at) for c in numbers):
            uncheckable.append({"rule": "F1", "sentence": n,
                                "why": "the count is neither the line's standing nor its change"})  # fmt: skip
        return {"held": held, "uncheckable": uncheckable}, True
    if len(materials) > 1 and not any(h.startswith("x") for h in handles):
        pairs = []
        for c in numbers:
            sized = [m for m in materials if isinstance(m.get("balance"), int)
                     and abs(m["balance"]) == abs(c)]  # fmt: skip
            if len(sized) != 1:
                uncheckable.append({"rule": "F1", "sentence": n, "why":
                                    f"{len(sized)} cited material propositions of size {abs(c)}"})  # fmt: skip
                return {"held": held, "uncheckable": uncheckable}, True
            if sized[0] not in pairs:
                pairs.append(sized[0])
        for prop in pairs:
            held += _material_rules(n, prop, records, standing, [],
                                    phrased=standing[0] in AMBIGUOUS_STANDING, strict=v4)  # fmt: skip
        return {"held": held, "uncheckable": uncheckable}, True
    return {"held": held, "uncheckable": uncheckable}, False


def _cited_lines(explicit: list, handles: list) -> list[str]:
    """The distinct lines a sentence cites: its line and score handles (a search's score carries
    its line: "7.Bxb5 … 7...cxb5" may run on into it) and its propositions' lines."""

    refs = [h for h in handles if h[:1] in ("x", "s")]
    refs += [p["line"] for p in explicit
             if isinstance(p.get("line"), str) and p["line"].startswith("x")]  # fmt: skip
    return list(dict.fromkeys(refs))


def _ledger_of(records: dict, ref: str) -> dict | None:
    _kind, item = records.get(ref, (None, None))
    book = (item or {}).get("ledger") if isinstance(item, dict) else None
    return book if isinstance(book, dict) and book.get("plies") else None


def _named_ply(text: str, book: dict, whole: bool = False) -> int:
    """The ply a sentence reads the line at: a ply it names ("6수 시점"), else the last move of
    the line it writes ("7...cxb5"), else the line's end."""

    rows = book.get("plies") or []
    named = [int(m.group(1)) for m in NAMED_PLY.finditer(text) if 0 < int(m.group(1)) <= len(rows)]
    if named:
        return named[-1]
    def writes(san: str) -> bool:  # v5 (RV-1 P5-7): "d5" is not written by "Qxd5"
        if not whole:
            return san in text
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(san)}(?![A-Za-z0-9])", text) is not None

    written = [i + 1 for i, row in enumerate(rows)
               if isinstance(row.get("san"), str) and row["san"] != "?" and writes(row["san"])]  # fmt: skip
    return max(written) if written else len(rows)


def _gain_words(change: int) -> str:
    if change == 0:
        return "물질은 그대로다"
    return f"백이 {abs(change)}점을 {'얻는다' if change > 0 else '잃는다'}"


def _lead_words(standing: int) -> str:
    if standing == 0:
        return "같은 물질"
    return f"{'백' if standing > 0 else '흑'}이 {abs(standing)}점 앞선 자리"


def _not_unique(materials: list, handles: list, numbers: list[int], v2: bool = False) -> str | None:
    if any(h.startswith("x") for h in handles):
        return "a material number may come from a cited handle"
    if len(materials) != 1:
        return f"{len(materials)} cited material propositions"
    balance = materials[0].get("balance")
    if not numbers or (len(numbers) != 1 and not v2):
        return f"{len(numbers)} counts in the sentence"
    # v2: several counts, all the proposition's number ("3점을 잃고 … -3으로"), read as one
    if not isinstance(balance, int) or any(abs(c) != abs(balance) for c in numbers):
        return "the count is not the cited proposition's"
    return None


def _material_rules(n: int, prop: dict, records: dict, standing: list, whole: list,
                    phrased: bool = False, strict: bool = False) -> list[dict]:  # fmt: skip
    """F1 and F2 on one cited `material` proposition; `strict` (v4): F1 only when the change and
    the standing differ in size, and the replies name no ledger field."""

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
        sized = not strict or not isinstance(change, int) or abs(change) != abs(at_end)
        if for_side != change and sized:
            leader = "백" if at_end > 0 else "흑" if at_end < 0 else "어느 쪽도 아닌"
            reply = (
                f"{prop.get('id')}는 {start}–{end}수 동안 {_side(side)}의 물질 변화({change:+d})이지 "
                f"앞선 정도가 아니다. {end}수 뒤 물질은 {leader} 쪽이 {abs(at_end)}점 앞선다"
                + ("." if strict else "(원장의 standing)."))  # fmt: skip
            if phrased:  # v2: the phrase, not a standing word, is what reads as the standing
                said = (f"{_side(side)}이 {abs(change)}점을 {'얻는다' if change > 0 else '잃는다'}"
                        if change else "물질은 그대로다")  # fmt: skip
                reply += (f" '{standing[0]}'는 앞선 정도로 읽힌다: 변화는 '{said}'처럼 얻고 잃은 "
                          f"양으로 쓰라.")  # fmt: skip
            out.append({"rule": "F1", "sentence": n, "reply": reply})
    tail = _standing_at(ledger, length)
    origin = _standing_at(
        ledger, 0
    )  # the whole line from its start, not the segment's (PR #163 F1)
    whole_change = None
    if tail is not None and origin is not None and side in ("white", "black"):
        whole_change = (tail - origin) if side == "white" else (origin - tail)
    partial = start > 0 or end < length
    # A8: a segment written as the whole line is wrong only when the whole line's change differs
    if whole and partial and whole_change is not None and whole_change != change:
        out.append({"rule": "F2", "sentence": n, "reply": (
            f"{prop.get('id')}는 라인 {length}수 중 {start}–{end}수 구간이다. 라인 끝의 "
            f"{'물질은' if strict else 'standing은'} 백 기준 {tail:+d}." if tail is not None else
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
    return [
        {
            "rule": "F3",
            "sentence": n,
            "reply": (
                f"인용한 판정({move or prop.get('judgement')})의 등급은 {shown}이다: '{word}'가 아니다."
            ),
        }
    ]


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
            plies = plies[int(prop.get("from", 0)) : int(prop.get("to", 0))]
        if any(x.get("source") == "search" for x in plies):
            return True
        if kind == "search_line" and "search" not in item:  # the analysis's lines carry `search`
            return True
    return False
