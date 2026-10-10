"""The rounds of an analysis (R0-D §6.2–§6.4): propose and verify to a fixpoint, then admit and
issue the evidence the open verdicts need, under the budget; record every request's outcome.

The controller stays the only stage that changes the tree (R0-D D2): templates propose and verify
on pinned views and return needs; this runner turns admitted needs into `ensure` / `extend`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from calliope.facts import (
    EnsureRequest,
    ExpansionSpec,
    ExtendRequest,
    FactEngine,
    FactEngineError,
    FactTree,
    IllegalMoveError,
    InputLine,
    InvalidRequestError,
    NodeId,
    analysis,
    planned_search_bound,
)
from calliope.reasoning.controller import Controller, RoundZero
from calliope.reasoning.errors import ReasoningError
from calliope.reasoning.graph import ClaimRelation, relations
from calliope.reasoning.hypotheses import (
    Hypothesis,
    HypothesisTemplate,
    ProposeContext,
    hypothesis_id,
)
from calliope.reasoning.labels import Label, label_v1
from calliope.reasoning.needs import (
    ANALYSIS_BY,
    EvidenceNeed,
    FamilyNeed,
    LineNeed,
    line_label,
    need_key,
)
from calliope.reasoning.request import AnalysisRequest
from calliope.reasoning.verification import (
    FINAL,
    Claim,
    Verdict,
    VerdictStatus,
    check_premises,
    check_scope,
    check_target,
    effective_scope,
)


@dataclass(frozen=True, slots=True)
class RequestOutcome:
    request: object  # EnsureRequest | ExtendRequest
    outcome: str  # "rev:<n>" | "NO_OP" | "REFUSED(<error type>)"


@dataclass(frozen=True, slots=True)
class Round:
    index: int
    rev: int  # the revision of V_r
    admitted: tuple[EvidenceNeed, ...]
    requests: tuple[RequestOutcome, ...]


@dataclass(frozen=True, slots=True)
class LimitReached:
    limit: str  # max_derivation_depth | max_hypotheses | max_fixpoint_passes
    round: int
    refused: int


@dataclass(frozen=True, slots=True)
class Analysis:
    round_zero: RoundZero
    rev: int  # the final revision
    claims: tuple[Claim, ...]  # by seq
    relations: tuple[ClaimRelation, ...]
    rounds: tuple[Round, ...]
    limits_reached: tuple[LimitReached, ...]
    labels: tuple[Label, ...] = ()

    @property
    def tree(self) -> FactTree:
        return self.round_zero.tree


class Reasoner:
    def __init__(
        self, fact_engine: FactEngine, templates: tuple[HypothesisTemplate, ...] | None = None
    ) -> None:
        if templates is None:
            from calliope.reasoning.catalogue import CATALOGUE_V1

            templates = CATALOGUE_V1
        names = [t.name for t in templates]
        if len(set(names)) != len(names):
            raise ReasoningError("template names must be unique in the registry (R0-D §8.4)")
        self.fact_engine = fact_engine
        self.templates = templates
        self._by_name = {t.name: t for t in templates}

    def analyse(self, request: AnalysisRequest) -> Analysis:
        zero = Controller(self.fact_engine).round_zero(request)
        return _Run(self, zero, request).run()


class _Run:
    def __init__(self, reasoner: Reasoner, zero: RoundZero, request: AnalysisRequest) -> None:
        self.reasoner = reasoner
        self.zero = zero
        self.budget = request.budget
        self.tree = zero.tree
        self.rev0 = zero.rev
        self.subject_move = zero.tree.view(zero.rev).node(zero.subject.child).incoming_move
        self.hypotheses: dict[str, Hypothesis] = {}
        self.order: dict[str, tuple[int, int, int]] = {}  # id -> (seq, proposed round, depth)
        self.claims: dict[str, Claim] = {}  # final verdicts
        self.open: dict[str, Verdict] = {}  # NEEDS_EVIDENCE verdicts
        self.admitted: set[EvidenceNeed] = set()
        self.ensure_nodes: set[NodeId] = set()
        self.refused: dict[EvidenceNeed, str] = {}  # need -> error type
        self.unadmitted: set[EvidenceNeed] = set()
        self.limits: dict[tuple[str, int], set[str]] = {}
        self.rounds: list[Round] = []
        self.seq = 0

    # -- the loop ---------------------------------------------------------------------------

    def run(self) -> Analysis:
        rev = self.rev0
        for index in range(self.budget.max_rounds):
            view = self.tree.view(rev)
            self._fixpoint(index, view)
            if index == self.budget.max_rounds - 1:
                break  # the last round issues no requests (R0-D §6.3 step 3)
            admitted = self._admit(index, view)
            if not admitted:
                break
            outcomes = self._issue(admitted)
            self.rounds.append(Round(index, rev, tuple(admitted), tuple(outcomes)))
            rev = self.tree.rev
        last = max((c.decided for c in self.claims.values()), default=0)
        self._close(max(last, len(self.rounds)))
        claims = tuple(sorted(self.claims.values(), key=lambda c: c.seq))
        graph = relations(claims, self.reasoner._by_name)
        limits = tuple(
            LimitReached(name, rnd, len(keys)) for (name, rnd), keys in sorted(self.limits.items())
        )
        labels = label_v1(self.tree.view(), self.zero.judgements, claims)
        return Analysis(self.zero, self.tree.rev, claims, graph, tuple(self.rounds), limits, labels)

    def _fixpoint(self, index: int, view) -> None:
        reverified: set[str] = set()
        passes = 0
        while True:
            if passes >= self.budget.max_fixpoint_passes:
                self._limit("max_fixpoint_passes", index, "pass")
                return
            passes += 1
            changed = self._propose(index, view)
            changed = self._verify(index, view, reverified) or changed
            if not changed:
                return

    def _propose(self, index: int, view) -> bool:
        claims = tuple(sorted(self.claims.values(), key=lambda c: c.seq))
        pending = tuple(
            self.hypotheses[i] for i in sorted(self._open_ids(), key=lambda i: self.order[i][0])
        )
        ctx = ProposeContext(
            view, self.zero.subject, self.zero.judgements, self.zero.observations, claims, pending
        )
        fresh: dict[str, Hypothesis] = {}
        for template in self.reasoner.templates:
            for h in template.propose(ctx):
                if h.template != template.name or h.version != template.version:
                    raise ReasoningError(f"{template.name} proposed a {h.template} hypothesis")
                if h.id != hypothesis_id(h):
                    raise ReasoningError(f"{template.name} proposed a hypothesis with a wrong id")
                known = self.hypotheses.get(h.id) or fresh.get(h.id)
                if known is not None and known.template != h.template:
                    raise ReasoningError(f"{template.name} and {known.template} share an id")
                if h.id in self.hypotheses:
                    self._merge(h)
                elif h.id in fresh:
                    fresh[h.id] = _merged(fresh[h.id], h, self._earlier_claims(None))
                else:
                    fresh[h.id] = h
        added = False
        for h in sorted(fresh.values(), key=lambda h: (self._depth(h), h.id)):
            depth = self._depth(h)
            if depth > self.budget.max_derivation_depth:
                self._limit("max_derivation_depth", index, h.id)
                continue
            if len(self.hypotheses) >= self.budget.max_hypotheses:
                self._limit("max_hypotheses", index, h.id)
                continue
            check_target(view, h)
            check_premises(view, h, self.claims)
            h = replace(h, origins=_sorted_origins(h.origins, self._earlier_claims(None)))
            self.hypotheses[h.id] = h
            self.order[h.id] = (self.seq, index, depth)
            self.seq += 1
            added = True
        return added

    def _verify(self, index: int, view, reverified: set[str]) -> bool:
        decided = False
        todo = [i for i in self.hypotheses if i not in self.claims and i not in reverified]
        for claim_id in sorted(todo):
            h = self.hypotheses[claim_id]
            verdict = self.reasoner._by_name[h.template].verify(h, view)
            if verdict.hypothesis != claim_id:
                raise ReasoningError(f"{h.template} returned a verdict for another hypothesis")
            verdict = check_scope(view, verdict, h, self.subject_move)
            reverified.add(claim_id)
            if verdict.status in FINAL:
                self._finalize(h, verdict, index)
                decided = True
            else:
                self.open[claim_id] = verdict
        return decided

    # -- needs and requests -------------------------------------------------------------------

    def _admit(self, index: int, view) -> list[EvidenceNeed]:
        wanted: set[EvidenceNeed] = set()
        for claim_id, verdict in sorted(self.open.items()):
            refused = [self.refused[n] for n in verdict.needs if n in self.refused]
            if refused:  # its request was refused (R0-D §15)
                self._close_one(claim_id, f"NOT_COMPUTED({refused[0]})", index)
                continue
            if any(n in self.admitted for n in verdict.needs):
                self._close_one(claim_id, "NEED_UNMET", index)  # R0-D §6.3 step 4
                continue
            wanted.update(verdict.needs)
        live = self.tree.view()
        remaining = self.budget.max_extra_searches - self._extra_searches(live)
        room = self._node_room(live)
        admitted: list[EvidenceNeed] = []
        lines: dict[tuple, list[LineNeed]] = {}
        for need in sorted(wanted, key=need_key):
            if isinstance(need, FamilyNeed):
                nodes = self.ensure_nodes | {n.node for n in admitted if isinstance(n, FamilyNeed)}
                if need.node not in nodes and len(nodes) >= self.budget.max_ensure_nodes:
                    self.unadmitted.add(need)
                    continue
                admitted.append(need)
                continue
            group = lines.get(_flags(need.expansion), [])
            trial = {**lines, _flags(need.expansion): [*group, need]}
            try:
                new_nodes = _new_nodes(live, need)
                bound = sum(planned_search_bound(live, _extend(g)) for g in trial.values())
            except (InvalidRequestError, IllegalMoveError) as error:
                raise ReasoningError(f"a template raised a malformed need: {error}") from error
            if new_nodes > room or bound > remaining:
                self.unadmitted.add(need)
                continue
            room -= new_nodes
            lines = trial
            admitted.append(need)
        return admitted

    def _issue(self, admitted: list[EvidenceNeed]) -> list[RequestOutcome]:
        outcomes: list[RequestOutcome] = []
        family_needs = [n for n in admitted if isinstance(n, FamilyNeed)]
        if family_needs:
            nodes = tuple(dict.fromkeys(n.node for n in family_needs))
            families = tuple(dict.fromkeys(n.family for n in family_needs))
            request = EnsureRequest(nodes, families)
            outcomes.append(self._submit(request, family_needs))
            self.ensure_nodes.update(nodes)
        groups: dict[tuple, list[LineNeed]] = {}
        for need in admitted:
            if isinstance(need, LineNeed):
                groups.setdefault(_flags(need.expansion), []).append(need)
        for flags in sorted(groups):
            outcomes.append(self._submit(_extend(groups[flags]), groups[flags]))
        self.admitted.update(admitted)
        return outcomes

    def _submit(self, request, needs: list) -> RequestOutcome:
        engine = self.reasoner.fact_engine
        before = self.tree.rev
        try:
            if isinstance(request, EnsureRequest):
                rev = engine.ensure(self.tree, request)
            else:
                rev = engine.extend(self.tree, request)
        except (InvalidRequestError, IllegalMoveError) as error:
            raise ReasoningError(f"a template raised a malformed need: {error}") from error
        except FactEngineError as error:
            for need in needs:
                self.refused[need] = type(error).__name__
            return RequestOutcome(request, f"REFUSED({type(error).__name__})")
        return RequestOutcome(request, "NO_OP" if rev == before else f"rev:{rev}")

    def _extra_searches(self, view) -> int:
        """Distinct search ids first bound after rev_0 (R0-D §6.4)."""

        ids: dict[str, int] = {}
        for node in view.nodes():
            for binding in view.searches(node.node_id):
                ids[binding.search_id] = min(binding.rev, ids.get(binding.search_id, binding.rev))
        return sum(1 for rev in ids.values() if rev > self.rev0)

    def _node_room(self, view) -> int:
        budget = view.request(1).budget
        if budget.max_nodes is None:
            return 1 << 30
        return budget.max_nodes - len(view.nodes())

    # -- bookkeeping -------------------------------------------------------------------------

    def _finalize(self, h: Hypothesis, verdict: Verdict, index: int) -> None:
        seq, proposed, depth = self.order[h.id]
        scope = effective_scope(verdict, h, self.claims)
        self.claims[h.id] = Claim(h.id, h, verdict, seq, proposed, index, depth, scope)
        self.open.pop(h.id, None)

    def _close_one(self, claim_id: str, reason: str, index: int) -> None:
        h = self.hypotheses[claim_id]
        verdict = self.open[claim_id]
        final = Verdict(claim_id, VerdictStatus.INCONCLUSIVE, verdict.evidence, verdict.scope,
                        (), verdict.findings, reason)  # fmt: skip
        self._finalize(h, final, index)

    def _close(self, index: int) -> None:
        for claim_id in sorted(self.open):
            needs = self.open[claim_id].needs
            refused = [self.refused[n] for n in needs if n in self.refused]
            if refused:
                reason = f"NOT_COMPUTED({refused[0]})"
            elif any(n in self.admitted for n in needs):
                reason = "NEED_UNMET"  # admitted earlier, still needed (as in R0-D §6.3 step 4)
            elif any(n in self.unadmitted for n in needs):
                reason = "BUDGET"
            else:
                reason = "ROUND_LIMIT"
            self._close_one(claim_id, reason, index)

    def _merge(self, h: Hypothesis) -> None:
        existing = self.hypotheses[h.id]
        seq = self.order[h.id][0]
        self.hypotheses[h.id] = _merged(existing, h, self._earlier_claims(seq))
        if h.id in self.claims:
            claim = self.claims[h.id]
            self.claims[h.id] = replace(claim, hypothesis=self.hypotheses[h.id])

    def _open_ids(self) -> set[str]:
        """Hypotheses proposed and not yet final (R0-D §8.1: proposers see every state)."""

        return set(self.hypotheses) - set(self.claims)

    def _earlier_claims(self, seq: int | None) -> set[str]:
        return {i for i, (s, _, _) in self.order.items() if seq is None or s < seq}

    def _depth(self, h: Hypothesis) -> int:
        if not h.premises:
            return 0
        return 1 + max(self.order[p.claim][2] if p.claim in self.order else 0 for p in h.premises)

    def _limit(self, name: str, index: int, key: str) -> None:
        """Each refused proposal (or pass) counts once per limit and round (review C5)."""

        self.limits.setdefault((name, index), set()).add(key)


def _merged(existing: Hypothesis, new: Hypothesis, earlier: set[str]) -> Hypothesis:
    """Origins and directions are provenance: a sorted union (R0-D §8.3)."""

    origins = _sorted_origins((*existing.origins, *new.origins), earlier)
    directions = tuple(sorted(set(existing.directions) | set(new.directions)))
    return replace(existing, origins=origins, directions=directions)


def _sorted_origins(origins: tuple, earlier_claims: set[str]) -> tuple:
    """Claim origins only if proposed earlier, so DERIVED_FROM stays acyclic (R0-D §8.3)."""

    from calliope.reasoning.encoding import canonical_bytes

    kept = {canonical_bytes(o): o for o in origins if not isinstance(o, str) or o in earlier_claims}
    return tuple(kept[k] for k in sorted(kept))


def _flags(expansion: ExpansionSpec) -> tuple[bool, bool, bool]:
    return (expansion.survey, expansion.comparison, expansion.attach_lines)


def _extend(needs: list[LineNeed]) -> ExtendRequest:
    lines = tuple(InputLine(line_label(n), n.moves, start=n.start) for n in needs)
    return ExtendRequest(lines, analysis(ANALYSIS_BY), needs[0].expansion)


def _new_nodes(view, need: LineNeed) -> int:
    node: NodeId | None = need.start
    created = 0
    for move in need.moves:
        child = view.child(node, move) if node is not None else None
        if child is None:
            created += 1
        node = child
    return created
