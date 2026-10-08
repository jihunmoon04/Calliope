"""D17: EXCHANGE v1 summaries and reports stay byte-identical to the pre-I1 baseline.

`scenario_exchange_v1_baseline.json` was captured at bf43f27 (before any I1-I3 source edit) by
hashing ``repr()`` of every E01-E15 ScenarioSummary and RenderedScenarioReport.
"""

import hashlib
import json
from pathlib import Path

import pytest
from test_scenario_design_observations import CASES, build

from calliope.domain.analysis.scenario import (
    ScenarioKind,
    ScenarioRequest,
    SelectionReason,
    SquareTarget,
)
from calliope.domain.chess import ChessMove
from calliope.services.position.scenario import ScenarioLineAnalyzer
from calliope.services.position.scenario_renderer import ScenarioSummaryRenderer

BASELINE = json.loads(
    Path(__file__).with_name("scenario_exchange_v1_baseline.json").read_text(encoding="utf-8")
)
EXPECTED = {c["id"]: c for c in BASELINE["cases"]}


def sha(value):
    return hashlib.sha256(repr(value).encode()).hexdigest()


def test_baseline_predates_the_implementation():
    assert BASELINE["base_commit"] == "bf43f27953bac04b4f99d209627f6fbe0346fd30"
    assert sorted(EXPECTED) == sorted(c["id"] for c in CASES)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_exchange_summary_and_report_bytes_unchanged(case):
    rules, lines = build()
    request = ScenarioRequest(
        ScenarioKind.EXCHANGE,
        SquareTarget(case["focus"]),
        rules.position_from_fen(case["fen"]),
        tuple(ChessMove(m) for m in case["moves"]),
    )
    summary = ScenarioLineAnalyzer(lines).analyze(request)
    report = ScenarioSummaryRenderer().render(summary)
    expected = EXPECTED[case["id"]]
    assert [[s.template_id.value, s.text] for s in report.digest] == expected["digest"]
    assert len(report.detail) == expected["detail_count"]
    detail_text = "\n".join(s.text for s in report.detail).encode()
    assert hashlib.sha256(detail_text).hexdigest() == expected["detail_text_sha256"]
    assert sha(report) == expected["report_repr_sha256"]
    assert sha(summary) == expected["summary_repr_sha256"]
    assert summary.definition_version == "scenario_summary_v1"
    assert summary.detail.definition_version == "exchange_rules_v1"
    reasons = {r for e in summary.events for r in e.reasons}
    reasons |= {
        r for c in (*summary.selected_changes, *summary.endpoint_changes) for r in c.reasons
    }
    assert SelectionReason.PLAYED_CHANGE not in reasons
