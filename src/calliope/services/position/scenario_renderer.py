"""Closed English templates over validated internal facts, without adapter work."""

from calliope.domain.analysis.scenario import (
    CaptureKey,
    CountView,
    EventKind,
    Fact,
    FactKind,
    PhysicalPiece,
    RenderedFactSentence,
    RenderedScenarioReport,
    ScenarioKind,
    ScenarioSummary,
    SelectionReason,
    Sentinel,
    TemplateId,
    require,
)
from calliope.domain.chess import Color, PieceType
from calliope.services.position.scenario import _Projection, _refs, validate_scenario_summary


def _piece(piece):
    return f"{piece.color.value} {piece.piece_type.value} on {piece.square}"


def _piece_type(piece):
    return f"{piece.color.value} {piece.piece_type.value}"


def _physical(piece: PhysicalPiece):
    return f"{_piece(piece.current)} (initially on {piece.base.base_square})"


def _list(values):
    return ", ".join(values) if values else "none"


def _sentence(template, text, refs):
    return RenderedFactSentence(template, text, tuple(dict.fromkeys(refs)))


def _fact(fact: Fact, context: str, refs=None):
    """Only internal typed-value branches supply placeholders; no free-text input API."""
    key, value = fact.key, fact.value
    family = key.family
    template = (
        TemplateId(family.value)
        if family is not FactKind.PIN_PRESENT
        else (TemplateId.PIN_PRESENT_TRUE if value else TemplateId.PIN_PRESENT_FALSE)
    )
    if family is FactKind.PIECE_STATE:
        body = f"the piece initially on {key.subject.base_square} is {('captured' if value is Sentinel.CAPTURED else _piece(value))}"
    elif family is FactKind.FOCUS_OCCUPANT:
        occupant = (
            "empty"
            if value is Sentinel.EMPTY
            else f"occupied by {value.current.color.value} {value.current.piece_type.value} initially on {value.base.base_square}"
        )
        body = f"{key.square} is {occupant}"
    elif family is FactKind.FOCUS_ATTACKERS:
        return tuple(
            _sentence(
                template,
                f"{context}, the {color} geometric attackers of {key.square} are {_list(tuple(_physical(p) for p in pieces))}.",
                refs or fact.source_refs,
            )
            for color, pieces in (("white", value.white), ("black", value.black))
        )
    elif family is FactKind.FOCUS_LEGAL_CAPTURES_NOW:
        body = f"the side to move is {value.side_to_move.value}; its current legal captures landing on {key.square} are {_list(tuple(c.move.uci for c in value.captures))}"
    elif family is FactKind.PAWN_FLAGS:
        body = f"the pawn initially on {key.subject.base_square} " + (
            "has pawn structure not applicable"
            if value is Sentinel.NOT_APPLICABLE
            else f"has isolated={str(value.isolated).lower()}, doubled={str(value.doubled).lower()}, passed={str(value.passed).lower()}"
        )
    elif family is FactKind.PAWN_SUPPORTERS:
        body = (
            f"geometric pawn supporters of the pawn initially on {key.subject.base_square} are "
            + (
                "not applicable"
                if value is Sentinel.NOT_APPLICABLE
                else _list(tuple(b.base_square for b in value.bases))
            )
        )
    elif family is FactKind.FILE_STATE:
        state = (
            "open"
            if value.open
            else (
                "semi-open for white"
                if value.semi_open_for(Color.WHITE)
                else ("semi-open for black" if value.semi_open_for(Color.BLACK) else "neither")
            )
        )
        body = f"file {key.file} contains {value.white_pawns} white pawn(s) and {value.black_pawns} black pawn(s); its derived state is {state}"
    elif family is FactKind.ATTACK_FOOTPRINT:
        body = (
            f"the geometric target squares of the piece initially on {key.subject.base_square} are "
            + ("not applicable" if value is Sentinel.NOT_APPLICABLE else _list(value.squares))
        )
    elif family is FactKind.ATTACK_PARTITION:
        body = f"geometric targets of the piece initially on {key.subject.base_square} are " + (
            "not applicable"
            if value is Sentinel.NOT_APPLICABLE
            else f"empty={_list(value.empty)}, friendly={_list(value.friendly)}, enemy={_list(value.enemy)}"
        )
    elif family is FactKind.RAY_STATE:
        body = f"the piece initially on {key.subject.base_square}'s ray {key.direction} " + (
            "is not applicable"
            if value is Sentinel.NOT_APPLICABLE
            else f"has visible squares {_list(value.ray.visible_squares)} and occupants {_list(tuple(_physical(p) for p in value.occupants))}"
        )
    else:
        triple = key.pinner.base_square, key.pinned.base_square, key.king.base_square
        if value:
            body = "an absolute pin is observed with " + ", ".join(
                f"{role}=piece initially on {b.base_square}"
                for role, b in zip(("pinner", "pinned", "king"), (key.pinner, key.pinned, key.king))
            )
        else:
            body = f"the absolute pin keyed by initial squares {_list(triple)} is not observed"
    return (_sentence(template, f"{context}, {body}.", refs or fact.source_refs),)


def _context(frame):
    return (
        "In the supplied line, at the initial frame"
        if frame == 0
        else f"In the supplied line, after ply {frame}"
    )


def _event(event):
    p, payload = event.key.ply, event.payload
    if type(event.key) is CaptureKey:
        if payload.is_en_passant:
            template = TemplateId.CAPTURE_EP
            text = f"In the supplied line, at ply {p}, {_piece(payload.capturer_before)} captures en passant, landing on {payload.landing_square} and removing {_piece(payload.captured)} from {payload.captured_square}."
        else:
            template = TemplateId.CAPTURE_NORMAL
            text = f"In the supplied line, at ply {p}, {_piece(payload.capturer_before)} captures {_piece_type(payload.captured)} on {payload.landing_square}."
    else:
        template = TemplateId(event.key.family.value)
        base = event.key.subject.base_square
        prefix = f"In the supplied line, at ply {p}, "
        if event.key.family is EventKind.CASTLING_ROOK:
            text = (
                prefix
                + f"move {event.move.uci} is castling; the participant rook initially on {base} moves from {payload.before.square} to {payload.after.square}."
            )
        elif event.key.family is EventKind.PROMOTION:
            text = (
                prefix
                + f"the piece initially on {base} moves from {payload.before.square} to {payload.after.square} and promotes to {payload.after.piece_type.value}."
            )
        elif payload.before.piece_type is PieceType.KING and event.move.uci in (
            "e1g1",
            "e1c1",
            "e8g8",
            "e8c8",
        ):
            text = (
                prefix
                + f"move {event.move.uci} is castling; the participant king initially on {base} moves from {payload.before.square} to {payload.after.square}."
            )
        else:
            text = (
                prefix
                + f"the piece initially on {base} moves from {payload.before.square} to {payload.after.square}."
            )
    return _sentence(template, text, event.source_refs)


def _count(count, focus):
    color, kind = count.key.color.value, count.key.piece_type.value
    if count.key.family is CountView.MATERIAL_COUNTS:
        template = TemplateId.MATERIAL_COUNTS
        text = f"In the supplied line, at the supplied endpoint, the {color} {kind} count changes by {count.count:+d} relative to the initial frame."
    else:
        template = TemplateId.FOCUS_LOSSES
        text = f"In the supplied line, captures landing on {focus} remove {count.count} {color} {kind} piece(s)."
    return _sentence(template, text, count.source_refs)


class ScenarioSummaryRenderer:
    def render(self, summary: ScenarioSummary) -> RenderedScenarioReport:
        validate_scenario_summary(summary)
        if summary.request.kind is ScenarioKind.PLAYED_TRANSITION:
            # Deferred import: the compact ledger module reuses this module's event templates.
            from calliope.services.position.scenario_observation import _render_played

            return _render_played(summary)
        p = _Projection(summary.request, summary.observed_line)
        focus, detail = summary.request.target.square, summary.detail
        capture_events = tuple(e for e in summary.events if type(e.key) is CaptureKey)
        status_refs = _refs(
            *(s.occupant.source_refs for s in summary.focus_timeline),
            *(e.source_refs for e in capture_events),
        )
        count = len(detail.focus_capture_events)
        status = _sentence(
            TemplateId.STATUS_OBSERVED if count else TemplateId.STATUS_NONE,
            f"In the supplied line, {count} capture(s) land on {focus}."
            if count
            else f"In the supplied line, no capture lands on {focus}.",
            status_refs,
        )
        digest = [status]
        digest.extend(
            _event(e)
            for e in summary.events
            if e.key.family is EventKind.PROMOTION
            or SelectionReason.FOCUS_CAPTURE in e.reasons
            or SelectionReason.FOCUS_VICTIM_SQUARE in e.reasons
        )
        digest.extend(
            _count(c, focus)
            for c in (*detail.whole_line_material_changes, *detail.focus_capture_losses)
        )
        for change in summary.endpoint_changes:
            digest.extend(_fact(change.before, _context(0)))
            digest.extend(_fact(change.after, "In the supplied line, at the supplied endpoint"))
        track_refs = _refs(
            status_refs,
            *(
                fact.source_refs
                for h in summary.feature_histories
                for run in h.runs
                for fact in run.facts
            ),
        )
        digest.append(
            _sentence(
                TemplateId.TEMPORARY_COUNT,
                f"In the supplied line, {detail.temporary_track_count} selected feature track(s) differ in intermediate frames and return to their initial value at the supplied endpoint.",
                track_refs,
            )
        )
        sentences = [_event(e) for e in summary.events]
        for snapshot in summary.focus_timeline:
            for fact in (snapshot.occupant, snapshot.attackers, snapshot.legal_captures):
                sentences.extend(_fact(fact, _context(snapshot.frame)))
        for change in summary.selected_changes:
            for fact in (change.before, change.after):
                sentences.extend(_fact(fact, _context(fact.frame)))
        for history in summary.feature_histories:
            for run in history.runs:
                refs = _refs(*(fact.source_refs for fact in run.facts))
                sentences.extend(
                    _fact(
                        run.facts[0],
                        f"In the supplied line, from frame {run.start} through frame {run.end}",
                        refs,
                    )
                )
        report = RenderedScenarioReport(tuple(digest), tuple(sentences))
        for sentence in (*report.digest, *report.detail):
            for ref in sentence.source_refs:
                p.resolve(ref)
        return report


def validate_rendered_report(summary: ScenarioSummary, report: RenderedScenarioReport) -> None:
    """A caller-held report is accepted only if it equals a fresh validated rendering."""
    require(
        type(report) is RenderedScenarioReport
        and report == ScenarioSummaryRenderer().render(summary),
        "rendered report differs from recomputation",
    )
