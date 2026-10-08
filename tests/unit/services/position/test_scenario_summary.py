"""Integrity, bounded requests and closed-template coverage for internal scenarios."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import chess
import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis.bad_move import BasePieceRef
from calliope.domain.analysis.scenario import (
    VALUE_TYPES,
    Bucket,
    EventKind,
    FactKind,
    HistorySource,
    MaterialSource,
    PinSource,
    RenderedFactSentence,
    ScenarioKind,
    ScenarioRequest,
    Sentinel,
    SourceKind,
    SquareTarget,
    SubjectKey,
    TemplateId,
    TransitionSource,
)
from calliope.domain.chess import ChessMove, Color, PieceType
from calliope.errors import InvalidScenarioRequestError, InvalidScenarioSummaryError
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.position.activity import ActivityAnalyzer, ActivityLineAnalyzer
from calliope.services.position.line import LineAnalyzer
from calliope.services.position.positional import PositionAnalyzer, TransitionAnalyzer
from calliope.services.position.scenario import (
    ScenarioLineAnalyzer,
    _project,
    _resolve_source,
    validate_scenario_summary,
)
from calliope.services.position.scenario_renderer import ScenarioSummaryRenderer

CORPUS = Path(__file__).parents[3] / "golden" / "scenario_explanation_cases.json"
NON_LEGACY_TEMPLATES = {
    TemplateId.PLAYED_STATUS,
    TemplateId.PLAYED_CHANGE,
    TemplateId.EXCHANGE_OBS_CHANGE,
}
CASES = json.loads(CORPUS.read_text(encoding="utf-8"))["cases"]


def build():
    rules = PythonChessAdapter()
    facts = PositionFactExtractor(rules)
    positions = PositionAnalyzer(facts)
    transitions = TransitionAnalyzer(rules, positions, BoardDeltaAnalyzer(rules, facts))
    return rules, ScenarioLineAnalyzer(
        ActivityLineAnalyzer(LineAnalyzer(transitions), ActivityAnalyzer(positions, rules))
    )


def summarize(case):
    rules, service = build()
    request = ScenarioRequest(
        ScenarioKind.EXCHANGE,
        SquareTarget(case["focus"]),
        rules.position_from_fen(case["fen"]),
        tuple(ChessMove(m) for m in case["moves"]),
    )
    return service.analyze(request)


@pytest.fixture
def capture():
    return summarize(CASES[1])


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", "EXCHANGE"),
        ("kind", True),
        ("target", "d5"),
        ("initial", None),
        ("supplied_line", []),
        ("supplied_line", ("e4d5",)),
        ("max_plies", True),
        ("max_plies", 0),
        ("max_plies", 257),
        ("max_plies", 1.0),
        ("max_plies", "64"),
    ],
)
def test_request_rejects_before_observation(field, value):
    rules, service = build()
    args = {
        "kind": ScenarioKind.EXCHANGE,
        "target": SquareTarget("d5"),
        "initial": rules.position_from_fen(CASES[1]["fen"]),
        "supplied_line": (ChessMove("e4d5"),),
    }
    service.activity_lines = Mock(side_effect=AssertionError("observation must not run"))
    args[field] = value
    with pytest.raises(InvalidScenarioRequestError):
        service.analyze(ScenarioRequest(**args))
    service.activity_lines.analyze.assert_not_called()


@pytest.mark.parametrize("square", ("i1", "A1", "a0", "", "a11", None, True))
def test_invalid_target(square):
    with pytest.raises(InvalidScenarioRequestError):
        SquareTarget(square)


def test_oversized_request_and_nonrequest_do_not_observe():
    rules, service = build()
    service.activity_lines = Mock()
    with pytest.raises(InvalidScenarioRequestError):
        ScenarioRequest(
            ScenarioKind.EXCHANGE,
            SquareTarget("d5"),
            rules.position_from_fen(CASES[1]["fen"]),
            (ChessMove("e4d5"),) * 2,
            1,
        )
    with pytest.raises(InvalidScenarioRequestError):
        service.analyze("EXCHANGE")
    service.activity_lines.analyze.assert_not_called()


def corrupt(summary, mutation):
    """Validly typed alterations expose cross-record completeness and equality bugs."""
    if mutation == "omit-event":
        return replace(summary, events=())
    if mutation == "duplicate-event":
        return replace(summary, events=summary.events * 2)
    if mutation == "omit-selected-change":
        return replace(summary, selected_changes=summary.selected_changes[1:])
    if mutation == "omit-endpoint":
        return replace(summary, endpoint_changes=summary.endpoint_changes[1:])
    if mutation == "omit-history":
        return replace(summary, feature_histories=summary.feature_histories[1:])
    if mutation == "omit-participant":
        return replace(
            summary, detail=replace(summary.detail, participants=summary.detail.participants[1:])
        )
    if mutation == "partition":
        return replace(
            summary,
            detail=replace(
                summary.detail,
                focus_capture_events=(),
                other_capture_events=summary.detail.focus_capture_events,
            ),
        )
    if mutation == "loss":
        losses = summary.detail.focus_capture_losses
        return replace(
            summary,
            detail=replace(summary.detail, focus_capture_losses=(replace(losses[0], count=2),)),
        )
    if mutation == "material":
        material = summary.detail.whole_line_material_changes
        return replace(
            summary,
            detail=replace(
                summary.detail, whole_line_material_changes=(replace(material[0], count=1),)
            ),
        )
    if mutation == "temporary":
        return replace(summary, detail=replace(summary.detail, temporary_track_count=1))
    if mutation == "version":
        return replace(summary, definition_version="scenario_summary_v2")
    if mutation == "detail-version":
        return replace(
            summary, detail=replace(summary.detail, definition_version="exchange_rules_v2")
        )
    if mutation == "incomplete-accounting":
        return replace(summary, selection_accounting=summary.selection_accounting[1:])
    if mutation == "same-count-wrong-key":
        row = next(
            r
            for r in summary.selection_accounting
            if r.bucket is Bucket.STEPS and r.family is FactKind.PIECE_STATE
        )
        king = next(
            h.base
            for h in summary.observed_line.structural.piece_histories
            if h.base.base_square == "e1"
        )
        alternate = replace(
            row.candidate_keys[0], property=replace(row.candidate_keys[0].property, subject=king)
        )
        changed = replace(
            row,
            candidate_keys=(alternate, *row.candidate_keys[1:]),
            included_keys=(alternate, *row.included_keys[1:]),
        )
        return replace(
            summary,
            selection_accounting=tuple(
                changed if r == row else r for r in summary.selection_accounting
            ),
        )
    event = summary.events[0]
    if mutation == "missing-mixed-provenance":
        event = replace(event, source_refs=event.source_refs[:1])
    elif mutation == "wrong-ref-anchor":
        event = replace(
            event,
            source_refs=(
                replace(event.source_refs[0], before_position_id="wrong"),
                *event.source_refs[1:],
            ),
        )
    elif mutation == "wrong-payload":
        event = replace(event, payload=replace(event.payload, landing_square="c5"))
    elif mutation == "reasons":
        event = replace(event, reasons=event.reasons[:1])
    return replace(summary, events=(event, *summary.events[1:]))


@pytest.mark.parametrize(
    "mutation",
    (
        "omit-event",
        "duplicate-event",
        "omit-selected-change",
        "omit-endpoint",
        "omit-history",
        "omit-participant",
        "partition",
        "loss",
        "material",
        "temporary",
        "version",
        "detail-version",
        "incomplete-accounting",
        "same-count-wrong-key",
        "missing-mixed-provenance",
        "wrong-ref-anchor",
        "wrong-payload",
        "reasons",
    ),
)
def test_renderer_rejects_cross_record_mutations(capture, mutation):
    altered = corrupt(capture, mutation)
    with pytest.raises(InvalidScenarioSummaryError):
        ScenarioSummaryRenderer().render(altered)


@pytest.mark.parametrize(
    "mutation",
    (
        "history",
        "identity-swap",
        "activity-uci",
        "activity-version",
        "features",
        "step-binding",
        "request-uci",
    ),
)
def test_retained_observation_integrity(capture, mutation):
    altered = deepcopy(capture)
    observed = altered.observed_line
    if mutation == "history":
        history = observed.structural.piece_histories[0]
        object.__setattr__(history, "states", (None, *history.states[1:]))
    elif mutation == "identity-swap":
        delta = observed.structural.transitions[0].board_delta
        pairs = delta.piece_correspondence
        object.__setattr__(
            delta,
            "piece_correspondence",
            (
                replace(pairs[0], after=pairs[1].after),
                replace(pairs[1], after=pairs[0].after),
                *pairs[2:],
            ),
        )
    elif mutation == "activity-uci":
        frame = observed.activity_frames[0]
        piece = next(p for p in frame.activity.pieces if p.legal_moves_now)
        object.__setattr__(piece, "legal_moves_now", (ChessMove("a1a2"),))
    elif mutation == "activity-version":
        object.__setattr__(observed.activity_frames[0].activity, "definition_version", "other")
    elif mutation == "features":
        features = observed.activity_frames[0].structural.features
        object.__setattr__(
            features,
            "files",
            tuple(replace(f, white_pawns=9) if f.file == "e" else f for f in features.files),
        )
    elif mutation == "step-binding":
        object.__setattr__(observed.structural.transitions[0], "before", observed.structural.final)
    else:
        object.__setattr__(altered.request, "supplied_line", (ChessMove("e4e5"),))
    with pytest.raises(InvalidScenarioSummaryError):
        ScenarioSummaryRenderer().render(altered)


def test_validate_render_and_resolve_make_no_adapter_calls():
    rules, service = build()
    request = ScenarioRequest(
        ScenarioKind.EXCHANGE,
        SquareTarget("d4"),
        rules.position_from_fen(CASES[11]["fen"]),
        tuple(ChessMove(m) for m in CASES[11]["moves"]),
    )
    replay = Mock(wraps=service.activity_lines.analyze)
    service.activity_lines = Mock(analyze=replay)
    summary = service.analyze(request)
    assert replay.call_count == 1
    for name in ("legal_move_from_uci", "apply_move", "observe_position", "observe_tactics"):
        setattr(rules, name, Mock(side_effect=AssertionError("no more adapter work")))
    validate_scenario_summary(summary)
    assert _project(request, summary.observed_line) == summary
    report = ScenarioSummaryRenderer().render(summary)
    for sentence in (*report.digest, *report.detail):
        for ref in sentence.source_refs:
            _resolve_source(summary, ref)
    assert replay.call_count == 1


def test_unsupported_and_absent_selectors_are_distinct(capture):
    ref = capture.detail.participants[0].history_refs[0]
    unknown = BasePieceRef(Color.WHITE, PieceType.ROOK, "a1")
    for invalid in (
        replace(ref, frame_index=2),
        replace(ref, position_id="wrong"),
        replace(ref, subject=unknown),
    ):
        with pytest.raises(InvalidScenarioSummaryError):
            _resolve_source(capture, invalid)
    victim = capture.detail.participants[1]
    assert _resolve_source(capture, victim.history_refs[-1]) is Sentinel.CAPTURED
    king = next(
        h.base
        for h in capture.observed_line.structural.piece_histories
        if h.base.base_square == "e1"
    )
    with pytest.raises(InvalidScenarioSummaryError):
        _resolve_source(capture, PinSource(0, ref.position_id, unknown, ref.subject, king))


@pytest.mark.parametrize(
    "construct",
    (
        lambda r: replace(r, frame_index=True),
        lambda r: HistorySource(-1, r.position_id, r.subject),
        lambda r: SubjectKey(FactKind.FILE_STATE, r.subject),
        lambda r: MaterialSource(r.position_id, r.position_id, Color.WHITE, PieceType.KING),
        lambda r: RenderedFactSentence("MOVE", "arbitrary", (r,)),
        lambda r: RenderedFactSentence(TemplateId.MOVE, "text", ()),
    ),
)
def test_child_records_reject_invalid_shape(capture, construct):
    with pytest.raises(InvalidScenarioSummaryError):
        construct(capture.detail.participants[0].history_refs[0])


def test_catalog_covers_every_template_and_sentinel_branch():
    templates, values, sources, branches, file_states, pin_values = (
        set(),
        set(),
        set(),
        set(),
        set(),
        set(),
    )
    for case in CASES:
        summary = summarize(case)
        report = ScenarioSummaryRenderer().render(summary)
        for sentence in (*report.digest, *report.detail):
            templates.add(sentence.template_id)
            sources.update(r.kind for r in sentence.source_refs)
        facts = [
            f for s in summary.focus_timeline for f in (s.occupant, s.attackers, s.legal_captures)
        ]
        facts.extend(
            f
            for c in (*summary.selected_changes, *summary.endpoint_changes)
            for f in (c.before, c.after)
        )
        facts.extend(f for h in summary.feature_histories for r in h.runs for f in r.facts)
        for fact in facts:
            branches.add(
                (fact.key.family, fact.value if type(fact.value) is Sentinel else type(fact.value))
            )
            if fact.key.family is FactKind.FILE_STATE:
                value = fact.value
                file_states.add(
                    "open"
                    if value.open
                    else "white"
                    if value.semi_open_for(Color.WHITE)
                    else "black"
                    if value.semi_open_for(Color.BLACK)
                    else "neither"
                )
            if fact.key.family is FactKind.PIN_PRESENT:
                pin_values.add(fact.value)
        for h in summary.feature_histories:
            values.update(f.value for r in h.runs for f in r.facts if type(f.value) is Sentinel)
        for change in summary.selected_changes:
            values.update(
                f.value for f in (change.before, change.after) if type(f.value) is Sentinel
            )
    # The legacy EXCHANGE report exercises its whole catalog; compact/PLAYED ids are separate.
    assert templates == set(TemplateId) - NON_LEGACY_TEMPLATES
    assert sources == set(SourceKind)
    assert values == set(Sentinel)
    assert branches == {
        (family, branch) for family, allowed in VALUE_TYPES.items() for branch in allowed
    }
    assert file_states == {"open", "white", "black", "neither"}
    assert pin_values == {False, True}


def test_san_is_not_rendered_or_used_as_move_identity():
    rules, service = build()
    initial = rules.position_from_fen(CASES[1]["fen"])
    regular = ScenarioRequest(
        ScenarioKind.EXCHANGE, SquareTarget("d5"), initial, (ChessMove("e4d5"),)
    )
    tainted = replace(regular, supplied_line=(ChessMove("e4d5", san="caused an advantage"),))
    renderer = ScenarioSummaryRenderer()
    assert renderer.render(service.analyze(regular)) == renderer.render(service.analyze(tainted))


@pytest.mark.parametrize("plies", (0, 1, 64, 256))
def test_long_line_keeps_every_frame_and_complete_history(plies):
    rules, service = build()
    cycle = ("g1f3", "g8f6", "f3g1", "f6g8")
    moves = tuple(ChessMove(cycle[i % 4]) for i in range(plies))
    request = ScenarioRequest(
        ScenarioKind.EXCHANGE,
        SquareTarget("e4"),
        rules.position_from_fen(CASES[0]["fen"]),
        moves,
        max_plies=256,
    )
    summary = service.analyze(request)
    assert len(summary.focus_timeline) == plies + 1
    assert not summary.detail.participants
    assert not summary.detail.focus_capture_losses
    assert not summary.detail.whole_line_material_changes
    assert len(summary.observed_line.structural.piece_histories[0].states) == plies + 1
    validate_scenario_summary(summary)
    ScenarioSummaryRenderer().render(summary)


@pytest.mark.parametrize("promoted", ("n", "b", "r", "q"))
@pytest.mark.parametrize("mirrored", (False, True))
def test_digest_keeps_capture_promotion_before_recapture(promoted, mirrored):
    rules, service = build()
    board = chess.Board("1nr4k/P7/8/8/8/8/8/4K3 w - - 0 1")
    moves = (f"a7b8{promoted}", "c8b8")
    square = lambda s: (
        chess.square_name(chess.square_mirror(chess.parse_square(s))) if mirrored else s
    )
    if mirrored:
        board = board.mirror()
        moves = tuple(square(m[:2]) + square(m[2:4]) + m[4:] for m in moves)
    request = ScenarioRequest(
        ScenarioKind.EXCHANGE,
        SquareTarget(square("b8")),
        rules.position_from_fen(board.fen()),
        tuple(ChessMove(m) for m in moves),
    )
    summary = service.analyze(request)
    report = ScenarioSummaryRenderer().render(summary)
    events = [
        s
        for s in report.digest
        if s.template_id in (TemplateId.CAPTURE_NORMAL, TemplateId.PROMOTION)
    ]
    assert [s.template_id for s in events] == [
        TemplateId.CAPTURE_NORMAL,
        TemplateId.PROMOTION,
        TemplateId.CAPTURE_NORMAL,
    ]
    transition = next(e for e in summary.events if e.key.family is EventKind.PROMOTION)
    ref = next(r for r in events[1].source_refs if type(r) is TransitionSource)
    assert ref.ply == 1 and ref.subject.base_square == square("a7")
    assert _resolve_source(summary, ref) == transition.payload
    promoted_type = chess.piece_name(chess.PIECE_SYMBOLS.index(promoted))
    assert f"initially on {square('a7')}" in events[1].text
    assert f"promotes to {promoted_type}" in events[1].text
    assert f"{promoted_type} on {square('b8')}" in events[2].text
    assert any(
        c.key.piece_type.value == promoted_type
        and c.key.color is (Color.BLACK if mirrored else Color.WHITE)
        for c in summary.detail.focus_capture_losses
    )
    for sentence in events:
        assert f"on {square('b8')} on {square('b8')}" not in sentence.text


def test_digest_keeps_participant_quiet_promotion_before_later_focus_capture():
    summary = summarize(
        {
            "fen": "2r4k/P7/8/8/8/8/8/4K3 w - - 0 1",
            "focus": "c7",
            "moves": ["a7a8n", "h8h7", "a8c7", "c8c7"],
        }
    )
    report = ScenarioSummaryRenderer().render(summary)
    events = [
        s
        for s in report.digest
        if s.template_id in (TemplateId.CAPTURE_NORMAL, TemplateId.PROMOTION)
    ]
    assert [s.template_id for s in events] == [TemplateId.PROMOTION, TemplateId.CAPTURE_NORMAL]
    assert "at ply 1" in events[0].text and "initially on a7" in events[0].text
    assert "at ply 4" in events[1].text and "white knight" in events[1].text


def test_nonparticipant_promotion_does_not_expand_digest_selection():
    summary = summarize(
        {"fen": "2r4k/P7/8/8/8/8/8/4K3 w - - 0 1", "focus": "d4", "moves": ["a7a8n"]}
    )
    assert not summary.detail.participants
    assert all(
        s.template_id is not TemplateId.PROMOTION
        for s in ScenarioSummaryRenderer().render(summary).digest
    )


@pytest.mark.parametrize("mirrored", (False, True))
def test_king_only_participant_castling_has_step_context(mirrored):
    rules, service = build()
    board = chess.Board("4k3/8/8/8/8/7p/8/4K2R w K - 0 1")
    moves = ("e1g1", "h3h2", "g1h2")
    square = lambda s: (
        chess.square_name(chess.square_mirror(chess.parse_square(s))) if mirrored else s
    )
    if mirrored:
        board = board.mirror()
        moves = tuple(square(m[:2]) + square(m[2:4]) for m in moves)
    summary = service.analyze(
        ScenarioRequest(
            ScenarioKind.EXCHANGE,
            SquareTarget(square("h2")),
            rules.position_from_fen(board.fen()),
            tuple(ChessMove(m) for m in moves),
        )
    )
    report = ScenarioSummaryRenderer().render(summary)
    assert square("e1") in [p.base.base_square for p in summary.detail.participants]
    assert square("h1") not in [p.base.base_square for p in summary.detail.participants]
    assert all(e.key.family is not EventKind.CASTLING_ROOK for e in summary.events)
    assert any(
        s.template_id is TemplateId.MOVE
        and f"move {moves[0]} is castling" in s.text
        and f"from {square('e1')} to {square('g1')}" in s.text
        for s in report.detail
    )
