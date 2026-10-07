"""P9-I6 ONLY_MOVE_CANDIDATE preservation rules: PREVENTS_MATE and PREVENTS_MATERIAL_LOSS."""

import ast
import inspect
import textwrap
from dataclasses import fields, replace

import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis import (
    AlternativeScope,
    BasePieceRef,
    GoodMoveBenefitKind,
    GoodMoveBenefitResult,
    GoodMoveBenefitStatus,
    GoodMoveExplanationResult,
    GoodMoveExplanationStatus,
    GoodMoveMode,
    MateEvidenceLevel,
    TacticalCandidateKind,
)
from calliope.domain.chess import ChessMove, Color, PieceType
from calliope.domain.engine import (
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
from calliope.errors import IncompatibleBadMoveContextError, IncompatibleGoodMoveContextError
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.explanation import GoodMoveExplainer, good_move_preservation
from calliope.services.explanation.good_move_preservation import evaluate_only_move
from calliope.services.explanation.piece_identity import BasePieceIdentityMap
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.tactics import TacticalDetector

rules = PythonChessAdapter()
SETTINGS = EngineSettings(EngineLimit(time_ms=43), multipv=1, threads=1, hash_mb=16)
IDENTITY = EngineIdentity("Scripted P7", "1")

# White to move; Black's queen on b2 mates on the back rank if the rook leaves it.
QUEEN = "6k1/5ppp/8/8/8/8/1q3PPP/3R2K1 w - - 0 1"
# Black to move; the mirrored defence.
BLACK_QUEEN = "3r2k1/1Q3ppp/8/8/8/8/5PPP/6K1 b - - 0 1"
# White rook b1 restrains the a2 pawn.
PROMOTION = "6k1/8/8/8/8/8/p7/1R4K1 w - - 0 1"
START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

K = GoodMoveBenefitKind
S = GoodMoveBenefitStatus
CP0 = EngineScore.cp(0)
ONLY = Forcedness(ForcednessLevel.ONLY_MOVE)

# Quiet, complete (stable at ply 3) continuations.
SAFE = {"h2h3": ("f7f6", "g1h2"), "f2f3": ("f7f6", "g1h1"), "d1e1": ("f7f6", "h2h3")}
# Exact board mate by Black's immediate reply (replay ply 2).
MATE_NOW = {"d1a1": ("b2a1",), "d1b1": ("b2b1",)}
# Rook lost, two further plies -> stable -500.
ROOK_LOST = {"d1d2": ("b2d2", "h2h3", "g8f8"), "d1d4": ("b2d4", "h2h3", "g8f8")}


def mate(color, moves):
    return EngineScore.forced_mate(color, moves)


class Forbidden:
    def __init__(self, label):
        self.label = label

    def __getattr__(self, name):
        raise AssertionError(f"I6 accessed forbidden {self.label}: {name}")


class ScriptedEngine:
    def __init__(self, script):
        self.script = script
        self.calls = []

    def analyze(self, position, settings, root_moves=None):
        self.calls.append((position, settings, root_moves))
        root = root_moves[0].uci if root_moves else None
        ucis, score = self.script.get(
            (position.position_id, root),
            ((root or rules.observe_tactics(position).legal_moves[0].uci,), CP0),
        )
        pv = tuple(ChessMove(u) for u in ucis)
        return EngineAnalysis(
            position.position_id, IDENTITY, settings, (EngineLine(1, pv[0], score, pv),)
        )


class RecordingP7:
    def __init__(self, engine):
        self.delegate = CounterfactualAnalyzer(rules, engine, rules, rules)
        self.calls = []

    def execute(self, request):
        self.calls.append(request)
        return self.delegate.execute(request)


def _line(value):
    if isinstance(value[-1], EngineScore):
        return tuple(value[0]), value[1]
    return tuple(value), CP0


def scenario(fen, moves, lines=None, *, attach=None, ignored=None, forcedness=ONLY):
    """Real I1-I3 pipeline with BEST + ONLY_MOVE hint; ``lines`` maps a first move to its PV."""
    base = rules.position_from_fen(fen)
    played_position = rules.apply_move(base, rules.legal_move_from_uci(base, moves[0]))
    script = {}
    for first, value in (lines or {}).items():
        position = rules.apply_move(base, rules.legal_move_from_uci(base, first))
        script[(position.position_id, None)] = _line(value)
    for q, value in (ignored or {}).items():
        script[(played_position.position_id, q)] = _line(value)
    engine = ScriptedEngine(script)
    p7 = RecordingP7(engine)
    facts = PositionFactExtractor(rules)
    explainer = GoodMoveExplainer(
        rules, facts, BoardDeltaAnalyzer(rules, facts), rules, TacticalDetector(), p7
    )
    basis = tuple(
        EngineLine(i, ChessMove(u), EngineScore.cp(500 - 200 * i), (ChessMove(u),))
        for i, u in enumerate(moves, start=1)
    )
    analysis = EngineAnalysis(
        base.position_id, EngineIdentity("P3"), EngineSettings(EngineLimit(depth=4)), basis
    )
    judgement = MoveJudgement(
        base.position_id,
        base.side_to_move,
        ChessMove(moves[0]),
        ChessMove(moves[0]),
        MoveQuality.BEST,
        1,
        EngineScore.cp(300),
        EngineScore.cp(300),
        0,
        0.0,
        forcedness,
    )
    prepared = explainer.prepare(base, judgement.move, judgement, analysis)
    context = explainer.verify_counterfactuals(explainer.build_branches(prepared), SETTINGS)
    if attach is not None:
        context = explainer.verify_ignored_response(context, ChessMove(attach))
    return explainer, context, p7, engine


def check_invariants(result):
    assert isinstance(result, GoodMoveExplanationResult)
    assert result.mode is GoodMoveMode.ONLY_MOVE_CANDIDATE
    assert result.alternative_scope is AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES
    assert result.literal_only_move_proven is False
    rebuilt = GoodMoveExplanationResult(**{f.name: getattr(result, f.name) for f in fields(result)})
    assert rebuilt == result
    order = [list(GoodMoveBenefitKind).index(b.kind) for b in result.benefits]
    assert order == sorted(order)
    for benefit in result.benefits:
        assert (
            GoodMoveBenefitResult(**{f.name: getattr(benefit, f.name) for f in fields(benefit)})
            == benefit
        )
        assert benefit.kind in (K.PREVENTS_MATE, K.PREVENTS_MATERIAL_LOSS)
        assert benefit.mode is GoodMoveMode.ONLY_MOVE_CANDIDATE
        assert benefit.tested_response is None
        assert len(benefit.probe_results) == 1 + len(result.alternatives)
        ranks = [a.rank for a in benefit.failed_alternatives]
        assert ranks == sorted(ranks)


def explain(*args, **kwargs):
    explainer, context, p7, engine = scenario(*args, **kwargs)
    calls = (len(p7.calls), len(engine.calls))
    result = explainer.explain_only_move(context)
    check_invariants(result)
    assert (len(p7.calls), len(engine.calls)) == calls  # no new P7 or engine work
    assert result.alternatives == context.deterministic.prepared.alternatives
    return result, context


def by_kind(result):
    found = {b.kind: b for b in result.benefits}
    assert len(found) == len(result.benefits)
    return found


def ucis(alternatives):
    return tuple(a.move.uci for a in alternatives)


def base(color, kind, square):
    return BasePieceRef(color, kind, square)


WHITE_KING = base(Color.WHITE, PieceType.KING, "g1")


# ---- mode boundaries -------------------------------------------------------------------------


def test_strong_move_mode_is_rejected():
    explainer, context, p7, _ = scenario(
        QUEEN, ("h2h3", "d1a1"), {**SAFE, **MATE_NOW}, forcedness=Forcedness()
    )
    assert context.deterministic.prepared.mode is GoodMoveMode.STRONG_MOVE
    with pytest.raises(IncompatibleGoodMoveContextError, match="ONLY_MOVE_CANDIDATE"):
        explainer.explain_only_move(context)
    with pytest.raises(IncompatibleGoodMoveContextError, match="ONLY_MOVE_CANDIDATE"):
        evaluate_only_move(explainer.replay_lines(context))
    assert len(p7.calls) == 1


def test_i5_still_rejects_only_move_mode():
    explainer, context, _, _ = scenario(QUEEN, ("h2h3", "d1a1"), {**SAFE, **MATE_NOW})
    with pytest.raises(IncompatibleGoodMoveContextError, match="STRONG_MOVE"):
        explainer.explain_strong_move(context)


def test_no_alternatives_is_inconclusive_without_p7():
    result, context = explain(QUEEN, ("h2h3",), SAFE)
    assert result.status is GoodMoveExplanationStatus.INCONCLUSIVE
    assert result.benefits == () and result.alternatives == ()
    assert context.probe_count == 1


# ---- PREVENTS_MATE ---------------------------------------------------------------------------


def test_exact_immediate_mates_on_every_failed_alternative():
    result, context = explain(QUEEN, ("h2h3", "d1a1", "d1b1"), {**SAFE, **MATE_NOW})
    benefit = by_kind(result)[K.PREVENTS_MATE]
    assert benefit.status is S.SUPPORTED
    assert ucis(benefit.failed_alternatives) == ("d1a1", "d1b1")
    assert benefit.equivalent_alternative_benefit is False  # every alternative mates
    assert benefit.mate_evidence_level is MateEvidenceLevel.EXACT_IMMEDIATE
    assert benefit.replayed_pv_ends_in_checkmate is True
    assert benefit.subject == (WHITE_KING,)
    assert benefit.probe_results == context.batch_a.results
    assert {c.kind for c in benefit.tactical_candidates} <= {
        TacticalCandidateKind.CHECK,
        TacticalCandidateKind.CHECKMATE,
    }
    assert TacticalCandidateKind.CHECKMATE in {c.kind for c in benefit.tactical_candidates}
    assert len(benefit.board_deltas) == 2
    assert result.status is GoodMoveExplanationStatus.SUPPORTED


def test_engine_line_mate_alone_supports():
    result, _ = explain(
        QUEEN, ("h2h3", "f2f3"), {**SAFE, "f2f3": (("b2b1", "d1b1"), mate(Color.BLACK, 4))}
    )
    benefit = by_kind(result)[K.PREVENTS_MATE]
    assert benefit.status is S.SUPPORTED and ucis(benefit.failed_alternatives) == ("f2f3",)
    assert benefit.mate_evidence_level is MateEvidenceLevel.ENGINE_LINE
    assert benefit.replayed_pv_ends_in_checkmate is False
    assert benefit.board_deltas == () and benefit.tactical_candidates == ()


def test_exact_replay_mate_later_in_the_line_is_engine_line_with_exact_flag():
    later = {"d1d7": ("b2b1", "d7d1", "b1d1")}
    result, context = explain(QUEEN, ("h2h3", "d1d7"), {**SAFE, **later})
    replay_line = context.batch_a.results[1].engine_analysis.best_line.pv
    assert len(replay_line) == 3
    benefit = by_kind(result)[K.PREVENTS_MATE]
    assert benefit.status is S.SUPPORTED
    assert benefit.mate_evidence_level is MateEvidenceLevel.ENGINE_LINE
    assert benefit.replayed_pv_ends_in_checkmate is True


def test_mixed_failures_never_upgrade_evidence():
    # A1 immediate exact mate, A2 P7 mate only -> ENGINE_LINE, not every line exact.
    result, _ = explain(
        QUEEN,
        ("h2h3", "d1a1", "f2f3"),
        {**SAFE, **MATE_NOW, "f2f3": (("b2b1", "d1b1"), mate(Color.BLACK, 4))},
    )
    benefit = by_kind(result)[K.PREVENTS_MATE]
    assert ucis(benefit.failed_alternatives) == ("d1a1", "f2f3")
    assert benefit.mate_evidence_level is MateEvidenceLevel.ENGINE_LINE
    assert benefit.replayed_pv_ends_in_checkmate is False
    # A1 immediate exact mate, A2 later exact mate -> ENGINE_LINE, but every line is exact.
    result, _ = explain(
        QUEEN, ("h2h3", "d1a1", "d1d7"), {**SAFE, **MATE_NOW, "d1d7": ("b2b1", "d7d1", "b1d1")}
    )
    benefit = by_kind(result)[K.PREVENTS_MATE]
    assert benefit.mate_evidence_level is MateEvidenceLevel.ENGINE_LINE
    assert benefit.replayed_pv_ends_in_checkmate is True


def test_played_line_also_mated_refutes():
    result, _ = explain(
        QUEEN,
        ("h2h3", "d1a1"),
        {**MATE_NOW, "h2h3": (("f7f6", "g1h2"), mate(Color.BLACK, 6))},
    )
    benefit = by_kind(result)[K.PREVENTS_MATE]
    assert benefit.status is S.REFUTED
    assert ucis(benefit.failed_alternatives) == ("d1a1",)


def test_no_mating_alternative_creates_no_candidate():
    result, _ = explain(QUEEN, ("h2h3", "f2f3", "d1e1"), SAFE)
    assert result.benefits == ()
    assert result.status is GoodMoveExplanationStatus.INCONCLUSIVE


def test_one_mating_one_safe_alternative_records_equivalent_preservation():
    result, _ = explain(QUEEN, ("h2h3", "d1a1", "f2f3"), {**SAFE, **MATE_NOW})
    benefit = by_kind(result)[K.PREVENTS_MATE]
    assert benefit.status is S.SUPPORTED
    assert ucis(benefit.failed_alternatives) == ("d1a1",)
    assert benefit.equivalent_alternative_benefit is True


def test_failed_alternatives_are_exactly_mating_ones_in_rank_order():
    result, _ = explain(QUEEN, ("h2h3", "f2f3", "d1b1"), {**SAFE, **MATE_NOW})
    benefit = by_kind(result)[K.PREVENTS_MATE]
    assert [(a.rank, a.move.uci) for a in benefit.failed_alternatives] == [(3, "d1b1")]


def test_centipawn_collapse_is_not_mate_failure():
    result, _ = explain(
        QUEEN, ("h2h3", "f2f3"), {**SAFE, "f2f3": (("f7f6", "g1h1"), EngineScore.cp(-5000))}
    )
    assert K.PREVENTS_MATE not in by_kind(result)


def test_black_mover_mate_symmetry():
    lines = {"h7h6": ("f2f3", "g8h7"), "d8a8": ("b7a8",), "d8b8": ("b7b8",)}
    result, _ = explain(BLACK_QUEEN, ("h7h6", "d8a8", "d8b8"), lines)
    benefit = by_kind(result)[K.PREVENTS_MATE]
    assert benefit.subject == (base(Color.BLACK, PieceType.KING, "g8"),)
    assert benefit.status is S.SUPPORTED
    assert benefit.mate_evidence_level is MateEvidenceLevel.EXACT_IMMEDIATE
    material = by_kind(result)[K.PREVENTS_MATERIAL_LOSS]
    assert [m.material_delta for m in material.material_evidence] == [0, -500, -500]
    assert material.subject == (base(Color.BLACK, PieceType.ROOK, "d8"),)


def test_missing_mover_king_fails_closed():
    explainer, context, _, _ = scenario(QUEEN, ("h2h3", "d1a1"), {**SAFE, **MATE_NOW})
    replay = explainer.replay_lines(context)
    d = replay.counterfactual.deterministic
    entries = tuple(e for e in d.root_identity._entries if e[0] != WHITE_KING)
    broken = replace(
        replay,
        counterfactual=replace(
            replay.counterfactual,
            deterministic=replace(d, root_identity=replace(d.root_identity, _entries=entries)),
        ),
    )
    with pytest.raises(IncompatibleGoodMoveContextError, match="mover king"):
        evaluate_only_move(broken)


# ---- PREVENTS_MATERIAL_LOSS ------------------------------------------------------------------

LOSE_PAWN = {
    "h2h3": ("b2f2", "g1h2", "g8f8"),  # played concedes f2: -100
    "g1h1": ("b2f2", "h2h3", "g8f8"),
}


@pytest.mark.parametrize(
    "played,alternatives,lines,status,failed,equivalent,deltas",
    [
        ("h2h3", ("d1d2",), {**SAFE, **ROOK_LOST}, S.SUPPORTED, ("d1d2",), False, [0, -500]),
        (
            "h2h3",
            ("d1d2",),
            {**ROOK_LOST, "h2h3": LOSE_PAWN["h2h3"]},
            S.SUPPORTED,
            ("d1d2",),
            False,
            [-100, -500],
        ),
        ("d1d2", ("d1d4",), ROOK_LOST, S.REFUTED, (), True, [-500, -500]),
        (
            "d1d2",
            ("g1h1",),
            {**ROOK_LOST, **LOSE_PAWN},
            S.REFUTED,
            (),
            True,
            [-500, -100],
        ),
        ("h2h3", ("d1d2",), {**ROOK_LOST, "h2h3": ("f7f6",)}, S.INCONCLUSIVE, (), None, None),
        (
            "h2h3",
            ("d1d2", "f2f3"),
            {**SAFE, **ROOK_LOST, "f2f3": ("f7f6",)},
            S.INCONCLUSIVE,
            ("d1d2",),
            None,
            None,
        ),
        (
            "h2h3",
            ("d1d2", "f2f3"),
            {**SAFE, **ROOK_LOST},
            S.SUPPORTED,
            ("d1d2",),
            True,
            [0, -500, 0],
        ),
        (
            "h2h3",
            ("d1d2", "g1h1"),
            {**SAFE, **ROOK_LOST, "g1h1": LOSE_PAWN["g1h1"]},
            S.SUPPORTED,
            ("d1d2", "g1h1"),
            False,
            [0, -500, -100],
        ),
    ],
    ids=[
        "M0-A500",
        "M100-A500",
        "M500-A500",
        "M500-A100",
        "M-incomplete",
        "A2-incomplete",
        "A2-preserves",
        "A2-smaller-loss",
    ],
)
def test_material_preservation_matrix(
    played, alternatives, lines, status, failed, equivalent, deltas
):
    result, _ = explain(QUEEN, (played, *alternatives), lines)
    benefit = by_kind(result)[K.PREVENTS_MATERIAL_LOSS]
    assert benefit.status is status
    assert ucis(benefit.failed_alternatives) == failed
    assert benefit.equivalent_alternative_benefit is equivalent
    assert [m.probe.intervention_move.uci for m in benefit.material_evidence] == [
        played,
        *alternatives,
    ]
    if deltas is not None:
        assert [m.material_delta for m in benefit.material_evidence] == deltas
    assert benefit.subject and benefit.material_evidence


def test_captured_mover_piece_subject_and_deltas():
    result, _ = explain(QUEEN, ("h2h3", "d1d2"), {**SAFE, **ROOK_LOST})
    benefit = by_kind(result)[K.PREVENTS_MATERIAL_LOSS]
    assert benefit.subject == (base(Color.WHITE, PieceType.ROOK, "d1"),)
    assert len(benefit.board_deltas) == 1
    capture = benefit.board_deltas[0].capture
    assert capture.captured.square == "d2" and capture.captured.color is Color.WHITE


def test_subjects_from_different_failed_alternatives_consolidate():
    result, _ = explain(
        QUEEN, ("h2h3", "d1d2", "g1h1"), {**SAFE, **ROOK_LOST, "g1h1": LOSE_PAWN["g1h1"]}
    )
    benefit = by_kind(result)[K.PREVENTS_MATERIAL_LOSS]
    assert benefit.subject == (
        base(Color.WHITE, PieceType.ROOK, "d1"),
        base(Color.WHITE, PieceType.PAWN, "f2"),
    )
    assert len(benefit.board_deltas) == 2


def test_opponent_promotion_is_a_negative_material_event():
    lines = {
        "b1a1": ("g8f7", "g1f2", "f7e6"),
        "b1b8": ("g8h7", "g1f2", "a2a1q", "b8b7", "h7g6"),
    }
    result, _ = explain(PROMOTION, ("b1a1", "b1b8"), lines)
    benefit = by_kind(result)[K.PREVENTS_MATERIAL_LOSS]
    assert [m.material_delta for m in benefit.material_evidence] == [0, -800]
    assert benefit.subject == (base(Color.BLACK, PieceType.PAWN, "a2"),)
    assert benefit.status is S.SUPPORTED


def test_no_stable_alternative_deficit_creates_no_candidate():
    result, _ = explain(QUEEN, ("h2h3", "d1d2"), {**SAFE, "d1d2": ("b2d2",)})
    assert K.PREVENTS_MATERIAL_LOSS not in by_kind(result)


def test_stable_deficit_without_negative_event_fails_closed():
    explainer, context, _, _ = scenario(QUEEN, ("h2h3", "f2f3"), SAFE)
    replay = explainer.replay_lines(context)
    alternative = replay.alternatives[0]
    material = replace(alternative.evidence.material, material_delta=-500)
    tampered = replace(
        replay,
        alternatives=(
            replace(alternative, evidence=replace(alternative.evidence, material=material)),
        ),
    )
    with pytest.raises(IncompatibleGoodMoveContextError, match="negative material event"):
        evaluate_only_move(tampered)


def test_identity_error_in_negative_event_translates_with_cause(monkeypatch):
    explainer, context, _, _ = scenario(QUEEN, ("h2h3", "d1d2"), {**SAFE, **ROOK_LOST})
    replay = explainer.replay_lines(context)
    cause = IncompatibleBadMoveContextError("no base piece")

    def base_ref_for(self, piece):
        raise cause

    monkeypatch.setattr(BasePieceIdentityMap, "base_ref_for", base_ref_for)
    with pytest.raises(IncompatibleGoodMoveContextError) as caught:
        evaluate_only_move(replay)
    assert caught.value.__cause__ is cause


def test_black_mover_material_signs():
    result, _ = explain(
        BLACK_QUEEN,
        ("h7h6", "d8d7"),
        {"h7h6": ("f2f3", "g8h7"), "d8d7": ("b7d7", "h7h6", "f2f3")},
    )
    benefit = by_kind(result)[K.PREVENTS_MATERIAL_LOSS]
    assert [m.material_delta for m in benefit.material_evidence] == [0, -500]
    assert benefit.subject == (base(Color.BLACK, PieceType.ROOK, "d8"),)
    assert benefit.status is S.SUPPORTED


# ---- aggregate -------------------------------------------------------------------------------


def test_mate_supported_with_material_refuted_is_supported():
    result, _ = explain(QUEEN, ("d1d2", "d1a1", "d1d4"), {**ROOK_LOST, **MATE_NOW})
    kinds = by_kind(result)
    assert kinds[K.PREVENTS_MATE].status is S.SUPPORTED
    assert kinds[K.PREVENTS_MATERIAL_LOSS].status is S.REFUTED
    assert kinds[K.PREVENTS_MATERIAL_LOSS].failed_alternatives == ()
    assert [b.kind for b in result.benefits] == [K.PREVENTS_MATE, K.PREVENTS_MATERIAL_LOSS]
    assert result.status is GoodMoveExplanationStatus.SUPPORTED


def test_mate_and_material_both_refuted_is_refuted():
    lines = {
        **ROOK_LOST,
        **MATE_NOW,
        "d1d2": (ROOK_LOST["d1d2"], mate(Color.BLACK, 5)),
    }
    result, _ = explain(QUEEN, ("d1d2", "d1a1", "d1d4"), lines)
    assert {b.status for b in result.benefits} == {S.REFUTED}
    assert len(result.benefits) == 2
    assert result.status is GoodMoveExplanationStatus.REFUTED


def test_material_inconclusive_alone_is_inconclusive():
    result, _ = explain(QUEEN, ("h2h3", "d1d2"), {**ROOK_LOST, "h2h3": ("f7f6",)})
    assert [b.status for b in result.benefits] == [S.INCONCLUSIVE]
    assert result.status is GoodMoveExplanationStatus.INCONCLUSIVE


def test_both_alternatives_fail_still_representative_only():
    result, _ = explain(QUEEN, ("h2h3", "d1a1", "d1b1"), {**SAFE, **MATE_NOW})
    assert all(b.failed_alternatives == result.alternatives for b in result.benefits)
    assert result.literal_only_move_proven is False
    assert result.alternative_scope is AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES
    assert all(
        b.alternative_scope is AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES
        for b in result.benefits
    )


# ---- Batch-B invariance ----------------------------------------------------------------------


def test_pre_attached_batch_b_never_changes_preservation_result():
    lines = {**SAFE, **MATE_NOW, **ROOK_LOST}
    ignored = {"b2b1": (("b2b1", "d1b1", "g8f8", "b1b8"), mate(Color.BLACK, 1))}
    plain, plain_context = explain(QUEEN, ("h2h3", "d1a1", "d1d2"), lines)
    explainer, context, p7, engine = scenario(
        QUEEN, ("h2h3", "d1a1", "d1d2"), lines, attach="b2b1", ignored=ignored
    )
    assert context.probe_count == 4 and len(p7.calls) == 2
    calls = (len(p7.calls), len(engine.calls))
    explainer.counterfactual = Forbidden("P7")
    attached = explainer.explain_only_move(context)
    assert explainer.explain_only_move(context) == attached
    assert (len(p7.calls), len(engine.calls)) == calls
    assert attached == plain
    batch_b = context.ignored_response_result
    for benefit in attached.benefits:
        assert benefit.tested_response is None
        assert batch_b not in benefit.probe_results
        assert all(m.probe.kind.value == "refutation" for m in benefit.material_evidence)
    assert plain_context.batch_b is None


def test_p3_judgement_and_basis_are_never_read():
    explainer, context, _, _ = scenario(
        QUEEN, ("h2h3", "d1a1", "d1d2"), {**SAFE, **MATE_NOW, **ROOK_LOST}
    )
    d = context.deterministic
    prepared = replace(
        d.prepared, judgement=Forbidden("judgement"), position_analysis=Forbidden("basis")
    )
    guarded = replace(context, deterministic=replace(d, prepared=prepared))
    result = explainer.explain_only_move(guarded)
    assert result.status is GoodMoveExplanationStatus.SUPPORTED


def test_explain_only_move_makes_no_p7_or_engine_call():
    explainer, context, _, engine = scenario(QUEEN, ("h2h3", "d1a1"), {**SAFE, **MATE_NOW})
    explainer.counterfactual = Forbidden("P7")

    def analyze(*args, **kwargs):
        raise AssertionError("I6 called the engine")

    engine.analyze = analyze
    assert explainer.explain_only_move(context).status is GoodMoveExplanationStatus.SUPPORTED


def test_i6_source_boundary():
    module = ast.parse(inspect.getsource(good_move_preservation))
    method = ast.parse(textwrap.dedent(inspect.getsource(GoodMoveExplainer.explain_only_move)))
    for tree in (module, method):
        attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not attributes & {
            "execute",
            "analyze",
            "judgement",
            "position_analysis",
            "best_score",
            "played_score",
            "cp_loss",
            "expected_score_loss",
            "acceptable_move_count",
            "best_to_second_gap_cp",
            "wdl",
            "centipawns",
            "centipawns_for",
            "score",
            "ignored_response",
            "ignored_response_result",
            "batch_b",
            "FORCES_RESPONSE",
            "MATE_THREAT",
            "MATERIAL_THREAT",
            "FORCED",
            "verify_ignored_response",
            "explain_strong_move",
            "_select_tested_threat",
        }
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert not names & {
            "evaluate_strong_move",
            "GoodMoveTestedThreat",
            "material_resources",
            "outcome_key",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "literal_only_move_proven":
                assert isinstance(node.value, ast.Constant) and node.value.value is False
    source = inspect.getsource(good_move_preservation)
    for forbidden in ("ALL_ALTERNATIVES_FAIL", "EXHAUSTIVE_ONLY_MOVE"):
        assert forbidden not in source


PAWN_D5 = "6k1/5ppp/8/3p4/8/8/1q3PPP/3R2K1 w - - 0 1"


def test_mover_gains_inside_a_failed_line_are_not_loss_subjects():
    # Rxd5 wins a pawn, then Qb1+ Rd1 Qxd1# wins the rook: only the rook is a loss subject.
    lines = {**SAFE, "d1d5": ("b2b1", "d5d1", "b1d1")}
    result, _ = explain(PAWN_D5, ("h2h3", "d1d5"), lines)
    benefit = by_kind(result)[K.PREVENTS_MATERIAL_LOSS]
    assert [m.material_delta for m in benefit.material_evidence] == [0, -400]
    assert benefit.subject == (base(Color.WHITE, PieceType.ROOK, "d1"),)
    assert by_kind(result)[K.PREVENTS_MATE].status is S.SUPPORTED


def test_played_material_gain_is_clamped_to_zero_deficit():
    lines = {"d1d5": ("f7f6", "h2h3"), **ROOK_LOST, **SAFE}
    result, _ = explain(PAWN_D5, ("d1d5", "d1d2", "h2h3"), lines)
    benefit = by_kind(result)[K.PREVENTS_MATERIAL_LOSS]
    assert [m.material_delta for m in benefit.material_evidence] == [100, -500, 0]
    assert ucis(benefit.failed_alternatives) == ("d1d2",)
    assert benefit.equivalent_alternative_benefit is True
