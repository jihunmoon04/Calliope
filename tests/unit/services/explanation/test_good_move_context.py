import ast
import inspect
from dataclasses import FrozenInstanceError, fields, replace

import pytest

import calliope
from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis import AlternativeScope, GoodMoveMode
from calliope.domain.chess import ChessMove, Color
from calliope.domain.engine import (
    WDL,
    EngineAnalysis,
    EngineIdentity,
    EngineLimit,
    EngineLine,
    EngineScore,
    EngineSettings,
    Forcedness,
    ForcednessLevel,
    MoveJudgement,
    MoveQuality,
)
from calliope.errors import (
    IllegalMoveError,
    IncompatibleGoodMoveContextError,
    InvalidUciError,
    NullMoveNotAllowedError,
)
from calliope.services.explanation import GoodMoveExplainer
from calliope.services.explanation import good_move as module
from calliope.services.explanation.good_move import GoodMoveNotApplicable, GoodMovePreparedContext

rules = PythonChessAdapter()
BASE = rules.position_from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
CASTLING = rules.position_from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
MOVES = ("e2e4", "d2d4", "g1f3", "c2c4")


def basis(ucis=MOVES, *, ranks=None, base=BASE):
    if ranks is None:
        ranks = range(1, len(ucis) + 1)
    lines = tuple(
        EngineLine(rank, ChessMove(uci), EngineScore.cp(100 - rank), (ChessMove(uci),))
        for rank, uci in zip(ranks, ucis, strict=True)
    )
    return EngineAnalysis(
        position_id=base.position_id,
        engine=EngineIdentity("Fixture ranking basis"),
        settings=EngineSettings(limit=EngineLimit(depth=12), multipv=len(lines), threads=4),
        lines=lines,
    )


def judgement(**changes):
    values = {
        "position_id": BASE.position_id,
        "mover": BASE.side_to_move,
        "move": ChessMove("e2e4"),
        "best_move": ChessMove("e2e4"),
        "quality": MoveQuality.BEST,
        "rank": 1,
        "best_score": EngineScore.cp(100),
        "played_score": EngineScore.cp(100),
        "cp_loss": 0,
        "expected_score_loss": 0.0,
    }
    values.update(changes)
    return MoveJudgement(**values)


def prepare(j=None, analysis=None, *, played=None, base=BASE, chess=rules):
    j = j if j is not None else judgement()
    analysis = analysis if analysis is not None else basis()
    return GoodMoveExplainer(chess).prepare(
        base, played if played is not None else j.move, j, analysis
    )


def selected(context):
    assert isinstance(context, GoodMovePreparedContext)
    return tuple((alternative.rank, alternative.move.uci) for alternative in context.alternatives)


def test_valid_preparation_retains_original_basis_and_judgement_without_mutation():
    original = basis()
    j = judgement()
    context = prepare(j, original)
    assert context.base is BASE
    assert context.judgement is j and context.position_analysis is original
    assert context.played_move == rules.legal_move_from_uci(BASE, "e2e4")
    assert context.best_move == context.played_move
    assert context.alternative_scope is AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES
    assert selected(context) == ((2, "d2d4"), (3, "g1f3"))
    assert tuple(line.first_move.uci for line in original.lines) == MOVES


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"position_id": "another-position"}, "another position"),
        ({"mover": Color.BLACK}, "side to move"),
    ],
)
def test_judgement_binding_rejected(changes, message):
    with pytest.raises(IncompatibleGoodMoveContextError, match=message):
        prepare(judgement(**changes))


def test_supplied_and_judged_played_moves_must_match():
    with pytest.raises(IncompatibleGoodMoveContextError, match="differs from the judged"):
        prepare(played=ChessMove("d2d4"))


@pytest.mark.parametrize("role", ["supplied", "judged", "best", "ranked"])
@pytest.mark.parametrize(
    ("uci", "cause"),
    [
        ("e2e5", IllegalMoveError),
        ("not-a-move", InvalidUciError),
        ("0000", NullMoveNotAllowedError),
    ],
)
def test_all_move_revalidation_failures_become_p9_errors(role, uci, cause):
    j = judgement()
    analysis = basis()
    played = j.move
    if role == "supplied":
        played = ChessMove(uci)
    elif role == "judged":
        j = replace(j, move=ChessMove(uci))
    elif role == "best":
        j = replace(j, best_move=ChessMove(uci))
    else:
        # Even an unselected rank beyond the first two alternatives is validated.
        analysis = basis(MOVES[:3] + (uci,))
    with pytest.raises(IncompatibleGoodMoveContextError) as raised:
        prepare(j, analysis, played=played)
    assert isinstance(raised.value.__cause__, cause)


def test_unexpected_rules_failure_is_not_swallowed():
    class BrokenRules:
        def legal_move_from_uci(self, position, uci):
            raise RuntimeError("unexpected rules defect")

    with pytest.raises(RuntimeError, match="unexpected rules defect"):
        prepare(chess=BrokenRules())


def test_position_analysis_binding_rejected():
    with pytest.raises(IncompatibleGoodMoveContextError, match="position analysis belongs"):
        prepare(analysis=replace(basis(), position_id="another-position"))


def test_rank_order_is_sorted_for_selection_without_mutating_analysis():
    original = basis()
    shuffled = replace(original, lines=tuple(reversed(original.lines)))
    assert selected(prepare(analysis=shuffled)) == ((2, "d2d4"), (3, "g1f3"))
    assert tuple(line.rank for line in shuffled.lines) == (4, 3, 2, 1)


@pytest.mark.parametrize("ranks", [(1, 3), (1, 2, 4), (1, 4, 5)])
def test_engine_domain_valid_rank_gaps_are_rejected_by_p9(ranks):
    analysis = basis(MOVES[: len(ranks)], ranks=ranks)
    with pytest.raises(IncompatibleGoodMoveContextError, match="contiguous"):
        prepare(analysis=analysis)


def test_rank_one_must_match_canonical_judged_best():
    with pytest.raises(IncompatibleGoodMoveContextError, match="rank-1 move differs"):
        prepare(judgement(best_move=ChessMove("d2d4")))


@pytest.mark.parametrize("rank", [None, 1, 2, 4])
def test_played_basis_rank_mismatch_rejected(rank):
    with pytest.raises(IncompatibleGoodMoveContextError, match="judgement rank differs"):
        prepare(judgement(quality=MoveQuality.GOOD, move=ChessMove("g1f3"), rank=rank))


def test_played_basis_rank_match_and_selection_gaps_retained():
    context = prepare(judgement(quality=MoveQuality.GOOD, move=ChessMove("g1f3"), rank=3))
    assert context.judgement.rank == 3
    assert selected(context) == ((1, "e2e4"), (2, "d2d4"))


def test_absent_played_move_with_no_rank_is_valid():
    context = prepare(judgement(quality=MoveQuality.GOOD, move=ChessMove("b1c3"), rank=None))
    assert selected(context) == ((1, "e2e4"), (2, "d2d4"))


@pytest.mark.parametrize("rank", [1, 2, 5])
def test_absent_played_move_cannot_claim_basis_rank(rank):
    with pytest.raises(IncompatibleGoodMoveContextError, match="judgement rank differs"):
        prepare(judgement(quality=MoveQuality.GOOD, move=ChessMove("b1c3"), rank=rank))


def test_whitespace_and_san_are_not_move_identity():
    analysis = basis((" e2e4 ", " d2d4 ", "g1f3"))
    j = judgement(move=ChessMove("e2e4", "irrelevant"), best_move=ChessMove(" e2e4 ", "other"))
    context = prepare(j, analysis, played=ChessMove("\t e2e4 \n", "different"))
    assert context.played_move.uci == "e2e4"
    assert context.played_move.san == "e4"
    assert selected(context) == ((2, "d2d4"), (3, "g1f3"))
    assert context.alternatives[0].move.san == "d4"


def test_castling_alias_binds_played_judged_best_and_rank_one():
    analysis = basis(("e1h1", "a1a2"), base=CASTLING)
    j = judgement(
        position_id=CASTLING.position_id,
        move=ChessMove("e1g1"),
        best_move=ChessMove(" e1h1 ", "ignored"),
    )
    context = prepare(j, analysis, base=CASTLING, played=ChessMove("e1h1"))
    assert context.played_move.uci == context.best_move.uci == "e1g1"
    assert selected(context) == ((2, "a1a2"),)
    assert analysis.lines[0].first_move.uci == "e1h1"


def test_selected_castling_alternative_has_canonical_uci():
    analysis = basis(("e1h1", "a1a2", "e1a1"), base=CASTLING)
    j = judgement(
        position_id=CASTLING.position_id,
        move=ChessMove("a1a2"),
        best_move=ChessMove("e1g1"),
        rank=2,
        quality=MoveQuality.GOOD,
    )
    assert selected(prepare(j, analysis, base=CASTLING)) == ((1, "e1g1"), (3, "e1c1"))


@pytest.mark.parametrize("quality", [MoveQuality.BEST, MoveQuality.BLUNDER])
def test_duplicate_castling_aliases_fail_before_played_exclusion_or_applicability(quality):
    analysis = basis(("e1g1", "e1h1"), base=CASTLING)
    j = judgement(
        position_id=CASTLING.position_id,
        move=ChessMove("e1g1"),
        best_move=ChessMove("e1h1"),
        quality=quality,
    )
    with pytest.raises(IncompatibleGoodMoveContextError, match="duplicate canonical"):
        prepare(j, analysis, base=CASTLING)


def test_duplicate_canonical_move_in_unselected_tail_is_rejected():
    with pytest.raises(IncompatibleGoodMoveContextError, match="duplicate canonical"):
        prepare(analysis=basis(MOVES + (" e2e4 ",)))


@pytest.mark.parametrize("quality", [MoveQuality.BEST, MoveQuality.EXCELLENT, MoveQuality.GOOD])
def test_exact_eligible_qualities_prepare(quality):
    assert isinstance(prepare(judgement(quality=quality)), GoodMovePreparedContext)


@pytest.mark.parametrize(
    "quality", [MoveQuality.INACCURACY, MoveQuality.MISTAKE, MoveQuality.BLUNDER]
)
def test_non_eligible_quality_returns_only_validated_move_identity(quality):
    context = prepare(judgement(quality=quality))
    assert isinstance(context, GoodMoveNotApplicable)
    assert context.base_position_id == BASE.position_id
    assert context.played_move == rules.legal_move_from_uci(BASE, "e2e4")
    assert tuple(field.name for field in fields(context)) == ("base_position_id", "played_move")


@pytest.mark.parametrize(
    "quality", [MoveQuality.INACCURACY, MoveQuality.MISTAKE, MoveQuality.BLUNDER]
)
@pytest.mark.parametrize("defect", ["gap", "illegal", "duplicate", "position", "best", "rank"])
def test_malformed_basis_is_rejected_even_for_non_applicable_quality(quality, defect):
    j = judgement(quality=quality)
    analysis = basis()
    if defect == "gap":
        analysis = basis(MOVES[:2], ranks=(1, 3))
    elif defect == "illegal":
        analysis = basis(MOVES[:3] + ("e2e5",))
    elif defect == "duplicate":
        analysis = basis(MOVES + ("e2e4",))
    elif defect == "position":
        analysis = replace(analysis, position_id="another-position")
    elif defect == "best":
        j = replace(j, best_move=ChessMove("d2d4"))
    else:
        j = replace(j, rank=None)
    with pytest.raises(IncompatibleGoodMoveContextError):
        prepare(j, analysis)


def test_best_quality_requires_played_best_without_recomputing_quality():
    with pytest.raises(IncompatibleGoodMoveContextError, match="BEST played move"):
        prepare(judgement(move=ChessMove("d2d4"), rank=2))


@pytest.mark.parametrize("level", list(ForcednessLevel))
def test_best_forcedness_hint_selects_mode_only(level):
    context = prepare(judgement(forcedness=Forcedness(level)))
    expected = (
        GoodMoveMode.ONLY_MOVE_CANDIDATE
        if level is ForcednessLevel.ONLY_MOVE
        else GoodMoveMode.STRONG_MOVE
    )
    assert context.mode is expected
    assert not hasattr(context, "literal_only_move_proven")


@pytest.mark.parametrize("quality", [MoveQuality.EXCELLENT, MoveQuality.GOOD])
@pytest.mark.parametrize("played_is_best", [True, False])
def test_good_and_excellent_only_hint_still_use_strong_mode(quality, played_is_best):
    move, rank = ("e2e4", 1) if played_is_best else ("d2d4", 2)
    context = prepare(
        judgement(
            quality=quality,
            move=ChessMove(move),
            rank=rank,
            forcedness=Forcedness(ForcednessLevel.ONLY_MOVE),
        )
    )
    assert context.mode is GoodMoveMode.STRONG_MOVE
    expected = ((2, "d2d4"), (3, "g1f3")) if played_is_best else ((1, "e2e4"), (3, "g1f3"))
    assert selected(context) == expected


@pytest.mark.parametrize("ucis", [MOVES[:1], MOVES[:2], MOVES[:3], MOVES + ("b1c3",)])
def test_zero_one_or_at_most_two_alternatives_are_valid(ucis):
    context = prepare(analysis=basis(ucis))
    expected = tuple(enumerate(ucis, start=1))[1:3]
    assert selected(context) == expected
    assert len(context.alternatives) <= 2


def test_only_move_candidate_without_alternatives_remains_eligible():
    context = prepare(judgement(forcedness=Forcedness(ForcednessLevel.ONLY_MOVE)), basis(MOVES[:1]))
    assert context.mode is GoodMoveMode.ONLY_MOVE_CANDIDATE
    assert selected(context) == ()


def test_selection_is_unchanged_by_scores_wdl_or_engine_budget():
    original = basis()
    changed = replace(
        original,
        engine=EngineIdentity("Other original ranking basis"),
        settings=EngineSettings(EngineLimit(nodes=7), multipv=4, threads=8, hash_mb=64),
        lines=tuple(
            replace(line, score=EngineScore.cp(line.rank * 900), wdl=WDL(0.0, 0.0, 1.0))
            for line in original.lines
        ),
    )
    j = judgement()
    changed_j = replace(
        j,
        best_score=EngineScore.cp(-900),
        played_score=EngineScore.cp(900),
        cp_loss=900,
        expected_score_loss=1.0,
        forcedness=Forcedness(
            ForcednessLevel.UNKNOWN, acceptable_move_count=1, best_to_second_gap_cp=900
        ),
    )
    assert selected(prepare(j, original)) == selected(prepare(changed_j, changed))
    assert prepare(changed_j, changed).position_analysis is changed


def test_numeric_fields_are_not_read_even_when_access_raises(monkeypatch):
    analysis = basis()
    j = judgement(forcedness=Forcedness(ForcednessLevel.ONLY_MOVE, 1, 900))

    def forbidden(self):
        raise AssertionError("P9-I1 read a selection-opaque field")

    with monkeypatch.context() as patch:
        for cls, names in (
            (EngineLine, ("score", "wdl", "pv", "depth", "seldepth", "nodes")),
            (MoveJudgement, ("best_score", "played_score", "cp_loss", "expected_score_loss")),
            (Forcedness, ("acceptable_move_count", "best_to_second_gap_cp")),
        ):
            for name in names:
                patch.setattr(cls, name, property(forbidden))
        context = prepare(j, analysis)
        assert context.mode is GoodMoveMode.ONLY_MOVE_CANDIDATE
        assert selected(context) == ((2, "d2d4"), (3, "g1f3"))


def test_only_rules_move_validation_is_called_from_the_same_base():
    class MoveValidationOnly:
        def __init__(self):
            self.calls = []

        def legal_move_from_uci(self, position, uci):
            self.calls.append((position, uci))
            return rules.legal_move_from_uci(position, uci)

        def __getattr__(self, name):
            raise AssertionError(f"unexpected dependency or rules operation: {name}")

    port = MoveValidationOnly()
    assert selected(prepare(chess=port)) == ((2, "d2d4"), (3, "g1f3"))
    assert len(port.calls) == 3 + len(MOVES)
    assert all(position is BASE for position, _ in port.calls)
    assert tuple(field.name for field in fields(GoodMoveExplainer)) == ("chess",)


@pytest.mark.parametrize("value", [prepare(), prepare(judgement(quality=MoveQuality.BLUNDER))])
def test_preparation_values_are_frozen_and_slotted(value):
    assert not hasattr(value, "__dict__")
    field = fields(value)[0].name
    with pytest.raises(FrozenInstanceError):
        setattr(value, field, getattr(value, field))


def test_source_guard_excludes_numeric_policy_and_later_packet_dependencies():
    tree = ast.parse(inspect.getsource(module))
    attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not attrs & {
        "score",
        "wdl",
        "best_score",
        "played_score",
        "cp_loss",
        "expected_score_loss",
        "acceptable_move_count",
        "best_to_second_gap_cp",
        "analyze",
        "execute",
        "apply_move",
        "observe_position",
        "observe_tactics",
    }
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not names & {
        "PositionFactExtractor",
        "BoardDeltaAnalyzer",
        "TacticalDetector",
        "BasePieceIdentityMap",
        "CounterfactualAnalyzer",
        "CounterfactualProbe",
        "CounterfactualBatchRequest",
        "StockfishAdapter",
        "GoodMoveExplanationResult",
    }
    assert "literal_only_move_proven" not in {
        node.arg for node in ast.walk(tree) if isinstance(node, ast.keyword)
    }


def test_internal_export_does_not_change_public_facade():
    assert GoodMoveExplainer is module.GoodMoveExplainer
    assert "GoodMoveExplainer" not in calliope.__all__
    assert not hasattr(calliope, "GoodMoveExplainer")


def test_black_mover_binding_and_selection():
    base = rules.position_from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1")
    j = judgement(
        position_id=base.position_id,
        mover=Color.BLACK,
        move=ChessMove("e7e5"),
        best_move=ChessMove("e7e5"),
    )
    assert selected(prepare(j, basis(("e7e5", "d7d5", "g8f6"), base=base), base=base)) == (
        (2, "d7d5"),
        (3, "g8f6"),
    )
