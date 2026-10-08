"""I3 real-Stockfish gate: the opt-in observation method adds zero engine work.

For every G0 public fixture in both output modes, ``analyze_move_with_observations`` must nest a
result identical to ``analyze_move`` and issue the identical Stockfish analysis/session sequence.
A transparent recorder wraps the production adapters; observation-side rules work must run only
outside the engine request session, and an illegal supplied line must cost no engine call.
"""

import dataclasses
import json
import os
import shutil
import threading
from dataclasses import dataclass, field

import pytest
from test_g0_public import BUDGET, FIXTURES

from calliope import (
    AnalysisOptions,
    AnalyzeMoveRequest,
    ObservedMoveRequest,
    OutputMode,
    SuppliedExchangeObservationRequest,
)
from calliope.adapters.python_chess import PythonChessAdapter
from calliope.adapters.stockfish import StockfishAdapter
from calliope.composition import create_calliope_engine
from calliope.errors import IllegalMoveError

STOCKFISH = os.environ.get("CALLIOPE_STOCKFISH_PATH") or shutil.which("stockfish")
pytestmark = pytest.mark.skipif(STOCKFISH is None, reason="Stockfish binary not available")


@dataclass
class Recorder:
    engine: list = field(default_factory=list)
    observation_calls: list = field(default_factory=list)
    active: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def clear(self):
        self.engine.clear()
        self.observation_calls.clear()


@pytest.fixture(scope="module")
def recorder():
    rec = Recorder()
    patch = pytest.MonkeyPatch()
    analyze, session = StockfishAdapter.analyze, StockfishAdapter.request_session

    def observe_analyze(self, position, settings, root_moves=None):
        result = analyze(self, position, settings, root_moves)
        rec.engine.append(
            (
                "engine",
                position.position_id,
                settings,
                tuple(m.uci for m in root_moves or ()),
                tuple(line.depth for line in result.lines),
                rec.active,
            )
        )
        return result

    def observe_session(self):
        inner = session(self)

        class Observed:
            def __enter__(self_):
                inner.__enter__()
                rec.active = True
                rec.engine.append(("acquire",))

            def __exit__(self_, *exc):
                rec.engine.append(("release",))
                rec.active = False
                return inner.__exit__(*exc)

        return Observed()

    patch.setattr(StockfishAdapter, "analyze", observe_analyze)
    patch.setattr(StockfishAdapter, "request_session", observe_session)
    for name in ("observe_position", "observe_tactics"):
        original = getattr(PythonChessAdapter, name)

        def spy(self, position, _original=original, _name=name):
            rec.observation_calls.append((_name, rec.active))
            return _original(self, position)

        patch.setattr(PythonChessAdapter, name, spy)
    yield rec
    patch.undo()


@pytest.fixture(scope="module")
def engine(recorder):
    with create_calliope_engine(STOCKFISH) as composed:  # type: ignore[arg-type]
        yield composed


def base_request(name, mode):
    fen, move = FIXTURES[name][:2]
    return AnalyzeMoveRequest(
        fen=fen, move_uci=move, options=AnalysisOptions(budget=BUDGET, output_mode=mode)
    )


def canonical(result):
    return json.dumps(dataclasses.asdict(result), sort_keys=True, separators=(",", ":"))


@pytest.mark.parametrize("mode", list(OutputMode))
@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_opt_in_nests_legacy_and_adds_no_engine_work(engine, recorder, name, mode):
    base = base_request(name, mode)
    recorder.clear()
    legacy = engine.analyze_move(base)
    legacy_engine = list(recorder.engine)
    legacy_observation = list(recorder.observation_calls)

    recorder.clear()
    focus = base.move_uci[2:4]
    lines = (
        SuppliedExchangeObservationRequest(focus, (base.move_uci,)),
        SuppliedExchangeObservationRequest(focus, ()),
    )
    observed = engine.analyze_move_with_observations(ObservedMoveRequest(base, True, lines))

    assert observed.schema_version == "0.3"
    assert observed.base_result == legacy
    assert canonical(observed.base_result) == canonical(legacy)
    assert recorder.engine == legacy_engine, "opt-in changed the Stockfish work"
    assert all(event[-1] for event in recorder.engine if event[0] == "engine")
    # Legacy P4-P9 observations are unchanged; every additional one is outside the session.
    extra = recorder.observation_calls[len(legacy_observation) :]
    assert recorder.observation_calls[: len(legacy_observation)] == legacy_observation
    assert extra and not any(active for _, active in extra)
    sections = (observed.played, *observed.exchange_lines)
    assert all(len(s.sentences) <= 2 for s in sections)
    ids = [s.observation_id for section in sections for s in section.sentences]
    assert len(ids) == len(set(ids))
    if mode is OutputMode.COMMENTARY:
        commentary = observed.base_result.commentary
        assert len(commentary.sentences) == len(commentary.used_claim_ids)
        assert not any(s.text in commentary.text for sec in sections for s in sec.sentences)


def test_illegal_supplied_line_costs_no_engine_call(engine, recorder):
    base = base_request("quiet_best_silence", OutputMode.STRUCTURED)
    recorder.clear()
    bad = SuppliedExchangeObservationRequest("e4", ("e2e4", "e7e5", "e4e5"))
    with pytest.raises(IllegalMoveError):
        engine.analyze_move_with_observations(ObservedMoveRequest(base, True, (bad,)))
    assert recorder.engine == []
