"""AF (agent-af-design.md): analysis first at a game position (§2.1–§2.4), the ledger's standing
(§3), disagreements shown (§2.6) and the plies' origins recorded (§5.1)."""

from __future__ import annotations

import json

import chess
import pytest
from agent_helpers import gid, session

from calliope.agent import AgentError
from calliope.agent.lines import DISAGREE_CP, analysis_score, disagrees, ledger, standing_white

TRADE = "1. e4 d5 2. exd5 Qxd5 3. Nc3 Qa5 *"
OTHER = "1. d4 d5 2. c4 e6 *"


@pytest.fixture
def s(tmp_path):
    s = session(tmp_path)
    for pgn in (TRADE, OTHER):
        s.open_game(pgn=pgn)
    yield s
    s.close()


def stored(s, pgn: str, ply: int) -> dict:
    game = s.game(gid(pgn))
    return s._analysis_at(game, tuple(game.parsed.uci[: ply - 1]))


def pv(line: dict) -> list[str]:
    return [p["uci"] for p in line.get("pv") or []]


def line_of(found: dict, name: str) -> dict:
    return next(line for n, line in found["lines"] if n == name)


# -- T1: analysis first (§2.1–§2.3) -----------------------------------------------------------


def test_nothing_is_read_from_a_ply_that_is_not_stored(s) -> None:
    game = s.game(gid(TRADE))
    assert not s._cached(game.parsed, 3)
    a = s.explore(gid(TRADE), {"ply": 3, "at": "before"}, ["exd5"], search=True)
    assert not s._cached(game.parsed, 3)  # no analysis started (§2.1)
    assert "analysis_score" not in a["ledger"] and "departs_at" not in a
    assert a["ledger"]["end_score"]["source"] == "search"


def test_the_next_plys_record_never_answers_a_line_of_this_ply(s) -> None:
    s.ply(gid(TRADE), 4)  # ply 4 stored, ply 3 not
    a = s.explore(gid(TRADE), {"ply": 3, "at": "before"}, ["exd5"], search=True)
    assert "analysis_score" not in a["ledger"] and a["ledger"]["end_score"]["source"] == "search"


def test_moves_along_an_analysis_line_answer_its_score_and_no_search(s) -> None:
    s.ply(gid(TRADE), 3)
    found = stored(s, TRADE, 3)
    played = line_of(found, "played")
    used = s.budget.meter.used
    a = s.explore(gid(TRADE), {"ply": 3, "at": "before"}, [pv(played)[0]], search=True,
                  continue_with="engine", length=3)  # fmt: skip
    assert s.budget.meter.used == used  # no search admitted
    book = a["ledger"]
    assert "end_score" not in book  # an analysis score is never an end score (§2.2)
    sources = [p["source"] for p in book["plies"]]
    assert sources[0] == "agent" and set(sources[1:]) == {"analysis"}
    assert [p["san"].split(".")[-1] for p in book["plies"]] == [p["san"] for p in played["pv"]][
        : len(sources)
    ]
    score = book["analysis_score"]
    assert score["source"] == "analysis" and score["score_at"] == "root" and score["root"] == "before"
    assert score["root_ply"] == 3 and score["line"] == "played"
    assert score["evaluated_move"] == "2.exd5" and score["pv_followed"] == len(sources)
    assert score["score_ref"] == played["ref"] and score["depth"] == played["depth"]
    assert score["profile"] == found["record"]["evaluation"]["search"]["profile"]


def test_continue_stops_where_the_analysis_line_ends(s) -> None:
    s.ply(gid(TRADE), 3)
    played = line_of(stored(s, TRADE, 3), "played")
    a = s.explore(gid(TRADE), {"ply": 3, "at": "before"}, [pv(played)[0]], search=True,
                  continue_with="engine", length=16)  # fmt: skip
    if len(pv(played)) < 16:
        assert a["analysis_ends_at"] == len(pv(played)) == len(a["ledger"]["plies"])


def test_no_moves_give_the_roots_best_and_played_scores(s) -> None:
    s.ply(gid(TRADE), 3)
    used = s.budget.meter.used
    a = s.explore(gid(TRADE), {"ply": 3, "at": "before"}, [], search=True)
    assert s.budget.meter.used == used
    scores = a["ledger"]["analysis_score"]
    assert set(scores) <= {"best", "played"} and "best" in scores
    assert scores["best"]["line"] == "best" and scores["best"]["pv_followed"] == 0
    assert "end_score" not in a["ledger"]


def test_fresh_searches_the_end_beside_the_analysis_and_compares(s) -> None:
    s.ply(gid(TRADE), 3)
    played = line_of(stored(s, TRADE, 3), "played")
    a = s.explore(gid(TRADE), {"ply": 3, "at": "before"}, [pv(played)[0]], search="fresh")
    book = a["ledger"]
    assert book["analysis_score"]["source"] == "analysis"
    assert book["end_score"]["source"] == "search" and book["end_score"]["end_score_at"] == 1
    d = a["disagreement"]
    assert d["analysis"]["root_ply"] == 3 and d["analysis"]["evaluated_move"] == "2.exd5"
    assert d["analysis"]["pv_followed"] == 1 and d["search"]["fen"]
    assert d["search"]["path"][-1] == pv(played)[0]
    assert isinstance(d["disagrees_with_analysis"], bool)


def test_moves_that_leave_the_analysis_say_where(s) -> None:
    s.ply(gid(TRADE), 3)
    played = line_of(stored(s, TRADE, 3), "played")
    board = chess.Board()
    for uci in s.game(gid(TRADE)).parsed.uci[:2]:
        board.push_uci(uci)
    board.push_uci(pv(played)[0])
    other = next(m.uci() for m in board.legal_moves if m.uci() != pv(played)[1])
    a = s.explore(gid(TRADE), {"ply": 3, "at": "before"}, [pv(played)[0], other], search=True,
                  continue_with="engine", length=2)  # fmt: skip
    departs = a["departs_at"]
    assert departs["ply"] == 2 and departs["analysis_move"] == played["pv"][1]["san"]
    assert departs["analysis_score"]["pv_followed"] == 1
    sources = [p["source"] for p in a["ledger"]["plies"]]
    assert sources[:2] == ["agent", "agent"] and set(sources[2:]) <= {"search"}
    assert a["ledger"]["end_score"]["source"] == "search"


def test_search_takes_only_true_false_or_fresh(s) -> None:
    with pytest.raises(AgentError, match="fresh"):
        s.explore(gid(TRADE), {"ply": 3, "at": "before"}, ["exd5"], search="deep")


# -- compare_lines (§2.4) ---------------------------------------------------------------------


def test_compare_lines_carries_the_analysis_score_and_one_search_at_the_given_end(s) -> None:
    g = gid(TRADE)
    s.ply(g, 4)
    origins = []
    s._origin = lambda answer, sources: origins.append(list(sources))
    a = s.compare_lines(g, 4, length=2)
    line = a["lines"]["played"]
    assert line["analysis_score"]["line"] == "played" and line["analysis_score"]["root_ply"] == 4
    end = line["end"]
    if "end_score" in end and end["end_score"] is not None:
        assert end["source"] == "search" and end["end_score_at"] == 2  # the given moves' end
        assert "disagreement" in line
    assert "_top" not in line and "_fen" not in line
    given = [o for o in origins if o and o[0] == "analysis"]
    assert given and all(set(o[:2]) == {"analysis"} and set(o[2:]) <= {"search"} for o in given)
    assert any(o and o[0] == "game" for o in origins)  # the game's own moves


def test_the_ranking_reads_the_analysis_when_every_move_has_a_line(s) -> None:
    g = gid(TRADE)
    s.ply(g, 4)
    found = stored(s, TRADE, 4)
    alternative = next((ln for n, ln in found["lines"] if n == "alternative"), None)
    if alternative is None:
        pytest.skip("the analysis holds no alternative here")
    a = s.compare_lines(g, 4, length=2, candidates=[pv(alternative)[0]])
    assert a["ranking"]["source"] == "analysis"
    for entry in a["ranking"]["moves"]:
        if entry.get("source") != "board":
            assert entry["source"] == "analysis" and entry["at"].startswith("the root")
            assert entry["analysis_score"]["score_at"] == "root"
    cand = a["lines"]["candidates"][0]
    assert "analysis_score" in cand and "end_score_at" not in cand["end"]


def test_the_ranking_searches_when_a_move_has_no_analysis_line(s) -> None:
    g = gid(TRADE)
    s.ply(g, 4)
    found = stored(s, TRADE, 4)
    firsts = {pv(ln)[0] for _, ln in found["lines"] if pv(ln)}
    board = chess.Board()
    for uci in s.game(g).parsed.uci[:3]:
        board.push_uci(uci)
    outside = next((m.uci() for m in board.legal_moves if m.uci() not in firsts), None)
    if outside is None:
        pytest.skip("every legal move has an analysis line")
    a = s.compare_lines(g, 4, length=2, candidates=[outside])
    assert a["ranking"]["source"] == "search"
    played = next(e for e in a["ranking"]["moves"] + a["ranking"].get("unranked", [])
                  if e["role"] == "played")  # fmt: skip
    assert played.get("source") in ("search", None) and "analysis_score" in played


# -- T2: the ledger's standing (§3) -----------------------------------------------------------


def test_the_standing_beside_the_change() -> None:
    assert standing_white(chess.STARTING_FEN) == 0
    board = chess.Board()
    for san in ("e4", "d5", "exd5"):
        board.push_san(san)
    assert standing_white(board.fen()) == 1


def test_the_ledger_gives_the_standing_at_start_each_ply_and_end(s) -> None:
    a = s.explore(gid(TRADE), {"ply": 4, "at": "before"}, ["Qxd5", "Nc3"])
    book = a["ledger"]
    assert book["standing"]["start"]["white_minus_black"] == 1  # after 2.exd5, White a pawn up
    assert [p["standing_white"] for p in book["plies"]] == [0, 0]
    assert book["standing"]["end"]["white_minus_black"] == 0
    assert book["net"]["white"] == (
        book["standing"]["end"]["white_minus_black"]
        - book["standing"]["start"]["white_minus_black"]
    )
    assert book["standing"]["leader_at_end"] == "level"
    assert "not who is ahead" in book["note"]


def test_the_ledger_function_keeps_net_as_the_change() -> None:
    plies = [{"move": {"mover": "black", "san": "Qxd5", "piece": {"color": "black"}, "events": []},
              "material_balance_white": -1}]  # fmt: skip
    board = chess.Board()
    for san in ("e4", "d5", "exd5"):
        board.push_san(san)
    book = ledger(plies, board.fen())
    assert book["net"]["white"] == -1 and book["standing"]["end"]["white_minus_black"] == 0


# -- T3: disagreements (§2.6) -----------------------------------------------------------------


def test_disagreement_is_a_kind_or_more_than_a_pawn() -> None:
    assert not disagrees({"cp": 100}, {"cp": 100 + DISAGREE_CP})  # 1.00 exactly: not above
    assert disagrees({"cp": 100}, {"cp": 101 + DISAGREE_CP})
    assert disagrees({"cp": 300}, {"mate": 4})  # a mate against centipawns
    assert disagrees({"cp": 40}, {"cp": -40})  # opposite sides, though only 0.80 apart
    assert not disagrees({"cp": 25}, {"cp": 35})  # the band against just outside: not a side
    assert not disagrees(None, {"cp": 10}) and not disagrees({"terminal": "checkmate"}, {"cp": 1})


def test_an_analysis_score_says_where_it_was_read() -> None:
    line = {"score": {"cp": -150}, "depth": 12, "ref": "s1.x"}
    a = analysis_score(line, root_ply=7, evaluated_move="4.Nf3", line_name="best", pv_followed=3,
                       mover="white", profile="d12_mpv5_v1")  # fmt: skip
    assert a == {"source": "analysis", "root_ply": 7, "root": "before", "evaluated_move": "4.Nf3",
                 "line": "best", "score_at": "root", "pv_followed": 3, "white_view": "-1.50",
                 "for_mover": "-1.50", "mover": "white", "favours": "black", "depth": 12,
                 "profile": "d12_mpv5_v1", "score_ref": "s1.x"}  # fmt: skip


# -- origins recorded (§5.1) ------------------------------------------------------------------


class Recorded:
    def __init__(self):
        self.lines = []

    def origin(self, ref, plies_origin):
        self.lines.append(("origin", ref, list(plies_origin)))

    def disagreement(self, entry):
        self.lines.append(("disagreement", entry))

    def __getattr__(self, name):  # every other recorder call is not this test's
        return lambda *a, **k: None


def test_explore_records_each_plys_origin(s) -> None:
    s.ply(gid(TRADE), 3)
    played = line_of(stored(s, TRADE, 3), "played")
    s.recorder = Recorded()
    a = s.explore(gid(TRADE), {"ply": 3, "at": "before"}, [pv(played)[0]], search=True,
                  continue_with="engine", length=2)  # fmt: skip
    origin = [x for x in s.recorder.lines if x[0] == "origin" and x[1] == a["ref"]]
    assert origin and origin[-1][2] == [p["source"] for p in a["ledger"]["plies"]]


# -- review F1, F2 of the implementation's rev. 2 --------------------------------------------


def _as_best(found: dict) -> dict:
    """The stored analysis with the played move made the best (same rank, same line)."""

    record = json.loads(json.dumps(found["record"]))
    subject = record["analysis"]["judgements"][0]
    subject["best"] = json.loads(json.dumps(subject["played"]))
    from calliope.agent.session import _stored

    return _stored(record, found["ply"])


def test_the_played_move_being_the_best_keeps_both_roles(s, monkeypatch) -> None:
    s.ply(gid(TRADE), 3)
    same = _as_best(stored(s, TRADE, 3))
    assert set(same["roles"]) == {"best", "played"}
    assert len([n for n, _ in same["lines"] if n in ("best", "played")]) == 1  # one line to follow
    monkeypatch.setattr(s, "_analysis_at", lambda game, base: same)
    a = s.explore(gid(TRADE), {"ply": 3, "at": "before"}, [], search=True)
    assert set(a["ledger"]["analysis_score"]) == {"best", "played"}
    fresh = s.explore(gid(TRADE), {"ply": 3, "at": "before"}, [], search="fresh")
    assert fresh["disagreement"]["analysis"]["line"] == "best"  # compared, not skipped


def test_compare_lines_records_the_searched_handle_and_the_extended_one(s) -> None:
    g = gid(TRADE)
    s.ply(g, 4)
    served = {}
    s._origin = lambda answer, sources: served.setdefault(answer["ref"], list(sources))
    a = s.compare_lines(g, 4, length=16)
    for line in a["lines"].values():
        if isinstance(line, dict):
            assert line["ref"] in served and line["searched"]["ref"] in served
            searched = served[line["searched"]["ref"]]
            assert len(searched) == line["searched"]["plies"] and "search" not in searched
