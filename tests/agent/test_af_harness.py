"""AF (agent-af-design.md §4): harness rev. 8 — the frame check by code (F1–F3), a rule only where
the sentence maps to one cited proposition and one count (`uncheckable` otherwise, review F2 of
rev. 2), holds and states, and the start line's versions."""

from __future__ import annotations

import json

import test_lt_harness as lt

from tools.rx import frames
from tools.rx import run as rx_run
from tools.rx.harness import FRAMES, REVISION, VERSIONS


def _ledger(start: int, standings: list[int]) -> dict:
    return {"standing": {"start": {"white_minus_black": start}},
            "plies": [{"san": "?", "source": "analysis", "standing_white": x} for x in standings]}  # fmt: skip


# 186492056006-22 (AF-D §0.1 row 3): Black ten up at the line's start; White takes the queen
LINE_22 = ("explored_line", {"ledger": _ledger(-10, [-10, -1] + [-1] * 14)})
MATERIAL = {"id": "pm21", "kind": "material", "line": "x21.t", "from": 0, "to": 2, "side": "white",
            "balance": 9}  # fmt: skip
LINE_PROP = {"id": "px21", "kind": "explored_line", "line": "x21.t", "moves": []}


def _call(text: str, props=(MATERIAL, LINE_PROP), cites=("px21", "pm21")) -> dict:
    return {"items": [{"ply": 22, "propositions": list(props),
                       "sentences": [{"text": text, "cites": list(cites)}]}]}  # fmt: skip


RECORDS = {"x21.t": LINE_22}


def test_a_change_written_as_the_standing_is_held_with_the_standing() -> None:
    out = frames.check(_call("둔 수 라인에서 백은 퀸을 그냥 잡고, 라인 전체에서 백이 9점 앞선다."), RECORDS)
    rules = sorted(h["rule"] for h in out["held"])
    assert rules == ["F1", "F2"]  # #2: the standing and the whole line
    f1 = next(h for h in out["held"] if h["rule"] == "F1")
    assert "+9" in f1["reply"] and "흑 쪽이 1점" in f1["reply"]
    assert not out["uncheckable"] and out["version"] == "harness_frames_v1"


def test_moves_and_squares_are_not_counts() -> None:
    text = "11...Qxd1+는 룩 d1을 잡고 12.Nxd1로 퀸을 내주는 교환이고, 그 라인에서 백이 4점 앞선다."
    four = dict(MATERIAL, balance=4)
    out = frames.check(_call(text, (four, LINE_PROP)), {"x21.t": ("explored_line",
                       {"ledger": _ledger(-10, [-5, -6])})})  # fmt: skip
    assert [h["rule"] for h in out["held"]] == ["F1"]  # #3; the line is two plies: no F2


def test_the_reviews_two_count_sentence_is_uncheckable_not_held() -> None:
    text = "백은 이 수순에서 9점을 얻었지만, 전체 물질은 여전히 흑이 1점 앞선다."
    out = frames.check(_call(text), RECORDS)
    assert out["held"] == []
    assert sorted(u["rule"] for u in out["uncheckable"]) == ["F1", "F2"]
    assert all("2 counts" in u["why"] for u in out["uncheckable"])


def test_a_level_start_never_holds_f1() -> None:
    out = frames.check(_call("이 라인에서 백이 9점 앞선다."),
                       {"x21.t": ("explored_line", {"ledger": _ledger(0, [5, 9])})})  # fmt: skip
    assert out["held"] == []


def test_a_material_number_backed_by_a_cited_handle_is_uncheckable() -> None:
    out = frames.check(_call("이 라인에서 백이 9점 앞선다.", props=(), cites=("x21.t",)), RECORDS)
    assert out["held"] == [] and out["uncheckable"][0]["why"].startswith("a material number")


def test_two_cited_material_propositions_are_uncheckable() -> None:
    other = dict(MATERIAL, id="pm22", side="black", balance=-9)
    out = frames.check(_call("백이 9점 앞선다.", (MATERIAL, other), ("pm21", "pm22")), RECORDS)
    assert out["held"] == [] and "2 cited material" in out["uncheckable"][0]["why"]


def test_a_sentence_outside_the_word_lists_is_not_held() -> None:
    out = frames.check(_call("백은 이 수순에서 퀸을 잡아 9점을 번다."), RECORDS)
    assert out["held"] == [] and out["uncheckable"] == []


def test_a_grade_against_the_cited_judgement_is_held() -> None:
    words = {v: k for k, v in frames.grade_words().items()}
    blunder, best = words["blunder"], words["best"]
    judgement = {"id": "pj", "kind": "judgement", "judgement": "j5.t"}
    records = {"j5.t": ("judgement", {"grade": "best", "label": "great",
                                      "move": {"san": "Be3+"}})}  # fmt: skip
    held = frames.check(_call(f"이 수는 {blunder}로 판정된다.", (judgement,), ("pj",)), records)
    assert [h["rule"] for h in held["held"]] == ["F3"] and best in held["held"][0]["reply"]
    right = frames.check(_call(f"이 수는 {best}이다.", (judgement,), ("pj",)), records)
    assert right["held"] == []
    two = frames.check(_call(f"이 수는 {blunder}({words['miss']})이다.", (judgement,), ("pj",)), records)
    assert two["held"] == [] and two["uncheckable"][0]["rule"] == "F3"


def test_numbers_from_a_session_search_are_counted() -> None:
    records = {"s9.t": ("search_line", {"score": {"cp": 639}, "pv": []}),  # no `search`: a session's
               "s1.t": ("search_line", {"score": {"cp": 518}, "search": 0, "rank": 1})}  # fmt: skip
    own = frames.check(_call("이 라인의 평가는 +6.39로 백이 유리하다.", (), ("s9.t",)), records)
    analysis = frames.check(_call("이 라인의 평가는 +5.18로 백이 유리하다.", (), ("s1.t",)), records)
    assert own["search_numbers"] == 1 and analysis["search_numbers"] == 0


def test_the_records_the_check_reads() -> None:
    call = _call("x", (MATERIAL, LINE_PROP, {"id": "pj", "kind": "judgement", "judgement": "j1.t"}),
                 ("pm21", "s3.t", "b1.t"))  # fmt: skip
    assert frames.refs_needed(call) == {"x21.t", "j1.t", "s3.t"}


# -- the loop (§4.2) --------------------------------------------------------------------------


def _submit_held():
    arguments = {"game": "g", "agent": {"name": "t"}, "items": [{
        "ply": 3, "propositions": [MATERIAL, LINE_PROP],
        "sentences": [{"text": "라인 전체에서 백이 9점 앞선다.", "cites": ["px21", "pm21"]}]}]}  # fmt: skip
    return lt._reply(calls=[("submit_commentary", arguments)])


def test_rev_8_holds_twice_then_sends_and_makes_no_model_request(tmp_path, monkeypatch) -> None:
    monkeypatch.setitem(lt.RECORDS, "x21.t", LINE_22)
    reason, judge, session, lines, _, _ = lt._run(
        tmp_path,
        [lt._facts(lt.GOOD[3:4]), _submit_held(), _submit_held(), _submit_held(),
         lt._reply("submitted")],
        [lt._verdict(True)],  # the judge only: the frame check asks no model
        revision=8,
    )  # fmt: skip
    assert reason == "done" and judge.replies == []
    assert [x["reason"] for x in lines if x["type"] == "tool_unsent"] == ["frame_check"] * 2
    held = [x for x in lines if x["type"] == "frames" and x.get("state") == "held"]
    assert len(held) == 2 and {h["rule"] for h in held[0]["held"]} == {"F1", "F2"}
    [state] = [x for x in lines if x.get("stage") == "sentence_state"]
    assert state["state"] == "exhausted" and state["holds"] == 2
    assert [n for n, _ in session.calls].count("submit_commentary") == 1
    assert any(x["type"] == "harness_call" and x["ref"] == "x21.t" for x in lines)


def test_rev_8_passes_a_right_sentence(tmp_path) -> None:
    _reason, _, session, lines, _, _ = lt._run(
        tmp_path, [lt._facts(lt.GOOD[3:4]), lt._submit(), lt._reply("submitted")],
        [lt._verdict(True)], revision=8,
    )  # fmt: skip
    [state] = [x for x in lines if x.get("stage") == "sentence_state"]
    assert state["state"] == "passed"
    assert [n for n, _ in session.calls].count("submit_commentary") == 1


def test_rev_8_is_the_default_and_its_start_line_names_the_frame_check(tmp_path) -> None:
    assert REVISION == 8 and VERSIONS[8] == ("harness_v4", "harness_judge_v3", None)
    assert FRAMES[8] == frames.FRAMES_VERSION
    spec = rx_run.RunSpec(arm="H", set_name="validation", game="g", pgn="", moments=[3],
                          base=tmp_path, records=tmp_path, work=tmp_path)  # fmt: skip
    info = rx_run._harness_info(spec)
    assert spec.harness_revision == 8
    assert info["harness"] == "harness_v4" and info["harness_frames"] == "harness_frames_v1"
    assert "harness_sentences" not in info
    assert json.dumps(info)
