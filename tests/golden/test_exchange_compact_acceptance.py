"""I2 acceptance: compact EXCHANGE observations against the frozen joint corpus (E01-E15).

The corpus (`docs/legacy/corpus/observation-bridge-i2i3-v1.json`) is read-only: selected keys, template
ids, exact English, status/count, cap, context-only and duplicate dispositions are its values.
"""

import json
from pathlib import Path

import pytest
from test_scenario_design_observations import build

from calliope.domain.analysis.scenario import (
    Bucket,
    CaptureKey,
    CountKey,
    ExchangeObservationInput,
    LineOrigin,
    PresentationExclusion,
    ScenarioKind,
    ScenarioRequest,
    SnapshotKey,
    SquareKey,
    SquareTarget,
    StepKey,
    TransitionKey,
)
from calliope.domain.chess import ChessMove
from calliope.services.position.scenario import ScenarioLineAnalyzer, _resolve_source
from calliope.services.position.scenario_observation import (
    ExchangeObservationSelector,
    compact_observations,
)
from calliope.services.position.scenario_renderer import ScenarioSummaryRenderer

ROOT = Path(__file__).resolve().parents[2]
CORPUS = json.loads(
    (ROOT / "docs" / "legacy" / "corpus" / "observation-bridge-i2i3-v1.json").read_text(encoding="utf-8")
)
CASES = CORPUS["cases"]
PUBLIC_MAX_PLIES = CORPUS["constraints"]["max_public_plies_per_line"]


def summarize(case, origin=LineOrigin.USER):
    rules, lines = build()
    request = ScenarioRequest(
        ScenarioKind.EXCHANGE,
        SquareTarget(case["focus"]),
        rules.position_from_fen(case["fen"]),
        tuple(ChessMove(m) for m in case["moves"]),
        PUBLIC_MAX_PLIES,
    )
    wrapped = ExchangeObservationInput(request, origin)
    return ScenarioLineAnalyzer(lines).analyze(wrapped.scenario)


def fmt(bucket, key):
    """The joint corpus' shorthand for a typed (Bucket, CandidateKey)."""
    if type(key) is CaptureKey:
        return f"EVENTS/CAPTURE:ply{key.ply}:capture"
    if type(key) is TransitionKey:
        return f"EVENTS/{key.family.value}:ply{key.ply}:base-{key.subject.base_square}"
    if type(key) is CountKey:
        return f"AGGREGATES/{key.family.value}:{key.color.value}:{key.piece_type.value}"
    if type(key) is SnapshotKey:
        return (
            f"SNAPSHOTS/{key.property.family.value}:square-{key.property.square};frame={key.frame}"
        )
    inner = key.property if type(key) is StepKey else key
    if type(inner) is SquareKey:
        selector = f"square-{inner.square}"
    elif hasattr(inner, "subject"):
        selector = f"base-{inner.subject.base_square}"
        if hasattr(inner, "direction"):
            selector += ":dir-{},{}".format(*inner.direction)
    elif hasattr(inner, "file"):
        selector = f"file-{inner.file}"
    else:
        selector = (
            f"pin-{inner.pinner.base_square}:{inner.pinned.base_square}:{inner.king.base_square}"
        )
    suffix = f";ply={key.ply}" if type(key) is StepKey else ""
    return f"{bucket.value.upper()}/{inner.family.value}:{selector}{suffix}"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_frozen_compact_selection_text_and_status(case):
    summary = summarize(case)
    assert summary.detail.status.value == case["expected_status"]
    assert len(summary.detail.focus_capture_events) == case["expected_focus_capture_count"]
    observations = compact_observations(summary)
    assert len(observations) <= case["cap"] == 2
    assert [
        {
            "key": fmt(o.bucket, o.key),
            "template_id": o.sentence.template_id.value,
            "text": o.sentence.text,
            "source_kind": o.sentence.source_refs[0].kind.value,
        }
        for o in observations
    ] == case["selected"]
    assert [o.sentence.source_refs[0].kind.value for o in observations] == case[
        "selected_source_kind"
    ]

    selection = ExchangeObservationSelector().select(summary)
    ledger = {fmt(c.bucket, c.key): c for c in selection.candidates}
    for key in case["candidate_cap_exclusions"]:
        assert ledger[key].exclusion is PresentationExclusion.CAP_EXCEEDED, key
    for key in case["candidate_context_only"]:
        assert ledger[key].exclusion is PresentationExclusion.CONTEXT_ONLY, key
    for row in case.get("candidate_semantic_duplicates", []):
        candidate = ledger[row["key"]]
        assert candidate.exclusion is PresentationExclusion.SEMANTIC_DUPLICATE
        assert fmt(Bucket.STEPS, candidate.duplicate_of) == row["duplicate_of"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_ledger_partitions_every_core_included_fact(case):
    summary = summarize(case)
    selection = ExchangeObservationSelector().select(summary)
    core = [(r.bucket, k) for r in summary.selection_accounting for k in r.included_keys]
    assert [(c.bucket, c.key) for c in selection.candidates] == core
    assert {(c.bucket, c.key) for c in selection.candidates if c.exclusion is None} == set(
        selection.selected_keys
    )
    # Capped or contextual facts remain in the untouched core summary and legacy report.
    again = summarize(case)
    assert again == summary
    assert ScenarioSummaryRenderer().render(summary) == ScenarioSummaryRenderer().render(again)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_compact_sources_are_the_underlying_record_sources(case):
    summary = summarize(case)
    events = {e.key: e for e in summary.events}
    counts = {
        c.key: c
        for c in (*summary.detail.whole_line_material_changes, *summary.detail.focus_capture_losses)
    }
    changes = {StepKey(c.after.frame, c.key): c for c in summary.selected_changes}
    changes.update({c.key: c for c in summary.endpoint_changes})
    for observation in compact_observations(summary):
        refs = observation.sentence.source_refs
        if observation.bucket is Bucket.EVENTS:
            assert refs == events[observation.key].source_refs
        elif observation.bucket is Bucket.AGGREGATES:
            assert refs == counts[observation.key].source_refs
        else:
            change = changes[observation.key]
            expected = tuple(dict.fromkeys((*change.before.source_refs, *change.after.source_refs)))
            assert refs == expected
        for ref in refs:
            _resolve_source(summary, ref)


def test_e06_capture_promotion_dependency_and_e08_context_material():
    e06 = next(c for c in CASES if c["id"] == "E06")
    keys = [fmt(o.bucket, o.key) for o in compact_observations(summarize(e06))]
    assert keys == ["EVENTS/CAPTURE:ply1:capture", "EVENTS/PROMOTION:ply1:base-a7"]
    e08 = next(c for c in CASES if c["id"] == "E08")
    keys = [fmt(o.bucket, o.key) for o in compact_observations(summarize(e08))]
    assert keys == ["EVENTS/CAPTURE:ply1:capture", "STEPS/FOCUS_OCCUPANT:square-e4;ply=1"]


@pytest.mark.parametrize("origin", list(LineOrigin))
def test_origin_is_provenance_not_evidence(origin):
    case = next(c for c in CASES if c["id"] == "E03")
    assert compact_observations(summarize(case, origin)) == compact_observations(summarize(case))
