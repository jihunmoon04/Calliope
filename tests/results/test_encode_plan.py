"""CC-D C3: `encode` planned per type gives F5-D §2's output — every byte a stored analysis saves to,
the cases of the encoding, its refusals — and checks the registry on every call."""

from __future__ import annotations

import dataclasses
import enum

import pytest
from corpus_case import analyse, cases
from test_result import synthetic_game

from calliope.facts import storage as facts_storage
from calliope.facts.storage import KEY_TYPES, encode
from calliope.reasoning import explain
from calliope.reasoning import storage as reasoning_storage
from calliope.reasoning.storage import save


def reference(value, registry):
    """F5-D §2's `encode` as it was before CC-D: every value tested against the cases in order."""

    if value is None or isinstance(value, bool | str) and not isinstance(value, enum.Enum):
        return value
    if isinstance(value, int) and not isinstance(value, enum.Enum):
        return value
    if isinstance(value, enum.Enum):
        _registered(type(value), registry)
        return {"e": type(value).__name__, "v": value.value}
    if isinstance(value, KEY_TYPES):
        return {"k": type(value).__name__, "v": value.value}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        _registered(type(value), registry)
        return {
            "t": type(value).__name__,
            "f": [reference(getattr(value, f.name), registry) for f in dataclasses.fields(value)],
        }
    if isinstance(value, tuple | list):
        return [reference(item, registry) for item in value]
    raise TypeError(f"{type(value).__name__} is not encodable (F5-D §2)")


def _registered(kind, registry):
    if registry.get(kind.__name__) is not kind:
        raise TypeError(f"{kind.__name__} is not in the type registry")


def _analyses():
    yield from synthetic_game(range(1, 6))
    for case in cases():
        yield analyse(case)


def test_every_stored_analysis_saves_to_the_same_bytes(monkeypatch) -> None:
    analyses = list(_analyses())
    planned = [save(a, explain(a)) for a in analyses]
    monkeypatch.setattr(facts_storage, "encode", reference)
    monkeypatch.setattr(reasoning_storage, "encode", reference)
    before = [save(a, explain(a)) for a in analyses]
    assert planned == before and len(planned) == 5 + len(cases())


class Colour(enum.Enum):
    WHITE = "white"


class Rank(enum.IntEnum):
    ONE = 1


class Name(enum.StrEnum):
    A = "a"


@dataclasses.dataclass(frozen=True)
class Record:
    n: int
    colour: Colour
    items: tuple
    nested: Record | None = None


REGISTRY = {"Colour": Colour, "Rank": Rank, "Name": Name, "Record": Record}


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        7,
        "s",
        Colour.WHITE,
        Rank.ONE,  # an int that is an enum
        Name.A,  # a str that is an enum
        (1, [2, "x"], ()),
        Record(1, Colour.WHITE, (Rank.ONE, Name.A), Record(2, Colour.WHITE, ())),
    ],
)
def test_the_cases_give_the_same_output(value) -> None:
    assert encode(value, REGISTRY) == reference(value, REGISTRY)


@pytest.mark.parametrize("value", [1.5, {"a": 1}, Record, Colour])
def test_what_is_not_encodable_is_refused_as_before(value) -> None:
    with pytest.raises(TypeError) as planned:
        encode(value, REGISTRY)
    with pytest.raises(TypeError) as before:
        reference(value, REGISTRY)
    assert str(planned.value) == str(before.value)


def test_the_registry_is_checked_on_every_call() -> None:
    """The plan holds no registry: one type under two registries in turn (review C3)."""

    value = Record(1, Colour.WHITE, ())
    without = {k: v for k, v in REGISTRY.items() if k != "Record"}
    for _ in range(2):
        assert encode(value, REGISTRY)["t"] == "Record"
        with pytest.raises(TypeError, match="Record is not in the type registry"):
            encode(value, without)
    with pytest.raises(TypeError, match="Colour is not in the type registry"):
        encode(Colour.WHITE, {})
