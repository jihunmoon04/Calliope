import ast
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis import (
    BadMoveCauseKind,
    BadMoveCauseResult,
    BadMoveCauseStatus,
    BadMoveExplanationResult,
    BadMoveExplanationStatus,
    BasePieceRef,
    MateEvidenceLevel,
    MaterialLineEvidence,
    ProbeKind,
    ProbeResult,
    TerminalKind,
    TerminalOutcome,
)
from calliope.domain.chess import ChessMove, Color, PieceType
from calliope.domain.engine import (
    EngineAnalysis,
    EngineIdentity,
    EngineLine,
    EngineScore,
    MoveJudgement,
    MoveQuality,
)
from calliope.domain.explanation import (
    EVIDENCE_RECORD_TYPE_ORDER,
    BoardFactEvidence,
    CounterfactualEvidence,
    EngineEvidence,
    EvidenceBundle,
    EvidenceForm,
    EvidenceSourceFamily,
    MotifEvidence,
    MoveClaimEntity,
    VariationEvidence,
    base_frame_piece_entity,
    base_piece_sort_key,
    evidence_record_type_rank,
)
from calliope.errors import ExplanationEvidenceError
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.counterfactual.analyzer import DEFAULT_SETTINGS
from calliope.services.explanation import BadMoveExplainer
from calliope.services.explanation import evidence_builder as evidence_builder_module
from calliope.services.explanation.evidence_builder import EvidenceBuilder
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.tactics import TacticalDetector

# ---- real P8 harness (mirrors test_bad_move_causes.py) ----------------------------------------

rules = PythonChessAdapter()
facts = PositionFactExtractor(rules)
deltas = BoardDeltaAnalyzer(rules, facts)
detector = TacticalDetector()

W, B = Color.WHITE, Color.BLACK
cp = EngineScore.cp
mate = EngineScore.forced_mate
Kind = BadMoveCauseKind
S = BadMoveCauseStatus

KNIGHT = "4k3/8/8/3p4/8/2N5/8/4K3 w - - 0 1"
DEFENDER = "3rk3/8/8/8/3N4/2P5/8/4K3 w - - 0 1"
FORK = "4k3/8/8/8/1n6/3B4/8/R3K3 w - - 0 1"
BACK_RANK = "4r1k1/8/8/8/8/8/5PPP/3R2K1 w - - 0 1"


def after(fen, *ucis):
    position = rules.position_from_fen(fen)
    for uci in ucis:
        position = rules.apply_move(position, rules.legal_move_from_uci(position, uci))
    return position


@dataclass
class LineEngine:
    lines: dict
    forced: dict = field(default_factory=dict)

    def analyze(self, position, settings, root_moves=None):
        if root_moves:
            pv, score = self.forced.get(position.position_id, ((root_moves[0].uci,), cp(0)))
        else:
            pv, score = self.lines[position.position_id]
        moves = tuple(ChessMove(uci) for uci in pv)
        return EngineAnalysis(
            position_id=position.position_id,
            engine=EngineIdentity("Fake", "1"),
            settings=settings,
            lines=(EngineLine(1, moves[0], score, moves),),
        )


def explain(fen, played, best, actual, comparator, same=None) -> BadMoveExplanationResult:
    base = rules.position_from_fen(fen)
    lines = {after(fen, played).position_id: actual, after(fen, best).position_id: comparator}
    forced = {after(fen, best).position_id: same} if same else {}
    p7 = CounterfactualAnalyzer(rules, LineEngine(lines, forced), rules, rules)
    explainer = BadMoveExplainer(rules, facts, deltas, rules, detector, p7)
    judgement = MoveJudgement(
        position_id=base.position_id,
        mover=base.side_to_move,
        move=ChessMove(played),
        best_move=ChessMove(best),
        quality=MoveQuality.BLUNDER,
        rank=None,
        best_score=cp(0),
        played_score=cp(-300),
        cp_loss=300,
        expected_score_loss=0.3,
    )
    return explainer.explain(base, judgement.move, judgement, DEFAULT_SETTINGS)


def knight():
    return explain(
        KNIGHT,
        "c3e4",
        "c3b5",
        (("d5e4", "e1d2", "e8d7"), cp(-300)),
        (("e8d7", "e1d2", "d7e6"), cp(0)),
    )


def defender():
    return explain(
        DEFENDER,
        "c3c4",
        "e1e2",
        (("d8d4", "e1e2", "d4d5"), cp(-300)),
        (("e8e7", "e2e3", "e7f7"), cp(0)),
        (("d8d4", "c3d4", "e8e7", "e2e3"), cp(0)),
    )


def fork():
    return explain(
        FORK,
        "d3e4",
        "e1f1",
        (("b4c2", "e1d2", "c2a1", "e4d3", "e8e7"), cp(-500)),
        (("e8e7", "f1e2", "e7f7"), cp(0)),
        (("b4c2", "d3c2", "e8e7", "f1e2"), cp(0)),
    )


def exact_mate():
    return explain(
        BACK_RANK, "d1d7", "h2h3", (("e8e1",), mate(B, 1)), (("g8f8", "g1h2", "f8e7"), cp(0))
    )


def engine_mate():
    return explain(
        BACK_RANK,
        "d1d7",
        "h2h3",
        (("g8f8", "d7a7", "e8e1"), mate(B, 2)),
        (("g8f8", "g1h2", "f8e7"), cp(0)),
    )


def build(result) -> EvidenceBundle:
    return EvidenceBuilder().build_bad_move(result)


def cause_of(result, kind) -> BadMoveCauseResult:
    (cause,) = [c for c in result.causes if c.kind is kind]
    return cause


def group_of(bundle, kind):
    (group,) = [g for g in bundle.groups if g.source_kind is kind]
    return group


def records_of(bundle, group):
    by_id = {record.evidence_id: record for record in bundle.evidence}
    return [by_id[evidence_id] for evidence_id in group.evidence_ids]


def only(records, record_type):
    (record,) = [r for r in records if type(r) is record_type]
    return record


def with_cause(result, cause, **changes) -> BadMoveExplanationResult:
    """Rebuild the aggregate with one cause changed through validating constructors."""

    changed = replace(cause, **changes)
    causes = tuple(changed if c is cause else c for c in result.causes)
    return replace(result, causes=causes)


def single_supported(result, kind):
    """The aggregate reduced to one supported cause, for focused provenance tamper tests."""

    return replace(result, causes=(cause_of(result, kind),))


def tamper(value, **changes):
    """Bypass domain validation to simulate an incompatible value reaching the boundary."""

    for name, change in changes.items():
        object.__setattr__(value, name, change)
    return value


# ---- eligibility -------------------------------------------------------------------------------


def test_wrong_input_type_rejected():
    with pytest.raises(ExplanationEvidenceError, match="BadMoveExplanationResult"):
        EvidenceBuilder().build_bad_move(cause_of(knight(), Kind.NEWLY_HANGING_PIECE))


@pytest.mark.parametrize(
    ("status", "causes"),
    [
        (BadMoveExplanationStatus.NOT_APPLICABLE, ()),
        (BadMoveExplanationStatus.INCONCLUSIVE, ()),
    ],
)
def test_non_supported_parent_without_causes_is_empty(status, causes):
    result = replace(knight(), status=status, causes=causes)
    assert build(result) == EvidenceBundle(result.base_position_id, (), ())


def test_refuted_parent_is_empty():
    result = knight()
    refuted = tuple(replace(c, status=S.REFUTED) for c in result.causes)
    value = replace(result, status=BadMoveExplanationStatus.REFUTED, causes=refuted)
    assert build(value) == EvidenceBundle(result.base_position_id, (), ())


def test_inconclusive_parent_with_inconclusive_causes_is_empty():
    result = knight()
    pending = tuple(replace(c, status=S.INCONCLUSIVE) for c in result.causes)
    value = replace(result, status=BadMoveExplanationStatus.INCONCLUSIVE, causes=pending)
    assert build(value) == EvidenceBundle(result.base_position_id, (), ())


@pytest.mark.parametrize("sibling_status", [S.REFUTED, S.INCONCLUSIVE])
def test_supported_parent_keeps_only_supported_children(sibling_status):
    result = knight()
    material = cause_of(result, Kind.MATERIAL_LOSS_LINE)
    value = with_cause(result, material, status=sibling_status)
    bundle = build(value)
    assert [g.source_kind for g in bundle.groups] == [Kind.NEWLY_HANGING_PIECE]
    assert build(result).groups[0] == bundle.groups[0]


def test_real_supported_parent_contains_refuted_siblings_that_are_ignored():
    result = defender()
    statuses = {c.kind: c.status for c in result.causes}
    supported = [k for k, s in statuses.items() if s is S.SUPPORTED]
    assert [g.source_kind for g in build(result).groups] == sorted(supported, key=list(Kind).index)


# ---- all five causes ---------------------------------------------------------------------------


CASES = [
    (knight, Kind.NEWLY_HANGING_PIECE, (BasePieceRef(W, PieceType.KNIGHT, "c3"),)),
    (defender, Kind.REMOVED_DEFENDER, (BasePieceRef(W, PieceType.KNIGHT, "d4"),)),
    (
        fork,
        Kind.FORK_ALLOWED,
        (
            BasePieceRef(W, PieceType.ROOK, "a1"),
            BasePieceRef(W, PieceType.KING, "e1"),
            BasePieceRef(B, PieceType.KNIGHT, "b4"),
        ),
    ),
    (exact_mate, Kind.MATE_ALLOWED, (BasePieceRef(W, PieceType.KING, "g1"),)),
    (knight, Kind.MATERIAL_LOSS_LINE, (BasePieceRef(W, PieceType.KNIGHT, "c3"),)),
]


@pytest.mark.parametrize(("make", "kind", "subject"), CASES)
def test_every_p8_cause_kind_builds_complete_direct_evidence(make, kind, subject):
    result = make()
    cause = cause_of(result, kind)
    assert cause.status is S.SUPPORTED
    bundle = build(result)
    group = group_of(bundle, kind)
    records = records_of(bundle, group)

    assert group.source_family is EvidenceSourceFamily.BAD_MOVE_CAUSE
    assert group.source_subject == subject
    assert group.evidence_form is EvidenceForm.DIRECT
    assert group.played_move == MoveClaimEntity(cause.played_move, result.base_position_id)
    assert group.comparator_move == MoveClaimEntity(cause.comparator_move, result.base_position_id)
    assert group.required_probe_results is cause.probe_results
    assert group.representative_alternatives == group.failed_alternatives == ()
    assert group.mate_evidence_level is cause.mate_evidence_level
    assert group.replayed_pv_ends_in_checkmate is cause.replayed_pv_ends_in_checkmate

    expected_refs = sorted({*cause.subject, *cause.affected_pieces}, key=base_piece_sort_key)
    expected_pieces = tuple(
        base_frame_piece_entity(result.base_position_id, r) for r in expected_refs
    )
    board = only(records, BoardFactEvidence)
    assert board.pieces == expected_pieces
    for piece in board.pieces:
        assert piece.at_position_id == result.base_position_id
        assert piece.current_square == piece.base_ref.base_square
        assert piece.current_piece_type is piece.base_ref.piece_type
    assert board.board_deltas == cause.board_deltas
    assert board.sole_response is None and board.terminal is None

    counterfactual = records[-1]
    assert type(counterfactual) is CounterfactualEvidence
    assert counterfactual.probe_results is cause.probe_results
    assert counterfactual.form is EvidenceForm.DIRECT
    assert counterfactual.tested_response is None
    assert counterfactual.comparator_move == group.comparator_move
    assert counterfactual.equivalent_alternative_benefit is cause.comparator_has_equivalent_resource
    _assert_canonical_type_order(records)


def _assert_canonical_type_order(records):
    ranks = [evidence_record_type_rank(r) for r in records]
    assert ranks == sorted(ranks)
    assert type(records[0]) is BoardFactEvidence
    assert [type(r) for r in records].count(CounterfactualEvidence) == 1


def test_exact_immediate_mate_retains_exact_provenance_only():
    result = exact_mate()
    cause = cause_of(result, Kind.MATE_ALLOWED)
    bundle = build(result)
    group = group_of(bundle, Kind.MATE_ALLOWED)
    records = records_of(bundle, group)
    assert group.mate_evidence_level is MateEvidenceLevel.EXACT_IMMEDIATE
    assert group.replayed_pv_ends_in_checkmate is True
    motif = only(records, MotifEvidence)
    assert motif.candidates == cause.tactical_candidates
    assert {c.kind.value for c in motif.candidates} <= {"check", "checkmate"}
    actual = next(r for r in records if type(r) is VariationEvidence)
    assert actual.replayed_pv_ends_in_checkmate is True
    assert actual.board_deltas == cause.board_deltas
    assert not hasattr(group, "confidence")


def test_engine_line_mate_retains_engine_level():
    bundle = build(engine_mate())
    group = group_of(bundle, Kind.MATE_ALLOWED)
    assert group.mate_evidence_level is MateEvidenceLevel.ENGINE_LINE
    assert group.evidence_form is EvidenceForm.DIRECT


# ---- probe shape -------------------------------------------------------------------------------


def test_two_probe_sequence_accepted():
    cause = cause_of(knight(), Kind.NEWLY_HANGING_PIECE)
    kinds = [r.probe.kind for r in cause.probe_results]
    assert kinds == [ProbeKind.REFUTATION, ProbeKind.REFUTATION]
    assert build(knight()).groups[0].required_probe_results == cause.probe_results


def test_same_punishment_ignore_threat_accepted_and_stays_direct():
    result = defender()
    cause = cause_of(result, Kind.REMOVED_DEFENDER)
    third = cause.probe_results[2]
    assert third.probe.kind is ProbeKind.IGNORE_THREAT
    assert third.probe.intervention_move.uci == cause.comparator_move.uci
    assert third.probe.execution_move.uci == cause.punishment_move.uci

    bundle = build(result)
    group = group_of(bundle, Kind.REMOVED_DEFENDER)
    counterfactual = records_of(bundle, group)[-1]
    assert group.evidence_form is EvidenceForm.DIRECT
    assert counterfactual.form is EvidenceForm.DIRECT
    assert counterfactual.tested_response is None
    assert counterfactual.probe_results == cause.probe_results
    # response is the actual-line punishment, never the comparator-replay probe's move.
    assert group.response.position_id == cause.probe_results[0].analysis_position.position_id
    assert group.response.position_id != third.analysis_position.position_id


def _probe_case():
    result = single_supported(defender(), Kind.REMOVED_DEFENDER)
    return result, result.causes[0]


def _with_probe(result_probe, **probe_changes):
    return replace(result_probe, probe=replace(result_probe.probe, **probe_changes))


def _rebuild(result, cause, probes):
    return with_cause(result, cause, probe_results=probes, material_evidence=())


def _malformed_sequences():
    _, cause = _probe_case()
    actual, comparator, same = cause.probe_results
    wrong_move = ChessMove("e8d8")
    return {
        "ignore_not_final": (actual, same, comparator),
        "wrong_intervention": (actual, comparator, _with_probe(same, intervention_move=wrong_move)),
        "wrong_execution": (actual, comparator, _with_probe(same, execution_move=wrong_move)),
        "multiple_ignores": (actual, comparator, same, same),
        "missing_actual": (comparator, same),
        "missing_comparator": (actual, same),
        "duplicate_actual": (actual, actual, comparator),
        "duplicate_comparator": (actual, comparator, comparator),
        "fourth_probe": (actual, comparator, same, actual),
        "swapped_refutations": (comparator, actual),
        "only_actual": (actual,),
        "third_refutation": (actual, comparator, _with_probe(same, kind=ProbeKind.REFUTATION)),
    }


@pytest.mark.parametrize("name", sorted(_malformed_sequences()))
def test_malformed_probe_sequence_rejected(name):
    result, cause = _probe_case()
    with pytest.raises(ExplanationEvidenceError, match="P8"):
        build(_rebuild(result, cause, _malformed_sequences()[name]))


@pytest.mark.parametrize(("index", "label"), [(0, "actual"), (1, "comparator")])
def test_refutation_with_execution_move_rejected(index, label):
    result, cause = _probe_case()
    probes = list(cause.probe_results)
    assert probes[index].probe.execution_move is None
    probes[index] = _with_probe(probes[index], execution_move=cause.punishment_move)
    with pytest.raises(
        ExplanationEvidenceError,
        match=f"{label} REFUTATION probe must not carry an execution move",
    ):
        build(_rebuild(result, cause, tuple(probes)))


def test_ignore_threat_without_punishment_rejected():
    result, cause = _probe_case()
    with pytest.raises(ExplanationEvidenceError, match="requires a punishment"):
        build(with_cause(result, cause, punishment_move=None, material_evidence=()))


def test_probe_from_other_base_rejected():
    result, cause = _probe_case()
    other = rules.position_from_fen(KNIGHT)
    actual, comparator, same = cause.probe_results
    moved = _with_probe(actual, base=other)
    with pytest.raises(ExplanationEvidenceError, match="another base"):
        build(_rebuild(result, cause, (moved, comparator, same)))


# ---- punishment binding and SAN identity ------------------------------------------------------


def test_punishment_bound_to_actual_refutation_analysis_position():
    result = knight()
    cause = cause_of(result, Kind.NEWLY_HANGING_PIECE)
    bundle = build(result)
    group = group_of(bundle, Kind.NEWLY_HANGING_PIECE)
    actual, comparator = cause.probe_results
    assert group.response == MoveClaimEntity(
        cause.punishment_move, actual.analysis_position.position_id
    )
    assert group.response.position_id not in {
        result.base_position_id,
        comparator.analysis_position.position_id,
    }
    board = records_of(bundle, group)[0]
    assert group.response in board.moves


def test_no_punishment_means_no_response():
    result = single_supported(knight(), Kind.NEWLY_HANGING_PIECE)
    cause = result.causes[0]
    group = build(with_cause(result, cause, punishment_move=None)).groups[0]
    assert group.response is None


def test_binding_uses_uci_not_san():
    result = defender()
    sanned = tuple(
        replace(
            c,
            played_move=ChessMove(c.played_move.uci, "c4"),
            comparator_move=ChessMove(c.comparator_move.uci, "Ke2"),
            punishment_move=ChessMove(c.punishment_move.uci, "Rxd4"),
        )
        for c in result.causes
    )
    value = replace(result, played_move=ChessMove(result.played_move.uci), causes=sanned)
    plain = build(defender())
    rich = build(value)
    assert [g.evidence_ids for g in rich.groups] == [g.evidence_ids for g in plain.groups]
    group = rich.groups[0]
    assert group.played_move.move.san == "c4"
    assert group.response.move.san == "Rxd4"
    board = records_of(rich, group)[0]
    assert len(board.moves) == 3


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("base_position_id", "pos_elsewhere"),
        ("played_move", ChessMove("e1d1")),
        ("comparator_move", ChessMove("e1d1")),
    ],
)
def test_child_parent_binding_mismatch_fails_closed(field_name, value):
    result = knight()
    tamper(result.causes[0], **{field_name: value})
    with pytest.raises(ExplanationEvidenceError, match="P8 cause"):
        build(result)


# ---- material association ----------------------------------------------------------------------


def _variations(bundle, group):
    return [r for r in records_of(bundle, group) if type(r) is VariationEvidence]


def test_material_associated_by_exact_probe_in_probe_order():
    result = defender()
    cause = cause_of(result, Kind.REMOVED_DEFENDER)
    assert len(cause.material_evidence) == 3
    variations = _variations(build(result), group_of(build(result), Kind.REMOVED_DEFENDER))
    assert [v.probe for v in variations] == [r.probe for r in cause.probe_results]
    for variation in variations:
        assert all(m.probe == variation.probe for m in variation.material_evidence)
    assert [v.material_evidence for v in variations] == [(m,) for m in cause.material_evidence]
    actual, comparator, same = variations
    assert actual.board_deltas == cause.board_deltas
    assert comparator.board_deltas == same.board_deltas == ()
    assert comparator.replayed_pv_ends_in_checkmate is same.replayed_pv_ends_in_checkmate is None


def test_material_association_ignores_material_tuple_position():
    result = single_supported(defender(), Kind.REMOVED_DEFENDER)
    cause = result.causes[0]
    shuffled = with_cause(result, cause, material_evidence=tuple(reversed(cause.material_evidence)))
    assert build(shuffled) == build(result)


def test_unknown_material_probe_rejected():
    result = single_supported(knight(), Kind.NEWLY_HANGING_PIECE)
    cause = result.causes[0]
    foreign_probe = replace(cause.probe_results[0].probe, kind=ProbeKind.BEST_RESPONSE)
    foreign = MaterialLineEvidence(foreign_probe, material_delta=-300, stable_at_ply=2)
    with pytest.raises(ExplanationEvidenceError, match="matches 0 retained probes"):
        build(with_cause(result, cause, material_evidence=(foreign,)))


def test_non_actual_probe_without_material_has_no_variation():
    result = single_supported(knight(), Kind.NEWLY_HANGING_PIECE)
    cause = result.causes[0]
    actual_only = tuple(
        m for m in cause.material_evidence if m.probe == cause.probe_results[0].probe
    )
    bundle = build(with_cause(result, cause, material_evidence=actual_only))
    variations = _variations(bundle, bundle.groups[0])
    assert [v.probe for v in variations] == [cause.probe_results[0].probe]


def test_actual_variation_omitted_when_nothing_to_retain():
    result = single_supported(knight(), Kind.NEWLY_HANGING_PIECE)
    cause = result.causes[0]
    bare = with_cause(result, cause, board_deltas=(), material_evidence=())
    bundle = build(bare)
    assert _variations(bundle, bundle.groups[0]) == []


# ---- terminal evidence -------------------------------------------------------------------------


def _terminal(result_probe: ProbeResult) -> ProbeResult:
    return ProbeResult(
        probe=result_probe.probe,
        analysis_position=result_probe.analysis_position,
        intervention_position=result_probe.intervention_position,
        root_moves=None,
        engine_analysis=None,
        terminal=TerminalOutcome(TerminalKind.STALEMATE, None),
    )


def test_terminal_probe_result_is_counterfactual_only_unless_variation_required():
    result = single_supported(knight(), Kind.NEWLY_HANGING_PIECE)
    cause = result.causes[0]
    actual, comparator = cause.probe_results
    terminal = _terminal(comparator)
    value = with_cause(result, cause, probe_results=(actual, terminal))
    bundle = build(value)
    records = records_of(bundle, bundle.groups[0])

    engines = [r for r in records if type(r) is EngineEvidence]
    assert [e.probe_result for e in engines] == [actual]
    assert records[-1].probe_results == (actual, terminal)
    comparator_variation = _variations(bundle, bundle.groups[0])[1]
    assert comparator_variation.terminal == terminal.terminal
    assert comparator_variation.material_evidence  # required by material, terminal retained


def test_terminal_actual_line_still_binds_punishment_to_analysis_position():
    result = single_supported(knight(), Kind.NEWLY_HANGING_PIECE)
    cause = result.causes[0]
    actual, comparator = cause.probe_results
    value = with_cause(result, cause, probe_results=(_terminal(actual), comparator))
    bundle = build(value)
    group = bundle.groups[0]
    assert group.response.position_id == actual.analysis_position.position_id
    assert _variations(bundle, group)[0].terminal is not None
    assert all(
        type(r) is not EngineEvidence or r.probe_result is comparator for r in bundle.evidence
    )


# ---- ordering, ids, determinism ----------------------------------------------------------------


def test_rich_group_exact_record_order():
    bundle = build(single_supported(fork(), Kind.FORK_ALLOWED))
    assert [type(r) for r in bundle.evidence] == [
        BoardFactEvidence,
        MotifEvidence,
        EngineEvidence,
        EngineEvidence,
        EngineEvidence,
        VariationEvidence,
        VariationEvidence,
        VariationEvidence,
        CounterfactualEvidence,
    ]
    assert [r.evidence_id for r in bundle.evidence] == [f"ev_{n:03d}" for n in range(1, 10)]
    assert EVIDENCE_RECORD_TYPE_ORDER[0] is BoardFactEvidence


def test_ids_are_global_monotonic_across_groups():
    bundle = build(defender())
    assert len(bundle.groups) >= 2
    flat = [evidence_id for group in bundle.groups for evidence_id in group.evidence_ids]
    assert flat == [record.evidence_id for record in bundle.evidence]
    assert flat == [f"ev_{n:03d}" for n in range(1, len(flat) + 1)]


def test_groups_follow_kind_declaration_order_not_input_order():
    result = defender()
    reversed_result = BadMoveExplanationResult(
        status=result.status,
        base_position_id=result.base_position_id,
        played_move=result.played_move,
        comparator_move=result.comparator_move,
        causes=tuple(reversed(result.causes)),
    )
    forward, backward = build(result), build(reversed_result)
    assert forward == backward
    assert repr(forward) == repr(backward)
    kinds = [g.source_kind for g in forward.groups]
    assert kinds == sorted(kinds, key=list(Kind).index)


def test_same_kind_groups_order_by_full_subject_key():
    result = knight()
    cause = cause_of(result, Kind.NEWLY_HANGING_PIECE)
    king = BasePieceRef(W, PieceType.KING, "e1")
    second = replace(cause, subject=(king,))
    value = replace(result, causes=(*result.causes, second))  # appended last on input
    subjects = [g.source_subject for g in build(value).groups if g.source_kind is cause.kind]
    # e1 (square index 4) sorts before c3 (square index 18).
    assert subjects == [(king,), (BasePieceRef(W, PieceType.KNIGHT, "c3"),)]


def test_build_is_deterministic_across_independent_runs():
    first, second = build(fork()), build(fork())
    assert first == second
    assert repr(first) == repr(second)


def test_builder_output_passes_bundle_validation_for_every_fixture():
    for make in (knight, defender, fork, exact_mate, engine_mate):
        bundle = build(make())
        EvidenceBundle(bundle.base_position_id, bundle.evidence, bundle.groups)


# ---- trust-boundary guards ---------------------------------------------------------------------


SOURCE = Path(evidence_builder_module.__file__)


def _tree():
    return ast.parse(SOURCE.read_text(encoding="utf-8"))


def test_no_score_reads():
    attrs = {node.attr for node in ast.walk(_tree()) if isinstance(node, ast.Attribute)}
    assert not attrs & {
        "score",
        "scores",
        "cp",
        "mate",
        "wdl",
        "cp_loss",
        "expected_score_loss",
        "best_line",
        "lines",
        "best_score",
        "played_score",
        "material_delta",
        "stable_at_ply",
        "stable_deficit",
    }
    # I3 uses representative rank only as retained ordering metadata.
    rank_reads = [n for n in ast.walk(_tree()) if isinstance(n, ast.Attribute) and n.attr == "rank"]
    assert all(isinstance(n.value, ast.Name) and n.value.id == "alternative" for n in rank_reads)


def test_no_chess_or_engine_execution_dependencies():
    imported = set()
    names = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    assert all(
        name.startswith(("calliope.domain", "calliope.errors", "collections", "__future__"))
        for name in imported
    ), imported
    assert not names & {
        "PythonChessAdapter",
        "ChessRulesPort",
        "StockfishAdapter",
        "CounterfactualAnalyzer",
        "PositionFactExtractor",
        "BoardDeltaAnalyzer",
        "TacticalDetector",
        "BasePieceIdentityMap",
    }


def test_builder_has_no_constructor_dependencies():
    assert EvidenceBuilder.__init__ is object.__init__
