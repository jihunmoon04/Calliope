"""P11-I3: adversarial, mutation and determinism gate for the P11 trust boundary.

Uses the reviewed P10 unit scenario corpus (python-chess rules + scripted P7 engine); these
are *not* real-Stockfish packages.  The real-engine P11 gate lives with the P10-I6 Stockfish
integration tests.  No production behaviour is changed here: mutation tests monkeypatch the
frozen tables/algorithm only to prove that the oracles below would catch such a change.
"""

import os
import subprocess
import sys
from dataclasses import replace
from itertools import product
from pathlib import Path

import _p8_claim_scenarios as p8
import _p9_preservation_claim_scenarios as pres
import _p9_strong_claim_scenarios as strong
import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.adapters.stockfish import StockfishAdapter
from calliope.domain.analysis import BasePieceRef
from calliope.domain.chess import ChessMove, Color, PieceType
from calliope.domain.engine import EngineScore
from calliope.domain.explanation import (
    ClaimConfidence,
    ClaimPredicate,
    ClaimScope,
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
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.explanation import (
    ExplanationGraphValidator,
    ExplanationSelectionValidator,
    ExplanationSelector,
    GraphBuilder,
)
from calliope.services.explanation import selector as selector_module
from calliope.services.explanation.selector import (
    SelectionFamily,
    priority_tier,
    select_claim_ids,
    selection_family,
)

tamper = p8.tamper
_P = ClaimPredicate
_C = ClaimConfidence
_F = SelectionFamily
EV = _C.ENGINE_VERIFIED
REPO = Path(__file__).resolve().parents[4]

CORPUS = {
    "p8-knight": (p8.knight, p8),
    "p8-defender": (p8.defender, p8),
    "p8-fork": (p8.fork, p8),
    "p8-exact-mate": (p8.exact_mate, p8),
    "p8-engine-mate": (p8.engine_mate, p8),
    **{f"strong-{make.__name__}": (make, strong) for make in strong.SCENARIOS},
    **{f"pres-{make.__name__}": (make, pres) for make in pres.SCENARIOS},
}

# Independent oracle copies of the frozen A0 tables and the expected corpus selections.
FROZEN_TIERS = {
    (_P.DELIVERS_CHECKMATE, _C.EXACT): 0,
    (_P.ALLOWS_CHECKMATE, _C.EXACT): 0,
    (_P.ALLOWS_CHECKMATE, EV): 1,
    (_P.LEADS_TO_MATE, EV): 1,
    (_P.AVOIDS_REPRESENTATIVE_MATE_FAILURE, EV): 1,
    (_P.ALLOWS_MATERIAL_LOSS, EV): 1,
    (_P.WINS_MATERIAL, EV): 1,
    (_P.AVOIDS_REPRESENTATIVE_MATERIAL_LOSS, EV): 1,
    (_P.LEAVES_PIECE_HANGING, EV): 2,
    (_P.REMOVES_DEFENDER, EV): 2,
    (_P.ALLOWS_FORK, EV): 2,
    (_P.FORCES_RESPONSE, _C.EXACT): 3,
    (_P.THREATENS_MATE_IF_IGNORED, EV): 4,
    (_P.THREATENS_MATERIAL_IF_IGNORED, EV): 4,
}
FROZEN_FAMILIES = {
    _P.ALLOWS_CHECKMATE: _F.MATE_OUTCOME,
    _P.DELIVERS_CHECKMATE: _F.MATE_OUTCOME,
    _P.LEADS_TO_MATE: _F.MATE_OUTCOME,
    _P.AVOIDS_REPRESENTATIVE_MATE_FAILURE: _F.MATE_OUTCOME,
    _P.ALLOWS_MATERIAL_LOSS: _F.MATERIAL_OUTCOME,
    _P.WINS_MATERIAL: _F.MATERIAL_OUTCOME,
    _P.AVOIDS_REPRESENTATIVE_MATERIAL_LOSS: _F.MATERIAL_OUTCOME,
    _P.LEAVES_PIECE_HANGING: _F.TACTICAL_MECHANISM,
    _P.REMOVES_DEFENDER: _F.TACTICAL_MECHANISM,
    _P.ALLOWS_FORK: _F.TACTICAL_MECHANISM,
    _P.FORCES_RESPONSE: _F.FORCED_RESPONSE,
    _P.THREATENS_MATE_IF_IGNORED: _F.TESTED_THREAT,
    _P.THREATENS_MATERIAL_IF_IGNORED: _F.TESTED_THREAT,
}
CORPUS_SELECTIONS = {
    "p8-knight": ("cl_002", "cl_001"),
    "p8-defender": ("cl_003", "cl_001"),
    "p8-fork": ("cl_002", "cl_001"),
    "p8-exact-mate": ("cl_001",),
    "p8-engine-mate": ("cl_001",),
    "strong-forces": ("cl_001",),
    "strong-exact_mate": ("cl_001",),
    "strong-direct_mate": ("cl_002", "cl_001"),
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


def package(name):
    make, module = CORPUS[name]
    bundle = module.evidence(make())
    return bundle, module.claims(bundle)


def built(name):
    return GraphBuilder().build(*package(name))


def p11(graph):
    selection = ExplanationSelector().select(graph)
    assert ExplanationSelectionValidator().validate(graph, selection) is selection
    return selection


def signature(graph, selection):
    """Stable P11 semantics only: no cp, WDL, mate distance, PV or timing."""

    return (
        graph.base_position_id,
        tuple((c.claim_id, c.predicate, c.confidence, c.scope) for c in graph.claims),
        tuple(r.relation_id for r in graph.relations),
        selection.selected_claim_ids,
        selection.selected_relation_ids,
    )


# ---- full unit corpus acceptance (17 packages; not real Stockfish) -----------------------------


def test_corpus_oracle_is_complete():
    assert set(CORPUS_SELECTIONS) == set(CORPUS) and len(CORPUS) == 17


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_full_corpus_end_to_end_invariants(name):
    bundle, claims = package(name)
    before = repr(claims)
    graph = GraphBuilder().build(bundle, claims)
    assert ExplanationGraphValidator().validate(graph) is graph
    assert graph.evidence is bundle and graph.claims is claims and graph.relations == ()
    selection = p11(graph)
    assert selection.selected_claim_ids == CORPUS_SELECTIONS[name]
    assert selection.selected_relation_ids == ()
    assert 0 < len(selection.selected_claim_ids) <= 3
    by_id = {c.claim_id: c for c in claims}
    families = [selection_family(by_id[i].predicate) for i in selection.selected_claim_ids]
    assert len(set(families)) == len(families)
    assert repr(claims) == before and all(c.importance is None for c in claims)
    for _ in range(3):
        assert signature(graph, p11(graph)) == signature(graph, selection)


@pytest.mark.parametrize("name", [n for n in sorted(CORPUS) if n.startswith("pres-")])
def test_preservation_claims_survive_selection_unchanged(name):
    bundle, claims = package(name)
    frozen = [(c.predicate, c.confidence, c.scope, c.objects, c.evidence_ids) for c in claims]
    selection = p11(GraphBuilder().build(bundle, claims))
    assert frozen == [
        (c.predicate, c.confidence, c.scope, c.objects, c.evidence_ids) for c in claims
    ]
    for claim in claims:
        if claim.claim_id in selection.selected_claim_ids:
            assert claim.scope is ClaimScope.REPRESENTATIVE_ALTERNATIVES
            assert claim.confidence is EV


# ---- A. P10 package tampering -------------------------------------------------------------------


def _other_group_evidence(graph):
    return graph.evidence.groups[1].evidence_ids[0]


TAMPERS = {
    "forced": ("p8-defender", lambda g: tamper(g.claims[0], confidence=_C.FORCED)),
    "importance": ("p8-defender", lambda g: tamper(g.claims[0], importance=0.0)),
    "preservation-local": ("pres-mate_all", lambda g: tamper(g.claims[0], scope=ClaimScope.LOCAL)),
    "tested-local": ("strong-ignored_mate", lambda g: tamper(g.claims[0], scope=ClaimScope.LOCAL)),
    "predicate": ("p8-defender", lambda g: tamper(g.claims[0], predicate=_P.REMOVES_DEFENDER)),
    "confidence": ("p8-defender", lambda g: tamper(g.claims[2], confidence=_C.EXACT)),
    "object-removed": (
        "p8-defender",
        lambda g: tamper(g.claims[0], objects=g.claims[0].objects[1:]),
    ),
    "object-replaced": (
        "p8-knight",
        lambda g: tamper(
            g.claims[0],
            objects=(
                MoveClaimEntity(ChessMove("a2a3"), g.base_position_id),
                *g.claims[0].objects[1:],
            ),
        ),
    ),
    "evidence-id-removed": (
        "p8-knight",
        lambda g: tamper(g.claims[0], evidence_ids=g.claims[0].evidence_ids[:-1]),
    ),
    "evidence-id-replaced": (
        "p8-knight",
        lambda g: tamper(
            g.claims[0], evidence_ids=(*g.claims[0].evidence_ids[:-1], _other_group_evidence(g))
        ),
    ),
    "claims-reordered": ("p8-defender", lambda g: tamper(g, claims=g.claims[::-1])),
    "claim-dropped": ("p8-defender", lambda g: tamper(g, claims=g.claims[:-1])),
    "claim-extra": (
        "p8-defender",
        lambda g: tamper(g, claims=(*g.claims, replace(g.claims[0], claim_id="cl_004"))),
    ),
    "record-foreign-base": (
        "p8-knight",
        lambda g: tamper(g.evidence.evidence[0], base_position_id="pos_foreign"),
    ),
    "probe-provenance-shrunk": (
        "pres-material_all",
        lambda g: tamper(
            g.evidence.groups[0],
            required_probe_results=g.evidence.groups[0].required_probe_results[:-1],
        ),
    ),
    "mixed-family": (
        "p8-knight",
        lambda g: tamper(
            g.evidence.groups[1], source_family=EvidenceSourceFamily.GOOD_MOVE_BENEFIT
        ),
    ),
    "string-family": (
        "strong-forces",
        lambda g: tamper(g.evidence.groups[0], source_family="good_move_benefit"),
    ),
    "claim-id-noncanonical": ("p8-knight", lambda g: tamper(g.claims[1], claim_id="cl_2")),
    "claim-id-renumbered": ("p8-knight", lambda g: tamper(g.claims[1], claim_id="cl_009")),
    "evidence-id-noncanonical": (
        "p8-knight",
        lambda g: tamper(g.evidence.evidence[0], evidence_id="ev_1"),
    ),
}


@pytest.mark.parametrize("name", sorted(TAMPERS))
def test_p10_tampering_fails_closed_at_every_p11_entrypoint(name):
    fixture, change = TAMPERS[name]
    graph = built(fixture)
    selection = p11(graph)
    change(graph)
    with pytest.raises(ExplanationGraphError):
        ExplanationGraphValidator().validate(graph)
    with pytest.raises(ExplanationGraphError):
        ExplanationSelector().select(graph)
    with pytest.raises(ExplanationGraphError):
        ExplanationSelectionValidator().validate(graph, selection)


# ---- B. relation injection ----------------------------------------------------------------------


def _relation(graph, kind, source="cl_001", target="cl_002", evidence_ids=()):
    return ExplanationRelation(
        "rel_001", graph.base_position_id, source, kind, target, evidence_ids
    )


def _union(graph):
    return tuple(sorted({*graph.claims[0].evidence_ids, *graph.claims[1].evidence_ids}))


_K = ExplanationRelationKind
RELATIONS = {
    # Each looks "natural" to a human; none has relation-specific provenance in P10.
    "shared-piece-causes": ("p8-knight", lambda g: _relation(g, _K.CAUSES)),
    "same-pv-leads-to": ("p8-defender", lambda g: _relation(g, _K.LEADS_TO, target="cl_003")),
    "predicate-pair-enables": ("strong-direct_mate", lambda g: _relation(g, _K.ENABLES)),
    "endpoint-union-supports": (
        "p8-knight",
        lambda g: _relation(g, _K.SUPPORTS, evidence_ids=_union(g)),
    ),
    "preservation-contrasts": ("pres-mate_all", lambda g: _relation(g, _K.CONTRASTS_WITH)),
    "arbitrary-prevents": (
        "p8-fork",
        lambda g: _relation(g, _K.PREVENTS, "cl_002", "cl_001", ("ev_001",)),
    ),
}


@pytest.mark.parametrize("name", sorted(RELATIONS))
def test_every_relation_injection_rejected(name):
    fixture, make = RELATIONS[name]
    bundle, claims = package(fixture)
    graph = ExplanationGraph(bundle.base_position_id, bundle, claims, ())
    injected = replace(graph, relations=(make(graph),))  # structurally valid future shape
    for attempt in (
        lambda: ExplanationGraphValidator().validate(injected),
        lambda: ExplanationSelector().select(injected),
        lambda: ExplanationSelectionValidator().validate(injected, p11(graph)),
    ):
        with pytest.raises(ExplanationGraphError, match="no relation rule is active"):
            attempt()


# ---- C. priority map mutation gate --------------------------------------------------------------


def priority_violations() -> list:
    """Oracle: every one of the 39 pairs must match the frozen table or fail closed."""

    found = []
    for pair in product(_P, _C):
        try:
            tier = priority_tier(*pair)
        except ExplanationSelectionError:
            tier = None
        if tier != FROZEN_TIERS.get(pair):
            found.append((pair, tier))
    return found


def test_priority_oracle_accepts_current_production():
    assert priority_violations() == []
    assert len(FROZEN_TIERS) == 14
    unlisted = [pair for pair in product(_P, _C) if pair not in FROZEN_TIERS]
    assert len(unlisted) == 25
    for pair in (
        (_P.DELIVERS_CHECKMATE, EV),
        (_P.FORCES_RESPONSE, EV),
        (_P.LEAVES_PIECE_HANGING, _C.EXACT),
        (_P.AVOIDS_REPRESENTATIVE_MATE_FAILURE, _C.EXACT),
        *((p, _C.FORCED) for p in _P),
    ):
        assert pair in unlisted


class _FallbackTiers(dict):
    def get(self, key, default=None):
        return super().get(key, 4)


def _mutated_tiers(mutation):
    table = dict(selector_module.PRIORITY_TIERS)
    if mutation == "entry-deleted":
        del table[(_P.FORCES_RESPONSE, _C.EXACT)]
    elif mutation == "tier-changed":
        table[(_P.WINS_MATERIAL, EV)] = 2
    elif mutation == "forced-added":
        table[(_P.ALLOWS_CHECKMATE, _C.FORCED)] = 0
    else:
        return _FallbackTiers(table)
    return table


@pytest.mark.parametrize("mutation", ["entry-deleted", "tier-changed", "forced-added", "fallback"])
def test_priority_mutation_is_caught_by_oracle(mutation, monkeypatch):
    monkeypatch.setattr(selector_module, "PRIORITY_TIERS", _mutated_tiers(mutation))
    assert priority_violations()


# ---- D. family map mutation gate ----------------------------------------------------------------


def family_violations() -> list:
    found = []
    for predicate in _P:
        try:
            family = selection_family(predicate)
        except ExplanationSelectionError:
            family = None
        if family is not FROZEN_FAMILIES[predicate]:
            found.append((predicate, family))
    members = [p for p in _P if p in selector_module.SELECTION_FAMILIES]
    if len(selector_module.SELECTION_FAMILIES) != len(members) or len(members) != 13:
        found.append(("partition", len(selector_module.SELECTION_FAMILIES)))
    return found


def test_family_oracle_accepts_current_production():
    assert family_violations() == []
    assert set(FROZEN_FAMILIES) == set(_P) and set(FROZEN_FAMILIES.values()) == set(_F)


def _mutated_families(mutation):
    table = dict(selector_module.SELECTION_FAMILIES)
    if mutation == "defender-to-material":
        table[_P.REMOVES_DEFENDER] = _F.MATERIAL_OUTCOME
    elif mutation == "threat-to-mate-outcome":
        table[_P.THREATENS_MATE_IF_IGNORED] = _F.MATE_OUTCOME
    elif mutation == "preservation-moved":
        table[_P.AVOIDS_REPRESENTATIVE_MATE_FAILURE] = _F.MATERIAL_OUTCOME
    elif mutation == "predicate-missing":
        del table[_P.ALLOWS_FORK]
    else:
        table["fallback"] = _F.TACTICAL_MECHANISM
    return table


@pytest.mark.parametrize(
    "mutation",
    [
        "defender-to-material",
        "threat-to-mate-outcome",
        "preservation-moved",
        "predicate-missing",
        "extra-entry",
    ],
)
def test_family_mutation_is_caught_by_oracle(mutation, monkeypatch):
    monkeypatch.setattr(selector_module, "SELECTION_FAMILIES", _mutated_families(mutation))
    assert family_violations()


# ---- E. selector algorithm mutation gate --------------------------------------------------------

BASE_ID = "pos_base"
PLAYED = MoveClaimEntity(ChessMove("e2e4"), BASE_ID)
KNIGHT = base_frame_piece_entity(BASE_ID, BasePieceRef(Color.WHITE, PieceType.KNIGHT, "g1"))


def synthetic(*specs) -> tuple[ExplanationClaim, ...]:
    """(predicate, confidence[, evidence count]) -> canonical domain-valid claim tuple."""

    claims, next_ev = [], 1
    for i, spec in enumerate(specs, start=1):
        predicate, confidence, count = (*spec, 1)[:3]
        ids = tuple(f"ev_{n:03d}" for n in range(next_ev, next_ev + count))
        next_ev += count
        claims.append(
            ExplanationClaim(
                f"cl_{i:03d}",
                BASE_ID,
                PLAYED,
                predicate,
                (KNIGHT,),
                confidence,
                required_claim_scope(predicate),
                ids,
            )
        )
    return tuple(claims)


ALGORITHM_CASES = [
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
    (
        ((_P.THREATENS_MATERIAL_IF_IGNORED, EV), (_P.FORCES_RESPONSE, _C.EXACT)),
        ("cl_002", "cl_001"),
    ),
    (((_P.FORCES_RESPONSE, _C.EXACT), (_P.ALLOWS_FORK, EV)), ("cl_002", "cl_001")),
    (((_P.ALLOWS_MATERIAL_LOSS, EV), (_P.ALLOWS_CHECKMATE, EV)), ("cl_001", "cl_002")),
    (((_P.ALLOWS_MATERIAL_LOSS, EV, 1), (_P.ALLOWS_CHECKMATE, EV, 4)), ("cl_001", "cl_002")),
    (
        ((_P.LEAVES_PIECE_HANGING, EV), (_P.REMOVES_DEFENDER, EV), (_P.ALLOWS_FORK, EV)),
        ("cl_001",),
    ),
    (
        (
            (_P.THREATENS_MATE_IF_IGNORED, EV),
            (_P.FORCES_RESPONSE, _C.EXACT),
            (_P.REMOVES_DEFENDER, EV),
            (_P.WINS_MATERIAL, EV),
        ),
        ("cl_004", "cl_003", "cl_002"),
    ),
]


def algorithm_violations() -> list:
    """Oracle: frozen synthetic cases plus every real corpus selection, via the selector."""

    found = []
    for specs, expected in ALGORITHM_CASES:
        got = selector_module.select_claim_ids(synthetic(*specs))
        if got != expected:
            found.append((expected, got))
    for name, expected in CORPUS_SELECTIONS.items():
        try:
            got = ExplanationSelector().select(built(name)).selected_claim_ids
        except ExplanationSelectionError as exc:
            got = exc
        if got != expected:
            found.append((name, got))
    return found


def test_algorithm_oracle_accepts_current_production():
    assert algorithm_violations() == []


def _mutant(kind):
    original = select_claim_ids

    def predicate_secondary(claims):
        order = list(_P)
        ranked = sorted(
            enumerate(claims),
            key=lambda t: (
                priority_tier(t[1].predicate, t[1].confidence),
                order.index(t[1].predicate),
                t[0],
            ),
        )
        return original(tuple(c for _, c in ranked))

    def evidence_volume_tiebreak(claims):
        # P11 has no score access; evidence volume is the nearest injectable magnitude.
        ranked = sorted(
            enumerate(claims),
            key=lambda t: (
                priority_tier(t[1].predicate, t[1].confidence),
                -len(t[1].evidence_ids),
                t[0],
            ),
        )
        return original(tuple(c for _, c in ranked))

    def no_family_suppression(claims):
        ranked = sorted(
            enumerate(claims), key=lambda t: (priority_tier(t[1].predicate, t[1].confidence), t[0])
        )
        return tuple(c.claim_id for _, c in ranked)[:3]

    def sorted_ids(claims):
        return tuple(sorted(original(claims)))

    return {
        "predicate-secondary-order": predicate_secondary,
        "evidence-volume-tiebreak": evidence_volume_tiebreak,
        "no-family-suppression": no_family_suppression,
        "sorted-ids": sorted_ids,
    }[kind]


@pytest.mark.parametrize(
    "mutation",
    [
        "predicate-secondary-order",
        "evidence-volume-tiebreak",
        "no-family-suppression",
        "sorted-ids",
        "cap-4",
    ],
)
def test_selector_mutation_is_caught_by_oracle(mutation, monkeypatch):
    if mutation == "cap-4":
        monkeypatch.setattr(selector_module, "MAX_SELECTED_CLAIMS", 4)
    else:
        monkeypatch.setattr(selector_module, "select_claim_ids", _mutant(mutation))
    assert algorithm_violations()


# ---- F. graph/selection pairing -----------------------------------------------------------------


def _only(kind):
    bundle = p8.evidence(p8.only_kind(p8.knight(), kind))
    return GraphBuilder().build(bundle, p8.claims(bundle))


def test_request_local_ids_never_pair_across_graphs():
    a = built("p8-knight")  # cl_001 hanging, cl_002 material
    b = _only(p8.Kind.NEWLY_HANGING_PIECE)  # cl_001 hanging only, same base
    assert a.base_position_id == b.base_position_id
    sel_a, sel_b = p11(a), p11(b)
    for graph, foreign in ((b, sel_a), (a, sel_b)):
        with pytest.raises(ExplanationSelectionError, match="exact frozen"):
            ExplanationSelectionValidator().validate(graph, foreign)


def test_identical_selection_values_are_resolved_only_against_their_own_graph():
    hanging = _only(p8.Kind.NEWLY_HANGING_PIECE)
    material = _only(p8.Kind.MATERIAL_LOSS_LINE)
    sel_h, sel_m = p11(hanging), p11(material)
    # Same base and the same request-local id: the values are identical and each is the exact
    # recomputation for both graphs, so meaning comes only from the validated paired graph.
    assert sel_h == sel_m == ExplanationSelection(hanging.base_position_id, ("cl_001",))
    assert hanging.claims[0].predicate is _P.LEAVES_PIECE_HANGING
    assert material.claims[0].predicate is _P.ALLOWS_MATERIAL_LOSS
    assert ExplanationSelectionValidator().validate(material, sel_h) is sel_h


PAIRING_ATTACKS = {
    "wrong-order": ("p8-knight", ("cl_001", "cl_002"), ()),
    "missing-claim": ("p8-knight", ("cl_002",), ()),
    "extra-unknown-claim": ("p8-knight", ("cl_002", "cl_001", "cl_003"), ()),
    "suppressed-family-claim": ("p8-defender", ("cl_003", "cl_001", "cl_002"), ()),
    "suppressed-family-swap": ("p8-defender", ("cl_003", "cl_002"), ()),
    "relation-id": ("p8-knight", ("cl_002", "cl_001"), ("rel_001",)),
}


@pytest.mark.parametrize("name", sorted(PAIRING_ATTACKS))
def test_pairing_attacks_rejected(name):
    fixture, ids, relations = PAIRING_ATTACKS[name]
    graph = built(fixture)
    selection = ExplanationSelection(graph.base_position_id, ids, relations)
    with pytest.raises(ExplanationSelectionError, match="exact frozen"):
        ExplanationSelectionValidator().validate(graph, selection)


@pytest.mark.parametrize("field", ["fourth-claim", "claim-list", "relation-list"])
def test_tampered_selection_fields_rejected(field):
    graph = built("p8-knight")
    selection = p11(graph)
    if field == "fourth-claim":
        tamper(selection, selected_claim_ids=("cl_002", "cl_001", "cl_003", "cl_004"))
    elif field == "claim-list":
        tamper(selection, selected_claim_ids=list(selection.selected_claim_ids))
    else:
        tamper(selection, selected_relation_ids=[])
    with pytest.raises(ExplanationSelectionError, match="exact frozen"):
        ExplanationSelectionValidator().validate(graph, selection)


# ---- G. determinism -----------------------------------------------------------------------------

_SIGNATURE_SCRIPT = """
import sys
sys.path[:0] = [{src!r}, {tests!r}]
import _p8_claim_scenarios as p8, _p9_strong_claim_scenarios as s, _p9_preservation_claim_scenarios as r
from calliope.services.explanation import GraphBuilder, ExplanationSelector
for mod, makes in ((p8, (p8.knight, p8.defender, p8.fork, p8.exact_mate, p8.engine_mate)),
                   (s, s.SCENARIOS), (r, r.SCENARIOS)):
    for make in makes:
        bundle = mod.evidence(make())
        graph = GraphBuilder().build(bundle, mod.claims(bundle))
        sel = ExplanationSelector().select(graph)
        print(make.__name__, [(c.claim_id, c.predicate.value, c.confidence.value, c.scope.value)
              for c in graph.claims], graph.relations, sel.selected_claim_ids, sel.selected_relation_ids)
"""


def test_p11_output_is_independent_of_hash_seed():
    script = _SIGNATURE_SCRIPT.format(
        src=str(REPO / "src"), tests=str(REPO / "tests/unit/services/explanation")
    )
    outputs = set()
    for seed in ("0", "4242"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        done = subprocess.run(
            [sys.executable, "-c", script], env=env, capture_output=True, text=True, check=True
        )
        outputs.add(done.stdout)
    assert len(outputs) == 1 and outputs.pop().count("\n") == 17


@pytest.mark.parametrize("make", [p8.engine_mate, p8.knight])
def test_p11_output_is_independent_of_rebuilds(make):
    signatures = set()
    for _ in range(3):
        bundle = p8.evidence(make())
        graph = GraphBuilder().build(bundle, p8.claims(bundle))
        signatures.add(signature(graph, p11(graph)))
    assert len(signatures) == 1


def test_p11_output_is_independent_of_engine_mate_distance():
    signatures = set()
    for distance in (2, 5, 9):
        bundle = p8.evidence(p8.engine_mate(EngineScore.forced_mate(Color.BLACK, distance)))
        graph = GraphBuilder().build(bundle, p8.claims(bundle))
        signatures.add(signature(graph, p11(graph)))
    assert len(signatures) == 1


# ---- H. no engine / rules / P7 at P11 runtime ---------------------------------------------------


def test_p11_runs_with_engine_rules_and_p7_disabled(monkeypatch):
    packages = {name: package(name) for name in CORPUS}  # P8/P9/P10 work happens before

    def forbidden(*args, **kwargs):
        raise AssertionError("P11 must not call engines, chess rules or P7")

    for cls in (PythonChessAdapter, StockfishAdapter, CounterfactualAnalyzer):
        for attribute in dir(cls):
            if not attribute.startswith("_") and callable(getattr(cls, attribute)):
                monkeypatch.setattr(cls, attribute, forbidden)
    for name, (bundle, claims) in packages.items():
        graph = GraphBuilder().build(bundle, claims)
        assert p11(graph).selected_claim_ids == CORPUS_SELECTIONS[name]
