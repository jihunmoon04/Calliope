"""The server process's work (AG-D §2, AG4-D): its games, trees, handles and budget, and the
tools' work.

A game id is derived from the game and resolves from its record (AG4-D §2), so it names the same
game in every process or is refused. The work state stays in the process and is bounded (§3.3):
the games it holds, least recently used first, each owning its facts tree and handles; projected analyses are a cache reloaded from the ply cache. The budget is the process's,
over a rolling window (§3).

Stored analyses are read-only: plies come from the ply cache or are analysed through the
pipeline's per-ply path and put into it (AG-D §3.3). Facts come from one engine-less facts tree per
game, rooted at the game's start, every asked path extended into it (§3.4). Searches run in
one-node search trees opened at the searched position. Every engine call the process causes goes
through its metering port (§3.5).
"""

from __future__ import annotations

import copy
import functools
import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import chess
import chess.pgn

from calliope.facts import (
    EXPLORED,
    NONE,
    EngineProfile,
    EnsureRequest,
    ExpansionSpec,
    ExtendRequest,
    FactEngine,
    FactEngineError,
    InputLine,
    OpenRequest,
    RootSpec,
    SessionBudget,
    Unavailable,
    material_flow,
)
from calliope.facts import Color as FactColor
from calliope.reasoning import Reasoner, build_digest, claim_sentence, expected
from calliope.results import EngineRun, GameInput, GameMove, PlyInput, game_result
from calliope.server import (
    CommentaryStore,
    EngineSlot,
    InputError,
    JobFailed,
    ParsedGame,
    PlyCache,
    StoreFailed,
    analyse_ply,
    board_size,
    canonical,
    normalized_ply,
    parse_game,
    plies_range,
    with_commentary,
)

from .budget import Budget, BudgetError, Limits, MeteredPort, SearchBudgetExhausted
from .build import text as prompt_text
from .digest import DigestTooLarge, bounded, digest
from .games import (
    MAX_BYTES,
    SHORT,
    GameError,
    Records,
    encode,
    from_record,
    game_id,
    parse_id,
    record_of,
)
from .handles import Entry, HandleExpired, Handles, is_handle
from .projection import identity, project

DEFAULT_FAMILIES = ("status", "material", "pieces")
EXPLORE_FAMILIES = ("status", "pieces", "exchange")
SHOW_LIMIT = 40  # plies in one `show_game` answer (AG3-D D10)
VIEWS = ("digest", "full")  # `ply` / `judge_move` (AG6-D §3.2, §3.4)
MAX_ITEMS = 16  # subjects in one submission (AG6-D §5.2)
MAX_PROPOSITIONS = 32  # in one commentary (AG6-D §5.3)
MAX_PROPOSITION_ID = 32  # characters
MAX_BOARD_BYTES = 64 * 1024  # one commentary as the board carries it (AG6-D §5.3)
SCORE_UNITS = {"cp": "cp_white", "mate": "mate_white", "expected": "expected_2000_side_to_move"}


class AgentError(ValueError):
    """A request the session cannot answer (a tool error with this message)."""


def pgn_of(fen: str | None, moves: list[str]) -> str:
    """A PGN without tags for a start position and moves (SAN or UCI)."""

    try:
        board = chess.Board(fen) if fen else chess.Board()
    except ValueError as error:
        raise AgentError(f"the FEN cannot be read: {error}") from error
    game = chess.pgn.Game()
    game.headers.clear()
    if fen:
        game.setup(board)
    node = game
    for ply, text in enumerate(moves, start=1):
        move = parse_move(board, text, ply)
        node = node.add_variation(move)
        board.push(move)
    return str(game)


def parse_move(board: chess.Board, text: str, ply: int) -> chess.Move:
    try:
        move = chess.Move.from_uci(text)
        if move in board.legal_moves:
            return move
    except ValueError:
        pass
    try:
        return board.parse_san(text)
    except ValueError as error:
        raise AgentError(f"move {ply} ({text!r}) is not legal in {board.fen()}") from error


@dataclass
class Game:
    """A game held in memory, with its work state (AG4-D §3.3)."""

    key: str
    parsed: ParsedGame  # `from_record` of its record (§2.4)
    facts: object | None = None  # its facts tree, opened on first use
    lines: int = 0  # facts-tree line labels used
    facts_nodes: int = 0  # the nodes it holds: search trees are not kept (review B3)


@dataclass
class Session:
    data: Path
    start: Callable[[], object]  # starts the engine (an EnginePort)
    limits: Limits = field(default_factory=Limits)
    profile: EngineProfile = field(default_factory=EngineProfile)
    clock: Callable[[], float] = time.monotonic  # the budget's window (tests inject one)

    def __post_init__(self) -> None:
        self.budget = Budget(self.limits, self.clock)
        self.slot = EngineSlot(lambda: MeteredPort(self.start(), self.budget.meter))
        self.cache = PlyCache(self.data / "plies")
        self.store = CommentaryStore(self.data / "commentary")
        self.records = Records(self.data / "agent" / "games")
        self.handles = Handles()
        self.held: OrderedDict[str, Game] = OrderedDict()  # by key, least recently used first
        self.facts_engine = FactEngine()
        # the search engine and its result store, the process's (re-review N1): what it holds
        # is asked of it (`survey_stored`, `stored_results`; re-review N2)
        self._search_engine: tuple[object, FactEngine] | None = None
        self._build: tuple[object, object, str] | None = None
        # projected and stored analyses by bundle, least recently used first: a cache (§3.3)
        self.analyses: OrderedDict[str, tuple[dict, object]] = OrderedDict()
        self.explored = 0

    def close(self) -> None:
        self.slot.close()

    # -- games (AG4-D §2.3, §3.3) -----------------------------------------------------------

    def game(self, game_id: str, hold: bool = True) -> Game:
        """The game an id names, or `GameError`. Work tools hold it (most recently used, making
        room as §3.3 says); read-only tools (`hold=False`) use a held game without touching the
        LRU, or a transient one built from the record (G6)."""

        digits = parse_id(game_id)
        if len(digits) > SHORT:
            key = digits
        else:  # a short id always lists the records, even for a held game (review B1)
            found = self._candidates(digits)
            if not found:
                raise GameError(f"no game {game_id} (open it with open_game)")
            if len(found) > 1:
                full = ", ".join(sorted(f"g-{k}" for k in found))
                raise GameError(f"game id {game_id} is ambiguous; use the full id given by "
                                f"open_game or its game_key: {full}")  # fmt: skip
            key = found.pop()
        game = self.held.get(key)
        if game is not None:
            if hold:
                self.held.move_to_end(key)
            return game
        game = Game(key, from_record(self.records.load(key)))
        if hold:
            self._hold(game)
        return game

    def _candidates(self, digits: str) -> set[str]:
        """The keys a short id may name: its records, and held games whose record is gone."""

        return {*self.records.keys(digits), *(k for k in self.held if k.startswith(digits))}

    def game_id(self, key: str) -> str:
        """The id `open_game` returns (§2.1): the short form, or the full one on a clash."""

        return game_id(key, short=not self._candidates(key[:SHORT]) - {key})

    def _hold(self, game: Game) -> None:
        self.held[game.key] = game
        self._room(game)

    def _room(self, game: Game, nodes: int = 0, tree: bool = False, handles: int = 0) -> None:
        """Make room for work on `game` that adds `nodes` (to its facts tree when `tree`) and
        `handles` (§3.3): past the per-tree limit the call is refused; past a process limit the
        least recently used other game is evicted, and the call is refused when its own game
        alone passes it."""

        limits = self.limits
        if tree and game.facts_nodes + nodes > limits.max_nodes_per_tree:
            raise BudgetError(f"the game's facts tree refuses {nodes} new nodes: it holds "
                              f"{game.facts_nodes} of {limits.max_nodes_per_tree}")  # fmt: skip

        def over() -> str | None:
            if len(self.held) > limits.max_open_games:
                return f"{limits.max_open_games} games held"
            if sum(g.facts_nodes for g in self.held.values()) + nodes > limits.max_nodes_total:
                return f"{limits.max_nodes_total} nodes in all trees"
            if len(self.handles) + handles > limits.max_handles:
                return f"{limits.max_handles} handles"
            return None

        while over() is not None:
            victim = next((k for k in self.held if k != game.key), None)
            if victim is None:
                raise BudgetError(f"the game alone would pass the process's limit of {over()}")
            self._evict(victim)

    def _evict(self, key: str) -> None:
        """Put a game away with all its work state: its facts tree and its handles."""

        self.held.pop(key)
        self.handles.drop(key)

    def _serve(self, game: Game, items: list[tuple[str, dict, dict, object, dict]]) -> None:
        """Serve `(prefix, source, address, item, target)`: each target gets the item's `ref`.
        Room is made only for the handles not served before (review B1)."""

        keys = [(prefix, source, address) for prefix, source, address, *_ in items]
        self._room(game, handles=self.handles.fresh(game.key, keys))
        for prefix, source, address, item, target in items:
            target["ref"] = self.handles.serve(prefix, game.key, source, address, item)

    def _left(self, game: Game) -> dict:
        return self.budget.left() | {"nodes": self.limits.max_nodes_per_tree - game.facts_nodes}

    def resolve(self, ref: str, game: Game) -> Entry:
        """A handle of `game`; one bound to an analysis the cache dropped is reloaded from the ply
        cache, or refused as expired (§3.3)."""

        entry = self.handles.resolve(ref, game.key)
        if entry.source.get("kind") == "analysis":
            try:
                self.analysis(game, entry.source)
            except HandleExpired as error:
                raise HandleExpired(f"{ref} expired: {error}") from error
        return entry

    def open_game(
        self,
        pgn: str | None = None,
        fen: str | None = None,
        moves: list[str] | None = None,
        plies: str | None = None,
        on_ply: Callable[[int, int, str], None] | None = None,
    ) -> dict:
        """Read a game, write its record (AG4-D §2.2) and return its id (§2.1). The game worked
        on is `from_record` of the record (§2.4); a game already held is reused as it is."""

        if (pgn is None) == (fen is None and moves is None):
            raise AgentError("give either `pgn`, or `fen` and/or `moves`")
        text = pgn if pgn is not None else pgn_of(fen, moves or [])
        if len(text.encode("utf-8")) > MAX_BYTES:
            raise AgentError(f"the game text has more than {MAX_BYTES} bytes")
        try:
            read = parse_game(text)
        except InputError as error:
            raise AgentError(str(error)) from error
        record = record_of(read.game)
        size = len(encode(record))
        if size > MAX_BYTES:  # before any work on the game (§2.2)
            raise GameError(f"the game's record would have {size} bytes, over {MAX_BYTES}")
        key = record["game_key"]
        game = self.held.get(key)
        parsed = game.parsed if game is not None else from_record(record)
        try:
            wanted = plies_range(plies, len(parsed.sans)) if plies else range(0)
        except InputError as error:
            raise AgentError(str(error)) from error
        if plies and (not wanted or wanted.start < 1):  # the analysis server's rule (`checked`)
            raise AgentError(f"the ply range {plies!r} is outside the game's "
                             f"{len(parsed.sans)} plies")  # fmt: skip
        cached = {ply: self._cached(parsed, ply) for ply in range(1, len(parsed.sans) + 1)}
        self.budget.admit_analyses([p for p in wanted if not cached[p]])
        self.records.create(record)  # once it is read and admitted
        if game is None:
            game = Game(key, parsed)
            self._hold(game)
        else:
            self.held.move_to_end(key)
        summaries, refused = {}, None
        for done, ply in enumerate(wanted, start=1):
            try:
                record, was_cached, _ = self._analysed(game, parsed, ply)
            except BudgetError as error:  # AG6-D F13: what was analysed is answered with it
                if not summaries:
                    raise
                refused = {"ply": ply, "message": str(error)}
                if error.retry_after_seconds is not None:
                    refused["retry_after_seconds"] = error.retry_after_seconds
                break
            summaries[ply] = _summary(record)
            cached[ply] = True
            if on_ply is not None:
                on_ply(done, len(wanted), f"ply {ply} {parsed.sans[ply - 1]}"
                       f"{' (cached)' if was_cached else ''}")  # fmt: skip
        out_moves = []
        for move in parsed.game.moves:
            ply = len(out_moves) + 1
            entry = {"ply": ply, "san": move.san, "uci": move.uci, "cached": cached[ply]}
            if ply in summaries:
                entry |= summaries[ply]
            out_moves.append(entry)
        answer = {
            "game": self.game_id(key),
            "game_key": key,
            "start_fen": parsed.game.start_fen,
            "headers": dict(parsed.game.headers),
            "warnings": list(read.warnings),
            "moves": out_moves,
            "budget_left": self._left(game),
        }
        if refused is not None:
            answer["refused"] = refused
        answer["next"] = NEXT_REFUSED if refused is not None else NEXT_OPENED
        return answer

    # -- analyses (AG-D §3.1, §3.3) ---------------------------------------------------------

    def ply(self, game_id: str, ply: int, view: str = "digest") -> dict:
        _check_view(view)
        game = self.game(game_id)
        if not 1 <= ply <= len(game.parsed.sans):
            raise AgentError(f"the game has plies 1 to {len(game.parsed.sans)}, not {ply}")
        record, cached, analysis = self._analysed(game, game.parsed, ply)
        answer = record | {"cached": cached, "budget_left": self._left(game)}
        return answer if view == "full" else self._digest(answer, analysis)

    def judge_move(self, game_id: str, position: dict, move: str, view: str = "digest") -> dict:
        _check_view(view)
        game = self.game(game_id)
        path = self.path(game, position)
        board = self._board(game, path)
        uci = parse_move(board, move, len(path) + 1).uci()
        parsed = variation(game.parsed, [*path, uci])
        record, cached, analysis = self._analysed(game, parsed, len(path) + 1)
        played = game.parsed.uci[: len(path) + 1] == (*path, uci)
        answer = record | {"played": played, "cached": cached, "budget_left": self._left(game)}
        return answer if view == "full" else self._digest(answer, analysis, ("played",))

    def _digest(self, answer: dict, analysis, keep: tuple[str, ...] = ()) -> dict:
        """AG6-D §3.2: the digest of a full answer, its unrendered claims' own sentences, then the
        session's fields, `next`, and the bound (§3.6)."""

        said = {s.get("claim") for s in answer["segments"] if s.get("source") == "claim"}
        sentences = {}
        for claim in answer["analysis"]["claims"]:
            if claim["status"] != "refuted" and claim["id"] not in said:
                text = claim_sentence(analysis, claim["id"])
                if text is not None:
                    sentences[claim["id"]] = text
        out = digest(answer, _glossary(), sentences)
        for name in (*keep, "cached", "budget_left"):
            out[name] = answer[name]
        out["next"] = _next_digest(out)
        try:
            return bounded(out)
        except DigestTooLarge as error:
            raise AgentError(str(error)) from error

    def detail(self, game_id: str, ref: str) -> dict:
        """AG6-D §3.4: the one item a handle names, exactly as the full answer projects it."""

        game = self.game(game_id, hold=False)  # read-only: nothing is analysed or charged
        entry = self.resolve(ref, game)
        return {"ref": ref, "kind": entry.kind, "item": copy.deepcopy(entry.item)}

    def reasoning_digest(self) -> str:
        return self._engine_build()[2]

    def _engine_build(self):
        port = self.slot.port
        if self._build is None or self._build[0] is not port:
            build = Reasoner(FactEngine(engine=port)).build()
            self._build = (port, build, build_digest(build))
        return self._build

    def _key(self, parsed: ParsedGame, ply: int):
        port, build, digest = self._engine_build()
        expected_request = normalized_ply(parsed, ply, self.profile)
        key = PlyCache.key(expected_request, digest, port.identity, self.profile)
        return key, expected_request, build, digest

    def _cached(self, parsed: ParsedGame, ply: int) -> bool:
        key, *_ = self._key(parsed, ply)
        return all(p.exists() for p in self.cache.paths(key))

    def _load_or_analyse(self, parsed: ParsedGame, ply: int):
        key, expected_request, build, digest = self._key(parsed, ply)
        loaded = self.cache.get(key, expected_request, build)
        if loaded is not None:
            return loaded, True, digest
        self.budget.admit_analysis(ply)  # charged as it is admitted
        refused = self.budget.meter.refused
        engine = list(self.slot.port.identity.fingerprint())
        try:
            analysis, rendered = analyse_ply(self.slot, parsed, ply, self.profile, engine)
        except SearchBudgetExhausted as error:
            raise BudgetError(f"{error}: the analysis of ply {ply} was cut short and is not "
                              f"cached; left: {self.budget.left()}") from error  # fmt: skip
        except JobFailed as error:
            raise AgentError(str(error)) from error
        if self.budget.meter.refused != refused:  # defensive: a refusal the reasoner absorbed
            raise BudgetError(f"the analysis of ply {ply} was cut short and is not cached")
        try:
            loaded = self.cache.put(key, analysis, rendered, expected_request, build)
        except StoreFailed as error:
            raise AgentError(f"the analysis of ply {ply} could not be stored: {error}") from error
        return loaded, False, digest

    def _record(self, parsed: ParsedGame, ply: int, loaded) -> dict:
        document = game_result(
            parsed.game,
            EngineRun(self.slot.port.identity, self.profile),
            [PlyInput(ply, loaded.analysis, loaded.rendered, loaded.bundle)],
            analysis=True,
        )
        return document["plies"][0]

    def _keep(self, analysis_id: str, projected: dict, analysis) -> tuple[dict, object]:
        self.analyses[analysis_id] = (projected, analysis)
        self.analyses.move_to_end(analysis_id)
        while len(self.analyses) > self.limits.max_analyses:
            self.analyses.popitem(last=False)
        return projected, analysis

    def analysis(self, game: Game, source: dict) -> tuple[dict, object]:
        """The projected and stored analysis of a handle's source: from the cache, or reloaded
        from the ply cache by its path and bundle digests (no engine); `HandleExpired` when the
        ply cache no longer holds those digests (AG4-D §3.3, review N1)."""

        analysis_id = source["analysis"]
        found = self.analyses.get(analysis_id)
        if found is not None:
            self.analyses.move_to_end(analysis_id)
            return found
        path = tuple(source["path"])
        parsed = game.parsed if game.parsed.uci[: len(path)] == path else variation(
            game.parsed, path)  # fmt: skip
        key, expected_request, build, _ = self._key(parsed, len(path))
        loaded = self.cache.get(key, expected_request, build)
        if loaded is None or (loaded.bundle.tree, loaded.bundle.graph) != (
                source["tree"], source["graph"]):  # fmt: skip
            raise HandleExpired(f"the analysis of {list(path)} is no longer in the cache; read "
                                "it again with ply or judge_move")  # fmt: skip
        record = self._record(parsed, len(path), loaded)
        return self._keep(analysis_id, record["analysis"], loaded.analysis)

    def _analysed(self, game: Game, parsed: ParsedGame, ply: int) -> tuple[dict, bool, object]:
        loaded, cached, digest = self._load_or_analyse(parsed, ply)
        record = self._record(parsed, ply, loaded)
        path = list(parsed.uci[:ply])
        analysis_id = f"{loaded.bundle.tree}:{loaded.bundle.graph}"
        self._keep(analysis_id, record["analysis"], loaded.analysis)
        source = {
            "kind": "analysis",
            "analysis": analysis_id,
            "path": path,
            "tree": loaded.bundle.tree,
            "graph": loaded.bundle.graph,
            "build": digest,
        }
        self._serve_analysis(game, record, source, loaded.analysis)
        return record, cached, loaded.analysis

    def _serve_analysis(self, game: Game, record: dict, source: dict, analysis_object) -> None:
        """Refs on the judgements, their search lines and the claims (§3.6). A judgement line gets
        its PV from the stored search (`by: engine`) and its depth; the subject's judgement its
        label."""

        analysis = record["analysis"]
        view = analysis_object.tree.view(analysis_object.rev)
        judgements = analysis_object.round_zero.judgements
        items = []
        for index, judgement in enumerate(analysis["judgements"]):
            subject = index == 0
            judgement["label"] = (record["label"] or {}).get("kind") if subject else None
            address = {"judgement": index, "move": judgement["move"]["uci"]}
            items.append(("j", source, address, judgement, judgement))
            found = judgements[index].search
            lines = {} if found is None else {x.rank: x for x in view.search(found.search_id).lines}
            fen = judgement["move"]["fen"]
            for line in (judgement["played"], judgement["best"], *judgement["alternatives"]):
                if line is None:
                    continue
                pv = lines[line["rank"]].pv if line["rank"] in lines else ()
                line["pv"] = _pv(fen, pv)
                line["depth"] = analysis["searches"][line["search"]]["depth"]
                address = {"judgement": index, "rank": line["rank"], "fen": fen}
                items.append(("s", source, address, line, line))
        items += [("c", source, {"claim": c["id"]}, c, c) for c in analysis["claims"]]
        self._serve(game, items)

    # -- commentary (AG-D §5, §8) ------------------------------------------------------------

    def _subject(self, game: Game, ply, position, move) -> tuple[str, ...]:
        if ply is not None:
            if not isinstance(ply, int) or not 1 <= ply <= len(game.parsed.uci):
                raise AgentError(f"the game has plies 1 to {len(game.parsed.uci)}, not {ply}")
            return game.parsed.uci[:ply]
        if position is None or move is None:
            raise AgentError("give the subject: `ply`, or `position` and `move`")
        path = self.path(game, position)
        return (*path, parse_move(self._board(game, path), move, len(path) + 1).uci())

    def submit_commentary(
        self,
        game_id: str,
        ply: int | None = None,
        position: dict | None = None,
        move: str | None = None,
        language: str = "ko",
        agent: dict | None = None,
        propositions: list | None = None,
        sentences: list | None = None,
        items: list | None = None,
    ) -> dict:
        """Verify every proposition (§4) and every sentence (§5.3); store an accepted commentary
        in the sidecar store (§8). One subject with its propositions and sentences, or `items`,
        each verified and stored on its own (AG6-D §5.2). A refusal lists every violation and
        stores nothing; an equal record already stored answers its id (F15)."""

        game = self.game(game_id)
        if items is None:
            outcome = self._commentary(game, ply, position, move, language, agent, propositions,
                                       sentences)  # fmt: skip
            if outcome["outcome"] == "not_stored":
                raise AgentError(outcome["message"])
            answer = {"accepted": outcome["outcome"] != "refused"}
            answer |= {k: v for k, v in outcome.items() if k != "outcome"}
            if outcome["outcome"] == "duplicate":
                answer["duplicate"] = True
            return answer | {"next": _next_submitted([outcome])}
        if any(v is not None for v in (ply, position, move, propositions, sentences)):
            raise AgentError("give either `items`, or one subject (`ply`, or `position` and "
                             "`move`) with its propositions and sentences")  # fmt: skip
        if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
            raise AgentError(f"`items` is a list of 1 to {MAX_ITEMS} subjects")
        outcomes = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                problem = "an item is {ply | position and move, propositions, sentences}"
                outcome = {
                    "outcome": "refused",
                    "violations": [{"rule": "item", "problem": problem}],
                }
            else:
                try:
                    outcome = self._commentary(game, item.get("ply"), item.get("position"),
                                               item.get("move"), language, agent,
                                               item.get("propositions"), item.get("sentences"))  # fmt: skip
                except AgentError as error:  # the item's subject
                    outcome = {"outcome": "refused",
                               "violations": [{"rule": "subject", "problem": str(error)}]}  # fmt: skip
            outcomes.append({"index": index} | outcome)
        return {"items": outcomes, "next": _next_submitted(outcomes)}

    def _commentary(self, game: Game, ply, position, move, language, agent, propositions,
                    sentences) -> dict:  # fmt: skip
        """One subject's commentary: `{"outcome": accepted | duplicate | refused | not_stored,
        ...}` (AG6-D §5.2); a subject that does not hold raises `AgentError`."""

        from .build import agent_build
        from .propositions import Refused, Verifier
        from .sentences import check_sentences

        subject = self._subject(game, ply, position, move)
        violations: list[dict] = []
        if not isinstance(agent, dict) or not isinstance(agent.get("name"), str):
            violations.append({"rule": "agent", "problem": "agent is {name, model?}"})
        if not isinstance(propositions, list) or not propositions:
            violations.append({"rule": "propositions", "problem": "at least one proposition"})
            propositions = []
        elif len(propositions) > MAX_PROPOSITIONS:  # AG6-D §5.3
            violations.append({"rule": "size", "problem": f"at most {MAX_PROPOSITIONS} "
                               f"propositions in one commentary, not {len(propositions)}"})  # fmt: skip
            return {"outcome": "refused", "violations": violations}
        verifier = Verifier(self, game)
        verified: dict[str, dict] = {}
        allowed = {}
        for index, proposition in enumerate(propositions):
            pid = proposition.get("id") if isinstance(proposition, dict) else None
            where = {"proposition": pid if pid is not None else index}
            if (not isinstance(pid, str) or not pid or len(pid) > MAX_PROPOSITION_ID
                    or pid in verified):  # fmt: skip
                problem = f"a unique id of at most {MAX_PROPOSITION_ID} characters is required"
                violations.append(where | {"field": "id", "problem": problem})
                continue
            try:
                record, allows = verifier.verify(proposition)
            except Refused as error:
                violations.append(
                    where
                    | {
                        "kind": proposition.get("kind"),
                        "field": error.field,
                        "problem": error.problem,
                        "expected": error.expected,
                    }
                )
                continue
            verified[pid], allowed[pid] = record, allows
        judged = [r for r in verified.values() if r["kind"] == "judgement"
                  and _subject_judgement(r, subject)]  # fmt: skip
        if not judged:
            violations.append(
                {
                    "rule": "subject",
                    "problem": "a judgement proposition citing "
                    "the subject's own judgement (ply or judge_move) is required",
                }
            )
        violations += check_sentences(language, sentences, allowed)
        if violations:
            return {"outcome": "refused", "violations": violations}
        source = judged[0]["judged"]["source"]
        stored = [
            {"text": s["text"], "class": s["class"], "cites": s["cites"],
             "by_agent": any(verified[c]["by_agent"] for c in s["cites"])}
            for s in sentences
        ]  # fmt: skip
        digest = self.reasoning_digest()
        record = {
            "game_key": game.key,
            "subject": {"path": list(subject), "ply": len(subject),
                        "played": game.parsed.uci[: len(subject)] == subject},
            "bundle": {"tree": source["tree"], "graph": source["graph"]},
            "created": datetime.now(UTC).isoformat(timespec="seconds"),
            "language": language,
            "agent": {k: agent[k] for k in ("name", "model") if k in agent},
            "level": "SOURCE_VERIFIED",
            "check": "commentary_check_v1",
            "propositions": list(verified.values()),
            "sentences": stored,
            "agent_build": agent_build(digest),
            "reasoning_build": digest,
        }  # fmt: skip
        board = board_size(record, game.parsed.game.start_fen)
        if board > MAX_BOARD_BYTES:  # AG6-D §5.3
            problem = (f"the commentary would carry {board} bytes on the board, over "
                       f"{MAX_BOARD_BYTES}")  # fmt: skip
            return {"outcome": "refused", "violations": [{"rule": "size", "problem": problem}]}
        counts = {"level": "SOURCE_VERIFIED", "propositions": len(verified),
                  "sentences": len(stored)}  # fmt: skip
        key = _content_key(record)
        for held in self.store.for_subject(game.key, subject):  # AG6-D F15
            if _content_key(held) == key:
                return {"outcome": "duplicate", "id": held["id"]} | counts
        try:
            commentary_id = self.store.write(record)
        except (OSError, StoreFailed) as error:
            return {"outcome": "not_stored",
                    "message": f"the commentary was verified but not stored: {error}"}  # fmt: skip
        return {"outcome": "accepted", "id": commentary_id} | counts

    def commentary(
        self, game_id: str, ply: int | None = None, position: dict | None = None,
        move: str | None = None,
    ) -> dict:  # fmt: skip
        """The accepted commentaries of a subject, newest first; `stale` against the analysis the
        ply cache holds now (None when it holds none)."""

        game = self.game(game_id, hold=False)  # read-only (G6)
        subject = self._subject(game, ply, position, move)
        parsed = game.parsed if game.parsed.uci[: len(subject)] == subject else variation(
            game.parsed, subject)  # fmt: skip
        key, *_ = self._key(parsed, len(subject))
        files = self.cache.paths(key)
        current = None
        if all(f.exists() for f in files):
            current = tuple(hashlib.sha256(f.read_bytes()).hexdigest() for f in files)
        out = []
        for record in self.store.for_subject(game.key, subject):
            held = (record["bundle"]["tree"], record["bundle"]["graph"])
            out.append(record | {"stale": None if current is None else held != current})
        return {"subject": {"path": list(subject), "ply": len(subject)}, "commentaries": out}

    # -- the App's document (AG3-D D10) -----------------------------------------------------

    def show_game(self, game_id: str, plies: str | None = None) -> tuple[dict, str]:
        """A combined `calliope_result_v1` over the asked plies that are cached, each with its
        newest current commentary and its `display`, and a short Korean text of it. Nothing is
        analysed or charged: a ply the cache cannot give is left out and named."""

        game = self.game(game_id, hold=False)  # read-only (G6)
        parsed = game.parsed
        count = len(parsed.sans)
        try:
            wanted = plies_range(plies, count)
        except InputError as error:
            raise AgentError(str(error)) from error
        if plies and (not wanted or wanted.start < 1):
            raise AgentError(f"the ply range {plies!r} is outside the game's {count} plies")
        if plies and len(wanted) > SHOW_LIMIT:
            raise AgentError(f"한 번에 {SHOW_LIMIT}수까지 보여 줄 수 있습니다: plies에 "
                             f"{SHOW_LIMIT}수 이하의 범위를 주세요 (요청 {len(wanted)}수)")  # fmt: skip
        held = [ply for ply in wanted if self._cached(parsed, ply)]
        inputs = []
        for ply in held:
            key, expected_request, build, _ = self._key(parsed, ply)
            loaded = self.cache.get(key, expected_request, build)  # a miss: left out
            if loaded is not None:
                inputs.append(PlyInput(ply, loaded.analysis, loaded.rendered, loaded.bundle))
            if len(inputs) > SHOW_LIMIT:  # without `plies`: the limit counts plies that load
                raise AgentError(f"분석된 수가 {SHOW_LIMIT}개를 넘어 한 번에 보여 줄 수 없습니다: "
                                 f"plies에 범위를 주세요 (예: \"1-{SHOW_LIMIT}\")")  # fmt: skip
        if not inputs:
            raise AgentError(f"게임 {game_id}의 요청한 수 가운데 분석된(캐시된) 수가 없습니다: "
                             "ply나 open_game의 plies로 먼저 분석하세요")  # fmt: skip
        document = game_result(parsed.game, EngineRun(self.slot.port.identity, self.profile),
                               inputs)  # fmt: skip
        combined = with_commentary(document, self.store.for_game(game.key), list(parsed.uci))
        shown = {p.ply for p in inputs}
        asked = wanted if plies else held  # without `plies`, the cached plies are the ones asked
        return combined, _shown_text(game_id, combined, [p for p in asked if p not in shown])

    # -- positions and the facts tree (AG-D §3.2, §3.4) --------------------------------------

    def path(self, game: Game, position: dict) -> tuple[str, ...]:
        """The canonical UCI path from the game's root to a position argument."""

        parsed = game.parsed
        if not isinstance(position, dict):
            raise AgentError(
                "a position is {'ply': n, 'at': 'before'|'after'} or {'from_root': [...]}"
            )
        if "from_root" in position:
            moves = position["from_root"]
            if not isinstance(moves, list) or not all(isinstance(m, str) for m in moves):
                raise AgentError("from_root is a list of moves")
            board = chess.Board(parsed.game.start_fen)
            out = []
            for ply, text in enumerate(moves, start=1):
                move = parse_move(board, text, ply)
                out.append(move.uci())
                board.push(move)
            return tuple(out)
        ply, at = position.get("ply"), position.get("at", "after")
        if (
            not isinstance(ply, int)
            or isinstance(ply, bool)
            or not 1 <= ply <= len(parsed.uci)
            or at not in ("before", "after")
        ):
            raise AgentError(f"no position {position!r} in a game of {len(parsed.uci)} plies")
        return parsed.uci[: ply if at == "after" else ply - 1]

    def _board(self, game: Game, path) -> chess.Board:
        board = chess.Board(game.parsed.game.start_fen)
        for uci in path:
            board.push_uci(uci)
        return board

    def _facts_tree(self, game: Game):
        if game.facts is None:
            self._room(game, nodes=1, tree=True)
            game.facts = self.facts_engine.open(OpenRequest(root=game.parsed.root, engine=None))
            game.facts_nodes = 1
        return game.facts

    def _node(self, game: Game, path) -> tuple[object, list]:
        """The facts tree's view and the nodes from the root along `path`, extended as needed."""

        tree = self._facts_tree(game)
        view = tree.view()
        nodes = [view.root]
        for i, uci in enumerate(path):
            child = view.child(nodes[-1], uci)
            if child is None:
                rest = tuple(path[i:])
                self._room(game, nodes=len(rest), tree=True)
                game.lines += 1
                label = f"p-{game.lines}"  # a new label each time (AG-D §3.4)
                line = InputLine(label, rest, start=nodes[-1])
                try:
                    self.facts_engine.extend(tree, ExtendRequest((line,), EXPLORED, NONE))
                except FactEngineError as error:
                    raise AgentError(f"the facts tree refuses the path: {error}") from error
                game.facts_nodes += len(rest)
                view = tree.view()
                for step in rest:
                    nodes.append(view.child(nodes[-1], step))
                return view, nodes
            nodes.append(child)
        return view, nodes

    def _raw_records(self, game: Game, node, families) -> tuple[object, dict]:
        """The facts tree's view and the raw records of `families` at `node`, ensured."""

        tree = self._facts_tree(game)
        if families:
            try:
                self.facts_engine.ensure(tree, EnsureRequest((node,), tuple(families)))
            except FactEngineError as error:
                raise AgentError(f"the facts tree refuses the records: {error}") from error
        view = tree.view()
        return view, {name: view.fact(name, node) for name in families}

    def _records(self, game: Game, view, node, families) -> tuple[object, dict]:
        tree = game.facts
        known = view.families()
        for name in families:
            if name not in known:
                raise AgentError(f"no fact family {name!r}; families: {sorted(known)}")
            if known[name][1].value == "span":
                raise AgentError(f"{name} is a span family; read it along a line with explore")
        try:
            self.facts_engine.ensure(tree, EnsureRequest((node,), tuple(families)))
        except FactEngineError as error:
            raise AgentError(f"the facts tree refuses the records: {error}") from error
        view = tree.view()
        frame = view.node(node)
        out = {}
        for name in families:
            if frame.parent is None and known[name][1].value == "edge":
                out[name] = {"sentinel": "no_edge", "reason": "the game's start has no move"}
                continue
            out[name] = project(view.fact(name, node), frame)
            if name == "pieces" and isinstance(out[name], dict):
                for entry in out[name]["pieces"]:  # by square: the identity from the frame (§3.7)
                    piece = frame.piece_at(entry["square"])
                    if piece is not None:
                        entry["identity"] = identity(piece, frame)
        return view, out

    def _position(self, game: Game, view, node, path) -> dict:
        frame = view.node(node)
        return {"from_root": list(path), "fen": frame.fen, "ply": len(path),
                "side_to_move": frame.side_to_move.value}  # fmt: skip

    def facts(self, game_id: str, position: dict, families: list[str] | None = None) -> dict:
        game = self.game(game_id)
        path = self.path(game, position)
        view, nodes = self._node(game, path)
        view, records = self._records(game, view, nodes[-1], families or DEFAULT_FAMILIES)
        source = {"kind": "facts_tree", "rev": view.rev}
        served = {name: {"ref": None, "record": record} for name, record in records.items()}
        self._serve(game, [("f", source, {"position": list(path), "family": name}, record,
                            served[name]) for name, record in records.items()])  # fmt: skip
        return {
            "position": self._position(game, view, nodes[-1], path),
            "families": served,
            "budget_left": self._left(game),
        }

    # -- exploration (AG-D §3.4) ------------------------------------------------------------

    def explore(
        self, game_id: str, position: dict, moves: list[str] | None = None, search: bool = False
    ) -> dict:
        game = self.game(game_id)
        base = self.path(game, position)
        board = self._board(game, base)
        line = []
        for ply, text in enumerate(moves or [], start=1):
            move = parse_move(board, str(text), ply)
            line.append(move.uci())
            board.push(move)
        if search:  # admitted before any facts work, so a refusal leaves nothing half done
            self._admit_search(game, (*base, *line))
        view, nodes = self._node(game, (*base, *line))
        start = len(base)
        steps = nodes[start:]
        plies = []
        if line:
            flow = material_flow(view, tuple(steps))
            for i, node in enumerate(steps[1:], start=1):
                frame = view.node(node)
                plies.append({
                    "ply": i,
                    "by": "agent",
                    "move": project(view.fact("move", node), frame),
                    "material_balance_white": flow.balance(FactColor.WHITE, i),
                })  # fmt: skip
        view, records = self._records(game, view, nodes[-1], EXPLORE_FAMILIES)
        source = {"kind": "facts_tree", "rev": view.rev}
        address = {"from": list(base), "moves": line}
        self.explored += 1
        answer = {
            "start": self._position(game, view, nodes[start], base),
            "end": self._position(game, view, nodes[-1], (*base, *line)),
            "plies": plies,
            "end_facts": records,
            "units": {"material_balance_white": "points_v1"},
        }
        self._serve(game, [("x", source, address | {"by": "agent"}, answer, answer)])
        if search:
            answer["search"] = self._search(game, (*base, *line))
        answer["budget_left"] = self._left(game)
        return answer

    def _admit_search(self, game: Game, path) -> None:
        if self._board(game, path).is_game_over(claim_draw=False):
            raise AgentError("the game is over at that position: there is nothing to search")
        if not self._engine().survey_stored(_search_root(game, path), self.profile):
            self.budget.admit_search()  # a search the store holds is free

    def _reset_store(self) -> None:
        """Replace the search engine's result store with an empty one (AG4-D §3.3, review C6)."""

        self._search_engine = None

    def _engine(self) -> FactEngine:
        """The search engine of the current port: a restarted engine has a new, empty store
        (re-review N1)."""

        port = self.slot.port
        if self._search_engine is None or self._search_engine[0] is not port:
            self._search_engine = (port, FactEngine(engine=port))  # its store lives with it
        return self._search_engine[1]

    def _search(self, game: Game, path) -> dict:
        """One survey of the position in a one-node search tree (AG-D §3.4, C1)."""

        root = _search_root(game, path)
        request = OpenRequest(
            root=root,
            families=(),
            budget=SessionBudget(max_searches=1),
            engine=self.profile,
            root_expansion=ExpansionSpec(survey=True, comparison=False, attach_lines=False),
        )
        engine = self._engine()
        if (not engine.survey_stored(root, self.profile)
                and engine.stored_results >= self.limits.max_store_results):  # fmt: skip
            self._reset_store()  # only for a search admitted and about to run (review B4)
            engine = self._engine()
        try:
            tree = engine.open(request)  # a one-node tree, not kept (review B3)
        except SearchBudgetExhausted as error:
            raise BudgetError(f"{error}; left: {self.budget.left()}") from error
        except FactEngineError as error:
            raise AgentError(f"the search was refused: {error}") from error
        view = tree.view()
        bindings = view.searches(view.root)
        if not bindings:
            raise AgentError("the position has no search")
        search = view.search(bindings[0].search_id)
        frame = view.node(view.root)
        mover = frame.side_to_move
        lines = []
        for line in search.lines:
            board = chess.Board(frame.fen)
            sans = []
            for uci in line.pv:
                move = chess.Move.from_uci(uci)
                sans.append(board.san(move))
                board.push(move)
            score = project(line.score)
            record = {
                "rank": line.rank,
                "move": {"uci": line.move, "san": sans[0] if sans else None},
                "score": {"cp": score["value"]} if "value" in score else
                         {"mate": score["moves"] if score["winner"] == "white" else -score["moves"]},
                "wdl": None if isinstance(line.wdl, Unavailable) else project(line.wdl),
                "expected": None if isinstance(line.wdl, Unavailable) else expected(line.wdl, mover),
                "depth": line.depth,
                "pv": [{"uci": u, "san": s, "by": "engine"} for u, s in zip(line.pv, sans, strict=True)],
            }  # fmt: skip
            lines.append(record)
        # a regular search's id names its request, not its lines: the digest binds the handles
        # to this result, so another result after a store reset gets other handles (review B2)
        digest = hashlib.sha256(canonical(lines)).hexdigest()
        source = {"kind": "search", "position": list(path), "search": search.search_id,
                  "lines": digest}  # fmt: skip
        self._serve(game, [("s", source, {"rank": r["rank"], "fen": frame.fen, "path": list(path)},
                            r, r) for r in lines])  # fmt: skip
        return {
            "position": {"from_root": list(path), "fen": frame.fen},
            "profile": search.profile.name,
            "multipv": search.multipv,
            "lines": lines,
            "units": SCORE_UNITS | {"wdl": "permille_white"},
        }


def _search_root(game: Game, path) -> RootSpec:
    """The root of a search at `path`: the game's start and the moves to the position."""

    return RootSpec(fen=game.parsed.root.fen, moves=tuple(path))


def variation(parsed: ParsedGame, path) -> ParsedGame:
    """The game's start with `path` as its moves: the input of a judged move (AG-D §3.3)."""

    board = chess.Board(parsed.game.start_fen)
    moves, sans = [], []
    for uci in path:
        move = chess.Move.from_uci(uci)
        san = board.san(move)
        before = board.fen()
        board.push(move)
        moves.append(GameMove(san, uci, before, board.fen()))
        sans.append(san)
    game = GameInput(parsed.game.start_fen, tuple(moves), parsed.game.headers)
    return ParsedGame(game, tuple(sans), tuple(path), parsed.root, parsed.spec, ())


def _subject_judgement(record: dict, subject) -> bool:
    """A verified judgement proposition on the subject's own judgement (the first of its ply)."""

    found = record["judged"]  # the source of the proposition's own `judgement` field
    return (
        found["source"].get("kind") == "analysis"
        and found["source"]["path"] == list(subject)
        and found["address"].get("judgement") == 0
        and record["move"] == subject[-1]
    )


def _shown_text(game_id: str, document: dict, missing: list[int]) -> str:
    """`show_game`'s `content`: the game, the plies shown, those left out, and per ply its grade
    and whether a commentary is attached (AG3-D D10)."""

    grades = _glossary()["grades"]
    plies = document["plies"]
    shown = _ranges([p["ply"] for p in plies])
    lines = [f"게임 {game_id}: 분석된 수 {len(plies)}개를 판에 보여 줍니다 (수 {shown})."]
    if missing:
        lines.append(f"분석되지 않아 빠진 수: {_ranges(missing)} (ply로 분석하면 볼 수 있습니다).")
    for p in plies:
        dots = "." if p["side"] == "white" else "..."
        grade = grades.get(p["grade"], "판정 보류") if p["grade"] else "판정 보류"
        ai = " · AI 해설 있음" if "ai_commentary" in p else ""
        lines.append(f"{p['move_number']}{dots}{p['san']} (수 {p['ply']}): {grade}{ai}")
    return "\n".join(lines)


def _ranges(numbers: list[int]) -> str:
    out, start = [], None
    for k, n in enumerate(numbers):
        if start is None:
            start = n
        if k + 1 == len(numbers) or numbers[k + 1] != n + 1:
            out.append(str(start) if start == n else f"{start}–{n}")
            start = None
    return ", ".join(out)


@functools.cache
def _glossary() -> dict:
    return json.loads(prompt_text("glossary_ko_v1.json"))


def _check_view(view) -> None:
    if view not in VIEWS:
        raise AgentError(f"view is one of {', '.join(VIEWS)}, not {view!r}")


# `next` (AG6-D §7) on the one-ply path: advice in one Korean sentence; no call is refused for not
# following it.
NEXT_OPENED = '해설할 수를 ply로 읽으세요(요약판으로 답합니다; 전체 분석은 view: "full").'
NEXT_REFUSED = (
    "분석된 수만 해설하세요: 나머지 수는 refused의 retry_after_seconds 뒤에 ply나 plies로 분석할 수 "
    "있고, 분석되지 않은 수는 기억으로 해설하지 않습니다."
)


def _next_digest(d: dict) -> str:
    text = (
        "이 수를 해설하려면 submit_commentary로 제출하세요: 판정은 "
        f'{{"kind": "judgement", "judgement": "{d["judgement"]}"}}처럼 ref만으로, 클레임은 ref와 '
        "use로 쓸 수 있습니다. 더 필요한 근거는 detail(ref)·judge_move·explore로 확인하세요."
    )
    if any(c["status"] == "inconclusive" for c in d["claims"]):
        text += " INCONCLUSIVE 클레임은 확인되지 않았다고만 씁니다(use: uncertain)."
    return text


def _next_submitted(outcomes: list[dict]) -> str:
    kinds = {o["outcome"] for o in outcomes}
    parts = []
    if "refused" in kinds:
        parts.append("거부된 항목은 violations를 고쳐 다시 제출하세요.")
    if "not_stored" in kinds:
        parts.append("저장되지 않은 항목은 같은 내용으로 다시 제출하세요(이미 저장된 것은 두 번 "
                     "저장되지 않습니다).")  # fmt: skip
    if kinds <= {"accepted", "duplicate"}:
        parts.append("저장된 해설은 show_game으로 판에 보여 주고, 채팅에는 짧은 요약만 쓰세요.")
    return " ".join(parts)


def _content_key(record: dict) -> bytes:
    """AG6-D F15: what makes two commentaries of a subject the same, free of what one process
    serves — handles and the facts tree's revision; the cited items' sources and addresses stay."""

    return canonical({
        "subject": record["subject"]["path"],
        "agent": record.get("agent"),
        "language": record.get("language"),
        "bundle": record.get("bundle"),
        "sentences": record.get("sentences"),
        "propositions": _stable(record.get("propositions")),
    })  # fmt: skip


def _stable(value):
    if isinstance(value, dict):
        if value.get("kind") == "facts_tree":
            value = {k: v for k, v in value.items() if k != "rev"}
        return {k: _stable(v) for k, v in value.items() if k != "ref" and not is_handle(v)}
    if isinstance(value, list):
        return [_stable(v) for v in value if not is_handle(v)]
    return value


def _summary(record: dict) -> dict:
    return {
        "grade": record["grade"],
        "label": record["label"],
        "text": record["text"],
    }


def _pv(fen: str, pv) -> list[dict]:
    board = chess.Board(fen)
    out = []
    for uci in pv:
        move = chess.Move.from_uci(uci)
        out.append({"uci": uci, "san": board.san(move), "by": "engine"})
        board.push(move)
    return out
