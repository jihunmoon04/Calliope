"""`python -m tools.calibrate_curve`: the calibration run of QM-D (amending Q-D §7), start to end.

1. Stream the training month; aggregate (Q-D §7.1).
2. Select the bands in the training month only (QM-D §6.1).
3. Run the engine-scale check on the sampled positions (Q-D §7.4).
4. Fix the curves, then stream the validation month until it holds a fifth of the training
   positions, scoring as it goes (QM-D §6.2, gate 1).
5. Run the gates (QM-D §6.2, with the loss of §6.3).
6. Write the report always, and the table only for a whole training file whose streams ended
   cleanly, with §7.4 and gates 1–3 passed (QM-D §8.3). A run with a byte limit is exploratory:
   its report says `partial`, and it never writes a table.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

from calliope.reasoning import MONOTONE_V1_KNOTS, load_curve_table
from tools.calibrate_curve.data import Training, Validation
from tools.calibrate_curve.gates import BandFit, Curves, pooled, select, validate, weight_flags
from tools.calibrate_curve.pgn import games
from tools.calibrate_curve.scale import check, engine_evaluator, sample

ROOT = Path(__file__).resolve().parents[2]
FILTERS = (
    "rated; standard; |dElo| <= 100; %eval contiguous; ply >= 8; no mate evals; cp clipped to 1500"
)
FIT = "symmetrized; gaussian h = knot spacing; coverage 400; weighted isotonic; round half-even"
COUNTS = "https://database.lichess.org/standard/counts.txt"


def content_length(url: str) -> int | None:
    """The `Content-Length` of a HEAD request, after redirects (QM-D §8.3)."""

    out = subprocess.run(["curl", "-sSIL", "--fail", url], capture_output=True, text=True,
                         check=False)  # fmt: skip
    if out.returncode:
        return None
    lengths = [
        int(line.split(":", 1)[1])
        for line in out.stdout.splitlines()
        if line.lower().startswith("content-length:")
    ]
    return lengths[-1] if lengths else None


def published_games(url: str) -> int | None:
    """Lichess's published game count for the file, if any (reported, not a gate)."""

    out = subprocess.run(["curl", "-sS", "--fail", COUNTS], capture_output=True, text=True,
                         check=False)  # fmt: skip
    name = url.rsplit("/", 1)[-1]
    for line in out.stdout.splitlines() if not out.returncode else ():
        parts = line.split()
        if len(parts) == 2 and parts[0] == name and parts[1].isdigit():
            return int(parts[1])
    return None


class Stream:
    """`curl URL | zstd -dc`, counting the compressed bytes read; stops at `limit` bytes. The
    status after reading checks both exit codes and the byte count (QM-D §8.3)."""

    def __init__(self, url: str, limit: int | None = None) -> None:
        self.url = url
        self.bytes = 0
        self.limit = limit
        self.length = content_length(url)
        self.curl = subprocess.Popen(["curl", "-sS", "--fail", url], stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)  # fmt: skip
        self.zstd = subprocess.Popen(
            ["zstd", "-dcq"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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

    def status(self, stopped: bool = False) -> dict:
        """After the reader is done. `stopped`: it stopped on purpose (the validation target)."""

        out = {"url": self.url, "bytes_read": self.bytes, "content_length": self.length,
               "limit": self.limit, "stopped_at_target": stopped, "failures": []}  # fmt: skip
        if stopped:
            self._kill()
            return out
        zstd = self.zstd.wait()
        self._pump.join()
        at_limit = self.limit is not None and self.bytes >= self.limit
        if at_limit:
            self._kill()  # the stream was cut on purpose; zstd's truncation error is expected
            return out
        curl = self.curl.wait()
        if curl:
            out["failures"].append(f"curl exited {curl}: {self.curl.stderr.read().decode()[:300]}")
        if zstd:
            out["failures"].append(f"zstd exited {zstd}: {self.zstd.stderr.read().decode()[:300]}")
        if self.limit is None and self.length is None:
            out["failures"].append("no Content-Length to check the read against")
        elif self.limit is None and self.bytes != self.length:
            out["failures"].append(f"read {self.bytes} bytes of {self.length}")
        return out

    def _kill(self) -> None:
        self._stop.set()
        for p in (self.curl, self.zstd):
            if p.poll() is None:
                p.kill()
            p.wait()


def _log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", file=sys.stderr, flush=True)


def train(url: str, limit: int | None) -> tuple[Training, dict]:
    training = Training()
    stream = Stream(url, limit)
    for game in games(stream.lines()):
        training.feed(game)
        if training.games_read % 1_000_000 == 0:
            _log(f"train: {training.games_read} games, {training.games_used} used, "
                 f"{training.positions} positions, {stream.bytes >> 20} MiB")  # fmt: skip
    return training, stream.status()


def held_out(url: str, target: int, curves: Curves) -> tuple[Validation, dict]:
    validation = Validation(curves)
    stream = Stream(url)
    stopped = False
    for game in games(stream.lines()):
        validation.feed(game)
        if validation.games_read % 1_000_000 == 0:
            _log(f"validate: {validation.games_read} games, {validation.positions} positions")
        if validation.positions >= target:
            stopped = True
            break
    return validation, stream.status(stopped)


def table_text(
    name: str, source: str, read: int, training: Training, fits: dict, permille: int
) -> str:
    head = [
        "[table]",
        f'name = "{name}"',
        'pool = "lichess"',
        'model = "monotone_v1"',
        "band_width = 200",
        f"knots = {list(MONOTONE_V1_KNOTS)}",
        f'source = "{source}"',
        f"bytes_read = {read}",
        f"games_read = {training.games_read}",
        f"games_used = {training.games_used}",
        f'filters = "{FILTERS}"',
        f'fit = "{FIT}"',
        f"cp_ratio_permille = {permille}",
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
            f"points = {list(f.points)}",
            f"positions = {f.positions}",
            f"shard_deviation = {math.ceil(f.shard_deviation)}",
            f"interpolated = {list(f.interpolated)}",
        ]
    return "\n".join(head + rows) + "\n"


def _band(f: BandFit) -> dict:
    return {**asdict(f), "kept": f.kept}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.calibrate_curve")
    parser.add_argument("--name", required=True, help="e.g. human_lichess_2026_08_v2")
    parser.add_argument("--train", required=True, help="the training month's .pgn.zst URL")
    parser.add_argument("--validate", required=True, help="the next month's .pgn.zst URL")
    parser.add_argument("--train-bytes", type=int, default=None,
                        help="exploratory runs only: the report says partial, no table")  # fmt: skip
    parser.add_argument("--stockfish", default=os.environ.get("CALLIOPE_STOCKFISH_PATH"))
    parser.add_argument("--table-dir", type=Path, default=ROOT / "src/calliope/reasoning/curves")
    parser.add_argument("--report-dir", type=Path, default=ROOT / "tools/calibrate_curve/reports")
    args = parser.parse_args(argv)
    partial = args.train_bytes is not None

    _log(f"training on {args.train}{' (exploratory)' if partial else ''}")
    training, train_stream = train(args.train, args.train_bytes)
    _log(f"train done: {training.games_read} games, {training.games_used} used, "
         f"{training.positions} positions, {train_stream}")  # fmt: skip
    fits = select(training)
    pools = pooled(training)
    _log(f"bands kept by QM-D §6.1: {sum(f.kept for f in fits.values())} of {len(fits)}")

    from calliope.facts.search import StockfishEngine

    engine = StockfishEngine.start(args.stockfish)
    try:
        positions = sample(training)
        _log(f"engine-scale check on {len(positions)} positions")
        scale = check(positions, engine_evaluator(engine))
    finally:
        engine.close()
    _log(f"k = {scale.k:.4f}, permille {scale.permille}, failures {scale.failures}")

    curves = Curves(fits, pools)  # fixed before the validation month is read (QM-D §6.1)
    validation, validation_stream = held_out(args.validate, -(-training.positions // 5), curves)
    _log(f"validation: {validation.games_used} games, {validation.positions} positions, "
         f"{validation_stream}")  # fmt: skip
    report = validate(training, validation, curves)
    streams_ok = not train_stream["failures"] and not validation_stream["failures"]
    passed = streams_ok and scale.passed and all(report.passed.values())
    write = passed and not partial

    args.report_dir.mkdir(parents=True, exist_ok=True)
    out = {
        "name": args.name,
        "partial": partial,
        "training": {"stream": train_stream, "games_read": training.games_read,
                     "published_games": published_games(args.train),
                     "games_used": training.games_used,
                     "games_eval_gap": training.games_eval_gap, "positions": training.positions},
        "validation": {"stream": validation_stream, "games_read": validation.games_read,
                       "games_used": validation.games_used,
                       "games_eval_gap": validation.games_eval_gap,
                       "positions": validation.positions},
        "bands": {f"{tc} {band}": _band(f) for (tc, band), f in fits.items()},
        "pooled": pools,
        "engine_scale": {**asdict(scale), "passed": scale.passed},
        "gates": report.passed,
        "aggregate": report.aggregate,
        "per_band": report.per_band,
        "reliability": report.reliability,
        "plateaus": report.plateaus,
        "game_weighted": weight_flags(fits),
        "selection": report.selection,
        "mate_allowing": report.mate_allowing,
        "table_written": write,
    }  # fmt: skip
    (args.report_dir / f"{args.name}.json").write_text(
        json.dumps(out, indent=1, default=str) + "\n"
    )
    if not write:
        _log("no table written" + (" (exploratory run)" if partial and passed else ""))
        return 0 if partial and passed else 1
    text = table_text(args.name, args.train, train_stream["bytes_read"], training, fits,
                      scale.permille)  # fmt: skip
    load_curve_table(text.encode())  # the runtime's own checks (QM-D §9)
    args.table_dir.mkdir(parents=True, exist_ok=True)
    (args.table_dir / f"{args.name}.toml").write_text(text)
    _log(f"table written: {args.table_dir / (args.name + '.toml')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
