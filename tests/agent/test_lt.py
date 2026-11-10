"""LT (agent-lt-design.md): `explore`'s line ledger and terminal ends (§2, re-review R1, review N1),
`compare_lines`' candidates and ranking (§3, review F4, re-review R1) and `squares` (§4, re-review
R2)."""

from __future__ import annotations

import pytest
from agent_helpers import gid, session

from calliope.agent import AgentError
from calliope.agent.lines import (
    changed_by_move,
    end_score,
    favours,
    for_side,
    ledger,
    rank_key,
    ranking,
    square_entry,
    vs_played,
)

TRADE = "1. e4 d5 2. exd5 Qxd5 *"
EN_PASSANT = "1. e4 a6 2. e5 f5 *"  # 3.exf6 takes the f5 pawn en passant
CASTLE = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 *"
FOOL = "1. f3 e5 2. g4 Nc6 *"  # at ply 4 Black's 2...Qh4# mates at once
EXPOSED = "1. e4 e5 2. Nf3 d6 3. Ng5 h6 *"
PIN = "1. d4 e5 2. Nc3 Bb4 *"  # the c3 knight is pinned to the king


@pytest.fixture
def s(tmp_path):
    s = session(tmp_path)
    for pgn in (TRADE, EN_PASSANT, CASTLE, FOOL, EXPOSED, PIN):
        s.open_game(pgn=pgn)
    yield s
    s.close()


# -- T1: the ledger (§2) ----------------------------------------------------------------------


def test_a_trade_is_counted_for_each_side_and_matches_the_balance(s) -> None:
    a = s.explore(gid(TRADE), {"ply": 1, "at": "before"}, ["e4", "d5", "exd5", "Qxd5"])
    book = a["ledger"]
    assert [p["san"] for p in book["plies"]] == ["1.e4", "1...d5", "2.exd5", "2...Qxd5"]
    assert book["captured"] == {"by_white": ["Black's pawn d5 (1)"],
                              "by_black": ["White's pawn d5 (1)"]}  # tools v11: the owner
    balance = a["plies"][-1]["material_balance_white"]
    assert book["net"]["white"] == balance and book["net"]["black"] == -balance == 0
    assert book["plies"][2]["captured"] == {"piece": "pawn", "owner": "black", "square": "d5",
                                            "points": 1}  # fmt: skip
    assert "takes Black's pawn on d5 (1)" in book["plies"][2]["says"]
    assert {p["side"] for p in book["plies"]} == {"white", "black"}  # N1: who moved
    assert {p["source"] for p in book["plies"]} == {"agent"}  # N1: where the move came from
    assert book["end"]["gone"] == ["Black pawn d5", "White pawn d5"]
    assert book["end"]["moved_pieces"] == ["Black queen d5"]
    assert book["end"]["status"] == "normal"
    assert "ledger" in s.detail(gid(TRADE), a["ref"])["item"]  # the x record holds it


def test_an_en_passant_capture_names_the_victims_square(s) -> None:
    """Review N1: the captured pawn stands on f5, not on the landing square f6."""

    a = s.explore(gid(EN_PASSANT), {"ply": 4, "at": "after"}, ["exf6"])
    taken = a["ledger"]["plies"][0]["captured"]
    assert taken["square"] == "f5" and taken["en_passant"] is True and taken["owner"] == "black"
    assert a["ledger"]["net"]["for_first_mover"] == 1


def test_castling_moves_king_and_rook(s) -> None:
    a = s.explore(gid(CASTLE), {"ply": 6, "at": "after"}, ["O-O"])
    assert set(a["ledger"]["end"]["moved_pieces"]) == {"White king g1", "White rook f1"}
    assert "castles kingside" in a["ledger"]["plies"][0]["says"]


def test_a_line_that_mates_answers_its_terminal_status_without_a_search(s) -> None:
    """Re-review R1: no search is admitted or charged at a finished position."""

    used = s.budget.meter.used
    a = s.explore(gid(FOOL), {"ply": 3, "at": "after"}, ["Qh4#"], search=True)
    assert a["search"] == {"terminal": "checkmate"}
    assert a["ledger"]["end_score"]["terminal"] == "checkmate"
    assert a["ledger"]["end_score"]["favours"] == "black"
    assert a["ledger"]["end"]["status"] == "checkmate" and a["ledger"]["plies"][0]["mate"] is True
    assert s.budget.meter.used == used


def test_continue_plays_the_engine_line_without_another_search(s) -> None:
    s.explore(gid(TRADE), {"ply": 2, "at": "after"}, ["exd5"], search=True)  # stores the search
    used = s.budget.meter.used
    a = s.explore(gid(TRADE), {"ply": 2, "at": "after"}, ["exd5"], search=True,
                  continue_with="engine", length=3)  # fmt: skip
    assert s.budget.meter.used == used  # the stored search; the extension searched nothing
    sources = [p["source"] for p in a["ledger"]["plies"]]
    assert sources[0] == "agent" and set(sources[1:]) == {"search"} and len(sources) <= 4
    assert a["ledger"]["end_score"]["end_score_at"] == 1


def test_continue_needs_search_and_a_bounded_length(s) -> None:
    with pytest.raises(AgentError, match="needs search"):
        s.explore(gid(TRADE), {"ply": 2, "at": "after"}, ["exd5"], continue_with="engine")
    with pytest.raises(AgentError, match="length"):
        s.explore(gid(TRADE), {"ply": 2, "at": "after"}, ["exd5"], search=True,
                  continue_with="engine", length=17)  # fmt: skip
    with pytest.raises(AgentError, match="continue"):
        s.explore(gid(TRADE), {"ply": 2, "at": "after"}, ["exd5"], search=True, continue_with="x")


def test_a_promotion_on_records_made_by_hand() -> None:
    pawn = {"piece": "pawn", "color": "white", "origin": "a2", "square": "a8", "type_now": "queen"}
    plies = [{"ply": 1, "material_balance_white": 8, "move": {
        "san": "a8=Q", "mover": "white", "piece": pawn, "piece_type": "pawn", "from_square": "a7",
        "to_square": "a8", "castling": None, "gives_check": False, "gives_mate": False,
        "events": [{"piece": pawn, "to": "queen"}]}}]  # fmt: skip
    book = ledger(plies, "8/P7/8/8/8/8/8/k6K w - - 0 60")
    assert (
        book["plies"][0]["promotion"] == "queen" and "promotes to queen" in book["plies"][0]["says"]
    )
    assert book["net"] == {"white": 8, "black": -8, "first_mover": "white", "for_first_mover": 8}
    assert book["end"]["moved_pieces"] == ["White queen a8"]


# -- scores and the ranking (§3) --------------------------------------------------------------


def test_scores_for_the_mover_and_the_side_they_favour() -> None:
    assert for_side({"cp": 120}, "black") == {"cp": -120}
    assert for_side({"mate": 3}, "black") == {"mate": -3}
    assert favours({"cp": 30}) == "neither" and favours({"cp": 31}) == "white"
    assert favours({"cp": -31}) == "black" and favours({"mate": -2}) == "black"
    assert favours({"terminal": "stalemate"}) == "neither"
    assert end_score({"cp": -250}, "black", "s1.x")["for_side_to_move"] == "+2.50"


def test_the_ranking_order_with_mates_and_terminal_positions() -> None:
    """Review F4, re-review R1: a checkmate by the move first, a mate for the mover, centipawns
    and the drawn endings at 0.00, a mate against the mover last; an unscored move unranked."""

    entries = [
        {"role": "played", "move": "a", "for_mover": {"cp": 50}},
        {"role": "best", "move": "b", "for_mover": {"mate": 3}},
        {
            "role": "candidate",
            "move": "c",
            "for_mover": {"terminal": "checkmate", "winner": "black"},
        },
        {"role": "candidate", "move": "d", "for_mover": {"terminal": "stalemate"}},
        {"role": "candidate", "move": "e", "for_mover": {"mate": -2}},
        {"role": "candidate", "move": "f", "for_mover": None, "search": "budget"},
        {"role": "candidate", "move": "g", "for_mover": {"cp": 40}},
    ]
    ordered, unranked = ranking(entries, "black")
    assert [e["move"] for e in ordered] == ["c", "b", "a", "g", "d", "e"]
    assert [e["move"] for e in unranked] == ["f"] and "rank" not in unranked[0]
    by = {e["move"]: e for e in ordered}
    assert by["g"]["vs_played"] == "-0.10" and by["g"].get("close") is True
    assert by["d"]["vs_played"] == "-0.50"
    assert by["b"]["vs_played"] == "mate in 3 for the mover against +0.50"
    assert rank_key({"mate": 1}, "white") > rank_key({"mate": 5}, "white")
    assert rank_key({"mate": -5}, "white") > rank_key({"mate": -1}, "white")
    assert vs_played({"cp": 10}, None) is None


def test_a_candidate_that_mates_is_ranked_first_from_the_board(s) -> None:
    """Re-review R1: Black's 2...Qh4# at ply 4 of the fool's mate is not searched and not
    unranked; its FEN and status are in the k record."""

    g = gid(FOOL)
    s.ply(g, 4)
    a = s.compare_lines(g, 4, length=4, candidates=["Qh4#"])
    first = a["ranking"]["moves"][0]
    assert first["role"] == "candidate" and first["for_mover"]["terminal"] == "checkmate"
    assert first["source"] == "board" and "fen_after" in first and "score_ref" not in first
    assert a["ranking"]["for"] == "black" and "unranked" not in a["ranking"]
    item = s.detail(g, a["ref"])
    assert (
        item["kind"] == "comparison"
        and item["item"]["ranking"]["moves"][0]["move"] == first["move"]
    )


def test_every_ranked_score_comes_from_a_search_after_the_move(s) -> None:
    """Review F4: played, best and candidates scored the same way; `root` never ranked."""

    g = gid(TRADE)
    s.ply(g, 4)
    a = s.compare_lines(g, 4, length=4, candidates=["Nf6", "e5"])
    ranked = a["ranking"]["moves"] + a["ranking"].get("unranked", [])
    assert {e["role"] for e in ranked} >= {"played", "candidate"}
    for entry in a["ranking"]["moves"]:
        assert entry["at"] == "after the move" and entry["score_ref"].startswith("s")
    assert "ranking" not in a["root"]
    assert {c["move"] for c in a["lines"]["candidates"]} == {"2...Nf6", "2...e5"}
    for line in a["lines"]["candidates"]:
        assert set(line["ledger"]) == {"captured", "net", "standing", "end"}
    for line in ("played", "game"):
        assert set(a["lines"][line]["ledger"]) == {"captured", "net", "standing", "end"}


def test_candidates_are_checked_before_any_work(s) -> None:
    g = gid(TRADE)
    s.ply(g, 4)
    used = s.budget.meter.used
    for bad in ([], ["a", "b", "c", "d", "e"], "Nf6", [3]):
        with pytest.raises(AgentError, match="candidates"):
            s.compare_lines(g, 4, candidates=bad)
    with pytest.raises(AgentError, match="not legal"):
        s.compare_lines(g, 4, candidates=["Ke7"])
    assert s.budget.meter.used == used


def test_a_k_handle_is_not_citable(s) -> None:
    from calliope.agent.propositions import Refused, Verifier

    g = gid(TRADE)
    s.ply(g, 4)
    a = s.compare_lines(g, 4, length=2, candidates=["Nf6"])
    with pytest.raises(Refused):
        Verifier(s, s.game(g)).verify({"id": "p", "kind": "explored_line", "line": a["ref"]})


# -- T3: squares (§4) -------------------------------------------------------------------------


def test_squares_lists_every_attacker_and_defender_and_the_change(s) -> None:
    g = gid(EXPOSED)
    a = s.squares(g, {"ply": 5, "at": "after"}, ["f7", "g5", "e6"])
    f7, g5, e6 = a["squares"]
    assert f7["piece"] == "pf7" and [x["piece"] for x in f7["attackers"]] == ["Ng5"]
    assert [x["piece"] for x in f7["defenders"]] == ["ke8"]
    assert f7["changed_by_move"]["attackers"] == {"lost": [], "gained": ["Ng5"], "kept": []}
    assert f7["changed_by_move"]["defenders"]["kept"] == ["ke8"]
    assert g5["piece"] == "Ng5" and [x["piece"] for x in g5["attackers"]] == ["qd8"]
    assert e6["piece"] is None  # an empty square: attackers by side, by reverse lookup (R2)
    assert "Ng5" in [x["piece"] for x in e6["attackers"]["white"]]
    assert {"bc8", "pf7"} <= {x["piece"] for x in e6["attackers"]["black"]}
    assert a["refs"]["pieces"].startswith("f")


def test_a_pinned_attacker_is_included_marked_and_cannot_move_there(s) -> None:
    """Re-review R2: the c3 knight attacks e4 but is pinned to the king by the b4 bishop."""

    a = s.squares(gid(PIN), {"ply": 4, "at": "after"}, ["e4"])
    white = {x["piece"]: x for x in a["squares"][0]["attackers"]["white"]}
    assert white["Nc3"]["absolutely_pinned"] == {"pinner": "bb4"}
    assert white["Nc3"]["can_move_there"] is False


def test_squares_checks_its_arguments(s) -> None:
    for bad in ([], ["z9"], ["a1"] * 9, "e4"):
        with pytest.raises(AgentError, match="squares"):
            s.squares(gid(PIN), {"ply": 4, "at": "after"}, bad)


def test_square_entries_on_records_made_by_hand() -> None:
    """A defender keeps its place when a rook leaves (the f7 case of LT-D §0.2)."""

    def piece(square, color, kind, attackers=(), defenders=(), dest=()):
        return {"square": square, "color": color, "piece_type": kind,
                "attacks": {"empty": [], "friendly": [], "enemy": []},
                "attackers": [{"square": q, "absolutely_pinned": False} for q in attackers],
                "defenders": [{"square": q} for q in defenders], "legal_destinations": list(dest),
                "identity": {"color": color, "origin": square}}  # fmt: skip

    before = [piece("f7", "black", "pawn", ["d5"], ["f8", "g8", "d6"]), piece("f8", "black", "rook"),
              piece("g8", "black", "king"), piece("d6", "black", "knight"),
              piece("d5", "white", "bishop", dest=["f7"])]  # fmt: skip
    after = [piece("f7", "black", "pawn", ["d5"], ["g8", "d6"]), piece("e8", "black", "rook"),
             piece("g8", "black", "king"), piece("d6", "black", "knight"),
             piece("d5", "white", "bishop", dest=["f7"])]  # fmt: skip
    after[1]["identity"] = {"color": "black", "origin": "f8"}
    change = changed_by_move("f7", before, after)
    assert change["defenders"] == {"lost": ["rf8"], "gained": [], "kept": ["kg8", "nd6"]}
    entry = square_entry("f7", after, None)
    assert [x["piece"] for x in entry["defenders"]] == ["kg8", "nd6"]
    assert entry["attackers"] == [{"piece": "Bd5", "can_move_there": True}]


def test_can_move_there_is_null_for_the_side_not_to_move(s) -> None:
    """LT review F4: after 3.Ng5 Black is to move, so White's legal moves are not observed: the
    knight's attack on f7 says nothing about whether it may move there."""

    a = s.squares(gid(EXPOSED), {"ply": 5, "at": "after"}, ["f7"])
    [knight] = a["squares"][0]["attackers"]
    assert knight["piece"] == "Ng5" and knight["can_move_there"] is None
    hand = square_entry("e4", [{"square": "c3", "color": "white", "piece_type": "knight",
                                "attacks": {"empty": ["e4"]},
                                "legal_destinations": {"sentinel": "not_observed"}}], None)  # fmt: skip
    assert hand["attackers"]["white"] == [{"piece": "Nc3", "can_move_there": None}]
