from dataclasses import FrozenInstanceError, replace

import pytest

import calliope
from calliope.domain import explanation
from calliope.domain.analysis import BasePieceRef
from calliope.domain.chess import ChessMove, Color, PieceType, square_index
from calliope.domain.explanation import (
    ClaimConfidence,
    ClaimPredicate,
    ClaimScope,
    ExplanationClaim,
    MoveClaimEntity,
    PieceClaimEntity,
    SideClaimEntity,
    base_frame_piece_entity,
    base_piece_sort_key,
    claim_entity_sort_key,
    mint_claim_id,
    mint_evidence_id,
    required_claim_scope,
)
from calliope.errors import (
    CalliopeError,
    ExplanationClaimError,
    ExplanationEvidenceError,
    IncompatibleBadMoveContextError,
    IncompatibleClaimEvidenceError,
    IncompatibleGoodMoveContextError,
)

BASE_ID = "pos_base"
AFTER_ID = "pos_after"
PLAYED = MoveClaimEntity(ChessMove("e2e4"), BASE_ID)
KNIGHT = BasePieceRef(Color.WHITE, PieceType.KNIGHT, "g1")
PAWN = BasePieceRef(Color.WHITE, PieceType.PAWN, "e7")
BLACK_KING = BasePieceRef(Color.BLACK, PieceType.KING, "e8")

_P = ClaimPredicate
_S = ClaimScope
REPRESENTATIVE = (_P.AVOIDS_REPRESENTATIVE_MATE_FAILURE, _P.AVOIDS_REPRESENTATIVE_MATERIAL_LOSS)
TESTED = (_P.THREATENS_MATE_IF_IGNORED, _P.THREATENS_MATERIAL_IF_IGNORED)
LOCAL = tuple(p for p in _P if p not in REPRESENTATIVE + TESTED)


def claim(**changes) -> ExplanationClaim:
    values = {
        "claim_id": "cl_001",
        "base_position_id": BASE_ID,
        "subject": PLAYED,
        "predicate": _P.LEAVES_PIECE_HANGING,
        "objects": (base_frame_piece_entity(BASE_ID, KNIGHT),),
        "confidence": ClaimConfidence.ENGINE_VERIFIED,
        "scope": _S.LOCAL,
        "evidence_ids": ("ev_001", "ev_002"),
    }
    values.update(changes)
    return ExplanationClaim(**values)


# -- errors --


def test_error_hierarchy_is_p10_owned():
    assert issubclass(ExplanationEvidenceError, CalliopeError)
    assert issubclass(ExplanationClaimError, CalliopeError)
    assert issubclass(IncompatibleClaimEvidenceError, ExplanationClaimError)
    for p10 in (ExplanationEvidenceError, ExplanationClaimError, IncompatibleClaimEvidenceError):
        assert not issubclass(
            p10, (IncompatibleBadMoveContextError, IncompatibleGoodMoveContextError)
        )


# -- vocabulary --


@pytest.mark.parametrize(
    ("enum", "pairs"),
    [
        (
            ClaimConfidence,
            [("EXACT", "exact"), ("FORCED", "forced"), ("ENGINE_VERIFIED", "engine_verified")],
        ),
        (
            ClaimScope,
            [
                ("LOCAL", "local"),
                ("TESTED_RESPONSE", "tested_response"),
                ("REPRESENTATIVE_ALTERNATIVES", "representative_alternatives"),
            ],
        ),
    ],
)
def test_confidence_and_scope_vocabulary(enum, pairs):
    assert [(member.name, member.value) for member in enum] == pairs


def test_predicate_vocabulary_and_declaration_order():
    assert [(p.name, p.value) for p in ClaimPredicate] == [
        ("LEAVES_PIECE_HANGING", "leaves_piece_hanging"),
        ("REMOVES_DEFENDER", "removes_defender"),
        ("ALLOWS_FORK", "allows_fork"),
        ("ALLOWS_CHECKMATE", "allows_checkmate"),
        ("ALLOWS_MATERIAL_LOSS", "allows_material_loss"),
        ("FORCES_RESPONSE", "forces_response"),
        ("DELIVERS_CHECKMATE", "delivers_checkmate"),
        ("LEADS_TO_MATE", "leads_to_mate"),
        ("WINS_MATERIAL", "wins_material"),
        ("THREATENS_MATE_IF_IGNORED", "threatens_mate_if_ignored"),
        ("THREATENS_MATERIAL_IF_IGNORED", "threatens_material_if_ignored"),
        ("AVOIDS_REPRESENTATIVE_MATE_FAILURE", "avoids_representative_mate_failure"),
        ("AVOIDS_REPRESENTATIVE_MATERIAL_LOSS", "avoids_representative_material_loss"),
    ]


def test_no_heuristic_positional_or_literal_only_vocabulary():
    assert "HEURISTIC" not in ClaimConfidence.__members__
    forbidden = (
        "only",
        "unique",
        "exhaust",
        "heuristic",
        "positional",
        "initiative",
        "space",
        "intent",
        "plan",
        "king_safety",
        "forced_material",
    )
    for predicate in ClaimPredicate:
        assert not any(word in predicate.value for word in forbidden), predicate
    assert {scope.value for scope in ClaimScope}.isdisjoint(
        {"all_legal_moves", "exhaustive", "only_move_proven"}
    )


# -- entities --


def test_move_entity_requires_position_id():
    assert PLAYED.position_id == BASE_ID
    with pytest.raises(ExplanationClaimError, match="position_id"):
        MoveClaimEntity(ChessMove("e2e4"), "")


def test_base_frame_helper_is_exact():
    entity = base_frame_piece_entity(BASE_ID, KNIGHT)
    assert entity == PieceClaimEntity(KNIGHT, BASE_ID, "g1", PieceType.KNIGHT)


def test_moved_presentation_square_is_allowed_without_changing_identity():
    moved = PieceClaimEntity(KNIGHT, AFTER_ID, "f3", PieceType.KNIGHT)
    assert moved.base_ref == KNIGHT
    assert moved.base_ref.base_square == "g1"


@pytest.mark.parametrize(
    "role", [PieceType.PAWN, PieceType.KNIGHT, PieceType.BISHOP, PieceType.ROOK, PieceType.QUEEN]
)
def test_pawn_promotion_presentation_is_allowed(role):
    promoted = PieceClaimEntity(PAWN, AFTER_ID, "e8", role)
    assert promoted.base_ref.piece_type is PieceType.PAWN
    assert promoted.current_piece_type is role


@pytest.mark.parametrize(
    ("base", "role"),
    [
        (KNIGHT, PieceType.BISHOP),
        (KNIGHT, PieceType.PAWN),
        (BLACK_KING, PieceType.QUEEN),
        (BasePieceRef(Color.BLACK, PieceType.QUEEN, "d8"), PieceType.KING),
        (PAWN, PieceType.KING),
    ],
)
def test_incompatible_role_change_rejected(base, role):
    with pytest.raises(ExplanationClaimError, match="cannot be presented"):
        PieceClaimEntity(base, AFTER_ID, "e8", role)


@pytest.mark.parametrize("square", ["", "e9", "i1", "E4", "e44"])
def test_piece_entity_rejects_bad_square(square):
    with pytest.raises(ExplanationClaimError, match="invalid square"):
        PieceClaimEntity(KNIGHT, AFTER_ID, square, PieceType.KNIGHT)


def test_piece_entity_requires_frame_id():
    with pytest.raises(ExplanationClaimError, match="at_position_id"):
        PieceClaimEntity(KNIGHT, "", "g1", PieceType.KNIGHT)


@pytest.mark.parametrize(
    "value",
    [
        PLAYED,
        base_frame_piece_entity(BASE_ID, KNIGHT),
        SideClaimEntity(Color.BLACK),
    ],
)
def test_entities_are_frozen_and_slotted(value):
    assert not hasattr(value, "__dict__")
    with pytest.raises(FrozenInstanceError):
        value.__setattr__(next(iter(type(value).__slots__)), None)


# -- ordering --


@pytest.mark.parametrize(
    "ref",
    [
        BasePieceRef(Color.WHITE, PieceType.ROOK, "a1"),
        BasePieceRef(Color.BLACK, PieceType.ROOK, "h8"),
        BasePieceRef(Color.WHITE, PieceType.KING, "e1"),
        BasePieceRef(Color.BLACK, PieceType.PAWN, "d7"),
        KNIGHT,
    ],
)
def test_base_piece_sort_key_matches_piece_identity_semantics(ref):
    from calliope.services.explanation.piece_identity import _base_key

    expected = (square_index(ref.base_square), ref.color.value, ref.piece_type.value)
    assert base_piece_sort_key(ref) == expected == _base_key(ref)


def test_base_piece_sort_key_orders_by_square_then_color_then_type():
    refs = [
        BasePieceRef(Color.BLACK, PieceType.PAWN, "a7"),
        BasePieceRef(Color.WHITE, PieceType.QUEEN, "d1"),
        BasePieceRef(Color.WHITE, PieceType.ROOK, "a1"),
    ]
    assert sorted(refs, key=base_piece_sort_key) == [refs[2], refs[1], refs[0]]


def test_entity_keys_are_exact():
    assert claim_entity_sort_key(PLAYED) == ("move", BASE_ID, "e2e4")
    piece = PieceClaimEntity(PAWN, AFTER_ID, "e8", PieceType.QUEEN)
    assert claim_entity_sort_key(piece) == (
        "piece",
        (square_index("e7"), "white", "pawn"),
        AFTER_ID,
        "e8",
        "queen",
    )
    assert claim_entity_sort_key(SideClaimEntity(Color.WHITE)) == ("side", "white")


def test_move_key_ignores_san_presentation():
    with_san = MoveClaimEntity(ChessMove("e2e4", "e4"), BASE_ID)
    assert claim_entity_sort_key(with_san) == claim_entity_sort_key(PLAYED)


def _ordering_fixture(*, reverse=False):
    entities = [
        SideClaimEntity(Color.WHITE),
        PieceClaimEntity(KNIGHT, AFTER_ID, "f3", PieceType.KNIGHT),
        MoveClaimEntity(ChessMove("g8f6"), AFTER_ID),
        SideClaimEntity(Color.BLACK),
        base_frame_piece_entity(BASE_ID, KNIGHT),
        base_frame_piece_entity(BASE_ID, BLACK_KING),
        MoveClaimEntity(ChessMove("d2d4"), BASE_ID),
        PLAYED,
    ]
    if reverse:
        entities.reverse()
    return entities


def test_entity_ordering_is_move_piece_side_and_deterministic():
    forward = sorted(_ordering_fixture(), key=claim_entity_sort_key)
    backward = sorted(_ordering_fixture(reverse=True), key=claim_entity_sort_key)
    assert forward == backward
    assert [type(entity) for entity in forward] == (
        [MoveClaimEntity] * 3 + [PieceClaimEntity] * 3 + [SideClaimEntity] * 2
    )
    # position_id sorts first ("pos_after" < "pos_base"), then UCI.
    assert forward[:3] == [
        MoveClaimEntity(ChessMove("g8f6"), AFTER_ID),
        MoveClaimEntity(ChessMove("d2d4"), BASE_ID),
        PLAYED,
    ]
    # base key first, then frame id for the same physical piece.
    assert forward[3:6] == [
        PieceClaimEntity(KNIGHT, AFTER_ID, "f3", PieceType.KNIGHT),
        base_frame_piece_entity(BASE_ID, KNIGHT),
        base_frame_piece_entity(BASE_ID, BLACK_KING),
    ]
    assert forward[6:] == [SideClaimEntity(Color.BLACK), SideClaimEntity(Color.WHITE)]


def test_unknown_entity_type_has_no_sort_key():
    with pytest.raises(ExplanationClaimError, match="unsupported claim entity"):
        claim_entity_sort_key(KNIGHT)


# -- ids --


@pytest.mark.parametrize(
    ("index", "evidence", "claim_id"),
    [
        (1, "ev_001", "cl_001"),
        (2, "ev_002", "cl_002"),
        (999, "ev_999", "cl_999"),
        (1000, "ev_1000", "cl_1000"),
        (12345, "ev_12345", "cl_12345"),
    ],
)
def test_ordinal_ids(index, evidence, claim_id):
    assert mint_evidence_id(index) == evidence
    assert mint_claim_id(index) == claim_id
    assert mint_evidence_id(index) == mint_evidence_id(index)


@pytest.mark.parametrize("index", [0, -1, True, 1.0, "1"])
def test_ordinal_ids_reject_non_positive_or_non_int(index):
    with pytest.raises(ExplanationEvidenceError, match="at least 1"):
        mint_evidence_id(index)
    with pytest.raises(ExplanationClaimError, match="at least 1"):
        mint_claim_id(index)


# -- claim --


def test_valid_local_claim_retains_caller_order():
    objects = (base_frame_piece_entity(BASE_ID, KNIGHT), SideClaimEntity(Color.BLACK))
    value = claim(objects=objects, evidence_ids=("ev_003", "ev_001"))
    assert value.objects == objects
    assert value.evidence_ids == ("ev_003", "ev_001")
    assert value.importance is None
    with pytest.raises(FrozenInstanceError):
        value.claim_id = "cl_002"


@pytest.mark.parametrize("predicate", LOCAL)
def test_local_predicates_require_local_scope(predicate):
    assert required_claim_scope(predicate) is _S.LOCAL
    claim(predicate=predicate)
    for scope in (_S.TESTED_RESPONSE, _S.REPRESENTATIVE_ALTERNATIVES):
        with pytest.raises(ExplanationClaimError, match="requires local scope"):
            claim(predicate=predicate, scope=scope)


@pytest.mark.parametrize("predicate", REPRESENTATIVE)
def test_preservation_requires_representative_scope(predicate):
    claim(predicate=predicate, scope=_S.REPRESENTATIVE_ALTERNATIVES)
    for scope in (_S.LOCAL, _S.TESTED_RESPONSE):
        with pytest.raises(ExplanationClaimError, match="representative_alternatives scope"):
            claim(predicate=predicate, scope=scope)


@pytest.mark.parametrize("predicate", TESTED)
def test_tested_threat_requires_tested_response_scope(predicate):
    claim(predicate=predicate, scope=_S.TESTED_RESPONSE)
    for scope in (_S.LOCAL, _S.REPRESENTATIVE_ALTERNATIVES):
        with pytest.raises(ExplanationClaimError, match="tested_response scope"):
            claim(predicate=predicate, scope=scope)


def test_duplicate_objects_rejected():
    piece = base_frame_piece_entity(BASE_ID, KNIGHT)
    with pytest.raises(ExplanationClaimError, match="duplicates"):
        claim(objects=(piece, piece))


def test_same_physical_piece_in_two_frames_is_a_duplicate():
    moved = PieceClaimEntity(KNIGHT, AFTER_ID, "f3", PieceType.KNIGHT)
    with pytest.raises(ExplanationClaimError, match="duplicates"):
        claim(objects=(base_frame_piece_entity(BASE_ID, KNIGHT), moved))


def test_same_move_with_different_san_is_a_duplicate():
    response = MoveClaimEntity(ChessMove("g8f6"), AFTER_ID)
    with_san = MoveClaimEntity(ChessMove("g8f6", "Nf6"), AFTER_ID)
    with pytest.raises(ExplanationClaimError, match="duplicates"):
        claim(objects=(response, with_san))


def test_same_uci_from_different_positions_is_distinct():
    claim(objects=(MoveClaimEntity(ChessMove("g8f6"), AFTER_ID), PLAYED))


@pytest.mark.parametrize(
    "evidence_ids",
    [(), ("ev_001", "ev_001"), ("",), ("ev_0001",), ("ev_000",), ("cl_001",), ("ev_1",)],
)
def test_claim_evidence_ids_must_be_non_empty_unique_canonical(evidence_ids):
    with pytest.raises(ExplanationClaimError, match="evidence_ids"):
        claim(evidence_ids=evidence_ids)


@pytest.mark.parametrize("claim_id", ["", "cl_000", "cl_01", "cl_0001", "ev_001", "claim"])
def test_claim_id_must_be_canonical(claim_id):
    with pytest.raises(ExplanationClaimError, match="claim_id"):
        claim(claim_id=claim_id)


def test_claim_requires_base_position():
    with pytest.raises(ExplanationClaimError, match="base_position_id"):
        claim(base_position_id="")


@pytest.mark.parametrize(
    "subject", [base_frame_piece_entity(BASE_ID, KNIGHT), SideClaimEntity(Color.WHITE)]
)
def test_subject_must_be_move_entity(subject):
    with pytest.raises(ExplanationClaimError, match="MoveClaimEntity"):
        claim(subject=subject)


def test_subject_move_must_be_legal_from_claim_base():
    with pytest.raises(ExplanationClaimError, match="legal from the claim base"):
        claim(subject=MoveClaimEntity(ChessMove("e2e4"), AFTER_ID))


def test_forced_confidence_is_structurally_allowed_in_i0():
    assert claim(confidence=ClaimConfidence.FORCED).confidence is ClaimConfidence.FORCED


@pytest.mark.parametrize(
    ("field", "value"),
    [("predicate", "leaves_piece_hanging"), ("confidence", "exact"), ("scope", "local")],
)
def test_claim_enums_must_be_typed(field, value):
    with pytest.raises(ExplanationClaimError, match=field):
        claim(**{field: value})


def test_replace_revalidates():
    with pytest.raises(ExplanationClaimError):
        replace(claim(), scope=_S.TESTED_RESPONSE)


def test_vocabulary_is_internal_only():
    for name in explanation.__all__:
        assert not hasattr(calliope, name), name
