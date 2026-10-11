"""The input contract of an analysis (R0-D §5)."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace

from calliope.facts import EngineProfile, ExtendRequest, OpenRequest, RootSpec, TreeView
from calliope.reasoning.errors import InvalidAnalysisRequest
from calliope.reasoning.grading import GradingSpec, check_spec

LANGUAGES = ("ko",)


@dataclass(frozen=True, slots=True)
class ReasoningBudget:
    """Per target move (R0-D D8, §6.3, §6.4)."""

    max_rounds: int = 3
    max_extra_searches: int = 4
    max_ensure_nodes: int = 64
    max_tree_nodes: int = 1000
    pv_plies: int = 10
    deadline_ms: int = 5000
    max_hypotheses: int = 256
    max_derivation_depth: int = 3
    max_fixpoint_passes: int = 16


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    root: RootSpec
    moves: tuple[str, ...]  # the played line from the root (UCI or SAN)
    target: int  # 1-based ply index into `moves`; R0 handles one target
    profile: EngineProfile
    budget: ReasoningBudget = ReasoningBudget()
    language: str = "ko"
    grading: GradingSpec = GradingSpec()  # noqa: RUF009 (frozen) — Q-D §3


def check(request: AnalysisRequest) -> None:
    """Structural checks before any fact request (R0-D §5); chess validity is the fact engine's."""

    if not isinstance(request.root, RootSpec):
        raise InvalidAnalysisRequest("root must be a RootSpec")
    if not isinstance(request.moves, tuple) or not all(isinstance(m, str) for m in request.moves):
        raise InvalidAnalysisRequest("moves must be a tuple of move strings")
    if isinstance(request.target, bool) or not isinstance(request.target, int):
        raise InvalidAnalysisRequest("target must be an integer ply index")
    if not 1 <= request.target <= len(request.moves):
        raise InvalidAnalysisRequest(
            f"target {request.target} is not a ply of a {len(request.moves)}-ply line"
        )
    if request.language not in LANGUAGES:
        raise InvalidAnalysisRequest(f"unknown language {request.language!r}")
    if not isinstance(request.profile, EngineProfile):
        raise InvalidAnalysisRequest("profile must be an EngineProfile")
    if not isinstance(request.budget, ReasoningBudget):
        raise InvalidAnalysisRequest("budget must be a ReasoningBudget")
    for field in fields(request.budget):
        value = getattr(request.budget, field.name)
        # every bound is positive except the work after round 0: 0 extra searches or ensure
        # nodes means none (R0-D §6.4, §27)
        minimum = 0 if field.name in ("max_extra_searches", "max_ensure_nodes") else 1
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise InvalidAnalysisRequest(f"budget {field.name} must be an integer ≥ {minimum}")
    check_spec(request.grading)


def normalized(
    request: AnalysisRequest, view: TreeView, extends: tuple[int, ...]
) -> AnalysisRequest:
    """The request with the root and moves as the fact engine recorded them (R0-D §5).

    Moves after `target` are dropped; the rest are the canonical UCI of the played line's
    `extend` revisions `extends`, in order.
    """

    opening = view.request(1)
    assert isinstance(opening, OpenRequest)
    moves: list[str] = []
    for rev in extends:
        extend = view.request(rev)
        assert isinstance(extend, ExtendRequest) and len(extend.lines) == 1
        moves.extend(extend.lines[0].moves)
    return replace(request, root=opening.root, moves=tuple(moves))
