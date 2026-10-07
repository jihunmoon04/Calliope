"""P9-I5 STRONG_MOVE benefit rules: FORCES_RESPONSE, MATE_THREAT and MATERIAL_THREAT."""

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
    ProbeKind,
    TacticalCandidateKind,
    TerminalKind,
    TerminalOutcome,
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
    ForcednessLevel,
    MoveJudgement,
    MoveQuality,
)
from calliope.errors import IncompatibleGoodMoveContextError
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.explanation import GoodMoveExplainer, good_move, good_move_benefits
from calliope.services.explanation.good_move_benefits import (
    GoodMoveTestedThreat,
    evaluate_strong_move,
    material_resources,
    outcome_key,
)
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.tactics import TacticalDetector

rules = PythonChessAdapter()
SETTINGS = EngineSettings(EngineLimit(time_ms=41), multipv=1, threads=1, hash_mb=16)
IDENTITY = EngineIdentity("Scripted P7", "1")

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
QUEEN = "7k/8/6K1/8/8/8/8/5Q2 w - - 0 1"
ROOK_CHECK = "k7/8/2K5/8/8/8/8/1R6 w - - 0 1"
CASTLE_CHECK = "2rkr3/2p1p3/8/8/8/8/8/R3Kn2 w Q - 0 1"
BACK_RANK = "6k1/5ppp/8/8/8/8/3B4/3Q2K1 w - - 0 1"
BACK_RANK_KNIGHT = "6k1/n4ppp/8/8/8/8/3B4/3Q2K1 w - - 0 1"
ROOK_TAKES = "4k3/8/8/3n4/8/8/8/3RK3 w - - 0 1"
TWO_KNIGHTS = "4k3/8/8/3n4/8/8/8/n2RK3 w - - 0 1"
KNIGHT_QUEEN = "4k3/8/8/3n4/q7/8/2B5/3RK3 w - - 0 1"
KNIGHT_PAWN = "4k3/8/8/3n4/8/8/4p3/3RK3 w - - 0 1"
ROOK_HANGS = "4k3/8/8/3n4/8/8/8/2R1K3 w - - 0 1"
PROMOTE = "1n5k/P7/8/8/8/8/8/K7 w - - 0 1"
ATTACK = "4k3/p7/8/7n/8/8/8/R3K3 w - - 0 1"
ATTACK_SOLO = "4k3/8/8/7n/8/8/8/R3K3 w - - 0 1"
ROOK_ATTACK = "4k3/8/8/7r/8/8/8/R3K3 w - - 0 1"
FORK = "7k/8/1r3b2/8/8/2N5/8/4K3 w - - 0 1"
DOUBLE = "4k3/r2q4/8/8/3N4/8/8/3RK3 w - - 0 1"
BLACK_TAKES = "3rk3/8/8/3N4/8/8/8/4K3 b - - 0 1"

K = GoodMoveBenefitKind
S = GoodMoveBenefitStatus
CP0 = EngineScore.cp(0)


def mate(color, moves):
    return EngineScore.forced_mate(color, moves)


class Forbidden:
    def __init__(self, label):
        self.label = label

    def __getattr__(self, name):
        raise AssertionError(f"I5 accessed forbidden {self.label}: {name}")


class ScriptedEngine:
    """Scripted (PV, score) per (analysis position, forced root)."""

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
        line = EngineLine(1, pv[0], score, pv)
        return EngineAnalysis(position.position_id, IDENTITY, settings, (line,))


class RecordingP7:
    def __init__(self, engine):
        self.delegate = CounterfactualAnalyzer(rules, engine, rules, rules)
        self.calls = []

    def execute(self, request):
        self.calls.append(request)
        return self.delegate.execute(request)


class ReversedRules:
    """Same exact rules, legal moves reported in reverse order."""

    def observe_tactics(self, position):
        observed = rules.observe_tactics(position)
        return replace(observed, legal_moves=observed.legal_moves[::-1])


def _line(value):
    return (
        value
        if isinstance(value, tuple) and isinstance(value[-1], EngineScore)
        else (
            value,
            CP0,
        )
    )


def scenario(
    fen,
    moves,
    lines=None,
    *,
    ignored=None,
    attach=None,
    quality=MoveQuality.GOOD,
    forcedness=None,
    tactical_rules=rules,
):
    """Real I1-I3 pipeline.  ``lines`` maps a first move to (PV, score) after it;
    ``ignored`` maps a Q to its forced Batch-B (PV, score); ``attach`` pre-attaches Batch B."""
    base = rules.position_from_fen(fen)
    played_position = rules.apply_move(base, rules.legal_move_from_uci(base, moves[0]))
    script = {}
    for first, value in (lines or {}).items():
        position = rules.apply_move(base, rules.legal_move_from_uci(base, first))
        pv, score = _line(value)
        script[(position.position_id, None)] = (tuple(pv), score)
    for q, value in (ignored or {}).items():
        pv, score = _line(value)
        script[(played_position.position_id, q)] = (tuple(pv), score)
    engine = ScriptedEngine(script)
    p7 = RecordingP7(engine)
    facts = PositionFactExtractor(rules)
    explainer = GoodMoveExplainer(
        rules, facts, BoardDeltaAnalyzer(rules, facts), tactical_rules, TacticalDetector(), p7
    )
    basis = tuple(
        EngineLine(i, ChessMove(u), EngineScore.cp(900 - i), (ChessMove(u),))
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
        quality,
        1,
        EngineScore.cp(900),
        EngineScore.cp(900),
        0,
        0.0,
        forcedness or Forcedness(),
    )
    prepared = explainer.prepare(base, judgement.move, judgement, analysis)
    context = explainer.verify_counterfactuals(explainer.build_branches(prepared), SETTINGS)
    if attach is not None:
        context = explainer.verify_ignored_response(context, ChessMove(attach))
    return explainer, context, p7, engine


def check_invariants(result):
    """Rebuild every record through the I0 constructors; nothing may be weakened."""
    assert isinstance(result, GoodMoveExplanationResult)
    for benefit in result.benefits:
        assert (
            GoodMoveBenefitResult(**{f.name: getattr(benefit, f.name) for f in fields(benefit)})
            == benefit
        )
        assert benefit.kind in (K.FORCES_RESPONSE, K.MATE_THREAT, K.MATERIAL_THREAT)
        assert benefit.mode is GoodMoveMode.STRONG_MOVE
        assert benefit.failed_alternatives == ()
        assert benefit.alternative_scope is AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES
        assert benefit.alternatives == result.alternatives
        assert len(benefit.probe_results) == len(set(map(id, benefit.probe_results)))
        expected = {S.REFUTED: True, S.INCONCLUSIVE: None, S.SUPPORTED: False}[benefit.status]
        assert benefit.equivalent_alternative_benefit is expected
    rebuilt = GoodMoveExplanationResult(**{f.name: getattr(result, f.name) for f in fields(result)})
    assert rebuilt == result
    assert result.literal_only_move_proven is False
    assert result.mode is GoodMoveMode.STRONG_MOVE
    assert result.alternative_scope is AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES
    order = [list(GoodMoveBenefitKind).index(b.kind) for b in result.benefits]
    assert order == sorted(order)


def explain(*args, **kwargs):
    explainer, context, p7, engine = scenario(*args, **kwargs)
    before = len(p7.calls)
    result = explainer.explain_strong_move(context)
    check_invariants(result)
    prepared = context.deterministic.prepared
    assert result.base_position_id == prepared.base.position_id
    assert result.played_move == prepared.played_move
    assert result.alternatives == prepared.alternatives
    return result, len(p7.calls) - before, (explainer, context, p7, engine)


def by_kind(result):
    found = {b.kind: b for b in result.benefits}
    assert len(found) == len(result.benefits)
    return found


def base(color, kind, square):
    return BasePieceRef(color, kind, square)


def stable(*pv):
    """A quiet two-ply continuation (stable at ply 3)."""
    return tuple(pv)


# ---- mode and comparator boundaries ----------------------------------------------------------


def test_only_move_candidate_mode_is_rejected_before_any_work():
    explainer, context, p7, _ = scenario(
        START,
        ("e2e4", "d2d4"),
        quality=MoveQuality.BEST,
        forcedness=Forcedness(ForcednessLevel.ONLY_MOVE),
    )
    assert context.deterministic.prepared.mode is GoodMoveMode.ONLY_MOVE_CANDIDATE
    calls = len(p7.calls)
    with pytest.raises(IncompatibleGoodMoveContextError, match="STRONG_MOVE"):
        explainer.explain_strong_move(context)
    replay = explainer.replay_lines(context)
    with pytest.raises(IncompatibleGoodMoveContextError, match="STRONG_MOVE"):
        evaluate_strong_move(replay)
    assert len(p7.calls) == calls


def test_no_alternatives_is_inconclusive_without_batch_b():
    result, calls, _ = explain(
        BACK_RANK, ("d2e3",), {"d2e3": (("h7h6", "g1h2"), CP0)}, ignored={"g8f8": ("g8f8", "d1d8")}
    )
    assert result.status is GoodMoveExplanationStatus.INCONCLUSIVE
    assert result.benefits == () and result.alternatives == ()
    assert calls == 0


# ---- outcome ordering ------------------------------------------------------------------------


def _result_with(context, terminal=None, score=None):
    played = context.played_refutation
    if terminal is not None:
        return replace(played, engine_analysis=None, root_moves=None, terminal=terminal)
    line = replace(played.engine_analysis.best_line, score=score)
    return replace(played, engine_analysis=replace(played.engine_analysis, lines=(line,)))


def test_mate_aware_outcome_key_from_mover_perspective():
    _, context, _, _ = scenario(START, ("e2e4", "d2d4"))
    keys = [
        outcome_key(_result_with(context, score=s), Color.WHITE)
        for s in (
            mate(Color.BLACK, 1),
            mate(Color.BLACK, 6),
            EngineScore.cp(-300),
            EngineScore.cp(250),
            mate(Color.WHITE, 7),
            mate(Color.WHITE, 2),
        )
    ]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)
    mated = TerminalOutcome(TerminalKind.CHECKMATE, Color.WHITE)
    assert outcome_key(_result_with(context, terminal=mated), Color.WHITE) == (2, 0)
    assert outcome_key(_result_with(context, terminal=mated), Color.BLACK) == (0, 0)
    stalemate = TerminalOutcome(TerminalKind.STALEMATE, None)
    assert outcome_key(_result_with(context, terminal=stalemate), Color.WHITE) is None
    assert outcome_key(_result_with(context, score=EngineScore.cp(250)), Color.BLACK) == (1, -250)


# ---- FORCES_RESPONSE -------------------------------------------------------------------------


def test_exact_one_response_move_supported_with_exact_evidence():
    result, calls, (_, context, _, _) = explain(
        ROOK_CHECK,
        ("b1a1", "b1h1", "b1c1"),
        {
            "b1a1": (("a8b8", "c6b6"), EngineScore.cp(800)),
            "b1h1": ("a8b8", "c6d6"),
            "b1c1": ("a8b8", "c6d6"),
        },
    )
    forces = by_kind(result)[K.FORCES_RESPONSE]
    assert forces.status is S.SUPPORTED and forces.equivalent_alternative_benefit is False
    assert forces.subject == (base(Color.WHITE, PieceType.ROOK, "b1"),)
    assert forces.tested_response == ChessMove("a8b8", "Kb8")
    assert forces.tested_response.uci == context.deterministic.played.rules.legal_moves[0].uci
    assert [c.kind for c in forces.tactical_candidates] == [TacticalCandidateKind.FORCED_RESPONSE]
    assert forces.board_deltas == (context.deterministic.played.delta,)
    assert forces.probe_results == context.batch_a.results
    assert result.status is GoodMoveExplanationStatus.SUPPORTED
    assert calls == 0  # no Batch B merely for FORCES_RESPONSE


@pytest.mark.parametrize("played", ["f1f8", "f1f7"])
def test_played_checkmate_or_stalemate_is_not_forces_response(played):
    other = "f1f7" if played == "f1f8" else "f1f8"
    result, calls, _ = explain(QUEEN, (played, other, "f1a1"))
    assert K.FORCES_RESPONSE not in by_kind(result)
    assert calls == 0
    if played == "f1f7":
        assert result.status is GoodMoveExplanationStatus.INCONCLUSIVE and result.benefits == ()


def _narrow_played(context, transform):
    d = context.deterministic
    detection = d.played.detection
    played = replace(d.played, detection=replace(detection, candidates=transform(detection)))
    return replace(context, deterministic=replace(d, played=played))


@pytest.mark.parametrize(
    "transform",
    [
        lambda d: tuple(
            c for c in d.candidates if c.kind is not TacticalCandidateKind.FORCED_RESPONSE
        ),
        lambda d: tuple(
            replace(c, responses=(ChessMove("a8a7"),))
            if c.kind is TacticalCandidateKind.FORCED_RESPONSE
            else c
            for c in d.candidates
        ),
        lambda d: (
            d.candidates
            + tuple(c for c in d.candidates if c.kind is TacticalCandidateKind.FORCED_RESPONSE)
        ),
    ],
    ids=["missing", "other-response", "duplicate"],
)
def test_missing_or_contradictory_p6_forced_response_fails_closed(transform):
    explainer, context, _, _ = scenario(ROOK_CHECK, ("b1a1", "b1h1"))
    with pytest.raises(IncompatibleGoodMoveContextError, match="forced response"):
        explainer.explain_strong_move(_narrow_played(context, transform))


def test_forced_response_candidate_without_single_reply_fails_closed():
    explainer, context, _, _ = scenario(ROOK_CHECK, ("b1h1", "b1a1"))
    forced = next(
        c
        for c in context.deterministic.alternatives[0].branch.detection.candidates
        if c.kind is TacticalCandidateKind.FORCED_RESPONSE
    )
    tampered = _narrow_played(context, lambda d: (*d.candidates, forced))
    with pytest.raises(IncompatibleGoodMoveContextError, match="legal-move count"):
        explainer.explain_strong_move(tampered)


@pytest.mark.parametrize(
    "alternative_score,status",
    [
        (EngineScore.cp(800), S.REFUTED),
        (EngineScore.cp(1200), S.REFUTED),
        (mate(Color.WHITE, 9), S.REFUTED),
        (EngineScore.cp(799), S.SUPPORTED),
        (mate(Color.BLACK, 9), S.SUPPORTED),
    ],
)
def test_one_response_alternative_compared_by_p7_outcome(alternative_score, status):
    result, _, _ = explain(
        ROOK_CHECK,
        ("b1a1", "c6b6", "b1h1"),
        {
            "b1a1": (("a8b8", "c6b6"), EngineScore.cp(800)),
            "c6b6": (("a8b8", "b1h1"), alternative_score),
        },
    )
    forces = by_kind(result)[K.FORCES_RESPONSE]
    assert forces.status is status
    assert forces.equivalent_alternative_benefit is (status is S.REFUTED)


def test_incomparable_stalemate_comparison_is_inconclusive():
    explainer, context, _, _ = scenario(
        ROOK_CHECK, ("b1a1", "c6b6"), {"b1a1": (("a8b8", "c6b6"), EngineScore.cp(800))}
    )
    replay = explainer.replay_lines(context)
    alternative = replay.alternatives[0]
    stalemate = replace(
        alternative.evidence.line.probe_result,
        engine_analysis=None,
        root_moves=None,
        terminal=TerminalOutcome(TerminalKind.STALEMATE, None),
    )
    line = replace(alternative.evidence.line, probe_result=stalemate)
    tampered = replace(
        replay,
        alternatives=(replace(alternative, evidence=replace(alternative.evidence, line=line)),),
    )
    forces = by_kind(evaluate_strong_move(tampered))[K.FORCES_RESPONSE]
    assert forces.status is S.INCONCLUSIVE and forces.equivalent_alternative_benefit is None


def test_castling_forcing_move_subject_is_king_and_rook():
    result, _, _ = explain(CASTLE_CHECK, ("e1c1", "e1f1", "a1a2"), {"e1c1": ("f1d2", "d1d2")})
    forces = by_kind(result)[K.FORCES_RESPONSE]
    assert forces.subject == (
        base(Color.WHITE, PieceType.ROOK, "a1"),
        base(Color.WHITE, PieceType.KING, "e1"),
    )
    assert forces.tested_response.uci == "f1d2"
    assert forces.status is S.SUPPORTED


# ---- MATE_THREAT -----------------------------------------------------------------------------


def test_exact_immediate_mate_supported_with_exact_flag():
    result, calls, _ = explain(QUEEN, ("f1f8", "f1f7", "f1a1"))
    mate_benefit = by_kind(result)[K.MATE_THREAT]
    assert mate_benefit.status is S.SUPPORTED
    assert mate_benefit.mate_evidence_level is MateEvidenceLevel.EXACT_IMMEDIATE
    assert mate_benefit.replayed_pv_ends_in_checkmate is True
    assert mate_benefit.subject == (base(Color.BLACK, PieceType.KING, "h8"),)
    assert mate_benefit.tested_response is None
    assert TacticalCandidateKind.CHECKMATE in {c.kind for c in mate_benefit.tactical_candidates}
    assert calls == 0


@pytest.mark.parametrize("pv,exact", [(("h8g8", "a1a8"), True), (("h8g8",), False)])
def test_played_engine_line_mate_retains_exact_replay_flag(pv, exact):
    result, _, _ = explain(
        QUEEN,
        ("f1a1", "g6f6", "f1h1"),
        {"f1a1": (pv, mate(Color.WHITE, 2)), "g6f6": (("h8g8", "f1f2"), EngineScore.cp(900))},
    )
    mate_benefit = by_kind(result)[K.MATE_THREAT]
    assert mate_benefit.mate_evidence_level is MateEvidenceLevel.ENGINE_LINE
    assert mate_benefit.replayed_pv_ends_in_checkmate is exact
    assert mate_benefit.status is S.SUPPORTED


def test_exact_replay_mate_without_mate_score_still_counts():
    result, _, _ = explain(QUEEN, ("f1a1", "g6f6"), {"f1a1": (("h8g8", "a1a8"), CP0)})
    mate_benefit = by_kind(result)[K.MATE_THREAT]
    assert mate_benefit.replayed_pv_ends_in_checkmate is True
    assert mate_benefit.mate_evidence_level is MateEvidenceLevel.ENGINE_LINE


@pytest.mark.parametrize("alternative_mate", [1, 2, 9])
def test_any_mating_alternative_refutes_regardless_of_distance(alternative_mate):
    result, _, _ = explain(
        QUEEN, ("f1f8", "f1a1"), {"f1a1": (("h8g8",), mate(Color.WHITE, alternative_mate))}
    )
    mate_benefit = by_kind(result)[K.MATE_THREAT]
    assert mate_benefit.status is S.REFUTED and mate_benefit.equivalent_alternative_benefit
    assert result.benefits == (mate_benefit,)
    assert result.status is GoodMoveExplanationStatus.REFUTED


def test_alternative_exact_mate_refutes_engine_line_mate():
    result, _, _ = explain(
        QUEEN, ("f1a1", "f1f8"), {"f1a1": (("h8g8", "a1a8"), mate(Color.WHITE, 2))}
    )
    assert by_kind(result)[K.MATE_THREAT].status is S.REFUTED


def test_mate_evidence_never_claims_forced():
    assert {level.name for level in MateEvidenceLevel} == {"EXACT_IMMEDIATE", "ENGINE_LINE"}


def test_missing_opponent_king_identity_fails_closed():
    explainer, context, _, _ = scenario(QUEEN, ("f1f8", "f1a1"))
    replay = explainer.replay_lines(context)
    d = replay.counterfactual.deterministic
    root = d.root_identity
    entries = tuple(e for e in root._entries if e[0].piece_type is not PieceType.KING)
    broken = replace(
        replay,
        counterfactual=replace(
            replay.counterfactual,
            deterministic=replace(d, root_identity=replace(root, _entries=entries)),
        ),
    )
    with pytest.raises(IncompatibleGoodMoveContextError, match="opponent king"):
        evaluate_strong_move(broken)


# ---- cause-specific ignored mate threat ------------------------------------------------------

BACK_RANK_LINES = {
    "d2e3": (("h7h6", "g1h2"), EngineScore.cp(60)),
    "g1f1": ("h7h6", "f1e2"),
    "g1h1": ("h7h6", "h1g1"),
}


def test_selector_finds_first_exact_mate_in_one_q_and_tests_it_once():
    result, calls, (_, _, p7, _) = explain(
        BACK_RANK,
        ("d2e3", "g1f1", "g1h1"),
        BACK_RANK_LINES,
        ignored={"g8f8": (("g8f8", "d1d8"), mate(Color.WHITE, 1))},
    )
    assert calls == 1
    request = p7.calls[-1]
    assert [p.kind for p in request.probes] == [ProbeKind.IGNORE_THREAT]
    assert request.probes[0].execution_move.uci == "g8f8"
    mate_benefit = by_kind(result)[K.MATE_THREAT]
    assert mate_benefit.status is S.SUPPORTED
    assert mate_benefit.tested_response.uci == "g8f8"
    assert mate_benefit.mate_evidence_level is MateEvidenceLevel.ENGINE_LINE
    assert mate_benefit.replayed_pv_ends_in_checkmate is True
    assert len(mate_benefit.probe_results) == 4
    assert mate_benefit.probe_results[-1].probe.kind is ProbeKind.IGNORE_THREAT


def test_selector_excludes_batch_a_best_response():
    result, calls, (_, _, p7, _) = explain(
        BACK_RANK,
        ("d2e3", "g1f1", "g1h1"),
        {**BACK_RANK_LINES, "d2e3": (("g8f8", "g1h2"), EngineScore.cp(60))},
        ignored={"g8h8": (("g8h8", "d1d8"), mate(Color.WHITE, 1))},
    )
    assert calls == 1 and p7.calls[-1].probes[0].execution_move.uci == "g8h8"
    assert by_kind(result)[K.MATE_THREAT].tested_response.uci == "g8h8"


def test_q_without_exact_mate_in_one_is_not_selected():
    explainer, context, _, _ = scenario(BACK_RANK, ("d2e3", "g1f1"), BACK_RANK_LINES)
    position = context.deterministic.played.position
    leaves = {
        move.uci: explainer._leaves_mate_in_one(position, move)
        for move in context.deterministic.played.rules.legal_moves
    }
    assert {uci for uci, value in leaves.items() if value} == {"g8f8", "g8h8"}


def test_selector_independent_of_legal_move_ordering():
    selected = []
    for tactical_rules in (rules, ReversedRules()):
        _, _, (_, _, p7, _) = explain(
            BACK_RANK,
            ("d2e3", "g1f1", "g1h1"),
            BACK_RANK_LINES,
            ignored={"g8f8": (("g8f8", "d1d8"), mate(Color.WHITE, 1))},
            tactical_rules=tactical_rules,
        )
        selected.append(p7.calls[-1].probes[0].execution_move.uci)
    assert selected == ["g8f8", "g8f8"]


def test_batch_b_without_mate_does_not_manufacture_mate_threat():
    result, calls, _ = explain(
        BACK_RANK,
        ("d2e3", "g1f1", "g1h1"),
        BACK_RANK_LINES,
        ignored={"g8f8": (("g8f8", "d1d7"), EngineScore.cp(150))},
    )
    assert calls == 1
    assert K.MATE_THREAT not in by_kind(result)
    assert result.status is GoodMoveExplanationStatus.INCONCLUSIVE and result.benefits == ()


def test_arbitrary_pre_attached_q_cannot_become_mate_evidence():
    result, calls, (_, context, _, _) = explain(
        BACK_RANK,
        ("d2e3", "g1f1", "g1h1"),
        BACK_RANK_LINES,
        ignored={"f7f6": (("f7f6", "d1d8", "g8f7"), mate(Color.WHITE, 3))},
        attach="f7f6",
    )
    assert context.ignored_response.uci == "f7f6"
    assert calls == 0
    assert result.benefits == ()


def test_pre_attached_cause_specific_q_is_used_without_new_p7():
    result, calls, _ = explain(
        BACK_RANK,
        ("d2e3", "g1f1", "g1h1"),
        BACK_RANK_LINES,
        ignored={"g8h8": (("g8h8", "d1d8"), mate(Color.WHITE, 1))},
        attach="g8h8",
    )
    assert calls == 0
    assert by_kind(result)[K.MATE_THREAT].tested_response.uci == "g8h8"


# ---- direct MATERIAL_THREAT ------------------------------------------------------------------


def test_stable_capture_gain_supported_with_base_subject():
    result, calls, (_, context, _, _) = explain(
        ROOK_TAKES,
        ("d1d5", "e1e2", "e1f2"),
        {"d1d5": ("e8e7", "e1e2"), "e1e2": ("d5c3", "e2e3"), "e1f2": ("d5c3", "f2f3")},
    )
    material = by_kind(result)[K.MATERIAL_THREAT]
    assert material.status is S.SUPPORTED and material.equivalent_alternative_benefit is False
    assert material.subject == (base(Color.BLACK, PieceType.KNIGHT, "d5"),)
    assert material.board_deltas == (context.deterministic.played.delta,)
    assert [m.material_delta for m in material.material_evidence] == [320, 0, 0]
    assert [m.probe.intervention_move.uci for m in material.material_evidence] == [
        "d1d5",
        "e1e2",
        "e1f2",
    ]
    assert material.tested_response is None and material.tactical_candidates == ()
    assert calls == 0


@pytest.mark.parametrize(
    "first,pv,gain,subject",
    [
        ("a7a8q", ("h8g7", "a1b1"), 800, ((Color.WHITE, PieceType.PAWN, "a7"),)),
        (
            "a7b8q",
            ("h8h7", "a1b1"),
            1120,
            ((Color.WHITE, PieceType.PAWN, "a7"), (Color.BLACK, PieceType.KNIGHT, "b8")),
        ),
    ],
)
def test_own_promotion_is_a_positive_material_event(first, pv, gain, subject):
    result, _, _ = explain(
        PROMOTE,
        (first, "a1b1", "a1a2"),
        {first: pv, "a1b1": ("h8g7", "b1c2"), "a1a2": ("h8g7", "a2b3")},
    )
    material = by_kind(result)[K.MATERIAL_THREAT]
    assert material.material_evidence[0].material_delta == gain
    assert material.subject == tuple(base(*s) for s in subject)
    assert material.status is S.SUPPORTED


@pytest.mark.parametrize(
    "fen,alternative,alt_pv,status",
    [
        (TWO_KNIGHTS, "d1a1", ("e8e7", "e1e2"), S.REFUTED),  # equal value, other piece
        (KNIGHT_QUEEN, "c2a4", ("e8e7", "e1e2"), S.REFUTED),  # greater gain
        (KNIGHT_PAWN, "e1e2", ("d5c3", "e2e3"), S.SUPPORTED),  # smaller gain
        (TWO_KNIGHTS, "d1a1", ("e8e7",), S.INCONCLUSIVE),  # truncated alternative
    ],
)
def test_alternative_material_equivalence_is_value_based(fen, alternative, alt_pv, status):
    played = ("e8e7", "e1f2") if fen == KNIGHT_PAWN else ("e8e7", "e1e2")
    result, _, _ = explain(fen, ("d1d5", alternative), {"d1d5": played, alternative: alt_pv})
    material = by_kind(result)[K.MATERIAL_THREAT]
    assert material.status is status
    assert material.subject == (base(Color.BLACK, PieceType.KNIGHT, "d5"),)


@pytest.mark.parametrize(
    "fen,first,pv",
    [
        (ROOK_TAKES, "d1d5", ("e8e7",)),  # unstable gain
        (START, "e2e4", ("e7e5", "g1f3")),  # zero
        (ROOK_HANGS, "c1c3", ("d5c3", "e1d2", "c3b5")),  # negative
    ],
)
def test_no_direct_material_candidate_without_stable_positive_gain(fen, first, pv):
    alternative = {"d1d5": "e1e2", "e2e4": "d2d4", "c1c3": "e1e2"}[first]
    result, _, _ = explain(fen, (first, alternative), {first: pv})
    assert K.MATERIAL_THREAT not in by_kind(result)


# ---- cause-specific material threat ----------------------------------------------------------

ATTACK_LINES = {
    "a1a5": (("h5f6", "e1e2"), EngineScore.cp(40)),
    "e1e2": ("h5f4", "e2e3"),
    "e1d2": ("h5f4", "d2e3"),
}


def test_direct_attack_resource_selects_q_and_proves_target_capture():
    result, calls, (_, context, p7, _) = explain(
        ATTACK,
        ("a1a5", "e1e2", "e1d2"),
        ATTACK_LINES,
        ignored={"a7a6": (("a7a6", "a5h5", "e8d7", "e1e2"), EngineScore.cp(300))},
    )
    assert calls == 1 and p7.calls[-1].probes[0].execution_move.uci == "a7a6"
    material = by_kind(result)[K.MATERIAL_THREAT]
    assert material.status is S.SUPPORTED
    assert material.tested_response.uci == "a7a6"
    assert material.subject == (base(Color.BLACK, PieceType.KNIGHT, "h5"),)
    assert [c.kind for c in material.tactical_candidates] == [TacticalCandidateKind.DIRECT_ATTACK]
    assert [m.material_delta for m in material.material_evidence] == [0, 0, 0, 320]
    assert material.material_evidence[-1].probe.kind is ProbeKind.IGNORE_THREAT
    assert len(material.probe_results) == 4
    assert material.probe_results[:3] == context.batch_a.results
    assert material.probe_results[-1].probe.kind is ProbeKind.IGNORE_THREAT


def test_material_selector_excludes_best_response():
    _, calls, (_, _, p7, _) = explain(
        ATTACK,
        ("a1a5", "e1e2", "e1d2"),
        {**ATTACK_LINES, "a1a5": (("a7a6", "e1e2"), EngineScore.cp(40))},
    )
    assert calls == 1 and p7.calls[-1].probes[0].execution_move.uci == "e8d7"


def test_batch_b_gaining_unrelated_material_does_not_prove_resource():
    result, calls, _ = explain(
        ATTACK,
        ("a1a5", "e1e2", "e1d2"),
        ATTACK_LINES,
        ignored={"a7a6": (("a7a6", "a5a6", "e8d7", "e1e2"), EngineScore.cp(300))},
    )
    assert calls == 1
    assert K.MATERIAL_THREAT not in by_kind(result) and result.benefits == ()


def test_resource_without_concrete_batch_b_consequence_is_not_supported():
    result, _, _ = explain(
        ATTACK,
        ("a1a5", "e1e2", "e1d2"),
        ATTACK_LINES,
        ignored={"a7a6": (("a7a6", "e1e2", "h5f6"), EngineScore.cp(500))},
    )
    assert result.benefits == () and result.status is GoodMoveExplanationStatus.INCONCLUSIVE


def test_moved_target_keeps_base_identity_and_remains_capturable():
    result, calls, _ = explain(
        ROOK_ATTACK,
        ("a1a5", "e1e2", "e1d2"),
        {"a1a5": (("h5a5", "e1d2"), CP0), "e1e2": ("h5h2", "e2e3"), "e1d2": ("h5h2", "d2e3")},
        ignored={"h5g5": (("h5g5", "a5g5", "e8d7", "e1e2"), EngineScore.cp(500))},
        attach="h5g5",
    )
    assert calls == 0
    material = by_kind(result)[K.MATERIAL_THREAT]
    assert material.subject == (base(Color.BLACK, PieceType.ROOK, "h5"),)
    assert material.tested_response.uci == "h5g5"
    assert material.status is S.SUPPORTED


def test_pre_attached_saving_q_is_not_material_evidence():
    # Only the knight is a mover target; moving it out of attack leaves nothing capturable.
    result, calls, _ = explain(
        ATTACK_SOLO,
        ("a1a5", "e1e2", "e1d2"),
        ATTACK_LINES,
        ignored={"h5g7": (("h5g7", "a5a7", "e8f8", "e1e2"), EngineScore.cp(300))},
        attach="h5g7",
    )
    assert calls == 0 and result.benefits == ()


def test_fork_target_already_attacked_before_m_still_counts_for_the_fork():
    # P6 reports the a7 pawn inside the rook's FORK, so a Q leaving it capturable qualifies.
    result, calls, _ = explain(
        ATTACK,
        ("a1a5", "e1e2", "e1d2"),
        ATTACK_LINES,
        ignored={"h5g7": (("h5g7", "a5a7", "e8f8", "e1e2"), EngineScore.cp(300))},
        attach="h5g7",
    )
    material = by_kind(result)[K.MATERIAL_THREAT]
    assert calls == 0
    assert [c.kind for c in material.tactical_candidates] == [TacticalCandidateKind.FORK]
    assert material.subject == (base(Color.BLACK, PieceType.PAWN, "a7"),)


def _replay_with_only(fen, moves, kind, lines=None):
    explainer, context, _, _ = scenario(fen, moves, lines)
    narrowed = _narrow_played(context, lambda d: tuple(c for c in d.candidates if c.kind is kind))
    return explainer, explainer.replay_lines(narrowed)


@pytest.mark.parametrize(
    "fen,move,kind,actors,targets,expected",
    [
        # best b6a6 is excluded; b6b1 gives check, so no target is legally capturable after it
        (FORK, "c3d5", TacticalCandidateKind.FORK, ("c3",), ("b6", "f6"), ("b6a6", "b6b2")),
        (
            DOUBLE,
            "d4b5",
            TacticalCandidateKind.DOUBLE_ATTACK,
            ("d1", "d4"),
            ("a7", "d7"),
            ("a7a1", "a7a2"),
        ),
    ],
)
def test_fork_and_double_attack_resources_select_cause_specific_q(
    fen, move, kind, actors, targets, expected
):
    explainer, replay = _replay_with_only(fen, (move, "e1e2"), kind)
    resources = material_resources(replay.played.line.plies[0], Color.WHITE)
    assert [r.candidate.kind for r in resources] == [kind]
    assert tuple(b.base_square for b in resources[0].actors) == actors
    assert tuple(b.base_square for b in resources[0].targets) == targets
    tested = explainer._select_tested_threat(replay, False, True)
    assert tested.kind is K.MATERIAL_THREAT and tested.resource.candidate.kind is kind
    assert (replay.played.line.plies[1].move.uci, tested.response.uci) == expected


def test_opponent_resources_are_skipped_and_order_is_deterministic():
    _, replay = _replay_with_only(DOUBLE, ("d4b5", "e1e2"), TacticalCandidateKind.DIRECT_ATTACK)
    resources = material_resources(replay.played.line.plies[0], Color.WHITE)
    assert [(r.actors[0].base_square, r.targets[0].base_square) for r in resources] == [
        ("d1", "d7"),
        ("d4", "a7"),
    ]
    assert all(r.actors[0].color is Color.WHITE for r in resources)


def test_king_targets_are_excluded_from_material_resources():
    _, replay = _replay_with_only(CASTLE_CHECK, ("e1c1", "e1f1"), TacticalCandidateKind.FORK)
    (resource,) = material_resources(replay.played.line.plies[0], Color.WHITE)
    assert resource.targets == (base(Color.BLACK, PieceType.KNIGHT, "f1"),)


@pytest.mark.parametrize("role", ["actors", "targets"])
def test_unmappable_resource_piece_fails_closed(role):
    explainer, context, _, _ = scenario(ATTACK, ("a1a5", "e1e2"), ATTACK_LINES)

    def corrupt(detection):
        ghost = PieceRef(Color.WHITE if role == "actors" else Color.BLACK, PieceType.BISHOP, "c4")
        return tuple(
            replace(c, **{role: (ghost,)}) if c.kind is TacticalCandidateKind.DIRECT_ATTACK else c
            for c in detection.candidates
        )

    with pytest.raises(IncompatibleGoodMoveContextError, match="base identity") as caught:
        explainer.explain_strong_move(_narrow_played(context, corrupt))
    assert caught.value.__cause__ is not None


def test_mover_resource_targeting_own_piece_fails_closed():
    explainer, context, _, _ = scenario(ATTACK, ("a1a5", "e1e2"), ATTACK_LINES)
    own = PieceRef(Color.WHITE, PieceType.KING, "e1")
    tampered = _narrow_played(
        context,
        lambda d: tuple(
            replace(c, targets=(*c.targets, own)) if c.kind is TacticalCandidateKind.FORK else c
            for c in d.candidates
        ),
    )
    with pytest.raises(IncompatibleGoodMoveContextError, match="own piece"):
        explainer.explain_strong_move(tampered)


# ---- one Batch-B budget ----------------------------------------------------------------------


def test_mate_q_has_priority_over_material_q():
    result, calls, (_, context, p7, _) = explain(
        BACK_RANK_KNIGHT,
        ("d2e3", "g1f1", "g1h1"),
        BACK_RANK_LINES,
        ignored={"a7b5": (("a7b5", "d1d8"), mate(Color.WHITE, 1))},
    )
    assert calls == 1 and len(p7.calls) == 2
    assert p7.calls[-1].probes[0].execution_move.uci == "a7b5"
    assert context.probe_count == 3
    assert by_kind(result)[K.MATE_THREAT].tested_response.uci == "a7b5"
    assert sum(len(c.probes) for c in p7.calls) == 4


def test_pre_attached_batch_b_never_adds_p7_calls():
    explainer, context, p7, engine = scenario(
        BACK_RANK, ("d2e3", "g1f1", "g1h1"), BACK_RANK_LINES, attach="f7f6"
    )
    calls = (len(p7.calls), len(engine.calls))
    explainer.counterfactual = Forbidden("P7")
    explainer.explain_strong_move(context)
    explainer.explain_strong_move(context)
    assert (len(p7.calls), len(engine.calls)) == calls == (2, 4)


def test_quiet_move_has_no_cause_specific_q_and_no_batch_b():
    result, calls, _ = explain(
        START,
        ("e2e4", "d2d4", "g1f3"),
        {"e2e4": (("e7e5", "g1f3"), EngineScore.cp(900))},
        quality=MoveQuality.BEST,
    )
    assert calls == 0
    assert result.status is GoodMoveExplanationStatus.INCONCLUSIVE and result.benefits == ()


def test_fifth_probe_is_rejected_before_p7(monkeypatch):
    explainer, context, p7, _ = scenario(BACK_RANK, ("d2e3", "g1f1", "g1h1"), BACK_RANK_LINES)
    monkeypatch.setattr(type(context), "probe_count", property(lambda self: 4))
    with pytest.raises(IncompatibleGoodMoveContextError, match="probe budget"):
        explainer.explain_strong_move(context)
    assert len(p7.calls) == 1


def test_operational_p7_error_during_auto_batch_b_propagates():
    explainer, context, _, _ = scenario(BACK_RANK, ("d2e3", "g1f1"), BACK_RANK_LINES)

    class Boom(Exception):
        pass

    def execute(request):
        raise Boom

    explainer.counterfactual = type("P7", (), {"execute": staticmethod(execute)})()
    with pytest.raises(Boom):
        explainer.explain_strong_move(context)


# ---- quiet / adversarial ---------------------------------------------------------------------


def test_raw_cp_superiority_alone_is_no_benefit():
    result, _, _ = explain(
        START,
        ("g1f3", "e2e4", "d2d4"),
        {
            "g1f3": (("g8f6", "g2g3"), EngineScore.cp(2000)),
            "e2e4": (("e7e5", "g1f3"), EngineScore.cp(-500)),
            "d2d4": (("d7d5", "c2c4"), EngineScore.cp(-500)),
        },
    )
    assert result.benefits == () and result.status is GoodMoveExplanationStatus.INCONCLUSIVE


def test_black_mover_symmetry():
    result, _, _ = explain(
        BLACK_TAKES,
        ("d8d5", "e8f8"),
        {"d8d5": ("e1e2", "e8e7"), "e8f8": ("d5c7", "d8d1")},
    )
    material = by_kind(result)[K.MATERIAL_THREAT]
    assert material.subject == (base(Color.WHITE, PieceType.KNIGHT, "d5"),)
    assert material.material_evidence[0].material_delta == 320
    assert material.status is S.SUPPORTED


def test_black_mover_mate_subject_is_white_king():
    mirrored = "5q2/8/8/8/8/6k1/8/7K b - - 0 1"
    result, _, _ = explain(mirrored, ("f8f1", "f8f2"), {"f8f2": ("h1g1",)})
    benefit = by_kind(result)[K.MATE_THREAT]
    assert benefit.subject == (base(Color.WHITE, PieceType.KING, "h1"),)
    assert benefit.mate_evidence_level is MateEvidenceLevel.EXACT_IMMEDIATE


def test_aggregate_status_rules():
    supported, _, _ = explain(QUEEN, ("f1f8", "f1f7"))
    assert supported.status is GoodMoveExplanationStatus.SUPPORTED
    refuted, _, _ = explain(QUEEN, ("f1f8", "f1a1"), {"f1a1": (("h8g8",), mate(Color.WHITE, 4))})
    assert {b.status for b in refuted.benefits} == {S.REFUTED}
    assert refuted.status is GoodMoveExplanationStatus.REFUTED
    inconclusive, _, _ = explain(
        TWO_KNIGHTS, ("d1d5", "d1a1"), {"d1d5": ("e8e7", "e1e2"), "d1a1": ("e8e7",)}
    )
    assert inconclusive.status is GoodMoveExplanationStatus.INCONCLUSIVE
    assert [b.status for b in inconclusive.benefits] == [S.INCONCLUSIVE]


def test_tested_threat_must_match_retained_ignored_response():
    explainer, context, _, _ = scenario(START, ("e2e4", "d2d4"))
    replay = explainer.replay_lines(context)
    tested = GoodMoveTestedThreat(K.MATE_THREAT, ChessMove("e7e5"))
    with pytest.raises(IncompatibleGoodMoveContextError, match="ignored response"):
        evaluate_strong_move(replay, tested)


def test_p3_judgement_and_basis_are_never_read():
    explainer, context, _, _ = scenario(
        BACK_RANK,
        ("d2e3", "g1f1", "g1h1"),
        BACK_RANK_LINES,
        ignored={"g8f8": (("g8f8", "d1d8"), mate(Color.WHITE, 1))},
    )
    d = context.deterministic
    prepared = replace(
        d.prepared, judgement=Forbidden("judgement"), position_analysis=Forbidden("basis")
    )
    guarded = replace(context, deterministic=replace(d, prepared=prepared))
    result = explainer.explain_strong_move(guarded)
    assert by_kind(result)[K.MATE_THREAT].status is S.SUPPORTED


def test_i5_source_boundary():
    module = ast.parse(inspect.getsource(good_move_benefits))
    methods = ast.parse(
        "\n".join(
            textwrap.dedent(inspect.getsource(m))
            for m in (
                GoodMoveExplainer.explain_strong_move,
                GoodMoveExplainer._select_tested_threat,
                GoodMoveExplainer._leaves_mate_in_one,
                GoodMoveExplainer._capturable_after,
            )
        )
    )
    for tree in (module, methods):
        attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not attributes & {
            "judgement",
            "position_analysis",
            "best_score",
            "played_score",
            "cp_loss",
            "expected_score_loss",
            "acceptable_move_count",
            "best_to_second_gap_cp",
            "wdl",
            "PREVENTS_MATE",
            "PREVENTS_MATERIAL_LOSS",
            "FORCED",
        }
        keywords = {n.arg for n in ast.walk(tree) if isinstance(n, ast.keyword)}
        assert "failed_alternatives" not in keywords
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "literal_only_move_proven":
                assert isinstance(node.value, ast.Constant) and node.value.value is False
    method_attributes = {n.attr for n in ast.walk(methods) if isinstance(n, ast.Attribute)}
    assert "score" not in method_attributes  # selectors never consult engine scores
    imported = {n.module for n in ast.walk(module) if isinstance(n, ast.ImportFrom)}
    assert not imported & {
        "calliope.services.explanation.bad_move",
        "calliope.services.explanation.bad_move_causes",
        "calliope.services.counterfactual",
    }
    assert good_move.evaluate_strong_move is evaluate_strong_move
