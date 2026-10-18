"""Korean refusals (AG8-D §7): a `ko` submission's violations get their `problem` in Korean from
fixed templates, the English text kept as `problem_en`.

A problem that carries another component's own message (a handle's, a position's) keeps that
message inside a Korean frame: it names a value, not a rule.
"""

from __future__ import annotations

import re

_V = r"(?P<v>.+)"
TEMPLATES: tuple[tuple[str, str], ...] = (
    # the sentence check (S1–S8)
    (r"the language is ko, not (?P<v>.+)", "해설의 language는 ko입니다({v}가 아님)"),
    (r"1 to (?P<n>\d+) sentences", "해설은 1~{n}문장입니다"),
    (r"at least one sentence is sourced", "sourced 문장이 하나 이상 있어야 합니다"),
    (r"a sentence is \{text, class, cites\}", "문장은 {{text, class, cites}}입니다"),
    (r"1 to (?P<n>\d+) characters", "문장은 1~{n}자입니다"),
    (r"the class is one of .+", "class는 sourced 또는 interpretation입니다"),
    (r"a sentence cites a proposition", "문장은 명제를 하나 이상 인용합니다(cites)"),
    (r"no verified proposition (?P<v>.+)", "검증된 명제가 아닌 id를 인용했습니다: {v}"),
    (r"digits other than 0-9", "0-9가 아닌 숫자 문자가 있습니다"),
    (
        r"a letter or mark other than ASCII and Hangul touches a move or number",
        "수나 숫자에 ASCII·한글이 아닌 문자가 붙어 있습니다",
    ),
    (
        r"the sign (?P<v>.+) stands apart from the number after it",
        "부호 {v}가 뒤의 숫자와 떨어져 있습니다",
    ),
    (
        r"the move (?P<v>.+) is not a move of the cited propositions",
        "수 {v}는 인용한 명제에 없습니다",
    ),
    (
        r"the score (?P<v>.+) is not a cited engine score",
        "평가치 {v}는 인용한 엔진 평가가 아닙니다",
    ),
    (r"the mate (?P<v>.+) is not cited", "메이트 {v}는 인용한 명제에 없습니다"),
    (r"the square (?P<v>.+) is not cited", "칸 {v}는 인용한 명제에 없습니다"),
    (r"the number (?P<v>.+) is not in the cited propositions", "숫자 {v}는 인용한 명제에 없습니다"),
    (
        r"(?P<v>.+) is neither a move, a score, a mate, a square nor a cited number",
        "{v}는 수, 평가치, 메이트, 칸, 인용한 숫자 중 어느 것도 아닙니다",
    ),
    (
        r"`states` lists ids the sentence cites",
        "`states`에는 이 문장이 cites에 둔 명제의 id만 씁니다",
    ),
    (
        r"the sentence states (?P<v>\S+) but writes none of its moves, squares, scores, mates or numbers",
        "이 문장은 {v}를 말한다고 했지만(`states`) 그 명제의 수·칸·평가치·숫자를 하나도 쓰지 않았습니다",
    ),
    (r"a sentence of a ko commentary is written in Korean", "해설 문장은 한국어로 씁니다"),
    # the submission
    (r"agent is \{name, model\?\}", "agent는 {{name, model?}}입니다"),
    (r"at least one proposition", "명제가 하나 이상 있어야 합니다"),
    (
        r"at most (?P<n>\d+) propositions in one commentary, not (?P<m>\d+)",
        "한 해설의 명제는 {n}개까지입니다({m}개를 보냄)",
    ),
    (
        r"a unique id of at most (?P<n>\d+) characters is required",
        "명제마다 {n}자 이하의 고유한 id가 필요합니다",
    ),
    (
        r"a judgement proposition citing the subject's own judgement \(ply or judge_move\) is required",
        "이 수 자신의 판정(ply 또는 judge_move의 judgement)을 인용한 judgement 명제가 필요합니다",
    ),
    (
        r"the commentary would carry (?P<n>\d+) bytes on the board, over (?P<m>\d+)",
        "해설이 판에 {n}바이트를 싣게 되어 한도 {m}를 넘습니다",
    ),
    (
        r"an item is \{ply \| position and move, propositions, sentences\}",
        "items의 항목은 {{ply 또는 position과 move, propositions, sentences}}입니다",
    ),
    # a proposition's field
    (r"a proposition is an object", "명제는 객체입니다"),
    (
        r"no proposition kind (?P<v>[^:]+): write (?P<w>.+?) \(.+\)",
        "명제 종류 {v}는 없습니다: {w}로 쓰세요",
    ),
    (r"no proposition kind (?P<v>.+)", "명제 종류 {v}는 없습니다(expected 참고)"),
    (r"a list of handles", "refs는 핸들의 목록입니다"),
    (r"a handle is a string such as (?P<v>.+)", "핸들은 {v} 같은 문자열입니다"),
    (r"(?P<v>\S+) is a (?P<k>\S+), not a (?P<w>.+)", "{v}는 {k} 핸들이고 {w}가 아닙니다"),
    (r"(?P<v>.+) is not a legal move at (?P<f>.+)", "{v}는 그 국면({f})의 합법 수가 아닙니다"),
    (
        r"(?P<v>.+) is not what the source holds",
        "{v}는 출처가 담은 값이 아닙니다(expected가 출처의 값)",
    ),
    (r"(?P<v>.+) is not a square", "{v}는 칸이 아닙니다"),
    (r"(?P<v>.+) is not an integer", "{v}는 정수가 아닙니다"),
    (r"no use (?P<v>.+)", "use {v}는 없습니다(expected 참고)"),
    (r"only an INCONCLUSIVE claim is uncertain", "uncertain은 INCONCLUSIVE 클레임에만 씁니다"),
    (r"only a REFUTED claim is not the case", "not_the_case는 REFUTED 클레임에만 씁니다"),
    (r"a (?P<s>\S+) claim cannot be used as (?P<u>\S+)", "{s} 클레임은 {u}로 쓸 수 없습니다"),
    (
        r"only a consequence is a result",
        "result는 role이 consequence인 클레임에만 씁니다(expected 참고)",
    ),
    (
        r"its ATTRIBUTED check did not pass: .+",
        "ATTRIBUTED 검사를 통과하지 못했습니다: 이 수의 득실이 아니라 라인의 사실입니다(line_fact)",
    ),
    (
        r"no explains or causes relation to a supported target",
        "mechanism으로 쓸 수 있는 explains·causes 관계가 없습니다",
    ),
    (
        r"not an associated_with claim \(or it explains or causes\)",
        "associated로 쓸 수 있는 클레임이 아닙니다",
    ),
    (
        r"not a comparison claim",
        "comparison으로 쓸 수 있는 클레임이 아닙니다(role이 comparison이 아님)",
    ),
    (
        r"the claim's effective scopes, as a list \(or leave it out\)",
        "scopes는 클레임의 effective_scopes 목록입니다(생략 가능)",
    ),
    (r"not the claim's effective scopes", "클레임의 effective_scopes가 아닙니다(expected 참고)"),
    (
        r"the line's position is not on its analysis's path",
        "그 라인의 국면이 분석한 경로 위에 없습니다",
    ),
    (r"not a prefix of the line's PV", "라인 PV의 앞부분이 아닙니다(expected가 PV)"),
    (r"a list of moves", "수의 목록입니다"),
    (r"from and to are plies 0 to (?P<n>\d+) of the line", "from과 to는 라인의 0~{n} 수입니다"),
    (r"white or black", "white 또는 black입니다"),
    (r"the material records are missing: (?P<v>.+)", "물질 기록이 없습니다: {v}"),
    (r"a registry id", "definition은 레지스트리 id입니다"),
    (r"no definition (?P<v>.+)", "정의 {v}는 없습니다"),
    (r"no piece on (?P<v>.+)", "{v}에 기물이 없습니다"),
    (
        r"(?P<a>\S+) does not attack (?P<t>\S+)",
        "{a}는 {t}를 공격하지 않습니다(expected가 공격하는 칸)",
    ),
    (r"(?P<a>\S+) does not defend (?P<t>\S+)", "{a}는 {t}를 지키지 않습니다(expected가 지키는 칸)"),
    (
        r"exposed, not_exposed or undecided",
        "exposed는 exposed, not_exposed, undecided 중 하나입니다",
    ),
    (
        r"the exchange record has no entry for (?P<v>\S+) \(a king\?\)",
        "{v}의 교환 기록이 없습니다(킹?)",
    ),
    (r"a list of squares \(empty: not in check\)", "checkers는 칸의 목록입니다(비면 체크 아님)"),
    (r"give the moves, the count or both", "moves나 count, 또는 둘 다 주세요"),
    (r"no pattern list (?P<v>.+)", "패턴 목록 {v}는 없습니다(expected 참고)"),
    (r"some of (?P<v>.+)", "participants는 {v} 중 일부입니다"),
    (r"no such configuration in (?P<v>.+)", "{v}에 그런 배치가 없습니다"),
    (
        r"after_a and after_b are P \+ a \+ r and P \+ b \+ r for one P",
        "after_a와 after_b는 같은 P에서 P + a + r, P + b + r입니다",
    ),
    (r"a proposition of one of (?P<v>.+)", "{v} 중 한 종류의 명제입니다"),
    (r"the position is (?P<v>.)'s, after the reply", "그 국면은 {v} 쪽 응수 뒤의 국면입니다"),
    (r"both nested propositions are of one kind", "두 안쪽 명제는 같은 종류입니다"),
)
COMPILED = tuple((re.compile(p), t) for p, t in TEMPLATES)


def korean(problem: str) -> str:
    for pattern, template in COMPILED:
        found = pattern.fullmatch(problem)
        if found:
            return template.format(**found.groupdict())
    return f"받아들여지지 않았습니다: {problem}"  # another component's own message, framed


def violations_ko(violations: list[dict]) -> list[dict]:
    """§7: each violation's `problem` in Korean, the English kept as `problem_en`."""

    out = []
    for v in violations:
        problem = v.get("problem")
        out.append(v | {"problem": korean(problem), "problem_en": problem}
                   if isinstance(problem, str) else v)  # fmt: skip
    return out
