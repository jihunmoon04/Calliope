"""F1 acceptance: the fact engine against the naive auditor over 400 seeded games (§9.4).

Games are random but biased toward captures, promotions, castling and repetition so that the
identity and draw rules are exercised; each also reruns from a mid-game bare FEN, where history
is incomplete and draw facts must stay sound.
"""

import os
import random

import chess
from facts_auditor import audit_line

from calliope.facts import PLAYED, ExtendRequest, FactEngine, InputLine, OpenRequest, RootSpec

GAMES = int(os.environ.get("FACTS_FUZZ_GAMES", "400"))  # F0 §9.4 asks for at least 400
MAX_PLIES = 160
ENGINE = FactEngine()


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
                out = rng.choice(knights)
                shuffle = [out]
                move = out
        board.push(move)
        moves.append(move)
        if shuffle and len(shuffle) == 1 and shuffle[0] == move:
            shuffle = _undo_pattern(board, move, rng.choice((1, 1, 1, 1, 2, 4)))
    return moves


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
    """Moves that return both sides to an earlier position: back (us), any reversible reply pair."""

    back = chess.Move(out.to_square, out.from_square)
    replies = [m for m in board.legal_moves if not board.is_zeroing(m)]
    if not replies:
        return []
    reply = replies[0]
    return ([reply, back, chess.Move(reply.to_square, reply.from_square), out] * cycles)[:-1]


def test_fact_engine_matches_auditor_over_400_games() -> None:
    rng = random.Random(20261008)
    audited = 0
    repetitions = promotions = castlings = en_passants = fivefolds = 0
    for game in range(GAMES):
        moves = _game(rng)
        tree = ENGINE.open(OpenRequest())
        ENGINE.extend(
            tree, ExtendRequest((InputLine(f"g{game}", tuple(m.uci() for m in moves)),), PLAYED)
        )
        line = tree.view().line(f"played::g{game}#0")
        audited += audit_line(tree, line.nodes, chess.Board(), complete=True)

        replay = chess.Board()
        for move in moves:
            repetitions += replay.is_repetition(3)
            promotions += move.promotion is not None
            castlings += replay.is_castling(move)
            en_passants += replay.is_en_passant(move)
            replay.push(move)
            fivefolds += replay.is_fivefold_repetition()

        if len(moves) > 20:  # rerun the tail from a bare mid-game FEN (incomplete history)
            cut = rng.randrange(10, len(moves) - 5)
            oracle = chess.Board()
            for move in moves[:cut]:
                oracle.push(move)
            bare = ENGINE.open(OpenRequest(root=RootSpec(fen=oracle.fen())))
            tail = tuple(m.uci() for m in moves[cut:])
            ENGINE.extend(bare, ExtendRequest((InputLine("tail", tail),), PLAYED))
            nodes = bare.view().line("played::tail#0").nodes
            audited += audit_line(bare, nodes, oracle, complete=False)

    print(
        f"audited={audited} rep3={repetitions} rep5={fivefolds} promo={promotions} castle={castlings} ep={en_passants}"
    )
    assert audited > 80 * GAMES
    # the generator must actually exercise the rules this audit exists for
    assert min(repetitions, promotions, castlings) > GAMES // 8 and en_passants > GAMES // 40
    assert fivefolds > GAMES // 100
