"""Piece relations (MS-D §4, §5; `piece_relations_v1`): what stands between pieces — at a move, or
at a ply of an engine line — by piece identity, with its time.

`move_relations` derives, from the fact tree's records at a move's two nodes, the relations AG8's
`board` reads (AG8-D §2.1, AG8 implementation §2 items 6 and 9): the same rules, moved out of the
agent layer; `limited` applies the board's limits. `claim_relation` reads a relation claim's
relation and its link to the consequence it comes with, from its finding, the records its evidence
names and the claim graph. Neither stores anything with an analysis: they are read from the facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from calliope.facts import (
    POINTS_V1_BY_TYPE,
    Color,
    Defined,
    EngineLineId,
    ExchangeFacts,
    NodeId,
    PatternDeltaFacts,
    PatternsFacts,
    PieceId,
    PiecesFacts,
    PieceType,
    StatusFacts,
    TreeView,
)
from calliope.reasoning.findings import DefenceFinding, HangingFinding, MechanismFinding
from calliope.reasoning.lines import Exposed, exposed
from calliope.reasoning.refs import FactRef, PieceRef
from calliope.reasoning.verification import REALIZED, CausalCheck

FORMAT = "piece_relations_v1"
FAMILIES = ("pieces", "patterns", "exchange", "status", "pattern_delta")  # `move_relations` reads
KINDS = ("attack", "defence", "exposed", "check", "double_attack", "absolute_pin", "relative_pin",
         "skewer", "discovered_attack")  # fmt: skip
TIMES = ("began", "held", "ended")
LOST_REASONS = ("defender_moved", "line_blocked")  # pattern_delta's: the defended piece stayed
LIMITS = {"double_attack": 2, "attack": 3, "exposed": 3, "absolute_pin": 2, "defence": 3}
VALUE = {t.value: v for t, v in POINTS_V1_BY_TYPE.items()} | {"king": 100}  # as `remarks`
RELATION_TEMPLATES = ("removed_defender_v2", "newly_exposed_v1", "left_en_prise_v2", "fork_v2",
                      "pin_v2", "skewer_v2", "discovery_v2")  # fmt: skip
LINKS = ("explains", "causes", "associated_with")  # strongest first


@dataclass(frozen=True, slots=True)
class Piece:
    id: str  # the PieceId (`w.N.g1`)
    color: str
    type: str
    square: str  # at the relation's node (a defender's: before the move)


@dataclass(frozen=True, slots=True)
class Place:
    at: str  # move | line
    ply: int | None = None  # a line's ply, from 1 (the line's first move is ply 1)
    search: str | None = None  # the engine line (review B2): its search's id …
    rank: int | None = None  # … and its rank


MOVE = Place("move")


@dataclass(frozen=True, slots=True)
class PieceRelation:
    kind: str
    roles: tuple[tuple[str, Piece], ...]  # in the kind's order (MS-D §4.1)
    place: Place
    time: str
    side: str  # the side the relation bears on: the attacked, exposed, pinned or defended pieces'
    data: tuple[tuple[str, int], ...] = ()  # gain; defenders and attackers after a lost defence

    def __post_init__(self) -> None:
        # one order whatever read it (review B1): the kind's roles in their first order, the
        # pieces of one role (a double attack's targets, the checkers) by square
        names = list(dict.fromkeys(name for name, _p in self.roles))
        roles = tuple((name, p) for name in names
                      for p in sorted((p for n, p in self.roles if n == name),
                                      key=lambda p: p.square))  # fmt: skip
        object.__setattr__(self, "roles", roles)

    def identity(self) -> tuple:
        """Kind, pieces, place and time: two relations are one only when these are (MS-D §6)."""

        return self.kind, tuple((r, p.id) for r, p in self.roles), self.place, self.time

    def role(self, name: str) -> Piece | None:
        return next((p for r, p in self.roles if r == name), None)


@dataclass(frozen=True, slots=True)
class Link:
    kind: str  # explains | causes | associated_with
    to: str  # the consequence claim's id
    did: str | None = None  # a mechanism's: won (its REALIZED check passed) | configuration


@dataclass(frozen=True, slots=True)
class ClaimRelation:
    relation: PieceRelation
    link: Link | None


# -- reading records -------------------------------------------------------------------------------


class MissingRecord(LookupError):
    """A record `move_relations` reads is not in the tree: the caller ensures `FAMILIES`."""


def _fact(view: TreeView, family: str, node: NodeId, kind: type):
    record = view.fact(family, node)
    if not isinstance(record, kind):
        raise MissingRecord(f"no {family} record at {node}")
    return record


def _piece(view: TreeView, node: NodeId, square: str, pieces: PiecesFacts) -> Piece:
    pid = view.node(node).piece_at(square)
    facts = pieces.at(square)
    assert pid is not None and facts is not None
    return Piece(pid.value, facts.color.value, facts.piece_type.value, square)


def _by_id(view: TreeView, node: NodeId, pieces: PiecesFacts) -> dict[str, str]:
    """PieceId value → square at `node`."""

    frame = view.node(node)
    return {pid.value: sq for sq, pid in frame.pieces}


def _ids(view: TreeView, node: NodeId) -> dict[str, str]:
    """Square → PieceId value at `node`."""

    return {sq: pid.value for sq, pid in view.node(node).pieces}


def _gains(exchange: ExchangeFacts) -> dict[str, int | None]:
    return {
        e.square: e.gain.value if isinstance(e.gain, Defined) else None for e in exchange.pieces
    }


def _value(kind: PieceType | str) -> int:
    return VALUE[kind.value if isinstance(kind, PieceType) else kind]


def _color(pid: PieceId | str) -> str:
    value = pid.value if isinstance(pid, PieceId) else pid
    return Color.WHITE.value if value.startswith("w.") else Color.BLACK.value


def _other(color: str) -> str:
    return Color.BLACK.value if color == Color.WHITE.value else Color.WHITE.value


# -- the relations at a move (MS-D §4.2) ----------------------------------------------------------


def move_relations(view: TreeView, parent: NodeId, child: NodeId) -> tuple[PieceRelation, ...]:
    """Every relation the move `parent → child` began or ended, by AG8's rules, unlimited: checks,
    the mover's new double attacks and attacks, newly exposed pieces and absolute pins of either
    side, the mover's lost defences. Each kind sorted as AG8's `board` sorts it."""

    before_pieces = _fact(view, "pieces", parent, PiecesFacts)
    after_pieces = _fact(view, "pieces", child, PiecesFacts)
    status_before = _fact(view, "status", parent, StatusFacts)
    status = _fact(view, "status", child, StatusFacts)
    delta = _fact(view, "pattern_delta", child, PatternDeltaFacts)
    gain_before = _gains(_fact(view, "exchange", parent, ExchangeFacts))
    gain_after = _gains(_fact(view, "exchange", child, ExchangeFacts))
    _fact(view, "patterns", child, PatternsFacts)
    mover = status_before.side_to_move.value
    enemy = _other(mover)
    ib, ia = _ids(view, parent), _ids(view, child)
    pa = {p.square: p for p in after_pieces.pieces}
    pb = {p.square: p for p in before_pieces.pieces}
    after = lambda sq: _piece(view, child, sq, after_pieces)
    out: list[PieceRelation] = []

    if status.in_check:
        roles = tuple(("checker", after(sq)) for sq in status.checkers)
        out.append(PieceRelation("check", roles, MOVE, "began", enemy))

    actors: set[str] = set()
    doubles = []
    by_square = _by_id(view, child, after_pieces)
    for change in delta.multi_target_attacks:
        if _color(change.piece) != mover or not isinstance(change.after, tuple):
            continue
        if len(change.after) >= 2 and len(change.before) < 2:  # AG8 rev. 4: none before
            actor = by_square[change.piece.value]
            doubles.append((actor, tuple(sorted(by_square[t.value] for t in change.after))))
    for actor, targets in sorted(doubles):
        actors.add(actor)
        roles = (("actor", after(actor)), *(("target", after(t)) for t in targets))
        out.append(PieceRelation("double_attack", roles, MOVE, "began", enemy))

    had = {(ib[s], ib[t]) for s, p in pb.items() if p.color.value == mover for t in p.attacks.enemy}
    attacks = sorted(
        ((s, t) for s, p in pa.items() if p.color.value == mover for t in p.attacks.enemy
         if (ia[s], ia[t]) not in had and pa[t].piece_type is not PieceType.KING
         and s not in actors
         and (pa[t].piece_type is not PieceType.PAWN or (gain_after.get(t) or 0) > 0)),
        key=lambda x: (-_value(pa[x[1]].piece_type), x),
    )  # fmt: skip
    for s, t in attacks:
        roles = (("attacker", after(s)), ("target", after(t)))
        out.append(PieceRelation("attack", roles, MOVE, "began", enemy))

    exposed_before = {ib[s] for s, g in gain_before.items() if s in ib and (g or 0) > 0}
    candidates = sorted(
        (s for s, g in gain_after.items() if (g or 0) > 0 and s in pa and ia[s] not in exposed_before
         and pa[s].piece_type is not PieceType.KING),
        key=lambda s: (-_value(pa[s].piece_type), s),
    )  # fmt: skip
    for color in (enemy, mover):  # AG8: the other side's (threats) before the mover's (weaknesses)
        for s in (s for s in candidates if pa[s].color.value == color):
            if exposed(view, PieceId(ia[s]), child) is not Exposed.EXPOSED:
                continue  # AG8 implementation §2 item 4: no item, not a fault
            gain = gain_after[s]
            assert gain is not None
            out.append(PieceRelation("exposed", (("piece", after(s)),), MOVE, "began", color,
                                     (("gain", gain),)))  # fmt: skip

    had_pins = {(ib[s], ib[p.absolutely_pinned.pinner]) for s, p in pb.items()
                if p.absolutely_pinned is not None}  # fmt: skip
    pins = sorted((s, p.absolutely_pinned.pinner) for s, p in pa.items()
                  if p.absolutely_pinned is not None
                  and (ia[s], ia[p.absolutely_pinned.pinner]) not in had_pins)  # fmt: skip
    for color in (enemy, mover):
        for pinned, pinner in (x for x in pins if pa[x[0]].color.value == color):
            king = next(q.square for q in after_pieces.pieces
                        if q.piece_type is PieceType.KING and q.color.value == color)  # fmt: skip
            roles = (("slider", after(pinner)), ("pinned", after(pinned)), ("king", after(king)))
            out.append(PieceRelation("absolute_pin", roles, MOVE, "began", color))

    by_id_before = _by_id(view, parent, before_pieces)
    found = []
    for ended in delta.defences_ended_under_attack:
        if _color(ended.defended) != mover or ended.reason.value not in LOST_REASONS:
            continue
        square = by_square.get(ended.defended.value)
        gone = by_id_before.get(ended.defender.value)
        if square is None or gone is None:
            continue
        entry = pa[square]
        attackers = sorted(entry.attackers, key=lambda a: (_value(a.piece_type), a.square))
        if attackers and entry.piece_type is not PieceType.KING:
            found.append((square, gone, attackers[0].square, len(entry.defenders), len(attackers)))
    found.sort(key=lambda x: (x[3] - x[4], -_value(pa[x[0]].piece_type), x[0]))
    for square, gone, attacker, defenders, count in found:
        roles = (("defender", _piece(view, parent, gone, before_pieces)),
                 ("defended", after(square)), ("attacker", after(attacker)))  # fmt: skip
        out.append(PieceRelation("defence", roles, MOVE, "ended", mover,
                                 (("defenders", defenders), ("attackers", count))))  # fmt: skip
    return tuple(out)


def limited(relations: tuple[PieceRelation, ...], mover: str) -> tuple[PieceRelation, ...]:
    """AG8's limits (AG8-D §2.1): 2 double attacks, 3 attacks, 3 exposed and 2 absolute pins a
    side, 3 lost defences; checks unlimited."""

    count: dict[tuple[str, str], int] = {}
    out = []
    for r in relations:
        key = (r.kind, r.side if r.kind in ("exposed", "absolute_pin") else "")
        limit = LIMITS.get(r.kind)
        if limit is not None and count.get(key, 0) >= limit:
            continue
        count[key] = count.get(key, 0) + 1
        out.append(r)
    return tuple(out)


def held_exposed(view: TreeView, parent: NodeId, child: NodeId, piece: PieceId) -> str | None:
    """`held` when the piece is exposed (`exposed_v1`) before and after the move, `began` when after
    only, None when not after (or a record is missing)."""

    now = exposed(view, piece, child)
    if now is not Exposed.EXPOSED:
        return None
    then = exposed(view, piece, parent)
    if then is None or then is Exposed.UNDECIDED:
        return None  # undecided before is no proof it was not exposed (review N1)
    return "held" if then is Exposed.EXPOSED else "began"


# -- a relation claim's relation and link (MS-D §5) -----------------------------------------------


class _Views:
    """The analysis's view, and for the move's two nodes the records it lacks from `move_view` (a
    facts tree of the same game: node ids are the same for the same path, `NodeId.child`)."""

    TYPES: ClassVar[dict[str, type]] = {
        "pieces": PiecesFacts, "exchange": ExchangeFacts, "patterns": PatternsFacts,
        "status": StatusFacts, "pattern_delta": PatternDeltaFacts,
    }  # fmt: skip

    def __init__(self, view: TreeView, move_view: TreeView | None) -> None:
        self.view, self.move_view = view, move_view

    def fact(self, family: str, node: NodeId):
        record = self.view.fact(family, node)
        kind = self.TYPES.get(family)
        if self.move_view is None or kind is None or isinstance(record, kind):
            return record
        try:
            other = self.move_view.fact(family, node)
        except Exception:  # noqa: BLE001 — a node the facts tree does not hold
            return record
        return other if isinstance(other, kind) else record

    def node(self, node: NodeId):
        return self.view.node(node)


def claim_relation(analysis, claim, view: TreeView,
                   move_view: TreeView | None = None) -> ClaimRelation | None:  # fmt: skip
    """The relation a SUPPORTED relation claim states and its link to its consequence; None for
    another claim, or when a relation cannot be read whole (MS-D §5: the claim stays unmatched).
    `view` is the analysis's; `move_view`, when given, supplies records the analysis's tree lacks
    at the move's two nodes (an on-request family such as `exchange` before a moved piece)."""

    view = _Views(view, move_view)  # type: ignore[assignment]

    template = claim.hypothesis.template
    if template not in RELATION_TEMPLATES or claim.verdict.status.value != "supported":
        return None
    parent, child = analysis.round_zero.subject.parent, analysis.round_zero.subject.child
    relation = None
    if template == "removed_defender_v2":
        relation = _defence(view, parent, child, _finding(claim, DefenceFinding))
    elif template in ("newly_exposed_v1", "left_en_prise_v2"):
        relation = _hanging(view, parent, child, _finding(claim, HangingFinding))
    else:
        relation = _mechanism(view, parent, child, claim, _finding(claim, MechanismFinding))
    if relation is None:
        return None
    return ClaimRelation(relation, _link(analysis, claim))


def _finding(claim, kind: type):
    return next((f for f in claim.verdict.findings if isinstance(f, kind)), None)


def _ref_piece(view: TreeView, ref: PieceRef, node: NodeId | None = None) -> Piece | None:
    node = ref.node if node is None else node
    square = view.node(node).square_of(ref.piece)
    pieces = view.fact("pieces", node)
    if square is None or not isinstance(pieces, PiecesFacts) or pieces.at(square) is None:
        return None
    facts = pieces.at(square)
    return Piece(ref.piece.value, facts.color.value, facts.piece_type.value, square)


def _defence(view, parent, child, f: DefenceFinding | None) -> PieceRelation | None:
    if f is None:
        return None
    before = view.fact("pieces", parent)
    after = view.fact("pieces", child)
    if not isinstance(before, PiecesFacts) or not isinstance(after, PiecesFacts):
        return None
    defender, defended = _ref_piece(view, f.defender, parent), _ref_piece(view, f.defended, child)
    held_square = view.node(parent).square_of(f.defended.piece)
    if defender is None or defended is None or held_square is None:
        return None
    was = before.at(held_square)
    now = after.at(defended.square)
    if was is None or now is None:
        return None
    ids_before, ids_after = _ids(view, parent), _ids(view, child)
    had = any(ids_before.get(d.square) == defender.id for d in was.defenders)
    has = any(ids_after.get(d.square) == defender.id for d in now.defenders)
    if not had or has:
        return None  # the defence did not end at the move: no relation read whole
    attackers = sorted(now.attackers, key=lambda a: (_value(a.piece_type), a.square))
    roles = [("defender", defender), ("defended", defended)]
    if attackers:
        attacker = _ref_piece(view, PieceRef(PieceId(ids_after[attackers[0].square]), child,
                                             attackers[0].square))  # fmt: skip
        if attacker is not None:
            roles.append(("attacker", attacker))
    return PieceRelation("defence", tuple(roles), MOVE, "ended", defended.color,
                         (("defenders", len(now.defenders)), ("attackers", len(now.attackers))))  # fmt: skip


def _hanging(view, parent, child, f: HangingFinding | None) -> PieceRelation | None:
    if f is None:
        return None
    piece = _ref_piece(view, f.piece, child)
    time = held_exposed(view, parent, child, f.piece.piece)  # MS-D §5 (review N3): from the facts
    if piece is None or time is None:
        return None
    gains = view.fact("exchange", child)
    gain = _gains(gains).get(piece.square) if isinstance(gains, ExchangeFacts) else None
    data = (("gain", gain),) if isinstance(gain, int) else ()
    return PieceRelation("exposed", (("piece", piece),), MOVE, time, piece.color, data)


def _depth(view: TreeView, node: NodeId, parent: NodeId) -> int | None:
    """The ply of `node` on a line from `parent` (the subject's child is ply 1)."""

    k, n = 0, node
    while n is not None and n != parent:
        n = view.node(n).parent
        k += 1
    return k if n == parent else None


def _evidence(claim) -> list[FactRef]:
    refs = [e for e in claim.verdict.evidence if isinstance(e, FactRef)]
    for f in claim.verdict.findings:
        if isinstance(f, CausalCheck):
            refs += [e for e in f.evidence if isinstance(e, FactRef)]
    return refs


def _mechanism(view, parent, child, claim, f: MechanismFinding | None) -> PieceRelation | None:
    if f is None:
        return None
    if f.node == child:
        place = MOVE
    else:  # review B2: the line the claim scanned, from its proof's scope
        segment = claim.verdict.scope.at if claim.verdict.scope is not None else None
        line = getattr(segment, "line", None)
        if not isinstance(line, EngineLineId):
            return None
        ply = _depth(view, f.node, line.anchor)
        if ply is None:
            return None
        place = Place("line", ply, line.search_id, line.rank)
    refs = _evidence(claim)
    actor = _ref_piece(view, f.actor, f.node) or _ref_piece(view, f.actor)
    targets = [_ref_piece(view, t, f.node) for t in f.targets]
    if actor is None or any(t is None for t in targets):
        return None
    if f.kind == "fork":
        if not any(r.family == "pattern_delta" and r.path[:1] == ("multi_target_attacks",)
                   for r in refs):  # fmt: skip
            return None
        roles = (("actor", actor), *(("target", t) for t in targets))
        return PieceRelation("double_attack", roles, place, "began", targets[0].color)
    if f.kind == "pin":
        if any(r.family == "delta" and r.path[:2] == ("pins", "began") for r in refs):
            pinned, king = targets
            roles = (("slider", actor), ("pinned", pinned), ("king", king))
            return PieceRelation("absolute_pin", roles, place, "began", pinned.color)
        if any(r.family == "pattern_delta" and r.path[:2] == ("relative_pins", "began")
               for r in refs):  # fmt: skip
            front, back = targets
            roles = (("slider", actor), ("front", front), ("back", back))
            return PieceRelation("relative_pin", roles, place, "began", front.color)
        return None
    if f.kind == "skewer":
        if not any(
            r.family == "pattern_delta" and r.path[:2] == ("skewers", "began") for r in refs
        ):
            return None
        front, back = targets
        roles = (("slider", actor), ("front", front), ("back", back))
        return PieceRelation("skewer", roles, place, "began", front.color)
    if f.kind == "discovery":
        ref = next((r for r in refs if r.family == "patterns" and r.path[:1] == ("discovery_lines",)
                    and len(r.path) == 2), None)  # fmt: skip
        here = view.node(f.node).parent
        patterns = view.fact("patterns", here) if here is not None else None
        if ref is None or not isinstance(patterns, PatternsFacts):
            return None
        line = patterns.discovery_lines[ref.path[1]]
        front = _ref_piece(view, PieceRef(view.node(here).piece_at(line.front.square), here,
                                          line.front.square))  # fmt: skip
        if front is None:
            return None
        roles = (("slider", actor), ("front", front), *(("target", t) for t in targets))
        return PieceRelation("discovered_attack", roles, place, "began", targets[0].color)
    return None


def _link(analysis, claim) -> Link | None:
    """The claim's strongest relation to a consequence claim (`explains`, `causes`, then
    `associated_with`), and for a mechanism whether its REALIZED check passed."""

    ids = {c.id for c in analysis.claims}
    found = [(r.kind.value, r.target) for r in analysis.relations
             if r.source == claim.id and r.kind.value in LINKS and r.target in ids]  # fmt: skip
    if not found:
        return None
    kind, target = min(found, key=lambda x: (LINKS.index(x[0]), str(x[1])))
    did = None
    if claim.hypothesis.template in ("fork_v2", "pin_v2", "skewer_v2", "discovery_v2"):
        realized = any(isinstance(f, CausalCheck) and f.kind == REALIZED and f.passed
                       for f in claim.verdict.findings)  # fmt: skip
        did = "won" if realized else "configuration"
    return Link(kind, target, did)
