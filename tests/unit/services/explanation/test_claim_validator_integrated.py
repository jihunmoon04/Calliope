"""P10-I5 integrated ClaimValidator gate over real P8, P9 STRONG and P9 preservation packages.

Family-specific adversarial suites live beside this module.  This module only adds what spans
the trust boundary as a whole: one sweep over every real package, package closure / vocabulary
injection applied uniformly to all three families, family/kind relabel attempts, and the
P8-side rules that P9 already enforced (design §17, §23.2, §24, §29).
"""

from dataclasses import replace
from enum import StrEnum

import _p8_claim_scenarios as p8
import _p9_preservation_claim_scenarios as pres
import _p9_strong_claim_scenarios as strong
import pytest

from calliope.domain.analysis import (
    BadMoveCauseKind,
    GoodMoveBenefitKind,
    MateEvidenceLevel,
)
from calliope.domain.explanation import (
    BoardFactEvidence,
    ClaimConfidence,
    ClaimPredicate,
    ClaimScope,
    CounterfactualEvidence,
    EngineEvidence,
    EvidenceBundle,
    EvidenceForm,
    EvidenceSourceFamily,
    MotifEvidence,
    MoveClaimEntity,
    VariationEvidence,
    mint_claim_id,
    mint_evidence_id,
    required_claim_scope,
)
from calliope.errors import IncompatibleClaimEvidenceError
from calliope.services.explanation.claim_validator import ClaimValidator

tamper = p8.tamper
_P = ClaimPredicate
_C = ClaimConfidence

# name -> (zero-argument P8/P9 result factory, scenario module); every bundle is a full real one.
REAL = {
    "p8-knight": (p8.knight, p8),
    "p8-defender": (p8.defender, p8),
    "p8-fork": (p8.fork, p8),
    "p8-exact-mate": (p8.exact_mate, p8),
    "p8-engine-mate": (p8.engine_mate, p8),
    **{f"strong-{make.__name__}": (make, strong) for make in strong.SCENARIOS},
    **{f"pres-{make.__name__}": (make, pres) for make in pres.SCENARIOS},
}
# One representative ENGINE_VERIFIED package per family for the uniform mutation matrix.
FAMILY = ("p8-knight", "strong-ignored_material", "pres-material_all")


def build(name):
    make, module = REAL[name]
    bundle = module.evidence(make())
    return bundle, module.claims(bundle)


def validate(bundle, claims):
    family = bundle.groups[0].source_family if bundle.groups else None
    if family is EvidenceSourceFamily.BAD_MOVE_CAUSE:
        return ClaimValidator().validate_bad_move(bundle, tuple(claims))
    return ClaimValidator().validate_good_move(bundle, tuple(claims))


def rejects(bundle, claims, match=None):
    with pytest.raises(IncompatibleClaimEvidenceError, match=match):
        validate(bundle, claims)


def owned(bundle, group):
    by_id = {r.evidence_id: r for r in bundle.evidence}
    return [by_id[eid] for eid in group.evidence_ids]


def claim_of(claims, group):
    (claim,) = [c for c in claims if set(c.evidence_ids) <= set(group.evidence_ids)]
    return claim


def of_type(records, record_type):
    return [r for r in records if type(r) is record_type]


# ---- every real package -------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(REAL))
def test_every_real_package_validates_unchanged_with_integrated_invariants(name):
    bundle, claims = build(name)
    assert claims, name
    assert validate(bundle, claims) is claims
    again_bundle, again_claims = build(name)
    assert repr(again_bundle) == repr(bundle)
    assert repr(again_claims) == repr(claims)
    assert [c.claim_id for c in claims] == [mint_claim_id(i) for i in range(1, len(claims) + 1)]
    for group in bundle.groups:
        claim = claim_of(claims, group)
        assert claim.confidence is not _C.FORCED
        assert claim.importance is None
        assert claim.scope is required_claim_scope(claim.predicate)
        assert claim.subject == group.played_move
        if claim.confidence is _C.ENGINE_VERIFIED:
            # §17.4: complete, ordered upstream probe provenance on every engine-verified claim.
            assert claim.evidence_ids == group.evidence_ids
            (cf,) = of_type(owned(bundle, group), CounterfactualEvidence)
            assert cf.probe_results == group.required_probe_results


# ---- package closure and vocabulary injection, uniform over all families ------------------------


class _Heuristic(StrEnum):
    IMPROVES_POSITION = "improves_position"
    HEURISTIC = "heuristic"


def _swap_engine_records(bundle, claims):
    group = bundle.groups[0]
    ids = list(group.evidence_ids)
    engines = [i for i, r in enumerate(owned(bundle, group)) if type(r) is EngineEvidence]
    assert len(engines) >= 2
    ids[engines[0]], ids[engines[1]] = ids[engines[1]], ids[engines[0]]
    claim = claim_of(claims, group)
    tamper(group, evidence_ids=tuple(ids))
    tamper(claim, evidence_ids=tuple(ids))


def _counterfactual_first(bundle, claims):
    group = bundle.groups[0]
    claim = claim_of(claims, group)
    ids = (group.evidence_ids[-1], *group.evidence_ids[:-1])
    tamper(group, evidence_ids=ids)
    tamper(claim, evidence_ids=ids)


def _unowned_motif(bundle, claims):
    """A real P6 motif taken from an unrelated P8 package and re-based onto this one."""

    donor, _ = build("p8-fork")
    motif = next(r for r in donor.evidence if type(r) is MotifEvidence)
    extra = replace(motif, evidence_id="ev_999", base_position_id=bundle.base_position_id)
    tamper(bundle, evidence=(*bundle.evidence, extra))


CLOSURE = {
    # §29.14: an arbitrary P6 motif without an owning supported group cannot ride along.
    "unowned-motif": (_unowned_motif, "group-owned"),
    "duplicate-record": (
        lambda b, c: tamper(b, evidence=(*b.evidence, b.evidence[0])),
        "unique",
    ),
    "foreign-base-record": (
        lambda b, c: tamper(b.evidence[0], base_position_id="pos_foreign"),
        "another base",
    ),
    "missing-claim": (lambda b, c: c.pop(), "one claim per evidence group"),
    "importance": (lambda b, c: tamper(c[0], importance=0.0), "importance"),
    # §29.23: no heuristic / positional / literal-only vocabulary, even as an equal string.
    "plain-string-predicate": (
        lambda b, c: tamper(c[0], predicate=str(c[0].predicate)),
        "closed-vocabulary",
    ),
    "heuristic-predicate": (
        lambda b, c: tamper(c[0], predicate=_Heuristic.IMPROVES_POSITION),
        "closed-vocabulary",
    ),
    "heuristic-confidence": (
        lambda b, c: tamper(c[0], confidence=_Heuristic.HEURISTIC),
        "closed-vocabulary",
    ),
    "literal-only-predicate": (
        lambda b, c: tamper(c[0], predicate="only_move"),
        "closed-vocabulary",
    ),
    # §23.2: EngineEvidence / VariationEvidence follow retained probe order inside a group.
    "engine-probe-order": (_swap_engine_records, "order"),
    "counterfactual-first": (_counterfactual_first, "order|final CounterfactualEvidence"),
}


@pytest.mark.parametrize("mutation", sorted(CLOSURE))
@pytest.mark.parametrize("name", FAMILY)
def test_package_closure_and_vocabulary_are_family_independent(name, mutation):
    bundle, built = build(name)
    claims = list(built)
    assert validate(bundle, built) is built
    change, match = CLOSURE[mutation]
    change(bundle, claims)
    rejects(bundle, claims, match)


@pytest.mark.parametrize("name", sorted(REAL))
def test_forced_never_accepted_for_any_real_claim(name):
    bundle, claims = build(name)
    for index, claim in enumerate(claims):
        changed = list(claims)
        changed[index] = replace(claim, confidence=_C.FORCED)
        rejects(bundle, changed, "FORCED")


def test_mixed_p8_and_p9_package_rejected_by_both_entrypoints():
    p8_bundle, p8_claims = build("p8-knight")
    p9_bundle, p9_claims = build("strong-ignored_material")
    offset = len(p8_bundle.evidence)
    rename = {
        r.evidence_id: mint_evidence_id(offset + i) for i, r in enumerate(p9_bundle.evidence, 1)
    }
    records = tuple(replace(r, evidence_id=rename[r.evidence_id]) for r in p9_bundle.evidence)
    groups = tuple(
        replace(g, evidence_ids=tuple(rename[e] for e in g.evidence_ids)) for g in p9_bundle.groups
    )
    claims = (
        *p8_claims,
        *(
            replace(
                c,
                claim_id=mint_claim_id(len(p8_claims) + i),
                evidence_ids=tuple(rename[e] for e in c.evidence_ids),
            )
            for i, c in enumerate(p9_claims, 1)
        ),
    )
    mixed = EvidenceBundle(p8_bundle.base_position_id, p8_bundle.evidence, p8_bundle.groups)
    tamper(mixed, evidence=(*p8_bundle.evidence, *records), groups=(*p8_bundle.groups, *groups))
    validator = ClaimValidator()
    with pytest.raises(IncompatibleClaimEvidenceError, match="BAD_MOVE_CAUSE"):
        validator.validate_bad_move(mixed, claims)
    with pytest.raises(IncompatibleClaimEvidenceError, match="GOOD_MOVE_BENEFIT"):
        validator.validate_good_move(mixed, claims)


# ---- family / kind relabel attempts -------------------------------------------------------------


def _relabel(group, records, claim, *, flag=False, **group_changes):
    """Rewrite only enum/form metadata (plus the matching mate flag) as consistently as possible."""

    tamper(group, **group_changes)
    if "mate_evidence_level" in group_changes and flag is not None:
        tamper(group, replayed_pv_ends_in_checkmate=flag)
        for variation in of_type(records, VariationEvidence):
            if variation.replayed_pv_ends_in_checkmate is not None or variation.board_deltas:
                tamper(variation, replayed_pv_ends_in_checkmate=flag)
    return claim


def _p8_package(make, kind):
    bundle = p8.evidence(p8.only_kind(make(), kind))
    (claim,) = p8.claims(bundle)
    return bundle, claim, bundle.groups[0], p8.records_of(bundle, bundle.groups[0])


def r_strong_material_as_mate(flag):
    bundle, claim, group, records = strong.package(strong.direct_material)
    _relabel(
        group,
        records,
        claim,
        flag=flag,
        source_kind=GoodMoveBenefitKind.MATE_THREAT,
        mate_evidence_level=MateEvidenceLevel.ENGINE_LINE,
    )
    return bundle, replace(claim, predicate=_P.LEADS_TO_MATE)


def r_p8_hanging_as_mate():
    bundle, claim, group, records = _p8_package(p8.knight, BadMoveCauseKind.NEWLY_HANGING_PIECE)
    _relabel(
        group,
        records,
        claim,
        source_kind=BadMoveCauseKind.MATE_ALLOWED,
        mate_evidence_level=MateEvidenceLevel.ENGINE_LINE,
    )
    return bundle, replace(claim, predicate=_P.ALLOWS_CHECKMATE)


def r_pres_material_as_mate():
    bundle, claim, group, records = pres.package(pres.material_all)
    _relabel(
        group,
        records,
        claim,
        source_kind=GoodMoveBenefitKind.PREVENTS_MATE,
        mate_evidence_level=MateEvidenceLevel.ENGINE_LINE,
    )
    return bundle, replace(claim, predicate=_P.AVOIDS_REPRESENTATIVE_MATE_FAILURE)


def r_p8_mate_as_material():
    bundle, claim, group, _ = _p8_package(p8.engine_mate, BadMoveCauseKind.MATE_ALLOWED)
    tamper(
        group,
        source_kind=BadMoveCauseKind.MATERIAL_LOSS_LINE,
        mate_evidence_level=None,
        replayed_pv_ends_in_checkmate=None,
    )
    return bundle, replace(claim, predicate=_P.ALLOWS_MATERIAL_LOSS)


def r_strong_forces_as_mate():
    bundle, claim, group, records = strong.package(strong.forces)
    _relabel(
        group,
        records,
        claim,
        source_kind=GoodMoveBenefitKind.MATE_THREAT,
        mate_evidence_level=MateEvidenceLevel.ENGINE_LINE,
    )
    return bundle, replace(claim, predicate=_P.LEADS_TO_MATE, confidence=_C.ENGINE_VERIFIED)


def r_p8_as_strong():
    bundle, claim, group, _ = _p8_package(p8.knight, BadMoveCauseKind.MATERIAL_LOSS_LINE)
    tamper(
        group,
        source_family=EvidenceSourceFamily.GOOD_MOVE_BENEFIT,
        source_kind=GoodMoveBenefitKind.MATERIAL_THREAT,
    )
    return bundle, replace(claim, predicate=_P.WINS_MATERIAL)


def r_strong_as_p8():
    bundle, claim, group, _ = strong.package(strong.direct_material)
    tamper(
        group,
        source_family=EvidenceSourceFamily.BAD_MOVE_CAUSE,
        source_kind=BadMoveCauseKind.MATERIAL_LOSS_LINE,
    )
    return bundle, replace(claim, predicate=_P.ALLOWS_MATERIAL_LOSS)


def r_pres_as_strong():
    bundle, claim, group, records = pres.package(pres.material_all)
    tamper(
        group,
        source_kind=GoodMoveBenefitKind.MATERIAL_THREAT,
        evidence_form=EvidenceForm.DIRECT,
        failed_alternatives=(),
    )
    tamper(
        of_type(records, CounterfactualEvidence)[0],
        form=EvidenceForm.DIRECT,
        failed_alternatives=(),
        equivalent_alternative_benefit=False,
    )
    objects = tuple(o for o in claim.objects if not isinstance(o, MoveClaimEntity))
    return bundle, replace(
        claim, predicate=_P.WINS_MATERIAL, scope=ClaimScope.LOCAL, objects=objects
    )


RELABELS = {
    "strong-material-as-mate": (lambda: r_strong_material_as_mate(False), "opponent king"),
    "strong-material-as-mate-without-flag": (
        lambda: r_strong_material_as_mate(None),
        "boolean replayed-mate flag",
    ),
    "p8-hanging-as-mate": (r_p8_hanging_as_mate, "mover king"),
    "pres-material-as-mate": (r_pres_material_as_mate, "mover king"),
    "p8-mate-as-material": (r_p8_mate_as_material, "material replay"),
    "strong-forces-as-mate": (r_strong_forces_as_mate, None),
    "p8-group-as-strong": (r_p8_as_strong, None),
    "strong-group-as-p8": (r_strong_as_p8, None),
    "pres-group-as-strong": (r_pres_as_strong, None),
}


@pytest.mark.parametrize("name", sorted(RELABELS))
def test_metadata_relabel_cannot_move_evidence_between_kinds_or_families(name):
    make, match = RELABELS[name]
    bundle, claim = make()
    rejects(bundle, (claim,), match)


# ---- P8 rules that P9 already enforced ----------------------------------------------------------


@pytest.mark.parametrize("value", [True, None])
def test_p8_unsupported_equivalent_resource_cannot_be_fed_as_supported(value):
    """§29.13: a REFUTED/INCONCLUSIVE P8 comparator outcome is retained and rechecked."""

    bundle, claim, _, records = _p8_package(p8.knight, BadMoveCauseKind.NEWLY_HANGING_PIECE)
    assert of_type(records, CounterfactualEvidence)[0].equivalent_alternative_benefit is False
    tamper(of_type(records, CounterfactualEvidence)[0], equivalent_alternative_benefit=value)
    rejects(bundle, (claim,), "equivalent resource")


@pytest.mark.parametrize("target", ["base", "comparator-branch"])
def test_p8_punishment_source_position_rebinding_rejected(target):
    """§29.15: the punishment is legal only from the actual refutation's analysis position."""

    bundle, claim, group, records = _p8_package(p8.defender, BadMoveCauseKind.REMOVED_DEFENDER)
    old = group.response
    assert old.position_id == group.required_probe_results[0].analysis_position.position_id
    position = (
        bundle.base_position_id
        if target == "base"
        else group.required_probe_results[1].analysis_position.position_id
    )
    new = MoveClaimEntity(old.move, position)
    tamper(group, response=new)
    for record in records:
        if isinstance(record, (BoardFactEvidence, MotifEvidence, VariationEvidence)):
            tamper(record, moves=tuple(new if m == old else m for m in record.moves))
    claim = replace(claim, objects=tuple(new if o == old else o for o in claim.objects))
    rejects(bundle, (claim,), "actual refutation position")


@pytest.mark.parametrize("family", ["p8", "strong"])
def test_mate_group_requires_boolean_replay_flag(family):
    if family == "p8":
        bundle, claim, group, records = _p8_package(p8.engine_mate, BadMoveCauseKind.MATE_ALLOWED)
    else:
        bundle, claim, group, records = strong.package(strong.direct_mate)
    assert isinstance(group.replayed_pv_ends_in_checkmate, bool)
    tamper(group, replayed_pv_ends_in_checkmate=None)
    for variation in of_type(records, VariationEvidence):
        tamper(variation, replayed_pv_ends_in_checkmate=None)
    rejects(bundle, (claim,), "boolean replayed-mate flag")
