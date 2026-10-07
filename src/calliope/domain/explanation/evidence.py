"""Internal immutable MVP-P10 evidence values.

Evidence records retain already-reviewed P8/P9 machine provenance as typed domain values.
They validate structural shape only: they never replay moves, run chess rules, or decide
whether evidence is sufficient for a claim.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from calliope.domain.analysis.bad_move import (
    BadMoveCauseKind,
    BasePieceRef,
    MateEvidenceLevel,
    MaterialLineEvidence,
)
from calliope.domain.analysis.counterfactual import (
    CounterfactualProbe,
    ProbeResult,
    TerminalOutcome,
)
from calliope.domain.analysis.delta import BoardDelta
from calliope.domain.analysis.good_move import (
    GoodMoveBenefitKind,
    RepresentativeAlternative,
    _alternative_keys,
)
from calliope.domain.analysis.tactics import TacticalCandidate
from calliope.domain.explanation.claim import (
    MoveClaimEntity,
    PieceClaimEntity,
    _has_duplicate_entities,
    _is_ordinal_id,
    _mint_ordinal_id,
    _require_evidence_ids,
    base_piece_sort_key,
)
from calliope.errors import ExplanationEvidenceError


class EvidenceSourceFamily(StrEnum):
    BAD_MOVE_CAUSE = "bad_move_cause"
    GOOD_MOVE_BENEFIT = "good_move_benefit"


class EvidenceForm(StrEnum):
    DIRECT = "direct"
    TESTED_RESPONSE = "tested_response"
    PRESERVATION = "preservation"


def mint_evidence_id(index: int) -> str:
    """Request-local evidence id for the given 1-based canonical ordinal."""

    return _mint_ordinal_id("ev", index, ExplanationEvidenceError)


def _fail(message: str) -> ExplanationEvidenceError:
    return ExplanationEvidenceError(message)


def _require_record_header(evidence_id: str, base_position_id: str) -> None:
    if not _is_ordinal_id(evidence_id, "ev"):
        raise _fail("evidence_id must be a canonical evidence id")
    if not base_position_id:
        raise _fail("base_position_id must not be empty")


def _require_entities(
    moves: tuple[MoveClaimEntity, ...], pieces: tuple[PieceClaimEntity, ...]
) -> None:
    if any(not isinstance(move, MoveClaimEntity) for move in moves):
        raise _fail("moves must contain MoveClaimEntity values")
    if any(not isinstance(piece, PieceClaimEntity) for piece in pieces):
        raise _fail("pieces must contain PieceClaimEntity values")
    if _has_duplicate_entities(moves):
        raise _fail("moves must not contain duplicate move entities")
    if _has_duplicate_entities(pieces):
        raise _fail("pieces must not contain duplicate piece entities")


def _require_board_deltas(board_deltas: tuple[BoardDelta, ...]) -> None:
    if any(not isinstance(delta, BoardDelta) for delta in board_deltas):
        raise _fail("board_deltas must contain BoardDelta values")


def _require_terminal(terminal: TerminalOutcome | None) -> None:
    if terminal is not None and not isinstance(terminal, TerminalOutcome):
        raise _fail("terminal must be a TerminalOutcome or None")


def _require_probe_base(probe: CounterfactualProbe, base_position_id: str, label: str) -> None:
    if probe.base.position_id != base_position_id:
        raise _fail(f"{label} belongs to another base position")


def _require_alternatives(
    alternatives: tuple[RepresentativeAlternative, ...],
    failed: tuple[RepresentativeAlternative, ...],
) -> None:
    """Existing P9 rank/UCI invariants; failed membership is by (rank, UCI)."""

    try:
        representative = _alternative_keys(alternatives, "representative_alternatives")
        failed_keys = _alternative_keys(failed, "failed_alternatives")
    except ValueError as exc:
        raise _fail(str(exc)) from exc
    if not set(failed_keys).issubset(representative):
        raise _fail("failed_alternatives must be a subset of representatives by rank and UCI")


# -- evidence variants --


@dataclass(frozen=True, slots=True)
class BoardFactEvidence:
    """Deterministic board/rule facts already verified upstream; rules are not re-run."""

    evidence_id: str
    base_position_id: str
    moves: tuple[MoveClaimEntity, ...] = ()
    pieces: tuple[PieceClaimEntity, ...] = ()
    board_deltas: tuple[BoardDelta, ...] = ()
    terminal: TerminalOutcome | None = None
    sole_response: MoveClaimEntity | None = None

    def __post_init__(self) -> None:
        _require_record_header(self.evidence_id, self.base_position_id)
        _require_entities(self.moves, self.pieces)
        _require_board_deltas(self.board_deltas)
        _require_terminal(self.terminal)
        if self.sole_response is not None and self.sole_response not in self.moves:
            raise _fail("sole_response must also appear in moves")


@dataclass(frozen=True, slots=True)
class EngineEvidence:
    """One retained non-terminal P7 result; identity/settings stay inside its analysis."""

    evidence_id: str
    base_position_id: str
    probe_result: ProbeResult

    def __post_init__(self) -> None:
        _require_record_header(self.evidence_id, self.base_position_id)
        if not isinstance(self.probe_result, ProbeResult):
            raise _fail("probe_result must be a ProbeResult")
        if self.probe_result.engine_analysis is None or self.probe_result.terminal is not None:
            raise _fail("engine evidence requires a non-terminal probe result")
        _require_probe_base(self.probe_result.probe, self.base_position_id, "probe_result")


@dataclass(frozen=True, slots=True)
class VariationEvidence:
    """Already-reviewed replay/material provenance for one probe line; never FORCED proof."""

    evidence_id: str
    base_position_id: str
    probe: CounterfactualProbe
    moves: tuple[MoveClaimEntity, ...] = ()
    pieces: tuple[PieceClaimEntity, ...] = ()
    board_deltas: tuple[BoardDelta, ...] = ()
    material_evidence: tuple[MaterialLineEvidence, ...] = ()
    terminal: TerminalOutcome | None = None
    replayed_pv_ends_in_checkmate: bool | None = None

    def __post_init__(self) -> None:
        _require_record_header(self.evidence_id, self.base_position_id)
        if not isinstance(self.probe, CounterfactualProbe):
            raise _fail("probe must be a CounterfactualProbe")
        _require_probe_base(self.probe, self.base_position_id, "probe")
        _require_entities(self.moves, self.pieces)
        _require_board_deltas(self.board_deltas)
        for material in self.material_evidence:
            if not isinstance(material, MaterialLineEvidence):
                raise _fail("material_evidence must contain MaterialLineEvidence values")
            _require_probe_base(material.probe, self.base_position_id, "material evidence")
        _require_terminal(self.terminal)


@dataclass(frozen=True, slots=True)
class CounterfactualEvidence:
    """A bounded experiment over the complete, verbatim upstream probe-result tuple."""

    evidence_id: str
    base_position_id: str
    form: EvidenceForm
    probe_results: tuple[ProbeResult, ...]
    comparator_move: MoveClaimEntity | None = None
    tested_response: MoveClaimEntity | None = None
    representative_alternatives: tuple[RepresentativeAlternative, ...] = ()
    failed_alternatives: tuple[RepresentativeAlternative, ...] = ()
    equivalent_alternative_benefit: bool | None = None

    def __post_init__(self) -> None:
        _require_record_header(self.evidence_id, self.base_position_id)
        if not isinstance(self.form, EvidenceForm):
            raise _fail("form must be an EvidenceForm")
        if not self.probe_results:
            raise _fail("counterfactual evidence requires probe_results")
        for result in self.probe_results:
            if not isinstance(result, ProbeResult):
                raise _fail("probe_results must contain ProbeResult values")
            _require_probe_base(result.probe, self.base_position_id, "probe result")
        for move in (self.comparator_move, self.tested_response):
            if move is not None and not isinstance(move, MoveClaimEntity):
                raise _fail("comparator/tested moves must be MoveClaimEntity values")
        _require_alternatives(self.representative_alternatives, self.failed_alternatives)


@dataclass(frozen=True, slots=True)
class MotifEvidence:
    """Supporting P6 candidates only; motif evidence alone has no claim authority."""

    evidence_id: str
    base_position_id: str
    candidates: tuple[TacticalCandidate, ...]
    pieces: tuple[PieceClaimEntity, ...] = ()
    moves: tuple[MoveClaimEntity, ...] = ()

    def __post_init__(self) -> None:
        _require_record_header(self.evidence_id, self.base_position_id)
        if not self.candidates:
            raise _fail("motif evidence requires candidates")
        if any(not isinstance(candidate, TacticalCandidate) for candidate in self.candidates):
            raise _fail("candidates must contain TacticalCandidate values")
        _require_entities(self.moves, self.pieces)


EvidenceRecord = (
    BoardFactEvidence | EngineEvidence | VariationEvidence | CounterfactualEvidence | MotifEvidence
)

EVIDENCE_RECORD_TYPE_ORDER: tuple[type, ...] = (
    BoardFactEvidence,
    MotifEvidence,
    EngineEvidence,
    VariationEvidence,
    CounterfactualEvidence,
)
"""Frozen within-group evidence order; never derived from class names or hashes."""


def evidence_record_type_rank(record: EvidenceRecord) -> int:
    for rank, record_type in enumerate(EVIDENCE_RECORD_TYPE_ORDER):
        if type(record) is record_type:
            return rank
    raise _fail(f"unsupported evidence record: {type(record).__name__}")


# -- groups and bundle --


@dataclass(frozen=True, slots=True)
class EvidenceGroup:
    """Source descriptor and owned evidence ids for one supported P8/P9 child."""

    source_family: EvidenceSourceFamily
    source_kind: BadMoveCauseKind | GoodMoveBenefitKind
    source_subject: tuple[BasePieceRef, ...]
    played_move: MoveClaimEntity
    evidence_form: EvidenceForm
    evidence_ids: tuple[str, ...]
    required_probe_results: tuple[ProbeResult, ...]
    comparator_move: MoveClaimEntity | None = None
    response: MoveClaimEntity | None = None
    representative_alternatives: tuple[RepresentativeAlternative, ...] = ()
    failed_alternatives: tuple[RepresentativeAlternative, ...] = ()
    mate_evidence_level: MateEvidenceLevel | None = None
    replayed_pv_ends_in_checkmate: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_family, EvidenceSourceFamily):
            raise _fail("source_family must be an EvidenceSourceFamily")
        expected_kind = (
            BadMoveCauseKind
            if self.source_family is EvidenceSourceFamily.BAD_MOVE_CAUSE
            else GoodMoveBenefitKind
        )
        if not isinstance(self.source_kind, expected_kind):
            raise _fail(f"source_kind does not belong to {self.source_family.value}")
        if not isinstance(self.evidence_form, EvidenceForm):
            raise _fail("evidence_form must be an EvidenceForm")

        if not self.source_subject:
            raise _fail("source_subject must not be empty")
        if any(not isinstance(base, BasePieceRef) for base in self.source_subject):
            raise _fail("source_subject must contain BasePieceRef values")
        if len(self.source_subject) != len(set(self.source_subject)):
            raise _fail("source_subject must contain unique base pieces")
        if list(self.source_subject) != sorted(self.source_subject, key=base_piece_sort_key):
            raise _fail("source_subject must be in canonical base-piece order")

        if not isinstance(self.played_move, MoveClaimEntity):
            raise _fail("played_move must be a MoveClaimEntity")
        for move in (self.comparator_move, self.response):
            if move is not None and not isinstance(move, MoveClaimEntity):
                raise _fail("comparator/response moves must be MoveClaimEntity values")

        _require_evidence_ids(self.evidence_ids, "group evidence_ids", ExplanationEvidenceError)
        if any(not isinstance(result, ProbeResult) for result in self.required_probe_results):
            raise _fail("required_probe_results must contain ProbeResult values")
        _require_alternatives(self.representative_alternatives, self.failed_alternatives)
        if self.replayed_pv_ends_in_checkmate is not None and self.mate_evidence_level is None:
            raise _fail("replayed mate flag requires mate_evidence_level")


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    """All evidence for one parent P8 **or** P9 result; caller order is retained."""

    base_position_id: str
    evidence: tuple[EvidenceRecord, ...]
    groups: tuple[EvidenceGroup, ...]

    def __post_init__(self) -> None:
        if not self.base_position_id:
            raise _fail("base_position_id must not be empty")
        if any(not isinstance(record, EVIDENCE_RECORD_TYPE_ORDER) for record in self.evidence):
            raise _fail("evidence must contain evidence record values")
        if any(not isinstance(group, EvidenceGroup) for group in self.groups):
            raise _fail("groups must contain EvidenceGroup values")

        records = {}
        for record in self.evidence:
            if record.evidence_id in records:
                raise _fail(f"duplicate evidence id {record.evidence_id}")
            if record.base_position_id != self.base_position_id:
                raise _fail(f"evidence {record.evidence_id} belongs to another base position")
            records[record.evidence_id] = record

        families = {group.source_family for group in self.groups}
        if len(families) > 1:
            raise _fail("bundle groups must come from one source family")

        owners = Counter(evidence_id for group in self.groups for evidence_id in group.evidence_ids)
        for group in self.groups:
            if group.played_move.position_id != self.base_position_id:
                raise _fail("group played move must be legal from the bundle base")
            unknown = [
                evidence_id for evidence_id in group.evidence_ids if evidence_id not in records
            ]
            if unknown:
                raise _fail(f"group references unknown evidence id {unknown[0]}")
            shared = [evidence_id for evidence_id in group.evidence_ids if owners[evidence_id] > 1]
            if shared:
                raise _fail(f"evidence id {shared[0]} is owned by more than one group")

            counterfactuals = [
                records[evidence_id]
                for evidence_id in group.evidence_ids
                if isinstance(records[evidence_id], CounterfactualEvidence)
            ]
            if len(counterfactuals) > 1:
                raise _fail("group owns more than one CounterfactualEvidence")
            if counterfactuals and (
                counterfactuals[0].probe_results != group.required_probe_results
            ):
                raise _fail("group CounterfactualEvidence differs from required_probe_results")

        unowned = [evidence_id for evidence_id in records if evidence_id not in owners]
        if unowned:
            raise _fail(f"evidence {unowned[0]} is not owned by any group")
