"""Shared real-P8 -> I1 fixtures for the P10-I2 claim tests (not a test module).

Mirrors the scripted P8 harness in test_bad_move_causes.py: python-chess rules plus a fake
line engine drive the real P8 explainer, and the real I1 EvidenceBuilder maps the result.
"""

from dataclasses import dataclass, field, replace

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis import BadMoveCauseKind, BadMoveExplanationResult
from calliope.domain.chess import ChessMove, Color
from calliope.domain.engine import (
    EngineAnalysis,
    EngineIdentity,
    EngineLine,
    EngineScore,
    MoveJudgement,
    MoveQuality,
)
from calliope.domain.explanation import EvidenceBundle
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.counterfactual.analyzer import DEFAULT_SETTINGS
from calliope.services.explanation import BadMoveExplainer
from calliope.services.explanation.claim_builder import ClaimBuilder
from calliope.services.explanation.evidence_builder import EvidenceBuilder
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.tactics import TacticalDetector

rules = PythonChessAdapter()
_facts = PositionFactExtractor(rules)
_deltas = BoardDeltaAnalyzer(rules, _facts)
_detector = TacticalDetector()

cp = EngineScore.cp
mate = EngineScore.forced_mate
Kind = BadMoveCauseKind

KNIGHT = "4k3/8/8/3p4/8/2N5/8/4K3 w - - 0 1"
DEFENDER = "3rk3/8/8/8/3N4/2P5/8/4K3 w - - 0 1"
FORK = "4k3/8/8/8/1n6/3B4/8/R3K3 w - - 0 1"
BACK_RANK = "4r1k1/8/8/8/8/8/5PPP/3R2K1 w - - 0 1"


def after(fen, *ucis):
    position = rules.position_from_fen(fen)
    for uci in ucis:
        position = rules.apply_move(position, rules.legal_move_from_uci(position, uci))
    return position


@dataclass
class _LineEngine:
    lines: dict
    forced: dict = field(default_factory=dict)

    def analyze(self, position, settings, root_moves=None):
        if root_moves:
            pv, score = self.forced.get(position.position_id, ((root_moves[0].uci,), cp(0)))
        else:
            pv, score = self.lines[position.position_id]
        moves = tuple(ChessMove(uci) for uci in pv)
        return EngineAnalysis(
            position_id=position.position_id,
            engine=EngineIdentity("Fake", "1"),
            settings=settings,
            lines=(EngineLine(1, moves[0], score, moves),),
        )


def explain(fen, played, best, actual, comparator, same=None) -> BadMoveExplanationResult:
    base = rules.position_from_fen(fen)
    lines = {after(fen, played).position_id: actual, after(fen, best).position_id: comparator}
    forced = {after(fen, best).position_id: same} if same else {}
    p7 = CounterfactualAnalyzer(rules, _LineEngine(lines, forced), rules, rules)
    explainer = BadMoveExplainer(rules, _facts, _deltas, rules, _detector, p7)
    judgement = MoveJudgement(
        position_id=base.position_id,
        mover=base.side_to_move,
        move=ChessMove(played),
        best_move=ChessMove(best),
        quality=MoveQuality.BLUNDER,
        rank=None,
        best_score=cp(0),
        played_score=cp(-300),
        cp_loss=300,
        expected_score_loss=0.3,
    )
    return explainer.explain(base, judgement.move, judgement, DEFAULT_SETTINGS)


def knight():
    return explain(
        KNIGHT,
        "c3e4",
        "c3b5",
        (("d5e4", "e1d2", "e8d7"), cp(-300)),
        (("e8d7", "e1d2", "d7e6"), cp(0)),
    )


def defender():
    return explain(
        DEFENDER,
        "c3c4",
        "e1e2",
        (("d8d4", "e1e2", "d4d5"), cp(-300)),
        (("e8e7", "e2e3", "e7f7"), cp(0)),
        (("d8d4", "c3d4", "e8e7", "e2e3"), cp(0)),
    )


def fork():
    return explain(
        FORK,
        "d3e4",
        "e1f1",
        (("b4c2", "e1d2", "c2a1", "e4d3", "e8e7"), cp(-500)),
        (("e8e7", "f1e2", "e7f7"), cp(0)),
        (("b4c2", "d3c2", "e8e7", "f1e2"), cp(0)),
    )


def exact_mate():
    return explain(
        BACK_RANK,
        "d1d7",
        "h2h3",
        (("e8e1",), mate(Color.BLACK, 1)),
        (("g8f8", "g1h2", "f8e7"), cp(0)),
    )


def engine_mate(score=None):
    return explain(
        BACK_RANK,
        "d1d7",
        "h2h3",
        (("g8f8", "d7a7", "e8e1"), score or mate(Color.BLACK, 2)),
        (("g8f8", "g1h2", "f8e7"), cp(0)),
    )


def only_kind(result: BadMoveExplanationResult, kind) -> BadMoveExplanationResult:
    (cause,) = [c for c in result.causes if c.kind is kind]
    return replace(result, causes=(cause,))


def evidence(result: BadMoveExplanationResult) -> EvidenceBundle:
    return EvidenceBuilder().build_bad_move(result)


def claims(bundle: EvidenceBundle):
    return ClaimBuilder().build_bad_move(bundle)


def group_of(bundle, kind):
    (group,) = [g for g in bundle.groups if g.source_kind is kind]
    return group


def records_of(bundle, group):
    by_id = {record.evidence_id: record for record in bundle.evidence}
    return [by_id[evidence_id] for evidence_id in group.evidence_ids]


def tamper(value, **changes):
    """Bypass frozen-domain validation to simulate a malicious or corrupted package."""

    for name, change in changes.items():
        object.__setattr__(value, name, change)
    return value
