"""Harness rev. 18 (the change log, "the survey's kinds"): frame check v6 holds material denied
against a cited comparison that counts it (F7) and a rank the sentence counted itself (F8); the
guides v3 (tier 2) and v4 (tier 1) state the survey's rules."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tools.rx import frames, harness
from tools.rx import run as rx_run
from tools.rx import score as rx_score

V5, V6 = frames.FRAMES_V5, frames.FRAMES_V6
C = "c96." + "a" * 24
COMPARISON = ("claim", {"template": "better_move_v1", "status": "supported", "findings": [
    {"type": "ComparisonFinding", "best": {"delta": 1}, "played": {"delta": 0}}]})  # fmt: skip


def _call(text: str, cites: list[str], props: list[dict] = ()) -> dict:
    return {"items": [{"ply": 1, "propositions": list(props),
                       "sentences": [{"text": text, "cites": cites}]}]}  # fmt: skip


def _rules(out: dict) -> list[str]:
    return sorted(h["rule"] for h in out["held"])


@pytest.mark.parametrize("text", [
    "이 판정은 물질 손실이 아니라 교환 뒤의 위치 평가에서 나온다.",
    "따라서 두 수를 물질 셈으로 비교할 수 없고 평가로 봐야 한다.",
    "룩을 e5에 세우는 수는 얻은 것이 없다.",
])  # fmt: skip
def test_v6_holds_material_denied_against_a_cited_comparison(text) -> None:
    by_handle = _call(text, [C])
    assert frames.claims_needed(by_handle) == {C}
    assert _rules(frames.check(by_handle, {C: COMPARISON}, V6)) == ["F7"]
    assert _rules(frames.check(by_handle, {C: COMPARISON}, V5)) == []  # rev. 17 as it ran
    explicit = _call(text, ["p"], [{"id": "p", "kind": "claim", "claim": C}])
    assert frames.claims_needed(explicit) == {C}
    assert _rules(frames.check(explicit, {C: COMPARISON}, V6)) == ["F7"]


def test_v6_leaves_a_denial_with_no_material_comparison_cited() -> None:
    level = ("claim", {"template": "better_move_v1", "status": "supported", "findings": [
        {"type": "ComparisonFinding", "best": {"delta": 0}, "played": {"delta": 0}}]})  # fmt: skip
    text = "이 수의 차이는 물질이 아니라 킹의 안전에서 나온다."
    assert _rules(frames.check(_call(text, [C]), {C: level}, V6)) == []
    assert _rules(frames.check(_call(text, ["s1." + "b" * 24]), {}, V6)) == []
    assert _rules(frames.check(_call("백이 1점을 얻는다.", [C]), {C: COMPARISON}, V6)) == []


@pytest.mark.parametrize("text, held", [
    ("둔 15...Nxf2가 -1.75이므로 둔 수는 셋째 후보입니다.", True),
    ("이 수는 엔진 후보 중 3위였다.", True),
    ("29.d7이 4번째 후보다.", True),
    ("엔진의 1순위는 29.d7이고 2순위는 29.g4다.", False),
    ("3수 뒤 백이 앞선다.", False),
    ("e3 위치의 비숍이 위협을 받는다.", False),
])  # fmt: skip
def test_v6_holds_a_rank_the_sentence_counted(text, held) -> None:
    assert ("F8" in _rules(frames.check(_call(text, []), {}, V6))) is held


def test_revision_18_is_revision_17_with_frame_check_v6_and_the_guides() -> None:
    import inspect

    assert harness.VERSIONS[18] == harness.VERSIONS[17] and harness.FRAMES[18] == V6
    assert harness.TIER1_GUIDES[18] == "harness_tier1_v4" and harness.guide_of(18) == "harness_guide_v3"
    assert harness.guide_of(18, "harness_guide_v1") == "harness_guide_v1"  # the flag wins
    assert all(18 in t for t in (harness.TIERED, harness.LEAN_TIER1, harness.SHORT_HANDLES,
                                 harness.COMPLETE_CITES, harness.REVIEWED, harness.TIER2_LEAN))  # fmt: skip
    for name in ("harness_guide_v3", "harness_tier1_v4"):
        text = (harness.PROMPTS / f"{name}.md").read_text(encoding="utf-8")
        assert "단정과 숫자의 경계" in text and name in text
    assert "default=18" in inspect.getsource(rx_score.main)
    info = rx_run._harness_info(SimpleNamespace(arm="H", harness_revision=18, harness_guide=None))
    assert info["harness_guide"] == "harness_guide_v3" and info["harness_frames"] == V6
