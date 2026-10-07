from dataclasses import dataclass, field, replace

import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis import (
    BadMoveCauseKind,
    BadMoveCauseStatus,
    BadMoveExplanationStatus,
    BasePieceRef,
    MateEvidenceLevel,
    TacticalCandidate,
    TacticalCandidateKind,
    TacticalCandidateStatus,
)
from calliope.domain.chess import ChessMove, Color, PieceRef, PieceType
from calliope.domain.engine import (
    EngineAnalysis,
    EngineIdentity,
    EngineLine,
    EngineScore,
    MoveJudgement,
    MoveQuality,
)
from calliope.errors import IncompatibleBadMoveContextError
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.counterfactual.analyzer import DEFAULT_SETTINGS
from calliope.services.explanation import BadMoveExplainer
from calliope.services.explanation.bad_move import BadMovePreparedContext
from calliope.services.explanation.bad_move_causes import (
    PIECE_VALUES,
    aggregate_status,
    fingerprint,
    material_advantage,
    material_evidence,
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

# ---- fixtures (all hand-checked) ------------------------------------------------------------

# Nc3-e4 hangs the knight to d5xe4; Nc3-b5 does not, and d5e4 is then illegal.
KNIGHT = "4k3/8/8/3p4/8/2N5/8/4K3 w - - 0 1"
KNIGHT_SUPPORTED = (("d5e4", "e1d2", "e8d7"), cp(-300))
KNIGHT_QUIET_COMPARATOR = (("e8d7", "e1d2", "d7e6"), cp(0))
# As KNIGHT, plus facing rooks: the comparator line can lose the h1 rook instead.
KNIGHT_ROOK = "4k2r/8/8/3p4/8/2N5/8/4K2R w - - 0 1"
# As KNIGHT, plus a c4 pawn the comparator line can lose instead.
KNIGHT_PAWN = "4k3/8/8/3p4/2P5/2N5/8/4K3 w - - 0 1"
# Nc3-a4 (A) also hangs the knight, to the d7 bishop.
KNIGHT_BISHOP = "4k3/3b4/8/3p4/8/2N5/8/4K3 w - - 0 1"
# The a4 knight is already attacked by the d7 bishop and undefended in the base.
EXPOSED = "4k3/3b4/8/8/N7/8/8/4K3 w - - 0 1"
# c3-c4 removes the pawn's defence of the d4 knight against the d8 rook.
DEFENDER = "3rk3/8/8/8/3N4/2P5/8/4K3 w - - 0 1"
# As DEFENDER plus a d1 rook; A = Rd1-a1 removes another defence of the same knight.
DEFENDER_TWICE = "3rk3/8/8/8/3N4/2P5/8/3RK3 w - - 0 1"
# Bb2xc3 is a P6 removal of defender, but White's own move removed no defence.
CAPTURED_DEFENDER = "3rk3/8/8/8/3N4/2P5/1b6/4K3 w - - 0 1"
# Bd3-e4 abandons c2: Nb4-c2+ forks the e1 king and a1 rook.
FORK = "4k3/8/8/8/1n6/3B4/8/R3K3 w - - 0 1"
# Back rank: Rd1-d7 allows Re8-e1#.
BACK_RANK = "4r1k1/8/8/8/8/8/5PPP/3R2K1 w - - 0 1"
# As BACK_RANK with a bishop on e1, so the mate also wins material.
BACK_RANK_BISHOP = "4r1k1/8/8/8/8/8/5PPP/3RB1K1 w - - 0 1"
# a2-a1=Q promotes for Black.
PROMOTION = "4k3/8/8/8/8/8/p7/4K2R w - - 0 1"
# Ng3 lets Rxg3 stalemate White at once.
STALEMATE = "6r1/8/8/8/8/p7/P1k5/K6N w - - 0 1"
# Qf7 stalemates, Qf8 mates (both terminal, no engine call).
QUEEN = "7k/8/6K1/8/8/8/8/5Q2 w - - 0 1"


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
            engine=EngineIdentity("Fake", "1"),
            settings=settings,
            lines=(EngineLine(1, moves[0], score, moves),),
        )


class RecordingP7:
    def __init__(self, analyzer) -> None:
        self.analyzer = analyzer
        self.requests: list = []

    def execute(self, request):
        self.requests.append(request)
        return self.analyzer.execute(request)


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

    def explain(self):
        return self.explainer.explain(
            self.base, self.judgement.move, self.judgement, DEFAULT_SETTINGS
        )


def scenario(fen, played, best, actual=(), comparator=(), same=None, quality=MoveQuality.BLUNDER):
    """actual/comparator: (PV ucis, White-POV score); same: scripted Batch-B forced line."""

    base = rules.position_from_fen(fen)
    lines = {}
    if actual:
        lines[after(fen, played).position_id] = actual
    if comparator:
        lines[after(fen, best).position_id] = comparator
    forced = {after(fen, best).position_id: same} if same else {}
    engine = LineEngine(lines, forced)
    p7 = RecordingP7(CounterfactualAnalyzer(rules, engine, rules, rules))
    explainer = BadMoveExplainer(rules, facts, deltas, rules, detector, p7)
    return Scenario(explainer, p7, engine, base, judgement(base, played, best, quality))


def explain(*args, **kwargs):
    return scenario(*args, **kwargs).explain()


def by_kind(result, kind):
    (cause,) = [c for c in result.causes if c.kind is kind]
    return cause


def kinds(result):
    return [c.kind for c in result.causes]


def base(color, kind, square):
    return BasePieceRef(color, kind, square)


def knight_supported():
    return scenario(KNIGHT, "c3e4", "c3b5", KNIGHT_SUPPORTED, KNIGHT_QUIET_COMPARATOR)


DEFENDER_SAME = (("d8d4", "c3d4", "e8e7", "e2e3"), cp(0))


def removed_defender(same=DEFENDER_SAME):
    return scenario(
        DEFENDER,
        "c3c4",
        "e1e2",
        (("d8d4", "e1e2", "d4d5"), cp(-300)),
        (("e8e7", "e2e3", "e7f7"), cp(0)),
        same,
    )


FORK_COMPARATOR = (("e8e7", "f1e2", "e7f7"), cp(0))
FORK_SAME = (("b4c2", "d3c2", "e8e7", "f1e2"), cp(0))


# ---- replay ---------------------------------------------------------------------------------


def test_actual_comparator_and_batch_b_pvs_replay_with_identity_at_every_ply() -> None:
    s = removed_defender()
    context = s.context()
    lines = s.explainer.replay_lines(context)
    base_id = context.prepared.base.position_id

    assert [p.ply for p in lines.actual.plies] == [1, 2, 3, 4]
    assert [p.ply for p in lines.comparator.plies] == [1, 2, 3, 4]
    assert [p.ply for p in lines.same_punishment.plies] == [1, 2, 3, 4, 5]
    for line in (lines.actual, lines.comparator, lines.same_punishment):
        for previous, step in zip(line.plies, line.plies[1:], strict=False):
            assert step.before == previous.position
            assert step.before_identity == previous.identity
        for step in line.plies:
            assert step.identity.base_position_id == base_id
            assert step.identity.position_id == step.position.position_id

    rook = base(B, R, "d8")
    assert lines.actual.final.identity.current_piece(rook) == PieceRef(B, R, "d5")
    assert lines.same_punishment.final.identity.current_piece(rook) is None


def test_capture_and_promotion_inside_pv_preserve_base_identity() -> None:
    s = scenario(
        PROMOTION,
        "h1h7",
        "e1d2",
        (("a2a1q", "e1d2", "e8f8"), cp(-800)),
        (("e8f8", "h1h8", "f8e7"), cp(0)),
    )
    lines = s.explainer.replay_lines(s.context())
    pawn = base(B, P, "a2")

    assert lines.actual.plies[1].identity.current_piece(pawn) == PieceRef(B, Q, "a1")
    assert lines.actual.final.identity.base_ref_for(PieceRef(B, Q, "a1")) == pawn

    s2 = knight_supported()
    actual = s2.explainer.replay_lines(s2.context()).actual
    assert actual.final.identity.current_piece(base(W, N, "c3")) is None
    assert actual.final.identity.current_piece(base(B, P, "d5")) == PieceRef(B, P, "e4")


def test_illegal_pv_ply_fails_closed() -> None:
    s = scenario(
        KNIGHT, "c3e4", "c3b5", (("d5e4", "e1e3", "e8d7"), cp(-300)), KNIGHT_QUIET_COMPARATOR
    )
    with pytest.raises(IncompatibleBadMoveContextError, match="engine PV move"):
        s.explain()


def test_replay_must_agree_with_i3_punishment_step() -> None:
    s = knight_supported()
    context = s.context()
    wrong = replace(context.actual_punishment, identity=context.prepared.actual.identity)
    with pytest.raises(IncompatibleBadMoveContextError, match="disagrees with the recorded"):
        s.explainer.evaluate_causes(replace(context, actual_punishment=wrong))


# ---- material -------------------------------------------------------------------------------


def test_fixed_material_values() -> None:
    assert PIECE_VALUES == {P: 100, N: 320, Bi: 330, R: 500, Q: 900}


def test_material_advantage_is_signed_from_the_mover() -> None:
    base_facts = facts.extract(rules.position_from_fen(KNIGHT))
    assert material_advantage(base_facts, W) == 220
    assert material_advantage(base_facts, B) == -220


def material_of(s, line="actual"):
    context = s.context()
    lines = s.explainer.replay_lines(context)
    return material_evidence(
        getattr(lines, line), context.prepared.base_facts, context.prepared.base.side_to_move
    )


def test_capture_is_traced_and_stable_after_two_further_plies() -> None:
    evidence = material_of(knight_supported())
    assert evidence.material_delta == -320
    assert evidence.stable_at_ply == 4
    assert evidence.stable_deficit == 320
    assert not evidence.terminal_checkmate


def test_one_further_ply_is_not_stable() -> None:
    s = scenario(KNIGHT, "c3e4", "c3b5", (("d5e4", "e1d2"), cp(-300)), KNIGHT_QUIET_COMPARATOR)
    evidence = material_of(s)
    assert evidence.material_delta == -320
    assert evidence.stable_at_ply is None
    assert evidence.stable_deficit is None


def test_promotion_is_traced_material_change() -> None:
    s = scenario(
        PROMOTION,
        "h1h7",
        "e1d2",
        (("a2a1q", "e1d2", "e8f8"), cp(-800)),
        (("e8f8", "h1h8", "f8e7"), cp(0)),
    )
    evidence = material_of(s)
    assert evidence.material_delta == -800
    assert evidence.stable_at_ply == 4


def test_exact_checkmate_terminates_a_stable_deficit() -> None:
    s = scenario(
        BACK_RANK_BISHOP,
        "d1d7",
        "h2h3",
        (("e8e1",), mate(B, 1)),
        (("g8f8", "g1h2", "f8e7"), cp(0)),
    )
    evidence = material_of(s)
    assert evidence.material_delta == -330
    assert evidence.stable_at_ply == 2
    assert evidence.terminal_checkmate is True
    assert evidence.stable_deficit == 330


def test_stalemate_before_stability_is_incomplete() -> None:
    s = scenario(STALEMATE, "h1g3", "h1f2", (("g8g3",), cp(0)), (("g8f8", "f2e4", "f8f7"), cp(0)))
    evidence = material_of(s)
    assert evidence.material_delta == -320
    assert evidence.stable_at_ply is None
    assert evidence.terminal_checkmate is False


def test_untraced_material_change_fails_closed() -> None:
    s = knight_supported()
    context = s.context()
    actual = s.explainer.replay_lines(context).actual
    capture_step = actual.plies[1]
    forged = replace(capture_step, delta=replace(capture_step.delta, capture=None))
    line = replace(actual, plies=(actual.plies[0], forged, *actual.plies[2:]))

    with pytest.raises(IncompatibleBadMoveContextError, match="not traced"):
        material_evidence(line, context.prepared.base_facts, W)


# ---- fingerprints ---------------------------------------------------------------------------


def test_same_physical_piece_on_different_squares_normalizes_equal() -> None:
    context = knight_supported().context()
    pawn = PieceRef(B, P, "d5")
    on_e4 = TacticalCandidate(
        TacticalCandidateKind.HANGING_PIECE,
        TacticalCandidateStatus.DETECTED,
        actors=(pawn,),
        targets=(PieceRef(W, N, "e4"),),
    )
    on_b5 = replace(on_e4, targets=(PieceRef(W, N, "b5"),))

    assert fingerprint(on_e4, context.prepared.actual.identity) == fingerprint(
        on_b5, context.prepared.comparator.identity
    )


def test_promoted_piece_keeps_pawn_identity_and_current_role() -> None:
    s = scenario(
        PROMOTION,
        "h1h7",
        "e1d2",
        (("a2a1q", "e1d2", "e8f8"), cp(-800)),
        (("e8f8", "h1h8", "f8e7"), cp(0)),
    )
    step = s.explainer.replay_lines(s.context()).actual.plies[1]
    check = TacticalCandidate(
        TacticalCandidateKind.CHECK,
        TacticalCandidateStatus.DETECTED,
        actors=(PieceRef(B, Q, "a1"),),
        targets=(PieceRef(W, K, "e1"),),
    )

    _, actors, _, _ = fingerprint(check, step.identity)
    assert actors == ((base(B, P, "a2"), Q),)


def test_response_uci_does_not_affect_generic_fingerprint() -> None:
    identity = knight_supported().context().prepared.actual.identity
    first = TacticalCandidate(
        TacticalCandidateKind.FORCED_RESPONSE,
        TacticalCandidateStatus.DETECTED,
        responses=(ChessMove("e8d8"),),
    )
    second = replace(first, responses=(ChessMove("e8f8"),))
    assert fingerprint(first, identity) == fingerprint(second, identity)


def test_unmappable_candidate_piece_fails_closed() -> None:
    identity = knight_supported().context().prepared.actual.identity
    ghost = TacticalCandidate(
        TacticalCandidateKind.HANGING_PIECE,
        TacticalCandidateStatus.DETECTED,
        actors=(PieceRef(B, P, "d5"),),
        targets=(PieceRef(W, Q, "h5"),),
    )
    with pytest.raises(IncompatibleBadMoveContextError, match="outside the branch identity"):
        fingerprint(ghost, identity)


# ---- NEWLY_HANGING_PIECE --------------------------------------------------------------------


def test_newly_hanging_piece_exploited_with_clean_comparator_is_supported() -> None:
    result = knight_supported().explain()
    cause = by_kind(result, Kind.NEWLY_HANGING_PIECE)

    assert result.status is Agg.SUPPORTED
    assert cause.status is S.SUPPORTED
    assert cause.subject == (base(W, N, "c3"),)
    assert cause.comparator_has_equivalent_resource is False
    assert cause.same_punishment_legal_after_comparator is False
    assert cause.punishment_move.uci == "d5e4"
    assert cause.material_evidence[0].stable_deficit == 320


def test_piece_already_exposed_in_base_is_not_newly_hanging() -> None:
    result = explain(
        EXPOSED,
        "e1d1",
        "a4c3",
        (("d7a4", "d1d2", "e8e7"), cp(-300)),
        (("e8e7", "e1d2", "e7e6"), cp(0)),
        # Bd7-a4 is still legal after Nc3, so Batch B runs; script a completed line.
        (("d7a4", "e1d2", "e8e7"), cp(0)),
    )
    assert Kind.NEWLY_HANGING_PIECE not in kinds(result)
    assert by_kind(result, Kind.MATERIAL_LOSS_LINE).status is S.SUPPORTED


def test_hanging_piece_never_captured_on_stable_line_is_refuted() -> None:
    result = explain(
        KNIGHT, "c3e4", "c3b5", (("e8d7", "e1d2", "d7e6"), cp(-300)), KNIGHT_QUIET_COMPARATOR
    )
    assert kinds(result) == [Kind.NEWLY_HANGING_PIECE]
    assert result.causes[0].status is S.REFUTED
    assert result.status is Agg.REFUTED


def test_same_subject_hanging_after_comparator_via_other_attacker_is_refuted() -> None:
    result = explain(
        KNIGHT_BISHOP,
        "c3e4",
        "c3a4",
        (("d5e4", "e1d2", "e8e7"), cp(-300)),
        (("e8e7", "e1d2", "e7e6"), cp(-10)),
    )
    cause = by_kind(result, Kind.NEWLY_HANGING_PIECE)
    assert cause.status is S.REFUTED
    assert cause.comparator_has_equivalent_resource is True


# ---- REMOVED_DEFENDER -----------------------------------------------------------------------


def test_removed_own_defender_exploited_is_supported() -> None:
    result = removed_defender().explain()
    cause = by_kind(result, Kind.REMOVED_DEFENDER)

    assert cause.status is S.SUPPORTED
    assert cause.subject == (base(W, N, "d4"),)
    assert cause.affected_pieces == (base(W, P, "c3"),)
    assert cause.same_punishment_legal_after_comparator is True
    assert cause.comparator_has_equivalent_resource is False
    assert kinds(result) == [
        Kind.NEWLY_HANGING_PIECE,
        Kind.REMOVED_DEFENDER,
        Kind.MATERIAL_LOSS_LINE,
    ]


def test_p6_removal_of_defender_alone_creates_no_cause() -> None:
    s = scenario(
        CAPTURED_DEFENDER,
        "e1d1",
        "e1f1",
        (("b2c3", "d1e2", "e8e7"), cp(-150)),
        (("e8e7", "f1e2", "e7f7"), cp(0)),
    )
    lines = s.explainer.replay_lines(s.context())
    motif = {c.kind for c in lines.actual.plies[1].detection.candidates}
    assert TacticalCandidateKind.REMOVAL_OF_DEFENDER in motif

    assert Kind.REMOVED_DEFENDER not in kinds(s.explain())


def test_comparator_removing_defence_of_same_subject_refutes() -> None:
    result = explain(
        DEFENDER_TWICE,
        "c3c4",
        "d1a1",
        (("d8d4", "e1e2", "d4d5"), cp(-300)),
        (("e8e7", "e1e2", "e7f7"), cp(0)),
    )
    cause = by_kind(result, Kind.REMOVED_DEFENDER)
    assert cause.status is S.REFUTED
    assert cause.comparator_has_equivalent_resource is True
    # Batch B stops mid-exchange, so the value comparison stays open.
    assert by_kind(result, Kind.MATERIAL_LOSS_LINE).status is S.INCONCLUSIVE
    assert result.status is Agg.INCONCLUSIVE


# ---- FORK_ALLOWED ---------------------------------------------------------------------------


def test_fork_with_target_capture_and_stable_deficit_is_supported() -> None:
    result = explain(
        FORK,
        "d3e4",
        "e1f1",
        (("b4c2", "e1d2", "c2a1", "e4d3", "e8e7"), cp(-500)),
        FORK_COMPARATOR,
        FORK_SAME,
    )
    cause = by_kind(result, Kind.FORK_ALLOWED)
    assert cause.status is S.SUPPORTED
    # Ordered by base square: a1, e1, b4.
    assert cause.subject == (base(W, R, "a1"), base(W, K, "e1"), base(B, N, "b4"))
    assert cause.comparator_has_equivalent_resource is False
    assert by_kind(result, Kind.MATERIAL_LOSS_LINE).status is S.SUPPORTED


def test_fork_geometry_without_consequence_is_refuted() -> None:
    result = explain(
        FORK,
        "d3e4",
        "e1f1",
        (("b4c2", "e1d2", "c2b4", "e4d3", "e8e7"), cp(-500)),
        FORK_COMPARATOR,
        FORK_SAME,
    )
    assert by_kind(result, Kind.FORK_ALLOWED).status is S.REFUTED


def test_equivalent_comparator_fork_with_consequence_is_refuted() -> None:
    result = explain(
        FORK,
        "d3e4",
        "d3f5",
        (("b4c2", "e1d2", "c2a1", "e4d3", "e8e7"), cp(-500)),
        (("b4c2", "e1d2", "c2a1", "f5e4", "e8e7"), cp(-400)),
    )
    cause = by_kind(result, Kind.FORK_ALLOWED)
    assert cause.status is S.REFUTED
    assert cause.comparator_has_equivalent_resource is True


# ---- MATE_ALLOWED ---------------------------------------------------------------------------


def test_exact_immediate_mate_with_no_comparator_mate_in_one_is_supported() -> None:
    result = explain(
        BACK_RANK, "d1d7", "h2h3", (("e8e1",), mate(B, 1)), (("g8f8", "g1h2", "f8e7"), cp(0))
    )
    cause = by_kind(result, Kind.MATE_ALLOWED)
    assert cause.status is S.SUPPORTED
    assert cause.subject == (base(W, K, "g1"),)
    assert cause.mate_evidence_level is MateEvidenceLevel.EXACT_IMMEDIATE
    assert cause.replayed_pv_ends_in_checkmate is True
    assert cause.comparator_has_equivalent_resource is False


def test_comparator_mate_in_one_refutes_exact_immediate_mate() -> None:
    result = explain(
        BACK_RANK, "d1d7", "d1d2", (("e8e1",), mate(B, 1)), (("g8f8", "g1f1", "f8e7"), cp(0))
    )
    cause = by_kind(result, Kind.MATE_ALLOWED)
    assert cause.status is S.REFUTED
    assert cause.mate_evidence_level is MateEvidenceLevel.EXACT_IMMEDIATE


ENGINE_MATE = (("g8f8", "d7a7", "e8e1"), mate(B, 2))
QUIET_AFTER_H3 = (("g8f8", "g1h2", "f8e7"), cp(0))


def test_engine_line_mate_ending_in_exact_mate_is_supported() -> None:
    result = explain(BACK_RANK, "d1d7", "h2h3", ENGINE_MATE, QUIET_AFTER_H3)
    cause = by_kind(result, Kind.MATE_ALLOWED)
    assert cause.status is S.SUPPORTED
    assert cause.mate_evidence_level is MateEvidenceLevel.ENGINE_LINE
    assert cause.replayed_pv_ends_in_checkmate is True


def test_engine_line_mate_without_final_mate_keeps_engine_level() -> None:
    result = explain(BACK_RANK, "d1d7", "h2h3", (("g8f8", "d7a7"), mate(B, 2)), QUIET_AFTER_H3)
    cause = by_kind(result, Kind.MATE_ALLOWED)
    assert cause.status is S.SUPPORTED
    assert cause.mate_evidence_level is MateEvidenceLevel.ENGINE_LINE
    assert cause.replayed_pv_ends_in_checkmate is False


def test_same_punishment_still_mating_after_comparator_refutes() -> None:
    result = explain(
        BACK_RANK, "d1d7", "h2h3", ENGINE_MATE, QUIET_AFTER_H3, (("g8f8",), mate(B, 2))
    )
    cause = by_kind(result, Kind.MATE_ALLOWED)
    assert cause.status is S.REFUTED
    assert cause.comparator_has_equivalent_resource is True


# ---- MATERIAL_LOSS_LINE ---------------------------------------------------------------------


def test_material_loss_with_complete_safe_comparator_is_supported() -> None:
    cause = by_kind(knight_supported().explain(), Kind.MATERIAL_LOSS_LINE)
    assert cause.status is S.SUPPORTED
    assert cause.subject == (base(W, N, "c3"),)
    assert cause.comparator_has_equivalent_resource is False


def test_comparator_losing_different_piece_of_greater_value_refutes() -> None:
    result = explain(
        KNIGHT_ROOK,
        "c3e4",
        "c3b5",
        KNIGHT_SUPPORTED,
        (("h8h1", "e1e2", "e8d7"), cp(-200)),
    )
    cause = by_kind(result, Kind.MATERIAL_LOSS_LINE)
    assert cause.status is S.REFUTED
    assert cause.comparator_has_equivalent_resource is True
    assert cause.material_evidence[1].stable_deficit == 500


def test_smaller_comparator_deficit_does_not_refute() -> None:
    result = explain(
        KNIGHT_PAWN, "c3e4", "c3b5", KNIGHT_SUPPORTED, (("d5c4", "e1d2", "e8d7"), cp(-50))
    )
    cause = by_kind(result, Kind.MATERIAL_LOSS_LINE)
    assert cause.material_evidence[1].stable_deficit == 100
    assert cause.status is S.SUPPORTED


def test_truncated_actual_exchange_is_inconclusive() -> None:
    result = explain(KNIGHT, "c3e4", "c3b5", (("d5e4",), cp(-300)), KNIGHT_QUIET_COMPARATOR)
    assert by_kind(result, Kind.MATERIAL_LOSS_LINE).status is S.INCONCLUSIVE
    assert by_kind(result, Kind.NEWLY_HANGING_PIECE).status is S.INCONCLUSIVE
    assert result.status is Agg.INCONCLUSIVE


def test_comparator_truncated_mid_exchange_is_inconclusive() -> None:
    result = explain(KNIGHT_ROOK, "c3e4", "c3b5", KNIGHT_SUPPORTED, (("h8h1",), cp(-200)))
    cause = by_kind(result, Kind.MATERIAL_LOSS_LINE)
    assert cause.material_evidence[1].stable_at_ply is None
    assert cause.status is S.INCONCLUSIVE
    assert cause.comparator_has_equivalent_resource is None
    assert result.status is Agg.INCONCLUSIVE


def test_batch_b_truncated_mid_exchange_is_inconclusive() -> None:
    result = removed_defender(same=(("d8d4",), cp(0))).explain()
    for kind in (Kind.NEWLY_HANGING_PIECE, Kind.REMOVED_DEFENDER, Kind.MATERIAL_LOSS_LINE):
        cause = by_kind(result, kind)
        assert cause.status is S.INCONCLUSIVE
        assert cause.comparator_has_equivalent_resource is None
    assert result.status is Agg.INCONCLUSIVE


# ---- result policy, budget, determinism -----------------------------------------------------


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ((S.SUPPORTED, S.REFUTED), Agg.SUPPORTED),
        ((S.REFUTED, S.REFUTED), Agg.REFUTED),
        ((S.REFUTED, S.INCONCLUSIVE), Agg.INCONCLUSIVE),
        ((), Agg.INCONCLUSIVE),
    ],
)
def test_aggregate_status(statuses, expected) -> None:
    template = by_kind(knight_supported().explain(), Kind.NEWLY_HANGING_PIECE)
    causes = tuple(replace(template, status=status) for status in statuses)
    assert aggregate_status(causes) is expected


def test_score_gate_false_returns_inconclusive_without_causes() -> None:
    result = explain(KNIGHT, "c3e4", "c3b5", (KNIGHT_SUPPORTED[0], cp(0)), KNIGHT_QUIET_COMPARATOR)
    assert result.status is Agg.INCONCLUSIVE
    assert result.causes == ()


def test_score_gate_none_returns_inconclusive_without_causes() -> None:
    s = scenario(QUEEN, "f1f7", "f1f8")
    result = s.explain()
    assert result.status is Agg.INCONCLUSIVE
    assert result.causes == ()
    assert s.engine.calls == []


@pytest.mark.parametrize(
    "quality",
    [MoveQuality.BEST, MoveQuality.EXCELLENT, MoveQuality.GOOD, MoveQuality.INACCURACY],
)
def test_not_applicable_makes_no_p7_call(quality) -> None:
    s = scenario(KNIGHT, "c3e4", "c3b5", quality=quality)
    result = s.explain()
    assert result.status is Agg.NOT_APPLICABLE
    assert result.causes == ()
    assert s.p7.requests == [] and s.engine.calls == []


@pytest.mark.parametrize("make", [knight_supported, removed_defender])
def test_cause_evaluation_adds_no_p7_probe(make) -> None:
    s = make()
    context = s.context()
    requests, calls = len(s.p7.requests), len(s.engine.calls)

    s.explainer.evaluate_causes(context)
    s.explainer.evaluate_causes(context)

    assert (len(s.p7.requests), len(s.engine.calls)) == (requests, calls)
    assert context.probe_count in (2, 3)
    assert sum(len(r.probes) for r in s.p7.requests) == context.probe_count


def test_results_are_deterministic_ordered_and_unique() -> None:
    first = removed_defender().explain()
    second = removed_defender().explain()

    assert first == second
    assert kinds(first) == sorted(kinds(first), key=list(BadMoveCauseKind).index)
    keys = [(c.kind, c.subject) for c in first.causes]
    assert len(keys) == len(set(keys))


# ---- independent-review corrections ---------------------------------------------------------


def capture_step():
    """KNIGHT ply 2: d5xe4 has just captured the white knight on e4."""

    s = knight_supported()
    step = s.explainer.replay_lines(s.context()).actual.plies[1]
    assert step.delta.capture.captured == PieceRef(W, N, "e4")
    return step


def step_print(candidate, step):
    return fingerprint(
        candidate,
        step.identity,
        before_identity=step.before_identity,
        captured=step.delta.capture.captured,
    )


CAPTURED_KNIGHT = PieceRef(W, N, "e4")
E4_PAWN = PieceRef(B, P, "e4")


@pytest.mark.parametrize(
    "malformed",
    [
        # Fork whose actor is the piece that was just captured.
        TacticalCandidate(
            TacticalCandidateKind.FORK,
            TacticalCandidateStatus.DETECTED,
            actors=(CAPTURED_KNIGHT,),
            targets=(PieceRef(B, K, "e8"), E4_PAWN),
        ),
        # Hanging piece whose target is the piece that was just captured.
        TacticalCandidate(
            TacticalCandidateKind.HANGING_PIECE,
            TacticalCandidateStatus.DETECTED,
            actors=(E4_PAWN,),
            targets=(CAPTURED_KNIGHT,),
        ),
        # Non-removal candidate carrying the captured piece as ``related``.
        TacticalCandidate(
            TacticalCandidateKind.HANGING_PIECE,
            TacticalCandidateStatus.DETECTED,
            actors=(PieceRef(W, K, "e1"),),
            targets=(E4_PAWN,),
            related=(CAPTURED_KNIGHT,),
        ),
    ],
    ids=["fork-actor", "hanging-target", "hanging-related"],
)
def test_captured_piece_fallback_rejected_outside_removal_related(malformed) -> None:
    step = capture_step()
    assert step.delta.capture.captured == CAPTURED_KNIGHT

    with pytest.raises(IncompatibleBadMoveContextError, match="outside the branch identity"):
        step_print(malformed, step)


def test_removal_of_defender_may_resolve_only_its_captured_related_piece() -> None:
    s = scenario(
        CAPTURED_DEFENDER,
        "e1d1",
        "e1f1",
        (("b2c3", "d1e2", "e8e7"), cp(-150)),
        (("e8e7", "f1e2", "e7f7"), cp(0)),
    )
    step = s.explainer.replay_lines(s.context()).actual.plies[1]
    (removal,) = [
        c for c in step.detection.candidates if c.kind is TacticalCandidateKind.REMOVAL_OF_DEFENDER
    ]

    _, actors, targets, related = step_print(removal, step)
    assert actors == ((base(B, Bi, "b2"), Bi),)
    assert targets == ((base(W, N, "d4"), N),)
    assert related == ((base(W, P, "c3"), P),)

    # The captured pawn is not resolvable as an actor, even on a removal candidate.
    misplaced = replace(removal, actors=(step.delta.capture.captured,))
    with pytest.raises(IncompatibleBadMoveContextError, match="outside the branch identity"):
        step_print(misplaced, step)


def test_exact_comparator_replay_mate_refutes_engine_line_mate() -> None:
    # After Rd2 the comparator's own line ends Re1#, although its score says centipawns.
    result = explain(BACK_RANK, "d1d7", "d1d2", ENGINE_MATE, (("e8e1",), cp(0)))
    cause = by_kind(result, Kind.MATE_ALLOWED)
    assert cause.mate_evidence_level is MateEvidenceLevel.ENGINE_LINE
    assert cause.status is S.REFUTED
    assert cause.comparator_has_equivalent_resource is True


def test_exact_same_punishment_replay_mate_refutes_engine_line_mate() -> None:
    # Batch B scores centipawns, but its replay ...Kf8 Rd3 Re1# ends in exact mate.
    result = explain(
        BACK_RANK,
        "d1d7",
        "d1d2",
        ENGINE_MATE,
        (("g8f8", "g1f1", "f8e7"), cp(0)),
        (("g8f8", "d2d3", "e8e1"), cp(0)),
    )
    cause = by_kind(result, Kind.MATE_ALLOWED)
    assert cause.same_punishment_legal_after_comparator is True
    assert cause.mate_evidence_level is MateEvidenceLevel.ENGINE_LINE
    assert cause.status is S.REFUTED
    assert cause.comparator_has_equivalent_resource is True


def test_later_hanging_exposure_on_comparator_refutation_refutes() -> None:
    # After Nb5 the knight is safe; ...Kd7, Kd2, Kc6, Ke3 then leaves it en prise to the king.
    s = scenario(
        KNIGHT,
        "c3e4",
        "c3b5",
        KNIGHT_SUPPORTED,
        (("e8d7", "e1d2", "d7c6", "d2e3"), cp(0)),
    )
    lines = s.explainer.replay_lines(s.context())
    knight = base(W, N, "c3")
    hanging = TacticalCandidateKind.HANGING_PIECE

    def exposed(step):
        return any(
            c.kind is hanging and step.identity.base_ref_for(c.targets[0]) == knight
            for c in step.detection.candidates
        )

    assert not exposed(lines.comparator.plies[0])
    assert exposed(lines.comparator.final)

    cause = by_kind(s.explain(), Kind.NEWLY_HANGING_PIECE)
    assert cause.status is S.REFUTED
    assert cause.comparator_has_equivalent_resource is True
