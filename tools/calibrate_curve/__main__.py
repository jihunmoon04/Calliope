"""`python -m tools.calibrate_curve`: the calibration run of Q-D §7, start to end.

1. Stream the training month; aggregate (§7.1).
2. Fit every band and apply the band criteria (§7.3).
3. Run the engine-scale check on the sampled positions (§7.4).
4. Stream the validation month until it holds a fifth of the training positions (§7.5 gate 1).
5. Run the gates (§7.5, with the loss of §7.6).
6. Write the report always, and the table only if §7.4 and gates 1–3 pass.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

from calliope.reasoning import load_curve_table
from calliope.reasoning.grading import runtime_scale
from tools.calibrate_curve.data import Training, Validation
from tools.calibrate_curve.gates import validate, weight_flags
from tools.calibrate_curve.pgn import games
from tools.calibrate_curve.scale import ScaleResult, check, engine_evaluator, sample

ROOT = Path(__file__).resolve().parents[2]
FILTERS = "rated; standard; |dElo| <= 100; %eval; ply >= 8; no mate evals; cp clipped to 1500"


class Stream:
    """`curl URL | zstd -dc`, counting the compressed bytes read; stops at `limit` bytes."""

    def __init__(self, url: str, limit: int | None = None) -> None:
        self.url = url
        self.bytes = 0
        self.limit = limit
        self.curl = subprocess.Popen(["curl", "-s", "--fail", url], stdout=subprocess.PIPE)
        self.zstd = subprocess.Popen(
            ["zstd", "-dc"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )  # fmt: skip
        self._stop = threading.Event()
        self._pump = threading.Thread(target=self._run, daemon=True)
        self._pump.start()

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                chunk = self.curl.stdout.read(1 << 20)
                if not chunk:
                    break
                self.bytes += len(chunk)
                self.zstd.stdin.write(chunk)
                if self.limit is not None and self.bytes >= self.limit:
                    break
        except (BrokenPipeError, ValueError):
            pass
        finally:
            try:
                self.zstd.stdin.close()
            except BrokenPipeError:
                pass

    def lines(self):
        return io.TextIOWrapper(self.zstd.stdout, encoding="utf-8", errors="replace")

    def close(self) -> None:
        self._stop.set()
        for p in (self.curl, self.zstd):
            if p.poll() is None:
                p.kill()


def _log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", file=sys.stderr, flush=True)


def train(url: str, limit: int | None) -> tuple[Training, int]:
    training = Training()
    stream = Stream(url, limit)
    try:
        for game in games(stream.lines()):
            training.feed(game)
            if training.games_read % 1_000_000 == 0:
                _log(f"train: {training.games_read} games, {training.games_used} used, "
                     f"{training.positions} positions, {stream.bytes >> 20} MiB")  # fmt: skip
    finally:
        stream.close()
    return training, stream.bytes


def held_out(url: str, target: int) -> tuple[Validation, int]:
    validation = Validation()
    stream = Stream(url)
    try:
        for game in games(stream.lines()):
            validation.feed(game)
            if validation.games_read % 1_000_000 == 0:
                _log(f"validate: {validation.games_read} games, {validation.positions} positions")
            if validation.positions >= target:
                break
    finally:
        stream.close()
    return validation, stream.bytes


def table_text(
    name: str, source: str, read: int, training: Training, fits, scale: ScaleResult
) -> str:
    head = [
        "[table]",
        f'name = "{name}"',
        'pool = "lichess"',
        'model = "logistic10"            # E = 1 / (1 + 10^(−cp / c))',
        "band_width = 200",
        f'source = "{source}"',
        f"bytes_read = {read}",
        f"games_read = {training.games_read}",
        f"games_used = {training.games_used}",
        f'filters = "{FILTERS}"',
        f"cp_ratio_permille = {scale.permille}",
    ]
    rows = []
    for (tc, band), f in sorted(fits.items()):
        if not f.kept:
            continue
        rows += [
            "",
            "[[band]]",
            f'time_class = "{tc}"',
            f"low = {band}",
            f"source_scale = {f.source_scale}",
            f"scale = {runtime_scale(f.source_scale, scale.permille)}",
            f"positions = {f.positions}",
            f"shard_low = {min(f.shard_scales)}",
            f"shard_high = {max(f.shard_scales)}",
        ]
    return "\n".join(head + rows) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.calibrate_curve")
    parser.add_argument("--name", required=True, help="e.g. human_lichess_2026_08_v1")
    parser.add_argument("--train", required=True, help="the training month's .pgn.zst URL")
    parser.add_argument("--validate", required=True, help="the next month's .pgn.zst URL")
    parser.add_argument("--train-bytes", type=int, default=None, help="for trial runs only")
    parser.add_argument("--stockfish", default=os.environ.get("CALLIOPE_STOCKFISH_PATH"))
    parser.add_argument("--table-dir", type=Path, default=ROOT / "src/calliope/reasoning/curves")
    parser.add_argument("--report-dir", type=Path, default=ROOT / "tools/calibrate_curve/reports")
    args = parser.parse_args(argv)

    _log(f"training on {args.train}")
    training, read = train(args.train, args.train_bytes)
    _log(f"train done: {training.games_read} games, {training.games_used} used, "
         f"{training.positions} positions, {read} bytes")  # fmt: skip
    from tools.calibrate_curve.gates import band_fits

    fits = band_fits(training)
    _log(f"bands passing §7.3: {sum(f.kept for f in fits.values())} of {len(fits)}")

    from calliope.facts.search import StockfishEngine

    engine = StockfishEngine.start(args.stockfish)
    try:
        positions = sample(training)
        _log(f"engine-scale check on {len(positions)} positions")
        scale = check(positions, engine_evaluator(engine))
    finally:
        engine.close()
    _log(f"k = {scale.k:.4f}, permille {scale.permille}, failures {scale.failures}")

    validation, read_validation = held_out(args.validate, -(-training.positions // 5))
    _log(f"validation: {validation.games_used} games, {validation.positions} positions")
    report = validate(training, validation, fits)
    passed = scale.passed and all(report.passed.values())

    args.report_dir.mkdir(parents=True, exist_ok=True)
    out = {
        "name": args.name,
        "training": {"source": args.train, "bytes_read": read, "games_read": training.games_read,
                     "games_used": training.games_used, "positions": training.positions},
        "validation": {"source": args.validate, "bytes_read": read_validation,
                       "games_read": validation.games_read, "games_used": validation.games_used,
                       "positions": validation.positions},
        "bands": {f"{tc} {band}": {**asdict(f), "kept": f.kept} for (tc, band), f in fits.items()},
        "pooled": report.pooled,
        "engine_scale": {**asdict(scale), "passed": scale.passed},
        "gates": report.passed,
        "aggregate": report.aggregate,
        "per_band": report.per_band,
        "reliability": report.reliability,
        "game_weighted_flags": weight_flags(fits),
        "selection": report.selection,
        "mate_allowing": report.mate_allowing,
        "table_written": passed,
    }  # fmt: skip
    (args.report_dir / f"{args.name}.json").write_text(
        json.dumps(out, indent=1, default=str) + "\n"
    )
    if not passed:
        _log("gates failed: no table written")
        return 1
    text = table_text(args.name, args.train, read, training, fits, scale)
    load_curve_table(text.encode())  # the runtime's own checks (Q-D §7.2–§7.4)
    args.table_dir.mkdir(parents=True, exist_ok=True)
    (args.table_dir / f"{args.name}.toml").write_text(text)
    _log(f"table written: {args.table_dir / (args.name + '.toml')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
