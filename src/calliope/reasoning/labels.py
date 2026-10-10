"""`label_v1` (R0-D §11, R2-D §5.2): GREAT and MISS from the grade and the claims.

BRILLIANT is not assigned in v1 (R2-D E10, owner decision 2026-10-10); it returns in `label_v2`.
The grade never reads claims; the label reads both, so there is no cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from calliope.facts import TreeView
from calliope.reasoning.findings import ComparisonFinding, OutcomeKind
from calliope.reasoning.observer import Grade, Judgement, JudgementStatus
from calliope.reasoning.refs import ClaimId, MoveSubject
from calliope.reasoning.verification import Claim

LABEL_POLICY = "label_v1"
MISS_PREVIOUS = (Grade.MISTAKE, Grade.BLUNDER)


class LabelKind(StrEnum):
    BRILLIANT = "brilliant"  # reserved for label_v2
    GREAT = "great"
    MISS = "miss"


@dataclass(frozen=True, slots=True)
class Label:
    kind: LabelKind
    subject: MoveSubject
    grounds: tuple[ClaimId, ...]
    policy: str = LABEL_POLICY


def _supported(claims: tuple[Claim, ...], template: str, subject: MoveSubject) -> Claim | None:
    return next(
        (
            c
            for c in claims
            if c.hypothesis.template == template and c.supported and c.hypothesis.subject == subject
        ),
        None,
    )


def label_v1(
    view: TreeView, judgements: tuple[Judgement, ...], claims: tuple[Claim, ...]
) -> tuple[Label, ...]:
    """At most one label for the target move: GREAT, then MISS."""

    target = judgements[0] if judgements else None
    if target is None or target.status is not JudgementStatus.DECIDED:
        return ()
    subject = target.subject
    if target.grade is Grade.BEST:
        only = _supported(claims, "only_move_v1", subject)
        if only is not None:
            return (Label(LabelKind.GREAT, subject, (only.id,)),)
    previous = judgements[1] if len(judgements) > 1 else None
    if (
        previous is not None
        and previous.status is JudgementStatus.DECIDED
        and previous.grade in MISS_PREVIOUS
        and target.grade.at_least(Grade.INACCURACY)
    ):
        better = _supported(claims, "better_move_v1", subject)
        if better is not None and _gains(view, subject, better):
            return (Label(LabelKind.MISS, subject, (better.id,)),)
    return ()


def _gains(view: TreeView, subject: MoveSubject, claim: Claim) -> bool:
    """The best line mates for the mover or wins material: `MATE(m, ·)` or `STABLE(Δ1 ≥ 1)`."""

    finding = next(f for f in claim.verdict.findings if isinstance(f, ComparisonFinding))
    best = finding.best
    mover = view.node(subject.parent).side_to_move
    if best.kind is OutcomeKind.MATE:
        return best.winner is mover
    return best.kind is OutcomeKind.STABLE and best.delta is not None and best.delta >= 1
