"""P8 bad-move cause rules over verified, deterministically replayed evidence.

Pure policy: no engine access and no rules-library access.  Inputs are the I3 counterfactual
context and the I4 replayed lines; the output is the internal P8 explanation result.  Material
values below are a fixed causal-verification metric, never an engine evaluation.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from calliope.domain.analysis import (
    BadMoveCauseKind,
    BadMoveCauseResult,
    BadMoveCauseStatus,
    BadMoveExplanationResult,
    BadMoveExplanationStatus,
    BasePieceRef,
    BoardDelta,
    MateEvidenceLevel,
    MaterialLineEvidence,
    PieceTransitionKind,
    TacticalCandidate,
    TacticalCandidateKind,
    TerminalKind,
)
from calliope.domain.chess import Color, PieceRef, PieceType, PositionFacts, square_index
from calliope.errors import IncompatibleBadMoveContextError
from calliope.services.explanation.piece_identity import BasePieceIdentityMap

if TYPE_CHECKING:
    from calliope.services.explanation.bad_move import (
        BadMoveCounterfactualContext,
        FirstMoveBranchContext,
        ReplayedLineContext,
        ReplayedLines,
        ReplayStepContext,
    )

PIECE_VALUES: dict[PieceType, int] = {
    PieceType.PAWN: 100,
    PieceType.KNIGHT: 320,
    PieceType.BISHOP: 330,
    PieceType.ROOK: 500,
    PieceType.QUEEN: 900,
}

_COUNT_FIELD = {
    PieceType.PAWN: "pawns",
    PieceType.KNIGHT: "knights",
    PieceType.BISHOP: "bishops",
    PieceType.ROOK: "rooks",
    PieceType.QUEEN: "queens",
}
_KIND_ORDER = {kind: index for index, kind in enumerate(BadMoveCauseKind)}

_S = BadMoveCauseStatus
_TK = TacticalCandidateKind

NormalizedPiece = tuple[BasePieceRef, PieceType]
Fingerprint = tuple[
    TacticalCandidateKind,
    tuple[NormalizedPiece, ...],
    tuple[NormalizedPiece, ...],
    tuple[NormalizedPiece, ...],
]


def _fail(message: str) -> IncompatibleBadMoveContextError:
    return IncompatibleBadMoveContextError(message)


def _base_key(base: BasePieceRef) -> tuple[int, str, str]:
    return (square_index(base.base_square), base.color.value, base.piece_type.value)


def _sorted_bases(bases: Iterable[BasePieceRef]) -> tuple[BasePieceRef, ...]:
    return tuple(sorted(set(bases), key=_base_key))


# ---- material ------------------------------------------------------------------------------


def piece_value(piece_type: PieceType) -> int:
    if piece_type is PieceType.KING:
        raise _fail("kings carry no material value")
    return PIECE_VALUES[piece_type]


def material_advantage(facts: PositionFacts, mover: Color) -> int:
    """Weighted material of ``mover`` minus the opponent's, from exact P4 counts."""

    def total(color: Color) -> int:
        counts = getattr(facts.material, color.value)
        return sum(
            getattr(counts, field) * PIECE_VALUES[kind] for kind, field in _COUNT_FIELD.items()
        )

    return total(mover) - total(mover.opposite)


def _traced_change(delta: BoardDelta, mover: Color) -> int:
    """Material-advantage change explained by the delta's exact capture/promotion events."""

    change = 0
    if delta.capture is not None:
        captured = delta.capture.captured
        value = piece_value(captured.piece_type)
        change += -value if captured.color is mover else value
    for transition in delta.transitions:
        if transition.kind is PieceTransitionKind.PROMOTION:
            gain = piece_value(transition.after.piece_type) - PIECE_VALUES[PieceType.PAWN]
            change += gain if transition.after.color is mover else -gain
    return change


def material_evidence(
    line: ReplayedLineContext, base_facts: PositionFacts, mover: Color
) -> MaterialLineEvidence:
    """Measure one replayed line relative to the base and decide its stable point.

    Plies: base = 0, first move = 1, first PV move = 2, ...  Stable when the line ends in exact
    checkmate, or when at least two further plies follow the last weighted-material change (or
    the first move, if nothing changed).  A stalemate ending must come after that point.
    """

    base_advantage = material_advantage(base_facts, mover)
    previous = base_advantage
    last_change: int | None = None
    for step in line.plies:
        current = material_advantage(step.facts, mover)
        if current - previous != _traced_change(step.delta, mover):
            raise _fail("weighted material change is not traced by exact capture/promotion")
        if current != previous:
            last_change = step.ply
        previous = current

    material_delta = previous - base_advantage
    final_ply = line.final.ply
    if line.ends_in_checkmate:
        return MaterialLineEvidence(line.probe_result.probe, material_delta, final_ply, True)

    reference = last_change if last_change is not None else line.plies[0].ply
    stable_at = reference + 2
    stable = stable_at < final_ply if line.ends_in_stalemate else stable_at <= final_ply
    return MaterialLineEvidence(
        line.probe_result.probe, material_delta, stable_at if stable else None
    )


# ---- tactical normalization ------------------------------------------------------------------


def _sort_normalized(pieces: Iterable[NormalizedPiece]) -> tuple[NormalizedPiece, ...]:
    return tuple(sorted(set(pieces), key=lambda item: (*_base_key(item[0]), item[1].value)))


def normalize_piece(
    piece: PieceRef,
    identity: BasePieceIdentityMap,
    *,
    before_identity: BasePieceIdentityMap | None = None,
    captured: PieceRef | None = None,
) -> NormalizedPiece:
    """Base identity plus current role of one piece at the candidate's position.

    Only the piece captured by the candidate's own move may be resolved in the position before
    that move (as P6 reports for REMOVAL_OF_DEFENDER).  Nothing is guessed from square or type.
    """

    if piece in identity.live_pieces:
        return (identity.base_ref_for(piece), piece.piece_type)
    if before_identity is not None and captured is not None and piece == captured:
        return (before_identity.base_ref_for(piece), piece.piece_type)
    raise _fail("tactical candidate references a piece outside the branch identity")


def fingerprint(
    candidate: TacticalCandidate,
    identity: BasePieceIdentityMap,
    *,
    before_identity: BasePieceIdentityMap | None = None,
    captured: PieceRef | None = None,
) -> Fingerprint:
    """Base-normalized semantic fingerprint; position-dependent response UCI is excluded.

    Every piece resolves in the candidate's own position, except the captured defender that
    P6 records as ``related`` on REMOVAL_OF_DEFENDER, which no longer exists there.
    """

    def group(
        pieces: tuple[PieceRef, ...], *, allow_captured: bool = False
    ) -> tuple[NormalizedPiece, ...]:
        return _sort_normalized(
            normalize_piece(
                p,
                identity,
                before_identity=before_identity if allow_captured else None,
                captured=captured if allow_captured else None,
            )
            for p in pieces
        )

    removal = candidate.kind is _TK.REMOVAL_OF_DEFENDER
    return (
        candidate.kind,
        group(candidate.actors),
        group(candidate.targets),
        group(candidate.related, allow_captured=removal),
    )


def _step_fingerprint(candidate: TacticalCandidate, step: ReplayStepContext) -> Fingerprint:
    capture = step.delta.capture
    return fingerprint(
        candidate,
        step.identity,
        before_identity=step.before_identity,
        captured=capture.captured if capture is not None else None,
    )


# ---- shared line checks ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Evidence:
    context: BadMoveCounterfactualContext
    lines: ReplayedLines
    actual: MaterialLineEvidence
    comparator: MaterialLineEvidence
    same_punishment: MaterialLineEvidence | None
    mover: Color

    @property
    def materials(self) -> tuple[MaterialLineEvidence, ...]:
        found = (self.actual, self.comparator, self.same_punishment)
        return tuple(m for m in found if m is not None)

    def comparator_lines(self) -> tuple[tuple[ReplayedLineContext, MaterialLineEvidence], ...]:
        pairs = [(self.lines.comparator, self.comparator)]
        if self.lines.same_punishment is not None:
            assert self.same_punishment is not None
            pairs.append((self.lines.same_punishment, self.same_punishment))
        return tuple(pairs)


def _captures(
    line: ReplayedLineContext, subject: BasePieceRef, after_ply: int = 0
) -> tuple[ReplayStepContext, ...]:
    """Replay steps whose exact CaptureDelta removes the physical ``subject``."""

    found = []
    for step in line.plies:
        capture = step.delta.capture
        if step.ply <= after_ply or capture is None:
            continue
        if step.before_identity.base_ref_for(capture.captured) == subject:
            found.append(step)
    return tuple(found)


def _exploits(
    line: ReplayedLineContext, material: MaterialLineEvidence, subject: BasePieceRef
) -> bool | None:
    """True: subject captured and stable mover deficit; False: completed without; None: open."""

    if _captures(line, subject) and material.stable_deficit is not None:
        return True
    if material.stable_at_ply is None:
        return None
    return False


def _mates_mover(line: ReplayedLineContext, mover: Color) -> bool:
    if line.ends_in_checkmate and line.final.position.side_to_move is mover:
        return True
    analysis = line.probe_result.engine_analysis
    if analysis is None:
        return False
    mate = analysis.best_line.score.mate
    return mate is not None and mate.winner is not mover


def _decide(
    actual: bool | None, comparator: Iterable[bool | None]
) -> tuple[BadMoveCauseStatus, bool | None]:
    """D1: REFUTED/SUPPORTED only from completed checks; anything open is INCONCLUSIVE."""

    checks = tuple(comparator)
    if any(check is True for check in checks):
        equivalent: bool | None = True
    elif any(check is None for check in checks):
        equivalent = None
    else:
        equivalent = False

    if actual is None:
        return _S.INCONCLUSIVE, equivalent
    if actual is False or equivalent is True:
        return _S.REFUTED, equivalent
    if equivalent is None:
        return _S.INCONCLUSIVE, equivalent
    return _S.SUPPORTED, equivalent


def _cause(
    ev: _Evidence,
    kind: BadMoveCauseKind,
    status: BadMoveCauseStatus,
    subject: Iterable[BasePieceRef],
    equivalent: bool | None,
    *,
    affected: Iterable[BasePieceRef] = (),
    deltas: Iterable[BoardDelta] = (),
    candidates: Iterable[TacticalCandidate] = (),
    material: tuple[MaterialLineEvidence, ...] = (),
    mate_level: MateEvidenceLevel | None = None,
    pv_mate: bool | None = None,
) -> BadMoveCauseResult:
    context = ev.context
    prepared = context.prepared
    probes = (context.actual_refutation, context.comparator_refutation, context.comparator_replay)
    return BadMoveCauseResult(
        kind=kind,
        status=status,
        subject=_sorted_bases(subject),
        base_position_id=prepared.base.position_id,
        played_move=prepared.played_move,
        comparator_move=prepared.comparator_move,
        punishment_move=context.punishment_move,
        affected_pieces=_sorted_bases(affected),
        board_deltas=tuple(dict.fromkeys(deltas)),
        tactical_candidates=tuple(dict.fromkeys(candidates)),
        probe_results=tuple(p for p in probes if p is not None),
        material_evidence=material,
        same_punishment_legal_after_comparator=context.same_punishment_legal_after_comparator,
        comparator_has_equivalent_resource=equivalent,
        mate_evidence_level=mate_level,
        replayed_pv_ends_in_checkmate=pv_mate,
    )


# ---- NEWLY_HANGING_PIECE ---------------------------------------------------------------------


def _already_exposed(base_facts: PositionFacts, subject: BasePieceRef, mover: Color) -> bool:
    piece = PieceRef(subject.color, subject.piece_type, subject.base_square)
    state = next((s for s in base_facts.pieces if s.piece == piece), None)
    if state is None:
        raise _fail("hanging subject is missing from the base facts")
    attacked = any(a.color is not mover for a in state.attacked_by)
    defended = any(d.color is mover for d in state.defended_by)
    return attacked and not defended


def _newly_hanging(ev: _Evidence) -> list[BadMoveCauseResult]:
    first = ev.lines.actual.plies[0]
    groups: dict[BasePieceRef, list[TacticalCandidate]] = {}
    for candidate in first.detection.candidates:
        if candidate.kind is not _TK.HANGING_PIECE or candidate.targets[0].color is not ev.mover:
            continue
        subject = first.identity.base_ref_for(candidate.targets[0])
        if _already_exposed(ev.context.prepared.base_facts, subject, ev.mover):
            continue
        groups.setdefault(subject, []).append(candidate)

    causes = []
    for subject, candidates in groups.items():
        # Exposure of the same physical piece anywhere on the comparator's own refutation
        # (immediately after A or at any later replayed ply), whoever attacks it.  The
        # same-punishment line counts only through exploitation, below.
        exposure = [
            c
            for step in ev.lines.comparator.plies
            for c in step.detection.candidates
            if c.kind is _TK.HANGING_PIECE and step.identity.base_ref_for(c.targets[0]) == subject
        ]
        checks = [bool(exposure)] + [
            _exploits(line, material, subject) for line, material in ev.comparator_lines()
        ]
        status, equivalent = _decide(_exploits(ev.lines.actual, ev.actual, subject), checks)
        captures = _captures(ev.lines.actual, subject)
        causes.append(
            _cause(
                ev,
                BadMoveCauseKind.NEWLY_HANGING_PIECE,
                status,
                (subject,),
                equivalent,
                deltas=[first.delta, *(s.delta for s in captures)],
                candidates=[*candidates, *exposure],
                material=ev.materials,
            )
        )
    return causes


# ---- REMOVED_DEFENDER ------------------------------------------------------------------------


def _own_removed_defenses(
    branch_first: ReplayStepContext, mover: Color
) -> dict[BasePieceRef, list[BasePieceRef]]:
    """Defended base subject -> removed own defenders, excluding the moved piece itself."""

    moved_from = branch_first.move.uci[:2]
    groups: dict[BasePieceRef, list[BasePieceRef]] = {}
    for change in branch_first.delta.removed_defenses:
        defender, defended = change.defender, change.defended
        if defender.color is not mover or defended.color is not mover:
            continue
        if defended.piece_type is PieceType.KING or defended.square == moved_from:
            continue
        subject = branch_first.before_identity.base_ref_for(defended)
        groups.setdefault(subject, []).append(branch_first.before_identity.base_ref_for(defender))
    return groups


def _removed_defender(ev: _Evidence) -> list[BadMoveCauseResult]:
    first = ev.lines.actual.plies[0]
    comparator_removed = _own_removed_defenses(ev.lines.comparator.plies[0], ev.mover)

    causes = []
    for subject, defenders in _own_removed_defenses(first, ev.mover).items():
        corroborating = [
            candidate
            for step in ev.lines.actual.plies[1:]
            for candidate in step.detection.candidates
            if candidate.kind is _TK.REMOVAL_OF_DEFENDER
            and candidate.targets[0].color is ev.mover
            and step.identity.base_ref_for(candidate.targets[0]) == subject
        ]
        checks = [subject in comparator_removed] + [
            _exploits(line, material, subject) for line, material in ev.comparator_lines()
        ]
        status, equivalent = _decide(_exploits(ev.lines.actual, ev.actual, subject), checks)
        captures = _captures(ev.lines.actual, subject)
        causes.append(
            _cause(
                ev,
                BadMoveCauseKind.REMOVED_DEFENDER,
                status,
                (subject,),
                equivalent,
                affected=defenders,
                deltas=[first.delta, *(s.delta for s in captures)],
                candidates=corroborating,
                material=ev.materials,
            )
        )
    return causes


# ---- FORK_ALLOWED ----------------------------------------------------------------------------


def _fork_print(
    candidate: TacticalCandidate, step: ReplayStepContext
) -> tuple[NormalizedPiece, tuple[NormalizedPiece, ...]]:
    _, actors, targets, _ = _step_fingerprint(candidate, step)
    return (actors[0], targets)


def _fork_consequence(
    line: ReplayedLineContext,
    material: MaterialLineEvidence,
    fork_ply: int,
    targets: Iterable[BasePieceRef],
    mover: Color,
) -> bool | None:
    targets = tuple(targets)
    if any(t.piece_type is PieceType.KING and t.color is mover for t in targets) and _mates_mover(
        line, mover
    ):
        return True
    captured = any(
        _captures(line, t, fork_ply) for t in targets if t.piece_type is not PieceType.KING
    )
    if captured and material.stable_deficit is not None:
        return True
    if material.stable_at_ply is None:
        return None
    return False


def _comparator_fork(
    line: ReplayedLineContext,
    material: MaterialLineEvidence,
    prints: set,
    targets: tuple[BasePieceRef, ...],
    mover: Color,
) -> bool | None:
    matches = [
        step.ply
        for step in line.plies
        for candidate in step.detection.candidates
        if candidate.kind is _TK.FORK and _fork_print(candidate, step) in prints
    ]
    if not matches:
        return False if material.stable_at_ply is not None else None
    return _fork_consequence(line, material, min(matches), targets, mover)


def _fork_allowed(ev: _Evidence) -> list[BadMoveCauseResult]:
    groups: dict[tuple[BasePieceRef, ...], dict] = {}
    for step in ev.lines.actual.plies[1:]:
        for candidate in step.detection.candidates:
            if candidate.kind is not _TK.FORK or candidate.actors[0].color is ev.mover:
                continue
            actor, targets = _fork_print(candidate, step)
            subject = _sorted_bases([actor[0], *(t[0] for t in targets)])
            group = groups.setdefault(
                subject,
                {"ply": step.ply, "prints": set(), "targets": set(), "candidates": []},
            )
            group["prints"].add((actor, targets))
            group["targets"].update(t[0] for t in targets)
            group["candidates"].append(candidate)

    causes = []
    for subject, group in groups.items():
        targets = _sorted_bases(group["targets"])
        actual = _fork_consequence(ev.lines.actual, ev.actual, group["ply"], targets, ev.mover)
        checks = [
            _comparator_fork(line, material, group["prints"], targets, ev.mover)
            for line, material in ev.comparator_lines()
        ]
        status, equivalent = _decide(actual, checks)
        causes.append(
            _cause(
                ev,
                BadMoveCauseKind.FORK_ALLOWED,
                status,
                subject,
                equivalent,
                deltas=[s.delta for s in ev.lines.actual.plies[1:] if s.ply >= group["ply"]],
                candidates=group["candidates"],
                material=ev.materials,
            )
        )
    return causes


# ---- MATE_ALLOWED ----------------------------------------------------------------------------


def _mate_allowed(
    ev: _Evidence, mates_in_one: Callable[[FirstMoveBranchContext], bool]
) -> list[BadMoveCauseResult]:
    context = ev.context
    prepared = context.prepared
    opponent = ev.mover.opposite
    king = next(
        (
            base
            for base in prepared.root_identity.base_pieces
            if base.color is ev.mover and base.piece_type is PieceType.KING
        ),
        None,
    )
    if king is None:
        raise _fail("mover king is missing from the base identity")

    punishment = context.actual_punishment
    if punishment is not None and punishment.facts.side_to_move_checkmated:
        equivalent = mates_in_one(prepared.comparator)
        mate_candidates = [c for c in punishment.detection.candidates if c.kind is _TK.CHECKMATE]
        return [
            _cause(
                ev,
                BadMoveCauseKind.MATE_ALLOWED,
                _S.REFUTED if equivalent else _S.SUPPORTED,
                (king,),
                equivalent,
                deltas=[punishment.delta],
                candidates=mate_candidates,
                mate_level=MateEvidenceLevel.EXACT_IMMEDIATE,
                pv_mate=True,
            )
        ]

    def mate_against_mover(analysis_score) -> bool:
        return analysis_score.mate is not None and analysis_score.mate.winner is opponent

    actual_analysis = context.actual_refutation.engine_analysis
    if actual_analysis is None or not mate_against_mover(actual_analysis.best_line.score):
        return []

    # Mate against the mover on a comparator line: a terminal checkmate, an engine mate score,
    # or an exact checkmate at the end of the deterministic replay (board truth wins).
    comparator = context.comparator_refutation
    comparator_mates = (
        comparator.terminal is not None
        and comparator.terminal.kind is TerminalKind.CHECKMATE
        and comparator.terminal.winner is opponent
    ) or _mates_mover(ev.lines.comparator, ev.mover)
    same = ev.lines.same_punishment
    same_mates = same is not None and _mates_mover(same, ev.mover)
    equivalent = comparator_mates or same_mates
    final = ev.lines.actual.final
    return [
        _cause(
            ev,
            BadMoveCauseKind.MATE_ALLOWED,
            _S.REFUTED if equivalent else _S.SUPPORTED,
            (king,),
            equivalent,
            deltas=[step.delta for step in ev.lines.actual.plies[1:]],
            mate_level=MateEvidenceLevel.ENGINE_LINE,
            pv_mate=ev.lines.actual.ends_in_checkmate and final.position.side_to_move is ev.mover,
        )
    ]


# ---- MATERIAL_LOSS_LINE ----------------------------------------------------------------------


def _value_equivalent(material: MaterialLineEvidence, actual_deficit: int) -> bool | None:
    if material.stable_at_ply is None:
        return None
    return material.stable_deficit is not None and material.stable_deficit >= actual_deficit


def _material_loss_line(ev: _Evidence) -> list[BadMoveCauseResult]:
    subject: list[BasePieceRef] = []
    event_deltas: list[BoardDelta] = []
    for step in ev.lines.actual.plies:
        capture = step.delta.capture
        changed = False
        if capture is not None and capture.captured.color is ev.mover:
            subject.append(step.before_identity.base_ref_for(capture.captured))
            changed = True
        for transition in step.delta.transitions:
            if transition.kind is PieceTransitionKind.PROMOTION:
                subject.append(step.before_identity.base_ref_for(transition.before))
                changed = True
        if changed:
            event_deltas.append(step.delta)
    if not subject:
        return []

    if ev.actual.stable_at_ply is None:
        actual: bool | None = None
        checks: list[bool | None] = []
    elif ev.actual.stable_deficit is None:
        actual, checks = False, []
    else:
        actual = True
        checks = [_value_equivalent(m, ev.actual.stable_deficit) for _, m in ev.comparator_lines()]
    status, equivalent = _decide(actual, checks)
    if actual is not True:
        equivalent = None
    return [
        _cause(
            ev,
            BadMoveCauseKind.MATERIAL_LOSS_LINE,
            status,
            subject,
            equivalent,
            deltas=event_deltas,
            material=ev.materials,
        )
    ]


# ---- result policy ---------------------------------------------------------------------------


def _cause_key(cause: BadMoveCauseResult) -> tuple[int, tuple[int, ...]]:
    return (_KIND_ORDER[cause.kind], tuple(square_index(s.base_square) for s in cause.subject))


def aggregate_status(causes: tuple[BadMoveCauseResult, ...]) -> BadMoveExplanationStatus:
    statuses = [cause.status for cause in causes]
    if _S.SUPPORTED in statuses:
        return BadMoveExplanationStatus.SUPPORTED
    if statuses and all(status is _S.REFUTED for status in statuses):
        return BadMoveExplanationStatus.REFUTED
    return BadMoveExplanationStatus.INCONCLUSIVE


def evaluate_bad_move_causes(
    context: BadMoveCounterfactualContext,
    lines: ReplayedLines,
    mates_in_one: Callable[[FirstMoveBranchContext], bool],
) -> BadMoveExplanationResult:
    """Apply the frozen P8 rules to validated evidence; performs no engine work."""

    prepared = context.prepared
    mover = prepared.base.side_to_move
    base_facts = prepared.base_facts

    # Validation first: material tracing failures are errors whatever the score gate says.
    same = lines.same_punishment
    ev = _Evidence(
        context=context,
        lines=lines,
        actual=material_evidence(lines.actual, base_facts, mover),
        comparator=material_evidence(lines.comparator, base_facts, mover),
        same_punishment=material_evidence(same, base_facts, mover) if same is not None else None,
        mover=mover,
    )

    def result(
        status: BadMoveExplanationStatus, causes: tuple[BadMoveCauseResult, ...] = ()
    ) -> BadMoveExplanationResult:
        return BadMoveExplanationResult(
            status=status,
            base_position_id=prepared.base.position_id,
            played_move=prepared.played_move,
            comparator_move=prepared.comparator_move,
            causes=causes,
        )

    if context.comparator_strictly_better is not True:
        return result(BadMoveExplanationStatus.INCONCLUSIVE)

    causes = tuple(
        sorted(
            [
                *_newly_hanging(ev),
                *_removed_defender(ev),
                *_fork_allowed(ev),
                *_mate_allowed(ev, mates_in_one),
                *_material_loss_line(ev),
            ],
            key=_cause_key,
        )
    )
    return result(aggregate_status(causes), causes)
