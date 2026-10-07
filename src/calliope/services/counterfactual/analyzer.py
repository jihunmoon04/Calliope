"""Execute bounded, explicitly specified hypothetical chess experiments.

Two phases: a complete preflight (no engine access) and a serial execution.  Nothing here
selects moves, verifies tactics, or infers causes.
"""

from __future__ import annotations

from dataclasses import dataclass

from calliope.application.ports.chess import ChessRulesPort
from calliope.application.ports.engine import EngineAnalysisPort
from calliope.application.ports.position import PositionObservationPort
from calliope.application.ports.tactics import TacticalObservationPort
from calliope.domain.analysis import (
    CounterfactualBatchRequest,
    CounterfactualBatchResult,
    CounterfactualProbe,
    ProbeKind,
    ProbeResult,
    TerminalKind,
    TerminalOutcome,
)
from calliope.domain.chess import ChessMove, PositionSnapshot
from calliope.domain.engine import EngineAnalysis, EngineIdentity, EngineLimit, EngineSettings
from calliope.errors import IncompatibleProbeResultError, InvalidProbeRequestError

MIN_PROBES = 1
MAX_PROBES = 4
MAX_TIME_MS = 2000

DEFAULT_SETTINGS = EngineSettings(
    limit=EngineLimit(time_ms=1000),
    multipv=1,
    threads=1,
    hash_mb=None,
)

_K = ProbeKind
# (intervention required, execution required)
_SHAPES = {
    _K.BEST_RESPONSE: (False, False),
    _K.ALTERNATIVE_MOVE: (True, False),
    _K.REFUTATION: (True, False),
    _K.IGNORE_THREAT: (True, True),
}


@dataclass(frozen=True, slots=True)
class _Prepared:
    probe: CounterfactualProbe
    analysis_position: PositionSnapshot
    intervention_position: PositionSnapshot | None
    root_moves: tuple[ChessMove, ...] | None
    terminal: TerminalOutcome | None
    identity: tuple[str, str, str | None, str | None]


def _validate_settings(settings: EngineSettings) -> None:
    time_ms = settings.limit.time_ms
    if time_ms is None:
        raise InvalidProbeRequestError("time_ms is required for counterfactual probes")
    if not 1 <= time_ms <= MAX_TIME_MS:
        raise InvalidProbeRequestError(f"time_ms must be within 1..{MAX_TIME_MS}")
    if settings.multipv != 1:
        raise InvalidProbeRequestError("multipv must be 1")
    if settings.threads != 1:
        raise InvalidProbeRequestError("threads must be 1")


def _validate_shape(probe: CounterfactualProbe) -> None:
    if not isinstance(probe.kind, ProbeKind):
        raise InvalidProbeRequestError("unsupported probe kind")
    need_intervention, need_execution = _SHAPES[probe.kind]
    if need_intervention != (probe.intervention_move is not None):
        raise InvalidProbeRequestError(
            f"{probe.kind.value}: intervention_move is "
            f"{'required' if need_intervention else 'not allowed'}"
        )
    if need_execution != (probe.execution_move is not None):
        raise InvalidProbeRequestError(
            f"{probe.kind.value}: execution_move is "
            f"{'required' if need_execution else 'not allowed'}"
        )


@dataclass(slots=True)
class CounterfactualAnalyzer:
    chess: ChessRulesPort
    engine: EngineAnalysisPort
    tactical_rules: TacticalObservationPort
    position_rules: PositionObservationPort

    def execute(self, request: CounterfactualBatchRequest) -> CounterfactualBatchResult:
        prepared = self._preflight(request)

        results: list[ProbeResult] = []
        identity: EngineIdentity | None = None
        for item in prepared:
            if item.terminal is not None:
                results.append(
                    ProbeResult(
                        probe=item.probe,
                        analysis_position=item.analysis_position,
                        intervention_position=item.intervention_position,
                        root_moves=None,
                        engine_analysis=None,
                        terminal=item.terminal,
                    )
                )
                continue
            analysis = self.engine.analyze(
                item.analysis_position, request.settings, item.root_moves
            )
            self._check_analysis(analysis, item, request.settings)
            if identity is None:
                identity = analysis.engine
            elif analysis.engine != identity:
                raise IncompatibleProbeResultError("engine identity differs within one batch")
            results.append(
                ProbeResult(
                    probe=item.probe,
                    analysis_position=item.analysis_position,
                    intervention_position=item.intervention_position,
                    root_moves=item.root_moves,
                    engine_analysis=analysis,
                    terminal=None,
                )
            )
        return CounterfactualBatchResult(settings=request.settings, results=tuple(results))

    # ---- Phase A -------------------------------------------------------------------

    def _preflight(self, request: CounterfactualBatchRequest) -> list[_Prepared]:
        if not MIN_PROBES <= len(request.probes) <= MAX_PROBES:
            raise InvalidProbeRequestError(f"batch must contain {MIN_PROBES}..{MAX_PROBES} probes")
        _validate_settings(request.settings)
        for probe in request.probes:
            _validate_shape(probe)
        prepared = [self._prepare(probe) for probe in request.probes]
        # Identity uses canonical UCI from the rules port, ignoring SAN and whitespace.
        if len({item.identity for item in prepared}) != len(prepared):
            raise InvalidProbeRequestError("duplicate probe in batch")
        return prepared

    def _prepare(self, probe: CounterfactualProbe) -> _Prepared:
        base = probe.base
        kind = probe.kind

        if kind is _K.BEST_RESPONSE:
            return self._prepared(probe, base, None, None, None, None)

        if kind is _K.ALTERNATIVE_MOVE:
            if self._terminal(base) is not None:
                raise InvalidProbeRequestError("alternative_move requires a non-terminal base")
            forced = self._legal(base, probe.intervention_move)
            return self._prepared(probe, base, None, (forced,), forced, None)

        intervention = self._legal(base, probe.intervention_move)
        after = self.chess.apply_move(base, intervention)

        if kind is _K.REFUTATION:
            return self._prepared(probe, after, after, None, intervention, None)

        if self._terminal(after) is not None:
            raise InvalidProbeRequestError("ignore_threat requires a non-terminal position")
        execution = self._legal(after, probe.execution_move)
        return self._prepared(probe, after, after, (execution,), intervention, execution)

    def _prepared(
        self,
        probe: CounterfactualProbe,
        analysis_position: PositionSnapshot,
        intervention_position: PositionSnapshot | None,
        root_moves: tuple[ChessMove, ...] | None,
        intervention: ChessMove | None,
        execution: ChessMove | None,
    ) -> _Prepared:
        terminal = self._terminal(analysis_position)
        return _Prepared(
            probe=probe,
            analysis_position=analysis_position,
            intervention_position=intervention_position,
            root_moves=None if terminal is not None else root_moves,
            terminal=terminal,
            identity=(
                probe.kind.value,
                probe.base.position_id,
                intervention.uci if intervention else None,
                execution.uci if execution else None,
            ),
        )

    def _legal(self, position: PositionSnapshot, move: ChessMove | None) -> ChessMove:
        assert move is not None
        return self.chess.legal_move_from_uci(position, move.uci)

    def _terminal(self, position: PositionSnapshot) -> TerminalOutcome | None:
        tactical = self.tactical_rules.observe_tactics(position)
        observed = self.position_rules.observe_position(position)
        if tactical.position_id != position.position_id:
            raise IncompatibleProbeResultError("tactical observation belongs to another position")
        if observed.position_id != position.position_id:
            raise IncompatibleProbeResultError("position observation belongs to another position")
        if tactical.side_to_move is not position.side_to_move:
            raise IncompatibleProbeResultError("observed side to move contradicts the position")

        no_moves = len(tactical.legal_moves) == 0
        in_check = observed.side_to_move_in_check
        if observed.side_to_move_checkmated != (no_moves and in_check):
            raise IncompatibleProbeResultError("checkmate observation contradicts legal moves")
        if not no_moves:
            return None
        if in_check:
            return TerminalOutcome(TerminalKind.CHECKMATE, position.side_to_move.opposite)
        return TerminalOutcome(TerminalKind.STALEMATE, None)

    # ---- Phase B integrity ---------------------------------------------------------

    @staticmethod
    def _check_analysis(
        analysis: EngineAnalysis, item: _Prepared, settings: EngineSettings
    ) -> None:
        if analysis.position_id != item.analysis_position.position_id:
            raise IncompatibleProbeResultError("engine analysis belongs to another position")
        if analysis.settings != settings:
            raise IncompatibleProbeResultError("engine analysis used different settings")
        if len(analysis.lines) != 1:
            raise IncompatibleProbeResultError("engine analysis must contain exactly one line")
        line = analysis.best_line
        if line.rank != 1:
            raise IncompatibleProbeResultError("engine line must have rank 1")
        if item.root_moves is not None and line.first_move.uci != item.root_moves[0].uci:
            raise IncompatibleProbeResultError("engine line does not start with the forced root")
