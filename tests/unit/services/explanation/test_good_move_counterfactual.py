"""P9 compatibility checks over real P7 execution, with post-return tampering only."""

import ast
import inspect
import textwrap
from dataclasses import FrozenInstanceError, fields, replace
from types import SimpleNamespace

import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis import ProbeKind, TerminalKind, TerminalOutcome
from calliope.domain.chess import ChessMove, Color
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
    EngineAnalysisError,
    EngineClosedError,
    EngineConfigurationError,
    EngineStartupError,
    IllegalMoveError,
    IncompatibleGoodMoveContextError,
    IncompatibleProbeResultError,
    InvalidEngineOutputError,
    InvalidProbeRequestError,
    InvalidUciError,
    NullMoveNotAllowedError,
)
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.explanation import GoodMoveExplainer
from calliope.services.explanation.good_move import GoodMoveCounterfactualContext
from calliope.services.explanation.piece_identity import BasePieceIdentityMap
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.tactics import TacticalDetector

rules = PythonChessAdapter()
START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
QUEEN = "7k/8/6K1/8/8/8/8/5Q2 w - - 0 1"
SETTINGS = EngineSettings(EngineLimit(time_ms=37), multipv=1, threads=1, hash_mb=16)
IDENTITY = EngineIdentity("Scripted P7", "1")


class Forbidden:
    def __getattr__(self, name):
        raise AssertionError(f"I3 accessed deterministic dependency: {name}")


class ScriptedEngine:
    def __init__(self):
        self.calls = []
        self.error = None
        self.transform = lambda value: value

    def analyze(self, position, settings, root_moves=None):
        self.calls.append((position, settings, root_moves))
        if self.error is not None:
            raise self.error
        move = (root_moves or rules.observe_tactics(position).legal_moves)[0]
        # Deliberately nonsensical PV suffix: I3 must not replay it.
        line = EngineLine(
            1, move, EngineScore.forced_mate(Color.BLACK, 3), (move, ChessMove("a1a8"))
        )
        return self.transform(EngineAnalysis(position.position_id, IDENTITY, settings, (line,)))


class RecordingP7:
    """Delegate every call to real P7, then alter returned evidence if requested."""

    def __init__(self, engine):
        self.delegate = CounterfactualAnalyzer(rules, engine, rules, rules)
        self.calls = []
        self.transform = lambda value: value

    def execute(self, request):
        self.calls.append(request)
        return self.transform(self.delegate.execute(request))


def scenario(count=2, *, fen=START, moves=("e2e4", "d2d4", "g1f3")):
    base = rules.position_from_fen(fen)
    engine = ScriptedEngine()
    p7 = RecordingP7(engine)
    facts = PositionFactExtractor(rules)
    explainer = GoodMoveExplainer(
        rules, facts, BoardDeltaAnalyzer(rules, facts), rules, TacticalDetector(), p7
    )
    lines = tuple(
        EngineLine(i, ChessMove(u), EngineScore.cp(0), (ChessMove(u),))
        for i, u in enumerate(moves[: count + 1], start=1)
    )
    analysis = EngineAnalysis(
        base.position_id,
        EngineIdentity("Different P3 engine"),
        EngineSettings(EngineLimit(depth=4)),
        lines,
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
    deterministic = explainer.build_branches(prepared)
    explainer.facts = explainer.delta = explainer.detector = explainer.tactical_rules = Forbidden()
    return explainer, deterministic, p7, engine


def view(value, **changes):
    """Model malformed external evidence without bypassing domain constructors."""
    values = {field.name: getattr(value, field.name) for field in fields(value)}
    values.update(changes)
    return SimpleNamespace(**values)


def change_result(batch, transform, index=0):
    results = list(batch.results)
    results[index] = transform(results[index])
    return replace(batch, results=tuple(results))


@pytest.mark.parametrize("count", [0, 1, 2])
@pytest.mark.parametrize("with_b", [False, True])
def test_protocol_order_exact_settings_and_budget(count, with_b):
    explainer, deterministic, p7, engine = scenario(count)
    context = explainer.verify_counterfactuals(deterministic, SETTINGS)
    assert context.deterministic is deterministic and context.settings is SETTINGS
    assert context.batch_a.settings is SETTINGS
    assert context.engine_identity == IDENTITY
    assert context.engine_identity != deterministic.prepared.position_analysis.engine
    request = p7.calls[0]
    assert request.settings is SETTINGS
    assert tuple(p.kind for p in request.probes) == (ProbeKind.REFUTATION,) * (count + 1)
    assert tuple(p.intervention_move for p in request.probes) == (
        deterministic.prepared.played_move,
        *(a.move for a in deterministic.prepared.alternatives),
    )
    assert all(
        p.base is deterministic.prepared.base and p.execution_move is None for p in request.probes
    )
    assert context.played_refutation is context.batch_a.results[0]
    assert (
        tuple(a.alternative for a in context.alternative_refutations)
        == deterministic.prepared.alternatives
    )
    assert all(
        a.result is r
        for a, r in zip(context.alternative_refutations, context.batch_a.results[1:], strict=True)
    )
    assert context.batch_b is context.ignored_response is context.ignored_response_result is None
    assert len(p7.calls) == 1
    for result, branch in zip(
        context.batch_a.results,
        (deterministic.played, *(a.branch for a in deterministic.alternatives)),
        strict=True,
    ):
        assert result.analysis_position == result.intervention_position == branch.position
        assert result.root_moves is None
        assert result.engine_analysis.settings is SETTINGS
        assert result.engine_analysis.position_id == branch.position.position_id
        assert result.engine_analysis.best_line.rank == 1
    if with_b:
        original = context
        context = explainer.verify_ignored_response(context, ChessMove(" e7e5 "))
        assert context.ignored_response.uci == "e7e5"
        assert context.batch_a is original.batch_a and original.batch_b is None
        assert context.ignored_response_result is context.batch_b.results[0]
        request = p7.calls[1]
        assert request.settings is SETTINGS and len(request.probes) == 1
        probe = request.probes[0]
        assert probe.kind is ProbeKind.IGNORE_THREAT
        assert probe.base is deterministic.prepared.base
        assert probe.intervention_move == deterministic.prepared.played_move
        assert probe.execution_move == context.ignored_response
        assert context.ignored_response_result.root_moves == (context.ignored_response,)
        assert engine.calls[-1] == (
            deterministic.played.position,
            SETTINGS,
            (context.ignored_response,),
        )
        with pytest.raises(IncompatibleGoodMoveContextError):
            explainer.verify_ignored_response(context, ChessMove("d7d5"))
    assert context.probe_count == count + 1 + int(with_b) <= 4
    assert len(p7.calls) == 1 + int(with_b)
    assert len(engine.calls) == context.probe_count


@pytest.mark.parametrize(
    "which",
    [
        "prepared_third",
        "branches_third",
        "both_third",
        "count",
        "played",
        "metadata",
        "alt_move",
        "base_anchor",
        "root",
        "branch_binding",
    ],
)
def test_deterministic_tampering_rejected_before_p7(which):
    explainer, d, p7, engine = scenario()
    a = d.alternatives[0]
    if which in {"prepared_third", "both_third"}:
        d = replace(
            d, prepared=replace(d.prepared, alternatives=(*d.prepared.alternatives, a.alternative))
        )
    if which in {"branches_third", "both_third"}:
        d = replace(d, alternatives=(*d.alternatives, a))
    if which == "count":
        d = replace(d, alternatives=d.alternatives[:1])
    if which == "played":
        d = replace(d, played=replace(d.played, move=ChessMove("d2d4")))
    if which == "metadata":
        d = replace(
            d,
            alternatives=(
                replace(a, alternative=replace(a.alternative, rank=9)),
                d.alternatives[1],
            ),
        )
    if which == "alt_move":
        d = replace(
            d,
            alternatives=(
                replace(a, branch=replace(a.branch, move=ChessMove("c2c4"))),
                d.alternatives[1],
            ),
        )
    if which == "base_anchor":
        d = replace(
            d,
            played=replace(d.played, identity=replace(d.played.identity, base_position_id="wrong")),
        )
    if which == "root":
        d = replace(d, root_identity=replace(d.root_identity, position_id="wrong"))
    if which == "branch_binding":
        d = replace(d, played=replace(d.played, facts=replace(d.played.facts, position_id="wrong")))
    with pytest.raises(IncompatibleGoodMoveContextError):
        explainer.verify_counterfactuals(d, SETTINGS)
    assert p7.calls == engine.calls == []


def corrupt(batch, kind):
    if kind == "settings":
        return replace(batch, settings=replace(SETTINGS, hash_mb=32))
    if kind == "short":
        return replace(batch, results=batch.results[:-1])
    if kind == "extra":
        return replace(batch, results=(*batch.results, batch.results[0]))
    if kind == "order":
        return replace(batch, results=tuple(reversed(batch.results)))

    def change(r):
        a = r.engine_analysis
        if kind == "probe":
            return replace(r, probe=replace(r.probe, kind=ProbeKind.ALTERNATIVE_MOVE))
        if kind == "intervention":
            return replace(r, intervention_position=r.probe.base)
        if kind == "position":
            return view(r, analysis_position=r.probe.base)
        if kind == "roots":
            return replace(r, root_moves=(ChessMove("a7a6"),))
        if kind == "terminal":
            return view(
                r,
                engine_analysis=None,
                root_moves=None,
                terminal=TerminalOutcome(TerminalKind.STALEMATE, None),
            )
        if kind == "engine_settings":
            return replace(r, engine_analysis=replace(a, settings=replace(SETTINGS, hash_mb=32)))
        if kind == "engine_position":
            return view(r, engine_analysis=replace(a, position_id="wrong"))
        if kind == "lines":
            return replace(
                r, engine_analysis=replace(a, lines=(*a.lines, replace(a.lines[0], rank=2)))
            )
        if kind == "rank":
            return view(r, engine_analysis=view(a, lines=(replace(a.lines[0], rank=2),)))
        if kind == "identity":
            return replace(r, engine_analysis=replace(a, engine=EngineIdentity("Other")))
        if kind == "missing_identity":
            return replace(r, engine_analysis=replace(a, engine=None))
        if kind == "first_move":
            move = ChessMove("a7a6")
            return replace(
                r,
                engine_analysis=replace(
                    a, lines=(replace(a.lines[0], first_move=move, pv=(move,)),)
                ),
            )
        raise AssertionError(kind)

    return change_result(batch, change)


@pytest.mark.parametrize(
    "kind",
    [
        "settings",
        "short",
        "extra",
        "order",
        "probe",
        "intervention",
        "position",
        "roots",
        "terminal",
        "engine_settings",
        "engine_position",
        "lines",
        "rank",
        "identity",
        "missing_identity",
    ],
)
def test_batch_a_returned_evidence_compatibility(kind):
    explainer, d, p7, engine = scenario()
    p7.transform = lambda b: corrupt(b, kind)
    with pytest.raises(IncompatibleGoodMoveContextError):
        explainer.verify_counterfactuals(d, SETTINGS)
    assert len(p7.calls) == 1 and len(engine.calls) == 3


@pytest.mark.parametrize(
    "kind",
    [
        "settings",
        "short",
        "extra",
        "probe",
        "intervention",
        "position",
        "roots",
        "terminal",
        "engine_settings",
        "engine_position",
        "lines",
        "rank",
        "identity",
        "missing_identity",
        "first_move",
    ],
)
def test_batch_b_returned_evidence_compatibility(kind):
    explainer, d, p7, engine = scenario()
    context = explainer.verify_counterfactuals(d, SETTINGS)
    p7.transform = lambda b: corrupt(b, kind)
    with pytest.raises(IncompatibleGoodMoveContextError):
        explainer.verify_ignored_response(context, ChessMove("e7e5"))
    assert len(p7.calls) == 2 and len(engine.calls) == 4
    assert context.batch_b is None


@pytest.mark.parametrize(
    "moves,terminal",
    [
        (("f1f8", "f1f7"), TerminalOutcome(TerminalKind.CHECKMATE, Color.WHITE)),
        (("f1f7", "f1f8"), TerminalOutcome(TerminalKind.STALEMATE, None)),
    ],
)
def test_all_terminal_exact_outcomes_no_engine_and_no_batch_b(moves, terminal):
    explainer, d, p7, engine = scenario(1, fen=QUEEN, moves=moves)
    context = explainer.verify_counterfactuals(d, SETTINGS)
    assert context.played_refutation.terminal == terminal
    assert context.alternative_refutations[0].result.terminal != terminal
    assert context.engine_identity is None and engine.calls == []
    assert context.probe_count == 2
    with pytest.raises(IncompatibleGoodMoveContextError):
        explainer.verify_ignored_response(context, ChessMove("h8g8"))
    assert len(p7.calls) == 1


@pytest.mark.parametrize("moves", [("f1f8", "f1f6"), ("f1f6", "f1f7")])
def test_mixed_terminal_evidence_retains_nonterminal_identity(moves):
    explainer, d, p7, engine = scenario(1, fen=QUEEN, moves=moves)
    context = explainer.verify_counterfactuals(d, SETTINGS)
    assert context.engine_identity == IDENTITY and len(engine.calls) == 1
    assert len(p7.calls) == 1


@pytest.mark.parametrize("played", ["f1f8", "f1f7"])
@pytest.mark.parametrize(
    "terminal",
    [
        TerminalOutcome(TerminalKind.CHECKMATE, Color.BLACK),
        TerminalOutcome(TerminalKind.CHECKMATE, None),
        TerminalOutcome(TerminalKind.STALEMATE, Color.WHITE),
    ],
)
def test_terminal_wrong_kind_or_winner_rejected(played, terminal):
    explainer, d, p7, _ = scenario(0, fen=QUEEN, moves=(played,))
    p7.transform = lambda b: change_result(b, lambda r: replace(r, terminal=terminal))
    with pytest.raises(IncompatibleGoodMoveContextError):
        explainer.verify_counterfactuals(d, SETTINGS)


@pytest.mark.parametrize(
    "field",
    [
        "batch_b",
        "ignored_response",
        "ignored_response_result",
        "engine_identity",
        "played_refutation",
        "alternative_refutations",
    ],
)
def test_batch_b_retained_context_tampering_preflight(field):
    explainer, d, p7, _ = scenario()
    context = explainer.verify_counterfactuals(d, SETTINGS)
    value = {
        "batch_b": context.batch_a,
        "ignored_response": ChessMove("e7e5"),
        "ignored_response_result": context.played_refutation,
        "engine_identity": None,
        "played_refutation": context.batch_a.results[1],
        "alternative_refutations": (),
    }[field]
    with pytest.raises(IncompatibleGoodMoveContextError):
        explainer.verify_ignored_response(replace(context, **{field: value}), ChessMove("e7e5"))
    assert len(p7.calls) == 1


@pytest.mark.parametrize(
    "uci,error_type",
    [("e2e4", IllegalMoveError), ("bad", InvalidUciError), ("0000", NullMoveNotAllowedError)],
)
def test_response_error_translation_retains_cause_before_p7(uci, error_type):
    explainer, d, p7, _ = scenario()
    context = explainer.verify_counterfactuals(d, SETTINGS)
    with pytest.raises(IncompatibleGoodMoveContextError) as caught:
        explainer.verify_ignored_response(context, ChessMove(uci))
    assert isinstance(caught.value.__cause__, error_type)
    assert len(p7.calls) == 1


def test_response_castling_alias_is_canonicalized_on_played_position():
    fen = "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"
    explainer, d, p7, _ = scenario(0, fen=fen, moves=("a1a2",))
    context = explainer.verify_counterfactuals(d, SETTINGS)
    result = explainer.verify_ignored_response(context, ChessMove("e8h8"))
    assert result.ignored_response.uci == "e8g8"
    assert p7.calls[-1].probes[0].execution_move.uci == "e8g8"


@pytest.mark.parametrize(
    "settings",
    [
        EngineSettings(EngineLimit(depth=4)),
        replace(SETTINGS, multipv=2),
        replace(SETTINGS, threads=2),
        replace(SETTINGS, limit=EngineLimit(time_ms=2001)),
    ],
)
def test_invalid_settings_propagate_real_p7_error_without_repair(settings):
    explainer, d, p7, engine = scenario()
    with pytest.raises(InvalidProbeRequestError):
        explainer.verify_counterfactuals(d, settings)
    assert p7.calls[0].settings is settings and engine.calls == []


@pytest.mark.parametrize("with_b", [False, True])
@pytest.mark.parametrize(
    "error_type",
    [
        EngineStartupError,
        EngineConfigurationError,
        EngineAnalysisError,
        InvalidEngineOutputError,
        EngineClosedError,
    ],
)
def test_engine_errors_propagate_exact_instance(error_type, with_b):
    explainer, d, p7, engine = scenario()
    context = explainer.verify_counterfactuals(d, SETTINGS) if with_b else None
    error = error_type("scripted engine failure")
    engine.error = error
    with pytest.raises(error_type) as caught:
        if with_b:
            explainer.verify_ignored_response(context, ChessMove("e7e5"))
        else:
            explainer.verify_counterfactuals(d, SETTINGS)
    assert caught.value is error and len(p7.calls) == 1 + int(with_b)


@pytest.mark.parametrize("with_b", [False, True])
def test_real_p7_incompatibility_propagates(with_b):
    explainer, d, p7, engine = scenario()
    context = explainer.verify_counterfactuals(d, SETTINGS) if with_b else None
    engine.transform = lambda a: replace(a, settings=replace(SETTINGS, hash_mb=32))
    with pytest.raises(IncompatibleProbeResultError):
        if with_b:
            explainer.verify_ignored_response(context, ChessMove("e7e5"))
        else:
            explainer.verify_counterfactuals(d, SETTINGS)
    assert len(p7.calls) == 1 + int(with_b)


def test_contexts_frozen_and_slotted():
    explainer, d, _, _ = scenario()
    context = explainer.verify_counterfactuals(d, SETTINGS)
    for value in (context, context.alternative_refutations[0]):
        assert not hasattr(value, "__dict__")
        field = fields(value)[0].name
        with pytest.raises(FrozenInstanceError):
            setattr(value, field, getattr(value, field))
    assert not {f.name for f in fields(GoodMoveCounterfactualContext)} & {
        "played_strictly_better",
        "alternative_worse",
        "evaluation_cliff",
    }


def test_i3_never_reads_numeric_evidence_or_advances_identity(monkeypatch):
    explainer, d, _, _ = scenario()

    def forbidden(*args, **kwargs):
        raise AssertionError("I3 accessed numeric evidence or advanced identity")

    # Prebuild engine evidence before guarding score/PV access.
    cache = {}
    engine = explainer.counterfactual.delegate.engine
    for branch in (d.played, *(a.branch for a in d.alternatives)):
        cache[(branch.position.position_id, None)] = engine.analyze(branch.position, SETTINGS)
    q = rules.legal_move_from_uci(d.played.position, "e7e5")
    cache[(d.played.position.position_id, (q,))] = engine.analyze(d.played.position, SETTINGS, (q,))
    engine.analyze = lambda position, settings, root_moves=None: cache[
        (position.position_id, root_moves)
    ]
    with monkeypatch.context() as patch:
        patch.setattr(BasePieceIdentityMap, "advance", forbidden)
        for cls, names in (
            (MoveJudgement, ("best_score", "played_score", "cp_loss", "expected_score_loss")),
            (Forcedness, ("acceptable_move_count", "best_to_second_gap_cp")),
            (EngineLine, ("score", "wdl", "pv")),
        ):
            for name in names:
                patch.setattr(cls, name, property(forbidden))
        context = explainer.verify_counterfactuals(d, SETTINGS)
        assert explainer.verify_ignored_response(context, q).probe_count == 4


def test_i3_source_boundary():
    methods = (
        GoodMoveExplainer.verify_counterfactuals,
        GoodMoveExplainer.verify_ignored_response,
        GoodMoveExplainer._counterfactual_branches,
        GoodMoveExplainer._refutation_request,
        GoodMoveExplainer._check_counterfactual_batch,
        GoodMoveExplainer._counterfactual_identity,
    )
    tree = ast.parse("\n".join(textwrap.dedent(inspect.getsource(m)) for m in methods))
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not attributes & {
        "extract",
        "analyze",
        "detect",
        "advance",
        "pv",
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
    }
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {
        "GoodMoveBenefitKind",
        "GoodMoveBenefitResult",
        "GoodMoveExplanationResult",
        "TacticalCandidateStatus",
    }


def test_black_mover_protocol():
    fen = "4k3/8/2n5/8/3P4/8/8/4K3 b - - 0 1"
    explainer, d, p7, _ = scenario(2, fen=fen, moves=("c6e5", "c6b4", "c6a5"))
    context = explainer.verify_counterfactuals(d, SETTINGS)
    q = d.played.rules.legal_moves[0]
    result = explainer.verify_ignored_response(context, q)
    assert result.probe_count == 4 and len(p7.calls) == 2
    assert result.ignored_response_result.analysis_position.side_to_move is Color.WHITE


@pytest.mark.parametrize(
    "played,terminal",
    [
        ("f1f8", TerminalOutcome(TerminalKind.STALEMATE, None)),
        ("f1f7", TerminalOutcome(TerminalKind.CHECKMATE, Color.WHITE)),
    ],
)
def test_terminal_kind_contradiction_with_otherwise_valid_outcome(played, terminal):
    explainer, d, p7, _ = scenario(0, fen=QUEEN, moves=(played,))
    p7.transform = lambda b: change_result(b, lambda r: replace(r, terminal=terminal))
    with pytest.raises(IncompatibleGoodMoveContextError):
        explainer.verify_counterfactuals(d, SETTINGS)


@pytest.mark.parametrize("played", ["f1f8", "f1f7"])
def test_engine_evidence_for_terminal_branch_rejected(played):
    explainer, d, p7, _ = scenario(0, fen=QUEEN, moves=(played,))
    move = ChessMove("h8g8")
    analysis = EngineAnalysis(
        d.played.position.position_id,
        IDENTITY,
        SETTINGS,
        (EngineLine(1, move, EngineScore.cp(0), (move,)),),
    )
    p7.transform = lambda b: change_result(
        b, lambda r: replace(r, engine_analysis=analysis, terminal=None)
    )
    with pytest.raises(IncompatibleGoodMoveContextError):
        explainer.verify_counterfactuals(d, SETTINGS)


def test_batch_b_revalidates_alternative_budget_before_second_call():
    explainer, d, p7, _ = scenario()
    context = explainer.verify_counterfactuals(d, SETTINGS)
    d = replace(d, alternatives=(*d.alternatives, d.alternatives[0]))
    with pytest.raises(IncompatibleGoodMoveContextError):
        explainer.verify_ignored_response(replace(context, deterministic=d), ChessMove("e7e5"))
    assert len(p7.calls) == 1


def test_response_owning_layer_operational_error_propagates():
    explainer, d, p7, _ = scenario()
    context = explainer.verify_counterfactuals(d, SETTINGS)
    error = EngineAnalysisError("owning chess dependency error")

    class FailingChess:
        def legal_move_from_uci(self, position, uci):
            raise error

    explainer.chess = FailingChess()
    with pytest.raises(EngineAnalysisError) as caught:
        explainer.verify_ignored_response(context, ChessMove("e7e5"))
    assert caught.value is error and len(p7.calls) == 1
