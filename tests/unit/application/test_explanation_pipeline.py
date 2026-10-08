"""G0 MoveExplanationPipeline: frozen routing, P9 mode ownership, P10/P11 closure, no silence.

Explainers are replaced by fakes that return real P8/P9 results from the reviewed unit scenario
corpus, so the P10/P11 closure runs on genuine packages.
"""

from dataclasses import dataclass, field
from pathlib import Path

import _g0_fakes
import _p8_claim_scenarios as p8
import _p9_preservation_claim_scenarios as pres
import _p9_strong_claim_scenarios as strong
import pytest

from calliope.application import explanation as pipeline_module
from calliope.application.explanation import (
    BAD_MOVE_QUALITIES,
    COUNTERFACTUAL_SETTINGS,
    GOOD_MOVE_QUALITIES,
    UNEXPLAINED_QUALITIES,
    MoveExplanationPipeline,
)
from calliope.domain.analysis import (
    BadMoveExplanationResult,
    BadMoveExplanationStatus,
    GoodMoveMode,
)
from calliope.domain.chess import ChessMove
from calliope.domain.engine import (
    EngineLimit,
    EngineScore,
    EngineSettings,
    Forcedness,
    ForcednessLevel,
    MoveJudgement,
    MoveQuality,
)
from calliope.domain.explanation import ClaimConfidence
from calliope.errors import (
    ExplanationClaimError,
    IncompatibleBadMoveContextError,
    IncompatibleGoodMoveContextError,
)
from calliope.services.explanation import bad_move, good_move
from calliope.services.explanation.claim_builder import ClaimBuilder
from calliope.services.explanation.good_move import GoodMoveNotApplicable

rules = _g0_fakes.rules
PLAYED = ChessMove("c3e4")


def judgement(base, quality):
    return MoveJudgement(
        position_id=base.position_id,
        mover=base.side_to_move,
        move=PLAYED,
        best_move=ChessMove("c3b5"),
        quality=quality,
        rank=None,
        best_score=EngineScore.cp(0),
        played_score=EngineScore.cp(0),
        cp_loss=0,
        expected_score_loss=0.0,
        forcedness=Forcedness(ForcednessLevel.FLEXIBLE, 2, 10),
    )


@dataclass
class FakeBad:
    result: object = None
    calls: list = field(default_factory=list)

    def explain(self, base, played, judged, settings):
        self.calls.append(("explain", settings))
        return self.result if self.result is not None else p8.knight()


@dataclass
class Prepared:
    mode: GoodMoveMode


@dataclass
class FakeGood:
    prepared: object = None
    calls: list = field(default_factory=list)

    def prepare(self, base, played, judged, position_analysis):
        self.calls.append(("prepare", position_analysis))
        return self.prepared

    def build_branches(self, prepared):
        self.calls.append(("build_branches",))
        return "deterministic"

    def verify_counterfactuals(self, deterministic, settings):
        self.calls.append(("verify_counterfactuals", settings))
        return "context"

    def explain_strong_move(self, context):
        self.calls.append(("explain_strong_move",))
        return strong.forces()

    def explain_only_move(self, context):
        self.calls.append(("explain_only_move",))
        return pres.mate_all()


def make(bad=None, good=None):
    bad, good = bad or FakeBad(), good or FakeGood(Prepared(GoodMoveMode.STRONG_MOVE))
    return MoveExplanationPipeline(bad_moves=bad, good_moves=good), bad, good  # type: ignore[arg-type]


# ---- routing closure ----------------------------------------------------------------------------


def test_routing_sets_are_exactly_the_frozen_eligibility_sets():
    assert BAD_MOVE_QUALITIES == bad_move.ELIGIBLE_QUALITIES
    assert GOOD_MOVE_QUALITIES == good_move.ELIGIBLE_QUALITIES
    assert not BAD_MOVE_QUALITIES & GOOD_MOVE_QUALITIES
    assert set(MoveQuality) - BAD_MOVE_QUALITIES - GOOD_MOVE_QUALITIES == {MoveQuality.INACCURACY}
    assert UNEXPLAINED_QUALITIES == {MoveQuality.INACCURACY}


def test_p7_profile_is_the_frozen_reproducibility_profile():
    assert COUNTERFACTUAL_SETTINGS == EngineSettings(
        limit=EngineLimit(depth=12, time_ms=2000), multipv=1, threads=1, hash_mb=16
    )


@pytest.mark.parametrize("quality", sorted(BAD_MOVE_QUALITIES))
def test_bad_moves_route_to_p8_only(quality):
    pipeline, bad, good = make()
    base = rules.position_from_fen(p8.KNIGHT)
    outcome = pipeline.explain(base, PLAYED, judgement(base, quality), None)
    assert bad.calls == [("explain", COUNTERFACTUAL_SETTINGS)] and good.calls == []
    assert [c.predicate.value for c in outcome.claims] == [
        "leaves_piece_hanging",
        "allows_material_loss",
    ]
    assert outcome.selection.selected_claim_ids == ("cl_002", "cl_001")
    assert outcome.graph.claims is outcome.claims and outcome.graph.relations == ()


@pytest.mark.parametrize(
    "mode,expected,predicate",
    [
        (GoodMoveMode.STRONG_MOVE, "explain_strong_move", "forces_response"),
        (
            GoodMoveMode.ONLY_MOVE_CANDIDATE,
            "explain_only_move",
            "avoids_representative_mate_failure",
        ),
    ],
)
@pytest.mark.parametrize("quality", sorted(GOOD_MOVE_QUALITIES))
def test_good_moves_use_p9s_own_mode(quality, mode, expected, predicate):
    pipeline, bad, good = make(good=FakeGood(Prepared(mode)))
    base = rules.position_from_fen(strong.ROOK_CHECK)
    analysis = object()
    outcome = pipeline.explain(base, PLAYED, judgement(base, quality), analysis)
    assert bad.calls == []
    assert good.calls == [
        ("prepare", analysis),
        ("build_branches",),
        ("verify_counterfactuals", COUNTERFACTUAL_SETTINGS),
        (expected,),
    ]
    assert outcome.claims[0].predicate.value == predicate


def test_inaccuracy_is_the_canonical_empty_package_through_p11(monkeypatch):
    pipeline, bad, good = make()
    built = []
    original = pipeline.graphs.build
    monkeypatch.setattr(
        pipeline.graphs, "build", lambda b, c: built.append((b, c)) or original(b, c)
    )
    base = rules.position_from_fen(p8.KNIGHT)
    outcome = pipeline.explain(base, PLAYED, judgement(base, MoveQuality.INACCURACY), None)
    assert bad.calls == [] and good.calls == []
    ((bundle, claims),) = built
    assert (bundle.base_position_id, bundle.evidence, bundle.groups, claims) == (
        base.position_id,
        (),
        (),
        (),
    )
    assert outcome.claims == () and outcome.selection.selected_claim_ids == ()


# ---- NOT_APPLICABLE after routing is an internal error, never silence -----------------------------


def test_p8_not_applicable_after_routing_raises():
    base = rules.position_from_fen(p8.KNIGHT)
    rejected = BadMoveExplanationResult(
        status=BadMoveExplanationStatus.NOT_APPLICABLE,
        base_position_id=base.position_id,
        played_move=PLAYED,
        comparator_move=ChessMove("c3b5"),
    )
    pipeline, _, _ = make(bad=FakeBad(rejected))
    with pytest.raises(IncompatibleBadMoveContextError, match="rejected"):
        pipeline.explain(base, PLAYED, judgement(base, MoveQuality.BLUNDER), None)


def test_p9_not_applicable_after_routing_raises():
    base = rules.position_from_fen(strong.ROOK_CHECK)
    good = FakeGood(GoodMoveNotApplicable(base.position_id, PLAYED))
    pipeline, _, _ = make(good=good)
    with pytest.raises(IncompatibleGoodMoveContextError, match="rejected"):
        pipeline.explain(base, PLAYED, judgement(base, MoveQuality.GOOD), object())
    assert good.calls == [("prepare", good.calls[0][1])]


def test_unknown_p9_mode_raises():
    base = rules.position_from_fen(strong.ROOK_CHECK)
    pipeline, _, _ = make(good=FakeGood(Prepared("guessed")))  # type: ignore[arg-type]
    with pytest.raises(IncompatibleGoodMoveContextError, match="mode"):
        pipeline.explain(base, PLAYED, judgement(base, MoveQuality.BEST), object())


# ---- P10/P11 closure always runs ----------------------------------------------------------------


def test_p10_validation_failure_propagates(monkeypatch):
    original = ClaimBuilder.build_bad_move

    def forced(self, bundle):
        claims = original(self, bundle)
        object.__setattr__(claims[0], "confidence", ClaimConfidence.FORCED)
        return claims

    monkeypatch.setattr(ClaimBuilder, "build_bad_move", forced)
    pipeline, _, _ = make()
    base = rules.position_from_fen(p8.KNIGHT)
    with pytest.raises(ExplanationClaimError):
        pipeline.explain(base, PLAYED, judgement(base, MoveQuality.BLUNDER), None)


@pytest.mark.parametrize(
    "stage",
    ["claim_validator.validate_bad_move", "graphs.build", "selector.select", "selections.validate"],
)
def test_every_closure_stage_runs(stage, monkeypatch):
    pipeline, _, _ = make()
    owner_name, method = stage.split(".")
    owner = getattr(pipeline, owner_name)
    calls = []
    original = getattr(owner, method)
    monkeypatch.setattr(owner, method, lambda *a: calls.append(a) or original(*a))
    base = rules.position_from_fen(p8.KNIGHT)
    pipeline.explain(base, PLAYED, judgement(base, MoveQuality.MISTAKE), None)
    assert len(calls) == 1


def test_pipeline_owns_no_engine():
    text = Path(pipeline_module.__file__).read_text(encoding="utf-8")
    for forbidden in ("StockfishAdapter", "popen_uci", "SimpleEngine", "chess.engine"):
        assert forbidden not in text
