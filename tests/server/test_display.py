"""AG3-D D14, §3.1: `display_v1` — the moves of each proposition and of the subject in SAN,
computed with python-chess when a record is read, never stored."""

from __future__ import annotations

import chess
import pytest

from calliope.results import schema_errors
from calliope.server.commentary import displayed

START = chess.STARTING_FEN


def _record(*propositions, path=("e2e4",)) -> dict:
    return {"subject": {"path": list(path)}, "propositions": list(propositions)}


def _shown(*propositions, start=START, path=("e2e4",)) -> list[dict]:
    return displayed(_record(*propositions, path=path), start)["propositions"]


def _san(fen: str, ucis) -> list[str]:
    board, out = chess.Board(fen), []
    for uci in ucis:
        move = chess.Move.from_uci(uci)
        out.append(board.san(move))
        board.push(move)
    return out


def _line(fen: str, ucis) -> dict:
    return {"fen": fen, "moves": [{"uci": u, "san": s} for u, s in zip(ucis, _san(fen, ucis),
                                                                      strict=True)]}  # fmt: skip


def _search(fen: str) -> list[dict]:
    return [{"kind": "search_line", "address": {"fen": fen, "rank": 1}, "source": {}}]


@pytest.mark.parametrize(
    ("fen", "moves"),
    [
        ("4k3/8/8/8/8/8/8/1N3N1K w - - 0 1", ["b1d2"]),  # disambiguated: Nbd2
        ("4k3/8/8/8/8/8/8/R3K2R w KQ - 0 1", ["e1g1", "e8d7", "a1a7"]),  # O-O, then a check
        ("rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2", ["d8h4"]),  # mate
        ("8/P6k/8/8/8/8/8/K7 w - - 0 1", ["a7a8q"]),  # a promotion: a8=Q
    ],
)
def test_a_line_is_written_in_sans_at_each_position(fen: str, moves: list[str]) -> None:
    p = {"id": "p", "kind": "explored_line", "from": [], "moves": moves, "by": "agent"}
    [shown] = _shown(p, start=fen, path=())
    assert shown["display"] == {"v": "display_v1"} | _line(fen, moves)
    assert [m["san"] for m in shown["display"]["moves"]] == _san(fen, moves)


def test_each_kind_has_its_shape() -> None:
    after = chess.Board()
    after.push_uci("e2e4")
    after.push_uci("d7d5")
    fen = after.fen()  # 1.e4 d5
    path = ["e2e4", "d7d5", "e4d5"]
    judged = {"source": {"path": path}, "address": {"judgement": 0, "move": "e4d5"}}
    previous = {"source": {"path": path}, "address": {"judgement": 1, "move": "d7d5"}}
    props = [
        {"id": "j", "kind": "judgement", "move": "e4d5", "best_move": "b1c3", "judged": judged},
        {"id": "j1", "kind": "judgement", "move": "d7d5", "best_move": "e7e5", "judged": previous},
        {"id": "s", "kind": "engine_score", "move": "b1c3", "sources": _search(fen)},
        {"id": "l", "kind": "engine_line", "moves": ["b1c3", "g8f6"], "sources": _search(fen)},
        {"id": "m", "kind": "material", "from": 0, "to": 1,
         "sources": [{"kind": "explored_line", "address": {"from": path, "moves": ["d8d5"]}}]},
        {"id": "ms", "kind": "material", "from": 0, "to": 1, "sources": _search(fen)},
        {"id": "a", "kind": "attack", "position": ["e2e4", "d7d5"], "attacker": "e4"},
        {"id": "c", "kind": "check", "position": [], "checkers": []},
        {"id": "n", "kind": "legal_moves", "position": [], "count": 20},
        {"id": "r", "kind": "after_reply", "reply": "g8f6", "after_a": [*path, "g8f6"],
         "after_b": ["e2e4", "d7d5", "b1c3", "g8f6"]},
        {"id": "k", "kind": "claim", "claim": "c1.x"},
        {"id": "d", "kind": "definition", "definition": "REFUTED"},
    ]  # fmt: skip
    shown = {p["id"]: p.get("display") for p in _shown(*props, path=path)}
    one = chess.Board()
    one.push_uci("e2e4")
    assert shown["j"] == {"v": "display_v1"} | _line(fen, ["e4d5"]) | {"best": _line(fen, ["b1c3"])}
    assert shown["j1"] == {"v": "display_v1"} | _line(one.fen(), ["d7d5"]) | {
        "best": _line(one.fen(), ["e7e5"])
    }  # the previous move's judgement, at its own position
    assert shown["s"]["moves"] == _line(fen, ["b1c3"])["moves"]
    assert shown["l"]["moves"] == _line(fen, ["b1c3", "g8f6"])["moves"]
    exd5 = chess.Board(fen)
    exd5.push_uci("e4d5")
    assert shown["m"] == {"v": "display_v1"} | _line(exd5.fen(), ["d8d5"])
    assert shown["ms"] is None  # a search line: the record keeps no moves (AG3a notes)
    assert shown["a"] == {"v": "display_v1", "fen": fen, "moves": []}
    assert shown["c"] == shown["n"] == {"v": "display_v1", "fen": START, "moves": []}
    assert shown["r"] == {"v": "display_v1", "fen": fen, "moves": [],
                          "a": _line(fen, ["e4d5", "g8f6"]), "b": _line(fen, ["b1c3", "g8f6"])}  # fmt: skip
    assert shown["k"] is None and shown["d"] is None
    for value in shown.values():  # `v` on the outer object only; `moves` always an array
        if value is not None:
            assert isinstance(value["moves"], list)
            assert all("v" not in value[k] for k in ("best", "a", "b") if k in value)


def test_legal_moves_are_choices_not_a_line() -> None:
    """AG3-D re-review B6: `a3` and `a4` are alternatives at one position, never a line."""

    legal = sorted(m.uci() for m in chess.Board().legal_moves)
    [shown] = _shown({"id": "n", "kind": "legal_moves", "position": [], "moves": legal})
    display = shown["display"]
    assert display["moves"] == [] and len(display["choices"]) == 20
    sans = {c["uci"]: c["san"] for c in display["choices"]}
    assert sans["a2a3"] == "a3" and sans["a2a4"] == "a4"
    assert all(sans[u] == chess.Board().san(chess.Move.from_uci(u)) for u in legal)
    check = "rnbqk1nr/pppp1ppp/8/4p3/1b1PP3/8/PPP2PPP/RNBQKBNR w KQkq - 1 3"  # 3.Bb4+
    answers = sorted(m.uci() for m in chess.Board(check).legal_moves)
    [shown] = _shown({"id": "n", "kind": "legal_moves", "position": [], "moves": answers},
                     start=check, path=())  # fmt: skip
    assert [c["san"] for c in shown["display"]["choices"]] == [
        chess.Board(check).san(chess.Move.from_uci(u)) for u in answers
    ]


def test_the_subject_of_a_played_a_judged_and_an_off_game_move() -> None:
    for path in (["e2e4", "d7d5"], ["e2e4", "e7e5"], ["d2d4", "d7d5", "g1f3"], ["e2e4"]):
        board = chess.Board()
        for uci in path[:-1]:
            board.push_uci(uci)
        record = displayed(_record(path=path), START)
        assert record["display"] == {"v": "display_v1", "subject": _line(board.fen(), path[-1:])}


def test_a_damaged_proposition_gets_no_display_and_the_others_keep_theirs() -> None:
    good = {"id": "a", "kind": "check", "position": ["e2e4"], "checkers": []}
    bad = [
        {"id": "x", "kind": "explored_line", "from": [], "moves": ["e2e5"]},  # illegal
        {"id": "y", "kind": "engine_line", "moves": ["b1c3"], "sources": [{"address": {}}]},
        {"id": "z", "kind": "attack", "position": ["e2e4", "e2e4"]},  # does not replay
        {"id": "w", "kind": "judgement", "move": "g1f3", "best_move": "b1c3",
         "judged": {"source": {"path": ["e2e4"]}, "address": {"judgement": 0}}},  # off its path
        {"id": "v", "kind": "legal_moves", "position": [], "moves": ["a2a3", "zz"]},
        {"id": "u", "kind": "after_reply", "after_a": ["e2e4"], "after_b": None},
    ]  # fmt: skip
    shown = _shown(good, *bad)
    assert "display" in shown[0]
    assert all("display" not in p for p in shown[1:])
    assert shown[1:] == bad  # left as they were
    assert "display" not in displayed(_record(path=["e2e5"]), START)


def test_a_record_is_not_changed() -> None:
    record = _record({"id": "a", "kind": "check", "position": [], "checkers": []})
    before = repr(record)
    displayed(record, START)
    assert repr(record) == before


def test_the_display_validates() -> None:
    p = {"id": "n", "kind": "legal_moves", "position": [], "moves": ["a2a3", "a2a4"]}
    record = displayed(_record(p), START)
    ai = {"format": "ai_commentary_v1", "id": "i", "level": "SOURCE_VERIFIED",
          "propositions": record["propositions"], "display": record["display"],
          "sentences": [{"text": "t", "class": "sourced", "cites": ["n"]}]}  # fmt: skip
    assert schema_errors(ai, "AiCommentary") == []
    broken = ai | {"display": {"v": "display_v1", "subject": {"fen": START}}}
    assert schema_errors(broken, "AiCommentary")
