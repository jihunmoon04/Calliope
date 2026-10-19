"""PW-D (issue #122): numbered lines (§2), moves given numbered (§2, review B1), plain words (§3)
and the tokens they allow (I5); on the synthetic engine and by hand-made texts."""

from __future__ import annotations

import chess
import pytest
from agent_helpers import G1, GAME, session

from calliope.agent import AgentError
from calliope.agent.digest import PV_SHORT, numbered_line
from calliope.agent.messages_ko import korean
from calliope.agent.propositions import Refused, Verifier
from calliope.agent.remarks import (
    OPPONENT_FIRST,
    PROVES_CAP,
    board_tokens,
    change_proves,
    en_passant,
    held_proves,
    link_remark,
    same_reply_proves,
    weakness_proves,
    with_opponent_first,
)
from calliope.agent.sentences import MoveNumberError, read_move

START = chess.STARTING_FEN
BLACK_15 = "r3k2r/pp1n1ppp/1q2p3/3pPP2/3P2P1/2N2Q1P/PPP5/R3K2R b KQkq - 0 15"
EP_38 = "5r1k/4p1b1/3p3q/3r3P/pR1PNpP1/P2Q1P2/5B2/4R1K1 b - g3 0 38"  # 38...fxg3 e.p. is legal


@pytest.fixture
def s(tmp_path):
    s = session(tmp_path)
    s.open_game(pgn=GAME)
    yield s
    s.close()


# -- §2 numbered lines ----------------------------------------------------------------------------


def test_a_line_is_numbered_as_in_pgn() -> None:
    assert numbered_line(START, ["e4", "e5", "Nf3"]) == "1.e4 e5 2.Nf3"
    assert (
        numbered_line(BLACK_15, ["Qxb2", "O-O", "O-O-O", "Qd3"]) == "15...Qxb2 16.O-O O-O-O 17.Qd3"
    )
    assert numbered_line(BLACK_15, ["Qxb2"]) == "15...Qxb2"  # a single move, as the line's first
    promoting = "8/1P6/8/8/8/8/k7/7K w - - 0 40"
    assert (
        numbered_line(promoting, ["b8=Q+", "Ka1", "Qb1#"]) == "40.b8=Q+ Ka1 41.Qb1#"
    )  # marks kept
    assert numbered_line("f" * 60, ["e4", "e5"]) == "e4 e5"  # a record made by hand: no position


def test_the_bounds_short_pv_keeps_moves_with_their_numbers() -> None:
    for fen, sans, kept in ((START, ["e4", "e5", "Nf3", "Nc6", "Bb5"], "1.e4 e5 2.Nf3 Nc6"),
                            (BLACK_15, ["Qxb2", "O-O", "O-O-O", "Qd3", "Qb6"],
                             "15...Qxb2 16.O-O O-O-O 17.Qd3")):  # fmt: skip
        assert " ".join(numbered_line(fen, sans).split()[:PV_SHORT]) == kept  # digest step 2


def test_an_en_passant_move_is_the_token_its_line_shows() -> None:
    board, ucis = chess.Board(EP_38), ["f4g3", "e4g3"]
    sans = []
    for uci in ucis:
        sans.append(board.san(chess.Move.from_uci(uci)))
        board.push_uci(uci)
    (passing,) = en_passant(EP_38, {"best": ucis})
    assert passing["move"] == numbered_line(EP_38, sans).split()[0] == "38...fxg3"


def test_the_digest_numbers_its_lines_and_best_move(s) -> None:
    d, full = s.ply(G1, 3), s.ply(G1, 3, view="full")
    for name in ("played", "best"):
        line = d["lines"][name]
        if line is None:
            continue
        tokens = line["pv"].split()
        assert tokens[0].startswith("2.") and line["move"] == tokens[0]
        board = chess.Board(full["fen_before"])  # every token names the move at its position
        for token in tokens:
            board.push(read_move(board, token))  # a numbered token is checked against the board
        assert len(tokens) == len(full["analysis"]["judgements"][0][name]["pv"][:8])
    best = d["evaluation"]["best_move"]
    assert best is None or best.startswith("2.")


def test_the_overview_shows_best_move_only_when_another_was_best(s, monkeypatch) -> None:
    s.analyze_game(G1, wait_seconds=60)
    game, summary_of = s.game(G1), s._summary

    def summary(g, ply):  # ply 4's best move is the move played (the synthetic engine's never is)
        out = summary_of(g, ply)
        return out | {"best_move": out["san"]} if ply == 4 and out else out

    monkeypatch.setattr(s, "_summary", summary)
    overview = s.game_overview(G1)
    shown = [line for line in overview["lines"] if "best_move" in line]
    assert 0 < len(shown) < len(overview["lines"]), [(x["move"], x.get("best_move"))
                                                       for x in overview["lines"]]  # fmt: skip
    for line in overview["lines"]:
        summary = s._summary(game, line["ply"])
        if summary["best_move"] and summary["best_move"] != summary["san"]:
            number = line["move"].split(".")[0]
            assert line["best_move"] == f"{line['move'][: line['move'].rindex('.') + 1]}" \
                f"{summary['best_move']}" and line["best_move"].startswith(number)  # fmt: skip
        else:
            assert "best_move" not in line  # review B3: compared bare, so a best move is no line


def test_the_same_reply_text_numbers_each_move_from_its_position() -> None:
    text = same_reply_proves("15.f5", "15...Qxd4", "15.O-O-O", "16.Rxd4", "+8.56", "-4.86")
    assert "엔진 라인의 15...Qxd4를 최선수 15.O-O-O 뒤에 두면, 엔진의 최선은 16.Rxd4" in text
    three = numbered_line(BLACK_15, ["Qxb2", "O-O", "O-O-O"])  # `same` of three moves (review N5)
    assert three == "15...Qxb2 16.O-O O-O-O"


def test_the_digest_same_reply_is_numbered(s) -> None:
    same = s.ply(G1, 2)["board"]["same_reply"]
    line, top, _ = same["propositions"]
    assert line["moves"][0] == "a5" and not line["moves"][1][0].isdigit()  # propositions: SAN
    reply = numbered_line(chess.Board().fen(), ["e4", "a5", line["moves"][1]]).split()[-1]
    assert f"엔진 라인의 {reply}를 최선수 1...a5 뒤에 두면" in same["proves"]
    assert reply.startswith("2.") and f"엔진의 최선은 2...{top['move']}" in same["proves"]


# -- §2 moves given to Calliope (review B1) -------------------------------------------------------


def test_a_numbered_move_is_read_with_its_number_and_side() -> None:
    board = chess.Board()
    assert read_move(board, "1.e4") == read_move(board, "e4") == read_move(board, "e2e4")
    assert read_move(board, "1. e4").uci() == "e2e4"
    for wrong in ("2.e4", "1...e5", "...e5"):
        with pytest.raises(MoveNumberError, match="move 1, white to move"):
            read_move(board, wrong)
    board.push_san("e4")
    assert read_move(board, "1...e5") == read_move(board, "...e5") == read_move(board, "e5")
    with pytest.raises(MoveNumberError, match="move 1, black to move"):
        read_move(board, "1.e5")
    with pytest.raises(ValueError):
        read_move(board, "1...e4")  # numbered right, not legal: refused as today
    problem = "'16.Ne2' is numbered for another position: move 15, white to move"
    assert (
        korean(problem) == "'16.Ne2'의 수 번호가 그 국면과 다릅니다: 그 국면은 15수, 백 차례입니다"
    )


def test_tools_take_numbered_moves(s) -> None:
    plain = s.judge_move(G1, {"ply": 3, "at": "before"}, "Nc3")
    numbered = s.judge_move(G1, {"ply": 3, "at": "before"}, "2.Nc3")
    assert numbered["move"] == plain["move"] and numbered["grade"] == plain["grade"]
    with pytest.raises(AgentError, match="numbered for another position"):
        s.judge_move(G1, {"ply": 3, "at": "before"}, "3.Nc3")
    x = s.explore(G1, {"ply": 2, "at": "after"}, ["2.Nc3", "dxe4", "3.Nxe4"])
    assert x["ref"]
    with pytest.raises(AgentError, match="numbered for another position"):
        s.explore(G1, {"ply": 2, "at": "after"}, ["2.Nc3", "3...dxe4"])


def test_propositions_take_numbered_moves(s) -> None:
    full = s.ply(G1, 3, view="full")
    j = full["analysis"]["judgements"][0]
    verifier = Verifier(s, s.game(G1))

    def verify(p: dict) -> dict:
        return verifier.verify({"id": "p", **p})[0]

    good = {"kind": "judgement", "judgement": j["ref"], "move": "2.exd5", "grade": j["grade"],
            "label": j["label"], "best_move": "2." + j["best"]["move"]["san"]}  # fmt: skip
    assert verify(good)["move"] == "e4d5"  # stored as today
    with pytest.raises(Refused) as error:
        verify(good | {"move": "3.exd5"})
    assert error.value.field == "move" and "numbered for another position" in error.value.problem
    best = j["best"]
    sans = [m["san"] for m in best["pv"][:2]]
    numbered = numbered_line(full["fen_before"], sans).split()
    record = verify({"kind": "engine_line", "line": best["ref"], "moves": numbered})
    assert record == verify({"kind": "engine_line", "line": best["ref"], "moves": sans})
    score = {"kind": "engine_score", "line": best["ref"], "move": numbered[0],
             "score": best["score"]}  # fmt: skip
    assert verify(score)["score"] == best["score"]


# -- §3 plain words, I5 ---------------------------------------------------------------------------


NAMES = {"g4": "백 퀸(g4)", "d7": "흑 나이트(d7)"}


def test_an_exposed_piece_is_said_from_its_owners_side_without_exchange() -> None:
    threat = change_proves("threat", "black", "19...Kh8",
                           {"kind": "exposed", "piece": "g4", "gain": 8}, NAMES)  # fmt: skip
    assert (
        "19...Kh8 뒤 백 퀸(g4)은 잡힐 수 있다: 그 칸의 잡고 되잡기만 셈하면 백이 8점을 잃는다"
        in threat
    )
    weak = weakness_proves("black", "19...Kh8", "흑 나이트(d7)", 3, "백 퀸(g4)", True)
    assert (
        "흑 나이트(d7)은 잡힐 수 있다: 백 퀸(g4)이 공격하고, 그 칸의 잡고 되잡기만 셈하면 흑이 3점을 잃는다"
        in weak
    )
    assert weak.endswith("(수 전에는 체크 중이었다)")
    plain = weakness_proves("white", "1.Ra5", "백 룩(a5)", 5, "흑 폰(b6)", False)
    assert plain.endswith("(수 전에는 아니었다)") and "백이 5점을 잃는다" in plain
    one = held_proves(
        "black", "26...Rf8", ("rook", "rook"), "f8", "f8", 5, ("백 비숍(c5)",) * 2, True
    )
    assert "f8에서 수 전에 이미 백 비숍(c5)이 공격했고, 수 뒤에도 공격한다" in one
    for text in (threat, weak, plain, one):
        assert "교환" not in text and "잡는 쪽" not in text and len(text) <= PROVES_CAP


def test_best_stops_reply_says_one_squares_count() -> None:
    from calliope.agent.remarks import Tokens, _best_stops_reply

    before = "rn2kb1r/pp3ppp/2p1pn2/2P5/1q6/2NPB3/PP2Q1PP/R3KB1R w KQkq - 3 13"
    board = chess.Board(before)
    board.push_uci("d3d4")
    move = {"uci": "d3d4", "fen": before}
    reply = {"uci": "f8c5", "fen": board.fen()}
    for kind, wanted in (("defends", "13...Bxc5로 c5를 잡아도 그 칸의 잡고 되잡기만 셈하면 이득이 없다"),
                         ("covers", "c5의 백 폰(c5)을 그 칸의 잡고 되잡기만 셈하면 잃는다"),
                         ("rescues", "(c5 칸에서 잡고 되잡기만 셈한 기준)")):  # fmt: skip
        finding = {"type": "ReplyFinding", "kind": kind, "best": move, "reply": reply,
                   "piece": {"color": "white", "piece": "pawn", "square": "c5"},
                   "square": {"square": "c5"}}  # fmt: skip
        text = _best_stops_reply({"findings": [finding]}, "white", {}, Tokens())
        assert wanted in text and "교환" not in text, (kind, text)


def _old_threat(name: str, gain: int) -> str:  # `board_remarks_ko_v3`, for the token comparison
    return f"… 뒤 {name}은 교환으로 잃을 수 있다 (정적 교환으로 잡는 쪽이 {gain}점 이득; 수 전에는 아니었다)"


def test_the_new_texts_allow_the_same_tokens() -> None:
    fen, uci = "4k3/8/8/8/6Q1/8/8/4K3 b - - 0 19", "e8d8"
    new = change_proves("threat", "black", "19...Kd8", {"kind": "exposed", "piece": "g4", "gain": 8},
                        NAMES)  # fmt: skip
    old = _old_threat("백 퀸(g4)", 8)
    a, b = board_tokens(new, uci, fen), board_tokens(old, uci, fen)
    assert (a.squares, a.integers) == (b.squares, b.integers) == ({"g4"}, {8})
    old_held = (
        "[흑의 약점: 수 전에도 수 뒤에도 흑의 기물이 위험하다] 34...Qb3 전에도 뒤에도 흑 퀸은 교환으로 "
        "잃을 수 있다: 수 전 e3에서도 수 뒤 b3에서도 백 룩(f3)이 공격한다 (수 뒤 정적 교환으로 잡는 쪽이 9점 이득)"
    )
    new_held = held_proves("black", "34...Qb3", ("queen", "queen"), "e3", "b3", 9,
                           ("백 룩(f3)", "백 룩(f3)"), True)  # fmt: skip
    a, b = board_tokens(new_held, uci, fen), board_tokens(old_held, uci, fen)
    assert (a.squares, a.integers) == (b.squares, b.integers) == ({"e3", "b3", "f3"}, {9})
    numbered = same_reply_proves("15.f5", "15...Qxd4 16.Rxd4 Qxb2", "15.O-O-O", "17.f6", "+8.56",
                                 "-4.86")  # fmt: skip
    bare = same_reply_proves("15.f5", "Qxd4 Rxd4 Qxb2", "O-O-O", "f6", "+8.56", "-4.86")
    a, b = board_tokens(numbered, uci, fen), board_tokens(bare, uci, fen)
    assert (a.squares, a.integers) == (b.squares, b.integers)  # numbers add no token


def test_a_threat_at_the_length_limit_keeps_its_squares_and_counts() -> None:
    names = {"h6": "백 퀸(h6)"}
    text = change_proves("threat", "black", "27...Nxf7", {"kind": "exposed", "piece": "h6",
                                                           "gain": 9}, names)  # fmt: skip
    leads = {
        "link": "associated_with",
        "to_template": "mate_in_one_allowed_v1",
        "did": "configuration",
    }
    full = with_opponent_first(text + link_remark(leads))
    assert full.endswith(OPPONENT_FIRST) and len(full) <= PROVES_CAP
    tokens = board_tokens(full, "d6f7", "r1b1r1k1/pp3B1p/3n2pQ/4R3/6P1/P4N1P/1q4PK/3R4 b - - 0 27")
    assert tokens.squares == {"h6"} and tokens.integers == {9}
