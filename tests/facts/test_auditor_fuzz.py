"""F1 acceptance: the fact engine against the naive auditor over seeded games (design §9.4).

Every game is audited from one of four root forms (startpos, startpos + pre-root moves, FEN +
moves, bare FEN), plus an explored branch. Separate pawnless endgames run the clock past the
fifty- and seventy-five-move marks and keep playing past automatic draws. Generators are biased
toward captures, promotions, castling, en passant and repetition so the rules are exercised.
"""

import os
import random
from collections import Counter

import chess
from facts_auditor import advance, audit_line, root_cursor

from calliope.facts import (
    EXPLORED,
    PLAYED,
    ExtendRequest,
    FactEngine,
    InputLine,
    OpenRequest,
    RoleKind,
    RootSpec,
    TerminalKind,
)

GAMES = int(os.environ.get("FACTS_FUZZ_GAMES", "400"))  # F0 §9.4 asks for at least 400
ENDGAMES = max(4, GAMES // 8)
MAX_PLIES = 160
ENGINE = FactEngine()


def _double_push_next_to_pawn(board: chess.Board, move: chess.Move) -> bool:
    if board.piece_type_at(move.from_square) != chess.PAWN:
        return False
    if abs(chess.square_rank(move.to_square) - chess.square_rank(move.from_square)) != 2:
        return False
    file, rank = chess.square_file(move.to_square), chess.square_rank(move.to_square)
    return any(
        board.piece_at(chess.square(f, rank)) == chess.Piece(chess.PAWN, not board.turn)
        for f in (file - 1, file + 1)
        if 0 <= f < 8
    )


def _undo_pattern(board: chess.Board, out: chess.Move, cycles: int) -> list[chess.Move]:
    back = chess.Move(out.to_square, out.from_square)
    replies = [m for m in board.legal_moves if not board.is_zeroing(m)]
    if not replies:
        return []
    reply = replies[0]
    return ([reply, back, chess.Move(reply.to_square, reply.from_square), out] * cycles)[:-1]


def _game(rng: random.Random) -> list[chess.Move]:
    board = chess.Board()
    moves: list[chess.Move] = []
    shuffle: list[chess.Move] = []
    while not board.is_game_over() and len(moves) < MAX_PLIES:
        legal = list(board.legal_moves)
        if shuffle and shuffle[0] in legal:
            move = shuffle.pop(0)
        elif special := [m for m in legal if board.is_en_passant(m) or board.is_castling(m)]:
            shuffle = []
            move = rng.choice(special) if rng.random() < 0.8 else rng.choice(legal)
        elif doubles := [m for m in legal if _double_push_next_to_pawn(board, m)]:
            shuffle = []
            move = rng.choice(doubles) if rng.random() < 0.5 else rng.choice(legal)
        else:
            shuffle = []
            preferred = [
                m
                for m in legal
                if board.is_capture(m)
                or m.promotion
                or board.is_castling(m)
                or board.gives_check(m)
            ]
            move = rng.choice(preferred if preferred and rng.random() < 0.5 else legal)
            knights = [m for m in legal if board.piece_type_at(m.from_square) == chess.KNIGHT]
            if knights and rng.random() < 0.05:  # start a back-and-forth to provoke repetition
                move = rng.choice(knights)
                shuffle = [move]
        board.push(move)
        moves.append(move)
        if shuffle and len(shuffle) == 1 and shuffle[0] == move:
            shuffle = _undo_pattern(board, move, rng.choice((1, 1, 1, 1, 2, 4)))
    return moves


def _endgame(rng: random.Random) -> tuple[chess.Board, list[chess.Move]]:
    """A pawnless position played for up to 320 plies, mostly without captures."""

    while True:
        board = chess.Board(None)
        squares = rng.sample(chess.SQUARES, 6)
        pieces = "KRBkrn" if rng.random() < 0.5 else "KQNkrb"
        for square, symbol in zip(squares, pieces, strict=True):
            board.set_piece_at(square, chess.Piece.from_symbol(symbol))
        board.turn = rng.choice((chess.WHITE, chess.BLACK))
        if board.is_valid() and not board.is_game_over():
            break
    start = board.copy()
    moves: list[chess.Move] = []
    while len(moves) < 320 and any(board.legal_moves):
        legal = list(board.legal_moves)
        quiet = [m for m in legal if not board.is_capture(m)]
        move = rng.choice(quiet if quiet and rng.random() < 0.97 else legal)
        board.push(move)
        moves.append(move)
    return start, moves


def _open_and_play(rng: random.Random, start: chess.Board, moves: list[chess.Move], form: int):
    """Open one root form over the true game `start + moves`; return (tree, nodes, cursor)."""

    uci = [m.uci() for m in moves]
    n = len(moves)
    if form in (0, 1):  # the true start position (+ pre-root moves for form 1)
        cut, pre = 0, (rng.randrange(1, max(2, n // 2)) if form == 1 else 0)
    else:  # a FEN cut out of the game (+ pre-root moves for form 2)
        cut = rng.randrange(1, max(2, n - 4))
        pre = rng.randrange(1, max(2, (n - cut) // 2)) if form == 2 else 0
    full = start.copy()
    for move in moves[:cut]:
        full.push(move)
    fen = full.fen()
    known = chess.Board(fen)
    for move in moves[cut : cut + pre]:
        full.push(move)
        known.push(move)
    tree = ENGINE.open(OpenRequest(root=RootSpec(fen=fen, moves=tuple(uci[cut : cut + pre]))))
    cursor = root_cursor(full, known)
    tail = tuple(uci[cut + pre :])
    if not tail:
        return tree, (tree.root,), cursor
    ENGINE.extend(tree, ExtendRequest((InputLine("line", tail),), PLAYED))
    return tree, tree.view().input_line("line").nodes, cursor


def _branch(rng: random.Random, tree, nodes, cursor) -> int:
    """Explore a random alternative from a random node of the audited line."""

    view = tree.view()
    at = rng.randrange(len(nodes))
    played = [chess.Move.from_uci(view.node(n).incoming_move) for n in nodes[1 : at + 1]]
    branch_cursor = advance(cursor, played)
    board = branch_cursor.full.copy()
    alt: list[str] = []
    for _ in range(rng.randrange(3, 9)):
        legal = list(board.legal_moves)
        if not legal:
            break
        move = rng.choice(legal)
        alt.append(move.uci())
        board.push(move)
    if not alt:
        return 0
    ENGINE.extend(tree, ExtendRequest((InputLine("alt", tuple(alt), start=nodes[at]),), EXPLORED))
    line = tree.view().input_line("alt", RoleKind.EXPLORED)
    return audit_line(tree, line.nodes, branch_cursor)


def test_fact_engine_matches_auditor() -> None:
    rng = random.Random(20261008)
    audited = 0
    seen: Counter[str] = Counter()
    jobs = [(chess.Board(), _game(rng)) for _ in range(GAMES)]
    jobs += [_endgame(rng) for _ in range(ENDGAMES)]
    for number, (start, moves) in enumerate(jobs):
        form = number % 4 if len(moves) > 12 else 0
        tree, nodes, cursor = _open_and_play(rng, start, moves, form)
        audited += audit_line(tree, nodes, cursor)
        audited += _branch(rng, tree, nodes, cursor)

        for node in tree.view().nodes():
            seen["incomplete"] += not node.history_complete
            seen["after_terminal"] += node.after_terminal
            seen["unproven"] += node.terminal.kind is TerminalKind.UNPROVEN
            seen["automatic_draw"] += node.terminal.kind is TerminalKind.AUTOMATIC_DRAW
            seen["clock150"] += node.halfmove_clock >= 150
            seen[f"form{form}"] += 1
        replay = start.copy()
        for move in moves:
            seen["promotion"] += move.promotion is not None
            seen["castling"] += replay.is_castling(move)
            seen["en_passant"] += replay.is_en_passant(move)
            replay.push(move)
            seen["threefold"] += replay.is_repetition(3)
            seen["fivefold"] += replay.is_fivefold_repetition()

    print(f"audited={audited} {dict(sorted(seen.items()))}")
    assert audited > 80 * GAMES
    floor = max(1, GAMES // 40)
    for key in (
        "promotion",
        "castling",
        "en_passant",
        "threefold",
        "fivefold",
        "incomplete",
        "after_terminal",
        "unproven",
        "automatic_draw",
        "clock150",
        "form0",
        "form1",
        "form2",
        "form3",
    ):
        assert seen[key] >= floor, f"generator never exercised {key}"
