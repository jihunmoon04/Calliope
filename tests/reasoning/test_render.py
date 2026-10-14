"""R3: the plan `selection_v1`, `phrases_en_v1` and the guarded renderer (R3-D §9 obligations)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from scripted import scripted as table_engine
from story import S, after, claim, line, run, uci
from test_quality import NO_WDL

from calliope.reasoning import GradingSpec
from calliope.reasoning.hypotheses import RelationKind
from calliope.reasoning.observer import JudgementStatus
from calliope.reasoning.planner import ExplanationPlan, plan, plan_digest
from calliope.reasoning.render import (
    CONNECTIVE,
    GuardError,
    Handle,
    explain,
    fmt_amount,
    phrase,
    render,
)

WIN, EVEN, LOST, DRAW = (1000, 0, 0), (300, 600, 100), (0, 0, 1000), (0, 1000, 0)
FORK = "4kb2/8/8/6n1/1P1B4/8/P7/4K3 w - - 0 1"
BACK = "r5k1/5ppp/8/8/8/8/4QPPP/4R1K1 w - - 0 1"
QUIET = "4k3/8/8/8/8/8/P7/4K3 w - - 0 1"
ONE = "k7/8/8/8/8/8/1q6/K7 w - - 0 1"


def wdl(e: int) -> tuple[int, int, int]:
    return (0, e, 1000 - e) if e <= 1000 else (e - 1000, 2000 - e, 0)


def fork():
    lines = [line(FORK, "Bb2 Ne6 Kd2 Kd7", EVEN),
             line(FORK, "a3 Bc5 b5 Be7 b6 Nf3+ Ke2 Nxd4+ Kd3 Nf5", LOST, cp=-500)]  # fmt: skip
    return run(FORK, "a3", lines, multipv=2)


def miss_mate():
    g = "r5k1/4rppp/8/8/8/8/4QPPP/4R1K1 b - - 0 1"
    at_g = [("g8f8", ("cp", 0), (200, 600, 200)), (uci(g, "Rb7")[0], ("mate", -2), (0, 0, 1000))]
    p = after(g, "Rb7")
    lines = [line(p, "Qe8+ Rxe8 Rxe8#", WIN, mate=2), line(p, "h3 h6 Qe3 Kh7", EVEN, cp=50)]
    return run(g, "h3", lines, before="Rb7", table={g: at_g}, multipv=2)


def great():
    return run(QUIET, "a3", [line(QUIET, "a3 Kd7", WIN), line(QUIET, "Kd2 Kd7", DRAW)], multipv=2)


def brilliant():
    x = after(BACK, "Qe8+ Rxe8")
    lines = [line(BACK, "Qe8+ Rxe8 Rxe8#", WIN, mate=2), line(BACK, "h3 h6 Qe3 Kh7", EVEN, cp=50)]
    return run(BACK, "Qe8+", lines, multipv=2, table={x: [line(x, "Rxe8#", WIN, mate=1)]})


def forced():
    return run(ONE, "Kxb2", [line(ONE, "Kxb2 Ka7", DRAW)], multipv=1)


def open_exchange():
    g = "r1bqkb1r/pp2np1p/2n3p1/2pp2B1/8/P1NP4/BPP2PPP/R2QK1NR b KQkq - 1 8"
    p = after(g, "h6")
    at_g = [line(g, "Qd6 Nf3", wdl(1050)), line(g, "h6 Bf6", wdl(750))]
    at_p = [line(p, "Bf6 Rg8 Bxe7 Bxe7 Qe2 Be6 O-O-O", wdl(1230)), line(p, "Bxe7", wdl(910))]
    return run(g, "Bxe7", at_p, before="h6", table={g: at_g}, multipv=2)


def undecided(analysis, reason: str):
    rz = analysis.round_zero
    j = replace(rz.judgements[0], status=JudgementStatus.INCONCLUSIVE, reason=reason, grade=None)
    return replace(analysis, round_zero=replace(rz, judgements=(j, *rz.judgements[1:])))


def plan_of(analysis, **changes) -> ExplanationPlan:
    p = plan(analysis.round_zero.judgements, analysis.claims, analysis.relations, analysis.labels)
    return replace(p, **changes)


# -- §8 golden examples, and determinism (obligation 7) -------------------------------------------

GOLDEN = {
    "fork": (fork, ("1.a3 is a blunder. Through the fork by the knight on f3 at 3...Nf3+, along the engine line, it loses the "
             "bishop on d4 at 4...Nxd4+ (net material loss over the line: at least 3 points). Instead, "
            "1.Bb2 was better: 1.Bb2 Ne6 2.Kd2 Kd7. "
             "Based on the engine line at depth 12 and piece exchanges judged by static "
             "exchange evaluation.")),
    "miss": (miss_mate, ("2.h3 is a blunder. This is a missed opportunity; instead, 2.Qe8+ was "
             "better: 2.Qe8+ Rxe8 3.Rxe8#. Based on the engine line at depth 12.")),
    "great": (great, ("1.a3 is the best move. This is a great move. Every other move, including "
              "1.Kd2, is clearly worse. Based on the engine's full search at depth 12.")),
    "mate": (lambda: run("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "Ra8#",
                         [line("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "Ra8#", WIN, mate=1),
                          line("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "h3 h6 Kh2 Kh7", WIN,
                               cp=300)], multipv=2),
             "1.Ra8# is the best move. It is checkmate."),
    "brilliant": (brilliant, ("1.Qe8+ is the best move. This is a brilliant move. Offering the queen "
                  "on e8 (net 4 points) to 1...Rxe8, it still holds after the capture, with "
                  "2.Rxe8#. The engine line leads to mate in 2: 1.Qe8+ Rxe8 2.Rxe8#. Every other "
                  "move, including 1.h3, is clearly worse. Based on the engine line at depth 12, "
                  "piece exchanges judged by static exchange evaluation, the engine's search after "
                  "the capture at depth 12 and the engine's full search at depth 12.")),
    "forced": (forced, "1.Kxb2 is the best move. It is the only legal move."),
    "missed gain": (open_exchange, ("9.Bxe7 is a mistake. This is a missed opportunity; instead, "
                    "9.Bf6 was stronger. Based on the 2 moves the engine reported.")),
}  # fmt: skip


@pytest.mark.parametrize("name", list(GOLDEN))
def test_golden_examples(name: str) -> None:
    build, text = GOLDEN[name]
    analysis = build()
    first, second = explain(analysis), explain(analysis)
    assert first.text == text
    assert first == second  # deterministic: the same segments and digest


def test_inconclusive_judgements() -> None:
    fen = "2r3k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1"
    lines = [("h2h3", ("cp", 0), None), ("e1c1", ("mate", -1), None)]
    analysis = run(fen, "Rc1", [], engine=table_engine({fen: lines}, identity=NO_WDL), multipv=2)
    assert explain(analysis).text == (
        "1.Rc1 could not be judged (the engine gave no win/draw/loss figures). It allows mate in "
        "one with 1...Rxc1#."
    )
    # review B2: FORCED needs no grade, so it survives an inconclusive judgement (example 5b)
    assert explain(undecided(forced(), "IRREGULAR_SEARCH")).text == (
        "1.Kxb2 could not be judged (the engine search was incomplete). It is the only legal move."
    )


# -- obligation 1: the planner --------------------------------------------------------------------


def test_the_plan_of_the_fork() -> None:
    analysis = fork()
    p = plan_of(analysis)
    loss, mech = claim(analysis, "material_loss_v2"), claim(analysis, "fork_v2")
    better = claim(analysis, "better_move_v1")
    assert (p.consequence, p.mechanism, p.purpose) == ((loss.id,), (mech.id,), ())
    assert p.justification == (better.id, better.hypothesis.operands[0])
    assert p.policy == "selection_v1" and len(plan_digest(p)) == 64


def test_an_associated_mechanism_is_never_selected() -> None:
    from test_catalogue_mechanisms import _loss

    analysis = _loss(FORK, "Be3", "Be3 Bd6 Kd2 Bxb4+ Kc2 Kd7", "Bb2 Ne6 Kd2 Kd7")
    explains = {r.source for r in analysis.relations if r.kind is RelationKind.EXPLAINS}
    p = plan_of(analysis)
    assert not p.mechanism or p.mechanism[0] in explains


def test_a_decided_judgement_without_claims_stands_alone() -> None:
    fen = "4k3/8/8/8/8/8/P7/4K3 w - - 0 1"
    analysis = run(fen, "a3", [line(fen, "a3 Kd7", WIN), line(fen, "a4 Kd7", (990, 10, 0))],
                   multipv=2)  # fmt: skip
    assert explain(analysis).text == "1.a3 is the best move."


def test_the_label_grounds_come_first() -> None:
    p = plan_of(great())
    assert p.purpose == p.label.grounds  # GREAT: only_move_v1 is the function
    m = miss_mate()
    pm = plan_of(m)
    better = claim(m, "better_move_v1")
    assert pm.justification[0] == better.id  # MISS prefers better_move_v1 over missed_gain_v1
    assert claim(m, "missed_gain_v1").id in pm.label.grounds


# -- obligations 2, 8: composition, labels and limits ---------------------------------------------


def test_brilliant_renders_the_pair_and_suppresses_the_line_sacrifice() -> None:
    analysis = brilliant()
    out = explain(analysis)
    offer, holds = claim(analysis, "piece_offer_v1"), claim(analysis, "capture_holds_v1")
    sources = [s.source for s in out.segments if s.source is not CONNECTIVE]
    assert offer.id in sources and holds.id in sources
    assert sources.index(offer.id) + 1 == sources.index(holds.id)  # lead, then its sentence
    for name in ("sacrifice_offer_v1", "sacrifice_sound_v1", "sacrifice_compensated_v1"):
        assert claim(analysis, name).verdict.status is S and claim(analysis, name).id not in sources
    assert (out.label_rule, out.label_provisional) == ("brilliant_p2", True)


def test_the_offer_alone_is_refused() -> None:
    analysis = brilliant()
    offer = claim(analysis, "piece_offer_v1")
    with pytest.raises(GuardError, match="G4"):
        render(plan_of(analysis, purpose=(offer.id,)), analysis)
    holds = claim(analysis, "capture_holds_v1")
    label = replace(plan_of(analysis).label, grounds=(holds.id,))
    with pytest.raises(GuardError, match="G4"):
        render(plan_of(analysis, label=label), analysis)


def test_a_missed_gain_without_a_miss_says_stronger_only() -> None:
    g = "4k3/8/8/8/8/8/P7/4K3 b - - 0 1"
    p = after(g, "Kd7")
    at_g = [line(g, "Kf7 Kd2", wdl(1000)), line(g, "Kd7 a3", wdl(1000))]
    analysis = run(g, "a3", [line(p, "Kd2 Kc6", wdl(1000)), line(p, "a3 Kc6", wdl(700))],
                   before="Kd7", table={g: at_g}, multipv=2)  # fmt: skip
    text = explain(analysis).text
    assert (
        text
        == "2.a3 is a mistake. Instead, 2.Kd2 was stronger. Based on the 2 moves the engine reported."
    )
    assert "missed" not in text


def test_rescue_as_the_function() -> None:
    fen = "4k3/8/8/3p4/4N3/8/8/4K3 w - - 0 1"
    lines = [line(fen, "Nc3 Kd7", WIN), line(fen, "Kd2 Kd7", (900, 100, 0))]  # no only move
    assert explain(run(fen, "Nc3", lines, multipv=2)).text == (
        "1.Nc3 is the best move. It moves the knight on c3 out of danger."
    )


def test_the_grade_sentence_is_the_same_under_both_gradings() -> None:
    v1 = great()
    v2 = run(QUIET, "a3", [line(QUIET, "a3 Kd7", WIN, cp=900), line(QUIET, "Kd2 Kd7", DRAW)],
             multipv=2, grading=GradingSpec(scale=1000))  # fmt: skip
    assert explain(v1).text.split(".")[:2] == explain(v2).text.split(".")[:2]


def test_a_stored_lead_is_refused() -> None:
    analysis = brilliant()
    sound, offer = claim(analysis, "sacrifice_sound_v1"), claim(analysis, "sacrifice_offer_v1")
    with pytest.raises(GuardError, match="G4"):
        render(plan_of(analysis, label=None, purpose=(offer.id, sound.id)), analysis)


def test_a_sacrifice_function_derives_its_lead() -> None:
    analysis = brilliant()
    sound, offer = claim(analysis, "sacrifice_sound_v1"), claim(analysis, "sacrifice_offer_v1")
    out = render(plan_of(analysis, label=None, purpose=(sound.id,)), analysis)
    sources = [s.source for s in out.segments]
    assert sources[sources.index(sound.id) - 2] == offer.id  # lead, connective, sentence
    assert "Giving up the queen on e2" in out.text or "Giving up the queen" in out.text


# -- obligations 9, 10: forcing, material and scoped wording --------------------------------------


@pytest.mark.parametrize(
    ("fen", "san", "sentence"),
    [
        ("4k3/8/8/8/8/8/8/R3K3 w - - 0 1", "Ra8+", "It gives check."),
        (
            "7k/8/5K2/8/8/8/8/R7 w - - 0 1",
            "Ra8+",
            "It gives check and leaves a single legal reply.",
        ),
        ("7k/5K2/8/8/8/8/8/6R1 w - - 0 1", "Rg2", "It leaves the opponent a single legal reply."),
    ],
)
def test_forcing_wording_follows_the_finding(fen: str, san: str, sentence: str) -> None:
    second = "Kd1" if fen.startswith("4k3") else "Ke6" if "R7" in fen else "Rg3"
    lines = [line(fen, san, (900, 100, 0)), line(fen, second, (900, 100, 0))]  # no only move
    analysis = run(fen, san, lines, multipv=2)
    assert claim(analysis, "forcing_v1").verdict.status is S
    text = explain(analysis).text
    assert sentence in text
    if sentence == "It gives check.":
        assert "forces" not in text and "single" not in text


def test_material_wording_follows_the_event() -> None:
    fen = "4k3/P7/8/8/8/8/8/4K3 w - - 0 1"
    lines = [line(fen, "a8=Q+ Kd7 Qb7+ Ke6", WIN, cp=900), line(fen, "Kd2 Kd7", DRAW)]
    text = explain(run(fen, "a8=Q+", lines, multipv=2)).text
    assert "promotes at 1.a8=Q+" in text and "wins" not in text
    capture = "4k3/8/8/3n4/8/8/8/3RK3 w - - 0 1"
    lines = [line(capture, "Rxd5 Ke7 Kf2 Kf6", WIN, cp=300), line(capture, "Kf2 Nf6", DRAW)]
    text = explain(run(capture, "Rxd5", lines, multipv=2)).text
    assert (
        "wins the knight on d5 at 1.Rxd5 (net material gain over the line: at least 3 points)"
        in text
    )
    assert "promotes" not in text


def test_scoped_wording() -> None:
    assert "The engine line leads to mate in 2" in explain(brilliant()).text  # review B5
    from calliope.reasoning.render import phrasebook

    mate = phrasebook()["sacrifice_compensated_v1"]["sentence.mate"][0]
    assert "faster" not in mate and "among those the engine reported" in mate


# -- obligations 3–6: slots, inflection, variants and guard mutations ------------------------------


def test_inflection() -> None:
    h = Handle("x", great().tree.view())
    assert (fmt_amount(h, 1), fmt_amount(h, 3)) == ("1 point", "3 points")
    sid = "0" * 64
    assert phrase("prevents_v1", "sentence.mate", {"count": "1"}, sid).startswith(
        "The other 1 move "
    )
    assert phrase("prevents_v1", "sentence.mate", {"count": "2"}, sid).startswith(
        "The other 2 moves"
    )


def test_variants(monkeypatch) -> None:
    import calliope.reasoning.render as r

    book = {"t": {"k": ["A {x}.", "B.", "C {y}."], "s": ["{x} starts."]}}
    monkeypatch.setattr(r, "phrasebook", lambda: book)
    assert phrase("t", "k", {"x": "1"}, "00000001") == "B."  # usable: A, B → index 1 mod 2
    assert phrase("t", "k", {"x": "1"}, "00000000") == "A 1."
    assert phrase("t", "k", {}, "00000000") == "B."  # A and C unbound, skipped
    with pytest.raises(GuardError, match="G5"):
        phrase("t", "missing", {}, "0")
    with pytest.raises(GuardError, match="G5"):
        phrase("t", "s", {}, "0")  # no usable variant
    with pytest.raises(GuardError, match="G5"):
        phrase("t", "s", {"x": "1"}, "0", sentence=True)  # a sentence beginning with a slot


def test_guard_mutations() -> None:
    analysis = fork()
    p = plan_of(analysis)
    refuted = next(c for c in analysis.claims if c.verdict.status.value == "refuted")
    with pytest.raises(GuardError, match="G4"):
        render(replace(p, consequence=(refuted.id,)), analysis)
    other = claim(analysis, "better_move_v1")
    with pytest.raises(GuardError, match="G4"):
        render(replace(p, mechanism=(other.id,)), analysis)  # no EXPLAINS to the consequence
    view = analysis.tree.view(analysis.rev)
    h = Handle(other.id, view, other.hypothesis.operands)
    with pytest.raises(GuardError, match="G3"):
        h.check(claim(analysis, "fork_v2").id)  # another claim's reference
    with pytest.raises(GuardError, match="G1"):
        h.node(analysis.round_zero.subject.parent.__class__("n_" + "0" * 24))


def test_segments_keep_their_sources() -> None:
    out = explain(fork())
    assert all(s.source is not None for s in out.segments)
    assert all(s.text == " " for s in out.segments if s.source is CONNECTIVE)
    assert out.language == "en" and out.phrasebook == "phrases_en_v1"
    assert out.text.count(". ") + 1 <= 9  # H1: at most nine sentences


def test_a_truncated_line_ends_its_sentence_without_a_period() -> None:
    """R3-D §16 (owner, 2026-10-12): "… 4.Kf3 ..." closes the sentence; no "...."."""

    best = "Bb2 Ne6 Kd2 Kd7 Ke3 Ke7 Kf3 Kd6"  # eight plies, shown up to six
    lines = [
        line(FORK, best, EVEN),
        line(FORK, "a3 Bc5 b5 Be7 b6 Nf3+ Ke2 Nxd4+ Kd3 Nf5", LOST, cp=-500),
    ]
    text = explain(run(FORK, "a3", lines, multipv=2)).text
    assert "1.Bb2 Ne6 2.Kd2 Kd7 3.Ke3 Ke7 ... Based on" in text and "...." not in text


def test_the_amount_is_a_guaranteed_size_not_the_total() -> None:
    """R3 review B1: Δp = −5 (the rook), Δ1 = −1, so the claim's amount is min(5, 4) = 4."""

    from story import finding

    from calliope.reasoning.findings import MaterialFinding

    fen = "7k/8/8/3q4/4R3/8/P7/6K1 w - - 0 1"
    lines = [line(fen, "Re2 Qxa2 Kf1 Kg8", EVEN), line(fen, "Kf1 Qxe4 Kg1 Kg8", LOST, cp=-500)]
    analysis = run(fen, "Kf1", lines, multipv=2)
    found = finding(claim(analysis, "material_loss_v2"), MaterialFinding)
    assert (found.amount.points, found.played.delta) == (4, -5)
    text = explain(analysis).text
    assert "(net material loss over the line: at least 4 points)" in text and "total" not in text


def test_a_label_not_made_by_the_analysis_is_refused() -> None:
    """R3 review B2: render() takes only the analysis's own labels, with SUPPORTED grounds."""

    from calliope.reasoning.labels import Label, LabelKind

    analysis = fork()
    p = plan_of(analysis)
    forged = Label(LabelKind.FORCED, p.subject, (), "label_v2", "forced_v1")
    with pytest.raises(GuardError, match="G4"):
        render(replace(p, label=forged), analysis)
    b = brilliant()
    real = plan_of(b).label
    refuted = next(c for c in b.claims if c.verdict.status.value == "refuted")
    with pytest.raises(GuardError, match="G4"):
        render(plan_of(b, label=replace(real, grounds=(refuted.id, real.grounds[1]))), b)
    labelled = replace(b, labels=(replace(real, grounds=(refuted.id, real.grounds[1])),))
    with pytest.raises(GuardError, match="G4"):  # in the analysis, but with a REFUTED ground
        render(plan_of(b, label=labelled.labels[0]), labelled)


# -- R3-D §17 (owner, 2026-10-12): MISS after what the move did; agreement; events later in the line


def test_a_miss_is_told_after_what_the_move_did() -> None:
    g = "7k/p3q3/8/8/8/8/8/R2Q3K b - - 0 1"
    p = after(g, "Qd8")  # Black's queen now hangs to Qxd8+
    at_g = [line(g, "Kg8 Qd5+ Kh7", wdl(800)), line(g, "Qd8 Qxd8+", wdl(100))]
    at_p = [line(p, "Qxd8+ Kh7 Qd3+ Kg8", wdl(2000)), line(p, "Rxa7 Qxd1+ Kh2 Qd6+ Kg1", wdl(1300))]
    analysis = run(g, "Rxa7", at_p, before="Qd8", table={g: at_g}, multipv=2)
    assert explain(analysis).text == (
        "2.Rxa7 is a blunder. With the rook on a1 no longer defending the queen on d1, it loses the "
        "queen on d1 at 2...Qxd1+ (net material loss over the line: at least 8 points). This is a "
        "missed opportunity; instead, 2.Qxd8+ was better: 2.Qxd8+ Kh7 3.Qd3+ Kg8. Based on the "
        "engine line at depth 12 and piece exchanges judged by static exchange evaluation."
    )


def test_a_single_alternative_agrees_with_its_verb() -> None:
    fen = "4k3/7p/8/4b3/8/8/7P/R3K3 w - - 0 1"
    lines = [
        line(fen, "Ra4 Kd7 Kd2 Kd6", EVEN),
        line(fen, "Kd2 Bxa1 Kc2 Be5", (200, 600, 200), cp=-500),
    ]  # close: no only move
    text = explain(run(fen, "Ra4", lines, multipv=2)).text
    assert "The only other move the engine reported loses at least 5 points." in text
    assert "1 move" not in text and "all lose" not in text


def test_an_event_later_in_the_line_says_so() -> None:
    assert "along the engine line, it loses the bishop on d4 at 4...Nxd4+" in explain(fork()).text
    fen = "7k/8/8/3q4/4R3/8/P7/6K1 w - - 0 1"  # the rook goes at once, on the reply
    lines = [line(fen, "Re2 Qxa2 Kf1 Kg8", EVEN), line(fen, "Kf1 Qxe4 Kg1 Kg8", LOST, cp=-500)]
    text = explain(run(fen, "Kf1", lines, multipv=2)).text
    assert "it loses the rook on e4 at 1...Qxe4" in text and "along the engine line" not in text
