"""TO (agent-to-design.md): the brief views of `explore` and `facts` (§2, review B3), `compare_lines`
(§3, reviews B1, B2, N2, C1–C3) and `game_overview`'s names (§4)."""

from __future__ import annotations

import json

import pytest
from agent_helpers import G1, GAME, gid, session

from calliope.agent import AgentError
from calliope.agent.brief import brief_exchange, brief_pieces, kept_squares
from calliope.agent.propositions import Refused, Verifier
from calliope.agent.session import COMPARE_MAX

EXPOSED = "1. e4 e5 2. Nf3 d6 3. Ng5 h6 *"  # the knight on g5: a pawn attacks it, nothing defends
G3 = gid(EXPOSED)


@pytest.fixture
def s(tmp_path):
    s = session(tmp_path)
    s.open_game(pgn=GAME)  # G1
    s.open_game(pgn=EXPOSED)  # G3
    yield s
    s.close()


def verify(s, game_id: str, proposition: dict) -> dict:
    record, _ = Verifier(s, s.game(game_id)).verify({"id": "p", **proposition})
    return record


def refused(s, game_id: str, proposition: dict, field: str | None = None) -> Refused:
    with pytest.raises(Refused) as error:
        verify(s, game_id, proposition)
    if field is not None:
        assert error.value.field == field, error.value.problem
    return error.value


# -- the brief filter, on records made by hand (§2.1) ------------------------------------------------


def _piece(square, color, kind, attackers=(), defenders=(), enemy=(), lowest=None, pinned=False,
           **flags) -> dict:  # fmt: skip
    return {
        "square": square, "color": color, "piece_type": kind,
        "attacks": {"empty": ["x1"], "friendly": [], "enemy": list(enemy)},
        "attackers": [{"square": a, "absolutely_pinned": False} for a in attackers],
        "defenders": [{"square": d} for d in defenders],
        "attacker_count": len(attackers), "defender_count": len(defenders),
        "lowest_attacker_types": {"value": [lowest] if lowest else [], "definition": "piece_order_v1"},
        "attacked_without_defender": bool(attackers) and not defenders,
        "attackers_exceed_defenders": len(attackers) > len(defenders),
        "absolutely_pinned": pinned, "legal_moves": ["a1a2"], "legal_destinations": ["a2"],
        "legally_capturable_now": {"sentinel": "not_observed"},
        "identity": {"piece": kind, "color": color, "origin": square, "square": square, "type_now": kind},
    } | flags  # fmt: skip


def _exchange(*gains) -> dict:
    return {
        "pieces": [{"square": sq, "gain": {"value": g, "definition": "see_v1"}} for sq, g in gains]
    }


def test_one_attacker_against_one_defender_that_loses_is_kept_with_its_exchange() -> None:
    """Review B3: a rook attacked once by a knight and defended once is exposed (see_v1 gain 2);
    the count alone (1 against 1) would not keep it."""

    rook = _piece("d4", "white", "rook", attackers=["f5"], defenders=["d1"], lowest="knight")
    knight = _piece("f5", "black", "knight", enemy=["d4"])
    queen = _piece("d1", "white", "queen")
    quiet = _piece("a2", "white", "pawn")
    pieces = [rook, knight, queen, quiet]
    assert kept_squares(pieces, {"d4"}, None, None) == {"d4", "f5", "d1"}  # rules 1 and 2
    # without the exchange record the lesser attacker (rule 3) still keeps the rook
    assert {"d4", "f5"} <= kept_squares(pieces, set(), None, None)
    shown = brief_pieces({"pieces": pieces}, _exchange(("d4", 2), ("a2", 0)), None, None)
    assert [e["piece"] for e in shown["pieces"]] == ["Rd4", "nf5", "Qd1"]
    assert shown["omitted"] == ["Pa2"] and shown["shown"] == 3 and shown["of"] == 4
    assert "detail(ref)" in shown["note"]
    entry = shown["pieces"][0]
    # A2: by name; counts, lowest attacker types, false flags and an unmoved origin left out
    assert entry == {"piece": "Rd4", "attackers": ["nf5"], "defenders": ["Qd1"]}
    assert "legal_moves" not in entry and "identity" not in entry and "origin" not in entry
    assert "attacker_count" not in entry and "lowest_attacker_types" not in entry
    assert shown["pieces"][1]["attacks"] == ["Rd4"]


def test_pins_double_attacks_checks_and_the_last_move_are_kept() -> None:
    pinned = _piece("c6", "black", "knight", pinned=True)
    fork = _piece("c7", "white", "knight", enemy=["a8", "e8"])
    king = _piece("e8", "black", "king")
    rook = _piece("a8", "black", "rook")
    moved = _piece("h3", "white", "pawn")
    status = {"in_check": True, "side_to_move": "black", "checkers": ["c7"]}
    kept = kept_squares([pinned, fork, king, rook, moved], set(), status, "h3")
    assert kept == {"c6", "c7", "e8", "h3"}  # the rook on a8 is attacked but only listed as omitted


def test_the_brief_exchange_keeps_the_exposed_pieces_and_counts_the_others() -> None:
    out = brief_exchange(_exchange(("g5", 3), ("e4", 0), ("a2", 0)) | {"definition": "see_v1"})
    assert [e["square"] for e in out["pieces"]] == ["g5"] and out["not_exposed"] == 2
    assert out["definition"] == "see_v1"
    assert brief_pieces({"sentinel": "no_edge"}, None, None, None) == {"sentinel": "no_edge"}


# -- facts and explore (§2.3, §2.4) ------------------------------------------------------------------


def test_facts_brief_keeps_the_exposed_knight_and_the_handle_keeps_everything(s) -> None:
    at = {"ply": 6, "at": "after"}  # 3...h6: the knight on g5 is attacked by the pawn, undefended
    brief = s.facts(G3, at)["families"]["pieces"]
    full = s.facts(G3, at, view="full")["families"]["pieces"]
    squares = [e["piece"][1:] for e in brief["record"]["pieces"]]
    assert "g5" in squares and "h6" in squares  # exposed, and its attacker (the last move too)
    assert brief["record"]["of"] == len(full["record"]["pieces"]) == 32
    assert len(squares) + len(brief["record"]["omitted"]) == 32
    detail = s.detail(G3, brief["ref"])
    assert len(detail["item"]["pieces"]) == 32 if "item" in detail else True
    assert len(str(brief["record"])) < len(str(full["record"])) / 2
    with pytest.raises(AgentError, match="view is one of brief, full"):
        s.facts(G3, at, view="digest")


def test_explore_brief_answers_the_line_and_the_handle_keeps_the_full_answer(s) -> None:
    line = s.explore(G1, {"ply": 4, "at": "after"}, ["Nc3", "Nxd5", "Nxd5", "Qxd5"])
    full = s.explore(G1, {"ply": 4, "at": "after"}, ["Nc3", "Nxd5", "Nxd5", "Qxd5"], view="full")
    assert line["ref"] == full["ref"] and line["plies"] == full["plies"]
    assert set(line["end_facts"]) == {"status", "pieces", "exchange"}
    assert "omitted" in line["end_facts"]["pieces"] and "omitted" not in full["end_facts"]["pieces"]
    assert len(str(line)) < len(str(full))
    # a material proposition from the brief line verifies as before (the handle is the full record)
    p = {"kind": "material", "line": line["ref"], "from": 0, "to": 3, "side": "white", "balance": 2}
    assert verify(s, G1, p)["balance"] == 2


def test_a_proposition_about_an_omitted_piece_is_still_accepted(s) -> None:
    at = {"ply": 6, "at": "after"}
    record = s.facts(G3, at)["families"]["pieces"]["record"]
    assert "Pd2" in record["omitted"] and "Qd1" in record["omitted"]  # nothing happens to them
    assert verify(s, G3, {"kind": "defence", "position": at, "defender": "d1", "defended": "d2"})


# -- compare_lines (§3) -----------------------------------------------------------------------------


def test_compare_lines_reads_the_records_whole_pv_and_cites_by_x_and_s(s) -> None:
    j = s.ply(G1, 4, view="full")["analysis"]["judgements"][0]
    answer = s.compare_lines(G1, 4)
    assert answer["ply"] == 4 and answer["from"]["ply"] == 3
    played = answer["lines"]["played"]
    record_pv = len(j["played"]["pv"])
    assert played["source"] == {
        "engine": min(record_pv, 16)
    }  # the record's PV, not the digest's (B1)
    assert len(played["moves"]) == played["source"]["engine"] + played["extended"]
    assert len(played["material"]) == len(played["moves"])
    end = played["end"]
    assert end["end_score_at"] == played["source"]["engine"]  # where the search ran (B2)
    assert end["score_ref"].startswith("s") and played["ref"].startswith("x")
    # C1: the material from the x handle, the score from the s handle
    p = {"kind": "material", "line": played["ref"], "from": 0, "to": 1, "side": "white",
         "balance": played["material"][0]}  # fmt: skip
    assert verify(s, G1, p)
    searched = s.handles.resolve(end["score_ref"], s.game(G1).key).item
    score = {"kind": "engine_score", "line": end["score_ref"], "move": searched["move"]["uci"],
             "score": searched["score"]}  # fmt: skip
    assert verify(s, G1, score)
    refused(s, G1, score | {"line": played["ref"]}, "line")  # a score is not an x's to give
    # N2: the root's scores apart, with the analysis record's own s handles
    assert answer["root"]["played"]["score_ref"] == j["played"]["ref"]
    game = answer["lines"]["game"]
    assert game["source"] == {"game": 7} and game["moves"][0] == "Nf6"  # plies 4 to 10 of the game


def test_compare_lines_one_search_a_line_and_partial_answers(s, tmp_path) -> None:
    s.ply(G1, 4)  # the ply's analysis first: what follows counts the comparison's searches only
    before = s.budget.meter.used
    answer = s.compare_lines(G1, 4, length=2)
    lines = answer["lines"]
    assert all(len(line["moves"]) <= 2 + 0 or line["extended"] for line in lines.values())
    run = answer["searches"]["run"] + answer["searches"]["stored"]
    assert run == len(lines) and s.budget.meter.used - before == answer["searches"]["run"]
    assert all("search" not in line for line in lines.values())


def test_compare_lines_checks_its_arguments_before_any_work(s) -> None:
    used = s.budget.meter.used
    for bad in (0, COMPARE_MAX + 1, "16", True):
        with pytest.raises(AgentError, match="length is an integer from 1 to 32"):
            s.compare_lines(G1, 4, length=bad)
    with pytest.raises(AgentError, match="plies 1 to 10"):
        s.compare_lines(G1, 11)
    assert s.budget.meter.used == used
    assert s.compare_lines(G1, 4, length=1)["lines"]
    assert s.compare_lines(G1, 4, length=COMPARE_MAX)["lines"]


def test_compare_lines_analyses_an_uncached_ply_as_ply_does(tmp_path) -> None:
    s = session(tmp_path)
    s.open_game(pgn=GAME)
    first = s.compare_lines(G1, 3)
    again = s.compare_lines(G1, 3)
    assert first["cached"] is False and again["cached"] is True  # review C2
    s.close()


def test_the_extension_follows_forcing_plies_only() -> None:
    """§3 step 3: a line ending in a capture goes on along the search while a capture, a check or a
    promotion stands in its last two plies; it stops at two quiet plies and at `length`."""

    import chess

    from calliope.agent.session import _extension

    board = chess.Board()
    for uci in ("e2e4", "d7d5", "e4d5"):  # the line's last ply is a capture
        board.push_uci(uci)
    moves = ["e2e4", "d7d5", "e4d5"]
    pv = ["d8d5", "b1c3", "d5a5", "g1f3", "g8f6"]  # Qxd5 (capture), Nc3, Qa5, Nf3, Nf6
    # after Qxd5 the last two are exd5, Qxd5 (captures); after Nc3 the last two are Qxd5, Nc3 (one
    # capture); after Qa5 the last two are Nc3, Qa5 (quiet): it stops there
    assert _extension(board, moves, pv, 16) == ["d8d5", "b1c3", "d5a5"]
    assert _extension(board, moves, pv, 4) == ["d8d5"]  # length bounds it
    quiet = chess.Board()
    for uci in ("e2e4", "e7e5"):
        quiet.push_uci(uci)
    assert _extension(quiet, ["e2e4", "e7e5"], ["g1f3"], 16) == []


def test_a_line_that_ends_the_game_answers_its_status(tmp_path) -> None:
    s = session(tmp_path)
    s.open_game(pgn="1. f3 e5 2. g4 Qh4# *")
    game = s.compare_lines(gid("1. f3 e5 2. g4 Qh4# *"), 3)["lines"]["game"]
    assert game["moves"] == ["g4", "Qh4#"] and game["extended"] == 0
    assert game["end"]["status"]["checkmate"] is True and "end_score" not in game["end"]
    s.close()


def test_a_budget_without_searches_answers_the_lines_without_scores(tmp_path, monkeypatch) -> None:
    from calliope.agent.budget import BudgetError

    s = session(tmp_path)
    s.open_game(pgn=GAME)
    s.ply(G1, 4)  # analysed with the default budget

    def spent() -> None:
        raise BudgetError("a search: none left in this window")

    monkeypatch.setattr(s.budget, "admit_search", spent)  # every search refused from here on
    monkeypatch.setattr(s, "_engine", lambda: type("E", (), {"survey_stored": lambda *a: False})())
    answer = s.compare_lines(G1, 4)
    for line in answer["lines"].values():
        assert line["search"] == "budget" and line["end"]["end_score"] is None
        assert line["end"]["score_ref"] is None and line["material"]  # moves and material stand
    assert answer["searches"] == {"run": 0, "stored": 0} and "budget_left" in answer
    s.close()


def test_compare_lines_numbers_its_moves(s) -> None:
    answer = s.compare_lines(G1, 4)
    assert answer["move"] == "2...Nf6"
    assert answer["best_move"] is None or answer["best_move"].startswith("2...")


def test_a_status_alone_is_brief_as_with_other_families(s) -> None:
    """TO review F2: the brief `status` does not depend on the other families asked for."""

    at = {"ply": 6, "at": "after"}
    alone = s.facts(G3, at, ["status"])["families"]["status"]["record"]
    with_pieces = s.facts(G3, at, ["status", "pieces"])["families"]["status"]["record"]
    full = s.facts(G3, at, ["status"], view="full")["families"]["status"]["record"]
    assert alone == with_pieces
    assert isinstance(alone["legal_moves"], str) and isinstance(full["legal_moves"], list)
    assert alone["legal_moves"].startswith(f"{len(full['legal_moves'])} ")


def _compared_submission(s) -> tuple[dict, dict, dict]:
    """A commentary of ply 4 citing `compare_lines`: the played line's material (its `x`), its end
    score (its `score_ref`, an `s`) and the root's played score (the record's `s`)."""

    answer = s.compare_lines(G1, 4)
    played = answer["lines"]["played"]
    end = s.handles.resolve(played["end"]["score_ref"], s.game(G1).key).item
    root = s.handles.resolve(answer["root"]["played"]["score_ref"], s.game(G1).key).item
    j = s.ply(G1, 4, view="full")["analysis"]["judgements"][0]
    propositions = [
        {"id": "p1", "kind": "judgement", "judgement": j["ref"], "move": "Nf6", "grade": j["grade"],
         "label": j["label"], "best_move": (j.get("best") or j["played"])["move"]["san"]},
        {"id": "p2", "kind": "material", "line": played["ref"], "from": 0, "to": 1,
         "side": "white", "balance": played["material"][0]},
        {"id": "p3", "kind": "engine_score", "line": played["end"]["score_ref"],
         "move": end["move"]["uci"], "score": end["score"]},
        {"id": "p4", "kind": "engine_score", "line": answer["root"]["played"]["score_ref"],
         "move": root["move"]["uci"], "score": root["score"]},
    ]  # fmt: skip
    sentences = [
        {"text": f"2...Nf6는 {j['grade']}이다.", "class": "sourced", "cites": ["p1"]},
        {"text": f"둔 수 뒤 엔진 라인의 첫 수에서 백의 물질 변화는 {played['material'][0]}점이다.",
         "class": "sourced", "cites": ["p2"]},
        {"text": f"그 라인 끝의 엔진 평가는 {played['end']['end_score']}이다.", "class": "sourced",
         "cites": ["p3"]},
        {"text": f"둔 수의 평가는 {answer['root']['played']['score']}이다.", "class": "sourced",
         "cites": ["p4"]},
    ]  # fmt: skip
    return {"propositions": propositions, "sentences": sentences}, played, answer


def test_a_commentary_citing_compare_lines_is_accepted_by_submit(s) -> None:
    """TO review F3: through `submit_commentary`, the material cited from the line's `x` and the
    scores cited from the `s` handles are accepted."""

    submission, _, _ = _compared_submission(s)
    answer = s.submit_commentary(G1, ply=4, agent={"name": "t", "model": "m"}, **submission)
    assert answer["accepted"] and answer["level"] == "SOURCE_VERIFIED", answer


def test_a_score_cited_from_the_lines_x_alone_is_refused_by_submit(s) -> None:
    """TO review F3 (C1): an end score cited from the line's `x` is refused at submission."""

    submission, played, _ = _compared_submission(s)
    p3 = next(p for p in submission["propositions"] if p["id"] == "p3")
    p3["line"] = played["ref"]  # the explored line's handle: it backs no score
    answer = s.submit_commentary(G1, ply=4, agent={"name": "t", "model": "m"}, **submission)
    assert not answer["accepted"], answer
    assert "p3" in json.dumps(answer["violations"], ensure_ascii=False)
