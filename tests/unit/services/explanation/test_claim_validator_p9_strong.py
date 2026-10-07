from dataclasses import replace

import pytest
from _p9_strong_claim_scenarios import (
    SCENARIOS,
    Kind,
    claims,
    direct_mate,
    direct_material,
    evidence,
    exact_mate,
    forces,
    ignored_mate,
    ignored_material,
    of_type,
    package,
    tamper,
)

from calliope.domain.analysis import (
    MateEvidenceLevel,
    ProbeKind,
    TacticalCandidateKind,
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
from calliope.errors import ExplanationClaimError, IncompatibleClaimEvidenceError
from calliope.services.explanation.claim_validator import ClaimValidator


def validate(bundle, *values):
    return ClaimValidator().validate_good_move(bundle, tuple(values))


def rejects(bundle, claim, match=None):
    with pytest.raises(IncompatibleClaimEvidenceError, match=match):
        validate(bundle, claim)


def replace_results(group, records, results):
    """Keep descriptor and counterfactual consistent so protocol must reject independently."""
    tamper(group, required_probe_results=tuple(results))
    (cf,) = of_type(records, CounterfactualEvidence)
    tamper(cf, probe_results=tuple(results))


@pytest.mark.parametrize("make", SCENARIOS)
def test_real_success_unchanged(make):
    bundle, claim, _, _ = package(make)
    assert validate(bundle, claim) == (claim,)


@pytest.mark.parametrize(
    "make", [forces, exact_mate, direct_mate, ignored_mate, direct_material, ignored_material]
)
def test_forced_rejected_unconditionally(make):
    bundle, claim, _, _ = package(make)
    rejects(bundle, replace(claim, confidence=ClaimConfidence.FORCED), "FORCED")


@pytest.mark.parametrize(
    "make,wrong,scope",
    [
        (forces, ClaimPredicate.LEADS_TO_MATE, ClaimScope.LOCAL),
        (direct_mate, ClaimPredicate.THREATENS_MATE_IF_IGNORED, ClaimScope.TESTED_RESPONSE),
        (ignored_mate, ClaimPredicate.LEADS_TO_MATE, ClaimScope.LOCAL),
        (direct_material, ClaimPredicate.THREATENS_MATERIAL_IF_IGNORED, ClaimScope.TESTED_RESPONSE),
        (ignored_material, ClaimPredicate.WINS_MATERIAL, ClaimScope.LOCAL),
        (
            direct_material,
            ClaimPredicate.AVOIDS_REPRESENTATIVE_MATERIAL_LOSS,
            ClaimScope.REPRESENTATIVE_ALTERNATIVES,
        ),
    ],
)
def test_cross_form_and_preservation_mapping_rejected(make, wrong, scope):
    bundle, claim, _, _ = package(make)
    rejects(bundle, replace(claim, predicate=wrong, scope=scope), "mapping")


@pytest.mark.parametrize(
    "make", [forces, exact_mate, direct_mate, direct_material, ignored_mate, ignored_material]
)
def test_reversed_evidence_form_rejected(make):
    bundle, claim, group, records = package(make)
    form = (
        EvidenceForm.DIRECT
        if group.evidence_form is EvidenceForm.TESTED_RESPONSE
        else EvidenceForm.TESTED_RESPONSE
    )
    tamper(group, evidence_form=form)
    tamper(of_type(records, CounterfactualEvidence)[0], form=form)
    rejects(bundle, claim)


@pytest.mark.parametrize(
    "mutation",
    [
        "no-ignore",
        "not-final",
        "wrong-q",
        "wrong-played",
        "second-ignore",
        "too-many",
        "missing-played",
        "alternative-order",
        "alternative-uci",
        "execution",
        "base",
        "final-position",
    ],
)
def test_independent_batch_a_b_protocol_revalidation(mutation):
    bundle, claim, group, records = package(ignored_material)
    results = list(group.required_probe_results)
    if mutation == "no-ignore":
        results.pop()
    elif mutation == "not-final":
        results[1], results[-1] = results[-1], results[1]
    elif mutation == "wrong-q":
        results[-1] = replace(
            results[-1], probe=replace(results[-1].probe, execution_move=ChessMove("a7a5"))
        )
    elif mutation == "wrong-played":
        results[-1] = replace(
            results[-1], probe=replace(results[-1].probe, intervention_move=ChessMove("a1a4"))
        )
    elif mutation == "second-ignore":
        results[1] = results[-1]
    elif mutation == "too-many":
        results.append(results[-1])
    elif mutation == "missing-played":
        results.pop(0)
    elif mutation == "alternative-order":
        results[1], results[2] = results[2], results[1]
    elif mutation == "alternative-uci":
        results[1] = replace(
            results[1], probe=replace(results[1].probe, intervention_move=ChessMove("e1f1"))
        )
    elif mutation == "execution":
        results[0] = replace(
            results[0], probe=replace(results[0].probe, execution_move=ChessMove("h5f6"))
        )
    elif mutation == "base":
        tamper(results[0].probe.base, position_id="pos_foreign")
    else:
        tamper(results[-1].analysis_position, position_id="pos_foreign")
    replace_results(group, records, results)
    rejects(bundle, claim)


@pytest.mark.parametrize("make", [direct_mate, direct_material, forces])
def test_direct_form_with_any_ignore_probe_rejected(make):
    bundle, claim, group, records = package(make)
    results = list(group.required_probe_results)
    results[1] = replace(results[1], probe=replace(results[1].probe, kind=ProbeKind.IGNORE_THREAT))
    replace_results(group, records, results)
    rejects(bundle, claim, "REFUTATION")


@pytest.mark.parametrize(
    "mutation",
    [
        "omitted",
        "reversed",
        "alternatives",
        "equivalent-true",
        "equivalent-none",
        "response",
        "comparator",
        "failed",
    ],
)
def test_counterfactual_must_match_complete_group(mutation):
    bundle, claim, group, records = package(ignored_material)
    (cf,) = of_type(records, CounterfactualEvidence)
    if mutation == "omitted":
        tamper(cf, probe_results=cf.probe_results[:2])
    elif mutation == "reversed":
        tamper(cf, probe_results=cf.probe_results[::-1])
    elif mutation == "alternatives":
        tamper(cf, representative_alternatives=cf.representative_alternatives[:1])
    elif mutation.startswith("equivalent"):
        tamper(cf, equivalent_alternative_benefit=True if mutation.endswith("true") else None)
    elif mutation == "response":
        tamper(cf, tested_response=None)
    elif mutation == "comparator":
        tamper(cf, comparator_move=group.played_move)
    else:
        tamper(cf, failed_alternatives=cf.representative_alternatives)
    rejects(bundle, claim, "CounterfactualEvidence")


@pytest.mark.parametrize("make", SCENARIOS)
def test_foreign_variation_rejected_even_for_exact(make):
    bundle, claim, _, records = package(make)
    variation = of_type(records, VariationEvidence)[0]
    tamper(variation, probe=replace(variation.probe, intervention_move=ChessMove("e1d1")))
    rejects(bundle, claim, "required probe")


@pytest.mark.parametrize("mutation", ["foreign", "another-required"])
@pytest.mark.parametrize("make", [direct_material, ignored_material])
def test_material_must_belong_to_its_variation(make, mutation):
    bundle, claim, group, records = package(make)
    variation = of_type(records, VariationEvidence)[0]
    probe = (
        group.required_probe_results[1].probe
        if mutation == "another-required"
        else replace(variation.probe, intervention_move=ChessMove("e1d1"))
    )
    tamper(variation.material_evidence[0], probe=probe)
    rejects(bundle, claim, "material probe")


@pytest.mark.parametrize("make", [forces, exact_mate, ignored_material])
@pytest.mark.parametrize("mutation", ["foreign-engine", "duplicate-engine", "duplicate-variation"])
def test_all_owned_provenance_including_unreferenced_exact_records(make, mutation):
    bundle, claim, group, records = package(make)
    if mutation == "duplicate-variation":
        inserted = replace(of_type(records, VariationEvidence)[0], evidence_id="ev_999")
    else:
        original = of_type(records, EngineEvidence)[0]
        result = original.probe_result
        if mutation == "foreign-engine":
            result = replace(
                result, probe=replace(result.probe, intervention_move=ChessMove("e1d1"))
            )
        inserted = replace(original, evidence_id="ev_999", probe_result=result)
    # Preserve type order so the provenance check is the one being challenged.
    index = next(i for i, r in enumerate(bundle.evidence) if type(r) is type(inserted))
    new_records = (*bundle.evidence[:index], inserted, *bundle.evidence[index:])
    tamper(bundle, evidence=new_records)
    tamper(group, evidence_ids=tuple(r.evidence_id for r in new_records))
    if claim.confidence is ClaimConfidence.ENGINE_VERIFIED:
        claim = replace(claim, evidence_ids=group.evidence_ids)
    rejects(bundle, claim, "non-terminal|at most one")


@pytest.mark.parametrize("make", [direct_mate, ignored_mate, direct_material, ignored_material])
def test_missing_engine_evidence_rejected(make):
    bundle, claim, group, records = package(make)
    engine = of_type(records, EngineEvidence)[0]
    kept = tuple(r for r in records if r is not engine)
    tamper(bundle, evidence=kept)
    tamper(group, evidence_ids=tuple(r.evidence_id for r in kept))
    rejects(bundle, replace(claim, evidence_ids=group.evidence_ids), "exactly one EngineEvidence")


@pytest.mark.parametrize("identity", [False, True])
def test_mixed_engine_identity_or_settings_rejected(identity):
    bundle, claim, group, _ = package(ignored_material)
    analysis = group.required_probe_results[1].engine_analysis
    if identity:
        tamper(analysis, engine=EngineIdentity("Other", "2"))
    else:
        tamper(analysis, settings=EngineSettings(EngineLimit(depth=99)))
    rejects(bundle, claim, "engine identities|engine settings")


@pytest.mark.parametrize("make", [forces, ignored_mate, ignored_material])
def test_wrong_response_source_position_rejected(make):
    bundle, claim, group, _ = package(make)
    tamper(group, response=MoveClaimEntity(group.response.move, bundle.base_position_id))
    rejects(bundle, claim, "played branch")


@pytest.mark.parametrize("make", [direct_material, ignored_material])
@pytest.mark.parametrize("index", [0, 1, 2])
def test_material_required_for_each_batch_a_probe(make, index):
    bundle, claim, _, records = package(make)
    variation = of_type(records, VariationEvidence)[index]
    tamper(variation, material_evidence=())
    rejects(bundle, claim, "every required probe")


def test_final_ignored_material_required_and_resource_motif_required():
    bundle, claim, _, records = package(ignored_material)
    tamper(of_type(records, VariationEvidence)[-1], material_evidence=())
    rejects(bundle, claim, "every required probe")
    bundle, claim, _, records = package(ignored_material)
    motif = of_type(records, MotifEvidence)[0]
    candidate = motif.candidates[0]
    tamper(candidate, kind=TacticalCandidateKind.HANGING_PIECE)
    rejects(bundle, claim, "resource motif")


@pytest.mark.parametrize("make", [ignored_material, ignored_mate])
def test_replay_on_batch_a_instead_of_causal_ignore_rejected(make):
    bundle, claim, _, records = package(make)
    causal = of_type(records, VariationEvidence)[-1]
    played = (
        of_type(records, VariationEvidence)[0]
        if make is ignored_material
        else VariationEvidence(
            "ev_999", bundle.base_position_id, bundle.groups[0].required_probe_results[0].probe
        )
    )
    if make is ignored_mate:
        tamper(bundle, evidence=(*bundle.evidence[:-1], played, bundle.evidence[-1]))
        tamper(bundle.groups[0], evidence_ids=tuple(r.evidence_id for r in bundle.evidence))
        claim = replace(claim, evidence_ids=bundle.groups[0].evidence_ids)
    tamper(
        played,
        board_deltas=causal.board_deltas,
        replayed_pv_ends_in_checkmate=causal.replayed_pv_ends_in_checkmate,
    )
    tamper(causal, board_deltas=(), replayed_pv_ends_in_checkmate=None)
    rejects(bundle, claim, "causal")


@pytest.mark.parametrize("make", [direct_material, ignored_material])
def test_causal_material_deltas_nonempty(make):
    bundle, claim, group, records = package(make)
    tamper(of_type(records, BoardFactEvidence)[0], board_deltas=())
    index = -1 if group.evidence_form is EvidenceForm.TESTED_RESPONSE else 0
    tamper(of_type(records, VariationEvidence)[index], board_deltas=())
    rejects(bundle, claim, "nonempty causal")


@pytest.mark.parametrize(
    "mutation",
    ["sole-response", "missing-candidate", "wrong-candidate", "duplicate-candidate", "board-moves"],
)
def test_forces_response_requires_exact_local_records(mutation):
    bundle, claim, group, records = package(forces)
    (board,) = of_type(records, BoardFactEvidence)
    (motif,) = of_type(records, MotifEvidence)
    if mutation == "sole-response":
        tamper(board, sole_response=None)
    elif mutation == "missing-candidate":
        tamper(motif.candidates[0], kind=TacticalCandidateKind.CHECK)
    elif mutation == "wrong-candidate":
        tamper(motif.candidates[0], responses=(ChessMove("a8a7"),))
    elif mutation == "duplicate-candidate":
        tamper(motif, candidates=(*motif.candidates, motif.candidates[0]))
    else:
        tamper(board, moves=tuple(m for m in board.moves if m != group.response))
    rejects(bundle, claim, "sole_response|candidate|sole reply")


@pytest.mark.parametrize(
    "mutation", ["board-terminal", "winner", "flag", "deltas", "variation", "engine-selection"]
)
def test_exact_mate_requires_exact_causal_evidence(mutation):
    bundle, claim, group, records = package(exact_mate)
    if mutation == "board-terminal":
        tamper(of_type(records, BoardFactEvidence)[0], terminal=None)
    elif mutation == "winner":
        tamper(group.required_probe_results[0].terminal, winner=None)
    elif mutation == "flag":
        tamper(group, replayed_pv_ends_in_checkmate=False)
        tamper(of_type(records, VariationEvidence)[0], replayed_pv_ends_in_checkmate=False)
    elif mutation == "deltas":
        tamper(of_type(records, BoardFactEvidence)[0], board_deltas=())
        tamper(of_type(records, VariationEvidence)[0], board_deltas=())
    elif mutation == "variation":
        kept = tuple(r for r in records if not isinstance(r, VariationEvidence))
        tamper(bundle, evidence=kept)
        tamper(group, evidence_ids=tuple(r.evidence_id for r in kept))
        claim = replace(
            claim,
            evidence_ids=tuple(eid for eid in claim.evidence_ids if eid in group.evidence_ids),
        )
    else:
        claim = replace(claim, evidence_ids=group.evidence_ids)
    rejects(bundle, claim, "exact|EXACT|causal variation")


@pytest.mark.parametrize("make", [forces, direct_material])
def test_non_mate_metadata_rejected(make):
    bundle, claim, group, _ = package(make)
    tamper(group, mate_evidence_level=MateEvidenceLevel.ENGINE_LINE)
    rejects(bundle, claim, "mate metadata")


def test_engine_line_not_upgraded_by_exact_replay():
    bundle, claim, _, _ = package(direct_mate)
    rejects(
        bundle,
        replace(
            claim, predicate=ClaimPredicate.DELIVERS_CHECKMATE, confidence=ClaimConfidence.EXACT
        ),
        "mapping",
    )


def test_exact_immediate_tested_response_is_invalid():
    bundle, claim, group, _ = package(ignored_mate)
    tamper(group, mate_evidence_level=MateEvidenceLevel.EXACT_IMMEDIATE)
    rejects(bundle, claim, "DIRECT only")


def test_full_package_bijection_and_canonical_order_ids():
    bundle = evidence(direct_mate())
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


def test_one_group_without_claim_and_wrong_input_type():
    bundle, _, _, _ = package(forces)
    with pytest.raises(IncompatibleClaimEvidenceError, match="one claim"):
        validate(bundle)
    with pytest.raises(ExplanationClaimError):
        validate(None)
    with pytest.raises(ExplanationClaimError):
        ClaimValidator().validate_good_move(bundle, [])


def test_p8_family_not_accepted():
    from _p8_claim_scenarios import claims as bad_claims
    from _p8_claim_scenarios import evidence as bad_evidence
    from _p8_claim_scenarios import knight

    bundle = bad_evidence(knight())
    with pytest.raises(IncompatibleClaimEvidenceError, match="GOOD_MOVE_BENEFIT"):
        validate(bundle, *bad_claims(bundle))


def test_engine_verified_full_selection_required():
    bundle, claim, _, _ = package(ignored_material)
    rejects(bundle, replace(claim, evidence_ids=claim.evidence_ids[:-1]), "complete group")


def test_all_terminal_engine_group_needs_no_synthetic_engine():
    result = direct_material()
    benefit = result.benefits[0]
    results = tuple(
        replace(
            r,
            engine_analysis=None,
            root_moves=None,
            terminal=TerminalOutcome(TerminalKind.STALEMATE, None),
        )
        for r in benefit.probe_results
    )
    result = replace(result, benefits=(replace(benefit, probe_results=results),))
    bundle = evidence(result)
    assert not of_type(bundle.evidence, EngineEvidence)
    built = claims(bundle)
    assert validate(bundle, *built) == built


@pytest.mark.parametrize(
    "mutation",
    [
        "subject",
        "missing-piece",
        "frame",
        "extra-alternative",
        "missing-response",
        "unknown-id",
        "base",
    ],
)
def test_entity_and_evidence_closure_rejected(mutation):
    bundle, claim, group, records = package(forces)
    if mutation == "subject":
        claim = replace(claim, subject=MoveClaimEntity(ChessMove("b1h1"), bundle.base_position_id))
    elif mutation == "missing-piece":
        for record in records:
            if hasattr(record, "pieces"):
                tamper(record, pieces=())
    elif mutation == "frame":
        piece = of_type(records, BoardFactEvidence)[0].pieces[0]
        tamper(piece, at_position_id=group.response.position_id)
    elif mutation == "extra-alternative":
        alternative = MoveClaimEntity(
            group.representative_alternatives[0].move, bundle.base_position_id
        )
        claim = replace(claim, objects=(*claim.objects, alternative))
    elif mutation == "missing-response":
        claim = replace(claim, objects=tuple(o for o in claim.objects if o != group.response))
    elif mutation == "unknown-id":
        claim = replace(claim, evidence_ids=(*claim.evidence_ids, "ev_999"))
    else:
        tamper(claim, base_position_id="pos_foreign")
    rejects(bundle, claim)


def test_evidence_cross_group_rejected():
    bundle = evidence(direct_mate())
    first, second = claims(bundle)
    first = replace(first, evidence_ids=(*first.evidence_ids, second.evidence_ids[0]))
    with pytest.raises(IncompatibleClaimEvidenceError, match="more than one group"):
        validate(bundle, first, second)


@pytest.mark.parametrize("make", [forces, exact_mate, direct_material])
def test_direct_counterfactual_cannot_carry_tested_q(make):
    bundle, claim, group, records = package(make)
    tamper(of_type(records, CounterfactualEvidence)[0], tested_response=group.played_move)
    rejects(bundle, claim, "DIRECT CounterfactualEvidence")


def test_representative_scope_not_emitted_for_strong():
    bundle, claim, _, _ = package(direct_material)
    tamper(claim, scope=ClaimScope.REPRESENTATIVE_ALTERNATIVES)
    rejects(bundle, claim, "mapping")


@pytest.mark.parametrize("kind", [Kind.PREVENTS_MATE, Kind.PREVENTS_MATERIAL_LOSS])
def test_preservation_groups_are_rejected(kind):
    bundle, claim, group, _ = package(direct_material)
    tamper(group, source_kind=kind, evidence_form=EvidenceForm.PRESERVATION)
    rejects(bundle, claim, "STRONG")


@pytest.mark.parametrize("make", [direct_mate, ignored_mate])
def test_causal_engine_mate_variation_is_required(make):
    bundle, claim, group, records = package(make)
    index = -1 if group.evidence_form is EvidenceForm.TESTED_RESPONSE else 0
    causal_probe = group.required_probe_results[index].probe
    kept = tuple(
        r for r in records if not isinstance(r, VariationEvidence) or r.probe != causal_probe
    )
    tamper(bundle, evidence=kept)
    tamper(group, evidence_ids=tuple(r.evidence_id for r in kept))
    rejects(bundle, replace(claim, evidence_ids=group.evidence_ids), "causal variation")


@pytest.mark.parametrize("foreign", [False, True])
def test_material_binding_is_validated_in_exact_unreferenced_provenance(foreign):
    bundle, claim, group, records = package(exact_mate)
    _, _, _, material_records = package(direct_material)
    material = of_type(material_records, VariationEvidence)[0].material_evidence[0]
    variation = of_type(records, VariationEvidence)[0]
    retained = replace(material, probe=variation.probe)
    tamper(variation, material_evidence=(retained,))
    assert validate(bundle, claim) == (claim,)
    probe = (
        replace(variation.probe, intervention_move=ChessMove("e1d1"))
        if foreign
        else group.required_probe_results[1].probe
    )
    tamper(retained, probe=probe)
    rejects(bundle, claim, "material probe")


def test_extra_exact_engine_for_terminal_probe_rejected():
    bundle, claim, group, records = package(exact_mate)
    original = of_type(records, EngineEvidence)[0]
    terminal_engine = tamper(
        replace(original, evidence_id="ev_999"), probe_result=group.required_probe_results[0]
    )
    index = records.index(original)
    kept = (*records[:index], terminal_engine, *records[index:])
    tamper(bundle, evidence=kept)
    tamper(group, evidence_ids=tuple(r.evidence_id for r in kept))
    rejects(bundle, claim, "non-terminal required results")
