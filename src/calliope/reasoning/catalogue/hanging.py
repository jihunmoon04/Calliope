"""Backward mechanisms of a material loss at the played move (R2-D §3.8, §3.8a, §3.8b, E9):
a removed defender, a piece made unsafe, a piece left unsafe.

Each builds on a SUPPORTED `material_loss_v1` on `Lp` and EXPLAINS it only when the lost piece
stayed exposed to its capturer up to the capture (§1.6a).
"""

from __future__ import annotations

from calliope.facts import DefenceEndReason, DeltaFacts, NodeId, PatternDeltaFacts, TreeView
from calliope.reasoning.catalogue.base import (
    REQUIRE_LINE,
    B,
    Template,
    exact_scope,
    lines,
    needs,
    observed,
    refuted,
    scope,
    search_id,
    supported,
    supported_claims,
)
from calliope.reasoning.findings import (
    DefenceFinding,
    HangingFinding,
    HangingKind,
    MaterialFinding,
)
from calliope.reasoning.grading import Grading
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
    Exposure,
    decisive_event,
    event_ref,
    exposure,
    fact_ref,
    pieces,
    unsafe,
)
from calliope.reasoning.needs import FamilyNeed
from calliope.reasoning.refs import Evidence, PieceRef, SearchRef
from calliope.reasoning.verification import REALIZED, CausalCheck, Verdict

LOSS = "material_loss_v1"


def _moved(view: TreeView, piece, parent: NodeId, child: NodeId) -> bool:
    return view.node(parent).square_of(piece) != view.node(child).square_of(piece)


def _ref(view: TreeView, piece, node: NodeId) -> PieceRef:
    square = view.node(node).square_of(piece)
    assert square is not None
    return PieceRef(piece, node, square)


def _attackers(view: TreeView, piece, node: NodeId) -> tuple[PieceRef, ...]:
    record = pieces(view, node)
    square = view.node(node).square_of(piece)
    assert record is not None and square is not None
    entry = record.at(square)
    position = view.node(node)
    return tuple(PieceRef(position.piece_at(a.square), node, a.square) for a in entry.attackers)


def _pieces_refs(view: TreeView, piece, nodes) -> tuple[Evidence, ...]:
    out = []
    for node in nodes:
        record = pieces(view, node)
        square = view.node(node).square_of(piece)
        if record is None or square is None:
            continue
        index = next(i for i, p in enumerate(record.pieces) if p.square == square)
        out.append(fact_ref(view, "pieces", node, ("pieces", index)))
    return tuple(out)


class _OnLoss(Template):
    role = ClaimRole.MECHANISM
    directions = frozenset({B})
    relations = (RelationDecl(RelationKind.EXPLAINS, LOSS),)
    with_best = False  # the operands also carry L1's window

    def _guard(self, ctx: ProposeContext, v, parent: NodeId, child: NodeId) -> bool:
        return True

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        found = observed(ctx, "played_edge")
        if found is None:
            return ()
        ref, _edge = found
        out = []
        for claim in supported_claims(ctx, LOSS):
            finding = next(f for f in claim.verdict.findings if isinstance(f, MaterialFinding))
            victim = finding.event.victim
            if victim is None or finding.event.capturer is None:
                continue
            if not self._guard(ctx, victim.piece, ctx.subject.parent, ctx.subject.child):
                continue
            windows = claim.hypothesis.operands[: 2 if self.with_best else 1]
            use = PremiseUse(
                claim.id, REQUIRE_LINE, PremiseRelation.SAME_CONTEXT, SearchCompat.SAME_SEARCH
            )
            out.append(
                self.make(
                    ctx,
                    context=LineContext(claim.hypothesis.target.at),
                    operands=(claim.id, *windows),
                    target=claim.hypothesis.target,
                    premises=(use,),
                    origins=(ref,),
                )
            )
        return tuple(out)

    def _loss(self, h: Hypothesis, view: TreeView):
        windows = h.operands[1:]
        read = lines(view, h, windows)
        lp = read[0]
        event = decisive_event(lp, loss=True)
        assert event is not None and event.victim is not None and event.capturer is not None
        return read, lp, event, event.victim.piece, event.capturer.piece

    def _check(self, view, v, w, span, extra=()) -> tuple[bool | None, tuple[FamilyNeed, ...]]:
        """`REALIZED`: the conditions in `extra` (each True/False/None with its need) and the
        exposure of `v` to `w` over `span`. A present failing record decides before any need."""

        results = list(extra)
        state, missing = exposure(view, v, w, span)
        results.append(
            (
                {Exposure.EXPOSED: True, Exposure.NOT_EXPOSED: False}.get(state),
                tuple(FamilyNeed(n, "pieces") for n in missing),
            )
        )
        if any(passed is False for passed, _ in results):
            return False, ()
        wanted = tuple(n for passed, ns in results if passed is None for n in ns)
        return (None, wanted) if wanted else (True, ())


class RemovedDefender(_OnLoss):
    """R2-D §3.8: the move ended the defence of the piece later lost."""

    name = "removed_defender_v1"
    predicate = "removed_defender"

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        _read, lp, event, v, w = self._loss(h, view)
        parent, child = h.subject.parent, h.subject.child
        record = view.fact("pattern_delta", child)
        if not isinstance(record, PatternDeltaFacts):
            return needs(h, (FamilyNeed(child, "pattern_delta"),))
        reasons = (DefenceEndReason.DEFENDER_MOVED, DefenceEndReason.LINE_BLOCKED)
        found = next(
            (
                (i, e)
                for i, e in enumerate(record.defences_ended_under_attack)
                if e.defended == v and e.reason in reasons
            ),
            None,
        )
        if found is None:
            path = ("defences_ended_under_attack",)
            return refuted(h, evidence=(fact_ref(view, "pattern_delta", child, path),))
        index, ended = found
        safe_p = unsafe(view, v, parent)
        safe = (None if safe_p is None else not safe_p, (FamilyNeed(parent, "pieces"),))
        span = lp.nodes[1 : event.ply]
        passed, wanted = self._check(view, v, w, span, (safe,))
        if passed is None:
            return needs(h, wanted)
        evidence = (
            fact_ref(view, "pattern_delta", child, ("defences_ended_under_attack", index)),
            *_pieces_refs(view, v, (parent, *span)),
        )
        finding = DefenceFinding(
            _ref(view, ended.defender, parent), _ref(view, v, parent), ended.reason.value
        )
        check = CausalCheck(REALIZED, passed, evidence)
        proof = exact_scope(h, plies=None, policies=(UNSAFE_POLICY,))
        return supported(h, proof, (finding, check), evidence)


class NewlyUnsafe(_OnLoss):
    """R2-D §3.8a: the played move made the lost piece unsafe."""

    name = "newly_unsafe_v1"
    predicate = "newly_unsafe"

    def _guard(self, ctx, v, parent, child) -> bool:
        return _moved(ctx.view, v, parent, child) or unsafe(ctx.view, v, parent) is False

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        _read, lp, event, v, w = self._loss(h, view)
        parent, child = h.subject.parent, h.subject.child
        at_c = unsafe(view, v, child)
        if at_c is None:
            return needs(h, (FamilyNeed(child, "pieces"),))
        if not at_c:
            return refuted(h, evidence=_pieces_refs(view, v, (child,)))  # rule 1
        evidence: list[Evidence] = [fact_ref(view, "move", child)]
        if _moved(view, v, parent, child):
            kind = HangingKind.MOVED_INTO_ATTACK  # rule 2
        else:
            delta = view.fact("delta", child)
            if not isinstance(delta, DeltaFacts):
                return needs(h, (FamilyNeed(child, "delta"),))
            opened = next(
                (
                    i
                    for i, pair in enumerate(delta.piece_attacks.began)
                    if pair.target == v and not _moved(view, pair.source, parent, child)
                ),
                None,
            )
            if opened is None:
                return refuted(h, evidence=tuple(evidence))  # rule 4
            kind = HangingKind.LINE_OPENED  # rule 3
            evidence.append(fact_ref(view, "delta", child, ("piece_attacks", "began", opened)))
        span = lp.nodes[1 : event.ply]
        passed, wanted = self._check(view, v, w, span)
        if passed is None:
            return needs(h, wanted)
        evidence.extend(_pieces_refs(view, v, (parent, *span)))
        check = CausalCheck(REALIZED, passed, tuple(evidence))
        finding = HangingFinding(kind, _ref(view, v, child), _attackers(view, v, child))
        proof = scope(view, h, grading, (lp.rank,), line=lp, extra_policies=(UNSAFE_POLICY,))
        return supported(h, proof, (finding, check), tuple(evidence))


class LeftEnPrise(_OnLoss):
    """R2-D §3.8b: the lost piece was unsafe at P, the move left it, the best line keeps it."""

    name = "left_en_prise_v1"
    predicate = "left_en_prise"
    with_best = True

    def _guard(self, ctx, v, parent, child) -> bool:
        return not _moved(ctx.view, v, parent, child) and unsafe(ctx.view, v, parent) is True

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        read, lp, event, v, w = self._loss(h, view)
        l1 = read[1]
        parent, child = h.subject.parent, h.subject.child
        at_c = unsafe(view, v, child)
        if at_c is None:
            return needs(h, (FamilyNeed(child, "pieces"),))
        evidence: list[Evidence] = [SearchRef(search_id(h), l1.rank)]
        if not at_c:
            return refuted(h, evidence=tuple(evidence))  # rule 1: the move defended it
        best = decisive_event(l1, loss=True)
        if best is not None:
            evidence.append(event_ref(view, best))
            if best.victim is not None and best.victim.piece == v:
                return refuted(h, evidence=tuple(evidence))  # rule 2: L1 loses it too
        span = lp.nodes[0 : event.ply]
        passed, wanted = self._check(view, v, w, span)
        if passed is None:
            return needs(h, wanted)
        evidence.extend(_pieces_refs(view, v, span))
        check = CausalCheck(REALIZED, passed, tuple(evidence))
        finding = HangingFinding(
            HangingKind.LEFT, _ref(view, v, parent), _attackers(view, v, parent)
        )
        proof = scope(view, h, grading, (l1.rank,), line=lp, extra_policies=(UNSAFE_POLICY,))
        return supported(h, proof, (finding, check), tuple(evidence))
