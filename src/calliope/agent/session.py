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
import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field, replace
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
from calliope.reasoning import Reasoner, build_digest, expected
from calliope.results import EngineRun, GameInput, GameMove, PlyInput, game_result
from calliope.server import (
    MAX_LOADED,
    MAX_LOADED_MB,
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

from .board import Board
from .board import canonical as canonical_record
from .budget import (
    Budget,
    BudgetError,
    EngineLock,
    Limits,
    MeteredSlot,
    SearchBudgetExhausted,
)
from .build import text as prompt_text
from .digest import DigestTooLarge, bounded, digest, numbered, score_text
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
from .handles import Entry, HandleError, HandleExpired, Handles, is_handle
from .jobs import ACTIVE, WAIT_LIMIT, GameJobs, Job
from .messages_ko import korean, violations_ko
from .projection import identity, project
from .remarks import proposition_part

DEFAULT_FAMILIES = ("status", "material", "pieces")
EXPLORE_FAMILIES = ("status", "pieces", "exchange")
SHOW_LIMIT = 200  # plies whose records one `show_game` carries (AG6-D §6.1)
GAME_PATH_PLIES = 600  # the game path's games (AG6-D §3.6, AS-D's MAX_PLIES)
LINES_LIMIT = 200  # ply lines of one overview (AG6-D §3.3)
OVERVIEW_LIMIT = 48_000  # characters of an overview as sent (AG6-D §3.6)
HEADER_CAP = 200  # a header value in the overview and the board (AG6-D §3.6)
MOMENTS = 8  # AG6-D §3.3
VIEW_LIMIT = 768 * 1024  # bytes of the board's document (AG6-D §6.2)
RECORD_LIMIT = 64 * 1024  # one ply's record on the board (AG6-D §6.2)
STOP_SECONDS = 120  # the job worker's time to end when the session closes (review B1)
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


WHOLE_GAME = (
    "to analyse the whole game, open it without `plies` and call `analyze_game`, "
    "which analyses it in the background"
)  # a range over the per-call bound


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
    verify_writes: bool = False  # the ply cache's replay on every write (CC-D §2.3)
    max_loaded: int = MAX_LOADED  # pairs the ply cache keeps loaded (CC-D §3.2)
    max_loaded_mb: int = MAX_LOADED_MB

    def __post_init__(self) -> None:
        self.budget = Budget(self.limits, self.clock)
        # one engine (AG6-D §4.3, §4.4): the tools see it through AG4-D's meter, the jobs through
        # their own; every use of it is under the fair engine lock
        self.engine_slot = EngineSlot(self.start)
        self.slot = MeteredSlot(self.engine_slot, self.budget.meter)
        self.engine_lock = EngineLock()
        self.jobs = GameJobs(self.limits, self._job_ply, self._job_cached, self.engine_slot,
                             self.clock)  # fmt: skip
        self.read: dict[str, set[int]] = {}  # plies whose digest was served, by game key (§7)
        self.boards: dict[str, dict[tuple, dict]] = {}  # served board items (AG8-D §6.2)
        self.board_tokens: dict[str, dict[str, object]] = {}  # game → `b` ref → its `proves`'
        # tokens (MS-D §8.3): what a sentence citing the item by handle may write
        self.moments: dict[str, list[int]] = {}  # the moments of the last overview, by game key
        self.cache = PlyCache(self.data / "plies", verify_writes=self.verify_writes,
                              max_loaded=self.max_loaded, max_loaded_mb=self.max_loaded_mb)  # fmt: skip
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
        """The jobs first, then the engine (review B1): the engine is closed only once the worker
        has ended, under the engine lock; a worker that does not end in STOP_SECONDS keeps it
        (the process's exit ends both)."""

        log = logging.getLogger(__name__)
        if not self.jobs.stop(timeout=STOP_SECONDS):
            log.error("the job worker did not end in %s s: the engine is left to it", STOP_SECONDS)
            return
        log.info("ply cache: %s, kept %s", self.cache.counts, self.cache.kept())
        with self.engine_lock:
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
        """Put a game away with all its work state: its facts tree, its handles and the board
        items its digests served (AG8-D §6.2)."""

        self.held.pop(key)
        self.handles.drop(key)
        self.boards.pop(key, None)
        self.board_tokens.pop(key, None)

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
        uncached = [p for p in wanted if not cached[p]]
        try:
            self.budget.admit_analyses(uncached)
        except BudgetError as error:
            if len(uncached) <= self.limits.max_uncached_plies_per_call:
                raise
            raise BudgetError(f"{error}; {WHOLE_GAME}", error.retry_after_seconds) from error
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
        self.jobs.keep_summary(game.key, ply, _ply_summary(record))  # for the overview (AG6b)
        answer = record | {"cached": cached, "budget_left": self._left(game)}
        if view == "full":
            return answer
        self.read.setdefault(game.key, set()).add(ply)  # a digest read (AG6-D §7)
        path = tuple(game.parsed.uci[: ply - 1])
        board = (game_id, game, path, game.parsed.uci[ply - 1], True)
        return self._digest(answer, analysis, key=game.key, board=board)

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
        if view == "full":
            return answer
        return self._digest(answer, analysis, ("played",), board=(game_id, game, path, uci, False))

    def _digest(
        self,
        answer: dict,
        analysis,
        keep: tuple[str, ...] = (),
        key: str | None = None,
        board: tuple | None = None,
    ) -> dict:
        """AG6-D §3.2: the digest of a full answer, its unrendered claims' own sentences, then the
        session's fields, `next`, `board` (AG8-D §2) and the bound (§3.6). The board items served
        are kept per game and subject in canonical form (AG8-D §6.2)."""

        out = digest(answer, _glossary())  # MS-D §8: `proves`, no sentence of Calliope's
        if board is not None:  # both callers pass the game with the board's inputs
            self._derived_uses(board[1], out)
        for name in (*keep, "cached", "budget_left"):
            out[name] = answer[name]
        out["next"] = _next_digest(out)
        if key is not None and self.moments.get(key):  # a game's overview was served (AG6-D §7)
            out["next"] = self._next_moment(key)
        served = []
        if board is not None:
            game_id, game, path, uci, by_ply = board
            built = Board(self, game_id, game, path, uci, answer, out, by_ply)
            out["board"], served = built.build(analysis)
            _annotate(out, built.relations, answer)  # MS-D §5: a relation claim's relation, link
            out["budget_left"] = self._left(game)  # after the same reply's searches (review B3)
        try:  # MS-D §6 (review B4): one relation once, settled within the bound (MS-b B2)
            bound = bounded(out, built=out.get("board"))
        except DigestTooLarge as error:
            raise AgentError(str(error)) from error
        if board is not None:
            self._keep_board(game, (*path, uci), out["board"], bound["board"], served, bound)
        return bound

    def _derived_uses(self, game: Game, d: dict) -> None:
        """MS-D §9.2: each listed claim (and each group member under one) with `as`, the use the
        server stores for it when a sentence cites it without one."""

        from .propositions import Verifier

        verifier = Verifier(self, game)
        for claim in d.get("claims", ()):
            for entry in (claim, *claim.get("also", ())):
                try:
                    served = self.resolve(entry["ref"], game)
                except HandleError:
                    continue
                use = verifier.derived_use(served.item, served.source)
                if use is not None:
                    entry["as"] = use

    def _keep_board(self, game: Game, subject: tuple, built: dict, shown: dict, served: list,
                    digest: dict) -> None:  # fmt: skip
        """AG8-D §6.2: the items the digest shows, in its order, with their canonical forms; and
        whether the digest held a reason (a board item or a claim of part `reason`)."""

        items = [*built["changes"], *([built["same_reply"]] if "propositions" in
                                      built.get("same_reply", {}) else [])]  # fmt: skip
        kept_items = [*shown["changes"], *([shown["same_reply"]] if "propositions" in
                                           shown.get("same_reply", {}) else [])]  # fmt: skip
        kept = []
        for item, entry in zip(items, served, strict=True):
            if item in kept_items:
                kept.append(entry | {"index": kept_items.index(item)})
        reason = bool(kept) or any(c.get("part") == "reason" for c in digest.get("claims", ()))
        self.boards.setdefault(game.key, {})[subject] = {"items": kept, "reason": reason}

    def detail(self, game_id: str, ref: str) -> dict:
        """AG6-D §3.4: the one item a handle names, exactly as the full answer projects it."""

        game = self.game(game_id, hold=False)  # read-only: nothing is analysed or charged
        entry = self.resolve(ref, game)
        return {"ref": ref, "kind": entry.kind, "item": copy.deepcopy(entry.item)}

    def reasoning_digest(self) -> str:
        return self._engine_build()[2]

    def _engine_build(self):
        """The build and digest of the running engine. Known for the running port, they are read
        without the engine lock, so a cache read never waits for an analysis (review B3); made
        under it when the engine starts or has restarted (AG6-D §4.3)."""

        known = self._build
        if known is not None and known[0] is self.slot.current():
            return known
        with self.engine_lock:
            port = self.slot.port
            if self._build is None or self._build[0] is not port:
                build = Reasoner(FactEngine(engine=port)).build()
                self._build = (port, build, build_digest(build))
            return self._build

    def _identity(self):
        return self._engine_build()[0].identity

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
        loaded = self.cache.get(key, expected_request, build)  # a read takes no engine lock
        if loaded is not None:
            return loaded, True, digest
        with self.engine_lock:  # check, analyse and write under one hold (AG6-D §4.3)
            return self._analyse_held(parsed, ply, key, expected_request, build, digest)

    def _analyse_held(self, parsed: ParsedGame, ply: int, key, expected_request, build, digest):
        loaded = self.cache.get(key, expected_request, build)  # a job may have written it
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

    def _record(self, parsed: ParsedGame, ply: int, loaded, analysis: bool = True) -> dict:
        document = game_result(
            parsed.game,
            EngineRun(self._identity(), self.profile),
            [PlyInput(ply, loaded.analysis, loaded.rendered, loaded.bundle)],
            analysis=analysis,
        )
        return document["plies"][0]

    # -- the jobs' per-ply path (AG6-D §4) ---------------------------------------------------

    def _job_cached(self, job: Job, ply: int) -> bool:
        return self._cached(job.parsed, ply)

    def _job_ply(self, job: Job, ply: int) -> tuple[bool, dict]:
        """One ply of a job, in the worker's thread: the cache's pair, or an analysis through the
        job's slot (its meter) under the engine lock; and the ply's summary (AG6b §2). It touches
        no session state but the cache and the engine (§4.3)."""

        key, expected, build, _ = self._key(job.parsed, ply)
        loaded = self.cache.get(key, expected, build)
        cached = loaded is not None
        if loaded is None:
            with self.engine_lock:
                loaded = self.cache.get(key, expected, build)
                cached = loaded is not None
                if loaded is None:
                    self.jobs.charge()  # only an analysis is charged, never a hit (review N1)
                    engine = list(job.slot.port.identity.fingerprint())
                    analysis, rendered = analyse_ply(job.slot, job.parsed, ply, self.profile,
                                                     engine)  # fmt: skip
                    loaded = self.cache.put(key, analysis, rendered, expected, build)
        return cached, _ply_summary(self._record(job.parsed, ply, loaded, analysis=False))

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
                refused = [{"rule": "item", "problem": problem}]
                outcome = {
                    "outcome": "refused",
                    "violations": violations_ko(refused) if language == "ko" else refused,
                }
            else:
                try:
                    outcome = self._commentary(game, item.get("ply"), item.get("position"),
                                               item.get("move"), language, agent,
                                               item.get("propositions"), item.get("sentences"))  # fmt: skip
                except AgentError as error:  # the item's subject
                    problem = {"rule": "subject", "problem": str(error)}
                    if language == "ko":  # AG8-D §7
                        problem |= {"problem": korean(str(error)), "problem_en": str(error)}
                    outcome = {"outcome": "refused", "violations": [problem]}
            outcomes.append({"index": index} | outcome)
        return {"items": outcomes, "next": _next_submitted(outcomes)}

    def _by_handle(self, game: Game, sentences: list) -> tuple[list, list, list]:
        """MS-D §9.1: each handle a sentence cites or states stands for the propositions the
        server builds for it, each with its own id (`<handle>:<part>`, review B1), built once.
        (the built propositions, the sentences with handles expanded, the problems)."""

        from .digest import PV_PLIES

        built: dict[str, list[dict]] = {}
        problems: list[dict] = []

        def expand(ref: str, index: int, field: str) -> list[str]:
            if ref not in built:
                try:
                    entry = self.resolve(ref, game)
                except HandleError as error:
                    problems.append({"sentence": index, "field": field, "problem": str(error)})
                    built[ref] = []
                    return []
                item, kind = entry.item, entry.kind
                if kind == "judgement":
                    out = [("judgement", {"kind": "judgement", "judgement": ref})]
                elif kind == "claim":
                    out = [("claim", {"kind": "claim", "claim": ref})]  # its use derived (§9.2)
                elif kind == "search_line":
                    out = [("score", {"kind": "engine_score", "line": ref,
                                      "move": item["move"]["uci"], "score": item["score"]})]  # fmt: skip
                    pv = [x["uci"] for x in item.get("pv") or []][:PV_PLIES]
                    if pv:  # a line without a PV: its score alone (review B8)
                        out.append(("line", {"kind": "engine_line", "line": ref, "moves": pv}))
                elif kind == "explored_line":
                    out = [("line", {"kind": "explored_line", "line": ref,
                                     "moves": list(entry.address["moves"])})]  # fmt: skip
                elif kind == "board_item":
                    out = [(str(i), dict(p)) for i, p in enumerate(item["propositions"])]
                else:
                    problems.append({"sentence": index, "field": field, "problem":
                                     f"a {kind} handle is not cited by itself: write its "
                                     "proposition"})  # fmt: skip
                    built[ref] = []
                    return []
                built[ref] = [p | {"id": f"{ref}:{part}", "by_handle": ref} for part, p in out]
            return [p["id"] for p in built[ref]]

        out = []
        for index, sentence in enumerate(sentences):
            if not isinstance(sentence, dict):
                out.append(sentence)
                continue
            sentence = dict(sentence)
            for name in ("cites", "states"):
                values = sentence.get(name)
                if isinstance(values, list):
                    expanded = []
                    for value in values:
                        expanded += (expand(value, index, name) if is_handle(value)
                                     else [value])  # fmt: skip
                    sentence[name] = list(dict.fromkeys(expanded))
            out.append(sentence)
        return [p for ps in built.values() for p in ps], out, problems

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
        if propositions is None:
            propositions = []
        if isinstance(propositions, list) and isinstance(sentences, list):
            for index, proposition in enumerate(propositions):  # MS-D §9.1: a colon is a handle's
                pid = proposition.get("id") if isinstance(proposition, dict) else None
                if isinstance(pid, str) and ":" in pid:
                    violations.append({"proposition": pid, "field": "id",
                                       "problem": "a proposition's id has no colon"})  # fmt: skip
            built, sentences, problems = self._by_handle(game, sentences)
            propositions = [*propositions, *built]
            violations += problems
        if not isinstance(propositions, list) or not propositions:
            violations.append({"rule": "propositions", "problem": "at least one proposition"})
            propositions = []
        elif len(propositions) > MAX_PROPOSITIONS:  # AG6-D §5.3
            violations.append({"rule": "size", "problem": f"at most {MAX_PROPOSITIONS} "
                               f"propositions in one commentary, not {len(propositions)}"})  # fmt: skip
            return {"outcome": "refused", "violations": violations_ko(violations)
                    if language == "ko" else violations}  # fmt: skip
        verifier = Verifier(self, game)
        verified: dict[str, dict] = {}
        allowed = {}
        for index, proposition in enumerate(propositions):
            pid = proposition.get("id") if isinstance(proposition, dict) else None
            where = {"proposition": pid if pid is not None else index}
            built = isinstance(proposition, dict) and "by_handle" in proposition  # the server's
            if (not isinstance(pid, str) or not pid or pid in verified
                    or (len(pid) > MAX_PROPOSITION_ID and not built)):  # fmt: skip
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
            if isinstance(proposition.get("by_handle"), str):  # MS-D §9.1
                record["by_handle"] = proposition["by_handle"]
                extra = self.board_tokens.get(game.key, {}).get(proposition["by_handle"])
                if extra is not None and pid.endswith(":0"):  # a board item's `proves` (I5)
                    allows.merge(extra)
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
        kinds = {pid: record["kind"] for pid, record in verified.items()}
        violations += check_sentences(language, sentences, allowed, kinds)
        if violations:
            if language == "ko":  # AG8-D §7
                violations = violations_ko(violations)
            return {"outcome": "refused", "violations": violations}
        source = judged[0]["judged"]["source"]
        served = self.boards.get(game.key, {}).get(subject)
        stated = [_stated(s, verified, served) for s in sentences]
        stored = []
        for sentence, (items, _) in zip(sentences, stated, strict=True):
            entry = {"text": sentence["text"], "class": sentence["class"],
                     "cites": sentence["cites"],
                     "by_agent": any(verified[c]["by_agent"] for c in sentence["cites"])}  # fmt: skip
            if sentence.get("states"):
                entry["states"] = list(sentence["states"])
                entry["states_items"] = items
            stored.append(entry)
        notes = _notes(sentences, stated, served)
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
            "check": CHECK,
            "propositions": list(verified.values()),
            "sentences": stored,
            "agent_build": agent_build(digest),
            "reasoning_build": digest,
        }  # fmt: skip
        board = board_size(record, game.parsed.game.start_fen)
        if board > MAX_BOARD_BYTES:  # AG6-D §5.3
            problem = (f"the commentary would carry {board} bytes on the board, over "
                       f"{MAX_BOARD_BYTES}")  # fmt: skip
            refused = [{"rule": "size", "problem": problem}]
            return {"outcome": "refused", "violations": violations_ko(refused)
                    if language == "ko" else refused}  # fmt: skip
        counts = {"level": "SOURCE_VERIFIED", "propositions": len(verified),
                  "sentences": len(stored)}  # fmt: skip
        if notes:
            counts["notes"] = notes  # AG8-D §6.4: accepted, with what a better commentary does
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
        """AG6-D §6: the board's `calliope_view_v1` — the whole game's moves, every ply's state and
        the job, with a `calliope_result_v1` of the analysed plies of the asked range (or none) and
        their newest current commentary, bounded in bytes; and a short Korean text of it. Nothing
        is analysed or charged."""

        game = self.game(game_id, hold=False)  # read-only (G6)
        parsed = game.parsed
        count = len(parsed.sans)
        _check_game_path(count)
        wanted = self._range(plies, count, SHOW_LIMIT, "show_game")
        pending, failed = self.jobs.pending(game.key), self.jobs.failed(game.key)
        # analysed as the overview says it, for every ply of the game, not only the asked range
        # (review B8): a summary of the files there now, else a pair that loads
        analysed = {p for p in range(1, count + 1) if self._summary(game, p) is not None}
        states = []
        for p in range(1, count + 1):
            state = ("analysed" if p in analysed else "pending" if p in pending else
                     "failed" if p in failed else "none")  # fmt: skip
            states.append({"ply": p, "state": state})
        headed = replace(parsed.game, headers=_capped_headers(parsed.game.headers))
        kept = self.cache.kept_keys()
        order = sorted(
            (p for p in wanted if p in analysed),
            key=lambda p: (self._key(parsed, p)[0] not in kept, p),
        )  # kept first (AG6b)
        loaded = {}
        for p in order:
            key, expected_request, build, _ = self._key(parsed, p)
            pair = self.cache.get(key, expected_request, build)
            if pair is not None:
                loaded[p] = PlyInput(p, pair.analysis, pair.rendered, pair.bundle)
            else:  # files that do not load are a miss (AS-D §4): not analysed
                states[p - 1]["state"] = "none"
        omitted = {"records": [], "commentary": []}
        result = self._view_result(game, headed, loaded, omitted)
        view = {
            "schema": "calliope_view_v1",
            "game": {"start_fen": headed.start_fen,
                     "moves": [{"san": m.san, "uci": m.uci} for m in headed.moves],
                     "headers": dict(headed.headers)},
            "result": result,
            "plies": states,
            "job": self.jobs.snapshot(game.key),
            "omitted": omitted,
        }  # fmt: skip
        for entry in states:
            if entry["ply"] in omitted["records"]:
                entry["omitted"] = "record"
            elif entry["ply"] in omitted["commentary"]:
                entry["omitted"] = "commentary"
        size = len(_compact(view).encode("utf-8"))
        if size > VIEW_LIMIT:  # the constructions above exclude it: a fault, never a cut document
            raise AgentError(f"the board's document exceeds its size bound ({size} > {VIEW_LIMIT})")
        return view, _view_text(game_id, view, wanted, count)

    def _view_result(self, game: Game, headed, loaded: dict, omitted: dict) -> dict | None:
        """The result of the range within the byte bound (AG6-D §6.2): a record over its own bound
        is left out; then commentary goes, the plies that are not moments first, each from the end;
        then records, from the end. What goes is named in `omitted`."""

        records = self.store.for_game(game.key)
        played = list(game.parsed.uci)
        moments = set(self.moments.get(game.key, ()))
        inputs = [loaded[p] for p in sorted(loaded)]
        identity = self._identity()

        def build(chosen, without):
            if not chosen:
                return None
            document = game_result(headed, EngineRun(identity, self.profile), chosen)
            combined = with_commentary(document, records, played)
            for ply in combined["plies"]:
                if ply["ply"] in without:
                    ply.pop("ai_commentary", None)
            return combined

        result = build(inputs, set())
        if result is None:
            return None
        for ply in result["plies"]:  # one record, or one commentary, over its own bound
            commentary = ply.get("ai_commentary")
            if commentary is not None and len(_compact(commentary).encode()) > RECORD_LIMIT:
                omitted["commentary"].append(ply["ply"])
            bare = {k: v for k, v in ply.items() if k != "ai_commentary"}
            if len(_compact(bare).encode()) > RECORD_LIMIT:
                omitted["records"].append(ply["ply"])
        inputs = [i for i in inputs if i.ply not in omitted["records"]]
        without = set(omitted["commentary"])
        result = build(inputs, without)
        budget = VIEW_LIMIT - 64 * 1024  # the moves, the states and the job: under 64 KiB (§6.2)
        with_ai = [p["ply"] for p in result["plies"] if "ai_commentary" in p] if result else []
        drop = [p for p in reversed(with_ai) if p not in moments] + \
            [p for p in reversed(with_ai) if p in moments]  # fmt: skip
        # what each leaves behind when it goes, so one build follows a run of drops, not each one
        by_ply = {p["ply"]: p for p in result["plies"]} if result else {}
        saves = {p: len(_compact(by_ply[p]["ai_commentary"]).encode()) + 18 for p in with_ai}
        while result is not None and (size := len(_compact(result).encode())) > budget and drop:
            while drop and size > budget:
                ply = drop.pop(0)
                without.add(ply)
                omitted["commentary"].append(ply)
                size -= saves[ply]
            result = build(inputs, without)
        while result is not None and (size := len(_compact(result).encode())) > budget and inputs:
            by_ply = {p["ply"]: p for p in result["plies"]}
            while inputs and size > budget:
                ply = inputs.pop().ply
                omitted["records"].append(ply)
                size -= len(_compact(by_ply[ply]).encode()) + 1
            result = build(inputs, without)
        omitted["records"].sort()
        omitted["commentary"].sort()
        return result

    def _range(self, plies: str | None, count: int, limit: int, tool: str) -> range:
        """An asked range of at most `limit` plies; by default the first `limit` (AG6-D §3.3)."""

        if not plies:
            return range(1, min(count, limit) + 1)
        try:
            wanted = plies_range(plies, count)
        except InputError as error:
            raise AgentError(str(error)) from error
        if not wanted or wanted.start < 1:
            raise AgentError(f"the ply range {plies!r} is outside the game's {count} plies")
        if len(wanted) > limit:
            raise AgentError(f"{tool}는 한 번에 {limit}수까지 다룹니다: plies에 {limit}수 이하의 "
                             f"범위를 주세요 (요청 {len(wanted)}수)")  # fmt: skip
        return wanted

    # -- the game path (AG6-D §3.3, §4) --------------------------------------------------------

    def analyze_start(self, game_id: str, plies: str | None = None, cancel: bool = False) -> str:
        """Start the game's job, answer the one it has, or cancel it (AG6-D §4.1); the game key."""

        from .jobs import JobRefused

        game = self.game(game_id)
        count = len(game.parsed.sans)
        _check_game_path(count)
        if cancel:
            self.jobs.cancel(game.key)
            return game.key
        wanted = (
            range(1, count + 1) if not plies else self._range(plies, count, count, "analyze_game")
        )
        try:
            self.jobs.start(game.key, game_id, game.parsed, wanted)
        except JobRefused as error:
            raise AgentError(str(error)) from error
        return game.key

    def analyze_wait(self, key: str, seconds: float, on_progress=None) -> None:
        """AG6-D §4.1: the wait, holding no lock of the session's."""

        self.jobs.wait(key, seconds, on_progress)

    def analyze_answer(self, game_id: str) -> dict:
        game = self.game(game_id, hold=False)
        job = self.jobs.snapshot(game.key)
        return {"game": game_id, "job": job, "next": _next_job(job)}

    def analyze_game(self, game_id: str, plies: str | None = None, wait_seconds: float = 0,
                     cancel: bool = False, on_progress=None) -> dict:  # fmt: skip
        """`analyze_game` in one call (the server splits it so that its wait holds no lock)."""

        key = self.analyze_start(game_id, plies, cancel)
        if wait_seconds and not cancel:
            self.analyze_wait(key, wait_seconds, on_progress)
        return self.analyze_answer(game_id)

    def game_overview(self, game_id: str, plies: str | None = None) -> dict:
        """AG6-D §3.3: one line per ply of the asked range and the whole game's moments, from the
        jobs' summaries and the cache; nothing is analysed or charged."""

        game = self.game(game_id, hold=False)
        count = len(game.parsed.sans)
        _check_game_path(count)
        wanted = self._range(plies, count, LINES_LIMIT, "game_overview")
        summaries = {p: s for p in range(1, count + 1)
                     if (s := self._summary(game, p)) is not None}  # fmt: skip
        moments = _moments(summaries)
        self.moments[game.key] = [m["ply"] for m in moments]
        glossary = _glossary()
        lines = []
        for p in wanted:
            s = summaries.get(p)
            if s is None:
                lines.append({"ply": p, "move": _numbered_move(game.parsed, p), "analysed": False})
                continue
            line = {"ply": p, "move": s["move"], "grade": s["grade"],
                    "grade_ko": glossary["grades"].get(s["grade"]) if s["grade"] else None,
                    "label": s["label"],
                    "label_ko": glossary["labels"].get(s["label"]) if s["label"] else None,
                    "score": s["score"], "loss": s["loss"]}  # fmt: skip
            if s["best_move"] and s["best_move"] != s["san"]:
                line["best_move"] = s["best_move"]
            lines.append(line)
        answer = {
            "game": game_id,
            "headers": _capped_headers(game.parsed.game.headers),
            "warnings": [w[:300] for w in game.parsed.warnings if w.startswith("graded with")][:5],
            "plies": count,
            "analysed": len(summaries),
            "lines_range": _ranges(list(wanted)),
            "lines": lines,
            "moments": moments,
            "job": self.jobs.snapshot(game.key),
        }
        if count > LINES_LIMIT:
            answer["ranges"] = [_ranges(list(range(a, min(a + LINES_LIMIT, count + 1))))
                                for a in range(1, count + 1, LINES_LIMIT)]  # fmt: skip
        answer["next"] = self._next_moment(game.key)
        return _bounded_overview(answer, {m["ply"] for m in moments})

    def _summary(self, game: Game, ply: int) -> dict | None:
        """A ply's summary: one kept by a job or a digest while the cache's files are still the
        ones it was made from (review B2), else read from the cache (a replay when the pair is not
        kept), else None (not analysed)."""

        key, expected_request, build, _ = self._key(game.parsed, ply)
        digests = self.cache.file_digests(key)
        if digests is None:
            return None
        found = self.jobs.summary(game.key, ply)
        if found is not None and tuple(found["bundle"]) == digests:
            return found
        loaded = self.cache.get(key, expected_request, build)
        if loaded is None:
            return None
        summary = _ply_summary(self._record(game.parsed, ply, loaded, analysis=False))
        self.jobs.keep_summary(game.key, ply, summary)
        return summary

    def _next_moment(self, key: str) -> str:
        moments = self.moments.get(key)
        if not moments:
            return "해설할 수를 골라 ply로 요약판을 읽으세요."
        unread = [p for p in moments if p not in self.read.get(key, set())]
        if unread:
            return (f"중요한 장면 {', '.join(map(str, moments))}을 차례로 ply로 읽으세요: 다음은 "
                    f"ply {unread[0]}입니다. 모든 장면을 읽은 뒤에 해설을 씁니다.")  # fmt: skip
        return _NEXT_SUBMIT_ITEMS

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
        return self._explore(game_id, position, moves, search, "agent")

    def compare(self, game_id: str, position: dict, moves: list[str]) -> dict:
        """AG8-D §5: a line Calliope plays for the same reply, with one search at its end; its
        handle says `by: "calliope"` (neither the agent's line nor the engine's)."""

        return self._explore(game_id, position, moves, True, "calliope")

    def _explore(self, game_id: str, position: dict, moves, search: bool, by: str) -> dict:
        game = self.game(game_id)
        base = self.path(game, position)
        board = self._board(game, base)
        line = []
        for ply, text in enumerate(moves or [], start=1):
            move = parse_move(board, str(text), ply)
            line.append(move.uci())
            board.push(move)

        def hold():  # Calliope's comparison never waits for the engine (AG8-D §5)
            return self.engine_lock if by == "agent" else self.engine_lock.now()

        if search:  # admitted before any facts work, so a refusal leaves nothing half done
            with hold():  # the engine's result store is read (AG6-D §4.3)
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
                    "by": by,
                    "move": project(view.fact("move", node), frame),
                    "material_balance_white": flow.balance(FactColor.WHITE, i),
                })  # fmt: skip
        view, records = self._records(game, view, nodes[-1], EXPLORE_FAMILIES)
        source = {"kind": "facts_tree", "rev": view.rev}
        address = {"from": list(base), "moves": line}
        if by == "agent":
            self.explored += 1
        answer = {
            "start": self._position(game, view, nodes[start], base),
            "end": self._position(game, view, nodes[-1], (*base, *line)),
            "plies": plies,
            "end_facts": records,
            "units": {"material_balance_white": "points_v1"},
        }
        self._serve(game, [("x", source, address | {"by": by}, answer, answer)])
        if search:
            with hold():  # one search (AG6-D §4.3)
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
NEXT_OPENED = (
    "대국 전체를 해설하려면 analyze_game으로 모든 수의 분석을 시작하세요. 한 수만 해설하려면 그 수를 "
    'ply로 읽으세요(요약판으로 답합니다; 전체 분석은 view: "full").'
)
_NEXT_SUBMIT_ITEMS = (
    "읽은 장면들의 해설을 submit_commentary(items)로 한 번에 저장하세요. 저장해야 판에 나타납니다."
)
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


CHECK = "commentary_check_v3"  # S1–S8, the notes, handles in cites and states (MS-D §9)


def _stated(sentence: dict, verified: dict, served: dict | None) -> tuple[list[int], set[str]]:
    """AG8-D §6.2: (the indexes of the board items the sentence states whole, the parts it
    states). A verified proposition belongs to an item when its canonical form is one of the
    item's; an item is stated when all its propositions are."""

    states = [pid for pid in (sentence.get("states") or []) if pid in verified]
    forms = [canonical_record(verified[pid]) for pid in states]
    items, parts = [], set()
    for item in (served or {}).get("items", ()):
        if all(form in forms for form in item["canonical"]):
            items.append(item["index"])
            parts.add(item["part"])
    parts |= {proposition_part(verified[pid]) for pid in states}
    return items, parts


def _notes(sentences: list, stated: list, served: dict | None) -> list[dict]:
    """AG8-D §6.4: N-reason, N-reading — told, not refused."""

    notes = []
    if served and served["reason"] and not any("reason" in parts for _, parts in stated):
        notes.append({"rule": "N-reason", "note": "이 수의 ply 답에는 이유(part: reason) 근거가 "
                      "있습니다. 그것을 states로 말하는 문장을 두면 더 좋은 해설이 됩니다"})  # fmt: skip
    for index, (sentence, (_, parts)) in enumerate(zip(sentences, stated, strict=True)):
        if sentence.get("class") == "interpretation" and not parts & {"reason", "consequence"}:
            notes.append({"rule": "N-reading", "sentence": index, "note": "이 interpretation "
                          "문장은 이유나 결과 근거를 states로 두지 않았습니다. 판정이나 'X가 더 "
                          "나았다'만으로는 읽기가 아닙니다"})  # fmt: skip
    return notes


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


# -- the game path's helpers (AG6-D §3.3, §3.6, §6, §7) -------------------------------------------


def _compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _check_game_path(count: int) -> None:
    if count > GAME_PATH_PLIES:
        raise AgentError(f"the game path takes games of at most {GAME_PATH_PLIES} plies, not "
                         f"{count}: read its plies with ply, judge_move, facts and explore")  # fmt: skip


def _capped_headers(headers) -> dict:
    """AG6-D §3.6: a header value of at most HEADER_CAP characters."""

    return {k: (v[: HEADER_CAP - 1] + "…" if isinstance(v, str) and len(v) > HEADER_CAP else v)
            for k, v in headers.items()}  # fmt: skip


def _numbered_move(parsed: ParsedGame, ply: int) -> str:
    board = chess.Board(parsed.game.moves[ply - 1].fen_before)
    side = "white" if board.turn == chess.WHITE else "black"
    return numbered(board.fullmove_number, side, parsed.sans[ply - 1])


def _ply_summary(record: dict) -> dict:
    """What the overview and the moments read of a ply's record (AG6-D §3.3): its move, grade and
    label, the score after it, the best move, the loss and White's expected points."""

    evaluation = record.get("evaluation") or {}
    expected = (evaluation.get("expected") or {}).get("played")  # the mover's, in 1/2000
    white = None if expected is None else expected if record["side"] == "white" else 2000 - expected
    label = record.get("label")
    return {
        "ply": record["ply"],
        "san": record["san"],
        "move": numbered(record["move_number"], record["side"], record["san"]),
        "grade": record.get("grade"),
        "label": label.get("kind") if isinstance(label, dict) else label,
        "score": score_text(evaluation.get("played")),
        "best_move": (evaluation.get("best_move") or {}).get("san"),
        "loss": evaluation.get("loss"),
        "white_expected": white,
        "bundle": [record["bundle"]["tree"], record["bundle"]["graph"]],  # what it was made from
    }


MOMENT_REASONS = {
    "blunder": 1,
    "mistake": 2,
    "miss": 3,
    "brilliant": 4,
    "great": 5,
    "loss": 6,
    "turning_point": 7,
}  # fmt: skip (AG6-D §3.3's priorities)


def _moments(summaries: dict[int, dict]) -> list[dict]:
    """AG6-D §3.3: each analysed ply's reasons; one moment per ply; ranked by the best priority,
    then the larger loss, then the earlier ply; the first MOMENTS, in ply order."""

    reasons: dict[int, list[str]] = {p: [] for p in summaries}
    for p, s in summaries.items():
        if s["grade"] in ("blunder", "mistake"):
            reasons[p].append(s["grade"])
        if s["label"] in ("miss", "brilliant", "great"):
            reasons[p].append(s["label"])
    losses = sorted((p for p, s in summaries.items() if (s["loss"] or 0) >= 150),
                    key=lambda p: (-summaries[p]["loss"], p))[:3]  # fmt: skip
    for p in losses:
        reasons[p].append("loss")
    for p, s in summaries.items():
        before = summaries.get(p - 1)
        if before is None or s["white_expected"] is None or before["white_expected"] is None:
            continue
        a, b = before["white_expected"], s["white_expected"]
        if (a < 1000 <= b or b < 1000 <= a) and abs(b - a) >= 300:
            reasons[p].append("turning_point")
    candidates = [p for p in reasons if reasons[p]]
    ranked = sorted(candidates, key=lambda p: (min(MOMENT_REASONS[r] for r in reasons[p]),
                                               -(summaries[p]["loss"] or 0), p))  # fmt: skip
    chosen = sorted(ranked[:MOMENTS])
    return [{"ply": p, "move": summaries[p]["move"],
             "reasons": sorted(reasons[p], key=MOMENT_REASONS.get)} for p in chosen]  # fmt: skip


def _bounded_overview(answer: dict, moments: set[int]) -> dict:
    """AG6-D §3.6: under OVERVIEW_LIMIT by construction; should that change, the lines of plies
    that are not moments lose `best_move` and `loss`, then go (counted); still over: an error."""

    if len(_compact(answer)) <= OVERVIEW_LIMIT:
        return answer
    for line in answer["lines"]:
        if line["ply"] not in moments:
            line.pop("best_move", None)
            line.pop("loss", None)
    if len(_compact(answer)) > OVERVIEW_LIMIT:
        kept = [line for line in answer["lines"] if line["ply"] in moments]
        answer["not_shown"] = {"lines": len(answer["lines"]) - len(kept)}
        answer["lines"] = kept
    if len(_compact(answer)) > OVERVIEW_LIMIT:
        raise AgentError(f"the answer exceeds its size bound ({len(_compact(answer))} > "
                         f"{OVERVIEW_LIMIT})")  # fmt: skip
    return answer


def _view_text(game_id: str, view: dict, wanted: range, count: int) -> str:
    """`show_game`'s `content` (AG3-D D10, AG6-D §6.1): the analysed plies, the job's progress,
    the plies with commentary, what was left out and the other ranges."""

    grades = _glossary()["grades"]
    states = {e["ply"]: e for e in view["plies"]}
    analysed = sum(1 for e in view["plies"] if e["state"] == "analysed")
    lines = [f"게임 {game_id}: {count}수 가운데 {analysed}수가 분석되어 있습니다."]
    job = view["job"]
    if job is not None and job["state"] in ACTIVE:
        lines.append(f"분석 작업: {job['state']} {job['done']}/{job['total']}.")
    result = view["result"]
    if result is None:
        lines.append(f"수 {_ranges(list(wanted))}에는 아직 분석된 수가 없습니다: analyze_game으로 "
                     "분석을 시작하세요.")  # fmt: skip
        return "\n".join(lines)
    shown = [p["ply"] for p in result["plies"]]
    lines.append(f"판에 수 {_ranges(shown)}의 분석을 보여 줍니다.")
    missing = [p for p in wanted if states[p]["state"] != "analysed"]
    if missing:
        lines.append(f"분석되지 않은 수: {_ranges(missing)}.")
    omitted = view["omitted"]
    for kind, word in (("records", "분석"), ("commentary", "해설")):
        if omitted[kind]:
            lines.append(f"크기 때문에 판에 담지 못한 {word}: 수 {_ranges(omitted[kind])} — "
                         "show_game(plies=…)로 더 좁은 범위를 여세요.")  # fmt: skip
    if count > len(wanted):
        lines.append(f"이 판은 수 {_ranges(list(wanted))}입니다. 다른 범위는 show_game(plies=…)로 "
                     "엽니다.")  # fmt: skip
    for p in result["plies"]:
        dots = "." if p["side"] == "white" else "..."
        grade = grades.get(p["grade"], "판정 보류") if p["grade"] else "판정 보류"
        ai = " · AI 해설 있음" if "ai_commentary" in p else ""
        lines.append(f"{p['move_number']}{dots}{p['san']} (수 {p['ply']}): {grade}{ai}")
    return "\n".join(lines)


def _next_job(job: dict | None) -> str:
    """`next` after `analyze_game` (AG6-D §7, re-review B8)."""

    if job is None:
        return "analyze_game으로 분석을 시작하세요."
    state = job["state"]
    if state in ("queued", "running") or (
        state == "waiting" and job.get("resume_after_seconds", 0) <= WAIT_LIMIT
    ):
        return f"analyze_game(wait_seconds={WAIT_LIMIT})으로 끝날 때까지 기다리세요."
    if state == "waiting":
        return ("분석이 시간당 예산을 다 써 resume_after_seconds 뒤에 이어집니다. 지금까지 분석된 "
                "수로 game_overview를 보고, 나머지가 언제 이어지는지 사용자에게 알리세요. 그 "
                "전에는 analyze_game을 다시 부르지 마세요.")  # fmt: skip
    if state == "done":
        return "game_overview로 대국의 흐름과 중요한 장면을 보세요."
    return "analyze_game을 다시 부르면 이어서 분석합니다(이미 분석된 수는 그대로 씁니다)."


def _annotate(digest: dict, relations: dict, answer: dict) -> None:
    """MS-D §5: each listed relation claim with its relation (kind, place, time, pieces) and its
    link to its consequence (by handle); a claim §6 settles under a board item leaves `claims`
    there."""

    refs = {c["id"]: c.get("ref") for c in answer["analysis"]["claims"]}
    by_ref = {refs[cid]: read for cid, read in relations.items() if refs.get(cid)}
    for entry in digest.get("claims", ()):
        read = by_ref.get(entry.get("ref"))
        if read is None:
            continue
        r = read.relation
        place = {"at": r.place.at}
        if r.place.at == "line":  # the engine line: its search and rank (review N1)
            place |= {"ply": r.place.ply, "search": r.place.search, "rank": r.place.rank}
        entry["relation"] = {"kind": r.kind, "place": place, "time": r.time,
                             "pieces": [[name, p.square] for name, p in r.roles]}  # fmt: skip
        if read.link is not None:
            link = {"kind": read.link.kind, "to": refs.get(read.link.to)}
            if read.link.did is not None:
                link["did"] = read.link.did
            entry["link"] = link
