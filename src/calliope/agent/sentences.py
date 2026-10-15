"""The sentence check (AG-D §5.3, S1–S6): sentences are checked as sources only.

Each sentence cites propositions; every move, score, mate, square and number written as such in
it must come from them (S3). The wording is not checked: an accepted commentary is
`SOURCE_VERIFIED` (`commentary_check_v1`), and an `interpretation` sentence is stored and shown as
the agent's reading.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

import chess

MAX_SENTENCES = 12
MAX_LENGTH = 300
CLASSES = ("sourced", "interpretation")

_RUN = re.compile(r"[A-Za-z0-9.+\-−#=]+")
_NUMBER = re.compile(r"\d+(\.|\.\.\.)")
_SAN = r"(O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8](=[QRBN])?|[a-h][1-8]=[QRBN]|[a-h][1-8])[+#]?"
_MOVE = re.compile(rf"(?:(\d+)(\.\.\.|\.) ?)?({_SAN})")
_SCORE = re.compile(r"[+\-−]?\d+\.\d{1,2}")
_MATE = re.compile(r"(?:M|#)(\d+)")
_SQUARE = re.compile(r"[a-h][1-8]")
_INTEGER = re.compile(r"[+\-−]?\d+")
_PAWN_PUSH = re.compile(r"[a-h][1-8][+#]?")


@dataclass
class Allowed:
    """What a verified proposition lets a sentence write (S3)."""

    moves: list[tuple[str, str]] = field(default_factory=list)  # (uci, FEN before the move)
    squares: set[str] = field(default_factory=set)
    integers: set[int] = field(default_factory=set)
    scores: set[int] = field(default_factory=set)  # cp_white
    mates: set[int] = field(default_factory=set)  # |mate_white|

    def add_move(self, uci: str, fen: str) -> None:
        self.moves.append((uci, fen))
        self.squares |= {uci[:2], uci[2:4]}
        self.integers.add(chess.Board(fen).fullmove_number)

    def add_line(self, fen: str, moves) -> None:
        board = chess.Board(fen)
        for uci in moves:
            self.add_move(uci, board.fen())
            board.push_uci(uci)

    def merge(self, other: Allowed) -> None:
        self.moves += other.moves
        self.squares |= other.squares
        self.integers |= other.integers
        self.scores |= other.scores
        self.mates |= other.mates


def tokens(text: str) -> list[str]:
    """S3's tokens: runs of `[A-Za-z0-9.+\\-−#=]`; a move number joined with the next token; a
    trailing `.` dropped unless the token is a bare move number."""

    runs = [(m.group(), m.start(), m.end()) for m in _RUN.finditer(text)]
    out, i = [], 0
    while i < len(runs):
        token, _, end = runs[i]
        if _NUMBER.fullmatch(token) and i + 1 < len(runs) and text[end : runs[i + 1][1]] == " ":
            token = f"{token} {runs[i + 1][0]}"
            i += 1
        if token.endswith(".") and not _NUMBER.fullmatch(token):
            token = token.rstrip(".")
        if token:  # a lone full stop is no token
            out.append(token)
        i += 1
    return out


def _signed(text: str) -> int:
    return int(text.replace("−", "-"))


def _move_ok(number: str | None, dots: str | None, san: str, allowed: Allowed) -> bool:
    for uci, fen in allowed.moves:
        board = chess.Board(fen)
        try:
            if board.parse_san(san).uci() != uci:
                continue
        except ValueError:
            continue
        if number is not None:
            black = board.turn == chess.BLACK
            if int(number) != board.fullmove_number or (dots == "...") != black:
                continue
        return True
    return False


def _score_ok(token: str, allowed: Allowed) -> bool:
    text = token.replace("−", "-")
    value = Decimal(text)
    places = len(text.split(".")[1])
    quantum = Decimal(1).scaleb(-places)
    for cp in allowed.scores:
        exact = Decimal(cp) / 100
        rounded = exact.copy_abs().quantize(quantum, rounding=ROUND_HALF_UP).copy_sign(exact)
        if rounded == value and (cp >= 0 or text.startswith("-")):
            return True
    return False


def check_token(token: str, allowed: Allowed) -> str | None:
    """None when the token is allowed, else the violation."""

    if not (re.search(r"\d", token) or token in ("O-O", "O-O-O")):
        return None
    move = _MOVE.fullmatch(token)
    if move and not (move[1] is None and _PAWN_PUSH.fullmatch(move[3])):
        if _move_ok(move[1], move[2], move[3], allowed):
            return None
        return f"the move {token!r} is not a move of the cited propositions"
    if _SCORE.fullmatch(token):
        return None if _score_ok(token, allowed) else (
            f"the score {token!r} is not a cited engine score")  # fmt: skip
    if mate := _MATE.fullmatch(token):
        return None if int(mate[1]) in allowed.mates else f"the mate {token!r} is not cited"
    if _SQUARE.fullmatch(token):
        return None if token in allowed.squares else f"the square {token!r} is not cited"
    if _INTEGER.fullmatch(token):
        value = _signed(token)
        if token[0] in "+-−":
            ok = value in allowed.integers
        else:
            ok = value in allowed.integers or value in {abs(x) for x in allowed.integers}
        return None if ok else f"the number {token!r} is not in the cited propositions"
    return f"{token!r} is neither a move, a score, a mate, a square nor a cited number"


def check_sentences(language: str, sentences, allowed: dict[str, Allowed]) -> list[dict]:
    """S1–S4 over the submission's sentences; `allowed` maps every verified proposition's id."""

    problems: list[dict] = []
    if language != "ko":
        problems.append({"rule": "S1", "problem": f"the language is ko, not {language!r}"})
    if not isinstance(sentences, list) or not 1 <= len(sentences) <= MAX_SENTENCES:
        return problems + [{"rule": "S1", "problem": f"1 to {MAX_SENTENCES} sentences"}]
    if not any(isinstance(s, dict) and s.get("class") == "sourced" for s in sentences):
        problems.append({"rule": "S1", "problem": "at least one sentence is sourced"})
    for index, sentence in enumerate(sentences):
        where = {"sentence": index}
        if not isinstance(sentence, dict) or not isinstance(sentence.get("text"), str):
            problems.append(where | {"rule": "S1", "problem": "a sentence is {text, class, cites}"})
            continue
        text = sentence["text"]
        if not text.strip() or len(text) > MAX_LENGTH:
            problems.append(where | {"rule": "S1", "problem": f"1 to {MAX_LENGTH} characters"})
        if sentence.get("class") not in CLASSES:
            problems.append(where | {"rule": "S1", "problem": f"the class is one of {CLASSES}"})
        cites = sentence.get("cites")
        if not isinstance(cites, list) or not cites:
            problems.append(where | {"rule": "S2", "problem": "a sentence cites a proposition"})
            continue
        unknown = [c for c in cites if c not in allowed]
        if unknown:
            problems.append(where | {"rule": "S2", "problem": f"no verified proposition {unknown}"})
            continue
        merged = Allowed()
        for cite in cites:
            merged.merge(allowed[cite])
        for token in tokens(text):
            problem = check_token(token, merged)
            if problem is not None:
                problems.append(where | {"rule": "S3", "token": token, "problem": problem})
    return problems
