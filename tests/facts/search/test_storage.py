"""F5-D §11: canonical encoding, digest chain, saved trees, rebuild and the persisted store."""

import dataclasses
import json
import os
import random
import subprocess
import sys
from pathlib import Path

import chess
import pytest
from engine_auditor import audit_engine_tree
from synthetic import IDENTITY, engine, synthetic

from calliope.facts import (
    EXPLORED,
    PLAYED,
    ExtendRequest,
    FactEngine,
    InputLine,
    OpenRequest,
    RootSpec,
    analysis,
    storage,
)
from calliope.facts.errors import BudgetExceededError, StoredTreeError
from calliope.facts.families import REGISTRY
from calliope.facts.request import FULL, EnsureRequest, ExpansionSpec
from calliope.facts.request import SessionBudget as Budget
from calliope.facts.search import EngineProfile, EngineResultStore, ScriptedEngine
from calliope.facts.search.profile import EngineIdentity

PROFILE = EngineProfile()
HERE = Path(__file__).parent


def _session(port=None, store=None, fen=None, moves=(), **kwargs):
    fact_engine = FactEngine(engine=port, store=store)
    tree = fact_engine.open(
        OpenRequest(root=RootSpec(fen=fen, moves=moves), engine=PROFILE if port else None, **kwargs)
    )
    return fact_engine, tree


def _extend(fact_engine, tree, *moves, label="g", role=PLAYED, start=None, expansion=None):
    fact_engine.extend(
        tree, ExtendRequest((InputLine(label, moves, start=start),), role, expansion)
    )


def _records(tree, rev=None):
    """Every record section of every revision, compared as encoded data."""

    rev = tree.rev if rev is None else rev
    registry = storage.tree_registry(tree)
    return [storage.encode(storage.revision_sections(tree, r), registry) for r in range(1, rev + 1)]


def _rich_tree(port=None):
    """An engine tree with irregular searches, ANALYSIS, role gain, ensure and branches."""

    port = port or engine(pv_plies=4)
    fact_engine, tree = _session(port)
    _extend(fact_engine, tree, "e4", "e5", "Nf3", "Nc6")
    _extend(fact_engine, tree, "d4", label="x", role=EXPLORED)
    _extend(fact_engine, tree, "h2h3", "h7h6", label="p", role=analysis("b"), expansion=FULL)
    view = tree.view()
    pv_node = next(n.node_id for n in view.nodes() if not view.has_input_role(n.node_id))
    _extend(fact_engine, tree, view.node(pv_node).incoming_move, label="gain", role=EXPLORED)
    fact_engine.ensure(tree, EnsureRequest((pv_node,), ("pieces", "patterns")))
    return fact_engine, tree, port


# -- encoding (§11.1) ----------------------------------------------------------------------------


def test_every_record_and_request_encodes_including_a_lone_surrogate() -> None:
    fact_engine, tree, _port = _rich_tree()
    _extend(fact_engine, tree, "a2a3", label="\ud800odd", role=EXPLORED)
    data = storage.save(tree)
    exported = storage.export(tree)
    assert data.isascii() and exported.isascii()
    assert FactEngine(engine=engine(pv_plies=4)).load(data).view().digest() == tree.view().digest()


def test_encoding_refuses_floats_sets_dicts_and_unknown_types() -> None:
    registry = storage.type_registry(REGISTRY)
    for bad in (1.5, {1}, frozenset(), {"a": 1}):
        with pytest.raises(TypeError):
            storage.encode(bad, registry)

    @dataclasses.dataclass(frozen=True)
    class Stranger:
        x: int

    with pytest.raises(TypeError):
        storage.encode(Stranger(1), registry)


def test_bytes_are_identical_across_processes_and_hash_seeds() -> None:
    code = (
        "from test_storage import _rich_tree; from calliope.facts import storage; "
        "import sys; _, t, _ = _rich_tree(); sys.stdout.write(storage.save(t).decode())"
    )
    outputs = set()
    for seed in ("1", "2", "3"):
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=HERE,
            env={**os.environ, "PYTHONHASHSEED": seed},
            check=True,
        )
        outputs.add(result.stdout)
    assert len(outputs) == 1


def test_types_digest_tracks_fields_order_and_enum_members() -> None:
    registry = storage.type_registry(REGISTRY)
    base = storage.types_digest(registry)

    @dataclasses.dataclass(frozen=True)
    class ExpansionSpec:
        comparison: bool
        survey: bool
        attach_lines: bool

    changed = dict(registry, ExpansionSpec=ExpansionSpec)
    assert storage.types_digest(changed) != base
    import enum

    class SearchKind(enum.StrEnum):
        SURVEY = "survey"

    assert storage.types_digest(dict(registry, SearchKind=SearchKind)) != base


# -- digest (§11.2) --------------------------------------------------------------------------------


def test_digest_is_stable_and_pinned_views_match() -> None:
    _e, tree, _p = _rich_tree()
    _e2, again, _p2 = _rich_tree()
    assert tree.view().digest() == again.view().digest()
    for rev in range(1, tree.rev + 1):
        assert tree.view(rev).digest() == storage.digest(tree, rev)
    assert len({tree.view(r).digest() for r in range(1, tree.rev + 1)}) == tree.rev


def test_cold_and_warm_builds_are_equal_when_reproducible() -> None:
    store = EngineResultStore()

    def build(budget=None, shared=store):
        budget = budget or Budget()
        fact_engine, tree = _session(engine(), shared, budget=budget)
        _extend(fact_engine, tree, "e4", "e5", "d4")
        _extend(fact_engine, tree, "d4", "e5", "e4", label="t", role=EXPLORED)
        return tree

    cold = build()
    warm = build()
    assert cold.view().reproducible() and cold.view().digest() == warm.view().digest()
    # transposed request nodes share one input: the pre-check counts it once (F5D-R2-C1),
    # so a cold build fits the budget the warm one fits
    searches = sum(len(p.searches) for p, _ in cold._revisions.values())
    limited = build(Budget(max_searches=searches), EngineResultStore())
    assert limited.view().reproducible()


def test_budget_counterexample_is_not_reproducible() -> None:
    store = EngineResultStore()
    fact_engine, tree = _session(engine(), store)
    _extend(fact_engine, tree, "h2h3")
    fact_engine, warm = _session(engine(), store, budget=Budget(max_searches=1))
    _extend(fact_engine, warm, "h2h3")  # accepted only because the store is warm
    assert not warm.view().reproducible()


def test_a_mutated_record_or_decision_changes_the_digest_but_metadata_does_not() -> None:
    _e, tree, _p = _rich_tree()
    original = tree.view().digest()
    pending, delta = tree._revisions[2]

    def recompute():
        tree._digests.clear()
        return tree.view().digest()

    node = pending.nodes[0]
    pending.nodes[0] = dataclasses.replace(node, halfmove_clock=node.halfmove_clock + 1)
    assert recompute() != original
    pending.nodes[0] = node
    assert recompute() == original
    tree._revisions[2] = (
        pending,
        dataclasses.replace(delta, skipped=((tree.root, "comparison", "BUDGET"),)),
    )
    assert recompute() != original
    tree._revisions[2] = (pending, dataclasses.replace(delta, searches_run=(("survey", 99),)))
    pending.runtimes.clear()
    assert recompute() == original


# -- round trip, isolation, continuation (§11.3–§11.5) ---------------------------------------------


def _game(seed: int, plies: int = 40) -> list[str]:
    rng = random.Random(seed)
    board = chess.Board()
    moves = []
    while len(moves) < plies and not board.is_game_over():
        move = rng.choice(list(board.legal_moves))
        moves.append(move.uci())
        board.push(move)
    return moves


def test_round_trip_of_engine_less_trees_in_every_root_form() -> None:
    for seed in range(8):
        moves = _game(seed)
        board = chess.Board()
        for uci in moves[:6]:
            board.push_uci(uci)
        forms = (
            (None, ()),
            (None, tuple(moves[:3])),
            (board.fen(), ()),
            (board.fen(), tuple(moves[6:9])),
        )
        fen, pre = forms[seed % 4]
        fact_engine, tree = _session(fen=fen, moves=pre)
        tail = moves[len(pre) if fen is None else 6 + len(pre) :]
        _extend(fact_engine, tree, *tail[:20])
        nodes = tree.view().input_line("g").nodes
        alternative = [m.uci() for m in chess.Board(tree.view().node(nodes[1]).fen).legal_moves][-1]
        _extend(fact_engine, tree, alternative, label="b", role=EXPLORED, start=nodes[1])
        fact_engine.ensure(tree, EnsureRequest((nodes[-1],), ("pieces", "patterns")))
        data = storage.save(tree)
        loaded = FactEngine().load(data)
        assert _records(loaded) == _records(tree)
        assert storage.save(loaded) == data


def test_round_trip_of_engine_trees_with_every_decision_kind() -> None:
    # irregular searches, budget skips, deadline cuts, ANALYSIS, role gain, ensure, pinned saves
    after_h3 = chess.Board("rnbqkbnr/pppppppp/8/8/8/7P/PPPPPPP1/RNBQKBNR b KQkq - 0 1").fen()
    port = engine(irregular=frozenset({after_h3}))
    for budget in (Budget(), Budget(max_searches=3), Budget(deadline_per_request_ms=0)):
        fact_engine = FactEngine(engine=port, store=EngineResultStore())
        tree = fact_engine.open(OpenRequest(engine=PROFILE, budget=budget))
        try:
            _extend(fact_engine, tree, "h2h3", "h7h6")
            _extend(fact_engine, tree, "a2a3", label="p", role=analysis("b"), expansion=FULL)
        except BudgetExceededError:
            pass
        data = storage.save(tree)
        loading = engine(irregular=frozenset({after_h3}))
        loaded = FactEngine(engine=loading).load(data)
        assert _records(loaded) == _records(tree) and loading.calls == []
        assert storage.save(loaded) == data
        if budget.deadline_per_request_ms is not None:
            assert any(d.deadline_cuts for _, d in tree._revisions.values())
        for rev in range(1, tree.rev + 1):
            pinned = FactEngine(engine=engine()).load(storage.save(tree, rev))
            assert _records(pinned) == _records(tree, rev)
    _e, rich, _p = _rich_tree()
    loaded = FactEngine(engine=engine(pv_plies=4)).load(storage.save(rich))
    assert _records(loaded) == _records(rich)
    audit_engine_tree(loaded)


def test_isolation_refused_loads_leave_the_store_and_port_alone() -> None:
    _e, tree, _p = _rich_tree()
    data = json.loads(storage.save(tree))
    data["digests"][-1] = "0" * 64
    store = EngineResultStore()
    port = engine(pv_plies=4)
    with pytest.raises(StoredTreeError, match="digest"):
        FactEngine(engine=port, store=store).load(json.dumps(data).encode())
    assert len(store) == 0 and port.calls == []


def test_a_conflicting_loading_store_refuses() -> None:
    _e, tree, _p = _rich_tree()
    data = storage.save(tree)
    some = next(s for p, _ in tree._revisions.values() for s in p.searches.values() if s.regular)
    store = EngineResultStore()
    lines = (dataclasses.replace(some.lines[0], nodes=some.lines[0].nodes + 1), *some.lines[1:])
    store._searches[some.search_id] = dataclasses.replace(some, lines=lines)
    with pytest.raises(StoredTreeError, match="other content"):
        FactEngine(engine=engine(pv_plies=4), store=store).load(data)


def test_pinned_load_puts_only_the_searches_at_that_revision() -> None:
    _e, tree, _p = _rich_tree()
    data = storage.save(tree)
    store = EngineResultStore()
    FactEngine(engine=engine(pv_plies=4), store=store).load(data, rev=1)
    assert len(store) == len(tree._revisions[1][0].searches)


def test_continuation_equals_the_original_and_the_budget_is_restored() -> None:
    store = EngineResultStore()
    fact_engine, tree = _session(engine(), store, budget=Budget(max_searches=4))
    _extend(fact_engine, tree, "e4", "e5")
    data = storage.save(tree)
    loaded_engine = FactEngine(engine=engine(), store=store)
    loaded = loaded_engine.load(data)
    for fe, t in ((fact_engine, tree), (loaded_engine, loaded)):
        with pytest.raises(BudgetExceededError):
            _extend(fe, t, "Nf3", "Nc6", label="more")
    _extend(fact_engine, tree, "e4", "e5", label="again")
    _extend(loaded_engine, loaded, "e4", "e5", label="again")
    assert _records(loaded) == _records(tree)


# -- refusals (§11.6) --------------------------------------------------------------------------------


def _tampered(tree, change) -> bytes:
    document = json.loads(storage.save(tree))
    change(document)
    return json.dumps(document).encode()


def test_refusals() -> None:
    _e, tree, _p = _rich_tree()
    data = storage.save(tree)

    def loads(blob, port=None, registry=REGISTRY):
        return FactEngine(registry, engine=port or engine(pv_plies=4)).load(blob)

    with pytest.raises(StoredTreeError, match="format"):
        loads(_tampered(tree, lambda d: d.update(format="other")))
    with pytest.raises(StoredTreeError, match="build identity"):
        old = storage.FACTS_BUILD_VERSION
        storage.FACTS_BUILD_VERSION = "0"
        try:
            loads(data)
        finally:
            storage.FACTS_BUILD_VERSION = old
    reordered = (REGISTRY[0], REGISTRY[2], REGISTRY[1], *REGISTRY[3:])  # material and draw swapped
    with pytest.raises(StoredTreeError, match="build identity"):
        loads(data, registry=reordered)
    with pytest.raises(StoredTreeError, match="type registry"):
        loads(_tampered(tree, lambda d: d["types"].pop()))

    def change_move(d):
        line = d["requests"][1]["f"][0][0]  # first InputLine of the first extend
        line["f"][1][0] = "d2d4"

    with pytest.raises(StoredTreeError):
        loads(_tampered(tree, change_move))

    def change_skip(d):
        d["replay"][1]["f"][0] = [[{"k": "NodeId", "v": tree.root.value}, "comparison", "BUDGET"]]

    with pytest.raises(StoredTreeError):
        loads(_tampered(tree, change_skip))

    def change_score(d):
        line = d["tape"][0]["f"][10][0]
        line["f"][2]["f"][0] += 1

    with pytest.raises(StoredTreeError, match="digest"):  # an answer is caught by the digest
        loads(_tampered(tree, change_score))

    def change_pv(d):
        line = d["tape"][0]["f"][10][0]
        line["f"][-1][-1] = "a1a1"

    with pytest.raises(StoredTreeError, match="ingestion|re-normalize"):
        loads(_tampered(tree, change_pv))

    def change_regular(d):
        d["tape"][0]["f"][9] = not d["tape"][0]["f"][9]

    with pytest.raises(StoredTreeError):
        loads(_tampered(tree, change_regular))
    with pytest.raises(StoredTreeError):
        loads(_tampered(tree, lambda d: d["tape"].pop()))
    with pytest.raises(StoredTreeError, match="out of bounds"):
        loads(_tampered(tree, lambda d: d["replay"][-1]["f"].__setitem__(2, 10_000)))
    other = ScriptedEngine(
        EngineIdentity("Stockfish 19", "x", "9" * 64, IDENTITY.options), synthetic()
    )
    with pytest.raises(StoredTreeError, match="another engine"):
        loads(data, port=other)


def test_harmless_rewrites_load() -> None:
    _e, tree, _p = _rich_tree()

    def reorder(d):
        for request in d["requests"]:
            if request["t"] == "EnsureRequest":
                request["f"][1] = list(reversed(request["f"][1]))

    assert (
        FactEngine(engine=engine(pv_plies=4)).load(_tampered(tree, reorder)).view().digest()
        == tree.view().digest()
    )


# -- rebuild (§11.7) ---------------------------------------------------------------------------------


def test_rebuild_under_another_build_version_and_with_a_dropped_tape_search() -> None:
    _e, tree, _p = _rich_tree()
    stale = _tampered(tree, lambda d: d["build"]["f"].__setitem__(0, "0"))
    with pytest.raises(StoredTreeError):
        FactEngine(engine=engine(pv_plies=4)).load(stale)
    port = engine(pv_plies=4)
    rebuilt = FactEngine(engine=port).rebuild(stale)
    assert _records(rebuilt) == _records(tree) and port.calls == []

    def break_one(d):
        d["build"]["f"][0] = "0"
        d["tape"][0]["f"][9] = False  # no longer what normalization gives: dropped

    port = engine(pv_plies=4)
    rebuilt = FactEngine(engine=port).rebuild(_tampered(tree, break_one))
    assert len(port.calls) == 1 and _records(rebuilt) == _records(tree)
    other = ScriptedEngine(
        EngineIdentity("Stockfish 19", "x", "9" * 64, IDENTITY.options), synthetic()
    )
    with pytest.raises(StoredTreeError, match="identity"):
        FactEngine(engine=other).rebuild(stale)


def test_rebuild_decodes_a_reordered_type_by_field_name() -> None:
    _e, tree, _p = _rich_tree()

    def reorder(d):
        d["build"]["f"][0] = "0"
        for row in d["types"]:
            if row[0] == "ExpansionSpec":
                row[2] = ["comparison", "survey", "attach_lines"]

        def walk(value):
            if isinstance(value, dict):
                if value.get("t") == "ExpansionSpec":
                    s, c, a = value["f"]
                    value["f"] = [c, s, a]
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(d)

    rebuilt = FactEngine(engine=engine(pv_plies=4)).rebuild(_tampered(tree, reorder))
    assert _records(rebuilt) == _records(tree)


# -- the persisted store (§11.9) ---------------------------------------------------------------------


def test_store_round_trip_and_refusals() -> None:
    _e, tree, _p = _rich_tree()
    store = EngineResultStore()
    for pending, _ in tree._revisions.values():
        for search in pending.searches.values():
            if search.regular:
                store.put(search)
    data = storage.save_store(store, REGISTRY)
    loaded = storage.load_store(data, REGISTRY)
    assert loaded._searches == store._searches
    port = engine(pv_plies=4)
    fact_engine = FactEngine(engine=port, store=loaded)
    again = fact_engine.open(OpenRequest(engine=PROFILE))
    _extend(fact_engine, again, "e4", "e5", "Nf3", "Nc6")
    assert port.calls == []  # answered from the loaded store

    def tampered(change):
        document = json.loads(data)
        change(document)
        return json.dumps(document).encode()

    def answer(d):  # caught by the body digest
        d["body"][0]["f"][10][0]["f"][2]["f"][0] += 1

    def illegal(d):  # body digest updated: caught by re-normalization
        d["body"][0]["f"][10][0]["f"][-1][-1] = "a1a1"
        d["sha256"] = storage.hashlib.sha256(storage._dumps(d["body"])).hexdigest()

    def irregular(d):
        d["body"][0]["f"][9] = False
        d["sha256"] = storage.hashlib.sha256(storage._dumps(d["body"])).hexdigest()

    for change, match in (
        (answer, "digest"),
        (illegal, "ingestion|re-normalize"),
        (irregular, "re-normalize|irregular"),
        (lambda d: d["body"][0]["f"].__setitem__(0, "s_other"), "digest"),
        (lambda d: d["build"].__setitem__("python_chess", "0"), "another build"),
    ):
        with pytest.raises(StoredTreeError, match=match):
            storage.load_store(tampered(change), REGISTRY)


# -- build-version guard (§11.10) and cost (§11.11) -------------------------------------------------

# facts_build_version -> python-chess version -> digest of the guard corpus
GUARD = {
    "1": {"1.11.2": "35ed265dd68c7d32d07a836296a173dc9a948dab98e56a5f3e38eab5b5224e60"},
}


def _guard_corpus() -> str:
    after_h3 = chess.Board("rnbqkbnr/pppppppp/8/8/8/7P/PPPPPPP1/RNBQKBNR b KQkq - 0 1").fen()
    fact_engine = FactEngine(engine=engine(irregular=frozenset({after_h3})))
    tree = fact_engine.open(OpenRequest(engine=PROFILE, budget=Budget(max_searches=5)))
    _extend(fact_engine, tree, "h2h3", "h7h6", "e4")
    probe = ExpansionSpec(True, True, True)
    _extend(fact_engine, tree, "h2h3", "h7h6", label="p", role=analysis("b"), expansion=probe)
    view = tree.view()
    pv_node = next(n.node_id for n in view.nodes() if not view.has_input_role(n.node_id))
    fact_engine.ensure(tree, EnsureRequest((pv_node,), tuple(f.name for f in REGISTRY)))
    deltas = [d for _, d in tree._revisions.values()]
    assert any(reason == "BUDGET" for d in deltas for _, _, reason in d.skipped)
    assert any(not s.regular for p, _ in tree._revisions.values() for s in p.searches.values())
    return tree.view().digest()


def test_build_version_guard() -> None:
    digest = _guard_corpus()
    recorded = GUARD.get(storage.FACTS_BUILD_VERSION, {}).get(chess.__version__)
    assert recorded is not None, f"record the guard digest: {digest}"
    assert digest == recorded, "behaviour changed: bump FACTS_BUILD_VERSION and add a GUARD row"
