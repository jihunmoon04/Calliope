from dataclasses import fields, replace

import pytest

import calliope.services.explanation.bad_move as bad_move_module
from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis import BadMoveCauseResult, TacticalCandidateStatus
from calliope.domain.chess import ChessMove, Color, PieceRef, PieceType
from calliope.domain.engine import EngineScore, MoveJudgement, MoveQuality
from calliope.errors import IncompatibleBadMoveContextError
from calliope.services.explanation import BadMoveExplainer, BasePieceIdentityMap
from calliope.services.explanation.bad_move import (
    BadMoveNotApplicable,
    BadMovePreparedContext,
    FirstMoveBranchContext,
)
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.tactics import TacticalDetector

rules = PythonChessAdapter()
facts = PositionFactExtractor(rules)
deltas = BoardDeltaAnalyzer(rules, facts)
detector = TacticalDetector()

# White knight on c3; Ne4 puts it en prise to the d5 pawn, Nb5 does not.
FEN = "4k3/8/8/3p4/8/2N5/8/4K3 w - - 0 1"
BASE = rules.position_from_fen(FEN)
PLAYED = ChessMove("c3e4")
BEST = ChessMove("c3b5")


def explainer(**overrides) -> BadMoveExplainer:
    parts = {
        "chess": rules,
        "facts": facts,
        "delta": deltas,
        "tactical_rules": rules,
        "detector": detector,
    }
    parts.update(overrides)
    return BadMoveExplainer(**parts)


def judgement(
    quality: MoveQuality = MoveQuality.BLUNDER,
    *,
    move: ChessMove = PLAYED,
    best: ChessMove = BEST,
    position_id: str | None = None,
    mover: Color = Color.WHITE,
) -> MoveJudgement:
    return MoveJudgement(
        position_id=position_id or BASE.position_id,
        mover=mover,
        move=move,
        best_move=best,
        quality=quality,
        rank=None,
        best_score=EngineScore.cp(0),
        played_score=EngineScore.cp(-300),
        cp_loss=300,
        expected_score_loss=0.3,
    )


def prepared(quality: MoveQuality = MoveQuality.BLUNDER) -> BadMovePreparedContext:
    result = explainer().prepare(BASE, PLAYED, judgement(quality))
    assert isinstance(result, BadMovePreparedContext)
    return result


# ---- eligibility / context ------------------------------------------------------------


@pytest.mark.parametrize("quality", [MoveQuality.MISTAKE, MoveQuality.BLUNDER])
def test_eligible_quality_prepares_both_branches(quality: MoveQuality) -> None:
    context = prepared(quality)

    assert context.base == BASE
    assert context.judgement.quality is quality
    assert context.played_move.uci == "c3e4"
    assert context.comparator_move.uci == "c3b5"
    assert context.actual.move == context.played_move
    assert context.comparator.move == context.comparator_move


@pytest.mark.parametrize(
    "quality",
    [MoveQuality.BEST, MoveQuality.EXCELLENT, MoveQuality.GOOD, MoveQuality.INACCURACY],
)
def test_non_eligible_quality_is_not_applicable(quality: MoveQuality) -> None:
    result = explainer().prepare(BASE, PLAYED, judgement(quality))

    assert isinstance(result, BadMoveNotApplicable)
    assert result.played_move.uci == "c3e4"
    assert result.comparator_move.uci == "c3b5"


def test_best_move_may_equal_comparator_on_not_applicable_path() -> None:
    result = explainer().prepare(BASE, BEST, judgement(MoveQuality.BEST, move=BEST, best=BEST))

    assert isinstance(result, BadMoveNotApplicable)
    assert result.played_move.uci == result.comparator_move.uci == "c3b5"


class _Forbidden:
    def __getattr__(self, name: str):
        raise AssertionError(f"non-applicable path must not use {name}")


def test_not_applicable_path_builds_no_branch_facts() -> None:
    quiet = explainer(facts=_Forbidden(), delta=_Forbidden(), detector=_Forbidden())

    result = quiet.prepare(BASE, PLAYED, judgement(MoveQuality.INACCURACY))

    assert isinstance(result, BadMoveNotApplicable)
    assert {f.name for f in fields(BadMoveNotApplicable)} == {
        "base",
        "judgement",
        "played_move",
        "comparator_move",
    }


def test_not_applicable_path_still_validates_context() -> None:
    with pytest.raises(IncompatibleBadMoveContextError, match="another position"):
        explainer().prepare(BASE, PLAYED, judgement(MoveQuality.GOOD, position_id="pos_other"))
    with pytest.raises(IncompatibleBadMoveContextError, match="comparator"):
        explainer().prepare(BASE, PLAYED, judgement(MoveQuality.GOOD, best=ChessMove("e1e3")))


def test_judgement_position_mismatch_fails_closed() -> None:
    with pytest.raises(IncompatibleBadMoveContextError, match="another position"):
        explainer().prepare(BASE, PLAYED, judgement(position_id="pos_other"))


def test_judgement_mover_mismatch_fails_closed() -> None:
    with pytest.raises(IncompatibleBadMoveContextError, match="mover"):
        explainer().prepare(BASE, PLAYED, judgement(mover=Color.BLACK))


def test_played_move_must_match_judged_move() -> None:
    with pytest.raises(IncompatibleBadMoveContextError, match="differs from the judged move"):
        explainer().prepare(BASE, ChessMove("c3a4"), judgement())


@pytest.mark.parametrize("uci", ["e1e3", "c3c3", "zz99"])
def test_illegal_comparator_fails_closed(uci: str) -> None:
    with pytest.raises(IncompatibleBadMoveContextError, match="comparator"):
        explainer().prepare(BASE, PLAYED, judgement(best=ChessMove(uci)))


def test_illegal_judged_move_fails_closed() -> None:
    with pytest.raises(IncompatibleBadMoveContextError, match="judged move"):
        explainer().prepare(BASE, PLAYED, judgement(move=ChessMove("e1e3")))


@pytest.mark.parametrize("quality", [MoveQuality.MISTAKE, MoveQuality.BLUNDER])
def test_eligible_comparator_equal_to_played_fails_closed(quality: MoveQuality) -> None:
    with pytest.raises(IncompatibleBadMoveContextError, match="differ from its comparator"):
        explainer().prepare(BASE, PLAYED, judgement(quality, best=PLAYED))


def test_moves_are_bound_by_canonical_uci_not_presentation() -> None:
    played = ChessMove(" c3e4 ", san="garbage")
    judged = judgement(
        move=ChessMove("c3e4", san="Nxd5?!"),
        best=ChessMove("c3b5 ", san="not-san"),
    )

    context = explainer().prepare(BASE, played, judged)

    assert isinstance(context, BadMovePreparedContext)
    assert context.played_move == ChessMove("c3e4", san="Ne4")
    assert context.comparator_move == ChessMove("c3b5", san="Nb5")
    assert context.actual.delta.move.uci == "c3e4"


def test_preparation_is_deterministic() -> None:
    assert prepared() == prepared()


# ---- branches -------------------------------------------------------------------------


def test_common_base_observations_are_bound_to_base() -> None:
    context = prepared()

    assert context.base_facts == facts.extract(BASE)
    assert context.base_rules == rules.observe_tactics(BASE)
    assert context.root_identity == BasePieceIdentityMap.from_facts(context.base_facts)
    assert context.root_identity.position_id == BASE.position_id


@pytest.mark.parametrize(("side", "uci"), [("actual", "c3e4"), ("comparator", "c3b5")])
def test_branch_is_one_coherent_first_move_from_base(side: str, uci: str) -> None:
    branch: FirstMoveBranchContext = getattr(prepared(), side)
    move = rules.legal_move_from_uci(BASE, uci)
    after = rules.apply_move(BASE, move)

    assert branch.position == after
    assert branch.delta == deltas.analyze(BASE, move)
    assert branch.delta.before_position_id == BASE.position_id
    assert branch.delta.after_position_id == after.position_id
    assert branch.facts == facts.extract(after)
    assert branch.rules.position_id == after.position_id
    assert branch.rules.side_to_move is Color.BLACK
    assert branch.detection.before_position_id == BASE.position_id
    assert branch.detection.after_position_id == after.position_id
    assert branch.detection.move.uci == uci
    assert branch.detection.mover is Color.WHITE
    assert branch.identity.base_position_id == BASE.position_id
    assert branch.identity.position_id == after.position_id


def test_actual_and_comparator_identities_are_independent() -> None:
    context = prepared()
    knight = context.root_identity.base_ref_for(PieceRef(Color.WHITE, PieceType.KNIGHT, "c3"))

    assert context.root_identity == BasePieceIdentityMap.from_facts(context.base_facts)
    assert context.root_identity.current_piece(knight).square == "c3"
    assert context.actual.identity.current_piece(knight).square == "e4"
    assert context.comparator.identity.current_piece(knight).square == "b5"
    assert (
        context.actual.identity.base_pieces
        == context.comparator.identity.base_pieces
        == context.root_identity.base_pieces
    )


def test_p6_candidates_stay_detected_and_no_cause_is_produced() -> None:
    context = prepared()

    kinds = {c.kind.value for c in context.actual.detection.candidates}
    assert "hanging_piece" in kinds
    for branch in (context.actual, context.comparator):
        assert all(
            c.status is TacticalCandidateStatus.DETECTED for c in branch.detection.candidates
        )

    def values(obj):
        for f in fields(obj):
            yield getattr(obj, f.name)

    retained = (
        list(values(context)) + list(values(context.actual)) + list(values(context.comparator))
    )
    assert not any(isinstance(value, BadMoveCauseResult) for value in retained)


# ---- fail-closed tampering ------------------------------------------------------------


class _TamperedDelta:
    def __init__(self, **changes) -> None:
        self.changes = changes

    def analyze(self, before, move):
        return replace(deltas.analyze(before, move), **self.changes)


class _TamperedRules:
    """Tamper only branch (non-base) tactical observations."""

    def __init__(self, **changes) -> None:
        self.changes = changes

    def observe_tactics(self, position):
        observation = rules.observe_tactics(position)
        if position.position_id == BASE.position_id:
            return observation
        return replace(observation, **self.changes)


class _TamperedDetector:
    def __init__(self, **changes) -> None:
        self.changes = changes

    def detect(self, **kwargs):
        return replace(detector.detect(**kwargs), **self.changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"before_position_id": "pos_other"}, "does not start from the base"),
        ({"after_position_id": "pos_other"}, "does not end at the branch"),
        ({"move": ChessMove("c3b5")}, "describes another move"),
        ({"mover": Color.BLACK}, "wrong mover"),
    ],
)
def test_corrupted_delta_fails_closed(changes: dict, message: str) -> None:
    with pytest.raises(IncompatibleBadMoveContextError, match=message):
        explainer(delta=_TamperedDelta(**changes)).prepare(BASE, PLAYED, judgement())


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"position_id": "pos_other"}, "observation belongs to another position"),
        ({"side_to_move": Color.WHITE}, "wrong side to move"),
    ],
)
def test_corrupted_branch_tactical_observation_fails_closed(changes: dict, message: str) -> None:
    with pytest.raises(IncompatibleBadMoveContextError, match=message):
        explainer(tactical_rules=_TamperedRules(**changes)).prepare(BASE, PLAYED, judgement())


def test_corrupted_base_tactical_observation_fails_closed() -> None:
    class BaseTampered:
        def observe_tactics(self, position):
            return replace(rules.observe_tactics(position), position_id="pos_other")

    with pytest.raises(IncompatibleBadMoveContextError, match="base tactical observation"):
        explainer(tactical_rules=BaseTampered()).prepare(BASE, PLAYED, judgement())


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"before_position_id": "pos_other"}, "detection does not start"),
        ({"after_position_id": "pos_other"}, "detection does not end"),
        ({"move": ChessMove("c3b5")}, "detection describes another move"),
        ({"mover": Color.BLACK}, "detection has the wrong mover"),
    ],
)
def test_corrupted_detection_fails_closed(changes: dict, message: str) -> None:
    with pytest.raises(IncompatibleBadMoveContextError, match=message):
        explainer(detector=_TamperedDetector(**changes)).prepare(BASE, PLAYED, judgement())


def test_corrupted_identity_binding_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    real_advance = BasePieceIdentityMap.advance

    def advance(self, delta):
        advanced = real_advance(self, delta)
        return BasePieceIdentityMap(advanced.base_position_id, "pos_other", advanced._entries)

    monkeypatch.setattr(bad_move_module.BasePieceIdentityMap, "advance", advance)

    with pytest.raises(IncompatibleBadMoveContextError, match="identity is not bound"):
        explainer().prepare(BASE, PLAYED, judgement())


def test_corrupted_after_position_fails_closed() -> None:
    class WrongAfter:
        def __getattr__(self, name):
            return getattr(rules, name)

        def apply_move(self, position, move):
            return rules.apply_move(position, ChessMove("e1d1"))

    with pytest.raises(IncompatibleBadMoveContextError, match="does not end at the branch"):
        explainer(chess=WrongAfter()).prepare(BASE, PLAYED, judgement())
