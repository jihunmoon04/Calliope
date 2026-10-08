"""The fact engine: the only writer of fact trees (design F0 §2, §3).

Packet F1 scope: `open` and `extend` without Stockfish. Every request is validated completely
(parsing, legality, labels, budget) before anything is built, and commits as one revision.
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
from calliope.facts.families.status import StatusFacts
from calliope.facts.keys import Color, NodeId, PositionKey, RootId
from calliope.facts.request import ExtendRequest, InputLine, LineRole, OpenRequest, SessionBudget
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
from calliope.facts.values import HistoryUnknown

ROOT_LABEL = "<root>"
DEFINITIONS = (
    ("insufficient_material", f"python-chess {chess.__version__} Board.is_insufficient_material"),
    ("points_v1", "1/3/3/5/9 per pawn/knight/bishop/rook/queen"),
)


@dataclass(frozen=True, slots=True)
class _Session:
    families: tuple[FactFamily, ...]  # selected, in dependency order
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
        self._registry = {family.name: family for family in families}

    # -- open --------------------------------------------------------------------------------

    def open(self, request: OpenRequest) -> FactTree:
        families = self._select(request.families)
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
        session = _Session(
            families=families,
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
        )
        with tree._write_lock:
            build = _Build(tree, session)
            build.add_root(board.copy(stack=False), known_plies=len(canonical))
            tree._commit(build.pending, build.delta("open", lines=(), definitions=DEFINITIONS))
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
        wanted = set(self._registry) if names is None else set(names) | MANDATORY
        unknown = wanted - set(self._registry)
        if unknown:
            raise InvalidRequestError(f"unknown fact families: {sorted(unknown)}")
        selected: list[FactFamily] = []
        for family in self._registry.values():  # registry order is dependency order
            if family.name not in wanted:
                continue
            missing = set(family.requires) - {f.name for f in selected}
            if missing:
                raise InvalidRequestError(f"{family.name} requires {sorted(missing)}")
            selected.append(family)
        return tuple(selected)


class _Build:
    """Records of one request, built against the committed store plus this request's own nodes."""

    def __init__(self, tree: FactTree, session: _Session) -> None:
        self.tree = tree
        self.session = session
        self.pending: PendingRevision = tree._begin()
        self._nodes: dict[NodeId, FrameNode] = {}
        self._position_facts: dict[tuple[str, PositionKey], Any] = {}
        self._roles: set[tuple[NodeId, bool, str, str, str, int]] = set()

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
            edge_context=None,
        )

    def add_child(self, step: _Step) -> None:
        if self.has_node(step.child):
            return
        parent = self.node(step.parent)
        before = chess.Board(parent.fen)
        moved = identity.advance(before, step.move, parent.pieces)
        after = before.copy(stack=False)
        after.push(step.move)
        self._add_node(
            node_id=step.child,
            board=after,
            parent=parent,
            move=step.move,
            known_plies=parent.known_plies + 1,
            pieces=moved.pieces_after,
            after_terminal=parent.after_terminal or parent.terminal.ends_game,
            edge_context=FamilyContext(
                board=after, records={}, parent_board=before, move=step.move, identity=moved
            ),
        )
        self.pending.edges.append(
            Edge(child=step.child, parent=step.parent, move=step.move.uci(), rev=self.pending.rev)
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
        edge_context: FamilyContext | None,
    ) -> None:
        key = PositionKey.of(board)
        records: dict[str, Any] = {}
        history = self._history(parent, board.halfmove_clock, known_plies)
        for family in self.session.families:
            required = {name: records[name] for name in family.requires}
            if family.scope is Scope.POSITION:
                records[family.name] = self._position_record(family, key, board)
            elif family.scope is Scope.NODE:
                ctx = FamilyContext(board=board, records=required, history=history)
                records[family.name] = family.compute(ctx)
                self._fact(family, node_id, records[family.name])
            elif family.scope is Scope.EDGE and edge_context is not None:
                ctx = FamilyContext(
                    board=edge_context.board,
                    records=required,
                    parent_board=edge_context.parent_board,
                    move=edge_context.move,
                    identity=edge_context.identity,
                )
                self._fact(family, node_id, family.compute(ctx))

        status: StatusFacts = records["status"]
        draw: DrawFacts = records["draw"]
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

    # -- facts ---------------------------------------------------------------------------------

    def _position_record(self, family: FactFamily, key: PositionKey, board: chess.Board) -> Any:
        cache_key = (family.name, key)
        if cache_key in self._position_facts:
            return self._position_facts[cache_key]
        stored = self.tree._store.facts.get(cache_key)
        if stored is not None:
            record = stored.record
        else:
            record = family.compute(FamilyContext(board=board, records={}))
            self._fact(family, key, record)
        self._position_facts[cache_key] = record
        return record

    def _fact(self, family: FactFamily, target: PositionKey | NodeId, record: Any) -> None:
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
        )


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
