"""P11-I0: structural ExplanationRelation / ExplanationGraph / ExplanationSelection values."""

import ast
from dataclasses import FrozenInstanceError, fields, replace
from enum import StrEnum
from pathlib import Path

import pytest

import calliope
import calliope.domain.explanation as explanation_package
from calliope.domain.analysis import BasePieceRef
from calliope.domain.chess import ChessMove, Color, PieceType
from calliope.domain.explanation import (
    ClaimConfidence,
    ClaimPredicate,
    ClaimScope,
    EvidenceBundle,
    ExplanationClaim,
    ExplanationGraph,
    ExplanationRelation,
    ExplanationRelationKind,
    ExplanationSelection,
    MoveClaimEntity,
    base_frame_piece_entity,
    mint_relation_id,
)
from calliope.domain.explanation.graph import MAX_SELECTED_CLAIMS
from calliope.errors import (
    CalliopeError,
    ExplanationClaimError,
    ExplanationEvidenceError,
    ExplanationGraphError,
    ExplanationSelectionError,
    IncompatibleClaimEvidenceError,
)

BASE_ID = "pos_base"
OTHER_ID = "pos_other"
PLAYED = MoveClaimEntity(ChessMove("e2e4"), BASE_ID)
KNIGHT = BasePieceRef(Color.WHITE, PieceType.KNIGHT, "g1")
_K = ExplanationRelationKind


def claim(claim_id="cl_001", base=BASE_ID, evidence_ids=("ev_001",)) -> ExplanationClaim:
    return ExplanationClaim(
        claim_id=claim_id,
        base_position_id=base,
        subject=MoveClaimEntity(PLAYED.move, base),
        predicate=ClaimPredicate.LEAVES_PIECE_HANGING,
        objects=(base_frame_piece_entity(base, KNIGHT),),
        confidence=ClaimConfidence.ENGINE_VERIFIED,
        scope=ClaimScope.LOCAL,
        evidence_ids=evidence_ids,
    )


CLAIMS = (claim("cl_001"), claim("cl_002", evidence_ids=("ev_002",)), claim("cl_003"))
EMPTY_BUNDLE = EvidenceBundle(BASE_ID, (), ())


def relation(**changes) -> ExplanationRelation:
    values = {
        "relation_id": "rel_001",
        "base_position_id": BASE_ID,
        "source_claim_id": "cl_001",
        "kind": _K.CAUSES,
        "target_claim_id": "cl_002",
        "evidence_ids": ("ev_001", "ev_002"),
    }
    values.update(changes)
    return ExplanationRelation(**values)


def graph(**changes) -> ExplanationGraph:
    values = {
        "base_position_id": BASE_ID,
        "evidence": EMPTY_BUNDLE,
        "claims": CLAIMS,
        "relations": (),
    }
    values.update(changes)
    return ExplanationGraph(**values)


def selection(**changes) -> ExplanationSelection:
    values = {"base_position_id": BASE_ID, "selected_claim_ids": ("cl_002", "cl_001")}
    values.update(changes)
    return ExplanationSelection(**values)


# -- errors --


def test_p11_errors_are_independent_calliope_errors():
    for error in (ExplanationGraphError, ExplanationSelectionError):
        assert issubclass(error, CalliopeError)
        assert error.__bases__ == (CalliopeError,)
        for p10 in (
            ExplanationEvidenceError,
            ExplanationClaimError,
            IncompatibleClaimEvidenceError,
        ):
            assert not issubclass(error, p10)
            assert not issubclass(p10, error)
    assert not issubclass(ExplanationGraphError, ExplanationSelectionError)
    assert not issubclass(ExplanationSelectionError, ExplanationGraphError)


# -- vocabulary --


def test_relation_vocabulary_is_exact_and_ordered():
    assert [(k.name, k.value) for k in ExplanationRelationKind] == [
        ("ENABLES", "enables"),
        ("PREVENTS", "prevents"),
        ("LEADS_TO", "leads_to"),
        ("CAUSES", "causes"),
        ("CONTRASTS_WITH", "contrasts_with"),
        ("SUPPORTS", "supports"),
    ]


# -- relation ids --


@pytest.mark.parametrize(("index", "value"), [(1, "rel_001"), (42, "rel_042"), (999, "rel_999")])
def test_mint_relation_id(index, value):
    assert mint_relation_id(index) == value
    assert relation(relation_id=value).relation_id == value


def test_relation_ids_beyond_three_digits_stay_canonical():
    assert mint_relation_id(1000) == "rel_1000"
    assert relation(relation_id="rel_1000").relation_id == "rel_1000"


@pytest.mark.parametrize("index", [0, -1, True, False, 1.0, "1", None])
def test_mint_relation_id_rejects_non_positive_or_non_int(index):
    with pytest.raises(ExplanationGraphError):
        mint_relation_id(index)


MALFORMED_REL = ["", "rel_1", "rel_01", "rel_000", "rel_0001", "REL_001", "rel-001", "cl_001", 1]


@pytest.mark.parametrize("value", MALFORMED_REL)
def test_malformed_relation_id_rejected(value):
    with pytest.raises(ExplanationGraphError, match="relation_id"):
        relation(relation_id=value)


# -- ExplanationRelation --


def test_relation_accepts_structural_future_shape():
    value = relation()
    assert value.kind is _K.CAUSES
    # Empty evidence is structurally representable; A0 freezes no sufficiency rule.
    assert relation(evidence_ids=()).evidence_ids == ()


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"base_position_id": ""}, "base_position_id"),
        ({"source_claim_id": "cl_1"}, "source"),
        ({"source_claim_id": "rel_001"}, "source"),
        ({"target_claim_id": "ev_002"}, "target"),
        ({"target_claim_id": None}, "target"),
        ({"target_claim_id": "cl_001"}, "differ"),
        ({"kind": "causes"}, "ExplanationRelationKind"),
        ({"kind": ClaimPredicate.LEAVES_PIECE_HANGING}, "ExplanationRelationKind"),
        ({"evidence_ids": ["ev_001"]}, "tuple"),
        ({"evidence_ids": ("ev_1",)}, "canonical"),
        ({"evidence_ids": ("cl_001",)}, "canonical"),
        ({"evidence_ids": ("ev_001", "ev_001")}, "unique"),
    ],
)
def test_relation_structural_invariants(changes, match):
    with pytest.raises(ExplanationGraphError, match=match):
        relation(**changes)


def test_relation_kind_rejects_foreign_enum_with_equal_value():
    class Foreign(StrEnum):
        CAUSES = "causes"

    with pytest.raises(ExplanationGraphError, match="ExplanationRelationKind"):
        relation(kind=Foreign.CAUSES)


# -- ExplanationGraph --


def test_empty_graph_with_empty_bundle():
    value = graph(claims=())
    assert value.evidence is EMPTY_BUNDLE and value.claims == () and value.relations == ()


def test_graph_holds_p10_objects_by_identity():
    value = graph()
    assert value.claims is CLAIMS and value.evidence is EMPTY_BUNDLE
    assert graph(claims=CLAIMS[:1]).claims == CLAIMS[:1]


def test_graph_is_structural_only_not_a_p10_proof():
    # Claims citing evidence absent from the bundle still form a graph: P10 revalidation and
    # the empty-relation policy are service-level P11 GraphValidator responsibilities.
    assert graph().evidence.evidence == ()


def test_graph_accepts_structurally_valid_future_relations():
    relations = (
        relation(relation_id="rel_001", source_claim_id="cl_001", kind=_K.ENABLES),
        relation(relation_id="rel_002", source_claim_id="cl_001", kind=_K.CAUSES),
        relation(
            relation_id="rel_003",
            source_claim_id="cl_001",
            target_claim_id="cl_003",
            kind=_K.CAUSES,
        ),
        relation(
            relation_id="rel_004",
            source_claim_id="cl_002",
            target_claim_id="cl_001",
            kind=_K.ENABLES,
        ),
    )
    assert graph(relations=relations).relations == relations


def _two(first, second):
    return (first, replace(second, relation_id="rel_002"))


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"base_position_id": ""}, "base_position_id"),
        ({"evidence": ()}, "EvidenceBundle"),
        ({"evidence": EvidenceBundle(OTHER_ID, (), ())}, "another base"),
        ({"claims": list(CLAIMS)}, "claims must be a tuple"),
        ({"claims": (CLAIMS[0], "cl_002")}, "ExplanationClaim"),
        ({"claims": (CLAIMS[0], claim("cl_002", base=OTHER_ID))}, "another base"),
        ({"claims": (CLAIMS[0], CLAIMS[0])}, "unique"),
        ({"relations": [relation()]}, "relations must be a tuple"),
        ({"relations": ("rel_001",)}, "ExplanationRelation"),
        ({"relations": (relation(base_position_id=OTHER_ID),)}, "another base"),
        ({"relations": (relation(source_claim_id="cl_009"),)}, "source claim"),
        ({"relations": (relation(target_claim_id="cl_009"),)}, "target claim"),
        ({"relations": (relation(), relation(kind=_K.ENABLES))}, "unique"),
        (
            {"relations": _two(relation(), relation(evidence_ids=("ev_003",)))},
            r"duplicate \(source, kind, target\)",
        ),
        (
            {"relations": _two(relation(kind=_K.CAUSES), relation(kind=_K.ENABLES))},
            "canonical order",
        ),
        (
            {
                "relations": _two(
                    relation(target_claim_id="cl_003"), relation(target_claim_id="cl_002")
                )
            },
            "canonical order",
        ),
        ({"relations": (relation(relation_id="rel_002"),)}, "tuple positions"),
    ],
)
def test_graph_structural_invariants(changes, match):
    with pytest.raises(ExplanationGraphError, match=match):
        graph(**changes)


def test_graph_rejects_tampered_noncanonical_claim_id():
    tampered = claim("cl_002")
    object.__setattr__(tampered, "claim_id", "cl_2")
    with pytest.raises(ExplanationGraphError, match="canonical"):
        graph(claims=(CLAIMS[0], tampered))


def test_relation_order_uses_numeric_ordinals_not_string_order():
    claims = tuple(claim(f"cl_{i:03d}") for i in range(1, 1001))
    relations = (
        relation(relation_id="rel_001", source_claim_id="cl_999", target_claim_id="cl_001"),
        relation(relation_id="rel_002", source_claim_id="cl_1000", target_claim_id="cl_001"),
    )
    assert graph(claims=claims, relations=relations).relations == relations


# -- ExplanationSelection --


@pytest.mark.parametrize(
    "ids", [(), ("cl_001",), ("cl_003", "cl_001", "cl_002"), ("cl_010", "cl_002", "cl_001")]
)
def test_selection_accepts_up_to_three_claims_in_supplied_order(ids):
    assert selection(selected_claim_ids=ids).selected_claim_ids == ids
    assert MAX_SELECTED_CLAIMS == 3


def test_selection_accepts_structural_relation_ids():
    value = selection(selected_relation_ids=("rel_002", "rel_001"))
    assert value.selected_relation_ids == ("rel_002", "rel_001")
    assert selection().selected_relation_ids == ()


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"base_position_id": ""}, "base_position_id"),
        ({"selected_claim_ids": ["cl_001"]}, "tuple"),
        ({"selected_claim_ids": ("cl_1",)}, "canonical"),
        ({"selected_claim_ids": ("rel_001",)}, "canonical"),
        ({"selected_claim_ids": ("cl_001", "cl_001")}, "unique"),
        ({"selected_claim_ids": ("cl_001", "cl_002", "cl_003", "cl_004")}, "at most 3"),
        ({"selected_relation_ids": ["rel_001"]}, "tuple"),
        ({"selected_relation_ids": ("rel_1",)}, "canonical"),
        ({"selected_relation_ids": ("cl_001",)}, "canonical"),
        ({"selected_relation_ids": ("rel_001", "rel_001")}, "unique"),
    ],
)
def test_selection_structural_invariants(changes, match):
    with pytest.raises(ExplanationSelectionError, match=match):
        selection(**changes)


def test_selection_does_not_resolve_ids_against_any_graph():
    assert not {f.name for f in fields(ExplanationSelection)} & {"graph", "claims", "relations"}
    assert selection(selected_claim_ids=("cl_999",)).selected_claim_ids == ("cl_999",)


# -- immutability --


@pytest.mark.parametrize(
    ("value", "field"),
    [
        (relation(), "kind"),
        (graph(), "relations"),
        (selection(), "selected_claim_ids"),
    ],
)
def test_values_are_frozen_and_slotted(value, field):
    assert type(value).__dataclass_params__.frozen
    assert not hasattr(value, "__dict__")
    with pytest.raises(FrozenInstanceError):
        setattr(value, field, getattr(value, field))


# -- exports and dependency direction --


P11_EXPORTS = {
    "ExplanationGraph",
    "ExplanationRelation",
    "ExplanationRelationKind",
    "ExplanationSelection",
    "mint_relation_id",
}


def test_p11_domain_exports_are_internal_only():
    assert P11_EXPORTS <= set(explanation_package.__all__)
    for name in P11_EXPORTS:
        assert not hasattr(calliope, name), name


GRAPH_MODULE = Path(explanation_package.__file__).parent / "graph.py"
FORBIDDEN_IMPORT_ROOTS = (
    "calliope.services",
    "calliope.application",
    "calliope.adapters",
    "calliope.contracts",
    "chess",
    "stockfish",
    "subprocess",
)


def test_graph_module_imports_only_domain_values():
    tree = ast.parse(GRAPH_MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            imported.add(node.module or "")
    for name in imported:
        for root in FORBIDDEN_IMPORT_ROOTS:
            assert name != root and not name.startswith(f"{root}."), name
    assert {n for n in imported if n.startswith("calliope")} <= {
        "calliope.errors",
        "calliope.domain.explanation.claim",
        "calliope.domain.explanation.evidence",
    }


def test_no_p11_service_or_policy_in_domain():
    for name in (
        "GraphBuilder",
        "ExplanationGraphValidator",
        "ExplanationSelector",
        "validate_selection",
        "ACTIVE_RELATION_RULES",
        "ClaimValidator",
    ):
        assert not hasattr(explanation_package, name), name
    source = GRAPH_MODULE.read_text(encoding="utf-8")
    assert "ACTIVE_RELATION_RULES" not in source
    assert "importance" not in source
