"""AG-D §11 tests 2–4: the tools' work in a session on the synthetic engine — answers, isolation
of the stored analyses, the facts tree against the stored trees, and handles."""

from __future__ import annotations

import pytest
from agent_helpers import G1, GAME, PROMOTION, session

from calliope.agent import AgentError, GameError, HandleError
from calliope.agent.session import variation
from calliope.results import EngineRun, PlyInput, game_result
from calliope.server import analyse_game, analyse_ply

ADDED = ("ref", "pv", "depth", "label")  # the session's additions: refs, PVs, depths, the label


def _plain(value):
    """The answer without the session's additions (applied to both sides of a comparison)."""

    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items() if k not in ADDED}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _refs(value, out=None) -> list[str]:
    out = [] if out is None else out
    if isinstance(value, dict):
        if "ref" in value:
            out.append(value["ref"])
        for v in value.values():
            _refs(v, out)
    elif isinstance(value, list):
        for v in value:
            _refs(v, out)
    return out


# -- open_game ------------------------------------------------------------------------------------


def test_open_game_reads_a_pgn_and_analyses_only_the_plies_asked(tmp_path) -> None:
    s = session(tmp_path)
    game = s.open_game(pgn=GAME)
    assert game["game"] == G1 and len(game["moves"]) == 10
    assert not any(m["cached"] for m in game["moves"]) and s.budget.meter.used == 0
    assert "grade" not in game["moves"][0]
    again = s.open_game(pgn=GAME, plies="2-3")
    assert [m["cached"] for m in again["moves"][:4]] == [False, True, True, False]
    assert {"grade", "label", "text"} <= set(again["moves"][1])
    assert again["game"] == G1 and again["game_key"] == game["game_key"]  # AG4-D G1


def test_open_game_takes_a_fen_and_moves_in_san_or_uci(tmp_path) -> None:
    s = session(tmp_path)
    game = s.open_game(fen="8/P6k/8/8/8/8/8/K7 w - - 0 1", moves=["a8=Q", "h7g6", "Qb8"])
    assert [m["san"] for m in game["moves"]] == ["a8=Q", "Kg6", "Qb8"]
    assert set(game["headers"]) <= {"result"} and game["start_fen"].startswith("8/P6k")
    with pytest.raises(AgentError, match="not legal"):
        s.open_game(moves=["e4", "e4"])
    with pytest.raises(AgentError, match="either"):
        s.open_game()


def test_open_game_refuses_a_ply_range_outside_the_game_and_registers_nothing(tmp_path) -> None:
    s = session(tmp_path)
    for plies in ("0", "0-2", "99"):
        with pytest.raises(AgentError, match="outside the game"):
            s.open_game(pgn=GAME, plies=plies)
    assert not s.held and s.budget.uncached.used == 0 and not s.records.keys("")
    assert s.open_game(pgn=GAME)["game"] == G1


# -- ply and judge_move (§3.1, §3.3) ---------------------------------------------------------------


def test_ply_is_the_documents_analysis_with_handles(tmp_path) -> None:
    s = session(tmp_path)
    s.open_game(pgn=GAME)
    record = s.ply(G1, 3)
    document = analyse_game(s.slot, s.game(G1).parsed, range(3, 4), s.cache, detail=True)
    expected = document["plies"][0]
    assert _plain(record["analysis"]) == _plain(expected["analysis"])
    best = record["analysis"]["judgements"][0]["best"]
    assert best["pv"] and best["pv"][0]["by"] == "engine" and best["depth"] == 12
    assert record["grade"] == expected["grade"] and record["text"] == expected["text"]
    analysis = record["analysis"]
    assert all(c["ref"].startswith("c") for c in analysis["claims"])
    assert all(j["ref"].startswith("j") for j in analysis["judgements"])
    assert analysis["judgements"][0]["best"]["ref"].startswith("s")
    lines = {}  # one item, one handle (AG4-D §3.3): a line that is both played and best
    for judgement in analysis["judgements"]:
        for line in (judgement["played"], judgement["best"], *judgement["alternatives"]):
            if line is not None:
                assert lines.setdefault(line["ref"], line) == line
    refs = [r for r in _refs(record) if r not in lines]
    assert len(refs) == len(set(refs))  # the others are unique


def test_judge_move_judges_a_played_and_an_unplayed_move(tmp_path) -> None:
    s = session(tmp_path)
    s.open_game(pgn=GAME)
    played = s.judge_move(G1, {"ply": 3, "at": "before"}, "exd5")
    assert played["played"] and _plain(played["analysis"]) == _plain(s.ply(G1, 3)["analysis"])
    unplayed = s.judge_move(G1, {"ply": 3, "at": "before"}, "e4e5")
    assert not unplayed["played"] and unplayed["san"] == "e5" and unplayed["ply"] == 3
    parsed = variation(s.game(G1).parsed, ["e2e4", "d7d5", "e4e5"])
    engine = list(s.slot.port.identity.fingerprint())
    analysis, rendered = analyse_ply(s.slot, parsed, 3, s.profile, engine)
    direct = game_result(parsed.game, EngineRun(s.slot.port.identity, s.profile),
                         [PlyInput(3, analysis, rendered)], analysis=True)  # fmt: skip
    assert _plain(unplayed["analysis"]) == _plain(direct["plies"][0]["analysis"])
    from_root = s.judge_move(G1, {"from_root": ["e4", "d5"]}, "e5")
    assert from_root["cached"] and _plain(from_root["analysis"]) == _plain(unplayed["analysis"])


def test_positions_are_checked(tmp_path) -> None:
    s = session(tmp_path)
    s.open_game(pgn=GAME)
    for position in ({"ply": 0}, {"ply": 11}, {"ply": 2, "at": "during"}, "e4"):
        with pytest.raises(AgentError):
            s.facts(G1, position)
    with pytest.raises(AgentError, match="not legal"):
        s.judge_move(G1, {"ply": 1, "at": "before"}, "e5")
    with pytest.raises(GameError, match="no game"):
        s.ply("g9", 1)


# -- facts and explore (§3.4, §3.7) ----------------------------------------------------------------


def test_facts_name_pieces_by_identity_from_the_games_start(tmp_path) -> None:
    s = session(tmp_path)
    g = s.open_game(pgn=PROMOTION)["game"]
    answer = s.facts(g, {"ply": 1, "at": "after"}, ["move", "status"])
    piece = answer["families"]["move"]["record"]["piece"]
    assert piece == {"piece": "pawn", "color": "white", "origin": "a7", "square": "a8",
                     "type_now": "queen"}  # fmt: skip
    pieces = s.facts(g, {"ply": 1, "at": "after"}, ["pieces"])["families"]["pieces"]["record"]
    queen = next(e for e in pieces["pieces"] if e["square"] == "a8")
    assert queen["piece_type"] == "queen" and queen["identity"] == piece  # the frame's identity
    assert answer["families"]["status"]["ref"].startswith("f")
    root = s.facts(g, {"from_root": []}, ["move"])
    assert root["families"]["move"]["record"]["sentinel"] == "no_edge"
    with pytest.raises(AgentError, match="span"):
        s.facts(g, {"ply": 1}, ["same_side_delta"])
    with pytest.raises(AgentError, match="no fact family"):
        s.facts(g, {"ply": 1}, ["threats"])


def test_explore_marks_the_agents_plies_and_the_engines(tmp_path) -> None:
    s = session(tmp_path)
    s.open_game(pgn=GAME)
    line = s.explore(G1, {"ply": 4, "at": "after"}, ["Nc3", "Nxd5", "Nxd5", "Qxd5"])
    assert [p["by"] for p in line["plies"]] == ["agent"] * 4
    assert [p["material_balance_white"] for p in line["plies"]] == [0, -1, 2, -1]
    assert "search" not in line and s.budget.meter.used == 0
    assert set(line["end_facts"]) == {"status", "pieces", "exchange"}
    assert line["ref"].startswith("x")
    searched = s.explore(G1, {"ply": 4, "at": "after"}, ["Nc3"], search=True)
    assert s.budget.meter.used == 1  # one search, of the end position (AG-D C1)
    lines = searched["search"]["lines"]
    assert len(lines) == 5 and all(p["by"] == "engine" for p in lines[0]["pv"])
    assert all(x["ref"].startswith("s") for x in lines)
    empty = s.explore(G1, {"ply": 4, "at": "after"}, [], search=True)
    assert s.budget.meter.used == 2 and empty["plies"] == [] and empty["search"]["lines"]


# -- isolation (§11 test 3) -------------------------------------------------------------------------


def _stored(tmp_path) -> dict:
    return {p: p.read_bytes() for p in tmp_path.rglob("*") if p.suffix in (".tree", ".graph")}


def test_exploring_and_judging_leave_the_stored_analyses_as_they_were(tmp_path) -> None:
    s = session(tmp_path)
    s.open_game(pgn=GAME, plies="1-3")
    before = _stored(tmp_path)
    s.explore(G1, {"ply": 2, "at": "after"}, ["exd5", "Qxd5"], search=True)
    s.judge_move(G1, {"ply": 3, "at": "before"}, "Nc3")
    s.facts(G1, {"ply": 3, "at": "after"}, ["exchange", "patterns"])
    after = _stored(tmp_path)
    assert {p: after[p] for p in before} == before  # judging added files, changed none


def test_the_facts_tree_holds_the_stored_trees_records(tmp_path) -> None:
    s = session(tmp_path)
    s.open_game(pgn=GAME, plies="3")
    game = s.game(G1)
    key, expected, build, _ = s._key(game.parsed, 3)
    stored = s.cache.get(key, expected, build).analysis
    stored_view = stored.tree.view(stored.rev)
    s.facts(G1, {"ply": 3, "at": "after"})
    view, nodes = s._node(game, game.parsed.uci[:3])
    node, stored_node = nodes[-1], stored_view.root
    for uci in game.parsed.uci[:3]:
        stored_node = stored_view.child(stored_node, uci)
    known = view.families()
    families = sorted(f for f in set(stored_view.families()) & set(known)
                      if known[f][1].value != "span")  # fmt: skip
    s._records(game, view, node, families)
    facts_view = game.facts.view()
    compared = 0
    for family in families:
        try:
            theirs = stored_view.fact(family, stored_node)
        except KeyError:  # not computed in the stored tree
            continue
        assert facts_view.fact(family, node) == theirs, family
        compared += 1
    assert compared >= 8


# -- handles (§3.6, §11 test 4) ---------------------------------------------------------------------


def test_handles_resolve_only_in_their_session_and_game(tmp_path) -> None:
    s, other = session(tmp_path), session(tmp_path)
    s.open_game(pgn=GAME)
    g2 = s.open_game(pgn=PROMOTION)["game"]
    record = s.ply(G1, 1)
    ref = record["analysis"]["claims"][0]["ref"] if record["analysis"]["claims"] else (
        record["analysis"]["judgements"][0]["ref"])  # fmt: skip
    entry = s.handles.resolve(ref, s.game(G1).key)
    assert entry.source["kind"] == "analysis" and entry.source["path"] == ["e2e4"]
    assert entry.source["tree"] == record["bundle"]["tree"]
    with pytest.raises(HandleError, match="another game"):
        s.handles.resolve(ref, s.game(g2).key)
    with pytest.raises(HandleError, match="not served in this session"):
        other.handles.resolve(ref)
    with pytest.raises(HandleError, match="no handle"):
        s.handles.resolve(f"c999.{s.handles.token}")


def test_a_finished_position_is_not_searched_and_costs_nothing(tmp_path) -> None:
    s = session(tmp_path)
    g = s.open_game(pgn="1. f3 e5 2. g4 Qh4# 0-1\n")["game"]
    left = s.budget.left()
    with pytest.raises(AgentError, match="game is over"):
        s.explore(g, {"ply": 4, "at": "after"}, [], search=True)
    assert s.budget.left() == left and s._engine().stored_results == 0
