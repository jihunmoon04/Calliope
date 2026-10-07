"""Real P9 ONLY_MOVE/scripted P7 fixtures shared by P10-I4 tests (not collected)."""

from dataclasses import replace

from _p9_strong_claim_scenarios import CP0, ScriptedEngine, rules

from calliope.domain.analysis import GoodMoveBenefitKind, GoodMoveBenefitStatus
from calliope.domain.chess import ChessMove, Color
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
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.explanation import GoodMoveExplainer
from calliope.services.explanation.claim_builder import ClaimBuilder
from calliope.services.explanation.evidence_builder import EvidenceBuilder
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.tactics import TacticalDetector

Kind = GoodMoveBenefitKind
QUEEN = "6k1/5ppp/8/8/8/8/1q3PPP/3R2K1 w - - 0 1"
START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
SAFE = {"h2h3": ("f7f6", "g1h2"), "f2f3": ("f7f6", "g1h1"), "d1e1": ("f7f6", "h2h3")}
MATE_NOW = {"d1a1": ("b2a1",), "d1b1": ("b2b1",)}
ROOK_LOST = {"d1d2": ("b2d2", "h2h3", "g8f8"), "d1d4": ("b2d4", "h2h3", "g8f8")}


def explain(fen, moves, lines=None, attach=None):
    base = rules.position_from_fen(fen)
    script = {}
    for first, value in (lines or {}).items():
        pv, score = value if isinstance(value[-1], EngineScore) else (value, CP0)
        position = rules.apply_move(base, rules.legal_move_from_uci(base, first))
        script[(position.position_id, None)] = (pv, score)
    facts = PositionFactExtractor(rules)
    p7 = CounterfactualAnalyzer(rules, ScriptedEngine(script), rules, rules)
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
        Forcedness(ForcednessLevel.ONLY_MOVE),
    )
    prepared = explainer.prepare(base, judgement.move, judgement, analysis)
    context = explainer.verify_counterfactuals(
        explainer.build_branches(prepared),
        EngineSettings(EngineLimit(time_ms=43), multipv=1, threads=1, hash_mb=16),
    )
    if attach is not None:
        context = explainer.verify_ignored_response(context, ChessMove(attach))
    return explainer.explain_only_move(context)


def mate_all():
    return explain(QUEEN, ("h2h3", "d1a1", "d1b1"), {**SAFE, **MATE_NOW})


def mate_subset():
    return explain(QUEEN, ("h2h3", "d1a1", "f2f3"), {**SAFE, **MATE_NOW})


def engine_mate():
    return explain(
        QUEEN,
        ("h2h3", "f2f3"),
        {
            **SAFE,
            "f2f3": (("b2b1", "d1b1"), EngineScore.forced_mate(Color.BLACK, 4)),
        },
    )


def replayed_engine_mate():
    return explain(QUEEN, ("h2h3", "d1d7"), {**SAFE, "d1d7": ("b2b1", "d7d1", "b1d1")})


def material_all():
    return explain(QUEEN, ("h2h3", "d1d2", "d1d4"), {**SAFE, **ROOK_LOST})


def material_subset():
    return explain(QUEEN, ("h2h3", "d1d2", "f2f3"), {**SAFE, **ROOK_LOST})


def quiet():
    return explain(START, ("e2e4", "d2d4"), {"e2e4": ("e7e5", "g1f3"), "d2d4": ("d7d5", "c1f4")})


def no_alternatives():
    return explain(QUEEN, ("h2h3",), SAFE)


def refuted():
    return explain(QUEEN, ("d1d2", "d1d4"), ROOK_LOST)


def inconclusive():
    return explain(QUEEN, ("h2h3", "d1d2"), {**ROOK_LOST, "h2h3": ("f7f6",)})


SCENARIOS = (
    mate_all,
    mate_subset,
    engine_mate,
    replayed_engine_mate,
    material_all,
    material_subset,
)


def evidence(result):
    return EvidenceBuilder().build_good_move(result)


def claims(bundle):
    return ClaimBuilder().build_good_move(bundle)


def only_kind(result, kind):
    (benefit,) = [
        b for b in result.benefits if b.kind is kind and b.status is GoodMoveBenefitStatus.SUPPORTED
    ]
    return replace(result, benefits=(benefit,))


def package(make=material_all, kind=None):
    if kind is None:
        kind = Kind.PREVENTS_MATE if make in SCENARIOS[:4] else Kind.PREVENTS_MATERIAL_LOSS
    bundle = evidence(only_kind(make(), kind))
    (claim,) = claims(bundle)
    return bundle, claim, bundle.groups[0], list(bundle.evidence)


def of_type(records, record_type):
    return [r for r in records if isinstance(r, record_type)]


def tamper(value, **changes):
    """Corrupt frozen P10 values only in adversarial validator tests."""
    for name, change in changes.items():
        object.__setattr__(value, name, change)
    return value
