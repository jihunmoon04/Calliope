"""AG6-D §13 for packet AG6a: the digest of a ply and its bounds, `view: "full"` and `detail`,
propositions by reference, several subjects in one submission, duplicates and the size of one
commentary, an `open_game` refused part-way, and `next` on the one-ply path."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from agent_helpers import G1, GAME, session

from calliope.agent import Limits
from calliope.agent.budget import analysis_bound
from calliope.agent.digest import (
    DIGEST_LIMIT,
    FINDING_CAP,
    PV_SHORT,
    SAYS_CAP,
    STEPS,
    TEXT_CAP,
    DigestTooLarge,
    bounded,
    digest,
    numbered,
    score_text,
    size,
)
from calliope.agent.handles import HandleError
from calliope.agent.session import (
    MAX_ITEMS,
    MAX_PROPOSITIONS,
    NEXT_OPENED,
    NEXT_REFUSED,
    AgentError,
    _glossary,
)
from calliope.reasoning import claim_sentence
from calliope.server import board_form, board_size

GOLDEN = Path(__file__).parent / "golden" / "full_answers_ms_a.json"
DIGEST_KEYS = {"ply", "move", "side", "status", "grade", "grade_ko", "label", "label_ko",
               "fen_before", "fen_after", "evaluation", "judgement", "lines", "text", "claims",
               "refuted", "not_shown", "cached", "budget_left", "next", "board"}  # fmt: skip


@pytest.fixture
def s(tmp_path):
    s = session(tmp_path)
    s.open_game(pgn=GAME)
    yield s
    s.close()


def _neutral(value):
    """Handles with their process token made neutral, as the golden file holds them."""

    return json.loads(re.sub(r'"([a-z])(\d+)\.[0-9a-f]{24}"', r'"\1\2.<token>"', json.dumps(value)))


def _refs(value) -> list[str]:
    return re.findall(r'"([a-z]\d+\.[0-9a-f]{24})"', json.dumps(value))


# -- the digest (§3.1, §3.2) --------------------------------------------------------------------


def test_the_digest_has_the_fields_of_the_design_and_nothing_hidden(s) -> None:
    full, d = s.ply(G1, 3, view="full"), s.ply(G1, 3)
    assert set(d) == DIGEST_KEYS
    assert d["move"] == "2.exd5" and d["grade"] == full["grade"]
    assert d["grade_ko"] == _glossary()["grades"][full["grade"]]
    subject = full["analysis"]["judgements"][0]
    assert d["judgement"] == subject["ref"]
    assert d["lines"]["played"]["ref"] == subject["played"]["ref"]
    assert d["lines"]["played"]["pv"] == " ".join(p["san"] for p in subject["played"]["pv"][:8])
    shown = [c["ref"] for c in d["claims"]]
    refuted = [c for c in full["analysis"]["claims"] if c["status"] == "refuted"]
    named = sorted(({"template": c["template"], "ref": c["ref"]} for c in refuted),
                   key=lambda e: e["ref"])  # fmt: skip
    assert sorted(d["refuted"], key=lambda e: e["ref"]) == named  # in the role order (§3.2)
    assert len(shown) + len(refuted) == len(full["analysis"]["claims"])
    assert d["not_shown"]["observations"] == len(full["analysis"]["observations"])
    text = json.dumps({k: v for k, v in d.items() if k != "budget_left"})  # its own `searches`
    for hidden in (
        '"from_root"',
        '"bundle"',
        '"curve"',
        '"segments"',
        '"game_key"',
        '"analysis"',
        '"searches"',
        '"operands"',
    ):  # fmt: skip (observations: a count only)
        assert hidden not in text, hidden  # V4, V5
    assert "policy" not in d["evaluation"] and "grade_basis" not in d["evaluation"]
    for ref in _refs(d):  # every ref in it resolves
        assert s.resolve(ref, s.game(G1)).ref == ref
    assert d["not_shown"]["steps"] == [] and size(d) < DIGEST_LIMIT


def test_claims_are_in_the_role_order() -> None:
    claims = [_claim(i, role, "supported") for i, role in
              enumerate(["function", "mechanism", "zeta", "consequence", "comparison", "alpha"])]  # fmt: skip
    d = digest(_record(claims), _glossary())
    assert [c["role"] for c in d["claims"]] == ["consequence", "comparison", "mechanism",
                                               "function", "alpha", "zeta"]  # fmt: skip


def test_a_judged_move_is_digested_as_a_ply(s) -> None:
    d = s.judge_move(G1, {"ply": 3, "at": "before"}, "Nc3")
    assert d["move"] == "2.Nc3" and d["played"] is False and "analysis" not in d
    assert s.judge_move(G1, {"ply": 3, "at": "before"}, "exd5")["played"] is True


def test_a_view_other_than_digest_or_full_is_refused(s) -> None:
    with pytest.raises(AgentError, match="view is one of digest, full"):
        s.ply(G1, 3, view="short")


def test_the_score_and_the_move_as_a_sentence_writes_them() -> None:
    assert [score_text({"cp": c}) for c in (38, -120, 0, 5, 1250)] == [
        "+0.38", "-1.20", "+0.00", "+0.05", "+12.50"]  # fmt: skip
    assert score_text({"mate": 3}) == "M3" and score_text({"mate": -2}) == "-M2"
    assert score_text(None) is None
    assert numbered(17, "white", "Ne3") == "17.Ne3" and numbered(17, "black", "Rxe3") == "17...Rxe3"


def test_an_unrendered_claim_says_its_own_sentence() -> None:
    claims = [_claim(0, "consequence", "supported"), _claim(1, "comparison", "supported")]
    d = digest(_record(claims, said={"id0": "It wins."}), _glossary(), {"id1": "Instead, a6."})
    assert [c.get("says") for c in d["claims"]] == ["It wins.", "Instead, a6."]


def test_claim_sentence_phrases_one_claim_or_answers_none(s) -> None:
    s.ply(G1, 3)
    _, analysis = next(iter(s.analyses.values()))
    claim = next(c for c in analysis.claims if c.verdict.status.value == "supported")
    assert claim_sentence(analysis, claim.id)  # a sentence of its template
    assert claim_sentence(analysis, "no such claim") is None


# -- the bounds (§3.6) --------------------------------------------------------------------------


def _claim(i: int, role: str, status: str, findings: int = 1, text: int = 10) -> dict:
    return {
        "id": f"id{i}",
        "ref": f"c{i}.{'0' * 24}",
        "template": f"template_{i}",
        "role": role,
        "status": status,
        "effective_scopes": [{"quantifier": "specific_line", "basis": "engine",
                              "at": {"kind": "line", "first": 0, "last": 8}, "depth": 12}],
        "checks": [],
        "findings": [{"type": "F", "note": "x" * text, "node": {"from_root": ["e2e4"] * 40}}
                     for _ in range(findings)],
    }  # fmt: skip


def _line(rank: int, san: str) -> dict:
    return {"ref": f"s{rank}.{'0' * 24}", "rank": rank, "move": {"san": san, "uci": "e2e4"},
            "score": {"cp": 20 * rank}, "depth": 12,
            "pv": [{"san": f"Rxe{k % 8 + 1}+", "uci": "e2e4", "by": "engine"}
                   for k in range(12)]}  # fmt: skip


def _record(claims: list[dict], text: str = "1.e4 is the best move.", said=None) -> dict:
    return {
        "ply": 1, "move_number": 1, "side": "white", "san": "e4", "status": "decided",
        "grade": "best", "label": None, "fen_before": "f" * 60, "fen_after": "g" * 60,
        "evaluation": {"played": {"cp": 20}, "best": {"cp": 20}, "loss": 0,
                       "best_move": {"san": "e4"}},
        "text": text,
        "segments": [{"source": "claim", "claim": k, "text": v} for k, v in (said or {}).items()],
        "analysis": {
            "judgements": [{"ref": f"j1.{'0' * 24}", "played": _line(2, "e4"),
                            "best": _line(1, "d4"),
                            "alternatives": [_line(r, f"a{r}") for r in range(2, 6)]}],
            "observations": [{}, {}, {}],
            "claims": claims,
        },
    }  # fmt: skip


def _heavy() -> dict:
    """A digest that needs every step: many claims with long findings, a long text."""

    claims = [_claim(i, "consequence", "supported", findings=4, text=90) for i in range(30)]
    claims += [_claim(100 + i, "mechanism", "inconclusive", findings=2, text=90) for i in range(20)]
    claims += [_claim(200 + i, "function", "refuted") for i in range(60)]
    return digest(_record(claims, text="t" * 1900), _glossary())


def test_each_step_runs_in_order_and_the_bound_holds() -> None:
    d = _heavy()
    seen, limit = [], size(d) - 1
    while limit > 1500:
        out = bounded(d, limit)
        assert size(out) <= limit
        steps = out["not_shown"]["steps"]
        assert steps == list(STEPS[: len(steps)])  # a prefix: in order, none skipped
        assert out["judgement"] and out["evaluation"] and out["lines"]["played"]["ref"]
        assert len(out["lines"]["played"]["pv"].split()) >= PV_SHORT  # never below 4 plies
        seen.append(steps[-1])
        limit = size(out) - 1
    assert set(seen) == set(STEPS) - {"board"}  # no board here: step 0 runs, moves nothing
    last = bounded(d, limit + 1)
    assert last["not_shown"]["counts"]["named_left_out"] == last["not_shown"]["left_out"] > 0


def test_steps_move_items_behind_detail_and_say_so() -> None:
    d = _heavy()
    out = bounded(d, size(d) - 1)  # step 1 only (step 0 runs and finds no board item)
    assert out["not_shown"]["steps"] == ["board", "findings"]
    assert all(isinstance(c["findings"], int) for c in out["claims"])
    moved = sum(len(c["findings"]) for c in d["claims"])  # 30 x 4 + 20 x 2 (review N1)
    assert out["not_shown"]["counts"]["findings"] == moved == 160
    out = bounded(d, 6_000)
    named = out["not_shown"]["named"]
    assert {e["status"] for e in named} == {"supported", "inconclusive"}
    assert all(set(e) == {"template", "ref", "status"} for e in named)
    assert "text" not in out and "text" in out["not_shown"]["steps"]


def test_a_digest_still_over_after_every_step_is_an_error_not_a_cut() -> None:
    with pytest.raises(DigestTooLarge, match="exceeds its size bound"):
        bounded(_heavy(), 300)


def test_fields_of_free_length_are_capped() -> None:
    claims = [_claim(0, "consequence", "supported", text=500)]
    d = digest(_record(claims, text="t" * 5000, said={"id0": "s" * 900}), _glossary())
    assert len(d["text"]) == TEXT_CAP and d["text"].endswith("…")
    assert len(d["claims"][0]["says"]) == SAYS_CAP
    assert len(d["claims"][0]["findings"][0]["note"]) == FINDING_CAP
    assert "node" not in d["claims"][0]["findings"][0]  # positions left out (V5)
    capped = d["not_shown"]["capped"]
    assert capped["text"] == 5000 and capped[f"says:c0.{'0' * 24}"] == 900


# -- view: "full" and detail (§3.4) -------------------------------------------------------------


def test_the_full_view_is_todays_answer_field_for_field(s) -> None:
    """A golden test: the full answers, handles made neutral. Made at `main @ 1f9ef15` (AG6a) and
    again at MS-a, whose mechanisms' `version` "2" changes their claims' ids, the claims' order by
    id and the graphs' digests, and nothing else (MS-a implementation §2 item 6)."""

    golden = json.loads(GOLDEN.read_text())
    answers = {
        "ply_3": s.ply(G1, 3, view="full"),
        "judge_move_unplayed": s.judge_move(G1, {"ply": 3, "at": "before"}, "e4e5", view="full"),
    }
    assert _neutral(answers) == golden


def test_detail_answers_the_item_as_the_full_answer_projects_it(s) -> None:
    full = s.ply(G1, 3, view="full")
    judgement = full["analysis"]["judgements"][0]
    claim = full["analysis"]["claims"][0]
    facts = s.facts(G1, {"ply": 3, "at": "after"}, ["status"])
    explored = s.explore(G1, {"ply": 3, "at": "after"}, ["Nf6"])
    for ref, item in ((judgement["ref"], judgement), (claim["ref"], claim),
                      (judgement["played"]["ref"], judgement["played"])):  # fmt: skip
        answer = s.detail(G1, ref)
        assert answer["ref"] == ref and answer["item"] == item
    status = facts["families"]["status"]
    assert s.detail(G1, status["ref"])["item"] == status["record"]
    assert s.detail(G1, explored["ref"])["kind"] == "explored_line"


def test_detail_refuses_a_handle_of_another_process(s, tmp_path) -> None:
    other = session(tmp_path / "other")
    try:
        other.open_game(pgn=GAME)
        foreign = other.ply(G1, 1)["judgement"]
    finally:
        other.close()
    with pytest.raises(HandleError, match="not served in this session"):
        s.detail(G1, foreign)


# -- propositions by reference (§5.1) -------------------------------------------------------------


def _by_ref(s, ply: int, pid: str = "p1") -> dict:
    d = s.ply(G1, ply)
    return {
        "ply": ply,
        "propositions": [{"id": pid, "kind": "judgement", "judgement": d["judgement"]}],
        "sentences": [{"text": f"{d['move']}로 이어졌다.", "class": "sourced", "cites": [pid]}],
    }


def test_a_proposition_by_reference_is_filled_and_stores_as_the_full_form(s) -> None:
    item = _by_ref(s, 3)
    claim = next(c for c in s.ply(G1, 3)["claims"] if c["status"] == "supported")
    item["propositions"].append({"id": "p2", "kind": "claim", "claim": claim["ref"],
                                 "use": "line_fact"})  # fmt: skip
    item["sentences"].append({"text": "그 라인의 사실이다.", "class": "interpretation",
                              "cites": ["p2"]})  # fmt: skip
    first = s.submit_commentary(G1, agent={"name": "t"}, **item)
    assert first["accepted"] and not first.get("duplicate"), first
    stored = s.commentary(G1, 3)["commentaries"][0]
    j = stored["propositions"][0]
    full = s.ply(G1, 3, view="full")["analysis"]
    subject = full["judgements"][0]
    assert (j["move"], j["grade"], j["label"]) == (subject["move"]["uci"], subject["grade"],
                                                   subject["label"])  # fmt: skip
    held = next(c for c in full["claims"] if c["ref"] == claim["ref"])
    assert stored["propositions"][1]["scopes"] == held["effective_scopes"]
    # the same commentary written out field by field is the same commentary (F15)
    item["propositions"][0] |= {"move": subject["move"]["san"], "grade": subject["grade"],
                                "label": subject["label"],
                                "best_move": subject["best"]["move"]["uci"]}  # fmt: skip
    item["propositions"][1]["scopes"] = held["effective_scopes"]
    again = s.submit_commentary(G1, agent={"name": "t"}, **item)
    assert again["accepted"] and again["duplicate"] and again["id"] == first["id"]


def test_a_field_given_is_still_verified_and_a_wrong_use_refused(s) -> None:
    item = _by_ref(s, 3)
    item["propositions"][0]["grade"] = "blunder"
    refused = s.submit_commentary(G1, agent={"name": "t"}, **item)
    assert not refused["accepted"] and refused["violations"][0]["field"] == "grade"
    claim = next(c for c in s.ply(G1, 3)["claims"] if c["status"] == "supported")
    item = _by_ref(s, 3)
    item["propositions"].append({"id": "p2", "kind": "claim", "claim": claim["ref"],
                                 "use": "uncertain"})  # fmt: skip
    refused = s.submit_commentary(G1, agent={"name": "t"}, **item)
    assert [v["field"] for v in refused["violations"] if v.get("proposition") == "p2"] == ["use"]


# -- several subjects, duplicates, the size of one commentary (§5.2, §5.3) -------------------------


def test_items_are_verified_and_stored_each_on_its_own(s) -> None:
    good = [_by_ref(s, ply) for ply in (1, 2, 3)]
    bad = _by_ref(s, 4)
    bad["sentences"][0]["text"] = "9.Qh5로 이어졌다."  # a move no proposition holds
    answer = s.submit_commentary(G1, agent={"name": "t"},
                                 items=[good[0], bad, good[1], "x", {"ply": 99}, good[2]])  # fmt: skip
    outcomes = [o["outcome"] for o in answer["items"]]
    assert outcomes == ["accepted", "refused", "accepted", "refused", "refused", "accepted"]
    assert [o["index"] for o in answer["items"]] == list(range(6))
    ids = [o["id"] for o in answer["items"] if o["outcome"] == "accepted"]
    assert len(set(ids)) == 3
    assert answer["items"][3]["violations"][0]["rule"] == "item"
    assert answer["items"][4]["violations"][0]["rule"] == "subject"
    assert [len(s.commentary(G1, p)["commentaries"]) for p in (1, 2, 3, 4)] == [1, 1, 1, 0]
    assert "거부된 항목" in answer["next"]


def test_items_and_a_single_subject_are_not_mixed_and_items_are_bounded(s) -> None:
    item = _by_ref(s, 1)
    with pytest.raises(AgentError, match="give either `items`"):
        s.submit_commentary(G1, agent={"name": "t"}, ply=1, items=[item])
    with pytest.raises(AgentError, match=f"1 to {MAX_ITEMS} subjects"):
        s.submit_commentary(G1, agent={"name": "t"}, items=[item] * (MAX_ITEMS + 1))


def test_a_failed_write_is_reported_per_item_and_a_resend_stores_each_once(s, monkeypatch) -> None:
    items = [_by_ref(s, ply) for ply in range(1, 6)]
    write, calls = s.store.write, []

    def failing(record):
        calls.append(record)
        if len(calls) == 3:
            raise OSError("disk full")
        return write(record)

    monkeypatch.setattr(s.store, "write", failing)
    answer = s.submit_commentary(G1, agent={"name": "t"}, items=items)
    assert [o["outcome"] for o in answer["items"]] == ["accepted", "accepted", "not_stored",
                                                       "accepted", "accepted"]  # fmt: skip
    assert "disk full" in answer["items"][2]["message"] and "다시 제출" in answer["next"]
    again = s.submit_commentary(G1, agent={"name": "t"}, items=items)
    assert [o["outcome"] for o in again["items"]] == ["duplicate", "duplicate", "accepted",
                                                      "duplicate", "duplicate"]  # fmt: skip
    assert again["items"][0]["id"] == answer["items"][0]["id"]
    assert [len(s.commentary(G1, p)["commentaries"]) for p in range(1, 6)] == [1] * 5
    assert "show_game" in again["next"]


def test_the_same_commentary_from_a_new_process_is_a_duplicate(tmp_path) -> None:
    """Review check I3: persisted records, new handles."""

    first = session(tmp_path)
    try:
        first.open_game(pgn=GAME)
        old = _by_ref(first, 3)
        stored = first.submit_commentary(G1, agent={"name": "t"}, **old)
    finally:
        first.close()
    second = session(tmp_path)
    try:
        second.open_game(pgn=GAME)
        item = _by_ref(second, 3)
        # the new process serves the same judgement under another handle (review N2)
        assert item["propositions"][0]["judgement"] != old["propositions"][0]["judgement"]
        again = second.submit_commentary(G1, agent={"name": "t"}, **item)
        assert again["duplicate"] and again["id"] == stored["id"]
        renamed = second.submit_commentary(G1, agent={"name": "t"}, **_by_ref(second, 3, "q1"))
        assert renamed["accepted"] and not renamed.get("duplicate")
        assert len(second.commentary(G1, 3)["commentaries"]) == 2
    finally:
        second.close()


def test_one_commentary_is_bounded(s, monkeypatch) -> None:
    item = _by_ref(s, 3)
    j = item["propositions"][0]
    many = dict(item, propositions=[j | {"id": f"p{i}"} for i in range(1, MAX_PROPOSITIONS + 2)])
    refused = s.submit_commentary(G1, agent={"name": "t"}, **many)
    assert refused["violations"] == [{"rule": "size", "problem": "한 해설의 명제는 32개까지입니다"
                                      "(33개를 보냄)", "problem_en": "at most 32 propositions in "
                                      "one commentary, not 33"}]  # Korean (AG8-D §7)  # fmt: skip
    long_id = dict(item, propositions=[j | {"id": "p" * 33}])
    refused = s.submit_commentary(G1, agent={"name": "t"}, **long_id)
    assert refused["violations"][0]["field"] == "id"
    monkeypatch.setattr("calliope.agent.session.MAX_BOARD_BYTES", 100)
    refused = s.submit_commentary(G1, agent={"name": "t"}, **item)
    assert refused["violations"][0]["rule"] == "size" and "on the board" in refused["violations"][
        0]["problem_en"]  # fmt: skip
    assert s.commentary(G1, 3)["commentaries"] == []


def test_the_board_size_is_measured_as_the_record_will_be_stored(s) -> None:
    s.submit_commentary(G1, agent={"name": "t"}, **_by_ref(s, 3))
    [stored] = s.store.for_game(s.game(G1).key)
    start = s.game(G1).parsed.game.start_fen
    sent = json.dumps(board_form(stored, start), ensure_ascii=False, separators=(",", ":"))
    unwritten = {k: v for k, v in stored.items() if k not in ("format", "id")}
    assert board_size(unwritten, start) == board_size(stored, start) == len(sent.encode())


# -- open_game refused part-way (F13) and `next` (§7) --------------------------------------------


def test_an_open_game_refused_part_way_answers_what_it_analysed(tmp_path) -> None:
    probe = session(tmp_path / "probe")
    try:
        probe.open_game(pgn=GAME, plies="1-2")
        used = probe.budget.meter.used
    finally:
        probe.close()
    s = session(tmp_path, Limits(max_searches=used + analysis_bound(3) - 1))
    try:
        answer = s.open_game(pgn=GAME, plies="1-3")
        assert [m["ply"] for m in answer["moves"] if "grade" in m] == [1, 2]
        assert answer["refused"]["ply"] == 3 and "budget" in answer["refused"]["message"]
        assert answer["refused"]["retry_after_seconds"] > 0 and answer["next"] == NEXT_REFUSED
        assert [m["cached"] for m in answer["moves"][:3]] == [True, True, False]
    finally:
        s.close()
    first = session(tmp_path / "first", Limits(max_searches=0))
    try:
        with pytest.raises(Exception, match="budget"):  # the first ply refused: an error, as before
            first.open_game(pgn=GAME, plies="1-2")
    finally:
        first.close()


def test_next_on_the_one_ply_path(s) -> None:
    assert s.open_game(pgn=GAME)["next"] == NEXT_OPENED
    d = s.ply(G1, 3)
    assert "submit_commentary" in d["next"] and d["judgement"] in d["next"]
    accepted = s.submit_commentary(G1, agent={"name": "t"}, **_by_ref(s, 3))
    assert "show_game" in accepted["next"]
    item = _by_ref(s, 2)
    item["sentences"][0]["text"] = "9.Qh5로 이어졌다."
    assert "고쳐 다시 제출" in s.submit_commentary(G1, agent={"name": "t"}, **item)["next"]


def _board_item(kind: str, n: int) -> dict:
    return {"kind": kind, "part": "reason", "owner": "white", "good_for": "black",
            "proves": "p" * 200, "propositions": [{"kind": "attack", "position": {"ply": n,
            "at": "after"}, "attacker": "a1", "target": "b2"}]}  # fmt: skip


def test_step_0_leaves_board_items_out_beyond_the_kept_ones_first() -> None:
    """AG8-D §2.3: threats beyond two, then weaknesses, then lost defences beyond two; the same
    reply never."""

    d = digest(_record([_claim(1, "consequence", "supported")]), _glossary())
    d["board"] = {"v": "board_v1", "mover": "black",
                  "changes": [_board_item(k, i) for i, k in enumerate(
                      ["lost_defence"] * 3 + ["weakness"] * 2 + ["threat"] * 4)],
                  "same_reply": {"kind": "same_reply", "proves": "s", "propositions": []}}  # fmt: skip
    kinds = [c["kind"] for c in bounded(d, size(d) - 1)["board"]["changes"]]
    assert kinds.count("threat") == 3 and kinds.count("lost_defence") == 3
    small = bounded(d, size(d) - 6 * 260)
    kinds = [c["kind"] for c in small["board"]["changes"]]
    assert kinds == ["lost_defence", "lost_defence", "threat", "threat"]
    assert small["not_shown"]["counts"]["board"] == 5 and "same_reply" in small["board"]
    assert small["not_shown"]["steps"][0] == "board"
