"""Labels from the grade and the claims; the grade never reads claims, so there is no cycle.

`label_v1` (R0-D §11, R2-D §5.2): GREAT and MISS. `label_v2` (LV-D): FORCED (one legal move),
a provisional BRILLIANT (rule `brilliant_p1`), a provisional GREAT without routine replies (rule
`great_p2`), and MISS as in v1. Every `label_v2` label names its rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from calliope.facts import Capture, TreeView
from calliope.reasoning.findings import ComparisonFinding, OutcomeKind
from calliope.reasoning.observer import Grade, Judgement, JudgementStatus
from calliope.reasoning.refs import ClaimId, MoveSubject
from calliope.reasoning.verification import Claim

LABEL_POLICY = "label_v1"
LABEL_V2 = "label_v2"
BRILLIANT_GRADES = (Grade.BEST, Grade.EXCELLENT, Grade.GOOD)  # loss < 100 (LV-D §5 step 3)
MISS_PREVIOUS = (Grade.MISTAKE, Grade.BLUNDER)


class LabelKind(StrEnum):
    BRILLIANT = "brilliant"  # label_v2, provisional
    GREAT = "great"
    MISS = "miss"
    FORCED = "forced"  # label_v2


@dataclass(frozen=True, slots=True)
class Label:
    kind: LabelKind
    subject: MoveSubject
    grounds: tuple[ClaimId, ...]
    policy: str = LABEL_POLICY
    rule: str = ""  # the rule that made it (LV-D §7); "" before label_v2
    provisional: bool = False  # made under a provisional rule (LV-D §8)


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


def _on(claims: tuple[Claim, ...], template: str, premise: ClaimId) -> Claim | None:
    """The SUPPORTED claim of `template` resting on `premise`."""

    return next(
        (
            c
            for c in claims
            if c.hypothesis.template == template
            and c.supported
            and any(use.claim == premise for use in c.hypothesis.premises)
        ),
        None,
    )


def _recapture(view: TreeView, subject: MoveSubject) -> bool:
    """The target captures on the square where the previous move captured (LV-D §4)."""

    previous = view.edge(subject.parent)
    if previous is None or view.node(subject.parent).incoming_move is None:
        return False
    before = view.fact("move", subject.parent)
    now = view.fact("move", subject.child)
    taken = next((e for e in before.events if isinstance(e, Capture)), None)
    retaken = next((e for e in now.events if isinstance(e, Capture)), None)
    return taken is not None and retaken is not None and taken.square == retaken.square


def label_v2(
    view: TreeView, judgements: tuple[Judgement, ...], claims: tuple[Claim, ...]
) -> tuple[Label, ...]:
    """At most one label for the target move: FORCED, BRILLIANT, GREAT, then MISS (LV-D)."""

    target = judgements[0] if judgements else None
    if target is None:
        return ()
    subject = target.subject
    status = view.fact("status", subject.parent)
    if status.legal_move_count == 1:  # a RULE fact: no grade needed (LV-D §3, review C2)
        return (Label(LabelKind.FORCED, subject, (), LABEL_V2, "forced_v1"),)
    if target.status is not JudgementStatus.DECIDED:
        return ()
    if target.grade in BRILLIANT_GRADES:
        sacrifice = _supported(claims, "piece_sacrifice_v1", subject)
        holds = _on(claims, "capture_holds_v1", sacrifice.id) if sacrifice is not None else None
        if sacrifice is not None and holds is not None:
            grounds = (sacrifice.id, holds.id)
            return (Label(LabelKind.BRILLIANT, subject, grounds, LABEL_V2, "brilliant_p1", True),)
    if target.grade is Grade.BEST:
        only = _supported(claims, "only_move_v1", subject)
        routine = (
            status.in_check
            or _recapture(view, subject)
            or view.fact("move", subject.child).gives_mate
            or _supported(claims, "rescue_v1", subject) is not None
        )
        if only is not None and not routine:
            return (Label(LabelKind.GREAT, subject, (only.id,), LABEL_V2, "great_p2", True),)
    for label in label_v1(view, judgements, claims):
        if label.kind is LabelKind.MISS:
            return (Label(LabelKind.MISS, subject, label.grounds, LABEL_V2, "miss_v1"),)
    return ()
