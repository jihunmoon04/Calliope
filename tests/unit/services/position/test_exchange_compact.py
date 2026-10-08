"""I2 compact EXCHANGE selector: dependency rules, integrity and zero adapter work."""

from dataclasses import replace
from unittest.mock import Mock

import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis.scenario import (
    Bucket,
    CaptureKey,
    CountKey,
    CountView,
    EventKind,
    ExchangeObservationInput,
    LineOrigin,
    PresentationExclusion,
    RenderedFactSentence,
    ScenarioKind,
    ScenarioRequest,
    SquareTarget,
    TemplateId,
    TransitionKey,
)
from calliope.domain.chess import ChessMove, Color, PieceType
from calliope.errors import InvalidScenarioRequestError, InvalidScenarioSummaryError
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.position.activity import ActivityAnalyzer, ActivityLineAnalyzer
from calliope.services.position.line import LineAnalyzer
from calliope.services.position.positional import PositionAnalyzer, TransitionAnalyzer
from calliope.services.position.scenario import ScenarioLineAnalyzer
from calliope.services.position.scenario_observation import (
    ExchangeObservationSelector,
    PlayedObservationSelector,
    compact_observations,
    validate_compact_observations,
    validate_observation_selection,
)
from calliope.services.position.scenario_renderer import ScenarioSummaryRenderer

rules = PythonChessAdapter()


def summarize(fen, moves, focus, max_plies=8):
    facts = PositionFactExtractor(rules)
    positions = PositionAnalyzer(facts)
    transitions = TransitionAnalyzer(rules, positions, BoardDeltaAnalyzer(rules, facts))
    service = ScenarioLineAnalyzer(
        ActivityLineAnalyzer(LineAnalyzer(transitions), ActivityAnalyzer(positions, rules))
    )
    request = ScenarioRequest(
        ScenarioKind.EXCHANGE,
        SquareTarget(focus),
        rules.position_from_fen(fen),
        tuple(ChessMove(m) for m in moves),
        max_plies,
    )
    return service.analyze(request)


def ledger(summary):
    return {(c.bucket, c.key): c for c in ExchangeObservationSelector().select(summary).candidates}


def keys(summary):
    return [(o.bucket, o.key) for o in compact_observations(summary)]


# a7a8q, Rb8xa8 (the promoted queen, off focus), exd4 on the focus square.
PROMOTED_OFF_FOCUS = ("1r2k3/P7/8/8/3p4/4P3/8/4K3 w - - 0 1", ("a7a8q", "b8a8", "e3d4"), "d4")


def test_capture_of_promoted_nonparticipant_needs_an_excluded_witness():
    summary = summarize(*PROMOTED_OFF_FOCUS)
    rows = ledger(summary)
    a7 = next(
        h.base
        for h in summary.observed_line.structural.piece_histories
        if h.base.base_square == "a7"
    )
    # The a7 promotion is a core-excluded nonparticipant event: it never enters the ledger.
    assert (Bucket.EVENTS, TransitionKey(1, EventKind.PROMOTION, a7)) not in rows
    assert rows[Bucket.EVENTS, CaptureKey(2)].exclusion is PresentationExclusion.CONTEXT_ONLY
    white_pawns = CountKey(CountView.MATERIAL_COUNTS, Color.WHITE, PieceType.PAWN)
    black_pawns = CountKey(CountView.MATERIAL_COUNTS, Color.BLACK, PieceType.PAWN)
    assert rows[Bucket.AGGREGATES, white_pawns].exclusion is PresentationExclusion.CONTEXT_ONLY
    assert rows[Bucket.AGGREGATES, black_pawns].exclusion is PresentationExclusion.CAP_EXCEEDED
    losses = CountKey(CountView.FOCUS_LOSSES, Color.BLACK, PieceType.PAWN)
    assert keys(summary) == [(Bucket.EVENTS, CaptureKey(3)), (Bucket.AGGREGATES, losses)]


def test_count_never_pulls_its_witness():
    # Two focus captures: the loss count needs both, so it cannot follow a single capture.
    summary = summarize(
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        ("e2e4", "d7d5", "e4d5", "d8d5"),
        "d5",
    )
    selected = keys(summary)
    assert selected == [(Bucket.EVENTS, CaptureKey(3)), (Bucket.EVENTS, CaptureKey(4))]
    rows = ledger(summary)
    for color in Color:
        loss = CountKey(CountView.FOCUS_LOSSES, color, PieceType.PAWN)
        assert rows[Bucket.AGGREGATES, loss].exclusion is PresentationExclusion.CAP_EXCEEDED


def test_multi_ply_endpoints_are_not_duplicates_and_snapshots_are_context():
    summary = summarize("4k3/p7/8/8/8/N7/8/R3K3 w - - 0 1", ("a3b5", "e8d8"), "a7")
    rows = ledger(summary)
    assert all(c.exclusion is not PresentationExclusion.SEMANTIC_DUPLICATE for c in rows.values())
    snapshots = [c for c in rows.values() if c.bucket is Bucket.SNAPSHOTS]
    assert len(snapshots) == 3 * 3
    assert all(c.exclusion is PresentationExclusion.CONTEXT_ONLY for c in snapshots)
    templates = {o.sentence.template_id for o in compact_observations(summary)}
    assert templates == {TemplateId.EXCHANGE_OBS_CHANGE}
    # Endpoint (tier 5, frames 0->2) precedes the distinct ply-1 step change (tier 6).
    selected = compact_observations(summary)
    assert [o.bucket for o in selected] == [Bucket.ENDPOINTS, Bucket.STEPS]
    assert "from frame 0 to 2" in selected[0].sentence.text
    assert "from frame 0 to 1" in selected[1].sentence.text


def test_selection_and_compact_mutations_fail_closed():
    summary = summarize(*PROMOTED_OFF_FOCUS)
    selection = ExchangeObservationSelector().select(summary)
    validate_observation_selection(summary, selection)
    index = next(i for i, c in enumerate(selection.candidates) if c.exclusion is None)
    forged = replace(selection.candidates[index], rank=(0,))
    with pytest.raises(InvalidScenarioSummaryError):
        validate_observation_selection(
            summary,
            replace(
                selection,
                candidates=selection.candidates[:index]
                + (forged,)
                + selection.candidates[index + 1 :],
            ),
        )
    with pytest.raises(InvalidScenarioSummaryError):
        validate_observation_selection(summary, PlayedObservationSelector)
    observations = compact_observations(summary)
    validate_compact_observations(summary, observations)
    sentence = observations[0].sentence
    wrong = replace(
        observations[0],
        sentence=RenderedFactSentence(
            sentence.template_id, sentence.text + " ", sentence.source_refs
        ),
    )
    with pytest.raises(InvalidScenarioSummaryError):
        validate_compact_observations(summary, (wrong, *observations[1:]))
    with pytest.raises(InvalidScenarioSummaryError):
        PlayedObservationSelector().select(summary)


def test_exchange_observation_input_is_closed():
    position = rules.position_from_fen("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
    request = ScenarioRequest(ScenarioKind.EXCHANGE, SquareTarget("e4"), position, ())
    assert ExchangeObservationInput(request, LineOrigin.FIXTURE).origin is LineOrigin.FIXTURE
    for origin in ("USER", None):
        with pytest.raises(InvalidScenarioRequestError):
            ExchangeObservationInput(request, origin)
    with pytest.raises(InvalidScenarioRequestError):
        ExchangeObservationInput("not a request", LineOrigin.USER)


def test_compact_selection_makes_no_adapter_calls(monkeypatch):
    summary = summarize(*PROMOTED_OFF_FOCUS)
    legacy = ScenarioSummaryRenderer().render(summary)
    for name in ("observe_position", "observe_tactics", "legal_move_from_uci", "apply_move"):
        monkeypatch.setattr(PythonChessAdapter, name, Mock(side_effect=AssertionError(name)))
    compact_observations(summary)
    ExchangeObservationSelector().select(summary)
    assert ScenarioSummaryRenderer().render(summary) == legacy
