"""The change log, 2026-11-10, "the standing read from the cited line": harness rev. 11's frame check
v3. Every case is a sentence of judging 94d6ca40 (rev. 10), with the line its record held."""

from __future__ import annotations

from tools.rx import frames
from tools.rx import score as rx_score
from tools.rx.harness import FRAMES, PER_MOMENT, VERSIONS

V2, V3 = frames.FRAMES_V2, frames.FRAMES_V3


def _book(start: int, rows: list[tuple[str, int]]) -> dict:
    return {"standing": {"start": {"white_minus_black": start}},
            "plies": [{"san": san, "source": "analysis", "standing_white": x} for san, x in rows]}  # fmt: skip


# 185264271324-29: 15.O-O Bd3 16.Qe3 Bxf1 17.Kxf1 O-O 18.a4 Nd7, White one up at the start
X5 = ("x5.t", ("explored_line", {"ledger": _book(1, [
    ("15.O-O", 1), ("15...Bd3", 1), ("16.Qe3", 1), ("16...Bxf1", -4), ("17.Kxf1", -1),
    ("17...O-O", -1), ("18.a4", -1), ("18...Nd7", -1)])}))  # fmt: skip
# 185264271324-67: 34.Bb2+ Qxb2+ … 37.Kxf4, Black one up at the start
X23 = ("x23.t", ("explored_line", {"ledger": _book(-1, [
    ("34.Bb2+", -1), ("34...Qxb2+", -4), ("35.Kg3", -4), ("35...Qe5+", -4), ("36.Qf4+", -4),
    ("36...Qxf4+", -13), ("37.Kxf4", -4), ("37...Kf7", -4), ("38.Kg4", -4)])}))  # fmt: skip
# 185264271324-45: 23.Rxe5 Rxe5 24.dxe5 Qxe5 25.Nxc4 Qxc3, level at the start
X18 = ("x18.t", ("explored_line", {"ledger": _book(0, [
    ("23.Rxe5", 3), ("23...Rxe5", -2), ("24.dxe5", 3), ("24...Qxe5", 2), ("25.Nxc4", 3),
    ("25...Qxc3", 2)])}))  # fmt: skip
RECORDS = dict([X5, X23, X18])


def _call(text: str, cites: list[str], props: list[dict] = ()) -> dict:
    return {"items": [{"ply": 1, "propositions": list(props),
                       "sentences": [{"text": text, "cites": cites}]}]}  # fmt: skip


def _rules(out: dict) -> list[str]:
    return sorted(h["rule"] for h in out["held"])


def test_revision_11_is_revision_10_with_the_frame_check_v3() -> None:
    assert VERSIONS[11] == VERSIONS[10] and 11 in PER_MOMENT
    assert FRAMES[10] == V2 and FRAMES[11] == V3
    import inspect

    assert "default=1" in inspect.getsource(rx_score.main)  # rev. 11 or later (12: WG-D)


def test_two_changes_written_as_the_difference_are_held() -> None:
    """8856bf87 #2: "-5가 되었다가 … -2로" — the changes to plies 4 and 5; the standings are -4, -1."""

    props = [{"id": "p1", "kind": "explored_line", "line": "x5.t", "moves": []},
             {"id": "p2", "kind": "material", "line": "x5.t", "from": 0, "to": 4, "side": "white",
              "balance": -5},
             {"id": "p3", "kind": "material", "line": "x5.t", "from": 0, "to": 5, "side": "white",
              "balance": -2}]  # fmt: skip
    text = (
        "엔진 라인에서 16.Qe3로 퀸이 e2를 떠나자 룩은 16...Bxf1에 잡히고, 17.Kxf1로 흑 비숍을 "
        "되잡습니다. 백은 룩을 잃어 물질 차이가 -5가 되었다가 비숍을 되잡고 -2로 남습니다."
    )
    call = _call(text, ["p1", "p2", "p3", "c7.t"], props)
    assert frames.check(call, RECORDS, V2)["held"] == []  # v2: two propositions, uncheckable
    out = frames.check(call, RECORDS, V3)
    assert _rules(out) == ["F1", "F1"] and out["version"] == V3
    replies = " ".join(h["reply"] for h in out["held"])
    assert "흑 쪽이 4점" in replies and "흑 쪽이 1점" in replies and "'물질 차이'" in replies


def test_a_lead_that_did_not_cross_over_is_held() -> None:
    """a869f4f9 #4: Black was one up before the line; it crossed nothing."""

    out = frames.check(_call("이 라인이 끝난 뒤 standing은 흑 쪽으로 넘어가 흑이 앞섭니다.", ["x23.t"]),
                       RECORDS, V3)  # fmt: skip
    assert _rules(out) == ["F4", "F6"]
    f4 = next(h for h in out["held"] if h["rule"] == "F4")["reply"]
    assert "-1에서 9수 뒤 -4" in f4 and "흑이 1점 앞선 자리" in f4


def test_a_lead_that_did_cross_over_is_not_held() -> None:
    """8856bf87 #3, in words: White +1 to Black +1."""

    out = frames.check(_call("이 라인에서 물질은 백 쪽 우위에서 흑 쪽 우위로 넘어갑니다.", ["x5.t"]),
                       RECORDS, V3)  # fmt: skip
    assert out["held"] == []


def test_a_ledger_term_is_held_whatever_the_sentence_says() -> None:
    text = "이 라인에서 standing은 백 쪽 우위에서 흑 쪽 우위로 넘어갑니다."  # 8856bf87 #3, right
    out = frames.check(_call(text, ["x5.t"]), RECORDS, V3)
    assert _rules(out) == ["F6"] and "'standing'" in out["held"][0]["reply"]
    assert frames.check(_call(text, ["x5.t"]), RECORDS, V2)["held"] == []
    # a move or a handle is not a term
    clean = frames.check(_call("25.Nxc4 뒤 나이트는 c4에 선다.", ["x18.t"]), RECORDS, V3)
    assert clean["held"] == []


def test_no_change_is_held_against_the_line_read_at_its_named_move() -> None:
    text = "백이 16...Bxf1에 룩을 잃고 17.Kxf1로 되잡아도 물질 변화가 없다."
    out = frames.check(_call(text, ["x5.t"]), RECORDS, V3)
    assert _rules(out) == ["F5"]  # +1 to -1 at 17.Kxf1 (ply 5)
    assert (
        "+1에서 -1로" in out["held"][0]["reply"] and "백이 2점을 잃는다" in out["held"][0]["reply"]
    )
    level = {"x26.t": ("explored_line", {"ledger": _book(-1, [("34.Qf4+", -1), ("34...Kg6", -1)])})}
    m2 = {"id": "m2", "kind": "material", "line": "x26.t", "from": 0, "to": 2, "side": "white",
          "balance": 0}  # fmt: skip
    right = _call("34.Qf4+ 라인은 최선 라인 전체에서 물질 변화가 없다.", ["m2", "x26.t"], [m2])
    assert frames.check(right, level, V3)["held"] == []  # a869f4f9 #6: one line, no change


def test_no_change_over_two_lines_is_uncheckable() -> None:
    """f8ee0f37 #6: 7.Bxb5 in the explored line, 7...cxb5 in a search's line — two lines."""

    records = dict(RECORDS, **{"x1.t": ("explored_line", {"ledger": _book(0, [
        ("6...c6", 0), ("7.Bxb5", 1)])})})  # fmt: skip
    text = "같은 7.Bxb5를 최선수 6...c6 뒤에 두면 흑은 7...cxb5로 되잡고 물질 변화가 없다."
    out = frames.check(_call(text, ["x1.t", "s12.t"]), records, V3)
    assert out["held"] == []  # read in x1 alone it would say "+1", which is not the claim
    assert out["uncheckable"] == [{"rule": "F5", "sentence": 1, "why": "2 cited lines"}]


def test_a_change_read_through_a_handle_is_held() -> None:
    """A standing phrase citing only the line handle, with the change as its count."""

    out = frames.check(_call("16...Bxf1 뒤 이 라인의 백 물질은 -5입니다.", ["x5.t"]), RECORDS, V3)
    assert _rules(out) == ["F1"]
    assert (
        "물질 변화" in out["held"][0]["reply"] and "흑이 4점 앞선 자리" in out["held"][0]["reply"]
    )
    assert frames.check(_call("16...Bxf1 뒤 이 라인의 백 물질은 -5입니다.", ["x5.t"]), RECORDS,
                        V2)["held"] == []  # fmt: skip


def test_a_standing_read_through_a_handle_is_not_held() -> None:
    """670e5617 (rev. 10): "6수 시점에서 백 물질은 +2" citing x18 — right."""

    out = frames.check(_call("둔 수 뒤 흑은 23...Rxe5로 백 룩을 잡고, 24.dxe5 Qxe5 25.Nxc4 Qxc3 "
                             "순서가 됩니다. 6수 시점에서 백 물질은 +2입니다.", ["x18.t"]), RECORDS, V3)  # fmt: skip
    assert out["held"] == []
    assert frames.check(_call("16...Bxf1 뒤 이 라인의 백 물질은 -4입니다.", ["x5.t"]), RECORDS,
                        V3)["held"] == []  # fmt: skip


def test_v3_keeps_v2() -> None:
    from test_sides import RECORDS as V2_RECORDS
    from test_sides import _call as v2_call

    out = frames.check(v2_call("이 라인의 백 물질 차이는 9입니다."), V2_RECORDS, V3)
    assert _rules(out) == ["F1"] and out["ambiguous"]
    denied = frames.check(v2_call("이 라인의 물질 차이는 9가 아니다."), V2_RECORDS, V3)
    assert denied["held"] == []
