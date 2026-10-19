"""MS-b with Stockfish 19 (gated): `board_v2` carries the relation claims of the move (`leads_to`),
a held exposure as a `held` item, the relation claims of the engine line as claims with their
relation; every template's `proves` may be written as it stands when its claim is cited (MS-D §8.3,
I5); every claim stays reachable (I4)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from calliope.agent import Limits, Session

STOCKFISH = os.environ.get("CALLIOPE_STOCKFISH_PATH")
HERE = Path(__file__).resolve().parent
GAMES = {
    "opera": (HERE / "fixtures" / "opera_game.pgn").read_text(),
    "rapid": (HERE.parent / "reasoning" / "fixtures" / "chesscom_rapid_813_801.pgn").read_text(),
    "weak": (HERE / "fixtures" / "weak_engines_1.pgn").read_text(),
    "weak2": (HERE / "fixtures" / "weak_engines_2.pgn").read_text(),
}
pytestmark = pytest.mark.skipif(not STOCKFISH or not os.path.exists(STOCKFISH),
                                reason="needs Stockfish 19")  # fmt: skip
# a ply of the four games where each template's claim is SUPPORTED
EXAMPLES = {
    "best_stops_reply_v1": ("weak2", 26), "better_alternative_v1": ("opera", 8),
    "better_move_v1": ("opera", 18), "capture_holds_v1": ("opera", 19),
    "check_answer_v1": ("opera", 22), "discovery_v2": ("weak", 61), "forcing_v1": ("opera", 21),
    "fork_v2": ("opera", 21), "left_en_prise_v2": ("weak", 62), "mate_allowed_v1": ("rapid", 52),
    "mate_delivered_v1": ("opera", 33), "mate_found_v1": ("opera", 31),
    "mate_in_one_allowed_v1": ("opera", 32), "material_gain_v3": ("opera", 7),
    "material_loss_v2": ("opera", 18), "missed_gain_v1": ("opera", 12),
    "newly_exposed_v1": ("weak", 76), "only_move_v1": ("opera", 21),
    "piece_offer_v1": ("opera", 19), "pin_v2": ("opera", 11), "prevents_v1": ("opera", 30),
    "removed_defender_v2": ("weak", 62), "rescue_v1": ("opera", 9),
    "sacrifice_compensated_v2": ("opera", 23), "sacrifice_offer_v1": ("opera", 23),
    "sacrifice_sound_v1": ("opera", 23),
}  # fmt: skip


@pytest.fixture(scope="module")
def s(tmp_path_factory):
    from calliope.facts.search import StockfishEngine

    s = Session(tmp_path_factory.mktemp("ms-b"), lambda: StockfishEngine.start(STOCKFISH),
                Limits(max_searches=4000, max_uncached_plies=400,
                       max_uncached_plies_per_call=400))  # fmt: skip
    s.ids_ = {name: s.open_game(pgn=pgn)["game"] for name, pgn in GAMES.items()}
    yield s
    s.close()


def _entries(d: dict) -> list[dict]:
    """Every claim entry a digest shows: listed, under a group's member, under a board item."""

    out = []
    for c in d["claims"]:
        out.append(c)
        out += c.get("also", [])
    return out


def test_31_qf6_the_lost_defence_carries_its_claim_and_f5_held(s) -> None:
    d = s.ply(s.ids_["weak"], 62)
    lost = next(c for c in d["board"]["changes"] if c["kind"] == "lost_defence"
                and c["propositions"][0]["defender"] == "f8")  # fmt: skip
    assert lost["leads_to"]["template"] == "removed_defender_v2" and lost["ref"].startswith("b")
    assert lost["leads_to"]["claim"] not in {c["ref"] for c in d["claims"]}  # once (MS-D §6)
    # BL-D §2: the facts give the bishop on d5 (gain 3) a held item too, first by stake; the
    # claim's f5 pawn is the facts' item of the same piece, carrying the claim
    held = next(c for c in d["board"]["changes"] if c["kind"] == "held"
                and c["propositions"][0]["piece"] == "f5")  # fmt: skip
    assert held["leads_to"]["template"] == "left_en_prise_v2"
    assert [p["piece"] for p in held["propositions"] if p["kind"] == "exposed"] == ["f5", "f5"]
    assert len([c for c in d["board"]["changes"] if c["kind"] == "held"]) == 2
    discovery = next(c for c in d["claims"] if c["template"] == "discovery_v2")
    assert discovery["relation"]["place"]["at"] == "line" and discovery["link"]["did"]
    assert s.detail(s.ids_["weak"], lost["ref"])["item"]["leads_to"] == lost["leads_to"]


def test_38_rxh5_and_13_rxd7_their_items_carry_the_relation_claims(s) -> None:
    d = s.ply(s.ids_["weak"], 76)
    weak = next(c for c in d["board"]["changes"] if c["kind"] == "weakness"
                and c["propositions"][0].get("piece") == "h5")  # fmt: skip
    assert weak["leads_to"]["template"] == "newly_exposed_v1"
    assert weak["leads_to"]["link"] == "explains"
    d = s.ply(s.ids_["opera"], 25)
    fork = next(c for c in d["board"]["changes"] if c["propositions"][0]["kind"] == "pattern")
    assert fork["leads_to"]["template"] == "fork_v2" and fork["leads_to"]["did"]
    assert "배치" in fork["proves"] or "물질을 얻었다" in fork["proves"]


@pytest.mark.parametrize("template", sorted(EXAMPLES))
def test_a_proves_may_be_written_as_it_stands(s, template) -> None:
    """MS-D §8.3 (review B2): a sentence that is the claim's `proves`, citing the claim, is
    accepted — its moves, squares and numbers all allowed."""

    name, ply = EXAMPLES[template]
    game = s.ids_[name]
    d = s.ply(game, ply)
    entries = [c for c in _entries(d) if c["template"] == template]
    if not entries:  # under a board item (MS-D §6): read it whole
        refs = [c["leads_to"]["claim"] for c in d["board"]["changes"]
                if c.get("leads_to", {}).get("template") == template]  # fmt: skip
        assert refs, template
        item = s.detail(game, refs[0])["item"]
        from calliope.agent.remarks import claim_proves

        entries = [{"ref": refs[0], "status": item["status"],
                    "proves": claim_proves(item, d["side"])}]  # fmt: skip
    entry = entries[0]
    assert entry.get("proves"), template
    use = "line_fact" if entry["status"] == "supported" else "uncertain"
    answer = s.submit_commentary(game, ply=ply, agent={"name": "t"}, propositions=[
        {"id": "j", "kind": "judgement", "judgement": d["judgement"]},
        {"id": "c", "kind": "claim", "claim": entry["ref"], "use": use}], sentences=[
        {"text": "판정을 받은 수다.", "class": "sourced", "cites": ["j"]},
        {"text": entry["proves"], "class": "sourced", "cites": ["c"]}])  # fmt: skip
    assert answer["accepted"], (template, entry["proves"], answer)


def test_every_claim_is_reachable_at_the_examples(s) -> None:
    """MS-D I4: listed, under a group's member or a board item, or by its ref in `not_shown`."""

    for name, ply in sorted(set(EXAMPLES.values())):
        game = s.ids_[name]
        d, full = s.ply(game, ply), s.ply(game, ply, view="full")
        reach = {c["ref"] for c in _entries(d)}
        reach |= {i["leads_to"]["claim"] for i in d["board"]["changes"] if "leads_to" in i}
        reach |= set(d["not_shown"]["refuted"]) | {
            e.get("leads_to") or e["ref"] for e in d["not_shown"]["named"]
        }
        assert reach == {c["ref"] for c in full["analysis"]["claims"]}, (name, ply)
