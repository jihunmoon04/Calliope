"""Catalogue v1 sacrifice claims (R2-D §3.11, §8.6g, §8.7, §8.7a; E10: no BRILLIANT in v1)."""

from __future__ import annotations

from story import I, R, S, claim, finding, line, run, status, table

from calliope.facts import Color, EngineLineId
from calliope.reasoning.catalogue.sacrifice import exchange, fate
from calliope.reasoning.findings import (
    CompensationFinding,
    CompensationKind,
    Fate,
    OfferFinding,
)
from calliope.reasoning.labels import LabelKind
from calliope.reasoning.lines import read_line
from calliope.reasoning.refs import LineSegment

MATED, WON, EVEN = (1000, 0, 0), (900, 100, 0), (300, 600, 100)

# 1.Qe8+ Rxe8 2.Rxe8#: the queen given up at ply 2 for a mate
BACK = "r5k1/5ppp/8/8/8/8/4QPPP/4R1K1 w - - 0 1"
OFFER = "Qe8+ Rxe8 Rxe8#"


def _offer(*alternatives, lp: str = OFFER, score=None, multipv: int = 3):
    lines = [line(BACK, lp, MATED, **(score or {"mate": 2})), *alternatives]
    return run(BACK, "Qe8+", lines, multipv=multipv)


def test_a_queen_offer_with_a_mate_return() -> None:
    analysis = _offer(line(BACK, "h3 h6 Qe3 Kh7", EVEN, cp=50), line(BACK, "g3 h6 Kg2 Kh7", EVEN))
    offer = claim(analysis, "sacrifice_offer_v1")
    assert offer.verdict.status is S
    found = finding(offer, OfferFinding)
    assert found.amount.points == 9 and found.event.ply == 2
    assert [f for _ref, f in found.keeping] == [Fate.PRESERVED, Fate.PRESERVED]
    assert set(offer.verdict.scope.witnesses) == {"h2h3", "g2g3"}  # keeping alternatives
    sound = claim(analysis, "sacrifice_sound_v1")
    assert sound.verdict.status is S
    assert finding(sound, CompensationFinding) == CompensationFinding(CompensationKind.ENGINE, 2000)
    compensated = claim(analysis, "sacrifice_compensated_v1")
    assert finding(compensated, CompensationFinding).kind is CompensationKind.MATE
    assert compensated.hypothesis.premises[0].claim == offer.id
    assert LabelKind.BRILLIANT not in {label.kind for label in analysis.labels}  # E10


def test_a_mate_return_as_fast_as_a_keeping_mate_is_refuted() -> None:
    keeping = line(BACK, "Qe7 h6 Qe8+ Kh7", MATED, mate=2)  # the queen is never taken
    analysis = _offer(keeping, line(BACK, "g3 h6 Kg2 Kh7", EVEN))
    assert status(analysis, "sacrifice_offer_v1") is S
    assert status(analysis, "sacrifice_compensated_v1") is R


def test_a_forced_loss_is_no_offer() -> None:
    # R2-D §3.11: every move loses the rook to the knight
    fen = "4k3/pp3ppp/8/8/8/8/PPn2PPP/R3K3 w - - 0 1"
    lines = [
        line(fen, "Kd2 Nxa1 Kc1 Ke7 Kb1 Kd6", (0, 300, 700), cp=-500),
        line(fen, "Kd1 Nxa1 Kc1 Ke7 Kb1 Kd6", (0, 250, 750), cp=-510),
        line(fen, "Ke2 Nxa1 Kd2 Ke7 Kc1 Kd6", (0, 200, 800), cp=-520),
    ]
    analysis = run(fen, "Kd2", lines)
    assert status(analysis, "sacrifice_offer_v1") is R  # rule 5
    assert status(analysis, "sacrifice_sound_v1") is None
    assert analysis.labels == ()


def test_a_line_cut_right_after_the_capture_is_inconclusive() -> None:
    # review 5 B1: the candidate is open, never refuted
    analysis = _offer(
        line(BACK, "h3 h6 Qe3 Kh7", EVEN, cp=50),
        lp="Qe8+ Rxe8",
        score={"cp": 900},
    )
    assert table(analysis)["sacrifice_offer_v1"] == (I, "LINE_TOO_SHORT")


def test_mated_alternatives_keep_nothing() -> None:
    mated = [
        line(BACK, "h3 h6 Qe3 Kh7", (0, 0, 1000), mate=-3),
        line(BACK, "g3 h6 Kg2 Kh7", (0, 0, 1000), mate=-3),
    ]
    analysis = _offer(*mated)
    assert status(analysis, "sacrifice_offer_v1") is R  # every other line is GIVEN_UP


def test_an_alternative_too_short_to_show_the_fate_is_undecided() -> None:
    # R2-D §8.6g: a mate score on an alternative cut before ply j + 1
    short = [line(BACK, "h3", WON, mate=3), line(BACK, "g3", WON, mate=4)]
    analysis = _offer(*short)
    assert table(analysis)["sacrifice_offer_v1"] == (I, "LINE_TOO_SHORT")  # rule 6


def test_a_knight_lost_everywhere_and_a_real_queen_offer_at_ply_four() -> None:
    fen = "r5k1/5ppp/8/2p5/3N4/8/4QPPP/4R1K1 w - - 0 1"
    lines = [
        line(fen, "h3 cxd4 Qe8+ Rxe8 Rxe8#", MATED, mate=3),
        line(fen, "h4 cxd4 Qe3 h6 Qxd4 Kh8", EVEN, cp=-150),
        line(fen, "g3 cxd4 Kg2 h6 Qd3 Kh8", EVEN, cp=-160),
    ]
    analysis = run(fen, "h3", lines)
    offer = claim(analysis, "sacrifice_offer_v1")
    assert offer.verdict.status is S
    found = finding(offer, OfferFinding)
    assert found.event.ply == 4 and found.amount.points == 12  # the knight, then the queen


def test_a_won_position_keeps_its_expectation_but_the_keeping_lines_end_better() -> None:
    # WDL saturates: the rook is given up at no cost in E, so only `sound` holds (R2-D §8.7)
    fen = "7k/6p1/8/8/8/8/Q7/K5R1 w - - 0 1"
    lines = [
        line(fen, "Rxg7 Kxg7 Qb2+ Kg8 Qb8+ Kf7", MATED, cp=2000),
        line(fen, "Qb1 Kg8 Qb8+ Kf7 Qb3+ Kf6", MATED, cp=2000),
        line(fen, "Qd2 Kg8 Qd8+ Kf7 Qd7+ Kf6", MATED, cp=1990),
    ]
    analysis = run(fen, "Rxg7", lines)
    assert status(analysis, "sacrifice_offer_v1") is S
    assert status(analysis, "sacrifice_sound_v1") is S
    assert status(analysis, "sacrifice_compensated_v1") is R  # the keeping lines end with more


def test_a_material_return_strictly_above_the_keeping_lines() -> None:
    # 1.Re8+ Kxe8 2.Nc7+ Kd7 3.Nxa8: a rook for the queen
    fen = "q4k2/8/8/1N6/8/8/5PPP/4R1K1 w - - 0 1"
    lines = [
        line(fen, "Re8+ Kxe8 Nc7+ Kd7 Nxa8 Kc6 Kf1 Kb7", MATED, cp=900),
        line(fen, "h3 Qa1 Rxa1 Ke7 Kh2 Kd7", WON, cp=500),
        line(fen, "Kf1 Qa6 Re3 Kg7 Kg1 Kf6", EVEN, cp=0),
    ]
    analysis = run(fen, "Re8+", lines)
    assert status(analysis, "sacrifice_offer_v1") is S
    compensated = claim(analysis, "sacrifice_compensated_v1")
    assert compensated.verdict.status is R  # h3 Qa1?? wins the queen outright: +9 > +4
    keeping = [
        lines[0],
        line(fen, "Kf1 Qa6 Re3 Kg7 Kg1 Kf6", WON, cp=0),
        line(fen, "g3 Qa4 Re3 Kg7 Kg2 Kf6", WON, cp=-10),
    ]
    analysis = run(fen, "Re8+", keeping)
    compensated = claim(analysis, "sacrifice_compensated_v1")
    assert compensated.verdict.status is S
    assert finding(compensated, CompensationFinding).kind is CompensationKind.MATERIAL_RETURN


def test_an_open_keeping_line_leaves_the_return_undecided() -> None:
    # a keeping line whose window ends on a capture is OPEN: never a refutation (rule 5)
    fen = "q4k2/7p/8/1N6/8/8/5PPP/4R1K1 w - - 0 1"
    lines = [
        line(fen, "Re8+ Kxe8 Nc7+ Kd7 Nxa8 Kc6 Kf1 Kb7", MATED, cp=900),
        line(fen, "Re3 Kg7 Re7+ Kg6 Rxh7", WON, cp=0),
    ]
    analysis = run(fen, "Re8+", lines, multipv=2)
    assert status(analysis, "sacrifice_offer_v1") is S
    assert table(analysis)["sacrifice_compensated_v1"] == (I, "LINE_TOO_SHORT")


# -- the fate of a given-up piece, read from the moves (R2-D §3.11 steps 1–4) ------------------

TRADE = "r2qk2r/ppp2ppp/8/8/2B5/8/PPP2PPP/3Q1RK1 w - - 0 1"
OTHER = "h3 h6 Kh2 a6"


def _fates(fen: str, alternative: str, piece_square: str, j: int, b_j: int, other: str):
    lines = [line(fen, alternative, EVEN), line(fen, other, EVEN)]
    analysis = run(fen, alternative.split()[0], lines, multipv=2)
    view = analysis.tree.view(analysis.rev)
    p = analysis.round_zero.subject.parent
    search = analysis.round_zero.judgements[0].search.search_id
    line_id = EngineLineId(p, search, 1)
    record = view.line(line_id)
    read = read_line(view, LineSegment(line_id, 0, len(record.nodes) - 1), Color.WHITE)
    piece = view.node(p).piece_at(piece_square)
    return read, fate(read, piece, j, b_j, Color.WHITE)


def test_an_in_between_check_does_not_split_a_trade() -> None:
    # re-check C1: 1.a3 Qxd1 2.Bb5+ Ke7 3.Rxd1 — the recapture of the capturer at c + 3
    read, result = _fates(TRADE, "a3 Qxd1 Bb5+ Ke7 Rxd1 a6 Bc4 h6", "d1", 2, -2, OTHER)
    assert result is Fate.TRADED
    assert exchange(read, 2, Color.WHITE) == 0


def test_a_quiet_in_between_move_does_not_split_a_trade() -> None:
    _read, result = _fates(TRADE, "a3 Qxd1 Bd3 h6 Rxd1 a6 Kf1 a5", "d1", 2, -2, OTHER)
    assert result is Fate.TRADED


def test_a_queen_lost_for_nothing_is_given_up() -> None:
    _read, result = _fates(TRADE, "a3 Qxd1 Bd3 h6 Kh1 a6 h3 a5", "d1", 2, -2, OTHER)
    assert result is Fate.GIVEN_UP


def test_an_exchange_running_at_the_window_end_is_undecided() -> None:
    _read, result = _fates(TRADE, "a3 Qxd1 Bb5+", "d1", 2, -2, OTHER)
    assert result is Fate.UNDECIDED


def test_saving_one_forked_rook_and_losing_the_other_keeps_nothing() -> None:
    # re-check C2: the knight forks both rooks; the a1 rook escapes with check, e1 is lost
    fen = "3k4/8/8/8/8/8/2n2PPP/R3R1K1 w - - 0 1"
    _read, result = _fates(fen, "Ra8+ Kd7 h3 Nxe1 Kf1 Nd3", "a1", 2, -5, "h3 Kd7 Kh2 Kd6")
    assert result is Fate.GIVEN_UP  # an exchange netting −5 ≤ b_j elsewhere on the line


def test_a_mate_return_over_an_undecided_keeping_line_is_inconclusive() -> None:
    # R2b review B1: the keeping line ends on a capture (OPEN); "strictly above" needs its outcome
    keeping = line(BACK, "Qe7 h6 Qxf7+", WON, cp=600)
    analysis = _offer(keeping, line(BACK, "g3 h6 Kg2 Kh7", EVEN))
    found = finding(claim(analysis, "sacrifice_offer_v1"), OfferFinding)
    assert [f for _ref, f in found.keeping] == [Fate.PRESERVED, Fate.PRESERVED]
    assert table(analysis)["sacrifice_compensated_v1"] == (I, "LINE_TOO_SHORT")


def test_a_capture_that_ends_the_game_is_evaluated_at_once() -> None:
    # R2-D §3.11: …Qxe1# at ply 2 is evaluated with b_3 = b_2, never left open
    fen = "6k1/5ppp/8/8/8/8/4qPPP/4R1K1 w - - 0 1"
    lines = [
        line(fen, "Kh1 Qxe1#", (0, 0, 1000), mate=-1),
        line(fen, "Rxe2 h6 Re3 Kh7", MATED, cp=900),
    ]
    analysis = run(fen, "Kh1", lines, multipv=2)
    offer = claim(analysis, "sacrifice_offer_v1")
    assert offer.verdict.status is S  # by the rules: the rook is given up, Rxe2 keeps it
    assert finding(offer, OfferFinding).event.ply == 2
    assert status(analysis, "sacrifice_sound_v1") is R  # mated: no soundness
    assert status(analysis, "sacrifice_compensated_v1") is R
