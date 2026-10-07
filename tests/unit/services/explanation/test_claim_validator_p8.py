from dataclasses import replace

import pytest
from _p8_claim_scenarios import (
    Kind,
    claims,
    defender,
    engine_mate,
    evidence,
    exact_mate,
    fork,
    knight,
    only_kind,
    records_of,
    tamper,
)

from calliope.domain.analysis import (
    GoodMoveBenefitKind,
    MateEvidenceLevel,
    ProbeKind,
    ProbeResult,
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
    EvidenceSourceFamily,
    MoveClaimEntity,
    PieceClaimEntity,
    VariationEvidence,
    base_frame_piece_entity,
)
from calliope.errors import IncompatibleClaimEvidenceError
from calliope.services.explanation.claim_validator import ClaimValidator

_P = ClaimPredicate
_C = ClaimConfidence
_S = ClaimScope


def package(make, kind):
    """(bundle, the one claim, its group, the group's owned records) for one supported cause."""

    bundle = evidence(only_kind(make(), kind))
    (claim,) = claims(bundle)
    group = bundle.groups[0]
    return bundle, claim, group, records_of(bundle, group)


def validate(bundle, *claim_values):
    return ClaimValidator().validate_bad_move(bundle, tuple(claim_values))


def rejects(bundle, claim, match):
    with pytest.raises(IncompatibleClaimEvidenceError, match=match):
        validate(bundle, claim)


def of_type(records, record_type):
    return [r for r in records if type(r) is record_type]


# ---- baseline ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("make", "kind"),
    [
        (knight, Kind.NEWLY_HANGING_PIECE),
        (defender, Kind.REMOVED_DEFENDER),
        (fork, Kind.FORK_ALLOWED),
        (exact_mate, Kind.MATE_ALLOWED),
        (engine_mate, Kind.MATE_ALLOWED),
        (knight, Kind.MATERIAL_LOSS_LINE),
    ],
)
def test_untampered_claim_validates(make, kind):
    bundle, claim, _, _ = package(make, kind)
    assert validate(bundle, claim) == (claim,)


def test_validator_returns_same_tuple_object():
    bundle = evidence(defender())
    built = claims(bundle)
    assert ClaimValidator().validate_bad_move(bundle, built) is built


def test_duplicate_claim_ids_rejected():
    bundle, claim, _, _ = package(knight, Kind.NEWLY_HANGING_PIECE)
    with pytest.raises(IncompatibleClaimEvidenceError, match="unique"):
        validate(bundle, claim, claim)


# ---- mapping -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("make", "kind", "wrong"),
    [
        (knight, Kind.NEWLY_HANGING_PIECE, _P.ALLOWS_FORK),
        (defender, Kind.REMOVED_DEFENDER, _P.ALLOWS_MATERIAL_LOSS),
        (fork, Kind.FORK_ALLOWED, _P.REMOVES_DEFENDER),
        (knight, Kind.MATERIAL_LOSS_LINE, _P.LEAVES_PIECE_HANGING),
        (engine_mate, Kind.MATE_ALLOWED, _P.LEADS_TO_MATE),
    ],
)
def test_cross_kind_predicate_rejected(make, kind, wrong):
    bundle, claim, _, _ = package(make, kind)
    rejects(bundle, replace(claim, predicate=wrong), "cannot support")


@pytest.mark.parametrize(
    ("predicate", "scope"),
    [
        (_P.THREATENS_MATE_IF_IGNORED, _S.TESTED_RESPONSE),
        (_P.THREATENS_MATERIAL_IF_IGNORED, _S.TESTED_RESPONSE),
        (_P.AVOIDS_REPRESENTATIVE_MATE_FAILURE, _S.REPRESENTATIVE_ALTERNATIVES),
        (_P.AVOIDS_REPRESENTATIVE_MATERIAL_LOSS, _S.REPRESENTATIVE_ALTERNATIVES),
    ],
)
def test_non_local_p8_predicates_rejected(predicate, scope):
    bundle, claim, _, _ = package(knight, Kind.MATERIAL_LOSS_LINE)
    rejects(bundle, replace(claim, predicate=predicate, scope=scope), "cannot support")


@pytest.mark.parametrize(
    ("make", "kind"),
    [
        (engine_mate, Kind.MATE_ALLOWED),
        (knight, Kind.MATERIAL_LOSS_LINE),
        (exact_mate, Kind.MATE_ALLOWED),
        (fork, Kind.FORK_ALLOWED),
    ],
)
def test_forced_rejected_unconditionally(make, kind):
    bundle, claim, _, _ = package(make, kind)
    rejects(bundle, replace(claim, confidence=_C.FORCED), "FORCED")


def test_exact_cannot_be_downgraded_or_engine_line_upgraded():
    bundle, claim, _, _ = package(exact_mate, Kind.MATE_ALLOWED)
    rejects(bundle, replace(claim, confidence=_C.ENGINE_VERIFIED), "confidence")
    bundle, claim, _, _ = package(engine_mate, Kind.MATE_ALLOWED)
    rejects(bundle, replace(claim, confidence=_C.EXACT), "confidence")
    bundle, claim, _, _ = package(knight, Kind.MATERIAL_LOSS_LINE)
    rejects(bundle, replace(claim, confidence=_C.EXACT), "confidence")


# ---- same-punishment IGNORE_THREAT -------------------------------------------------------------


def test_same_punishment_probe_cannot_license_tested_response():
    bundle, claim, group, _ = package(defender, Kind.REMOVED_DEFENDER)
    assert group.required_probe_results[2].probe.kind is ProbeKind.IGNORE_THREAT
    assert validate(bundle, claim) == (claim,)
    rejects(
        bundle,
        replace(claim, predicate=_P.THREATENS_MATERIAL_IF_IGNORED, scope=_S.TESTED_RESPONSE),
        "cannot support",
    )
    rejects(
        bundle,
        replace(claim, predicate=_P.THREATENS_MATE_IF_IGNORED, scope=_S.TESTED_RESPONSE),
        "cannot support",
    )


# ---- entity closure ----------------------------------------------------------------------------


def test_subject_must_be_played_move():
    bundle, claim, group, _ = package(knight, Kind.NEWLY_HANGING_PIECE)
    other = MoveClaimEntity(group.comparator_move.move, bundle.base_position_id)
    rejects(bundle, replace(claim, subject=other), "played move")


def test_source_piece_removed_from_referenced_evidence_rejected():
    bundle, claim, _, owned = package(knight, Kind.NEWLY_HANGING_PIECE)
    for record in owned:
        if hasattr(record, "pieces"):
            tamper(record, pieces=())
    rejects(bundle, claim, "absent from referenced evidence")


def test_wrong_base_piece_rejected():
    bundle, claim, _, _ = package(knight, Kind.NEWLY_HANGING_PIECE)
    (piece,) = [o for o in claim.objects if isinstance(o, PieceClaimEntity)]
    other = base_frame_piece_entity(
        bundle.base_position_id, replace(piece.base_ref, base_square="e1")
    )
    objects = tuple(other if o is piece else o for o in claim.objects)
    rejects(bundle, replace(claim, objects=objects), "source pieces")


def test_same_piece_in_incompatible_frame_rejected():
    bundle, claim, group, _ = package(knight, Kind.NEWLY_HANGING_PIECE)
    (piece,) = [o for o in claim.objects if isinstance(o, PieceClaimEntity)]
    moved = PieceClaimEntity(
        piece.base_ref, group.response.position_id, "e4", piece.base_ref.piece_type
    )
    objects = tuple(moved if o is piece else o for o in claim.objects)
    rejects(bundle, replace(claim, objects=objects), "source pieces")


def test_punishment_removed_from_referenced_evidence_rejected():
    bundle, claim, group, owned = package(knight, Kind.NEWLY_HANGING_PIECE)
    key = (group.response.position_id, group.response.move.uci)
    for record in owned:
        if hasattr(record, "moves"):
            kept = tuple(m for m in record.moves if (m.position_id, m.move.uci) != key)
            tamper(record, moves=kept)
    rejects(bundle, claim, "absent from referenced evidence")


def test_punishment_with_wrong_position_rejected():
    bundle, claim, group, _ = package(knight, Kind.NEWLY_HANGING_PIECE)
    wrong = MoveClaimEntity(group.response.move, bundle.base_position_id)
    objects = tuple(wrong if o == group.response else o for o in claim.objects)
    rejects(bundle, replace(claim, objects=objects), "source pieces")


def test_punishment_with_different_san_only_is_the_same_move():
    bundle, claim, group, _ = package(knight, Kind.NEWLY_HANGING_PIECE)
    sanned = MoveClaimEntity(ChessMove(group.response.move.uci, "dxe4"), group.response.position_id)
    objects = tuple(sanned if o == group.response else o for o in claim.objects)
    changed = replace(claim, objects=objects)
    assert validate(bundle, changed) == (changed,)


def test_comparator_is_provenance_not_an_object():
    bundle, claim, group, owned = package(knight, Kind.NEWLY_HANGING_PIECE)
    assert group.comparator_move in of_type(owned, BoardFactEvidence)[0].moves
    extra = replace(claim, objects=(*claim.objects, group.comparator_move))
    rejects(bundle, extra, "source pieces")


def test_missing_punishment_object_rejected():
    bundle, claim, group, _ = package(knight, Kind.NEWLY_HANGING_PIECE)
    objects = tuple(o for o in claim.objects if o != group.response)
    rejects(bundle, replace(claim, objects=objects), "source pieces")


# ---- evidence ids ------------------------------------------------------------------------------


def test_unknown_evidence_id_rejected():
    bundle, claim, _, _ = package(knight, Kind.NEWLY_HANGING_PIECE)
    rejects(bundle, replace(claim, evidence_ids=(*claim.evidence_ids, "ev_999")), "ev_999")


def test_evidence_from_another_group_rejected():
    bundle = evidence(knight())
    first, second = claims(bundle)
    mixed = replace(first, evidence_ids=(*first.evidence_ids, second.evidence_ids[0]))
    with pytest.raises(IncompatibleClaimEvidenceError, match="more than one group"):
        validate(bundle, mixed, second)


def test_claim_from_another_base_rejected():
    bundle, claim, group, _ = package(knight, Kind.NEWLY_HANGING_PIECE)
    other = "pos_elsewhere"
    moved = replace(
        claim,
        base_position_id=other,
        subject=MoveClaimEntity(group.played_move.move, other),
    )
    rejects(bundle, moved, "another base")


def test_missing_counterfactual_reference_rejected():
    bundle, claim, _, _ = package(knight, Kind.NEWLY_HANGING_PIECE)
    rejects(bundle, replace(claim, evidence_ids=claim.evidence_ids[:-1]), "complete group")


def test_counterfactual_subset_rejected():
    bundle, claim, _, owned = package(knight, Kind.NEWLY_HANGING_PIECE)
    (counterfactual,) = of_type(owned, CounterfactualEvidence)
    tamper(counterfactual, probe_results=counterfactual.probe_results[:1])
    rejects(bundle, claim, "differs from required_probe_results")


def test_missing_optional_same_punishment_probe_rejected():
    bundle, claim, _, owned = package(defender, Kind.REMOVED_DEFENDER)
    (counterfactual,) = of_type(owned, CounterfactualEvidence)
    tamper(counterfactual, probe_results=counterfactual.probe_results[:2])
    rejects(bundle, claim, "differs from required_probe_results")


def test_reordered_probe_tuple_rejected():
    bundle, claim, group, owned = package(knight, Kind.NEWLY_HANGING_PIECE)
    (counterfactual,) = of_type(owned, CounterfactualEvidence)
    swapped = tuple(reversed(group.required_probe_results))
    tamper(group, required_probe_results=swapped)
    tamper(counterfactual, probe_results=swapped)
    rejects(bundle, claim, "execution-free REFUTATION")


def test_extra_probe_rejected():
    bundle, claim, group, owned = package(defender, Kind.REMOVED_DEFENDER)
    (counterfactual,) = of_type(owned, CounterfactualEvidence)
    extended = (*group.required_probe_results, group.required_probe_results[0])
    tamper(group, required_probe_results=extended)
    tamper(counterfactual, probe_results=extended)
    rejects(bundle, claim, "two or three")


def test_different_counterfactual_comparator_rejected():
    bundle, claim, _, owned = package(knight, Kind.NEWLY_HANGING_PIECE)
    (counterfactual,) = of_type(owned, CounterfactualEvidence)
    tamper(
        counterfactual, comparator_move=MoveClaimEntity(ChessMove("e1d1"), claim.base_position_id)
    )
    rejects(bundle, claim, "comparator differs")


def test_missing_engine_evidence_rejected():
    bundle, claim, group, owned = package(knight, Kind.NEWLY_HANGING_PIECE)
    engine = of_type(owned, EngineEvidence)[0]
    kept = tuple(eid for eid in group.evidence_ids if eid != engine.evidence_id)
    tamper(group, evidence_ids=kept)
    rejects(bundle, replace(claim, evidence_ids=kept), "exactly one EngineEvidence")


def test_duplicate_mismatched_engine_evidence_rejected():
    bundle, claim, _, owned = package(knight, Kind.NEWLY_HANGING_PIECE)
    first, second = of_type(owned, EngineEvidence)
    tamper(second, probe_result=first.probe_result)
    rejects(bundle, claim, "at most one EngineEvidence")


def test_engine_evidence_for_terminal_result_rejected():
    bundle, claim, group, owned = package(knight, Kind.NEWLY_HANGING_PIECE)
    (counterfactual,) = of_type(owned, CounterfactualEvidence)
    actual, comparator = group.required_probe_results
    terminal = _terminal(comparator)
    tamper(group, required_probe_results=(actual, terminal))
    tamper(counterfactual, probe_results=(actual, terminal))
    rejects(bundle, claim, "only to non-terminal")


def test_wrong_evidence_order_rejected():
    bundle, claim, _, _ = package(knight, Kind.NEWLY_HANGING_PIECE)
    rejects(
        bundle, replace(claim, evidence_ids=tuple(reversed(claim.evidence_ids))), "complete group"
    )
    bundle, claim, _, _ = package(exact_mate, Kind.MATE_ALLOWED)
    rejects(bundle, replace(claim, evidence_ids=tuple(reversed(claim.evidence_ids))), "board fact")


# ---- probe protocol revalidation ---------------------------------------------------------------


def _replace_probe(bundle, group, owned, index, **probe_changes):
    (counterfactual,) = of_type(owned, CounterfactualEvidence)
    results = list(group.required_probe_results)
    results[index] = replace(results[index], probe=replace(results[index].probe, **probe_changes))
    tamper(group, required_probe_results=tuple(results))
    tamper(counterfactual, probe_results=tuple(results))


@pytest.mark.parametrize(
    ("index", "changes", "match"),
    [
        (0, {"execution_move": ChessMove("d8d4")}, "actual probe"),
        (1, {"execution_move": ChessMove("d8d4")}, "comparator probe"),
        (0, {"kind": ProbeKind.BEST_RESPONSE}, "actual probe"),
        (1, {"intervention_move": ChessMove("e1d1")}, "comparator probe"),
        (2, {"kind": ProbeKind.REFUTATION}, "third probe"),
        (2, {"intervention_move": ChessMove("e1d1")}, "intervene with the comparator"),
        (2, {"execution_move": ChessMove("d8d7")}, "execute the punishment"),
    ],
)
def test_p8_probe_protocol_revalidated(index, changes, match):
    bundle, claim, group, owned = package(defender, Kind.REMOVED_DEFENDER)
    _replace_probe(bundle, group, owned, index, **changes)
    rejects(bundle, claim, match)


def test_same_punishment_probe_without_response_rejected():
    bundle, claim, group, _ = package(defender, Kind.REMOVED_DEFENDER)
    tamper(group, response=None)
    rejects(bundle, claim, "requires the punishment")


# ---- engine identity / settings ----------------------------------------------------------------


def test_mixed_engine_identity_rejected():
    bundle, claim, group, _ = package(knight, Kind.NEWLY_HANGING_PIECE)
    tamper(group.required_probe_results[1].engine_analysis, engine=EngineIdentity("Other", "9"))
    rejects(bundle, claim, "engine identities")


def test_mixed_engine_settings_rejected():
    bundle, claim, group, _ = package(knight, Kind.NEWLY_HANGING_PIECE)
    tamper(
        group.required_probe_results[1].engine_analysis,
        settings=EngineSettings(EngineLimit(depth=99)),
    )
    rejects(bundle, claim, "engine settings")


def _terminal(result: ProbeResult) -> ProbeResult:
    return ProbeResult(
        probe=result.probe,
        analysis_position=result.analysis_position,
        intervention_position=result.intervention_position,
        root_moves=None,
        engine_analysis=None,
        terminal=TerminalOutcome(TerminalKind.STALEMATE, None),
    )


def test_all_terminal_group_needs_no_synthetic_engine_identity():
    result = only_kind(knight(), Kind.NEWLY_HANGING_PIECE)
    (cause,) = result.causes
    terminal = tuple(_terminal(r) for r in cause.probe_results)
    bundle = evidence(replace(result, causes=(replace(cause, probe_results=terminal),)))
    assert not [r for r in bundle.evidence if type(r) is EngineEvidence]
    (claim,) = claims(bundle)
    assert claim.confidence is _C.ENGINE_VERIFIED
    assert validate(bundle, claim) == (claim,)


# ---- exact mate --------------------------------------------------------------------------------


def _actual_variation(group, owned):
    actual = group.required_probe_results[0].probe
    (variation,) = [r for r in of_type(owned, VariationEvidence) if r.probe == actual]
    return variation


def test_exact_mate_needs_exact_level():
    bundle, claim, group, _ = package(exact_mate, Kind.MATE_ALLOWED)
    tamper(group, mate_evidence_level=MateEvidenceLevel.ENGINE_LINE)
    rejects(bundle, claim, "confidence")


def test_exact_mate_needs_group_replay_flag():
    bundle, claim, group, _ = package(exact_mate, Kind.MATE_ALLOWED)
    tamper(group, replayed_pv_ends_in_checkmate=False)
    rejects(bundle, claim, "replayed line ending in checkmate")


def test_exact_mate_needs_actual_variation_flag():
    bundle, claim, group, owned = package(exact_mate, Kind.MATE_ALLOWED)
    tamper(_actual_variation(group, owned), replayed_pv_ends_in_checkmate=False)
    rejects(bundle, claim, "exact replayed checkmate variation")


def test_exact_mate_needs_actual_variation_deltas():
    bundle, claim, group, owned = package(exact_mate, Kind.MATE_ALLOWED)
    tamper(_actual_variation(group, owned), board_deltas=())
    rejects(bundle, claim, "exact replayed checkmate variation")


def test_exact_mate_needs_board_fact_deltas():
    bundle, claim, _, owned = package(exact_mate, Kind.MATE_ALLOWED)
    tamper(of_type(owned, BoardFactEvidence)[0], board_deltas=())
    rejects(bundle, claim, "board-fact deltas")


def test_exact_mate_claim_references_no_engine_or_counterfactual():
    bundle, claim, _, owned = package(exact_mate, Kind.MATE_ALLOWED)
    by_id = {r.evidence_id: r for r in owned}
    assert not {type(by_id[eid]) for eid in claim.evidence_ids} & {
        EngineEvidence,
        CounterfactualEvidence,
    }
    with_engine = replace(claim, evidence_ids=tuple(r.evidence_id for r in owned))
    rejects(bundle, with_engine, "board fact, motif and actual variation")


# ---- mate metadata -----------------------------------------------------------------------------


def test_mate_allowed_without_level_rejected():
    bundle, claim, group, _ = package(engine_mate, Kind.MATE_ALLOWED)
    tamper(group, mate_evidence_level=None, replayed_pv_ends_in_checkmate=None)
    rejects(bundle, claim, "mate_evidence_level")


@pytest.mark.parametrize(
    "changes",
    [
        {"mate_evidence_level": MateEvidenceLevel.ENGINE_LINE},
        {"replayed_pv_ends_in_checkmate": True},
    ],
)
def test_non_mate_group_with_mate_metadata_rejected(changes):
    bundle, claim, group, _ = package(knight, Kind.MATERIAL_LOSS_LINE)
    tamper(group, **changes)
    rejects(bundle, claim, "mate metadata")


# ---- material / replay provenance -------------------------------------------------------------


@pytest.mark.parametrize(
    ("make", "kind"),
    [
        (knight, Kind.NEWLY_HANGING_PIECE),
        (defender, Kind.REMOVED_DEFENDER),
        (knight, Kind.MATERIAL_LOSS_LINE),
    ],
)
def test_material_backed_claims_need_material_replay(make, kind):
    bundle, claim, _, owned = package(make, kind)
    for variation in of_type(owned, VariationEvidence):
        tamper(variation, material_evidence=())
    rejects(bundle, claim, "material replay provenance")


def test_fork_may_rely_on_non_material_replay():
    bundle, claim, _, owned = package(fork, Kind.FORK_ALLOWED)
    for variation in of_type(owned, VariationEvidence):
        tamper(variation, material_evidence=())
    assert validate(bundle, claim) == (claim,)


def test_engine_verified_needs_some_variation():
    bundle, claim, group, owned = package(fork, Kind.FORK_ALLOWED)
    kept = tuple(r.evidence_id for r in owned if type(r) is not VariationEvidence)
    tamper(group, evidence_ids=kept)
    rejects(bundle, replace(claim, evidence_ids=kept), "replay provenance")


# ---- family / input ----------------------------------------------------------------------------


def test_validator_rejects_good_move_family_bundle():
    bundle, claim, group, _ = package(knight, Kind.NEWLY_HANGING_PIECE)
    p9 = replace(
        group,
        source_family=EvidenceSourceFamily.GOOD_MOVE_BENEFIT,
        source_kind=GoodMoveBenefitKind.MATERIAL_THREAT,
    )
    foreign = EvidenceBundle(bundle.base_position_id, bundle.evidence, (p9,))
    rejects(foreign, claim, "BAD_MOVE_CAUSE")


# ---- complete group provenance, independent of confidence ---------------------------------------


def _foreign_probe(probe):
    return replace(probe, intervention_move=ChessMove("e1d1"))


@pytest.mark.parametrize("make", [knight, exact_mate])
@pytest.mark.parametrize("index", [0, 1])
def test_foreign_same_base_variation_probe_rejected(make, index):
    kind = Kind.MATE_ALLOWED if make is exact_mate else Kind.NEWLY_HANGING_PIECE
    bundle, claim, group, owned = package(make, kind)
    if make is exact_mate and index == 1:
        comparator = VariationEvidence(
            "ev_999", bundle.base_position_id, group.required_probe_results[1].probe
        )
        # Frozen §23.2 order: the extra variation precedes the final CounterfactualEvidence.
        tamper(bundle, evidence=(*bundle.evidence, comparator))
        ids = group.evidence_ids
        tamper(group, evidence_ids=(*ids[:-1], comparator.evidence_id, ids[-1]))
        owned.insert(len(owned) - 1, comparator)
        assert validate(bundle, claim) == (claim,)
    variation = of_type(owned, VariationEvidence)[index]
    tamper(variation, probe=_foreign_probe(variation.probe))
    rejects(bundle, claim, "exactly one required probe")


def test_variation_changed_to_required_probe_with_original_material_rejected():
    bundle, claim, group, owned = package(knight, Kind.NEWLY_HANGING_PIECE)
    variation = _actual_variation(group, owned)
    assert variation.material_evidence
    tamper(variation, probe=group.required_probe_results[1].probe)
    rejects(bundle, claim, "material probe")


@pytest.mark.parametrize("foreign", [False, True])
@pytest.mark.parametrize("make", [knight, exact_mate])
def test_material_probe_must_match_its_variation(make, foreign):
    kind = Kind.MATE_ALLOWED if make is exact_mate else Kind.NEWLY_HANGING_PIECE
    bundle, claim, group, owned = package(make, kind)
    if make is exact_mate:
        _, _, _, material_owned = package(knight, Kind.NEWLY_HANGING_PIECE)
        material = next(
            v.material_evidence[0]
            for v in of_type(material_owned, VariationEvidence)
            if v.material_evidence
        )
        actual = _actual_variation(group, owned)
        tamper(actual, material_evidence=(replace(material, probe=actual.probe),))
        assert validate(bundle, claim) == (claim,)
    variation = next(v for v in of_type(owned, VariationEvidence) if v.material_evidence)
    other = next(r.probe for r in group.required_probe_results if r.probe != variation.probe)
    tamper(
        variation.material_evidence[0], probe=_foreign_probe(variation.probe) if foreign else other
    )
    rejects(bundle, claim, "material probe")


@pytest.mark.parametrize("make", [knight, exact_mate])
def test_duplicate_variation_for_required_probe_rejected(make):
    kind = Kind.MATE_ALLOWED if make is exact_mate else Kind.NEWLY_HANGING_PIECE
    bundle, claim, group, owned = package(make, kind)
    variation = of_type(owned, VariationEvidence)[0]
    duplicate = replace(variation, evidence_id="ev_999")
    tamper(bundle, evidence=(*bundle.evidence, duplicate))
    tamper(group, evidence_ids=(*group.evidence_ids, duplicate.evidence_id))
    if claim.confidence is _C.ENGINE_VERIFIED:
        claim = replace(claim, evidence_ids=group.evidence_ids)
    rejects(bundle, claim, "at most one VariationEvidence")


@pytest.mark.parametrize("foreign", [False, True])
def test_unreferenced_invalid_engine_inserted_into_exact_group_rejected(foreign):
    bundle, claim, group, owned = package(exact_mate, Kind.MATE_ALLOWED)
    engine = of_type(owned, EngineEvidence)[0]
    result = engine.probe_result
    if foreign:
        result = replace(result, probe=_foreign_probe(result.probe))
    inserted = replace(engine, evidence_id="ev_999", probe_result=result)
    tamper(bundle, evidence=(*bundle.evidence, inserted))
    tamper(group, evidence_ids=(*group.evidence_ids, inserted.evidence_id))
    rejects(
        bundle, claim, "non-terminal required results" if foreign else "at most one EngineEvidence"
    )


def test_exact_group_with_valid_unreferenced_provenance_passes():
    bundle, claim, _, owned = package(exact_mate, Kind.MATE_ALLOWED)
    unreferenced = [r for r in owned if isinstance(r, (EngineEvidence, CounterfactualEvidence))]
    assert any(isinstance(r, EngineEvidence) for r in unreferenced)
    assert any(isinstance(r, CounterfactualEvidence) for r in unreferenced)
    assert all(r.evidence_id not in claim.evidence_ids for r in unreferenced)
    assert validate(bundle, claim) == (claim,)


# ---- full package bijection and canonical tuple -------------------------------------------------


def test_nonempty_bundle_without_claims_rejected():
    bundle, _, _, _ = package(knight, Kind.NEWLY_HANGING_PIECE)
    with pytest.raises(IncompatibleClaimEvidenceError, match="one claim per evidence group"):
        validate(bundle)


def test_two_group_package_with_omitted_claim_rejected():
    bundle = evidence(knight())
    first, _ = claims(bundle)
    rejects(bundle, first, "one claim per evidence group")


def test_distinct_claim_ids_for_same_group_rejected():
    bundle = evidence(knight())
    first, _ = claims(bundle)
    with pytest.raises(IncompatibleClaimEvidenceError, match="one claim per evidence group"):
        validate(bundle, first, replace(first, claim_id="cl_002"))


@pytest.mark.parametrize("renumber", [False, True])
def test_reversed_claim_tuple_rejected(renumber):
    bundle = evidence(knight())
    first, second = claims(bundle)
    reversed_claims = (second, first)
    if renumber:
        reversed_claims = (replace(second, claim_id="cl_001"), replace(first, claim_id="cl_002"))
    with pytest.raises(
        IncompatibleClaimEvidenceError, match="canonical predicate and object order"
    ):
        validate(bundle, *reversed_claims)


def test_canonical_two_group_package_passes():
    bundle = evidence(knight())
    built = claims(bundle)
    assert tuple(c.claim_id for c in built) == ("cl_001", "cl_002")
    assert validate(bundle, *built) == built


@pytest.mark.parametrize("ids", [("cl_002", "cl_001"), ("cl_001", "cl_003"), ("cl_010", "cl_011")])
def test_noncanonical_claim_ids_rejected(ids):
    bundle = evidence(knight())
    changed = tuple(replace(c, claim_id=eid) for c, eid in zip(claims(bundle), ids, strict=True))
    with pytest.raises(IncompatibleClaimEvidenceError, match="canonical tuple positions"):
        validate(bundle, *changed)


def test_empty_bundle_without_claims_passes():
    assert validate(EvidenceBundle("pos_base", (), ())) == ()
