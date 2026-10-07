from dataclasses import replace

import pytest
from _p9_preservation_claim_scenarios import (
    Kind,
    claims,
    engine_mate,
    evidence,
    mate_all,
    mate_subset,
    material_all,
    material_subset,
    of_type,
    package,
    tamper,
)

from calliope.domain.analysis import (
    MateEvidenceLevel,
    ProbeKind,
    RepresentativeAlternative,
    TerminalKind,
    TerminalOutcome,
)
from calliope.domain.chess import ChessMove
from calliope.domain.engine import EngineIdentity, EngineLimit, EngineSettings
from calliope.domain.explanation import (
    BoardFactEvidence,
    ClaimConfidence,
    ClaimPredicate,
    ClaimScope,
    CounterfactualEvidence,
    EngineEvidence,
    EvidenceBundle,
    EvidenceForm,
    MotifEvidence,
    MoveClaimEntity,
    VariationEvidence,
)
from calliope.errors import IncompatibleClaimEvidenceError
from calliope.services.explanation.claim_validator import ClaimValidator


def validate(bundle, *values):
    return ClaimValidator().validate_good_move(bundle, tuple(values))


def rejects(bundle, claim, match=None):
    with pytest.raises(IncompatibleClaimEvidenceError, match=match):
        validate(bundle, claim)


def replace_results(group, records, results):
    results = tuple(results)
    tamper(group, required_probe_results=results)
    tamper(of_type(records, CounterfactualEvidence)[0], probe_results=results)


@pytest.mark.parametrize(
    "make", [mate_all, mate_subset, engine_mate, material_all, material_subset]
)
def test_real_preservation_validates(make):
    bundle, claim, _, _ = package(make)
    assert validate(bundle, claim) == (claim,)


@pytest.mark.parametrize(
    "mutation",
    [
        "ignore",
        "batch-b",
        "missing-played",
        "alternative-order",
        "wrong-uci",
        "execution",
        "base",
        "best-response",
        "alternative-move",
    ],
)
def test_batch_a_only_protocol_rechecked(mutation):
    bundle, claim, group, records = package(material_all)
    results = list(group.required_probe_results)
    if mutation == "batch-b":
        results.append(
            replace(
                results[0],
                probe=replace(
                    results[0].probe, kind=ProbeKind.IGNORE_THREAT, execution_move=ChessMove("f7f6")
                ),
            )
        )
    elif mutation == "missing-played":
        results.pop(0)
    elif mutation == "alternative-order":
        results[1], results[2] = results[2], results[1]
    elif mutation == "wrong-uci":
        results[1] = replace(
            results[1], probe=replace(results[1].probe, intervention_move=ChessMove("d1c1"))
        )
    elif mutation == "execution":
        results[1] = replace(
            results[1], probe=replace(results[1].probe, execution_move=ChessMove("b2d2"))
        )
    elif mutation == "base":
        tamper(results[0].probe.base, position_id="pos_foreign")
    else:
        kind = {
            "ignore": ProbeKind.IGNORE_THREAT,
            "best-response": ProbeKind.BEST_RESPONSE,
            "alternative-move": ProbeKind.ALTERNATIVE_MOVE,
        }[mutation]
        results[1] = replace(results[1], probe=replace(results[1].probe, kind=kind))
    replace_results(group, records, results)
    rejects(bundle, claim, "Batch-A|Batch A")


@pytest.mark.parametrize(
    "mutation", ["zero", "three", "rank-duplicate", "uci-duplicate", "reversed"]
)
def test_representative_alternative_shape_rechecked(mutation):
    bundle, claim, group, records = package(material_all)
    alternatives = group.representative_alternatives
    if mutation == "zero":
        alternatives = ()
    elif mutation == "three":
        alternatives = (*alternatives, RepresentativeAlternative(4, ChessMove("d1c1")))
    elif mutation == "rank-duplicate":
        alternatives = (alternatives[0], replace(alternatives[1], rank=alternatives[0].rank))
    elif mutation == "uci-duplicate":
        alternatives = (alternatives[0], replace(alternatives[1], move=alternatives[0].move))
    else:
        alternatives = alternatives[::-1]
    tamper(group, representative_alternatives=alternatives)
    tamper(of_type(records, CounterfactualEvidence)[0], representative_alternatives=alternatives)
    rejects(bundle, claim, "representative alternatives")


@pytest.mark.parametrize(
    "mutation", ["empty", "foreign", "wrong-rank", "wrong-uci", "reversed", "duplicate"]
)
def test_failed_alternative_membership_and_rank_order(mutation):
    bundle, claim, group, records = package(material_all)
    failed = group.failed_alternatives
    if mutation == "empty":
        failed = ()
    elif mutation == "foreign":
        failed = (RepresentativeAlternative(4, ChessMove("d1c1")),)
    elif mutation == "wrong-rank":
        failed = (replace(failed[0], rank=3),)
    elif mutation == "wrong-uci":
        failed = (replace(failed[0], move=failed[1].move),)
    elif mutation == "reversed":
        failed = failed[::-1]
    else:
        failed = (failed[0], failed[0])
    tamper(group, failed_alternatives=failed)
    tamper(of_type(records, CounterfactualEvidence)[0], failed_alternatives=failed)
    rejects(bundle, claim, "failed alternatives")


@pytest.mark.parametrize("make", [mate_all, mate_subset, material_all, material_subset])
@pytest.mark.parametrize("value", [None, "opposite"])
def test_equivalence_boolean_must_match_subset(make, value):
    bundle, claim, _, records = package(make)
    (cf,) = of_type(records, CounterfactualEvidence)
    tamper(
        cf,
        equivalent_alternative_benefit=None
        if value is None
        else not cf.equivalent_alternative_benefit,
    )
    rejects(bundle, claim, "equivalence")


@pytest.mark.parametrize("make", [mate_all, material_all])
@pytest.mark.parametrize(
    "mutation", ["cross-kind", "local", "tested", "exact", "forced", "strong-predicate"]
)
def test_preservation_mapping_cannot_be_strengthened(make, mutation):
    bundle, claim, _, _ = package(make)
    if mutation == "cross-kind":
        tamper(
            claim,
            predicate=ClaimPredicate.AVOIDS_REPRESENTATIVE_MATERIAL_LOSS
            if make is mate_all
            else ClaimPredicate.AVOIDS_REPRESENTATIVE_MATE_FAILURE,
        )
    elif mutation in ("local", "tested"):
        tamper(claim, scope=ClaimScope.LOCAL if mutation == "local" else ClaimScope.TESTED_RESPONSE)
    elif mutation in ("exact", "forced"):
        tamper(
            claim,
            confidence=ClaimConfidence.EXACT if mutation == "exact" else ClaimConfidence.FORCED,
        )
    else:
        tamper(claim, predicate=ClaimPredicate.WINS_MATERIAL)
    rejects(bundle, claim, "mapping|FORCED")


@pytest.mark.parametrize("make", [mate_all, material_all])
@pytest.mark.parametrize("form", [EvidenceForm.DIRECT, EvidenceForm.TESTED_RESPONSE])
def test_preservation_kind_cannot_use_strong_form(make, form):
    bundle, claim, group, records = package(make)
    tamper(group, evidence_form=form)
    tamper(of_type(records, CounterfactualEvidence)[0], form=form)
    rejects(bundle, claim, "PRESERVATION form")


@pytest.mark.parametrize(
    "mutation",
    [
        "omit-failed",
        "add-safe",
        "foreign",
        "wrong-position",
        "duplicate",
        "missing-piece",
        "piece-frame",
        "subject",
    ],
)
def test_exact_object_membership_and_frame_closure(mutation):
    bundle, claim, group, records = package(material_subset)
    move = next(o for o in claim.objects if isinstance(o, MoveClaimEntity))
    if mutation == "omit-failed":
        tamper(claim, objects=tuple(o for o in claim.objects if o is not move))
    elif mutation == "add-safe":
        safe = next(
            a for a in group.representative_alternatives if a not in group.failed_alternatives
        )
        tamper(claim, objects=(*claim.objects, MoveClaimEntity(safe.move, bundle.base_position_id)))
    elif mutation == "foreign":
        tamper(
            claim,
            objects=tuple(
                MoveClaimEntity(ChessMove("d1c1"), bundle.base_position_id) if o is move else o
                for o in claim.objects
            ),
        )
    elif mutation == "wrong-position":
        tamper(move, position_id=group.required_probe_results[1].analysis_position.position_id)
    elif mutation == "duplicate":
        tamper(claim, objects=(*claim.objects, move))
    elif mutation == "missing-piece":
        for record in records:
            if hasattr(record, "pieces"):
                tamper(record, pieces=())
    elif mutation == "piece-frame":
        tamper(of_type(records, BoardFactEvidence)[0].pieces[0], at_position_id="pos_foreign")
    else:
        tamper(claim, subject=MoveClaimEntity(ChessMove("d1c1"), bundle.base_position_id))
    rejects(bundle, claim)


@pytest.mark.parametrize(
    "mutation",
    ["subset", "reversed", "representatives", "failed", "response", "comparator", "form"],
)
def test_complete_counterfactual_descriptor_required(mutation):
    bundle, claim, group, records = package(material_all)
    (cf,) = of_type(records, CounterfactualEvidence)
    if mutation == "subset":
        tamper(cf, probe_results=cf.probe_results[:2])
    elif mutation == "reversed":
        tamper(cf, probe_results=cf.probe_results[::-1])
    elif mutation == "representatives":
        tamper(cf, representative_alternatives=cf.representative_alternatives[:1])
    elif mutation == "failed":
        tamper(cf, failed_alternatives=cf.failed_alternatives[:1])
    elif mutation == "response":
        tamper(cf, tested_response=group.played_move)
    elif mutation == "comparator":
        tamper(cf, comparator_move=group.played_move)
    else:
        tamper(cf, form=EvidenceForm.DIRECT)
    rejects(bundle, claim, "CounterfactualEvidence")


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-engine",
        "duplicate-engine",
        "foreign-engine",
        "foreign-variation",
        "duplicate-variation",
        "foreign-material",
        "other-probe-material",
        "identity",
        "settings",
    ],
)
def test_owned_provenance_and_engine_closure(mutation):
    bundle, claim, group, records = package(material_all)
    engines = of_type(records, EngineEvidence)
    variations = of_type(records, VariationEvidence)
    if mutation == "missing-engine":
        records.remove(engines[0])
    elif mutation == "duplicate-engine":
        records.insert(records.index(engines[0]), replace(engines[0], evidence_id="ev_999"))
    elif mutation == "foreign-engine":
        tamper(
            engines[0],
            probe_result=replace(
                engines[0].probe_result,
                probe=replace(engines[0].probe_result.probe, intervention_move=ChessMove("d1c1")),
            ),
        )
    elif mutation == "foreign-variation":
        tamper(
            variations[0], probe=replace(variations[0].probe, intervention_move=ChessMove("d1c1"))
        )
    elif mutation == "duplicate-variation":
        records.insert(records.index(variations[0]), replace(variations[0], evidence_id="ev_999"))
    elif mutation in ("foreign-material", "other-probe-material"):
        probe = (
            group.required_probe_results[1].probe
            if mutation == "other-probe-material"
            else replace(variations[0].probe, intervention_move=ChessMove("d1c1"))
        )
        tamper(variations[0].material_evidence[0], probe=probe)
    elif mutation == "identity":
        tamper(group.required_probe_results[1].engine_analysis, engine=EngineIdentity("Other", "2"))
    else:
        tamper(
            group.required_probe_results[1].engine_analysis,
            settings=EngineSettings(EngineLimit(depth=99)),
        )
    tamper(bundle, evidence=tuple(records))
    tamper(group, evidence_ids=tuple(r.evidence_id for r in records))
    claim = replace(claim, evidence_ids=group.evidence_ids)
    rejects(bundle, claim)


@pytest.mark.parametrize("index", [0, 1, 2])
@pytest.mark.parametrize("mutation", ["missing", "empty", "duplicate-measurement"])
def test_exactly_one_material_variation_and_measurement_per_probe(index, mutation):
    bundle, claim, group, records = package(material_all)
    variation = of_type(records, VariationEvidence)[index]
    if mutation == "missing":
        records.remove(variation)
        tamper(bundle, evidence=tuple(records))
        tamper(group, evidence_ids=tuple(r.evidence_id for r in records))
        claim = replace(claim, evidence_ids=group.evidence_ids)
    elif mutation == "empty":
        tamper(variation, material_evidence=())
    else:
        tamper(
            variation,
            material_evidence=(*variation.material_evidence, variation.material_evidence[0]),
        )
    rejects(bundle, claim, "material")


@pytest.mark.parametrize("make", [mate_all, material_all])
def test_aggregate_deltas_cannot_be_copied_to_individual_variations(make):
    bundle, claim, group, records = package(make)
    board = of_type(records, BoardFactEvidence)[0]
    if make is mate_all:
        variation = VariationEvidence(
            "ev_999",
            bundle.base_position_id,
            group.required_probe_results[1].probe,
            moves=(board.moves[1],),
            board_deltas=board.board_deltas,
            replayed_pv_ends_in_checkmate=True,
        )
        records.insert(len(records) - 1, variation)
        tamper(bundle, evidence=tuple(records))
        tamper(group, evidence_ids=tuple(r.evidence_id for r in records))
        claim = replace(claim, evidence_ids=group.evidence_ids)
    else:
        tamper(of_type(records, VariationEvidence)[1], board_deltas=board.board_deltas)
    rejects(bundle, claim, "aggregate")


def test_aggregate_motif_cannot_be_attached_to_failed_alternative():
    bundle, claim, _, records = package(mate_all)
    board = of_type(records, BoardFactEvidence)[0]
    tamper(of_type(records, MotifEvidence)[0], moves=(board.moves[1],))
    rejects(bundle, claim, "aggregate typed motifs")


@pytest.mark.parametrize(
    "mutation", ["level", "flag-none", "flag-zero", "exact-false", "exact-no-deltas"]
)
def test_mate_aggregate_metadata_contract(mutation):
    bundle, claim, group, records = package(mate_all)
    if mutation == "level":
        tamper(group, mate_evidence_level=None)
    elif mutation == "flag-none":
        tamper(group, replayed_pv_ends_in_checkmate=None)
    elif mutation == "flag-zero":
        tamper(group, replayed_pv_ends_in_checkmate=0)
    elif mutation == "exact-false":
        tamper(group, replayed_pv_ends_in_checkmate=False)
    else:
        tamper(of_type(records, BoardFactEvidence)[0], board_deltas=())
    rejects(bundle, claim)


@pytest.mark.parametrize("mutation", ["mate-level", "mate-flag", "no-deltas"])
def test_material_aggregate_metadata_contract(mutation):
    bundle, claim, group, records = package(material_all)
    if mutation == "mate-level":
        tamper(group, mate_evidence_level=MateEvidenceLevel.ENGINE_LINE)
    elif mutation == "mate-flag":
        tamper(group, replayed_pv_ends_in_checkmate=False)
    else:
        tamper(of_type(records, BoardFactEvidence)[0], board_deltas=())
    rejects(bundle, claim, "material preservation")


def test_preservation_references_safe_probes_too():
    bundle, claim, _, _ = package(material_subset)
    rejects(bundle, replace(claim, evidence_ids=claim.evidence_ids[:-1]), "complete group")


def test_package_bijection_canonical_order_and_ids():
    bundle = evidence(mate_all())
    first, second = claims(bundle)
    assert validate(bundle, first, second) == (first, second)
    for values in (
        (),
        (first,),
        (first, replace(first, claim_id="cl_002")),
        (second, first),
        (replace(second, claim_id="cl_001"), replace(first, claim_id="cl_002")),
        (replace(first, claim_id="cl_002"), replace(second, claim_id="cl_001")),
        (first, replace(second, claim_id="cl_003")),
        (first, first),
    ):
        with pytest.raises(IncompatibleClaimEvidenceError):
            validate(bundle, *values)
    assert validate(EvidenceBundle("pos_base", (), ())) == ()


@pytest.mark.parametrize(
    "mutation", ["unknown-claim-id", "unowned", "foreign-base", "shared", "cross-group"]
)
def test_all_evidence_has_one_owner_and_common_base(mutation):
    bundle = evidence(mate_all())
    first, second = claims(bundle)
    if mutation == "unknown-claim-id":
        first = replace(first, evidence_ids=(*first.evidence_ids, "ev_999"))
    elif mutation == "unowned":
        extra = replace(bundle.evidence[0], evidence_id="ev_999")
        tamper(bundle, evidence=(*bundle.evidence, extra))
    elif mutation == "foreign-base":
        tamper(bundle.evidence[0], base_position_id="pos_foreign")
    elif mutation == "shared":
        tamper(
            bundle.groups[1],
            evidence_ids=(*bundle.groups[1].evidence_ids, bundle.groups[0].evidence_ids[0]),
        )
    else:
        first = replace(first, evidence_ids=(*first.evidence_ids, second.evidence_ids[0]))
    with pytest.raises(IncompatibleClaimEvidenceError):
        validate(bundle, first, second)


def test_adversarial_mixed_strong_and_preservation_package_rejected():
    bundle = evidence(mate_all())
    first, second = claims(bundle)
    tamper(bundle.groups[0], source_kind=Kind.MATE_THREAT, evidence_form=EvidenceForm.DIRECT)
    with pytest.raises(IncompatibleClaimEvidenceError, match="cannot mix"):
        validate(bundle, first, second)


def test_all_terminal_batch_a_uses_no_synthetic_engine():
    result = material_all()
    child = result.benefits[0]
    probes = tuple(
        replace(
            r,
            engine_analysis=None,
            root_moves=None,
            terminal=TerminalOutcome(TerminalKind.STALEMATE, None),
        )
        for r in child.probe_results
    )
    bundle = evidence(replace(result, benefits=(replace(child, probe_results=probes),)))
    assert of_type(bundle.evidence, EngineEvidence) == []
    built = claims(bundle)
    assert validate(bundle, *built) == built


@pytest.mark.parametrize("mutation", ["response", "comparator"])
def test_preservation_group_has_no_response_or_comparator(mutation):
    bundle, claim, group, _ = package(material_all)
    tamper(group, **{mutation if mutation == "response" else "comparator_move": group.played_move})
    rejects(bundle, claim, "without comparator or response")


def test_strong_group_cannot_use_preservation_form():
    from _p9_strong_claim_scenarios import direct_material
    from _p9_strong_claim_scenarios import package as strong_package

    bundle, claim, group, records = strong_package(direct_material)
    tamper(group, evidence_form=EvidenceForm.PRESERVATION)
    tamper(of_type(records, CounterfactualEvidence)[0], form=EvidenceForm.PRESERVATION)
    rejects(bundle, claim, "DIRECT or TESTED_RESPONSE")


@pytest.mark.parametrize("make", [mate_all, material_all])
def test_builder_will_not_reconstruct_missing_failed_or_source_entities(make):
    from calliope.errors import IncompatibleClaimEvidenceError

    bundle, _, group, records = package(make)
    missing_uci = group.failed_alternatives[0].move.uci
    for record in records:
        if hasattr(record, "moves"):
            tamper(record, moves=tuple(m for m in record.moves if m.move.uci != missing_uci))
    with pytest.raises(IncompatibleClaimEvidenceError, match="failed alternative move is absent"):
        claims(bundle)
    bundle, _, _, records = package(make)
    for record in records:
        if hasattr(record, "pieces"):
            tamper(record, pieces=())
    with pytest.raises(IncompatibleClaimEvidenceError, match="0 retained presentations"):
        claims(bundle)
