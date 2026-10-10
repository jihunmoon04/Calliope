"""An upper bound on the searches an `extend` request would bind (reasoning R0-D §6.4–§6.5).

It applies the planning rules of `EngineWork` (F4-D §6.3) to the request without running anything,
so a caller can admit engine work against a budget before issuing it. Surveys of new nodes are
assumed regular and new nodes are assumed searchable, so the bound never falls below the number
of searches the request actually binds — engine runs and store reuses alike.
"""

from __future__ import annotations

from calliope.facts.engine import plan_lines
from calliope.facts.errors import InvalidRequestError
from calliope.facts.keys import NodeId
from calliope.facts.request import POLICY_ROLE_KINDS, ExpansionSpec, ExtendRequest, RoleKind
from calliope.facts.search.records import EngineSearch, SearchKind
from calliope.facts.tree import RoleEntry, TreeView, effective_expansion


def planned_search_bound(view: TreeView, request: ExtendRequest) -> int:
    """Searches `request` can bind if issued now; `view` must be the tree's current revision."""

    tree = view._tree
    if view.rev != tree.rev:
        raise InvalidRequestError("the bound is computed for a request issued at the current rev")
    session = tree._session
    if session.engine is None:
        return 0
    expansion = _expansion(session, request)
    plans = plan_lines(tree, request)
    role = request.role.kind

    nodes: list[NodeId] = []
    child_moves: dict[NodeId, set[str]] = {}
    for plan in plans:
        nodes.append(plan.start)
        for step in plan.steps:
            nodes.append(step.child)
            child_moves.setdefault(step.parent, set()).add(step.move.uci())
    nodes = list(dict.fromkeys(nodes))

    bound = 0
    for node_id in nodes:
        existing = view.has_node(node_id)
        if existing:
            node = view.node(node_id)
            if node.terminal.ends_game or node.after_terminal:
                continue  # never searched (F4-D §6.3)
        roles = [*view.roles(node_id)] if existing else []
        roles.append(_request_role(node_id, role, expansion))
        searchable = effective_expansion(roles).survey
        policy = effective_expansion(roles, policy=True)
        survey = _latest(view, node_id, SearchKind.SURVEY) if existing else None
        added = child_moves.get(node_id, set())
        policy_children = _policy_children(view, node_id) if existing else set()
        if role in POLICY_ROLE_KINDS:
            policy_children |= added

        if searchable and survey is None:
            bound += 1  # a survey
        if searchable and policy.comparison:
            if survey is None:
                if policy_children:
                    bound += 1  # the new survey may leave a policy child outside its moves
            elif survey.regular:
                wanted = {line.move for line in survey.lines} | policy_children
                last = _latest(view, node_id, SearchKind.COMPARISON)
                covered = last is not None and set(last.root_moves or ()) >= wanted
                if len(wanted) > len(survey.lines) and not covered:
                    bound += 1  # a comparison, or the retry of a skipped one
        if role is RoleKind.ANALYSIS and expansion.comparison and added:
            survey_moves = set() if survey is None else {line.move for line in survey.lines}
            if survey is None or not added <= survey_moves:
                bound += 1  # an ANALYSIS search over survey moves and this request's moves
    return bound


def _expansion(session, request: ExtendRequest) -> ExpansionSpec:
    if request.expansion is not None:
        return request.expansion
    if request.role.kind is RoleKind.ANALYSIS:
        raise InvalidRequestError("an ANALYSIS request must state its expansion")
    if request.role.kind is RoleKind.PLAYED:
        return session.defaults.played
    return session.defaults.explored


def _request_role(node_id: NodeId, kind: RoleKind, expansion: ExpansionSpec) -> RoleEntry:
    return RoleEntry(node_id, False, kind, "", "", 0, 0, expansion)


def _latest(view: TreeView, node_id: NodeId, kind: SearchKind) -> EngineSearch | None:
    bindings = [b for b in view.searches(node_id) if b.kind is kind]
    return None if not bindings else view.search(bindings[-1].search_id)


def _policy_children(view: TreeView, node_id: NodeId) -> set[str]:
    moves: set[str] = set()
    for child in view.children(node_id):
        if any(r.kind in POLICY_ROLE_KINDS for r in view.roles(child, on_edge=True)):
            move = view.node(child).incoming_move
            assert move is not None
            moves.add(move)
    return moves
