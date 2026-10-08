"""Development cost smoke, not a production performance guarantee.

Run with explicit PYTHONPATH=src. Observation/replay is outside both timings;
render_ms includes full summary validation and sentence reference resolution.
"""

import json
import platform
from statistics import median
from time import perf_counter

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis.scenario import ScenarioKind, ScenarioRequest, SquareTarget
from calliope.domain.chess import ChessMove
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.position.activity import ActivityAnalyzer, ActivityLineAnalyzer
from calliope.services.position.line import LineAnalyzer
from calliope.services.position.positional import PositionAnalyzer, TransitionAnalyzer
from calliope.services.position.scenario import _project
from calliope.services.position.scenario_renderer import ScenarioSummaryRenderer


def main():
    rules = PythonChessAdapter()
    facts = PositionFactExtractor(rules)
    positions = PositionAnalyzer(facts)
    lines = ActivityLineAnalyzer(
        LineAnalyzer(TransitionAnalyzer(rules, positions, BoardDeltaAnalyzer(rules, facts))),
        ActivityAnalyzer(positions, rules),
    )
    initial = rules.position_from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    renderer = ScenarioSummaryRenderer()
    records = []
    for plies in (0, 1, 64, 256):
        cycle = ("g1f3", "g8f6", "f3g1", "f6g8")
        request = ScenarioRequest(
            ScenarioKind.EXCHANGE,
            SquareTarget("e4"),
            initial,
            tuple(ChessMove(cycle[i % 4]) for i in range(plies)),
            256,
        )
        observed = lines.analyze(initial, request.supplied_line, max_plies=256)
        projection_times, render_times = [], []
        for _ in range(3):
            started = perf_counter()
            summary = _project(request, observed)
            projection_times.append(1000 * (perf_counter() - started))
            started = perf_counter()
            report = renderer.render(summary)
            render_times.append(1000 * (perf_counter() - started))
        records.append(
            {
                "plies": plies,
                "projection_ms": round(median(projection_times), 3),
                "render_ms": round(median(render_times), 3),
                "factual_sentences": len(report.digest) + len(report.detail),
                "feature_tracks": len(summary.feature_histories),
            }
        )
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "repetitions": 3,
                "statistic": "median",
                "line": "starting position knight repetition, focus e4, no capture",
                "projection": "retained observation validation + selection + accounting + compression; excludes replay",
                "render": "full summary recomputation + fixed templates + source resolution; excludes replay",
                "measurements": records,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
