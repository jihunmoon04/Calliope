"""What a remark proves and the part it plays (AG8-D §3, §4, §6.2): `board_remarks_ko_v1`.

A board item and a consequence claim get `proves`, a Korean statement from fixed templates that
names whose piece is meant and who gains or loses; every remark gets a `part`. The texts say what
the propositions hold and nothing beyond.
"""

from __future__ import annotations

import chess

from calliope.facts import POINTS_V1_BY_TYPE

REMARKS_VERSION = "board_remarks_ko_v1"
PROVES_CAP = 240
COLOR = {"white": "백", "black": "흑"}
PIECE = {
    "pawn": "폰",
    "knight": "나이트",
    "bishop": "비숍",
    "rook": "룩",
    "queen": "퀸",
    "king": "킹",
}
# the order of pieces by points_v1, the fact engine's one value table; the king above all
VALUE = {t.value: v for t, v in POINTS_V1_BY_TYPE.items()} | {"king": 100}
PARTS = ("reason", "consequence", "comparison", "grade", "line", "other")
TEMPLATE_PARTS = {
    "reason": (
        "fork_v2", "pin_v2", "skewer_v2", "discovery_v2", "removed_defender_v2",
        "left_en_prise_v2", "newly_exposed_v1", "prevents_v1", "rescue_v1", "only_move_v1",
        "best_stops_reply_v1", "capture_holds_v1", "sacrifice_offer_v1",
        "sacrifice_compensated_v1", "sacrifice_sound_v1", "piece_offer_v1", "forcing_v1",
        "check_answer_v1",
    ),
    "consequence": (
        "material_gain_v3", "material_loss_v2", "mate_found_v1", "mate_allowed_v1",
        "mate_delivered_v1", "mate_in_one_allowed_v1", "mate_missed_v1", "checks_draw_v1",
        "checks_draw_missed_v1",
    ),
    "comparison": ("better_alternative_v1", "better_move_v1", "missed_gain_v1"),
}  # fmt: skip
PART_OF_TEMPLATE = {t: part for part, templates in TEMPLATE_PARTS.items() for t in templates}
MATERIAL = ("material_gain_v3", "material_loss_v2")
POSITION_KINDS = ("attack", "defence", "exposed", "pin", "check", "legal_moves", "pattern")


def template_part(template: str) -> str:
    """§4: a claim's part by its template; a template not in the table is `other`."""

    return PART_OF_TEMPLATE.get(template, "other")


def other(color: str) -> str:
    return "black" if color == "white" else "white"


def piece(color: str, kind: str, square: str) -> str:
    """`백 비숍(c4)`."""

    return f"{COLOR[color]} {PIECE[kind]}({square})"


def numbered(fen: str, moves: list[str], index: int) -> str:
    """The SAN of `moves[index]` from `fen`, numbered (`14.cxb4`, `9...b5`)."""

    board = chess.Board(fen)
    for uci in moves[:index]:
        board.push_uci(uci)
    move = chess.Move.from_uci(moves[index])
    dots = "." if board.turn == chess.WHITE else "..."
    return f"{board.fullmove_number}{dots}{board.san(move)}"


def capped(text: str) -> str:
    return text if len(text) <= PROVES_CAP else text[: PROVES_CAP - 1] + "…"


# -- board items (§3) ------------------------------------------------------------------------


def bracket(kind: str, mover: str) -> str:
    m, o = COLOR[mover], COLOR[other(mover)]
    return {
        "threat": f"[{m}(둔 쪽)의 위협 — {o}의 기물이 걸린 것이고 {m}이 잃는 것이 아니다]",
        "weakness": f"[{m}(둔 쪽)의 약점 — {m}의 기물이 위험하다]",
        "lost_defence": f"[{m}(둔 쪽)의 수비 상실]",
        "same_reply": "[같은 수순 비교]",
    }[kind]


def change_proves(kind: str, mover: str, move: str, proposition: dict, names: dict) -> str:
    """One `threat` or `weakness` proposition after `move`; `names` maps squares to pieces."""

    p, head = proposition, f"{bracket(kind, mover)} {move} 뒤"
    k = p["kind"]
    if k == "check":
        checked = COLOR[other(mover)]
        return capped(f"{head} {checked} 킹이 체크를 받는다 ({', '.join(p['checkers'])}에서)")
    if k == "pattern":
        targets = ", ".join(names[t] for t in p["participants"]["targets"])
        return capped(
            f"{head} {names[p['participants']['actor']]}이 {targets}을 동시에 공격한다 "
            "(수 전에는 없던 이중 공격; 배치일 뿐 통하는 전술인지는 따로 확인)"
        )
    if k == "attack":
        return capped(
            f"{head} {names[p['attacker']]}이 {names[p['target']]}을 공격한다 (수 전에는 아니었다)"
        )
    if k == "exposed":
        return capped(
            f"{head} {names[p['piece']]}은 교환으로 잃을 수 있다 (정적 교환으로 잡는 "
            f"쪽이 {p['gain']}점 이득; 수 전에는 아니었다)"
        )
    if k == "pin":
        return capped(
            f"{head} {names[p['pinned']]}이 {names[p['pinner']]}에게 킹 쪽으로 핀되어, 킹을 "
            "공격에 노출하는 이동이 제한된다 (수 전에는 아니었다)"
        )
    raise ValueError(f"no template for {k}")


def lost_defence_proves(mover: str, move: str, defended: str, guard: str, hitter: str,
                        defenders: int, attackers: int) -> str:  # fmt: skip
    o = COLOR[other(mover)]
    return capped(
        f"{bracket('lost_defence', mover)} {move} 전에는 {guard}이 {defended}을 지켰다. "
        f"수 뒤에는 그 수비가 없고, {hitter}이 {defended}을 공격한다 (수 뒤 "
        f"{defended}을 지키는 기물 {defenders}개, 공격하는 {o} 기물 {attackers}개)"
    )


def same_reply_proves(move: str, same: list[str], best: str, top: str, top_score: str,
                      played_score: str) -> str:  # fmt: skip
    return capped(
        f"{bracket('same_reply', 'white')} 둔 수 {move} 뒤 엔진 라인의 {' '.join(same)}를 "
        f"최선수 {best} 뒤에 두면, 엔진의 최선은 {top}, 평가 {top_score}(백 기준). 둔 수의 "
        f"평가는 {played_score}. 상대의 수는 같고, 둔 쪽의 수는 엔진이 그 자리에서도 같은 "
        "수를 고를 때만 이어 두었다"
    )


# -- consequence claims (§4) -----------------------------------------------------------------


def _line(scope: dict) -> tuple[str, list[str]] | None:
    at = scope.get("at") or {}
    if at.get("kind") != "line" or not at.get("fen"):
        return None
    return at["fen"], [m["uci"] for m in at.get("moves", ())]


def _only(scope: dict) -> str:
    return "이 라인에서만, " if scope.get("quantifier") == "specific_line" else ""


def claim_proves(claim: dict, mover: str) -> str | None:
    """The `proves` of a material or mate claim from its findings; None for the other claims or
    a claim whose findings do not name what it needs."""

    template = claim.get("template")
    scopes = claim.get("effective_scopes") or ()
    scope = scopes[0] if scopes else {}
    if template in MATERIAL:
        found = next((f for f in claim.get("findings", ()) if f.get("type") == "MaterialFinding"),
                     None)  # fmt: skip
        event = (found or {}).get("event") or {}
        victim, capturer = event.get("victim") or {}, event.get("capturer") or {}
        line = _line(scope)
        if not (found and victim.get("square") and capturer.get("square") and line):
            return None
        fen, moves = line
        ply = event.get("ply")
        if not isinstance(ply, int) or not 1 <= ply <= len(moves):
            return None
        side = victim["color"]
        what = "손실" if side == mover else "이득"  # the mover's piece taken, or the other's
        mark = f"[{COLOR[mover]}(둔 쪽)의 {what}]"
        points = (found.get("amount") or {}).get("points")
        net = (
            f"라인 전체에서 {COLOR[mover]}의 순{'손실' if side == mover else '이득'} {points}점 이상"
            if isinstance(points, int)
            else ""
        )
        text = (f"{mark} 엔진 라인에서 {numbered(fen, moves, ply - 1)}로 "
                f"{piece(capturer['color'], capturer['piece'], capturer['square'])}이 "
                f"{piece(victim['color'], victim['piece'], victim['square'])}을 잡는다 "
                f"({_only(scope)}{net})")  # fmt: skip
        checks = [c for c in claim.get("checks", ()) if c.get("kind") == "attributed"]
        if checks and not all(c.get("passed") for c in checks):
            text += " (이 수의 성과가 아니라 라인의 사실)"
        return capped(text)
    if template and template.startswith("mate_"):
        found = next((f for f in claim.get("findings", ()) if f.get("type") == "MateFinding"),
                     None)  # fmt: skip
        mating = (found or {}).get("mating_move") or {}
        if not (found and mating.get("fen") and mating.get("uci")):
            return None
        board = chess.Board(mating["fen"])
        side = "white" if board.turn == chess.WHITE else "black"
        dots = "." if board.turn == chess.WHITE else "..."
        last = f"{board.fullmove_number}{dots}{board.san(chess.Move.from_uci(mating['uci']))}"
        whose = "(둔 쪽)" if side == mover else ""
        count = found.get("moves")
        within = f"{count}수 만에 " if isinstance(count, int) and count > 0 else ""
        only = " (이 라인에서만)" if scope.get("quantifier") == "specific_line" else ""
        return capped(
            f"[{COLOR[side]}{whose}의 메이트] 엔진 라인에서 {COLOR[side]}이 {within}메이트한다 "
            f"— 마지막 수 {last}{only}"
        )
    return None


# -- the part of a verified proposition (§6.2) ------------------------------------------------


def proposition_part(record: dict) -> str:
    """The part of a verified proposition stated on its own (not as a whole board item)."""

    kind = record["kind"]
    if kind == "judgement":
        return "grade"
    if kind == "claim":
        return template_part(record["template"])
    if kind == "material":
        return "consequence"
    if kind in ("engine_score", "engine_line"):
        return "line"
    if kind == "definition":
        return "other"
    if kind == "explored_line" and record.get("by") == "calliope":
        return "line"  # a same reply's line stated without its scores (§6.2)
    return "reason"  # a position kind, an after_reply, the agent's own explored line


# -- en passant ------------------------------------------------------------------------------


def en_passant(fen: str, lines: dict[str, list[str]]) -> list[dict]:
    """Each en passant capture in the digest's lines (UCI from `fen`), said in Korean: its SAN
    names the empty square it goes to, not the pawn it takes."""

    out = []
    for name, moves in lines.items():
        try:
            board = chess.Board(fen)
        except ValueError:
            return []  # not a position (a record made by hand)
        for index, uci in enumerate(moves):
            try:
                move = chess.Move.from_uci(uci)
            except ValueError:
                break
            if move not in board.legal_moves:
                break
            if board.is_en_passant(move):
                side = "white" if board.turn == chess.WHITE else "black"
                taken = chess.square_name(move.to_square + (-8 if board.turn == chess.WHITE else 8))
                san = numbered(fen, moves, index)
                out.append({"line": name, "move": san, "text": (
                    f"{san}는 앙파상입니다: {COLOR[side]} 폰이 {uci[:2]}에서 {uci[2:4]}로 가며 "
                    f"{piece(other(side), 'pawn', taken)}을 잡습니다. {uci[2:4]} 칸은 비어 "
                    "있었습니다.")})  # fmt: skip
            board.push(move)
    return out
