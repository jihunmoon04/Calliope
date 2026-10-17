"""AG4-D §5 (ids, records, resolution, the agent's game, `pgn_tags`, id stability): a game id is
derived from the game and resolves from its record in every process, or is refused; a record is
created once and never replaced; the game worked on is `from_record` of its record."""

from __future__ import annotations

import json
import multiprocessing

import chess
import chess.pgn
import pytest
from agent_helpers import G1, GAME, PROMOTION, gid, session

from calliope.agent import AgentError, GameError, from_record, pgn_tags
from calliope.agent.games import MAX_BYTES, Records, damage, encode, record_of
from calliope.facts import EngineProfile
from calliope.server import HEADERS, game_input, game_key, grading_for, normalized_ply, parse_game

KEY = game_key(parse_game(GAME).game)
RECORD = record_of(parse_game(GAME).game)


def _records(tmp_path) -> Records:
    return Records(tmp_path / "agent" / "games")


# -- ids (B1) --------------------------------------------------------------------------------------


def test_the_same_game_has_the_same_id_in_two_processes(tmp_path) -> None:
    one, two = session(tmp_path), session(tmp_path)
    first = one.open_game(pgn=GAME)
    assert first["game"] == G1 == f"g-{KEY[:16]}" and first["game_key"] == KEY
    assert two.open_game(pgn=GAME)["game"] == G1
    assert two.ply(G1, 1)["cached"] is False  # resolved and worked on in the second process too
    again = one.open_game(pgn=GAME)
    assert again["game"] == G1 and _records(tmp_path).keys("") == [KEY]
    other = one.open_game(pgn='[White "Kim"]\n\n' + GAME)
    assert other["game"] != G1 and len(_records(tmp_path).keys("")) == 2


def test_opening_again_reuses_the_held_game(tmp_path) -> None:
    s = session(tmp_path)
    s.open_game(pgn=GAME)
    held = s.game(G1)
    s.facts(G1, {"ply": 2, "at": "after"})
    s.open_game(pgn=GAME + "\n")
    assert s.game(G1) is held and held.facts is not None and len(s.held) == 1


def _clash(tmp_path, key: str = KEY) -> str:
    """A record by hand whose name shares the key's 16 digits (its content does not matter)."""

    other = key[:16] + ("0" if key[16] != "0" else "1") * 48
    folder = _records(tmp_path).root
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{other}.json").write_text("{}")
    return other


def test_a_clash_makes_the_short_id_ambiguous_and_the_full_id_resolves(tmp_path) -> None:
    s = session(tmp_path)
    assert s.open_game(pgn=GAME)["game"] == G1
    assert s.ply(G1, 1)  # the short id resolves
    other = _clash(tmp_path)
    with pytest.raises(GameError, match="ambiguous") as error:
        s.ply(G1, 1)  # held in memory, still refused (B1, C9)
    assert f"g-{KEY}" in str(error.value) and f"g-{other}" in str(error.value)
    assert s.ply(f"g-{KEY}", 1)["cached"]
    assert s.open_game(pgn=GAME)["game"] == f"g-{KEY}"  # the full form on a clash
    fresh = session(tmp_path)
    with pytest.raises(GameError, match="ambiguous"):
        fresh.ply(G1, 1)
    assert fresh.ply(f"g-{KEY}", 1)["cached"]  # stability (C9): the full id always resolves


@pytest.mark.parametrize("text", ["g1", "g-123", "g-" + "A" * 16, "", None, 7])
def test_a_malformed_id_is_refused(tmp_path, text) -> None:
    with pytest.raises(GameError, match="no game"):
        session(tmp_path).ply(text, 1)


def test_an_unknown_id_is_refused(tmp_path) -> None:
    s = session(tmp_path)
    for text in (G1, f"g-{KEY}"):
        with pytest.raises(GameError, match=f"no game g-{KEY[:16]}.* open_game"):
            s.ply(text, 1)


# -- records (B2, C5) ------------------------------------------------------------------------------


def _open(data, text, barrier) -> None:
    s = session(data)
    barrier.wait()
    s.records.create(record_of(parse_game(text).game))
    s.open_game(pgn=text)
    s.close()


def test_two_processes_with_two_texts_of_one_key_make_one_record(tmp_path) -> None:
    spaced = "1.e4   d5 {a comment} (1...e5) 2. exd5 Nf6 3. Nf3 Nxd5\n4. Be2 e6 5. O-O Be7 *"
    assert game_key(parse_game(spaced).game) == KEY
    context = multiprocessing.get_context("fork")
    barrier = context.Barrier(2)
    workers = [context.Process(target=_open, args=(tmp_path, text, barrier))
               for text in (GAME, spaced)]  # fmt: skip
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(60)
    assert [w.exitcode for w in workers] == [0, 0]
    folder = _records(tmp_path).root
    assert sorted(p.name for p in folder.iterdir()) == [f"{KEY}.json"]  # no temporaries
    assert (folder / f"{KEY}.json").read_bytes() == encode(RECORD)
    assert damage(encode(RECORD), KEY) is None


def test_an_existing_record_is_never_replaced(tmp_path) -> None:
    session(tmp_path).open_game(pgn=GAME)
    path = _records(tmp_path).path(KEY)
    before = path.stat()
    session(tmp_path).open_game(pgn="1. e4 d5 {again} 2. exd5 Nf6 3. Nf3 Nxd5 4. Be2 e6 5. O-O Be7")
    after = path.stat()
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns)


def _damaged() -> dict[str, bytes]:
    r = RECORD
    ep = "4k3/8/8/8/4P3/8/8/4K3 b - e3 0 1"  # an en passant square no pawn can take
    return {
        "too large": encode(r) + b" " * MAX_BYTES,
        "not JSON": b"{",
        "not an object": b"[]",
        "a key missing": encode({k: v for k, v in r.items() if k != "headers"}),
        "a key more": encode(r | {"extra": 1}),
        "another version": encode(r | {"v": "agent_game_v0"}),
        "moves not a list": encode(r | {"moves": "e2e4"}),
        "a move not a string": encode(r | {"moves": [1]}),
        "headers not an object": encode(r | {"headers": []}),
        "start_fen unreadable": encode(r | {"start_fen": "nonsense"}),
        "start_fen not normal": encode(r | {"start_fen": ep}),
        "an illegal move": encode(r | {"moves": ["e2e5"]}),
        "a move not in UCI": encode(r | {"moves": ["e4"]}),
        "a header name": encode(r | {"headers": {"event": "x"}}),
        "a rating as a string": encode(r | {"headers": {"white_rating": "1500"}}),
        "a negative rating": encode(r | {"headers": {"white_rating": -1}}),
        "a rating as a boolean": encode(r | {"headers": {"white_rating": True}}),
        "an unknown value": encode(r | {"headers": {"white": "?"}}),
        "an empty value": encode(r | {"headers": {"date": ""}}),
        "a number as a name": encode(r | {"headers": {"white": 7}}),
        "another game's content": encode(r | {"moves": ["d2d4"]}),
        "another key": encode(r | {"game_key": "0" * 64}),
        "not canonical": json.dumps(r, indent=1).encode(),
    }


@pytest.mark.parametrize("rule", list(_damaged()))
def test_a_damaged_record_is_refused_and_left_as_it_is(tmp_path, rule) -> None:
    raw = _damaged()[rule]
    path = _records(tmp_path).path(KEY)
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    assert damage(raw, KEY) is not None
    s = session(tmp_path)
    for text in (G1, f"g-{KEY}"):
        with pytest.raises(GameError, match="is damaged"):
            s.ply(text, 1)
    with pytest.raises(GameError, match="is damaged"):
        s.open_game(pgn=GAME)
    assert path.read_bytes() == raw and not s.held


def test_too_large_inputs_and_records_are_refused(tmp_path) -> None:
    s = session(tmp_path)
    with pytest.raises(AgentError, match=f"more than {MAX_BYTES} bytes"):
        s.open_game(pgn="{" + "가" * 90_000 + "} 1. e4 *")  # 90,000 characters, 270,000 bytes
    big = parse_game('[White "' + "x" * (MAX_BYTES // 2) + '"]\n\n1. e4 *').game
    record = record_of(big)
    with pytest.raises(GameError, match="over"):
        _records(tmp_path).create(record | {"headers": {"white": "x" * MAX_BYTES}})
    assert not _records(tmp_path).keys("")


# -- resolution (C2) -------------------------------------------------------------------------------


def test_a_removed_or_damaged_record_keeps_serving_where_it_was_loaded(tmp_path) -> None:
    one = session(tmp_path)
    one.open_game(pgn=GAME, plies="1")
    path = _records(tmp_path).path(KEY)
    path.unlink()
    assert one.ply(G1, 1)["cached"]  # the holding process: its validated game
    with pytest.raises(GameError, match="no game"):
        session(tmp_path).ply(G1, 1)  # another process refuses, never serves another game
    path.write_bytes(encode(RECORD | {"moves": ["d2d4"]}))
    assert one.ply(f"g-{KEY}", 1, view="full")["san"] == "e4"
    with pytest.raises(GameError, match="is damaged"):
        session(tmp_path).ply(f"g-{KEY}", 1)


# -- the agent's game (C7, N3, N4) -----------------------------------------------------------------

STANDARD = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
CORPUS = {
    "no FEN tag": "1. e4 e5 2. Nf3 *",
    "normalized ratings": '[WhiteElo "01500"]\n[BlackElo "?"]\n\n1. e4 *',
    "chess.com": '[Site "Chess.com"]\n[WhiteElo "1500"]\n[BlackElo "1600"]\n'
    '[TimeControl "180+2"]\n\n1. e4 e5 *',
    "lichess": '[Site "https://lichess.org/x"]\n[WhiteElo "1500"]\n[BlackElo "1600"]\n'
    '[TimeControl "300+3"]\n\n1. d4 *',
    "unknown time control on chess.com": '[Site "Chess.com"]\n[WhiteElo "1500"]\n'
    '[BlackElo "1600"]\n[TimeControl "?"]\n\n1. e4 *',
    "unknown headers": '[White "?"]\n[Black "?"]\n[Date "????.??.??"]\n[Result "*"]\n\n1. e4 *',
    "comments and variations": "1. e4 {good} (1. d4 d5) e5 $1 2. Nf3 (2. f4) Nc6 *",
    "the standard start as a FEN tag": f'[SetUp "1"]\n[FEN "{STANDARD}"]\n\n1. e4 *',
    "a custom FEN with spaces": '[SetUp "1"]\n[FEN "  8/P6k/8/8/8/8/8/K7 w - - 0 1  "]\n\n'
    "1. a8=Q Kg6 *",
    "a takeable en passant square": '[SetUp "1"]\n[FEN "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1"]\n\n'
    "1. exd6 Kd7 *",
    "an untakeable en passant square": '[SetUp "1"]\n[FEN "4k3/8/8/8/4P3/8/8/4K3 b - e3 0 1"]\n\n'
    "1... Kd7 2. Kd2 *",
}  # fmt: skip


@pytest.mark.parametrize("case", list(CORPUS))
def test_the_agents_game_is_built_from_its_record(tmp_path, case) -> None:
    text = CORPUS[case]
    read = parse_game(text)
    opener = session(tmp_path)
    opened = opener.open_game(pgn=text)
    game = opener.game(opened["game"]).parsed
    record = json.loads(_records(tmp_path).path(opened["game_key"]).read_bytes())
    assert session(tmp_path).game(opened["game"]).parsed == game  # another process, one value
    assert from_record(record) == game
    assert (game.game, game.sans, game.uci, game.spec) == (read.game, read.sans, read.uci,
                                                           read.spec)  # fmt: skip
    assert game_key(game.game) == game_key(read.game) == opened["game_key"]
    assert game.warnings == tuple(w for w in read.warnings if w.startswith("graded"))
    profile = EngineProfile()
    for ply in range(1, len(game.sans) + 1):
        ours, theirs = normalized_ply(game, ply, profile), normalized_ply(read, ply, profile)
        if case == "an untakeable en passant square":  # N4: the square is not in start_fen
            assert ours.root.fen != theirs.root.fen and ours.root.fen == game.game.start_fen
            assert ours.moves == theirs.moves
        else:
            assert ours == theirs


def test_a_second_process_reads_the_analysis_from_the_ply_cache(tmp_path) -> None:
    session(tmp_path).open_game(pgn=PROMOTION, plies="1")
    second = session(tmp_path)
    answer = second.ply(gid(PROMOTION), 1)
    assert answer["cached"] and second.budget.meter.used == 0  # no engine search


def test_pgn_tags_is_the_inverse_of_the_headers() -> None:
    headers = {"white": "Kim", "black": "Lee", "white_rating": 1500, "black_rating": 0,
               "time_control": "180+2", "site": "Chess.com", "date": "2026.10.15",
               "result": "1-0"}  # fmt: skip
    assert set(headers) == set(HEADERS.values())
    tags = pgn_tags(headers)
    assert tags["WhiteElo"] == "1500" and tags["TimeControl"] == "180+2"
    game = chess.pgn.Game.without_tag_roster()
    game.headers.update(tags)
    assert dict(game_input(game, ()).headers) == headers
    original = {"WhiteElo": "01500", "BlackElo": "0", "TimeControl": "180+2", "Site": "Chess.com"}
    read = parse_game("".join(f'[{k} "{v}"]\n' for k, v in original.items()) + "\n1. e4 *")
    assert grading_for(pgn_tags(read.game.headers)) == grading_for(original) == read.spec


def test_a_record_starts_where_python_chess_starts(tmp_path) -> None:
    record = record_of(parse_game(CORPUS["no FEN tag"]).game)
    assert record["start_fen"] == chess.STARTING_FEN and from_record(record).root.fen is None
