"""`StockfishEngine`: the raw-UCI adapter, the only module that talks to the engine (F4-D §3.3).

python-chess's engine module is deliberately not used: its `analyse()` merges info lines across
depths and drops illegal PV moves (F4-D §2.2).
"""

from __future__ import annotations

import hashlib
import os
import queue
import shutil
import subprocess
import threading
import time
from collections.abc import Sequence
from typing import Self

from calliope.facts.errors import EngineError, EngineOutputError, EngineUnsupportedError
from calliope.facts.search.port import Bound, RawLine, RawSearch, SearchRequest, StoppedBy
from calliope.facts.search.profile import (
    SUPPORTED_ENGINE,
    EngineIdentity,
    EngineOption,
    search_options,
    start_options,
)

READY_TIMEOUT_S = 10.0
STOP_TIMEOUT_S = 10.0
_EOF = object()
_INFO_KEYS = {
    "depth",
    "seldepth",
    "multipv",
    "score",
    "wdl",
    "nodes",
    "nps",
    "hashfull",
    "tbhits",
    "time",
    "pv",
    "currmove",
    "currmovenumber",
    "string",
    "refutation",
    "currline",
    "cpuload",
}


class StockfishEngine:
    """One engine process; one search at a time under the adapter lock."""

    def __init__(self, command: Sequence[str]) -> None:
        """`command[0]` is the engine executable itself (it is the one hashed), not a wrapper."""

        executable = shutil.which(command[0]) or command[0]
        try:
            self._process = subprocess.Popen(
                list(command),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                errors="replace",
            )
        except OSError as error:
            raise EngineError(f"cannot start engine {command[0]!r}: {error}") from None
        self._lines: queue.Queue[object] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self._lock = threading.Lock()
        try:
            self.identity = self._handshake(executable)
            self._send_options(start_options(self.identity))
            self._ready()
        except BaseException:
            self.close()
            raise

    @classmethod
    def start(cls, path: str) -> StockfishEngine:
        return cls([path])

    # -- protocol -------------------------------------------------------------------------------

    def search(self, request: SearchRequest) -> RawSearch:
        with self._lock:
            self._send_options(search_options(self.identity, request.profile, request.multipv))
            self._send("ucinewgame")
            self._send("setoption name Clear Hash")
            self._ready()
            position = f"position fen {request.input.fen}"
            if request.input.moves:
                position += " moves " + " ".join(request.input.moves)
            self._send(position)
            go = f"go depth {request.profile.depth}"
            if request.root_moves is not None:
                go += " searchmoves " + " ".join(request.root_moves)
            started = time.monotonic()
            self._send(go)
            lines, done = self._until("bestmove", request.profile.time_cap_ms / 1000)
            stopped = StoppedBy.DEPTH
            if not done:
                self._send("stop")
                stopped = StoppedBy.TIME  # a race with `bestmove` is classed TIME (F4D-C1)
                more, done = self._until("bestmove", STOP_TIMEOUT_S)
                lines += more
                if not done:
                    self._kill()
                    raise EngineError("no bestmove after stop")
            elapsed = round((time.monotonic() - started) * 1000)
            return RawSearch(_last_lines(lines, request.multipv), stopped, elapsed)

    def close(self) -> None:
        if self._process.poll() is None:
            try:
                self._send("quit")
                self._process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired, EngineError):
                self._kill()
        for stream in (self._process.stdin, self._process.stdout):
            if stream is not None:
                stream.close()

    def _kill(self) -> None:
        """After a timeout the process is not trusted again: later searches raise."""

        if self._process.poll() is None:
            self._process.kill()
            self._process.wait()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- helpers --------------------------------------------------------------------------------

    def _handshake(self, executable: str) -> EngineIdentity:
        self._send("uci")
        lines, done = self._until("uciok", READY_TIMEOUT_S)
        if not done:
            raise EngineError("no uciok")
        name = author = ""
        options: list[EngineOption] = []
        for line in lines:
            if line.startswith("id name "):
                name = line[len("id name ") :].strip()
            elif line.startswith("id author "):
                author = line[len("id author ") :].strip()
            elif line.startswith("option name "):
                options.append(_option(line))
        if name != SUPPORTED_ENGINE:
            raise EngineUnsupportedError(f"engine {name!r} is not {SUPPORTED_ENGINE!r}")
        return EngineIdentity(name, author, _sha256(executable), tuple(options))

    def _send_options(self, options) -> None:
        for option, value in options:
            self._send(f"setoption name {option} value {value}")

    def _ready(self) -> None:
        self._send("isready")
        lines, done = self._until("readyok", READY_TIMEOUT_S)
        if not done:
            self._kill()
            raise EngineError("no readyok")
        errors = [line for line in lines if line.startswith("info string") and "ERROR" in line]
        if errors:
            raise EngineError(f"engine reported: {errors[0]}")

    def _send(self, command: str) -> None:
        if self._process.poll() is not None or self._process.stdin is None:
            raise EngineError("engine process is not running")
        try:
            self._process.stdin.write(command + "\n")
            self._process.stdin.flush()
        except OSError as error:
            raise EngineError(f"engine write failed: {error}") from None

    def _read(self) -> None:
        assert self._process.stdout is not None
        try:
            for line in self._process.stdout:
                self._lines.put(line.rstrip("\n"))
        except (OSError, ValueError):
            pass
        finally:
            self._lines.put(_EOF)

    def _until(self, prefix: str, timeout_s: float) -> tuple[list[str], bool]:
        out: list[str] = []
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return out, False
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty:
                return out, False
            if line is _EOF:
                raise EngineError("engine process exited")
            assert isinstance(line, str)
            out.append(line)
            if line.startswith(prefix):
                return out, True


def _option(line: str) -> EngineOption:
    tokens = line.split()
    type_at = tokens.index("type")
    name = " ".join(tokens[2:type_at])
    kind = tokens[type_at + 1]
    default: str | None = None
    if "default" in tokens:
        start = tokens.index("default") + 1
        end = next(
            (i for i in range(start, len(tokens)) if tokens[i] in ("min", "max", "var")),
            len(tokens),
        )
        default = " ".join(tokens[start:end])
    return EngineOption(name, kind, default)


def _sha256(executable: str) -> str:
    digest = hashlib.sha256()
    with open(os.path.realpath(executable), "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _last_lines(lines: list[str], multipv: int) -> tuple[RawLine, ...]:
    """The last scored `info` line of every rank; refuses gaps and excess ranks (F4-D §3.3)."""

    last: dict[int, RawLine] = {}
    for line in lines:
        if not line.startswith("info ") or line.startswith("info string"):
            continue
        tokens = line.split()
        if "score" not in tokens and "pv" not in tokens:
            continue  # progress lines (`currmove`, `depth` alone)
        parsed = _info(line)
        last[parsed.multipv] = parsed
    ranks = sorted(last)
    if ranks != list(range(1, len(ranks) + 1)):
        raise EngineOutputError(f"rank gap in engine output: {ranks}")
    if len(ranks) > multipv:
        raise EngineOutputError(f"{len(ranks)} ranks exceed MultiPV {multipv}")
    return tuple(last[r] for r in ranks)


def _info(line: str) -> RawLine:
    tokens = line.split()[1:]
    values: dict[str, object] = {}
    bound = Bound.EXACT
    i = 0
    try:
        while i < len(tokens):
            key = tokens[i]
            if key == "pv":
                values["pv"] = tuple(tokens[i + 1 :])
                break
            if key == "score":
                if "score" in values:
                    raise ValueError("repeated score")
                values["score"] = (tokens[i + 1], int(tokens[i + 2]))
                i += 3
                if i < len(tokens) and tokens[i] in ("lowerbound", "upperbound"):
                    bound = Bound.LOWER if tokens[i] == "lowerbound" else Bound.UPPER
                    i += 1
                continue
            if key == "wdl":
                values["wdl"] = (int(tokens[i + 1]), int(tokens[i + 2]), int(tokens[i + 3]))
                i += 4
                continue
            if key not in _INFO_KEYS or key in ("string", "currmove", "refutation", "currline"):
                raise ValueError(f"unexpected info field {key!r}")
            if key in values:
                raise ValueError(f"repeated info field {key!r}")
            values[key] = int(tokens[i + 1])
            i += 2
        pv = values.get("pv")
        if not pv:
            raise ValueError("scored line without pv")
        if "score" not in values:
            raise ValueError("pv line without score")
        missing = [
            k for k in ("multipv", "depth", "seldepth", "nodes", "tbhits") if k not in values
        ]
        if missing:
            # never invented: A0 §1 "undefined is never zero" (F4a-C7)
            raise ValueError(f"missing fields {missing}")
        return RawLine(
            multipv=int(values["multipv"]),  # type: ignore[arg-type]
            depth=int(values["depth"]),  # type: ignore[arg-type]
            seldepth=int(values["seldepth"]),  # type: ignore[arg-type]
            score=values["score"],  # type: ignore[arg-type]
            bound=bound,
            wdl=values.get("wdl"),  # type: ignore[arg-type]
            nodes=int(values["nodes"]),  # type: ignore[arg-type]
            tbhits=int(values["tbhits"]),  # type: ignore[arg-type]
            pv=pv,  # type: ignore[arg-type]
        )
    except (IndexError, KeyError, ValueError) as error:
        raise EngineOutputError(f"cannot read engine line {line!r}: {error}") from None
