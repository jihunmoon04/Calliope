"""One observed line, a closed EXCHANGE policy and a replay-free integrity boundary.

Intentionally not exported by services.position: physical identity currently lives
under services.explanation, whose package imports the position foundation.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from calliope.domain.analysis.activity import SLIDER_DIRECTIONS, ActivityLineAnalysis
from calliope.domain.analysis.scenario import (
    AccountingRow,
    ActivitySource,
    Attackers,
    AttackPartition,
    Bucket,
    CaptureKey,
    CaptureSource,
    CountFact,
    CountKey,
    CountView,
    EventKind,
    ExchangeDetail,
    ExchangeStatus,
    ExcludedCandidate,
    Fact,
    FactKind,
    FeatureHistory,
    FileKey,
    FileSource,
    FocusSnapshot,
    Footprint,
    HistoryRun,
    HistorySource,
    LegalCaptures,
    MaterialSource,
    ParticipantSummary,
    PawnFlags,
    PawnSource,
    PhysicalPiece,
    PhysicalRay,
    PinKey,
    PinSource,
    PropertyKey,
    RayKey,
    RaySource,
    Record,
    ScenarioEvent,
    ScenarioRequest,
    ScenarioSummary,
    SelectedChange,
    SelectionReason,
    Sentinel,
    SnapshotKey,
    SourceRef,
    SquareKey,
    SquareSource,
    StepKey,
    SubjectKey,
    Supporters,
    TransitionKey,
    TransitionSource,
    require,
)
from calliope.domain.chess import Color, PieceType, square_index
from calliope.errors import CalliopeError, InvalidScenarioRequestError, InvalidScenarioSummaryError
from calliope.services.explanation.piece_identity import BasePieceIdentityMap
from calliope.services.position.activity import (
    ActivityLineAnalyzer,
    _activity_diff,
    _validate_captures,
    _validate_moves,
    _validate_structural,
)
from calliope.services.position.positional import (
    _material_delta,
    _reconcile_delta,
    extract_positional_features,
)

COUNTS = (PieceType.PAWN, PieceType.KNIGHT, PieceType.BISHOP, PieceType.ROOK, PieceType.QUEEN)
FOCUS = (FactKind.FOCUS_OCCUPANT, FactKind.FOCUS_ATTACKERS, FactKind.FOCUS_LEGAL_CAPTURES_NOW)
CHANGED = tuple(f for f in FactKind if f is not FactKind.FOCUS_LEGAL_CAPTURES_NOW)


def _base_order(base):
    return square_index(base.base_square)


def _property_order(key):
    order = list(FactKind).index(key.family)
    if type(key) is PinKey:
        return order, *map(_base_order, (key.pinner, key.pinned, key.king))
    if type(key) is RayKey:
        return order, _base_order(key.subject), *key.direction
    if type(key) is SubjectKey:
        return order, _base_order(key.subject)
    if type(key) is SquareKey:
        return order, square_index(key.square)
    return order, ord(key.file)


def _refs(*groups):
    return tuple(dict.fromkeys(r for group in groups for r in group))


def _validate_observed(request: ScenarioRequest, observed: ActivityLineAnalysis) -> None:
    """Reconcile retained records, not chess legality; never calls a port."""
    require(type(observed) is ActivityLineAnalysis, "wrong observed line type")
    observed.__post_init__()
    structural, frames = observed.structural, observed.activity_frames
    require(structural.initial.position == request.initial, "request initial anchor differs")
    require(
        len(structural.transitions) == len(request.supplied_line), "request line length differs"
    )
    identity = BasePieceIdentityMap.from_facts(structural.initial.facts)
    expected_histories = {base: [] for base in identity.base_pieces}
    for i, frame in enumerate(frames):
        frame.__post_init__()
        _validate_structural(frame.structural)
        require(
            frame.structural.features == extract_positional_features(frame.structural.facts),
            "positional features differ from P4",
        )
        frame.activity.__post_init__()
        for record in (
            *frame.activity.pieces,
            *frame.activity.squares,
            *frame.activity.rays,
            *frame.activity.absolute_pins,
        ):
            record.__post_init__()
        moves = tuple(
            sorted(
                (m for p in frame.activity.pieces for m in (p.legal_moves_now or ())),
                key=lambda m: m.uci,
            )
        )
        pieces = {s.piece.square: s.piece for s in frame.structural.facts.pieces}
        _validate_moves(frame.structural.position, pieces, moves)
        _validate_captures(pieces, moves, frame.structural.facts.legal_captures)
        if i:
            step = structural.transitions[i - 1]
            require(
                step.before == frames[i - 1].structural and step.after == frame.structural,
                "nonconsecutive step",
            )
            require(
                step.board_delta.move.uci == request.supplied_line[i - 1].uci,
                "supplied UCI differs",
            )
            require(
                step.board_delta.before_position_id == step.before.position.position_id
                and step.board_delta.after_position_id == step.after.position.position_id,
                "delta anchor differs",
            )
            require(
                step.board_delta.mover is step.before.position.side_to_move, "delta mover differs"
            )
            _reconcile_delta(step.before.facts, step.after.facts, step.board_delta)
            identity = identity.advance(step.board_delta)
            require(
                observed.activity_transitions[i - 1] == _activity_diff(step, frames[i - 1], frame),
                "activity diff differs",
            )
        require(
            identity.position_id == frame.structural.position.position_id, "history anchor differs"
        )
        require(
            set(identity.live_pieces) == set(pieces.values()),
            "inverse identities do not cover frame",
        )
        for base in identity.base_pieces:
            expected_histories[base].append(identity.current_piece(base))
    require(
        tuple((h.base, h.states) for h in structural.piece_histories)
        == tuple((b, tuple(s)) for b, s in expected_histories.items()),
        "physical histories differ from P5",
    )
    require(
        structural.material_changes
        == _material_delta(structural.initial.facts, structural.final.facts),
        "line material differs",
    )


class _Projection:
    def __init__(self, request: ScenarioRequest, observed: ActivityLineAnalysis):
        self.request, self.observed = request, observed
        self.frames = observed.activity_frames
        self.n = len(self.frames) - 1
        self.histories = {h.base: h.states for h in observed.structural.piece_histories}
        self.bases = tuple(self.histories)
        self.inverse = tuple(
            {s[i]: b for b, s in self.histories.items() if s[i] is not None}
            for i in range(self.n + 1)
        )
        self.pawns = tuple({p.pawn: p for p in f.structural.features.pawns} for f in self.frames)
        self.activities = tuple({p.piece: p for p in f.activity.pieces} for f in self.frames)
        self.rays = tuple(
            {(r.source, r.direction): r for r in f.activity.rays} for f in self.frames
        )
        self.pins = tuple(
            {
                tuple(self.inverse[i][p] for p in (pin.pinner, pin.pinned, pin.king))
                for pin in f.activity.absolute_pins
            }
            for i, f in enumerate(self.frames)
        )
        self.pin_keys = tuple(
            sorted(set().union(*self.pins), key=lambda t: tuple(map(_base_order, t)))
        )
        self.cache = {}

    def history_ref(self, i, base):
        require(base in self.histories, "unknown physical identity")
        return HistorySource(i, self.frames[i].activity.position_id, base)

    def physical(self, i, piece):
        return PhysicalPiece(self.inverse[i][piece], piece)

    def fact(self, key: PropertyKey, i: int) -> Fact:
        if (key, i) in self.cache:
            return self.cache[key, i]
        f, pid, family = self.frames[i], self.frames[i].activity.position_id, key.family
        references = []
        if type(key) is SquareKey:
            access = f.activity.squares[square_index(key.square)]
            references.append(SquareSource(i, pid, key.square))
            if family is FactKind.FOCUS_OCCUPANT:
                value = self.physical(i, access.occupant) if access.occupant else Sentinel.EMPTY
                pieces = (access.occupant,) if access.occupant else ()
            elif family is FactKind.FOCUS_ATTACKERS:
                white = tuple(
                    sorted(
                        (self.physical(i, p) for p in access.white_attackers),
                        key=lambda p: _base_order(p.base),
                    )
                )
                black = tuple(
                    sorted(
                        (self.physical(i, p) for p in access.black_attackers),
                        key=lambda p: _base_order(p.base),
                    )
                )
                value, pieces = (
                    Attackers(white, black),
                    (*access.white_attackers, *access.black_attackers),
                )
            else:
                value = LegalCaptures(f.activity.side_to_move, access.current_legal_captures)
                pieces = tuple(
                    p for c in access.current_legal_captures for p in (c.capturer, c.captured)
                )
            references.extend(self.history_ref(i, self.inverse[i][p]) for p in pieces)
        elif type(key) is FileKey:
            value = f.structural.features.files[ord(key.file) - ord("a")]
            references.append(FileSource(i, pid, key.file))
        elif type(key) is PinKey:
            bases = key.pinner, key.pinned, key.king
            value = bases in self.pins[i]
            references.append(PinSource(i, pid, *bases))
            references.extend(self.history_ref(i, b) for b in bases)
        else:
            piece = self.histories[key.subject][i]
            history = self.history_ref(i, key.subject)
            if family is FactKind.PIECE_STATE:
                value = piece if piece else Sentinel.CAPTURED
            elif family in (FactKind.PAWN_FLAGS, FactKind.PAWN_SUPPORTERS):
                references.append(PawnSource(i, pid, key.subject))
                pawn = self.pawns[i].get(piece)
                value = Sentinel.NOT_APPLICABLE
                if pawn:
                    if family is FactKind.PAWN_FLAGS:
                        value = PawnFlags(pawn.isolated, pawn.doubled, pawn.passed)
                    else:
                        bases = tuple(
                            sorted(
                                (self.inverse[i][p] for p in pawn.pawn_supporters), key=_base_order
                            )
                        )
                        value = Supporters(bases)
                        references.extend(self.history_ref(i, b) for b in bases)
            elif family in (FactKind.ATTACK_FOOTPRINT, FactKind.ATTACK_PARTITION):
                references.append(ActivitySource(i, pid, key.subject))
                activity = self.activities[i].get(piece)
                value = (
                    Sentinel.NOT_APPLICABLE
                    if not activity
                    else (
                        Footprint(activity.footprint)
                        if family is FactKind.ATTACK_FOOTPRINT
                        else AttackPartition(
                            activity.empty_attacks,
                            activity.friendly_attacks,
                            activity.enemy_attacks,
                        )
                    )
                )
            else:
                references.append(RaySource(i, pid, key.subject, key.direction))
                ray = self.rays[i].get((piece, key.direction))
                value = Sentinel.NOT_APPLICABLE
                if ray:
                    occupants = tuple(self.physical(i, p) for p in ray.occupants)
                    value = PhysicalRay(ray, key.subject, occupants)
                    references.extend(self.history_ref(i, p.base) for p in occupants)
            references.append(history)
        result = Fact(key, i, value, _refs(references))
        self.cache[key, i] = result
        return result

    def properties(self, a, b):
        keys = []
        for family in CHANGED:
            if family in FOCUS:
                keys.append(SquareKey(family, self.request.target.square))
            elif family is FactKind.FILE_STATE:
                keys.extend(FileKey(family, file) for file in "abcdefgh")
            elif family is FactKind.PIN_PRESENT:
                keys.extend(PinKey(family, *bases) for bases in self.pin_keys)
            elif family is FactKind.RAY_STATE:
                for base in self.bases:
                    directions = set()
                    for i in (a, b):
                        piece = self.histories[base][i]
                        directions.update(
                            SLIDER_DIRECTIONS.get(piece.piece_type, ()) if piece else ()
                        )
                    keys.extend(RayKey(family, base, d) for d in sorted(directions))
            else:
                keys.extend(
                    SubjectKey(family, base)
                    for base in self.bases
                    if family not in (FactKind.PAWN_FLAGS, FactKind.PAWN_SUPPORTERS)
                    or any(
                        p and p.piece_type is PieceType.PAWN
                        for p in (self.histories[base][a], self.histories[base][b])
                    )
                )
        return tuple(sorted(keys, key=_property_order))

    def events(self):
        events = []
        for ply, step in enumerate(self.observed.structural.transitions, 1):
            delta, capture = step.board_delta, step.board_delta.capture
            ids = delta.before_position_id, delta.after_position_id
            if capture:
                bases = (
                    self.inverse[ply - 1][capture.capturer_before],
                    self.inverse[ply - 1][capture.captured],
                )
                refs = (
                    CaptureSource(ply, *ids),
                    *(self.history_ref(i, base) for base in bases for i in (ply - 1, ply)),
                )
                events.append((CaptureKey(ply), capture, delta.move, refs))
            transitions = sorted(
                delta.transitions,
                key=lambda t: (
                    list(EventKind).index(EventKind(t.kind.value.upper())),
                    _base_order(self.inverse[ply - 1][t.before]),
                ),
            )
            for transition in transitions:
                kind = EventKind(transition.kind.value.upper())
                if (
                    kind is EventKind.MOVE
                    and capture
                    and transition.before == capture.capturer_before
                ):
                    continue
                base = self.inverse[ply - 1][transition.before]
                refs = (
                    TransitionSource(ply, *ids, base, transition.kind),
                    self.history_ref(ply - 1, base),
                    self.history_ref(ply, base),
                )
                events.append((TransitionKey(ply, kind, base), transition, delta.move, refs))
        return tuple(events)

    def resolve(self, ref: SourceRef):
        """Resolve a closed selector against retained records, including explicit absence."""
        require(
            type(ref)
            in (
                CaptureSource,
                TransitionSource,
                MaterialSource,
                HistorySource,
                SquareSource,
                PawnSource,
                FileSource,
                ActivitySource,
                RaySource,
                PinSource,
            ),
            "unknown source type",
        )
        ref.__post_init__()
        if type(ref) is MaterialSource:
            require(ref.piece_type in COUNTS, "king material selector is forbidden")
            require(
                (ref.initial_position_id, ref.final_position_id)
                == (self.frames[0].activity.position_id, self.frames[-1].activity.position_id),
                "material anchor differs",
            )
            return tuple(
                sum(
                    s.piece.color is ref.color and s.piece.piece_type is ref.piece_type
                    for s in self.frames[i].structural.facts.pieces
                )
                for i in (0, self.n)
            )
        if type(ref) in (CaptureSource, TransitionSource):
            require(1 <= ref.ply <= self.n, "source ply outside line")
            delta = self.observed.structural.transitions[ref.ply - 1].board_delta
            require(
                (ref.before_position_id, ref.after_position_id)
                == (delta.before_position_id, delta.after_position_id),
                "step source anchor differs",
            )
            if type(ref) is CaptureSource:
                require(delta.capture is not None, "capture source has no capture")
                return delta.capture
            require(ref.subject in self.histories, "unknown transition subject")
            matches = tuple(
                t
                for t in delta.transitions
                if self.inverse[ref.ply - 1][t.before] == ref.subject
                and t.kind is ref.transition_kind
            )
            require(len(matches) == 1, "transition source does not resolve uniquely")
            return matches[0]
        i = ref.frame_index
        require(0 <= i <= self.n, "source frame outside line")
        frame = self.frames[i]
        require(ref.position_id == frame.activity.position_id, "frame source anchor differs")
        if type(ref) is SquareSource:
            return frame.activity.squares[square_index(ref.square)]
        if type(ref) is FileSource:
            return frame.structural.features.files[ord(ref.file) - ord("a")]
        if type(ref) is PinSource:
            bases = ref.pinner, ref.pinned, ref.king
            require(all(b in self.histories for b in bases), "unknown pin identity")
            require(
                ref.king.piece_type is PieceType.KING
                and ref.pinned.color is ref.king.color
                and ref.pinner.color is not ref.king.color
                and ref.pinned.piece_type is not PieceType.KING,
                "invalid pin identity roles",
            )
            require(
                any(p and p.piece_type in SLIDER_DIRECTIONS for p in self.histories[ref.pinner]),
                "pin pinner has no slider state",
            )
            return bases in self.pins[i]
        require(ref.subject in self.histories, "unknown source subject")
        piece = self.histories[ref.subject][i]
        if type(ref) is HistorySource:
            return piece if piece else Sentinel.CAPTURED
        if type(ref) is PawnSource:
            require(ref.subject.piece_type is PieceType.PAWN, "pawn source is not a physical pawn")
            return self.pawns[i].get(piece, Sentinel.NOT_APPLICABLE)
        if type(ref) is ActivitySource:
            return self.activities[i].get(piece, Sentinel.NOT_APPLICABLE)
        return self.rays[i].get((piece, ref.direction), Sentinel.NOT_APPLICABLE)


class _ExchangePolicy:
    def __init__(self, projection: _Projection, events):
        self.p = projection
        self.focus = projection.request.target.square
        captures = tuple(e for e in events if type(e[0]) is CaptureKey)
        self.focus_events = tuple(e for e in captures if e[1].landing_square == self.focus)
        self.participants = frozenset(
            b
            for key, c, _, _ in self.focus_events
            for b in (
                projection.inverse[key.ply - 1][c.capturer_before],
                projection.inverse[key.ply - 1][c.captured],
            )
        )

    def event_reasons(self, key, payload):
        if type(key) is CaptureKey:
            reasons = [SelectionReason.LINE_CONTEXT]
            if payload.landing_square == self.focus:
                reasons.append(SelectionReason.FOCUS_CAPTURE)
            if payload.captured_square == self.focus and payload.landing_square != self.focus:
                reasons.append(SelectionReason.FOCUS_VICTIM_SQUARE)
            return tuple(reasons)
        return (SelectionReason.PARTICIPANT,) if key.subject in self.participants else ()

    def reasons(self, key, a, b):
        if type(key) is SquareKey:
            return (SelectionReason.FOCUS_SQUARE,)
        if type(key) is PinKey:
            return (
                (SelectionReason.PARTICIPANT_PIN,)
                if self.participants.intersection((key.pinner, key.pinned, key.king))
                else ()
            )
        if type(key) is FileKey:
            reasons = []
            if key.file == self.focus[0]:
                reasons.append(SelectionReason.FOCUS_FILE)
            if any(
                piece and piece.piece_type is PieceType.PAWN and piece.square[0] == key.file
                for base in self.participants
                for piece in (self.p.histories[base][a], self.p.histories[base][b])
            ):
                reasons.append(SelectionReason.PARTICIPANT_FILE)
            return tuple(reasons)
        return (SelectionReason.PARTICIPANT,) if key.subject in self.participants else ()


def _project(request: ScenarioRequest, observed: ActivityLineAnalysis) -> ScenarioSummary:
    try:
        request.__post_init__()
        _validate_observed(request, observed)
        return _build(_Projection(request, observed))
    except InvalidScenarioSummaryError:
        raise
    except (CalliopeError, ValueError, TypeError, AttributeError, IndexError, KeyError) as exc:
        raise InvalidScenarioSummaryError(f"inconsistent retained observation: {exc}") from exc


def _build(p: _Projection) -> ScenarioSummary:
    raw_events = p.events()
    policy = _ExchangePolicy(p, raw_events)
    rows = {
        (bucket, family): [[], [], []]
        for bucket, families in (
            (Bucket.STEPS, CHANGED),
            (Bucket.ENDPOINTS, CHANGED),
            (Bucket.EVENTS, tuple(EventKind)),
            (Bucket.SNAPSHOTS, FOCUS),
            (Bucket.AGGREGATES, tuple(CountView)),
        )
        for family in families
    }

    def account(bucket, family, key, selected):
        row = rows[bucket, family]
        row[0].append(key)
        row[1 if selected else 2].append(key)

    events = []
    for key, payload, move, refs in raw_events:
        reasons = policy.event_reasons(key, payload)
        account(Bucket.EVENTS, key.family, key, reasons)
        if reasons:
            events.append(ScenarioEvent(key, payload, move, reasons, refs))
    timeline = []
    for frame in range(p.n + 1):
        facts = tuple(p.fact(SquareKey(family, policy.focus), frame) for family in FOCUS)
        for fact in facts:
            account(Bucket.SNAPSHOTS, fact.key.family, SnapshotKey(frame, fact.key), True)
        timeline.append(FocusSnapshot(frame, *facts))
    selected, endpoints, tracked = [], [], {}
    for bucket, pairs in (
        (Bucket.STEPS, tuple((i - 1, i) for i in range(1, p.n + 1))),
        (Bucket.ENDPOINTS, ((0, p.n),)),
    ):
        for a, b in pairs:
            for key in p.properties(a, b):
                before, after = p.fact(key, a), p.fact(key, b)
                if before.value == after.value:
                    continue
                reasons = policy.reasons(key, a, b)
                candidate = StepKey(b, key) if bucket is Bucket.STEPS else key
                account(bucket, key.family, candidate, reasons)
                if not reasons:
                    continue
                change = SelectedChange(key, before, after, reasons)
                (selected if bucket is Bucket.STEPS else endpoints).append(change)
                if bucket is Bucket.STEPS and key.family is not FactKind.PIECE_STATE:
                    tracked.setdefault(key, []).append(candidate)
    histories = []
    for key in sorted(tracked, key=_property_order):
        facts = tuple(p.fact(key, i) for i in range(p.n + 1))
        runs, start = [], 0
        for i in range(1, p.n + 2):
            if i == p.n + 1 or facts[i].value != facts[start].value:
                runs.append(HistoryRun(start, i - 1, facts[start:i]))
                start = i
        histories.append(FeatureHistory(key, tuple(runs), tuple(tracked[key])))
    materials = tuple(
        CountFact(
            CountKey(CountView.MATERIAL_COUNTS, m.color, m.piece_type),
            m.count_delta,
            (
                MaterialSource(
                    p.frames[0].activity.position_id,
                    p.frames[-1].activity.position_id,
                    m.color,
                    m.piece_type,
                ),
            ),
        )
        for m in p.observed.structural.material_changes
    )
    losses = []
    for color in Color:
        for kind in COUNTS:
            contributing = tuple(
                e
                for e in policy.focus_events
                if e[1].captured.color is color and e[1].captured.piece_type is kind
            )
            if contributing:
                losses.append(
                    CountFact(
                        CountKey(CountView.FOCUS_LOSSES, color, kind),
                        len(contributing),
                        _refs(*(e[3] for e in contributing)),
                    )
                )
    for count in (*materials, *losses):
        account(Bucket.AGGREGATES, count.key.family, count.key, True)
    temporary = sum(
        len(h.runs) > 1 and h.runs[0].facts[0].value == h.runs[-1].facts[-1].value
        for h in histories
    )
    focus_ids = tuple(e[0] for e in policy.focus_events)
    detail = ExchangeDetail(
        ExchangeStatus.FOCUS_CAPTURES_OBSERVED if focus_ids else ExchangeStatus.NO_FOCUS_CAPTURE,
        tuple(
            ParticipantSummary(b, tuple(p.history_ref(i, b) for i in range(p.n + 1)))
            for b in p.bases
            if b in policy.participants
        ),
        focus_ids,
        tuple(e.key for e in events if type(e.key) is CaptureKey and e.key not in focus_ids),
        materials,
        tuple(losses),
        temporary,
    )
    accounting = tuple(
        AccountingRow(
            bucket,
            family,
            tuple(candidates),
            tuple(included),
            tuple(ExcludedCandidate(key) for key in excluded),
        )
        for (bucket, family), (candidates, included, excluded) in rows.items()
    )
    return ScenarioSummary(
        p.request,
        p.observed,
        detail,
        tuple(events),
        tuple(timeline),
        tuple(selected),
        tuple(endpoints),
        tuple(histories),
        accounting,
    )


@dataclass(slots=True)
class ScenarioLineAnalyzer:
    activity_lines: ActivityLineAnalyzer

    def analyze(self, request: ScenarioRequest) -> ScenarioSummary:
        if type(request) is not ScenarioRequest:
            raise InvalidScenarioRequestError("expected ScenarioRequest")
        request.__post_init__()
        observed = self.activity_lines.analyze(
            request.initial, request.supplied_line, max_plies=request.max_plies
        )
        return _project(request, observed)


def _check_records(value):
    """Re-run local checks even if frozen records were illicitly edited after construction."""
    if isinstance(value, Record):
        value.__post_init__()
        for field in fields(value):
            _check_records(getattr(value, field.name))
    elif type(value) is tuple:
        for child in value:
            _check_records(child)


def validate_scenario_summary(summary: ScenarioSummary) -> None:
    require(type(summary) is ScenarioSummary, "expected ScenarioSummary")
    try:
        _check_records(summary)
        require(
            summary == _project(summary.request, summary.observed_line),
            "summary differs from exact scenario projection",
        )
    except InvalidScenarioSummaryError:
        raise
    except (CalliopeError, ValueError, TypeError, AttributeError, IndexError, KeyError) as exc:
        raise InvalidScenarioSummaryError(str(exc)) from exc


def resolve_source(summary: ScenarioSummary, ref: SourceRef):
    """Standalone reference resolution; rendering additionally validates full projection."""
    try:
        return _Projection(summary.request, summary.observed_line).resolve(ref)
    except InvalidScenarioSummaryError:
        raise
    except (ValueError, TypeError, AttributeError, IndexError, KeyError) as exc:
        raise InvalidScenarioSummaryError(str(exc)) from exc
