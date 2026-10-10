"""The input contract of an analysis (R0-D §5)."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace

from calliope.facts import EngineProfile, ExtendRequest, OpenRequest, RootSpec, TreeView
from calliope.reasoning.errors import InvalidAnalysisRequest

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


def check(request: AnalysisRequest) -> None:
    """Structural checks before any fact request (R0-D §5); chess validity is the fact engine's."""

    if not isinstance(request.moves, tuple) or not all(isinstance(m, str) for m in request.moves):
        raise InvalidAnalysisRequest("moves must be a tuple of move strings")
    if not 1 <= request.target <= len(request.moves):
        raise InvalidAnalysisRequest(
            f"target {request.target} is not a ply of a {len(request.moves)}-ply line"
        )
    if request.language not in LANGUAGES:
        raise InvalidAnalysisRequest(f"unknown language {request.language!r}")
    for field in fields(request.budget):
        value = getattr(request.budget, field.name)
        minimum = 0 if field.name == "max_extra_searches" else 1
        if not isinstance(value, int) or value < minimum:
            raise InvalidAnalysisRequest(f"budget {field.name} must be an integer ≥ {minimum}")


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
