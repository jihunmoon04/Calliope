"""`calliope_result_v1`: the builder, `render.trace` and the schema (AR-D §7 obligations)."""

from __future__ import annotations

from dataclasses import replace

import jsonschema
import pytest
from corpus_case import analyse, cases
from result_input import engine_run, game_input, ply_input
from story import after, claim, line, run
from synthetic import engine as synthetic_engine

from calliope.facts import EngineProfile, FactEngine, RootSpec
from calliope.reasoning import (
    AnalysisRequest,
    GradingSpec,
    Reasoner,
    RenderedExplanation,
    Segment,
    build_digest,
    explain,
    plan_analysis,
    trace,
)
from calliope.results import Bundle, EngineRun, ResultError, dumps, game_result, schema

FORK = "4kb2/8/8/6n1/1P1N4/8/P7/4K3 w - - 0 1"
BACK = "r5k1/5ppp/8/8/8/8/4QPPP/4R1K1 w - - 0 1"
EVEN, LOST, WIN = (300, 600, 100), (0, 0, 1000), (1000, 0, 0)
GAME = "e4 e5 Nf3 Nc6 Bb5"


def validate(doc: dict) -> dict:
    jsonschema.validate(doc, schema(), cls=jsonschema.Draft202012Validator)
    return doc


def result(analysis, fen: str, sans, **kwargs) -> dict:
    game = game_input(fen, sans, kwargs.pop("headers", None))
    return validate(game_result(game, engine_run(analysis), [ply_input(analysis, **kwargs)]))


def corpus_result(case: dict):
    a = analyse(case)
    return a, result(a, case["fen"], [*case.get("before", "").split(), case["played"]])


def fork(best: str = "Nb3 Ne6 Kd2 Kd7", **kwargs):
    lines = [line(FORK, best, EVEN),
             line(FORK, "a3 Bc5 b5 Be7 b6 Nf3+ Ke2 Nxd4+ Kd3 Nf5", LOST, cp=-500)]  # fmt: skip
    return run(FORK, "a3", lines, multipv=2, **kwargs)


def segment(doc: dict, a, template: str) -> dict:
    cid = claim(a, template).id
    return next(s for s in doc["plies"][-1]["segments"] if s.get("claim") == cid)


def synthetic_game(plies, *, root=None, moves=GAME, grading=None, port=None):
    """Analyses of `plies` of a synthetic-engine game, as `tools/explain_game` runs them."""

    port = port or synthetic_engine()
    root, grading = root or RootSpec(), grading or GradingSpec()
    out = []
    for ply in plies:
        request = AnalysisRequest(root, tuple(moves.split()), ply, EngineProfile(),
                                  grading=grading)  # fmt: skip
        out.append(Reasoner(FactEngine(engine=port)).analyse(request))
    return out


def build(game, analyses, run_=None, **kwargs) -> dict:
    run_ = run_ or engine_run(analyses[0])
    return validate(game_result(game, run_, [ply_input(a, **kwargs) for a in analyses]))


# -- 1, 2, 7g: determinism, text and segments, trace = render (every corpus case) ----------------


@pytest.mark.parametrize("case", cases(), ids=lambda c: c["name"])
def test_every_corpus_case_projects_and_validates(case: dict) -> None:
    a, doc = corpus_result(case)
    again = corpus_result(case)[1]
    assert dumps(doc) == dumps(again)  # pure: equal JSON twice
    ply = doc["plies"][-1]
    assert ply["text"] == "".join(s["text"] for s in ply["segments"]) == explain(a).text
    ids = {c["id"] for c in ply["claims"]}
    for s in ply["segments"]:
        assert {s.get("claim"), *s.get("claims", ())} - {None} <= ids
    rendered = explain(a).segments
    traced = trace(plan_analysis(a), a)
    assert [(s.text, s.source) for s in traced] == [(s.text, s.source) for s in rendered]
    assert doc["provenance"]["build_digest"] == build_digest(a.build)
    assert doc["provenance"]["label_rules"] == {
        "brilliant": "brilliant_p2", "great": "great_p2", "miss": "miss_p2"
    }  # fmt: skip
    assert not any(c["status"] == "refuted" for c in ply["claims"])


# -- 3, 7d: refs ----------------------------------------------------------------------------------


def test_the_fork_segment_names_exactly_the_piece_and_the_move() -> None:
    a = fork()
    doc = result(a, FORK, ["a3"])
    view = a.tree.view(a.rev)
    seg = segment(doc, a, "fork_v1")
    assert seg["text"].startswith("Through the fork by the knight on f3 at 3...Nf3+")
    piece, move = seg["refs"]  # exactly two: the actor and the move, in slot order
    assert (piece["kind"], piece["square"], piece["piece"], piece["color"]) == (
        "piece", "f3", "knight", "black"
    )  # fmt: skip
    assert piece["fen"] == after(FORK, "a3 Bc5 b5 Be7 b6 Nf3+")  # the position at its node
    assert (move["kind"], move["uci"], move["san"]) == ("move", "g5f3", "Nf3+")
    assert move["fen"] == after(FORK, "a3 Bc5 b5 Be7 b6")  # the position before the move
    # the claim's other references are left out: the forked targets are not in the text
    finding = claim(a, "fork_v1").verdict.findings[0]
    assert view.node(finding.actor.node).fen == piece["fen"]
    assert finding.targets and all(f"on {x.square}" not in seg["text"] for x in finding.targets)
    assert {r.get("square") for r in seg["refs"]} == {"f3", None}


def test_the_judgement_and_the_better_move_name_their_moves_and_line() -> None:
    a = fork()
    doc = result(a, FORK, ["a3"])
    judgement = doc["plies"][0]["segments"][0]
    assert judgement["source"] == "judgement"
    assert judgement["refs"] == [{"kind": "move", "uci": "a2a3", "san": "a3", "fen": FORK}]
    better = segment(doc, a, "better_move_v1")
    best, line_ = better["refs"]
    assert (best["uci"], best["san"], best["fen"]) == ("d4b3", "Nb3", FORK)
    assert line_["kind"] == "line" and line_["fen"] == FORK and not line_["truncated"]
    assert [m["san"] for m in line_["moves"]] == ["Nb3", "Ne6", "Kd2", "Kd7"]  # four, all shown
    assert all(s["refs"] == [] for s in doc["plies"][0]["segments"]
               if s["source"] in ("connective", "scope"))  # fmt: skip


def test_the_new_claims_name_their_capture_and_their_move() -> None:
    """EA-D §6.7: `material_gain_v2` and `better_alternative_v1` through `trace` into the
    document, with the references their sentences name."""

    by_name = {c["name"]: c for c in cases()}
    a, doc = corpus_result(by_name["later_gain"])
    gain = segment(doc, a, "material_gain_v2")
    assert gain["text"].startswith("Along the engine line, it wins the pawn on d5 at 2.Nxd5")
    victim, capture = gain["refs"]
    fen = by_name["later_gain"]["fen"]
    assert (victim["kind"], victim["square"], victim["piece"]) == ("piece", "d5", "pawn")
    assert (capture["kind"], capture["uci"], capture["san"]) == ("move", "c3d5", "Nxd5")
    assert capture["fen"] == after(fen, "Nc3 Kd7")
    a, doc = corpus_result(by_name["better_alternative"])
    alt = segment(doc, a, "better_alternative_v1")
    assert alt["text"] == "Instead, 2.Kd2 was better."
    (best,) = alt["refs"]
    case = by_name["better_alternative"]
    assert (best["uci"], best["san"]) == ("e1d2", "Kd2")
    assert best["fen"] == after(case["fen"], case["before"])


def test_a_long_line_lists_only_the_six_plies_the_text_shows() -> None:
    a = fork("Nb3 Ne6 Kd2 Kd7 Ke3 Ke7 Kf3 Kf6")  # eight plies
    doc = result(a, FORK, ["a3"])
    seg = segment(doc, a, "better_move_v1")
    assert seg["text"].endswith("1.Nb3 Ne6 2.Kd2 Kd7 3.Ke3 Ke7 ...")
    line_ = seg["refs"][1]
    assert [m["san"] for m in line_["moves"]] == ["Nb3", "Ne6", "Kd2", "Kd7", "Ke3", "Ke7"]
    assert line_["truncated"] is True


def test_a_zero_ply_line_holds_the_first_move_it_rendered() -> None:
    from calliope.reasoning import LineSegment
    from calliope.reasoning.render import Handle, fmt_line
    from calliope.results.document import _ref

    a = fork()
    view = a.tree.view(a.rev)
    better = claim(a, "better_move_v1")
    whole = better.hypothesis.operands[0]
    assert isinstance(whole, LineSegment)
    empty = LineSegment(whole.line, whole.first, whole.first)  # the line cut before its first ply
    text = fmt_line(Handle(better.id, view, empty), empty)
    assert text == "1.Nb3 ..."
    ref = _ref(view, text.ref)
    assert ref == {"kind": "line", "fen": FORK, "moves": [{"uci": "d4b3", "san": "Nb3"}],
                   "truncated": True}  # fmt: skip


def test_a_square_ref_carries_its_fen() -> None:
    """No `phrases_en_v1` slot names a bare square yet; the schema's square ref needs its FEN."""

    _, doc = corpus_result(next(c for c in cases() if c["name"] == "fork_blunder"))
    doc["plies"][0]["segments"][0]["refs"].append({"kind": "square", "square": "e4", "fen": FORK})
    validate(doc)
    del doc["plies"][0]["segments"][0]["refs"][-1]["fen"]
    with pytest.raises(jsonschema.ValidationError):
        validate(doc)


# -- 4, 7c: evaluation and grade basis ------------------------------------------------------------


def test_a_black_move_is_scored_from_whites_view() -> None:
    fen = "3k1b2/8/8/6n1/1P1N4/8/P7/4K3 b - - 0 1"
    lines = [line(fen, "Ke7 Nb3", EVEN, cp=120), line(fen, "Ke8 a3", EVEN, cp=40)]
    a = run(fen, "Ke8", lines, multipv=2)
    ev = result(a, fen, ["Ke8"])["plies"][0]["evaluation"]
    assert (ev["played"], ev["best"]) == ({"cp": -40}, {"cp": -120})  # Black's +40 is White's -40
    assert ev["best_move"] == {"san": "Ke7", "uci": "d8e7"}
    assert ev["grade_basis"] == "expected_points"


def test_mate_scores_and_a_slower_mate() -> None:
    lines = [line(BACK, "Qe8+ Rxe8 Rxe8#", WIN, mate=2),
             line(BACK, "Qb5 h6 Qe8+ Rxe8 Rxe8#", WIN, mate=3)]  # fmt: skip
    a = run(BACK, "Qb5", lines, multipv=2)
    ply = result(a, BACK, ["Qb5"])["plies"][0]
    ev = ply["evaluation"]
    assert (ev["played"], ev["best"], ev["loss"]) == ({"mate": 3}, {"mate": 2}, 0)
    assert ev["grade_basis"] == "mate_distance" and ply["grade"] != "best"
    black = "4r1k1/4qppp/8/8/8/8/5PPP/R5K1 b - - 0 1"  # the mirror: Black mates
    lines = [line(black, "Qe1+ Rxe1 Rxe1#", WIN, mate=2), line(black, "h6 h3", EVEN, cp=0)]
    a = run(black, "Qe1+", lines, multipv=2)
    ev = result(a, black, ["Qe1+"])["plies"][0]["evaluation"]
    assert ev["played"] == {"mate": -2} and ev["grade_basis"] == "best_move"


def test_the_grade_basis_follows_the_grade() -> None:
    by_name = {c["name"]: c for c in cases()}
    assert corpus_result(by_name["quiet_best_move"])[1]["plies"][0]["evaluation"][
        "grade_basis"] == "best_move"  # fmt: skip
    fork_doc = corpus_result(by_name["fork_blunder"])[1]["plies"][0]
    assert (fork_doc["grade"], fork_doc["evaluation"]["grade_basis"]) == (
        "blunder", "expected_points"
    )  # fmt: skip


def test_an_inconclusive_judgement_has_no_evaluation() -> None:
    _, doc = corpus_result(next(c for c in cases() if c["name"] == "inconclusive_exact"))
    ply = doc["plies"][-1]
    assert (ply["status"], ply["grade"], ply["evaluation"]) == (
        "inconclusive", None, {"grade_basis": None}
    )  # fmt: skip
    assert ply["reason"]
    assert doc["summary"][ply["side"]]["inconclusive"] == 1


# -- 5: labels ------------------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "label"), [
    ("forced", {"kind": "forced", "rule": "forced_v1", "provisional": False}),
    ("brilliant_queen_sacrifice",
     {"kind": "brilliant", "rule": "brilliant_p2", "provisional": True}),
    ("missed_mate", {"kind": "miss", "rule": "miss_p2", "provisional": True}),
])  # fmt: skip
def test_labels(name: str, label: dict) -> None:
    _, doc = corpus_result(next(c for c in cases() if c["name"] == name))
    ply = doc["plies"][-1]
    assert ply["label"] == label
    assert doc["summary"][ply["side"]]["labels"][label["kind"]] == 1
    for s in ply["segments"]:
        if s["source"] == "label":  # the label segment references the played move only
            assert s["refs"] == [{"kind": "move", "uci": ply["uci"], "san": ply["san"],
                                  "fen": ply["fen_before"]}]  # fmt: skip


# -- 6, 7f: the grading block ---------------------------------------------------------------------


RATED = GradingSpec(white_rating=1500, black_rating=1480, rating_pool="chesscom",
                    time_class="rapid")  # fmt: skip


@pytest.mark.parametrize(("spec", "expect"), [
    (GradingSpec("quality_v1"), {"policy": "quality_v1", "curve": None, "fallback": False}),
    (RATED, {"policy": "quality_v2", "model": "monotone_v1", "source": "table",
             "pool": "chesscom", "fallback": False}),
    (GradingSpec(scale=900), {"policy": "quality_v2", "model": "logistic10", "source": "explicit",
                              "scale": 900, "pool": None, "fallback": False}),
    (GradingSpec(), {"policy": "quality_v2", "model": "logistic10", "source": "default",
                     "scale": 1000, "pool": None, "fallback": True}),
])  # fmt: skip
def test_the_grading_block(spec: GradingSpec, expect: dict) -> None:
    grading = result(fork(grading=spec), FORK, ["a3"])["grading"]
    assert grading["policy"] == expect.pop("policy")
    assert grading["fallback"] is expect.pop("fallback")
    if "curve" in expect:
        assert grading["curve"] is None
        return
    curve = grading["curve"]
    assert {k: curve.get(k) for k in expect} == expect
    if curve["source"] == "table":
        assert {"table", "time_class", "band", "rating"} <= set(curve) and "scale" not in curve
    else:
        assert "table" not in curve and "band" not in curve
    assert curve["clamped"] in (True, False)


def test_an_invalid_grading_combination_is_rejected_by_the_schema() -> None:
    doc = result(fork(grading=RATED), FORK, ["a3"])
    doc["grading"]["curve"]["scale"] = 1000  # monotone_v1 with a scale
    with pytest.raises(jsonschema.ValidationError):
        validate(doc)
    doc = result(fork(grading=GradingSpec()), FORK, ["a3"])
    doc["grading"]["fallback"] = False  # the default curve is always a fallback
    with pytest.raises(jsonschema.ValidationError):
        validate(doc)


def test_an_unknown_field_still_validates() -> None:
    """7h: every object allows additional properties (G7); the builder never emits one."""

    doc = result(fork(), FORK, ["a3"])
    doc["future"] = {"x": 1}
    doc["plies"][0]["accuracy"] = 97
    doc["plies"][0]["segments"][0]["refs"][0]["arrow"] = "green"
    validate(doc)


# -- 7a, 7b, 7k: a partial game, provenance, a custom start ---------------------------------------


def test_a_partial_analysis_keeps_the_whole_game() -> None:
    analyses = synthetic_game([3, 4])
    doc = build(game_input(FEN_START, GAME), analyses, bundle=Bundle("a" * 64, "b" * 64, False))
    assert [m["san"] for m in doc["game"]["moves"]] == GAME.split()
    assert [(p["ply"], p["move_number"], p["side"]) for p in doc["plies"]] == [
        (3, 2, "white"), (4, 2, "black")
    ]  # fmt: skip
    assert doc["plies"][0]["bundle"] == {"tree": "a" * 64, "graph": "b" * 64, "stored": False}
    total = sum(sum(c["grades"].values()) + c["inconclusive"] for c in doc["summary"].values())
    assert total == 2


@pytest.mark.parametrize("bundle", [
    Bundle("invalid", "b" * 64, True),
    Bundle("a" * 64, "B" * 64, True),  # upper case is not the schema's form
    Bundle("a" * 64, "b" * 63, False),
    Bundle("a" * 64, "b" * 64, 1),  # not a boolean
    Bundle("a" * 64, "b" * 64, "yes"),
])  # fmt: skip
def test_a_malformed_bundle_is_refused(bundle: Bundle) -> None:
    """AR1 review B1: what `game_result` returns always validates; a bad bundle is refused."""

    (one,) = synthetic_game([1])
    with pytest.raises(ResultError, match="bundle"):
        game_result(game_input(FEN_START, GAME), engine_run(one), [ply_input(one, bundle=bundle)])


def test_the_engine_block_is_the_run_and_a_foreign_identity_is_refused() -> None:
    analyses = synthetic_game([1])
    run_ = engine_run(analyses[0])
    doc = build(game_input(FEN_START, GAME), analyses, run_)
    engine = doc["provenance"]["engine"]
    assert (engine["name"], engine["binary_sha256"]) == (run_.identity.name,
                                                         run_.identity.binary_sha256)  # fmt: skip
    assert engine["profile"] == {"name": "d12_mpv5_v1", "depth": 12, "time_cap_ms": 2000,
                                 "multipv": 5, "threads": 1, "hash_mb": 16}  # fmt: skip
    foreign = EngineRun(replace(run_.identity, binary_sha256="0" * 64), run_.profile)
    with pytest.raises(ResultError, match="another engine"):
        build(game_input(FEN_START, GAME), analyses, foreign)
    other_profile = EngineRun(run_.identity, replace(run_.profile, depth=16))
    with pytest.raises(ResultError, match="profile"):
        build(game_input(FEN_START, GAME), analyses, other_profile)


def test_a_custom_start_numbers_its_plies_from_the_fen() -> None:
    fen = "4k3/8/8/8/8/8/4P3/4K3 b - - 0 17"
    analyses = synthetic_game([1, 2], root=RootSpec(fen=fen), moves="Kd7 Kd2")
    doc = build(game_input(fen, "Kd7 Kd2"), analyses)
    assert [(p["move_number"], p["side"]) for p in doc["plies"]] == [(17, "black"), (18, "white")]
    assert doc["plies"][0]["text"].startswith("17...Kd7")


# -- 7e, 7i, 7j: cross-checks ---------------------------------------------------------------------

FEN_START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def test_another_game_or_start_is_refused() -> None:
    analyses = synthetic_game([2])
    with pytest.raises(ResultError, match="not the game's"):
        build(game_input(FEN_START, "e4 c5 Nf3"), analyses)
    other = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w Kkq - 0 1"
    with pytest.raises(ResultError, match="starts elsewhere"):
        build(game_input(other, GAME), analyses)


def test_a_target_off_by_one_is_refused() -> None:
    (four,) = synthetic_game([4])
    game = game_input(FEN_START, GAME)
    with pytest.raises(ResultError, match="is of ply 4"):
        game_result(game, engine_run(four), [replace(ply_input(four), ply=5)])


def test_mixed_builds_are_refused() -> None:
    one, two = synthetic_game([1, 2])
    templates = (*two.build.templates, ("extra_v1", "1"))
    two = replace(two, build=replace(two.build, templates=templates))
    with pytest.raises(ResultError, match="another reasoner build"):
        build(game_input(FEN_START, GAME), [one, two])


def test_pre_root_moves_compare_the_root_nodes_fen() -> None:
    root = RootSpec(moves=("e2e4",))
    analyses = synthetic_game([1, 2], root=root, moves="e5 Nf3")
    after_e4 = after(FEN_START, "e4")
    doc = build(game_input(after_e4, "e5 Nf3"), analyses)  # the root node: after 1.e4
    assert doc["game"]["start_fen"] == after_e4 and doc["plies"][0]["move_number"] == 1
    before_e4 = replace(game_input(after_e4, "e5 Nf3"), start_fen=FEN_START)
    with pytest.raises(ResultError, match="FEN chain|starts elsewhere"):
        build(before_e4, analyses)  # OpenRequest.root.fen, before 1.e4: refused
    with pytest.raises(ResultError, match="starts elsewhere"):
        build(
            game_input(FEN_START, "e4 e5 Nf3"), analyses
        )  # the game from before 1.e4  # before 1.e4: refused


def test_duplicate_plies_two_gradings_and_a_broken_chain_are_refused() -> None:
    (one,) = synthetic_game([1])
    game = game_input(FEN_START, GAME)
    with pytest.raises(ResultError, match="strictly increasing"):
        game_result(game, engine_run(one), [ply_input(one), ply_input(one)])
    (rated,) = synthetic_game([2], grading=RATED)
    with pytest.raises(ResultError, match="another grading"):
        game_result(game, engine_run(one), [ply_input(one), ply_input(rated)])
    moves = list(game.moves)
    moves[1] = replace(moves[1], fen_before=moves[0].fen_before)
    with pytest.raises(ResultError, match="FEN chain"):
        game_result(replace(game, moves=tuple(moves)), engine_run(one), [ply_input(one)])


def test_consistently_altered_fens_are_refused() -> None:
    """7i: the chain is intact, but the analysed ply's two FENs are not the tree's."""

    (two,) = synthetic_game([2])
    game = game_input(FEN_START, GAME)
    moves = list(game.moves)
    alt_before = moves[1].fen_before.rsplit(" ", 1)[0] + " 9"
    alt_after = moves[1].fen_after.rsplit(" ", 1)[0] + " 9"
    moves[0] = replace(moves[0], fen_after=alt_before)
    moves[1] = replace(moves[1], fen_before=alt_before, fen_after=alt_after)
    moves[2] = replace(moves[2], fen_before=alt_after)
    with pytest.raises(ResultError, match="FENs are not the analysis's"):
        game_result(replace(game, moves=tuple(moves)), engine_run(two), [ply_input(two)])


def test_a_foreign_or_altered_rendering_is_refused() -> None:
    one, two = synthetic_game([1, 2])
    game = game_input(FEN_START, GAME)
    with pytest.raises(ResultError, match="rendering"):
        game_result(game, engine_run(one), [ply_input(one, rendered=explain(two))])
    mine = explain(one)
    first = mine.segments[0]
    changed = (Segment(first.text + "!", first.source), *mine.segments[1:])
    altered = RenderedExplanation(mine.plan_digest, mine.language, mine.phrasebook, changed,
                                  mine.label_rule, mine.label_provisional)  # fmt: skip
    with pytest.raises(ResultError, match="rendering"):
        game_result(game, engine_run(one), [ply_input(one, rendered=altered)])


# -- 7: boundaries live in tests/test_package_boundaries.py ---------------------------------------


def test_headers_are_projected_in_order() -> None:
    headers = {"site": "https://www.chess.com/game/live/1", "white": "A", "black": "B",
               "white_rating": 1500, "result": "1-0", "black_rating": None}  # fmt: skip
    doc = build(game_input(FEN_START, GAME, headers), synthetic_game([1]))
    assert list(doc["game"]["headers"]) == ["white", "black", "white_rating", "site", "result"]
    with pytest.raises(ResultError, match="integer"):
        build(game_input(FEN_START, GAME, {"white_rating": "1500"}), synthetic_game([1]))
