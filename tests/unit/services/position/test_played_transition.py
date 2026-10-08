"""I1 PLAYED_TRANSITION request preflight, legality and integrity mutations (D14-D16)."""

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis.scenario import (
    ActivitySource,
    Bucket,
    ExchangeDetail,
    ExchangeStatus,
    PlayedMoveTarget,
    PresentationExclusion,
    RenderedFactSentence,
    ScenarioKind,
    ScenarioRequest,
    SquareTarget,
    StepKey,
    SubjectKey,
    is_canonical_uci,
)
from calliope.domain.chess import ChessMove
from calliope.errors import (
    IllegalMoveError,
    InvalidScenarioRequestError,
    InvalidScenarioSummaryError,
)
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.position.activity import ActivityAnalyzer, ActivityLineAnalyzer
from calliope.services.position.line import LineAnalyzer
from calliope.services.position.positional import PositionAnalyzer, TransitionAnalyzer
from calliope.services.position.scenario import ScenarioLineAnalyzer, validate_scenario_summary
from calliope.services.position.scenario_observation import (
    PlayedObservationSelector,
    compact_observations,
    validate_compact_observations,
    validate_observation_selection,
)
from calliope.services.position.scenario_renderer import (
    ScenarioSummaryRenderer,
    validate_rendered_report,
)

CORPUS = json.loads(
    (
        Path(__file__).resolve().parents[4] / "docs" / "corpus" / "played-transition-i1d-v1.json"
    ).read_text(encoding="utf-8")
)
CASES = {c["id"]: c for c in CORPUS["cases"]}
START = CASES["D01"]["fen"]
rules = PythonChessAdapter()


def service():
    facts = PositionFactExtractor(rules)
    positions = PositionAnalyzer(facts)
    transitions = TransitionAnalyzer(rules, positions, BoardDeltaAnalyzer(rules, facts))
    return ScenarioLineAnalyzer(
        ActivityLineAnalyzer(LineAnalyzer(transitions), ActivityAnalyzer(positions, rules))
    )


def played(fen, uci, *, target=None, line=None, max_plies=1):
    target = ChessMove(uci) if target is None else target
    line = (ChessMove(uci),) if line is None else line
    return ScenarioRequest(
        ScenarioKind.PLAYED_TRANSITION,
        PlayedMoveTarget(target),
        rules.position_from_fen(fen),
        line,
        max_plies,
    )


@pytest.fixture(scope="module")
def d01():
    return service().analyze(played(START, "e2e4"))


@pytest.fixture(scope="module")
def d03():
    case = CASES["D03"]
    return service().analyze(played(case["fen"], case["uci"]))


# ---- D14: preflight before any activity/adapter work ----------------------------------------


@pytest.mark.parametrize("variant", CASES["D14"]["variants"], ids=lambda v: v["name"])
def test_d14_corpus_variants_reject_before_observation(variant):
    case = CASES["D14"]
    target = variant.get("target_uci", case["target_uci"])
    uci = variant.get("uci", case["uci"])
    line = tuple(ChessMove(m) for m in variant.get("line", [uci]))
    spy = Mock()
    with pytest.raises(InvalidScenarioRequestError):
        request = ScenarioRequest(
            ScenarioKind.PLAYED_TRANSITION,
            PlayedMoveTarget(ChessMove(target)),
            rules.position_from_fen(case["fen"]),
            line,
            variant.get("max_plies", case["max_plies"]),
        )
        ScenarioLineAnalyzer(spy).analyze(request)
    assert spy.method_calls == [] == spy.analyze.call_args_list
    assert case["expected_activity_calls"] == 0


@pytest.mark.parametrize(
    "build",
    [
        lambda p: ScenarioRequest(
            "PLAYED_TRANSITION", PlayedMoveTarget(ChessMove("e2e4")), p, (ChessMove("e2e4"),), 1
        ),
        lambda p: ScenarioRequest(
            ScenarioKind.PLAYED_TRANSITION, SquareTarget("e4"), p, (ChessMove("e2e4"),), 1
        ),
        lambda p: ScenarioRequest(
            ScenarioKind.EXCHANGE, PlayedMoveTarget(ChessMove("e2e4")), p, (), 1
        ),
        lambda p: ScenarioRequest(
            ScenarioKind.PLAYED_TRANSITION,
            PlayedMoveTarget(ChessMove("e2e4")),
            p,
            [ChessMove("e2e4")],
            1,
        ),
        lambda p: ScenarioRequest(
            ScenarioKind.PLAYED_TRANSITION, PlayedMoveTarget(ChessMove("e2e4")), p, ("e2e4",), 1
        ),
        lambda p: ScenarioRequest(
            ScenarioKind.PLAYED_TRANSITION,
            PlayedMoveTarget(ChessMove("e2e4")),
            p,
            (ChessMove("e2e4"),),
        ),
        lambda p: PlayedMoveTarget("e2e4"),
        lambda p: PlayedMoveTarget(ChessMove("e2e2")),
        lambda p: PlayedMoveTarget(ChessMove("e2e4q")),
        lambda p: PlayedMoveTarget(ChessMove("a7a8k")),
    ],
)
def test_wrong_kind_target_line_and_default_budget_reject(build):
    with pytest.raises(InvalidScenarioRequestError):
        build(rules.position_from_fen(START))


def test_canonical_uci_shape_is_lexical_only():
    assert is_canonical_uci("a7a8q") and is_canonical_uci("h2h1n") and is_canonical_uci("e2e4")
    for bad in ("e2e4 ", "E2E4", "e2e2", "e2e4q", "a7a8k", "e9e4", "", None, "a7a8Q"):
        assert not is_canonical_uci(bad)
    # Pawn kind and missing suffix are the adapter's job, never a second rules implementation.
    assert is_canonical_uci("b7b8q")


def test_d14_san_display_differs_but_uci_identity_accepted():
    request = played(
        START, "e2e4", target=ChessMove("e2e4", "display"), line=(ChessMove("e2e4", "e4"),)
    )
    assert service().analyze(request).request.supplied_line[0].san == "e4"


def test_exchange_preflight_is_unchanged():
    position = rules.position_from_fen(START)
    for max_plies in (0, 257, True):
        with pytest.raises(InvalidScenarioRequestError):
            ScenarioRequest(ScenarioKind.EXCHANGE, SquareTarget("e4"), position, (), max_plies)
    ScenarioRequest(ScenarioKind.EXCHANGE, SquareTarget("e4"), position, ())


# ---- D15: illegal but well-shaped move -----------------------------------------------------


def test_d15_illegal_move_uses_existing_legality_error():
    case = CASES["D15"]
    with pytest.raises(IllegalMoveError):
        service().analyze(played(case["fen"], case["uci"]))


# ---- D16: integrity mutations ----------------------------------------------------------------


def _row_index(summary, bucket, family):
    return next(
        i
        for i, r in enumerate(summary.selection_accounting)
        if (r.bucket, r.family.value) == (bucket, family)
    )


def _with_row(summary, index, row):
    rows = list(summary.selection_accounting)
    rows[index] = row
    return replace(summary, selection_accounting=tuple(rows))


def wrong_version_for_kind(s):
    return replace(s, definition_version="scenario_summary_v1")


def exchange_detail_in_played(s):
    return replace(s, detail=ExchangeDetail(ExchangeStatus.NO_FOCUS_CAPTURE, (), (), (), (), (), 0))


def wrong_base_position_id(s):
    participant = s.detail.participants[0]
    refs = (
        replace(participant.history_refs[0], position_id=participant.history_refs[1].position_id),
    )
    refs += participant.history_refs[1:]
    detail = replace(s.detail, participants=(replace(participant, history_refs=refs),))
    return replace(s, detail=detail)


def altered_source_ref(s):
    index, change = next(
        (i, c)
        for i, c in enumerate(s.selected_changes)
        if any(type(r) is ActivitySource for r in c.before.source_refs)
    )
    refs = tuple(
        replace(r, position_id=s.observed_line.activity_frames[1].activity.position_id)
        if type(r) is ActivitySource
        else r
        for r in change.before.source_refs
    )
    forged = replace(change, before=replace(change.before, source_refs=refs))
    changes = s.selected_changes[:index] + (forged,) + s.selected_changes[index + 1 :]
    return replace(s, selected_changes=changes)


def same_count_different_candidate_key(s):
    index = _row_index(s, Bucket.STEPS, "ATTACK_FOOTPRINT")
    row = s.selection_accounting[index]
    other = SubjectKey(row.candidate_keys[0].property.family, s.detail.participants[0].base)
    keys = list(row.candidate_keys)
    swap = next(i for i, k in enumerate(keys) if k.property != other)
    replacement = StepKey(1, SubjectKey(other.family, replace(other.subject, base_square="a2")))
    keys[swap] = replacement
    keys = tuple(
        sorted(
            set(keys),
            key=lambda k: (k.property.subject.base_square[1], k.property.subject.base_square[0]),
        )
    )
    return _with_row(s, index, replace(row, candidate_keys=keys, included_keys=keys))


def missing_accounting_row(s):
    return replace(s, selection_accounting=s.selection_accounting[:-1])


def wrong_claim_role(s):
    other = next(
        b
        for b in (
            r.property.subject
            for r in s.selection_accounting[
                _row_index(s, Bucket.STEPS, "ATTACK_FOOTPRINT")
            ].included_keys
        )
        if b != s.detail.mover
    )
    return replace(s, detail=replace(s.detail, mover=other))


def swapped_step_frame(s):
    change = s.selected_changes[0]
    return replace(
        s,
        selected_changes=(replace(change, before=change.after, after=change.before),)
        + s.selected_changes[1:],
    )


SUMMARY_MUTATIONS = {
    "wrong_version_for_kind": wrong_version_for_kind,
    "ExchangeDetail_in_PLAYED": exchange_detail_in_played,
    "wrong_base_position_id": wrong_base_position_id,
    "altered_attacker_source_ref": altered_source_ref,
    "same_count_different_candidate_key": same_count_different_candidate_key,
    "missing_accounting_row": missing_accounting_row,
    "wrong_claim_role": wrong_claim_role,
    "swapped_step_frame": swapped_step_frame,
}


def test_d16_mutation_catalog_is_complete():
    assert set(CASES["D16"]["mutations"]) == set(SUMMARY_MUTATIONS) | {
        "wrong_capture_victim",
        "wrong_presentation_exclusion_reason",
        "wrong_digest_sentence",
        "forged_status_source",
    }


@pytest.mark.parametrize("name", sorted(SUMMARY_MUTATIONS))
def test_d16_summary_mutations_are_refused(d01, name):
    validate_scenario_summary(d01)
    with pytest.raises(InvalidScenarioSummaryError):
        mutated = SUMMARY_MUTATIONS[name](d01)
        assert mutated != d01, "mutation must change the summary"
        validate_scenario_summary(mutated)
    with pytest.raises(InvalidScenarioSummaryError):
        ScenarioSummaryRenderer().render(SUMMARY_MUTATIONS[name](d01))


def test_d16_wrong_capture_victim(d03):
    event = d03.events[0]
    victim = replace(event.payload.captured, square="d6")
    with pytest.raises(InvalidScenarioSummaryError):
        mutated = replace(
            d03,
            events=(replace(event, payload=replace(event.payload, captured=victim)),)
            + d03.events[1:],
        )
        validate_scenario_summary(mutated)
    with pytest.raises(InvalidScenarioSummaryError):
        validate_scenario_summary(replace(d03, detail=replace(d03.detail, capture_event=None)))


def test_d16_wrong_presentation_exclusion_reason(d01):
    selection = PlayedObservationSelector().select(d01)
    validate_observation_selection(d01, selection)
    index, row = next(
        (i, c)
        for i, c in enumerate(selection.candidates)
        if c.exclusion is PresentationExclusion.CAP_EXCEEDED
    )
    forged = replace(row, exclusion=PresentationExclusion.CONTEXT_ONLY)
    candidates = selection.candidates[:index] + (forged,) + selection.candidates[index + 1 :]
    with pytest.raises(InvalidScenarioSummaryError):
        validate_observation_selection(d01, replace(selection, candidates=candidates))
    swapped = replace(selection, selected_keys=tuple(reversed(selection.selected_keys)))
    with pytest.raises(InvalidScenarioSummaryError):
        validate_observation_selection(d01, swapped)


def test_d16_wrong_digest_sentence_and_forged_status_source(d01):
    report = ScenarioSummaryRenderer().render(d01)
    validate_rendered_report(d01, report)
    sentence = report.digest[1]
    wrong = RenderedFactSentence(
        sentence.template_id, sentence.text.replace("d5", "d6"), sentence.source_refs
    )
    with pytest.raises(InvalidScenarioSummaryError):
        validate_rendered_report(d01, replace(report, digest=(report.digest[0], wrong)))
    status = report.detail[0]
    forged = RenderedFactSentence(status.template_id, status.text, report.digest[1].source_refs)
    with pytest.raises(InvalidScenarioSummaryError):
        validate_rendered_report(d01, replace(report, detail=(forged,)))
    observations = compact_observations(d01)
    validate_compact_observations(d01, observations)
    with pytest.raises(InvalidScenarioSummaryError):
        validate_compact_observations(d01, tuple(reversed(observations)))


def test_played_rendering_and_selection_make_no_adapter_calls(d01, monkeypatch):
    for name in (
        "observe_position",
        "observe_tactics",
        "legal_move_from_uci",
        "apply_move",
        "position_from_fen",
    ):
        monkeypatch.setattr(PythonChessAdapter, name, Mock(side_effect=AssertionError(name)))
    ScenarioSummaryRenderer().render(d01)
    PlayedObservationSelector().select(d01)
    validate_scenario_summary(d01)


def test_exactly_one_activity_line_replay():
    inner = service()
    spy = Mock(wraps=inner.activity_lines)
    ScenarioLineAnalyzer(spy).analyze(played(START, "e2e4"))
    assert spy.analyze.call_count == 1
    assert spy.analyze.call_args.kwargs == {"max_plies": 1}
