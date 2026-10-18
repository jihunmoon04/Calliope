"""What a remark proves and the part it plays (AG8-D §3, §4, §6.2): `board_remarks_ko_v2`.

A board item and a consequence claim get `proves`, a Korean statement from fixed templates that
names whose piece is meant and who gains or loses; every remark gets a `part`. The texts say what
the propositions hold and nothing beyond.
"""

from __future__ import annotations

import re

import chess

from calliope.facts import POINTS_V1_BY_TYPE

REMARKS_VERSION = "board_remarks_ko_v2"  # MS-D §8.2: every template, with its tokens
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
        "sacrifice_compensated_v2", "sacrifice_sound_v1", "piece_offer_v1", "forcing_v1",
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
        "threat": f"[{m}(둔 쪽)의 위협: {o}의 기물이 걸린 것이고 {m}이 잃는 것이 아니다]",
        "weakness": f"[{m}(둔 쪽)의 약점: {m}의 기물이 위험하다]",
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


CONSEQUENCE_KO = {
    "material_loss_v2": "물질 손실", "material_gain_v3": "물질 이득", "mate_found_v1": "메이트",
    "mate_allowed_v1": "메이트 허용", "mate_delivered_v1": "메이트", "mate_missed_v1": "놓친 메이트",
    "mate_in_one_allowed_v1": "한 수 메이트 허용",
}  # fmt: skip


def link_remark(leads: dict) -> str:
    """MS-D §6 item 2: the link a relation claim adds to its item — the consequence it explains or
    comes with, and for a mechanism whether it won material; empty without a link."""

    kind = leads.get("link")
    if kind is None:
        return ""
    consequence = CONSEQUENCE_KO.get(leads.get("to_template") or "", "결과")
    if kind in ("explains", "causes"):
        text = f", 이 변화가 엔진 라인의 {consequence}을(를) 설명한다"
    else:
        text = f", 엔진 라인의 {consequence}과(와) 함께 나온다 (원인으로 확인되지는 않음)"
    if leads.get("did") == "won":
        text += " (이 전술로 물질을 얻었다)"
    elif leads.get("did") == "configuration":
        text += " (배치일 뿐 그것으로 물질을 얻은 것은 아니다)"
    return text


def held_proves(color: str, move: str, name: str, gain: int) -> str:
    """MS-D §6 item 3: a piece exposed before the move and after it."""

    return capped(
        f"[{COLOR[color]} 기물이 계속 잡힐 수 있음] {move} 전에도 뒤에도 {name}은 교환으로 잃을 "
        f"수 있다 (수 뒤 정적 교환으로 잡는 쪽이 {gain}점 이득)"
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


class Tokens:
    """What a `proves` writes (MS-D §8.3): its moves with their positions, its squares, its
    numbers — built with the text, so what a citation allows is what was shown."""

    def __init__(self) -> None:
        self.moves: list[tuple[str, str]] = []  # (uci, fen)
        self.squares: set[str] = set()
        self.integers: set[int] = set()

    def move(self, fen: str, moves: list[str], index: int) -> str:
        """`moves[index]` from `fen`, numbered (`14.cxb4`)."""

        board = chess.Board(fen)
        for uci in moves[:index]:
            board.push_uci(uci)
        self.moves.append((moves[index], board.fen()))
        return numbered(fen, moves, index)

    def piece(self, color: str, kind: str, square: str) -> str:
        self.squares.add(square)
        return piece(color, kind, square)

    def n(self, value: int) -> str:
        self.integers.add(value)
        return str(value)


def claim_proves(claim: dict, mover: str) -> str | None:
    """The `proves` of a claim from its findings (AG8-D §4, MS-D §8.2); None for a claim whose
    findings do not name what its row needs."""

    remark = claim_remark(claim, mover)
    return None if remark is None else remark[0]


def claim_remark(claim: dict, mover: str) -> tuple[str, Tokens] | None:
    """(`proves`, the tokens it writes) — MS-D §8.2, §8.3."""

    template = claim.get("template") or ""
    scopes = claim.get("effective_scopes") or ()
    scope = scopes[0] if scopes else {}
    tokens = Tokens()
    build = _REMARKS.get(template) or (_mate if template.startswith("mate_") else None)
    if build is None:
        return None
    try:
        text = build(claim, mover, scope, tokens)
    except (KeyError, TypeError, ValueError, IndexError):
        return None  # findings that do not name what the row needs (MS-D §8.2)
    if not text or len(text) > PROVES_CAP:
        # a `proves` too long to show whole is none (MS-b re-review N3): a cut text would allow
        # tokens it does not show; the claim keeps its findings instead
        return None
    return text, tokens


def _finding(claim: dict, kind: str) -> dict | None:
    return next((f for f in claim.get("findings", ()) if f.get("type") == kind), None)


def _material(claim: dict, mover: str, scope: dict, t: Tokens) -> str | None:
    found = _finding(claim, "MaterialFinding")
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
        f"라인 전체에서 {COLOR[mover]}의 순{'손실' if side == mover else '이득'} {t.n(points)}점 이상"
        if isinstance(points, int)
        else ""
    )
    text = (f"{mark} 엔진 라인에서 {t.move(fen, moves, ply - 1)}로 "
            f"{t.piece(capturer['color'], capturer['piece'], capturer['square'])}이 "
            f"{t.piece(victim['color'], victim['piece'], victim['square'])}을 잡는다 "
            f"({_only(scope)}{net})")  # fmt: skip
    checks = [c for c in claim.get("checks", ()) if c.get("kind") == "attributed"]
    if checks and not all(c.get("passed") for c in checks):
        text += " (이 수의 성과가 아니라 라인의 사실)"
    return text


def _mate(claim: dict, mover: str, scope: dict, t: Tokens) -> str | None:
    found = _finding(claim, "MateFinding")
    if found and claim.get("template") == "mate_in_one_allowed_v1" and not found.get("mating_move"):
        # exact, with no engine line (R2-D §3.3a): the reply that mates is not named
        return f"[메이트 허용] 둔 수 뒤 {COLOR[other(mover)]}은 한 수 만에 메이트할 수 있다"
    mating = (found or {}).get("mating_move") or {}
    if not (found and mating.get("fen") and mating.get("uci")):
        return None
    board = chess.Board(mating["fen"])
    side = "white" if board.turn == chess.WHITE else "black"
    last = t.move(mating["fen"], [mating["uci"]], 0)
    whose = "(둔 쪽)" if side == mover else ""
    count = found.get("moves")
    within = f"{t.n(count)}수 만에 " if isinstance(count, int) and count > 0 else ""
    only = ", 이 라인에서만" if scope.get("quantifier") == "specific_line" else ""
    return (f"[{COLOR[side]}{whose}의 메이트] 엔진 라인에서 {COLOR[side]}이 {within}메이트한다 "
            f"(마지막 수 {last}{only})")  # fmt: skip


def _pct(value: int) -> int:
    """Expected points (1/2000) as a whole percent, half up."""

    return (value + 10) // 20


def _san(t: Tokens, move: dict) -> str:
    return t.move(move["fen"], [move["uci"]], 0)


def _outcome(o: dict, t: Tokens) -> str:
    kind = o.get("kind")
    if kind == "mate":
        return f"{COLOR[o['winner']]}의 메이트"
    if kind == "stable":
        delta = o["delta"]
        if delta == 0:
            return "물질 변화 없음"
        return f"물질 {t.n(abs(delta))}점 {'이득' if delta > 0 else '손실'}"
    return {"drawn": "무승부", "open": "물질 미정"}[kind]


def _better_move(c, mover, scope, t):
    f = _finding(c, "ComparisonFinding")
    return (f"[비교] 둔 수의 엔진 라인은 {_outcome(f['played'], t)}, {_san(t, f['best_move'])}의 "
            f"라인은 {_outcome(f['best'], t)}")  # fmt: skip


def _missed_gain(c, mover, scope, t):
    f = _finding(c, "MissedGainFinding")
    if c.get("template") == "better_alternative_v1":
        return f"[비교] 엔진의 {t.n(1)}순위는 {_san(t, f['best'])}였다"
    return f"[비교] {_san(t, f['best'])}가 둔 수보다 기대 점수로 {t.n(_pct(f['loss']))}퍼센트포인트 앞선다"


def _best_stops_reply(c, mover, scope, t):
    f = _finding(c, "ReplyFinding")
    best, reply = _san(t, f["best"]), _san(t, f["reply"])
    p, square = f["piece"], f["square"]["square"]
    t.squares.add(square)
    name = t.piece(p["color"], p["piece"], p["square"])
    return {
        "rescues": f"[비교] {best}는 {reply}가 잡을 {name}을 옮긴다 ({square} 칸의 정적 교환 기준)",
        "defends": f"[비교] {best} 뒤에는 {reply}로 {square}를 잡아도 정적 교환상 이득이 없다",
        "covers": f"[비교] {best} 뒤 {reply}를 두면 {square}의 {name}을 정적 교환상 잃는다",
    }[f["kind"]]


def _forcing(c, mover, scope, t):
    f = _finding(c, "ForcingFinding")
    if f["check"]:
        return f"[강제] 둔 수는 체크다 (상대의 응수 {t.n(f['replies'])}개)"
    return f"[강제] 둔 수 뒤 상대의 응수는 {t.n(f['replies'])}개다"


def _check_answer(c, mover, scope, t):
    f = _finding(c, "CheckAnswerFinding")
    checkers = ", ".join(t.piece(p["color"], p["piece"], p["square"]) for p in f["checkers"])
    how = {"block": "가로막는", "capture": "체크한 기물을 잡는", "king": "킹으로 피하는"}[f["kind"]]
    return f"[체크 대응] 둔 수는 {checkers}의 체크를 {how} 수다 (합법 수 {t.n(f['legal_moves'])}개)"


def _only_move(c, mover, scope, t):
    f = _finding(c, "AlternativeFinding")
    return (f"[유일한 수] 엔진의 {t.n(2)}순위 수는 기대 점수로 {t.n(_pct(f['loss']))}퍼센트포인트 "
            "나쁘다")  # fmt: skip


def _prevents(c, mover, scope, t):
    f = _finding(c, "PreventsFinding")
    what = {"mate": "모두 메이트당하고", "material": "모두 물질을 잃고",
            "mixed": "메이트당하거나 물질을 잃고"}[f["kind"]]  # fmt: skip
    return (f"[막음] 엔진이 보고한 다른 {t.n(f['alternatives'])}개 라인은 {what}, 둔 수의 라인은 "
            "그렇지 않다")  # fmt: skip


def _rescue(c, mover, scope, t):
    f = _finding(c, "RescueFinding")
    p = f["piece"]
    return (f"[구출] 둔 수로 {t.piece(p['color'], p['piece'], p['square'])}은 더 이상 잡히는 "
            f"자리에 있지 않다 (수 전에는 {t.n(f['exposure_before'])}점 노출)")  # fmt: skip


def _capture_holds(c, mover, scope, t):
    f = _finding(c, "CaptureHoldsFinding")
    return (f"[받아도 됨] 내준 기물을 상대가 잡아도 엔진의 최선 응수 뒤 {COLOR[mover]}(둔 쪽)의 "
            f"기대 점수는 {t.n(_pct(f['expected']))}퍼센트다 (절반 이상)")  # fmt: skip


def _piece_offer(c, mover, scope, t):
    f = _finding(c, "PieceOfferFinding")
    p = f["piece"]
    taking = " 잡으며" if f.get("capture") else ""
    by = f", 상대는 {_san(t, f['taken_by'])}로 잡을 수 있다" if f.get("taken_by") else ""
    return (f"[{COLOR[mover]}(둔 쪽)의 제공] 둔 수로{taking} {t.piece(p['color'], p['piece'], p['square'])}"
            f"을 내준다 ({t.n(f['offer'])}점){by} (옳은지는 따로)")  # fmt: skip


def _sacrifice_offer(c, mover, scope, t):
    f = _finding(c, "OfferFinding")
    return f"[{COLOR[mover]}(둔 쪽)의 희생] 엔진 라인에서 {t.n(f['amount']['points'])}점을 내준다"


def _compensation(c, mover, scope, t):
    f = _finding(c, "CompensationFinding")
    kind = f["kind"]
    if c.get("template") == "sacrifice_sound_v1":
        return (f"[희생의 평가] 엔진은 희생 뒤를 {COLOR[mover]}(둔 쪽)에 손해로 보지 않는다 (평가일 "
                "뿐 대가의 증명은 아니다)")  # fmt: skip
    if kind == "material_return":
        return "[희생의 대가] 물질을 지키는 다른 수들보다 더 많이 되찾는다"
    text = "[희생의 대가] 엔진 라인에서 메이트로 돌려받는다"
    return text + (", 다른 라인과는 엔진 평가로 비교했다" if kind == "mate_over_scores" else "")


def _link(c) -> str:
    kinds = {r.get("kind") for r in c.get("relations", ())}
    if kinds & {"explains", "causes"}:
        return ", 엔진 라인의 결과를 설명한다"
    if "associated_with" in kinds:
        return ", 엔진 라인의 결과와 함께 나온다 (원인으로 확인되지는 않음)"
    return ""


def _defence_claim(c, mover, scope, t):
    f = _finding(c, "DefenceFinding")
    d, x = f["defender"], f["defended"]
    why = {"defender_moved": "지키던 기물이 움직였다", "line_blocked": "둔 수가 선을 막았다",
           "defended_moved": "지켜지던 기물이 움직였다",
           "defender_captured": "지키던 기물이 잡혔다"}.get(f.get("reason"), "")  # fmt: skip
    return (f"[{COLOR[x['color']]} 기물의 수비 상실] 둔 수 뒤 {t.piece(d['color'], d['piece'], d['square'])}"
            f"은 {t.piece(x['color'], x['piece'], x['square'])}을 더 이상 지키지 않는다 ({why})"
            f"{_link(c)}")  # fmt: skip


def _hanging_claim(c, mover, scope, t):
    f = _finding(c, "HangingFinding")
    p = f["piece"]
    name = t.piece(p["color"], p["piece"], p["square"])
    by = ", ".join(t.piece(a["color"], a["piece"], a["square"]) for a in f.get("attackers", ()))
    if c.get("template") == "left_en_prise_v2":
        return f"[{COLOR[p['color']]} 기물 방치] {name}은 수 전부터 {by}에게 잡힐 수 있었고 둔 수 뒤에도 그렇다{_link(c)}"
    how = {"moved_into_attack": "공격받는 자리로 갔다", "line_opened": "선이 열려 공격받게 됐다"}.get(
        f.get("kind"), "공격받게 됐다")  # fmt: skip
    return f"[{COLOR[p['color']]} 기물의 노출] 둔 수로 {name}이 {how} ({by}){_link(c)}"


def _mechanism_claim(c, mover, scope, t):
    f = _finding(c, "MechanismFinding")
    a = f["actor"]
    actor = t.piece(a["color"], a["piece"], a["square"])
    targets = [t.piece(x["color"], x["piece"], x["square"]) for x in f["targets"]]
    where = f"엔진 라인의 {_san(t, f['move'])} 뒤"
    realized = any(k.get("kind") == "realized" and k.get("passed") for k in c.get("checks", ()))
    did = " (이 전술로 물질을 얻었다)" if realized else " (배치일 뿐 물질과 함께 나온다)"
    kind = f["kind"]
    if kind == "fork":
        body = f"{actor}이 {', '.join(targets)}을 동시에 공격한다"
    elif kind == "pin":
        body = f"{actor}이 {targets[0]}을 {targets[1]} 쪽으로 핀한다"
    elif kind == "skewer":
        body = f"{actor}이 {targets[0]}을 공격해 뒤의 {targets[1]}이 드러난다"
    else:
        body = f"{actor}의 선이 열려 {', '.join(targets)}을 공격한다"
    return f"[전술] {where} {body}{did}"


_REMARKS = {
    "material_gain_v3": _material, "material_loss_v2": _material,
    "better_move_v1": _better_move, "missed_gain_v1": _missed_gain,
    "better_alternative_v1": _missed_gain, "best_stops_reply_v1": _best_stops_reply,
    "forcing_v1": _forcing, "check_answer_v1": _check_answer, "only_move_v1": _only_move,
    "prevents_v1": _prevents, "rescue_v1": _rescue, "capture_holds_v1": _capture_holds,
    "piece_offer_v1": _piece_offer, "sacrifice_offer_v1": _sacrifice_offer,
    "sacrifice_sound_v1": _compensation, "sacrifice_compensated_v2": _compensation,
    "removed_defender_v2": _defence_claim, "newly_exposed_v1": _hanging_claim,
    "left_en_prise_v2": _hanging_claim, "fork_v2": _mechanism_claim, "pin_v2": _mechanism_claim,
    "skewer_v2": _mechanism_claim, "discovery_v2": _mechanism_claim,
}  # fmt: skip


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


_SQUARE = re.compile(r"(?<![A-Za-z0-9])([a-h][1-8])(?![A-Za-z0-9])")
_COUNT = re.compile(r"(?<![A-Za-z0-9.+\-])(\d+)(?=점|개|수)")


def board_tokens(proves: str, uci: str, fen_before: str):
    """MS-D §8.3 for a board item: what its `proves` writes — the subject's move (`{move} 뒤`),
    the squares of its pieces, its points and counts — read from the server's own text, so a
    sentence citing the item by its `b` handle may write what the item shows and no more."""

    from .sentences import Allowed

    allowed = Allowed()
    allowed.add_move(uci, fen_before)
    allowed.squares |= set(_SQUARE.findall(proves))
    allowed.integers = {int(n) for n in _COUNT.findall(proves)}  # not the move's number (review B1)
    return allowed
