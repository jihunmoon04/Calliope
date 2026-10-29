"""POSITION records kept per process (PF-D §3, D2): the tree is the same with them as without."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from calliope.facts import (
    PLAYED,
    REGISTRY,
    ExtendRequest,
    FactEngine,
    InputLine,
    InvalidRequestError,
    OpenRequest,
    PositionKey,
    PositionRecords,
)
from calliope.facts.families.base import FamilyContext
from calliope.facts.families.material import MaterialFamily
from calliope.facts.storage import digest, save

LINES = (("e4", "e5", "Nf3", "Nc6", "Bb5", "a6"), ("d4", "d5", "c4", "e6", "Nc3"))


def _build(memo=None, families=REGISTRY, lines=LINES):
    fact_engine = FactEngine(families, position_records=memo)
    tree = fact_engine.open(OpenRequest())
    for i, moves in enumerate(lines):
        fact_engine.extend(tree, ExtendRequest((InputLine(f"l{i}", moves),), PLAYED))
    return tree


def _same(tree, plain) -> None:
    assert save(tree) == save(plain)  # the file's bytes, so its F5 digests too
    assert [digest(tree, r) for r in range(1, tree.rev + 1)] == [
        digest(plain, r) for r in range(1, plain.rev + 1)
    ]


def test_a_tree_built_with_kept_records_equals_one_built_without() -> None:
    plain = _build()
    memo = PositionRecords(100_000)
    first = _build(memo)
    computed = memo.misses
    assert computed == len(memo) and memo.hits == 0
    second = _build(memo)  # every POSITION record from the memo
    assert memo.misses == computed and memo.hits == computed
    _same(first, plain)
    _same(second, plain)
    # a family with requirements (king: status, squares, pawns) is among them
    assert any(name == "king" for name, _, _ in memo._records)
    # a transposition shares a position with another line: kept once
    _same(
        _build(memo, lines=(("Nf3", "Nc6", "e4", "e5"),)),
        _build(lines=(("Nf3", "Nc6", "e4", "e5"),)),
    )


def test_a_small_bound_evicts_but_gives_the_same_tree() -> None:
    memo = PositionRecords(5)
    _same(_build(memo), _build())
    assert len(memo) == 5
    _same(_build(memo), _build())


def test_another_family_version_is_another_record() -> None:
    memo = PositionRecords(10)
    key = PositionKey.of(__import__("chess").Board())
    calls = []

    def family(version):
        def compute(ctx):
            calls.append(version)
            return (version, ctx.records)

        return SimpleNamespace(name="material", version=version, compute=compute)

    def context():
        return FamilyContext(board=None, records={})

    assert memo.compute(family("material_v1"), key, context)[0] == "material_v1"
    assert memo.compute(family("material_v1"), key, context)[0] == "material_v1"
    assert memo.compute(family("material_v2"), key, context)[0] == "material_v2"
    assert calls == ["material_v1", "material_v2"]


def test_an_engine_with_other_families_is_refused() -> None:
    memo = PositionRecords(10)
    FactEngine(position_records=memo)
    FactEngine(position_records=memo)  # the same registry again

    class Material2(MaterialFamily):
        version = "material_v2"

    other = tuple(Material2() if f.name == "material" else f for f in REGISTRY)
    with pytest.raises(InvalidRequestError):
        FactEngine(other, position_records=memo)


@pytest.mark.parametrize("bound", [0, -1, 1.5, None, True])
def test_the_bound_is_an_integer_of_at_least_one(bound) -> None:
    with pytest.raises(ValueError):
        PositionRecords(bound)


def test_threads_share_one_memo() -> None:
    plain = _build()
    memo = PositionRecords(100_000)
    trees: list = []

    def build() -> None:
        trees.append(_build(memo))

    threads = [threading.Thread(target=build) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(trees) == 3
    for tree in trees:
        _same(tree, plain)
