"""P12-I1: adversarial, signature, mutation and determinism gate for the deterministic renderer.

Uses the reviewed P10 unit scenario corpus (python-chess rules + scripted P7 engine), not real
Stockfish.  No production behaviour is changed: mutation tests monkeypatch the renderer only to
prove that the oracle below would catch such a change.
"""

import ast
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import _p8_claim_scenarios as p8
import pytest
from _p12_render_corpus import (
    CORPUS,
    GOLDEN,
    NO_VERIFIED_EXPLANATION,
    built,
    defender_without_unselected_claim,
    empty_pair,
    pair,
    signature,
)

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.adapters.stockfish import StockfishAdapter
from calliope.domain.analysis import BasePieceRef
from calliope.domain.chess import ChessMove, Color, PieceType
from calliope.domain.engine import EngineScore
from calliope.domain.explanation import (
    ClaimConfidence,
    ClaimPredicate,
    ClaimScope,
    ExplanationClaim,
    ExplanationGraph,
    ExplanationRelation,
    ExplanationRelationKind,
    ExplanationSelection,
    MoveClaimEntity,
    PieceClaimEntity,
    RenderedCommentary,
    SideClaimEntity,
    base_frame_piece_entity,
)
from calliope.errors import (
    ExplanationGraphError,
    ExplanationRenderError,
    ExplanationSelectionError,
)
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.explanation import (
    DeterministicExplanationRenderer,
    ExplanationSelector,
    GraphBuilder,
)
from calliope.services.explanation import renderer as renderer_module
from calliope.services.explanation.renderer import RENDER_RULES, render_claim
from calliope.services.explanation.selector import ExplanationSelectionValidator

tamper = p8.tamper
_P = ClaimPredicate
_C = ClaimConfidence
_S = ClaimScope
REPO = Path(__file__).resolve().parents[4]
RENDERER_SOURCE = Path(renderer_module.__file__)
AFTER = "pos_after_tampered"


def _render(graph, selection):
    return DeterministicExplanationRenderer().render(graph, selection)


def _claim(name, predicate):
    graph = built(name)
    (claim,) = [c for c in graph.claims if c.predicate is predicate]
    return graph, claim


def _move(claim, index=0):
    return [o for o in claim.objects if type(o) is MoveClaimEntity][index]


def _pieces(claim):
    return [o for o in claim.objects if type(o) is PieceClaimEntity]


def _base_piece(claim, color, piece_type, square):
    return base_frame_piece_entity(claim.base_position_id, BasePieceRef(color, piece_type, square))


def _reframed_piece(piece, **changes):
    copy = replace(piece)
    return tamper(copy, **changes)


# ---- A. exact object signatures -----------------------------------------------------------------
# Each entry: (fixture, predicate, new objects).  Applied two ways: the P12-own gate on a
# structurally valid synthetic claim, and the full pipeline on a tampered graph.


def _after(move):
    return MoveClaimEntity(move.move, AFTER)


SIGNATURE_TAMPERS = {
    "hanging-missing-punishment": (
        "p8-knight",
        _P.LEAVES_PIECE_HANGING,
        lambda c: tuple(_pieces(c)),
    ),
    "hanging-punishment-base-frame": (
        "p8-knight",
        _P.LEAVES_PIECE_HANGING,
        lambda c: (MoveClaimEntity(_move(c).move, c.base_position_id), *_pieces(c)),
    ),
    "hanging-extra-move": (
        "p8-knight",
        _P.LEAVES_PIECE_HANGING,
        lambda c: (_move(c), MoveClaimEntity(ChessMove("a7a6"), _move(c).position_id), *_pieces(c)),
    ),
    "hanging-missing-piece": ("p8-knight", _P.LEAVES_PIECE_HANGING, lambda c: (_move(c),)),
    "hanging-extra-piece": (
        "p8-knight",
        _P.LEAVES_PIECE_HANGING,
        lambda c: (*c.objects, _base_piece(c, Color.WHITE, PieceType.KING, "e1")),
    ),
    "defender-extra-piece": (
        "p8-defender",
        _P.REMOVES_DEFENDER,
        lambda c: (*c.objects, _base_piece(c, Color.WHITE, PieceType.KING, "e1")),
    ),
    "fork-two-pieces": ("p8-fork", _P.ALLOWS_FORK, lambda c: (_move(c), *_pieces(c)[:2])),
    "mate-extra-piece": (
        "p8-exact-mate",
        _P.ALLOWS_CHECKMATE,
        lambda c: (*c.objects, _base_piece(c, Color.BLACK, PieceType.KING, "g8")),
    ),
    "engine-mate-missing-punishment": (
        "p8-engine-mate",
        _P.ALLOWS_CHECKMATE,
        lambda c: tuple(_pieces(c)),
    ),
    "material-punishment-base-frame": (
        "p8-knight",
        _P.ALLOWS_MATERIAL_LOSS,
        lambda c: (MoveClaimEntity(_move(c).move, c.base_position_id), *_pieces(c)),
    ),
    "forces-response-base-frame": (
        "strong-forces",
        _P.FORCES_RESPONSE,
        lambda c: (MoveClaimEntity(_move(c).move, c.base_position_id), *_pieces(c)),
    ),
    "forces-missing-response": ("strong-forces", _P.FORCES_RESPONSE, lambda c: tuple(_pieces(c))),
    "forces-missing-piece": ("strong-forces", _P.FORCES_RESPONSE, lambda c: (_move(c),)),
    "delivers-extra-move": (
        "strong-exact_mate",
        _P.DELIVERS_CHECKMATE,
        lambda c: (MoveClaimEntity(ChessMove("h8g8"), AFTER), *c.objects),
    ),
    "leads-extra-piece": (
        "strong-direct_mate",
        _P.LEADS_TO_MATE,
        lambda c: (*c.objects, _base_piece(c, Color.WHITE, PieceType.QUEEN, "f1")),
    ),
    "wins-missing-piece": ("strong-direct_material", _P.WINS_MATERIAL, lambda c: ()),
    "tested-mate-q-base-frame": (
        "strong-ignored_mate",
        _P.THREATENS_MATE_IF_IGNORED,
        lambda c: (MoveClaimEntity(_move(c).move, c.base_position_id), *_pieces(c)),
    ),
    "tested-material-q-base-frame": (
        "strong-ignored_material",
        _P.THREATENS_MATERIAL_IF_IGNORED,
        lambda c: (MoveClaimEntity(_move(c).move, c.base_position_id), *_pieces(c)),
    ),
    "tested-missing-q": (
        "strong-ignored_mate",
        _P.THREATENS_MATE_IF_IGNORED,
        lambda c: tuple(_pieces(c)),
    ),
    "preservation-alternative-after-frame": (
        "pres-mate_all",
        _P.AVOIDS_REPRESENTATIVE_MATE_FAILURE,
        lambda c: (_after(_move(c)), _move(c, 1), *_pieces(c)),
    ),
    "preservation-three-alternatives": (
        "pres-mate_all",
        _P.AVOIDS_REPRESENTATIVE_MATE_FAILURE,
        lambda c: (
            _move(c),
            _move(c, 1),
            MoveClaimEntity(ChessMove("d1c1"), c.base_position_id),
            *_pieces(c),
        ),
    ),
    "preservation-missing-alternatives": (
        "pres-material_all",
        _P.AVOIDS_REPRESENTATIVE_MATERIAL_LOSS,
        lambda c: tuple(_pieces(c)),
    ),
    "preservation-mate-extra-piece": (
        "pres-mate_all",
        _P.AVOIDS_REPRESENTATIVE_MATE_FAILURE,
        lambda c: (*c.objects, _base_piece(c, Color.WHITE, PieceType.ROOK, "d1")),
    ),
    "piece-not-base-frame": (
        "p8-knight",
        _P.LEAVES_PIECE_HANGING,
        lambda c: (_move(c), _reframed_piece(_pieces(c)[0], at_position_id=AFTER)),
    ),
    "piece-current-square": (
        "p8-knight",
        _P.LEAVES_PIECE_HANGING,
        lambda c: (_move(c), _reframed_piece(_pieces(c)[0], current_square="e4")),
    ),
    "piece-current-type": (
        "p8-knight",
        _P.LEAVES_PIECE_HANGING,
        lambda c: (_move(c), _reframed_piece(_pieces(c)[0], current_piece_type=PieceType.BISHOP)),
    ),
    "unrendered-piece-not-base-frame": (
        "p8-fork",
        _P.ALLOWS_FORK,
        lambda c: (
            _move(c),
            *_pieces(c)[:-1],
            _reframed_piece(_pieces(c)[-1], current_square="a1"),
        ),
    ),
    "side-object": (
        "p8-exact-mate",
        _P.ALLOWS_CHECKMATE,
        lambda c: (*c.objects, SideClaimEntity(Color.WHITE)),
    ),
}


@pytest.mark.parametrize("name", sorted(SIGNATURE_TAMPERS))
def test_p12_own_signature_gate_rejects_malformed_objects(name):
    fixture, predicate, objects = SIGNATURE_TAMPERS[name]
    _, claim = _claim(fixture, predicate)
    render_claim(claim)  # the untouched claim renders
    synthetic = tamper(replace(claim), objects=objects(claim))
    with pytest.raises(ExplanationRenderError):
        render_claim(synthetic)


@pytest.mark.parametrize("name", sorted(SIGNATURE_TAMPERS))
def test_malformed_package_never_gets_prose(name):
    fixture, predicate, objects = SIGNATURE_TAMPERS[name]
    graph, claim = _claim(fixture, predicate)
    selection = ExplanationSelector().select(graph)
    tamper(claim, objects=objects(claim))
    with pytest.raises(ExplanationRenderError):
        _render(graph, selection)


@pytest.mark.parametrize("name", sorted(SIGNATURE_TAMPERS))
def test_p12_signature_gate_holds_even_if_p11_were_bypassed(name, monkeypatch):
    fixture, predicate, objects = SIGNATURE_TAMPERS[name]
    graph, claim = _claim(fixture, predicate)
    selection = ExplanationSelector().select(graph)
    tamper(claim, objects=objects(claim))
    monkeypatch.setattr(ExplanationSelectionValidator, "validate", lambda self, g, s: s)
    if claim.claim_id not in selection.selected_claim_ids:
        selection = ExplanationSelection(graph.base_position_id, (claim.claim_id,))
    with pytest.raises(ExplanationRenderError):
        _render(graph, selection)


def test_subject_must_be_a_base_frame_move():
    _, claim = _claim("p8-knight", _P.LEAVES_PIECE_HANGING)
    moved = tamper(replace(claim), subject=MoveClaimEntity(claim.subject.move, AFTER))
    with pytest.raises(ExplanationRenderError, match="subject"):
        render_claim(moved)
    piece = tamper(replace(claim), subject=_pieces(claim)[0])
    with pytest.raises(ExplanationRenderError, match="subject"):
        render_claim(piece)


# ---- B. closed rule table -----------------------------------------------------------------------


def _all_forms():
    return [(p, c, s) for p in ClaimPredicate for c in ClaimConfidence for s in ClaimScope]


def test_every_non_frozen_form_fails_closed():
    _, base = _claim("p8-exact-mate", _P.ALLOWS_CHECKMATE)
    rejected = 0
    for predicate, confidence, scope in _all_forms():
        if (predicate, confidence, scope) in RENDER_RULES:
            continue
        claim = tamper(replace(base), predicate=predicate, confidence=confidence, scope=scope)
        with pytest.raises(ExplanationRenderError, match="no frozen render rule"):
            render_claim(claim)
        rejected += 1
    assert rejected == 13 * 3 * 3 - 14


@pytest.mark.parametrize("predicate", list(ClaimPredicate))
def test_every_forced_form_fails_closed(predicate):
    _, base = _claim("p8-exact-mate", _P.ALLOWS_CHECKMATE)
    for scope in ClaimScope:
        claim = tamper(replace(base), predicate=predicate, confidence=_C.FORCED, scope=scope)
        with pytest.raises(ExplanationRenderError):
            render_claim(claim)


@pytest.mark.parametrize(
    "field,value",
    [
        ("predicate", "allows_checkmate"),
        ("confidence", "exact"),
        ("scope", "local"),
    ],
)
def test_plain_string_forms_never_hash_match_the_rule_table(field, value):
    _, base = _claim("p8-exact-mate", _P.ALLOWS_CHECKMATE)
    claim = tamper(replace(base), **{field: value})
    with pytest.raises(ExplanationRenderError, match="exact P10"):
        render_claim(claim)


def test_fork_rule_can_never_name_pieces():
    rule = RENDER_RULES[(_P.ALLOWS_FORK, _C.ENGINE_VERIFIED, _S.LOCAL)]
    assert rule.template == "Move {move} allows a fork."


# ---- C. trust boundary --------------------------------------------------------------------------


def _relation(graph):
    return ExplanationRelation(
        "rel_001", graph.base_position_id, "cl_001", ExplanationRelationKind.CAUSES, "cl_002", ()
    )


def _foreign_selection(graph, selection):
    bundle = p8.evidence(p8.only_kind(p8.knight(), p8.Kind.MATERIAL_LOSS_LINE))
    other = GraphBuilder().build(bundle, p8.claims(bundle))
    return graph, ExplanationSelector().select(other)


def _claim_tamper(**changes):
    def attack(graph, selection):
        tamper(graph.claims[0], **changes)
        return graph, selection

    return attack


TRUST_ATTACKS = {
    "graph-none": ("p8-knight", lambda g, s: (None, s), ExplanationGraphError),
    "selection-none": ("p8-knight", lambda g, s: (g, None), ExplanationSelectionError),
    "graph-wrong-type": ("p8-knight", lambda g, s: (s, s), ExplanationGraphError),
    "tampered-claim-scope": (
        "pres-mate_all",
        _claim_tamper(scope=_S.LOCAL),
        ExplanationGraphError,
    ),
    "tampered-claim-forced": (
        "p8-exact-mate",
        _claim_tamper(confidence=_C.FORCED),
        ExplanationGraphError,
    ),
    "tampered-claim-predicate": (
        "strong-ignored_mate",
        _claim_tamper(predicate=_P.LEADS_TO_MATE),
        ExplanationGraphError,
    ),
    "stale-foreign-selection": ("p8-knight", _foreign_selection, ExplanationSelectionError),
    "relation-injection": (
        "p8-knight",
        lambda g, s: (replace(g, relations=(_relation(g),)), s),
        ExplanationGraphError,
    ),
    "selected-relation": (
        "p8-knight",
        lambda g, s: (g, replace(s, selected_relation_ids=("rel_001",))),
        ExplanationSelectionError,
    ),
    "reordered-selection": (
        "p8-knight",
        lambda g, s: (g, replace(s, selected_claim_ids=s.selected_claim_ids[::-1])),
        ExplanationSelectionError,
    ),
    "missing-selection-claim": (
        "p8-knight",
        lambda g, s: (g, replace(s, selected_claim_ids=s.selected_claim_ids[:1])),
        ExplanationSelectionError,
    ),
    "extra-selection-claim": (
        "p8-defender",
        lambda g, s: (g, replace(s, selected_claim_ids=(*s.selected_claim_ids, "cl_002"))),
        ExplanationSelectionError,
    ),
    "foreign-base-selection": (
        "p8-knight",
        lambda g, s: (g, replace(s, base_position_id="pos_other")),
        ExplanationSelectionError,
    ),
    "empty-selection-for-non-empty-graph": (
        "p8-knight",
        lambda g, s: (g, replace(s, selected_claim_ids=())),
        ExplanationSelectionError,
    ),
    "selection-for-empty-graph": (
        "p8-knight",
        lambda g, s: (empty_pair(g.base_position_id)[0], s),
        ExplanationSelectionError,
    ),
}


@pytest.mark.parametrize("name", sorted(TRUST_ATTACKS))
def test_trust_boundary_attacks_fail_before_prose(name, monkeypatch):
    fixture, attack, cause = TRUST_ATTACKS[name]
    graph, selection = pair(fixture)
    rendered_claims = []
    original = renderer_module.render_claim
    monkeypatch.setattr(
        renderer_module,
        "render_claim",
        lambda claim: rendered_claims.append(claim) or original(claim),
    )
    with pytest.raises(ExplanationRenderError) as info:
        _render(*attack(graph, selection))
    assert type(info.value.__cause__) is cause  # the original P11 failure is chained
    assert rendered_claims == []  # validation finished before any claim was read


def test_p10_failures_stay_reachable_through_the_chain():
    graph, selection = pair("p8-knight")
    tamper(graph.claims[0], evidence_ids=graph.claims[0].evidence_ids[:-1])
    with pytest.raises(ExplanationRenderError) as info:
        _render(graph, selection)
    p11 = info.value.__cause__
    assert type(p11) is ExplanationGraphError and p11.__cause__ is not None


def test_validation_runs_before_resolution(monkeypatch):
    graph, selection = pair("p8-knight")
    calls = []
    original = ExplanationSelectionValidator.validate

    def spy(self, g, s):
        calls.append("validate")
        return original(self, g, s)

    monkeypatch.setattr(ExplanationSelectionValidator, "validate", spy)
    monkeypatch.setattr(
        renderer_module,
        "render_claim",
        lambda claim: calls.append(claim.claim_id) or GOLDEN["p8-knight"][len(calls) - 2],
    )
    _render(graph, selection)
    assert calls == ["validate", *selection.selected_claim_ids]


@pytest.mark.parametrize("ids", [("cl_009",), ("cl_002", "cl_001", "cl_007")])
def test_unresolvable_ids_fail_closed_even_without_p11(ids, monkeypatch):
    graph, _ = pair("p8-knight")
    monkeypatch.setattr(ExplanationSelectionValidator, "validate", lambda self, g, s: s)
    with pytest.raises(ExplanationRenderError, match="does not resolve"):
        _render(graph, ExplanationSelection(graph.base_position_id, ids))


def test_relation_selection_fails_closed_even_without_p11(monkeypatch):
    graph, selection = pair("p8-knight")
    monkeypatch.setattr(ExplanationSelectionValidator, "validate", lambda self, g, s: s)
    with pytest.raises(ExplanationRenderError, match="no relation rule"):
        _render(graph, replace(selection, selected_relation_ids=("rel_001",)))


def test_manual_graph_is_still_revalidated():
    graph, selection = pair("p8-knight")
    manual = ExplanationGraph(graph.base_position_id, graph.evidence, graph.claims[::-1], ())
    with pytest.raises(ExplanationRenderError) as info:
        _render(manual, selection)
    assert type(info.value.__cause__) is ExplanationGraphError


# ---- D. SAN gate --------------------------------------------------------------------------------

_SANS = ("Re1#", "Nc2+", "dxe4", "Rxd4", "O-O", "Nbd2")


def _with_san(entity, index):
    if type(entity) is MoveClaimEntity:
        return MoveClaimEntity(
            ChessMove(entity.move.uci, _SANS[index % len(_SANS)]), entity.position_id
        )
    return entity


def _san_poisoned(graph):
    for i, claim in enumerate(graph.claims):
        tamper(
            claim,
            subject=_with_san(claim.subject, i),
            objects=tuple(_with_san(o, i + j + 1) for j, o in enumerate(claim.objects)),
        )
    return graph


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_san_changes_never_change_the_output(name):
    graph, selection = pair(name)
    before = signature(_render(graph, selection))
    _san_poisoned(graph)
    assert {o.move.san for c in graph.claims for o in (c.subject,)} <= set(_SANS)
    after = _render(graph, selection)
    assert signature(after) == before
    for san in _SANS:
        assert san not in after.text


# ---- E. renderer source guard -------------------------------------------------------------------

ALLOWED_IMPORTS = {
    "__future__",
    "collections.abc",
    "dataclasses",
    "enum",
    "calliope.domain.chess",
    "calliope.domain.explanation",
    "calliope.domain.explanation.render",
    "calliope.errors",
    "calliope.services.explanation.selector",
}
FORBIDDEN_NAMES = {
    "EvidenceRecord",
    "EvidenceBundle",
    "EvidenceGroup",
    "BoardFactEvidence",
    "EngineEvidence",
    "VariationEvidence",
    "CounterfactualEvidence",
    "MotifEvidence",
    "EngineAnalysis",
    "EngineScore",
    "StockfishAdapter",
    "PythonChessAdapter",
    "CounterfactualAnalyzer",
    "BoardDelta",
    "PositionFacts",
    "BadMoveExplanationResult",
    "GoodMoveExplanationResult",
    "BadMoveCauseResult",
    "GoodMoveBenefitResult",
    "SelectionFamily",
    "priority_tier",
}
FORBIDDEN_ATTRIBUTES = {
    "san",
    "evidence",
    "evidence_ids",
    "groups",
    "relations",
    "engine_analysis",
    "score",
    "pv",
    "importance",
    "required_probe_results",
}


def _tree():
    return ast.parse(RENDERER_SOURCE.read_text(encoding="utf-8"))


def test_renderer_imports_only_presentation_dependencies():
    imported = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            imported.add(node.module or "")
    assert imported <= ALLOWED_IMPORTS, imported - ALLOWED_IMPORTS


def test_renderer_never_names_evidence_engine_or_raw_analysis_types():
    names = {n.id for n in ast.walk(_tree()) if isinstance(n, ast.Name)}
    names |= {
        alias.asname or alias.name
        for n in ast.walk(_tree())
        if isinstance(n, ast.ImportFrom)
        for alias in n.names
    }
    assert not names & FORBIDDEN_NAMES, names & FORBIDDEN_NAMES


def test_renderer_never_reads_san_evidence_scores_or_relations():
    attributes = {n.attr for n in ast.walk(_tree()) if isinstance(n, ast.Attribute)}
    assert not attributes & FORBIDDEN_ATTRIBUTES, attributes & FORBIDDEN_ATTRIBUTES
    assert "selected_relation_ids" in attributes  # only the selection's own empty tuple


# ---- F. unselected claim isolation --------------------------------------------------------------


def test_unselected_claim_does_not_change_any_sentence():
    full = _render(*pair("p8-defender"))
    graph, selection = pair("p8-defender")
    (unselected,) = [c for c in graph.claims if c.claim_id not in selection.selected_claim_ids]
    assert unselected.predicate is _P.REMOVES_DEFENDER

    bundle = p8.evidence(defender_without_unselected_claim())
    reduced = GraphBuilder().build(bundle, p8.claims(bundle))
    rendered = _render(reduced, ExplanationSelector().select(reduced))
    assert {c.predicate for c in reduced.claims} == {
        _P.LEAVES_PIECE_HANGING,
        _P.ALLOWS_MATERIAL_LOSS,
    }
    assert rendered.sentences == full.sentences  # the unselected claim contributed nothing


def test_unselected_claim_presentation_metadata_is_ignored():
    graph, selection = pair("p8-defender")
    before = signature(_render(graph, selection))
    (unselected,) = [c for c in graph.claims if c.claim_id not in selection.selected_claim_ids]
    tamper(
        unselected,
        subject=_with_san(unselected.subject, 0),
        objects=tuple(_with_san(o, 1) for o in unselected.objects),
    )
    assert signature(_render(graph, selection)) == before


def test_only_selected_claims_reach_the_rule_table(monkeypatch):
    for name in CORPUS:
        graph, selection = pair(name)
        seen = []
        original = renderer_module.render_claim
        monkeypatch.setattr(
            renderer_module,
            "render_claim",
            lambda c, seen=seen, original=original: seen.append(c) or original(c),
        )
        _render(graph, selection)
        assert [c.claim_id for c in seen] == list(selection.selected_claim_ids)
        monkeypatch.undo()


# ---- G. render mutation oracle ------------------------------------------------------------------


def render_violations() -> list:
    """Independent oracle: golden wording, provenance, scope phrases, signatures, SAN, closure."""

    violations = []
    for name in sorted(CORPUS):
        graph, selection = pair(name)
        try:
            rendered = _render(graph, selection)
        except Exception as exc:  # noqa: BLE001 - the oracle reports, never raises
            violations.append(("raised", name, repr(exc)))
            continue
        if rendered.sentences != GOLDEN[name]:
            violations.append(("golden", name, rendered.sentences))
        if (
            rendered.used_claim_ids != selection.selected_claim_ids
            or len(rendered.sentences) != len(selection.selected_claim_ids)
            or rendered.text != " ".join(GOLDEN[name])
        ):
            violations.append(("provenance", name, rendered))
        poisoned = _render(_san_poisoned(graph), selection)
        if signature(poisoned) != signature(rendered):
            violations.append(("san", name, poisoned.text))
    empty = _render(*empty_pair())
    if signature(empty) != (NO_VERIFIED_EXPLANATION, (), ()):
        violations.append(("empty", empty))
    for name in sorted(SIGNATURE_TAMPERS):
        fixture, predicate, objects = SIGNATURE_TAMPERS[name]
        _, claim = _claim(fixture, predicate)
        try:
            render_claim(tamper(replace(claim), objects=objects(claim)))
            violations.append(("signature", name))
        except ExplanationRenderError:
            pass
    _, base = _claim("p8-exact-mate", _P.ALLOWS_CHECKMATE)
    for predicate in ClaimPredicate:
        for confidence in ClaimConfidence:
            for scope in ClaimScope:
                if (predicate, confidence, scope) in FROZEN_FORMS:
                    continue
                claim = tamper(
                    replace(base), predicate=predicate, confidence=confidence, scope=scope
                )
                try:
                    render_claim(claim)
                    violations.append(("fallback", predicate, confidence, scope))
                except ExplanationRenderError:
                    pass
    return violations


FROZEN_FORMS = frozenset(
    {
        (_P.LEAVES_PIECE_HANGING, _C.ENGINE_VERIFIED, _S.LOCAL),
        (_P.REMOVES_DEFENDER, _C.ENGINE_VERIFIED, _S.LOCAL),
        (_P.ALLOWS_FORK, _C.ENGINE_VERIFIED, _S.LOCAL),
        (_P.ALLOWS_CHECKMATE, _C.EXACT, _S.LOCAL),
        (_P.ALLOWS_CHECKMATE, _C.ENGINE_VERIFIED, _S.LOCAL),
        (_P.ALLOWS_MATERIAL_LOSS, _C.ENGINE_VERIFIED, _S.LOCAL),
        (_P.FORCES_RESPONSE, _C.EXACT, _S.LOCAL),
        (_P.DELIVERS_CHECKMATE, _C.EXACT, _S.LOCAL),
        (_P.LEADS_TO_MATE, _C.ENGINE_VERIFIED, _S.LOCAL),
        (_P.WINS_MATERIAL, _C.ENGINE_VERIFIED, _S.LOCAL),
        (_P.THREATENS_MATE_IF_IGNORED, _C.ENGINE_VERIFIED, _S.TESTED_RESPONSE),
        (_P.THREATENS_MATERIAL_IF_IGNORED, _C.ENGINE_VERIFIED, _S.TESTED_RESPONSE),
        (
            _P.AVOIDS_REPRESENTATIVE_MATE_FAILURE,
            _C.ENGINE_VERIFIED,
            _S.REPRESENTATIVE_ALTERNATIVES,
        ),
        (
            _P.AVOIDS_REPRESENTATIVE_MATERIAL_LOSS,
            _C.ENGINE_VERIFIED,
            _S.REPRESENTATIVE_ALTERNATIVES,
        ),
    }
)


def test_render_oracle_accepts_current_production():
    assert render_violations() == []


def _retemplate(key, template):
    rules = dict(RENDER_RULES)
    rules[key] = replace(rules[key], template=template)
    return rules


class _GenericFallback(dict):
    def get(self, key, default=None):
        rule = super().get(key)
        if rule is not None:
            return rule
        return renderer_module.RenderRule(
            0, 99, renderer_module.MoveFrame.AFTER_MOVE, 0, None, "Move {move} is explained."
        )


def _relaxed_counts():
    return {
        key: replace(rule, min_moves=0, max_moves=99, min_pieces=0, max_pieces=None)
        for key, rule in RENDER_RULES.items()
    }


def _classify_only(claim, rule):
    moves = [o for o in claim.objects if isinstance(o, MoveClaimEntity)]
    pieces = [o for o in claim.objects if isinstance(o, PieceClaimEntity)]
    return moves, pieces


def _forged(text, sentences, ids):
    value = object.__new__(RenderedCommentary)
    for field, item in (("text", text), ("sentences", sentences), ("used_claim_ids", ids)):
        object.__setattr__(value, field, item)
    return value


_ORIGINAL_RENDER = DeterministicExplanationRenderer.render


def _merging_render(self, graph, selection):
    rendered = _ORIGINAL_RENDER(self, graph, selection)
    if len(rendered.sentences) < 2:
        return rendered
    first, second = rendered.sentences[:2]
    merged = f"{first[:-1]} because {second[0].lower()}{second[1:]}"
    return _forged(merged, (merged, *rendered.sentences[2:]), rendered.used_claim_ids)


def _sorted_ids_render(self, graph, selection):
    rendered = _ORIGINAL_RENDER(self, graph, selection)
    return _forged(rendered.text, rendered.sentences, tuple(sorted(rendered.used_claim_ids)))


def _unselected_render(self, graph, selection):
    rendered = _ORIGINAL_RENDER(self, graph, selection)
    extra = tuple(
        renderer_module.render_claim(c)
        for c in graph.claims
        if c.claim_id not in selection.selected_claim_ids
    )
    sentences = (*rendered.sentences, *extra)
    return _forged(" ".join(sentences), sentences, rendered.used_claim_ids)


EV = _C.ENGINE_VERIFIED
_TESTED_MATE = (_P.THREATENS_MATE_IF_IGNORED, EV, _S.TESTED_RESPONSE)
_PRES_MATE = (_P.AVOIDS_REPRESENTATIVE_MATE_FAILURE, EV, _S.REPRESENTATIVE_ALTERNATIVES)
RENDER_MUTATIONS = {
    "tested-q-old-wording": (
        "RENDER_RULES",
        lambda: _retemplate(
            _TESTED_MATE, "Move {move} threatens mate if tested response {response} is not played."
        ),
    ),
    "fork-against-pieces": (
        "RENDER_RULES",
        lambda: _retemplate(
            (_P.ALLOWS_FORK, EV, _S.LOCAL), "Move {move} allows a fork against {pieces}."
        ),
    ),
    "engine-verified-dropped": (
        "RENDER_RULES",
        lambda: _retemplate(
            (_P.ALLOWS_CHECKMATE, EV, _S.LOCAL), "Move {move} allows a verified mating line."
        ),
    ),
    "preservation-scope-dropped": (
        "RENDER_RULES",
        lambda: _retemplate(
            _PRES_MATE, "Move {move} avoids the mate failure seen after {alternatives}."
        ),
    ),
    "generic-fallback": ("RENDER_RULES", lambda: _GenericFallback(RENDER_RULES)),
    "signature-removed": ("check_signature", lambda: _classify_only),
    "signature-counts-relaxed": ("RENDER_RULES", _relaxed_counts),
    "san-used": ("_uci", lambda: lambda move: move.move.san or move.move.uci),
    "claims-merged": ("render", lambda: _merging_render),
    "provenance-order-ignored": ("render", lambda: _sorted_ids_render),
    "unselected-claim-added": ("render", lambda: _unselected_render),
}


@pytest.mark.parametrize("mutation", sorted(RENDER_MUTATIONS))
def test_render_mutation_is_caught_by_oracle(mutation, monkeypatch):
    target, make = RENDER_MUTATIONS[mutation]
    if target == "render":
        monkeypatch.setattr(DeterministicExplanationRenderer, "render", make())
    else:
        monkeypatch.setattr(renderer_module, target, make())
    assert render_violations()


# ---- H. determinism -----------------------------------------------------------------------------

_RENDER_SCRIPT = """
import sys
sys.path[:0] = [{src!r}, {tests!r}]
from _p12_render_corpus import CORPUS, render, empty_pair
from calliope.services.explanation import DeterministicExplanationRenderer
for name in sorted(CORPUS):
    r = render(name)
    print(name, repr(r.text), r.sentences, r.used_claim_ids)
print(DeterministicExplanationRenderer().render(*empty_pair()))
"""


def test_render_output_is_independent_of_hash_seed():
    script = _RENDER_SCRIPT.format(
        src=str(REPO / "src"), tests=str(REPO / "tests/unit/services/explanation")
    )
    outputs = set()
    for seed in ("0", "4242"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        done = subprocess.run(
            [sys.executable, "-c", script], env=env, capture_output=True, text=True, check=True
        )
        outputs.add(done.stdout)
    assert len(outputs) == 1 and outputs.pop().count("\n") == len(CORPUS) + 1


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_render_output_is_independent_of_repetition_and_rebuilds(name):
    signatures = {signature(_render(*pair(name))) for _ in range(3)}
    graph, selection = pair(name)
    renderer = DeterministicExplanationRenderer()
    signatures |= {signature(renderer.render(graph, selection)) for _ in range(3)}
    assert signatures == {(" ".join(GOLDEN[name]), GOLDEN[name], selection.selected_claim_ids)}


def test_render_output_is_independent_of_engine_mate_distance():
    signatures = set()
    for distance in (2, 5, 9):
        bundle = p8.evidence(p8.engine_mate(EngineScore.forced_mate(Color.BLACK, distance)))
        graph = GraphBuilder().build(bundle, p8.claims(bundle))
        signatures.add(signature(_render(graph, ExplanationSelector().select(graph))))
    assert signatures == {
        (
            "Move d1d7 allows an engine-verified mating line.",
            ("Move d1d7 allows an engine-verified mating line.",),
            ("cl_001",),
        )
    }


# ---- I. no engine / rules / P7 at P12 runtime ---------------------------------------------------


def test_p12_runs_with_engine_rules_and_p7_disabled(monkeypatch):
    graphs = {name: built(name) for name in CORPUS}  # P8/P9/P10 work happens before

    def forbidden(*args, **kwargs):
        raise AssertionError("P11/P12 must not call engines, chess rules or P7")

    for cls in (PythonChessAdapter, StockfishAdapter, CounterfactualAnalyzer):
        for attribute in dir(cls):
            if not attribute.startswith("_") and callable(getattr(cls, attribute)):
                monkeypatch.setattr(cls, attribute, forbidden)
    for name, graph in graphs.items():
        rendered = _render(graph, ExplanationSelector().select(graph))
        assert rendered.sentences == GOLDEN[name]


def test_claims_are_unchanged_by_rendering():
    for name in CORPUS:
        graph, selection = pair(name)
        before = repr(graph.claims)
        _render(graph, selection)
        assert repr(graph.claims) == before
        assert all(type(c) is ExplanationClaim and c.importance is None for c in graph.claims)
