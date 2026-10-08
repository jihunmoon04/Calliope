"""Explicit opt-in observations around the unchanged schema-0.2 move analysis.

Order is fixed: shape preflight and full sequential legality of every supplied line through the
same chess rules port (zero engine work), then the legacy use case to completion, then purely
observational scenario work outside any engine request session. Any failure is atomic: no
partial schema-0.3 result is returned, and nothing here can become a P10 claim.
"""

from __future__ import annotations

from dataclasses import dataclass

from calliope.application.ports.chess import ChessRulesPort
from calliope.contracts import (
    OBSERVATION_SCHEMA_VERSION,
    PUBLIC_SCHEMA_VERSION,
    AnalyzeMoveRequest,
    MoveAnalysisResult,
    ObservationSectionView,
    ObservationSentenceView,
    ObservationSourceView,
    ObservedMoveAnalysisResult,
    ObservedMoveRequest,
    SuppliedExchangeObservationRequest,
)
from calliope.domain.analysis.bad_move import BasePieceRef
from calliope.domain.analysis.scenario import (
    COMPACT_SENTENCE_CAP,
    ActivitySource,
    Bucket,
    CaptureKey,
    CaptureSource,
    CompactObservation,
    CountKey,
    ExchangeObservationInput,
    FileKey,
    FileSource,
    HistorySource,
    LineOrigin,
    MaterialSource,
    PawnSource,
    PinKey,
    PinSource,
    PlayedMoveTarget,
    RayKey,
    RaySource,
    ScenarioKind,
    ScenarioRequest,
    SquareKey,
    SquareSource,
    SquareTarget,
    StepKey,
    SubjectKey,
    TransitionKey,
    TransitionSource,
    is_canonical_uci,
    is_square,
)
from calliope.engine import MoveAnalysisUseCase
from calliope.errors import InvalidScenarioRequestError, ObservationProjectionError
from calliope.services.position.scenario import ScenarioLineAnalyzer
from calliope.services.position.scenario_observation import compact_observations

MAX_EXCHANGE_LINES = 2
MAX_EXCHANGE_PLIES = 8
PLAYED_LABEL = "Observed facts after the played move"
EXCHANGE_LABEL = "Facts in the supplied line"
PLAYED_SCOPE = "played_transition"
EXCHANGE_SCOPE = "supplied_line_exchange"


@dataclass(slots=True)
class ObservedMoveService:
    legacy: MoveAnalysisUseCase
    chess: ChessRulesPort
    scenarios: ScenarioLineAnalyzer

    def execute(self, request: ObservedMoveRequest) -> ObservedMoveAnalysisResult:
        _preflight_shape(request)
        initial = self.chess.position_from_fen(request.base.fen)
        played = self.chess.legal_move_from_uci(initial, request.base.move_uci)
        lines = tuple(self._legal_line(initial, line) for line in request.exchange_lines)

        base_result = self.legacy.execute(request.base)

        # Strictly after the legacy request session has closed; no engine port is reachable here.
        _check_legacy_anchor(base_result, initial.position_id, played.uci)
        played_section = None
        if request.include_played:
            scenario = ScenarioRequest(
                ScenarioKind.PLAYED_TRANSITION, PlayedMoveTarget(played), initial, (played,), 1
            )
            observations = compact_observations(self.scenarios.analyze(scenario))
            played_section = ObservationSectionView(
                PLAYED_LABEL,
                PLAYED_SCOPE,
                (played.uci,),
                None,
                None,
                None,
                _sentences("p", observations),
            )
        exchange_sections = []
        for index, (line, moves) in enumerate(zip(request.exchange_lines, lines, strict=True)):
            wrapped = ExchangeObservationInput(
                ScenarioRequest(
                    ScenarioKind.EXCHANGE,
                    SquareTarget(line.focus_square),
                    initial,
                    moves,
                    MAX_EXCHANGE_PLIES,
                ),
                LineOrigin.USER,
            )
            summary = self.scenarios.analyze(wrapped.scenario)
            observations = compact_observations(summary)
            exchange_sections.append(
                ObservationSectionView(
                    EXCHANGE_LABEL,
                    EXCHANGE_SCOPE,
                    tuple(m.uci for m in moves),
                    line.focus_square,
                    summary.detail.status.value,
                    len(summary.detail.focus_capture_events),
                    _sentences(f"x{index}", observations),
                )
            )
        result = ObservedMoveAnalysisResult(
            OBSERVATION_SCHEMA_VERSION, base_result, played_section, tuple(exchange_sections)
        )
        _check_result(result)
        return result

    def _legal_line(self, initial, line: SuppliedExchangeObservationRequest):
        """Sequential legality through the same rules port; canonical aliases are refused."""
        current, moves = initial, []
        for uci in line.moves_uci:
            move = self.chess.legal_move_from_uci(current, uci)
            if move.uci != uci:
                raise InvalidScenarioRequestError(f"supplied move {uci!r} is not canonical UCI")
            moves.append(move)
            current = self.chess.apply_move(current, move)
        return tuple(moves)


def _preflight_shape(request: ObservedMoveRequest) -> None:
    """Exact types, budgets, canonical UCI shape and duplicates; no rules or engine work."""
    if type(request) is not ObservedMoveRequest or type(request.base) is not AnalyzeMoveRequest:
        raise InvalidScenarioRequestError("expected ObservedMoveRequest over AnalyzeMoveRequest")
    if type(request.include_played) is not bool:
        raise InvalidScenarioRequestError("include_played must be a bool")
    lines = request.exchange_lines
    if type(lines) is not tuple or len(lines) > MAX_EXCHANGE_LINES:
        raise InvalidScenarioRequestError("exchange_lines must be a tuple of at most two lines")
    if not request.include_played and not lines:
        raise InvalidScenarioRequestError("an observation request must ask for a section")
    seen = set()
    for line in lines:
        if (
            type(line) is not SuppliedExchangeObservationRequest
            or not is_square(line.focus_square)
            or type(line.moves_uci) is not tuple
            or len(line.moves_uci) > MAX_EXCHANGE_PLIES
            or not all(is_canonical_uci(m) for m in line.moves_uci)
        ):
            raise InvalidScenarioRequestError("invalid supplied exchange line")
        identity = (line.focus_square, line.moves_uci)
        if identity in seen:
            raise InvalidScenarioRequestError("duplicate supplied exchange line")
        seen.add(identity)


def _check_legacy_anchor(result: MoveAnalysisResult, position_id: str, move_uci: str) -> None:
    if not (
        type(result) is MoveAnalysisResult
        and result.schema_version == PUBLIC_SCHEMA_VERSION
        and result.metadata.get("position_id") == position_id
        and result.judgement.move_uci == move_uci
    ):
        raise ObservationProjectionError("legacy result is anchored to another position or move")


def _check_result(result: ObservedMoveAnalysisResult) -> None:
    sections = (*((result.played,) if result.played else ()), *result.exchange_lines)
    ids = [s.observation_id for section in sections for s in section.sentences]
    if (
        any(len(section.sentences) > COMPACT_SENTENCE_CAP for section in sections)
        or len(ids) > COMPACT_SENTENCE_CAP * (1 + MAX_EXCHANGE_LINES)
        or len(set(ids)) != len(ids)
    ):
        raise ObservationProjectionError("observation sections exceed caps or repeat identifiers")


# ---- closed public identifier and source grammar ---------------------------------------------


def _triple(base: BasePieceRef) -> tuple[str, str, str]:
    if type(base) is not BasePieceRef:
        raise ObservationProjectionError("physical identity is not a BasePieceRef")
    return base.color.value, base.piece_type.value, base.base_square


def _property_key(key) -> str:
    if type(key) is SubjectKey:
        return "base=" + ",".join(_triple(key.subject))
    if type(key) is SquareKey:
        return f"square={key.square}"
    if type(key) is FileKey:
        return f"file={key.file}"
    if type(key) is RayKey:
        df, dr = key.direction
        return "base=" + ",".join(_triple(key.subject)) + f";dir={df},{dr}"
    if type(key) is PinKey:
        return ";".join(
            f"{role}=" + ",".join(_triple(base))
            for role, base in (("pinner", key.pinner), ("pinned", key.pinned), ("king", key.king))
        )
    raise ObservationProjectionError(f"unknown property key {type(key).__name__}")


def observation_id(section: str, bucket: Bucket, key) -> str:
    """``obs.v1/{section}/{bucket}/{family}/{key}``, recomputed from the typed key only."""
    if type(key) is StepKey:
        family, encoded = key.property.family.value, f"ply={key.ply};{_property_key(key.property)}"
    elif type(key) is CaptureKey:
        family, encoded = key.family.value, f"ply={key.ply}"
    elif type(key) is TransitionKey:
        family, encoded = key.family.value, f"ply={key.ply};base=" + ",".join(_triple(key.subject))
    elif type(key) is CountKey:
        family = key.family.value
        encoded = f"color={key.color.value};piece={key.piece_type.value}"
    elif bucket is Bucket.ENDPOINTS:
        family, encoded = key.family.value, _property_key(key)
    else:
        raise ObservationProjectionError(f"unprojectable {bucket.value} key")
    if bucket not in (Bucket.STEPS, Bucket.ENDPOINTS, Bucket.EVENTS, Bucket.AGGREGATES):
        raise ObservationProjectionError("snapshot observations are never displayed")
    return f"obs.v1/{section}/{bucket.value}/{family}/{encoded}"


def source_view(ref) -> ObservationSourceView:
    """Exact class dispatch over the ten internal SourceRef variants; anything else fails."""
    kind = type(ref)
    if kind is CaptureSource:
        return _view(ref, "step", ref.ply, (ref.before_position_id, ref.after_position_id), ())
    if kind is TransitionSource:
        selectors = (*_triple(ref.subject), ref.transition_kind.value)
        return _view(
            ref, "step", ref.ply, (ref.before_position_id, ref.after_position_id), selectors
        )
    if kind is MaterialSource:
        selectors = (ref.color.value, ref.piece_type.value)
        ids = (ref.initial_position_id, ref.final_position_id)
        return _view(ref, "endpoints", None, ids, selectors)
    if kind in (HistorySource, PawnSource, ActivitySource):
        return _frame_view(ref, _triple(ref.subject))
    if kind is SquareSource:
        return _frame_view(ref, (ref.square,))
    if kind is FileSource:
        return _frame_view(ref, (ref.file,))
    if kind is RaySource:
        df, dr = ref.direction
        return _frame_view(ref, (*_triple(ref.subject), str(df), str(dr)))
    if kind is PinSource:
        return _frame_view(ref, (*_triple(ref.pinner), *_triple(ref.pinned), *_triple(ref.king)))
    raise ObservationProjectionError(f"unknown source reference {kind.__name__}")


def _frame_view(ref, selectors) -> ObservationSourceView:
    return _view(ref, "frame", ref.frame_index, (ref.position_id,), selectors)


def _view(ref, anchor, index, position_ids, selectors) -> ObservationSourceView:
    if index is not None and type(index) is not int:
        raise ObservationProjectionError("source index must be an int")
    return ObservationSourceView(
        ref.kind.value, anchor, index, tuple(position_ids), tuple(selectors)
    )


def _sentences(section: str, observations) -> tuple[ObservationSentenceView, ...]:
    views = []
    for observation in observations:
        if type(observation) is not CompactObservation:
            raise ObservationProjectionError("expected validated compact observations")
        sentence = observation.sentence
        views.append(
            ObservationSentenceView(
                observation_id(section, observation.bucket, observation.key),
                sentence.template_id.value,
                sentence.text,
                tuple(source_view(ref) for ref in sentence.source_refs),
            )
        )
    return tuple(views)
