"""P8-I5 adversarial coverage: P8 must not invent causes from incomplete or confused evidence.

Every fixture is a hand-checked position replayed through the real rules, P4/P5/P6 services and
the real P7 analyzer behind a scripted engine.  No Stockfish binary is required.
"""

import ast
import copy
import inspect
from dataclasses import dataclass, field, replace

import pytest

import calliope
import calliope.services.explanation.bad_move as bad_move_module
import calliope.services.explanation.bad_move_causes as bad_move_causes_module
import calliope.services.explanation.piece_identity as piece_identity_module
from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis import (
    BadMoveCauseKind,
    BadMoveCauseStatus,
    BadMoveExplanationStatus,
    BasePieceRef,
    CounterfactualBatchResult,
    MateEvidenceLevel,
    PieceTransitionKind,
    ProbeKind,
    TacticalCandidate,
    TacticalCandidateKind,
    TacticalCandidateStatus,
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
    MoveJudgement,
    MoveQuality,
)
from calliope.errors import IncompatibleBadMoveContextError
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.counterfactual.analyzer import DEFAULT_SETTINGS
from calliope.services.explanation import BadMoveExplainer
from calliope.services.explanation.bad_move import BadMovePreparedContext
from calliope.services.explanation.bad_move_causes import (
    evaluate_bad_move_causes,
    fingerprint,
    material_advantage,
    material_evidence,
    normalize_piece,
)
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.tactics import TacticalDetector

rules = PythonChessAdapter()
facts = PositionFactExtractor(rules)
deltas = BoardDeltaAnalyzer(rules, facts)
detector = TacticalDetector()

W, B = Color.WHITE, Color.BLACK
P, N, Bi, R, Q, K = (
    PieceType.PAWN,
    PieceType.KNIGHT,
    PieceType.BISHOP,
    PieceType.ROOK,
    PieceType.QUEEN,
    PieceType.KING,
)
cp = EngineScore.cp
mate = EngineScore.forced_mate
Kind = BadMoveCauseKind
S = BadMoveCauseStatus
Agg = BadMoveExplanationStatus
TK = TacticalCandidateKind
FAKE = EngineIdentity("Fake", "1")
FAKE2 = EngineIdentity("Fake", "2")
OTHER_SETTINGS = EngineSettings(limit=EngineLimit(time_ms=500), multipv=1, threads=1)

# ---- fixtures (all hand-checked; scores are White-POV) ---------------------------------------

# Nc3-e4 hangs the knight to d5xe4; after Nc3-b5, d5e4 is illegal.
KNIGHT = "4k3/8/8/3p4/8/2N5/8/4K3 w - - 0 1"
KNIGHT_TAKEN = (("d5e4", "e1d2", "e8d7"), cp(-300))
KNIGHT_QUIET = (("e8d7", "e1d2", "d7e6"), cp(0))
# As KNIGHT plus facing h-file rooks.
KNIGHT_ROOK = "4k2r/8/8/3p4/8/2N5/8/4K2R w - - 0 1"
# A7: after Nc3-b5 the knight is defended by the f1 bishop (so not hanging), d5e4 is illegal,
# and the comparator's own line wins it with a6xb5 instead.
KNIGHT_B5 = "4k3/8/p7/3p4/8/2N5/8/4KB2 w - - 0 1"
# A8: d5xe4 is legal after both Nc3-e4 (takes the c3 knight) and e3-e4 (takes the e3 pawn).
KNIGHT_E3 = "4k3/8/8/3p4/8/2N1P3/8/4K3 w - - 0 1"
# A11: a second white minor piece on g4, already en prise to h5xg4 in the base.
KNIGHT_G4 = "4k3/8/8/3p3p/6N1/2N5/8/4K3 w - - 0 1"
BISHOP_G4 = "4k3/8/8/3p3p/6B1/2N5/8/4K3 w - - 0 1"
# Nc3-a4 (A) also hangs the knight, to the d7 bishop.
KNIGHT_BISHOP = "4k3/3b4/8/3p4/8/2N5/8/4K3 w - - 0 1"
BISHOP_TAKEN = (("d5e4", "e1d2", "e8e7"), cp(-300))
# Two white knights that can both reach e4.
TWO_KNIGHTS = "4k3/8/8/6N1/8/2N5/8/4K3 w - - 0 1"
# Ne2-c3 removes the e2 knight's defence of d4 and blocks the b2 bishop's defence of it.
TWO_DEFENDERS = "3rk3/8/8/8/3N4/8/1B2N3/6K1 w - - 0 1"
# Nd3-c5 removes the knight's defence of its own king (frozen: never a REMOVED_DEFENDER).
KING_DEFENDER = "4k3/8/8/8/8/3N4/8/4K3 w - - 0 1"
DEFENDER_TWICE = "3rk3/8/8/8/3N4/2P5/8/3RK3 w - - 0 1"
# Bd3-e4 abandons c2: Nb4-c2+ forks the e1 king and a1 rook.
FORK = "4k3/8/8/8/1n6/3B4/8/R3K3 w - - 0 1"
FORK_COMPARATOR = (("e8e7", "f1e2", "e7f7"), cp(0))
FORK_SAME = (("b4c2", "d3c2", "e8e7", "f1e2"), cp(0))
# Be1-b4 abandons f2: Ne4-f2 is a smothered mate that also forks d1 and h1.
SMOTHER = "k7/8/8/8/4n3/8/6PP/3QB1RK w - - 0 1"
# As SMOTHER without the g1 rook: Nf2+ forks but Kg1 escapes (engine-line mate only).
FORK_CHECK = "k7/8/8/8/4n3/8/6PP/3QB2K w - - 0 1"
SMOTHER_COMPARATOR = (("a8b8", "e2d2", "b8a8"), cp(0))
SMOTHER_SAME = (("e4f2", "e1f2", "a8b8", "f2e1"), cp(0))
# Back rank: Rd1-d7 allows Re8-e1#.
BACK_RANK = "4r1k1/8/8/8/8/8/5PPP/3R2K1 w - - 0 1"
# As BACK_RANK with a c8 bishop: Rd1-d7 also hangs the rook.
BACK_RANK_C8 = "2b1r1k1/8/8/8/8/8/5PPP/3R2K1 w - - 0 1"
# Ne4-g5 hangs the knight to Rg8xg5; White then has only h-pawn tempi before stalemate.
STALEMATE_LATE = "6r1/8/8/7p/4N3/p7/P1k4P/K7 w - - 0 1"
STALEMATE_EARLY = "6r1/8/8/7p/4N3/p6P/P1k5/K7 w - - 0 1"
STALEMATE_SAME = (("g8g5", "h2h3", "g5g6"), cp(0))
# Qf7 stalemates, Qf8 mates.
QUEEN = "7k/8/6K1/8/8/8/8/5Q2 w - - 0 1"
# Ne7-g8 hangs the knight to the king; Qf8 is mate.
QUEEN_KNIGHT = "7k/4N3/6K1/8/8/8/8/5Q2 w - - 0 1"
# As QUEEN_KNIGHT with blocked a-pawns, so Qf7 is stalemate.
QUEEN_KNIGHT_PAWNS = "7k/4N3/6K1/8/8/p7/P7/5Q2 w - - 0 1"
QUEEN_KNIGHT_TAKEN = (("h8g8", "f1b5", "g8h8"), cp(-300))
# a2-a1 promotes for Black; a black queen on h7 can also reach b1.
PROMOTION = "4k3/8/8/8/8/8/p7/4K2R w - - 0 1"
PROMOTION_SAME = (("a2a1q", "h1a1", "e8f8", "d2e3"), cp(0))
QUEENS = "4k3/7q/8/8/8/8/1p6/6K1 w - - 0 1"
# e2-e4 allows d4xe3 en passant.
EN_PASSANT = "4k3/8/8/8/3p4/8/4P3/4K3 w - - 0 1"
# KNIGHT with White kingside castling rights.
CASTLING = "4k3/8/8/3p4/8/2N5/8/4K2R w K - 0 1"
# Black to move: the KNIGHT fixtures mirrored.
BLACK_KNIGHT = "4k3/8/2n5/8/3P4/8/8/4K3 b - - 0 1"
BLACK_KNIGHT_ROOK = "4k2r/8/2n5/8/3P4/8/8/4K2R b - - 0 1"


def after(fen: str, *ucis: str):
    position = rules.position_from_fen(fen)
    for uci in ucis:
        position = rules.apply_move(position, rules.legal_move_from_uci(position, uci))
    return position


@dataclass
class LineEngine:
    """Scripted engine: full PVs per analysed position; forced roots may be scripted too."""

    lines: dict
    forced: dict = field(default_factory=dict)
    identity_for_call: object = lambda call: FAKE
    calls: list = field(default_factory=list)

    def analyze(self, position, settings, root_moves=None):
        self.calls.append((position, root_moves))
        if root_moves:
            pv, score = self.forced.get(position.position_id, ((root_moves[0].uci,), cp(0)))
            assert pv[0] == root_moves[0].uci
        else:
            pv, score = self.lines[position.position_id]
        moves = tuple(ChessMove(uci) for uci in pv)
        return EngineAnalysis(
            position_id=position.position_id,
            engine=self.identity_for_call(len(self.calls)),
            settings=settings,
            lines=(EngineLine(1, moves[0], score, moves),),
        )


class RecordingP7:
    """The real P7 analyzer behind a recorder that may tamper with returned batches."""

    def __init__(self, analyzer, tamper=None) -> None:
        self.analyzer = analyzer
        self.tamper = tamper
        self.requests: list = []

    def execute(self, request):
        self.requests.append(request)
        result = self.analyzer.execute(request)
        return self.tamper(len(self.requests), result) if self.tamper else result

    @property
    def probes(self) -> int:
        return sum(len(request.probes) for request in self.requests)


class InjectingDetector:
    """The real P6 detector, with extra candidates prepended after chosen positions."""

    def __init__(self, inject: dict) -> None:
        self.inject = inject

    def detect(self, **kwargs):
        detection = detector.detect(**kwargs)
        extra = self.inject.get(kwargs["after"].position_id, ())
        return replace(detection, candidates=(*extra, *detection.candidates))


def judgement(base, played: str, best: str, quality=MoveQuality.BLUNDER) -> MoveJudgement:
    return MoveJudgement(
        position_id=base.position_id,
        mover=base.side_to_move,
        move=ChessMove(played),
        best_move=ChessMove(best),
        quality=quality,
        rank=None,
        best_score=cp(0),
        played_score=cp(-300),
        cp_loss=300,
        expected_score_loss=0.3,
    )


@dataclass
class Scenario:
    explainer: BadMoveExplainer
    p7: RecordingP7
    engine: LineEngine
    base: object
    judgement: MoveJudgement

    def context(self):
        prepared = self.explainer.prepare(self.base, self.judgement.move, self.judgement)
        assert isinstance(prepared, BadMovePreparedContext)
        return self.explainer.verify_counterfactuals(prepared, DEFAULT_SETTINGS)

    def lines(self):
        return self.explainer.replay_lines(self.context())

    def explain(self):
        return self.explainer.explain(
            self.base, self.judgement.move, self.judgement, DEFAULT_SETTINGS
        )


def scenario(
    fen,
    played,
    best,
    actual=(),
    comparator=(),
    same=None,
    *,
    quality=MoveQuality.BLUNDER,
    inject=None,
    tamper=None,
    identity_for_call=None,
):
    """actual/comparator: (PV ucis, White-POV score); same: scripted Batch-B forced line."""

    base = rules.position_from_fen(fen)
    lines = {}
    if actual:
        lines[after(fen, played).position_id] = actual
    if comparator:
        lines[after(fen, best).position_id] = comparator
    forced = {after(fen, best).position_id: same} if same else {}
    engine = LineEngine(lines, forced)
    if identity_for_call is not None:
        engine.identity_for_call = identity_for_call
    p7 = RecordingP7(CounterfactualAnalyzer(rules, engine, rules, rules), tamper)
    used_detector = InjectingDetector(inject) if inject else detector
    explainer = BadMoveExplainer(rules, facts, deltas, rules, used_detector, p7)
    return Scenario(explainer, p7, engine, base, judgement(base, played, best, quality))


def by_kind(result, kind):
    (cause,) = [c for c in result.causes if c.kind is kind]
    return cause


def kinds(result):
    return [c.kind for c in result.causes]


def base(color, kind, square):
    return BasePieceRef(color, kind, square)


def candidate(kind, actors=(), targets=(), related=(), responses=()):
    return TacticalCandidate(
        kind,
        TacticalCandidateStatus.DETECTED,
        actors=tuple(actors),
        targets=tuple(targets),
        related=tuple(related),
        responses=tuple(responses),
    )


def has_candidate(step, kind, subject=None):
    return any(
        c.kind is kind and (subject is None or step.identity.base_ref_for(c.targets[0]) == subject)
        for c in step.detection.candidates
    )


def knight_taken(comparator=KNIGHT_QUIET, **kw):
    return scenario(KNIGHT, "c3e4", "c3b5", KNIGHT_TAKEN, comparator, **kw)


def a7_scenario():
    return scenario(
        KNIGHT_B5,
        "c3e4",
        "c3b5",
        (("d5e4", "e1d2", "e8e7"), cp(-300)),
        (("a6b5", "f1b5", "e8e7", "e1d2"), cp(-200)),
    )


A8_SAME = (("d5e4", "e1e2", "e8e7"), cp(0))


def a8_scenario(same=A8_SAME):
    return scenario(
        KNIGHT_E3,
        "c3e4",
        "e3e4",
        (("d5e4", "e1d2", "e8d7"), cp(-300)),
        (("e8e7", "e1e2", "e7e6"), cp(0)),
        same,
    )


def removed_defenders_scenario():
    return scenario(
        TWO_DEFENDERS,
        "e2c3",
        "g1f1",
        (("d8d4", "g1f2", "e8e7"), cp(-300)),
        (("e8e7", "f1e1", "e7f7"), cp(0)),
        (("d8d4", "e2d4", "e8e7", "f1e1"), cp(0)),
    )


def fork_scenario(actual_pv=("b4c2", "e1d2", "c2a1", "e4d3", "e8e7"), **kw):
    return scenario(FORK, "d3e4", "e1f1", (actual_pv, cp(-500)), FORK_COMPARATOR, FORK_SAME, **kw)


KNIGHT_C3 = base(W, N, "c3")


# =============================================================================================
# §18.4 mandatory adversarial matrix
# =============================================================================================


def test_a1_hanging_geometry_without_exploitation_is_refuted() -> None:
    s = scenario(KNIGHT, "c3e4", "c3b5", (("e8d7", "e1d2", "d7e6"), cp(-300)), KNIGHT_QUIET)
    lines = s.lines()
    assert has_candidate(lines.actual.plies[0], TK.HANGING_PIECE, KNIGHT_C3)
    assert all(step.delta.capture is None for step in lines.actual.plies)

    result = s.explain()
    cause = by_kind(result, Kind.NEWLY_HANGING_PIECE)
    assert cause.material_evidence[0].stable_at_ply == 3
    assert cause.status is S.REFUTED
    assert result.status is Agg.REFUTED


def test_a2_fork_geometry_without_consequence_is_refuted() -> None:
    s = fork_scenario(("b4c2", "e1d2", "c2b4", "e4d3", "e8e7"))
    lines = s.lines()
    (fork,) = [c for c in lines.actual.plies[1].detection.candidates if c.kind is TK.FORK]
    assert PieceRef(W, K, "e1") in fork.targets
    assert all(step.delta.capture is None for step in lines.actual.plies)

    cause = by_kind(s.explain(), Kind.FORK_ALLOWED)
    assert cause.material_evidence[0].stable_at_ply is not None
    assert cause.material_evidence[0].stable_deficit is None
    assert cause.status is S.REFUTED


@pytest.mark.parametrize(
    ("fen", "best", "actual", "comparator", "kind"),
    [
        # Physical identity: the comparator's own line wins the same c3 knight.
        (
            KNIGHT_BISHOP,
            "c3a4",
            BISHOP_TAKEN,
            (("d7a4", "e1d2", "e8e7"), cp(-250)),
            Kind.NEWLY_HANGING_PIECE,
        ),
        # Material value: the comparator's own line loses the h1 rook (500 >= 320).
        (
            KNIGHT_ROOK,
            "c3b5",
            KNIGHT_TAKEN,
            (("h8h1", "e1e2", "e8d7"), cp(-200)),
            Kind.MATERIAL_LOSS_LINE,
        ),
    ],
    ids=["identity-hanging", "value-material"],
)
def test_a3_equivalent_comparator_resource_refutes(fen, best, actual, comparator, kind) -> None:
    result = scenario(fen, "c3e4", best, actual, comparator).explain()
    cause = by_kind(result, kind)
    assert cause.status is S.REFUTED
    assert cause.comparator_has_equivalent_resource is True


def test_a3_equivalent_comparator_fork_refutes() -> None:
    result = scenario(
        FORK,
        "d3e4",
        "d3f5",
        (("b4c2", "e1d2", "c2a1", "e4d3", "e8e7"), cp(-500)),
        (("b4c2", "e1d2", "c2a1", "f5e4", "e8e7"), cp(-400)),
    ).explain()
    cause = by_kind(result, Kind.FORK_ALLOWED)
    assert cause.status is S.REFUTED
    assert cause.comparator_has_equivalent_resource is True


def test_a4_positional_loss_outside_vocabulary_is_inconclusive_without_causes() -> None:
    s = scenario(
        KNIGHT,
        "e1d1",
        "e1d2",
        (("e8e7", "d1d2", "e7e6"), cp(-200)),
        (("e8e7", "c3b5", "e7e6"), cp(0)),
    )
    context = s.context()
    assert context.comparator_strictly_better is True

    result = s.explain()
    assert result.status is Agg.INCONCLUSIVE
    assert result.causes == ()


def test_a5_unmappable_actual_hanging_piece_fails_closed() -> None:
    ghost = candidate(TK.HANGING_PIECE, [PieceRef(B, P, "d5")], [PieceRef(W, Q, "h5")])
    s = knight_taken(inject={after(KNIGHT, "c3e4").position_id: (ghost,)})
    with pytest.raises(IncompatibleBadMoveContextError):
        s.explain()


def test_a5_unmappable_fork_actor_fails_closed() -> None:
    ghost = candidate(TK.FORK, [PieceRef(B, N, "f6")], [PieceRef(W, K, "e1"), PieceRef(W, R, "a1")])
    s = fork_scenario(inject={after(FORK, "d3e4", "b4c2").position_id: (ghost,)})
    with pytest.raises(IncompatibleBadMoveContextError, match="outside the branch identity"):
        s.explain()


def test_a5_unmappable_comparator_exposure_fails_closed() -> None:
    ghost = candidate(TK.HANGING_PIECE, [PieceRef(W, K, "d2")], [PieceRef(W, Q, "h5")])
    s = knight_taken(inject={after(KNIGHT, "c3b5", "e8d7", "e1d2").position_id: (ghost,)})
    with pytest.raises(IncompatibleBadMoveContextError):
        s.explain()


@pytest.mark.parametrize("gate_score", [cp(0), cp(-300)], ids=["gate-false", "gate-true"])
def test_a5_unmappable_piece_fails_closed_whatever_the_score_gate(gate_score) -> None:
    # Incompatible input is decided before the P7 score gate (design §14 decision order).
    ghost = candidate(TK.HANGING_PIECE, [PieceRef(B, P, "d5")], [PieceRef(W, Q, "h5")])
    s = scenario(
        KNIGHT,
        "c3e4",
        "c3b5",
        (KNIGHT_TAKEN[0], gate_score),
        KNIGHT_QUIET,
        inject={after(KNIGHT, "c3e4").position_id: (ghost,)},
    )
    with pytest.raises(IncompatibleBadMoveContextError):
        s.explain()


def test_a6_strictly_better_different_comparator_alone_is_no_cause() -> None:
    # The comparator even claims a forced mate; the played king move allows nothing concrete.
    s = scenario(
        KNIGHT,
        "e1d1",
        "c3d5",
        (("e8e7", "d1d2", "e7e6"), cp(-50)),
        (("e8d7", "e1d2", "d7c6"), mate(W, 9)),
    )
    context = s.context()
    assert context.prepared.comparator_move.uci != context.prepared.played_move.uci
    assert context.comparator_strictly_better is True

    result = s.explain()
    assert result.status is Agg.INCONCLUSIVE
    assert result.causes == ()


def test_a7_punishment_illegal_after_comparator_but_other_uci_wins_same_piece() -> None:
    s = a7_scenario()
    context = s.context()
    lines = s.explainer.replay_lines(context)

    assert context.punishment_move.uci == "d5e4"
    assert context.same_punishment_legal_after_comparator is False
    assert context.batch_b is None
    # The comparator's own refutation wins the same physical knight with another UCI ...
    (taken,) = [s for s in lines.comparator.plies if s.delta.capture is not None][:1]
    assert taken.move.uci == "a6b5" != context.punishment_move.uci
    assert taken.before_identity.base_ref_for(taken.delta.capture.captured) == KNIGHT_C3
    # ... although the knight was never hanging there (b5 is defended by the f1 bishop).
    assert not any(has_candidate(p, TK.HANGING_PIECE, KNIGHT_C3) for p in lines.comparator.plies)

    cause = by_kind(s.explain(), Kind.NEWLY_HANGING_PIECE)
    assert cause.same_punishment_legal_after_comparator is False
    assert cause.status is S.REFUTED
    assert cause.comparator_has_equivalent_resource is True


def test_a8_same_uci_capturing_a_different_physical_piece_is_not_the_same_resource() -> None:
    s = a8_scenario()
    context = s.context()
    lines = s.explainer.replay_lines(context)
    actual_take, same_take = lines.actual.plies[1], lines.same_punishment.plies[1]

    assert context.same_punishment_legal_after_comparator is True
    assert actual_take.move.uci == same_take.move.uci == "d5e4"
    assert actual_take.delta.capture.captured.square == same_take.delta.capture.captured.square
    actual_victim = actual_take.before_identity.base_ref_for(actual_take.delta.capture.captured)
    same_victim = same_take.before_identity.base_ref_for(same_take.delta.capture.captured)
    assert actual_victim == KNIGHT_C3
    assert same_victim == base(W, P, "e3")
    # The forced same-UCI line is itself a completed stable deficit, so only identity separates it.
    assert material_evidence(lines.same_punishment, context.prepared.base_facts, W).stable_deficit

    result = s.explain()
    hanging = by_kind(result, Kind.NEWLY_HANGING_PIECE)
    assert hanging.subject == (KNIGHT_C3,)
    assert hanging.status is S.SUPPORTED
    assert hanging.comparator_has_equivalent_resource is False


def test_a8_same_uci_different_piece_can_still_refute_by_value() -> None:
    # MATERIAL_LOSS_LINE compares value, not identity: the forced d5xe4 wins only the e4 pawn
    # (100 < 320), so the material cause stays supported on completed evidence.
    material = by_kind(a8_scenario().explain(), Kind.MATERIAL_LOSS_LINE)
    assert material.material_evidence[2].stable_deficit == 100
    assert material.status is S.SUPPORTED


def test_a9_actual_line_truncated_mid_exchange_is_inconclusive() -> None:
    s = scenario(KNIGHT_ROOK, "c3e4", "c3b5", (("d5e4", "h1h8", "e8d7"), cp(-300)), KNIGHT_QUIET)
    result = s.explain()
    actual = by_kind(result, Kind.MATERIAL_LOSS_LINE).material_evidence[0]
    assert actual.stable_at_ply is None
    for kind in (Kind.NEWLY_HANGING_PIECE, Kind.MATERIAL_LOSS_LINE):
        assert by_kind(result, kind).status is S.INCONCLUSIVE
    assert result.status is Agg.INCONCLUSIVE


def test_a10_stalemate_before_stability_is_inconclusive() -> None:
    # Capture on ply 2, stable point would be ply 4, but ply 4 is already stalemate.
    s = scenario(
        STALEMATE_EARLY,
        "e4g5",
        "e4c5",
        (("g8g5", "h3h4", "g5g6"), cp(-300)),
        (("g8g7", "h3h4", "g7g6"), cp(0)),
        (("g8g5", "h3h4", "g5g6"), cp(0)),
    )
    lines = s.lines()
    assert lines.actual.ends_in_stalemate and lines.actual.final.ply == 4

    result = s.explain()
    material = by_kind(result, Kind.MATERIAL_LOSS_LINE)
    assert material.material_evidence[0].material_delta == -320
    assert material.material_evidence[0].stable_at_ply is None
    assert material.status is S.INCONCLUSIVE
    assert by_kind(result, Kind.NEWLY_HANGING_PIECE).status is S.INCONCLUSIVE


def test_a10_stability_reached_before_a_later_stalemate_stays_valid() -> None:
    s = scenario(
        STALEMATE_LATE,
        "e4g5",
        "e4c5",
        (("g8g5", "h2h3", "g5g6", "h3h4", "g6g7"), cp(-300)),
        (("g8g7", "h2h3", "g7g6"), cp(0)),
        STALEMATE_SAME,
    )
    lines = s.lines()
    assert lines.actual.ends_in_stalemate and lines.actual.final.ply == 6

    result = s.explain()
    material = by_kind(result, Kind.MATERIAL_LOSS_LINE)
    assert material.material_evidence[0].stable_at_ply == 4
    assert material.material_evidence[0].stable_deficit == 320
    assert material.status is S.SUPPORTED


@pytest.mark.parametrize(
    ("fen", "comparator_deficit"),
    [(KNIGHT_G4, 320), (BISHOP_G4, 330)],
    ids=["equal-value", "greater-value"],
)
def test_a11_comparator_losing_a_different_piece_of_at_least_equal_value_refutes(
    fen, comparator_deficit
) -> None:
    s = scenario(
        fen,
        "c3e4",
        "c3b5",
        (("d5e4", "e1d2", "e8f7"), cp(-300)),
        (("h5g4", "e1d2", "e8f7"), cp(-250)),
    )
    lines = s.lines()
    lost = lines.comparator.plies[1]
    assert lost.before_identity.base_ref_for(lost.delta.capture.captured).base_square == "g4"

    result = s.explain()
    material = by_kind(result, Kind.MATERIAL_LOSS_LINE)
    assert material.material_evidence[0].stable_deficit == 320
    assert material.material_evidence[1].stable_deficit == comparator_deficit
    assert material.status is S.REFUTED
    assert material.comparator_has_equivalent_resource is True
    # Value equivalence is not identity equivalence: the c3 knight itself stays supported.
    assert by_kind(result, Kind.NEWLY_HANGING_PIECE).status is S.SUPPORTED


def test_a12_score_gate_false_suppresses_otherwise_supported_causes() -> None:
    s = scenario(KNIGHT, "c3e4", "c3b5", (KNIGHT_TAKEN[0], cp(0)), KNIGHT_QUIET)
    context = s.context()
    assert context.comparator_strictly_better is False

    result = s.explainer.evaluate_causes(context)
    assert result.status is Agg.INCONCLUSIVE
    assert result.causes == ()

    opened = s.explainer.evaluate_causes(replace(context, comparator_strictly_better=True))
    assert opened.status is Agg.SUPPORTED


def test_a12_score_gate_none_suppresses_causes() -> None:
    s = scenario(QUEEN_KNIGHT_PAWNS, "e7g8", "f1f7", QUEEN_KNIGHT_TAKEN)
    context = s.context()
    assert context.comparator_refutation.terminal == TerminalOutcome(TerminalKind.STALEMATE, None)
    assert context.comparator_strictly_better is None

    result = s.explainer.evaluate_causes(context)
    assert result.status is Agg.INCONCLUSIVE
    assert result.causes == ()

    opened = s.explainer.evaluate_causes(replace(context, comparator_strictly_better=True))
    assert Kind.NEWLY_HANGING_PIECE in kinds(opened)


def test_a13_actual_stalemate_branch_invents_no_punishment() -> None:
    s = scenario(QUEEN, "f1f7", "f1f8")
    context = s.context()
    assert context.actual_refutation.terminal == TerminalOutcome(TerminalKind.STALEMATE, None)
    assert context.punishment_move is None and context.actual_punishment is None
    assert len(s.explainer.replay_lines(context).actual.plies) == 1

    result = s.explain()
    assert result.status is Agg.INCONCLUSIVE and result.causes == ()
    assert s.engine.calls == []


def test_a13_actual_checkmate_branch_is_never_worse_than_its_comparator() -> None:
    s = scenario(QUEEN, "f1f8", "f1f2", comparator=(("h8g8", "f2f7", "g8h8"), cp(500)))
    context = s.context()
    assert context.actual_refutation.terminal == TerminalOutcome(TerminalKind.CHECKMATE, W)
    assert context.punishment_move is None
    assert context.comparator_strictly_better is False

    result = s.explain()
    assert result.status is Agg.INCONCLUSIVE and result.causes == ()


def test_a13_terminal_comparator_checkmate_is_a_completed_clean_comparator() -> None:
    s = scenario(QUEEN_KNIGHT, "e7g8", "f1f8", QUEEN_KNIGHT_TAKEN)
    context = s.context()
    lines = s.explainer.replay_lines(context)
    assert context.comparator_refutation.terminal == TerminalOutcome(TerminalKind.CHECKMATE, W)
    assert len(lines.comparator.plies) == 1
    assert context.same_punishment_legal_after_comparator is False
    assert context.probe_count == 2

    result = s.explain()
    cause = by_kind(result, Kind.NEWLY_HANGING_PIECE)
    assert cause.material_evidence[1].terminal_checkmate is True
    assert cause.status is S.SUPPORTED
    assert cause.comparator_has_equivalent_resource is False


def on_call(n, change):
    def tamper(call, batch):
        return change(batch) if call == n else batch

    return tamper


def with_result(index, change):
    def apply(batch: CounterfactualBatchResult) -> CounterfactualBatchResult:
        results = list(batch.results)
        results[index] = change(results[index])
        return replace(batch, results=tuple(results))

    return apply


def probe_field(index, **changes):
    return with_result(index, lambda r: replace(r, probe=replace(r.probe, **changes)))


def moved_to(position):
    def change(result):
        analysis = replace(result.engine_analysis, position_id=position.position_id)
        return replace(result, analysis_position=position, engine_analysis=analysis)

    return change


A14_BATCH_A = [
    (lambda b: replace(b, settings=OTHER_SETTINGS), "different settings"),
    (lambda b: replace(b, results=b.results[::-1]), "echo the requested probe"),
    (probe_field(0, kind=ProbeKind.ALTERNATIVE_MOVE), "echo the requested probe"),
    (probe_field(1, intervention_move=ChessMove("c3a4")), "echo the requested probe"),
    (probe_field(0, execution_move=ChessMove("d5e4")), "echo the requested probe"),
    (with_result(0, moved_to(after(KNIGHT, "c3a4"))), "analysed a different position"),
    (
        with_result(
            1, lambda r: replace(r, engine_analysis=replace(r.engine_analysis, engine=FAKE2))
        ),
        "within one P7 batch",
    ),
]
A14_BATCH_B = [
    (lambda b: replace(b, settings=OTHER_SETTINGS), "different settings"),
    (probe_field(0, intervention_move=ChessMove("g1h1")), "echo the requested probe"),
    (probe_field(0, execution_move=ChessMove("e8e7")), "echo the requested probe"),
    (with_result(0, moved_to(after(TWO_DEFENDERS, "g1h1"))), "analysed a different position"),
]


@pytest.mark.parametrize(("change", "message"), A14_BATCH_A)
def test_a14_malformed_batch_a_fails_closed_through_explain(change, message) -> None:
    s = knight_taken(tamper=on_call(1, change))
    with pytest.raises(IncompatibleBadMoveContextError, match=message):
        s.explain()


@pytest.mark.parametrize(("change", "message"), A14_BATCH_B)
def test_a14_malformed_batch_b_fails_closed_through_explain(change, message) -> None:
    s = removed_defenders_scenario()
    s.p7.tamper = on_call(2, change)
    with pytest.raises(IncompatibleBadMoveContextError, match=message):
        s.explain()


def test_a14_cross_batch_engine_identity_fails_closed_through_explain() -> None:
    s = removed_defenders_scenario()
    s.engine.identity_for_call = lambda call: FAKE if call < 3 else FAKE2
    with pytest.raises(IncompatibleBadMoveContextError, match="across P7 batches"):
        s.explain()


# =============================================================================================
# Physical identity attacks
# =============================================================================================


def test_same_destination_square_from_different_base_pieces_never_normalizes_equal() -> None:
    position = rules.position_from_fen(TWO_KNIGHTS)
    s = scenario(TWO_KNIGHTS, "c3e4", "g5e4")
    prepared = s.explainer.prepare(position, ChessMove("c3e4"), s.judgement)
    on_e4 = PieceRef(W, N, "e4")
    hanging = candidate(TK.HANGING_PIECE, [PieceRef(B, K, "e8")], [on_e4])

    assert on_e4 in prepared.actual.identity.live_pieces
    assert on_e4 in prepared.comparator.identity.live_pieces
    assert prepared.actual.identity.base_ref_for(on_e4) == KNIGHT_C3
    assert prepared.comparator.identity.base_ref_for(on_e4) == base(W, N, "g5")
    assert fingerprint(hanging, prepared.actual.identity) != fingerprint(
        hanging, prepared.comparator.identity
    )


def test_promoted_queen_never_equals_an_original_queen_on_the_same_square() -> None:
    s = scenario(
        QUEENS,
        "g1f2",
        "g1g2",
        (("b2b1q", "f2e3", "e8d8"), cp(-900)),
        (("h7b1", "g2f2", "e8d8"), cp(0)),
    )
    lines = s.lines()
    on_b1 = PieceRef(B, Q, "b1")
    promoted = normalize_piece(on_b1, lines.actual.plies[1].identity)
    original = normalize_piece(on_b1, lines.comparator.plies[1].identity)

    assert promoted == (base(B, P, "b2"), Q)
    assert original == (base(B, Q, "h7"), Q)
    assert promoted != original


def test_piece_captured_on_one_branch_only_is_not_resurrected() -> None:
    s = knight_taken()
    lines = s.lines()
    dead = PieceRef(W, N, "e4")
    after_capture = lines.actual.plies[2]

    assert lines.comparator.final.identity.current_piece(KNIGHT_C3) == PieceRef(W, N, "b5")
    assert lines.actual.final.identity.current_piece(KNIGHT_C3) is None
    with pytest.raises(IncompatibleBadMoveContextError, match="outside the branch identity"):
        normalize_piece(dead, after_capture.identity)
    # Even with a before-identity, a ply that captured nothing cannot resolve it.
    with pytest.raises(IncompatibleBadMoveContextError, match="outside the branch identity"):
        normalize_piece(dead, after_capture.identity, before_identity=after_capture.before_identity)


def test_removal_related_fallback_holds_only_on_the_exact_capture_step() -> None:
    s = scenario(
        "3rk3/8/8/8/3N4/2P5/1b6/4K3 w - - 0 1",
        "e1d1",
        "e1f1",
        (("b2c3", "d1e2", "e8e7"), cp(-150)),
        (("e8e7", "f1e2", "e7f7"), cp(0)),
    )
    lines = s.lines()
    capture, later = lines.actual.plies[1], lines.actual.plies[2]
    (removal,) = [c for c in capture.detection.candidates if c.kind is TK.REMOVAL_OF_DEFENDER]

    def at(step):
        taken = step.delta.capture
        return fingerprint(
            removal,
            step.identity,
            before_identity=step.before_identity,
            captured=taken.captured if taken is not None else None,
        )

    assert at(capture)[3] == ((base(W, P, "c3"), P),)
    # One ply later the bishop and knight still stand, but the c3 pawn is gone for good.
    shifted = replace(removal, actors=(PieceRef(B, Bi, "c3"),))
    with pytest.raises(IncompatibleBadMoveContextError, match="outside the branch identity"):
        fingerprint(shifted, later.identity, before_identity=later.before_identity)


# =============================================================================================
# Tactical fingerprint semantics
# =============================================================================================


def fork_step():
    step = fork_scenario().lines().actual.plies[1]
    (fork,) = [c for c in step.detection.candidates if c.kind is TK.FORK]
    return step, fork


def test_fork_response_ucis_do_not_change_the_generic_fingerprint() -> None:
    step, fork = fork_step()
    first = replace(fork, responses=(ChessMove("e1d2"),))
    second = replace(fork, responses=(ChessMove("e1f1"),))
    assert fingerprint(first, step.identity) == fingerprint(second, step.identity)


def test_promoted_role_is_part_of_the_fingerprint() -> None:
    s = scenario(
        PROMOTION,
        "h1h7",
        "e1d2",
        (("a2a1q", "e1d2", "e8f8"), cp(-800)),
        (("a2a1r", "d2e3", "e8f8"), cp(0)),
        PROMOTION_SAME,
    )
    lines = s.lines()
    as_queen = candidate(TK.HANGING_PIECE, [PieceRef(B, Q, "a1")], [PieceRef(W, R, "h7")])
    as_rook = candidate(TK.HANGING_PIECE, [PieceRef(B, R, "a1")], [PieceRef(W, R, "h1")])

    queen_print = fingerprint(as_queen, lines.actual.plies[1].identity)
    rook_print = fingerprint(as_rook, lines.comparator.plies[1].identity)
    assert queen_print[1] == ((base(B, P, "a2"), Q),)
    assert rook_print[1] == ((base(B, P, "a2"), R),)
    assert queen_print[2] == rook_print[2] == ((base(W, R, "h1"), R),)
    assert queen_print != rook_print


def test_fork_actor_identity_is_part_of_the_fingerprint() -> None:
    step, fork = fork_step()
    other_actor = replace(fork, actors=(PieceRef(B, K, "e8"),))
    assert fingerprint(fork, step.identity)[2] == fingerprint(other_actor, step.identity)[2]
    assert fingerprint(fork, step.identity) != fingerprint(other_actor, step.identity)


def test_fork_target_set_is_part_of_the_fingerprint() -> None:
    step, fork = fork_step()
    other_targets = replace(fork, targets=(PieceRef(W, K, "e1"), PieceRef(W, Bi, "e4")))
    assert fingerprint(fork, step.identity)[1] == fingerprint(other_targets, step.identity)[1]
    assert fingerprint(fork, step.identity) != fingerprint(other_targets, step.identity)


def test_hanging_exposure_is_equivalent_whoever_attacks_it() -> None:
    s = scenario(KNIGHT_BISHOP, "c3e4", "c3a4", BISHOP_TAKEN, (("e8e7", "e1d2", "e7e6"), cp(-10)))
    lines = s.lines()
    (actual,) = [
        c for c in lines.actual.plies[0].detection.candidates if c.kind is TK.HANGING_PIECE
    ]
    (other,) = [
        c for c in lines.comparator.plies[0].detection.candidates if c.kind is TK.HANGING_PIECE
    ]
    assert actual.actors != other.actors
    # Generic fingerprints differ through the attacker ...
    assert fingerprint(actual, lines.actual.plies[0].identity) != fingerprint(
        other, lines.comparator.plies[0].identity
    )

    # ... but NEWLY_HANGING_PIECE deliberately compares only the exposed physical subject.
    cause = by_kind(s.explain(), Kind.NEWLY_HANGING_PIECE)
    assert cause.status is S.REFUTED
    assert cause.comparator_has_equivalent_resource is True
    assert other in cause.tactical_candidates


# =============================================================================================
# Grouping
# =============================================================================================


def test_removed_defenders_of_one_subject_group_into_one_cause() -> None:
    s = removed_defenders_scenario()
    removed = s.context().prepared.actual.delta.removed_defenses
    assert {(c.defender.square, c.defended.square) for c in removed} >= {
        ("e2", "d4"),
        ("b2", "d4"),
    }

    result = s.explain()
    (cause,) = [c for c in result.causes if c.kind is Kind.REMOVED_DEFENDER]
    assert cause.subject == (base(W, N, "d4"),)
    assert cause.affected_pieces == (base(W, Bi, "b2"), base(W, N, "e2"))
    assert cause.status is S.SUPPORTED
    keys = [(c.kind, c.subject) for c in result.causes]
    assert len(keys) == len(set(keys))


def test_removed_defence_of_the_own_king_is_never_a_candidate() -> None:
    s = scenario(
        KING_DEFENDER,
        "d3c5",
        "d3f4",
        (("e8d8", "e1d2", "d8c8"), cp(-100)),
        (("e8d8", "e1d2", "d8e8"), cp(0)),
        (("e8d8", "e1d2", "d8e8"), cp(0)),
    )
    (removed,) = s.context().prepared.actual.delta.removed_defenses
    assert removed.defended == PieceRef(W, K, "e1")

    result = s.explain()
    assert Kind.REMOVED_DEFENDER not in kinds(result)
    assert result.causes == ()


def test_repeated_identical_fork_groups_into_one_cause() -> None:
    # Re-detected after Kd2: same knight, same king and rook, now normalized from new squares.
    again = candidate(TK.FORK, [PieceRef(B, N, "c2")], [PieceRef(W, K, "d2"), PieceRef(W, R, "a1")])
    s = fork_scenario(inject={after(FORK, "d3e4", "b4c2", "e1d2").position_id: (again,)})

    result = s.explain()
    (cause,) = [c for c in result.causes if c.kind is Kind.FORK_ALLOWED]
    assert cause.subject == (base(W, R, "a1"), base(W, K, "e1"), base(B, N, "b4"))
    assert again in cause.tactical_candidates and len(cause.tactical_candidates) == 2
    assert cause.status is S.SUPPORTED


def test_distinct_forks_give_distinct_causes_in_subject_order() -> None:
    # Injected first, but its subject (a1, d3, b4) sorts after the natural fork (a1, e1, b4).
    rook_bishop = candidate(
        TK.FORK, [PieceRef(B, N, "c2")], [PieceRef(W, R, "a1"), PieceRef(W, Bi, "e4")]
    )
    s = fork_scenario(inject={after(FORK, "d3e4", "b4c2").position_id: (rook_bishop,)})

    forks = [c for c in s.explain().causes if c.kind is Kind.FORK_ALLOWED]
    assert [c.subject for c in forks] == [
        (base(W, R, "a1"), base(W, K, "e1"), base(B, N, "b4")),
        (base(W, R, "a1"), base(W, Bi, "d3"), base(B, N, "b4")),
    ]


# =============================================================================================
# Aggregation, ordering, determinism
# =============================================================================================


def back_rank_c8():
    return scenario(
        BACK_RANK_C8,
        "d1d7",
        "h2h3",
        (("c8d7",), mate(B, 3)),
        (("g8f8", "g1h2", "f8e7"), cp(0)),
        (("c8d7", "g1h2", "g8f8"), cp(0)),
    )


@pytest.mark.parametrize(
    ("make", "statuses", "expected"),
    [
        (
            lambda: scenario(
                KNIGHT_G4,
                "c3e4",
                "c3b5",
                (("d5e4", "e1d2", "e8f7"), cp(-300)),
                (("h5g4", "e1d2", "e8f7"), cp(-250)),
            ),
            {Kind.NEWLY_HANGING_PIECE: S.SUPPORTED, Kind.MATERIAL_LOSS_LINE: S.REFUTED},
            Agg.SUPPORTED,
        ),
        (
            back_rank_c8,
            {
                Kind.NEWLY_HANGING_PIECE: S.INCONCLUSIVE,
                Kind.MATE_ALLOWED: S.SUPPORTED,
                Kind.MATERIAL_LOSS_LINE: S.INCONCLUSIVE,
            },
            Agg.SUPPORTED,
        ),
        (
            lambda: scenario(
                KNIGHT_BISHOP, "c3e4", "c3a4", BISHOP_TAKEN, (("d7a4", "e1d2", "e8e7"), cp(-250))
            ),
            {Kind.NEWLY_HANGING_PIECE: S.REFUTED, Kind.MATERIAL_LOSS_LINE: S.REFUTED},
            Agg.REFUTED,
        ),
        (
            lambda: scenario(
                DEFENDER_TWICE,
                "c3c4",
                "d1a1",
                (("d8d4", "e1e2", "d4d5"), cp(-300)),
                (("e8e7", "e1e2", "e7f7"), cp(0)),
            ),
            {Kind.REMOVED_DEFENDER: S.REFUTED, Kind.MATERIAL_LOSS_LINE: S.INCONCLUSIVE},
            Agg.INCONCLUSIVE,
        ),
        (
            lambda: scenario(KNIGHT, "c3e4", "c3b5", (("d5e4",), cp(-300)), KNIGHT_QUIET),
            {Kind.NEWLY_HANGING_PIECE: S.INCONCLUSIVE, Kind.MATERIAL_LOSS_LINE: S.INCONCLUSIVE},
            Agg.INCONCLUSIVE,
        ),
        (
            lambda: scenario(
                KNIGHT,
                "e1d1",
                "e1d2",
                (("e8e7", "d1d2", "e7e6"), cp(-200)),
                (("e8e7", "c3b5", "e7e6"), cp(0)),
            ),
            {},
            Agg.INCONCLUSIVE,
        ),
    ],
    ids=[
        "supported+refuted",
        "supported+inconclusive",
        "refuted+refuted",
        "refuted+inconclusive",
        "only-inconclusive",
        "no-candidates",
    ],
)
def test_aggregate_policy_over_real_evaluated_causes(make, statuses, expected) -> None:
    s = make()
    original = copy.deepcopy(s.judgement)
    result = s.explain()
    found = {c.kind: c.status for c in result.causes}
    for kind, status in statuses.items():
        assert found[kind] is status
    assert set(statuses) <= set(found)
    assert result.status is expected
    # REFUTED or not, the P2 judgement is untouched.
    assert s.judgement == original
    assert s.judgement.quality is MoveQuality.BLUNDER


def test_causes_follow_declaration_order_not_alphabetical_order() -> None:
    result = removed_defenders_scenario().explain()
    assert kinds(result) == [
        Kind.NEWLY_HANGING_PIECE,
        Kind.REMOVED_DEFENDER,
        Kind.MATERIAL_LOSS_LINE,
    ]
    assert kinds(result) != sorted(kinds(result), key=lambda k: k.value)


def test_identical_evidence_gives_identical_results() -> None:
    s = removed_defenders_scenario()
    context = s.context()
    first = s.explainer.evaluate_causes(context)
    assert s.explainer.evaluate_causes(context) == first
    assert removed_defenders_scenario().explain() == first


# =============================================================================================
# D1 completeness
# =============================================================================================


def test_d1_completed_actual_without_exploitation_refutes_despite_open_comparator() -> None:
    s = scenario(
        KNIGHT_ROOK, "c3e4", "c3b5", (("e8d7", "e1d2", "d7e6"), cp(-300)), (("h8h1",), cp(-200))
    )
    result = s.explain()
    cause = by_kind(result, Kind.NEWLY_HANGING_PIECE)
    assert cause.material_evidence[1].stable_at_ply is None
    assert cause.status is S.REFUTED
    assert cause.comparator_has_equivalent_resource is None
    assert result.status is Agg.REFUTED


def test_d1_supported_actual_with_open_comparator_is_inconclusive() -> None:
    result = knight_taken(comparator=(("e8d7",), cp(0))).explain()
    for kind in (Kind.NEWLY_HANGING_PIECE, Kind.MATERIAL_LOSS_LINE):
        cause = by_kind(result, kind)
        assert cause.material_evidence[1].stable_at_ply is None
        assert cause.status is S.INCONCLUSIVE
        assert cause.comparator_has_equivalent_resource is None
    assert result.status is Agg.INCONCLUSIVE


def test_d1_open_batch_b_keeps_a_supported_actual_inconclusive() -> None:
    s = a8_scenario(same=(("d5e4",), cp(0)))
    hanging = by_kind(s.explain(), Kind.NEWLY_HANGING_PIECE)
    assert hanging.material_evidence[2].stable_at_ply is None
    assert hanging.status is S.INCONCLUSIVE
    assert hanging.comparator_has_equivalent_resource is None


# =============================================================================================
# Mate
# =============================================================================================


def test_exact_immediate_comparator_check_covers_every_legal_reply() -> None:
    s = scenario(
        BACK_RANK, "d1d7", "d1d2", (("e8e1",), mate(B, 1)), (("g8f8", "g1f1", "f8e7"), cp(0))
    )
    context = s.context()
    replies = [m.uci for m in context.prepared.comparator.rules.legal_moves]
    assert replies.index("e8e1") >= 3  # the only mate is not among the first replies

    cause = by_kind(s.explain(), Kind.MATE_ALLOWED)
    assert cause.mate_evidence_level is MateEvidenceLevel.EXACT_IMMEDIATE
    assert cause.status is S.REFUTED
    assert cause.comparator_has_equivalent_resource is True


def test_exact_immediate_wins_over_engine_mate_with_one_mate_cause() -> None:
    result = scenario(
        BACK_RANK, "d1d7", "h2h3", (("e8e1",), mate(B, 1)), (("g8f8", "g1h2", "f8e7"), cp(0))
    ).explain()
    mates = [c for c in result.causes if c.kind is Kind.MATE_ALLOWED]
    assert len(mates) == 1
    assert mates[0].mate_evidence_level is MateEvidenceLevel.EXACT_IMMEDIATE
    assert mates[0].subject == (base(W, K, "g1"),)


def test_engine_mate_without_exact_ending_stays_engine_line() -> None:
    cause = by_kind(back_rank_c8().explain(), Kind.MATE_ALLOWED)
    assert cause.mate_evidence_level is MateEvidenceLevel.ENGINE_LINE
    assert cause.replayed_pv_ends_in_checkmate is False


# =============================================================================================
# Fork + mate
# =============================================================================================


def test_fork_with_king_target_supported_by_exact_checkmate() -> None:
    s = scenario(SMOTHER, "e1b4", "d1e2", (("e4f2",), mate(B, 1)), SMOTHER_COMPARATOR, SMOTHER_SAME)
    lines = s.lines()
    assert lines.actual.ends_in_checkmate
    assert all(step.delta.capture is None for step in lines.actual.plies)

    result = s.explain()
    fork = by_kind(result, Kind.FORK_ALLOWED)
    assert base(W, K, "h1") in fork.subject
    assert fork.material_evidence[0].stable_deficit is None
    assert fork.status is S.SUPPORTED
    assert by_kind(result, Kind.MATE_ALLOWED).mate_evidence_level is (
        MateEvidenceLevel.EXACT_IMMEDIATE
    )


def test_fork_with_king_target_supported_by_p7_mate_evidence() -> None:
    s = scenario(
        FORK_CHECK,
        "e1b4",
        "d1e2",
        (("e4f2", "h1g1"), mate(B, 3)),
        SMOTHER_COMPARATOR,
        SMOTHER_SAME,
    )
    lines = s.lines()
    assert not lines.actual.ends_in_checkmate
    assert all(step.delta.capture is None for step in lines.actual.plies)

    fork = by_kind(s.explain(), Kind.FORK_ALLOWED)
    assert base(W, K, "h1") in fork.subject
    assert fork.status is S.SUPPORTED


def test_fork_with_king_target_but_no_mate_or_material_is_refuted() -> None:
    s = fork_scenario(("b4c2", "e1d2", "c2b4", "e4d3", "e8e7"))
    fork = by_kind(s.explain(), Kind.FORK_ALLOWED)
    assert base(W, K, "e1") in fork.subject
    assert fork.status is S.REFUTED


# =============================================================================================
# Material stability boundaries and tracing
# =============================================================================================


def material_of(s, line="actual"):
    context = s.context()
    lines = s.explainer.replay_lines(context)
    return material_evidence(getattr(lines, line), context.prepared.base_facts, W)


@pytest.mark.parametrize(
    ("pv", "stable_at"),
    [
        (("d5e4",), None),
        (("d5e4", "e1d2"), None),
        (("d5e4", "e1d2", "e8d7"), 4),
    ],
    ids=["0-further", "1-further", "2-further"],
)
def test_stable_point_needs_two_plies_after_the_last_change(pv, stable_at) -> None:
    evidence = material_of(scenario(KNIGHT, "c3e4", "c3b5", (pv, cp(-300)), KNIGHT_QUIET))
    assert evidence.material_delta == -320
    assert evidence.stable_at_ply == stable_at
    assert evidence.stable_deficit == (320 if stable_at else None)


@pytest.mark.parametrize(
    ("pv", "stable_at"),
    [(("e8d7",), None), (("e8d7", "e1d2"), 3)],
    ids=["1-pv-ply", "2-pv-plies"],
)
def test_unchanged_line_is_measured_from_the_first_move_branch(pv, stable_at) -> None:
    evidence = material_of(knight_taken(comparator=(pv, cp(0))), "comparator")
    assert evidence.material_delta == 0
    assert evidence.stable_at_ply == stable_at
    assert evidence.stable_deficit is None


def test_checkmate_with_no_material_deficit_is_stable_without_deficit() -> None:
    evidence = material_of(
        scenario(BACK_RANK, "d1d7", "h2h3", (("e8e1",), mate(B, 1)), (("g8f8", "g1h2"), cp(0)))
    )
    assert evidence.terminal_checkmate is True
    assert evidence.material_delta == 0
    assert evidence.stable_at_ply == 2
    assert evidence.stable_deficit is None


def forge(line, index, **changes):
    step = line.plies[index]
    forged = replace(step, delta=replace(step.delta, **changes))
    return replace(line, plies=(*line.plies[:index], forged, *line.plies[index + 1 :]))


def test_claimed_capture_without_material_change_fails_closed() -> None:
    s = knight_taken()
    context = s.context()
    lines = s.explainer.replay_lines(context)
    capture = lines.actual.plies[1].delta.capture
    forged = forge(lines.actual, 2, capture=capture)  # quiet Kd2 claims the d5xe4 capture

    with pytest.raises(IncompatibleBadMoveContextError, match="not traced"):
        material_evidence(forged, context.prepared.base_facts, W)


def test_claimed_promotion_without_material_change_fails_closed() -> None:
    s = scenario(
        PROMOTION,
        "h1h7",
        "e1d2",
        (("a2a1q", "e1d2", "e8f8"), cp(-800)),
        (("e8f8", "h1h8", "f8e7"), cp(0)),
        PROMOTION_SAME,
    )
    context = s.context()
    lines = s.explainer.replay_lines(context)
    promotion = [
        t
        for t in lines.actual.plies[1].delta.transitions
        if t.kind is PieceTransitionKind.PROMOTION
    ]
    assert promotion
    quiet = lines.actual.plies[3]
    forged = forge(lines.actual, 3, transitions=(*quiet.delta.transitions, *promotion))

    with pytest.raises(IncompatibleBadMoveContextError, match="not traced"):
        material_evidence(forged, context.prepared.base_facts, W)


def test_untraced_material_fails_closed_even_when_the_score_gate_is_closed() -> None:
    s = scenario(KNIGHT, "c3e4", "c3b5", (KNIGHT_TAKEN[0], cp(0)), KNIGHT_QUIET)
    context = s.context()
    assert context.comparator_strictly_better is False
    lines = s.explainer.replay_lines(context)
    forged = replace(lines, actual=forge(lines.actual, 1, capture=None))

    with pytest.raises(IncompatibleBadMoveContextError, match="not traced"):
        evaluate_bad_move_causes(context, forged, s.explainer._mates_in_one)


# =============================================================================================
# Black mover symmetry
# =============================================================================================


def test_black_mover_hanging_and_material_mirror_the_white_case() -> None:
    black = scenario(
        BLACK_KNIGHT,
        "c6e5",
        "c6b4",
        (("d4e5", "e8d7", "e1d2"), cp(300)),
        (("e1d2", "e8d7", "d2e3"), cp(0)),
    )
    context = black.context()
    assert context.prepared.base.side_to_move is B
    assert material_advantage(context.prepared.base_facts, B) == 220
    assert context.comparator_strictly_better is True

    result = black.explain()
    white = knight_taken().explain()
    assert [(c.kind, c.status) for c in result.causes] == [(c.kind, c.status) for c in white.causes]
    hanging = by_kind(result, Kind.NEWLY_HANGING_PIECE)
    assert hanging.subject == (base(B, N, "c6"),)
    assert hanging.status is S.SUPPORTED
    material = by_kind(result, Kind.MATERIAL_LOSS_LINE)
    assert material.material_evidence[0].material_delta == -320
    assert material.material_evidence[0].stable_deficit == 320
    assert result.status is Agg.SUPPORTED


def test_black_mover_value_equivalence_is_measured_for_black() -> None:
    result = scenario(
        BLACK_KNIGHT_ROOK,
        "c6e5",
        "c6b4",
        (("d4e5", "e8d7", "e1d2"), cp(300)),
        (("h1h8", "e8d7", "e1d2"), cp(200)),
    ).explain()
    material = by_kind(result, Kind.MATERIAL_LOSS_LINE)
    assert material.material_evidence[1].stable_deficit == 500
    assert material.status is S.REFUTED
    assert material.comparator_has_equivalent_resource is True
    assert by_kind(result, Kind.NEWLY_HANGING_PIECE).status is S.SUPPORTED


# =============================================================================================
# Special moves inside replayed PVs
# =============================================================================================


def test_castling_alias_in_engine_pv_replays_canonically_with_identity() -> None:
    s = scenario(
        CASTLING,
        "c3e4",
        "c3b5",
        (("d5e4", "e1h1", "e8d7"), cp(-300)),
        (("e8d7", "e1g1", "d7e6"), cp(0)),
    )
    lines = s.lines()
    castle = lines.actual.plies[2]
    assert castle.move.uci == "e1g1"
    assert castle.identity.current_piece(base(W, K, "e1")) == PieceRef(W, K, "g1")
    assert castle.identity.current_piece(base(W, R, "h1")) == PieceRef(W, R, "f1")
    assert lines.comparator.plies[2].identity.current_piece(base(W, R, "h1")) == PieceRef(
        W, R, "f1"
    )

    result = s.explain()
    assert by_kind(result, Kind.MATERIAL_LOSS_LINE).material_evidence[0].stable_deficit == 320
    assert result.status is Agg.SUPPORTED


def test_en_passant_maps_the_pawn_captured_on_its_real_square() -> None:
    s = scenario(
        EN_PASSANT,
        "e2e4",
        "e1f2",
        (("d4e3", "e1f1", "e8d7"), cp(-100)),
        (("e8d7", "f2f3", "d7e6"), cp(0)),
    )
    lines = s.lines()
    ep = lines.actual.plies[1]
    assert ep.move.uci == "d4e3"
    assert ep.delta.capture.captured == PieceRef(W, P, "e4")
    assert ep.before_identity.base_ref_for(ep.delta.capture.captured) == base(W, P, "e2")

    material = by_kind(s.explain(), Kind.MATERIAL_LOSS_LINE)
    assert material.subject == (base(W, P, "e2"),)
    assert material.material_evidence[0].stable_deficit == 100
    assert material.status is S.SUPPORTED


def test_opponent_promotion_is_a_material_cause_on_the_base_pawn() -> None:
    s = scenario(
        PROMOTION,
        "h1h7",
        "e1d2",
        (("a2a1q", "e1d2", "e8f8"), cp(-800)),
        (("e8f8", "h1h8", "f8e7"), cp(0)),
        PROMOTION_SAME,
    )
    lines = s.lines()
    assert lines.actual.final.identity.current_piece(base(B, P, "a2")) == PieceRef(B, Q, "a1")

    material = by_kind(s.explain(), Kind.MATERIAL_LOSS_LINE)
    assert material.subject == (base(B, P, "a2"),)
    assert material.material_evidence[0].stable_deficit == 800
    assert material.status is S.SUPPORTED


# =============================================================================================
# Probe budget and production scope
# =============================================================================================


@pytest.mark.parametrize(
    ("make", "status", "probes", "requests"),
    [
        (lambda: knight_taken(quality=MoveQuality.INACCURACY), Agg.NOT_APPLICABLE, 0, 0),
        (knight_taken, Agg.SUPPORTED, 2, 1),
        (
            lambda: scenario(
                KNIGHT,
                "c3e4",
                "c3b5",
                (("e8d7", "e1d2", "d7e6"), cp(-300)),
                KNIGHT_QUIET,
                (("e8d7", "e1d2", "d7e6"), cp(0)),
            ),
            Agg.REFUTED,
            3,
            2,
        ),
        (lambda: knight_taken(comparator=(("e8d7",), cp(0))), Agg.INCONCLUSIVE, 2, 1),
        (removed_defenders_scenario, Agg.SUPPORTED, 3, 2),
    ],
    ids=["not-applicable", "supported-batch-a", "refuted-batch-b", "inconclusive", "batch-b"],
)
def test_probe_budget_end_to_end(make, status, probes, requests) -> None:
    s = make()
    assert s.explain().status is status
    assert (s.p7.probes, len(s.p7.requests)) == (probes, requests)
    assert s.p7.probes <= 3

    if status is Agg.NOT_APPLICABLE:
        assert s.engine.calls == []
        return
    s.p7.requests.clear()
    context = s.context()
    recorded = (len(s.p7.requests), len(s.engine.calls))
    for _ in range(3):
        s.explainer.evaluate_causes(context)
    assert (len(s.p7.requests), len(s.engine.calls)) == recorded
    assert context.probe_count == probes


def calls_named(tree, name):
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == name
    ]


def test_only_the_two_i3_batches_call_p7() -> None:
    explainer_tree = ast.parse(inspect.getsource(BadMoveExplainer))
    assert len(calls_named(explainer_tree, "execute")) == 2
    verify = ast.parse(inspect.getsource(BadMoveExplainer.verify_counterfactuals).strip())
    assert len(calls_named(verify, "execute")) == 2

    for module in (bad_move_causes_module, piece_identity_module):
        tree = ast.parse(inspect.getsource(module))
        assert calls_named(tree, "execute") == []
        assert calls_named(tree, "analyze") == []

    evaluate = ast.parse(inspect.getsource(BadMoveExplainer.evaluate_causes).strip())
    assert calls_named(evaluate, "execute") == []
    assert list(inspect.signature(evaluate_bad_move_causes).parameters) == [
        "context",
        "lines",
        "mates_in_one",
    ]


def test_p8_layer_adds_no_claims_rendering_llm_or_p3_scores() -> None:
    for module in (bad_move_module, bad_move_causes_module, piece_identity_module):
        tree = ast.parse(inspect.getsource(module))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        } | {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        assert not any(
            part in name
            for name in imported
            for part in ("commentary", "render", "llm", "anthropic", "openai", "calliope.engine")
        )
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        assert "ExplanationClaim" not in names
        assert not {"best_score", "played_score", "cp_loss", "expected_score_loss"} & attributes


def test_p8_stays_internal_to_the_public_package() -> None:
    # P8 boundary (design §3): a later integration packet changes this deliberately.
    public = set(getattr(calliope, "__all__", ())) | set(vars(calliope))
    assert not any(name.startswith("BadMove") for name in public)
