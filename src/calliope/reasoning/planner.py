"""The explanation plan, `selection_v1` (R0-D §12, R3-D §1).

The plan picks, for one target move, at most one claim per role and the label's grounds, from the
final claims and the claim graph. It reads claims, relations, judgements and labels; it never reads
the fact tree, so selection cannot depend on wording. Claim ids break every tie.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from calliope.reasoning.graph import ClaimRelation
from calliope.reasoning.hypotheses import ClaimRole, RelationKind
from calliope.reasoning.labels import Label, LabelKind
from calliope.reasoning.observer import Judgement, JudgementRef, JudgementStatus
from calliope.reasoning.refs import LineSegment, MoveSubject, ScopeRef
from calliope.reasoning.verification import Claim, VerdictStatus

SELECTION_V1 = "selection_v1"

# R3-D §1: the priority tables of `selection_v1` (policy constants, R0-D §12.2)
EXACT_CONSEQUENCES = ("mate_delivered_v1", "mate_in_one_allowed_v1")  # rule 1
EXACT_FUNCTIONS = ("forcing_v1",)
MATES = ("mate_delivered_v1", "mate_found_v1", "mate_in_one_allowed_v1", "mate_allowed_v1")
MATERIAL = ("material_loss_v1", "material_gain_v1")
MECHANISMS = (
    "fork_v1",
    "skewer_v1",
    "pin_v1",
    "discovery_v1",
    "newly_unsafe_v1",
    "left_en_prise_v1",
    "removed_defender_v1",
)
SACRIFICES = ("sacrifice_compensated_v1", "sacrifice_sound_v1")
FUNCTIONS = ("only_move_v1", "prevents_v1", *SACRIFICES, "rescue_v1", "forcing_v1")
COMPARISONS = ("mate_missed_v1", "better_move_v1", "missed_gain_v1")
WITH_LINE = ("mate_missed_v1", "better_move_v1")  # their first operand is the best line's window
PENDING_ROLES = (
    ClaimRole.CONSEQUENCE,
    ClaimRole.MECHANISM,
    ClaimRole.FUNCTION,
    ClaimRole.COMPARISON,
)
MAX_PENDING = 2


@dataclass(frozen=True, slots=True)
class ExplanationPlan:
    """R0-D §12.1 as refined by R3-D §1. `purpose` holds one function claim; a lead is derived
    from that claim's premises by the renderer, never stored (R3-D review B6)."""

    subject: MoveSubject
    judgement: JudgementRef
    label: Label | None
    purpose: tuple[str, ...]  # FUNCTION: 0–1
    mechanism: tuple[str, ...]  # MECHANISM: 0–1, with EXPLAINS to the consequence
    consequence: tuple[str, ...]  # CONSEQUENCE: 0–1
    justification: tuple[str | LineSegment, ...]  # COMPARISON: 0–1, then its best line
    qualification: tuple[str | ScopeRef, ...]  # scopes of the selected claims, then ≤ 2 pending
    policy: str = SELECTION_V1


def plan_digest(plan: ExplanationPlan) -> str:
    """sha256 of the plan's canonical encoding (R3-D §1)."""

    from calliope.reasoning.encoding import canonical_bytes

    return hashlib.sha256(canonical_bytes(plan)).hexdigest()


def _supported(claims: dict[str, Claim], template: str, subject: MoveSubject) -> list[Claim]:
    return sorted(
        (
            c
            for c in claims.values()
            if c.hypothesis.template == template and c.supported and c.hypothesis.subject == subject
        ),
        key=lambda c: c.id,
    )


def _first(claims: dict[str, Claim], order: tuple[str, ...], subject: MoveSubject) -> Claim | None:
    for template in order:
        found = _supported(claims, template, subject)
        if found:
            return found[0]
    return None


def _exact(claim: Claim) -> bool:
    return claim.verdict.scope is not None and claim.verdict.scope.basis.value == "exact"


def _material(claim: Claim) -> int:
    from calliope.reasoning.findings import MaterialFinding

    found = next((f for f in claim.verdict.findings if isinstance(f, MaterialFinding)), None)
    return found.amount.points if found is not None else 0


def _consequence(claims: dict[str, Claim], subject: MoveSubject) -> Claim | None:
    """Rule 3: mates in order, then material by the larger amount, then id."""

    mate = _first(claims, MATES, subject)
    if mate is not None:
        return mate
    material = [c for t in MATERIAL for c in _supported(claims, t, subject)]
    return min(material, key=lambda c: (-_material(c), c.id), default=None)


def _mechanism(
    claims: dict[str, Claim],
    relations: tuple[ClaimRelation, ...],
    consequence: Claim | None,
    ply_of,
) -> Claim | None:
    """Rule 4: an EXPLAINS edge into the consequence; template order, the earliest node, id."""

    if consequence is None:
        return None
    sources = {
        r.source
        for r in relations
        if r.target == consequence.id and r.kind is RelationKind.EXPLAINS
    }
    candidates = [
        claims[s] for s in sources if s in claims and claims[s].supported
        and claims[s].hypothesis.template in MECHANISMS
    ]  # fmt: skip
    return min(
        candidates,
        key=lambda c: (MECHANISMS.index(c.hypothesis.template), ply_of(c), c.id),
        default=None,
    )


def _pending(
    claims: dict[str, Claim], relations: tuple[ClaimRelation, ...], selected: set[str]
) -> tuple[str, ...]:
    """Rule 7: ≤ 2 INCONCLUSIVE claims with QUALIFIES to a selected claim, by role, then id."""

    found = {
        r.source
        for r in relations
        if r.kind is RelationKind.QUALIFIES and r.target in selected and r.source in claims
        and claims[r.source].verdict.status is VerdictStatus.INCONCLUSIVE
        and claims[r.source].hypothesis.role in PENDING_ROLES
    }  # fmt: skip
    ordered = sorted(found, key=lambda i: (PENDING_ROLES.index(claims[i].hypothesis.role), i))
    return tuple(ordered[:MAX_PENDING])


def plan(
    judgements: tuple[Judgement, ...],
    claims: tuple[Claim, ...],
    relations: tuple[ClaimRelation, ...],
    labels: tuple[Label, ...],
    ply_of=lambda claim: 0,
) -> ExplanationPlan:
    """`selection_v1` (R3-D §1, rules 1–7). `ply_of` orders mechanisms of one template by their
    node on the line; the caller passes it so the plan itself never reads the tree."""

    judgement = judgements[0]
    subject = judgement.subject
    by_id = {c.id: c for c in claims}
    label = next((lb for lb in labels if lb.subject == subject), None)
    purpose: tuple[str, ...] = ()
    mechanism: tuple[str, ...] = ()
    consequence: tuple[str, ...] = ()
    justification: tuple[str | LineSegment, ...] = ()
    grounds: tuple[str, ...] = ()

    if judgement.status is not JudgementStatus.DECIDED:  # rule 1
        label = label if label is not None and label.kind is LabelKind.FORCED else None
        exact = {i: c for i, c in by_id.items() if _exact(c)}
        found = _first(exact, EXACT_CONSEQUENCES, subject)
        consequence = (found.id,) if found is not None else ()
        function = _first(exact, EXACT_FUNCTIONS, subject)
        purpose = (function.id,) if function is not None else ()
    else:
        function_taken = comparison_taken = False
        if label is not None:  # rule 2
            grounds = label.grounds
            if label.kind is LabelKind.GREAT:
                purpose, function_taken = (label.grounds[0],), True
            elif label.kind is LabelKind.MISS:
                better = next(
                    (g for g in label.grounds if by_id[g].hypothesis.template == "better_move_v1"),
                    None,
                )
                chosen = better if better is not None else label.grounds[0]
                justification, comparison_taken = _with_line(by_id[chosen]), True
        primary = _consequence(by_id, subject)  # rule 3
        consequence = (primary.id,) if primary is not None else ()
        mech = _mechanism(by_id, relations, primary, ply_of)  # rule 4
        mechanism = (mech.id,) if mech is not None else ()
        if not function_taken:  # rule 5
            order = FUNCTIONS
            if label is not None and label.kind is LabelKind.BRILLIANT:
                order = tuple(t for t in FUNCTIONS if t not in SACRIFICES)  # R3-D H10
            function = _first(by_id, order, subject)
            purpose = (function.id,) if function is not None else ()
        if not comparison_taken:  # rule 6
            comparison = _first(by_id, COMPARISONS, subject)
            justification = _with_line(comparison) if comparison is not None else ()

    # rule 7 qualifies what is rendered: BRILLIANT's pair is its ground sentence; GREAT's and MISS's
    # rendered grounds already sit in purpose or justification (an unchosen MISS ground is not shown)
    rendered = grounds if label is not None and label.kind is LabelKind.BRILLIANT else ()
    selected = [*rendered, *consequence, *mechanism, *purpose]
    selected += [j for j in justification if isinstance(j, str)]
    selected = list(dict.fromkeys(selected))
    scopes = tuple(ScopeRef(i) for i in selected)  # rule 7: deduplicated when rendered
    pending = _pending(by_id, relations, set(selected))
    return ExplanationPlan(
        subject,
        JudgementRef(subject),
        label,
        purpose,
        mechanism,
        consequence,
        justification,
        (*scopes, *pending),
    )


def _with_line(claim: Claim) -> tuple[str | LineSegment, ...]:
    if claim.hypothesis.template in WITH_LINE and claim.hypothesis.operands:
        window = claim.hypothesis.operands[0]
        if isinstance(window, LineSegment):
            return (claim.id, window)
    return (claim.id,)
