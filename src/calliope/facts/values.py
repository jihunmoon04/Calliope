"""Typed fact values: classes of facts, sentinels for undefined values, partial counts (§1)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FactClass(StrEnum):
    RULE = "rule"
    DEFINED = "defined"
    ATTESTED = "attested"


@dataclass(frozen=True, slots=True)
class NotObserved:
    """The value depends on the side to move and is undefined for this frame."""


@dataclass(frozen=True, slots=True)
class HistoryUnknown:
    """The value depends on positions before the known history (§2.2)."""


# The closed reason codes of `NotApplicable` and `NotComputed` (DF-D §6.2): each is an entry of
# the definitions registry (`calliope.facts.definitions`).
FACT_REASONS = frozenset(
    {
        "IN_CHECK",  # `exchange`: no `see_v1` for a side in check
        "NOT_EXPOSED",  # `exchange.safe_moves`: the piece is not exposed
        "IRREGULAR_SEARCH",  # the basis: the survey ended irregularly
        "COMPARISON_NOT_REQUESTED",  # the basis: no comparison was asked for
        "PARENT_NOT_SEARCHED",  # the basis: the parent has no survey
        "BUDGET",  # the basis: the comparison was skipped for the search budget
        "DEADLINE",  # the basis: the comparison was skipped for the request deadline
        "TIER",  # `TreeView.fact`: an engine-only node holds the tier families only
        "NOT_REQUESTED",  # `TreeView.fact`: an on-request family not yet ensured
        "NO_SAME_SIDE_ANCESTOR",  # `same_side_delta` at a node without a grandparent (stored)
        "ROOT_HAS_NO_MOVE",  # an EDGE family or a child score at the root
        "TERMINAL",  # the basis of a terminal node or one after it
        "FAMILY_NOT_SELECTED",  # `TreeView.fact`: the family is not in the session
        "NOT_COMPUTED_AT_NODE",  # `TreeView.fact`: an eager family missing at an input node
        "NOT_APPLICABLE_RECORD",  # `material_flow`: a record on the path is not applicable
    }
)


@dataclass(frozen=True, slots=True)
class NotApplicable:
    reason: str


@dataclass(frozen=True, slots=True)
class NotComputed:
    reason: str


@dataclass(frozen=True, slots=True)
class Unavailable:
    """The engine does not provide the value (A0 §1)."""


class AbsentReason(StrEnum):
    CAPTURED = "captured"
    PROMOTED = "promoted"


@dataclass(frozen=True, slots=True)
class Absent:
    """The piece no longer exists in the role this fact describes (F2-D §11)."""

    reason: AbsentReason


NOT_OBSERVED = NotObserved()
HISTORY_UNKNOWN = HistoryUnknown()
UNAVAILABLE = Unavailable()
CAPTURED = Absent(AbsentReason.CAPTURED)
PROMOTED = Absent(AbsentReason.PROMOTED)


@dataclass(frozen=True, slots=True, order=True)
class AtLeast:
    """A count over incomplete history: the true count is `n` or more."""

    n: int


@dataclass(frozen=True, slots=True)
class Defined[T]:
    """A `DEFINED` value inside a family record, with the definition that produced it."""

    definition: str
    value: T
