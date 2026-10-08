"""P11-I1+I2: GraphBuilder, ExplanationGraphValidator, ExplanationSelector and exact
selection revalidation over real P10 packages built from the reviewed P8/P9 fixtures."""

import ast
from dataclasses import replace
from itertools import product
from pathlib import Path

import _p8_claim_scenarios as p8
import _p9_preservation_claim_scenarios as pres
import _p9_strong_claim_scenarios as strong
import pytest

from calliope.domain.analysis import BasePieceRef
from calliope.domain.chess import ChessMove, Color, PieceType
from calliope.domain.explanation import (
    ClaimConfidence,
    ClaimPredicate,
    ClaimScope,
    EvidenceBundle,
    EvidenceSourceFamily,
    ExplanationClaim,
    ExplanationGraph,
    ExplanationRelation,
    ExplanationRelationKind,
    ExplanationSelection,
    MoveClaimEntity,
    base_frame_piece_entity,
    required_claim_scope,
)
from calliope.errors import ExplanationGraphError, ExplanationSelectionError
from calliope.services.explanation import (
    ExplanationGraphValidator,
    ExplanationSelectionValidator,
    ExplanationSelector,
    GraphBuilder,
    graph_builder,
    graph_validator,
    selector,
)
from calliope.services.explanation.claim_validator import ClaimValidator
from calliope.services.explanation.selector import (
    PRIORITY_TIERS,
    SELECTION_FAMILIES,
    SelectionFamily,
    priority_tier,
    select_claim_ids,
    selection_family,
)

tamper = p8.tamper
_P = ClaimPredicate
_C = ClaimConfidence
_F = SelectionFamily

REAL = {
    "p8-knight": (p8.knight, p8),
    "p8-defender": (p8.defender, p8),
    "p8-fork": (p8.fork, p8),
    "p8-exact-mate": (p8.exact_mate, p8),
    "p8-engine-mate": (p8.engine_mate, p8),
    **{f"strong-{make.__name__}": (make, strong) for make in strong.SCENARIOS},
    **{f"pres-{make.__name__}": (make, pres) for make in pres.SCENARIOS},
}


def package(name):
    make, module = REAL[name]
    bundle = module.evidence(make())
    return bundle, module.claims(bundle)


def built(name):
    return GraphBuilder().build(*package(name))


def manual(name, **changes):
    bundle, claims = package(name)
    values = {
        "base_position_id": bundle.base_position_id,
        "evidence": bundle,
        "claims": claims,
        "relations": (),
    }
    values.update(changes)
    return ExplanationGraph(**values)


@pytest.fixture
def dispatch(monkeypatch):
    """Record which P10 entrypoint ran, while still running it."""

    calls = []
    for name in ("validate_bad_move", "validate_good_move"):
        original = getattr(ClaimValidator, name)

        def spy(self, bundle, claims, _name=name, _original=original):
            calls.append(_name)
            return _original(self, bundle, claims)

        monkeypatch.setattr(ClaimValidator, name, spy)
    return calls


# ---- GraphBuilder -------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(REAL))
def test_builder_preserves_exact_package_and_emits_no_relations(name, dispatch):
    bundle, claims = package(name)
    dispatch.clear()  # building the P10 fixture already ran its validator
    graph = GraphBuilder().build(bundle, claims)
    assert graph.evidence is bundle and graph.claims is claims
    assert graph.relations == () and graph.base_position_id == bundle.base_position_id
    assert ExplanationGraphValidator().validate(graph) is graph
    expected = "validate_bad_move" if name.startswith("p8") else "validate_good_move"
    assert set(dispatch) == {expected}


def test_dispatch_follows_source_family_not_predicates(dispatch):
    bundle, claims = package("p8-knight")
    dispatch.clear()
    tamper(claims[0], predicate=_P.WINS_MATERIAL)  # a P9-looking predicate on a P8 package
    with pytest.raises(ExplanationGraphError, match="revalidation"):
        GraphBuilder().build(bundle, claims)
    assert dispatch == ["validate_bad_move"]


def test_mixed_family_package_rejected_without_fallback(dispatch):
    bundle, claims = package("p8-knight")
    dispatch.clear()
    tamper(bundle.groups[1], source_family=EvidenceSourceFamily.GOOD_MOVE_BENEFIT)
    with pytest.raises(ExplanationGraphError, match="exactly one supported source family"):
        GraphBuilder().build(bundle, claims)
    assert dispatch == []


def test_string_source_family_is_not_dispatched(dispatch):
    bundle, claims = package("strong-forces")
    dispatch.clear()
    tamper(bundle.groups[0], source_family="good_move_benefit")
    with pytest.raises(ExplanationGraphError, match="EvidenceSourceFamily"):
        GraphBuilder().build(bundle, claims)
    assert dispatch == []


def test_empty_package_is_family_neutral(dispatch):
    bundle = EvidenceBundle("pos_base", (), ())
    graph = GraphBuilder().build(bundle, ())
    assert graph.evidence is bundle and graph.claims == () and graph.relations == ()
    assert ExplanationSelector().select(graph) == ExplanationSelection("pos_base", ())
    assert dispatch  # the canonical empty path still runs a P10 entrypoint


@pytest.mark.parametrize("mutation", ["claims-without-groups", "evidence-without-groups"])
def test_empty_like_package_is_never_normalized(mutation):
    bundle, claims = package("p8-exact-mate")
    empty = EvidenceBundle(bundle.base_position_id, (), ())
    if mutation == "claims-without-groups":
        args = (empty, claims)
    else:
        tamper(empty, evidence=bundle.evidence)
        args = (empty, ())
    with pytest.raises(ExplanationGraphError, match="completely empty"):
        GraphBuilder().build(*args)


@pytest.mark.parametrize(
    "mutation", ["not-bundle", "missing-claim", "reordered", "forced", "importance", "list"]
)
def test_invalid_p10_package_rejected(mutation):
    bundle, claims = package("p8-defender")
    if mutation == "not-bundle":
        args = (bundle.evidence, claims)
    elif mutation == "missing-claim":
        args = (bundle, claims[:-1])
    elif mutation == "reordered":
        args = (bundle, claims[::-1])
    elif mutation == "forced":
        args = (bundle, (*claims[:-1], replace(claims[-1], confidence=_C.FORCED)))
    elif mutation == "importance":
        args = (bundle, (*claims[:-1], replace(claims[-1], importance=1.0)))
    else:
        args = (bundle, list(claims))
    with pytest.raises(ExplanationGraphError):
        GraphBuilder().build(*args)


def test_builder_requires_p10_to_return_the_exact_claim_tuple(monkeypatch):
    bundle, claims = package("p8-knight")
    monkeypatch.setattr(ClaimValidator, "validate_bad_move", lambda self, b, c: tuple(x for x in c))
    with pytest.raises(ExplanationGraphError, match="exact supplied claim tuple"):
        GraphBuilder().build(bundle, claims)


# ---- ExplanationGraphValidator ------------------------------------------------------------------


@pytest.mark.parametrize("name", ["p8-defender", "strong-direct_mate", "pres-mate_all"])
def test_manually_constructed_valid_graph_accepted_and_revalidated(name, dispatch):
    graph = manual(name)
    dispatch.clear()
    assert ExplanationGraphValidator().validate(graph) is graph
    assert ExplanationGraphValidator().validate(graph) is graph
    assert len(dispatch) == 2  # P10 runs on every validation, never cached as trust


def _relation(**changes):
    values = {
        "relation_id": "rel_001",
        "base_position_id": "",
        "source_claim_id": "cl_001",
        "kind": ExplanationRelationKind.CAUSES,
        "target_claim_id": "cl_002",
        "evidence_ids": (),
    }
    values.update(changes)
    return ExplanationRelation(**values)


def _knight_relation(graph, kind, evidence_ids=()):
    return (
        _relation(base_position_id=graph.base_position_id, kind=kind, evidence_ids=evidence_ids),
    )


RELATION_INJECTIONS = {
    # Shared c3 knight, same PV, predicate pairing, endpoint-evidence union: none is authority.
    "shared-piece-causes": (ExplanationRelationKind.CAUSES, ()),
    "same-pv-leads-to": (ExplanationRelationKind.LEADS_TO, ()),
    "predicate-pair-enables": (ExplanationRelationKind.ENABLES, ()),
    "endpoint-evidence-supports": (ExplanationRelationKind.SUPPORTS, "union"),
}


@pytest.mark.parametrize("name", sorted(RELATION_INJECTIONS))
def test_any_relation_is_rejected_while_no_rule_is_active(name):
    graph = manual("p8-knight")
    kind, evidence = RELATION_INJECTIONS[name]
    if evidence == "union":
        evidence = tuple(sorted({*graph.claims[0].evidence_ids, *graph.claims[1].evidence_ids}))
    relations = _knight_relation(graph, kind, evidence)
    with pytest.raises(ExplanationGraphError, match="no relation rule is active"):
        ExplanationGraphValidator().validate(manual("p8-knight", relations=relations))


def test_preservation_contrast_relation_rejected():
    graph = manual("pres-mate_all")
    relations = _knight_relation(graph, ExplanationRelationKind.CONTRASTS_WITH)
    with pytest.raises(ExplanationGraphError, match="no relation rule is active"):
        ExplanationGraphValidator().validate(manual("pres-mate_all", relations=relations))


def _tamper_graph(graph, mutation):
    claim = graph.claims[0]
    if mutation == "graph-base":
        tamper(graph, base_position_id="pos_foreign")
    elif mutation == "relations-list":
        tamper(graph, relations=[])
    elif mutation == "evidence-type":
        tamper(graph, evidence=graph.claims)
    elif mutation == "claim-forced":
        tamper(claim, confidence=_C.FORCED)
    elif mutation == "claim-scope":
        tamper(claim, scope=ClaimScope.TESTED_RESPONSE)
    elif mutation == "claim-object":
        tamper(claim, objects=claim.objects[:-1])
    elif mutation == "claim-importance":
        tamper(claim, importance=0.5)
    elif mutation == "evidence-provenance":
        group = graph.evidence.groups[0]
        tamper(group, required_probe_results=group.required_probe_results[:1])
    elif mutation == "evidence-record-base":
        tamper(graph.evidence.evidence[0], base_position_id="pos_foreign")
    elif mutation == "claims-reordered":
        tamper(graph, claims=graph.claims[::-1])
    else:
        tamper(graph, claims=graph.claims[:-1])


TAMPERS = [
    "graph-base",
    "relations-list",
    "evidence-type",
    "claim-forced",
    "claim-scope",
    "claim-object",
    "claim-importance",
    "evidence-provenance",
    "evidence-record-base",
    "claims-reordered",
    "claims-dropped",
]


@pytest.mark.parametrize("mutation", TAMPERS)
def test_tampered_graph_rejected_by_validator_and_selector(mutation):
    graph = built("p8-defender")
    _tamper_graph(graph, mutation)
    with pytest.raises(ExplanationGraphError):
        ExplanationGraphValidator().validate(graph)
    with pytest.raises(ExplanationGraphError):
        ExplanationSelector().select(graph)


def test_graph_validator_requires_exact_graph_type():
    graph = built("p8-knight")
    with pytest.raises(ExplanationGraphError, match="ExplanationGraph"):
        ExplanationGraphValidator().validate((graph.evidence, graph.claims))


# ---- frozen priority and family maps ------------------------------------------------------------


def test_priority_map_is_exactly_the_14_real_p10_pairs():
    real_pairs = {
        (claim.predicate, claim.confidence) for name in REAL for claim in package(name)[1]
    }
    assert len(real_pairs) == 14
    assert set(PRIORITY_TIERS) == real_pairs
    assert PRIORITY_TIERS == {
        (_P.DELIVERS_CHECKMATE, _C.EXACT): 0,
        (_P.ALLOWS_CHECKMATE, _C.EXACT): 0,
        (_P.ALLOWS_CHECKMATE, _C.ENGINE_VERIFIED): 1,
        (_P.LEADS_TO_MATE, _C.ENGINE_VERIFIED): 1,
        (_P.AVOIDS_REPRESENTATIVE_MATE_FAILURE, _C.ENGINE_VERIFIED): 1,
        (_P.ALLOWS_MATERIAL_LOSS, _C.ENGINE_VERIFIED): 1,
        (_P.WINS_MATERIAL, _C.ENGINE_VERIFIED): 1,
        (_P.AVOIDS_REPRESENTATIVE_MATERIAL_LOSS, _C.ENGINE_VERIFIED): 1,
        (_P.LEAVES_PIECE_HANGING, _C.ENGINE_VERIFIED): 2,
        (_P.REMOVES_DEFENDER, _C.ENGINE_VERIFIED): 2,
        (_P.ALLOWS_FORK, _C.ENGINE_VERIFIED): 2,
        (_P.FORCES_RESPONSE, _C.EXACT): 3,
        (_P.THREATENS_MATE_IF_IGNORED, _C.ENGINE_VERIFIED): 4,
        (_P.THREATENS_MATERIAL_IF_IGNORED, _C.ENGINE_VERIFIED): 4,
    }
    for (predicate, confidence), tier in PRIORITY_TIERS.items():
        assert priority_tier(predicate, confidence) == tier


UNLISTED = [pair for pair in product(_P, _C) if pair not in PRIORITY_TIERS]


def test_every_unlisted_pair_fails_closed_including_all_forced():
    assert len(UNLISTED) == len(_P) * len(_C) - 14 == 25
    assert {p for p, c in UNLISTED if c is _C.FORCED} == set(_P)
    for predicate, confidence in UNLISTED:
        with pytest.raises(ExplanationSelectionError, match="no frozen priority"):
            priority_tier(predicate, confidence)


@pytest.mark.parametrize("pair", [("delivers_checkmate", _C.EXACT), (_P.FORCES_RESPONSE, "exact")])
def test_priority_requires_exact_enum_members(pair):
    with pytest.raises(ExplanationSelectionError, match="exact P10"):
        priority_tier(*pair)


def test_family_map_partitions_all_13_predicates():
    assert set(SELECTION_FAMILIES) == set(_P) and len(SELECTION_FAMILIES) == 13
    members = {family: {p for p, f in SELECTION_FAMILIES.items() if f is family} for family in _F}
    assert members == {
        _F.MATE_OUTCOME: {
            _P.ALLOWS_CHECKMATE,
            _P.DELIVERS_CHECKMATE,
            _P.LEADS_TO_MATE,
            _P.AVOIDS_REPRESENTATIVE_MATE_FAILURE,
        },
        _F.MATERIAL_OUTCOME: {
            _P.ALLOWS_MATERIAL_LOSS,
            _P.WINS_MATERIAL,
            _P.AVOIDS_REPRESENTATIVE_MATERIAL_LOSS,
        },
        _F.TACTICAL_MECHANISM: {_P.LEAVES_PIECE_HANGING, _P.REMOVES_DEFENDER, _P.ALLOWS_FORK},
        _F.FORCED_RESPONSE: {_P.FORCES_RESPONSE},
        _F.TESTED_THREAT: {_P.THREATENS_MATE_IF_IGNORED, _P.THREATENS_MATERIAL_IF_IGNORED},
    }
    assert sum(len(m) for m in members.values()) == 13  # no overlap
    with pytest.raises(ExplanationSelectionError):
        selection_family("leaves_piece_hanging")


# ---- frozen selection algorithm (pure ordering over synthetic canonical tuples) -----------------

BASE_ID = "pos_base"
PLAYED = MoveClaimEntity(ChessMove("e2e4"), BASE_ID)
KNIGHT = base_frame_piece_entity(BASE_ID, BasePieceRef(Color.WHITE, PieceType.KNIGHT, "g1"))


def synthetic(*pairs) -> tuple[ExplanationClaim, ...]:
    return tuple(
        ExplanationClaim(
            claim_id=f"cl_{i:03d}",
            base_position_id=BASE_ID,
            subject=PLAYED,
            predicate=predicate,
            objects=(KNIGHT,),
            confidence=confidence,
            scope=required_claim_scope(predicate),
            evidence_ids=(f"ev_{i:03d}",),
        )
        for i, (predicate, confidence) in enumerate(pairs, start=1)
    )


EV = _C.ENGINE_VERIFIED


@pytest.mark.parametrize(
    ("pairs", "expected"),
    [
        ((), ()),
        # Tier 0 exact mate outranks everything; then tiers 1 and 2 fill the cap of three.
        (
            (
                (_P.THREATENS_MATE_IF_IGNORED, EV),
                (_P.FORCES_RESPONSE, _C.EXACT),
                (_P.LEAVES_PIECE_HANGING, EV),
                (_P.WINS_MATERIAL, EV),
                (_P.DELIVERS_CHECKMATE, _C.EXACT),
            ),
            ("cl_005", "cl_004", "cl_003"),
        ),
        # Tier 1 > 2 > 3 > 4 when the higher families are absent.
        (
            ((_P.THREATENS_MATERIAL_IF_IGNORED, EV), (_P.FORCES_RESPONSE, _C.EXACT)),
            ("cl_002", "cl_001"),
        ),
        (
            ((_P.FORCES_RESPONSE, _C.EXACT), (_P.ALLOWS_FORK, EV)),
            ("cl_002", "cl_001"),
        ),
        # Same tier: original canonical tuple position, no second predicate ranking.
        (
            ((_P.ALLOWS_MATERIAL_LOSS, EV), (_P.ALLOWS_CHECKMATE, EV)),
            ("cl_001", "cl_002"),
        ),
        # Same family: only the first in priority order survives.
        (
            ((_P.LEAVES_PIECE_HANGING, EV), (_P.REMOVES_DEFENDER, EV), (_P.ALLOWS_FORK, EV)),
            ("cl_001",),
        ),
        (
            (
                (_P.THREATENS_MATE_IF_IGNORED, EV),
                (_P.THREATENS_MATERIAL_IF_IGNORED, EV),
            ),
            ("cl_001",),
        ),
        # Exact mate suppresses the engine-verified mate of the same family.
        (
            ((_P.ALLOWS_CHECKMATE, EV), (_P.ALLOWS_CHECKMATE, _C.EXACT)),
            ("cl_002",),
        ),
        # Four families present: the cap keeps the first three in priority order.
        (
            (
                (_P.THREATENS_MATE_IF_IGNORED, EV),
                (_P.FORCES_RESPONSE, _C.EXACT),
                (_P.REMOVES_DEFENDER, EV),
                (_P.WINS_MATERIAL, EV),
            ),
            ("cl_004", "cl_003", "cl_002"),
        ),
    ],
)
def test_frozen_selection_order(pairs, expected):
    assert select_claim_ids(synthetic(*pairs)) == expected


def test_selection_algorithm_fails_closed_on_unlisted_pair():
    claims = synthetic((_P.LEAVES_PIECE_HANGING, EV))
    tamper(claims[0], confidence=_C.EXACT)
    with pytest.raises(ExplanationSelectionError, match="no frozen priority"):
        select_claim_ids(claims)


# ---- ExplanationSelector over real graphs -------------------------------------------------------

REAL_SELECTIONS = {
    "p8-knight": ("cl_002", "cl_001"),  # material consequence, then hanging mechanism
    "p8-defender": ("cl_003", "cl_001"),  # REMOVES_DEFENDER suppressed by its family
    "p8-fork": ("cl_002", "cl_001"),
    "p8-exact-mate": ("cl_001",),
    "p8-engine-mate": ("cl_001",),
    "strong-forces": ("cl_001",),
    "strong-exact_mate": ("cl_001",),
    "strong-direct_mate": ("cl_002", "cl_001"),  # LEADS_TO_MATE before FORCES_RESPONSE
    "strong-ignored_mate": ("cl_001",),
    "strong-direct_material": ("cl_001",),
    "strong-ignored_material": ("cl_001",),
    "pres-mate_all": ("cl_001", "cl_002"),
    "pres-mate_subset": ("cl_001", "cl_002"),
    "pres-engine_mate": ("cl_001",),
    "pres-replayed_engine_mate": ("cl_001", "cl_002"),
    "pres-material_all": ("cl_001",),
    "pres-material_subset": ("cl_001",),
}


def test_real_selection_table_covers_every_real_package():
    assert set(REAL_SELECTIONS) == set(REAL)


@pytest.mark.parametrize("name", sorted(REAL))
def test_selector_on_real_graphs_leaves_claims_unchanged(name):
    graph = built(name)
    before = repr(graph.claims)
    selection = ExplanationSelector().select(graph)
    assert selection == ExplanationSelection(graph.base_position_id, REAL_SELECTIONS[name], ())
    assert repr(graph.claims) == before
    assert all(claim.importance is None for claim in graph.claims)
    assert ExplanationSelectionValidator().validate(graph, selection) is selection


@pytest.mark.parametrize("name", ["pres-mate_all", "pres-material_subset"])
def test_preservation_scope_is_preserved_through_selection(name):
    graph = built(name)
    for claim_id in ExplanationSelector().select(graph).selected_claim_ids:
        (claim,) = [c for c in graph.claims if c.claim_id == claim_id]
        assert claim.scope is ClaimScope.REPRESENTATIVE_ALTERNATIVES
        assert claim.confidence is _C.ENGINE_VERIFIED


def test_selector_validates_graph_before_selecting(monkeypatch):
    graph = built("p8-knight")
    calls = []
    original = ExplanationGraphValidator.validate

    def spy(self, value):
        calls.append(value)
        return original(self, value)

    monkeypatch.setattr(ExplanationGraphValidator, "validate", spy)
    ExplanationSelector().select(graph)
    assert calls == [graph]


# ---- ExplanationSelectionValidator --------------------------------------------------------------


def _check(graph, selection, error=ExplanationSelectionError, match=None):
    with pytest.raises(error, match=match):
        ExplanationSelectionValidator().validate(graph, selection)


@pytest.mark.parametrize(
    "ids",
    [
        ("cl_002",),  # missing selected claim
        ("cl_002", "cl_001", "cl_003"),  # extra claim from a suppressed family
        ("cl_001", "cl_002"),  # wrong order
        ("cl_001", "cl_003"),  # second claim of the suppressed tactical family
    ],
)
def test_selection_must_equal_exact_recomputation(ids):
    graph = built("p8-defender")
    assert ExplanationSelector().select(graph).selected_claim_ids == ("cl_003", "cl_001")
    _check(graph, ExplanationSelection(graph.base_position_id, ids), match="exact frozen")


def test_wrong_base_and_type_rejected():
    graph = built("p8-knight")
    _check(graph, ExplanationSelection("pos_foreign", ("cl_002", "cl_001")), match="base")
    _check(graph, ("cl_002", "cl_001"), match="ExplanationSelection")


def test_fourth_claim_and_relation_selection_rejected():
    graph = built("p8-knight")
    valid = ExplanationSelector().select(graph)
    tamper(valid, selected_claim_ids=("cl_002", "cl_001", "cl_003", "cl_004"))
    _check(graph, valid, match="exact frozen")
    relation = ExplanationSelection(graph.base_position_id, ("cl_002", "cl_001"), ("rel_001",))
    _check(graph, relation, match="exact frozen")


def test_tampered_list_ids_rejected_even_when_equal_in_content():
    graph = built("p8-knight")
    selection = ExplanationSelector().select(graph)
    tamper(selection, selected_claim_ids=list(selection.selected_claim_ids))
    _check(graph, selection, match="exact frozen")


def test_same_base_same_ids_from_another_graph_do_not_establish_trust():
    full = built("p8-knight")  # LEAVES_PIECE_HANGING cl_001 + ALLOWS_MATERIAL_LOSS cl_002
    bundle = p8.evidence(p8.only_kind(p8.knight(), p8.Kind.NEWLY_HANGING_PIECE))
    single = GraphBuilder().build(bundle, p8.claims(bundle))
    assert single.base_position_id == full.base_position_id
    assert single.claims[0].claim_id == "cl_001" and full.claims[0].claim_id == "cl_001"
    stale_from_single = ExplanationSelector().select(single)
    stale_from_full = ExplanationSelector().select(full)
    _check(full, stale_from_single, match="exact frozen")
    _check(single, stale_from_full, match="exact frozen")


def test_selection_validation_revalidates_the_graph():
    graph = built("p8-knight")
    selection = ExplanationSelector().select(graph)
    tamper(graph.claims[0], confidence=_C.FORCED)
    _check(graph, selection, error=ExplanationGraphError)


# ---- dependency guards --------------------------------------------------------------------------

P11_MODULES = (graph_builder, graph_validator, selector)
FORBIDDEN = (
    "calliope.adapters",
    "calliope.application",
    "calliope.contracts",
    "calliope.services.commentary",
    "calliope.services.counterfactual",
    "calliope.services.explanation.bad_move",
    "calliope.services.explanation.good_move",
    "calliope.services.explanation.evidence_builder",
    "calliope.services.explanation.claim_builder",
    "calliope.domain.analysis",
    "calliope.domain.engine",
    "chess",
    "stockfish",
)


@pytest.mark.parametrize("module", P11_MODULES, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_p11_services_depend_only_on_domain_and_p10_validator(module):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    for name in imported:
        assert not any(name == root or name.startswith(f"{root}.") for root in FORBIDDEN), name
    allowed = {
        "__future__",
        "enum",
        "calliope.errors",
        "calliope.domain.explanation",
        "calliope.domain.explanation.graph",
        "calliope.services.explanation.claim_validator",
        "calliope.services.explanation.graph_validator",
    }
    assert imported <= allowed, imported - allowed
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not attributes & {
        "importance",
        "score",
        "cp",
        "mate",
        "wdl",
        "rank",
        "pv",
        "lines",
        "engine_analysis",
        "cp_loss",
        "expected_score_loss",
        "required_probe_results",
        "material_evidence",
    }
