"""One MCP session (AG-D §2): its games, trees, handles and budget, and the tools' work.

Stored analyses are read-only: plies come from the ply cache or are analysed through the
pipeline's per-ply path and put into it (§3.3). Facts come from one engine-less facts tree per
game, rooted at the game's start, every asked path extended into it (§3.4). Searches run in
one-node search trees opened at the searched position. Every engine call the session causes goes
through the session's metering port (§3.5).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
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
    EngineSlot,
    InputError,
    JobFailed,
    ParsedGame,
    PlyCache,
    StoreFailed,
    analyse_ply,
    normalized_ply,
    parse_game,
    plies_range,
)

from .budget import Budget, BudgetError, Limits, MeteredPort, SearchBudgetExhausted
from .handles import Handles
from .projection import identity, project

GAME_KEY_VERSION = "game_key_v1"
DEFAULT_FAMILIES = ("status", "material", "pieces")
EXPLORE_FAMILIES = ("status", "pieces", "exchange")
SCORE_UNITS = {"cp": "cp_white", "mate": "mate_white", "expected": "expected_2000_side_to_move"}


class AgentError(ValueError):
    """A request the session cannot answer (a tool error with this message)."""


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def game_key(parsed: ParsedGame) -> str:
    """`game_key_v1` (AG-D §8): the game part of the job id's preimage."""

    game = parsed.game
    preimage = {
        "v": GAME_KEY_VERSION,
        "start_fen": game.start_fen,
        "moves": [m.uci for m in game.moves],
        "headers": dict(game.headers),
    }
    return hashlib.sha256(canonical(preimage)).hexdigest()


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
    id: str
    parsed: ParsedGame
    key: str
    facts: object | None = None  # its facts tree, opened on first use
    lines: int = 0  # facts-tree line labels used


@dataclass
class Session:
    data: Path
    start: Callable[[], object]  # starts the engine (an EnginePort)
    limits: Limits = field(default_factory=Limits)
    profile: EngineProfile = field(default_factory=EngineProfile)

    def __post_init__(self) -> None:
        self.budget = Budget(self.limits)
        self.slot = EngineSlot(lambda: MeteredPort(self.start(), self.budget.meter))
        self.cache = PlyCache(self.data / "plies")
        self.handles = Handles()
        self.games: dict[str, Game] = {}
        self.facts_engine = FactEngine()
        self._search_engine: tuple[object, FactEngine] | None = None
        self._build: tuple[object, object, str] | None = None
        self.searched: set[tuple[str, tuple[str, ...]]] = set()
        self.explored = 0

    def close(self) -> None:
        self.slot.close()

    # -- games ------------------------------------------------------------------------------

    def game(self, game_id: str) -> Game:
        found = self.games.get(game_id)
        if found is None:
            raise AgentError(f"no game {game_id!r} in this session (open it with open_game)")
        return found

    def open_game(
        self,
        pgn: str | None = None,
        fen: str | None = None,
        moves: list[str] | None = None,
        plies: str | None = None,
        on_ply: Callable[[int, int, str], None] | None = None,
    ) -> dict:
        if (pgn is None) == (fen is None and moves is None):
            raise AgentError("give either `pgn`, or `fen` and/or `moves`")
        try:
            parsed = parse_game(pgn if pgn is not None else pgn_of(fen, moves or []))
            wanted = plies_range(plies, len(parsed.sans)) if plies else range(0)
        except InputError as error:
            raise AgentError(str(error)) from error
        if plies and (not wanted or wanted.start < 1):  # the analysis server's rule (`checked`)
            raise AgentError(f"the ply range {plies!r} is outside the game's "
                             f"{len(parsed.sans)} plies")  # fmt: skip
        cached = {ply: self._cached(parsed, ply) for ply in range(1, len(parsed.sans) + 1)}
        self.budget.admit_analyses([p for p in wanted if not cached[p]])
        game = Game(f"g{len(self.games) + 1}", parsed, game_key(parsed))
        self.games[game.id] = game  # registered once it is read and admitted
        summaries = {}
        for done, ply in enumerate(wanted, start=1):
            record, was_cached = self._analysed(game, parsed, ply)
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
        return {
            "game": game.id,
            "game_key": game.key,
            "start_fen": parsed.game.start_fen,
            "headers": dict(parsed.game.headers),
            "warnings": list(parsed.warnings),
            "moves": out_moves,
            "budget_left": self.budget.left(),
        }

    # -- analyses (AG-D §3.1, §3.3) ---------------------------------------------------------

    def ply(self, game_id: str, ply: int) -> dict:
        game = self.game(game_id)
        if not 1 <= ply <= len(game.parsed.sans):
            raise AgentError(f"the game has plies 1 to {len(game.parsed.sans)}, not {ply}")
        record, cached = self._analysed(game, game.parsed, ply)
        return record | {"cached": cached, "budget_left": self.budget.left()}

    def judge_move(self, game_id: str, position: dict, move: str) -> dict:
        game = self.game(game_id)
        path = self.path(game, position)
        board = self._board(game, path)
        uci = parse_move(board, move, len(path) + 1).uci()
        parsed = variation(game.parsed, [*path, uci])
        record, cached = self._analysed(game, parsed, len(path) + 1)
        played = game.parsed.uci[: len(path) + 1] == (*path, uci)
        return record | {"played": played, "cached": cached, "budget_left": self.budget.left()}

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

    def _analysed(self, game: Game, parsed: ParsedGame, ply: int) -> tuple[dict, bool]:
        loaded, cached, digest = self._load_or_analyse(parsed, ply)
        port = self.slot.port
        document = game_result(
            parsed.game,
            EngineRun(port.identity, self.profile),
            [PlyInput(ply, loaded.analysis, loaded.rendered, loaded.bundle)],
            analysis=True,
        )
        record = document["plies"][0]
        source = {
            "kind": "analysis",
            "path": list(parsed.uci[:ply]),
            "tree": loaded.bundle.tree,
            "graph": loaded.bundle.graph,
            "build": digest,
        }
        self._serve_analysis(game, record, source)
        return record, cached

    def _serve_analysis(self, game: Game, record: dict, source: dict) -> None:
        analysis = record["analysis"]
        for judgement in analysis["judgements"]:
            judgement["ref"] = self.handles.serve(
                "j", game.key, source, {"move": judgement["move"]["uci"]}, judgement
            )
            for line in (judgement["played"], judgement["best"], *judgement["alternatives"]):
                if line is not None:
                    address = {"search": line["search"], "rank": line["rank"]}
                    line["ref"] = self.handles.serve("s", game.key, source, address, line)
        for claim in analysis["claims"]:
            claim["ref"] = self.handles.serve("c", game.key, source, {"claim": claim["id"]}, claim)

    # -- positions and the facts tree (AG-D §3.2, §3.4) --------------------------------------

    def path(self, game: Game, position: dict) -> tuple[str, ...]:
        """The canonical UCI path from the game's root to a position argument."""

        parsed = game.parsed
        if not isinstance(position, dict):
            raise AgentError(
                "a position is {'ply': n, 'at': 'before'|'after'} or {'from_root': [...]}"
            )
        if "from_root" in position:
            board = chess.Board(parsed.game.start_fen)
            out = []
            for ply, text in enumerate(position["from_root"], start=1):
                move = parse_move(board, str(text), ply)
                out.append(move.uci())
                board.push(move)
            return tuple(out)
        ply, at = position.get("ply"), position.get("at", "after")
        if (
            not isinstance(ply, int)
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
            self.budget.admit_nodes(1)
            game.facts = self.facts_engine.open(OpenRequest(root=game.parsed.root, engine=None))
            self.budget.charge_nodes(1)
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
                self.budget.admit_nodes(len(rest))
                game.lines += 1
                label = f"p-{game.lines}"  # a new label each time (AG-D §3.4)
                line = InputLine(label, rest, start=nodes[-1])
                try:
                    self.facts_engine.extend(tree, ExtendRequest((line,), EXPLORED, NONE))
                except FactEngineError as error:
                    raise AgentError(f"the facts tree refuses the path: {error}") from error
                self.budget.charge_nodes(len(rest))
                view = tree.view()
                for step in rest:
                    nodes.append(view.child(nodes[-1], step))
                return view, nodes
            nodes.append(child)
        return view, nodes

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
        served = {}
        for name, record in records.items():
            address = {"position": list(path), "family": name}
            ref = self.handles.serve("f", game.key, source, address, record)
            served[name] = {"ref": ref, "record": record}
        return {
            "position": self._position(game, view, nodes[-1], path),
            "families": served,
            "budget_left": self.budget.left(),
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
        answer["ref"] = self.handles.serve("x", game.key, source, address | {"by": "agent"}, answer)
        if search:
            answer["search"] = self._search(game, (*base, *line))
        answer["budget_left"] = self.budget.left()
        return answer

    def _admit_search(self, game: Game, path) -> None:
        if self._board(game, path).is_game_over(claim_draw=False):
            raise AgentError("the game is over at that position: there is nothing to search")
        if (game.key, tuple(path)) not in self.searched:  # a repeated search is a store hit
            self.budget.admit_search()
        self.budget.admit_nodes(1)

    def _engine(self) -> FactEngine:
        port = self.slot.port
        if self._search_engine is None or self._search_engine[0] is not port:
            self._search_engine = (port, FactEngine(engine=port))  # its store lives with it
        return self._search_engine[1]

    def _search(self, game: Game, path) -> dict:
        """One survey of the position in a one-node search tree (AG-D §3.4, C1)."""

        root = RootSpec(fen=game.parsed.root.fen, moves=tuple(path))
        request = OpenRequest(
            root=root,
            families=(),
            budget=SessionBudget(max_searches=1),
            engine=self.profile,
            root_expansion=ExpansionSpec(survey=True, comparison=False, attach_lines=False),
        )
        self.budget.admit_nodes(1)  # again: the line's facts nodes are charged by now
        try:
            tree = self._engine().open(request)
        except SearchBudgetExhausted as error:
            raise BudgetError(f"{error}; left: {self.budget.left()}") from error
        except FactEngineError as error:
            raise AgentError(f"the search was refused: {error}") from error
        self.budget.charge_nodes(1)
        view = tree.view()
        bindings = view.searches(view.root)
        if not bindings:
            raise AgentError("the position has no search")
        self.searched.add((game.key, tuple(path)))
        search = view.search(bindings[0].search_id)
        frame = view.node(view.root)
        mover = frame.side_to_move
        source = {"kind": "search", "position": list(path), "search": search.search_id}
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
            record["ref"] = self.handles.serve("s", game.key, source, {"rank": line.rank}, record)
            lines.append(record)
        return {
            "position": {"from_root": list(path), "fen": frame.fen},
            "profile": search.profile.name,
            "multipv": search.multipv,
            "lines": lines,
            "units": SCORE_UNITS | {"wdl": "permille_white"},
        }


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


def _summary(record: dict) -> dict:
    return {
        "grade": record["grade"],
        "label": record["label"],
        "text": record["text"],
    }
