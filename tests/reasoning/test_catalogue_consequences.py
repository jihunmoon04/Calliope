"""Catalogue v1 consequences, comparisons, functions and labels (R2-D §3.1–§3.6, §3.9–§3.13,
§5.2, §8.1–§8.4, §8.6d, §8.6f, §8.8, §8.9, §8.11).

Every scenario runs the whole analysis with the scripted engine: the lines of S at P (PVs, scores
and WDL from the side to move) are set by the test.
"""

from __future__ import annotations

from dataclasses import replace

from story import I, R, S, after, claim, finding, line, run, status, table, uci

from calliope.facts.search import Bound, RawLine, RawSearch, ScriptedEngine, StoppedBy
from calliope.reasoning import ReasoningBudget
from calliope.reasoning.findings import (
    ComparisonFinding,
    ForcingFinding,
    MateFinding,
    MaterialFinding,
    OutcomeKind,
    PreventsFinding,
    PreventsKind,
)
from calliope.reasoning.hypotheses import RelationKind
from calliope.reasoning.labels import LabelKind
from calliope.reasoning.refs import MoveRef, SearchMoveRef

WIN, EVEN, LOST = (900, 100, 0), (300, 600, 100), (0, 100, 900)

# R2-D §3.7: the knight fork after an unrelated double attack
FORK = "4kb2/8/8/6n1/1P1N4/8/P7/4K3 w - - 0 1"
FORK_LP = "a3 Bc5 b5 Be7 b6 Nf3+ Ke2 Nxd4+ Kd3 Nf5"
QUIET = ["Nb3 Ne6 Kd2 Kd7", "Kd2 Ne6 Nf5 Kd7"]

# the back rank (D1): 1.Qe8+ Rxe8 2.Rxe8#
BACK = "r5k1/5ppp/8/8/8/8/4QPPP/4R1K1 w - - 0 1"
BACK_LINES = ["Qe8+ Rxe8 Rxe8#", "h3 h6 Qe3 Kh7", "g3 h6 Kg2 Kh7"]


def _fork(lp: str = FORK_LP, **kw):
    lines = [
        line(FORK, QUIET[0], EVEN),
        line(FORK, QUIET[1], (250, 600, 150), cp=-10),
        line(FORK, lp, (50, 300, 650), cp=-300),
    ]
    return run(FORK, "a3", lines, **kw)


def _back(played: str, **kw):
    lines = [
        line(BACK, BACK_LINES[0], (1000, 0, 0), mate=2),
        line(BACK, BACK_LINES[1], EVEN, cp=50),
        line(BACK, BACK_LINES[2], (250, 600, 150), cp=30),
    ]
    return run(BACK, played, lines, **kw)


# -- material_loss_v1, better_move_v1 (R2-D §3.1, §3.12) -----------------------------------------


def test_a_material_loss_against_the_best_line_with_its_comparison() -> None:
    analysis = _fork()
    loss = claim(analysis, "material_loss_v1")
    assert loss.verdict.status is S
    found = finding(loss, MaterialFinding)
    assert found.amount.points == 3  # min(−Δp, Δ1 − Δp) = min(3, 0 + 3)
    assert (found.played.kind, found.played.delta) == (OutcomeKind.STABLE, -3)
    assert (found.best.kind, found.best.delta) == (OutcomeKind.STABLE, 0)
    assert found.event.ply == 8 and found.event.victim.square == "d4"  # …Nxd4+
    assert found.event.capturer.square == "f3"
    better = claim(analysis, "better_move_v1")
    assert better.verdict.status is S
    assert better.hypothesis.premises[0].claim == loss.id
    compare = finding(better, ComparisonFinding)
    assert compare.best_move.rank == 1 and compare.best_move.ply == 1
    kinds = {(r.source, r.target, r.kind) for r in analysis.relations}
    assert (better.id, loss.id, RelationKind.COMPARES_WITH) in kinds
    # the scope names S's two lines, the window and the policies
    scope = loss.verdict.scope
    assert {ref.rank for ref in scope.searches} == {1, 3}
    assert scope.plies == 10 and scope.policies == ("points_v1", "quality_v1")


def test_a_loss_the_best_line_shares_is_refuted() -> None:
    # the pawn fork pending at P takes a knight on every line: not this move's loss (rule 6)
    fen = "4k3/8/8/8/3p4/2N1N3/8/4K3 w - - 0 1"
    lines = [
        line(fen, "Nc4 dxc3 Kd1 Kd7 Kc2 Ke6", (300, 500, 200), cp=-150),
        line(fen, "Nb5 dxe3 Kf1 Kd7 Ke2 Ke6", (90, 400, 510), cp=-260),
    ]
    analysis = run(fen, "Nb5", lines, multipv=2)
    loss = claim(analysis, "material_loss_v1")
    assert loss.verdict.status is R  # Δp = Δ1 = −3
    better = claim(analysis, "better_move_v1")
    assert better.verdict.status is R and better.hypothesis.premises == ()
    kinds = {r.kind for r in analysis.relations if r.source == better.id}
    assert RelationKind.COMPARES_WITH not in kinds


def test_an_open_window_and_a_mated_played_line_are_inconclusive() -> None:
    open_end = line(FORK, "a3 Bc5 b5 Nf3+ Ke2 Nxd4+", (50, 300, 650), cp=-300)  # capture at end
    analysis = run(FORK, "a3", [line(FORK, QUIET[0], EVEN), open_end])
    assert table(analysis)["material_loss_v1"] == (I, "LINE_TOO_SHORT")
    assert table(analysis)["better_move_v1"] == (I, "LINE_TOO_SHORT")
    analysis = _back("h3")
    assert status(analysis, "material_loss_v1") is R  # Δp = 0: rule 3


def test_a_drawn_best_line_is_incomparable_with_a_material_loss() -> None:
    # K+B+N v K+R: the best line trades into a bare-king draw (DRAWN_END); Lp loses the bishop
    fen = "4k3/8/8/8/3r4/8/2B2N2/4K3 w - - 0 1"
    lines = [
        line(fen, "Ne4 Rxe4+ Bxe4 Kd7", (0, 1000, 0)),  # K+B v K: insufficient material
        line(fen, "Kf1 Rd2 Ke1 Rxc2 Ne4 Ke7 Kf1 Ke6", (0, 300, 700), cp=-300),
    ]
    analysis = run(fen, "Kf1", lines, multipv=2)
    assert table(analysis)["material_loss_v1"] == (I, "UNSTABLE")
    assert table(analysis)["better_move_v1"] == (I, "UNSTABLE")


# -- material_gain_v1 and the baseline veto (R2-D §1.4, §3.2) ------------------------------------


def test_a_recapture_is_no_gain_from_the_baseline() -> None:
    start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    before = "e4 e5 Nf3 Nc6 Bb5 a6 Bxc6"
    p = after(start, before)
    lines = [
        line(p, "dxc6 O-O Bd6 d3 Nf6 Nc3", EVEN),
        line(p, "bxc6 d3 d6 O-O Nf6 Nc3", (280, 600, 120), cp=-20),
    ]
    analysis = run(start, "dxc6", lines, before=before, multipv=2)
    gain = claim(analysis, "material_gain_v1")
    assert gain.verdict.status is R  # +3 from P, 0 from B


def test_a_check_and_recapture_trade_is_no_gain() -> None:
    start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    before = "d4 e5 dxe5 Bb4+"
    p = after(start, before)
    lines = [
        line(p, "Bd2 Bxd2+ Qxd2 Nc6 Nf3 Qe7", EVEN),
        line(p, "c3 Ba5 Nf3 Nc6 Bf4 Nge7", (280, 600, 120), cp=-20),
    ]
    analysis = run(start, "Bd2", lines, before=before, multipv=2)
    assert status(analysis, "material_gain_v1") is R  # Δp = 0


def test_a_capture_that_holds_is_a_gain() -> None:
    fen = "4k3/8/8/3q4/8/8/4N3/4RK2 w - - 0 1"
    lines = [
        line(fen, "Nc3+ Kd7 Nxd5 Kd6 Ne3 Ke5", WIN, cp=900),
        line(fen, "Kf2 Qd2 Kf3 Kd7", EVEN),
    ]
    analysis = run(fen, "Nc3+", lines, multipv=2)
    gain = claim(analysis, "material_gain_v1")
    assert gain.verdict.status is S
    found = finding(gain, MaterialFinding)
    assert found.amount.points == 9 and found.event.ply == 3
    assert found.event.victim.square == "d5"


def test_a_promotion_without_capture_is_a_gain_naming_the_promotion() -> None:
    fen = "8/4P1k1/8/8/8/8/8/4K3 w - - 0 1"
    lines = [line(fen, "e8=Q Kf6 Kf2 Kg5 Kg3 Kf5", WIN, cp=900), line(fen, "Kf2 Kf7 Ke3 Ke8", EVEN)]
    analysis = run(fen, "e8=Q", lines, multipv=2)
    gain = claim(analysis, "material_gain_v1")
    assert gain.verdict.status is S
    event = finding(gain, MaterialFinding).event
    assert event.victim is None and event.capturer is None and event.promotion.value == "queen"
    for name in ("fork_v1", "pin_v1", "skewer_v1", "discovery_v1"):
        assert status(analysis, name) is None  # no mechanism without a victim (R2-D §1.5)


def test_black_as_the_mover() -> None:
    # the colours of R2-D §3.8a reversed: 1…Qd5 exd5 2…cxd5
    fen = "3qk3/8/2p5/8/4P3/8/8/4K3 b - - 0 1"
    lines = [
        line(fen, "Qd7 Kf2 Ke7 Ke3", EVEN),
        line(fen, "Qd5 exd5 cxd5 Kd2 Kd7 Kd3", LOST, cp=-800),
    ]
    analysis = run(fen, "Qd5", lines, multipv=2)
    loss = claim(analysis, "material_loss_v1")
    assert loss.verdict.status is S
    assert finding(loss, MaterialFinding).amount.points == 8  # the queen for a pawn
    assert table(analysis)["newly_unsafe_v1"][0] is S


# -- mates (R2-D §3.3–§3.6, §8.6d, §8.6f) --------------------------------------------------------


def test_mate_delivered_and_forcing_are_exact() -> None:
    fen = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"
    lines = [line(fen, "Ra8#", (1000, 0, 0), mate=1), line(fen, "h3 h6 Kh2 Kh7", WIN, cp=300)]
    analysis = run(fen, "Ra8#", lines, multipv=2)
    mate = claim(analysis, "mate_delivered_v1")
    assert mate.verdict.status is S and mate.verdict.scope.basis.value == "exact"
    assert finding(mate, MateFinding) == MateFinding(1, MoveRef(analysis.round_zero.subject.child))
    assert status(analysis, "mate_found_v1") is None  # the move itself mates
    assert status(analysis, "forcing_v1") is None


def test_mate_found_with_its_mating_edge_and_forcing() -> None:
    analysis = _back("Qe8+")
    found = claim(analysis, "mate_found_v1")
    assert found.verdict.status is S
    mate = finding(found, MateFinding)
    assert mate.moves == 2 and isinstance(mate.mating_move, MoveRef)
    forcing = claim(analysis, "forcing_v1")
    assert finding(forcing, ForcingFinding) == ForcingFinding(True, 1)  # check, one reply


MATE_IN_ONE = "2r3k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1"  # 1.Rc1?? Rxc1#


def test_mate_in_one_allowed_and_mate_allowed_are_both_claimed() -> None:
    fen = MATE_IN_ONE
    lines = [
        line(fen, "h3 h6 Kh2 Kh7", EVEN),
        line(fen, "Rc1 Rxc1#", (0, 0, 1000), mate=-1),
    ]
    analysis = run(fen, "Rc1", lines, multipv=2)
    exact = claim(analysis, "mate_in_one_allowed_v1")
    assert exact.verdict.status is S and exact.verdict.scope.witnesses == ("c8c1",)
    assert exact.verdict.scope.basis.value == "exact"
    allowed = claim(analysis, "mate_allowed_v1")
    assert allowed.verdict.status is S
    assert isinstance(finding(allowed, MateFinding).mating_move, MoveRef)
    assert table(analysis)["material_loss_v1"] == (I, "MATE_LINE")
    better = claim(analysis, "better_move_v1")
    assert better.verdict.status is S and better.hypothesis.premises[0].claim == allowed.id


def test_mate_in_one_allowed_needs_no_judgement() -> None:
    from scripted import scripted as table_engine
    from test_quality import NO_WDL

    lines = [("h2h3", ("cp", 0), None), ("e1c1", ("mate", -1), None)]
    engine = table_engine({MATE_IN_ONE: lines}, identity=NO_WDL)
    analysis = run(MATE_IN_ONE, "Rc1", [], engine=engine, multipv=2)
    assert analysis.round_zero.judgements[0].reason == "WDL_UNAVAILABLE"
    assert table(analysis) == {"mate_in_one_allowed_v1": (S, None)}


def test_mate_missed_cites_the_best_move_of_the_search() -> None:
    analysis = _back("h3")
    missed = claim(analysis, "mate_missed_v1")
    assert missed.verdict.status is S
    compare = finding(missed, ComparisonFinding)
    assert compare.best_move == SearchMoveRef(compare.best_move.search_id, 1, 1)
    assert compare.best.kind is OutcomeKind.MATE and compare.played.kind is OutcomeKind.STABLE
    better = claim(analysis, "better_move_v1")
    assert better.verdict.status is S and better.hypothesis.premises == ()


# one spare tree node, taken by G's best line: S's lines at P are cut before their first new ply
CUT = replace(ReasoningBudget(), max_tree_nodes=1)
BACK_G = "r5k1/4rppp/8/8/8/8/4QPPP/4R1K1 b - - 0 1"  # …Re7-b7 opens the e-file
FORK_G = "3k1b2/8/8/6n1/1P1N4/8/P7/4K3 b - - 0 1"  # …Kd8-e8 reaches the fork position


def test_a_best_line_cut_before_its_first_ply_keeps_its_mate_score() -> None:
    p = after(BACK_G, "Rb7")
    lines = [line(p, "Qe8+ Rxe8 Rxe8#", (1000, 0, 0), mate=2), line(p, "h3 h6", LOST, mate=-5)]
    analysis = run(BACK_G, "h3", lines, before="Rb7", budget=CUT, multipv=2)
    view = analysis.tree.view(analysis.rev)
    missed = claim(analysis, "mate_missed_v1")
    l1 = missed.hypothesis.target.at
    assert view.line(l1.line).end.value == "budget_limit" and l1.last == 0
    assert missed.verdict.status is S  # the score decides (R2-D §8.6f)
    compare = finding(missed, ComparisonFinding)
    search = view.search(compare.best_move.search_id)
    assert search.lines[0].pv[0] == uci(p, "Qe8+")[0]  # the move's text comes from the search
    # better_move rests on mate_allowed across a zero-ply sibling (ALTERNATIVE_OF by moves)
    better = claim(analysis, "better_move_v1")
    assert better.verdict.status is S
    assert better.hypothesis.premises[0].claim == claim(analysis, "mate_allowed_v1").id


def test_a_material_outcome_on_a_cut_line_is_inconclusive() -> None:
    lines = [
        line(FORK, QUIET[0], EVEN),
        line(FORK, FORK_LP, (50, 300, 650), cp=-300),
    ]
    analysis = run(FORK_G, "a3", lines, before="Ke8", budget=CUT, multipv=2)
    assert table(analysis)["material_loss_v1"] == (I, "LINE_TOO_SHORT")
    assert table(analysis)["better_move_v1"] == (I, "LINE_TOO_SHORT")


# -- functions (R2-D §3.9, §3.10, §3.13) ---------------------------------------------------------


def test_only_move_by_the_margin_of_rank_two() -> None:
    analysis = _back("Qe8+")
    only = claim(analysis, "only_move_v1")
    assert only.verdict.status is S and only.verdict.scope.population.kind.value == "engine_ranked"
    assert [label.kind for label in analysis.labels] == [LabelKind.GREAT]
    assert analysis.labels[0].grounds == (only.id,)
    close = [
        line(BACK, BACK_LINES[0], (1000, 0, 0), mate=2),
        line(BACK, BACK_LINES[1], WIN, cp=500),
    ]
    analysis = run(BACK, "Qe8+", close, multipv=2)
    assert status(analysis, "only_move_v1") is R  # 2000 − 1900 < 400
    assert analysis.labels == ()


def test_only_move_without_rank_two() -> None:
    analysis = run(BACK, "Qe8+", [line(BACK, BACK_LINES[0], (1000, 0, 0), mate=2)], multipv=1)
    assert table(analysis)["only_move_v1"] == (I, "NOT_COMPUTED(NO_RANK_2)")


def _comparison_engine() -> ScriptedEngine:
    """At BACK the survey omits Qe8+; the comparison then ranks it first."""

    from scripted import _position
    from synthetic import IDENTITY, synthetic

    from calliope.facts.search.inputs import window_end

    survey = [("h2h3", ("cp", 50), EVEN), ("g2g3", ("cp", 40), EVEN)]
    played = uci(BACK, BACK_LINES[0])
    fallback = synthetic(4)

    def answer(request):
        if _position(window_end(request.input).fen()) != _position(BACK):
            return fallback(request)
        if request.root_moves is None:
            rows = survey
        else:
            rows = [(played[0], ("mate", 2), (1000, 0, 0)), *survey]
        out = []
        for rank, (move, score, wdl) in enumerate(rows[: request.multipv], start=1):
            pv = played if move == played[0] else (move,)
            out.append(RawLine(rank, 12, 14, score, Bound.EXACT, wdl, 1000, 0, pv))
        return RawSearch(tuple(out), StoppedBy.DEPTH, 1)

    return ScriptedEngine(IDENTITY, answer)


def test_only_move_on_a_comparison_search_is_scope_short() -> None:
    analysis = run(BACK, "Qe8+", [], engine=_comparison_engine(), multipv=2)
    judgement = analysis.round_zero.judgements[0]
    view = analysis.tree.view(analysis.rev)
    assert view.search(judgement.search.search_id).kind.value == "comparison"
    assert table(analysis)["only_move_v1"] == (I, "SCOPE_SHORT")

    # the runner enforces it too: a template claiming ENGINE_RANKED over a comparison is cut short
    from calliope.reasoning.catalogue.base import scope, supported
    from calliope.reasoning.catalogue.functions import OnlyMove

    class Unchecked(OnlyMove):
        def verify(self, h, view, grading):
            return supported(h, scope(view, h, grading, (1, 2)))

    engine = _comparison_engine()
    analysis = run(BACK, "Qe8+", [], engine=engine, multipv=2, templates=(Unchecked(),))
    assert table(analysis)["only_move_v1"] == (I, "SCOPE_SHORT")


def test_an_existential_claim_over_a_comparison_ranking_is_scope_short() -> None:
    # R2b re-review C2: EXISTS_* targets over ENGINE_RANKED need a SURVEY as well
    from calliope.reasoning.catalogue.base import F, Template, judged, scope, supported
    from calliope.reasoning.hypotheses import (
        ClaimRole,
        NodeContext,
        Population,
        PopulationKind,
        Quantifier,
        VerificationTarget,
    )

    class SomeAlternative(Template):
        name = "some_alternative"
        role = ClaimRole.FUNCTION
        directions = frozenset({F})
        predicate = "some_alternative"

        def propose(self, ctx):
            search = judged(ctx).search.search_id
            p = ctx.subject.parent
            population = Population(PopulationKind.ENGINE_RANKED, search)
            target = VerificationTarget(Quantifier.EXISTS_ALTERNATIVE, p, population)
            return (self.make(ctx, context=NodeContext(p), operands=(), target=target),)

        def verify(self, h, view, grading):
            return supported(
                h, scope(view, h, grading, (2,), witnesses=("h2h3",))
            )  # a legal witness

    templates = (SomeAlternative(),)
    analysis = run(BACK, "Qe8+", [], engine=_comparison_engine(), multipv=2, templates=templates)
    assert table(analysis)["some_alternative"] == (I, "SCOPE_SHORT")
    # over the survey of an ordinary position the same claim stands
    lines = [line(BACK, BACK_LINES[0], (1000, 0, 0), mate=2), line(BACK, BACK_LINES[1], EVEN)]
    analysis = run(BACK, "Qe8+", lines, multipv=2, templates=templates)
    assert table(analysis)["some_alternative"] == (S, None)


def test_prevents_when_every_alternative_loses() -> None:
    fen = "4k3/7p/8/4b3/8/8/7P/R3K3 w - - 0 1"
    lines = [
        line(fen, "Ra4 Kd7 Kd2 Kd6", EVEN),
        line(fen, "Kd2 Bxa1 Kc2 Be5", (0, 300, 700), cp=-500),
        line(fen, "Ke2 Bxa1 Kd3 Be5", (0, 250, 750), cp=-510),
    ]
    analysis = run(fen, "Ra4", lines)
    prevents = claim(analysis, "prevents_v1")
    assert prevents.verdict.status is S
    assert finding(prevents, PreventsFinding) == PreventsFinding(PreventsKind.MATERIAL, 2, 5)
    counter = [lines[0], lines[1], line(fen, "Rb1 Kd7 Kd2 Kd6", (250, 600, 150), cp=-10)]
    assert status(run(fen, "Ra4", counter), "prevents_v1") is R  # one counterexample


def test_prevents_is_refuted_when_the_played_line_is_bad_too() -> None:
    fen = "4k3/pp3ppp/8/8/8/8/PPn2PPP/R3K3 w - - 0 1"
    lines = [
        line(fen, "Kd2 Nxa1 Kc1 Ke7 Kb1 Kd6", (0, 300, 700), cp=-500),
        line(fen, "Kd1 Nxa1 Kc1 Ke7 Kb1 Kd6", (0, 250, 750), cp=-510),
    ]
    assert status(run(fen, "Kd2", lines, multipv=2), "prevents_v1") is R


# -- labels (R2-D §5.2) --------------------------------------------------------------------------


def test_miss_after_the_opponents_blunder() -> None:
    g = "r5k1/4rppp/8/8/8/8/4QPPP/4R1K1 b - - 0 1"
    at_g = [
        ("g8f8", ("cp", 0), (200, 600, 200)),
        (uci(g, "Rb7")[0], ("mate", -2), (0, 0, 1000)),
    ]
    p = after(g, "Rb7")
    at_p = [
        line(p, "Qe8+ Rxe8 Rxe8#", (1000, 0, 0), mate=2),
        line(p, "h3 h6 Qe3 Kh7", EVEN, cp=50),
    ]
    analysis = run(g, "h3", at_p, before="Rb7", table={g: at_g}, multipv=2)
    assert analysis.round_zero.judgements[1].grade.value == "blunder"
    better = claim(analysis, "better_move_v1")
    assert [label.kind for label in analysis.labels] == [LabelKind.MISS]
    assert analysis.labels[0].grounds == (better.id,)
    # without the opponent's mistake there is no MISS
    at_g_fine = [(uci(g, "Rb7")[0], ("cp", 0), (200, 600, 200)), ("g8f8", ("cp", -10), EVEN)]
    analysis = run(g, "h3", at_p, before="Rb7", table={g: at_g_fine}, multipv=2)
    assert analysis.labels == ()


def test_label_v1_never_assigns_brilliant() -> None:
    analysis = _back("Qe8+")
    assert status(analysis, "sacrifice_compensated_v1") is S
    assert LabelKind.BRILLIANT not in {label.kind for label in analysis.labels}
