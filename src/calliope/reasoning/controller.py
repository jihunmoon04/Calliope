"""The analysis controller: the only stage that changes the fact tree (R0-D §6, D2).

Packet R1 delivers round 0 — the base tree, the judgements and the round-0 observations. Later
rounds (needs, admission, the hypothesis fixpoint) come with packet R2.
"""

from __future__ import annotations

from dataclasses import dataclass

from calliope.facts import (
    FULL,
    NONE,
    PLAYED,
    EnsureRequest,
    ExtendRequest,
    FactEngine,
    FactEngineError,
    FactTree,
    IllegalMoveError,
    InputLine,
    InvalidPositionError,
    NodeId,
    OpenRequest,
    SessionBudget,
    UnsupportedVariantError,
)
from calliope.reasoning.errors import AnalysisFailed, InvalidAnalysisRequest
from calliope.reasoning.grading import SHIPPED, Grading, GradingBuild, resolve
from calliope.reasoning.observer import (
    Judgement,
    Observation,
    judge,
    line_material,
    line_nodes,
    played_edge,
    standard_lines,
)
from calliope.reasoning.refs import MoveSubject
from calliope.reasoning.request import AnalysisRequest, check, normalized

PLAYED_LABEL = "game"
_INPUT_ERRORS = (IllegalMoveError, InvalidPositionError, UnsupportedVariantError)


@dataclass(frozen=True, slots=True)
class RoundZero:
    """The state after round 0 (R0-D §6.1): everything later rounds start from."""

    request: AnalysisRequest  # normalized (R0-D §5)
    grading: Grading  # resolved before any fact request (Q-D §3)
    tree: FactTree
    rev: int  # rev_0
    subject: MoveSubject  # the target move P → C
    previous: MoveSubject | None  # the opponent's move G → P, when G exists
    judgements: tuple[Judgement, ...]  # the target's, then the previous move's
    observations: tuple[Observation, ...]
    reproducible: bool  # False if any revision is load-dependent (deadline cuts)


class Controller:
    def __init__(self, fact_engine: FactEngine, grading_build: GradingBuild = SHIPPED) -> None:
        self.fact_engine = fact_engine
        self.grading_build = grading_build

    def round_zero(self, request: AnalysisRequest) -> RoundZero:
        """Build the base tree of R0-D §6.1 and read the judgements on `V_0`."""

        check(request)
        grading = resolve(request.grading, self.grading_build)
        t = request.target
        g = max(0, t - 2)
        budget = SessionBudget(
            max_nodes=t + 1 + request.budget.max_tree_nodes,
            deadline_per_request_ms=request.budget.deadline_ms,
        )
        engine = self.fact_engine
        try:
            tree = engine.open(
                OpenRequest(
                    root=request.root,
                    engine=request.profile,
                    # always NONE: the window extend gives its start node FULL, after its input
                    # nodes are counted, so attached lines never crowd out the played moves
                    root_expansion=NONE,
                    budget=budget,
                )
            )
            extends: list[int] = []
            start: NodeId | None = None
            if g > 0:
                line = InputLine(PLAYED_LABEL, request.moves[:g])
                extends.append(engine.extend(tree, ExtendRequest((line,), PLAYED, NONE)))
                start = tree.view().input_line(PLAYED_LABEL).nodes[-1]
            window = InputLine(PLAYED_LABEL, request.moves[g:t], start=start)
            extends.append(engine.extend(tree, ExtendRequest((window,), PLAYED, FULL)))
        except _INPUT_ERRORS as error:
            raise InvalidAnalysisRequest(f"the fact engine refused the input: {error}", error)
        except FactEngineError as error:
            raise AnalysisFailed(f"round 0 failed: {type(error).__name__}: {error}", error)

        view = tree.view()
        played = _played_nodes(view.input_line(PLAYED_LABEL), view)
        subject = MoveSubject(played[t - 1], played[t])
        previous = MoveSubject(played[t - 2], played[t - 1]) if t >= 2 else None

        # step 4: every family on the standard lines' first pv_plies plies (R2-C5)
        target_judgement = judge(view, subject, grading)
        nodes = line_nodes(view, target_judgement, request.budget.pv_plies)
        if nodes:
            try:
                engine.ensure(tree, EnsureRequest(nodes, tuple(view.families())))
            except FactEngineError as error:
                raise AnalysisFailed(f"round 0 ensure failed: {error}", error)

        view = tree.view()  # V_0
        judgements = [judge(view, subject, grading)]
        if previous is not None:
            judgements.append(judge(view, previous, grading))
        observations = []
        for observe in (standard_lines, line_material):
            observation = observe(view, judgements[0], request.budget.pv_plies)
            if observation is not None:
                observations.append(observation)
        observations.append(played_edge(view, subject))
        return RoundZero(
            request=normalized(request, view, tuple(extends)),
            grading=grading,
            tree=tree,
            rev=view.rev,
            subject=subject,
            previous=previous,
            judgements=tuple(judgements),
            observations=tuple(observations),
            reproducible=view.reproducible(),
        )


def _played_nodes(segment, view) -> tuple[NodeId, ...]:
    """Root, then the node after each played ply (the line may be stored in two segments)."""

    head = segment
    nodes = list(head.nodes)
    while head.line_id.segment > 0:
        head = view.input_line(PLAYED_LABEL, segment=head.line_id.segment - 1)
        nodes = list(head.nodes[:-1]) + nodes
    if nodes[0] != view.root:
        raise AssertionError("the played line does not start at the root")
    return tuple(nodes)
