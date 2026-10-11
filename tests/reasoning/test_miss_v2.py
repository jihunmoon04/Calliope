"""MISS v2 (MV-D, test obligations §6): `missed_gain_v1` and the provisional rule `miss_p2`."""

from __future__ import annotations

from dataclasses import replace

from story import R, S, after, claim, finding, line, run, status

from calliope.facts.engine_work import EngineWork
from calliope.reasoning import GradingSpec
from calliope.reasoning.findings import MissedGainFinding
from calliope.reasoning.labels import MISS_LOSS, MISS_OPPORTUNITY, LabelKind, label_v2
from calliope.reasoning.observer import JudgementStatus

G = "4k3/8/8/8/8/8/P7/4K3 b - - 0 1"  # quiet: no line wins material
P = after(G, "Kd7")


def wdl(e: int) -> tuple[int, int, int]:
    """A WDL whose expected points are `e` (1/2000) for the side to move."""

    return (0, e, 1000 - e) if e <= 1000 else (e - 1000, 2000 - e, 0)


def scenario(previous_loss: int, loss: int, **kwargs):
    """The opponent's Kd7 loses `previous_loss` at G; the target a3 loses `loss` at P."""

    at_g = [line(G, "Kf7 Kd2", wdl(1000)), line(G, "Kd7 a3", wdl(1000 - previous_loss))]
    at_p = [line(P, "Kd2 Kc6", wdl(1000)), line(P, "a3 Kc6", wdl(1000 - loss))]
    return run(G, "a3", at_p, before="Kd7", table={G: at_g}, multipv=2, **kwargs)


def kinds(analysis) -> list[LabelKind]:
    return [label.kind for label in analysis.labels]


def test_miss_without_material() -> None:
    analysis = scenario(MISS_OPPORTUNITY, MISS_LOSS)
    gain = claim(analysis, "missed_gain_v1")
    assert gain.verdict.status is S
    assert finding(gain, MissedGainFinding) == MissedGainFinding(
        finding(gain, MissedGainFinding).best, MISS_LOSS
    )  # best and loss only: nothing from S_G (review B1)
    assert gain.verdict.scope.witnesses == ("e1d2",)  # rank 1 of S, not the played move
    assert gain.verdict.scope.quantifier.value == "exists_alternative"
    (label,) = analysis.labels
    assert (label.kind, label.rule, label.provisional, label.grounds) == (
        LabelKind.MISS, "miss_p2", True, (gain.id,),
    )  # fmt: skip
    assert status(analysis, "better_move_v1") is not S  # the best line wins nothing


def test_the_thresholds() -> None:
    below_a = scenario(MISS_OPPORTUNITY - 1, MISS_LOSS)
    assert status(below_a, "missed_gain_v1") is S and kinds(below_a) == []
    below_b = scenario(MISS_OPPORTUNITY, MISS_LOSS - 1)
    assert status(below_b, "missed_gain_v1") is None and kinds(below_b) == []
    # the claim does not read the previous move (review B1)
    fine = scenario(0, 300)
    assert status(fine, "missed_gain_v1") is S and kinds(fine) == []


def test_no_miss_without_a_decided_previous_judgement() -> None:
    analysis = scenario(MISS_OPPORTUNITY, MISS_LOSS)
    target, previous = analysis.round_zero.judgements
    undecided = replace(previous, status=JudgementStatus.INCONCLUSIVE)
    view = analysis.tree.view()
    assert label_v2(view, (target, undecided), analysis.claims) == ()
    assert label_v2(view, (target,), analysis.claims) == ()  # no previous move
    first = run(P, "a3", [line(P, "Kd2 Kc6", wdl(1000)), line(P, "a3 Kc6", wdl(600))], multipv=2)
    assert status(first, "missed_gain_v1") is S and kinds(first) == []


def test_a_forced_target_is_never_a_miss() -> None:
    g = "k7/8/8/8/8/8/7q/K7 b - - 0 1"  # Qb2+ gives the queen away; Kxb2 is the only move
    p = after(g, "Qb2+")
    at_g = [line(g, "Kb7 Kb1", wdl(2000)), line(g, "Qb2+ Kxb2", wdl(0))]
    analysis = run(g, "Kxb2", [line(p, "Kxb2 Kb7", wdl(2000))], before="Qb2+", table={g: at_g},
                   multipv=2)  # fmt: skip
    assert kinds(analysis) == [LabelKind.FORCED]


def test_a_rank_one_pv_left_unattached_keeps_the_claim(monkeypatch) -> None:
    """Review B2: the claim needs S's scores, not rank 1's nodes."""

    attach, passed, cut = EngineWork._attach_line, EngineWork._deadline_passed, {"now": False}

    def attach_line(self, anchor, search, rank, pv):  # a deadline cut of rank 1 at P only
        cut["now"] = rank == 1 and pv[0] == "e1d2"
        try:
            return attach(self, anchor, search, rank, pv)
        finally:
            cut["now"] = False

    monkeypatch.setattr(EngineWork, "_attach_line", attach_line)
    monkeypatch.setattr(EngineWork, "_deadline_passed", lambda self: cut["now"] or passed(self))
    analysis = scenario(MISS_OPPORTUNITY, MISS_LOSS)
    target = analysis.round_zero.judgements[0]
    assert analysis.tree.view().child(target.subject.parent, "e1d2") is None  # never attached
    assert status(analysis, "missed_gain_v1") is S
    assert kinds(analysis) == [LabelKind.MISS]


def test_the_same_thresholds_under_an_explicit_scale() -> None:
    """Review N1: quality_v1 is the scenarios' grading; quality_v2 with c = 1000 is checked here."""

    at_g = [line(G, "Kf7 Kd2", wdl(1000), cp=0), line(G, "Kd7 a3", wdl(1000), cp=-300)]
    at_p = [line(P, "Kd2 Kc6", wdl(1000), cp=300), line(P, "a3 Kc6", wdl(1000), cp=0)]
    analysis = run(G, "a3", at_p, before="Kd7", table={G: at_g}, multipv=2,
                   grading=GradingSpec(scale=1000))  # fmt: skip
    target, previous = analysis.round_zero.judgements
    assert previous.loss >= MISS_OPPORTUNITY and target.loss >= MISS_LOSS  # 332 and 332
    assert kinds(analysis) == [LabelKind.MISS]
    same_wdl = scenario(0, 0)  # under quality_v1 the equal WDLs make no loss
    assert status(same_wdl, "missed_gain_v1") is None and status(same_wdl, "better_move_v1") in (
        None, R,
    )  # fmt: skip


def test_an_open_exchange_still_makes_the_miss() -> None:
    """9.Bxe7 of the 1700 game (Q3 §6.1): `better_move_v1` cannot decide, `miss_p2` can."""

    g = "r1bqkb1r/pp2np1p/2n3p1/2pp2B1/8/P1NP4/BPP2PPP/R2QK1NR b KQkq - 1 8"
    p = after(g, "h6")
    at_g = [line(g, "Qd6 Nf3", wdl(1050)), line(g, "h6 Bf6", wdl(750))]  # 8…h6 loses 300
    at_p = [
        line(p, "Bf6 Rg8 Bxe7 Bxe7 Qe2 Be6 O-O-O", wdl(1230)),
        line(p, "Bxe7", wdl(910)),  # the PV stops inside the exchange
    ]
    analysis = run(g, "Bxe7", at_p, before="h6", table={g: at_g}, multipv=2)
    better = claim(analysis, "better_move_v1").verdict
    assert (better.status.value, better.reason) == ("inconclusive", "LINE_TOO_SHORT")
    (label,) = analysis.labels
    assert (label.kind, label.rule) == (LabelKind.MISS, "miss_p2")
    assert label.grounds == (claim(analysis, "missed_gain_v1").id,)


def test_a_miss_p2_label_round_trips() -> None:
    from calliope.facts.storage import _Decoder
    from calliope.reasoning.encoding import encoded, reasoning_registry
    from calliope.reasoning.labels import Label

    (label,) = scenario(MISS_OPPORTUNITY, MISS_LOSS).labels
    fields = ["kind", "subject", "grounds", "policy", "rule", "provisional"]
    decoded = _Decoder(reasoning_registry(), [["Label", "", fields]])(encoded(label))
    assert decoded == label and isinstance(decoded, Label) and decoded.rule == "miss_p2"
