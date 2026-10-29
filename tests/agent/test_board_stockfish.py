"""AG8-D §9 with Stockfish 19 (gated): `board` at the trial's fixed moments — the lost defences of
26...Re8, 27...Nxf7 and 31...Qf6, none at 28...Qe6 (the queen still defends from e6), the sides at
9...b5 and 38...Rxh5, the same reply at 9...b5 and 26...Re8, the material claim's `proves`, and
every served proposition verifying as given."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from calliope.agent import Limits, Session

STOCKFISH = os.environ.get("CALLIOPE_STOCKFISH_PATH")
HERE = Path(__file__).resolve().parent
RAPID = (HERE.parent / "reasoning" / "fixtures" / "chesscom_rapid_813_801.pgn").read_text()
OPERA = (HERE / "fixtures" / "opera_game.pgn").read_text()
WEAK = (HERE / "fixtures" / "weak_engines_1.pgn").read_text()
pytestmark = pytest.mark.skipif(not STOCKFISH or not os.path.exists(STOCKFISH),
                                reason="needs Stockfish 19")  # fmt: skip


@pytest.fixture
def s(tmp_path):
    from calliope.facts.search import StockfishEngine

    s = Session(tmp_path, lambda: StockfishEngine.start(STOCKFISH),
                Limits(max_searches=400, max_uncached_plies=64))  # fmt: skip
    yield s
    s.close()


def _digest(s, pgn: str, ply: int) -> tuple[str, dict]:
    game = s.open_game(pgn=pgn, plies=f"{ply}-{ply}")["game"]
    return game, s.ply(game, ply)


def _lost(board: dict) -> list[tuple]:
    return [tuple((p["kind"], p.get("defender") or p.get("attacker"), p.get("defended")
                   or p.get("target")) for p in c["propositions"][:2])  # ST-D §3: since after
            for c in board["changes"] if c["kind"] == "lost_defence"]  # fmt: skip


def _all_verify(s, game: str, ply: int, digest: dict) -> None:
    propositions = [{"id": "j", "kind": "judgement", "judgement": digest["judgement"]}]
    items = list(digest["board"]["changes"])
    if "propositions" in digest["board"].get("same_reply", {}):
        items.append(digest["board"]["same_reply"])
    if "played_material" in digest["board"]:  # BL-D §4
        items.append(digest["board"]["played_material"])
    for i, item in enumerate(items):
        propositions += [p | {"id": f"i{i}_{k}"} for k, p in enumerate(item["propositions"])]
    answer = s.submit_commentary(game, ply=ply, agent={"name": "t"}, propositions=propositions,
                                 sentences=[{"text": "판정을 받은 수다.", "class": "sourced",
                                             "cites": ["j"]}])  # fmt: skip
    assert answer["accepted"], answer
    assert "refused" not in digest["board"]


def test_26_re8_and_27_nxf7_lose_their_defences(s) -> None:
    game, re8 = _digest(s, RAPID, 52)
    assert (("defence", "f8", "f7"), ("attack", "d5", "f7")) in _lost(re8["board"])
    assert re8["board"]["changes"][0]["kind"] == "lost_defence"  # a blunder: the cost first
    same = re8["board"]["same_reply"]
    assert same["propositions"][0]["moves"] == ["Bd7", "Bxf7+"]  # no second search: ...Nxf7,
    assert same["propositions"][1]["move"] == "Nxf7"  # not the played line's ...Kxf7
    _all_verify(s, game, 52, re8)
    game, nxf7 = _digest(s, RAPID, 54)
    assert (("defence", "d6", "e8"), ("attack", "e5", "e8")) in _lost(nxf7["board"])
    _all_verify(s, game, 54, nxf7)


def test_31_qf6_blocks_a_defence_and_28_qe6_loses_none(s) -> None:
    game, qf6 = _digest(s, WEAK, 62)
    assert (("defence", "f8", "f5"), ("attack", "e4", "f5")) in _lost(qf6["board"])
    _all_verify(s, game, 62, qf6)
    game, qe6 = _digest(s, WEAK, 56)
    assert not [x for x in _lost(qe6["board"]) if x[0][2] in ("f5", "d6")]  # framing §7.1
    _all_verify(s, game, 56, qe6)


def test_38_rxh5_is_a_weakness_of_blacks(s) -> None:
    game, rxh5 = _digest(s, WEAK, 76)
    weak = [c for c in rxh5["board"]["changes"] if c["kind"] == "weakness"]
    assert any(c["owner"] == "black" and c["propositions"][0].get("piece") == "h5" for c in weak)
    _all_verify(s, game, 76, rxh5)


def test_9_b5_threatens_whites_bishop_and_the_same_reply_shows_why(s) -> None:
    game, b5 = _digest(s, OPERA, 18)
    changes = b5["board"]["changes"]
    assert changes and all(c["kind"] == "threat" and c["owner"] == "white"
                           and c["good_for"] == "black" for c in changes)  # fmt: skip
    same = b5["board"]["same_reply"]
    assert same["propositions"][0]["moves"][:2] == ["a6", "Nb5"]
    assert same["propositions"][1]["move"] == "axb5"
    loss = next(c for c in b5["claims"] if c["template"] == "material_loss_v2")
    assert loss["part"] == "consequence" and "흑 비숍(b4)" in loss["proves"]
    assert "백 폰(c3)" in loss["proves"] and loss["proves"].startswith("[흑(둔 쪽)의 손실]")
    _all_verify(s, game, 18, b5)


def test_13_rxd7_gains_for_white(s) -> None:
    game, rxd7 = _digest(s, OPERA, 25)
    gain = next(c for c in rxd7["claims"] if c["template"] == "material_gain_v3")
    assert gain["proves"].startswith("[백(둔 쪽)의 이득]") and "흑 룩(d7)" in gain["proves"]
    assert any(
        c["kind"] == "threat" and c["propositions"][0]["kind"] == "pattern"
        for c in rxd7["board"]["changes"]
    )  # the double attack of the rook on d7
    _all_verify(s, game, 25, rxd7)
