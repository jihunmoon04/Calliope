"""I1-I3 observation cost measurement (development evidence, not a production SLA).

Usage (explicit source tree, UTF-8 mode):

    PYTHONPATH=src python -X utf8 benchmarks/observation_bridge_cost.py \
        --stockfish /path/to/stockfish --repeat 20 --warmup 3 --out cost.json

Worst permitted opt-in request: the played move plus two explicit 8-ply EXCHANGE lines from the
same root. Every component is timed separately after warm-up; the first (cold) observation run
and the first legacy run are reported on their own. Nothing here skips any validation.
"""

import argparse
import json
import os
import platform
import random
import subprocess
import time
from statistics import median, quantiles

import chess

from calliope import (
    AnalysisBudget,
    AnalysisOptions,
    AnalyzeMoveRequest,
    ObservedMoveRequest,
    OutputMode,
    SuppliedExchangeObservationRequest,
)
from calliope.adapters.python_chess import PythonChessAdapter
from calliope.application import observe_move
from calliope.application.observe_move import ObservedMoveService, _preflight_shape, _sentences
from calliope.composition import create_calliope_engine
from calliope.domain.analysis.scenario import (
    PlayedMoveTarget,
    ScenarioKind,
    ScenarioRequest,
    SquareTarget,
)
from calliope.domain.chess import ChessMove
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.position.activity import ActivityAnalyzer, ActivityLineAnalyzer
from calliope.services.position.line import LineAnalyzer
from calliope.services.position.positional import PositionAnalyzer, TransitionAnalyzer
from calliope.services.position.scenario import (
    ScenarioLineAnalyzer,
    _project,
    validate_scenario_summary,
)
from calliope.services.position.scenario_observation import _compact_after_validation, _select
from calliope.services.position.scenario_renderer import ScenarioSummaryRenderer

ROOT_FEN = "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
BUDGET = AnalysisBudget(depth=12, multipv=3)


def capture_heavy_line(seed, plies=8):
    """Deterministic legal line preferring captures, so focus facts and events exist."""
    rng, board, moves, landings = random.Random(seed), chess.Board(ROOT_FEN), [], []
    for _ in range(plies):
        legal = sorted(board.legal_moves, key=lambda m: m.uci())
        captures = [m for m in legal if board.is_capture(m)]
        move = rng.choice(captures or legal)
        if board.is_capture(move):
            landings.append(chess.square_name(move.to_square))
        moves.append(move.uci())
        board.push(move)
    assert not board.is_game_over()
    return (landings[0] if landings else moves[0][2:4]), tuple(moves)


def stats(values):
    q = quantiles(values, n=20) if len(values) >= 2 else values * 19
    return {
        "n": len(values),
        "min_ms": round(min(values), 3),
        "median_ms": round(median(values), 3),
        "p95_ms": round(q[18], 3),
        "max_ms": round(max(values), 3),
    }


def timed(fn, *args):
    start = time.perf_counter_ns()
    value = fn(*args)
    return value, (time.perf_counter_ns() - start) / 1e6


def observation_graph():
    rules = PythonChessAdapter()
    facts = PositionFactExtractor(rules)
    positions = PositionAnalyzer(facts)
    lines = ActivityLineAnalyzer(
        LineAnalyzer(TransitionAnalyzer(rules, positions, BoardDeltaAnalyzer(rules, facts))),
        ActivityAnalyzer(positions, rules),
    )
    return rules, lines, ScenarioLineAnalyzer(lines)


def components(rules, activity_lines, request, repeat, warmup):
    """Per-section replay/projection/validation/ledger/render/DTO times plus preflight."""
    records = {}
    initial = rules.position_from_fen(request.base.fen)
    played = rules.legal_move_from_uci(initial, request.base.move_uci)
    sections = [
        (
            "p",
            ScenarioRequest(
                ScenarioKind.PLAYED_TRANSITION, PlayedMoveTarget(played), initial, (played,), 1
            ),
        )
    ]
    for i, line in enumerate(request.exchange_lines):
        current, moves = initial, []
        for uci in line.moves_uci:
            move = rules.legal_move_from_uci(current, uci)
            moves.append(move)
            current = rules.apply_move(current, move)
        sections.append(
            (
                f"x{i}",
                ScenarioRequest(
                    ScenarioKind.EXCHANGE, SquareTarget(line.focus_square), initial, tuple(moves), 8
                ),
            )
        )

    def preflight():
        _preflight_shape(request)
        root = rules.position_from_fen(request.base.fen)
        rules.legal_move_from_uci(root, request.base.move_uci)
        for line in request.exchange_lines:
            current = root
            for uci in line.moves_uci:
                current = rules.apply_move(current, rules.legal_move_from_uci(current, uci))

    samples = {"preflight": []}
    for name, _ in sections:
        for part in (
            "replay",
            "projection",
            "full_validation",
            "ledger",
            "compact_render",
            "dto_projection",
        ):
            samples[f"{name}.{part}"] = []
    for iteration in range(warmup + repeat):
        keep = iteration >= warmup
        _, t = timed(preflight)
        if keep:
            samples["preflight"].append(t)
        for name, scenario in sections:
            start = time.perf_counter_ns()
            observed = activity_lines.analyze(
                scenario.initial, scenario.supplied_line, max_plies=scenario.max_plies
            )
            t_replay = (time.perf_counter_ns() - start) / 1e6
            summary, t_project = timed(_project, scenario, observed)
            _, t_validate = timed(validate_scenario_summary, summary)
            _, t_ledger = timed(_select, summary)
            observations, t_render = timed(_compact_after_validation, summary)
            _, t_dto = timed(_sentences, name, observations)
            if keep:
                for part, t in (
                    ("replay", t_replay),
                    ("projection", t_project),
                    ("full_validation", t_validate),
                    ("ledger", t_ledger),
                    ("compact_render", t_render),
                    ("dto_projection", t_dto),
                ):
                    samples[f"{name}.{part}"].append(t)
    records = {k: stats(v) for k, v in samples.items()}
    records["sections"] = {
        name: {"kind": s.kind.value, "plies": len(s.supplied_line)} for name, s in sections
    }
    return records


def end_to_end(stockfish, request, repeat, warmup):
    rules, _, scenarios = observation_graph()
    # Observation-only total: legacy replaced by a precomputed result (zero engine work).
    with create_calliope_engine(stockfish) as engine:
        start = time.perf_counter_ns()
        legacy_result = engine.analyze_move(request.base)
        legacy_cold = (time.perf_counter_ns() - start) / 1e6

        class Instant:
            def execute(self, _):
                return legacy_result

        service = ObservedMoveService(Instant(), rules, scenarios)
        renders = []
        original = ScenarioSummaryRenderer.render

        def counting(self, summary):
            renders.append(summary.request.kind)
            return original(self, summary)

        ScenarioSummaryRenderer.render = counting
        try:
            _, observation_cold = timed(service.execute, request)
            observation, legacy, opt_in = [], [], []
            for iteration in range(warmup + repeat):
                _, t_obs = timed(service.execute, request)
                _, t_legacy = timed(engine.analyze_move, request.base)
                _, t_opt = timed(engine.analyze_move_with_observations, request)
                if iteration >= warmup:
                    observation.append(t_obs)
                    legacy.append(t_legacy)
                    opt_in.append(t_opt)
        finally:
            ScenarioSummaryRenderer.render = original
    paired = [o - lg for o, lg in zip(opt_in, legacy, strict=True)]
    return {
        "observation_only_cold_ms": round(observation_cold, 3),
        "legacy_cold_ms": round(legacy_cold, 3),
        "observation_only_total": stats(observation),
        "legacy_analyze_move": stats(legacy),
        "analyze_move_with_observations": stats(opt_in),
        "paired_delta_opt_in_minus_legacy": stats(paired),
        "legacy_full_detail_renderer_calls": len(renders),
    }


def internal_stress():
    rules, activity_lines, _ = observation_graph()
    initial = rules.position_from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    cycle = ("g1f3", "g8f6", "f3g1", "f6g8")
    rows = []
    for plies in (0, 1, 8, 16, 64, 256):
        request = ScenarioRequest(
            ScenarioKind.EXCHANGE,
            SquareTarget("e4"),
            initial,
            tuple(ChessMove(cycle[i % 4]) for i in range(plies)),
            256,
        )
        times = {"replay": [], "projection": [], "compact_with_validation": []}
        for _ in range(3):
            observed, t = timed(
                lambda r=request: activity_lines.analyze(initial, r.supplied_line, max_plies=256)
            )
            times["replay"].append(t)
            summary, t = timed(_project, request, observed)
            times["projection"].append(t)
            _, t = timed(
                lambda s: (validate_scenario_summary(s), _compact_after_validation(s)), summary
            )
            times["compact_with_validation"].append(t)
        rows.append({"plies": plies, **{k: round(median(v), 3) for k, v in times.items()}})
    return rows


def one_ply_kinds(repeat):
    rules, activity_lines, _ = observation_graph()
    cases = {
        "quiet": ("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", "e2e4"),
        "capture": ("4k3/8/8/3p4/8/8/8/3RK3 w - - 0 1", "d1d5"),
        "promotion": ("4k3/P7/8/8/8/8/8/4K3 w - - 0 1", "a7a8q"),
        "castling": ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1g1"),
        "en_passant": ("8/8/8/3pP3/8/8/8/4K2k w - d6 0 1", "e5d6"),
    }
    rows = {}
    for name, (fen, uci) in cases.items():
        initial = rules.position_from_fen(fen)
        move = ChessMove(uci)
        request = ScenarioRequest(
            ScenarioKind.PLAYED_TRANSITION, PlayedMoveTarget(move), initial, (move,), 1
        )
        times = {"replay": [], "projection": [], "full_validation": [], "ledger_and_render": []}
        for _ in range(repeat + 2):
            observed, t_r = timed(
                lambda i=initial, m=move: activity_lines.analyze(i, (m,), max_plies=1)
            )
            summary, t_p = timed(_project, request, observed)
            _, t_v = timed(validate_scenario_summary, summary)
            _, t_c = timed(_compact_after_validation, summary)
            for key, t in zip(times, (t_r, t_p, t_v, t_c), strict=True):
                times[key].append(t)
        rows[name] = {k: round(median(v[2:]), 3) for k, v in times.items()}
    return rows


def host():
    model = "unknown"
    try:
        model = subprocess.run(["lscpu"], capture_output=True, text=True, check=False).stdout
        model = next(
            (
                l.split(":", 1)[1].strip()
                for l in model.splitlines()
                if l.startswith(("Model name", "Vendor ID"))
            ),
            "unknown",
        )
    except OSError:
        pass
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu": model,
        "logical_cpus": os.cpu_count(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stockfish", required=True)
    parser.add_argument("--repeat", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--out")
    args = parser.parse_args()
    (focus_a, line_a), (focus_b, line_b) = capture_heavy_line(7), capture_heavy_line(11)
    base = AnalyzeMoveRequest(
        ROOT_FEN, line_a[0], AnalysisOptions(budget=BUDGET, output_mode=OutputMode.COMMENTARY)
    )
    request = ObservedMoveRequest(
        base,
        True,
        (
            SuppliedExchangeObservationRequest(focus_a, line_a),
            SuppliedExchangeObservationRequest(focus_b, line_b),
        ),
    )
    rules, activity_lines, _ = observation_graph()
    report = {
        "kind": "development measurement; not a production latency SLA",
        "host": host(),
        "stockfish": os.path.basename(args.stockfish),
        "repeat_after_warmup": args.repeat,
        "warmup": args.warmup,
        "worst_request": {
            "root_fen": ROOT_FEN,
            "played": base.move_uci,
            "exchange_lines": [[focus_a, list(line_a)], [focus_b, list(line_b)]],
            "budget": {"depth": BUDGET.depth, "multipv": BUDGET.multipv},
            "output_mode": "commentary",
        },
        "components_ms": components(rules, activity_lines, request, args.repeat, args.warmup),
        "end_to_end": end_to_end(args.stockfish, request, args.repeat, args.warmup),
        "one_ply_played_medians_ms": one_ply_kinds(args.repeat),
        "internal_exchange_stress_medians_ms": internal_stress(),
        "note": (
            "compact_render includes its own ledger recomputation and source resolution; "
            "ObservedMoveService additionally re-validates each summary inside compact_observations"
        ),
        "observe_move_module": observe_move.__name__,
    }
    text = json.dumps(report, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
