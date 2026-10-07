import inspect
from dataclasses import dataclass, field, fields, replace

import pytest

import calliope.services.explanation.bad_move as bad_move_module
from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis import (
    BadMoveCauseResult,
    CounterfactualBatchResult,
    ProbeKind,
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
from calliope.services.explanation.bad_move import (
    BadMoveCounterfactualContext,
    BadMoveNotApplicable,
    BadMovePreparedContext,
    comparator_strictly_better,
)
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.tactics import TacticalDetector

rules = PythonChessAdapter()
facts = PositionFactExtractor(rules)
deltas = BoardDeltaAnalyzer(rules, facts)
detector = TacticalDetector()

W, B = Color.WHITE, Color.BLACK
cp = EngineScore.cp
mate = EngineScore.forced_mate
OTHER_SETTINGS = EngineSettings(limit=EngineLimit(time_ms=500), multipv=1, threads=1)
FAKE = EngineIdentity("Fake", "1")

# White knight on c3. Ne4 (M) is en prise to d5xe4; Nb5 (A) is not, and d5e4 is then illegal.
KNIGHT = "4k3/8/8/3p4/8/2N5/8/4K3 w - - 0 1"
CASTLING = "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"
# Qf7 stalemates, Qf8 mates, Qf6+ is an ordinary check.
QUEEN = "7k/8/6K1/8/8/8/8/5Q2 w - - 0 1"


def after(fen: str, *ucis: str):
    position = rules.position_from_fen(fen)
    for uci in ucis:
        position = rules.apply_move(position, rules.legal_move_from_uci(position, uci))
    return position


@dataclass
class ScriptedEngine:
    """Answers unforced analyses from a per-position script; echoes forced roots."""

    replies: dict
    forced_score: EngineScore = field(default_factory=lambda: cp(0))
    identity_for_call: callable = lambda call: FAKE
    calls: list = field(default_factory=list)

    def analyze(self, position, settings, root_moves=None):
        self.calls.append((position, root_moves))
        if root_moves:
            first, score = root_moves[0], self.forced_score
        else:
            uci, score = self.replies[position.position_id]
            first = ChessMove(uci)
        return EngineAnalysis(
            position_id=position.position_id,
            engine=self.identity_for_call(len(self.calls)),
            settings=settings,
            lines=(EngineLine(1, first, score, (first,)),),
        )


class RecordingP7:
    """The real P7 analyzer behind a recorder that may tamper with returned batches."""

    def __init__(self, analyzer: CounterfactualAnalyzer, tamper=None) -> None:
        self.analyzer = analyzer
        self.tamper = tamper
        self.requests: list = []

    def execute(self, request):
        self.requests.append(request)
        result = self.analyzer.execute(request)
        return self.tamper(len(self.requests), result) if self.tamper else result


def judgement(base, played: str, best: str, quality=MoveQuality.BLUNDER) -> MoveJudgement:
    return MoveJudgement(
        position_id=base.position_id,
        mover=base.side_to_move,
        move=ChessMove(played),
        best_move=ChessMove(best),
        quality=quality,
        rank=None,
        best_score=EngineScore.cp(10_000),
        played_score=EngineScore.cp(-10_000),
        cp_loss=20_000,
        expected_score_loss=1.0,
    )


def setup(fen, played, best, replies, *, tamper=None, quality=MoveQuality.BLUNDER, **engine_kw):
    """replies: {first-move uci: (engine reply uci, White-POV score)} for unforced analyses."""

    base = rules.position_from_fen(fen)
    engine = ScriptedEngine(
        {after(fen, uci).position_id: reply for uci, reply in replies.items()}, **engine_kw
    )
    p7 = RecordingP7(CounterfactualAnalyzer(rules, engine, rules, rules), tamper)
    explainer = BadMoveExplainer(rules, facts, deltas, rules, detector, p7)
    prepared = explainer.prepare(base, ChessMove(played), judgement(base, played, best, quality))
    return explainer, prepared, p7, engine


def run(fen, played, best, replies, **kw) -> tuple[BadMoveCounterfactualContext, RecordingP7]:
    explainer, prepared, p7, _ = setup(fen, played, best, replies, **kw)
    return explainer.verify_counterfactuals(prepared, DEFAULT_SETTINGS), p7


def knight(**kw):
    return run(KNIGHT, "c3e4", "c3b5", {"c3e4": ("d5e4", cp(-300)), "c3b5": ("e8e7", cp(0))}, **kw)


def quiet(**kw):
    # The punishment e8e7 stays legal after the comparator, so Batch B runs.
    return run(KNIGHT, "c3e4", "c3b5", {"c3e4": ("e8e7", cp(-50)), "c3b5": ("e8d7", cp(0))}, **kw)


def probe_shape(p7: RecordingP7):
    return [
        [
            (p.kind, p.intervention_move.uci, p.execution_move and p.execution_move.uci)
            for p in request.probes
        ]
        for request in p7.requests
    ]


# ---- Batch A --------------------------------------------------------------------------


def test_batch_a_is_exactly_two_refutations_in_order_with_requested_settings() -> None:
    context, p7 = knight()

    assert probe_shape(p7) == [
        [(ProbeKind.REFUTATION, "c3e4", None), (ProbeKind.REFUTATION, "c3b5", None)]
    ]
    request = p7.requests[0]
    assert request.settings == DEFAULT_SETTINGS
    assert all(p.base == context.prepared.base for p in request.probes)
    assert context.batch_a.settings == DEFAULT_SETTINGS


def test_batch_a_results_bind_to_prepared_branches() -> None:
    context, _ = knight()

    assert context.actual_refutation.analysis_position == context.prepared.actual.position
    assert context.comparator_refutation.analysis_position == context.prepared.comparator.position
    assert context.actual_refutation is context.batch_a.results[0]
    assert context.comparator_refutation is context.batch_a.results[1]


def test_not_applicable_path_makes_no_p7_call() -> None:
    _, prepared, p7, engine = setup(KNIGHT, "c3e4", "c3b5", {}, quality=MoveQuality.INACCURACY)

    assert isinstance(prepared, BadMoveNotApplicable)
    assert p7.requests == [] and engine.calls == []


# ---- punishment P ---------------------------------------------------------------------


def test_punishment_is_canonical_rank_one_reply_after_played_move() -> None:
    context, _ = knight()

    assert context.punishment_move == ChessMove("d5e4", "dxe4")
    assert context.actual_punishment.move == context.punishment_move


@pytest.mark.parametrize("reply", ["zzzz", "e1e2", "0000", "d5d3"])
def test_malformed_or_illegal_engine_punishment_fails_closed(reply: str) -> None:
    with pytest.raises(IncompatibleBadMoveContextError, match="engine punishment"):
        run(KNIGHT, "c3e4", "c3b5", {"c3e4": (reply, cp(-300)), "c3b5": ("e8e7", cp(0))})


def test_engine_castling_alias_becomes_canonical_punishment() -> None:
    context, p7 = run(
        CASTLING, "a1b1", "a1a2", {"a1b1": ("e8h8", cp(-20)), "a1a2": ("e8c8", cp(0))}
    )

    assert context.punishment_move == ChessMove("e8g8", "O-O")
    assert context.same_punishment_legal_after_comparator is True
    assert p7.requests[1].probes[0].execution_move.uci == "e8g8"


# ---- actual punishment branch ---------------------------------------------------------


def test_actual_punishment_branch_is_one_coherent_step_from_played_branch() -> None:
    context, _ = knight()
    branch = context.prepared.actual
    step = context.actual_punishment
    bmp = rules.apply_move(branch.position, context.punishment_move)

    assert step.before == branch.position
    assert step.position == bmp
    assert step.delta == deltas.analyze(branch.position, context.punishment_move)
    assert step.facts == facts.extract(bmp)
    assert step.rules == rules.observe_tactics(bmp)
    assert step.detection.before_position_id == branch.position.position_id
    assert step.detection.mover is B
    assert step.identity == branch.identity.advance(step.delta)
    assert step.identity.base_position_id == context.prepared.base.position_id

    root = context.prepared.root_identity
    knight_ref = root.base_ref_for(PieceRef(W, PieceType.KNIGHT, "c3"))
    pawn_ref = root.base_ref_for(PieceRef(B, PieceType.PAWN, "d5"))
    assert step.identity.current_piece(knight_ref) is None
    assert step.identity.current_piece(pawn_ref) == PieceRef(B, PieceType.PAWN, "e4")
    assert all(c.status is TacticalCandidateStatus.DETECTED for c in step.detection.candidates)


# ---- Batch B decision -----------------------------------------------------------------


def test_punishment_illegal_after_comparator_skips_batch_b() -> None:
    context, p7 = knight()

    assert context.same_punishment_legal_after_comparator is False
    assert context.batch_b is None
    assert context.comparator_replay is None
    assert context.comparator_punishment is None
    assert len(p7.requests) == 1 and context.probe_count == 2


def test_batch_b_decision_uses_comparator_legal_move_membership() -> None:
    explainer, prepared, p7, _ = setup(
        KNIGHT, "c3e4", "c3b5", {"c3e4": ("e8e7", cp(-50)), "c3b5": ("e8d7", cp(0))}
    )
    # e8e7 is legal after Nb5, but the recorded comparator observation omits it.
    rules_without = replace(
        prepared.comparator.rules,
        legal_moves=tuple(m for m in prepared.comparator.rules.legal_moves if m.uci != "e8e7"),
    )
    tampered = replace(prepared, comparator=replace(prepared.comparator, rules=rules_without))

    context = explainer.verify_counterfactuals(tampered, DEFAULT_SETTINGS)

    assert context.same_punishment_legal_after_comparator is False
    assert len(p7.requests) == 1


def test_legal_punishment_runs_exactly_one_ignore_threat_probe() -> None:
    context, p7 = quiet()

    assert probe_shape(p7) == [
        [(ProbeKind.REFUTATION, "c3e4", None), (ProbeKind.REFUTATION, "c3b5", None)],
        [(ProbeKind.IGNORE_THREAT, "c3b5", "e8e7")],
    ]
    assert p7.requests[1].settings == DEFAULT_SETTINGS
    assert p7.requests[1].probes[0].execution_move == rules.legal_move_from_uci(
        context.prepared.comparator.position, "e8e7"
    )
    assert context.same_punishment_legal_after_comparator is True
    assert context.comparator_replay is context.batch_b.results[0]
    assert context.comparator_replay.root_moves[0].uci == "e8e7"
    assert context.probe_count == 3


def test_comparator_punishment_branch_advances_comparator_identity() -> None:
    context, _ = quiet()
    comparator = context.prepared.comparator
    step = context.comparator_punishment

    assert step.before == comparator.position
    assert step.position == rules.apply_move(comparator.position, step.move)
    assert step.delta.before_position_id == comparator.position.position_id
    assert step.identity == comparator.identity.advance(step.delta)

    knight_ref = context.prepared.root_identity.base_ref_for(PieceRef(W, PieceType.KNIGHT, "c3"))
    assert step.identity.current_piece(knight_ref).square == "b5"
    assert context.actual_punishment.identity.current_piece(knight_ref).square == "e4"
    assert all(c.status is TacticalCandidateStatus.DETECTED for c in step.detection.candidates)


# ---- batch integrity ------------------------------------------------------------------


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


def moved_to(position):
    def change(result):
        analysis = replace(result.engine_analysis, position_id=position.position_id)
        return replace(result, analysis_position=position, engine_analysis=analysis)

    return change


A_TAMPERING = [
    (lambda b: replace(b, settings=OTHER_SETTINGS), "different settings"),
    (lambda b: replace(b, results=b.results[:1]), "wrong number"),
    (lambda b: replace(b, results=b.results[::-1]), "echo the requested probe"),
    (
        with_result(
            0, lambda r: replace(r, probe=replace(r.probe, kind=ProbeKind.ALTERNATIVE_MOVE))
        ),
        "echo the requested probe",
    ),
    (
        with_result(
            1, lambda r: replace(r, probe=replace(r.probe, intervention_move=ChessMove("c3a4")))
        ),
        "echo the requested probe",
    ),
    (
        with_result(
            0, lambda r: replace(r, probe=replace(r.probe, execution_move=ChessMove("e8e7")))
        ),
        "echo the requested probe",
    ),
    (with_result(0, moved_to(after(KNIGHT, "c3a4"))), "analysed a different position"),
    (
        with_result(
            0,
            lambda r: replace(
                r, engine_analysis=replace(r.engine_analysis, settings=OTHER_SETTINGS)
            ),
        ),
        "engine analysis used different settings",
    ),
    (
        with_result(
            1,
            lambda r: replace(
                r, engine_analysis=replace(r.engine_analysis, engine=EngineIdentity("Other"))
            ),
        ),
        "within one P7 batch",
    ),
    (with_result(0, lambda r: replace(r, root_moves=(ChessMove("d5e4"),))), "root moves"),
]


@pytest.mark.parametrize(("change", "message"), A_TAMPERING)
def test_tampered_batch_a_fails_closed(change, message: str) -> None:
    with pytest.raises(IncompatibleBadMoveContextError, match=message):
        knight(tamper=on_call(1, change))


B_TAMPERING = [
    (lambda b: replace(b, settings=OTHER_SETTINGS), "different settings"),
    (lambda b: replace(b, results=()), "wrong number"),
    (
        with_result(
            0, lambda r: replace(r, probe=replace(r.probe, execution_move=ChessMove("e8d7")))
        ),
        "echo the requested probe",
    ),
    (with_result(0, lambda r: replace(r, root_moves=(ChessMove("e8d7"),))), "root moves"),
    (with_result(0, lambda r: replace(r, root_moves=None)), "lost its root move"),
    (with_result(0, moved_to(after(KNIGHT, "c3a4"))), "analysed a different position"),
]


@pytest.mark.parametrize(("change", "message"), B_TAMPERING)
def test_tampered_batch_b_fails_closed(change, message: str) -> None:
    with pytest.raises(IncompatibleBadMoveContextError, match=message):
        quiet(tamper=on_call(2, change))


def test_terminal_result_must_match_exact_branch_facts() -> None:
    wrong = with_result(
        0, lambda r: replace(r, terminal=TerminalOutcome(TerminalKind.CHECKMATE, W))
    )
    with pytest.raises(IncompatibleBadMoveContextError, match="contradicts the exact branch"):
        run(QUEEN, "f1f7", "f1f8", {}, tamper=on_call(1, wrong))


# ---- engine identity ------------------------------------------------------------------


def test_common_engine_identity_is_retained_across_batches() -> None:
    context, _ = quiet()
    assert context.engine_identity == FAKE


def test_batch_b_engine_identity_must_match_batch_a() -> None:
    with pytest.raises(IncompatibleBadMoveContextError, match="across P7 batches"):
        quiet(identity_for_call=lambda call: FAKE if call < 3 else EngineIdentity("Fake", "2"))


# ---- terminal paths and score gate through the service ------------------------------


def test_terminal_actual_branch_has_no_punishment_and_two_probes() -> None:
    context, p7 = run(QUEEN, "f1f7", "f1f8", {})

    assert context.actual_refutation.terminal == TerminalOutcome(TerminalKind.STALEMATE, None)
    assert context.comparator_refutation.terminal == TerminalOutcome(TerminalKind.CHECKMATE, W)
    assert context.punishment_move is None
    assert context.actual_punishment is None
    assert context.same_punishment_legal_after_comparator is None
    assert context.batch_b is None
    assert context.engine_identity is None
    assert context.comparator_strictly_better is None
    assert len(p7.requests) == 1 and context.probe_count == 2


def test_exact_comparator_checkmate_beats_actual_centipawns() -> None:
    context, _ = run(QUEEN, "f1f6", "f1f8", {"f1f6": ("h8g8", cp(500))})

    assert context.punishment_move.uci == "h8g8"
    assert context.same_punishment_legal_after_comparator is False
    assert context.comparator_strictly_better is True
    assert context.probe_count == 2


@pytest.mark.parametrize(
    ("actual", "comparator", "expected"),
    [((-300), 0, True), (0, 0, False), (0, -300, False)],
)
def test_service_gate_uses_p7_scores_only(actual: int, comparator: int, expected: bool) -> None:
    # The judgement claims a 20000 cp loss; only the P7 scores may decide the gate.
    context, _ = run(
        KNIGHT,
        "c3e4",
        "c3b5",
        {"c3e4": ("d5e4", cp(actual)), "c3b5": ("e8e7", cp(comparator))},
    )
    assert context.comparator_strictly_better is expected


# ---- score ordering (pure) ------------------------------------------------------------


@pytest.mark.parametrize(
    ("mover", "actual", "comparator", "expected"),
    [
        (W, cp(-100), cp(50), True),
        (B, cp(100), cp(-50), True),
        (W, cp(30), cp(30), False),
        (W, cp(30), cp(-10), False),
        (B, cp(-30), cp(10), False),
        (W, cp(900), mate(W, 7), True),
        (B, cp(-900), mate(B, 7), True),
        (W, mate(B, 2), cp(-900), True),
        (W, cp(-900), mate(B, 2), False),
        (W, mate(W, 5), mate(W, 3), True),
        (W, mate(W, 3), mate(W, 5), False),
        (W, mate(B, 3), mate(B, 6), True),
        (W, mate(B, 6), mate(B, 3), False),
        (W, mate(B, 1), mate(W, 9), True),
        (W, mate(W, 4), mate(W, 4), False),
        (B, mate(B, 4), mate(B, 4), False),
    ],
)
def test_mate_aware_strict_ordering(mover, actual, comparator, expected) -> None:
    assert comparator_strictly_better(mover, actual, comparator) is expected


def test_exact_checkmate_is_mate_at_zero() -> None:
    white_mates = TerminalOutcome(TerminalKind.CHECKMATE, W)
    black_mates = TerminalOutcome(TerminalKind.CHECKMATE, B)

    assert comparator_strictly_better(W, mate(W, 1), white_mates) is True
    assert comparator_strictly_better(W, white_mates, mate(W, 1)) is False
    assert comparator_strictly_better(W, black_mates, mate(B, 1)) is True
    assert comparator_strictly_better(W, black_mates, cp(-5000)) is True
    assert comparator_strictly_better(W, white_mates, white_mates) is False
    # A zero-distance engine mate keeps its winner even though for_color() is 0.
    assert comparator_strictly_better(W, mate(B, 0), cp(0)) is True


@pytest.mark.parametrize("stalemate_side", ["actual", "comparator"])
def test_stalemate_on_either_side_has_no_ordering(stalemate_side: str) -> None:
    stalemate = TerminalOutcome(TerminalKind.STALEMATE, None)
    actual, comparator = (stalemate, cp(0)) if stalemate_side == "actual" else (cp(0), stalemate)

    assert comparator_strictly_better(W, actual, comparator) is None
    assert comparator_strictly_better(B, actual, comparator) is None


# ---- real P7 boundary and scope -------------------------------------------------------


def test_real_counterfactual_analyzer_boundary_end_to_end() -> None:
    base = rules.position_from_fen(KNIGHT)
    engine = ScriptedEngine(
        {
            after(KNIGHT, "c3e4").position_id: ("e8e7", cp(-50)),
            after(KNIGHT, "c3b5").position_id: ("e8d7", cp(0)),
        }
    )
    analyzer = CounterfactualAnalyzer(rules, engine, rules, rules)
    explainer = BadMoveExplainer(rules, facts, deltas, rules, detector, analyzer)
    prepared = explainer.prepare(base, ChessMove("c3e4"), judgement(base, "c3e4", "c3b5"))
    assert isinstance(prepared, BadMovePreparedContext)

    context = explainer.verify_counterfactuals(prepared, DEFAULT_SETTINGS)

    assert [roots for _, roots in engine.calls] == [None, None, (ChessMove("e8e7", "Ke7"),)]
    assert context.probe_count == 3
    assert context.comparator_strictly_better is True
    assert context.engine_identity == FAKE


def test_no_cause_is_classified_and_no_p3_score_or_material_logic_exists() -> None:
    context, _ = quiet()

    values = [getattr(context, f.name) for f in fields(context)]
    assert not any(isinstance(value, BadMoveCauseResult) for value in values)

    source = inspect.getsource(bad_move_module)
    for forbidden in (
        "best_score",
        "played_score",
        "cp_loss",
        "expected_score_loss",
        "BadMoveCause",
        "BadMoveExplanationStatus",
        "900",
        "330",
        "320",
    ):
        assert forbidden not in source
