"""P9-I4 full-PV deterministic replay and frozen-P8 material normalization."""

import ast
import inspect
import textwrap
from dataclasses import FrozenInstanceError, fields, replace
from itertools import pairwise

import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis import BasePieceRef, ProbeKind, TacticalCandidateStatus
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
    IncompatibleGoodMoveContextError,
    InvalidUciError,
    NullMoveNotAllowedError,
)
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.explanation import GoodMoveExplainer, bad_move_causes, good_move
from calliope.services.explanation.good_move import (
    GoodMoveAlternativeLineEvidence,
    GoodMoveLineEvidence,
    GoodMoveReplayContext,
    GoodMoveReplayedLineContext,
    GoodMoveReplayStepContext,
)
from calliope.services.explanation.piece_identity import BasePieceIdentityMap
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.tactics import TacticalDetector

rules = PythonChessAdapter()
START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
QUEEN = "7k/8/6K1/8/8/8/8/5Q2 w - - 0 1"
ROOK_TAKES = "4k3/8/8/3n4/8/8/8/3RK3 w - - 0 1"
ROOK_HANGS = "4k3/8/8/3n4/8/8/8/2R1K3 w - - 0 1"
PROMOTE = "1n5k/P7/8/8/8/8/8/K7 w - - 0 1"
CASTLE = "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"
EN_PASSANT = "4k3/3p4/8/4P3/8/8/8/4K3 w - - 0 1"
BLACK_TAKES = "3rk3/8/8/3N4/8/8/8/4K3 b - - 0 1"
SETTINGS = EngineSettings(EngineLimit(time_ms=37), multipv=1, threads=1, hash_mb=16)
IDENTITY = EngineIdentity("Scripted P7", "1")


class Forbidden:
    def __init__(self, label="dependency"):
        self.label = label

    def __getattr__(self, name):
        raise AssertionError(f"I4 accessed forbidden {self.label}: {name}")


class ScriptedEngine:
    """Return a scripted PV per (analysis position, forced root); never validates the suffix."""

    def __init__(self, script):
        self.script = script
        self.calls = []

    def analyze(self, position, settings, root_moves=None):
        self.calls.append((position, settings, root_moves))
        root = root_moves[0].uci if root_moves else None
        ucis = self.script.get((position.position_id, root))
        if ucis is None:
            ucis = (root or rules.observe_tactics(position).legal_moves[0].uci,)
        pv = tuple(ChessMove(u) for u in ucis)
        line = EngineLine(1, pv[0], EngineScore.cp(0), pv)
        return EngineAnalysis(position.position_id, IDENTITY, settings, (line,))


class RecordingP7:
    def __init__(self, engine):
        self.delegate = CounterfactualAnalyzer(rules, engine, rules, rules)
        self.calls = []

    def execute(self, request):
        self.calls.append(request)
        return self.delegate.execute(request)


def scenario(fen, moves, pvs=None, *, response=None, response_pv=None):
    """Real I1-I3 pipeline; ``pvs`` maps a first move to the PV played after it."""
    base = rules.position_from_fen(fen)
    script = {}
    for first, pv in (pvs or {}).items():
        position = rules.apply_move(base, rules.legal_move_from_uci(base, first))
        script[(position.position_id, None)] = tuple(pv)
    if response is not None:
        position = rules.apply_move(base, rules.legal_move_from_uci(base, moves[0]))
        script[(position.position_id, response)] = tuple(response_pv or (response,))
    engine = ScriptedEngine(script)
    p7 = RecordingP7(engine)
    facts = PositionFactExtractor(rules)
    explainer = GoodMoveExplainer(
        rules, facts, BoardDeltaAnalyzer(rules, facts), rules, TacticalDetector(), p7
    )
    lines = tuple(
        EngineLine(i, ChessMove(u), EngineScore.cp(0), (ChessMove(u),))
        for i, u in enumerate(moves, start=1)
    )
    analysis = EngineAnalysis(
        base.position_id, EngineIdentity("P3"), EngineSettings(EngineLimit(depth=4)), lines
    )
    judgement = MoveJudgement(
        base.position_id,
        base.side_to_move,
        ChessMove(moves[0]),
        ChessMove(moves[0]),
        MoveQuality.GOOD,
        1,
        EngineScore.cp(0),
        EngineScore.cp(0),
        0,
        0.0,
    )
    prepared = explainer.prepare(base, judgement.move, judgement, analysis)
    context = explainer.verify_counterfactuals(explainer.build_branches(prepared), SETTINGS)
    if response is not None:
        context = explainer.verify_ignored_response(context, ChessMove(response))
    return explainer, context, p7, engine


def full_start():
    return scenario(
        START,
        ("e2e4", "d2d4", "g1f3"),
        {
            "e2e4": ("e7e5", "g1f3", "b8c6"),
            "d2d4": ("d7d5", "c2c4"),
            "g1f3": ("g8f6", "g2g3", "g7g6", "f1g2"),
        },
        response="d7d5",
        response_pv=("d7d5", "e4d5", "d8d5"),
    )


def single(fen, first, pv=()):
    explainer, context, _, _ = scenario(fen, (first,), {first: pv} if pv else None)
    return explainer.replay_lines(context).played


def ucis(evidence):
    return tuple(step.move.uci for step in evidence.line.plies)


def p8_material(evidence, context):
    return bad_move_causes.material_evidence(
        evidence.line,
        context.deterministic.base_facts,
        context.deterministic.prepared.base.side_to_move,
    )


def assert_chained(evidence, deterministic):
    plies = evidence.line.plies
    base = deterministic.prepared.base
    assert [step.ply for step in plies] == list(range(1, len(plies) + 1))
    assert plies[0].before is base
    assert plies[0].before_identity is deterministic.root_identity
    for previous, step in pairwise(plies):
        assert step.before is previous.position
        assert step.before_identity is previous.identity
    for step in plies:
        assert step.identity.base_position_id == base.position_id
        assert step.identity.position_id == step.position.position_id
        assert step.position.side_to_move is step.before.side_to_move.opposite
        assert step.delta.before_position_id == step.before.position_id
        assert step.delta.after_position_id == step.position.position_id
        assert step.delta.move.uci == step.move.uci == step.detection.move.uci
        assert step.delta.mover is step.before.side_to_move is step.detection.mover
        assert step.facts.position_id == step.rules.position_id == step.position.position_id
        assert all(c.status is TacticalCandidateStatus.DETECTED for c in step.detection.candidates)


# ---- replay ----------------------------------------------------------------------------------


def test_played_alternatives_and_batch_b_replay_full_pvs_in_rank_order():
    explainer, context, _, _ = full_start()
    replay = explainer.replay_lines(context)
    d = context.deterministic
    assert replay.counterfactual is context
    assert ucis(replay.played) == ("e2e4", "e7e5", "g1f3", "b8c6")
    assert [ucis(a.evidence) for a in replay.alternatives] == [
        ("d2d4", "d7d5", "c2c4"),
        ("g1f3", "g8f6", "g2g3", "g7g6", "f1g2"),
    ]
    assert tuple(a.alternative for a in replay.alternatives) == d.prepared.alternatives
    assert [a.alternative.rank for a in replay.alternatives] == [2, 3]
    assert replay.played.line.probe_result is context.played_refutation
    for retained, line in zip(context.alternative_refutations, replay.alternatives, strict=True):
        assert line.evidence.line.probe_result is retained.result
    ignored = replay.ignored_response
    assert ucis(ignored) == ("e2e4", "d7d5", "e4d5", "d8d5")
    assert ignored.line.plies[1].move.uci == context.ignored_response.uci
    assert ignored.line.probe_result is context.ignored_response_result
    assert ignored.material.probe.kind is ProbeKind.IGNORE_THREAT
    assert (ignored.material.material_delta, ignored.material.stable_at_ply) == (0, None)
    for evidence in (replay.played, *(a.evidence for a in replay.alternatives), ignored):
        assert_chained(evidence, d)
    assert (replay.played.material.material_delta, replay.played.material.stable_at_ply) == (0, 3)


def test_first_ply_is_the_exact_retained_i2_branch():
    explainer, context, _, _ = full_start()
    replay = explainer.replay_lines(context)
    d = context.deterministic
    pairs = [(replay.played, d.played), (replay.ignored_response, d.played)]
    pairs += [(a.evidence, b.branch) for a, b in zip(replay.alternatives, d.alternatives)]
    for evidence, branch in pairs:
        first = evidence.line.plies[0]
        assert first.move is branch.move and first.position is branch.position
        assert first.facts is branch.facts and first.delta is branch.delta
        assert first.rules is branch.rules and first.detection is branch.detection
        assert first.identity is branch.identity


def test_batch_b_absent_is_not_synthesized():
    explainer, context, _, _ = scenario(START, ("e2e4", "d2d4"), {"e2e4": ("e7e5", "g1f3")})
    replay = explainer.replay_lines(context)
    assert replay.ignored_response is None
    assert len(replay.alternatives) == 1


def test_no_alternatives_replays_played_only():
    explainer, context, _, _ = scenario(START, ("e2e4",), {"e2e4": ("e7e5",)})
    replay = explainer.replay_lines(context)
    assert replay.alternatives == () and ucis(replay.played) == ("e2e4", "e7e5")


def test_terminal_batch_a_line_contains_only_first_ply():
    explainer, context, _, _ = scenario(QUEEN, ("f1f8", "f1f7"))
    replay = explainer.replay_lines(context)
    mate, stalemate = replay.played, replay.alternatives[0].evidence
    assert len(mate.line.plies) == len(stalemate.line.plies) == 1
    assert mate.line.final.position is context.deterministic.played.position
    assert mate.line.ends_in_checkmate and not mate.line.ends_in_stalemate
    assert stalemate.line.ends_in_stalemate and not stalemate.line.ends_in_checkmate
    assert mate.material == replace(mate.material, material_delta=0, stable_at_ply=1)
    assert mate.material.terminal_checkmate
    assert stalemate.material.stable_at_ply is None
    assert not stalemate.material.terminal_checkmate


def test_repeated_replay_makes_zero_p7_or_engine_calls():
    explainer, context, p7, engine = full_start()
    p7_calls, engine_calls = len(p7.calls), len(engine.calls)
    first = explainer.replay_lines(context)
    explainer.counterfactual = Forbidden("P7")

    def analyze(*args, **kwargs):
        raise AssertionError("I4 called the engine")

    engine.analyze = analyze
    assert explainer.replay_lines(context) == first == explainer.replay_lines(context)
    assert (len(p7.calls), len(engine.calls)) == (p7_calls, engine_calls)


def test_replay_never_reads_scores_wdl_or_judgement_numbers(monkeypatch):
    explainer, context, _, _ = full_start()

    def forbidden(self):
        raise AssertionError("I4 read numeric engine evidence")

    with monkeypatch.context() as patch:
        for cls, names in (
            (MoveJudgement, ("best_score", "played_score", "cp_loss", "expected_score_loss")),
            (Forcedness, ("acceptable_move_count", "best_to_second_gap_cp")),
            (EngineLine, ("score", "wdl", "depth", "seldepth", "nodes")),
        ):
            for name in names:
                patch.setattr(cls, name, property(forbidden))
        replay = explainer.replay_lines(context)
    assert len(replay.alternatives) == 2


def test_i4_source_boundary():
    methods = (
        GoodMoveExplainer.replay_lines,
        GoodMoveExplainer._revalidate_counterfactual_context,
        GoodMoveExplainer._replay_line,
        GoodMoveExplainer._replay_step,
        GoodMoveExplainer._legal_in,
        GoodMoveExplainer._check_board_truth,
        good_move._material_evidence,
        good_move._material_advantage,
        good_move._traced_change,
        good_move._piece_value,
    )
    tree = ast.parse("\n".join(textwrap.dedent(inspect.getsource(m)) for m in methods))
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert {"extract", "analyze", "observe_tactics", "detect", "advance", "pv"} <= attributes
    assert not attributes & {
        "execute",
        "counterfactual",
        "engine",
        "score",
        "wdl",
        "best_score",
        "played_score",
        "cp_loss",
        "expected_score_loss",
        "acceptable_move_count",
        "best_to_second_gap_cp",
        "position_analysis",
        "judgement",
        "status",
    }
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {
        "GoodMoveBenefitKind",
        "GoodMoveBenefitStatus",
        "GoodMoveBenefitResult",
        "GoodMoveExplanationResult",
        "TacticalCandidateStatus",
        "bad_move_causes",
        "material_evidence",
    }
    module = ast.parse(inspect.getsource(good_move))
    imported = {
        node.module for node in ast.walk(module) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "calliope.services.explanation.bad_move_causes" not in imported
    assert "calliope.services.explanation.bad_move" not in imported


def test_replay_models_frozen_and_slotted():
    explainer, context, _, _ = full_start()
    replay = explainer.replay_lines(context)
    values = (
        replay,
        replay.played,
        replay.played.line,
        replay.played.line.plies[0],
        replay.alternatives[0],
    )
    for value in values:
        assert not hasattr(value, "__dict__")
        field = fields(value)[0].name
        with pytest.raises(FrozenInstanceError):
            setattr(value, field, getattr(value, field))
    assert {f.name for f in fields(GoodMoveReplayContext)} == {
        "counterfactual",
        "played",
        "alternatives",
        "ignored_response",
    }
    assert {f.name for f in fields(GoodMoveLineEvidence)} == {"line", "material"}
    assert {f.name for f in fields(GoodMoveAlternativeLineEvidence)} == {
        "alternative",
        "evidence",
    }
    assert {f.name for f in fields(GoodMoveReplayedLineContext)} == {"probe_result", "plies"}
    assert len(fields(GoodMoveReplayStepContext)) == 10


# ---- special moves ---------------------------------------------------------------------------


def test_capture_inside_pv_removes_physical_base_identity():
    evidence = single(ROOK_HANGS, "c1c3", ("d5c3", "e1d2", "c3b5"))
    rook = BasePieceRef(Color.WHITE, PieceType.ROOK, "c1")
    knight = BasePieceRef(Color.BLACK, PieceType.KNIGHT, "d5")
    plies = evidence.line.plies
    assert plies[0].identity.current_piece(rook) == PieceRef(Color.WHITE, PieceType.ROOK, "c3")
    assert plies[1].identity.current_piece(rook) is None
    assert evidence.line.final.identity.current_piece(knight) == PieceRef(
        Color.BLACK, PieceType.KNIGHT, "b5"
    )
    assert (evidence.material.material_delta, evidence.material.stable_at_ply) == (-500, 4)


def test_promotion_inside_pv_keeps_base_pawn_identity():
    evidence = single(PROMOTE, "a1b1", ("h8h7", "a7a8q", "h7g6", "b1c2"))
    pawn = BasePieceRef(Color.WHITE, PieceType.PAWN, "a7")
    queen = PieceRef(Color.WHITE, PieceType.QUEEN, "a8")
    final = evidence.line.final.identity
    assert final.current_piece(pawn) == queen and final.base_ref_for(queen) == pawn
    assert (evidence.material.material_delta, evidence.material.stable_at_ply) == (800, 5)


def test_capture_promotion_first_move():
    evidence = single(PROMOTE, "a7b8q", ("h8h7", "a1b1"))
    knight = BasePieceRef(Color.BLACK, PieceType.KNIGHT, "b8")
    pawn = BasePieceRef(Color.WHITE, PieceType.PAWN, "a7")
    final = evidence.line.final.identity
    assert final.current_piece(knight) is None
    assert final.current_piece(pawn) == PieceRef(Color.WHITE, PieceType.QUEEN, "b8")
    assert (evidence.material.material_delta, evidence.material.stable_at_ply) == (1120, 3)


def test_castling_inside_pv_composes_king_and_rook_identities():
    evidence = single(CASTLE, "a1a2", ("e8c8", "e1g1"))
    final = evidence.line.final.identity
    expected = {
        ("e1", PieceType.KING, Color.WHITE): "g1",
        ("h1", PieceType.ROOK, Color.WHITE): "f1",
        ("e8", PieceType.KING, Color.BLACK): "c8",
        ("a8", PieceType.ROOK, Color.BLACK): "d8",
        ("a1", PieceType.ROOK, Color.WHITE): "a2",
    }
    for (square, kind, color), current in expected.items():
        assert final.current_piece(BasePieceRef(color, kind, square)) == PieceRef(
            color, kind, current
        )
    assert ucis(evidence) == ("a1a2", "e8c8", "e1g1")


def test_en_passant_inside_pv_uses_captured_square():
    evidence = single(EN_PASSANT, "e1e2", ("d7d5", "e5d6", "e8f7", "e2e3"))
    capture = evidence.line.plies[2].delta.capture
    assert capture.is_en_passant
    assert (capture.captured_square, capture.landing_square) == ("d5", "d6")
    victim = BasePieceRef(Color.BLACK, PieceType.PAWN, "d7")
    capturer = BasePieceRef(Color.WHITE, PieceType.PAWN, "e5")
    final = evidence.line.final.identity
    assert final.current_piece(victim) is None
    assert final.current_piece(capturer) == PieceRef(Color.WHITE, PieceType.PAWN, "d6")
    assert (evidence.material.material_delta, evidence.material.stable_at_ply) == (100, 5)


# ---- material ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fen,first,pv,delta,stable",
    [
        (START, "e2e4", ("e7e5", "g1f3"), 0, 3),  # no change: reference ply 1
        (START, "e2e4", ("e7e5",), 0, None),  # no change, one further ply
        (ROOK_TAKES, "d1d5", ("e8e7", "e1e2"), 320, 3),  # mover captures
        (ROOK_TAKES, "d1d5", ("e8e7",), 320, None),  # one ply after the change
        (ROOK_HANGS, "c1c3", ("d5c3",), -500, None),  # zero plies after the change
        (ROOK_HANGS, "c1c3", ("d5c3", "e1d2", "c3b5"), -500, 4),  # mover loses a rook
        (ROOK_HANGS, "c1c3", ("d5c3", "e1d2"), -500, None),
        (PROMOTE, "a7a8q", ("h8h7", "a1b1"), 800, 3),
        (PROMOTE, "a7a8n", ("h8g7", "a1b1"), 220, 3),  # underpromotion value
    ],
)
def test_material_delta_and_exact_stability_boundaries(fen, first, pv, delta, stable):
    evidence = single(fen, first, pv)
    assert len(evidence.line.plies) == len(pv) + 1
    assert evidence.material.material_delta == delta
    assert evidence.material.stable_at_ply == stable
    assert not evidence.material.terminal_checkmate
    assert evidence.material.probe.intervention_move.uci == first


def test_truncated_exchange_retains_delta_without_stability():
    exchange = "4k3/2n5/8/3p4/4P3/8/8/4K3 w - - 0 1"
    truncated = single(exchange, "e4d5", ("c7d5", "e1e2"))
    assert [s.delta.capture is not None for s in truncated.line.plies] == [True, True, False]
    assert (truncated.material.material_delta, truncated.material.stable_at_ply) == (0, None)
    completed = single(exchange, "e4d5", ("c7d5", "e1e2", "e8e7"))
    assert (completed.material.material_delta, completed.material.stable_at_ply) == (0, 4)
    winning = single("4k3/8/2n5/3p4/4P3/8/8/4K3 w - - 0 1", "e4d5", ("c6e5",))
    assert (winning.material.material_delta, winning.material.stable_at_ply) == (100, None)


def test_exact_checkmate_inside_pv_is_stable_without_material_change():
    evidence = single(QUEEN, "f1a1", ("h8g8", "a1a8"))
    assert evidence.line.ends_in_checkmate
    assert evidence.material.material_delta == 0
    assert evidence.material.stable_at_ply == 3 == evidence.line.final.ply
    assert evidence.material.terminal_checkmate


def test_stalemate_exactly_at_stability_ply_is_unstable():
    evidence = single(QUEEN, "g6h6", ("h8g8", "f1f6"))
    assert evidence.line.ends_in_stalemate and evidence.line.final.ply == 3
    assert evidence.material.stable_at_ply is None
    assert not evidence.material.terminal_checkmate


def test_later_stalemate_retains_established_stability():
    evidence = single(QUEEN, "g6f7", ("h8h7", "f7f8", "h7h8", "f1f7"))
    assert evidence.line.ends_in_stalemate and evidence.line.final.ply == 5
    assert evidence.material.stable_at_ply == 3


def test_black_original_mover_orientation():
    explainer, context, _, _ = scenario(
        BLACK_TAKES, ("d8d5", "e8f8"), {"d8d5": ("e1e2", "e8e7"), "e8f8": ("d5c7", "d8d1")}
    )
    replay = explainer.replay_lines(context)
    assert context.deterministic.prepared.base.side_to_move is Color.BLACK
    assert (replay.played.material.material_delta, replay.played.material.stable_at_ply) == (
        320,
        3,
    )
    alternative = replay.alternatives[0].evidence
    assert ucis(alternative) == ("e8f8", "d5c7", "d8d1")
    assert alternative.material.material_delta == 0
    assert_chained(replay.played, context.deterministic)


def test_engine_pv_continuing_past_checkmate_fails_closed():
    explainer, context, _, _ = scenario(QUEEN, ("f1a1",), {"f1a1": ("h8g8", "a1a8", "g8h7")})
    with pytest.raises(IncompatibleGoodMoveContextError, match="terminal"):
        explainer.replay_lines(context)


def test_engine_pv_continuing_past_stalemate_fails_closed():
    explainer, context, _, _ = scenario(QUEEN, ("g6h6",), {"g6h6": ("h8g8", "f1f6", "g8h8")})
    with pytest.raises(IncompatibleGoodMoveContextError, match="terminal"):
        explainer.replay_lines(context)


@pytest.mark.parametrize(
    "uci,error_type",
    [("e2e4", IllegalMoveError), ("bad", InvalidUciError), ("0000", NullMoveNotAllowedError)],
)
@pytest.mark.parametrize("index", [0, 2])
def test_illegal_or_malformed_engine_pv_fails_closed_with_cause(uci, error_type, index):
    pv = ["e7e5", "g1f3", "b8c6"]
    pv[index] = uci
    explainer, context, _, _ = scenario(START, ("e2e4",), {"e2e4": tuple(pv)})
    with pytest.raises(IncompatibleGoodMoveContextError) as caught:
        explainer.replay_lines(context)
    assert isinstance(caught.value.__cause__, error_type)


def test_unexpected_rules_failure_is_not_swallowed(monkeypatch):
    explainer, context, _, _ = full_start()

    def boom(position, uci):
        raise RuntimeError("rules adapter failure")

    monkeypatch.setattr(explainer.chess, "legal_move_from_uci", boom)
    with pytest.raises(RuntimeError, match="rules adapter failure"):
        explainer.replay_lines(context)


# ---- P8 parity -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fen,first,pv",
    [
        (START, "e2e4", ("e7e5", "g1f3", "b8c6")),  # no material change
        (ROOK_TAKES, "d1d5", ("e8e7", "e1e2")),  # capture
        (ROOK_HANGS, "c1c3", ("d5c3", "e1d2", "c3b5")),  # mover loses
        (PROMOTE, "a1b1", ("h8h7", "a7a8q", "h7g6", "b1c2")),  # promotion
        (PROMOTE, "a7b8q", ("h8h7", "a1b1")),  # capture + promotion
        (QUEEN, "f1a1", ("h8g8", "a1a8")),  # exact checkmate
        (QUEEN, "f1f8", ()),  # terminal first-move checkmate
        (QUEEN, "g6h6", ("h8g8", "f1f6")),  # stalemate boundary
        (QUEEN, "g6f7", ("h8h7", "f7f8", "h7h8", "f1f7")),  # later stalemate
        (QUEEN, "f1f7", ()),  # terminal first-move stalemate
        (ROOK_TAKES, "d1d5", ("e8e7",)),  # truncated
        (EN_PASSANT, "e1e2", ("d7d5", "e5d6", "e8f7", "e2e3")),
        (BLACK_TAKES, "d8d5", ("e1e2", "e8e7")),
    ],
)
def test_material_parity_with_p8(fen, first, pv):
    explainer, context, _, _ = scenario(fen, (first,), {first: pv} if pv else None)
    evidence = explainer.replay_lines(context).played
    assert evidence.material == p8_material(evidence, context)
    assert good_move.PIECE_VALUES == bad_move_causes.PIECE_VALUES


# ---- material tracing fails closed -----------------------------------------------------------


def _with_step(evidence, index, **changes):
    plies = list(evidence.line.plies)
    plies[index] = replace(plies[index], **changes)
    return replace(evidence.line, plies=tuple(plies))


def test_material_change_without_p5_event_fails_closed():
    explainer, context, _, _ = scenario(ROOK_TAKES, ("d1d5",), {"d1d5": ("e8e7", "e1e2")})
    evidence = explainer.replay_lines(context).played
    base_facts = context.deterministic.base_facts
    quiet = evidence.line.plies[1]
    capture = evidence.line.plies[0]
    # P4 changes on a quiet ply: reuse post-capture facts one ply earlier.
    tampered = _with_step(evidence, 0, delta=quiet.delta)
    with pytest.raises(IncompatibleGoodMoveContextError, match="traced"):
        good_move._material_evidence(tampered, base_facts, Color.WHITE)
    # P5 capture with no P4 change.
    tampered = _with_step(evidence, 1, delta=capture.delta)
    with pytest.raises(IncompatibleGoodMoveContextError, match="traced"):
        good_move._material_evidence(tampered, base_facts, Color.WHITE)


def test_corrupted_p4_material_during_replay_fails_closed(monkeypatch):
    explainer, context, _, _ = scenario(START, ("e2e4",), {"e2e4": ("e7e5", "g1f3")})

    def corrupt(facts):
        material = replace(facts.material, black=replace(facts.material.black, knights=1))
        return replace(facts, material=material)

    _patch_result(monkeypatch, explainer, "facts", "extract", corrupt)
    with pytest.raises(IncompatibleGoodMoveContextError, match="traced"):
        explainer.replay_lines(context)


def test_corrupted_p5_capture_during_replay_fails_closed(monkeypatch):
    explainer, context, _, _ = scenario(ROOK_HANGS, ("c1c3",), {"c1c3": ("d5c3", "e1d2")})

    def corrupt(delta):
        if delta.capture is not None:
            captured = replace(delta.capture.captured, piece_type=PieceType.BISHOP)
            return replace(delta, capture=replace(delta.capture, captured=captured))
        return delta

    _patch_result(monkeypatch, explainer, "delta", "analyze", corrupt)
    with pytest.raises(IncompatibleGoodMoveContextError):
        explainer.replay_lines(context)


# ---- step binding validation -----------------------------------------------------------------


class Altered:
    """Wrap one explainer dependency so only its own returned evidence is altered."""

    def __init__(self, inner, method, change):
        self.inner, self.method, self.change = inner, method, change

    def __getattr__(self, name):
        found = getattr(self.inner, name)
        if name != self.method:
            return found
        return lambda *a, **k: self.change(found(*a, **k))


def _patch_result(monkeypatch, explainer, dependency, method, change):
    """Branches are already built, so only replayed plies see the altered evidence."""
    altered = Altered(getattr(explainer, dependency), method, change)
    monkeypatch.setattr(explainer, dependency, altered)


@pytest.mark.parametrize(
    "dependency,method,change,message",
    [
        ("delta", "analyze", lambda d: replace(d, before_position_id="x"), "start"),
        ("delta", "analyze", lambda d: replace(d, after_position_id="x"), "end"),
        ("delta", "analyze", lambda d: replace(d, move=ChessMove("a2a3")), "another move"),
        ("delta", "analyze", lambda d: replace(d, mover=d.mover.opposite), "mover"),
        ("facts", "extract", lambda f: replace(f, position_id="x"), "facts"),
        ("tactical_rules", "observe_tactics", lambda r: replace(r, position_id="x"), "obser"),
        (
            "tactical_rules",
            "observe_tactics",
            lambda r: replace(r, side_to_move=r.side_to_move.opposite),
            "side to move",
        ),
        ("detector", "detect", lambda d: replace(d, before_position_id="x"), "start"),
        ("detector", "detect", lambda d: replace(d, after_position_id="x"), "end"),
        ("detector", "detect", lambda d: replace(d, move=ChessMove("a2a3")), "another move"),
        ("detector", "detect", lambda d: replace(d, mover=d.mover.opposite), "mover"),
    ],
)
def test_replay_binding_contradictions_fail_closed(
    monkeypatch, dependency, method, change, message
):
    explainer, context, _, _ = full_start()
    _patch_result(monkeypatch, explainer, dependency, method, change)
    with pytest.raises(IncompatibleGoodMoveContextError, match=message):
        explainer.replay_lines(context)


@pytest.mark.parametrize("which", ["played", "alternative"])
def test_retained_first_ply_checkmate_contradiction_fails_closed(which):
    explainer, context, _, _ = full_start()
    d = context.deterministic
    if which == "played":
        facts = replace(d.played.facts, side_to_move_checkmated=True)
        d = replace(d, played=replace(d.played, facts=facts))
    else:
        alt = d.alternatives[0]
        facts = replace(alt.branch.facts, side_to_move_checkmated=True)
        alt = replace(alt, branch=replace(alt.branch, facts=facts))
        d = replace(d, alternatives=(alt, *d.alternatives[1:]))
    _forbid_replay(explainer)
    with pytest.raises(IncompatibleGoodMoveContextError, match="checkmate"):
        explainer.replay_lines(replace(context, deterministic=d))


class ConsistentDetector:
    """Hide the injected contradiction from P6 so that P9's own board-truth check is reached."""

    def __init__(self, inner):
        self.inner = inner

    def detect(self, *, after, **kwargs):
        return self.inner.detect(after=replace(after, side_to_move_checkmated=False), **kwargs)


def test_replayed_ply_checkmate_contradiction_fails_closed(monkeypatch):
    explainer, context, _, _ = scenario(START, ("e2e4",), {"e2e4": ("e7e5", "g1f3")})
    _patch_result(
        monkeypatch,
        explainer,
        "facts",
        "extract",
        lambda f: replace(f, side_to_move_checkmated=True),
    )
    monkeypatch.setattr(explainer, "detector", ConsistentDetector(explainer.detector))
    with pytest.raises(IncompatibleGoodMoveContextError, match="checkmate"):
        explainer.replay_lines(context)


@pytest.mark.parametrize("attribute", ["base_position_id", "position_id"])
def test_identity_binding_mismatch_fails_closed(monkeypatch, attribute):
    explainer, context, _, _ = full_start()
    original = BasePieceIdentityMap.advance
    monkeypatch.setattr(
        BasePieceIdentityMap,
        "advance",
        lambda self, delta: replace(original(self, delta), **{attribute: "x"}),
    )
    with pytest.raises(IncompatibleGoodMoveContextError, match="identity"):
        explainer.replay_lines(context)


def test_identity_error_translates_to_p9_with_cause(monkeypatch):
    explainer, context, _, _ = full_start()
    cause = IncompatibleBadMoveContextError("identity helper rejected the delta")

    def advance(self, delta):
        raise cause

    monkeypatch.setattr(BasePieceIdentityMap, "advance", advance)
    with pytest.raises(IncompatibleGoodMoveContextError) as caught:
        explainer.replay_lines(context)
    assert caught.value.__cause__ is cause
    assert not isinstance(caught.value, IncompatibleBadMoveContextError)


def test_apply_move_rejection_translates_with_cause(monkeypatch):
    explainer, context, _, _ = full_start()
    cause = IllegalMoveError("rejected")

    def apply_move(position, move):
        raise cause

    monkeypatch.setattr(explainer.chess, "apply_move", apply_move)
    with pytest.raises(IncompatibleGoodMoveContextError) as caught:
        explainer.replay_lines(context)
    assert caught.value.__cause__ is cause


# ---- retained I3 context integrity -----------------------------------------------------------


def _forbid_replay(explainer):
    for name in ("facts", "delta", "detector", "tactical_rules"):
        setattr(explainer, name, Forbidden(name))
    explainer.counterfactual = Forbidden("P7")


def _results(batch, transform):
    return replace(batch, results=transform(batch.results))


def _other_batch_b_engine(context):
    result = context.ignored_response_result
    analysis = replace(result.engine_analysis, engine=EngineIdentity("Other"))
    result = replace(result, engine_analysis=analysis)
    return replace(
        context,
        batch_b=replace(context.batch_b, results=(result,)),
        ignored_response_result=result,
    )


EXPECTED = {
    "alternative_branch": "alternative branch metadata",
    "alternative_dropped": "Batch-A refutations",
    "alternative_result_swapped": "alternative refutation",
    "alternatives_reordered": "alternative refutation",
    "batch_a_reordered": "probe echo or order",
    "batch_a_truncated": "result count",
    "batch_b_identity": "engine identity differs across P7 batches",
    "batch_b_only": "partially retained",
    "engine_identity": "Batch-A engine identity",
    "engine_identity_none": "Batch-A engine identity",
    "played_branch": "played branch move",
    "played_refutation": "Batch-A refutations",
    "probe_budget": "four probes",
    "response_changed": "probe echo or order",
    "response_only": "partially retained",
    "response_result_missing": "partially retained",
    "response_result_swapped": "ignored-response result",
    "root_identity": "deterministic base evidence",
    "settings": "settings",
}

TAMPERS = {
    "played_refutation": lambda c: replace(c, played_refutation=c.batch_a.results[1]),
    "alternatives_reordered": lambda c: replace(
        c, alternative_refutations=c.alternative_refutations[::-1]
    ),
    "alternative_dropped": lambda c: replace(
        c, alternative_refutations=c.alternative_refutations[:1]
    ),
    "alternative_result_swapped": lambda c: replace(
        c,
        alternative_refutations=(
            replace(c.alternative_refutations[0], result=c.batch_a.results[2]),
            c.alternative_refutations[1],
        ),
    ),
    "batch_a_reordered": lambda c: replace(
        c, batch_a=_results(c.batch_a, lambda r: (r[0], r[2], r[1]))
    ),
    "batch_a_truncated": lambda c: replace(c, batch_a=_results(c.batch_a, lambda r: r[:2])),
    "engine_identity": lambda c: replace(c, engine_identity=EngineIdentity("Other")),
    "engine_identity_none": lambda c: replace(c, engine_identity=None),
    "settings": lambda c: replace(c, settings=EngineSettings(EngineLimit(depth=2))),
    "played_branch": lambda c: replace(
        c,
        deterministic=replace(c.deterministic, played=c.deterministic.alternatives[0].branch),
    ),
    "alternative_branch": lambda c: replace(
        c,
        deterministic=replace(
            c.deterministic,
            alternatives=(
                replace(
                    c.deterministic.alternatives[0],
                    branch=c.deterministic.alternatives[1].branch,
                ),
                c.deterministic.alternatives[1],
            ),
        ),
    ),
    "root_identity": lambda c: replace(
        c,
        deterministic=replace(c.deterministic, root_identity=c.deterministic.played.identity),
    ),
    "batch_b_only": lambda c: replace(c, ignored_response=None, ignored_response_result=None),
    "response_only": lambda c: replace(c, batch_b=None, ignored_response_result=None),
    "response_result_missing": lambda c: replace(c, ignored_response_result=None),
    "response_changed": lambda c: replace(c, ignored_response=ChessMove("e7e5")),
    "response_result_swapped": lambda c: replace(c, ignored_response_result=c.batch_a.results[0]),
    "batch_b_identity": lambda c: _other_batch_b_engine(c),
    "probe_budget": lambda c: replace(c, batch_b=_results(c.batch_b, lambda r: (r[0], r[0]))),
}


def test_tamper_table_is_complete():
    assert set(TAMPERS) == set(EXPECTED)


@pytest.mark.parametrize("name", sorted(TAMPERS))
def test_tampered_i3_context_fails_before_replay(name):
    explainer, context, p7, engine = full_start()
    calls = (len(p7.calls), len(engine.calls))
    tampered = TAMPERS[name](context)
    _forbid_replay(explainer)
    with pytest.raises(IncompatibleGoodMoveContextError, match=EXPECTED[name]):
        explainer.replay_lines(tampered)
    assert (len(p7.calls), len(engine.calls)) == calls


def test_batch_b_ply_two_must_equal_ignored_response(monkeypatch):
    explainer, context, _, _ = full_start()
    other = rules.legal_move_from_uci(context.deterministic.played.position, "e7e5")
    monkeypatch.setattr(GoodMoveExplainer, "_check_counterfactual_batch", lambda *a: None)
    with pytest.raises(IncompatibleGoodMoveContextError, match="ignored response"):
        explainer.replay_lines(replace(context, ignored_response=other))


def test_terminal_line_tampered_with_engine_pv_rejected():
    explainer, context, _, _ = scenario(QUEEN, ("f1f8", "f1f7"))
    nonterminal, *_ = scenario(QUEEN, ("f1a1",))[1].batch_a.results
    fake = replace(
        context.played_refutation,
        terminal=None,
        engine_analysis=replace(
            nonterminal.engine_analysis,
            position_id=context.played_refutation.analysis_position.position_id,
            settings=SETTINGS,
        ),
    )
    tampered = replace(
        context,
        played_refutation=fake,
        batch_a=_results(context.batch_a, lambda r: (fake, *r[1:])),
    )
    _forbid_replay(explainer)
    with pytest.raises(IncompatibleGoodMoveContextError):
        explainer.replay_lines(tampered)
