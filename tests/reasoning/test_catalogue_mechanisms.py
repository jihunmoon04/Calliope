"""Catalogue v1 mechanisms (R2-D §3.7, §3.8, §3.8a, §3.8b, §8.2a, §8.5, §8.6, §8.10).

A mechanism EXPLAINS its consequence only through a passed `REALIZED` check; otherwise it is
`ASSOCIATED_WITH`; v1 never claims `CAUSES` (R2-D E8).
"""

from __future__ import annotations

from dataclasses import replace

from story import R, S, claim, finding, line, run, status

from calliope.reasoning import ReasoningBudget
from calliope.reasoning.findings import (
    DefenceFinding,
    HangingFinding,
    HangingKind,
    MaterialFinding,
    MechanismFinding,
)
from calliope.reasoning.hypotheses import RelationKind
from calliope.reasoning.verification import CausalCheck

EVEN, LOST, WIN = (300, 600, 100), (0, 100, 900), (900, 100, 0)


def _edge(analysis, source: str, target: str) -> set[RelationKind]:
    a, b = claim(analysis, source), claim(analysis, target)
    return {r.kind for r in analysis.relations if r.source == a.id and r.target == b.id}


def _passed(analysis, name: str) -> bool:
    return finding(claim(analysis, name), CausalCheck).passed


def _loss(fen: str, played: str, lp: str, best: str, **kw):
    return run(fen, played, [line(fen, best, EVEN), line(fen, lp, LOST, cp=-500)], multipv=2, **kw)


# -- fork_v1 (R2-D §3.7) -------------------------------------------------------------------------

FORK = "4kb2/8/8/6n1/1P1N4/8/P7/4K3 w - - 0 1"


def test_the_fork_the_capture_goes_through_after_an_unrelated_double_attack() -> None:
    analysis = _loss(FORK, "a3", "a3 Bc5 b5 Be7 b6 Nf3+ Ke2 Nxd4+ Kd3 Nf5", "Nb3 Ne6 Kd2 Kd7")
    fork = claim(analysis, "fork_v1")
    assert fork.verdict.status is S and _passed(analysis, "fork_v1")
    mechanism = finding(fork, MechanismFinding)
    assert mechanism.actor.square == "f3" and not mechanism.walked_into  # …Nf3+ at N_6
    assert {t.square for t in mechanism.targets} == {"d4", "e1"}
    assert _edge(analysis, "fork_v1", "material_loss_v1") == {
        RelationKind.EXPLAINS,
        RelationKind.DERIVED_FROM,
    }
    assert "unsafe_v1" in fork.verdict.scope.policies


def test_a_fork_on_a_piece_already_losable_is_only_associated() -> None:
    analysis = _loss(FORK, "a3", "a3 Bc5 b5 Nf3+ Ke2 Nxd4+ Kd3 Nf5", "Nb3 Ne6 Kd2 Kd7")
    assert status(analysis, "fork_v1") is S and not _passed(analysis, "fork_v1")
    assert _edge(analysis, "fork_v1", "material_loss_v1") == {
        RelationKind.ASSOCIATED_WITH,
        RelationKind.DERIVED_FROM,
    }


def test_a_capture_fork_names_the_rook_as_the_decisive_victim() -> None:
    # R2-D §1.5 re-check B1: 1.h3 Nxc2+ 2.Kd2 Nxa1 — the pawn turns the balance, the rook decides
    fen = "4k3/8/8/8/1n6/8/2P4P/R3K3 w - - 0 1"
    analysis = _loss(fen, "h3", "h3 Nxc2+ Kd2 Nxa1 Kc1 Ke7 Kb2 Kd6", "Kd2 Nxc2 Kxc2 Kd7 Kd3 Kd6")
    event = finding(claim(analysis, "material_loss_v1"), MaterialFinding).event
    assert (event.ply, event.victim.square) == (4, "a1")
    assert status(analysis, "fork_v1") is S and _passed(analysis, "fork_v1")  # king and rook


def test_a_fork_whose_capture_is_made_by_another_piece_is_associated() -> None:
    # …Ne3 forks both rooks; after 2.c3 the bishop, not the knight, takes d1
    fen = "6k1/8/8/8/b5n1/8/2P4P/3R1R1K w - - 0 1"
    lp = "h3 Ne3 c3 Bxd1 Kg1 Kg7 Kh2 Kh6"
    analysis = _loss(fen, "h3", lp, "Rd2 Nf6 Rdf2 Kg7")
    event = finding(claim(analysis, "material_loss_v1"), MaterialFinding).event
    assert (event.victim.square, event.capturer.square) == ("d1", "a4")
    fork = claim(analysis, "fork_v1")
    assert fork.verdict.status is S and not _passed(analysis, "fork_v1")
    assert finding(fork, MechanismFinding).actor.square == "e3"


# -- pin_v1 (R2-D §3.7) --------------------------------------------------------------------------

PIN = "4r1k1/5p2/8/8/8/6N1/P7/4K3 w - - 0 1"


def test_a_pin_the_played_move_walked_into() -> None:
    analysis = _loss(PIN, "Ne4", "Ne4 f5 a3 fxe4 a4 Kf7", "Kd2 Kf8 Ne2 Ke7")
    pin = claim(analysis, "pin_v1")
    assert pin.verdict.status is S and _passed(analysis, "pin_v1")
    assert finding(pin, MechanismFinding).walked_into
    # the capturer f5 attacked the knight only later: the move's own exposure is not realized
    unsafe = claim(analysis, "newly_unsafe_v1")
    assert finding(unsafe, HangingFinding).kind is HangingKind.MOVED_INTO_ATTACK
    assert not _passed(analysis, "newly_unsafe_v1")
    assert _edge(analysis, "newly_unsafe_v1", "material_loss_v1") >= {RelationKind.ASSOCIATED_WITH}


def test_a_pin_past_the_round_zero_ensure_is_decided_in_the_next_round() -> None:
    # pv_plies 4: the window widens to 8 plies; the pin check reads N_5, beyond the ensure
    fen = "4r1k1/5pp1/7p/8/8/6N1/P7/2B1K3 w - - 0 1"
    lp = "Ne4 f5 Bxh6 gxh6 a3 fxe4 a4 Kf7"
    budget = replace(ReasoningBudget(), pv_plies=4)
    analysis = _loss(fen, "Ne4", lp, "Kd2 Kf8 Ne2 Ke7", budget=budget)
    loss = claim(analysis, "material_loss_v1")
    assert finding(loss, MaterialFinding).event.ply == 6
    pin = claim(analysis, "pin_v1")
    assert pin.verdict.status is S and _passed(analysis, "pin_v1")
    assert pin.decided == 1 and analysis.rounds[0].index == 0  # ensured in round 0's requests
    families = {n.family for n in analysis.rounds[0].admitted}
    assert {"delta", "pieces"} <= families  # the pin never ended on the way, and holds at N_5
    # the same run with no ensure budget ends INCONCLUSIVE(BUDGET)
    starved = replace(budget, max_ensure_nodes=0)
    analysis = _loss(fen, "Ne4", lp, "Kd2 Kf8 Ne2 Ke7", budget=starved)
    assert claim(analysis, "pin_v1").verdict.reason == "BUDGET"


# -- skewer_v1, discovery_v1 (R2-D §3.7) ---------------------------------------------------------


def test_a_skewer_wins_the_queen_behind_the_king() -> None:
    fen = "8/8/q3k3/8/8/8/8/4K2R w - - 0 1"
    lines = [
        line(fen, "Rh6+ Kd5 Rxa6 Kc5 Kd2 Kb5", WIN, cp=900),
        line(fen, "Kd2 Qa2+ Kc3 Qa5+", EVEN),
    ]
    analysis = run(fen, "Rh6+", lines, multipv=2)
    assert status(analysis, "material_gain_v1") is S
    skewer = claim(analysis, "skewer_v1")
    assert skewer.verdict.status is S and _passed(analysis, "skewer_v1")
    assert finding(skewer, MechanismFinding).actor.square == "h6"
    assert _edge(analysis, "skewer_v1", "material_gain_v1") >= {RelationKind.EXPLAINS}


def test_a_discovered_check_wins_the_queen() -> None:
    # R2-D §3.7 example (b): 1.Nc3+ Kd7 2.Nxd5
    fen = "4k3/8/8/3q4/8/8/4N3/4RK2 w - - 0 1"
    lines = [
        line(fen, "Nc3+ Kd7 Nxd5 Kd6 Ne3 Ke5", WIN, cp=900),
        line(fen, "Kf2 Qd2 Kf3 Kd7", EVEN),
    ]
    analysis = run(fen, "Nc3+", lines, multipv=2)
    discovery = claim(analysis, "discovery_v1")
    assert discovery.verdict.status is S and _passed(analysis, "discovery_v1")
    mechanism = finding(discovery, MechanismFinding)
    assert mechanism.actor.square == "e1"  # the slider; the blocker took the queen
    assert status(analysis, "skewer_v1") is R and status(analysis, "fork_v1") is R


# -- removed_defender_v1, newly_unsafe_v1, left_en_prise_v1 (R2-D §3.8–§3.8b) ------------------


def test_a_removed_defender_explains_the_loss() -> None:
    fen = "4k3/8/5b2/8/3N4/2P5/8/4K3 w - - 0 1"
    analysis = _loss(fen, "c4", "c4 Bxd4 Kd2 Kd7 Kd3 Bf6", "Kd2 Kd7 Kd3 Kd6")
    removed = claim(analysis, "removed_defender_v1")
    assert removed.verdict.status is S and _passed(analysis, "removed_defender_v1")
    defence = finding(removed, DefenceFinding)
    assert (defence.defender.square, defence.defended.square) == ("c3", "d4")
    assert defence.reason == "defender_moved"
    assert removed.verdict.scope.basis.value == "exact"
    assert _edge(analysis, "removed_defender_v1", "material_loss_v1") >= {RelationKind.EXPLAINS}
    assert RelationKind.CAUSES not in {r.kind for r in analysis.relations}  # E8
    # the knight was safe at P and did not move: not newly unsafe (rule 4), not left en prise
    assert status(analysis, "newly_unsafe_v1") is R
    assert status(analysis, "left_en_prise_v1") is None


def test_newly_unsafe_moved_into_attack() -> None:
    # R2-D §3.8a: the defended queen is attacked by a pawn
    fen = "4k3/8/8/4p3/8/2P5/8/3QK3 w - - 0 1"
    analysis = _loss(fen, "Qd4", "Qd4 exd4 cxd4 Kd7 Kd2 Kd6", "Qd5 Ke7 Kf2 Kf6")
    unsafe = claim(analysis, "newly_unsafe_v1")
    assert unsafe.verdict.status is S and _passed(analysis, "newly_unsafe_v1")
    assert finding(unsafe, HangingFinding).kind is HangingKind.MOVED_INTO_ATTACK
    assert status(analysis, "left_en_prise_v1") is None  # the queen moved


def test_left_en_prise_against_the_best_line() -> None:
    # R2-D §3.8b: the queen is defended by c3 but attacked by a pawn
    fen = "4k3/8/8/4p3/3Q4/2P5/8/4K3 w - - 0 1"
    analysis = _loss(fen, "Kf2", "Kf2 exd4 cxd4 Kd7 Ke3 Kd6", "Qd5 Ke7 Kf2 Kf6")
    left = claim(analysis, "left_en_prise_v1")
    assert left.verdict.status is S and _passed(analysis, "left_en_prise_v1")
    assert finding(left, HangingFinding).kind is HangingKind.LEFT
    assert {ref.rank for ref in left.verdict.scope.searches} == {1}
    assert status(analysis, "newly_unsafe_v1") is None  # unsafe at P and not moved


def test_left_en_prise_is_refuted_when_the_best_line_loses_it_too() -> None:
    fen = "4k3/8/8/4p3/3Q4/2P5/8/4K3 w - - 0 1"
    best = "Kd2 exd4 cxd4 Kd7 Kd3 Kd6"  # also loses the queen, but stands better elsewhere
    lp = "Kf2 exd4 cxd4 Kd7 Ke3 Kd6"
    lines = [line(fen, best, EVEN), line(fen, lp, LOST, cp=-500)]
    analysis = run(fen, "Kf2", lines, multipv=2)
    assert status(analysis, "material_loss_v1") is R  # the same loss on both lines
    assert status(analysis, "left_en_prise_v1") is None  # no SUPPORTED loss to build on


def test_a_piece_that_leaves_and_returns_before_the_capture_is_only_associated() -> None:
    # review 5 B2: the queen leaves d4 and comes back; the capture is not the threat it left
    fen = "4k3/8/8/4p3/3Q4/2P5/8/4K3 w - - 0 1"
    lp = "Kf2 Kf7 Qa4 Kf6 Qd4 exd4 cxd4 Ke6 Ke3 Kd5"
    analysis = _loss(fen, "Kf2", lp, "Qd5 Ke7 Kf2 Kf6")
    assert status(analysis, "left_en_prise_v1") is S
    assert not _passed(analysis, "left_en_prise_v1")
    assert _edge(analysis, "left_en_prise_v1", "material_loss_v1") >= {RelationKind.ASSOCIATED_WITH}


def test_a_line_opened_onto_a_piece_by_the_played_move() -> None:
    # R2-D §3.8a rule 3: the bishop leaves the d-file; the rook now attacks the knight
    fen = "3rk3/8/8/3B4/8/8/3N4/6K1 w - - 0 1"
    analysis = _loss(fen, "Bf3", "Bf3 Rxd2 Bb7 Ke7 Kf1 Kd6", "Nf3 Ke7 Kf2 Kd6")
    unsafe = claim(analysis, "newly_unsafe_v1")
    assert finding(unsafe, HangingFinding).kind is HangingKind.LINE_OPENED
    assert _passed(analysis, "newly_unsafe_v1")


def test_a_defence_blocked_by_the_played_move() -> None:
    # the bishop steps between the defending rook and the knight it defended
    fen = "4r2k/8/8/8/8/1B6/R3N3/6K1 w - - 0 1"
    analysis = _loss(fen, "Bc2", "Bc2 Rxe2 Kf1 Re7 Kf2 Kg7", "Kf2 Kg7 Kf3 Kg6")
    removed = claim(analysis, "removed_defender_v1")
    assert finding(removed, DefenceFinding).reason == "line_blocked"
    assert _passed(analysis, "removed_defender_v1")


def test_a_pin_released_and_renewed_by_another_piece_is_the_second_pin() -> None:
    # R2b review B2: 1.Ne4 walks into the e8 rook's pin, which ends with …Rf8; the a7 rook pins
    # the knight again with …Re7 and the pawn takes it — the capture goes through the second pin
    fen = "4r1k1/r4p2/8/8/8/6N1/P7/4K3 w - - 0 1"
    lp = "Ne4 Rf8 a3 Re7 a4 f5 a5 fxe4 a6 Kg7"
    analysis = _loss(fen, "Ne4", lp, "Kd2 Kh7 Ne2 Kg6")
    pin = claim(analysis, "pin_v1")
    assert pin.verdict.status is S and _passed(analysis, "pin_v1")
    mechanism = finding(pin, MechanismFinding)
    assert mechanism.actor.square == "e7" and not mechanism.walked_into


def test_a_piece_moving_from_one_attacked_square_to_another() -> None:
    fen = "4k3/8/8/4p3/3Q4/8/8/4K3 w - - 0 1"
    analysis = _loss(fen, "Qf4", "Qf4 exf4 Kd2 Kd7 Kd3 Kd6", "Qd5 Ke7 Kd2 Kf6")
    unsafe = claim(analysis, "newly_unsafe_v1")
    assert finding(unsafe, HangingFinding).kind is HangingKind.MOVED_INTO_ATTACK
    assert _passed(analysis, "newly_unsafe_v1")
    assert status(analysis, "left_en_prise_v1") is None  # it moved


def test_a_castling_rook_ends_a_defence_by_moving() -> None:
    # R2-D §1.1 (integrated N2): O-O moves the h1 rook off the h-file, which defended h5
    fen = "4b1k1/8/8/7N/8/8/8/4K2R w K - 0 1"
    analysis = _loss(fen, "O-O", "O-O Bxh5 Kg2 Kg7 Kg3 Kg6", "Nf4 Kf7 Kf2 Ke7")
    removed = claim(analysis, "removed_defender_v1")
    defence = finding(removed, DefenceFinding)
    assert (defence.defender.square, defence.reason) == ("h1", "defender_moved")
    assert _passed(analysis, "removed_defender_v1")
