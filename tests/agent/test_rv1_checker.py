"""RV-1 (docs/design/review-2026-11-11.md) P4-1, P4-2: the sentence check reads a symbol drawn as a
minus or a capture mark as one, and a lone Hangul jamo touching a token is a foreign letter."""

from __future__ import annotations

import pytest

from calliope.agent.sentences import Allowed, check_sentences, tokens


def _plus_one() -> Allowed:
    allowed = Allowed()
    allowed.scores.add(100)
    return allowed


def _quiet_rook() -> Allowed:
    allowed = Allowed()
    allowed.add_move("e1e3", "4k3/8/8/8/8/8/8/4R1K1 w - - 0 17")
    return allowed


def _problems(text: str, allowed: Allowed) -> list[dict]:
    sentence = {"text": text, "class": "sourced", "cites": ["p1"]}
    return [p for p in check_sentences("ko", [sentence], {"p1": allowed}) if p.get("rule") == "S3"]


@pytest.mark.parametrize("sign", ["˗", "➖", "─", "∓", "⁃", "⎯"])
def test_a_symbol_drawn_as_a_minus_is_read_as_one(sign) -> None:
    assert tokens(f"평가는 {sign}1.00이다") == ["-1.00"]
    assert _problems(f"평가는 {sign}1.00이다", _plus_one())  # -1.00 is not the cited +1.00
    assert not _problems("평가는 +1.00이다", _plus_one())


@pytest.mark.parametrize("mark", ["×", "✕", "⨯"])
def test_a_symbol_drawn_as_a_capture_mark_is_read_as_one(mark) -> None:
    assert tokens(f"백은 Q{mark}e3로 잡았다") == ["Qxe3"]
    assert _problems(f"백은 Q{mark}e3로 잡았다", _quiet_rook())
    assert not _problems("백은 Re3로 옮겼다", _quiet_rook())


@pytest.mark.parametrize("text", ["평가는 ㅡ1.00이다", "OㅡO로 캐슬링", "Rxeㅣ로 잡는다"])
def test_a_lone_jamo_touching_a_token_is_a_foreign_letter(text) -> None:
    got = _problems(text, _plus_one())
    assert any("touches a move or number" in p["problem"] for p in got)


def test_hangul_syllables_touching_a_token_are_still_fine() -> None:
    assert not _problems("평가는 +1.00이고 흑이 밀린다", _plus_one())
