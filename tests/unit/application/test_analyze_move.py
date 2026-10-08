"""G0 AnalyzeMoveService orchestration over deterministic fakes (P3 guarantees retained)."""

import json
from dataclasses import fields, replace

import pytest
from _g0_fakes import FEN, MOVE, P7_MARKER, build, empty_outcome, position, request

from calliope.application.explanation import MoveExplanationOutcome
from calliope.application.projection import project_claims
from calliope.contracts import (
    PUBLIC_SCHEMA_VERSION,
    AnalysisBudget,
    CommentaryView,
    OutputMode,
)
from calliope.domain.engine import EngineLimit, EngineSettings
from calliope.domain.explanation import EvidenceBundle
from calliope.errors import (
    ClaimProjectionError,
    EngineAnalysisError,
    ExplanationGraphError,
    ExplanationRenderError,
    FeatureUnavailableError,
    IllegalMoveError,
    IncompatibleAnalysisError,
    IncompatibleBadMoveContextError,
    InvalidAnalysisBudgetError,
    InvalidFenError,
    UnsupportedOutputModeError,
)
from calliope.services.explanation import ExplanationSelector, GraphBuilder

DEFAULT = EngineSettings(limit=EngineLimit(depth=12), multipv=5, threads=1, hash_mb=16)
PLAYED = replace(DEFAULT, multipv=1)


# ---- order, budget and fixed engine options -----------------------------------------------------


def test_orchestration_order_and_default_budget():
    world = build()
    result = world.service.execute(request())
    assert world.log == [
        ("fen", FEN),
        ("move", MOVE.uci),
        ("acquire",),
        ("engine", DEFAULT, None),
        ("engine", PLAYED, (MOVE,)),
        ("judge",),
        ("explain", world.judge.quality),
        ("engine", P7_MARKER, (MOVE,)),
        ("engine", P7_MARKER, (MOVE,)),
        ("release",),
    ]
    assert result.schema_version == PUBLIC_SCHEMA_VERSION == "0.2"


def test_judgement_options_are_fixed_and_budget_is_preserved():
    world = build()
    world.service.execute(request(AnalysisBudget(depth=16, nodes=100000, time_ms=500, multipv=3)))
    first, second = world.engine.calls[0][1], world.engine.calls[1][1]
    assert first == EngineSettings(
        limit=EngineLimit(depth=16, nodes=100000, time_ms=500), multipv=3, threads=1, hash_mb=16
    )
    assert second == replace(first, multipv=1)
    assert world.engine.calls[1][2] == (MOVE,)


def test_default_depth_not_added_when_explicit_limit():
    world = build()
    world.service.execute(request(AnalysisBudget(nodes=100000, multipv=3)))
    settings = world.engine.calls[0][1]
    assert settings.limit == EngineLimit(depth=None, nodes=100000, time_ms=None)
    assert (settings.multipv, settings.threads, settings.hash_mb) == (3, 1, 16)


@pytest.mark.parametrize(
    "budget",
    [
        AnalysisBudget(depth=0),
        AnalysisBudget(nodes=0),
        AnalysisBudget(time_ms=0),
        AnalysisBudget(multipv=0),
        AnalysisBudget(depth=-1),
        AnalysisBudget(nodes=-5),
        AnalysisBudget(time_ms=-1),
        AnalysisBudget(multipv=-2),
        AnalysisBudget(depth=10, multipv=0),
    ],
)
def test_invalid_budget_rejected_before_any_work(budget):
    world = build()
    with pytest.raises(InvalidAnalysisBudgetError):
        world.service.execute(request(budget))
    assert world.log == []


@pytest.mark.parametrize(
    "attr, error",
    [("fen_error", InvalidFenError("x")), ("move_error", IllegalMoveError("x"))],
)
def test_invalid_chess_input_short_circuits_before_the_session(attr, error):
    world = build()
    setattr(world.chess, attr, error)
    with pytest.raises(type(error)):
        world.service.execute(request())
    assert ("acquire",) not in world.log and world.engine.calls == []


@pytest.mark.parametrize("mode", [OutputMode.STRUCTURED, OutputMode.COMMENTARY])
def test_heuristic_claims_fail_closed_before_any_work(mode):
    world = build()
    with pytest.raises(FeatureUnavailableError):
        world.service.execute(request(mode=mode, heuristic=True))
    assert world.log == []


@pytest.mark.parametrize("mode", ["verbose", "structured", "commentary", None, 1])
def test_non_enum_output_modes_rejected_before_any_work(mode):
    world = build()
    with pytest.raises(UnsupportedOutputModeError):
        world.service.execute(request(mode=mode))  # type: ignore[arg-type]
    assert world.log == []  # no FEN/move, session, engine, explanation or render work
    assert world.chess.log == [] and world.engine.calls == [] and not world.sessions.active


@pytest.mark.parametrize("mode", list(OutputMode))
def test_exact_enum_output_modes_are_accepted(mode):
    world = build()
    result = world.service.execute(request(mode=mode))
    assert ("explain", world.judge.quality) in world.log
    if mode is OutputMode.COMMENTARY:
        assert world.log[-2:] == [("release",), ("render",)]
        assert result.commentary.used_claim_ids == result.selected_claim_ids == ("cl_002", "cl_001")
    else:
        assert ("render",) not in world.log and result.commentary is None


# ---- error propagation; the session is always released -----------------------------------------


def _assert_released(world):
    assert world.log.count(("acquire",)) == world.log.count(("release",)) == 1
    assert world.log[-1] == ("release",) and not world.sessions.active


def test_played_analysis_failure_propagates_and_releases():
    world = build()
    world.engine.fail_on_call = 2
    with pytest.raises(EngineAnalysisError):
        world.service.execute(request())
    assert len(world.engine.calls) == 2 and ("judge",) not in world.log
    _assert_released(world)


def test_judge_error_propagates_unwrapped_and_releases():
    world = build()
    world.judge.error = IncompatibleAnalysisError("nope")
    with pytest.raises(IncompatibleAnalysisError):
        world.service.execute(request())
    _assert_released(world)


@pytest.mark.parametrize(
    "error",
    [ExplanationGraphError("bad graph"), IncompatibleBadMoveContextError("routed but rejected")],
)
def test_explanation_failure_is_never_silence(error):
    world = build(error=error)
    with pytest.raises(type(error)):
        world.service.execute(request())
    _assert_released(world)


def test_renderer_failure_is_an_analysis_failure_after_release():
    world = build()
    world.renderer.error = ExplanationRenderError("broken invariant")
    with pytest.raises(ExplanationRenderError):
        world.service.execute(request(mode=OutputMode.COMMENTARY))
    assert world.log[-2:] == [("release",), ("render",)]


def test_outcome_claims_must_be_the_graph_claims():
    world = build()
    outcome = world.explanations.outcome
    world.explanations.outcome = replace(outcome, claims=tuple(c for c in outcome.claims))
    with pytest.raises(ClaimProjectionError):
        world.service.execute(request())


def test_outcome_from_another_position_fails_closed():
    world = build()
    graph = GraphBuilder().build(EvidenceBundle("pos_elsewhere", (), ()), ())
    world.explanations.outcome = MoveExplanationOutcome(
        (), graph, ExplanationSelector().select(graph)
    )
    with pytest.raises(ClaimProjectionError):
        world.service.execute(request())


# ---- projection, provenance and modes -----------------------------------------------------------


def test_structured_result_projects_all_claims_and_the_selection():
    world = build()
    result = world.service.execute(request())
    outcome = world.explanations.outcome
    assert result.claims == project_claims(outcome.claims)
    assert [c.claim_id for c in result.claims] == ["cl_001", "cl_002"]
    assert result.selected_claim_ids == outcome.selection.selected_claim_ids == ("cl_002", "cl_001")
    assert result.variations == () and result.commentary is None
    assert ("render",) not in world.log


def test_commentary_is_the_exact_p12_projection_rendered_after_release():
    world = build()
    result = world.service.execute(request(mode=OutputMode.COMMENTARY))
    assert world.log[-2:] == [("release",), ("render",)]
    assert result.commentary == CommentaryView(
        text=(
            "Move c3e4 allows an engine-verified line with material loss. "
            "Move c3e4 leaves white knight from c3 hanging."
        ),
        sentences=(
            "Move c3e4 allows an engine-verified line with material loss.",
            "Move c3e4 leaves white knight from c3 hanging.",
        ),
        used_claim_ids=("cl_002", "cl_001"),
    )
    assert result.commentary.used_claim_ids == result.selected_claim_ids


@pytest.mark.parametrize("make", [build, lambda: build(outcome=empty_outcome(), p7_calls=0)])
def test_output_mode_changes_presentation_only(make):
    structured_world, commentary_world = make(), make()
    structured = structured_world.service.execute(request())
    commentary = commentary_world.service.execute(request(mode=OutputMode.COMMENTARY))
    # Identical engine/session/explanation work; COMMENTARY adds only a final render.
    assert commentary_world.log == [*structured_world.log, ("render",)]
    assert commentary_world.engine.calls == structured_world.engine.calls
    for f in fields(structured):
        if f.name != "commentary":
            assert getattr(structured, f.name) == getattr(commentary, f.name), f.name
    assert structured.commentary is None
    assert type(commentary.commentary) is CommentaryView


@pytest.mark.parametrize("mode", list(OutputMode))
def test_empty_strict_result_keeps_judgement_and_meta_commentary(mode):
    world = build(outcome=empty_outcome(), p7_calls=0)
    result = world.service.execute(request(mode=mode))
    assert result.claims == () and result.selected_claim_ids == ()
    assert result.judgement.quality == "blunder"
    if mode is OutputMode.STRUCTURED:
        assert result.commentary is None
    else:
        assert result.commentary == CommentaryView("No verified explanation is available.", (), ())


def test_metadata_is_the_frozen_noise_free_shape():
    result = build().service.execute(request())
    assert result.metadata == {
        "position_id": position().position_id,
        "engine": {"name": "Stockfish", "version": "17"},
        "analysis": {
            "depth": 12,
            "nodes": None,
            "time_ms": None,
            "multipv": 5,
            "threads": 1,
            "hash_mb": 16,
        },
        "forcedness": {"acceptable_move_count": 3, "best_to_second_gap_cp": 20},
        "explanation": {
            "mode": "strict",
            "counterfactual": {
                "depth": 12,
                "time_ms": 2000,
                "multipv": 1,
                "threads": 1,
                "hash_mb": 16,
            },
        },
    }
    json.dumps(result.metadata)


def test_dto_judgement_projection():
    result = build().service.execute(request())
    j = result.judgement
    assert result.position_fen == position().fen
    assert (j.move_uci, j.best_move_uci, j.quality) == ("c3e4", "c3b5", "blunder")
    assert (j.rank, j.cp_loss, j.expected_score_loss, j.forcedness) == (None, 310, 0.3, "flexible")
