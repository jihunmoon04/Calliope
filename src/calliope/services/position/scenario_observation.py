"""Compact, source-linked presentation ledgers over fully validated scenario summaries.

The ledger never edits core scenario accounting: every core-included key gets exactly one
presentation row, and capped or contextual facts stay in the summary. Tiers are a closed
narrative order, not chess importance; nothing here reads judgement, scores or claims.
"""

from __future__ import annotations

from calliope.domain.analysis.scenario import (
    COMPACT_SENTENCE_CAP,
    Bucket,
    CaptureKey,
    CompactObservation,
    CountView,
    EventKind,
    ExchangeObservationSelection,
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
    SelectionReason,
    Sentinel,
    SnapshotKey,
    SquareKey,
    StepKey,
    SubjectKey,
    TemplateId,
    TransitionKey,
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

# I2-D frozen EXCHANGE tiers 0, 1, 2, 3, 4, 4.5, 5, 6, 7 stored as their ordinal 0..8.
EX_FOCUS_CAPTURE, EX_VICTIM_CAPTURE, EX_PROMOTION, EX_FOCUS_LOSSES, EX_MATERIAL = range(5)
EX_CONTEXT_CAPTURE, EX_ENDPOINT, EX_STEP, EX_OTHER_EVENT = range(5, 9)
EXCHANGE_BUCKET_ORDER = {
    Bucket.EVENTS: 0,
    Bucket.AGGREGATES: 1,
    Bucket.ENDPOINTS: 2,
    Bucket.STEPS: 3,
    Bucket.SNAPSHOTS: 4,
}
EXCHANGE_CHANGE_FAMILIES = (
    FactKind.PIECE_STATE,
    FactKind.PAWN_FLAGS,
    FactKind.PAWN_SUPPORTERS,
    FactKind.FILE_STATE,
    FactKind.ATTACK_FOOTPRINT,
    FactKind.ATTACK_PARTITION,
    FactKind.RAY_STATE,
    FactKind.PIN_PRESENT,
    FactKind.FOCUS_OCCUPANT,
    FactKind.FOCUS_ATTACKERS,
)


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


def _base_at(summary: ScenarioSummary, frame: int, piece):
    return next(
        h.base for h in summary.observed_line.structural.piece_histories if h.states[frame] == piece
    )


def _promotions(summary: ScenarioSummary):
    """Every actual P5 promotion, core-included or not: TransitionKey -> promoted type."""
    result = {}
    for ply, step in enumerate(summary.observed_line.structural.transitions, 1):
        for transition in step.board_delta.transitions:
            if transition.kind.value == "promotion":
                base = _base_at(summary, ply - 1, transition.before)
                result[TransitionKey(ply, EventKind.PROMOTION, base)] = transition.after.piece_type
    return result


def _select_exchange(summary: ScenarioSummary) -> ExchangeObservationSelection:
    """Dependency-closed two-slot selection: shown counts and promoted victims need witnesses."""
    require(summary.request.kind is ScenarioKind.EXCHANGE, "expected an EXCHANGE summary")
    n = len(summary.request.supplied_line)
    items = _items(summary)
    included = {(i.bucket, i.key) for i in items}
    events = {e.key: e for e in summary.events}
    captures = tuple(e for e in summary.events if type(e.key) is CaptureKey)
    focus_related = any(
        {SelectionReason.FOCUS_CAPTURE, SelectionReason.FOCUS_VICTIM_SQUARE} & set(e.reasons)
        for e in captures
    )
    promotions = _promotions(summary)
    ranks, exclusions, duplicates, witnesses = {}, {}, {}, {}

    def requires(row, needed):
        witnesses[row] = needed
        if any(w not in included for w in needed):
            exclusions[row] = PresentationExclusion.CONTEXT_ONLY

    for item in items:
        row, key = (item.bucket, item.key), item.key
        if item.bucket is Bucket.EVENTS:
            anchor = key.ply
            if type(key) is CaptureKey:
                reasons = events[key].reasons
                if SelectionReason.FOCUS_CAPTURE in reasons:
                    tier = EX_FOCUS_CAPTURE
                elif SelectionReason.FOCUS_VICTIM_SQUARE in reasons:
                    tier = EX_VICTIM_CAPTURE
                else:
                    tier = EX_OTHER_EVENT if focus_related else EX_CONTEXT_CAPTURE
                victim = _base_at(summary, key.ply - 1, events[key].payload.captured)
                requires(
                    row,
                    tuple(
                        (Bucket.EVENTS, p)
                        for p in sorted(promotions, key=candidate_index)
                        if p.subject == victim and p.ply < key.ply
                    ),
                )
            else:
                tier = EX_PROMOTION if key.family is EventKind.PROMOTION else EX_OTHER_EVENT
        elif item.bucket is Bucket.AGGREGATES:
            anchor = n
            if key.family is CountView.FOCUS_LOSSES:
                tier = EX_FOCUS_LOSSES
                needed = tuple(
                    (Bucket.EVENTS, e.key)
                    for e in captures
                    if SelectionReason.FOCUS_CAPTURE in e.reasons
                    and (e.payload.captured.color, e.payload.captured.piece_type)
                    == (key.color, key.piece_type)
                )
                requires(row, needed)
            else:
                tier = EX_MATERIAL
                needed = tuple(
                    (Bucket.EVENTS, e.key)
                    for e in captures
                    if (e.payload.captured.color, e.payload.captured.piece_type)
                    == (key.color, key.piece_type)
                ) + tuple(
                    (Bucket.EVENTS, p)
                    for p, promoted in sorted(
                        promotions.items(), key=lambda kv: candidate_index(kv[0])
                    )
                    if p.subject.color is key.color
                    and (key.piece_type.value == "pawn" or promoted is key.piece_type)
                )
                requires(row, needed)
                if not focus_related:
                    exclusions[row] = PresentationExclusion.CONTEXT_ONLY
        elif item.bucket in (Bucket.STEPS, Bucket.ENDPOINTS):
            anchor = key.ply if item.bucket is Bucket.STEPS else n
            tier = EX_STEP if item.bucket is Bucket.STEPS else EX_ENDPOINT
            if item.bucket is Bucket.ENDPOINTS and n == 1:
                # Only an identical frame pair is a duplicate: one ply, (0, 1) both ways.
                exclusions[row] = PresentationExclusion.SEMANTIC_DUPLICATE
                duplicates[row] = StepKey(1, key)
            elif item.family not in EXCHANGE_CHANGE_FAMILIES or _sentinel_affected(item.payload):
                exclusions[row] = PresentationExclusion.CONTEXT_ONLY
        else:
            anchor, tier = key.frame, EX_OTHER_EVENT
            exclusions[row] = PresentationExclusion.CONTEXT_ONLY
        ranks[row] = (tier, anchor, *candidate_index(key), EXCHANGE_BUCKET_ORDER[item.bucket])
    selected = []
    for row in sorted((r for r in ranks if r not in exclusions), key=lambda r: ranks[r]):
        if row in selected:
            continue  # already accepted inside an earlier capture block
        room = COMPACT_SENTENCE_CAP - len(selected)
        if row[0] is Bucket.EVENTS and type(row[1]) is CaptureKey:
            block = [row, *(w for w in witnesses[row] if w not in selected)]
            if len(block) <= room:
                selected.extend(block)
                continue
        elif row[0] is Bucket.AGGREGATES:
            if room and all(w in selected for w in witnesses[row]):
                selected.append(row)
                continue
        elif room:
            selected.append(row)
            continue
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
    return ExchangeObservationSelection(candidates, tuple(selected))


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


def _exchange_sentence(summary, item) -> RenderedFactSentence:
    if item.bucket is Bucket.EVENTS:
        return _event(item.payload)
    if item.bucket is Bucket.AGGREGATES:
        return _count(item.payload, summary.request.target.square)
    change = item.payload
    a, b = change.before.frame, change.after.frame
    text = (
        f"In the supplied line after ply {b}, {_label(change.key)} [{change.key.family.value}]"
        f" from frame {a} to {b}: {_state(change.before)} -> {_state(change.after)}."
    )
    return _sentence(TemplateId.EXCHANGE_OBS_CHANGE, text, item.refs)


def _resolve_all(summary: ScenarioSummary, sentences) -> None:
    projection = _Projection(summary.request, summary.observed_line)
    for sentence in sentences:
        for ref in sentence.source_refs:
            projection.resolve(ref)


def _select(summary: ScenarioSummary):
    if summary.request.kind is ScenarioKind.PLAYED_TRANSITION:
        return _select_played(summary)
    if summary.request.kind is ScenarioKind.EXCHANGE:
        return _select_exchange(summary)
    raise InvalidScenarioSummaryError("unsupported compact kind")


def _compact_after_validation(summary: ScenarioSummary) -> tuple[CompactObservation, ...]:
    selection = _select(summary)
    played = summary.request.kind is ScenarioKind.PLAYED_TRANSITION
    sentence = _played_sentence if played else _exchange_sentence
    items = {(i.bucket, i.key): i for i in _items(summary)}
    observations = tuple(
        CompactObservation(bucket, key, sentence(summary, items[bucket, key]))
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


class ExchangeObservationSelector:
    """Compact ledger over a validated EXCHANGE summary; the legacy report is not involved."""

    def select(self, summary: ScenarioSummary) -> ExchangeObservationSelection:
        validate_scenario_summary(summary)
        return _select_exchange(summary)


def compact_observations(summary: ScenarioSummary) -> tuple[CompactObservation, ...]:
    """Fully validate, then return the capped source-linked sentences with their ledger keys."""
    validate_scenario_summary(summary)
    return _compact_after_validation(summary)


def validate_observation_selection(summary: ScenarioSummary, selection) -> None:
    """A caller-held ledger is accepted only if it equals a fresh recomputation."""
    validate_scenario_summary(summary)
    require(
        type(selection) in (PlayedObservationSelection, ExchangeObservationSelection),
        "unexpected selection type",
    )
    require(selection == _select(summary), "presentation ledger differs from recomputation")


def validate_compact_observations(summary: ScenarioSummary, observations) -> None:
    validate_scenario_summary(summary)
    require(
        type(observations) is tuple and observations == _compact_after_validation(summary),
        "compact observations differ from recomputation",
    )
