"""AG8-D over the synthetic engine: `board` in the digest, its sides and `proves`, the same reply
and its provenance, what a sentence states (S7, §6.2), S8, the notes and the Korean refusals."""

from __future__ import annotations

import threading

import chess
import pytest
from agent_helpers import G1, GAME, session

from calliope.agent.budget import BudgetError
from calliope.agent.digest import score_text


@pytest.fixture
def s(tmp_path):
    s = session(tmp_path)
    s.open_game(pgn=GAME, plies="1-4")
    yield s
    s.close()


def _cite(digest: dict) -> tuple[list[dict], dict[str, list[str]]]:
    """The judgement and every board proposition, each with an id; ids by item ("c0", "r")."""

    propositions = [{"id": "j", "kind": "judgement", "judgement": digest["judgement"]}]
    ids: dict[str, list[str]] = {}
    board = digest["board"]
    items = [(f"c{i}", c) for i, c in enumerate(board["changes"])]
    if "propositions" in board.get("same_reply", {}):
        items.append(("r", board["same_reply"]))
    for name, item in items:
        ids[name] = []
        for k, proposition in enumerate(item["propositions"]):
            pid = f"{name}_{k}"
            propositions.append(proposition | {"id": pid})
            ids[name].append(pid)
    return propositions, ids


def _submit(s, ply: int, sentences: list[dict], digest: dict | None = None) -> dict:
    digest = digest or s.ply(G1, ply)
    propositions, _ = _cite(digest)
    return s.submit_commentary(G1, ply=ply, agent={"name": "t"}, propositions=propositions,
                               sentences=sentences)  # fmt: skip


def _same_reply_text(digest: dict) -> str:
    """A sentence that writes a token of each of the same reply's three propositions."""

    line, top, played = digest["board"]["same_reply"]["propositions"]
    board = chess.Board(digest["fen_before"])
    written = []
    for san in line["moves"]:
        dots = "." if board.turn == chess.WHITE else "..."
        written.append(f"{board.fullmove_number}{dots}{san}")
        board.push_san(san)
    return (f"{' '.join(written)} 뒤 엔진은 {score_text(top['score'])}을 주고, 실제 수는 "
            f"{score_text(played['score'])}이다.")  # fmt: skip


# -- the field ------------------------------------------------------------------------------------


def test_board_names_the_mover_and_whose_each_change_is(s) -> None:
    black = s.ply(G1, 2)["board"]  # 1...d5: Black's threats on White's pawn
    assert black["v"] == "board_v1" and black["mover"] == "black"
    assert [c["kind"] for c in black["changes"]] == ["threat", "threat"]
    assert all(c["owner"] == "white" and c["good_for"] == "black" and c["part"] == "reason"
               for c in black["changes"])  # fmt: skip
    assert all(c["proves"].startswith("[흑(둔 쪽)의 위협 — 백의 기물이 걸린 것이고 흑이 잃는 것이 아니다]")
               for c in black["changes"])  # fmt: skip
    white = s.ply(G1, 3)["board"]  # 2.exd5: White's own pawn can be won
    assert [(c["kind"], c["owner"], c["good_for"]) for c in white["changes"]] == [
        ("weakness", "white", "black")
    ]
    assert white["changes"][0]["proves"].startswith("[백(둔 쪽)의 약점")
    assert all(len(c["proves"]) <= 240 for c in black["changes"] + white["changes"])


def test_a_judged_move_reads_the_same_with_its_path(s) -> None:
    judged = s.judge_move(G1, {"ply": 3, "at": "before"}, "Nc3")["board"]
    assert judged["mover"] == "white" and judged["changes"]
    assert all(p["position"] == {"from_root": ["e2e4", "d7d5", "b1c3"]}
               for c in judged["changes"] for p in c["propositions"])  # fmt: skip


def test_the_same_reply_is_calliopes_line_and_its_scores(s) -> None:
    same = s.ply(G1, 2)["board"]["same_reply"]
    line, top, played = same["propositions"]
    assert [p["kind"] for p in same["propositions"]] == ["explored_line", "engine_score",
                                                          "engine_score"]  # fmt: skip
    assert line["moves"][0] == "a5" and played["move"] == "d5"  # the best move, then the reply
    assert (
        same["proves"].startswith("[같은 수순 비교]") and score_text(top["score"]) in same["proves"]
    )
    assert s.resolve(line["line"], s.game(G1)).address["by"] == "calliope"


def test_every_served_proposition_verifies_as_given(s) -> None:
    for ply in (2, 3, 4):
        answer = _submit(
            s, ply, [{"text": "판정을 받은 수다.", "class": "sourced", "cites": ["j"]}]
        )
        assert answer["accepted"], answer


def test_a_busy_engine_leaves_only_the_same_reply_out(s) -> None:
    held, release = threading.Event(), threading.Event()

    def hold():
        with s.engine_lock:
            held.set()
            release.wait(10)

    worker = threading.Thread(target=hold)
    worker.start()
    try:
        assert held.wait(10)
        board = s.ply(G1, 4)["board"]  # analysed by open_game; its same reply not yet searched
        assert board["same_reply"] == {"not_computed": "engine_busy"} and board["changes"]
    finally:
        release.set()
        worker.join()
    assert "propositions" in s.ply(G1, 4)["board"]["same_reply"]  # a later read computes it


def test_a_refused_search_leaves_only_the_same_reply_out(s, monkeypatch) -> None:
    def refuse(*args, **kwargs):
        raise BudgetError("no search left", 42)

    monkeypatch.setattr(s, "compare", refuse)
    board = s.ply(G1, 2)["board"]
    assert board["same_reply"] == {"not_computed": "budget", "retry_after_seconds": 42}
    assert board["changes"]


# -- the provenance of the comparison line (review N1) -------------------------------------------


def test_calliopes_line_is_not_the_agents(s) -> None:
    digest = s.ply(G1, 2)
    propositions, ids = _cite(digest)
    own = s.explore(G1, {"ply": 2, "at": "after"}, ["Nc3"])
    propositions.append({"id": "x", "kind": "explored_line", "line": own["ref"], "moves": ["Nc3"]})
    sentences = [
        {"text": _same_reply_text(digest), "class": "sourced", "cites": ids["r"]},
        {"text": "2.Nc3을 두어 본다.", "class": "sourced", "cites": ["x"]},
        {"text": _same_reply_text(digest) + " 2.Nc3도 있다.", "class": "sourced",
         "cites": [*ids["r"], "x"]},
    ]  # fmt: skip
    answer = s.submit_commentary(G1, ply=2, agent={"name": "t"}, propositions=propositions,
                                 sentences=sentences)  # fmt: skip
    assert answer["accepted"], answer
    stored = s.commentary(G1, 2)["commentaries"][0]
    lines = {p["id"]: p for p in stored["propositions"] if p["kind"] == "explored_line"}
    assert lines[ids["r"][0]]["by"] == "calliope" and lines["x"]["by"] == "agent"
    assert [x["by_agent"] for x in stored["sentences"]] == [False, True, True]


# -- what a sentence states (S7, §6.2) -----------------------------------------------------------


def test_states_lists_cited_ids_and_a_stated_proposition_writes_its_token(s) -> None:
    digest = s.ply(G1, 2)
    _, ids = _cite(digest)
    attack = ids["c0"][0]
    outside = _submit(s, 2, [{"text": "1...d5가 폰을 겨눈다.", "class": "sourced", "cites": ["j"],
                              "states": [attack]}], digest)  # fmt: skip
    assert [v["rule"] for v in outside["violations"]] == ["S7"]
    silent = _submit(s, 2, [{"text": "폰이 폰을 겨눈다.", "class": "sourced", "cites": [attack],
                             "states": [attack]}], digest)  # fmt: skip
    assert [(v["rule"], v["proposition"]) for v in silent["violations"]] == [("S7", attack)]
    said = _submit(s, 2, [{"text": "d5의 폰이 e4를 겨눈다.", "class": "sourced",
                           "cites": ["j", attack], "states": [attack]}], digest)  # fmt: skip
    assert said["accepted"]
    stored = s.commentary(G1, 2)["commentaries"][0]["sentences"][0]
    assert stored["states"] == [attack] and stored["states_items"] == [0]


def test_s7_checks_only_propositions_that_allow_a_token(s) -> None:
    """Review B2: a definition and a legal_moves given by its moves allow no token; a count
    allows the count."""

    digest = s.ply(G1, 2)
    propositions, _ = _cite(digest)
    board = chess.Board(digest["fen_after"])
    extra = [
        {"id": "d", "kind": "definition", "definition": "sentence.sourced"},
        {"id": "m", "kind": "legal_moves", "position": {"ply": 2, "at": "after"},
         "moves": [m.uci() for m in board.legal_moves]},
        {"id": "n", "kind": "legal_moves", "position": {"ply": 2, "at": "after"},
         "count": board.legal_moves.count()},
    ]  # fmt: skip

    def submit(text, cites, states):
        return s.submit_commentary(G1, ply=2, agent={"name": "t"}, propositions=propositions + extra,
                                   sentences=[{"text": text, "class": "sourced", "cites": cites,
                                               "states": states}])  # fmt: skip

    assert submit("정의대로 쓴다.", ["j", "d", "m"], ["d", "m"])["accepted"]
    count = board.legal_moves.count()
    assert submit(f"백은 {count}가지 수를 둘 수 있다.", ["j", "n"], ["n"])["accepted"]
    refused = submit("백은 여러 수를 둘 수 있다.", ["j", "n"], ["n"])
    assert [(v["rule"], v["proposition"]) for v in refused["violations"]] == [("S7", "n")]


def test_an_item_is_stated_when_all_its_propositions_are(s) -> None:
    """Review B1: the same reply's line alone is a line, not the item; all three state it."""

    digest = s.ply(G1, 2)
    _, ids = _cite(digest)
    index = len(digest["board"]["changes"])  # the same reply follows the changes
    line = _submit(s, 2, [{"text": _same_reply_text(digest).split(" 뒤")[0] + "를 두어 본다.",
                           "class": "sourced", "cites": ["j", ids["r"][0]],
                           "states": [ids["r"][0]]}], digest)  # fmt: skip
    assert line["accepted"] and [n["rule"] for n in line["notes"]] == ["N-reason"]
    assert s.commentary(G1, 2)["commentaries"][0]["sentences"][0]["states_items"] == []
    whole = _submit(s, 2, [{"text": _same_reply_text(digest), "class": "sourced",
                            "cites": ["j", *ids["r"]], "states": ids["r"]}], digest)  # fmt: skip
    assert whole["accepted"] and "notes" not in whole
    stored = next(c for c in s.commentary(G1, 2)["commentaries"] if c["id"] == whole["id"])
    assert stored["sentences"][0]["states_items"] == [index]


def test_a_proposition_belongs_to_an_item_by_content(s) -> None:
    digest = s.ply(G1, 2)
    attack = digest["board"]["changes"][0]["propositions"][0]
    same, renamed = dict(attack, id="mine"), dict(attack, id="other", position={"from_root":
                                                                            ["e2e4", "d7d5"]})  # fmt: skip
    for proposition in (same, renamed):  # copied with another id; written with its path
        answer = s.submit_commentary(G1, ply=2, agent={"name": "t"}, propositions=[
            {"id": "j", "kind": "judgement", "judgement": digest["judgement"]}, proposition],
            sentences=[{"text": "d5가 e4를 겨눈다.", "class": "sourced",
                        "cites": [proposition["id"]], "states": [proposition["id"]]}])  # fmt: skip
        stored = next(c for c in s.commentary(G1, 2)["commentaries"] if c["id"] == answer["id"])
        assert stored["sentences"][0]["states_items"] == [0] and "notes" not in answer


# -- S8, the notes, Korean refusals ---------------------------------------------------------------


def test_s8_a_korean_commentary_is_written_in_korean(s) -> None:
    answer = _submit(s, 2, [{"text": "1...d5 attacks the pawn.", "class": "sourced",
                             "cites": ["j"]}])  # fmt: skip
    assert [v["rule"] for v in answer["violations"]] == ["S8"]
    assert answer["violations"][0]["problem"] == "해설 문장은 한국어로 씁니다"


def test_the_notes_tell_and_never_refuse(s) -> None:
    digest = s.ply(G1, 2)
    _, ids = _cite(digest)
    told = _submit(s, 2, [{"text": "1...d5는 판정을 받은 수다.", "class": "sourced", "cites": ["j"]},
                          {"text": "중앙을 다투는 수로 보인다.", "class": "interpretation",
                           "cites": ["j"]}], digest)  # fmt: skip
    assert told["accepted"]
    assert [(n["rule"], n.get("sentence")) for n in told["notes"]] == [("N-reason", None),
                                                                        ("N-reading", 1)]  # fmt: skip
    attack = ids["c0"][0]
    quiet = _submit(s, 2, [{"text": "1...d5는 판정을 받은 수다.", "class": "sourced", "cites": ["j"]},
                           {"text": "d5의 폰으로 e4를 겨누며 중앙을 다투는 수로 보인다.",
                            "class": "interpretation", "cites": ["j", attack],
                            "states": [attack]}], digest)  # fmt: skip
    assert quiet["accepted"] and "notes" not in quiet


def test_a_subject_whose_digest_was_never_served_gets_no_n_reason(s) -> None:
    record = s.ply(G1, 3, view="full")
    answer = s.submit_commentary(G1, ply=3, agent={"name": "t"}, propositions=[
        {"id": "j", "kind": "judgement", "judgement": record["analysis"]["judgements"][0]["ref"]}],
        sentences=[{"text": "2.exd5는 판정을 받은 수다.", "class": "sourced", "cites": ["j"]}])  # fmt: skip
    assert answer["accepted"] and "notes" not in answer


def test_a_korean_refusal_keeps_the_english_text(s) -> None:
    answer = _submit(s, 2, [{"text": "엔진은 +7.77을 준다.", "class": "sourced", "cites": ["j"]}])
    violation = next(v for v in answer["violations"] if v.get("token") == "+7.77")
    assert violation["problem"] == "평가치 '+7.77'는 인용한 엔진 평가가 아닙니다"
    assert violation["problem_en"] == "the score '+7.77' is not a cited engine score"
    stored_check = _submit(s, 2, [{"text": "1...d5다.", "class": "sourced", "cites": ["j"]}])
    assert stored_check["accepted"]
    assert s.commentary(G1, 2)["commentaries"][0]["check"] == "commentary_check_v2"


# -- the claims' `proves` (AG8-D §4) ----------------------------------------------------------------


def _material(template: str, victim: str, passed: bool = True) -> dict:
    fen = "rn2kb1r/pp2qppp/2p2n2/4p1B1/2B1P3/1QN5/PPP2PPP/R3K2R b KQkq - 1 9"
    return {
        "template": template,
        "findings": [{"type": "MaterialFinding", "amount": {"points": 2},
                      "event": {"ply": 2, "victim": {"square": "b5", "piece": "pawn",
                                                     "color": victim},
                                "capturer": {"square": "c3", "piece": "knight",
                                             "color": "white" if victim == "black" else "black"}}}],
        "effective_scopes": [{"quantifier": "specific_line",
                              "at": {"kind": "line", "fen": fen,
                                     "moves": [{"uci": "b7b5"}, {"uci": "c3b5"}]}}],
        "checks": [{"kind": "attributed", "passed": passed}],
    }  # fmt: skip


def test_a_material_claim_proves_whose_gain_or_loss() -> None:
    from calliope.agent.remarks import claim_proves

    loss = claim_proves(_material("material_loss_v2", "black"), "black")
    assert loss.startswith(
        "[흑(둔 쪽)의 손실] 엔진 라인에서 10.Nxb5로 백 나이트(c3)이 흑 폰(b5)을 잡는다"
    )
    assert "이 라인에서만" in loss and "순손실 2점" in loss
    gain = claim_proves(_material("material_gain_v3", "black"), "white")
    assert gain.startswith("[백(둔 쪽)의 이득]") and "순이득 2점" in gain  # the review's 13.Rxd7
    line = claim_proves(_material("material_gain_v3", "black", passed=False), "white")
    assert line.endswith("(이 수의 성과가 아니라 라인의 사실)")
    assert claim_proves({"template": "fork_v2", "findings": []}, "white") is None


def test_a_mate_claim_proves_who_mates() -> None:
    from calliope.agent.remarks import claim_proves

    mate = {"template": "mate_allowed_v1",
            "findings": [{"type": "MateFinding", "moves": 4, "mating_move": {
                "uci": "f3g5", "fen": "r1b1r2Q/pp3k2/3n2p1/4R3/6P1/P4N1P/1q4PK/3R4 w - - 3 30"}}],
            "effective_scopes": [{"quantifier": "specific_line"}]}  # fmt: skip
    assert claim_proves(mate, "black") == ("[백의 메이트] 엔진 라인에서 백이 4수 만에 메이트한다 — "
                                           "마지막 수 30.Ng5# (이 라인에서만)")  # fmt: skip
    assert claim_proves(mate, "white").startswith("[백(둔 쪽)의 메이트]")


def test_an_en_passant_capture_in_a_line_is_said_with_the_pawn_it_takes() -> None:
    from calliope.agent.remarks import en_passant

    fen = "rnbqkbnr/1pp1pppp/p7/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3"
    (said,) = en_passant(fen, {"played": ["e5d6", "c7d6"], "best": ["d2d4"]})
    assert said["line"] == "played" and said["move"] == "3.exd6"
    assert "흑 폰(d5)을 잡습니다" in said["text"] and "d6 칸은 비어" in said["text"]
    assert en_passant(fen, {"best": ["d2d4", "d5d4"]}) == []  # an illegal move ends the line


def test_a_digest_names_the_en_passant_capture_of_its_played_move(tmp_path) -> None:
    s = session(tmp_path)
    game = s.open_game(pgn="1. e4 a6 2. e5 d5 3. exd6 *", plies="5-5")["game"]
    d = s.ply(game, 5)
    assert d["en_passant"][0]["line"] == "played" and d["en_passant"][0]["move"] == "3.exd6"
    s.close()


def test_a_range_over_the_per_call_bound_points_to_analyze_game(tmp_path) -> None:
    from calliope.agent import Limits

    s = session(tmp_path, Limits(max_uncached_plies_per_call=2))
    with pytest.raises(BudgetError, match="in one call: at most 2; .* call `analyze_game`"):
        s.open_game(pgn=GAME, plies="1-3")
    s.open_game(pgn=GAME, plies="1-2")
    s.close()
