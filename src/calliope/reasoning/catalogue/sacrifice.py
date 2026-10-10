"""Sacrifice claims (R2-D §3.11): the offer, its soundness and a concrete return.

No label is derived from them in v1 (R2-D E10): BRILLIANT waits for `label_v2`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from calliope.facts import Capture, Color, PieceId, TreeView
from calliope.reasoning.catalogue.base import (
    REQUIRE_OFFER,
    F,
    Template,
    inconclusive,
    judged,
    judgement,
    judgement_ref,
    line_target,
    lines,
    materials,
    mover,
    opponent,
    refuted,
    scope,
    search_id,
    seg,
    supported,
    supported_claims,
)
from calliope.reasoning.findings import (
    CompensationFinding,
    CompensationKind,
    Fate,
    OfferFinding,
    OutcomeKind,
)
from calliope.reasoning.hypotheses import (
    ClaimRole,
    Hypothesis,
    LineContext,
    NodeContext,
    Population,
    PopulationKind,
    PremiseRelation,
    PremiseUse,
    ProposeContext,
    Quantifier,
    SearchCompat,
    VerificationTarget,
)
from calliope.reasoning.lines import (
    Line,
    compare,
    decided,
    event_at,
    event_ref,
    mate_for,
    read_line,
    undecided_reason,
    veto,
)
from calliope.reasoning.observer import Grade, standard_line_ids
from calliope.reasoning.refs import MaterialAmount, SearchRef
from calliope.reasoning.verification import Verdict

GIVE_UP = -2  # the balance after the offer and after the mover's next ply (R2-D §3.11)
TRADED_NET = -1  # an exchange netting at least this gives the piece's value back
SOUND_EXPECTED = 1000  # 0.50 expected points in 1/2000 (`sacrifice_sound_v1`)
OFFER_GRADES = (Grade.BEST, Grade.EXCELLENT)


class State(StrEnum):
    QUALIFIES = "qualifies"
    NOT = "not"
    OPEN = "open"


@dataclass(frozen=True, slots=True)
class Candidate:
    ply: int  # j ∈ {2, 4}
    piece: PieceId  # the given-up piece v_j
    state: State


def _captures(line: Line, ply: int) -> Capture | None:
    move = line.moves[ply - 1]
    return next((e for e in move.events if isinstance(e, Capture)), None)


def candidates(view: TreeView, line: Line) -> tuple[Candidate, ...]:
    """The opponent's captures at plies 2 and 4 of `Lp`, each qualified or open."""

    if not line.counted:
        return ()
    b = line.balances
    baseline = veto(view, line)
    out: list[Candidate] = []
    for j in (2, 4):
        if j > line.k:
            continue
        capture = _captures(line, j)
        if capture is None:
            continue
        if j + 1 <= line.k:
            after, after_b = b[j + 1], (baseline[j + 1] if baseline else None)
        elif line.terminal[j]:
            after, after_b = b[j], (baseline[j] if baseline else None)  # the game ended at j
        else:
            out.append(Candidate(j, capture.piece, State.OPEN))
            continue
        qualifies = b[j] <= GIVE_UP and after <= GIVE_UP
        if baseline is not None:
            assert after_b is not None
            qualifies = qualifies and baseline[j] <= GIVE_UP and after_b <= GIVE_UP
        out.append(Candidate(j, capture.piece, State.QUALIFIES if qualifies else State.NOT))
    return tuple(out)


def fully_examined(line: Line) -> bool:
    """The window reaches ply 5, or the line ends the game within it."""

    return line.k >= 5 or (line.counted and line.terminal[-1])


def _active(line: Line, ply: int) -> bool:
    material = line.flow.plies[ply - 1]
    return (
        material.capture is not None
        or material.promotion is not None
        or line.moves[ply - 1].gives_check
    )


def _run(line: Line, ply: int) -> tuple[int, int]:
    start = end = ply
    while start > 1 and _active(line, start - 1):
        start -= 1
    while end < line.k and _active(line, end + 1):
        end += 1
    return start, end


def exchange(line: Line, ply: int, m: Color) -> int | None:
    """The net of the exchange around the capture at `ply`; None while it is unfinished.

    The run of consecutive capturing, promoting or checking plies around `ply`, extended to the
    run of the mover's recapture of the capturer at `ply + 1` or `ply + 3` (R2-D §3.11 step 3).
    """

    start, end = _run(line, ply)
    capturer = line.moves[ply - 1].piece
    for later in (ply + 1, ply + 3):
        if later > line.k or line.moves[later - 1].mover is not m:
            continue
        capture = _captures(line, later)
        if capture is not None and capture.piece == capturer:
            end = max(end, _run(line, later)[1])
            break
    if end == line.k and not line.terminal[end]:
        return None
    return line.balances[end] - line.balances[start - 1]


def fate(line: Line, piece: PieceId, j: int, b_j: int, m: Color) -> Fate:
    """The fate of the given-up piece on an alternative, read from its moves by `PieceId`."""

    if mate_for(line.outcome, opponent(m)):
        return Fate.GIVEN_UP  # 1: the alternative loses the game
    if not line.counted:
        return Fate.UNDECIDED
    captured = next(
        (
            ply
            for ply in range(1, line.k + 1)
            if (c := _captures(line, ply)) is not None and c.piece == piece
        ),
        None,
    )
    if captured is None:  # 2
        result = Fate.PRESERVED if line.k >= j + 1 or line.terminal[-1] else Fate.UNDECIDED
    else:  # 3
        net = exchange(line, captured, m)
        if net is None:
            return Fate.UNDECIDED
        result = Fate.TRADED if net >= TRADED_NET else Fate.GIVEN_UP
    if result is Fate.UNDECIDED or result is Fate.GIVEN_UP:
        return result
    for ply in range(1, line.k + 1):  # 4: no equal loss elsewhere
        if line.moves[ply - 1].mover is m or _captures(line, ply) is None:
            continue
        net = exchange(line, ply, m)
        if net is None:
            return Fate.UNDECIDED  # an unfinished exchange of the mover's piece: not yet keeping
        if net <= b_j:
            return Fate.GIVEN_UP
    return result


KEEPING = (Fate.PRESERVED, Fate.TRADED)


class SacrificeOffer(Template):
    name = "sacrifice_offer_v1"
    role = ClaimRole.FUNCTION
    directions = frozenset({F})
    predicate = "sacrifice_offer"

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        judgement_ = judged(ctx)
        found = materials(ctx)
        if judgement_ is None or found is None or judgement_.grade not in OFFER_GRADES:
            return ()
        ref, by_rank = found
        p = standard_line_ids(judgement_)[0].rank
        windows = (by_rank[p].window, *(by_rank[r].window for r in sorted(by_rank) if r != p))
        lp = read_line(ctx.view, windows[0], ctx.view.node(ctx.subject.parent).side_to_move)
        if not lp.counted or all(j > lp.k or _captures(lp, j) is None for j in (2, 4)):
            return ()  # proposed on a capture by the opponent at ply 2 or 4
        parent = ctx.subject.parent
        assert judgement_.search is not None
        population = Population(PopulationKind.ENGINE_REPORTED, judgement_.search.search_id)
        return (
            self.make(
                ctx,
                context=NodeContext(parent),
                operands=windows,
                target=VerificationTarget(Quantifier.EXISTS_ALTERNATIVE, parent, population),
                origins=(judgement_ref(ctx), ref),
            ),
        )

    def verify(self, h: Hypothesis, view: TreeView) -> Verdict:
        lp, *others = lines(view, h, h.operands)
        m = mover(view, h)
        sid = search_id(h)
        evidence = tuple(SearchRef(sid, line.rank) for line in (lp, *others))
        if lp.outcome.kind is OutcomeKind.MISSING:
            return inconclusive(h, undecided_reason(lp.outcome))  # rule 1
        found = candidates(view, lp)
        qualifying = [c for c in found if c.state is State.QUALIFIES]
        unsettled = any(c.state is State.OPEN for c in found) or not fully_examined(lp)
        if not qualifying:  # rule 2
            return inconclusive(h, "LINE_TOO_SHORT") if unsettled else refuted(h, evidence=evidence)
        fates = {}
        for c in qualifying:  # rule 3: every qualifying j is examined
            b_j = lp.balances[c.ply]
            fates[c.ply] = [(line, fate(line, c.piece, c.ply, b_j, m)) for line in others]
            keeping = [(line, f) for line, f in fates[c.ply] if f in KEEPING]
            if keeping:
                event = event_at(lp, c.ply)
                finding = OfferFinding(
                    MaterialAmount(-b_j),
                    event,
                    tuple((SearchRef(sid, line.rank), f) for line, f in keeping),
                )
                witnesses = tuple(line.fact.move for line, _f in keeping)
                ranks = (lp.rank, *(line.rank for line in others))
                proof = scope(view, h, ranks, witnesses=witnesses)
                return supported(h, proof, (finding,), (*evidence, event_ref(view, event)))
        if not others:  # rule 4
            if view.fact("status", h.subject.parent).legal_move_count == 1:
                return refuted(h, evidence=evidence)
            return inconclusive(h, "SCOPE_SHORT")
        given_up = all(f is Fate.GIVEN_UP for pairs in fates.values() for _line, f in pairs)
        if given_up and not unsettled:
            return refuted(h, evidence=evidence)  # rule 5: a forced loss
        return inconclusive(h, "LINE_TOO_SHORT")  # rule 6


class _OnOffer(Template):
    """A claim about `Lp` that builds on a SUPPORTED offer (`SAME_CONTEXT`, `SAME_SEARCH`)."""

    role = ClaimRole.FUNCTION
    directions = frozenset({F})

    def _operands(self, ctx: ProposeContext, offer, by_rank, p) -> tuple:
        return (by_rank[p].window,)

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        judgement_ = judged(ctx)
        found = materials(ctx)
        if judgement_ is None or found is None:
            return ()
        _ref, by_rank = found
        lp_id = standard_line_ids(judgement_)[0]
        at = seg(ctx.view, lp_id)
        if at is None:
            return ()
        out = []
        for offer in supported_claims(ctx, SacrificeOffer.name):
            use = PremiseUse(
                offer.id, REQUIRE_OFFER, PremiseRelation.SAME_CONTEXT, SearchCompat.SAME_SEARCH
            )
            out.append(
                self.make(
                    ctx,
                    context=LineContext(at),
                    operands=self._operands(ctx, offer, by_rank, lp_id.rank),
                    target=line_target(at),
                    premises=(use,),
                    origins=(judgement_ref(ctx),),
                )
            )
        return tuple(out)


class SacrificeSound(_OnOffer):
    """An evaluation, not a return (R2-D §3.11)."""

    name = "sacrifice_sound_v1"
    predicate = "sacrifice_sound"

    def verify(self, h: Hypothesis, view: TreeView) -> Verdict:
        result = judgement(view, h)
        assert result.played is not None
        sid = search_id(h)
        expected = result.played.expected
        finding = CompensationFinding(CompensationKind.ENGINE, expected)
        evidence = (SearchRef(sid, result.played.rank),)
        if result.grade in OFFER_GRADES and expected >= SOUND_EXPECTED:
            return supported(h, scope(view, h, (result.played.rank,)), (finding,), evidence)
        return refuted(h, (finding,), evidence)


class SacrificeCompensated(_OnOffer):
    """A concrete return against the keeping alternatives of the offer (R2-D §3.11)."""

    name = "sacrifice_compensated_v1"
    predicate = "sacrifice_compensated"

    def _operands(self, ctx, offer, by_rank, p) -> tuple:
        (finding,) = (f for f in offer.verdict.findings if isinstance(f, OfferFinding))
        keeping = tuple(by_rank[ref.rank].window for ref, _fate in finding.keeping)
        return (by_rank[p].window, *keeping)

    def verify(self, h: Hypothesis, view: TreeView) -> Verdict:
        result = judgement(view, h)
        assert result.played is not None
        lp, *compared = lines(view, h, h.operands)
        m = mover(view, h)
        sid = search_id(h)
        evidence = tuple(SearchRef(sid, line.rank) for line in (lp, *compared))
        if result.grade not in OFFER_GRADES:
            return refuted(h, evidence=evidence)  # rule 1
        if not decided(lp.outcome):
            return inconclusive(h, undecided_reason(lp.outcome))  # rule 2
        ranks = (lp.rank, *(line.rank for line in compared))
        played_ = lp.outcome
        kind = None
        if mate_for(played_, m) and all(  # rule 3: a faster mate than every keeping line
            not mate_for(line.outcome, m) or line.outcome.moves > played_.moves for line in compared
        ):
            kind = CompensationKind.MATE
        elif (  # rule 4: the material back, and more than every keeping line ends with
            played_.kind is OutcomeKind.STABLE
            and played_.delta >= 0
            and all(
                line.outcome.kind is OutcomeKind.STABLE and line.outcome.delta < played_.delta
                for line in compared
            )
        ):
            kind = CompensationKind.MATERIAL_RETURN
        if kind is not None:
            finding = CompensationFinding(kind, result.played.expected)
            return supported(h, scope(view, h, ranks, line=lp), (finding,), evidence)
        pending = [line.outcome for line in compared if not decided(line.outcome)]
        if pending:
            return inconclusive(h, undecided_reason(pending[0]))  # rule 5
        if any(compare(line.outcome, played_, m) is None for line in compared):
            return inconclusive(h, "UNSTABLE")  # rule 5: DRAWN against STABLE
        return refuted(h, evidence=evidence)  # rule 6
