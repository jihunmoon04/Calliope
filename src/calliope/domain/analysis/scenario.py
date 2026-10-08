"""Internal, frozen scenario vocabulary; independent of public schema 0.2."""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import StrEnum
from functools import cache
from types import UnionType
from typing import ClassVar, TypeAliasType, get_args, get_origin, get_type_hints

from calliope.domain.analysis.activity import ActivityLineAnalysis, SliderRay
from calliope.domain.analysis.bad_move import BasePieceRef
from calliope.domain.analysis.delta import CaptureDelta, PieceTransition, PieceTransitionKind
from calliope.domain.analysis.positional import FileStructure
from calliope.domain.chess import (
    ChessMove,
    Color,
    LegalCapture,
    PieceRef,
    PieceType,
    PositionSnapshot,
)
from calliope.errors import InvalidScenarioRequestError, InvalidScenarioSummaryError


class ScenarioKind(StrEnum):
    EXCHANGE = "EXCHANGE"


class Sentinel(StrEnum):
    CAPTURED = "CAPTURED"
    EMPTY = "EMPTY"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FactKind(StrEnum):
    PIECE_STATE = "PIECE_STATE"
    FOCUS_OCCUPANT = "FOCUS_OCCUPANT"
    FOCUS_ATTACKERS = "FOCUS_ATTACKERS"
    FOCUS_LEGAL_CAPTURES_NOW = "FOCUS_LEGAL_CAPTURES_NOW"
    PAWN_FLAGS = "PAWN_FLAGS"
    PAWN_SUPPORTERS = "PAWN_SUPPORTERS"
    FILE_STATE = "FILE_STATE"
    ATTACK_FOOTPRINT = "ATTACK_FOOTPRINT"
    ATTACK_PARTITION = "ATTACK_PARTITION"
    RAY_STATE = "RAY_STATE"
    PIN_PRESENT = "PIN_PRESENT"


class EventKind(StrEnum):
    CAPTURE = "CAPTURE"
    PROMOTION = "PROMOTION"
    MOVE = "MOVE"
    CASTLING_ROOK = "CASTLING_ROOK"


class CountView(StrEnum):
    MATERIAL_COUNTS = "MATERIAL_COUNTS"
    FOCUS_LOSSES = "FOCUS_LOSSES"


class SelectionReason(StrEnum):
    LINE_CONTEXT = "LINE_CONTEXT"
    FOCUS_CAPTURE = "FOCUS_CAPTURE"
    FOCUS_VICTIM_SQUARE = "FOCUS_VICTIM_SQUARE"
    FOCUS_SQUARE = "FOCUS_SQUARE"
    PARTICIPANT = "PARTICIPANT"
    FOCUS_FILE = "FOCUS_FILE"
    PARTICIPANT_FILE = "PARTICIPANT_FILE"
    PARTICIPANT_PIN = "PARTICIPANT_PIN"


class ExclusionReason(StrEnum):
    NOT_SCENARIO_RELEVANT = "NOT_SCENARIO_RELEVANT"


class ExchangeStatus(StrEnum):
    NO_FOCUS_CAPTURE = "NO_FOCUS_CAPTURE"
    FOCUS_CAPTURES_OBSERVED = "FOCUS_CAPTURES_OBSERVED"


class SourceKind(StrEnum):
    CAPTURE = "CAPTURE"
    TRANSITION = "TRANSITION"
    MATERIAL = "MATERIAL"
    PIECE_HISTORY = "PIECE_HISTORY"
    SQUARE_ACCESS = "SQUARE_ACCESS"
    PAWN_STRUCTURE = "PAWN_STRUCTURE"
    FILE_STRUCTURE = "FILE_STRUCTURE"
    PIECE_ACTIVITY = "PIECE_ACTIVITY"
    SLIDER_RAY = "SLIDER_RAY"
    ABSOLUTE_PIN = "ABSOLUTE_PIN"


class Bucket(StrEnum):
    STEPS = "steps"
    ENDPOINTS = "endpoints"
    EVENTS = "events"
    SNAPSHOTS = "snapshots"
    AGGREGATES = "aggregates"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidScenarioSummaryError(message)


def is_square(value: str) -> bool:
    return (
        type(value) is str and len(value) == 2 and value[0] in "abcdefgh" and value[1] in "12345678"
    )


@cache
def _hints(cls: type) -> dict:
    return get_type_hints(cls)


def _matches(value: object, annotation: object) -> bool:
    if isinstance(annotation, TypeAliasType):
        return _matches(value, annotation.__value__)
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is UnionType:
        return any(_matches(value, a) for a in args)
    if origin is tuple:
        if type(value) is not tuple:
            return False
        if len(args) == 2 and args[1] is Ellipsis:
            return all(_matches(v, args[0]) for v in value)
        return len(value) == len(args) and all(_matches(v, a) for v, a in zip(value, args))
    if annotation in (BasePieceRef, PieceRef) and type(value) is annotation:
        square = value.base_square if annotation is BasePieceRef else value.square
        return (
            is_square(square) and type(value.color) is Color and type(value.piece_type) is PieceType
        )
    return type(value) is annotation


class Record:
    __slots__ = ()

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            require(
                _matches(value, _hints(type(self))[field.name]),
                f"invalid {type(self).__name__}.{field.name}",
            )
            if field.name in ("frame_index", "start", "end", "frame"):
                require(value >= 0, "negative frame index")
            if field.name == "ply":
                require(value >= 1, "ply must be positive")
            if field.name.endswith("position_id"):
                require(bool(value), "empty position id")
            if field.name in ("square", "focus"):
                require(is_square(value), "invalid square")
            if field.name == "file":
                require(value in tuple("abcdefgh"), "invalid file")
            if field.name == "direction":
                require(
                    value
                    in tuple(
                        (df, dr) for df in (-1, 0, 1) for dr in (-1, 0, 1) if (df, dr) != (0, 0)
                    ),
                    "invalid ray direction",
                )
        _local(self)


@dataclass(frozen=True, slots=True)
class SquareTarget:
    square: str

    def __post_init__(self) -> None:
        if not is_square(self.square):
            raise InvalidScenarioRequestError("target must be a standard square")


@dataclass(frozen=True, slots=True)
class ScenarioRequest:
    kind: ScenarioKind
    target: SquareTarget
    initial: PositionSnapshot
    supplied_line: tuple[ChessMove, ...]
    max_plies: int = 64

    def __post_init__(self) -> None:
        if not (
            type(self.kind) is ScenarioKind
            and self.kind is ScenarioKind.EXCHANGE
            and type(self.target) is SquareTarget
            and is_square(self.target.square)
            and type(self.initial) is PositionSnapshot
            and type(self.supplied_line) is tuple
            and all(type(m) is ChessMove for m in self.supplied_line)
            and type(self.max_plies) is int
            and 1 <= self.max_plies <= 256
            and len(self.supplied_line) <= self.max_plies
        ):
            raise InvalidScenarioRequestError("invalid scenario kind, target, line or budget")


# Each source variant has exactly its selectors: there is no optional-field bag.
@dataclass(frozen=True, slots=True)
class CaptureSource(Record):
    ply: int
    before_position_id: str
    after_position_id: str
    kind: ClassVar[SourceKind] = SourceKind.CAPTURE


@dataclass(frozen=True, slots=True)
class TransitionSource(Record):
    ply: int
    before_position_id: str
    after_position_id: str
    subject: BasePieceRef
    transition_kind: PieceTransitionKind
    kind: ClassVar[SourceKind] = SourceKind.TRANSITION


@dataclass(frozen=True, slots=True)
class MaterialSource(Record):
    initial_position_id: str
    final_position_id: str
    color: Color
    piece_type: PieceType
    kind: ClassVar[SourceKind] = SourceKind.MATERIAL


@dataclass(frozen=True, slots=True)
class HistorySource(Record):
    frame_index: int
    position_id: str
    subject: BasePieceRef
    kind: ClassVar[SourceKind] = SourceKind.PIECE_HISTORY


@dataclass(frozen=True, slots=True)
class SquareSource(Record):
    frame_index: int
    position_id: str
    square: str
    kind: ClassVar[SourceKind] = SourceKind.SQUARE_ACCESS


@dataclass(frozen=True, slots=True)
class PawnSource(Record):
    frame_index: int
    position_id: str
    subject: BasePieceRef
    kind: ClassVar[SourceKind] = SourceKind.PAWN_STRUCTURE


@dataclass(frozen=True, slots=True)
class FileSource(Record):
    frame_index: int
    position_id: str
    file: str
    kind: ClassVar[SourceKind] = SourceKind.FILE_STRUCTURE


@dataclass(frozen=True, slots=True)
class ActivitySource(Record):
    frame_index: int
    position_id: str
    subject: BasePieceRef
    kind: ClassVar[SourceKind] = SourceKind.PIECE_ACTIVITY


@dataclass(frozen=True, slots=True)
class RaySource(Record):
    frame_index: int
    position_id: str
    subject: BasePieceRef
    direction: tuple[int, int]
    kind: ClassVar[SourceKind] = SourceKind.SLIDER_RAY


@dataclass(frozen=True, slots=True)
class PinSource(Record):
    frame_index: int
    position_id: str
    pinner: BasePieceRef
    pinned: BasePieceRef
    king: BasePieceRef
    kind: ClassVar[SourceKind] = SourceKind.ABSOLUTE_PIN


type SourceRef = (
    CaptureSource
    | TransitionSource
    | MaterialSource
    | HistorySource
    | SquareSource
    | PawnSource
    | FileSource
    | ActivitySource
    | RaySource
    | PinSource
)


@dataclass(frozen=True, slots=True)
class SubjectKey(Record):
    family: FactKind
    subject: BasePieceRef


@dataclass(frozen=True, slots=True)
class SquareKey(Record):
    family: FactKind
    square: str


@dataclass(frozen=True, slots=True)
class FileKey(Record):
    family: FactKind
    file: str


@dataclass(frozen=True, slots=True)
class RayKey(Record):
    family: FactKind
    subject: BasePieceRef
    direction: tuple[int, int]


@dataclass(frozen=True, slots=True)
class PinKey(Record):
    family: FactKind
    pinner: BasePieceRef
    pinned: BasePieceRef
    king: BasePieceRef


type PropertyKey = SubjectKey | SquareKey | FileKey | RayKey | PinKey


@dataclass(frozen=True, slots=True)
class StepKey(Record):
    ply: int
    property: PropertyKey


@dataclass(frozen=True, slots=True)
class SnapshotKey(Record):
    frame: int
    property: SquareKey


@dataclass(frozen=True, slots=True)
class CaptureKey(Record):
    ply: int
    family: EventKind = EventKind.CAPTURE


@dataclass(frozen=True, slots=True)
class TransitionKey(Record):
    ply: int
    family: EventKind
    subject: BasePieceRef


type EventKey = CaptureKey | TransitionKey


@dataclass(frozen=True, slots=True)
class CountKey(Record):
    family: CountView
    color: Color
    piece_type: PieceType


type CandidateKey = PropertyKey | StepKey | SnapshotKey | EventKey | CountKey


@dataclass(frozen=True, slots=True)
class PhysicalPiece(Record):
    base: BasePieceRef
    current: PieceRef


@dataclass(frozen=True, slots=True)
class Attackers(Record):
    white: tuple[PhysicalPiece, ...]
    black: tuple[PhysicalPiece, ...]


@dataclass(frozen=True, slots=True)
class LegalCaptures(Record):
    side_to_move: Color
    captures: tuple[LegalCapture, ...]


@dataclass(frozen=True, slots=True)
class PawnFlags(Record):
    isolated: bool
    doubled: bool
    passed: bool


@dataclass(frozen=True, slots=True)
class Supporters(Record):
    bases: tuple[BasePieceRef, ...]


@dataclass(frozen=True, slots=True)
class Footprint(Record):
    squares: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AttackPartition(Record):
    empty: tuple[str, ...]
    friendly: tuple[str, ...]
    enemy: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PhysicalRay(Record):
    ray: SliderRay
    source: BasePieceRef
    occupants: tuple[PhysicalPiece, ...]


type FactValue = (
    PieceRef
    | Sentinel
    | PhysicalPiece
    | Attackers
    | LegalCaptures
    | PawnFlags
    | Supporters
    | FileStructure
    | Footprint
    | AttackPartition
    | PhysicalRay
    | bool
)

VALUE_TYPES = {
    FactKind.PIECE_STATE: (PieceRef, Sentinel.CAPTURED),
    FactKind.FOCUS_OCCUPANT: (PhysicalPiece, Sentinel.EMPTY),
    FactKind.FOCUS_ATTACKERS: (Attackers,),
    FactKind.FOCUS_LEGAL_CAPTURES_NOW: (LegalCaptures,),
    FactKind.PAWN_FLAGS: (PawnFlags, Sentinel.NOT_APPLICABLE),
    FactKind.PAWN_SUPPORTERS: (Supporters, Sentinel.NOT_APPLICABLE),
    FactKind.FILE_STATE: (FileStructure,),
    FactKind.ATTACK_FOOTPRINT: (Footprint, Sentinel.NOT_APPLICABLE),
    FactKind.ATTACK_PARTITION: (AttackPartition, Sentinel.NOT_APPLICABLE),
    FactKind.RAY_STATE: (PhysicalRay, Sentinel.NOT_APPLICABLE),
    FactKind.PIN_PRESENT: (bool,),
}


@dataclass(frozen=True, slots=True)
class Fact(Record):
    key: PropertyKey
    frame: int
    value: FactValue
    source_refs: tuple[SourceRef, ...]

    def __post_init__(self) -> None:
        Record.__post_init__(self)
        require(
            any(
                type(self.value) is t if isinstance(t, type) else self.value is t
                for t in VALUE_TYPES[self.key.family]
            ),
            "value does not match fact family",
        )
        require(
            bool(self.source_refs) and len(set(self.source_refs)) == len(self.source_refs),
            "fact sources must be nonempty and unique",
        )


@dataclass(frozen=True, slots=True)
class SelectedChange(Record):
    key: PropertyKey
    before: Fact
    after: Fact
    reasons: tuple[SelectionReason, ...]


@dataclass(frozen=True, slots=True)
class ScenarioEvent(Record):
    key: EventKey
    payload: CaptureDelta | PieceTransition
    move: ChessMove
    reasons: tuple[SelectionReason, ...]
    source_refs: tuple[SourceRef, ...]


@dataclass(frozen=True, slots=True)
class HistoryRun(Record):
    start: int
    end: int
    facts: tuple[Fact, ...]


@dataclass(frozen=True, slots=True)
class FeatureHistory(Record):
    key: PropertyKey
    runs: tuple[HistoryRun, ...]
    relevant_steps: tuple[StepKey, ...]


@dataclass(frozen=True, slots=True)
class FocusSnapshot(Record):
    frame: int
    occupant: Fact
    attackers: Fact
    legal_captures: Fact


@dataclass(frozen=True, slots=True)
class ParticipantSummary(Record):
    base: BasePieceRef
    history_refs: tuple[HistorySource, ...]


@dataclass(frozen=True, slots=True)
class CountFact(Record):
    key: CountKey
    count: int
    source_refs: tuple[SourceRef, ...]


@dataclass(frozen=True, slots=True)
class ExchangeDetail(Record):
    status: ExchangeStatus
    participants: tuple[ParticipantSummary, ...]
    focus_capture_events: tuple[CaptureKey, ...]
    other_capture_events: tuple[CaptureKey, ...]
    whole_line_material_changes: tuple[CountFact, ...]
    focus_capture_losses: tuple[CountFact, ...]
    temporary_track_count: int
    definition_version: str = "exchange_rules_v1"


@dataclass(frozen=True, slots=True)
class ExcludedCandidate(Record):
    key: CandidateKey
    reason: ExclusionReason = ExclusionReason.NOT_SCENARIO_RELEVANT


@dataclass(frozen=True, slots=True)
class AccountingRow(Record):
    bucket: Bucket
    family: FactKind | EventKind | CountView
    candidate_keys: tuple[CandidateKey, ...]
    included_keys: tuple[CandidateKey, ...]
    excluded: tuple[ExcludedCandidate, ...]

    @property
    def excluded_keys(self) -> tuple[CandidateKey, ...]:
        return tuple(e.key for e in self.excluded)

    @property
    def candidate_count(self) -> int:
        return len(self.candidate_keys)

    @property
    def included_count(self) -> int:
        return len(self.included_keys)

    @property
    def excluded_count(self) -> int:
        return len(self.excluded)


@dataclass(frozen=True, slots=True)
class ScenarioSummary(Record):
    request: ScenarioRequest
    observed_line: ActivityLineAnalysis
    detail: ExchangeDetail
    events: tuple[ScenarioEvent, ...]
    focus_timeline: tuple[FocusSnapshot, ...]
    selected_changes: tuple[SelectedChange, ...]
    endpoint_changes: tuple[SelectedChange, ...]
    feature_histories: tuple[FeatureHistory, ...]
    selection_accounting: tuple[AccountingRow, ...]
    definition_version: str = "scenario_summary_v1"


class TemplateId(StrEnum):
    STATUS_NONE = "STATUS_NONE"
    STATUS_OBSERVED = "STATUS_OBSERVED"
    CAPTURE_NORMAL = "CAPTURE_NORMAL"
    CAPTURE_EP = "CAPTURE_EP"
    MOVE = "MOVE"
    PROMOTION = "PROMOTION"
    CASTLING_ROOK = "CASTLING_ROOK"
    PIECE_STATE = "PIECE_STATE"
    FOCUS_OCCUPANT = "FOCUS_OCCUPANT"
    FOCUS_ATTACKERS = "FOCUS_ATTACKERS"
    FOCUS_LEGAL_CAPTURES_NOW = "FOCUS_LEGAL_CAPTURES_NOW"
    PAWN_FLAGS = "PAWN_FLAGS"
    PAWN_SUPPORTERS = "PAWN_SUPPORTERS"
    FILE_STATE = "FILE_STATE"
    ATTACK_FOOTPRINT = "ATTACK_FOOTPRINT"
    ATTACK_PARTITION = "ATTACK_PARTITION"
    RAY_STATE = "RAY_STATE"
    PIN_PRESENT_TRUE = "PIN_PRESENT_TRUE"
    PIN_PRESENT_FALSE = "PIN_PRESENT_FALSE"
    MATERIAL_COUNTS = "MATERIAL_COUNTS"
    FOCUS_LOSSES = "FOCUS_LOSSES"
    TEMPORARY_COUNT = "TEMPORARY_COUNT"


@dataclass(frozen=True, slots=True)
class RenderedFactSentence(Record):
    template_id: TemplateId
    text: str
    source_refs: tuple[SourceRef, ...]

    def __post_init__(self) -> None:
        Record.__post_init__(self)
        require(
            bool(self.text) and bool(self.source_refs), "factual sentences need text and sources"
        )


@dataclass(frozen=True, slots=True)
class RenderedScenarioReport(Record):
    digest: tuple[RenderedFactSentence, ...]
    detail: tuple[RenderedFactSentence, ...]


def _canonical(values: tuple, key=lambda v: v) -> bool:
    return tuple(sorted(set(values), key=key)) == values


def _base_index(base: BasePieceRef) -> int:
    return (int(base.base_square[1]) - 1) * 8 + ord(base.base_square[0]) - ord("a")


def _squares(values: tuple[str, ...]) -> None:
    require(all(is_square(s) for s in values), "invalid geometric square")
    require(_canonical(values, lambda s: (int(s[1]), s[0])), "noncanonical geometric squares")


def _property_index(key: PropertyKey) -> tuple:
    family = list(FactKind).index(key.family)
    if type(key) is PinKey:
        return family, *(_base_index(b) for b in (key.pinner, key.pinned, key.king))
    if type(key) is RayKey:
        return family, _base_index(key.subject), *key.direction
    if type(key) is SubjectKey:
        return family, _base_index(key.subject)
    if type(key) is SquareKey:
        return family, (int(key.square[1]) - 1) * 8 + ord(key.square[0]) - ord("a")
    return family, ord(key.file)


def _candidate_index(key: CandidateKey) -> tuple:
    if type(key) is StepKey:
        return key.ply, *_property_index(key.property)
    if type(key) is SnapshotKey:
        return key.frame, *_property_index(key.property)
    if type(key) in (CaptureKey, TransitionKey):
        return (
            key.ply,
            list(EventKind).index(key.family),
            (0 if type(key) is CaptureKey else _base_index(key.subject)),
        )
    if type(key) is CountKey:
        return (
            list(CountView).index(key.family),
            list(Color).index(key.color),
            list(PieceType).index(key.piece_type),
        )
    return _property_index(key)


def _local(record: Record) -> None:
    """Local shape checks; cross-frame coverage and ordering are recomputed by the service."""
    for field in fields(record):
        value = getattr(record, field.name)
        if type(value) in (BasePieceRef, PieceRef):
            square = value.base_square if type(value) is BasePieceRef else value.square
            require(
                is_square(square)
                and type(value.color) is Color
                and type(value.piece_type) is PieceType,
                "invalid typed piece identity",
            )
    if type(record) is SubjectKey:
        require(
            record.family
            in (
                FactKind.PIECE_STATE,
                FactKind.PAWN_FLAGS,
                FactKind.PAWN_SUPPORTERS,
                FactKind.ATTACK_FOOTPRINT,
                FactKind.ATTACK_PARTITION,
            ),
            "invalid subject property family",
        )
    elif type(record) is SquareKey:
        require(
            record.family
            in (
                FactKind.FOCUS_OCCUPANT,
                FactKind.FOCUS_ATTACKERS,
                FactKind.FOCUS_LEGAL_CAPTURES_NOW,
            ),
            "invalid square property family",
        )
    elif type(record) is FileKey:
        require(record.family is FactKind.FILE_STATE, "invalid file family")
    elif type(record) is RayKey:
        require(record.family is FactKind.RAY_STATE, "invalid ray family")
    elif type(record) is PinKey:
        require(record.family is FactKind.PIN_PRESENT, "invalid pin family")
    elif type(record) is CaptureKey:
        require(record.family is EventKind.CAPTURE, "invalid capture family")
    elif type(record) is TransitionKey:
        require(record.family is not EventKind.CAPTURE, "capture has no transition subject key")
    elif type(record) in (MaterialSource, CountKey):
        require(record.piece_type is not PieceType.KING, "king is not a count view")
    elif type(record) is PhysicalPiece:
        require(record.base.color is record.current.color, "physical piece changes color")
    elif type(record) is Attackers:
        for color, pieces in ((Color.WHITE, record.white), (Color.BLACK, record.black)):
            require(all(p.base.color is color for p in pieces), "attacker color differs")
            require(
                _canonical(pieces, lambda p: _base_index(p.base)), "noncanonical physical attackers"
            )
    elif type(record) is Supporters:
        require(_canonical(record.bases, _base_index), "noncanonical supporters")
    elif type(record) is Footprint:
        _squares(record.squares)
    elif type(record) is AttackPartition:
        for part in (record.empty, record.friendly, record.enemy):
            _squares(part)
        require(
            len({*record.empty, *record.friendly, *record.enemy})
            == len(record.empty) + len(record.friendly) + len(record.enemy),
            "overlapping attack partitions",
        )
    elif type(record) is PhysicalRay:
        require(
            tuple(p.current for p in record.occupants) == record.ray.occupants,
            "physical ray occupants differ",
        )
    elif type(record) is SelectedChange:
        require(
            record.key == record.before.key == record.after.key
            and record.before.frame < record.after.frame
            and record.before.value != record.after.value,
            "invalid changed property",
        )
    elif type(record) is ScenarioEvent:
        require(
            (type(record.key) is CaptureKey) == (type(record.payload) is CaptureDelta),
            "event payload kind differs",
        )
        require(
            bool(record.source_refs) and len(set(record.source_refs)) == len(record.source_refs),
            "event sources must be nonempty and unique",
        )
    elif type(record) is HistoryRun:
        require(
            record.end >= record.start
            and tuple(f.frame for f in record.facts) == tuple(range(record.start, record.end + 1)),
            "run frame coverage differs",
        )
        require(
            len({f.key for f in record.facts}) == 1
            and all(f.value == record.facts[0].value for f in record.facts),
            "run must contain one equal property value",
        )
    elif type(record) is FeatureHistory:
        require(bool(record.runs) and bool(record.relevant_steps), "selected history is empty")
        require(
            record.key.family not in (FactKind.PIECE_STATE, FactKind.FOCUS_LEGAL_CAPTURES_NOW),
            "untracked property",
        )
        require(
            record.runs[0].start == 0
            and all(
                a.end + 1 == b.start and a.facts[0].value != b.facts[0].value
                for a, b in zip(record.runs, record.runs[1:])
            ),
            "history runs must be contiguous and maximal",
        )
        require(
            all(f.key == record.key for run in record.runs for f in run.facts),
            "history property differs",
        )
        require(
            all(k.property == record.key for k in record.relevant_steps)
            and _canonical(record.relevant_steps, _candidate_index),
            "invalid history relevance keys",
        )
    elif type(record) is FocusSnapshot:
        require(
            all(
                f.frame == record.frame
                for f in (record.occupant, record.attackers, record.legal_captures)
            ),
            "snapshot fact frames differ",
        )
        require(
            tuple(f.key.family for f in (record.occupant, record.attackers, record.legal_captures))
            == (
                FactKind.FOCUS_OCCUPANT,
                FactKind.FOCUS_ATTACKERS,
                FactKind.FOCUS_LEGAL_CAPTURES_NOW,
            ),
            "snapshot families differ",
        )
        require(
            len({f.key.square for f in (record.occupant, record.attackers, record.legal_captures)})
            == 1,
            "snapshot focus differs",
        )
    elif type(record) is ParticipantSummary:
        require(
            bool(record.history_refs)
            and all(
                r.subject == record.base and r.frame_index == i
                for i, r in enumerate(record.history_refs)
            ),
            "participant history coverage differs",
        )
    elif type(record) is ExchangeDetail:
        require(
            _canonical(tuple(p.base for p in record.participants), _base_index)
            and record.temporary_track_count >= 0,
            "invalid participants or temporary count",
        )
    elif type(record) is CountFact:
        require(record.count != 0 and bool(record.source_refs), "zero or unreferenced aggregate")
        require(
            record.key.family is not CountView.FOCUS_LOSSES or record.count > 0,
            "negative capture loss",
        )
    elif type(record) is AccountingRow:
        allowed = {
            Bucket.STEPS: tuple(f for f in FactKind if f is not FactKind.FOCUS_LEGAL_CAPTURES_NOW),
            Bucket.ENDPOINTS: tuple(
                f for f in FactKind if f is not FactKind.FOCUS_LEGAL_CAPTURES_NOW
            ),
            Bucket.EVENTS: tuple(EventKind),
            Bucket.SNAPSHOTS: (
                FactKind.FOCUS_OCCUPANT,
                FactKind.FOCUS_ATTACKERS,
                FactKind.FOCUS_LEGAL_CAPTURES_NOW,
            ),
            Bucket.AGGREGATES: tuple(CountView),
        }
        key_types = {
            Bucket.STEPS: (StepKey,),
            Bucket.ENDPOINTS: get_args(PropertyKey.__value__),
            Bucket.EVENTS: (CaptureKey, TransitionKey),
            Bucket.SNAPSHOTS: (SnapshotKey,),
            Bucket.AGGREGATES: (CountKey,),
        }
        require(
            record.family in allowed[record.bucket]
            and type(record.family) is type(allowed[record.bucket][0]),
            "unsupported accounting family/bucket",
        )
        require(
            all(
                type(k) in key_types[record.bucket]
                and (k.property.family if type(k) in (StepKey, SnapshotKey) else k.family)
                is record.family
                for k in record.candidate_keys
            ),
            "accounting key family/bucket differs",
        )
        for keys in (record.candidate_keys, record.included_keys, record.excluded_keys):
            require(_canonical(keys, _candidate_index), "noncanonical accounting keys")
        require(
            len(set(record.candidate_keys)) == len(record.candidate_keys), "duplicate candidates"
        )
        require(
            len(set(record.included_keys)) == len(record.included_keys)
            and len(set(record.excluded_keys)) == len(record.excluded_keys),
            "duplicate accounting partition",
        )
        require(
            not set(record.included_keys).intersection(record.excluded_keys)
            and set(record.included_keys).union(record.excluded_keys) == set(record.candidate_keys),
            "incomplete accounting partition",
        )
    if type(record) in (SelectedChange, ScenarioEvent):
        require(
            bool(record.reasons)
            and _canonical(record.reasons, lambda r: list(SelectionReason).index(r)),
            "noncanonical selection reasons",
        )
