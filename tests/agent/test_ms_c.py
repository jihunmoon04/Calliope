"""MS-c over the synthetic engine: citing by handle (MS-D §9.1) and the server's derived use
(§9.2), with the digest's `as`."""

from __future__ import annotations

import pytest
from agent_helpers import GAME, session

from calliope.agent.handles import Entry


@pytest.fixture
def s(tmp_path):
    s = session(tmp_path)
    yield s
    s.close()


def _open(s, ply: int = 2):
    game = s.open_game(pgn=GAME, plies=f"1-{ply}")["game"]
    return game, s.ply(game, ply)


def _submit(s, game, ply, sentences, propositions=None):
    return s.submit_commentary(game, ply=ply, agent={"name": "t"}, propositions=propositions,
                               sentences=sentences)  # fmt: skip


def _stored(s, game, ply) -> dict:
    return s.store.for_subject(s.game(game).key, tuple(s.game(game).parsed.uci[:ply]))[0]  # newest


def test_handles_alone_cite_a_judgement_a_claim_a_line_and_a_board_item(s) -> None:
    game, d = _open(s, 3)  # 2.exd5: a claim
    claim = d["claims"][0]
    line = d["lines"]["played"]
    item = s.ply(game, 2)["board"]["changes"][0]  # 1...d5: a board item (of ply 2)
    answer = _submit(s, game, 3, [
        {"text": "판정을 받은 수다.", "class": "sourced", "cites": [d["judgement"]]},
        {"text": "엔진이 확인한 사실이다.", "class": "sourced", "cites": [claim["ref"]]},
        {"text": f"엔진 라인은 {line['move']}로 시작한다.", "class": "sourced",
         "cites": [line["ref"]]},
    ])  # fmt: skip
    assert answer["accepted"], answer
    _game, two = game, s.ply(game, 2)
    answer = _submit(s, game, 2, [
        {"text": "판정을 받은 수다.", "class": "sourced", "cites": [two["judgement"]]},
        {"text": "그 수가 판에 남긴 변화다.", "class": "sourced", "cites": [item["ref"]]},
    ])  # fmt: skip
    assert answer["accepted"], answer


def test_built_propositions_have_their_own_ids_and_are_built_once(s) -> None:
    game, d = _open(s)
    built, sentences, problems = s._by_handle(s.game(game), [
        {"text": "a", "cites": [d["judgement"], d["lines"]["played"]["ref"]]},
        {"text": "b", "cites": [d["lines"]["played"]["ref"]],
         "states": [d["lines"]["played"]["ref"]]},
    ])  # fmt: skip
    ids = [p["id"] for p in built]
    line = d["lines"]["played"]["ref"]
    assert problems == [] and len(ids) == len(set(ids))
    assert ids == [f"{d['judgement']}:judgement", f"{line}:score", f"{line}:line"]
    assert sentences[1]["cites"] == [f"{line}:score", f"{line}:line"]
    assert sentences[1]["states"] == sentences[1]["cites"]  # a handle states all it stands for
    assert all(p["by_handle"] in (d["judgement"], line) for p in built)


def test_a_line_without_a_pv_stands_for_its_score_alone(s, monkeypatch) -> None:
    """Review B8: `engine_line` refuses an empty line; such a handle builds `engine_score`."""

    game, d = _open(s)
    ref = d["lines"]["played"]["ref"]
    real = s.resolve(ref, s.game(game))
    bare = Entry(real.ref, real.kind, real.game, real.source, real.address,
                 real.item | {"pv": []})  # fmt: skip
    monkeypatch.setattr(s, "resolve", lambda r, g: bare if r == ref else real)
    built, _sentences, _ = s._by_handle(s.game(game), [{"text": "a", "cites": [ref]}])
    assert [p["id"] for p in built] == [f"{ref}:score"]


def test_an_agents_id_with_a_colon_is_refused(s) -> None:
    game, d = _open(s)
    answer = _submit(s, game, 2, [{"text": "판정을 받은 수다.", "class": "sourced",
                                   "cites": ["j:1"]}],
                     [{"id": "j:1", "kind": "judgement", "judgement": d["judgement"]}])  # fmt: skip
    assert not answer["accepted"]
    assert any(v.get("problem_en") == "a proposition's id has no colon"
               for v in answer["violations"])  # fmt: skip


def test_a_claim_cited_without_a_use_is_stored_with_the_servers(s) -> None:
    game, d = _open(s, 3)
    claim = d["claims"][0]
    assert claim["as"]  # MS-D §9.2: shown before the sentence is written
    answer = _submit(s, game, 3, [
        {"text": "판정을 받은 수다.", "class": "sourced", "cites": [d["judgement"]]},
        {"text": "엔진이 확인한 사실이다.", "class": "sourced", "cites": [claim["ref"]]},
    ])  # fmt: skip
    assert answer["accepted"], answer
    stored = next(p for p in _stored(s, game, 3)["propositions"] if p["kind"] == "claim")
    assert stored["use"] == claim["as"] and stored["use_by"] == "server"
    assert stored["id"] == f"{claim['ref']}:claim" and stored["by_handle"] == claim["ref"]


def test_an_explicit_use_is_checked_as_before(s) -> None:
    game, d = _open(s, 3)
    claim = d["claims"][0]
    answer = _submit(s, game, 3, [
        {"text": "판정을 받은 수다.", "class": "sourced", "cites": ["j"]},
        {"text": "엔진이 확인한 사실이다.", "class": "sourced", "cites": ["c"]},
    ], [{"id": "j", "kind": "judgement", "judgement": d["judgement"]},
        {"id": "c", "kind": "claim", "claim": claim["ref"], "use": "not_the_case"}])  # fmt: skip
    assert not answer["accepted"] and any(v.get("field") == "use" for v in answer["violations"])
    explicit = _submit(s, game, 3, [
        {"text": "판정을 받은 수다.", "class": "sourced", "cites": ["j"]},
        {"text": "엔진이 확인한 사실이다.", "class": "sourced", "cites": ["c"]},
    ], [{"id": "j", "kind": "judgement", "judgement": d["judgement"]},
        {"id": "c", "kind": "claim", "claim": claim["ref"], "use": claim["as"]}])  # fmt: skip
    assert explicit["accepted"], explicit
    stored = next(p for p in _stored(s, game, 3)["propositions"] if p["kind"] == "claim")
    assert "use_by" not in stored


def test_a_move_the_cited_handle_does_not_hold_is_refused(s) -> None:
    game, d = _open(s)
    answer = _submit(s, game, 2, [
        {"text": "판정을 받은 수다. 9.Qh5로 이어졌다.", "class": "sourced",
         "cites": [d["judgement"]]},
    ])  # fmt: skip
    assert not answer["accepted"] and any(v.get("rule") == "S3" for v in answer["violations"])


def test_a_handle_this_game_did_not_serve_is_refused(s) -> None:
    game, d = _open(s)
    answer = _submit(s, game, 2, [
        {"text": "판정을 받은 수다.", "class": "sourced", "cites": [d["judgement"]]},
        {"text": "그런 항목이다.", "class": "sourced", "cites": [f"c999.{s.handles.token}"]},
    ])  # fmt: skip
    assert not answer["accepted"]
    assert any(v.get("field") == "cites" for v in answer["violations"])


# -- review 1 ---------------------------------------------------------------------------------------


def _ok(d) -> dict:
    return {"text": "판정을 받은 수다.", "class": "sourced", "cites": [d["judgement"]]}


def test_a_stated_board_item_needs_its_own_token_not_the_moves(s) -> None:
    """Review B1: a `b` handle's `proves` tokens are S3's, never S7's; the move's number is not
    a count of the item."""

    game, d = _open(s, 4)
    item = d["board"]["changes"][0]
    stated = _submit(s, game, 4, [_ok(d), {"text": "2...Nf6는 좋은 수였다.", "class": "sourced",
                                           "cites": [d["judgement"], item["ref"]],
                                           "states": [item["ref"]]}])  # fmt: skip
    assert not stated["accepted"]
    assert any(v.get("rule") == "S7" for v in stated["violations"]), stated
    origin = _submit(s, game, 4, [_ok(d), {"text": "나이트는 g8에서 왔다.", "class": "sourced",
                                           "cites": [item["ref"]]}])  # fmt: skip
    assert not origin["accepted"], origin  # review 2 N1: a square its `proves` does not write
    count = _submit(s, game, 4, [_ok(d), {"text": "흑 나이트가 백 폰 2개를 노린다.",
                                          "class": "sourced", "cites": [item["ref"]]}])  # fmt: skip
    assert not count["accepted"] and any(v.get("rule") == "S3" for v in count["violations"])


def test_a_board_items_points_are_allowed_and_no_others(s) -> None:
    game, d = _open(s)
    item = next(c for c in d["board"]["changes"] if "1점" in c.get("proves", ""))
    square = item["propositions"][0].get("square") or "e4"
    good = _submit(s, game, 2, [_ok(d), {"text": f"{square} 폰은 1점 이득으로 잡힌다.",
                                         "class": "sourced", "cites": [item["ref"]]}])  # fmt: skip
    assert good["accepted"], good
    bad = _submit(s, game, 2, [_ok(d), {"text": f"{square} 폰은 3점 이득으로 잡힌다.",
                                        "class": "sourced", "cites": [item["ref"]]}])  # fmt: skip
    assert not bad["accepted"] and any(v.get("rule") == "S3" for v in bad["violations"])


def test_an_item_stated_by_handle_is_stored_as_stated_whole(s) -> None:
    """Review B3: `states_items` as when the agent wrote the item's propositions."""

    game, d = _open(s)
    item = d["board"]["changes"][0]
    text = item["proves"]
    answer = _submit(s, game, 2, [_ok(d), {"text": text, "class": "sourced",
                                           "cites": [item["ref"]], "states": [item["ref"]]}])  # fmt: skip
    assert answer["accepted"], answer
    assert _stored(s, game, 2)["sentences"][1]["states_items"] == [0]


def test_a_commentary_by_handle_is_a_duplicate_in_a_new_process_and_after_eviction(
    tmp_path,
) -> None:
    """Review B2 (AG6-D F15): the content key holds no `<handle>:<part>`."""

    def sentences(s, game):
        d = s.ply(game, 2)
        return [_ok(d), {"text": "d5가 e4를 공격한다.", "class": "sourced",
                         "cites": [d["board"]["changes"][0]["ref"]]}]  # fmt: skip

    s = session(tmp_path)
    game, _d = _open(s)
    assert _submit(s, game, 2, sentences(s, game))["accepted"]
    s._evict(s.game(game).key)
    game, _d = _open(s)
    assert _submit(s, game, 2, sentences(s, game))["duplicate"]
    s.close()
    s = session(tmp_path)
    game, _d = _open(s)
    again = _submit(s, game, 2, sentences(s, game))
    assert (
        again["duplicate"]
        and len(s.store.for_subject(s.game(game).key, tuple(s.game(game).parsed.uci[:2]))) == 1
    )
    s.close()


def test_by_handle_and_use_by_are_the_servers(s) -> None:
    """Review N2: an agent's proposition does not carry them."""

    game, d = _open(s)
    answer = _submit(s, game, 2, [{"text": "판정을 받은 수다.", "class": "sourced", "cites": ["p" * 40]}],
                     [{"id": "p" * 40, "kind": "judgement", "judgement": d["judgement"],
                       "by_handle": d["judgement"]}])  # fmt: skip
    assert not answer["accepted"]
    assert any(v.get("field") == "by_handle" for v in answer["violations"])


def test_the_derived_use_is_the_first_the_rule_allows(s, monkeypatch) -> None:
    """Review N6: the order of MS-D §9.2, apart from the digest that shows it."""

    from calliope.agent.propositions import DERIVED_ORDER, Verifier

    assert DERIVED_ORDER == ("result", "mechanism", "associated", "comparison", "line_fact",
                             "uncertain", "not_the_case")  # fmt: skip
    game, _d = _open(s)
    allowed = {"line_fact", "comparison"}
    monkeypatch.setattr(Verifier, "_use", lambda self, c, u, src: None if u in allowed else "no")
    assert Verifier(s, s.game(game)).derived_use({}, {}) == "comparison"
    allowed = set()
    assert Verifier(s, s.game(game)).derived_use({}, {}) is None


def test_handles_of_another_game_expired_or_of_a_fact_record_are_refused(s) -> None:
    game, d = _open(s)
    other = s.open_game(pgn="1. d4 d5 2. c4 *\n", plies="1-2")["game"]
    theirs = s.ply(other, 2)["judgement"]
    facts = s.facts(game, {"ply": 2, "at": "after"}, ["status"])["families"]["status"]["ref"]
    for ref in (theirs, facts):
        answer = _submit(
            s, game, 2, [_ok(d), {"text": "근거다.", "class": "sourced", "cites": [ref]}]
        )
        assert not answer["accepted"], ref
    old = d["board"]["changes"][0]["ref"]
    s._evict(s.game(game).key)
    game, d = _open(s)
    answer = _submit(s, game, 2, [_ok(d), {"text": "근거다.", "class": "sourced", "cites": [old]}])
    assert not answer["accepted"]


def test_an_explored_line_is_cited_by_handle(s) -> None:
    game, d = _open(s)
    x = s.explore(game, {"ply": 2, "at": "after"}, ["exd5"])
    answer = _submit(s, game, 2, [_ok(d), {"text": "2.exd5로 이어 둘 수 있다.", "class": "sourced",
                                           "cites": [x["ref"]]}])  # fmt: skip
    assert answer["accepted"], answer
    stored = _stored(s, game, 2)["propositions"]
    assert any(p["id"] == f"{x['ref']}:line" and p["kind"] == "explored_line" for p in stored)


def test_states_name_what_the_sentence_cites_even_as_handles(s) -> None:
    game, d = _open(s)
    item = d["board"]["changes"][0]
    answer = _submit(s, game, 2, [{"text": item["proves"], "class": "sourced",
                                   "cites": [d["judgement"]], "states": [item["ref"]]}])  # fmt: skip
    assert not answer["accepted"] and any(v.get("rule") == "S7" for v in answer["violations"])


def test_built_propositions_count_toward_the_bound(s) -> None:
    from calliope.agent.session import MAX_PROPOSITIONS

    game, d = _open(s)
    line = d["lines"]["played"]["ref"]  # two propositions
    own = [{"id": f"j{i}", "kind": "judgement", "judgement": d["judgement"]}
           for i in range(MAX_PROPOSITIONS - 1)]  # fmt: skip
    answer = _submit(s, game, 2, [{"text": "판정을 받은 수다.", "class": "sourced",
                                   "cites": ["j0", line]}], own)  # fmt: skip
    assert not answer["accepted"] and any(v.get("rule") == "size" for v in answer["violations"])


def test_items_cite_handles_per_subject(s) -> None:
    game, three = _open(s, 3)
    two = s.ply(game, 2)
    answer = s.submit_commentary(game, agent={"name": "t"}, items=[
        {"ply": 2, "sentences": [_ok(two)]}, {"ply": 3, "sentences": [_ok(three)]}])  # fmt: skip
    assert [i["outcome"] for i in answer["items"]] == ["accepted", "accepted"], answer
