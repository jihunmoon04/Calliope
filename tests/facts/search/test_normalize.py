"""`FactEngine.normalize_open` and `FactEngine.normalize` (reasoning R4-D §3.5).

Every raw request, normalized on the view of the revision before it, equals the request the tree
logged for its revision. The view is pinned before the final revision, so a later revision cannot
enter the normal form (R4-D final review note).
"""

from __future__ import annotations

from synthetic import engine

from calliope.facts import (
    EXPLORED,
    FULL,
    NONE,
    PLAYED,
    EngineProfile,
    EnsureRequest,
    ExtendRequest,
    FactEngine,
    InputLine,
    OpenRequest,
    RootSpec,
)


def _run(fact_engine: FactEngine, opening: OpenRequest, calls: list) -> tuple:
    tree = fact_engine.open(opening)
    raws = [opening]
    for make in calls:
        raw = make(tree)
        if isinstance(raw, EnsureRequest):
            before = tree.rev
            if fact_engine.ensure(tree, raw) == before:
                continue  # NO_OP commits nothing and is not logged
        else:
            fact_engine.extend(tree, raw)
        raws.append(raw)
    return tree, raws


def _check(fact_engine: FactEngine, tree, raws) -> None:
    final = tree.view()
    assert fact_engine.normalize_open(raws[0]) == final.request(1)
    for rev in range(2, len(raws) + 1):
        before = tree.view(rev - 1)  # the cursor: the tree as the call found it
        assert fact_engine.normalize(before, raws[rev - 1]) == final.request(rev), rev


def test_open_resolves_fen_san_and_default_families() -> None:
    fe = FactEngine()
    raw = OpenRequest(root=RootSpec(fen=None, moves=("e4", "e5", "Nf3")))
    normal = fe.normalize_open(raw)
    assert normal.root.fen.startswith("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -")
    assert normal.root.moves == ("e2e4", "e7e5", "g1f3")
    assert normal.families and "exchange" not in normal.families  # on-request families stay out
    assert normal == fe.open(raw).view().request(1)


def test_extends_and_ensures_without_an_engine() -> None:
    fe = FactEngine()
    opening = OpenRequest(root=RootSpec())
    calls = [
        lambda t: ExtendRequest((InputLine("game", ("e4", "e5", "Nf3")),), PLAYED),
        lambda t: ExtendRequest((InputLine("game", ("Nc6", "Bb5")),), PLAYED),  # continues the line
        lambda t: ExtendRequest(
            (InputLine("alt", ("d4",), start=t.view().input_line("game").nodes[1]),), EXPLORED
        ),
        lambda t: EnsureRequest(tuple(reversed(t.view().input_line("game").nodes)), ("exchange",)),
        lambda t: EnsureRequest(t.view().input_line("game").nodes[:2], ("exchange",)),  # NO_OP
    ]
    tree, raws = _run(fe, opening, calls)
    assert len(raws) == 5  # the NO_OP left no revision
    _check(fe, tree, raws)


def test_extends_with_an_engine_resolve_the_session_expansion() -> None:
    fe = FactEngine(engine=engine())
    opening = OpenRequest(root=RootSpec(moves=("d4",)), engine=EngineProfile(), root_expansion=NONE)
    calls = [
        lambda t: ExtendRequest(
            (InputLine("game", ("d5", "c4")),), PLAYED
        ),  # the default expansion
        lambda t: ExtendRequest((InputLine("game", ("e6",)),), PLAYED, FULL),  # its own
    ]
    tree, raws = _run(fe, opening, calls)
    assert tree.view().request(2).expansion is not None
    _check(fe, tree, raws)
