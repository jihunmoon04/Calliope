"""Mechanisms tied to the decisive capture (R2-D §3.7): fork, pin, skewer, discovery.

A mechanism builds on a SUPPORTED material consequence `X` and is read on `X`'s line. Candidates
are scanned from the start of the line; the first whose `REALIZED` check passes is the claim
(`EXPLAINS → X`); otherwise the earliest candidate is `ASSOCIATED_WITH → X`; with none it is
REFUTED. A missing record stops the scan before any qualifying candidate: NEEDS_EVIDENCE.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from calliope.facts import (
    PIECE_ORDER_RANK,
    Absent,
    Color,
    DeltaFacts,
    NodeId,
    PatternDeltaFacts,
    PatternsFacts,
    PieceId,
    PieceType,
    TreeView,
)
from calliope.reasoning.catalogue.base import (
    REQUIRE_LINE,
    B,
    F,
    Template,
    lines,
    materials,
    mover,
    needs,
    opponent,
    refuted,
    scope,
    supported,
    supported_claims,
)
from calliope.reasoning.findings import DecisiveEvent, MaterialFinding, MechanismFinding
from calliope.reasoning.hypotheses import (
    ClaimRole,
    Hypothesis,
    LineContext,
    PremiseRelation,
    PremiseUse,
    ProposeContext,
    RelationDecl,
    RelationKind,
    SearchCompat,
)
from calliope.reasoning.lines import (
    UNSAFE_POLICY,
    Line,
    decisive_event,
    fact_ref,
    pieces,
    unsafe,
)
from calliope.reasoning.needs import FamilyNeed
from calliope.reasoning.refs import Evidence, MoveRef, PieceRef
from calliope.reasoning.verification import REALIZED, CausalCheck, Verdict

CONSEQUENCES = ("material_loss_v1", "material_gain_v1")
POLICIES = ("points_v1", "quality_v1", UNSAFE_POLICY)


@dataclass(frozen=True, slots=True)
class Scene:
    """What a mechanism scan reads from its premise's line."""

    view: TreeView
    line: Line
    loss: bool
    event: DecisiveEvent
    v: PieceId  # the lost (or won) piece
    w: PieceId  # the capturer
    s: Color  # the beneficiary


@dataclass(frozen=True, slots=True)
class Candidate:
    finding: MechanismFinding
    node: NodeId  # the node where the configuration appeared
    check: object  # a callable returning (passed: bool | None, needs, evidence)


def _ref(view: TreeView, piece: PieceId, node: NodeId) -> PieceRef:
    square = view.node(node).square_of(piece)
    assert square is not None
    return PieceRef(piece, node, square)


def _piece_type(view: TreeView, piece: PieceId, node: NodeId) -> PieceType | None:
    record = pieces(view, node)
    square = view.node(node).square_of(piece)
    if record is None or square is None:
        return None
    entry = record.at(square)
    return entry.piece_type if entry is not None else None


def _record(view: TreeView, family: str, node: NodeId, kind: type):
    record = view.fact(family, node)
    return record if isinstance(record, kind) else None


def _pieces_ref(view: TreeView, piece: PieceId, node: NodeId) -> Evidence | None:
    record = pieces(view, node)
    square = view.node(node).square_of(piece)
    if record is None or square is None:
        return None
    index = next(i for i, p in enumerate(record.pieces) if p.square == square)
    return fact_ref(view, "pieces", node, ("pieces", index))


def _safe(scene: Scene, node: NodeId) -> tuple[bool | None, tuple[FamilyNeed, ...]]:
    result = unsafe(scene.view, scene.v, node)
    if result is None:
        return None, (FamilyNeed(node, "pieces"),)
    return not result, ()


class _Mechanism(Template):
    role = ClaimRole.MECHANISM
    directions = frozenset({F, B})
    relations = (
        RelationDecl(RelationKind.EXPLAINS, "material_loss_v1"),
        RelationDecl(RelationKind.EXPLAINS, "material_gain_v1"),
    )
    # (family, offset): the records the scan reads at node `i + offset` for each step `i`
    reads: tuple[tuple[str, int], ...] = ()

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        found = materials(ctx)
        if found is None:
            return ()
        ref, _by_rank = found
        out = []
        for name in CONSEQUENCES:
            for claim in supported_claims(ctx, name):
                finding = next(f for f in claim.verdict.findings if isinstance(f, MaterialFinding))
                if finding.event.victim is None or finding.event.capturer is None:
                    continue  # a promotion: no mechanism (R2-D §1.5)
                at = claim.hypothesis.target.at
                use = PremiseUse(
                    claim.id, REQUIRE_LINE, PremiseRelation.SAME_CONTEXT, SearchCompat.SAME_SEARCH
                )
                out.append(
                    self.make(
                        ctx,
                        context=LineContext(at),
                        operands=(claim.id, claim.hypothesis.operands[0]),
                        target=claim.hypothesis.target,
                        premises=(use,),
                        origins=(ref,),
                    )
                )
        return tuple(out)

    def _scene(self, h: Hypothesis, view: TreeView) -> Scene:
        _claim, window = h.operands
        (line,) = lines(view, h, (window,))
        assert line.outcome.delta is not None
        loss = line.outcome.delta < 0
        event = decisive_event(line, loss)
        assert event is not None and event.victim is not None and event.capturer is not None
        m = mover(view, h)
        s = opponent(m) if loss else m
        return Scene(view, line, loss, event, event.victim.piece, event.capturer.piece, s)

    def _steps(self, scene: Scene) -> range:
        return range(1, scene.event.ply)

    def _candidates(self, scene: Scene, i: int) -> Iterator[Candidate]:
        raise NotImplementedError

    def verify(self, h: Hypothesis, view: TreeView) -> Verdict:
        scene = self._scene(h, view)
        nodes = scene.line.nodes
        first: Candidate | None = None
        for i in self._steps(scene):
            missing = tuple(
                FamilyNeed(nodes[i + offset], family)
                for family, offset in self.reads
                if not _present(view, family, nodes[i + offset])
            )
            if missing:  # rule 1: stop at the first node with a missing record
                return needs(h, missing)
            for candidate in self._candidates(scene, i):
                passed, wanted, evidence = candidate.check()
                if passed is None:
                    return needs(h, wanted)  # rule 1: an undecided candidate
                if passed:
                    return self._supported(h, scene, candidate, True, evidence)  # rule 2
                first = first or candidate
        if first is None:
            return refuted(h)  # rule 4
        _passed, _wanted, evidence = first.check()
        return self._supported(h, scene, first, False, evidence)  # rule 3

    def _supported(self, h, scene: Scene, candidate: Candidate, passed: bool, evidence) -> Verdict:
        evidence = tuple(e for e in evidence if e is not None)
        check = CausalCheck(REALIZED, passed, evidence)
        proof = scope(scene.view, h, (scene.line.rank,), line=scene.line, policies=POLICIES)
        return supported(h, proof, (candidate.finding, check), evidence)


def _present(view: TreeView, family: str, node: NodeId) -> bool:
    return view.fact_entry(family, node) is not None


def _allowed(scene: Scene, i: int) -> bool | None:
    """`walked_into` if the configuration may count, else None (R2-D §3.7, E7).

    The beneficiary made it appear (False), or — for a loss — the played move walked into it
    (True).
    """

    if scene.view.node(scene.line.nodes[i]).mover is scene.s:
        return False
    if scene.loss and i == 1:
        return True
    return None


class Fork(_Mechanism):
    name = "fork_v1"
    predicate = "fork"
    reads = (("pattern_delta", 0), ("pieces", -1))

    def _candidates(self, scene: Scene, i: int) -> Iterator[Candidate]:
        view, node, before = scene.view, scene.line.nodes[i], scene.line.nodes[i - 1]
        walked = _allowed(scene, i)
        if walked is None:
            return
        delta = _record(view, "pattern_delta", node, PatternDeltaFacts)
        for change in delta.multi_target_attacks:
            after = change.after
            if isinstance(after, Absent) or scene.v not in after or len(after) < 2:
                continue
            if scene.v in change.before and len(change.before) >= 2:
                continue
            actor = change.piece
            finding = MechanismFinding(
                "fork",
                node,
                MoveRef(node),
                _ref(view, actor, node),
                tuple(_ref(view, t, node) for t in after),
                walked,
            )

            def check(actor=actor, after=after, node=node, before=before):
                evidence = [fact_ref(view, "pattern_delta", node, ("multi_target_attacks",))]
                safe, wanted = _safe(scene, before)
                if safe is None:
                    return None, wanted, evidence
                evidence.append(_pieces_ref(view, scene.v, before))
                if not safe or scene.w != actor:
                    return False, (), evidence
                own = _piece_type(view, actor, node)
                if own is None:
                    return None, (FamilyNeed(node, "pieces"),), evidence
                for target in after:
                    if target == scene.v:
                        continue
                    kind = _piece_type(view, target, node)
                    if kind is PieceType.KING or PIECE_ORDER_RANK[kind] >= PIECE_ORDER_RANK[own]:
                        return True, (), evidence
                    if unsafe(view, target, node):
                        return True, (), evidence  # a real second threat
                return False, (), evidence

            yield Candidate(finding, node, check)


class Pin(_Mechanism):
    name = "pin_v1"
    predicate = "pin"
    reads = (("delta", 0), ("pattern_delta", 0), ("pieces", -1))

    def _candidates(self, scene: Scene, i: int) -> Iterator[Candidate]:
        view, node, before = scene.view, scene.line.nodes[i], scene.line.nodes[i - 1]
        walked = _allowed(scene, i)
        if walked is None:
            return
        delta = _record(view, "delta", node, DeltaFacts)
        pattern_delta = _record(view, "pattern_delta", node, PatternDeltaFacts)
        found: list[tuple[object, PieceId, tuple[PieceId, ...], str, tuple]] = []
        for pin in delta.pins.began:
            if pin.pinned == scene.v:
                targets = (pin.pinned, pin.king)
                found.append((pin, pin.pinner, targets, "delta", ("pins", "began")))
        for triple in pattern_delta.relative_pins.began:
            if triple.front == scene.v:
                targets = (triple.front, triple.back)
                path = ("relative_pins", "began")
                found.append((triple, triple.slider, targets, "pattern_delta", path))
        for relation, actor, targets, family, path in found:
            finding = MechanismFinding(
                "pin",
                node,
                MoveRef(node),
                _ref(view, actor, node),
                tuple(_ref(view, t, node) for t in targets),
                walked,
            )

            def check(relation=relation, family=family, path=path, i=i, node=node, before=before):
                evidence = [fact_ref(view, family, node, path)]
                safe, wanted = _safe(scene, before)
                if safe is None:
                    return None, wanted, evidence
                evidence.append(_pieces_ref(view, scene.v, before))
                if not safe:
                    return False, (), evidence
                return _pin_holds(scene, relation, family, i, evidence)

            yield Candidate(finding, node, check)


def _pin_holds(scene: Scene, relation, family: str, i: int, evidence: list):
    """The same pin — pinner, pinned piece and the piece behind, by `PieceId` — begun at `N_i`
    never ends on the edges up to `N_{q−1}` and holds there (R2-D §3.7; R2b review B2)."""

    view, nodes = scene.view, scene.line.nodes
    q = scene.event.ply
    wanted: list[FamilyNeed] = []
    for j in range(i + 1, q):
        record = view.fact(family, nodes[j])
        if not isinstance(record, DeltaFacts | PatternDeltaFacts):
            wanted.append(FamilyNeed(nodes[j], family))
            continue
        ended = record.pins.ended if family == "delta" else record.relative_pins.ended
        if relation in ended:
            return False, (), evidence  # released on the way: not this pin
    last = nodes[q - 1]
    position = view.node(last)
    square = position.square_of(scene.v)
    if family == "delta":
        record = pieces(view, last)
        if record is None:
            wanted.append(FamilyNeed(last, "pieces"))
        elif square is not None:
            entry = record.at(square)
            pin = entry.absolutely_pinned if entry is not None else None
            if pin is None or pin.pinner != position.square_of(relation.pinner):
                return False, (), evidence
            evidence.append(_pieces_ref(view, scene.v, last))
    else:
        patterns = _record(view, "patterns", last, PatternsFacts)
        if patterns is None:
            wanted.append(FamilyNeed(last, "patterns"))
        else:
            slider, back = position.square_of(relation.slider), position.square_of(relation.back)
            index = next(
                (
                    k
                    for k, line in enumerate(patterns.relative_pins)
                    if (line.slider.square, line.front.square, line.back.square)
                    == (slider, square, back)
                ),
                None,
            )
            if index is None:
                return False, (), evidence
            evidence.append(fact_ref(view, "patterns", last, ("relative_pins", index)))
    if wanted:
        return None, tuple(wanted), evidence
    return True, (), evidence


class Skewer(_Mechanism):
    name = "skewer_v1"
    predicate = "skewer"
    reads = (("pattern_delta", 0), ("pieces", -1))

    def _candidates(self, scene: Scene, i: int) -> Iterator[Candidate]:
        view, node, before = scene.view, scene.line.nodes[i], scene.line.nodes[i - 1]
        walked = _allowed(scene, i)
        if walked is None:
            return
        pattern_delta = _record(view, "pattern_delta", node, PatternDeltaFacts)
        for triple in pattern_delta.skewers.began:
            if triple.back != scene.v:
                continue
            finding = MechanismFinding(
                "skewer",
                node,
                MoveRef(node),
                _ref(view, triple.slider, node),
                (_ref(view, triple.front, node), _ref(view, triple.back, node)),
                walked,
            )

            def check(slider=triple.slider, node=node, before=before):
                evidence = [fact_ref(view, "pattern_delta", node, ("skewers", "began"))]
                safe, wanted = _safe(scene, before)
                if safe is None:
                    return None, wanted, evidence
                evidence.append(_pieces_ref(view, scene.v, before))
                return (safe and scene.w == slider), (), evidence

            yield Candidate(finding, node, check)


class Discovery(_Mechanism):
    """Read around the uncovering move `N_i → N_{i+1}` by the beneficiary (R2-D §3.7)."""

    name = "discovery_v1"
    predicate = "discovery"
    reads = (("patterns", 0), ("pieces", 0), ("pieces", 1))

    def _steps(self, scene: Scene) -> range:
        return range(scene.event.ply - 1)

    def _candidates(self, scene: Scene, i: int) -> Iterator[Candidate]:
        view, nodes = scene.view, scene.line.nodes
        here, after = nodes[i], nodes[i + 1]
        if view.node(here).side_to_move is not scene.s:
            return
        patterns = _record(view, "patterns", here, PatternsFacts)
        record, later = pieces(view, here), pieces(view, after)
        position, next_position = view.node(here), view.node(after)
        move = view.fact("move", after)
        v_here, v_after = position.square_of(scene.v), next_position.square_of(scene.v)
        for index, line in enumerate(patterns.discovery_lines):
            if record.at(line.slider.square).color is not scene.s:
                continue
            slider = position.piece_at(line.slider.square)
            blocker = position.piece_at(line.front.square)
            if next_position.square_of(blocker) == line.front.square:
                continue  # the blocker did not move
            slider_after = next_position.square_of(slider)
            blocker_after = next_position.square_of(blocker)
            opened = (
                slider_after is not None
                and v_after is not None
                and v_after in later.at(slider_after).attacks.enemy
                and (v_here is None or v_here not in record.at(line.slider.square).attacks.enemy)
            )
            back = record.at(line.back.square)
            checked = (
                move.gives_check
                and back.piece_type is PieceType.KING
                and back.color is not scene.s
                and slider_after is not None
                and line.back.square in later.at(slider_after).attacks.enemy
                and blocker_after is not None
                and v_after is not None
                and v_after in later.at(blocker_after).attacks.enemy
            )
            if not (opened or checked):
                continue
            finding = MechanismFinding(
                "discovery",
                after,
                MoveRef(after),
                _ref(view, slider, here),
                (_ref(view, scene.v, after),),
                False,
            )

            def check(slider=slider, blocker=blocker, opened=opened, checked=checked, index=index):
                evidence = [fact_ref(view, "patterns", here, ("discovery_lines", index))]
                safe, wanted = _safe(scene, here)
                if safe is None:
                    return None, wanted, evidence
                evidence.append(_pieces_ref(view, scene.v, here))
                through = (opened and scene.w == slider) or (checked and scene.w == blocker)
                return (safe and through), (), evidence

            yield Candidate(finding, after, check)
