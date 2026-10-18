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
