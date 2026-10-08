"""The fact tree: append-only records, one revision per committed request (design F0 §3).

Only the fact engine writes (`_commit`). Readers use `FactTree.view(rev)`; a view never sees a
record whose revision is above its own, so a pinned reader never sees a half-built request.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from calliope.facts.keys import Color, NodeId, PieceId, PositionKey, RootId
from calliope.facts.request import RoleKind
from calliope.facts.values import FactClass, NotApplicable, NotComputed


class Scope(StrEnum):
    POSITION = "position"  # per PositionKey, shared by every node with that position
    NODE = "node"  # path-dependent, per node
    EDGE = "edge"  # parent -> child; keyed by the child node
    SPAN = "span"  # grandparent -> node (from packet F2)


class TerminalKind(StrEnum):
    CHECKMATE = "checkmate"
    STALEMATE = "stalemate"
    AUTOMATIC_DRAW = "automatic_draw"
    UNPROVEN = "unproven"  # an automatic draw is neither proven nor disproved (history unknown)
    NONE = "none"


class DrawRule(StrEnum):
    FIVEFOLD_REPETITION = "fivefold_repetition"
    SEVENTY_FIVE_MOVE = "seventy_five_move"
    INSUFFICIENT_MATERIAL = "insufficient_material"


@dataclass(frozen=True, slots=True)
class Terminal:
    kind: TerminalKind
    rule: DrawRule | None = None

    @property
    def ends_game(self) -> bool:
        return self.kind in (
            TerminalKind.CHECKMATE,
            TerminalKind.STALEMATE,
            TerminalKind.AUTOMATIC_DRAW,
        )


@dataclass(frozen=True, slots=True)
class FrameNode:
    """Immutable node header (§3.2). Facts live in family records; roles are separate entries."""

    node_id: NodeId
    rev: int
    parent: NodeId | None
    incoming_move: str | None  # canonical UCI of the edge into this node
    mover: Color | None  # side that played `incoming_move`
    ply: int  # plies from the root
    fen: str
    position_key: PositionKey
    side_to_move: Color
    fullmove_number: int
    halfmove_clock: int
    known_plies: int  # plies replayed before this node (pre-root moves + path)
    history_complete: bool  # known_plies >= halfmove_clock (§2.2)
    terminal: Terminal
    after_terminal: bool  # an ancestor ended the game by rule (§2.3)
    pieces: tuple[tuple[str, PieceId], ...]  # square -> physical piece, canonical square order

    def piece_at(self, square: str) -> PieceId | None:
        return next((pid for sq, pid in self.pieces if sq == square), None)

    def square_of(self, piece: PieceId) -> str | None:
        return next((sq for sq, pid in self.pieces if pid == piece), None)


@dataclass(frozen=True, slots=True)
class Edge:
    """The move from `parent` to `child`; edges are identified by their child node."""

    child: NodeId
    parent: NodeId
    move: str
    rev: int


@dataclass(frozen=True, slots=True, order=True)
class RoleEntry:
    """A node or edge lies on an input line at ply `index` (§3.2). Edge roles index the move."""

    target: NodeId
    on_edge: bool
    kind: RoleKind
    by: str
    label: str
    index: int
    rev: int


class LineEnd(StrEnum):
    INPUT_END = "input_end"
    CHECKMATE = "checkmate"
    STALEMATE = "stalemate"
    DRAW_RULE = "draw_rule"


@dataclass(frozen=True, slots=True, order=True)
class LineId:
    """Identity of one segment of an input line; a structured key, never a joined string."""

    kind: RoleKind
    by: str
    label: str
    segment: int

    @property
    def stem(self) -> tuple[RoleKind, str, str]:
        return (self.kind, self.by, self.label)

    def __str__(self) -> str:
        return f"{self.kind.value}[{self.by!r}]:{self.label!r}#{self.segment}"


@dataclass(frozen=True, slots=True)
class LineRecord:
    """One committed segment of an input line. A label continues across `extend` calls."""

    line_id: LineId
    first_index: int  # role index of `nodes[0]`
    nodes: tuple[NodeId, ...]
    end: LineEnd
    end_rule: DrawRule | None
    rev: int

    @property
    def kind(self) -> RoleKind:
        return self.line_id.kind

    @property
    def label(self) -> str:
        return self.line_id.label

    @property
    def segment(self) -> int:
        return self.line_id.segment


@dataclass(frozen=True, slots=True)
class FactEntry:
    family: str
    version: str
    fact_class: FactClass
    scope: Scope
    target: PositionKey | NodeId
    record: Any
    rev: int


@dataclass(frozen=True, slots=True)
class RevisionDelta:
    """Manifest entry of one revision (§3.3)."""

    rev: int
    request: str  # "open" | "extend"
    nodes_added: int
    families: tuple[tuple[str, str, int], ...]  # (family, version, records added)
    lines: tuple[LineId, ...]
    definitions: tuple[tuple[str, str], ...] = ()  # rule implementations named once, at open


@dataclass(slots=True)
class _Store:
    nodes: dict[NodeId, FrameNode] = field(default_factory=dict)
    edges: dict[NodeId, Edge] = field(default_factory=dict)
    children: dict[NodeId, list[NodeId]] = field(default_factory=dict)
    roles: dict[tuple[NodeId, bool], list[RoleEntry]] = field(default_factory=dict)
    lines: dict[LineId, LineRecord] = field(default_factory=dict)
    line_heads: dict[tuple[RoleKind, str, str], LineRecord] = field(default_factory=dict)
    facts: dict[tuple[str, PositionKey | NodeId], FactEntry] = field(default_factory=dict)
    deltas: list[RevisionDelta] = field(default_factory=list)


@dataclass(slots=True)
class PendingRevision:
    """Records of one request, appended atomically by `FactTree._commit`."""

    rev: int
    nodes: list[FrameNode] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    roles: list[RoleEntry] = field(default_factory=list)
    lines: list[LineRecord] = field(default_factory=list)
    facts: list[FactEntry] = field(default_factory=list)


class FactTree:
    """One analysis session's tree. Append-only; readers go through `view`."""

    def __init__(
        self,
        root_id: RootId,
        root: NodeId,
        families: dict[str, tuple[str, Scope, FactClass]],
        session: object,
    ) -> None:
        self.root_id = root_id
        self.root = root
        self._families = dict(families)  # name -> (version, scope, class), fixed per session
        self._session = session  # the fact engine's private session state
        self._store = _Store()
        self._rev = 0
        self._write_lock = threading.Lock()  # one writer at a time (§3.3)
        self._publish_lock = threading.Lock()

    @property
    def rev(self) -> int:
        return self._rev

    def view(self, rev: int | None = None) -> TreeView:
        latest = self._rev
        if rev is None:
            rev = latest
        if not 0 < rev <= latest:
            raise ValueError(f"revision {rev} is not committed (latest {latest})")
        return TreeView(self, rev)

    # -- writer side (fact engine only) ---------------------------------------------------------

    def _begin(self) -> PendingRevision:
        return PendingRevision(rev=self._rev + 1)

    def _commit(self, pending: PendingRevision, delta: RevisionDelta) -> int:
        store = self._store
        _require_new(store.nodes, (n.node_id for n in pending.nodes), "node")
        _require_new(store.edges, (e.child for e in pending.edges), "edge")
        _require_new(store.lines, (line.line_id for line in pending.lines), "line")
        _require_new(store.facts, ((f.family, f.target) for f in pending.facts), "fact")
        with self._publish_lock:
            for node in pending.nodes:
                store.nodes[node.node_id] = node
                store.children.setdefault(node.node_id, [])
            for edge in pending.edges:
                store.edges[edge.child] = edge
                store.children[edge.parent].append(edge.child)
            for role in pending.roles:
                store.roles.setdefault((role.target, role.on_edge), []).append(role)
            for line in pending.lines:
                store.lines[line.line_id] = line
                store.line_heads[line.line_id.stem] = line
            for entry in pending.facts:
                store.facts[(entry.family, entry.target)] = entry
            store.deltas.append(delta)
            self._rev = pending.rev  # publish last: views of rev r never see r+1 records
        return pending.rev


class TreeView:
    """Read-only access to the tree as of one revision."""

    def __init__(self, tree: FactTree, rev: int) -> None:
        self._tree = tree
        self._store = tree._store
        self.rev = rev

    @property
    def root(self) -> NodeId:
        return self._tree.root

    def _visible(self, rev: int) -> bool:
        return rev <= self.rev

    def has_node(self, node_id: NodeId) -> bool:
        node = self._store.nodes.get(node_id)
        return node is not None and self._visible(node.rev)

    def node(self, node_id: NodeId) -> FrameNode:
        node = self._store.nodes.get(node_id)
        if node is None or not self._visible(node.rev):
            raise KeyError(f"no node {node_id} at rev {self.rev}")
        return node

    def nodes(self) -> tuple[FrameNode, ...]:
        with self._tree._publish_lock:
            nodes = list(self._store.nodes.values())
        return tuple(n for n in nodes if self._visible(n.rev))

    def children(self, node_id: NodeId) -> tuple[NodeId, ...]:
        with self._tree._publish_lock:
            children = list(self._store.children.get(node_id, ()))
        visible = (c for c in children if self.has_node(c))
        return tuple(sorted(visible, key=lambda c: self._store.edges[c].move))

    def edge(self, child: NodeId) -> Edge | None:
        edge = self._store.edges.get(child)
        return edge if edge is not None and self._visible(edge.rev) else None

    def child(self, node_id: NodeId, move_uci: str) -> NodeId | None:
        child = NodeId.child(node_id, move_uci)
        return child if self.has_node(child) else None

    def roles(self, node_id: NodeId, *, on_edge: bool = False) -> tuple[RoleEntry, ...]:
        with self._tree._publish_lock:
            entries = list(self._store.roles.get((node_id, on_edge), ()))
        visible = (r for r in entries if self._visible(r.rev))
        return tuple(sorted(visible, key=_role_order))

    def lines(self) -> tuple[LineRecord, ...]:
        with self._tree._publish_lock:
            lines = list(self._store.lines.values())
        visible = (line for line in lines if self._visible(line.rev))
        return tuple(sorted(visible, key=lambda line: line.line_id))

    def line(self, line_id: LineId) -> LineRecord:
        line = self._store.lines.get(line_id)
        if line is None or not self._visible(line.rev):
            raise KeyError(f"no line {line_id} at rev {self.rev}")
        return line

    def input_line(
        self,
        label: str,
        kind: RoleKind = RoleKind.PLAYED,
        by: str = "",
        segment: int | None = None,
    ) -> LineRecord:
        """A segment of an input line; by default the latest one visible at this revision."""

        if segment is not None:
            return self.line(LineId(kind, by, label, segment))
        head = self._store.line_heads.get((kind, by, label))
        for number in range(-1 if head is None else head.segment, -1, -1):
            line = self._store.lines[LineId(kind, by, label, number)]
            if self._visible(line.rev):
                return line
        raise KeyError(f"no line {label!r} ({kind.value}, by={by!r}) at rev {self.rev}")

    def coverage(self, family: str) -> tuple[tuple[PositionKey | NodeId, int], ...]:
        """Targets that hold a record of `family` at this revision, with the revision that added it."""

        with self._tree._publish_lock:
            entries = [e for (name, _), e in self._store.facts.items() if name == family]
        return tuple((e.target, e.rev) for e in entries if self._visible(e.rev))

    def fact(self, family: str, node_id: NodeId) -> Any:
        """The record of `family` for this node, or a typed reason why there is none."""

        meta = self._tree._families.get(family)
        if meta is None:
            return NotComputed(f"family {family!r} not selected for this session")
        _version, scope, _cls = meta
        node = self.node(node_id)
        if scope is Scope.EDGE and node.parent is None:
            return NotApplicable("the root node has no incoming move")
        target: PositionKey | NodeId = node.position_key if scope is Scope.POSITION else node_id
        entry = self._store.facts.get((family, target))
        if entry is None or not self._visible(entry.rev):
            return NotComputed(f"{family} not computed for {node_id} at rev {self.rev}")
        return entry.record

    def fact_entry(self, family: str, node_id: NodeId) -> FactEntry | None:
        meta = self._tree._families.get(family)
        if meta is None:
            return None
        node = self.node(node_id)
        target = node.position_key if meta[1] is Scope.POSITION else node_id
        entry = self._store.facts.get((family, target))
        return entry if entry is not None and self._visible(entry.rev) else None

    def families(self) -> dict[str, tuple[str, Scope, FactClass]]:
        return dict(self._tree._families)

    def manifest(self) -> tuple[RevisionDelta, ...]:
        with self._tree._publish_lock:
            deltas = list(self._store.deltas)
        return tuple(d for d in deltas if self._visible(d.rev))

    def path(self, node_id: NodeId) -> tuple[NodeId, ...]:
        """Nodes from the root to `node_id`, inclusive."""

        out: list[NodeId] = []
        current: NodeId | None = node_id
        while current is not None:
            out.append(current)
            current = self.node(current).parent
        return tuple(reversed(out))


_KIND_ORDER = {kind: i for i, kind in enumerate(RoleKind)}


def _role_order(role: RoleEntry) -> tuple[int, str, str, int]:
    return (_KIND_ORDER[role.kind], role.by, role.label, role.index)


def _require_new(store: Any, keys: Any, what: str) -> None:
    """Append-only invariant: a commit never replaces a committed record."""

    for key in keys:
        if key in store:
            raise RuntimeError(f"append-only violation: {what} {key} is already committed")
