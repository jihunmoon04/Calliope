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
