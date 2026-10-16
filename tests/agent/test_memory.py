"""AG4-D §5 (memory, handles, read-only tools, store reset, server, hosts): the work state of a
process is bounded and evicted least recently used first, never the call's own game; the same item
gets the same handle; read-only tools change no work state; the budget is the process's."""

from __future__ import annotations

import copy

import anyio
import pytest
from agent_helpers import G1, GAME, gid, session

from calliope.agent import BudgetError, HandleError, HandleExpired, Handles, Limits

pytest.importorskip("mcp", reason="the MCP SDK is the optional group `agent`")

from mcp import Client

from calliope.agent.server import build_server


def named(i: int) -> str:
    """GAME under another White: another game, the same ply-cache keys (no ratings)."""

    return f'[White "p{i}"]\n\n{GAME}'


def _nodes(s) -> int:
    return sum(g.facts_nodes for g in s.held.values())


# -- memory (B3) -----------------------------------------------------------------------------------


def test_many_games_stay_within_the_node_and_game_limits(tmp_path) -> None:
    s = session(tmp_path, Limits(max_nodes_per_tree=5, max_nodes_total=12, max_open_games=3))
    for i in range(6):
        game = s.open_game(pgn=named(i))["game"]
        answer = s.facts(game, {"ply": 3, "at": "after"})  # the root and three plies
        assert answer["budget_left"]["nodes"] == 1
        assert len(s.held) <= 3 and _nodes(s) <= 12 and s.game(game).facts_nodes == 4
    with pytest.raises(BudgetError, match="facts tree refuses 2 new nodes"):
        s.facts(game, {"ply": 5, "at": "after"})


def test_the_least_recently_used_game_is_evicted_never_the_current(tmp_path) -> None:
    s = session(tmp_path, Limits(max_open_games=2))
    a, b, c = (s.open_game(pgn=named(i))["game"] for i in range(3))
    keys = {g: s.game(g, hold=False).key for g in (a, b, c)}
    assert list(s.held) == [keys[b], keys[c]]  # opening c put a away
    s.facts(b, {"ply": 1, "at": "after"})  # b is now the most recent
    s.facts(a, {"ply": 1, "at": "after"})  # a is held again, c put away
    assert list(s.held) == [keys[b], keys[a]]
    small = session(tmp_path / "small", Limits(max_nodes_total=4))
    a, b = (small.open_game(pgn=named(i))["game"] for i in range(2))
    small.facts(a, {"ply": 3, "at": "after"})  # 4 nodes
    small.facts(b, {"ply": 1, "at": "after"})  # 2 more: a is put away, not b
    assert list(small.held) == [small.game(b, hold=False).key]
    small.facts(b, {"ply": 3, "at": "after"})
    with pytest.raises(BudgetError, match="the game alone would pass .* 4 nodes"):
        small.facts(b, {"ply": 4, "at": "after"})


def test_an_evicted_games_handles_expire_and_its_id_still_works(tmp_path) -> None:
    s = session(tmp_path, Limits(max_open_games=1))
    s.open_game(pgn=GAME, plies="1")
    ref = s.ply(G1, 1)["analysis"]["judgements"][0]["ref"]
    key = s.game(G1).key
    s.open_game(pgn=named(1))  # G1 is put away with its handles
    assert key not in s.held
    with pytest.raises(HandleExpired, match=f"{ref} expired"):
        s.handles.resolve(ref, key)
    again = s.ply(G1, 1)  # the id still resolves; the game is rebuilt from its record
    assert again["cached"] and again["analysis"]["judgements"][0]["ref"] != ref


def test_the_store_is_replaced_past_its_limit_and_a_search_is_charged_again(tmp_path) -> None:
    """Review C6: after the store is replaced, a repeated search is admitted against the window
    again, and with the window empty it is refused before the engine."""

    s = session(tmp_path, Limits(max_store_results=1, max_searches=3))
    s.open_game(pgn=GAME)
    p1, p2 = {"ply": 2, "at": "after"}, {"ply": 4, "at": "after"}
    s.explore(G1, p1, [], search=True)
    s.explore(G1, p1, [], search=True)  # a store hit: free
    assert s.budget.meter.used == 1 and s._store_results == 1
    s.explore(G1, p2, [], search=True)  # the store is replaced first
    assert s.budget.meter.used == 2 and s.game(G1).searched == {("e2e4", "d7d5", "e4d5", "g8f6")}
    s.explore(G1, p1, [], search=True)  # no longer a store hit: charged again
    assert s.budget.meter.used == 3
    with pytest.raises(BudgetError, match="a search"):
        s.explore(G1, p2, [], search=True)
    assert s.budget.meter.total == 3 and s.budget.meter.refused == 0  # refused before the engine


# -- handles (G4, N1, C8) --------------------------------------------------------------------------


def test_the_same_ply_10000_times_adds_no_handle(tmp_path) -> None:
    s = session(tmp_path)
    s.open_game(pgn=GAME, plies="1")
    first = s.ply(G1, 1)
    count = len(s.handles)
    for _ in range(20):  # through the ply cache
        assert s.ply(G1, 1)["analysis"]["judgements"][0]["ref"] == first["analysis"][
            "judgements"][0]["ref"]  # fmt: skip
    assert len(s.handles) == count
    loaded = s._load_or_analyse(s.game(G1).parsed, 1)  # the cache's load, kept for speed
    record = s._record(s.game(G1).parsed, 1, loaded[0])
    s._load_or_analyse = lambda parsed, ply: loaded
    s._record = lambda parsed, ply, _: copy.deepcopy(record)
    for _ in range(10_000):
        s.ply(G1, 1)
    assert len(s.handles) == count and len(s.analyses) == 1


def test_handles_and_analyses_stay_within_their_limits(tmp_path) -> None:
    session(tmp_path).open_game(pgn=GAME, plies="1-2")  # both plies cached
    probe = session(tmp_path)
    probe.open_game(pgn=GAME)
    probe.ply(G1, 1)
    per_ply = len(probe.handles)
    s = session(tmp_path, Limits(max_handles=2 * per_ply - 1, max_analyses=1))
    a, b = (s.open_game(pgn=named(i))["game"] for i in range(2))
    s.ply(a, 1)
    s.ply(b, 1)  # the second game's handles do not fit beside the first's: a is put away
    assert len(s.handles) == per_ply and list(s.held) == [s.game(b, hold=False).key]
    with pytest.raises(BudgetError, match="the game alone would pass .* handles"):
        s.ply(b, 2)  # b's own handles would pass the limit: refused, nothing else to evict
    assert len(s.handles) == per_ply and len(s.analyses) == 1
    cache = session(tmp_path, Limits(max_analyses=1))
    cache.open_game(pgn=GAME)
    cache.ply(G1, 1)
    cache.ply(G1, 2)  # a second analysis: the first is dropped from the cache
    assert len(cache.analyses) == 1
    tight = session(tmp_path / "t", Limits(max_handles=per_ply - 1))
    tight.open_game(pgn=GAME)
    with pytest.raises(BudgetError, match="the game alone would pass .* handles"):
        tight.ply(G1, 1)


def test_a_dropped_analysis_is_reloaded_or_its_handle_expires(tmp_path) -> None:
    s = session(tmp_path, Limits(max_analyses=1))
    s.open_game(pgn=GAME, plies="1-2")
    j = s.ply(G1, 1)["analysis"]["judgements"][0]["ref"]
    s.ply(G1, 2)
    game = s.game(G1)
    assert [k for k in s.analyses] != [s.handles.resolve(j).source["analysis"]]
    assert s.resolve(j, game).kind == "judgement"  # reloaded from the ply cache, no engine
    assert list(s.analyses) == [s.handles.resolve(j).source["analysis"]]
    s.ply(G1, 2)  # drops ply 1's analysis again
    key, *_ = s._key(game.parsed, 1)
    for path in s.cache.paths(key):
        path.unlink()
    with pytest.raises(HandleExpired, match=f"{j} expired"):
        s.resolve(j, game)


def test_expired_never_issued_and_foreign_handles_each_have_their_message() -> None:
    handles, other = Handles(), Handles()
    assert len(handles.token) == 24 and handles.token != other.token  # 96 bits (C10)
    ref = handles.serve("c", "k", {"kind": "analysis"}, {"claim": "c1"}, {})
    assert ref == f"c1.{handles.token}"
    assert handles.serve("c", "k", {"kind": "analysis"}, {"claim": "c1"}, {}) == ref  # N1
    assert handles.count("k") == 1
    handles.drop("k")
    with pytest.raises(HandleExpired, match="expired"):
        handles.resolve(ref)
    for unknown in (f"c2.{handles.token}", f"q1.{handles.token}", "nonsense"):
        with pytest.raises(HandleError, match="not a handle this server served") as error:
            handles.resolve(unknown)
        assert not isinstance(error.value, HandleExpired)
    with pytest.raises(HandleError, match="not served in this session"):
        handles.resolve(f"c1.{other.token}")


# -- read-only tools (G6, N2) ----------------------------------------------------------------------


def test_read_only_tools_change_no_work_state(tmp_path) -> None:
    other = session(tmp_path)
    ids = [other.open_game(pgn=named(100 + i), plies="1")["game"] for i in range(20)]
    other.close()
    s = session(tmp_path)
    for i in range(1, 16):
        s.open_game(pgn=named(i))
    a = s.open_game(pgn=named(0), plies="1")["game"]
    j = s.ply(a, 1)["analysis"]["judgements"][0]
    held = list(s.held)
    assert len(held) == 16
    for game in ids:
        document, _ = s.show_game(game)
        assert [p["ply"] for p in document["plies"]] == [1]
        assert s.commentary(game, 1)["commentaries"] == []
    assert list(s.held) == held and len(s.handles) > 0
    proposition = {"id": "p1", "kind": "judgement", "judgement": j["ref"], "refs": [j["ref"]],
                   "move": "e4", "grade": j["grade"], "label": j["label"],
                   "best_move": j["best"]["move"]["uci"]}  # fmt: skip
    answer = s.submit_commentary(a, ply=1, agent={"name": "t"}, propositions=[proposition],
                                 sentences=[{"text": "1.e4로 시작했다.", "class": "sourced",
                                             "cites": ["p1"]}])  # fmt: skip
    assert answer["accepted"], answer


# -- the server and the hosts (§5 Server, review 4.6) ----------------------------------------------


def _call(server, *calls):
    async def main():
        async with Client(server) as client:
            return [(await client.call_tool(name, args)) for name, args in calls]

    return anyio.run(main)


def test_show_game_answers_for_a_game_another_process_opened(tmp_path) -> None:
    """Also the App's refresh after a restart: the App calls show_game with the same id."""

    before = session(tmp_path)
    before.open_game(pgn=GAME, plies="1-3")
    before.close()
    after = session(tmp_path)
    [shown] = _call(build_server(after), ("show_game", {"game": G1}))
    after.close()
    assert not shown.is_error and [p["ply"] for p in shown.structured_content["plies"]] == [1, 2, 3]


def test_one_shared_process_and_one_process_per_conversation(tmp_path) -> None:
    shared = session(tmp_path / "shared")
    server = build_server(shared)
    [one] = _call(server, ("open_game", {"pgn": GAME, "plies": "1"}))
    [two] = _call(server, ("open_game", {"pgn": GAME + "\n", "plies": "2"}))  # a new connection
    shared.close()
    assert one.structured_content["game"] == two.structured_content["game"] == G1
    assert one.structured_content["budget_left"]["uncached_plies"] == 15
    assert two.structured_content["budget_left"]["uncached_plies"] == 14  # shared
    per = []
    for plies in ("3", "4"):  # a process per conversation: one data directory, two budgets
        s = session(tmp_path / "per")
        [opened] = _call(build_server(s), ("open_game", {"pgn": GAME, "plies": plies}))
        s.close()
        per.append(opened.structured_content)
    assert [p["game"] for p in per] == [G1, G1] and gid(GAME) == G1
    assert [p["budget_left"]["uncached_plies"] for p in per] == [15, 15]  # separate


# -- re-review of rev. 1 (B1–B5) -------------------------------------------------------------------


def test_reading_an_item_again_at_the_handle_limit_needs_no_room(tmp_path) -> None:
    """B1: room is made only for handles not served before."""

    probe = session(tmp_path)
    probe.open_game(pgn=GAME, plies="1")
    probe.ply(G1, 1)
    per_ply = len(probe.handles)
    s = session(tmp_path, Limits(max_handles=per_ply))
    s.open_game(pgn=GAME)
    first = s.ply(G1, 1)
    again = s.ply(G1, 1)  # at the limit, nothing new to serve
    assert _refs(again) == _refs(first) and len(s.handles) == per_ply


def _refs(answer: dict) -> list[str]:
    judgement = answer["analysis"]["judgements"][0]
    return [judgement["ref"], *(c["ref"] for c in answer["analysis"]["claims"])]


def _switching():
    """A synthetic engine whose PVs shorten after its first search: one request, another result."""

    from synthetic import IDENTITY, synthetic

    from calliope.facts.search import ScriptedEngine

    long, short = synthetic(pv_plies=4), synthetic(pv_plies=2)
    calls = []

    def answer(request):
        calls.append(request)
        return (long if len(calls) == 1 else short)(request)

    return ScriptedEngine(IDENTITY, answer)


def test_another_search_result_after_a_store_reset_gets_other_handles(tmp_path) -> None:
    """B2: a regular search's id names its request; the handle is bound to its lines too."""

    s = session(tmp_path, Limits(max_store_results=1), start=_switching)
    s.open_game(pgn=GAME)
    p1, p2 = {"ply": 2, "at": "after"}, {"ply": 4, "at": "after"}
    before = s.explore(G1, p1, [], search=True)["search"]["lines"]
    s.explore(G1, p2, [], search=True)  # replaces the store
    after = s.explore(G1, p1, [], search=True)["search"]["lines"]  # replaces it again
    assert len(before[0]["pv"]) == 4 and len(after[0]["pv"]) == 2
    assert {x["ref"] for x in before}.isdisjoint(x["ref"] for x in after)
    old, new = s.handles.resolve(before[0]["ref"]), s.handles.resolve(after[0]["ref"])
    assert old.source["search"] == new.source["search"] and old.item["pv"] != new.item["pv"]
    same = session(tmp_path / "same", Limits(max_store_results=1))
    same.open_game(pgn=GAME)
    one = same.explore(G1, p1, [], search=True)["search"]["lines"]
    same.explore(G1, p2, [], search=True)
    two = same.explore(G1, p1, [], search=True)["search"]["lines"]
    assert [x["ref"] for x in one] == [x["ref"] for x in two]  # one result, one handle


def test_repeated_searches_hold_no_nodes(tmp_path) -> None:
    """B3: search trees are not kept, so they are not counted."""

    s = session(tmp_path)
    s.open_game(pgn=GAME)
    for _ in range(50):
        s.explore(G1, {"ply": 2, "at": "after"}, [], search=True)
    game = s.game(G1)
    assert game.facts_nodes == len(game.facts.view().nodes()) == 3
    assert s.budget.meter.used == 1  # one search; the rest were store hits


def test_a_refused_search_keeps_the_store(tmp_path) -> None:
    """B4: the store is replaced only for a search that was admitted."""

    s = session(tmp_path, Limits(max_store_results=1, max_searches=1))
    s.open_game(pgn=GAME)
    a, b = {"ply": 2, "at": "after"}, {"ply": 4, "at": "after"}
    s.explore(G1, a, [], search=True)  # the store is full, the window used
    with pytest.raises(BudgetError, match="a search"):
        s.explore(G1, b, [], search=True)
    again = s.explore(G1, a, [], search=True)  # still a store hit
    assert again["search"]["lines"] and s.budget.meter.used == 1 and s.budget.meter.refused == 0


def test_an_irregular_search_is_no_store_hit(tmp_path) -> None:
    """B5: an irregular search does not enter the store, so it is admitted again."""

    import chess
    from synthetic import engine

    board = chess.Board()
    for san in ("e4", "d5"):
        board.push_san(san)
    fens = frozenset({board.fen(), board.fen().rsplit(" ", 2)[0] + " 0 1"})  # either counters
    s = session(tmp_path, Limits(max_searches=1), start=lambda: engine(irregular=fens))
    s.open_game(pgn=GAME)
    s.explore(G1, {"ply": 2, "at": "after"}, [], search=True)
    assert not s.game(G1).searched and s._store_results == 0
    with pytest.raises(BudgetError, match="a search"):  # admission, not the port
        s.explore(G1, {"ply": 2, "at": "after"}, [], search=True)
    assert s.budget.meter.refused == 0
