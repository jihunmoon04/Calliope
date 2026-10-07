"""Synchronous Stockfish adapter normalizing raw UCI analysis into ``EngineAnalysis``."""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Mapping
from types import TracebackType
from typing import Any, Self

import chess
import chess.engine

from calliope.application.ports.engine import EngineAnalysisPort
from calliope.domain.chess import ChessMove, Color, PositionSnapshot
from calliope.domain.engine import (
    WDL,
    EngineAnalysis,
    EngineIdentity,
    EngineLine,
    EngineScore,
    EngineSettings,
    EngineStability,
    StabilityLevel,
)
from calliope.errors import (
    EngineAnalysisError,
    EngineClosedError,
    EngineConfigurationError,
    EngineStartupError,
    IllegalMoveError,
    InvalidEngineOutputError,
    InvalidFenError,
    InvalidPositionError,
    InvalidUciError,
    NullMoveNotAllowedError,
)

_ENGINE_FAILURES = (
    chess.engine.EngineError,
    chess.engine.EngineTerminatedError,
    OSError,
    TimeoutError,
)


class StockfishAdapter(EngineAnalysisPort):
    """Own one Stockfish process and serialize analyses sent to it."""

    def __init__(self, engine: chess.engine.SimpleEngine, identity: EngineIdentity) -> None:
        self._engine = engine
        self._identity = identity
        self._lock = threading.Lock()
        self._closed = False

    @classmethod
    def start(cls, command: str | list[str], *, timeout_s: float = 10.0) -> StockfishAdapter:
        try:
            engine = chess.engine.SimpleEngine.popen_uci(command, timeout=timeout_s)
        except _ENGINE_FAILURES as exc:
            raise EngineStartupError(f"could not start UCI engine: {exc}") from None

        try:
            name = str(engine.id.get("name", ""))
        except _ENGINE_FAILURES as exc:
            _quit_quietly(engine)
            raise EngineStartupError(f"could not read engine identity: {exc}") from None
        if "stockfish" not in name.lower():
            _quit_quietly(engine)
            raise EngineStartupError(f"UCI engine is not Stockfish: {name!r}")
        return cls(engine, EngineIdentity(name=name, version=None))

    def analyze(
        self,
        position: PositionSnapshot,
        settings: EngineSettings,
        root_moves: tuple[ChessMove, ...] | None = None,
    ) -> EngineAnalysis:
        with self._lock:
            if self._closed:
                raise EngineClosedError("StockfishAdapter is closed")

            board = _board_from_snapshot(position)
            if not any(board.legal_moves):
                raise EngineAnalysisError("position has no legal moves; nothing to analyze")
            native_roots = _validate_root_moves(board, root_moves)
            limit = _translate_limit(settings)

            try:
                options = self._analysis_options(settings)
                infos = self._engine.analyse(
                    board,
                    limit,
                    multipv=settings.multipv,
                    info=chess.engine.INFO_ALL,
                    root_moves=native_roots,
                    options=options,
                )
            except chess.engine.EngineError as exc:
                raise EngineAnalysisError(f"engine analysis failed: {exc}") from None
            except _ENGINE_FAILURES as exc:
                raise EngineAnalysisError(f"engine communication failed: {exc}") from None

            lines = _normalize_lines(board, infos)
            return EngineAnalysis(
                position_id=position.position_id,
                engine=self._identity,
                settings=settings,
                lines=lines,
                stability=EngineStability(
                    level=StabilityLevel.UNKNOWN,
                    samples=1,
                    best_move_switches=0,
                    max_cp_swing=None,
                ),
            )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            _quit_quietly(self._engine)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _analysis_options(self, settings: EngineSettings) -> dict[str, Any]:
        available = self._engine.options
        options: dict[str, Any] = {}
        for name, value in (("Threads", settings.threads), ("Hash", settings.hash_mb)):
            if value is None:
                continue
            option = available.get(name)
            if option is None:
                raise EngineConfigurationError(f"engine does not support option {name!r}")
            if (option.min is not None and value < option.min) or (
                option.max is not None and value > option.max
            ):
                raise EngineConfigurationError(
                    f"{name}={value} outside engine range [{option.min}, {option.max}]"
                )
            options[name] = value
        if "UCI_ShowWDL" in available:
            options["UCI_ShowWDL"] = True
        return options


def _quit_quietly(engine: chess.engine.SimpleEngine) -> None:
    with contextlib.suppress(*_ENGINE_FAILURES):
        engine.quit()
    with contextlib.suppress(*_ENGINE_FAILURES):
        engine.close()


def _board_from_snapshot(position: PositionSnapshot) -> chess.Board:
    try:
        board = chess.Board(position.fen, chess960=False)
    except ValueError:
        raise InvalidFenError("PositionSnapshot contains invalid FEN syntax") from None
    if not board.is_valid():
        raise InvalidPositionError("PositionSnapshot contains an invalid chess position")
    return board


def _translate_limit(settings: EngineSettings) -> chess.engine.Limit:
    limit = settings.limit
    return chess.engine.Limit(
        depth=limit.depth,
        nodes=limit.nodes,
        time=None if limit.time_ms is None else limit.time_ms / 1000,
    )


def _validate_root_moves(
    board: chess.Board,
    root_moves: tuple[ChessMove, ...] | None,
) -> list[chess.Move] | None:
    if root_moves is None:
        return None
    if not root_moves:
        raise EngineConfigurationError("root_moves must not be empty")
    native: list[chess.Move] = []
    for move in root_moves:
        text = move.uci.strip()
        try:
            parsed = chess.Move.from_uci(text)
        except ValueError:
            raise InvalidUciError(f"UCI syntax is invalid: {text!r}") from None
        if not parsed:
            raise NullMoveNotAllowedError("Null move '0000' is not allowed")
        if parsed not in board.legal_moves:
            raise IllegalMoveError(f"Root move {text!r} is not legal in this position")
        if parsed in native:
            raise EngineConfigurationError(f"duplicate root move {text!r}")
        native.append(parsed)
    return native


def _normalize_lines(board: chess.Board, infos: object) -> tuple[EngineLine, ...]:
    if not isinstance(infos, list) or not infos:
        raise InvalidEngineOutputError("engine returned no analysis lines")

    lines: list[EngineLine] = []
    for index, info in enumerate(infos):
        if not isinstance(info, Mapping):
            raise InvalidEngineOutputError("engine analysis line is not a mapping")
        rank = info.get("multipv", index + 1)
        if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
            raise InvalidEngineOutputError(f"invalid MultiPV rank: {rank!r}")
        pv = _normalize_pv(board, info.get("pv"))
        lines.append(
            EngineLine(
                rank=rank,
                first_move=pv[0],
                score=_normalize_score(info),
                pv=pv,
                wdl=_normalize_wdl(info.get("wdl")),
                depth=info.get("depth"),
                seldepth=info.get("seldepth"),
                nodes=info.get("nodes"),
            )
        )

    ranks = [line.rank for line in lines]
    if len(ranks) != len(set(ranks)):
        raise InvalidEngineOutputError("duplicate MultiPV rank in engine output")
    if 1 not in ranks:
        raise InvalidEngineOutputError("engine output has no rank 1 line")
    return tuple(sorted(lines, key=lambda line: line.rank))


def _normalize_pv(board: chess.Board, raw_pv: object) -> tuple[ChessMove, ...]:
    if not raw_pv:
        raise InvalidEngineOutputError("engine line has no PV")
    walker = board.copy(stack=False)
    moves: list[ChessMove] = []
    for move in raw_pv:  # type: ignore[attr-defined]
        if not isinstance(move, chess.Move) or not move:
            raise InvalidEngineOutputError("engine PV contains a null or non-move entry")
        if move not in walker.legal_moves:
            raise InvalidEngineOutputError(f"engine PV contains illegal move {move.uci()!r}")
        moves.append(ChessMove(uci=move.uci(), san=walker.san(move)))
        walker.push(move)
    return tuple(moves)


def _normalize_score(info: Mapping[str, Any]) -> EngineScore:
    if info.get("lowerbound") or info.get("upperbound"):
        raise InvalidEngineOutputError("bound-only score cannot be treated as exact")
    pov = info.get("score")
    if not isinstance(pov, chess.engine.PovScore):
        raise InvalidEngineOutputError("engine line has no score")
    white = pov.white()
    if isinstance(white, chess.engine.Cp):
        return EngineScore.cp(white.cp)
    if white is chess.engine.MateGiven:
        return EngineScore.forced_mate(Color.WHITE, 0)
    if isinstance(white, chess.engine.Mate):
        moves = white.moves
        if moves > 0:
            return EngineScore.forced_mate(Color.WHITE, moves)
        # Mate(0) is "side is checkmated"; from White POV that means Black delivered mate.
        return EngineScore.forced_mate(Color.BLACK, -moves)
    raise InvalidEngineOutputError(f"unsupported score type: {white!r}")


def _normalize_wdl(raw: object) -> WDL | None:
    if raw is None:
        return None
    if not isinstance(raw, chess.engine.PovWdl):
        raise InvalidEngineOutputError("engine WDL has unsupported type")
    white = raw.white()
    wins, draws, losses = white.wins, white.draws, white.losses
    total = wins + draws + losses
    if min(wins, draws, losses) < 0 or total <= 0:
        raise InvalidEngineOutputError("engine WDL is invalid")
    return WDL(white_win=wins / total, draw=draws / total, black_win=losses / total)
