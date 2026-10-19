"""The sentence check (AG-D §5.3, S1–S6): sentences are checked as sources only.

Each sentence cites propositions; every move, score, mate, square and number written as such in
it must come from them (S3). The wording is not checked: an accepted commentary is
`SOURCE_VERIFIED` (`commentary_check_v1`), and an `interpretation` sentence is stored and shown as
the agent's reading.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

import chess

MAX_SENTENCES = 12
MAX_LENGTH = 300
CLASSES = ("sourced", "interpretation")

_RUN = re.compile(r"[A-Za-z0-9.+\-−#=]+")
_NUMBER = re.compile(r"\d+\.+")  # a move number: one or three dots read, other counts refused
_DIGITS = re.compile(r"\d+")
_DOTS = re.compile(r"\.+")
_SAN = r"(O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8](=[QRBN])?|[a-h][1-8]=[QRBN]|[a-h][1-8])[+#]?"
# A number with one or three dots, or three dots alone (Black's move, AG7-D §5); one dot alone is none
_MOVE = re.compile(rf"(?:(\d+)(\.\.\.|\.) ?|(\.\.\.))?({_SAN})")
_SCORE = re.compile(r"[+\-−]?\d+\.\d{1,2}")
_MATE = re.compile(r"(?:M|#)(\d+)")
_SQUARE = re.compile(r"[a-h][1-8]")
_INTEGER = re.compile(r"[+\-−]?\d+")
_PAWN_PUSH = re.compile(r"[a-h][1-8][+#]?")
_CASTLING = re.compile(r"O-O(-O)?[+#]?")
_MINUS = "\u2212\ufe63\uff0d"  # minus signs; every dash (category Pd) is read as one too
_PREFIX = re.compile(r"[+\-]+|M|#")  # a sign or a mate mark standing apart from its number
_NUMERIC = re.compile(r"[+\-]*(\d|[M#]\d)")  # a run that writes a number, a score or a mate
_IGNORABLE = (  # Unicode's default-ignorable code points: shown as nothing (AM4)
    (0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5),
    (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F), (0x3164, 0x3164),
    (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF),
)  # fmt: skip
_HANGUL = ((0x1100, 0x11FF), (0x3130, 0x318F), (0xA960, 0xA97F), (0xAC00, 0xD7AF), (0xD7B0, 0xD7FF))
# CV4-D §3: kana and CJK ideographs, refused in a ko sentence (S8); read after NFKC
_KANA_CJK = (
    (0x3040, 0x309F), (0x30A0, 0x30FF), (0x31F0, 0x31FF), (0x1AFF0, 0x1B16F),  # kana
    (0x3005, 0x3007), (0x2E80, 0x2FDF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF),
    (0x20000, 0x323AF),  # CJK ideographs
)  # fmt: skip
_RUN_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.+-#=")


def _within(ch: str, ranges) -> bool:
    return any(lo <= ord(ch) <= hi for lo, hi in ranges)


def _invisible(ch: str) -> bool:
    category = unicodedata.category(ch)
    return _within(ch, _IGNORABLE) or category == "Cf" or (category == "Cc" and not ch.isspace())


def normalized(text: str) -> str:
    """AG-D AM2, AM4: NFKC (full-width and styled letters and digits become ASCII); characters
    shown as nothing (U+200B, U+3164, ...) removed and NFKC again; every dash and minus sign
    becomes `-` and a blank (U+2800) a space, so no sign, digit or separator hides."""

    text = unicodedata.normalize("NFKC", text)
    text = unicodedata.normalize("NFKC", "".join(ch for ch in text if not _invisible(ch)))
    return "".join(
        "-" if ch in _MINUS or unicodedata.category(ch) == "Pd" else " " if ch == "\u2800" else ch
        for ch in text
    )


def foreign_letters(text: str) -> str:
    """AM4: letters and marks other than ASCII and Hangul that touch a token (`Nxе4` with a
    Cyrillic е, a combining mark on a digit): the token's reading is not checked."""

    text = normalized(text)
    padded = f" {text} "
    return "".join(
        ch
        for before, ch, after in zip(padded[:-2], text, padded[2:], strict=True)
        if not (ch.isascii() or _within(ch, _HANGUL) or unicodedata.category(ch)[0] not in "LM")
        and (before in _RUN_CHARS or after in _RUN_CHARS)
    )


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
        board = chess.Board(fen)
        self.integers.add(board.fullmove_number)
        move = chess.Move.from_uci(uci)
        if board.is_en_passant(
            move
        ):  # the square of the pawn it takes, which its SAN does not name
            self.squares.add(chess.square_name(move.to_square + (-8 if board.turn else 8)))

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
    """S3's tokens: runs of `[A-Za-z0-9.+\\-−#=]`. Across a gap with no letter or digit (spaces,
    punctuation; AM3, AM4): a move number is joined with the next token (`17.  Rxe3`, `17 . Rxe3`
    read as `17. Rxe3`), and a sign or a mate mark with the number after it (`- 1.00`, `−(2)`,
    `M 3` read as `-1.00`, `-2`, `M3`). A sign or mark apart from the number after it (`- 약 1.00`,
    `- (+1.00)`, `Rxe3 — 백은 2점`) is a token of its own, a violation (AM5); one before a word or
    a move (`e4 - e5`) is none. A trailing `.` is dropped unless the token is a bare move number."""

    text = normalized(text)
    runs = [(m.group(), m.start(), m.end()) for m in _RUN.finditer(text)]

    def gap(i: int) -> str | None:  # what separates run i from the next, None at the end
        return text[runs[i][2] : runs[i + 1][1]] if i + 1 < len(runs) else None

    def spaced(i: int) -> bool:  # no letter or digit between run i and the next
        between = gap(i)
        return between is not None and not any(unicodedata.category(c)[0] in "LN" for c in between)

    out, i = [], 0
    while i < len(runs):
        token = runs[i][0]
        after = runs[i + 1][0] if i + 1 < len(runs) else ""
        if _PREFIX.fullmatch(token):
            if after[:1].isdigit() and spaced(i):
                token += after  # `- 1.00`, `M 3`: the sign is the number's
                i += 1
            else:  # a sign or mark apart: no token before a word or a move (`e4 - e5`); before
                if _NUMERIC.match(after):  # a number its reading is not decided (B5), a violation
                    out.append(token)
                i += 1
                continue
        if _DIGITS.fullmatch(token) and spaced(i) and _DOTS.fullmatch(runs[i + 1][0]):
            token += runs[i + 1][0]  # `17 . Rxe3`: the dots are the number's
            i += 1
        if _NUMBER.fullmatch(token) and spaced(i):
            token = f"{token} {runs[i + 1][0]}"
            i += 1
        token = token.rstrip(".")  # a lone move number ("17.", "3.") is read as its integer
        if token:  # a lone full stop is no token
            out.append(token)
        i += 1
    return out


def _signed(text: str) -> int:
    return int(text.replace("−", "-"))


def _marks_hold(board: chess.Board, move: chess.Move, san: str) -> bool:
    """The capture, check and mate marks a SAN token writes must hold (review B2); a check or
    mate mark may be left out, a capture mark may not (SAN)."""

    if ("x" in san) != board.is_capture(move):
        return False
    after = board.copy(stack=False)
    after.push(move)
    if san.endswith("#"):
        return after.is_checkmate()
    if san.endswith("+"):
        return after.is_check() and not after.is_checkmate()
    return True


def _move_ok(number: str | None, dots: str | None, san: str, allowed: Allowed) -> bool:
    for uci, fen in allowed.moves:
        board = chess.Board(fen)
        try:
            move = board.parse_san(san)
        except ValueError:
            continue
        if move.uci() != uci or not _marks_hold(board, move, san):
            continue
        if dots is not None and (dots == "...") != (board.turn == chess.BLACK):
            continue  # `...` exactly for Black, with or without a number (AG7-D §5)
        if number is not None and int(number) != board.fullmove_number:
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

    if _PREFIX.fullmatch(token):  # AM4, AM5: a sign or mark apart from its number (`tokens`)
        return f"the sign {token!r} stands apart from the number after it"
    if not (re.search(r"\d", token) or _CASTLING.fullmatch(token.removeprefix("..."))):
        return None
    move = _MOVE.fullmatch(token)
    if move:
        number, dots, san = move[1], move[2] or move[3], move[4]
        # a bare pawn push is a square only with neither a number nor dots (AG7-D §5)
        if not (number is None and dots is None and _PAWN_PUSH.fullmatch(san)):
            if _move_ok(number, dots, san, allowed):
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


def _hangul(text: str) -> bool:
    return any("\uac00" <= ch <= "\ud7a3" for ch in text)


def _allows_any(allowed: Allowed) -> bool:
    return bool(allowed.moves or allowed.squares or allowed.integers or allowed.scores
                or allowed.mates)  # fmt: skip


def _writes(text: str, allowed: Allowed) -> bool:
    """A token of the text that `allowed` alone accepts (S7b): a move, square, score, mate or
    number, not a word."""

    return any(
        (any(c.isdigit() for c in t) or _CASTLING.fullmatch(t.removeprefix("...")))
        and check_token(t, allowed) is None
        for t in tokens(text)
    )


def check_states(sentence: dict, where: dict, allowed: dict[str, Allowed],
                 kinds: dict[str, str]) -> list[dict]:  # fmt: skip
    """S7 (AG8-D §6.1): `states` lists cited ids; a stated proposition other than a judgement
    that allows a token has one of its tokens written."""

    states = sentence.get("states")
    if states is None:
        return []
    cites = sentence.get("cites") or []
    if not isinstance(states, list) or any(
        not isinstance(s, str) or s not in cites for s in states
    ):
        return [where | {"rule": "S7", "problem": "`states` lists ids the sentence cites"}]
    problems = []
    for pid in states:
        if pid not in allowed or kinds.get(pid) == "judgement" or not _allows_any(allowed[pid]):
            continue
        if not _writes(sentence.get("text") or "", allowed[pid]):
            problems.append(where | {"rule": "S7", "proposition": pid, "problem": f"the sentence states "
                                     f"{pid} but writes none of its moves, squares, scores, mates "
                                     "or numbers"})  # fmt: skip
    return problems


def check_sentences(language: str, sentences, allowed: dict[str, Allowed],
                    kinds: dict[str, str] | None = None,
                    proved: dict[str, Allowed] | None = None) -> list[dict]:  # fmt: skip
    """S1–S4, S7, S8 (CV4-D §3) over the submission's sentences; `allowed` maps every verified
    proposition's id, `kinds` its kind (AG8-D §6); `proved`, what a cited board item's `proves`
    writes (MS-D §8.3), is allowed by S3 and never stands for a stated proposition (S7)."""

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
        unknown = [c for c in cites if not isinstance(c, str) or c not in allowed]
        if unknown:
            problems.append(where | {"rule": "S2", "problem": f"no verified proposition {unknown}"})
            continue
        merged = Allowed()
        for cite in cites:
            merged.merge(allowed[cite])
            if proved and cite in proved:
                merged.merge(proved[cite])
        foreign = [ch for ch in normalized(text) if unicodedata.category(ch) == "Nd"
                   and not ch.isascii()]  # fmt: skip
        if foreign:  # digits of other scripts: no reading of them is checked (AM2)
            problems.append(where | {"rule": "S3", "token": "".join(foreign),
                                     "problem": "digits other than 0-9"})  # fmt: skip
        if touching := foreign_letters(text):
            problems.append(where | {"rule": "S3", "token": touching,
                                     "problem": "a letter or mark other than ASCII and Hangul "
                                                "touches a move or number"})  # fmt: skip
        for token in tokens(text):
            problem = check_token(token, merged)
            if problem is not None:
                problems.append(where | {"rule": "S3", "token": token, "problem": problem})
        if language == "ko" and text.strip() and not _hangul(text):  # S8 (AG8-D §6.3)
            problems.append(where | {"rule": "S8", "problem": "a sentence of a ko commentary "
                                     "is written in Korean"})  # fmt: skip
        kana = "".join(ch for ch in normalized(text) if _within(ch, _KANA_CJK))
        if language == "ko" and kana:  # S8 (CV4-D §3)
            problems.append(where | {"rule": "S8", "token": kana, "problem": "a sentence of a ko "
                                     "commentary is written in Korean, without kana or CJK "
                                     "ideographs"})  # fmt: skip
        problems += check_states(sentence, where, allowed, kinds or {})
    return problems
