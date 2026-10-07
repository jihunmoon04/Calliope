from dataclasses import replace

import pytest
from _p9_strong_claim_scenarios import (
    SCENARIOS,
    Kind,
    claims,
    direct_mate,
    direct_material,
    equivalent_mate,
    evidence,
    exact_mate,
    forces,
    ignored_mate,
    ignored_material,
    of_type,
    quiet,
    supported_with_refuted_sibling,
    tamper,
)

from calliope.domain.analysis import (
    GoodMoveBenefitStatus,
    GoodMoveExplanationStatus,
    GoodMoveMode,
    MateEvidenceLevel,
    ProbeKind,
    RepresentativeAlternative,
    TerminalKind,
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
def test_real_p9_retained_evidence_and_global_ids(make):
    result = make()
    bundle = evidence(result)
    supported = [b for b in result.benefits if b.status is GoodMoveBenefitStatus.SUPPORTED]
    assert len(bundle.groups) == len(supported)
    assert tuple(r.evidence_id for r in bundle.evidence) == tuple(
        mint_evidence_id(i) for i in range(1, len(bundle.evidence) + 1)
    )
    for group, benefit in zip(bundle.groups, supported, strict=True):
        records = [r for r in bundle.evidence if r.evidence_id in group.evidence_ids]
        assert group.source_family is EvidenceSourceFamily.GOOD_MOVE_BENEFIT
        assert group.source_kind is benefit.kind
        assert group.required_probe_results is benefit.probe_results
        assert group.representative_alternatives is benefit.alternatives
        assert group.comparator_move is None and group.failed_alternatives == ()
        assert group.source_subject == tuple(sorted(benefit.subject, key=base_piece_sort_key))
        assert [EVIDENCE_RECORD_TYPE_ORDER.index(type(r)) for r in records] == sorted(
            EVIDENCE_RECORD_TYPE_ORDER.index(type(r)) for r in records
        )
        (board,) = of_type(records, BoardFactEvidence)
        expected_pieces = tuple(
            base_frame_piece_entity(result.base_position_id, ref)
            for ref in sorted({*benefit.subject, *benefit.affected_pieces}, key=base_piece_sort_key)
        )
        assert board.pieces == expected_pieces and board.board_deltas is benefit.board_deltas
        expected_moves = [benefit.played_move.uci, *(a.move.uci for a in benefit.alternatives)]
        if benefit.tested_response:
            expected_moves.append(benefit.tested_response.uci)
            assert (
                group.response.position_id == benefit.probe_results[0].analysis_position.position_id
            )
        assert [m.move.uci for m in board.moves] == expected_moves
        motifs = of_type(records, MotifEvidence)
        assert len(motifs) == int(bool(benefit.tactical_candidates))
        if motifs:
            assert motifs[0].candidates is benefit.tactical_candidates
        assert [e.probe_result for e in of_type(records, EngineEvidence)] == [
            r for r in benefit.probe_results if r.engine_analysis is not None
        ]
        (counterfactual,) = of_type(records, CounterfactualEvidence)
        assert records[-1] is counterfactual
        assert counterfactual.probe_results is benefit.probe_results
        assert counterfactual.representative_alternatives is benefit.alternatives
        assert counterfactual.equivalent_alternative_benefit is False
        assert counterfactual.form is group.evidence_form
        assert counterfactual.tested_response == (
            group.response if group.evidence_form is EvidenceForm.TESTED_RESPONSE else None
        )
        variations = of_type(records, VariationEvidence)
        assert [m for v in variations for m in v.material_evidence] == list(
            benefit.material_evidence
        )
        causal_index = -1 if group.evidence_form is EvidenceForm.TESTED_RESPONSE else 0
        causal = benefit.probe_results[causal_index]
        for variation in variations:
            assert all(m.probe == variation.probe for m in variation.material_evidence)
            matching = next(r for r in benefit.probe_results if r.probe == variation.probe)
            assert variation.terminal == matching.terminal
            if matching is causal:
                assert variation.board_deltas is benefit.board_deltas
                assert (
                    variation.replayed_pv_ends_in_checkmate is benefit.replayed_pv_ends_in_checkmate
                )
                assert variation.pieces == expected_pieces
            else:
                assert (
                    variation.board_deltas == () and variation.replayed_pv_ends_in_checkmate is None
                )
        if benefit.kind is Kind.FORCES_RESPONSE:
            assert board.sole_response == group.response and board.terminal is None
        elif benefit.mate_evidence_level is MateEvidenceLevel.EXACT_IMMEDIATE:
            assert board.terminal is causal.terminal
            assert board.terminal.kind is TerminalKind.CHECKMATE
        else:
            assert board.terminal is None


@pytest.mark.parametrize("make", [equivalent_mate, quiet])
def test_refuted_and_quiet_real_sources_stay_silent(make):
    result = make()
    assert result.status is not GoodMoveExplanationStatus.SUPPORTED
    bundle = evidence(result)
    assert bundle.evidence == bundle.groups == claims(bundle) == ()


@pytest.mark.parametrize(
    "status",
    [
        GoodMoveExplanationStatus.NOT_APPLICABLE,
        GoodMoveExplanationStatus.REFUTED,
        GoodMoveExplanationStatus.INCONCLUSIVE,
    ],
)
def test_non_supported_parent_returns_exact_empty_shape(status):
    result = tamper(forces(), status=status)
    bundle = evidence(result)
    assert bundle.base_position_id == result.base_position_id
    assert bundle.evidence == bundle.groups == ()


def test_supported_parent_ignores_refuted_and_inconclusive_siblings():
    for status in (GoodMoveBenefitStatus.REFUTED, GoodMoveBenefitStatus.INCONCLUSIVE):
        result = direct_mate()
        assert len(result.benefits) == 2
        tamper(result.benefits[0], status=status)
        assert [g.source_kind for g in evidence(result).groups] == [Kind.MATE_THREAT]


def test_real_supported_parent_with_refuted_mate_sibling():
    result = supported_with_refuted_sibling()
    assert result.status is GoodMoveExplanationStatus.SUPPORTED
    assert [b.status for b in result.benefits] == [
        GoodMoveBenefitStatus.SUPPORTED,
        GoodMoveBenefitStatus.REFUTED,
    ]
    bundle = evidence(result)
    assert [g.source_kind for g in bundle.groups] == [Kind.FORCES_RESPONSE]
    assert len(claims(bundle)) == 1


def test_supported_child_order_does_not_control_global_evidence_ids():
    result = direct_mate()
    canonical = evidence(result)
    reversed_result = replace(result, benefits=result.benefits[::-1])
    assert evidence(reversed_result) == canonical
    assert repr(evidence(reversed_result)) == repr(canonical)


@pytest.mark.parametrize("value", [None, (), object()])
def test_wrong_result_type(value):
    with pytest.raises(ExplanationEvidenceError, match="GoodMoveExplanationResult"):
        evidence(value)


@pytest.mark.parametrize("value", [True, None, 0])
def test_literal_only_guard_precedes_empty_status(value):
    result = tamper(quiet(), literal_only_move_proven=value)
    with pytest.raises(ExplanationEvidenceError, match="literal_only"):
        evidence(result)


def test_supported_only_move_candidate_is_not_dropped():
    with pytest.raises(ExplanationEvidenceError, match="STRONG_MOVE"):
        evidence(tamper(forces(), mode=GoodMoveMode.ONLY_MOVE_CANDIDATE))


@pytest.mark.parametrize(
    "changes",
    [
        {"base_position_id": "pos_foreign"},
        {"played_move": ChessMove("e1d1")},
        {"mode": GoodMoveMode.ONLY_MOVE_CANDIDATE},
        {"alternatives": ()},
        {"alternative_scope": None},
        {"failed_alternatives": (RepresentativeAlternative(2, ChessMove("b1h1")),)},
        {"equivalent_alternative_benefit": True},
        {"equivalent_alternative_benefit": None},
        {"kind": Kind.PREVENTS_MATE},
        {"kind": Kind.PREVENTS_MATERIAL_LOSS},
    ],
)
def test_supported_child_binding_rechecked(changes):
    result = forces()
    tamper(result.benefits[0], **changes)
    with pytest.raises(ExplanationEvidenceError):
        evidence(result)


def test_san_difference_does_not_break_parent_child_move_identity():
    result = forces()
    changed = replace(result.benefits[0], played_move=ChessMove(result.played_move.uci, "Ra1+"))
    assert evidence(replace(result, benefits=(changed,))).groups


@pytest.mark.parametrize("make", [direct_material, ignored_material])
@pytest.mark.parametrize("mutation", ["foreign", "missing"])
def test_material_association_is_closed(make, mutation):
    result = make()
    (benefit,) = result.benefits
    if mutation == "missing":
        tamper(benefit, material_evidence=benefit.material_evidence[1:])
    else:
        material = benefit.material_evidence[0]
        foreign = replace(material.probe, intervention_move=ChessMove("e1d1"))
        tamper(material, probe=foreign)
    with pytest.raises(ExplanationEvidenceError, match="material"):
        evidence(result)


@pytest.mark.parametrize("mutation", ["terminal", "flag", "deltas"])
def test_exact_mate_missing_source_evidence_fails_closed(mutation):
    result = exact_mate()
    (benefit,) = result.benefits
    if mutation == "terminal":
        tamper(benefit.probe_results[0], terminal=None)
    elif mutation == "flag":
        tamper(benefit, replayed_pv_ends_in_checkmate=False)
    else:
        tamper(benefit, board_deltas=())
    with pytest.raises(ExplanationEvidenceError, match="exact"):
        evidence(result)


@pytest.mark.parametrize("make", [forces, ignored_material])
def test_required_motif_source_gap_fails_closed(make):
    result = make()
    tamper(result.benefits[0], tactical_candidates=())
    with pytest.raises(ExplanationEvidenceError, match="candidate|motif"):
        evidence(result)


@pytest.mark.parametrize("make", [forces, ignored_mate])
def test_batch_a_and_final_protocol_rechecked(make):
    result = make()
    benefit = result.benefits[0]
    tamper(benefit.probe_results[0].probe, execution_move=ChessMove("a8b8"))
    with pytest.raises(ExplanationEvidenceError, match="REFUTATION"):
        evidence(result)


def test_tested_causal_deltas_are_never_attached_to_batch_a():
    result = ignored_material()
    bundle = evidence(result)
    variations = of_type(bundle.evidence, VariationEvidence)
    assert len(variations) == 4
    assert all(not v.board_deltas for v in variations[:-1])
    assert variations[-1].probe.kind is ProbeKind.IGNORE_THREAT
    assert variations[-1].board_deltas is result.benefits[0].board_deltas
    assert [m.move.uci for m in variations[-1].moves] == [
        result.played_move.uci,
        result.benefits[0].tested_response.uci,
    ]


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
        "final-position",
    ],
)
def test_raw_p9_protocol_fails_closed(mutation):
    result = ignored_material()
    benefit = result.benefits[0]
    probes = list(benefit.probe_results)
    if mutation == "no-ignore":
        probes.pop()
    elif mutation == "not-final":
        probes[1], probes[-1] = probes[-1], probes[1]
    elif mutation == "wrong-q":
        probes[-1] = replace(
            probes[-1], probe=replace(probes[-1].probe, execution_move=ChessMove("a7a5"))
        )
    elif mutation == "wrong-played":
        probes[-1] = replace(
            probes[-1], probe=replace(probes[-1].probe, intervention_move=ChessMove("a1a4"))
        )
    elif mutation == "second-ignore":
        probes[1] = probes[-1]
    elif mutation == "too-many":
        probes.append(probes[-1])
    elif mutation == "missing-played":
        probes.pop(0)
    elif mutation == "alternative-order":
        probes[1], probes[2] = probes[2], probes[1]
    elif mutation == "alternative-uci":
        probes[1] = replace(
            probes[1], probe=replace(probes[1].probe, intervention_move=ChessMove("e1f1"))
        )
    else:
        tamper(probes[-1].analysis_position, position_id="pos_foreign")
    tamper(benefit, probe_results=tuple(probes))
    with pytest.raises(ExplanationEvidenceError):
        evidence(result)


@pytest.mark.parametrize("mutation", ["reversed", "none", "three", "duplicate"])
def test_alternative_rank_shape_rechecked_independently_of_parent_binding(mutation):
    result = forces()
    alternatives = result.alternatives
    if mutation == "reversed":
        alternatives = alternatives[::-1]
    elif mutation == "none":
        alternatives = ()
    elif mutation == "three":
        alternatives = (*alternatives, RepresentativeAlternative(4, ChessMove("b1g1")))
    else:
        alternatives = (alternatives[0], alternatives[0])
    tamper(result, alternatives=alternatives)
    tamper(result.benefits[0], alternatives=alternatives)
    with pytest.raises(ExplanationEvidenceError, match="alternatives"):
        evidence(result)
