"""The fact engine: the only writer of fact trees (design F0 §2, §3).

Packets F1–F4: `open`, `extend` and `ensure`, with engine searches when the session has an
engine (F4-D). Every request is validated completely (parsing, legality, labels, budget, known
nodes and families) before anything is built, and commits as one revision; a refused request,
an engine failure included, commits nothing.

Family records are resolved by scope (F2-D §9): POSITION records once per `PositionKey`, from a
board rebuilt from the key; NODE records per node; EDGE records per child node with the parent's
records; SPAN records per node with the grandparent's records. A present record is never
recomputed.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import chess

from calliope.facts import identity
from calliope.facts.board import MoveRejectedError, canonical_move, node_fen, parse_start_fen
from calliope.facts.errors import (
    BudgetExceededError,
    IllegalMoveError,
    InvalidRequestError,
    StoredTreeError,
)
from calliope.facts.families import MANDATORY, REGISTRY, FactFamily, FamilyContext, HistoryWindow
from calliope.facts.families.draw import DrawFacts
from calliope.facts.families.pieces import PIECE_ORDER_V1
from calliope.facts.families.status import StatusFacts
from calliope.facts.identity import IdentityStep
from calliope.facts.keys import Color, NodeId, PositionKey, RootId
from calliope.facts.request import (
    Defaults,
    EnsureRequest,
    ExpansionSpec,
    ExtendRequest,
    InputLine,
    LineRole,
    OpenRequest,
    RoleKind,
    RootSpec,
    SessionBudget,
)
from calliope.facts.search.port import EnginePort
from calliope.facts.search.profile import EngineIdentity, EngineProfile
from calliope.facts.search.records import pinned
from calliope.facts.search.store import EngineResultStore, Searcher
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
    ReplayRecord,
    RevisionDelta,
    RoleEntry,
    Scope,
    Terminal,
    TerminalKind,
)
from calliope.facts.values import HistoryUnknown, NotApplicable

# Engine-only nodes get this tier, intersected with the eager set (F4-D §8.2).
TIER = ("status", "material", "draw", "move")
_DEFAULTS = Defaults()

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
    tier: tuple[FactFamily, ...] = ()  # engine-only nodes (F4-D §8.2)
    engine: EngineProfile | None = None  # None: no attested facts
    identity: EngineIdentity | None = None  # bound at open (F4-D §6.1)
    searcher: Searcher | None = None
    defaults: Defaults = _DEFAULTS


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

    def __init__(
        self,
        families: Sequence[FactFamily] = REGISTRY,
        *,
        engine: EnginePort | None = None,
        store: EngineResultStore | None = None,
    ) -> None:
        """`engine` is owned by the caller (F4-D §3.1); `store` may be shared between engines."""

        _check_registry(families)
        self._registry = {family.name: family for family in families}
        self._port = engine
        self._store = EngineResultStore() if store is None else store
        # F5 replay / rebuild hooks, set only by `storage` on an internal engine
        self._next_record: ReplayRecord | None = None
        self._strict = True
        self._irregular_seed: dict = {}

    # -- open --------------------------------------------------------------------------------

    def open(self, request: OpenRequest) -> FactTree:
        eager = self._select(request.families)
        profile = request.engine
        if profile is not None:
            if not isinstance(profile, EngineProfile):
                raise InvalidRequestError("`engine` must be an EngineProfile")
            if self._port is None:
                raise InvalidRequestError(
                    "an engine profile needs a FactEngine with an engine port"
                )
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
            tier=self._tier(eager),
            engine=profile,
            identity=None if profile is None else self._port.identity,  # type: ignore[union-attr]
            searcher=None if profile is None else self._searcher(profile),
            defaults=request.defaults,
        )
        normalized = OpenRequest(
            root=RootSpec(fen=start.fen(en_passant="fen"), moves=tuple(canonical)),
            families=tuple(f.name for f in eager),
            budget=request.budget,
            engine=profile,
            root_expansion=request.root_expansion,
            defaults=request.defaults,
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
            report = None
            if profile is not None:
                build.role(
                    tree.root, False, RoleKind.ROOT, "", ROOT_LABEL, 0, request.root_expansion
                )
                report = self._engine_work(
                    build, [tree.root], RoleKind.ROOT, request.root_expansion, {}, time.monotonic()
                )
            delta = build.delta(
                "open",
                lines=(),
                definitions=DEFINITIONS,
                eager=tuple(f.name for f in eager),
                report=report,
                engine=_engine_manifest(session),
            )
            self._commit(tree, build, delta, normalized, report)
        return tree

    # -- saved trees (F5-D) ----------------------------------------------------------------

    def load(self, data: bytes, *, rev: int | None = None) -> FactTree:
        """A saved tree, replayed and verified (F5-D §6); refusals raise `StoredTreeError`."""

        from calliope.facts import storage

        return storage.load(self, data, rev=rev)

    def rebuild(self, data: bytes) -> FactTree:
        """A stale saved tree rebuilt under this build: a new tree, never a load (F5-D §7)."""

        from calliope.facts import storage

        return storage.load(self, data, rebuild=True)

    def _searcher(self, profile: EngineProfile) -> Searcher:
        searcher = Searcher(self._port, self._store, profile)  # type: ignore[arg-type]
        searcher._committed.update(self._irregular_seed)  # a replay's irregular tape (F5-D §6.1)
        return searcher

    def _tier(self, eager: tuple[FactFamily, ...]) -> tuple[FactFamily, ...]:
        names = {f.name for f in eager} & set(TIER)
        for family in reversed(self._registry.values()):
            if family.name in names:
                names.update(family.requires)
        return tuple(f for f in self._registry.values() if f.name in names)

    def _engine_work(self, build, nodes, role_kind, expansion, child_moves, started):
        from calliope.facts.engine_work import Decisions, EngineWork

        decisions = None
        if self._next_record is not None:
            record = self._next_record
            decisions = Decisions(
                skips={(node, kind): reason for node, kind, reason in record.skips},
                cuts=frozenset(record.deadline_cuts),
                strict=self._strict,
            )
        work = EngineWork(build, role_kind, expansion, child_moves, started, decisions)
        return work.run(nodes)

    def _commit(self, tree: FactTree, build: _Build, delta: RevisionDelta, request, report) -> int:
        """Commit with the request's log entry (F5-D §5.1); a replay checks its decisions."""

        searcher = build.session.searcher
        record = ReplayRecord(
            skips=() if report is None else tuple(sorted(report.skipped)),
            deadline_cuts=() if report is None else tuple(sorted(report.deadline_cuts)),
            engine_calls=0 if searcher is None else searcher.engine_calls,
        )
        if self._next_record is not None and self._strict:
            expected = self._next_record
            if (record.skips, record.deadline_cuts) != (expected.skips, expected.deadline_cuts):
                raise StoredTreeError("replayed engine decisions differ from the recorded ones")
            record = expected  # the recorded engine calls (F5-D §5.1, save(load(x)) == x)
        rev = tree._commit(build.pending, delta, (request, record))
        if searcher is not None:
            searcher.commit()
        return rev

    # -- extend ------------------------------------------------------------------------------

    def extend(self, tree: FactTree, request: ExtendRequest) -> int:
        session = tree._session
        assert isinstance(session, _Session)
        expansion = self._expansion(session, request)
        with tree._write_lock:
            started = time.monotonic()  # the deadline counts from the lock (F4b-N6)
            plans = self._plan(tree, request)
            if session.searcher is not None:  # validated by `_expansion`; rebound under the lock
                session.searcher.port = self._port  # type: ignore[assignment]
            new_nodes = {s.child for p in plans for s in p.steps} - tree._store.nodes.keys()
            _check_budget(session.budget, nodes_after=len(tree._store.nodes) + len(new_nodes))

            build = _Build(tree, session)
            try:
                for plan in plans:
                    for step in plan.steps:
                        build.add_child(step)
                line_ids = tuple(build.add_line(plan, request.role, expansion) for plan in plans)
                nodes = list(
                    dict.fromkeys(n for p in plans for n in (p.start, *(s.child for s in p.steps)))
                )
                for node_id in nodes:  # role gain: an engine-only node gets the eager set (F2D-N4)
                    for family in session.eager:
                        build.resolve(family, node_id)
                report = None
                if session.engine is not None:
                    child_moves: dict[NodeId, set[str]] = {}
                    for plan in plans:
                        for step in plan.steps:
                            child_moves.setdefault(step.parent, set()).add(step.move.uci())
                    report = self._engine_work(
                        build, nodes, request.role.kind, expansion, child_moves, started
                    )
                delta = build.delta("extend", lines=line_ids, report=report)
                normalized = ExtendRequest(
                    lines=tuple(
                        InputLine(
                            p.line.label, tuple(s.move.uci() for s in p.steps), start=p.line.start
                        )
                        for p in plans
                    ),
                    role=request.role,
                    expansion=expansion,
                )
                return self._commit(tree, build, delta, normalized, report)
            except BaseException:
                if session.searcher is not None:
                    session.searcher.discard()
                raise

    def _expansion(self, session: _Session, request: ExtendRequest) -> ExpansionSpec | None:
        """The request's expansion (F4-D §6.1); None in a session without an engine."""

        if session.engine is None:
            return None
        if self._port is None or self._port.identity != session.identity:
            raise InvalidRequestError("this FactEngine's engine port is not the session's engine")
        if request.expansion is not None:
            return request.expansion
        if request.role.kind is RoleKind.ANALYSIS:
            raise InvalidRequestError("an ANALYSIS request must state its expansion")
        if request.role.kind is RoleKind.PLAYED:
            return session.defaults.played
        return session.defaults.explored

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
            normalized = EnsureRequest(
                _ordered_nodes(request.nodes), tuple(f.name for f in families)
            )
            return self._commit(tree, build, build.delta("ensure", lines=()), normalized, None)

    def _plan(self, tree: FactTree, request: ExtendRequest) -> list[_PlannedLine]:
        return plan_lines(tree, request)

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


def plan_lines(tree: FactTree, request: ExtendRequest) -> list[_PlannedLine]:
    """Canonical steps of every line of `request` on the current tree.

    One rule for `extend` and `planned_search_bound` (reasoning R0-D §6.5).
    """

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

    def add_child(self, step: _Step, *, engine_only: bool = False) -> None:
        """A new child node; an existing one is left as it is (role gain: `FactEngine.extend`)."""

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
            families=self.session.tier if engine_only else self.session.eager,
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
        families: tuple[FactFamily, ...] | None = None,
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
        # input nodes get the eager set; engine-only nodes the tier (F4-D §8.2)
        for family in self.session.eager if families is None else families:
            self.resolve(family, node_id)

    # -- engine work helpers (F4-D §6–§8) --------------------------------------------------------

    def roles_of(self, node_id: NodeId, *, on_edge: bool = False) -> list[RoleEntry]:
        committed = self.tree._store.roles.get((node_id, on_edge), [])
        pending = [r for r in self.pending.roles if r.target == node_id and r.on_edge == on_edge]
        return [*committed, *pending]

    def children_of(self, node_id: NodeId) -> list[NodeId]:
        committed = self.tree._store.children.get(node_id, [])
        pending = [e.child for e in self.pending.edges if e.parent == node_id]
        return [*committed, *pending]

    def is_attached(self, anchor: NodeId, search_id: str) -> bool:
        key = (anchor, search_id)
        return key in self.tree._store.attached or key in self.pending.attached

    def room_for_node(self) -> bool:
        limit = self.session.budget.max_nodes
        return limit is None or len(self.tree._store.nodes) + len(self._nodes) < limit

    def add_engine_child(self, parent: NodeId, child: NodeId, move: chess.Move) -> None:
        self.add_child(_Step(parent, child, move), engine_only=True)

    def engine_role(
        self, target: NodeId, anchor: NodeId, search_id: str, rank: int, pv_index: int
    ) -> None:
        for on_edge in (True, False):
            key = (target, on_edge, f"engine:{anchor}:{search_id}", "", str(rank), pv_index)
            if key in self._roles:
                continue
            self._roles.add(key)
            self.pending.roles.append(
                RoleEntry(
                    target=target,
                    on_edge=on_edge,
                    kind=RoleKind.ENGINE,
                    by="",
                    label="",
                    index=pv_index,
                    rev=self.pending.rev,
                    anchor=anchor,
                    search_id=search_id,
                    rank=rank,
                )
            )

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

    def add_line(
        self, plan: _PlannedLine, role: LineRole, expansion: ExpansionSpec | None = None
    ) -> LineId:
        by = role.by or ""
        index = plan.first_index
        label = plan.line.label
        if plan.segment == 0 or expansion is not None:
            # with an engine, a continued line's start node also gets the request's expansion
            self.role(plan.start, False, role.kind, by, label, index, expansion)
        nodes = [plan.start]
        for step in plan.steps:
            index += 1
            self.role(step.child, True, role.kind, by, label, index, expansion)
            self.role(step.child, False, role.kind, by, label, index, expansion)
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

    def role(
        self,
        target: NodeId,
        on_edge: bool,
        kind: RoleKind,
        by: str,
        label: str,
        index: int,
        expansion: ExpansionSpec | None = None,
    ) -> None:
        key = (target, on_edge, kind.value, by, label, index)
        if key in self._roles:
            return
        committed = self.tree._store.roles.get((target, on_edge), [])
        if any(
            (r.kind, r.by, r.label, r.index, r.expansion) == (kind, by, label, index, expansion)
            for r in committed
        ):
            return
        self._roles.add(key)
        self.pending.roles.append(
            RoleEntry(
                target=target,
                on_edge=on_edge,
                kind=kind,
                by=by,
                label=label,
                index=index,
                rev=self.pending.rev,
                expansion=expansion,
            )
        )

    def delta(
        self,
        request: str,
        lines: tuple[LineId, ...],
        definitions: tuple[tuple[str, str], ...] = (),
        eager: tuple[str, ...] = (),
        report=None,
        engine: tuple[tuple[str, str], ...] = (),
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
            engine=engine,
            searches_run=() if report is None else tuple(sorted(report.runs.items())),
            searches_reused=() if report is None else tuple(sorted(report.reuses.items())),
            skipped=() if report is None else tuple(report.skipped),
            deadline_cuts=() if report is None else tuple(sorted(report.deadline_cuts)),
            engine_lines=() if report is None else tuple(sorted(report.lines.items())),
            load_dependent=False if report is None else report.load_dependent,
        )


def _engine_manifest(session: _Session) -> tuple[tuple[str, str], ...]:
    """The open delta names the profile, the identity and the pinned options (F4-D §8a)."""

    if session.engine is None or session.identity is None:
        return ()
    profile, identity = session.engine, session.identity
    options = pinned(identity, profile, profile.multipv)
    return (
        ("profile", ";".join(profile.fingerprint())),
        ("identity", ";".join(identity.fingerprint())),
        ("pinned_options", ";".join(f"{n}={v}" for n, v in options)),
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


def _ordered_nodes(nodes) -> tuple[NodeId, ...]:
    """An ensure's nodes in one canonical order, whatever collection held them (F5-D §5.1)."""

    return tuple(sorted(set(nodes)))
