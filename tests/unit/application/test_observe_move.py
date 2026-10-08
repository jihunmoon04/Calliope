"""I3 opt-in observation service over deterministic legacy fakes and real python-chess rules."""

from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest
from _g0_fakes import FEN, MOVE, build, request

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.application import observe_move
from calliope.application.observe_move import ObservedMoveService, observation_id, source_view
from calliope.contracts import (
    OBSERVATION_SCHEMA_VERSION,
    ObservedMoveRequest,
    OutputMode,
    SuppliedExchangeObservationRequest,
)
from calliope.domain.analysis.bad_move import BasePieceRef
from calliope.domain.analysis.delta import PieceTransitionKind
from calliope.domain.analysis.scenario import (
    ActivitySource,
    Bucket,
    CaptureKey,
    CaptureSource,
    CountKey,
    CountView,
    EventKind,
    FactKind,
    FileKey,
    FileSource,
    HistorySource,
    MaterialSource,
    PawnSource,
    PinKey,
    PinSource,
    RayKey,
    RaySource,
    SnapshotKey,
    SquareKey,
    SquareSource,
    StepKey,
    SubjectKey,
    TransitionKey,
    TransitionSource,
)
from calliope.domain.chess import Color, PieceType
from calliope.errors import (
    EngineAnalysisError,
    IllegalMoveError,
    InvalidScenarioRequestError,
    InvalidScenarioSummaryError,
    ObservationProjectionError,
)
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.position.activity import ActivityAnalyzer, ActivityLineAnalyzer
from calliope.services.position.line import LineAnalyzer
from calliope.services.position.positional import PositionAnalyzer, TransitionAnalyzer
from calliope.services.position.scenario import ScenarioLineAnalyzer

CAPTURE_LINE = SuppliedExchangeObservationRequest("d5", ("c3d5",))
RECAPTURE_LINE = SuppliedExchangeObservationRequest("e4", ("c3e4", "d5e4"))


@dataclass
class LoggedRules:
    """Real python-chess rules that log each call together with the session state."""

    log: list
    sessions: object
    inner: PythonChessAdapter

    def __getattr__(self, name):
        method = getattr(self.inner, name)

        def call(*args, **kwargs):
            self.log.append(("rules", name, self.sessions.active))
            return method(*args, **kwargs)

        return call


def observed(world):
    rules = LoggedRules(world.log, world.sessions, PythonChessAdapter())
    facts = PositionFactExtractor(rules)
    positions = PositionAnalyzer(facts)
    scenarios = ScenarioLineAnalyzer(
        ActivityLineAnalyzer(
            LineAnalyzer(TransitionAnalyzer(rules, positions, BoardDeltaAnalyzer(rules, facts))),
            ActivityAnalyzer(positions, rules),
        )
    )
    return ObservedMoveService(world.service, rules, scenarios)


def engine_events(log):
    return [e for e in log if e[0] in ("acquire", "release", "engine")]


@pytest.mark.parametrize("mode", list(OutputMode))
def test_nested_result_is_the_exact_legacy_result_with_no_extra_engine_work(mode):
    legacy_world = build()
    legacy = legacy_world.service.execute(request(mode=mode))
    world = build()
    result = observed(world).execute(
        ObservedMoveRequest(request(mode=mode), True, (CAPTURE_LINE, RECAPTURE_LINE))
    )
    assert result.schema_version == OBSERVATION_SCHEMA_VERSION == "0.3"
    assert result.base_result == legacy and result.base_result.schema_version == "0.2"
    assert engine_events(world.log) == engine_events(legacy_world.log)
    if mode is OutputMode.COMMENTARY:
        commentary = result.base_result.commentary
        assert len(commentary.sentences) == len(commentary.used_claim_ids)
        for section in (result.played, *result.exchange_lines):
            for sentence in section.sentences:
                assert sentence.text not in commentary.text
    else:
        assert result.base_result.commentary is None
    assert result.played.label == "Observed facts after the played move"
    assert result.played.scope == "played_transition"
    assert result.played.supplied_line_uci == (MOVE.uci,)
    assert (result.played.focus_square, result.played.status) == (None, None)
    assert [s.scope for s in result.exchange_lines] == ["supplied_line_exchange"] * 2
    assert [s.focus_square for s in result.exchange_lines] == ["d5", "e4"]
    assert [s.status for s in result.exchange_lines] == ["FOCUS_CAPTURES_OBSERVED"] * 2
    assert [s.focus_capture_count for s in result.exchange_lines] == [1, 1]
    sections = (result.played, *result.exchange_lines)
    assert all(len(s.sentences) <= 2 for s in sections)
    ids = [s.observation_id for section in sections for s in section.sentences]
    assert len(ids) == len(set(ids)) <= 6
    assert all(
        i.split("/")[1] == p
        for section, p in zip(sections, ("p", "x0", "x1"))
        for i in (s.observation_id for s in section.sentences)
    )


def test_rules_work_brackets_the_engine_session():
    world = build()
    observed(world).execute(ObservedMoveRequest(request(), True, (RECAPTURE_LINE,)))
    acquire = world.log.index(("acquire",))
    release = world.log.index(("release",))
    rules = [(i, e) for i, e in enumerate(world.log) if e[0] == "rules"]
    assert all(not active for _, (_, _, active) in rules), "observation work inside a session"
    before = [e[1] for i, e in rules if i < acquire]
    after = [e[1] for i, e in rules if i > release]
    # Preflight: FEN, the played move once, then the supplied line move by move.
    assert before == [
        "position_from_fen",
        "legal_move_from_uci",
        "legal_move_from_uci",
        "apply_move",
        "legal_move_from_uci",
        "apply_move",
    ]
    assert "observe_position" in after and "observe_tactics" in after
    assert not any(acquire < i < release for i, _ in rules)


BAD_REQUESTS = {
    "not_request": lambda: request(),
    "base_type": lambda: ObservedMoveRequest(SimpleNamespace(fen=FEN, move_uci=MOVE.uci)),
    "played_flag": lambda: ObservedMoveRequest(request(), 1),
    "lines_list": lambda: ObservedMoveRequest(request(), True, [CAPTURE_LINE]),
    "three_lines": lambda: ObservedMoveRequest(
        request(),
        True,
        (CAPTURE_LINE, RECAPTURE_LINE, SuppliedExchangeObservationRequest("e4", ())),
    ),
    "nine_plies": lambda: ObservedMoveRequest(
        request(), True, (SuppliedExchangeObservationRequest("d5", ("c3d5",) * 9),)
    ),
    "uppercase": lambda: ObservedMoveRequest(
        request(), True, (SuppliedExchangeObservationRequest("d5", ("C3D5",)),)
    ),
    "whitespace": lambda: ObservedMoveRequest(
        request(), True, (SuppliedExchangeObservationRequest("d5", ("c3d5 ",)),)
    ),
    "bad_focus": lambda: ObservedMoveRequest(
        request(), True, (SuppliedExchangeObservationRequest("d9", ("c3d5",)),)
    ),
    "moves_list": lambda: ObservedMoveRequest(
        request(), True, (SuppliedExchangeObservationRequest("d5", ["c3d5"]),)
    ),
    "duplicate": lambda: ObservedMoveRequest(request(), True, (CAPTURE_LINE, CAPTURE_LINE)),
    "no_section": lambda: ObservedMoveRequest(request(), False, ()),
}


@pytest.mark.parametrize("name", sorted(BAD_REQUESTS))
def test_shape_preflight_rejects_before_any_rules_or_engine_work(name):
    world = build()
    with pytest.raises(InvalidScenarioRequestError):
        observed(world).execute(BAD_REQUESTS[name]())
    assert world.log == []


def test_illegal_supplied_move_is_rejected_before_the_legacy_call():
    world = build()
    line = SuppliedExchangeObservationRequest("e4", ("c3e4", "d5d4", "e4d5"))
    with pytest.raises(IllegalMoveError):
        observed(world).execute(ObservedMoveRequest(request(), True, (line,)))
    assert engine_events(world.log) == []
    assert not any(e[0] in ("fen", "move", "judge") for e in world.log)


def test_illegal_played_move_is_rejected_before_the_legacy_call():
    world = build()
    base = replace(request(), move_uci="c3c4")
    with pytest.raises(IllegalMoveError):
        observed(world).execute(ObservedMoveRequest(base))
    assert engine_events(world.log) == []


def test_exchange_only_and_empty_line_sections():
    world = build()
    result = observed(world).execute(
        ObservedMoveRequest(request(), False, (SuppliedExchangeObservationRequest("e4", ()),))
    )
    assert result.played is None
    (section,) = result.exchange_lines
    assert (section.status, section.focus_capture_count, section.sentences) == (
        "NO_FOCUS_CAPTURE",
        0,
        (),
    )


def test_legacy_errors_propagate_unchanged_and_nothing_is_observed():
    world = build()
    world.engine.fail_on_call = 1
    with pytest.raises(EngineAnalysisError):
        observed(world).execute(ObservedMoveRequest(request(), True, (CAPTURE_LINE,)))
    assert not any(e[:2] == ("rules", "observe_position") for e in world.log)


def test_legacy_anchor_mismatch_is_a_projection_error():
    world = build()
    service = observed(world)
    legacy = world.service.execute(request())
    stub = SimpleNamespace(execute=lambda _: replace(legacy, metadata={"position_id": "pos_x"}))
    with pytest.raises(ObservationProjectionError):
        ObservedMoveService(stub, service.chess, service.scenarios).execute(
            ObservedMoveRequest(request())
        )
    stub = SimpleNamespace(
        execute=lambda _: replace(legacy, judgement=replace(legacy.judgement, move_uci="c3b5"))
    )
    with pytest.raises(ObservationProjectionError):
        ObservedMoveService(stub, service.chess, service.scenarios).execute(
            ObservedMoveRequest(request())
        )


def test_observation_failure_is_atomic(monkeypatch):
    calls = []
    real = observe_move.compact_observations

    def fail_second(summary):
        calls.append(summary)
        if len(calls) == 2:
            raise InvalidScenarioSummaryError("corrupt")
        return real(summary)

    monkeypatch.setattr(observe_move, "compact_observations", fail_second)
    world = build()
    with pytest.raises(InvalidScenarioSummaryError):
        observed(world).execute(ObservedMoveRequest(request(), True, (CAPTURE_LINE,)))
    assert len(calls) == 2


W_PAWN = BasePieceRef(Color.WHITE, PieceType.PAWN, "e2")
B_KING = BasePieceRef(Color.BLACK, PieceType.KING, "e8")
B_ROOK = BasePieceRef(Color.BLACK, PieceType.ROOK, "a8")
W_KNIGHT = BasePieceRef(Color.WHITE, PieceType.KNIGHT, "b1")
P0, P1 = "pos_" + "0" * 24, "pos_" + "1" * 24


@pytest.mark.parametrize(
    ("ref", "kind", "anchor", "index", "ids", "selectors"),
    [
        (CaptureSource(2, P0, P1), "CAPTURE", "step", 2, (P0, P1), ()),
        (
            TransitionSource(1, P0, P1, W_PAWN, PieceTransitionKind.PROMOTION),
            "TRANSITION",
            "step",
            1,
            (P0, P1),
            ("white", "pawn", "e2", "promotion"),
        ),
        (
            MaterialSource(P0, P1, Color.BLACK, PieceType.ROOK),
            "MATERIAL",
            "endpoints",
            None,
            (P0, P1),
            ("black", "rook"),
        ),
        (HistorySource(0, P0, W_PAWN), "PIECE_HISTORY", "frame", 0, (P0,), ("white", "pawn", "e2")),
        (SquareSource(1, P1, "e4"), "SQUARE_ACCESS", "frame", 1, (P1,), ("e4",)),
        (PawnSource(0, P0, W_PAWN), "PAWN_STRUCTURE", "frame", 0, (P0,), ("white", "pawn", "e2")),
        (FileSource(1, P1, "d"), "FILE_STRUCTURE", "frame", 1, (P1,), ("d",)),
        (
            ActivitySource(0, P0, W_KNIGHT),
            "PIECE_ACTIVITY",
            "frame",
            0,
            (P0,),
            ("white", "knight", "b1"),
        ),
        (
            RaySource(1, P1, B_ROOK, (-1, 0)),
            "SLIDER_RAY",
            "frame",
            1,
            (P1,),
            ("black", "rook", "a8", "-1", "0"),
        ),
        (
            PinSource(0, P0, B_ROOK, W_KNIGHT, BasePieceRef(Color.WHITE, PieceType.KING, "e1")),
            "ABSOLUTE_PIN",
            "frame",
            0,
            (P0,),
            ("black", "rook", "a8", "white", "knight", "b1", "white", "king", "e1"),
        ),
    ],
)
def test_closed_source_projection(ref, kind, anchor, index, ids, selectors):
    view = source_view(ref)
    assert (view.kind, view.anchor_kind, view.index, view.position_ids, view.selectors) == (
        kind,
        anchor,
        index,
        ids,
        selectors,
    )


def test_unknown_source_and_snapshot_ids_fail_closed():
    with pytest.raises(ObservationProjectionError):
        source_view(SimpleNamespace(kind=SimpleNamespace(value="CAPTURE"), ply=1))
    with pytest.raises(ObservationProjectionError):
        observation_id(
            "x0", Bucket.SNAPSHOTS, SnapshotKey(0, SquareKey(FactKind.FOCUS_OCCUPANT, "e4"))
        )


@pytest.mark.parametrize(
    ("bucket", "key", "expected"),
    [
        (Bucket.EVENTS, CaptureKey(1), "obs.v1/p/events/CAPTURE/ply=1"),
        (
            Bucket.EVENTS,
            TransitionKey(3, EventKind.PROMOTION, W_PAWN),
            "obs.v1/p/events/PROMOTION/ply=3;base=white,pawn,e2",
        ),
        (
            Bucket.STEPS,
            StepKey(1, FileKey(FactKind.FILE_STATE, "d")),
            "obs.v1/p/steps/FILE_STATE/ply=1;file=d",
        ),
        (
            Bucket.STEPS,
            StepKey(2, SquareKey(FactKind.FOCUS_OCCUPANT, "e4")),
            "obs.v1/p/steps/FOCUS_OCCUPANT/ply=2;square=e4",
        ),
        (
            Bucket.ENDPOINTS,
            SubjectKey(FactKind.PAWN_FLAGS, W_PAWN),
            "obs.v1/p/endpoints/PAWN_FLAGS/base=white,pawn,e2",
        ),
        (
            Bucket.ENDPOINTS,
            RayKey(FactKind.RAY_STATE, B_ROOK, (1, -1)),
            "obs.v1/p/endpoints/RAY_STATE/base=black,rook,a8;dir=1,-1",
        ),
        (
            Bucket.STEPS,
            StepKey(
                1,
                PinKey(
                    FactKind.PIN_PRESENT,
                    B_ROOK,
                    W_KNIGHT,
                    BasePieceRef(Color.WHITE, PieceType.KING, "e1"),
                ),
            ),
            "obs.v1/p/steps/PIN_PRESENT/ply=1;pinner=black,rook,a8;pinned=white,knight,b1;king=white,king,e1",
        ),
        (
            Bucket.AGGREGATES,
            CountKey(CountView.FOCUS_LOSSES, Color.BLACK, PieceType.PAWN),
            "obs.v1/p/aggregates/FOCUS_LOSSES/color=black;piece=pawn",
        ),
    ],
)
def test_observation_id_grammar(bucket, key, expected):
    assert observation_id("p", bucket, key) == expected


def test_public_path_never_calls_the_full_detail_renderer(monkeypatch):
    from calliope.services.position.scenario_renderer import ScenarioSummaryRenderer

    def forbidden(self, summary):
        raise AssertionError("legacy full-detail renderer reached from the public path")

    monkeypatch.setattr(ScenarioSummaryRenderer, "render", forbidden)
    world = build()
    result = observed(world).execute(ObservedMoveRequest(request(), True, (RECAPTURE_LINE,)))
    assert result.played.sentences and result.exchange_lines[0].sentences
