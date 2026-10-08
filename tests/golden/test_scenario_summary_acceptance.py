"""A2 acceptance against the independently frozen A1 v2 corpus, including color mirrors."""

from copy import deepcopy

import chess
import pytest
from test_scenario_design_observations import (
    CASES,
    build,
    mirror_move,
    mirror_square,
    mirror_type_key,
)

from calliope.domain.analysis.scenario import (
    Bucket,
    CaptureKey,
    PinKey,
    ScenarioKind,
    ScenarioRequest,
    SnapshotKey,
    SquareTarget,
    StepKey,
    TemplateId,
    TransitionKey,
)
from calliope.domain.chess import ChessMove, square_index
from calliope.services.position.scenario import ScenarioLineAnalyzer, resolve_source
from calliope.services.position.scenario_renderer import ScenarioSummaryRenderer


def mirror_expectations(case):
    result = deepcopy(case)
    result["fen"] = chess.Board(case["fen"]).mirror().fen()
    result["moves"] = [mirror_move(m) for m in case["moves"]]
    result["focus"] = mirror_square(case["focus"])
    result["material"] = {mirror_type_key(k): v for k, v in case["material"].items()}
    e = result["summary_expectations"]
    e["participants"] = sorted(map(mirror_square, e["participants"]), key=square_index)
    e["focus_losses"] = {mirror_type_key(k): v for k, v in e["focus_losses"].items()}
    for group in (
        "included_fact_keys",
        "excluded_fact_keys",
        "absent_fact_keys",
        "temporary_tracks",
        "castling_context",
        "required_digest_events",
    ):
        entries = e.get(group, [])
        if isinstance(entries, dict):
            entries = [entries]
        for key in entries:
            for name in ("subject", "square", "from", "to", "landing", "victim_square"):
                if name in key:
                    key[name] = mirror_square(key[name])
            if "pin" in key:
                key["pin"] = [mirror_square(s) for s in key["pin"]]
            if "direction" in key:
                key["direction"][1] *= -1
            if "uci" in key:
                key["uci"] = mirror_move(key["uci"])
    return result


def descriptor(key, scope):
    result = {"scope": scope}
    if type(key) is StepKey:
        result["ply"], key = key.ply, key.property
    if type(key) is SnapshotKey:
        result["frame"], key = key.frame, key.property
    result["family"] = key.family.value
    if type(key) in (CaptureKey, TransitionKey):
        result["ply"] = key.ply
    for name in ("square", "file", "direction"):
        if hasattr(key, name):
            value = getattr(key, name)
            result[name] = list(value) if type(value) is tuple else value
    if hasattr(key, "subject"):
        result["subject"] = key.subject.base_square
    if type(key) is PinKey:
        result["pin"] = [b.base_square for b in (key.pinner, key.pinned, key.king)]
    return result


SCOPES = {
    Bucket.STEPS: "step",
    Bucket.ENDPOINTS: "endpoint",
    Bucket.EVENTS: "event",
    Bucket.SNAPSHOTS: "snapshot",
}


def assert_expected(summary, case):
    expected = case["summary_expectations"]
    assert [p.base.base_square for p in summary.detail.participants] == expected["participants"]
    assert summary.detail.status.value == expected["status"]
    assert {
        f"{c.key.color.value}:{c.key.piece_type.value}": c.count
        for c in summary.detail.focus_capture_losses
    } == expected["focus_losses"]
    assert {
        f"{c.key.color.value}:{c.key.piece_type.value}": c.count
        for c in summary.detail.whole_line_material_changes
    } == case["material"]
    included, excluded, candidates = [], [], []
    for row in summary.selection_accounting:
        if row.bucket in SCOPES:
            scope = SCOPES[row.bucket]
            included.extend(descriptor(k, scope) for k in row.included_keys)
            excluded.extend(descriptor(k, scope) for k in row.excluded_keys)
            candidates.extend(descriptor(k, scope) for k in row.candidate_keys)
        assert row.candidate_count == row.included_count + row.excluded_count
    included.extend(descriptor(h.key, "history") for h in summary.feature_histories)
    for group, actual in (("included_fact_keys", included), ("excluded_fact_keys", excluded)):
        for key in expected[group]:
            target = {k: v for k, v in key.items() if k != "reasons"}
            assert target in actual, (case["id"], group, key)
            if "reasons" in key:
                event = next(e for e in summary.events if descriptor(e.key, "event") == target)
                assert [r.value for r in event.reasons] == key["reasons"]
    for key in expected["absent_fact_keys"]:
        assert key not in candidates
    for track in expected.get("temporary_tracks", []):
        key = {k: v for k, v in track.items() if k != "values"}
        history = next(
            h
            for h in summary.feature_histories
            if descriptor(h.key, "history") == dict(scope="history", **key)
        )
        assert [f.value for r in history.runs for f in r.facts] == track["values"]
    if "temporary_track_count" in expected:
        assert summary.detail.temporary_track_count == expected["temporary_track_count"]


@pytest.mark.parametrize("mirrored", (False, True), ids=("base", "color-mirror"))
@pytest.mark.parametrize("original", CASES, ids=lambda c: c["id"])
def test_frozen_selection_and_renderer_acceptance(original, mirrored):
    case = mirror_expectations(original) if mirrored else original
    rules, activity = build()
    request = ScenarioRequest(
        ScenarioKind.EXCHANGE,
        SquareTarget(case["focus"]),
        rules.position_from_fen(case["fen"]),
        tuple(ChessMove(m) for m in case["moves"]),
    )
    summary = ScenarioLineAnalyzer(activity).analyze(request)
    assert_expected(summary, case)
    report = ScenarioSummaryRenderer().render(summary)
    expected = case["summary_expectations"]
    assert set(map(TemplateId, expected.get("required_templates", []))) <= {
        s.template_id for s in report.detail
    }
    for required in expected.get("required_digest_events", []):
        sentences = [s for s in report.digest if s.template_id.value == required["template"]]
        assert any(
            required["landing"] in s.text and required["victim_square"] in s.text for s in sentences
        )
    castling = expected.get("castling_context")
    if castling:
        assert any(
            s.template_id is TemplateId.CASTLING_ROOK
            and castling["uci"] in s.text
            and f"from {castling['from']} to {castling['to']}" in s.text
            for s in report.detail
        )
    for sentence in (*report.digest, *report.detail):
        assert sentence.text.startswith("In the supplied line,") and sentence.source_refs
        for ref in sentence.source_refs:
            resolve_source(summary, ref)
    if original["id"] == "E09":
        assert any(
            "geometric attackers" in s.text and ("e7" if mirrored else "e2") in s.text
            for s in report.detail
        )
        assert any(
            s.template_id is TemplateId.FOCUS_LEGAL_CAPTURES_NOW and "are none" in s.text
            for s in report.detail
        )
