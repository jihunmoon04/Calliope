"""MS-a with Stockfish 19 (gated): the relations of the trial's fixed moments are the board's
(MS-D §4.2); the relation claims read whole, with their kinds, places, times and links (§5); a
mechanism's batch decides 11.Bxb5+ and is never worse than one node at a time, at any budget (§2);
`sacrifice_compensated_v2` decides 16.Qb8+ by the open line's score (§3)."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest
from test_piece_relations import same_as_board

from calliope.agent import Limits, Session
from calliope.facts.engine import FactEngine
from calliope.reasoning.findings import CompensationFinding, CompensationKind
from calliope.reasoning.piece_relations import FAMILIES, MOVE, Place, claim_relation
from calliope.reasoning.runner import Reasoner
from calliope.server.pipeline import ply_request

STOCKFISH = os.environ.get("CALLIOPE_STOCKFISH_PATH")
HERE = Path(__file__).resolve().parent
RAPID = (HERE.parent / "reasoning" / "fixtures" / "chesscom_rapid_813_801.pgn").read_text()
OPERA = (HERE / "fixtures" / "opera_game.pgn").read_text()
WEAK = (HERE / "fixtures" / "weak_engines_1.pgn").read_text()
pytestmark = pytest.mark.skipif(not STOCKFISH or not os.path.exists(STOCKFISH),
                                reason="needs Stockfish 19")  # fmt: skip


@pytest.fixture(scope="module")
def s(tmp_path_factory):
    from calliope.facts.search import StockfishEngine

    s = Session(tmp_path_factory.mktemp("ms-a"), lambda: StockfishEngine.start(STOCKFISH),
                Limits(max_searches=4000, max_uncached_plies=400,
                       max_uncached_plies_per_call=400))  # fmt: skip
    s.games_ = {name: s.open_game(pgn=pgn)["game"] for name, pgn in
                (("rapid", RAPID), ("opera", OPERA), ("weak", WEAK))}  # fmt: skip
    yield s
    s.close()


def _claims(s, name: str, ply: int) -> dict:
    """The supported relation claims at `ply`, read: template → ClaimRelation."""

    game = s.game(s.games_[name])
    _record, _cached, analysis = s._analysed(game, game.parsed, ply)
    view, nodes = s._node(game, tuple(game.parsed.uci[:ply]))
    s._records(game, view, nodes[-2], ("pieces", "patterns", "exchange", "status"))
    s._records(game, view, nodes[-1], FAMILIES)
    out = {}
    for c in analysis.claims:
        read = claim_relation(analysis, c, analysis.tree.view(analysis.rev), game.facts.view())
        if read is not None:
            out[c.hypothesis.template] = read
    return out


def _squares(read) -> list[tuple[str, str]]:
    return [(name, p.square) for name, p in read.relation.roles]


# -- §4.2: the board's relations ------------------------------------------------------------------


@pytest.mark.parametrize(("name", "ply"), [("rapid", 52), ("rapid", 54), ("weak", 56),
                                           ("weak", 62), ("weak", 76), ("opera", 18),
                                           ("opera", 25)])  # fmt: skip
def test_the_fixed_moments_relations_are_the_boards(s, name, ply) -> None:
    board, read = same_as_board(s, s.games_[name], ply)
    assert board == read


# -- §5: the relation claims ----------------------------------------------------------------------


def test_31_qf6_a_defence_ended_a_piece_held_en_prise_and_a_discovery_in_the_line(s) -> None:
    read = _claims(s, "weak", 62)
    removed = read["removed_defender_v2"]
    assert removed.relation.kind == "defence" and removed.relation.time == "ended"
    assert removed.relation.place == MOVE
    assert _squares(removed) == [("defender", "f8"), ("defended", "f5"), ("attacker", "e4")]
    assert removed.link.kind == "associated_with"
    held = read["left_en_prise_v2"]
    assert held.relation.kind == "exposed" and held.relation.time == "held"
    assert _squares(held) == [("piece", "f5")]
    discovery = read["discovery_v2"]
    assert discovery.relation.kind == "discovered_attack"
    assert discovery.relation.place == Place("line", 2)
    assert _squares(discovery) == [("slider", "d3"), ("front", "e4"), ("target", "f5")]
    assert discovery.link.did == "configuration"


def test_38_rxh5_the_rook_moved_into_an_attack_that_began(s) -> None:
    exposed = _claims(s, "weak", 76)["newly_exposed_v1"]
    assert exposed.relation.time == "began" and _squares(exposed) == [("piece", "h5")]
    assert exposed.link.kind == "explains"


def test_13_rxd7_the_fork_at_the_move_and_6_bc4_a_relative_pin_in_the_line(s) -> None:
    fork = _claims(s, "opera", 25)["fork_v2"]
    assert fork.relation.kind == "double_attack" and fork.relation.place == MOVE
    assert _squares(fork) == [("actor", "d7"), ("target", "a7"), ("target", "e7"),
                              ("target", "d8")]  # fmt: skip
    pin = _claims(s, "opera", 11)["pin_v2"]
    assert pin.relation.kind == "relative_pin" and pin.relation.place == Place("line", 3)
    assert _squares(pin) == [("slider", "b3"), ("front", "b7"), ("back", "b8")]


# -- §2: a mechanism's batch ----------------------------------------------------------------------


def _analyse(s, name: str, ply: int, today: bool, monkeypatch, **budget):
    from calliope.reasoning import runner
    from calliope.reasoning.catalogue import mechanisms

    with monkeypatch.context() as m:
        if today:  # one node a request, needs admitted by key: the scan before MS-a
            m.setattr(mechanisms, "BATCH_NODES", 1)
            m.setattr(runner._Run, "_order",
                      lambda self, wanted, listed: sorted(wanted, key=runner.need_key))  # fmt: skip
        game = s.game(s.games_[name])
        request = ply_request(game.parsed, ply, s.profile)
        if budget:
            request = replace(request, budget=replace(request.budget, **budget))
        analysis = Reasoner(FactEngine(engine=s.slot.port)).analyse(request)
    return {
        c.id: (c.hypothesis.template, c.verdict.status.value, c.decided) for c in analysis.claims
    }


def test_11_bxb5_the_fork_is_decided_within_three_rounds(s) -> None:
    game = s.game(s.games_["opera"])
    _record, _cached, analysis = s._analysed(game, game.parsed, 21)
    fork = next(c for c in analysis.claims if c.hypothesis.template == "fork_v2")
    assert fork.verdict.status.value == "supported"


@pytest.mark.parametrize("ply", [21, 25])
def test_the_batch_is_never_worse_and_never_later(s, ply, monkeypatch) -> None:
    for budget in ({}, {"max_ensure_nodes": 1}, {"max_ensure_nodes": 2}, {"max_ensure_nodes": 4},
                   {"max_ensure_nodes": 8}, {"max_rounds": 2}):  # fmt: skip
        today = _analyse(s, "opera", ply, True, monkeypatch, **budget)
        now = _analyse(s, "opera", ply, False, monkeypatch, **budget)
        for cid, (template, status, decided) in today.items():
            if status in ("supported", "refuted"):
                assert cid in now and now[cid][1] == status, (budget, template)
                assert now[cid][2] <= decided, (budget, template)  # the scan first (review B6)


# -- §3: sacrifice_compensated_v2 -----------------------------------------------------------------


def test_16_qb8_mates_over_the_open_line_by_its_score_and_13_rxd7_stays_open(s) -> None:
    game = s.game(s.games_["opera"])
    _record, _cached, qb8 = s._analysed(game, game.parsed, 31)
    claim = next(c for c in qb8.claims if c.hypothesis.template == "sacrifice_compensated_v2")
    assert claim.verdict.status.value == "supported"
    (finding,) = [f for f in claim.verdict.findings if isinstance(f, CompensationFinding)]
    assert finding.kind is CompensationKind.MATE_OVER_SCORES
    _record, _cached, rxd7 = s._analysed(game, game.parsed, 25)
    claim = next(c for c in rxd7.claims if c.hypothesis.template == "sacrifice_compensated_v2")
    assert (claim.verdict.status.value, claim.verdict.reason) == ("inconclusive", "LINE_TOO_SHORT")
