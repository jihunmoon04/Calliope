from dataclasses import replace

import pytest
from _p9_preservation_claim_scenarios import (
    SCENARIOS,
    Kind,
    claims,
    engine_mate,
    evidence,
    inconclusive,
    mate_all,
    mate_subset,
    material_all,
    material_subset,
    no_alternatives,
    of_type,
    only_kind,
    quiet,
    refuted,
)

from calliope.domain.analysis import (
    GoodMoveBenefitStatus,
    GoodMoveExplanationStatus,
    GoodMoveMode,
    MateEvidenceLevel,
    ProbeKind,
    RepresentativeAlternative,
)
from calliope.domain.chess import ChessMove
from calliope.domain.explanation import (
    EVIDENCE_RECORD_TYPE_ORDER,
    BoardFactEvidence,
    CounterfactualEvidence,
    EngineEvidence,
    EvidenceForm,
    EvidenceSourceFamily,
    MotifEvidence,
    VariationEvidence,
    base_frame_piece_entity,
    base_piece_sort_key,
    mint_evidence_id,
)
from calliope.errors import ExplanationEvidenceError


@pytest.mark.parametrize("make", SCENARIOS)
def test_real_p9_preservation_retains_complete_source(make):
    result = make()
    bundle = evidence(result)
    assert result.mode is GoodMoveMode.ONLY_MOVE_CANDIDATE
    supported = [b for b in result.benefits if b.status is GoodMoveBenefitStatus.SUPPORTED]
    assert len(bundle.groups) == len(supported)
    assert [r.evidence_id for r in bundle.evidence] == [
        mint_evidence_id(i) for i in range(1, len(bundle.evidence) + 1)
    ]
    for group, benefit in zip(bundle.groups, supported, strict=True):
        records = [r for r in bundle.evidence if r.evidence_id in group.evidence_ids]
        assert group.source_family is EvidenceSourceFamily.GOOD_MOVE_BENEFIT
        assert group.source_kind is benefit.kind
        assert group.evidence_form is EvidenceForm.PRESERVATION
        assert group.required_probe_results is benefit.probe_results
        assert group.representative_alternatives is benefit.alternatives
        assert group.failed_alternatives is benefit.failed_alternatives
        assert group.response is group.comparator_move is None
        assert group.mate_evidence_level is benefit.mate_evidence_level
        assert group.replayed_pv_ends_in_checkmate is benefit.replayed_pv_ends_in_checkmate
        assert group.source_subject == tuple(sorted(benefit.subject, key=base_piece_sort_key))
        (board,) = of_type(records, BoardFactEvidence)
        assert board.board_deltas is benefit.board_deltas
        assert board.terminal is board.sole_response is None
        assert [m.move.uci for m in board.moves] == [
            benefit.played_move.uci,
            *(a.move.uci for a in benefit.alternatives),
        ]
        assert all(m.position_id == result.base_position_id for m in board.moves)
        assert board.pieces == tuple(
            base_frame_piece_entity(result.base_position_id, ref)
            for ref in sorted({*benefit.subject, *benefit.affected_pieces}, key=base_piece_sort_key)
        )
        motifs = of_type(records, MotifEvidence)
        assert len(motifs) == int(bool(benefit.tactical_candidates))
        if motifs:
            assert motifs[0].candidates is benefit.tactical_candidates
            assert motifs[0].moves == () and motifs[0].pieces == board.pieces
        assert [e.probe_result for e in of_type(records, EngineEvidence)] == [
            r for r in benefit.probe_results if r.engine_analysis is not None
        ]
        variations = of_type(records, VariationEvidence)
        if benefit.kind is Kind.PREVENTS_MATE:
            assert variations == []  # aggregate metadata has no branch association
        else:
            assert len(variations) == len(benefit.probe_results)
            for index, variation in enumerate(variations):
                assert variation.probe is benefit.probe_results[index].probe
                assert variation.moves == (board.moves[index],)
                assert len(variation.material_evidence) == 1
                assert variation.material_evidence[0] is benefit.material_evidence[index]
                assert variation.material_evidence[0].probe == variation.probe
                assert variation.terminal is benefit.probe_results[index].terminal
                assert variation.board_deltas == ()
                assert variation.replayed_pv_ends_in_checkmate is None
        (cf,) = of_type(records, CounterfactualEvidence)
        assert records[-1] is cf
        assert cf.form is EvidenceForm.PRESERVATION
        assert cf.probe_results is benefit.probe_results
        assert cf.representative_alternatives is benefit.alternatives
        assert cf.failed_alternatives is benefit.failed_alternatives
        assert cf.equivalent_alternative_benefit is (
            len(benefit.failed_alternatives) < len(benefit.alternatives)
        )
        assert cf.tested_response is cf.comparator_move is None
        type_ranks = [EVIDENCE_RECORD_TYPE_ORDER.index(type(r)) for r in records]
        assert type_ranks == sorted(type_ranks)


@pytest.mark.parametrize("make", [quiet, no_alternatives, refuted, inconclusive])
def test_real_silent_only_move_sources_remain_empty(make):
    result = make()
    assert result.mode is GoodMoveMode.ONLY_MOVE_CANDIDATE
    assert result.status is not GoodMoveExplanationStatus.SUPPORTED
    bundle = evidence(result)
    assert bundle.base_position_id == result.base_position_id
    assert bundle.evidence == bundle.groups == claims(bundle) == ()


def test_supported_parent_ignores_refuted_and_inconclusive_children():
    result = mate_all()
    first, second = result.benefits
    for status in (GoodMoveBenefitStatus.REFUTED, GoodMoveBenefitStatus.INCONCLUSIVE):
        sibling = replace(second, status=status)
        mixed = replace(result, benefits=(first, sibling))
        assert [g.source_kind for g in evidence(mixed).groups] == [Kind.PREVENTS_MATE]


def test_supported_only_mode_rejects_strong_kind():
    result = material_all()
    child = replace(result.benefits[0], kind=Kind.MATERIAL_THREAT)
    with pytest.raises(ExplanationEvidenceError, match="preservation benefits only"):
        evidence(replace(result, benefits=(child,)))


@pytest.mark.parametrize("mutation", ["none", "unknown", "wrong-rank", "wrong-uci"])
def test_invalid_failed_subset_rejected_without_redeciding_outcomes(mutation):
    result = only_kind(mate_all(), Kind.PREVENTS_MATE)
    child = result.benefits[0]
    if mutation == "none":
        failed = ()
    elif mutation == "unknown":
        failed = (RepresentativeAlternative(4, ChessMove("d1c1")),)
    elif mutation == "wrong-rank":
        failed = (replace(child.failed_alternatives[0], rank=3),)
    else:
        failed = (replace(child.failed_alternatives[0], move=ChessMove("d1b1")),)
    # Domain constructors reject non-members; empty subset reaches the mapper and fails.
    if mutation == "none":
        with pytest.raises(ExplanationEvidenceError, match="failed alternatives"):
            evidence(replace(result, benefits=(replace(child, failed_alternatives=failed),)))
    else:
        with pytest.raises(ValueError, match="subset"):
            replace(child, failed_alternatives=failed)


@pytest.mark.parametrize("make", [mate_all, mate_subset, material_all, material_subset])
@pytest.mark.parametrize("value", [None, "opposite"])
def test_equivalence_is_preservation_subset_boolean(make, value):
    result = make()
    child = result.benefits[0]
    wrong = None if value is None else not child.equivalent_alternative_benefit
    result = replace(result, benefits=(replace(child, equivalent_alternative_benefit=wrong),))
    with pytest.raises(ExplanationEvidenceError, match="equivalence"):
        evidence(result)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown"])
def test_material_requires_one_exact_measurement_for_every_probe(mutation):
    result = material_all()
    child = result.benefits[0]
    materials = child.material_evidence
    if mutation == "missing":
        materials = materials[1:]
    elif mutation == "duplicate":
        materials = (*materials, materials[0])
    else:
        foreign = replace(materials[0].probe, intervention_move=ChessMove("d1c1"))
        materials = (replace(materials[0], probe=foreign), *materials[1:])
    with pytest.raises(ExplanationEvidenceError, match="material"):
        evidence(replace(result, benefits=(replace(child, material_evidence=materials),)))


def test_material_input_order_does_not_change_deterministic_bundle():
    result = material_all()
    child = result.benefits[0]
    reversed_result = replace(
        result, benefits=(replace(child, material_evidence=child.material_evidence[::-1]),)
    )
    assert evidence(reversed_result) == evidence(result)
    assert repr(evidence(reversed_result)) == repr(evidence(result))


def test_child_order_and_independent_runs_keep_identical_evidence():
    result = mate_all()
    built = evidence(result)
    assert len(built.groups) == 2
    assert evidence(mate_all()) == built
    assert repr(evidence(mate_all())) == repr(built)
    assert evidence(replace(result, benefits=result.benefits[::-1])) == built


def test_aggregate_mate_evidence_never_gets_spread_onto_variations():
    bundle = evidence(only_kind(mate_all(), Kind.PREVENTS_MATE))
    assert of_type(bundle.evidence, BoardFactEvidence)[0].board_deltas
    assert of_type(bundle.evidence, MotifEvidence)[0].candidates
    assert not of_type(bundle.evidence, VariationEvidence)
    assert claims(bundle)
    engine_bundle = evidence(engine_mate())
    assert not of_type(engine_bundle.evidence, VariationEvidence)
    assert engine_bundle.groups[0].replayed_pv_ends_in_checkmate is False


def test_external_batch_b_is_not_retained_as_preservation_provenance():
    from _p9_preservation_claim_scenarios import MATE_NOW, QUEEN, SAFE, explain

    result = explain(QUEEN, ("h2h3", "d1a1", "d1b1"), {**SAFE, **MATE_NOW}, attach="f7f6")
    for group in evidence(result).groups:
        assert len(group.required_probe_results) == 3
        assert all(r.probe.kind is ProbeKind.REFUTATION for r in group.required_probe_results)


@pytest.mark.parametrize("make", [mate_all, material_all])
def test_missing_required_aggregate_deltas_is_source_gap(make):
    result = make()
    kind = Kind.PREVENTS_MATE if make is mate_all else Kind.PREVENTS_MATERIAL_LOSS
    result = only_kind(result, kind)
    child = replace(result.benefits[0], board_deltas=())
    with pytest.raises(ExplanationEvidenceError, match="deltas"):
        evidence(replace(result, benefits=(child,)))


def test_exact_mate_aggregate_flag_is_required():
    result = only_kind(mate_all(), Kind.PREVENTS_MATE)
    child = replace(result.benefits[0], replayed_pv_ends_in_checkmate=False)
    assert child.mate_evidence_level is MateEvidenceLevel.EXACT_IMMEDIATE
    with pytest.raises(ExplanationEvidenceError, match="flag True"):
        evidence(replace(result, benefits=(child,)))
