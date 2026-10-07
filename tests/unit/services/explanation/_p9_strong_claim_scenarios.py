"""Shared real-P9/scripted-P7 success fixtures for P10-I3 (not a collected module)."""

from dataclasses import replace

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis import GoodMoveBenefitKind, GoodMoveBenefitStatus
from calliope.domain.chess import ChessMove, Color
from calliope.domain.engine import (
    EngineAnalysis,
    EngineIdentity,
    EngineLimit,
    EngineLine,
    EngineScore,
    EngineSettings,
    MoveJudgement,
    MoveQuality,
)
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.explanation import GoodMoveExplainer
from calliope.services.explanation.claim_builder import ClaimBuilder
from calliope.services.explanation.evidence_builder import EvidenceBuilder
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.tactics import TacticalDetector

rules = PythonChessAdapter()
SETTINGS = EngineSettings(EngineLimit(time_ms=41), multipv=1, threads=1, hash_mb=16)
IDENTITY = EngineIdentity("Scripted P7", "1")
Kind = GoodMoveBenefitKind
CP0 = EngineScore.cp(0)
QUEEN = "7k/8/6K1/8/8/8/8/5Q2 w - - 0 1"
ROOK_CHECK = "k7/8/2K5/8/8/8/8/1R6 w - - 0 1"
BACK_RANK = "6k1/5ppp/8/8/8/8/3B4/3Q2K1 w - - 0 1"
ROOK_TAKES = "4k3/8/8/3n4/8/8/8/3RK3 w - - 0 1"
ATTACK = "4k3/p7/8/7n/8/8/8/R3K3 w - - 0 1"
START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


class ScriptedEngine:
    def __init__(self, script):
        self.script = script

    def analyze(self, position, settings, root_moves=None):
        root = root_moves[0].uci if root_moves else None
        ucis, score = self.script.get(
            (position.position_id, root),
            ((root or rules.observe_tactics(position).legal_moves[0].uci,), CP0),
        )
        pv = tuple(ChessMove(u) for u in ucis)
        return EngineAnalysis(
            position.position_id, IDENTITY, settings, (EngineLine(1, pv[0], score, pv),)
        )


def explain(fen, moves, lines=None, ignored=None, quality=MoveQuality.GOOD):
    """Execute the reviewed P9 pipeline; P10 never receives any of these dependencies."""
    base = rules.position_from_fen(fen)
    played_position = rules.apply_move(base, rules.legal_move_from_uci(base, moves[0]))
    script = {}
    for first, (pv, score) in (lines or {}).items():
        position = rules.apply_move(base, rules.legal_move_from_uci(base, first))
        script[(position.position_id, None)] = (pv, score)
    for q, (pv, score) in (ignored or {}).items():
        script[(played_position.position_id, q)] = (pv, score)
    p7 = CounterfactualAnalyzer(rules, ScriptedEngine(script), rules, rules)
    facts = PositionFactExtractor(rules)
    explainer = GoodMoveExplainer(
        rules, facts, BoardDeltaAnalyzer(rules, facts), rules, TacticalDetector(), p7
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
    )
    prepared = explainer.prepare(base, judgement.move, judgement, analysis)
    context = explainer.verify_counterfactuals(explainer.build_branches(prepared), SETTINGS)
    return explainer.explain_strong_move(context)


def forces():
    return explain(
        ROOK_CHECK,
        ("b1a1", "b1h1", "b1c1"),
        {
            "b1a1": (("a8b8", "c6b6"), EngineScore.cp(800)),
            "b1h1": (("a8b8", "c6d6"), CP0),
            "b1c1": (("a8b8", "c6d6"), CP0),
        },
    )


def exact_mate():
    return explain(QUEEN, ("f1f8", "f1f7", "f1a1"))


def direct_mate():
    return explain(
        QUEEN,
        ("f1a1", "g6f6", "f1h1"),
        {
            "f1a1": (("h8g8", "a1a8"), EngineScore.forced_mate(Color.WHITE, 2)),
            "g6f6": (("h8g8", "f1f2"), EngineScore.cp(900)),
        },
    )


def ignored_mate():
    return explain(
        BACK_RANK,
        ("d2e3", "g1f1", "g1h1"),
        {
            "d2e3": (("h7h6", "g1h2"), EngineScore.cp(60)),
            "g1f1": (("h7h6", "f1e2"), CP0),
            "g1h1": (("h7h6", "h1g1"), CP0),
        },
        {"g8f8": (("g8f8", "d1d8"), EngineScore.forced_mate(Color.WHITE, 1))},
    )


def direct_material():
    return explain(
        ROOK_TAKES,
        ("d1d5", "e1e2", "e1f2"),
        {
            "d1d5": (("e8e7", "e1e2"), CP0),
            "e1e2": (("d5c3", "e2e3"), CP0),
            "e1f2": (("d5c3", "f2f3"), CP0),
        },
    )


def ignored_material():
    return explain(
        ATTACK,
        ("a1a5", "e1e2", "e1d2"),
        {
            "a1a5": (("h5f6", "e1e2"), EngineScore.cp(40)),
            "e1e2": (("h5f4", "e2e3"), CP0),
            "e1d2": (("h5f4", "d2e3"), CP0),
        },
        {"a7a6": (("a7a6", "a5h5", "e8d7", "e1e2"), EngineScore.cp(300))},
    )


def equivalent_mate():
    return explain(
        QUEEN,
        ("f1f8", "f1a1"),
        {
            "f1a1": (("h8g8",), EngineScore.forced_mate(Color.WHITE, 2)),
        },
    )


def supported_with_refuted_sibling():
    return explain(
        QUEEN,
        ("f1a1", "g6f6", "f1h1"),
        {
            "f1a1": (("h8g8", "a1a8"), EngineScore.forced_mate(Color.WHITE, 2)),
            "g6f6": (("h8g8", "f1f2"), EngineScore.forced_mate(Color.WHITE, 9)),
        },
    )


def quiet():
    return explain(
        START,
        ("e2e4", "d2d4"),
        {
            "e2e4": (("e7e5", "g1f3"), CP0),
            "d2d4": (("d7d5", "c1f4"), CP0),
        },
        quality=MoveQuality.BEST,
    )


SCENARIOS = (forces, exact_mate, direct_mate, ignored_mate, direct_material, ignored_material)


def evidence(result):
    return EvidenceBuilder().build_good_move(result)


def claims(bundle):
    return ClaimBuilder().build_good_move(bundle)


def only_kind(result, kind):
    (benefit,) = [
        b for b in result.benefits if b.kind is kind and b.status is GoodMoveBenefitStatus.SUPPORTED
    ]
    return replace(result, benefits=(benefit,))


def package(make):
    result = make()
    if make is direct_mate:
        result = only_kind(result, Kind.MATE_THREAT)
    bundle = evidence(result)
    (claim,) = claims(bundle)
    (group,) = bundle.groups
    return bundle, claim, group, list(bundle.evidence)


def of_type(records, record_type):
    return [r for r in records if isinstance(r, record_type)]


def tamper(value, **changes):
    for name, change in changes.items():
        object.__setattr__(value, name, change)
    return value
