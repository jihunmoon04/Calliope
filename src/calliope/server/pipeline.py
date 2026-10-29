"""The game pipeline (AS-D §3): PGN intake, normalization, per-ply requests, the analysis loop.

`tools/explain_game` and the server share it. `parse_game` is AR-D G8's caller: it parses the
PGN and normalizes the whole game with python-chess. `analyse_game` runs the plies in order,
takes each from the ply cache or analyses it, and builds the `calliope_result_v1` document from
the plies as they were loaded from the cache files (one path, AS-D §3).
"""

from __future__ import annotations

import io
import logging
import re
import threading
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

import chess.pgn

from calliope.facts import (
    EngineError,
    EngineOutputError,
    EngineProfile,
    EngineResultStore,
    EngineUnsupportedError,
    FactEngine,
    InvalidRequestError,
    OpenRequest,
    PositionRecords,
    RootSpec,
)
from calliope.reasoning import (
    SHIPPED,
    AnalysisFailed,
    AnalysisRequest,
    CurveSource,
    GradingSpec,
    Reasoner,
    build_digest,
    chesscom_time_class,
    explain,
    resolve,
    time_class,
)
from calliope.results import EngineRun, GameInput, GameMove, PlyInput, game_result
from calliope.server.cache import PlyCache, StoreFailed

FALLBACK = (
    "graded with the default curve (logistic10, scale {scale}): "
    "the PGN gives no ratings and time class to choose one"
)
SEVERAL_GAMES = "only the first game of the text is analysed"
MAX_STORE_SEARCHES = 20_000  # the process's result store (PF-D §2)
MAX_POSITION_RECORDS = 40_000  # the process's POSITION records, ≈ 7 KB each (PF-D §3, PF1)
LOOKAHEAD = 3  # listed plies the prefetch may run ahead of the analysis (PF-D §4.2)
STANDARD_VARIANTS = ("standard", "chess", "normal", "from position")


class InputError(ValueError):
    """The PGN or the ply range cannot be analysed (AS-D §6.3: HTTP 400)."""


class JobFailed(Exception):
    """A ply could not be analysed or stored; the job fails with this message (AS-D §5.2)."""


@dataclass(frozen=True, slots=True)
class ParsedGame:
    game: GameInput
    sans: tuple[str, ...]
    uci: tuple[str, ...]
    root: RootSpec
    spec: GradingSpec
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlyProgress:
    ply: int
    san: str
    cached: bool
    seconds: float  # 0 for a cache hit


def _elo(value: str | None) -> int | None:
    return int(value) if value and re.fullmatch(r"\d+", value) else None


def grading_for(headers) -> GradingSpec:
    """Ratings and time class from the headers; the default curve when either is missing."""

    white, black = _elo(headers.get("WhiteElo")), _elo(headers.get("BlackElo"))
    control = headers.get("TimeControl", "-")
    chesscom = "chess.com" in headers.get("Site", "").lower()
    kind = (
        chesscom_time_class(control)
        if chesscom
        else (time_class(control) if "+" in control else None)
    )
    if white is None or black is None or kind is None:
        return GradingSpec()
    return GradingSpec(
        white_rating=white,
        black_rating=black,
        rating_pool="chesscom" if chesscom else "lichess",
        time_class=kind,
    )


HEADERS = {
    "White": "white",
    "Black": "black",
    "WhiteElo": "white_rating",
    "BlackElo": "black_rating",
    "TimeControl": "time_control",
    "Site": "site",
    "Date": "date",
    "Result": "result",
}


def game_input(game, sans) -> GameInput:
    """The whole game, normalized with python-chess (AR-D §5, G8): FENs as `board.fen()`."""

    board = game.board()
    start, moves = board.fen(), []
    for move, san in zip(game.mainline_moves(), sans, strict=True):
        before = board.fen()
        board.push(move)
        moves.append(GameMove(san, move.uci(), before, board.fen()))
    headers: dict[str, str | int] = {}
    for tag, key in HEADERS.items():
        value = game.headers.get(tag)
        if key.endswith("_rating"):
            value = _elo(value)
        elif value in ("", "?") or (value and set(value) <= set("?.")):
            value = None  # PGN's "unknown"
        if value is not None:
            headers[key] = value
    return GameInput(start, tuple(moves), headers)


def parse_game(pgn_text: str) -> ParsedGame:
    """The first game of the text, normalized; `InputError` when it cannot be read."""

    stream = io.StringIO(pgn_text)
    logging.getLogger("chess.pgn").disabled = True  # errors are read from `game.errors`
    game = chess.pgn.read_game(stream)
    if game is None:
        raise InputError("no game in the PGN")
    if game.errors:
        raise InputError(f"the PGN cannot be read: {game.errors[0]}")
    variant = game.headers.get("Variant", "Standard").lower()
    if variant not in STANDARD_VARIANTS or game.headers.is_chess960():
        raise InputError(f"only standard chess is supported, not {game.headers['Variant']!r}")
    board = game.board()
    sans, uci = [], []
    for move in game.mainline_moves():
        sans.append(board.san(move))
        uci.append(move.uci())
        board.push(move)
    spec = grading_for(game.headers)
    warnings = []
    curve = resolve(spec, SHIPPED).curve
    if curve is not None and curve.source == CurveSource.DEFAULT:  # AR-D §2's `fallback`
        warnings.append(FALLBACK.format(scale=curve.scale))
    if chess.pgn.read_game(stream) is not None:
        warnings.append(SEVERAL_GAMES)
    root = RootSpec(fen=game.headers["FEN"]) if "FEN" in game.headers else RootSpec()
    return ParsedGame(game_input(game, sans), tuple(sans), tuple(uci), root, spec, tuple(warnings))


def plies_range(text: str | None, count: int) -> range:
    """`17` or `1-40`; the last ply is clamped to the game (the tool's rule). May be empty."""

    if not text:
        return range(1, count + 1)
    if not re.fullmatch(r"\s*\d+\s*(-\s*\d*\s*)?", text):
        raise InputError(f"a ply range is a ply or two plies joined by '-', not {text!r}")
    first, _, last = text.partition("-")
    first_ply = int(first)
    last_ply = int(last) if last.strip() else first_ply
    return range(first_ply, min(last_ply, count) + 1)


def ply_request(parsed: ParsedGame, ply: int, profile: EngineProfile) -> AnalysisRequest:
    """The request the tool has always sent: the whole game's SANs, this ply as the target."""

    return AnalysisRequest(parsed.root, parsed.sans, ply, profile, grading=parsed.spec)


def normalized_ply(parsed: ParsedGame, ply: int, profile: EngineProfile) -> AnalysisRequest:
    """The request as the analysis will record it (AS-D S4, §3): the root as `normalize_open`
    resolves it, the moves up to the target as canonical UCI."""

    root = FactEngine().normalize_open(OpenRequest(root=parsed.root)).root
    return replace(ply_request(parsed, ply, profile), root=root, moves=parsed.uci[:ply])


def is_engine_failure(error: BaseException | None) -> bool:
    """An `EngineError` about the process (failed, exited, timed out), not about its answer or
    its identity (AS-D §5.2, review B3)."""

    return isinstance(error, EngineError) and not isinstance(
        error, EngineOutputError | EngineUnsupportedError
    )


ENGINE_REFUSAL = f"REFUSED({EngineError.__name__})"


def refused_by_engine_failure(analysis) -> bool:
    """A later round recorded a request refused because the engine process failed."""

    return any(o.outcome == ENGINE_REFUSAL for r in analysis.rounds for o in r.requests)


class EngineSlot:
    """The worker's engine: started on demand, restarted after an engine failure."""

    def __init__(self, start: Callable[[], object]) -> None:
        self._start = start
        self._port = None

    @property
    def port(self):
        if self._port is None:
            self._port = self._start()
        return self._port

    @property
    def current(self):
        """The running port, or None: never starts one (AG6b: a reader's check)."""

        return self._port

    def restart(self):
        self.close()
        return self.port

    def close(self) -> None:
        port, self._port = self._port, None
        if port is not None:
            try:
                port.close()
            except Exception:  # a dead process may fail to close; it is replaced anyway
                logging.getLogger(__name__).warning("engine close failed", exc_info=True)


def build_of(port) -> str:
    """The digest of the reasoner build that analyses with this engine (AR-D §5)."""

    return build_digest(Reasoner(FactEngine(engine=port)).build())


def fingerprint(port) -> list[str]:
    """The engine's identity as a job's environment records it (AS-D §5.1)."""

    return list(port.identity.fingerprint())


def analyse_ply(
    slot: EngineSlot,
    parsed: ParsedGame,
    ply: int,
    profile: EngineProfile,
    engine: list[str],
    *,
    store: EngineResultStore | None = None,
    memo: PositionRecords | None = None,
):
    """One ply analysed and rendered: the per-ply path of the server and the tool (AS-D S3, §15).

    `store` and `memo` are the process's result store and POSITION records (PF-D §2, §3); without
    them the ply has a fresh store and computes every record. `engine` is the fingerprint the work
    is bound to. Before each attempt the slot's engine must still have it. An engine failure
    (round 0's `AnalysisFailed` cause, or a later round's `REFUSED(EngineError)`) restarts the
    engine and runs the ply once more (AS-D §5.2)."""

    for attempt in (1, 2):
        port = slot.port
        if fingerprint(port) != list(engine):
            raise JobFailed("the engine is not the one this work was posted for")
        try:
            facts = FactEngine(engine=port, store=store, position_records=memo)
            analysis = Reasoner(facts).analyse(ply_request(parsed, ply, profile))
        except AnalysisFailed as error:
            if not is_engine_failure(error.cause):
                raise JobFailed(f"ply {ply}: {error}") from error
            failure = str(error)
        else:
            if not refused_by_engine_failure(analysis):
                return analysis, explain(analysis)
            failure = "a later round's search was refused: the engine process failed"
        if attempt == 2:
            raise JobFailed(f"ply {ply}: the engine failed twice: {failure}")
        logging.getLogger(__name__).warning("ply %d: engine failure, restarting: %s", ply, failure)
        slot.restart()
    raise AssertionError("unreachable")


class Prefetch:
    """The played positions of a job's plies surveyed ahead of its analysis, on a second engine
    the process keeps (PF-D §4.2): `start` one run per job in the job's thread, tell it each ply
    the analysis reaches, `stop` it at the end. Its engine is started at most once per process
    and again only after a failure closed it; a failure never fails the job."""

    def __init__(self, ahead: EngineSlot, lookahead: int = LOOKAHEAD) -> None:
        self.ahead = ahead
        self.lookahead = lookahead
        self.counts: Counter[str] = Counter()  # outcomes of every run (`PrefetchOutcome`)
        self.windows: list[int] = []  # the plies whose windows were asked, every run

    def start(
        self,
        facts: FactEngine,
        parsed: ParsedGame,
        plies: Sequence[int],
        profile: EngineProfile,
    ) -> _PrefetchRun | None:
        """A run over `plies` (the analysis's listed plies, in order), or None: fewer than two,
        or the engine does not start. `facts` holds the process store and the main engine:
        built in the job thread, so the prefetch's thread never reads the main slot."""

        if len(plies) < 2:
            return None
        try:
            port = self.ahead.port  # in the job's thread (§4.2)
        except Exception:
            logging.getLogger(__name__).warning("prefetch: the engine did not start", exc_info=True)
            self.ahead.close()
            return None
        run = _PrefetchRun(self, facts, port, parsed, tuple(plies), profile)
        run.thread.start()
        return run

    def close(self) -> None:
        """The process's shutdown, once no run is left (PF-D §4.2)."""

        self.ahead.close()


class _PrefetchRun:
    def __init__(self, owner: Prefetch, facts, port, parsed, plies, profile) -> None:
        self.owner = owner
        self.facts = facts
        self.port = port
        self.parsed = parsed
        self.plies = plies
        self.profile = profile
        self.reached = 0  # listed plies the analysis has started on or passed
        self.stopping = False
        self.changed = threading.Condition()
        self.thread = threading.Thread(target=self._run, name="calliope-prefetch", daemon=True)

    def reach(self, ply: int) -> None:
        """The analysis starts on `ply` (cached or not): the gate opens up to `LOOKAHEAD`
        listed plies past it."""

        with self.changed:
            self.reached = sum(1 for u in self.plies if u <= ply)
            self.changed.notify_all()

    def stop(self) -> None:
        """Stop, and wait for the search under way (at most the adapter's bound, §4.1)."""

        with self.changed:
            self.stopping = True
            self.changed.notify_all()
        self.thread.join()

    def _run(self) -> None:
        asked: set[int] = set()
        try:
            for index, ply in enumerate(self.plies):
                with self.changed:
                    self.changed.wait_for(
                        lambda i=index: self.stopping or i < self.reached + self.owner.lookahead
                    )
                    if self.stopping:
                        return
                self.owner.windows.append(ply)
                for k in range(max(0, ply - 2), ply + 1):  # round 0's window (R0-D §6.1)
                    if k in asked:
                        continue
                    asked.add(k)
                    with self.changed:
                        if self.stopping:
                            return
                    root = replace(self.parsed.root, moves=self.parsed.uci[:k])
                    outcome = self.facts.prefetch_survey(root, self.profile, self.port)
                    self.owner.counts[outcome.value] += 1
        except Exception as error:  # never the job's failure (§4.2)
            logging.getLogger(__name__).warning("prefetch stopped: %s", error, exc_info=True)
            if isinstance(error, EngineError | InvalidRequestError):
                self.owner.ahead.close()  # started again by the next job that wants it


def document(
    parsed: ParsedGame, identity, profile: EngineProfile, inputs, *, detail: bool = False
) -> dict:
    """The game's `calliope_result_v1` (AR-D §5) over the analysed plies; with `detail`, each ply's
    `analysis` (DF-D §4.3)."""

    return game_result(parsed.game, EngineRun(identity, profile), inputs, analysis=detail)


def analyse_game(
    slot: EngineSlot,
    parsed: ParsedGame,
    plies: range,
    cache: PlyCache,
    *,
    profile: EngineProfile | None = None,
    engine: list[str] | None = None,
    on_ply: Callable[[PlyProgress], None] | None = None,
    detail: bool = False,
    store: EngineResultStore | None = None,
    memo: PositionRecords | None = None,
    prefetch: Prefetch | None = None,
) -> dict:
    """The game's `calliope_result_v1` document over `plies` (AS-D §3). `engine` is the engine
    fingerprint the job was posted for (AS1 review B1); without it, the slot's engine now.
    `store` and `memo` as `analyse_ply`'s; with `prefetch` (and a `store`), the plies whose files
    the cache does not hold have their played positions surveyed ahead (PF-D §4.2)."""

    profile = profile if profile is not None else EngineProfile()
    port = slot.port
    engine = list(engine) if engine is not None else fingerprint(port)
    if fingerprint(port) != engine:
        raise JobFailed("the engine is not the one this work was posted for")
    identity = port.identity  # equal fingerprints: the same name, author, binary and options
    build = Reasoner(FactEngine(engine=port)).build()
    digest = build_digest(build)
    keys = {ply: PlyCache.key(normalized_ply(parsed, ply, profile), digest, identity, profile)
            for ply in plies}  # fmt: skip
    ahead = None
    if prefetch is not None and store is not None:
        missing = [ply for ply in plies if not cache.holds(keys[ply])]  # a guess (§4.2)
        ahead = prefetch.start(FactEngine(engine=port, store=store), parsed, missing, profile)
    inputs = []
    try:
        for ply in plies:
            if ahead is not None:
                ahead.reach(ply)
            expected = normalized_ply(parsed, ply, profile)
            key = keys[ply]
            started = time.monotonic()
            loaded = cache.get(key, expected, build)
            cached = loaded is not None
            if loaded is None:
                analysis, rendered = analyse_ply(
                    slot, parsed, ply, profile, engine, store=store, memo=memo
                )
                try:
                    loaded = cache.put(key, analysis, rendered, expected, build)
                except StoreFailed as error:
                    raise JobFailed(
                        f"the stored analysis of ply {ply} failed its check: {error}"
                    ) from error
            inputs.append(PlyInput(ply, loaded.analysis, loaded.rendered, loaded.bundle))
            if on_ply is not None:
                seconds = 0.0 if cached else time.monotonic() - started
                on_ply(PlyProgress(ply, parsed.sans[ply - 1], cached, seconds))
    finally:
        if ahead is not None:
            ahead.stop()
    return document(parsed, identity, profile, inputs, detail=detail)
