"""Engine work of one request (F4-D §6.3, §7, §8): surveys, comparisons, ANALYSIS searches,
basis entries and engine-line attachment.

Engine work happens only at the nodes of the request, in this fixed order. Everything is
written into the request's pending revision, so a refused request commits nothing.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import chess

from calliope.facts.errors import BudgetExceededError
from calliope.facts.keys import NodeId
from calliope.facts.request import POLICY_ROLE_KINDS, ExpansionSpec, RoleKind
from calliope.facts.search.inputs import EngineInput, window_input
from calliope.facts.search.records import EngineSearch, ReuseSource, SearchKind, SearchRuntime
from calliope.facts.tree import (
    BasisEntry,
    BasisValue,
    DrawRule,
    EngineLineId,
    LineEnd,
    LineRecord,
    NodeSearch,
    TerminalKind,
    effective_expansion,
)
from calliope.facts.values import NotComputed

if TYPE_CHECKING:
    from calliope.facts.engine import _Build

IRREGULAR = NotComputed("IRREGULAR_SEARCH")
NOT_REQUESTED = NotComputed("COMPARISON_NOT_REQUESTED")


@dataclass(slots=True)
class WorkReport:
    """Manifest material of one request (F4-D §8a)."""

    runs: Counter[str] = field(default_factory=Counter)
    reuses: Counter[str] = field(default_factory=Counter)
    skipped: list[tuple[NodeId, str, str]] = field(default_factory=list)
    lines: Counter[str] = field(default_factory=Counter)
    load_dependent: bool = False


class EngineWork:
    def __init__(
        self,
        build: _Build,
        role_kind: RoleKind | None,
        expansion: ExpansionSpec | None,
        child_moves: dict[NodeId, set[str]],
        started: float,
    ) -> None:
        self.build = build
        self.session = build.session
        self.searcher = build.session.searcher
        self.role_kind = role_kind
        self.expansion = expansion
        self.child_moves = child_moves  # this request's child moves per node (ANALYSIS)
        self.started = started
        self.report = WorkReport()
        self._skipped_comparison: dict[NodeId, str] = {}
        self._analysis_bound: list[tuple[NodeId, str]] = []

    # -- the request ------------------------------------------------------------------------

    def run(self, nodes: list[NodeId]) -> WorkReport:
        searchable = [n for n in nodes if self._searchable(n)]
        self._precheck(searchable)
        for node_id in searchable:
            if self._latest(node_id, SearchKind.SURVEY) is None:
                self._search(node_id, SearchKind.SURVEY, None, None)
        for node_id in searchable:
            self._compare(node_id)
        if self.role_kind is RoleKind.ANALYSIS and self.expansion and self.expansion.comparison:
            for node_id in nodes:
                self._analysis(node_id)
        for node_id in nodes:
            self._basis(node_id)
        for node_id in nodes:
            self._attach(node_id)
        return self.report

    def _precheck(self, searchable: list[NodeId]) -> None:
        """Surveys must fit `max_searches`; store hits and session reuse are free (F4-D §8.3)."""

        limit = self.session.budget.max_searches
        if limit is None:
            return
        needed = sum(
            1
            for n in searchable
            if self._latest(n, SearchKind.SURVEY) is None
            and not self.searcher.cached(self._input(n), SearchKind.SURVEY)
        )
        if needed > limit - self.searcher.engine_calls:
            raise BudgetExceededError(
                f"the request needs {needed} new surveys; "
                f"{limit - self.searcher.engine_calls} engine calls remain"
            )

    # -- helpers ---------------------------------------------------------------------------

    def _deadline_passed(self) -> bool:
        deadline = self.session.budget.deadline_per_request_ms
        return deadline is not None and (time.monotonic() - self.started) * 1000 > deadline

    def _budget_left(self) -> bool:
        limit = self.session.budget.max_searches
        return limit is None or self.searcher.engine_calls < limit

    def _searchable(self, node_id: NodeId) -> bool:
        node = self.build.node(node_id)
        if node.terminal.ends_game or node.after_terminal:
            return False
        return effective_expansion(self.build.roles_of(node_id)).survey

    def _input(self, node_id: NodeId) -> EngineInput:
        history: list[str] = []
        current = self.build.node(node_id)
        while current.parent is not None:
            assert current.incoming_move is not None
            history.append(current.incoming_move)
            current = self.build.node(current.parent)
        history.reverse()
        node = self.build.node(node_id)
        moves = [*self.session.pre_root_moves, *history]
        return window_input(self.session.start_board, moves, node.halfmove_clock)

    def _bindings(self, node_id: NodeId) -> list[NodeSearch]:
        committed = self.build.tree._store.node_searches.get(node_id, [])
        pending = [b for b in self.build.pending.node_searches if b.node == node_id]
        return [*committed, *pending]

    def _record(self, search_id: str) -> EngineSearch:
        pending = self.build.pending.searches.get(search_id)
        if pending is not None:
            return pending
        return self.build.tree._store.searches[search_id][0]

    def _latest(self, node_id: NodeId, kind: SearchKind) -> EngineSearch | None:
        bindings = [b for b in self._bindings(node_id) if b.kind is kind]
        return None if not bindings else self._record(bindings[-1].search_id)

    def _search(
        self,
        node_id: NodeId,
        kind: SearchKind,
        roots: tuple[str, ...] | None,
        multipv: int | None,
    ) -> EngineSearch:
        search, reused, elapsed = self.searcher.search(self._input(node_id), kind, roots, multipv)
        if reused is None:
            self.report.runs[kind.value] += 1
        else:
            self.report.reuses[reused.value] += 1
        if not search.regular:
            self.report.load_dependent = True
        self._bind(node_id, search, kind, reused, elapsed)
        return search

    def _bind(
        self,
        node_id: NodeId,
        search: EngineSearch,
        kind: SearchKind,
        reused: ReuseSource | None,
        elapsed: int,
    ) -> None:
        pending = self.build.pending
        if any(b.search_id == search.search_id for b in self._bindings(node_id)):
            return
        pending.node_searches.append(NodeSearch(node_id, pending.rev, search.search_id, kind))
        if (
            search.search_id not in pending.searches
            and search.search_id not in self.build.tree._store.searches
        ):
            pending.searches[search.search_id] = search
        pending.runtimes.append(SearchRuntime(pending.rev, search.search_id, elapsed, reused))

    def _skip(self, node_id: NodeId, kind: SearchKind, roots, multipv) -> str | None:
        """A reason to skip a comparison / ANALYSIS search, or None (store hits are free)."""

        if self._deadline_passed():
            self.report.load_dependent = True
            return "DEADLINE"
        if not self._budget_left() and not self.searcher.cached(
            self._input(node_id), kind, roots, multipv
        ):
            return "BUDGET"
        return None

    # -- comparisons and ANALYSIS searches -----------------------------------------------------

    def _comparison_set(self, node_id: NodeId, survey: EngineSearch) -> tuple[str, ...]:
        moves = {line.move for line in survey.lines}
        for child in self.build.children_of(node_id):
            if any(r.kind in POLICY_ROLE_KINDS for r in self.build.roles_of(child, on_edge=True)):
                moves.add(self.build.node(child).incoming_move)  # type: ignore[arg-type]
        return tuple(sorted(moves))

    def _compare(self, node_id: NodeId) -> None:
        survey = self._latest(node_id, SearchKind.SURVEY)
        if survey is None or not survey.regular:
            return
        if not effective_expansion(self.build.roles_of(node_id), policy=True).comparison:
            return
        wanted = self._comparison_set(node_id, survey)
        if len(wanted) == len(survey.lines):
            return  # no comparison needed
        last = self._latest(node_id, SearchKind.COMPARISON)
        if last is not None and set(last.root_moves or ()) >= set(wanted):
            return
        reason = self._skip(node_id, SearchKind.COMPARISON, wanted, len(wanted))
        if reason is not None:
            self._skipped_comparison[node_id] = reason
            self.report.skipped.append((node_id, SearchKind.COMPARISON.value, reason))
            return
        self._search(node_id, SearchKind.COMPARISON, wanted, len(wanted))

    def _analysis(self, node_id: NodeId) -> None:
        node = self.build.node(node_id)
        moves = self.child_moves.get(node_id)
        if not moves or node.terminal.ends_game or node.after_terminal:
            return
        survey = self._latest(node_id, SearchKind.SURVEY)
        survey_moves = set() if survey is None else {line.move for line in survey.lines}
        wanted = tuple(sorted(survey_moves | moves))
        if set(wanted) == survey_moves:
            return
        reason = self._skip(node_id, SearchKind.ANALYSIS, wanted, len(wanted))
        if reason is not None:
            self.report.skipped.append((node_id, SearchKind.ANALYSIS.value, reason))
            return
        search = self._search(node_id, SearchKind.ANALYSIS, wanted, len(wanted))
        self._analysis_bound.append((node_id, search.search_id))

    # -- basis (§7.3) -------------------------------------------------------------------------

    def _basis(self, node_id: NodeId) -> None:
        value = self._basis_value(node_id)
        if value is None:
            return  # rows 1–2: derived by `TreeView.basis`, never written
        committed = self.build.tree._store.basis.get(node_id, [])
        pending = [b for b in self.build.pending.basis if b.node == node_id]
        entries = [*committed, *pending]
        if entries and entries[-1].value == value:
            return
        self.build.pending.basis.append(BasisEntry(node_id, self.build.pending.rev, value))

    def _basis_value(self, node_id: NodeId) -> BasisValue | None:
        node = self.build.node(node_id)
        if node.terminal.ends_game or node.after_terminal:
            return None
        survey = self._latest(node_id, SearchKind.SURVEY)
        if survey is None:
            return None
        if not survey.regular:
            return IRREGULAR
        wanted = self._comparison_set(node_id, survey)
        if len(wanted) == len(survey.lines):
            return survey.search_id
        if not effective_expansion(self.build.roles_of(node_id), policy=True).comparison:
            return NOT_REQUESTED
        reason = self._skipped_comparison.get(node_id)
        if reason is not None:
            return NotComputed(reason)
        last = self._latest(node_id, SearchKind.COMPARISON)
        if last is None or not set(last.root_moves or ()) >= set(wanted):
            return NotComputed("BUDGET")  # an older skip not yet retried
        return last.search_id if last.regular else IRREGULAR

    # -- engine lines (§8.1) --------------------------------------------------------------------

    def _attach(self, node_id: NodeId) -> None:
        expansion = effective_expansion(self.build.roles_of(node_id))
        todo: list[str] = []
        if expansion.attach_lines:
            bindings = sorted(
                (b for b in self._bindings(node_id) if b.kind is not SearchKind.ANALYSIS),
                key=lambda b: (b.rev, list(SearchKind).index(b.kind), b.search_id),
            )
            todo.extend(b.search_id for b in bindings)
        if self.expansion is not None and self.expansion.attach_lines:
            todo.extend(sid for n, sid in self._analysis_bound if n == node_id)
        for search_id in todo:
            if self.build.is_attached(node_id, search_id):
                continue
            self.build.pending.attached.append((node_id, search_id))
            search = self._record(search_id)
            for line in search.lines:
                self._attach_line(node_id, search, line.rank, line.pv)

    def _attach_line(
        self, anchor: NodeId, search: EngineSearch, rank: int, pv: tuple[str, ...]
    ) -> None:
        line_id = EngineLineId(anchor, search.search_id, rank)
        path = [anchor]
        end, rule, attached = LineEnd.PV_END, None, 0
        if self._deadline_passed():
            self.report.load_dependent = True
            end = LineEnd.BUDGET_LIMIT
        else:
            current = anchor
            for index, uci in enumerate(pv, start=1):
                child = NodeId.child(current, uci)
                if not self.build.has_node(child):
                    if not self.build.room_for_node():
                        end = LineEnd.BUDGET_LIMIT
                        break
                    self.build.add_engine_child(current, child, chess.Move.from_uci(uci))
                self.build.engine_role(child, anchor, search.search_id, rank, index)
                path.append(child)
                attached = index
                current = child
                terminal = self.build.node(child).terminal
                if terminal.ends_game:
                    end, rule = _terminal_end(terminal.kind, terminal.rule)
                    break
        self.report.lines[end.value] += 1
        self.build.pending.lines.append(
            LineRecord(
                line_id=line_id,
                first_index=0,
                nodes=tuple(path),
                end=end,
                end_rule=rule,
                rev=self.build.pending.rev,
                unattached_plies=len(pv) - attached,
            )
        )


def _terminal_end(kind: TerminalKind, rule: DrawRule | None) -> tuple[LineEnd, DrawRule | None]:
    if kind is TerminalKind.CHECKMATE:
        return LineEnd.CHECKMATE, None
    if kind is TerminalKind.STALEMATE:
        return LineEnd.STALEMATE, None
    return LineEnd.DRAW_RULE, rule
