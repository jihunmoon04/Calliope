"""MS-c with Stockfish 19 (gated): every board item of the trial's fixed moments, cited by its `b`
handle with its `proves` as the sentence, is accepted (MS-D §8.3, I5); a claim only associated
with its consequence, cited by handle, is stored `associated` — never `mechanism` (§9.2)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from calliope.agent import Limits, Session

STOCKFISH = os.environ.get("CALLIOPE_STOCKFISH_PATH")
HERE = Path(__file__).resolve().parent
GAMES = {
    "opera": ((HERE / "fixtures" / "opera_game.pgn").read_text(), (18, 25, 29)),
    "rapid": ((HERE.parent / "reasoning" / "fixtures" / "chesscom_rapid_813_801.pgn").read_text(),
              (40, 52, 54)),
    "weak": ((HERE / "fixtures" / "weak_engines_1.pgn").read_text(), (56, 62, 76)),
    "weak2": ((HERE / "fixtures" / "weak_engines_2.pgn").read_text(), (37, 38, 56)),
}  # fmt: skip
pytestmark = pytest.mark.skipif(not STOCKFISH or not os.path.exists(STOCKFISH),
                                reason="needs Stockfish 19")  # fmt: skip


@pytest.fixture(scope="module")
def s(tmp_path_factory):
    from calliope.facts.search import StockfishEngine

    s = Session(tmp_path_factory.mktemp("ms-c"), lambda: StockfishEngine.start(STOCKFISH),
                Limits(max_searches=4000, max_uncached_plies=400,
                       max_uncached_plies_per_call=400))  # fmt: skip
    s.ids_ = {name: s.open_game(pgn=pgn)["game"] for name, (pgn, _) in GAMES.items()}
    yield s
    s.close()


@pytest.mark.parametrize(("name", "ply"), [(n, p) for n, (_, ps) in GAMES.items() for p in ps])
def test_a_board_item_cited_by_handle_may_say_its_proves(s, name, ply) -> None:
    game = s.ids_[name]
    d = s.ply(game, ply)
    for item in d["board"]["changes"]:
        answer = s.submit_commentary(game, ply=ply, agent={"name": "t"}, sentences=[
            {"text": "판정을 받은 수다.", "class": "sourced", "cites": [d["judgement"]]},
            {"text": item["proves"], "class": "sourced", "cites": [item["ref"]],
             "states": [item["ref"]]}])  # fmt: skip
        assert answer["accepted"], (name, ply, item["kind"], item["proves"], answer)


def test_an_associated_claim_cited_by_handle_is_stored_associated(s) -> None:
    game = s.ids_["weak"]
    d = s.ply(game, 62)  # 31...Qf6: removed_defender_v2, associated with the material lost
    lost = next(c for c in d["board"]["changes"]
                if c.get("leads_to", {}).get("template") == "removed_defender_v2")  # fmt: skip
    assert lost["leads_to"]["link"] == "associated_with"
    assert lost["leads_to"]["as"] == "associated"  # MS-c review 2 N2: shown before it is cited
    ref = lost["leads_to"]["claim"]
    answer = s.submit_commentary(game, ply=62, agent={"name": "t"}, sentences=[
        {"text": "판정을 받은 수다.", "class": "sourced", "cites": [d["judgement"]]},
        {"text": "수비가 끊긴 것과 물질 손실이 함께 나온다.", "class": "interpretation",
         "cites": [ref]}])  # fmt: skip
    assert answer["accepted"], answer
    g = s.game(game)
    record = s.store.for_subject(g.key, tuple(g.parsed.uci[:62]))[0]  # newest first
    claim = next(p for p in record["propositions"] if p.get("by_handle") == ref)
    assert claim["use"] == "associated" and claim["use_by"] == "server"
