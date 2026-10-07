from dataclasses import dataclass, field, replace

import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.application.ports.tactics import TacticalObservation
from calliope.domain.analysis import (
    CounterfactualBatchRequest,
    CounterfactualProbe,
    ProbeKind,
    ProbeResult,
    TerminalKind,
)
from calliope.domain.chess import ChessMove, Color
from calliope.domain.engine import (
    EngineAnalysis,
    EngineIdentity,
    EngineLimit,
    EngineLine,
    EngineScore,
    EngineSettings,
)
from calliope.errors import (
    EngineAnalysisError,
    IllegalMoveError,
    IncompatibleProbeResultError,
    InvalidProbeRequestError,
    NullMoveNotAllowedError,
)
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.counterfactual.analyzer import DEFAULT_SETTINGS

rules = PythonChessAdapter()
START = rules.position_from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
BEFORE_MATE = rules.position_from_fen(
    "rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2"
)
MATED = rules.position_from_fen("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3")
STALEMATE = rules.position_from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")

BR, ALT, REF, IGN = (
    ProbeKind.BEST_RESPONSE,
    ProbeKind.ALTERNATIVE_MOVE,
    ProbeKind.REFUTATION,
    ProbeKind.IGNORE_THREAT,
)


def mv(uci: str, san: str | None = None) -> ChessMove:
    return ChessMove(uci, san)


@dataclass
class FakeEngine:
    """Records calls; echoes a coherent one-line analysis unless tweaked."""

    calls: list = field(default_factory=list)
    fail_on_call: int | None = None
    tweak: callable = None
    identity: EngineIdentity = field(default_factory=lambda: EngineIdentity("Fake", "1"))

    def analyze(self, position, settings, root_moves=None):
        self.calls.append((position, settings, root_moves))
        if self.fail_on_call == len(self.calls):
            raise EngineAnalysisError("boom")
        first = root_moves[0] if root_moves else mv("a2a3")
        analysis = EngineAnalysis(
            position_id=position.position_id,
            engine=self.identity,
            settings=settings,
            lines=(EngineLine(1, first, EngineScore.cp(-35), (first,)),),
        )
        return self.tweak(analysis, len(self.calls)) if self.tweak else analysis


class Spy:
    """Wraps the real rules adapter and logs port calls."""

    def __init__(self, log):
        self.log = log

    def __getattr__(self, name):
        target = getattr(rules, name)

        def call(*args, **kwargs):
            self.log.append(name)
            return target(*args, **kwargs)

        return call


def make(engine=None, tactical=None, position=None):
    engine = engine or FakeEngine()
    spy = Spy([])
    analyzer = CounterfactualAnalyzer(
        chess=rules,
        engine=engine,
        tactical_rules=tactical or rules,
        position_rules=position or rules,
    )
    return analyzer, engine, spy


def run(probes, settings=DEFAULT_SETTINGS, engine=None, **kw):
    analyzer, engine, _ = make(engine, **kw)
    return analyzer.execute(CounterfactualBatchRequest(tuple(probes), settings)), engine


def best(position=START):
    return CounterfactualProbe(BR, position)


# ---- shape / batch / settings --------------------------------------------------


@pytest.mark.parametrize(
    "probe",
    [
        CounterfactualProbe(BR, START, intervention_move=mv("e2e4")),
        CounterfactualProbe(BR, START, execution_move=mv("e2e4")),
        CounterfactualProbe(ALT, START),
        CounterfactualProbe(ALT, START, mv("e2e4"), mv("e7e5")),
        CounterfactualProbe(REF, START),
        CounterfactualProbe(REF, START, mv("e2e4"), mv("e7e5")),
        CounterfactualProbe(IGN, START, mv("e2e4")),
        CounterfactualProbe(IGN, START, execution_move=mv("e2e4")),
    ],
)
def test_invalid_field_combinations(probe):
    engine = FakeEngine()
    with pytest.raises(InvalidProbeRequestError):
        run([probe], engine=engine)
    assert engine.calls == []


def test_empty_and_oversized_batch():
    with pytest.raises(InvalidProbeRequestError):
        run([])
    probes = [
        CounterfactualProbe(ALT, START, mv(u)) for u in ("e2e4", "d2d4", "g1f3", "c2c4", "b1c3")
    ]
    engine = FakeEngine()
    with pytest.raises(InvalidProbeRequestError):
        run(probes, engine=engine)
    assert engine.calls == []
    result, _ = run(probes[:4])
    assert len(result.results) == 4


def test_duplicate_probe_with_different_san_rejected():
    engine = FakeEngine()
    probes = [
        CounterfactualProbe(ALT, START, mv("e2e4", "e4")),
        CounterfactualProbe(ALT, START, mv("e2e4", "garbage")),
    ]
    with pytest.raises(InvalidProbeRequestError):
        run(probes, engine=engine)
    assert engine.calls == []


def test_duplicate_probe_ignores_whitespace_and_san():
    engine = FakeEngine()
    for first, second in (
        (
            CounterfactualProbe(ALT, START, mv("e2e4")),
            CounterfactualProbe(ALT, START, mv(" e2e4 ")),
        ),
        (
            CounterfactualProbe(REF, START, mv("e2e4", "x")),
            CounterfactualProbe(REF, START, mv("e2e4\t", "y")),
        ),
        (
            CounterfactualProbe(IGN, START, mv("e2e4"), mv("e7e5")),
            CounterfactualProbe(IGN, START, mv(" e2e4"), mv("e7e5 ")),
        ),
    ):
        with pytest.raises(InvalidProbeRequestError):
            run([first, second], engine=engine)
    assert engine.calls == []


def test_duplicate_probe_detects_equivalent_castling_notation():
    castling = rules.position_from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    engine = FakeEngine()
    probes = [
        CounterfactualProbe(REF, castling, mv("e1g1")),
        CounterfactualProbe(REF, castling, mv("e1h1")),
    ]
    with pytest.raises(InvalidProbeRequestError, match="duplicate probe"):
        run(probes, engine=engine)
    assert engine.calls == []


def test_same_move_different_kind_is_not_duplicate():
    _, engine = run(
        [CounterfactualProbe(ALT, START, mv("e2e4")), CounterfactualProbe(REF, START, mv("e2e4"))]
    )
    assert len(engine.calls) == 2


@pytest.mark.parametrize(
    "settings",
    [
        EngineSettings(limit=EngineLimit(depth=8), multipv=1, threads=1),
        EngineSettings(limit=EngineLimit(nodes=1000), multipv=1, threads=1),
        EngineSettings(limit=EngineLimit(time_ms=2001), multipv=1, threads=1),
        EngineSettings(limit=EngineLimit(time_ms=1000), multipv=2, threads=1),
        EngineSettings(limit=EngineLimit(time_ms=1000), multipv=1, threads=2),
        EngineSettings(limit=EngineLimit(time_ms=1000), multipv=1, threads=None),
    ],
)
def test_invalid_settings(settings):
    engine = FakeEngine()
    with pytest.raises(InvalidProbeRequestError):
        run([best()], settings, engine=engine)
    assert engine.calls == []


def test_time_budget_boundaries_and_extra_limits_allowed():
    for limit in (EngineLimit(time_ms=1), EngineLimit(time_ms=2000, depth=10, nodes=5000)):
        settings = EngineSettings(limit=limit, multipv=1, threads=1)
        result, _ = run([best()], settings)
        assert result.settings == settings


# ---- per-kind semantics --------------------------------------------------------


def test_best_response_root_semantics():
    result, engine = run([best()])
    ((position, settings, roots),) = engine.calls
    assert position == START and roots is None and settings == DEFAULT_SETTINGS
    r = result.results[0]
    assert r.analysis_position == START
    assert r.intervention_position is None and r.root_moves is None
    assert r.terminal is None and r.engine_analysis is not None


def test_alternative_move_forced_root_on_base():
    result, engine = run([CounterfactualProbe(ALT, START, mv("e2e4", "bogus"))])
    ((position, _, roots),) = engine.calls
    assert position == START
    assert roots == (ChessMove("e2e4", "e4"),)  # SAN comes from the rules port, not input
    r = result.results[0]
    assert r.intervention_position is None
    assert r.engine_analysis.position_id == START.position_id


def test_refutation_applies_before_analysis():
    result, engine = run([CounterfactualProbe(REF, START, mv("e2e4"))])
    after = rules.apply_move(START, mv("e2e4"))
    ((position, _, roots),) = engine.calls
    assert position == after and roots is None
    r = result.results[0]
    assert r.analysis_position == after and r.intervention_position == after


def test_ignore_threat_reply_then_forced_execution():
    result, engine = run([CounterfactualProbe(IGN, START, mv("e2e4"), mv("e7e5"))])
    after = rules.apply_move(START, mv("e2e4"))
    ((position, _, roots),) = engine.calls
    assert position == after
    assert [m.uci for m in roots] == ["e7e5"]
    r = result.results[0]
    assert r.analysis_position == after and r.intervention_position == after
    assert r.root_moves == roots


def test_batch_preserves_order_and_runs_serially():
    probes = [
        CounterfactualProbe(REF, START, mv("e2e4")),
        best(),
        CounterfactualProbe(ALT, START, mv("d2d4")),
    ]
    result, engine = run(probes)
    assert [r.probe for r in result.results] == probes
    assert [c[0].position_id for c in engine.calls] == [
        rules.apply_move(START, mv("e2e4")).position_id,
        START.position_id,
        START.position_id,
    ]


def test_deterministic_requests():
    probes = [CounterfactualProbe(IGN, START, mv("e2e4"), mv("e7e5")), best()]
    _, e1 = run(probes)
    _, e2 = run(probes)
    assert e1.calls == e2.calls


# ---- legality / preflight ------------------------------------------------------


@pytest.mark.parametrize(
    "probe, error",
    [
        (CounterfactualProbe(ALT, START, mv("e2e5")), IllegalMoveError),
        (CounterfactualProbe(REF, START, mv("e7e5")), IllegalMoveError),
        (CounterfactualProbe(ALT, START, mv("0000")), NullMoveNotAllowedError),
        (CounterfactualProbe(IGN, START, mv("e2e4"), mv("e2e4")), IllegalMoveError),
        (CounterfactualProbe(IGN, START, mv("e2e4"), mv("0000")), NullMoveNotAllowedError),
        (CounterfactualProbe(IGN, START, mv("e2e4"), mv("d2d4")), IllegalMoveError),
    ],
)
def test_illegal_moves_rejected(probe, error):
    engine = FakeEngine()
    with pytest.raises(error):
        run([probe], engine=engine)
    assert engine.calls == []


def test_no_engine_call_before_complete_preflight():
    engine = FakeEngine()
    probes = [
        best(),
        CounterfactualProbe(ALT, START, mv("d2d4")),
        CounterfactualProbe(ALT, START, mv("e2e5")),
    ]
    with pytest.raises(IllegalMoveError):
        run(probes, engine=engine)
    assert engine.calls == []


def test_observation_position_mismatch():
    class WrongTactics:
        def observe_tactics(self, position):
            real = rules.observe_tactics(position)
            return TacticalObservation(
                "pos_other", real.side_to_move, real.legal_moves, real.absolute_pins
            )

    class WrongPosition:
        def observe_position(self, position):
            real = rules.observe_position(position)
            return replace(real, position_id="pos_other")

    for kw in ({"tactical": WrongTactics()}, {"position": WrongPosition()}):
        engine = FakeEngine()
        with pytest.raises(IncompatibleProbeResultError):
            run([best()], engine=engine, **kw)
        assert engine.calls == []


# ---- terminal ------------------------------------------------------------------


def test_checkmate_terminal_without_engine():
    result, engine = run([best(MATED)])
    r = result.results[0]
    assert engine.calls == []
    assert r.engine_analysis is None and r.root_moves is None
    assert r.terminal.kind is TerminalKind.CHECKMATE and r.terminal.winner is Color.BLACK
    assert r.analysis_position == MATED


def test_stalemate_terminal_without_engine():
    result, engine = run([best(STALEMATE)])
    r = result.results[0]
    assert engine.calls == []
    assert r.terminal.kind is TerminalKind.STALEMATE and r.terminal.winner is None


def test_refutation_into_checkmate_is_terminal():
    result, engine = run([CounterfactualProbe(REF, BEFORE_MATE, mv("d8h4"))])
    r = result.results[0]
    assert engine.calls == []
    assert r.analysis_position == MATED and r.intervention_position == MATED
    assert r.terminal.kind is TerminalKind.CHECKMATE and r.terminal.winner is Color.BLACK


def test_unforceable_terminal_requests_rejected():
    engine = FakeEngine()
    with pytest.raises(InvalidProbeRequestError):
        run([CounterfactualProbe(ALT, MATED, mv("e1e2"))], engine=engine)
    with pytest.raises(InvalidProbeRequestError):
        run([CounterfactualProbe(IGN, BEFORE_MATE, mv("d8h4"), mv("e1e2"))], engine=engine)
    assert engine.calls == []


def test_mixed_terminal_and_engine_probes_keep_order():
    result, engine = run([best(MATED), best(), best(STALEMATE)])
    assert [r.terminal is not None for r in result.results] == [True, False, True]
    assert len(engine.calls) == 1


def test_contradictory_terminal_observation_fails_closed():
    class Contradiction:
        def observe_position(self, position):
            real = rules.observe_position(position)
            return replace(real, side_to_move_checkmated=True)

    engine = FakeEngine()
    with pytest.raises(IncompatibleProbeResultError):
        run([best()], engine=engine, position=Contradiction())
    assert engine.calls == []

    class NotInCheck:
        def observe_position(self, position):
            real = rules.observe_position(position)
            return replace(real, side_to_move_in_check=False)

    with pytest.raises(IncompatibleProbeResultError):
        run([best(MATED)], engine=engine, position=NotInCheck())


# ---- engine result integrity ---------------------------------------------------


def _line(analysis, **changes):
    return replace(analysis, lines=(replace(analysis.lines[0], **changes),))


@pytest.mark.parametrize(
    "tweak",
    [
        lambda a, n: replace(a, position_id="pos_other"),
        lambda a, n: replace(
            a, settings=EngineSettings(limit=EngineLimit(time_ms=999), multipv=1, threads=1)
        ),
        lambda a, n: replace(a, lines=a.lines + (replace(a.lines[0], rank=2),)),
    ],
)
def test_engine_binding_mismatch(tweak):
    with pytest.raises(IncompatibleProbeResultError):
        run([best()], engine=FakeEngine(tweak=tweak))


def test_forced_root_mismatch():
    def tweak(a, n):
        other = mv("d2d4")
        return replace(a, lines=(EngineLine(1, other, EngineScore.cp(0), (other,)),))

    with pytest.raises(IncompatibleProbeResultError):
        run([CounterfactualProbe(ALT, START, mv("e2e4"))], engine=FakeEngine(tweak=tweak))


def test_cross_probe_engine_identity_mismatch():
    def tweak(a, n):
        return replace(a, engine=EngineIdentity("Fake", str(n)))

    with pytest.raises(IncompatibleProbeResultError):
        run([best(), CounterfactualProbe(ALT, START, mv("e2e4"))], engine=FakeEngine(tweak=tweak))


def test_engine_exception_propagates_and_no_partial_result():
    engine = FakeEngine(fail_on_call=2)
    with pytest.raises(EngineAnalysisError):
        run([best(), CounterfactualProbe(ALT, START, mv("e2e4")), best(MATED)], engine=engine)
    assert len(engine.calls) == 2


def test_white_pov_and_mate_scores_preserved_verbatim():
    mate = EngineScore.forced_mate(Color.BLACK, 3)

    def tweak(a, n):
        line = a.lines[0]
        return replace(a, lines=(replace(line, score=mate if n == 1 else EngineScore.cp(-120)),))

    result, _ = run(
        [best(), CounterfactualProbe(REF, START, mv("e2e4"))], engine=FakeEngine(tweak=tweak)
    )
    assert result.results[0].engine_analysis.best_line.score is mate
    assert result.results[1].engine_analysis.best_line.score.centipawns == -120


def test_probe_result_invariants():
    r = run([best()])[0].results[0]
    with pytest.raises(ValueError):
        ProbeResult(r.probe, r.analysis_position, None, None, r.engine_analysis, r.terminal or _t())
    with pytest.raises(ValueError):
        ProbeResult(r.probe, r.analysis_position, None, None, None, None)


def _t():
    from calliope.domain.analysis import TerminalKind, TerminalOutcome

    return TerminalOutcome(TerminalKind.STALEMATE, None)
