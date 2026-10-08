"""Schema-0.2 public projection: lossless copy only, exact-type dispatch, no SAN, no reasoning."""

import dataclasses

import _g0_fakes  # noqa: F401  (puts the explanation scenario corpus on sys.path)
import _p8_claim_scenarios as p8
import _p9_preservation_claim_scenarios as pres
import _p9_strong_claim_scenarios as strong
import pytest

import calliope
from calliope.application.projection import (
    project_claim,
    project_claims,
    project_commentary,
    project_entity,
    project_selected_ids,
)
from calliope.contracts import (
    PUBLIC_SCHEMA_VERSION,
    ClaimEntityKind,
    ClaimView,
    CommentaryView,
    MoveAnalysisResult,
    MoveClaimEntityView,
    PieceClaimEntityView,
    SideClaimEntityView,
)
from calliope.domain.analysis import BasePieceRef
from calliope.domain.chess import ChessMove, Color, PieceType
from calliope.domain.explanation import (
    ClaimScope,
    MoveClaimEntity,
    PieceClaimEntity,
    RenderedCommentary,
    SideClaimEntity,
)
from calliope.errors import ApplicationError, ClaimProjectionError

tamper = p8.tamper


def corpus_claims():
    packages = [p8.evidence(m()) for m in (p8.knight, p8.defender, p8.fork, p8.exact_mate)]
    claims = [c for b in packages for c in p8.claims(b)]
    claims += [c for m in strong.SCENARIOS for c in strong.claims(strong.evidence(m()))]
    claims += [c for m in pres.SCENARIOS for c in pres.claims(pres.evidence(m()))]
    return claims


# ---- contracts ----------------------------------------------------------------------------------


def test_schema_is_0_2_and_shapes_are_frozen():
    assert PUBLIC_SCHEMA_VERSION == "0.2"
    assert [f.name for f in dataclasses.fields(ClaimView)] == [
        "claim_id",
        "base_position_id",
        "confidence",
        "scope",
        "subject",
        "predicate",
        "objects",
        "evidence_ids",
        "importance",
    ]
    assert [f.name for f in dataclasses.fields(CommentaryView)] == [
        "text",
        "sentences",
        "used_claim_ids",
    ]
    assert [f.name for f in dataclasses.fields(MoveAnalysisResult)][3:5] == [
        "claims",
        "selected_claim_ids",
    ]
    assert [f.name for f in dataclasses.fields(PieceClaimEntityView)] == [
        "color",
        "base_piece_type",
        "base_square",
        "at_position_id",
        "current_piece_type",
        "current_square",
        "kind",
    ]


def test_entity_kind_is_a_fixed_discriminator():
    assert MoveClaimEntityView("e2e4", "pos").kind is ClaimEntityKind.MOVE
    assert SideClaimEntityView("white").kind is ClaimEntityKind.SIDE
    with pytest.raises(TypeError):
        MoveClaimEntityView("e2e4", "pos", kind=ClaimEntityKind.PIECE)  # type: ignore[call-arg]
    assert {k.value for k in ClaimEntityKind} == {"move", "piece", "side"}


def test_projection_error_is_an_application_error():
    assert issubclass(ClaimProjectionError, ApplicationError)


def test_nested_dtos_are_not_top_level_exports():
    for name in ("ClaimEntityKind", "MoveClaimEntityView", "PieceClaimEntityView"):
        assert not hasattr(calliope, name)
    assert not hasattr(calliope, "MoveExplanationPipeline")


# ---- entity variants ----------------------------------------------------------------------------


def test_move_entity_is_uci_plus_frame_never_san():
    view = project_entity(MoveClaimEntity(ChessMove("d1d8", "Rd8#"), "pos_after"))
    assert view == MoveClaimEntityView(move_uci="d1d8", position_id="pos_after")
    assert "Rd8#" not in repr(view)


def test_piece_entity_keeps_identity_and_presentation_frame():
    piece = PieceClaimEntity(
        BasePieceRef(Color.BLACK, PieceType.PAWN, "b2"), "pos_later", "b1", PieceType.QUEEN
    )
    assert project_entity(piece) == PieceClaimEntityView(
        color="black",
        base_piece_type="pawn",
        base_square="b2",
        at_position_id="pos_later",
        current_piece_type="queen",
        current_square="b1",
    )


def test_side_entity():
    assert project_entity(SideClaimEntity(Color.WHITE)) == SideClaimEntityView("white")


@pytest.mark.parametrize(
    "entity",
    [
        "white knight on c3",
        ChessMove("e2e4"),
        BasePieceRef(Color.WHITE, PieceType.KNIGHT, "c3"),
        None,
    ],
)
def test_unknown_entities_fail_closed(entity):
    with pytest.raises(ClaimProjectionError):
        project_entity(entity)


def test_plain_string_enums_fail_closed():
    piece = PieceClaimEntity(
        BasePieceRef(Color.WHITE, PieceType.KNIGHT, "c3"), "pos", "c3", PieceType.KNIGHT
    )
    tamper(piece, current_piece_type="knight")
    with pytest.raises(ClaimProjectionError):
        project_entity(piece)


# ---- whole claims -------------------------------------------------------------------------------


def _back(view, claim):
    """Independent oracle: the public view must carry every internal value exactly."""

    assert view.claim_id == claim.claim_id
    assert view.base_position_id == claim.base_position_id
    assert (view.confidence, view.scope, view.predicate) == (
        claim.confidence.value,
        claim.scope.value,
        claim.predicate.value,
    )
    assert (view.subject.move_uci, view.subject.position_id) == (
        claim.subject.move.uci,
        claim.subject.position_id,
    )
    assert view.evidence_ids == claim.evidence_ids and view.importance is claim.importance
    assert len(view.objects) == len(claim.objects)
    for public, internal in zip(view.objects, claim.objects, strict=True):
        if type(internal) is MoveClaimEntity:
            assert public == MoveClaimEntityView(internal.move.uci, internal.position_id)
        else:
            ref = internal.base_ref
            assert public == PieceClaimEntityView(
                ref.color.value,
                ref.piece_type.value,
                ref.base_square,
                internal.at_position_id,
                internal.current_piece_type.value,
                internal.current_square,
            )


def test_every_corpus_claim_projects_losslessly():
    claims = corpus_claims()
    assert {c.scope for c in claims} == set(ClaimScope)
    for claim in claims:
        _back(project_claim(claim), claim)


def test_scope_limitations_survive_projection():
    scoped = {project_claim(c).scope for c in corpus_claims()}
    assert scoped == {"local", "tested_response", "representative_alternatives"}
    (preservation,) = [c for c in pres.claims(pres.evidence(pres.material_all()))]
    view = project_claim(preservation)
    assert view.scope == "representative_alternatives"
    moves = [o for o in view.objects if o.kind is ClaimEntityKind.MOVE]
    assert moves and all(m.position_id == view.base_position_id for m in moves)


def test_object_and_evidence_order_is_preserved():
    (fork_claim,) = [
        c for c in p8.claims(p8.evidence(p8.fork())) if c.predicate.value == "allows_fork"
    ]
    view = project_claim(fork_claim)
    assert [type(o).__name__ for o in view.objects] == [
        "MoveClaimEntityView",
        "PieceClaimEntityView",
        "PieceClaimEntityView",
        "PieceClaimEntityView",
    ]
    assert [o.base_square for o in view.objects[1:]] == [
        o.base_ref.base_square for o in fork_claim.objects[1:]
    ]
    assert view.evidence_ids == fork_claim.evidence_ids


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope", "local"),
        ("confidence", "engine_verified"),
        ("predicate", "allows_fork"),
        ("objects", ["not", "a", "tuple"]),
        ("evidence_ids", ["ev_001"]),
        ("importance", 1),
        ("subject", SideClaimEntity(Color.WHITE)),
    ],
)
def test_malformed_claims_fail_closed(field, value):
    claim = p8.claims(p8.evidence(p8.knight()))[0]
    tamper(claim, **{field: value})
    with pytest.raises(ClaimProjectionError):
        project_claim(claim)


def test_claim_collection_and_selection_resolution():
    claims = project_claims(p8.claims(p8.evidence(p8.knight())))
    assert project_selected_ids(claims, ("cl_002", "cl_001")) == ("cl_002", "cl_001")
    with pytest.raises(ClaimProjectionError):
        project_selected_ids(claims, ("cl_003",))
    with pytest.raises(ClaimProjectionError):
        project_selected_ids((*claims, claims[0]), ("cl_001",))
    with pytest.raises(ClaimProjectionError):
        project_claims(list(p8.claims(p8.evidence(p8.knight()))))  # type: ignore[arg-type]


def test_commentary_projection_is_exact():
    rendered = RenderedCommentary(
        text="Move d1d7 allows checkmate.",
        sentences=("Move d1d7 allows checkmate.",),
        used_claim_ids=("cl_001",),
    )
    assert project_commentary(rendered) == CommentaryView(
        "Move d1d7 allows checkmate.", ("Move d1d7 allows checkmate.",), ("cl_001",)
    )
    with pytest.raises(ClaimProjectionError):
        project_commentary(CommentaryView("x", (), ()))  # type: ignore[arg-type]
