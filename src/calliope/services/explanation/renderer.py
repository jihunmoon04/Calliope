"""MVP-P12 deterministic renderer: validated P11 pair -> one sentence per selected claim.

Presentation only.  The only inputs to prose are the selected claims' closed-vocabulary
predicate/confidence/scope, the subject and object move UCIs, and the base-frame identity of
object pieces.  Nothing here reads evidence payloads, SAN, scores, PVs, engines or chess rules;
the retained EvidenceBundle is read only by the P11/P10 revalidation it delegates to.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from calliope.domain.chess import Color, PieceType
from calliope.domain.explanation import (
    ClaimConfidence,
    ClaimPredicate,
    ClaimScope,
    ExplanationClaim,
    ExplanationGraph,
    ExplanationSelection,
    MoveClaimEntity,
    PieceClaimEntity,
)
from calliope.domain.explanation.render import NO_VERIFIED_EXPLANATION, RenderedCommentary
from calliope.errors import CalliopeError, ExplanationRenderError
from calliope.services.explanation.selector import ExplanationSelectionValidator

_P = ClaimPredicate
_C = ClaimConfidence
_S = ClaimScope


class MoveFrame(StrEnum):
    """Base-vs-non-base frame of a retained move object; P12 never derives the position."""

    BASE_MOVE = "base_move"
    AFTER_MOVE = "after_move"


@dataclass(frozen=True, slots=True)
class RenderRule:
    """One frozen A0 §10/§11 rule: exact object signature plus canonical English template."""

    min_moves: int
    max_moves: int
    move_frame: MoveFrame | None
    min_pieces: int
    max_pieces: int | None
    template: str


_AFTER = MoveFrame.AFTER_MOVE
_BASE = MoveFrame.BASE_MOVE


def _rule(moves, frame, pieces, template) -> RenderRule:
    low_moves, high_moves = moves if isinstance(moves, tuple) else (moves, moves)
    low_pieces, high_pieces = pieces
    return RenderRule(low_moves, high_moves, frame, low_pieces, high_pieces, template)


_EXACTLY_ONE = (1, 1)
_AT_LEAST_ONE = (1, None)

RENDER_RULES: dict[tuple[ClaimPredicate, ClaimConfidence, ClaimScope], RenderRule] = {
    (_P.LEAVES_PIECE_HANGING, _C.ENGINE_VERIFIED, _S.LOCAL): _rule(
        1, _AFTER, _EXACTLY_ONE, "Move {move} leaves {pieces} hanging."
    ),
    (_P.REMOVES_DEFENDER, _C.ENGINE_VERIFIED, _S.LOCAL): _rule(
        1, _AFTER, _EXACTLY_ONE, "Move {move} removes a defender of {pieces}."
    ),
    # P10 retains the fork actor and its targets together without role tags.
    (_P.ALLOWS_FORK, _C.ENGINE_VERIFIED, _S.LOCAL): _rule(
        1, _AFTER, (3, None), "Move {move} allows a fork."
    ),
    (_P.ALLOWS_CHECKMATE, _C.EXACT, _S.LOCAL): _rule(
        1, _AFTER, _EXACTLY_ONE, "Move {move} allows checkmate."
    ),
    (_P.ALLOWS_CHECKMATE, _C.ENGINE_VERIFIED, _S.LOCAL): _rule(
        1, _AFTER, _EXACTLY_ONE, "Move {move} allows an engine-verified mating line."
    ),
    (_P.ALLOWS_MATERIAL_LOSS, _C.ENGINE_VERIFIED, _S.LOCAL): _rule(
        1, _AFTER, _AT_LEAST_ONE, "Move {move} allows an engine-verified line with material loss."
    ),
    (_P.FORCES_RESPONSE, _C.EXACT, _S.LOCAL): _rule(
        1, _AFTER, _AT_LEAST_ONE, "Move {move} forces response {response}."
    ),
    (_P.DELIVERS_CHECKMATE, _C.EXACT, _S.LOCAL): _rule(
        0, None, _EXACTLY_ONE, "Move {move} delivers checkmate."
    ),
    (_P.LEADS_TO_MATE, _C.ENGINE_VERIFIED, _S.LOCAL): _rule(
        0, None, _EXACTLY_ONE, "Move {move} has an engine-verified line leading to mate."
    ),
    (_P.WINS_MATERIAL, _C.ENGINE_VERIFIED, _S.LOCAL): _rule(
        0, None, _AT_LEAST_ONE, "Move {move} has an engine-verified line that wins material."
    ),
    # The tested response Q is the concrete reply that was tested and failed to meet the threat.
    (_P.THREATENS_MATE_IF_IGNORED, _C.ENGINE_VERIFIED, _S.TESTED_RESPONSE): _rule(
        1,
        _AFTER,
        _EXACTLY_ONE,
        "Move {move} creates a mate threat that tested response {response} does not meet.",
    ),
    (_P.THREATENS_MATERIAL_IF_IGNORED, _C.ENGINE_VERIFIED, _S.TESTED_RESPONSE): _rule(
        1,
        _AFTER,
        _AT_LEAST_ONE,
        "Move {move} creates a material threat that tested response {response} does not meet.",
    ),
    (
        _P.AVOIDS_REPRESENTATIVE_MATE_FAILURE,
        _C.ENGINE_VERIFIED,
        _S.REPRESENTATIVE_ALTERNATIVES,
    ): _rule(
        (1, 2),
        _BASE,
        _EXACTLY_ONE,
        "Compared with the tested representative alternatives, move {move} avoids the mate"
        " failure seen after {alternatives}.",
    ),
    (
        _P.AVOIDS_REPRESENTATIVE_MATERIAL_LOSS,
        _C.ENGINE_VERIFIED,
        _S.REPRESENTATIVE_ALTERNATIVES,
    ): _rule(
        (1, 2),
        _BASE,
        _AT_LEAST_ONE,
        "Compared with the tested representative alternatives, move {move} avoids the material"
        " loss seen after {alternatives}.",
    ),
}
"""Frozen closed table over the 14 current P10-valid forms; there is no fallback rule."""

_COLOR_WORDS = {Color.WHITE: "white", Color.BLACK: "black"}
_PIECE_WORDS = {
    PieceType.PAWN: "pawn",
    PieceType.KNIGHT: "knight",
    PieceType.BISHOP: "bishop",
    PieceType.ROOK: "rook",
    PieceType.QUEEN: "queen",
    PieceType.KING: "king",
}


def _fail(message: str) -> ExplanationRenderError:
    return ExplanationRenderError(message)


def format_list(items: Iterable[str]) -> str:
    """``A`` / ``A and B`` / ``A, B, and C`` in the given order."""

    values = list(items)
    if not values:
        raise _fail("cannot format an empty list")
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def _require_base_frame(claim: ExplanationClaim, piece: PieceClaimEntity) -> None:
    ref = piece.base_ref
    if (
        piece.at_position_id != claim.base_position_id
        or piece.current_square != ref.base_square
        or piece.current_piece_type is not ref.piece_type
    ):
        raise _fail("strict P12 renders only base-frame piece presentations")


def _piece_text(piece: PieceClaimEntity) -> str:
    """Base-frame physical identity: ``{color} {piece} from {base square}``."""

    ref = piece.base_ref
    color = _COLOR_WORDS.get(ref.color) if type(ref.color) is Color else None
    name = _PIECE_WORDS.get(ref.piece_type) if type(ref.piece_type) is PieceType else None
    if color is None or name is None:
        raise _fail("piece identity has no closed lexical presentation")
    return f"{color} {name} from {ref.base_square}"


def _move_frame(claim: ExplanationClaim, move: MoveClaimEntity) -> MoveFrame:
    return (
        MoveFrame.BASE_MOVE if move.position_id == claim.base_position_id else MoveFrame.AFTER_MOVE
    )


def _uci(move: MoveClaimEntity) -> str:
    uci = move.move.uci
    if not isinstance(uci, str) or not uci:
        raise _fail("move presentation requires a canonical UCI string")
    return uci


def render_rule(claim: ExplanationClaim) -> RenderRule:
    """The one closed rule for an exact (predicate, confidence, scope) form; FORCED has none."""

    form = (claim.predicate, claim.confidence, claim.scope)
    if (
        type(claim.predicate) is not ClaimPredicate
        or type(claim.confidence) is not ClaimConfidence
        or type(claim.scope) is not ClaimScope
    ):
        raise _fail("render form requires exact P10 predicate/confidence/scope members")
    rule = RENDER_RULES.get(form)
    if rule is None:
        raise _fail(
            f"no frozen render rule for {claim.predicate.value} / {claim.confidence.value}"
            f" / {claim.scope.value}"
        )
    return rule


def check_signature(
    claim: ExplanationClaim, rule: RenderRule
) -> tuple[list[MoveClaimEntity], list[PieceClaimEntity]]:
    """Exact frozen §11 object signature; unprinted objects are validated too."""

    subject = claim.subject
    if type(subject) is not MoveClaimEntity or _move_frame(claim, subject) is not _BASE:
        raise _fail("claim subject must be a base-frame move")
    if not isinstance(claim.objects, tuple):
        raise _fail("claim objects must be a tuple")
    moves: list[MoveClaimEntity] = []
    pieces: list[PieceClaimEntity] = []
    for entity in claim.objects:
        if type(entity) is MoveClaimEntity:
            moves.append(entity)
        elif type(entity) is PieceClaimEntity:
            pieces.append(entity)
        else:
            raise _fail(f"unexpected {type(entity).__name__} object for {claim.predicate.value}")
    if not rule.min_moves <= len(moves) <= rule.max_moves:
        raise _fail(f"{claim.predicate.value} move objects do not match the frozen signature")
    if any(_move_frame(claim, move) is not rule.move_frame for move in moves):
        raise _fail(f"{claim.predicate.value} move object is in the wrong frame")
    if len(pieces) < rule.min_pieces or (
        rule.max_pieces is not None and len(pieces) > rule.max_pieces
    ):
        raise _fail(f"{claim.predicate.value} piece objects do not match the frozen signature")
    for piece in pieces:
        _require_base_frame(claim, piece)
        _piece_text(piece)  # closed lexical presentation, printed or not
    return moves, pieces


def render_claim(claim: ExplanationClaim) -> str:
    """One selected claim -> one sentence, after its exact object signature passes."""

    if type(claim) is not ExplanationClaim:
        raise _fail("renderer requires an ExplanationClaim")
    rule = render_rule(claim)
    moves, pieces = check_signature(claim, rule)
    values = {"move": _uci(claim.subject)}
    if "{pieces}" in rule.template:
        values["pieces"] = format_list(_piece_text(piece) for piece in pieces)
    if "{response}" in rule.template:
        values["response"] = format_list(_uci(move) for move in moves)
    if "{alternatives}" in rule.template:
        values["alternatives"] = format_list(_uci(move) for move in moves)
    return rule.template.format(**values)


class DeterministicExplanationRenderer:
    """Validated (graph, selection) pair -> RenderedCommentary; the pair is never trusted."""

    def __init__(self) -> None:
        self._selections = ExplanationSelectionValidator()

    def render(
        self, graph: ExplanationGraph, selection: ExplanationSelection
    ) -> RenderedCommentary:
        # Step 1: P11 pair revalidation (graph -> P10 -> exact selection) before any claim read.
        try:
            self._selections.validate(graph, selection)
        except CalliopeError as exc:
            raise ExplanationRenderError(f"P11 pair failed revalidation: {exc}") from exc
        if selection.selected_relation_ids != ():
            raise _fail("no relation rule is active; selected relations must be empty")

        # Step 2: an empty selection is meta-level status, never a manufactured chess reason.
        if selection.selected_claim_ids == ():
            return RenderedCommentary(
                text=NO_VERIFIED_EXPLANATION,
                sentences=(),
                used_claim_ids=(),
            )

        # Step 3: resolve in selection (render) order; never sorted.
        by_id = {claim.claim_id: claim for claim in graph.claims}
        missing = [i for i in selection.selected_claim_ids if i not in by_id]
        if missing:
            raise _fail(f"selected claim {missing[0]} does not resolve in the graph")
        selected = tuple(by_id[claim_id] for claim_id in selection.selected_claim_ids)

        # Steps 4-6: signature check plus one closed rule per claim, then plain adjacency.
        sentences = tuple(render_claim(claim) for claim in selected)
        text = " ".join(sentences)
        if len(sentences) != len(selection.selected_claim_ids):
            raise _fail("rendering must produce exactly one sentence per selected claim")
        rendered = RenderedCommentary(
            text=text,
            sentences=sentences,
            used_claim_ids=selection.selected_claim_ids,
        )
        matches_selection = rendered.used_claim_ids == selection.selected_claim_ids
        if not matches_selection or rendered.text != " ".join(rendered.sentences):
            raise _fail("rendered provenance differs from the validated selection")
        return rendered
