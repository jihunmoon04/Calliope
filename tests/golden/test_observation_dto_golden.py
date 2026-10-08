"""I3: the complete schema-0.3 serialization equals the frozen synthetic DTO golden.

The nested v0.2 payload is the golden's synthetic stub (never a Stockfish claim); every
observation section, sentence, identifier and source reference is produced by the real
python-chess observation path for D13 played e4d5 plus E02 supplied EXCHANGE at the same root.
"""

import dataclasses
import json
import subprocess
import sys
from pathlib import Path

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.application.observe_move import ObservedMoveService
from calliope.contracts import (
    AnalyzeMoveRequest,
    JudgementSummary,
    MoveAnalysisResult,
    ObservedMoveRequest,
    SuppliedExchangeObservationRequest,
)
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.position.activity import ActivityAnalyzer, ActivityLineAnalyzer
from calliope.services.position.line import LineAnalyzer
from calliope.services.position.positional import PositionAnalyzer, TransitionAnalyzer
from calliope.services.position.scenario import ScenarioLineAnalyzer

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "docs" / "corpus"
GOLDEN = json.loads((CORPUS / "observation-bridge-i3-dto-golden.json").read_text(encoding="utf-8"))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stub_legacy():
    base = GOLDEN["result"]["base_result"]
    result = MoveAnalysisResult(
        schema_version=base["schema_version"],
        position_fen=base["position_fen"],
        judgement=JudgementSummary(**base["judgement"]),
        claims=(),
        selected_claim_ids=(),
        variations=(),
        commentary=None,
        metadata=base["metadata"],
    )

    class Legacy:
        def __init__(self):
            self.calls = []

        def execute(self, request):
            self.calls.append(request)
            return result

    return Legacy()


def build_service(legacy):
    rules = PythonChessAdapter()
    facts = PositionFactExtractor(rules)
    positions = PositionAnalyzer(facts)
    scenarios = ScenarioLineAnalyzer(
        ActivityLineAnalyzer(
            LineAnalyzer(TransitionAnalyzer(rules, positions, BoardDeltaAnalyzer(rules, facts))),
            ActivityAnalyzer(positions, rules),
        )
    )
    return ObservedMoveService(legacy, rules, scenarios)


def test_complete_v03_serialization_matches_the_frozen_golden():
    legacy = stub_legacy()
    base = AnalyzeMoveRequest(GOLDEN["source_position_fen"], "e4d5")
    request = ObservedMoveRequest(
        base, True, (SuppliedExchangeObservationRequest("d5", ("e4d5",)),)
    )
    result = build_service(legacy).execute(request)
    assert legacy.calls == [base]
    encoded = canonical(dataclasses.asdict(result))
    assert json.loads(encoded) == GOLDEN["result"]
    assert encoded == canonical(GOLDEN["result"])
    assert GOLDEN["fixture_kind"] == "synthetic_legacy_dto_factual_observation"


def test_frozen_corpus_checkers_pass_in_both_modes():
    for checker in ("check_played_transition_i1d.py", "check_observation_bridge_i2i3.py"):
        for mode in ("--schema-only", "--full"):
            run = subprocess.run(
                [sys.executable, "-X", "utf8", "-I", str(CORPUS / checker), mode],
                capture_output=True,
                text=True,
                check=False,
            )
            assert run.returncode == 0, (checker, mode, run.stdout, run.stderr)
            assert "PASS" in run.stdout
