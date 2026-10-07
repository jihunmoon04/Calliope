import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

import calliope.domain.explanation as explanation_package
from calliope.domain.analysis import (
    BadMoveCauseKind,
    BasePieceRef,
    BoardDelta,
    CounterfactualProbe,
    GoodMoveBenefitKind,
    MateEvidenceLevel,
    MaterialLineEvidence,
    ProbeKind,
    ProbeResult,
    RepresentativeAlternative,
    TacticalCandidate,
    TacticalCandidateKind,
    TacticalCandidateStatus,
    TerminalKind,
    TerminalOutcome,
)
from calliope.domain.chess import ChessMove, Color, PieceRef, PieceType, PositionSnapshot
from calliope.domain.engine import (
    EngineAnalysis,
    EngineIdentity,
    EngineLimit,
    EngineLine,
    EngineScore,
    EngineSettings,
)
from calliope.domain.explanation import (
    EVIDENCE_RECORD_TYPE_ORDER,
    BoardFactEvidence,
    CounterfactualEvidence,
    EngineEvidence,
    EvidenceBundle,
    EvidenceForm,
    EvidenceGroup,
    EvidenceSourceFamily,
    MotifEvidence,
    MoveClaimEntity,
    PieceClaimEntity,
    VariationEvidence,
    base_frame_piece_entity,
    evidence_record_type_rank,
)
from calliope.errors import ExplanationEvidenceError


def snapshot(fen: str, ply: int, side: Color) -> PositionSnapshot:
    return PositionSnapshot.create(
        fen=fen,
        ply=ply,
        side_to_move=side,
        castling_rights="-",
        en_passant_square=None,
        halfmove_clock=0,
        fullmove_number=1,
    )


BASE = snapshot("8/8/8/8/8/8/8/K6k w - - 0 1", 0, Color.WHITE)
AFTER = snapshot("8/8/8/8/8/8/K7/7k b - - 1 1", 1, Color.BLACK)
OTHER = snapshot("8/8/8/8/8/8/8/K5k1 w - - 0 1", 0, Color.WHITE)
BASE_ID = BASE.position_id

PLAYED_MOVE = ChessMove("a1a2")
PLAYED = MoveClaimEntity(PLAYED_MOVE, BASE_ID)
RESPONSE = MoveClaimEntity(ChessMove("h1g1"), AFTER.position_id)
COMPARATOR = MoveClaimEntity(ChessMove("a1b1"), BASE_ID)
KING = BasePieceRef(Color.WHITE, PieceType.KING, "a1")
BLACK_KING = BasePieceRef(Color.BLACK, PieceType.KING, "h1")
KING_ENTITY = base_frame_piece_entity(BASE_ID, KING)

A1 = RepresentativeAlternative(1, ChessMove("a1b1"))
A2 = RepresentativeAlternative(3, ChessMove("a1b2"))

ENGINE = EngineIdentity("Fixture", "1")
SETTINGS = EngineSettings(EngineLimit(depth=4))


def probe(kind=ProbeKind.REFUTATION, base=BASE, move=PLAYED_MOVE) -> CounterfactualProbe:
    return CounterfactualProbe(kind, base, move)


def engine_result(base=BASE, uci="h1g1") -> ProbeResult:
    line = EngineLine(1, ChessMove(uci), EngineScore.cp(0), (ChessMove(uci),))
    return ProbeResult(
        probe=probe(base=base),
        analysis_position=AFTER,
        intervention_position=AFTER,
        root_moves=None,
        engine_analysis=EngineAnalysis(AFTER.position_id, ENGINE, SETTINGS, (line,)),
        terminal=None,
    )


def terminal_result() -> ProbeResult:
    return ProbeResult(
        probe=probe(move=ChessMove("a1b2")),
        analysis_position=AFTER,
        intervention_position=AFTER,
        root_moves=None,
        engine_analysis=None,
        terminal=TerminalOutcome(TerminalKind.CHECKMATE, Color.WHITE),
    )


DELTA = BoardDelta(
    before_position_id=BASE_ID,
    after_position_id=AFTER.position_id,
    move=PLAYED_MOVE,
    mover=Color.WHITE,
    piece_correspondence=(),
    transitions=(),
    capture=None,
    material_changes=(),
    new_attacks=(),
    removed_attacks=(),
    new_defenses=(),
    removed_defenses=(),
    check_changes=(),
)
FORCED = TacticalCandidate(
    TacticalCandidateKind.FORCED_RESPONSE,
    TacticalCandidateStatus.VERIFIED,
    actors=(PieceRef(Color.WHITE, PieceType.KING, "a2"),),
    responses=(RESPONSE.move,),
)


def board(evidence_id="ev_001", **changes) -> BoardFactEvidence:
    values = {"moves": (PLAYED, RESPONSE), "pieces": (KING_ENTITY,), "board_deltas": (DELTA,)}
    values.update(changes)
    return BoardFactEvidence(evidence_id, BASE_ID, **values)


def motif(evidence_id="ev_002", **changes) -> MotifEvidence:
    values = {"candidates": (FORCED,), "pieces": (KING_ENTITY,), "moves": (RESPONSE,)}
    values.update(changes)
    return MotifEvidence(evidence_id, BASE_ID, **values)


def engine(evidence_id="ev_003", result=None) -> EngineEvidence:
    return EngineEvidence(evidence_id, BASE_ID, result or engine_result())


def variation(evidence_id="ev_004", **changes) -> VariationEvidence:
    values = {"probe": probe()}
    values.update(changes)
    return VariationEvidence(evidence_id, BASE_ID, **values)


PROBES = (engine_result(), terminal_result())


def counterfactual(evidence_id="ev_005", **changes) -> CounterfactualEvidence:
    values = {
        "form": EvidenceForm.DIRECT,
        "probe_results": PROBES,
        "representative_alternatives": (A1, A2),
        "failed_alternatives": (A1,),
    }
    values.update(changes)
    return CounterfactualEvidence(evidence_id, BASE_ID, **values)


def group(evidence_ids=("ev_001", "ev_002", "ev_003", "ev_004", "ev_005"), **changes):
    values = {
        "source_family": EvidenceSourceFamily.GOOD_MOVE_BENEFIT,
        "source_kind": GoodMoveBenefitKind.FORCES_RESPONSE,
        "source_subject": (KING,),
        "played_move": PLAYED,
        "evidence_form": EvidenceForm.DIRECT,
        "evidence_ids": evidence_ids,
        "required_probe_results": PROBES,
        "response": RESPONSE,
        "representative_alternatives": (A1, A2),
        "failed_alternatives": (A1,),
    }
    values.update(changes)
    return EvidenceGroup(**values)


def records(offset=0):
    def eid(n):
        return f"ev_{n + offset:03d}"

    return (
        board(eid(1)),
        motif(eid(2)),
        engine(eid(3)),
        variation(eid(4)),
        counterfactual(eid(5)),
    )


def bundle(evidence=None, groups=None) -> EvidenceBundle:
    return EvidenceBundle(
        BASE_ID,
        records() if evidence is None else evidence,
        (group(),) if groups is None else groups,
    )


# -- common record header --


FACTORIES = [board, motif, engine, variation, counterfactual]


@pytest.mark.parametrize("factory", FACTORIES)
def test_record_requires_canonical_evidence_id(factory):
    for bad in ("", "ev_0", "cl_001", "ev_0001"):
        with pytest.raises(ExplanationEvidenceError, match="evidence_id"):
            factory(bad)


@pytest.mark.parametrize("factory", FACTORIES)
def test_record_requires_base_position(factory):
    with pytest.raises(ExplanationEvidenceError, match="base_position_id"):
        replace(factory(), base_position_id="")


@pytest.mark.parametrize("factory", FACTORIES)
def test_records_are_frozen_and_slotted(factory):
    record = factory()
    assert not hasattr(record, "__dict__")
    with pytest.raises(FrozenInstanceError):
        record.evidence_id = "ev_009"


def test_variant_order_is_pinned():
    assert EVIDENCE_RECORD_TYPE_ORDER == (
        BoardFactEvidence,
        MotifEvidence,
        EngineEvidence,
        VariationEvidence,
        CounterfactualEvidence,
    )
    shuffled = [counterfactual(), engine(), board(), variation(), motif()]
    ranked = sorted(shuffled, key=evidence_record_type_rank)
    assert [type(record) for record in ranked] == list(EVIDENCE_RECORD_TYPE_ORDER)
    with pytest.raises(ExplanationEvidenceError, match="unsupported evidence record"):
        evidence_record_type_rank(PLAYED)


# -- BoardFactEvidence --


def test_board_fact_retains_exact_facts():
    terminal = TerminalOutcome(TerminalKind.CHECKMATE, Color.WHITE)
    record = board(terminal=terminal, sole_response=RESPONSE)
    assert record.sole_response == RESPONSE
    assert record.terminal == terminal
    assert record.board_deltas == (DELTA,)


def test_board_fact_sole_response_must_be_retained_move():
    with pytest.raises(ExplanationEvidenceError, match="sole_response"):
        board(moves=(PLAYED,), sole_response=RESPONSE)


def test_sole_response_membership_ignores_san_presentation():
    with_san = MoveClaimEntity(ChessMove("h1g1", "Kg1"), AFTER.position_id)
    record = board(moves=(PLAYED, with_san), sole_response=RESPONSE)
    assert record.sole_response == RESPONSE
    assert record.moves[1].move.san == "Kg1"


def test_sole_response_same_uci_other_position_rejected():
    elsewhere = MoveClaimEntity(RESPONSE.move, BASE_ID)
    with pytest.raises(ExplanationEvidenceError, match="must also appear in moves"):
        board(moves=(PLAYED, elsewhere), sole_response=RESPONSE)


def test_sole_response_different_uci_rejected():
    other = MoveClaimEntity(ChessMove("h1h2"), AFTER.position_id)
    with pytest.raises(ExplanationEvidenceError, match="must also appear in moves"):
        board(sole_response=other)


@pytest.mark.parametrize("response", [ChessMove("h1g1"), "h1g1", ("h1g1", "pos")])
def test_sole_response_must_be_move_entity(response):
    with pytest.raises(ExplanationEvidenceError, match="sole_response must be a MoveClaimEntity"):
        board(sole_response=response)


@pytest.mark.parametrize("factory", [board, motif, variation])
def test_duplicate_moves_and_pieces_rejected(factory):
    with pytest.raises(ExplanationEvidenceError, match="duplicate move"):
        factory(moves=(RESPONSE, MoveClaimEntity(ChessMove("h1g1", "Kg1"), AFTER.position_id)))
    moved = PieceClaimEntity(KING, AFTER.position_id, "a2", PieceType.KING)
    with pytest.raises(ExplanationEvidenceError, match="duplicate piece"):
        factory(pieces=(KING_ENTITY, moved))


@pytest.mark.parametrize("factory", [board, motif, variation])
def test_entity_tuples_must_be_typed(factory):
    with pytest.raises(ExplanationEvidenceError, match="MoveClaimEntity"):
        factory(moves=(PLAYED_MOVE,))
    with pytest.raises(ExplanationEvidenceError, match="PieceClaimEntity"):
        factory(pieces=(KING,))


@pytest.mark.parametrize("factory", [board, variation])
def test_board_deltas_must_be_domain_values(factory):
    with pytest.raises(ExplanationEvidenceError, match="BoardDelta"):
        factory(board_deltas=({"move": "a1a2"},))


# -- EngineEvidence --


def test_engine_evidence_accepts_non_terminal_result():
    record = engine()
    assert record.probe_result.engine_analysis.engine == ENGINE
    assert not hasattr(record, "engine") and not hasattr(record, "settings")


def test_engine_evidence_refuses_terminal_result():
    with pytest.raises(ExplanationEvidenceError, match="non-terminal"):
        engine(result=terminal_result())


def test_engine_evidence_requires_probe_base_equal_to_evidence_base():
    with pytest.raises(ExplanationEvidenceError, match="another base"):
        engine(result=engine_result(base=OTHER))


# -- VariationEvidence --


def test_variation_retains_replay_provenance_without_replaying():
    illegal = MoveClaimEntity(ChessMove("h8h1"), AFTER.position_id)  # not legal anywhere here
    material = MaterialLineEvidence(probe(), material_delta=-300, stable_at_ply=2)
    record = variation(
        moves=(illegal,),
        material_evidence=(material,),
        terminal=TerminalOutcome(TerminalKind.CHECKMATE, Color.BLACK),
        replayed_pv_ends_in_checkmate=True,
    )
    assert record.moves == (illegal,)
    assert record.material_evidence == (material,)


def test_variation_probes_must_share_evidence_base():
    with pytest.raises(ExplanationEvidenceError, match="another base"):
        variation(probe=probe(base=OTHER))
    foreign = MaterialLineEvidence(probe(base=OTHER), material_delta=0, stable_at_ply=None)
    with pytest.raises(ExplanationEvidenceError, match="another base"):
        variation(material_evidence=(foreign,))


# -- CounterfactualEvidence --


def test_counterfactual_accepts_terminal_results_and_retains_order():
    reversed_probes = (terminal_result(), engine_result())
    record = counterfactual(probe_results=reversed_probes)
    assert record.probe_results == reversed_probes
    assert record.probe_results[0].engine_analysis is None


def test_counterfactual_requires_probe_results_on_its_base():
    with pytest.raises(ExplanationEvidenceError, match="requires probe_results"):
        counterfactual(probe_results=())
    with pytest.raises(ExplanationEvidenceError, match="another base"):
        counterfactual(probe_results=(engine_result(base=OTHER),))


def test_counterfactual_does_not_enforce_form_semantics_in_i0():
    ignore = replace(engine_result(), probe=probe(kind=ProbeKind.IGNORE_THREAT))
    for form in EvidenceForm:
        counterfactual(form=form, probe_results=(ignore,), tested_response=RESPONSE)


@pytest.mark.parametrize("factory", [counterfactual, group])
def test_failed_alternatives_must_be_rank_uci_subset(factory):
    with pytest.raises(ExplanationEvidenceError, match="subset"):
        factory(failed_alternatives=(RepresentativeAlternative(2, ChessMove("a1b1")),))
    with pytest.raises(ExplanationEvidenceError, match="subset"):
        factory(failed_alternatives=(RepresentativeAlternative(1, ChessMove("a1b2")),))


@pytest.mark.parametrize("factory", [counterfactual, group])
def test_alternatives_preserve_rank_order(factory):
    with pytest.raises(ExplanationEvidenceError, match="ascending rank"):
        factory(representative_alternatives=(A2, A1))
    with pytest.raises(ExplanationEvidenceError, match="ascending rank"):
        factory(failed_alternatives=(A2, A1))
    assert factory(failed_alternatives=(A1, A2)).failed_alternatives == (A1, A2)


# -- MotifEvidence --


def test_motif_requires_typed_candidates():
    with pytest.raises(ExplanationEvidenceError, match="requires candidates"):
        motif(candidates=())
    with pytest.raises(ExplanationEvidenceError, match="TacticalCandidate"):
        motif(candidates=("fork",))


# -- EvidenceGroup --


def test_group_retains_descriptor_and_probe_order():
    reversed_probes = tuple(reversed(PROBES))
    value = group(
        evidence_ids=("ev_005", "ev_001"),
        required_probe_results=reversed_probes,
        mate_evidence_level=MateEvidenceLevel.EXACT_IMMEDIATE,
        replayed_pv_ends_in_checkmate=True,
    )
    assert value.evidence_ids == ("ev_005", "ev_001")
    assert value.required_probe_results == reversed_probes


@pytest.mark.parametrize(
    ("family", "kind"),
    [
        (EvidenceSourceFamily.BAD_MOVE_CAUSE, GoodMoveBenefitKind.MATE_THREAT),
        (EvidenceSourceFamily.GOOD_MOVE_BENEFIT, BadMoveCauseKind.MATE_ALLOWED),
        (EvidenceSourceFamily.BAD_MOVE_CAUSE, "mate_allowed"),
    ],
)
def test_family_kind_mismatch_rejected(family, kind):
    with pytest.raises(ExplanationEvidenceError, match="source_kind"):
        group(source_family=family, source_kind=kind)


def test_family_must_be_typed():
    with pytest.raises(ExplanationEvidenceError, match="source_family"):
        group(source_family="good_move_benefit")


def test_bad_move_family_accepts_cause_kind():
    value = group(
        source_family=EvidenceSourceFamily.BAD_MOVE_CAUSE,
        source_kind=BadMoveCauseKind.NEWLY_HANGING_PIECE,
        comparator_move=COMPARATOR,
        response=None,
    )
    assert value.comparator_move == COMPARATOR


@pytest.mark.parametrize(
    ("subject", "message"),
    [
        ((), "must not be empty"),
        ((KING, KING), "unique"),
        ((BLACK_KING, KING), "canonical base-piece order"),
    ],
)
def test_source_subject_invariants(subject, message):
    with pytest.raises(ExplanationEvidenceError, match=message):
        group(source_subject=subject)


def test_sorted_multi_piece_subject_accepted():
    assert group(source_subject=(KING, BLACK_KING)).source_subject == (KING, BLACK_KING)


@pytest.mark.parametrize("evidence_ids", [(), ("ev_001", "ev_001"), ("ev_01",)])
def test_group_evidence_ids_rejected(evidence_ids):
    with pytest.raises(ExplanationEvidenceError, match="evidence_ids"):
        group(evidence_ids=evidence_ids)


def test_mate_replay_flag_requires_level():
    with pytest.raises(ExplanationEvidenceError, match="mate_evidence_level"):
        group(replayed_pv_ends_in_checkmate=False)


def test_group_moves_must_be_entities():
    with pytest.raises(ExplanationEvidenceError, match="played_move"):
        group(played_move=PLAYED_MOVE)
    with pytest.raises(ExplanationEvidenceError, match="response"):
        group(response=RESPONSE.move)


# -- EvidenceBundle --


def test_valid_one_group_bundle_retains_caller_order():
    evidence = tuple(reversed(records()))
    value = bundle(evidence=evidence)
    assert value.evidence == evidence
    assert value.groups == (group(),)


def test_valid_multi_group_same_family_bundle():
    second = group(
        evidence_ids=tuple(f"ev_{n:03d}" for n in range(6, 11)),
        source_kind=GoodMoveBenefitKind.MATE_THREAT,
        mate_evidence_level=MateEvidenceLevel.ENGINE_LINE,
    )
    value = bundle(evidence=records() + records(offset=5), groups=(group(), second))
    assert len(value.groups) == 2


def test_empty_bundle_is_valid():
    assert EvidenceBundle(BASE_ID, (), ()).groups == ()


def test_bundle_requires_base():
    with pytest.raises(ExplanationEvidenceError, match="base_position_id"):
        EvidenceBundle("", (), ())


def test_duplicate_global_evidence_id_rejected():
    with pytest.raises(ExplanationEvidenceError, match="duplicate evidence id ev_001"):
        bundle(evidence=records() + (board("ev_001"),))


def test_unknown_group_evidence_id_rejected():
    with pytest.raises(ExplanationEvidenceError, match="unknown evidence id ev_006"):
        bundle(groups=(group(evidence_ids=group().evidence_ids + ("ev_006",)),))


def test_unowned_evidence_rejected():
    with pytest.raises(ExplanationEvidenceError, match="ev_006 is not owned"):
        bundle(evidence=records() + (board("ev_006"),))


def test_evidence_shared_across_groups_rejected():
    second = group(
        evidence_ids=("ev_001",),
        source_kind=GoodMoveBenefitKind.MATE_THREAT,
    )
    with pytest.raises(ExplanationEvidenceError, match="ev_001 is owned by more than one"):
        bundle(groups=(group(), second))


def test_cross_base_evidence_rejected():
    foreign = BoardFactEvidence("ev_006", OTHER.position_id)
    with pytest.raises(ExplanationEvidenceError, match="ev_006 belongs to another base"):
        bundle(evidence=records() + (foreign,))


def test_cross_family_groups_rejected():
    p8 = group(
        evidence_ids=tuple(f"ev_{n:03d}" for n in range(6, 11)),
        source_family=EvidenceSourceFamily.BAD_MOVE_CAUSE,
        source_kind=BadMoveCauseKind.MATE_ALLOWED,
    )
    with pytest.raises(ExplanationEvidenceError, match="one source family"):
        bundle(evidence=records() + records(offset=5), groups=(group(), p8))


def test_group_played_move_must_be_from_bundle_base():
    moved = group(played_move=MoveClaimEntity(PLAYED_MOVE, AFTER.position_id))
    with pytest.raises(ExplanationEvidenceError, match="legal from the bundle base"):
        bundle(groups=(moved,))


def test_group_counterfactual_must_equal_required_probe_results():
    subset = group(required_probe_results=PROBES[:1])
    with pytest.raises(ExplanationEvidenceError, match="required_probe_results"):
        bundle(groups=(subset,))
    reordered = group(required_probe_results=tuple(reversed(PROBES)))
    with pytest.raises(ExplanationEvidenceError, match="required_probe_results"):
        bundle(groups=(reordered,))


def test_group_requires_required_probe_results():
    with pytest.raises(ExplanationEvidenceError, match="required_probe_results must not be empty"):
        group(required_probe_results=())


def test_group_must_own_a_counterfactual():
    without = records()[:4]
    owner = group(evidence_ids=("ev_001", "ev_002", "ev_003", "ev_004"))
    with pytest.raises(ExplanationEvidenceError, match="exactly one CounterfactualEvidence, not 0"):
        bundle(evidence=without, groups=(owner,))


def test_group_owns_at_most_one_counterfactual():
    evidence = records() + (counterfactual("ev_006"),)
    owner = group(evidence_ids=group().evidence_ids + ("ev_006",))
    with pytest.raises(ExplanationEvidenceError, match="exactly one CounterfactualEvidence, not 2"):
        bundle(evidence=evidence, groups=(owner,))


def test_every_group_in_multi_group_bundle_needs_its_own_counterfactual():
    second = group(
        evidence_ids=("ev_006",),
        source_kind=GoodMoveBenefitKind.MATE_THREAT,
    )
    with pytest.raises(ExplanationEvidenceError, match="not 0"):
        bundle(evidence=records() + (board("ev_006"),), groups=(group(), second))


def test_bundle_rejects_untyped_members():
    with pytest.raises(ExplanationEvidenceError, match="evidence record"):
        bundle(evidence=records() + (PLAYED,))
    with pytest.raises(ExplanationEvidenceError, match="EvidenceGroup"):
        bundle(groups=({"evidence_ids": ()},))


# -- source guards --


DOMAIN_DIR = Path(explanation_package.__file__).parent
FORBIDDEN_IMPORT_ROOTS = (
    "calliope.services",
    "calliope.application",
    "calliope.adapters",
    "chess",
    "stockfish",
    "anthropic",
    "openai",
    "google",
    "httpx",
    "requests",
    "subprocess",
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"relative import in {path.name}"
            names.add(node.module or "")
    return names


@pytest.mark.parametrize("module", ["__init__.py", "claim.py", "evidence.py"])
def test_p10_domain_modules_import_only_domain_values(module):
    imported = _imported_modules(DOMAIN_DIR / module)
    for name in imported:
        for root in FORBIDDEN_IMPORT_ROOTS:
            assert name != root and not name.startswith(f"{root}."), (module, name)
    calliope_imports = {name for name in imported if name.startswith("calliope")}
    assert all(
        name == "calliope.errors" or name.startswith("calliope.domain.")
        for name in calliope_imports
    ), calliope_imports


def test_p10_domain_has_no_semantic_builders():
    assert {path.name for path in DOMAIN_DIR.glob("*.py")} == {
        "__init__.py",
        "claim.py",
        "evidence.py",
    }
    for name in ("EvidenceBuilder", "ClaimBuilder", "ClaimValidator"):
        assert not hasattr(explanation_package, name)
