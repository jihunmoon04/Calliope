"""AG3-D §5: the viewer's AI commentary part under node, against commentaries accepted by an MCP
session on the synthetic engine and read through `calliope.server.commentary` (`display_v1`)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import chess
import pytest

ROOT = Path(__file__).resolve().parents[2]
for sub in ("tests/agent", "tests/server", "tests/facts/search"):
    if str(ROOT / sub) not in sys.path:
        sys.path.insert(0, str(ROOT / sub))

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def _key(board: chess.Board) -> str:
    return "".join((p.symbol() if (p := board.piece_at(chess.square(f, r))) else ".")
                   for r in range(7, -1, -1) for f in range(8))  # fmt: skip


def _after(*sans: str, fen: str = chess.STARTING_FEN) -> chess.Board:
    board = chess.Board(fen)
    for san in sans:
        board.push_san(san)
    return board


def _submit(s, propositions, sentences, **subject) -> str:
    answer = s.submit_commentary("g1", agent={"name": "t", "model": "m"},
                                 propositions=propositions, sentences=sentences, **subject)  # fmt: skip
    assert answer["accepted"], answer
    return answer["id"]


def _judged(s, position: dict, move: str) -> str:
    j = s.judge_move("g1", position, move)["analysis"]["judgements"][0]
    p = {"id": "p1", "kind": "judgement", "judgement": j["ref"], "move": move, "grade": j["grade"],
         "label": j["label"], "best_move": j["best"]["move"]["uci"]}  # fmt: skip
    return _submit(s, [p], [{"text": "판정이다.", "class": "sourced", "cites": ["p1"]}],
                   position=position, move=move)  # fmt: skip


@pytest.fixture(scope="module")
def cases(tmp_path_factory):
    from agent_helpers import GAME, session

    from calliope.server import CommentaryStore, game_key, parse_game
    from calliope.server.commentary import listing, with_commentary

    data = tmp_path_factory.mktemp("ai")
    s = session(data)
    try:
        s.open_game(pgn=GAME)
        j = s.ply("g1", 3)["analysis"]["judgements"][0]
        best = j["best"]
        x = s.explore("g1", {"ply": 4, "at": "after"}, ["Nc3", "Nxd5", "Nxd5", "Qxd5"])
        a = {"from_root": ["e4", "d5", "exd5", "Nf6"]}
        b = {"from_root": ["e4", "d5", "Nc3", "Nf6"]}
        legal = sorted(m.uci() for m in chess.Board().legal_moves)
        props = [
            {"id": "p1", "kind": "judgement", "judgement": j["ref"], "move": "exd5",
             "grade": j["grade"], "label": j["label"], "best_move": best["move"]["san"]},
            {"id": "p2", "kind": "engine_line", "line": best["ref"],
             "moves": [m["uci"] for m in best["pv"]][:2]},
            {"id": "p3", "kind": "explored_line", "line": x["ref"],
             "moves": ["Nc3", "Nxd5", "Nxd5", "Qxd5"]},
            {"id": "p4", "kind": "legal_moves", "position": {"from_root": []}, "moves": legal},
            {"id": "p5", "kind": "attack", "position": {"ply": 2, "at": "after"},
             "attacker": "e4", "target": "d5"},
            {"id": "p7", "kind": "pin", "position": {"from_root": ["e4", "e5", "d4", "Bb4+", "c3"]},
             "pinned": "c3", "pinner": "b4"},
            {"id": "p8", "kind": "material", "line": best["ref"], "from": 0, "to": 2,
             "side": "white", "balance": 0},
            {"id": "p6", "kind": "after_reply", "reply": "Nf6", "after_a": a, "after_b": b,
             "proposition_a": {"kind": "attack", "position": a, "attacker": "f6", "target": "d5"},
             "proposition_b": {"kind": "attack", "position": b, "attacker": "f6", "target": "e4"}},
        ]  # fmt: skip
        sentences = [
            {"text": "Calliope의 판정이다.", "class": "sourced", "cites": ["p1", "p2"]},
            {"text": "에이전트가 둔 수순으로 보면 흑이 되찾는다.", "class": "interpretation",
             "cites": ["p3"]},
        ]  # fmt: skip
        older = _submit(s, props, sentences, ply=3)
        newer = _submit(
            s, props[:1], [{"text": "판정이다.", "class": "sourced", "cites": ["p1"]}], ply=3
        )
        at_two = _judged(s, {"ply": 2, "at": "after"}, "Nc3")
        at_start = _judged(s, {"from_root": []}, "d4")
        off_game = _judged(s, {"from_root": ["d4", "d5"]}, "Nf3")
    finally:
        s.close()
    parsed = parse_game(GAME)
    store = CommentaryStore(data / "commentary")
    key = game_key(parsed.game)
    records = store.for_game(key)
    first = next(r for r in records if r["id"] == older)
    copy = {k: v for k, v in first.items() if k not in ("format", "id")}
    stale_id = store.write(copy | {"bundle": {"tree": "0" * 64, "graph": "0" * 64}})
    records = store.for_game(key)
    document = {"game": {"start_fen": parsed.game.start_fen},
                "plies": [{"ply": 3, "bundle": first["bundle"]}]}  # fmt: skip
    played = list(parsed.uci)
    answer = listing(records, played, document, parsed.game.start_fen)
    combined = with_commentary(document, records, played)
    game = {"start_fen": parsed.game.start_fen,
            "moves": [{"uci": u, "san": n} for u, n in zip(parsed.uci, parsed.sans, strict=True)]}  # fmt: skip
    hostile = {
        "id": '"><b>x', "agent": {"name": "<img src=x onerror=alert(1)>", "model": "<m>"},
        "propositions": [{"id": "<p>", "kind": "definition", "definition": "<d>"}],
        "sentences": [{"text": "<script>alert(1)</script>", "class": "sourced", "cites": ["<p>"]}],
    }  # fmt: skip
    unreadable = [
        None, {"id": "a", "propositions": [], "sentences": []},
        {"id": "a", "propositions": [{"id": "p"}], "sentences": [
            {"text": "t", "class": "sourced", "cites": ["p"]}]},
        {"id": "a", "propositions": [], "sentences": [{"text": "t", "class": "verified", "cites": []}]},
        {"propositions": [], "sentences": [{"text": "t", "class": "sourced", "cites": []}]},
    ]  # fmt: skip
    no_display = [
        {"id": "q", "kind": "engine_line", "moves": ["e2e4", "e7e5"]},
        {"id": "r", "kind": "judgement", "move": "e2e4", "grade": "best", "best_move": "d2d4"},
    ]  # fmt: skip
    path = data / "cases.json"
    path.write_text(json.dumps({"game": game, "listing": answer, "doc": {**combined, "game": game},
                                "hostile": hostile, "unreadable": unreadable,
                                "noDisplay": no_display}))  # fmt: skip
    run = subprocess.run([NODE, str(ROOT / "tests/viewer/check_ai.js"), str(ROOT / "viewer/index.html"),
                          str(path)], capture_output=True, text=True, check=False)  # fmt: skip
    assert run.returncode == 0, run.stderr
    ids = {"older": older, "newer": newer, "stale": stale_id, "at_two": at_two,
           "at_start": at_start, "off_game": off_game}  # fmt: skip
    return json.loads(run.stdout), ids, answer


def test_each_commentary_is_placed(cases) -> None:
    """D4 and D8: the newest current one is the ply's; older, stale and judged ones apart; a judged
    move on the ply whose played path it starts from, the start position included; off the game,
    at game level and on no ply (AG3-D review B2)."""

    out, ids, _ = cases
    plies = out["listing"]["plies"]
    assert plies["3"]["main"] == ids["newer"]
    assert sorted(plies["3"]["others"]) == sorted([[ids["older"], "이전 해설"],
                                                   [ids["stale"], "다른 분석 기준"]])  # fmt: skip
    assert plies["2"] == {
        "main": None,
        "others": [[ids["at_two"], "두지 않은 수 2.Nc3에 대한 해설"]],
    }
    assert plies["0"] == {
        "main": None,
        "others": [[ids["at_start"], "두지 않은 수 1.d4에 대한 해설"]],
    }
    assert out["listing"]["offGame"] == [[ids["off_game"], "2.Nf3에 대한 해설 (본선 밖)"]]
    everywhere = [
        i for slot in plies.values() for i in [slot["main"], *[o[0] for o in slot["others"]]]
    ]
    assert ids["off_game"] not in everywhere
    assert out["listing"]["any"] and not out["empty"]["any"]
    # a combined document (file mode, D2): the newest current one, nothing apart
    assert out["doc"]["plies"] == {"3": {"main": ids["newer"], "others": []}}
    assert out["doc"]["offGame"] == []


def test_propositions_are_shown_from_their_verified_fields(cases) -> None:
    out, ids, _ = cases
    line = lambda pid: out["lines"][f"{ids['older']}/{pid}"]
    assert line("p1").startswith("판정: 2.exd5 — ") and "최선수 2." in line("p1")
    assert line("p2").startswith("엔진 수순: 2.")
    assert line("p3").startswith("에이전트 수순: 3.Nc3 Nxd5 4.Nxd5 Qxd5")
    assert '<span class="tag agent">에이전트 탐색</span>' in line("p3")
    assert line("p4").startswith("합법수 20개: ") and "a3, a4" in line("p4")
    assert line("p5") == "공격: e4 → d5"
    assert line("p6") == (
        "응수 비교: 같은 응수 Nf6 뒤 — A: 공격: f6 → d5 / B: 공격: f6 → e4"
        ' <span class="tag agent">에이전트 탐색</span>'
    )  # AG-D AM2 (d)
    assert line("p7") == "핀: b4 → c3 (고정된 기물 c3)"  # the pinner, then the pinned (AG3a B1)
    assert line("p8").startswith("기물 득실: 수순의 0–2 구간, 백 ")
    for text, frames in out["noDisplay"]:
        assert text.endswith('<span class="hint">(표시할 수 없음)</span>') and frames == 0


def test_previews_follow_the_display(cases) -> None:
    """D7: a line steps through its moves; each legal move is its own frame from the same
    position (AG3-D review B6); a position marks its squares."""

    out, ids, answer = cases
    frames = lambda pid: out["frames"][f"{ids['older']}/{pid}"]
    legal = frames("p4")
    assert len(legal) == 20
    for f in legal:  # one move from the start, never two of them
        (arrow,) = f["arrows"]
        move = chess.Move.from_uci(arrow[0] + arrow[1])
        board = chess.Board()
        board.push(move)
        assert f["board"] == _key(board)
    explored = frames("p3")
    sans = ["Nc3", "Nxd5", "Nxd5", "Qxd5"]
    assert [f["board"] for f in explored] == [
        _key(_after("e4", "d5", "exd5", "Nf6", *sans[: k + 1])) for k in range(4)
    ]
    assert "<b>3.Nc3</b>" in explored[0]["caption"]
    (attack,) = frames("p5")
    assert attack["board"] == _key(_after("e4", "d5"))
    assert attack["rings"] == ["e4", "d5"] and attack["arrows"] == [["e4", "d5"]]
    after = frames("p6")
    assert [f["board"] for f in after] == [_key(_after("e4", "d5", "exd5")),
                                           _key(_after("e4", "d5", "exd5", "Nf6")),
                                           _key(_after("e4", "d5", "Nc3")),
                                           _key(_after("e4", "d5", "Nc3", "Nf6"))]  # fmt: skip
    (pin,) = frames("p7")
    assert pin["board"] == _key(_after("e4", "e5", "d4", "Bb4+", "c3"))
    assert pin["rings"] == ["c3", "b4"] and pin["arrows"] == [["b4", "c3"]]
    material = frames("p8")  # over a search line: its moves from the line's start (AG-D AM7)
    record = next(c for c in answer["plies"]["3"] if c["id"] == ids["older"])
    p8 = next(p for p in record["propositions"] if p["id"] == "p8")
    board, boards = chess.Board(p8["display"]["fen"]), []
    for uci in p8["moves"]:
        board.push_uci(uci)
        boards.append(_key(board))
    assert len(p8["moves"]) >= 2 and [f["board"] for f in material] == boards
    judgement = frames("p1")
    assert judgement[0]["board"] == _key(_after("e4", "d5", "exd5"))


def test_sentences_and_tags(cases) -> None:
    """D4, D5: the level and the note; sourced with chips; interpretation and the agent's line
    marked; the propositions list the sentences that cite them."""

    out, ids, _ = cases
    html = out["html"][ids["older"]]
    assert '<span class="tag level"' in html and "출처 확인" in html
    assert '<li class="sent sourced">' in html and '<li class="sent interpretation">' in html
    assert (
        '<span class="tag interp">해석</span><span class="tag agent">에이전트 탐색</span>' in html
    )
    assert (
        '<span class="chip" data-p="p1">p1</span><span class="chip" data-p="p2">p2</span>' in html
    )
    assert '<span class="hint">문장 1</span>' in html and '<span class="hint">문장 2</span>' in html
    assert "확인된 명제 8개" in html and "검증" not in html
    assert '<span class="who">t (m)</span>' in html
    judged = out["htmlJudged"][ids["off_game"]]
    assert '<div class="ai-subject" data-k="0">판에 보기: 2.Nf3</div>' in judged
    assert out["note"].startswith("명제는 Calliope 데이터로 확인했습니다.")


def test_everything_from_a_record_is_escaped(cases) -> None:
    """D12: sentences, the agent's name and model, ids and a tag are text, never HTML."""

    out, _, _ = cases
    html = out["hostile"]
    for raw in ("<script>", "<img", "<m>", "<p>", "<d>", '"><b>', "<i>"):
        assert raw not in html, raw
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "&lt;img src=x" in html
    assert out["readable"] == [False] * 5


def test_server_mode_reads_the_listing_and_survives_errors(cases) -> None:
    """D1: the listing route by a relative URL; a 409 or a network error is a message only."""

    out, _, _ = cases
    assert out["fetch"]["urls"] == [f"api/games/{'a' * 64}/commentary"]
    plies, error = out["fetch"]["ok"]
    assert plies == out["listing"]["plies"] and error == ""
    assert out["fetch"]["conflict"] == [
        None,
        "해설을 읽지 못했습니다: the job's game cannot be read",
    ]
    assert out["fetch"]["thrown"] == [None, "해설을 읽지 못했습니다: offline"]


def test_the_listing_carries_the_display(cases) -> None:
    _, ids, answer = cases
    entry = next(e for e in answer["judged"] if e["id"] == ids["off_game"])
    subject = entry["display"]["subject"]
    assert subject["fen"] == _after("d4", "d5").fen()
    assert subject["moves"] == [{"uci": "g1f3", "san": "Nf3"}]
