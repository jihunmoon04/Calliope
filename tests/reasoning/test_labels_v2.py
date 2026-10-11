"""`label_v2` (LV-D, test obligations §10): FORCED, GREAT without routine replies, `rescue_v1`,
the provisional BRILLIANT from `piece_offer_v1` and `capture_holds_v1`, and the `Label` record."""

from __future__ import annotations

from dataclasses import replace

from story import I, R, S, after, claim, finding, line, run, status

from calliope.facts.engine_work import EngineWork
from calliope.facts.storage import _Decoder
from calliope.reasoning import ReasoningBudget
from calliope.reasoning.encoding import encoded, reasoning_registry
from calliope.reasoning.findings import PieceOfferFinding
from calliope.reasoning.labels import Label, LabelKind, label_v1, label_v2, sound_sacrifice
from calliope.reasoning.needs import FamilyNeed, LineNeed
from calliope.reasoning.observer import JudgementStatus

WIN, EVEN, LOSS = (1000, 0, 0), (300, 600, 100), (0, 0, 1000)  # 2000, 1200, 0 for the mover
DRAW = (0, 1000, 0)  # 1000


def kinds(analysis) -> list[LabelKind]:
    return [label.kind for label in analysis.labels]


# -- §10.1 FORCED -------------------------------------------------------------------------------

ONE_MOVE = "k7/8/8/8/8/8/1q6/K7 w - - 0 1"  # Kxb2 is the only legal move


def test_a_single_legal_move_is_forced_even_without_a_decided_judgement() -> None:
    analysis = run(ONE_MOVE, "Kxb2", [line(ONE_MOVE, "Kxb2 Ka7", DRAW)], multipv=1)
    (label,) = analysis.labels
    assert (label.kind, label.grounds, label.rule, label.provisional) == (
        LabelKind.FORCED, (), "forced_v1", False,
    )  # fmt: skip
    undecided = replace(analysis.round_zero.judgements[0], status=JudgementStatus.INCONCLUSIVE)
    view = analysis.tree.view()
    assert [lb.kind for lb in label_v2(view, (undecided,), analysis.claims)] == [LabelKind.FORCED]


# -- §10.2 GREAT --------------------------------------------------------------------------------

QUIET = "4k3/8/8/8/8/8/P7/4K3 w - - 0 1"


def test_a_quiet_only_move_is_a_provisional_great() -> None:
    analysis = run(
        QUIET, "a3", [line(QUIET, "a3 Kd7", WIN), line(QUIET, "Kd2 Kd7", DRAW)], multipv=2
    )
    only = claim(analysis, "only_move_v1")
    (label,) = analysis.labels
    assert (label.kind, label.grounds, label.rule, label.provisional) == (
        LabelKind.GREAT, (only.id,), "great_p2", True,
    )  # fmt: skip
    assert LabelKind.FORCED not in kinds(analysis)  # two legal moves or more


def test_great_is_withheld_on_routine_only_moves() -> None:
    check = "4k3/8/8/8/8/8/4r3/4K3 w - - 0 1"  # in check at P
    a = run(check, "Kxe2", [line(check, "Kxe2 Kd7", WIN), line(check, "Kd1 Rb2", DRAW)], multipv=2)
    assert status(a, "only_move_v1") is S and LabelKind.GREAT not in kinds(a)
    mate = "6k1/5ppp/8/8/8/8/8/4R1K1 w - - 0 1"  # Re8# mates in one
    b = run(mate, "Re8#", [line(mate, "Re8#", WIN, mate=1), line(mate, "Kf1 Kf8", DRAW)], multipv=2)
    assert status(b, "only_move_v1") is S and LabelKind.GREAT not in kinds(b)
    retreat = "4k3/8/8/3p4/4N3/8/8/4K3 w - - 0 1"  # the knight on e4 is attacked by d5
    c = run(retreat, "Nc3", [line(retreat, "Nc3 Kd7", WIN), line(retreat, "Kd2 dxe4", DRAW)],
            multipv=2)  # fmt: skip
    assert status(c, "only_move_v1") is S and status(c, "rescue_v1") is S
    assert LabelKind.GREAT not in kinds(c)


def test_great_is_withheld_on_a_recapture() -> None:
    fen = "4k3/8/5n2/8/4P3/2N5/8/4K3 b - - 0 1"
    p = after(fen, "Nxe4")
    a = run(fen, "Nxe4", [line(p, "Nxe4 Kd7", WIN), line(p, "Kf1 Nxc3", DRAW)], before="Nxe4",
            multipv=2)  # fmt: skip
    assert status(a, "only_move_v1") is S and LabelKind.GREAT not in kinds(a)


def test_great_is_kept_on_a_best_capture_that_is_not_a_recapture() -> None:
    fen = "4k3/8/5n2/8/8/8/8/3RK3 b - - 0 1"
    p = after(fen, "Nd5")  # a quiet knight move: Rxd5 takes, but retakes nothing
    a = run(fen, "Rxd5", [line(p, "Rxd5 Ke7", WIN), line(p, "Kf2 Ke7", DRAW)], before="Nd5",
            multipv=2)  # fmt: skip
    assert status(a, "rescue_v1") is None  # the rook had no attacker at P
    (label,) = a.labels
    assert (label.kind, label.rule) == (LabelKind.GREAT, "great_p2")


def test_an_undecided_rescue_withholds_great() -> None:
    """LV1 review B2: a rescue not ruled out is not read as "no rescue"."""

    retreat = "4k3/8/8/3p4/4N3/8/8/4K3 w - - 0 1"
    c = run(retreat, "Nc3", [line(retreat, "Nc3 Kd7", WIN), line(retreat, "Kd2 dxe4", DRAW)],
            multipv=2, budget=ReasoningBudget(max_ensure_nodes=0))  # fmt: skip
    rescue = claim(c, "rescue_v1").verdict
    assert status(c, "only_move_v1") is S and (rescue.status, rescue.reason) == (I, "BUDGET")
    assert c.labels == ()


# -- §10.3 rescue_v1 ----------------------------------------------------------------------------


def test_rescue_needs_a_piece_en_prise_that_ends_safe() -> None:
    defended = "4r1k1/8/8/8/4N3/3P4/8/6K1 w - - 0 1"  # Rxe4 dxe4: not en prise
    a = run(defended, "Nc3", [line(defended, "Nc3 Kf8", WIN), line(defended, "Kf2 Kf8", DRAW)],
            multipv=2)  # fmt: skip
    assert status(a, "rescue_v1") is R
    still = "4k3/8/1p6/3p4/4N3/8/8/4K3 w - - 0 1"  # Nc5 runs into b6
    b = run(still, "Nc5", [line(still, "Nc5 Kd8", WIN), line(still, "Nc3 Kd8", DRAW)], multipv=2)
    assert status(b, "rescue_v1") is R


# -- §10.4 piece_offer_v1 and capture_holds_v1 --------------------------------------------------

BACK = "r5k1/5ppp/8/8/8/8/4QPPP/4R1K1 w - - 0 1"  # 1.Qe8+ Rxe8 2.Rxe8#


def _back(*alternatives, table=None, budget=None):
    lines = [line(BACK, "Qe8+ Rxe8 Rxe8#", WIN, mate=2), *alternatives]
    return run(BACK, "Qe8+", lines, multipv=1 + len(alternatives), table=table, budget=budget)


def test_the_queen_sacrifice_is_brilliant_in_three_rounds() -> None:
    analysis = _back(line(BACK, "h3 h6 Qe3 Kh7", EVEN, cp=50))
    offer, holds = claim(analysis, "piece_offer_v1"), claim(analysis, "capture_holds_v1")
    assert offer.verdict.status is S and holds.verdict.status is S
    assert sound_sacrifice(analysis.claims, offer.hypothesis.subject) == (offer, holds)
    assert analysis.labels[0].grounds == (offer.id, holds.id)
    assert analysis.labels[0].rule == "brilliant_p2"
    assert holds.hypothesis.premises[0].claim == offer.id
    assert holds.hypothesis.premises[0].search.value == "any_search"
    assert offer.verdict.scope.policies[-1] == "see_v1"
    assert kinds(analysis) == [LabelKind.BRILLIANT]
    assert len(analysis.rounds) == 2  # exchange facts, then the survey after the capture


def test_the_capture_branch_must_hold() -> None:
    x = after(BACK, "Qe8+ Rxe8")
    table = {x: [line(x, "Rxe8#", LOSS, cp=-900)]}  # the engine, scripted, says White is lost
    analysis = _back(line(BACK, "h3 h6 Qe3 Kh7", EVEN, cp=50), table=table)
    offer = claim(analysis, "piece_offer_v1")
    assert offer.verdict.status is S  # an offer, not a sacrifice (LV1 review B1)
    assert status(analysis, "capture_holds_v1") is R
    assert sound_sacrifice(analysis.claims, offer.hypothesis.subject) is None
    assert LabelKind.BRILLIANT not in kinds(analysis)


def test_no_sacrifice_when_a_quiet_line_already_wins() -> None:
    analysis = _back(line(BACK, "h3 h6 Qe3 Kh7", WIN, cp=900))  # 2000 ≥ 1700
    assert status(analysis, "piece_offer_v1") is R


def test_no_sacrifice_without_the_capture_survey() -> None:
    analysis = _back(line(BACK, "h3 h6 Qe3 Kh7", EVEN, cp=50),
                     budget=ReasoningBudget(max_extra_searches=0))  # fmt: skip
    assert status(analysis, "piece_offer_v1") is I
    assert status(analysis, "capture_holds_v1") is None
    assert LabelKind.BRILLIANT not in kinds(analysis)


def test_a_trapped_piece_is_no_sacrifice_even_with_a_capture() -> None:
    fen = "7k/8/8/8/4b2p/p3p3/K7/7N w - - 0 1"  # Nh1 is lost whatever White plays
    analysis = run(fen, "Kxa3", [line(fen, "Kxa3 Bxh1", EVEN), line(fen, "Kb3 Bxh1", EVEN)],
                   multipv=2)  # fmt: skip
    assert status(analysis, "piece_offer_v1") is R


def test_a_piece_left_hanging_by_a_quiet_move_is_no_sacrifice() -> None:
    fen = "4k3/8/1p6/3p4/4N3/8/8/4K3 w - - 0 1"  # e4 already hangs; Nc5 hangs again
    analysis = run(fen, "Nc5", [line(fen, "Nc5 bxc5", EVEN), line(fen, "Nc3 Kd7", EVEN)], multipv=2)
    assert status(analysis, "piece_offer_v1") is R


def test_in_check_created_is_unknown() -> None:
    fen = "4r1k1/8/8/8/8/3B4/8/4K3 w - - 0 1"  # Be4 blocks the check and hangs
    analysis = run(fen, "Be4", [line(fen, "Be4 Rxe4+", EVEN), line(fen, "Kf1 Kg7", EVEN)],
                   multipv=2)  # fmt: skip
    verdict = claim(analysis, "piece_offer_v1").verdict
    assert (verdict.status, verdict.reason) == (I, "NOT_COMPUTED(IN_CHECK)")


def test_in_check_a_capture_passes_step_two() -> None:
    fen = "6k1/8/1Q6/p7/1b6/8/8/4K3 w - - 0 1"  # Bb4+; Qxb4 takes it and hangs to axb4
    x = after(fen, "Qxb4 axb4")
    lines = [line(fen, "Qxb4 axb4 Kd2", EVEN, cp=50), line(fen, "Ke2 Kg7", EVEN, cp=0)]
    analysis = run(fen, "Qxb4", lines, multipv=2, table={x: [line(x, "Kd2 Kg7", EVEN)]})
    offer = claim(analysis, "piece_offer_v1")
    assert offer.verdict.status is S
    assert finding(offer, PieceOfferFinding).created is None  # unknown in check, never 0
    assert finding(offer, PieceOfferFinding).capture
    assert kinds(analysis) == [LabelKind.BRILLIANT]


def test_the_move_must_leave_the_mover_at_least_half_a_point() -> None:
    def at(expected: int):
        played = line(BACK, "Qe8+ Rxe8 Rxe8#", (0, expected, 1000 - expected))
        quiet = line(BACK, "h3 h6 Qe3 Kh7", (0, 990, 10))  # E 990: the loss stays under 100
        return run(BACK, "Qe8+", [played, quiet], multipv=2)

    assert status(at(999), "piece_offer_v1") is None  # E(Lp) < 1000: never proposed
    assert status(at(1000), "piece_offer_v1") is S


def test_a_missing_alternative_child_is_created_then_read(monkeypatch) -> None:
    """LV-D §6.1 (review B1): a line of S cut in round 0 has no child; the claim creates it."""

    cut, attach, passed = (
        {"done": False, "now": False},
        EngineWork._attach_line,
        EngineWork._deadline_passed,
    )

    def attach_line(self, anchor, search, rank, pv):  # a deadline cut of rank 2, once
        cut["now"] = rank == 2 and not cut["done"]
        cut["done"] = cut["done"] or cut["now"]
        try:
            return attach(self, anchor, search, rank, pv)
        finally:
            cut["now"] = False

    monkeypatch.setattr(EngineWork, "_attach_line", attach_line)
    monkeypatch.setattr(EngineWork, "_deadline_passed", lambda self: cut["now"] or passed(self))
    alternative = line(BACK, "h3 h6 Qe3 Kh7", EVEN, cp=50)
    short = _back(alternative)  # three rounds: the survey after the capture never comes
    verdict = claim(short, "piece_offer_v1").verdict
    assert (verdict.status, verdict.reason) == (I, "ROUND_LIMIT")
    assert kinds(short) == [LabelKind.GREAT]  # an undecided offer does not withhold GREAT
    cut["done"] = False
    full = _back(alternative, budget=ReasoningBudget(max_rounds=4))
    first, second, third = (r.admitted for r in full.rounds)
    (create,) = (n for n in first if isinstance(n, LineNeed))
    assert (create.moves, create.expansion.survey, create.expansion.attach_lines) == (
        ("h2h3",), False, False,
    )  # fmt: skip
    assert [type(n) for n in second] == [FamilyNeed]  # the new child's exchange facts
    assert [n.expansion.survey for n in third] == [True]  # the capture survey
    assert kinds(full) == [LabelKind.BRILLIANT]


def test_a_just_promoted_piece_is_not_offered() -> None:
    """`brilliant_p2` (LV-D §15, LV1 review B3): the move gave up a pawn, not a queen."""

    fen = "1r5k/2P5/8/8/8/8/8/7K w - - 0 1"  # c8=Q+ puts the new queen en prise to Rxc8
    x = after(fen, "c8=Q+ Rxc8")
    lines = [line(fen, "c8=Q+ Rxc8 Kg2", EVEN, cp=50), line(fen, "Kg2 Rc8", DRAW)]
    analysis = run(fen, "c8=Q+", lines, multipv=2, table={x: [line(x, "Kg2 Kg7", EVEN)]})
    assert status(analysis, "piece_offer_v1") is R  # step 1: nothing offered
    assert LabelKind.BRILLIANT not in kinds(analysis)


def test_far_from_best_is_never_proposed() -> None:
    lines = [line(BACK, "h3 h6 Qe3 Kh7", WIN, cp=50), line(BACK, "Qe8+ Rxe8 Rxe8#", DRAW)]
    analysis = run(BACK, "Qe8+", lines, multipv=2)
    assert status(analysis, "piece_offer_v1") is None


# -- §10.5 the Label record ---------------------------------------------------------------------


def test_label_v1_records_decode_with_the_new_defaults() -> None:
    analysis = _back(line(BACK, "h3 h6 Qe3 Kh7", EVEN, cp=50))
    old = label_v1(analysis.tree.view(), analysis.round_zero.judgements, analysis.claims)
    assert old and old[0].rule == "" and not old[0].provisional
    value = encoded(old[0])
    value["f"] = value["f"][:4]  # as label_v1 stored it: kind, subject, grounds, policy
    saved = [["Label", "", ["kind", "subject", "grounds", "policy"]]]
    decoded = _Decoder(reasoning_registry(), saved)(value)
    assert decoded == Label(old[0].kind, old[0].subject, old[0].grounds, old[0].policy)
