import ast
import inspect
import textwrap
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis import (
    BasePieceRef,
    GoodMoveMode,
    RepresentativeAlternative,
    TacticalCandidateStatus,
)
from calliope.domain.chess import ChessMove, Color, PieceRef, PieceType
from calliope.domain.engine import (
    EngineAnalysis,
    EngineIdentity,
    EngineLimit,
    EngineLine,
    EngineScore,
    EngineSettings,
    Forcedness,
    MoveJudgement,
    MoveQuality,
)
from calliope.errors import (
    IllegalMoveError,
    IncompatibleBadMoveContextError,
    IncompatibleBoardDeltaError,
    IncompatibleGoodMoveContextError,
    IncompatiblePositionObservationError,
    IncompatibleTacticalContextError,
    InvalidUciError,
    NullMoveNotAllowedError,
)
from calliope.services.explanation import BasePieceIdentityMap, GoodMoveExplainer
from calliope.services.explanation.good_move import GoodMovePreparedContext
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.tactics import TacticalDetector

rules = PythonChessAdapter()
KNIGHT = "4k3/8/8/3p4/8/2N5/8/4K3 w - - 0 1"
MOVES = ("c3e4", "c3b5", "c3a4")


def scenario(fen=KNIGHT, moves=MOVES):
    base = rules.position_from_fen(fen)
    facts = PositionFactExtractor(rules)
    explainer = GoodMoveExplainer(
        rules, facts, BoardDeltaAnalyzer(rules, facts), rules, TacticalDetector()
    )
    lines = tuple(
        EngineLine(rank, ChessMove(uci), EngineScore.cp(0), (ChessMove(uci),))
        for rank, uci in enumerate(moves, start=1)
    )
    analysis = EngineAnalysis(
        base.position_id,
        EngineIdentity("Fixture basis"),
        EngineSettings(EngineLimit(depth=4)),
        lines,
    )
    judgement = MoveJudgement(
        position_id=base.position_id,
        mover=base.side_to_move,
        move=ChessMove(moves[0]),
        best_move=ChessMove(moves[0]),
        quality=MoveQuality.GOOD,
        rank=1,
        best_score=EngineScore.cp(0),
        played_score=EngineScore.cp(0),
        cp_loss=0,
        expected_score_loss=0.0,
    )
    prepared = explainer.prepare(base, judgement.move, judgement, analysis)
    assert isinstance(prepared, GoodMovePreparedContext)
    return explainer, prepared


class WrappedMethod:
    """Observe one real dependency method, optionally corrupting only its returned value."""

    def __init__(self, delegate, name, transform=lambda value: value):
        self.delegate, self.name, self.transform = delegate, name, transform
        self.calls = []

    def __getattr__(self, name):
        method = getattr(self.delegate, name)
        if name != self.name:
            return method

        def call(*args, **kwargs):
            self.calls.append((args, kwargs))
            return self.transform(method(*args, **kwargs))

        return call


def all_branches(context):
    return (context.played, *(alternative.branch for alternative in context.alternatives))


def test_common_base_evidence_built_once_and_shared_by_every_branch(monkeypatch):
    explainer, prepared = scenario()
    for dependency, method in (
        ("facts", "extract"),
        ("delta", "analyze"),
        ("tactical_rules", "observe_tactics"),
        ("detector", "detect"),
        ("chess", "apply_move"),
    ):
        setattr(explainer, dependency, WrappedMethod(getattr(explainer, dependency), method))
    original_from = BasePieceIdentityMap.from_facts
    original_advance = BasePieceIdentityMap.advance
    roots, advances = [], []

    def from_facts(cls, facts):
        root = original_from(facts)
        roots.append(root)
        return root

    def advance(self, delta):
        advances.append(self)
        return original_advance(self, delta)

    monkeypatch.setattr(BasePieceIdentityMap, "from_facts", classmethod(from_facts))
    monkeypatch.setattr(BasePieceIdentityMap, "advance", advance)
    context = explainer.build_branches(prepared)
    assert roots == [context.root_identity]
    assert len(advances) == 3 and all(root is context.root_identity for root in advances)
    for dependency in (explainer.facts, explainer.tactical_rules):
        assert len(dependency.calls) == 4
        assert sum(args[0] is prepared.base for args, _ in dependency.calls) == 1
    assert len(explainer.chess.calls) == len(explainer.delta.calls) == 3
    assert all(args[0] is prepared.base for args, _ in explainer.chess.calls)
    assert all(args[0] is prepared.base for args, _ in explainer.delta.calls)
    for _, kwargs in explainer.detector.calls:
        assert kwargs["before"] is context.base_facts
        assert kwargs["before_rules"] is context.base_rules


def test_real_branch_bindings_and_p6_candidates_remain_detected():
    explainer, prepared = scenario()
    context = explainer.build_branches(prepared)
    assert context.prepared is prepared
    assert (
        context.base_facts.position_id
        == context.base_rules.position_id
        == prepared.base.position_id
    )
    candidates = []
    for branch in all_branches(context):
        assert branch.position == rules.apply_move(prepared.base, branch.move)
        assert branch.position.side_to_move is prepared.base.side_to_move.opposite
        assert branch.delta.before_position_id == prepared.base.position_id
        assert (
            branch.delta.after_position_id
            == branch.facts.position_id
            == branch.rules.position_id
            == branch.position.position_id
        )
        assert branch.delta.move.uci == branch.detection.move.uci == branch.move.uci
        assert branch.delta.mover is branch.detection.mover is prepared.base.side_to_move
        assert branch.rules.side_to_move is branch.position.side_to_move
        assert branch.detection.before_position_id == prepared.base.position_id
        assert branch.detection.after_position_id == branch.position.position_id
        assert branch.identity.base_position_id == prepared.base.position_id
        assert branch.identity.position_id == branch.position.position_id
        candidates.extend(branch.detection.candidates)
    assert candidates
    assert all(candidate.status is TacticalCandidateStatus.DETECTED for candidate in candidates)
    assert context.played.move is prepared.played_move
    assert tuple(a.alternative for a in context.alternatives) == prepared.alternatives
    assert all(a.branch.move is a.alternative.move for a in context.alternatives)


@pytest.mark.parametrize("moves", [MOVES[:1], MOVES[:2], MOVES, MOVES + ("e1d2",)])
def test_only_prepared_zero_one_or_two_alternatives_are_built(moves):
    explainer, prepared = scenario(moves=moves)
    context = explainer.build_branches(prepared)
    assert len(context.alternatives) == min(2, len(moves) - 1)
    assert tuple(a.alternative for a in context.alternatives) == prepared.alternatives
    assert context.played.position == rules.apply_move(prepared.base, prepared.played_move)


def test_prepared_alternative_rank_gaps_are_retained_without_reselection():
    explainer, prepared = scenario()
    # I2 consumes selection metadata, rather than validating the original engine basis again.
    alternatives = tuple(replace(a, rank=a.rank + 5) for a in prepared.alternatives)
    context = explainer.build_branches(replace(prepared, alternatives=alternatives))
    assert tuple(a.alternative for a in context.alternatives) == alternatives


def test_same_physical_knight_has_independent_branch_locations():
    explainer, prepared = scenario()
    context = explainer.build_branches(prepared)
    subject = BasePieceRef(Color.WHITE, PieceType.KNIGHT, "c3")
    assert context.root_identity.current_piece(subject) == PieceRef(
        Color.WHITE, PieceType.KNIGHT, "c3"
    )
    for branch, square in zip(all_branches(context), ("e4", "b5", "a4"), strict=True):
        current = PieceRef(Color.WHITE, PieceType.KNIGHT, square)
        assert branch.identity.current_piece(subject) == current
        assert branch.identity.base_ref_for(current) == subject


def test_capture_removes_base_piece_on_only_one_branch():
    explainer, prepared = scenario(moves=("c3d5", "c3b5", "c3a4"))
    context = explainer.build_branches(prepared)
    pawn = BasePieceRef(Color.BLACK, PieceType.PAWN, "d5")
    assert context.played.delta.capture.captured_square == "d5"
    assert context.played.identity.current_piece(pawn) is None
    assert context.root_identity.current_piece(pawn) == PieceRef(Color.BLACK, PieceType.PAWN, "d5")
    assert all(
        a.branch.identity.current_piece(pawn) == context.root_identity.current_piece(pawn)
        for a in context.alternatives
    )


def test_promotion_keeps_base_pawn_identity_and_branch_specific_role():
    explainer, prepared = scenario("4k3/P7/8/8/8/8/8/4K3 w - - 0 1", ("a7a8q", "a7a8n", "e1d2"))
    context = explainer.build_branches(prepared)
    pawn = BasePieceRef(Color.WHITE, PieceType.PAWN, "a7")
    for branch, role in zip(
        all_branches(context)[:2], (PieceType.QUEEN, PieceType.KNIGHT), strict=True
    ):
        current = PieceRef(Color.WHITE, role, "a8")
        assert branch.identity.current_piece(pawn) == current
        assert branch.identity.base_ref_for(current) == pawn
    assert context.alternatives[1].branch.identity.current_piece(pawn) == PieceRef(
        Color.WHITE, PieceType.PAWN, "a7"
    )


def test_canonical_castling_composes_both_king_and_rook_identities():
    explainer, prepared = scenario("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", ("e1h1", "a1a2"))
    context = explainer.build_branches(prepared)
    assert context.played.move is prepared.played_move
    assert context.played.move.uci == "e1g1"
    for role, origin, destination in ((PieceType.KING, "e1", "g1"), (PieceType.ROOK, "h1", "f1")):
        subject = BasePieceRef(Color.WHITE, role, origin)
        assert context.played.identity.current_piece(subject) == PieceRef(
            Color.WHITE, role, destination
        )
        assert context.alternatives[0].branch.identity.current_piece(subject) == PieceRef(
            Color.WHITE, role, origin
        )


def test_en_passant_uses_captured_square_and_preserves_sibling_state():
    explainer, prepared = scenario("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2", ("e5d6", "e5e6"))
    context = explainer.build_branches(prepared)
    capture = context.played.delta.capture
    assert capture.is_en_passant
    assert (capture.captured_square, capture.landing_square) == ("d5", "d6")
    victim = BasePieceRef(Color.BLACK, PieceType.PAWN, "d5")
    capturer = BasePieceRef(Color.WHITE, PieceType.PAWN, "e5")
    assert context.played.identity.current_piece(victim) is None
    assert context.played.identity.current_piece(capturer) == PieceRef(
        Color.WHITE, PieceType.PAWN, "d6"
    )
    assert context.alternatives[0].branch.identity.current_piece(victim) == PieceRef(
        Color.BLACK, PieceType.PAWN, "d5"
    )


def test_modes_do_not_change_deterministic_board_truth():
    explainer, prepared = scenario()
    strong = explainer.build_branches(prepared)
    only = explainer.build_branches(replace(prepared, mode=GoodMoveMode.ONLY_MOVE_CANDIDATE))
    assert strong.base_facts == only.base_facts
    assert strong.base_rules == only.base_rules
    assert strong.root_identity == only.root_identity
    assert strong.played == only.played and strong.alternatives == only.alternatives


@pytest.mark.parametrize(
    ("dependency", "method", "when", "changes", "message"),
    [
        ("facts", "extract", "base", {"position_id": "wrong"}, "base facts"),
        (
            "tactical_rules",
            "observe_tactics",
            "base",
            {"position_id": "wrong"},
            "base tactical observation",
        ),
        ("tactical_rules", "observe_tactics", "base", {"side_to_move": Color.BLACK}, "wrong side"),
        ("chess", "apply_move", "branch", {"side_to_move": Color.WHITE}, "branch position"),
        ("delta", "analyze", "branch", {"before_position_id": "wrong"}, "start from the base"),
        ("delta", "analyze", "branch", {"after_position_id": "wrong"}, "end at the branch"),
        ("delta", "analyze", "branch", {"move": ChessMove("e1d2")}, "another move"),
        ("delta", "analyze", "branch", {"mover": Color.BLACK}, "wrong mover"),
        ("facts", "extract", "branch", {"position_id": "wrong"}, "branch facts"),
        (
            "tactical_rules",
            "observe_tactics",
            "branch",
            {"position_id": "wrong"},
            "branch tactical observation",
        ),
        (
            "tactical_rules",
            "observe_tactics",
            "branch",
            {"side_to_move": Color.WHITE},
            "wrong side",
        ),
        ("detector", "detect", "branch", {"before_position_id": "wrong"}, "start from the base"),
        ("detector", "detect", "branch", {"after_position_id": "wrong"}, "end at the branch"),
        ("detector", "detect", "branch", {"move": ChessMove("e1d2")}, "another move"),
        ("detector", "detect", "branch", {"mover": Color.BLACK}, "wrong mover"),
    ],
)
def test_p9_detected_bindings_fail_closed(dependency, method, when, changes, message):
    explainer, prepared = scenario()

    def transform(value):
        is_base = getattr(value, "position_id", None) == prepared.base.position_id
        if (when == "base") == is_base:
            return replace(value, **changes)
        return value

    setattr(explainer, dependency, WrappedMethod(getattr(explainer, dependency), method, transform))
    with pytest.raises(IncompatibleGoodMoveContextError, match=message):
        explainer.build_branches(prepared)


@pytest.mark.parametrize("operation", ["from_facts", "advance"])
def test_real_identity_inconsistencies_translate_to_p9_with_original_cause(operation):
    explainer, prepared = scenario()
    if operation == "from_facts":
        explainer.facts = WrappedMethod(
            explainer.facts,
            "extract",
            lambda value: replace(value, pieces=value.pieces + value.pieces[:1]),
        )
    else:
        explainer.delta = WrappedMethod(
            explainer.delta,
            "analyze",
            lambda value: replace(value, piece_correspondence=value.piece_correspondence[1:]),
        )
    with pytest.raises(
        IncompatibleGoodMoveContextError, match="identity is inconsistent"
    ) as raised:
        explainer.build_branches(prepared)
    assert isinstance(raised.value.__cause__, IncompatibleBadMoveContextError)


@pytest.mark.parametrize("operation", ["from_facts", "advance"])
@pytest.mark.parametrize("attribute", ["position_id", "base_position_id"])
def test_identity_binding_mismatches_detected_by_p9(monkeypatch, operation, attribute):
    explainer, prepared = scenario()
    original = getattr(BasePieceIdentityMap, operation)
    if operation == "from_facts":

        def corrupt(cls, facts):
            return replace(original(facts), **{attribute: "wrong"})

        monkeypatch.setattr(BasePieceIdentityMap, operation, classmethod(corrupt))
    else:

        def corrupt(self, delta):
            return replace(original(self, delta), **{attribute: "wrong"})

        monkeypatch.setattr(BasePieceIdentityMap, operation, corrupt)
    with pytest.raises(IncompatibleGoodMoveContextError, match="identity"):
        explainer.build_branches(prepared)


@pytest.mark.parametrize(
    ("dependency", "method", "error_type"),
    [
        ("facts", "extract", IncompatiblePositionObservationError),
        ("delta", "analyze", IncompatibleBoardDeltaError),
        ("detector", "detect", IncompatibleTacticalContextError),
        ("facts", "extract", IncompatibleBadMoveContextError),
    ],
)
def test_owning_layer_errors_are_not_broadly_translated(dependency, method, error_type):
    explainer, prepared = scenario()
    error = error_type("owning-layer failure")

    def fail(value):
        raise error

    setattr(explainer, dependency, WrappedMethod(getattr(explainer, dependency), method, fail))
    with pytest.raises(error_type) as raised:
        explainer.build_branches(prepared)
    assert raised.value is error


@pytest.mark.parametrize("uci", ["c3c4", "invalid", "0000"])
@pytest.mark.parametrize("branch", ["played", "alternative"])
def test_tampered_branch_moves_cannot_be_silently_dropped(uci, branch):
    explainer, prepared = scenario()
    if branch == "played":
        prepared = replace(prepared, played_move=ChessMove(uci))
    else:
        prepared = replace(prepared, alternatives=(RepresentativeAlternative(2, ChessMove(uci)),))
    with pytest.raises(IncompatibleGoodMoveContextError):
        explainer.build_branches(prepared)


@pytest.mark.parametrize("error_type", [IllegalMoveError, InvalidUciError, NullMoveNotAllowedError])
def test_apply_move_binding_failure_is_translated(error_type):
    explainer, prepared = scenario()
    error = error_type("application failure")

    def fail(value):
        raise error

    explainer.chess = WrappedMethod(explainer.chess, "apply_move", fail)
    with pytest.raises(IncompatibleGoodMoveContextError) as raised:
        explainer.build_branches(prepared)
    assert raised.value.__cause__ is error


def test_branch_builder_does_not_read_engine_basis_or_numeric_metadata(monkeypatch):
    explainer, prepared = scenario()

    def forbidden(self):
        raise AssertionError("I2 accessed ranking or numerical metadata")

    with monkeypatch.context() as patch:
        for cls, names in (
            (GoodMovePreparedContext, ("position_analysis", "judgement")),
            (EngineAnalysis, ("lines",)),
            (EngineLine, ("score", "wdl")),
            (MoveJudgement, ("best_score", "played_score", "cp_loss", "expected_score_loss")),
            (Forcedness, ("acceptable_move_count", "best_to_second_gap_cp")),
        ):
            for name in names:
                patch.setattr(cls, name, property(forbidden))
        context = explainer.build_branches(prepared)
        assert len(context.alternatives) == 2


def test_i2_source_guard_has_no_p7_benefit_rules_or_candidate_status_changes():
    source = "\n".join(
        textwrap.dedent(inspect.getsource(method))
        for method in (GoodMoveExplainer.build_branches, GoodMoveExplainer._first_move_branch)
    )
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not names & {
        "CounterfactualAnalyzer",
        "CounterfactualProbe",
        "CounterfactualBatchRequest",
        "EngineAnalysisPort",
        "StockfishAdapter",
        "GoodMoveBenefitResult",
        "GoodMoveExplanationResult",
        "GoodMoveBenefitKind",
        "TacticalCandidate",
        "TacticalCandidateStatus",
    }
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not attributes & {
        "best_score",
        "played_score",
        "cp_loss",
        "expected_score_loss",
        "acceptable_move_count",
        "best_to_second_gap_cp",
        "score",
        "wdl",
        "position_analysis",
        "lines",
        "execute",
        "VERIFIED",
        "REFUTED",
    }
    assert tuple(field.name for field in fields(GoodMoveExplainer)) == (
        "chess",
        "facts",
        "delta",
        "tactical_rules",
        "detector",
    )


def test_context_and_branches_are_frozen_and_slotted():
    explainer, prepared = scenario()
    context = explainer.build_branches(prepared)
    for value in (context, context.played, context.alternatives[0]):
        assert not hasattr(value, "__dict__")
        field = fields(value)[0].name
        with pytest.raises(FrozenInstanceError):
            setattr(value, field, getattr(value, field))


def test_black_mover_branch_identity_and_bindings():
    explainer, prepared = scenario("4k3/8/2n5/8/3P4/8/8/4K3 b - - 0 1", ("c6e5", "c6b4", "c6a5"))
    context = explainer.build_branches(prepared)
    knight = BasePieceRef(Color.BLACK, PieceType.KNIGHT, "c6")
    for branch, square in zip(all_branches(context), ("e5", "b4", "a5"), strict=True):
        assert branch.delta.mover is branch.detection.mover is Color.BLACK
        assert branch.position.side_to_move is branch.rules.side_to_move is Color.WHITE
        assert branch.identity.current_piece(knight) == PieceRef(
            Color.BLACK, PieceType.KNIGHT, square
        )
