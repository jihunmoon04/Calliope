"""Compact, source-linked presentation ledgers over fully validated scenario summaries.

The ledger never edits core scenario accounting: every core-included key gets exactly one
presentation row, and capped or contextual facts stay in the summary. Tiers are a closed
narrative order, not chess importance; nothing here reads judgement, scores or claims.
"""

from __future__ import annotations

from calliope.domain.analysis.scenario import (
    COMPACT_SENTENCE_CAP,
    Bucket,
    CompactObservation,
    CountView,
    EventKind,
    Fact,
    FactKind,
    FileKey,
    PinKey,
    PlayedObservationSelection,
    PresentationCandidate,
    PresentationDecision,
    PresentationExclusion,
    RayKey,
    RenderedFactSentence,
    RenderedScenarioReport,
    ScenarioKind,
    ScenarioSummary,
    Sentinel,
    SnapshotKey,
    SquareKey,
    StepKey,
    SubjectKey,
    TemplateId,
    candidate_index,
    require,
)
from calliope.domain.chess import Color
from calliope.errors import InvalidScenarioSummaryError
from calliope.services.position.scenario import (
    _Projection,
    _refs,
    material_count_facts,
    validate_scenario_summary,
)
from calliope.services.position.scenario_renderer import _count, _event, _sentence

# I1-D frozen PLAYED narrative tiers (ascending).
PLAYED_TIERS = {
    EventKind.CAPTURE: 0,
    EventKind.PROMOTION: 1,
    EventKind.CASTLING_ROOK: 2,
    FactKind.PIN_PRESENT: 3,
    FactKind.FILE_STATE: 4,
    CountView.MATERIAL_COUNTS: 5,
    FactKind.PAWN_FLAGS: 6,
    FactKind.PAWN_SUPPORTERS: 7,
    EventKind.MOVE: 8,
    FactKind.ATTACK_FOOTPRINT: 9,
    FactKind.ATTACK_PARTITION: 10,
    FactKind.RAY_STATE: 11,
    FactKind.PIECE_STATE: 12,
}
PLAYED_BUCKET_ORDER = {Bucket.STEPS: 0, Bucket.ENDPOINTS: 1, Bucket.EVENTS: 2, Bucket.AGGREGATES: 3}
UNSUITABLE = (Sentinel.CAPTURED, Sentinel.NOT_APPLICABLE)


class _Item:
    """A core-included key with its typed anchor, sources and payload."""

    __slots__ = ("bucket", "family", "frames", "key", "payload", "refs")

    def __init__(self, bucket, key, family, frames, refs, payload):
        self.bucket, self.key, self.family = bucket, key, family
        self.frames, self.refs, self.payload = frames, refs, payload


def _counts(summary: ScenarioSummary):
    if summary.request.kind is ScenarioKind.EXCHANGE:
        detail = summary.detail
        return (*detail.whole_line_material_changes, *detail.focus_capture_losses)
    return material_count_facts(summary.observed_line)


def _items(summary: ScenarioSummary) -> tuple[_Item, ...]:
    """Every core-included key in accounting order; core-excluded keys never enter."""
    n = len(summary.request.supplied_line)
    events = {e.key: e for e in summary.events}
    steps = {StepKey(c.after.frame, c.key): c for c in summary.selected_changes}
    endpoints = {c.key: c for c in summary.endpoint_changes}
    counts = {c.key: c for c in _counts(summary)}
    snapshots = {
        SnapshotKey(s.frame, f.key): f
        for s in summary.focus_timeline
        for f in (s.occupant, s.attackers, s.legal_captures)
    }
    items = []
    for row in summary.selection_accounting:
        for key in row.included_keys:
            if row.bucket is Bucket.EVENTS:
                event = events[key]
                items.append(
                    _Item(
                        row.bucket,
                        key,
                        row.family,
                        (key.ply - 1, key.ply),
                        event.source_refs,
                        event,
                    )
                )
            elif row.bucket in (Bucket.STEPS, Bucket.ENDPOINTS):
                change = steps[key] if row.bucket is Bucket.STEPS else endpoints[key]
                frames = (change.before.frame, change.after.frame)
                refs = _refs(change.before.source_refs, change.after.source_refs)
                items.append(_Item(row.bucket, key, row.family, frames, refs, change))
            elif row.bucket is Bucket.AGGREGATES:
                count = counts[key]
                items.append(_Item(row.bucket, key, row.family, (0, n), count.source_refs, count))
            else:
                fact = snapshots[key]
                items.append(
                    _Item(
                        row.bucket, key, row.family, (key.frame, key.frame), fact.source_refs, fact
                    )
                )
    return tuple(items)


def _inner(key):
    return key.property if type(key) in (StepKey, SnapshotKey) else key


def _sentinel_affected(change) -> bool:
    return any(
        v in UNSUITABLE for v in (change.before.value, change.after.value) if type(v) is Sentinel
    )


def _candidate(summary, item, rank, exclusion=None, duplicate_of=None):
    return PresentationCandidate(
        item.bucket,
        item.key,
        item.family,
        summary.request.initial.position_id,
        item.frames,
        item.refs,
        rank,
        PresentationDecision.INCLUDE if exclusion is None else PresentationDecision.EXCLUDE,
        exclusion,
        duplicate_of,
    )


def _select_played(summary: ScenarioSummary) -> PlayedObservationSelection:
    require(summary.request.kind is ScenarioKind.PLAYED_TRANSITION, "expected a PLAYED summary")
    participants = {p.base for p in summary.detail.participants}
    items = _items(summary)
    ranks, exclusions, duplicates = {}, {}, {}
    for item in items:
        inner = _inner(item.key)
        subject = getattr(inner, "subject", None)
        direct = 0 if subject is None or subject in participants else 1
        ranks[item.bucket, item.key] = (
            PLAYED_TIERS[item.family],
            direct,
            *candidate_index(inner),
            PLAYED_BUCKET_ORDER[item.bucket],
        )
        if item.bucket is Bucket.ENDPOINTS:
            # One ply: an endpoint change is exactly its STEPS counterpart.
            exclusions[item.bucket, item.key] = PresentationExclusion.SEMANTIC_DUPLICATE
            duplicates[item.bucket, item.key] = StepKey(1, item.key)
        elif item.bucket is Bucket.STEPS and _sentinel_affected(item.payload):
            exclusions[item.bucket, item.key] = PresentationExclusion.CONTEXT_ONLY
    eligible = sorted(
        ((i.bucket, i.key) for i in items if (i.bucket, i.key) not in exclusions),
        key=lambda row: ranks[row],
    )
    selected = tuple(eligible[:COMPACT_SENTENCE_CAP])
    for row in eligible[COMPACT_SENTENCE_CAP:]:
        exclusions[row] = PresentationExclusion.CAP_EXCEEDED
    candidates = tuple(
        _candidate(
            summary,
            item,
            ranks[item.bucket, item.key],
            exclusions.get((item.bucket, item.key)),
            duplicates.get((item.bucket, item.key)),
        )
        for item in items
    )
    return PlayedObservationSelection(candidates, selected)


# ---- closed PLAYED_CHANGE / EXCHANGE_OBS_CHANGE value grammar ---------------------------------


def _tuple(values) -> str:
    return "(" + ", ".join(values) + ")"


def _physical(piece) -> str:
    current = piece.current
    return (
        f"{current.color.value} {current.piece_type.value} on {current.square}"
        f" (initially {piece.base.base_square})"
    )


def _file_state(value) -> str:
    if value.open:
        return "open"
    if value.semi_open_for(Color.WHITE):
        return "semi-open for white"
    if value.semi_open_for(Color.BLACK):
        return "semi-open for black"
    return "neither"


def _state(fact: Fact) -> str:
    family, value = fact.key.family, fact.value
    if value is Sentinel.CAPTURED:
        return "captured"
    if value is Sentinel.NOT_APPLICABLE:
        return "not applicable"
    if value is Sentinel.EMPTY:
        return "empty"
    if family is FactKind.PIECE_STATE:
        return f"{value.color.value} {value.piece_type.value} on {value.square}"
    if family is FactKind.PAWN_FLAGS:
        return (
            f"isolated={str(value.isolated).lower()}, doubled={str(value.doubled).lower()},"
            f" passed={str(value.passed).lower()}"
        )
    if family is FactKind.PAWN_SUPPORTERS:
        return "geometric pawn supporters=" + _tuple(b.base_square for b in value.bases)
    if family is FactKind.FILE_STATE:
        return (
            f"white_pawns={value.white_pawns}, black_pawns={value.black_pawns},"
            f" state={_file_state(value)}"
        )
    if family is FactKind.ATTACK_FOOTPRINT:
        return "geometric squares=" + _tuple(value.squares)
    if family is FactKind.ATTACK_PARTITION:
        return (
            f"geometric empty={_tuple(value.empty)}, friendly={_tuple(value.friendly)},"
            f" enemy={_tuple(value.enemy)}"
        )
    if family is FactKind.RAY_STATE:
        return (
            f"visible={_tuple(value.ray.visible_squares)},"
            f" occupants={_tuple(_physical(p) for p in value.occupants)}"
        )
    if family is FactKind.PIN_PRESENT:
        return "true" if value else "false"
    if family is FactKind.FOCUS_OCCUPANT:
        return _physical(value)
    if family is FactKind.FOCUS_ATTACKERS:
        return (
            f"white={_tuple(_physical(p) for p in value.white)},"
            f" black={_tuple(_physical(p) for p in value.black)}"
        )
    raise InvalidScenarioSummaryError(f"no compact grammar for {family.value}")


def _label(key) -> str:
    if type(key) in (SubjectKey, RayKey):
        return f"piece initially on {key.subject.base_square}"
    if type(key) is FileKey:
        return f"file {key.file}"
    if type(key) is PinKey:
        return (
            f"absolute pin (pinner={key.pinner.base_square}, pinned={key.pinned.base_square},"
            f" king={key.king.base_square})"
        )
    if type(key) is SquareKey:
        return f"square {key.square}"
    raise InvalidScenarioSummaryError("no compact label for key")


def _played_uci(summary: ScenarioSummary) -> str:
    return summary.observed_line.structural.transitions[0].board_delta.move.uci


def _played_sentence(summary, item) -> RenderedFactSentence:
    if item.bucket is Bucket.EVENTS:
        return _event(item.payload)
    if item.bucket is Bucket.AGGREGATES:
        return _count(item.payload, None)
    change = item.payload
    text = (
        f"In the supplied one-move line {_played_uci(summary)}, {_label(change.key)}"
        f" [{change.key.family.value}]: {_state(change.before)} -> {_state(change.after)}."
    )
    return _sentence(TemplateId.PLAYED_CHANGE, text, item.refs)


def _resolve_all(summary: ScenarioSummary, sentences) -> None:
    projection = _Projection(summary.request, summary.observed_line)
    for sentence in sentences:
        for ref in sentence.source_refs:
            projection.resolve(ref)


def _compact_after_validation(summary: ScenarioSummary) -> tuple[CompactObservation, ...]:
    require(summary.request.kind is ScenarioKind.PLAYED_TRANSITION, "unsupported compact kind")
    selection = _select_played(summary)
    items = {(i.bucket, i.key): i for i in _items(summary)}
    observations = tuple(
        CompactObservation(bucket, key, _played_sentence(summary, items[bucket, key]))
        for bucket, key in selection.selected_keys
    )
    _resolve_all(summary, (o.sentence for o in observations))
    return observations


def _render_played(summary: ScenarioSummary) -> RenderedScenarioReport:
    """Validated-summary entry used by ScenarioSummaryRenderer: status detail + capped digest."""
    digest = tuple(o.sentence for o in _compact_after_validation(summary))
    status = _sentence(
        TemplateId.PLAYED_STATUS,
        f"In the supplied one-move line, the played move is {_played_uci(summary)}.",
        summary.events[0].source_refs,
    )
    _resolve_all(summary, (status,))
    return RenderedScenarioReport(digest, (status,))


# ---- public internal entry points ----------------------------------------------------------


class PlayedObservationSelector:
    def select(self, summary: ScenarioSummary) -> PlayedObservationSelection:
        validate_scenario_summary(summary)
        return _select_played(summary)


def compact_observations(summary: ScenarioSummary) -> tuple[CompactObservation, ...]:
    """Fully validate, then return the capped source-linked sentences with their ledger keys."""
    validate_scenario_summary(summary)
    return _compact_after_validation(summary)


def validate_observation_selection(summary: ScenarioSummary, selection) -> None:
    """A caller-held ledger is accepted only if it equals a fresh recomputation."""
    validate_scenario_summary(summary)
    require(type(selection) is PlayedObservationSelection, "unexpected selection type")
    require(selection == _select_played(summary), "presentation ledger differs from recomputation")


def validate_compact_observations(summary: ScenarioSummary, observations) -> None:
    validate_scenario_summary(summary)
    require(
        type(observations) is tuple and observations == _compact_after_validation(summary),
        "compact observations differ from recomputation",
    )
