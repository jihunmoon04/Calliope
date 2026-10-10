"""Shared definitions of catalogue v1 (R2-D §1, §8.2, §8.6c, §8.6e) and whole-run properties:
registry order, determinism, encoding (R2-D §6, §8.10; R0-D §14.1, §16)."""

from __future__ import annotations

import random
from dataclasses import replace

import pytest
from story import claim, line, run

from calliope.facts import (
    PLAYED,
    Color,
    EngineLineId,
    EnsureRequest,
    ExtendRequest,
    FactEngine,
    InputLine,
    OpenRequest,
    RootSpec,
)
from calliope.reasoning import ReasoningBudget
from calliope.reasoning.catalogue import CATALOGUE_V1
from calliope.reasoning.encoding import canonical_bytes
from calliope.reasoning.findings import Outcome, OutcomeKind
from calliope.reasoning.lines import (
    Exposure,
    compare,
    decisive_ply,
    exposure,
    read_line,
    unsafe,
)
from calliope.reasoning.refs import LineSegment

W, B = Color.WHITE, Color.BLACK


def _played(fen: str, sans: str):
    engine = FactEngine()
    tree = engine.open(OpenRequest(root=RootSpec(fen=fen)))
    engine.extend(tree, ExtendRequest((InputLine("g", tuple(sans.split())),), PLAYED))
    view = tree.view()
    nodes = view.input_line("g").nodes
    engine.ensure(tree, EnsureRequest(nodes, ("pieces",)))
    return tree.view(), nodes


# -- unsafe_v1 (R2-D §1.6, §8.6e) ----------------------------------------------------------------


def test_unsafe_v1_outnumbered_or_attacked_by_a_lower_piece() -> None:
    # the queen on d4: one attacker, one defender, but the attacker is a pawn
    view, nodes = _played("4k3/8/8/4p3/8/2P5/8/3QK3 w - - 0 1", "Qd4")
    queen = view.node(nodes[0]).piece_at("d1")
    assert unsafe(view, queen, nodes[0]) is False
    assert unsafe(view, queen, nodes[1]) is True
    # an undefended knight attacked by a knight is outnumbered
    view, nodes = _played("4k3/8/8/2n5/8/3N4/8/4K3 w - - 0 1", "Kf1")
    knight = view.node(nodes[1]).piece_at("d3")
    assert unsafe(view, knight, nodes[1]) is True
    # equal attackers of equal rank, defended: safe
    view, nodes = _played("4k3/8/8/2n5/8/3N4/4P3/4K3 w - - 0 1", "Kd2")
    assert unsafe(view, view.node(nodes[1]).piece_at("d3"), nodes[1]) is False


def test_a_piece_off_the_board_is_not_unsafe() -> None:
    # R2-D §1.1: tests read by square at the node; an absent piece makes the test false
    view, nodes = _played("4k3/8/8/4p3/3Q4/8/8/4K3 b - - 0 1", "exd4")
    queen = view.node(nodes[0]).piece_at("d4")
    assert view.node(nodes[1]).square_of(queen) is None
    assert unsafe(view, queen, nodes[1]) is False


def test_a_missing_record_is_reported_not_guessed() -> None:
    engine = FactEngine()
    tree = engine.open(OpenRequest(root=RootSpec(), families=("status", "draw", "move")))
    view = tree.view()
    king = view.node(view.root).piece_at("e1")
    assert unsafe(view, king, view.root) is None


# -- the outcome order and the decisive ply (R2-D §1.3, §1.5) -----------------------------------


def _mate(winner: Color, n: int) -> Outcome:
    return Outcome(OutcomeKind.MATE, winner, n)


def _stable(delta: int) -> Outcome:
    return Outcome(OutcomeKind.STABLE, delta=delta)


DRAWN = Outcome(OutcomeKind.DRAWN)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (_mate(W, 2), _mate(W, 3), 1),  # a faster mate first
        (_mate(W, 9), _stable(9), 1),
        (_stable(1), _stable(0), 1),
        (_stable(-9), _mate(B, 1), 1),
        (_mate(B, 5), _mate(B, 2), 1),  # mated later is better
        (DRAWN, _mate(B, 9), 1),
        (DRAWN, _mate(W, 9), -1),
        (DRAWN, _stable(0), None),  # incomparable
        (DRAWN, DRAWN, 0),
        (Outcome(OutcomeKind.OPEN), _stable(0), None),  # undecided
        (Outcome(OutcomeKind.MISSING, reason="LINE_TOO_SHORT"), _mate(W, 1), None),
    ],
)
def test_the_outcome_order(a: Outcome, b: Outcome, expected: int | None) -> None:
    assert compare(a, b, W) == expected
    if expected is not None:
        assert compare(b, a, W) == -expected


def test_the_decisive_ply_is_where_the_final_level_is_reached() -> None:
    # 1.h3 Nxc2+ 2.Kd2 Nxa1: the pawn turns the balance, the rook decides (re-check B1)
    assert decisive_ply((0, 0, -1, -1, -6, -6, -6), loss=True) == 4
    # capture, then the main loss, then a partial recovery
    assert decisive_ply((0, 0, -3, -3, -12, -7, -7), loss=True) == 4
    assert decisive_ply((0, 0, -3, 0, 0), loss=True) is None  # no loss at the end
    assert decisive_ply((0, 3, 3, 9, 9), loss=False) == 3
    assert decisive_ply((0, 1, -1, 1, 1), loss=False) == 3  # stays above 0 from ply 3


def test_balances_count_a_capture_promotion_as_one_ply() -> None:
    fen = "1n2k3/P7/8/8/8/8/8/4K3 w - - 0 1"
    lines = [
        line(fen, "axb8=Q Kd7 Qb5+ Kd6 Kd2 Ke6", (900, 100, 0), cp=900),
        line(fen, "Kd2 Kd7 Kd3 Kd6", (300, 600, 100)),
    ]
    analysis = run(fen, "axb8=Q", lines, multipv=2)
    gain = claim(analysis, "material_gain_v1")
    window = gain.hypothesis.operands[0]
    lp = read_line(analysis.tree.view(analysis.rev), window, W)
    assert lp.balances[:2] == (0, 11)  # +3 for the knight, +8 for the promotion, one ply


# -- exposure continuity (R2-D §1.6a) ------------------------------------------------------------


def test_exposure_fails_on_a_present_record_before_asking_for_a_missing_one() -> None:
    fen = "4r1k1/5pp1/7p/8/8/6N1/P7/2B1K3 w - - 0 1"
    lp = "Ne4 f5 Bxh6 gxh6 a3 fxe4 a4 Kf7"
    budget = replace(ReasoningBudget(), pv_plies=4, max_rounds=1)
    lines = [line(fen, "Kd2 Kf8 Ne2 Ke7", (300, 600, 100)), line(fen, lp, (0, 100, 900), cp=-500)]
    analysis = run(fen, "Ne4", lines, multipv=2, budget=budget)
    view = analysis.tree.view(analysis.rev)
    loss = claim(analysis, "material_loss_v1")
    nodes = view.line(loss.hypothesis.target.at.line).nodes
    knight = view.node(nodes[1]).piece_at("e4")
    rook = view.node(nodes[1]).piece_at("e8")
    pawn = view.node(nodes[1]).piece_at("f7")
    assert unsafe(view, knight, nodes[5]) is None  # beyond the round-0 ensure
    # the rook attacks the knight throughout: only N_5 is missing
    assert exposure(view, knight, rook, nodes[1:6]) == (Exposure.UNDECIDED, (nodes[5],))
    # the pawn does not attack it at N_1: a present failing record decides, no need
    assert exposure(view, knight, pawn, nodes[1:6]) == (Exposure.NOT_EXPOSED, ())
    # with one round only, the pin check's need is never met
    assert claim(analysis, "pin_v1").verdict.reason == "ROUND_LIMIT"


# -- registry order, determinism, encoding (R2-D §6, §8.10) -------------------------------------


def test_the_registry_order() -> None:
    assert [t.name for t in CATALOGUE_V1] == [
        "mate_delivered_v1", "mate_found_v1", "mate_in_one_allowed_v1", "mate_allowed_v1",
        "mate_missed_v1", "material_loss_v1", "material_gain_v1", "forcing_v1", "only_move_v1",
        "sacrifice_offer_v1", "sacrifice_sound_v1", "sacrifice_compensated_v1", "prevents_v1",
        "fork_v1", "pin_v1", "skewer_v1", "discovery_v1", "removed_defender_v1",
        "newly_unsafe_v1", "left_en_prise_v1", "better_move_v1",
    ]  # fmt: skip


SCENARIOS = [
    (
        "4kb2/8/8/6n1/1P1N4/8/P7/4K3 w - - 0 1",
        "a3",
        ["Nb3 Ne6 Kd2 Kd7", "a3 Bc5 b5 Be7 b6 Nf3+ Ke2 Nxd4+ Kd3 Nf5"],
    ),
    ("r5k1/5ppp/8/8/8/8/4QPPP/4R1K1 w - - 0 1", "Qe8+", ["Qe8+ Rxe8 Rxe8#", "h3 h6 Qe3 Kh7"]),
]


def _scenario(index: int, templates=None):
    fen, played, pvs = SCENARIOS[index]
    mate = {"mate": 2} if index == 1 else {"cp": 0}
    lines = [line(fen, pvs[0], (300, 600, 100), **mate), line(fen, pvs[1], (0, 100, 900), cp=-500)]
    return run(fen, played, lines, multipv=2, templates=templates)


def _bytes(analysis) -> bytes:
    return canonical_bytes((analysis.claims, analysis.relations, analysis.labels))


@pytest.mark.parametrize("index", [0, 1])
def test_a_rerun_and_a_shuffled_registry_give_the_same_bytes(index: int) -> None:
    first = _bytes(_scenario(index))
    assert _bytes(_scenario(index)) == first
    shuffled = list(CATALOGUE_V1)
    random.Random(index).shuffle(shuffled)
    assert _bytes(_scenario(index, tuple(shuffled))) == first


def test_every_claim_encodes_with_the_reasoning_registry() -> None:
    analysis = _scenario(0)
    assert analysis.claims
    for c in analysis.claims:
        assert canonical_bytes(c)  # findings, scopes, evidence: all registered types
    assert canonical_bytes(analysis.round_zero.observations)


def test_no_line_need_and_no_causes_in_catalogue_v1() -> None:
    for index in (0, 1):
        analysis = _scenario(index)
        assert all(r.kind.value != "causes" for r in analysis.relations)  # E8
        for rnd in analysis.rounds:
            assert all(type(n).__name__ == "FamilyNeed" for n in rnd.admitted)  # R2-D §4


def test_engine_line_ids_in_targets_name_the_pinned_search() -> None:
    analysis = _scenario(0)
    search = analysis.round_zero.judgements[0].search.search_id
    for c in analysis.claims:
        at = c.hypothesis.target.at
        if isinstance(at, LineSegment) and isinstance(at.line, EngineLineId):
            assert at.line.search_id == search  # R0-D R0-I1: one search
