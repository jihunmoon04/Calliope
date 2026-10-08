"""P9-I7 adversarial / coverage gate over the complete good-move stack.

Real python-chess rules, real P4/P5/P6, real P7 CounterfactualAnalyzer and a scripted engine;
only returned or retained evidence is tampered with.  The stack must never overstate evidence.
"""

import ast
import inspect
import re
import textwrap
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import calliope
import calliope.engine as public_engine
import calliope.services.explanation.good_move as good_move_module
import calliope.services.explanation.good_move_benefits as benefits_module
import calliope.services.explanation.good_move_preservation as preservation_module
from calliope import contracts
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
)
from calliope.domain.chess import ChessMove, Color, PieceRef, PieceType
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
from calliope.errors import IncompatibleBadMoveContextError, IncompatibleGoodMoveContextError
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.explanation import GoodMoveExplainer
from calliope.services.explanation.good_move_benefits import evaluate_strong_move
from calliope.services.explanation.good_move_preservation import evaluate_only_move
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.tactics import TacticalDetector

rules = PythonChessAdapter()
SETTINGS = EngineSettings(EngineLimit(time_ms=47), multipv=1, threads=1, hash_mb=16)
IDENTITY = EngineIdentity("Scripted P7", "1")

K = GoodMoveBenefitKind
S = GoodMoveBenefitStatus
ES = GoodMoveExplanationStatus
TK = TacticalCandidateKind
CP0 = EngineScore.cp(0)
ONLY = Forcedness(ForcednessLevel.ONLY_MOVE)

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
QUEEN_MATES = "7k/8/6K1/8/8/8/8/5Q2 w - - 0 1"
ROOK_CHECK = "k7/8/2K5/8/8/8/8/1R6 w - - 0 1"
CASTLE_CHECK = "2rkr3/2p1p3/8/8/8/8/8/R3Kn2 w Q - 0 1"
CASTLE_ALIAS = "r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1"
BACK_RANK = "6k1/5ppp/8/8/8/8/3B4/3Q2K1 w - - 0 1"
BACK_RANK_KNIGHT = "6k1/n4ppp/8/8/8/8/3B4/3Q2K1 w - - 0 1"
ROOK_TAKES = "4k3/8/8/3n4/8/8/8/3RK3 w - - 0 1"
TWO_KNIGHTS = "4k3/8/8/3n4/8/8/8/n2RK3 w - - 0 1"
KNIGHT_QUEEN = "4k3/8/8/3n4/q7/8/2B5/3RK3 w - - 0 1"
KNIGHT_PAWN = "4k3/8/8/3n4/8/8/4p3/3RK3 w - - 0 1"
PROMOTE = "1n5k/P7/8/8/8/8/8/K7 w - - 0 1"
EN_PASSANT = "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2"
ATTACK = "4k3/p7/8/7n/8/8/8/R3K3 w - - 0 1"
ATTACK_SOLO = "4k3/8/8/7n/8/8/8/R3K3 w - - 0 1"
ATTACK_SWAP = "4k2r/8/8/7n/8/8/8/R3K3 w - - 0 1"
BLACK_TAKES = "3rk3/8/8/3N4/8/8/8/4K3 b - - 0 1"
# ONLY_MOVE preservation: Black's queen mates on the back rank if White's rook leaves it.
DEFEND = "6k1/5ppp/8/8/8/8/1q3PPP/3R2K1 w - - 0 1"
DEFEND_PAWN = "6k1/5ppp/8/3p4/8/8/1q3PPP/3R2K1 w - - 0 1"
DEFEND_QUEEN = "6k1/5ppp/8/8/8/8/Pq3PPP/3Q2K1 w - - 0 1"
DEFEND_BLACK = "3r2k1/1Q3ppp/8/8/8/8/5PPP/6K1 b - - 0 1"
PROMOTION_RACE = "6k1/8/8/8/8/8/p7/1R4K1 w - - 0 1"

SAFE = {"h2h3": ("f7f6", "g1h2"), "f2f3": ("f7f6", "g1h1"), "d1e1": ("f7f6", "h2h3")}
MATE_NOW = {"d1a1": ("b2a1",), "d1b1": ("b2b1",)}
ROOK_LOST = {"d1d2": ("b2d2", "h2h3", "g8f8"), "d1d4": ("b2d4", "h2h3", "g8f8")}
PAWN_LOST = {"g1h1": ("b2f2", "h2h3", "g8f8"), "h2h3": ("b2f2", "g1h2", "g8f8")}
BACK_RANK_LINES = {
    "d2e3": (("h7h6", "g1h2"), EngineScore.cp(60)),
    "g1f1": ("h7h6", "f1e2"),
    "g1h1": ("h7h6", "h1g1"),
}
ATTACK_LINES = {
    "a1a5": (("h5f6", "e1e2"), EngineScore.cp(40)),
    "e1e2": ("h5f4", "e2e3"),
    "e1d2": ("h5f4", "d2e3"),
}


def mate(color, moves):
    return EngineScore.forced_mate(color, moves)


class Forbidden:
    def __init__(self, label):
        self.label = label

    def __getattr__(self, name):
        raise AssertionError(f"P9 accessed forbidden {self.label}: {name}")


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
    """Delegate to real P7; optionally tamper the returned batch."""

    def __init__(self, engine):
        self.delegate = CounterfactualAnalyzer(rules, engine, rules, rules)
        self.calls = []
        self.transform = lambda batch: batch

    def execute(self, request):
        self.calls.append(request)
        return self.transform(self.delegate.execute(request))


class ReversedRules:
    def observe_tactics(self, position):
        observed = rules.observe_tactics(position)
        return replace(observed, legal_moves=observed.legal_moves[::-1])


class ReversedDetector:
    """Same P6 candidates, reported in reverse iteration order."""

    def __init__(self):
        self.inner = TacticalDetector()

    def detect(self, **kwargs):
        detection = self.inner.detect(**kwargs)
        return replace(detection, candidates=detection.candidates[::-1])


def _line(value):
    if isinstance(value[-1], EngineScore):
        return tuple(value[0]), value[1]
    return tuple(value), CP0


def judgement_for(base, played, quality, forcedness, rank=1, best=None):
    return MoveJudgement(
        base.position_id,
        base.side_to_move,
        ChessMove(played),
        ChessMove(best or played),
        quality,
        rank,
        EngineScore.cp(2500),
        EngineScore.cp(2500),
        0,
        0.0,
        forcedness,
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
    detector=None,
):
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
        rules,
        facts,
        BoardDeltaAnalyzer(rules, facts),
        tactical_rules,
        detector or TacticalDetector(),
        p7,
    )
    basis = tuple(
        EngineLine(
            i,
            ChessMove(u),
            EngineScore.cp(3000 - 1000 * i),
            (ChessMove(u),),
            wdl=WDL(1.0, 0.0, 0.0),
        )
        for i, u in enumerate(moves, start=1)
    )
    analysis = EngineAnalysis(
        base.position_id, EngineIdentity("P3"), EngineSettings(EngineLimit(depth=4)), basis
    )
    judgement = judgement_for(base, moves[0], quality, forcedness or Forcedness())
    prepared = explainer.prepare(base, judgement.move, judgement, analysis)
    context = explainer.verify_counterfactuals(explainer.build_branches(prepared), SETTINGS)
    if attach is not None:
        context = explainer.verify_ignored_response(context, ChessMove(attach))
    return explainer, context, p7, engine


def check_result(result, mode):
    assert isinstance(result, GoodMoveExplanationResult)
    assert result.mode is mode
    assert result.alternative_scope is AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES
    assert result.literal_only_move_proven is False
    assert (
        GoodMoveExplanationResult(**{f.name: getattr(result, f.name) for f in fields(result)})
        == result
    )
    kinds = [list(GoodMoveBenefitKind).index(b.kind) for b in result.benefits]
    assert kinds == sorted(kinds)
    allowed = (
        {K.FORCES_RESPONSE, K.MATE_THREAT, K.MATERIAL_THREAT}
        if mode is GoodMoveMode.STRONG_MOVE
        else {K.PREVENTS_MATE, K.PREVENTS_MATERIAL_LOSS}
    )
    for benefit in result.benefits:
        assert benefit.kind in allowed
        assert (
            GoodMoveBenefitResult(**{f.name: getattr(benefit, f.name) for f in fields(benefit)})
            == benefit
        )
        assert benefit.alternative_scope is AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES
        squares = [b.base_square for b in benefit.subject]
        assert list(benefit.subject) == sorted(
            benefit.subject, key=lambda b: (_square(b.base_square), b.color, b.piece_type)
        ), squares
        assert [a.rank for a in benefit.failed_alternatives] == sorted(
            a.rank for a in benefit.failed_alternatives
        )
        if mode is GoodMoveMode.STRONG_MOVE:
            assert benefit.failed_alternatives == ()
    return result


def _square(name):
    return (int(name[1]) - 1) * 8 + "abcdefgh".index(name[0])


def strong(*args, **kwargs):
    explainer, context, p7, engine = scenario(*args, **kwargs)
    before = len(p7.calls)
    result = check_result(explainer.explain_strong_move(context), GoodMoveMode.STRONG_MOVE)
    return result, len(p7.calls) - before, (explainer, context, p7, engine)


def only(*args, **kwargs):
    kwargs.setdefault("quality", MoveQuality.BEST)
    kwargs.setdefault("forcedness", ONLY)
    explainer, context, p7, engine = scenario(*args, **kwargs)
    calls = (len(p7.calls), len(engine.calls))
    result = check_result(explainer.explain_only_move(context), GoodMoveMode.ONLY_MOVE_CANDIDATE)
    assert (len(p7.calls), len(engine.calls)) == calls
    return result, context


def by_kind(result):
    found = {b.kind: b for b in result.benefits}
    assert len(found) == len(result.benefits)
    return found


def ucis(alternatives):
    return tuple(a.move.uci for a in alternatives)


def base(color, kind, square):
    return BasePieceRef(color, kind, square)


def narrow_played(context, transform):
    d = context.deterministic
    detection = d.played.detection
    played = replace(d.played, detection=replace(detection, candidates=transform(detection)))
    return replace(context, deterministic=replace(d, played=played))


def with_ghost_attack(context, role="actors"):
    ghost = PieceRef(Color.WHITE if role == "actors" else Color.BLACK, PieceType.BISHOP, "c4")
    actor = PieceRef(Color.WHITE, PieceType.ROOK, "a8")
    target = PieceRef(Color.BLACK, PieceType.KNIGHT, "h8")
    malformed = SimpleNamespace(
        kind=TK.DIRECT_ATTACK,
        actors=(ghost,) if role == "actors" else (actor,),
        targets=(ghost,) if role == "targets" else (target,),
    )
    return narrow_played(context, lambda d: (*d.candidates, malformed))


# ---- A1/A2 representative-only forcedness ----------------------------------------------------


def test_a1_only_move_hint_without_concrete_failure_is_not_evidence():
    result, context = only(DEFEND, ("h2h3", "f2f3", "d1e1"), SAFE)
    assert context.deterministic.prepared.mode is GoodMoveMode.ONLY_MOVE_CANDIDATE
    assert result.status is ES.INCONCLUSIVE and result.benefits == ()
    assert result.literal_only_move_proven is False


def test_a2_every_representative_alternative_failing_is_still_not_exhaustive():
    result, _ = only(DEFEND, ("h2h3", "d1a1", "d1b1"), {**SAFE, **MATE_NOW})
    assert result.status is ES.SUPPORTED
    for benefit in result.benefits:
        assert benefit.failed_alternatives == result.alternatives
        assert benefit.alternative_scope is AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES
    assert result.literal_only_move_proven is False
    field_names = {f.name for f in fields(GoodMoveExplanationResult)} | {
        f.name for f in fields(GoodMoveBenefitResult)
    }
    assert not {n for n in field_names if re.search("exhaust|unique|all_legal|only_move", n)} - {
        "literal_only_move_proven"
    }


# ---- A3/A4 equivalent benefits ----------------------------------------------------------------


def test_a3_equivalent_forcing_alternative_refutes():
    result, _, _ = strong(
        ROOK_CHECK,
        ("b1a1", "c6b6"),
        {
            "b1a1": (("a8b8", "c6b6"), EngineScore.cp(800)),
            "c6b6": (("a8b8", "b1h1"), EngineScore.cp(800)),
        },
    )
    forces = by_kind(result)[K.FORCES_RESPONSE]
    assert forces.status is S.REFUTED and forces.equivalent_alternative_benefit is True


def test_a3_equivalent_mating_alternative_refutes():
    result, _, _ = strong(
        QUEEN_MATES, ("f1f8", "f1a1"), {"f1a1": (("h8g8",), mate(Color.WHITE, 2))}
    )
    benefit = by_kind(result)[K.MATE_THREAT]
    assert benefit.status is S.REFUTED and benefit.equivalent_alternative_benefit is True
    assert result.status is ES.REFUTED


def test_a3_equivalent_material_alternative_refutes():
    result, _, _ = strong(
        TWO_KNIGHTS, ("d1d5", "d1a1"), {"d1d5": ("e8e7", "e1e2"), "d1a1": ("e8e7", "e1e2")}
    )
    benefit = by_kind(result)[K.MATERIAL_THREAT]
    assert benefit.status is S.REFUTED and benefit.equivalent_alternative_benefit is True


@pytest.mark.parametrize("played_mate,alternative_mate", [(1, 9), (9, 1), (3, 3)])
def test_a4_mate_distance_never_rescues_uniqueness(played_mate, alternative_mate):
    result, _, _ = strong(
        QUEEN_MATES,
        ("f1a1", "f1h1"),
        {
            "f1a1": (("h8g8",), mate(Color.WHITE, played_mate)),
            "f1h1": (("h8g8",), mate(Color.WHITE, alternative_mate)),
        },
    )
    assert by_kind(result)[K.MATE_THREAT].status is S.REFUTED


# ---- A5/A6 quiet moves and score temptation --------------------------------------------------


@pytest.mark.parametrize("quality", [MoveQuality.BEST, MoveQuality.EXCELLENT, MoveQuality.GOOD])
def test_a5_quiet_positional_move_has_no_benefit(quality):
    result, calls, _ = strong(
        START,
        ("g1f3", "e2e4", "d2d4"),
        {
            "g1f3": (("g8f6", "g2g3"), EngineScore.cp(900)),
            "e2e4": (("e7e5", "g1f3"), EngineScore.cp(-900)),
            "d2d4": (("d7d5", "c2c4"), EngineScore.cp(-900)),
        },
        quality=quality,
    )
    assert result.status is ES.INCONCLUSIVE and result.benefits == () and calls == 0


def test_a6_p3_numbers_cannot_create_or_change_benefits():
    lines = {
        "g1f3": (("g8f6", "g2g3"), EngineScore.cp(5000)),
        "e2e4": (("e7e5", "g1f3"), mate(Color.BLACK, 1)),
    }
    explainer, context, _, _ = scenario(START, ("g1f3", "e2e4"), lines, quality=MoveQuality.BEST)
    d = context.deterministic
    guarded_prepared = replace(
        d.prepared, judgement=Forbidden("judgement"), position_analysis=Forbidden("basis")
    )
    guarded = replace(context, deterministic=replace(d, prepared=guarded_prepared))
    result = check_result(explainer.explain_strong_move(guarded), GoodMoveMode.STRONG_MOVE)
    assert result.benefits == ()


def test_a6_p3_numbers_never_read_in_either_mode(monkeypatch):
    def forbidden(self):
        raise AssertionError("P9 policy read a P3 number")

    cases = (
        (strong, (BACK_RANK, ("d2e3", "g1f1", "g1h1"), BACK_RANK_LINES), {}),
        (only, (DEFEND, ("h2h3", "d1a1", "d1d2"), {**SAFE, **MATE_NOW, **ROOK_LOST}), {}),
    )
    for run, args, kwargs in cases:
        explainer, context, _, _ = scenario(
            *args,
            **(
                {"quality": MoveQuality.BEST, "forcedness": ONLY}
                if run is only
                else {
                    "ignored": {"g8f8": (("g8f8", "d1d8"), mate(Color.WHITE, 1))},
                    "attach": "g8f8",
                }
            ),
        )
        with monkeypatch.context() as patch:
            for cls, names in (
                (MoveJudgement, ("best_score", "played_score", "cp_loss", "expected_score_loss")),
                (Forcedness, ("acceptable_move_count", "best_to_second_gap_cp")),
                (EngineLine, ("wdl", "depth", "seldepth", "nodes")),
            ):
                for name in names:
                    patch.setattr(cls, name, property(forbidden))
            method = explainer.explain_only_move if run is only else explainer.explain_strong_move
            assert method(context).status is ES.SUPPORTED


# ---- A7 absence vs incomplete evidence -------------------------------------------------------


def test_a7_truncated_alternative_is_incomplete_not_absent():
    truncated, _, _ = strong(
        TWO_KNIGHTS, ("d1d5", "d1a1"), {"d1d5": ("e8e7", "e1e2"), "d1a1": ("e8e7",)}
    )
    benefit = by_kind(truncated)[K.MATERIAL_THREAT]
    assert benefit.status is S.INCONCLUSIVE and benefit.equivalent_alternative_benefit is None
    assert truncated.status is ES.INCONCLUSIVE
    absent, _, _ = strong(
        TWO_KNIGHTS, ("d1d5", "e1e2"), {"d1d5": ("e8e7", "e1e2"), "e1e2": ("a1c2", "e2f3")}
    )
    benefit = by_kind(absent)[K.MATERIAL_THREAT]
    assert benefit.status is S.SUPPORTED and benefit.equivalent_alternative_benefit is False


def test_a7_truncated_preservation_comparator_is_incomplete():
    result, _ = only(DEFEND, ("h2h3", "d1d2"), {**ROOK_LOST, "h2h3": ("f7f6",)})
    benefit = by_kind(result)[K.PREVENTS_MATERIAL_LOSS]
    assert benefit.status is S.INCONCLUSIVE and benefit.failed_alternatives == ()


# ---- A8 canonical duplicates -----------------------------------------------------------------


def test_a8_castling_aliases_fail_before_any_p7_or_engine_call():
    base_position = rules.position_from_fen(CASTLE_ALIAS)
    engine = ScriptedEngine({})
    p7 = RecordingP7(engine)
    facts = PositionFactExtractor(rules)
    explainer = GoodMoveExplainer(
        rules, facts, BoardDeltaAnalyzer(rules, facts), rules, TacticalDetector(), p7
    )
    lines = tuple(
        EngineLine(i, ChessMove(u), CP0, (ChessMove(u),))
        for i, u in enumerate(("e1g1", "e1h1", "a2a3"), start=1)
    )
    analysis = EngineAnalysis(base_position.position_id, IDENTITY, SETTINGS, lines)
    judgement = judgement_for(base_position, "e1g1", MoveQuality.BEST, ONLY)
    with pytest.raises(IncompatibleGoodMoveContextError, match="duplicate"):
        explainer.prepare(base_position, ChessMove("e1g1"), judgement, analysis)
    assert (len(p7.calls), len(engine.calls)) == (0, 0)


# ---- A9/A10 identity -------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["actors", "targets"])
@pytest.mark.parametrize(
    "case",
    ["mate-q-priority", "direct-material", "pre-attached-b", "pure-policy"],
)
def test_a9_unmappable_resource_fails_closed_whatever_the_earlier_gate(case, role):
    if case == "mate-q-priority":
        explainer, context, p7, _ = scenario(BACK_RANK_KNIGHT, ("d2e3", "g1f1"), BACK_RANK_LINES)
    elif case == "direct-material":
        explainer, context, p7, _ = scenario(
            ROOK_TAKES, ("d1d5", "e1e2"), {"d1d5": ("e8e7", "e1e2"), "e1e2": ("d5c3", "e2e3")}
        )
    else:
        explainer, context, p7, _ = scenario(
            BACK_RANK, ("d2e3", "g1f1"), BACK_RANK_LINES, attach="f7f6"
        )
    tampered = with_ghost_attack(context, role)
    calls = len(p7.calls)
    with pytest.raises(IncompatibleGoodMoveContextError) as caught:
        if case == "pure-policy":
            evaluate_strong_move(explainer.replay_lines(tampered))
        else:
            explainer.explain_strong_move(tampered)
    assert isinstance(caught.value.__cause__, IncompatibleBadMoveContextError)
    assert len(p7.calls) == calls


def test_a10_capture_on_the_target_square_of_another_physical_piece_is_not_the_target():
    # The rook h8 later stands on h5 and is captured there; the resource target was knight h5.
    lines = {
        "a1a5": (("h5f6", "e1e2"), EngineScore.cp(40)),
        "e1e2": ("h5f4", "e2e3"),
        "e1d2": ("h5f4", "d2e3"),
    }
    pv = ("e8d7", "e1e2", "h5f6", "e2e3", "h8h5", "a5h5", "d7e6", "e3d3")
    result, calls, _ = strong(
        ATTACK_SWAP,
        ("a1a5", "e1e2", "e1d2"),
        lines,
        ignored={"e8d7": (pv, EngineScore.cp(500))},
        attach="e8d7",
    )
    assert calls == 0
    assert K.MATERIAL_THREAT not in by_kind(result)


def test_a10_promoted_queen_is_never_a_new_base_identity():
    result, _, _ = strong(
        PROMOTE,
        ("a7b8q", "a1b1", "a1a2"),
        {"a7b8q": ("h8h7", "a1b1"), "a1b1": ("h8g7", "b1c2"), "a1a2": ("h8g7", "a2b3")},
    )
    subject = by_kind(result)[K.MATERIAL_THREAT].subject
    assert subject == (
        base(Color.WHITE, PieceType.PAWN, "a7"),
        base(Color.BLACK, PieceType.KNIGHT, "b8"),
    )
    assert all(b.piece_type is not PieceType.QUEEN for b in subject)


# ---- A11 value-based material equivalence ----------------------------------------------------


@pytest.mark.parametrize(
    "fen,alternative,status",
    [
        (TWO_KNIGHTS, "d1a1", S.REFUTED),
        (KNIGHT_QUEEN, "c2a4", S.REFUTED),
        (KNIGHT_PAWN, "e1e2", S.SUPPORTED),
    ],
    ids=["equal-other-piece", "greater", "smaller"],
)
def test_a11_material_equivalence_is_value_based(fen, alternative, status):
    played = ("e8e7", "e1f2") if fen == KNIGHT_PAWN else ("e8e7", "e1e2")
    alt_pv = ("d5c3", "e2e3") if fen == KNIGHT_PAWN else ("e8e7", "e1e2")
    result, _, _ = strong(fen, ("d1d5", alternative), {"d1d5": played, alternative: alt_pv})
    benefit = by_kind(result)[K.MATERIAL_THREAT]
    assert benefit.status is status
    assert benefit.equivalent_alternative_benefit is (status is S.REFUTED)
    assert benefit.subject == (base(Color.BLACK, PieceType.KNIGHT, "d5"),)


# ---- A12/A13/A14 ignored responses -----------------------------------------------------------


def test_a12_pre_attached_losing_q_is_not_a_mate_threat():
    result, calls, _ = strong(
        BACK_RANK,
        ("d2e3", "g1f1", "g1h1"),
        BACK_RANK_LINES,
        ignored={"f7f6": (("f7f6", "d1d8", "g8f7"), mate(Color.WHITE, 2))},
        attach="f7f6",
    )
    assert calls == 0 and result.benefits == ()


def test_a12_pre_attached_saving_q_is_not_a_material_threat():
    result, calls, _ = strong(
        ATTACK_SOLO,
        ("a1a5", "e1e2", "e1d2"),
        ATTACK_LINES,
        ignored={"h5g7": (("h5g7", "a5a7", "e8f8", "e1e2"), EngineScore.cp(900))},
        attach="h5g7",
    )
    assert calls == 0 and result.benefits == ()


def test_a12_automatic_selector_never_probes_arbitrary_losing_q():
    explainer, context, p7, engine = scenario(
        START,
        ("e2e4", "d2d4"),
        {"e2e4": (("e7e5", "g1f3"), EngineScore.cp(50))},
        ignored={"f7f6": (("f7f6", "d1h5"), mate(Color.WHITE, 2))},
    )
    result = check_result(explainer.explain_strong_move(context), GoodMoveMode.STRONG_MOVE)
    assert len(p7.calls) == 1 and len(engine.calls) == 2
    assert result.benefits == ()


def test_a13_unrelated_batch_b_gain_does_not_prove_the_resource():
    result, calls, _ = strong(
        ATTACK,
        ("a1a5", "e1e2", "e1d2"),
        ATTACK_LINES,
        ignored={"a7a6": (("a7a6", "e1e2", "h5f6", "a5a6", "e8d7", "e2e3"), EngineScore.cp(300))},
    )
    assert calls == 1
    assert K.MATERIAL_THREAT not in by_kind(result)


def test_a14_best_response_is_skipped_for_the_next_cause_specific_q():
    _, calls, (_, _, p7, _) = strong(
        BACK_RANK,
        ("d2e3", "g1f1", "g1h1"),
        {**BACK_RANK_LINES, "d2e3": (("g8f8", "g1h2"), EngineScore.cp(60))},
        ignored={"g8h8": (("g8h8", "d1d8"), mate(Color.WHITE, 1))},
    )
    assert calls == 1 and p7.calls[-1].probes[0].execution_move.uci == "g8h8"


def test_a14_when_only_the_best_response_qualifies_no_batch_b_is_run():
    # After Bb4 only Kh8 leaves an exact mate-in-one; Batch A already plays it.
    result, calls, _ = strong(
        BACK_RANK,
        ("d2b4", "g1f1"),
        {"d2b4": (("g8h8", "g1h2"), EngineScore.cp(60)), "g1f1": ("h7h6", "f1e2")},
    )
    assert calls == 0 and result.benefits == ()


# ---- A15/A16/A17 P7 compatibility, identity and budget ---------------------------------------


def _view(value, **changes):
    values = {f.name: getattr(value, f.name) for f in fields(value)}
    values.update(changes)
    return SimpleNamespace(**values)


def _analysis_view(analysis, **changes):
    view = _view(analysis, **changes)
    view.best_line = next((line for line in view.lines if line.rank == 1), view.lines[0])
    return view


def _tamper_a(change):
    def apply(context):
        results = list(context.batch_a.results)
        results[1] = change(results[1], context)
        batch = replace(context.batch_a, results=tuple(results))
        refutations = tuple(
            replace(r, result=batch.results[i + 1])
            for i, r in enumerate(context.alternative_refutations)
        )
        return replace(context, batch_a=batch, alternative_refutations=refutations)

    return apply


A15_TAMPERS = {
    "settings": lambda c: replace(
        c, batch_a=replace(c.batch_a, settings=EngineSettings(EngineLimit(depth=2)))
    ),
    "probe-echo": _tamper_a(
        lambda r, c: replace(r, probe=replace(r.probe, intervention_move=ChessMove("g1h1")))
    ),
    "result-order": lambda c: replace(
        c,
        batch_a=replace(c.batch_a, results=c.batch_a.results[::-1]),
        played_refutation=c.batch_a.results[-1],
    ),
    "analysis-position": _tamper_a(
        lambda r, c: _view(r, analysis_position=c.deterministic.prepared.base)
    ),
    "intervention-position": _tamper_a(
        lambda r, c: _view(r, intervention_position=c.deterministic.prepared.base)
    ),
    "root-moves": _tamper_a(lambda r, c: _view(r, root_moves=(ChessMove("h7h6"),))),
    "engine-position": _tamper_a(
        lambda r, c: _view(
            r, engine_analysis=_analysis_view(r.engine_analysis, position_id="elsewhere")
        )
    ),
    "rank": _tamper_a(
        lambda r, c: _view(
            r,
            engine_analysis=_analysis_view(
                r.engine_analysis, lines=(replace(r.engine_analysis.lines[0], rank=2),)
            ),
        )
    ),
    "line-count": _tamper_a(
        lambda r, c: _view(
            r,
            engine_analysis=_analysis_view(
                r.engine_analysis,
                lines=(
                    r.engine_analysis.lines[0],
                    replace(r.engine_analysis.lines[0], rank=2),
                ),
            ),
        )
    ),
}


@pytest.mark.parametrize("name", sorted(A15_TAMPERS))
@pytest.mark.parametrize("mode", ["strong", "only"])
def test_a15_tampered_batch_a_fails_closed_through_explanation(name, mode):
    kwargs = {"quality": MoveQuality.BEST, "forcedness": ONLY} if mode == "only" else {}
    explainer, context, _p7, _ = scenario(
        BACK_RANK, ("d2e3", "g1f1", "g1h1"), BACK_RANK_LINES, **kwargs
    )
    tampered = A15_TAMPERS[name](context)
    explainer.counterfactual = Forbidden("P7")
    method = explainer.explain_only_move if mode == "only" else explainer.explain_strong_move
    with pytest.raises(IncompatibleGoodMoveContextError):
        method(tampered)


@pytest.mark.parametrize("mode", ["strong", "only"])
def test_a16_cross_batch_engine_identity_fails_before_benefits(mode):
    kwargs = {"quality": MoveQuality.BEST, "forcedness": ONLY} if mode == "only" else {}
    explainer, context, _, _ = scenario(
        BACK_RANK,
        ("d2e3", "g1f1"),
        BACK_RANK_LINES,
        attach="g8h8",
        ignored={"g8h8": (("g8h8", "d1d8"), mate(Color.WHITE, 1))},
        **kwargs,
    )
    result = context.ignored_response_result
    other = replace(
        result, engine_analysis=replace(result.engine_analysis, engine=EngineIdentity("Other"))
    )
    tampered = replace(
        context, batch_b=replace(context.batch_b, results=(other,)), ignored_response_result=other
    )
    explainer.counterfactual = Forbidden("P7")
    method = explainer.explain_only_move if mode == "only" else explainer.explain_strong_move
    with pytest.raises(IncompatibleGoodMoveContextError, match="engine identity"):
        method(tampered)


def test_a17_two_alternatives_and_one_batch_b_is_exactly_four_probes():
    _, calls, (_explainer, _context, p7, engine) = strong(
        BACK_RANK,
        ("d2e3", "g1f1", "g1h1"),
        BACK_RANK_LINES,
        ignored={"g8f8": (("g8f8", "d1d8"), mate(Color.WHITE, 1))},
    )
    assert calls == 1 and len(p7.calls) == 2
    assert sum(len(request.probes) for request in p7.calls) == len(engine.calls) == 4


def test_a17_no_route_reaches_a_fifth_probe(monkeypatch):
    # Attached Batch B: a second explanation and a second Batch B never reach P7.
    explainer, context, p7, _ = scenario(
        BACK_RANK, ("d2e3", "g1f1", "g1h1"), BACK_RANK_LINES, attach="g8h8"
    )
    assert context.probe_count == 4 and len(p7.calls) == 2
    explainer.counterfactual = Forbidden("P7")
    explainer.explain_strong_move(context)
    with pytest.raises(IncompatibleGoodMoveContextError):
        explainer.verify_ignored_response(context, ChessMove("g8f8"))
    assert len(p7.calls) == 2
    # A forged fifth retained probe is rejected during revalidation.
    forged = replace(context, batch_b=replace(context.batch_b, results=context.batch_b.results * 2))
    with pytest.raises(IncompatibleGoodMoveContextError, match="four probes"):
        explainer.explain_strong_move(forged)
    # A context claiming a full budget never starts an automatic Batch B.
    explainer, fresh, _p7, _ = scenario(BACK_RANK, ("d2e3", "g1f1", "g1h1"), BACK_RANK_LINES)
    monkeypatch.setattr(type(fresh), "probe_count", property(lambda self: 4))
    explainer.counterfactual = Forbidden("P7")
    with pytest.raises(IncompatibleGoodMoveContextError, match="probe budget"):
        explainer.explain_strong_move(fresh)


# ---- A18/A19/A20 Batch-B discipline -----------------------------------------------------------


def test_a18_direct_mate_prevents_unnecessary_batch_b():
    result, calls, _ = strong(
        BACK_RANK,
        ("d2e3", "g1f1", "g1h1"),
        {**BACK_RANK_LINES, "d2e3": (("g8h8", "d1d8"), mate(Color.WHITE, 1))},
        ignored={"g8f8": (("g8f8", "d1d8"), mate(Color.WHITE, 1))},
    )
    assert calls == 0
    benefit = by_kind(result)[K.MATE_THREAT]
    assert benefit.status is S.SUPPORTED and benefit.tested_response is None


def test_a18_direct_material_prevents_unnecessary_batch_b():
    result, calls, _ = strong(
        ATTACK,
        ("a1a5", "e1e2", "e1d2"),
        {**ATTACK_LINES, "a1a5": (("e8d7", "a5h5", "d7e6", "e1e2"), EngineScore.cp(300))},
    )
    assert calls == 0
    benefit = by_kind(result)[K.MATERIAL_THREAT]
    assert benefit.status is S.SUPPORTED and benefit.tested_response is None
    assert benefit.subject == (base(Color.BLACK, PieceType.KNIGHT, "h5"),)


def test_a19_mate_q_wins_and_only_one_batch_b_runs():
    result, calls, (_, _, p7, engine) = strong(
        BACK_RANK_KNIGHT,
        ("d2e3", "g1f1", "g1h1"),
        BACK_RANK_LINES,
        ignored={"a7b5": (("a7b5", "d1d8"), mate(Color.WHITE, 1))},
    )
    assert calls == 1 and len(engine.calls) == 4
    assert p7.calls[-1].probes[0].execution_move.uci == "a7b5"
    assert by_kind(result)[K.MATE_THREAT].tested_response.uci == "a7b5"
    assert K.MATERIAL_THREAT not in by_kind(result)


def test_a20_strong_pre_attached_q_counts_only_if_cause_specific():
    ignored = {
        "g8h8": (("g8h8", "d1d8"), mate(Color.WHITE, 1)),
        "f7f6": (("f7f6", "d1d8", "g8f7"), mate(Color.WHITE, 2)),
    }
    specific, _, _ = strong(
        BACK_RANK, ("d2e3", "g1f1"), BACK_RANK_LINES, ignored=ignored, attach="g8h8"
    )
    arbitrary, _, _ = strong(
        BACK_RANK, ("d2e3", "g1f1"), BACK_RANK_LINES, ignored=ignored, attach="f7f6"
    )
    assert by_kind(specific)[K.MATE_THREAT].tested_response.uci == "g8h8"
    assert arbitrary.benefits == ()


def test_a20_only_move_ignores_any_pre_attached_batch_b():
    lines = {**SAFE, **MATE_NOW, **ROOK_LOST}
    ignored = {"b2b1": (("b2b1", "d1b1", "g8f8", "b1b8"), mate(Color.BLACK, 1))}
    plain, _ = only(DEFEND, ("h2h3", "d1a1", "d1d2"), lines)
    attached, context = only(
        DEFEND, ("h2h3", "d1a1", "d1d2"), lines, ignored=ignored, attach="b2b1"
    )
    assert context.probe_count == 4
    assert attached == plain
    assert all(context.ignored_response_result not in b.probe_results for b in attached.benefits)


# ---- A21/A22 ONLY_MOVE mate evidence ---------------------------------------------------------


@pytest.mark.parametrize(
    "alternative,failure,level,exact",
    [
        ("d1a1", ("b2a1",), MateEvidenceLevel.EXACT_IMMEDIATE, True),  # ply 2 exact mate
        ("d1d7", ("b2b1", "d7d1", "b1d1"), MateEvidenceLevel.ENGINE_LINE, True),  # ply 4
        ("d1d7", (("b2b1", "d7d1"), mate(Color.BLACK, 2)), MateEvidenceLevel.ENGINE_LINE, False),
    ],
    ids=["ply2-exact", "later-exact", "engine-only"],
)
def test_a21_immediate_means_the_opponents_ply_two_reply(alternative, failure, level, exact):
    result, _ = only(DEFEND, ("h2h3", alternative), {**SAFE, alternative: failure})
    benefit = by_kind(result)[K.PREVENTS_MATE]
    assert benefit.status is S.SUPPORTED
    assert (benefit.mate_evidence_level, benefit.replayed_pv_ends_in_checkmate) == (level, exact)


def test_a22_mixed_mate_evidence_is_never_upgraded():
    result, _ = only(
        DEFEND,
        ("h2h3", "d1a1", "f2f3"),
        {**SAFE, **MATE_NOW, "f2f3": (("b2b1", "d1b1"), mate(Color.BLACK, 4))},
    )
    benefit = by_kind(result)[K.PREVENTS_MATE]
    assert ucis(benefit.failed_alternatives) == ("d1a1", "f2f3")
    assert benefit.mate_evidence_level is MateEvidenceLevel.ENGINE_LINE
    assert benefit.replayed_pv_ends_in_checkmate is False


# ---- A23..A27 relative preservation and event orientation ------------------------------------


def test_a23_preservation_is_relative_not_zero_loss():
    lines = {
        "h2h3": ("b2a2", "g1h2", "g8f8"),  # -100
        "d1d2": ("b2d2", "h2h3", "g8f8"),  # queen lost: -900
    }
    result, _ = only(DEFEND_QUEEN, ("h2h3", "d1d2"), lines)
    benefit = by_kind(result)[K.PREVENTS_MATERIAL_LOSS]
    assert [m.material_delta for m in benefit.material_evidence] == [-100, -900]
    assert benefit.status is S.SUPPORTED and ucis(benefit.failed_alternatives) == ("d1d2",)


@pytest.mark.parametrize(
    "fen,played,alternative,lines,status,failed",
    [
        (
            DEFEND_PAWN,
            "d1d5",
            "d1d2",
            {"d1d5": ("f7f6", "h2h3"), **ROOK_LOST},
            S.SUPPORTED,
            ("d1d2",),
        ),
        (DEFEND, "d1d2", "d1d4", ROOK_LOST, S.REFUTED, ()),
        (DEFEND, "d1d2", "g1h1", {**ROOK_LOST, **PAWN_LOST}, S.REFUTED, ()),
    ],
    ids=["M+100", "M-500-A-500", "M-500-A-100"],
)
def test_a23_relative_deficit_matrix(fen, played, alternative, lines, status, failed):
    result, _ = only(fen, (played, alternative), lines)
    benefit = by_kind(result)[K.PREVENTS_MATERIAL_LOSS]
    assert benefit.status is status and ucis(benefit.failed_alternatives) == failed


def test_a23_played_gain_counts_as_zero_deficit_not_negative():
    # Without the max(0, .) clamp the safe alternative h2h3 would also count as a failure.
    lines = {"d1d5": ("f7f6", "h2h3"), **ROOK_LOST, **SAFE}
    result, _ = only(DEFEND_PAWN, ("d1d5", "d1d2", "h2h3"), lines)
    benefit = by_kind(result)[K.PREVENTS_MATERIAL_LOSS]
    assert [m.material_delta for m in benefit.material_evidence] == [100, -500, 0]
    assert ucis(benefit.failed_alternatives) == ("d1d2",)
    assert benefit.equivalent_alternative_benefit is True


def test_a24_incomplete_preservation_comparator_keeps_proven_failures():
    result, _ = only(DEFEND, ("h2h3", "d1d2", "f2f3"), {**SAFE, **ROOK_LOST, "f2f3": ("f7f6",)})
    benefit = by_kind(result)[K.PREVENTS_MATERIAL_LOSS]
    assert benefit.status is S.INCONCLUSIVE
    assert ucis(benefit.failed_alternatives) == ("d1d2",)
    assert benefit.equivalent_alternative_benefit is None


@pytest.mark.parametrize(
    "lines,kind",
    [
        ({**SAFE, **MATE_NOW}, K.PREVENTS_MATE),
        ({**SAFE, **ROOK_LOST}, K.PREVENTS_MATERIAL_LOSS),
    ],
)
def test_a25_safe_equivalent_alternative_does_not_refute_preservation(lines, kind):
    failing = "d1a1" if kind is K.PREVENTS_MATE else "d1d2"
    result, _ = only(DEFEND, ("h2h3", failing, "f2f3"), lines)
    benefit = by_kind(result)[kind]
    assert benefit.status is S.SUPPORTED
    assert ucis(benefit.failed_alternatives) == (failing,)
    assert benefit.equivalent_alternative_benefit is True


def test_a26_positive_events_inside_a_failed_line_are_not_loss_subjects():
    result, _ = only(DEFEND_PAWN, ("h2h3", "d1d5"), {**SAFE, "d1d5": ("b2b1", "d5d1", "b1d1")})
    benefit = by_kind(result)[K.PREVENTS_MATERIAL_LOSS]
    assert benefit.subject == (base(Color.WHITE, PieceType.ROOK, "d1"),)


def test_a27_promotion_orientation_by_mode():
    strong_result, _, _ = strong(
        PROMOTE,
        ("a7a8q", "a1b1", "a1a2"),
        {"a7a8q": ("h8g7", "a1b1"), "a1b1": ("h8g7", "b1c2"), "a1a2": ("h8g7", "a2b3")},
    )
    assert by_kind(strong_result)[K.MATERIAL_THREAT].subject == (
        base(Color.WHITE, PieceType.PAWN, "a7"),
    )
    only_result, _ = only(
        PROMOTION_RACE,
        ("b1a1", "b1b8"),
        {
            "b1a1": ("g8f7", "g1f2", "f7e6"),
            "b1b8": ("g8h7", "g1f2", "a2a1q", "b8b7", "h7g6"),
        },
    )
    benefit = by_kind(only_result)[K.PREVENTS_MATERIAL_LOSS]
    assert benefit.subject == (base(Color.BLACK, PieceType.PAWN, "a2"),)
    assert [m.material_delta for m in benefit.material_evidence] == [0, -800]


# ---- A28 special moves -----------------------------------------------------------------------


def test_a28_castling_forcing_subject_is_king_and_rook():
    result, _, _ = strong(CASTLE_CHECK, ("e1c1", "e1f1", "a1a2"), {"e1c1": ("f1d2", "d1d2")})
    assert by_kind(result)[K.FORCES_RESPONSE].subject == (
        base(Color.WHITE, PieceType.ROOK, "a1"),
        base(Color.WHITE, PieceType.KING, "e1"),
    )


def test_a28_en_passant_subject_is_the_pawn_from_its_real_square():
    result, _, _ = strong(
        EN_PASSANT, ("e5d6", "e1e2"), {"e5d6": ("e8f7", "e1e2"), "e1e2": ("e8d7", "e2e3")}
    )
    benefit = by_kind(result)[K.MATERIAL_THREAT]
    assert benefit.subject == (base(Color.BLACK, PieceType.PAWN, "d5"),)
    assert benefit.board_deltas[0].capture.landing_square == "d6"


# ---- A29 Black symmetry ----------------------------------------------------------------------


def test_a29_black_strong_move_material_and_mate():
    result, _, _ = strong(
        BLACK_TAKES, ("d8d5", "e8f8"), {"d8d5": ("e1e2", "e8e7"), "e8f8": ("d5c7", "d8d1")}
    )
    material = by_kind(result)[K.MATERIAL_THREAT]
    assert material.subject == (base(Color.WHITE, PieceType.KNIGHT, "d5"),)
    assert material.material_evidence[0].material_delta == 320
    mate_result, _, _ = strong(
        "5q2/8/8/8/8/6k1/8/7K b - - 0 1", ("f8f1", "f8f2"), {"f8f2": ("h1g1",)}
    )
    assert by_kind(mate_result)[K.MATE_THREAT].subject == (base(Color.WHITE, PieceType.KING, "h1"),)


def test_a29_black_only_move_preservation():
    result, _ = only(
        DEFEND_BLACK,
        ("h7h6", "d8a8", "d8d7"),
        {"h7h6": ("f2f3", "g8h7"), "d8a8": ("b7a8",), "d8d7": ("b7d7", "h7h6", "f2f3")},
    )
    kinds = by_kind(result)
    assert kinds[K.PREVENTS_MATE].subject == (base(Color.BLACK, PieceType.KING, "g8"),)
    assert ucis(kinds[K.PREVENTS_MATE].failed_alternatives) == ("d8a8",)
    loss = kinds[K.PREVENTS_MATERIAL_LOSS]
    assert [m.material_delta for m in loss.material_evidence] == [0, -500, -500]
    assert loss.subject == (base(Color.BLACK, PieceType.ROOK, "d8"),)


# ---- A30 deterministic ordering --------------------------------------------------------------


def test_a30_repeated_and_perturbed_evaluation_is_identical():
    args = (ATTACK, ("a1a5", "e1e2", "e1d2"), ATTACK_LINES)
    ignored = {"a7a6": (("a7a6", "a5h5", "e8d7", "e1e2"), EngineScore.cp(300))}
    baseline, _, (_explainer, _context, _, _) = strong(*args, ignored=ignored)
    perturbed, _, _ = strong(
        *args, ignored=ignored, tactical_rules=ReversedRules(), detector=ReversedDetector()
    )
    assert perturbed == baseline
    assert repr(perturbed) == repr(baseline)
    benefit = by_kind(baseline)[K.MATERIAL_THREAT]
    assert [r.probe.kind for r in benefit.probe_results] == [ProbeKind.REFUTATION] * 3 + [
        ProbeKind.IGNORE_THREAT
    ]
    assert [a.rank for a in baseline.alternatives] == [2, 3]


def test_a30_preservation_order_is_stable_under_perturbation():
    lines = {**SAFE, **ROOK_LOST, "g1h1": PAWN_LOST["g1h1"]}
    first, _ = only(DEFEND, ("h2h3", "g1h1", "d1d2"), lines)
    second, _ = only(
        DEFEND,
        ("h2h3", "g1h1", "d1d2"),
        lines,
        tactical_rules=ReversedRules(),
        detector=ReversedDetector(),
    )
    assert first == second
    benefit = by_kind(first)[K.PREVENTS_MATERIAL_LOSS]
    assert [a.rank for a in benefit.failed_alternatives] == [2, 3]
    assert [b.base_square for b in benefit.subject] == ["d1", "f2"]


# ---- architecture gates ----------------------------------------------------------------------

P9_MODULES = (good_move_module, benefits_module, preservation_module)


def _imports(module):
    tree = ast.parse(inspect.getsource(module))
    return {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | {
        alias.name for n in ast.walk(tree) if isinstance(n, ast.Import) for alias in n.names
    }


def test_public_api_is_unchanged_by_p9():
    public = set(getattr(calliope, "__all__", ())) | set(vars(calliope))
    assert not any(name.startswith("GoodMove") for name in public)
    for module in (contracts, public_engine):
        source = inspect.getsource(module)
        assert "GoodMove" not in source and "good_move" not in source
    # G0 (not P9) owns the public schema; it moved to 0.2 at application integration.
    assert contracts.PUBLIC_SCHEMA_VERSION == "0.2"
    for module in P9_MODULES:
        assert not any(
            part in name
            for name in _imports(module)
            for part in ("commentary", "render", "llm", "anthropic", "openai", "calliope.engine")
        )


def test_p3_numbers_are_absent_from_causal_policy_sources():
    numeric = {
        "best_score",
        "played_score",
        "cp_loss",
        "expected_score_loss",
        "acceptable_move_count",
        "best_to_second_gap_cp",
        "wdl",
        "position_analysis",
        "judgement",
    }
    policy = [
        ast.parse(inspect.getsource(benefits_module)),
        ast.parse(inspect.getsource(preservation_module)),
    ]
    methods = [
        name
        for name, _ in inspect.getmembers(GoodMoveExplainer, inspect.isfunction)
        if not name.startswith("__")
        and name not in {"prepare", "_canonical"}  # I1's reviewed mode/rank selection
    ]
    policy += [
        ast.parse(textwrap.dedent(inspect.getsource(getattr(GoodMoveExplainer, name))))
        for name in methods
    ]
    for tree in policy:
        attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not attributes & numeric


def test_no_literal_uniqueness_surface():
    for module in P9_MODULES:
        source = inspect.getsource(module)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "literal_only_move_proven":
                assert isinstance(node.value, ast.Constant) and node.value.value is False
        identifiers = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
            n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
        }
        assert not {i for i in identifiers if re.search(r"(?i)exhaustive|all_legal|unique_move", i)}
    domain = Path(inspect.getsourcefile(GoodMoveExplanationResult)).read_text()
    assert "literal_only_move_proven must always be False" in domain


def test_benefit_vocabulary_is_closed():
    assert {kind.name for kind in GoodMoveBenefitKind} == {
        "FORCES_RESPONSE",
        "MATE_THREAT",
        "MATERIAL_THREAT",
        "PREVENTS_MATE",
        "PREVENTS_MATERIAL_LOSS",
    }
    for module in P9_MODULES:
        source = inspect.getsource(module)
        for speculative in ("POSITIONAL", "INITIATIVE", "SPACE_GAIN", "KING_SAFETY", "STRUCTURE"):
            assert speculative not in source
    assert evaluate_only_move is preservation_module.evaluate_only_move
