"""P12-I0/I1: deterministic renderer golden matrix and core contract.

Uses the reviewed P10 unit scenario corpus (python-chess rules + scripted P7 engine), not real
Stockfish; the real-engine P12 gate lives with the Stockfish integration tests.
"""

import pytest
from _p12_render_corpus import (
    CORPUS,
    FORM_GOLDEN,
    GOLDEN,
    NO_VERIFIED_EXPLANATION,
    empty_pair,
    pair,
    render,
)

from calliope.domain.explanation import (
    ClaimConfidence,
    ClaimPredicate,
    ClaimScope,
    MoveClaimEntity,
    PieceClaimEntity,
    RenderedCommentary,
    required_claim_scope,
)
from calliope.services.explanation import DeterministicExplanationRenderer
from calliope.services.explanation.renderer import (
    RENDER_RULES,
    MoveFrame,
    format_list,
    render_claim,
)

_P = ClaimPredicate
_C = ClaimConfidence
_S = ClaimScope

# Independent oracle copy of the frozen A0 §11 signature table:
# (move count range, move frame, minimum pieces, maximum pieces or None).
FROZEN_SIGNATURES = {
    (_P.LEAVES_PIECE_HANGING, _C.ENGINE_VERIFIED, _S.LOCAL): ((1, 1), "after", 1, 1),
    (_P.REMOVES_DEFENDER, _C.ENGINE_VERIFIED, _S.LOCAL): ((1, 1), "after", 1, 1),
    (_P.ALLOWS_FORK, _C.ENGINE_VERIFIED, _S.LOCAL): ((1, 1), "after", 3, None),
    (_P.ALLOWS_CHECKMATE, _C.EXACT, _S.LOCAL): ((1, 1), "after", 1, 1),
    (_P.ALLOWS_CHECKMATE, _C.ENGINE_VERIFIED, _S.LOCAL): ((1, 1), "after", 1, 1),
    (_P.ALLOWS_MATERIAL_LOSS, _C.ENGINE_VERIFIED, _S.LOCAL): ((1, 1), "after", 1, None),
    (_P.FORCES_RESPONSE, _C.EXACT, _S.LOCAL): ((1, 1), "after", 1, None),
    (_P.DELIVERS_CHECKMATE, _C.EXACT, _S.LOCAL): ((0, 0), None, 1, 1),
    (_P.LEADS_TO_MATE, _C.ENGINE_VERIFIED, _S.LOCAL): ((0, 0), None, 1, 1),
    (_P.WINS_MATERIAL, _C.ENGINE_VERIFIED, _S.LOCAL): ((0, 0), None, 1, None),
    (_P.THREATENS_MATE_IF_IGNORED, _C.ENGINE_VERIFIED, _S.TESTED_RESPONSE): (
        (1, 1),
        "after",
        1,
        1,
    ),
    (_P.THREATENS_MATERIAL_IF_IGNORED, _C.ENGINE_VERIFIED, _S.TESTED_RESPONSE): (
        (1, 1),
        "after",
        1,
        None,
    ),
    (
        _P.AVOIDS_REPRESENTATIVE_MATE_FAILURE,
        _C.ENGINE_VERIFIED,
        _S.REPRESENTATIVE_ALTERNATIVES,
    ): ((1, 2), "base", 1, 1),
    (
        _P.AVOIDS_REPRESENTATIVE_MATERIAL_LOSS,
        _C.ENGINE_VERIFIED,
        _S.REPRESENTATIVE_ALTERNATIVES,
    ): ((1, 2), "base", 1, None),
}


FRAMES = {None: None, "after": MoveFrame.AFTER_MOVE, "base": MoveFrame.BASE_MOVE}


# ---- 14-form golden matrix ----------------------------------------------------------------------


def test_golden_oracle_covers_the_whole_corpus():
    assert set(GOLDEN) == set(CORPUS)


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_corpus_golden_sentences(name):
    graph, selection = pair(name)
    rendered = DeterministicExplanationRenderer().render(graph, selection)
    assert type(rendered) is RenderedCommentary
    assert rendered.sentences == GOLDEN[name]
    assert rendered.used_claim_ids == selection.selected_claim_ids
    assert rendered.text == " ".join(GOLDEN[name])


def test_rule_table_is_exactly_the_fourteen_valid_forms():
    assert len(RENDER_RULES) == 14
    assert set(RENDER_RULES) == set(FORM_GOLDEN) == set(FROZEN_SIGNATURES)
    for predicate, confidence, scope in RENDER_RULES:
        assert confidence is not _C.FORCED
        assert scope is required_claim_scope(predicate)


@pytest.mark.parametrize("form", sorted(FORM_GOLDEN, key=lambda f: tuple(map(str, f))))
def test_every_form_has_a_selected_golden_sentence(form):
    name, index = FORM_GOLDEN[form]
    graph, selection = pair(name)
    claim_id = selection.selected_claim_ids[index]
    (claim,) = [c for c in graph.claims if c.claim_id == claim_id]
    assert (claim.predicate, claim.confidence, claim.scope) == form
    assert render(name).sentences[index] == GOLDEN[name][index]
    assert render_claim(claim) == GOLDEN[name][index]


@pytest.mark.parametrize("form", sorted(FROZEN_SIGNATURES, key=lambda f: tuple(map(str, f))))
def test_signature_table_matches_the_frozen_design(form):
    (low, high), frame, min_pieces, max_pieces = FROZEN_SIGNATURES[form]
    rule = RENDER_RULES[form]
    assert (rule.min_moves, rule.max_moves) == (low, high)
    assert rule.move_frame is FRAMES[frame]
    assert (rule.min_pieces, rule.max_pieces) == (min_pieces, max_pieces)


@pytest.mark.parametrize("form", sorted(FORM_GOLDEN, key=lambda f: tuple(map(str, f))))
def test_every_golden_claim_has_its_exact_frozen_signature(form):
    name, index = FORM_GOLDEN[form]
    graph, selection = pair(name)
    (claim,) = [c for c in graph.claims if c.claim_id == selection.selected_claim_ids[index]]
    moves = [o for o in claim.objects if type(o) is MoveClaimEntity]
    pieces = [o for o in claim.objects if type(o) is PieceClaimEntity]
    assert len(moves) + len(pieces) == len(claim.objects)
    (low, high), frame, min_pieces, max_pieces = FROZEN_SIGNATURES[form]
    assert low <= len(moves) <= high
    for move in moves:
        is_base = move.position_id == claim.base_position_id
        assert is_base is (frame == "base")
    assert min_pieces <= len(pieces) and (max_pieces is None or len(pieces) <= max_pieces)
    for piece in pieces:
        assert piece.at_position_id == claim.base_position_id
        assert piece.current_square == piece.base_ref.base_square
        assert piece.current_piece_type is piece.base_ref.piece_type


# ---- wording safety -----------------------------------------------------------------------------

FORBIDDEN_EVERYWHERE = (
    " because ",
    " therefore",
    " so ",
    " causes ",
    " enables ",
    " which leads to ",
    "forced",
    "only move",
    "unique",
    "every ",
    " all ",
    "unstoppable",
    "unavoidable",
    "inevitabl",
    " on ",
)


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_no_synthesis_strengthening_or_post_move_square_wording(name):
    for sentence in render(name).sentences:
        lowered = f" {sentence.lower()} "
        for phrase in FORBIDDEN_EVERYWHERE:
            assert phrase not in lowered, (name, phrase, sentence)
        assert sentence.endswith(".") and sentence.count(".") == 1


@pytest.mark.parametrize("name", ["strong-ignored_mate", "strong-ignored_material"])
def test_tested_q_is_a_failed_response_never_a_defense(name):
    (sentence,) = render(name).sentences
    assert "tested response" in sentence and sentence.endswith(" does not meet.")
    lowered = sentence.lower()
    for phrase in (
        "not played",
        "unless",
        "must play",
        "must be played",
        "defend",
        "defence",
        "defense",
        "only",
        "other response",
        "all ",
        "every",
        "if ",
        "unstoppable",
        "unavoidable",
    ):
        assert phrase not in lowered, phrase


def test_fork_never_prints_actor_or_targets_as_roles():
    graph, _ = pair("p8-fork")
    (fork,) = [c for c in graph.claims if c.predicate is _P.ALLOWS_FORK]
    pieces = [o for o in fork.objects if type(o) is PieceClaimEntity]
    colors = {p.base_ref.color for p in pieces}
    assert len(pieces) >= 3 and len(colors) == 2  # actor and targets are mixed, untagged
    sentence = render_claim(fork)
    assert sentence == "Move d3e4 allows a fork."
    assert "against" not in sentence and " from " not in sentence and "knight" not in sentence


def test_engine_verified_forms_say_engine_verified_and_exact_forms_do_not():
    for form, (name, index) in FORM_GOLDEN.items():
        sentence = GOLDEN[name][index]
        predicate, confidence, scope = form
        if scope is not _S.LOCAL:
            continue  # tested-response / representative scope carry their own limitation
        if predicate in (_P.LEAVES_PIECE_HANGING, _P.REMOVES_DEFENDER, _P.ALLOWS_FORK):
            continue  # tactical mechanism names the motif only
        assert ("engine-verified" in sentence) is (confidence is _C.ENGINE_VERIFIED), sentence
        assert "verified" not in sentence.replace("engine-verified", ""), sentence


def test_exact_and_engine_verified_mate_wording_differ():
    assert render("p8-exact-mate").text == "Move d1d7 allows checkmate."
    assert render("p8-engine-mate").text == "Move d1d7 allows an engine-verified mating line."


@pytest.mark.parametrize("name", [n for n in sorted(CORPUS) if n.startswith("pres-")])
def test_preservation_keeps_representative_scope(name):
    for sentence in render(name).sentences:
        assert sentence.startswith("Compared with the tested representative alternatives, ")
        lowered = sentence.lower()
        for phrase in ("only", "unique", "all alternatives", "every", "forced", "exhaustive"):
            assert phrase not in lowered


# ---- presentation helpers -----------------------------------------------------------------------


def test_list_formatting_is_deterministic_and_order_preserving():
    assert format_list(["a"]) == "a"
    assert format_list(["b", "a"]) == "b and a"
    assert format_list(["c", "a", "b"]) == "c, a, and b"
    assert format_list(["d", "c", "b", "a"]) == "d, c, b, and a"


def test_moves_are_printed_as_uci_only():
    graph, _ = pair("p8-knight")
    sans = {o.move.san for c in graph.claims for o in (c.subject, *c.objects) if hasattr(o, "move")}
    assert sans - {None}  # the corpus retains SAN presentation metadata ...
    for sentence in render("p8-knight").sentences:
        for san in sans - {None}:
            assert san not in sentence  # ... which P12 never prints


# ---- empty selection ----------------------------------------------------------------------------


def test_empty_selection_is_meta_only():
    graph, selection = empty_pair()
    assert graph.claims == () and selection.selected_claim_ids == ()
    rendered = DeterministicExplanationRenderer().render(graph, selection)
    assert rendered == RenderedCommentary(
        text=NO_VERIFIED_EXPLANATION, sentences=(), used_claim_ids=()
    )


def test_renderer_returns_the_selection_provenance_for_every_package():
    for name in CORPUS:
        graph, selection = pair(name)
        rendered = DeterministicExplanationRenderer().render(graph, selection)
        assert rendered.used_claim_ids == selection.selected_claim_ids
        assert len(rendered.sentences) == len(selection.selected_claim_ids)
        assert rendered.text == " ".join(rendered.sentences)
