"""The fact engine: the only writer of fact trees (design F0 §2, §3).

Packets F1–F2: `open`, `extend` and `ensure` without Stockfish. Every request is validated
completely (parsing, legality, labels, budget, known nodes and families) before anything is
built, and commits as one revision.

Family records are resolved by scope (F2-D §9): POSITION records once per `PositionKey`, from a
board rebuilt from the key; NODE records per node; EDGE records per child node with the parent's
records; SPAN records per node with the grandparent's records. A present record is never
recomputed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import chess

from calliope.facts import identity
from calliope.facts.board import MoveRejectedError, canonical_move, node_fen, parse_start_fen
from calliope.facts.errors import BudgetExceededError, IllegalMoveError, InvalidRequestError
from calliope.facts.families import MANDATORY, REGISTRY, FactFamily, FamilyContext, HistoryWindow
from calliope.facts.families.draw import DrawFacts
from calliope.facts.families.pieces import PIECE_ORDER_V1
from calliope.facts.families.status import StatusFacts
from calliope.facts.identity import IdentityStep
from calliope.facts.keys import Color, NodeId, PositionKey, RootId
from calliope.facts.request import (
    EnsureRequest,
    ExtendRequest,
    InputLine,
    LineRole,
    OpenRequest,
    SessionBudget,
)
from calliope.facts.tree import (
    DrawRule,
    Edge,
    FactEntry,
    FactTree,
    FrameNode,
    LineEnd,
    LineId,
    LineRecord,
    PendingRevision,
    RevisionDelta,
    RoleEntry,
    Scope,
    Terminal,
    TerminalKind,
)
from calliope.facts.values import HistoryUnknown, NotApplicable

ROOT_LABEL = "<root>"
DEFINITIONS = (
    ("insufficient_material", f"python-chess {chess.__version__} Board.is_insufficient_material"),
    ("points_v1", "1/3/3/5/9 per pawn/knight/bishop/rook/queen"),
    (PIECE_ORDER_V1, "K > Q > R > B = N > P"),
)
# What a family of each scope may require, and where the requirement is resolved (F2-D §9).
ALLOWED_REQUIRES: dict[Scope, frozenset[Scope]] = {
    Scope.POSITION: frozenset({Scope.POSITION}),  # the same PositionKey
    Scope.NODE: frozenset({Scope.POSITION, Scope.NODE}),  # the same node
    Scope.EDGE: frozenset({Scope.POSITION, Scope.NODE, Scope.EDGE}),  # both ends; this edge
    Scope.SPAN: frozenset({Scope.POSITION, Scope.NODE}),  # grandparent and node
}
NO_GRANDPARENT = NotApplicable("no same-side ancestor in the tree")


@dataclass(frozen=True, slots=True)
class _Session:
    families: tuple[FactFamily, ...]  # every registered family, in dependency order
    eager: tuple[FactFamily, ...]  # the eager set, closed under `requires`, in dependency order
    budget: SessionBudget
    start_board: chess.Board  # the start position exactly as parsed (incl. its en passant square)
    pre_root_moves: tuple[str, ...]  # canonical UCI, replayed from `start_board` to the root
    pre_root_keys: tuple[PositionKey, ...]  # positions before the root, oldest first
    ended_before_root: bool  # a known position before the root ended the game by rule


@dataclass(frozen=True, slots=True)
class _Step:
    parent: NodeId
    child: NodeId
    move: chess.Move


@dataclass(frozen=True, slots=True)
class _PlannedLine:
    line: InputLine
    start: NodeId
    first_index: int
    segment: int
    steps: tuple[_Step, ...]


class FactEngine:
    """Builds and extends fact trees. Stateless; each tree carries its own session."""

    def __init__(self, families: Sequence[FactFamily] = REGISTRY) -> None:
        _check_registry(families)
        self._registry = {family.name: family for family in families}

    # -- open --------------------------------------------------------------------------------

    def open(self, request: OpenRequest) -> FactTree:
        eager = self._select(request.families)
        start = parse_start_fen(request.root.fen)
        board = start.copy()  # carries the known move stack for the pre-root checks below
        canonical: list[str] = []
        pre_root_keys: list[PositionKey] = []
        # A clock above 150 proves an earlier position reached the seventy-five-move rule.
        ended = start.halfmove_clock > 150
        for ply, text in enumerate(request.root.moves, start=1):
            move = _parse(board, text, ROOT_LABEL, ply)
            ended = ended or _ended_by_rule(board)
            pre_root_keys.append(PositionKey.of(board))
            canonical.append(move.uci())
            board.push(move)
        _check_budget(request.budget, nodes_after=1)

        root_id = RootId.of(node_fen(start), tuple(canonical))
        families = tuple(self._registry.values())
        session = _Session(
            families=families,
            eager=eager,
            budget=request.budget,
            start_board=start.copy(),
            pre_root_moves=tuple(canonical),
            pre_root_keys=tuple(pre_root_keys),
            ended_before_root=ended,
        )
        tree = FactTree(
            root_id,
            NodeId.root(root_id),
            {f.name: (f.version, f.scope, f.fact_class) for f in families},
            session,
            eager=frozenset(f.name for f in eager),
        )
        with tree._write_lock:
            build = _Build(tree, session)
            build.add_root(board.copy(stack=False), known_plies=len(canonical))
            delta = build.delta(
                "open",
                lines=(),
                definitions=DEFINITIONS,
                eager=tuple(f.name for f in eager),
            )
            tree._commit(build.pending, delta)
        return tree

    # -- extend ------------------------------------------------------------------------------

    def extend(self, tree: FactTree, request: ExtendRequest) -> int:
        session = tree._session
        assert isinstance(session, _Session)
        with tree._write_lock:
            plans = self._plan(tree, request)
            new_nodes = {s.child for p in plans for s in p.steps} - tree._store.nodes.keys()
            _check_budget(session.budget, nodes_after=len(tree._store.nodes) + len(new_nodes))

            build = _Build(tree, session)
            for plan in plans:
                for step in plan.steps:
                    build.add_child(step)
            line_ids = tuple(build.add_line(plan, request.role) for plan in plans)
            return tree._commit(build.pending, build.delta("extend", lines=line_ids))

    # -- ensure ------------------------------------------------------------------------------

    def ensure(self, tree: FactTree, request: EnsureRequest) -> int:
        """Compute the missing records of `families` and their dependencies on `nodes`.

        Dependencies are resolved where their scope puts them: EDGE families also on the
        parent, SPAN families also on the grandparent. Every new record goes in at one new
        revision; if nothing is missing, no revision is committed and the current one is
        returned (F2-D §9).
        """

        session = tree._session
        assert isinstance(session, _Session)
        if not request.nodes or not request.families:
            raise InvalidRequestError("an ensure request needs at least one node and one family")
        session_families = {f.name for f in session.families}  # the tree's, not this engine's
        unknown = sorted(set(request.families) - session_families)
        if unknown:
            raise InvalidRequestError(f"unknown fact families: {unknown}")
        wanted = set(request.families)
        families = tuple(f for f in session.families if f.name in wanted)
        with tree._write_lock:
            missing = [n for n in request.nodes if n not in tree._store.nodes]
            if missing:
                raise InvalidRequestError(f"unknown nodes: {[str(n) for n in missing]}")
            build = _Build(tree, session)
            for node_id in dict.fromkeys(request.nodes):
                for family in families:
                    build.resolve(family, node_id)
            if not build.pending.facts:
                return tree.rev
            return tree._commit(build.pending, build.delta("ensure", lines=()))

    def _plan(self, tree: FactTree, request: ExtendRequest) -> list[_PlannedLine]:
        role = request.role
        if not request.lines:
            raise InvalidRequestError("an extend request needs at least one line")
        labels = [line.label for line in request.lines]
        if len(set(labels)) != len(labels):
            raise InvalidRequestError("labels must be unique within one request")
        store = tree._store
        plans: list[_PlannedLine] = []
        for line in request.lines:
            if not line.label or line.label == ROOT_LABEL:
                raise InvalidRequestError(f"invalid line label {line.label!r}")
            if not line.moves:
                raise InvalidRequestError(f"line {line.label!r} has no moves")
            previous = store.line_heads.get((role.kind, role.by or "", line.label))
            if previous is None:
                start = line.start or tree.root
                first_index, segment = 0, 0
            else:
                end = previous.nodes[-1]
                if line.start is not None and line.start != end:
                    raise InvalidRequestError(
                        f"line {line.label!r} continues only from its end node {end}"
                    )
                start = end
                first_index = previous.first_index + len(previous.nodes) - 1
                segment = previous.segment + 1
            if start not in store.nodes:
                raise InvalidRequestError(f"line {line.label!r} starts at unknown node {start}")

            board = chess.Board(store.nodes[start].fen)
            parent = start
            steps: list[_Step] = []
            for ply, text in enumerate(line.moves, start=1):
                move = _parse(board, text, line.label, ply)
                child = NodeId.child(parent, move.uci())
                steps.append(_Step(parent, child, move))
                board.push(move)
                parent = child
            plans.append(_PlannedLine(line, start, first_index, segment, tuple(steps)))
        return plans

    def _select(self, names: tuple[str, ...] | None) -> tuple[FactFamily, ...]:
        """The eager set: the named families plus `MANDATORY`, closed under `requires`."""

        wanted = set(self._registry) if names is None else set(names) | MANDATORY
        unknown = wanted - set(self._registry)
        if unknown:
            raise InvalidRequestError(f"unknown fact families: {sorted(unknown)}")
        for family in reversed(self._registry.values()):  # reverse dependency order
            if family.name in wanted:
                wanted.update(family.requires)
        return tuple(f for f in self._registry.values() if f.name in wanted)


def _check_registry(families: Sequence[FactFamily]) -> None:
    """Registry order is dependency order, and each `requires` respects its scope (F2-D §9)."""

    seen: dict[str, FactFamily] = {}
    for family in families:
        if family.name in seen:
            raise ValueError(f"family {family.name!r} is registered twice")
        for name in family.requires:
            required = seen.get(name)
            if required is None:
                raise ValueError(f"{family.name} requires {name!r}, not registered before it")
            if required.scope not in ALLOWED_REQUIRES[family.scope]:
                raise ValueError(
                    f"a {family.scope.value} family ({family.name}) cannot require a "
                    f"{required.scope.value} family ({name})"
                )
        seen[family.name] = family


class _Build:
    """Records of one request, built against the committed store plus this request's own nodes."""

    def __init__(self, tree: FactTree, session: _Session) -> None:
        self.tree = tree
        self.session = session
        self.pending: PendingRevision = tree._begin()
        self._nodes: dict[NodeId, FrameNode] = {}
        self._records: dict[tuple[str, PositionKey | NodeId], Any] = {}
        self._steps: dict[NodeId, IdentityStep] = {}  # identity step of the edge into a node
        self._boards: dict[PositionKey | NodeId, chess.Board] = {}  # families never mutate them
        self._roles: set[tuple[NodeId, bool, str, str, str, int]] = set()
        self._by_name = {family.name: family for family in session.families}

    # -- nodes ---------------------------------------------------------------------------------

    def node(self, node_id: NodeId) -> FrameNode:
        return self._nodes.get(node_id) or self.tree._store.nodes[node_id]

    def has_node(self, node_id: NodeId) -> bool:
        return node_id in self._nodes or node_id in self.tree._store.nodes

    def add_root(self, board: chess.Board, known_plies: int) -> None:
        self._add_node(
            node_id=self.tree.root,
            board=board,
            parent=None,
            move=None,
            known_plies=known_plies,
            pieces=identity.root_pieces(board),
            after_terminal=self.session.ended_before_root,
        )

    def add_child(self, step: _Step) -> None:
        if self.has_node(step.child):
            return
        parent = self.node(step.parent)
        before = chess.Board(parent.fen)
        moved = identity.advance(before, step.move, parent.pieces)
        self._steps[step.child] = moved
        after = before.copy(stack=False)
        after.push(step.move)
        self.pending.edges.append(
            Edge(child=step.child, parent=step.parent, move=step.move.uci(), rev=self.pending.rev)
        )
        self._add_node(
            node_id=step.child,
            board=after,
            parent=parent,
            move=step.move,
            known_plies=parent.known_plies + 1,
            pieces=moved.pieces_after,
            after_terminal=parent.after_terminal or parent.terminal.ends_game,
        )

    def _add_node(
        self,
        *,
        node_id: NodeId,
        board: chess.Board,
        parent: FrameNode | None,
        move: chess.Move | None,
        known_plies: int,
        pieces: tuple[Any, ...],
        after_terminal: bool,
    ) -> None:
        key = PositionKey.of(board)
        # The header (`terminal`) needs `status` and `draw` before the node exists; both
        # require POSITION records only.
        status: StatusFacts = self._position(self._by_name["status"], key)
        draw_family = self._by_name["draw"]
        history = self._history(parent, board.halfmove_clock, known_plies)
        draw: DrawFacts = draw_family.compute(
            FamilyContext(board=board, records={"status": status}, history=history)
        )
        self._store_record(draw_family, node_id, draw)
        node = FrameNode(
            node_id=node_id,
            rev=self.pending.rev,
            parent=None if parent is None else parent.node_id,
            incoming_move=None if move is None else move.uci(),
            mover=None if parent is None else parent.side_to_move,
            ply=0 if parent is None else parent.ply + 1,
            fen=node_fen(board),
            position_key=key,
            side_to_move=Color.of(board.turn),
            fullmove_number=board.fullmove_number,
            halfmove_clock=board.halfmove_clock,
            known_plies=known_plies,
            history_complete=known_plies >= board.halfmove_clock,
            terminal=terminal(status, draw),
            after_terminal=after_terminal,
            pieces=pieces,
        )
        self._nodes[node_id] = node
        self.pending.nodes.append(node)
        # F2: every node is an input-role node, so the eager set applies to all of them.
        for family in self.session.eager:
            self.resolve(family, node_id)

    def _history(
        self, parent: FrameNode | None, halfmove_clock: int, known_plies: int
    ) -> HistoryWindow:
        depth = min(halfmove_clock, known_plies)
        keys: list[PositionKey] = []
        current = parent
        while current is not None and len(keys) < depth:
            keys.append(current.position_key)
            current = None if current.parent is None else self.node(current.parent)
        in_tree = len(keys)  # when the walk reached the root, this is the node's ply
        pre_root = self.session.pre_root_keys  # oldest first; the last one is the root's parent
        keys.extend(pre_root[-(distance - in_tree + 1)] for distance in range(in_tree, depth))
        return HistoryWindow(keys=tuple(keys), unknown_plies=max(0, halfmove_clock - known_plies))

    def _key_board(self, key: PositionKey) -> chess.Board:
        board = self._boards.get(key)
        if board is None:
            board = self._boards[key] = key_board(key)
        return board

    def _board(self, node: FrameNode) -> chess.Board:
        board = self._boards.get(node.node_id)
        if board is None:
            board = self._boards[node.node_id] = chess.Board(node.fen)
        return board

    def _step(self, node: FrameNode) -> IdentityStep:
        """The identity step of the edge into `node` (recomputed for committed edges)."""

        step = self._steps.get(node.node_id)
        if step is None:
            assert node.parent is not None and node.incoming_move is not None
            parent = self.node(node.parent)
            move = chess.Move.from_uci(node.incoming_move)
            step = identity.advance(self._board(parent), move, parent.pieces)
            self._steps[node.node_id] = step
        return step

    # -- facts ---------------------------------------------------------------------------------

    def resolve(self, family: FactFamily, node_id: NodeId) -> Any:
        """The record of `family` for `node_id`: present, or computed now with its dependencies.

        Returns None for an EDGE family at the root, which has no incoming edge.
        """

        node = self.node(node_id)
        if family.scope is Scope.POSITION:
            return self._position(family, node.position_key)
        if family.scope is Scope.EDGE and node.parent is None:
            return None
        cache_key = (family.name, node_id)
        if cache_key in self._records:
            return self._records[cache_key]
        stored = self.tree._store.facts.get(cache_key)
        if stored is not None:
            self._records[cache_key] = stored.record
            return stored.record
        if family.scope is Scope.NODE:
            record = family.compute(
                FamilyContext(
                    board=self._board(node),
                    records=self._requires(family, node),
                    history=self._history(
                        None if node.parent is None else self.node(node.parent),
                        node.halfmove_clock,
                        node.known_plies,
                    ),
                )
            )
        elif family.scope is Scope.EDGE:
            record = self._edge(family, node)
        else:
            record = self._span(family, node)
        self._store_record(family, node_id, record)
        return record

    def _position(self, family: FactFamily, key: PositionKey) -> Any:
        """A POSITION record, computed once per key from a board rebuilt from the key alone."""

        cache_key = (family.name, key)
        if cache_key in self._records:
            return self._records[cache_key]
        stored = self.tree._store.facts.get(cache_key)
        if stored is not None:
            record = stored.record
        else:
            required = {name: self._position(self._by_name[name], key) for name in family.requires}
            record = family.compute(FamilyContext(board=self._key_board(key), records=required))
            self._store_record(family, key, record)
        self._records[cache_key] = record
        return record

    def _requires(
        self, family: FactFamily, node: FrameNode, *, edge: bool = False
    ) -> dict[str, Any]:
        """Required records on one node; EDGE requirements only for this edge (`edge=True`)."""

        out: dict[str, Any] = {}
        for name in family.requires:
            required = self._by_name[name]
            if required.scope is Scope.EDGE and not edge:
                continue
            out[name] = self.resolve(required, node.node_id)
        return out

    def _edge(self, family: FactFamily, node: FrameNode) -> Any:
        assert node.parent is not None and node.incoming_move is not None
        parent = self.node(node.parent)
        step = self._step(node)
        return family.compute(
            FamilyContext(
                board=self._board(node),
                records=self._requires(family, node, edge=True),
                parent_board=self._board(parent),
                move=chess.Move.from_uci(node.incoming_move),
                identity=step,
                parent_records=self._requires(family, parent),
                pieces_maps=(parent.pieces, node.pieces),
                identity_steps=(step,),
            )
        )

    def _span(self, family: FactFamily, node: FrameNode) -> Any:
        if node.ply < 2:
            return NO_GRANDPARENT
        assert node.parent is not None
        parent = self.node(node.parent)
        assert parent.parent is not None
        grandparent = self.node(parent.parent)
        return family.compute(
            FamilyContext(
                board=self._board(node),
                records=self._requires(family, node),
                grandparent_records=self._requires(family, grandparent),
                pieces_maps=(grandparent.pieces, parent.pieces, node.pieces),
                identity_steps=(self._step(parent), self._step(node)),
            )
        )

    def _store_record(self, family: FactFamily, target: PositionKey | NodeId, record: Any) -> None:
        self._records[(family.name, target)] = record
        self.pending.facts.append(
            FactEntry(
                family=family.name,
                version=family.version,
                fact_class=family.fact_class,
                scope=family.scope,
                target=target,
                record=record,
                rev=self.pending.rev,
            )
        )

    # -- roles and lines -----------------------------------------------------------------------

    def add_line(self, plan: _PlannedLine, role: LineRole) -> LineId:
        by = role.by or ""
        index = plan.first_index
        if plan.segment == 0:
            self._role(plan.start, False, role, by, plan.line.label, index)
        nodes = [plan.start]
        for step in plan.steps:
            index += 1
            self._role(step.child, True, role, by, plan.line.label, index)
            self._role(step.child, False, role, by, plan.line.label, index)
            nodes.append(step.child)
        last = self.node(nodes[-1]).terminal
        end, rule = _line_end(last)
        line_id = LineId(role.kind, by, plan.line.label, plan.segment)
        self.pending.lines.append(
            LineRecord(
                line_id=line_id,
                first_index=plan.first_index,
                nodes=tuple(nodes),
                end=end,
                end_rule=rule,
                rev=self.pending.rev,
            )
        )
        return line_id

    def _role(
        self, target: NodeId, on_edge: bool, role: LineRole, by: str, label: str, index: int
    ) -> None:
        key = (target, on_edge, role.kind.value, by, label, index)
        if key in self._roles:
            return
        self._roles.add(key)
        self.pending.roles.append(
            RoleEntry(
                target=target,
                on_edge=on_edge,
                kind=role.kind,
                by=by,
                label=label,
                index=index,
                rev=self.pending.rev,
            )
        )

    def delta(
        self,
        request: str,
        lines: tuple[LineId, ...],
        definitions: tuple[tuple[str, str], ...] = (),
        eager: tuple[str, ...] = (),
    ) -> RevisionDelta:
        counts: dict[str, int] = {}
        for entry in self.pending.facts:
            counts[entry.family] = counts.get(entry.family, 0) + 1
        families = tuple((f.name, f.version, counts.get(f.name, 0)) for f in self.session.families)
        return RevisionDelta(
            rev=self.pending.rev,
            request=request,
            nodes_added=len(self.pending.nodes),
            families=families,
            lines=lines,
            definitions=definitions,
            eager=eager,
        )


def key_board(key: PositionKey) -> chess.Board:
    """The position alone: placement, side, castling, legal en passant; clocks 0, no stack."""

    return chess.Board(f"{key.value} 0 1")


def terminal(status: StatusFacts, draw: DrawFacts) -> Terminal:
    """Node terminal state (§3.2, §7.8): checkmate before any draw rule; `NONE` only if disproved."""

    if status.checkmate:
        return Terminal(TerminalKind.CHECKMATE)
    if status.stalemate:
        return Terminal(TerminalKind.STALEMATE)
    if status.insufficient_material:
        return Terminal(TerminalKind.AUTOMATIC_DRAW, DrawRule.INSUFFICIENT_MATERIAL)
    if draw.seventy_five_move_reached:
        return Terminal(TerminalKind.AUTOMATIC_DRAW, DrawRule.SEVENTY_FIVE_MOVE)
    if draw.fivefold_reached is True:
        return Terminal(TerminalKind.AUTOMATIC_DRAW, DrawRule.FIVEFOLD_REPETITION)
    if isinstance(draw.fivefold_reached, HistoryUnknown):
        return Terminal(TerminalKind.UNPROVEN)
    return Terminal(TerminalKind.NONE)


def _line_end(last: Terminal) -> tuple[LineEnd, DrawRule | None]:
    if last.kind is TerminalKind.CHECKMATE:
        return LineEnd.CHECKMATE, None
    if last.kind is TerminalKind.STALEMATE:
        return LineEnd.STALEMATE, None
    if last.kind is TerminalKind.AUTOMATIC_DRAW:
        return LineEnd.DRAW_RULE, last.rule
    return LineEnd.INPUT_END, None


def _ended_by_rule(board: chess.Board) -> bool:
    """A known pre-root position that ended the game by rule (proven on the known stack).

    Checkmate and stalemate cannot precede a move. Fivefold is counted on the known stack only,
    so a `True` here is proven; earlier unknown history is not ruled out (`after_terminal` is
    "proven ended before", §3.2).
    """

    return (
        board.is_insufficient_material()
        or board.halfmove_clock >= 150
        or board.is_fivefold_repetition()
    )


def _parse(board: chess.Board, text: str, label: str, ply: int) -> chess.Move:
    try:
        return canonical_move(board, text)
    except MoveRejectedError as error:
        raise IllegalMoveError(label, ply, text, str(error)) from None


def _check_budget(budget: SessionBudget, *, nodes_after: int) -> None:
    if budget.max_nodes is not None and nodes_after > budget.max_nodes:
        raise BudgetExceededError(
            f"the request needs {nodes_after} nodes in total; the session allows {budget.max_nodes}"
        )
