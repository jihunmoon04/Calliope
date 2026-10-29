"""CV4-D over the synthetic engine: the notes on what a sentence cites (§2), `states_items` still
on what it states, and S8 without kana and CJK ideographs (§3)."""

from __future__ import annotations

import pytest
from agent_helpers import GAME, session

from calliope.agent.board import canonical
from calliope.agent.sentences import Allowed, check_sentences
from calliope.agent.session import _notes, _stated


@pytest.fixture
def s(tmp_path):
    s = session(tmp_path)
    yield s
    s.close()


def _open(s, plies: int = 4):
    return s.open_game(pgn=GAME, plies=f"1-{plies}")["game"]


def _submit(s, game, ply, sentences, propositions=None):
    return s.submit_commentary(game, ply=ply, agent={"name": "t"}, propositions=propositions,
                               sentences=sentences)  # fmt: skip


def _stored(s, game, ply) -> dict:
    return s.store.for_subject(s.game(game).key, tuple(s.game(game).parsed.uci[:ply]))[0]  # newest


def _rules(answer: dict) -> list[tuple[str, int | None]]:
    return [(n["rule"], n.get("sentence")) for n in answer.get("notes", ())]


# -- the notes on what a sentence cites (§2) ----------------------------------------------------


def test_reasons_cited_by_handle_without_states_get_no_note(s) -> None:
    """§0's example: the reason cited, no `states` — under v3 both notes, now none."""

    game = _open(s)
    d = s.ply(game, 2)
    item = d["board"]["changes"][0]["ref"]
    answer = _submit(s, game, 2, [
        {"text": "판정을 받은 수다.", "class": "sourced", "cites": [d["judgement"], item]},
        {"text": "중앙을 다투는 수로 보인다.", "class": "interpretation", "cites": [item]},
    ])  # fmt: skip
    assert answer["accepted"], answer
    assert "notes" not in answer
    stored = _stored(s, game, 2)["sentences"]
    assert all("states" not in x and "states_items" not in x for x in stored)


def test_the_notes_are_off(s) -> None:
    """ST-D §6 (owner O2): `commentary_check_v6` gives no note — what v4 told here (N-reason and
    N-reading) is not said; the sentence check is unchanged."""

    game = _open(s)
    d = s.ply(game, 2)
    answer = _submit(s, game, 2, [
        {"text": "판정을 받은 수다.", "class": "sourced", "cites": [d["judgement"]]},
        {"text": "중앙을 다투는 수로 보인다.", "class": "interpretation", "cites": [d["judgement"]]},
    ])  # fmt: skip
    assert answer["accepted"] and "notes" not in answer


def test_states_items_read_what_a_sentence_states_not_what_it_cites(s) -> None:
    """Review focus: the notes on `cites` leave `states_items` as it was."""

    game = _open(s)
    d = s.ply(game, 2)
    first, second = d["board"]["changes"][:2]
    answer = _submit(s, game, 2, [
        {"text": "판정을 받은 수다.", "class": "sourced", "cites": [d["judgement"]]},
        {"text": first["proves"], "class": "sourced", "cites": [first["ref"], second["ref"]],
         "states": [first["ref"]]},
    ])  # fmt: skip
    assert answer["accepted"], answer
    stored = _stored(s, game, 2)["sentences"][1]
    assert stored["states_items"] == [0]  # the second item is cited whole, not stated


# v4's notes within v3's (§2): `states` is within `cites` (S7a), so what silences a v3 note
# silences the v4 one. Over records of every part and a served item of two propositions.
_RECORDS = {
    "j": {"kind": "judgement", "judgement": "j1.x"},
    "fork": {"kind": "claim", "template": "fork_v2", "claim": "c1.x"},
    "gain": {"kind": "claim", "template": "material_gain_v3", "claim": "c2.x"},
    "better": {"kind": "claim", "template": "better_move_v1", "claim": "c3.x"},
    "line": {"kind": "engine_line", "line": "s1.x", "moves": ["e2e4"]},
    "a0": {"kind": "attack", "attacker": "d5", "target": "e4"},
    "a1": {"kind": "defence", "defender": "d8", "target": "d5"},
}  # fmt: skip
_SERVED = {"items": [{"index": 0, "part": "reason",
                      "canonical": [canonical(_RECORDS["a0"]), canonical(_RECORDS["a1"])]}],
           "reason": True}  # fmt: skip


def _both(sentences: list[dict], served: dict | None) -> tuple[set, set]:
    v3 = _notes(sentences, [_stated(x.get("states", []), _RECORDS, served)[1]
                            for x in sentences], served)  # fmt: skip
    v4 = _notes(sentences, [_stated(x["cites"], _RECORDS, served)[1] for x in sentences], served)
    return ({(n["rule"], n.get("sentence")) for n in v3},
            {(n["rule"], n.get("sentence")) for n in v4})  # fmt: skip


def _sentence(marks: tuple[int, ...], klass: str) -> dict | None:
    """Each record not cited (0), cited (1) or cited and stated (2)."""

    ids = list(_RECORDS)
    cites = [i for i, m in zip(ids, marks, strict=True) if m]
    if not cites:
        return None
    return {"class": klass, "cites": cites,
            "states": [i for i, m in zip(ids, marks, strict=True) if m == 2]}  # fmt: skip


# -- S8 without kana and CJK ideographs (§3) -----------------------------------------------------


def _s8(text: str) -> list[tuple[str | None, str]]:
    sentence = {"text": text, "class": "sourced", "cites": ["j"]}
    return [(v.get("token"), v["problem"]) for v in check_sentences("ko", [sentence], {"j": Allowed()})
            if v["rule"] == "S8"]  # fmt: skip


NO_HANGUL = "a sentence of a ko commentary is written in Korean"
KANA = "a sentence of a ko commentary is written in Korean, without kana or CJK ideographs"


@pytest.mark.parametrize(("text", "token"), [
    ("흑은 중앙을 우선하는ほう이 나았다.", "ほう"),  # hiragana
    ("흑은 タイミング을 놓쳤다.", "タイミング"),  # katakana
    ("흑은 ﾀｲﾐﾝｸﾞ을 놓쳤다.", "タイミング"),  # half-width katakana, read after NFKC
    ("폰으로 압박하는計画보다 낫다.", "計画"),  # a kanji
    ("그 수는 惡手였다.", "惡手"),  # Hanja
    ("그 수는 𠀀였다.", "𠀀"),  # Extension B
    ("그 수는 𚿰였다.", "𚿰"),  # Kana Extended-B (review N1)
    ("그 수는 々였다.", "々"),
    ("그 수는 \ufa0e였다.", "\ufa0e"),  # a compatibility ideograph NFKC keeps (review N7)
])  # fmt: skip
def test_kana_and_cjk_ideographs_are_refused_with_the_characters(text, token) -> None:
    assert _s8(text) == [(token, KANA)]


def test_cjk_punctuation_alone_is_accepted() -> None:
    assert _s8("흑은 중앙을、 백은 측면을 노린다。") == []
    assert _s8("1・2위 후보수가 같다.") == [] and _s8("1･2위 후보수가 같다.") == []  # review N1


def test_each_run_of_kana_or_cjk_is_named_apart() -> None:
    """Review N2: characters apart are not joined into a word the sentence does not write."""

    assert _s8("나이트를 전진시키는積極적 선택이지만 비숍을 전개하는ほうが 낫다.") == [
        ("積極 ほうが", KANA)
    ]
    assert _s8("計 画이다.") == [("計 画", KANA)]


def test_the_two_s8_conditions_apart() -> None:
    """Review N2: no Hangul → the existing violation; kana → the new one; both → both."""

    assert _s8("1...d5 attacks the pawn.") == [(None, NO_HANGUL)]
    assert _s8("흑은 폰을 では 잡는다.") == [("では", KANA)]
    assert _s8("ほうが良い") == [(None, NO_HANGUL), ("ほうが良い", KANA)]


def test_the_trials_mixed_sentences_are_refused_and_plain_korean_is_not() -> None:
    mixed = [
        "c6 폰으로 d5를 압박하는計画보다, 퀸을 d6로 두는 편이 이 국면을 더 잘 유지하는 선택으로 보인다.",
        "흑은 중앙의 긴장을 풀기 전에 퀸 수를 우선하는ほう이 나았던 것으로 보인다.",
        "흑은 나이트를 전진시키는積極적 선택을 했지만, 이 자리에서는 비숍을 전개하는ほうが 효과적이었던 것으로 보인다.",
        "이 장면では 룩을 전진시키는 것보다, 곧바로 폰을 잡는 수를 먼저 계산하는 편이 중요했습니다.",
        "백은 b5의 나이트を 내주는 제안을 했고, 분석된 수순에서는 흑이 cxb5로 이를 받아들입니다.",
        "체크와 퀸 공격이 눈에入る場面でも、 먼저 15.Bxf6로 나이트를 정리하는 편이 더 큰 이득을 낳는 계산이었다.",
    ]  # fmt: skip
    for text in mixed:
        assert [p for _, p in _s8(text)] == [KANA], text
    plain = ["13.Rxd7는 최선수이자 브릴리언트로 평가됐다.",
             "룩을 던져 흑의 응수를 강요한 뒤에도 백의 우세가 유지되는, 공격의 주도권을 위한 희생으로 보인다.",
             "앙파상으로 e6의 폰을 잡는다(exd6 e.p.)."]  # fmt: skip
    for text in plain:
        assert _s8(text) == [], text


def test_the_kana_refusal_is_in_korean_with_the_english_kept(s) -> None:
    game = _open(s)
    d = s.ply(game, 2)
    answer = _submit(s, game, 2, [{"text": "판정을 받은 수ほう다.", "class": "sourced",
                                   "cites": [d["judgement"]]}])  # fmt: skip
    (violation,) = answer["violations"]
    assert violation["rule"] == "S8" and violation["token"] == "ほう"
    assert violation["problem"] == "해설 문장은 한국어로 씁니다. 가나나 한자는 쓰지 않습니다"
    assert violation["problem_en"] == KANA
