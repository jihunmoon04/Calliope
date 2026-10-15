"""Explanation v2, part 1 (EV-D §7): draws by checks and what the better move does about the reply.

Scenarios are scripted (`story.run`); a few rules that need an unusual board are checked on a
real analysis whose records a wrapped view replaces (`_Patched`), so the claim's decision itself is
what the test reads.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from scripted import scripted
from story import I, R, S, after, claim, finding, line, run, status
from test_miss_v2 import wdl
from test_quality import NO_WDL

from calliope.facts import (
    Color,
    Defined,
    EnsureRequest,
    ExchangeFacts,
    FactEngine,
    NotComputed,
    PieceType,
    Relation,
    SearchKind,
)
from calliope.reasoning import GradingSpec, ReasoningBudget, StoredGraphError
from calliope.reasoning.catalogue import CATALOGUE_V1
from calliope.reasoning.catalogue.comparison import BestStopsReply
from calliope.reasoning.catalogue.draws import ChecksDraw
from calliope.reasoning.findings import ChecksDrawFinding, DrawKind, ReplyFinding, ReplyKind
from calliope.reasoning.lines import CHECK_RUN, DRAW_CP, DRAW_WDL, checking_draw, read_line
from calliope.reasoning.needs import FamilyNeed, LineNeed
from calliope.reasoning.planner import DETAIL_AFTER, plan
from calliope.reasoning.refs import FactRef, LineSegment, SearchRef
from calliope.reasoning.render import GuardError, explain, plan_analysis, render, trace
from calliope.reasoning.storage import load, save

WIN, DRAW = (1000, 0, 0), (0, 1000, 0)

# -- the boards ---------------------------------------------------------------------------------

# Black's queen checks from d1 and d6 while White's king walks h1–h2; White mates with Qb8+
A = "7k/6pp/3q4/8/8/8/1Q6/7K w - - 0 1"
MATE2 = "Qb8+ Qd8 Qxd8#"
CHECKS3 = "Qb3 Qd1+ Kh2 Qd6+ Kh1 Qd1+"  # the third check repeats the position after the first
THIRD = "Qb3 Qd1+ Kh2 Qd6+ Kh1 Qd1+ Kh2 Qd6+ Kh1 Qd1+"  # a third occurrence inside the window
CYCLE = "Qb3 Qd1+ Kh2 Qd6+ Kh1 Qd1+ Kh2 Qd6+ Kh1 Qe6 Qb2 Qd6"  # back to A, the checks played twice
# White's own checks: Qd8+ / Qd3+ against the king on h8 / h7
OWN = "7k/1q6/8/8/8/3Q4/6PP/7K w - - 0 1"
# the reply's square: Black's queen enters e2 and takes on f2 later; 1.Qc2 covers e2
COVERS = "6k1/5ppp/8/1q6/Q7/8/5PPP/6K1 w - - 0 1"
COVERS_L1 = "Qc2 h6 h3 Kh8 Kh2 Kg8"
COVERS_LP = "h3 Qe2 Kh2 Qxf2 Qd7 Qf4+"
# the reply takes the knight on e5; 1.Nf3 moves it to safety
RESCUES = "6k1/6pp/3p4/4N3/8/8/6PP/6K1 w - - 0 1"
RESCUES_L1, RESCUES_LP = "Nf3 Kf7 Kf2 Ke6", "h3 dxe5 Kf2 Kf7"
# the reply takes the pawn on e4; 1.Nc3 defends it
DEFENDS = "6k1/6pp/8/3p4/4P3/8/6PP/1N4K1 w - - 0 1"
DEFENDS_L1, DEFENDS_LP = "Nc3 Kf7 exd5 Ke7 Kf2 Kd6", "h3 dxe4 Kf2 Kf7 Ke3 Ke6"
GOOD, POOR = (600, 400, 0), (100, 500, 400)


def checks(lp: str, *, fen: str = A, played: str = "Qb3", before: str = "", l1: str = MATE2,
           l1_wdl=WIN, l1_cp: int = 0, **score):  # fmt: skip
    """Scenario A: the played move's line `lp` against the best line `l1` (rank 1)."""

    p = after(fen, before)
    wdl_ = score.pop("wdl", DRAW)
    lines = [line(p, l1, l1_wdl, cp=l1_cp), line(p, lp, wdl_, **score)]
    return run(fen, played, lines, before=before, multipv=2)


def no_wdl(lp: str, *, before: str = "", l1: str = MATE2, played: str = "Qb3"):
    """The same with an engine that reports no WDL, graded by the score curve."""

    p = after(A, before)
    lines = [line(p, l1, None, cp=900), line(p, lp, None, cp=0)]
    port = scripted({p: lines}, identity=NO_WDL)
    return run(A, played, [], before=before, engine=port, grading=GradingSpec(), multipv=2)


def reply(fen: str, l1: str, lp: str, played: str = "h3", *, good=GOOD, poor=POOR, **kwargs):
    return run(fen, played, [line(fen, l1, good), line(fen, lp, poor)], multipv=2, **kwargs)


def draw_of(a) -> ChecksDrawFinding:
    return finding(claim(a, "checks_draw_v1"), ChecksDrawFinding)


def view_of(a):
    return a.tree.view(a.rev)


def resolve(view, ref: FactRef):
    """The value a `FactRef` names: its record at its revision, then its path (G3)."""

    for node in view.nodes():
        entry = view.fact_entry(ref.family, node.node_id)
        if entry is not None and entry.target == ref.target and entry.rev == ref.rev:
            value = view.fact(ref.family, node.node_id)
            for step in ref.path:
                value = value[step] if isinstance(step, int) else getattr(value, step)
            return value
    raise AssertionError(f"{ref} resolves to no record")


def resolves(a, c) -> None:
    view = view_of(a)
    for ref in c.verdict.evidence:
        if isinstance(ref, FactRef):
            resolve(view, ref)
        elif isinstance(ref, SearchRef):
            assert any(x.rank == ref.rank for x in view.search(ref.search_id).lines)


class _Patched:
    """A view whose records `patch(family, node, record)` may replace; the rest is the view's."""

    def __init__(self, view, patch) -> None:
        self._view, self._patch = view, patch

    def __getattr__(self, name):
        return getattr(self._view, name)

    def fact(self, family, node):
        return self._patch(family, node, self._view.fact(family, node))


def reverify(a, template, patch):
    c = claim(a, template.name)
    view = _Patched(view_of(a), patch)
    return template.verify(c.hypothesis, view, a.round_zero.grading)


def nodes(a):
    """`(P, A1, R, B1, C)` of the reply claim (EV-D §3.1); C is None when it was not created."""

    c = claim(a, "best_stops_reply_v1")
    view = view_of(a)
    l1_window, lp_window = c.hypothesis.operands
    lp, l1 = view.line(lp_window.line), view.line(l1_window.line)
    r = view.node(lp.nodes[2]).incoming_move
    return lp.nodes[0], lp.nodes[1], lp.nodes[2], l1.nodes[1], view.child(l1.nodes[1], r)


# -- 1: the checking draw (EV-D §2.1) -----------------------------------------------------------


def test_the_constants() -> None:
    assert (CHECK_RUN, DRAW_CP, DRAW_WDL) == (2, 10, 900)


def test_runs_of_one_two_and_three_checks() -> None:
    assert status(checks("Qb3 h6 Qc2 Qd1+ Kh2"), "checks_draw_v1") is R  # one check
    two = draw_of(checks("Qb3 h6 Qc2 Qd1+ Kh2 Qd6+"))
    assert (two.checker, two.kind, two.checks, two.repeat_at) == (
        Color.BLACK,
        DrawKind.SCORED,
        2,
        None,
    )
    assert (two.line.first, two.line.last) == (3, 6)  # it shows the edges into N_4 … N_6
    three = draw_of(checks(CHECKS3))
    assert (three.kind, three.checks) == (DrawKind.REPEATED, 3)


def test_a_quiet_ply_breaks_the_run_and_a_mate_ends_it() -> None:
    assert status(checks("Qb3 Qd1+ Kh2 h6 Qc2 Qd6+"), "checks_draw_v1") is R
    mating = "7k/6pp/3q4/8/8/8/1Q5P/7K w - - 0 1"
    a = checks("Qb3 Qc6+ Qf3 Qc1+ Qf1 Qxf1#", fen=mating, l1="Qb8+ Qd8 Qxd8#", cp=0)
    assert status(a, "checks_draw_v1") is R  # the last check mates: no draw


@pytest.mark.parametrize(("cp", "expected"), [(0, S), (10, S), (-10, S), (11, R), (-11, R)])
def test_the_score_bound(cp: int, expected) -> None:
    assert status(checks(CHECKS3, cp=cp), "checks_draw_v1") is expected


def test_a_mate_score_is_never_a_draw() -> None:
    assert status(checks(CHECKS3, mate=-9), "checks_draw_v1") is R


@pytest.mark.parametrize(("draw", "expected"), [(899, R), (900, S)])
def test_the_wdl_bound(draw: int, expected) -> None:
    a = checks("Qb3 h6 Qc2 Qd1+ Kh2 Qd6+", wdl=(1000 - draw, draw, 0))
    assert status(a, "checks_draw_v1") is expected


def test_without_the_wdl_only_a_repetition_by_rule_counts() -> None:
    a = no_wdl(CHECKS3)
    assert claim(a, "checks_draw_v1").verdict.status is I
    assert claim(a, "checks_draw_v1").verdict.reason == "NOT_COMPUTED(wdl)"
    assert "check after check" not in explain(a).text  # INCONCLUSIVE: not rendered
    assert draw_of(no_wdl(THIRD)).kind is DrawKind.THREEFOLD
    assert draw_of(no_wdl(THIRD, before=CYCLE)).kind is DrawKind.FIVEFOLD


def test_a_third_occurrence_can_be_claimed_and_a_fifth_is_drawn() -> None:
    third = checks(THIRD)
    f = draw_of(third)
    assert f.kind is DrawKind.THREEFOLD
    (ref,) = (e for e in claim(third, "checks_draw_v1").verdict.evidence
              if isinstance(e, FactRef) and e.family == "draw")  # fmt: skip
    assert ref.path == ("threefold_reached",) and resolve(view_of(third), ref) is True
    assert "repeating the position a third time, so a draw can be claimed." in explain(third).text
    fifth = checks(THIRD, before=CYCLE)
    assert draw_of(fifth).kind is DrawKind.FIVEFOLD
    view = view_of(fifth)
    assert view.fact("draw", draw_of(fifth).repeat_at.node).fivefold_reached is True
    text = explain(fifth).text
    assert "repeating the position a fifth time: the game is drawn." in text
    assert "can be claimed" not in text


def test_history_unknown_is_not_a_third_occurrence() -> None:
    unknown = "7k/6pp/3q4/8/8/8/1Q6/7K w - - 30 40"  # thirty plies of unknown history
    a = checks(CHECKS3, fen=unknown)
    f = draw_of(a)
    assert f.kind is DrawKind.REPEATED  # by the WDL, not by rule
    record = view_of(a).fact("draw", f.repeat_at.node)
    assert record.threefold_reached is not True


def test_only_the_run_repeats() -> None:
    # rev. 2, N1: the node before the first check repeats a position, the run does not
    a = checks("Qb3 Qd1+ Kh2 Qd6+", before="Qb3 Qe6 Qb2 Qd6")
    assert view_of(a).fact("draw", read_window(a)[1]).occurrences == 2
    assert draw_of(a).kind is DrawKind.SCORED


def test_a_repetition_of_the_game_history_and_of_the_window() -> None:
    history = checks("Qb3 Qd1+ Kh2 Qd6+", before="Qb3 Qd1+ Kh2 Qd6+ Kh1 Qe6 Qb2 Qd6")
    f = draw_of(history)
    assert f.kind is DrawKind.REPEATED and f.repeat_at.node == read_window(history)[2]
    a = checks(CHECKS3)  # 3.Kh1 brings back the position after 1.Qb3, inside the run
    window = draw_of(a)
    assert window.kind is DrawKind.REPEATED and window.repeat_at.node == read_window(a)[5]


def read_window(a):
    c = claim(a, "checks_draw_v1")
    view = view_of(a)
    return read_line(view, c.hypothesis.operands[0], Color.WHITE).nodes


def test_a_missing_draw_record_is_inconclusive() -> None:
    a = checks(CHECKS3)
    verdict = reverify(a, ChecksDraw(), lambda f, n, rec: NotComputed("x") if f == "draw" else rec)
    assert (verdict.status, verdict.reason) == (I, "NOT_COMPUTED(draw)")
    view = _Patched(view_of(a), lambda f, n, rec: NotComputed("x") if f == "draw" else rec)
    lp = read_line(view, claim(a, "checks_draw_v1").hypothesis.operands[0], Color.WHITE)
    assert checking_draw(view, lp, Color.BLACK) == "NOT_COMPUTED(draw)"


# -- 2: checks_draw_v1 (EV-D §2.2) ----------------------------------------------------------------


def test_the_opponents_checks_after_a_blunder() -> None:
    a = checks(CHECKS3)
    c = claim(a, "checks_draw_v1")
    assert c.verdict.status is S
    assert c.verdict.scope.plies == 6 and c.verdict.scope.searches == (
        SearchRef(c.hypothesis.target.population.search_id, 2),
        SearchRef(c.hypothesis.target.population.search_id, 1),
    )
    resolves(a, c)
    assert plan_analysis(a).consequence == (c.id,)
    assert explain(a).text == (
        "1.Qb3 is a blunder. Along the engine line, Black then gives check after check, 1...Qd1+ "
        "2.Kh2 Qd6+ 3.Kh1 Qd1+, repeating the position, and the engine scores it as a draw. There "
        "was mate in 2 with 1.Qb8+. Based on the engine line at depth 12."
    )
    scored = explain(checks("Qb3 h6 Qc2 Qd1+ Kh2 Qd6+")).text
    assert (
        "Black then gives check after check, 2...Qd1+ 3.Kh2 Qd6+, and the engine scores it as a draw."
        in scored
    )


def test_the_movers_own_checks() -> None:
    lp = "Qd8+ Kh7 Qd3+ Kh8 Qd8+ Kh7"
    a = checks(lp, fen=OWN, played="Qd8+", l1="Qd4 Kg8 h3 Kf7")
    f = draw_of(a)
    assert (f.checker, f.kind, f.checks) == (Color.WHITE, DrawKind.REPEATED, 3)
    assert (
        "It settles for checks, 1.Qd8+ Kh7 2.Qd3+ Kh8 3.Qd8+ Kh7, repeating the position, which the engine scores as a draw."
        in explain(a).text
    )


def test_the_same_checks_in_the_best_line_refute() -> None:
    l1 = "Qc2 Qd1+ Kh2 Qd6+ Kh1 Qd1+ Kh2 Qd6+ Kh1 Qd1+"  # Black's checks to a third occurrence
    a = checks(CHECKS3, l1=l1, l1_wdl=(600, 400, 0))
    assert status(a, "checks_draw_v1") is R


def test_not_proposed_for_a_good_move() -> None:
    a = checks(CHECKS3, l1="Qc2 Qd1+ Kh2 Qd6+", l1_wdl=DRAW)
    assert a.round_zero.judgements[0].loss == 0
    assert status(a, "checks_draw_v1") is None


# -- 3: checks_draw_missed_v1 (EV-D §2.3) -------------------------------------------------------

B_FEN = "7k/6pp/3q4/8/8/8/1Q6/7K b - - 0 1"
B_L1 = "Qd1+ Kh2 Qd6+ Kh1 Qd1+ Kh2 Qd6+ Kh1 Qd1+"


def missed(lp: str = "h6 Qb3 Kh7 Qc2+ Kh8 Qc3", *, l1: str = B_L1, lp_wdl=(0, 100, 900),
           l1_wdl=DRAW, **kwargs):  # fmt: skip
    p = after(B_FEN, kwargs.get("before", ""))
    return run(B_FEN, "h6", [line(p, l1, l1_wdl), line(p, lp, lp_wdl)], multipv=2, **kwargs)


def test_the_movers_missed_checks() -> None:
    a = missed()
    c = claim(a, "checks_draw_missed_v1")
    assert c.verdict.status is S and finding(c, ChecksDrawFinding).kind is DrawKind.THREEFOLD
    resolves(a, c)
    p = plan_analysis(a)
    assert p.justification == (c.id,) and p.detail == ()
    assert status(a, "missed_gain_v1") is S  # chosen over it: one "Instead"
    text = explain(a).text
    assert text.count("Instead") == 1
    assert text == (
        "1...h6 is a blunder. Instead, 1...Qd1+ was needed: it starts a series of checks, 1...Qd1+ "
        "2.Kh2 Qd6+ 3.Kh1 Qd1+ 4.Kh2 ..., repeating the position a third time, so a draw can be "
        "claimed. Based on the engine line at depth 12."
    )


def test_a_played_line_that_draws_by_checks_too_refutes() -> None:
    a = missed("h6 Qb8+ Kh7 Qb1+ Kh8 Qb8+", lp_wdl=(0, 950, 50), l1_wdl=(500, 500, 0))
    assert status(a, "checks_draw_v1") is S  # White's checks
    assert status(a, "checks_draw_missed_v1") is R


def test_a_best_line_drawn_without_checks_refutes() -> None:
    assert status(missed(l1="Kg8 Qb3+ Kh8 Qb2 Kg8 Qb3+ Kh8"), "checks_draw_missed_v1") is R


def test_a_miss_keeps_its_ground() -> None:
    g = "7k/6pp/3q4/8/8/8/2Q5/7K w - - 0 1"  # White's Qb2 (from c2) lost 130 at G
    at_g = [line(g, "Qc8+ Qd8 Qxd8#", wdl(2000)), line(g, "Qb2 Qd1+ Kh2 Qd6+", wdl(1870))]
    p = after(g, "Qb2")
    lines = [line(p, B_L1, DRAW), line(p, "h6 Qb3 Kh7 Qc2+ Kh8 Qc3", (0, 100, 900))]
    a = run(g, "h6", lines, before="Qb2", table={g: at_g}, multipv=2)
    assert [lb.kind.value for lb in a.labels] == ["miss"]
    assert status(a, "checks_draw_missed_v1") is S
    gain = claim(a, "missed_gain_v1")
    assert plan_analysis(a).justification == (gain.id,)
    assert "This is a missed opportunity; instead, 1...Qd1+ was stronger." in explain(a).text


# -- 4: best_stops_reply_v1 (EV-D §3) -----------------------------------------------------------


def reply_of(a) -> ReplyFinding:
    return finding(claim(a, "best_stops_reply_v1"), ReplyFinding)


def admitted(a) -> list:
    return [need for rnd in a.rounds for need in rnd.admitted]


def test_covers() -> None:
    a = reply(COVERS, COVERS_L1, COVERS_LP)
    c = claim(a, "best_stops_reply_v1")
    f = finding(c, ReplyFinding)
    p_, a1, r_, b1, c_ = nodes(a)
    assert (f.kind, f.square.square, f.board, f.counter, f.answer, f.lost) == (
        ReplyKind.COVERS, "e2", b1, c_, "c2e2", 9)  # fmt: skip
    assert (f.piece.square, f.piece.node, f.played_gain, f.best_gain) == ("e2", c_, None, None)
    resolves(a, c)
    view = view_of(a)
    assert view.searches(c_) == ()  # the node B1 + r has no search
    assert c.verdict.scope.plies == 6 and "see_v1" in c.verdict.scope.policies
    assert c.hypothesis.target.at.line.rank == 2  # EV1 note 1: the target is Lp's segment
    rounds = [tuple(rnd.admitted) for rnd in a.rounds]
    assert LineNeed(b1, ("b5e2",), _no_search()) in rounds[0]
    assert FamilyNeed(c_, "exchange") in rounds[1]
    # COVERS reads `exchange` at C only; on Lp (P, A1, R) the loss's attribution reads it (EF-D §3.5)
    wanted = [n for n in admitted(a) if isinstance(n, FamilyNeed)]
    assert not any(n.node == b1 for n in wanted)
    assert all(n.family == "exchange" for n in wanted if n.node in (p_, a1, r_))
    assert explain(a).text.endswith(
        "1.Qc2 covers e2: after 1.Qc2, 1...Qe2 would lose the queen on e2 in the exchange there, "
        "starting with 2.Qxe2. Based on the engine line at depth 12 and piece exchanges judged by "
        "static exchange evaluation."
    )


def _no_search():
    from calliope.facts import ExpansionSpec

    return ExpansionSpec(False, False, False)


def test_covers_with_a_net_loss_below_the_piece() -> None:
    # Black's rook on e8 recaptures on e2: the rook takes the queen and is lost, net 4
    fen = "4r1k1/5ppp/8/1q6/8/R7/5PPP/6K1 w - - 0 1"
    a = reply(fen, "Ra2 h6 h3 Kh8 Kh2 Kg8", "h3 Qe2 Kh2 Qxf2 Rg3 h6")
    f = reply_of(a)
    assert (f.kind, f.lost, f.answer) == (ReplyKind.COVERS, 4, "a2e2")
    assert ("1.Ra2 covers e2: after 1.Ra2, 1...Qe2 would lose material in the exchange there "
            "(net 4 points), starting with 2.Rxe2.") in explain(a).text  # fmt: skip


@pytest.mark.parametrize(
    ("fen", "l1", "lp"),
    [
        (COVERS, "Qxb5 h6 h3 Kh8 Kh2 Kg8", COVERS_LP),  # r is not legal after b
        ("4r1k1/5ppp/8/1q6/Q7/8/5PPP/6K1 w - - 0 1", COVERS_L1, COVERS_LP),  # no SEE gain on e2
        ("6k1/5ppp/8/8/Q7/8/R1q2PPP/6K1 w - - 0 1", "Qe4 h6 h3 Kh8 Kh2 Kg8",
         COVERS_LP),  # the rook, not the best move's queen, takes first
        ("6k1/5ppp/8/1q6/Q7/8/5PPP/2N3K1 w - - 0 1", COVERS_L1, COVERS_LP),  # e2 already covered
        ("6k1/5ppp/8/1q6/8/R7/5PPP/3Q2K1 w - - 0 1", "Ra2 h6 h3 Kh8 Kh2 Kg8",
         "h3 Qe2 Kh2 Qxf2 Rg3 h6"),  # covered by the queen, though the rook would take first
        (COVERS, COVERS_L1, "h3 Qe2 Kh2 h6 Kg1 Kh7"),  # the queen does nothing later
    ],
)  # fmt: skip
def test_covers_refuted(fen: str, l1: str, lp: str) -> None:
    assert status(reply(fen, l1, lp), "best_stops_reply_v1") is R


def test_rescues() -> None:
    a = reply(RESCUES, RESCUES_L1, RESCUES_LP)
    c = claim(a, "best_stops_reply_v1")
    f = finding(c, ReplyFinding)
    p_, a1, _r, _b1, _c = nodes(a)
    assert (f.kind, f.piece.square, f.piece.node, f.square) == (ReplyKind.RESCUES, "e5", p_, None)
    resolves(a, c)
    assert {FamilyNeed(p_, "exchange"), FamilyNeed(a1, "exchange")} <= set(a.rounds[0].admitted)
    assert "1.Nf3 saves the knight on e5 from 1...dxe5." in explain(a).text


def test_rescues_refuted() -> None:
    # the best move puts the knight where a pawn takes it: not among its safe moves
    unsafe = "6k1/1p4pp/3p4/4N3/8/8/6PP/6K1 w - - 0 1"
    assert status(reply(unsafe, "Nc6 bxc6 Kf2 Kf7", RESCUES_LP), "best_stops_reply_v1") is R
    # the knight was safe at P: the played move took away its defender
    safe = "4r1k1/6pp/8/4N3/3P4/8/6PP/6K1 w - - 0 1"
    a = reply(safe, RESCUES_L1, "d5 Rxe5 Kf2 Kf7", played="d5")
    assert status(a, "best_stops_reply_v1") is R


def test_defends() -> None:
    a = reply(DEFENDS, DEFENDS_L1, DEFENDS_LP)
    c = claim(a, "best_stops_reply_v1")
    f = finding(c, ReplyFinding)
    _p, a1, r_, b1, c_ = nodes(a)
    assert (f.kind, f.piece.square, f.piece.node, f.board, f.counter) == (
        ReplyKind.DEFENDS, "e4", b1, b1, c_)  # fmt: skip
    assert (f.answer, f.played_gain, f.best_gain, f.lost) == ("c3e4", 1, 0, None)
    resolves(a, c)
    assert view_of(a).searches(c_) == ()
    # rev. 4, B7: R and the extension of B1 in one round, then C; never A1 or B1
    assert set(a.rounds[0].admitted) >= {FamilyNeed(r_, "exchange"),
                                         LineNeed(b1, ("d5e4",), _no_search())}  # fmt: skip
    assert FamilyNeed(c_, "exchange") in a.rounds[1].admitted
    # DEFENDS reads nothing at A1 or B1; on Lp (A1) the loss's attribution reads `exchange`
    wanted = [n for n in admitted(a) if isinstance(n, FamilyNeed)]
    assert not any(n.node == b1 for n in wanted)
    assert all(n.family == "exchange" for n in wanted if n.node == a1)
    assert ("1.Nc3 defends the pawn on e4: if 1...dxe4, the static exchange on e4 yields no net "
            "gain, starting with 2.Nxe4.") in explain(a).text  # fmt: skip


def test_defends_with_the_node_already_in_the_best_line() -> None:
    a = reply(DEFENDS, "Nc3 dxe4 Nxe4 Kf7 Kf2 Ke6", DEFENDS_LP)  # L1 plays r itself
    _p, _a1, r_, b1, c_ = nodes(a)
    assert status(a, "best_stops_reply_v1") is S
    assert not any(isinstance(n, LineNeed) and n.start == b1 for n in admitted(a))
    assert {FamilyNeed(r_, "exchange"), FamilyNeed(c_, "exchange")} <= set(a.rounds[0].admitted)


def test_defends_reads_the_reply_not_the_square() -> None:
    """B7: the reply is the queen's capture, not the pawn's (the least valuable attacker). After
    1.Nc3 the square's exchange still wins a pawn for Black (the pawn takes first), but the
    queen's capture loses the queen: the claim reads the reply."""

    fen = "4q1k1/6pp/8/3p4/4P3/8/6PP/1N4K1 w - - 0 1"
    a = reply(fen, DEFENDS_L1, "h3 Qxe4 Kf2 Kf7 g3 Ke6")
    f = reply_of(a)
    assert (f.kind, f.played_gain, f.best_gain, f.answer) == (ReplyKind.DEFENDS, 1, -5, "c3e4")
    _p, _a1, _r, b1, _c = nodes(a)
    FactEngine().ensure(a.tree, EnsureRequest((b1,), ("exchange",)))
    square = next(x for x in a.tree.view().fact("exchange", b1).pieces if x.square == "e4")
    assert square.gain.value >= 1  # a square-level rule would have refused the defence


def test_defends_ignores_a_square_level_exchange() -> None:
    """B7: with the square's exchange 0 after the best move but the fixed reply still winning
    (here: the record at C made to win nothing for White), DEFENDS is refuted."""

    a = reply(DEFENDS, DEFENDS_L1, DEFENDS_LP)
    _p, _a1, _r, b1, c_ = nodes(a)

    def patch(family, node, record):
        if family == "exchange" and node == c_:
            return _gain_at(record, "e4", 0)
        if family == "exchange" and node == b1:
            return _gain_at(record, "e4", 0)
        return record

    verdict = reverify(a, BestStopsReply(), patch)
    assert verdict.status is R


def _gain_at(record: ExchangeFacts, square: str, gain: int) -> ExchangeFacts:
    """The record with the gain on `square` replaced; its first capture is kept."""

    pieces = tuple(replace(p, gain=Defined("see_v1", gain)) if p.square == square else p
                   for p in record.pieces)  # fmt: skip
    return replace(record, pieces=pieces)


def test_defends_needs_the_same_capture_and_a_new_unpinned_defender() -> None:
    a = reply(DEFENDS, DEFENDS_L1, DEFENDS_LP)
    _p, _a1, _r, b1, c_ = nodes(a)
    view = view_of(a)
    other = replace(view.fact("move", c_), piece=view.fact("move", _a1).piece)  # another capturer

    def capturer(family, node, record):
        return other if family == "move" and node == c_ else record

    assert reverify(a, BestStopsReply(), capturer).status is R
    squares = view.fact("squares", b1)
    e4 = squares.squares[28]
    pinned = replace(e4, white_attackers=tuple(replace(x, absolutely_pinned=True)
                                               for x in e4.white_attackers))  # fmt: skip
    patched = replace(squares, squares=(*squares.squares[:28], pinned, *squares.squares[29:]))

    def pin(family, node, record):
        return patched if family == "squares" and node == b1 else record

    assert reverify(a, BestStopsReply(), pin).status is R
    # the knight already attacked e4 at A1, pinned (even a pinned attacker is not new)
    squares_a1 = view.fact("squares", _a1)
    knight = Relation("b1", PieceType.KNIGHT, True)
    e4_a1 = replace(squares_a1.squares[28], white_attackers=(knight,))
    before = replace(
        squares_a1, squares=(*squares_a1.squares[:28], e4_a1, *squares_a1.squares[29:])
    )

    def known(family, node, record):
        return before if family == "squares" and node == _a1 else record

    assert reverify(a, BestStopsReply(), known).status is R


def test_defends_needs_the_reply_legal_after_the_best_move() -> None:
    """Rev. 3, B5: 1.Nf6+ defends e4 and gives check, so 1...dxe4 is not legal after it."""

    fen = "6k1/6pp/8/3p4/4P1N1/8/6PP/6K1 w - - 0 1"
    assert status(reply(fen, "Nf6+ gxf6 exd5 Kf7 Kf2 Ke7", DEFENDS_LP), "best_stops_reply_v1") is R


@pytest.mark.parametrize(
    ("fen", "l1", "lp", "played"),
    [
        # the king captures
        ("8/6pp/8/8/4Pk2/8/6PP/1N4K1 w - - 0 1", "Nc3 Ke5 Kf2 Kd4 Kf3 Kc4",
         "h3 Kxe4 Kf2 Kd3 Kf3 Kc2", "h3"),
        # en passant: the pawn the reply takes was not on the square
        ("6k1/6pp/8/8/4p3/8/3P2PP/1N4K1 w - - 0 1", "Nc3 Kf7 Nxe4 Ke6 Kf2 Ke5",
         "d4 exd3 Kf2 Kf7 Ke3 Ke6", "d4"),
        # a capture that promotes
        ("6k1/6pp/8/8/8/8/3p2PP/4R1K1 w - - 0 1", "Kf2 dxe1=Q+ Kxe1 Kf7 Kd2 Ke6",
         "h3 dxe1=Q+ Kh2 Qe5+ g3 Qe2+", "h3"),
    ],
)  # fmt: skip
def test_defends_refuted(fen: str, l1: str, lp: str, played: str) -> None:
    assert status(reply(fen, l1, lp, played), "best_stops_reply_v1") is R


@pytest.mark.parametrize(
    ("family", "at", "reason"),
    [("status", 3, "NOT_COMPUTED(status)"), ("move", 4, "NOT_COMPUTED(move)")],
)
def test_a_missing_status_or_move_record_is_inconclusive(family: str, at: int, reason: str) -> None:
    """EV1 review B1: `status` at B1 and `move` at C missing close the claim INCONCLUSIVE."""

    for fen, l1, lp in ((DEFENDS, DEFENDS_L1, DEFENDS_LP), (COVERS, COVERS_L1, COVERS_LP)):
        a = reply(fen, l1, lp)
        node = nodes(a)[at]

        def missing(f, n, record, node=node):
            return NotComputed("x") if f == family and n == node else record

        if family == "move" and fen == COVERS:
            continue  # COVERS reads no move at C
        verdict = reverify(a, BestStopsReply(), missing)
        assert (verdict.status, verdict.reason) == (I, reason)


@pytest.mark.parametrize(
    ("budget", "reason"),
    [(ReasoningBudget(max_rounds=1), "ROUND_LIMIT"), (ReasoningBudget(max_ensure_nodes=0), "BUDGET")],
)  # fmt: skip
def test_missing_exchange_records_close_inconclusive(budget, reason) -> None:
    for fen, l1, lp in ((DEFENDS, DEFENDS_L1, DEFENDS_LP), (COVERS, COVERS_L1, COVERS_LP)):
        a = reply(fen, l1, lp, budget=budget)
        c = claim(a, "best_stops_reply_v1")
        assert (c.verdict.status, c.verdict.reason) == (I, reason)
        assert plan_analysis(a).detail == ()  # never a square-level fallback, nothing rendered
        assert " covers " not in explain(a).text and " defends " not in explain(a).text


def test_no_node_room_closes_covers_inconclusive() -> None:
    a = reply(COVERS, COVERS_L1, COVERS_LP, budget=ReasoningBudget(max_rounds=1))
    zero = a.round_zero.tree.view(a.round_zero.rev)
    game_nodes = zero.request(1).budget.max_nodes - ReasoningBudget().max_tree_nodes
    exact = ReasoningBudget(max_tree_nodes=len(zero.nodes()) - game_nodes)  # round zero fills it
    tight = reply(COVERS, COVERS_L1, COVERS_LP, budget=exact)
    c = claim(tight, "best_stops_reply_v1")
    assert (c.verdict.status, c.verdict.reason) == (I, "BUDGET")


# -- 5: plan and guard (EV-D §4) ----------------------------------------------------------------


def test_the_detail_follows_each_comparison_it_can_explain() -> None:
    covers = reply(COVERS, COVERS_L1, COVERS_LP)  # after better_move_v1
    p = plan_analysis(covers)
    assert claims_template(covers, p.justification[0]) == "better_move_v1"
    assert p.detail == (claim(covers, "best_stops_reply_v1").id,)
    # after missed_gain_v1: a short best line leaves better_move_v1 undecided
    short = reply(DEFENDS, "Nc3 dxe4", DEFENDS_LP, good=(900, 100, 0), poor=(0, 600, 400))
    p = plan_analysis(short)
    assert claims_template(short, p.justification[0]) == "missed_gain_v1"
    assert p.detail == (claim(short, "best_stops_reply_v1").id,)
    text = explain(short).text
    assert "Instead, 1.Nc3 was stronger. 1.Nc3 defends the pawn on e4" in text
    # after better_alternative_v1: an inaccuracy below the MISS loss
    small = reply(DEFENDS, "Nc3 dxe4", DEFENDS_LP, good=(120, 880, 0), poor=DRAW)
    p = plan_analysis(small)
    assert claims_template(small, p.justification[0]) == "better_alternative_v1"
    assert p.detail == (claim(small, "best_stops_reply_v1").id,)
    assert "Instead, 1.Nc3 was better. 1.Nc3 defends the pawn on e4" in explain(small).text


def claims_template(a, claim_id: str) -> str:
    return next(c.hypothesis.template for c in a.claims if c.id == claim_id)


def test_the_detail_follows_the_miss_sentence() -> None:
    g = "6k1/3p2pp/8/4N3/8/8/6PP/6K1 b - - 0 1"  # Black's d6 attacks the knight and loses 130
    at_g = [line(g, "Kf8 Nd3 Ke7 Kf2", wdl(1000)), line(g, "d6 Nf3 Kf7 Kf2", wdl(870))]
    lines = [line(RESCUES, RESCUES_L1, wdl(1300)), line(RESCUES, RESCUES_LP, wdl(1000))]
    a = run(g, "h3", lines, before="d6", table={g: at_g}, multipv=2)
    assert [lb.kind.value for lb in a.labels] == ["miss"]
    p = plan_analysis(a)
    assert p.detail == (claim(a, "best_stops_reply_v1").id,)
    text = explain(a).text
    assert (
        "This is a missed opportunity; instead, 2.Nf3 was better: 2.Nf3 Kf7 3.Kf2 Ke6. 2.Nf3 saves the knight on e5 from 2...dxe5."
        in text
    )


@pytest.mark.parametrize("template", ["mate_missed_v1", "checks_draw_missed_v1"])
def test_no_detail_after_a_comparison_that_says_why(template: str) -> None:
    a = reply(COVERS, COVERS_L1, COVERS_LP)
    p = plan_analysis(a)
    better = p.justification[0]
    claims = tuple(
        replace(c, hypothesis=replace(c.hypothesis, template=template)) if c.id == better else c
        for c in a.claims
    )
    again = plan(a.round_zero.judgements, claims, a.relations, a.labels)
    assert again.justification[0] == better and again.detail == ()
    assert template not in DETAIL_AFTER


def test_the_guard_refuses_a_misplaced_detail() -> None:
    a = reply(COVERS, COVERS_L1, COVERS_LP)
    p = plan_analysis(a)
    detail = p.detail[0]
    for bad in (
        replace(p, justification=()),  # no comparison
        replace(p, detail=(detail, detail)),  # two details
        replace(p, detail=(claim(a, "better_move_v1").id,)),  # another template
        replace(p, detail=(claim(a, "checks_draw_missed_v1").id,)),  # not SUPPORTED
    ):
        with pytest.raises(GuardError, match="G4"):
            render(bad, a)
    b = missed()  # the comparison is checks_draw_missed_v1: a detail after it is refused
    refuted = claim(b, "best_stops_reply_v1")
    with pytest.raises(GuardError, match="G4"):
        render(replace(plan_analysis(b), detail=(refuted.id,)), b)


def test_a_sentence_may_open_only_with_a_numbered_move() -> None:
    from calliope.reasoning.render import phrase

    with pytest.raises(GuardError, match="G5"):
        phrase("best_stops_reply_v1", "sentence.rescues",
               {"best": "x", "piece": "the knight on e5", "reply": "1...dxe5"}, "0" * 64,
               sentence=True)  # fmt: skip


# -- 6: through the renderer, the store and the result document ---------------------------------


@pytest.mark.parametrize(
    "a",
    [
        pytest.param(lambda: checks(CHECKS3), id="checks_draw"),
        pytest.param(lambda: missed(), id="checks_draw_missed"),
        pytest.param(lambda: reply(COVERS, COVERS_L1, COVERS_LP), id="covers"),
        pytest.param(lambda: reply(DEFENDS, DEFENDS_L1, DEFENDS_LP), id="defends"),
        pytest.param(lambda: reply(RESCUES, RESCUES_L1, RESCUES_LP), id="rescues"),
    ],
)
def test_trace_store_and_reload(a) -> None:
    a = a()
    rendered = explain(a)
    traced = trace(plan_analysis(a), a)
    assert tuple(s.text for s in traced) == tuple(s.text for s in rendered.segments)
    tree_bytes, graph_bytes = save(a, rendered)
    loaded, again = load(FactEngine(), tree_bytes, graph_bytes)
    assert again == rendered and plan_analysis(loaded) == plan_analysis(a)
    assert save(loaded, again) == (tree_bytes, graph_bytes)


def test_the_stored_tree_keeps_the_node_without_a_search() -> None:
    a = reply(COVERS, COVERS_L1, COVERS_LP)
    _p, _a1, _r, _b1, c_ = nodes(a)
    tree_bytes, graph_bytes = save(a, explain(a))
    loaded, _ = load(FactEngine(), tree_bytes, graph_bytes)
    view = loaded.tree.view(loaded.rev)
    assert view.has_node(c_) and view.searches(c_) == ()
    assert not any(s.kind is SearchKind.SURVEY for s in view.searches(c_))


# -- 8: build identity ---------------------------------------------------------------------------


def test_a_graph_of_the_ea1_build_is_refused() -> None:
    new = {"checks_draw_v1", "checks_draw_missed_v1", "best_stops_reply_v1"}
    old = tuple(t for t in CATALOGUE_V1 if t.name not in new)
    a = reply(COVERS, COVERS_L1, COVERS_LP, templates=old)
    tree_bytes, graph_bytes = save(a, explain(a))
    with pytest.raises(StoredGraphError, match="re-analyse"):
        load(FactEngine(), tree_bytes, graph_bytes)
    current = reply(COVERS, COVERS_L1, COVERS_LP)
    assert new <= {name for name, _ in current.build.templates}
    assert current.build != a.build


def test_the_detail_is_part_of_the_plan_digest() -> None:
    from calliope.reasoning.planner import plan_digest

    a = reply(COVERS, COVERS_L1, COVERS_LP)
    p = plan_analysis(a)
    assert plan_digest(p) != plan_digest(replace(p, detail=()))
    assert isinstance(p.justification[1], LineSegment)
