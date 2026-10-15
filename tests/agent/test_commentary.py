"""AG-D §11 tests 6 and 7: the sentence check (S1–S6) and `submit_commentary` — an accepted
commentary stored with its resolved sources, a refused one leaving nothing."""

from __future__ import annotations

import pytest
from agent_helpers import GAME, session

from calliope.agent.sentences import Allowed, check_sentences, check_token, tokens

# -- S3: tokens and their rules -------------------------------------------------------------------


def test_the_tokens_of_korean_text() -> None:
    assert tokens("17...Rxe3로 백이 이긴다.") == ["17...Rxe3"]
    assert tokens("17. Ne3는 +0.38, Kd1은 −0.38이다.") == ["17. Ne3", "+0.38", "Kd1", "-0.38"]
    # AG-D AM2: dashes and minus signs read as `-`, full-width letters and digits as ASCII
    assert tokens("균형은 –2점, ３수, Ｍ３, ⁻1.00, 끝은 3.") == ["-2", "3", "M3", "-1.00", "3"]
    assert tokens("O-O 이후 e4, M3 또는 #3; 0-0과 Stockfish16") == [
        "O-O", "e4", "M3", "#3", "0-0", "Stockfish16"]  # fmt: skip
    assert tokens("17.Ne3. 그리고 0.385") == ["17.Ne3", "0.385"]


START = "rn2r3/p2p1k1p/b7/1pp2N2/8/2P5/P2N1PPP/R1B1KB1R w KQ - 3 17"  # g1014, before 17.Ne3


def _allowed() -> Allowed:
    a = Allowed()
    a.add_move("f5e3", START)  # 17.Ne3 (and its squares f5, e3, the move number 17)
    a.add_line("rn2r3/p2p1k1p/b7/1pp5/8/2P1N3/P2N1PPP/R1B1KB1R b KQ - 4 17", ["e8e3"])  # 17...Rxe3
    a.scores |= {933, -38}
    a.mates.add(3)
    a.integers |= {3, -3}
    return a


@pytest.mark.parametrize(
    ("token", "ok"),
    [
        ("17.Ne3", True), ("17. Ne3", True), ("Ne3", True), ("17...Ne3", False),
        ("18.Ne3", False), ("17...Rxe3", True), ("17.Rxe3", False), ("Nf3", False),
        ("e3", True), ("e4", False), ("+9.33", True), ("9.33", True), ("9.3", True),
        ("-9.33", False), ("-0.38", True), ("−0.38", True), ("0.38", False), ("0.385", False),
        ("M3", True), ("#3", True), ("M4", False), ("3", True), ("-3", True), ("+3", True),
        ("5", False), ("0-0", False), ("Stockfish16", False), ("Ne9", False), ("O-O", False),
        ("O-O+", False), ("Ne3+", False), ("Ne3#", False), ("Nxe3", False), ("17...Re3", False),
        ("17...Rxe3+", True), ("17...Rxe3#", False), ("17", True),
    ],
)  # fmt: skip
def test_each_token_rule(token: str, ok: bool) -> None:
    assert (check_token(token, _allowed()) is None) == ok, check_token(token, _allowed())


def test_capture_check_and_mate_marks_must_hold() -> None:
    """Review B2: `x`, `+` and `#` claim a capture, a check, a mate; they must hold."""

    a = Allowed()
    fools = "rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2"
    a.add_move("d8h4", fools)  # 2...Qh4#
    a.add_move("e1g1", "r3k2r/8/8/8/8/8/8/4K2R w Kkq - 0 1")  # O-O, then Rf1 gives no check
    assert check_token("2...Qh4#", a) is None and check_token("Qh4", a) is None
    assert check_token("Qh4+", a) is not None  # a mate is not written as a mere check
    assert check_token("Qxh4#", a) is not None
    assert check_token("O-O", a) is None and check_token("O-O+", a) is not None
    ends = check_sentences("ko", [{"text": "그 수는 17.", "class": "sourced", "cites": ["p"]}],
                           {"p": _allowed()})  # a lone move number reads as its integer (AM2)  # fmt: skip
    assert ends == []


def test_a_sign_or_a_digit_does_not_hide_in_other_characters() -> None:
    """Review B3: an en dash, a full-width minus, full-width digits and letters."""

    a = Allowed()
    a.integers.add(2)  # a balance of +2
    a.scores.add(100)
    a.mates.add(4)
    problems = lambda text: check_sentences(
        "ko", [{"text": text, "class": "sourced", "cites": ["p"]}], {"p": a}
    )
    assert problems("균형은 2점이다.") == []
    assert problems("균형은 –2점이다.") and problems("평가는 –1.00이다.")
    assert problems("평가는 －1.00이다.") and problems("백은 Ｍ３로 이긴다.")
    assert problems("백은 ３수 만에 이긴다.")
    assert problems("백은 ٣수 만에 이긴다.")[0]["problem"] == "digits other than 0-9"


def test_a_move_number_holds_across_any_whitespace() -> None:
    """Re-review B3: `17.  Rxe3` (17...Rxe3 is black's) split into `17` and `Rxe3`, both cited."""

    problems = lambda text: check_sentences(
        "ko", [{"text": text, "class": "sourced", "cites": ["p"]}], {"p": _allowed()}
    )
    for text in ("17.  Rxe3", "17.\tRxe3", "17.\nRxe3", "17 . Rxe3", "17\u00a0.\u3000Rxe3",
                 "17.. Rxe3", "17 .. Rxe3"):  # fmt: skip
        assert problems(f"{text}로 교환한다."), text
        assert tokens(text)[0].startswith("17"), text
    for text in ("17... Rxe3", "17...  Rxe3", "17 ... Rxe3", "17...\nRxe3", "17.\tNe3"):
        assert problems(f"{text}로 교환한다.") == [], text


def test_a_sign_a_number_and_a_move_number_hold_across_any_gap() -> None:
    """Re-review B4: a sign apart from its number, an invisible character between a move number
    and its move; AM4 also a mate mark apart, a homoglyph and a combining mark on a token."""

    a = Allowed()
    a.integers |= {2, 3}  # a balance of +2, a count of 3
    a.scores.add(100)  # +1.00
    a.add_line("rn2r3/p2p1k1p/b7/1pp5/8/2P1N3/P2N1PPP/R1B1KB1R b KQ - 4 17", ["e8e3"])  # 17...Rxe3
    problems = lambda text: check_sentences(
        "ko", [{"text": text, "class": "sourced", "cites": ["p"]}], {"p": a}
    )
    for text in ("평가는 - 1.00이다.", "백은 − 2점을 얻었다.", "평가는 -(1.00)이다.",
                 "평가는 -약 1.00이다.", "17.\u200bRxe3로 교환한다.", "17.\u3164Rxe3로 교환한다.",
                 "17.\uffa0Rxe3로 교환한다.", "17.\u2800Rxe3로 교환한다.", "백은 M 3로 이긴다.",
                 "백은 # 3로 이긴다.", "Rx\u04353로 교환한다.", "평가는 1\u0301.00이다.",
                 "백은 2점을 얻었다 - 3수 동안."):  # a dash before a number is its sign  # fmt: skip
        assert problems(text), text
    for text in ("평가는 - 약 1.00이다.", "평가는 - (+1.00)이다.", "백은 M 약 3로 이긴다.",
                 "백은 2점을 얻었다 - 그 뒤 3수 동안.", "Rxe3 — 백은 2점을 얻는다.",
                 "Rxe3 - 17...Rxe3로 교환한다."):  # B5; a dash before a digit is a sign  # fmt: skip
        assert problems(text), text
    for text in ("평가는 + 1.00이다.", "백은 2점을 얻는다 — 좋은 수다.", "Rxe3 — 좋은 수다.",
                 "17...\u200bRxe3로 교환한다.",
                 "Rxe3로 교환한다 -", "M과 #은 메이트를 뜻한다."):  # fmt: skip
        assert problems(text) == [], text


def test_a_signed_integer_needs_its_sign() -> None:
    a = Allowed()
    a.integers.add(3)  # a balance of +3
    assert check_token("-3", a) is not None and check_token("3", a) is None
    assert check_token("+3", a) is None


def test_s1_and_s2() -> None:
    allowed = {"p1": _allowed()}
    ok = [{"text": "17.Ne3는 최선이다.", "class": "sourced", "cites": ["p1"]}]
    assert check_sentences("ko", ok, allowed) == []
    rules = lambda problems: [p["rule"] for p in problems]
    assert rules(check_sentences("en", ok, allowed)) == ["S1"]
    assert rules(check_sentences("ko", [], allowed)) == ["S1"]
    assert rules(check_sentences("ko", ok * 13, allowed)) == ["S1"]
    assert "S1" in rules(check_sentences("ko", [ok[0] | {"text": "가" * 301}], allowed))
    assert rules(check_sentences("ko", [ok[0] | {"class": "interpretation"}], allowed)) == ["S1"]
    assert rules(check_sentences("ko", [ok[0] | {"cites": []}], allowed)) == ["S2"]
    assert rules(check_sentences("ko", [ok[0] | {"cites": ["p9"]}], allowed)) == ["S2"]
    assert rules(check_sentences("ko", [ok[0] | {"cites": [{"id": "p1"}]}], allowed)) == ["S2"]
    interpretation = {
        "text": "18.Ne3였다면 좋았을 것이다.",
        "class": "interpretation",
        "cites": ["p1"],
    }
    assert rules(check_sentences("ko", [*ok, interpretation], allowed)) == ["S3"]  # S4


# -- submit_commentary ----------------------------------------------------------------------------


@pytest.fixture
def s(tmp_path):
    s = session(tmp_path)
    s.open_game(pgn=GAME)
    yield s
    s.close()


def _submission(s) -> dict:
    record = s.ply("g1", 3)
    j = record["analysis"]["judgements"][0]
    claim = next(c for c in record["analysis"]["claims"] if c["status"] == "supported")
    x = s.explore("g1", {"ply": 4, "at": "after"}, ["Nc3", "Nxd5", "Nxd5", "Qxd5"])
    cp = j["best"]["score"]["cp"]
    propositions = [
        {"id": "p1", "kind": "judgement", "judgement": j["ref"], "move": "exd5",
         "grade": j["grade"], "label": j["label"], "best_move": j["best"]["move"]["san"]},
        {"id": "p2", "kind": "engine_score", "line": j["best"]["ref"],
         "move": j["best"]["move"]["uci"], "score": j["best"]["score"]},
        {"id": "p3", "kind": "material", "line": x["ref"], "from": 0, "to": 3, "side": "white",
         "balance": 2},
        {"id": "p4", "kind": "claim", "claim": claim["ref"], "use": "line_fact",
         "scopes": claim["effective_scopes"]},
    ]  # fmt: skip
    sentences = [
        {"text": f"2.exd5는 {j['grade']}이다.", "class": "sourced", "cites": ["p1"]},
        {"text": f"엔진은 {j['best']['move']['san']}에 {cp / 100:+.2f}을 준다.", "class": "sourced",
         "cites": ["p2"]},
        {"text": "3.Nc3 Nxd5 4.Nxd5에서 백은 2점을 얻는다.", "class": "sourced", "cites": ["p3"]},
        {"text": "중앙을 서두른 수로 보인다.", "class": "interpretation", "cites": ["p4"]},
    ]  # fmt: skip
    return {"propositions": propositions, "sentences": sentences}


def test_an_accepted_commentary_is_stored_with_its_sources(s, tmp_path) -> None:
    submission = _submission(s)
    answer = s.submit_commentary("g1", ply=3, agent={"name": "t", "model": "m"}, **submission)
    assert answer["accepted"] and answer["level"] == "SOURCE_VERIFIED", answer
    [stored] = s.commentary("g1", 3)["commentaries"]
    assert stored["id"] == answer["id"] and stored["stale"] is False
    assert stored["subject"] == {"path": ["e2e4", "d7d5", "e4d5"], "ply": 3, "played": True}
    assert stored["bundle"]["tree"] == s.ply("g1", 3)["bundle"]["tree"]
    judgement = stored["propositions"][0]
    assert judgement["sources"][0]["source"]["path"] == ["e2e4", "d7d5", "e4d5"]
    assert "item" not in judgement["sources"][0]  # the source, not the served answer
    assert [x["by_agent"] for x in stored["sentences"]] == [False, False, True, False]
    assert stored["sentences"][3]["class"] == "interpretation"
    assert stored["agent_build"]["tools"] == "agent_tools_v3"
    files = list((tmp_path / "commentary").rglob("*.json"))
    assert len(files) == 1 and not list((tmp_path / "commentary").rglob("*.tmp"))


def test_a_refused_commentary_names_every_violation_and_stores_nothing(s, tmp_path) -> None:
    submission = _submission(s)
    submission["propositions"][0]["grade"] = "blunder"  # not Calliope's grade
    submission["sentences"][1]["text"] = "엔진은 +7.77을 준다."
    answer = s.submit_commentary("g1", ply=3, agent={"name": "t"}, **submission)
    assert not answer["accepted"]
    found = {(v.get("proposition"), v.get("rule"), v.get("field")) for v in answer["violations"]}
    assert ("p1", None, "grade") in found and (None, "subject", None) in found
    assert any(v.get("token") == "+7.77" for v in answer["violations"])
    assert any(v.get("problem", "").startswith("no verified proposition") for v in
               answer["violations"])  # the sentence citing p1  # fmt: skip
    assert not (tmp_path / "commentary").exists()


def test_the_subject_needs_its_own_judgement(s) -> None:
    submission = _submission(s)
    other = s.ply("g1", 2)["analysis"]["judgements"][0]
    submission["propositions"][0] = {"id": "p1", "kind": "judgement", "judgement": other["ref"],
                                     "move": other["move"]["uci"], "grade": other["grade"],
                                     "label": other["label"],
                                     "best_move": other["best"]["move"]["uci"]}  # fmt: skip
    submission["sentences"][0]["text"] = "이 수는 판정을 받았다."
    answer = s.submit_commentary("g1", ply=3, agent={"name": "t"}, **submission)
    assert [v["rule"] for v in answer["violations"]] == ["subject"]


def test_a_sentence_with_no_token_citing_an_unrelated_claim_is_only_source_verified(s) -> None:
    """The review's B1 case: accepted, as SOURCE_VERIFIED only — the wording is not verified."""

    submission = _submission(s)
    submission["sentences"] = [submission["sentences"][0],
                               {"text": "이 수는 상대의 퀸을 잡는다.", "class": "sourced",
                                "cites": ["p4"]}]  # fmt: skip
    answer = s.submit_commentary("g1", ply=3, agent={"name": "t"}, **submission)
    assert answer["accepted"] and answer["level"] == "SOURCE_VERIFIED"
    stored = s.commentary("g1", 3)["commentaries"][0]
    assert stored["check"] == "commentary_check_v1" and stored["level"] == "SOURCE_VERIFIED"


def test_a_judged_move_is_a_subject(s) -> None:
    judged = s.judge_move("g1", {"ply": 3, "at": "before"}, "Nc3")
    j = judged["analysis"]["judgements"][0]
    p = {"id": "p1", "kind": "judgement", "judgement": j["ref"], "move": "Nc3",
         "grade": j["grade"], "label": j["label"], "best_move": j["best"]["move"]["uci"]}  # fmt: skip
    sentence = {"text": "2.Nc3도 둘 만했다.", "class": "sourced", "cites": ["p1"]}
    answer = s.submit_commentary("g1", position={"ply": 3, "at": "before"}, move="Nc3",
                                 agent={"name": "t"}, propositions=[p], sentences=[sentence])  # fmt: skip
    assert answer["accepted"], answer
    stored = s.commentary("g1", position={"ply": 3, "at": "before"}, move="Nc3")
    assert stored["commentaries"][0]["subject"]["played"] is False
