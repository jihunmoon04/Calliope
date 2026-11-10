"""The change log, 2026-11-10: whose piece and change-as-standing. Tools v11 name each piece's owner
in the ledger (`captured`, `end`); harness rev. 10's frame check v2 holds a cited change written with
"물질 차이"/"물질은", and reads a sentence whose counts are all the proposition's number."""

from __future__ import annotations

from test_af_harness import LINE_PROP, MATERIAL, RECORDS, _call, _ledger

from calliope.agent.definitions import TOOLS_VERSION
from calliope.agent.lines import LEDGER_NOTE, ledger
from tools.rx import frames
from tools.rx import run as rx_run
from tools.rx.harness import FRAMES, PER_MOMENT, VERSIONS

V2 = frames.FRAMES_V2

# 184800218248-57: 29...Rxd6 takes White's d6 pawn; four rows gave the pawn to Black
FEN_57 = "3r4/k5p1/p2P1p2/4p2p/Rb6/8/5PPP/3R2K1 b - - 2 29"
ROOK = {"color": "black", "origin": "h8", "type_now": "rook", "square": "d6"}
PAWN = {"color": "white", "origin": "e2"}
RXD6 = [{"ply": 1, "material_balance_white": -1, "move": {
    "san": "Rxd6", "mover": "black", "piece": ROOK, "piece_type": "rook", "from_square": "d8",
    "to_square": "d6", "castling": None, "gives_check": False, "gives_mate": False,
    "events": [{"piece": PAWN, "piece_type": "pawn", "square": "d6", "en_passant": False}]}}]  # fmt: skip


def test_the_ledger_names_whose_piece_was_taken_and_moved() -> None:
    book = ledger(RXD6, FEN_57)
    assert book["captured"] == {"by_white": [], "by_black": ["White's pawn d6 (1)"]}
    assert book["end"]["gone"] == ["White pawn d6"]
    assert book["end"]["moved_pieces"] == ["Black rook d6"]
    assert book["plies"][0]["captured"]["owner"] == "white"
    assert "named with its owner" in LEDGER_NOTE
    assert TOOLS_VERSION == "agent_tools_v11"
    assert rx_run.TOOLS_VERSIONS["v11"] == TOOLS_VERSION
    assert rx_run.SERVER_ROOTS["v10"] == "agent-tools-v10"  # v10 runs from its tag
    assert rx_run.server_root("v11") is None  # v11 from this repository


def test_revision_10_is_revision_9_with_the_frame_check_v2() -> None:
    assert VERSIONS[10] == VERSIONS[9] and 10 in PER_MOMENT
    assert FRAMES[9] == "harness_frames_v1" and FRAMES[10] == V2


def test_v2_holds_a_change_written_as_material_difference() -> None:
    text = "이 라인의 백 물질 차이는 9입니다."
    v1 = frames.check(_call(text), RECORDS)
    assert v1["held"] == [] and v1["ambiguous"]  # v1: counted only
    v2 = frames.check(_call(text), RECORDS, V2)
    assert [h["rule"] for h in v2["held"]] == ["F1"] and v2["version"] == V2
    reply = v2["held"][0]["reply"]
    assert "흑 쪽이 1점" in reply and "'물질 차이'는 앞선 정도로 읽힌다" in reply
    assert "백이 9점을 얻는다" in reply
    assert v2["ambiguous"] == v1["ambiguous"]  # still counted, so rows stay comparable


def test_v2_reads_several_counts_that_are_all_the_propositions() -> None:
    """e118b76e #5 and 801be227 #3: "N점을 잃고 … 물질은 -N" — v1 left them uncheckable."""

    lost = dict(MATERIAL, side="black", balance=-9)
    text = "이 라인에서 흑은 9점을 잃고, 라인 끝 물질은 흑 -9입니다."
    v1 = frames.check(_call(text, (lost, LINE_PROP)), RECORDS)
    assert v1["held"] == [] and v1["uncheckable"] == [] and v1["ambiguous"]
    v2 = frames.check(_call(text, (lost, LINE_PROP)), RECORDS, V2)
    assert "F1" in [h["rule"] for h in v2["held"]]
    assert "흑이 9점을 잃는다" in next(h for h in v2["held"] if h["rule"] == "F1")["reply"]


def test_v2_never_holds_a_right_standing_or_other_counts() -> None:
    level = {"x21.t": ("explored_line", {"ledger": _ledger(0, [0, 9])})}
    assert frames.check(_call("이 라인의 백 물질 차이는 9입니다."), level, V2)["held"] == []
    mixed = frames.check(_call("백은 9점을 얻었지만 물질은 흑이 1점 앞선다."), RECORDS, V2)
    assert mixed["held"] == []  # 9 and 1: not one number
    assert all("not the cited" in u["why"] for u in mixed["uncheckable"])
    plain = frames.check(_call("백은 이 수순에서 9점을 얻는다."), RECORDS, V2)
    assert plain["held"] == [] and plain["ambiguous"] == []
    denied = frames.check(_call("이 라인의 물질 차이는 9가 아니다."), RECORDS, V2)
    assert denied["held"] == []
